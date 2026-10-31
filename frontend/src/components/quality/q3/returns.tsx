"use client";
import { Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FormField } from "@/components/common/form-field";
import { PageHeader } from "@/components/common/page-header";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { useQCustomers } from "@/lib/api/quality/q0";
import { useQ3Products, useQ3Return, useQ3Returns } from "@/lib/api/quality/q3";
import { useFormatters } from "@/lib/use-formatters";
import { StatusBadge, useQCaps, useQLabels, useRun } from "@/components/quality/q0/common";
import { ChecklistRunner, Q3Gate, type Project } from "./common";

export function ReturnsListPage() {
  return <Q3Gate>{(p) => <Returns project={p} />}</Q3Gate>;
}

function Returns({ project }: { project: Project }) {
  const t = useTranslations("quality.logistics.ret");
  const tc = useTranslations("quality.common");
  const caps = useQCaps(project.id);
  const { dateTime } = useFormatters(project.id);
  const q = useQ3Returns(project.id, { page_size: 100 });
  const [adding, setAdding] = useState(false);
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} actions={caps.write("stock.record") && !adding ? <Button onClick={() => setAdding(true)} data-testid="q3-return-new"><Plus aria-hidden />{t("new")}</Button> : null} />
      {adding ? <ReturnForm project={project} onDone={() => setAdding(false)} /> : null}
      {q.isLoading ? <LoadingState /> : (q.data?.items ?? []).length ? (
        <Table compact data-testid="q3-return-table">
          <THead><TR><TH>{t("no")}</TH><TH>{t("owner")}</TH><TH>{t("rma")}</TH><TH>{t("received")}</TH><TH>{t("grades")}</TH><TH>{tc("status")}</TH></TR></THead>
          <TBody>{(q.data?.items ?? []).map((r) => (
            <TR key={r.id}><TD><Link className="ltr font-medium text-primary hover:underline" href={`/quality/returns/${r.id}`}>{r.ret_no}</Link></TD><TD>{r.customer?.code}</TD><TD className="ltr">{r.rma_ref ?? "—"}</TD><TD>{dateTime(r.received_at)}</TD><TD className="ltr">{r.grades.join(", ") || "—"}</TD><TD><StatusBadge kind="return_status" value={r.status} /></TD></TR>
          ))}</TBody>
        </Table>
      ) : <EmptyState message={t("empty")} />}
    </div>
  );
}

function ReturnForm({ project, onDone }: { project: Project; onDone: () => void }) {
  const t = useTranslations("quality.logistics.ret");
  const tc = useTranslations("quality.common");
  const opts = useProjectOptions(project.id);
  const customers = useQCustomers(project.id);
  const products = useQ3Products(project.id);
  const router = useRouter();
  const { run, busy, error } = useRun();
  const [cust, setCust] = useState("");
  const [rma, setRma] = useState("");
  const [line, setLine] = useState({ product_id: "", batch: "", qty: "", temp_history: false });
  return (
    <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-4" data-testid="q3-return-form">
      <MutationError error={error} />
      <FormField id="rt-owner" label={t("owner")}><Select id="rt-owner" value={cust} onChange={(e) => setCust(e.target.value)}><option value="">{tc("select")}</option>{(customers.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.code}</option>)}</Select></FormField>
      <FormField id="rt-rma" label={t("rma")}><Input id="rt-rma" value={rma} onChange={(e) => setRma(e.target.value)} dir="ltr" /></FormField>
      <FormField id="rt-prod" label={t("product")}><Select id="rt-prod" value={line.product_id} onChange={(e) => setLine({ ...line, product_id: e.target.value })}><option value="">{tc("select")}</option>{(products.data ?? []).filter((p) => !cust || p.owner?.id === cust).map((p) => <option key={p.id} value={p.id}>{p.sku}</option>)}</Select></FormField>
      <FormField id="rt-batch" label={t("batch")}><Input id="rt-batch" value={line.batch} onChange={(e) => setLine({ ...line, batch: e.target.value })} dir="ltr" /></FormField>
      <FormField id="rt-qty" label={t("qty")}><Input id="rt-qty" value={line.qty} onChange={(e) => setLine({ ...line, qty: e.target.value })} dir="ltr" inputMode="decimal" /></FormField>
      <label className="flex min-h-touch items-center gap-2 text-sm"><input type="checkbox" checked={line.temp_history} onChange={(e) => setLine({ ...line, temp_history: e.target.checked })} />{t("tempHistory")}</label>
      <div className="flex gap-2 sm:col-span-4"><Button disabled={busy || !cust || !line.product_id || !line.batch || !line.qty} onClick={() => void run(async () => { const o = await unwrap(api.POST("/api/v1/projects/{project_id}/quality/returns", { params: { path: { project_id: project.id } }, body: { site_id: opts.sites[0]?.value, customer_id: cust, rma_ref: rma || null, lines: [line] } as never })); onDone(); router.push(`/quality/returns/${o.id}`); return o; })}>{tc("save")}</Button><Button variant="outline" onClick={onDone}>{tc("cancel")}</Button></div>
    </CardContent></Card>
  );
}

export function ReturnDetailPage({ id }: { id: string }) {
  return <Q3Gate>{(p) => <ReturnDetail project={p} id={id} />}</Q3Gate>;
}

function ReturnDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.logistics.ret");
  const { l, options } = useQLabels();
  const caps = useQCaps(project.id);
  const q = useQ3Return(id);
  const { run, busy, error } = useRun();
  const [grades, setGrades] = useState<Record<string, string>>({});
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const r = q.data;
  if (!r) return null;
  const edit = caps.write("stock.record") && r.status !== "confirmed";
  return (
    <div data-testid="q3-return-detail" data-status={r.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/returns" }, { label: r.ret_no }]} />
      <PageHeader title={<span className="ltr">{r.ret_no}</span>} badge={<StatusBadge kind="return_status" value={r.status} />} />
      <MutationError error={error} />
      <Card className="mb-4"><CardContent className="p-4">
        <Table compact>
          <THead><TR><TH>{t("product")}</TH><TH>{t("batch")}</TH><TH>{t("qty")}</TH><TH>{t("tempHistory")}</TH><TH>{t("grade")}</TH></TR></THead>
          <TBody>{r.lines.map((ln) => (
            <TR key={String(ln.id)} data-testid="q3-return-line">
              <TD className="ltr">{String((ln.product as { sku?: string } | null)?.sku ?? "")}</TD><TD className="ltr">{String(ln.batch)}</TD><TD><span dir="ltr">{String(ln.qty)}</span></TD>
              <TD>{ln.temp_history ? t("yes") : t("no_")}</TD>
              <TD>{edit ? <Select value={grades[String(ln.id)] ?? String(ln.grade ?? "")} onChange={(e) => setGrades((g) => ({ ...g, [String(ln.id)]: e.target.value }))} data-testid="ret-grade"><option value="">—</option>{options("return_grade").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select> : l("return_grade", ln.grade as string | null)}</TD>
            </TR>
          ))}</TBody>
        </Table>
        {edit ? <Button className="mt-3" disabled={busy || !Object.keys(grades).length} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/returns/{return_id}/grade", { params: { path: { return_id: id } }, body: { lines: Object.entries(grades).filter(([, g]) => g).map(([line_id, grade]) => ({ line_id, grade })) } as never })))} data-testid="ret-grade-save">{t("saveGrades")}</Button> : null}
        {r.can_confirm ? <Button className="ms-2 mt-3" disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/returns/{return_id}/confirm", { params: { path: { return_id: id } }, body: {} })))} data-testid="ret-confirm">{t("confirm")}</Button> : null}
        {r.hold_id ? <Alert tone="info" className="mt-3"><Link className="underline" href={`/quality/holds/${r.hold_id}`}>{t("openHold")}</Link></Alert> : null}
      </CardContent></Card>
      {edit && !r.inspection ? (
        <Card><CardContent className="p-4"><h2 className="mb-2 text-base font-semibold">{t("inspection")}</h2>
          <ChecklistRunner code="QRET" submitLabel={t("saveInspection")} busy={busy} onSubmit={(a) => void run(() => unwrap(api.POST("/api/v1/quality/returns/{return_id}/inspection", { params: { path: { return_id: id } }, body: { answers: a } as never })))} />
        </CardContent></Card>
      ) : null}
    </div>
  );
}
