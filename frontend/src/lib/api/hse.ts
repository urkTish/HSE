"use client";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, unwrap } from "./client";
import type { QueryOf } from "./queries";

type Opt = { enabled?: boolean };

/** Query keys for Phase 1 data; prefixes are invalidated after writes. */
export const hk = {
  refLists: ["reference-lists"] as const,
  hseSettings: (pid: string) => ["hse-settings", pid] as const,
  returns: (pid: string, q: object) => ["workforce-returns", pid, q] as const,
  ret: (id: string) => ["workforce-return", id] as const,
  months: (pid: string, year?: number) => ["workforce-months", pid, year ?? null] as const,
  imports: (pid: string, q: object) => ["workforce-imports", pid, q] as const,
  importBatch: (id: string, ok: boolean) => ["workforce-import", id, ok] as const,
  incidents: (pid: string, q: object) => ["incidents", pid, q] as const,
  incident: (id: string) => ["incident", id] as const,
  excluded: (pid: string, q: object) => ["excluded-cases", pid, q] as const,
  injuryCase: (id: string) => ["injury-case", id] as const,
  investigation: (id: string) => ["investigation", id] as const,
  observations: (pid: string, q: object) => ["observations", pid, q] as const,
  observation: (id: string) => ["observation", id] as const,
  plans: (pid: string, q: object) => ["inspection-plans", pid, q] as const,
  plan: (id: string) => ["inspection-plan", id] as const,
  inspections: (pid: string, q: object) => ["inspections", pid, q] as const,
  inspection: (id: string) => ["inspection", id] as const,
  cas: (pid: string, q: object) => ["corrective-actions", pid, q] as const,
  ca: (id: string) => ["corrective-action", id] as const,
  meetings: (pid: string, q: object) => ["hse-meetings", pid, q] as const,
  meeting: (id: string) => ["hse-meeting", id] as const,
  attachments: (type: string, id: string) => ["attachments", type, id] as const,
  aiStatus: (pid: string) => ["ai-status", pid] as const,
  reports: (pid: string, page: number) => ["monthly-reports", pid, page] as const,
  report: (id: string) => ["monthly-report", id] as const,
  aiLogs: (q: object) => ["ai-logs", q] as const,
};

export function useReferenceLists() {
  return useQuery({
    queryKey: hk.refLists,
    queryFn: () => unwrap(api.GET("/api/v1/reference-lists")),
    staleTime: 10 * 60_000,
  });
}

export function useHseSettings(pid: string | null | undefined, o: Opt = {}) {
  return useQuery({
    queryKey: hk.hseSettings(pid ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/hse-settings", { params: { path: { project_id: pid ?? "" } } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    staleTime: 60_000,
  });
}

export function useWorkforceReturns(pid: string, q: QueryOf<"list_workforce_returns">) {
  return useQuery({
    queryKey: hk.returns(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/workforce-returns", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid),
    placeholderData: keepPreviousData,
  });
}

export function useWorkforceReturn(id: string) {
  return useQuery({
    queryKey: hk.ret(id),
    queryFn: () => unwrap(api.GET("/api/v1/workforce-returns/{return_id}", { params: { path: { return_id: id } } })),
    enabled: Boolean(id),
  });
}

export function useWorkforceMonths(pid: string, year?: number) {
  return useQuery({
    queryKey: hk.months(pid, year),
    queryFn: () =>
      unwrap(api.GET("/api/v1/projects/{project_id}/workforce-months", { params: { path: { project_id: pid }, query: { year: year ?? null } } })),
    enabled: Boolean(pid),
  });
}

export function useWorkforceImports(pid: string, q: QueryOf<"list_workforce_imports">) {
  return useQuery({
    queryKey: hk.imports(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/workforce-imports", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid),
    placeholderData: keepPreviousData,
  });
}

export function useWorkforceImport(id: string, includeOk = false) {
  return useQuery({
    queryKey: hk.importBatch(id, includeOk),
    queryFn: () =>
      unwrap(api.GET("/api/v1/workforce-imports/{batch_id}", { params: { path: { batch_id: id }, query: { include_ok_rows: includeOk } } })),
    enabled: Boolean(id),
    placeholderData: keepPreviousData,
  });
}

export function useIncidents(pid: string, q: QueryOf<"list_incidents">) {
  return useQuery({
    queryKey: hk.incidents(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/incidents", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid),
    placeholderData: keepPreviousData,
  });
}

export function useIncident(id: string) {
  return useQuery({
    queryKey: hk.incident(id),
    queryFn: () => unwrap(api.GET("/api/v1/incidents/{incident_id}", { params: { path: { incident_id: id } } })),
    enabled: Boolean(id),
  });
}

export function useExcludedCases(pid: string, q: QueryOf<"list_excluded_cases">) {
  return useQuery({
    queryKey: hk.excluded(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/incidents/excluded-cases", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid),
  });
}

export function useInjuryCase(id: string) {
  return useQuery({
    queryKey: hk.injuryCase(id),
    queryFn: () => unwrap(api.GET("/api/v1/injury-cases/{case_id}", { params: { path: { case_id: id } } })),
    enabled: Boolean(id),
  });
}

export function useInvestigation(incidentId: string, enabled = true) {
  return useQuery({
    queryKey: hk.investigation(incidentId),
    queryFn: () => unwrap(api.GET("/api/v1/incidents/{incident_id}/investigation", { params: { path: { incident_id: incidentId } } })),
    enabled: Boolean(incidentId) && enabled,
    retry: false,
  });
}

export function useObservations(pid: string, q: QueryOf<"list_observations">) {
  return useQuery({
    queryKey: hk.observations(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/observations", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid),
    placeholderData: keepPreviousData,
  });
}

export function useObservation(id: string) {
  return useQuery({
    queryKey: hk.observation(id),
    queryFn: () => unwrap(api.GET("/api/v1/observations/{observation_id}", { params: { path: { observation_id: id } } })),
    enabled: Boolean(id),
  });
}

export function useInspectionPlans(pid: string, q: QueryOf<"list_inspection_plans">) {
  return useQuery({
    queryKey: hk.plans(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/inspection-plans", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid),
    placeholderData: keepPreviousData,
  });
}

export function useInspectionPlan(id: string) {
  return useQuery({
    queryKey: hk.plan(id),
    queryFn: () => unwrap(api.GET("/api/v1/inspection-plans/{plan_id}", { params: { path: { plan_id: id } } })),
    enabled: Boolean(id),
  });
}

export function useInspections(pid: string, q: QueryOf<"list_inspections">) {
  return useQuery({
    queryKey: hk.inspections(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/inspections", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid),
    placeholderData: keepPreviousData,
  });
}

export function useInspection(id: string) {
  return useQuery({
    queryKey: hk.inspection(id),
    queryFn: () => unwrap(api.GET("/api/v1/inspections/{inspection_id}", { params: { path: { inspection_id: id } } })),
    enabled: Boolean(id),
  });
}

export function useCorrectiveActions(pid: string, q: QueryOf<"list_corrective_actions">, o: Opt = {}) {
  return useQuery({
    queryKey: hk.cas(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/corrective-actions", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid) && (o.enabled ?? true),
    placeholderData: keepPreviousData,
  });
}

export function useCorrectiveAction(id: string) {
  return useQuery({
    queryKey: hk.ca(id),
    queryFn: () => unwrap(api.GET("/api/v1/corrective-actions/{ca_id}", { params: { path: { ca_id: id } } })),
    enabled: Boolean(id),
  });
}

export function useHseMeetings(pid: string, q: QueryOf<"list_hse_meetings">) {
  return useQuery({
    queryKey: hk.meetings(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/hse-meetings", { params: { path: { project_id: pid }, query: q } })),
    enabled: Boolean(pid),
    placeholderData: keepPreviousData,
  });
}

export function useHseMeeting(id: string) {
  return useQuery({
    queryKey: hk.meeting(id),
    queryFn: () => unwrap(api.GET("/api/v1/hse-meetings/{meeting_id}", { params: { path: { meeting_id: id } } })),
    enabled: Boolean(id),
  });
}

export function useAttachments(ownerType: QueryOf<"list_attachments">["owner_type"], ownerId: string, enabled = true) {
  return useQuery({
    queryKey: hk.attachments(ownerType, ownerId),
    queryFn: () => unwrap(api.GET("/api/v1/attachments", { params: { query: { owner_type: ownerType, owner_id: ownerId } } })),
    enabled: Boolean(ownerId) && enabled,
  });
}

export function useAiStatus(pid: string | null | undefined) {
  return useQuery({
    queryKey: hk.aiStatus(pid ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/ai/status", { params: { query: { project_id: pid ?? "" } } })),
    enabled: Boolean(pid),
    staleTime: 60_000,
    retry: false,
  });
}

export function useMonthlyReports(pid: string, page: number) {
  return useQuery({
    queryKey: hk.reports(pid, page),
    queryFn: () =>
      unwrap(api.GET("/api/v1/projects/{project_id}/monthly-reports", { params: { path: { project_id: pid }, query: { page, page_size: 20 } } })),
    enabled: Boolean(pid),
    placeholderData: keepPreviousData,
  });
}

export function useMonthlyReport(id: string) {
  return useQuery({
    queryKey: hk.report(id),
    queryFn: () => unwrap(api.GET("/api/v1/monthly-reports/{report_id}", { params: { path: { report_id: id } } })),
    enabled: Boolean(id),
    refetchInterval: (q) => (q.state.data?.status === "generating" ? 3000 : false),
  });
}

export function useAiLogs(q: QueryOf<"list_ai_logs">) {
  return useQuery({
    queryKey: hk.aiLogs(q),
    queryFn: () => unwrap(api.GET("/api/v1/ai/logs", { params: { query: q } })),
    placeholderData: keepPreviousData,
  });
}
