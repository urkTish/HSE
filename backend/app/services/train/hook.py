"""Hook provider for kind `training_course` (spec 5-training §5.10a HK5-2…HK5-7, CC-7).

Called through `eligibility.phase4_hook_item` once the provider is registered on the project
(the hook policy state for kind training_course, HK5-1); the stage logic (transition → warn,
block, hard stops) is the shared Phase 4 mechanism."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import (
    HookProviderStatus,
    HookSubjectType,
    InductionResult,
    InductionStatus,
    InductionType,
    WorkerStatus,
)
from app.core.cert_enums import HookReasonCode
from app.core.train_enums import CourseCategory
from app.models import (
    InductionCourse,
    InductionRecord,
    TrainingCourse,
    TrainingProvider,
    TrainingRecord,
    Worker,
)
from app.services.access import common as acommon
from app.services.access.hooks import HookCheck, HookContext
from app.services.train import common
from app.services.train import validity as v

P = HookProviderStatus
R = HookReasonCode
IND_OK = (InductionStatus.valid, InductionStatus.expired, InductionStatus.superseded)


def providers(db: Session) -> dict[uuid.UUID, TrainingProvider]:
    cache: dict[uuid.UUID, TrainingProvider] | None = db.info.get("train_providers")
    if cache is None:
        cache = {p.id: p for p in db.scalars(select(TrainingProvider))}
        db.info["train_providers"] = cache
    return cache


def eval_ctx(db: Session, project_id: uuid.UUID | None) -> v.EvalCtx:
    s = common.settings(db, project_id) if project_id is not None else None
    return v.EvalCtx(courses=common.courses(db), settings=s, providers=providers(db))


def implemented(db: Session, code: str) -> bool:
    """HK5-2: the Phase 2/3 codes and every other active catalogue code."""
    c = common.course(db, code)
    return c is not None and c.active


def codes(db: Session) -> list[str]:
    from app.services.train import reference as ref  # noqa: PLC0415

    first = list(ref.HOOK_CODES_TODAY)
    rest = sorted(c.code for c in common.courses(db).values() if c.active and c.code not in first)
    return first + rest


def worker_records(db: Session, worker_id: uuid.UUID) -> list[TrainingRecord]:
    return list(db.scalars(select(TrainingRecord).where(TrainingRecord.worker_id == worker_id)))


def induction_valid(
    db: Session, worker_id: uuid.UUID, project_id: uuid.UUID | None, c: TrainingCourse, d: date
) -> InductionRecord | None:
    """CC-7: a Phase 2 induction record Valid at d of the course's type on the project
    (general_site: any active course of the type; zone_specific: the mapped course)."""
    if project_id is None or not c.induction_type:
        return None
    q = select(InductionRecord).where(
        InductionRecord.worker_id == worker_id,
        InductionRecord.project_id == project_id,
        InductionRecord.induction_type == InductionType(c.induction_type),
        InductionRecord.result == InductionResult.passed,
        InductionRecord.status.in_(IND_OK),
    )
    mapped = (c.induction_project_codes or {}).get(str(project_id))
    if mapped:
        q = q.join(InductionCourse, InductionCourse.id == InductionRecord.course_id).where(
            InductionCourse.code == mapped
        )
    best: InductionRecord | None = None
    for r in db.scalars(q):
        if r.valid_from is not None and r.valid_from > d:
            continue
        if r.valid_until is not None and d > r.valid_until:
            continue
        if best is None or (r.valid_until or date.max) > (best.valid_until or date.max):
            best = r
    return best


def check(
    db: Session,
    subject_type: HookSubjectType,
    subject_id: uuid.UUID,
    code: str,
    at: datetime,
    ctx: HookContext | None,
    project_id: uuid.UUID | None,
) -> HookCheck:
    """HK5-6. A subject that is not a worker → unknown_code; an appointment holder without a
    linked worker → not_met HOLDER_NOT_LINKED (no hard stop, HK5-7)."""
    if subject_type != HookSubjectType.worker:
        return HookCheck(P.unknown_code, reason_code=R.UNKNOWN_CODE.value)
    pid = (ctx.project_id if ctx else None) or project_id
    w = db.get(Worker, subject_id)
    if w is None:
        return HookCheck(P.not_met, reason_code=R.HOLDER_NOT_LINKED.value)
    c = common.course(db, code)
    if c is None or not c.active:
        return HookCheck(P.unknown_code, reason_code=R.UNKNOWN_CODE.value)
    if w.status == WorkerStatus.anonymised:
        return HookCheck(P.not_met, reason_code=R.TRAINING_MISSING.value)
    d = acommon.local_day(at)
    if c.category == CourseCategory.induction_link:
        ind = induction_valid(db, w.id, pid, c, d)
        if ind is None:
            return HookCheck(P.not_met, reason_code=R.INDUCTION_NOT_VALID.value)
        st = P.expiring if ind.valid_until and ind.valid_until <= d + timedelta(days=7) else P.met
        return HookCheck(st, valid_until=ind.valid_until, ref=ind.induction_no)
    b = v.best(worker_records(db, w.id), common.satisfiers(db, code), d, eval_ctx(db, pid), at)
    ref = b.record.record_no if b.record is not None else None
    if b.met:
        vu = b.valid_until
        st = P.expiring if vu is not None and vu <= d + timedelta(days=7) else P.met
        return HookCheck(st, valid_until=vu, ref=ref)
    return HookCheck(
        P.not_met,
        valid_until=b.valid_until,
        ref=ref,
        reason_code=(b.reason or R.TRAINING_MISSING).value,
        hard_stop=b.hard,
    )


def clear_cache(db: Session) -> None:
    db.info.pop("train_providers", None)
    common.clear_cache(db)
