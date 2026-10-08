"use client";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "./client";
import type { QueryOf } from "./queries";

type Opt = { enabled?: boolean; refetchInterval?: number | false };

/** Query keys for Phase 3 (permit to work). Writes invalidate by the first element. */
export const pk = {
  permitTypes: (pid: string) => ["permit-types", pid] as const,
  zonePtw: (zid: string) => ["zone-ptw-profile", zid] as const,
  adjacency: (pid: string) => ["zone-adjacency", pid] as const,
  simopsRules: (pid: string) => ["simops-rules", pid] as const,
  riskMatrix: ["risk-matrix"] as const,
  ptwSettings: (pid: string) => ["ptw-settings", pid] as const,
  appointments: (pid: string, q: object) => ["ptw-appointments", pid, q] as const,
  appointment: (id: string) => ["ptw-appointment", id] as const,
  permits: (pid: string, q: object) => ["permits", pid, q] as const,
  permit: (id: string) => ["permit", id] as const,
  readiness: (id: string, action: string) => ["permit-readiness", id, action] as const,
  handovers: (id: string) => ["permit-handovers", id] as const,
  shifts: (id: string) => ["permit-shifts", id] as const,
  suspensions: (id: string) => ["permit-suspensions", id] as const,
  projectSuspensions: (pid: string, q: object) => ["project-permit-suspensions", pid, q] as const,
  print: (id: string) => ["permit-print", id] as const,
  closurePack: (id: string) => ["permit-closure-pack", id] as const,
  board: (pid: string, q: object) => ["ptw-board", pid, q] as const,
  jsaTemplates: (pid: string, q: object) => ["jsa-templates", pid, q] as const,
  jsa: (id: string) => ["jsa", id] as const,
  jsaRevisions: (id: string) => ["jsa-revisions", id] as const,
  detectors: (pid: string, q: object) => ["gas-detectors", pid, q] as const,
  detector: (id: string) => ["gas-detector", id] as const,
  bumpTests: (id: string) => ["bump-tests", id] as const,
  permitGasTests: (id: string) => ["permit-gas-tests", id] as const,
  gasTests: (pid: string, q: object) => ["gas-tests", pid, q] as const,
  gasTest: (id: string) => ["gas-test", id] as const,
  isolations: (pid: string, q: object) => ["isolations", pid, q] as const,
  isolation: (id: string) => ["isolation", id] as const,
  personalLocks: (id: string) => ["personal-locks", id] as const,
  locks: (pid: string, q: object) => ["locks", pid, q] as const,
  conflicts: (pid: string, q: object) => ["simops-conflicts", pid, q] as const,
  conflict: (id: string) => ["simops-conflict", id] as const,
  audits: (pid: string, q: object) => ["ptw-audits", pid, q] as const,
  audit: (id: string) => ["ptw-audit", id] as const,
  auditChecklist: (pid: string, type: string, permitId: string | null) => ["ptw-audit-checklist", pid, type, permitId] as const,
  ptwKpis: (q: object) => ["kpi", "ptw", q] as const,
};

/** Every Phase 3 prefix that a permit-side action can change: invalidated together after a lifecycle action. */
export const PTW_PREFIXES = [
  "permits",
  "permit",
  "permit-readiness",
  "permit-handovers",
  "permit-shifts",
  "permit-suspensions",
  "project-permit-suspensions",
  "permit-print",
  "ptw-board",
  "jsa",
  "permit-gas-tests",
  "gas-tests",
  "gas-test",
  "bump-tests",
  "jsa-revisions",
  "permit-closure-pack",
  "ptw-audits",
  "ptw-audit",
  "gas-detector",
  "gas-detectors",
  "isolations",
  "isolation",
  "personal-locks",
  "locks",
  "simops-conflicts",
  "simops-conflict",
  "ptw-appointments",
  "ptw-appointment",
  "dashboard",
  "kpi",
];

/** Refresh one permit in place and invalidate every PTW list that may show it. */
export function usePtwRefresh() {
  const qc = useQueryClient();
  return async (permit?: Schemas["PermitRead"]) => {
    if (permit) qc.setQueryData(pk.permit(permit.id), permit);
    await Promise.all(PTW_PREFIXES.filter((k) => !(permit && k === "permit")).map((k) => qc.invalidateQueries({ queryKey: [k] })));
  };
}

const list = { placeholderData: keepPreviousData };

/* ── configuration ── */

export function usePermitTypes(pid: string, o: Opt = {}) {
  return useQuery({
    queryKey: pk.permitTypes(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/permit-types", { params: { path: { project_id: pid } } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    staleTime: 60_000,
  });
}

export function useZonePtwProfile(zid: string, o: Opt = {}) {
  return useQuery({
    queryKey: pk.zonePtw(zid),
    queryFn: () => unwrap(api.GET("/api/v1/zones/{zone_id}/ptw-profile", { params: { path: { zone_id: zid } } })),
    enabled: Boolean(zid) && (o.enabled ?? true),
    retry: false,
  });
}

export function useZoneAdjacency(pid: string) {
  return useQuery({
    queryKey: pk.adjacency(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/zone-adjacency", { params: { path: { project_id: pid } } })),
    enabled: Boolean(pid),
  });
}

export function useSimopsRules(pid: string) {
  return useQuery({
    queryKey: pk.simopsRules(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/simops-rules", { params: { path: { project_id: pid } } })),
    enabled: Boolean(pid),
  });
}

export function useRiskMatrix() {
  return useQuery({ queryKey: pk.riskMatrix, queryFn: () => unwrap(api.GET("/api/v1/ptw/risk-matrix")), staleTime: 30 * 60_000 });
}

export function usePtwSettings(pid: string, o: Opt = {}) {
  return useQuery({
    queryKey: pk.ptwSettings(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/ptw-settings", { params: { path: { project_id: pid } } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    staleTime: 60_000,
  });
}

/* ── appointments ── */

export function useAppointments(pid: string, q: QueryOf<"list_ptw_appointments">, o: Opt = {}) {
  return useQuery({
    queryKey: pk.appointments(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/ptw-appointments", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    ...list,
  });
}

export function useAppointment(id: string) {
  return useQuery({
    queryKey: pk.appointment(id),
    queryFn: () => unwrap(api.GET("/api/v1/ptw-appointments/{appointment_id}", { params: { path: { appointment_id: id } } })),
    enabled: Boolean(id),
  });
}

/* ── permits ── */

export function usePermits(pid: string, q: QueryOf<"list_permits">, o: Opt = {}) {
  return useQuery({
    queryKey: pk.permits(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/permits", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    refetchInterval: o.refetchInterval,
    ...list,
  });
}

export function usePermit(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: pk.permit(id),
    queryFn: () => unwrap(api.GET("/api/v1/permits/{permit_id}", { params: { path: { permit_id: id } } })),
    enabled: Boolean(id) && (o.enabled ?? true),
    refetchInterval: o.refetchInterval,
  });
}

export function useReadiness(id: string, action: Schemas["PermitAction"] | null) {
  return useQuery({
    queryKey: pk.readiness(id, action ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/permits/{permit_id}/readiness", { params: { path: { permit_id: id }, query: { action: action as Schemas["PermitAction"] } } })),
    enabled: Boolean(id && action),
    retry: false,
  });
}

export function useHandovers(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: pk.handovers(id),
    queryFn: () => unwrap(api.GET("/api/v1/permits/{permit_id}/handovers", { params: { path: { permit_id: id } } })),
    enabled: Boolean(id) && (o.enabled ?? true),
  });
}

export function useShifts(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: pk.shifts(id),
    queryFn: () => unwrap(api.GET("/api/v1/permits/{permit_id}/shifts", { params: { path: { permit_id: id } } })),
    enabled: Boolean(id) && (o.enabled ?? true),
  });
}

export function useSuspensions(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: pk.suspensions(id),
    queryFn: () => unwrap(api.GET("/api/v1/permits/{permit_id}/suspensions", { params: { path: { permit_id: id } } })),
    enabled: Boolean(id) && (o.enabled ?? true),
  });
}

export function useProjectSuspensions(pid: string, q: QueryOf<"list_project_permit_suspensions">) {
  return useQuery({
    queryKey: pk.projectSuspensions(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/permit-suspensions", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid),
    ...list,
  });
}

export function usePermitPrint(id: string) {
  return useQuery({
    queryKey: pk.print(id),
    queryFn: () => unwrap(api.GET("/api/v1/permits/{permit_id}/print", { params: { path: { permit_id: id } } })),
    enabled: Boolean(id),
    retry: false,
  });
}

export function useClosurePack(id: string) {
  return useQuery({
    queryKey: pk.closurePack(id),
    queryFn: () => unwrap(api.GET("/api/v1/permits/{permit_id}/closure-pack", { params: { path: { permit_id: id } } })),
    enabled: Boolean(id),
    retry: false,
  });
}

export function usePtwBoard(pid: string, q: QueryOf<"get_ptw_board">) {
  return useQuery({
    queryKey: pk.board(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/ptw-board", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid),
    refetchInterval: 30_000,
    ...list,
  });
}

/* ── JSA ── */

export function useJsaTemplates(pid: string, q: QueryOf<"list_jsa_templates">, o: Opt = {}) {
  return useQuery({
    queryKey: pk.jsaTemplates(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/jsa-templates", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    ...list,
  });
}

export function useJsa(id: string | null | undefined) {
  return useQuery({
    queryKey: pk.jsa(id ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/jsas/{jsa_id}", { params: { path: { jsa_id: id ?? "" } } })),
    enabled: Boolean(id),
  });
}

export function useJsaRevisions(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: pk.jsaRevisions(id),
    queryFn: () => unwrap(api.GET("/api/v1/jsas/{jsa_id}/revisions", { params: { path: { jsa_id: id } } })),
    enabled: Boolean(id) && (o.enabled ?? true),
  });
}

/* ── gas ── */

export function useDetectors(pid: string, q: QueryOf<"list_gas_detectors">, o: Opt = {}) {
  return useQuery({
    queryKey: pk.detectors(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/gas-detectors", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    ...list,
  });
}

export function useDetector(id: string) {
  return useQuery({
    queryKey: pk.detector(id),
    queryFn: () => unwrap(api.GET("/api/v1/gas-detectors/{detector_id}", { params: { path: { detector_id: id } } })),
    enabled: Boolean(id),
  });
}

export function useBumpTests(id: string) {
  return useQuery({
    queryKey: pk.bumpTests(id),
    queryFn: () => unwrap(api.GET("/api/v1/gas-detectors/{detector_id}/bump-tests", { params: { path: { detector_id: id }, query: {} } })),
    enabled: Boolean(id),
  });
}

export function usePermitGasTests(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: pk.permitGasTests(id),
    queryFn: () => unwrap(api.GET("/api/v1/permits/{permit_id}/gas-tests", { params: { path: { permit_id: id } } })),
    enabled: Boolean(id) && (o.enabled ?? true),
  });
}

export function useGasTests(pid: string, q: QueryOf<"list_project_gas_tests">) {
  return useQuery({
    queryKey: pk.gasTests(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/gas-tests", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid),
    ...list,
  });
}

export function useGasTest(id: string) {
  return useQuery({
    queryKey: pk.gasTest(id),
    queryFn: () => unwrap(api.GET("/api/v1/gas-tests/{gas_test_id}", { params: { path: { gas_test_id: id } } })),
    enabled: Boolean(id),
  });
}

/* ── isolations / LOTO ── */

export function useIsolations(pid: string, q: QueryOf<"list_isolations">, o: Opt = {}) {
  return useQuery({
    queryKey: pk.isolations(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/isolations", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    ...list,
  });
}

export function useIsolation(id: string) {
  return useQuery({
    queryKey: pk.isolation(id),
    queryFn: () => unwrap(api.GET("/api/v1/isolations/{isolation_id}", { params: { path: { isolation_id: id } } })),
    enabled: Boolean(id),
  });
}

export function usePersonalLocks(id: string) {
  return useQuery({
    queryKey: pk.personalLocks(id),
    queryFn: () => unwrap(api.GET("/api/v1/isolations/{isolation_id}/personal-locks", { params: { path: { isolation_id: id } } })),
    enabled: Boolean(id),
  });
}

export function useLocks(pid: string, q: QueryOf<"list_locks">, o: Opt = {}) {
  return useQuery({
    queryKey: pk.locks(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/locks", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    ...list,
  });
}

/* ── SIMOPS ── */

export function useConflicts(pid: string, q: QueryOf<"list_simops_conflicts">, o: Opt = {}) {
  return useQuery({
    queryKey: pk.conflicts(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/simops-conflicts", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    ...list,
  });
}

export function useConflict(id: string) {
  return useQuery({
    queryKey: pk.conflict(id),
    queryFn: () => unwrap(api.GET("/api/v1/simops-conflicts/{conflict_id}", { params: { path: { conflict_id: id } } })),
    enabled: Boolean(id),
  });
}

/* ── audits ── */

export function usePtwAudits(pid: string, q: QueryOf<"list_ptw_audits">) {
  return useQuery({
    queryKey: pk.audits(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/ptw-audits", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid),
    ...list,
  });
}

export function usePtwAudit(id: string) {
  return useQuery({
    queryKey: pk.audit(id),
    queryFn: () => unwrap(api.GET("/api/v1/ptw-audits/{audit_id}", { params: { path: { audit_id: id } } })),
    enabled: Boolean(id),
  });
}

export function usePtwAuditChecklist(pid: string, type: Schemas["PtwAuditType"], permitId: string | null) {
  return useQuery({
    queryKey: pk.auditChecklist(pid, type, permitId),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/ptw-audits/checklist", { params: { path: { project_id: pid }, query: { audit_type: type, permit_id: permitId } } })),
    // Field and closure audits need their permit first; unpermitted-work audits have no permit.
    enabled: Boolean(pid) && (type === "unpermitted_work" || Boolean(permitId)),
  });
}
