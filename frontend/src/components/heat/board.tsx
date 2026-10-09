"use client";
import { Ban, ClipboardList, Plus, ShieldAlert, Sun, Thermometer, Users } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { ProjectGate } from "@/components/common/project-gate";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { Code, WorkerLabel } from "@/components/access/common";
import { DateFilter } from "@/components/training/common";
import { Link } from "@/i18n/navigation";
import type { Schemas } from "@/lib/api/client";
import { useHeatBoard, useHeatDutyList } from "@/lib/api/heat";
import { formatTime } from "@/lib/datetime";
import { WORKLOADS } from "@/lib/heat-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { HeatFieldSubNav, HeatStateBadge, RegimeBadge, RestMinutes, WaterAdvice, Wbgt, useHeatCaps } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];

/* ═════════════ heat board (§8.1 heat band, §6.3; phone-first for supervisors) ═════════════ */

export function HeatBoardPage() {
  return <ProjectGate>{(p) => <Board project={p} />}</ProjectGate>;
}

function Board({ project }: { project: Project }) {
  const t = useTranslations("heat.board");
  const tc = useTranslations("common");
  const caps = useHeatCaps(project.id);
  const opts = useProjectOptions(project.id);
  const { prefs } = useFormatters(project.id);
  const q = useHeatBoard(project.id, { enabled: caps.view });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const b = q.data;
  const bySite = new Map<string, S["ZoneHeatState"][]>();
  for (const z of b?.zones ?? []) bySite.set(z.site_id, [...(bySite.get(z.site_id) ?? []), z]);
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.record ? (
            <Button asChild className="min-h-12 text-base sm:min-h-control sm:text-sm">
              <Link href="/wbgt-readings/new" data-testid="board-record">
                <Plus aria-hidden />
                {t("record")}
              </Link>
            </Button>
          ) : null
        }
      />
      <HeatFieldSubNav />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : b ? (
        <div className="flex flex-col gap-4" data-testid="heat-board">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-muted-foreground">{t("at", { time: formatTime(b.at, prefs) })}</span>
            <Badge tone={b.in_controls_period ? "warning" : "neutral"} data-testid="controls-period" data-on={b.in_controls_period ? "yes" : "no"}>
              <Sun aria-hidden />
              {b.in_controls_period ? t("inControls") : t("outsideControls")}
            </Badge>
            {b.ban_in_force ? (
              <Badge tone="danger" data-testid="ban-in-force">
                <Ban aria-hidden />
                {t("banInForce")}
              </Badge>
            ) : null}
            <Link href="/acclimatisation-plans?status=active" className="inline-flex items-center gap-1 text-primary hover:underline" data-testid="acclimatising-today">
              <Users aria-hidden className="size-4" />
              {t("acclimatising", { n: b.acclimatising_today })}
            </Link>
            {caps.log ? (
              <Link href="/heat-illness-log?status=open" className="inline-flex items-center gap-1 text-primary hover:underline" data-testid="open-reviews">
                <ClipboardList aria-hidden className="size-4" />
                {t("openReviews", { n: b.open_reviews })}
              </Link>
            ) : null}
          </div>
          {b.coverage_gaps.length ? (
            <Alert tone="warning" data-testid="coverage-gaps">
              <ShieldAlert aria-hidden className="inline size-4" /> {t("coverageGaps", { zones: b.coverage_gaps.join(", ") })}
            </Alert>
          ) : null}
          <WaterAdvice en={b.water_advice_en} ar={b.water_advice_ar} />
          {b.zones.length ? (
            [...bySite.entries()].map(([siteId, zones]) => (
              <section key={siteId} className="flex flex-col gap-2">
                <h2 className="text-sm font-semibold text-muted-foreground">{opts.sites.find((s) => s.value === siteId)?.label ?? ""}</h2>
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {zones.map((z) => (
                    <ZoneCard key={z.zone_id} z={z} record={caps.record} />
                  ))}
                </div>
              </section>
            ))
          ) : (
            <EmptyState message={t("noZones")} />
          )}
        </div>
      ) : null}
    </div>
  );
}

const CARD_TONE: Record<S["Regime"], string> = {
  R0: "border-s-success",
  R1: "border-s-info",
  R2: "border-s-warning",
  R3: "border-s-warning",
  R4: "border-s-danger bg-danger-bg",
  unknown: "border-s-neutral",
};

/** One zone: WBGT and its age, state, the headline regime large, ban and exemptions, then every cell (WR-4). */
export function ZoneCard({ z, record }: { z: S["ZoneHeatState"]; record?: boolean }) {
  const t = useTranslations("heat.board");
  const te = useTranslations("enums");
  const { prefs } = useFormatters();
  return (
    <Card className={cn("border-s-8", CARD_TONE[z.headline_regime])} data-testid="zone-card" data-zone={z.zone_code} data-regime={z.headline_regime} data-state={z.state}>
      <CardContent className="flex flex-col gap-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="flex flex-col">
            <Code className="text-base font-semibold">{z.zone_code}</Code>
            <span className="text-xs text-muted-foreground">
              {z.point_code ? (
                <>
                  {t("point")} <Code>{z.point_code}</Code>
                </>
              ) : (
                t("noPoint")
              )}
              {z.required ? <> · {t("required")}</> : null}
            </span>
          </div>
          <HeatStateBadge state={z.state} />
        </div>
        <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
          <span className="flex items-center gap-1.5 text-3xl font-bold" data-testid="zone-wbgt">
            <Thermometer aria-hidden className="size-6 text-muted-foreground" />
            <Wbgt v={z.wbgt_c} />
          </span>
          {z.measured_at ? (
            <span className="pb-1 text-xs text-muted-foreground">
              <bdi className="ltr">{formatTime(z.measured_at, prefs)}</bdi> · {t("age", { n: z.age_minutes ?? 0 })}
            </span>
          ) : null}
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">{t("headline", { workload: te(`workload.${z.headline_workload}`) })}</span>
          <span className="flex flex-wrap items-center gap-2">
            <RegimeBadge regime={z.headline_regime} className="px-3 py-1 text-sm [&_svg]:size-4" />
            <RestMinutes regime={z.headline_regime} minutes={z.rest_minutes_per_hour} />
          </span>
        </div>
        {z.ban_in_force || z.active_exemptions.length ? (
          <div className="flex flex-wrap gap-1.5 text-xs">
            {z.ban_in_force ? (
              <Badge tone="danger">
                <Ban aria-hidden />
                {t("banInForce")}
              </Badge>
            ) : null}
            {z.active_exemptions.map((x) => (
              <Badge key={x} tone="info">
                {t("exemption")} <Code>{x}</Code>
              </Badge>
            ))}
          </div>
        ) : null}
        <CellsTable cells={z.cells} />
        {record ? (
          <Button asChild variant="outline" size="sm" className="min-h-11 sm:min-h-control">
            <Link href={`/wbgt-readings/new?zone=${z.zone_id}`} data-testid="zone-record">
              <Plus aria-hidden />
              {t("recordHere")}
            </Link>
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

/** Regime per (basis × workload): acclimatised (TLV) and unacclimatised (Action Limit) rows. */
export function CellsTable({ cells }: { cells: S["RegimeCell"][] }) {
  const t = useTranslations("heat.board");
  const te = useTranslations("enums");
  return (
    <table className="w-full table-fixed text-xs" data-testid="regime-cells">
      <thead>
        <tr className="text-muted-foreground">
          <th className="w-24 py-1 text-start font-normal" />
          {WORKLOADS.map((w) => (
            <th key={w} className="py-1 text-center font-normal">
              {te(`workload.${w}`)}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {(["acclimatised", "unacclimatised"] as const).map((basis) => (
          <tr key={basis} className="border-t">
            <th scope="row" className="py-1.5 text-start font-medium">
              {t(`basis.${basis}`)}
            </th>
            {WORKLOADS.map((w) => {
              const c = cells.find((x) => x.basis === basis && x.workload === w);
              return (
                <td key={w} className="py-1.5 text-center" data-testid="cell" data-basis={basis} data-workload={w} data-regime={c?.regime ?? ""}>
                  {c ? <RegimeBadge regime={c.regime} short className="px-1.5" /> : "—"}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ═════════════ heat duty list (§8.4, AP-9) ═════════════ */

export function HeatDutyListPage() {
  return <ProjectGate>{(p) => <Duty project={p} />}</ProjectGate>;
}

function Duty({ project }: { project: Project }) {
  const t = useTranslations("heat.duty");
  const tc = useTranslations("common");
  const locale = useLocale();
  const caps = useHeatCaps(project.id);
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const day = s.get("day") ?? "";
  const eng = s.get("engagement") ?? "";
  const q = useHeatDutyList(project.id, { day: day || null, engagement_id: eng || null }, { enabled: caps.view });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const d = q.data;
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <HeatFieldSubNav />
      <ListToolbar>
        <DateFilter id="duty-day" label={t("day")} value={day} onChange={(v) => s.set({ day: v })} />
        <SelectFilter id="duty-eng" label={t("engagement")} value={eng} onChange={(v) => s.set({ engagement: v })} options={opts.engagements.map((e) => ({ value: e.value, label: e.label }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : d ? (
        <div className="flex flex-col gap-6">
          <section>
            <h2 className="mb-2 text-base font-semibold">{t("acclimatising")}</h2>
            {d.acclimatising.length ? (
              <Table data-testid="duty-acclimatising">
                <THead>
                  <TR>
                    <TH>{t("worker")}</TH>
                    <TH>{t("plan")}</TH>
                    <TH>{t("dayNo")}</TH>
                    <TH>{t("maxPct")}</TH>
                    <TH>{t("maxMinutes")}</TH>
                  </TR>
                </THead>
                <TBody>
                  {d.acclimatising.map((w) => (
                    <TR key={w.worker.id} data-testid="duty-row">
                      <TD label={t("worker")}>
                        <WorkerLabel w={w.worker} />
                      </TD>
                      <TD label={t("plan")}>{w.plan_no ? <Code>{w.plan_no}</Code> : "—"}</TD>
                      <TD label={t("dayNo")}>{w.day_no ?? "—"}</TD>
                      <TD label={t("maxPct")}>
                        <bdi className="ltr">{w.max_pct != null ? `${w.max_pct} %` : "—"}</bdi>
                      </TD>
                      <TD label={t("maxMinutes")}>{w.max_minutes != null ? t("minutes", { n: w.max_minutes }) : "—"}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            ) : (
              <EmptyState message={t("noneAcclimatising")} />
            )}
          </section>
          <section>
            <h2 className="mb-2 text-base font-semibold">{t("notForHeat")}</h2>
            {d.not_for_heat_work.length ? (
              <ul className="flex flex-col divide-y rounded-md border" data-testid="duty-not-for-heat">
                {d.not_for_heat_work.map((w) => (
                  <li key={w.worker.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm" data-testid="duty-not-row">
                    <WorkerLabel w={w.worker} />
                    <Badge tone="danger">
                      <Ban aria-hidden />
                      {locale === "ar" ? w.label_ar : w.label_en}
                    </Badge>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState message={t("noneNotForHeat")} />
            )}
          </section>
          <section>
            <h2 className="mb-2 text-base font-semibold">{t("zonesNow")}</h2>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {d.zones.map((z) => (
                <ZoneCard key={z.zone_id} z={z} />
              ))}
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
