"use client";
import { AlertTriangle, ArrowDownUp, BarChart3, CalendarClock, CheckCircle2, ChevronRight, Info, Lightbulb, OctagonAlert, RefreshCw, Table2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { ErrorState, LoadingState } from "@/components/common/states";
import { ChartRenderer } from "@/components/charts/chart-renderer";
import { Link } from "@/i18n/navigation";
import type { Schemas } from "@/lib/api/client";
import { useActionPanel, useContractorLeague, useExpiringItems, useInsights, usePyramid, type KpiQuery } from "@/lib/api/kpi";
import { useArabicDigits } from "@/lib/digits";
import { apiPathToRoute, entityRoute, listLinkToRoute } from "@/lib/routes";
import { useFormatters } from "@/lib/use-formatters";
import { cn } from "@/lib/utils";
import { DrillNumber } from "./drill";

type Show = (v: string | number | null | undefined) => string;

const PYRAMID_METRIC: Record<Schemas["PyramidLayer"], Schemas["KpiMetric"]> = {
  FAT: "K-05",
  LTI: "K-06",
  RWC_JTC: "K-07",
  MTC: "K-09",
  FAC: "K-12",
  NM: "K-13",
  UNSAFE_OBS: "K-30",
};

/** Ordinal ramp for the pyramid: one hue, darkest at the most severe layer (never a rainbow). */
const PYRAMID_SHADE = [100, 88, 76, 64, 52, 42, 34];

/**
 * C4: layers stacked as centred bars, most severe at the top; width ∝ log(count) so small top layers stay
 * visible. Counts sit beside the bar in text colour (readable in both themes); the table view lists ratios.
 */
export function SafetyPyramid({ query, show }: { query: KpiQuery; show: Show }) {
  const t = useTranslations("dashboard");
  const ar = useLocale() === "ar";
  const q = usePyramid(query);
  const [table, setTable] = useState(false);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const layers = q.data.layers;
  const max = Math.max(1, ...layers.map((l) => l.count));
  const w = (n: number) => (n <= 0 ? 4 : 12 + 88 * (Math.log10(n + 1) / Math.log10(max + 1)));
  return (
    <div className="flex flex-col gap-2" data-testid="pyramid">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">{t("pyramidTri", { n: show(q.data.tri) })}</p>
        <Button size="sm" variant="ghost" onClick={() => setTable(!table)} aria-pressed={table}>
          {table ? <BarChart3 aria-hidden /> : <Table2 aria-hidden />}
          {table ? t("chart") : t("table")}
        </Button>
      </div>
      {table ? (
        <table className="w-full text-sm">
          <tbody>
            {layers.map((l) => (
              <tr key={l.layer} className="border-b last:border-0">
                <th scope="row" className="py-1.5 text-start font-normal">
                  {ar ? l.label_ar : l.label_en}
                </th>
                <td className="py-1.5 text-end tabular-nums">{show(l.count)}</td>
                <td className="py-1.5 text-end text-muted-foreground tabular-nums">{show(l.ratio_display)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <ol className="flex flex-col gap-0.5">
          {layers.map((l, i) => (
            <li key={l.layer} data-testid="pyramid-layer" data-layer={l.layer}>
              <DrillNumber
                metric={PYRAMID_METRIC[l.layer]}
                label={ar ? l.label_ar : l.label_en}
                className="grid min-h-9 w-full grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)_2.75rem] items-center gap-2 px-1 hover:bg-accent/50 hover:no-underline"
              >
                <span className="min-w-0 text-xs leading-tight">
                  <span className="block text-foreground">{ar ? l.label_ar : l.label_en}</span>
                  {l.ratio_to_tri !== null ? (
                    <span className="block text-muted-foreground">
                      {show(l.ratio_display)} {t("ratioToTri")}
                    </span>
                  ) : null}
                </span>
                <span className="flex justify-center">
                  <span
                    aria-hidden
                    className="block h-6 rounded-[3px]"
                    style={{
                      width: `${w(l.count)}%`,
                      background: `color-mix(in oklab, var(--series-1) ${PYRAMID_SHADE[i] ?? 34}%, var(--surface))`,
                    }}
                  />
                </span>
                <span className="text-end text-sm font-semibold tabular-nums">{show(l.count)}</span>
              </DrillNumber>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

type ColKey = "man_hours" | "tri" | "trir" | "ltifr" | "lti_free_days" | "near_misses" | "unsafe_observations" | "ca_on_time_pct" | "overdue_cas";
const LEAGUE_COLS: { key: ColKey; metric: Schemas["KpiMetric"] }[] = [
  { key: "man_hours", metric: "K-01" },
  { key: "tri", metric: "K-10" },
  { key: "trir", metric: "K-21" },
  { key: "ltifr", metric: "K-20" },
  { key: "lti_free_days", metric: "K-28" },
  { key: "near_misses", metric: "K-13" },
  { key: "unsafe_observations", metric: "K-30" },
  { key: "ca_on_time_pct", metric: "K-41" },
  { key: "overdue_cas", metric: "K-42" },
];

/** C6 league table: sortable, every cell drills down with that contractor as the filter. */
export function LeagueTable({ query, show }: { query: KpiQuery; show: Show }) {
  const t = useTranslations("dashboard");
  const [rollup, setRollup] = useState(false);
  const [sort, setSort] = useState<{ key: ColKey | "engagement"; dir: 1 | -1 }>({ key: "man_hours", dir: -1 });
  const q = useContractorLeague(query, rollup);
  const rows = useMemo(() => {
    const list = [...(q.data?.rows ?? [])];
    list.sort((a, b) => {
      if (sort.key === "engagement") return a.engagement.short_code.localeCompare(b.engagement.short_code) * sort.dir;
      const av = a[sort.key].value === null ? Number.NEGATIVE_INFINITY : Number(a[sort.key].value);
      const bv = b[sort.key].value === null ? Number.NEGATIVE_INFINITY : Number(b[sort.key].value);
      return (av - bv) * sort.dir;
    });
    return list;
  }, [q.data, sort]);
  const head = (key: ColKey | "engagement", label: string, numeric: boolean) => (
    <th
      key={key}
      className={cn("px-2 py-1.5 font-medium whitespace-nowrap", numeric ? "text-end" : "text-start")}
      aria-sort={sort.key === key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
    >
      <button
        type="button"
        className="inline-flex min-h-touch items-center gap-1 hover:text-foreground"
        onClick={() => setSort({ key, dir: sort.key === key ? (-sort.dir as 1 | -1) : -1 })}
        aria-label={t("sortBy", { col: label })}
      >
        {label}
        <ArrowDownUp aria-hidden className="size-3" />
      </button>
    </th>
  );
  return (
    <div className="flex flex-col gap-2" data-testid="league-table">
      <label className="flex min-h-touch items-center gap-2 text-sm">
        <Checkbox checked={rollup} onChange={(e) => setRollup(e.target.checked)} />
        {t("rollup")}
      </label>
      {q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : !q.data ? (
        <LoadingState />
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("noData")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-xs text-muted-foreground">
                {head("engagement", t("league_cols.engagement"), false)}
                <th className="px-2 py-1.5 text-start font-medium">{t("league_cols.tier")}</th>
                {LEAGUE_COLS.map((c) => head(c.key, t(`league_cols.${c.key}`), true))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.engagement.id} className="border-b last:border-0" data-testid="league-row" data-code={r.engagement.short_code}>
                  <th scope="row" className="px-2 py-1.5 text-start font-medium whitespace-nowrap">
                    <span className="ltr">{r.engagement.short_code}</span>
                    {r.low_exposure ? <span className="ms-2 rounded bg-muted px-1.5 py-0.5 text-[11px] font-normal whitespace-nowrap text-muted-foreground">{t("lowExposure")}</span> : null}
                  </th>
                  <td className="px-2 py-1.5 tabular-nums">{show(r.engagement.tier)}</td>
                  {LEAGUE_COLS.map((c) => (
                    <td key={c.key} className="px-2 py-1.5 text-end tabular-nums">
                      <DrillNumber
                        metric={c.metric}
                        label={`${t(`league_cols.${c.key}`)} · ${r.engagement.short_code}`}
                        override={{
                          engagement_id: [r.engagement.id],
                          include_subcontractors: rollup,
                        }}
                        className="tabular-nums"
                      >
                        {show(r[c.key].display)}
                      </DrillNumber>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const SEV_ICON = {
  info: Info,
  warning: AlertTriangle,
  critical: OctagonAlert,
} as const;
const SEV_CLASS = {
  info: "text-info",
  warning: "text-warning",
  critical: "text-danger",
} as const;

export function ActionPanel({ query, show }: { query: KpiQuery; show: Show }) {
  const t = useTranslations("dashboard");
  const te = useTranslations("enums");
  const ar = useLocale() === "ar";
  // The action panel is per project (the API refuses all_projects).
  const single = !query.all_projects && (query.project_id?.length ?? 0) === 1;
  const q = useActionPanel(query, single);
  if (!single)
    return (
      <p className="text-sm text-muted-foreground" data-testid="action-panel-one-project">
        {t("actionPanelOneProject")}
      </p>
    );
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const items = q.data.items.filter((i) => i.count > 0);
  if (items.length === 0)
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground" data-testid="action-panel-empty">
        <CheckCircle2 aria-hidden className="size-4 text-success" />
        {t("allClear")}
      </p>
    );
  return (
    <ul className="flex flex-col divide-y" data-testid="action-panel">
      {items.map((i) => {
        const Icon = SEV_ICON[i.severity];
        const href = listLinkToRoute(i.link);
        const body = (
          <>
            <span className="flex min-w-0 items-start gap-2">
              <Icon aria-hidden className={cn("mt-0.5 size-4 shrink-0", SEV_CLASS[i.severity])} />
              <span className="min-w-0">
                <span className="sr-only">{te(`severity.${i.severity}`)}: </span>
                {ar ? i.label_ar : i.label_en}
                {i.by_contractor.length > 0 ? (
                  <span className="block text-xs text-muted-foreground">
                    {i.by_contractor
                      .slice(0, 4)
                      .map((b) => `${b.engagement.short_code} ${show(b.count)}`)
                      .join(" · ")}
                  </span>
                ) : null}
              </span>
            </span>
            <span className="inline-flex shrink-0 items-center gap-1">
              <span className="text-lg font-semibold tabular-nums" data-testid="action-count">
                {show(i.count)}
              </span>
              {href ? <ChevronRight aria-hidden className="size-4 text-muted-foreground rtl:-scale-x-100" /> : <span aria-hidden className="size-4" />}
            </span>
          </>
        );
        return (
          <li key={i.key} data-testid="action-item" data-key={i.key}>
            {href ? (
              <Link href={href} className="-mx-2 flex min-h-touch items-center justify-between gap-3 rounded-md px-2 py-2 text-sm hover:bg-accent/60">
                {body}
              </Link>
            ) : (
              <div className="-mx-2 flex min-h-touch items-center justify-between gap-3 px-2 py-2 text-sm">{body}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

const LIST_PREVIEW = 6;

export function ExpiringItems({ projectId, asOf, show }: { projectId: string | null; asOf: string | null; show: Show }) {
  const t = useTranslations("dashboard");
  const te = useTranslations("enums");
  const ar = useLocale() === "ar";
  const { date } = useFormatters(projectId);
  const q = useExpiringItems(projectId, asOf);
  const [all, setAll] = useState(false);
  if (!projectId) return null;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  if (q.data.items.length === 0)
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <CheckCircle2 aria-hidden className="size-4 text-success" />
        {t("allClear")}
      </p>
    );
  const items = q.data.items.slice(0, 12);
  const visible = all ? items : items.slice(0, LIST_PREVIEW);
  return (
    <div className="flex flex-col gap-1">
      <ul className="flex flex-col divide-y" data-testid="expiring-items">
        {visible.map((i, idx) => {
          const href = apiPathToRoute(i.detail_path) ?? entityRoute(i.entity_type, i.entity_id, projectId);
          const overdue = i.days_left < 0;
          const soon = !overdue && i.days_left <= 2;
          const when = overdue ? t("daysOverdue", { days: show(-i.days_left) }) : i.days_left === 0 ? t("dueToday") : t("daysLeft", { days: show(i.days_left), n: i.days_left });
          const content = (
            <>
              <span className="min-w-0">
                <span className="block text-xs text-muted-foreground">
                  {te(`expiringKind.${i.kind}`)}
                  {i.ref ? (
                    <>
                      {" · "}
                      <bdi className="ltr whitespace-nowrap">{i.ref}</bdi>
                    </>
                  ) : null}
                </span>
                <span className="line-clamp-2 [overflow-wrap:anywhere]">{ar ? i.title_ar : i.title_en}</span>
              </span>
              <span className="flex shrink-0 flex-col items-end gap-0.5 text-end text-xs">
                <span
                  className={cn(
                    "inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-medium whitespace-nowrap",
                    overdue ? "bg-danger-bg text-danger" : soon ? "bg-warning-bg text-warning" : "text-muted-foreground",
                  )}
                  data-state={overdue ? "overdue" : soon ? "soon" : "ok"}
                >
                  {overdue ? <AlertTriangle aria-hidden className="size-3.5" /> : <CalendarClock aria-hidden className="size-3.5" />}
                  {when}
                </span>
                <span className="text-muted-foreground">{date(i.due_date)}</span>
              </span>
            </>
          );
          return (
            <li key={`${i.kind}-${i.entity_id ?? idx}`} data-testid="expiring-item">
              {href ? (
                <Link href={href} className="-mx-2 flex min-h-touch items-center justify-between gap-3 rounded-md px-2 py-2 text-sm hover:bg-accent/60">
                  {content}
                </Link>
              ) : (
                <div className="-mx-2 flex min-h-touch items-center justify-between gap-3 px-2 py-2 text-sm">{content}</div>
              )}
            </li>
          );
        })}
      </ul>
      {items.length > LIST_PREVIEW ? (
        <Button size="sm" variant="ghost" className="self-start" onClick={() => setAll(!all)} aria-expanded={all}>
          {all ? t("showLess") : t("showAll", { count: show(items.length) })}
        </Button>
      ) : null}
    </div>
  );
}

export function InsightsPanel({ query, enabled, show }: { query: KpiQuery; enabled: boolean; show: Show }) {
  const t = useTranslations("dashboard");
  const te = useTranslations("enums");
  const ar = useLocale() === "ar";
  const digits = useArabicDigits();
  const q = useInsights(query, enabled);
  const [all, setAll] = useState(false);
  if (!enabled) return null;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const items = q.data.items;
  const visible = all ? items : items.slice(0, LIST_PREVIEW);
  return (
    <div className="flex flex-col gap-2" data-testid="insights">
      {!q.data.ai_available ? <p className="text-xs text-muted-foreground">{t("insightsAiOff")}</p> : null}
      {items.length === 0 ? <p className="text-sm text-muted-foreground">{t("noData")}</p> : null}
      <div className="flex flex-col divide-y">
        {visible.map((i) => {
          const Icon = i.kind === "positive" ? Lightbulb : SEV_ICON[i.severity];
          return (
            <article key={i.id} className="flex gap-2.5 py-2.5" data-testid="insight" data-source={i.source}>
              <Icon aria-hidden className={cn("mt-0.5 size-4 shrink-0", i.kind === "positive" ? "text-success" : SEV_CLASS[i.severity])} />
              <div className="min-w-0 flex-1">
                <header className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <h3 className="text-sm font-semibold">{ar ? i.title_ar : i.title_en}</h3>
                  <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                    {te(`insightKind.${i.kind}`)} · {te(`insightSource.${i.source}`)}
                  </span>
                </header>
                <p className="mt-0.5 text-sm whitespace-pre-wrap">{show(ar ? i.text_ar : i.text_en)}</p>
                {i.chart ? (
                  <div className="mt-2">
                    <ChartRenderer spec={i.chart} height={180} arabicDigits={digits} />
                  </div>
                ) : null}
                {i.citations.length > 0 ? <p className="mt-1 text-[11px] text-muted-foreground">{i.citations.map((c) => show(ar ? c.text_ar : c.text_en)).join(" · ")}</p> : null}
              </div>
            </article>
          );
        })}
      </div>
      <div className="flex flex-wrap gap-2">
        {items.length > LIST_PREVIEW ? (
          <Button size="sm" variant="ghost" onClick={() => setAll(!all)} aria-expanded={all}>
            {all ? t("showLess") : t("showAll", { count: show(items.length) })}
          </Button>
        ) : null}
        <Button size="sm" variant="ghost" onClick={() => void q.refetch()} disabled={q.isFetching}>
          <RefreshCw aria-hidden />
          {t("refreshInsights")}
        </Button>
      </div>
    </div>
  );
}

export function Panel({ title, children, testId, className, actions }: { title: string; children: ReactNode; testId?: string; className?: string; actions?: ReactNode }) {
  return (
    <Card className={cn("min-w-0", className)} data-testid={testId}>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2 pb-2">
        <CardTitle className="text-base">{title}</CardTitle>
        {actions}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}
