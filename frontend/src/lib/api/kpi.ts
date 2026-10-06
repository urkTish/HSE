"use client";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "./client";
import type { QueryOf } from "./queries";

/** Shared KPI filter query (§5.7 D-2) — the same parameters on every /kpi endpoint. */
export type KpiQuery = QueryOf<"get_dashboard">;

const STALE = 60_000;

export const kk = {
  catalogue: ["kpi-catalogue"] as const,
  dashboard: (q: KpiQuery) => ["kpi", "dashboard", q] as const,
  chart: (id: string, q: KpiQuery, extra: object) => ["kpi", "chart", id, q, extra] as const,
  pyramid: (q: KpiQuery) => ["kpi", "pyramid", q] as const,
  league: (q: KpiQuery, rollup: boolean) => ["kpi", "league", q, rollup] as const,
  metric: (m: string, q: KpiQuery) => ["kpi", "metric", m, q] as const,
  sources: (m: string, part: string, page: number, q: KpiQuery) => ["kpi", "sources", m, part, page, q] as const,
  actionPanel: (q: KpiQuery) => ["kpi", "action-panel", q] as const,
  expiring: (pid: string, asOf: string | null | undefined) => ["kpi", "expiring", pid, asOf ?? null] as const,
  insights: (q: KpiQuery) => ["kpi", "insights", q] as const,
  prefs: ["dashboard-preferences"] as const,
};

export function useKpiCatalogue() {
  return useQuery({
    queryKey: kk.catalogue,
    queryFn: () => unwrap(api.GET("/api/v1/kpi/catalogue")),
    staleTime: 10 * 60_000,
  });
}

export function useDashboard(q: KpiQuery, enabled = true) {
  return useQuery({
    queryKey: kk.dashboard(q),
    queryFn: () => unwrap(api.GET("/api/v1/kpi/dashboard", { params: { query: q } })),
    enabled,
    staleTime: STALE,
    placeholderData: keepPreviousData,
  });
}

export function useChart(
  id: Schemas["ChartId"],
  q: KpiQuery,
  extra: {
    dimension?: Schemas["BreakdownDimension"] | null;
    measure?: Schemas["BreakdownMeasure"] | null;
  } = {},
  enabled = true,
) {
  return useQuery({
    queryKey: kk.chart(id, q, extra),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/kpi/charts/{chart_id}", {
          params: { path: { chart_id: id }, query: { ...q, ...extra } },
        }),
      ),
    enabled,
    staleTime: STALE,
    placeholderData: keepPreviousData,
  });
}

export function usePyramid(q: KpiQuery, enabled = true) {
  return useQuery({
    queryKey: kk.pyramid(q),
    queryFn: () => unwrap(api.GET("/api/v1/kpi/pyramid", { params: { query: q } })),
    enabled,
    staleTime: STALE,
    placeholderData: keepPreviousData,
  });
}

export function useContractorLeague(q: KpiQuery, rollup: boolean, enabled = true) {
  return useQuery({
    queryKey: kk.league(q, rollup),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/kpi/contractors", {
          params: { query: { ...q, rollup } },
        }),
      ),
    enabled,
    staleTime: STALE,
    placeholderData: keepPreviousData,
  });
}

export function useKpi(metric: Schemas["KpiMetric"] | null, q: KpiQuery) {
  return useQuery({
    queryKey: kk.metric(metric ?? "", q),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/kpi/metrics/{metric}", {
          params: {
            path: { metric: metric as Schemas["KpiMetric"] },
            query: { ...q, source_limit: 0 },
          },
        }),
      ),
    enabled: Boolean(metric),
    staleTime: STALE,
  });
}

export function useKpiSources(metric: Schemas["KpiMetric"] | null, part: "numerator" | "denominator", page: number, q: KpiQuery) {
  return useQuery({
    queryKey: kk.sources(metric ?? "", part, page, q),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/kpi/metrics/{metric}/sources", {
          params: {
            path: { metric: metric as Schemas["KpiMetric"] },
            query: { ...q, part, page, page_size: 25 },
          },
        }),
      ),
    enabled: Boolean(metric),
    staleTime: STALE,
    placeholderData: keepPreviousData,
  });
}

export function useActionPanel(q: KpiQuery, enabled = true) {
  return useQuery({
    queryKey: kk.actionPanel(q),
    queryFn: () => unwrap(api.GET("/api/v1/dashboard/action-panel", { params: { query: q } })),
    enabled,
    staleTime: STALE,
  });
}

export function useExpiringItems(pid: string | null, asOf: string | null | undefined, withinDays = 14) {
  return useQuery({
    queryKey: kk.expiring(pid ?? "", asOf),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/dashboard/expiring-items", {
          params: {
            query: {
              project_id: pid ?? "",
              as_of: asOf ?? null,
              within_days: withinDays,
            },
          },
        }),
      ),
    enabled: Boolean(pid),
    staleTime: STALE,
  });
}

export function useInsights(q: KpiQuery, enabled: boolean) {
  return useQuery({
    queryKey: kk.insights(q),
    queryFn: () => unwrap(api.GET("/api/v1/ai/insights", { params: { query: q } })),
    enabled,
    staleTime: 5 * 60_000,
    retry: false,
  });
}

export function useDashboardPrefs() {
  return useQuery({
    queryKey: kk.prefs,
    queryFn: () => unwrap(api.GET("/api/v1/dashboard/preferences")),
    staleTime: Infinity,
    retry: false,
  });
}
