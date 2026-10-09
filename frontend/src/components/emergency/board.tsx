"use client";
import { ArrowRight, CalendarClock, ClipboardCheck, FileText, HeartPulse, Phone, ShieldAlert, Siren, Users } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Fragment, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { ProjectGate } from "@/components/common/project-gate";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { Code } from "@/components/access/common";
import { StackedDate } from "@/components/medical/common";
import { DateFilter } from "@/components/training/common";
import { Link } from "@/i18n/navigation";
import type { Schemas } from "@/lib/api/client";
import { useEmergencyActionPanel, useEmergencyBoard, useEmergencyInfo, useEmergencyKpis } from "@/lib/api/emergency";
import { useDisplay } from "@/lib/digits";
import { EM_KPI_GROUP_BY } from "@/lib/emergency-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { Codes, CoverageBadge, EmPlanSubNav, EmReportSubNav, ErpStatusBadge, EventStatusBadge, LineStatusBadge, MusterStatusBadge, useEmCaps, useEmRef } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];

/* ═════════════ emergency board (§8.1 band; phone-first) ═════════════ */

export function EmergencyBoardPage() {
  return <ProjectGate>{(p) => <Board project={p} />}</ProjectGate>;
}

function Board({ project }: { project: Project }) {
  const t = useTranslations("emergency.board");
  const tc = useTranslations("common");
  const caps = useEmCaps(project.id);
  const { prefs, dateTime } = useFormatters(project.id);
  const q = useEmergencyBoard(project.id, { enabled: caps.view });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const b = q.data;
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.declare || caps.check ? (
            <div className="grid w-full gap-2 sm:flex sm:w-auto">
              {caps.declare ? (
                <Button asChild variant="destructive" className="min-h-12 text-base sm:min-h-control sm:text-sm">
                  <Link href="/emergency-events?declare=1" data-testid="board-declare">
                    <Siren aria-hidden />
                    {t("declare")}
                  </Link>
                </Button>
              ) : null}
              {caps.check ? (
                <Button asChild variant="outline" className="min-h-12 text-base sm:min-h-control sm:text-sm">
                  <Link href="/emergency-asset-checks/new" data-testid="board-check">
                    <ClipboardCheck aria-hidden />
                    {t("check")}
                  </Link>
                </Button>
              ) : null}
            </div>
          ) : null
        }
      />
      <EmReportSubNav />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : b ? (
        <div className="flex flex-col gap-4" data-testid="emergency-board">
          <p className="text-sm text-muted-foreground">{t("at", { time: dateTime(b.at) })}</p>
          {b.active_events.length ? (
            <section className="flex flex-col gap-2" data-testid="board-events">
              {b.active_events.map((e) => (
                <Link key={e.id} href={`/emergency-events/${e.id}`} className="flex flex-wrap items-center gap-3 rounded-md border-2 border-danger/60 bg-danger-bg px-4 py-3 text-danger" data-testid="board-event">
                  <Siren aria-hidden className="size-7 shrink-0" />
                  <span className="flex flex-col">
                    <span className="text-lg font-bold">
                      <EventType code={e.event_type} /> · <Code>{e.site_code}</Code>
                    </span>
                    <span className="text-sm">
                      <Code>{e.event_no}</Code> · {t("since", { time: dateTime(e.raised_at) })}
                    </span>
                  </span>
                  <ArrowRight aria-hidden className="ms-auto size-5 rtl:-scale-x-100" />
                </Link>
              ))}
            </section>
          ) : null}
          {b.open_musters.length ? (
            <section className="flex flex-col gap-2" data-testid="board-musters">
              <h2 className="text-sm font-semibold text-muted-foreground">{t("openMusters")}</h2>
              {b.open_musters.map((m) => (
                <Link key={m.id} href={`/musters/${m.id}`} className="flex flex-wrap items-center gap-3 rounded-md border border-warning/50 bg-warning-bg px-4 py-3" data-testid="board-muster">
                  <Users aria-hidden className="size-6 text-warning" />
                  <Code className="font-semibold">{m.muster_no}</Code>
                  <span className="text-base font-semibold tabular-nums">
                    <bdi className="ltr">
                      {m.accounted + m.resolved} / {m.expected}
                    </bdi>
                  </span>
                  {m.unaccounted ? <Badge tone="danger">{t("unaccounted", { n: m.unaccounted })}</Badge> : null}
                  <MusterStatusBadge status={m.status} />
                  <ArrowRight aria-hidden className="ms-auto size-5 rtl:-scale-x-100" />
                </Link>
              ))}
            </section>
          ) : null}
          <ErpCard erp={b.erp} />
          {b.sites.length ? (
            <div className="grid gap-3 lg:grid-cols-2">
              {b.sites.map((s) => (
                <SiteCard key={s.site_id} s={s} prefs={prefs} />
              ))}
            </div>
          ) : (
            <EmptyState message={t("noSites")} />
          )}
        </div>
      ) : null}
    </div>
  );
}

function EventType({ code }: { code: string }) {
  const { label } = useEmRef();
  return <>{label("event_types", code)}</>;
}

/** ERP status and review date (ER-7: an overdue plan stays the plan in force). */
export function ErpCard({ erp }: { erp: S["ErpRead"] | null }) {
  const t = useTranslations("emergency.board");
  const { date } = useFormatters();
  return (
    <Card data-testid="board-erp" data-in-force={erp?.in_force ? "yes" : "no"}>
      <CardContent className="flex flex-wrap items-center gap-x-4 gap-y-2 p-4">
        <FileText aria-hidden className="size-6 text-muted-foreground" />
        {erp ? (
          <>
            <Link href={`/emergency-plans/${erp.id}`} className="font-semibold text-primary hover:underline">
              <Code>{erp.erp_no}</Code>
            </Link>
            <ErpStatusBadge status={erp.status} />
            <span className="text-sm">{t("reviewDue", { date: date(erp.review_due_on) })}</span>
            {erp.overdue ? (
              <Badge tone="danger" data-testid="erp-overdue">
                <CalendarClock aria-hidden />
                {t("erpOverdue")}
              </Badge>
            ) : null}
            {erp.review_required ? (
              <Badge tone="warning" data-testid="erp-review-required">
                <ShieldAlert aria-hidden />
                {t("reviewRequired")}
              </Badge>
            ) : null}
          </>
        ) : (
          <Badge tone="danger" data-testid="erp-none">
            {t("noErp")}
          </Badge>
        )}
      </CardContent>
    </Card>
  );
}

function SiteCard({ s, prefs }: { s: S["BoardSite"]; prefs: ReturnType<typeof useFormatters>["prefs"] }) {
  const t = useTranslations("emergency.board");
  const te = useTranslations("enums");
  const { label } = useEmRef();
  const c = s.coverage;
  void prefs;
  return (
    <Card className={cn("border-s-8", c?.state === "short" ? "border-s-danger" : c?.state === "covered" ? "border-s-success" : "border-s-neutral")} data-testid="board-site" data-site={s.site_code} data-state={c?.state ?? "none"}>
      <CardHeader className="pb-2">
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          <Code>{s.site_code}</Code>
          <span className="text-sm font-normal text-muted-foreground">{t("shiftNow", { shift: te(`emShift.${s.shift}`) })}</span>
          {c ? <CoverageBadge state={c.state} /> : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {c ? (
          <div className="grid grid-cols-2 gap-2" data-testid="board-coverage">
            <Counter icon={<HeartPulse aria-hidden className="size-5" />} label={t("firstAiders")} have={c.first_aiders_counted} need={c.first_aiders_required} testId="fa" />
            <Counter icon={<ShieldAlert aria-hidden className="size-5" />} label={t("wardens")} have={c.wardens_counted} need={c.wardens_required} testId="fw" />
            <p className="col-span-2 text-xs text-muted-foreground">
              {t("headcount", { n: c.headcount })}
              {c.zones_without_warden.length ? (
                <>
                  {" · "}
                  {t("zonesWithoutWarden")} <Codes items={c.zones_without_warden} />
                </>
              ) : null}
              {!c.coordinator_ok ? <> · {t("noCoordinator")}</> : null}
            </p>
          </div>
        ) : (
          <p className="rounded-md border border-neutral/40 bg-neutral-bg px-3 py-2 text-neutral" data-testid="board-no-coverage">
            {t("noReturns")}
          </p>
        )}
        {s.provision_gaps.length ? (
          <div className="rounded-md border border-warning/40 bg-warning-bg px-3 py-2 text-warning" data-testid="provision-gaps">
            <p className="font-medium">{t("provisionGaps")}</p>
            <ul className="list-inside list-disc text-xs">
              {s.provision_gaps.map((g) => (
                <li key={g}>
                  <bdi>{g}</bdi>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <div>
          <p className="mb-1 font-medium">{t("nextDrills")}</p>
          {s.next_drills_due.length ? (
            <ul className="flex flex-col divide-y rounded-md border" data-testid="board-next-drills">
              {s.next_drills_due.slice(0, 4).map((l) => (
                <li key={l.line_no} className="flex flex-wrap items-center gap-2 px-3 py-2" data-testid="board-line" data-line={l.line_no}>
                  <span className="font-medium">{label("drill_types", l.drill_type)}</span>
                  <LineQualifiers l={l} />
                  <span className="ms-auto whitespace-nowrap text-xs">
                    <StackedDate v={l.due_by} />
                  </span>
                  <LineStatusBadge status={l.status} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-muted-foreground">—</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function LineQualifiers({ l }: { l: S["ProgrammeLine"] }) {
  const te = useTranslations("enums");
  return (
    <span className="inline-flex flex-wrap gap-1 text-xs">
      {l.shift_requirement === "night" ? <Badge tone="info">{te("emShift.night")}</Badge> : null}
      {l.announcement_requirement === "unannounced" ? <Badge tone="info">{te("emAnnounced.unannounced")}</Badge> : null}
      {l.source === "repeat" ? <Badge tone="warning">{te("emLineSource.repeat")}</Badge> : null}
    </span>
  );
}

function Counter({ icon, label, have, need, testId }: { icon: React.ReactNode; label: string; have: number; need: number; testId: string }) {
  const short = have < need;
  return (
    <div className={cn("flex items-center gap-2 rounded-md border px-3 py-2", short ? "border-danger/50 bg-danger-bg text-danger" : "border-success/40 bg-success-bg text-success")} data-testid={`counter-${testId}`} data-short={short ? "yes" : "no"}>
      {icon}
      <span className="flex flex-col">
        <span className="text-xs">{label}</span>
        <span className="text-xl font-bold tabular-nums">
          <bdi className="ltr">
            {have} / {need}
          </bdi>
        </span>
      </span>
    </div>
  );
}

/* ═════════════ action panel (§8.2) ═════════════ */

const ACTION_HREF: Record<S["EmergencyActionKind"], string> = {
  erp_overdue: "/emergency-plans",
  erp_review_required: "/emergency-plans",
  zone_without_assembly_point: "/assembly-points",
  active_events: "/emergency-events?status=active",
  open_musters_unaccounted: "/emergency-board",
  coverage_shortfall: "/emergency-coverage",
  programme_overdue: "/drill-programme",
  drill_evaluation_overdue: "/drills?status=conducted",
  event_review_overdue: "/emergency-events?status=all_clear",
  assets_out_of_service: "/emergency-assets?status=out_of_service",
  asset_checks_overdue: "/emergency-assets?reason=CHECK_OVERDUE",
  provision_gaps: "/emergency-board",
  rescue_teams_not_current: "/rescue-teams",
  cse_permits_team_not_current: "/permits?status=active",
  permits_still_drill_suspended: "/permits?status=suspended",
};

export function EmergencyActionsPage() {
  return <ProjectGate>{(p) => <Actions project={p} />}</ProjectGate>;
}

function Actions({ project }: { project: Project }) {
  const t = useTranslations("emergency.actions");
  const tc = useTranslations("common");
  const ar = useLocale() === "ar";
  const caps = useEmCaps(project.id);
  const q = useEmergencyActionPanel(project.id, { enabled: caps.kpi });
  if (!caps.kpi) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <EmReportSubNav />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <ul className="flex flex-col divide-y rounded-md border" data-testid="emergency-actions">
          {items.map((i) => (
            <li key={i.kind} className="flex flex-wrap items-center gap-3 px-4 py-3" data-testid="em-action" data-kind={i.kind}>
              <span className="min-w-10 rounded-md bg-warning-bg px-2 py-1 text-center text-lg font-bold text-warning tabular-nums">{i.count}</span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="font-medium">{ar ? i.label_ar : i.label_en}</span>
                {i.refs.length ? <Codes items={i.refs.slice(0, 12)} /> : null}
              </span>
              <Link href={ACTION_HREF[i.kind]} className="inline-flex min-h-touch items-center gap-1 text-sm text-primary hover:underline">
                {t("open")}
                <ArrowRight aria-hidden className="size-4 rtl:-scale-x-100" />
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState message={t("empty")} />
      )}
    </div>
  );
}

/* ═════════════ emergency information (PE-6) ═════════════ */

export function EmergencyInfoPage() {
  return <ProjectGate>{(p) => <Info project={p} />}</ProjectGate>;
}

function Info({ project }: { project: Project }) {
  const t = useTranslations("emergency.info");
  const tc = useTranslations("common");
  const caps = useEmCaps(project.id);
  const opts = useProjectOptions(project.id);
  const [zones, setZones] = useState<string[]>([]);
  const q = useEmergencyInfo(project.id, zones, { enabled: caps.view });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <EmPlanSubNav />
      <ListToolbar>
        <MultiSelect id="ei-zones" label={t("zones")} options={opts.zones} value={zones} onChange={setZones} allLabel={t("chooseZones")} testId="ei-zones" />
      </ListToolbar>
      {!zones.length ? (
        <EmptyState message={t("pick")} />
      ) : q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data ? (
        <Card data-testid="emergency-info">
          <CardContent className="flex flex-col gap-3 p-4">
            <p className="text-base" data-testid="ei-text">
              <bdi>{q.data.text}</bdi>
            </p>
            <p className="text-sm">
              {t("ap")} <Code data-testid="ei-ap">{q.data.assembly_point_code ?? "—"}</Code>
            </p>
            <ul className="flex flex-wrap gap-2" data-testid="ei-numbers">
              {q.data.numbers.map((n) => (
                <li key={n}>
                  <a href={`tel:${n}`} className="inline-flex min-h-touch items-center gap-1 rounded-md border px-3 text-base font-semibold">
                    <Phone aria-hidden className="size-4" />
                    <bdi className="ltr">{n}</bdi>
                  </a>
                </li>
              ))}
            </ul>
            <p className="text-xs text-muted-foreground">{t("hint")}</p>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

/* ═════════════ KPIs K-104…K-109 (§6.8) ═════════════ */

export function EmergencyKpiPage() {
  return <ProjectGate>{(p) => <Kpis project={p} />}</ProjectGate>;
}

const PERIODS = ["month", "quarter", "year", "ytd"] as const satisfies readonly S["PeriodPreset"][];

/** Every number is the server's `display`; nothing is computed here (EM-1). */
function Kpis({ project }: { project: Project }) {
  const t = useTranslations("emergency.kpi");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const ar = useLocale() === "ar";
  const caps = useEmCaps(project.id);
  const show = useDisplay(project.id);
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const groupBy = (s.get("group_by") as S["EmergencyKpiGroupBy"]) || "site";
  const period = (s.get("period") as (typeof PERIODS)[number]) || "month";
  const anchor = s.get("anchor") ?? "";
  const q = useEmergencyKpis({ project_id: [project.id], group_by: [groupBy], period, anchor: anchor || null }, { enabled: caps.kpi });
  if (!caps.kpi) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const d = q.data;
  const label = (x: { label_en: string; label_ar: string }) => (ar ? x.label_ar : x.label_en);
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <EmReportSubNav />
      <ListToolbar>
        <SelectFilter id="ek-period" label={t("period")} value={period} onChange={(v) => s.set({ period: v })} options={PERIODS.map((p) => ({ value: p, label: te(`period.${p}`) }))} allLabel={te("period.month")} />
        <DateFilter id="ek-anchor" label={t("anchor")} value={anchor} onChange={(v) => s.set({ anchor: v })} />
        <SelectFilter id="ek-group" label={t("groupBy")} value={groupBy} onChange={(v) => s.set({ group_by: v })} options={EM_KPI_GROUP_BY.map((g) => ({ value: g, label: te(`emKpiGroupBy.${g}`) }))} allLabel={te("emKpiGroupBy.site")} />
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
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid="em-tiles">
            {d.metrics.map((m) => (
              <Card key={m.metric} data-testid="em-tile" data-metric={m.metric}>
                <CardContent className="flex flex-col gap-1 p-4">
                  <span className="flex items-center justify-between gap-2 text-xs font-medium text-muted-foreground">
                    <span>{ar ? m.short_label_ar : m.short_label_en}</span>
                    <span className="font-mono ltr">{m.metric}</span>
                  </span>
                  <span className={cn("text-3xl font-semibold tabular-nums", m.rag === "red" && "text-danger", m.rag === "amber" && "text-warning")} data-testid="em-value">
                    {show(m.display)}
                  </span>
                  {m.null_reason ? <span className="text-xs text-muted-foreground">{te(`nullReason.${m.null_reason}`)}</span> : null}
                  {m.components.length ? (
                    <span className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                      {m.components.map((c) => (
                        <span key={c.key} data-testid="em-component" data-key={c.key}>
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
              <CardTitle className="text-base">{t("breakdown", { by: te(`emKpiGroupBy.${groupBy}`) })}</CardTitle>
              <p className="text-xs text-muted-foreground">{t("aggregatesHint")}</p>
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

function Breakdown({ breakdowns, metrics, show }: { breakdowns: S["EmergencyBreakdown"][]; metrics: S["KpiValue"][]; show: (v: string) => string }) {
  const t = useTranslations("emergency.kpi");
  const ar = useLocale() === "ar";
  if (!breakdowns.length || breakdowns.every((b) => !b.rows.length)) return <EmptyState message={t("noBreakdown")} />;
  const keys: { key: string; label: string }[] = [];
  for (const b of breakdowns) for (const r of b.rows) if (!keys.some((k) => k.key === r.key)) keys.push({ key: r.key, label: ar ? r.label_ar : r.label_en });
  const metricLabel = (id: string) => {
    const m = metrics.find((x) => x.metric === id);
    return m ? (ar ? m.short_label_ar : m.short_label_en) : id;
  };
  return (
    <Table data-testid="em-breakdown">
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
          <TR key={k.key} data-testid="em-row" data-key={k.key}>
            <TD label={t("key")}>
              <bdi>{k.label}</bdi>
            </TD>
            {breakdowns.map((b) => {
              const r = b.rows.find((x) => x.key === k.key);
              return (
                <Fragment key={b.metric}>
                  <TD label={metricLabel(b.metric)} className="text-end tabular-nums" data-testid="em-cell" data-metric={b.metric}>
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
