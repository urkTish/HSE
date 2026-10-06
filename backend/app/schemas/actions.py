"""Corrective actions (spec 1-dashboard §3.8, §4.5, §5.5, §6.6)."""

import uuid
from datetime import date, datetime

from pydantic import Field

from app.core.hse_enums import (
    CaPriority,
    CaSourceType,
    CaStatus,
    ControlLevel,
    ExtensionStatus,
    OverdueBucket,
)
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput, Timestamps
from app.schemas.hse_common import ApiWarning, EngagementRef, SiteRef, UserRef, ZoneRef


class CaInline(StrictInput):
    """A CA created together with its source (inspection finding, investigation root cause)."""

    title: str = Field(min_length=1, max_length=150)
    description: str = Field(min_length=1, max_length=2000)
    control_level: ControlLevel
    priority: CaPriority
    owner_id: uuid.UUID
    verifier_id: uuid.UUID
    responsible_engagement_id: uuid.UUID | None = Field(
        default=None, description="Defaults to the source's engagement."
    )
    due_date: date | None = Field(
        default=None, description="Default created date + ca_due_days[priority] (CA-2)."
    )


class CaCreate(CaInline):
    """Create a CA (capability 34). `source_id` is required except for source_type = other.
    For `ai_recommendation`, `source_id` is the AI answer id and `ai_recommendation_id` the
    recommendation inside it (CA-7: only by a human, after editing the draft).

    Rules: verifier ≠ owner (`VERIFIER_IS_OWNER`); verifier role per priority
    (`VERIFIER_ROLE_NOT_ALLOWED`, CA-5); due_date later than default → `DUE_DATE_TOO_LATE`
    (use an extension). Response `warnings` may contain `PPE_ONLY_CONTROL` (CA-6)."""

    source_type: CaSourceType
    source_id: uuid.UUID | None = None
    ai_recommendation_id: str | None = Field(default=None, max_length=40)
    site_id: uuid.UUID | None = Field(default=None, description="Defaults to the source's site.")
    zone_id: uuid.UUID | None = None


class CaUpdate(PatchInput):
    """Owner-editable while open/in_progress; HSE Officer/Manager may also change owner,
    verifier and priority. due_date changes only via extensions."""

    non_nullable = frozenset(
        {"title", "description", "control_level", "priority", "owner_id", "verifier_id"}
    )

    title: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    control_level: ControlLevel | None = None
    priority: CaPriority | None = None
    owner_id: uuid.UUID | None = None
    verifier_id: uuid.UUID | None = None
    zone_id: uuid.UUID | None = None


class CaSourceRef(ApiModel):
    type: CaSourceType
    id: uuid.UUID | None
    ref: str | None = Field(description="e.g. INC-ANIA-EXP-2026-0147, or the AI answer id.")


class CaExtensionRead(ApiModel):
    id: uuid.UUID
    new_due_date: date
    previous_due_date: date
    reason: str
    status: ExtensionStatus
    requested_by: UserRef
    requested_at: datetime
    decided_by: UserRef | None
    decided_at: datetime | None
    decision_comment: str | None


class CaRead(Timestamps):
    id: uuid.UUID
    ref: str = Field(examples=["CA-ANIA-EXP-2026-00398"])
    project_id: uuid.UUID
    source: CaSourceRef
    site: SiteRef
    zone: ZoneRef | None
    responsible_engagement: EngagementRef
    title: str
    description: str
    control_level: ControlLevel
    priority: CaPriority
    owner: UserRef
    verifier: UserRef
    due_date: date = Field(description="Current approved due date.")
    original_due_date: date = Field(description="Immutable (CA-3).")
    extensions: list[CaExtensionRead]
    status: CaStatus
    completed_at: datetime | None
    evidence_text: str | None
    evidence_attachment_count: int
    verified_at: datetime | None
    verification_comment: str | None
    cancel_reason: str | None
    overdue: bool = Field(description="Derived (§6.6): open/in_progress and today > due_date.")
    days_overdue: int | None
    overdue_bucket: OverdueBucket | None
    verification_overdue: bool = Field(description="K-42b: pending > completed date + 3 days.")
    allowed_transitions: list[CaStatus]
    warnings: list[ApiWarning] = Field(default_factory=list)


class CaPage(Page[CaRead]):
    pass


class CaTransitionRequest(StrictInput):
    """§4.5:

    * open → in_progress (owner: accept)
    * open/in_progress → pending_verification (owner): evidence_text ≥ 20 chars or ≥ 1
      evidence attachment, else `EVIDENCE_REQUIRED`; sets completed_at
    * pending_verification → closed (verifier): sets verified_at; verifier = owner →
      `VERIFIER_IS_OWNER`
    * pending_verification → in_progress (verifier): `comment` required; clears completed_at
    * open/in_progress → cancelled (HSE Officer/Manager): `reason` required
    * closed → in_progress (HSE Manager): `reason` required (reopen)
    """

    to_status: CaStatus
    evidence_text: str | None = Field(default=None, max_length=2000)
    comment: str | None = Field(default=None, max_length=1000)
    reason: str | None = Field(default=None, max_length=500)


class CaExtensionCreate(StrictInput):
    """Owner requests (CA-3). More than ca_max_extensions → `EXTENSION_LIMIT_REACHED`."""

    new_due_date: date
    reason: str = Field(min_length=1, max_length=500)


class CaExtensionDecision(StrictInput):
    """HSE Officer/Manager (not the owner) approves or rejects (capability 37)."""

    approve: bool
    comment: str | None = Field(default=None, max_length=500)
