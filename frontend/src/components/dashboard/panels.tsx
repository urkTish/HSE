"use client";
import { AlertTriangle, ArrowDownUp, CalendarClock, ChevronRight, Info, Lightbulb, OctagonAlert, RefreshCw } from "lucide-react";
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

/** C4: layers drawn as centred bars of equal height; width ∝ log(count) so small top layers stay visible. */
export function SafetyPyramid({ query, show }: { query: KpiQuery; show: Show }) {
  const t = useTranslations("dashboard");
  const ar = useLocale() === "ar";
  const q = usePyramid(query);
  const [table, setTable] = useState(false);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const layers = q.data.layers;
  const max = Math.max(1, ...layers.map((l) => l.count));
  const w = (n: number) => (n <= 0 ? 6 : 14 + 86 * (Math.log10(n + 1) / Math.log10(max + 1)));
  return (
    <div className="flex flex-col gap-2" data-testid="pyramid">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">{t("pyramidTri", { n: show(q.data.tri) })}</p>
        <Button size="sm" variant="ghost" onClick={() => setTable(!table)} aria-pressed={table}>
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
        <ol className="flex flex-col items-center gap-0.5">
          {layers.map((l, i) => (
            <li key={l.layer} className="grid w-full grid-cols-[1fr_auto] items-center gap-2" data-testid="pyramid-layer" data-layer={l.layer}>
              <div className="flex justify-center">
                <DrillNumber
                  metric={PYRAMID_METRIC[l.layer]}
                  label={ar ? l.label_ar : l.label_en}
                  className="flex h-8 items-center justify-center rounded-sm text-xs font-semibold text-white no-underline hover:opacity-90"
                >
                  <span
                    className="flex h-8 items-center justify-center rounded-sm px-2"
                    style={{
                      width: `${w(l.count)}%`,
                      minWidth: "3rem",
                      background: `var(--series-${(i % 8) + 1})`,
                    }}
                  >
                    <span className="rounded bg-black/35 px-1">{show(l.count)}</span>
                  </span>
                </DrillNumber>
              </div>
              <span className="w-40 text-xs text-muted-foreground">
                {ar ? l.label_ar : l.label_en}
                {l.ratio_to_tri !== null ? (
                  <span className="ms-1">
                    ({show(l.ratio_display)} {t("ratioToTri")})
                  </span>
                ) : null}
              </span>
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
                  <th scope="row" className="px-2 py-1.5 text-start font-medium">
                    <span className="ltr">{r.engagement.short_code}</span>
                    {r.low_exposure ? <span className="ms-2 rounded bg-muted px-1.5 py-0.5 text-[10px] font-normal text-muted-foreground">{t("lowExposure")}</span> : null}
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
  const q = useActionPanel(query);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const items = q.data.items.filter((i) => i.count > 0);
  if (items.length === 0)
    return (
      <p className="text-sm text-muted-foreground" data-testid="action-panel-empty">
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
            <span className="inline-flex items-center gap-1">
              <span className="text-lg font-semibold" data-testid="action-count">
                {show(i.count)}
              </span>
              {href ? <ChevronRight aria-hidden className="size-4 text-muted-foreground rtl:-scale-x-100" /> : null}
            </span>
          </>
        );
        return (
          <li key={i.key} data-testid="action-item" data-key={i.key}>
            {href ? (
              <Link href={href} className="flex min-h-touch items-center justify-between gap-3 py-2 text-sm hover:bg-accent/50">
                {body}
              </Link>
            ) : (
              <div className="flex min-h-touch items-center justify-between gap-3 py-2 text-sm">{body}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function ExpiringItems({ projectId, asOf, show }: { projectId: string | null; asOf: string | null; show: Show }) {
  const t = useTranslations("dashboard");
  const te = useTranslations("enums");
  const ar = useLocale() === "ar";
  const { date } = useFormatters(projectId);
  const q = useExpiringItems(projectId, asOf);
  if (!projectId) return null;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  if (q.data.items.length === 0) return <p className="text-sm text-muted-foreground">{t("allClear")}</p>;
  return (
    <ul className="flex flex-col divide-y" data-testid="expiring-items">
      {q.data.items.slice(0, 12).map((i, idx) => {
        const href = apiPathToRoute(i.detail_path) ?? entityRoute(i.entity_type, i.entity_id, projectId);
        const when = i.days_left < 0 ? t("daysOverdue", { days: show(-i.days_left) }) : i.days_left === 0 ? t("dueToday") : t("daysLeft", { days: show(i.days_left) });
        const content = (
          <>
            <span className="min-w-0">
              <span className="block text-xs text-muted-foreground">{te(`expiringKind.${i.kind}`)}</span>
              <span className="block [overflow-wrap:anywhere]">
                {i.ref ? <span className="ltr me-1">{i.ref}</span> : null}
                {ar ? i.title_ar : i.title_en}
              </span>
            </span>
            <span className={cn("max-w-[50%] shrink-0 text-end text-xs", i.days_left < 0 ? "text-danger" : i.days_left <= 2 ? "text-warning" : "text-muted-foreground")}>
              <CalendarClock aria-hidden className="me-1 inline size-3.5" />
              {date(i.due_date)}
              <span className="block">{when}</span>
            </span>
          </>
        );
        return (
          <li key={`${i.kind}-${i.entity_id ?? idx}`} data-testid="expiring-item">
            {href ? (
              <Link href={href} className="flex min-h-touch items-center justify-between gap-3 py-2 text-sm hover:bg-accent/50">
                {content}
              </Link>
            ) : (
              <div className="flex min-h-touch items-center justify-between gap-3 py-2 text-sm">{content}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function InsightsPanel({ query, enabled, show }: { query: KpiQuery; enabled: boolean; show: Show }) {
  const t = useTranslations("dashboard");
  const te = useTranslations("enums");
  const ar = useLocale() === "ar";
  const digits = useArabicDigits();
  const q = useInsights(query, enabled);
  if (!enabled) return null;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  return (
    <div className="flex flex-col gap-3" data-testid="insights">
      {!q.data.ai_available ? <p className="text-xs text-muted-foreground">{t("insightsAiOff")}</p> : null}
      {q.data.items.length === 0 ? <p className="text-sm text-muted-foreground">{t("noData")}</p> : null}
      {q.data.items.map((i) => {
        const Icon = i.kind === "positive" ? Lightbulb : SEV_ICON[i.severity];
        return (
          <article key={i.id} className="rounded-md border p-3" data-testid="insight" data-source={i.source}>
            <header className="mb-1 flex flex-wrap items-center gap-2">
              <Icon aria-hidden className={cn("size-4", i.kind === "positive" ? "text-success" : SEV_CLASS[i.severity])} />
              <h3 className="text-sm font-semibold">{ar ? i.title_ar : i.title_en}</h3>
              <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                {te(`insightKind.${i.kind}`)} · {te(`insightSource.${i.source}`)}
              </span>
            </header>
            <p className="text-sm whitespace-pre-wrap">{show(ar ? i.text_ar : i.text_en)}</p>
            {i.chart ? (
              <div className="mt-2">
                <ChartRenderer spec={i.chart} height={180} arabicDigits={digits} />
              </div>
            ) : null}
            {i.citations.length > 0 ? <p className="mt-1 text-[11px] text-muted-foreground">{i.citations.map((c) => show(ar ? c.text_ar : c.text_en)).join(" · ")}</p> : null}
          </article>
        );
      })}
      <div>
        <Button size="sm" variant="ghost" onClick={() => void q.refetch()} disabled={q.isFetching}>
          <RefreshCw aria-hidden />
          {t("insights")}
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
