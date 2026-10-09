import type { Schemas } from "@/lib/api/client";

type S = Schemas;

/** Phase 6b (heat stress) enum values in display order (spec 6b §3.13, §4). */
export const WORKLOADS = ["light", "moderate", "heavy", "very_heavy"] as const satisfies readonly S["Workload"][];
export const CLOTHING = ["work_clothes", "cloth_coveralls", "double_layer_woven", "sms_coveralls", "polyolefin_coveralls", "vapour_barrier_coveralls"] as const satisfies readonly S["Clothing"][];
export const REGIMES = ["R0", "R1", "R2", "R3", "R4", "unknown"] as const satisfies readonly S["Regime"][];
export const TABLE_REGIMES = ["R0", "R1", "R2", "R3"] as const satisfies readonly S["Regime"][];
export const BASES = ["acclimatised", "unacclimatised"] as const satisfies readonly S["AcclimatisationBasis"][];
export const INSTRUMENT_KINDS = ["handheld_meter", "fixed_station"] as const satisfies readonly S["InstrumentKind"][];
export const INSTRUMENT_STATUSES = ["active", "quarantined", "retired"] as const satisfies readonly S["InstrumentStatus"][];
export const POINT_SOURCES = ["manual", "station"] as const satisfies readonly S["PointSourceKind"][];
export const STATION_TYPES = ["cooled_cabin", "shaded_shelter", "mobile_shade_unit", "indoor_rest_area"] as const satisfies readonly S["StationType"][];
export const COOLING = ["none", "fans", "misting", "air_conditioning"] as const satisfies readonly S["Cooling"][];
export const PLAN_TYPES = ["new_worker", "returner", "post_heat_illness", "period_start"] as const satisfies readonly S["PlanType"][];
export const PLAN_STATUSES = ["planned", "waiting_restriction", "active", "completed", "interrupted", "cancelled"] as const satisfies readonly S["PlanStatus"][];
export const WELFARE_ITEMS = ["HW01", "HW02", "HW03", "HW04", "HW05", "HW06", "HW07", "HW08", "HW09", "HW10"] as const satisfies readonly S["WelfareItem"][];
export const CHECK_ANSWERS = ["pass", "fail", "na"] as const satisfies readonly S["CheckAnswer"][];
export const PATROL_OUTCOMES = ["no_outdoor_work", "compliant_shaded_or_indoor", "exempt_work", "violation"] as const satisfies readonly S["PatrolOutcome"][];
export const EXEMPTION_REASONS = ["emergency_repair", "exempt_activity_mhrsd", "shaded_and_cooled_workplace"] as const satisfies readonly S["BanExemptionReason"][];
export const EXEMPTION_STATUSES = ["active", "expired", "revoked"] as const satisfies readonly S["BanExemptionStatus"][];
export const HEAT_LOG_STATUSES = ["open", "reviewed", "voided"] as const satisfies readonly S["HeatLogStatus"][];
export const REVIEW_QUESTIONS = ["HC1", "HC2", "HC3", "HC4", "HC5", "HC6"] as const;
export const REVIEW_ANSWERS = ["yes", "no", "unknown", "na"] as const satisfies readonly S["ReviewAnswer"][];
export const HEAT_KPIS = ["K-97", "K-98", "K-99", "K-100", "K-101", "K-102", "K-103"] as const satisfies readonly S["KpiMetric"][];
export const HEAT_KPI_GROUP_BY = ["zone", "site", "contractor", "month"] as const satisfies readonly S["HeatKpiGroupBy"][];
/** Rest minutes per hour by regime (§6.2); shown with the regime, the server sends the same value on the board. */
export const REST_MIN: Record<S["Regime"], number | null> = { R0: 0, R1: 15, R2: 30, R3: 45, R4: 60, unknown: null };
