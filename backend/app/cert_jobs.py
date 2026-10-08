"""Phase 4 scheduled jobs (4-third-party-cert §4, §7).

`cert_daily` (00:05:45): certificate expiry (EC-13, PC-10), scaffold tag expiry (SF-5), overdue B
defects (DF-4), contractor-blacklisted demobilisation (EM-6) and the ban-review reminder (BL-4).
`cert_alerts` (07:00): the long-schedule expiry alerts 30/14/7/0 (equipment lines, personnel
certificates, TPI accreditations and client approvals), verification-due reminders, B-defect due
reminders 7/3/0, hook block date approaching (7 and 1 day before) and the weekly PC-12 reminder.
`cert_minute` (every minute): import batch expiry (IM-5), review reminders at 24 h and arrival
inspection reminders (EM-3).
`cert_switch` (00:00:30): the warn → block switch of every project and kind (HK4-4).

Alert texts carry tags / worker_no / cert numbers only (P4-4). Every step is de-duplicated per
(subject, step) through JobMark, so re-running a job never sends twice.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import DeploymentStatus
from app.core.cert_enums import (
    CertificateStatus,
    ClientApprovalStatus,
    DefectCategory,
    DefectStatus,
    EquipmentDeploymentStatus,
    HookStage,
    TpiStatus,
    VerificationStatus,
)
from app.core.clock import now
from app.core.enums import EntityType, NotificationKind
from app.models import (
    Deployment,
    EquipmentCertificate,
    EquipmentCertLine,
    EquipmentDefect,
    EquipmentDeployment,
    EquipmentItem,
    HookPolicyState,
    PersonnelCertificate,
    Tpi,
    TpiAccreditation,
    TpiClientApproval,
    Worker,
)
from app.services.access import common as acommon
from app.services.cert import alerts
from app.services.cert import common as cc
from app.services.cert import settings as cset

CS = CertificateStatus
NK = NotificationKind
LONG = (30, 14, 7, 0)
CERT_MODELS: list[tuple[Any, EntityType]] = [
    (EquipmentCertificate, EntityType.equipment_certificate),
    (PersonnelCertificate, EntityType.personnel_certificate),
]


def _sched(db: Session, project_id: Any) -> list[int]:
    s = cset.get(db, project_id)
    return list(s.alert_schedule_long_days or LONG)


# ---- 00:05:45 ----


def cert_daily(db: Session, at: datetime | None = None) -> dict[str, Any]:
    from app.services.cert import (  # noqa: PLC0415
        bans,
        defects,
        deployments,
        equipment_certs,
        personnel,
        scaffolds,
    )

    at = at or now()
    out = {
        "equipment_certs_expired": equipment_certs.expiry_job(db, at),
        "personnel_certs_expired": personnel.expiry_job(db, at),
        "scaffold_tags_expired": scaffolds.tag_expiry_job(db, at),
        "b_defects_overdue": defects.overdue_job(db, at),
        "contractor_blacklist_demobilised": deployments.blacklisted_contractor_job(db),
        "ban_reviews_due": bans.review_job(db, acommon.local_day(at)),
    }
    db.flush()
    return out


# ---- 07:00 ----


def _equipment_expiry(db: Session, d: date) -> int:
    n = 0
    rows = db.execute(
        select(EquipmentCertLine, EquipmentCertificate, EquipmentItem)
        .join(EquipmentCertificate, EquipmentCertificate.id == EquipmentCertLine.certificate_id)
        .join(EquipmentItem, EquipmentItem.id == EquipmentCertLine.equipment_id)
        .where(
            EquipmentCertificate.status == CS.accepted,
            EquipmentCertLine.superseded_by_line_id.is_(None),
            EquipmentCertLine.valid_until.is_not(None),
            EquipmentCertLine.valid_until >= d,
            EquipmentCertLine.valid_until <= d + timedelta(days=30),
        )
    ).all()
    for ln, c, item in rows:
        dep = cc.latest_deployment_on(db, item.id, c.project_id)
        if dep is None or dep.status != EquipmentDeploymentStatus.on_site:
            continue
        step = alerts.long_step(db, f"eq-exp:{ln.id}", ln.valid_until, d, _sched(db, c.project_id))
        if step is None:
            continue
        users = alerts.reps(db, c.project_id, dep.engagement_id)
        if step <= 7:
            users |= alerts.officers(db, c.project_id)
        if step == 0:
            from app.services.cert.validity import category_critical  # noqa: PLC0415

            if category_critical(cset.get(db, c.project_id), item.category):
                users |= alerts.managers(db)
        alerts.send(
            db, users, NK.equipment_cert_expiry,
            f"{dep.tag}: certificate {c.cert_no} valid until {ln.valid_until} ({step} days)",
            f"{dep.tag}: الشهادة {c.cert_no} سارية حتى {ln.valid_until} ({step} يوم)",
            EntityType.equipment_certificate, c.id, c.project_id, email=True,
        )  # fmt: skip
        n += 1
    return n


def _personnel_expiry(db: Session, d: date) -> int:
    n = 0
    for pc in db.scalars(
        select(PersonnelCertificate).where(
            PersonnelCertificate.status == CS.accepted,
            PersonnelCertificate.valid_until.is_not(None),
            PersonnelCertificate.valid_until >= d,
            PersonnelCertificate.valid_until <= d + timedelta(days=30),
        )
    ):
        deps = list(
            db.scalars(
                select(Deployment).where(
                    Deployment.worker_id == pc.worker_id,
                    Deployment.status == DeploymentStatus.mobilised,
                )
            )
        )
        if not deps:
            continue
        step = alerts.long_step(db, f"pc-exp:{pc.id}", pc.valid_until, d, _sched(db, pc.project_id))
        if step is None:
            continue
        w = db.get(Worker, pc.worker_id)
        users: set[Any] = set()
        for dep in deps:
            users |= alerts.reps(db, dep.project_id, dep.engagement_id)
            if step <= 7:
                users |= alerts.officers(db, dep.project_id)
        alerts.send(
            db, users, NK.personnel_cert_expiry,
            f"{w.worker_no if w else ''}: {pc.cert_type} {pc.cert_no} valid until "
            f"{pc.valid_until} ({step} days)",
            f"{w.worker_no if w else ''}: {pc.cert_type} {pc.cert_no} سارية حتى "
            f"{pc.valid_until} ({step} يوم)",
            EntityType.personnel_certificate, pc.id, pc.project_id, email=True,
        )  # fmt: skip
        n += 1
    return n


def _accreditation_expiry(db: Session, d: date) -> int:
    n = 0
    hse = alerts.managers(db)
    for a, t in db.execute(
        select(TpiAccreditation, Tpi)
        .join(Tpi, Tpi.id == TpiAccreditation.tpi_id)
        .where(
            Tpi.status.in_([TpiStatus.approved, TpiStatus.suspended]),
            TpiAccreditation.valid_until >= d,
            TpiAccreditation.valid_until <= d + timedelta(days=30),
        )
    ).all():
        step = alerts.long_step(db, f"acc-exp:{a.id}", a.valid_until, d, LONG)
        if step is None:
            continue
        from app.models import Project  # noqa: PLC0415

        users = set(hse)
        for pid in db.scalars(select(Project.id)):
            users |= alerts.officers(db, pid)
        alerts.send(
            db, users, NK.tpi_accreditation_expiry,
            f"{t.tpi_code}: accreditation {a.accreditation_no} valid until {a.valid_until} "
            f"({step} days)",
            f"{t.tpi_code}: الاعتماد {a.accreditation_no} ساري حتى {a.valid_until} ({step} يوم)",
            EntityType.tpi_accreditation, a.id, None, email=True,
        )  # fmt: skip
        n += 1
    return n


def _client_approval_expiry(db: Session, d: date) -> int:
    n = 0
    for ap, t in db.execute(
        select(TpiClientApproval, Tpi)
        .join(Tpi, Tpi.id == TpiClientApproval.tpi_id)
        .where(
            TpiClientApproval.status == ClientApprovalStatus.active,
            TpiClientApproval.valid_until >= d,
            TpiClientApproval.valid_until <= d + timedelta(days=30),
        )
    ).all():
        step = alerts.long_step(db, f"ca-exp:{ap.id}", ap.valid_until, d, LONG)
        if step is None:
            continue
        alerts.send(
            db, alerts.officers(db, ap.project_id) | alerts.managers(db),
            NK.tpi_client_approval_expiry,
            f"{t.tpi_code}: client approval {ap.approval_ref} valid until {ap.valid_until} "
            f"({step} days)",
            f"{t.tpi_code}: موافقة العميل {ap.approval_ref} سارية حتى {ap.valid_until} "
            f"({step} يوم)",
            EntityType.tpi_client_approval, ap.id, ap.project_id, email=True,
        )  # fmt: skip
        n += 1
    return n


def _verification_due(db: Session, d: date) -> int:
    n = 0
    for model, et in CERT_MODELS:
        for c in db.scalars(
            select(model).where(
                model.status.in_([CS.submitted, CS.accepted]),
                model.verification_status == VerificationStatus.not_verified,
                model.verification_due_on.is_not(None),
                model.verification_due_on <= d + timedelta(days=1),
            )
        ):
            due = c.verification_due_on
            if not alerts.once(db, f"ver-due:{c.id}:{d.isoformat()}"):
                continue
            users = alerts.officers(db, c.project_id)
            if due < d:
                users |= alerts.managers(db)
                en, ar = "overdue", "متأخر"
            elif due == d:
                en, ar = "due today", "مستحق اليوم"
            else:
                en, ar = "due tomorrow", "مستحق غداً"
            alerts.send(
                db, users, NK.verification_due,
                f"Verification of {c.cert_no} {en} ({due})",
                f"التحقق من {c.cert_no} {ar} ({due})",
                et, c.id, c.project_id, email=True,
            )  # fmt: skip
            n += 1
    return n


def _defect_due(db: Session, d: date) -> int:
    n = 0
    for x in db.scalars(
        select(EquipmentDefect).where(
            EquipmentDefect.category == DefectCategory.B,
            EquipmentDefect.status.in_([DefectStatus.open, DefectStatus.rectified]),
            EquipmentDefect.due_date >= d,
            EquipmentDefect.due_date <= d + timedelta(days=7),
        )
    ):
        step = alerts.long_step(db, f"def-due:{x.id}", x.due_date, d, (7, 3, 0))
        if step is None:
            continue
        users = alerts.reps(db, x.project_id, x.engagement_id)
        if step == 0:
            users |= alerts.officers(db, x.project_id)
        alerts.send(
            db, users, NK.defect_rectification_due,
            f"Defect {x.defect_no}: rectification due {x.due_date} ({step} days)",
            f"العيب {x.defect_no}: موعد الإصلاح {x.due_date} ({step} يوم)",
            EntityType.equipment_defect, x.id, x.project_id, email=True,
        )  # fmt: skip
        n += 1
    return n


def _hook_block(db: Session, d: date) -> int:
    n = 0
    for st in db.scalars(select(HookPolicyState).where(HookPolicyState.stage != HookStage.block)):
        for scope_, when in (
            ("critical", st.critical_block_from),
            ("general", st.general_block_from),
        ):
            left = (when - d).days
            if left not in (7, 1):
                continue
            if not alerts.once(db, f"hook-block:{st.id}:{scope_}:{when}:{left}"):
                continue
            users = alerts.officers(db, st.project_id) | alerts.managers(db)
            users |= alerts.reps(db, st.project_id, None)
            alerts.send(
                db, users, NK.hook_block_approaching,
                f"{st.kind.value}: {scope_} codes block from {when} ({left} days)",
                f"{st.kind.value}: تُحظر الرموز ({scope_}) اعتباراً من {when} (بعد {left} يوم)",
                EntityType.hook_policy_state, st.id, st.project_id, email=True,
            )  # fmt: skip
            n += 1
    return n


def _trade_missing(db: Session, d: date) -> int:
    """PC-12 weekly reminder (Sunday)."""
    if d.weekday() != 6:
        return 0
    from app.services.cert import personnel  # noqa: PLC0415

    n = 0
    for dep in db.scalars(
        select(Deployment).where(Deployment.status == DeploymentStatus.mobilised)
    ):
        code = personnel.trade_requirement(db, dep.project_id, dep.worker_id)
        if not code:
            continue
        if any(
            pc.cert_type == code
            for pc in db.scalars(
                select(PersonnelCertificate).where(
                    PersonnelCertificate.worker_id == dep.worker_id,
                    PersonnelCertificate.status == CS.accepted,
                    PersonnelCertificate.valid_until >= d,
                )
            )
        ):
            continue
        if not alerts.once(db, f"trade-missing:{dep.id}:{d.isoformat()}"):
            continue
        w = db.get(Worker, dep.worker_id)
        alerts.send(
            db, alerts.reps(db, dep.project_id, dep.engagement_id), NK.trade_cert_missing,
            f"{w.worker_no if w else ''}: {code} certificate missing for trade {dep.trade.value}",
            f"{w.worker_no if w else ''}: شهادة {code} مفقودة للمهنة {dep.trade.value}",
            EntityType.worker, dep.worker_id, dep.project_id,
        )  # fmt: skip
        n += 1
    return n


def cert_alerts(db: Session, at: datetime | None = None) -> dict[str, Any]:
    at = at or now()
    d = acommon.local_day(at)
    out = {
        "equipment_expiry": _equipment_expiry(db, d),
        "personnel_expiry": _personnel_expiry(db, d),
        "accreditation_expiry": _accreditation_expiry(db, d),
        "client_approval_expiry": _client_approval_expiry(db, d),
        "verification_due": _verification_due(db, d),
        "defect_due": _defect_due(db, d),
        "hook_block": _hook_block(db, d),
        "trade_missing": _trade_missing(db, d),
    }
    db.flush()
    return out


# ---- every minute ----


def _review_reminders(db: Session, at: datetime) -> int:
    n = 0
    for model, et in CERT_MODELS:
        for c in db.scalars(
            select(model).where(
                model.status == CS.submitted,
                model.submitted_at.is_not(None),
                model.submitted_at <= at - timedelta(hours=24),
            )
        ):
            if not alerts.once(db, f"review-24h:{c.id}:{c.submitted_at.isoformat()}"):
                continue
            alerts.send(
                db, alerts.officers(db, c.project_id), NK.certificate_review_reminder,
                f"Certificate {c.cert_no} awaiting review for more than 24 h",
                f"الشهادة {c.cert_no} بانتظار المراجعة منذ أكثر من 24 ساعة",
                et, c.id, c.project_id,
            )  # fmt: skip
            n += 1
    return n


def _arrival_due(db: Session, at: datetime) -> int:
    n = 0
    for dep in db.scalars(
        select(EquipmentDeployment).where(
            EquipmentDeployment.status == EquipmentDeploymentStatus.on_site,
            EquipmentDeployment.arrived_at.is_not(None),
            EquipmentDeployment.arrival_inspection_passed.is_(False),
        )
    ):
        if dep.arrival_inspection:
            continue
        hours = cset.get(db, dep.project_id).arrival_inspection_hours
        assert dep.arrived_at is not None  # noqa: S101
        deadline: datetime = dep.arrived_at + timedelta(hours=hours)
        for key, when in (("warn", deadline - timedelta(hours=4)), ("due", deadline)):
            if at < when or not alerts.once(db, f"arrival:{dep.id}:{key}"):
                continue
            alerts.send(
                db,
                alerts.reps(db, dep.project_id, dep.engagement_id)
                | alerts.site_engineers(db, dep.project_id),
                NK.arrival_inspection_due,
                f"{dep.tag}: arrival inspection due by {acommon.local(deadline):%Y-%m-%d %H:%M}",
                f"{dep.tag}: فحص الوصول مستحق قبل {acommon.local(deadline):%Y-%m-%d %H:%M}",
                EntityType.equipment_deployment,
                dep.id,
                dep.project_id,
            )
            n += 1
    return n


def cert_minute(db: Session, at: datetime | None = None) -> dict[str, Any]:
    from app.services.cert import imports  # noqa: PLC0415

    at = at or now()
    out = {
        "imports_expired": imports.expiry_job(db, at),
        "review_reminders": _review_reminders(db, at),
        "arrival_reminders": _arrival_due(db, at),
    }
    db.flush()
    return out


def cert_switch(db: Session, at: datetime | None = None) -> dict[str, Any]:
    from app.services.cert import policy  # noqa: PLC0415

    return dict(policy.switch_due(db, at))


PHASE4_JOBS = {
    "cert_daily": cert_daily,
    "cert_alerts": cert_alerts,
    "cert_minute": cert_minute,
    "cert_switch": cert_switch,
}
