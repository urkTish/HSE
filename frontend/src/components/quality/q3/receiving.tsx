"use client";
import { Plus } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { useAttachments } from "@/lib/api/hse";
import { useQCustomers, useQMte } from "@/lib/api/quality/q0";
import { useQ3Products, useQ3Receipt, useQ3Receipts } from "@/lib/api/quality/q3";
import { useDebounced } from "@/lib/use-debounced";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { StatusBadge, useBilingual, useQCaps, useQLabels, useRun } from "@/components/quality/q0/common";
import { ChecklistRunner, DecisionBadge, Q3Gate, Temp, clean, fromLocalInput, nowLocal, useForm, type Project, type S } from "./common";

const PAGE_SIZE = 50;

export function ReceivingListPage() {
  return <Q3Gate>{(p) => <ReceivingList project={p} />}</Q3Gate>;
}

function ReceivingList({ project }: { project: Project }) {
  const t = useTranslations("quality.logistics.rcv");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const caps = useQCaps(project.id);
  const s = useSearchState();
  const { dateTime } = useFormatters(project.id);
  const page = s.getInt("page", 1) ?? 1;
  const status = s.get("status") ?? "";
  const decision = s.get("decision") ?? "";
  const customer = s.get("customer") ?? "";
  const [search, setSearch] = useState(s.get("q") ?? "");
  const q = useDebounced(search, 300);
  const customers = useQCustomers(project.id);
  const r = useQ3Receipts(project.id, {
    status: (status || null) as S["QReceiptStatus"] | null,
    decision: (decision || null) as S["QLineDecision"] | null,
    customer_id: customer || null,
    q: q || null,
    page,
    page_size: PAGE_SIZE,
  });
  const items = r.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.write("receiving.record") ? (
            <Button asChild data-testid="q3-rcv-new">
              <Link href="/quality/receiving/new">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <ListToolbar>
        <SearchFilter id="q3-rcv-q" value={search} onChange={(v) => { setSearch(v); s.set({ q: v, page: null }); }} />
        <SelectFilter id="q3-rcv-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={options("receipt_status")} />
        <SelectFilter id="q3-rcv-decision" label={t("decision")} value={decision} onChange={(v) => s.set({ decision: v, page: null })} options={options("line_decision")} />
        <SelectFilter id="q3-rcv-owner" label={t("owner")} value={customer} onChange={(v) => s.set({ customer: v, page: null })} options={(customers.data ?? []).filter((c) => c.kind === "depositor").map((c) => ({ value: c.id, label: c.code }))} />
      </ListToolbar>
      {r.isLoading ? <LoadingState /> : r.isError ? <ErrorState error={r.error} onRetry={() => r.refetch()} /> : items.length ? (
        <>
          <Table compact data-testid="q3-rcv-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH><TH>{t("owner")}</TH><TH>{t("arrived")}</TH><TH>{t("asn")}</TH><TH>{t("decisions")}</TH><TH>{t("dwell")}</TH><TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((x) => (
                <TR key={x.id} data-testid="q3-rcv-row" data-no={x.rcv_no ?? ""}>
                  <TD label={t("no")}><Link href={`/quality/receiving/${x.id}`} className="ltr font-medium text-primary hover:underline">{x.rcv_no ?? t("draft")}</Link></TD>
                  <TD label={t("owner")}>{x.customer?.code ?? "—"}</TD>
                  <TD label={t("arrived")}>{dateTime(x.arrived_at)}</TD>
                  <TD label={t("asn")} className="ltr text-xs">{x.asn_ref ?? "—"}</TD>
                  <TD label={t("decisions")}>
                    <div className="flex flex-wrap gap-1">
                      {x.decisions.map((d) => <DecisionBadge key={d} value={d} label={l("line_decision", d)} />)}
                      {x.pending_signoff ? <Badge tone="warning">{t("pendingSignoff")}</Badge> : null}
                      {x.seal_flag ? <Badge tone="danger">{t("sealFlag")}</Badge> : null}
                    </div>
                  </TD>
                  <TD label={t("dwell")} className={x.dwell_long ? "font-medium text-danger" : ""}><span dir="ltr">{x.dwell_minutes ?? "—"}</span></TD>
                  <TD label={tc("status")}><StatusBadge kind="receipt_status" value={x.status} /></TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={r.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : <EmptyState message={t("empty")} />}
    </div>
  );
}

// ---- new receipt (dock flow step 1) -----------------------------------------------------------------

export function ReceiptNewPage() {
  return <Q3Gate>{(p) => <ReceiptNew project={p} />}</Q3Gate>;
}

function ReceiptNew({ project }: { project: Project }) {
  const t = useTranslations("quality.logistics.rcv");
  const tc = useTranslations("quality.common");
  const opts = useProjectOptions(project.id);
  const customers = useQCustomers(project.id);
  const router = useRouter();
  const { run, busy, error } = useRun();
  const [f, set] = useForm({ site_id: "", dock_zone_id: "", customer_id: "", po_ref: "", asn_ref: "", vehicle_plate: "", reefer_display_c: "", seal_expected: "", seal_actual: "", arrived_at: nowLocal(), unload_start: "", unload_end: "" });
  const [sealIntact, setSealIntact] = useState(true);
  const site = f.site_id || opts.sites[0]?.value || "";
  const zones = opts.zones.filter((z) => z.siteId === site);
  async function save() {
    const b = clean(f) as Record<string, unknown>;
    b.site_id = site;
    for (const k of ["arrived_at", "unload_start", "unload_end"]) b[k] = fromLocalInput(f[k as keyof typeof f]);
    b.seal_intact = sealIntact;
    const out = await run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/receipts", { params: { path: { project_id: project.id } }, body: b as unknown as S["Q3ReceiptCreate"] })));
    if (out) router.push(`/quality/receiving/${out.id}`);
  }
  return (
    <div>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/receiving" }, { label: t("new") }]} />
      <PageHeader title={t("new")} description={t("newHint")} />
      <Card><CardContent className="grid gap-3 p-4 sm:grid-cols-3" data-testid="q3-rcv-form">
        <MutationError error={error} />
        <FormField id="rcv-site" label={t("site")} required><Select id="rcv-site" value={site} onChange={set("site_id")}>{opts.sites.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
        <FormField id="rcv-dock" label={t("dock")} required><Select id="rcv-dock" value={f.dock_zone_id} onChange={set("dock_zone_id")} data-testid="rcv-dock"><option value="">{tc("select")}</option>{zones.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
        <FormField id="rcv-owner" label={t("owner")} required><Select id="rcv-owner" value={f.customer_id} onChange={set("customer_id")} data-testid="rcv-owner"><option value="">{tc("select")}</option>{(customers.data ?? []).filter((c) => c.kind === "depositor").map((c) => <option key={c.id} value={c.id}>{c.code}</option>)}</Select></FormField>
        <FormField id="rcv-po" label={t("po")}><Input id="rcv-po" value={f.po_ref} onChange={set("po_ref")} dir="ltr" /></FormField>
        <FormField id="rcv-asn" label={t("asn")}><Input id="rcv-asn" value={f.asn_ref} onChange={set("asn_ref")} dir="ltr" data-testid="rcv-asn" /></FormField>
        <FormField id="rcv-plate" label={t("plate")}><Input id="rcv-plate" value={f.vehicle_plate} onChange={set("vehicle_plate")} dir="ltr" /></FormField>
        <FormField id="rcv-reefer" label={t("reefer")}><Input id="rcv-reefer" value={f.reefer_display_c} onChange={set("reefer_display_c")} dir="ltr" inputMode="decimal" /></FormField>
        <FormField id="rcv-seal-e" label={t("sealExpected")}><Input id="rcv-seal-e" value={f.seal_expected} onChange={set("seal_expected")} dir="ltr" /></FormField>
        <FormField id="rcv-seal-a" label={t("sealActual")}><Input id="rcv-seal-a" value={f.seal_actual} onChange={set("seal_actual")} dir="ltr" /></FormField>
        <label className="flex min-h-touch items-center gap-2 text-sm"><Checkbox checked={sealIntact} onChange={(e) => setSealIntact(e.target.checked)} />{t("sealIntact")}</label>
        <FormField id="rcv-arr" label={t("arrived")} required><Input id="rcv-arr" type="datetime-local" value={f.arrived_at} onChange={set("arrived_at")} dir="ltr" /></FormField>
        <FormField id="rcv-us" label={t("unloadStart")}><Input id="rcv-us" type="datetime-local" value={f.unload_start} onChange={set("unload_start")} dir="ltr" data-testid="rcv-unload-start" /></FormField>
        <FormField id="rcv-ue" label={t("unloadEnd")}><Input id="rcv-ue" type="datetime-local" value={f.unload_end} onChange={set("unload_end")} dir="ltr" data-testid="rcv-unload-end" /></FormField>
        <div className="flex gap-2 sm:col-span-3">
          <Button disabled={busy || !f.dock_zone_id || !f.customer_id} onClick={() => void save()} data-testid="rcv-save">{t("start")}</Button>
          <Button variant="outline" asChild><Link href="/quality/receiving">{tc("cancel")}</Link></Button>
        </div>
      </CardContent></Card>
    </div>
  );
}

// ---- receipt detail (dock flow: vehicle check, lines, decisions) --------------------------------------

export function ReceiptDetailPage({ id }: { id: string }) {
  return <Q3Gate>{(p) => <ReceiptDetail project={p} id={id} />}</Q3Gate>;
}

function ReceiptDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.logistics.rcv");
  const { l } = useQLabels();
  const caps = useQCaps(project.id);
  const { dateTime } = useFormatters(project.id);
  const q = useQ3Receipt(id);
  const { run, busy, error } = useRun();
  const [adding, setAdding] = useState(false);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const r = q.data;
  if (!r) return null;
  const editable = r.status === "draft" || r.status === "inspected";
  const rec = caps.write("receiving.record");
  return (
    <div data-testid="q3-rcv-detail" data-status={r.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/receiving" }, { label: r.rcv_no ?? t("draft") }]} />
      <PageHeader title={<span className="ltr">{r.rcv_no ?? t("draft")}</span>} badge={<StatusBadge kind="receipt_status" value={r.status} />}
        actions={r.status === "draft" && rec ? <Button disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/receipts/{receipt_id}/inspect", { params: { path: { receipt_id: id } } })))} data-testid="q3-rcv-inspect">{t("inspect")}</Button> : null} />
      <MutationError error={error} />
      {r.seal_flag ? <Alert tone="danger" className="mb-3">{t("sealFlagHint")}</Alert> : null}
      <Card className="mb-4"><CardContent className="p-4">
        <FieldList>
          <FieldItem label={t("owner")}>{r.customer?.code ?? "—"}</FieldItem>
          <FieldItem label={t("supplier")}>{r.supplier?.code ?? "—"}</FieldItem>
          <FieldItem label={t("carrier")}>{r.carrier?.code ?? "—"}</FieldItem>
          <FieldItem label={t("dock")}>{r.dock_zone?.code ?? "—"}</FieldItem>
          <FieldItem label={t("asn")} ltr>{r.asn_ref ?? "—"}</FieldItem>
          <FieldItem label={t("po")} ltr>{r.po_ref ?? "—"}</FieldItem>
          <FieldItem label={t("arrived")}>{dateTime(r.arrived_at)}</FieldItem>
          <FieldItem label={t("dwell")}><span className={r.dwell_minutes && r.dwell_minutes > r.dwell_limit_minutes ? "font-medium text-danger" : ""} dir="ltr">{r.dwell_minutes ?? "—"} / {r.dwell_limit_minutes} min</span></FieldItem>
          <FieldItem label={t("reefer")}><Temp v={r.reefer_display_c} /></FieldItem>
          <FieldItem label={t("seal")} ltr>{[r.seal_expected, r.seal_actual].filter(Boolean).join(" / ") || "—"}</FieldItem>
        </FieldList>
      </CardContent></Card>
      <Card className="mb-4"><CardContent className="p-4">
        <h2 className="mb-2 text-base font-semibold">{t("vehicleCheck")}</h2>
        {r.vehicle_check ? (
          <p className="text-sm" data-testid="q3-rcv-vehicle-done">
            <span className="ltr">{r.vehicle_check.template_code}</span> · <span dir="ltr">{r.vehicle_check.score_pct ?? "—"} %</span> ·{" "}
            <Badge tone={r.vehicle_check.result === "pass" ? "success" : "danger"}>{r.vehicle_check.result === "pass" ? t("checkPass") : t("checkFail")}</Badge>
          </p>
        ) : editable && rec ? (
          <ChecklistRunner code="QRCV" submitLabel={t("saveCheck")} busy={busy} onSubmit={(a) => void run(() => unwrap(api.POST("/api/v1/quality/receipts/{receipt_id}/vehicle-check", { params: { path: { receipt_id: id } }, body: { answers: a } as never })))} />
        ) : <p className="text-sm text-muted-foreground">—</p>}
      </CardContent></Card>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-base font-semibold">{t("lines")}</h2>
        {editable && rec && !adding ? <Button size="sm" onClick={() => setAdding(true)} data-testid="q3-rcv-add-line"><Plus aria-hidden />{t("addLine")}</Button> : null}
      </div>
      {adding ? <LineForm project={project} receipt={r} onDone={() => setAdding(false)} /> : null}
      <div className="grid gap-3">
        {r.lines.map((ln) => <LineCard key={ln.id} project={project} receipt={r} line={ln} />)}
        {!r.lines.length ? <EmptyState message={t("noLines")} /> : null}
      </div>
      <Card className="mt-4"><CardContent className="p-4">
        <h2 className="mb-2 text-base font-semibold">{t("files")}</h2>
        <Attachments ownerType="q_receipt" ownerId={id} canUpload={editable && rec} hint={t("filesHint")} />
      </CardContent></Card>
      {r.signoffs.length ? (
        <Card className="mt-4"><CardContent className="p-4">
          <h2 className="mb-2 text-base font-semibold">{t("signoffs")}</h2>
          <ul className="text-sm">{r.signoffs.map((x) => <li key={x.id} data-testid="q3-signoff">{x.step} · {x.decision} · {x.text_en} · {dateTime(x.signed_at)}</li>)}</ul>
        </CardContent></Card>
      ) : null}
    </div>
  );
}

function LineForm({ project, receipt, onDone }: { project: Project; receipt: S["Q3ReceiptRead"]; onDone: () => void }) {
  const t = useTranslations("quality.logistics.rcv");
  const tc = useTranslations("quality.common");
  const name = useBilingual();
  const { options } = useQLabels();
  const products = useQ3Products(project.id, { owner_id: receipt.customer?.id ?? null });
  const mte = useQMte(project.id, { page_size: 200 });
  const { run, busy, error } = useRun();
  const [f, set] = useForm({ product_id: "", batch: "", expiry_date: "", qty_expected: "", qty_received: "", product_temp_c: "", mte_id: "", condition: "good" });
  const [labels, setLabels] = useState(true);
  async function save() {
    const b = clean(f) as Record<string, unknown>;
    b.labels_ok = labels;
    const out = await run(() => unwrap(api.POST("/api/v1/quality/receipts/{receipt_id}/lines", { params: { path: { receipt_id: receipt.id } }, body: b as never })));
    if (out) onDone();
  }
  return (
    <Card className="mb-3"><CardContent className="grid gap-3 p-4 sm:grid-cols-4" data-testid="q3-line-form">
      <MutationError error={error} />
      <FormField id="ln-prod" label={t("product")} required className="sm:col-span-2"><Select id="ln-prod" value={f.product_id} onChange={set("product_id")} data-testid="ln-product"><option value="">{tc("select")}</option>{(products.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.sku} — {name(p.description_en, p.description_ar)}</option>)}</Select></FormField>
      <FormField id="ln-batch" label={t("batch")} required><Input id="ln-batch" value={f.batch} onChange={set("batch")} dir="ltr" data-testid="ln-batch" /></FormField>
      <FormField id="ln-exp" label={t("expiry")}><Input id="ln-exp" type="date" value={f.expiry_date} onChange={set("expiry_date")} dir="ltr" data-testid="ln-expiry" /></FormField>
      <FormField id="ln-qe" label={t("qtyAsn")}><Input id="ln-qe" value={f.qty_expected} onChange={set("qty_expected")} dir="ltr" inputMode="decimal" /></FormField>
      <FormField id="ln-qr" label={t("qtyReceived")} required><Input id="ln-qr" value={f.qty_received} onChange={set("qty_received")} dir="ltr" inputMode="decimal" data-testid="ln-qty" /></FormField>
      <FormField id="ln-temp" label={t("productTemp")}><Input id="ln-temp" value={f.product_temp_c} onChange={set("product_temp_c")} dir="ltr" inputMode="decimal" data-testid="ln-temp" /></FormField>
      <FormField id="ln-mte" label={t("probe")}><Select id="ln-mte" value={f.mte_id} onChange={set("mte_id")} data-testid="ln-mte"><option value="">—</option>{(mte.data?.items ?? []).filter((m) => m.mte_type === "temp_probe" || m.mte_type === "thermometer").map((m) => <option key={m.id} value={m.id}>{m.mte_no} · {m.description}</option>)}</Select></FormField>
      <FormField id="ln-cond" label={t("condition")}><Select id="ln-cond" value={f.condition} onChange={set("condition")} data-testid="ln-condition">{options("line_condition").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <label className="flex min-h-touch items-center gap-2 text-sm"><Checkbox checked={labels} onChange={(e) => setLabels(e.target.checked)} />{t("labelsOk")}</label>
      <div className="flex gap-2 sm:col-span-4">
        <Button disabled={busy || !f.product_id || !f.batch || !f.qty_received} onClick={() => void save()} data-testid="ln-save">{tc("save")}</Button>
        <Button variant="outline" onClick={onDone}>{tc("cancel")}</Button>
      </div>
    </CardContent></Card>
  );
}

function LineCard({ project, receipt, line }: { project: Project; receipt: S["Q3ReceiptRead"]; line: S["Q3ReceiptLineRead"] }) {
  const t = useTranslations("quality.logistics.rcv");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const name = useBilingual();
  const ar = useLocale() === "ar";
  const caps = useQCaps(project.id);
  const { run, busy, error } = useRun();
  const [deciding, setDeciding] = useState(false);
  const [f, set] = useForm({ decision: line.proposed_decision ?? "accept", reason: "", claim_ref: "", owner_approval_attachment_id: "" });
  const [raiseNcr, setRaiseNcr] = useState(false);
  const resolves = receipt.my_steps.length > 0;
  async function decide(request: boolean) {
    const b: Record<string, unknown> = { ...clean(f), raise_ncr: raiseNcr, request };
    const out = await run(() => unwrap(api.POST("/api/v1/quality/receipt-lines/{line_id}/decide", { params: { path: { line_id: line.id } }, body: b as never })));
    if (out) setDeciding(false);
  }
  async function sign() {
    await run(() => unwrap(api.POST("/api/v1/quality/receipt-lines/{line_id}/decide", { params: { path: { line_id: line.id } }, body: {} as never })));
  }
  const canDecide = receipt.status === "inspected" && !line.decision && (caps.write("receiving.record") || caps.write("receiving.decide"));
  return (
    <Card data-testid="q3-line" data-line={line.line_no} data-proposed={line.proposed_decision ?? ""} data-decision={line.decision ?? ""}>
      <CardContent className="p-4">
        <MutationError error={error} />
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="font-medium"><span className="ltr">{line.product?.sku}</span> — {line.product ? name(line.product.description_en, line.product.description_ar) : ""}</p>
            <p className="text-sm text-muted-foreground"><span className="ltr">{line.batch}</span> · {t("expiry")} <span className="ltr">{line.expiry_date ?? "—"}</span> · <span dir="ltr">{line.qty_received} {line.unit}</span></p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground">{t("proposed")}</span>
            <DecisionBadge value={line.proposed_decision} label={l("line_decision", line.proposed_decision)} />
            {line.decision ? <><span className="text-xs text-muted-foreground">{t("decided")}</span><DecisionBadge value={line.decision} label={l("line_decision", line.decision)} /></> : null}
          </div>
        </div>
        <FieldList className="mt-2">
          <FieldItem label={t("productTemp")}><Temp v={line.product_temp_c} /></FieldItem>
          <FieldItem label={t("probe")} ltr>{line.mte?.mte_no ?? "—"}</FieldItem>
          <FieldItem label={t("rsl")}><span dir="ltr">{line.remaining_shelf_life_pct ?? "—"} %</span></FieldItem>
          <FieldItem label={t("condition")}>{l("line_condition", line.condition)}</FieldItem>
          <FieldItem label={t("sampleHint")}><span dir="ltr">{line.sample_hint ?? "—"}</span></FieldItem>
        </FieldList>
        {line.proposal_reasons.length ? (
          <ul className="mt-2 list-disc ps-5 text-sm" data-testid="q3-line-reasons">
            {line.proposal_reasons.map((x, i) => <li key={i}>{String(ar ? x.ar : x.en)}</li>)}
          </ul>
        ) : null}
        {line.requested_decision ? (
          <Alert tone="warning" className="mt-2">
            {t("requested", { d: l("line_decision", line.requested_decision) })}
            {resolves ? <Button size="sm" className="ms-2" disabled={busy} onClick={() => void sign()} data-testid="q3-line-sign">{t("sign")}</Button> : null}
          </Alert>
        ) : null}
        {line.hold_id ? <p className="mt-2 text-sm"><Link className="text-primary hover:underline" href={`/quality/holds/${line.hold_id}`}>{t("openHold")}</Link></p> : null}
        {line.ncr_id ? <p className="mt-1 text-sm"><Link className="text-primary hover:underline" href={`/quality/ncrs/${line.ncr_id}`}>{t("openNcr")}</Link></p> : null}
        {canDecide && !line.requested_decision ? (
          deciding ? (
            <div className="mt-3 grid gap-3 sm:grid-cols-3" data-testid="q3-line-decide-form">
              <FormField id={`dec-${line.id}`} label={t("decision")}><Select id={`dec-${line.id}`} value={f.decision} onChange={set("decision")} data-testid="dec-decision">{options("line_decision").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
              <FormField id={`rsn-${line.id}`} label={tc("reason")} className="sm:col-span-2"><Textarea id={`rsn-${line.id}`} rows={2} value={f.reason} onChange={set("reason")} data-testid="dec-reason" /></FormField>
              {f.decision === "reject" ? (
                <>
                  <FormField id={`clm-${line.id}`} label={t("claim")}><Input id={`clm-${line.id}`} value={f.claim_ref} onChange={set("claim_ref")} dir="ltr" /></FormField>
                  <label className="flex min-h-touch items-center gap-2 text-sm"><Checkbox checked={raiseNcr} onChange={(e) => setRaiseNcr(e.target.checked)} data-testid="dec-raise-ncr" />{t("raiseNcr")}</label>
                </>
              ) : null}
              {f.decision === "accept_with_deviation" && receipt.customer?.owner_release_approval ? (
                <FormField id={`own-${line.id}`} label={t("ownerApproval")}>
                  <OwnerFile receiptId={receipt.id} value={f.owner_approval_attachment_id} onChange={(v) => set("owner_approval_attachment_id")({ target: { value: v } })} />
                </FormField>
              ) : null}
              <div className="flex flex-wrap gap-2 sm:col-span-3">
                <Button disabled={busy} onClick={() => void decide(false)} data-testid="dec-save">{resolves ? t("decideSign") : t("decide")}</Button>
                {!resolves ? <Button variant="outline" disabled={busy} onClick={() => void decide(true)} data-testid="dec-request">{t("requestSignoff")}</Button> : null}
                <Button variant="ghost" onClick={() => setDeciding(false)}>{tc("cancel")}</Button>
              </div>
            </div>
          ) : (
            <Button size="sm" className="mt-3" onClick={() => setDeciding(true)} data-testid="q3-line-decide">{t("decide")}</Button>
          )
        ) : null}
      </CardContent>
    </Card>
  );
}

function OwnerFile({ receiptId, value, onChange }: { receiptId: string; value: string; onChange: (v: string) => void }) {
  const t = useTranslations("quality.logistics.common");
  const files = useAttachmentsList(receiptId);
  return (
    <Select value={value} onChange={(e) => onChange(e.target.value)} data-testid="dec-owner-file">
      <option value="">{t("noFile")}</option>
      {files.map((a) => <option key={a.id} value={a.id}>{a.file_name}</option>)}
    </Select>
  );
}

function useAttachmentsList(receiptId: string) {
  return useAttachments("q_receipt", receiptId).data?.items ?? [];
}
