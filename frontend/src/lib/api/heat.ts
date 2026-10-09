"use client";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "./client";
import type { QueryOf } from "./queries";

type Opt = { enabled?: boolean };

/** Query keys for Phase 6b (heat stress). Writes invalidate by the first element. */
export const hk = {
  reference: () => ["heat-reference"] as const,
  settings: (pid: string) => ["heat-settings", pid] as const,
  regimeTable: () => ["heat-regime-table"] as const,
  instruments: (pid: string, q: object) => ["heat-instruments", pid, q] as const,
  points: (pid: string, q: object) => ["monitoring-points", pid, q] as const,
  stations: (pid: string, q: object) => ["rest-stations", pid, q] as const,
  readings: (pid: string, q: object) => ["wbgt-readings", pid, q] as const,
  board: (pid: string) => ["heat-board", pid] as const,
  duty: (pid: string, q: object) => ["heat-duty-list", pid, q] as const,
  plans: (pid: string, q: object) => ["acclimatisation-plans", pid, q] as const,
  plan: (id: string) => ["acclimatisation-plan", id] as const,
  checks: (pid: string, q: object) => ["heat-welfare-checks", pid, q] as const,
  patrols: (pid: string, q: object) => ["ban-patrols", pid, q] as const,
  exemptions: (pid: string, q: object) => ["ban-exemptions", pid, q] as const,
  log: (pid: string, q: object) => ["heat-illness-log", pid, q] as const,
  entry: (id: string) => ["heat-illness-entry", id] as const,
  actions: (pid: string) => ["heat-action-panel", pid] as const,
  reports: (pid: string, q: object) => ["heat-season-reports", pid, q] as const,
  kpis: (q: object) => ["kpi", "heat-stress", q] as const,
};

/** Every Phase 6b prefix plus the permit and dashboard consumers, refreshed together after a heat write. */
export const HEAT_PREFIXES = [
  ...new Set(Object.values(hk).map((f) => (f as (...a: string[]) => readonly unknown[])("", "", "")[0] as string)),
  "kpi",
  "dashboard",
  "permit",
  "permits",
  "corrective-actions",
  "history",
];

export function useHeatRefresh() {
  const qc = useQueryClient();
  return async () => {
    await Promise.all(HEAT_PREFIXES.map((k) => qc.invalidateQueries({ queryKey: [k] })));
  };
}

const list = { placeholderData: keepPreviousData };
const on = (id: string, o: Opt) => Boolean(id) && (o.enabled ?? true);
const P = (pid: string) => ({ path: { project_id: pid } });

export function useHeatReference() {
  return useQuery({ queryKey: hk.reference(), queryFn: () => unwrap(api.GET("/api/v1/heat-reference")), staleTime: 10 * 60_000 });
}

export function useHeatSettings(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: hk.settings(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/heat-settings", { params: P(pid) })), enabled: on(pid, o) });
}

export function useRegimeTable(o: Opt = {}) {
  return useQuery({ queryKey: hk.regimeTable(), queryFn: () => unwrap(api.GET("/api/v1/heat-regime-table")), enabled: o.enabled ?? true });
}

export function useHeatInstruments(pid: string, q: QueryOf<"list_heat_instruments"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: hk.instruments(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/heat-instruments", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useMonitoringPoints(pid: string, q: QueryOf<"list_monitoring_points"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: hk.points(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/monitoring-points", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useRestStations(pid: string, q: QueryOf<"list_rest_stations"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: hk.stations(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/rest-stations", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useWbgtReadings(pid: string, q: QueryOf<"list_wbgt_readings"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: hk.readings(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/wbgt-readings", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

/** Live board: refreshed every minute (the server rebuilds the zone state every 60 s). */
export function useHeatBoard(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: hk.board(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/heat-board", { params: P(pid) })), enabled: on(pid, o), refetchInterval: 60_000 });
}

export function useHeatDutyList(pid: string, q: QueryOf<"get_heat_duty_list"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: hk.duty(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/heat-duty-list", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useAcclimatisationPlans(pid: string, q: QueryOf<"list_acclimatisation_plans"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: hk.plans(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/acclimatisation-plans", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useAcclimatisationPlan(id: string, o: Opt = {}) {
  return useQuery({ queryKey: hk.plan(id), queryFn: () => unwrap(api.GET("/api/v1/acclimatisation-plans/{plan_id}", { params: { path: { plan_id: id } } })), enabled: on(id, o) });
}

export function useWelfareChecks(pid: string, q: QueryOf<"list_welfare_checks"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: hk.checks(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/heat-welfare-checks", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useBanPatrols(pid: string, q: QueryOf<"list_ban_patrols"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: hk.patrols(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/ban-patrols", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useBanExemptions(pid: string, q: QueryOf<"list_ban_exemptions"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: hk.exemptions(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/ban-exemptions", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useHeatLog(pid: string, q: QueryOf<"list_heat_illness_log"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: hk.log(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/heat-illness-log", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useHeatLogEntry(id: string, o: Opt = {}) {
  return useQuery({ queryKey: hk.entry(id), queryFn: () => unwrap(api.GET("/api/v1/heat-illness-log/{entry_id}", { params: { path: { entry_id: id } } })), enabled: on(id, o) });
}

export function useHeatActionPanel(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: hk.actions(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/heat-action-panel", { params: P(pid) })), enabled: on(pid, o) });
}

export function useSeasonReports(pid: string, q: QueryOf<"list_heat_season_reports"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: hk.reports(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/heat-season-reports", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useHeatKpis(q: QueryOf<"get_heat_stress_kpis">, o: Opt = {}) {
  return useQuery({ queryKey: hk.kpis(q), queryFn: () => unwrap(api.GET("/api/v1/kpi/heat-stress", { params: { query: q } })), enabled: o.enabled ?? true, ...list });
}
