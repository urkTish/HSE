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
] as const satisfies readonly Schemas["AuditAction"][];
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
