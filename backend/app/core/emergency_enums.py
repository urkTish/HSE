"""Phase 6c enumerations — emergency preparedness & drills (spec 6c-emergency-drills v1.0, §3.14
lists and §4 states). Exported into the OpenAPI contract so the frontend gets typed unions."""

from enum import StrEnum


class ScenarioType(StrEnum):
    """List ES (★ mandatory, ER-3)."""

    fire_explosion = "fire_explosion"
    medical_emergency = "medical_emergency"
    severe_weather = "severe_weather"
    confined_space_rescue = "confined_space_rescue"
    height_rescue = "height_rescue"
    structural_collapse = "structural_collapse"
    excavation_collapse = "excavation_collapse"
    gas_release = "gas_release"
    electrical_contact = "electrical_contact"
    utility_strike = "utility_strike"
    security_threat = "security_threat"
    aircraft_emergency = "aircraft_emergency"


class EventType(StrEnum):
    """§3.13: list ES ∪ {false_alarm, airport_aep_activation}."""

    fire_explosion = "fire_explosion"
    medical_emergency = "medical_emergency"
    severe_weather = "severe_weather"
    confined_space_rescue = "confined_space_rescue"
    height_rescue = "height_rescue"
    structural_collapse = "structural_collapse"
    excavation_collapse = "excavation_collapse"
    gas_release = "gas_release"
    electrical_contact = "electrical_contact"
    utility_strike = "utility_strike"
    security_threat = "security_threat"
    aircraft_emergency = "aircraft_emergency"
    false_alarm = "false_alarm"
    airport_aep_activation = "airport_aep_activation"


class ResponseType(StrEnum):
    """§3.2 (events add `none`)."""

    zone_evacuation = "zone_evacuation"
    site_evacuation = "site_evacuation"
    shelter_in_place = "shelter_in_place"
    local_response = "local_response"
    none = "none"


class DrillType(StrEnum):
    """List DT."""

    evacuation_full = "evacuation_full"
    evacuation_partial = "evacuation_partial"
    shelter_in_place = "shelter_in_place"
    medical_response = "medical_response"
    cse_rescue = "cse_rescue"
    height_rescue = "height_rescue"
    tabletop = "tabletop"
    airport_exercise = "airport_exercise"


class Agency(StrEnum):
    """List AG."""

    civil_defense = "civil_defense"
    red_crescent = "red_crescent"
    police = "police"
    unified_911 = "unified_911"
    airport_arff = "airport_arff"
    airport_aocc = "airport_aocc"
    airport_security = "airport_security"
    site_clinic = "site_clinic"
    hospital = "hospital"
    client_emergency = "client_emergency"
    electricity_utility = "electricity_utility"
    water_utility = "water_utility"
    other = "other"


class EmergencyRole(StrEnum):
    """List EOR."""

    emergency_coordinator = "emergency_coordinator"
    fire_warden = "fire_warden"
    first_aider = "first_aider"
    assembly_marshal = "assembly_marshal"


class RosterShift(StrEnum):
    day = "day"
    night = "night"
    both = "both"


class DrillShift(StrEnum):
    day = "day"
    night = "night"


class AssetType(StrEnum):
    """List EAT."""

    fire_extinguisher = "fire_extinguisher"
    fire_blanket = "fire_blanket"
    hose_reel = "hose_reel"
    alarm_call_point = "alarm_call_point"
    alarm_panel_temporary = "alarm_panel_temporary"
    siren_air_horn = "siren_air_horn"
    emergency_lighting = "emergency_lighting"
    first_aid_kit = "first_aid_kit"
    first_aid_room = "first_aid_room"
    aed = "aed"
    eyewash_plumbed = "eyewash_plumbed"
    eyewash_portable = "eyewash_portable"
    safety_shower = "safety_shower"
    stretcher = "stretcher"
    rescue_kit_height = "rescue_kit_height"
    escape_breathing_set = "escape_breathing_set"
    spill_kit = "spill_kit"  # 6c v1.2 (6e §11.4): reported as 6e K-125, excluded from K-107 / E19


class ExtinguisherSubtype(StrEnum):
    dcp_abc = "dcp_abc"
    co2 = "co2"
    foam = "foam"
    water = "water"
    wet_chemical = "wet_chemical"
    clean_agent = "clean_agent"


class ExpiryItem(StrEnum):
    pads = "pads"
    battery = "battery"
    eyewash_fluid = "eyewash_fluid"
    kit_contents = "kit_contents"
    other = "other"


class AssetStatus(StrEnum):
    """§4.4."""

    in_service = "in_service"
    out_of_service = "out_of_service"
    missing = "missing"
    retired = "retired"


class AssetAction(StrEnum):
    tag_out = "tag_out"
    retire = "retire"


class NotReadyReason(StrEnum):
    """EA-5."""

    CHECK_OVERDUE = "CHECK_OVERDUE"
    LAST_CHECK_FAILED = "LAST_CHECK_FAILED"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"
    MISSING = "MISSING"
    SERVICE_OVERDUE = "SERVICE_OVERDUE"
    HYDROTEST_OVERDUE = "HYDROTEST_OVERDUE"
    CONSUMABLE_EXPIRED = "CONSUMABLE_EXPIRED"
    USED_REPLENISH = "USED_REPLENISH"  # 6c v1.2 (6e SPL-5): used in a 6e spill, until a pass check


class CheckItem(StrEnum):
    """List EC (★ critical: EC01, EC03–EC08)."""

    EC01 = "EC01"
    EC02 = "EC02"
    EC03 = "EC03"
    EC04 = "EC04"
    EC05 = "EC05"
    EC06 = "EC06"
    EC07 = "EC07"
    EC08 = "EC08"
    EC09 = "EC09"
    EC10 = "EC10"


class CheckAnswer(StrEnum):
    pass_ = "pass"
    fail = "fail"
    na = "na"


class CheckMethod(StrEnum):
    qr_scan = "qr_scan"
    manual = "manual"


class CheckOutcome(StrEnum):
    checked = "checked"
    missing = "missing"


class CheckResult(StrEnum):
    pass_ = "pass"
    fail = "fail"


class RecordStatus(StrEnum):
    valid = "valid"
    voided = "voided"


class ErpStatus(StrEnum):
    """§4.1."""

    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    superseded = "superseded"


class ErpAction(StrEnum):
    submit = "submit"
    return_ = "return"
    approve = "approve"


class ActiveStatus(StrEnum):
    active = "active"
    inactive = "inactive"


class ApKind(StrEnum):
    primary = "primary"
    alternate = "alternate"


class AssignmentStatus(StrEnum):
    """§4.2 (derived from the dates)."""

    active = "active"
    ended = "ended"


class TeamType(StrEnum):
    confined_space = "confined_space"
    height = "height"


class TeamReason(StrEnum):
    """RT-2 failing reasons."""

    TEAM_UNDERSTRENGTH = "TEAM_UNDERSTRENGTH"
    NO_FIRST_AIDER = "NO_FIRST_AIDER"
    RESCUE_DRILL_OVERDUE = "RESCUE_DRILL_OVERDUE"
    RESCUE_EQUIPMENT_NOT_READY = "RESCUE_EQUIPMENT_NOT_READY"


class ProgrammeScope(StrEnum):
    site = "site"
    team = "team"
    project = "project"


class ShiftRequirement(StrEnum):
    any = "any"
    night = "night"


class AnnouncementRequirement(StrEnum):
    any = "any"
    unannounced = "unannounced"


class LineSource(StrEnum):
    minimum = "minimum"
    erp_scenario = "erp_scenario"
    repeat = "repeat"


class LineStatus(StrEnum):
    due = "due"
    overdue = "overdue"
    satisfied = "satisfied"
    retired = "retired"


class DrillStatus(StrEnum):
    """§4.5."""

    planned = "planned"
    in_progress = "in_progress"
    conducted = "conducted"
    evaluated = "evaluated"
    cancelled = "cancelled"
    voided = "voided"


class DrillAction(StrEnum):
    start = "start"
    conduct = "conduct"
    cancel = "cancel"
    void = "void"


class DrillResult(StrEnum):
    satisfactory = "satisfactory"
    unsatisfactory = "unsatisfactory"


class Criterion(StrEnum):
    """List DC (★ critical: DC01, DC02, DC04, DC09, DC10, DC11)."""

    DC01 = "DC01"
    DC02 = "DC02"
    DC03 = "DC03"
    DC04 = "DC04"
    DC05 = "DC05"
    DC06 = "DC06"
    DC07 = "DC07"
    DC08 = "DC08"
    DC09 = "DC09"
    DC10 = "DC10"
    DC11 = "DC11"
    DC12 = "DC12"


class FindingCategory(StrEnum):
    """List FC."""

    plan_deficiency = "plan_deficiency"
    training_competence = "training_competence"
    equipment = "equipment"
    communication = "communication"
    route_infrastructure = "route_infrastructure"
    behaviour = "behaviour"
    external_coordination = "external_coordination"


class FindingSeverity(StrEnum):
    critical = "critical"
    major = "major"
    minor = "minor"


class MusterMode(StrEnum):
    roll = "roll"
    count_ = "count"


class MusterStatus(StrEnum):
    """§4.7 (voided by 190)."""

    open = "open"
    reconciled = "reconciled"
    closed = "closed"
    voided = "voided"


class MusterSource(StrEnum):
    drill = "drill"
    event = "event"


class EntryState(StrEnum):
    """List MS."""

    expected = "expected"
    accounted = "accounted"
    unaccounted = "unaccounted"
    resolved = "resolved"


class EntryMethod(StrEnum):
    scan = "scan"
    tick = "tick"
    count_ = "count"
    exit_scan = "exit_scan"


class ResolutionReason(StrEnum):
    """List UR."""

    left_site_no_exit_scan = "left_site_no_exit_scan"
    off_site_confirmed = "off_site_confirmed"
    found_on_site = "found_on_site"
    with_emergency_team = "with_emergency_team"
    record_error = "record_error"


class EventStatus(StrEnum):
    """§4.6."""

    active = "active"
    all_clear = "all_clear"
    reviewed = "reviewed"
    voided = "voided"


class EventAction(StrEnum):
    all_clear = "all_clear"
    void = "void"


class CoverageState(StrEnum):
    covered = "covered"
    short = "short"
    not_required = "not_required"


class EmergencyActionKind(StrEnum):
    """§8.2 action-panel items."""

    erp_overdue = "erp_overdue"
    erp_review_required = "erp_review_required"
    zone_without_assembly_point = "zone_without_assembly_point"
    active_events = "active_events"
    open_musters_unaccounted = "open_musters_unaccounted"
    coverage_shortfall = "coverage_shortfall"
    programme_overdue = "programme_overdue"
    drill_evaluation_overdue = "drill_evaluation_overdue"
    event_review_overdue = "event_review_overdue"
    assets_out_of_service = "assets_out_of_service"
    asset_checks_overdue = "asset_checks_overdue"
    provision_gaps = "provision_gaps"
    rescue_teams_not_current = "rescue_teams_not_current"
    cse_permits_team_not_current = "cse_permits_team_not_current"
    permits_still_drill_suspended = "permits_still_drill_suspended"


class EmergencyKpiGroupBy(StrEnum):
    """EM-2 / §8.1 breakdowns."""

    site = "site"
    month = "month"
    drill_type = "drill_type"
    asset_type = "asset_type"
    event_type = "event_type"
