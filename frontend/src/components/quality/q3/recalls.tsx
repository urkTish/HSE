"use client";
import { Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { PageHeader } from "@/components/common/page-header";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { useQ3Products, useQ3Recall, useQ3Recalls } from "@/lib/api/quality/q3";
import { useFormatters } from "@/lib/use-formatters";
import { ReasonDialog, StatusBadge, useQCaps, useQLabels, useRun } from "@/components/quality/q0/common";
import { Q3Gate, type Project, type S } from "./common";

export function RecallsListPage() {
  return <Q3Gate>{(p) => <Recalls project={p} />}</Q3Gate>;
}

function Recalls({ project }: { project: Project }) {
  const t = useTranslations("quality.logistics.rcl");
  const tc = useTranslations("quality.common");
  const { l } = useQLabels();
  const caps = useQCaps(project.id);
  const { dateTime } = useFormatters(project.id);
  const q = useQ3Recalls(project.id);
  const [adding, setAdding] = useState(false);
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} actions={caps.write("recall.manage") && !adding ? <Button onClick={() => setAdding(true)} data-testid="q3-recall-new"><Plus aria-hidden />{t("new")}</Button> : null} />
      {adding ? <RecallForm project={project} onDone={() => setAdding(false)} /> : null}
      {q.isLoading ? <LoadingState /> : (q.data ?? []).length ? (
        <Table compact data-testid="q3-recall-table">
          <THead><TR><TH>{t("no")}</TH><TH>{t("type")}</TH><TH>{t("batches")}</TH><TH>{t("initiated")}</TH><TH>{t("effectiveness")}</TH><TH>{t("traceTime")}</TH><TH>{tc("status")}</TH></TR></THead>
          <TBody>{(q.data ?? []).map((r) => (
            <TR key={r.id} data-testid="q3-recall-row" data-no={r.rcl_no}>
              <TD label={t("no")}><Link className="ltr font-medium text-primary hover:underline" href={`/quality/recalls/${r.id}`}>{r.rcl_no}</Link></TD>
              <TD label={t("type")}>{l("recall_type", r.recall_type)}</TD>
              <TD label={t("batches")} className="ltr">{r.batches.join(", ")}</TD>
              <TD label={t("initiated")}>{dateTime(r.initiated_at)}</TD>
              <TD label={t("effectiveness")}><span dir="ltr">{r.effectiveness_pct ?? "—"} %</span></TD>
              <TD label={t("traceTime")}><span dir="ltr">{r.trace_minutes !== null ? `${Math.floor(r.trace_minutes / 60)} h ${r.trace_minutes % 60} min` : "—"}</span></TD>
              <TD label={tc("status")}><StatusBadge kind="recall_status" value={r.status} /></TD>
            </TR>
          ))}</TBody>
        </Table>
      ) : <EmptyState message={t("empty")} />}
    </div>
  );
}

function RecallForm({ project, onDone }: { project: Project; onDone: () => void }) {
  const t = useTranslations("quality.logistics.rcl");
  const tc = useTranslations("quality.common");
  const { options } = useQLabels();
  const opts = useProjectOptions(project.id);
  const products = useQ3Products(project.id);
  const router = useRouter();
  const { run, busy, error } = useRun();
  const [type, setType] = useState("mock");
  const [cls, setCls] = useState("");
  const [product, setProduct] = useState("");
  const [batch, setBatch] = useState("");
  const [reason, setReason] = useState("");
  const [ext, setExt] = useState("");
  async function save() {
    const out = await run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/recalls", { params: { path: { project_id: project.id } }, body: { site_id: opts.sites[0]?.value, recall_type: type as S["QRecallType"], recall_class: (cls || null) as S["QRecallClass"] | null, items: [{ product_id: product, batch }], reason, external_ref: ext || null } as never })));
    if (out) { onDone(); router.push(`/quality/recalls/${out.id}`); }
  }
  return (
    <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-3" data-testid="q3-recall-form">
      <MutationError error={error} />
      {type !== "mock" ? <Alert tone="danger" className="sm:col-span-3">{t("realHint")}</Alert> : null}
      <FormField id="rc-type" label={t("type")}><Select id="rc-type" value={type} onChange={(e) => setType(e.target.value)} data-testid="rc-type">{options("recall_type").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <FormField id="rc-class" label={t("class")}><Select id="rc-class" value={cls} onChange={(e) => setCls(e.target.value)}><option value="">—</option>{options("recall_class").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <FormField id="rc-ext" label={t("externalRef")}><Input id="rc-ext" value={ext} onChange={(e) => setExt(e.target.value)} dir="ltr" /></FormField>
      <FormField id="rc-prod" label={t("product")}><Select id="rc-prod" value={product} onChange={(e) => setProduct(e.target.value)} data-testid="rc-product"><option value="">{tc("select")}</option>{(products.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.sku}</option>)}</Select></FormField>
      <FormField id="rc-batch" label={t("batch")}><Input id="rc-batch" value={batch} onChange={(e) => setBatch(e.target.value)} dir="ltr" data-testid="rc-batch" /></FormField>
      <FormField id="rc-reason" label={tc("reason")} className="sm:col-span-3"><Textarea id="rc-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} data-testid="rc-reason" /></FormField>
      <div className="flex gap-2 sm:col-span-3"><Button disabled={busy || !product || !batch || reason.trim().length < 10} onClick={() => void save()} data-testid="rc-save">{t("open")}</Button><Button variant="outline" onClick={onDone}>{tc("cancel")}</Button></div>
    </CardContent></Card>
  );
}

export function RecallDetailPage({ id }: { id: string }) {
  return <Q3Gate>{(p) => <RecallDetail project={p} id={id} />}</Q3Gate>;
}

function RecallDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.logistics.rcl");
  const tc = useTranslations("quality.common");
  const { l } = useQLabels();
  const caps = useQCaps(project.id);
  const { dateTime } = useFormatters(project.id);
  const q = useQ3Recall(id);
  const { run, busy, error } = useRun();
  const [cancel, setCancel] = useState(false);
  const [just, setJust] = useState("");
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const r = q.data;
  if (!r) return null;
  const tr = r.trace as Record<string, string | boolean | null | Record<string, unknown>[]>;
  const manage = caps.write("recall.manage");
  const below = r.effectiveness_pct !== null && Number(r.effectiveness_pct) < Number(r.effectiveness_target_pct);
  return (
    <div data-testid="q3-recall-detail" data-status={r.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/recalls" }, { label: r.rcl_no }]} />
      <PageHeader title={<span className="ltr">{r.rcl_no}</span>} badge={<><Badge tone={r.recall_type === "mock" ? "info" : "danger"}>{l("recall_type", r.recall_type)}</Badge> <StatusBadge kind="recall_status" value={r.status} /></>} />
      <MutationError error={error} />
      {r.warnings.map((w, i) => <Alert key={i} tone="warning" className="mb-2">{String(w.message)}</Alert>)}
      <Card className="mb-4"><CardContent className="p-4">
        <FieldList>
          <FieldItem label={t("batches")} ltr>{r.items.map((i) => `${i.sku} ${i.batch}`).join(", ")}</FieldItem>
          <FieldItem label={t("initiated")}>{dateTime(r.initiated_at)}</FieldItem>
          <FieldItem label={t("traceCompleted")}>{dateTime(r.trace_completed_at)}</FieldItem>
          <FieldItem label={t("traceTime")}><span dir="ltr" className={r.trace_slow ? "text-danger" : ""}>{r.trace_minutes !== null ? `${Math.floor(r.trace_minutes / 60)} h ${r.trace_minutes % 60} min` : "—"} / {r.trace_target_hours} h</span></FieldItem>
          <FieldItem label={t("effectiveness")}><span dir="ltr" data-testid="q3-recall-eff" className={below ? "text-danger" : ""}>{r.effectiveness_pct ?? "—"} % / {r.effectiveness_target_pct} %</span></FieldItem>
          <FieldItem label={t("hold")}>{r.hold_id ? <Link className="text-primary hover:underline" href={`/quality/holds/${r.hold_id}`}>{t("openHold")}</Link> : "—"}</FieldItem>
          <FieldItem label={t("ncr")}>{r.ncr_id ? <Link className="text-primary hover:underline" href={`/quality/ncrs/${r.ncr_id}`}>{t("openNcr")}</Link> : "—"}</FieldItem>
        </FieldList>
      </CardContent></Card>
      <Card className="mb-4"><CardContent className="p-4" data-testid="q3-trace">
        <h2 className="mb-2 text-base font-semibold">{t("trace")}</h2>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {(["received", "on_hand", "shipped", "destroyed", "unaccounted"] as const).map((k) => (
            <div key={k} className="rounded-md border p-2" data-testid={`trace-${k}`}><p className="text-xs text-muted-foreground">{t(`t.${k}`)}</p><p className="font-semibold tabular-nums" dir="ltr">{Number(tr[k] ?? 0).toLocaleString("en")}</p></div>
          ))}
        </div>
        <Table compact className="mt-3">
          <THead><TR><TH>{t("consignee")}</TH><TH>{t("qty")}</TH><TH>{t("shipments")}</TH></TR></THead>
          <TBody>{((tr.consignees as Record<string, unknown>[]) ?? []).map((c, i) => <TR key={i}><TD>{String(c.name)}</TD><TD><span dir="ltr">{Number(c.qty).toLocaleString("en")}</span></TD><TD><span dir="ltr">{String(c.shipments)}</span></TD></TR>)}</TBody>
        </Table>
        {r.status === "open" && manage ? <Button className="mt-3" disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/recalls/{recall_id}/trace", { params: { path: { recall_id: id } }, body: {} })))} data-testid="q3-trace-confirm">{t("confirmTrace")}</Button> : null}
        {r.status === "traced" && r.recall_type !== "mock" && manage ? <Button className="ms-2 mt-3" disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/recalls/{recall_id}/recover", { params: { path: { recall_id: id } } })))} data-testid="q3-recover">{t("recover")}</Button> : null}
      </CardContent></Card>
      {r.consignee_contacts.length ? (
        <Card className="mb-4"><CardContent className="p-4">
          <h2 className="mb-2 text-base font-semibold">{t("contacts")}</h2>
          <Table compact>
            <THead><TR><TH>{t("consignee")}</TH><TH>{t("qty")}</TH><TH>{t("retrieved")}</TH><TH>{t("destroyedByConsignee")}</TH></TR></THead>
            <TBody>{r.consignee_contacts.map((c) => <ContactRow key={String(c.id)} c={c} editable={manage && (r.status === "traced" || r.status === "recovering")} />)}</TBody>
          </Table>
        </CardContent></Card>
      ) : null}
      {r.can_close ? (
        <Card className="mb-4"><CardContent className="grid gap-2 p-4">
          {below ? <FormField id="rc-just" label={t("justification")} hint={tc("minChars", { n: 50 })}><Textarea id="rc-just" rows={3} value={just} onChange={(e) => setJust(e.target.value)} /></FormField> : null}
          <div className="flex gap-2">
            {(r.status === "recovering" || (r.status === "traced" && r.recall_type === "mock")) ? <Button disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/recalls/{recall_id}/close", { params: { path: { recall_id: id } }, body: { justification: just || null } })))} data-testid="q3-recall-close">{t("close")}</Button> : null}
            <Button variant="outline" onClick={() => setCancel(true)}>{t("cancel")}</Button>
          </div>
        </CardContent></Card>
      ) : null}
      <ReasonDialog open={cancel} onOpenChange={setCancel} title={t("cancel")} confirm={t("cancel")} onSubmit={(text) => run(() => unwrap(api.POST("/api/v1/quality/recalls/{recall_id}/cancel", { params: { path: { recall_id: id } }, body: { reason: text } })))} />
    </div>
  );
}

function ContactRow({ c, editable }: { c: Record<string, unknown>; editable: boolean }) {
  const t = useTranslations("quality.logistics.rcl");
  const { run, busy } = useRun();
  const [ret, setRet] = useState(String(c.qty_retrieved ?? "0"));
  const [des, setDes] = useState(String(c.qty_destroyed_by_consignee ?? "0"));
  return (
    <TR>
      <TD label={t("consignee")}>{String(c.consignee_name)}</TD>
      <TD label={t("qty")}><span dir="ltr">{String(c.qty_shipped)}</span></TD>
      <TD label={t("retrieved")}>{editable ? <Input value={ret} onChange={(e) => setRet(e.target.value)} dir="ltr" className="w-24" /> : <span dir="ltr">{String(c.qty_retrieved)}</span>}</TD>
      <TD label={t("destroyedByConsignee")}>{editable ? <div className="flex gap-1"><Input value={des} onChange={(e) => setDes(e.target.value)} dir="ltr" className="w-24" /><Button size="sm" variant="outline" disabled={busy} onClick={() => void run(() => unwrap(api.PATCH("/api/v1/quality/recall-contacts/{item_id}", { params: { path: { item_id: String(c.id) } }, body: { qty_retrieved: ret, qty_destroyed_by_consignee: des, contacted_at: new Date().toISOString() } as never })))}>{t("save")}</Button></div> : <span dir="ltr">{String(c.qty_destroyed_by_consignee)}</span>}</TD>
    </TR>
  );
}
