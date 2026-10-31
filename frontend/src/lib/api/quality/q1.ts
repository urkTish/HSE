"use client";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../client";
import type { QueryOf } from "../queries";

/** Query hooks of Quality package Q1: ITPs, inspection requests, punch lists, floor plans and handover dossiers
 * (spec 8-quality Part B). Keys start with `q-` so `useQualityRefresh` refreshes them after every write. */
type Opt = { enabled?: boolean };
const on = (id: string, o: Opt = {}) => Boolean(id) && (o.enabled ?? true);
const P = (pid: string) => ({ path: { project_id: pid } });
const list = { placeholderData: keepPreviousData };

export const q1k = {
  itps: (pid: string, q: object) => ["q-itps", pid, q] as const,
  itp: (id: string) => ["q-itp", id] as const,
  coverage: (id: string) => ["q-itp-coverage", id] as const,
  irs: (pid: string, q: object) => ["q-irs", pid, q] as const,
  ir: (id: string) => ["q-ir", id] as const,
  locations: (pid: string, q: object) => ["q-ir-locations", pid, q] as const,
  punch: (pid: string, q: object) => ["q-punch", pid, q] as const,
  punchItem: (id: string) => ["q-punch-item", id] as const,
  plans: (pid: string, q: object) => ["q-plans", pid, q] as const,
  plan: (id: string) => ["q-plan", id] as const,
  dossiers: (pid: string, q: object) => ["q-dossiers", pid, q] as const,
  dossier: (id: string) => ["q-dossier", id] as const,
  templates: (type: string) => ["q-templates", type] as const,
};

export function useQItps(pid: string, q: QueryOf<"q1_list_itps"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: q1k.itps(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/itps", { params: { ...P(pid), query: q } })),
    enabled: on(pid, o),
    retry: false,
    ...list,
  });
}

export function useQItp(id: string) {
  return useQuery({ queryKey: q1k.itp(id), queryFn: () => unwrap(api.GET("/api/v1/quality/itps/{itp_id}", { params: { path: { itp_id: id } } })), enabled: on(id), retry: false });
}

export function useQItpCoverage(id: string) {
  return useQuery({ queryKey: q1k.coverage(id), queryFn: () => unwrap(api.GET("/api/v1/quality/itps/{itp_id}/coverage", { params: { path: { itp_id: id } } })), enabled: on(id), retry: false });
}

export function useQIrs(pid: string, q: QueryOf<"q1_list_irs"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: q1k.irs(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/inspection-requests", { params: { ...P(pid), query: q } })),
    enabled: on(pid, o),
    retry: false,
    ...list,
  });
}

export function useQIr(id: string) {
  return useQuery({
    queryKey: q1k.ir(id),
    queryFn: () => unwrap(api.GET("/api/v1/quality/inspection-requests/{ir_id}", { params: { path: { ir_id: id } } })),
    enabled: on(id),
    retry: false,
  });
}

export function useQIrLocations(pid: string, q: QueryOf<"q1_ir_locations"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: q1k.locations(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/inspection-requests/locations", { params: { ...P(pid), query: q } })),
    enabled: on(pid, o),
    staleTime: 60_000,
  });
}

export function useQPunch(pid: string, q: QueryOf<"q1_list_punch"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: q1k.punch(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/punch", { params: { ...P(pid), query: q } })),
    enabled: on(pid, o),
    retry: false,
    ...list,
  });
}

export function useQPunchItem(id: string) {
  return useQuery({ queryKey: q1k.punchItem(id), queryFn: () => unwrap(api.GET("/api/v1/quality/punch/{item_id}", { params: { path: { item_id: id } } })), enabled: on(id), retry: false });
}

export function useQPlans(pid: string, q: QueryOf<"q1_list_plans"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: q1k.plans(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/floor-plans", { params: { ...P(pid), query: q } })),
    enabled: on(pid, o),
    retry: false,
  });
}

export function useQPlan(id: string) {
  return useQuery({ queryKey: q1k.plan(id), queryFn: () => unwrap(api.GET("/api/v1/quality/floor-plans/{plan_id}", { params: { path: { plan_id: id } } })), enabled: on(id), retry: false });
}

export function useQDossiers(pid: string, q: QueryOf<"q1_list_dossiers"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: q1k.dossiers(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/dossiers", { params: { ...P(pid), query: q } })),
    enabled: on(pid, o),
    retry: false,
    ...list,
  });
}

export function useQDossier(id: string) {
  return useQuery({ queryKey: q1k.dossier(id), queryFn: () => unwrap(api.GET("/api/v1/quality/dossiers/{dossier_id}", { params: { path: { dossier_id: id } } })), enabled: on(id), retry: false });
}

/** Published quality checklists of one type (point template picker, walkdown). */
export function useQTemplates(qualityType: string) {
  return useQuery({
    queryKey: q1k.templates(qualityType),
    queryFn: () => unwrap(api.GET("/api/v1/checklist-templates", { params: { query: { kind: "quality", status: ["published"], page_size: 200 } } })),
    select: (d) => d.items.filter((t) => t.quality_type === qualityType),
    staleTime: 5 * 60_000,
  });
}

export function useQCriteriaPublished() {
  return useQuery({
    queryKey: ["q-criteria-published"],
    queryFn: () => unwrap(api.GET("/api/v1/quality/criteria", { params: { query: { status: ["published"], page_size: 200 } } })),
    staleTime: 5 * 60_000,
  });
}
