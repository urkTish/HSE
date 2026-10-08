"""Equipment and scaffold defects: raise → rectify → close / return to service (spec
4-third-party-cert §3.11, §4.5, §6.3, DF-1…DF-10)."""

import uuid
from datetime import date, datetime

from pydantic import Field

from app.core.cert_enums import (
    DefectCategory,
    DefectClosureMethod,
    DefectSource,
    DefectStatus,
)
from app.schemas.access_common import WorkerRef
from app.schemas.cert_common import P4_HINT, CertLineRef, EquipmentRef, ScaffoldRef
from app.schemas.common import ApiModel, Page, StrictInput
from app.schemas.hse_common import EngagementRef, UserRef


class DefectCreate(StrictInput):
    """Capability 110. One of equipment_id (item with a deployment on the project) or
    scaffold_id. Category A → item Out of Service at once (`defect_a`, DF-3): requires
    `physical_tag_applied` = true (422 PHYSICAL_TAG_REQUIRED). A on a lifting_accessory /
    tripod_winch can only be closed as destroyed (DF-7). B due date per §6.3."""

    equipment_id: uuid.UUID | None = None
    scaffold_id: uuid.UUID | None = None
    source: DefectSource
    source_ref: str | None = Field(
        default=None,
        max_length=40,
        description="Phase 1 inspection / incident / observation ref, PTW audit no.",
        examples=["INC-ANIA-EXP-2026-0150"],
    )
    category: DefectCategory
    description_en: str = Field(min_length=1, max_length=1000, description=P4_HINT)
    description_ar: str | None = Field(default=None, max_length=1000)
    photo_attachment_ids: list[uuid.UUID] = Field(
        default_factory=list, description="Owner defect_photo; avoid faces."
    )
    raised_by_worker_id: uuid.UUID | None = Field(
        default=None, description="When a worker (operator) raised it; else the caller."
    )
    raised_at: datetime | None = Field(default=None, description="UTC ≤ now; default now.")
    tpi_due_date: date | None = Field(default=None, description="B only (§6.3).")
    physical_tag_applied: bool = False


class RectificationInput(StrictInput):
    """DF-5 (capability 111): does not return the item to service. Category A on a lifting
    accessory or tripod winch → 422 ACCESSORY_REPAIR_NOT_ALLOWED (DF-7)."""

    description: str = Field(min_length=10, max_length=1000)
    done_by_text: str = Field(min_length=1, max_length=120, examples=["OEM service engineer"])
    done_at: datetime = Field(description="UTC ≤ now.")
    evidence_attachment_ids: list[uuid.UUID] = Field(
        default_factory=list, description="Owner defect_evidence."
    )


class DefectCloseInput(StrictInput):
    """DF-6 (capability 112; ≠ rectifier and not employed by the owner contractor, 422
    SOD_CONFLICT). A defects on cranes, hoists, mast climbers, BMUs, MEWPs, man-baskets and
    telehandlers / forklifts (structural, hydraulic-holding or safety-device) need method
    tpi_certificate with an accepted, verified after_repair line inspected after
    rectification (422 TPI_REINSPECTION_REQUIRED); others close by HSE verification with
    photo evidence."""

    method: DefectClosureMethod
    cert_line_id: uuid.UUID | None = Field(
        default=None, description="Required for tpi_certificate."
    )
    note: str = Field(min_length=5, max_length=500)
    evidence_attachment_ids: list[uuid.UUID] = Field(default_factory=list)
    requires_tpi_reinspection: bool | None = Field(
        default=None,
        description="Category A only: whether the defect is structural, hydraulic-holding or "
        "a safety device (DF-6). Default true for the listed categories.",
    )


class DefectReopenInput(StrictInput):
    """Rectified → Open (capability 112): verification failed."""

    reason: str = Field(min_length=10, max_length=500)


class DefectDestroyInput(StrictInput):
    """DF-7 (capability 112): Open A on a lifting accessory / tripod winch → Closed
    (destroyed / returned to manufacturer); the item is Retired (`retired_destroyed`)."""

    note: str = Field(min_length=5, max_length=500)
    returned_to_manufacturer: bool = False


class DefectCancelInput(StrictInput):
    """Raised in error (capability 112); not for TPI-raised defects (422
    TPI_DEFECT_NOT_CANCELLABLE)."""

    reason: str = Field(min_length=20, max_length=500)


class RectificationRead(ApiModel):
    description: str
    done_by_text: str
    done_at: datetime
    recorded_by: UserRef
    evidence_attachment_ids: list[uuid.UUID]


class DefectClosureRead(ApiModel):
    method: DefectClosureMethod
    cert_line: CertLineRef | None
    closed_by: UserRef
    closed_at: datetime
    note: str
    evidence_attachment_ids: list[uuid.UUID]


class DefectRead(ApiModel):
    id: uuid.UUID
    defect_no: str = Field(examples=["DEF-ANIA-EXP-2026-0007"])
    project_id: uuid.UUID
    equipment: EquipmentRef | None
    scaffold: ScaffoldRef | None
    tag: str | None = Field(description="Deployment tag or scaffold tag.")
    engagement: EngagementRef | None = Field(description="KC-3 attribution at raised_at.")
    source: DefectSource
    source_ref: str | None
    cert_line: CertLineRef | None = Field(description="TPI certificate line that raised it.")
    category: DefectCategory
    description_en: str
    description_ar: str | None
    photo_attachment_ids: list[uuid.UUID]
    raised_by_user: UserRef | None
    raised_by_worker: WorkerRef | None
    raised_at: datetime
    physical_tag_applied: bool
    tpi_due_date: date | None
    due_date: date | None = Field(description="§6.3; B only.")
    days_left: int | None
    overdue: bool
    rectification: RectificationRead | None
    closure: DefectClosureRead | None
    status: DefectStatus
    cancelled_reason: str | None
    allowed_actions: list[str] = Field(
        examples=[["rectify", "close", "destroy", "reopen", "cancel"]]
    )
    created_at: datetime
    updated_at: datetime


class DefectPage(Page[DefectRead]):
    pass


class IncidentDefectPrompt(ApiModel):
    """DF-9: incidents whose agency is crane_lifting_gear, mewp or scaffold prompt the
    investigator to link or raise a defect (not mandatory; no Phase 1 field changes)."""

    incident_id: uuid.UUID
    incident_ref: str
    prompt: bool
    agency: str | None
    linked_defects: list[DefectRead]
