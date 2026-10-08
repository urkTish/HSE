"""Phase 3 Permit-to-Work enumerations (spec 3-ptw §3, §4, §5).

Codes are stable (Phase 0 rule 48); EN/AR labels live in the reference lists (§3.16) or the
frontend i18n files. These enums are exported into the OpenAPI contract.
"""

from enum import StrEnum

# ---------------------------------------------------------------------------------------------
# Permit types, zone profile, adjacency (§3.1-§3.3)
# ---------------------------------------------------------------------------------------------


class PermitType(StrEnum):
    """§3.1 (display letters GW, HW, CS, WH, EX, EL, LF, RG, AW)."""

    general = "general"
    hot_work = "hot_work"
    confined_space = "confined_space"
    work_at_height = "work_at_height"
    excavation = "excavation"
    electrical_isolation = "electrical_isolation"
    lifting = "lifting"
    radiography = "radiography"
    airside_works = "airside_works"


PERMIT_TYPE_LETTERS: dict[PermitType, str] = {
    PermitType.general: "GW",
    PermitType.hot_work: "HW",
    PermitType.confined_space: "CS",
    PermitType.work_at_height: "WH",
    PermitType.excavation: "EX",
    PermitType.electrical_isolation: "EL",
    PermitType.lifting: "LF",
    PermitType.radiography: "RG",
    PermitType.airside_works: "AW",
}


class RevalidationRule(StrEnum):
    """§3.1 'Revalidation' column."""

    each_shift = "each_shift"
    one_handover = "one_handover"
    none = "none"


class HazardousAreaClass(StrEnum):
    """IEC 60079-10-1."""

    none = "none"
    zone_0 = "zone_0"
    zone_1 = "zone_1"
    zone_2 = "zone_2"


class Exposure(StrEnum):
    outdoor_direct_sun = "outdoor_direct_sun"
    outdoor_shaded = "outdoor_shaded"
    indoor = "indoor"


class VerticalRelation(StrEnum):
    none = "none"
    a_above_b = "a_above_b"
    b_above_a = "b_above_a"
    overlapping = "overlapping"


# ---------------------------------------------------------------------------------------------
# Appointments (§3.4, §4.7)
# ---------------------------------------------------------------------------------------------


class AppointmentFunction(StrEnum):
    issuer = "issuer"
    area_authority = "area_authority"
    isolation_authority = "isolation_authority"
    gas_tester = "gas_tester"
    authorised_person = "authorised_person"


class AppointmentDiscipline(StrEnum):
    """isolation_authority: electrical_lv / electrical_hv / mechanical_process; authorised_person:
    the rest plus electrical_lv / electrical_hv."""

    electrical_lv = "electrical_lv"
    electrical_hv = "electrical_hv"
    mechanical_process = "mechanical_process"
    lifting_appointed_person = "lifting_appointed_person"
    lift_supervisor = "lift_supervisor"
    excavation_competent_person = "excavation_competent_person"
    fall_protection_competent_person = "fall_protection_competent_person"
    radiation_protection_officer = "radiation_protection_officer"
    cse_rescue_lead = "cse_rescue_lead"


class AppointmentStatus(StrEnum):
    active = "active"
    suspended = "suspended"
    revoked = "revoked"
    expired = "expired"


# ---------------------------------------------------------------------------------------------
# Permit core (§3.5, §3.6, §4.1)
# ---------------------------------------------------------------------------------------------


class PermitStatus(StrEnum):
    """§4.1. Terminal: closed, cancelled, expired."""

    draft = "draft"
    requested = "requested"
    reviewed = "reviewed"
    approved = "approved"
    issued = "issued"
    active = "active"
    suspended = "suspended"
    closed = "closed"
    cancelled = "cancelled"
    expired = "expired"


PERMIT_TERMINAL: frozenset[PermitStatus] = frozenset(
    {PermitStatus.closed, PermitStatus.cancelled, PermitStatus.expired}
)
PERMIT_LIVE: frozenset[PermitStatus] = frozenset(
    {PermitStatus.issued, PermitStatus.active, PermitStatus.suspended}
)


class PermitAction(StrEnum):
    """Lifecycle actions (one endpoint each under /permits/{id}/…)."""

    request = "request"
    return_ = "return"
    review = "review"
    hse_review = "hse_review"
    approve = "approve"
    issue = "issue"
    start = "start"
    end_shift = "end_shift"
    suspend = "suspend"
    revalidate = "revalidate"
    resume = "resume"
    request_closure = "request_closure"
    close = "close"
    cancel = "cancel"
    lapse_issue = "lapse_issue"  # job: Issued → Approved
    expire = "expire"  # job
    handover = "handover"  # handover accepted (new shift)


class SignaturePurpose(StrEnum):
    """PT-15 signing transitions (each needs re-authentication within step_up_reauth_minutes)."""

    request = "request"
    review = "review"
    hse_review = "hse_review"
    approve = "approve"
    issue = "issue"
    accept = "accept"  # receiver acceptance of issue / revalidation / resume
    revalidate = "revalidate"
    resume = "resume"
    close = "close"
    cancel = "cancel"
    handover_accept = "handover_accept"
    residual_acceptance = "residual_acceptance"
    simops_coordination = "simops_coordination"
    gas_test = "gas_test"


class AcceptancePurpose(StrEnum):
    """What a receiver acceptance (made on the receiver's own device) is for."""

    issue = "issue"
    revalidate = "revalidate"
    resume = "resume"


class PtwCrewRole(StrEnum):
    """List CR (§3.16)."""

    worker = "worker"
    supervisor = "supervisor"
    hot_work_operative = "hot_work_operative"
    fire_watch = "fire_watch"
    entrant = "entrant"
    standby_person = "standby_person"
    rescue_lead = "rescue_lead"
    rescue_member = "rescue_member"
    gas_tester = "gas_tester"
    crane_operator = "crane_operator"
    rigger = "rigger"
    signaller = "signaller"
    lift_supervisor = "lift_supervisor"
    electrician = "electrician"
    competent_person = "competent_person"
    radiographer = "radiographer"
    rpo = "rpo"
    driver = "driver"
    banksman = "banksman"
    escort = "escort"


KEY_CREW_ROLES: frozenset[PtwCrewRole] = frozenset(
    {
        PtwCrewRole.supervisor,
        PtwCrewRole.fire_watch,
        PtwCrewRole.standby_person,
        PtwCrewRole.gas_tester,
        PtwCrewRole.crane_operator,
        PtwCrewRole.rigger,
        PtwCrewRole.signaller,
        PtwCrewRole.lift_supervisor,
        PtwCrewRole.radiographer,
        PtwCrewRole.rpo,
        PtwCrewRole.competent_person,
        PtwCrewRole.hot_work_operative,
        PtwCrewRole.rescue_lead,
    }
)


class CrewLineStatus(StrEnum):
    listed = "listed"
    excluded = "excluded"
    removed = "removed"


class EquipmentCategory(StrEnum):
    """List EQ (§3.16)."""

    tower_crane = "tower_crane"
    mobile_crane = "mobile_crane"
    crawler_crane = "crawler_crane"
    lifting_accessory = "lifting_accessory"
    spreader_beam = "spreader_beam"
    mewp = "mewp"
    man_basket = "man_basket"
    mast_climber = "mast_climber"
    bmu = "bmu"
    scaffold = "scaffold"
    welding_set = "welding_set"
    gas_cylinder_set = "gas_cylinder_set"
    ventilation_fan = "ventilation_fan"
    tripod_winch = "tripod_winch"
    voltage_tester = "voltage_tester"
    radiography_projector = "radiography_projector"
    survey_meter = "survey_meter"
    other = "other"


class EquipmentUse(StrEnum):
    lifting_appliance = "lifting_appliance"
    lifting_accessory = "lifting_accessory"
    access_equipment = "access_equipment"
    welding_set = "welding_set"
    gas_detector = "gas_detector"
    ventilation = "ventilation"
    rescue_equipment = "rescue_equipment"
    excavating_plant = "excavating_plant"
    radiography_source = "radiography_source"
    other = "other"


class DocumentType(StrEnum):
    """List D (§3.8)."""

    method_statement = "method_statement"
    risk_assessment = "risk_assessment"
    lift_plan = "lift_plan"
    critical_lift_plan = "critical_lift_plan"
    rescue_plan = "rescue_plan"
    excavation_plan = "excavation_plan"
    pe_design = "pe_design"
    utility_drawing = "utility_drawing"
    switching_programme = "switching_programme"
    radiation_protection_plan = "radiation_protection_plan"
    nrrc_licence = "nrrc_licence"
    fire_impairment_notice = "fire_impairment_notice"
    other = "other"


class StatusReason(StrEnum):
    """List SR (§3.16): suspension and cancellation reasons. Routine: shift_end, midday_ban."""

    shift_end = "shift_end"
    midday_ban = "midday_ban"
    shift_lapsed = "shift_lapsed"
    gas_test_failed = "gas_test_failed"
    gas_retest_overdue = "gas_retest_overdue"
    gas_alarm = "gas_alarm"
    wap_suspended = "wap_suspended"
    ops_suspension = "ops_suspension"
    notam_not_in_effect = "notam_not_in_effect"
    obs_not_active = "obs_not_active"
    simops_conflict = "simops_conflict"
    key_role_ineligible = "key_role_ineligible"
    hook_not_met = "hook_not_met"
    wind_limit = "wind_limit"
    weather = "weather"
    audit_critical = "audit_critical"
    stop_work = "stop_work"
    emergency = "emergency"
    contractor_suspended = "contractor_suspended"
    contractor_blacklisted = "contractor_blacklisted"
    isolation_breach = "isolation_breach"
    rejected = "rejected"
    not_required = "not_required"
    duplicate = "duplicate"
    other = "other"


ROUTINE_REASONS: frozenset[StatusReason] = frozenset(
    {StatusReason.shift_end, StatusReason.midday_ban}
)
CANCEL_REASONS: frozenset[StatusReason] = frozenset(
    {
        StatusReason.rejected,
        StatusReason.not_required,
        StatusReason.duplicate,
        StatusReason.contractor_suspended,
        StatusReason.contractor_blacklisted,
        StatusReason.other,
    }
)
MANUAL_SUSPEND_REASONS: frozenset[StatusReason] = frozenset(
    {
        StatusReason.stop_work,
        StatusReason.weather,
        StatusReason.emergency,
        StatusReason.gas_alarm,
        StatusReason.isolation_breach,
        StatusReason.other,
    }
)


class PermitBlocker(StrEnum):
    """List B (§3.16), in display order. A blocked transition returns 422 with detail.code =
    the first blocker and detail.meta.blockers = all of them."""

    JSA_MISSING = "JSA_MISSING"
    JSA_NOT_APPROVED = "JSA_NOT_APPROVED"
    JSA_RESIDUAL_EXTREME = "JSA_RESIDUAL_EXTREME"
    RESIDUAL_ACCEPTANCE_MISSING = "RESIDUAL_ACCEPTANCE_MISSING"
    HSE_REVIEW_MISSING = "HSE_REVIEW_MISSING"
    DOCUMENT_MISSING = "DOCUMENT_MISSING"
    CHECKLIST_INCOMPLETE = "CHECKLIST_INCOMPLETE"
    ROLE_MISSING = "ROLE_MISSING"
    APPOINTMENT_INVALID = "APPOINTMENT_INVALID"
    KEY_ROLE_INELIGIBLE = "KEY_ROLE_INELIGIBLE"
    NO_ELIGIBLE_CREW = "NO_ELIGIBLE_CREW"
    HOOK_NOT_MET = "HOOK_NOT_MET"
    GAS_TEST_REQUIRED = "GAS_TEST_REQUIRED"
    GAS_TEST_FAILED = "GAS_TEST_FAILED"
    GAS_TEST_EXPIRED = "GAS_TEST_EXPIRED"
    ISOLATION_NOT_VERIFIED = "ISOLATION_NOT_VERIFIED"
    PERSONAL_LOCKS_MISSING = "PERSONAL_LOCKS_MISSING"
    SIMOPS_PROHIBITED = "SIMOPS_PROHIBITED"
    SIMOPS_COORDINATION_REQUIRED = "SIMOPS_COORDINATION_REQUIRED"
    WAP_NOT_ACTIVE = "WAP_NOT_ACTIVE"
    WAP_CREW_MISSING = "WAP_CREW_MISSING"
    OUTSIDE_WAP_WINDOW = "OUTSIDE_WAP_WINDOW"
    NOTAM_NOT_IN_EFFECT = "NOTAM_NOT_IN_EFFECT"
    OBS_CLEARANCE_REQUIRED = "OBS_CLEARANCE_REQUIRED"
    WIND_LIMIT_EXCEEDED = "WIND_LIMIT_EXCEEDED"
    MIDDAY_BAN = "MIDDAY_BAN"
    OUTSIDE_WINDOW = "OUTSIDE_WINDOW"
    CONTRACTOR_SUSPENDED = "CONTRACTOR_SUSPENDED"
    LICENCE_INVALID = "LICENCE_INVALID"
    BARRIER_NOT_VERIFIED = "BARRIER_NOT_VERIFIED"
    FIRE_IMPAIRMENT_NOT_APPROVED = "FIRE_IMPAIRMENT_NOT_APPROVED"
    UTILITY_CLEARANCE_MISSING = "UTILITY_CLEARANCE_MISSING"
    FALL_CLEARANCE_INSUFFICIENT = "FALL_CLEARANCE_INSUFFICIENT"


class PermitWarningCode(StrEnum):
    """Non-blocking permit warnings (amber in the UI)."""

    HOOK_NOT_AVAILABLE = "HOOK_NOT_AVAILABLE"
    EXPIRING_7D = "EXPIRING_7D"
    EXPIRES_DURING_SHIFT = "EXPIRES_DURING_SHIFT"
    APPOINTMENT_EXPIRES = "APPOINTMENT_EXPIRES"
    SEVERITY_REDUCED_WITHOUT_HIGHER_CONTROL = "SEVERITY_REDUCED_WITHOUT_HIGHER_CONTROL"
    HOT_WORK_LATE = "HOT_WORK_LATE"
    POST_EXPIRY_CHECK_PENDING = "POST_EXPIRY_CHECK_PENDING"
    MIDDAY_BAN_PREWARN = "MIDDAY_BAN_PREWARN"
    EXEMPTION_ACTIVE = "EXEMPTION_ACTIVE"
    CREW_EXCLUDED = "CREW_EXCLUDED"
    SIMOPS_CONDITIONAL = "SIMOPS_CONDITIONAL"
    ISOLATIONS_STILL_APPLIED = "ISOLATIONS_STILL_APPLIED"
    POSSIBLE_ID_NUMBER = "POSSIBLE_ID_NUMBER"


class ChecklistAnswer(StrEnum):
    yes = "yes"
    no = "no"
    na = "n.a."


class ChecklistKind(StrEnum):
    pre_issue = "pre_issue"
    closure = "closure"


class PreIssueItem(StrEnum):
    """List C (§3.16)."""

    GW_01 = "GW-01"
    GW_02 = "GW-02"
    GW_03 = "GW-03"
    HW_01 = "HW-01"
    HW_02 = "HW-02"
    HW_03 = "HW-03"
    HW_04 = "HW-04"
    HW_05 = "HW-05"
    HW_06 = "HW-06"
    HW_07 = "HW-07"
    CS_01 = "CS-01"
    CS_02 = "CS-02"
    CS_03 = "CS-03"
    CS_04 = "CS-04"
    CS_05 = "CS-05"
    WH_01 = "WH-01"
    WH_02 = "WH-02"
    WH_03 = "WH-03"
    WH_04 = "WH-04"
    EX_01 = "EX-01"
    EX_02 = "EX-02"
    EX_03 = "EX-03"
    EX_04 = "EX-04"
    EX_05 = "EX-05"
    EL_01 = "EL-01"
    EL_02 = "EL-02"
    EL_03 = "EL-03"
    EL_04 = "EL-04"
    LF_01 = "LF-01"
    LF_02 = "LF-02"
    LF_03 = "LF-03"
    LF_04 = "LF-04"
    LF_05 = "LF-05"
    LF_06 = "LF-06"
    RG_01 = "RG-01"
    RG_02 = "RG-02"
    RG_03 = "RG-03"
    AW_01 = "AW-01"
    AW_02 = "AW-02"
    AW_03 = "AW-03"
    AW_04 = "AW-04"
    AW_05 = "AW-05"


class ClosureItem(StrEnum):
    """List X (§3.16)."""

    X_01 = "X-01"
    X_02 = "X-02"
    X_03 = "X-03"
    X_04 = "X-04"
    X_05 = "X-05"
    X_06 = "X-06"
    X_07 = "X-07"
    X_08 = "X-08"
    X_09 = "X-09"
    X_10 = "X-10"
    X_11 = "X-11"
    X_12 = "X-12"


class WorkStatus(StrEnum):
    """CL-1 closure request."""

    complete = "complete"
    incomplete_area_safe = "incomplete_area_safe"


class ExemptionKind(StrEnum):
    """PT-17: the only exemptions (capability 102)."""

    midday_ban = "midday_ban"  # HT-4
    energized_work = "energized_work"  # EL-3
    fire_impairment = "fire_impairment"  # HW-8
    lift_capacity_over_90 = "lift_capacity_over_90"  # LF-3


class MiddayExemptionReason(StrEnum):
    emergency_repair = "emergency_repair"
    exempt_activity_mhrsd = "exempt_activity_mhrsd"
    shaded_and_cooled_workplace = "shaded_and_cooled_workplace"


class ExemptionStatus(StrEnum):
    requested = "requested"
    granted = "granted"
    refused = "refused"
    withdrawn = "withdrawn"


# ---------------------------------------------------------------------------------------------
# Type sections (§3.7)
# ---------------------------------------------------------------------------------------------


class HotWorkKind(StrEnum):
    arc_welding = "arc_welding"
    gas_welding_cutting = "gas_welding_cutting"
    grinding = "grinding"
    torch_roofing = "torch_roofing"
    thermal_spraying = "thermal_spraying"
    brazing_soldering = "brazing_soldering"
    other_spark_flame = "other_spark_flame"


class ExtinguisherType(StrEnum):
    dcp_abc_6kg = "dcp_abc_6kg"
    co2_5kg = "co2_5kg"
    foam_9l = "foam_9l"
    water_9l = "water_9l"


class OpeningsProtected(StrEnum):
    na = "n.a."
    yes = "yes"


class CylinderKind(StrEnum):
    none = "none"
    oxy_fuel = "oxy_fuel"
    fuel_only = "fuel_only"
    inert_only = "inert_only"


class SpaceHazard(StrEnum):
    toxic = "toxic"
    flammable = "flammable"
    oxygen_deficiency = "oxygen_deficiency"
    oxygen_enrichment = "oxygen_enrichment"
    engulfment = "engulfment"
    entrapment_configuration = "entrapment_configuration"
    heat = "heat"
    mechanical = "mechanical"
    electrical = "electrical"
    other = "other"


class Ventilation(StrEnum):
    natural = "natural"
    forced_supply = "forced_supply"
    forced_extract = "forced_extract"
    none_justified = "none_justified"


class RescueMethod(StrEnum):
    non_entry_tripod_winch = "non_entry_tripod_winch"
    entry_rescue_team = "entry_rescue_team"
    external_rescue_service = "external_rescue_service"


class CommunicationMethod(StrEnum):
    voice_visual = "voice_visual"
    radio = "radio"
    rope_signal = "rope_signal"


class EntryDirection(StrEnum):
    in_ = "in"
    out = "out"


class AccessMethod(StrEnum):
    fixed_platform = "fixed_platform"
    scaffold = "scaffold"
    mewp = "mewp"
    ladder = "ladder"
    mast_climber = "mast_climber"
    suspended_platform_bmu = "suspended_platform_bmu"
    rope_access = "rope_access"
    slab_edge = "slab_edge"


class FallProtection(StrEnum):
    collective_only = "collective_only"
    restraint = "restraint"
    arrest_lanyard = "arrest_lanyard"
    arrest_srl = "arrest_srl"
    rope_access_two_rope = "rope_access_two_rope"


class ExcavationMethod(StrEnum):
    hand_dig = "hand_dig"
    mechanical = "mechanical"
    vacuum = "vacuum"
    trenchless = "trenchless"


class SoilType(StrEnum):
    rock = "rock"
    type_a = "type_a"
    type_b = "type_b"
    type_c = "type_c"


class ProtectiveSystem(StrEnum):
    none_lt_1_2m = "none_lt_1_2m"
    sloping = "sloping"
    benching = "benching"
    trench_box = "trench_box"
    shoring = "shoring"
    engineered_design = "engineered_design"


class Egress(StrEnum):
    ladder = "ladder"
    ramp = "ramp"
    stairs = "stairs"


class ExcavationInspectionResult(StrEnum):
    safe = "safe"
    unsafe = "unsafe"


class VoltageClass(StrEnum):
    elv = "elv"
    lv = "lv"
    hv = "hv"


class WorkCondition(StrEnum):
    electrically_safe = "electrically_safe"
    energized = "energized"


class EnergizedJustification(StrEnum):
    greater_hazard_if_deenergized = "greater_hazard_if_deenergized"
    infeasible_due_to_design = "infeasible_due_to_design"
    diagnostic_testing_only = "diagnostic_testing_only"


class LiftCriticalReason(StrEnum):
    """LF-2."""

    capacity = "capacity"
    tandem = "tandem"
    personnel_lift = "personnel_lift"
    gross_weight = "gross_weight"
    airside_movement_area = "airside_movement_area"
    overhead_lines = "overhead_lines"
    over_occupied_or_live = "over_occupied_or_live"


class WindSource(StrEnum):
    anemometer = "anemometer"
    handheld = "handheld"
    weather_service = "weather_service"


class RadiationSource(StrEnum):
    ir_192 = "ir_192"
    se_75 = "se_75"
    co_60 = "co_60"
    x_ray = "x_ray"


class AircraftProximity(StrEnum):
    stand_closed_notam = "stand_closed_notam"
    stand_closed_operator = "stand_closed_operator"
    no_stand_in_zone = "no_stand_in_zone"
    live_stand_adjacent = "live_stand_adjacent"


# ---------------------------------------------------------------------------------------------
# JSA (§3.8, §4.3, §6.1)
# ---------------------------------------------------------------------------------------------


class Hazard(StrEnum):
    """List H (§3.16)."""

    fall_from_height = "fall_from_height"
    falling_objects = "falling_objects"
    fire_explosion = "fire_explosion"
    toxic_atmosphere = "toxic_atmosphere"
    oxygen_deficiency = "oxygen_deficiency"
    engulfment = "engulfment"
    electric_shock = "electric_shock"
    arc_flash = "arc_flash"
    struck_by_load = "struck_by_load"
    crane_overturn = "crane_overturn"
    excavation_collapse = "excavation_collapse"
    buried_services = "buried_services"
    ionising_radiation = "ionising_radiation"
    heat_stress = "heat_stress"
    hot_surfaces_burns = "hot_surfaces_burns"
    noise = "noise"
    manual_handling = "manual_handling"
    moving_plant = "moving_plant"
    aircraft_jet_blast = "aircraft_jet_blast"
    fod = "fod"
    stored_energy = "stored_energy"
    chemical_exposure = "chemical_exposure"
    dropped_tools = "dropped_tools"
    weather_wind = "weather_wind"
    slips_trips = "slips_trips"
    other = "other"


class RiskBand(StrEnum):
    """JS-2: Low 1-4, Medium 5-9, High 10-14, Extreme 15-25."""

    low = "low"
    medium = "medium"
    high = "high"
    extreme = "extreme"


class JsaStatus(StrEnum):
    """§4.3."""

    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    superseded = "superseded"
    review_due = "review_due"


class JsaWarningCode(StrEnum):
    SEVERITY_REDUCED_WITHOUT_HIGHER_CONTROL = "SEVERITY_REDUCED_WITHOUT_HIGHER_CONTROL"
    POSSIBLE_ID_NUMBER = "POSSIBLE_ID_NUMBER"


# ---------------------------------------------------------------------------------------------
# Gas detectors and tests (§3.9, §3.10, §4.6, §6.2, §6.3)
# ---------------------------------------------------------------------------------------------


class GasSensor(StrEnum):
    o2 = "o2"
    lel = "lel"
    h2s = "h2s"
    co = "co"
    voc_pid = "voc_pid"
    nh3 = "nh3"
    so2 = "so2"
    other = "other"


class LelReferenceGas(StrEnum):
    methane = "methane"
    pentane = "pentane"
    propane = "propane"
    hydrogen = "hydrogen"


class DetectorStatus(StrEnum):
    in_service = "in_service"
    quarantined = "quarantined"
    retired = "retired"


class QuarantineReason(StrEnum):
    bump_test_failed = "bump_test_failed"
    calibration_overdue = "calibration_overdue"


class BumpTestResult(StrEnum):
    pass_ = "pass"
    fail = "fail"


class GasTestType(StrEnum):
    pre_issue = "pre_issue"
    pre_entry = "pre_entry"
    periodic = "periodic"
    post_break = "post_break"
    revalidation = "revalidation"
    post_alarm = "post_alarm"


class GasReadingPoint(StrEnum):
    top = "top"
    middle = "middle"
    bottom = "bottom"
    at_work_point = "at_work_point"
    outside = "outside"


class GasTestResult(StrEnum):
    pass_ = "pass"
    fail = "fail"


class GasFailCode(StrEnum):
    O2_OUT_OF_RANGE = "O2_OUT_OF_RANGE"
    LEL_ABOVE_LIMIT = "LEL_ABOVE_LIMIT"
    H2S_ABOVE_LIMIT = "H2S_ABOVE_LIMIT"
    CO_ABOVE_LIMIT = "CO_ABOVE_LIMIT"
    OTHER_ABOVE_LIMIT = "OTHER_ABOVE_LIMIT"


class GasLimitProfile(StrEnum):
    """§6.2 columns."""

    general = "general"  # general / cold work, excavation
    confined_space = "confined_space"
    hot_work = "hot_work"


class GasStatus(StrEnum):
    """Live gas status of a permit (board chip)."""

    not_required = "not_required"
    valid = "valid"
    due_soon = "due_soon"
    overdue = "overdue"
    failed = "failed"
    missing = "missing"


# ---------------------------------------------------------------------------------------------
# Isolations / LOTO (§3.11, §4.4, §4.5)
# ---------------------------------------------------------------------------------------------


class EnergyType(StrEnum):
    electrical = "electrical"
    mechanical = "mechanical"
    hydraulic = "hydraulic"
    pneumatic = "pneumatic"
    process_fluid = "process_fluid"
    thermal = "thermal"
    gravity = "gravity"
    stored_spring = "stored_spring"
    chemical = "chemical"
    radiation = "radiation"


class IsolationMethod(StrEnum):
    breaker_racked_out = "breaker_racked_out"
    fuse_removed = "fuse_removed"
    isolator_open_locked = "isolator_open_locked"
    cable_disconnected = "cable_disconnected"
    earth_applied = "earth_applied"
    valve_closed_locked = "valve_closed_locked"
    spade_blind = "spade_blind"
    double_block_bleed = "double_block_bleed"
    disconnect_removed_spool = "disconnect_removed_spool"
    mechanical_pin_block = "mechanical_pin_block"
    bleed_vent_drain = "bleed_vent_drain"
    other = "other"


class VerificationMethod(StrEnum):
    try_out_start_attempt = "try_out_start_attempt"
    test_for_dead = "test_for_dead"
    pressure_gauge_zero = "pressure_gauge_zero"
    visual_air_gap = "visual_air_gap"
    other = "other"


class IsolationStatus(StrEnum):
    """§4.4."""

    planned = "planned"
    isolated = "isolated"
    verified = "verified"
    deisolation_requested = "deisolation_requested"
    deisolated = "deisolated"
    cancelled = "cancelled"


class LockType(StrEnum):
    isolation_lock = "isolation_lock"
    personal_lock = "personal_lock"
    lockbox = "lockbox"


class LockStatus(StrEnum):
    """§4.5."""

    available = "available"
    applied = "applied"
    lost = "lost"
    cut = "cut"
    retired = "retired"


class PersonalLockRemoval(StrEnum):
    holder = "holder"
    cut = "cut"


# ---------------------------------------------------------------------------------------------
# SIMOPS (§3.12, §4.8, §5.6)
# ---------------------------------------------------------------------------------------------


class SimopsRuleCode(StrEnum):
    """Default rules SM-R01…SM-R12 (codes immutable; cannot be deleted). Custom rules use
    SM-R13 and up (free string on SimopsRule.rule_code)."""

    SM_R01 = "SM-R01"
    SM_R02 = "SM-R02"
    SM_R03 = "SM-R03"
    SM_R04 = "SM-R04"
    SM_R05a = "SM-R05a"
    SM_R05b = "SM-R05b"
    SM_R06 = "SM-R06"
    SM_R07 = "SM-R07"
    SM_R08 = "SM-R08"
    SM_R09 = "SM-R09"
    SM_R10 = "SM-R10"
    SM_R11 = "SM-R11"
    SM_R12 = "SM-R12"


class SimopsCondition(StrEnum):
    """§5.6 table 'Condition' column (the engine's evaluators)."""

    within_barrier = "within_barrier"  # R01 distance ≤ A.planned_barrier_m
    within_threshold = "within_threshold"  # distance ≤ threshold_m
    within_combustible_clearance = "within_combustible_clearance"  # R03
    within_exclusion_radius = "within_exclusion_radius"  # R05a
    within_slew_radius = "within_slew_radius"  # R05b
    above_within_drop_zone = "above_within_drop_zone"  # R06
    hot_work_above_within_clearance = "hot_work_above_within_clearance"  # R07
    within_surcharge_zone = "within_surcharge_zone"  # R08
    same_zone = "same_zone"  # R10, R12
    slew_overlap = "slew_overlap"  # R11


class SimopsTypeSelector(StrEnum):
    """Permit B selector of a rule (or A for custom rules): a permit type, `any`, or a
    characteristic."""

    any = "any"
    general = "general"
    hot_work = "hot_work"
    confined_space = "confined_space"
    work_at_height = "work_at_height"
    excavation = "excavation"
    electrical_isolation = "electrical_isolation"
    lifting = "lifting"
    radiography = "radiography"
    airside_works = "airside_works"
    flammables_in_use = "flammables_in_use"
    gas_test_required = "gas_test_required"
    lifting_or_excavating_plant = "lifting_or_excavating_plant"
    combustion_engine_plant = "combustion_engine_plant"
    energized_electrical = "energized_electrical"
    crane = "crane"
    other_contractor_movement_area = "other_contractor_movement_area"


class SimopsResult(StrEnum):
    prohibited = "prohibited"
    conditional = "conditional"
    allowed = "allowed"


class SimopsConflictStatus(StrEnum):
    open = "open"
    coordinated = "coordinated"
    resolved_by_change = "resolved_by_change"
    closed = "closed"


class DistanceBasis(StrEnum):
    """SM-2: how the distance was obtained."""

    grid = "grid"
    same_zone = "same_zone"
    adjacency = "adjacency"


class SimopsCheckTrigger(StrEnum):
    preview = "preview"
    request = "request"
    review = "review"
    approve = "approve"
    issue = "issue"
    start = "start"
    revalidate = "revalidate"
    resume = "resume"
    change = "change"
    manual = "manual"


class CoordinationStatus(StrEnum):
    pending_signatures = "pending_signatures"
    signed = "signed"
    expired = "expired"


class CoordinationSignerRole(StrEnum):
    issuer_a = "issuer_a"
    issuer_b = "issuer_b"
    area_authority = "area_authority"


# ---------------------------------------------------------------------------------------------
# Shifts, handover, suspension (§3.13, §3.14, §4.2)
# ---------------------------------------------------------------------------------------------


class ShiftEndType(StrEnum):
    handover = "handover"
    shift_end = "shift_end"
    suspended = "suspended"
    lapsed = "lapsed"
    closed = "closed"
    expired = "expired"


class PauseReason(StrEnum):
    break_ = "break"
    prayer = "prayer"
    weather = "weather"
    other = "other"


class HandoverStatus(StrEnum):
    initiated = "initiated"
    accepted = "accepted"
    lapsed = "lapsed"


# ---------------------------------------------------------------------------------------------
# PTW audits (§3.15, §4.9)
# ---------------------------------------------------------------------------------------------


class PtwAuditType(StrEnum):
    field = "field"
    document_review = "document_review"
    unpermitted_work = "unpermitted_work"


class PtwAuditStatus(StrEnum):
    draft = "draft"
    completed = "completed"
    locked = "locked"


class AuditAnswer(StrEnum):
    compliant = "compliant"
    non_compliant = "non_compliant"
    na = "n.a."


class AuditFindingSeverity(StrEnum):
    minor = "minor"
    major = "major"
    critical = "critical"


class AuditItem(StrEnum):
    """List A (§3.16)."""

    A00 = "A00"
    A01 = "A01"
    A02 = "A02"
    A03 = "A03"
    A04 = "A04"
    A05 = "A05"
    A06 = "A06"
    A07 = "A07"
    A08 = "A08"
    A09 = "A09"
    A10 = "A10"
    A11 = "A11"
    A12 = "A12"
    A13 = "A13"
    A14 = "A14"
    A15 = "A15"
    A16 = "A16"
    A17 = "A17"
    A18 = "A18"
    A19 = "A19"
    A20 = "A20"


# ---------------------------------------------------------------------------------------------
# KPIs, board, registers (§6.11, §8)
# ---------------------------------------------------------------------------------------------


class PtwKpiGroupBy(StrEnum):
    """T15 group_by (KP-5)."""

    type = "type"
    contractor = "contractor"
    zone = "zone"
    month = "month"
    week = "week"
    suspension_reason = "suspension_reason"
    audit_item = "audit_item"
    simops_rule = "simops_rule"


class PermitRegisterSort(StrEnum):
    newest = "newest"
    valid_from = "valid_from"
    valid_to = "valid_to"
    permit_no = "permit_no"
