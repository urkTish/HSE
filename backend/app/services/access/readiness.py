"""Read-only access services for later phases (spec 2-access-permits HK-6, ZP-3, §8.5).

Phase 3 (PTW) calls these; Phase 2 never reads PTW data. Signatures are final; the bodies are
implemented in stage 2.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.core.access_enums import EligibilityContext
from app.schemas.inductions import EligibilityResult


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
    raise NotImplementedError


def worker_cleared_for_zone_now(db: Session, worker_id: uuid.UUID, zone_id: uuid.UUID) -> bool:
    """Convenience for Phase 3: eligible now (ptw context)."""
    raise NotImplementedError


def active_waps(
    db: Session, zone_id: uuid.UUID, engagement_id: uuid.UUID | None, at: datetime
) -> list[ActiveWap]:
    """Active WAPs covering the zone at `at` (optionally for one engagement and its ancestors)."""
    raise NotImplementedError
