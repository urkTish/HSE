import type { Schemas } from "@/lib/api/client";

type S = Schemas;

/** Phase 6d (field assurance) enum values in display order (spec 6d §3, §4). Reference lists (IT, FS, AT, AF, AG…) come from the server. */
export const FIELD_KPIS = ["K-110", "K-111", "K-112", "K-113", "K-114", "K-115", "K-116", "K-117"] as const satisfies readonly S["KpiMetric"][];
export const FIELD_KPI_GROUP_BY = ["inspection_type", "template", "item_code", "contractor", "zone", "month", "language"] as const satisfies readonly S["FieldKpiGroupBy"][];
export const VERSION_STATUSES = ["draft", "published", "superseded", "retired"] as const satisfies readonly S["VersionStatus"][];
export const TEMPLATE_KINDS = ["inspection", "audit"] as const satisfies readonly S["TemplateKind"][];
export const ZONE_TYPES = ["airside", "landside", "other"] as const satisfies readonly S["ZoneType"][];
export const ITEM_TYPES = ["yes_no", "rating_0_3", "numeric", "single_select", "text", "photo", "count"] as const satisfies readonly S["ItemType"][];
export const SCORED_TYPES: readonly S["ItemType"][] = ["yes_no", "rating_0_3", "numeric", "single_select"];
export const OPTION_MAPPINGS = ["compliant", "non_compliant", "info"] as const satisfies readonly S["OptionMapping"][];
export const CONTROL_LEVELS = ["elimination", "substitution", "engineering", "administrative", "ppe"] as const satisfies readonly S["ControlLevel"][];
export const INSPECTION_SEVERITIES = ["minor", "major", "critical"] as const;
export const AUDIT_GRADES_F = ["ofi", "observation", "minor_nc", "major_nc"] as const;
export const STOP_STATUSES = ["active", "released", "voided"] as const satisfies readonly S["StopOrderStatus"][];
export const AUDIT_STATUSES = ["planned", "in_progress", "fieldwork_complete", "issued", "closed", "cancelled", "voided"] as const satisfies readonly S["AuditStatus"][];
export const AUDIT_TYPES = ["contractor_hse", "system_iso45001", "client_requested"] as const satisfies readonly S["AuditType"][];
export const TALK_STATUSES = ["delivered", "locked", "voided"] as const satisfies readonly S["TalkStatus"][];
export const TALK_SHIFTS = ["day", "night"] as const satisfies readonly S["TalkShift"][];
export const CAMPAIGN_STATUSES = ["draft", "issued", "closed", "cancelled"] as const satisfies readonly S["CampaignStatus"][];
export const WORKER_LANGUAGES = ["ar", "en", "ur", "hi", "bn", "ne", "tl", "ml", "ta", "other"] as const satisfies readonly S["WorkerLanguage"][];
export const ROTATIONS = ["none", "zones", "engagements"] as const satisfies readonly S["Rotation"][];
export const LINKED_REF_KINDS = ["incident", "observation_category", "template_item", "lesson"] as const satisfies readonly S["LinkedRefKind"][];

/** Severity order for "raise, never lower" (FND-1, AUD-2). */
export const SEVERITY_RANK: Record<string, number> = { ofi: 0, observation: 1, minor: 2, minor_nc: 2, major: 3, major_nc: 3, critical: 4 };
