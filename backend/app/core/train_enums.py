"""Phase 5 enumerations — training certificates (spec 5-training v1.0).

Exported into the OpenAPI contract so the frontend gets typed unions. Course codes are plain
strings (the org-wide catalogue `GET /training-courses` can be extended by the HSE Manager);
fixed lists (CAT-C, ACB, MR, SV, states, codes) are enums here.
"""

from enum import StrEnum

# ---------------------------------------------------------------------------------------------
# Course catalogue (§3.1, §3.15 CAT-C)
# ---------------------------------------------------------------------------------------------


class CourseCategory(StrEnum):
    """List CAT-C (§3.15)."""

    induction_link = "induction_link"
    awareness = "awareness"
    high_risk_task = "high_risk_task"
    ptw_role = "ptw_role"
    emergency_response = "emergency_response"
    aviation_security = "aviation_security"
    airside_operations = "airside_operations"
    electrical = "electrical"
    professional_qualification = "professional_qualification"


class DeliveryMode(StrEnum):
    """§3.1 delivery_modes / §3.6 delivery_mode (CC-5)."""

    classroom = "classroom"
    practical = "practical"
    blended = "blended"
    e_learning = "e_learning"


class AccreditationBodyCode(StrEnum):
    """List ACB — accreditation / awarding bodies (§3.15, VERIFY names)."""

    srca = "srca"
    aha = "aha"
    erc = "erc"
    gaca_avsec = "gaca_avsec"
    airport_operator = "airport_operator"
    nebosh = "nebosh"
    iosh = "iosh"
    osha_otc = "osha_otc"
    tvtc = "tvtc"
    client_approved = "client_approved"
    other = "other"


class MatrixRole(StrEnum):
    """List MR — designations on the training profile (§3.15)."""

    fire_warden = "fire_warden"
    first_aider = "first_aider"
    fire_watch = "fire_watch"


class SessionVoidReason(StrEnum):
    """List SV (§3.15)."""

    trainer_not_competent = "trainer_not_competent"
    attendance_falsified = "attendance_falsified"
    assessment_compromised = "assessment_compromised"
    provider_misconduct = "provider_misconduct"
    other = "other"


# ---------------------------------------------------------------------------------------------
# Providers and trainers (§3.2, §3.3, §4.1, §4.2, PV-3)
# ---------------------------------------------------------------------------------------------


class TrainingProviderKind(StrEnum):
    internal = "internal"
    contractor_internal = "contractor_internal"
    external = "external"


class TrainingProviderStatus(StrEnum):
    """§4.1."""

    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    suspended = "suspended"
    blacklisted = "blacklisted"


class TrainingProviderAction(StrEnum):
    """§4.1 transitions (`POST /training-providers/{id}/transitions`)."""

    submit = "submit"  # 127: Draft → Pending Approval
    approve = "approve"  # 128
    return_ = "return"  # 128: Pending Approval → Draft (comment)
    suspend = "suspend"  # 128: Approved → Suspended (reason)
    reinstate = "reinstate"  # 128: Suspended → Approved (reason)
    blacklist = "blacklist"  # 128: Approved/Suspended → Blacklisted (reason, scope)
    lift_blacklist = "lift_blacklist"  # 128: Blacklisted → Suspended


class ProviderBlacklistScope(StrEnum):
    """PV-6."""

    all_records = "all_records"
    issued_from = "issued_from"


class ProviderUnacceptableReason(StrEnum):
    """PV-3: `meta.reason` of 422 PROVIDER_NOT_ACCEPTABLE (also an ErrorCode each)."""

    PROVIDER_NOT_APPROVED = "PROVIDER_NOT_APPROVED"
    PROVIDER_SUSPENDED = "PROVIDER_SUSPENDED"
    PROVIDER_BLACKLISTED = "PROVIDER_BLACKLISTED"
    ACCREDITATION_INVALID = "ACCREDITATION_INVALID"
    ACCREDITATION_SCOPE = "ACCREDITATION_SCOPE"
    INTERNAL_NOT_ALLOWED = "INTERNAL_NOT_ALLOWED"
    CONTRACTOR_DELIVERY_NOT_ALLOWED = "CONTRACTOR_DELIVERY_NOT_ALLOWED"
    NOT_OWN_TREE = "NOT_OWN_TREE"


class TrainerRole(StrEnum):
    trainer = "trainer"
    assessor = "assessor"


class TrainerAuthorisationStatus(StrEnum):
    """§4.2."""

    active = "active"
    suspended = "suspended"
    withdrawn = "withdrawn"
    expired = "expired"


class TrainerAuthorisationAction(StrEnum):
    suspend = "suspend"
    reinstate = "reinstate"
    withdraw = "withdraw"


# ---------------------------------------------------------------------------------------------
# Matrix, profiles, requirements, exemptions (§3.4, §3.5, §3.10, §3.11)
# ---------------------------------------------------------------------------------------------


class MatrixAppliesTo(StrEnum):
    """§3.4 applies_to_kind."""

    all_workers = "all_workers"
    trade = "trade"
    matrix_role = "matrix_role"
    zone = "zone"
    pass_category = "pass_category"
    adp_category = "adp_category"
    crew_role = "crew_role"
    appointment_function = "appointment_function"


class MatrixLevel(StrEnum):
    mandatory = "mandatory"
    recommended = "recommended"


class MatrixLineSource(StrEnum):
    """§3.4: hook lines are derived from the Phase 2/3 attach points (read-only, MX-2)."""

    manual = "manual"
    hook = "hook"


class RequirementState(StrEnum):
    """§3.10 / §6.2 state of one requirement at as_of."""

    met = "met"
    expiring = "expiring"
    due = "due"
    gap = "gap"
    exempt = "exempt"


class ExemptionStatus(StrEnum):
    active = "active"
    withdrawn = "withdrawn"
    expired = "expired"


class ProfileField(StrEnum):
    """§3.5 training-profile history field names."""

    matrix_roles = "matrix_roles"
    work_zone_ids = "work_zone_ids"


# ---------------------------------------------------------------------------------------------
# Sessions, nominations, attendance (§3.6, §3.7, §4.4, §4.5)
# ---------------------------------------------------------------------------------------------


class SessionStatus(StrEnum):
    """§4.4."""

    draft = "draft"
    scheduled = "scheduled"
    in_progress = "in_progress"
    delivered = "delivered"
    closed = "closed"
    cancelled = "cancelled"
    voided = "voided"


class SessionAction(StrEnum):
    """`POST /training-sessions/{id}/transitions` (132). Close (135) and void (145) have their
    own endpoints; in_progress / delivered are set by the system (or SS-5 record_delivered)."""

    schedule = "schedule"  # Draft → Scheduled (SS-1…SS-4)
    record_delivered = "record_delivered"  # Draft → Delivered (SS-5, HSE Officer / Manager)
    cancel = "cancel"  # Draft / Scheduled → Cancelled (reason)


class NominationStatus(StrEnum):
    """§3.7 / §4.5 attendance status."""

    nominated = "nominated"
    attended = "attended"
    partial = "partial"
    absent = "absent"
    withdrawn = "withdrawn"


class UnderstoodLanguage(StrEnum):
    """AT-6."""

    session_language = "session_language"
    interpreter = "interpreter"
    none = "none"


class AttendanceResult(StrEnum):
    """AT-1…AT-4."""

    pending = "pending"
    passed = "passed"
    failed = "failed"
    incomplete = "incomplete"


class PracticalResult(StrEnum):
    pass_ = "pass"
    fail = "fail"


# ---------------------------------------------------------------------------------------------
# Records and verification (§3.8, §3.9, §4.6)
# ---------------------------------------------------------------------------------------------


class TrainingRecordSource(StrEnum):
    session = "session"
    external_certificate = "external_certificate"
    import_ = "import"


class TrainingRecordStatus(StrEnum):
    """§4.6. `historic` records (TR-3, already expired) are a flag, never in force."""

    draft = "draft"
    submitted = "submitted"
    accepted = "accepted"
    rejected = "rejected"
    superseded = "superseded"
    suspended = "suspended"
    revoked = "revoked"
    expired = "expired"


class TrainingRecordAction(StrEnum):
    """`POST /training-records/{id}/transitions`."""

    submit = "submit"  # 137: Draft → Submitted (scan; TR-1…TR-6)
    return_ = "return"  # 138: Submitted → Draft (comment ≥ 10)
    accept = "accept"  # 138: Submitted → Accepted (reviewer ≠ submitter)
    reject = "reject"  # 138: Submitted → Rejected (reason)
    suspend = "suspend"  # 140: Accepted → Suspended (reason ≥ 20; hard stop)
    reinstate = "reinstate"  # 140: Suspended → Accepted (reason)
    revoke = "revoke"  # 140: Accepted / Suspended → Revoked (reason ≥ 20; hard stop)


class TrainingStatusReason(StrEnum):
    """Why a record was rejected / revoked / suspended / superseded (system or user)."""

    verification_failed = "verification_failed"
    provider_blacklisted = "provider_blacklisted"
    session_voided = "session_voided"
    hse_suspension = "hse_suspension"
    hse_revocation = "hse_revocation"
    document_review = "document_review"
    newer_record = "newer_record"
    other = "other"


class TrainingLimitingFactor(StrEnum):
    """§6.1: the term that gives valid_until (printed_expiry on a tie)."""

    printed_expiry = "printed_expiry"
    course_validity = "course_validity"
    project_override = "project_override"
    none = "none"


class TrainingVerificationMethod(StrEnum):
    """§3.9. `original_sighted` is recorded but never verifies (VR-3); `session_record` is the
    system method of session-issued records (TR-14)."""

    provider_portal = "provider_portal"
    provider_qr_url = "provider_qr_url"
    provider_email = "provider_email"
    provider_phone = "provider_phone"
    provider_register_file = "provider_register_file"
    awarding_body_portal = "awarding_body_portal"
    original_sighted = "original_sighted"
    session_record = "session_record"


class TrainingVerificationOutcome(StrEnum):
    confirmed = "confirmed"
    not_found = "not_found"
    details_differ = "details_differ"
    revoked_by_provider = "revoked_by_provider"
    no_response = "no_response"


# ---------------------------------------------------------------------------------------------
# Refresher plan (§3.14, §6.7)
# ---------------------------------------------------------------------------------------------


class RefresherPlanState(StrEnum):
    not_booked = "not_booked"
    booked_in_time = "booked_in_time"
    booked_late = "booked_late"


# ---------------------------------------------------------------------------------------------
# Imports (§3.13, §5.12)
# ---------------------------------------------------------------------------------------------


class TrainingImportTemplate(StrEnum):
    training_records = "training_records"
    session_attendance = "session_attendance"


class TrainingImportSource(StrEnum):
    contractor_file = "contractor_file"
    provider_register_file = "provider_register_file"


class TrainingImportCode(StrEnum):
    """IM5-7 validation codes (errors block the row; a file-level error blocks the file)."""

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
    E11 = "E11"
    E12 = "E12"
    W01 = "W01"
    W02 = "W02"
    W03 = "W03"
    W04 = "W04"
    W05 = "W05"
    W06 = "W06"


class TrainingImportStatus(StrEnum):
    """§4.8 (as Phase 1 §4.1)."""

    validated = "validated"
    committed = "committed"
    discarded = "discarded"
    expired = "expired"


# ---------------------------------------------------------------------------------------------
# Competence check (CK5) and KPIs (§6.8, TK-4)
# ---------------------------------------------------------------------------------------------


class TrainingCheckStatus(StrEnum):
    """CK5-1 colour of a TR QR check: in force (green), expired (amber), revoked (red)."""

    in_force = "in_force"
    expired = "expired"
    not_in_force = "not_in_force"
    revoked = "revoked"


class TrainingKpiGroupBy(StrEnum):
    """TK-4 / §8.1 breakdowns of /kpi/training and T17."""

    course = "course"
    course_category = "course_category"
    contractor = "contractor"
    trade = "trade"
    provider = "provider"
    source = "source"
    month = "month"


class TrainingHoursSource(StrEnum):
    """TH-6: the K-37 numerator source of a day / period."""

    register = "register"
    daily_returns = "daily_returns"
    mixed = "mixed"


class DataSubjectPurpose(StrEnum):
    """P5-9 per-worker training report purpose."""

    data_subject_request = "data_subject_request"
