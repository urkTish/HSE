"""Dashboard action panel, expiring items and saved filters (spec 1-dashboard §8.1, D-2)."""

import uuid
from datetime import date, datetime

from pydantic import Field

from app.core.access_enums import LimitingFactor
from app.core.cert_enums import CertLimitingFactor
from app.core.enums import EntityType, ZoneType
from app.core.hse_enums import (
    ActionPanelItem,
    ComparisonKind,
    ExpiringItemKind,
    PeriodPreset,
    Severity,
)
from app.schemas.common import ApiModel, StrictInput
from app.schemas.hse_common import EngagementRef


class ListLink(ApiModel):
    """Where the count leads: call `path` with `query` to get exactly the counted records."""

    resource: str = Field(
        examples=["corrective_actions", "incidents", "inspections", "observations"]
    )
    path: str = Field(examples=["/api/v1/projects/{project_id}/corrective-actions"])
    query: dict[str, str | list[str]] = Field(examples=[{"overdue": "true"}])


class ActionPanelBreakdown(ApiModel):
    engagement: EngagementRef
    count: int


class ActionPanelEntry(ApiModel):
    key: ActionPanelItem
    label_en: str
    label_ar: str
    count: int
    severity: Severity
    link: ListLink | None = Field(description="Null when the items have no list (e.g. returns).")
    by_contractor: list[ActionPanelBreakdown]


class ActionPanelResponse(ApiModel):
    """§8.1 item 6. `overdue_cas.count` equals K-42 for the same filters (AC64)."""

    project_id: uuid.UUID
    as_of: date
    items: list[ActionPanelEntry]


class ExpiringItem(ApiModel):
    kind: ExpiringItemKind
    entity_type: EntityType
    entity_id: uuid.UUID | None
    ref: str | None
    title_en: str
    title_ar: str
    due_date: date
    days_left: int = Field(description="Negative = overdue.")
    engagement: EngagementRef | None
    detail_path: str | None
    limiting_factor: LimitingFactor | None = Field(
        default=None, description="Phase 2 credentials: the term giving the effective validity."
    )
    due_at: datetime | None = Field(
        default=None,
        description="Phase 3 timed kinds (ptw_valid_to, ptw_shift_end, gas_retest_due, "
        "fire_watch_end): the exact UTC time; due_date is its local date.",
    )
    minutes_left: int | None = Field(
        default=None, description="Phase 3 timed kinds: minutes until due_at (negative = past)."
    )
    cert_limiting_factor: CertLimitingFactor | None = Field(
        default=None,
        description="Phase 4 certificate kinds: the term giving valid_until (§6.1/§6.2).",
    )


class ExpiringItemsResponse(ApiModel):
    project_id: uuid.UUID
    as_of: date
    within_days: int
    items: list[ExpiringItem]


class DashboardFilters(StrictInput):
    """Saved dashboard filters per user (D-2). Same meaning as the /kpi query parameters."""

    project_id: uuid.UUID | None = None
    all_projects: bool = False
    site_ids: list[uuid.UUID] = Field(default_factory=list)
    zone_ids: list[uuid.UUID] = Field(default_factory=list)
    zone_type: ZoneType | None = None
    engagement_ids: list[uuid.UUID] = Field(default_factory=list)
    include_subcontractors: bool = True
    tiers: list[int] = Field(default_factory=list)
    period: PeriodPreset = PeriodPreset.month
    start: date | None = None
    end: date | None = None
    compare: list[ComparisonKind] = Field(default_factory=lambda: [ComparisonKind.previous])


class DashboardPreferencesRead(ApiModel):
    filters: DashboardFilters
