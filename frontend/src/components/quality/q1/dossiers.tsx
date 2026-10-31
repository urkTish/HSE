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
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { CheckboxField, FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Link, useRouter } from "@/i18n/navigation";
import { api, downloadFile, unwrap } from "@/lib/api/client";
import { useQSystems } from "@/lib/api/quality/q0";
import { useQDossier, useQDossiers } from "@/lib/api/quality/q1";
import { useFormatters } from "@/lib/use-formatters";
import { QGate, useBilingual, useQCaps, useQLabels, useRun, userText, type Project, type S } from "../q0/common";
import { BlockerList, emptyPaper, LinkList, PaperFields, paperReady, Q1Status, SignoffList } from "./shared";

type Dossier = S["QDossierRead"];

export function DossierListPage() {
  return <QGate>{(p) => <List project={p} />}</QGate>;
}

function List({ project }: { project: Project }) {
  const t = useTranslations("quality.q1.dossier");
  const tc = useTranslations("quality.common");
  const b = useBilingual();
  const caps = useQCaps(project.id);
  const { date } = useFormatters(project.id);
  const r = useQDossiers(project.id, { page_size: 100 });
  const items = r.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")}
        actions={caps.write("dossier.compile") ? <Button asChild data-testid="q1-dossier-new"><Link href="/quality/dossiers/new"><Plus aria-hidden />{t("new")}</Link></Button> : null} />
      {r.isLoading ? <LoadingState /> : r.isError ? <ErrorState error={r.error} onRetry={() => r.refetch()} /> : items.length ? (
        <Table compact data-testid="q1-dossier-table">
          <THead><TR><TH>{t("no")}</TH><TH>{t("titleField")}</TH><TH>{t("scope")}</TH><TH>{tc("status")}</TH><TH>{t("compiled")}</TH></TR></THead>
          <TBody>
            {items.map((d) => (
              <TR key={d.id} data-testid="q1-dossier-row" data-status={d.status}>
                <TD label={t("no")}><Link href={`/quality/dossiers/${d.id}`} className="ltr font-medium text-primary hover:underline">{d.dossier_no} Rev.{d.revision}</Link></TD>
                <TD label={t("titleField")} data-full=""><span dir="auto">{b(d.title_en, d.title_ar)}</span></TD>
                <TD label={t("scope")}>{d.zones.map((z) => z.code).join(", ")}{d.system_ids.length ? ` +${d.system_ids.length}` : ""}</TD>
                <TD label={tc("status")}><Q1Status kind="dossier_status" value={d.status} /></TD>
                <TD label={t("compiled")}>{date(d.compiled_at)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : <EmptyState message={t("empty")} />}
    </div>
  );
}

export function DossierNewPage() {
  return <QGate>{(p) => <NewDossier project={p} />}</QGate>;
}

function NewDossier({ project }: { project: Project }) {
  const t = useTranslations("quality.q1.dossier");
  const tc = useTranslations("quality.common");
  const ar = useLocale() === "ar";
  const opts = useProjectOptions(project.id);
  const systems = useQSystems(project.id);
  const router = useRouter();
  const { run, busy, error } = useRun();
  const [f, setF] = useState({ title_en: "", title_ar: "" });
  const [zones, setZones] = useState<string[]>([]);
  const [sys, setSys] = useState<string[]>([]);
  async function go() {
    const out = await run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/dossiers", { params: { path: { project_id: project.id } }, body: { ...f, zone_ids: zones, system_ids: sys } })));
    if (out) router.push(`/quality/dossiers/${out.id}`);
  }
  return (
    <div data-testid="q1-dossier-form">
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/dossiers" }, { label: t("new") }]} />
      <PageHeader title={t("new")} description={t("newHint")} />
      <MutationError error={error} />
      <FormSection title={t("scope")}>
        <FormField id="ds-en" label={t("titleEn")} required><Input value={f.title_en} onChange={(e) => setF((x) => ({ ...x, title_en: e.target.value }))} data-testid="q1-dossier-title-en" /></FormField>
        <FormField id="ds-ar" label={t("titleAr")} required><Input dir="rtl" value={f.title_ar} onChange={(e) => setF((x) => ({ ...x, title_ar: e.target.value }))} data-testid="q1-dossier-title-ar" /></FormField>
        <MultiSelect id="ds-zones" label={t("zones")} value={zones} onChange={setZones} options={opts.zones.map((z) => ({ value: z.value, label: z.label }))} allLabel={tc("select")} testId="q1-dossier-zones" />
        <MultiSelect id="ds-sys" label={t("systems")} value={sys} onChange={setSys} options={(systems.data ?? []).map((x) => ({ value: x.id, label: `${x.code} — ${ar ? x.name_ar : x.name_en}` }))} allLabel={tc("select")} />
      </FormSection>
      <Button className="mt-4" disabled={busy || !f.title_en || !f.title_ar || (!zones.length && !sys.length)} onClick={() => void go()} data-testid="q1-dossier-create">{t("create")}</Button>
    </div>
  );
}

export function DossierDetailPage({ id }: { id: string }) {
  return <QGate>{(p) => <Detail project={p} id={id} />}</QGate>;
}

function Detail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.q1.dossier");
  const tc = useTranslations("quality.common");
  const ar = useLocale() === "ar";
  const b = useBilingual();
  const { l } = useQLabels();
  const { dateTime } = useFormatters(project.id);
  const router = useRouter();
  const q = useQDossier(id);
  const { run, busy, error } = useRun();
  const [decide, setDecide] = useState(false);
  const [comment, setComment] = useState("");
  const [paper, setPaper] = useState(false);
  const [pp, setPp] = useState(emptyPaper());
  const [ab, setAb] = useState({ drawing_no: "", title: "", revision: "0", status: "submitted" });
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data;
  if (!d) return null;
  const allowed = new Set(d.allowed_actions);
  const path = { params: { path: { dossier_id: d.id } } };
  const base = `${d.dossier_no}-Rev${d.revision}`;
  const sections = new Set(d.sections);
  async function toggleSection(code: string, on: boolean) {
    const next = on ? [...d!.sections, code] : d!.sections.filter((x) => x !== code);
    await run(() => unwrap(api.PATCH("/api/v1/quality/dossiers/{dossier_id}", { ...path, body: { sections: next } })));
  }
  async function decideGo(decision: "approved" | "returned") {
    const out = await run(() => unwrap(api.POST("/api/v1/quality/dossiers/{dossier_id}/decide", { ...path, body: { decision, comment: comment || null, paper: paper ? pp : null } })), decision === "approved" ? t("acceptedToast") : t("returnedToast"));
    if (out) setDecide(false);
  }
  return (
    <div data-testid="q1-dossier-detail" data-status={d.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/dossiers" }, { label: `${d.dossier_no} Rev.${d.revision}` }]} />
      <PageHeader
        title={<span className="ltr">{d.dossier_no} Rev.{d.revision}</span>}
        badge={<Q1Status kind="dossier_status" value={d.status} />}
        description={b(d.title_en, d.title_ar)}
        actions={
          <div className="flex flex-wrap justify-end gap-2">
            {allowed.has("compile") ? <Button disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/dossiers/{dossier_id}/compile", path)), t("compiledToast"))} data-testid="q1-dossier-compile">{t("compile")}</Button> : null}
            {allowed.has("submit") ? <Button disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/dossiers/{dossier_id}/submit", path)), t("submittedToast"))} data-testid="q1-dossier-submit">{t("submit")}</Button> : null}
            {allowed.has("decide") || allowed.has("paper_signoff") ? <Button onClick={() => { setDecide((v) => !v); setPaper(!allowed.has("decide")); }} data-testid="q1-dossier-decide">{t("decide")}</Button> : null}
            {allowed.has("reopen") ? <Button variant="outline" disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/dossiers/{dossier_id}/reopen", path)))}>{t("reopen")}</Button> : null}
            {allowed.has("new_revision") ? (
              <Button variant="outline" disabled={busy} onClick={async () => { const r = await run(() => unwrap(api.POST("/api/v1/quality/dossiers/{dossier_id}/revisions", path))); if (r) router.push(`/quality/dossiers/${r.id}`); }} data-testid="q1-dossier-new-rev">{t("newRevision")}</Button>
            ) : null}
            {allowed.has("download_index") ? (
              <>
                <Button variant="outline" onClick={() => void downloadFile(`/api/v1/quality/dossiers/${d.id}/index?lang=en`, `${base}-index-EN.pdf`)} data-testid="q1-dossier-index-en"><Download aria-hidden />{t("indexEn")}</Button>
                <Button variant="outline" onClick={() => void downloadFile(`/api/v1/quality/dossiers/${d.id}/index?lang=ar`, `${base}-index-AR.pdf`)} data-testid="q1-dossier-index-ar"><Download aria-hidden />{t("indexAr")}</Button>
              </>
            ) : null}
            {allowed.has("download_package") ? <Button variant="outline" onClick={() => void downloadFile(`/api/v1/quality/dossiers/${d.id}/package`, `${base}.zip`)} data-testid="q1-dossier-zip"><Download aria-hidden />{t("package")}</Button> : null}
          </div>
        }
      />
      <MutationError error={error} />
      {d.status === "returned" && d.status_reason ? <Alert tone="warning" className="mb-3">{t("returnedBecause", { reason: d.status_reason })}</Alert> : null}
      {decide ? (
        <Card className="mb-4" data-testid="q1-dossier-decide-form">
          <CardContent className="flex flex-col gap-3 p-4">
            <FormField id="ds-comment" label={t("comment")} hint={t("returnNeedsComment")}><Textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={2} data-testid="q1-dossier-comment" /></FormField>
            {allowed.has("decide") ? <CheckboxField id="ds-paper" label={t("paperInstead")}><Checkbox checked={paper} onChange={(e) => setPaper(e.target.checked)} /></CheckboxField> : null}
            {paper ? <PaperFields value={pp} onChange={setPp} /> : null}
            <div className="flex gap-2">
              <Button disabled={busy || (paper && !paperReady(pp))} onClick={() => void decideGo("approved")} data-testid="q1-dossier-accept">{t("accept")}</Button>
              <Button variant="outline" disabled={busy || comment.trim().length < 20 || (paper && !paperReady(pp))} onClick={() => void decideGo("returned")} data-testid="q1-dossier-return">{t("return")}</Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
      {d.blockers.length ? (
        <Alert tone="danger" className="mb-3"><p className="font-medium">{t("blockers", { n: d.blockers.length })}</p><BlockerList items={d.blockers} testId="q1-dossier-blockers" /></Alert>
      ) : d.status !== "accepted" ? <Alert tone="success" className="mb-3" data-testid="q1-dossier-no-blockers">{t("noBlockers")}</Alert> : null}
      {d.warnings.length ? <div className="mb-3"><p className="mb-1 text-sm font-medium">{t("warnings")}</p><BlockerList items={d.warnings} tone="warning" testId="q1-dossier-warnings" /></div> : null}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardContent className="p-4">
            <FieldList className="lg:grid-cols-2">
              <FieldItem label={t("zones")}>{d.zones.map((z) => z.code).join(", ") || "—"}</FieldItem>
              <FieldItem label={t("systems")}>{d.systems.map((z) => z.code).join(", ") || "—"}</FieldItem>
              <FieldItem label={t("compiled")}>{dateTime(d.compiled_at)} {d.compiled_by ? `· ${userText(d.compiled_by, ar)}` : ""}</FieldItem>
              <FieldItem label={t("sha")} ltr>{d.package_sha256 ? `${d.package_sha256.slice(0, 16)}…` : "—"}</FieldItem>
              {d.responsible.length ? <FieldItem label={t("acceptor")} wide>{d.responsible.map((u) => userText(u, ar)).join(", ")}</FieldItem> : null}
            </FieldList>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex flex-col gap-2 p-4" data-testid="q1-dossier-sections">
            <p className="text-sm font-medium">{t("sections")}</p>
            {d.available_sections.map((s) => {
              const snap = d.snapshot_sections.find((x) => x.code === s.code);
              return (
                <label key={s.code} className="flex min-h-touch items-center gap-3 text-sm">
                  <Checkbox checked={sections.has(s.code)} disabled={!allowed.has("edit") || busy} onChange={(e) => void toggleSection(s.code, e.target.checked)} />
                  <span>{ar ? s.title_ar || l("dossier_section", s.code) : s.title_en || l("dossier_section", s.code)}</span>
                  {snap ? <span className="ms-auto text-xs text-muted-foreground">{t("itemsFiles", { items: snap.item_count, files: snap.file_count })}</span> : null}
                </label>
              );
            })}
          </CardContent>
        </Card>
      </div>
      <section className="mt-6" data-testid="q1-asbuilt">
        <h2 className="mb-2 text-base font-semibold">{t("asbuilt")}</h2>
        {d.asbuilt.length ? (
          <Table compact>
            <THead><TR><TH>{t("drawingNo")}</TH><TH>{t("titleField")}</TH><TH>{t("rev")}</TH><TH>{tc("status")}</TH><TH /></TR></THead>
            <TBody>
              {d.asbuilt.map((a) => (
                <TR key={a.id} data-testid="q1-asbuilt-row">
                  <TD label={t("drawingNo")} className="ltr">{a.drawing_no}</TD>
                  <TD label={t("titleField")}>{a.title}</TD>
                  <TD label={t("rev")} className="ltr">{a.revision}</TD>
                  <TD label={tc("status")}><Q1Status kind="asbuilt_status" value={a.status} /></TD>
                  <TD label="">{allowed.has("asbuilt") && a.status !== "approved" ? (
                    <Button size="sm" variant="outline" disabled={busy} onClick={() => void run(() => unwrap(api.PATCH("/api/v1/quality/asbuilt/{item_id}", { params: { path: { item_id: a.id } }, body: { status: "approved", delete: false } })))} data-testid="q1-asbuilt-approve">{t("approveDrawing")}</Button>
                  ) : null}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        ) : <EmptyState message={t("asbuiltEmpty")} />}
        {allowed.has("asbuilt") ? (
          <div className="mt-3 grid gap-2 sm:grid-cols-5">
            <Input placeholder={t("drawingNo")} className="ltr" value={ab.drawing_no} onChange={(e) => setAb((x) => ({ ...x, drawing_no: e.target.value }))} data-testid="q1-asbuilt-no" />
            <Input placeholder={t("titleField")} className="sm:col-span-2" value={ab.title} onChange={(e) => setAb((x) => ({ ...x, title: e.target.value }))} data-testid="q1-asbuilt-title" />
            <Input placeholder={t("rev")} className="ltr" value={ab.revision} onChange={(e) => setAb((x) => ({ ...x, revision: e.target.value }))} />
            <Select value={ab.status} onChange={(e) => setAb((x) => ({ ...x, status: e.target.value }))} aria-label={tc("status")}>
              <option value="submitted">{l("asbuilt_status", "submitted")}</option>
              <option value="approved">{l("asbuilt_status", "approved")}</option>
            </Select>
            <Button className="sm:col-span-5 sm:justify-self-start" disabled={busy || !ab.drawing_no || !ab.title} data-testid="q1-asbuilt-add"
              onClick={async () => { const r = await run(() => unwrap(api.POST("/api/v1/quality/dossiers/{dossier_id}/asbuilt", { ...path, body: { ...ab, status: ab.status as S["QAsbuiltStatus"] } }))); if (r) setAb({ drawing_no: "", title: "", revision: "0", status: "submitted" }); }}>
              {t("addDrawing")}
            </Button>
          </div>
        ) : null}
        {allowed.has("asbuilt") ? <div className="mt-3"><Attachments ownerType="q_dossier" ownerId={d.id} canUpload canDelete={false} hint={t("asbuiltFilesHint")} /></div> : null}
      </section>
      <div className="mt-6 flex flex-col gap-4">
        <h2 className="text-base font-semibold">{t("signoffs")}</h2>
        <SignoffList items={d.signoffs} recordType="dossier" />
        <LinkList items={d.links} />
        <ul className="flex flex-wrap gap-2 text-sm">{d.revisions.map((r) => <li key={r.id}><Link href={`/quality/dossiers/${r.id}`} className={`ltr rounded border px-2 py-1 ${r.id === d.id ? "border-primary" : ""}`}>Rev.{r.revision} · {l("dossier_status", r.status)}</Link></li>)}</ul>
        <HistoryPanel entityType="q_dossier" entityId={d.id} projectId={project.id} />
      </div>
    </div>
  );
}

export type { Dossier };
