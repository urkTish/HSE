"""Phase 2 scheduled jobs (spec 2-access-permits §4 "Job" transitions, §5.9 LC-1/LC-3/LC-12/LC-13,
§5.12 retention, §6.3 alert dates, §7 alerts). Every job is idempotent: alerts are sent once per
trigger (``job_marks`` keys or the row's ``alerts_sent``) and transitions only move forward.

Alert texts carry worker_no, name and credential number, never ID numbers or background status.
"""

import uuid
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.core.access_enums import (
    BackgroundCheckStatus,
    CredentialAction,
    CredentialKind,
    CredentialReason,
    CustodyStatus,
    DeploymentStatus,
    InductionStatus,
    NotamStatus,
    PassApplicationStatus,
    SuspensionState,
    ValidityStatus,
    VehicleStatus,
    WorkerIdType,
    WorkerStatus,
)
from app.core.clock import now, today
from app.core.enums import AuditAction, EntityType, NotificationKind, Role
from app.core.hse_enums import AttachmentOwner, IncidentStatus
from app.hse_jobs import once
from app.kpi.periods import add_months
from app.models import (
    AccessSettings,
    Adp,
    AirportPass,
    Attachment,
    Avp,
    CredentialEvent,
    CredentialSuspension,
    Deployment,
    GateCheck,
    Incident,
    InductionCourse,
    InductionRecord,
    InjuryCase,
    NotamRequest,
    ObstacleClearance,
    PassApplication,
    ProjectEngagement,
    Vehicle,
    Wap,
    Worker,
    WorkerIdHistory,
)
from app.services import attachments, audit, notify
from app.services.access import (
    common,
    credentials,
    gates,
    inductions,
    lifecycle,
    passes,
    waps,
    workers,
    works,
)
from app.services.hse_common import contractor_reps

ID = uuid.UUID
LIVE = (ValidityStatus.active, ValidityStatus.suspended)
APPROVED_OBS = works.APPROVED
NTM_PENDING = (NotamStatus.submitted_to_ops, NotamStatus.requested_from_ais)
APPLICATION_COLLECT_DAYS = 30  # §4.4 Approved → Cancelled, ASSUMPTION
WORKER_INACTIVE_DAYS = 30  # §4.1


# ---- helpers -------------------------------------------------------------------------------------


def _officers(db: Session, pid: ID) -> set[ID]:
    return set(notify.users_with_role(db, Role.hse_officer, [pid]))


def _managers(db: Session) -> set[ID]:
    return set(notify.managers(db))


def _reps(db: Session, pid: ID, eid: ID | None) -> set[ID]:
    return set(contractor_reps(db, pid, eid))


def _send(
    db: Session,
    users: Iterable[ID],
    kind: NotificationKind,
    en: str,
    ar: str,
    entity_type: EntityType | None,
    entity_id: ID | None,
    project_id: ID | None,
) -> None:
    notify.notify(db, users, kind, en, ar, None, None, entity_type, entity_id, project_id)


def long_due(db: Session, base: str, until: date | None, day: date, sched: list[int]) -> int | None:
    """§6.3: alert on until − n for n in the schedule; an alert date already past fires once with
    the current days_left (most urgent unsent threshold only). Returns that threshold or None."""
    if until is None:
        return None
    left = (until - day).days
    if left < 0:
        return None
    due = sorted(t for t in sched if left <= t)
    if not due:
        return None
    if not once(db, f"{base}:{until.isoformat()}:{due[0]}"):
        return None
    for t in due[1:]:
        once(db, f"{base}:{until.isoformat()}:{t}")
    return due[0]


def short_due(sent: list[str], end: datetime, at: datetime, sched: list[int]) -> int | None:
    """§6.3 short-window items: 72 / 24 / 0 h before the end (most urgent unsent only)."""
    if at > end + timedelta(hours=1):
        return None
    due = sorted(h for h in sched if at >= end - timedelta(hours=h))
    if not due or f"end:{due[0]}" in sent:
        return None
    return due[0]


def _worker_label(w: Worker | None) -> str:
    return f"{w.worker_no} {w.full_name_en}" if w else "—"


def _worker_label_ar(w: Worker | None) -> str:
    return f"{w.worker_no} {w.full_name_ar}" if w else "—"


def _settings(db: Session) -> dict[ID, AccessSettings]:
    return {s.project_id: s for s in db.scalars(select(AccessSettings))}


# ---- 00:05 daily ---------------------------------------------------------------------------------


def access_daily(db: Session, day: date | None = None) -> dict[str, Any]:
    """00:05: induction expiry (§4.3), credential validity / dependency suspensions and expiry
    (§4.5, LC-1/LC-6), obstacle expiry/suspension (§4.7), deployments of demobilised
    engagements (§4.2), uncollected approvals cancelled (§4.4), inactive workers (§4.1), ID-copy
    retention (P2-5). Status changes made by the job are notified to the holder's audience."""
    day = day or today()
    started = now()
    out: dict[str, Any] = {"inductions_expired": inductions.expire_records(db, day)}
    for ps in list(db.scalars(select(AirportPass).where(AirportPass.validity_status.in_(LIVE)))):
        lifecycle.evaluate_pass(db, ps, day)
    for a in list(
        db.scalars(select(Adp).where(Adp.validity_status.in_(LIVE), Adp.pass_id.is_(None)))
    ):
        lifecycle.evaluate_adp(db, a, day)
    for a in list(
        db.scalars(select(Adp).where(Adp.validity_status.in_(LIVE), Adp.pass_id.is_not(None)))
    ):
        lifecycle.evaluate_adp(db, a, day)
    for v in list(db.scalars(select(Avp).where(Avp.validity_status.in_(LIVE)))):
        lifecycle.evaluate_avp(db, v, day)
    db.flush()
    out["obstacles_changed"] = works.obstacle_job(db, day)
    out["deployments_demobilised"] = _demobilise_ended_engagements(db, day)
    out["applications_cancelled"] = _cancel_uncollected(db, day)
    out["workers_inactive"] = _workers_inactive(db, day)
    out["id_copies_deleted"] = passes.delete_id_copies(db, day)
    out["status_notices"] = _notify_system_changes(db, started)
    return out


def _notify_system_changes(db: Session, since: datetime) -> int:
    """§7 "any suspension / revocation" and expiry for changes made by a job (no actor)."""
    n = 0
    actions = {
        CredentialAction.auto_suspended: ("suspended by the system", "أوقف تلقائياً"),
        CredentialAction.auto_reinstated: ("reinstated automatically", "أعيد تفعيله تلقائياً"),
        CredentialAction.expired: ("expired", "انتهت صلاحيته"),
        CredentialAction.revoked: ("revoked", "أُلغي"),
    }
    for ev in db.scalars(
        select(CredentialEvent).where(
            CredentialEvent.occurred_at >= since,
            CredentialEvent.actor_user_id.is_(None),
            CredentialEvent.action.in_(list(actions)),
        )
    ):
        s = credentials.subject(db, ev.credential_kind, ev.credential_id)
        if s is None:
            continue
        en, ar = actions[ev.action]
        credentials.status_changed(db, s, f"{en} ({ev.reason_code.value})", ar)
        n += 1
    return n


def _demobilise_ended_engagements(db: Session, day: date) -> int:
    n = 0
    for d, end in db.execute(
        select(Deployment, ProjectEngagement.demobilisation_date)
        .join(ProjectEngagement, ProjectEngagement.id == Deployment.engagement_id)
        .where(
            Deployment.status != DeploymentStatus.demobilised,
            ProjectEngagement.demobilisation_date < day,
        )
    ).all():
        on = max(end or day, d.mobilised_on)
        workers.demobilise(db, d, on, CredentialReason.demobilised, None)
        audit.record(
            db,
            AuditAction.status_change,
            entity_type=EntityType.worker_deployment,
            entity_id=d.id,
            project_id=d.project_id,
            after={"status": d.status, "demobilised_on": on},
            details={"reason": "engagement demobilisation date passed"},
        )
        n += 1
    return n


def _cancel_uncollected(db: Session, day: date) -> int:
    n = 0
    for a in db.scalars(
        select(PassApplication).where(
            PassApplication.status == PassApplicationStatus.approved,
            PassApplication.decided_at.is_not(None),
        )
    ):
        assert a.decided_at is not None  # noqa: S101
        if (day - common.local_day(a.decided_at)).days <= APPLICATION_COLLECT_DAYS:
            continue
        a.status = PassApplicationStatus.cancelled
        a.closed_at = now()
        audit.record(
            db,
            AuditAction.status_change,
            entity_type=EntityType.pass_application,
            entity_id=a.id,
            project_id=a.project_id,
            before={"status": "approved"},
            after={"status": "cancelled"},
            details={"reason": f"not collected within {APPLICATION_COLLECT_DAYS} days"},
        )
        n += 1
    return n


def _workers_inactive(db: Session, day: date) -> int:
    open_dep = exists().where(
        Deployment.worker_id == Worker.id, Deployment.status != DeploymentStatus.demobilised
    )
    last_demob = (
        select(func.max(Deployment.demobilised_on))
        .where(Deployment.worker_id == Worker.id)
        .scalar_subquery()
    )
    n = 0
    for w, last in db.execute(
        select(Worker, last_demob).where(Worker.status == WorkerStatus.active, ~open_dep)
    ).all():
        since = last or common.local_day(w.created_at)
        if (day - since).days < WORKER_INACTIVE_DAYS:
            continue
        w.status = WorkerStatus.inactive
        w.inactive_since = day
        audit.record(
            db,
            AuditAction.status_change,
            entity_type=EntityType.worker,
            entity_id=w.id,
            before={"status": "active"},
            after={"status": "inactive"},
            details={"reason": f"no deployment for {WORKER_INACTIVE_DAYS} days"},
        )
        n += 1
    return n


# ---- 07:00 alerts --------------------------------------------------------------------------------


def credential_alerts(db: Session, day: date | None = None) -> dict[str, Any]:
    """§7 long-validity alerts (30/14/7/0, §6.3) and the daily digests: inductions, re-induction,
    worker ID, passport registration (WK-8), passes, background recheck, ADPs, AVPs, vehicle
    documents, stale applications (AP-14), return due / overdue, ADP suspension ended."""
    day = day or today()
    st = _settings(db)
    counts = {
        "induction": _induction_alerts(db, day, st),
        "reinduction": _reinduction_alerts(db, day),
        "worker_id": _worker_id_alerts(db, day, st),
        "passport": _passport_alerts(db, day),
        "pass": _pass_alerts(db, day, st),
        "adp": _adp_avp_alerts(db, day, st, Adp),
        "avp": _adp_avp_alerts(db, day, st, Avp),
        "vehicle_docs": _vehicle_doc_alerts(db, day, st),
        "stale": _stale_applications(db, day, st),
        "returns": _return_alerts(db, day),
        "adp_suspension_ended": _adp_suspension_ended(db, day),
    }
    return counts


def _sched(st: dict[ID, AccessSettings], pid: ID) -> list[int]:
    s = st.get(pid)
    return list(s.alert_schedule_long_days) if s else [30, 14, 7, 0]


def _induction_alerts(db: Session, day: date, st: dict[ID, AccessSettings]) -> int:
    n = 0
    for r, d in db.execute(
        select(InductionRecord, Deployment)
        .join(Deployment, Deployment.id == InductionRecord.deployment_id)
        .where(
            InductionRecord.status == InductionStatus.valid,
            Deployment.status != DeploymentStatus.demobilised,
        )
    ).all():
        until = lifecycle.induction_valid_until(r)
        t = long_due(db, f"acc:ind:{r.id}", until, day, _sched(st, r.project_id))
        if t is None or until is None:
            continue
        w = db.get(Worker, r.worker_id)
        course = db.get(InductionCourse, r.course_id)
        code = course.code if course else ""
        users = _reps(db, r.project_id, d.engagement_id)
        if t <= 7:
            users |= _officers(db, r.project_id)
        left = (until - day).days
        _send(
            db, users, NotificationKind.induction_expiry,
            f"{_worker_label(w)}: {code} induction {r.induction_no} expires on {until} "
            f"({left} days)",
            f"{_worker_label_ar(w)}: تنتهي صلاحية التعريف {code} {r.induction_no} في {until}",
            EntityType.induction_record, r.id, r.project_id,
        )  # fmt: skip
        n += 1
    return n


def _reinduction_alerts(db: Session, day: date) -> int:
    """IN-9: 7 days before and on reinduction_due_on (the publish alert is sent on publish)."""
    n = 0
    for r in db.scalars(
        select(InductionRecord).where(
            InductionRecord.status == InductionStatus.valid,
            InductionRecord.reinduction_due_on.is_not(None),
        )
    ):
        assert r.reinduction_due_on is not None  # noqa: S101
        left = (r.reinduction_due_on - day).days
        if left not in (7, 0) or not once(db, f"acc:reind:{r.id}:{left}"):
            continue
        w = db.get(Worker, r.worker_id)
        users = _reps(db, r.project_id, r.engagement_id) | _officers(db, r.project_id)
        _send(
            db, users, NotificationKind.reinduction_due,
            f"{_worker_label(w)}: re-induction due on {r.reinduction_due_on} ({r.induction_no})",
            f"{_worker_label_ar(w)}: إعادة التعريف مستحقة في {r.reinduction_due_on}",
            EntityType.induction_record, r.id, r.project_id,
        )  # fmt: skip
        n += 1
    return n


def _live_deployments(db: Session) -> list[tuple[Deployment, Worker]]:
    return [
        (d, w)
        for d, w in db.execute(
            select(Deployment, Worker)
            .join(Worker, Worker.id == Deployment.worker_id)
            .where(
                Deployment.status != DeploymentStatus.demobilised,
                Worker.status.in_([WorkerStatus.active, WorkerStatus.inactive]),
            )
        ).all()
    ]


def _worker_id_alerts(db: Session, day: date, st: dict[ID, AccessSettings]) -> int:
    n = 0
    for d, w in _live_deployments(db):
        until = w.id_expiry_date
        t = long_due(db, f"acc:wid:{w.id}:{d.project_id}", until, day, _sched(st, d.project_id))
        if t is None or until is None:
            continue
        users = _reps(db, d.project_id, d.engagement_id)
        if t == 0:
            users |= _officers(db, d.project_id)
        left = (until - day).days
        _send(
            db, users, NotificationKind.worker_id_expiry,
            f"{_worker_label(w)}: worker ID expires on {until} ({left} days)",
            f"{_worker_label_ar(w)}: تنتهي هوية العامل في {until} ({left} يوماً)",
            EntityType.worker, w.id, d.project_id,
        )  # fmt: skip
        n += 1
    return n


def _passport_alerts(db: Session, day: date) -> int:
    """WK-8: registered with a passport — alert on mobilised_on + 60 and + 90 days."""
    n = 0
    for d, w in _live_deployments(db):
        if w.id_type != WorkerIdType.passport:
            continue
        age = (day - d.mobilised_on).days
        due = [t for t in (60, 90) if age >= t and t not in (d.passport_alerts_sent or [])]
        if not due:
            continue
        d.passport_alerts_sent = sorted({*(d.passport_alerts_sent or []), *due})
        _send(
            db, _reps(db, d.project_id, d.engagement_id), NotificationKind.passport_registration,
            f"{_worker_label(w)}: registered with a passport for {age} days; "
            "replace it with the Iqama",
            f"{_worker_label_ar(w)}: مسجل بجواز السفر منذ {age} يوماً؛ يرجى تحديثه بالإقامة",
            EntityType.worker, w.id, d.project_id,
        )  # fmt: skip
        n += 1
    return n


def _pass_alerts(db: Session, day: date, st: dict[ID, AccessSettings]) -> int:
    n = 0
    for ps in db.scalars(
        select(AirportPass).where(AirportPass.validity_status == ValidityStatus.active)
    ):
        w = db.get(Worker, ps.worker_id)
        until = ps.effective_valid_until
        t = long_due(db, f"acc:pass:{ps.id}", until, day, _sched(st, ps.project_id))
        if t is not None and until is not None:
            lf = ps.limiting_factor.value if ps.limiting_factor else "card_expiry_date"
            left = (until - day).days
            users = _reps(db, ps.project_id, ps.engagement_id) | _officers(db, ps.project_id)
            _send(
                db, users, NotificationKind.airport_pass_expiry,
                f"{_worker_label(w)}: pass {ps.pass_no} valid until {until} ({left} days; "
                f"limited by {lf})",
                f"{_worker_label_ar(w)}: ينتهي التصريح {ps.pass_no} في {until} ({lf})",
                EntityType.airport_pass, ps.id, ps.project_id,
            )  # fmt: skip
            n += 1
        if ps.escorted:
            continue
        bg = lifecycle.background(db.get(PassApplication, ps.application_id))
        if bg.get("status") != BackgroundCheckStatus.cleared.value or not bg.get("recheck_due"):
            continue
        due_on = date.fromisoformat(str(bg["recheck_due"]))
        t = long_due(db, f"acc:bg:{ps.id}", due_on, day, _sched(st, ps.project_id))
        if t is None:
            continue
        _send(
            db, _officers(db, ps.project_id), NotificationKind.bg_recheck_due,
            f"{ps.pass_no}: background recheck due on {due_on}",
            f"{ps.pass_no}: إعادة التحقق الأمني مستحقة في {due_on}",
            EntityType.airport_pass, ps.id, ps.project_id,
        )  # fmt: skip
        n += 1
    return n


def _adp_avp_alerts(
    db: Session, day: date, st: dict[ID, AccessSettings], model: type[Adp] | type[Avp]
) -> int:
    n = 0
    rows: list[Adp | Avp] = list(
        db.scalars(select(model).where(model.validity_status == ValidityStatus.active))
    )
    for obj in rows:
        until = obj.effective_valid_until
        is_adp = isinstance(obj, Adp)
        t = long_due(
            db, f"acc:{'adp' if is_adp else 'avp'}:{obj.id}", until, day, _sched(st, obj.project_id)
        )
        if t is None or until is None:
            continue
        users = _reps(db, obj.project_id, obj.engagement_id)
        if t <= 7:
            users |= _officers(db, obj.project_id)
        left = (until - day).days
        lf = obj.limiting_factor.value if obj.limiting_factor else "own_valid_until"
        if isinstance(obj, Adp):
            who = _worker_label(db.get(Worker, obj.worker_id))
            ref, kind, et = obj.adp_no or "ADP", NotificationKind.adp_expiry, EntityType.adp
        else:
            v = db.get(Vehicle, obj.vehicle_id)
            who = v.vehicle_no if v else "—"
            ref, kind, et = obj.avp_no or "AVP", NotificationKind.avp_expiry, EntityType.avp
        _send(
            db, users, kind,
            f"{who}: {ref} valid until {until} ({left} days; limited by {lf})",
            f"{who}: ينتهي {ref} في {until} ({lf})",
            et, obj.id, obj.project_id,
        )  # fmt: skip
        n += 1
    return n


def _vehicle_doc_alerts(db: Session, day: date, st: dict[ID, AccessSettings]) -> int:
    n = 0
    for v in db.scalars(select(Vehicle).where(Vehicle.status == VehicleStatus.active)):
        docs = {
            "istimara": v.istimara_expiry,
            "insurance": v.insurance_expiry,
            "mvpi": v.mvpi_expiry,
        }
        for doc, until in docs.items():
            t = long_due(db, f"acc:vdoc:{v.id}:{doc}", until, day, _sched(st, v.project_id))
            if t is None or until is None:
                continue
            users = _reps(db, v.project_id, v.engagement_id)
            if t <= 7:
                users |= _officers(db, v.project_id)
            left = (until - day).days
            _send(
                db, users, NotificationKind.vehicle_document_expiry,
                f"{v.vehicle_no}: {doc} expires on {until} ({left} days)",
                f"{v.vehicle_no}: تنتهي وثيقة {doc} في {until}",
                EntityType.vehicle, v.id, v.project_id,
            )  # fmt: skip
            n += 1
    return n


def _stale_applications(db: Session, day: date, st: dict[ID, AccessSettings]) -> int:
    """AP-14: Lodged > application_stale_days → HSE Officer at stale days, then weekly; the HSE
    Manager from 2 × stale days."""
    n = 0
    for a in db.scalars(
        select(PassApplication).where(
            PassApplication.status == PassApplicationStatus.lodged,
            PassApplication.lodged_at.is_not(None),
        )
    ):
        assert a.lodged_at is not None  # noqa: S101
        s = st.get(a.project_id)
        stale = s.application_stale_days if s else 21
        age = (day - common.local_day(a.lodged_at)).days
        if age < stale:
            continue
        if a.stale_alerted_on is not None and (day - a.stale_alerted_on).days < 7:
            continue
        a.stale_alerted_on = day
        users = _officers(db, a.project_id)
        if age >= 2 * stale:
            users |= _managers(db)
        _send(
            db, users, NotificationKind.pass_application_stale,
            f"{a.application_no}: lodged for {age} days without a decision",
            f"{a.application_no}: مقدم للجهة منذ {age} يوماً دون قرار",
            EntityType.pass_application, a.id, a.project_id,
        )  # fmt: skip
        n += 1
    return n


def _return_alerts(db: Session, day: date) -> int:
    """§7 return due (once, on Return Due) and overdue (daily; officer from 1 day, manager at 7)."""
    n = 0
    items: list[tuple[AirportPass | Adp | Avp, EntityType, str]] = []
    for ps in db.scalars(
        select(AirportPass).where(AirportPass.custody_status == CustodyStatus.return_due)
    ):
        items.append((ps, EntityType.airport_pass, ps.pass_no))
    for a in db.scalars(select(Adp).where(Adp.custody_status == CustodyStatus.return_due)):
        items.append((a, EntityType.adp, a.adp_no or "ADP"))
    for v in db.scalars(select(Avp).where(Avp.custody_status == CustodyStatus.return_due)):
        items.append((v, EntityType.avp, v.avp_no or "AVP"))
    for obj, et, ref in items:
        if obj.return_due_on is None:
            continue
        over = (day - obj.return_due_on).days
        users = _reps(db, obj.project_id, obj.engagement_id)
        if over <= 0:
            if not once(db, f"acc:retdue:{obj.id}:{obj.return_due_on}"):
                continue
            kind = NotificationKind.return_due
            en = f"{ref}: return the card by {obj.return_due_on}"
            ar = f"{ref}: يجب إرجاع البطاقة بحلول {obj.return_due_on}"
        else:
            if not once(db, f"acc:retover:{obj.id}:{day}"):
                continue
            kind = NotificationKind.return_overdue
            users |= _officers(db, obj.project_id)
            if over >= 7:
                users |= _managers(db)
            en = f"{ref}: return overdue by {over} days (due {obj.return_due_on})"
            ar = f"{ref}: تأخر الإرجاع {over} يوماً"
        _send(db, users, kind, en, ar, et, obj.id, obj.project_id)
        n += 1
    return n


def _adp_suspension_ended(db: Session, day: date) -> int:
    n = 0
    for sp in db.scalars(
        select(CredentialSuspension).where(
            CredentialSuspension.credential_kind == CredentialKind.adp,
            CredentialSuspension.lifted_at.is_(None),
            CredentialSuspension.suspension_end.is_not(None),
            CredentialSuspension.suspension_end < day,
        )
    ):
        if not once(db, f"acc:adpend:{sp.id}"):
            continue
        a = db.get(Adp, sp.credential_id)
        if a is None or a.validity_status != ValidityStatus.suspended:
            continue
        _send(
            db, _officers(db, a.project_id), NotificationKind.adp_suspension_ended,
            f"{a.adp_no}: suspension period ended {sp.suspension_end}; reinstatement possible",
            f"{a.adp_no}: انتهت فترة الإيقاف في {sp.suspension_end}؛ يمكن إعادة التفعيل",
            EntityType.adp, a.id, a.project_id,
        )  # fmt: skip
        n += 1
    return n


# ---- every minute --------------------------------------------------------------------------------


def access_minute(db: Session, at: datetime | None = None) -> dict[str, Any]:
    """Ending alerts first (so the 0 h alert precedes closure), then NOTAM expiry (§4.6), ops
    events (WA-15), WAP activation / window / closure (§4.8), raised-suspension expiry (LC-3),
    lost-report deadlines (LC-12) and timed-out gate pairings (GC-8)."""
    at = at or now()
    return {
        "ending_alerts": ending_alerts(db, at),
        "notam_not_issued": _notam_not_issued(db, at),
        "notams_expired": works.expire_notams(db, at),
        "ops": waps.ops_job(db, at),
        "waps": waps.wap_job(db, at),
        "raised": raised_suspensions(db, at),
        "lost_deadlines": _lost_deadlines(db, at),
        "pairings_timed_out": gates.pairing_timeout_job(db, at),
    }


def ending_alerts(db: Session, at: datetime) -> int:
    """§6.3 / §7: WAP, NOTAM and obstacle clearance ending — 72 / 24 / 0 h before the end."""
    st = _settings(db)
    n = 0

    def hours(pid: ID) -> list[int]:
        s = st.get(pid)
        return list(s.alert_schedule_short_hours) if s else [72, 24, 0]

    def mark(row: Wap | NotamRequest | ObstacleClearance, h: int, sched: list[int]) -> None:
        keys = {f"end:{x}" for x in sched if x >= h}
        row.alerts_sent = [*(row.alerts_sent or []), *sorted(keys - set(row.alerts_sent or []))]

    for w in db.scalars(select(Wap).where(Wap.revision_of_id.is_(None), Wap.status.in_(waps.LIVE))):
        end = common.local_midnight_utc(w.valid_to + timedelta(days=1))
        sched = hours(w.project_id)
        h = short_due(list(w.alerts_sent or []), end, at, sched)
        if h is None:
            continue
        mark(w, h, sched)
        users = {w.requested_by_user_id} | _reps(db, w.project_id, w.engagement_id)
        _send(
            db, users, NotificationKind.wap_ending,
            f"{w.wap_no}: ends {w.valid_to} 24:00 ({h} h)",
            f"{w.wap_no}: ينتهي في {w.valid_to} الساعة 24:00 ({h} ساعة)",
            EntityType.wap, w.id, w.project_id,
        )  # fmt: skip
        n += 1
    for nt in db.scalars(
        select(NotamRequest).where(
            NotamRequest.status == NotamStatus.issued, NotamRequest.effective_to_utc.is_not(None)
        )
    ):
        if nt.effective_to_utc is None:
            continue
        sched = hours(nt.project_id)
        h = short_due(list(nt.alerts_sent or []), nt.effective_to_utc, at, sched)
        if h is None:
            continue
        mark(nt, h, sched)
        users = {nt.requested_by_user_id} | _reps(db, nt.project_id, nt.engagement_id)
        ends = common.notam_format(nt.effective_to_utc)
        _send(
            db, users, NotificationKind.notam_ending,
            f"{nt.ntm_no} ({nt.notam_number}): ends {ends} UTC ({h} h)",
            f"{nt.ntm_no} ({nt.notam_number}): ينتهي {ends} UTC ({h} ساعة)",
            EntityType.notam_request, nt.id, nt.project_id,
        )  # fmt: skip
        n += 1
    for o in db.scalars(
        select(ObstacleClearance).where(
            ObstacleClearance.status.in_(APPROVED_OBS), ObstacleClearance.valid_to.is_not(None)
        )
    ):
        assert o.valid_to is not None  # noqa: S101
        end = common.local_midnight_utc(o.valid_to + timedelta(days=1))
        sched = hours(o.project_id)
        h = short_due(list(o.alerts_sent or []), end, at, sched)
        if h is None:
            continue
        mark(o, h, sched)
        users = {o.requested_by_user_id} | _reps(db, o.project_id, o.engagement_id)
        _send(
            db, users, NotificationKind.obstacle_clearance_ending,
            f"{o.obs_no}: clearance ends {o.valid_to} 24:00 ({h} h)",
            f"{o.obs_no}: تنتهي الموافقة في {o.valid_to} الساعة 24:00 ({h} ساعة)",
            EntityType.obstacle_clearance, o.id, o.project_id,
        )  # fmt: skip
        n += 1
    db.flush()
    return n


def _notam_not_issued(db: Session, at: datetime) -> int:
    """§7: a NOTAM request still not Issued 48 h before the requested start."""
    n = 0
    for nt in db.scalars(
        select(NotamRequest).where(
            NotamRequest.status.in_(NTM_PENDING),
            NotamRequest.requested_start_utc > at,
            NotamRequest.requested_start_utc <= at + timedelta(hours=48),
        )
    ):
        if "t48" in (nt.alerts_sent or []):
            continue
        nt.alerts_sent = [*(nt.alerts_sent or []), "t48"]
        users = {nt.requested_by_user_id} | _officers(db, nt.project_id)
        starts = common.notam_format(nt.requested_start_utc)
        _send(
            db, users, NotificationKind.notam_not_issued,
            f"{nt.ntm_no}: not yet issued; works start {starts} UTC",
            f"{nt.ntm_no}: لم يصدر بعد؛ تبدأ الأعمال {starts} UTC",
            EntityType.notam_request, nt.id, nt.project_id,
        )  # fmt: skip
        n += 1
    return n


def raised_suspensions(db: Session, at: datetime | None = None) -> int:
    """LC-3: a raised suspension not confirmed — reminder to HSE Officers at 48 h; at
    raised_suspension_max_hours it lifts automatically (`auto_reinstated` when nothing else is
    open), notifying the raiser and HSE Officers."""
    at = at or now()
    n = 0
    for sp in list(
        db.scalars(
            select(CredentialSuspension).where(
                CredentialSuspension.state == SuspensionState.raised,
                CredentialSuspension.lifted_at.is_(None),
                CredentialSuspension.confirmed_at.is_(None),
            )
        )
    ):
        s = credentials.subject(db, sp.credential_kind, sp.credential_id)
        if s is None or s.project_id is None:
            continue
        officers = _officers(db, s.project_id)
        et = credentials.ENTITY[sp.credential_kind]
        if sp.expires_at is not None and at >= sp.expires_at:
            lifecycle.lift(db, s.obj, sp, None, "Raised suspension not confirmed (LC-3)", at=at)
            users = officers | ({sp.raised_by_user_id} if sp.raised_by_user_id else set())
            _send(
                db, users, NotificationKind.raised_suspension_pending,
                f"{s.number}: raised suspension not confirmed — lifted automatically",
                f"{s.number}: لم يؤكد الإيقاف المرفوع — رُفع تلقائياً",
                et, s.obj.id, s.project_id,
            )  # fmt: skip
            credentials.after_change(db, s)
            n += 1
        elif at - sp.raised_at >= timedelta(hours=48) and "48h" not in (sp.alerts_sent or []):
            sp.alerts_sent = [*(sp.alerts_sent or []), "48h"]
            _send(
                db, officers, NotificationKind.raised_suspension_pending,
                f"{s.number}: raised suspension awaiting confirmation (48 h)",
                f"{s.number}: إيقاف مرفوع بانتظار التأكيد (48 ساعة)",
                et, s.obj.id, s.project_id,
            )  # fmt: skip
            n += 1
    db.flush()
    return n


def _lost_deadlines(db: Session, at: datetime) -> int:
    """LC-12: authority not notified within lost_report_hours → HSE Officer and HSE Manager."""
    st = _settings(db)
    n = 0
    rows: list[tuple[AirportPass | Adp | Avp, EntityType, str]] = []
    for ps in db.scalars(
        select(AirportPass).where(
            AirportPass.lost_reported_at.is_not(None), AirportPass.authority_notified_at.is_(None)
        )
    ):
        rows.append((ps, EntityType.airport_pass, ps.pass_no))
    for a in db.scalars(
        select(Adp).where(Adp.lost_reported_at.is_not(None), Adp.authority_notified_at.is_(None))
    ):
        rows.append((a, EntityType.adp, a.adp_no or "ADP"))
    for v in db.scalars(
        select(Avp).where(Avp.lost_reported_at.is_not(None), Avp.authority_notified_at.is_(None))
    ):
        rows.append((v, EntityType.avp, v.avp_no or "AVP"))
    for obj, et, ref in rows:
        assert obj.lost_reported_at is not None  # noqa: S101
        s = st.get(obj.project_id)
        hrs = s.lost_report_hours if s else 24
        if at < obj.lost_reported_at + timedelta(hours=hrs):
            continue
        if not once(db, f"acc:lost:{obj.id}"):
            continue
        _send(
            db, _officers(db, obj.project_id) | _managers(db),
            NotificationKind.lost_authority_not_notified,
            f"{ref}: reported lost; issuing authority not notified within {hrs} h",
            f"{ref}: أُبلغ عن فقده ولم تُبلغ الجهة المصدرة خلال {hrs} ساعة",
            et, obj.id, obj.project_id,
        )  # fmt: skip
        n += 1
    return n


# ---- weekly retention ----------------------------------------------------------------------------


def access_retention(db: Session, day: date | None = None) -> dict[str, Any]:
    """P2-6 gate-log purge and P2-7 worker anonymisation."""
    day = day or today()
    return {
        "gate_rows_purged": gates.purge_log(db, common.local_midnight_utc(day)),
        "workers_anonymised": anonymise_workers(db, day),
    }


def anonymise_workers(db: Session, day: date | None = None) -> int:
    """P2-7: worker_retention_years after the last deployment's demobilised_on, with no open
    incident link and no injury-case link (those follow Phase 1 P1-5): names replaced, photo, ID
    number, ID history, blind index, nationality and passport country deleted; worker_no and
    statistics kept. Terminal."""
    day = day or today()
    st = _settings(db)
    open_dep = exists().where(
        Deployment.worker_id == Worker.id, Deployment.status != DeploymentStatus.demobilised
    )
    n = 0
    for w in list(
        db.scalars(select(Worker).where(Worker.status != WorkerStatus.anonymised, ~open_dep))
    ):
        deps = list(db.scalars(select(Deployment).where(Deployment.worker_id == w.id)))
        if not deps:
            continue
        years = max((st[d.project_id].worker_retention_years for d in deps if d.project_id in st),
                    default=5)  # fmt: skip
        last = max((d.demobilised_on for d in deps if d.demobilised_on), default=None)
        if last is None or day < add_months(last, 12 * years):
            continue
        if db.scalar(select(InjuryCase.id).where(InjuryCase.worker_id == w.id).limit(1)):
            continue
        open_inc = db.scalar(
            select(GateCheck.id)
            .join(Incident, Incident.id == GateCheck.incident_id)
            .where(GateCheck.worker_id == w.id, Incident.status != IncidentStatus.closed)
            .limit(1)
        )
        if open_inc is not None:
            continue
        for f in db.scalars(
            select(Attachment).where(
                Attachment.owner_type == AttachmentOwner.worker_photo, Attachment.owner_id == w.id
            )
        ):
            attachments.erase(db, f)
        for h in db.scalars(select(WorkerIdHistory).where(WorkerIdHistory.worker_id == w.id)):
            db.delete(h)
        w.full_name_en = f"Anonymised worker {w.worker_no}"
        w.full_name_ar = f"عامل مجهول الهوية {w.worker_no}"
        w.id_type = None
        w.id_number_enc = None
        w.id_number_bidx = None
        w.id_number_masked = None
        w.passport_country = None
        w.id_expiry_date = None
        w.nationality = None
        w.status = WorkerStatus.anonymised
        w.anonymised_at = now()
        w.search_text = w.worker_no.lower()
        audit.record(
            db,
            AuditAction.archive,
            entity_type=EntityType.worker,
            entity_id=w.id,
            details={"anonymised": True, "retention_years": years},
        )
        n += 1
    db.flush()
    return n


PHASE2_JOBS = {
    "access_daily": access_daily,
    "credential_alerts": credential_alerts,
    "access_minute": access_minute,
    "access_retention": access_retention,
}
