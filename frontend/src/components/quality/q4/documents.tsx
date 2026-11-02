"use client";
import { CheckCircle2, Download, FilePlus2, Plus, Send } from "lucide-react";
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
import { ListToolbar, SearchFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Link } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { useQ4Document, useQ4Documents, useQ4MyAcks, useQ4Transmittal, useQ4Transmittals } from "@/lib/api/quality/q4";
import { useDebounced } from "@/lib/use-debounced";
import { useFormatters } from "@/lib/use-formatters";
import { ReasonDialog, useQCaps, useRun } from "@/components/quality/q0/common";
import { FileButton, Ltr, Q4Gate, Q4Status, clean, upload, useForm, useName, type Project , useT } from "./common";

const DOC_TYPES = ["pqp", "quality_manual", "procedure", "work_instruction", "sop", "method_statement", "specification", "form", "other"];

export function DocumentsPage() {
  return <Q4Gate>{(p) => <Documents project={p} />}</Q4Gate>;
}

function Documents({ project }: { project: Project }) {
  const t = useT("quality.q4.doc");
  const tc = useTranslations("quality.common");
  const name = useName();
  const caps = useQCaps(project.id);
  const [search, setSearch] = useState("");
  const q = useDebounced(search, 300);
  const r = useQ4Documents(project.id, { q: q || null, page_size: 200 });
  const { run, busy, error } = useRun();
  const [adding, setAdding] = useState(false);
  const [f, set] = useForm({ doc_type: "procedure", title_en: "", title_ar: "", discipline: "" });
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} actions={caps.write("document.author") && !adding ? <Button onClick={() => setAdding(true)} data-testid="q4-doc-new"><Plus aria-hidden />{t("new")}</Button> : null} />
      <MyAcks project={project} />
      {adding ? (
        <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-4" data-testid="q4-doc-form">
          <MutationError error={error} />
          <FormField id="d-type" label={t("type")} required><Select id="d-type" value={f.doc_type} onChange={set("doc_type")}>{DOC_TYPES.map((x) => <option key={x} value={x}>{t(`types.${x}`)}</option>)}</Select></FormField>
          <FormField id="d-en" label={t("titleEn")} required><Input id="d-en" value={f.title_en} onChange={set("title_en")} dir="ltr" data-testid="q4-doc-title" /></FormField>
          <FormField id="d-ar" label={t("titleAr")}><Input id="d-ar" value={f.title_ar} onChange={set("title_ar")} dir="rtl" /></FormField>
          <FormField id="d-disc" label={t("discipline")}><Input id="d-disc" value={f.discipline} onChange={set("discipline")} dir="ltr" /></FormField>
          <div className="flex gap-2 sm:col-span-4">
            <Button disabled={busy || f.title_en.length < 3} data-testid="q4-doc-save" onClick={() => void run(async () => { const o = await unwrap(api.POST("/api/v1/projects/{project_id}/quality/documents", { params: { path: { project_id: project.id } }, body: clean(f) as never })); setAdding(false); return o; })}>{tc("save")}</Button>
            <Button variant="outline" onClick={() => setAdding(false)}>{tc("cancel")}</Button>
          </div>
        </CardContent></Card>
      ) : null}
      <ListToolbar><SearchFilter id="q4-doc-q" value={search} onChange={setSearch} /></ListToolbar>
      {r.isLoading ? <LoadingState /> : r.isError ? <ErrorState error={r.error} onRetry={() => r.refetch()} /> : (r.data?.items ?? []).length ? (
        <Table data-testid="q4-docs">
          <THead><TR><TH>{t("no")}</TH><TH>{t("type")}</TH><TH>{t("titleCol")}</TH><TH>{t("rev")}</TH><TH>{t("status")}</TH><TH>{t("reviewDue")}</TH></TR></THead>
          <TBody>{(r.data?.items ?? []).map((d) => (
            <TR key={d.id} data-testid="q4-doc-row">
              <TD label={t("no")}><Link href={`/quality/documents/${d.id}`} className="ltr font-medium underline-offset-2 hover:underline">{d.doc_no}</Link></TD>
              <TD label={t("type")}>{t(`types.${d.doc_type}`)}</TD>
              <TD label={t("titleCol")}>{name(d.title_en, d.title_ar)}</TD>
              <TD label={t("rev")}><Ltr>{d.current_rev ?? "—"}{d.open_rev ? ` → ${d.open_rev}` : ""}</Ltr></TD>
              <TD label={t("status")}><Q4Status value={d.open_rev_status ?? d.status} /></TD>
              <TD label={t("reviewDue")}><Ltr className={d.review_overdue ? "font-semibold text-danger" : ""}>{d.review_due_on ?? "—"}</Ltr></TD>
            </TR>
          ))}</TBody>
        </Table>
      ) : <EmptyState />}
    </div>
  );
}

/** Phone and desk: "My acknowledgements" with one-tap read-and-acknowledge (Q-DOC-05). */
function MyAcks({ project }: { project: Project }) {
  const t = useT("quality.q4.doc");
  const r = useQ4MyAcks(project.id);
  const { run, busy } = useRun();
  const rows = r.data ?? [];
  if (!rows.length) return null;
  return (
    <Card className="mb-4" data-testid="q4-my-acks"><CardContent className="space-y-2 p-4">
      <p className="font-medium">{t("myAcks")}</p>
      {rows.map((a) => (
        <div key={a.revision_id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-2" data-testid="q4-ack-row">
          <div><Link href={`/quality/documents/${a.document_id}`} className="ltr font-medium">{a.doc_no} Rev.{a.rev_code}</Link><p className="text-sm text-muted-foreground">{t("dueOn")} <Ltr>{a.due_on}</Ltr></p></div>
          <div className="flex gap-2">
            <FileButton id={a.file_attachment_id} label={t("read")} />
            <Button size="sm" disabled={busy} data-testid="q4-ack" onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/document-revisions/{rev_id}/ack", { params: { path: { rev_id: a.revision_id } } })), t("acked"))}><CheckCircle2 aria-hidden />{t("acknowledge")}</Button>
          </div>
        </div>
      ))}
    </CardContent></Card>
  );
}

export function DocumentDetailPage({ id }: { id: string }) {
  return <Q4Gate>{(p) => <DocumentDetail project={p} id={id} />}</Q4Gate>;
}

function DocumentDetail({ project, id }: { project: Project; id: string }) {
  const t = useT("quality.q4.doc");
  const name = useName();
  const { dateTime } = useFormatters();
  const caps = useQCaps(project.id);
  const r = useQ4Document(id);
  const { run, busy, error } = useRun();
  const [ret, setRet] = useState<null | { rev: string; step: "review" | "approve" }>(null);
  const [roles, setRoles] = useState<string | null>(null);
  if (r.isLoading) return <LoadingState />;
  if (r.isError || !r.data) return <ErrorState error={r.error} onRetry={() => r.refetch()} />;
  const d = r.data;
  const author = d.can_author && caps.write("document.author");
  const open = d.revisions.find((x) => x.status === "draft" || x.status === "for_review");
  const sign = (rid: string, step: "review" | "approve") => run(() => unwrap(api.POST(step === "review" ? "/api/v1/quality/document-revisions/{rev_id}/review" : "/api/v1/quality/document-revisions/{rev_id}/approve", { params: { path: { rev_id: rid } }, body: { decision: "approved" } })));
  return (
    <div>
      <PageHeader title={<span><Ltr>{d.doc_no}</Ltr> — {name(d.title_en, d.title_ar)}</span>} description={t(`types.${d.doc_type}`)} actions={<Q4Status value={d.status} />} />
      <MutationError error={error} />
      <div className="mb-4 grid gap-2 text-sm sm:grid-cols-4">
        <p>{t("current")}: <Ltr>{d.current_rev ?? "—"}</Ltr></p>
        <p>{t("reviewDue")}: <Ltr>{d.review_due_on ?? "—"}</Ltr></p>
        <p>{t("owner")}: {d.owner ? name(d.owner.name_en, d.owner.name_ar) : "—"}</p>
        {d.my_ack && !d.my_ack.acked_at ? <Button size="sm" data-testid="q4-ack-detail" disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/document-revisions/{rev_id}/ack", { params: { path: { rev_id: String(d.my_ack?.revision_id) } } })), t("acked"))}>{t("acknowledge")}</Button> : null}
      </div>
      {author && !open && d.status !== "obsolete" ? <Button className="mb-3" variant="outline" data-testid="q4-new-rev" disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/documents/{doc_id}/revisions", { params: { path: { doc_id: id } } })))}><FilePlus2 aria-hidden />{t("newRevision")}</Button> : null}
      <Table data-testid="q4-revisions">
        <THead><TR><TH>{t("rev")}</TH><TH>{t("status")}</TH><TH>{t("summary")}</TH><TH>{t("approved")}</TH><TH>{t("acks")}</TH><TH>{t("actions")}</TH></TR></THead>
        <TBody>{d.revisions.map((v) => (
          <TR key={v.id} data-testid="q4-rev-row" data-rev={v.rev_code}>
            <TD label={t("rev")}><Ltr className="font-medium">{v.rev_code}</Ltr></TD>
            <TD label={t("status")}><Q4Status value={v.status} />{v.returned_comment && v.status === "draft" ? <p className="text-xs text-muted-foreground">{v.returned_comment}</p> : null}</TD>
            <TD label={t("summary")}>{v.change_summary ?? "—"}</TD>
            <TD label={t("approved")}>{v.approved_at ? dateTime(v.approved_at) : "—"}</TD>
            <TD label={t("acks")}><Ltr>{v.acks.required ? `${v.acks.acked} / ${v.acks.required} (${v.acks.pct} %)` : "—"}</Ltr></TD>
            <TD label={t("actions")}><div className="flex flex-wrap gap-1">
              {v.download_name ? <Button size="sm" variant="outline" asChild><a href={`/api/v1/quality/document-revisions/${v.id}/download`} data-testid="q4-rev-download"><Download aria-hidden />PDF</a></Button> : null}
              {author && v.status === "draft" ? <label className="inline-flex cursor-pointer items-center rounded-md border px-2 py-1 text-sm" data-testid="q4-rev-upload">{t("uploadPdf")}<input type="file" accept="application/pdf" className="sr-only" onChange={(e) => { const file = e.target.files?.[0]; if (file) void run(async () => { const aid = await upload("q_document_file", v.id, file); return unwrap(api.PATCH("/api/v1/quality/document-revisions/{rev_id}", { params: { path: { rev_id: v.id } }, body: { file_attachment_id: aid } })); }); }} /></label> : null}
              {author && v.status === "draft" ? <Button size="sm" disabled={busy} data-testid="q4-rev-submit" onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/document-revisions/{rev_id}/submit", { params: { path: { rev_id: v.id } } })))}><Send aria-hidden />{t("submit")}</Button> : null}
              {d.can_review && v.status === "for_review" ? <><Button size="sm" disabled={busy} data-testid="q4-rev-review" onClick={() => void sign(v.id, "review")}>{t("review")}</Button><Button size="sm" variant="outline" onClick={() => setRet({ rev: v.id, step: "review" })}>{t("return")}</Button></> : null}
              {d.can_approve && v.status === "for_review" ? <><Button size="sm" disabled={busy} data-testid="q4-rev-approve" onClick={() => void sign(v.id, "approve")}>{t("approve")}</Button><Button size="sm" variant="outline" onClick={() => setRet({ rev: v.id, step: "approve" })}>{t("return")}</Button></> : null}
            </div></TD>
          </TR>
        ))}</TBody>
      </Table>
      {d.status === "superseded" || d.revisions.some((x) => x.status === "superseded") ? <Alert tone="info" className="mt-3">{t("supersededNote")}</Alert> : null}
      <Card className="mt-4"><CardContent className="space-y-2 p-4" data-testid="q4-distribution">
        <p className="font-medium">{t("distribution")}</p>
        <p className="text-sm">{t("roles")}: <Ltr>{(d.distribution.roles as string[] | undefined)?.join(", ") || "—"}</Ltr> · {t("ackRequired")}: {d.distribution.ack_required ? t("yes") : t("no_")}</p>
        {author ? (roles === null ? <Button size="sm" variant="outline" onClick={() => setRoles(((d.distribution.roles as string[] | undefined) ?? []).join(", "))}>{t("editDistribution")}</Button> : (
          <div className="flex flex-wrap items-end gap-2">
            <FormField id="dist-roles" label={t("roles")} hint={t("rolesHint")}><Input id="dist-roles" value={roles} onChange={(e) => setRoles(e.target.value)} dir="ltr" data-testid="q4-dist-roles" /></FormField>
            <Button size="sm" disabled={busy} data-testid="q4-dist-save" onClick={() => void run(async () => { const o = await unwrap(api.PUT("/api/v1/quality/documents/{doc_id}/distribution", { params: { path: { doc_id: id } }, body: { roles: roles.split(",").map((x) => x.trim()).filter(Boolean), ack_required: true } })); setRoles(null); return o; })}>{t("save")}</Button>
          </div>
        )) : null}
      </CardContent></Card>
      <ReasonDialog open={ret !== null} onOpenChange={(o) => !o && setRet(null)} title={t("return")} confirm={t("return")} label={t("comment")} onSubmit={async (text) => { if (!ret) return; await run(() => unwrap(api.POST(ret.step === "review" ? "/api/v1/quality/document-revisions/{rev_id}/review" : "/api/v1/quality/document-revisions/{rev_id}/approve", { params: { path: { rev_id: ret.rev } }, body: { decision: "returned", comment: text } }))); }} />
    </div>
  );
}

// ---- transmittals ----------------------------------------------------------------------------

export function TransmittalsPage() {
  return <Q4Gate>{(p) => <Transmittals project={p} />}</Q4Gate>;
}

function Transmittals({ project }: { project: Project }) {
  const t = useT("quality.q4.trm");
  const tc = useTranslations("quality.common");
  const caps = useQCaps(project.id);
  const r = useQ4Transmittals(project.id);
  const docs = useQ4Documents(project.id, { status: "approved", page_size: 200 });
  const { run, busy, error } = useRun();
  const [adding, setAdding] = useState(false);
  const [f, set] = useForm({ to_name: "", to_email: "", purpose: "for_approval", method: "email", subject: "", response_due_on: "", doc: "" });
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} actions={caps.write("document.author") && !adding ? <Button onClick={() => setAdding(true)} data-testid="q4-trm-new"><Plus aria-hidden />{t("new")}</Button> : null} />
      {adding ? (
        <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-3" data-testid="q4-trm-form">
          <MutationError error={error} />
          <FormField id="t-to" label={t("toName")} required><Input id="t-to" value={f.to_name} onChange={set("to_name")} /></FormField>
          <FormField id="t-mail" label={t("toEmail")}><Input id="t-mail" value={f.to_email} onChange={set("to_email")} dir="ltr" type="email" /></FormField>
          <FormField id="t-subj" label={t("subject")} required><Input id="t-subj" value={f.subject} onChange={set("subject")} /></FormField>
          <FormField id="t-purpose" label={t("purpose")}><Select id="t-purpose" value={f.purpose} onChange={set("purpose")}>{["for_approval", "for_review", "for_information", "for_construction", "as_built"].map((x) => <option key={x} value={x}>{t(`purposes.${x}`)}</option>)}</Select></FormField>
          <FormField id="t-method" label={t("method")}><Select id="t-method" value={f.method} onChange={set("method")}>{["email", "portal", "hand"].map((x) => <option key={x} value={x}>{t(`methods.${x}`)}</option>)}</Select></FormField>
          <FormField id="t-due" label={t("responseDue")}><Input id="t-due" type="date" value={f.response_due_on} onChange={set("response_due_on")} dir="ltr" /></FormField>
          <FormField id="t-doc" label={t("document")} required><Select id="t-doc" value={f.doc} onChange={set("doc")}><option value="">{tc("select")}</option>{(docs.data?.items ?? []).map((d) => <option key={d.id} value={d.id}>{d.doc_no} Rev.{d.current_rev}</option>)}</Select></FormField>
          <div className="flex gap-2 sm:col-span-3">
            <Button disabled={busy || !f.subject || !f.doc || !f.to_name} onClick={() => void run(async () => {
              const doc = await unwrap(api.GET("/api/v1/quality/documents/{doc_id}", { params: { path: { doc_id: f.doc } } }));
              const rev = doc.revisions.find((x) => x.status === "approved");
              const body = { to_kind: "external", to_name: f.to_name, to_email: f.to_email || null, purpose: f.purpose, method: f.method, subject: f.subject, response_due_on: f.response_due_on || null, items: [{ revision_id: rev?.id }] };
              const o = await unwrap(api.POST("/api/v1/projects/{project_id}/quality/transmittals", { params: { path: { project_id: project.id } }, body: body as never }));
              setAdding(false);
              return o;
            })}>{tc("save")}</Button>
            <Button variant="outline" onClick={() => setAdding(false)}>{tc("cancel")}</Button>
          </div>
        </CardContent></Card>
      ) : null}
      {r.isLoading ? <LoadingState /> : (r.data?.items ?? []).length ? (
        <Table data-testid="q4-trms">
          <THead><TR><TH>{t("no")}</TH><TH>{t("subject")}</TH><TH>{t("to")}</TH><TH>{t("purpose")}</TH><TH>{t("status")}</TH><TH>{t("responseDue")}</TH></TR></THead>
          <TBody>{(r.data?.items ?? []).map((x) => (
            <TR key={x.id} data-testid="q4-trm-row">
              <TD label={t("no")}><Link href={`/quality/transmittals/${x.id}`} className="ltr font-medium">{x.trm_no ?? t("draft")}</Link></TD>
              <TD label={t("subject")}>{x.subject}</TD><TD label={t("to")}>{x.to_label_en}</TD>
              <TD label={t("purpose")}>{t(`purposes.${x.purpose}`)}</TD><TD label={t("status")}><Q4Status value={x.status} /></TD>
              <TD label={t("responseDue")}><Ltr>{x.response_due_on ?? "—"}</Ltr></TD>
            </TR>
          ))}</TBody>
        </Table>
      ) : <EmptyState />}
    </div>
  );
}

export function TransmittalDetailPage({ id }: { id: string }) {
  return <Q4Gate>{(p) => <TransmittalDetail project={p} id={id} />}</Q4Gate>;
}

function TransmittalDetail({ project, id }: { project: Project; id: string }) {
  const t = useT("quality.q4.trm");
  const caps = useQCaps(project.id);
  const r = useQ4Transmittal(id);
  const { run, busy, error } = useRun();
  const [codes, setCodes] = useState<Record<string, string>>({});
  const [who, setWho] = useState("");
  if (r.isLoading) return <LoadingState />;
  if (r.isError || !r.data) return <ErrorState error={r.error} onRetry={() => r.refetch()} />;
  const x = r.data;
  const w = caps.write("document.author");
  return (
    <div>
      <PageHeader title={<Ltr>{x.trm_no ?? t("draft")}</Ltr>} description={x.subject} actions={<Q4Status value={x.status} />} />
      <MutationError error={error} />
      <div className="mb-3 flex flex-wrap gap-2">
        {w && x.status === "draft" ? <Button data-testid="q4-trm-send" disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/transmittals/{tid}/send", { params: { path: { tid: id } } })), t("sent"))}><Send aria-hidden />{t("send")}</Button> : null}
        <FileButton id={x.cover_en_id} label={t("coverEn")} testId="q4-trm-cover-en" />
        <FileButton id={x.cover_ar_id} label={t("coverAr")} />
      </div>
      <Table>
        <THead><TR><TH>{t("ref")}</TH><TH>{t("itemTitle")}</TH><TH>{t("code")}</TH></TR></THead>
        <TBody>{x.items.map((i) => (
          <TR key={i.id}><TD label={t("ref")}><Ltr>{i.ref}</Ltr></TD><TD label={t("itemTitle")}>{i.title}</TD>
            <TD label={t("code")}>{x.status === "sent" && w ? <Select value={codes[i.id] ?? ""} onChange={(e) => setCodes((c) => ({ ...c, [i.id]: e.target.value }))} data-testid="q4-trm-code"><option value="">—</option>{["A", "B", "C", "D"].map((c) => <option key={c} value={c}>{c} — {t(`codes.${c}`)}</option>)}</Select> : <Ltr>{i.response_code ?? "—"}</Ltr>}</TD></TR>
        ))}</TBody>
      </Table>
      {x.status === "sent" && w ? (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <FormField id="t-who" label={t("respondedBy")}><Input id="t-who" value={who} onChange={(e) => setWho(e.target.value)} /></FormField>
          <Button data-testid="q4-trm-respond" disabled={busy || !Object.keys(codes).length} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/transmittals/{tid}/response", { params: { path: { tid: id } }, body: { response_name: who || null, items: Object.entries(codes).filter(([, v]) => v).map(([item_id, response_code]) => ({ item_id, response_code: response_code as "A" })) } })))}>{t("recordResponse")}</Button>
        </div>
      ) : null}
      {x.note ? <Textarea className="mt-3" readOnly value={x.note} /> : null}
    </div>
  );
}
