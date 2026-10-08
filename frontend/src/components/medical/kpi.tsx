"use client";
import { useLocale, useTranslations } from "next-intl";
import { Fragment } from "react";
import { Alert } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { DateFilter } from "@/components/training/common";
import type { Schemas } from "@/lib/api/client";
import { useOccupationalHealthKpis } from "@/lib/api/medical";
import { useDisplay } from "@/lib/digits";
import { MEDICAL_KPI_GROUP_BY } from "@/lib/med-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { useMedCaps } from "./common";

type S = Schemas;

export function OccupationalHealthKpiPage() {
  return <ProjectGate>{(p) => <OhKpis project={p} />}</ProjectGate>;
}

/** K-89…K-96: every number is the server's `display` (MK-3 "<5" suppression included); nothing is computed here. */
function OhKpis({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("medical.kpi");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const ar = useLocale() === "ar";
  const caps = useMedCaps(project.id);
  const show = useDisplay(project.id);
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const groupBy = (s.get("group_by") as S["MedicalKpiGroupBy"]) || "code";
  const asOf = s.get("as_of") ?? "";
  const q = useOccupationalHealthKpis({ project_id: [project.id], as_of: asOf || null, group_by: [groupBy] }, { enabled: caps.kpi });
  if (!caps.kpi) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const d = q.data;
  const label = (x: { label_en: string; label_ar: string }) => (ar ? x.label_ar : x.label_en);
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <ListToolbar>
        <DateFilter id="oh-as-of" label={t("asOf")} value={asOf} onChange={(v) => s.set({ as_of: v })} />
        <SelectFilter id="oh-group" label={t("groupBy")} value={groupBy} onChange={(v) => s.set({ group_by: v })} options={MEDICAL_KPI_GROUP_BY.map((g) => ({ value: g, label: te(`medicalKpiGroupBy.${g}`) }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : d ? (
        <div className="flex flex-col gap-6">
          <p className="text-xs text-muted-foreground">
            {label(d.context.period)} · {t("computedAt", { at: dateTime(d.context.computed_at) })}
          </p>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" data-testid="oh-tiles">
            {d.metrics.map((m) => (
              <Card key={m.metric} data-testid="oh-tile" data-metric={m.metric}>
                <CardContent className="flex flex-col gap-1 p-4">
                  <span className="flex items-center justify-between gap-2 text-xs font-medium text-muted-foreground">
                    <span>{ar ? m.short_label_ar : m.short_label_en}</span>
                    <span className="font-mono ltr">{m.metric}</span>
                  </span>
                  <span className={cn("text-3xl font-semibold tabular-nums", m.rag === "red" && "text-danger", m.rag === "amber" && "text-warning")} data-testid="oh-value">
                    {show(m.display)}
                  </span>
                  {m.null_reason ? <span className="text-xs text-muted-foreground">{te(`nullReason.${m.null_reason}`)}</span> : null}
                  {m.components.length ? (
                    <span className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                      {m.components.map((c) => (
                        <span key={c.key} data-testid="oh-component" data-key={c.key}>
                          {label(c)}: <span className="font-medium tabular-nums text-foreground">{show(c.display)}</span>
                        </span>
                      ))}
                    </span>
                  ) : null}
                  {m.target_display ? <span className="text-xs text-muted-foreground">{t("target", { v: show(m.target_display) })}</span> : null}
                  <span className="text-xs text-muted-foreground">{ar ? m.label_ar : m.label_en}</span>
                </CardContent>
              </Card>
            ))}
          </div>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("breakdown", { by: te(`medicalKpiGroupBy.${groupBy}`) })}</CardTitle>
              <p className="text-xs text-muted-foreground">{t("suppressedHint")}</p>
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

function Breakdown({ breakdowns, metrics, show }: { breakdowns: S["MedicalBreakdown"][]; metrics: S["KpiValue"][]; show: (v: string) => string }) {
  const t = useTranslations("medical.kpi");
  const ar = useLocale() === "ar";
  if (!breakdowns.length) return <EmptyState message={t("noBreakdown")} />;
  const keys: { key: string; label: string }[] = [];
  for (const b of breakdowns) for (const r of b.rows) if (!keys.some((k) => k.key === r.key)) keys.push({ key: r.key, label: ar ? r.label_ar : r.label_en });
  const metricLabel = (id: string) => {
    const m = metrics.find((x) => x.metric === id);
    return m ? (ar ? m.short_label_ar : m.short_label_en) : id;
  };
  return (
    <Table data-testid="oh-breakdown">
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
          <TR key={k.key} data-testid="oh-row" data-key={k.key}>
            <TD label={t("key")}>{k.label}</TD>
            {breakdowns.map((b) => {
              const r = b.rows.find((x) => x.key === k.key);
              return (
                <Fragment key={b.metric}>
                  <TD label={metricLabel(b.metric)} className={cn("text-end tabular-nums", r?.suppressed && "text-muted-foreground")} data-testid="oh-cell" data-metric={b.metric} data-suppressed={r?.suppressed ? "1" : "0"}>
                    {r ? show(r.display) : "—"}
                  </TD>
                </Fragment>
              );
            })}
          </TR>
        ))}
      </TBody>
    </Table>
  );
}
