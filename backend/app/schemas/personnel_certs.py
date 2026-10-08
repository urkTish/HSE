"""Personnel certificates, scans, certification bans and the blacklist register (spec
4-third-party-cert §3.9, §3.12, §4.4, §4.7, §6.2, PC-1…PC-13, BL-1…BL-5, P4-1…P4-6)."""

import uuid
from datetime import date, datetime

from pydantic import Field

from app.core.access_enums import WorkerIdType, WorkerLanguage
from app.core.cert_enums import (
    BanReason,
    BanStatus,
    BlacklistSubject,
    CertificateStatus,
    CertLevel,
    CertLimitingFactor,
    CertSource,
    CertStatusReason,
    EquipmentCertCategory,
    IdMatchResult,
    NameMatch,
    ScanReason,
    ScanSide,
    VerificationStatus,
)
from app.schemas.access_common import WorkerRef
from app.schemas.cert_common import (
    CERT_TYPE_CODE,
    AllowedCertAction,
    CertValidity,
    PersonnelLimitation,
    PersonnelLimitationRead,
    Tonnes,
    TpiRef,
)
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput
from app.schemas.hse_common import ApiWarning, DecimalStr, EngagementRef, UserRef

NOT_ACCEPTED_EN = "Certification not accepted on this organisation's projects"
NOT_ACCEPTED_AR = "الشهادة غير مقبولة في مشاريع هذه الجهة"


class IdOnCard(StrictInput):
    """PC-3: the ID number printed on the card, typed for matching. **Never stored**: the
    server compares HMAC(id_type ‖ number ‖ passport_country) with the worker's blind index
    (and previous IDs). A different number → 422 CERT_ID_MISMATCH (nothing stored; audit
    shows the masked value). `shown` = false → id_match `not_shown`."""

    shown: bool
    id_type: WorkerIdType | None = None
    id_number: str | None = Field(default=None, min_length=6, max_length=15)
    passport_country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")


class Assessment(StrictInput):
    theory_on: date | None = None
    practical_on: date | None = None
    language: WorkerLanguage | None = None


class AssessmentRead(ApiModel):
    theory_on: date | None
    practical_on: date | None
    language: WorkerLanguage | None


class PersonnelCertFields(StrictInput):
    cert_type: str = Field(
        pattern=CERT_TYPE_CODE, examples=["CRANE-OPERATOR"], description="List PCT code."
    )
    tpi_id: uuid.UUID
    cert_no: str = Field(
        min_length=1,
        max_length=40,
        description="Unique per (TPI, cert_type) (409 CERT_EXISTS); another worker → 422 "
        "CERT_NO_REUSED (PC-2).",
    )
    issued_on: date
    printed_expiry: date | None = Field(default=None, description="Null → PCT cap (§6.2).")
    scope_categories: list[EquipmentCertCategory] = Field(
        default_factory=list, description="Operator types: ≥ 1, ⊆ the type's allowed set."
    )
    max_capacity_t: Tonnes | None = Field(default=None, description="Null = unlimited.")
    level: CertLevel | None = Field(
        default=None, description="RIGGER / ROPE-ACCESS 1-3; RADIOGRAPHER II/III; SCAFFOLDER."
    )
    limitations: list[PersonnelLimitation] = Field(default_factory=list)
    medical_restriction_on_card: bool = Field(
        default=False,
        description="True when the card states any health-related restriction. The detail "
        "is NOT recorded (P4-6).",
    )
    name_as_printed: str = Field(min_length=1, max_length=120)
    assessment: Assessment | None = None
    scan_front_attachment_id: uuid.UUID | None = Field(
        default=None,
        description="Owner personnel_cert_scan (jpg/png/pdf ≤ 5 MB, personal bucket); "
        "required to Submit.",
    )
    scan_back_attachment_id: uuid.UUID | None = None
    tpi_verification_url: str | None = Field(default=None, max_length=300)


class PersonnelCertCreate(PersonnelCertFields):
    """Capability 118 → Draft. PC-1 holder scope (Contractor HSE Rep: workers deployed in
    their C scope; 404 otherwise); BL-4 banned holder → 422 HOLDER_BANNED; PC-5 TPI
    acceptability (422 TPI_NOT_ACCEPTABLE); PC-7 scope / level (422 CERT_SCOPE_MISMATCH,
    LEVEL_NOT_ACCEPTED); PC-3 ID match (422 CERT_ID_MISMATCH)."""

    worker_id: uuid.UUID
    id_on_card: IdOnCard


class PersonnelCertUpdate(PatchInput):
    """Draft only. Sending `id_on_card` re-runs the PC-3 match."""

    non_nullable = frozenset({"cert_type", "tpi_id", "cert_no", "issued_on", "name_as_printed"})

    cert_type: str | None = Field(default=None, pattern=CERT_TYPE_CODE)
    tpi_id: uuid.UUID | None = None
    cert_no: str | None = Field(default=None, min_length=1, max_length=40)
    issued_on: date | None = None
    printed_expiry: date | None = None
    scope_categories: list[EquipmentCertCategory] | None = None
    max_capacity_t: Tonnes | None = None
    level: CertLevel | None = None
    limitations: list[PersonnelLimitation] | None = None
    medical_restriction_on_card: bool | None = None
    name_as_printed: str | None = Field(default=None, min_length=1, max_length=120)
    assessment: Assessment | None = None
    scan_front_attachment_id: uuid.UUID | None = None
    scan_back_attachment_id: uuid.UUID | None = None
    tpi_verification_url: str | None = Field(default=None, max_length=300)
    id_on_card: IdOnCard | None = None


class PersonnelCertRead(ApiModel):
    """Needs capabilities 117 and 46 (403 otherwise; Viewer/Client never, AC107). Served with
    absent keys: `medical_restriction_on_card` and `restriction_reviewed_at` only with
    capability 119; `status_reason_text` and verification-failure detail only for HSE
    Manager / Officer (P4-4) — other roles see `not_accepted_message_*` instead. The ID number
    is never returned (only `id_match_result`)."""

    id: uuid.UUID
    record_no: str = Field(examples=["PCR-000019"])
    project_id: uuid.UUID = Field(description="Project it was submitted on.")
    worker: WorkerRef
    engagement: EngagementRef | None = Field(
        default=None, description="The worker's deployment engagement on the project."
    )
    cert_type: str
    cert_type_label_en: str
    cert_type_label_ar: str
    tpi: TpiRef
    cert_no: str
    issued_on: date
    printed_expiry: date | None
    validity: CertValidity
    scope_categories: list[EquipmentCertCategory]
    max_capacity_t: DecimalStr | None
    level: CertLevel | None
    limitations: list[PersonnelLimitationRead]
    medical_restriction_on_card: bool | None = Field(
        default=None, description="Absent without capability 119 (sensitive, P4-1)."
    )
    restriction_reviewed_at: datetime | None = Field(
        default=None, description="PC-13; absent without capability 119."
    )
    name_as_printed: str
    id_match_result: IdMatchResult
    name_match: NameMatch
    identity_confirmed_by_tpi: bool
    assessment: AssessmentRead | None
    has_scan_front: bool
    has_scan_back: bool
    tpi_verification_url: str | None
    status: CertificateStatus
    status_reason: CertStatusReason | None
    status_reason_text: str | None = Field(default=None, description="HSE roles only (P4-4).")
    not_accepted_message_en: str | None = Field(
        default=None,
        description="Contractor roles, for rejected / revoked / banned (BL-5, P4-4).",
        examples=[NOT_ACCEPTED_EN],
    )
    not_accepted_message_ar: str | None = Field(default=None, examples=[NOT_ACCEPTED_AR])
    verification_status: VerificationStatus
    verification_due_on: date | None
    source: CertSource
    superseded_by_id: uuid.UUID | None
    submitted_by: UserRef | None
    submitted_at: datetime | None
    reviewed_by: UserRef | None
    reviewed_at: datetime | None
    warnings: list[ApiWarning] = Field(
        description="W01 capped, W02 name match partial/none, CERT_NO_REUSED, "
        "VERIFICATION_URL_FOREIGN_DOMAIN, CERT_UNVERIFIED window."
    )
    prompts: list[ApiWarning] = Field(
        default_factory=list,
        description="Returned once after an action, e.g. CONSIDER_WORKER_BAN after an HSE "
        "suspension (PC-11: no ban is automatic).",
    )
    allowed_actions: list[AllowedCertAction]
    created_at: datetime
    updated_at: datetime


class PersonnelCertListItem(ApiModel):
    id: uuid.UUID
    record_no: str
    worker: WorkerRef
    engagement: EngagementRef | None
    cert_type: str
    tpi_code: str
    cert_no: str
    issued_on: date
    valid_until: date | None
    limiting_factor: CertLimitingFactor | None
    days_left: int | None
    in_force: bool
    expiring: bool
    status: CertificateStatus
    verification_status: VerificationStatus
    level: CertLevel | None
    source: CertSource


class PersonnelCertPage(Page[PersonnelCertListItem]):
    pass


class PersonnelCertPreviewRequest(PersonnelCertFields):
    """Form helper: validity (§6.2), name match (PC-4), scope checks; no ID typed here and
    nothing stored."""

    worker_id: uuid.UUID


class PersonnelCertPreview(ApiModel):
    validity: CertValidity
    name_match: NameMatch
    tpi_acceptable: bool
    tpi_reason: str | None
    errors: list[ApiWarning]
    warnings: list[ApiWarning]


class ScanUrlRequest(StrictInput):
    """P4-3: capability 119 with a reason; writes `sensitive_field_read` (fields_read
    ["cert_scan"]). The URL lives ≤ 5 min."""

    side: ScanSide
    reason: ScanReason
    reason_text: str | None = Field(
        default=None, max_length=200, description="Required when reason = other."
    )


class RestrictionReviewRequest(StrictInput):
    """PC-13: an HSE Officer records "restriction reviewed" (no medical detail)."""

    note: str | None = Field(default=None, max_length=200, description="No medical detail.")


class WorkerCertLine(ApiModel):
    id: uuid.UUID
    cert_type: str
    cert_type_label_en: str
    cert_type_label_ar: str
    cert_no: str
    tpi_code: str
    valid_until: date | None
    in_force: bool
    not_in_force_reason: str | None
    status: CertificateStatus
    level: CertLevel | None
    scope_categories: list[EquipmentCertCategory]


class WorkerCertificates(ApiModel):
    """GET /workers/{id}/certificates (117 + 46): per-type overview on the worker page, plus
    PC-12 trade requirement status."""

    worker: WorkerRef
    certificates: list[WorkerCertLine]
    trade_requirement: str | None = Field(description="Mapped PCT code for the worker's trade.")
    trade_requirement_met: bool | None
    banned: bool = Field(description="Active certification ban (any scope).")
    ban_message_en: str | None = Field(description="BL-5 text for contractor roles.")
    ban_message_ar: str | None


# ---- certification bans (§3.12, BL-4/BL-5) ------------------------------------------------------


class CertificationBanCreate(StrictInput):
    """Capability 115 (HSE Manager only). Never changes worker status (PC-11)."""

    worker_id: uuid.UUID
    scope_all: bool = True
    cert_types: list[str] = Field(
        default_factory=list, description="PCT codes when scope_all = false."
    )
    reason_code: BanReason
    reason_text: str = Field(
        min_length=20, max_length=500, description="Facts only; no criminal-law conclusions."
    )
    from_date: date


class CertificationBanLift(StrictInput):
    reason: str = Field(min_length=10, max_length=500)


class CertificationBanRead(ApiModel):
    """Sensitive (P4-1): full detail for HSE Manager / Officer only. Contractor roles get
    `reason_code` / `reason_text` null and the BL-5 message."""

    id: uuid.UUID
    worker: WorkerRef
    scope_all: bool
    cert_types: list[str]
    reason_code: BanReason | None
    reason_text: str | None
    from_date: date
    review_due_on: date
    status: BanStatus
    message_en: str = Field(examples=[NOT_ACCEPTED_EN])
    message_ar: str = Field(examples=[NOT_ACCEPTED_AR])
    created_by: UserRef | None
    lifted_at: datetime | None
    lifted_by: UserRef | None
    lift_reason: str | None
    created_at: datetime


class CertificationBanPage(Page[CertificationBanRead]):
    pass


class BlacklistRegisterRow(ApiModel):
    """§8.4 blacklist and ban register (HSE Manager / Officer; contractor reps see
    'not accepted' only)."""

    subject: BlacklistSubject
    subject_id: uuid.UUID
    ref: str = Field(examples=["SH-TH-02", "WKR-000022", "QUICKCERT"])
    label_en: str
    label_ar: str
    reason_code: str | None
    from_date: date
    review_due_on: date | None
    status: str = Field(examples=["active", "lifted", "blacklisted"])
    project_ids: list[uuid.UUID]


class BlacklistRegister(ApiModel):
    items: list[BlacklistRegisterRow]
