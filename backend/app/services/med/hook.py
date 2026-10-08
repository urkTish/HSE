"""Hook provider for kind `medical_fitness` (spec 6a-occupational-health HK6-2…HK6-7).

Called through `eligibility.phase4_hook_item` once the provider is registered on the project
(the hook policy state for kind medical_fitness, HK6-1); the stage logic (transition → warn,
block, hard stops) is the shared Phase 4 mechanism."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.access_enums import HookProviderStatus, HookSubjectType
from app.core.cert_enums import HookReasonCode
from app.services.access.hooks import HookCheck, HookContext
from app.services.med import common, engine

P = HookProviderStatus


def implemented(db: Session, code: str) -> bool:
    """HK6-2: the catalogue codes (any other code → unknown_code)."""
    return common.code(db, code) is not None


def codes(db: Session) -> list[str]:
    from app.services.med import reference as ref  # noqa: PLC0415

    first = [c for c in ref.CODES if c in common.codes(db)]
    return first + sorted(c for c in common.codes(db) if c not in first)


def facts(db: Session, worker_id: uuid.UUID) -> engine.WorkerFacts:
    cache: dict[uuid.UUID, engine.WorkerFacts] = db.info.setdefault("med_wf", {})
    wf = cache.get(worker_id)
    if wf is None:
        wf = engine.load_one(db, worker_id)
        cache[worker_id] = wf
    return wf


def result(db: Session, worker_id: uuid.UUID, code: str, at: datetime,
           project_id: uuid.UUID | None) -> engine.Check:  # fmt: skip
    return engine.check(engine.ctx_for(db, project_id), facts(db, worker_id), code, at)


def check(
    db: Session,
    subject_type: HookSubjectType,
    subject_id: uuid.UUID,
    code: str,
    at: datetime,
    ctx: HookContext | None,
    project_id: uuid.UUID | None,
) -> HookCheck:
    if subject_type != HookSubjectType.worker:
        return HookCheck(P.unknown_code, reason_code=HookReasonCode.UNKNOWN_CODE.value)
    pid = (ctx.project_id if ctx else None) or project_id
    r = result(db, subject_id, code, at, pid)
    return HookCheck(
        r.status,
        valid_until=r.valid_until,
        ref=r.ref,
        reason_code=r.reason.value if r.reason else None,
        hard_stop=r.hard_stop,
        conditions=r.conditions,
    )
