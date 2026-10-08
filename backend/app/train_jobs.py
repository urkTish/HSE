"""Phase 5 scheduled jobs (5-training §4, §7).

`training_daily` (00:06:00, after Phase 4 `cert_daily`): training record expiry (publishes
`training.record_changed`, HK5-8), trainer authorisation expiry (TA Active → Expired; Scheduled
sessions flagged to HSE Officers), scan retention (P5-8).
`training_alerts` (07:00): the long schedule 30/14/7/0 for training records that satisfy a
requirement of a Mobilised deployment (30/14 suppressed when `booked_in_time`, GP-5), trainer
authorisation expiry, provider accreditation expiry (PV-8), session reminders (1 day before),
session close due (SS-8: last day + 1, the deadline, daily while overdue) and verification due.
The hook block-date reminders for kind training_course are sent by Phase 4 `cert_alerts`
(shared hook policy state); E12/E13 by Phase 1 `leading_warnings` (monthly, day 2).
`training_minute` (every 60 s): session status from the clock (Scheduled → In Progress →
Delivered) and import batch expiry (IM5-1).

Alert texts carry worker_no, course, record / session numbers and dates only (P5-4, P5-6).
Every step is de-duplicated per (subject, step) through JobMark.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cert_enums import VerificationStatus
from app.core.clock import now
from app.core.enums import EntityType, NotificationKind
from app.core.train_enums import (
    RefresherPlanState,
    RequirementState,
    SessionStatus,
    TrainerAuthorisationStatus,
    TrainingProviderStatus,
    TrainingRecordStatus,
)
from app.models import (
    Project,
    TrainerAuthorisation,
    TrainingProvider,
    TrainingProviderAccreditation,
    TrainingRecord,
    TrainingSession,
    Worker,
)
from app.services.access import common as acommon
from app.services.cert import alerts

NK = NotificationKind
LONG = (30, 14, 7, 0)


def _sched(db: Session, project_id: Any) -> list[int]:
    from app.services.train import common  # noqa: PLC0415

    return list(common.settings(db, project_id).alert_schedule_long_days or LONG)


# ---- 00:06:00 ---------------------------------------------------------------------------------


def _ta_expiry(db: Session, d: date) -> int:
    from app.services.train import trainers  # noqa: PLC0415

    n = 0
    for ta in db.scalars(
        select(TrainerAuthorisation).where(
            TrainerAuthorisation.status == TrainerAuthorisationStatus.active,
            TrainerAuthorisation.valid_to < d,
        )
    ):
        ta.status = TrainerAuthorisationStatus.expired
        ta.status_reason = "valid_to passed"
        n += 1
        trainers.flag_sessions(db, ta)
    db.flush()
    return n


def training_daily(db: Session, at: datetime | None = None) -> dict[str, Any]:
    from app.services.train import records  # noqa: PLC0415

    at = at or now()
    d = acommon.local_day(at)
    out = {
        "training_records_expired": records.expiry_job(db, d),
        "trainer_authorisations_expired": _ta_expiry(db, d),
        "training_scans_deleted": records.scan_retention_job(db, d),
    }
    db.flush()
    return out


# ---- 07:00 ------------------------------------------------------------------------------------


def _record_expiry(db: Session, d: date) -> int:
    from app.services.train import gaps  # noqa: PLC0415
    from app.services.train import requirements as reqs  # noqa: PLC0415

    n = 0
    for pid in db.scalars(select(Project.id)):
        sched = _sched(db, pid)
        pe = reqs.evaluate_project(db, pid, d, bookings=True, enforcement=True)
        seen: set[Any] = set()
        for r in pe.reqs:
            rec = r.record
            if (
                rec is None
                or r.valid_until is None
                or r.state
                not in (
                    RequirementState.met,
                    RequirementState.expiring,
                )
            ):
                continue
            if (rec.id, r.dep.engagement_id) in seen:
                continue
            seen.add((rec.id, r.dep.engagement_id))
            left = (r.valid_until - d).days
            if left < 0 or left > max(sched):
                continue
            in_time = gaps.plan_state(r) == RefresherPlanState.booked_in_time
            steps = [t for t in sched if not (in_time and t > 7)]
            step = alerts.long_step(
                db, f"trr-exp:{rec.id}:{r.dep.id}", r.valid_until, d, steps or [0]
            )
            if step is None:
                continue
            w = db.get(Worker, rec.worker_id)
            users = alerts.reps(db, pid, r.dep.engagement_id) if r.dep.engagement_id else set()
            if step <= 7 or not users:  # client / PMC staff: no engagement rep → HSE Officers
                users |= alerts.officers(db, pid)
            if step == 0 and r.critical:
                users |= alerts.managers(db)
            alerts.send(
                db, users, NK.training_record_expiry,
                f"{w.worker_no if w else ''}: {rec.course_code} {rec.record_no} valid until "
                f"{r.valid_until} ({step} days)",
                f"{w.worker_no if w else ''}: {rec.course_code} {rec.record_no} ساري حتى "
                f"{r.valid_until} ({step} يوم)",
                EntityType.training_record, rec.id, pid, email=True,
            )  # fmt: skip
            n += 1
    return n


def _ta_alerts(db: Session, d: date) -> int:
    n = 0
    for ta in db.scalars(
        select(TrainerAuthorisation).where(
            TrainerAuthorisation.status == TrainerAuthorisationStatus.active,
            TrainerAuthorisation.valid_to >= d,
            TrainerAuthorisation.valid_to <= d + timedelta(days=30),
        )
    ):
        step = alerts.long_step(db, f"ta-exp:{ta.id}", ta.valid_to, d, LONG)
        if step is None:
            continue
        users = alerts.officers(db, ta.project_id) | {ta.authorised_by_user_id}
        if ta.trainer_user_id is not None:
            users.add(ta.trainer_user_id)
        alerts.send(
            db, users, NK.trainer_authorisation_expiry,
            f"Trainer authorisation {ta.authorisation_no} valid until {ta.valid_to} ({step} days)",
            f"تفويض المدرب {ta.authorisation_no} ساري حتى {ta.valid_to} ({step} يوم)",
            EntityType.trainer_authorisation, ta.id, ta.project_id, email=True,
        )  # fmt: skip
        n += 1
    return n


def _accreditation_expiry(db: Session, d: date) -> int:
    """PV-8: 30 / 14 / 7 / 0 days before an accreditation's valid_until."""
    n = 0
    hse = alerts.managers(db)
    for a, pv in db.execute(
        select(TrainingProviderAccreditation, TrainingProvider)
        .join(TrainingProvider, TrainingProvider.id == TrainingProviderAccreditation.provider_id)
        .where(
            TrainingProvider.status.in_(
                [TrainingProviderStatus.approved, TrainingProviderStatus.suspended]
            ),
            TrainingProviderAccreditation.valid_until >= d,
            TrainingProviderAccreditation.valid_until <= d + timedelta(days=30),
        )
    ).all():
        step = alerts.long_step(db, f"tacc-exp:{a.id}", a.valid_until, d, LONG)
        if step is None:
            continue
        users = set(hse)
        for pid in db.scalars(select(Project.id)):
            users |= alerts.officers(db, pid)
        alerts.send(
            db, users, NK.training_provider_accreditation_expiry,
            f"{pv.provider_code}: accreditation {a.accreditation_no} valid until {a.valid_until} "
            f"({step} days)",
            f"{pv.provider_code}: الاعتماد {a.accreditation_no} ساري حتى {a.valid_until} "
            f"({step} يوم)",
            EntityType.training_provider_accreditation, a.id, None, email=True,
        )  # fmt: skip
        n += 1
    return n


def _session_alerts(db: Session, d: date) -> int:
    from app.services.train import sessions  # noqa: PLC0415

    n = 0
    for s in db.scalars(
        select(TrainingSession).where(TrainingSession.status == SessionStatus.scheduled)
    ):
        if s.first_day != d + timedelta(days=1) or not alerts.once(db, f"trs-rem:{s.id}:{d}"):
            continue
        users = set(sessions.trainer_user_ids(db, s))
        for nom in sessions.nominations(db, s, live=True):
            users |= alerts.reps(db, s.project_id, nom.engagement_id)
        alerts.send(
            db, users, NK.training_session_reminder,
            f"Training session {s.session_no} ({s.course_code}) starts {s.first_day}",
            f"تبدأ الجلسة التدريبية {s.session_no} ({s.course_code}) في {s.first_day}",
            EntityType.training_session, s.id, s.project_id,
        )  # fmt: skip
        n += 1
    for s in db.scalars(
        select(TrainingSession).where(TrainingSession.status == SessionStatus.delivered)
    ):
        due = sessions._close_due(db, s)
        overdue = due is not None and d > due
        if not (d == s.last_day + timedelta(days=1) or d == due or overdue):
            continue
        if not alerts.once(db, f"trs-close:{s.id}:{d}"):
            continue
        users = alerts.officers(db, s.project_id)
        if overdue:
            users |= alerts.managers(db)
        alerts.send(
            db, users, NK.training_session_close_due,
            f"Training session {s.session_no} delivered {s.last_day}: close by {due}"
            + (" (overdue)" if overdue else ""),
            f"الجلسة التدريبية {s.session_no} منفذة {s.last_day}: الإغلاق قبل {due}"
            + (" (متأخر)" if overdue else ""),
            EntityType.training_session, s.id, s.project_id, email=True,
        )  # fmt: skip
        n += 1
    return n


def _verification_due(db: Session, d: date) -> int:
    n = 0
    for r in db.scalars(
        select(TrainingRecord).where(
            TrainingRecord.status.in_(
                [TrainingRecordStatus.submitted, TrainingRecordStatus.accepted]
            ),
            TrainingRecord.verification_status.in_(
                [VerificationStatus.not_verified, VerificationStatus.unable_to_verify]
            ),
            TrainingRecord.verification_due_on.is_not(None),
            TrainingRecord.verification_due_on <= d + timedelta(days=1),
        )
    ):
        assert r.verification_due_on is not None  # noqa: S101
        if r.project_id is None or not alerts.once(db, f"trv-due:{r.id}:{d}"):
            continue
        overdue = d > r.verification_due_on
        users = alerts.officers(db, r.project_id)
        if overdue:
            users |= alerts.managers(db)
        alerts.send(
            db, users, NK.training_verification_due,
            f"Training record {r.record_no} ({r.course_code}): verification due "
            f"{r.verification_due_on}" + (" (overdue)" if overdue else ""),
            f"السجل التدريبي {r.record_no} ({r.course_code}): التحقق مستحق "
            f"{r.verification_due_on}" + (" (متأخر)" if overdue else ""),
            EntityType.training_record, r.id, r.project_id, email=True,
        )  # fmt: skip
        n += 1
    return n


def training_alerts(db: Session, at: datetime | None = None) -> dict[str, Any]:
    at = at or now()
    d = acommon.local_day(at)
    out = {
        "record_expiry": _record_expiry(db, d),
        "trainer_authorisation_expiry": _ta_alerts(db, d),
        "accreditation_expiry": _accreditation_expiry(db, d),
        "sessions": _session_alerts(db, d),
        "verification_due": _verification_due(db, d),
    }
    db.flush()
    return out


# ---- every 60 s -------------------------------------------------------------------------------


def training_minute(db: Session, at: datetime | None = None) -> dict[str, Any]:
    from app.services.train import imports, sessions  # noqa: PLC0415

    at = at or now()
    moved = 0
    for s in db.scalars(
        select(TrainingSession).where(
            TrainingSession.status.in_([SessionStatus.scheduled, SessionStatus.in_progress])
        )
    ):
        if sessions.advance(db, s, at):
            moved += 1
    out = {"sessions_advanced": moved, "imports_expired": imports.expiry_job(db, at)}
    db.flush()
    return out


PHASE5_JOBS = {
    "training_daily": training_daily,
    "training_alerts": training_alerts,
    "training_minute": training_minute,
}
