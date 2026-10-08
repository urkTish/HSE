"""Phase 6a schemas — occupational health & medical fitness (spec 6a-occupational-health).

Tiered reads (OH-2): fields above the caller's tier are omitted (`response_model_exclude_unset`
on the routes), so the frontend must treat every tier-2 / tier-3 field as optional. `tier`
on each read says which tier the caller got. No field holds clinical data (P6-2)."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import Field

from app.core.access_enums import DeploymentStatus
from app.core.cert_enums import HookReasonCode, IdMatchResult, NameMatch, VerificationStatus
from app.core.hse_enums import Trade
from app.core.med_enums import (
    AssessmentAction,
    AssessmentSource,
    AssessmentStatus,
    AssessmentType,
    ExaminerAction,
    ExaminerClass,
    ExaminerStatus,
    ExposureGroup,
    FitnessCategory,
    FitnessCheckStatus,
    FitnessLimitingFactor,
    FitnessLineState,
    FitnessOutcome,
    FitnessRequirementState,
    FitnessScanReason,
    FitnessTier,
    FitnessVerificationMethod,
    FitnessVerificationOutcome,
    HoldCancelCode,
    HoldReason,
    HoldSourceType,
    HoldStatus,
    HookBand,
    MedicalAppliesTo,
    MedicalBlacklistScope,
    MedicalImportCode,
    MedicalImportSource,
    MedicalImportStatus,
    MedicalKpiGroupBy,
    MedicalLineSource,
    MedicalProviderAction,
    MedicalProviderKind,
    MedicalProviderStatus,
    ReferralReason,
    ReferralStatus,
    RestrictionCode,
    TypicalTest,
    WorkDuringHoldType,
)
from app.schemas.access_common import WorkerRef
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput
from app.schemas.hse_common import ApiWarning, LabelledCode, UserRef
from app.schemas.kpi import KpiContext, KpiValue

TIER = Field(description="OH-2 tier the caller received for this record.")

# ---- refs ---------------------------------------------------------------------------------------


class FitnessCodeRef(ApiModel):
    code: str = Field(examples=["CSE-ENTRY-FIT"])
    name_en: str
    name_ar: str
    category: FitnessCategory


class MedicalProviderRef(ApiModel):
    id: uuid.UUID
    provider_code: str = Field(examples=["SHIFA-ANIA"])
    legal_name_en: str
    legal_name_ar: str
    kind: MedicalProviderKind


class ExaminerRef(ApiModel):
    id: uuid.UUID
    examiner_no: str = Field(examples=["EXR-0001"])
    full_name_en: str
    full_name_ar: str
    classification: ExaminerClass


# ---- reference lists (§3.10) ---------------------------------------------------------------------


class RestrictionInfo(ApiModel):
    code: RestrictionCode
    label_en: str
    label_ar: str
    value_kind: str | None = Field(
        description="`int_kg` (5–25) for lifting_limit_kg, `text` (≤ 100) for "
        "other_functional, else null."
    )
    negates: list[str] = Field(description="Fitness codes the restriction makes not_met.")
    review_required: bool


class FitnessReference(ApiModel):
    """§3.10 lists with EN/AR labels (codes immutable)."""

    restrictions: list[RestrictionInfo]
    exposure_groups: list[LabelledCode]
    outcomes: list[LabelledCode]
    assessment_types: list[LabelledCode]
    examiner_classes: list[LabelledCode]
    categories: list[LabelledCode]
    hold_reasons: list[LabelledCode]
    referral_reasons: list[LabelledCode]
    typical_tests: list[LabelledCode]
    hints: list[LabelledCode] = Field(
        description="P6-2 / FA-4 / RF-1 free-text hints (code functional_only, referral_note, "
        "no_diagnosis_form)."
    )


# ---- catalogue (§3.1) ----------------------------------------------------------------------------


class FitnessCodeRead(ApiModel):
    id: uuid.UUID
    code: str
    name_en: str
    name_ar: str
    category: FitnessCategory
    validity_months: int
    examiner_classes: list[ExaminerClass]
    provider_kinds: list[MedicalProviderKind]
    typical_tests: list[TypicalTest]
    negated_by: list[RestrictionCode]
    hook_code: bool = Field(description="Used by any Phase 2/3 attach point (HK6-2).")
    in_use: bool = Field(description="Has assessment or plan lines (delete → 409).")
    active: bool
    effective_validity_months: int | None = Field(
        default=None, description="With ?project_id: after the project override (MC-5)."
    )
    critical_on_project: bool | None = None


class FitnessCodeList(ApiModel):
    items: list[FitnessCodeRead]


class FitnessCodeCreate(StrictInput):
    """Capability 147. Code disjoint from Phase 4 PCT and the Phase 5 catalogue (422
    CODE_IN_OTHER_CATALOGUE, MC-2); contractor_clinic only for category general (MC-4)."""

    code: str = Field(pattern=r"^[A-Z0-9-]{2,24}$", examples=["SCBA-FIT"])
    name_en: str = Field(min_length=1, max_length=150)
    name_ar: str = Field(min_length=1, max_length=150)
    category: FitnessCategory
    validity_months: int = Field(ge=1, le=60)
    examiner_classes: list[ExaminerClass] = Field(min_length=1)
    provider_kinds: list[MedicalProviderKind] = Field(min_length=1)
    typical_tests: list[TypicalTest] = Field(default_factory=list)
    active: bool = True


class FitnessCodeUpdate(PatchInput):
    """Tighten only (MC-3): shorter validity, fewer examiner classes / provider kinds, an added
    negating restriction; anything else → 422 CATALOGUE_LOOSENING. Labels are free."""

    name_en: str | None = Field(default=None, min_length=1, max_length=150)
    name_ar: str | None = Field(default=None, min_length=1, max_length=150)
    validity_months: int | None = Field(default=None, ge=1, le=60)
    examiner_classes: list[ExaminerClass] | None = None
    provider_kinds: list[MedicalProviderKind] | None = None
    typical_tests: list[TypicalTest] | None = None
    negated_by: list[RestrictionCode] | None = None
    active: bool | None = None


# ---- providers (§3.2) ----------------------------------------------------------------------------


class MedicalProviderCreate(StrictInput):
    provider_code: str = Field(pattern=r"^[A-Z0-9-]{2,12}$")
    legal_name_en: str = Field(min_length=1, max_length=200)
    legal_name_ar: str = Field(min_length=1, max_length=200)
    kind: MedicalProviderKind
    project_ids: list[uuid.UUID] = Field(default_factory=list, description="Iff site_clinic.")
    contractor_id: uuid.UUID | None = Field(default=None, description="Iff contractor_clinic.")
    moh_licence_no: str = Field(min_length=1, max_length=40)
    licence_valid_until: date
    licence_checked_at: datetime | None = Field(
        default=None, description="MP-2: set when the MOH register was checked (by = caller)."
    )
    verification_domains: list[str] = Field(default_factory=list)
    verification_email: str | None = Field(default=None, max_length=254)
    verification_phone: str | None = Field(default=None, pattern=r"^\+[1-9]\d{6,14}$")
    verification_portal_url: str | None = Field(default=None, max_length=300)


class MedicalProviderUpdate(PatchInput):
    legal_name_en: str | None = Field(default=None, min_length=1, max_length=200)
    legal_name_ar: str | None = Field(default=None, min_length=1, max_length=200)
    project_ids: list[uuid.UUID] | None = None
    moh_licence_no: str | None = Field(default=None, min_length=1, max_length=40)
    licence_valid_until: date | None = None
    licence_checked_at: datetime | None = None
    verification_domains: list[str] | None = None
    verification_email: str | None = Field(default=None, max_length=254)
    verification_phone: str | None = Field(default=None, pattern=r"^\+[1-9]\d{6,14}$")
    verification_portal_url: str | None = Field(default=None, max_length=300)


class MedicalProviderTransition(StrictInput):
    """§4.1: submit (148); approve / return / suspend / reinstate / blacklist / lift_blacklist
    (149). Suspend and blacklist need a reason; blacklist needs a scope (MP-6)."""

    action: MedicalProviderAction
    reason: str | None = Field(default=None, max_length=500)
    blacklist_scope: MedicalBlacklistScope | None = None
    blacklist_from: date | None = None


class MedicalProviderRead(ApiModel):
    id: uuid.UUID
    provider_code: str
    legal_name_en: str
    legal_name_ar: str
    kind: MedicalProviderKind
    project_ids: list[uuid.UUID]
    contractor_id: uuid.UUID | None
    moh_licence_no: str
    licence_valid_until: date
    licence_checked_at: datetime | None
    licence_checked_by: UserRef | None
    verification_domains: list[str]
    verification_email: str | None
    verification_phone: str | None
    verification_portal_url: str | None
    status: MedicalProviderStatus
    status_reason: str | None
    approved_on: date | None
    blacklist_scope: MedicalBlacklistScope | None
    blacklist_from: date | None
    allowed_actions: list[MedicalProviderAction]


class MedicalProviderPage(Page[MedicalProviderRead]):
    pass


# ---- examiners (§3.3) ----------------------------------------------------------------------------


class ExaminerCreate(StrictInput):
    """Capability 148; licence_checked_at required (EX-1); ≥ 1 approved provider."""

    full_name_en: str = Field(min_length=1, max_length=120)
    full_name_ar: str = Field(min_length=1, max_length=120)
    scfhs_licence_no: str = Field(min_length=1, max_length=30)
    classification: ExaminerClass
    licence_valid_until: date
    licence_checked_at: datetime
    provider_ids: list[uuid.UUID] = Field(min_length=1)
    user_id: uuid.UUID | None = Field(
        default=None, description="An oh_practitioner user (unique): a signing physician."
    )


class ExaminerUpdate(PatchInput):
    full_name_en: str | None = Field(default=None, min_length=1, max_length=120)
    full_name_ar: str | None = Field(default=None, min_length=1, max_length=120)
    provider_ids: list[uuid.UUID] | None = None
    user_id: uuid.UUID | None = None


class ExaminerTransition(StrictInput):
    action: ExaminerAction
    reason: str = Field(min_length=1, max_length=500)


class ExaminerRead(ApiModel):
    """Licence fields only for capability 148 holders (row 146: "no licences of examiners")."""

    id: uuid.UUID
    examiner_no: str
    full_name_en: str
    full_name_ar: str
    classification: ExaminerClass
    scfhs_licence_no: str | None = None
    licence_valid_until: date | None = None
    licence_checked_at: datetime | None = None
    provider_ids: list[uuid.UUID]
    user: UserRef | None
    status: ExaminerStatus
    status_reason: str | None = None


class ExaminerPage(Page[ExaminerRead]):
    pass


# ---- requirement plan (§3.4) ---------------------------------------------------------------------


class MedicalPlanLineRead(ApiModel):
    id: uuid.UUID = Field(description="This version.")
    line_id: uuid.UUID = Field(description="Stable across versions.")
    line_no: str = Field(examples=["MRL-ANIA-EXP-002", "MRL-ANIA-EXP-H01"])
    applies_to_kind: MedicalAppliesTo
    applies_to_values: list[str]
    trades: list[Trade]
    code: str
    due_within_days: int
    source: MedicalLineSource
    kpi_counted: bool
    read_only: bool
    hook_key: str | None
    effective_from: date
    effective_to: date | None
    reason: str | None
    counted: int | None = Field(default=None, description="Counted requirements at as_of.")
    met: int | None = None
    gaps: int | None = None


class MedicalPlanRead(ApiModel):
    project_id: uuid.UUID
    as_of: date
    lines: list[MedicalPlanLineRead]
    hook_codes: list[str]


class MedicalPlanLineCreate(StrictInput):
    """Capability 150. Manual kinds: all_workers, trade, exposure_group, adp_category. Applies
    from today (no back-dating, MR-1). due_within_days 0…medical_line_max_due_days and 0 for a
    hook code (422 DUE_DAYS_NOT_ALLOWED)."""

    applies_to_kind: MedicalAppliesTo
    applies_to_values: list[str] = Field(default_factory=list)
    code: str
    due_within_days: int = Field(default=0, ge=0, le=30)


class MedicalPlanLineUpdate(StrictInput):
    """A new version from today. Raising due_within_days or dropping values is loosening: HSE
    Manager with a reason ≥ 20 chars (else 422 PLAN_LOOSENING, MR-5)."""

    applies_to_values: list[str] | None = None
    due_within_days: int | None = Field(default=None, ge=0, le=30)
    reason: str | None = Field(default=None, max_length=300)


class MedicalPlanLineRemove(StrictInput):
    reason: str = Field(min_length=1, max_length=300)


class MedicalPlanLineVersions(ApiModel):
    items: list[MedicalPlanLineRead]


class MedicalExemptionRequest(StrictInput):
    """MR-6: there are no medical exemptions (always 422 EXEMPTION_NOT_ALLOWED)."""

    deployment_id: uuid.UUID | None = None
    line_id: uuid.UUID | None = None
    reason: str | None = None


# ---- health profile (§3.5) -----------------------------------------------------------------------


class HealthProfileHistory(ApiModel):
    value: list[ExposureGroup]
    from_date: date
    to_date: date | None
    by: UserRef | None


class HealthProfileRead(ApiModel):
    deployment_id: uuid.UUID
    project_id: uuid.UUID
    worker: WorkerRef
    trade: Trade
    deployment_status: DeploymentStatus
    exposure_groups: list[ExposureGroup]
    history: list[HealthProfileHistory]


class HealthProfileUpdate(StrictInput):
    """Capability 151 (Contractor HSE Rep: C scope). Applies from today. Removing a group whose
    surveillance line is in gap needs a reason ≥ 20 chars (WP-2)."""

    exposure_groups: list[ExposureGroup]
    reason: str | None = Field(default=None, max_length=300)


# ---- restrictions, lines, conditions ---------------------------------------------------------


class RestrictionInput(StrictInput):
    code: RestrictionCode
    value: int | None = Field(default=None, description="lifting_limit_kg only: 5–25.")
    text: str | None = Field(
        default=None, max_length=100, description="other_functional only: functional wording."
    )


class RestrictionRead(ApiModel):
    code: RestrictionCode
    value: int | None
    text: str | None
    label_en: str
    label_ar: str
    review_required: bool


class FitnessLineInput(StrictInput):
    code: str
    outcome: FitnessOutcome
    restrictions: list[RestrictionInput] = Field(default_factory=list)
    restriction_review_date: date | None = None
    unfit_review_date: date | None = None
    printed_next_due: date | None = None


class FitnessLineRead(ApiModel):
    """Tier 2+: outcome, restrictions and review dates. Tier 1 sees code and validity only."""

    id: uuid.UUID
    code: str
    outcome: FitnessOutcome | None = None
    restrictions: list[RestrictionRead] | None = None
    restriction_review_date: date | None = None
    unfit_review_date: date | None = None
    printed_next_due: date | None = None
    valid_until: date | None = Field(description="Stored org default (§6.1).")
    effective_valid_until: date | None = Field(
        description="On the assessment's project (override applied on read)."
    )
    limiting_factor: FitnessLimitingFactor | None = None
    line_state: FitnessLineState


# ---- assessments (§3.6) --------------------------------------------------------------------------


class FitnessAssessmentCreate(StrictInput):
    """Site clinic (152): saved by the examiner's linked user (with step-up re-auth) → Accepted
    and verified; by another recorder → Awaiting Sign-off. External certificate (153): Draft,
    then Submit with the scan. `id_on_card` is checked through the blind index and never stored
    (FA-10). `historic` (157 only) attaches an already-expired external certificate that is never
    in force (FA-2)."""

    worker_id: uuid.UUID
    assessment_type: AssessmentType
    source: AssessmentSource = AssessmentSource.site_clinic
    provider_id: uuid.UUID
    examiner_id: uuid.UUID
    examined_on: date
    certificate_no: str | None = Field(
        default=None, max_length=40, description="External: as printed; site clinic: system."
    )
    lines: list[FitnessLineInput] = Field(min_length=1, max_length=11)
    related_hold_id: uuid.UUID | None = None
    related_referral_id: uuid.UUID | None = None
    purpose_notice_given: bool
    name_as_printed: str | None = Field(default=None, max_length=120)
    id_on_card: str | None = Field(default=None, max_length=20, description="Never stored.")
    historic: bool = False


class FitnessAssessmentUpdate(PatchInput):
    """Draft / Awaiting Sign-off: any field. Accepted: tier 3 within 24 h only; later → 409
    ASSESSMENT_LOCKED (revoke + new, FA-14)."""

    examined_on: date | None = None
    certificate_no: str | None = Field(default=None, max_length=40)
    lines: list[FitnessLineInput] | None = Field(default=None, min_length=1, max_length=11)
    name_as_printed: str | None = Field(default=None, max_length=120)


class FitnessAssessmentTransition(StrictInput):
    """§4.3. `reason`: return ≥ 10 chars, revoke ≥ 20 chars, reject required.
    `clinical_data_present` must be answered on accept / reject of an external certificate
    (FA-9; true → Rejected CLINICAL_DATA_IN_SCAN)."""

    action: AssessmentAction
    reason: str | None = Field(default=None, max_length=500)
    clinical_data_present: bool | None = None


class RevokeInfo(ApiModel):
    reason: str | None = None
    code: str | None = None
    by: UserRef | None
    at: datetime


class FitnessAssessmentRead(ApiModel):
    id: uuid.UUID
    tier: FitnessTier = TIER
    assessment_no: str
    worker: WorkerRef
    project_id: uuid.UUID
    engagement_short_code: str | None
    source: AssessmentSource
    status: AssessmentStatus
    examined_on: date
    certificate_no: str
    lines: list[FitnessLineRead]
    purpose_notice_given: bool
    historic: bool
    accepted_at: datetime | None
    signed_by: UserRef | None = None
    signed_at: datetime | None = None
    recorded_by: UserRef | None = None
    submitted_by: UserRef | None = None
    submitted_at: datetime | None = None
    has_scan: bool
    # tier 3 (157)
    assessment_type: AssessmentType | None = None
    provider: MedicalProviderRef | None = None
    examiner: ExaminerRef | None = None
    verification_status: VerificationStatus | None = None
    verification_due_on: date | None = None
    related_hold_no: str | None = None
    related_referral_no: str | None = None
    name_as_printed: str | None = None
    name_match: NameMatch | None = None
    id_match_result: IdMatchResult | None = None
    clinical_data_present: bool | None = None
    status_reason: str | None = None
    reviewed_by: UserRef | None = None
    reviewed_at: datetime | None = None
    revoke: RevokeInfo | None = None
    allowed_actions: list[AssessmentAction] = Field(default_factory=list)
    warnings: list[ApiWarning] = Field(default_factory=list)


class FitnessAssessmentPage(Page[FitnessAssessmentRead]):
    pass


class FitnessVerificationCreate(StrictInput):
    """Capability 154; verifier ≠ submitter and not employed by the worker's employer (422
    SOD_CONFLICT, FV-2). `channel_used` must be the provider's registered portal, a domain
    email or phone (422 CHANNEL_NOT_REGISTERED); the server never fetches URLs (FV-3)."""

    method: FitnessVerificationMethod
    channel_used: str = Field(min_length=1, max_length=200)
    outcome: FitnessVerificationOutcome
    reference: str = Field(min_length=1, max_length=100)
    performed_at: datetime | None = Field(default=None, description="UTC; default now.")


class FitnessVerificationRead(ApiModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    assessment_no: str
    method: FitnessVerificationMethod
    channel_used: str
    outcome: FitnessVerificationOutcome
    reference: str
    performed_by: UserRef | None
    performed_at: datetime
    counts_as_verification: bool
    verification_status_after: VerificationStatus


class FitnessVerificationList(ApiModel):
    items: list[FitnessVerificationRead]


class FitnessScanUrlRequest(StrictInput):
    """P6-5 (capability 160): a reason is required (422 without)."""

    reason: FitnessScanReason
    reason_text: str | None = Field(default=None, max_length=300, description="For `other`.")


# ---- worker fitness (tiered status per code) -------------------------------------------------


class WorkerFitnessItem(ApiModel):
    """HK6-6 result per code at `as_of`. Tier 1: status, valid_until and the generic text;
    tier 2: + outcome, restrictions / conditions, review dates; tier 3: + reason_code and the
    governing assessment."""

    code: str
    name_en: str
    name_ar: str
    required: bool = Field(description="Required by the plan for the deployment.")
    status: FitnessCheckStatus
    band: HookBand
    text_en: str
    text_ar: str
    valid_until: date | None
    hard_stop: bool | None = None
    outcome: FitnessOutcome | None = None
    restrictions: list[RestrictionRead] | None = None
    restriction_review_date: date | None = None
    unfit_review_date: date | None = None
    reason_code: HookReasonCode | None = None
    assessment_no: str | None = None


class WorkerFitnessRead(ApiModel):
    worker: WorkerRef
    project_id: uuid.UUID
    as_of: datetime
    tier: FitnessTier = TIER
    on_hold: bool | None = Field(default=None, description="Tier 2+ (FH-6).")
    items: list[WorkerFitnessItem]


class FitnessHoldBrief(ApiModel):
    hold_no: str
    status: HoldStatus
    reason: HoldReason
    started_at: datetime
    released_at: datetime | None


class FitnessReferralBrief(ApiModel):
    referral_no: str
    status: ReferralStatus
    reason: ReferralReason
    raised_at: datetime
    assessed_at: datetime | None


class FitnessDataSubjectReport(ApiModel):
    """P6-9 (capability 165): handed over by the OH Practitioner; audited `export` with purpose
    data_subject_request."""

    worker: WorkerRef
    generated_at: datetime
    assessments: list[FitnessAssessmentRead]
    holds: list[FitnessHoldBrief]
    referrals: list[FitnessReferralBrief]


# ---- requirements and gaps (§6.3) ----------------------------------------------------------------


class FitnessRequirementRead(ApiModel):
    code: str
    line_nos: list[str]
    kpi_counted: bool
    hook_code: bool
    critical: bool
    applies_from: date
    due_date: date
    state: FitnessRequirementState
    counted: bool
    valid_until: date | None
    outcome: FitnessOutcome | None = None
    reason_code: HookReasonCode | None = None


class FitnessRequirementList(ApiModel):
    deployment_id: uuid.UUID
    worker: WorkerRef
    as_of: date
    tier: FitnessTier = TIER
    items: list[FitnessRequirementRead]


class FitnessGapRow(ApiModel):
    deployment_id: uuid.UUID
    worker: WorkerRef
    engagement_short_code: str | None
    trade: Trade
    code: str
    due_date: date
    hook_code: bool
    critical: bool
    outcome_category: str | None = Field(
        default=None, description="Tier 2+: missing / expired / unfit / restriction / hold …"
    )
    reason_code: HookReasonCode | None = Field(default=None, description="Tier 3 only.")


class FitnessGapPage(Page[FitnessGapRow]):
    as_of: date
    tier: FitnessTier


# ---- holds (§3.7) and referrals (§3.8) -----------------------------------------------------------


class WorkDuringHoldRead(ApiModel):
    event_type: WorkDuringHoldType
    ref: str | None
    at: datetime


class FitnessHoldCreate(StrictInput):
    """Manual hold (capability 159): reason_text ≥ 20 chars in functional wording."""

    worker_id: uuid.UUID
    reason_text: str = Field(min_length=1, max_length=300)


class FitnessHoldCancel(StrictInput):
    reason: str = Field(min_length=1, max_length=500)


class FitnessHoldRead(ApiModel):
    """Tier 2: existence, dates, work during hold; tier 3: + reason, source and texts."""

    id: uuid.UUID
    tier: FitnessTier = TIER
    hold_no: str
    worker: WorkerRef
    project_id: uuid.UUID
    status: HoldStatus
    started_at: datetime
    released_at: datetime | None
    cancelled_at: datetime | None
    hold_hours: str = Field(description="(released_at or now) − started_at, 1 dp (§6.4).")
    compliant: bool | None = Field(description="Released holds: no work during the hold.")
    work_during_hold: list[WorkDuringHoldRead]
    reason: HoldReason | None = None
    source_type: HoldSourceType | None = None
    source_ref: str | None = None
    reason_text: str | None = None
    release_assessment_no: str | None = None
    cancel_code: HoldCancelCode | None = None
    cancel_reason: str | None = None


class FitnessHoldPage(Page[FitnessHoldRead]):
    pass


class FitnessReferralCreate(StrictInput):
    """Capability 158 within RF-2 scope. `note`: describe what you saw, not a diagnosis."""

    worker_id: uuid.UUID
    reason: ReferralReason
    note: str | None = Field(default=None, max_length=300)
    remove_from_work: bool


class FitnessReferralCancel(StrictInput):
    reason: str = Field(min_length=1, max_length=500)


class FitnessReferralRead(ApiModel):
    """Existence and raiser are personal (tier 1 context); reason and note tier 3."""

    id: uuid.UUID
    tier: FitnessTier = TIER
    referral_no: str
    worker: WorkerRef
    project_id: uuid.UUID
    status: ReferralStatus
    remove_from_work: bool
    raised_by: UserRef | None
    raised_at: datetime
    due_at: datetime
    overdue: bool
    assessed_at: datetime | None
    on_time: bool | None
    hold_no: str | None = None
    assessment_no: str | None = None
    reason: ReferralReason | None = None
    note: str | None = None
    cancel_reason: str | None = None
    incident_draft_link: str | None = Field(
        default=None, description="RF-6: Phase 1 incident draft link (heat_illness_episode)."
    )
    warnings: list[ApiWarning] = Field(default_factory=list)


class FitnessReferralPage(Page[FitnessReferralRead]):
    pass


# ---- settings (§3.12) ----------------------------------------------------------------------------


class MedicalSettingsRead(ApiModel):
    project_id: uuid.UUID
    medical_register_from: date | None
    fitness_validity_months: dict[str, int]
    medical_hook_transition_days: int
    medical_hook_critical_transition_days: int
    medical_hook_critical_codes: list[str]
    unverified_fitness_acceptance_hours: int
    fitness_verification_due_days: int
    referral_assessment_hours: int
    signoff_due_hours: int
    assessment_backdate_max_days: int
    restriction_review_max_days: int
    unfit_review_max_days: int
    medical_line_max_due_days: int
    rtw_hold_case_categories: list[str]
    heat_illness_natures: list[str]
    exposure_group_trade_defaults: dict[str, list[str]]
    medical_compliance_warning_pct: str
    health_cell_min: int
    fitness_scan_retention_months: int
    fitness_record_retention_years: int
    surveillance_record_retention_years: int
    worker_purpose_notice_version: str
    alert_schedule_long_days: list[int]
    medical_hooks_enabled: bool
    updated_at: datetime | None


class MedicalSettingsUpdate(PatchInput):
    """Capability 164; "Allowed" ranges only (§3.12; tighten-only keys → 422
    SETTING_LOOSENING; medical_register_from may only move earlier → 422
    MEDICAL_REGISTER_LATER)."""

    medical_register_from: date | None = None
    fitness_validity_months: dict[str, int] | None = None
    medical_hook_transition_days: int | None = Field(default=None, ge=0, le=30)
    medical_hook_critical_transition_days: int | None = Field(default=None, ge=0, le=7)
    medical_hook_critical_codes: list[str] | None = None
    unverified_fitness_acceptance_hours: int | None = Field(default=None, ge=0, le=24)
    fitness_verification_due_days: int | None = Field(default=None, ge=1, le=14)
    referral_assessment_hours: int | None = Field(default=None, ge=4, le=72)
    signoff_due_hours: int | None = Field(default=None, ge=24, le=72)
    assessment_backdate_max_days: int | None = Field(default=None, ge=0, le=14)
    restriction_review_max_days: int | None = Field(default=None, ge=30, le=180)
    unfit_review_max_days: int | None = Field(default=None, ge=14, le=180)
    medical_line_max_due_days: int | None = Field(default=None, ge=0, le=30)
    rtw_hold_case_categories: list[str] | None = None
    heat_illness_natures: list[str] | None = None
    exposure_group_trade_defaults: dict[str, list[str]] | None = None
    medical_compliance_warning_pct: str | None = Field(default=None, pattern=r"^\d{1,3}(\.\d)?$")
    health_cell_min: int | None = Field(default=None, ge=5, le=10)
    fitness_scan_retention_months: int | None = Field(default=None, ge=6, le=24)
    fitness_record_retention_years: int | None = Field(default=None, ge=5, le=30)
    surveillance_record_retention_years: int | None = Field(default=None, ge=10, le=40)
    worker_purpose_notice_version: str | None = Field(default=None, min_length=1, max_length=40)


class MedicalSettingsUpdateResult(ApiModel):
    settings: MedicalSettingsRead
    changed: list[str]


class MedicalHooksEnableRequest(StrictInput):
    """HK6-1 (capability 164): needs medical_register_from ≤ today (422
    MEDICAL_REGISTER_NOT_LIVE) and an Approved site or external clinic serving the project (422
    NO_MEDICAL_PROVIDER). Show `GET /projects/{id}/hook-readiness?kind=medical_fitness` first."""

    registered_on: date | None = Field(default=None, description="Default today (local).")


# ---- imports (§3.11) -----------------------------------------------------------------------------


class MedicalImportIssue(ApiModel):
    code: MedicalImportCode
    level: str = Field(examples=["error", "warning"])
    message_en: str
    message_ar: str
    field: str | None = None
    meta: dict[str, Any] | None = None


class MedicalImportRow(ApiModel):
    row_no: int
    worker_no: str | None
    id_masked: str | None
    certificate_no: str | None
    code: str | None
    status: str = Field(examples=["ok", "warning", "error"])
    issues: list[MedicalImportIssue]


class MedicalImportBatchRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    source: MedicalImportSource
    provider_id: uuid.UUID | None
    file_name: str
    file_sha256: str
    status: MedicalImportStatus
    counts: dict[str, int]
    file_issues: list[MedicalImportIssue]
    rows: list[MedicalImportRow]
    uploaded_by: UserRef | None
    created_at: datetime
    expires_at: datetime
    committed_at: datetime | None
    committed_assessment_nos: list[str]


class MedicalImportBatchPage(Page[MedicalImportBatchRead]):
    pass


# ---- KPIs (§6.6, MK-1…MK-5) ----------------------------------------------------------------------


class MedicalBreakdownRow(ApiModel):
    """Codes, categories, contractor short codes, trades, months or gap reasons as keys; cells
    of 1–4 persons are shown as "<5" (MK-3)."""

    key: str
    label_en: str
    label_ar: str
    value: str | None
    display: str
    numerator: str | None = None
    denominator: str | None = None
    suppressed: bool = False


class MedicalBreakdown(ApiModel):
    metric: str = Field(examples=["K-89"])
    group_by: MedicalKpiGroupBy
    rows: list[MedicalBreakdownRow]


class MedicalKpiResponse(ApiModel):
    """GET /kpi/occupational-health: K-89…K-96 for the /kpi filters plus `trade`, `code` and
    `code_category`. Multi-value metrics use `components` (K-91 gaps · workers · hook_gaps; K-93
    active · overdue). Viewer/Client and tier-1 roles get MK-3 suppression ("<5")."""

    context: KpiContext
    metrics: list[KpiValue]
    breakdowns: list[MedicalBreakdown]


class MedicalCheckItem(ApiModel):
    """§8.5 / AC133: the tier-1 Fitness section of the Phase 4 VF-9 and Phase 5 CK5-2 views."""

    code: str
    cleared: bool
