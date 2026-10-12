import type { Schemas as S } from "@/lib/api/client";

/** 7a vehicle accident lists (contract v0.14.0); labels live under `veh.enum.*`. */
export const VEH_ROAD_TYPES = ["site_road", "airside", "public_road"] as const satisfies readonly S["VehRoadType"][];
export const VEH_JOURNEY_PURPOSES = [
  "work_task",
  "material_delivery",
  "crew_transport",
  "commuting_company_transport",
  "commuting_own",
  "personal",
  "other",
] as const satisfies readonly S["VehJourneyPurpose"][];
export const VEH_COMMUTING: readonly S["VehJourneyPurpose"][] = ["commuting_company_transport", "commuting_own"];
export const VEH_LIGHTS = ["daylight", "dusk_dawn", "dark_lit", "dark_unlit"] as const satisfies readonly S["VehLight"][];
export const VEH_SURFACES = ["dry", "wet", "sand_on_road", "gravel_unpaved", "other"] as const satisfies readonly S["VehSurface"][];
export const VEH_AUTHORITIES = ["najm", "traffic_police", "airport_operator", "none_internal"] as const satisfies readonly S["VehReportAuthority"][];
export const VEH_LIABILITY = [0, 25, 50, 75, 100] as const;
export const VEH_OWNERSHIPS = ["own_company", "contractor", "hired", "third_party", "unknown"] as const satisfies readonly S["VehOwnership"][];
export const VEH_COMPANY_OWNERSHIPS: readonly S["VehOwnership"][] = ["own_company", "contractor", "hired"];
export const VEH_ROLES = ["striking", "struck", "single_vehicle", "parked"] as const satisfies readonly S["VehRole"][];
export const VEH_DAMAGES = ["none", "minor", "major", "total_loss"] as const satisfies readonly S["VehDamage"][];
export const VEH_DOC_STATES = ["valid", "expired", "unknown"] as const satisfies readonly S["VehDocState"][];
export const VEH_SEAT_BELTS = ["worn", "not_worn", "unknown", "not_fitted"] as const satisfies readonly S["VehSeatBelt"][];
export const VEH_SPEED_SOURCES = ["vehicle_recorder", "report", "estimate", "unknown"] as const satisfies readonly S["VehSpeedSource"][];
export const VEH_DRIVER_KINDS = ["worker", "external", "none"] as const satisfies readonly S["VehDriverKind"][];
export const VEH_LICENCE_CHECKS = ["valid", "expired", "wrong_class", "no_licence", "not_checked"] as const satisfies readonly S["VehLicenceCheck"][];
export const VEH_CATEGORIES = [
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
  "private_car",
  "motorcycle",
  "bicycle_pedestrian",
] as const satisfies readonly S["VehCategory"][];
export const PLATE_TYPES = ["private", "transport", "heavy_equipment", "none"] as const satisfies readonly S["PlateType"][];
export const LICENCE_ISSUERS = ["ksa", "gcc", "international"] as const satisfies readonly S["LicenceIssuer"][];
export const LICENCE_CLASSES = ["private", "public_transport", "heavy_transport", "heavy_equipment", "motorcycle"] as const satisfies readonly S["LicenceClass"][];

/** Status-badge tone key for a licence check result (colour plus text, never colour alone). */
export function licenceCheckStatus(v: S["VehLicenceCheck"] | null | undefined): string {
  if (v === "valid") return "ok";
  if (v === "not_checked" || !v) return "pending";
  return "error";
}

/** Plate as one LTR string: Latin letters, digits; Arabic letters shown separately. */
export function plateText(r: { plate_letters_en?: string | null; plate_digits?: string | null }): string {
  return [r.plate_letters_en, r.plate_digits].filter(Boolean).join(" ");
}
