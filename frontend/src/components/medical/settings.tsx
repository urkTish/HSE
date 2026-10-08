"use client";
import { Lock, ShieldCheck } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { FormField } from "@/components/common/form-field";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { ProjectGate } from "@/components/common/project-gate";
import { ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Code, StepDialog } from "@/components/access/common";
import { HookKindCard, Readiness } from "@/components/cert/config";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useCertRefresh, useHookPolicy } from "@/lib/api/cert";
import { useMedicalRefresh, useMedicalSettings } from "@/lib/api/medical";
import { todayInZone } from "@/lib/datetime";
import { CASE_CATEGORIES } from "@/lib/enums";
import { useFormatters } from "@/lib/use-formatters";
import { useFitnessCatalogue, useMedCaps } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];
type Settings = S["MedicalSettingsRead"];

type NumKey =
  | "medical_hook_transition_days"
  | "medical_hook_critical_transition_days"
  | "unverified_fitness_acceptance_hours"
  | "fitness_verification_due_days"
  | "referral_assessment_hours"
  | "signoff_due_hours"
  | "assessment_backdate_max_days"
  | "restriction_review_max_days"
  | "unfit_review_max_days"
  | "medical_line_max_due_days"
  | "medical_compliance_warning_pct"
  | "health_cell_min"
  | "fitness_scan_retention_months"
  | "fitness_record_retention_years"
  | "surveillance_record_retention_years";

/** §3.12 "Allowed" ranges; the server is the judge (422 VALIDATION / SETTING_LOOSENING), these are hints. */
const GROUPS: { title: "groupHooks" | "groupVerification" | "groupDeadlines" | "groupReporting" | "groupRetention"; keys: { k: NumKey; range: string; decimal?: boolean }[] }[] = [
  { title: "groupHooks", keys: [{ k: "medical_hook_transition_days", range: "0–30" }, { k: "medical_hook_critical_transition_days", range: "0–7" }] },
  { title: "groupVerification", keys: [{ k: "unverified_fitness_acceptance_hours", range: "0–24" }, { k: "fitness_verification_due_days", range: "1–14" }] },
  {
    title: "groupDeadlines",
    keys: [
      { k: "referral_assessment_hours", range: "4–72" },
      { k: "signoff_due_hours", range: "24–72" },
      { k: "assessment_backdate_max_days", range: "0–14" },
      { k: "restriction_review_max_days", range: "30–180" },
      { k: "unfit_review_max_days", range: "14–180" },
      { k: "medical_line_max_due_days", range: "0–30" },
    ],
  },
  { title: "groupReporting", keys: [{ k: "medical_compliance_warning_pct", range: "80.0–100.0", decimal: true }, { k: "health_cell_min", range: "5–10" }] },
  {
    title: "groupRetention",
    keys: [
      { k: "fitness_scan_retention_months", range: "6–24" },
      { k: "fitness_record_retention_years", range: "5–30" },
      { k: "surveillance_record_retention_years", range: "10–40" },
    ],
  },
];

export function MedicalSettingsPage() {
  return <ProjectGate>{(p) => <MedicalSettings project={p} />}</ProjectGate>;
}

function MedicalSettings({ project }: { project: Project }) {
  const t = useTranslations("medical.settings");
  const caps = useMedCaps(project.id);
  const q = useMedicalSettings(project.id);
  const policy = useHookPolicy(project.id);
  const [enable, setEnable] = useState(false);
  const s = q.data;
  const medKind = policy.data?.kinds.find((k) => k.kind === "medical_fitness");
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          s && !s.medical_hooks_enabled && caps.settings ? (
            <Button onClick={() => setEnable(true)} data-testid="enable-medical-hooks">
              <ShieldCheck aria-hidden />
              {t("enableHooks")}
            </Button>
          ) : null
        }
      />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : s ? (
        <div className="flex flex-col gap-4">
          <Alert tone={s.medical_hooks_enabled ? "success" : "warning"} data-testid="medical-hooks-state" data-enabled={s.medical_hooks_enabled}>
            {s.medical_hooks_enabled ? t("hooksOn") : t("hooksOff")}
          </Alert>
          {medKind && policy.data ? <HookKindCard project={project} k={medKind} editable={caps.settings} asOf={policy.data.as_of} /> : null}
          {caps.settings ? <Readiness project={project} kinds={["medical_fitness"]} /> : null}
          <SettingsForm key={s.updated_at ?? "x"} project={project} s={s} editable={caps.settings} />
        </div>
      ) : null}
      {enable ? <EnableDialog project={project} onClose={() => setEnable(false)} /> : null}
    </div>
  );
}

function EnableDialog({ project, onClose }: { project: Project; onClose: () => void }) {
  const t = useTranslations("medical.settings");
  const refresh = useMedicalRefresh();
  const certRefresh = useCertRefresh();
  const [regOn, setRegOn] = useState(todayInZone());
  return (
    <StepDialog
      title={t("enableHooks")}
      description={t("enableHint")}
      confirmLabel={t("enableHooks")}
      testId="enable-medical-confirm"
      onConfirm={async () => {
        await unwrap(api.POST("/api/v1/projects/{project_id}/medical-hooks/enable", { params: { path: { project_id: project.id } }, body: { registered_on: regOn || null } }));
        toast.success(t("enabled"));
        refresh();
        certRefresh();
      }}
      onClose={onClose}
    >
      <FormField id="mh-reg" label={t("registeredOn")} hint={t("registeredOnHint")}>
        <Input id="mh-reg" type="date" dir="ltr" value={regOn} onChange={(e) => setRegOn(e.target.value)} data-testid="mh-reg" />
      </FormField>
    </StepDialog>
  );
}

function SettingsForm({ project, s, editable }: { project: Project; s: Settings; editable: boolean }) {
  const t = useTranslations("medical.settings");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const { dateTime } = useFormatters(project.id);
  const refresh = useMedicalRefresh();
  const cat = useFitnessCatalogue(project.id);
  const init = useMemo(() => Object.fromEntries(GROUPS.flatMap((g) => g.keys.map((x) => [x.k, String(s[x.k] ?? "")]))) as Record<NumKey, string>, [s]);
  const [nums, setNums] = useState<Record<NumKey, string>>(init);
  const [registerFrom, setRegisterFrom] = useState(s.medical_register_from ?? "");
  const [critical, setCritical] = useState<string[]>(s.medical_hook_critical_codes);
  const [rtw, setRtw] = useState<string[]>(s.rtw_hold_case_categories);
  const [notice, setNotice] = useState(s.worker_purpose_notice_version);
  const validityInit = s.fitness_validity_months as Record<string, number>;
  const [validity, setValidity] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(validityInit).map(([k, v]) => [k, String(v)])));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const body: S["MedicalSettingsUpdate"] = {};
  for (const g of GROUPS)
    for (const x of g.keys) {
      if (nums[x.k] === init[x.k] || nums[x.k] === "") continue;
      if (x.k === "medical_compliance_warning_pct") body.medical_compliance_warning_pct = nums[x.k];
      else body[x.k] = Number(nums[x.k]);
    }
  if ((registerFrom || null) !== s.medical_register_from && registerFrom) body.medical_register_from = registerFrom;
  if (JSON.stringify([...critical].sort()) !== JSON.stringify([...s.medical_hook_critical_codes].sort())) body.medical_hook_critical_codes = critical;
  if (JSON.stringify([...rtw].sort()) !== JSON.stringify([...s.rtw_hold_case_categories].sort())) body.rtw_hold_case_categories = rtw;
  if (notice.trim() && notice.trim() !== s.worker_purpose_notice_version) body.worker_purpose_notice_version = notice.trim();
  const vm = Object.fromEntries(Object.entries(validity).filter(([, v]) => v !== "").map(([k, v]) => [k, Number(v)]));
  if (JSON.stringify(vm) !== JSON.stringify(validityInit)) body.fitness_validity_months = vm;
  const dirty = Object.keys(body).length > 0;

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const r = await unwrap(api.PATCH("/api/v1/projects/{project_id}/medical-settings", { params: { path: { project_id: project.id } }, body }));
      toast.success(t("saved", { n: r.changed.length }));
      refresh();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const egDefaults = s.exposure_group_trade_defaults as Record<string, string[]>;
  return (
    <div className="flex flex-col gap-4" data-testid="medical-settings">
      {!editable ? <Alert tone="info">{t("readOnly")}</Alert> : null}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("groupRegister")}</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2">
          <FormField id="ms-register-from" label={t("medical_register_from")} hint={t("registerHint")}>
            <Input id="ms-register-from" type="date" dir="ltr" value={registerFrom} disabled={!editable} onChange={(e) => setRegisterFrom(e.target.value)} data-testid="ms-register-from" />
          </FormField>
          <FormField id="ms-notice" label={t("worker_purpose_notice_version")}>
            <Input id="ms-notice" dir="ltr" value={notice} disabled={!editable} maxLength={60} onChange={(e) => setNotice(e.target.value)} />
          </FormField>
        </CardContent>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        {GROUPS.map((g) => (
          <Card key={g.title}>
            <CardHeader>
              <CardTitle className="text-base">{t(g.title)}</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              {g.keys.map((x) => (
                <FormField key={x.k} id={`ms-${x.k}`} label={t(x.k)} hint={t("allowed", { range: x.range })}>
                  <Input
                    id={`ms-${x.k}`}
                    inputMode={x.decimal ? "decimal" : "numeric"}
                    dir="ltr"
                    value={nums[x.k]}
                    disabled={!editable}
                    onChange={(e) => setNums({ ...nums, [x.k]: e.target.value.replace(x.decimal ? /[^\d.]/g : /\D/g, "") })}
                    data-testid={`ms-${x.k}`}
                  />
                </FormField>
              ))}
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("medical_hook_critical_codes")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <p className="text-xs text-muted-foreground">{t("addOnly")}</p>
          <MultiSelect
            id="ms-critical"
            label={t("medical_hook_critical_codes")}
            options={cat.codes.filter((c) => c.hook_code).map((c) => ({ value: c.code, label: c.code, disabled: s.medical_hook_critical_codes.includes(c.code) }))}
            value={critical}
            onChange={(v) => setCritical([...new Set([...s.medical_hook_critical_codes, ...v])])}
          />
          <div className="flex flex-wrap gap-1">
            {critical.map((c) => (
              <Badge key={c} tone="neutral">
                <Lock className="size-3" aria-hidden /> {c}
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("fitness_validity_months")}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="mb-2 text-xs text-muted-foreground">{t("shortenOnly")}</p>
            <Table>
              <THead>
                <TR>
                  <TH>{t("code")}</TH>
                  <TH>{t("catalogue")}</TH>
                  <TH>{t("months")}</TH>
                </TR>
              </THead>
              <TBody>
                {cat.codes.map((c) => (
                  <TR key={c.code}>
                    <TD label={t("code")}>
                      <Code>{c.code}</Code> <span className="text-muted-foreground">{locale === "ar" ? c.name_ar : c.name_en}</span>
                    </TD>
                    <TD label={t("catalogue")}>{c.validity_months}</TD>
                    <TD label={t("months")}>
                      <Input
                        aria-label={t("months")}
                        className="w-20"
                        dir="ltr"
                        inputMode="numeric"
                        placeholder={String(c.validity_months)}
                        disabled={!editable}
                        value={validity[c.code] ?? ""}
                        onChange={(e) => setValidity({ ...validity, [c.code]: e.target.value.replace(/\D/g, "") })}
                        data-testid={`ms-validity-${c.code}`}
                      />
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </CardContent>
        </Card>
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("rtw_hold_case_categories")}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="mb-2 text-xs text-muted-foreground">{t("addOnly")}</p>
              <CheckboxGroup
                id="ms-rtw"
                legend={t("rtw_hold_case_categories")}
                options={CASE_CATEGORIES.map((c) => ({ value: c, label: te(`caseCategory.${c}`) }))}
                disabled={!editable}
                value={rtw}
                onChange={(v) => setRtw([...new Set([...s.rtw_hold_case_categories, ...v])])}
              />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("readOnlyLists")}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 text-sm">
              <div>
                <p className="font-medium">{t("heat_illness_natures")}</p>
                <p className="text-muted-foreground">{s.heat_illness_natures.map((n) => (te.has(`heatNature.${n as "heat_stroke"}`) ? te(`heatNature.${n as "heat_stroke"}`) : n)).join(" · ")}</p>
              </div>
              <div>
                <p className="font-medium">{t("exposure_group_trade_defaults")}</p>
                <ul className="flex flex-col gap-1">
                  {Object.entries(egDefaults).map(([eg, trades]) => (
                    <li key={eg}>
                      <span>{te.has(`exposureGroup.${eg as S["ExposureGroup"]}`) ? te(`exposureGroup.${eg as S["ExposureGroup"]}`) : eg}</span>
                      {": "}
                      <span className="text-muted-foreground">{trades.length ? trades.map((x) => (te.has(`trade.${x as S["Trade"]}`) ? te(`trade.${x as S["Trade"]}`) : x)).join(", ") : "—"}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        {t("alertSchedule", { days: s.alert_schedule_long_days.join(", ") })}
        {s.updated_at ? ` · ${t("lastUpdated", { at: dateTime(s.updated_at) })}` : null}
      </p>
      <MutationError error={error} />
      {editable ? (
        <div className="sticky bottom-0 flex justify-end gap-2 border-t bg-background py-3">
          <Button onClick={() => void save()} disabled={!dirty || busy} data-testid="save-medical-settings">
            {busy ? tc("saving") : tc("save")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
