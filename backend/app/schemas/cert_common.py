"""Building blocks shared by the Phase 4 schemas (spec 4-third-party-cert)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import Field

from app.core.cert_enums import (
    CertificateStatus,
    CertKind,
    CertLimitingFactor,
    CertStatusReason,
    CertVerificationMethod,
    DefectCategory,
    EquipmentCertCategory,
    EquipmentSubtype,
    HookReasonCode,
    LimitationCode,
    PersonnelLimitationCode,
    ScaffoldStatus,
    ScaffoldTagStatus,
    ServiceStatus,
    TpiStatus,
    VerificationDifference,
    VerificationOutcome,
    VerificationStatus,
)
from app.schemas.common import ApiModel, Page, StrictInput
from app.schemas.hse_common import DecimalStr, UserRef

Tonnes = Annotated[DecimalStr, Field(ge=Decimal(0), max_digits=8, decimal_places=3)]
"""Mass in tonnes, 3 dp (decimal(8,3)); JSON string on output."""
Metres2 = Annotated[DecimalStr, Field(ge=Decimal(0), max_digits=6, decimal_places=2)]
Pct1 = Annotated[DecimalStr, Field(ge=Decimal(0), max_digits=5, decimal_places=1)]

CERT_TYPE_CODE = r"^[A-Z0-9-]{2,40}$"
TAG_PATTERN = r"^[A-Za-z0-9-]{2,20}$"

P4_HINT = (
    "P3/P4 hint: no ID numbers, medical details, criminal-law conclusions or personal mobiles."
)


# ---- references -----------------------------------------------------------------------------


class TpiRef(ApiModel):
    """A TPI as shown on other records. Contractor roles see `status` only as accepted / not
    accepted (`accepted_for_use`), never the suspension or blacklist reason (P4-5)."""

    id: uuid.UUID
    tpi_code: str = Field(examples=["AICC"])
    legal_name_en: str
    legal_name_ar: str
    status: TpiStatus | None = Field(
        default=None, description="Null for callers outside HSE roles (they get accepted_for_use)."
    )
    accepted_for_use: bool = Field(
        description="Approved (new certificates accepted). Contractors see 'Not accepted / غير "
        "مقبولة' when false."
    )


class EquipmentRef(ApiModel):
    id: uuid.UUID
    equipment_no: str = Field(examples=["EQP-000101"])
    category: EquipmentCertCategory
    subtype: EquipmentSubtype | None
    manufacturer: str
    model: str
    serial_no: str
    owner_short_code: str | None = Field(examples=["QIMMA"])
    service_status: ServiceStatus


class DeploymentRef(ApiModel):
    id: uuid.UUID
    deployment_no: str = Field(examples=["EQD-RBT-52-0001"])
    project_id: uuid.UUID
    tag: str = Field(examples=["TC-01"])


class ScaffoldRef(ApiModel):
    id: uuid.UUID
    scaffold_no: str = Field(examples=["SCF-ANIA-EXP-0142"])
    tag: str = Field(examples=["SC-0142"])
    status: ScaffoldStatus
    tag_status: ScaffoldTagStatus
    tag_valid_until: date | None


class CertLineRef(ApiModel):
    certificate_id: uuid.UUID
    line_id: uuid.UUID
    cert_no: str
    tpi_code: str
    status: CertificateStatus
    valid_until: date | None


class DefectRef(ApiModel):
    id: uuid.UUID
    defect_no: str = Field(examples=["DEF-ANIA-EXP-2026-0007"])
    category: DefectCategory
    status: str = Field(examples=["open"])
    due_date: date | None


# ---- limitations ----------------------------------------------------------------------------


class EquipmentLimitation(StrictInput):
    """List LIM. `value` for derated_swl (t), max_wind_ms (m/s), reinspect_after_hours (h);
    `text` for other."""

    code: LimitationCode
    value: DecimalStr | None = Field(default=None, ge=Decimal(0), max_digits=8, decimal_places=3)
    text: str | None = Field(default=None, max_length=200)


class EquipmentLimitationRead(ApiModel):
    code: LimitationCode
    value: DecimalStr | None
    text: str | None
    label_en: str
    label_ar: str


class PersonnelLimitation(StrictInput):
    """List LIM-P — non-medical only (P4-6). `text` for specific_model_only and other."""

    code: PersonnelLimitationCode
    text: str | None = Field(default=None, max_length=200)


class PersonnelLimitationRead(ApiModel):
    code: PersonnelLimitationCode
    text: str | None
    label_en: str
    label_ar: str


# ---- validity -------------------------------------------------------------------------------


class CertValidity(ApiModel):
    """§6.1 / §6.2 strictest-wins validity and the §6.6 in-force predicate today."""

    valid_until: date | None = Field(description="Effective last valid day (local).")
    limiting_factor: CertLimitingFactor | None
    printed_date: date | None = Field(description="printed_next_due / printed_expiry as printed.")
    platform_end: date | None = Field(description="Interval end / cap end (§6.1, §6.2).")
    days_left: int | None = Field(description="valid_until − today; negative = past.")
    in_force: bool
    not_in_force_reason: HookReasonCode | None = Field(
        description="CERT_UNVERIFIED, CERT_EXPIRED, CERT_SUSPENDED, CERT_REVOKED, "
        "CERT_HOLDER_BANNED, TPI_BLACKLISTED, CONFIGURATION_CHANGED…"
    )
    expiring: bool = Field(description="In force and valid_until ≤ today + 7 (§6.6).")
    in_force_from: datetime | None = Field(
        description="When it came into force (accepted and verified), UTC."
    )
    unverified_window_until: datetime | None = Field(
        default=None,
        description="VF-1: counts as in force (warning CERT_UNVERIFIED) until this time; "
        "never for critical codes.",
    )


# ---- transitions ----------------------------------------------------------------------------


class CertTransitionRequest(StrictInput):
    """§4.4 certificate transitions (equipment and personnel):

    * `submitted` (106 / 118): scan attached; EC-1…EC-5 / PC-1…PC-7.
    * `draft` (107): return with `reason` ≥ 10 chars.
    * `accepted` (107, reviewer ≠ submitter, 422 SOD_CONFLICT): personnel name match `none`
      needs `identity_confirmed_by_tpi` (422 NAME_MISMATCH_CONFIRMATION); a CF-3 mismatch
      needs `configuration_mismatch_confirmed` (422 CONFIGURATION_MISMATCH).
    * `rejected` (107): reason.
    * `suspended` (116): reason; hard stop (HK4-3).
    * `accepted` from suspended (116): reinstate, reason; never for configuration_changed.
    * `revoked` (107): TPI revocation notice, reason.
    * `historic` (107): EC-2 attach an already-expired certificate to the history.
    """

    to_status: CertificateStatus
    reason: str | None = Field(default=None, max_length=500, description=P4_HINT)
    reason_code: CertStatusReason | None = None
    identity_confirmed_by_tpi: bool = False
    configuration_mismatch_confirmed: bool = False


# ---- verification (§3.10, VF) -----------------------------------------------------------------


class VerificationCreate(StrictInput):
    """Capability 108; verifier ≠ submitter and not employed by the holder's employer / the
    equipment owner (422 SOD_CONFLICT, VF-2). `channel_used` must be on the TPI record
    (422 CHANNEL_NOT_REGISTERED, VF-3). `evidence_attachment_id` (owner
    verification_evidence) is required except for tpi_phone, where `reference` ≥ 20 chars
    names the TPI person's role (422 EVIDENCE_REQUIRED_FOR_METHOD). The server never opens
    external URLs (VF-4)."""

    method: CertVerificationMethod
    channel_used: str = Field(min_length=1, max_length=200, examples=["verify.aicc-test.example"])
    outcome: VerificationOutcome
    differences: list[VerificationDifference] = Field(
        default_factory=list, description="Required iff outcome = details_differ."
    )
    differences_text: str | None = Field(default=None, max_length=300)
    reference: str = Field(min_length=1, max_length=100, examples=["AICC portal ref TEST-77812"])
    evidence_attachment_id: uuid.UUID | None = None
    performed_at: datetime | None = Field(default=None, description="UTC; default now.")


class VerificationRead(ApiModel):
    """Outcome detail (`differences`, not_found / details_differ on personnel certificates)
    is sensitive (P4-4): only HSE Manager / Officer see it; others get `outcome` = null and
    `counts_as_verification`."""

    id: uuid.UUID
    cert_kind: CertKind
    cert_id: uuid.UUID
    cert_no: str
    method: CertVerificationMethod
    channel_used: str
    outcome: VerificationOutcome | None
    differences: list[VerificationDifference]
    differences_text: str | None
    reference: str
    evidence_attachment_id: uuid.UUID | None
    performed_by: UserRef
    performed_at: datetime
    counts_as_verification: bool = Field(
        description="False for original_sighted and no_response (VF-3, VF-5)."
    )
    verification_status_after: VerificationStatus


class VerificationList(ApiModel):
    items: list[VerificationRead]


class VerificationLogItem(VerificationRead):
    project_id: uuid.UUID
    holder_or_item_ref: str = Field(examples=["WKR-000019", "RW-MC-03"])


class VerificationLogPage(Page[VerificationLogItem]):
    pass


class AllowedCertAction(ApiModel):
    to_status: CertificateStatus
    label_en: str
    label_ar: str
