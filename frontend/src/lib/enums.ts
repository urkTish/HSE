import type { Schemas } from "@/lib/api/client";

// Enum value lists mirrored from the contract for selects (types keep them in sync).
export const PROJECT_STATUSES = ["planning", "active", "on_hold", "closed"] as const satisfies readonly Schemas["ProjectStatus"][];
export const PROJECT_TYPES = ["airport", "building_highrise", "infrastructure", "industrial", "other"] as const satisfies readonly Schemas["ProjectType"][];
export const SITE_SIDES = ["airside", "landside", "mixed", "other"] as const satisfies readonly Schemas["SiteSide"][];
export const SITE_STATUSES = ["active", "inactive"] as const satisfies readonly Schemas["SiteStatus"][];
export const ZONE_TYPES = ["airside", "landside", "other"] as const satisfies readonly Schemas["ZoneType"][];
export const ZONE_STATUSES = ["active", "temporarily_closed", "archived"] as const satisfies readonly Schemas["ZoneStatus"][];
export const AIRSIDE_AREAS = [
  "runway",
  "runway_strip",
  "resa",
  "taxiway",
  "taxiway_strip",
  "apron",
  "ils_critical",
  "ils_sensitive",
  "airside_road",
  "other_airside",
] as const satisfies readonly Schemas["AirsideArea"][];
/** Areas that are always part of the movement area (rule 20). */
export const MOVEMENT_AREAS: readonly Schemas["AirsideArea"][] = ["runway", "runway_strip", "resa", "taxiway", "taxiway_strip", "apron"];
export const CONTRACTOR_STATUSES = [
  "draft",
  "pending_approval",
  "approved",
  "suspended",
  "demobilised",
  "blacklisted",
] as const satisfies readonly Schemas["ContractorStatus"][];
export const CONTRACTOR_CATEGORIES = [
  "civil",
  "mep",
  "steel",
  "airfield",
  "scaffolding",
  "lifting",
  "facade",
  "specialist",
  "consultant",
  "other",
] as const satisfies readonly Schemas["ContractorCategory"][];
export const ROLES = [
  "hse_manager",
  "hse_officer",
  "site_engineer",
  "permit_issuer",
  "permit_receiver",
  "contractor_hse_rep",
  "viewer_client",
  "oh_practitioner",
] as const satisfies readonly Schemas["Role"][];
/** Roles an HSE Officer may assign (rule 14). */
export const OFFICER_ASSIGNABLE_ROLES: readonly Schemas["Role"][] = [
  "site_engineer",
  "permit_issuer",
  "permit_receiver",
  "contractor_hse_rep",
  "viewer_client",
];
/** Roles that need a contractor engagement (spec §3.7). */
export const CONTRACTOR_SCOPED_ROLES: readonly Schemas["Role"][] = ["contractor_hse_rep", "permit_receiver"];
export const USER_STATUSES = ["invited", "active", "locked", "deactivated"] as const satisfies readonly Schemas["UserStatus"][];
export const EMPLOYER_TYPES = ["client", "pmc_consultant", "contractor"] as const satisfies readonly Schemas["EmployerType"][];
export const AUDIT_ACTIONS = [
  "login_success",
  "login_failed",
  "logout",
  "account_locked",
  "password_reset_requested",
  "password_changed",
  "mfa_changed",
  "user_invited",
  "user_status_changed",
  "role_assigned",
  "role_revoked",
  "create",
  "update",
  "status_change",
  "archive",
  "settings_changed",
  "sensitive_field_read",
  "export",
  "access_denied",
  "audit_log_viewed",
  "audit_chain_verified",
  "retention_purge",
  "privacy_notice_acknowledged",
] as const satisfies readonly Schemas["AuditAction-Output"][];
export const ENTITY_TYPES = [
  "project",
  "site",
  "zone",
  "contractor",
  "project_engagement",
  "user",
  "role_assignment",
  "project_settings",
  "audit_log",
] as const satisfies readonly Schemas["EntityType"][];
export const AUDIT_RESULTS = ["success", "denied", "failed"] as const satisfies readonly Schemas["AuditResult"][];
export const KPI_BASES = [200000, 1000000] as const satisfies readonly Schemas["KpiBaseHours"][];

// ---- Phase 1 (contract v0.2.0) ----
export const SHIFTS = ["day", "night", "all"] as const satisfies readonly Schemas["Shift"][];
export const WORKFORCE_STATUSES = ["draft", "submitted", "verified", "locked"] as const satisfies readonly Schemas["WorkforceStatus"][];
export const IMPORT_MODES = ["insert_only", "upsert"] as const satisfies readonly Schemas["ImportMode"][];
export const IMPORT_STATUSES = ["validated", "committed", "discarded", "expired"] as const satisfies readonly Schemas["ImportStatus"][];
export const INCIDENT_STATUSES = ["draft", "reported", "under_investigation", "pending_review", "actions_pending", "closed", "voided"] as const satisfies readonly Schemas["IncidentStatus"][];
export const INCIDENT_TYPES = ["injury_illness", "near_miss", "property_damage", "environmental", "dangerous_occurrence"] as const satisfies readonly Schemas["IncidentType"][];
export const INCIDENT_SHIFTS = ["day", "night"] as const satisfies readonly Schemas["IncidentShift"][];
export const PERSON_TYPES = ["contractor_worker", "client_pmc_staff", "visitor", "third_party_public"] as const satisfies readonly Schemas["PersonType"][];
export const ID_TYPES = ["iqama", "national_id", "gcc_id", "passport"] as const satisfies readonly Schemas["IdType"][];
export const BODY_SIDES = ["left", "right", "both", "n/a"] as const satisfies readonly Schemas["BodySide"][];
export const TREATED_AT = ["site_clinic", "hospital_outpatient", "hospital_admitted", "none"] as const satisfies readonly Schemas["TreatedAt"][];
export const PERMANENT_DISABILITY = ["none", "partial", "total"] as const satisfies readonly Schemas["PermanentDisability"][];
export const PRIVACY_REASONS = ["sexual_assault", "mental_illness", "infectious_disease", "needlestick_contaminated", "reproductive_organs", "employee_request"] as const satisfies readonly Schemas["PrivacyCaseReason"][];
export const CASE_CATEGORIES = ["FAT", "LTI", "RWC", "JTC", "MTC", "FAC"] as const satisfies readonly Schemas["CaseCategory"][];
export const NOT_WORK_RELATED_REASONS = ["off_duty_camp", "personal_task", "pre_existing_condition", "commuting", "voluntary_wellness", "other"] as const satisfies readonly Schemas["NotWorkRelatedReason"][];
export const AIRSIDE_FLAGS = ["runway_incursion", "fod_event", "aircraft_involved", "gse_damage", "notam_breach", "ols_infringement", "wildlife", "airside_vehicle_incident"] as const satisfies readonly Schemas["AirsideFlag"][];
export const ASSET_TYPES = ["plant", "vehicle", "structure", "utility", "airport_asset", "aircraft", "other"] as const satisfies readonly Schemas["app__core__hse_enums__AssetType"][];
export const ENV_CATEGORIES = ["spill", "emission", "dust", "noise", "waste", "water", "wildlife_habitat"] as const satisfies readonly Schemas["EnvCategory"][];
export const ENV_REACHED = ["none", "soil", "drain", "water_body"] as const satisfies readonly Schemas["EnvReached"][];
export const DO_CATEGORIES = ["crane_lifting_failure", "scaffold_collapse", "structural_collapse", "excavation_collapse", "electrical_short_fire", "fire_explosion", "gas_release", "pressure_failure", "vehicle_overturn", "other"] as const satisfies readonly Schemas["DangerousOccurrenceCategory"][];
export const EXTERNAL_BODIES = ["gosi", "mhrsd", "civil_defense", "gaca", "airport_operator", "client", "police"] as const satisfies readonly Schemas["ExternalBody"][];
export const INVESTIGATION_LEVELS = ["L1", "L2", "L3"] as const satisfies readonly Schemas["InvestigationLevel"][];
export const INVESTIGATION_METHODS = ["simple", "five_why", "icam", "taproot"] as const satisfies readonly Schemas["InvestigationMethod"][];
export const OBSERVATION_TYPES = ["safe_behaviour", "safe_condition", "unsafe_act", "unsafe_condition"] as const satisfies readonly Schemas["ObservationType"][];
export const OBSERVATION_STATUSES = ["open", "action_raised", "closed"] as const satisfies readonly Schemas["ObservationStatus"][];
export const RISK_RATINGS = ["low", "medium", "high"] as const satisfies readonly Schemas["RiskRating"][];
export const INSPECTION_STATUSES = ["planned", "completed", "missed", "cancelled"] as const satisfies readonly Schemas["InspectionStatus"][];
export const INSPECTION_TIMELINESS = ["on_time", "late", "missed", "pending", "unplanned", "cancelled"] as const satisfies readonly Schemas["InspectionTimeliness"][];
export const INSPECTION_FREQUENCIES = ["daily", "weekly", "fortnightly", "monthly", "once"] as const satisfies readonly Schemas["InspectionFrequency"][];
export const WEEKDAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"] as const satisfies readonly Schemas["Weekday"][];
export const ASSIGNEE_ROLES = ["hse_officer", "site_engineer", "contractor_hse_rep"] as const satisfies readonly Schemas["InspectionAssigneeRole"][];
export const FINDING_SEVERITIES = ["low", "medium", "high", "critical"] as const satisfies readonly Schemas["app__core__hse_enums__FindingSeverity"][];
export const CA_STATUSES = ["open", "in_progress", "pending_verification", "closed", "cancelled"] as const satisfies readonly Schemas["CaStatus"][];
export const CA_PRIORITIES = ["critical", "high", "medium", "low"] as const satisfies readonly Schemas["CaPriority"][];
export const CONTROL_LEVELS = ["elimination", "substitution", "engineering", "administrative", "ppe"] as const satisfies readonly Schemas["ControlLevel"][];
export const CA_SOURCE_TYPES = ["incident", "observation", "inspection", "ai_recommendation", "other"] as const satisfies readonly Schemas["CaSourceType"][];
export const OVERDUE_BUCKETS = ["1-7", "8-30", "31-60", ">60"] as const satisfies readonly Schemas["OverdueBucket"][];
export const MEETING_TYPES = ["hse_committee", "contractor_hse", "management_walk", "other"] as const satisfies readonly Schemas["MeetingType"][];
export const PERIOD_PRESETS = ["day", "week", "month", "quarter", "year", "mtd", "qtd", "ytd", "r12", "itd", "custom"] as const satisfies readonly Schemas["PeriodPreset"][];
export const COMPARISON_KINDS = ["previous", "sply", "r12"] as const satisfies readonly Schemas["ComparisonKind"][];
export const BREAKDOWN_DIMENSIONS = ["site", "zone", "zone_type", "airside_area", "contractor", "tier", "activity", "mechanism", "agency", "body_part", "nature", "case_category", "incident_type", "root_cause_level", "root_cause_code", "shift", "hour_band", "weekday", "month", "heat_season", "ramadan", "days_on_site_band", "trade", "age_band", "nationality", "observation_category", "observation_type", "inspection_type", "control_level", "ca_priority"] as const satisfies readonly Schemas["BreakdownDimension"][];
export const BREAKDOWN_MEASURES = ["injury_cases", "recordable_cases", "events_by_type", "observations", "unsafe_observations", "cas", "inspections"] as const satisfies readonly Schemas["BreakdownMeasure"][];
export const AGE_BANDS = ["<20", "20-29", "30-39", "40-49", "50-59", "60+"] as const satisfies readonly Schemas["AgeBand"][];
export const EXPORT_PURPOSES = ["gosi", "client_report", "legal", "insurance", "other"] as const satisfies readonly Schemas["ExportPurpose"][];
export const REPORT_STATUSES = ["generating", "draft", "reviewed", "published", "failed"] as const satisfies readonly Schemas["MonthlyReportStatus"][];
export const KPI_METRICS = ["K-01", "K-02", "K-03", "K-04", "K-05", "K-05b", "K-06", "K-07", "K-08", "K-09", "K-10", "K-11", "K-12", "K-13", "K-14", "K-15", "K-16", "K-17", "K-18", "K-20", "K-21", "K-22", "K-23", "K-24", "K-25", "K-26a", "K-26b", "K-26c", "K-27", "K-28", "K-29", "K-30", "K-31", "K-32", "K-33", "K-34", "K-35", "K-35b", "K-36", "K-37", "K-38", "K-39", "K-40", "K-41", "K-42", "K-42b", "K-43", "K-44", "K-45", "K-46", "K-47"] as const satisfies readonly Schemas["KpiMetric"][];
export const TREATMENTS = ["otc_medication_otc_strength", "tetanus_immunisation", "wound_cleaning", "wound_covering_steristrips", "hot_cold_therapy", "non_rigid_support", "temporary_immobilisation_transport", "nail_drilling", "eye_patch", "eye_irrigation_swab", "splinter_removal", "finger_guard", "massage", "fluids_oral_heat", "sutures_staples_glue", "rigid_splint", "prescription_medication", "otc_at_prescription_strength", "iv_fluids", "physiotherapy", "foreign_body_removal_eye_tools", "surgical_debridement", "hospital_admission", "other_medical", "x_ray_diagnosis", "observation_only"] as const satisfies readonly Schemas["Treatment"][];
export const ROOT_CAUSE_CODES = ["AD-01", "AD-02", "AD-03", "AD-04", "AD-05", "AD-06", "AD-07", "IT-01", "IT-02", "IT-03", "IT-04", "TE-01", "TE-02", "TE-03", "TE-04", "TE-05", "TE-06", "TE-07", "TE-08", "OF-01", "OF-02", "OF-03", "OF-04", "OF-05", "OF-06", "OF-07", "OF-08", "OF-09", "OF-10"] as const satisfies readonly Schemas["RootCauseCode"][];
