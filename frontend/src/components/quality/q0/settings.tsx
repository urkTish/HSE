"use client";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { CheckboxField, FormField } from "@/components/common/form-field";
import { PageHeader } from "@/components/common/page-header";
import { ProjectGate } from "@/components/common/project-gate";
import { UserSelect } from "@/components/common/pickers";
import { ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { api, unwrap } from "@/lib/api/client";
import { useQNumbering, useQPositions, useQRules, useQSettings, useQSettingsSchema } from "@/lib/api/quality/q0";
import { useFormatters } from "@/lib/use-formatters";
import { ProfileBadge, useQLabels, useRun, userText, type Project, type QSettings, type S } from "./common";

const TABS = ["profile", "matrix", "positions", "numbering", "parts"] as const;
type Tab = (typeof TABS)[number];

/** Quality settings `/quality/settings` (239): profile · RP matrix · positions · numbering · part settings. */
export function QualitySettingsPage() {
  return <ProjectGate>{(p) => <SettingsGate project={p} />}</ProjectGate>;
}

function SettingsGate({ project }: { project: Project }) {
  const q = useQSettings(project.id);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return null;
  return <Settings project={project} settings={q.data} />;
}

function Settings({ project, settings }: { project: Project; settings: QSettings }) {
  const t = useTranslations("quality.settings");
  const [tab, setTab] = useState<Tab>("profile");
  const configured = Boolean(settings.sector_profile);
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle", { project: project.code })} badge={<ProfileBadge profile={settings.sector_profile} />} />
      <div className="mb-4 flex gap-1 overflow-x-auto border-b" role="tablist">
        {TABS.filter((k) => configured || k === "profile").map((k) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} data-testid={`q-settings-tab-${k}`}
            className={`min-h-touch shrink-0 rounded-t-md px-3 text-sm ${tab === k ? "border-b-2 border-primary font-semibold" : "text-muted-foreground"}`}>
            {t(`tab.${k}`)}
          </button>
        ))}
      </div>
      {tab === "profile" ? <ProfileTab project={project} settings={settings} /> : null}
      {tab === "matrix" && configured ? <MatrixTab project={project} settings={settings} /> : null}
      {tab === "positions" && configured ? <PositionsTab project={project} settings={settings} /> : null}
      {tab === "numbering" && configured ? <NumberingTab project={project} settings={settings} /> : null}
      {tab === "parts" && configured ? <PartsTab project={project} settings={settings} /> : null}
    </div>
  );
}

/* ─── profile (Q-PRF) ─── */

function ProfileTab({ project, settings }: { project: Project; settings: QSettings }) {
  const t = useTranslations("quality.settings");
  const tc = useTranslations("quality.common");
  const { l } = useQLabels();
  const { date, dateTime } = useFormatters(project.id);
  const { run, busy, error } = useRun();
  const [profile, setProfile] = useState<string>(settings.sector_profile ?? settings.suggested_profile);
  const [start, setStart] = useState(settings.quality_start_date ?? "");
  const [reason, setReason] = useState("");
  const change = Boolean(settings.sector_profile) && profile !== settings.sector_profile;
  const save = () =>
    run(() =>
      unwrap(api.PUT("/api/v1/projects/{project_id}/quality/profile", {
        params: { path: { project_id: project.id } },
        body: { sector_profile: profile as S["QSectorProfile"], reason: change ? reason : null, quality_start_date: start || null },
      })),
    );
  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-4" data-testid="q-profile-form">
        <MutationError error={error} />
        {!settings.sector_profile ? <Alert tone="info">{t("profileIntro", { suggested: l("profile", settings.suggested_profile) })}</Alert> : null}
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-sm font-medium">{t("profile")}</legend>
          {(["construction", "logistics"] as const).map((p) => (
            <label key={p} className="flex min-h-touch cursor-pointer items-start gap-3 rounded-lg border p-3">
              <input type="radio" name="q-profile" value={p} checked={profile === p} onChange={() => setProfile(p)} disabled={!settings.can_edit} className="mt-1 size-5 accent-primary" data-testid={`q-profile-${p}`} />
              <span>
                <span className="font-medium">{l("profile", p)}</span>
                {p === settings.suggested_profile ? <Badge tone="info" className="ms-2">{t("suggested")}</Badge> : null}
                <span className="block text-xs text-muted-foreground">{t(`profileHint.${p}`)}</span>
              </span>
            </label>
          ))}
        </fieldset>
        <FormField id="q-start" label={t("startDate")} hint={t("startDateHint")}>
          <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} disabled={!settings.can_edit} className="max-w-xs" />
        </FormField>
        {change ? (
          <>
            <Alert tone="warning">{t("changeWarning")}</Alert>
            <FormField id="q-prof-reason" label={tc("reason")} hint={tc("minChars", { n: 20 })} required>
              <Textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} data-testid="q-profile-reason" />
            </FormField>
          </>
        ) : null}
        {settings.profile_changed_at ? <p className="text-xs text-muted-foreground">{t("changedAt", { at: dateTime(settings.profile_changed_at) })}</p> : null}
        {settings.quality_start_date ? <p className="text-xs text-muted-foreground">{t("startsOn", { on: date(settings.quality_start_date) })}</p> : null}
        {settings.can_edit ? (
          <Button className="self-start" disabled={busy || (change && reason.trim().length < 20) || (!change && settings.sector_profile === profile && (settings.quality_start_date ?? "") === start)} onClick={() => void save()} data-testid="q-profile-save">
            {settings.sector_profile ? tc("save") : t("configure")}
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

const inProfile = (scope: string | null | undefined, profile: string | null) => !scope || scope === "both" || scope === profile;

/* ─── responsible-person matrix (Q-RPM) ─── */

function MatrixTab({ project, settings }: { project: Project; settings: QSettings }) {
  const t = useTranslations("quality.settings");
  const tc = useTranslations("quality.common");
  const { l, recordType } = useQLabels();
  const ar = useLocale() === "ar";
  const rules = useQRules(project.id);
  const positions = useQPositions(project.id);
  const { run, busy, error } = useRun();
  const [part, setPart] = useState("");
  const [edit, setEdit] = useState<S["QRpRuleRead"] | null>(null);
  const rows = (rules.data ?? []).filter((r) => !r.record_id && inProfile(r.profile, settings.sector_profile) && (!part || r.part === part));
  const parts = [...new Set((rules.data ?? []).map((r) => r.part).filter(Boolean))].sort() as string[];
  const overrides = (rules.data ?? []).filter((r) => r.record_id);
  if (rules.isLoading) return <LoadingState />;
  if (rules.isError) return <ErrorState error={rules.error} onRetry={() => rules.refetch()} />;
  const assigneeText = (r: S["QRpRuleRead"]) => {
    if (r.assignee_kind === "role") return l("role", r.assignee);
    if (r.assignee_kind === "position") {
      const p = (positions.data ?? []).find((x) => x.code === r.assignee);
      return p ? (ar ? p.name_ar : p.name_en) : r.assignee;
    }
    return t("namedUser");
  };
  return (
    <div className="flex flex-col gap-4">
      <MutationError error={error} />
      <p className="text-sm text-muted-foreground">{t("matrixHint")}</p>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant={part ? "outline" : "default"} onClick={() => setPart("")}>{tc("all")}</Button>
        {parts.map((p) => <Button key={p} size="sm" variant={part === p ? "default" : "outline"} onClick={() => setPart(p)}>{p}</Button>)}
      </div>
      <Table compact data-testid="q-rp-matrix">
        <THead><TR><TH>{t("recordType")}</TH><TH>{t("step")}</TH><TH>{t("qualifier")}</TH><TH>{t("assignee")}</TH><TH>{t("flags")}</TH>{settings.can_edit ? <TH /> : null}</TR></THead>
        <TBody>{rows.map((r) => (
          <TR key={r.id} data-testid="q-rp-row" data-record-type={r.record_type} data-step={r.step} data-qualifier={r.qualifier ?? ""}>
            <TD label={t("recordType")}>{recordType(r.record_type)}</TD>
            <TD label={t("step")}>{ar ? r.step_ar : r.step_en}</TD>
            <TD label={t("qualifier")} className="ltr text-xs">{r.qualifier ?? "—"}</TD>
            <TD label={t("assignee")}>
              <span className="text-xs text-muted-foreground">{l("assignee_kind", r.assignee_kind)}: </span>
              <span data-testid="q-rp-assignee">{assigneeText(r)}</span>
              {!r.active ? <Badge tone="neutral" className="ms-1">{t("inactive")}</Badge> : null}
            </TD>
            <TD label={t("flags")} className="text-xs">
              {[r.self_approval_allowed ? t("selfOk") : null, r.own_tree_allowed ? t("ownTreeOk") : null, r.paper_allowed ? t("paperOk") : null].filter(Boolean).join(" · ") || "—"}
            </TD>
            {settings.can_edit ? <TD><Button size="sm" variant="outline" onClick={() => setEdit(r)} data-testid="q-rp-edit">{t("edit")}</Button></TD> : null}
          </TR>
        ))}</TBody>
      </Table>
      {edit ? <RuleEditor key={edit.id} project={project} rule={edit} busy={busy} onClose={() => setEdit(null)}
        onSave={(body) => run(() => unwrap(api.PATCH("/api/v1/quality/rp-rules/{rule_id}", { params: { path: { rule_id: edit.id } }, body }))).then((x) => x && setEdit(null))} /> : null}
      {overrides.length ? (
        <Card>
          <CardHeader><CardTitle className="text-base">{t("overrides")}</CardTitle></CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-1 text-sm" data-testid="q-rp-overrides">
              {overrides.map((r) => <li key={r.id}>{recordType(r.record_type)} · {ar ? r.step_ar : r.step_en} → {assigneeText(r)} — <span className="text-muted-foreground">{r.reason}</span></li>)}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function RuleEditor({ project, rule, busy, onClose, onSave }: { project: Project; rule: S["QRpRuleRead"]; busy: boolean; onClose: () => void; onSave: (b: S["QRpRuleUpdate"]) => Promise<unknown> }) {
  const t = useTranslations("quality.settings");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const ar = useLocale() === "ar";
  const positions = useQPositions(project.id);
  const [kind, setKind] = useState<string>(rule.assignee_kind);
  const [assignee, setAssignee] = useState(rule.assignee);
  const [self, setSelf] = useState(rule.self_approval_allowed);
  const [tree, setTree] = useState(rule.own_tree_allowed);
  const [paper, setPaper] = useState(rule.paper_allowed);
  const [active, setActive] = useState(rule.active);
  const roleOptions = useMemo(() => options("role"), [options]);
  return (
    <Card data-testid="q-rp-editor">
      <CardHeader><CardTitle className="text-base">{ar ? rule.step_ar : rule.step_en}{rule.qualifier ? ` · ${rule.qualifier}` : ""}</CardTitle></CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-3">
        <FormField id="rp-kind" label={t("assigneeKind")}>
          <Select value={kind} onChange={(e) => { setKind(e.target.value); setAssignee(""); }} data-testid="rp-kind">
            {options("assignee_kind").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        </FormField>
        <FormField id="rp-assignee" label={t("assignee")} className="sm:col-span-2">
          {kind === "role" ? (
            <Select value={assignee} onChange={(e) => setAssignee(e.target.value)} data-testid="rp-assignee">
              <option value="">{tc("select")}</option>
              {roleOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          ) : kind === "position" ? (
            <Select value={assignee} onChange={(e) => setAssignee(e.target.value)} data-testid="rp-assignee">
              <option value="">{tc("select")}</option>
              {(positions.data ?? []).filter((p) => p.active).map((p) => <option key={p.code} value={p.code}>{ar ? p.name_ar : p.name_en}</option>)}
            </Select>
          ) : (
            <UserSelect projectId={project.id} value={assignee} onChange={(e) => setAssignee(e.target.value)} data-testid="rp-assignee" />
          )}
        </FormField>
        <CheckboxField id="rp-self" label={t("selfOk")}><Checkbox checked={self} onChange={(e) => setSelf(e.target.checked)} /></CheckboxField>
        <CheckboxField id="rp-tree" label={t("ownTreeOk")}><Checkbox checked={tree} onChange={(e) => setTree(e.target.checked)} /></CheckboxField>
        <CheckboxField id="rp-paper" label={t("paperOk")}><Checkbox checked={paper} onChange={(e) => setPaper(e.target.checked)} /></CheckboxField>
        <CheckboxField id="rp-active" label={t("active")}><Checkbox checked={active} onChange={(e) => setActive(e.target.checked)} /></CheckboxField>
        <p className="text-xs text-muted-foreground sm:col-span-3">{t("capabilityHint", { kind: l("assignee_kind", kind) })}</p>
        <div className="flex gap-2 sm:col-span-3">
          <Button disabled={busy || !assignee} onClick={() => void onSave({ assignee_kind: kind as S["QAssigneeKind"], assignee, self_approval_allowed: self, own_tree_allowed: tree, paper_allowed: paper, active })} data-testid="rp-save">{tc("save")}</Button>
          <Button variant="outline" onClick={onClose}>{tc("cancel")}</Button>
        </div>
      </CardContent>
    </Card>
  );
}

/* ─── positions (Q-RPM-03) ─── */

function PositionsTab({ project, settings }: { project: Project; settings: QSettings }) {
  const t = useTranslations("quality.settings");
  const { l } = useQLabels();
  const ar = useLocale() === "ar";
  const { date } = useFormatters(project.id);
  const q = useQPositions(project.id);
  const { run, busy, error } = useRun();
  const [holder, setHolder] = useState<Record<string, string>>({});
  const [f, setF] = useState({ code: "", name_en: "", name_ar: "" });
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const rows = (q.data ?? []).filter((p) => inProfile(p.profile, settings.sector_profile));
  return (
    <div className="flex flex-col gap-4">
      <MutationError error={error} />
      {rows.map((p) => (
        <Card key={p.id} data-testid="q-position" data-code={p.code}>
          <CardContent className="flex flex-col gap-2 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{ar ? p.name_ar : p.name_en}</span>
              <span className="ltr text-xs text-muted-foreground">{p.code}</span>
              {p.profile !== "both" ? <Badge tone="info">{l("profile", p.profile)}</Badge> : null}
              {!p.active ? <Badge tone="neutral">{t("inactive")}</Badge> : null}
            </div>
            {p.holders.length ? (
              <ul className="flex flex-col gap-1 text-sm">
                {p.holders.map((h) => (
                  <li key={h.id} className="flex flex-wrap items-center gap-2" data-testid="q-position-holder">
                    <span>{userText(h.user, ar)}</span>
                    <span className="text-xs text-muted-foreground">{date(h.valid_from)} → {h.valid_to ? date(h.valid_to) : t("open")}</span>
                    {settings.can_edit && !h.valid_to ? (
                      <Button size="sm" variant="outline" disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/position-holders/{holder_id}/end", { params: { path: { holder_id: h.id } }, body: {} })))}>{t("endHolder")}</Button>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-warning">{t("noHolder")}</p>}
            {settings.can_edit ? (
              <div className="flex flex-wrap items-end gap-2">
                <UserSelect projectId={project.id} value={holder[p.id] ?? ""} onChange={(e) => setHolder((x) => ({ ...x, [p.id]: e.target.value }))} className="max-w-xs" aria-label={t("addHolder")} data-testid="q-holder-user" />
                <Button size="sm" disabled={busy || !holder[p.id]} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/positions/{position_id}/holders", { params: { path: { position_id: p.id } }, body: { user_id: holder[p.id] ?? "" } })))} data-testid="q-holder-add">{t("addHolder")}</Button>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ))}
      {settings.can_edit ? (
        <Card><CardContent className="grid gap-3 p-4 sm:grid-cols-4" data-testid="q-position-form">
          <FormField id="pos-code" label={t("code")} required><Input value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} dir="ltr" /></FormField>
          <FormField id="pos-en" label={t("nameEn")} required><Input value={f.name_en} onChange={(e) => setF({ ...f, name_en: e.target.value })} dir="ltr" /></FormField>
          <FormField id="pos-ar" label={t("nameAr")} required><Input value={f.name_ar} onChange={(e) => setF({ ...f, name_ar: e.target.value })} dir="rtl" /></FormField>
          <Button className="self-end" disabled={busy || !f.code || !f.name_en || !f.name_ar}
            onClick={() => void run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/positions", { params: { path: { project_id: project.id } }, body: { ...f, profile: "both" } }))).then((x) => x && setF({ code: "", name_en: "", name_ar: "" }))}>{t("addPosition")}</Button>
        </CardContent></Card>
      ) : null}
    </div>
  );
}

/* ─── numbering (Q-NUM) ─── */

const TOKENS = ["{PFX}", "{PROJECT}", "{YYYY}", "{YY}", "{DISC}", "{SITE}", "{SEQ3}", "{SEQ4}", "{SEQ5}"];

function NumberingTab({ project, settings }: { project: Project; settings: QSettings }) {
  const t = useTranslations("quality.settings");
  const { recordType, l, options } = useQLabels();
  const q = useQNumbering(project.id);
  const { run, busy, error } = useRun();
  const [edit, setEdit] = useState<Record<string, { format: string; reset: string }>>({});
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const rows = (q.data ?? []).filter((r) => inProfile(r.profile, settings.sector_profile));
  return (
    <div className="flex flex-col gap-3">
      <MutationError error={error} />
      <p className="text-sm text-muted-foreground">{t("numberingHint")} <span className="ltr">{TOKENS.join(" ")}</span></p>
      <Table compact data-testid="q-numbering">
        <THead><TR><TH>{t("recordType")}</TH><TH>{t("format")}</TH><TH>{t("reset")}</TH><TH>{t("preview")}</TH>{settings.can_edit ? <TH /> : null}</TR></THead>
        <TBody>{rows.map((r) => {
          const e = edit[r.record_type];
          return (
            <TR key={r.record_type} data-testid="q-numbering-row" data-record-type={r.record_type}>
              <TD label={t("recordType")}>{recordType(r.record_type)} <span className="text-xs text-muted-foreground">{r.part}</span></TD>
              <TD label={t("format")}>
                {e ? <Input value={e.format} onChange={(x) => setEdit({ ...edit, [r.record_type]: { ...e, format: x.target.value } })} dir="ltr" className="min-w-48" data-testid="q-numbering-format" /> : <span className="ltr text-xs">{r.format}</span>}
              </TD>
              <TD label={t("reset")}>
                {e ? (
                  <Select value={e.reset} onChange={(x) => setEdit({ ...edit, [r.record_type]: { ...e, reset: x.target.value } })}>
                    {options("number_reset").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </Select>
                ) : l("number_reset", r.reset)}
              </TD>
              <TD label={t("preview")} className="ltr font-medium" data-testid="q-numbering-preview">{r.preview}</TD>
              {settings.can_edit ? (
                <TD>
                  {e ? (
                    <Button size="sm" disabled={busy} data-testid="q-numbering-save"
                      onClick={() => void run(() => unwrap(api.PUT("/api/v1/projects/{project_id}/quality/numbering/{record_type}", { params: { path: { project_id: project.id, record_type: r.record_type } }, body: { format: e.format, reset: e.reset as S["QNumberReset"] } }))).then((x) => { if (x) { const n = { ...edit }; delete n[r.record_type]; setEdit(n); } })}>{t("saveFormat")}</Button>
                  ) : <Button size="sm" variant="outline" onClick={() => setEdit({ ...edit, [r.record_type]: { format: r.format, reset: r.reset } })} data-testid="q-numbering-edit">{t("edit")}</Button>}
                </TD>
              ) : null}
            </TR>
          );
        })}</TBody>
      </Table>
    </div>
  );
}

/* ─── part settings from the schema (Q-SET) ─── */

function PartsTab({ project, settings }: { project: Project; settings: QSettings }) {
  const t = useTranslations("quality.settings");
  const tc = useTranslations("quality.common");
  const ar = useLocale() === "ar";
  const schema = useQSettingsSchema();
  const { run, busy, error } = useRun();
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [part, setPart] = useState("Q0");
  if (schema.isLoading) return <LoadingState />;
  if (schema.isError) return <ErrorState error={schema.error} onRetry={() => schema.refetch()} />;
  const defs = (schema.data ?? []).filter((d) => inProfile(d.profile, settings.sector_profile));
  const parts = [...new Set(defs.map((d) => d.part))].sort();
  const val = (k: string) => (k in draft ? draft[k] : settings.values[k]);
  const set = (k: string, v: unknown) => setDraft((x) => ({ ...x, [k]: v }));
  const save = () =>
    run(() => unwrap(api.PATCH("/api/v1/projects/{project_id}/quality/settings", { params: { path: { project_id: project.id } }, body: { values: draft, clear_quality_start_date: false } }))).then((x) => x && setDraft({}));
  return (
    <div className="flex flex-col gap-4">
      <MutationError error={error} />
      <div className="flex flex-wrap gap-2">
        {parts.map((p) => <Button key={p} size="sm" variant={part === p ? "default" : "outline"} onClick={() => setPart(p)} data-testid={`q-settings-part-${p}`}>{p}</Button>)}
      </div>
      <Card><CardContent className="grid gap-4 p-4 sm:grid-cols-2" data-testid="q-part-settings">
        {defs.filter((d) => d.part === part).map((d) => (
          <SettingInput key={d.key} def={d} value={val(d.key)} onChange={(v) => set(d.key, v)} disabled={!settings.can_edit} changed={settings.changed_keys.includes(d.key)} label={ar ? d.label_ar : d.label_en} />
        ))}
      </CardContent></Card>
      {settings.can_edit ? (
        <div className="flex gap-2">
          <Button disabled={busy || !Object.keys(draft).length} onClick={() => void save()} data-testid="q-settings-save">{tc("save")}</Button>
          {Object.keys(draft).length ? <Button variant="outline" onClick={() => setDraft({})}>{tc("cancel")}</Button> : null}
          <span className="self-center text-xs text-muted-foreground">{t("pending", { n: Object.keys(draft).length })}</span>
        </div>
      ) : null}
    </div>
  );
}

function SettingInput({ def, value, onChange, disabled, changed, label }: { def: S["QSettingDefRead"]; value: unknown; onChange: (v: unknown) => void; disabled: boolean; changed: boolean; label: string }) {
  const t = useTranslations("quality.settings");
  const id = `qs-${def.key}`;
  const hint = [def.min != null ? `≥ ${def.min}` : null, def.max != null ? `≤ ${def.max}` : null, changed ? t("changed") : null].filter(Boolean).join(" · ") || undefined;
  if (def.kind === "bool") {
    return <CheckboxField id={id} label={label}><Checkbox checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} disabled={disabled} data-testid={id} /></CheckboxField>;
  }
  if (def.kind === "enum") {
    return (
      <FormField id={id} label={label} hint={hint}>
        <Select value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} disabled={disabled} data-testid={id}>
          {def.options.map((o) => <option key={o} value={o}>{o}</option>)}
        </Select>
      </FormField>
    );
  }
  if (def.kind === "int" || def.kind === "decimal" || def.kind === "decimal_or_null") {
    return (
      <FormField id={id} label={label} hint={hint}>
        <Input value={value == null ? "" : String(value)} dir="ltr" inputMode="decimal" disabled={disabled} data-testid={id}
          onChange={(e) => onChange(e.target.value === "" ? (def.kind === "decimal_or_null" ? null : "") : def.kind === "int" ? Number(e.target.value) : e.target.value)} />
      </FormField>
    );
  }
  if (def.kind === "set") {
    const cur = Array.isArray(value) ? (value as string[]) : [];
    return (
      <fieldset className="flex flex-col gap-1">
        <legend className="text-sm font-medium">{label}</legend>
        <div className="flex flex-wrap gap-3">
          {def.options.map((o) => (
            <label key={o} className="flex items-center gap-2 text-sm">
              <Checkbox checked={cur.includes(o)} disabled={disabled} onChange={(e) => onChange(e.target.checked ? [...cur, o] : cur.filter((x) => x !== o))} />
              <span className="ltr">{o}</span>
            </label>
          ))}
        </div>
      </fieldset>
    );
  }
  return <JsonInput id={id} label={label} hint={hint} value={value} onChange={onChange} disabled={disabled} />;
}

function JsonInput({ id, label, hint, value, onChange, disabled }: { id: string; label: string; hint?: string; value: unknown; onChange: (v: unknown) => void; disabled: boolean }) {
  const t = useTranslations("quality.settings");
  const [text, setText] = useState(JSON.stringify(value ?? null, null, 1));
  const [bad, setBad] = useState(false);
  return (
    <FormField id={id} label={label} hint={hint} error={bad ? t("badJson") : undefined} className="sm:col-span-2">
      <Textarea value={text} rows={4} dir="ltr" className="font-mono text-xs" disabled={disabled} data-testid={id}
        onChange={(e) => {
          setText(e.target.value);
          try {
            onChange(JSON.parse(e.target.value));
            setBad(false);
          } catch {
            setBad(true);
          }
        }} />
    </FormField>
  );
}
