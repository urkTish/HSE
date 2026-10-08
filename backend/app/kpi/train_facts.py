"""Training KPI facts (spec 5-training §6.4, §6.8, §6.9): register hours per attendance day
(TH-1…TH-3, TH-9), assessments of closed sessions (K-87), failed verifications and voided
sessions (E13), and requirement evaluations per (project, date) computed on demand (K-82…K-85,
K-88). Loaded once per cached KPI Facts; the requirement evaluations need a session, so every
request works on a copy bound to its own session (`with_db`)."""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import HookKind, WorkerPersonType
from app.core.cert_enums import VerificationStatus
from app.core.train_enums import (
    AttendanceResult,
    SessionStatus,
    TrainingRecordStatus,
    TrainingVerificationOutcome,
)
from app.models import (
    Deployment,
    HookPolicyState,
    TrainingNomination,
    TrainingRecord,
    TrainingSession,
    TrainingSettings,
    TrainingVerification,
    Worker,
)
from app.services.access import common as acommon

UUID = uuid.UUID
SIXTY = Decimal(60)
FAILING = (
    TrainingVerificationOutcome.not_found,
    TrainingVerificationOutcome.details_differ,
    TrainingVerificationOutcome.revoked_by_provider,
)


@dataclass(frozen=True, slots=True)
class HourFact:
    """Person-hours of one attendee on one session day, or of one sponsored external record."""

    project: UUID
    d: date
    eng: UUID | None
    sites: frozenset[UUID]
    course: str
    category: str
    provider: UUID
    source: str  # session | external_certificate
    hours: Decimal
    staff: bool  # client_pmc_staff (K-86 second figure; never K-37)
    voided: date | None = None  # local date the session was voided (TH-9)


@dataclass(frozen=True, slots=True)
class AssessFact:
    """K-87: a passed / failed contractor_worker attendance of a closed session."""

    project: UUID
    d: date  # closed_at local date
    eng: UUID | None
    sites: frozenset[UUID]
    course: str
    category: str
    provider: UUID
    passed: bool
    voided: date | None = None


@dataclass(frozen=True, slots=True)
class FailFact:
    """E13: a failed verification (performed_at local date) or a voided session."""

    project: UUID
    d: date
    engs: frozenset[UUID]
    kind: str  # verification | void


@dataclass
class TrainFacts:
    pids: list[UUID]
    hours: list[HourFact] = field(default_factory=list)
    assess: list[AssessFact] = field(default_factory=list)
    fails: list[FailFact] = field(default_factory=list)
    open_sessions: list[tuple[UUID, date]] = field(default_factory=list)  # Delivered, not closed
    settings: dict[UUID, TrainingSettings] = field(default_factory=dict)
    hook_states: dict[UUID, HookPolicyState] = field(default_factory=dict)
    courses: dict[str, Any] = field(default_factory=dict)
    pe_cache: dict[tuple[UUID, date], Any] = field(default_factory=dict)
    base_cache: dict[UUID, Any] = field(default_factory=dict)
    db: Session | None = None

    def with_db(self, db: Session) -> TrainFacts:
        out = copy.copy(self)  # caches shared with the original
        out.db = db
        return out

    def peval(self, pid: UUID, d: date) -> Any:
        """The requirement evaluation of a project at local date d (cached)."""
        from app.services.train import requirements as treq  # noqa: PLC0415

        key = (pid, d)
        pe = self.pe_cache.get(key)
        if pe is None:
            assert self.db is not None  # noqa: S101
            base = self.base_cache.get(pid)
            if base is None:
                base = self.base_cache[pid] = treq.load_base(self.db, pid)
            pe = treq.evaluate_project(self.db, pid, d, bookings=True, base=base)
            self.pe_cache[key] = pe
        return pe


def load_train(db: Session, pids: list[UUID], shared: Any = None) -> TrainFacts:
    from app.services.train import common as tcommon  # noqa: PLC0415

    tf = TrainFacts(pids=list(pids), db=db)
    courses = tcommon.courses(db)
    tf.courses = dict(courses)
    for ts in db.scalars(select(TrainingSettings).where(TrainingSettings.project_id.in_(pids))):
        tf.settings[ts.project_id] = ts
    for st in db.scalars(
        select(HookPolicyState).where(
            HookPolicyState.project_id.in_(pids), HookPolicyState.kind == HookKind.training_course
        )
    ):
        tf.hook_states[st.project_id] = st

    def cat(code: str) -> str:
        c = courses.get(code)
        return c.category.value if c is not None else "other"

    staff: dict[UUID, bool] = {}
    dep_sites: dict[UUID, frozenset[UUID]] = {}
    rows = db.execute(
        select(TrainingNomination, TrainingSession, Worker.person_type, Deployment.site_ids)
        .join(TrainingSession, TrainingSession.id == TrainingNomination.session_id)
        .join(Worker, Worker.id == TrainingNomination.worker_id)
        .outerjoin(Deployment, Deployment.id == TrainingNomination.deployment_id)
        .where(
            TrainingSession.project_id.in_(pids),
            TrainingSession.status.in_([SessionStatus.closed, SessionStatus.voided]),
        )
    ).all()
    void_engs: dict[UUID, set[UUID]] = {}
    for n, s, ptype, sites in rows:
        if s.closed_at is None:
            continue
        is_staff = ptype == WorkerPersonType.client_pmc_staff
        if ptype == WorkerPersonType.visitor:
            continue
        staff[n.worker_id] = is_staff
        sset = frozenset(sites or [])
        if n.deployment_id is not None:
            dep_sites[n.deployment_id] = sset
        voided = acommon.local_day(s.voided_at) if s.voided_at is not None else None
        if voided is not None and n.engagement_id is not None:
            void_engs.setdefault(s.id, set()).add(n.engagement_id)
        for i, day in enumerate(s.days or []):
            m = int((n.minutes_by_day or {}).get(str(i + 1), 0))
            if m <= 0:
                continue
            tf.hours.append(
                HourFact(
                    project=s.project_id,
                    d=date.fromisoformat(day["date"]),
                    eng=n.engagement_id,
                    sites=sset,
                    course=s.course_code,
                    category=cat(s.course_code),
                    provider=s.provider_id,
                    source="session",
                    hours=Decimal(m) / SIXTY,
                    staff=is_staff,
                    voided=voided,
                )
            )
        if (
            n.contractor_worker
            and not is_staff
            and n.result
            in (
                AttendanceResult.passed,
                AttendanceResult.failed,
            )
        ):
            tf.assess.append(
                AssessFact(
                    project=s.project_id,
                    d=acommon.local_day(s.closed_at),
                    eng=n.engagement_id,
                    sites=sset,
                    course=s.course_code,
                    category=cat(s.course_code),
                    provider=s.provider_id,
                    passed=n.result == AttendanceResult.passed,
                    voided=voided,
                )
            )
    for s in db.scalars(
        select(TrainingSession).where(
            TrainingSession.project_id.in_(pids), TrainingSession.voided_at.is_not(None)
        )
    ):
        assert s.voided_at is not None  # noqa: S101
        tf.fails.append(
            FailFact(
                s.project_id,
                acommon.local_day(s.voided_at),
                frozenset(void_engs.get(s.id, set())),
                "void",
            )
        )
    for s in db.scalars(
        select(TrainingSession).where(
            TrainingSession.project_id.in_(pids),
            TrainingSession.status == SessionStatus.delivered,
        )
    ):
        tf.open_sessions.append((s.project_id, s.last_day))
    # TH-3 sponsored external records (Accepted / Superseded / Expired, verified)
    for r, ptype, w_sites in db.execute(
        select(TrainingRecord, Worker.person_type, Deployment.site_ids)
        .join(Worker, Worker.id == TrainingRecord.worker_id)
        .outerjoin(
            Deployment,
            (Deployment.worker_id == TrainingRecord.worker_id)
            & (Deployment.project_id == TrainingRecord.sponsoring_project_id),
        )
        .where(
            TrainingRecord.sponsoring_project_id.in_(pids),
            TrainingRecord.project_sponsored.is_(True),
            TrainingRecord.status.in_(
                [
                    TrainingRecordStatus.accepted,
                    TrainingRecordStatus.superseded,
                    TrainingRecordStatus.expired,
                ]
            ),
            TrainingRecord.verification_status == VerificationStatus.verified,
            TrainingRecord.historic.is_(False),
        )
    ).all():
        if ptype != WorkerPersonType.contractor_worker or r.hours is None:
            continue
        assert r.sponsoring_project_id is not None  # noqa: S101
        tf.hours.append(
            HourFact(
                project=r.sponsoring_project_id,
                d=r.completed_on,
                eng=r.engagement_id,
                sites=frozenset(w_sites or []),
                course=r.course_code,
                category=cat(r.course_code),
                provider=r.provider_id,
                source="external_certificate",
                hours=Decimal(r.hours),
                staff=False,
            )
        )
    # E13 failed verifications
    for v, r in db.execute(
        select(TrainingVerification, TrainingRecord)
        .join(TrainingRecord, TrainingRecord.id == TrainingVerification.record_id)
        .where(
            TrainingVerification.project_id.in_(pids),
            TrainingVerification.outcome.in_(list(FAILING)),
        )
    ):
        assert v.project_id is not None  # noqa: S101
        tf.fails.append(
            FailFact(
                v.project_id,
                acommon.local_day(v.performed_at),
                frozenset({r.engagement_id} if r.engagement_id else set()),
                "verification",
            )
        )
    tf.hours.sort(key=lambda h: h.d)
    return tf
