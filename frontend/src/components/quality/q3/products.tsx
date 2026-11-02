"use client";
import { Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SearchFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, LoadingState, MutationError } from "@/components/common/states";
import { api, unwrap } from "@/lib/api/client";
import { useQCustomers } from "@/lib/api/quality/q0";
import { useQ3Products } from "@/lib/api/quality/q3";
import { useDebounced } from "@/lib/use-debounced";
import { useBilingual, useQCaps, useQLabels, useRun } from "@/components/quality/q0/common";
import { Q3Gate, Temp, clean, useForm, type Project } from "./common";

export function ProductsPage() {
  return <Q3Gate>{(p) => <Products project={p} />}</Q3Gate>;
}

function Products({ project }: { project: Project }) {
  const t = useTranslations("quality.logistics.prd");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const name = useBilingual();
  const caps = useQCaps(project.id);
  const customers = useQCustomers(project.id);
  const [search, setSearch] = useState("");
  const q = useDebounced(search, 300);
  const r = useQ3Products(project.id, { q: q || null });
  const { run, busy, error } = useRun();
  const [adding, setAdding] = useState(false);
  const [f, set] = useForm({ owner_customer_id: "", sku: "", description_en: "", description_ar: "", gtin: "", storage_class: "chilled", shelf_life_days: "", min_remaining_shelf_life_pct: "" });
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} actions={caps.write("stock.record") && !adding ? <Button onClick={() => setAdding(true)} data-testid="q3-product-new"><Plus aria-hidden />{t("new")}</Button> : null} />
      {adding ? (
        <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-4" data-testid="q3-product-form">
          <MutationError error={error} />
          <FormField id="pr-owner" label={t("owner")} required><Select id="pr-owner" value={f.owner_customer_id} onChange={set("owner_customer_id")}><option value="">{tc("select")}</option>{(customers.data ?? []).filter((c) => c.kind === "depositor").map((c) => <option key={c.id} value={c.id}>{c.code}</option>)}</Select></FormField>
          <FormField id="pr-sku" label={t("sku")} required><Input id="pr-sku" value={f.sku} onChange={set("sku")} dir="ltr" /></FormField>
          <FormField id="pr-en" label={t("descEn")} required><Input id="pr-en" value={f.description_en} onChange={set("description_en")} dir="ltr" /></FormField>
          <FormField id="pr-ar" label={t("descAr")}><Input id="pr-ar" value={f.description_ar} onChange={set("description_ar")} dir="rtl" /></FormField>
          <FormField id="pr-gtin" label={t("gtin")}><Input id="pr-gtin" value={f.gtin} onChange={set("gtin")} dir="ltr" inputMode="numeric" /></FormField>
          <FormField id="pr-class" label={t("class")}><Select id="pr-class" value={f.storage_class} onChange={set("storage_class")}>{options("storage_class").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
          <FormField id="pr-life" label={t("shelfLife")}><Input id="pr-life" value={f.shelf_life_days} onChange={set("shelf_life_days")} dir="ltr" inputMode="numeric" /></FormField>
          <FormField id="pr-min" label={t("minRemaining")}><Input id="pr-min" value={f.min_remaining_shelf_life_pct} onChange={set("min_remaining_shelf_life_pct")} dir="ltr" inputMode="decimal" /></FormField>
          <div className="flex gap-2 sm:col-span-4">
            <Button disabled={busy || !f.owner_customer_id || !f.sku || !f.description_en} onClick={() => void run(async () => { const b: Record<string, unknown> = clean(f); if (b.shelf_life_days) b.shelf_life_days = Number(b.shelf_life_days); const o = await unwrap(api.POST("/api/v1/projects/{project_id}/quality/products", { params: { path: { project_id: project.id } }, body: b as never })); setAdding(false); return o; })}>{tc("save")}</Button>
            <Button variant="outline" onClick={() => setAdding(false)}>{tc("cancel")}</Button>
          </div>
        </CardContent></Card>
      ) : null}
      <ListToolbar><SearchFilter id="q3-prd-q" value={search} onChange={setSearch} /></ListToolbar>
      {r.isLoading ? <LoadingState /> : (r.data ?? []).length ? (
        <Table compact data-testid="q3-products">
          <THead><TR><TH>{t("sku")}</TH><TH>{t("owner")}</TH><TH>{t("desc")}</TH><TH>{t("class")}</TH><TH>{t("range")}</TH><TH>{t("shelfLife")}</TH></TR></THead>
          <TBody>{(r.data ?? []).map((p) => (
            <TR key={p.id} data-testid="q3-product-row"><TD className="ltr font-medium">{p.sku}</TD><TD>{p.owner?.code}</TD><TD>{name(p.description_en, p.description_ar)}</TD><TD>{l("storage_class", p.storage_class)}</TD><TD><Temp v={p.temp_min} /> … <Temp v={p.temp_max} /></TD><TD><span dir="ltr">{p.shelf_life_days ?? "—"}</span></TD></TR>
          ))}</TBody>
        </Table>
      ) : <EmptyState />}
    </div>
  );
}
