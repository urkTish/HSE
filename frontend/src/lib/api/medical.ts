"use client";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "./client";
import type { QueryOf } from "./queries";

type Opt = { enabled?: boolean };

/** Query keys for Phase 6a (occupational health). Writes invalidate by the first element. */
export const mk = {
  reference: () => ["fitness-reference"] as const,
  codes: (q: object) => ["fitness-codes", q] as const,
  providers: (q: object) => ["medical-providers", q] as const,
  provider: (id: string) => ["medical-provider", id] as const,
  providerAffected: (id: string) => ["medical-provider-affected", id] as const,
  examiners: (q: object) => ["medical-examiners", q] as const,
  plan: (pid: string, q: object) => ["medical-plan", pid, q] as const,
  lineVersions: (id: string) => ["medical-plan-line-versions", id] as const,
  profile: (did: string) => ["health-profile", did] as const,
  requirements: (did: string, q: object) => ["fitness-requirements", did, q] as const,
  gaps: (pid: string, q: object) => ["fitness-gaps", pid, q] as const,
  assessments: (pid: string, q: object) => ["fitness-assessments", pid, q] as const,
  assessment: (id: string) => ["fitness-assessment", id] as const,
  verifications: (id: string) => ["fitness-verifications", id] as const,
  workerFitness: (wid: string, pid: string) => ["worker-fitness", wid, pid] as const,
  holds: (pid: string, q: object) => ["fitness-holds", pid, q] as const,
  referrals: (pid: string, q: object) => ["fitness-referrals", pid, q] as const,
  settings: (pid: string) => ["medical-settings", pid] as const,
  imports: (pid: string, q: object) => ["medical-imports", pid, q] as const,
  importBatch: (id: string) => ["medical-import", id] as const,
  kpis: (q: object) => ["kpi", "occupational-health", q] as const,
};

/** Every Phase 6a prefix plus the hook consumers, refreshed together after a medical write. */
export const MEDICAL_PREFIXES = [
  ...new Set(Object.values(mk).map((f) => (f as (...a: string[]) => readonly unknown[])("", "", "")[0] as string)),
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

export function useMedicalRefresh() {
  const qc = useQueryClient();
  return async () => {
    await Promise.all(MEDICAL_PREFIXES.map((k) => qc.invalidateQueries({ queryKey: [k] })));
  };
}

const list = { placeholderData: keepPreviousData };
const on = (id: string, o: Opt) => Boolean(id) && (o.enabled ?? true);

/* ── catalogue, providers, examiners ── */

export function useFitnessReference() {
  return useQuery({
    queryKey: mk.reference(),
    queryFn: () => unwrap(api.GET("/api/v1/fitness-reference")),
    staleTime: 10 * 60_000,
  });
}

export function useFitnessCodes(q: QueryOf<"list_fitness_codes"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: mk.codes(q),
    queryFn: () => unwrap(api.GET("/api/v1/fitness-codes", { params: { query: q } })),
    enabled: o.enabled ?? true,
    staleTime: 60_000,
    ...list,
  });
}

export function useMedicalProviders(q: QueryOf<"list_medical_providers"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: mk.providers(q),
    queryFn: () => unwrap(api.GET("/api/v1/medical-providers", { params: { query: q } })),
    enabled: o.enabled ?? true,
    ...list,
  });
}

export function useMedicalProvider(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: mk.provider(id),
    queryFn: () => unwrap(api.GET("/api/v1/medical-providers/{provider_id}", { params: { path: { provider_id: id } } })),
    enabled: on(id, o),
  });
}

export function useMedicalProviderAffected(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: mk.providerAffected(id),
    queryFn: () => unwrap(api.GET("/api/v1/medical-providers/{provider_id}/affected", { params: { path: { provider_id: id } } })),
    enabled: on(id, o),
  });
}

export function useMedicalExaminers(q: QueryOf<"list_medical_examiners"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: mk.examiners(q),
    queryFn: () => unwrap(api.GET("/api/v1/medical-examiners", { params: { query: q } })),
    enabled: o.enabled ?? true,
    ...list,
  });
}

/* ── plan, profiles, requirements, gaps ── */

export function useMedicalPlan(pid: string, q: QueryOf<"get_medical_plan"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: mk.plan(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/medical-plan", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useMedicalLineVersions(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: mk.lineVersions(id),
    queryFn: () => unwrap(api.GET("/api/v1/medical-plan-lines/{line_id}/versions", { params: { path: { line_id: id } } })),
    enabled: on(id, o),
  });
}

export function useHealthProfile(did: string, o: Opt = {}) {
  return useQuery({
    queryKey: mk.profile(did),
    queryFn: () => unwrap(api.GET("/api/v1/deployments/{deployment_id}/health-profile", { params: { path: { deployment_id: did } } })),
    enabled: on(did, o),
    retry: false,
  });
}

export function useFitnessRequirements(did: string, q: QueryOf<"get_fitness_requirements"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: mk.requirements(did, q),
    queryFn: () => unwrap(api.GET("/api/v1/deployments/{deployment_id}/fitness-requirements", { params: { path: { deployment_id: did }, query: q } })),
    enabled: on(did, o),
    retry: false,
  });
}

export function useFitnessGaps(pid: string, q: QueryOf<"list_fitness_gaps"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: mk.gaps(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/fitness-gaps", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

/* ── assessments ── */

export function useFitnessAssessments(pid: string, q: QueryOf<"list_fitness_assessments"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: mk.assessments(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/fitness-assessments", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useFitnessAssessment(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: mk.assessment(id),
    queryFn: () => unwrap(api.GET("/api/v1/fitness-assessments/{assessment_id}", { params: { path: { assessment_id: id } } })),
    enabled: on(id, o),
  });
}

export function useFitnessVerifications(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: mk.verifications(id),
    queryFn: () => unwrap(api.GET("/api/v1/fitness-assessments/{assessment_id}/verifications", { params: { path: { assessment_id: id } } })),
    enabled: on(id, o),
    retry: false,
  });
}

export function useWorkerFitness(wid: string, pid: string, o: Opt = {}) {
  return useQuery({
    queryKey: mk.workerFitness(wid, pid),
    queryFn: () => unwrap(api.GET("/api/v1/workers/{worker_id}/fitness", { params: { path: { worker_id: wid }, query: { project_id: pid } } })),
    enabled: on(wid, o) && Boolean(pid),
    retry: false,
  });
}

/* ── holds and referrals ── */

export function useFitnessHolds(pid: string, q: QueryOf<"list_fitness_holds"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: mk.holds(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/fitness-holds", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useFitnessReferrals(pid: string, q: QueryOf<"list_fitness_referrals"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: mk.referrals(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/fitness-referrals", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

/* ── settings, imports, KPIs ── */

export function useMedicalSettings(pid: string, o: Opt = {}) {
  return useQuery({
    queryKey: mk.settings(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/medical-settings", { params: { path: { project_id: pid } } })),
    enabled: on(pid, o),
  });
}

export function useMedicalImports(pid: string, q: QueryOf<"list_medical_imports"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: mk.imports(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/medical-imports", { params: { path: { project_id: pid }, query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useMedicalImport(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: mk.importBatch(id),
    queryFn: () => unwrap(api.GET("/api/v1/medical-imports/{batch_id}", { params: { path: { batch_id: id } } })),
    enabled: on(id, o),
  });
}

export function useOccupationalHealthKpis(q: QueryOf<"get_occupational_health_kpis">, o: Opt = {}) {
  return useQuery({
    queryKey: mk.kpis(q),
    queryFn: () => unwrap(api.GET("/api/v1/kpi/occupational-health", { params: { query: q } })),
    enabled: o.enabled ?? true,
    ...list,
  });
}
