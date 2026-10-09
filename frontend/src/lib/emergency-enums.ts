import type { Schemas } from "@/lib/api/client";

type S = Schemas;

/** Phase 6c (emergency preparedness) enum values in display order (spec 6c §3, §4). Reference lists (ES, DT, AG…) come from the server. */
export const EM_KPI_GROUP_BY = ["site", "month", "drill_type", "asset_type", "event_type"] as const satisfies readonly S["EmergencyKpiGroupBy"][];
export const EM_KPIS = ["K-104", "K-105", "K-106", "K-107", "K-108", "K-109"] as const satisfies readonly S["KpiMetric"][];
export const DRILL_SHIFTS = ["day", "night"] as const satisfies readonly S["DrillShift"][];
export const ROSTER_SHIFTS = ["day", "night", "both"] as const satisfies readonly S["RosterShift"][];
export const AP_KINDS = ["primary", "alternate"] as const satisfies readonly S["ApKind"][];
export const TEAM_TYPES = ["confined_space", "height"] as const satisfies readonly S["TeamType"][];
export const ASSET_STATUSES = ["in_service", "out_of_service", "missing", "retired"] as const satisfies readonly S["AssetStatus"][];
export const NOT_READY = ["CHECK_OVERDUE", "LAST_CHECK_FAILED", "OUT_OF_SERVICE", "MISSING", "SERVICE_OVERDUE", "HYDROTEST_OVERDUE", "CONSUMABLE_EXPIRED"] as const satisfies readonly S["NotReadyReason"][];
export const EXPIRY_ITEMS = ["pads", "battery", "eyewash_fluid", "kit_contents", "other"] as const satisfies readonly S["ExpiryItem"][];
export const DRILL_STATUSES = ["planned", "in_progress", "conducted", "evaluated", "cancelled", "voided"] as const satisfies readonly S["DrillStatus"][];
export const EVENT_STATUSES = ["active", "all_clear", "reviewed", "voided"] as const satisfies readonly S["EventStatus"][];
export const ERP_STATUSES = ["draft", "submitted", "approved", "superseded"] as const satisfies readonly S["ErpStatus"][];
export const SEVERITIES = ["critical", "major", "minor"] as const satisfies readonly S["app__core__emergency_enums__FindingSeverity"][];
export const CHECK_ANSWERS = ["pass", "fail", "na"] as const satisfies readonly S["CheckAnswer"][];
/** Fire extinguisher subtypes (list EAT); free string in the contract. */
export const EXTINGUISHER_SUBTYPES = ["dcp_abc", "co2", "foam", "water", "wet_chemical", "clean_agent"] as const;
/** Timeline fields a user types (headcount_complete_at is set by the muster, DR-5). */
export const TIMELINE_KEYS = ["alarm_at", "evacuation_complete_at", "first_responder_at", "casualty_reached_at", "casualty_recovered_at", "all_clear_at"] as const satisfies readonly (keyof S["Timeline"])[];
/** Drill types that open a muster (MU-1) and are planned per site; team drills need a team. */
export const MUSTER_DRILLS: readonly S["DrillType"][] = ["evacuation_full", "evacuation_partial", "shelter_in_place"];
export const TEAM_DRILLS: Partial<Record<S["DrillType"], S["TeamType"]>> = { cse_rescue: "confined_space", height_rescue: "height" };
export const PROJECT_DRILLS: readonly S["DrillType"][] = ["tabletop", "airport_exercise"];
/** EV-4: event types that need a Phase 1 incident before the review. */
export const INCIDENT_EVENT_TYPES: readonly S["EventType"][] = ["fire_explosion", "medical_emergency", "structural_collapse", "excavation_collapse", "gas_release", "electrical_contact", "utility_strike", "confined_space_rescue", "height_rescue"];
