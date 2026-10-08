"""Scaffold register, tags and inspections (spec 4-third-party-cert §3.8, §4.6, §6.4,
SF-1…SF-7)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.core.cert_enums import (
    ChecklistItemResult,
    ReinspectionReason,
    ScaffoldChecklistItem,
    ScaffoldInspectionResult,
    ScaffoldInspectionType,
    ScaffoldStatus,
    ScaffoldTagStatus,
    ScaffoldType,
)
from app.schemas.access_common import WorkerRef
from app.schemas.cert_common import P4_HINT, TAG_PATTERN, Metres2, ScaffoldRef
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput
from app.schemas.hse_common import ApiWarning, DecimalStr, EngagementRef, UserRef, ZoneRef
from app.schemas.inductions import EligibilityItem


class ScaffoldFields(StrictInput):
    engagement_id: uuid.UUID
    zone_id: uuid.UUID = Field(description="Zone of the engagement's sites.")
    location_desc: str = Field(min_length=1, max_length=150, examples=["Gridline P7–P9 east"])
    level_code: str | None = Field(default=None, max_length=10)
    grid_x_m: DecimalStr | None = Field(default=None, max_digits=8, decimal_places=1)
    grid_y_m: DecimalStr | None = Field(default=None, max_digits=8, decimal_places=1)
    scaffold_type: ScaffoldType
    height_m: Metres2 = Field(gt=Decimal(0))
    load_class: int = Field(ge=1, le=6, description="EN 12811-1 class 1–6.")
    design_ref: str | None = Field(
        default=None,
        max_length=40,
        description="Required at handover when SF-2 applies (422 SCAFFOLD_DESIGN_REQUIRED).",
    )
    sheeting_fitted: bool = Field(default=False, description="Sheeting / netting (SF-2).")
    erection_supervisor_worker_id: uuid.UUID
    erection_crew_worker_ids: list[uuid.UUID] = Field(
        min_length=1, description="Trade scaffolder; SCAFFOLDER hook at handover (SF-3)."
    )


class ScaffoldCreate(ScaffoldFields):
    """Capability 106 (site engineers too) → Under Erection, tag red ("not complete — do not
    use"). tag unique on the project among non-dismantled scaffolds (409 TAG_EXISTS)."""

    tag: str = Field(pattern=TAG_PATTERN, examples=["SC-0142"])


class ScaffoldUpdate(PatchInput):
    non_nullable = frozenset(
        {
            "zone_id",
            "location_desc",
            "scaffold_type",
            "height_m",
            "load_class",
            "erection_supervisor_worker_id",
            "erection_crew_worker_ids",
        }
    )

    zone_id: uuid.UUID | None = None
    location_desc: str | None = Field(default=None, min_length=1, max_length=150)
    level_code: str | None = Field(default=None, max_length=10)
    grid_x_m: DecimalStr | None = Field(default=None, max_digits=8, decimal_places=1)
    grid_y_m: DecimalStr | None = Field(default=None, max_digits=8, decimal_places=1)
    scaffold_type: ScaffoldType | None = None
    height_m: Metres2 | None = None
    load_class: int | None = Field(default=None, ge=1, le=6)
    design_ref: str | None = Field(default=None, max_length=40)
    sheeting_fitted: bool | None = None
    erection_supervisor_worker_id: uuid.UUID | None = None
    erection_crew_worker_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)


class ScaffoldTransitionRequest(StrictInput):
    """§4.6 (capability 106): in_use / closed_red → under_alteration (alteration started, tag
    red); any → dismantled (terminal, token revoked). In Use is reached only through an
    inspection (capability 113)."""

    to_status: ScaffoldStatus
    reason: str | None = Field(default=None, max_length=500)


class ScaffoldChecklistLine(StrictInput):
    item: ScaffoldChecklistItem
    result: ChecklistItemResult = Field(description="n.a. only for SIC-10.")


class ScaffoldInspectionCreate(StrictInput):
    """Capability 113. The inspector worker must hold an in-force SCAFFOLD-INSPECTOR
    certificate at inspected_at in every hook stage (422 INSPECTOR_NOT_CERTIFIED, SF-4); a
    handover inspector ≠ erection supervisor (422 SOD_CONFLICT). inspected_at ≤ now and
    ≥ now − 60 min (422 BACKDATED_INSPECTION). Yellow needs restrictions (422
    RESTRICTIONS_REQUIRED). Handover: SF-2 design (422 SCAFFOLD_DESIGN_REQUIRED) and SF-3
    crew certificates (transition: warning; block or hard stop: 422 CREW_NOT_CERTIFIED)."""

    inspection_type: ScaffoldInspectionType
    inspected_at: datetime | None = Field(default=None, description="UTC; default now.")
    inspector_worker_id: uuid.UUID
    checklist: list[ScaffoldChecklistLine] = Field(min_length=11, max_length=11)
    result: ScaffoldInspectionResult
    restrictions_en: str | None = Field(default=None, max_length=300, description=P4_HINT)
    restrictions_ar: str | None = Field(default=None, max_length=300)
    photo_attachment_ids: list[uuid.UUID] = Field(
        default_factory=list, description="Owner scaffold_inspection_photo; avoid faces."
    )


class ScaffoldChecklistLineRead(ApiModel):
    item: ScaffoldChecklistItem
    label_en: str
    label_ar: str
    result: ChecklistItemResult


class ScaffoldInspectionRead(ApiModel):
    id: uuid.UUID
    scaffold_id: uuid.UUID
    inspection_type: ScaffoldInspectionType
    inspected_at: datetime
    inspector: WorkerRef | None = Field(description="Null without capability 46 (name).")
    recorded_by: UserRef
    checklist: list[ScaffoldChecklistLineRead]
    result: ScaffoldInspectionResult
    restrictions_en: str | None
    restrictions_ar: str | None
    tag_valid_until: date | None = Field(description="§6.4; null for red.")
    photo_attachment_ids: list[uuid.UUID]
    warnings: list[ApiWarning] = Field(
        description="E.g. CREW_NOT_CERTIFIED under the transition stage (SF-3)."
    )


class ScaffoldInspectionList(ApiModel):
    items: list[ScaffoldInspectionRead]


class ScaffoldRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    scaffold_no: str = Field(examples=["SCF-ANIA-EXP-0142"])
    tag: str
    engagement: EngagementRef
    zone: ZoneRef
    location_desc: str
    level_code: str | None
    grid_x_m: DecimalStr | None
    grid_y_m: DecimalStr | None
    scaffold_type: ScaffoldType
    height_m: DecimalStr
    load_class: int
    load_class_kn_m2: DecimalStr = Field(description="0.75 / 1.5 / 2.0 / 3.0 / 4.5 / 6.0.")
    design_ref: str | None
    design_required: bool = Field(description="SF-2.")
    sheeting_fitted: bool
    erection_supervisor: WorkerRef | None
    erection_crew: list[WorkerRef]
    crew_certification: list[EligibilityItem] = Field(
        description="SF-3 SCAFFOLDER results for the crew (advanced for SF-2 scaffolds)."
    )
    status: ScaffoldStatus
    tag_status: ScaffoldTagStatus
    tag_valid_until: date | None
    usable_today: bool = Field(description="SF-1: green or yellow and tag_valid_until ≥ today.")
    restrictions_en: str | None = Field(description="Current yellow-tag restriction (SF-6).")
    restrictions_ar: str | None
    inspection_required_reason: ReinspectionReason | None
    inspection_required_at: datetime | None
    last_inspection: ScaffoldInspectionRead | None
    sticker_printed_ref: str | None
    has_sticker: bool
    created_at: datetime
    updated_at: datetime


class ScaffoldPage(Page[ScaffoldRead]):
    pass


class ScaffoldReinspectionRequest(StrictInput):
    """SF-5 "Require re-inspection" (capability 112): every In Use scaffold of the site
    (or zone) gets tag_status inspection_required immediately — a hard stop until a new
    inspection (HK4-3)."""

    site_id: uuid.UUID
    zone_id: uuid.UUID | None = None
    reason: ReinspectionReason
    reason_text: str = Field(min_length=10, max_length=500)


class ScaffoldReinspectionResult(ApiModel):
    at: datetime
    reason: ReinspectionReason
    affected: list[ScaffoldRef]


class ScaffoldBoardZone(ApiModel):
    zone: ZoneRef
    scaffolds: list[ScaffoldRef]
    counts: dict[str, int] = Field(description="tag_status → count.")


class ScaffoldBoard(ApiModel):
    """§8.4 tag board per zone."""

    project_id: uuid.UUID
    as_of: date
    zones: list[ScaffoldBoardZone]
