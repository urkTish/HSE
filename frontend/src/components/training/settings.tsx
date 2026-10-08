"use client";
import { Lock, ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { FormField } from "@/components/common/form-field";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { ProjectGate } from "@/components/common/project-gate";
import { ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Code, StepDialog } from "@/components/access/common";
import { UserName } from "@/components/cert/common";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useTrainingRefresh, useTrainingSettings } from "@/lib/api/training";
import { COURSE_CATEGORIES } from "@/lib/train-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useCourseCatalogue, useTrainingCaps } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];
type Settings = S["TrainingSettingsRead"];

type IntKey =
  | "training_pass_mark_pct"
  | "training_max_attempts_30d"
  | "unverified_training_acceptance_hours"
  | "training_verification_due_days"
  | "session_close_deadline_days"
  | "session_backdate_max_days"
  | "trainer_authorisation_max_months"
  | "refresher_planning_days"
  | "refresher_max_lapse_days"
  | "matrix_line_max_due_days"
  | "training_hook_transition_days"
  | "training_hook_critical_transition_days"
  | "training_scan_retention_years";
type DecKey = "session_day_max_net_hours" | "training_matrix_warning_pct";
type Field = { k: IntKey | DecKey; min: number; max: number; decimal?: boolean };

const GROUPS: { title: "groupRecords" | "groupSessions" | "groupPlanning" | "groupHooks"; keys: Field[] }[] = [
  {
    title: "groupRecords",
    keys: [
      { k: "training_pass_mark_pct", min: 50, max: 100 },
      { k: "training_max_attempts_30d", min: 1, max: 5 },
      { k: "unverified_training_acceptance_hours", min: 0, max: 24 },
      { k: "training_verification_due_days", min: 1, max: 14 },
      { k: "training_scan_retention_years", min: 1, max: 10 },
    ],
  },
  {
    title: "groupSessions",
    keys: [
      { k: "session_close_deadline_days", min: 1, max: 7 },
      { k: "session_backdate_max_days", min: 0, max: 14 },
      { k: "session_day_max_net_hours", min: 4, max: 10, decimal: true },
      { k: "trainer_authorisation_max_months", min: 6, max: 24 },
    ],
  },
  {
    title: "groupPlanning",
    keys: [
      { k: "refresher_planning_days", min: 30, max: 120 },
      { k: "refresher_max_lapse_days", min: 0, max: 30 },
      { k: "matrix_line_max_due_days", min: 0, max: 180 },
      { k: "training_matrix_warning_pct", min: 80, max: 100, decimal: true },
    ],
  },
  {
    title: "groupHooks",
    keys: [
      { k: "training_hook_transition_days", min: 0, max: 30 },
      { k: "training_hook_critical_transition_days", min: 0, max: 7 },
    ],
  },
];

export function TrainingSettingsPage() {
  return <ProjectGate>{(p) => <TrainingSettings project={p} />}</ProjectGate>;
}

function TrainingSettings({ project }: { project: Project }) {
  const t = useTranslations("training.settings");
  const caps = useTrainingCaps(project.id);
  const q = useTrainingSettings(project.id);
  const [enable, setEnable] = useState(false);
  const [regOn, setRegOn] = useState("");
  const refresh = useTrainingRefresh();
  const s = q.data;
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          s && !s.training_hooks_enabled && caps.settings ? (
            <Button onClick={() => setEnable(true)} data-testid="enable-training-hooks">
              <ShieldCheck aria-hidden />
              {t("enableHooks")}
            </Button>
          ) : null
        }
      />
      {q.isLoading ? <LoadingState /> : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : s ? <SettingsForm key={s.updated_at ?? "x"} project={project} s={s} editable={caps.settings} /> : null}
      {enable ? (
        <StepDialog
          title={t("enableTitle")}
          description={t("enableHint")}
          confirmLabel={t("enableHooks")}
          testId="enable-training-confirm"
          onConfirm={async () => {
            await unwrap(api.POST("/api/v1/projects/{project_id}/training-hooks/enable", { params: { path: { project_id: project.id } }, body: { registered_on: regOn || null } }));
            toast.success(t("hooksEnabled"));
            await refresh();
          }}
          onClose={() => setEnable(false)}
        >
          <p className="text-sm">
            <Link href="/hook-policy?kind=training_course" className="text-primary hover:underline">
              {t("readReadiness")}
            </Link>
          </p>
          <FormField id="th-reg" label={t("registeredOn")} hint={t("registeredOnHint")}>
            <Input id="th-reg" type="date" dir="ltr" value={regOn} onChange={(e) => setRegOn(e.target.value)} />
          </FormField>
        </StepDialog>
      ) : null}
    </div>
  );
}

function SettingsForm({ project, s, editable }: { project: Project; s: Settings; editable: boolean }) {
  const t = useTranslations("training.settings");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const { date, dateTime } = useFormatters(project.id);
  const refresh = useTrainingRefresh();
  const cat = useCourseCatalogue(project.id);
  const init = useMemo(() => {
    const v: Record<string, string> = {};
    for (const g of GROUPS) for (const x of g.keys) v[x.k] = String(s[x.k] ?? "");
    return v;
  }, [s]);
  const [nums, setNums] = useState<Record<string, string>>(init);
  const curValidity = s.course_validity_months as Record<string, number>;
  const [validity, setValidity] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(curValidity).map(([k, v]) => [k, String(v)])));
  const [blockCats, setBlockCats] = useState<string[]>(s.language_block_categories);
  const [critical, setCritical] = useState<string[]>(s.training_hook_critical_codes);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const validityCourses = cat.courses.filter((c) => c.validity_months != null || curValidity[c.code] != null);
  const hookCourses = cat.courses.filter((c) => c.hook_code);

  function buildBody(): S["TrainingSettingsUpdate"] {
    const body: Record<string, unknown> = {};
    for (const g of GROUPS)
      for (const x of g.keys) {
        if (nums[x.k] === init[x.k]) continue;
        body[x.k] = x.decimal ? nums[x.k] : Number(nums[x.k]);
      }
    const vm = Object.fromEntries(Object.entries(validity).filter(([, v]) => v !== "").map(([k, v]) => [k, Number(v)]));
    if (JSON.stringify(vm) !== JSON.stringify(curValidity)) body.course_validity_months = vm;
    if (JSON.stringify([...blockCats].sort()) !== JSON.stringify([...s.language_block_categories].sort())) body.language_block_categories = blockCats;
    if (JSON.stringify([...critical].sort()) !== JSON.stringify([...s.training_hook_critical_codes].sort())) body.training_hook_critical_codes = critical;
    return body as S["TrainingSettingsUpdate"];
  }
  const body = buildBody();
  const dirty = Object.keys(body).length > 0;

  async function save() {
    const e: Record<string, string> = {};
    for (const g of GROUPS)
      for (const x of g.keys) {
        const raw = nums[x.k];
        const v = Number(raw);
        if (raw === "" || Number.isNaN(v) || v < x.min || v > x.max || (!x.decimal && !Number.isInteger(v))) e[x.k] = tv("range", { min: x.min, max: x.max });
      }
    setErrors(e);
    if (Object.keys(e).length) return;
    setBusy(true);
    setError(null);
    try {
      await unwrap(api.PATCH("/api/v1/projects/{project_id}/training-settings", { params: { path: { project_id: project.id } }, body }));
      toast.success(t("saved"));
      await refresh();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4" data-testid="training-settings">
      {!editable ? <Alert tone="info">{t("readOnly")}</Alert> : null}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("groupRegister")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          <p data-testid="training-register-from">
            {t("registerFrom")}: <span className="font-medium">{s.training_register_from ? date(s.training_register_from) : t("notSet")}</span>{" "}
            <Link href="/hse-settings" className="text-primary hover:underline">
              {t("editInHse")}
            </Link>
          </p>
          <p className="text-xs text-muted-foreground">{t("registerHint")}</p>
          <p data-testid="training-hooks-state">
            {t("hooks")}:{" "}
            {s.training_hooks_enabled ? (
              <Badge tone="success">{t("hooksOn")}</Badge>
            ) : (
              <Badge tone="neutral">{t("hooksOff")}</Badge>
            )}{" "}
            <Link href="/hook-policy" className="text-primary hover:underline">
              {t("openHookPolicy")}
            </Link>
          </p>
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
                <FormField key={x.k} id={`ts-${x.k}`} label={t(`f.${x.k}`)} hint={t("allowed", { range: `${x.min}–${x.max}` })} error={errors[x.k]}>
                  <Input
                    id={`ts-${x.k}`}
                    inputMode={x.decimal ? "decimal" : "numeric"}
                    dir="ltr"
                    value={nums[x.k] ?? ""}
                    disabled={!editable}
                    onChange={(e) => setNums({ ...nums, [x.k]: e.target.value.replace(x.decimal ? /[^\d.]/g : /\D/g, "") })}
                    data-testid={`ts-${x.k}`}
                  />
                </FormField>
              ))}
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("languageBlock")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            <p className="text-xs text-muted-foreground">{t("addOnly")}</p>
            <MultiSelect
              id="ts-lang-block"
              label={t("languageBlock")}
              options={COURSE_CATEGORIES.map((c) => ({ value: c, label: te(`courseCategory.${c}`), disabled: s.language_block_categories.includes(c) }))}
              value={blockCats}
              onChange={(v) => setBlockCats([...new Set([...s.language_block_categories, ...v])])}
              testId="ts-lang-block"
              allLabel={tc("none")}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("criticalCodes")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            <p className="text-xs text-muted-foreground">{t("criticalHint")}</p>
            <MultiSelect
              id="ts-critical"
              label={t("criticalCodes")}
              options={hookCourses.map((c) => ({ value: c.code, label: c.code, disabled: s.training_hook_critical_codes.includes(c.code) }))}
              value={critical}
              onChange={(v) => setCritical([...new Set([...s.training_hook_critical_codes, ...v])])}
              testId="ts-critical"
              allLabel={tc("none")}
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
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("validity")}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="mb-2 text-xs text-muted-foreground">{t("validityHint")}</p>
          {cat.isLoading ? (
            <LoadingState rows={2} />
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>{t("course")}</TH>
                  <TH>{t("catalogueMonths")}</TH>
                  <TH>{t("projectMonths")}</TH>
                </TR>
              </THead>
              <TBody>
                {validityCourses.map((c) => (
                  <TR key={c.code}>
                    <TD label={t("course")}>
                      <Code>{c.code}</Code> <span className="text-muted-foreground">{cat.label(c.code)}</span>
                    </TD>
                    <TD label={t("catalogueMonths")}>{c.validity_months ?? t("noExpiry")}</TD>
                    <TD label={t("projectMonths")}>
                      <Input
                        aria-label={`${t("projectMonths")} ${c.code}`}
                        className="w-20"
                        dir="ltr"
                        inputMode="numeric"
                        disabled={!editable}
                        value={validity[c.code] ?? ""}
                        placeholder="—"
                        onChange={(e) => setValidity({ ...validity, [c.code]: e.target.value.replace(/\D/g, "") })}
                        data-testid={`ts-validity-${c.code}`}
                      />
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <p className="text-xs text-muted-foreground">
        {t("alertSchedule", { days: s.alert_schedule_long_days.join(", ") })}
        {s.updated_at ? (
          <>
            {" · "}
            {t("lastUpdated", { at: dateTime(s.updated_at) })} <UserName u={s.updated_by} />
          </>
        ) : null}
      </p>
      <MutationError error={error} />
      {editable ? (
        <div className="sticky bottom-0 flex justify-end gap-2 border-t bg-background py-3">
          <Button onClick={() => void save()} disabled={!dirty || busy} data-testid="save-training-settings">
            {busy ? tc("saving") : tc("save")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
