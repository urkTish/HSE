"""Phase 6b enumerations — heat stress management (spec 6b-heat-stress v1.0, §3.13 lists and §4
states). Exported into the OpenAPI contract so the frontend gets typed unions."""

from enum import StrEnum


class Workload(StrEnum):
    """List WL (metabolic rate classes, ACGIH)."""

    light = "light"
    moderate = "moderate"
    heavy = "heavy"
    very_heavy = "very_heavy"


class Clothing(StrEnum):
    """List CL (clothing adjustment factor added to WBGT)."""

    work_clothes = "work_clothes"
    cloth_coveralls = "cloth_coveralls"
    double_layer_woven = "double_layer_woven"
    sms_coveralls = "sms_coveralls"
    polyolefin_coveralls = "polyolefin_coveralls"
    vapour_barrier_coveralls = "vapour_barrier_coveralls"


class Regime(StrEnum):
    """List RGM. R0 < R1 < R2 < R3 < R4; `unknown` = no reading."""

    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"
    unknown = "unknown"


class AcclimatisationBasis(StrEnum):
    """§3.4: acclimatised workers use the TLV table, others the Action Limit (WR-3)."""

    acclimatised = "acclimatised"
    unacclimatised = "unacclimatised"


class AcclimatisationStatus(StrEnum):
    """§6.4 status(worker, d)."""

    acclimatised = "acclimatised"
    acclimatising = "acclimatising"
    not_acclimatised = "not_acclimatised"
    not_applicable = "n.a."


class HeatStateKind(StrEnum):
    """§3.5 zone heat state."""

    current = "current"
    stale = "stale"
    unknown = "unknown"


class InstrumentKind(StrEnum):
    handheld_meter = "handheld_meter"
    fixed_station = "fixed_station"


class InstrumentStatus(StrEnum):
    """§4.1."""

    active = "active"
    quarantined = "quarantined"
    retired = "retired"


class InstrumentAction(StrEnum):
    activate = "activate"
    quarantine = "quarantine"
    retire = "retire"


class PointSourceKind(StrEnum):
    manual = "manual"
    station = "station"


class ReadingSource(StrEnum):
    manual = "manual"
    station = "station"
    import_ = "import"


class RecordStatus(StrEnum):
    """Readings, welfare checks and patrols: valid → voided (177)."""

    valid = "valid"
    voided = "voided"


class PlanType(StrEnum):
    """List APT."""

    new_worker = "new_worker"
    returner = "returner"
    post_heat_illness = "post_heat_illness"
    period_start = "period_start"


class PlanTriggerKind(StrEnum):
    mobilisation = "mobilisation"
    absence = "absence"
    hold_release = "hold_release"
    period_start = "period_start"
    manual = "manual"


class PlanStatus(StrEnum):
    """§4.2."""

    planned = "planned"
    waiting_restriction = "waiting_restriction"
    active = "active"
    completed = "completed"
    interrupted = "interrupted"
    cancelled = "cancelled"


class StationType(StrEnum):
    cooled_cabin = "cooled_cabin"
    shaded_shelter = "shaded_shelter"
    mobile_shade_unit = "mobile_shade_unit"
    indoor_rest_area = "indoor_rest_area"


class Cooling(StrEnum):
    none = "none"
    fans = "fans"
    misting = "misting"
    air_conditioning = "air_conditioning"


class WelfareItem(StrEnum):
    """List HW (★ critical: HW01, HW05, HW08, HW10)."""

    HW01 = "HW01"
    HW02 = "HW02"
    HW03 = "HW03"
    HW04 = "HW04"
    HW05 = "HW05"
    HW06 = "HW06"
    HW07 = "HW07"
    HW08 = "HW08"
    HW09 = "HW09"
    HW10 = "HW10"


class CheckAnswer(StrEnum):
    pass_ = "pass"
    fail = "fail"
    na = "na"


class PatrolOutcome(StrEnum):
    """List BO."""

    no_outdoor_work = "no_outdoor_work"
    compliant_shaded_or_indoor = "compliant_shaded_or_indoor"
    exempt_work = "exempt_work"
    violation = "violation"


class BanExemptionReason(StrEnum):
    """As Phase 3 HT-4."""

    emergency_repair = "emergency_repair"
    exempt_activity_mhrsd = "exempt_activity_mhrsd"
    shaded_and_cooled_workplace = "shaded_and_cooled_workplace"


class BanExemptionStatus(StrEnum):
    active = "active"
    expired = "expired"
    revoked = "revoked"


class ReviewQuestion(StrEnum):
    """List HC."""

    HC1 = "HC1"
    HC2 = "HC2"
    HC3 = "HC3"
    HC4 = "HC4"
    HC5 = "HC5"
    HC6 = "HC6"


class ReviewAnswer(StrEnum):
    yes = "yes"
    no = "no"
    unknown = "unknown"
    na = "na"


class HeatLogSource(StrEnum):
    injury_case = "injury_case"
    referral = "referral"


class HeatLogStatus(StrEnum):
    open = "open"
    reviewed = "reviewed"
    voided = "voided"


class SeasonReportStatus(StrEnum):
    draft = "draft"
    issued = "issued"
    superseded = "superseded"


class HeatKpiGroupBy(StrEnum):
    """T19 / KPI page group_by (HM-2)."""

    zone = "zone"
    site = "site"
    contractor = "contractor"
    month = "month"


class HeatActionKind(StrEnum):
    """§8.2 action-panel items."""

    required_zone_without_point = "required_zone_without_point"
    reading_overdue_now = "reading_overdue_now"
    r4_permit_not_suspended = "r4_permit_not_suspended"
    ban_violation_ca_open = "ban_violation_ca_open"
    patrol_coverage_missed_yesterday = "patrol_coverage_missed_yesterday"
    welfare_coverage_missed_yesterday = "welfare_coverage_missed_yesterday"
    plan_days_unconfirmed = "plan_days_unconfirmed"
    heat_reviews_overdue = "heat_reviews_overdue"
    active_ban_exemption = "active_ban_exemption"
    quarantined_instrument_on_point = "quarantined_instrument_on_point"
    permit_ban_violation = "permit_ban_violation"  # MB-4 (Phase 3 §8.3)
