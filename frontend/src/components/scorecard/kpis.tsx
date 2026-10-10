"use client";
import { TriangleAlert } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Alert } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { DateFilter } from "@/components/training/common";
import type { Schemas } from "@/lib/api/client";
import { useScKpis } from "@/lib/api/scorecard";
import { useDisplay } from "@/lib/digits";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { ScSubNav, useScCaps } from "./common";

type S = Schemas;

const PERIODS = ["month", "quarter", "year", "ytd"] as const satisfies readonly S["PeriodPreset"][];
const GROUP_BY: S["ScKpiGroupBy"][] = ["contractor", "month"];
const LEVELS = new Set(["watch", "improvement_plan", "suspension_review"]);

export function ScorecardKpiPage() {
  return <ProjectGate>{(p) => <Kpis project={p} />}</ProjectGate>;
}

/** K-132…K-135 exactly as the server returns them (`display`); nothing is computed here. */
function Kpis({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("sc.kpi");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const ar = useLocale() === "ar";
  const caps = useScCaps(project.id);
  const show = useDisplay(project.id);
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const groupBy = (s.get("group_by") as S["ScKpiGroupBy"]) || "contractor";
  const period = (s.get("period") as (typeof PERIODS)[number]) || "month";
  const anchor = s.get("anchor") ?? "";
  const q = useScKpis({ project_id: [project.id], group_by: [groupBy], period, anchor: anchor || null }, { enabled: caps.view });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const d = q.data;
  const compLabel = (c: S["KpiValue"]["components"][number]) => (LEVELS.has(c.key) ? te(`scWatchLevel.${c.key}` as "scWatchLevel.watch") : ar ? c.label_ar : c.label_en);
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <ScSubNav />
      <ListToolbar>
        <SelectFilter id="sk-period" label={t("period")} value={period} onChange={(v) => s.set({ period: v })} options={PERIODS.map((p) => ({ value: p, label: te(`period.${p}`) }))} allLabel={te("period.month")} />
        <DateFilter id="sk-anchor" label={t("anchor")} value={anchor} onChange={(v) => s.set({ anchor: v })} />
        <SelectFilter id="sk-group" label={t("groupBy")} value={groupBy} onChange={(v) => s.set({ group_by: v })} options={GROUP_BY.map((g) => ({ value: g, label: te(`scKpiGroupBy.${g}`) }))} allLabel={te("scKpiGroupBy.contractor")} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : d ? (
        <div className="flex flex-col gap-6">
          <p className="text-xs text-muted-foreground">
            {ar ? d.context.period.label_ar : d.context.period.label_en} · {t("computedAt", { at: dateTime(d.context.computed_at) })}
          </p>
          {d.notes.length ? <p className="text-sm text-muted-foreground">{t("attribution")}</p> : null}
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" data-testid="sk-tiles">
            {d.metrics.map((m) => (
              <Card key={m.metric} data-testid="sk-tile" data-metric={m.metric}>
                <CardContent className="flex flex-col gap-1 p-4">
                  <span className="flex items-center justify-between gap-2 text-xs font-medium text-muted-foreground">
                    <span>{ar ? m.short_label_ar : m.short_label_en}</span>
                    <span className="ltr font-mono">{m.metric}</span>
                  </span>
                  <span className={cn("text-3xl font-semibold tabular-nums", m.rag === "red" && "text-danger", m.rag === "amber" && "text-warning")} data-testid="sk-value">
                    {show(m.display)}
                  </span>
                  {m.rag && m.rag !== "green" ? (
                    <span className={cn("inline-flex items-center gap-1 text-xs font-medium", m.rag === "red" ? "text-danger" : "text-warning")}>
                      <TriangleAlert aria-hidden className="size-3.5" />
                      {te(`rag.${m.rag}`)}
                    </span>
                  ) : null}
                  {m.null_reason ? <span className="text-xs text-muted-foreground">{te(`nullReason.${m.null_reason}`)}</span> : null}
                  {m.components.length ? (
                    <span className="flex flex-wrap gap-x-3 text-xs text-muted-foreground" data-testid="sk-chips">
                      {m.components.map((c) => (
                        <span key={c.key}>
                          {compLabel(c)}: <span className="font-medium tabular-nums text-foreground">{show(c.display)}</span>
                        </span>
                      ))}
                    </span>
                  ) : null}
                  <span className="text-xs text-muted-foreground">{ar ? m.label_ar : m.label_en}</span>
                </CardContent>
              </Card>
            ))}
          </div>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("breakdown", { by: te(`scKpiGroupBy.${groupBy}`) })}</CardTitle>
            </CardHeader>
            <CardContent>
              <Breakdown breakdowns={d.breakdowns} metrics={d.metrics} show={show} />
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
}

function Breakdown({ breakdowns, metrics, show }: { breakdowns: S["ScBreakdown"][]; metrics: S["KpiValue"][]; show: (v: string) => string }) {
  const t = useTranslations("sc.kpi");
  const ar = useLocale() === "ar";
  if (!breakdowns.length || breakdowns.every((b) => !b.rows.length)) return <EmptyState message={t("noBreakdown")} />;
  const keys: { key: string; label: string }[] = [];
  for (const b of breakdowns) for (const r of b.rows) if (!keys.some((k) => k.key === r.key)) keys.push({ key: r.key, label: ar ? r.label_ar : r.label_en });
  const metricLabel = (id: string) => {
    const m = metrics.find((x) => x.metric === id);
    return m ? (ar ? m.short_label_ar : m.short_label_en) : id;
  };
  return (
    <Table data-testid="sk-breakdown">
      <THead>
        <TR>
          <TH>{t("key")}</TH>
          {breakdowns.map((b) => (
            <TH key={b.metric} className="text-end">
              {metricLabel(b.metric)}
            </TH>
          ))}
        </TR>
      </THead>
      <TBody>
        {keys.map((k) => (
          <TR key={k.key} data-testid="sk-row" data-key={k.key}>
            <TD label={t("key")}>
              <bdi>{k.label}</bdi>
            </TD>
            {breakdowns.map((b) => {
              const r = b.rows.find((x) => x.key === k.key);
              return (
                <TD key={b.metric} label={metricLabel(b.metric)} className="text-end tabular-nums">
                  {r ? show(r.display) : "—"}
                </TD>
              );
            })}
          </TR>
        ))}
      </TBody>
    </Table>
  );
}
