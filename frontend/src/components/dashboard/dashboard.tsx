"use client";
import { useMutation } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { ChartRenderer } from "@/components/charts/chart-renderer";
import { AiAssistant } from "@/components/ai/ai-panel";
import { PageHeader } from "@/components/common/page-header";
import { ErrorState, LoadingState } from "@/components/common/states";
import { useMeData } from "@/components/shell/me-context";
import { api, downloadFile, unwrap, type Schemas } from "@/lib/api/client";
import { useAiStatus } from "@/lib/api/ai";
import { useChart, useDashboard, useDashboardPrefs, type KpiQuery } from "@/lib/api/kpi";
import { useCurrentProject } from "@/lib/current-project";
import { fromPreferences, toKpiQuery, toPreferences, useDashFilters } from "@/lib/dashboard-filters";
import { useArabicDigits, useDisplay } from "@/lib/digits";
import { useErrorMessage, useLocalizedName } from "@/lib/i18n-helpers";
import { can } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { toQueryString } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { DrillNumber, DrillProvider, useDrill } from "./drill";
import { FilterBar } from "./filter-bar";
import { HeadlineValue, KpiTile } from "./kpi-tile";
import { ActionPanel, ExpiringItems, InsightsPanel, LeagueTable, Panel, SafetyPyramid } from "./panels";

type Show = (v: string | number | null | undefined) => string;

/** §8.1 C7 dimensions; trade / age band / nationality need capability "breakdown.sensitive_view". */
const C7_DIMENSIONS: Schemas["BreakdownDimension"][] = [
  "mechanism",
  "agency",
  "body_part",
  "nature",
  "activity",
  "root_cause_code",
  "site",
  "zone",
  "zone_type",
  "shift",
  "hour_band",
  "weekday",
  "days_on_site_band",
];
const SENSITIVE_DIMENSIONS: Schemas["BreakdownDimension"][] = ["trade", "age_band", "nationality"];
const C7_MEASURES: Schemas["BreakdownMeasure"][] = ["injury_cases", "recordable_cases", "events_by_type", "unsafe_observations"];
const METRIC_RE = /^K-\d{2}$/;
const MONTH_RE = /^\d{4}-\d{2}(-\d{2})?$/;

/** Home page for users with capability 38 (dashboard.view). */
export function Dashboard() {
  const t = useTranslations("dashboard");
  const th = useTranslations("home");
  const me = useMeData();
  const name = useLocalizedName();
  const { project, isLoading } = useCurrentProject();
  const { filters, set, hasAny } = useDashFilters();
  const pid = project?.id ?? null;
  const query = useMemo(() => toKpiQuery(pid, filters), [pid, filters]);
  usePreferenceSync(pid, filters, set, hasAny);

  return (
    <div data-testid="home" className="flex flex-col gap-4">
      <PageHeader
        title={th("welcome", { name: name(me.full_name_en, me.full_name_ar) })}
        description={project ? `${t("title")} · ${project.code}` : t("title")}
        actions={pid && !filters.allProjects ? <AiAssistant projectId={pid} filters={toPreferences(pid, filters)} /> : null}
      />
      {isLoading ? (
        <LoadingState />
      ) : !pid && !filters.allProjects ? (
        <Alert tone="info">{t("noProject")}</Alert>
      ) : (
        <DrillProvider query={query} projectId={pid}>
          <DashboardBody query={query} projectId={pid} />
        </DrillProvider>
      )}
    </div>
  );
}

/**
 * Filters persist per user (PUT /dashboard/preferences). A link with filters in the URL wins;
 * with none, the saved filters are applied once.
 */
function usePreferenceSync(pid: string | null, filters: ReturnType<typeof useDashFilters>["filters"], set: ReturnType<typeof useDashFilters>["set"], hasAny: boolean) {
  const prefs = useDashboardPrefs();
  const applied = useRef(false);
  const save = useMutation({
    mutationFn: (body: Schemas["DashboardFilters"]) => unwrap(api.PUT("/api/v1/dashboard/preferences", { body })),
  });
  const { mutate } = save;
  useEffect(() => {
    if (applied.current || !prefs.isFetched) return;
    applied.current = true;
    const saved = prefs.data?.filters;
    if (!hasAny && saved && (!saved.project_id || saved.project_id === pid)) set(fromPreferences(saved), { resetPage: false });
  }, [prefs.isFetched, prefs.data, hasAny, pid, set]);
  const key = JSON.stringify(toPreferences(pid, filters));
  useEffect(() => {
    if (!applied.current) return;
    const h = window.setTimeout(() => mutate(JSON.parse(key) as Schemas["DashboardFilters"]), 800);
    return () => window.clearTimeout(h);
  }, [key, mutate]);
}

function DashboardBody({ query, projectId }: { query: KpiQuery; projectId: string | null }) {
  const t = useTranslations("dashboard");
  const locale = useLocale();
  const me = useMeData();
  const show = useDisplay(projectId);
  const { filters, set } = useDashFilters();
  const d = useDashboard(query);
  const ai = useAiStatus(projectId, !filters.allProjects);
  const aiInsights = Boolean(ai.data?.enabled && ai.data.available);
  const canExport = can(me, "export.kpis", projectId);

  return (
    <>
      <FilterBar projectId={projectId ?? ""} filters={filters} set={set} context={d.data?.context} />
      {d.isError ? (
        <ErrorState error={d.error} onRetry={() => d.refetch()} />
      ) : !d.data ? (
        <LoadingState rows={6} />
      ) : (
        <div className={cn("flex flex-col gap-4 transition-opacity", d.isPlaceholderData && "opacity-60")} aria-busy={d.isFetching}>
          <ContextBar ctx={d.data.context} show={show} projectId={projectId} />
          <Headline h={d.data.headline} show={show} projectId={projectId} periodLabel={locale === "ar" ? d.data.context.period.label_ar : d.data.context.period.label_en} />
          <section aria-labelledby="lagging-h">
            <h2 id="lagging-h" className="mb-2 text-sm font-semibold">
              {t("lagging")}
            </h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5" data-testid="lagging-tiles">
              {d.data.lagging.map((tile) => (
                <KpiTile key={tile.metric} tile={tile} show={show} />
              ))}
            </div>
          </section>
          <section aria-labelledby="leading-h">
            <h2 id="leading-h" className="mb-2 text-sm font-semibold">
              {t("leading")}
            </h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5" data-testid="leading-tiles">
              {d.data.leading.map((tile) => (
                <KpiTile key={tile.metric} tile={tile} show={show} />
              ))}
              {d.data.placeholders.map((p) => (
                <Placeholder key={p.metric} p={p} />
              ))}
            </div>
          </section>
          <div className="grid gap-4 lg:grid-cols-3">
            <Panel title={t("actionPanel")} testId="action-panel-card" className="lg:col-span-2">
              <ActionPanel query={query} show={show} />
            </Panel>
            <Panel title={t("expiring")} testId="expiring-card">
              <ExpiringItems projectId={filters.allProjects ? null : projectId} asOf={filters.asOf} show={show} />
            </Panel>
          </div>
          <Charts query={query} projectId={projectId} show={show} />
          <div className="grid gap-4 lg:grid-cols-3">
            <Panel title={t("pyramid")} testId="pyramid-card">
              <SafetyPyramid query={query} show={show} />
            </Panel>
            <Panel
              title={t("league")}
              testId="league-card"
              className="lg:col-span-2"
              actions={canExport ? <ExportButton table="contractors" query={query} label={t("exportContractors")} /> : null}
            >
              <LeagueTable query={query} show={show} />
            </Panel>
          </div>
          <Panel title={t("insights")} testId="insights-card">
            {!aiInsights && ai.data ? <p className="mb-2 text-xs text-muted-foreground">{t("insightsAiOff")}</p> : null}
            <InsightsPanel query={query} enabled={!filters.allProjects} show={show} />
          </Panel>
          {canExport ? (
            <div className="flex flex-wrap gap-2 print:hidden" data-testid="dashboard-export">
              <ExportButton table="metrics" query={query} label={t("exportMetrics")} />
              <ExportButton table="comparisons" query={query} label={t("exportComparisons")} />
            </div>
          ) : null}
        </div>
      )}
    </>
  );
}

function ContextBar({ ctx, show, projectId }: { ctx: Schemas["KpiContext"]; show: Show; projectId: string | null }) {
  const t = useTranslations("dashboard");
  const locale = useLocale();
  const ar = locale === "ar";
  const { dateTime } = useFormatters(projectId);
  const shown = new Set<string>();
  return (
    <div className="flex flex-col gap-2" data-testid="dashboard-context">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded-full border px-2.5 py-1 font-medium" data-testid="period-label">
          {ar ? ctx.period.label_ar : ctx.period.label_en}
        </span>
        <span
          className={cn("rounded-full border px-2.5 py-1", ctx.completeness_below_threshold ? "border-warning/50 bg-warning-bg text-foreground" : "text-muted-foreground")}
          data-testid="chip-completeness"
          data-below={ctx.completeness_below_threshold}
        >
          {t("completeness", { value: show(ctx.data_completeness_display) })}
        </span>
        {ctx.provisional_cases_count > 0 ? (
          <span className="rounded-full border border-info/40 bg-info-bg px-2.5 py-1" data-testid="chip-provisional">
            {t("provisional", { count: show(ctx.provisional_cases_count) })}
          </span>
        ) : null}
        {ctx.restated ? (
          <span className="rounded-full border border-warning/50 bg-warning-bg px-2.5 py-1" data-testid="chip-restated">
            {t("restated", { months: show(ctx.restated_months.join(", ")) })}
          </span>
        ) : null}
        <span className="text-muted-foreground">{t("computedAt", { time: dateTime(ctx.computed_at) })}</span>
      </div>
      {ctx.banners.map((b) => {
        if (shown.has(b.code)) return null;
        shown.add(b.code);
        return (
          <Alert key={b.code} tone={b.severity === "critical" ? "danger" : b.severity === "warning" ? "warning" : "info"} data-testid="dashboard-banner" data-code={b.code}>
            {show(ar ? b.message_ar : b.message_en)}
          </Alert>
        );
      })}
      {ctx.filters.scope_narrowed || (ctx.filters.engagement_ids.length === 0 && ctx.filters.effective_engagement_ids !== null) ? (
        <Alert tone="info" data-testid="banner-scope">
          {t("scopeNarrowed")}
        </Alert>
      ) : null}
      {ctx.bases.mixed_projects && !shown.has("MIXED_BASES") ? (
        <Alert tone="info" data-testid="banner-mixed">
          {t("mixedBases")}
        </Alert>
      ) : null}
    </div>
  );
}

function Headline({ h, show, projectId, periodLabel }: { h: Schemas["DashboardHeadline"]; show: Show; projectId: string | null; periodLabel: string }) {
  const t = useTranslations("dashboard");
  const ar = useLocale() === "ar";
  const { date } = useFormatters(projectId);
  const l = h.lti_free;
  return (
    <section aria-label={t("headline")} className="grid gap-3 rounded-xl border bg-surface p-4 shadow-xs sm:grid-cols-2 lg:grid-cols-6" data-testid="headline">
      <div className="flex flex-col gap-1 lg:col-span-2" data-testid="lti-free">
        <p className="text-xs font-medium text-muted-foreground">{ar ? l.label_ar : l.label_en}</p>
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <DrillNumber metric="K-28" label={t("ltiFree")} className="text-3xl font-semibold text-success">
            <span data-testid="lti-free-days">{show(l.days_display)}</span>
            <span className="ms-1 text-sm font-normal text-muted-foreground">{t("days")}</span>
          </DrillNumber>
          <DrillNumber metric="K-29" label={t("ltiFreeHours")} className="text-lg font-semibold">
            <span data-testid="lti-free-hours">{show(l.man_hours_display)}</span>
            <span className="ms-1 text-xs font-normal text-muted-foreground">{t("hours")}</span>
          </DrillNumber>
        </div>
        <p className="text-xs text-muted-foreground">
          {l.basis === "since_start" ? t("sinceStart") : t("lastLti", { date: date(l.last_lti_date) })}
          {l.last_lti_incident_ref ? <span className="ltr ms-1">({l.last_lti_incident_ref})</span> : null}
          {l.longest_run_days > 0 ? <span className="ms-2">· {t("longestRun", { days: show(l.longest_run_days) })}</span> : null}
        </p>
      </div>
      <HeadlineValue v={h.man_hours_period} show={show} big caption={periodLabel} />
      <HeadlineValue v={h.man_hours_itd} show={show} caption={t("sinceStart")} />
      <HeadlineValue v={h.average_headcount} show={show} />
      <div className="flex flex-col gap-3">
        <HeadlineValue v={h.peak_headcount} show={show} />
        <HeadlineValue v={h.direct_sub_split} show={show} />
      </div>
    </section>
  );
}

function Placeholder({ p }: { p: Schemas["KpiPlaceholder"] }) {
  const ar = useLocale() === "ar";
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-dashed p-3 text-muted-foreground" data-testid="kpi-placeholder" data-metric={p.metric}>
      <p className="text-xs font-medium">{ar ? p.label_ar : p.label_en}</p>
      <p className="text-sm">{ar ? p.message_ar : p.message_en}</p>
    </div>
  );
}

function Charts({ query, projectId, show }: { query: KpiQuery; projectId: string | null; show: Show }) {
  const t = useTranslations("dashboard");
  const te = useTranslations("enums");
  const me = useMeData();
  const s = useDashFilters().search;
  const dims = can(me, "breakdown.sensitive_view", projectId) ? [...C7_DIMENSIONS, ...SENSITIVE_DIMENSIONS] : C7_DIMENSIONS;
  const dim = (dims.includes(s.get("c7d") as Schemas["BreakdownDimension"]) ? s.get("c7d") : "mechanism") as Schemas["BreakdownDimension"];
  const measure = (C7_MEASURES.includes(s.get("c7m") as Schemas["BreakdownMeasure"]) ? s.get("c7m") : "injury_cases") as Schemas["BreakdownMeasure"];
  return (
    <section aria-labelledby="charts-h" className="flex flex-col gap-3">
      <h2 id="charts-h" className="text-sm font-semibold">
        {t("charts")}
      </h2>
      <div className="grid gap-4 lg:grid-cols-2">
        {(["C1", "C2", "C3", "C5", "C8", "C9"] as const).map((id) => (
          <ChartCard key={id} id={id} query={query} projectId={projectId} show={show} />
        ))}
        <ChartCard
          id="C7"
          query={query}
          projectId={projectId}
          show={show}
          extra={{ dimension: dim, measure }}
          className="lg:col-span-2"
          controls={
            <div className="flex flex-wrap gap-2">
              <div className="flex flex-col gap-1">
                <Label htmlFor="c7-dim" className="text-xs">
                  {t("dimension")}
                </Label>
                <Select
                  id="c7-dim"
                  value={dim}
                  onChange={(e) =>
                    s.set(
                      {
                        c7d: e.target.value === "mechanism" ? null : e.target.value,
                      },
                      { resetPage: false },
                    )
                  }
                  data-testid="c7-dimension"
                >
                  {dims.map((x) => (
                    <option key={x} value={x}>
                      {te(`dimension.${x}`)}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="c7-measure" className="text-xs">
                  {t("measure")}
                </Label>
                <Select
                  id="c7-measure"
                  value={measure}
                  onChange={(e) =>
                    s.set(
                      {
                        c7m: e.target.value === "injury_cases" ? null : e.target.value,
                      },
                      { resetPage: false },
                    )
                  }
                  data-testid="c7-measure"
                >
                  {C7_MEASURES.map((x) => (
                    <option key={x} value={x}>
                      {te(`measure.${x}`)}
                    </option>
                  ))}
                </Select>
              </div>
            </div>
          }
        />
      </div>
    </section>
  );
}

/** Month key → the month's dates (drill into one bar of a monthly chart). */
function monthOverride(x: string): Partial<KpiQuery> | null {
  if (!MONTH_RE.test(x)) return null;
  const [y, m] = x.split("-").map(Number);
  const start = new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, 1));
  const end = new Date(Date.UTC(y ?? 1970, m ?? 1, 0));
  return {
    period: "custom",
    anchor: null,
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  };
}

function ChartCard({
  id,
  query,
  projectId,
  show,
  extra,
  controls,
  className,
}: {
  id: Schemas["ChartId"];
  query: KpiQuery;
  projectId: string | null;
  show: Show;
  extra?: {
    dimension?: Schemas["BreakdownDimension"];
    measure?: Schemas["BreakdownMeasure"];
  };
  controls?: ReactNode;
  className?: string;
}) {
  const ar = useLocale() === "ar";
  const digits = useArabicDigits(projectId);
  const { open } = useDrill();
  const q = useChart(id, query, extra ?? {});
  const spec = q.data?.chart;
  return (
    <div className={cn("min-w-0 rounded-xl border bg-surface p-3 shadow-xs", className)} data-testid={`chart-card-${id}`}>
      {q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : !spec ? (
        <LoadingState rows={3} />
      ) : (
        <>
          <ChartRenderer
            spec={spec}
            arabicDigits={digits}
            actions={controls}
            onPointClick={(seriesKey, x) => {
              if (!METRIC_RE.test(seriesKey)) return;
              const series = spec.series.find((s) => s.key === seriesKey);
              const label = series ? (ar ? series.label_ar : series.label_en) : seriesKey;
              open(seriesKey as Schemas["KpiMetric"], `${label} · ${show(x)}`, monthOverride(x) ?? {});
            }}
          />
        </>
      )}
    </div>
  );
}

function ExportButton({ table, query, label }: { table: Schemas["KpiExportTable"]; query: KpiQuery; label: string }) {
  const t = useTranslations("export");
  const msg = useErrorMessage();
  const [busy, setBusy] = useState(false);
  async function run() {
    setBusy(true);
    try {
      const qs = toQueryString({
        format: "csv",
        project_id: query.project_id ?? undefined,
        all_projects: query.all_projects ? "true" : undefined,
        site_id: query.site_id ?? undefined,
        zone_id: query.zone_id ?? undefined,
        zone_type: query.zone_type ?? undefined,
        engagement_id: query.engagement_id ?? undefined,
        include_subcontractors: query.include_subcontractors === false ? "false" : undefined,
        tier: query.tier?.map(String) ?? undefined,
        period: query.period ?? undefined,
        anchor: query.anchor ?? undefined,
        start: query.start ?? undefined,
        end: query.end ?? undefined,
        as_of: query.as_of ?? undefined,
        compare: query.compare ?? undefined,
      });
      await downloadFile(`/api/v1/kpi/export/${table}${qs}`, `${table}.csv`);
      toast.success(t("done"));
    } catch (e) {
      toast.error(`${t("failed")}: ${msg(e)}`);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Button size="sm" variant="outline" onClick={() => void run()} disabled={busy} data-testid={`export-kpi-${table}`}>
      <Download aria-hidden />
      {label}
    </Button>
  );
}
