"""Safety observations (spec 1-dashboard §3.6, §4.3, §5.3)."""

import uuid
from datetime import datetime

from pydantic import Field

from app.core.hse_enums import ObservationCategory, ObservationStatus, ObservationType, RiskRating
from app.schemas.common import Page, PatchInput, StrictInput, Timestamps
from app.schemas.hse_common import ApiWarning, EngagementRef, SiteRef, UserRef, ZoneRef
from app.schemas.incidents import LinkedCaSummary

NO_NAMES = "No names of observed workers (O-4); P3 hint applies."


class ObservationCreate(StrictInput):
    """Safe types → status closed; unsafe with closed_on_spot = true → closed; unsafe otherwise
    → open (§4.3). Unsafe requires risk_rating and immediate_action."""

    site_id: uuid.UUID
    zone_id: uuid.UUID | None = None
    observed_at: datetime = Field(description="UTC; ≤ now.")
    anonymous: bool = Field(
        default=False, description="Observer hidden from every role except HSE Manager (O-5)."
    )
    observed_engagement_id: uuid.UUID
    obs_type: ObservationType
    category: ObservationCategory
    risk_rating: RiskRating | None = Field(default=None, description="Required if unsafe.")
    description: str = Field(min_length=1, max_length=1000, description=NO_NAMES)
    stop_work_applied: bool = False
    immediate_action: str | None = Field(
        default=None, max_length=500, description="Required if unsafe."
    )
    closed_on_spot: bool | None = Field(default=None, description="Unsafe only.")


class ObservationUpdate(PatchInput):
    """Safe observations are immutable 24 h after submission (O-3 → 409
    SAFE_OBSERVATION_IMMUTABLE)."""

    non_nullable = frozenset({"obs_type", "category", "description", "stop_work_applied"})

    zone_id: uuid.UUID | None = None
    obs_type: ObservationType | None = None
    category: ObservationCategory | None = None
    risk_rating: RiskRating | None = None
    description: str | None = Field(default=None, min_length=1, max_length=1000)
    stop_work_applied: bool | None = None
    immediate_action: str | None = Field(default=None, max_length=500)


class ObservationRead(Timestamps):
    """`observer` is omitted (key absent) for anonymous observations unless the caller is the
    HSE Manager (capability 45)."""

    id: uuid.UUID
    ref: str = Field(examples=["OBS-ANIA-EXP-2026-00412"])
    project_id: uuid.UUID
    site: SiteRef
    zone: ZoneRef | None
    observed_at: datetime
    anonymous: bool
    observer: UserRef | None = None
    observed_engagement: EngagementRef
    obs_type: ObservationType
    category: ObservationCategory
    risk_rating: RiskRating | None
    description: str
    stop_work_applied: bool
    immediate_action: str | None
    closed_on_spot: bool | None
    status: ObservationStatus
    closure_comment: str | None
    closed_at: datetime | None
    ca_due_by: datetime | None = Field(
        description="High-risk unsafe, not closed on spot: CA expected within 24 h (O-2)."
    )
    corrective_actions: list[LinkedCaSummary]
    attachment_count: int
    warnings: list[ApiWarning] = Field(default_factory=list)


class ObservationPage(Page[ObservationRead]):
    pass


class ObservationCloseRequest(StrictInput):
    """open → closed (HSE Officer, Site Engineer, Contractor HSE Rep in scope)."""

    comment: str = Field(min_length=1, max_length=500)
