"use client";
import { ArrowRight, FileCheck2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Fragment, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { ProjectGate } from "@/components/common/project-gate";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { Code, StepDialog } from "@/components/access/common";
import { UserName } from "@/components/cert/common";
import { DateFilter } from "@/components/training/common";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useHeatActionPanel, useHeatKpis, useHeatRefresh, useSeasonReports } from "@/lib/api/heat";
import { useDisplay } from "@/lib/digits";
import { HEAT_KPI_GROUP_BY } from "@/lib/heat-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { FreeText, HeatFieldSubNav, HeatReportSubNav, useHeatCaps } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];

/* ═════════════ heat stress KPIs K-97…K-103 (§6.6) ═════════════ */

export function HeatKpiPage() {
  return <ProjectGate>{(p) => <HeatKpis project={p} />}</ProjectGate>;
}

const PERIODS = ["month", "quarter", "year", "ytd"] as const satisfies readonly S["PeriodPreset"][];

/** Every number is the server's `display` ("<3" small-cell suppression included); nothing is computed here. */
function HeatKpis({ project }: { project: Project }) {
  const t = useTranslations("heat.kpi");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const ar = useLocale() === "ar";
  const caps = useHeatCaps(project.id);
  const show = useDisplay(project.id);
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const groupBy = (s.get("group_by") as S["HeatKpiGroupBy"]) || "zone";
  const period = (s.get("period") as (typeof PERIODS)[number]) || "month";
  const anchor = s.get("anchor") ?? "";
  const q = useHeatKpis({ project_id: [project.id], group_by: [groupBy], period, anchor: anchor || null }, { enabled: caps.kpi });
  if (!caps.kpi) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const d = q.data;
  const label = (x: { label_en: string; label_ar: string }) => (ar ? x.label_ar : x.label_en);
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <HeatReportSubNav />
      <ListToolbar>
        <SelectFilter id="hk-period" label={t("period")} value={period} onChange={(v) => s.set({ period: v })} options={PERIODS.map((p) => ({ value: p, label: te(`period.${p}`) }))} allLabel={te("period.month")} />
        <DateFilter id="hk-anchor" label={t("anchor")} value={anchor} onChange={(v) => s.set({ anchor: v })} />
        <SelectFilter id="hk-group" label={t("groupBy")} value={groupBy} onChange={(v) => s.set({ group_by: v })} options={HEAT_KPI_GROUP_BY.map((g) => ({ value: g, label: te(`heatKpiGroupBy.${g}`) }))} allLabel={te("heatKpiGroupBy.zone")} />
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
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" data-testid="heat-tiles">
            {d.metrics.map((m) => (
              <Card key={m.metric} data-testid="heat-tile" data-metric={m.metric}>
                <CardContent className="flex flex-col gap-1 p-4">
                  <span className="flex items-center justify-between gap-2 text-xs font-medium text-muted-foreground">
                    <span>{ar ? m.short_label_ar : m.short_label_en}</span>
                    <span className="font-mono ltr">{m.metric}</span>
                  </span>
                  <span className={cn("text-3xl font-semibold tabular-nums", m.rag === "red" && "text-danger", m.rag === "amber" && "text-warning")} data-testid="heat-value">
                    {show(m.display)}
                  </span>
                  {m.null_reason ? <span className="text-xs text-muted-foreground">{te(`nullReason.${m.null_reason}`)}</span> : null}
                  {m.components.length ? (
                    <span className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                      {m.components.map((c) => (
                        <span key={c.key} data-testid="heat-component" data-key={c.key}>
                          {label(c)}: <span className="font-medium tabular-nums text-foreground">{show(c.display)}</span>
                        </span>
                      ))}
                    </span>
                  ) : null}
                  {m.numerator && m.denominator ? (
                    <span className="text-xs text-muted-foreground">
                      <bdi className="ltr tabular-nums">
                        {show(m.numerator)} / {show(m.denominator)}
                      </bdi>
                    </span>
                  ) : null}
                  <span className="text-xs text-muted-foreground">{ar ? m.label_ar : m.label_en}</span>
                </CardContent>
              </Card>
            ))}
          </div>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("breakdown", { by: te(`heatKpiGroupBy.${groupBy}`) })}</CardTitle>
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

function Breakdown({ breakdowns, metrics, show }: { breakdowns: S["HeatBreakdown"][]; metrics: S["KpiValue"][]; show: (v: string) => string }) {
  const t = useTranslations("heat.kpi");
  const ar = useLocale() === "ar";
  if (!breakdowns.length) return <EmptyState message={t("noBreakdown")} />;
  const keys: { key: string; label: string }[] = [];
  for (const b of breakdowns) for (const r of b.rows) if (!keys.some((k) => k.key === r.key)) keys.push({ key: r.key, label: ar ? r.label_ar : r.label_en });
  const metricLabel = (id: string) => {
    const m = metrics.find((x) => x.metric === id);
    return m ? (ar ? m.short_label_ar : m.short_label_en) : id;
  };
  return (
    <Table data-testid="heat-breakdown">
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
          <TR key={k.key} data-testid="heat-row" data-key={k.key}>
            <TD label={t("key")}>
              <bdi>{k.label}</bdi>
            </TD>
            {breakdowns.map((b) => {
              const r = b.rows.find((x) => x.key === k.key);
              return (
                <Fragment key={b.metric}>
                  <TD label={metricLabel(b.metric)} className="text-end tabular-nums" data-testid="heat-cell" data-metric={b.metric}>
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

/* ═════════════ action panel (§8.2) ═════════════ */

const ACTION_HREF: Record<S["HeatActionKind"], string> = {
  required_zone_without_point: "/monitoring-points",
  reading_overdue_now: "/heat-board",
  r4_permit_not_suspended: "/permits?status=active",
  ban_violation_ca_open: "/ban-patrols?outcome=violation",
  patrol_coverage_missed_yesterday: "/ban-patrols",
  welfare_coverage_missed_yesterday: "/heat-welfare-checks",
  plan_days_unconfirmed: "/acclimatisation-plans?status=active",
  heat_reviews_overdue: "/heat-illness-log?status=open",
  active_ban_exemption: "/ban-exemptions?status=active",
  quarantined_instrument_on_point: "/heat-instruments",
  permit_ban_violation: "/permits",
};

export function HeatActionsPage() {
  return <ProjectGate>{(p) => <Actions project={p} />}</ProjectGate>;
}

function Actions({ project }: { project: Project }) {
  const t = useTranslations("heat.actions");
  const tc = useTranslations("common");
  const ar = useLocale() === "ar";
  const caps = useHeatCaps(project.id);
  const q = useHeatActionPanel(project.id, { enabled: caps.kpi });
  if (!caps.kpi) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <HeatFieldSubNav />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <ul className="flex flex-col divide-y rounded-md border" data-testid="heat-actions">
          {items.map((i) => {
            const linkable = i.kind !== "heat_reviews_overdue" || caps.log;
            return (
              <li key={i.kind} className="flex flex-wrap items-center gap-3 px-3 py-2.5" data-testid="heat-action" data-kind={i.kind} data-count={i.count}>
                <Badge tone={i.count ? (i.kind === "r4_permit_not_suspended" || i.kind === "permit_ban_violation" ? "danger" : i.kind === "active_ban_exemption" ? "info" : "warning") : "neutral"} className="min-w-10 justify-center tabular-nums">
                  {i.count}
                </Badge>
                <span className="flex-1 text-sm">{ar ? i.label_ar : i.label_en}</span>
                {i.refs.length ? (
                  <span className="flex flex-wrap gap-1 text-xs">
                    {i.refs.slice(0, 6).map((r) => (
                      <Code key={r} className="rounded bg-surface px-1">
                        {r}
                      </Code>
                    ))}
                  </span>
                ) : null}
                {linkable && i.count ? (
                  <Link href={ACTION_HREF[i.kind]} className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
                    {t("open")}
                    <ArrowRight aria-hidden className="size-4 rtl:-scale-x-100" />
                  </Link>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/* ═════════════ season report (§8.4, HM-4) ═════════════ */

export function SeasonReportPage() {
  return <ProjectGate>{(p) => <Season project={p} />}</ProjectGate>;
}

type M = Record<string, unknown>;

function Season({ project }: { project: Project }) {
  const t = useTranslations("heat.report");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useHeatCaps(project.id);
  const { date, dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const year = s.get("year") ?? "";
  const q = useSeasonReports(project.id, { season_year: year ? Number(year) : null }, { enabled: caps.kpi });
  const [issue, setIssue] = useState(false);
  const [rev, setRev] = useState("");
  if (!caps.kpi) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const d = q.data;
  const reports = [...(d?.draft ? [d.draft] : []), ...(d?.issued ?? [])];
  const current = reports.find((r) => (r.report_no ?? "draft") === rev) ?? reports[0];
  const thisYear = new Date().getFullYear();
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.settings && d?.draft ? (
            <Button onClick={() => setIssue(true)} data-testid="report-issue">
              <FileCheck2 aria-hidden />
              {d.issued.some((r) => r.status === "issued") ? t("reissue") : t("issue")}
            </Button>
          ) : null
        }
      />
      <HeatReportSubNav />
      <ListToolbar>
        <SelectFilter id="sr-year" label={t("year")} value={year} onChange={(v) => s.set({ year: v })} options={[thisYear, thisYear - 1, thisYear - 2].map((y) => ({ value: String(y), label: String(y) }))} allLabel={t("currentSeason")} />
        {reports.length > 1 ? (
          <SelectFilter
            id="sr-rev"
            label={t("revision")}
            value={rev}
            onChange={(v) => setRev(v)}
            options={reports.map((r) => ({ value: r.report_no ?? "draft", label: r.report_no ? `${r.report_no} · ${te(`seasonReportStatus.${r.status}`)}` : te("seasonReportStatus.draft") }))}
            allLabel={t("latest")}
          />
        ) : null}
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : current ? (
        <div className="flex flex-col gap-4" data-testid="season-report" data-status={current.status} data-no={current.report_no ?? "draft"}>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <StatusBadge status={current.status === "draft" ? "draft" : current.status} label={te(`seasonReportStatus.${current.status}`)} />
            {current.report_no ? <Code className="font-medium">{current.report_no}</Code> : null}
            <span className="text-muted-foreground">
              {t("period", { from: date(current.period_from), to: date(current.period_to) })}
            </span>
            {current.issued_at ? (
              <span className="text-muted-foreground">
                · {t("issuedBy")} <UserName u={current.issued_by} /> {dateTime(current.issued_at)}
              </span>
            ) : null}
          </div>
          {current.status === "draft" ? <Alert tone="info">{t("draftHint")}</Alert> : null}
          <ReportBody m={current.metrics as M} />
          {current.comments_en || current.comments_ar ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t("comments")}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2 text-sm">
                <FreeText>{current.comments_en}</FreeText>
                <FreeText>{current.comments_ar}</FreeText>
              </CardContent>
            </Card>
          ) : null}
        </div>
      ) : (
        <EmptyState message={t("empty")} />
      )}
      {issue && d?.draft ? <IssueDialog project={project} year={d.draft.season_year} reissue={d.issued.some((r) => r.status === "issued")} onClose={() => setIssue(false)} /> : null}
    </div>
  );
}

function SmallTable({ head, rows, testId }: { head: string[]; rows: (string | number | null | undefined)[][]; testId?: string }) {
  const show = useDisplay();
  if (!rows.length) return <p className="text-sm text-muted-foreground">—</p>;
  return (
    <Table data-testid={testId}>
      <THead>
        <TR>
          {head.map((h, i) => (
            <TH key={i} className={i ? "text-end" : undefined}>
              {h}
            </TH>
          ))}
        </TR>
      </THead>
      <TBody>
        {rows.map((r, i) => (
          <TR key={i}>
            {r.map((c, j) => (
              <TD key={j} label={head[j]} className={j ? "text-end tabular-nums" : undefined}>
                <bdi className="ltr">{c === null || c === undefined ? "—" : show(String(c))}</bdi>
              </TD>
            ))}
          </TR>
        ))}
      </TBody>
    </Table>
  );
}

/** §8.4 sections from the frozen (or live) metrics; aggregates only (HM-3), no names. */
function ReportBody({ m }: { m: M }) {
  const t = useTranslations("heat.report");
  const te = useTranslations("enums");
  const show = useDisplay();
  const season = (m.season ?? {}) as Record<string, { display?: string; [k: string]: unknown }>;
  const cov = (m.coverage_by_month ?? []) as Record<string, string>[];
  const wbgt = (m.wbgt_by_point_month ?? []) as Record<string, string>[];
  const k98 = (m.k98_by_zone ?? []) as Record<string, string>[];
  const ban = (m.midday_ban ?? {}) as { patrols?: number; violations?: number; violations_by_contractor?: Record<string, number>; exemptions_granted?: number; "K-99"?: string };
  const acc = (m.acclimatisation ?? {}) as { plans_by_type?: Record<string, number>; "K-102"?: string };
  const hi = (m.heat_illness ?? {}) as { cases?: string; rate?: string; recordable?: string; recordable_rate?: string; by_month_category?: Record<string, Record<string, number>>; control_gap_share_pct?: string | null; previous_season?: unknown };
  const cas = (m.corrective_actions ?? {}) as { raised?: number; closed?: number };
  const regimes = ["R0", "R1", "R2", "R3", "R4", "stale", "unknown"];
  const sec = (title: string, body: ReactNode, testId?: string) => (
    <Card data-testid={testId}>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>{body}</CardContent>
    </Card>
  );
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" data-testid="season-tiles">
        <Card>
          <CardContent className="flex flex-col gap-1 p-4">
            <span className="text-xs text-muted-foreground">{t("manHours")}</span>
            <span className="text-2xl font-semibold tabular-nums" data-testid="season-k01">
              {show(m.k01_man_hours ? Number(m.k01_man_hours).toLocaleString("en-US") : "—")}
            </span>
          </CardContent>
        </Card>
        {Object.entries(season).map(([k, v]) => (
          <Card key={k} data-testid="season-tile" data-metric={k}>
            <CardContent className="flex flex-col gap-1 p-4">
              <span className="flex justify-between text-xs text-muted-foreground">
                <span>{te.has(`heatKpi.${k}` as never) ? te(`heatKpi.${k}` as never) : k}</span>
                <span className="font-mono ltr">{k}</span>
              </span>
              <span className="text-2xl font-semibold tabular-nums">{show(v.display ?? "—")}</span>
            </CardContent>
          </Card>
        ))}
      </div>
      {sec(t("s1"), <SmallTable head={[t("month"), "K-97", "K-99", "K-101"]} rows={cov.map((r) => [r.month, r["K-97"], r["K-99"], r["K-101"]])} testId="season-coverage" />)}
      {sec(t("s2"), <SmallTable head={[t("point"), t("month"), t("max"), t("meanMax")]} rows={wbgt.map((r) => [r.point_code, r.month, r.max_c, r.mean_daily_max_c])} />)}
      {sec(t("s3"), <SmallTable head={[t("zone"), ...regimes.map((r) => (te.has(`regimeShort.${r}` as never) ? te(`regimeShort.${r}` as never) : te(`heatState.${r}` as never)))]} rows={k98.map((r) => [r.zone_code, ...regimes.map((g) => r[g])])} />)}
      {sec(
        t("s4"),
        <div className="flex flex-col gap-2 text-sm" data-testid="season-ban">
          <p>{t("banLine", { patrols: ban.patrols ?? 0, violations: ban.violations ?? 0, exemptions: ban.exemptions_granted ?? 0, k99: ban["K-99"] ?? "—" })}</p>
          <SmallTable head={[t("contractor"), t("violations")]} rows={Object.entries(ban.violations_by_contractor ?? {}).map(([k, v]) => [k, v])} />
        </div>,
      )}
      {sec(
        t("s5"),
        <div className="flex flex-col gap-2 text-sm">
          <SmallTable head={[t("planType"), t("plans")]} rows={Object.entries(acc.plans_by_type ?? {}).map(([k, v]) => [te.has(`planType.${k}` as never) ? te(`planType.${k}` as never) : k, v])} />
          <p>K-102: {show(acc["K-102"] ?? "—")}</p>
        </div>,
      )}
      {sec(
        t("s6"),
        <div className="flex flex-col gap-2 text-sm" data-testid="season-illness">
          <p>{t("illnessLine", { cases: hi.cases ?? "—", rate: hi.rate ?? "—", recordable: hi.recordable ?? "—", rrate: hi.recordable_rate ?? "—", gap: hi.control_gap_share_pct ?? "—" })}</p>
          <SmallTable head={[t("month"), "FAC", "MTC", "RWC", "LTI"]} rows={Object.entries(hi.by_month_category ?? {}).map(([mo, c]) => [mo, c.FAC ?? 0, c.MTC ?? 0, c.RWC ?? 0, c.LTI ?? 0])} />
          <p className="text-muted-foreground">{t("previousSeason")}: {hi.previous_season ? JSON.stringify(hi.previous_season) : "—"}</p>
        </div>,
      )}
      {sec(t("s7"), <p className="text-sm">{m.heat_awr_compliance === null || m.heat_awr_compliance === undefined ? "—" : String(m.heat_awr_compliance)}</p>)}
      {sec(t("s8"), <p className="text-sm">{t("caLine", { raised: cas.raised ?? 0, closed: cas.closed ?? 0 })}</p>)}
    </div>
  );
}

function IssueDialog({ project, year, reissue, onClose }: { project: Project; year: number; reissue: boolean; onClose: () => void }) {
  const t = useTranslations("heat.report");
  const tcm = useTranslations("heat.common");
  const refresh = useHeatRefresh();
  const [en, setEn] = useState("");
  const [ar, setAr] = useState("");
  const [reason, setReason] = useState("");
  return (
    <StepDialog
      title={reissue ? t("reissue") : t("issue")}
      description={t("issueHint", { year })}
      confirmLabel={reissue ? t("reissue") : t("issue")}
      disabled={reissue && reason.trim().length < 20}
      testId="report-issue-confirm"
      wide
      onConfirm={async () => {
        const r = await unwrap(
          api.POST("/api/v1/projects/{project_id}/heat-season-reports", {
            params: { path: { project_id: project.id } },
            body: { season_year: year, comments_en: en.trim() || null, comments_ar: ar.trim() || null, reason: reason.trim() || null },
          }),
        );
        toast.success(t("issued", { no: r.report_no ?? "" }));
        await refresh();
      }}
      onClose={onClose}
    >
      <FormField id="sr-en" label={t("commentsEn")} hint={t("commentsHint")}>
        <Textarea value={en} onChange={(e) => setEn(e.target.value)} maxLength={2000} data-testid="sr-en" />
      </FormField>
      <FormField id="sr-ar" label={t("commentsAr")}>
        <Textarea dir="rtl" value={ar} onChange={(e) => setAr(e.target.value)} maxLength={2000} />
      </FormField>
      {reissue ? (
        <FormField id="sr-reason" label={tcm("reason")} required hint={tcm("reasonMin", { min: 20, n: reason.trim().length })}>
          <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} data-testid="sr-reason" />
        </FormField>
      ) : null}
    </StepDialog>
  );
}
