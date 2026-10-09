"""Phase 1 scheduled jobs (spec 1-dashboard §7 alerts, §4.1 month lock, §4.4 inspections,
P1-5 retention). Each alert is sent once per trigger, recorded in `job_marks`."""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.kpi_params import KpiQuery
from app.core.clock import now
from app.core.enums import (
    AuditAction,
    EntityType,
    NotificationKind,
    ProjectStatus,
    Role,
    UserStatus,
)
from app.core.hse_enums import (
    AttachmentOwner,
    CaStatus,
    IncidentStatus,
    InspectionStatus,
    InvestigationLevel,
    ObservationStatus,
    PeriodPreset,
    RiskRating,
)
from app.kpi import data as kdata
from app.kpi import scope as kscope
from app.kpi import warnings as kwarn
from app.kpi.engine import Engine, EngineConfig
from app.kpi.facts import Filter
from app.kpi.periods import Window, add_months, month_end, month_start
from app.models import (
    Attachment,
    CorrectiveAction,
    ExternalNotification,
    Incident,
    InjuryCase,
    Inspection,
    InspectionPlan,
    Investigation,
    JobMark,
    Observation,
    Project,
    User,
)
from app.services import audit, hse_settings, notify
from app.services import incidents as inc_svc
from app.services import inspections as ins_svc
from app.services import workforce as wf_svc
from app.services.followup import common as fu_common
from app.services.hse_common import contractor_reps, project_role_users, project_today
from app.services.permissions import Principal

MILESTONE_HOURS = (1_000_000, 2_000_000, 5_000_000, 10_000_000)
MILESTONE_DAYS = (100, 365)


def once(db: Session, key: str) -> bool:
    """True the first time a key is seen (idempotent alerts)."""
    if db.get(JobMark, key) is not None:
        return False
    db.add(JobMark(key=key, created_at=now()))
    db.flush()
    return True


def _projects(db: Session) -> list[Project]:
    return list(db.scalars(select(Project).where(Project.status != ProjectStatus.closed)))


def _officers(db: Session, pid: uuid.UUID) -> list[uuid.UUID]:
    return project_role_users(db, pid, Role.hse_officer)


def system_principal(db: Session) -> Principal:
    """An organisation-wide read principal for jobs that need a KPI scope."""
    user = db.scalar(select(User).where(User.status == UserStatus.active).limit(1))
    assert user is not None  # noqa: S101
    return Principal(
        user=user,
        session=None,
        today=date.today(),
        is_manager=True,
        projects={},
        employer_status=None,
        active_assignments=[],
    )


def project_scope(db: Session, project: Project, as_of: date) -> kscope.Scope:
    q = KpiQuery(
        project_ids=[project.id],
        all_projects=False,
        site_ids=[],
        zone_ids=[],
        zone_type=None,
        engagement_ids=[],
        include_subcontractors=True,
        tiers=[],
        period=PeriodPreset.month,
        anchor=as_of,
        start=None,
        end=None,
        as_of=as_of,
        compare=[],
    )
    return kscope.build(db, system_principal(db), q)


def _engine(db: Session, project: Project, as_of: date) -> Engine:
    s = hse_settings.get(db, project.id)
    facts = kdata.load(db, [project], {project.id: s})
    ps = project.settings
    config = EngineConfig(
        ps.ltifr_base_hours if ps else 1_000_000,
        ps.rate_base_hours if ps else 200_000,
        s.low_exposure_hours,
    )
    return Engine(facts, Filter(), as_of, config)


# ---- corrective actions --------------------------------------------------------------------------


def ca_alerts(db: Session, day: date | None = None) -> dict[str, Any]:
    """§7: due (3 days before, on the day), overdue daily (rep; officer ≥ 7 d; manager ≥ 30 d),
    pending verification reminder at 3 days."""
    due = overdue = pv = 0
    for project in _projects(db):
        d0 = day or project_today(project)
        cas = db.scalars(
            select(CorrectiveAction).where(
                CorrectiveAction.project_id == project.id,
                CorrectiveAction.status.in_(
                    [CaStatus.open, CaStatus.in_progress, CaStatus.pending_verification]
                ),
            )
        )
        for ca in cas:
            if ca.status in (CaStatus.open, CaStatus.in_progress):
                left = (ca.due_date - d0).days
                if left in (3, 0) and once(db, f"ca_due:{ca.id}:{ca.due_date}:{left}"):
                    notify.notify(
                        db,
                        [ca.owner_id],
                        NotificationKind.ca_due,
                        f"{ca.ref} is due {'today' if left == 0 else 'in 3 days'}",
                        f"{ca.ref} مستحق {'اليوم' if left == 0 else 'خلال 3 أيام'}",
                        entity_type=EntityType.corrective_action,
                        entity_id=ca.id,
                        project_id=project.id,
                    )
                    due += 1
                if left < 0 and once(db, f"ca_overdue:{ca.id}:{d0}"):
                    late = -left
                    who = {
                        ca.owner_id,
                        *contractor_reps(db, project.id, ca.responsible_engagement_id),
                    }
                    if late >= 7:
                        who |= set(_officers(db, project.id))
                    if late >= 30:
                        who |= set(notify.managers(db))
                    notify.notify(
                        db,
                        who,
                        NotificationKind.ca_overdue,
                        f"{ca.ref} is {late} day(s) overdue",
                        f"{ca.ref} متأخر {late} يوم",
                        entity_type=EntityType.corrective_action,
                        entity_id=ca.id,
                        project_id=project.id,
                    )
                    overdue += 1
            elif (
                ca.completed_date
                and (d0 - ca.completed_date).days >= 3
                and once(db, f"ca_pv:{ca.id}:{ca.completed_date}")
            ):
                notify.notify(
                    db,
                    [ca.verifier_id],
                    NotificationKind.ca_pending_verification,
                    f"Reminder: {ca.ref} awaits your verification",
                    f"تذكير: {ca.ref} بانتظار التحقق",
                    entity_type=EntityType.corrective_action,
                    entity_id=ca.id,
                    project_id=project.id,
                )
                pv += 1
    return {"due": due, "overdue": overdue, "verification_reminders": pv}


# ---- inspections ---------------------------------------------------------------------------------


def inspections_generate(db: Session, day: date | None = None) -> dict[str, Any]:
    n = 0
    for plan in db.scalars(select(InspectionPlan).where(InspectionPlan.active.is_(True))):
        project = db.get(Project, plan.project_id)
        if project is None or project.status == ProjectStatus.closed:
            continue
        n += ins_svc.generate(db, plan, day or project_today(project))
    return {"generated": n}


def inspections_missed(db: Session, day: date | None = None) -> dict[str, Any]:
    n = 0
    for project in _projects(db):
        rows = ins_svc.mark_missed(db, project, day or project_today(project))
        n += len(rows)
        if rows:
            notify.notify(
                db,
                _officers(db, project.id),
                NotificationKind.inspection_missed,
                f"{len(rows)} inspection(s) missed on {project.code}",
                f"فات موعد {len(rows)} تفتيش في {project.code}",
                project_id=project.id,
            )
    return {"missed": n}


def inspection_due_alerts(db: Session, day: date | None = None) -> dict[str, Any]:
    n = 0
    for project in _projects(db):
        d0 = day or project_today(project)
        for ins in db.scalars(
            select(Inspection).where(
                Inspection.project_id == project.id,
                Inspection.status == InspectionStatus.planned,
                Inspection.planned_date == d0,
            )
        ):
            who = [ins.assignee_user_id] if ins.assignee_user_id else []
            if not who and ins.assignee_role is not None:
                who = project_role_users(db, project.id, Role(ins.assignee_role.value))
            if who and once(db, f"inspection_due:{ins.id}"):
                notify.notify(
                    db,
                    who,
                    NotificationKind.inspection_due,
                    f"{ins.ref} ({ins.inspection_type.value}) is planned today",
                    f"{ins.ref} مخطط اليوم",
                    entity_type=EntityType.inspection,
                    entity_id=ins.id,
                    project_id=project.id,
                )
                n += 1
    return {"notified": n}


# ---- month lock ----------------------------------------------------------------------------------


def month_auto_lock(db: Session, day: date | None = None) -> dict[str, Any]:
    locked: list[str] = []
    approaching = 0
    for project in _projects(db):
        d0 = day or project_today(project)
        for m in wf_svc.month_lock_candidates(db, project, d0):
            wf_svc.lock_month(db, None, project, m, "automatic lock (month_lock_day)")
            locked.append(f"{project.code}:{m.strftime('%Y-%m')}")
        s = hse_settings.get(db, project.id)
        lock_day = d0.replace(day=min(s.month_lock_day, 28))
        prev = add_months(month_start(d0), -1)
        if (lock_day - d0).days == 3 and once(db, f"month_lock_approaching:{project.id}:{prev}"):
            who = set(_officers(db, project.id)) | set(
                project_role_users(db, project.id, Role.contractor_hse_rep)
            )
            notify.notify(
                db,
                who,
                NotificationKind.month_lock_approaching,
                f"{project.code} {prev.strftime('%Y-%m')} locks on {lock_day.isoformat()}",
                f"يُقفل شهر {prev.strftime('%Y-%m')} في {lock_day.isoformat()}",
                entity_type=EntityType.workforce_month,
                project_id=project.id,
            )
            approaching += 1
    return {"locked": locked, "approaching_notified": approaching}


# ---- incidents -----------------------------------------------------------------------------------


def incident_alerts(db: Session, at: datetime | None = None) -> dict[str, Any]:
    """Unclassified (24 h officers, 48 h manager), external notifications (24 h before due, at
    due, manager when overdue), investigation due (2 days before, at due, every 3 days overdue,
    manager at 7 days), L3 preliminary report missing (48 h), open LTI (every 7 days)."""
    t = at or now()
    counts = {
        "unclassified": 0,
        "notifications": 0,
        "investigations": 0,
        "preliminary": 0,
        "open_lti": 0,
    }
    for project in _projects(db):
        pid = project.id
        d0 = t.astimezone(inc_svc.tz_of(project)).date()
        officers = _officers(db, pid)
        incs = list(
            db.scalars(
                select(Incident).where(
                    Incident.project_id == pid,
                    Incident.status.not_in([IncidentStatus.draft, IncidentStatus.voided]),
                )
            )
        )
        ids = [i.id for i in incs]
        cases = inc_svc.load_cases(db, ids)
        invs = {
            v.incident_id: v
            for v in (
                db.scalars(select(Investigation).where(Investigation.incident_id.in_(ids)))
                if ids
                else []
            )
        }
        recorded: dict[uuid.UUID, set[str]] = {}
        if ids:
            for n in db.scalars(
                select(ExternalNotification).where(ExternalNotification.incident_id.in_(ids))
            ):
                recorded.setdefault(n.incident_id, set()).add(str(n.body))
        for i in incs:
            reps = contractor_reps(db, pid, i.responsible_engagement_id)
            # unclassified
            if i.status == IncidentStatus.reported and i.reported_at:
                age = t - i.reported_at
                for hours, who in ((24, officers), (48, notify.managers(db))):
                    if age >= timedelta(hours=hours) and once(db, f"unclassified:{i.id}:{hours}"):
                        notify.notify(
                            db,
                            who,
                            NotificationKind.incident_unclassified,
                            f"{i.ref} still not classified after {hours} h",
                            f"{i.ref} لم يُصنف بعد {hours} ساعة",
                            entity_type=EntityType.incident,
                            entity_id=i.id,
                            project_id=pid,
                        )
                        counts["unclassified"] += 1
            # external notifications (6f §7 alerts replace these under the rule profile)
            ext_req = (
                []
                if fu_common.under_profile(db, i)
                else inc_svc.required_notifications(i, cases.get(i.id, []))
            )
            for r in ext_req:
                if r.body.value in recorded.get(i.id, set()):
                    continue
                stages = [("pre", r.due_at - timedelta(hours=24)), ("due", r.due_at)]
                for stage, when in stages:
                    if t >= when and once(db, f"ext_notif:{i.id}:{r.body.value}:{stage}"):
                        ext_to: set[uuid.UUID] = set(officers) | set(reps)
                        if stage == "due":
                            ext_to |= set(notify.managers(db))
                        notify.notify(
                            db,
                            ext_to,
                            NotificationKind.external_notification_due,
                            f"{i.ref}: notify {r.body.value} "
                            + ("now (overdue)" if stage == "due" else "within 24 h"),
                            f"{i.ref}: إخطار {r.body.value}",
                            entity_type=EntityType.incident,
                            entity_id=i.id,
                            project_id=pid,
                        )
                        counts["notifications"] += 1
            v = invs.get(i.id)
            if v is not None and v.due_date:
                left = (v.due_date - d0).days
                active = v.submitted_at is None and i.status in (
                    IncidentStatus.reported,
                    IncidentStatus.under_investigation,
                )
                key = None
                if active and left in (2, 0):
                    key = f"inv_due:{i.id}:{v.due_date}:{left}"
                elif active and left < 0 and (-left) % 3 == 0:
                    key = f"inv_overdue:{i.id}:{d0}"
                if key and once(db, key):
                    inv_to: set[uuid.UUID] = set(officers)
                    if v.lead_investigator_id:
                        inv_to.add(v.lead_investigator_id)
                    if left <= -7:
                        inv_to |= set(notify.managers(db))
                    notify.notify(
                        db,
                        inv_to,
                        NotificationKind.investigation_due,
                        f"{i.ref}: investigation "
                        + (
                            f"due in {left} day(s)"
                            if left > 0
                            else "due today"
                            if left == 0
                            else f"{-left} day(s) overdue"
                        ),
                        f"{i.ref}: استحقاق التحقيق",
                        entity_type=EntityType.investigation,
                        entity_id=i.id,
                        project_id=pid,
                    )
                    counts["investigations"] += 1
                if (
                    v.level == InvestigationLevel.L3
                    and v.preliminary_report_at is None
                    and t >= i.occurred_at + timedelta(hours=48)
                    and once(db, f"prelim:{i.id}")
                ):
                    pre_to: set[uuid.UUID] = set(notify.managers(db))
                    if v.lead_investigator_id:
                        pre_to.add(v.lead_investigator_id)
                    notify.notify(
                        db,
                        pre_to,
                        NotificationKind.preliminary_report_missing,
                        f"{i.ref}: L3 preliminary report not filed within 48 h",
                        f"{i.ref}: لم يُقدَّم التقرير المبدئي خلال 48 ساعة",
                        entity_type=EntityType.investigation,
                        entity_id=i.id,
                        project_id=pid,
                    )
                    counts["preliminary"] += 1
            for c in cases.get(i.id, []):
                if not inc_svc.open_lti(c):
                    continue
                last = c.last_open_alert_on
                if last is None or (d0 - last).days >= 7:
                    c.last_open_alert_on = d0
                    notify.notify(
                        db,
                        officers,
                        NotificationKind.open_lti_case,
                        f"{i.ref}-P{c.person_no}: LTI still open (no return-to-work date)",
                        f"{i.ref}-P{c.person_no}: إصابة مضيعة للوقت لا تزال مفتوحة",
                        entity_type=EntityType.injury_case,
                        entity_id=c.id,
                        project_id=pid,
                    )
                    counts["open_lti"] += 1
    return counts


# ---- observations --------------------------------------------------------------------------------


def high_risk_observations(db: Session, at: datetime | None = None) -> dict[str, Any]:
    """O-2: high-risk unsafe, not closed on spot, no CA 24 h after submission."""
    t = at or now()
    n = 0
    for o in db.scalars(
        select(Observation).where(
            Observation.status == ObservationStatus.open,
            Observation.risk_rating == RiskRating.high,
            Observation.closed_on_spot.is_(False),
            Observation.no_ca_alert_sent.is_(False),
            Observation.created_at <= t - timedelta(hours=24),
        )
    ):
        who = set(_officers(db, o.project_id)) | set(
            contractor_reps(db, o.project_id, o.observed_engagement_id)
        )
        notify.notify(
            db,
            who,
            NotificationKind.high_risk_observation_without_ca,
            f"{o.ref}: high-risk observation has no corrective action after 24 h",
            f"{o.ref}: ملاحظة عالية الخطورة دون إجراء تصحيحي بعد 24 ساعة",
            entity_type=EntityType.observation,
            entity_id=o.id,
            project_id=o.project_id,
        )
        o.no_ca_alert_sent = True
        n += 1
    return {"alerted": n}


# ---- workforce data quality ----------------------------------------------------------------------


def daily_return_missing(db: Session, at: datetime | None = None) -> dict[str, Any]:
    """§7: at daily_return_deadline, yesterday's missing engagement-site returns → the
    engagement's Contractor HSE Rep; the HSE Officer after 2 consecutive missing days."""
    t = at or now()
    n = 0
    for project in _projects(db):
        local = t.astimezone(inc_svc.tz_of(project))
        s = hse_settings.get(db, project.id)
        if local.time() < s.daily_return_deadline:
            continue
        d = local.date() - timedelta(days=1)
        eng = _engine(db, project, d)
        missing = set(eng.missing_cells(Window(d - timedelta(days=1), d)))
        for eng_id, site_id, day in sorted(missing, key=lambda c: (str(c[0]), str(c[1]), c[2])):
            if day != d or not once(db, f"daily_return_missing:{eng_id}:{site_id}:{d}"):
                continue
            who = set(contractor_reps(db, project.id, eng_id))
            if (eng_id, site_id, d - timedelta(days=1)) in missing:
                who |= set(_officers(db, project.id))
            e = eng.facts.engagements.get(eng_id)
            code = e.code if e else "?"
            notify.notify(
                db,
                who,
                NotificationKind.daily_return_missing,
                f"{project.code}: daily return missing for {code} on {d.isoformat()}",
                f"{project.code}: البيان اليومي مفقود لـ {code} بتاريخ {d.isoformat()}",
                entity_type=EntityType.workforce_return,
                project_id=project.id,
            )
            n += 1
    return {"notified": n}


def completeness_check(db: Session, day: date | None = None) -> dict[str, Any]:
    """§7: on the 3rd day of the month, previous month completeness < threshold."""
    n = 0
    for project in _projects(db):
        d0 = day or project_today(project)
        if d0.day != 3:
            continue
        prev = add_months(month_start(d0), -1)
        eng = _engine(db, project, month_end(prev))
        expected, reported = eng.completeness(Window(prev, month_end(prev)))
        if not expected:
            continue
        pct = Decimal(reported) / Decimal(expected) * 100
        s = hse_settings.get(db, project.id)
        if pct < s.completeness_threshold_pct and once(db, f"completeness:{project.id}:{prev}"):
            notify.notify(
                db,
                set(_officers(db, project.id)) | set(notify.managers(db)),
                NotificationKind.data_completeness_low,
                f"{project.code} {prev.strftime('%Y-%m')}: data completeness {pct:.1f} %",
                f"{project.code} {prev.strftime('%Y-%m')}: اكتمال البيانات {pct:.1f} %",
                project_id=project.id,
            )
            n += 1
    return {"notified": n}


def leading_warnings(db: Session, day: date | None = None) -> dict[str, Any]:
    """§6.9 / §7: monthly on the 2nd day — E1-E4 for the previous month."""
    n = 0
    for project in _projects(db):
        d0 = day or project_today(project)
        if d0.day != 2:
            continue
        sc = project_scope(db, project, d0)
        prev = add_months(month_start(d0), -1)
        found = kwarn.evaluate(sc, [Window(prev, month_end(prev))])
        for w in found:
            eng_key = w.engagement.id if w.engagement else ""
            key = f"leading:{project.id}:{w.code}:{w.month_key}:{eng_key}"
            if not once(db, key):
                continue
            who = set(_officers(db, project.id)) | set(notify.managers(db))
            if w.engagement:
                who |= set(contractor_reps(db, project.id, w.engagement.id))
            notify.notify(
                db,
                who,
                NotificationKind.leading_warning,
                f"{project.code} {w.month_key}: {w.code} — {w.message_en}",
                f"{project.code} {w.month_key}: {w.code} — {w.message_ar}",
                project_id=project.id,
            )
            n += 1
    return {"warnings": n}


def lti_free_milestones(db: Session, day: date | None = None) -> dict[str, Any]:
    n = 0
    for project in _projects(db):
        d0 = day or project_today(project)
        lf = _engine(db, project, d0).lti_free()
        hits = [f"{h // 1_000_000}M h" for h in MILESTONE_HOURS if lf.man_hours >= h]
        hits += [f"{dd} days" for dd in MILESTONE_DAYS if lf.days >= dd]
        for label in hits:
            if once(db, f"lti_free:{project.id}:{lf.run_start}:{label}"):
                notify.notify(
                    db,
                    set(_officers(db, project.id)) | set(notify.managers(db)),
                    NotificationKind.lti_free_milestone,
                    f"{project.code}: {label} without a lost-time injury",
                    f"{project.code}: {label} دون إصابة مضيعة للوقت",
                    project_id=project.id,
                )
                n += 1
    return {"milestones": n}


# ---- retention (P1-5) ----------------------------------------------------------------------------


def anonymise_injury_identity(db: Session, at: datetime | None = None) -> dict[str, Any]:
    t = at or now()
    n = 0
    rows = db.execute(
        select(InjuryCase, Incident)
        .join(Incident, Incident.id == InjuryCase.incident_id)
        .where(Incident.status == IncidentStatus.closed, InjuryCase.anonymised_at.is_(None))
    ).all()
    for c, i in rows:
        years = hse_settings.get(db, i.project_id).injury_identity_retention_years
        if i.closed_at is None or i.closed_at.replace(year=i.closed_at.year + years) > t:
            continue
        c.person_name = "Anonymised / مجهّل"
        c.id_number_enc = None
        c.id_number_masked = None
        c.employee_no = None
        c.gosi_case_ref = None
        c.medical_notes = None
        c.anonymised_at = t
        for a in db.scalars(
            select(Attachment).where(
                Attachment.owner_type == AttachmentOwner.injury_case_medical,
                Attachment.owner_id == c.id,
            )
        ):
            db.delete(a)
        audit.record(
            db,
            AuditAction.update,
            audit.SYSTEM,
            entity_type=EntityType.injury_case,
            entity_id=c.id,
            project_id=i.project_id,
            details={"anonymised": True, "retention_years": years},
        )
        n += 1
    return {"anonymised": n}


PHASE1_JOBS = {
    "ca_alerts": ca_alerts,
    "inspections_generate": inspections_generate,
    "inspections_missed": inspections_missed,
    "inspection_due_alerts": inspection_due_alerts,
    "month_auto_lock": month_auto_lock,
    "incident_alerts": incident_alerts,
    "high_risk_observations": high_risk_observations,
    "daily_return_missing": daily_return_missing,
    "completeness_check": completeness_check,
    "leading_warnings": leading_warnings,
    "lti_free_milestones": lti_free_milestones,
    "anonymise_injury_identity": anonymise_injury_identity,
}
