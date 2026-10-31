"use client";
import { useCallback } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "../client";
import type { QueryOf } from "../queries";

/** Query hooks of Quality package Q0 (spec 8-quality Part A). Writes invalidate every `q-` key. */
type Opt = { enabled?: boolean };
const on = (id: string, o: Opt = {}) => Boolean(id) && (o.enabled ?? true);
const P = (pid: string) => ({ path: { project_id: pid } });
const list = { placeholderData: keepPreviousData };

export const qk = {
  reference: () => ["q-reference"] as const,
  schema: () => ["q-settings-schema"] as const,
  settings: (pid: string) => ["q-settings", pid] as const,
  home: (pid: string) => ["q-home", pid] as const,
  awaiting: (pid: string) => ["q-awaiting", pid] as const,
  positions: (pid: string) => ["q-positions", pid] as const,
  rules: (pid: string) => ["q-rules", pid] as const,
  numbering: (pid: string) => ["q-numbering", pid] as const,
  ncrs: (pid: string, q: object) => ["q-ncrs", pid, q] as const,
  ncr: (id: string) => ["q-ncr", id] as const,
  observations: (pid: string, q: object) => ["q-observations", pid, q] as const,
  observation: (id: string) => ["q-observation", id] as const,
  alerts: (pid: string, q: object) => ["q-alerts", pid, q] as const,
  alert: (id: string) => ["q-alert", id] as const,
  complaints: (pid: string, q: object) => ["q-complaints", pid, q] as const,
  complaint: (id: string) => ["q-complaint", id] as const,
  suppliers: (q: object) => ["q-suppliers", q] as const,
  supplier: (id: string) => ["q-supplier", id] as const,
  customers: (pid: string) => ["q-customers", pid] as const,
  systems: (pid: string) => ["q-systems", pid] as const,
  criteria: (q: object) => ["q-criteria", q] as const,
  criterion: (id: string) => ["q-criterion", id] as const,
  mte: (pid: string, q: object) => ["q-mte", pid, q] as const,
  mteItem: (id: string) => ["q-mte-item", id] as const,
  mteUsage: (id: string) => ["q-mte-usage", id] as const,
};

/** After a Quality write: refresh every Quality query, plus CAs and notifications shown elsewhere. */
export function useQualityRefresh() {
  const qc = useQueryClient();
  return useCallback(async () => {
    await qc.invalidateQueries({ predicate: (q) => typeof q.queryKey[0] === "string" && (q.queryKey[0] as string).startsWith("q-") });
    await qc.invalidateQueries({ queryKey: ["corrective-actions"] });
    await qc.invalidateQueries({ queryKey: ["notifications"] });
  }, [qc]);
}

export function useQReference() {
  return useQuery({ queryKey: qk.reference(), queryFn: () => unwrap(api.GET("/api/v1/quality/reference")), staleTime: 10 * 60_000 });
}

export function useQSettingsSchema() {
  return useQuery({ queryKey: qk.schema(), queryFn: () => unwrap(api.GET("/api/v1/quality/settings/schema")), staleTime: 10 * 60_000 });
}

export function useQSettings(pid: string, o: Opt = {}) {
  return useQuery({
    queryKey: qk.settings(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/settings", { params: P(pid) })),
    enabled: on(pid, o),
    staleTime: 60_000,
    retry: false,
  });
}

export function useQHome(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: qk.home(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/home", { params: P(pid) })), enabled: on(pid, o), retry: false });
}

export function useQAwaiting(pid: string, o: Opt = {}) {
  return useQuery({
    queryKey: qk.awaiting(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/awaiting", { params: P(pid) })),
    enabled: on(pid, o),
    retry: false,
    staleTime: 30_000,
  });
}

export function useQPositions(pid: string) {
  return useQuery({ queryKey: qk.positions(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/positions", { params: P(pid) })), enabled: on(pid) });
}

export function useQRules(pid: string) {
  return useQuery({ queryKey: qk.rules(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/rp-rules", { params: P(pid) })), enabled: on(pid) });
}

export function useQNumbering(pid: string) {
  return useQuery({ queryKey: qk.numbering(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/numbering", { params: P(pid) })), enabled: on(pid) });
}

export function useQNcrs(pid: string, q: QueryOf<"q_list_ncrs"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: qk.ncrs(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/ncrs", { params: { ...P(pid), query: q } })),
    enabled: on(pid, o),
    retry: false,
    ...list,
  });
}

export function useQNcr(id: string) {
  return useQuery({ queryKey: qk.ncr(id), queryFn: () => unwrap(api.GET("/api/v1/quality/ncrs/{ncr_id}", { params: { path: { ncr_id: id } } })), enabled: on(id), retry: false });
}

export function useQObservations(pid: string, q: QueryOf<"q_list_observations"> = {}) {
  return useQuery({
    queryKey: qk.observations(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/observations", { params: { ...P(pid), query: q } })),
    enabled: on(pid),
    retry: false,
    ...list,
  });
}

export function useQObservation(id: string) {
  return useQuery({ queryKey: qk.observation(id), queryFn: () => unwrap(api.GET("/api/v1/quality/observations/{obs_id}", { params: { path: { obs_id: id } } })), enabled: on(id), retry: false });
}

export function useQAlerts(pid: string, q: QueryOf<"q_list_alerts"> = {}) {
  return useQuery({
    queryKey: qk.alerts(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/alerts", { params: { ...P(pid), query: q } })),
    enabled: on(pid),
    retry: false,
    ...list,
  });
}

export function useQAlert(id: string) {
  return useQuery({ queryKey: qk.alert(id), queryFn: () => unwrap(api.GET("/api/v1/quality/alerts/{alert_id}", { params: { path: { alert_id: id } } })), enabled: on(id), retry: false });
}

export function useQComplaints(pid: string, q: QueryOf<"q_list_complaints"> = {}) {
  return useQuery({
    queryKey: qk.complaints(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/complaints", { params: { ...P(pid), query: q } })),
    enabled: on(pid),
    retry: false,
    ...list,
  });
}

export function useQComplaint(id: string) {
  return useQuery({
    queryKey: qk.complaint(id),
    queryFn: () => unwrap(api.GET("/api/v1/quality/complaints/{complaint_id}", { params: { path: { complaint_id: id } } })),
    enabled: on(id),
    retry: false,
  });
}

export function useQSuppliers(q: QueryOf<"q_list_suppliers"> = {}) {
  return useQuery({ queryKey: qk.suppliers(q), queryFn: () => unwrap(api.GET("/api/v1/quality/suppliers", { params: { query: q } })), retry: false, ...list });
}

export function useQSupplier(id: string) {
  return useQuery({
    queryKey: qk.supplier(id),
    queryFn: () => unwrap(api.GET("/api/v1/quality/suppliers/{supplier_id}", { params: { path: { supplier_id: id } } })),
    enabled: on(id),
    retry: false,
  });
}

export function useQCustomers(pid: string) {
  return useQuery({ queryKey: qk.customers(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/customers", { params: P(pid) })), enabled: on(pid), retry: false });
}

export function useQSystems(pid: string) {
  return useQuery({ queryKey: qk.systems(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/systems", { params: P(pid) })), enabled: on(pid), retry: false });
}

export function useQCriteria(q: QueryOf<"q_list_criteria"> = {}) {
  return useQuery({ queryKey: qk.criteria(q), queryFn: () => unwrap(api.GET("/api/v1/quality/criteria", { params: { query: q } })), retry: false, ...list });
}

export function useQCriterion(id: string) {
  return useQuery({
    queryKey: qk.criterion(id),
    queryFn: () => unwrap(api.GET("/api/v1/quality/criteria/{criterion_id}", { params: { path: { criterion_id: id } } })),
    enabled: on(id),
    retry: false,
  });
}

export function useQMte(pid: string, q: QueryOf<"q_list_mte"> = {}) {
  return useQuery({
    queryKey: qk.mte(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/mte", { params: { ...P(pid), query: q } })),
    enabled: on(pid),
    retry: false,
    ...list,
  });
}

export function useQMteItem(id: string) {
  return useQuery({ queryKey: qk.mteItem(id), queryFn: () => unwrap(api.GET("/api/v1/quality/mte/{mte_id}", { params: { path: { mte_id: id } } })), enabled: on(id), retry: false });
}

export function useQMteUsage(id: string) {
  return useQuery({ queryKey: qk.mteUsage(id), queryFn: () => unwrap(api.GET("/api/v1/quality/mte/{mte_id}/usage", { params: { path: { mte_id: id } } })), enabled: on(id), retry: false });
}
