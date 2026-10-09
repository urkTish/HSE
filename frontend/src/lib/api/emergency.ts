"use client";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "./client";
import type { QueryOf } from "./queries";

type Opt = { enabled?: boolean };

/** Query keys for Phase 6c (emergency preparedness). Writes invalidate by the first element. */
export const ek = {
  reference: () => ["emergency-reference"] as const,
  settings: (pid: string) => ["emergency-settings", pid] as const,
  erps: (pid: string) => ["erps", pid] as const,
  erp: (id: string) => ["erp", id] as const,
  aps: (pid: string, q: object) => ["assembly-points", pid, q] as const,
  contacts: (pid: string) => ["emergency-contacts", pid] as const,
  profiles: (pid: string) => ["zone-emergency-profiles", pid] as const,
  roster: (pid: string, q: object) => ["emergency-roster", pid, q] as const,
  teams: (pid: string, q: object) => ["rescue-teams", pid, q] as const,
  coverage: (pid: string, q: object) => ["emergency-coverage", pid, q] as const,
  board: (pid: string) => ["emergency-board", pid] as const,
  actions: (pid: string) => ["emergency-action-panel", pid] as const,
  info: (pid: string, zones: string[]) => ["emergency-info", pid, zones] as const,
  assets: (pid: string, q: object) => ["emergency-assets", pid, q] as const,
  asset: (id: string) => ["emergency-asset", id] as const,
  checks: (pid: string, q: object) => ["emergency-asset-checks", pid, q] as const,
  programme: (pid: string, q: object) => ["drill-programme", pid, q] as const,
  drills: (pid: string, q: object) => ["drills", pid, q] as const,
  drill: (id: string) => ["drill", id] as const,
  muster: (id: string) => ["muster", id] as const,
  events: (pid: string, q: object) => ["emergency-events", pid, q] as const,
  event: (id: string) => ["emergency-event", id] as const,
  kpis: (q: object) => ["kpi", "emergency", q] as const,
};

/** Every Phase 6c prefix plus the permit, CA and dashboard consumers, refreshed together after a 6c write. */
export const EMERGENCY_PREFIXES = [
  ...new Set(Object.values(ek).map((f) => (f as (...a: string[]) => readonly unknown[])("", "", "")[0] as string)),
  "kpi",
  "dashboard",
  "permit",
  "permits",
  "corrective-actions",
  "history",
];

export function useEmergencyRefresh() {
  const qc = useQueryClient();
  return async () => {
    await Promise.all(EMERGENCY_PREFIXES.map((k) => qc.invalidateQueries({ queryKey: [k] })));
  };
}

const list = { placeholderData: keepPreviousData };
const on = (id: string, o: Opt) => Boolean(id) && (o.enabled ?? true);
const P = (pid: string) => ({ path: { project_id: pid } });

export function useEmergencyReference() {
  return useQuery({ queryKey: ek.reference(), queryFn: () => unwrap(api.GET("/api/v1/emergency-reference")), staleTime: 10 * 60_000 });
}

export function useEmergencySettings(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: ek.settings(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/emergency-settings", { params: P(pid) })), enabled: on(pid, o) });
}

export function useErps(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: ek.erps(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/erps", { params: { ...P(pid), query: { page_size: 100 } } })), enabled: on(pid, o), ...list });
}

export function useErp(id: string, o: Opt = {}) {
  return useQuery({ queryKey: ek.erp(id), queryFn: () => unwrap(api.GET("/api/v1/erps/{erp_id}", { params: { path: { erp_id: id } } })), enabled: on(id, o) });
}

export function useAssemblyPoints(pid: string, q: QueryOf<"list_assembly_points"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: ek.aps(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/assembly-points", { params: { ...P(pid), query: { page_size: 200, ...q } } })), enabled: on(pid, o), ...list });
}

export function useEmergencyContacts(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: ek.contacts(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/emergency-contacts", { params: { ...P(pid), query: { page_size: 200 } } })), enabled: on(pid, o) });
}

export function useZoneProfiles(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: ek.profiles(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/zone-emergency-profiles", { params: P(pid) })), enabled: on(pid, o) });
}

export function useRoster(pid: string, q: QueryOf<"list_emergency_roster"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: ek.roster(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/emergency-roster", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useRescueTeams(pid: string, q: QueryOf<"list_rescue_teams"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: ek.teams(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/rescue-teams", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useCoverage(pid: string, q: QueryOf<"get_emergency_coverage">, o: Opt = {}) {
  return useQuery({ queryKey: ek.coverage(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/emergency-coverage", { params: { ...P(pid), query: q } })), enabled: on(pid, o) && Boolean(q.date_from), ...list });
}

/** Live board: refreshed every minute (events, musters and the current shift change minute by minute). */
export function useEmergencyBoard(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: ek.board(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/emergency-board", { params: P(pid) })), enabled: on(pid, o), refetchInterval: 60_000 });
}

export function useEmergencyActionPanel(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: ek.actions(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/emergency-action-panel", { params: P(pid) })), enabled: on(pid, o) });
}

export function useEmergencyInfo(pid: string, zones: string[], o: Opt = {}) {
  return useQuery({
    queryKey: ek.info(pid, zones),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/emergency-info", { params: { ...P(pid), query: { zone_ids: zones } } })),
    enabled: on(pid, o) && zones.length > 0,
  });
}

export function useEmergencyAssets(pid: string, q: QueryOf<"list_emergency_assets"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: ek.assets(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/emergency-assets", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useEmergencyAsset(id: string, o: Opt = {}) {
  return useQuery({ queryKey: ek.asset(id), queryFn: () => unwrap(api.GET("/api/v1/emergency-assets/{asset_id}", { params: { path: { asset_id: id } } })), enabled: on(id, o) });
}

export function useAssetChecks(pid: string, q: QueryOf<"list_emergency_asset_checks"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: ek.checks(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/emergency-asset-checks", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useDrillProgramme(pid: string, q: QueryOf<"get_drill_programme"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: ek.programme(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/drill-programme", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useDrills(pid: string, q: QueryOf<"list_drills"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: ek.drills(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/drills", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useDrill(id: string, o: Opt = {}) {
  return useQuery({ queryKey: ek.drill(id), queryFn: () => unwrap(api.GET("/api/v1/drills/{drill_id}", { params: { path: { drill_id: id } } })), enabled: on(id, o) });
}

/** An open muster is refreshed every 10 s: scans arrive from reader devices and other phones. */
export function useMuster(id: string, o: Opt & { live?: boolean } = {}) {
  return useQuery({
    queryKey: ek.muster(id),
    queryFn: () => unwrap(api.GET("/api/v1/musters/{muster_id}", { params: { path: { muster_id: id } } })),
    enabled: on(id, o),
    refetchInterval: o.live ? 10_000 : false,
  });
}

export function useEmergencyEvents(pid: string, q: QueryOf<"list_emergency_events"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: ek.events(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/emergency-events", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useEmergencyEvent(id: string, o: Opt = {}) {
  return useQuery({ queryKey: ek.event(id), queryFn: () => unwrap(api.GET("/api/v1/emergency-events/{event_id}", { params: { path: { event_id: id } } })), enabled: on(id, o) });
}

export function useEmergencyKpis(q: QueryOf<"get_emergency_kpis">, o: Opt = {}) {
  return useQuery({ queryKey: ek.kpis(q), queryFn: () => unwrap(api.GET("/api/v1/kpi/emergency", { params: { query: q } })), enabled: o.enabled ?? true, ...list });
}
