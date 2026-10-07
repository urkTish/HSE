"use client";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "./client";
import type { QueryOf } from "./queries";

type Opt = { enabled?: boolean };

/** Query keys for Phase 2 (access permits). Writes invalidate by the first element. */
export const ak = {
  workers: (q: object) => ["workers", q] as const,
  worker: (id: string) => ["worker", id] as const,
  deployments: (pid: string, q: object) => ["deployments", pid, q] as const,
  deployment: (id: string) => ["deployment", id] as const,
  accessCard: (id: string) => ["access-card", id] as const,
  eligibility: (wid: string, zid: string, at: string | null) => ["eligibility", wid, zid, at] as const,
  hookProviders: (pid: string) => ["hook-providers", pid] as const,
  courses: (pid: string) => ["induction-courses", pid] as const,
  course: (id: string) => ["induction-course", id] as const,
  inductions: (pid: string, q: object) => ["inductions", pid, q] as const,
  induction: (id: string) => ["induction", id] as const,
  zoneProfiles: (pid: string) => ["zone-access-profiles", pid] as const,
  zoneProfile: (zid: string) => ["zone-access-profile", zid] as const,
  passCategories: (pid: string) => ["pass-categories", pid] as const,
  passAreas: (pid: string) => ["pass-areas", pid] as const,
  applications: (pid: string, q: object) => ["pass-applications", pid, q] as const,
  application: (id: string) => ["pass-application", id] as const,
  passes: (pid: string, q: object) => ["airport-passes", pid, q] as const,
  pass: (id: string) => ["airport-pass", id] as const,
  adps: (pid: string, q: object) => ["adps", pid, q] as const,
  adp: (id: string) => ["adp", id] as const,
  offences: (pid: string, q: object) => ["offences", pid, q] as const,
  offence: (id: string) => ["offence", id] as const,
  vehicles: (pid: string, q: object) => ["vehicles", pid, q] as const,
  vehicle: (id: string) => ["vehicle", id] as const,
  avps: (pid: string, q: object) => ["avps", pid, q] as const,
  avp: (id: string) => ["avp", id] as const,
  sticker: (id: string) => ["avp-sticker", id] as const,
  notams: (pid: string, q: object) => ["notams", pid, q] as const,
  notam: (id: string) => ["notam", id] as const,
  obstacles: (pid: string, q: object) => ["obstacles", pid, q] as const,
  obstacle: (id: string) => ["obstacle", id] as const,
  waps: (pid: string, q: object) => ["waps", pid, q] as const,
  wap: (id: string) => ["wap", id] as const,
  wapBoard: (pid: string, q: object) => ["wap-board", pid, q] as const,
  wapPrint: (id: string) => ["wap-print", id] as const,
  opsEvents: (pid: string, q: object) => ["ops-events", pid, q] as const,
  opsEvent: (id: string) => ["ops-event", id] as const,
  credential: (kind: string, id: string) => ["credential", kind, id] as const,
  credentialEvents: (kind: string, id: string, page: number) => ["credential-events", kind, id, page] as const,
  gates: (pid: string) => ["gates", pid] as const,
  gate: (id: string) => ["gate", id] as const,
  gateLog: (pid: string, q: object) => ["gate-log", pid, q] as const,
  accessSettings: (pid: string) => ["access-settings", pid] as const,
  accessKpis: (q: object) => ["kpi", "access", q] as const,
};

/** Every Phase 2 list/detail prefix: invalidated together after a lifecycle action. */
export const ACCESS_PREFIXES = [
  "workers",
  "worker",
  "deployments",
  "deployment",
  "inductions",
  "induction",
  "pass-applications",
  "pass-application",
  "airport-passes",
  "airport-pass",
  "adps",
  "adp",
  "avps",
  "avp",
  "vehicles",
  "vehicle",
  "credential",
  "credential-events",
  "access-card",
  "waps",
  "wap",
  "wap-board",
  "eligibility",
];

const list = { placeholderData: keepPreviousData };

export function useWorkers(q: QueryOf<"list_workers">, o: Opt = {}) {
  return useQuery({ queryKey: ak.workers(q), queryFn: () => unwrap(api.GET("/api/v1/workers", { params: { query: q } })), enabled: o.enabled ?? true, ...list });
}

export function useWorker(id: string) {
  return useQuery({ queryKey: ak.worker(id), queryFn: () => unwrap(api.GET("/api/v1/workers/{worker_id}", { params: { path: { worker_id: id } } })), enabled: Boolean(id) });
}

export function useDeployments(pid: string, q: QueryOf<"list_deployments">, o: Opt = {}) {
  return useQuery({
    queryKey: ak.deployments(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/deployments", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    ...list,
  });
}

export function useDeployment(id: string) {
  return useQuery({ queryKey: ak.deployment(id), queryFn: () => unwrap(api.GET("/api/v1/deployments/{deployment_id}", { params: { path: { deployment_id: id } } })), enabled: Boolean(id) });
}

export function useAccessCard(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: ak.accessCard(id),
    queryFn: () => unwrap(api.GET("/api/v1/deployments/{deployment_id}/access-card", { params: { path: { deployment_id: id } } })),
    enabled: Boolean(id) && (o.enabled ?? true),
    retry: false,
  });
}

export function useEligibility(wid: string, zid: string, at: string | null, context: Schemas["EligibilityContext"] = "check") {
  return useQuery({
    queryKey: [...ak.eligibility(wid, zid, at), context],
    queryFn: () => unwrap(api.GET("/api/v1/workers/{worker_id}/eligibility", { params: { path: { worker_id: wid }, query: { zone_id: zid, at, context } } })),
    enabled: Boolean(wid && zid),
    retry: false,
  });
}

export function useHookProviders(pid: string | null | undefined) {
  return useQuery({
    queryKey: ak.hookProviders(pid ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/hook-providers", { params: { query: { project_id: pid ?? "" } } })),
    enabled: Boolean(pid),
    staleTime: 5 * 60_000,
  });
}

export function useInductionCourses(pid: string, o: Opt = {}) {
  return useQuery({
    queryKey: ak.courses(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/induction-courses", { params: { path: { project_id: pid } } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    staleTime: 60_000,
  });
}

export function useInductionCourse(id: string) {
  return useQuery({ queryKey: ak.course(id), queryFn: () => unwrap(api.GET("/api/v1/induction-courses/{course_id}", { params: { path: { course_id: id } } })), enabled: Boolean(id) });
}

export function useInductions(pid: string, q: QueryOf<"list_inductions">, o: Opt = {}) {
  return useQuery({
    queryKey: ak.inductions(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/inductions", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    ...list,
  });
}

export function useInduction(id: string) {
  return useQuery({ queryKey: ak.induction(id), queryFn: () => unwrap(api.GET("/api/v1/inductions/{induction_id}", { params: { path: { induction_id: id } } })), enabled: Boolean(id) });
}

export function useZoneProfiles(pid: string, siteId?: string | null) {
  return useQuery({
    queryKey: [...ak.zoneProfiles(pid), siteId ?? null],
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/zone-access-profiles", { params: { path: { project_id: pid }, query: { site_id: siteId ?? null } } })),
    enabled: Boolean(pid),
  });
}

export function useZoneProfile(zid: string, o: Opt = {}) {
  return useQuery({
    queryKey: ak.zoneProfile(zid),
    queryFn: () => unwrap(api.GET("/api/v1/zones/{zone_id}/access-profile", { params: { path: { zone_id: zid } } })),
    enabled: Boolean(zid) && (o.enabled ?? true),
    retry: false,
  });
}

export function usePassCategories(pid: string, o: Opt = {}) {
  return useQuery({
    queryKey: ak.passCategories(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/airport-pass-categories", { params: { path: { project_id: pid } } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    staleTime: 60_000,
  });
}

export function usePassAreas(pid: string, o: Opt = {}) {
  return useQuery({
    queryKey: ak.passAreas(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/airport-pass-areas", { params: { path: { project_id: pid } } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    staleTime: 60_000,
  });
}

export function usePassApplications(pid: string, q: QueryOf<"list_pass_applications">) {
  return useQuery({
    queryKey: ak.applications(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/pass-applications", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid),
    ...list,
  });
}

export function usePassApplication(id: string) {
  return useQuery({
    queryKey: ak.application(id),
    queryFn: () => unwrap(api.GET("/api/v1/pass-applications/{application_id}", { params: { path: { application_id: id } } })),
    enabled: Boolean(id),
  });
}

export function useAirportPasses(pid: string, q: QueryOf<"list_airport_passes">, o: Opt = {}) {
  return useQuery({
    queryKey: ak.passes(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/airport-passes", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    ...list,
  });
}

export function useAirportPass(id: string) {
  return useQuery({ queryKey: ak.pass(id), queryFn: () => unwrap(api.GET("/api/v1/airport-passes/{pass_id}", { params: { path: { pass_id: id } } })), enabled: Boolean(id) });
}

export function useAdps(pid: string, q: QueryOf<"list_adps">, o: Opt = {}) {
  return useQuery({
    queryKey: ak.adps(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/adps", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    ...list,
  });
}

export function useAdp(id: string, pointsAsOf?: string | null) {
  return useQuery({
    queryKey: [...ak.adp(id), pointsAsOf ?? null],
    queryFn: () => unwrap(api.GET("/api/v1/adps/{adp_id}", { params: { path: { adp_id: id }, query: { points_as_of: pointsAsOf ?? null } } })),
    enabled: Boolean(id),
    placeholderData: keepPreviousData,
  });
}

export function useOffences(pid: string, q: QueryOf<"list_offences">, o: Opt = {}) {
  return useQuery({
    queryKey: ak.offences(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/airside-offences", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    ...list,
  });
}

export function useOffence(id: string) {
  return useQuery({ queryKey: ak.offence(id), queryFn: () => unwrap(api.GET("/api/v1/airside-offences/{offence_id}", { params: { path: { offence_id: id } } })), enabled: Boolean(id) });
}

export function useVehicles(pid: string, q: QueryOf<"list_vehicles">, o: Opt = {}) {
  return useQuery({
    queryKey: ak.vehicles(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/vehicles", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    ...list,
  });
}

export function useVehicle(id: string) {
  return useQuery({ queryKey: ak.vehicle(id), queryFn: () => unwrap(api.GET("/api/v1/vehicles/{vehicle_id}", { params: { path: { vehicle_id: id } } })), enabled: Boolean(id) });
}

export function useAvps(pid: string, q: QueryOf<"list_avps">, o: Opt = {}) {
  return useQuery({
    queryKey: ak.avps(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/avps", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    ...list,
  });
}

export function useAvp(id: string) {
  return useQuery({ queryKey: ak.avp(id), queryFn: () => unwrap(api.GET("/api/v1/avps/{avp_id}", { params: { path: { avp_id: id } } })), enabled: Boolean(id) });
}

export function useAvpSticker(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: ak.sticker(id),
    queryFn: () => unwrap(api.GET("/api/v1/avps/{avp_id}/sticker", { params: { path: { avp_id: id } } })),
    enabled: Boolean(id) && (o.enabled ?? true),
    retry: false,
  });
}

export function useNotams(pid: string, q: QueryOf<"list_notam_requests">, o: Opt = {}) {
  return useQuery({
    queryKey: ak.notams(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/notam-requests", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    ...list,
  });
}

export function useNotam(id: string) {
  return useQuery({ queryKey: ak.notam(id), queryFn: () => unwrap(api.GET("/api/v1/notam-requests/{ntm_id}", { params: { path: { ntm_id: id } } })), enabled: Boolean(id) });
}

export function useObstacles(pid: string, q: QueryOf<"list_obstacle_clearances">, o: Opt = {}) {
  return useQuery({
    queryKey: ak.obstacles(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/obstacle-clearances", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    ...list,
  });
}

export function useObstacle(id: string) {
  return useQuery({ queryKey: ak.obstacle(id), queryFn: () => unwrap(api.GET("/api/v1/obstacle-clearances/{obs_id}", { params: { path: { obs_id: id } } })), enabled: Boolean(id) });
}

export function useWaps(pid: string, q: QueryOf<"list_waps">, o: Opt = {}) {
  return useQuery({
    queryKey: ak.waps(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/waps", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    ...list,
  });
}

export function useWap(id: string) {
  return useQuery({ queryKey: ak.wap(id), queryFn: () => unwrap(api.GET("/api/v1/waps/{wap_id}", { params: { path: { wap_id: id } } })), enabled: Boolean(id) });
}

export function useWapBoard(pid: string, q: QueryOf<"get_wap_board">) {
  return useQuery({
    queryKey: ak.wapBoard(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/wap-board", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid),
    refetchInterval: 60_000,
    ...list,
  });
}

export function useWapPrint(id: string) {
  return useQuery({ queryKey: ak.wapPrint(id), queryFn: () => unwrap(api.GET("/api/v1/waps/{wap_id}/print", { params: { path: { wap_id: id } } })), enabled: Boolean(id), retry: false });
}

export function useOpsEvents(pid: string, q: QueryOf<"list_ops_events">, o: Opt = {}) {
  return useQuery({
    queryKey: ak.opsEvents(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/ops-events", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    ...list,
  });
}

export function useOpsEvent(id: string) {
  return useQuery({ queryKey: ak.opsEvent(id), queryFn: () => unwrap(api.GET("/api/v1/ops-events/{event_id}", { params: { path: { event_id: id } } })), enabled: Boolean(id) });
}

export function useCredential(kind: Schemas["CredentialKind"], id: string, o: Opt = {}) {
  return useQuery({
    queryKey: ak.credential(kind, id),
    queryFn: () => unwrap(api.GET("/api/v1/credentials/{kind}/{credential_id}", { params: { path: { kind, credential_id: id } } })),
    enabled: Boolean(id) && (o.enabled ?? true),
  });
}

export function useGates(pid: string, o: Opt = {}) {
  return useQuery({
    queryKey: ak.gates(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/gates", { params: { path: { project_id: pid } } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
  });
}

export function useGate(id: string) {
  return useQuery({ queryKey: ak.gate(id), queryFn: () => unwrap(api.GET("/api/v1/gates/{gate_id}", { params: { path: { gate_id: id } } })), enabled: Boolean(id) });
}

export function useGateLog(pid: string, q: QueryOf<"list_gate_log">) {
  return useQuery({
    queryKey: ak.gateLog(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/gate-log", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid),
    ...list,
  });
}

export function useAccessSettings(pid: string | null | undefined, o: Opt = {}) {
  return useQuery({
    queryKey: ak.accessSettings(pid ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/access-settings", { params: { path: { project_id: pid ?? "" } } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    staleTime: 60_000,
  });
}

export function useAccessKpis(q: QueryOf<"get_access_kpis">, o: Opt = {}) {
  return useQuery({
    queryKey: ak.accessKpis(q),
    queryFn: () => unwrap(api.GET("/api/v1/kpi/access", { params: { query: q } })),
    enabled: o.enabled ?? true,
    staleTime: 60_000,
    retry: false,
    ...list,
  });
}
