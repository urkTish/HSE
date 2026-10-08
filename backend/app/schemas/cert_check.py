"""Certification check: EQ sticker scan (VF-8), scaffold sticker, and the personnel
certification check from an AC card or a typed cert_no (VF-9). Capability 121; logs
`cert_check_view`; records no entry (spec 4-third-party-cert §5.7)."""

import uuid
from datetime import date, datetime

from pydantic import Field

from app.core.access_enums import QrKind
from app.core.cert_enums import (
    CertCheckResult,
    CertCheckSubject,
    EquipmentCertCategory,
    ScaffoldStatus,
    ScaffoldTagStatus,
    ServiceStatus,
    ServiceStatusReason,
)
from app.core.errors import ErrorCode
from app.core.hse_enums import Trade
from app.schemas.cert_common import EquipmentLimitationRead, PersonnelLimitationRead
from app.schemas.common import ApiModel, StrictInput
from app.schemas.hse_common import DecimalStr


class CertCheckRequest(StrictInput):
    """Send exactly one of `payload` (QR text: kind EQ — one token family for
    equipment and scaffold stickers — or AC in certificates mode),
    `printed_ref` (`<project>-<tag>` for equipment or a scaffold) or `cert_no` (a personnel
    certificate number, with `tpi_code` when ambiguous). `project_id` scopes a printed_ref or
    cert_no lookup (required for them). 422 VALIDATION_ERROR otherwise."""

    payload: str | None = Field(
        default=None, max_length=200, examples=["HSE2:EQ:q8Xb2mJf0Q9nZr4tYc1wKA"]
    )
    printed_ref: str | None = Field(default=None, max_length=60, examples=["ANIA-EXP-TC-01"])
    cert_no: str | None = Field(default=None, max_length=40)
    tpi_code: str | None = Field(default=None, max_length=20)
    project_id: uuid.UUID | None = None


class EquipmentCheckCard(ApiModel):
    """VF-8 / GE-5: no personal data (no inspector or operator names)."""

    deployment_id: uuid.UUID
    project_code: str
    tag: str
    equipment_no: str
    category: EquipmentCertCategory
    owner_short_code: str | None
    service_status: ServiceStatus
    service_status_reason: ServiceStatusReason | None
    colour: str = Field(description="green | amber | red.", examples=["green"])
    cert_no: str | None
    tpi_code: str | None
    valid_until: date | None
    swl_t: DecimalStr | None
    limitations: list[EquipmentLimitationRead]
    arrival_inspection_due: bool


class ScaffoldCheckCard(ApiModel):
    scaffold_id: uuid.UUID
    project_code: str
    tag: str
    scaffold_no: str
    zone_code: str
    status: ScaffoldStatus
    tag_status: ScaffoldTagStatus
    tag_valid_until: date | None
    usable_today: bool
    load_class: int
    restrictions_en: str | None
    restrictions_ar: str | None


class PersonCheckCertificate(ApiModel):
    """VF-9: never ID numbers, scans, the medical flag or verification-failure details."""

    cert_type: str = Field(examples=["RIGGER"])
    cert_type_label_en: str
    cert_type_label_ar: str
    cert_no: str
    tpi_code: str
    level: str | None
    valid_until: date | None
    in_force: bool
    not_in_force_reason: ErrorCode | None = Field(
        description="E.g. EXPIRED, NOT_VERIFIED, SUSPENDED (no failure details)."
    )
    scope_categories: list[EquipmentCertCategory]
    max_capacity_t: DecimalStr | None
    limitations: list[PersonnelLimitationRead] = Field(description="Non-medical only.")


class PersonCheckCard(ApiModel):
    worker_id: uuid.UUID
    worker_no: str
    full_name_en: str
    full_name_ar: str
    photo_url: str | None = Field(description="Signed, short-lived (GC-7).")
    employer_short_code: str | None
    trade: Trade | None
    certificates: list[PersonCheckCertificate]


class CertCheckResponse(ApiModel):
    checked_at: datetime
    qr_kind: QrKind | None
    subject: CertCheckSubject | None = Field(description="Null when unknown.")
    result: CertCheckResult
    reason_code: ErrorCode | None = Field(
        description="TOKEN_UNKNOWN, CREDENTIAL_REVOKED, OUT_OF_SCOPE, or the not-usable reason."
    )
    message_en: str
    message_ar: str
    equipment: EquipmentCheckCard | None = None
    scaffold: ScaffoldCheckCard | None = None
    person: PersonCheckCard | None = None
