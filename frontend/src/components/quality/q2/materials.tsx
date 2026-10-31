"use client";
import { Plus, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiWarnings } from "@/components/common/api-warnings";
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { useQSuppliers } from "@/lib/api/quality/q0";
import { useQMar, useQMars, useQMir, useQMirs, useQQuarantine, useQQuarantineItem } from "@/lib/api/quality/q2";
import { useDebounced } from "@/lib/use-debounced";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { QGate, ReasonDialog, useBilingual, useQCaps, useQLabels, useRun, type Project } from "../q0/common";
import { DecisionDialog, Q2Badge, Signoffs, clean, type S } from "./shared";

const PAGE_SIZE = 50;

/** Pages of the construction-only material records show this when the project uses the logistics profile. */
function ConstructionOnly({ profile, children }: { profile: string | null; children: React.ReactNode }) {
  const t = useTranslations("quality.q2");
  return (
    <>
      {profile === "logistics" ? <Alert tone="info" className="mb-3" data-testid="q2-other-profile">{t("otherProfile")}</Alert> : null}
      {children}
    </>
  );
}

/* ═════════════ MAR `/quality/materials` (§C.3.1) ═════════════ */

export function MarListPage() {
  return <QGate>{(p, st) => <ConstructionOnly profile={st.sector_profile}><Mars project={p} /></ConstructionOnly>}</QGate>;
}

function Mars({ project }: { project: Project }) {
  const t = useTranslations("quality.mat");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const caps = useQCaps(project.id);
  const s = useSearchState();
  const { date } = useFormatters(project.id);
  const page = s.getInt("page", 1) ?? 1;
  const status = s.get("status") ?? "";
  const [search, setSearch] = useState(s.get("q") ?? "");
  const q = useDebounced(search, 300);
  const r = useQMars(project.id, { status: status ? [status as S["QMarStatus"]] : null, q: q || null, page, page_size: PAGE_SIZE });
  const [adding, setAdding] = useState(false);
  const items = r.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")}
        actions={caps.write("material.submit") && !adding ? <Button onClick={() => setAdding(true)} data-testid="q2-mar-new"><Plus aria-hidden />{t("new")}</Button> : null} />
      {adding ? <MarForm project={project} onDone={() => setAdding(false)} /> : null}
      <ListToolbar>
        <SearchFilter id="q2-mar-q" value={search} onChange={(v) => { setSearch(v); s.set({ q: v, page: null }); }} />
        <SelectFilter id="q2-mar-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={options("mar_status")} />
      </ListToolbar>
      {r.isLoading ? <LoadingState /> : r.isError ? <ErrorState error={r.error} onRetry={() => r.refetch()} /> : items.length ? (
        <>
          <Table compact data-testid="q2-mar-table">
            <THead><TR><TH>{t("no")}</TH><TH>{t("titleField")}</TH><TH>{t("category")}</TH><TH>{t("contractor")}</TH><TH>{t("supplier")}</TH><TH>{t("submitted")}</TH><TH>{tc("status")}</TH></TR></THead>
            <TBody>{items.map((m) => (
              <TR key={m.id} data-testid="q2-mar-row" data-no={m.mar_no ?? ""} data-status={m.status}>
                <TD label={t("no")}><Link href={`/quality/materials/${m.id}`} className="ltr font-medium text-primary hover:underline">{m.mar_no ? `${m.mar_no} Rev.${m.revision}` : t("draft")}</Link></TD>
                <TD label={t("titleField")} dir="auto">{m.title_en}</TD>
                <TD label={t("category")}>{l("material_category", m.category)}</TD>
                <TD label={t("contractor")} className="ltr">{m.engagement_code ?? "—"}</TD>
                <TD label={t("supplier")} className="ltr">{m.supplier_code ?? "—"}</TD>
                <TD label={t("submitted")}>{date(m.submitted_at)}</TD>
                <TD label={tc("status")}><Q2Badge value={m.status} label={l("mar_status", m.status)} /></TD>
              </TR>
            ))}</TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={r.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : <EmptyState message={t("empty")} />}
    </div>
  );
}

type Row = { requirement: string; offered: string; result: string; note: string };

function MarForm({ project, onDone }: { project: Project; onDone: () => void }) {
  const t = useTranslations("quality.mat");
  const tc = useTranslations("quality.common");
  const { options } = useQLabels();
  const opts = useProjectOptions(project.id);
  const sup = useQSuppliers({ page_size: 200 });
  const router = useRouter();
  const { run, busy, error } = useRun();
  const [f, setF] = useState({ engagement_id: "", title_en: "", title_ar: "", category: "", supplier_id: "", manufacturer: "", spec_section: "", deviations_note: "" });
  const [rows, setRows] = useState<Row[]>([{ requirement: "", offered: "", result: "complies", note: "" }]);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  async function save() {
    const body = { ...clean(f), compliance: rows.filter((r) => r.requirement.trim()) } as unknown as S["QMarCreate"];
    const out = await run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/mars", { params: { path: { project_id: project.id } }, body })));
    if (out) { onDone(); router.push(`/quality/materials/${out.id}`); }
  }
  return (
    <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-3" data-testid="q2-mar-form">
      <MutationError error={error} />
      <FormField id="mar-eng" label={t("contractor")} required><Select value={f.engagement_id} onChange={set("engagement_id")} data-testid="mar-engagement"><option value="">{tc("select")}</option>{opts.engagements.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <FormField id="mar-cat" label={t("category")} required><Select value={f.category} onChange={set("category")} data-testid="mar-category"><option value="">{tc("select")}</option>{options("material_category").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <FormField id="mar-sup" label={t("supplier")}><Select value={f.supplier_id} onChange={set("supplier_id")} data-testid="mar-supplier"><option value="">—</option>{(sup.data?.items ?? []).map((x) => <option key={x.id} value={x.id}>{x.supplier_code}</option>)}</Select></FormField>
      <FormField id="mar-title" label={t("titleField")} required className="sm:col-span-2"><Input value={f.title_en} onChange={set("title_en")} data-testid="mar-title" /></FormField>
      <FormField id="mar-title-ar" label={t("titleAr")}><Input value={f.title_ar} onChange={set("title_ar")} dir="rtl" /></FormField>
      <FormField id="mar-man" label={t("manufacturer")}><Input value={f.manufacturer} onChange={set("manufacturer")} /></FormField>
      <FormField id="mar-spec" label={t("spec")}><Input value={f.spec_section} onChange={set("spec_section")} dir="ltr" /></FormField>
      <div className="sm:col-span-3">
        <ComplianceEditor rows={rows} setRows={setRows} />
      </div>
      {rows.some((r) => r.result === "deviation") ? <FormField id="mar-dev" label={t("deviations")} required className="sm:col-span-3"><Textarea value={f.deviations_note} onChange={set("deviations_note")} rows={2} data-testid="mar-deviations" /></FormField> : null}
      <div className="flex gap-2 sm:col-span-3">
        <Button disabled={busy || !f.engagement_id || !f.category || !f.title_en} onClick={() => void save()} data-testid="mar-save">{tc("save")}</Button>
        <Button variant="outline" onClick={onDone}>{tc("cancel")}</Button>
      </div>
    </CardContent></Card>
  );
}

function ComplianceEditor({ rows, setRows }: { rows: Row[]; setRows: (r: Row[]) => void }) {
  const t = useTranslations("quality.mat");
  const { options } = useQLabels();
  const upd = (i: number, k: keyof Row, v: string) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  return (
    <div data-testid="q2-compliance">
      <h3 className="mb-2 text-sm font-semibold">{t("compliance")}</h3>
      {rows.map((r, i) => (
        <div key={i} className="mb-2 grid gap-2 sm:grid-cols-[2fr_2fr_1fr_auto]">
          <Input aria-label={t("requirement")} placeholder={t("requirement")} value={r.requirement} onChange={(e) => upd(i, "requirement", e.target.value)} data-testid="mar-req" />
          <Input aria-label={t("offered")} placeholder={t("offered")} value={r.offered} onChange={(e) => upd(i, "offered", e.target.value)} />
          <Select aria-label={t("result")} value={r.result} onChange={(e) => upd(i, "result", e.target.value)} data-testid="mar-result">{options("compliance").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select>
          <Button variant="ghost" size="sm" aria-label={t("removeRow")} onClick={() => setRows(rows.filter((_, j) => j !== i))}><Trash2 aria-hidden /></Button>
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={() => setRows([...rows, { requirement: "", offered: "", result: "complies", note: "" }])}><Plus aria-hidden />{t("addRow")}</Button>
    </div>
  );
}

export function MarDetailPage({ id }: { id: string }) {
  return <QGate>{(p) => <MarDetail project={p} id={id} />}</QGate>;
}

function MarDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.mat");
  const { l } = useQLabels();
  const bi = useBilingual();
  const { dateTime } = useFormatters(project.id);
  const router = useRouter();
  const q = useQMar(id);
  const { run, busy, error } = useRun();
  const [deciding, setDeciding] = useState(false);
  const [withdrawing, setWithdrawing] = useState(false);
  const [accept, setAccept] = useState(false);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const m = q.data;
  if (!m) return null;
  const path = { params: { path: { mar_id: m.id } } };
  const can = (a: string) => m.actions.includes(a);
  async function resubmit() {
    const out = await run(() => unwrap(api.POST("/api/v1/quality/mars/{mar_id}/resubmit", path)));
    if (out) router.push(`/quality/materials/${out.id}`);
  }
  return (
    <div data-testid="q2-mar-detail" data-status={m.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/materials" }, { label: m.mar_no ?? t("draft") }]} />
      <PageHeader title={<span className="ltr">{m.mar_no ? `${m.mar_no} Rev.${m.revision}` : t("draft")}</span>} description={bi(m.title_en, m.title_ar)}
        badge={<Q2Badge value={m.status} label={l("mar_status", m.status)} testId="q2-mar-status" />}
        actions={<>
          {can("submit") ? <Button disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/mars/{mar_id}/submit", path)))} data-testid="q2-mar-submit">{t("submit")}</Button> : null}
          {can("decide") ? <Button onClick={() => setDeciding(true)} data-testid="q2-mar-decide">{t("decide")}</Button> : null}
          {can("resubmit") ? <Button variant="outline" disabled={busy} onClick={() => void resubmit()} data-testid="q2-mar-resubmit">{t("resubmit")}</Button> : null}
          {can("withdraw") ? <Button variant="outline" onClick={() => setWithdrawing(true)}>{t("withdraw")}</Button> : null}
        </>} />
      <MutationError error={error} />
      <ApiWarnings warnings={m.warnings} className="mb-3" />
      {m.with_deviations ? <Alert tone="warning" className="mb-3">{t("withDeviations")}</Alert> : null}
      <Card className="mb-4"><CardContent className="p-4"><FieldList>
        <FieldItem label={t("category")}>{l("material_category", m.category)}</FieldItem>
        <FieldItem label={t("contractor")} ltr>{m.engagement_code ?? "—"}</FieldItem>
        <FieldItem label={t("supplier")} ltr>{m.supplier_code ?? "—"}</FieldItem>
        <FieldItem label={t("manufacturer")}>{m.manufacturer ?? "—"}</FieldItem>
        <FieldItem label={t("spec")} ltr>{m.spec_section ?? "—"}</FieldItem>
        <FieldItem label={t("code")}>{m.approval_code ? l("mar_code", m.approval_code) : "—"}</FieldItem>
        <FieldItem label={t("submitted")}>{dateTime(m.submitted_at)}</FieldItem>
        <FieldItem label={t("decided")}>{dateTime(m.decided_at)}</FieldItem>
        {m.decision_comment ? <FieldItem label={t("comment")} wide><span dir="auto">{m.decision_comment}</span></FieldItem> : null}
        {m.deviations_note ? <FieldItem label={t("deviations")} wide><span dir="auto">{m.deviations_note}</span></FieldItem> : null}
      </FieldList></CardContent></Card>
      <Card className="mb-4"><CardContent className="p-4">
        <h3 className="mb-2 text-sm font-semibold">{t("compliance")}</h3>
        <Table compact><THead><TR><TH>{t("requirement")}</TH><TH>{t("offered")}</TH><TH>{t("result")}</TH></TR></THead>
          <TBody>{m.compliance.map((r, i) => <TR key={i} data-result={r.result}><TD label={t("requirement")} dir="auto">{r.requirement}</TD><TD label={t("offered")} dir="auto">{r.offered}</TD><TD label={t("result")}>{l("compliance", r.result)}</TD></TR>)}</TBody></Table>
      </CardContent></Card>
      <Card className="mb-4"><CardContent className="p-4"><h3 className="mb-2 text-sm font-semibold">{t("documents")}</h3><Attachments ownerType="q_mar" ownerId={m.id} canUpload={can("edit")} /></CardContent></Card>
      {m.revisions.length > 1 ? <Card className="mb-4"><CardContent className="p-4"><h3 className="mb-2 text-sm font-semibold">{t("revisions")}</h3>
        <ul className="text-sm">{m.revisions.map((r) => <li key={r.id}><Link href={`/quality/materials/${r.id}`} className="text-primary hover:underline">Rev.{r.revision}</Link> · {l("mar_status", r.status)}</li>)}</ul></CardContent></Card> : null}
      <Signoffs recordType="mar" recordId={m.id} />
      <HistoryPanel entityType="q_mar" entityId={m.id} projectId={project.id} />
      <DecisionDialog open={deciding} onOpenChange={setDeciding} title={t("decide")} testId="q2-mar-decide-dialog"
        options={["A", "B", "C", "D"].map((c) => ({ value: c, label: l("mar_code", c) }))} needsComment={(v) => v !== "A"}
        extra={m.with_deviations ? <label className="flex items-center gap-2 text-sm"><Checkbox checked={accept} onCheckedChange={(v) => setAccept(Boolean(v))} data-testid="q2-accept-deviations" />{t("acceptDeviations")}</label> : null}
        onSubmit={(d, c) => unwrap(api.POST("/api/v1/quality/mars/{mar_id}/decide", { ...path, body: { approval_code: d as "A", comment: c || null, accept_deviations: accept } })).then(() => q.refetch())} />
      <ReasonDialog open={withdrawing} onOpenChange={setWithdrawing} title={t("withdraw")} confirm={t("withdraw")}
        onSubmit={(reason) => unwrap(api.POST("/api/v1/quality/mars/{mar_id}/withdraw", { ...path, body: { reason } })).then(() => q.refetch())} />
    </div>
  );
}

/* ═════════════ MIR `/quality/material-inspections` (§C.3.2) ═════════════ */

export function MirListPage() {
  return <QGate>{(p, st) => <ConstructionOnly profile={st.sector_profile}><Mirs project={p} /></ConstructionOnly>}</QGate>;
}

function Mirs({ project }: { project: Project }) {
  const t = useTranslations("quality.mir");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const caps = useQCaps(project.id);
  const s = useSearchState();
  const { date } = useFormatters(project.id);
  const page = s.getInt("page", 1) ?? 1;
  const status = s.get("status") ?? "";
  const r = useQMirs(project.id, { status: status ? [status as S["QMirStatus"]] : null, page, page_size: PAGE_SIZE });
  const [adding, setAdding] = useState(false);
  const items = r.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")}
        actions={caps.write("material.submit") && !adding ? <Button onClick={() => setAdding(true)} data-testid="q2-mir-new"><Plus aria-hidden />{t("new")}</Button> : null} />
      {adding ? <MirForm project={project} onDone={() => setAdding(false)} /> : null}
      <ListToolbar><SelectFilter id="q2-mir-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={options("mir_status")} /></ListToolbar>
      {r.isLoading ? <LoadingState /> : r.isError ? <ErrorState error={r.error} onRetry={() => r.refetch()} /> : items.length ? (
        <>
          <Table compact data-testid="q2-mir-table">
            <THead><TR><TH>{t("no")}</TH><TH>{t("material")}</TH><TH>{t("mar")}</TH><TH>{t("quantity")}</TH><TH>{t("delivered")}</TH><TH>{t("result")}</TH><TH>{tc("status")}</TH></TR></THead>
            <TBody>{items.map((x) => (
              <TR key={x.id} data-testid="q2-mir-row" data-no={x.mir_no ?? ""} data-status={x.status}>
                <TD label={t("no")}><Link href={`/quality/material-inspections/${x.id}`} className="ltr font-medium text-primary hover:underline">{x.mir_no ?? t("draft")}</Link></TD>
                <TD label={t("material")} dir="auto">{x.material_description}</TD>
                <TD label={t("mar")} className="ltr">{x.mar_no ?? "—"}</TD>
                <TD label={t("quantity")} className="ltr">{x.quantity} {x.unit}</TD>
                <TD label={t("delivered")}>{date(x.delivered_at)}</TD>
                <TD label={t("result")}>{x.result ? <Q2Badge value={x.result === "rejected" ? "rejected" : "accepted"} label={l("mir_result", x.result)} /> : "—"}</TD>
                <TD label={tc("status")}><Q2Badge value={x.status} label={l("mir_status", x.status)} /></TD>
              </TR>
            ))}</TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={r.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : <EmptyState message={t("empty")} />}
    </div>
  );
}

function MirForm({ project, onDone }: { project: Project; onDone: () => void }) {
  const t = useTranslations("quality.mir");
  const tc = useTranslations("quality.common");
  const { options } = useQLabels();
  const opts = useProjectOptions(project.id);
  const mars = useQMars(project.id, { status: ["approved", "approved_as_noted", "revise_resubmit"], page_size: 200 });
  const router = useRouter();
  const { run, busy, error } = useRun();
  const [f, setF] = useState({ mar_id: "", category: "", engagement_id: "", material_description: "", site_id: "", delivery_note_no: "", quantity: "", unit: "", lots: "", certs: "" });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const split = (v: string) => v.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean);
  async function save() {
    const { lots, certs, ...rest } = f;
    const body = { ...clean(rest), lot_numbers: split(lots), cert_heat_numbers: split(certs) } as unknown as S["QMirCreate"];
    const out = await run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/mirs", { params: { path: { project_id: project.id } }, body })));
    if (out) { onDone(); router.push(`/quality/material-inspections/${out.id}`); }
  }
  return (
    <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-3" data-testid="q2-mir-form">
      <MutationError error={error} />
      <FormField id="mir-mar" label={t("mar")}><Select value={f.mar_id} onChange={set("mar_id")} data-testid="mir-mar"><option value="">{t("noMar")}</option>{(mars.data?.items ?? []).map((m) => <option key={m.id} value={m.id}>{m.mar_no} Rev.{m.revision} — {m.title_en}</option>)}</Select></FormField>
      {!f.mar_id ? <>
        <FormField id="mir-cat" label={t("category")} required><Select value={f.category} onChange={set("category")} data-testid="mir-category"><option value="">{tc("select")}</option>{options("material_category").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
        <FormField id="mir-eng" label={t("contractor")}><Select value={f.engagement_id} onChange={set("engagement_id")}><option value="">—</option>{opts.engagements.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      </> : null}
      <FormField id="mir-desc" label={t("material")} className="sm:col-span-2"><Input value={f.material_description} onChange={set("material_description")} data-testid="mir-material" /></FormField>
      <FormField id="mir-site" label={t("site")}><Select value={f.site_id} onChange={set("site_id")}><option value="">—</option>{opts.sites.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <FormField id="mir-dn" label={t("deliveryNote")}><Input value={f.delivery_note_no} onChange={set("delivery_note_no")} dir="ltr" /></FormField>
      <FormField id="mir-qty" label={t("quantity")} required><div className="flex gap-2"><Input value={f.quantity} onChange={set("quantity")} inputMode="decimal" dir="ltr" data-testid="mir-qty" /><Input value={f.unit} onChange={set("unit")} className="w-20" dir="ltr" placeholder="m" data-testid="mir-unit" /></div></FormField>
      <FormField id="mir-lots" label={t("tagHeats")} hint={t("listHint")}><Input value={f.lots} onChange={set("lots")} dir="ltr" data-testid="mir-lots" /></FormField>
      <FormField id="mir-certs" label={t("certHeats")} hint={t("listHint")}><Input value={f.certs} onChange={set("certs")} dir="ltr" data-testid="mir-certs" /></FormField>
      <div className="flex gap-2 sm:col-span-3">
        <Button disabled={busy || !f.quantity || !f.unit || (!f.mar_id && !f.category)} onClick={() => void save()} data-testid="mir-save">{tc("save")}</Button>
        <Button variant="outline" onClick={onDone}>{tc("cancel")}</Button>
      </div>
    </CardContent></Card>
  );
}

export function MirDetailPage({ id }: { id: string }) {
  return <QGate>{(p) => <MirDetail project={p} id={id} />}</QGate>;
}

function MirDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.mir");
  const tq = useTranslations("quality.q2");
  const tc = useTranslations("common");
  const { l, options } = useQLabels();
  const { dateTime } = useFormatters(project.id);
  const q = useQMir(id);
  const { run, busy, error } = useRun();
  const [dec, setDec] = useState({ result: "accepted", accepted_qty: "", rejected_qty: "0", comment: "" });
  const [open, setOpen] = useState(false);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const x = q.data;
  if (!x) return null;
  const path = { params: { path: { mir_id: x.id } } };
  const can = (a: string) => x.actions.includes(a);
  return (
    <div data-testid="q2-mir-detail" data-status={x.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/material-inspections" }, { label: x.mir_no ?? t("draft") }]} />
      <PageHeader title={<span className="ltr">{x.mir_no ?? t("draft")}</span>} description={x.material_description}
        badge={<Q2Badge value={x.status} label={l("mir_status", x.status)} testId="q2-mir-status" />}
        actions={<>
          {can("submit") ? <Button disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/mirs/{mir_id}/submit", path)))} data-testid="q2-mir-submit">{t("submit")}</Button> : null}
          {can("decide") ? <Button onClick={() => { setDec((d) => ({ ...d, accepted_qty: d.accepted_qty || x.quantity })); setOpen(true); }} data-testid="q2-mir-decide">{t("decide")}</Button> : null}
        </>} />
      <MutationError error={error} />
      <ApiWarnings warnings={x.warnings} className="mb-3" />
      {x.failed_tests ? <Alert tone="danger" className="mb-3">{t("failedTests", { n: x.failed_tests })}</Alert> : null}
      <Card className="mb-4"><CardContent className="p-4"><FieldList>
        <FieldItem label={t("mar")} ltr>{x.mar_no ? `${x.mar_no} Rev.${x.mar_revision}` : "—"}{x.mar_status ? ` · ${l("mar_status", x.mar_status)}` : ""}</FieldItem>
        <FieldItem label={t("category")}>{l("material_category", x.category)}</FieldItem>
        <FieldItem label={t("contractor")} ltr>{x.engagement_code ?? "—"}</FieldItem>
        <FieldItem label={t("supplier")} ltr>{x.supplier_code ?? "—"}</FieldItem>
        <FieldItem label={t("quantity")} ltr>{x.quantity} {x.unit}</FieldItem>
        <FieldItem label={t("accepted")} ltr>{x.accepted_qty ?? "—"} / {x.rejected_qty ?? "—"}</FieldItem>
        <FieldItem label={t("deliveryNote")} ltr>{x.delivery_note_no ?? "—"}</FieldItem>
        <FieldItem label={t("delivered")}>{dateTime(x.delivered_at)}</FieldItem>
        <FieldItem label={t("result")}>{x.result ? l("mir_result", x.result) : "—"}</FieldItem>
        {x.decision_comment ? <FieldItem label={t("comment")} wide><span dir="auto">{x.decision_comment}</span></FieldItem> : null}
      </FieldList></CardContent></Card>
      <Card className="mb-4" data-testid="q2-heat-panel"><CardContent className="grid gap-3 p-4 sm:grid-cols-2">
        <div><h3 className="mb-1 text-sm font-semibold">{t("tagHeats")}</h3><p className="ltr text-sm">{x.lot_numbers.map((h) => <span key={h} className={x.heat_mismatch.includes(h) ? "me-2 font-semibold text-danger" : "me-2"} data-mismatch={x.heat_mismatch.includes(h) ? "1" : "0"}>{h}</span>)}</p></div>
        <div><h3 className="mb-1 text-sm font-semibold">{t("certHeats")}</h3><p className="ltr text-sm">{x.cert_heat_numbers.join(" · ") || "—"}</p></div>
      </CardContent></Card>
      {x.tests.length ? <Card className="mb-4"><CardContent className="p-4"><h3 className="mb-2 text-sm font-semibold">{t("tests")}</h3>
        <ul className="text-sm">{x.tests.map((tt) => <li key={tt.id}><Link href={`/quality/tests/${tt.id}`} className="ltr text-primary hover:underline">{tt.test_no}</Link> · {tt.test_type_code} · <Q2Badge value={tt.verdict} label={l("test_verdict", tt.verdict)} /></li>)}</ul></CardContent></Card> : null}
      {x.quarantine_ids.length ? <Card className="mb-4"><CardContent className="p-4"><h3 className="mb-2 text-sm font-semibold">{t("quarantine")}</h3>
        <ul className="text-sm">{x.quarantine_ids.map((qid) => <li key={qid}><Link href={`/quality/quarantine/${qid}`} className="text-primary hover:underline" data-testid="q2-mir-quarantine-link">{t("openTag")}</Link></li>)}</ul></CardContent></Card> : null}
      <Card className="mb-4"><CardContent className="p-4"><h3 className="mb-2 text-sm font-semibold">{t("certificates")}</h3><Attachments ownerType="q_mir" ownerId={x.id} canUpload={x.status !== "decided" && x.status !== "cancelled"} /></CardContent></Card>
      <Signoffs recordType="mir" recordId={x.id} />
      <HistoryPanel entityType="q_mir" entityId={x.id} projectId={project.id} />
      {open ? (
        <Card className="mt-4" data-testid="q2-mir-decide-form"><CardContent className="grid gap-3 p-4 sm:grid-cols-4">
          <FormField id="mir-res" label={t("result")}><Select value={dec.result} onChange={(e) => setDec({ ...dec, result: e.target.value })} data-testid="mir-dec-result">{options("mir_result").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
          <FormField id="mir-acc" label={t("acceptedQty")}><Input value={dec.accepted_qty} onChange={(e) => setDec({ ...dec, accepted_qty: e.target.value })} dir="ltr" inputMode="decimal" data-testid="mir-dec-accepted" /></FormField>
          <FormField id="mir-rej" label={t("rejectedQty")}><Input value={dec.rejected_qty} onChange={(e) => setDec({ ...dec, rejected_qty: e.target.value })} dir="ltr" inputMode="decimal" data-testid="mir-dec-rejected" /></FormField>
          <FormField id="mir-com" label={tq("comment")} className="sm:col-span-4"><Textarea value={dec.comment} onChange={(e) => setDec({ ...dec, comment: e.target.value })} rows={2} data-testid="mir-dec-comment" /></FormField>
          <div className="flex gap-2 sm:col-span-4">
            <Button disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/mirs/{mir_id}/decide", { ...path, body: { result: dec.result as S["QMirResult"], accepted_qty: dec.accepted_qty, rejected_qty: dec.rejected_qty, comment: dec.comment || null } }))).then((o) => { if (o) setOpen(false); })} data-testid="mir-dec-confirm">{tq("confirm")}</Button>
            <Button variant="outline" onClick={() => setOpen(false)}>{tc("cancel")}</Button>
          </div>
        </CardContent></Card>
      ) : null}
    </div>
  );
}

/* ═════════════ quarantine `/quality/quarantine` (§C.3.3) ═════════════ */

export function QuarantineListPage() {
  return <QGate>{(p, st) => <ConstructionOnly profile={st.sector_profile}><Quarantine project={p} /></ConstructionOnly>}</QGate>;
}

function Quarantine({ project }: { project: Project }) {
  const t = useTranslations("quality.qtn");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const s = useSearchState();
  const { date } = useFormatters(project.id);
  const page = s.getInt("page", 1) ?? 1;
  const status = s.get("status") ?? "quarantined";
  const [search, setSearch] = useState(s.get("q") ?? "");
  const q = useDebounced(search, 300);
  const r = useQQuarantine(project.id, { status: (status || null) as S["QQuarantineStatus"] | null, q: q || null, page, page_size: PAGE_SIZE });
  const items = r.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <ListToolbar>
        <SearchFilter id="q2-qtn-q" value={search} onChange={(v) => { setSearch(v); s.set({ q: v, page: null }); }} />
        <SelectFilter id="q2-qtn-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={options("quarantine_status")} />
      </ListToolbar>
      {r.isLoading ? <LoadingState /> : r.isError ? <ErrorState error={r.error} onRetry={() => r.refetch()} /> : items.length ? (
        <>
          <Table compact data-testid="q2-qtn-table">
            <THead><TR><TH>{t("tag")}</TH><TH>{t("material")}</TH><TH>{t("quantity")}</TH><TH>{t("since")}</TH><TH>{t("age")}</TH><TH>{t("ncr")}</TH><TH>{tc("status")}</TH></TR></THead>
            <TBody>{items.map((x) => (
              <TR key={x.id} data-testid="q2-qtn-row" data-tag={x.tag_no} data-status={x.status}>
                <TD label={t("tag")}><Link href={`/quality/quarantine/${x.id}`} className="ltr font-medium text-primary hover:underline">{x.tag_no}</Link></TD>
                <TD label={t("material")} dir="auto">{x.material_description}</TD>
                <TD label={t("quantity")} className="ltr">{x.quantity} {x.unit}</TD>
                <TD label={t("since")}>{date(x.quarantined_on)}</TD>
                <TD label={t("age")} className={x.ageing ? "font-semibold text-danger" : ""}>{x.age_days ?? "—"}</TD>
                <TD label={t("ncr")} className="ltr">{x.ncr_id ? <Link href={`/quality/ncrs/${x.ncr_id}`} className="text-primary hover:underline">{x.ncr_no}</Link> : "—"}</TD>
                <TD label={tc("status")}><Q2Badge value={x.status} label={l("quarantine_status", x.status)} /></TD>
              </TR>
            ))}</TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={r.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : <EmptyState message={t("empty")} />}
    </div>
  );
}

export function QuarantineDetailPage({ id }: { id: string }) {
  return <QGate>{(p) => <QuarantineDetail project={p} id={id} />}</QGate>;
}

function QuarantineDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.qtn");
  const tq = useTranslations("quality.q2");
  const tc = useTranslations("common");
  const { l } = useQLabels();
  const { date, dateTime } = useFormatters(project.id);
  const q = useQQuarantineItem(id);
  const { run, busy, error } = useRun();
  const [to, setTo] = useState<"" | "released" | "returned" | "scrapped">("");
  const [note, setNote] = useState("");
  const [rn, setRn] = useState("");
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const x = q.data;
  if (!x) return null;
  const path = { params: { path: { item_id: x.id } } };
  return (
    <div data-testid="q2-qtn-detail" data-status={x.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/quarantine" }, { label: x.tag_no }]} />
      <div className="mb-4 rounded-md border-4 border-danger p-4" data-testid="q2-red-tag">
        <p className="text-xs font-semibold uppercase text-danger">{t("redTag")}</p>
        <p className="ltr text-2xl font-bold">{x.tag_no}</p>
        <p dir="auto">{x.material_description}</p>
        <p className="ltr">{x.quantity} {x.unit} · {date(x.quarantined_on)}</p>
        <Q2Badge value={x.status} label={l("quarantine_status", x.status)} testId="q2-qtn-status" />
      </div>
      <MutationError error={error} />
      {x.ageing ? <Alert tone="warning" className="mb-3">{t("ageing", { n: x.age_days ?? 0 })}</Alert> : null}
      <Card className="mb-4"><CardContent className="p-4"><FieldList>
        <FieldItem label={t("mir")} ltr>{x.mir_id ? <Link href={`/quality/material-inspections/${x.mir_id}`} className="text-primary hover:underline">{x.mir_no}</Link> : "—"}</FieldItem>
        <FieldItem label={t("ncr")} ltr>{x.ncr_id ? <Link href={`/quality/ncrs/${x.ncr_id}`} className="text-primary hover:underline">{x.ncr_no}</Link> : "—"}{x.ncr_status ? ` · ${l("ncr_status", x.ncr_status)}` : ""}</FieldItem>
        <FieldItem label={t("location")}>{[x.zone_code, x.location_ref].filter(Boolean).join(" · ") || "—"}</FieldItem>
        <FieldItem label={t("returnNote")} ltr>{x.return_note_no ?? "—"}</FieldItem>
        <FieldItem label={t("disposed")}>{dateTime(x.disposed_at)}</FieldItem>
      </FieldList></CardContent></Card>
      <Card className="mb-4"><CardContent className="p-4"><h3 className="mb-2 text-sm font-semibold">{t("evidence")}</h3><Attachments ownerType="q_quarantine" ownerId={x.id} canUpload={x.status === "quarantined"} /></CardContent></Card>
      {x.actions.includes("release") ? (
        <Card className="mb-4" data-testid="q2-qtn-dispose"><CardContent className="flex flex-wrap items-end gap-3 p-4">
          {(["released", "returned", "scrapped"] as const).map((k) => <Button key={k} variant={to === k ? "default" : "outline"} onClick={() => setTo(k)} data-testid={`q2-qtn-${k}`}>{l("quarantine_status", k)}</Button>)}
          {to === "returned" ? <FormField id="qtn-rn" label={t("returnNote")}><Input value={rn} onChange={(e) => setRn(e.target.value)} dir="ltr" data-testid="q2-qtn-return-note" /></FormField> : null}
          {to ? <FormField id="qtn-note" label={tq("comment")}><Input value={note} onChange={(e) => setNote(e.target.value)} /></FormField> : null}
          {to ? <Button disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/quarantine/{item_id}/dispose", { ...path, body: { to_status: to, return_note_no: rn || null, note: note || null } })))} data-testid="q2-qtn-confirm">{tq("confirm")}</Button> : null}
          {to ? <Button variant="outline" onClick={() => setTo("")}>{tc("cancel")}</Button> : null}
        </CardContent></Card>
      ) : null}
      <Signoffs recordType="quarantine" recordId={x.id} />
      <HistoryPanel entityType="q_quarantine" entityId={x.id} projectId={project.id} />
    </div>
  );
}
