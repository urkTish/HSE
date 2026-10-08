"""Training records, external certificates, verification, certificate print / QR, the worker
passport and the per-worker data-subject report (spec 5-training §3.8, §3.9, §4.6, TR-1…TR-16,
VR-1…VR-8, CK5-1, P5-3…P5-9)."""

import uuid
from datetime import date, datetime

from pydantic import Field

from app.core.cert_enums import (
    IdMatchResult,
    NameMatch,
    ScanReason,
    VerificationDifference,
    VerificationStatus,
)
from app.core.train_enums import (
    DataSubjectPurpose,
    PracticalResult,
    TrainingLimitingFactor,
    TrainingRecordAction,
    TrainingRecordSource,
    TrainingRecordStatus,
    TrainingStatusReason,
    TrainingVerificationMethod,
    TrainingVerificationOutcome,
)
from app.schemas.access_common import WorkerRef
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput
from app.schemas.hse_common import ApiWarning, EngagementRef, UserRef
from app.schemas.personnel_certs import IdOnCard
from app.schemas.training_common import (
    COURSE_CODE,
    NOT_ACCEPTED_AR,
    NOT_ACCEPTED_EN,
    P5_HINT,
    TR_QR_PATTERN,
    CourseRef,
    Hours,
    ScorePct,
    TrainingProviderRef,
    TrainingSessionRef,
    TrainingValidity,
)
from app.schemas.training_matrix import RequirementStatus


class ExternalRecordFields(StrictInput):
    course_code: str = Field(pattern=COURSE_CODE, examples=["FIRST-AID"])
    provider_id: uuid.UUID
    certificate_no: str = Field(
        min_length=1,
        max_length=40,
        description="Unique per (provider, course) (409 CERT_EXISTS); same number for another "
        "worker → 409 CERT_NO_REUSED on save and at Submit, HSE Officers alerted (TR-5).",
    )
    completed_on: date = Field(description="≤ today (TR-3).")
    printed_expiry: date | None = Field(default=None, description="> completed_on.")
    theory_score_pct: ScorePct | None = None
    practical_result: PracticalResult | None = None
    hours: Hours | None = Field(default=None, description="Required when project_sponsored.")
    project_sponsored: bool = False
    sponsoring_project_id: uuid.UUID | None = Field(
        default=None, description="Required iff project_sponsored (TH-3)."
    )
    name_as_printed: str = Field(min_length=1, max_length=120)
    scan_attachment_id: uuid.UUID | None = Field(
        default=None,
        description="Owner training_record_scan (pdf/jpg/png ≤ 5 MB, personal bucket); "
        "required to Submit.",
    )
    provider_verification_url: str | None = Field(default=None, max_length=300)
    prerequisite_evidenced_on_certificate: bool = Field(
        default=False, description="TR-9 reviewer tick (capability 138 only)."
    )


class TrainingRecordCreate(ExternalRecordFields):
    """Capability 137 → Draft (external certificate). TR-1 holder scope (404 outside C scope);
    TR-2 provider acceptable on completed_on (422 PROVIDER_NOT_ACCEPTABLE with meta.reason);
    TR-3 already expired → 422 RECORD_ALREADY_EXPIRED unless `historic` (capability 138);
    TR-6 ID match (422 CERT_ID_MISMATCH, never stored); TR-11 renews_only (422
    REFRESHER_NOT_ELIGIBLE); induction_link → 422 INDUCTION_OWNED_BY_PHASE2."""

    worker_id: uuid.UUID
    project_id: uuid.UUID = Field(description="Project it is submitted on (review queue).")
    id_on_card: IdOnCard
    historic: bool = Field(default=False, description="TR-3: capability 138; never in force.")


class TrainingRecordUpdate(PatchInput):
    """Draft: any field (sending `id_on_card` re-runs TR-6). Accepted records after 24 h: HSE
    Manager only with `reason` (TR-12; 409 RECORD_EDIT_LOCKED otherwise)."""

    non_nullable = frozenset(
        {"course_code", "provider_id", "certificate_no", "completed_on", "name_as_printed"}
    )

    course_code: str | None = Field(default=None, pattern=COURSE_CODE)
    provider_id: uuid.UUID | None = None
    certificate_no: str | None = Field(default=None, min_length=1, max_length=40)
    completed_on: date | None = None
    printed_expiry: date | None = None
    theory_score_pct: ScorePct | None = None
    practical_result: PracticalResult | None = None
    hours: Hours | None = None
    project_sponsored: bool | None = None
    sponsoring_project_id: uuid.UUID | None = None
    name_as_printed: str | None = Field(default=None, min_length=1, max_length=120)
    scan_attachment_id: uuid.UUID | None = None
    provider_verification_url: str | None = Field(default=None, max_length=300)
    prerequisite_evidenced_on_certificate: bool | None = None
    id_on_card: IdOnCard | None = None
    reason: str | None = Field(default=None, max_length=500, description=P5_HINT)


class TrainingRecordTransition(StrictInput):
    """§4.6: submit (137; scan, TR-1…TR-6) · return (138; reason ≥ 10) · accept (138; reviewer
    ≠ submitter — 422 SOD_CONFLICT; name match none needs `identity_confirmed_by_provider` —
    422 NAME_MISMATCH_CONFIRMATION; TR-9 prerequisites — 422 TRAINING_PREREQUISITE) · reject
    (138; reason) · suspend (140; reason ≥ 20; hard stop) · reinstate (140; reason) · revoke
    (140; reason ≥ 20; hard stop). Contractor HSE Reps never accept (TR-7)."""

    action: TrainingRecordAction
    reason: str | None = Field(default=None, max_length=500, description=P5_HINT)
    reason_code: TrainingStatusReason | None = None
    identity_confirmed_by_provider: bool = False


class TrainingRecordRead(ApiModel):
    """Needs capability 136 and 46 for names. Absent / null by role: scores and practical
    result (AT-7, P5-5); `status_reason_text` and verification-failure detail only for HSE
    Manager / Officer — others see `not_accepted_message_*` (P5-4). The ID number is never
    returned (only `id_match_result`)."""

    id: uuid.UUID
    record_no: str = Field(examples=["TRR-000812"])
    project_id: uuid.UUID | None = Field(description="Project it was issued / submitted on.")
    worker: WorkerRef
    engagement: EngagementRef | None
    course: CourseRef
    source: TrainingRecordSource
    provider: TrainingProviderRef
    session: TrainingSessionRef | None
    certificate_no: str = Field(examples=["TRC-ANIA-EXP-2026-00911"])
    completed_on: date
    printed_expiry: date | None
    valid_until: date | None = Field(description="Stored (org default, §6.1).")
    limiting_factor: TrainingLimitingFactor
    validity: TrainingValidity = Field(description="Effective on ?project_id (or own project).")
    theory_score_pct: ScorePct | None = None
    practical_result: PracticalResult | None = None
    hours: Hours | None
    project_sponsored: bool
    sponsoring_project_id: uuid.UUID | None
    name_as_printed: str | None
    name_match: NameMatch | None
    id_match_result: IdMatchResult | None
    identity_confirmed_by_provider: bool
    has_scan: bool
    provider_verification_url: str | None
    has_qr: bool = Field(description="Session records carry a TR QR (TR-14).")
    status: TrainingRecordStatus
    status_reason: TrainingStatusReason | None
    status_reason_text: str | None = Field(default=None, description="HSE roles only (P5-4).")
    not_accepted_message_en: str | None = Field(default=None, examples=[NOT_ACCEPTED_EN])
    not_accepted_message_ar: str | None = Field(default=None, examples=[NOT_ACCEPTED_AR])
    verification_status: VerificationStatus
    verification_due_on: date | None
    historic: bool
    prerequisite_evidenced_on_certificate: bool
    superseded_by_id: uuid.UUID | None
    submitted_by: UserRef | None
    submitted_at: datetime | None
    reviewed_by: UserRef | None
    reviewed_at: datetime | None
    warnings: list[ApiWarning] = Field(
        description="W01 shortened by course validity, W02 name match, CERT_NO_REUSED, "
        "VERIFICATION_URL_FOREIGN_DOMAIN, LANGUAGE_MISMATCH, TRAINING_UNVERIFIED window."
    )
    prompts: list[ApiWarning] = Field(
        default_factory=list,
        description="Returned once after an action, e.g. CONSIDER_PROVIDER_REVIEW / "
        "CONSIDER_WORKER_BAN after a failed verification (VR-6: never automatic).",
    )
    allowed_actions: list[TrainingRecordAction]
    created_at: datetime
    updated_at: datetime


class TrainingRecordListItem(ApiModel):
    id: uuid.UUID
    record_no: str
    worker: WorkerRef
    engagement: EngagementRef | None
    course_code: str
    course_name_en: str
    course_name_ar: str
    provider_code: str
    source: TrainingRecordSource
    certificate_no: str
    completed_on: date
    valid_until: date | None = Field(description="Effective on the listed project.")
    limiting_factor: TrainingLimitingFactor
    days_left: int | None
    in_force: bool
    expiring: bool
    status: TrainingRecordStatus
    verification_status: VerificationStatus
    historic: bool


class TrainingRecordPage(Page[TrainingRecordListItem]):
    pass


class TrainingRecordPreviewRequest(ExternalRecordFields):
    """Form helper (no ID typed, nothing stored): validity (§6.1), name match, provider
    acceptability (PV-3), refresher eligibility (TR-11), prerequisites (TR-9)."""

    worker_id: uuid.UUID
    project_id: uuid.UUID


class TrainingRecordPreview(ApiModel):
    validity: TrainingValidity
    name_match: NameMatch
    provider_acceptable: bool
    provider_reason: str | None
    errors: list[ApiWarning]
    warnings: list[ApiWarning]


class TrainingScanUrlRequest(StrictInput):
    """P5-3: capability 139 with a reason; writes `sensitive_field_read` (fields_read
    ["training_scan"]). URL ≤ 5 min."""

    reason: ScanReason
    reason_text: str | None = Field(
        default=None, max_length=200, description="Required when reason = other."
    )


# ---- verification (§3.9, VR) ------------------------------------------------------------------


class TrainingVerificationCreate(StrictInput):
    """Capability 138; verifier ≠ submitter and not employed by the holder's employer (422
    SOD_CONFLICT, VR-2). `channel_used` registered on the provider or the awarding body (ACB)
    (422 CHANNEL_NOT_REGISTERED, VR-3); `session_record` is system-only (422). Evidence
    (owner training_verification_evidence) required except provider_phone (`reference` ≥ 20
    chars). The server never opens external URLs (VR-4)."""

    method: TrainingVerificationMethod
    channel_used: str = Field(min_length=1, max_length=200, examples=["verify.hayat-test.example"])
    outcome: TrainingVerificationOutcome
    differences: list[VerificationDifference] = Field(
        default_factory=list, description="Required iff outcome = details_differ."
    )
    differences_text: str | None = Field(default=None, max_length=300)
    reference: str = Field(min_length=1, max_length=100)
    evidence_attachment_id: uuid.UUID | None = None
    performed_at: datetime | None = Field(default=None, description="UTC; default now.")


class TrainingVerificationRead(ApiModel):
    """Outcome not_found / details_differ is sensitive (P5-1): only HSE Manager / Officer see
    `outcome` and `differences`; others get null and `counts_as_verification`."""

    id: uuid.UUID
    record_id: uuid.UUID
    record_no: str
    certificate_no: str
    method: TrainingVerificationMethod
    channel_used: str
    outcome: TrainingVerificationOutcome | None
    differences: list[VerificationDifference]
    differences_text: str | None
    reference: str
    evidence_attachment_id: uuid.UUID | None
    performed_by: UserRef | None = Field(description="Null for system (session_record, VR-8).")
    performed_at: datetime
    counts_as_verification: bool = Field(
        description="False for original_sighted and no_response (VR-3, VR-5)."
    )
    verification_status_after: VerificationStatus


class TrainingVerificationList(ApiModel):
    items: list[TrainingVerificationRead]


class TrainingVerificationLogItem(TrainingVerificationRead):
    project_id: uuid.UUID
    worker_no: str
    course_code: str
    provider_code: str


class TrainingVerificationLogPage(Page[TrainingVerificationLogItem]):
    pass


# ---- certificate print and QR (TR-14, CK5-1) ---------------------------------------------------


class TrainingCertificatePrint(ApiModel):
    """Bilingual certificate data for session-issued records (TR-14). No ID number, score or
    photo (P5-6). Encode `qr_payload` as a QR code; external records → 404 (no QR)."""

    record_id: uuid.UUID
    record_no: str
    certificate_no: str
    worker_no: str
    worker_name_en: str
    worker_name_ar: str | None
    course_code: str
    course_name_en: str
    course_name_ar: str
    completed_on: date
    valid_until: date | None
    provider_code: str
    provider_name_en: str
    provider_name_ar: str
    trainer_names: list[str]
    session_no: str
    qr_payload: str = Field(
        pattern=TR_QR_PATTERN,
        examples=["HSE2:TR:q8Xb2mJf0Q9nZr4tYc1wKA"],
        description="`HSE2:TR:<22-char token>` — never an access token (gates answer "
        "TOKEN_UNKNOWN, GC-3).",
    )
    printed_ref: str = Field(examples=["TRC-ANIA-EXP-2026-00911"])
    issued_at: datetime


class CertificateReissue(StrictInput):
    """Rotate the TR token (old one shows REVOKED / ملغاة); capability 138."""

    reason: str = Field(min_length=10, max_length=300, description=P5_HINT)


# ---- passport and data-subject report ----------------------------------------------------------


class PassportEntry(ApiModel):
    record_id: uuid.UUID
    record_no: str
    course: CourseRef
    provider_code: str
    source: TrainingRecordSource
    completed_on: date
    valid_until: date | None
    in_force: bool
    status: TrainingRecordStatus
    has_qr: bool


class TrainingPassport(ApiModel):
    """Per-worker passport (printable): records across projects (TR-16) with the
    effective validity on ?project_id; no ID, score or scan (P5-6)."""

    worker: WorkerRef
    as_of: date
    project_id: uuid.UUID | None
    entries: list[PassportEntry]
    requirements: list[RequirementStatus] = Field(
        description="On ?project_id: the worker's requirement status there."
    )


class TrainingReportAttendance(ApiModel):
    session_no: str
    course_code: str
    first_day: date
    last_day: date
    status: str
    minutes: int
    theory_score_pct: ScorePct | None
    practical_result: PracticalResult | None
    result: str


class DataSubjectReport(ApiModel):
    """P5-9: capability 144 with purpose data_subject_request (HSE Manager); audited as an
    export. Contains records, sessions, scores and gaps of one worker — never ID numbers or
    scans."""

    worker: WorkerRef
    purpose: DataSubjectPurpose
    generated_at: datetime
    records: list[TrainingRecordListItem]
    attendances: list[TrainingReportAttendance]
    requirements: list[RequirementStatus]
