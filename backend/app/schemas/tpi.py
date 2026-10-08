"""TPI organisations, accreditations and client approvals (spec 4-third-party-cert §3.1-§3.3,
§4.1, TP-1…TP-8, BL-6…BL-8)."""

import uuid
from datetime import date, datetime

from pydantic import Field

from app.core.cert_enums import (
    AccreditationBody,
    AccreditationStandard,
    ClientApprovalStatus,
    EquipmentCertCategory,
    TpiBlacklistScope,
    TpiKind,
    TpiStatus,
)
from app.schemas.cert_common import CERT_TYPE_CODE, P4_HINT, EquipmentRef, TpiRef
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput
from app.schemas.hse_common import UserRef

TPI_CODE = r"^[A-Z0-9-]{2,12}$"
FQDN = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$"
E164 = r"^\+[1-9]\d{7,14}$"
CR_NUMBER = r"^\d{10}$"


class TpiFields(StrictInput):
    legal_name_en: str = Field(min_length=1, max_length=200)
    legal_name_ar: str = Field(min_length=1, max_length=200, description="Arabic script.")
    kinds: list[TpiKind] = Field(min_length=1)
    country: str = Field(pattern=r"^[A-Z]{2}$", examples=["SA"])
    cr_number: str | None = Field(
        default=None, pattern=CR_NUMBER, description="Required iff country = SA."
    )
    foreign_reg_no: str | None = Field(
        default=None, max_length=30, description="Required iff country ≠ SA."
    )
    verification_portal_url: str | None = Field(
        default=None,
        max_length=300,
        description="https only; host ∈ verification_domains.",
        examples=["https://verify.aicc-test.example"],
    )
    verification_domains: list[str] = Field(
        min_length=1, description="Lower-case FQDNs (VF-3, VF-4).", examples=[["aicc-test.example"]]
    )
    verification_email: str | None = Field(
        default=None, max_length=254, description="Domain ∈ verification_domains."
    )
    verification_phone: str | None = Field(default=None, pattern=E164)
    contact_name: str | None = Field(default=None, max_length=120)
    contact_mobile: str | None = Field(default=None, pattern=E164)
    affiliated_contractor_ids: list[uuid.UUID] = Field(
        default_factory=list, description="TP-6 independence check."
    )


class TpiCreate(TpiFields):
    """Capability 114 → Draft. tpi_code unique org-wide and immutable; names unique after
    Phase 0 rule 45 normalisation (409 DUPLICATE_VALUE)."""

    tpi_code: str = Field(pattern=TPI_CODE, examples=["AICC"])


class TpiUpdate(PatchInput):
    non_nullable = frozenset(
        {"legal_name_en", "legal_name_ar", "kinds", "country", "verification_domains"}
    )

    legal_name_en: str | None = Field(default=None, min_length=1, max_length=200)
    legal_name_ar: str | None = Field(default=None, min_length=1, max_length=200)
    kinds: list[TpiKind] | None = Field(default=None, min_length=1)
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    cr_number: str | None = Field(default=None, pattern=CR_NUMBER)
    foreign_reg_no: str | None = Field(default=None, max_length=30)
    verification_portal_url: str | None = Field(default=None, max_length=300)
    verification_domains: list[str] | None = Field(default=None, min_length=1)
    verification_email: str | None = Field(default=None, max_length=254)
    verification_phone: str | None = Field(default=None, pattern=E164)
    contact_name: str | None = Field(default=None, max_length=120)
    contact_mobile: str | None = Field(default=None, pattern=E164)
    affiliated_contractor_ids: list[uuid.UUID] | None = None


class TpiTransitionRequest(StrictInput):
    """§4.1: Draft → pending_approval (114; needs ≥ 1 accreditation with register_checked_at,
    or kind client_scheme with a client approval — 422 TPI_ACCREDITATION_REQUIRED);
    pending_approval → approved / draft (115, return with reason); approved → suspended
    (115, reason, BL-6); suspended → approved (115, reason); approved/suspended →
    blacklisted (115, reason ≥ 20, blacklist_scope, blacklist_from for issued_from; BL-7);
    blacklisted → suspended (115, "lift blacklist", reason; BL-8)."""

    to_status: TpiStatus
    reason: str | None = Field(default=None, max_length=500, description=P4_HINT)
    blacklist_scope: TpiBlacklistScope | None = None
    blacklist_from: date | None = None


class AccreditationFields(StrictInput):
    accreditation_body: AccreditationBody
    standard: AccreditationStandard = Field(
        description="Must correspond to one of the TPI's kinds (422 STANDARD_KIND_MISMATCH): "
        "17020 inspection_body, 17024 personnel_certification_body / ndt_body, 17025 "
        "calibration_lab, client_scheme client_scheme (accreditation_body client)."
    )
    accreditation_no: str = Field(min_length=1, max_length=40, examples=["SAC-TEST-IB-0101"])
    scope_categories: list[EquipmentCertCategory] = Field(
        default_factory=list, description="Required for 17020 / 17025 (list EQC)."
    )
    scope_cert_types: list[str] = Field(
        default_factory=list,
        description="Required for 17024 / client_scheme personnel (list PCT codes).",
        examples=[["CRANE-OPERATOR", "RIGGER", "SIGNALLER"]],
    )
    valid_from: date
    valid_until: date
    certificate_attachment_id: uuid.UUID = Field(
        description="PDF ≤ 10 MB, owner tpi_accreditation_certificate."
    )


class AccreditationCreate(AccreditationFields):
    """Capability 114. accreditation_no unique per accreditation_body (409 DUPLICATE_VALUE)."""


class AccreditationUpdate(PatchInput):
    non_nullable = frozenset(
        {"accreditation_body", "standard", "accreditation_no", "valid_from", "valid_until"}
    )

    accreditation_body: AccreditationBody | None = None
    standard: AccreditationStandard | None = None
    accreditation_no: str | None = Field(default=None, min_length=1, max_length=40)
    scope_categories: list[EquipmentCertCategory] | None = None
    scope_cert_types: list[str] | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    certificate_attachment_id: uuid.UUID | None = None


class RegisterCheckInput(StrictInput):
    """TP-3: the accreditation was confirmed on the accreditation body's public register."""

    checked_at: datetime | None = Field(default=None, description="UTC; default now.")
    note: str | None = Field(default=None, max_length=300)


class AccreditationRead(ApiModel):
    id: uuid.UUID
    tpi_id: uuid.UUID
    accreditation_body: AccreditationBody
    standard: AccreditationStandard
    accreditation_no: str
    scope_categories: list[EquipmentCertCategory]
    scope_cert_types: list[str]
    valid_from: date
    valid_until: date
    days_left: int
    certificate_attachment_id: uuid.UUID | None
    register_checked_at: datetime | None
    register_checked_by: UserRef | None
    counts: bool = Field(description="TP-3: register checked and today ≤ valid_until.")
    created_at: datetime
    updated_at: datetime


class TpiRead(ApiModel):
    """Contact person fields are personal (absent for roles without capability 114). For
    contractor roles `status_reason` and blacklist details are null (P4-5)."""

    id: uuid.UUID
    tpi_code: str
    legal_name_en: str
    legal_name_ar: str
    kinds: list[TpiKind]
    country: str
    cr_number: str | None
    foreign_reg_no: str | None
    verification_portal_url: str | None
    verification_domains: list[str]
    verification_email: str | None
    verification_phone: str | None
    contact_name: str | None
    contact_mobile: str | None
    affiliated_contractor_ids: list[uuid.UUID]
    status: TpiStatus | None
    accepted_for_use: bool
    status_reason: str | None
    blacklist_scope: TpiBlacklistScope | None
    blacklist_from: date | None
    accreditation_lapsed: bool = Field(
        description="Derived: no accreditation valid today for any kind (§4.1)."
    )
    accreditations: list[AccreditationRead]
    approved_by: UserRef | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TpiListItem(ApiModel):
    id: uuid.UUID
    tpi_code: str
    legal_name_en: str
    legal_name_ar: str
    kinds: list[TpiKind]
    country: str
    status: TpiStatus | None
    accepted_for_use: bool
    accreditation_lapsed: bool
    next_accreditation_expiry: date | None


class TpiPage(Page[TpiListItem]):
    pass


class ClientApprovalCreate(StrictInput):
    """Capability 114 (§3.3). (project, tpi) unique (409 DUPLICATE_VALUE). Scope ⊆ the TPI's
    accredited scope (422 SCOPE_EXCEEDS_ACCREDITATION); ≥ 1 code overall."""

    tpi_id: uuid.UUID
    approval_ref: str = Field(min_length=1, max_length=40, examples=["ANIA-CL-TPI-TEST-007"])
    scope_categories: list[EquipmentCertCategory] = Field(default_factory=list)
    scope_cert_types: list[str] = Field(default_factory=list)
    valid_until: date


class ClientApprovalUpdate(PatchInput):
    non_nullable = frozenset({"approval_ref", "valid_until", "status"})

    approval_ref: str | None = Field(default=None, min_length=1, max_length=40)
    scope_categories: list[EquipmentCertCategory] | None = None
    scope_cert_types: list[str] | None = None
    valid_until: date | None = None
    status: ClientApprovalStatus | None = Field(default=None, description="withdrawn is final.")


class ClientApprovalRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    tpi: TpiRef
    approval_ref: str
    scope_categories: list[EquipmentCertCategory]
    scope_cert_types: list[str]
    valid_until: date
    days_left: int
    status: ClientApprovalStatus
    created_at: datetime
    updated_at: datetime


class ClientApprovalList(ApiModel):
    items: list[ClientApprovalRead]


class TpiImpactHolder(ApiModel):
    worker_id: uuid.UUID
    worker_no: str
    full_name_en: str | None = Field(description="Only with capability 46.")
    full_name_ar: str | None
    cert_type: str = Field(pattern=CERT_TYPE_CODE)
    cert_no: str
    project_ids: list[uuid.UUID]


class TpiImpactItem(ApiModel):
    equipment: EquipmentRef
    cert_no: str
    tags: list[str] = Field(description="Deployment tags (non-demobilised).")
    project_ids: list[uuid.UUID]


class TpiImpact(ApiModel):
    """BL-7: items and holders affected by the TPI's suspension / blacklist (for
    re-certification), plus Phase 3 detectors calibrated by it."""

    tpi: TpiRef
    revoked_certificates: int
    equipment: list[TpiImpactItem]
    holders: list[TpiImpactHolder]
    gas_detector_ids: list[uuid.UUID]
