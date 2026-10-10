"use client";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "./client";
import type { QueryOf } from "./queries";

type Opt = { enabled?: boolean };

/** Query keys for Phase 6g (contractor scorecard, report packs, generic exports). Writes invalidate by the first element. */
export const sck = {
  reference: () => ["sc-reference"] as const,
  settings: (pid: string) => ["sc-settings", pid] as const,
  profiles: (q: object) => ["sc-profiles", q] as const,
  profile: (id: string) => ["sc-profile", id] as const,
  cards: (pid: string, q: object) => ["sc-cards", pid, q] as const,
  card: (id: string) => ["sc-card", id] as const,
  ranking: (pid: string, month: string) => ["sc-ranking", pid, month] as const,
  remarks: (pid: string, q: object) => ["sc-remarks", pid, q] as const,
  watch: (pid: string, q: object) => ["sc-watch", pid, q] as const,
  watchEntry: (id: string) => ["sc-watch-entry", id] as const,
  suspension: (id: string) => ["sc-suspension", id] as const,
  cps: (id: string) => ["sc-cps", id] as const,
  packs: (pid: string, q: object) => ["rp-packs", pid, q] as const,
  pack: (id: string) => ["rp-pack", id] as const,
  deliveries: (id: string) => ["rp-deliveries", id] as const,
  distribution: (pid: string, type: string) => ["rp-distribution", pid, type] as const,
  datasets: () => ["xp-datasets"] as const,
  jobs: (q: object) => ["xp-jobs", q] as const,
  subscriptions: () => ["xp-subscriptions"] as const,
  kpis: (q: object) => ["kpi", "scorecards", q] as const,
};

/** Every Phase 6g prefix plus the Phase 1 consumers (dashboard, CAs). */
export const SC_PREFIXES = [
  ...new Set(Object.values(sck).map((f) => (f as (...a: string[]) => readonly unknown[])("", "", "")[0] as string)),
  "kpi",
  "dashboard",
  "corrective-actions",
  "history",
];

export function useScRefresh() {
  const qc = useQueryClient();
  return async () => {
    await Promise.all(SC_PREFIXES.map((k) => qc.invalidateQueries({ queryKey: [k] })));
  };
}

const list = { placeholderData: keepPreviousData };
const on = (id: string, o: Opt) => Boolean(id) && (o.enabled ?? true);
const P = (pid: string) => ({ path: { project_id: pid } });

export function useScReference() {
  return useQuery({ queryKey: sck.reference(), queryFn: () => unwrap(api.GET("/api/v1/scorecard-reference")), staleTime: 10 * 60_000 });
}

export function useScSettings(pid: string, o: Opt = {}) {
  return useQuery({ queryKey: sck.settings(pid), queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/scorecard-settings", { params: P(pid) })), enabled: on(pid, o) });
}

export function useScProfiles(q: QueryOf<"list_scorecard_profiles"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: sck.profiles(q), queryFn: () => unwrap(api.GET("/api/v1/scorecard-profiles", { params: { query: q } })), enabled: o.enabled ?? true });
}

export function useScProfile(id: string, o: Opt = {}) {
  return useQuery({ queryKey: sck.profile(id), queryFn: () => unwrap(api.GET("/api/v1/scorecard-profiles/{profile_id}", { params: { path: { profile_id: id } } })), enabled: on(id, o) });
}

export function useScCards(pid: string, q: QueryOf<"list_scorecards"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: sck.cards(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/scorecards", { params: { ...P(pid), query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useScCard(id: string, o: Opt = {}) {
  return useQuery({ queryKey: sck.card(id), queryFn: () => unwrap(api.GET("/api/v1/scorecards/{card_id}", { params: { path: { card_id: id } } })), enabled: on(id, o), retry: false });
}

export function useScRanking(pid: string, month: string, o: Opt = {}) {
  return useQuery({
    queryKey: sck.ranking(pid, month),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/scorecard-ranking", { params: { ...P(pid), query: { month } } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useScRemarks(pid: string, q: QueryOf<"list_scorecard_remarks"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: sck.remarks(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/scorecard-remarks", { params: { ...P(pid), query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useWatchList(pid: string, q: QueryOf<"list_watch_list"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: sck.watch(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/watch-list", { params: { ...P(pid), query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useWatchEntry(id: string, o: Opt = {}) {
  return useQuery({ queryKey: sck.watchEntry(id), queryFn: () => unwrap(api.GET("/api/v1/watch-list/{entry_id}", { params: { path: { entry_id: id } } })), enabled: on(id, o) });
}

export function useSuspensionForm(id: string, o: Opt = {}) {
  return useQuery({ queryKey: sck.suspension(id), queryFn: () => unwrap(api.GET("/api/v1/watch-list/{entry_id}/suspension-form", { params: { path: { entry_id: id } } })), enabled: on(id, o) });
}

export function usePerformanceSummary(contractorId: string, o: Opt = {}) {
  return useQuery({
    queryKey: sck.cps(contractorId),
    queryFn: () => unwrap(api.GET("/api/v1/contractors/{contractor_id}/performance-summary", { params: { path: { contractor_id: contractorId } } })),
    enabled: on(contractorId, o),
  });
}

export function useReportPacks(pid: string, q: QueryOf<"list_report_packs"> = {}, o: Opt = {}) {
  return useQuery({
    queryKey: sck.packs(pid, q),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/report-packs", { params: { ...P(pid), query: q } })),
    enabled: on(pid, o),
    ...list,
  });
}

export function useReportPack(id: string, o: Opt = {}) {
  return useQuery({ queryKey: sck.pack(id), queryFn: () => unwrap(api.GET("/api/v1/report-packs/{pack_id}", { params: { path: { pack_id: id } } })), enabled: on(id, o) });
}

export function usePackDeliveries(id: string, o: Opt = {}) {
  return useQuery({
    queryKey: sck.deliveries(id),
    queryFn: () => unwrap(api.GET("/api/v1/report-packs/{pack_id}/deliveries", { params: { path: { pack_id: id }, query: { page_size: 200 } } })),
    enabled: on(id, o),
  });
}

export function useDistributionList(pid: string, type: "MCR" | "SCP" | "CPS" | "OSHA300" | "HEAT", o: Opt = {}) {
  return useQuery({
    queryKey: sck.distribution(pid, type),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/distribution-lists/{report_type}", { params: { path: { project_id: pid, report_type: type } } })),
    enabled: on(pid, o),
  });
}

export function useExportDatasets(o: Opt = {}) {
  return useQuery({ queryKey: sck.datasets(), queryFn: () => unwrap(api.GET("/api/v1/export-datasets")), staleTime: 10 * 60_000, enabled: o.enabled ?? true });
}

export function useExportJobs(q: QueryOf<"list_export_jobs"> = {}, o: Opt = {}) {
  return useQuery({ queryKey: sck.jobs(q), queryFn: () => unwrap(api.GET("/api/v1/export-jobs", { params: { query: q } })), enabled: o.enabled ?? true, ...list });
}

export function useExportSubscriptions(o: Opt = {}) {
  return useQuery({ queryKey: sck.subscriptions(), queryFn: () => unwrap(api.GET("/api/v1/export-subscriptions")), enabled: o.enabled ?? true });
}

export function useScKpis(q: QueryOf<"get_scorecard_kpis">, o: Opt = {}) {
  return useQuery({ queryKey: sck.kpis(q), queryFn: () => unwrap(api.GET("/api/v1/kpi/scorecards", { params: { query: q } })), enabled: o.enabled ?? true, ...list });
}
