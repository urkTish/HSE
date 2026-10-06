"use client";
import { useMemo } from "react";
import type { Schemas } from "@/lib/api/client";
import type { KpiQuery } from "@/lib/api/kpi";
import { useSearchState, type ParamValue } from "@/lib/url-state";

/** URL keys of the dashboard filter bar (D-2). Short so shared links stay readable. */
export const DASH_KEYS = ["all", "site", "zone", "zt", "eng", "subs", "tier", "period", "anchor", "start", "end", "as_of", "cmp"] as const;

export interface DashFilters {
  allProjects: boolean;
  siteIds: string[];
  zoneIds: string[];
  zoneType: Schemas["ZoneType"] | null;
  engagementIds: string[];
  includeSubs: boolean;
  tiers: number[];
  period: Schemas["PeriodPreset"];
  anchor: string | null;
  start: string | null;
  end: string | null;
  asOf: string | null;
  compare: Schemas["ComparisonKind"][];
}

export function toKpiQuery(projectId: string | null, f: DashFilters): KpiQuery {
  return {
    project_id: f.allProjects || !projectId ? null : [projectId],
    all_projects: f.allProjects,
    site_id: f.siteIds.length ? f.siteIds : null,
    zone_id: f.zoneIds.length ? f.zoneIds : null,
    zone_type: f.zoneType,
    engagement_id: f.engagementIds.length ? f.engagementIds : null,
    include_subcontractors: f.includeSubs,
    tier: f.tiers.length ? f.tiers : null,
    period: f.period,
    anchor: f.period === "custom" ? null : f.anchor,
    start: f.period === "custom" ? f.start : null,
    end: f.period === "custom" ? f.end : null,
    as_of: f.asOf,
    compare: f.compare.length ? f.compare : ["previous"],
  };
}

export function fromPreferences(p: Schemas["DashboardFilters"]): Record<string, ParamValue> {
  return {
    all: p.all_projects ? "1" : null,
    site: p.site_ids ?? [],
    zone: p.zone_ids ?? [],
    zt: p.zone_type,
    eng: p.engagement_ids ?? [],
    subs: p.include_subcontractors === false ? "0" : null,
    tier: (p.tiers ?? []).map(String),
    period: p.period && p.period !== "month" ? p.period : null,
    start: p.start,
    end: p.end,
    cmp: (p.compare ?? []).filter((c) => c !== "previous").length ? (p.compare ?? []) : null,
  };
}

export function toPreferences(projectId: string | null, f: DashFilters): Schemas["DashboardFilters"] {
  return {
    project_id: projectId,
    all_projects: f.allProjects,
    site_ids: f.siteIds,
    zone_ids: f.zoneIds,
    zone_type: f.zoneType,
    engagement_ids: f.engagementIds,
    include_subcontractors: f.includeSubs,
    tiers: f.tiers,
    period: f.period,
    start: f.start,
    end: f.end,
    compare: f.compare,
  };
}

/** Dashboard filters from the URL; `set` writes them back (shareable, back-button friendly). */
export function useDashFilters() {
  const s = useSearchState();
  const filters = useMemo<DashFilters>(
    () => ({
      allProjects: s.getBool("all") ?? false,
      siteIds: s.getAll("site"),
      zoneIds: s.getAll("zone"),
      zoneType: (s.get("zt") as Schemas["ZoneType"] | null) || null,
      engagementIds: s.getAll("eng"),
      includeSubs: s.getBool("subs") ?? true,
      tiers: s
        .getAll("tier")
        .map(Number)
        .filter((n) => n >= 1 && n <= 3),
      period: ((s.get("period") as Schemas["PeriodPreset"] | null) || "month") as Schemas["PeriodPreset"],
      anchor: s.get("anchor"),
      start: s.get("start"),
      end: s.get("end"),
      asOf: s.get("as_of"),
      compare: s.getAll("cmp") as Schemas["ComparisonKind"][],
    }),
    [s],
  );
  const hasAny = DASH_KEYS.some((k) => s.keys.includes(k));
  return { filters, set: s.set, hasAny, search: s };
}

/** Shift an ISO date by whole periods (anchor arrows); quarter = 3 months. */
export function shiftAnchor(anchor: string, period: Schemas["PeriodPreset"], dir: -1 | 1): string {
  const [y, m, d] = anchor.split("-").map(Number);
  const dt = new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1));
  if (period === "day") dt.setUTCDate(dt.getUTCDate() + dir);
  else if (period === "week") dt.setUTCDate(dt.getUTCDate() + 7 * dir);
  else if (period === "month") {
    dt.setUTCDate(1);
    dt.setUTCMonth(dt.getUTCMonth() + dir);
  } else if (period === "quarter") {
    dt.setUTCDate(1);
    dt.setUTCMonth(dt.getUTCMonth() + 3 * dir);
  } else if (period === "year") {
    dt.setUTCDate(1);
    dt.setUTCFullYear(dt.getUTCFullYear() + dir);
  }
  return dt.toISOString().slice(0, 10);
}

export const ANCHORED_PERIODS: Schemas["PeriodPreset"][] = ["day", "week", "month", "quarter", "year"];
