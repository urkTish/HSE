"use client";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { PageHeader } from "@/components/common/page-header";
import { ProjectGate } from "@/components/common/project-gate";
import { ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Tick } from "@/components/cert/common";
import { DecimalInput } from "@/components/ptw/common";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useHeatRefresh, useHeatSettings, useRegimeTable } from "@/lib/api/heat";
import { BASES, TABLE_REGIMES, WORKLOADS } from "@/lib/heat-enums";
import { HeatSetupSubNav, useHeatCaps } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];
type Settings = S["HeatSettingsRead"];

type Key = Extract<keyof S["HeatSettingsUpdate"], "heat_register_from" | "heat_ptw_enforcement_from" | "heat_fitness_required" | "regime_relax_minutes" | "wbgt_limit_offset_c" | "reading_backdate_max_hours" | "wbgt_component_tolerance_c" | "standard_shift_hours" | "deacclimatisation_days" | "acclimatisation_restart_gap_days" | "plan_confirmation_hours" | "cool_water_max_c" | "welfare_checks_per_station_day" | "ban_patrols_per_zone_day" | "heat_illness_review_days" | "heat_case_merge_hours" | "wbgt_coverage_warning_pct" | "welfare_compliance_warning_pct" | "ban_patrol_coverage_warning_pct" | "heat_photo_retention_months" | "heat_record_retention_years">;
type Field = { k: Key; kind: "int" | "dec" | "date" | "bool"; range?: string };

/** §3.14 "Allowed" ranges: hints only; the server is the judge (422 VALIDATION / PERIOD_TOO_SHORT / HEAT_COVERAGE_INCOMPLETE). */
const GROUPS: { title: "groupRegister" | "groupReadings" | "groupAcclimatisation" | "groupWelfare" | "groupReporting" | "groupRetention"; fields: Field[] }[] = [
  {
    title: "groupRegister",
    fields: [
      { k: "heat_register_from", kind: "date" },
      { k: "heat_ptw_enforcement_from", kind: "date" },
      { k: "heat_fitness_required", kind: "bool" },
    ],
  },
  {
    title: "groupReadings",
    fields: [
      { k: "regime_relax_minutes", kind: "int", range: "30–60" },
      { k: "wbgt_limit_offset_c", kind: "dec", range: "−3.0 … 0.0" },
      { k: "reading_backdate_max_hours", kind: "int", range: "0–24" },
      { k: "wbgt_component_tolerance_c", kind: "dec", range: "0.2–1.0" },
    ],
  },
  {
    title: "groupAcclimatisation",
    fields: [
      { k: "standard_shift_hours", kind: "dec", range: "8.0–12.0" },
      { k: "deacclimatisation_days", kind: "int", range: "3–7" },
      { k: "acclimatisation_restart_gap_days", kind: "int", range: "2–4" },
      { k: "plan_confirmation_hours", kind: "int", range: "4–24" },
    ],
  },
  {
    title: "groupWelfare",
    fields: [
      { k: "cool_water_max_c", kind: "dec", range: "10.0–15.0" },
      { k: "welfare_checks_per_station_day", kind: "int", range: "1–4" },
      { k: "ban_patrols_per_zone_day", kind: "int", range: "1–4" },
      { k: "heat_illness_review_days", kind: "int", range: "1–7" },
      { k: "heat_case_merge_hours", kind: "int", range: "24–72" },
    ],
  },
  {
    title: "groupReporting",
    fields: [
      { k: "wbgt_coverage_warning_pct", kind: "dec", range: "80.0–100.0" },
      { k: "welfare_compliance_warning_pct", kind: "dec", range: "80.0–100.0" },
      { k: "ban_patrol_coverage_warning_pct", kind: "dec", range: "80.0–100.0" },
    ],
  },
  {
    title: "groupRetention",
    fields: [
      { k: "heat_photo_retention_months", kind: "int", range: "6–36" },
      { k: "heat_record_retention_years", kind: "int", range: "2–10" },
    ],
  },
];

export function HeatSettingsPage() {
  return <ProjectGate>{(p) => <HeatSettings project={p} />}</ProjectGate>;
}

function HeatSettings({ project }: { project: Project }) {
  const t = useTranslations("heat.settings");
  const tc = useTranslations("common");
  const caps = useHeatCaps(project.id);
  const q = useHeatSettings(project.id, { enabled: caps.view });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <HeatSetupSubNav />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data ? (
        <div className="flex flex-col gap-4">
          {!caps.settings ? <Alert tone="info">{t("readOnly")}</Alert> : null}
          <SettingsForm key={JSON.stringify(q.data)} project={project} s={q.data} editable={caps.settings} />
          <RegimeTableCard editable={caps.settings} offset={q.data.wbgt_limit_offset_c} />
        </div>
      ) : null}
    </div>
  );
}

function SettingsForm({ project, s, editable }: { project: Project; s: Settings; editable: boolean }) {
  const t = useTranslations("heat.settings");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const refresh = useHeatRefresh();
  const init = Object.fromEntries(GROUPS.flatMap((g) => g.fields).map((f) => [f.k, String((s as Record<string, unknown>)[f.k] ?? "")]));
  const [v, setV] = useState<Record<string, string>>(init);
  const [period, setPeriod] = useState(s.heat_controls_period);
  const [hours, setHours] = useState({ start_local: s.heat_monitoring_hours.start_local.slice(0, 5), end_local: s.heat_monitoring_hours.end_local.slice(0, 5) });
  const [valid, setValid] = useState(s.reading_valid_minutes);
  const [headline, setHeadline] = useState(s.headline_workload);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {};
      for (const f of GROUPS.flatMap((g) => g.fields)) {
        if (v[f.k] === init[f.k]) continue;
        body[f.k] = f.kind === "bool" ? v[f.k] === "true" : f.kind === "int" ? (v[f.k] === "" ? null : Number(v[f.k])) : v[f.k] || null;
      }
      if (JSON.stringify(period) !== JSON.stringify(s.heat_controls_period)) body.heat_controls_period = period;
      if (hours.start_local !== s.heat_monitoring_hours.start_local.slice(0, 5) || hours.end_local !== s.heat_monitoring_hours.end_local.slice(0, 5)) body.heat_monitoring_hours = hours;
      if (JSON.stringify(valid) !== JSON.stringify(s.reading_valid_minutes)) body.reading_valid_minutes = valid;
      if (headline !== s.headline_workload) body.headline_workload = headline;
      await unwrap(api.PATCH("/api/v1/projects/{project_id}/heat-settings", { params: { path: { project_id: project.id } }, body: body as S["HeatSettingsUpdate"] }));
      toast.success(tc("saved"));
      await refresh();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card data-testid="heat-settings-form">
      <CardContent className="flex flex-col gap-5 p-4">
        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <FormField id="hs-period-from" label={t("controlsFrom")} hint={t("mmdd")}>
            <Input id="hs-period-from" dir="ltr" disabled={!editable} value={period.start_mmdd} onChange={(e) => setPeriod({ ...period, start_mmdd: e.target.value })} data-testid="hs-period-from" />
          </FormField>
          <FormField id="hs-period-to" label={t("controlsTo")} hint={t("mmdd")}>
            <Input id="hs-period-to" dir="ltr" disabled={!editable} value={period.end_mmdd} onChange={(e) => setPeriod({ ...period, end_mmdd: e.target.value })} data-testid="hs-period-to" />
          </FormField>
          <FormField id="hs-hours-from" label={t("hoursFrom")}>
            <Input id="hs-hours-from" type="time" dir="ltr" disabled={!editable} value={hours.start_local} onChange={(e) => setHours({ ...hours, start_local: e.target.value })} />
          </FormField>
          <FormField id="hs-hours-to" label={t("hoursTo")}>
            <Input id="hs-hours-to" type="time" dir="ltr" disabled={!editable} value={hours.end_local} onChange={(e) => setHours({ ...hours, end_local: e.target.value })} />
          </FormField>
          <FormField id="hs-valid-manual" label={t("validManual")} hint="15–60">
            <Input id="hs-valid-manual" inputMode="numeric" dir="ltr" disabled={!editable} value={valid.manual} onChange={(e) => setValid({ ...valid, manual: Number(e.target.value.replace(/[^0-9]/g, "")) })} />
          </FormField>
          <FormField id="hs-valid-station" label={t("validStation")} hint="5–30">
            <Input id="hs-valid-station" inputMode="numeric" dir="ltr" disabled={!editable} value={valid.station} onChange={(e) => setValid({ ...valid, station: Number(e.target.value.replace(/[^0-9]/g, "")) })} />
          </FormField>
          <FormField id="hs-headline" label={t("k.headline_workload")} hint={t("headlineHint")}>
            <Select id="hs-headline" disabled={!editable} value={headline} onChange={(e) => setHeadline(e.target.value as S["Workload"])}>
              {WORKLOADS.filter((w) => w !== "light").map((w) => (
                <option key={w} value={w}>
                  {te(`workload.${w}`)}
                </option>
              ))}
            </Select>
          </FormField>
        </section>
        {GROUPS.map((g) => (
          <section key={g.title} className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">{t(g.title)}</h3>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {g.fields.map((f) =>
                f.kind === "bool" ? (
                  <Tick key={f.k} id={`hs-${f.k}`} label={t(`k.${f.k}`)} checked={v[f.k] === "true"} disabled={!editable || init[f.k] === "true"} onChange={(x) => setV({ ...v, [f.k]: String(x) })} />
                ) : (
                  <FormField key={f.k} id={`hs-${f.k}`} label={t(`k.${f.k}`)} hint={f.kind === "date" ? t(`hint.${f.k as "heat_register_from" | "heat_ptw_enforcement_from"}`) : f.range}>
                    {f.kind === "date" ? (
                      <Input id={`hs-${f.k}`} type="date" dir="ltr" disabled={!editable} value={v[f.k] ?? ""} onChange={(e) => setV({ ...v, [f.k]: e.target.value })} data-testid={`hs-${f.k}`} />
                    ) : f.kind === "dec" ? (
                      <DecimalInput id={`hs-${f.k}`} disabled={!editable} value={v[f.k] ?? ""} onChange={(x) => setV({ ...v, [f.k]: x })} data-testid={`hs-${f.k}`} />
                    ) : (
                      <Input id={`hs-${f.k}`} inputMode="numeric" dir="ltr" disabled={!editable} value={v[f.k] ?? ""} onChange={(e) => setV({ ...v, [f.k]: e.target.value.replace(/[^0-9]/g, "") })} data-testid={`hs-${f.k}`} />
                    )}
                  </FormField>
                ),
              )}
            </div>
          </section>
        ))}
        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">{t("readOnlyGroup")}</h3>
          <FieldList>
            <FieldItem label={t("banPeriod")}>
              <bdi className="ltr">
                {s.midday_ban_period.start_mmdd} → {s.midday_ban_period.end_mmdd} · {s.midday_ban_hours.start_local.slice(0, 5)}–{s.midday_ban_hours.end_local.slice(0, 5)}
              </bdi>
            </FieldItem>
            <FieldItem label={t("k.acclimatisation_schedules")}>
              <span className="flex flex-col text-sm">
                <span>
                  {te("planType.new_worker")}: <bdi className="ltr">{s.acclimatisation_schedules.new_worker.map((x) => `${x}%`).join(" · ")}</bdi>
                </span>
                <span>
                  {te("planType.returner")}: <bdi className="ltr">{s.acclimatisation_schedules.returner.map((x) => `${x}%`).join(" · ")}</bdi>
                </span>
              </span>
            </FieldItem>
            <FieldItem label={t("k.trade_workload_defaults")} wide>
              <span className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
                {Object.entries(s.trade_workload_defaults).map(([trade, w]) => (
                  <span key={trade}>
                    {te.has(`trade.${trade}` as never) ? te(`trade.${trade}` as never) : trade}: <span className="font-medium">{te(`workload.${w}`)}</span>
                  </span>
                ))}
              </span>
            </FieldItem>
          </FieldList>
        </section>
        <MutationError error={error} />
        {editable ? (
          <Button className="self-start" disabled={busy} onClick={() => void save()} data-testid="hs-save">
            {busy ? tc("saving") : tc("save")}
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

/* ═════════════ regime table (§3.4, HS-5 tighten only) ═════════════ */

function RegimeTableCard({ editable, offset }: { editable: boolean; offset: string }) {
  const t = useTranslations("heat.settings");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const refresh = useHeatRefresh();
  const q = useRegimeTable();
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const rows = q.data?.rows ?? [];
  const key = (b: string, r: string, w: string) => `${b}|${r}|${w}`;
  const get = (b: string, r: string, w: string) => rows.find((x) => x.basis === b && x.regime === r && x.workload === w);
  async function save() {
    setBusy(true);
    setError(null);
    try {
      const changed = Object.entries(edits)
        .filter(([k, val]) => {
          const [b, r, w] = k.split("|") as [string, string, string];
          return val !== "" && val !== get(b, r, w)?.limit_c;
        })
        .map(([k, val]) => {
          const [basis, regime, workload] = k.split("|") as [S["AcclimatisationBasis"], S["Regime"], S["Workload"]];
          return { basis, regime, workload, limit_c: val };
        });
      if (changed.length) await unwrap(api.PATCH("/api/v1/heat-regime-table", { body: { rows: changed } }));
      setEdits({});
      toast.success(tc("saved"));
      await refresh();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card data-testid="regime-table">
      <CardHeader>
        <CardTitle className="text-base">{t("regimeTable")}</CardTitle>
        <p className="text-xs text-muted-foreground">{t("regimeHint", { offset })}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {q.isLoading ? (
          <LoadingState />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : (
          BASES.map((b) => (
            <div key={b} className="flex flex-col gap-1">
              <h3 className="text-sm font-semibold">{t(`basisTitle.${b}`)}</h3>
              <Table>
                <THead>
                  <TR>
                    <TH>{t("regime")}</TH>
                    {WORKLOADS.map((w) => (
                      <TH key={w} className="text-end">
                        {te(`workload.${w}`)}
                      </TH>
                    ))}
                  </TR>
                </THead>
                <TBody>
                  {TABLE_REGIMES.map((r) => (
                    <TR key={r}>
                      <TD label={t("regime")}>{te(`regime.${r}`)}</TD>
                      {WORKLOADS.map((w) => {
                        const row = get(b, r, w);
                        const k = key(b, r, w);
                        return (
                          <TD key={w} label={te(`workload.${w}`)} className="text-end" data-testid="limit" data-key={k}>
                            {editable ? (
                              <DecimalInput value={edits[k] ?? row?.limit_c ?? ""} onChange={(x) => setEdits({ ...edits, [k]: x })} className="ms-auto w-20 text-end" data-testid={`limit-${b}-${r}-${w}`} />
                            ) : (
                              <bdi className="ltr tabular-nums">{row?.limit_c ?? "—"}</bdi>
                            )}
                          </TD>
                        );
                      })}
                    </TR>
                  ))}
                </TBody>
              </Table>
            </div>
          ))
        )}
        <p className="text-xs text-muted-foreground">{t("r4Note")}</p>
        <MutationError error={error} />
        {editable ? (
          <Button className="self-start" disabled={busy || !Object.keys(edits).length} onClick={() => void save()} data-testid="regime-save">
            {t("saveTable")}
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}
