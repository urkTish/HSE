"""Equipment inspection certificates and lines (spec 4-third-party-cert §3.6, §4.4, §6.1,
EC-1…EC-14, CF-1/CF-3, VF-1…VF-7)."""

import uuid
from datetime import date, datetime

from pydantic import Field

from app.core.cert_enums import (
    CertificateStatus,
    CertInspectionType,
    CertLimitingFactor,
    CertSource,
    CertStatusReason,
    DefectCategory,
    LiftingGearColour,
    LineResult,
    VerificationStatus,
)
from app.schemas.cert_common import (
    AllowedCertAction,
    CertValidity,
    DefectRef,
    EquipmentLimitation,
    EquipmentLimitationRead,
    EquipmentRef,
    Pct1,
    Tonnes,
    TpiRef,
)
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput
from app.schemas.hse_common import ApiWarning, DecimalStr, UserRef


class LoadTest(StrictInput):
    """EC-7: performed with percent_of_swl ≥ 100.0 for initial, after_configuration_change and
    structural after_repair lines of cranes, hoists, mast climbers, BMUs and man-baskets."""

    performed: bool
    percent_of_swl: Pct1 | None = None
    test_weight_t: Tonnes | None = None


class LoadTestRead(ApiModel):
    performed: bool
    percent_of_swl: DecimalStr | None
    test_weight_t: DecimalStr | None


class LineDefectInput(StrictInput):
    """DF-2: each creates a Defect with the TPI's category and due date."""

    category: DefectCategory
    description_en: str = Field(min_length=1, max_length=1000)
    description_ar: str | None = Field(default=None, max_length=1000)
    tpi_due_date: date | None = Field(default=None, description="B only.")


class CertLineInput(StrictInput):
    equipment_id: uuid.UUID
    serial_as_printed: str = Field(
        min_length=1, max_length=40, description="Normalised must equal the item's (EC-5)."
    )
    result: LineResult
    swl_t: Tonnes | None = Field(
        default=None, description="Lifting categories; ≤ rated_capacity_t (EC-8)."
    )
    configuration_ref: str | None = Field(
        default=None, max_length=100, description="Tower cranes / hoists (CF-3)."
    )
    load_test: LoadTest | None = None
    structural_repair: bool = Field(
        default=False, description="after_repair with a structural repair (EC-7)."
    )
    lifting_duty_certified: bool = Field(
        default=False, description="EC-9: excavator / loader / telehandler lifting duty."
    )
    colour_code: LiftingGearColour | None = Field(
        default=None, description="When the colour scheme is enabled (EC-12)."
    )
    limitations: list[EquipmentLimitation] = Field(default_factory=list)
    defects: list[LineDefectInput] = Field(default_factory=list)


class EquipmentCertificateFields(StrictInput):
    tpi_id: uuid.UUID
    cert_no: str = Field(
        min_length=1,
        max_length=40,
        description="As printed; unique per TPI (409 CERT_EXISTS; another item → "
        "CERT_NO_REUSED, EC-1).",
        examples=["NKTI-TEST-26-0929"],
    )
    inspection_type: CertInspectionType
    inspected_on: date
    issued_on: date = Field(description="inspected_on ≤ issued_on ≤ today (EC-2).")
    printed_next_due: date | None = Field(
        default=None, description="Last valid day as printed; null = not printed (§6.1)."
    )
    inspector_name: str = Field(min_length=1, max_length=120)
    inspector_staff_no: str | None = Field(
        default=None, max_length=30, description="TPI staff number, never a national ID."
    )
    scan_attachment_id: uuid.UUID | None = Field(
        default=None,
        description="Owner equipment_certificate_scan (PDF ≤ 20 MB); required to Submit.",
    )
    tpi_verification_url: str | None = Field(
        default=None,
        max_length=300,
        description="From the TPI's QR. A host outside the TPI's verification_domains gives "
        "warning VERIFICATION_URL_FOREIGN_DOMAIN (VF-4).",
    )
    configuration_event_id: uuid.UUID | None = Field(
        default=None,
        description="CF-1: the configuration event this certificate clears (inspected on or "
        "after occurred_at, else 422 INSPECTION_BEFORE_EVENT).",
    )


class EquipmentCertificateCreate(EquipmentCertificateFields):
    """Capability 106 → Draft (`historic` = true: capability 107, EC-2 attach as history,
    never in force). Lines: one per item; every item must have a non-cancelled deployment on
    the project. TP-4/TP-5 acceptability (422 TPI_NOT_ACCEPTABLE, meta.reason), TP-6 (422
    TPI_NOT_INDEPENDENT), EC-2 (422 CERT_ALREADY_EXPIRED unless historic), EC-5, EC-7, EC-8
    are checked at create and again at Submit."""

    lines: list[CertLineInput] = Field(min_length=1, max_length=500)
    historic: bool = False


class EquipmentCertificateUpdate(PatchInput):
    """Draft only (409 INVALID_TRANSITION otherwise). `lines` replaces all lines."""

    non_nullable = frozenset(
        {"tpi_id", "cert_no", "inspection_type", "inspected_on", "issued_on", "inspector_name"}
    )

    tpi_id: uuid.UUID | None = None
    cert_no: str | None = Field(default=None, min_length=1, max_length=40)
    inspection_type: CertInspectionType | None = None
    inspected_on: date | None = None
    issued_on: date | None = None
    printed_next_due: date | None = None
    inspector_name: str | None = Field(default=None, min_length=1, max_length=120)
    inspector_staff_no: str | None = Field(default=None, max_length=30)
    scan_attachment_id: uuid.UUID | None = None
    tpi_verification_url: str | None = Field(default=None, max_length=300)
    configuration_event_id: uuid.UUID | None = None
    lines: list[CertLineInput] | None = Field(default=None, min_length=1, max_length=500)


class CertLineRead(ApiModel):
    id: uuid.UUID
    equipment: EquipmentRef
    serial_as_printed: str
    result: LineResult
    swl_t: DecimalStr | None
    configuration_ref: str | None
    load_test: LoadTestRead | None
    structural_repair: bool
    lifting_duty_certified: bool
    colour_code: LiftingGearColour | None
    limitations: list[EquipmentLimitationRead]
    defects: list[DefectRef]
    validity: CertValidity = Field(description="§6.1 valid_until / limiting_factor; §6.6.")
    superseded_by_line_id: uuid.UUID | None
    suspended_for_configuration: bool


class EquipmentCertificateRead(ApiModel):
    """`inspector_name` is personal: present for callers with capability 105 on the project
    (the sticker check and gate never show it, VF-8)."""

    id: uuid.UUID
    project_id: uuid.UUID
    cert_no: str
    tpi: TpiRef
    inspection_type: CertInspectionType
    inspected_on: date
    issued_on: date
    printed_next_due: date | None
    inspector_name: str | None
    inspector_staff_no: str | None
    scan_attachment_id: uuid.UUID | None
    tpi_verification_url: str | None
    configuration_event_id: uuid.UUID | None
    status: CertificateStatus
    status_reason: CertStatusReason | None
    status_reason_text: str | None
    verification_status: VerificationStatus
    verification_due_on: date | None = Field(
        description="Submitted date + verification_due_days (local)."
    )
    source: CertSource
    submitted_by: UserRef | None
    submitted_at: datetime | None
    reviewed_by: UserRef | None
    reviewed_at: datetime | None
    accepted_at: datetime | None
    verified_at: datetime | None
    in_force_from: datetime | None
    valid_until: date | None = Field(description="Latest line valid_until.")
    lines: list[CertLineRead]
    warnings: list[ApiWarning] = Field(
        description="Review warnings: W01 shortened by interval, CONFIGURATION_MISMATCH "
        "(CF-3), CERT_NO_REUSED, VERIFICATION_URL_FOREIGN_DOMAIN, TPI_ACCREDITATION_LAPSED "
        "(TP-7 note), CERT_UNVERIFIED (VF-1 window)."
    )
    allowed_actions: list[AllowedCertAction]
    created_at: datetime
    updated_at: datetime


class EquipmentCertificateListItem(ApiModel):
    id: uuid.UUID
    cert_no: str
    tpi_code: str
    inspection_type: CertInspectionType
    inspected_on: date
    status: CertificateStatus
    verification_status: VerificationStatus
    line_count: int
    equipment_tags: list[str] = Field(description="First 5 tags.")
    categories: list[str]
    valid_until: date | None
    limiting_factor: CertLimitingFactor | None
    in_force: bool
    source: CertSource
    submitted_at: datetime | None


class EquipmentCertificatePage(Page[EquipmentCertificateListItem]):
    pass


class EquipmentCertPreviewLine(ApiModel):
    equipment_id: uuid.UUID
    validity: CertValidity
    errors: list[ApiWarning] = Field(
        description="What Submit would refuse (SERIAL_MISMATCH, SWL_ABOVE_RATING, "
        "LOAD_TEST_REQUIRED, ATTRIBUTE_REQUIRED…)."
    )
    warnings: list[ApiWarning]


class EquipmentCertPreview(ApiModel):
    """POST /projects/{id}/equipment-certificates/preview: validity per line (§6.1) and the
    errors / warnings Submit would give, for the form. Writes nothing."""

    tpi_acceptable: bool
    tpi_reason: str | None = Field(description="TP-4 meta reason when not acceptable.")
    errors: list[ApiWarning]
    warnings: list[ApiWarning]
    lines: list[EquipmentCertPreviewLine]
