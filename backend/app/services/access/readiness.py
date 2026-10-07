"""Read-only access services for later phases (spec 2-access-permits HK-6, ZP-3, §8.5).

Phase 3 (PTW) calls these; Phase 2 never reads PTW data. Signatures are final.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.core.access_enums import EligibilityContext
from app.models import NotamRequest, ObstacleClearance
from app.schemas.inductions import EligibilityResult
from app.services.access import eligibility, waps, windows
from app.services.hse_common import Refs


@dataclass(frozen=True)
class ActiveWap:
    wap_id: uuid.UUID
    wap_no: str
    engagement_id: uuid.UUID
    zone_ids: tuple[uuid.UUID, ...]
    valid_from: date
    valid_to: date
    in_window: bool
    linked_ntm_nos: tuple[str, ...]
    linked_obs_nos: tuple[str, ...]


def access_eligibility(
    db: Session,
    worker_id: uuid.UUID,
    zone_id: uuid.UUID,
    at: datetime,
    context: EligibilityContext = EligibilityContext.ptw,
) -> EligibilityResult:
    """E(worker, zone, at, context) per ZP-3/ZP-4 (context ptw skips the WAP step)."""
    ev = eligibility.eligibility(db, worker_id, zone_id, at, context)
    if ev is None:
        raise LookupError("worker or zone not found")
    return eligibility.to_result(db, ev, names=False, refs=Refs(db))


def worker_cleared_for_zone_now(db: Session, worker_id: uuid.UUID, zone_id: uuid.UUID) -> bool:
    """Convenience for Phase 3: eligible now (ptw context)."""
    ev = eligibility.eligibility(db, worker_id, zone_id, None, EligibilityContext.ptw)
    return ev is not None and ev.eligible


def active_waps(
    db: Session, zone_id: uuid.UUID, engagement_id: uuid.UUID | None, at: datetime
) -> list[ActiveWap]:
    """Active WAPs covering the zone at `at` (optionally for one engagement and its ancestors)."""
    out = []
    for w in waps.active_at(db, zone_id, engagement_id, at):
        ntms = [n.ntm_no for n in (db.get(NotamRequest, i) for i in w.linked_ntm_ids or []) if n]
        obs = [
            o.obs_no for o in (db.get(ObstacleClearance, i) for i in w.linked_obs_ids or []) if o
        ]
        inst = windows.current(windows.parse(w.windows), w.valid_from, w.valid_to, at)
        out.append(
            ActiveWap(
                wap_id=w.id,
                wap_no=w.wap_no,
                engagement_id=w.engagement_id,
                zone_ids=tuple(w.zone_ids or []),
                valid_from=w.valid_from,
                valid_to=w.valid_to,
                in_window=inst is not None,
                linked_ntm_nos=tuple(ntms),
                linked_obs_nos=tuple(obs),
            )
        )
    return out
