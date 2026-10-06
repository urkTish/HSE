"use client";
import { ShieldCheck, ShieldOff } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { FormField, FormSection } from "@/components/common/form-field";
import { PageHeader } from "@/components/common/page-header";
import { ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { useMeData } from "@/components/shell/me-context";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { hk, useHseSettings } from "@/lib/api/hse";
import { useKpiCatalogue } from "@/lib/api/kpi";
import { CA_PRIORITIES } from "@/lib/enums";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { canWrite } from "@/lib/permissions";
import { todayInZone } from "@/lib/datetime";
import { useFormatters } from "@/lib/use-formatters";

type Settings = Schemas["HseSettingsRead"];
type NumKey =
  | "max_hours_per_person_day"
  | "warn_hours_per_person_day"
  | "completeness_threshold_pct"
  | "inspection_grace_days"
  | "ca_max_extensions"
  | "new_starter_days"
  | "low_exposure_hours"
  | "leading_warning_drop_pct"
  | "leading_warning_rise_pct"
  | "month_lock_day"
  | "injury_identity_retention_years";

const RANGES: Record<NumKey, [number, number]> = {
  max_hours_per_person_day: [12, 24],
  warn_hours_per_person_day: [8, 16],
  completeness_threshold_pct: [50, 100],
  inspection_grace_days: [0, 7],
  ca_max_extensions: [0, 5],
  new_starter_days: [7, 90],
  low_exposure_hours: [0, 100_000_000],
  leading_warning_drop_pct: [5, 90],
  leading_warning_rise_pct: [5, 200],
  month_lock_day: [1, 28],
  injury_identity_retention_years: [5, 30],
};
const MMDD = /^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;

export function HseSettingsPage({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("hseSettings");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const te = useTranslations("enums");
  const locale = useLocale();
  const me = useMeData();
  const qc = useQueryClient();
  const q = useHseSettings(project.id);
  const cat = useKpiCatalogue();
  const editable = canWrite(me, "hse_settings.edit", project.id);
  const [edits, setEdits] = useState<Partial<Settings>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const d: Settings = { ...q.data, ...edits };
  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => setEdits({ ...edits, [k]: v });

  async function save() {
    const e: Record<string, string> = {};
    for (const [k, [min, max]] of Object.entries(RANGES) as [NumKey, [number, number]][]) {
      const v = d[k];
      if (!Number.isInteger(v) || v < min || v > max) e[k] = tv("range", { min, max });
    }
    if (d.warn_hours_per_person_day > d.max_hours_per_person_day) e.warn_hours_per_person_day = tv("invalid");
    if (!MMDD.test(d.heat_season.start)) e.heat_start = tv("invalid");
    if (!MMDD.test(d.heat_season.end)) e.heat_end = tv("invalid");
    for (const p of CA_PRIORITIES) {
      const v = d.ca_due_days[p];
      if (v === undefined || v < 1 || v > 90) e[`ca_${p}`] = tv("range", { min: 1, max: 90 });
    }
    for (const [m, v] of Object.entries(d.kpi_targets)) if (v !== undefined && v !== "" && !/^-?\d+(\.\d+)?$/.test(v)) e[`target_${m}`] = tv("number");
    setErrors(e);
    if (Object.keys(e).length) return;
    setBusy(true);
    setError(null);
    try {
      const targets = Object.fromEntries(Object.entries(d.kpi_targets).filter(([, v]) => v !== undefined && v !== ""));
      const next = await unwrap(
        api.PATCH("/api/v1/projects/{project_id}/hse-settings", {
          params: { path: { project_id: project.id } },
          body: {
            lost_days_cap: d.lost_days_cap,
            fatality_lost_days_charge: d.fatality_lost_days_charge,
            include_commuting_in_rates: d.include_commuting_in_rates,
            include_non_contractor_cases_in_rates: d.include_non_contractor_cases_in_rates,
            max_hours_per_person_day: d.max_hours_per_person_day,
            warn_hours_per_person_day: d.warn_hours_per_person_day,
            daily_return_deadline: d.daily_return_deadline,
            completeness_threshold_pct: d.completeness_threshold_pct,
            inspection_grace_days: d.inspection_grace_days,
            ca_due_days: d.ca_due_days,
            ca_max_extensions: d.ca_max_extensions,
            new_starter_days: d.new_starter_days,
            heat_season: d.heat_season,
            low_exposure_hours: d.low_exposure_hours,
            leading_warning_drop_pct: d.leading_warning_drop_pct,
            leading_warning_rise_pct: d.leading_warning_rise_pct,
            kpi_targets: targets,
            month_lock_day: d.month_lock_day,
            injury_identity_retention_years: d.injury_identity_retention_years,
          },
        }),
      );
      qc.setQueryData(hk.hseSettings(project.id), next);
      setEdits({});
      await qc.invalidateQueries({ queryKey: ["kpi"] });
      toast.success(tc("saved"));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const num = (k: NumKey) => (
    <FormField id={`hs-${k}`} label={t(`fields.${k}`)} error={errors[k]}>
      <Input inputMode="numeric" className="ltr" disabled={!editable} value={String(d[k])} onChange={(e) => set(k, Number(e.target.value.replace(/\D/g, "") || 0))} />
    </FormField>
  );
  const bool = (k: "include_commuting_in_rates" | "include_non_contractor_cases_in_rates") => (
    <label className="flex min-h-touch items-center gap-3 text-sm">
      <Checkbox disabled={!editable} checked={d[k]} onChange={(e) => set(k, e.target.checked)} />
      {t(`fields.${k}`)}
    </label>
  );

  return (
    <div className="flex flex-col gap-6" data-testid="hse-settings">
      <PageHeader title={t("title")} description={t("subtitle")} />
      {!editable ? <Alert tone="info">{t("readOnly")}</Alert> : null}
      <AiSection project={project} settings={q.data} editable={editable} />
      <FormSection title={t("rates")}>
        <FormField id="hs-cap" label={t("fields.lost_days_cap")}>
          <Select disabled={!editable} value={String(d.lost_days_cap)} onChange={(e) => set("lost_days_cap", Number(e.target.value))}>
            <option value="180">180 (OSHA)</option>
            <option value="0">0 — {tc("none")}</option>
          </Select>
        </FormField>
        <FormField id="hs-fat" label={t("fields.fatality_lost_days_charge")}>
          <Select disabled={!editable} value={String(d.fatality_lost_days_charge)} onChange={(e) => set("fatality_lost_days_charge", Number(e.target.value))}>
            <option value="0">0</option>
            <option value="6000">6000 (ANSI Z16.1)</option>
          </Select>
        </FormField>
        {bool("include_commuting_in_rates")}
        {bool("include_non_contractor_cases_in_rates")}
        {num("low_exposure_hours")}
        {num("injury_identity_retention_years")}
      </FormSection>
      <FormSection title={t("workforce")}>
        {num("max_hours_per_person_day")}
        {num("warn_hours_per_person_day")}
        <FormField id="hs-deadline" label={t("fields.daily_return_deadline")}>
          <Input type="time" disabled={!editable} value={d.daily_return_deadline.slice(0, 5)} onChange={(e) => set("daily_return_deadline", e.target.value)} />
        </FormField>
        {num("completeness_threshold_pct")}
        {num("month_lock_day")}
        {num("new_starter_days")}
        <FormField id="hs-heat-start" label={t("fields.heat_season_start")} error={errors.heat_start}>
          <Input className="ltr" disabled={!editable} value={d.heat_season.start} onChange={(e) => set("heat_season", { ...d.heat_season, start: e.target.value })} placeholder="06-01" />
        </FormField>
        <FormField id="hs-heat-end" label={t("fields.heat_season_end")} error={errors.heat_end}>
          <Input className="ltr" disabled={!editable} value={d.heat_season.end} onChange={(e) => set("heat_season", { ...d.heat_season, end: e.target.value })} placeholder="09-30" />
        </FormField>
      </FormSection>
      <FormSection title={t("actions")}>
        {num("inspection_grace_days")}
        {num("ca_max_extensions")}
        <fieldset className="grid grid-cols-2 gap-3 sm:col-span-2 sm:grid-cols-4">
          <legend className="mb-1 text-sm font-medium">{t("fields.ca_due_days")}</legend>
          {CA_PRIORITIES.map((p) => (
            <FormField key={p} id={`hs-ca-${p}`} label={te(`caPriority.${p}`)} error={errors[`ca_${p}`]}>
              <Input inputMode="numeric" className="ltr" disabled={!editable} value={String(d.ca_due_days[p] ?? "")} onChange={(e) => set("ca_due_days", { ...d.ca_due_days, [p]: Number(e.target.value.replace(/\D/g, "") || 0) })} />
            </FormField>
          ))}
        </fieldset>
      </FormSection>
      <FormSection title={t("warnings")}>
        {num("leading_warning_drop_pct")}
        {num("leading_warning_rise_pct")}
      </FormSection>
      <Card>
        <CardHeader>
          <CardTitle>{t("targets")}</CardTitle>
          <p className="text-xs text-muted-foreground">{t("targetsHint")}</p>
        </CardHeader>
        <CardContent>
          {cat.isLoading ? (
            <LoadingState />
          ) : (
            <Table data-testid="targets-table">
              <THead>
                <TR>
                  <TH>{t("metric")}</TH>
                  <TH>{t("better")}</TH>
                  <TH>{t("target")}</TH>
                </TR>
              </THead>
              <TBody>
                {(cat.data?.items ?? [])
                  .filter((k) => k.available)
                  .map((k) => (
                    <TR key={k.metric}>
                      <TD label={t("metric")}>
                        <span className="ltr me-2 text-xs text-muted-foreground">{k.metric}</span>
                        {locale === "ar" ? k.label_ar : k.label_en}
                      </TD>
                      <TD label={t("better")}>{k.better === "none" ? "—" : t(k.better === "lower" ? "lower" : "higher")}</TD>
                      <TD label={t("target")}>
                        <Input
                          aria-label={`${t("target")} ${k.metric}`}
                          inputMode="decimal"
                          className="ltr w-32"
                          disabled={!editable}
                          placeholder={t("noTarget")}
                          value={d.kpi_targets[k.metric] ?? ""}
                          onChange={(e) => set("kpi_targets", { ...d.kpi_targets, [k.metric]: e.target.value })}
                          data-testid={`target-${k.metric}`}
                        />
                        {errors[`target_${k.metric}`] ? <p className="text-xs text-destructive">{errors[`target_${k.metric}`]}</p> : null}
                      </TD>
                    </TR>
                  ))}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <MutationError error={error} />
      {editable ? (
        <div>
          <Button onClick={() => void save()} disabled={busy} data-testid="save-settings">
            {busy ? tc("saving") : tc("save")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function AiSection({ project, settings: s, editable }: { project: Schemas["ProjectRead"]; settings: Settings; editable: boolean }) {
  const t = useTranslations("hseSettings");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const name = useLocalizedName();
  const { date, dateTime } = useFormatters(project.id);
  const [form, setForm] = useState({ approved_on: todayInZone(), approver_name: "", approver_organisation: "", reference: "", notes: "" });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const approval = s.ai_transfer_approval;

  async function refresh(next?: Settings) {
    if (next) qc.setQueryData(hk.hseSettings(project.id), next);
    else await qc.invalidateQueries({ queryKey: hk.hseSettings(project.id) });
    await qc.invalidateQueries({ queryKey: ["ai-status"] });
  }
  async function toggle(on: boolean) {
    setBusy(true);
    setError(null);
    try {
      const next = await unwrap(api.PATCH("/api/v1/projects/{project_id}/hse-settings", { params: { path: { project_id: project.id } }, body: { ai_enabled: on } }));
      await refresh(next);
      toast.success(tc("saved"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function record() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(
        api.POST("/api/v1/projects/{project_id}/ai-transfer-approval", {
          params: { path: { project_id: project.id } },
          body: {
            approved_on: form.approved_on,
            approver_name: form.approver_name.trim(),
            approver_organisation: form.approver_organisation.trim(),
            reference: form.reference.trim() || null,
            notes: form.notes.trim() || null,
          },
        }),
      );
      await refresh();
      toast.success(tc("saved"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function withdraw() {
    if (!window.confirm(t("withdrawConfirm"))) return;
    setBusy(true);
    setError(null);
    try {
      await unwrap(api.DELETE("/api/v1/projects/{project_id}/ai-transfer-approval", { params: { path: { project_id: project.id } } }));
      await refresh();
      toast.success(tc("saved"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card data-testid="ai-settings">
      <CardHeader>
        <CardTitle>{t("ai")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <Alert tone={s.ai_enabled ? "success" : "info"} data-testid="ai-effective">
          {t("aiEffective", { state: s.ai_enabled ? t("aiOn") : t("aiOff") })} {!approval ? t("aiNeedsApproval") : null}
        </Alert>
        <label className="flex min-h-touch items-center gap-3 text-sm">
          <Checkbox disabled={!editable || busy} checked={s.ai_requested} onChange={(e) => void toggle(e.target.checked)} data-testid="ai-requested" />
          {t("aiRequested")}
        </label>
        <div>
          <p className="mb-2 text-sm font-medium">{t("approval")}</p>
          {approval ? (
            <div className="flex flex-col gap-2 rounded-md border p-3 text-sm" data-testid="ai-approval">
              <p>
                <ShieldCheck aria-hidden className="me-1 inline size-4 text-success" />
                {approval.approver_name} — {approval.approver_organisation} · {date(approval.approved_on)}
                {approval.reference ? <span className="ltr"> · {approval.reference}</span> : null}
              </p>
              {approval.notes ? <p className="text-muted-foreground">{approval.notes}</p> : null}
              <p className="text-xs text-muted-foreground">{t("recordedBy", { name: name(approval.recorded_by.full_name_en, approval.recorded_by.full_name_ar), date: dateTime(approval.recorded_at) })}</p>
              {editable ? (
                <div>
                  <Button size="sm" variant="outline" onClick={() => void withdraw()} disabled={busy} data-testid="withdraw-approval">
                    <ShieldOff aria-hidden />
                    {t("withdrawApproval")}
                  </Button>
                </div>
              ) : null}
            </div>
          ) : editable ? (
            <div className="grid gap-3 sm:grid-cols-2" data-testid="approval-form">
              <FormField id="ap-on" label={t("fields.approved_on")} required>
                <Input type="date" value={form.approved_on} onChange={(e) => setForm({ ...form, approved_on: e.target.value })} />
              </FormField>
              <FormField id="ap-name" label={t("fields.approver_name")} required>
                <Input maxLength={120} value={form.approver_name} onChange={(e) => setForm({ ...form, approver_name: e.target.value })} />
              </FormField>
              <FormField id="ap-org" label={t("fields.approver_organisation")} required>
                <Input maxLength={120} value={form.approver_organisation} onChange={(e) => setForm({ ...form, approver_organisation: e.target.value })} />
              </FormField>
              <FormField id="ap-ref" label={t("fields.reference")}>
                <Input maxLength={60} className="ltr" value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} />
              </FormField>
              <FormField id="ap-notes" label={t("fields.notes")} className="sm:col-span-2">
                <Textarea maxLength={500} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
              </FormField>
              <div>
                <Button onClick={() => void record()} disabled={busy || !form.approver_name.trim() || !form.approver_organisation.trim() || !form.approved_on} data-testid="record-approval">
                  {t("recordApproval")}
                </Button>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{t("noApproval")}</p>
          )}
        </div>
        <MutationError error={error} />
      </CardContent>
    </Card>
  );
}
