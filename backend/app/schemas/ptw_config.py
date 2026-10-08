"""PTW configuration: permit types, zone PTW profiles, zone adjacency, SIMOPS matrix, the 5×5
risk matrix and the Phase 3 project settings (spec 3-ptw §3.1-§3.3, §3.12, §3.17, §6.1)."""

import uuid
from datetime import datetime, time
from decimal import Decimal
from typing import Any

from pydantic import Field

from app.core.access_enums import HookKind, HookPolicy
from app.core.ptw_enums import (
    AppointmentFunction,
    ClosureItem,
    DocumentType,
    EquipmentCategory,
    Exposure,
    GasLimitProfile,
    GasSensor,
    Hazard,
    HazardousAreaClass,
    PermitType,
    PreIssueItem,
    PtwCrewRole,
    RevalidationRule,
    RiskBand,
    SimopsCondition,
    SimopsResult,
    SimopsTypeSelector,
    VerticalRelation,
)
from app.schemas.access_common import HookRequirement, HookRequirementRead
from app.schemas.common import ApiModel, PatchInput, StrictInput
from app.schemas.hse_common import DecimalStr, UserRef, ZoneRef
from app.schemas.ptw_common import Dec1

# ---- permit types (§3.1) ------------------------------------------------------------------------


class PermitTypeConfigRead(ApiModel):
    """§3.1 row of a project. Durations come from the settings key type_max_duration_days."""

    project_id: uuid.UUID
    type: PermitType
    ref_letter: str = Field(examples=["HW"])
    label_en: str
    label_ar: str
    max_duration_days: int
    max_duration_days_critical: int | None = Field(
        description="lifting only: critical lifts (always 1)."
    )
    max_shift_hours: int
    revalidation: RevalidationRule
    gas_test_rule_en: str = Field(description="§3.1 'Gas test' column, for display.")
    gas_test_rule_ar: str
    hse_review_rule_en: str = Field(description="§3.1 'HSE review' column, for display.")
    hse_review_rule_ar: str
    mandatory_crew_roles: list[PtwCrewRole] = Field(
        description="Always required crew roles (conditional ones are explained in the rule "
        "texts and enforced as ROLE_MISSING)."
    )
    mandatory_documents: list[DocumentType] = Field(
        description="Always required documents (conditional ones: DOCUMENT_MISSING)."
    )
    pre_issue_checklist: list[PreIssueItem] = Field(description="List C codes for this type.")
    closure_checklist: list[ClosureItem] = Field(description="List X codes for this type.")
    mandatory_hazards: list[Hazard] = Field(description="JS-4 (conditional extras added).")
    hook_requirements_by_crew_role: dict[PtwCrewRole, list[HookRequirementRead]] = Field(
        description="HK3-2, e.g. crane_operator → personnel_certificate CRANE-OPERATOR."
    )
    hook_requirements_by_equipment: dict[EquipmentCategory, list[HookRequirementRead]] = Field(
        description="HK3-2, e.g. tower_crane → equipment_certificate CRANE-TPI."
    )
    updated_at: datetime | None
    updated_by: UserRef | None


class PermitTypeConfigUpdate(PatchInput):
    """Capability 99, audited. Items may be added; the spec defaults of each list cannot be
    removed (422 VALIDATION_ERROR)."""

    non_nullable = frozenset(
        {
            "pre_issue_checklist",
            "closure_checklist",
            "mandatory_hazards",
            "hook_requirements_by_crew_role",
            "hook_requirements_by_equipment",
        }
    )

    pre_issue_checklist: list[PreIssueItem] | None = None
    closure_checklist: list[ClosureItem] | None = None
    mandatory_hazards: list[Hazard] | None = None
    hook_requirements_by_crew_role: dict[PtwCrewRole, list[HookRequirement]] | None = None
    hook_requirements_by_equipment: dict[EquipmentCategory, list[HookRequirement]] | None = None


class PermitTypeConfigList(ApiModel):
    items: list[PermitTypeConfigRead]
    hook_requirements_by_appointment: dict[AppointmentFunction, list[HookRequirementRead]] = Field(
        description="HK3-2 appointment hooks: issuer → PTW-ISSUER, isolation_authority → "
        "LOTO-AUTHORITY (receiver PTW-RECEIVER is evaluated on the receiver's linked worker)."
    )


# ---- zone PTW profile (§3.2) --------------------------------------------------------------------


class ZonePtwProfileRead(ApiModel):
    """1:1 with zone; created with PT-3 defaults."""

    zone: ZoneRef
    permit_required_all_work: bool
    gas_test_zone: bool
    hazardous_area_class: HazardousAreaClass
    hazardous_area_note: str | None
    default_exposure: Exposure
    fire_protection_present: bool
    level_datum_note: str | None
    default_area_authority_ids: list[uuid.UUID]
    default_area_authorities: list[UserRef]
    in_movement_area: bool = Field(description="From the zone's airside attributes.")
    updated_at: datetime | None
    updated_by: UserRef | None


class ZonePtwProfileUpdate(PatchInput):
    """Capability 98, audited. permit_required_all_work = false on a movement-area zone → 422
    PROFILE_LOOSENING (PT-3). hazardous_area_note is required iff class ≠ none."""

    non_nullable = frozenset(
        {
            "permit_required_all_work",
            "gas_test_zone",
            "hazardous_area_class",
            "default_exposure",
            "fire_protection_present",
            "default_area_authority_ids",
        }
    )

    permit_required_all_work: bool | None = None
    gas_test_zone: bool | None = None
    hazardous_area_class: HazardousAreaClass | None = None
    hazardous_area_note: str | None = Field(default=None, max_length=200)
    default_exposure: Exposure | None = None
    fire_protection_present: bool | None = None
    level_datum_note: str | None = Field(default=None, max_length=100)
    default_area_authority_ids: list[uuid.UUID] | None = Field(
        default=None,
        description="Users with an Active area_authority appointment covering the zone.",
    )


# ---- zone adjacency (§3.3) ----------------------------------------------------------------------


class ZoneAdjacencyCreate(StrictInput):
    """Capability 98. Same project, a ≠ b, unordered pair unique (409 DUPLICATE_VALUE)."""

    zone_a_id: uuid.UUID
    zone_b_id: uuid.UUID
    distance_m: Dec1 = Field(description="Closest edge-to-edge; 0 = touching/overlapping.")
    vertical_relation: VerticalRelation = VerticalRelation.none


class ZoneAdjacencyUpdate(PatchInput):
    non_nullable = frozenset({"distance_m", "vertical_relation"})

    distance_m: Dec1 | None = None
    vertical_relation: VerticalRelation | None = None


class ZoneAdjacencyRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    zone_a: ZoneRef
    zone_b: ZoneRef
    distance_m: DecimalStr
    vertical_relation: VerticalRelation
    updated_at: datetime


# ---- SIMOPS matrix (§3.12, SM-3) ----------------------------------------------------------------


class SimopsRuleRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    rule_code: str = Field(examples=["SM-R03"], description="Immutable.")
    is_default: bool = Field(description="SM-R01…SM-R12: cannot be deleted or loosened.")
    type_a: SimopsTypeSelector
    type_b: SimopsTypeSelector
    condition: SimopsCondition
    condition_en: str = Field(description="§5.6 'Condition' text for display.")
    condition_ar: str
    threshold_m: DecimalStr | None = Field(
        description="Fixed threshold (null when the rule uses a permit value, e.g. R01 barrier)."
    )
    result: SimopsResult
    required_controls_en: str | None
    required_controls_ar: str | None
    active: bool
    updated_at: datetime
    updated_by: UserRef | None


class SimopsRuleCreate(StrictInput):
    """Capability 99. A custom rule gets the next code SM-R13, SM-R14, …"""

    type_a: SimopsTypeSelector
    type_b: SimopsTypeSelector
    condition: SimopsCondition
    threshold_m: Dec1 | None = None
    result: SimopsResult
    required_controls_en: str | None = Field(default=None, max_length=1000)
    required_controls_ar: str | None = Field(default=None, max_length=1000)


class SimopsRuleUpdate(PatchInput):
    """Capability 99, audited. Default rules may only be tightened: threshold up, result
    allowed → conditional → prohibited (422 SIMOPS_RULE_LOCKED otherwise)."""

    non_nullable = frozenset({"result", "active"})

    threshold_m: Dec1 | None = None
    result: SimopsResult | None = None
    required_controls_en: str | None = Field(default=None, max_length=1000)
    required_controls_ar: str | None = Field(default=None, max_length=1000)
    active: bool | None = Field(default=None, description="Custom rules only.")


class SimopsRuleList(ApiModel):
    items: list[SimopsRuleRead]


# ---- risk matrix (§6.1) -------------------------------------------------------------------------


class RiskMatrixCell(ApiModel):
    likelihood: int = Field(ge=1, le=5)
    severity: int = Field(ge=1, le=5)
    score: int
    band: RiskBand


class RiskBandInfo(ApiModel):
    band: RiskBand
    min_score: int
    max_score: int
    label_en: str
    label_ar: str
    acceptance_en: str = Field(description="JS-7 acceptance authority.")
    acceptance_ar: str


class RiskMatrixRead(ApiModel):
    """The 5×5 matrix (JS-2, §6.1) for rendering; scores are computed by the server."""

    cells: list[RiskMatrixCell]
    bands: list[RiskBandInfo]


# ---- Phase 3 settings (§3.17) -------------------------------------------------------------------


class GasLimitSet(StrictInput):
    """§6.2 column. O₂ inclusive range; the others are 'below' limits (pass iff x < max)."""

    o2_min_pct: DecimalStr = Field(max_digits=4, decimal_places=1)
    o2_max_pct: DecimalStr = Field(max_digits=4, decimal_places=1)
    lel_below_pct: DecimalStr = Field(max_digits=4, decimal_places=1)
    h2s_below_ppm: DecimalStr = Field(max_digits=5, decimal_places=1)
    co_below_ppm: DecimalStr = Field(max_digits=5, decimal_places=1)


class OtherGasLimit(StrictInput):
    gas: str = Field(min_length=1, max_length=40, examples=["NH3"])
    sensor: GasSensor | None = None
    unit: str = Field(max_length=10, examples=["ppm"])
    below: DecimalStr = Field(gt=Decimal(0), max_digits=8, decimal_places=2, description="TLV")


class GasLimits(StrictInput):
    by_profile: dict[GasLimitProfile, GasLimitSet]
    other_toxics: list[OtherGasLimit] = Field(default_factory=list)


class MiddayBanPeriod(StrictInput):
    start_mmdd: str = Field(pattern=r"^\d{2}-\d{2}$", examples=["06-15"])
    end_mmdd: str = Field(pattern=r"^\d{2}-\d{2}$", examples=["09-15"], description="Inclusive.")


class MiddayBanHours(StrictInput):
    start_local: time = Field(examples=["12:00"])
    end_local: time = Field(examples=["15:00"])


class PtwSettingsRead(ApiModel):
    """Every key of §3.17 (HSE Manager only to change, capability 99, audited)."""

    project_id: uuid.UUID
    ptw_shift_max_hours: int
    issue_to_start_max_minutes: int
    max_active_permits_per_receiver: int
    type_max_duration_days: dict[PermitType, int]
    critical_lift_max_duration_days: int = Field(description="Always 1 (Allowed: 1 only).")
    gas_pre_start_validity_minutes: int
    gas_retest_interval_minutes: dict[PermitType, int] = Field(
        description="confined_space 60, hot_work 120, excavation 120, general 240 (defaults)."
    )
    gas_break_retest_minutes: int
    gas_limits: GasLimits
    detector_calibration_interval_days: int
    fire_watch_post_minutes: int
    hw_combustible_clearance_m: DecimalStr
    hw_extinguisher_max_m: DecimalStr
    airside_hotwork_separation_m: DecimalStr
    wah_permit_threshold_m: DecimalStr
    wah_rescue_max_minutes: int
    cse_rescue_max_minutes: int
    cse_heat_control_temp_c: DecimalStr
    ex_permit_depth_m: DecimalStr
    ex_protective_system_depth_m: DecimalStr
    ex_pe_design_depth_m: DecimalStr
    ex_spoil_setback_m: DecimalStr
    ex_egress_max_m: DecimalStr
    ex_hand_dig_distance_m: DecimalStr
    critical_lift_capacity_pct: int
    critical_lift_weight_t: DecimalStr
    lift_wind_limit_ms: DecimalStr
    man_basket_wind_limit_ms: DecimalStr
    rg_barrier_limit_usv_h: DecimalStr
    drop_zone_radius_m: DecimalStr
    vertical_separation_m: DecimalStr
    midday_ban_period: MiddayBanPeriod
    midday_ban_hours: MiddayBanHours
    midday_ban_prewarn_minutes: int
    jsa_review_months: int
    long_term_isolation_days: int
    appointment_max_months: int
    ptw_audit_min_per_week: int
    ptw_audit_warning_pct: DecimalStr
    ptw_critical_findings_warning: int
    ptw_closure_warning_pct: DecimalStr
    step_up_reauth_minutes: int
    ptw_retention_years: int
    hook_policy: dict[HookKind, HookPolicy] = Field(
        description="Phase 2 key, shown read-only here; change it on /access-settings."
    )
    updated_at: datetime | None
    updated_by: UserRef | None


def _dec(lo: str, hi: str, digits: int = 5, places: int = 1) -> Any:
    return Field(
        default=None,
        ge=Decimal(lo),
        le=Decimal(hi),
        max_digits=digits,
        decimal_places=places,
        description=f"Allowed {lo}–{hi}.",
    )


class PtwSettingsUpdate(PatchInput):
    """Partial update (capability 99, audited). Only the 'Allowed' ranges of §3.17 are accepted
    (422 otherwise); gas_limits may only be tightened; midday ban period/hours may only widen;
    type_max_duration_days: general/WAH/excavation/electrical/airside/lifting 1–14, hot_work 1–7,
    confined_space and radiography 1 only (AC9)."""

    non_nullable = frozenset(
        {
            "ptw_shift_max_hours",
            "issue_to_start_max_minutes",
            "max_active_permits_per_receiver",
            "type_max_duration_days",
            "gas_pre_start_validity_minutes",
            "gas_retest_interval_minutes",
            "gas_break_retest_minutes",
            "gas_limits",
            "detector_calibration_interval_days",
            "fire_watch_post_minutes",
            "hw_combustible_clearance_m",
            "hw_extinguisher_max_m",
            "airside_hotwork_separation_m",
            "wah_permit_threshold_m",
            "wah_rescue_max_minutes",
            "cse_rescue_max_minutes",
            "cse_heat_control_temp_c",
            "ex_permit_depth_m",
            "ex_protective_system_depth_m",
            "ex_pe_design_depth_m",
            "ex_spoil_setback_m",
            "ex_egress_max_m",
            "ex_hand_dig_distance_m",
            "critical_lift_capacity_pct",
            "critical_lift_weight_t",
            "lift_wind_limit_ms",
            "man_basket_wind_limit_ms",
            "rg_barrier_limit_usv_h",
            "drop_zone_radius_m",
            "vertical_separation_m",
            "midday_ban_period",
            "midday_ban_hours",
            "midday_ban_prewarn_minutes",
            "jsa_review_months",
            "long_term_isolation_days",
            "appointment_max_months",
            "ptw_audit_min_per_week",
            "ptw_audit_warning_pct",
            "ptw_critical_findings_warning",
            "ptw_closure_warning_pct",
            "step_up_reauth_minutes",
            "ptw_retention_years",
        }
    )

    ptw_shift_max_hours: int | None = Field(default=None, ge=4, le=12)
    issue_to_start_max_minutes: int | None = Field(default=None, ge=15, le=120)
    max_active_permits_per_receiver: int | None = Field(default=None, ge=1, le=10)
    type_max_duration_days: dict[PermitType, int] | None = None
    gas_pre_start_validity_minutes: int | None = Field(default=None, ge=10, le=60)
    gas_retest_interval_minutes: dict[PermitType, int] | None = Field(
        default=None, description="Each 15–240."
    )
    gas_break_retest_minutes: int | None = Field(default=None, ge=15, le=60)
    gas_limits: GasLimits | None = None
    detector_calibration_interval_days: int | None = Field(default=None, ge=30, le=180)
    fire_watch_post_minutes: int | None = Field(default=None, ge=60, le=240)
    hw_combustible_clearance_m: DecimalStr | None = _dec("11.0", "20.0")
    hw_extinguisher_max_m: DecimalStr | None = _dec("3.0", "9.0")
    airside_hotwork_separation_m: DecimalStr | None = _dec("15.0", "50.0")
    wah_permit_threshold_m: DecimalStr | None = _dec("1.2", "1.8")
    wah_rescue_max_minutes: int | None = Field(default=None, ge=5, le=15)
    cse_rescue_max_minutes: int | None = Field(default=None, ge=2, le=10)
    cse_heat_control_temp_c: DecimalStr | None = _dec("30.0", "40.0")
    ex_permit_depth_m: DecimalStr | None = _dec("0.6", "1.2")
    ex_protective_system_depth_m: DecimalStr | None = _dec("0.6", "1.2")
    ex_pe_design_depth_m: DecimalStr | None = _dec("3.0", "6.0")
    ex_spoil_setback_m: DecimalStr | None = _dec("0.6", "2.0")
    ex_egress_max_m: DecimalStr | None = _dec("3.0", "7.5")
    ex_hand_dig_distance_m: DecimalStr | None = _dec("0.5", "3.0")
    critical_lift_capacity_pct: int | None = Field(default=None, ge=50, le=90)
    critical_lift_weight_t: DecimalStr | None = _dec("5.0", "50.0")
    lift_wind_limit_ms: DecimalStr | None = _dec("5.0", "20.0")
    man_basket_wind_limit_ms: DecimalStr | None = _dec("5.0", "9.8")
    rg_barrier_limit_usv_h: DecimalStr | None = _dec("0.5", "7.5")
    drop_zone_radius_m: DecimalStr | None = _dec("3.0", "20.0")
    vertical_separation_m: DecimalStr | None = _dec("1.0", "5.0")
    midday_ban_period: MiddayBanPeriod | None = None
    midday_ban_hours: MiddayBanHours | None = None
    midday_ban_prewarn_minutes: int | None = Field(default=None, ge=5, le=60)
    jsa_review_months: int | None = Field(default=None, ge=3, le=24)
    long_term_isolation_days: int | None = Field(default=None, ge=1, le=30)
    appointment_max_months: int | None = Field(default=None, ge=1, le=24)
    ptw_audit_min_per_week: int | None = Field(default=None, ge=1, le=50)
    ptw_audit_warning_pct: DecimalStr | None = _dec("50", "100")
    ptw_critical_findings_warning: int | None = Field(default=None, ge=1, le=20)
    ptw_closure_warning_pct: DecimalStr | None = _dec("50", "100")
    step_up_reauth_minutes: int | None = Field(default=None, ge=5, le=60)
    ptw_retention_years: int | None = Field(default=None, ge=1, le=15)
