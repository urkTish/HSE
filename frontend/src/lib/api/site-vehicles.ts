"use client";
import { useCallback } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "./client";
import type { QueryOf } from "./queries";

type Opt = { enabled?: boolean };

/** Query keys for Option 7b site vehicle & plant readiness (Prototype). Writes invalidate by the first element. */
export const svk = {
  reference: () => ["sv-reference"] as const,
  settings: (pid: string) => ["sv-settings", pid] as const,
  summary: (pid: string) => ["sv-summary", pid] as const,
  vehicles: (pid: string, q: object) => ["sv-vehicles", pid, q] as const,
  vehicle: (id: string) => ["sv-vehicle", id] as const,
  auths: (pid: string, q: object) => ["sv-auths", pid, q] as const,
  auth: (id: string) => ["sv-auth", id] as const,
  prefill: (pid: string, worker: string) => ["sv-auth-prefill", pid, worker] as const,
  checks: (pid: string, q: object) => ["sv-checks", pid, q] as const,
  check: (id: string) => ["sv-check", id] as const,
  form: (pid: string, vehicle: string) => ["sv-check-form", pid, vehicle] as const,
  missing: (pid: string, day: string) => ["sv-missing", pid, day] as const,
  journeys: (pid: string, q: object) => ["sv-journeys", pid, q] as const,
  journey: (id: string) => ["sv-journey", id] as const,
  kpis: (q: object) => ["kpi", "site-vehicles", q] as const,
};

/** Every 7b prefix plus the consumers that show 7b data (dashboard, expiring items, Phase 2 vehicles, CAs). */
export const SV_PREFIXES = ["sv-settings", "sv-summary", "sv-vehicles", "sv-vehicle", "sv-auths", "sv-auth", "sv-checks", "sv-check", "sv-check-form", "sv-missing", "sv-journeys", "sv-journey", "kpi", "vehicles", "vehicle", "corrective-actions", "history"];

export function useSvRefresh() {
  const qc = useQueryClient();
  return useCallback(
    async () => {
      await Promise.all(SV_PREFIXES.map((k) => qc.invalidateQueries({ queryKey: [k] })));
    },
    [qc],
  );
}

const list = { placeholderData: keepPreviousData };
const on = (id: string, o: Opt) => Boolean(id) && (o.enabled ?? true);
const P = (pid: string) => ({ path: { project_id: pid } });

export function useSvReference() {
  return useQuery({ queryKey: svk.reference(), queryFn: () => unwrap(api.GET("/api/v1/site-vehicles/reference")), staleTime: 10 * 60_000 });
}

export function useSvSettings(pid: string, o: Opt = {}) {
  return useQuery({
    queryKey: svk.settings(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/site-vehicle-settings", { params: P(pid) })),
    enabled: on(pid, o),
    staleTime: 60_000,
    retry: false,
  });
}

export function useSvSummary(pid: string, o: Opt = {}) {
  return useQuery({
    queryKey: svk.summary(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/site-vehicles/summary", { params: P(pid) })),
    enabled: on(pid, o),
    retry: false,
  });
}

export function useSiteVehicles(pid: string, q: QueryOf<"list_site_vehicles"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: svk.vehicles(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/site-vehicles", { params: { ...P(pid), query: q } })),
    enabled: on(pid, o),
    retry: false,
    ...list,
  });
}

export function useSiteVehicle(id: string, o: Opt = {}) {
  return useQuery({ queryKey: svk.vehicle(id), queryFn: () => unwrap(api.GET("/api/v1/site-vehicles/{vehicle_id}", { params: { path: { vehicle_id: id } } })), enabled: on(id, o), retry: false });
}

export function useDriverAuths(pid: string, q: QueryOf<"list_driver_authorisations"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: svk.auths(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/driver-authorisations", { params: { ...P(pid), query: q } })),
    enabled: on(pid, o),
    retry: false,
    ...list,
  });
}

export function useDriverAuth(id: string, o: Opt = {}) {
  return useQuery({ queryKey: svk.auth(id), queryFn: () => unwrap(api.GET("/api/v1/driver-authorisations/{auth_id}", { params: { path: { auth_id: id } } })), enabled: on(id, o), retry: false });
}

export function useAuthPrefill(pid: string, workerId: string, o: Opt = {}) {
  return useQuery({
    queryKey: svk.prefill(pid, workerId),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/driver-authorisations/prefill", { params: { ...P(pid), query: { worker_id: workerId } } })),
    enabled: on(pid, o) && Boolean(workerId),
    retry: false,
  });
}

export function usePreUseChecks(pid: string, q: QueryOf<"list_pre_use_checks"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: svk.checks(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/pre-use-checks", { params: { ...P(pid), query: q } })),
    enabled: on(pid, o),
    retry: false,
    ...list,
  });
}

export function usePreUseCheck(id: string, o: Opt = {}) {
  return useQuery({ queryKey: svk.check(id), queryFn: () => unwrap(api.GET("/api/v1/pre-use-checks/{check_id}", { params: { path: { check_id: id } } })), enabled: on(id, o), retry: false });
}

export function usePreUseForm(pid: string, vehicleId: string, o: Opt = {}) {
  return useQuery({
    queryKey: svk.form(pid, vehicleId),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/pre-use-checks/form", { params: { ...P(pid), query: { vehicle_id: vehicleId } } })),
    enabled: on(pid, o) && Boolean(vehicleId),
    retry: false,
  });
}

export function useMissingChecks(pid: string, day: string, o: Opt = {}) {
  return useQuery({
    queryKey: svk.missing(pid, day),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/pre-use-checks/missing", { params: { ...P(pid), query: { day: day || null } } })),
    enabled: on(pid, o),
    retry: false,
    ...list,
  });
}

export function useJourneyPlans(pid: string, q: QueryOf<"list_journey_plans"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: svk.journeys(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/journey-plans", { params: { ...P(pid), query: q } })),
    enabled: on(pid, o),
    retry: false,
    ...list,
  });
}

export function useJourneyPlan(id: string, o: Opt = {}) {
  return useQuery({ queryKey: svk.journey(id), queryFn: () => unwrap(api.GET("/api/v1/journey-plans/{plan_id}", { params: { path: { plan_id: id } } })), enabled: on(id, o), retry: false });
}

/** K-138…K-140 for the dashboard tiles and the KPI card (values exactly as the server returns them). */
export function useSiteVehicleKpis(q: QueryOf<"get_site_vehicle_kpis">, o: Opt = {}) {
  return useQuery({
    queryKey: svk.kpis(q),
    queryFn: () => unwrap(api.GET("/api/v1/kpi/site-vehicles", { params: { query: q } })),
    enabled: o.enabled ?? true,
    staleTime: 60_000,
    retry: false,
    ...list,
  });
}
