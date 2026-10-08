"""Phase 4 settings, catalogues (EQC / PCT), hook policy state, the warn → block switch and
the readiness report (spec 4-third-party-cert §3.14, §3.16, §3.17, §4.8, §6.5, §6.8, HK4-1…
HK4-12, BD-3, TP-5)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.core.access_enums import HookKind, VehicleCategory
from app.core.cert_enums import (
    CertLevel,
    EquipmentCertCategory,
    EquipmentSubtype,
    HookCodePolicy,
    HookReasonCode,
    HookStage,
    LiftingGearColour,
)
from app.core.hse_enums import Trade
from app.core.med_enums import HookBand
from app.core.ptw_enums import EquipmentCategory
from app.schemas.cert_common import CERT_TYPE_CODE
from app.schemas.common import ApiModel, PatchInput, StrictInput
from app.schemas.hse_common import DecimalStr, UserRef
from app.schemas.ptw_common import PermitRef

MMDD = r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$"

# ---- settings (§3.17) -------------------------------------------------------------------------


class ColourPeriod(StrictInput):
    from_mmdd: str = Field(pattern=MMDD, examples=["01-01"])
    to_mmdd: str = Field(pattern=MMDD, examples=["03-31"])
    colour: LiftingGearColour


class ColourScheme(StrictInput):
    enabled: bool
    periods: list[ColourPeriod] = Field(default_factory=list)


class ColourSchemeRead(ApiModel):
    enabled: bool
    periods: list[ColourPeriod]


class CertSettingsRead(ApiModel):
    """§3.17 (capability 124 edits; 15 / 122 read). "Allowed" ranges only; intervals and caps
    shorten only; lists tighten only."""

    project_id: uuid.UUID
    equipment_interval_months: dict[str, int] = Field(
        description="EQC code → months (scaffold uses scaffold_inspection_interval_days)."
    )
    equipment_interval_defaults: dict[str, int]
    personnel_cert_cap_months: dict[str, int] = Field(description="PCT code → months.")
    personnel_cert_cap_defaults: dict[str, int]
    require_client_approved_tpi: bool
    unverified_acceptance_hours: int
    verification_due_days: int
    defect_b_max_days: int
    defect_b_default_days: int
    scaffold_inspection_interval_days: int
    scaffold_design_height_m: DecimalStr
    arrival_inspection_hours: int
    rigger_level_critical_min: int
    trade_cert_requirements: dict[str, str] = Field(description="Trade → PCT code.")
    hook_transition_days: int
    hook_critical_codes: list[str]
    hook_critical_transition_days: int
    lifting_gear_colour_scheme: ColourSchemeRead
    equipment_cert_warning_pct: DecimalStr
    personnel_cert_warning_pct: DecimalStr
    scaffold_tag_warning_pct: DecimalStr
    dangerous_defect_warning_count: int
    ban_review_months: int
    cert_scan_retention_years: int
    alert_schedule_long_days: list[int]
    updated_at: datetime | None
    updated_by: UserRef | None


class CertSettingsUpdate(PatchInput):
    """Capability 124 (HSE Manager). Out-of-range or loosening values → 422 (VALIDATION_ERROR
    / SETTING_LOOSENING). Setting require_client_approved_tpi true returns the in-force
    certificates that would fail TP-5 (`client_approval_impact`); they turn not in force
    after 7 days unless an approval is recorded."""

    equipment_interval_months: dict[EquipmentCertCategory, int] | None = None
    personnel_cert_cap_months: dict[str, int] | None = None
    require_client_approved_tpi: bool | None = None
    unverified_acceptance_hours: int | None = Field(default=None, ge=0, le=24)
    verification_due_days: int | None = Field(default=None, ge=1, le=14)
    defect_b_max_days: int | None = Field(default=None, ge=1, le=30)
    defect_b_default_days: int | None = Field(default=None, ge=1, le=30)
    scaffold_inspection_interval_days: int | None = Field(default=None, ge=1, le=7)
    scaffold_design_height_m: DecimalStr | None = Field(
        default=None, ge=Decimal("6.00"), le=Decimal("20.00"), max_digits=4, decimal_places=2
    )
    arrival_inspection_hours: int | None = Field(default=None, ge=1, le=24)
    rigger_level_critical_min: int | None = Field(default=None, ge=1, le=3)
    trade_cert_requirements: dict[Trade, str] | None = None
    hook_transition_days: int | None = Field(default=None, ge=0, le=30)
    hook_critical_codes: list[str] | None = None
    hook_critical_transition_days: int | None = Field(default=None, ge=0, le=7)
    lifting_gear_colour_scheme: ColourScheme | None = None
    equipment_cert_warning_pct: DecimalStr | None = Field(
        default=None, ge=Decimal("80.0"), le=Decimal("100.0"), max_digits=4, decimal_places=1
    )
    personnel_cert_warning_pct: DecimalStr | None = Field(
        default=None, ge=Decimal("80.0"), le=Decimal("100.0"), max_digits=4, decimal_places=1
    )
    scaffold_tag_warning_pct: DecimalStr | None = Field(
        default=None, ge=Decimal("80.0"), le=Decimal("100.0"), max_digits=4, decimal_places=1
    )
    dangerous_defect_warning_count: int | None = Field(default=None, ge=1, le=20)
    ban_review_months: int | None = Field(default=None, ge=1, le=12)
    cert_scan_retention_years: int | None = Field(default=None, ge=1, le=10)


class ClientApprovalImpactItem(ApiModel):
    cert_kind: Literal["equipment", "personnel"]
    certificate_id: uuid.UUID
    cert_no: str
    tpi_code: str
    subject_ref: str = Field(examples=["RW-MC-03", "WKR-000019"])
    code: str = Field(description="Category or cert type not covered by a client approval.")
    not_in_force_from: date = Field(description="TP-5: 7 days after the switch unless covered.")


class CertSettingsUpdateResult(ApiModel):
    settings: CertSettingsRead
    client_approval_impact: list[ClientApprovalImpactItem] | None = Field(
        description="Only when require_client_approved_tpi was switched to true (TP-5)."
    )


# ---- catalogues (§3.16, BD-3) -----------------------------------------------------------------


class EquipmentCategoryInfo(ApiModel):
    code: EquipmentCertCategory
    label_en: str
    label_ar: str
    default_interval_months: int | None = Field(description="Null for scaffold (7 days).")
    interval_months: int | None = Field(description="This project's value (settings).")
    configuration_change_rule: bool = Field(description="'+ CF-1' categories.")
    hook_code: str = Field(examples=["CRANE-TPI"])
    operator_code: str | None = Field(examples=["CRANE-OPERATOR"])
    subtypes: list[EquipmentSubtype]
    subtype_required: bool


class CertTypeInfo(ApiModel):
    code: str = Field(pattern=CERT_TYPE_CODE)
    label_en: str
    label_ar: str
    default_cap_months: int
    cap_months: int
    satisfies: list[str] = Field(description="Hook codes met by an in-force certificate.")
    scope_categories_allowed: list[EquipmentCertCategory]
    levels_allowed: list[CertLevel]
    level_required: bool
    seeded: bool
    critical: bool = Field(description="In hook_critical_codes.")


class CategoryMapping(ApiModel):
    vehicle_category: VehicleCategory | None = None
    ptw_equipment_category: EquipmentCategory | None = None
    eqc: list[EquipmentCertCategory] = Field(description="Allowed EQC (other → any).")


class CertCatalogue(ApiModel):
    """GET /cert-catalogue?project_id=: lists EQC and PCT with this project's intervals and
    caps, the implemented hook codes (HK4-2), critical codes, and the VC → EQC / EQ → EQC
    mappings."""

    equipment_categories: list[EquipmentCategoryInfo]
    cert_types: list[CertTypeInfo]
    personnel_hook_codes: list[str]
    equipment_hook_codes: list[str]
    critical_codes: list[str]
    vehicle_mappings: list[CategoryMapping]
    ptw_mappings: list[CategoryMapping]


class CertTypeCreate(StrictInput):
    """Capability 124. A code that exists as a Phase 5 / training_course code (hook
    requirements or induction courses) → 422 CODE_IN_OTHER_CATALOGUE (BD-3); duplicate →
    409 DUPLICATE_VALUE."""

    code: str = Field(pattern=CERT_TYPE_CODE, examples=["HOIST-SIGNALLER"])
    label_en: str = Field(min_length=1, max_length=120)
    label_ar: str = Field(min_length=1, max_length=120)
    cap_months: int = Field(ge=6, le=120)
    scope_categories_allowed: list[EquipmentCertCategory] = Field(default_factory=list)
    levels_allowed: list[CertLevel] = Field(default_factory=list)


class CertTypeUpdate(PatchInput):
    """Labels only (codes immutable); caps via settings (shorten only)."""

    non_nullable = frozenset({"label_en", "label_ar"})

    label_en: str | None = Field(default=None, min_length=1, max_length=120)
    label_ar: str | None = Field(default=None, min_length=1, max_length=120)


# ---- hook policy (§3.14, §4.8, HK4-) -----------------------------------------------------------


class HookCodeState(ApiModel):
    code: str = Field(examples=["CRANE-OPERATOR"])
    critical: bool
    policy: HookCodePolicy = Field(description="Effective today.")
    block_from: date | None = Field(description="Local date the code blocks from (00:00).")
    switched_early_at: datetime | None
    implemented: bool = Field(description="HK4-2; others → unknown_code.")


class HookDeferralRead(ApiModel):
    original_date: date
    new_date: date
    reason: str
    by: UserRef
    at: datetime


class HookEarlySwitchRead(ApiModel):
    at: datetime
    by: UserRef
    all_codes: bool
    codes: list[str]


class HookPolicyStateRead(ApiModel):
    kind: HookKind = Field(
        description="personnel_certificate, equipment_certificate or (5-training §3.12) "
        "training_course."
    )
    stage: HookStage
    provider_registered_on: date | None
    critical_block_from: date | None
    general_block_from: date | None
    deferral: HookDeferralRead | None
    deferral_used: bool
    early_switches: list[HookEarlySwitchRead]
    codes: list[HookCodeState]
    next_block_date: date | None


class HookPolicyRead(ApiModel):
    project_id: uuid.UUID
    enabled: bool = Field(description="Phase 4 enabled on the project (HK4-1).")
    training_enabled: bool = Field(
        default=False,
        description="5-training HK5-1: training hooks enabled (POST /projects/{id}/training-hooks"
        "/enable); `kinds` then includes training_course.",
    )
    medical_enabled: bool = Field(
        default=False,
        description="6a HK6-1: medical hooks enabled (POST /projects/{id}/medical-hooks/enable); "
        "`kinds` then includes medical_fitness.",
    )
    as_of: date
    kinds: list[HookPolicyStateRead]


class HookEnableRequest(StrictInput):
    """HK4-1 (capability 124): register the Phase 4 providers on the project; dates per §6.5.
    Already enabled → 409 INVALID_TRANSITION."""

    registered_on: date | None = Field(default=None, description="Default today (local).")


class HookSwitchRequest(StrictInput):
    """HK4-5 early switch (capability 124; kind training_course: capability 145, HK5-5):
    `policy` block for the listed codes (or all) — always allowed, effective at once, audited,
    alerted. `policy` warn on a blocked code → 422 HOOK_POLICY_LOOSENING (a return to warn needs
    a spec change)."""

    all_codes: bool = False
    codes: list[str] = Field(default_factory=list)
    policy: Literal["block", "warn"] = "block"


class HookDeferralRequest(StrictInput):
    """HK4-6 (capability 124; kind training_course: capability 145, HK5-5): general_block_from
    later, once per project and kind (422 DEFERRAL_USED), ≤ 30 days (422 DEFERRAL_TOO_LONG),
    reason ≥ 30 chars. `codes` naming a critical code → 422 CRITICAL_CODE_NO_DEFERRAL."""

    new_date: date
    reason: str = Field(min_length=30, max_length=500)
    codes: list[str] = Field(
        default_factory=list,
        description="Optional; the deferral always applies to all non-critical codes.",
    )


class ReadinessSubject(ApiModel):
    subject_type: Literal["worker", "equipment", "scaffold"]
    subject_id: uuid.UUID
    ref: str = Field(examples=["WKR-000104", "FX-ACC-0219"])
    label: str | None = Field(description="Names only with capability 46.")
    reason_code: HookReasonCode | None = Field(
        description="Kind medical_fitness: only with capability 157 (tier 3, OH-2); else null "
        "and `band` is set."
    )
    band: HookBand | None = Field(
        default=None, description="Kind medical_fitness: display band (HK6-7) for every caller."
    )
    hard_stop: bool


class ReadinessCode(ApiModel):
    code: str
    critical: bool
    policy: HookCodePolicy
    block_from: date | None
    required: int
    in_force: int
    readiness_pct: DecimalStr | None = Field(description="§6.8, 1 dp; null when required = 0.")
    readiness_display: str
    not_met: list[ReadinessSubject]


class ReadinessAffected(ApiModel):
    """Live permits / WAPs / gates the block will affect (HK4-7 preview)."""

    on_date: date
    permits: list[PermitRef]
    wap_nos: list[str]
    gate_codes: list[str]


class HookReadinessReport(ApiModel):
    """HK4-7 (capability 122): never prevents the switch."""

    project_id: uuid.UUID
    kind: HookKind
    as_of: date
    stage: HookStage
    codes: list[ReadinessCode]
    affected: list[ReadinessAffected]
