"use client";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "./client";
import type { QueryOf } from "./queries";

type Opt = { enabled?: boolean };

/** Query keys for Phase 6f (incident follow-up). Writes invalidate by the first element. */
export const fuk = {
  reference: () => ["fu-reference"] as const,
  settings: (pid: string) => ["fu-settings", pid] as const,
  rules: (pid: string) => ["fu-rules", pid] as const,
  requirements: (pid: string, q: object) => ["fu-requirements", pid, q] as const,
  packs: (pid: string, q: object) => ["fu-packs", pid, q] as const,
  pack: (id: string) => ["fu-pack", id] as const,
  submissions: (pid: string, q: object) => ["fu-submissions", pid, q] as const,
  band: (pid: string) => ["fu-band", pid] as const,
  actions: (pid: string) => ["fu-action-panel", pid] as const,
  lessons: (q: object) => ["lessons", q] as const,
  lesson: (id: string) => ["lesson", id] as const,
  distribution: (id: string) => ["lesson-distribution", id] as const,
  projectDistribution: (pid: string, q: object) => ["project-lesson-distribution", pid, q] as const,
  links: (id: string) => ["lesson-links", id] as const,
  similar: (incidentId: string) => ["similar-lessons", incidentId] as const,
  checks: (pid: string, q: object) => ["effectiveness-checks", pid, q] as const,
  kpis: (q: object) => ["kpi", "incident-followup", q] as const,
};

/** Every Phase 6f prefix plus the Phase 1 consumers (incident page, CAs, dashboard). */
export const FU_PREFIXES = [
  ...new Set(Object.values(fuk).map((f) => (f as (...a: string[]) => readonly unknown[])("", "", "")[0] as string)),
  "kpi",
  "dashboard",
  "incidents",
  "incident",
  "corrective-actions",
  "history",
];

export function useFuRefresh() {
  const qc = useQueryClient();
  return async () => {
    await Promise.all(FU_PREFIXES.map((k) => qc.invalidateQueries({ queryKey: [k] })));
  };
}

const list = { placeholderData: keepPreviousData };
const on = (id: string, o: Opt) => Boolean(id) && (o.enabled ?? true);
const P = (pid: string) => ({ path: { project_id: pid } });

export function useFuReference() {
  return useQuery({ queryKey: fuk.reference(), queryFn: () => unwrap(api.GET("/api/v1/followup-reference")), staleTime: 10 * 60_000 });
}

export function useFuSettings(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: fuk.settings(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/followup-settings", { params: P(pid) })), enabled: on(pid, o) });
}

export function useFuRules(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: fuk.rules(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/notification-rules", { params: P(pid) })), enabled: on(pid, o) });
}

export function useFuRequirements(pid: string, q: QueryOf<"list_notification_requirements"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: fuk.requirements(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/notification-requirements", { params: { ...P(pid), query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useFuPacks(pid: string, q: QueryOf<"list_notification_packs"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: fuk.packs(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/notification-packs", { params: { ...P(pid), query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useFuPack(id: string, o: Opt = {}) {
  return useQuery({ queryKey: fuk.pack(id), queryFn: () => unwrap(api.GET("/api/v1/notification-packs/{pack_id}", { params: { path: { pack_id: id } } })), enabled: on(id, o) });
}

export function useFuSubmissions(pid: string, q: QueryOf<"list_notification_submissions"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: fuk.submissions(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/notification-submissions", { params: { ...P(pid), query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useFuBand(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: fuk.band(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/followup-band", { params: P(pid) })), enabled: on(pid, o), refetchInterval: 60_000 });
}

export function useFuActionPanel(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: fuk.actions(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/followup-action-panel", { params: P(pid) })), enabled: on(pid, o) });
}

export function useLessons(q: QueryOf<"list_lessons"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: fuk.lessons(q), queryFn: () => unwrap(api.GET("/api/v1/lessons", { params: { query: q } })), enabled: o.enabled ?? true, ...list });
}

export function useLesson(id: string, o: Opt = {}) {
  return useQuery({ queryKey: fuk.lesson(id), queryFn: () => unwrap(api.GET("/api/v1/lessons/{lesson_id}", { params: { path: { lesson_id: id } } })), enabled: on(id, o) });
}

export function useLessonDistribution(id: string, o: Opt = {}) {
  return useQuery({ queryKey: fuk.distribution(id), queryFn: () => unwrap(api.GET("/api/v1/lessons/{lesson_id}/distribution", { params: { path: { lesson_id: id } } })), enabled: on(id, o) });
}

export function useProjectDistribution(pid: string, q: QueryOf<"list_project_lesson_distribution"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: fuk.projectDistribution(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/lesson-distribution", { params: { ...P(pid), query: q } })),
    enabled: on(pid, o),
  });
}

export function useLessonLinks(id: string, o: Opt = {}) {
  return useQuery({ queryKey: fuk.links(id), queryFn: () => unwrap(api.GET("/api/v1/lessons/{lesson_id}/links", { params: { path: { lesson_id: id } } })), enabled: on(id, o) });
}

export function useSimilarLessons(incidentId: string, o: Opt = {}) {
  return useQuery({
    queryKey: fuk.similar(incidentId),
    queryFn: () => unwrap(api.GET("/api/v1/incidents/{incident_id}/similar-lessons", { params: { path: { incident_id: incidentId } } })),
    enabled: on(incidentId, o),
  });
}

export function useEffectivenessChecks(pid: string, q: QueryOf<"list_effectiveness_checks"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: fuk.checks(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/effectiveness-checks", { params: { ...P(pid), query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useFuKpis(q: QueryOf<"get_incident_followup_kpis">, o: Opt = {}) {
  return useQuery({ queryKey: fuk.kpis(q), queryFn: () => unwrap(api.GET("/api/v1/kpi/incident-followup", { params: { query: q } })), enabled: o.enabled ?? true, ...list });
}
