"use client";
import { Plus } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { FormField } from "@/components/common/form-field";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { api, unwrap } from "@/lib/api/client";
import { useQCompetenceMatrix, useQCompetenceReqs } from "@/lib/api/quality/q2";
import { useFormatters } from "@/lib/use-formatters";
import { QGate, useQCaps, useQLabels, useRun, type Project } from "../q0/common";
import { Q2Badge, type S } from "./shared";

export function CompetencePage() {
  return <QGate>{(p) => <Competence project={p} />}</QGate>;
}

function Competence({ project }: { project: Project }) {
  const t = useTranslations("quality.cpt");
  const caps = useQCaps(project.id);
  const [tab, setTab] = useState<"matrix" | "requirements">("matrix");
  return (
    <div data-testid="q2-competence">
      <PageHeader title={t("title")} description={t("subtitle")} />
      <div className="mb-4 flex gap-1 border-b" role="tablist">
        {(["matrix", "requirements"] as const).map((k) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} data-testid={`q2-cpt-tab-${k}`}
            className={`min-h-touch rounded-t-md px-3 text-sm ${tab === k ? "border-b-2 border-primary font-semibold" : "text-muted-foreground"}`}>{t(`tab.${k}`)}</button>
        ))}
      </div>
      {tab === "matrix" ? <Matrix project={project} /> : <Requirements editable={caps.write("competence.manage") && (caps.manager || caps.me.projects.some((x) => x.roles.some((r) => r === "qa_qc_manager" || r === "quality_engineer")))} />}
    </div>
  );
}

function Matrix({ project }: { project: Project }) {
  const t = useTranslations("quality.cpt");
  const { l } = useQLabels();
  const ar = useLocale() === "ar";
  const { date } = useFormatters(project.id);
  const q = useQCompetenceMatrix(project.id);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const m = q.data;
  if (!m || !m.people.length) return <EmptyState message={t("emptyMatrix")} />;
  const cell = (uid: string, code: string) => m.cells.find((c) => c.user_id === uid && c.code === code);
  return (
    <div>
      <p className="mb-2 text-sm text-muted-foreground" data-testid="q2-cpt-summary">{t("summary", { met: m.met, total: m.applicable, on: date(m.on) })}</p>
      <div className="overflow-x-auto">
        <Table compact data-testid="q2-cpt-matrix">
          <THead><TR><TH>{t("person")}</TH>{m.requirements.map((r) => <TH key={r.code} className="ltr">{r.code}</TH>)}</TR></THead>
          <TBody>{m.people.map((p) => (
            <TR key={p.user_id} data-user={p.user_id}>
              <TD label={t("person")}>{ar ? p.full_name_ar || p.full_name_en : p.full_name_en}{!p.linked_worker ? <span className="block text-xs text-danger">{t("notLinked")}</span> : null}</TD>
              {m.requirements.map((r) => {
                const c = cell(p.user_id, r.code);
                return (
                  <TD key={r.code} label={r.code} data-code={r.code} data-state={c?.state ?? ""}>
                    {c ? c.state === "not_applicable" ? <span className="text-muted-foreground">—</span> : <Q2Badge value={c.state} label={`${l("competence_state", c.state)}${c.valid_until ? ` · ${date(c.valid_until)}` : ""}`} /> : null}
                  </TD>
                );
              })}
            </TR>
          ))}</TBody>
        </Table>
      </div>
    </div>
  );
}

function Requirements({ editable }: { editable: boolean }) {
  const t = useTranslations("quality.cpt");
  const { l } = useQLabels();
  const ar = useLocale() === "ar";
  const q = useQCompetenceReqs();
  const [adding, setAdding] = useState(false);
  const rows = q.data ?? [];
  return (
    <div>
      {editable && !adding ? <Button className="mb-3" onClick={() => setAdding(true)} data-testid="q2-cpt-new"><Plus aria-hidden />{t("new")}</Button> : null}
      {adding ? <ReqForm onDone={() => setAdding(false)} /> : null}
      {q.isLoading ? <LoadingState /> : rows.length ? (
        <Table compact data-testid="q2-cpt-reqs"><THead><TR><TH>{t("code")}</TH><TH>{t("titleField")}</TH><TH>{t("appliesTo")}</TH><TH>{t("evidence")}</TH><TH>{t("policy")}</TH><TH>{t("profile")}</TH></TR></THead>
          <TBody>{rows.map((r) => (
            <TR key={r.id} data-code={r.code}>
              <TD label={t("code")} className="ltr font-medium">{r.code}</TD>
              <TD label={t("titleField")}>{ar ? r.title_ar || r.title_en : r.title_en}</TD>
              <TD label={t("appliesTo")}>{r.applies_to.map((a) => l("competence_applies_to", a)).join(", ")}</TD>
              <TD label={t("evidence")} className="ltr text-xs">{[...r.any_of, ...r.all_of].map((e) => `${e.code}${e.min_level ? ` ≥ ${e.min_level}` : ""}`).join(" / ")}</TD>
              <TD label={t("policy")}>{l("competence_policy", r.policy)}</TD>
              <TD label={t("profile")}>{l("profile", r.profile)}</TD>
            </TR>
          ))}</TBody></Table>
      ) : <EmptyState message={t("empty")} />}
    </div>
  );
}

function ReqForm({ onDone }: { onDone: () => void }) {
  const t = useTranslations("quality.cpt");
  const tc = useTranslations("quality.common");
  const { options } = useQLabels();
  const { run, busy, error } = useRun();
  const [f, setF] = useState({ code: "", title_en: "", title_ar: "", kind: "training_course", ecode: "", level: "", policy: "inherit", profile: "both" });
  const [applies, setApplies] = useState<string[]>([]);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  async function save() {
    const body: S["QCompetenceReqCreate"] = {
      code: f.code.toUpperCase(), title_en: f.title_en, title_ar: f.title_ar, applies_to: applies as S["QCompetenceAppliesTo"][],
      any_of: [{ kind: f.kind as "training_course", code: f.ecode, min_level: f.level || null }], policy: f.policy as S["QCompetencePolicy"], profile: f.profile as S["QProfileScope"],
    };
    const out = await run(() => unwrap(api.POST("/api/v1/quality/competence/requirements", { body })));
    if (out) onDone();
  }
  return (
    <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-3" data-testid="q2-cpt-form">
      <MutationError error={error} />
      <FormField id="cpt-code" label={t("code")} required><Input value={f.code} onChange={set("code")} dir="ltr" data-testid="cpt-code" /></FormField>
      <FormField id="cpt-title" label={t("titleField")} required><Input value={f.title_en} onChange={set("title_en")} data-testid="cpt-title" /></FormField>
      <FormField id="cpt-title-ar" label={t("titleAr")}><Input value={f.title_ar} onChange={set("title_ar")} dir="rtl" /></FormField>
      <FormField id="cpt-kind" label={t("evidenceKind")}><Select value={f.kind} onChange={set("kind")}>{options("evidence_kind").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <FormField id="cpt-ecode" label={t("evidenceCode")} required><Input value={f.ecode} onChange={set("ecode")} dir="ltr" data-testid="cpt-ecode" /></FormField>
      <FormField id="cpt-level" label={t("minLevel")}><Input value={f.level} onChange={set("level")} dir="ltr" /></FormField>
      <FormField id="cpt-policy" label={t("policy")}><Select value={f.policy} onChange={set("policy")}>{options("competence_policy").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <FormField id="cpt-profile" label={t("profile")}><Select value={f.profile} onChange={set("profile")}>{options("profile").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <div className="sm:col-span-3"><CheckboxGroup id="cpt-applies" legend={t("appliesTo")} value={applies} onChange={setApplies} options={options("competence_applies_to")} /></div>
      <div className="flex gap-2 sm:col-span-3">
        <Button disabled={busy || !f.code || !f.title_en || !f.ecode} onClick={() => void save()} data-testid="cpt-save">{tc("save")}</Button>
        <Button variant="outline" onClick={onDone}>{tc("cancel")}</Button>
      </div>
    </CardContent></Card>
  );
}
