"""Induction courses and records, zone access profiles and the eligibility function
(spec 2-access-permits §3.3-§3.5, §4.3, §5.2, §5.3)."""

import uuid
from datetime import date, datetime

from pydantic import Field

from app.core.access_enums import (
    AreaCategory,
    EligibilityContext,
    GateReasonCode,
    HookKind,
    HookPolicy,
    InductionDelivererRole,
    InductionResult,
    InductionStatus,
    InductionType,
    RequirementKind,
    RequirementStatus,
    WorkerLanguage,
)
from app.schemas.access_common import HookRequirement, HookRequirementRead, WorkerRef
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput, Timestamps
from app.schemas.hse_common import ApiWarning, EngagementRef, UserRef, ZoneRef

VERSION = r"^\d+\.\d+$"

# ---- courses ------------------------------------------------------------------------------------


class InductionCourseCreate(StrictInput):
    """Capability 50. airside courses, and zone_specific courses used by an airside zone
    profile, cannot list contractor_hse_rep (422 DELIVERER_NOT_ALLOWED, IN-3)."""

    code: str = Field(min_length=1, max_length=10, examples=["AIR"])
    induction_type: InductionType
    name_en: str = Field(min_length=1, max_length=150)
    name_ar: str = Field(min_length=1, max_length=150)
    version: str = Field(pattern=VERSION, examples=["2.0"])
    validity_months: int | None = Field(
        default=None, ge=1, le=36, description="Required unless visitor."
    )
    validity_days: int | None = Field(default=None, ge=1, le=7, description="Visitor only.")
    min_duration_minutes: int = Field(ge=15)
    test_required: bool
    pass_mark_pct: int | None = Field(
        default=None, ge=50, le=100, description="Default = setting induction_pass_mark_pct."
    )
    languages_offered: list[WorkerLanguage] = Field(min_length=1)
    prerequisite_codes: list[str] = Field(default_factory=list)
    delivered_by_roles: list[InductionDelivererRole] = Field(min_length=1)
    active: bool = True


class InductionCourseUpdate(PatchInput):
    """Code and type are immutable. A new version is published with
    POST /induction-courses/{id}/versions."""

    non_nullable = frozenset(
        {
            "name_en",
            "name_ar",
            "min_duration_minutes",
            "test_required",
            "languages_offered",
            "delivered_by_roles",
            "active",
        }
    )

    name_en: str | None = Field(default=None, min_length=1, max_length=150)
    name_ar: str | None = Field(default=None, min_length=1, max_length=150)
    validity_months: int | None = Field(default=None, ge=1, le=36)
    validity_days: int | None = Field(default=None, ge=1, le=7)
    min_duration_minutes: int | None = Field(default=None, ge=15)
    test_required: bool | None = None
    pass_mark_pct: int | None = Field(default=None, ge=50, le=100)
    languages_offered: list[WorkerLanguage] | None = Field(default=None, min_length=1)
    prerequisite_codes: list[str] | None = None
    delivered_by_roles: list[InductionDelivererRole] | None = Field(default=None, min_length=1)
    active: bool | None = None


class InductionCourseVersionPublish(StrictInput):
    """IN-9: requires_reinduction = true sets reinduction_due_on = publish date +
    reinduction_grace_days on every Valid record of older versions (they expire on that date
    unless superseded)."""

    version: str = Field(pattern=VERSION, examples=["3.0"])
    requires_reinduction: bool
    published_on: date | None = Field(default=None, description="Default today.")


class InductionCourseRead(Timestamps):
    id: uuid.UUID
    project_id: uuid.UUID
    code: str
    induction_type: InductionType
    name_en: str
    name_ar: str
    version: str
    version_published_on: date | None
    requires_reinduction: bool
    validity_months: int | None
    validity_days: int | None
    min_duration_minutes: int
    test_required: bool
    pass_mark_pct: int | None
    effective_pass_mark_pct: int | None = Field(
        description="max(course pass mark, setting induction_pass_mark_pct) when a test is set."
    )
    languages_offered: list[WorkerLanguage]
    prerequisite_codes: list[str]
    delivered_by_roles: list[InductionDelivererRole]
    active: bool


class InductionCourseList(ApiModel):
    items: list[InductionCourseRead]


# ---- records ------------------------------------------------------------------------------------


class InductionAttendee(StrictInput):
    worker_id: uuid.UUID
    delivery_language: WorkerLanguage
    interpreter_used: bool = False
    test_score_pct: str | None = Field(
        default=None,
        pattern=r"^\d{1,3}(\.\d{1,2})?$",
        description="0-100, 2 dp. Required iff the course has a test.",
    )
    privacy_notice_version: str = Field(min_length=1, max_length=20, examples=["WPN-1.0"])
    signature_png_base64: str = Field(
        min_length=1,
        max_length=400_000,
        description="Drawn signature (attendance + worker privacy notice, P2-9) as base64 PNG; "
        "stored as an attachment (induction_signature).",
    )
    helmet_sticker_no: str | None = Field(
        default=None, max_length=20, description="Unique within the project (IN-13)."
    )


class InductionRecordCreate(InductionAttendee):
    """Capability 51. Rules: deployment on the project (pending_induction or mobilised);
    deliverer role ∈ course.delivered_by_roles (403 DELIVERER_NOT_ALLOWED) and ≠ the worker
    (IN-12); prerequisites Valid at delivered_at (422 INDUCTION_PREREQUISITE); duration ≥
    minimum (422 INDUCTION_TOO_SHORT); attempts within 30 days ≤ setting (422
    INDUCTION_ATTEMPTS_EXCEEDED). Result is derived (IN-5). Language mismatch without
    interpreter saves with warning LANGUAGE_MISMATCH (IN-6). A passed general_site record
    mobilises a pending deployment and issues the access card (IN-1)."""

    course_id: uuid.UUID
    delivered_at: datetime = Field(description="UTC; ≤ now.")
    delivered_by_user_id: uuid.UUID | None = Field(default=None, description="Default: the caller.")
    duration_minutes: int = Field(ge=1)
    session_ref: str | None = Field(default=None, max_length=30)


class InductionSessionCreate(StrictInput):
    """Record one session for several attendees (capability 51). Each attendee is validated
    like a single record; the response lists per-attendee results (no partial commit: any
    error rejects the whole session with field errors per attendee index)."""

    course_id: uuid.UUID
    delivered_at: datetime
    delivered_by_user_id: uuid.UUID | None = None
    duration_minutes: int = Field(ge=1)
    session_ref: str | None = Field(default=None, max_length=30)
    attendees: list[InductionAttendee] = Field(min_length=1, max_length=60)


class InductionRecordUpdate(PatchInput):
    """IN-11: records are never deleted; edits after 24 h only by the HSE Manager with
    `edit_reason` (422 INDUCTION_EDIT_LOCKED otherwise)."""

    non_nullable = frozenset({"interpreter_used", "delivery_language"})

    delivery_language: WorkerLanguage | None = None
    interpreter_used: bool | None = None
    helmet_sticker_no: str | None = Field(default=None, max_length=20)
    session_ref: str | None = Field(default=None, max_length=30)
    edit_reason: str | None = Field(default=None, min_length=10, max_length=500)


class InductionRetrainingNote(StrictInput):
    """IN-5: lets a worker attempt again after reaching induction_max_attempts_30d."""

    worker_id: uuid.UUID
    course_id: uuid.UUID
    note: str = Field(min_length=10, max_length=500)


class InductionRetrainingNoteRead(ApiModel):
    id: uuid.UUID
    worker_id: uuid.UUID
    course_id: uuid.UUID
    note: str
    recorded_by: UserRef
    recorded_at: datetime


class InductionRecordRead(Timestamps):
    id: uuid.UUID
    induction_no: str = Field(examples=["IND-ANIA-EXP-2026-03117"])
    project_id: uuid.UUID
    worker: WorkerRef
    engagement: EngagementRef | None
    course_id: uuid.UUID
    course_code: str
    induction_type: InductionType
    course_version: str
    session_ref: str | None
    delivered_at: datetime
    delivered_by: UserRef
    delivery_language: WorkerLanguage
    interpreter_used: bool
    language_mismatch: bool = Field(description="IN-6, counted in the data-quality list.")
    duration_minutes: int
    test_score_pct: str | None = Field(description="2 dp.")
    attempt_no: int
    result: InductionResult
    privacy_notice_version: str
    signature_attachment_id: uuid.UUID | None
    valid_from: date | None
    valid_until: date | None = Field(description="§6.1 X1; null if failed.")
    reinduction_due_on: date | None = Field(description="IN-9.")
    days_left: int | None
    helmet_sticker_no: str | None
    status: InductionStatus
    warnings: list[ApiWarning] = Field(default_factory=list)


class InductionRecordPage(Page[InductionRecordRead]):
    pass


class InductionSessionResult(ApiModel):
    items: list[InductionRecordRead]


# ---- zone access profiles -----------------------------------------------------------------------


class ZoneAccessProfileRead(ApiModel):
    """Created with defaults when the zone is created (ZP-1)."""

    zone: ZoneRef
    site_id: uuid.UUID
    required_inductions: list[str] = Field(examples=[["GEN", "AIR"]])
    airport_pass_area_code: str | None
    access_permit_required: bool
    adp_category_required: AreaCategory | None
    avp_area_required: AreaCategory | None
    escort_ratio_max: int | None
    lvp_withdrawal_required: bool
    ils_outage_notam_required: bool
    hook_requirements: list[HookRequirementRead]
    updated_at: datetime
    updated_by: UserRef | None


class ZoneAccessProfileUpdate(PatchInput):
    """Capability 81. Only tightening is allowed (ZP-2): removing the airside course from an
    airside zone, access_permit_required = false on a movement-area/SRA zone or escort ratio
    above the setting → 422 PROFILE_LOOSENING."""

    non_nullable = frozenset(
        {
            "required_inductions",
            "access_permit_required",
            "lvp_withdrawal_required",
            "ils_outage_notam_required",
            "hook_requirements",
        }
    )

    required_inductions: list[str] | None = Field(default=None, min_length=1)
    airport_pass_area_code: str | None = None
    access_permit_required: bool | None = None
    adp_category_required: AreaCategory | None = None
    avp_area_required: AreaCategory | None = None
    escort_ratio_max: int | None = Field(default=None, ge=1, le=10)
    lvp_withdrawal_required: bool | None = None
    ils_outage_notam_required: bool | None = None
    hook_requirements: list[HookRequirement] | None = None


class ZoneAccessProfileList(ApiModel):
    items: list[ZoneAccessProfileRead]


# ---- eligibility (ZP-3, ZP-4) -------------------------------------------------------------------


class EligibilityItem(ApiModel):
    """One requirement of E(worker, zone, at, context)."""

    kind: RequirementKind
    code: str | None = Field(
        description="Course code, area code, hook code, ADP category…", examples=["AIR"]
    )
    hook_kind: HookKind | None = None
    status: RequirementStatus
    valid_until: date | None
    ref: str | None = Field(examples=["IND-ANIA-EXP-2025-02210", "ANIA-AP-26-01877"])
    reason_code: GateReasonCode | None = Field(
        description="Why not met / warn (GC-6 codes, e.g. INDUCTION_EXPIRED, HOOK_NOT_AVAILABLE)."
    )
    message_en: str | None = None
    message_ar: str | None = None


class EligibilityResult(ApiModel):
    """Eligible iff no item is not_met (and, under `block` hook policy, none not_evaluated).
    Also used by Phase 3 (HK-6, context = ptw)."""

    worker: WorkerRef
    zone: ZoneRef
    at: datetime
    context: EligibilityContext
    eligible: bool
    escort_required: bool
    items: list[EligibilityItem]


class HookProviderInfo(ApiModel):
    kind: HookKind
    registered: bool = Field(description="False until Phase 4/5/6 registers a provider (HK-3).")
    policy: HookPolicy
    available_from_phase: int = Field(examples=[5])
