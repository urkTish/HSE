"""Phase 6a scheduled jobs (6a-occupational-health §4, §7).

`medical_daily` (00:06:30, after `training_daily`): provider licence expiry → Suspended
`licence_expired` (MP-5), examiner licence expiry → Expired (§4.2), import batch expiry, and a
`medical.fitness_changed` event for every worker whose fitness line ended yesterday so that the
gates and permits re-evaluate (HK6-8).
`medical_alerts` (07:03): the long schedule 30 / 14 / 7 / 0 for fitness lines that satisfy a
counted requirement of a Mobilised deployment, restriction / temporarily-unfit reviews (14 / 0),
licence expiry (MP-5, EX-5) and referrals still overdue (daily while overdue).
`medical_minute` (every 60 s): referral reminder at due_at − 2 h and the overdue alert at due_at
(OH Practitioners; HSE Officers; HSE Manager from due + 24 h).

Alert texts carry worker_no, code, reference and dates only (P6-7). Every step is de-duplicated
per (subject, step) through JobMark, so re-running a job never sends twice.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import EntityType, NotificationKind
from app.core.med_enums import (
    ExaminerStatus,
    FitnessLineState,
    MedicalImportStatus,
    MedicalProviderStatus,
    ReferralStatus,
)
from app.models import (
    FitnessLine,
    FitnessReferral,
    MedicalExaminer,
    MedicalImportBatch,
    MedicalProvider,
    Project,
)
from app.services.cert.alerts import long_step, once

NK = NotificationKind
LONG = (30, 14, 7, 0)
REVIEW = (14, 0)


# ---- 00:06:30 -----------------------------------------------------------------------------------


def medical_daily(db: Session, at: datetime | None = None) -> dict[str, Any]:
    from app.services.cert import events  # noqa: PLC0415
    from app.services.med import common, imports, providers  # noqa: PLC0415

    at = at or now()
    d = common.local_day(at)
    suspended = 0
    for pv in db.scalars(
        select(MedicalProvider).where(
            MedicalProvider.status == MedicalProviderStatus.approved,
            MedicalProvider.licence_valid_until < d,
        )
    ):
        providers.suspend(db, pv, None, "licence_expired", d)
        providers.alert_status(db, pv)
        suspended += 1
    expired = 0
    for x in db.scalars(
        select(MedicalExaminer).where(
            MedicalExaminer.status == ExaminerStatus.active,
            MedicalExaminer.licence_valid_until < d,
        )
    ):
        x.status = ExaminerStatus.expired
        x.status_reason = "licence_valid_until passed"
        expired += 1
    batches = 0
    for b in db.scalars(
        select(MedicalImportBatch).where(
            MedicalImportBatch.status.in_(
                [MedicalImportStatus.uploaded, MedicalImportStatus.validated]
            ),
            MedicalImportBatch.expires_at < at,
        )
    ):
        imports._expire(db, b)
        batches += 1
    ended = sorted(
        set(
            db.scalars(
                select(FitnessLine.worker_id).where(
                    FitnessLine.line_state == FitnessLineState.governing,
                    FitnessLine.valid_until == d - timedelta(days=1),
                )
            )
        )
    )
    if suspended or ended:
        common.clear_cache(db)
    if ended:
        events.publish(db, "medical.fitness_changed", worker_ids=ended)
    db.flush()
    return {
        "providers_suspended": suspended,
        "examiners_expired": expired,
        "imports_expired": batches,
        "workers_line_ended": len(ended),
    }


# ---- 07:00 --------------------------------------------------------------------------------------


def _line_expiry(db: Session, d: date) -> int:
    from app.services.med import alerts, common  # noqa: PLC0415
    from app.services.med import requirements as rq  # noqa: PLC0415

    n = 0
    for pid in db.scalars(select(Project.id)):
        s = common.settings(db, pid)
        if s.medical_register_from is None:
            continue
        pe = rq.evaluate_project(db, pid, d)
        seen: set[Any] = set()
        for r in pe.reqs:
            chk = r.check
            if not r.counted or chk is None or not chk.ok or chk.row is None:
                continue
            vu = chk.valid_until
            key = (chk.row.line.id, r.dep.id)
            if vu is None or key in seen or not 0 <= (vu - d).days <= max(LONG):
                continue
            seen.add(key)
            step = long_step(db, f"mfx:{chk.row.line.id}:{r.dep.id}", vu, d, LONG)
            if step is None:
                continue
            users = alerts.reps(db, pid, r.dep.engagement_id)
            if step in (30, 7):
                users |= alerts.oh(db, pid)
            if step == 0:
                users |= alerts.officers(db, pid)
                if r.critical:
                    users |= alerts.managers(db)
            wno = alerts.wno(db, r.dep.worker_id)
            alerts.send(
                db, users, NK.fitness_expiry,
                f"Fitness certificate due: {wno} {r.code} valid until {vu} ({step} days)",
                f"شهادة لياقة مستحقة: {wno} {r.code} سارية حتى {vu} ({step} يوم)",
                pid, EntityType.worker, r.dep.worker_id,
            )  # fmt: skip
            n += 1
    return n


def _reviews(db: Session, d: date) -> int:
    from app.models import FitnessAssessment  # noqa: PLC0415
    from app.services.med import alerts, common  # noqa: PLC0415

    n = 0
    end = d + timedelta(days=max(REVIEW))
    rows = db.execute(
        select(FitnessLine, FitnessAssessment)
        .join(FitnessAssessment, FitnessAssessment.id == FitnessLine.assessment_id)
        .where(FitnessLine.line_state == FitnessLineState.governing)
    ).all()
    for ln, a in rows:
        for kind, rd in (("rr", ln.restriction_review_date), ("ur", ln.unfit_review_date)):
            if rd is None or not d <= rd <= end:
                continue
            step = long_step(db, f"mrv:{kind}:{ln.id}", rd, d, REVIEW)
            if step is None:
                continue
            dep = common.deployment(db, ln.worker_id, a.project_id)
            users = alerts.oh(db, a.project_id)
            if dep is not None:
                users |= alerts.reps(db, a.project_id, dep.engagement_id)
            wno = alerts.wno(db, ln.worker_id)
            alerts.send(
                db, users, NK.fitness_review_due,
                f"Fitness review due: {wno} {ln.code} on {rd} ({a.assessment_no})",
                f"مراجعة لياقة مستحقة: {wno} {ln.code} في {rd} ({a.assessment_no})",
                a.project_id, EntityType.fitness_assessment, a.id,
            )  # fmt: skip
            n += 1
    return n


def _licences(db: Session, d: date) -> int:
    from app.services.med import alerts  # noqa: PLC0415

    pids = list(db.scalars(select(Project.id)))
    end = d + timedelta(days=max(LONG))
    n = 0
    subjects: list[tuple[str, Any, date, str, EntityType]] = []
    for pv in db.scalars(
        select(MedicalProvider).where(
            MedicalProvider.status.in_(
                [MedicalProviderStatus.approved, MedicalProviderStatus.suspended]
            ),
            MedicalProvider.licence_valid_until >= d,
            MedicalProvider.licence_valid_until <= end,
        )
    ):
        subjects.append(
            ("mpl", pv.id, pv.licence_valid_until, pv.provider_code, EntityType.medical_provider)
        )
    for x in db.scalars(
        select(MedicalExaminer).where(
            MedicalExaminer.status == ExaminerStatus.active,
            MedicalExaminer.licence_valid_until >= d,
            MedicalExaminer.licence_valid_until <= end,
        )
    ):
        subjects.append(
            ("mxl", x.id, x.licence_valid_until, x.examiner_no, EntityType.medical_examiner)
        )
    for prefix, sid, until, label, et in subjects:
        step = long_step(db, f"{prefix}:{sid}", until, d, LONG)
        if step is None:
            continue
        users = set(alerts.managers(db))
        for pid in pids:
            users |= alerts.oh(db, pid) | alerts.officers(db, pid)
        alerts.send(
            db, users, NK.medical_licence_expiry,
            f"{label}: licence valid until {until} ({step} days)",
            f"{label}: الترخيص ساري حتى {until} ({step} يوم)",
            None, et, sid,
        )  # fmt: skip
        n += 1
    return n


def _overdue(db: Session, r: FitnessReferral, at: datetime, tag: str) -> bool:
    from app.services.med import alerts  # noqa: PLC0415

    if not once(db, f"mrf:{r.id}:{tag}"):
        return False
    users = alerts.oh(db, r.project_id) | alerts.officers(db, r.project_id)
    if at >= r.due_at + timedelta(hours=24):
        users |= alerts.managers(db)
    wno = alerts.wno(db, r.worker_id)
    alerts.send(
        db, users, NK.fitness_referral_overdue,
        f"Referral overdue: {r.referral_no} ({wno}), due {r.due_at:%Y-%m-%d %H:%M}",
        f"إحالة متأخرة: {r.referral_no} ({wno})",
        r.project_id, EntityType.fitness_referral, r.id,
    )  # fmt: skip
    return True


def medical_alerts(db: Session, at: datetime | None = None) -> dict[str, Any]:
    from app.services.med import common  # noqa: PLC0415

    at = at or now()
    d = common.local_day(at)
    late = 0
    for r in db.scalars(
        select(FitnessReferral).where(
            FitnessReferral.status == ReferralStatus.open, FitnessReferral.due_at < at
        )
    ):
        late += int(_overdue(db, r, at, f"day:{d.isoformat()}"))
    out = {
        "fitness_expiry": _line_expiry(db, d),
        "reviews": _reviews(db, d),
        "licences": _licences(db, d),
        "referrals_overdue": late,
    }
    db.flush()
    return out


# ---- every 60 s ---------------------------------------------------------------------------------


def medical_minute(db: Session, at: datetime | None = None) -> dict[str, Any]:
    from app.services.med import alerts  # noqa: PLC0415

    at = at or now()
    reminded = overdue = 0
    for r in db.scalars(
        select(FitnessReferral).where(
            FitnessReferral.status == ReferralStatus.open,
            FitnessReferral.due_at <= at + timedelta(hours=2),
        )
    ):
        if r.due_at <= at:
            overdue += int(_overdue(db, r, at, "due"))
            if at >= r.due_at + timedelta(hours=24) and once(db, f"mrf:{r.id}:due+24h"):
                alerts.send(
                    db, alerts.managers(db), NK.fitness_referral_overdue,
                    f"Referral overdue 24 h: {r.referral_no} ({alerts.wno(db, r.worker_id)})",
                    f"إحالة متأخرة 24 ساعة: {r.referral_no} ({alerts.wno(db, r.worker_id)})",
                    r.project_id, EntityType.fitness_referral, r.id,
                )  # fmt: skip
        elif once(db, f"mrf:{r.id}:due-2h"):
            alerts.send(
                db, alerts.oh(db, r.project_id), NK.fitness_referral_raised,
                f"Referral {r.referral_no} is due at {r.due_at:%Y-%m-%d %H:%M}",
                f"الإحالة {r.referral_no} مستحقة قريباً",
                r.project_id, EntityType.fitness_referral, r.id, email=False,
            )  # fmt: skip
            reminded += 1
    db.flush()
    return {"referral_reminders": reminded, "referrals_overdue": overdue}


PHASE6A_JOBS = {
    "medical_daily": medical_daily,
    "medical_alerts": medical_alerts,
    "medical_minute": medical_minute,
}
