"use client";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Code, StepDialog } from "@/components/access/common";
import { FormField } from "@/components/common/form-field";
import { PageHeader } from "@/components/common/page-header";
import { ProjectGate } from "@/components/common/project-gate";
import { ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useFuRefresh, useFuRules, useFuSettings } from "@/lib/api/followup";
import { useDisplay } from "@/lib/digits";
import { Choices, FuSubNav, useFuCaps } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];

const TRIGGERS: S["FuTrigger"][] = [
  "recordable_contractor_case",
  "commuting_case",
  "fatality",
  "permanent_disability",
  "lti",
  "fire_explosion_do",
  "any_do",
  "hipo",
  "gaca_airside_flag",
  "any_airside_flag",
  "env_ncec",
  "env_airside",
  "any_recordable_case",
  "property_damage_ge_sar",
];
const FORMS: S["FuForm"][] = ["CLIENT-FLASH", "CLIENT-INTERIM", "CLIENT-FINAL"];
const STAGES: S["FuStage"][] = ["verbal", "written", "interim", "final"];
const LEVELS: S["InvestigationLevel"][] = ["L2", "L3"];

export function FollowupSettingsPage() {
  return <ProjectGate>{(p) => <SettingsPage project={p} />}</ProjectGate>;
}

function SettingsPage({ project }: { project: Project }) {
  const t = useTranslations("fu.settings");
  const tc = useTranslations("common");
  const caps = useFuCaps(project.id);
  const q = useFuSettings(project.id, { enabled: caps.view || caps.settings });
  if (!caps.view && !caps.settings) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <FuSubNav />
      {!caps.settings ? (
        <Alert tone="info" className="mb-4" data-testid="fu-settings-readonly">
          {t("readOnly")}
        </Alert>
      ) : null}
      <div className="flex flex-col gap-6">
        {q.isLoading ? <LoadingState /> : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.data ? <SettingsForm key={JSON.stringify(q.data)} project={project} s={q.data} editable={caps.settings} /> : null}
        <Rules project={project} editable={caps.settings} />
      </div>
    </div>
  );
}

type NumKey = "notification_alert_lead_hours" | "lesson_publish_days" | "lesson_ack_days" | "lesson_effectiveness_days" | "followup_warning_pct" | "lesson_ack_warning_pct";
const NUMS: { k: NumKey; range: string; dec?: boolean }[] = [
  { k: "notification_alert_lead_hours", range: "2–48" },
  { k: "lesson_publish_days", range: "3–30" },
  { k: "lesson_ack_days", range: "1–14" },
  { k: "lesson_effectiveness_days", range: "30–180" },
  { k: "followup_warning_pct", range: "50.0–100.0", dec: true },
  { k: "lesson_ack_warning_pct", range: "50.0–100.0", dec: true },
];

function SettingsForm({ project, s, editable }: { project: Project; s: S["FuSettingsRead"]; editable: boolean }) {
  const t = useTranslations("fu.settings");
  const te = useTranslations("enums");
  const refresh = useFuRefresh();
  const [from, setFrom] = useState(s.followup_rules_from ?? "");
  const [nums, setNums] = useState<Record<NumKey, string>>(Object.fromEntries(NUMS.map((n) => [n.k, String(s[n.k])])) as Record<NumKey, string>);
  const [ident, setIdent] = useState<S["FuClientIdentity"]>(s.client_pack_identity);
  const [clause, setClause] = useState(s.client_identity_clause ?? "");
  const [levels, setLevels] = useState<S["InvestigationLevel"][]>(s.lesson_required_levels);
  const [recipients, setRecipients] = useState<S["FuRecipient"][]>(s.client_recipients);
  const [directory, setDirectory] = useState<S["FuDirectoryEntry"][]>(s.body_directory);
  const [sigEn, setSigEn] = useState(s.signatory_role_en ?? "");
  const [sigAr, setSigAr] = useState(s.signatory_role_ar ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const body: S["FuSettingsUpdate"] = {};
      if ((s.followup_rules_from ?? "") !== from) body.followup_rules_from = from || null;
      for (const n of NUMS) if (String(s[n.k]) !== nums[n.k]) (body as Record<string, unknown>)[n.k] = n.dec ? nums[n.k] : Number(nums[n.k]);
      if (ident !== s.client_pack_identity || clause !== (s.client_identity_clause ?? "")) {
        body.client_pack_identity = ident;
        body.client_identity_clause = clause.trim() || null;
      }
      if (levels.join() !== s.lesson_required_levels.join()) body.lesson_required_levels = levels;
      if (JSON.stringify(recipients) !== JSON.stringify(s.client_recipients)) body.client_recipients = recipients;
      if (JSON.stringify(directory) !== JSON.stringify(s.body_directory)) body.body_directory = directory;
      if (sigEn !== (s.signatory_role_en ?? "")) body.signatory_role_en = sigEn.trim() || null;
      if (sigAr !== (s.signatory_role_ar ?? "")) body.signatory_role_ar = sigAr.trim() || null;
      await unwrap(api.PATCH("/api/v1/projects/{project_id}/followup-settings", { params: { path: { project_id: project.id } }, body }));
      await refresh();
      toast.success(t("saved"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4" data-testid="fu-settings">
      <p className="text-sm text-muted-foreground">{t("tightenOnly")}</p>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("groupRules")}</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <FormField id="fs-from" label={t("f.followup_rules_from")} hint={t("fromHint")}>
            <Input type="date" value={from} disabled={!editable} onChange={(e) => setFrom(e.target.value)} data-testid="fs-followup_rules_from" />
          </FormField>
          {NUMS.map((n) => (
            <FormField key={n.k} id={`fs-${n.k}`} label={t(`f.${n.k}`)} hint={t("allowed", { range: n.range })}>
              <Input
                type={n.dec ? "text" : "number"}
                inputMode={n.dec ? "decimal" : undefined}
                value={nums[n.k]}
                disabled={!editable}
                onChange={(e) => setNums({ ...nums, [n.k]: e.target.value })}
                data-testid={`fs-${n.k}`}
              />
            </FormField>
          ))}
          <fieldset className="flex flex-col gap-1">
            <legend className="mb-1 text-sm font-medium">{t("f.lesson_required_levels")}</legend>
            <Choices
              label={t("f.lesson_required_levels")}
              testId="fs-levels"
              value={levels.includes("L2") ? "L2" : "L3"}
              options={LEVELS.map((l) => ({ value: l, label: l === "L2" ? t("levelsL2") : t("levelsL3"), disabled: !editable }))}
              onChange={(v) => setLevels(v === "L2" ? ["L2", "L3"] : ["L3"])}
            />
          </fieldset>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("groupClient")}</CardTitle>
          <p className="text-xs text-muted-foreground">{t("identityHint")}</p>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Choices
            label={t("f.client_pack_identity")}
            testId="fs-identity"
            value={ident}
            options={(["none", "name_and_trade"] as const).map((x) => ({ value: x, label: te(`fuClientIdentity.${x}`), disabled: !editable }))}
            onChange={setIdent}
          />
          {ident === "name_and_trade" ? (
            <FormField id="fs-clause" label={t("clause")} required hint={t("clauseHint")}>
              <Textarea value={clause} disabled={!editable} onChange={(e) => setClause(e.target.value)} maxLength={500} data-testid="fs-clause" />
            </FormField>
          ) : null}
          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">{t("recipients")}</h3>
            {recipients.map((r, i) => (
              <div key={i} className="grid gap-2 rounded-md border p-2 sm:grid-cols-[1fr_1fr_auto_1fr_auto]" data-testid="fs-recipient">
                <Input aria-label={t("orgEn")} placeholder={t("orgEn")} value={r.organisation_en} disabled={!editable} onChange={(e) => setRecipients(recipients.map((x, j) => (j === i ? { ...x, organisation_en: e.target.value } : x)))} />
                <Input aria-label={t("orgAr")} placeholder={t("orgAr")} dir="rtl" value={r.organisation_ar} disabled={!editable} onChange={(e) => setRecipients(recipients.map((x, j) => (j === i ? { ...x, organisation_ar: e.target.value } : x)))} />
                <Select aria-label={t("role")} value={r.role} disabled={!editable} onChange={(e) => setRecipients(recipients.map((x, j) => (j === i ? { ...x, role: e.target.value as S["FuRecipientRole"] } : x)))}>
                  <option value="client">{te("fuRecipientRole.client")}</option>
                  <option value="pmc">{te("fuRecipientRole.pmc")}</option>
                </Select>
                <Input aria-label={t("email")} placeholder={t("email")} className="ltr" type="email" value={r.email ?? ""} disabled={!editable} onChange={(e) => setRecipients(recipients.map((x, j) => (j === i ? { ...x, email: e.target.value || null } : x)))} />
                {editable ? (
                  <Button variant="ghost" aria-label={t("remove")} onClick={() => setRecipients(recipients.filter((_, j) => j !== i))}>
                    <Trash2 aria-hidden />
                  </Button>
                ) : null}
              </div>
            ))}
            {editable ? (
              <Button variant="outline" size="sm" className="w-fit" onClick={() => setRecipients([...recipients, { organisation_en: "", organisation_ar: "", role: "client", email: null }])} data-testid="fs-add-recipient">
                <Plus aria-hidden />
                {t("addRecipient")}
              </Button>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("groupLetters")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField id="fs-sig-en" label={t("signatoryEn")} hint={t("signatoryHint")}>
              <Input dir="ltr" value={sigEn} disabled={!editable} onChange={(e) => setSigEn(e.target.value)} />
            </FormField>
            <FormField id="fs-sig-ar" label={t("signatoryAr")}>
              <Input dir="rtl" value={sigAr} disabled={!editable} onChange={(e) => setSigAr(e.target.value)} />
            </FormField>
          </div>
          <h3 className="text-sm font-semibold">{t("directory")}</h3>
          <Table>
            <THead>
              <TR>
                <TH>{t("body")}</TH>
                <TH>{t("office")}</TH>
                <TH>{t("portal")}</TH>
              </TR>
            </THead>
            <TBody>
              {directory.map((d, i) => (
                <TR key={`${d.body}-${i}`} data-testid="fs-directory">
                  <TD label={t("body")}>{te(`externalBody.${d.body}`)}</TD>
                  <TD label={t("office")}>
                    {editable ? (
                      <span className="flex flex-col gap-1">
                        <Input aria-label={t("orgEn")} dir="ltr" value={d.office_name_en} onChange={(e) => setDirectory(directory.map((x, j) => (j === i ? { ...x, office_name_en: e.target.value } : x)))} />
                        <Input aria-label={t("orgAr")} dir="rtl" value={d.office_name_ar} onChange={(e) => setDirectory(directory.map((x, j) => (j === i ? { ...x, office_name_ar: e.target.value } : x)))} />
                      </span>
                    ) : (
                      <OfficeName d={d} />
                    )}
                  </TD>
                  <TD label={t("portal")}>
                    {editable ? (
                      <Input aria-label={t("portal")} className="ltr" value={d.address_or_portal ?? ""} onChange={(e) => setDirectory(directory.map((x, j) => (j === i ? { ...x, address_or_portal: e.target.value || null } : x)))} />
                    ) : (
                      <bdi className="ltr">{d.address_or_portal ?? "—"}</bdi>
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>

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

function OfficeName({ d }: { d: S["FuDirectoryEntry"] }) {
  const ar = useLocale() === "ar";
  return <span>{ar ? d.office_name_ar : d.office_name_en}</span>;
}

/* ═════════════ rule profile (§3.1; statutory rows tighten only, NR-3) ═════════════ */

function Rules({ project, editable }: { project: Project; editable: boolean }) {
  const t = useTranslations("fu.rules");
  const te = useTranslations("enums");
  const show = useDisplay(project.id);
  const q = useFuRules(project.id);
  const [edit, setEdit] = useState<S["FuRuleRead"] | "new" | null>(null);
  const rows = q.data?.items ?? [];
  return (
    <Card data-testid="fu-rules">
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
        <div className="flex flex-col gap-1">
          <CardTitle className="text-base">{t("title")}</CardTitle>
          <p className="text-xs text-muted-foreground">{t("hint")}</p>
        </div>
        {editable ? (
          <Button size="sm" variant="outline" onClick={() => setEdit("new")} data-testid="rule-add">
            <Plus aria-hidden />
            {t("addClient")}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        {q.isLoading ? (
          <LoadingState />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>{t("rule")}</TH>
                <TH>{t("bodyStage")}</TH>
                <TH>{t("triggers")}</TH>
                <TH>{t("deadline")}</TH>
                <TH>{t("filer")}</TH>
                <TH>{t("active")}</TH>
                {editable ? <TH>{t("edit")}</TH> : null}
              </TR>
            </THead>
            <TBody>
              {rows.map((r) => (
                <TR key={r.id} data-testid="rule-row" data-rule={r.rule_code}>
                  <TD label={t("rule")}>
                    <span className="flex flex-col">
                      <Code className="font-medium">{r.rule_code}</Code>
                      <span className="text-xs text-muted-foreground">{te(`fuRuleSource.${r.source}`)}</span>
                    </span>
                  </TD>
                  <TD label={t("bodyStage")}>
                    {te(`externalBody.${r.body}`)} · {te(`fuStage.${r.stage}`)}
                    {r.form_code ? <span className="block text-xs text-muted-foreground">{te(`fuForm.${r.form_code}`)}</span> : null}
                  </TD>
                  <TD label={t("triggers")}>
                    <span className="text-sm">{r.triggers.map((x) => te(`fuTrigger.${x}`)).join(" · ")}</span>
                  </TD>
                  <TD label={t("deadline")}>
                    <span data-testid="rule-hours">{r.deadline_basis === "investigation_due" ? te("fuDeadlineBasis.investigation_due") : t("hours", { n: r.deadline_hours ?? 0, h: show(String(r.deadline_hours ?? "")) })}</span>
                  </TD>
                  <TD label={t("filer")}>{te(`fuFiler.${r.filer}`)}</TD>
                  <TD label={t("active")}>{r.active ? t("yes") : t("no")}</TD>
                  {editable ? (
                    <TD label={t("edit")}>
                      <Button size="sm" variant="outline" onClick={() => setEdit(r)} data-testid="rule-edit">
                        <Pencil aria-hidden />
                        {t("edit")}
                      </Button>
                    </TD>
                  ) : null}
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </CardContent>
      {edit ? <RuleDialog project={project} rule={edit === "new" ? null : edit} onClose={() => setEdit(null)} /> : null}
    </Card>
  );
}

function RuleDialog({ project, rule, onClose }: { project: Project; rule: S["FuRuleRead"] | null; onClose: () => void }) {
  const t = useTranslations("fu.rules");
  const te = useTranslations("enums");
  const refresh = useFuRefresh();
  const statutory = rule?.source === "statutory";
  const [code, setCode] = useState(rule?.rule_code ?? "CL-");
  const [stage, setStage] = useState<S["FuStage"]>(rule?.stage ?? "written");
  const [triggers, setTriggers] = useState<S["FuTrigger"][]>(rule?.triggers ?? []);
  const [basis, setBasis] = useState<S["FuDeadlineBasis"]>(rule?.deadline_basis ?? "trigger");
  const [hours, setHours] = useState(rule?.deadline_hours ? String(rule.deadline_hours) : "");
  const [form, setForm] = useState<S["FuForm"] | "">(rule?.form_code ?? "");
  const [active, setActive] = useState(rule?.active ?? true);
  return (
    <StepDialog
      title={rule ? t("editTitle", { rule: rule.rule_code }) : t("addTitle")}
      description={statutory ? t("statutoryHint") : t("clientHint")}
      confirmLabel={t("save")}
      testId="rule-save"
      wide
      disabled={!triggers.length || (basis === "trigger" && !hours)}
      onConfirm={async () => {
        if (rule) {
          await unwrap(
            api.PATCH("/api/v1/notification-rules/{rule_id}", {
              params: { path: { rule_id: rule.id } },
              body: { triggers, deadline_hours: basis === "trigger" ? Number(hours) : null, form_code: form || null, active },
            }),
          );
        } else {
          await unwrap(
            api.POST("/api/v1/projects/{project_id}/notification-rules", {
              params: { path: { project_id: project.id } },
              body: { rule_code: code.trim(), stage, triggers, deadline_basis: basis, deadline_hours: basis === "trigger" ? Number(hours) : null, form_code: form || null, active },
            }),
          );
        }
        await refresh();
        toast.success(t("saved"));
      }}
      onClose={onClose}
    >
      {!rule ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField id="rule-code" label={t("rule")} required>
            <Input className="ltr" value={code} onChange={(e) => setCode(e.target.value)} maxLength={16} data-testid="rule-code" />
          </FormField>
          <FormField id="rule-stage" label={t("stage")} required>
            <Select value={stage} onChange={(e) => setStage(e.target.value as S["FuStage"])}>
              {STAGES.map((s) => (
                <option key={s} value={s}>
                  {te(`fuStage.${s}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="rule-basis" label={t("basis")}>
            <Select value={basis} onChange={(e) => setBasis(e.target.value as S["FuDeadlineBasis"])}>
              <option value="trigger">{te("fuDeadlineBasis.trigger")}</option>
              <option value="investigation_due">{te("fuDeadlineBasis.investigation_due")}</option>
            </Select>
          </FormField>
        </div>
      ) : null}
      {basis === "trigger" ? (
        <FormField id="rule-hours" label={t("deadlineHours")} required hint={statutory ? t("lowerOnly") : t("range")}>
          <Input type="number" min={1} max={720} value={hours} onChange={(e) => setHours(e.target.value)} data-testid="rule-hours-input" />
        </FormField>
      ) : null}
      {!statutory ? (
        <FormField id="rule-form" label={t("form")}>
          <Select value={form} onChange={(e) => setForm(e.target.value as S["FuForm"])}>
            <option value="">—</option>
            {FORMS.map((f) => (
              <option key={f} value={f}>
                {te(`fuForm.${f}`)}
              </option>
            ))}
          </Select>
        </FormField>
      ) : null}
      <fieldset className="flex flex-col gap-1">
        <legend className="mb-1 text-sm font-medium">{t("triggers")}</legend>
        <div className="grid gap-1 sm:grid-cols-2">
          {TRIGGERS.map((x) => {
            const on = triggers.includes(x);
            return (
              <label key={x} className="flex min-h-12 items-center gap-2 rounded-md px-1 text-sm sm:min-h-touch">
                <input type="checkbox" className="size-5" checked={on} onChange={(e) => setTriggers(e.target.checked ? [...triggers, x] : triggers.filter((y) => y !== x))} data-testid={`rule-trigger-${x}`} />
                {te(`fuTrigger.${x}`)}
              </label>
            );
          })}
        </div>
      </fieldset>
      <label className="flex min-h-12 items-center gap-2 text-sm">
        <input type="checkbox" className="size-5" checked={active} onChange={(e) => setActive(e.target.checked)} data-testid="rule-active" />
        {t("active")}
      </label>
    </StepDialog>
  );
}
