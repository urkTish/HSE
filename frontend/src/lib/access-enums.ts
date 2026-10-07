import type { Schemas } from "@/lib/api/client";

// Phase 2 enum value lists mirrored from contract v0.3.1 (the `satisfies` clauses keep them in sync).
type S = Schemas;

export const WORKER_ID_TYPES = ["iqama", "national_id", "gcc_id", "passport"] as const satisfies readonly S["WorkerIdType"][];
export const WORKER_PERSON_TYPES = ["contractor_worker", "client_pmc_staff", "visitor"] as const satisfies readonly S["WorkerPersonType"][];
export const WORKER_LANGUAGES = ["ar", "en", "ur", "hi", "bn", "ne", "tl", "ml", "ta", "other"] as const satisfies readonly S["WorkerLanguage"][];
export const WORKER_STATUSES = ["active", "banned", "inactive", "anonymised"] as const satisfies readonly S["WorkerStatus"][];
export const DEPLOYMENT_STATUSES = ["pending_induction", "mobilised", "demobilised"] as const satisfies readonly S["DeploymentStatus"][];
export const TRADES = [
  "labourer",
  "carpenter",
  "steel_fixer",
  "steel_erector",
  "scaffolder",
  "rigger",
  "crane_operator",
  "plant_operator",
  "driver",
  "electrician",
  "plumber",
  "welder",
  "mason",
  "painter",
  "surveyor",
  "supervisor",
  "engineer",
  "hse_staff",
  "flagman",
  "other",
] as const satisfies readonly S["Trade"][];
export const UNMASK_REASONS = ["pass_application", "authority_request", "identity_verification", "incident_investigation", "other"] as const satisfies readonly S["UnmaskReason"][];
export const ACCESS_CARD_REISSUE_REASONS = ["lost", "damaged", "other"] as const satisfies readonly S["AccessCardReissueReason"][];

export const INDUCTION_TYPES = ["general_site", "airside", "zone_specific", "visitor"] as const satisfies readonly S["InductionType"][];
export const INDUCTION_STATUSES = ["valid", "failed", "suspended", "revoked", "superseded", "expired"] as const satisfies readonly S["InductionStatus"][];
export const INDUCTION_DELIVERER_ROLES = ["hse_manager", "hse_officer", "contractor_hse_rep"] as const satisfies readonly S["InductionDelivererRole"][];

export const AREA_CATEGORIES = ["apron", "manoeuvring", "airside_roads"] as const satisfies readonly S["AreaCategory"][];
export const HOOK_KINDS = ["training_course", "personnel_certificate", "equipment_certificate", "medical_fitness"] as const satisfies readonly S["HookKind"][];
export const CARD_COLOURS = ["red", "blue", "green", "yellow", "orange", "white", "grey"] as const satisfies readonly S["CardColour"][];
export const PASS_AREA_KINDS = ["apron", "manoeuvring", "terminal_airside", "airside_roads", "other_sra"] as const satisfies readonly S["PassAreaKind"][];

export const PASS_APPLICATION_TYPES = ["new", "renewal", "replacement_lost", "replacement_damaged", "area_change"] as const satisfies readonly S["PassApplicationType"][];
export const PASS_APPLICATION_STATUSES = ["draft", "submitted", "endorsed", "lodged", "approved", "refused", "issued", "withdrawn", "cancelled"] as const satisfies readonly S["PassApplicationStatus"][];
export const BACKGROUND_STATUSES = ["not_required", "submitted", "in_progress", "cleared", "not_cleared", "expired"] as const satisfies readonly S["BackgroundCheckStatus"][];
export const VALIDITY_STATUSES = ["pending", "active", "suspended", "revoked", "expired", "withdrawn"] as const satisfies readonly S["ValidityStatus"][];
export const CUSTODY_STATUSES = ["held", "return_due", "returned", "lost"] as const satisfies readonly S["CustodyStatus"][];

export const VEHICLE_CLASSES = ["light", "heavy", "special_plant"] as const satisfies readonly S["VehicleClass"][];
export const LICENCE_ISSUERS = ["ksa", "gcc", "international"] as const satisfies readonly S["LicenceIssuer"][];
export const LICENCE_CLASSES = ["private", "public_transport", "heavy_transport", "heavy_equipment", "motorcycle"] as const satisfies readonly S["LicenceClass"][];
export const OFFENCE_STATUSES = ["recorded", "disputed", "upheld", "withdrawn"] as const satisfies readonly S["OffenceStatus"][];

export const VEHICLE_OWNER_TYPES = ["company", "rental", "individual"] as const satisfies readonly S["VehicleOwnerType"][];
export const PLATE_TYPES = ["private", "transport", "heavy_equipment", "none"] as const satisfies readonly S["PlateType"][];
export const VEHICLE_STATUSES = ["active", "off_site", "withdrawn"] as const satisfies readonly S["VehicleStatus"][];
export const VEHICLE_CATEGORIES = [
  "light_vehicle",
  "pickup",
  "van",
  "bus",
  "truck",
  "tipper",
  "water_tanker",
  "fuel_bowser",
  "concrete_mixer",
  "mobile_crane",
  "crawler_crane",
  "mewp",
  "forklift",
  "telehandler",
  "excavator",
  "wheel_loader",
  "grader",
  "roller",
  "paver",
  "milling_machine",
  "line_marking_vehicle",
  "sweeper",
  "lighting_tower",
  "trailer",
  "other",
] as const satisfies readonly S["VehicleCategory"][];
export const AVP_CHECKLIST_ITEMS = [
  "amber_beacon",
  "company_marking",
  "chequered_flag_or_marking",
  "radio_fitted",
  "fire_extinguisher",
  "spill_kit",
  "fod_bin",
  "tyres_brakes",
  "reverse_alarm",
  "lights",
  "no_loose_items",
  "height_marking",
] as const satisfies readonly S["AvpChecklistItem"][];
/** VP-4: these items may not be n.a. */
export const AVP_NO_NA: readonly S["AvpChecklistItem"][] = ["amber_beacon", "company_marking", "fire_extinguisher", "tyres_brakes", "lights"];
export const CHECKLIST_OUTCOMES = ["pass", "fail", "n.a."] as const satisfies readonly S["ChecklistOutcome"][];

export const WORKS_IMPACTS = [
  "taxiway_closure",
  "runway_closure",
  "declared_distances_change",
  "ils_outage",
  "lighting_outage",
  "stand_closure",
  "obstacle",
  "other",
] as const satisfies readonly S["WorksImpact"][];
export const NOTAM_STATUSES = ["draft", "submitted_to_ops", "requested_from_ais", "issued", "rejected", "replaced", "cancelled", "expired"] as const satisfies readonly S["NotamStatus"][];
export const NOTAM_TYPES = ["N", "R", "C"] as const satisfies readonly S["NotamType"][];

export const OBSTACLE_EQUIPMENT_TYPES = [
  "mobile_crane",
  "tower_crane",
  "crawler_crane",
  "piling_rig",
  "drilling_rig",
  "mewp",
  "concrete_pump_boom",
  "excavator",
  "temporary_structure",
  "other",
] as const satisfies readonly S["ObstacleEquipmentType"][];
export const OLS_SURFACES = [
  "approach",
  "take_off_climb",
  "transitional",
  "inner_horizontal",
  "conical",
  "inner_approach",
  "inner_transitional",
  "balked_landing",
  "none_applicable",
] as const satisfies readonly S["OlsSurface"][];
export const OBSTACLE_CONDITIONS = [
  "obstruction_light",
  "day_marking",
  "lower_when_idle",
  "lower_at_night",
  "notam_required",
  "ats_coordination_each_lift",
  "daylight_only",
] as const satisfies readonly S["ObstacleCondition"][];
export const OBSTACLE_DECISIONS = ["approved", "approved_with_conditions", "rejected"] as const satisfies readonly S["ObstacleDecision"][];
export const OBSTACLE_STATUSES = ["draft", "submitted", "approved", "approved_with_conditions", "rejected", "suspended", "withdrawn", "expired"] as const satisfies readonly S["ObstacleStatus"][];
export const CLEARANCE_REASONS = ["zone_height_exceeded", "ols_penetration", "within_ols_buffer", "height_threshold", "operator_requires"] as const satisfies readonly S["ClearanceReason"][];

export const WAP_STATUSES = ["draft", "submitted", "approved", "rejected", "active", "suspended", "closed", "cancelled", "expired"] as const satisfies readonly S["WapStatus"][];
export const CREW_ROLES = ["worker", "supervisor", "escort", "driver", "banksman"] as const satisfies readonly S["CrewRole"][];
export const WEEKDAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"] as const satisfies readonly S["Weekday"][];
export const WAP_BLOCKERS = [
  "NOTAM_NOT_ISSUED",
  "NOTAM_NOT_COVERING_WINDOW",
  "ILS_OUTAGE_NOTAM_REQUIRED",
  "HEIGHT_CLEARANCE_REQUIRED",
  "OBS_NOT_ACTIVE",
  "WSP_REQUIRED",
  "SUPERVISOR_INELIGIBLE",
  "NO_ELIGIBLE_CREW",
  "CONTRACTOR_SUSPENDED",
  "OPS_SUSPENSION_ACTIVE",
] as const satisfies readonly S["WapBlocker"][];
export const OPS_EVENT_TYPES = [
  "lvp",
  "dust_sandstorm",
  "thunderstorm_lightning",
  "security_alert",
  "aircraft_emergency",
  "atc_instruction",
  "vip_movement",
  "other",
] as const satisfies readonly S["OpsEventType"][];
export const OPS_EVENT_SOURCES = ["aocc", "atc", "airport_security", "hse"] as const satisfies readonly S["OpsEventSource"][];

export const CREDENTIAL_REASONS = [
  "violation",
  "investigation_pending",
  "contractor_suspended",
  "contractor_blacklisted",
  "worker_banned",
  "id_expired",
  "licence_expired",
  "vehicle_document_expired",
  "dependency_invalid",
  "points_threshold",
  "security_request",
  "ops_suspension",
  "demobilised",
  "superseded",
  "lost_stolen",
  "fraud_misuse",
  "other",
] as const satisfies readonly S["CredentialReason"][];
/** LC-6: applied and lifted by the system only — never offered for manual actions. */
export const SYSTEM_REASONS: readonly S["CredentialReason"][] = ["dependency_invalid", "id_expired", "licence_expired", "vehicle_document_expired", "points_threshold", "demobilised", "superseded", "contractor_blacklisted", "worker_banned", "ops_suspension", "contractor_suspended"];
export const MANUAL_REASONS = CREDENTIAL_REASONS.filter((r) => !SYSTEM_REASONS.includes(r));

export const GATE_TYPES = ["site_gate", "zone_entry", "airside_precheck"] as const satisfies readonly S["GateType"][];
export const GATE_RESULTS = [
  "GRANTED",
  "GRANTED_WITH_WARNING",
  "DENIED",
  "PENDING_ESCORT",
  "PENDING_DRIVER",
  "PENDING_ESCORT_VEHICLE",
  "EXIT_RECORDED",
  "WAP_VIEW",
] as const satisfies readonly S["GateResult"][];
export const GATE_SUBJECT_KINDS = ["person", "vehicle", "wap", "unknown"] as const satisfies readonly S["GateSubjectKind"][];
export const GATE_REASON_CODES = [
  "TOKEN_UNKNOWN",
  "OUT_OF_SCOPE",
  "WORKER_NOT_DEPLOYED",
  "WORKER_BANNED",
  "CONTRACTOR_SUSPENDED",
  "CONTRACTOR_BLACKLISTED",
  "ID_EXPIRED",
  "INDUCTION_MISSING",
  "INDUCTION_EXPIRED",
  "INDUCTION_SUSPENDED",
  "INDUCTION_ABSENCE",
  "PASS_MISSING",
  "PASS_AREA_NOT_COVERED",
  "PASS_SUSPENDED",
  "PASS_EXPIRED",
  "CREDENTIAL_REVOKED",
  "CREDENTIAL_LOST",
  "ESCORT_REQUIRED",
  "ESCORT_INVALID",
  "ESCORT_RATIO_EXCEEDED",
  "WAP_MISSING",
  "WAP_NOT_ACTIVE",
  "WAP_SUSPENDED",
  "WAP_OUTSIDE_WINDOW",
  "CREW_EXCLUDED",
  "ADP_MISSING",
  "ADP_CATEGORY",
  "ADP_SUSPENDED",
  "AVP_MISSING",
  "AVP_AREA",
  "AVP_SUSPENDED",
  "VEHICLE_DOC_EXPIRED",
  "HEIGHT_CLEARANCE_REQUIRED",
  "HOOK_NOT_MET",
  "EXPIRING_7D",
  "HOOK_NOT_AVAILABLE",
  "LANGUAGE_MISMATCH",
] as const satisfies readonly S["GateReasonCode"][];

export const SUSPENDED_CONTRACTOR_GATE_MODES = ["deny", "warn"] as const satisfies readonly S["SuspendedContractorGateMode"][];
export const HOOK_POLICIES = ["warn", "block"] as const satisfies readonly S["HookPolicy"][];

export type CredentialKind = S["CredentialKind"];

export const EXPORT_PURPOSES_ACCESS = ["pass_office", "authority_request", "legal", "other"] as const satisfies readonly S["ExportPurpose"][];
