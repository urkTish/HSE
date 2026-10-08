"use client";
import { Layers, Plane, Radio, TriangleAlert, Users } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { Link } from "@/i18n/navigation";
import type { Schemas } from "@/lib/api/client";
import { useProjectSuspensions, usePtwBoard } from "@/lib/api/ptw";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { PERMIT_TYPES, STATUS_REASONS } from "@/lib/ptw-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { Countdown, GasStatusBadge, HighRiskBadge, PermitNo, PermitStatusBadge, PermitsSubNav, TypeChips, userLabel } from "./common";

type S = Schemas;
const PAGE_SIZE = 50;

/* ───────────── live permit board ───────────── */

export function PtwBoardPage() {
  return <ProjectGate>{(p) => <PtwBoard project={p} />}</ProjectGate>;
}

function PtwBoard({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("ptwBoard");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const name = useLocalizedName();
  const opts = useProjectOptions(project.id);
  const s = useSearchState();
  const types = s.getAll("work_type") as S["PermitType"][];
  const zones = s.getAll("zone_id");
  const q = usePtwBoard(project.id, { site_id: s.get("site_id") || null, zone_id: zones.length ? zones : null, work_type: types.length ? types : null });
  const { dateTime } = useFormatters(project.id);
  const data = q.data;
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <PermitsSubNav />
      <ListToolbar>
        <SelectFilter id="pb-site" label={tc("site")} value={s.get("site_id") ?? ""} onChange={(v) => s.set({ site_id: v })} options={opts.sites.map((x) => ({ value: x.value, label: x.label }))} />
        <MultiSelect id="pb-zone" label={tc("zone")} options={opts.zones.map((z) => ({ value: z.value, label: z.label }))} value={zones} onChange={(v) => s.set({ zone_id: v })} />
        <MultiSelect id="pb-type" label={t("workType")} options={PERMIT_TYPES.map((x) => ({ value: x, label: te(`permitType.${x}`) }))} value={types} onChange={(v) => s.set({ work_type: v })} />
      </ListToolbar>
      {data ? (
        <div className="mb-4 flex flex-wrap items-center gap-2 text-sm" data-testid="board-counts">
          {Object.entries(data.counts).map(([k, v]) => (
            <span key={k} className="rounded-md border px-2 py-1" data-key={k}>
              {te.has(`permitStatus.${k}` as "permitStatus.active") ? te(`permitStatus.${k}` as "permitStatus.active") : t.has(`count.${k}` as "count.blocked") ? t(`count.${k}` as "count.blocked") : k}: <span className="font-semibold tabular-nums">{v}</span>
            </span>
          ))}
          <span className="ms-auto inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Radio aria-hidden className="size-3.5 text-success" />
            {t("liveAt", { at: dateTime(data.at) })}
          </span>
        </div>
      ) : null}
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : !data || data.zones.length === 0 ? (
        <EmptyState message={t("empty")} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" data-testid="ptw-board">
          {data.zones.map((z) => (
            <Card key={z.zone.id} data-testid="board-zone" data-zone={z.zone.code}>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center justify-between gap-2 text-base">
                  <span>
                    <bdi className="ltr font-mono">{z.zone.code}</bdi> {name(z.zone.name_en, z.zone.name_ar)}
                  </span>
                  <span className="text-xs font-normal text-muted-foreground tabular-nums">{z.permits.length}</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                {z.permits.map((p) => (
                  <BoardCard key={p.id} p={p} />
                ))}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

const ROUTINE: string[] = ["shift_end", "shift_lapsed", "midday_ban"];

function BoardCard({ p }: { p: S["BoardPermit"] }) {
  const t = useTranslations("ptwBoard");
  const te = useTranslations("enums");
  return (
    <Link
      href={`/permits/${p.id}`}
      className={cn(
        "flex flex-col gap-1.5 rounded-lg border p-2.5 hover:bg-accent",
        p.status === "active" && p.in_window_now && "border-s-4 border-s-success",
        // Routine suspensions (shift end, midday ban) are amber; stop-work, gas and other suspensions red.
        p.status === "suspended" && (ROUTINE.includes(p.status_reason ?? "other") ? "border-s-4 border-s-warning" : "border-s-4 border-s-danger"),
        p.blockers.length > 0 && p.status !== "suspended" && "border-s-4 border-s-warning",
      )}
      data-testid="board-permit"
      data-status={p.status}
      data-permit-no={p.permit_no}
    >
      <span className="flex flex-wrap items-center justify-between gap-2">
        <bdi className="ltr font-semibold">{p.display_no}</bdi>
        <PermitStatusBadge status={p.status} reason={p.status_reason} />
      </span>
      <span className="flex flex-wrap items-center gap-1">
        <TypeChips types={p.work_types} primary={p.primary_type} short />
        <HighRiskBadge show={p.high_risk} />
      </span>
      <span className="line-clamp-2 text-sm" dir="auto">
        {p.title}
      </span>
      <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span>{p.engagement_code}</span>
        {p.window_today ? <bdi className={cn("ltr tabular-nums", p.in_window_now && "font-semibold text-success")}>{p.window_today}</bdi> : <span>{t("noWindowToday")}</span>}
        <span className="inline-flex items-center gap-1">
          <Users aria-hidden className="size-3.5" />
          <bdi className="ltr tabular-nums">{p.crew_present_count !== null ? `${p.crew_present_count}/${p.crew_count}` : p.crew_count}</bdi>
        </span>
        {p.persons_inside !== null ? <span data-testid="board-inside">{t("inside", { n: p.persons_inside })}</span> : null}
      </span>
      <span className="flex flex-wrap items-center gap-2">
        {p.gas_status !== "not_required" ? <GasStatusBadge status={p.gas_status} /> : null}
        {p.gas_next_due_at ? <Countdown to={p.gas_next_due_at} label={t("gasDue")} warnMinutes={15} testId="board-gas-due" /> : null}
        {p.shift_planned_end_at ? <Countdown to={p.shift_planned_end_at} label={t("shiftEnds", { n: p.shift_no ?? 1 })} warnMinutes={30} testId="board-shift-end" /> : null}
        {p.fire_watch_until ? <Countdown to={p.fire_watch_until} label={t("fireWatch")} icon="fire" testId="board-fire-watch" /> : null}
      </span>
      {p.simops_chips.length || p.wap_chip || p.notam_chip ? (
        <span className="flex flex-wrap gap-1">
          {p.simops_chips.map((c) => (
            <Badge key={c} tone="warning" data-testid="board-simops">
              <Layers aria-hidden />
              <bdi className="ltr">{c}</bdi>
            </Badge>
          ))}
          {p.wap_chip ? (
            <Badge tone="info">
              <Plane aria-hidden />
              <bdi className="ltr">{p.wap_chip}</bdi>
            </Badge>
          ) : null}
          {p.notam_chip ? (
            <Badge tone="info">
              <bdi className="ltr">{p.notam_chip}</bdi>
            </Badge>
          ) : null}
        </span>
      ) : null}
      {p.blockers.length ? (
        <span className="flex flex-wrap gap-1" data-testid="board-blockers">
          {p.blockers.map((b) => (
            <Badge key={b} tone="danger">
              <TriangleAlert aria-hidden />
              {te.has(`permitBlocker.${b}` as "permitBlocker.JSA_MISSING") ? te(`permitBlocker.${b}` as "permitBlocker.JSA_MISSING") : b}
            </Badge>
          ))}
        </span>
      ) : null}
    </Link>
  );
}

/* ───────────── suspension log ───────────── */

export function SuspensionLogPage() {
  return <ProjectGate>{(p) => <SuspensionLog project={p} />}</ProjectGate>;
}

function SuspensionLog({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("ptwBoard");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const opts = useProjectOptions(project.id);
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const reasons = s.getAll("reason") as S["StatusReason"][];
  const types = s.getAll("work_type") as S["PermitType"][];
  const engs = s.getAll("engagement_id");
  const q = useProjectSuspensions(project.id, {
    reason: reasons.length ? reasons : null,
    work_type: types.length ? types : null,
    engagement_id: engs.length ? engs : null,
    open_only: s.getBool("open_only") ?? undefined,
    date_from: s.get("date_from") || null,
    date_to: s.get("date_to") || null,
    page,
    page_size: PAGE_SIZE,
  });
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("suspensions")} description={t("suspensionsHint")} />
      <PermitsSubNav />
      <ListToolbar>
        <MultiSelect id="sl-reason" label={t("reason")} options={STATUS_REASONS.map((x) => ({ value: x, label: te(`statusReason.${x}`) }))} value={reasons} onChange={(v) => s.set({ reason: v })} />
        <MultiSelect id="sl-type" label={t("workType")} options={PERMIT_TYPES.map((x) => ({ value: x, label: te(`permitType.${x}`) }))} value={types} onChange={(v) => s.set({ work_type: v })} />
        <MultiSelect id="sl-eng" label={tc("contractor")} options={opts.engagements} value={engs} onChange={(v) => s.set({ engagement_id: v })} allLabel={tc("anyContractor")} />
        <SelectFilter id="sl-open" label={t("openOnly")} value={s.get("open_only") === "true" ? "true" : ""} onChange={(v) => s.set({ open_only: v })} options={[{ value: "true", label: tc("yes") }]} />
        <FormField id="sl-from" label={t("from")}>
          <Input id="sl-from" type="date" className="ltr" value={s.get("date_from") ?? ""} onChange={(e) => s.set({ date_from: e.target.value })} />
        </FormField>
        <FormField id="sl-to" label={t("to")}>
          <Input id="sl-to" type="date" className="ltr" value={s.get("date_to") ?? ""} onChange={(e) => s.set({ date_to: e.target.value })} />
        </FormField>
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="suspensions-table">
            <THead>
              <TR>
                <TH>{t("permit")}</TH>
                <TH>{t("reason")}</TH>
                <TH>{t("suspendedAt")}</TH>
                <TH>{t("raisedBy")}</TH>
                <TH>{t("resumedAt")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((x) => (
                <TR key={x.id} data-testid="suspension-row" data-reason={x.reason}>
                  <TD label={t("permit")}>
                    <PermitNo p={x.permit} />
                    <span className="block text-xs text-muted-foreground">
                      {x.engagement.short_code} · <bdi className="ltr">{x.zone_codes.join(", ")}</bdi>
                    </span>
                  </TD>
                  <TD label={t("reason")}>
                    {te(`statusReason.${x.reason}`)}
                    {x.routine ? <span className="ms-1 text-xs text-muted-foreground">({t("routine")})</span> : null}
                    {x.detail ? <span className="block text-xs text-muted-foreground">{x.detail}</span> : null}
                  </TD>
                  <TD label={t("suspendedAt")}>
                    <span className="ltr">{dateTime(x.suspended_at)}</span>
                  </TD>
                  <TD label={t("raisedBy")}>{x.raised_by ? userLabel(x.raised_by, locale) : x.auto_source_ref ? <bdi className="ltr">{x.auto_source_ref}</bdi> : t("system")}</TD>
                  <TD label={t("resumedAt")}>
                    {x.resumed_at ? (
                      <>
                        <span className="ltr">{dateTime(x.resumed_at)}</span>
                        {x.resumed_by ? <span className="block text-xs text-muted-foreground">{userLabel(x.resumed_by, locale)}</span> : null}
                      </>
                    ) : (
                      <span className="text-warning">{t("stillSuspended")}</span>
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState />
      )}
    </div>
  );
}
