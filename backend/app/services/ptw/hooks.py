"""Phase 2 / Phase 0 events → PTW re-evaluation (3-ptw PT-8, rule 28).

Credential events and contractor status changes mark workers / engagements on the session;
``process`` (called by the request transaction before commit) refreshes the Approved and live
permits concerned, so a suspension or revocation acts on the permit in the same request. The
minute job recomputes every live permit as a backstop (≤ 1 min) for changes made elsewhere.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ptw_enums import PERMIT_LIVE, PermitStatus

WORKERS = "ptw_dirty_workers"
ENGS = "ptw_dirty_engagements"


def mark_workers(db: Session, ids: Iterable[uuid.UUID | None]) -> None:
    db.info.setdefault(WORKERS, set()).update(x for x in ids if x is not None)


def mark_engagements(db: Session, ids: Iterable[uuid.UUID]) -> None:
    db.info.setdefault(ENGS, set()).update(ids)


def process(db: Session) -> int:
    workers: set[uuid.UUID] = db.info.pop(WORKERS, set())
    engs: set[uuid.UUID] = db.info.pop(ENGS, set())
    if not workers and not engs:
        return 0
    from app.models import Permit, PermitCrew  # noqa: PLC0415
    from app.services.permissions import engagement_descendants  # noqa: PLC0415
    from app.services.ptw import evaluation  # noqa: PLC0415

    statuses = [*PERMIT_LIVE, PermitStatus.approved]
    ids: set[uuid.UUID] = set()
    if workers:
        ids |= set(
            db.scalars(
                select(PermitCrew.permit_id)
                .join(Permit, Permit.id == PermitCrew.permit_id)
                .where(PermitCrew.worker_id.in_(workers), Permit.status.in_(statuses))
            )
        )
        ids |= set(
            db.scalars(
                select(Permit.id).where(
                    Permit.supervisor_worker_id.in_(workers), Permit.status.in_(statuses)
                )
            )
        )
    if engs:
        tree: set[uuid.UUID] = set()
        for e in engs:
            tree |= engagement_descendants(db, e)
        ids |= set(
            db.scalars(
                select(Permit.id).where(Permit.engagement_id.in_(tree), Permit.status.in_(statuses))
            )
        )
    n = 0
    for pid in sorted(ids, key=str):
        permit = db.get(Permit, pid)
        if permit is not None and evaluation.refresh(db, permit, run_simops=False) is not None:
            n += 1
    db.flush()
    return n
