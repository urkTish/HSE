"use client";
import { ArrowRight, CalendarClock, CloudFog, FileWarning, Hourglass, Plane, Truck, TriangleAlert, Wind } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Fragment, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Code } from "@/components/access/common";
import { DateFilter } from "@/components/training/common";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useEnvActionPanel, useEnvBand, useEnvKpis, useEnvRefresh, useEnvSettings } from "@/lib/api/env";
import { useDisplay } from "@/lib/digits";
import { ENV_KPI_GROUP_BY, WASTE_CLASSES } from "@/lib/env-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { Check, EnvOverviewSubNav, useEnvCaps, useEnvRef } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];

/* ═════════════ overview: live environment band + action panel (§8.1 item 2, §8.2) ═════════════ */

function actionHref(r: S["EnvActionRow"]): string {
  const id = r.entity_id;
  switch (r.kind) {
    case "exceedances_awaiting_review":
      return id ? `/env-exceedances/${id}` : "/env-exceedances";
    case "requirements_not_in_force":
      return id ? `/env-permits/${id}` : "/env-permits";
    case "consignments_overdue":
    case "consignments_rejected":
      return id ? `/waste-consignments/${id}` : "/waste-consignments";
    case "haz_storage_overdue":
      return id ? `/waste-areas/${id}` : "/waste-areas";
    case "discharge_without_permit":
      return "/env-water";
    case "post_storm_checks_unmet":
      return "/field-inspections/new";
    case "spill_kit_coverage_gap":
      return "/spills#spill-kits";
    case "spills_not_closed":
      return id ? `/spills/${id}` : "/spills";
    case "complaints_past_due":
      return id ? `/env-complaints/${id}` : "/env-complaints";
  }
}

export function EnvOverviewPage() {
  return <ProjectGate>{(p) => <Overview project={p} />}</ProjectGate>;
}

function Overview({ project }: { project: Project }) {
  const t = useTranslations("env.overview");
  const tc = useTranslations("common");
  const te = useTranslations("enums");
  const ar = useLocale() === "ar";
  const ref = useEnvRef();
  const caps = useEnvCaps(project.id);
  const show = useDisplay(project.id);
  const band = useEnvBand(project.id, { enabled: caps.view });
  const panel = useEnvActionPanel(project.id, { enabled: caps.view });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const b = band.data;
  const openX = b?.open_exceedances ?? [];
  const tiles = b
    ? ([
        { k: "open_exceedances", n: openX.length, icon: TriangleAlert, href: "/env-exceedances?status=open", danger: true },
        { k: "airside_dust_alerts_24h", n: b.airside_dust_alerts_24h, icon: Plane, href: "/env-exceedances", danger: true },
        { k: "expiring_permits", n: b.expiring_permits.length, icon: CalendarClock, href: "/env-permits", danger: false },
        { k: "consignments_overdue", n: b.consignments_overdue, icon: Truck, href: "/waste-consignments?overdue=1", danger: true },
        { k: "haz_storage_due", n: b.haz_storage_due.length, icon: Hourglass, href: "/waste-areas", danger: false },
        { k: "post_storm_tasks", n: b.post_storm_tasks.filter((x) => !x.met).length, icon: Wind, href: "/field-inspections/new", danger: false },
      ] as const)
    : [];
  // One row per kind, the affected records listed under it (the server sends one row per record).
  const rows = panel.data?.items ?? [];
  const kinds = [...new Set(rows.map((r) => r.kind))];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          <div className="flex flex-wrap gap-2">
            {caps.reading ? (
              <Button asChild className="min-h-12 sm:min-h-control">
                <Link href="/env-readings/new" data-testid="overview-reading">
                  {t("newReading")}
                </Link>
              </Button>
            ) : null}
            {caps.spill ? (
              <Button asChild variant="outline" className="min-h-12 sm:min-h-control">
                <Link href="/spills/new" data-testid="overview-spill">
                  {t("newSpill")}
                </Link>
              </Button>
            ) : null}
          </div>
        }
      />
      <EnvOverviewSubNav />
      <div className="flex flex-col gap-6">
        <section aria-labelledby="env-band-h">
          <h2 id="env-band-h" className="mb-2 text-sm font-semibold text-muted-foreground">
            {t("band")}
          </h2>
          {band.isLoading ? (
            <LoadingState />
          ) : band.isError ? (
            <ErrorState error={band.error} onRetry={() => band.refetch()} />
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6" data-testid="env-band">
              {tiles.map((x) => {
                const Icon = x.icon;
                const hot = x.danger && x.n > 0;
                return (
                  <Link
                    key={x.k}
                    href={x.href}
                    className={cn("flex min-h-touch flex-col gap-1 rounded-md border p-3 hover:bg-muted/50", hot && "border-danger bg-danger-bg")}
                    data-testid="band-tile"
                    data-kind={x.k}
                  >
                    <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                      <Icon aria-hidden className={cn("size-4 shrink-0", hot && "text-danger")} />
                      {t(`b.${x.k}`)}
                    </span>
                    <span className={cn("text-3xl font-semibold tabular-nums", hot && "text-danger")} data-testid="band-value">
                      {show(String(x.n))}
                    </span>
                  </Link>
                );
              })}
            </div>
          )}
          {openX.length ? (
            // Airside first (§8.1 item 2): the server orders them.
            <ul className="mt-3 flex flex-col divide-y rounded-md border" data-testid="band-exceedances">
              {openX.slice(0, 6).map((x) => (
                <li key={x.id} className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm">
                  {x.airside ? <Plane aria-label={t("airside")} className="size-4 text-danger" /> : null}
                  <Link href={`/env-exceedances/${x.id}`} className="font-medium text-primary hover:underline">
                    <Code>{x.exceedance_no}</Code>
                  </Link>
                  <Code>{x.point_code}</Code>
                  <span>{ref.label("parameters", x.parameter)}</span>
                  {x.background_ref ? (
                    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                      <CloudFog aria-hidden className="size-3.5" />
                      {t("backgroundSuggested")}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
        </section>
        <section aria-labelledby="env-actions-h">
          <h2 id="env-actions-h" className="mb-2 text-sm font-semibold text-muted-foreground">
            {t("actions")}
          </h2>
          {panel.isLoading ? (
            <LoadingState />
          ) : panel.isError ? (
            <ErrorState error={panel.error} onRetry={() => panel.refetch()} />
          ) : kinds.length ? (
            <ul className="flex flex-col divide-y rounded-md border" data-testid="env-actions">
              {kinds.map((k) => {
                const items = rows.filter((r) => r.kind === k);
                return (
                  <li key={k} className="flex flex-col gap-2 px-4 py-3" data-testid="env-action" data-kind={k}>
                    <span className="flex items-center gap-3">
                      <span className="min-w-10 rounded-md bg-warning-bg px-2 py-1 text-center text-lg font-bold text-warning tabular-nums">{show(String(items.length))}</span>
                      <span className="font-medium">{te(`envActionKind.${k}`)}</span>
                    </span>
                    <ul className="flex flex-col gap-1 ps-1">
                      {items.slice(0, 8).map((r, i) => (
                        <li key={`${r.ref}-${i}`} className="flex flex-wrap items-center gap-2 text-sm">
                          <FileWarning aria-hidden className="size-4 shrink-0 text-muted-foreground" />
                          <Code>{r.ref}</Code>
                          <span className="min-w-0 flex-1 text-muted-foreground">{ar ? r.label_ar : r.label_en}</span>
                          <Link href={actionHref(r)} className="inline-flex min-h-touch items-center gap-1 text-primary hover:underline">
                            {t("open")}
                            <ArrowRight aria-hidden className="size-4 rtl:-scale-x-100" />
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </li>
                );
              })}
            </ul>
          ) : (
            <EmptyState message={t("empty")} />
          )}
        </section>
      </div>
    </div>
  );
}

/* ═════════════ KPI page (K-118…K-126; aggregates only, EK-1) ═════════════ */

/** The server writes its two notes in English (env_views.notes); show them in the page language. */
function KpiNote({ n }: { n: string }) {
  const t = useTranslations("env.kpi");
  const target = /^K-120 target: (.+)$/.exec(n);
  if (target) return <>{t("noteTarget", { v: target[1] ?? "" })}</>;
  if (n.startsWith("K-118 is project level only")) return <>{t("noteK118")}</>;
  return <bdi>{n}</bdi>;
}

export function EnvKpiPage() {
  return <ProjectGate>{(p) => <Kpis project={p} />}</ProjectGate>;
}

const PERIODS = ["month", "quarter", "year", "ytd"] as const satisfies readonly S["PeriodPreset"][];

/** Every number is the server's `display`; nothing is computed here. */
function Kpis({ project }: { project: Project }) {
  const t = useTranslations("env.kpi");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const ar = useLocale() === "ar";
  const ref = useEnvRef();
  const caps = useEnvCaps(project.id);
  const show = useDisplay(project.id);
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const groupBy = (s.get("group_by") as S["EnvKpiGroupBy"]) || "stream";
  const period = (s.get("period") as (typeof PERIODS)[number]) || "month";
  const anchor = s.get("anchor") ?? "";
  const q = useEnvKpis({ project_id: [project.id], group_by: [groupBy], period, anchor: anchor || null }, { enabled: caps.view });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const d = q.data;
  const label = (x: { label_en: string; label_ar: string }) => (ar ? x.label_ar : x.label_en);
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <EnvOverviewSubNav />
      <ListToolbar>
        <SelectFilter id="ek-period" label={t("period")} value={period} onChange={(v) => s.set({ period: v })} options={PERIODS.map((p) => ({ value: p, label: te(`period.${p}`) }))} allLabel={te("period.month")} />
        <DateFilter id="ek-anchor" label={t("anchor")} value={anchor} onChange={(v) => s.set({ anchor: v })} />
        <SelectFilter
          id="ek-group"
          label={t("groupBy")}
          value={groupBy}
          onChange={(v) => s.set({ group_by: v })}
          options={ENV_KPI_GROUP_BY.map((g) => ({ value: g, label: te(`envKpiGroupBy.${g}`) }))}
          allLabel={te("envKpiGroupBy.stream")}
        />
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
          {d.notes.length ? (
            <ul className="flex flex-col gap-1 rounded-md border bg-muted/30 px-4 py-2 text-sm" data-testid="ek-notes">
              {d.notes.map((n) => (
                <li key={n} data-testid="ek-note">
                  <KpiNote n={n} />
                </li>
              ))}
            </ul>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid="ek-tiles">
            {d.metrics.map((m) => (
              <Card key={m.metric} data-testid="ek-tile" data-metric={m.metric}>
                <CardContent className="flex flex-col gap-1 p-4">
                  <span className="flex items-center justify-between gap-2 text-xs font-medium text-muted-foreground">
                    <span>{ar ? m.short_label_ar : m.short_label_en}</span>
                    <span className="font-mono ltr">{m.metric}</span>
                  </span>
                  <span className={cn("text-3xl font-semibold tabular-nums", m.rag === "red" && "text-danger", m.rag === "amber" && "text-warning")} data-testid="ek-value">
                    {show(m.display)}
                  </span>
                  {m.rag && m.rag !== "green" ? (
                    <span className={cn("inline-flex items-center gap-1 text-xs font-medium", m.rag === "red" ? "text-danger" : "text-warning")} data-testid="ek-rag" data-rag={m.rag}>
                      <TriangleAlert aria-hidden className="size-3.5" />
                      {te(`rag.${m.rag}`)}
                    </span>
                  ) : null}
                  {m.target_display ? (
                    <span className="text-xs text-muted-foreground">
                      {t("target")}: <span className="tabular-nums">{show(m.target_display)}</span>
                    </span>
                  ) : null}
                  {m.null_reason ? <span className="text-xs text-muted-foreground">{te(`nullReason.${m.null_reason}`)}</span> : null}
                  {m.components.length ? (
                    <span className="flex flex-wrap gap-x-3 text-xs text-muted-foreground" data-testid="ek-chips">
                      {m.components.map((c) => (
                        <span key={c.key}>
                          {/^[A-Z_]+$/.test(c.key) && te.has(`emNotReady.${c.key}` as "emNotReady.MISSING") ? te(`emNotReady.${c.key}` as "emNotReady.MISSING") : ref.items("parameters").some((x) => x.code === c.key) ? ref.label("parameters", c.key) : label(c)}: <span className="font-medium tabular-nums text-foreground">{show(c.display)}</span>
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
              <CardTitle className="text-base">{t("breakdown", { by: te(`envKpiGroupBy.${groupBy}`) })}</CardTitle>
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

function Breakdown({ breakdowns, metrics, show }: { breakdowns: S["EnvBreakdown"][]; metrics: S["KpiValue"][]; show: (v: string) => string }) {
  const t = useTranslations("env.kpi");
  const ar = useLocale() === "ar";
  if (!breakdowns.length || breakdowns.every((b) => !b.rows.length)) return <EmptyState message={t("noBreakdown")} />;
  const keys: { key: string; label: string }[] = [];
  for (const b of breakdowns) for (const r of b.rows) if (!keys.some((k) => k.key === r.key)) keys.push({ key: r.key, label: ar ? r.label_ar : r.label_en });
  const metricLabel = (id: string) => {
    const m = metrics.find((x) => x.metric === id);
    return m ? (ar ? m.short_label_ar : m.short_label_en) : id;
  };
  return (
    <Table data-testid="ek-breakdown">
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
          <TR key={k.key} data-testid="ek-row" data-key={k.key}>
            <TD label={t("key")}>
              <bdi>{k.label}</bdi>
            </TD>
            {breakdowns.map((b) => {
              const r = b.rows.find((x) => x.key === k.key);
              return (
                <Fragment key={b.metric}>
                  <TD label={metricLabel(b.metric)} className="text-end tabular-nums">
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

/* ═════════════ settings (§3.16; tighten only; 213 edits) ═════════════ */

type Key = keyof S["EnvSettingsUpdate"];
type Kind = "int" | "dec" | "date" | "time" | "intList" | "classes" | "bool" | "codes";
const GROUPS: { title: "groupPermits" | "groupWaste" | "groupMonitoring" | "groupSpills" | "groupComplaints" | "groupWarn" | "groupRetention"; fields: { k: Key; kind: Kind; range?: string }[] }[] = [
  {
    title: "groupPermits",
    fields: [
      { k: "permit_alert_days", kind: "intList", range: "0–180" },
      { k: "provider_licence_alert_days", kind: "intList", range: "0–180" },
      { k: "aspect_review_months", kind: "int", range: "6–12" },
      { k: "env_notifications_from", kind: "date" },
    ],
  },
  {
    title: "groupWaste",
    fields: [
      { k: "manifest_return_days", kind: "int", range: "1–14" },
      { k: "weight_discrepancy_pct", kind: "dec", range: "2.0–20.0" },
      { k: "mwan_manifest_required_for", kind: "classes" },
      { k: "haz_storage_max_days", kind: "int", range: "30–90" },
      { k: "containment_min_pct", kind: "int", range: "110–150" },
      { k: "diversion_target_pct", kind: "dec", range: "0.0–100.0" },
    ],
  },
  {
    title: "groupMonitoring",
    fields: [
      { k: "data_capture_pct", kind: "dec", range: "50.0–100.0" },
      { k: "noise_day_start", kind: "time" },
      { k: "noise_night_start", kind: "time" },
      { k: "background_ops_event_types", kind: "codes" },
      { k: "post_storm_check_hours", kind: "int", range: "1–12" },
      { k: "exceedance_review_days", kind: "int", range: "1–7" },
    ],
  },
  {
    title: "groupSpills",
    fields: [
      { k: "spill_reportable_l", kind: "dec", range: "1.0–200.0" },
      { k: "airside_spill_always_reportable", kind: "bool" },
    ],
  },
  {
    title: "groupComplaints",
    fields: [
      { k: "complaint_response_days", kind: "int", range: "1–14" },
      { k: "authority_complaint_response_days", kind: "int", range: "1–7" },
    ],
  },
  {
    title: "groupWarn",
    fields: [
      { k: "monitoring_warning_pct", kind: "dec", range: "50.0–100.0" },
      { k: "custody_warning_pct", kind: "dec", range: "50.0–100.0" },
      { k: "exceedance_warning_count", kind: "int", range: "1–10" },
    ],
  },
  {
    title: "groupRetention",
    fields: [
      { k: "photo_retention_months", kind: "int", range: "12–60" },
      { k: "complainant_retention_months", kind: "int", range: "6–24" },
    ],
  },
];

export function EnvSettingsPage() {
  return <ProjectGate>{(p) => <Settings project={p} />}</ProjectGate>;
}

function Settings({ project }: { project: Project }) {
  const t = useTranslations("env.settings");
  const tc = useTranslations("common");
  const caps = useEnvCaps(project.id);
  const q = useEnvSettings(project.id, { enabled: caps.view || caps.settings });
  if (!caps.view && !caps.settings) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <EnvOverviewSubNav />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data ? (
        <div className="flex flex-col gap-4">
          {!caps.settings ? (
            <Alert tone="info" data-testid="settings-readonly">
              {t("readOnly")}
            </Alert>
          ) : null}
          <SettingsForm key={JSON.stringify(q.data)} project={project} s={q.data} editable={caps.settings} />
        </div>
      ) : null}
    </div>
  );
}

function str(kind: Kind, v: unknown): string {
  if (v === null || v === undefined) return "";
  if (kind === "intList" || kind === "codes") return (v as (string | number)[]).join(", ");
  if (kind === "classes") return (v as string[]).join(",");
  if (kind === "bool") return v ? "1" : "";
  if (kind === "time") return String(v).slice(0, 5);
  return String(v);
}

function SettingsForm({ project, s, editable }: { project: Project; s: S["EnvSettingsRead"]; editable: boolean }) {
  const t = useTranslations("env.settings");
  const { label } = useEnvRef();
  const refresh = useEnvRefresh();
  const flat = GROUPS.flatMap((g) => g.fields);
  const init = Object.fromEntries(flat.map((f) => [f.k, str(f.kind, (s as Record<string, unknown>)[f.k])]));
  const [v, setV] = useState<Record<string, string>>(init);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {};
      for (const f of flat) {
        const x = v[f.k] ?? "";
        if (x === init[f.k]) continue;
        const list = x.split(/[,\s،]+/).filter(Boolean);
        body[f.k] =
          f.kind === "int"
            ? x === ""
              ? null
              : Number(x)
            : f.kind === "intList"
              ? list.map(Number)
              : f.kind === "codes" || f.kind === "classes"
                ? list
                : f.kind === "bool"
                  ? x === "1"
                  : x || null;
      }
      await unwrap(api.PATCH("/api/v1/projects/{project_id}/env-settings", { params: { path: { project_id: project.id } }, body: body as S["EnvSettingsUpdate"] }));
      await refresh();
      toast.success(t("saved"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-4" data-testid="env-settings">
      <p className="text-sm text-muted-foreground">{t("tightenOnly")}</p>
      {GROUPS.map((g) => (
        <Card key={g.title}>
          <CardHeader>
            <CardTitle className="text-base">{t(g.title)}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {g.fields.map((f) =>
              f.kind === "bool" ? (
                <Check key={f.k} id={`es-${f.k}`} label={t(`f.${f.k}`)} checked={v[f.k] === "1"} disabled={!editable} onChange={(c) => setV({ ...v, [f.k]: c ? "1" : "" })} testId={`es-${f.k}`} />
              ) : f.kind === "classes" ? (
                <fieldset key={f.k} className="flex flex-col gap-1" data-testid={`es-${f.k}`}>
                  <legend className="mb-1 text-sm font-medium">{t(`f.${f.k}`)}</legend>
                  {WASTE_CLASSES.map((c) => {
                    const on = (v[f.k] ?? "").split(",").includes(c);
                    return (
                      <Check
                        key={c}
                        id={`es-${f.k}-${c}`}
                        label={label("waste_classes", c)}
                        checked={on}
                        disabled={!editable}
                        onChange={(ck) => {
                          const cur = (v[f.k] ?? "").split(",").filter(Boolean);
                          setV({ ...v, [f.k]: (ck ? [...cur, c] : cur.filter((x) => x !== c)).join(",") });
                        }}
                      />
                    );
                  })}
                </fieldset>
              ) : (
                <FormField key={f.k} id={`es-${f.k}`} label={t(`f.${f.k}`)} hint={f.range ? t("allowed", { range: f.range }) : f.kind === "intList" || f.kind === "codes" ? t("listHint") : undefined}>
                  <Input
                    type={f.kind === "date" ? "date" : f.kind === "time" ? "time" : f.kind === "int" ? "number" : "text"}
                    inputMode={f.kind === "dec" ? "decimal" : undefined}
                    dir={f.kind === "intList" || f.kind === "codes" ? "ltr" : undefined}
                    disabled={!editable}
                    value={v[f.k] ?? ""}
                    onChange={(x) => setV({ ...v, [f.k]: x.target.value })}
                    data-testid={`es-${f.k}`}
                  />
                </FormField>
              ),
            )}
          </CardContent>
        </Card>
      ))}
      {editable ? (
        <div className="flex flex-col gap-2">
          <MutationError error={error} />
          <Button className="w-fit" disabled={busy} onClick={() => void save()} data-testid="es-save">
            {t("save")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
