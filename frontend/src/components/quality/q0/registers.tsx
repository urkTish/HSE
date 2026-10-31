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
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { CheckboxField, FormField } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { UserSelect, useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { tabsFor } from "@/components/quality/registry";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { useQCriteria, useQCriterion, useQCustomers, useQMte, useQMteItem, useQMteUsage, useQSupplier, useQSuppliers, useQSystems } from "@/lib/api/quality/q0";
import { useDebounced } from "@/lib/use-debounced";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { ProfileBadge, QGate, ReasonDialog, StatusBadge, useBilingual, useQCaps, useQLabels, useRun, type Project, type S } from "./common";

const PAGE_SIZE = 50;
type SetF<T> = (k: keyof T) => (e: { target: { value: string } }) => void;
function useForm<T extends Record<string, string>>(init: T): [T, SetF<T>, (v: T) => void] {
  const [f, setF] = useState(init);
  return [f, (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value })), setF];
}
const clean = (o: Record<string, string>) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== ""));

/** Detail-page tabs: the host's own plus the ones later parts registered (registry/tabs-q<n>.tsx). */
function HostTabs({ host, own, tab, setTab, profile }: { host: "supplier" | "mte"; own: { key: string; label: string }[]; tab: string; setTab: (k: string) => void; profile: string | null }) {
  const tq = useTranslations("quality");
  const extra = tabsFor(host).filter((x) => !x.profiles || (profile && x.profiles.includes(profile as never)));
  return (
    <div className="mb-4 flex gap-1 overflow-x-auto border-b" role="tablist">
      {[...own, ...extra.map((x) => ({ key: x.key, label: tq(x.labelKey as never) }))].map((k) => (
        <button key={k.key} role="tab" aria-selected={tab === k.key} onClick={() => setTab(k.key)} data-testid={`q-${host}-tab-${k.key}`}
          className={`min-h-touch shrink-0 rounded-t-md px-3 text-sm ${tab === k.key ? "border-b-2 border-primary font-semibold" : "text-muted-foreground"}`}>
          {k.label}
        </button>
      ))}
    </div>
  );
}

function ExtraTab({ host, tab, recordId, projectId }: { host: "supplier" | "mte"; tab: string; recordId: string; projectId: string }) {
  return <>{tabsFor(host).filter((x) => x.key === tab).map((x) => <div key={x.key}>{x.render({ recordId, projectId })}</div>)}</>;
}

/* ═════════════ suppliers `/quality/suppliers` (Q-SUP, org-wide) ═════════════ */

export function SupplierListPage() {
  return <QGate>{(p) => <Suppliers project={p} />}</QGate>;
}

function Suppliers({ project }: { project: Project }) {
  const t = useTranslations("quality.supplier");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const caps = useQCaps(project.id);
  const s = useSearchState();
  const bi = useBilingual();
  const { date } = useFormatters(project.id);
  const page = s.getInt("page", 1) ?? 1;
  const status = s.get("status") ?? "";
  const category = s.get("category") ?? "";
  const [search, setSearch] = useState(s.get("q") ?? "");
  const q = useDebounced(search, 300);
  const r = useQSuppliers({ status: status ? [status as S["QSupplierStatus"]] : null, category: (category || null) as S["QSupplierCategory"] | null, q: q || null, page, page_size: PAGE_SIZE });
  const [adding, setAdding] = useState(false);
  const items = r.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")}
        actions={caps.write("supplier.manage") && !adding ? <Button onClick={() => setAdding(true)} data-testid="q-supplier-new"><Plus aria-hidden />{t("new")}</Button> : null} />
      {adding ? <SupplierForm onDone={() => setAdding(false)} /> : null}
      <ListToolbar>
        <SearchFilter id="q-sup-q" value={search} onChange={(v) => { setSearch(v); s.set({ q: v, page: null }); }} />
        <SelectFilter id="q-sup-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={options("supplier_status")} />
        <SelectFilter id="q-sup-cat" label={t("category")} value={category} onChange={(v) => s.set({ category: v, page: null })} options={options("supplier_category")} />
      </ListToolbar>
      {r.isLoading ? <LoadingState /> : r.isError ? <ErrorState error={r.error} onRetry={() => r.refetch()} /> : items.length ? (
        <>
          <Table compact data-testid="q-supplier-table">
            <THead><TR><TH>{t("code")}</TH><TH>{t("name")}</TH><TH>{tc("status")}</TH><TH>{t("category")}</TH><TH>{t("accreditations")}</TH><TH>{t("nextEval")}</TH></TR></THead>
            <TBody>
              {items.map((x) => (
                <TR key={x.id} data-testid="q-supplier-row" data-code={x.supplier_code} data-status={x.status}>
                  <TD label={t("code")}><Link href={`/quality/suppliers/${x.id}`} className="ltr font-medium text-primary hover:underline">{x.supplier_code}</Link></TD>
                  <TD label={t("name")} data-full=""><span dir="auto">{bi(x.legal_name_en, x.legal_name_ar)}</span></TD>
                  <TD label={tc("status")}><StatusBadge kind="supplier_status" value={x.status} /></TD>
                  <TD label={t("category")} className="text-xs">{x.categories.map((c) => l("supplier_category", c)).join(", ")}</TD>
                  <TD label={t("accreditations")} className="text-xs">{x.accreditations.map((a) => `${l("accreditation_standard", a.standard)}${a.valid ? "" : " ✕"}`).join(", ") || "—"}</TD>
                  <TD label={t("nextEval")}>{date(x.next_evaluation_due)}</TD>
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

function SupplierForm({ onDone }: { onDone: () => void }) {
  const t = useTranslations("quality.supplier");
  const tc = useTranslations("quality.common");
  const { options } = useQLabels();
  const router = useRouter();
  const { run, busy, error } = useRun();
  const [f, set] = useForm({ supplier_code: "", legal_name_en: "", legal_name_ar: "", cr_number: "", vat_number: "", country: "SA", scope_en: "", scope_ar: "", contact_name: "", contact_mobile: "", contact_email: "" });
  const [cats, setCats] = useState<string[]>([]);
  async function save() {
    const out = await run(() => unwrap(api.POST("/api/v1/quality/suppliers", { body: { ...clean(f), categories: cats } as unknown as S["QSupplierCreate"] })));
    if (out) {
      onDone();
      router.push(`/quality/suppliers/${out.id}`);
    }
  }
  return (
    <Card className="mb-4">
      <CardContent className="grid gap-4 p-4 sm:grid-cols-2" data-testid="q-supplier-form">
        <MutationError error={error} />
        <FormField id="sup-code" label={t("code")} required hint={t("codeHint")}><Input value={f.supplier_code} onChange={set("supplier_code")} dir="ltr" data-testid="sup-code" /></FormField>
        <FormField id="sup-country" label={t("country")}><Input value={f.country} onChange={set("country")} maxLength={2} dir="ltr" /></FormField>
        <FormField id="sup-en" label={t("nameEn")} required><Input value={f.legal_name_en} onChange={set("legal_name_en")} dir="ltr" data-testid="sup-name-en" /></FormField>
        <FormField id="sup-ar" label={t("nameAr")} required><Input value={f.legal_name_ar} onChange={set("legal_name_ar")} dir="rtl" data-testid="sup-name-ar" /></FormField>
        <FormField id="sup-cr" label={t("cr")} hint={t("crHint")}><Input value={f.cr_number} onChange={set("cr_number")} dir="ltr" inputMode="numeric" /></FormField>
        <FormField id="sup-vat" label={t("vat")}><Input value={f.vat_number} onChange={set("vat_number")} dir="ltr" /></FormField>
        <CheckboxGroup id="sup-cats" legend={t("category")} options={options("supplier_category")} value={cats} onChange={setCats} required className="sm:col-span-2" />
        <FormField id="sup-scope" label={t("scope")} className="sm:col-span-2"><Textarea value={f.scope_en} onChange={set("scope_en")} rows={2} /></FormField>
        <FormField id="sup-cn" label={t("contact")}><Input value={f.contact_name} onChange={set("contact_name")} /></FormField>
        <FormField id="sup-cm" label={t("mobile")}><Input value={f.contact_mobile} onChange={set("contact_mobile")} dir="ltr" inputMode="tel" /></FormField>
        <FormField id="sup-ce" label={t("email")}><Input value={f.contact_email} onChange={set("contact_email")} dir="ltr" type="email" /></FormField>
        <div className="flex gap-2 sm:col-span-2">
          <Button onClick={() => void save()} disabled={busy || !f.supplier_code || !f.legal_name_en || !f.legal_name_ar || !cats.length} data-testid="sup-save">{tc("save")}</Button>
          <Button variant="outline" onClick={onDone}>{tc("cancel")}</Button>
        </div>
      </CardContent>
    </Card>
  );
}

/** Next statuses a user may ask for (the server checks the RPM step and the reason). */
const SUPPLIER_NEXT: Record<string, string[]> = {
  draft: ["pending_approval"],
  pending_approval: ["approved", "conditional", "draft"],
  approved: ["conditional", "suspended", "disqualified"],
  conditional: ["approved", "suspended", "disqualified"],
  suspended: ["approved", "conditional", "disqualified"],
  disqualified: ["suspended"],
};

export function SupplierDetailPage({ id }: { id: string }) {
  return <QGate>{(p, st) => <SupplierDetail project={p} id={id} profile={st.sector_profile} />}</QGate>;
}

function SupplierDetail({ project, id, profile }: { project: Project; id: string; profile: string | null }) {
  const t = useTranslations("quality.supplier");
  const { l, options } = useQLabels();
  const caps = useQCaps(project.id);
  const bi = useBilingual();
  const { date, dateTime } = useFormatters(project.id);
  const q = useQSupplier(id);
  const { run, busy, error } = useRun();
  const [tab, setTab] = useState("details");
  const [to, setTo] = useState<string | null>(null);
  const [acc, setAcc] = useForm({ body: "sac", standard: "iso_iec_17025", number: "", scope_text: "", scope_codes: "", valid_from: "", valid_until: "" });
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const x = q.data;
  if (!x) return null;
  const path = { params: { path: { supplier_id: x.id } } };
  const manage = caps.write("supplier.manage");
  const addAcc = () => {
    const body = { ...clean(acc), scope_codes: acc.scope_codes.split(/[,\s]+/).filter(Boolean) } as unknown as S["QAccreditationCreate"];
    return run(() => unwrap(api.POST("/api/v1/quality/suppliers/{supplier_id}/accreditations", { ...path, body })));
  };
  return (
    <div data-testid="q-supplier-detail" data-status={x.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/suppliers" }, { label: x.supplier_code }]} />
      <PageHeader title={<span className="ltr">{x.supplier_code}</span>} description={bi(x.legal_name_en, x.legal_name_ar)} badge={<StatusBadge kind="supplier_status" value={x.status} />}
        actions={(manage || caps.has("supplier.approve")) ? (
          <div className="flex flex-wrap gap-2">
            {(SUPPLIER_NEXT[x.status] ?? []).map((s) => (
              <Button key={s} variant={s === "approved" ? "default" : "outline"} size="sm" onClick={() => setTo(s)} data-testid={`q-sup-to-${s}`}>{t("to", { status: l("supplier_status", s) })}</Button>
            ))}
          </div>
        ) : null} />
      <MutationError error={error} />
      {x.status === "disqualified" ? <Alert tone="danger" className="mb-3">{t("disqualifiedBanner")}</Alert> : null}
      <HostTabs host="supplier" own={[{ key: "details", label: t("details") }, { key: "accreditations", label: t("accreditations") }, { key: "docs", label: t("docs") }, { key: "history", label: t("history") }]} tab={tab} setTab={setTab} profile={profile} />
      {tab === "details" ? (
        <Card><CardContent className="p-4"><FieldList>
          <FieldItem label={t("category")}>{x.categories.map((c) => l("supplier_category", c)).join(", ")}</FieldItem>
          <FieldItem label={t("cr")} ltr>{x.cr_number ?? "—"}</FieldItem>
          <FieldItem label={t("vat")} ltr>{x.vat_number ?? "—"}</FieldItem>
          <FieldItem label={t("country")} ltr>{x.country}</FieldItem>
          <FieldItem label={t("contractor")} ltr>{x.contractor_code ?? "—"}</FieldItem>
          <FieldItem label={t("scope")} wide><span dir="auto">{bi(x.scope_en, x.scope_ar)}</span></FieldItem>
          {x.approved_scope ? <FieldItem label={t("approvedScope")} wide>{x.approved_scope}</FieldItem> : null}
          {x.contacts_visible ? <FieldItem label={t("contact")}>{[x.contact_name, x.contact_mobile, x.contact_email].filter(Boolean).join(" · ") || "—"}</FieldItem> : null}
          <FieldItem label={t("nextEval")}>{date(x.next_evaluation_due)}</FieldItem>
          {x.status_reason ? <FieldItem label={t("reason")} wide>{x.status_reason} {x.status_changed_at ? `(${dateTime(x.status_changed_at)})` : ""}</FieldItem> : null}
        </FieldList></CardContent></Card>
      ) : null}
      {tab === "accreditations" ? (
        <div className="flex flex-col gap-4">
          {x.accreditations.length ? (
            <Table compact data-testid="q-accreditations">
              <THead><TR><TH>{t("standard")}</TH><TH>{t("body")}</TH><TH>{t("number")}</TH><TH>{t("scopeCodes")}</TH><TH>{t("validUntil")}</TH></TR></THead>
              <TBody>{x.accreditations.map((a) => (
                <TR key={a.id}>
                  <TD label={t("standard")}>{l("accreditation_standard", a.standard)}</TD>
                  <TD label={t("body")}>{l("accreditation_body", a.body)}</TD>
                  <TD label={t("number")} className="ltr">{a.number}</TD>
                  <TD label={t("scopeCodes")} className="ltr text-xs">{a.scope_codes.join(", ") || "—"}</TD>
                  <TD label={t("validUntil")} className={a.valid ? "" : "font-medium text-danger"}>{date(a.valid_until)}</TD>
                </TR>
              ))}</TBody>
            </Table>
          ) : <EmptyState message={t("noAccreditations")} />}
          {manage ? (
            <Card><CardContent className="grid gap-3 p-4 sm:grid-cols-3" data-testid="q-acc-form">
              <FormField id="acc-std" label={t("standard")}><Select value={acc.standard} onChange={setAcc("standard")}>{options("accreditation_standard").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
              <FormField id="acc-body" label={t("body")}><Select value={acc.body} onChange={setAcc("body")}>{options("accreditation_body").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
              <FormField id="acc-no" label={t("number")} required><Input value={acc.number} onChange={setAcc("number")} dir="ltr" data-testid="acc-number" /></FormField>
              <FormField id="acc-codes" label={t("scopeCodes")} hint={t("scopeCodesHint")}><Input value={acc.scope_codes} onChange={setAcc("scope_codes")} dir="ltr" /></FormField>
              <FormField id="acc-from" label={t("validFrom")}><Input type="date" value={acc.valid_from} onChange={setAcc("valid_from")} /></FormField>
              <FormField id="acc-until" label={t("validUntil")} required><Input type="date" value={acc.valid_until} onChange={setAcc("valid_until")} data-testid="acc-until" /></FormField>
              <Button className="self-start" disabled={busy || !acc.number || !acc.valid_until} onClick={() => void addAcc()} data-testid="acc-add">{t("addAccreditation")}</Button>
            </CardContent></Card>
          ) : null}
        </div>
      ) : null}
      {tab === "docs" ? <Card><CardContent className="p-4"><Attachments ownerType="q_supplier_doc" ownerId={x.id} canUpload={manage} /></CardContent></Card> : null}
      {tab === "history" ? <HistoryPanel entityType="q_supplier" entityId={x.id} projectId={project.id} /> : null}
      <ExtraTab host="supplier" tab={tab} recordId={x.id} projectId={project.id} />
      <ReasonDialog open={to !== null} onOpenChange={(v) => !v && setTo(null)} min={to === "approved" || to === "pending_approval" ? 0 : 20}
        title={to ? t("to", { status: l("supplier_status", to) }) : ""} confirm={t("confirm")} label={t("reasonOrComment")} testId="q-sup-transition-dialog"
        onSubmit={(reason) => unwrap(api.POST("/api/v1/quality/suppliers/{supplier_id}/transitions", { ...path, body: { to_status: to as S["QSupplierStatus"], reason: reason || null, project_id: project.id } })).then(() => q.refetch())} />
    </div>
  );
}

/* ═════════════ customers `/quality/customers` (Q-CUS) ═════════════ */

export function CustomersPage() {
  return <QGate>{(p) => <Customers project={p} />}</QGate>;
}

function Customers({ project }: { project: Project }) {
  const t = useTranslations("quality.customer");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const caps = useQCaps(project.id);
  const bi = useBilingual();
  const r = useQCustomers(project.id);
  const { run, busy, error } = useRun();
  const [f, set, setF] = useForm({ code: "", name_en: "", name_ar: "", kind: "client", contact_name: "", contact_mobile: "", contact_email: "" });
  const [ora, setOra] = useState(false);
  const manage = caps.write("quality.settings") || caps.write("complaint.manage");
  const P = { params: { path: { project_id: project.id } } };
  async function add() {
    const out = await run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/customers", { ...P, body: { ...clean(f), owner_release_approval: ora } as unknown as S["QCustomerCreate"] })));
    if (out) setF({ code: "", name_en: "", name_ar: "", kind: "client", contact_name: "", contact_mobile: "", contact_email: "" });
  }
  const toggle = (c: S["QCustomerRead"]) =>
    run(() => unwrap(api.PATCH("/api/v1/quality/customers/{customer_id}", { params: { path: { customer_id: c.id } }, body: { status: c.status === "active" ? "inactive" : "active" } })));
  const rows = r.data ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <MutationError error={error} />
      {r.isLoading ? <LoadingState /> : r.isError ? <ErrorState error={r.error} onRetry={() => r.refetch()} /> : rows.length ? (
        <Table compact data-testid="q-customer-table">
          <THead><TR><TH>{t("code")}</TH><TH>{t("name")}</TH><TH>{t("kind")}</TH><TH>{tc("status")}</TH><TH>{t("ownerRelease")}</TH><TH>{t("contact")}</TH>{manage ? <TH /> : null}</TR></THead>
          <TBody>{rows.map((c) => (
            <TR key={c.id} data-testid="q-customer-row" data-code={c.code}>
              <TD label={t("code")} className="ltr font-medium">{c.code}</TD>
              <TD label={t("name")}>{bi(c.name_en, c.name_ar)}</TD>
              <TD label={t("kind")}>{l("customer_kind", c.kind)}</TD>
              <TD label={tc("status")}><StatusBadge kind="customer_status" value={c.status} /></TD>
              <TD label={t("ownerRelease")}>{c.owner_release_approval ? t("yes") : t("no")}</TD>
              <TD label={t("contact")} className="text-xs">{c.contacts_visible ? [c.contact_name, c.contact_mobile, c.contact_email].filter(Boolean).join(" · ") || "—" : "—"}</TD>
              {manage ? <TD><Button size="sm" variant="outline" disabled={busy} onClick={() => void toggle(c)}>{c.status === "active" ? t("deactivate") : t("activate")}</Button></TD> : null}
            </TR>
          ))}</TBody>
        </Table>
      ) : <EmptyState message={t("empty")} />}
      {manage ? (
        <Card className="mt-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-3" data-testid="q-customer-form">
          <FormField id="cus-code" label={t("code")} required><Input value={f.code} onChange={set("code")} dir="ltr" data-testid="cus-code" /></FormField>
          <FormField id="cus-en" label={t("nameEn")} required><Input value={f.name_en} onChange={set("name_en")} dir="ltr" data-testid="cus-name-en" /></FormField>
          <FormField id="cus-ar" label={t("nameAr")} required><Input value={f.name_ar} onChange={set("name_ar")} dir="rtl" data-testid="cus-name-ar" /></FormField>
          <FormField id="cus-kind" label={t("kind")}><Select value={f.kind} onChange={set("kind")}>{options("customer_kind").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
          <FormField id="cus-cn" label={t("contact")}><Input value={f.contact_name} onChange={set("contact_name")} /></FormField>
          <FormField id="cus-cm" label={t("mobile")}><Input value={f.contact_mobile} onChange={set("contact_mobile")} dir="ltr" inputMode="tel" /></FormField>
          <FormField id="cus-ce" label={t("email")}><Input value={f.contact_email} onChange={set("contact_email")} dir="ltr" type="email" /></FormField>
          <CheckboxField id="cus-ora" label={t("ownerRelease")}><Checkbox checked={ora} onChange={(e) => setOra(e.target.checked)} /></CheckboxField>
          <Button className="self-start" disabled={busy || !f.code || !f.name_en || !f.name_ar} onClick={() => void add()} data-testid="cus-add">{t("add")}</Button>
        </CardContent></Card>
      ) : null}
    </div>
  );
}

/* ═════════════ systems `/quality/systems` (construction only, Q-SYS) ═════════════ */

export function SystemsPage() {
  return <QGate>{(p, st) => (st.sector_profile === "construction" ? <Systems project={p} /> : <ConstructionOnly />)}</QGate>;
}

function ConstructionOnly() {
  const t = useTranslations("quality.system");
  return <Alert tone="info" data-testid="q-construction-only">{t("constructionOnly")}</Alert>;
}

function Systems({ project }: { project: Project }) {
  const t = useTranslations("quality.system");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const caps = useQCaps(project.id);
  const opts = useProjectOptions(project.id);
  const bi = useBilingual();
  const r = useQSystems(project.id);
  const { run, busy, error } = useRun();
  const [f, set, setF] = useForm({ code: "", name_en: "", name_ar: "", discipline: "civil", parent_id: "" });
  const manage = caps.write("quality.settings");
  const rows = r.data ?? [];
  const byId = new Map(rows.map((x) => [x.id, x]));
  async function add() {
    const out = await run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/systems", { params: { path: { project_id: project.id } }, body: clean(f) as unknown as S["QSystemCreate"] })));
    if (out) setF({ code: "", name_en: "", name_ar: "", discipline: f.discipline, parent_id: "" });
  }
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <MutationError error={error} />
      {r.isLoading ? <LoadingState /> : r.isError ? <ErrorState error={r.error} onRetry={() => r.refetch()} /> : rows.length ? (
        <Table compact data-testid="q-system-table">
          <THead><TR><TH>{t("code")}</TH><TH>{t("name")}</TH><TH>{t("discipline")}</TH><TH>{t("parent")}</TH><TH>{t("zones")}</TH><TH>{tc("status")}</TH>{manage ? <TH /> : null}</TR></THead>
          <TBody>{rows.map((x) => (
            <TR key={x.id} data-testid="q-system-row" data-code={x.code}>
              <TD label={t("code")} className="ltr font-medium">{x.code}</TD>
              <TD label={t("name")}>{bi(x.name_en, x.name_ar)}</TD>
              <TD label={t("discipline")}>{l("discipline", x.discipline)}</TD>
              <TD label={t("parent")} className="ltr">{x.parent_id ? byId.get(x.parent_id)?.code ?? "—" : "—"}</TD>
              <TD label={t("zones")} className="ltr text-xs">{x.zone_ids.map((z) => opts.zoneById.get(z)?.code).filter(Boolean).join(", ") || "—"}</TD>
              <TD label={tc("status")}><StatusBadge kind="active_status" value={x.status} /></TD>
              {manage ? <TD><Button size="sm" variant="outline" disabled={busy} onClick={() => void run(() => unwrap(api.PATCH("/api/v1/quality/systems/{system_id}", { params: { path: { system_id: x.id } }, body: { status: x.status === "active" ? "archived" : "active" } })))}>{x.status === "active" ? t("archive") : t("restore")}</Button></TD> : null}
            </TR>
          ))}</TBody>
        </Table>
      ) : <EmptyState message={t("empty")} />}
      {manage ? (
        <Card className="mt-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-3" data-testid="q-system-form">
          <FormField id="sys-code" label={t("code")} required><Input value={f.code} onChange={set("code")} dir="ltr" data-testid="sys-code" /></FormField>
          <FormField id="sys-en" label={t("nameEn")} required><Input value={f.name_en} onChange={set("name_en")} dir="ltr" data-testid="sys-name-en" /></FormField>
          <FormField id="sys-ar" label={t("nameAr")} required><Input value={f.name_ar} onChange={set("name_ar")} dir="rtl" data-testid="sys-name-ar" /></FormField>
          <FormField id="sys-disc" label={t("discipline")}><Select value={f.discipline} onChange={set("discipline")}>{options("discipline").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
          <FormField id="sys-parent" label={t("parent")}><Select value={f.parent_id} onChange={set("parent_id")}><option value="">—</option>{rows.map((x) => <option key={x.id} value={x.id}>{x.code}</option>)}</Select></FormField>
          <Button className="self-start" disabled={busy || !f.code || !f.name_en || !f.name_ar} onClick={() => void add()} data-testid="sys-add">{t("add")}</Button>
        </CardContent></Card>
      ) : null}
    </div>
  );
}

/* ═════════════ acceptance criteria `/quality/criteria` (Q-CRT) ═════════════ */

export function CriteriaListPage() {
  return <QGate>{(p) => <Criteria project={p} />}</QGate>;
}

function Criteria({ project }: { project: Project }) {
  const t = useTranslations("quality.criterion");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const caps = useQCaps(project.id);
  const s = useSearchState();
  const bi = useBilingual();
  const router = useRouter();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.get("status") ?? "";
  const [search, setSearch] = useState(s.get("q") ?? "");
  const q = useDebounced(search, 300);
  const r = useQCriteria({ status: status ? [status as S["QCriterionStatus"]] : null, q: q || null, page, page_size: PAGE_SIZE });
  const { run, busy, error } = useRun();
  const [adding, setAdding] = useState(false);
  const [f, set] = useForm({ code: "", title_en: "", title_ar: "", kind: "range", unit: "", min_value: "", max_value: "", target: "", tol_minus: "", tol_plus: "", reference: "", profile: "both" });
  const items = r.data?.items ?? [];
  async function add() {
    const out = await run(() => unwrap(api.POST("/api/v1/quality/criteria", { body: clean(f) as unknown as S["QCriterionCreate"] })));
    if (out) router.push(`/quality/criteria/${out.id}`);
  }
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")}
        actions={caps.write("quality.author") && !adding ? <Button onClick={() => setAdding(true)} data-testid="q-criterion-new"><Plus aria-hidden />{t("new")}</Button> : null} />
      {adding ? (
        <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-3" data-testid="q-criterion-form">
          <MutationError error={error} />
          <FormField id="cr-code" label={t("code")} required><Input value={f.code} onChange={set("code")} dir="ltr" data-testid="cr-code" /></FormField>
          <FormField id="cr-en" label={t("titleEn")} required><Input value={f.title_en} onChange={set("title_en")} dir="ltr" data-testid="cr-title" /></FormField>
          <FormField id="cr-ar" label={t("titleAr")}><Input value={f.title_ar} onChange={set("title_ar")} dir="rtl" /></FormField>
          <FormField id="cr-kind" label={t("kind")}><Select value={f.kind} onChange={set("kind")} data-testid="cr-kind">{options("criterion_kind").filter((o) => o.value !== "rule").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
          <FormField id="cr-prof" label={t("profile")}><Select value={f.profile} onChange={set("profile")}>{options("profile").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
          <FormField id="cr-unit" label={t("unit")}><Input value={f.unit} onChange={set("unit")} dir="ltr" /></FormField>
          {f.kind === "range" || f.kind === "min" ? <FormField id="cr-min" label={t("min")}><Input value={f.min_value} onChange={set("min_value")} dir="ltr" inputMode="decimal" data-testid="cr-min" /></FormField> : null}
          {f.kind === "range" || f.kind === "max" ? <FormField id="cr-max" label={t("max")}><Input value={f.max_value} onChange={set("max_value")} dir="ltr" inputMode="decimal" data-testid="cr-max" /></FormField> : null}
          {f.kind === "target_tolerance" ? (
            <>
              <FormField id="cr-target" label={t("target")}><Input value={f.target} onChange={set("target")} dir="ltr" inputMode="decimal" /></FormField>
              <FormField id="cr-tm" label={t("tolMinus")}><Input value={f.tol_minus} onChange={set("tol_minus")} dir="ltr" inputMode="decimal" /></FormField>
              <FormField id="cr-tp" label={t("tolPlus")}><Input value={f.tol_plus} onChange={set("tol_plus")} dir="ltr" inputMode="decimal" /></FormField>
            </>
          ) : null}
          <FormField id="cr-ref" label={t("reference")}><Input value={f.reference} onChange={set("reference")} /></FormField>
          <div className="flex gap-2 sm:col-span-3">
            <Button disabled={busy || !f.code || !f.title_en} onClick={() => void add()} data-testid="cr-save">{tc("save")}</Button>
            <Button variant="outline" onClick={() => setAdding(false)}>{tc("cancel")}</Button>
          </div>
        </CardContent></Card>
      ) : null}
      <ListToolbar>
        <SearchFilter id="q-cr-q" value={search} onChange={(v) => { setSearch(v); s.set({ q: v, page: null }); }} />
        <SelectFilter id="q-cr-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={options("criterion_status")} />
      </ListToolbar>
      {r.isLoading ? <LoadingState /> : r.isError ? <ErrorState error={r.error} onRetry={() => r.refetch()} /> : items.length ? (
        <>
          <Table compact data-testid="q-criterion-table">
            <THead><TR><TH>{t("code")}</TH><TH>{t("version")}</TH><TH>{t("titleField")}</TH><TH>{t("kind")}</TH><TH>{t("limits")}</TH><TH>{tc("status")}</TH></TR></THead>
            <TBody>{items.map((c) => (
              <TR key={c.id} data-testid="q-criterion-row" data-code={c.code}>
                <TD label={t("code")}><Link href={`/quality/criteria/${c.id}`} className="ltr font-medium text-primary hover:underline">{c.code}</Link></TD>
                <TD label={t("version")} className="ltr">v{c.version}</TD>
                <TD label={t("titleField")} data-full=""><span dir="auto">{bi(c.title_en, c.title_ar)}</span> <ProfileBadge profile={c.profile === "both" ? null : c.profile} /></TD>
                <TD label={t("kind")}>{l("criterion_kind", c.kind)}</TD>
                <TD label={t("limits")} className="ltr text-xs">{limits(c)}</TD>
                <TD label={tc("status")}><StatusBadge kind="criterion_status" value={c.status} /></TD>
              </TR>
            ))}</TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={r.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : <EmptyState message={t("empty")} />}
    </div>
  );
}

function limits(c: S["QCriterionRead"]): string {
  const u = c.unit ? ` ${c.unit}` : "";
  if (c.kind === "range") return `${c.min_value ?? "?"} – ${c.max_value ?? "?"}${u}`;
  if (c.kind === "min") return `≥ ${c.min_value ?? "?"}${u}`;
  if (c.kind === "max") return `≤ ${c.max_value ?? "?"}${u}`;
  if (c.kind === "target_tolerance") return `${c.target ?? "?"} −${c.tol_minus ?? "0"} / +${c.tol_plus ?? "0"}${u}`;
  if (c.kind === "rule") return c.rule_code ?? "—";
  return "—";
}

export function CriterionDetailPage({ id }: { id: string }) {
  return <QGate>{(p) => <CriterionDetail project={p} id={id} />}</QGate>;
}

function CriterionDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.criterion");
  const { l } = useQLabels();
  const caps = useQCaps(project.id);
  const bi = useBilingual();
  const router = useRouter();
  const ar = useLocale() === "ar";
  const q = useQCriterion(id);
  const { run, busy, error } = useRun();
  const [retire, setRetire] = useState(false);
  const [value, setValue] = useState("");
  const [verdict, setVerdict] = useState<S["QEvaluateRead"] | null>(null);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const c = q.data;
  if (!c) return null;
  const path = { params: { path: { criterion_id: c.id } } };
  const author = caps.write("quality.author");
  async function newVersion() {
    const out = await run(() => unwrap(api.POST("/api/v1/quality/criteria/{criterion_id}/new-version", path)));
    if (out) router.push(`/quality/criteria/${out.id}`);
  }
  async function evaluate() {
    const out = await unwrap(api.POST("/api/v1/quality/criteria/{criterion_id}/evaluate", { ...path, body: c!.kind === "pass_fail" ? { verdict: value as "pass" | "fail" } : { value } })).catch(() => null);
    setVerdict(out);
  }
  return (
    <div data-testid="q-criterion-detail" data-status={c.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/criteria" }, { label: `${c.code} v${c.version}` }]} />
      <PageHeader title={<span className="ltr">{c.code} v{c.version}</span>} description={bi(c.title_en, c.title_ar)} badge={<StatusBadge kind="criterion_status" value={c.status} />}
        actions={author ? (
          <>
            {c.status === "draft" ? <Button disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/criteria/{criterion_id}/transitions", { ...path, body: { action: "publish" } })))} data-testid="q-cr-publish">{t("publish")}</Button> : null}
            {c.status === "published" ? <Button variant="outline" disabled={busy} onClick={() => void newVersion()} data-testid="q-cr-new-version">{t("newVersion")}</Button> : null}
            {c.status === "published" ? <Button variant="outline" onClick={() => setRetire(true)} data-testid="q-cr-retire">{t("retire")}</Button> : null}
          </>
        ) : null} />
      <MutationError error={error} />
      {c.status !== "draft" ? <Alert tone="info" className="mb-3">{t("immutable")}</Alert> : null}
      <Card className="mb-4"><CardContent className="p-4"><FieldList>
        <FieldItem label={t("kind")}>{l("criterion_kind", c.kind)}</FieldItem>
        <FieldItem label={t("limits")} ltr>{limits(c)}</FieldItem>
        <FieldItem label={t("profile")}>{l("profile", c.profile)}</FieldItem>
        <FieldItem label={t("reference")}>{c.reference ?? "—"}</FieldItem>
        {c.kind === "rule" ? <FieldItem label={t("rule")}>{c.rule_installed ? t("ruleInstalled") : t("ruleMissing")}</FieldItem> : null}
        {c.note_en || c.note_ar ? <FieldItem label={t("note")} wide><span dir="auto">{ar ? c.note_ar || c.note_en : c.note_en || c.note_ar}</span></FieldItem> : null}
        {c.status_reason ? <FieldItem label={t("retireReason")} wide>{c.status_reason}</FieldItem> : null}
      </FieldList></CardContent></Card>
      {c.status === "published" && c.kind !== "text" && c.kind !== "rule" ? (
        <Card className="mb-4"><CardContent className="flex flex-wrap items-end gap-3 p-4" data-testid="q-cr-evaluate">
          <FormField id="cr-value" label={t("tryValue")}>
            {c.kind === "pass_fail" ? (
              <Select value={value} onChange={(e) => setValue(e.target.value)}><option value="">—</option><option value="pass">{l("verdict", "pass")}</option><option value="fail">{l("verdict", "fail")}</option></Select>
            ) : <Input value={value} onChange={(e) => setValue(e.target.value)} dir="ltr" inputMode="decimal" data-testid="cr-value" />}
          </FormField>
          <Button variant="outline" disabled={!value} onClick={() => void evaluate()} data-testid="cr-evaluate">{t("evaluate")}</Button>
          {verdict ? <Badge tone={verdict.verdict === "pass" ? "success" : verdict.verdict === "fail" ? "danger" : "neutral"} data-testid="cr-verdict" data-verdict={verdict.verdict}>{l("verdict", verdict.verdict)} — {ar ? verdict.reason_ar : verdict.reason_en}</Badge> : null}
        </CardContent></Card>
      ) : null}
      <HistoryPanel entityType="q_criterion" entityId={c.id} projectId={project.id} />
      <ReasonDialog open={retire} onOpenChange={setRetire} title={t("retire")} confirm={t("retire")}
        onSubmit={(reason) => unwrap(api.POST("/api/v1/quality/criteria/{criterion_id}/transitions", { ...path, body: { action: "retire", reason } })).then(() => q.refetch())} />
    </div>
  );
}

/* ═════════════ M&TE register `/quality/mte` (Q-MTE, AC-Q0-49) ═════════════ */

export function MteListPage() {
  return <QGate>{(p) => <MteList project={p} />}</QGate>;
}

const CAL_TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = { calibrated: "success", due_soon: "warning", overdue: "danger", out_of_service: "danger", limited_use: "warning" };

function MteList({ project }: { project: Project }) {
  const t = useTranslations("quality.mte");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const caps = useQCaps(project.id);
  const s = useSearchState();
  const { date } = useFormatters(project.id);
  const page = s.getInt("page", 1) ?? 1;
  const cal = s.get("cal_status") ?? "";
  const type = s.get("mte_type") ?? "";
  const [search, setSearch] = useState(s.get("q") ?? "");
  const q = useDebounced(search, 300);
  const r = useQMte(project.id, { cal_status: cal ? [cal as S["QCalStatus"]] : null, mte_type: (type || null) as S["QMteType"] | null, q: q || null, page, page_size: PAGE_SIZE });
  const [adding, setAdding] = useState(false);
  const items = r.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")}
        actions={caps.write("mte.manage") && !adding ? <Button onClick={() => setAdding(true)} data-testid="q-mte-new"><Plus aria-hidden />{t("new")}</Button> : null} />
      {adding ? <MteForm project={project} onDone={() => setAdding(false)} /> : null}
      <ListToolbar>
        <SearchFilter id="q-mte-q" value={search} onChange={(v) => { setSearch(v); s.set({ q: v, page: null }); }} />
        <SelectFilter id="q-mte-cal" label={t("calStatus")} value={cal} onChange={(v) => s.set({ cal_status: v, page: null })} options={options("cal_status")} />
        <SelectFilter id="q-mte-type" label={t("type")} value={type} onChange={(v) => s.set({ mte_type: v, page: null })} options={options("mte_type")} />
      </ListToolbar>
      {r.isLoading ? <LoadingState /> : r.isError ? <ErrorState error={r.error} onRetry={() => r.refetch()} /> : items.length ? (
        <>
          <Table compact data-testid="q-mte-table">
            <THead><TR><TH>{t("no")}</TH><TH>{t("type")}</TH><TH>{t("description")}</TH><TH>{t("serial")}</TH><TH>{t("calStatus")}</TH><TH>{t("due")}</TH><TH>{tc("status")}</TH></TR></THead>
            <TBody>{items.map((m) => (
              <TR key={m.id} data-testid="q-mte-row" data-no={m.mte_no} data-cal={m.cal_status}>
                <TD label={t("no")}><Link href={`/quality/mte/${m.id}`} className="ltr font-medium text-primary hover:underline">{m.mte_no}</Link></TD>
                <TD label={t("type")}>{l("mte_type", m.mte_type)}</TD>
                <TD label={t("description")} data-full="" dir="auto">{m.description}</TD>
                <TD label={t("serial")} className="ltr text-xs">{[m.manufacturer, m.serial_no].filter(Boolean).join(" · ") || "—"}</TD>
                <TD label={t("calStatus")}><Badge tone={CAL_TONE[m.cal_status] ?? "neutral"} data-status={m.cal_status}>{l("cal_status", m.cal_status)}</Badge></TD>
                <TD label={t("due")} className={m.cal_status === "overdue" ? "font-medium text-danger" : ""}>{date(m.cal_due_on)}</TD>
                <TD label={tc("status")}><StatusBadge kind="mte_status" value={m.status} /></TD>
              </TR>
            ))}</TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={r.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : <EmptyState message={t("empty")} />}
    </div>
  );
}

function MteForm({ project, onDone }: { project: Project; onDone: () => void }) {
  const t = useTranslations("quality.mte");
  const tc = useTranslations("quality.common");
  const tn = useTranslations("quality.ncr");
  const { options } = useQLabels();
  const opts = useProjectOptions(project.id);
  const suppliers = useQSuppliers({ page_size: 200 });
  const router = useRouter();
  const { run, busy, error } = useRun();
  const [f, set] = useForm({
    mte_type: "", description: "", manufacturer: "", model: "", serial_no: "", range_text: "", resolution: "", tolerance_value: "", tolerance_unit: "",
    owner_kind: "own", owner_engagement_id: "", owner_supplier_id: "", site_id: "", custodian_user_id: "", check_kind: "calibration", interval_months: "12",
  });
  async function save() {
    const body = clean(f) as Record<string, unknown>;
    if (body.interval_months) body.interval_months = Number(body.interval_months);
    if (f.check_kind === "none") delete body.interval_months;
    const out = await run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/mte", { params: { path: { project_id: project.id } }, body: body as unknown as S["QMteCreate"] })));
    if (out) {
      onDone();
      router.push(`/quality/mte/${out.id}`);
    }
  }
  return (
    <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-3" data-testid="q-mte-form">
      <MutationError error={error} />
      <FormField id="mte-type" label={t("type")} required><Select value={f.mte_type} onChange={set("mte_type")} data-testid="mte-type"><option value="">{tc("select")}</option>{options("mte_type").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <FormField id="mte-desc" label={t("description")} required className="sm:col-span-2"><Input value={f.description} onChange={set("description")} data-testid="mte-description" /></FormField>
      <FormField id="mte-man" label={t("manufacturer")}><Input value={f.manufacturer} onChange={set("manufacturer")} dir="ltr" data-testid="mte-manufacturer" /></FormField>
      <FormField id="mte-model" label={t("model")}><Input value={f.model} onChange={set("model")} dir="ltr" /></FormField>
      <FormField id="mte-serial" label={t("serial")}><Input value={f.serial_no} onChange={set("serial_no")} dir="ltr" data-testid="mte-serial" /></FormField>
      <FormField id="mte-range" label={t("range")}><Input value={f.range_text} onChange={set("range_text")} dir="ltr" /></FormField>
      <FormField id="mte-res" label={t("resolution")}><Input value={f.resolution} onChange={set("resolution")} dir="ltr" /></FormField>
      <FormField id="mte-tol" label={t("tolerance")}><div className="flex gap-2"><Input value={f.tolerance_value} onChange={set("tolerance_value")} dir="ltr" inputMode="decimal" /><Input value={f.tolerance_unit} onChange={set("tolerance_unit")} dir="ltr" className="w-24" /></div></FormField>
      <FormField id="mte-owner" label={t("owner")}><Select value={f.owner_kind} onChange={set("owner_kind")}>{options("mte_owner_kind").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      {f.owner_kind === "engagement" ? <FormField id="mte-eng" label={tn("responsible")}><Select value={f.owner_engagement_id} onChange={set("owner_engagement_id")}><option value="">{tc("select")}</option>{opts.engagements.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField> : null}
      {f.owner_kind === "supplier" ? <FormField id="mte-sup" label={tn("supplier")}><Select value={f.owner_supplier_id} onChange={set("owner_supplier_id")}><option value="">{tc("select")}</option>{(suppliers.data?.items ?? []).map((x) => <option key={x.id} value={x.id}>{x.supplier_code}</option>)}</Select></FormField> : null}
      <FormField id="mte-site" label={tn("site")}><Select value={f.site_id} onChange={set("site_id")}><option value="">—</option>{opts.sites.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <FormField id="mte-cust" label={t("custodian")}><UserSelect projectId={project.id} value={f.custodian_user_id} onChange={set("custodian_user_id")} /></FormField>
      <FormField id="mte-check" label={t("checkKind")}><Select value={f.check_kind} onChange={set("check_kind")} data-testid="mte-check">{options("check_kind").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      {f.check_kind !== "none" ? <FormField id="mte-int" label={t("interval")}><Input type="number" min={1} max={120} value={f.interval_months} onChange={set("interval_months")} dir="ltr" /></FormField> : null}
      <div className="flex gap-2 sm:col-span-3">
        <Button disabled={busy || !f.mte_type || !f.description} onClick={() => void save()} data-testid="mte-save">{tc("save")}</Button>
        <Button variant="outline" onClick={onDone}>{tc("cancel")}</Button>
      </div>
    </CardContent></Card>
  );
}

export function MteDetailPage({ id }: { id: string }) {
  return <QGate>{(p, st) => <MteDetail project={p} id={id} profile={st.sector_profile} />}</QGate>;
}

function MteDetail({ project, id, profile }: { project: Project; id: string; profile: string | null }) {
  const t = useTranslations("quality.mte");
  const { l, recordType } = useQLabels();
  const caps = useQCaps(project.id);
  const { date, dateTime } = useFormatters(project.id);
  const q = useQMteItem(id);
  const usage = useQMteUsage(id);
  const { run, busy, error } = useRun();
  const [tab, setTab] = useState("details");
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const m = q.data;
  if (!m) return null;
  const manage = caps.write("mte.manage");
  const setStatus = (status: S["QMteStatus"]) => run(() => unwrap(api.PATCH("/api/v1/quality/mte/{mte_id}", { params: { path: { mte_id: m.id } }, body: { status } })));
  return (
    <div data-testid="q-mte-detail" data-cal={m.cal_status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/mte" }, { label: m.mte_no }]} />
      <PageHeader title={<span className="ltr">{m.mte_no}</span>} description={m.description}
        badge={<span className="flex gap-2"><Badge tone={CAL_TONE[m.cal_status] ?? "neutral"}>{l("cal_status", m.cal_status)}</Badge><StatusBadge kind="mte_status" value={m.status} /></span>}
        actions={manage && m.status === "active" ? (
          <>
            <Button variant="outline" size="sm" disabled={busy} onClick={() => void setStatus("retired")} data-testid="q-mte-retire">{t("retire")}</Button>
            <Button variant="outline" size="sm" disabled={busy} onClick={() => void setStatus("lost")}>{t("lost")}</Button>
          </>
        ) : manage ? <Button variant="outline" size="sm" disabled={busy} onClick={() => void setStatus("active")}>{t("reactivate")}</Button> : null} />
      <MutationError error={error} />
      {["overdue", "out_of_service"].includes(m.cal_status) ? <Alert tone="danger" className="mb-3">{t("notCalibrated")}</Alert> : null}
      <HostTabs host="mte" own={[{ key: "details", label: t("details") }, { key: "usage", label: t("usage") }, { key: "docs", label: t("docs") }, { key: "history", label: t("history") }]} tab={tab} setTab={setTab} profile={profile} />
      {tab === "details" ? (
        <Card><CardContent className="p-4"><FieldList>
          <FieldItem label={t("type")}>{l("mte_type", m.mte_type)}</FieldItem>
          <FieldItem label={t("manufacturer")} ltr>{m.manufacturer ?? "—"}</FieldItem>
          <FieldItem label={t("model")} ltr>{m.model ?? "—"}</FieldItem>
          <FieldItem label={t("serial")} ltr>{m.serial_no ?? "—"}</FieldItem>
          <FieldItem label={t("range")} ltr>{m.range_text ?? "—"}</FieldItem>
          <FieldItem label={t("resolution")} ltr>{m.resolution ?? "—"}</FieldItem>
          <FieldItem label={t("tolerance")} ltr>{m.tolerance_value ? `± ${m.tolerance_value} ${m.tolerance_unit ?? ""}` : "—"}</FieldItem>
          <FieldItem label={t("owner")}>{l("mte_owner_kind", m.owner_kind)}</FieldItem>
          <FieldItem label={t("location")} ltr>{[m.site_code, m.zone_code].filter(Boolean).join(" / ") || "—"}</FieldItem>
          <FieldItem label={t("checkKind")}>{l("check_kind", m.check_kind)}{m.interval_months ? ` · ${t("months", { n: m.interval_months })}` : ""}</FieldItem>
          <FieldItem label={t("due")}>{date(m.cal_due_on)}</FieldItem>
          {m.cal_status_reason ? <FieldItem label={t("calReason")} wide>{m.cal_status_reason}</FieldItem> : null}
        </FieldList></CardContent></Card>
      ) : null}
      {tab === "usage" ? (
        usage.isLoading ? <LoadingState /> : (usage.data ?? []).length ? (
          <Table compact data-testid="q-mte-usage">
            <THead><TR><TH>{t("usedAt")}</TH><TH>{t("record")}</TH><TH>{t("verdict")}</TH><TH>{t("calAtUse")}</TH><TH>{t("note")}</TH></TR></THead>
            <TBody>{(usage.data ?? []).map((u) => (
              <TR key={u.id}>
                <TD label={t("usedAt")}>{dateTime(u.used_at)}</TD>
                <TD label={t("record")}>{recordType(u.record_type)}</TD>
                <TD label={t("verdict")}><Badge tone={u.verdict === "ok" ? "success" : "warning"}>{l("mte_use_verdict", u.verdict)}</Badge></TD>
                <TD label={t("calAtUse")}>{l("cal_status", u.cal_status_at_use)}</TD>
                <TD label={t("note")}>{u.value_note ?? "—"}</TD>
              </TR>
            ))}</TBody>
          </Table>
        ) : <EmptyState message={t("noUsage")} />
      ) : null}
      {tab === "docs" ? <Card><CardContent className="p-4"><Attachments ownerType="q_mte_doc" ownerId={m.id} canUpload={manage} /></CardContent></Card> : null}
      {tab === "history" ? <HistoryPanel entityType="q_mte" entityId={m.id} projectId={project.id} /> : null}
      <ExtraTab host="mte" tab={tab} recordId={m.id} projectId={project.id} />
    </div>
  );
}
