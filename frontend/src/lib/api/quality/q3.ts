"use client";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, toApiError, unwrap, type Schemas } from "../client";
import type { QueryOf } from "../queries";

/** Query hooks of Quality package Q3 logistics (spec 8-quality Part D). Keys start with `q-` so the
 * Q0 `useQualityRefresh()` refreshes them after every write. */
type Opt = { enabled?: boolean };
const on = (id: string, o: Opt = {}) => Boolean(id) && (o.enabled ?? true);
const P = (pid: string) => ({ path: { project_id: pid } });
const list = { placeholderData: keepPreviousData, retry: false } as const;

export const q3k = {
  products: (pid: string, q: object) => ["q-q3-products", pid, q] as const,
  imports: (pid: string, q: object) => ["q-q3-imports", pid, q] as const,
  zones: (pid: string) => ["q-q3-zones", pid] as const,
  zone: (id: string) => ["q-q3-zone", id] as const,
  zoneReport: (id: string, a: string, b: string) => ["q-q3-zone-report", id, a, b] as const,
  excursions: (pid: string, q: object) => ["q-q3-excursions", pid, q] as const,
  excursion: (id: string) => ["q-q3-excursion", id] as const,
  studies: (pid: string) => ["q-q3-studies", pid] as const,
  study: (id: string) => ["q-q3-study", id] as const,
  schedules: (pid: string) => ["q-q3-schedules", pid] as const,
  stations: (pid: string) => ["q-q3-stations", pid] as const,
  visits: (pid: string) => ["q-q3-visits", pid] as const,
  visit: (id: string) => ["q-q3-visit", id] as const,
  receipts: (pid: string, q: object) => ["q-q3-receipts", pid, q] as const,
  receipt: (id: string) => ["q-q3-receipt", id] as const,
  holds: (pid: string, q: object) => ["q-q3-holds", pid, q] as const,
  hold: (id: string) => ["q-q3-hold", id] as const,
  nearExpiry: (pid: string) => ["q-q3-near-expiry", pid] as const,
  fefo: (pid: string, q: object) => ["q-q3-fefo", pid, q] as const,
  damage: (pid: string, q: object) => ["q-q3-damage", pid, q] as const,
  counts: (pid: string) => ["q-q3-counts", pid] as const,
  throughput: (pid: string) => ["q-q3-throughput", pid] as const,
  snapshots: (pid: string) => ["q-q3-snapshots", pid] as const,
  returns: (pid: string, q: object) => ["q-q3-returns", pid, q] as const,
  ret: (id: string) => ["q-q3-return", id] as const,
  recalls: (pid: string) => ["q-q3-recalls", pid] as const,
  recall: (id: string) => ["q-q3-recall", id] as const,
  trips: (pid: string, q: object) => ["q-q3-trips", pid, q] as const,
  trip: (id: string) => ["q-q3-trip", id] as const,
  shipments: (pid: string, unassigned: boolean) => ["q-q3-shipments", pid, unassigned] as const,
  metrics: (pid: string, y: number, m: number) => ["q-q3-metrics", pid, y, m] as const,
};

export function useQ3Products(pid: string, q: QueryOf<"q3_list_products"> = {}) {
  return useQuery({ queryKey: q3k.products(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/products", { params: { ...P(pid), query: q } })), enabled: on(pid), ...list });
}
export function useQ3Imports(pid: string, q: QueryOf<"q3_list_imports"> = {}) {
  return useQuery({ queryKey: q3k.imports(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/imports", { params: { ...P(pid), query: q } })), enabled: on(pid), ...list });
}
export function useQ3Zones(pid: string) {
  return useQuery({ queryKey: q3k.zones(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/storage-zones", { params: P(pid) })), enabled: on(pid), ...list });
}
export function useQ3Zone(id: string) {
  return useQuery({ queryKey: q3k.zone(id), queryFn: () => unwrap(api.GET("/api/v1/quality/storage-zones/{zone_id}", { params: { path: { zone_id: id } } })), enabled: on(id), retry: false });
}
export function useQ3ZoneReport(id: string, start: string, end: string) {
  return useQuery({
    queryKey: q3k.zoneReport(id, start, end),
    queryFn: () => unwrap(api.GET("/api/v1/quality/storage-zones/{zone_id}/report", { params: { path: { zone_id: id }, query: { start, end } } })),
    enabled: on(id) && Boolean(start && end),
    retry: false,
  });
}
export function useQ3Excursions(pid: string, q: QueryOf<"q3_list_excursions"> = {}) {
  return useQuery({ queryKey: q3k.excursions(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/excursions", { params: { ...P(pid), query: q } })), enabled: on(pid), ...list });
}
export function useQ3Excursion(id: string) {
  return useQuery({ queryKey: q3k.excursion(id), queryFn: () => unwrap(api.GET("/api/v1/quality/excursions/{exc_id}", { params: { path: { exc_id: id } } })), enabled: on(id), retry: false });
}
export function useQ3Studies(pid: string) {
  return useQuery({ queryKey: q3k.studies(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/mapping-studies", { params: P(pid) })), enabled: on(pid), ...list });
}
export function useQ3Study(id: string) {
  return useQuery({ queryKey: q3k.study(id), queryFn: () => unwrap(api.GET("/api/v1/quality/mapping-studies/{study_id}", { params: { path: { study_id: id } } })), enabled: on(id), retry: false });
}
export function useQ3Schedules(pid: string) {
  return useQuery({ queryKey: q3k.schedules(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/check-schedules", { params: P(pid) })), enabled: on(pid), ...list });
}
export function useQ3Stations(pid: string) {
  return useQuery({ queryKey: q3k.stations(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/pest-stations", { params: P(pid) })), enabled: on(pid), ...list });
}
export function useQ3Visits(pid: string) {
  return useQuery({ queryKey: q3k.visits(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/pest-visits", { params: P(pid) })), enabled: on(pid), ...list });
}
export function useQ3Receipts(pid: string, q: QueryOf<"q3_list_receipts"> = {}) {
  return useQuery({ queryKey: q3k.receipts(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/receipts", { params: { ...P(pid), query: q } })), enabled: on(pid), ...list });
}
export function useQ3Receipt(id: string) {
  return useQuery({ queryKey: q3k.receipt(id), queryFn: () => unwrap(api.GET("/api/v1/quality/receipts/{receipt_id}", { params: { path: { receipt_id: id } } })), enabled: on(id), retry: false });
}
export function useQ3Holds(pid: string, q: QueryOf<"q3_list_holds"> = {}) {
  return useQuery({ queryKey: q3k.holds(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/holds", { params: { ...P(pid), query: q } })), enabled: on(pid), ...list });
}
export function useQ3Hold(id: string) {
  return useQuery({ queryKey: q3k.hold(id), queryFn: () => unwrap(api.GET("/api/v1/quality/holds/{hold_id}", { params: { path: { hold_id: id } } })), enabled: on(id), retry: false });
}
export function useQ3NearExpiry(pid: string) {
  return useQuery({ queryKey: q3k.nearExpiry(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/near-expiry", { params: P(pid) })), enabled: on(pid), ...list });
}
export function useQ3Fefo(pid: string, q: QueryOf<"q3_list_fefo"> = {}) {
  return useQuery({ queryKey: q3k.fefo(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/fefo-checks", { params: { ...P(pid), query: q } })), enabled: on(pid), ...list });
}
export function useQ3Damage(pid: string, q: QueryOf<"q3_list_damage"> = {}) {
  return useQuery({ queryKey: q3k.damage(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/damage-reports", { params: { ...P(pid), query: q } })), enabled: on(pid), ...list });
}
export function useQ3Counts(pid: string) {
  return useQuery({ queryKey: q3k.counts(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/cycle-counts", { params: P(pid) })), enabled: on(pid), ...list });
}
export function useQ3Throughput(pid: string) {
  return useQuery({ queryKey: q3k.throughput(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/throughput", { params: P(pid) })), enabled: on(pid), ...list });
}
export function useQ3Snapshots(pid: string) {
  return useQuery({ queryKey: q3k.snapshots(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/stock-snapshots", { params: P(pid) })), enabled: on(pid), ...list });
}
export function useQ3Returns(pid: string, q: QueryOf<"q3_list_returns"> = {}) {
  return useQuery({ queryKey: q3k.returns(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/returns", { params: { ...P(pid), query: q } })), enabled: on(pid), ...list });
}
export function useQ3Return(id: string) {
  return useQuery({ queryKey: q3k.ret(id), queryFn: () => unwrap(api.GET("/api/v1/quality/returns/{return_id}", { params: { path: { return_id: id } } })), enabled: on(id), retry: false });
}
export function useQ3Recalls(pid: string) {
  return useQuery({ queryKey: q3k.recalls(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/recalls", { params: P(pid) })), enabled: on(pid), ...list });
}
export function useQ3Recall(id: string) {
  return useQuery({ queryKey: q3k.recall(id), queryFn: () => unwrap(api.GET("/api/v1/quality/recalls/{recall_id}", { params: { path: { recall_id: id } } })), enabled: on(id), retry: false });
}
export function useQ3Trips(pid: string, q: QueryOf<"q3_list_trips"> = {}) {
  return useQuery({ queryKey: q3k.trips(pid, q), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/trips", { params: { ...P(pid), query: q } })), enabled: on(pid), ...list });
}
export function useQ3Trip(id: string) {
  return useQuery({ queryKey: q3k.trip(id), queryFn: () => unwrap(api.GET("/api/v1/quality/trips/{trip_id}", { params: { path: { trip_id: id } } })), enabled: on(id), retry: false });
}
export function useQ3Shipments(pid: string, unassigned = false) {
  return useQuery({ queryKey: q3k.shipments(pid, unassigned), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/shipments", { params: { ...P(pid), query: { unassigned } } })), enabled: on(pid), ...list });
}
export function useQ3Metrics(pid: string, year: number, month: number, o: Opt = {}) {
  return useQuery({
    queryKey: q3k.metrics(pid, year, month),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/quality/logistics-metrics", { params: { ...P(pid), query: { year, month } } })),
    enabled: on(pid, o),
    retry: false,
    staleTime: 60_000,
  });
}

/** Multipart CSV import (Q-IMP): the file is sent unchanged; the server stores it with its SHA-256. */
export async function postImport(
  pid: string,
  fields: { kind: Schemas["QImportKind"]; target_type: Schemas["QImportTarget"]; target_id: string; profile?: string; as_of?: string },
  file: File,
  preview = false,
): Promise<Schemas["Q3ImportResult"] & Schemas["Q3ImportPreview"]> {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) if (v) fd.append(k, v);
  fd.append("file", file);
  const res = await fetch(`/api/v1/projects/${pid}/quality/imports${preview ? "/preview" : ""}`, { method: "POST", body: fd, credentials: "same-origin" });
  const body = await res.json().catch(() => null);
  if (!res.ok) throw toApiError(res.status, body);
  return body;
}
