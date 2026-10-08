"""Course catalogue, training providers and their accreditations (spec 5-training §3.1, §3.2,
§4.1, CC-1…CC-7, PV-1…PV-8)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.core.access_enums import InductionType, WorkerLanguage
from app.core.train_enums import (
    AccreditationBodyCode,
    CourseCategory,
    DeliveryMode,
    ProviderBlacklistScope,
    ProviderUnacceptableReason,
    TrainingProviderAction,
    TrainingProviderKind,
    TrainingProviderStatus,
)
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput
from app.schemas.hse_common import DecimalStr, UserRef
from app.schemas.training_common import COURSE_CODE, P5_HINT, PROVIDER_CODE, CourseRef

FQDN = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$"
E164 = r"^\+[1-9]\d{7,14}$"
CR_NUMBER = r"^\d{10}$"

# ---- course catalogue -----------------------------------------------------------------------


class InductionLink(StrictInput):
    """CC-7: required iff category = induction_link. `project_course_codes` maps a project id
    to the Phase 2 induction course code (zone_specific); general_site needs none (any active
    course of the type, DECISIONS #47)."""

    induction_type: InductionType
    project_course_codes: dict[uuid.UUID, str] = Field(default_factory=dict)


class InductionLinkRead(ApiModel):
    induction_type: InductionType
    project_course_codes: dict[uuid.UUID, str]


class ProviderRule(StrictInput):
    """CC-4: a non-empty `accreditation_bodies_required` ⇒ internal_allowed = false and
    contractor_delivery_allowed = false (422 ACCREDITED_PROVIDER_REQUIRED)."""

    internal_allowed: bool
    contractor_delivery_allowed: bool
    accreditation_bodies_required: list[AccreditationBodyCode] = Field(default_factory=list)


class ProviderRuleRead(ApiModel):
    internal_allowed: bool
    contractor_delivery_allowed: bool
    accreditation_bodies_required: list[AccreditationBodyCode]


class CourseFields(StrictInput):
    name_en: str = Field(min_length=1, max_length=150)
    name_ar: str = Field(min_length=1, max_length=150, description="Arabic script.")
    category: CourseCategory
    induction_link: InductionLink | None = None
    validity_months: int | None = Field(
        default=None,
        ge=1,
        le=60,
        description="Null = no expiry (only professional_qualification); ignored for "
        "induction_link.",
    )
    min_duration_hours: DecimalStr | None = Field(
        default=None,
        ge=Decimal("0.50"),
        le=Decimal("400.00"),
        max_digits=5,
        decimal_places=2,
        description="Required except for induction_link.",
    )
    max_class_size: int | None = Field(default=None, ge=1, le=60)
    delivery_modes: list[DeliveryMode] = Field(
        default_factory=list,
        description="e_learning alone not allowed when practical_required (CC-5, 422 "
        "PRACTICAL_REQUIRED).",
    )
    theory_required: bool = False
    pass_mark_pct: int | None = Field(
        default=None, ge=50, le=100, description="Required iff theory_required."
    )
    practical_required: bool = False
    prerequisite_codes: list[str] = Field(
        default_factory=list, description="Active codes; no cycles (422 PREREQUISITE_CYCLE)."
    )
    satisfies: list[str] = Field(default_factory=list, description="CC-6 (one level only).")
    renewal_course_code: str | None = Field(default=None, pattern=COURSE_CODE)
    renews_only: bool = False
    provider_rule: ProviderRule | None = Field(
        default=None, description="Required except for induction_link."
    )
    languages_offered: list[WorkerLanguage] = Field(default_factory=list)
    active: bool = True


class CourseCreate(CourseFields):
    """Capability 126 (HSE Manager). `code` unique org-wide and immutable; a code in Phase 4
    list PCT → 409 CODE_IN_OTHER_CATALOGUE (BD5-2)."""

    code: str = Field(pattern=COURSE_CODE, examples=["CSE-ATTENDANT"])


class CourseUpdate(PatchInput):
    """CC-2 tighten only: validity shorter, pass mark higher, min hours longer, practical
    false → true, accreditation bodies added; anything else → 422 CATALOGUE_LOOSENING. Labels,
    languages, `active` and prerequisite/satisfies lists are editable. A validity shortening
    recomputes every record's stored valid_until (response `records_recomputed`)."""

    non_nullable = frozenset(
        {"name_en", "name_ar", "category", "delivery_modes", "provider_rule", "active"}
    )

    name_en: str | None = Field(default=None, min_length=1, max_length=150)
    name_ar: str | None = Field(default=None, min_length=1, max_length=150)
    category: CourseCategory | None = None
    induction_link: InductionLink | None = None
    validity_months: int | None = Field(default=None, ge=1, le=60)
    min_duration_hours: DecimalStr | None = Field(
        default=None, ge=Decimal("0.50"), le=Decimal("400.00"), max_digits=5, decimal_places=2
    )
    max_class_size: int | None = Field(default=None, ge=1, le=60)
    delivery_modes: list[DeliveryMode] | None = None
    theory_required: bool | None = None
    pass_mark_pct: int | None = Field(default=None, ge=50, le=100)
    practical_required: bool | None = None
    prerequisite_codes: list[str] | None = None
    satisfies: list[str] | None = None
    renewal_course_code: str | None = Field(default=None, pattern=COURSE_CODE)
    renews_only: bool | None = None
    provider_rule: ProviderRule | None = None
    languages_offered: list[WorkerLanguage] | None = None
    active: bool | None = None
    reason: str | None = Field(default=None, max_length=300, description=P5_HINT)


class CourseRead(ApiModel):
    id: uuid.UUID = Field(description="Use for GET /history/training_course/{id}.")
    code: str
    name_en: str
    name_ar: str
    category: CourseCategory
    induction_link: InductionLinkRead | None
    validity_months: int | None
    effective_validity_months: int | None = Field(
        default=None,
        description="With ?project_id: min(catalogue, project course_validity_months) (§6.1).",
    )
    min_duration_hours: DecimalStr | None
    max_class_size: int | None
    delivery_modes: list[DeliveryMode]
    theory_required: bool
    pass_mark_pct: int | None
    effective_pass_mark_pct: int | None = Field(
        default=None, description="With ?project_id: max(course, training_pass_mark_pct)."
    )
    practical_required: bool
    prerequisite_codes: list[str]
    satisfies: list[str]
    satisfied_by: list[str] = Field(description="Derived: courses whose `satisfies` lists it.")
    renewal_course_code: str | None
    renews_only: bool
    provider_rule: ProviderRuleRead | None
    languages_offered: list[WorkerLanguage]
    hook_code: bool = Field(description="Used by a Phase 2/3 attach point (HK5-2).")
    critical_on_project: bool | None = Field(
        default=None, description="With ?project_id: in training_hook_critical_codes."
    )
    in_use: bool = Field(description="Records, sessions, matrix lines or hooks (CC-1).")
    active: bool
    records_recomputed: int | None = Field(
        default=None, description="Returned once after a validity shortening (CC-2)."
    )
    created_at: datetime
    updated_at: datetime


class CourseList(ApiModel):
    items: list[CourseRead]


# ---- providers ------------------------------------------------------------------------------


class ProviderFields(StrictInput):
    legal_name_en: str = Field(min_length=1, max_length=200)
    legal_name_ar: str = Field(min_length=1, max_length=200, description="Arabic script.")
    kind: TrainingProviderKind
    contractor_id: uuid.UUID | None = Field(
        default=None, description="Required iff kind = contractor_internal."
    )
    country: str | None = Field(
        default=None, pattern=r"^[A-Z]{2}$", description="External: required."
    )
    cr_number: str | None = Field(
        default=None, pattern=CR_NUMBER, description="External, country = SA."
    )
    foreign_reg_no: str | None = Field(default=None, max_length=30)
    verification_portal_url: str | None = Field(
        default=None, max_length=300, description="https; host ∈ verification_domains."
    )
    verification_domains: list[str] = Field(
        default_factory=list, description="External: ≥ 1 lower-case FQDN (VR-3, VR-4)."
    )
    verification_email: str | None = Field(default=None, max_length=254)
    verification_phone: str | None = Field(default=None, pattern=E164)
    contact_name: str | None = Field(default=None, max_length=120)
    contact_mobile: str | None = Field(default=None, pattern=E164)


class ProviderCreate(ProviderFields):
    """Capability 127 → Draft. provider_code unique and immutable (409 DUPLICATE_VALUE)."""

    provider_code: str = Field(pattern=PROVIDER_CODE, examples=["HAYAT"])


class ProviderUpdate(PatchInput):
    non_nullable = frozenset({"legal_name_en", "legal_name_ar"})

    legal_name_en: str | None = Field(default=None, min_length=1, max_length=200)
    legal_name_ar: str | None = Field(default=None, min_length=1, max_length=200)
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    cr_number: str | None = Field(default=None, pattern=CR_NUMBER)
    foreign_reg_no: str | None = Field(default=None, max_length=30)
    verification_portal_url: str | None = Field(default=None, max_length=300)
    verification_domains: list[str] | None = None
    verification_email: str | None = Field(default=None, max_length=254)
    verification_phone: str | None = Field(default=None, pattern=E164)
    contact_name: str | None = Field(default=None, max_length=120)
    contact_mobile: str | None = Field(default=None, pattern=E164)


class ProviderTransitionRequest(StrictInput):
    """§4.1: submit (127; external needs ≥ 1 register-checked accreditation unless no course
    in scope requires one — 422 PROVIDER_ACCREDITATION_REQUIRED); approve / return (comment) /
    suspend (reason) / reinstate (reason) / blacklist (reason ≥ 20, `blacklist_scope`,
    `blacklist_from` for issued_from — 422 PROVIDER_BLACKLIST_SCOPE_REQUIRED) /
    lift_blacklist (→ Suspended) — capability 128. `effective_on` dates a suspension (PV-5,
    default today)."""

    action: TrainingProviderAction
    reason: str | None = Field(default=None, max_length=500, description=P5_HINT)
    blacklist_scope: ProviderBlacklistScope | None = None
    blacklist_from: date | None = None
    effective_on: date | None = None


class AccreditationFields(StrictInput):
    accreditation_body: AccreditationBodyCode
    accreditation_no: str = Field(min_length=1, max_length=40, examples=["SRCA-TEST-0042"])
    scope_course_codes: list[str] = Field(min_length=1, examples=[["FIRST-AID", "FIRST-AID-R"]])
    valid_from: date
    valid_until: date = Field(description="> valid_from.")
    certificate_attachment_id: uuid.UUID = Field(
        description="PDF ≤ 10 MB, owner training_accreditation_certificate."
    )


class ProviderAccreditationCreate(AccreditationFields):
    """Capability 127. accreditation_no unique per body (409 DUPLICATE_VALUE)."""


class ProviderAccreditationUpdate(PatchInput):
    non_nullable = frozenset(
        {"accreditation_body", "accreditation_no", "scope_course_codes", "valid_from"}
    )

    accreditation_body: AccreditationBodyCode | None = None
    accreditation_no: str | None = Field(default=None, min_length=1, max_length=40)
    scope_course_codes: list[str] | None = Field(default=None, min_length=1)
    valid_from: date | None = None
    valid_until: date | None = None
    certificate_attachment_id: uuid.UUID | None = None


class RegisterCheckInput(StrictInput):
    """PV-2: confirmed on the body's public register (needed for the accreditation to count)."""

    checked_at: datetime | None = Field(default=None, description="UTC; default now.")
    note: str | None = Field(default=None, max_length=300)


class ProviderAccreditationRead(ApiModel):
    id: uuid.UUID
    provider_id: uuid.UUID
    accreditation_body: AccreditationBodyCode
    accreditation_no: str
    scope_course_codes: list[str]
    valid_from: date
    valid_until: date
    days_left: int
    certificate_attachment_id: uuid.UUID | None
    register_checked_at: datetime | None
    register_checked_by: UserRef | None
    counts: bool = Field(description="PV-2: register checked and today within the dates.")
    created_at: datetime
    updated_at: datetime


class ProviderRead(ApiModel):
    """Contact fields absent for roles without capability 127. Contractor roles get
    `status` = null and no reasons (P5-4); they see `accepted_for_use`."""

    id: uuid.UUID
    provider_code: str
    legal_name_en: str
    legal_name_ar: str
    kind: TrainingProviderKind
    contractor_id: uuid.UUID | None
    contractor_short_code: str | None
    country: str | None
    cr_number: str | None
    foreign_reg_no: str | None
    verification_portal_url: str | None
    verification_domains: list[str]
    verification_email: str | None
    verification_phone: str | None
    contact_name: str | None = None
    contact_mobile: str | None = None
    status: TrainingProviderStatus | None
    accepted_for_use: bool
    status_reason: str | None
    suspended_from: date | None
    blacklist_scope: ProviderBlacklistScope | None
    blacklist_from: date | None
    accreditations: list[ProviderAccreditationRead]
    approved_by: UserRef | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProviderListItem(ApiModel):
    id: uuid.UUID
    provider_code: str
    legal_name_en: str
    legal_name_ar: str
    kind: TrainingProviderKind
    contractor_short_code: str | None
    status: TrainingProviderStatus | None
    accepted_for_use: bool
    accredited_course_codes: list[str] = Field(description="Counted accreditations today.")
    next_accreditation_expiry: date | None


class ProviderPage(Page[ProviderListItem]):
    pass


class ProviderImpactHolder(ApiModel):
    worker_id: uuid.UUID
    worker_no: str
    full_name_en: str | None = Field(description="Only with capability 46.")
    full_name_ar: str | None
    course_code: str
    record_no: str
    completed_on: date
    project_ids: list[uuid.UUID]


class ProviderImpact(ApiModel):
    """PV-6: holders whose records the suspension / blacklist affects (for re-training), and
    Scheduled sessions no longer allowed (PV-5)."""

    provider_id: uuid.UUID
    provider_code: str
    records_revoked: int
    holders: list[ProviderImpactHolder]
    sessions_not_allowed: list[uuid.UUID]


class AcceptabilityItem(ApiModel):
    on_date: date
    acceptable: bool
    reason: ProviderUnacceptableReason | None
    worker_ids_not_own_tree: list[uuid.UUID] = Field(
        default_factory=list, description="contractor_internal: NOT_OWN_TREE holders."
    )


class ProviderAcceptability(ApiModel):
    """PV-3 form helper: is the provider acceptable for the course on each date?"""

    provider_id: uuid.UUID
    course: CourseRef
    items: list[AcceptabilityItem]
