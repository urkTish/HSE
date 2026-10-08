"""Phase 6a enumerations — occupational health & medical fitness (spec 6a-occupational-health
v1.0, §3.10 lists and §4 states).

Exported into the OpenAPI contract so the frontend gets typed unions. Fitness codes are plain
strings (the org-wide catalogue `GET /fitness-codes` can be extended by the HSE Manager); fixed
lists (EXC, FCAT, OUT, AT6, RC, EG, HR, RR, TST) and states are enums here.
"""

from enum import StrEnum

# ---- catalogue (§3.1, §3.10) ---------------------------------------------------------------------


class FitnessCategory(StrEnum):
    """List FCAT."""

    general = "general"
    task = "task"
    surveillance = "surveillance"


class ExaminerClass(StrEnum):
    """List EXC. A nurse may record but never signs a line (EX-3)."""

    occupational_physician = "occupational_physician"
    physician = "physician"
    nurse = "nurse"


class MedicalProviderKind(StrEnum):
    """§3.2 kind; also the `provider_kinds` a fitness code allows (MC-4)."""

    site_clinic = "site_clinic"
    external_clinic = "external_clinic"
    contractor_clinic = "contractor_clinic"


class TypicalTest(StrEnum):
    """List TST (informational only; results are never stored, P6-2)."""

    history_questionnaire = "history_questionnaire"
    vision_acuity = "vision_acuity"
    colour_vision = "colour_vision"
    depth_perception = "depth_perception"
    audiometry = "audiometry"
    spirometry = "spirometry"
    chest_xray = "chest_xray"
    cardio_exam = "cardio_exam"
    blood_pressure = "blood_pressure"
    balance_vertigo_screen = "balance_vertigo_screen"
    claustrophobia_screen = "claustrophobia_screen"
    respirator_questionnaire = "respirator_questionnaire"
    blood_count = "blood_count"
    musculoskeletal_exam = "musculoskeletal_exam"


class FitnessOutcome(StrEnum):
    """List OUT (per fitness code)."""

    fit = "fit"
    fit_with_restrictions = "fit_with_restrictions"
    temporarily_unfit = "temporarily_unfit"
    permanently_unfit = "permanently_unfit"


class RestrictionCode(StrEnum):
    """List RC — functional restrictions (what the person must not do, never why)."""

    no_work_at_height = "no_work_at_height"
    no_confined_space = "no_confined_space"
    no_driving = "no_driving"
    no_plant_operation = "no_plant_operation"
    no_respirator_use = "no_respirator_use"
    no_heat_exposure = "no_heat_exposure"
    no_noise_exposure = "no_noise_exposure"
    no_radiation_work = "no_radiation_work"
    lifting_limit_kg = "lifting_limit_kg"
    no_night_work = "no_night_work"
    no_lone_work = "no_lone_work"
    light_duties_only = "light_duties_only"
    requires_corrective_lenses = "requires_corrective_lenses"
    other_functional = "other_functional"


class ExposureGroup(StrEnum):
    """List EG (describes the job, not the person's health: personal, not sensitive)."""

    noise_85 = "noise_85"
    silica_rcs = "silica_rcs"
    ionising_radiation = "ionising_radiation"
    heat_outdoor = "heat_outdoor"


# ---- providers (§3.2, §4.1) and examiners (§3.3, §4.2) ---------------------------------------


class MedicalProviderStatus(StrEnum):
    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    suspended = "suspended"
    blacklisted = "blacklisted"


class MedicalProviderAction(StrEnum):
    """§4.1: submit (148); approve / return / suspend / reinstate / blacklist / lift_blacklist
    (149)."""

    submit = "submit"
    approve = "approve"
    return_ = "return"
    suspend = "suspend"
    reinstate = "reinstate"
    blacklist = "blacklist"
    lift_blacklist = "lift_blacklist"


class MedicalBlacklistScope(StrEnum):
    """MP-6."""

    all_records = "all_records"
    issued_from = "issued_from"


class MedicalProviderUnacceptableReason(StrEnum):
    """MP-3 `meta.reason` of 422 MEDICAL_PROVIDER_NOT_ACCEPTABLE (also ErrorCodes)."""

    PROVIDER_NOT_APPROVED = "PROVIDER_NOT_APPROVED"
    PROVIDER_SUSPENDED = "PROVIDER_SUSPENDED"
    PROVIDER_BLACKLISTED = "PROVIDER_BLACKLISTED"
    LICENCE_INVALID = "LICENCE_INVALID"
    PROVIDER_KIND_NOT_ALLOWED = "PROVIDER_KIND_NOT_ALLOWED"
    NOT_PROJECT_CLINIC = "NOT_PROJECT_CLINIC"
    NOT_OWN_TREE = "NOT_OWN_TREE"


class ExaminerStatus(StrEnum):
    active = "active"
    suspended = "suspended"
    withdrawn = "withdrawn"
    expired = "expired"


class ExaminerAction(StrEnum):
    """§4.2 (capability 149)."""

    suspend = "suspend"
    reinstate = "reinstate"
    withdraw = "withdraw"


# ---- requirement plan (§3.4) and health profile (§3.5) ---------------------------------------


class MedicalAppliesTo(StrEnum):
    all_workers = "all_workers"
    trade = "trade"
    exposure_group = "exposure_group"
    adp_category = "adp_category"
    zone = "zone"
    project_hook = "project_hook"
    crew_role = "crew_role"
    operator_binding = "operator_binding"


class MedicalLineSource(StrEnum):
    """`manual` (capability 150), `hook` (H lines, kpi_counted) or `enforcement` (E lines,
    enforcement-only, kpi_counted = false). Derived lines are read-only (MR-2)."""

    manual = "manual"
    hook = "hook"
    enforcement = "enforcement"


class FitnessRequirementState(StrEnum):
    """§6.3 (first match wins: met / expiring, due, gap)."""

    met = "met"
    expiring = "expiring"
    due = "due"
    gap = "gap"


# ---- assessments (§3.6, §4.3) ------------------------------------------------------------------


class AssessmentType(StrEnum):
    """List AT6."""

    pre_placement = "pre_placement"
    periodic = "periodic"
    return_to_work = "return_to_work"
    referral = "referral"
    change_of_task = "change_of_task"
    post_exposure = "post_exposure"
    exit = "exit"


class AssessmentSource(StrEnum):
    site_clinic = "site_clinic"
    external_certificate = "external_certificate"
    import_ = "import"


class AssessmentStatus(StrEnum):
    draft = "draft"
    awaiting_signoff = "awaiting_signoff"
    submitted = "submitted"
    accepted = "accepted"
    rejected = "rejected"
    revoked = "revoked"


class AssessmentAction(StrEnum):
    """§4.3. `sign` (site clinic: the examiner's linked user, re-auth), `return` (from Awaiting
    Sign-off or Submitted, comment ≥ 10 chars), `submit` (external, 153), `accept` / `reject`
    (154, ≠ submitter), `revoke` (157, reason ≥ 20 chars)."""

    sign = "sign"
    return_ = "return"
    submit = "submit"
    accept = "accept"
    reject = "reject"
    revoke = "revoke"


class FitnessLineState(StrEnum):
    """§3.6a line_state (derived on save of any assessment of the worker, §6.2)."""

    pending = "pending"
    governing = "governing"
    superseded = "superseded"
    revoked = "revoked"
    rejected = "rejected"


class FitnessLimitingFactor(StrEnum):
    """§6.1 (ties: restriction_review, printed_next_due, code_validity, project_override)."""

    restriction_review = "restriction_review"
    printed_next_due = "printed_next_due"
    code_validity = "code_validity"
    project_override = "project_override"


class FitnessVerificationMethod(StrEnum):
    """FV-3 channels; `site_clinic_record` (FV-6) and `clinic_register_file` (IM6-3) are set by
    the system."""

    clinic_portal = "clinic_portal"
    clinic_email = "clinic_email"
    clinic_phone = "clinic_phone"
    site_clinic_record = "site_clinic_record"
    clinic_register_file = "clinic_register_file"


class FitnessVerificationOutcome(StrEnum):
    """FV-4 / FV-5."""

    confirmed = "confirmed"
    not_found = "not_found"
    details_differ = "details_differ"
    revoked_by_clinic = "revoked_by_clinic"
    no_response = "no_response"


class FitnessScanReason(StrEnum):
    """P6-5 reason to open a certificate scan (capability 160)."""

    verification = "verification"
    authority_request = "authority_request"
    gosi_claim = "gosi_claim"
    legal = "legal"
    other = "other"


# ---- holds (§3.7, §4.4) and referrals (§3.8, §4.5) ----------------------------------------------


class HoldReason(StrEnum):
    """List HR."""

    rtw_after_injury = "rtw_after_injury"
    heat_illness = "heat_illness"
    referral = "referral"
    manual = "manual"


class HoldSourceType(StrEnum):
    injury_case = "injury_case"
    referral = "referral"
    manual = "manual"


class HoldStatus(StrEnum):
    active = "active"
    released = "released"
    cancelled = "cancelled"


class HoldCancelCode(StrEnum):
    """FH-4 system cancellation codes."""

    source_voided = "source_voided"
    source_reclassified = "source_reclassified"


class WorkDuringHoldType(StrEnum):
    """FH-8 detections."""

    gate_entry = "gate_entry"
    crew_present = "crew_present"
    rtw_before_clearance = "rtw_before_clearance"


class ReferralReason(StrEnum):
    """List RR."""

    observed_unwell = "observed_unwell"
    heat_illness_episode = "heat_illness_episode"
    self_reported = "self_reported"
    return_after_absence = "return_after_absence"
    post_incident_no_injury = "post_incident_no_injury"
    certificate_restriction = "certificate_restriction"
    supervisor_concern = "supervisor_concern"
    other = "other"


class ReferralStatus(StrEnum):
    open = "open"
    assessed = "assessed"
    cancelled = "cancelled"


# ---- tiers, hook results, imports, KPIs --------------------------------------------------------


class FitnessTier(StrEnum):
    """OH-2 access tier of the caller for the record (each includes the one before it)."""

    status = "status"  # tier 1, capability 155
    functional = "functional"  # tier 2, capability 156
    clinical_admin = "clinical_admin"  # tier 3, capability 157


class FitnessCheckStatus(StrEnum):
    """HK6-6 result status (raw provider result, before the hook-policy stage)."""

    met = "met"
    expiring = "expiring"
    not_met = "not_met"
    unknown_code = "unknown_code"


class MedicalImportSource(StrEnum):
    """§3.11: clinic_register_file (157 holders) or contractor_file (Contractor HSE Rep)."""

    clinic_register_file = "clinic_register_file"
    contractor_file = "contractor_file"


class MedicalImportStatus(StrEnum):
    uploaded = "uploaded"
    validated = "validated"
    committed = "committed"
    discarded = "discarded"
    expired = "expired"


class MedicalImportCode(StrEnum):
    """IM6-5 validation codes."""

    E01 = "E01"
    E02 = "E02"
    E03 = "E03"
    E04 = "E04"
    E05 = "E05"
    E06 = "E06"
    E07 = "E07"
    E08 = "E08"
    E09 = "E09"
    E10 = "E10"
    W01 = "W01"
    W02 = "W02"
    W03 = "W03"
    W04 = "W04"


class MedicalKpiGroupBy(StrEnum):
    """MK-4 / §6.6 breakdowns (cells of 1–4 persons shown as "<5", MK-3)."""

    code = "code"
    code_category = "code_category"
    contractor = "contractor"
    trade = "trade"
    month = "month"
    gap_reason = "gap_reason"


class HookBand(StrEnum):
    """Display band of a medical hook result for callers below tier 2 (HK6-7)."""

    cleared = "cleared"
    not_eligible = "not_eligible"
    check_due = "check_due"
    restriction_applies = "restriction_applies"
