"use client";
import { Plus, RefreshCw } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/common/form-field";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Link } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { useQ4Audit, useQ4Audits, useQ4Mrv, useQ4Mrvs, useQ4Processes, useQ4Programme } from "@/lib/api/quality/q4";
import { useQCaps, useRun } from "@/components/quality/q0/common";
import { FileButton, Ltr, MONTHS, Q4Gate, Q4Status, useForm, useName, type Project , useT } from "./common";

// ---- audits ----------------------------------------------------------------------------------------

export function AuditsPage() {
  return <Q4Gate>{(p) => <Audits project={p} />}</Q4Gate>;
}

function Audits({ project }: { project: Project }) {
  const t = useT("quality.q4.aud");
  const tc = useTranslations("quality.common");
  const name = useName();
  const caps = useQCaps(project.id);
  const r = useQ4Audits(project.id);
  const procs = useQ4Processes(project.id);
  const { run, busy, error } = useRun();
  const [adding, setAdding] = useState(false);
  const [f, set] = useForm({ audit_type: "qms_internal", template_code: "Q9K", process: "", start: "", end: "" });
  const me = caps.me;
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} actions={caps.write("quality_audit.conduct") && !adding ? <Button onClick={() => setAdding(true)} data-testid="q4-aud-new"><Plus aria-hidden />{t("new")}</Button> : null} />
      {adding ? (
        <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-3" data-testid="q4-aud-form">
          <MutationError error={error} />
          <FormField id="a-type" label={t("type")}><Select id="a-type" value={f.audit_type} onChange={set("audit_type")}>{["qms_internal", "process_quality", "supplier_quality", "subcontractor_quality"].map((x) => <option key={x} value={x}>{t(`types.${x}`)}</option>)}</Select></FormField>
          <FormField id="a-tpl" label={t("template")}><Select id="a-tpl" value={f.template_code} onChange={set("template_code")}>{["Q9K", "QSUP", "QGDP"].map((x) => <option key={x} value={x}>{x}</option>)}</Select></FormField>
          <FormField id="a-proc" label={t("process")}><Select id="a-proc" value={f.process} onChange={set("process")}><option value="">—</option>{(procs.data ?? []).map((x) => <option key={x.id} value={x.id}>{x.code} — {name(x.name_en, x.name_ar)}</option>)}</Select></FormField>
          <FormField id="a-start" label={t("start")} required><Input id="a-start" type="date" value={f.start} onChange={set("start")} dir="ltr" data-testid="q4-aud-start" /></FormField>
          <FormField id="a-end" label={t("end")} required><Input id="a-end" type="date" value={f.end} onChange={set("end")} dir="ltr" data-testid="q4-aud-end" /></FormField>
          <div className="flex gap-2 sm:col-span-3">
            <Button disabled={busy || !f.start || !f.end} data-testid="q4-aud-save" onClick={() => void run(async () => { const o = await unwrap(api.POST("/api/v1/projects/{project_id}/quality/audits", { params: { path: { project_id: project.id } }, body: { audit_type: f.audit_type as "qms_internal", template_code: f.template_code, lead_auditor_id: me.id, process_ids: f.process ? [f.process] : [], planned_start: f.start, planned_end: f.end } })); setAdding(false); return o; })}>{tc("save")}</Button>
            <Button variant="outline" onClick={() => setAdding(false)}>{tc("cancel")}</Button>
          </div>
        </CardContent></Card>
      ) : null}
      {r.isLoading ? <LoadingState /> : (r.data?.items ?? []).length ? (
        <Table data-testid="q4-audits">
          <THead><TR><TH>{t("no")}</TH><TH>{t("type")}</TH><TH>{t("scope")}</TH><TH>{t("fieldwork")}</TH><TH>{t("status")}</TH><TH>{t("ncrs")}</TH></TR></THead>
          <TBody>{(r.data?.items ?? []).map((a) => (
            <TR key={a.id} data-testid="q4-audit-row">
              <TD label={t("no")}><Link href={`/quality/audits/${a.id}`} className="ltr font-medium">{a.audit_no}</Link></TD>
              <TD label={t("type")}>{t(`types.${a.audit_type}`)}</TD>
              <TD label={t("scope")}>{[...a.processes.map((x) => String(x.code)), a.auditee_supplier ? String(a.auditee_supplier.code) : ""].filter(Boolean).join(", ") || "—"}</TD>
              <TD label={t("fieldwork")}><Ltr>{a.fieldwork_start ?? a.planned_start} – {a.fieldwork_end ?? a.planned_end}</Ltr></TD>
              <TD label={t("status")}><Q4Status value={a.status} /></TD>
              <TD label={t("ncrs")}><Ltr>{a.ncr_ids.length}</Ltr></TD>
            </TR>
          ))}</TBody>
        </Table>
      ) : <EmptyState />}
    </div>
  );
}

type Item = { item_code: string; text_en: string; text_ar: string; reference?: string | null; critical?: boolean; section_code: string };

/** Phone: the 6d-style conduct runner (one card per item, 0–3 rating); desk: the same list wide. */
export function AuditDetailPage({ id }: { id: string }) {
  return <Q4Gate>{(p) => <AuditDetail project={p} id={id} />}</Q4Gate>;
}

function AuditDetail({ project, id }: { project: Project; id: string }) {
  const t = useT("quality.q4.aud");
  const name = useName();
  const caps = useQCaps(project.id);
  const r = useQ4Audit(id);
  const [ans, setAns] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [summary, setSummary] = useState<string | null>(null);
  const [fw, setFw] = useState({ start: "", end: "" });
  const { run, busy, error } = useRun();
  if (r.isLoading) return <LoadingState />;
  if (r.isError || !r.data) return <ErrorState error={r.error} onRetry={() => r.refetch()} />;
  const a = r.data;
  const items = { data: (a.template_items ?? []) as unknown as Item[] };
  const lead = a.lead_auditor as { id?: string } | null;
  const isTeam = caps.me.id === lead?.id || caps.manager;
  const answering = isTeam && (a.status === "planned" || a.status === "in_progress");
  const saved = ((a.response as { answers?: { item_code: string; answer?: string }[] } | null)?.answers ?? []).reduce<Record<string, string>>((m, x) => ({ ...m, [x.item_code]: String(x.answer ?? "") }), {});
  const val = (c: string) => ans[c] ?? saved[c] ?? "";
  const findings = (a.findings ?? []) as { finding_no: string; severity: string; description_en?: string; description_ar?: string }[];
  return (
    <div>
      <PageHeader title={<Ltr>{a.audit_no}</Ltr>} description={t(`types.${a.audit_type}`)} actions={<Q4Status value={a.status} />} />
      <MutationError error={error} />
      <div className="mb-3 grid gap-2 text-sm sm:grid-cols-3">
        <p>{t("lead")}: {lead ? name((lead as { full_name_en?: string }).full_name_en, (lead as { full_name_ar?: string }).full_name_ar) : "—"}</p>
        <p>{t("scope")}: <Ltr>{a.processes.map((x) => String(x.code)).join(", ") || (a.auditee_supplier ? String(a.auditee_supplier.code) : "—")}</Ltr></p>
        <p>{t("reportDue")}: <Ltr>{a.report_due_by ?? "—"}</Ltr></p>
      </div>
      {answering ? (
        <Card className="mb-4"><CardContent className="space-y-2 p-3" data-testid="q4-aud-runner">
          {(items.data ?? []).map((it) => (
            <div key={it.item_code} className="grid gap-2 rounded-md border p-2 sm:grid-cols-[1fr_auto]" data-testid="q4-aud-item">
              <div><p className="text-sm font-medium">{name(it.text_en, it.text_ar)}</p><p className="ltr text-xs text-muted-foreground">{it.reference}{it.critical ? " · critical" : ""}</p>
                {val(it.item_code) && val(it.item_code) !== "3" ? <Input className="mt-1" placeholder={t("note")} value={notes[it.item_code] ?? ""} onChange={(e) => setNotes((n) => ({ ...n, [it.item_code]: e.target.value }))} /> : null}</div>
              <div className="flex gap-1" role="radiogroup" aria-label={it.item_code}>{["0", "1", "2", "3"].map((v) => <Button key={v} size="sm" variant={val(it.item_code) === v ? "default" : "outline"} onClick={() => setAns((x) => ({ ...x, [it.item_code]: v }))} aria-pressed={val(it.item_code) === v}><Ltr>{v}</Ltr></Button>)}</div>
            </div>
          ))}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => setAns(Object.fromEntries((items.data ?? []).map((it) => [it.item_code, val(it.item_code) || "3"])))}>{t("fillCompliant")}</Button>
            <Button size="sm" disabled={busy} data-testid="q4-aud-save-answers" onClick={() => void run(() => unwrap(api.PUT("/api/v1/quality/audits/{audit_id}/answers", { params: { path: { audit_id: id } }, body: { answers: (items.data ?? []).filter((it) => val(it.item_code)).map((it) => ({ item_code: it.item_code, answer: val(it.item_code), note: val(it.item_code) !== "3" ? notes[it.item_code] || t("defaultNote") : null })) } as never })))}>{t("saveAnswers")}</Button>
          </div>
        </CardContent></Card>
      ) : null}
      {isTeam && (a.status === "in_progress" || a.status === "planned") ? (
        <Card className="mb-4"><CardContent className="grid gap-2 p-3 sm:grid-cols-4">
          <FormField id="fw-s" label={t("start")}><Input id="fw-s" type="date" value={fw.start} onChange={(e) => setFw((x) => ({ ...x, start: e.target.value }))} dir="ltr" /></FormField>
          <FormField id="fw-e" label={t("end")}><Input id="fw-e" type="date" value={fw.end} onChange={(e) => setFw((x) => ({ ...x, end: e.target.value }))} dir="ltr" /></FormField>
          <FormField id="fw-sum" label={t("summary")}><Textarea id="fw-sum" value={summary ?? a.summary_en ?? ""} onChange={(e) => setSummary(e.target.value)} rows={2} /></FormField>
          <div className="flex items-end gap-2">
            <Button size="sm" variant="outline" disabled={busy || !fw.start || !fw.end} data-testid="q4-aud-fieldwork" onClick={() => void run(() => unwrap(api.PATCH("/api/v1/quality/audits/{audit_id}", { params: { path: { audit_id: id } }, body: { fieldwork_start: fw.start, fieldwork_end: fw.end, opening_meeting_at: `${fw.start}T05:00:00Z`, closing_meeting_at: `${fw.end}T12:00:00Z`, summary_en: summary ?? a.summary_en ?? null } })))}>{t("saveFieldwork")}</Button>
            <Button size="sm" disabled={busy} data-testid="q4-aud-complete" onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/audits/{audit_id}/complete-fieldwork", { params: { path: { audit_id: id } } })))}>{t("complete")}</Button>
          </div>
        </CardContent></Card>
      ) : null}
      {a.can_issue ? <Button className="mb-3" disabled={busy} data-testid="q4-aud-issue" onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/audits/{audit_id}/issue", { params: { path: { audit_id: id } }, body: { ca_for_observations: false } })), t("issued"))}>{t("issue")}</Button> : null}
      {a.status === "fieldwork_complete" && !a.can_issue ? <Alert tone="info" className="mb-3">{t("waitIssue")}</Alert> : null}
      <div className="mb-3 flex gap-2"><FileButton id={a.report_en_id} label={t("reportEn")} testId="q4-aud-report-en" /><FileButton id={a.report_ar_id} label={t("reportAr")} /></div>
      {findings.length ? (
        <Table><THead><TR><TH>{t("finding")}</TH><TH>{t("grade")}</TH><TH>{t("description")}</TH></TR></THead>
          <TBody>{findings.map((x) => <TR key={x.finding_no}><TD label={t("finding")}><Ltr>{x.finding_no}</Ltr></TD><TD label={t("grade")}>{t(`grades.${x.severity}`)}</TD><TD label={t("description")}>{name(x.description_en, x.description_ar)}</TD></TR>)}</TBody></Table>
      ) : null}
      {a.ncr_ids.length ? <p className="mt-3 text-sm">{t("ncrsRaised")}: {a.ncr_ids.map((n) => <Link key={n} href={`/quality/ncrs/${n}`} className="me-2 underline">NCR</Link>)}</p> : null}
    </div>
  );
}

// ---- programme --------------------------------------------------------------------------------------

export function ProgrammePage() {
  return <Q4Gate>{(p) => <Programme project={p} />}</Q4Gate>;
}

function Programme({ project }: { project: Project }) {
  const t = useT("quality.q4.prog");
  const ta = useT("quality.q4.aud");
  const caps = useQCaps(project.id);
  const [year, setYear] = useState(new Date().getFullYear());
  const r = useQ4Programme(project.id, year);
  const { run, busy, error } = useRun();
  const rows = r.data ?? [];
  const subjects = Array.from(new Set(rows.map((x) => x.process_code ?? (x.supplier ? String(x.supplier.code) : x.engagement_code ?? x.clause_set ?? "—"))));
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} actions={<div className="flex gap-2"><Input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} className="w-24" dir="ltr" aria-label={t("year")} data-testid="q4-prog-year" />{caps.write("quality_audit.conduct") ? <Button variant="outline" disabled={busy} data-testid="q4-prog-generate" onClick={() => void run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/audit-programme/generate", { params: { path: { project_id: project.id }, query: { year } } })))}><RefreshCw aria-hidden />{t("generate")}</Button> : null}</div>} />
      <MutationError error={error} />
      {r.isLoading ? <LoadingState /> : rows.length ? (
        <div className="overflow-x-auto"><Table data-testid="q4-programme">
          <THead><TR><TH>{t("subject")}</TH>{MONTHS.map((m) => <TH key={m}><Ltr>{m}</Ltr></TH>)}</TR></THead>
          <TBody>{subjects.map((s) => (
            <TR key={s}><TD label={t("subject")}><Ltr className="font-medium">{s}</Ltr></TD>
              {MONTHS.map((m) => { const ln = rows.find((x) => (x.process_code ?? (x.supplier ? String(x.supplier.code) : x.engagement_code ?? x.clause_set ?? "—")) === s && x.planned_month === m); return <TD key={m} label={String(m)}>{ln ? <span data-testid="q4-prog-cell" data-status={ln.status}>{ln.audit_id ? <Link href={`/quality/audits/${ln.audit_id}`}><Q4Status value={ln.on_time ? "done" : ln.status} /></Link> : <Q4Status value={ln.status} />}</span> : null}</TD>; })}
            </TR>
          ))}</TBody>
        </Table></div>
      ) : <EmptyState message={ta("noProgramme")} />}
    </div>
  );
}

// ---- management reviews -------------------------------------------------------------------------

export function MrvsPage() {
  return <Q4Gate>{(p) => <Mrvs project={p} />}</Q4Gate>;
}

function Mrvs({ project }: { project: Project }) {
  const t = useT("quality.q4.mrv");
  const tc = useTranslations("quality.common");
  const caps = useQCaps(project.id);
  const r = useQ4Mrvs(project.id);
  const { run, busy, error } = useRun();
  const [f, set] = useForm({ period_start: "", period_end: "" });
  const [adding, setAdding] = useState(false);
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} actions={caps.write("quality_audit.conduct") && !adding ? <Button onClick={() => setAdding(true)} data-testid="q4-mrv-new"><Plus aria-hidden />{t("new")}</Button> : null} />
      {adding ? (
        <Card className="mb-4"><CardContent className="flex flex-wrap items-end gap-3 p-4">
          <MutationError error={error} />
          <FormField id="m-s" label={t("from")}><Input id="m-s" type="date" value={f.period_start} onChange={set("period_start")} dir="ltr" /></FormField>
          <FormField id="m-e" label={t("to")}><Input id="m-e" type="date" value={f.period_end} onChange={set("period_end")} dir="ltr" /></FormField>
          <Button disabled={busy || !f.period_start || !f.period_end} onClick={() => void run(async () => { const o = await unwrap(api.POST("/api/v1/projects/{project_id}/quality/management-reviews", { params: { path: { project_id: project.id } }, body: f })); setAdding(false); return o; })}>{tc("save")}</Button>
        </CardContent></Card>
      ) : null}
      {r.isLoading ? <LoadingState /> : (r.data ?? []).length ? (
        <Table data-testid="q4-mrvs"><THead><TR><TH>{t("no")}</TH><TH>{t("period")}</TH><TH>{t("held")}</TH><TH>{t("status")}</TH></TR></THead>
          <TBody>{(r.data ?? []).map((m) => <TR key={m.id} data-testid="q4-mrv-row"><TD label={t("no")}><Link href={`/quality/management-reviews/${m.id}`} className="ltr font-medium">{m.mrv_no}</Link></TD><TD label={t("period")}><Ltr>{m.period_start} – {m.period_end}</Ltr></TD><TD label={t("held")}><Ltr>{m.held_on ?? "—"}</Ltr></TD><TD label={t("status")}><Q4Status value={m.status} /></TD></TR>)}</TBody></Table>
      ) : <EmptyState />}
    </div>
  );
}

export function MrvDetailPage({ id }: { id: string }) {
  return <Q4Gate>{(p) => <MrvDetail project={p} id={id} />}</Q4Gate>;
}

function MrvDetail({ project, id }: { project: Project; id: string }) {
  const t = useT("quality.q4.mrv");
  const name = useName();
  const caps = useQCaps(project.id);
  const r = useQ4Mrv(id);
  const { run, busy, error } = useRun();
  const [inputs, setInputs] = useState<Record<string, { note: string; not_applicable: boolean }>>({});
  const [out, setOut] = useState("");
  if (r.isLoading) return <LoadingState />;
  if (r.isError || !r.data) return <ErrorState error={r.error} onRetry={() => r.refetch()} />;
  const m = r.data;
  const draft = m.status === "draft" && caps.write("quality_audit.conduct");
  const get = (k: string, x: Record<string, unknown>) => inputs[k] ?? { note: String(x.note ?? ""), not_applicable: Boolean(x.not_applicable) };
  return (
    <div>
      <PageHeader title={<Ltr>{m.mrv_no}</Ltr>} description={`${m.period_start} – ${m.period_end}`} actions={<Q4Status value={m.status} />} />
      <MutationError error={error} />
      <Card className="mb-4"><CardContent className="space-y-2 p-3" data-testid="q4-mrv-inputs">
        <p className="font-medium">{t("inputs")}</p>
        {m.inputs.map((x) => { const k = String(x.key); const v = get(k, x); return (
          <div key={k} className="grid gap-1 rounded-md border p-2 sm:grid-cols-[1fr_2fr_auto]" data-testid="q4-mrv-input">
            <p className="text-sm font-medium">{name(String(x.label_en), String(x.label_ar))}</p>
            {draft ? <Textarea rows={2} value={v.note} onChange={(e) => setInputs((s) => ({ ...s, [k]: { ...v, note: e.target.value } }))} /> : <p className="text-sm">{v.not_applicable ? t("na") : v.note || "—"}</p>}
            {draft ? <label className="flex items-center gap-1 text-sm"><input type="checkbox" checked={v.not_applicable} onChange={(e) => setInputs((s) => ({ ...s, [k]: { ...v, not_applicable: e.target.checked } }))} />{t("na")}</label> : null}
          </div>
        ); })}
        {draft ? <div className="flex gap-2">
          <Button size="sm" variant="outline" disabled={busy} data-testid="q4-mrv-save" onClick={() => void run(() => unwrap(api.PATCH("/api/v1/quality/management-reviews/{mid}", { params: { path: { mid: id } }, body: { inputs } })))}>{t("save")}</Button>
          <Button size="sm" disabled={busy} data-testid="q4-mrv-hold" onClick={() => void run(async () => { if (Object.keys(inputs).length) await unwrap(api.PATCH("/api/v1/quality/management-reviews/{mid}", { params: { path: { mid: id } }, body: { inputs } })); return unwrap(api.POST("/api/v1/quality/management-reviews/{mid}/hold", { params: { path: { mid: id } }, body: {} })); })}>{t("hold")}</Button>
        </div> : null}
      </CardContent></Card>
      {m.kpi_snapshot ? (
        <Card className="mb-4"><CardContent className="p-3"><p className="mb-2 font-medium">{t("snapshot")}</p>
          <Table compact data-testid="q4-mrv-snapshot"><THead><TR><TH>KPI</TH><TH>{t("name")}</TH><TH>{t("value")}</TH><TH>{t("target")}</TH></TR></THead>
            <TBody>{((m.kpi_snapshot.kpis ?? []) as { kpi: string; name_en: string; name_ar: string; display: string; target: string | null }[]).map((k) => <TR key={k.kpi}><TD label="KPI"><Ltr>{k.kpi}</Ltr></TD><TD label={t("name")}>{name(k.name_en, k.name_ar)}</TD><TD label={t("value")}><Ltr>{k.display}</Ltr></TD><TD label={t("target")}><Ltr>{k.target ?? "—"}</Ltr></TD></TR>)}</TBody></Table>
        </CardContent></Card>
      ) : null}
      <Card className="mb-4"><CardContent className="space-y-2 p-3"><p className="font-medium">{t("outputs")}</p>
        {m.outputs.map((o) => <p key={String(o.id)} className="text-sm">• {String(o.text)} {o.ca_id ? <Link href={`/actions/${String(o.ca_id)}`} className="underline">CA</Link> : null}</p>)}
        {m.status !== "minutes_issued" && caps.write("quality_audit.conduct") ? <div className="flex flex-wrap gap-2"><Input value={out} onChange={(e) => setOut(e.target.value)} placeholder={t("outputText")} className="max-w-md" data-testid="q4-mrv-output" /><Button size="sm" variant="outline" disabled={busy || out.length < 3} onClick={() => void run(async () => { const o = await unwrap(api.PATCH("/api/v1/quality/management-reviews/{mid}", { params: { path: { mid: id } }, body: { outputs: [...m.outputs.map((x) => ({ id: String(x.id), kind: x.kind as "improvement", text: String(x.text), create_ca: false })), { kind: "improvement", text: out, create_ca: true }] } })); setOut(""); return o; })}>{t("addOutputCa")}</Button></div> : null}
      </CardContent></Card>
      {m.can_issue ? <Button disabled={busy} data-testid="q4-mrv-issue" onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/management-reviews/{mid}/issue-minutes", { params: { path: { mid: id } }, body: {} })))}>{t("issueMinutes")}</Button> : null}
      <div className="mt-3 flex gap-2"><FileButton id={m.minutes_en_id} label={t("minutesEn")} /><FileButton id={m.minutes_ar_id} label={t("minutesAr")} /></div>
    </div>
  );
}
