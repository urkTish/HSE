"use client";
import { Download, Plus } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Link, useRouter } from "@/i18n/navigation";
import { api, downloadFile, unwrap } from "@/lib/api/client";
import { useQ3Hold, useQ3Holds, useQ3Products } from "@/lib/api/quality/q3";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { ReasonDialog, StatusBadge, useBilingual, useQCaps, useQLabels, useRun } from "@/components/quality/q0/common";
import { AttachmentPick, Q3Gate, useForm, type Project, type S } from "./common";

const PAGE_SIZE = 50;

export function HoldsListPage() {
  return <Q3Gate>{(p) => <HoldsList project={p} />}</Q3Gate>;
}

function HoldsList({ project }: { project: Project }) {
  const t = useTranslations("quality.logistics.hld");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const caps = useQCaps(project.id);
  const s = useSearchState();
  const { dateTime } = useFormatters(project.id);
  const page = s.getInt("page", 1) ?? 1;
  const status = s.get("status") ?? "";
  const reason = s.get("reason") ?? "";
  const [adding, setAdding] = useState(false);
  const r = useQ3Holds(project.id, { status: status ? [status as S["QHoldStatus"]] : null, reason: (reason || null) as S["QHoldReason"] | null, page, page_size: PAGE_SIZE });
  const items = r.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")}
        actions={<div className="flex gap-2">
          {caps.has("export.quality") ? <Button variant="outline" onClick={() => void downloadFile(`/api/v1/projects/${project.id}/quality/holds/export.csv`, "holds.csv")} data-testid="q3-hold-export"><Download aria-hidden />{t("wmsExport")}</Button> : null}
          {caps.write("hold.manage") && !adding ? <Button onClick={() => setAdding(true)} data-testid="q3-hold-new"><Plus aria-hidden />{t("new")}</Button> : null}
        </div>} />
      {adding ? <HoldForm project={project} onDone={() => setAdding(false)} /> : null}
      <ListToolbar>
        <SelectFilter id="q3-hold-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={options("hold_status")} />
        <SelectFilter id="q3-hold-reason" label={t("reason")} value={reason} onChange={(v) => s.set({ reason: v, page: null })} options={options("hold_reason")} />
      </ListToolbar>
      {r.isLoading ? <LoadingState /> : r.isError ? <ErrorState error={r.error} onRetry={() => r.refetch()} /> : items.length ? (
        <>
          <Table compact data-testid="q3-hold-table">
            <THead><TR><TH>{t("no")}</TH><TH>{t("reason")}</TH><TH>{t("placed")}</TH><TH>{t("age")}</TH><TH>{t("lines")}</TH><TH>{t("flags")}</TH><TH>{tc("status")}</TH></TR></THead>
            <TBody>{items.map((h) => (
              <TR key={h.id} data-testid="q3-hold-row" data-no={h.hold_no}>
                <TD label={t("no")}><Link href={`/quality/holds/${h.id}`} className="ltr font-medium text-primary hover:underline">{h.hold_no}</Link></TD>
                <TD label={t("reason")}>{l("hold_reason", h.reason)}{h.source_ref ? <span className="ltr ms-1 text-xs text-muted-foreground">{h.source_ref}</span> : null}</TD>
                <TD label={t("placed")}>{dateTime(h.placed_at)}</TD>
                <TD label={t("age")}><span dir="ltr">{h.age_days} d</span></TD>
                <TD label={t("lines")}><span dir="ltr">{h.lines_on_hold} / {h.lines}</span></TD>
                <TD label={t("flags")}><div className="flex flex-wrap gap-1">
                  {h.zone_level ? <Badge tone="danger">{t("zoneLevel")}</Badge> : null}
                  {h.blocked ? <Badge tone="warning">{t("blocked")}</Badge> : null}
                  {!h.segregated && h.status === "on_hold" ? <Badge tone="warning">{t("notSegregated")}</Badge> : null}
                  {h.wms_confirmed ? <Badge tone="success">{t("wms")}</Badge> : null}
                </div></TD>
                <TD label={tc("status")}><StatusBadge kind="hold_status" value={h.status} /></TD>
              </TR>
            ))}</TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={r.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : <EmptyState message={t("empty")} />}
    </div>
  );
}

function HoldForm({ project, onDone }: { project: Project; onDone: () => void }) {
  const t = useTranslations("quality.logistics.hld");
  const tc = useTranslations("quality.common");
  const { options } = useQLabels();
  const name = useBilingual();
  const opts = useProjectOptions(project.id);
  const products = useQ3Products(project.id);
  const router = useRouter();
  const { run, busy, error } = useRun();
  const [f, set] = useForm({ reason: "other", zone_id: "", product_id: "", batch: "", qty: "", location: "", reason_note: "" });
  const [zoneLevel, setZoneLevel] = useState(false);
  const site = opts.sites[0]?.value ?? "";
  async function save() {
    const lines = zoneLevel ? [] : [{ product_id: f.product_id, batch: f.batch, qty: f.qty, location: f.location || null }];
    const out = await run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/holds", { params: { path: { project_id: project.id } }, body: { site_id: site, reason: f.reason as S["QHoldReason"], zone_id: f.zone_id || null, zone_level: zoneLevel, reason_note: f.reason_note || null, lines } as never })));
    if (out) { onDone(); router.push(`/quality/holds/${out.id}`); }
  }
  return (
    <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-3" data-testid="q3-hold-form">
      <MutationError error={error} />
      <FormField id="h-reason" label={t("reason")}><Select id="h-reason" value={f.reason} onChange={set("reason")} data-testid="h-reason">{options("hold_reason").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <FormField id="h-zone" label={t("zone")}><Select id="h-zone" value={f.zone_id} onChange={set("zone_id")}><option value="">—</option>{opts.zones.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <label className="flex min-h-touch items-center gap-2 text-sm"><input type="checkbox" checked={zoneLevel} onChange={(e) => setZoneLevel(e.target.checked)} data-testid="h-zone-level" />{t("zoneLevelHint")}</label>
      {!zoneLevel ? (
        <>
          <FormField id="h-prod" label={t("product")}><Select id="h-prod" value={f.product_id} onChange={set("product_id")} data-testid="h-product"><option value="">{tc("select")}</option>{(products.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.sku} — {name(p.description_en, p.description_ar)}</option>)}</Select></FormField>
          <FormField id="h-batch" label={t("batch")}><Input id="h-batch" value={f.batch} onChange={set("batch")} dir="ltr" data-testid="h-batch" /></FormField>
          <FormField id="h-qty" label={t("qty")}><Input id="h-qty" value={f.qty} onChange={set("qty")} dir="ltr" inputMode="decimal" data-testid="h-qty" /></FormField>
          <FormField id="h-loc" label={t("location")}><Input id="h-loc" value={f.location} onChange={set("location")} dir="ltr" /></FormField>
        </>
      ) : null}
      <FormField id="h-note" label={t("note")} className="sm:col-span-2"><Input id="h-note" value={f.reason_note} onChange={set("reason_note")} /></FormField>
      <div className="flex gap-2 sm:col-span-3">
        <Button disabled={busy || (!zoneLevel && (!f.product_id || !f.batch || !f.qty)) || (zoneLevel && !f.zone_id)} onClick={() => void save()} data-testid="h-save">{t("place")}</Button>
        <Button variant="outline" onClick={onDone}>{tc("cancel")}</Button>
      </div>
    </CardContent></Card>
  );
}

export function HoldDetailPage({ id }: { id: string }) {
  return <Q3Gate>{(p) => <HoldDetail project={p} id={id} />}</Q3Gate>;
}

function HoldDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.logistics.hld");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const ar = useLocale() === "ar";
  const caps = useQCaps(project.id);
  const { dateTime } = useFormatters(project.id);
  const q = useQ3Hold(id);
  const { run, busy, error } = useRun();
  const [sel, setSel] = useState<string[]>([]);
  const [rejecting, setRejecting] = useState(false);
  const [ownerFile, setOwnerFile] = useState("");
  const [seg, setSeg] = useState({ segregation: "tagged_in_place", location: "", photo: "" });
  const [outcome, setOutcome] = useState<{ line: string; outcome: string; file: string } | null>(null);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const h = q.data;
  if (!h) return null;
  const manage = caps.write("hold.manage");
  const can = new Set(h.allowed_actions);
  const decide = (action: "release" | "reject", reason?: string) =>
    run(() => unwrap(api.POST("/api/v1/quality/holds/{hold_id}/decide", { params: { path: { hold_id: id } }, body: { action, line_ids: sel, reason: reason ?? null, owner_decision_attachment_id: ownerFile || null } as never })));
  return (
    <div data-testid="q3-hold-detail" data-status={h.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/holds" }, { label: h.hold_no }]} />
      <PageHeader title={<span className="ltr">{h.hold_no}</span>} badge={<StatusBadge kind="hold_status" value={h.status} />} />
      <MutationError error={error} />
      {h.blockers.length ? (
        <Alert tone="warning" className="mb-3" data-testid="q3-hold-blockers">
          <p className="font-medium">{t("blockersTitle")}</p>
          <ul className="list-disc ps-5">{h.blockers.map((b, i) => <li key={i} data-code={b.code}>{ar ? b.detail_ar : b.detail_en}</li>)}</ul>
        </Alert>
      ) : null}
      <Card className="mb-4"><CardContent className="p-4">
        <FieldList>
          <FieldItem label={t("reason")}>{l("hold_reason", h.reason)}</FieldItem>
          <FieldItem label={t("source")} ltr>{h.source_ref ?? "—"}</FieldItem>
          <FieldItem label={t("zone")}>{h.zone?.code ?? "—"}</FieldItem>
          <FieldItem label={t("placed")}>{dateTime(h.placed_at)}</FieldItem>
          <FieldItem label={t("age")}><span dir="ltr">{h.age_days} d</span></FieldItem>
          <FieldItem label={t("segregation")}>{h.segregation ? l("segregation", h.segregation) : "—"}{h.segregation_location ? <span className="ltr ms-1">{h.segregation_location}</span> : null}</FieldItem>
          <FieldItem label={t("wms")}>{h.wms_confirmed ? dateTime(h.wms_confirmed_at) : "—"}</FieldItem>
          <FieldItem label={t("ncr")}>{h.ncr_id ? <Link className="text-primary hover:underline" href={`/quality/ncrs/${h.ncr_id}`}>{t("openNcr")}</Link> : "—"}</FieldItem>
        </FieldList>
        {h.zone_level ? <Alert tone="danger" className="mt-3">{t("zoneLevelAlert")}</Alert> : null}
      </CardContent></Card>
      <Card className="mb-4"><CardContent className="p-4">
        <h2 className="mb-2 text-base font-semibold">{t("lines")}</h2>
        <Table data-testid="q3-hold-lines">
          <THead><TR><TH /><TH>{t("product")}</TH><TH>{t("batch")}</TH><TH>{t("qty")}</TH><TH>{t("owner")}</TH><TH>{t("proposed")}</TH><TH>{tc("status")}</TH><TH /></TR></THead>
          <TBody>{h.lines.map((ln) => (
            <TR key={ln.id} data-testid="q3-hold-line" data-status={ln.line_status}>
              <TD>{ln.line_status === "on_hold" && (can.has("release") || can.has("reject")) ? <input type="checkbox" checked={sel.includes(ln.id)} onChange={(e) => setSel((x) => (e.target.checked ? [...x, ln.id] : x.filter((y) => y !== ln.id)))} aria-label={ln.batch} /> : null}</TD>
              <TD label={t("product")} className="ltr">{ln.sku}</TD>
              <TD label={t("batch")} className="ltr">{ln.batch}</TD>
              <TD label={t("qty")}><span dir="ltr">{ln.qty} {ln.unit}</span></TD>
              <TD label={t("owner")}>{ln.owner?.code ?? "—"}</TD>
              <TD label={t("proposed")}>{ln.proposed_decision ? l("impact_decision", ln.proposed_decision) : "—"}</TD>
              <TD label={tc("status")}><StatusBadge kind="hold_line_status" value={ln.line_status} />{ln.final_outcome ? <span className="ms-1 text-xs">{l("hold_outcome", ln.final_outcome)}</span> : null}</TD>
              <TD>{ln.line_status === "rejected" && !ln.final_outcome && caps.write("stock.record") ? <Button size="sm" variant="outline" onClick={() => setOutcome({ line: ln.id, outcome: "destroyed", file: "" })} data-testid="q3-line-outcome">{t("outcome")}</Button> : null}</TD>
            </TR>
          ))}</TBody>
        </Table>
        {can.has("release") || can.has("reject") ? (
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <AttachmentPick ownerType="q_hold" ownerId={id} value={ownerFile} onChange={setOwnerFile} label={t("ownerDecision")} id="q3-hold-owner-file" />
            {can.has("release") ? <Button disabled={busy} onClick={() => void decide("release")} data-testid="q3-hold-release">{sel.length ? t("releaseSel", { n: sel.length }) : t("releaseAll")}</Button> : null}
            {can.has("reject") ? <Button variant="destructive-outline" disabled={busy} onClick={() => setRejecting(true)} data-testid="q3-hold-reject">{t("reject")}</Button> : null}
          </div>
        ) : null}
        {h.status !== "on_hold" && h.status !== "closed" && manage ? <Button className="mt-3" variant="outline" disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/holds/{hold_id}/close", { params: { path: { hold_id: id } } })))} data-testid="q3-hold-close">{t("close")}</Button> : null}
      </CardContent></Card>
      {outcome ? (
        <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-3" data-testid="q3-outcome-form">
          <FormField id="oc-kind" label={t("outcome")}><Select id="oc-kind" value={outcome.outcome} onChange={(e) => setOutcome({ ...outcome, outcome: e.target.value })}>{options("hold_outcome").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
          <AttachmentPick ownerType="q_hold" ownerId={id} value={outcome.file} onChange={(v) => setOutcome({ ...outcome, file: v })} label={t("evidence")} id="oc-file" />
          <div className="flex items-end gap-2">
            <Button disabled={busy || !outcome.file} onClick={() => void run(async () => { const o = await unwrap(api.POST("/api/v1/quality/hold-lines/{line_id}/outcome", { params: { path: { line_id: outcome.line } }, body: { outcome: outcome.outcome as S["QHoldOutcome"], evidence_attachment_id: outcome.file } })); setOutcome(null); return o; })} data-testid="oc-save">{tc("save")}</Button>
            <Button variant="outline" onClick={() => setOutcome(null)}>{tc("cancel")}</Button>
          </div>
        </CardContent></Card>
      ) : null}
      {manage && h.status === "on_hold" ? (
        <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-4" data-testid="q3-segregation">
          <h2 className="text-base font-semibold sm:col-span-4">{t("segregationTitle")}</h2>
          <FormField id="sg-kind" label={t("segregation")}><Select id="sg-kind" value={seg.segregation} onChange={(e) => setSeg({ ...seg, segregation: e.target.value })}>{options("segregation").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
          <FormField id="sg-loc" label={t("location")}><Input id="sg-loc" value={seg.location} onChange={(e) => setSeg({ ...seg, location: e.target.value })} dir="ltr" /></FormField>
          <AttachmentPick ownerType="q_hold" ownerId={id} value={seg.photo} onChange={(v) => setSeg({ ...seg, photo: v })} label={t("photo")} id="sg-photo" />
          <div className="flex items-end gap-2">
            <Button disabled={busy || !seg.photo} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/holds/{hold_id}/segregation", { params: { path: { hold_id: id } }, body: { segregation: seg.segregation as S["QSegregation"], location: seg.location || null, photo_attachment_id: seg.photo } })))} data-testid="sg-save">{tc("save")}</Button>
            {!h.wms_confirmed ? <Button variant="outline" disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/holds/{hold_id}/wms-confirmed", { params: { path: { hold_id: id } } })))} data-testid="q3-wms">{t("wmsConfirm")}</Button> : null}
          </div>
        </CardContent></Card>
      ) : null}
      <Card className="mb-4"><CardContent className="p-4">
        <h2 className="mb-2 text-base font-semibold">{t("files")}</h2>
        <Attachments ownerType="q_hold" ownerId={id} canUpload={manage || can.size > 0} hint={t("filesHint")} />
      </CardContent></Card>
      {h.signoffs.length ? (
        <Card><CardContent className="p-4"><h2 className="mb-2 text-base font-semibold">{t("signoffs")}</h2>
          <ul className="text-sm">{h.signoffs.map((s) => <li key={s.id} data-testid="q3-signoff">{s.step} · {s.decision} · {ar ? s.text_ar : s.text_en} · {dateTime(s.signed_at)}</li>)}</ul>
        </CardContent></Card>
      ) : null}
      <ReasonDialog open={rejecting} onOpenChange={setRejecting} title={t("reject")} confirm={t("reject")} testId="q3-hold-reject-dialog" onSubmit={(text) => decide("reject", text)} />
    </div>
  );
}
