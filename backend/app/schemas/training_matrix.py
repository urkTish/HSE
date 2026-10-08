"""Training matrix, worker training profiles, requirement status, exemptions, the gap register
and the refresher plan (spec 5-training §3.4, §3.5, §3.10, §3.11, §3.14, §4.3, §6.2, §6.7,
MX-1…MX-12, GP-1…GP-8)."""

import uuid
from datetime import date, datetime

from pydantic import Field

from app.core.access_enums import DeploymentStatus, WorkerLanguage
from app.core.hse_enums import Trade
from app.core.train_enums import (
    ExemptionStatus,
    MatrixAppliesTo,
    MatrixLevel,
    MatrixLineSource,
    MatrixRole,
    ProfileField,
    RefresherPlanState,
    RequirementState,
)
from app.schemas.access_common import WorkerRef
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput
from app.schemas.hse_common import EngagementRef, UserRef, ZoneRef
from app.schemas.ptw_common import PermitRef
from app.schemas.training_common import (
    COURSE_CODE,
    P5_HINT,
    CourseRef,
    TrainingRecordRef,
    TrainingSessionRef,
)

# ---- matrix lines ---------------------------------------------------------------------------


class MatrixRequirement(StrictInput):
    """Exactly one of `course_code` or `any_of` (2-6 codes; categories professional_qualification
    and awareness only — 422 ANY_OF_NOT_ALLOWED, MX-3)."""

    course_code: str | None = Field(default=None, pattern=COURSE_CODE)
    any_of: list[str] | None = Field(default=None, min_length=2, max_length=6)


class MatrixRequirementRead(ApiModel):
    course_code: str | None
    any_of: list[str] | None
    courses: list[CourseRef]


class MatrixLineCreate(StrictInput):
    """Capability 129 → a manual line effective today (MX-7, no back-dating).
    `due_within_days` ≤ matrix_line_max_due_days and 0 when the code (or a code it satisfies)
    is a hook code on the project (422 DUE_DAYS_NOT_ALLOWED)."""

    applies_to_kind: MatrixAppliesTo
    applies_to_values: list[str] = Field(
        default_factory=list,
        description="Not for all_workers; trade ⊆ list T; matrix_role ⊆ MR; zone ⊆ project "
        "zone ids; pass_category ⊆ AP-CAT; adp_category ⊆ {apron, manoeuvring, airside_roads}.",
        examples=[["scaffolder", "steel_erector", "rigger"]],
    )
    requirement: MatrixRequirement
    level: MatrixLevel
    due_within_days: int = Field(ge=0, le=180)


class MatrixLineUpdate(PatchInput):
    """Closes the current version (effective_to = yesterday) and opens a new one from today
    (MX-7). Downgrade to recommended or a higher due_within_days on a mandatory line needs the
    HSE Manager and `reason` ≥ 20 (422 MATRIX_LOOSENING, MX-8). Hook lines → 422
    LINE_DERIVED_FROM_HOOK."""

    non_nullable = frozenset({"applies_to_values", "requirement", "level", "due_within_days"})

    applies_to_values: list[str] | None = None
    requirement: MatrixRequirement | None = None
    level: MatrixLevel | None = None
    due_within_days: int | None = Field(default=None, ge=0, le=180)
    reason: str | None = Field(default=None, max_length=300, description=P5_HINT)


class MatrixLineRemove(StrictInput):
    """Sets effective_to = yesterday. A mandatory manual line: HSE Manager only, reason ≥ 20
    (MX-8)."""

    reason: str | None = Field(default=None, max_length=300, description=P5_HINT)


class MatrixLineRead(ApiModel):
    id: uuid.UUID = Field(description="The line (stable across versions).")
    version_id: uuid.UUID
    line_no: str = Field(examples=["MXL-ANIA-EXP-003", "MXL-ANIA-EXP-H01", "MXL-ANIA-EXP-E05"])
    project_id: uuid.UUID
    applies_to_kind: MatrixAppliesTo
    applies_to_values: list[str]
    applies_to_labels: list[str] = Field(description="EN labels for display.")
    requirement: MatrixRequirementRead
    level: MatrixLevel
    due_within_days: int
    source: MatrixLineSource
    kpi_counted: bool = Field(description="False for crew_role / appointment_function (MX-2).")
    hook_attach_point: str | None = Field(
        description="Hook lines: e.g. 'zone profile Z-TWB', 'crew role standby_person'."
    )
    effective_from: date
    effective_to: date | None
    reason: str | None
    applicable_deployments: int | None = Field(
        default=None, description="Count at as_of (kpi_counted lines)."
    )
    created_by: UserRef | None
    created_at: datetime


class MatrixRead(ApiModel):
    project_id: uuid.UUID
    as_of: date
    lines: list[MatrixLineRead]


class MatrixLineVersions(ApiModel):
    line_id: uuid.UUID
    line_no: str
    versions: list[MatrixLineRead] = Field(description="Newest first.")


# ---- training profile -----------------------------------------------------------------------


class TrainingProfileUpdate(PatchInput):
    """Capability 130 (Contractor HSE Rep: C-scope deployments). Applies from today; each
    change opens a history row (MX-9). Zones of the deployment's sites only (422
    ZONE_NOT_IN_DEPLOYMENT_SITES)."""

    non_nullable = frozenset({"matrix_roles", "work_zone_ids"})

    matrix_roles: list[MatrixRole] | None = None
    work_zone_ids: list[uuid.UUID] | None = None


class ProfileHistoryRow(ApiModel):
    field: ProfileField
    value: list[str]
    from_date: date
    to_date: date | None
    by: UserRef | None


class TrainingProfileRead(ApiModel):
    deployment_id: uuid.UUID
    project_id: uuid.UUID
    worker: WorkerRef
    engagement: EngagementRef
    trade: Trade | None
    matrix_roles: list[MatrixRole]
    work_zones: list[ZoneRef]
    history: list[ProfileHistoryRow]
    updated_at: datetime | None


# ---- requirement status (§3.10, §6.2) ---------------------------------------------------------


class RequirementStatus(ApiModel):
    """One de-duplicated requirement of a deployment at as_of (MX-6)."""

    line_nos: list[str] = Field(description="Lines giving this requirement (MX-6).")
    requirement: MatrixRequirementRead
    level: MatrixLevel
    kpi_counted: bool
    hook_code: bool
    critical: bool
    applies_from: date
    due_date: date
    state: RequirementState
    counted: bool = Field(description="§6.2: counted in K-82…K-84 at as_of.")
    satisfied_by_record: TrainingRecordRef | None
    satisfied_by_induction_no: str | None = Field(description="induction_link codes (CC-7).")
    valid_until: date | None
    booked_session: TrainingSessionRef | None
    exemption_id: uuid.UUID | None
    not_met_reason: str | None = Field(
        description="Hook reason for gaps, e.g. TRAINING_MISSING, TRAINING_EXPIRED."
    )


class DeploymentRequirements(ApiModel):
    """GET /deployments/{id}/training-requirements: the competence profile (kpi_counted lines
    plus enforcement lines while on a permit crew / WAP / appointment)."""

    deployment_id: uuid.UUID
    project_id: uuid.UUID
    as_of: date
    worker: WorkerRef
    engagement: EngagementRef
    deployment_status: DeploymentStatus
    kpi_population: bool = Field(description="contractor_worker deployment (TK-2).")
    requirements: list[RequirementStatus]


# ---- exemptions (§3.11, MX-10) ----------------------------------------------------------------


class ExemptionCreate(StrictInput):
    """Capability 129. Never for IND-GENERAL or hook codes (422 EXEMPTION_NOT_ALLOWED);
    valid_until ≤ today + 6 months."""

    deployment_id: uuid.UUID
    line_id: uuid.UUID
    reason: str = Field(min_length=30, max_length=500, description=P5_HINT)
    valid_until: date


class ExemptionWithdraw(StrictInput):
    reason: str = Field(min_length=10, max_length=500, description=P5_HINT)


class ExemptionRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    deployment_id: uuid.UUID
    worker: WorkerRef
    line_no: str
    requirement: MatrixRequirementRead
    reason: str
    valid_until: date
    status: ExemptionStatus
    granted_by: UserRef
    granted_at: datetime
    withdrawn_by: UserRef | None
    withdrawn_at: datetime | None


class ExemptionPage(Page[ExemptionRead]):
    pass


# ---- gap register (GP-1, GP-2) --------------------------------------------------------------


class GapRow(ApiModel):
    """Viewer/Client never get rows (counts only via /summary, TK-5)."""

    deployment_id: uuid.UUID
    worker: WorkerRef
    engagement: EngagementRef
    trade: Trade | None
    line_nos: list[str]
    requirement: MatrixRequirementRead
    level: MatrixLevel
    hook_code: bool
    critical: bool
    due_date: date
    state: RequirementState
    days_overdue: int | None
    valid_until: date | None
    booked_session: TrainingSessionRef | None
    live_permits: list[PermitRef] = Field(
        description="Non-terminal permits naming the worker (GP-7, hook codes)."
    )
    live_wap_nos: list[str]


class GapPage(Page[GapRow]):
    pass


class GapSummaryRow(ApiModel):
    key: str = Field(examples=["WAH", "RAWABI", "scaffolder"])
    label_en: str
    label_ar: str
    counted: int
    met: int
    expiring: int
    gap: int
    due: int
    exempt: int


class GapSummary(ApiModel):
    project_id: uuid.UUID
    as_of: date
    totals: GapSummaryRow
    by_course: list[GapSummaryRow]
    by_contractor: list[GapSummaryRow]
    by_trade: list[GapSummaryRow]


# ---- refresher plan (§3.14, §6.7, GP-3…GP-6) ---------------------------------------------------


class RefresherPlanItem(ApiModel):
    record: TrainingRecordRef
    worker: WorkerRef
    engagement: EngagementRef
    language: WorkerLanguage | None
    course: CourseRef
    valid_until: date
    days_left: int
    refresher_due_from: date
    reason_required: str = Field(
        examples=["matrix MXL-ANIA-EXP-003", "rescue lead on PTW-ANIA-EXP-2026-0413"]
    )
    booked_session: TrainingSessionRef | None
    state: RefresherPlanState


class RefresherPlanPage(Page[RefresherPlanItem]):
    pass


class RetrainingNoteCreate(StrictInput):
    """AT-5 (as Phase 2 IN-5): an HSE Officer / Manager (capability 138 on the project)
    releases the attempts limit for one course; the next nomination is allowed."""

    project_id: uuid.UUID
    course_code: str = Field(pattern=COURSE_CODE)
    note: str = Field(min_length=20, max_length=500, description=P5_HINT)


class RetrainingNoteRead(ApiModel):
    id: uuid.UUID
    worker_id: uuid.UUID
    project_id: uuid.UUID
    course_code: str
    note: str
    created_by: UserRef
    created_at: datetime
