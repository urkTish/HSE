"""Contractors (master records) and project engagements (spec §3.4, §3.5, §4.2, §5.4)."""

import re
import uuid
from datetime import date

from pydantic import EmailStr, Field, field_validator, model_validator

from app.core.enums import ContractorCategory, ContractorStatus
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput, Timestamps, has_arabic

CR_PATTERN = r"^[12457]\d{9}$"
VAT_PATTERN = r"^3\d{13}3$"
SHORT_CODE = r"^[A-Z0-9]{2,10}$"
E164 = re.compile(r"^\+[1-9]\d{7,14}$")
KSA_MOBILE = re.compile(r"^\+9665\d{8}$")
CONTACT_NOTE = " Omitted when the caller lacks capability 9 (view contractor contact details)."


def check_mobile(v: str | None) -> str | None:
    if v is None:
        return v
    if not E164.match(v):
        raise ValueError("must be an E.164 number, e.g. +966500000101")
    if v.startswith("+966") and not KSA_MOBILE.match(v):
        raise ValueError("KSA mobile must match +9665XXXXXXXX")
    return v


def _check_ar(v: str | None) -> str | None:
    if v is not None and not has_arabic(v):
        raise ValueError("must contain Arabic script")
    return v


class ContractorCreate(StrictInput):
    """Creates a contractor in status draft (capability 5)."""

    legal_name_en: str = Field(min_length=1, max_length=200)
    legal_name_ar: str = Field(min_length=1, max_length=200)
    short_code: str = Field(pattern=SHORT_CODE, description="Unique, e.g. RAWABI.")
    cr_number: str = Field(
        pattern=CR_PATTERN,
        description="10-digit Commercial Registration; legacy prefix 1/2/4/5 or unified 7. Unique.",
    )
    cr_expiry_date: date | None = None
    vat_number: str | None = Field(default=None, pattern=VAT_PATTERN)
    contractor_category: ContractorCategory
    primary_contact_name: str = Field(min_length=1, max_length=120)
    primary_contact_mobile: str = Field(max_length=16, description="E.164; KSA +9665XXXXXXXX.")
    primary_contact_email: EmailStr

    _ar = field_validator("legal_name_ar")(_check_ar)
    _mob = field_validator("primary_contact_mobile")(check_mobile)


class ContractorUpdate(PatchInput):
    non_nullable = frozenset(
        {
            "legal_name_en",
            "legal_name_ar",
            "short_code",
            "cr_number",
            "contractor_category",
            "primary_contact_name",
            "primary_contact_mobile",
            "primary_contact_email",
        }
    )

    legal_name_en: str | None = Field(default=None, min_length=1, max_length=200)
    legal_name_ar: str | None = Field(default=None, min_length=1, max_length=200)
    short_code: str | None = Field(default=None, pattern=SHORT_CODE)
    cr_number: str | None = Field(default=None, pattern=CR_PATTERN)
    cr_expiry_date: date | None = None
    vat_number: str | None = Field(default=None, pattern=VAT_PATTERN)
    contractor_category: ContractorCategory | None = None
    primary_contact_name: str | None = Field(default=None, min_length=1, max_length=120)
    primary_contact_mobile: str | None = Field(default=None, max_length=16)
    primary_contact_email: EmailStr | None = None

    _ar = field_validator("legal_name_ar")(_check_ar)
    _mob = field_validator("primary_contact_mobile")(check_mobile)


class ContractorRead(Timestamps):
    id: uuid.UUID
    legal_name_en: str
    legal_name_ar: str
    short_code: str
    cr_number: str
    cr_expiry_date: date | None
    vat_number: str | None
    contractor_category: ContractorCategory
    status: ContractorStatus
    status_reason: str | None
    primary_contact_name: str | None = Field(default=None, description="Personal." + CONTACT_NOTE)
    primary_contact_mobile: str | None = Field(default=None, description="Personal." + CONTACT_NOTE)
    primary_contact_email: str | None = Field(default=None, description="Personal." + CONTACT_NOTE)


class ContractorPage(Page[ContractorRead]):
    pass


class ContractorTransitionRequest(StrictInput):
    """Allowed (§4.2): draft→pending_approval; pending_approval→approved; pending_approval→draft
    (comment); approved→suspended (reason); suspended→approved (reason); approved/suspended→
    demobilised (all engagements demobilised); any→blacklisted (reason); blacklisted→suspended
    (lift blacklist, reason)."""

    to_status: ContractorStatus
    reason: str | None = Field(default=None, max_length=500)


class ContractorSummary(ApiModel):
    id: uuid.UUID
    short_code: str
    legal_name_en: str
    legal_name_ar: str
    status: ContractorStatus


class EngagementCreate(StrictInput):
    """Engage an approved contractor on a project (capability 7)."""

    contractor_id: uuid.UUID
    tier: int = Field(
        ge=1, le=3, description="1 main contractor, 2 subcontractor, 3 sub-subcontractor."
    )
    parent_engagement_id: uuid.UUID | None = Field(
        default=None,
        description="Null iff tier = 1; otherwise an engagement on the same project with tier-1.",
    )
    scope_of_work_en: str = Field(min_length=1, max_length=500)
    scope_of_work_ar: str = Field(min_length=1, max_length=500)
    site_ids: list[uuid.UUID] = Field(min_length=1, description="Sites of the same project.")
    mobilisation_date: date
    demobilisation_date: date | None = None

    @model_validator(mode="after")
    def _rules(self) -> "EngagementCreate":
        if self.tier == 1 and self.parent_engagement_id is not None:
            raise ValueError("tier 1 engagements have no parent")
        if self.tier > 1 and self.parent_engagement_id is None:
            raise ValueError("parent_engagement_id is required for tier > 1")
        if self.demobilisation_date and self.demobilisation_date < self.mobilisation_date:
            raise ValueError("demobilisation_date must be on or after mobilisation_date")
        return self


class EngagementUpdate(PatchInput):
    """Tier, parent and contractor are immutable once created."""

    non_nullable = frozenset(
        {"scope_of_work_en", "scope_of_work_ar", "site_ids", "mobilisation_date"}
    )

    scope_of_work_en: str | None = Field(default=None, min_length=1, max_length=500)
    scope_of_work_ar: str | None = Field(default=None, min_length=1, max_length=500)
    site_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)
    mobilisation_date: date | None = None
    demobilisation_date: date | None = None


class EngagementRead(Timestamps):
    id: uuid.UUID
    project_id: uuid.UUID
    contractor_id: uuid.UUID
    contractor: ContractorSummary
    tier: int = Field(ge=1, le=3)
    parent_engagement_id: uuid.UUID | None
    root_engagement_id: uuid.UUID = Field(
        description="Tier-1 engagement this one rolls up to (§8 roll-up rule)."
    )
    scope_of_work_en: str
    scope_of_work_ar: str
    site_ids: list[uuid.UUID]
    mobilisation_date: date
    demobilisation_date: date | None
    parent_blacklisted: bool = Field(
        description="An ancestor contractor was blacklisted; awaiting HSE Manager review (rule 27)."
    )


class EngagementPage(Page[EngagementRead]):
    pass
