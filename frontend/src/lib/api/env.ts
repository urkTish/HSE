"use client";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "./client";
import type { QueryOf } from "./queries";

type Opt = { enabled?: boolean };

/** Query keys for Phase 6e (environmental). Writes invalidate by the first element. */
export const enk = {
  reference: () => ["env-reference"] as const,
  settings: (pid: string) => ["env-settings", pid] as const,
  aspects: (pid: string, q: object) => ["env-aspects", pid, q] as const,
  aspect: (id: string) => ["env-aspect", id] as const,
  providers: (q: object) => ["env-providers", q] as const,
  provider: (id: string) => ["env-provider", id] as const,
  permits: (pid: string, q: object) => ["env-permits", pid, q] as const,
  permit: (id: string) => ["env-permit", id] as const,
  streams: (pid: string) => ["waste-streams", pid] as const,
  areas: (pid: string, q: object) => ["waste-areas", pid, q] as const,
  area: (id: string) => ["waste-area", id] as const,
  consignments: (pid: string, q: object) => ["waste-consignments", pid, q] as const,
  consignment: (id: string) => ["waste-consignment", id] as const,
  instruments: (pid: string) => ["env-instruments", pid] as const,
  points: (pid: string) => ["env-points", pid] as const,
  point: (id: string) => ["env-point", id] as const,
  readings: (pid: string, q: object) => ["env-readings", pid, q] as const,
  backgrounds: (pid: string) => ["background-declarations", pid] as const,
  exceedances: (pid: string, q: object) => ["env-exceedances", pid, q] as const,
  exceedance: (id: string) => ["env-exceedance", id] as const,
  spills: (pid: string, q: object) => ["spills", pid, q] as const,
  spill: (id: string) => ["spill", id] as const,
  water: (pid: string, q: object) => ["water-entries", pid, q] as const,
  discharge: (pid: string) => ["discharge-days", pid] as const,
  complaints: (pid: string, q: object) => ["env-complaints", pid, q] as const,
  complaint: (id: string) => ["env-complaint", id] as const,
  nearby: (id: string) => ["env-complaint-nearby", id] as const,
  actions: (pid: string) => ["env-action-panel", pid] as const,
  band: (pid: string) => ["env-band", pid] as const,
  kpis: (q: object) => ["kpi", "environmental", q] as const,
};

/** Every Phase 6e prefix plus the Phase 1 / 6c consumers (incidents, CAs, spill kits, dashboard). */
export const ENV_PREFIXES = [
  ...new Set(Object.values(enk).map((f) => (f as (...a: string[]) => readonly unknown[])("", "", "")[0] as string)),
  "kpi",
  "dashboard",
  "incidents",
  "incident",
  "corrective-actions",
  "emergency-assets",
  "history",
  "attachments",
];

export function useEnvRefresh() {
  const qc = useQueryClient();
  return async () => {
    await Promise.all(ENV_PREFIXES.map((k) => qc.invalidateQueries({ queryKey: [k] })));
  };
}

const list = { placeholderData: keepPreviousData };
const on = (id: string, o: Opt) => Boolean(id) && (o.enabled ?? true);
const P = (pid: string) => ({ path: { project_id: pid } });

export function useEnvReference() {
  return useQuery({ queryKey: enk.reference(), queryFn: () => unwrap(api.GET("/api/v1/env-reference")), staleTime: 10 * 60_000 });
}

export function useEnvSettings(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: enk.settings(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/env-settings", { params: P(pid) })), enabled: on(pid, o) });
}

export function useAspects(pid: string, q: QueryOf<"list_env_aspects"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: enk.aspects(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/env-aspects", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useAspect(id: string, o: Opt = {}) {
  return useQuery({ queryKey: enk.aspect(id), queryFn: () => unwrap(api.GET("/api/v1/env-aspects/{aspect_id}", { params: { path: { aspect_id: id } } })), enabled: on(id, o) });
}

export function useEnvProviders(q: QueryOf<"list_env_providers"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: enk.providers(q), queryFn: () => unwrap(api.GET("/api/v1/env-providers", { params: { query: { page_size: 200, ...q } } })), enabled: o.enabled ?? true, ...list });
}

export function useEnvProvider(id: string, o: Opt = {}) {
  return useQuery({ queryKey: enk.provider(id), queryFn: () => unwrap(api.GET("/api/v1/env-providers/{provider_id}", { params: { path: { provider_id: id } } })), enabled: on(id, o) });
}

export function useEnvPermits(pid: string, q: QueryOf<"list_env_permits"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: enk.permits(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/env-permits", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useEnvPermit(id: string, o: Opt = {}) {
  return useQuery({ queryKey: enk.permit(id), queryFn: () => unwrap(api.GET("/api/v1/env-permits/{permit_id}", { params: { path: { permit_id: id } } })), enabled: on(id, o) });
}

export function useWasteStreams(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: enk.streams(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/waste-streams", { params: P(pid) })), enabled: on(pid, o) });
}

export function useWasteAreas(pid: string, q: QueryOf<"list_waste_areas"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: enk.areas(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/waste-storage-areas", { params: { ...P(pid), query: { page_size: 200, ...q } } })), enabled: on(pid, o), ...list });
}

export function useWasteArea(id: string, o: Opt = {}) {
  return useQuery({ queryKey: enk.area(id), queryFn: () => unwrap(api.GET("/api/v1/waste-storage-areas/{area_id}", { params: { path: { area_id: id } } })), enabled: on(id, o) });
}

export function useConsignments(pid: string, q: QueryOf<"list_waste_consignments"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: enk.consignments(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/waste-consignments", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useConsignment(id: string, o: Opt = {}) {
  return useQuery({ queryKey: enk.consignment(id), queryFn: () => unwrap(api.GET("/api/v1/waste-consignments/{consignment_id}", { params: { path: { consignment_id: id } } })), enabled: on(id, o) });
}

export function useEnvInstruments(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: enk.instruments(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/env-instruments", { params: { ...P(pid), query: { page_size: 200 } } })), enabled: on(pid, o) });
}

export function useEnvPoints(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: enk.points(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/env-points", { params: { ...P(pid), query: { page_size: 200 } } })), enabled: on(pid, o) });
}

export function useEnvPoint(id: string, o: Opt = {}) {
  return useQuery({ queryKey: enk.point(id), queryFn: () => unwrap(api.GET("/api/v1/env-points/{point_id}", { params: { path: { point_id: id } } })), enabled: on(id, o) });
}

export function useEnvReadings(pid: string, q: QueryOf<"list_env_readings"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: enk.readings(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/env-readings", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useBackgrounds(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: enk.backgrounds(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/background-declarations", { params: { ...P(pid), query: { page_size: 100 } } })), enabled: on(pid, o) });
}

export function useExceedances(pid: string, q: QueryOf<"list_env_exceedances"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: enk.exceedances(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/env-exceedances", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useExceedance(id: string, o: Opt = {}) {
  return useQuery({ queryKey: enk.exceedance(id), queryFn: () => unwrap(api.GET("/api/v1/env-exceedances/{exceedance_id}", { params: { path: { exceedance_id: id } } })), enabled: on(id, o) });
}

export function useSpills(pid: string, q: QueryOf<"list_spills"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: enk.spills(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/spills", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useSpill(id: string, o: Opt = {}) {
  return useQuery({ queryKey: enk.spill(id), queryFn: () => unwrap(api.GET("/api/v1/spills/{spill_id}", { params: { path: { spill_id: id } } })), enabled: on(id, o) });
}

export function useWaterEntries(pid: string, q: QueryOf<"list_water_entries"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: enk.water(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/water-entries", { params: { ...P(pid), query: { page_size: 200, ...q } } })), enabled: on(pid, o), ...list });
}

export function useDischargeDays(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: enk.discharge(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/discharge-days", { params: { ...P(pid), query: { page_size: 100 } } })), enabled: on(pid, o) });
}

export function useComplaints(pid: string, q: QueryOf<"list_env_complaints"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: enk.complaints(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/env-complaints", { params: { ...P(pid), query: q } })), enabled: on(pid, o), ...list });
}

export function useComplaint(id: string, o: Opt = {}) {
  return useQuery({ queryKey: enk.complaint(id), queryFn: () => unwrap(api.GET("/api/v1/env-complaints/{complaint_id}", { params: { path: { complaint_id: id } } })), enabled: on(id, o) });
}

export function useNearbyReadings(id: string, o: Opt = {}) {
  return useQuery({ queryKey: enk.nearby(id), queryFn: () => unwrap(api.GET("/api/v1/env-complaints/{complaint_id}/nearby-readings", { params: { path: { complaint_id: id } } })), enabled: on(id, o) });
}

export function useEnvActionPanel(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: enk.actions(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/env-action-panel", { params: P(pid) })), enabled: on(pid, o) });
}

/** Environment band (§8.1 item 2) is live: refreshed every minute. */
export function useEnvBand(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: enk.band(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/env-band", { params: P(pid) })), enabled: on(pid, o), refetchInterval: 60_000 });
}

export function useEnvKpis(q: QueryOf<"get_environmental_kpis">, o: Opt = {}) {
  return useQuery({ queryKey: enk.kpis(q), queryFn: () => unwrap(api.GET("/api/v1/kpi/environmental", { params: { query: q } })), enabled: o.enabled ?? true, ...list });
}
