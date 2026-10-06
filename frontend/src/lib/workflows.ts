import type { Schemas } from "@/lib/api/client";

/**
 * Allowed status transitions from spec §4, used only to decide which buttons to show.
 * The server validates every transition (409 INVALID_TRANSITION / TRANSITION_CONDITION_NOT_MET).
 */
export interface Edge<S extends string> {
  to: S;
  reasonRequired?: boolean;
  /** "approve" edges need contractor.approve; others contractor.create (contractors only). */
  approve?: boolean;
  kind?: string;
}

export const PROJECT_FLOW: Record<Schemas["ProjectStatus"], Edge<Schemas["ProjectStatus"]>[]> = {
  planning: [{ to: "active" }],
  active: [
    { to: "on_hold", reasonRequired: true },
    { to: "closed", reasonRequired: true },
  ],
  on_hold: [{ to: "active" }, { to: "closed", reasonRequired: true }],
  closed: [{ to: "active", reasonRequired: true, kind: "reopen" }],
};

export const SITE_FLOW: Record<Schemas["SiteStatus"], Edge<Schemas["SiteStatus"]>[]> = {
  active: [{ to: "inactive" }],
  inactive: [{ to: "active" }],
};

export const ZONE_FLOW: Record<Schemas["ZoneStatus"], Edge<Schemas["ZoneStatus"]>[]> = {
  active: [{ to: "temporarily_closed" }, { to: "archived" }],
  temporarily_closed: [{ to: "active" }, { to: "archived" }],
  archived: [],
};

export const CONTRACTOR_FLOW: Record<Schemas["ContractorStatus"], Edge<Schemas["ContractorStatus"]>[]> = {
  draft: [{ to: "pending_approval", kind: "submit" }, { to: "blacklisted", reasonRequired: true, approve: true, kind: "blacklist" }],
  pending_approval: [
    { to: "approved", approve: true, kind: "approve" },
    { to: "draft", reasonRequired: true, approve: true, kind: "returnToDraft" },
    { to: "blacklisted", reasonRequired: true, approve: true, kind: "blacklist" },
  ],
  approved: [
    { to: "suspended", reasonRequired: true, approve: true, kind: "suspend" },
    { to: "demobilised", approve: true, kind: "demobilise" },
    { to: "blacklisted", reasonRequired: true, approve: true, kind: "blacklist" },
  ],
  suspended: [
    { to: "approved", reasonRequired: true, approve: true, kind: "reinstate" },
    { to: "demobilised", approve: true, kind: "demobilise" },
    { to: "blacklisted", reasonRequired: true, approve: true, kind: "blacklist" },
  ],
  demobilised: [{ to: "blacklisted", reasonRequired: true, approve: true, kind: "blacklist" }],
  blacklisted: [{ to: "suspended", reasonRequired: true, approve: true, kind: "liftBlacklist" }],
};

export const USER_FLOW: Record<Schemas["UserStatus"], Edge<Schemas["UserStatus"]>[]> = {
  invited: [],
  active: [{ to: "deactivated", reasonRequired: true, kind: "deactivate" }],
  locked: [{ to: "active", kind: "unlock" }, { to: "deactivated", reasonRequired: true, kind: "deactivate" }],
  deactivated: [{ to: "active", reasonRequired: true, kind: "reactivate" }],
};

// ---- Phase 1 (spec 1-dashboard §4) ----
type Cap = Schemas["Capability"];
export interface P1Edge<S extends string> {
  to: S;
  kind: string;
  cap: Cap;
  reasonRequired?: boolean;
  destructive?: boolean;
}

export const WORKFORCE_FLOW: Record<Schemas["WorkforceStatus"], P1Edge<Schemas["WorkforceStatus"]>[]> = {
  draft: [{ to: "submitted", kind: "submit", cap: "workforce.edit" }],
  submitted: [
    { to: "verified", kind: "verify", cap: "workforce.verify" },
    { to: "draft", kind: "backToDraft", cap: "workforce.edit" },
  ],
  verified: [{ to: "submitted", kind: "correct", cap: "workforce.verify", reasonRequired: true }],
  locked: [{ to: "verified", kind: "unlockRow", cap: "workforce.unlock", reasonRequired: true }],
};
