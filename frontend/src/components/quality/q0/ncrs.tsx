"use client";
import { Download, Plus } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { CheckboxField, FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { UserSelect, useProjectOptions, useUserOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Attachments } from "@/components/common/attachments";
import { ApiWarnings } from "@/components/common/api-warnings";
import { Link, useRouter } from "@/i18n/navigation";
import { api, downloadFile, unwrap } from "@/lib/api/client";
import { useQNcr, useQNcrs, useQSuppliers } from "@/lib/api/quality/q0";
import { useDebounced } from "@/lib/use-debounced";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { tabsFor } from "@/components/quality/registry";
import { ClassBadge, ProfileBadge, QGate, ReasonDialog, StatusBadge, useBilingual, useQCaps, useQLabels, useRun, userText, type Project, type QSettings, type S } from "./common";

type Ncr = S["QNcrRead"];
const PAGE_SIZE = 50;
const CLASSES = ["minor", "major", "critical"] as const;

/* ═════════════ register `/quality/ncrs` ═════════════ */

export function NcrListPage() {
  return <QGate>{(p) => <Register project={p} />}</QGate>;
}

function Register({ project }: { project: Project }) {
  const t = useTranslations("quality.ncr");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const caps = useQCaps(project.id);
  const s = useSearchState();
  const { date } = useFormatters(project.id);
  const ar = useLocale() === "ar";
  const page = s.getInt("page", 1) ?? 1;
  const status = s.get("status") ?? "";
  const cls = s.get("classification") ?? "";
  const cat = s.get("category") ?? "";
  const [search, setSearch] = useState(s.get("q") ?? "");
  const q = useDebounced(search, 300);
  const query = {
    status: status ? [status as S["QNcrStatus"]] : null,
    classification: cls ? [cls as S["QNcrClass"]] : null,
    category: cat ? [cat as S["QNcrCategory"]] : null,
    open_only: s.getBool("open_only") ?? false,
    overdue: s.getBool("overdue") ?? null,
    mine: s.getBool("mine") ?? false,
    repeat: s.getBool("repeat") ?? null,
    q: q || null,
    page,
    page_size: PAGE_SIZE,
  };
  const r = useQNcrs(project.id, query);
  const items = r.data?.items ?? [];
  async function exportCsv() {
    const job = await unwrap(api.POST("/api/v1/exports", { body: { dataset: "quality_ncrs", project_id: project.id, format: "csv" } }));
    if (job.status === "ready") await downloadFile(`/api/v1/export-jobs/${job.id}/download`, `${job.export_no}.csv`).catch(() => undefined);
  }
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          <>
            {caps.has("export.quality") ? (
              <Button variant="outline" onClick={() => void exportCsv()} data-testid="q-ncr-export">
                <Download aria-hidden />
                {tc("export")}
              </Button>
            ) : null}
            {caps.write("ncr.raise") ? (
              <Button asChild data-testid="q-ncr-new">
                <Link href="/quality/ncrs/new">
                  <Plus aria-hidden />
                  {t("new")}
                </Link>
              </Button>
            ) : null}
          </>
        }
      />
      <ListToolbar>
        <SearchFilter id="q-ncr-q" value={search} onChange={(v) => { setSearch(v); s.set({ q: v, page: null }); }} />
        <SelectFilter id="q-ncr-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={options("ncr_status")} />
        <SelectFilter id="q-ncr-class" label={t("classification")} value={cls} onChange={(v) => s.set({ classification: v, page: null })} options={CLASSES.map((c) => ({ value: c, label: l("ncr_class", c) }))} />
        <SelectFilter id="q-ncr-cat" label={t("category")} value={cat} onChange={(v) => s.set({ category: v, page: null })} options={options("ncr_category")} />
        <SelectFilter id="q-ncr-flags" label={tc("show")} value={s.getBool("mine") ? "mine" : s.getBool("overdue") ? "overdue" : s.getBool("open_only") ? "open" : s.getBool("repeat") ? "repeat" : ""}
          onChange={(v) => s.set({ mine: v === "mine" ? "true" : null, overdue: v === "overdue" ? "true" : null, open_only: v === "open" ? "true" : null, repeat: v === "repeat" ? "true" : null, page: null })}
          options={[{ value: "mine", label: tc("mine") }, { value: "open", label: tc("openOnly") }, { value: "overdue", label: tc("overdue") }, { value: "repeat", label: t("repeat") }]} />
      </ListToolbar>
      {r.isLoading ? (
        <LoadingState />
      ) : r.isError ? (
        <ErrorState error={r.error} onRetry={() => r.refetch()} />
      ) : items.length ? (
        <>
          <Table compact data-testid="q-ncr-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("classification")}</TH>
                <TH>{tc("status")}</TH>
                <TH>{t("titleField")}</TH>
                <TH>{t("source")}</TH>
                <TH>{t("responsible")}</TH>
                <TH>{t("age")}</TH>
                <TH>{t("target")}</TH>
                <TH>{t("cost")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((n) => (
                <TR key={n.id} data-testid="q-ncr-row" data-no={n.ncr_no ?? ""} data-status={n.status}>
                  <TD label={t("no")}>
                    <Link href={`/quality/ncrs/${n.id}`} className="ltr font-medium whitespace-nowrap text-primary hover:underline">
                      {n.ncr_no ?? t("draft")}
                    </Link>
                  </TD>
                  <TD label={t("classification")}>
                    <ClassBadge value={n.classification} />
                    {n.repeat ? <span className="ms-1 text-xs text-warning">{t("repeat")}</span> : null}
                  </TD>
                  <TD label={tc("status")}>
                    <StatusBadge kind="ncr_status" value={n.status} />
                  </TD>
                  <TD label={t("titleField")} data-full="" className="md:min-w-56">
                    <span dir="auto">{n.title}</span>
                    <span className="block text-xs text-muted-foreground">{l("ncr_category", n.category)} · {n.site_code}</span>
                  </TD>
                  <TD label={t("source")} className="text-xs">
                    {l("ncr_source", n.source_type)}
                    {n.source_ref ? <span className="ltr block">{n.source_ref}</span> : null}
                  </TD>
                  <TD label={t("responsible")} className="text-xs">
                    {n.responsible_engagement?.short_code ?? "—"}
                    {n.supplier ? <span className="block">{n.supplier.code}</span> : null}
                    {n.owner ? <span className="block text-muted-foreground">{userText(n.owner, ar)}</span> : null}
                  </TD>
                  <TD label={t("age")} className="ltr">
                    {n.age_days ?? "—"}
                  </TD>
                  <TD label={t("target")} className={n.overdue ? "font-medium text-danger" : ""}>
                    {date(n.target_close_date)}
                  </TD>
                  <TD label={t("cost")} className="ltr text-end">
                    {n.cost_gross_sar ?? "—"}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={r.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState message={t("empty")} />
      )}
    </div>
  );
}

/* ═════════════ raise `/quality/ncrs/new` (phone: one screen) ═════════════ */

export function NcrNewPage() {
  return <QGate>{(p, st) => <RaiseForm project={p} settings={st} />}</QGate>;
}

function RaiseForm({ project }: { project: Project; settings: QSettings }) {
  const t = useTranslations("quality.ncr");
  const tc = useTranslations("quality.common");
  const { options } = useQLabels();
  const opts = useProjectOptions(project.id);
  const suppliers = useQSuppliers({ page_size: 200 });
  const router = useRouter();
  const { run, busy, error } = useRun();
  const [f, setF] = useState({
    title: "", finding_en: "", requirement_en: "", category: "", classification: "minor", detection_stage: "in_process",
    site_id: "", zone_id: "", responsible_engagement_id: "", owner_id: "", supplier_id: "", location_ref: "", quantity: "", unit: "",
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const ready = f.title.trim() && f.site_id;
  async function save(open: boolean) {
    const body = Object.fromEntries(Object.entries(f).filter(([, v]) => v !== "")) as Record<string, string>;
    const out = await run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/ncrs", { params: { path: { project_id: project.id } }, body: { ...body, open } as S["QNcrCreate"] })), open ? t("opened") : t("draftSaved"));
    if (out) router.push(`/quality/ncrs/${out.id}`);
  }
  return (
    <div>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/ncrs" }, { label: t("new") }]} />
      <PageHeader title={t("new")} description={t("newHint")} />
      <MutationError error={error} />
      <Card>
        <CardContent className="flex flex-col gap-4 p-4">
          <FormSection title={t("what")}>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField id="ncr-title" label={t("titleField")} required className="sm:col-span-2">
                <Input value={f.title} onChange={set("title")} maxLength={150} data-testid="ncr-title" />
              </FormField>
              <FormField id="ncr-finding" label={t("finding")} hint={tc("noNames")} className="sm:col-span-2">
                <Textarea value={f.finding_en} onChange={set("finding_en")} rows={3} data-testid="ncr-finding" />
              </FormField>
              <FormField id="ncr-req" label={t("requirement")} className="sm:col-span-2">
                <Textarea value={f.requirement_en} onChange={set("requirement_en")} rows={2} data-testid="ncr-requirement" />
              </FormField>
              <FormField id="ncr-cat" label={t("category")}>
                <Select value={f.category} onChange={set("category")} data-testid="ncr-category">
                  <option value="">{tc("select")}</option>
                  {options("ncr_category").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </Select>
              </FormField>
              <FormField id="ncr-class" label={t("classification")}>
                <Select value={f.classification} onChange={set("classification")} data-testid="ncr-class">
                  {options("ncr_class").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </Select>
              </FormField>
              <FormField id="ncr-stage" label={t("detectionStage")}>
                <Select value={f.detection_stage} onChange={set("detection_stage")} data-testid="ncr-stage">
                  {options("detection_stage").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </Select>
              </FormField>
            </div>
          </FormSection>
          <FormSection title={t("where")}>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField id="ncr-site" label={t("site")} required>
                <Select value={f.site_id} onChange={(e) => setF((x) => ({ ...x, site_id: e.target.value, zone_id: "" }))} data-testid="ncr-site">
                  <option value="">{tc("select")}</option>
                  {opts.sites.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </Select>
              </FormField>
              <FormField id="ncr-zone" label={t("zone")}>
                <Select value={f.zone_id} onChange={set("zone_id")} data-testid="ncr-zone">
                  <option value="">—</option>
                  {opts.zones.filter((z) => z.siteId === f.site_id).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </Select>
              </FormField>
              <FormField id="ncr-loc" label={t("location")} className="sm:col-span-2">
                <Input value={f.location_ref} onChange={set("location_ref")} maxLength={120} />
              </FormField>
            </div>
          </FormSection>
          <FormSection title={t("who")}>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField id="ncr-eng" label={t("responsible")}>
                <Select value={f.responsible_engagement_id} onChange={set("responsible_engagement_id")} data-testid="ncr-engagement">
                  <option value="">{tc("select")}</option>
                  {opts.engagements.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </Select>
              </FormField>
              <FormField id="ncr-owner" label={t("owner")}>
                <UserSelect projectId={project.id} value={f.owner_id} onChange={set("owner_id")} data-testid="ncr-owner" />
              </FormField>
              <FormField id="ncr-sup" label={t("supplier")}>
                <Select value={f.supplier_id} onChange={set("supplier_id")} data-testid="ncr-supplier">
                  <option value="">—</option>
                  {(suppliers.data?.items ?? []).map((x) => <option key={x.id} value={x.id}>{x.supplier_code} — {x.legal_name_en}</option>)}
                </Select>
              </FormField>
              <div className="grid grid-cols-2 gap-2">
                <FormField id="ncr-qty" label={t("quantity")}>
                  <Input value={f.quantity} onChange={set("quantity")} inputMode="decimal" className="ltr" />
                </FormField>
                <FormField id="ncr-unit" label={t("unit")}>
                  <Input value={f.unit} onChange={set("unit")} maxLength={10} />
                </FormField>
              </div>
            </div>
          </FormSection>
          <p className="text-xs text-muted-foreground">{t("photoAfter")}</p>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" disabled={busy || !ready} onClick={() => void save(false)} data-testid="ncr-save-draft">
              {t("saveDraft")}
            </Button>
            <Button disabled={busy || !ready} onClick={() => void save(true)} data-testid="ncr-open">
              {t("saveOpen")}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

/* ═════════════ detail `/quality/ncrs/[id]` ═════════════ */

const TABS = ["details", "containment", "rca", "disposition", "actions", "costs", "supplier", "signoffs", "links", "history"] as const;

export function NcrDetailPage({ id }: { id: string }) {
  return <QGate>{(p) => <Detail project={p} id={id} />}</QGate>;
}

function Detail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.ncr");
  const tc = useTranslations("quality.common");
  const q = useQNcr(id);
  const [tab, setTab] = useState<string>("details");
  const extra = tabsFor("ncr");
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const n = q.data;
  if (!n) return null;
  const allowed = new Set(n.allowed_actions);
  return (
    <div data-testid="q-ncr-detail" data-status={n.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/ncrs" }, { label: n.ncr_no ?? t("draft") }]} />
      <PageHeader
        title={<span className="ltr">{n.ncr_no ?? t("draft")}</span>}
        badge={
          <span className="flex flex-wrap items-center gap-2">
            <ClassBadge value={n.classification} />
            <StatusBadge kind="ncr_status" value={n.status} />
            <ProfileBadge profile={n.profile} />
            {n.repeat ? <span className="text-xs font-medium text-warning" data-testid="q-ncr-repeat">{t("repeat")}</span> : null}
          </span>
        }
        description={n.title}
        actions={<HeaderActions ncr={n} />}
      />
      <ApiWarnings warnings={n.warnings} className="mb-3" />
      {n.containment_overdue ? <Alert tone="danger" className="mb-3">{t("containmentOverdue")}</Alert> : null}
      <Steps ncr={n} projectId={project.id} />
      <div className="mb-4 flex gap-1 overflow-x-auto border-b" role="tablist">
        {[...TABS, ...extra.map((x) => x.key)].map((k) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} data-testid={`q-ncr-tab-${k}`}
            className={`min-h-touch shrink-0 rounded-t-md px-3 text-sm ${tab === k ? "border-b-2 border-primary font-semibold" : "text-muted-foreground"}`}>
            {(TABS as readonly string[]).includes(k) ? t(`tab.${k}` as never) : tc("more")}
          </button>
        ))}
      </div>
      {tab === "details" ? <Details ncr={n} projectId={project.id} canEdit={allowed.has("edit")} /> : null}
      {tab === "containment" ? <Containment ncr={n} canEdit={allowed.has("containment")} /> : null}
      {tab === "rca" ? <Rca ncr={n} projectId={project.id} canEdit={allowed.has("rca")} /> : null}
      {tab === "disposition" ? <Disposition ncr={n} canEdit={allowed.has("disposition")} canEvidence={allowed.has("edit")} /> : null}
      {tab === "actions" ? <Actions ncr={n} projectId={project.id} canAdd={allowed.has("actions")} /> : null}
      {tab === "costs" ? <Costs ncr={n} canEdit={allowed.has("costs")} /> : null}
      {tab === "supplier" ? <SupplierResponse ncr={n} canEdit={allowed.has("supplier_response")} /> : null}
      {tab === "signoffs" ? <Signoffs ncr={n} /> : null}
      {tab === "links" ? <Links ncr={n} /> : null}
      {tab === "history" ? <HistoryPanel entityType="q_ncr" entityId={n.id} projectId={project.id} /> : null}
      {extra.filter((x) => x.key === tab).map((x) => <div key={x.key}>{x.render({ recordId: n.id, projectId: project.id })}</div>)}
    </div>
  );
}

function useNcrRun(id: string) {
  const r = useRun();
  return { ...r, path: { params: { path: { ncr_id: id } } } as const };
}

function HeaderActions({ ncr }: { ncr: Ncr }) {
  const t = useTranslations("quality.ncr");
  const tc = useTranslations("quality.common");
  const allowed = new Set(ncr.allowed_actions);
  const router = useRouter();
  const { run, busy, error, path } = useNcrRun(ncr.id);
  const [dlg, setDlg] = useState<"" | "void" | "reopen" | "implement" | "class">("");
  const [cls, setCls] = useState<string>(ncr.classification ?? "minor");
  const pdf = (lang: "en" | "ar") => downloadFile(`/api/v1/quality/ncrs/${ncr.id}/pdf?lang=${lang}`, `${ncr.ncr_no ?? "NCR"}-${lang.toUpperCase()}.pdf`);
  return (
    <>
      <MutationError error={error} />
      {ncr.ncr_no ? (
        <>
          <Button variant="outline" size="sm" onClick={() => void pdf("en")} data-testid="q-ncr-pdf-en">PDF EN</Button>
          <Button variant="outline" size="sm" onClick={() => void pdf("ar")} data-testid="q-ncr-pdf-ar">PDF عربي</Button>
        </>
      ) : null}
      {allowed.has("open") ? (
        <Button disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/ncrs/{ncr_id}/open", path)), t("opened"))} data-testid="q-ncr-open">
          {t("openNcr")}
        </Button>
      ) : null}
      {allowed.has("delete") ? (
        <Button variant="outline" disabled={busy} onClick={async () => { await run(() => unwrap(api.DELETE("/api/v1/quality/ncrs/{ncr_id}", path))); router.push("/quality/ncrs"); }} data-testid="q-ncr-delete">
          {tc("delete")}
        </Button>
      ) : null}
      {allowed.has("propose") ? (
        <Button disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/ncrs/{ncr_id}/propose", path)), t("proposed"))} data-testid="q-ncr-propose">
          {t("propose")}
        </Button>
      ) : null}
      {allowed.has("implement") ? <Button disabled={busy} onClick={() => setDlg("implement")} data-testid="q-ncr-implement">{t("implement")}</Button> : null}
      {allowed.has("class") ? <Button variant="outline" size="sm" onClick={() => setDlg("class")} data-testid="q-ncr-class">{t("changeClass")}</Button> : null}
      {allowed.has("reopen") ? <Button variant="outline" size="sm" onClick={() => setDlg("reopen")} data-testid="q-ncr-reopen">{t("reopen")}</Button> : null}
      {allowed.has("void") ? <Button variant="outline" size="sm" onClick={() => setDlg("void")} data-testid="q-ncr-void">{t("void")}</Button> : null}
      <ReasonDialog open={dlg === "void"} onOpenChange={(v) => setDlg(v ? "void" : "")} title={t("void")} confirm={t("void")} testId="q-ncr-void-dialog"
        onSubmit={(reason) => run(() => unwrap(api.POST("/api/v1/quality/ncrs/{ncr_id}/void", { ...path, body: { reason } })))} />
      <ReasonDialog open={dlg === "reopen"} onOpenChange={(v) => setDlg(v ? "reopen" : "")} title={t("reopen")} confirm={t("reopen")}
        onSubmit={(reason) => run(() => unwrap(api.POST("/api/v1/quality/ncrs/{ncr_id}/reopen", { ...path, body: { reason } })))} />
      <ReasonDialog open={dlg === "implement"} onOpenChange={(v) => setDlg(v ? "implement" : "")} title={t("implement")} label={t("implementationNote")} confirm={t("implement")} testId="q-ncr-implement-dialog"
        onSubmit={(note) => run(() => unwrap(api.POST("/api/v1/quality/ncrs/{ncr_id}/implement", { ...path, body: { implementation_note: note } })))} />
      <ReasonDialog open={dlg === "class"} onOpenChange={(v) => setDlg(v ? "class" : "")} title={t("changeClass")} min={0} description={t("classHint")} confirm={tc("save")}
        onSubmit={(reason) => run(() => unwrap(api.POST("/api/v1/quality/ncrs/{ncr_id}/classification", { ...path, body: { classification: cls as S["QNcrClass"], reason: reason || null } })))} />
      {dlg === "class" ? (
        <Select value={cls} onChange={(e) => setCls(e.target.value)} className="w-40" aria-label={t("classification")} data-testid="q-ncr-class-select">
          {CLASSES.map((c) => <option key={c} value={c}>{c}</option>)}
        </Select>
      ) : null}
    </>
  );
}

/** Responsible-person steps (disposition, concession, close): who signs, and the sign buttons. */
function Steps({ ncr, projectId }: { ncr: Ncr; projectId: string }) {
  const t = useTranslations("quality.ncr");
  const ar = useLocale() === "ar";
  const { step } = useQLabels();
  const { run, busy, error, path } = useNcrRun(ncr.id);
  const [neg, setNeg] = useState<string>("");
  const [paper, setPaper] = useState<string>("");
  const allowed = new Set(ncr.allowed_actions);
  if (!ncr.steps.length) return null;
  const sign = (s: string, decision: "approved" | "returned" | "rejected", comment?: string) =>
    run(() => unwrap(api.POST("/api/v1/quality/ncrs/{ncr_id}/sign", { ...path, body: { step: s as "close", decision, comment: comment ?? null } })), t("signed"));
  return (
    <Card className="mb-4" data-testid="q-ncr-steps">
      <CardContent className="flex flex-col gap-3 p-4">
        <MutationError error={error} />
        {ncr.steps.map((s) => (
          <div key={s.step} className="flex flex-wrap items-center gap-2" data-testid="q-ncr-step" data-step={s.step} data-pending={s.pending}>
            <span className="font-medium">{step("ncr", s.step)}</span>
            <span className="text-sm text-muted-foreground">
              {s.pending ? (s.responsible_set ? t("waitingFor", { who: s.resolvers.map((u) => userText(u, ar)).join(ar ? "، " : ", ") || "—" }) : t("noResponsible")) : t("signedStep")}
            </span>
            {s.pending && allowed.has(`sign:${s.step}`) ? (
              <>
                <Button size="sm" disabled={busy} onClick={() => void sign(s.step, "approved")} data-testid={`q-sign-${s.step}`}>
                  {t("approve")}
                </Button>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => setNeg(s.step)} data-testid={`q-return-${s.step}`}>
                  {s.step === "concession" ? t("reject") : t("return")}
                </Button>
              </>
            ) : null}
            {s.pending && allowed.has(`paper:${s.step}`) ? (
              <Button size="sm" variant="ghost" onClick={() => setPaper(s.step)} data-testid={`q-paper-${s.step}`}>
                {t("paper")}
              </Button>
            ) : null}
          </div>
        ))}
        <ReasonDialog open={Boolean(neg)} onOpenChange={(v) => !v && setNeg("")} title={t("returnTitle")} label={t("comment")} confirm={t("return")}
          onSubmit={(c) => sign(neg, neg === "concession" ? "rejected" : "returned", c)} />
        {paper ? <PaperDialog ncr={ncr} step={paper} onClose={() => setPaper("")} projectId={projectId} /> : null}
      </CardContent>
    </Card>
  );
}

function PaperDialog({ ncr, step, onClose }: { ncr: Ncr; step: string; onClose: () => void; projectId: string }) {
  const t = useTranslations("quality.ncr");
  const tc = useTranslations("quality.common");
  const { run, busy, error, path } = useNcrRun(ncr.id);
  const [f, setF] = useState({ name: "", organisation: "", position: "", signed_on: "" });
  const [file, setFile] = useState<File | null>(null);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  async function go() {
    if (!file) return;
    const b64 = await new Promise<string>((res) => {
      const r = new FileReader();
      r.onload = () => res(String(r.result).split(",")[1] ?? "");
      r.readAsDataURL(file);
    });
    const out = await run(() => unwrap(api.POST("/api/v1/quality/ncrs/{ncr_id}/sign", {
      ...path, body: { step: step as "close", decision: "approved", paper: { ...f, scans: [{ file_name: file.name, content_base64: b64 }] } },
    })), t("signed"));
    if (out) onClose();
  }
  return (
    <div className="glass rounded-lg border p-3" data-testid="q-paper-form">
      <p className="mb-2 text-sm font-medium">{t("paperTitle")}</p>
      <MutationError error={error} />
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="pp-name" label={t("paperName")} required><Input value={f.name} onChange={set("name")} /></FormField>
        <FormField id="pp-org" label={t("paperOrg")} required><Input value={f.organisation} onChange={set("organisation")} /></FormField>
        <FormField id="pp-pos" label={t("paperPosition")} required><Input value={f.position} onChange={set("position")} /></FormField>
        <FormField id="pp-date" label={t("paperDate")} required><Input type="date" value={f.signed_on} onChange={set("signed_on")} /></FormField>
        <FormField id="pp-file" label={t("paperScan")} required className="sm:col-span-2">
          <Input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </FormField>
      </div>
      <div className="mt-3 flex gap-2">
        <Button variant="outline" onClick={onClose}>{tc("cancel")}</Button>
        <Button disabled={busy || !file || !f.name || !f.organisation || !f.position || !f.signed_on} onClick={() => void go()}>{t("paperSave")}</Button>
      </div>
    </div>
  );
}

function Details({ ncr, projectId, canEdit }: { ncr: Ncr; projectId: string; canEdit: boolean }) {
  const t = useTranslations("quality.ncr");
  const { l } = useQLabels();
  const b = useBilingual();
  const ar = useLocale() === "ar";
  const { date, dateTime } = useFormatters(projectId);
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardContent className="p-4">
          <FieldList>
            <FieldItem label={t("requirement")} wide>{b(ncr.requirement_en, ncr.requirement_ar)}</FieldItem>
            <FieldItem label={t("finding")} wide>{b(ncr.finding_en, ncr.finding_ar)}</FieldItem>
            <FieldItem label={t("category")}>{l("ncr_category", ncr.category)}</FieldItem>
            <FieldItem label={t("detectionStage")}>{l("detection_stage", ncr.detection_stage)}</FieldItem>
            <FieldItem label={t("source")}>{l("ncr_source", ncr.source_type)} <span className="ltr">{ncr.source_ref ?? ""}</span></FieldItem>
            <FieldItem label={t("site")}>{ncr.site.code}{ncr.zone ? ` · ${ncr.zone.code}` : ""}</FieldItem>
            <FieldItem label={t("location")}>{ncr.location_ref}</FieldItem>
            <FieldItem label={t("responsible")}>{ncr.responsible_engagement?.short_code ?? "—"}</FieldItem>
            <FieldItem label={t("supplier")}>{ncr.supplier ? `${ncr.supplier.code} — ${ar ? ncr.supplier.name_ar : ncr.supplier.name_en}` : "—"}</FieldItem>
            <FieldItem label={t("quantity")} ltr>{ncr.quantity ? `${ncr.quantity} ${ncr.unit ?? ""}` : "—"}</FieldItem>
            <FieldItem label={t("owner")}>{userText(ncr.owner, ar)}</FieldItem>
            <FieldItem label={t("raisedBy")}>{userText(ncr.raised_by, ar)}</FieldItem>
            <FieldItem label={t("opened")}>{dateTime(ncr.opened_at)}</FieldItem>
            <FieldItem label={t("target")}>{date(ncr.target_close_date)}</FieldItem>
            <FieldItem label={t("containmentDue")}>{dateTime(ncr.containment_due_at)}</FieldItem>
            <FieldItem label={t("age")} ltr>{ncr.age_days ?? "—"}</FieldItem>
            {ncr.closed_at ? <FieldItem label={t("closed")}>{date(ncr.closed_date)} ({t("closureDays", { n: ncr.closure_days ?? 0 })})</FieldItem> : null}
            {ncr.repeat_of ? <FieldItem label={t("repeatOf")}><Link className="ltr underline" href={`/quality/ncrs/${String(ncr.repeat_of.id)}`}>{String(ncr.repeat_of.ncr_no ?? "")}</Link></FieldItem> : null}
            {ncr.effectiveness ? <FieldItem label={t("effectiveness")}>{String(ncr.effectiveness.result ?? ncr.effectiveness.proposed ?? `${t("due")} ${String(ncr.effectiveness.due_on ?? "")}`)}</FieldItem> : null}
          </FieldList>
        </CardContent>
      </Card>
      {!ncr.names_hidden ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card><CardContent className="p-4"><h3 className="mb-2 text-sm font-semibold">{t("photos")}</h3><Attachments ownerType="q_ncr" ownerId={ncr.id} canUpload={canEdit} hint={t("photoHint")} /></CardContent></Card>
          <Card><CardContent className="p-4"><h3 className="mb-2 text-sm font-semibold">{t("evidence")}</h3><Attachments ownerType="q_ncr_evidence" ownerId={ncr.id} canUpload={canEdit} /></CardContent></Card>
        </div>
      ) : null}
    </div>
  );
}

function Containment({ ncr, canEdit }: { ncr: Ncr; canEdit: boolean }) {
  const t = useTranslations("quality.ncr");
  const tc = useTranslations("quality.common");
  const { run, busy, error, path } = useNcrRun(ncr.id);
  const [text, setText] = useState(ncr.containment_en ?? ncr.containment_ar ?? "");
  const [none, setNone] = useState(ncr.no_product_affected);
  const save = (done: boolean) =>
    run(() => unwrap(api.PUT("/api/v1/quality/ncrs/{ncr_id}/containment", { ...path, body: { containment_en: text, no_product_affected: none, done } })));
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 p-4">
        <MutationError error={error} />
        <p className="text-sm text-muted-foreground">{t("containmentHint")}</p>
        <FormField id="cont-text" label={t("containment")}>
          <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} disabled={!canEdit} data-testid="q-containment-text" />
        </FormField>
        {ncr.profile === "logistics" ? <CheckboxField id="cont-none" label={t("noProductAffected")}><Checkbox checked={none} onChange={(e) => setNone(e.target.checked)} /></CheckboxField> : null}
        {ncr.containment_done_at ? <p className="text-sm text-success">{t("containmentDone")}</p> : null}
        {canEdit ? (
          <div className="flex gap-2">
            <Button variant="outline" disabled={busy} onClick={() => void save(false)}>{tc("save")}</Button>
            <Button disabled={busy || !text.trim()} onClick={() => void save(true)} data-testid="q-containment-done">{t("markContained")}</Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

const M6 = ["people", "machine", "method", "material", "measurement", "environment"];

function Rca({ ncr, projectId, canEdit }: { ncr: Ncr; projectId: string; canEdit: boolean }) {
  const t = useTranslations("quality.ncr");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const users = useUserOptions(projectId);
  const { run, busy, error, path } = useNcrRun(ncr.id);
  const r = ncr.rca;
  const d = (r?.data ?? {}) as Record<string, unknown>;
  const [method, setMethod] = useState<string>(r?.method ?? (ncr.classification === "critical" ? "eight_d" : ncr.classification === "major" ? "five_why" : "simple"));
  const [cause, setCause] = useState<string>(r?.cause_category ?? "");
  const [simple, setSimple] = useState(String(d.cause ?? ""));
  const [whys, setWhys] = useState<string[]>(Array.isArray(d.whys) ? (d.whys as string[]) : ["", "", ""]);
  const [root, setRoot] = useState(String(d.root_cause ?? r?.root_cause ?? ""));
  const [causes, setCauses] = useState<{ category: string; text: string; root?: boolean }[]>(Array.isArray(d.causes) ? (d.causes as never) : [{ category: "method", text: "", root: true }, { category: "people", text: "" }]);
  const [e8, setE8] = useState<Record<string, unknown>>(method === "eight_d" ? d : { d2_problem: {} });
  const d2 = (e8.d2_problem ?? {}) as Record<string, string>;
  const set8 = (k: string, v: unknown) => setE8((x) => ({ ...x, [k]: v }));
  function data() {
    if (method === "simple") return { cause: simple };
    if (method === "five_why") return { whys: whys.filter((w) => w.trim()), root_cause: root };
    if (method === "ishikawa") return { causes };
    return e8;
  }
  const save = (final: boolean) =>
    run(() => unwrap(api.PUT("/api/v1/quality/ncrs/{ncr_id}/rca", { ...path, body: { method: method as S["QRcaMethod"], cause_category: (cause || null) as S["QCauseCategory"] | null, data: data(), root_cause: root || null, final } })));
  const dis = !canEdit;
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 p-4" data-testid="q-rca">
        <MutationError error={error} />
        <p className="text-sm text-muted-foreground">{t("rcaHint")}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField id="rca-method" label={t("rcaMethod")}>
            <Select value={method} onChange={(e) => setMethod(e.target.value)} disabled={dis} data-testid="q-rca-method">
              {options("rca_method").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          </FormField>
          <FormField id="rca-cause" label={t("causeCategory")}>
            <Select value={cause} onChange={(e) => setCause(e.target.value)} disabled={dis} data-testid="q-rca-cause">
              <option value="">{tc("select")}</option>
              {M6.map((c) => <option key={c} value={c}>{l("cause_category", c)}</option>)}
            </Select>
          </FormField>
        </div>
        {method === "simple" ? (
          <FormField id="rca-simple" label={t("causeStatement")} hint={tc("minChars", { n: 30 })}>
            <Textarea value={simple} onChange={(e) => setSimple(e.target.value)} rows={3} disabled={dis} data-testid="q-rca-simple" />
          </FormField>
        ) : null}
        {method === "five_why" ? (
          <div className="flex flex-col gap-2">
            {whys.map((w, i) => (
              <FormField key={i} id={`why-${i}`} label={t("why", { n: i + 1 })}>
                <Input value={w} onChange={(e) => setWhys((x) => x.map((y, j) => (j === i ? e.target.value : y)))} disabled={dis} data-testid={`q-why-${i}`} />
              </FormField>
            ))}
            {!dis && whys.length < 7 ? <Button size="sm" variant="outline" className="self-start" onClick={() => setWhys((x) => [...x, ""])}>{t("addWhy")}</Button> : null}
            <FormField id="why-root" label={t("rootCause")}>
              <Input value={root} onChange={(e) => setRoot(e.target.value)} disabled={dis} data-testid="q-why-root" />
            </FormField>
          </div>
        ) : null}
        {method === "ishikawa" ? (
          <div className="flex flex-col gap-2">
            {causes.map((c, i) => (
              <div key={i} className="grid gap-2 sm:grid-cols-[10rem_1fr_auto]">
                <Select value={c.category} onChange={(e) => setCauses((x) => x.map((y, j) => (j === i ? { ...y, category: e.target.value } : y)))} disabled={dis} aria-label={t("causeCategory")}>
                  {M6.map((m) => <option key={m} value={m}>{l("cause_category", m)}</option>)}
                </Select>
                <Input value={c.text} onChange={(e) => setCauses((x) => x.map((y, j) => (j === i ? { ...y, text: e.target.value } : y)))} disabled={dis} aria-label={t("cause")} />
                <CheckboxField id={`root-${i}`} label={t("root")}><Checkbox checked={Boolean(c.root)} onChange={(e) => setCauses((x) => x.map((y, j) => (j === i ? { ...y, root: e.target.checked } : y)))} /></CheckboxField>
              </div>
            ))}
            {!dis ? <Button size="sm" variant="outline" className="self-start" onClick={() => setCauses((x) => [...x, { category: "method", text: "" }])}>{t("addCause")}</Button> : null}
          </div>
        ) : null}
        {method === "eight_d" ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField id="d1" label={t("d1")} className="sm:col-span-2">
              <Select multiple value={(e8.d1_team as string[] | undefined) ?? []} onChange={(e) => set8("d1_team", Array.from(e.target.selectedOptions).map((o) => o.value))} disabled={dis} className="min-h-24">
                {users.map((u) => <option key={u.value} value={u.value}>{u.label}</option>)}
              </Select>
            </FormField>
            {(["what", "where", "when", "how_many", "is_not"] as const).map((k) => (
              <FormField key={k} id={`d2-${k}`} label={t(`d2.${k}`)}>
                <Input value={d2[k] ?? ""} onChange={(e) => set8("d2_problem", { ...d2, [k]: e.target.value })} disabled={dis} />
              </FormField>
            ))}
            {(["d3_containment", "d4_root_cause", "d4_escape_point", "d7_prevention", "d8_closure"] as const).map((k) => (
              <FormField key={k} id={k} label={t(`d8.${k}`)} className="sm:col-span-2">
                <Textarea rows={2} value={String(e8[k] ?? "")} onChange={(e) => set8(k, e.target.value)} disabled={dis} />
              </FormField>
            ))}
            <FormField id="d6a" label={t("d8.d6_implemented_on")}><Input type="date" value={String(e8.d6_implemented_on ?? "")} onChange={(e) => set8("d6_implemented_on", e.target.value)} disabled={dis} /></FormField>
            <FormField id="d6b" label={t("d8.d6_validated_on")}><Input type="date" value={String(e8.d6_validated_on ?? "")} onChange={(e) => set8("d6_validated_on", e.target.value)} disabled={dis} /></FormField>
          </div>
        ) : null}
        {r ? <p className="text-xs text-muted-foreground">{r.complete ? t("rcaComplete") : t("rcaDraft")}</p> : null}
        {canEdit ? (
          <div className="flex gap-2">
            <Button variant="outline" disabled={busy} onClick={() => void save(false)}>{t("saveDraft")}</Button>
            <Button disabled={busy} onClick={() => void save(true)} data-testid="q-rca-save">{t("rcaSave")}</Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Disposition({ ncr, canEdit, canEvidence }: { ncr: Ncr; canEdit: boolean; canEvidence: boolean }) {
  const t = useTranslations("quality.ncr");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const { run, busy, error, path } = useNcrRun(ncr.id);
  const [lines, setLines] = useState(ncr.disposition_lines.length ? ncr.disposition_lines.map((x) => ({ disposition: x.disposition as string, quantity: x.quantity ?? "", note: x.note ?? "", repair_procedure: x.repair_procedure ?? "", evidenced: Boolean(x.destruction_evidenced) })) : [{ disposition: "rework", quantity: ncr.quantity ?? "", note: "", repair_procedure: "", evidenced: false }]);
  const [just, setJust] = useState(ncr.disposition_justification_en ?? "");
  const save = () =>
    run(() => unwrap(api.PUT("/api/v1/quality/ncrs/{ncr_id}/disposition", {
      ...path, body: { lines: lines.map((x) => ({ disposition: x.disposition as S["QDisposition"], quantity: x.quantity || null, note: x.note || null, repair_procedure: x.repair_procedure || null, destruction_evidenced: x.evidenced })), disposition_justification_en: just || null },
    })));
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 p-4" data-testid="q-disposition">
        <MutationError error={error} />
        {canEdit ? (
          <>
            {lines.map((x, i) => (
              <div key={i} className="grid gap-2 sm:grid-cols-[12rem_7rem_1fr]">
                <Select value={x.disposition} onChange={(e) => setLines((ls) => ls.map((y, j) => (j === i ? { ...y, disposition: e.target.value } : y)))} aria-label={t("disposition")} data-testid={`q-line-disp-${i}`}>
                  {options("disposition").map((o) => <option key={o.value} value={o.value}>{ncr.profile === "logistics" && o.value === "use_as_is" ? l("disposition_logistics", "use_as_is") : o.label}</option>)}
                </Select>
                <Input value={x.quantity} onChange={(e) => setLines((ls) => ls.map((y, j) => (j === i ? { ...y, quantity: e.target.value } : y)))} placeholder={t("quantity")} inputMode="decimal" className="ltr" data-testid={`q-line-qty-${i}`} />
                <Input value={x.disposition === "repair" ? x.repair_procedure : x.note} onChange={(e) => setLines((ls) => ls.map((y, j) => (j === i ? (y.disposition === "repair" ? { ...y, repair_procedure: e.target.value } : { ...y, note: e.target.value }) : y)))} placeholder={x.disposition === "repair" ? t("repairProcedure") : t("note")} />
              </div>
            ))}
            <Button size="sm" variant="outline" className="self-start" onClick={() => setLines((ls) => [...ls, { disposition: "rework", quantity: "", note: "", repair_procedure: "", evidenced: false }])}>{t("addLine")}</Button>
            <FormField id="disp-just" label={t("justification")} hint={t("justificationHint")}>
              <Textarea value={just} onChange={(e) => setJust(e.target.value)} rows={3} data-testid="q-disp-justification" />
            </FormField>
            <Button className="self-start" disabled={busy} onClick={() => void save()} data-testid="q-disp-save">{tc("save")}</Button>
          </>
        ) : ncr.disposition_lines.length ? (
          <Table compact stack={false}>
            <THead><TR><TH>{t("disposition")}</TH><TH>{t("quantity")}</TH><TH>{t("note")}</TH><TH>{t("lineEvidence")}</TH></TR></THead>
            <TBody>
              {ncr.disposition_lines.map((x) => (
                <TR key={x.id}>
                  <TD>{ncr.profile === "logistics" && x.disposition === "use_as_is" ? l("disposition_logistics", "use_as_is") : l("disposition", x.disposition)}</TD>
                  <TD className="ltr">{x.quantity ?? "—"}</TD>
                  <TD>{x.repair_procedure ?? x.note ?? "—"}</TD>
                  <TD><LineEvidence line={x} canEdit={canEvidence} /></TD>
                </TR>
              ))}
            </TBody>
          </Table>
        ) : (
          <EmptyState message={t("noLines")} />
        )}
        {ncr.disposition_justification_en ? <p className="text-sm" dir="auto">{ncr.disposition_justification_en}</p> : null}
      </CardContent>
    </Card>
  );
}

function LineEvidence({ line, canEdit }: { line: Ncr["disposition_lines"][number]; canEdit: boolean }) {
  const t = useTranslations("quality.ncr");
  const { run, busy } = useRun();
  const [ref, setRef] = useState(line.return_ref ?? "");
  const p = { params: { path: { line_id: line.id } } };
  if (line.disposition === "reject_return")
    return canEdit ? (
      <span className="flex gap-1">
        <Input value={ref} onChange={(e) => setRef(e.target.value)} placeholder={t("returnRef")} className="h-9 w-36" />
        <Button size="sm" disabled={busy || !ref} onClick={() => void run(() => unwrap(api.PATCH("/api/v1/quality/ncr-lines/{line_id}", { ...p, body: { return_ref: ref } })))}>{t("saveShort")}</Button>
      </span>
    ) : <span className="ltr">{line.return_ref ?? "—"}</span>;
  if (line.disposition === "reject_scrap")
    return line.destruction_evidenced ? <span className="text-success">{t("evidenced")}</span> : canEdit ? (
      <Button size="sm" variant="outline" disabled={busy} onClick={() => void run(() => unwrap(api.PATCH("/api/v1/quality/ncr-lines/{line_id}", { ...p, body: { destruction_evidenced: true } })))}>{t("markDestroyed")}</Button>
    ) : <>—</>;
  return <>—</>;
}

function Actions({ ncr, projectId, canAdd }: { ncr: Ncr; projectId: string; canAdd: boolean }) {
  const t = useTranslations("quality.ncr");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const { date } = useFormatters(projectId);
  const { run, busy, error, path } = useNcrRun(ncr.id);
  const [f, setF] = useState({ title: "", description: "", control_level: "administrative", owner_id: "", verifier_id: "", due_date: "" });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const add = () =>
    run(() => unwrap(api.POST("/api/v1/quality/ncrs/{ncr_id}/actions", { ...path, body: { ...f, control_level: f.control_level as S["ControlLevel"], due_date: f.due_date || null } })));
  return (
    <div className="flex flex-col gap-4">
      {ncr.actions.length ? (
        <Table compact data-testid="q-ncr-actions">
          <THead><TR><TH>{t("caRef")}</TH><TH>{t("titleField")}</TH><TH>{tc("status")}</TH><TH>{t("controlLevel")}</TH><TH>{t("due")}</TH></TR></THead>
          <TBody>
            {ncr.actions.map((a) => (
              <TR key={a.id}>
                <TD label={t("caRef")}><Link href={`/actions/${a.id}`} className="ltr text-primary hover:underline">{a.ref}</Link></TD>
                <TD label={t("titleField")} dir="auto">{a.title}</TD>
                <TD label={tc("status")}>{a.status}</TD>
                <TD label={t("controlLevel")}>{l("control_level_quality", a.control_level)}</TD>
                <TD label={t("due")}>{date(a.due_date)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <EmptyState message={t("noActions")} />
      )}
      {canAdd ? (
        <Card>
          <CardContent className="grid gap-3 p-4 sm:grid-cols-2" data-testid="q-ca-form">
            <MutationError error={error} />
            <FormField id="ca-title" label={t("titleField")} required className="sm:col-span-2"><Input value={f.title} onChange={set("title")} data-testid="q-ca-title" /></FormField>
            <FormField id="ca-desc" label={t("caDescription")} required className="sm:col-span-2"><Textarea value={f.description} onChange={set("description")} rows={2} data-testid="q-ca-description" /></FormField>
            <FormField id="ca-control" label={t("controlLevel")}>
              <Select value={f.control_level} onChange={set("control_level")} data-testid="q-ca-control">
                {options("control_level_quality").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
            </FormField>
            <FormField id="ca-due" label={t("due")}><Input type="date" value={f.due_date} onChange={set("due_date")} /></FormField>
            <FormField id="ca-owner" label={t("caOwner")} required><UserSelect projectId={projectId} value={f.owner_id} onChange={set("owner_id")} data-testid="q-ca-owner" /></FormField>
            <FormField id="ca-verifier" label={t("caVerifier")} required hint={t("caVerifierHint")}><UserSelect projectId={projectId} value={f.verifier_id} onChange={set("verifier_id")} data-testid="q-ca-verifier" /></FormField>
            <Button className="self-start" disabled={busy || !f.title || !f.description || !f.owner_id || !f.verifier_id} onClick={() => void add()} data-testid="q-ca-add">{t("addAction")}</Button>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function Costs({ ncr, canEdit }: { ncr: Ncr; canEdit: boolean }) {
  const t = useTranslations("quality.ncr");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const { run, busy, error, path } = useNcrRun(ncr.id);
  const [f, setF] = useState({ cost_type: "rework_labour", quantity: "", rate_sar: "", recovered_sar: "", description: "" });
  const [noCost, setNoCost] = useState(false);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const add = () =>
    run(() => unwrap(api.POST("/api/v1/quality/ncrs/{ncr_id}/costs", { ...path, body: { cost_type: f.cost_type as S["QCostType"], quantity: f.quantity || null, rate_sar: f.rate_sar || null, recovered_sar: f.recovered_sar || null, description: f.description || null, recoverable: Boolean(f.recovered_sar) } })));
  return (
    <div className="flex flex-col gap-4">
      <MutationError error={error} />
      <Card>
        <CardContent className="p-4">
          <FieldList>
            <FieldItem label={t("costGross")} ltr>{ncr.cost_gross_sar ?? "—"}</FieldItem>
            <FieldItem label={t("costRecovered")} ltr>{ncr.cost_recovered_sar ?? "—"}</FieldItem>
            <FieldItem label={t("costNet")} ltr>{ncr.cost_net_sar ?? "—"}</FieldItem>
            <FieldItem label={t("failureClass")}>{ncr.failure_class ? t(`failure.${ncr.failure_class}`) : "—"}</FieldItem>
            {ncr.no_cost_reason ? <FieldItem label={t("noCost")} wide>{ncr.no_cost_reason}</FieldItem> : null}
          </FieldList>
        </CardContent>
      </Card>
      {ncr.cost_lines_visible && ncr.cost_lines.length ? (
        <Table compact data-testid="q-cost-lines">
          <THead><TR><TH>{t("costType")}</TH><TH>{t("quantity")}</TH><TH>{t("rate")}</TH><TH>{t("amount")}</TH><TH>{t("recovered")}</TH><TH /></TR></THead>
          <TBody>
            {ncr.cost_lines.map((c) => (
              <TR key={c.id}>
                <TD label={t("costType")}>{l("cost_type", c.cost_type)}</TD>
                <TD label={t("quantity")} className="ltr">{c.quantity} {c.unit ?? ""}</TD>
                <TD label={t("rate")} className="ltr">{c.rate_sar}</TD>
                <TD label={t("amount")} className="ltr font-medium">{c.amount_sar}</TD>
                <TD label={t("recovered")} className="ltr">{c.recovered_sar}</TD>
                <TD>{canEdit ? <Button size="sm" variant="ghost" disabled={busy} onClick={() => void run(() => unwrap(api.DELETE("/api/v1/quality/ncr-costs/{cost_id}", { params: { path: { cost_id: c.id } } })))}>{tc("delete")}</Button> : null}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : null}
      {canEdit ? (
        <Card>
          <CardContent className="grid gap-3 p-4 sm:grid-cols-5" data-testid="q-cost-form">
            <FormField id="cost-type" label={t("costType")}>
              <Select value={f.cost_type} onChange={set("cost_type")} data-testid="q-cost-type">
                {options("cost_type").map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
            </FormField>
            <FormField id="cost-qty" label={t("quantity")}><Input value={f.quantity} onChange={set("quantity")} inputMode="decimal" className="ltr" data-testid="q-cost-qty" /></FormField>
            <FormField id="cost-rate" label={t("rate")} hint={t("rateHint")}><Input value={f.rate_sar} onChange={set("rate_sar")} inputMode="decimal" className="ltr" data-testid="q-cost-rate" /></FormField>
            <FormField id="cost-rec" label={t("recovered")}><Input value={f.recovered_sar} onChange={set("recovered_sar")} inputMode="decimal" className="ltr" /></FormField>
            <div className="flex items-end gap-2">
              <Button disabled={busy} onClick={() => void add()} data-testid="q-cost-add">{t("addCost")}</Button>
            </div>
            <div className="sm:col-span-5">
              <Button variant="ghost" size="sm" onClick={() => setNoCost(true)} data-testid="q-no-cost">{t("noCostButton")}</Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
      <ReasonDialog open={noCost} onOpenChange={setNoCost} title={t("noCostButton")} confirm={tc("save")}
        onSubmit={(reason) => run(() => unwrap(api.POST("/api/v1/quality/ncrs/{ncr_id}/no-cost", { ...path, body: { reason } })))} />
    </div>
  );
}

function SupplierResponse({ ncr, canEdit }: { ncr: Ncr; canEdit: boolean }) {
  const t = useTranslations("quality.ncr");
  const { run, busy, error, path } = useNcrRun(ncr.id);
  const sr = (ncr.supplier_response ?? {}) as Record<string, unknown>;
  const act = (action: "request" | "receive" | "accept" | "reject") =>
    run(() => unwrap(api.POST("/api/v1/quality/ncrs/{ncr_id}/supplier-response", { ...path, body: { action } })));
  if (!ncr.supplier) return <EmptyState message={t("noSupplier")} />;
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 p-4" data-testid="q-scar">
        <MutationError error={error} />
        <FieldList>
          <FieldItem label={t("scarRequested")}>{String(sr.requested_at ?? "—")}</FieldItem>
          <FieldItem label={t("scarDue")} ltr>{String(sr.due_on ?? "—")}</FieldItem>
          <FieldItem label={t("scarReceived")}>{String(sr.received_at ?? "—")}</FieldItem>
          <FieldItem label={t("scarDecision")}>{sr.accepted === true ? t("accepted") : sr.accepted === false ? t("rejected") : "—"}</FieldItem>
        </FieldList>
        {canEdit ? (
          <div className="flex flex-wrap gap-2">
            {!sr.requested_at ? <Button disabled={busy} onClick={() => void act("request")} data-testid="q-scar-request">{t("scarRequest")}</Button> : null}
            {sr.requested_at && !sr.received_at ? <Button disabled={busy} onClick={() => void act("receive")}>{t("scarReceive")}</Button> : null}
            {sr.received_at && sr.accepted == null ? (
              <>
                <Button disabled={busy} onClick={() => void act("accept")}>{t("accept")}</Button>
                <Button variant="outline" disabled={busy} onClick={() => void act("reject")}>{t("reject")}</Button>
              </>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Signoffs({ ncr }: { ncr: Ncr }) {
  const t = useTranslations("quality.ncr");
  const ar = useLocale() === "ar";
  const { dateTime } = useFormatters();
  const { step } = useQLabels();
  if (!ncr.signoffs.length) return <EmptyState message={t("noSignoffs")} />;
  return (
    <ul className="flex flex-col gap-2" data-testid="q-signoffs">
      {ncr.signoffs.map((s) => (
        <li key={s.id} className="glass rounded-lg border p-3 text-sm" data-step={s.step} data-channel={s.channel}>
          <p className="font-medium">{step("ncr", s.step)} · {s.decision}</p>
          <p>{ar ? s.text_ar : s.text_en}</p>
          <p className="text-xs text-muted-foreground">{dateTime(s.signed_at)}{s.comment ? ` — ${s.comment}` : ""}</p>
        </li>
      ))}
    </ul>
  );
}

function Links({ ncr }: { ncr: Ncr }) {
  const t = useTranslations("quality.ncr");
  const { l, recordType } = useQLabels();
  if (!ncr.links.length) return <EmptyState message={t("noLinks")} />;
  return (
    <ul className="flex flex-col gap-2" data-testid="q-links">
      {ncr.links.map((k) => (
        <li key={k.id} className="glass flex flex-wrap items-center gap-2 rounded-lg border p-3 text-sm">
          <span className="text-muted-foreground">{l("link_kind", k.kind)}</span>
          <span>{recordType(k.record_type)}</span>
          {k.visible && k.link_path ? <Link href={k.link_path} className="ltr text-primary hover:underline">{k.ref}</Link> : <span>{t("notVisible")}</span>}
          {k.voided ? <span className="text-xs text-danger">{t("voided")}</span> : null}
        </li>
      ))}
    </ul>
  );
}
