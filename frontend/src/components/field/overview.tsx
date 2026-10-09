"use client";
import { ArrowRight, CalendarClock, ClipboardCheck, ClipboardX, Megaphone, OctagonAlert } from "lucide-react";
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
import { DateFilter } from "@/components/training/common";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useFieldActionPanel, useFieldBand, useFieldKpis, useFieldRefresh, useFieldSettings } from "@/lib/api/field";
import { useDisplay } from "@/lib/digits";
import { FIELD_KPI_GROUP_BY } from "@/lib/field-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { Codes, FieldOverviewSubNav, useFieldCaps } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];

/* ═════════════ overview: live field band + action panel (§8.1 item 2, §8.2) ═════════════ */

const ACTION_HREF: Record<S["FieldActionKind"], string> = {
  stop_work_active: "/stop-work-orders",
  plan_without_checklist: "/inspection-plans",
  not_inspected_this_week: "/field-inspections/new",
  audit_lines_overdue: "/audit-programme",
  audit_reports_overdue: "/field-audits",
  campaigns_unmet: "/briefing-campaigns",
  offline_rejected: "/field-inspections/new",
};

export function FieldOverviewPage() {
  return <ProjectGate>{(p) => <Overview project={p} />}</ProjectGate>;
}

function Overview({ project }: { project: Project }) {
  const t = useTranslations("field.overview");
  const tc = useTranslations("common");
  const ar = useLocale() === "ar";
  const caps = useFieldCaps(project.id);
  const band = useFieldBand(project.id, { enabled: caps.view });
  const panel = useFieldActionPanel(project.id, { enabled: caps.view });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const b = band.data;
  const tiles = b
    ? ([
        { k: "stop_work_active", n: b.stop_work_active, icon: OctagonAlert, href: "/stop-work-orders", danger: true },
        { k: "critical_failures_today", n: b.critical_failures_today, icon: ClipboardX, href: "/field-findings", danger: true },
        { k: "not_inspected_this_week", n: b.not_inspected_this_week, icon: ClipboardCheck, href: "/field-inspections/new", danger: false },
        { k: "campaigns_unmet", n: b.campaigns_unmet, icon: Megaphone, href: "/briefing-campaigns", danger: false },
        { k: "audits_due_30_days", n: b.audits_due_30_days, icon: CalendarClock, href: "/audit-programme", danger: false },
      ] as const)
    : [];
  const items = panel.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.record ? (
            <Button asChild className="min-h-12 w-full text-base sm:min-h-control sm:w-auto sm:text-sm">
              <Link href="/field-inspections/new" data-testid="overview-run">
                <ClipboardCheck aria-hidden />
                {t("run")}
              </Link>
            </Button>
          ) : null
        }
      />
      <FieldOverviewSubNav />
      <div className="flex flex-col gap-6">
        <section aria-labelledby="fd-band-h">
          <h2 id="fd-band-h" className="mb-2 text-sm font-semibold text-muted-foreground">
            {t("band")}
          </h2>
          {band.isLoading ? (
            <LoadingState />
          ) : band.isError ? (
            <ErrorState error={band.error} onRetry={() => band.refetch()} />
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5" data-testid="field-band">
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
                      <Icon aria-hidden className={cn("size-4", hot && "text-danger")} />
                      {t(`b.${x.k}`)}
                    </span>
                    <span className={cn("text-3xl font-semibold tabular-nums", hot && "text-danger")} data-testid="band-value">
                      {x.n}
                    </span>
                  </Link>
                );
              })}
            </div>
          )}
        </section>
        <section aria-labelledby="fd-actions-h">
          <h2 id="fd-actions-h" className="mb-2 text-sm font-semibold text-muted-foreground">
            {t("actions")}
          </h2>
          {panel.isLoading ? (
            <LoadingState />
          ) : panel.isError ? (
            <ErrorState error={panel.error} onRetry={() => panel.refetch()} />
          ) : items.length ? (
            <ul className="flex flex-col divide-y rounded-md border" data-testid="field-actions">
              {items.map((i) => (
                <li key={i.kind} className="flex flex-wrap items-center gap-3 px-4 py-3" data-testid="fd-action" data-kind={i.kind}>
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
        </section>
      </div>
    </div>
  );
}

/* ═════════════ KPI page (K-34/35/36, K-110…K-117; aggregates only) ═════════════ */

export function FieldKpiPage() {
  return <ProjectGate>{(p) => <Kpis project={p} />}</ProjectGate>;
}

const PERIODS = ["month", "quarter", "year", "ytd"] as const satisfies readonly S["PeriodPreset"][];

/** The server sends its notes in English; they follow three fixed shapes, rendered here through messages. */
function useNote() {
  const t = useTranslations("field.kpi");
  const { date } = useFormatters();
  return (n: string) => {
    let m = /^K-36 source: (.+)$/.exec(n);
    if (m) {
      const src = { "Toolbox register": "register", "Daily returns": "returns", Mixed: "mixed" }[m[1] ?? ""];
      return src ? t("noteSource", { src: t(`src.${src as "register"}`) }) : n;
    }
    m = /^Daily returns differ from the toolbox register by (.+)$/.exec(n);
    if (m) {
      const parts = (m[1] ?? "").split(", ").map((p) => {
        const x = /^([\d.]+) % \((talks|attendees)\)$/.exec(p);
        return x ? t(`diff.${x[2] as "talks" | "attendees"}`, { pct: x[1] ?? "" }) : p;
      });
      return t("noteDiff", { parts: parts.join("، ") });
    }
    m = /^K-34 \/ K-35: checklist-based from (\d{4}-\d{2}-\d{2})$/.exec(n);
    if (m) return t("noteFrom", { date: date(m[1] ?? "") });
    return n;
  };
}

/** Every number is the server's `display`; nothing is computed here. */
function Kpis({ project }: { project: Project }) {
  const t = useTranslations("field.kpi");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const ar = useLocale() === "ar";
  const caps = useFieldCaps(project.id);
  const show = useDisplay(project.id);
  const note = useNote();
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const groupBy = (s.get("group_by") as S["FieldKpiGroupBy"]) || "inspection_type";
  const period = (s.get("period") as (typeof PERIODS)[number]) || "month";
  const anchor = s.get("anchor") ?? "";
  const q = useFieldKpis({ project_id: [project.id], group_by: [groupBy], period, anchor: anchor || null }, { enabled: caps.view });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const d = q.data;
  const label = (x: { label_en: string; label_ar: string }) => (ar ? x.label_ar : x.label_en);
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <FieldOverviewSubNav />
      <ListToolbar>
        <SelectFilter id="fk-period" label={t("period")} value={period} onChange={(v) => s.set({ period: v })} options={PERIODS.map((p) => ({ value: p, label: te(`period.${p}`) }))} allLabel={te("period.month")} />
        <DateFilter id="fk-anchor" label={t("anchor")} value={anchor} onChange={(v) => s.set({ anchor: v })} />
        <SelectFilter
          id="fk-group"
          label={t("groupBy")}
          value={groupBy}
          onChange={(v) => s.set({ group_by: v })}
          options={FIELD_KPI_GROUP_BY.map((g) => ({ value: g, label: te(`fdKpiGroupBy.${g}`) }))}
          allLabel={te("fdKpiGroupBy.inspection_type")}
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
            <ul className="flex flex-col gap-1 rounded-md border bg-muted/30 px-4 py-2 text-sm" data-testid="fk-notes">
              {d.notes.map((n) => (
                <li key={n} data-testid="fk-note">
                  {note(n)}
                </li>
              ))}
            </ul>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid="fk-tiles">
            {d.metrics.map((m) => (
              <Card key={m.metric} data-testid="fk-tile" data-metric={m.metric}>
                <CardContent className="flex flex-col gap-1 p-4">
                  <span className="flex items-center justify-between gap-2 text-xs font-medium text-muted-foreground">
                    <span>{ar ? m.short_label_ar : m.short_label_en}</span>
                    <span className="font-mono ltr">{m.metric}</span>
                  </span>
                  <span className={cn("text-3xl font-semibold tabular-nums", m.rag === "red" && "text-danger", m.rag === "amber" && "text-warning")} data-testid="fk-value">
                    {show(m.display)}
                  </span>
                  {m.null_reason ? <span className="text-xs text-muted-foreground">{te(`nullReason.${m.null_reason}`)}</span> : null}
                  {m.components.length ? (
                    <span className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                      {m.components.map((c) => (
                        <span key={c.key}>
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
              <CardTitle className="text-base">{t("breakdown", { by: te(`fdKpiGroupBy.${groupBy}`) })}</CardTitle>
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

function Breakdown({ breakdowns, metrics, show }: { breakdowns: S["FieldBreakdown"][]; metrics: S["KpiValue"][]; show: (v: string) => string }) {
  const t = useTranslations("field.kpi");
  const ar = useLocale() === "ar";
  if (!breakdowns.length || breakdowns.every((b) => !b.rows.length)) return <EmptyState message={t("noBreakdown")} />;
  const keys: { key: string; label: string }[] = [];
  for (const b of breakdowns) for (const r of b.rows) if (!keys.some((k) => k.key === r.key)) keys.push({ key: r.key, label: ar ? r.label_ar : r.label_en });
  const metricLabel = (id: string) => {
    const m = metrics.find((x) => x.metric === id);
    return m ? (ar ? m.short_label_ar : m.short_label_en) : id;
  };
  return (
    <Table data-testid="fk-breakdown">
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
          <TR key={k.key} data-testid="fk-row" data-key={k.key}>
            <TD label={t("key")}>
              <bdi>{k.label}</bdi>
            </TD>
            {breakdowns.map((b) => {
              const r = b.rows.find((x) => x.key === k.key);
              return (
                <Fragment key={b.metric}>
                  <TD label={metricLabel(b.metric)} className="text-end tabular-nums" data-testid="fk-cell" data-metric={b.metric}>
                    {r ? show(r.display) : "—"}
                    {r?.note ? <span className="block text-xs text-muted-foreground">{t("smallSample")}</span> : null}
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

/* ═════════════ settings (§3.14; tighten only; 193 edits) ═════════════ */

type FieldKey = keyof S["FieldSettingsUpdate"];
const GROUPS: { title: "groupSwitch" | "groupInspect" | "groupAudit" | "groupTalk" | "groupWarn"; fields: { k: FieldKey; kind: "date" | "int" | "dec"; range?: string }[] }[] = [
  {
    title: "groupSwitch",
    fields: [
      { k: "inspection_template_required_from", kind: "date" },
      { k: "toolbox_register_from", kind: "date" },
    ],
  },
  {
    title: "groupInspect",
    fields: [
      { k: "inspection_pass_mark_pct", kind: "dec", range: "50.0–100.0" },
      { k: "repeat_finding_days", kind: "int", range: "14–90" },
      { k: "offline_submit_max_hours", kind: "int", range: "12–72" },
      { k: "offline_cache_hours", kind: "int", range: "24–72" },
      { k: "photo_retention_months", kind: "int", range: "12–60" },
    ],
  },
  {
    title: "groupAudit",
    fields: [
      { k: "contractor_audit_months", kind: "int", range: "3–12" },
      { k: "system_audit_months", kind: "int", range: "6–12" },
      { k: "first_audit_grace_days", kind: "int", range: "30–90" },
      { k: "audit_report_days", kind: "int", range: "3–14" },
    ],
  },
  {
    title: "groupTalk",
    fields: [
      { k: "tbt_min_minutes", kind: "int", range: "5–30" },
      { k: "tbt_edit_window_hours", kind: "int", range: "4–48" },
      { k: "campaign_default_days", kind: "int", range: "1–30" },
    ],
  },
  {
    title: "groupWarn",
    fields: [
      { k: "inspection_coverage_warning_pct", kind: "dec", range: "50.0–100.0" },
      { k: "audit_programme_warning_pct", kind: "dec", range: "50.0–100.0" },
      { k: "tbt_reach_warning_pct", kind: "dec", range: "50.0–100.0" },
      { k: "critical_fail_warning_per_100", kind: "dec", range: "1.00–20.00" },
    ],
  },
];

export function FieldSettingsPage() {
  return <ProjectGate>{(p) => <Settings project={p} />}</ProjectGate>;
}

function Settings({ project }: { project: Project }) {
  const t = useTranslations("field.settings");
  const tc = useTranslations("common");
  const caps = useFieldCaps(project.id);
  const q = useFieldSettings(project.id, { enabled: caps.view || caps.settings });
  if (!caps.view && !caps.settings) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <FieldOverviewSubNav />
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

function SettingsForm({ project, s, editable }: { project: Project; s: S["FieldSettingsRead"]; editable: boolean }) {
  const t = useTranslations("field.settings");
  const refresh = useFieldRefresh();
  const flat = GROUPS.flatMap((g) => g.fields);
  const init = Object.fromEntries(flat.map((f) => [f.k, String((s as Record<string, unknown>)[f.k] ?? "")]));
  const [v, setV] = useState<Record<string, string>>(init);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {};
      for (const f of flat) {
        if (v[f.k] === init[f.k]) continue;
        body[f.k] = f.kind === "int" ? (v[f.k] === "" ? null : Number(v[f.k])) : v[f.k] || null;
      }
      await unwrap(api.PATCH("/api/v1/projects/{project_id}/field-settings", { params: { path: { project_id: project.id } }, body: body as S["FieldSettingsUpdate"] }));
      await refresh();
      toast.success(t("saved"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-4" data-testid="fd-settings">
      <p className="text-sm text-muted-foreground">{t("tightenOnly")}</p>
      {GROUPS.map((g) => (
        <Card key={g.title}>
          <CardHeader>
            <CardTitle className="text-base">{t(g.title)}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {g.fields.map((f) => (
              <FormField key={f.k} id={`fs-${f.k}`} label={t(`f.${f.k}`)} hint={f.range ? t("allowed", { range: f.range }) : f.kind === "date" ? t("switchHint") : undefined}>
                <Input
                  type={f.kind === "date" ? "date" : f.kind === "int" ? "number" : "text"}
                  inputMode={f.kind === "dec" ? "decimal" : undefined}
                  disabled={!editable}
                  value={v[f.k]}
                  onChange={(x) => setV({ ...v, [f.k]: x.target.value })}
                  data-testid={`fs-${f.k}`}
                />
              </FormField>
            ))}
          </CardContent>
        </Card>
      ))}
      {editable ? (
        <div className="flex flex-col gap-2">
          <MutationError error={error} />
          <Button className="w-fit" disabled={busy} onClick={() => void save()} data-testid="fs-save">
            {t("save")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
