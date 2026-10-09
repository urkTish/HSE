"""Inspection plans and inspections (spec 1-dashboard §3.7, §4.4, §5.4)."""

import uuid
from datetime import date, datetime

from pydantic import Field, model_validator

from app.core.field_enums import ResponseResult, Rotation
from app.core.hse_enums import (
    FindingSeverity,
    InspectionAssigneeRole,
    InspectionFrequency,
    InspectionStatus,
    InspectionTimeliness,
    InspectionType,
    Weekday,
)
from app.schemas.actions import CaInline
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput, Timestamps
from app.schemas.hse_common import DecimalStr, EngagementRef, SiteRef, UserRef, ZoneRef


class InspectionPlanCreate(StrictInput):
    name_en: str = Field(min_length=1, max_length=150)
    name_ar: str = Field(min_length=1, max_length=150)
    inspection_type: InspectionType
    site_id: uuid.UUID
    zone_id: uuid.UUID | None = None
    engagement_id: uuid.UUID | None = None
    frequency: InspectionFrequency
    weekday: Weekday | None = Field(default=None, description="Required for weekly/fortnightly.")
    start_date: date
    end_date: date | None = None
    assignee_role: InspectionAssigneeRole
    assignee_user_id: uuid.UUID | None = None
    active: bool = True
    template_code: str | None = Field(
        default=None,
        max_length=8,
        description="v1.7 (6d §3.3): a Published inspection template of the same type; required "
        "from inspection_template_required_from (422 TEMPLATE_REQUIRED).",
    )
    rotation: Rotation = Field(default=Rotation.none, description="6d ISP-2.")
    rotation_list: list[uuid.UUID] = Field(
        default_factory=list, description="2–20 zones of the site or engagements on the site."
    )

    @model_validator(mode="after")
    def _rules(self) -> "InspectionPlanCreate":
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if self.frequency in (InspectionFrequency.weekly, InspectionFrequency.fortnightly) and (
            self.weekday is None
        ):
            raise ValueError("weekday is required for weekly/fortnightly plans")
        return self


class InspectionPlanUpdate(PatchInput):
    """Changes affect only future planned instances (N-1)."""

    non_nullable = frozenset({"name_en", "name_ar", "frequency", "assignee_role", "active"})

    name_en: str | None = Field(default=None, min_length=1, max_length=150)
    name_ar: str | None = Field(default=None, min_length=1, max_length=150)
    zone_id: uuid.UUID | None = None
    engagement_id: uuid.UUID | None = None
    frequency: InspectionFrequency | None = None
    weekday: Weekday | None = None
    end_date: date | None = None
    assignee_role: InspectionAssigneeRole | None = None
    assignee_user_id: uuid.UUID | None = None
    active: bool | None = None
    template_code: str | None = Field(default=None, max_length=8)
    rotation: Rotation | None = None
    rotation_list: list[uuid.UUID] | None = None


class InspectionPlanRead(Timestamps):
    id: uuid.UUID
    project_id: uuid.UUID
    name_en: str
    name_ar: str
    inspection_type: InspectionType
    site: SiteRef
    zone: ZoneRef | None
    engagement: EngagementRef | None
    frequency: InspectionFrequency
    weekday: Weekday | None
    start_date: date
    end_date: date | None
    assignee_role: InspectionAssigneeRole
    assignee: UserRef | None
    active: bool
    next_planned_date: date | None
    template_code: str | None = None
    rotation: Rotation = Rotation.none
    rotation_list: list[uuid.UUID] = Field(default_factory=list)
    without_checklist: bool = Field(
        default=False, description='6d ISP-1: "plan without checklist" after the switch date.'
    )


class InspectionPlanPage(Page[InspectionPlanRead]):
    pass


class FindingInput(StrictInput):
    """N-4: ca_required = true needs `ca_id` (existing CA) or `corrective_action` (created
    atomically with the inspection), else 422 FINDING_CA_REQUIRED."""

    description: str = Field(min_length=1, max_length=1000)
    severity: FindingSeverity
    ca_required: bool = False
    ca_id: uuid.UUID | None = None
    corrective_action: CaInline | None = None


class FindingRead(ApiModel):
    id: uuid.UUID
    description: str
    severity: FindingSeverity
    ca_required: bool
    ca_id: uuid.UUID | None
    ca_ref: str | None


class InspectionResults(StrictInput):
    completed_at: datetime = Field(description="UTC; ≤ now.")
    items_checked: int | None = Field(default=None, ge=0)
    items_compliant: int | None = Field(default=None, ge=0)
    findings: list[FindingInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def _rules(self) -> "InspectionResults":
        if (self.items_compliant or 0) > (self.items_checked or 0):
            raise ValueError("items_compliant must be ≤ items_checked")
        return self


class InspectionComplete(InspectionResults):
    """planned/missed → completed (assignee or capability 33 record). A Missed instance
    completed late stays 'late' for KPIs (N-2)."""


class UnplannedInspectionCreate(InspectionResults):
    """Ad-hoc inspection, created directly as completed (counts in K-35b only, N-5)."""

    inspection_type: InspectionType
    site_id: uuid.UUID
    zone_id: uuid.UUID | None = None
    engagement_id: uuid.UUID | None = None


class InspectionCancel(StrictInput):
    """planned/missed → cancelled (HSE Officer/Manager; after Missed HSE Manager only, N-3)."""

    reason: str = Field(min_length=1, max_length=500)


class InspectionRead(Timestamps):
    id: uuid.UUID
    ref: str = Field(examples=["INS-ANIA-EXP-2026-00321"])
    project_id: uuid.UUID
    plan_id: uuid.UUID | None
    plan_name_en: str | None
    plan_name_ar: str | None
    inspection_type: InspectionType
    site: SiteRef
    zone: ZoneRef | None
    engagement: EngagementRef | None
    assignee_role: InspectionAssigneeRole | None
    assignee: UserRef | None
    planned_date: date | None
    due_by: date | None = Field(description="planned_date + inspection_grace_days.")
    completed_at: datetime | None
    inspector: UserRef | None
    items_checked: int | None
    items_compliant: int | None
    score_pct: DecimalStr | None = Field(description="compliant ÷ checked × 100, 1 dp.")
    findings: list[FindingRead]
    status: InspectionStatus
    timeliness: InspectionTimeliness = Field(description="Derived (N-2).")
    cancel_reason: str | None
    response_id: uuid.UUID | None = Field(default=None, description="6d checklist response.")
    result: ResponseResult | None = Field(default=None, description="6d FND-6 pass / fail.")
    offline_delay_min: int | None = None
    recorded_offline: bool = Field(default=False, description='6d EXE-7 "recorded offline".')
    void_reason: str | None = None


class InspectionPage(Page[InspectionRead]):
    pass
