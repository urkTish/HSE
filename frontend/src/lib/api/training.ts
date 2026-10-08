"use client";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "./client";
import type { QueryOf } from "./queries";

type Opt = { enabled?: boolean; refetchInterval?: number | false };

/** Query keys for Phase 5 (training). Writes invalidate by the first element. */
export const tk = {
  courses: (q: object) => ["training-courses", q] as const,
  course: (code: string, pid: string) => ["training-course", code, pid] as const,
  providers: (q: object) => ["training-providers", q] as const,
  provider: (id: string) => ["training-provider", id] as const,
  providerImpact: (id: string) => ["training-provider-impact", id] as const,
  acceptability: (id: string, q: object) => ["training-provider-acceptability", id, q] as const,
  trainers: (pid: string, q: object) => ["trainer-authorisations", pid, q] as const,
  trainer: (id: string) => ["trainer-authorisation", id] as const,
  matrix: (pid: string, q: object) => ["training-matrix", pid, q] as const,
  lineVersions: (id: string) => ["training-matrix-line-versions", id] as const,
  profile: (did: string) => ["training-profile", did] as const,
  requirements: (did: string, asOf: string) => ["training-requirements", did, asOf] as const,
  exemptions: (pid: string, q: object) => ["training-exemptions", pid, q] as const,
  gaps: (pid: string, q: object) => ["training-gaps", pid, q] as const,
  gapSummary: (pid: string, q: object) => ["training-gap-summary", pid, q] as const,
  plan: (pid: string, q: object) => ["refresher-plan", pid, q] as const,
  sessions: (pid: string, q: object) => ["training-sessions", pid, q] as const,
  session: (id: string) => ["training-session", id] as const,
  nominations: (id: string) => ["training-nominations", id] as const,
  records: (pid: string, q: object) => ["training-records", pid, q] as const,
  record: (id: string, pid: string) => ["training-record", id, pid] as const,
  verifications: (id: string) => ["training-verifications", id] as const,
  verificationLog: (pid: string, q: object) => ["training-verification-log", pid, q] as const,
  certificate: (id: string) => ["training-certificate", id] as const,
  passport: (wid: string, pid: string) => ["training-passport", wid, pid] as const,
  report: (wid: string) => ["training-report", wid] as const,
  settings: (pid: string) => ["training-settings", pid] as const,
  hours: (pid: string, q: object) => ["training-hours", pid, q] as const,
  imports: (pid: string, q: object) => ["training-imports", pid, q] as const,
  importBatch: (id: string, ok: boolean) => ["training-import", id, ok] as const,
  kpis: (q: object) => ["kpi", "training", q] as const,
};

/** Every Phase 5 prefix plus the hook consumers (gates, permits, dashboard), refreshed together after a training write. */
export const TRAINING_PREFIXES = [
  ...new Set(Object.values(tk).map((f) => (f as (...a: string[]) => readonly unknown[])("", "", "")[0] as string)),
  "dashboard",
  "kpi",
  "hook-policy",
  "hook-readiness",
  "permit",
  "permits",
  "history",
  "worker",
  "deployment",
];

export function useTrainingRefresh() {
  const qc = useQueryClient();
  return async () => {
    await Promise.all(TRAINING_PREFIXES.map((k) => qc.invalidateQueries({ queryKey: [k] })));
  };
}

const list = { placeholderData: keepPreviousData };
const on = (id: string, o: Opt) => Boolean(id) && (o.enabled ?? true);

/* ── catalogue ── */

export function useTrainingCourses(q: QueryOf<"list_training_courses"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: tk.courses(q),
    queryFn: () => unwrap(api.GET("/api/v1/training-courses", { params: { query: q } })),
    enabled: o.enabled ?? true,
    staleTime: 60_000,
    ...list,
  });
}

export function useTrainingCourse(code: string, pid: string, o: Opt = {}) {
  return useQuery({
    queryKey: tk.course(code, pid),
    queryFn: () => unwrap(api.GET("/api/v1/training-courses/{code}", { params: { path: { code }, query: pid ? { project_id: pid } : {} } })),
    enabled: on(code, o),
  });
}

/* ── providers ── */

export function useTrainingProviders(q: QueryOf<"list_training_providers"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: tk.providers(q),
    queryFn: () => unwrap(api.GET("/api/v1/training-providers", { params: { query: q } })),
    enabled: o.enabled ?? true,
    ...list,
  });
}

export function useTrainingProvider(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: tk.provider(id),
    queryFn: () => unwrap(api.GET("/api/v1/training-providers/{provider_id}", { params: { path: { provider_id: id } } })),
    enabled: on(id, o),
  });
}

export function useTrainingProviderImpact(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: tk.providerImpact(id),
    queryFn: () => unwrap(api.GET("/api/v1/training-providers/{provider_id}/affected", { params: { path: { provider_id: id } } })),
    enabled: on(id, o),
  });
}

export function useProviderAcceptability(id: string, q: QueryOf<"get_training_provider_acceptability">, o: Opt = {}) {
  return useQuery({
    queryKey: tk.acceptability(id, q),
    queryFn: () => unwrap(api.GET("/api/v1/training-providers/{provider_id}/acceptability", { params: { path: { provider_id: id }, query: q } })),
    enabled: on(id, o) && Boolean(q.course_code),
    retry: false,
  });
}

/* ── trainer authorisations ── */

export function useTrainerAuthorisations(pid: string, q: QueryOf<"list_trainer_authorisations"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: tk.trainers(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/trainer-authorisations", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useTrainerAuthorisation(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: tk.trainer(id),
    queryFn: () => unwrap(api.GET("/api/v1/trainer-authorisations/{authorisation_id}", { params: { path: { authorisation_id: id } } })),
    enabled: on(id, o),
  });
}

/* ── matrix, profiles, exemptions, gaps, plan ── */

export function useTrainingMatrix(pid: string, q: QueryOf<"get_training_matrix"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: tk.matrix(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/training-matrix", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useMatrixLineVersions(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: tk.lineVersions(id),
    queryFn: () => unwrap(api.GET("/api/v1/training-matrix-lines/{line_id}/versions", { params: { path: { line_id: id } } })),
    enabled: on(id, o),
  });
}

export function useTrainingProfile(did: string, o: Opt = {}) {
  return useQuery({
    queryKey: tk.profile(did),
    queryFn: () => unwrap(api.GET("/api/v1/deployments/{deployment_id}/training-profile", { params: { path: { deployment_id: did } } })),
    enabled: on(did, o),
    retry: false,
  });
}

export function useTrainingRequirements(did: string, asOf: string | null, o: Opt = {}) {
  return useQuery({
    queryKey: tk.requirements(did, asOf ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/deployments/{deployment_id}/training-requirements", { params: { path: { deployment_id: did }, query: { as_of: asOf || null } } })),
    enabled: on(did, o),
    retry: false,
  });
}

export function useTrainingExemptions(pid: string, q: QueryOf<"list_training_exemptions"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: tk.exemptions(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/training-exemptions", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useTrainingGaps(pid: string, q: QueryOf<"list_training_gaps">, o: Opt = {}) {
  return useQuery({
    queryKey: tk.gaps(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/training-gaps", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    retry: false,
    ...list,
  });
}

export function useTrainingGapSummary(pid: string, q: QueryOf<"get_training_gap_summary">, o: Opt = {}) {
  return useQuery({
    queryKey: tk.gapSummary(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/training-gaps/summary", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useRefresherPlan(pid: string, q: QueryOf<"get_refresher_plan">, o: Opt = {}) {
  return useQuery({
    queryKey: tk.plan(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/refresher-plan", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

/* ── sessions ── */

export function useTrainingSessions(pid: string, q: QueryOf<"list_training_sessions">, o: Opt = {}) {
  return useQuery({
    queryKey: tk.sessions(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/training-sessions", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useTrainingSession(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: tk.session(id),
    queryFn: () => unwrap(api.GET("/api/v1/training-sessions/{session_id}", { params: { path: { session_id: id } } })),
    enabled: on(id, o),
  });
}

export function useNominations(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: tk.nominations(id),
    queryFn: () => unwrap(api.GET("/api/v1/training-sessions/{session_id}/nominations", { params: { path: { session_id: id } } })),
    enabled: on(id, o),
  });
}

/* ── records ── */

export function useTrainingRecords(pid: string, q: QueryOf<"list_training_records">, o: Opt = {}) {
  return useQuery({
    queryKey: tk.records(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/training-records", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useTrainingRecord(id: string, pid: string, o: Opt = {}) {
  return useQuery({
    queryKey: tk.record(id, pid),
    queryFn: () => unwrap(api.GET("/api/v1/training-records/{record_id}", { params: { path: { record_id: id }, query: pid ? { project_id: pid } : {} } })),
    enabled: on(id, o),
  });
}

export function useTrainingVerifications(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: tk.verifications(id),
    queryFn: () => unwrap(api.GET("/api/v1/training-records/{record_id}/verifications", { params: { path: { record_id: id } } })),
    enabled: on(id, o),
  });
}

export function useTrainingVerificationLog(pid: string, q: QueryOf<"list_training_verification_log">, o: Opt = {}) {
  return useQuery({
    queryKey: tk.verificationLog(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/training-verification-log", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useTrainingCertificate(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: tk.certificate(id),
    queryFn: () => unwrap(api.GET("/api/v1/training-records/{record_id}/certificate", { params: { path: { record_id: id } } })),
    enabled: on(id, o),
    retry: false,
  });
}

export function useTrainingPassport(wid: string, pid: string, o: Opt = {}) {
  return useQuery({
    queryKey: tk.passport(wid, pid),
    queryFn: () => unwrap(api.GET("/api/v1/workers/{worker_id}/training-records", { params: { path: { worker_id: wid }, query: pid ? { project_id: pid } : {} } })),
    enabled: on(wid, o),
    retry: false,
  });
}

export function useTrainingReport(wid: string, o: Opt = {}) {
  return useQuery({
    queryKey: tk.report(wid),
    queryFn: () => unwrap(api.GET("/api/v1/workers/{worker_id}/training-report", { params: { path: { worker_id: wid }, query: { purpose: "data_subject_request" } } })),
    enabled: on(wid, o),
    retry: false,
  });
}

/* ── settings, hours, imports, KPIs ── */

export function useTrainingSettings(pid: string, o: Opt = {}) {
  return useQuery({
    queryKey: tk.settings(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/training-settings", { params: { path: { project_id: pid } } })),
    enabled: on(pid, o),
  });
}

export function useTrainingHours(pid: string, q: QueryOf<"get_training_hours_report">, o: Opt = {}) {
  return useQuery({
    queryKey: tk.hours(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/training-hours", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useTrainingImports(pid: string, q: QueryOf<"list_training_imports">, o: Opt = {}) {
  return useQuery({
    queryKey: tk.imports(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/training-imports", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useTrainingImport(id: string, includeOk: boolean, o: Opt = {}) {
  return useQuery({
    queryKey: tk.importBatch(id, includeOk),
    queryFn: () => unwrap(api.GET("/api/v1/training-imports/{batch_id}", { params: { path: { batch_id: id }, query: { include_ok_rows: includeOk } } })),
    enabled: on(id, o),
  });
}

export function useTrainingKpis(q: QueryOf<"get_training_kpis">, o: Opt = {}) {
  return useQuery({
    queryKey: tk.kpis(q),
    queryFn: () => unwrap(api.GET("/api/v1/kpi/training", { params: { query: q } })),
    enabled: o.enabled ?? true,
    staleTime: 60_000,
    ...list,
  });
}
