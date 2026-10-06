"use client";
import { ExternalLink } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Pagination } from "@/components/common/pagination";
import { ErrorState, LoadingState } from "@/components/common/states";
import { Link } from "@/i18n/navigation";
import type { Schemas } from "@/lib/api/client";
import { useKpi, useKpiSources, type KpiQuery } from "@/lib/api/kpi";
import { useDisplay } from "@/lib/digits";
import { useFormatters } from "@/lib/use-formatters";
import { apiPathToRoute } from "@/lib/routes";
import { cn } from "@/lib/utils";

type Metric = Schemas["KpiMetric"];

interface DrillCtx {
  open: (metric: Metric, label?: string, override?: Partial<KpiQuery>) => void;
}

const Ctx = createContext<DrillCtx>({ open: () => undefined });

export function useDrill() {
  return useContext(Ctx);
}

/** Every number on the dashboard opens its source records (D-1, AC on drill-down). */
export function DrillProvider({ query, projectId, children }: { query: KpiQuery; projectId: string | null; children: ReactNode }) {
  const [state, setState] = useState<{
    metric: Metric;
    label?: string;
    override?: Partial<KpiQuery>;
  } | null>(null);
  const open = useCallback((metric: Metric, label?: string, override?: Partial<KpiQuery>) => setState({ metric, label, override }), []);
  const value = useMemo(() => ({ open }), [open]);
  return (
    <Ctx.Provider value={value}>
      {children}
      {state ? <DrillDialog metric={state.metric} label={state.label} query={{ ...query, ...state.override }} projectId={projectId} onClose={() => setState(null)} /> : null}
    </Ctx.Provider>
  );
}

/** A KPI number rendered as a button that opens the drill-down. */
export function DrillNumber({
  metric,
  label,
  children,
  className,
  override,
}: {
  metric: Metric;
  label: string;
  children: ReactNode;
  className?: string;
  override?: Partial<KpiQuery>;
}) {
  const t = useTranslations("dashboard");
  const { open } = useDrill();
  return (
    <button
      type="button"
      onClick={() => open(metric, label, override)}
      className={cn("cursor-pointer rounded-sm text-start underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-ring", className)}
      aria-label={t("openDrill", { label })}
      data-testid={`drill-${metric}`}
    >
      {children}
    </button>
  );
}

function DrillDialog({ metric, label, query, projectId, onClose }: { metric: Metric; label?: string; query: KpiQuery; projectId: string | null; onClose: () => void }) {
  const t = useTranslations("dashboard");
  const tc = useTranslations("common");
  const te = useTranslations("enums");
  const locale = useLocale();
  const ar = locale === "ar";
  const show = useDisplay(projectId);
  const { date } = useFormatters(projectId);
  const kpi = useKpi(metric, query);
  const [part, setPart] = useState<"numerator" | "denominator">("numerator");
  const [page, setPage] = useState(1);
  const sources = useKpiSources(metric, part, page, query);
  const k = kpi.data?.kpi;
  const title = label ?? (k ? (ar ? k.label_ar : k.label_en) : metric);
  const hasDenominator = Boolean(k?.denominator_label_en);

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")} className="max-w-3xl" data-testid="drill-dialog">
        <DialogHeader>
          <DialogTitle>{t("drillTitle", { label: title })}</DialogTitle>
          <DialogDescription>{kpi.data ? (ar ? kpi.data.context.period.label_ar : kpi.data.context.period.label_en) : null}</DialogDescription>
        </DialogHeader>
        {kpi.isError ? (
          <ErrorState error={kpi.error} onRetry={() => kpi.refetch()} />
        ) : !k ? (
          <LoadingState />
        ) : (
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
              <p className="text-3xl font-semibold" data-testid="drill-value">
                {show(k.display)}
                <span className="ms-1 text-sm font-normal text-muted-foreground">{ar ? k.unit_ar : k.unit_en}</span>
              </p>
              {k.numerator !== null ? (
                <p className="text-sm text-muted-foreground">
                  {k.numerator_label_en ?? t("numerator")}: <span className="font-medium text-foreground">{show(k.numerator)}</span>
                </p>
              ) : null}
              {k.denominator !== null ? (
                <p className="text-sm text-muted-foreground">
                  {k.denominator_label_en ?? t("denominator")}: <span className="font-medium text-foreground">{show(k.denominator)}</span>
                </p>
              ) : null}
            </div>
            {k.warnings.length > 0 ? (
              <ul className="flex flex-wrap gap-2">
                {k.warnings.map((w) => (
                  <li key={w} className="rounded bg-warning-bg px-2 py-0.5 text-xs text-warning">
                    {te(`kpiWarning.${w}`)}
                  </li>
                ))}
              </ul>
            ) : null}
            {k.one_case_changes_rate_by ? <Alert tone="info">{t("oneCase", { value: show(k.one_case_changes_rate_by) })}</Alert> : null}
            {hasDenominator ? (
              <div className="flex gap-2" role="tablist">
                {(["numerator", "denominator"] as const).map((p) => (
                  <Button
                    key={p}
                    size="sm"
                    role="tab"
                    aria-selected={part === p}
                    variant={part === p ? "default" : "outline"}
                    onClick={() => {
                      setPart(p);
                      setPage(1);
                    }}
                    data-testid={`drill-part-${p}`}
                  >
                    {p === "numerator" ? (k.numerator_label_en ?? t("numerator")) : (k.denominator_label_en ?? t("denominator"))}
                  </Button>
                ))}
              </div>
            ) : null}
            {sources.isError ? (
              <ErrorState error={sources.error} onRetry={() => sources.refetch()} />
            ) : !sources.data ? (
              <LoadingState />
            ) : (
              <>
                <p className="text-xs text-muted-foreground">{t("records", { count: show(sources.data.total) })}</p>
                <ul className="flex max-h-80 flex-col divide-y overflow-y-auto rounded-md border" data-testid="drill-sources">
                  {sources.data.items.map((r) => {
                    const href = apiPathToRoute(r.detail_path);
                    const text = (
                      <>
                        <span className="font-medium">
                          {r.ref ? <span className="ltr me-2">{r.ref}</span> : null}
                          {ar ? r.label_ar : r.label_en}
                        </span>
                        <span className="block text-xs text-muted-foreground">
                          {date(r.date)}
                          {r.site_code ? <span className="ltr"> · {r.site_code}</span> : null}
                          {r.engagement_code ? <span className="ltr"> · {r.engagement_code}</span> : null}
                        </span>
                      </>
                    );
                    return (
                      <li key={`${r.entity_type}-${r.id}`} className="p-2 text-sm" data-testid="drill-source">
                        {href ? (
                          <Link href={href} className="flex items-start justify-between gap-2 hover:underline" onClick={onClose}>
                            <span>{text}</span>
                            <ExternalLink aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground rtl:-scale-x-100" />
                          </Link>
                        ) : (
                          <div title={t("noOpen")}>{text}</div>
                        )}
                      </li>
                    );
                  })}
                </ul>
                <Pagination page={page} pageSize={sources.data.page_size} total={sources.data.total} onPage={setPage} />
              </>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
