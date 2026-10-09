import type { Schemas } from "@/lib/api/client";

type S = Schemas;

/** Phase 6e (environmental) enum values in display order (spec 6e §3, §4). Reference lists (AS, IM, PT, WS, PA…) come from the server. */
export const ENV_KPI_GROUP_BY = ["stream", "class", "route", "transporter", "facility", "point", "parameter", "cause", "substance", "contractor", "month"] as const satisfies readonly S["EnvKpiGroupBy"][];
export const WASTE_CLASSES = ["inert", "non_hazardous", "hazardous", "liquid_sewage"] as const satisfies readonly S["WasteClass"][];
export const WASTE_ROUTES = ["reuse", "recycle", "recovery", "treatment", "disposal_landfill"] as const satisfies readonly S["WasteRoute"][];
export const ASPECT_STATUSES = ["draft", "active", "archived"] as const satisfies readonly S["AspectStatus"][];
export const PERMIT_STATUSES = ["pending", "valid", "expiring", "expired", "suspended", "superseded", "cancelled"] as const satisfies readonly S["EnvPermitStatus"][];
export const CONSIGNMENT_STATUSES = ["dispatched", "received", "closed", "rejected", "voided"] as const satisfies readonly S["ConsignmentStatus"][];
export const EXCEEDANCE_STATUSES = ["open", "reviewed", "closed", "voided"] as const satisfies readonly S["ExceedanceStatus"][];
export const SPILL_STATUSES = ["reported", "cleaned_up", "closed", "voided"] as const satisfies readonly S["SpillStatus"][];
export const COMPLAINT_STATUSES = ["open", "responded", "closed", "voided"] as const satisfies readonly S["ComplaintStatus"][];
export const QUANTITY_UNITS = ["t", "m3", "L"] as const satisfies readonly S["QuantityUnit"][];
export const ENV_REACHED = ["none", "soil", "drain", "water_body"] as const satisfies readonly S["EnvReached"][];
export const CONTROL_LEVELS = ["elimination", "substitution", "engineering", "administrative", "ppe"] as const satisfies readonly S["ControlLevel"][];
export const HAZARDOUS_STORES: readonly S["StorageAreaType"][] = ["hazardous_store", "liquid_store"];
