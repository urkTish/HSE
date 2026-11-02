"use client";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../client";
import type { QueryOf } from "../queries";

/** Query hooks of Quality package Q4 (spec 8-quality Part E): documents, transmittals, audits,
 * programme, management reviews, suppliers, KPIs, SPC and Quality report packs. Keys start with `q-`
 * so the Q0 `useQualityRefresh()` refreshes them after every write. */
type Opt = { enabled?: boolean };
const on = (id: string, o: Opt = {}) => Boolean(id) && (o.enabled ?? true);
const P = (pid: string) => ({ project_id: pid });
const list = { placeholderData: keepPreviousData, retry: false } as const;

export const q4k = {
  docs: (pid: string, q: object) => ["q-q4-docs", pid, q] as const,
  doc: (id: string) => ["q-q4-doc", id] as const,
  acks: (pid: string) => ["q-q4-acks", pid] as const,
  trms: (pid: string) => ["q-q4-trms", pid] as const,
  trm: (id: string) => ["q-q4-trm", id] as const,
  processes: (pid: string) => ["q-q4-processes", pid] as const,
  programme: (pid: string, y: number) => ["q-q4-programme", pid, y] as const,
  audits: (pid: string) => ["q-q4-audits", pid] as const,
  audit: (id: string) => ["q-q4-audit", id] as const,
  mrvs: (pid: string) => ["q-q4-mrvs", pid] as const,
  mrv: (id: string) => ["q-q4-mrv", id] as const,
  sevs: (pid: string, s?: string) => ["q-q4-sevs", pid, s ?? ""] as const,
  scores: (pid: string, s?: string) => ["q-q4-scores", pid, s ?? ""] as const,
  kpis: (pid: string, q: object) => ["q-q4-kpis", pid, q] as const,
  targets: (pid: string) => ["q-q4-targets", pid] as const,
  spcs: (pid: string) => ["q-q4-spcs", pid] as const,
  packs: (pid: string) => ["q-q4-packs", pid] as const,
  template: (code: string) => ["q-q4-template", code] as const,
};

export function useQ4Documents(pid: string, q: QueryOf<"q4_list_documents"> = {}) {
  return useQuery({ queryKey: q4k.docs(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/documents", { params: { path: P(pid), query: q } })), enabled: on(pid), ...list });
}
export function useQ4Document(id: string) {
  return useQuery({ queryKey: q4k.doc(id), queryFn: () => unwrap(api.GET("/api/v1/quality/documents/{doc_id}", { params: { path: { doc_id: id } } })), enabled: on(id), retry: false });
}
export function useQ4MyAcks(pid: string) {
  return useQuery({ queryKey: q4k.acks(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/my-acknowledgements", { params: { path: P(pid), query: { pending: true } } })), enabled: on(pid), ...list });
}
export function useQ4Transmittals(pid: string) {
  return useQuery({ queryKey: q4k.trms(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/transmittals", { params: { path: P(pid), query: { page_size: 100 } } })), enabled: on(pid), ...list });
}
export function useQ4Transmittal(id: string) {
  return useQuery({ queryKey: q4k.trm(id), queryFn: () => unwrap(api.GET("/api/v1/quality/transmittals/{tid}", { params: { path: { tid: id } } })), enabled: on(id), retry: false });
}
export function useQ4Processes(pid: string) {
  return useQuery({ queryKey: q4k.processes(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/processes", { params: { path: P(pid) } })), enabled: on(pid), ...list });
}
export function useQ4Programme(pid: string, year: number) {
  return useQuery({ queryKey: q4k.programme(pid, year), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/audit-programme", { params: { path: P(pid), query: { year } } })), enabled: on(pid), ...list });
}
export function useQ4Audits(pid: string) {
  return useQuery({ queryKey: q4k.audits(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/audits", { params: { path: P(pid), query: { page_size: 100 } } })), enabled: on(pid), ...list });
}
export function useQ4Audit(id: string) {
  return useQuery({ queryKey: q4k.audit(id), queryFn: () => unwrap(api.GET("/api/v1/quality/audits/{audit_id}", { params: { path: { audit_id: id } } })), enabled: on(id), retry: false });
}
export function useQ4Mrvs(pid: string) {
  return useQuery({ queryKey: q4k.mrvs(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/management-reviews", { params: { path: P(pid) } })), enabled: on(pid), ...list });
}
export function useQ4Mrv(id: string) {
  return useQuery({ queryKey: q4k.mrv(id), queryFn: () => unwrap(api.GET("/api/v1/quality/management-reviews/{mid}", { params: { path: { mid: id } } })), enabled: on(id), retry: false });
}
export function useQ4Evaluations(pid: string, supplierId?: string, o: Opt = {}) {
  return useQuery({ queryKey: q4k.sevs(pid, supplierId), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/supplier-evaluations", { params: { path: P(pid), query: supplierId ? { supplier_id: supplierId } : {} } })), enabled: on(pid, o), ...list });
}
export function useQ4Scores(pid: string, supplierId?: string, o: Opt = {}) {
  return useQuery({ queryKey: q4k.scores(pid, supplierId), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/supplier-scores", { params: { path: P(pid), query: supplierId ? { supplier_id: supplierId } : {} } })), enabled: on(pid, o), ...list });
}
export function useQ4Kpis(pid: string, q: QueryOf<"q4_kpis"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: q4k.kpis(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/kpis", { params: { path: P(pid), query: q } })), enabled: on(pid, o), retry: false, staleTime: 60_000 });
}
export function useQ4Targets(pid: string) {
  return useQuery({ queryKey: q4k.targets(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/kpi-targets", { params: { path: P(pid) } })), enabled: on(pid), ...list });
}
export function useQ4SpcCharts(pid: string) {
  return useQuery({ queryKey: q4k.spcs(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/spc-charts", { params: { path: P(pid) } })), enabled: on(pid), ...list });
}
export function useQ4Packs(pid: string) {
  return useQuery({ queryKey: q4k.packs(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/report-packs", { params: { path: P(pid), query: { page_size: 100 } } })), enabled: on(pid), ...list });
}
