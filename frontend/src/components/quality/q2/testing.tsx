"use client";
import { Plus } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
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
import { useQMte, useQSuppliers } from "@/lib/api/quality/q0";
import { useQMars, useQPour, useQPours, useQSpecimenCalendar, useQTest, useQTestTypes, useQTests } from "@/lib/api/quality/q2";
import { useDebounced } from "@/lib/use-debounced";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { QGate, ReasonDialog, useQCaps, useQLabels, useRun, userText, type Project } from "../q0/common";
import { DecisionDialog, Q2Badge, Signoffs, clean, type S } from "./shared";

const PAGE_SIZE = 50;

/* ═════════════ tests `/quality/tests` (§C.2) ═════════════ */

export function TestListPage() {
  return <QGate>{(p, st) => <Tests project={p} profile={st.sector_profile} />}</QGate>;
}

function Tests({ project, profile }: { project: Project; profile: string | null }) {
  const t = useTranslations("quality.tst");
  const tc = useTranslations("quality.common");
  const { l, options } = useQLabels();
  const caps = useQCaps(project.id);
  const s = useSearchState();
  const { date } = useFormatters(project.id);
  const page = s.getInt("page", 1) ?? 1;
  const status = s.get("status") ?? "";
  const verdict = s.get("verdict") ?? "";
  const [search, setSearch] = useState(s.get("q") ?? "");
  const q = useDebounced(search, 300);
  const r = useQTests(project.id, { status: status ? [status as S["QTestStatus"]] : null, verdict: (verdict || null) as S["QTestVerdict"] | null, q: q || null, page, page_size: PAGE_SIZE });
  const [adding, setAdding] = useState(false);
  const items = r.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")}
        actions={caps.write("test.record") && !adding ? <Button onClick={() => setAdding(true)} data-testid="q2-test-new"><Plus aria-hidden />{t("new")}</Button> : null} />
      {adding ? <TestForm project={project} profile={profile} onDone={() => setAdding(false)} /> : null}
      <SpecimenCalendar project={project} />
      <ListToolbar>
        <SearchFilter id="q2-tst-q" value={search} onChange={(v) => { setSearch(v); s.set({ q: v, page: null }); }} />
        <SelectFilter id="q2-tst-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={options("test_status")} />
        <SelectFilter id="q2-tst-verdict" label={t("verdict")} value={verdict} onChange={(v) => s.set({ verdict: v, page: null })} options={options("test_verdict")} />
      </ListToolbar>
      {r.isLoading ? <LoadingState /> : r.isError ? <ErrorState error={r.error} onRetry={() => r.refetch()} /> : items.length ? (
        <>
          <Table compact data-testid="q2-test-table">
            <THead><TR><TH>{t("no")}</TH><TH>{t("type")}</TH><TH>{t("location")}</TH><TH>{t("cast")}</TH><TH>{t("lab")}</TH><TH>{t("verdict")}</TH><TH>{tc("status")}</TH></TR></THead>
            <TBody>{items.map((x) => (
              <TR key={x.id} data-testid="q2-test-row" data-no={x.test_no} data-verdict={x.verdict} data-status={x.status}>
                <TD label={t("no")}><Link href={`/quality/tests/${x.id}`} className="ltr font-medium text-primary hover:underline">{x.test_no}</Link></TD>
                <TD label={t("type")} className="ltr">{x.test_type_code}</TD>
                <TD label={t("location")} dir="auto">{x.location_ref}</TD>
                <TD label={t("cast")}>{date(x.cast_date)}</TD>
                <TD label={t("lab")} className="ltr">{x.lab_code}</TD>
                <TD label={t("verdict")}><Q2Badge value={x.verdict} label={l("test_verdict", x.verdict)} /></TD>
                <TD label={tc("status")}><Q2Badge value={x.status} label={l("test_status", x.status)} /></TD>
              </TR>
            ))}</TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={r.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : <EmptyState message={t("empty")} />}
    </div>
  );
}

function SpecimenCalendar({ project }: { project: Project }) {
  const t = useTranslations("quality.tst");
  const { date } = useFormatters(project.id);
  const c = useQSpecimenCalendar(project.id);
  const items = c.data?.items ?? [];
  if (!items.length) return null;
  const tone = { overdue: "danger", today: "warning", upcoming: "neutral" } as const;
  return (
    <Card className="mb-4" data-testid="q2-specimen-calendar"><CardContent className="p-4">
      <h3 className="mb-2 text-sm font-semibold">{t("calendar")}</h3>
      <ul className="flex flex-col gap-1 text-sm">{items.slice(0, 12).map((x) => (
        <li key={`${x.test_id}-${x.specimen_ref}`} data-state={x.state}>
          <Badge tone={tone[x.state]}>{t(`due.${x.state}`)}</Badge> <Link href={`/quality/tests/${x.test_id}`} className="ltr text-primary hover:underline">{x.test_no}</Link> · <span className="ltr">{x.specimen_ref}</span> · {x.age_days != null ? t("days", { n: x.age_days }) : "—"} · {date(x.due_on)}
        </li>
      ))}</ul>
    </CardContent></Card>
  );
}

function TestForm({ project, profile, onDone }: { project: Project; profile: string | null; onDone: () => void }) {
  const t = useTranslations("quality.tst");
  const tc = useTranslations("quality.common");
  const ar = useLocale() === "ar";
  const opts = useProjectOptions(project.id);
  const types = useQTestTypes({ status: "published", project_id: project.id });
  const sup = useQSuppliers({ page_size: 200 });
  const pours = useQPours(project.id, { page_size: 100 });
  const router = useRouter();
  const { run, busy, error } = useRun();
  const [f, setF] = useState({ test_type_id: "", site_id: "", location_ref: "", engagement_id: "", lab_supplier_id: "", pour_id: "" });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const labs = (sup.data?.items ?? []).filter((x) => x.categories.some((c) => c === "testing_lab" || c === "ndt_provider"));
  const tts = (types.data ?? []).filter((x) => x.profile === "both" || x.profile === profile);
  async function save() {
    const body = clean(f) as unknown as S["QTestCreate"];
    const out = await run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/tests", { params: { path: { project_id: project.id } }, body })));
    if (out) { onDone(); router.push(`/quality/tests/${out.id}`); }
  }
  return (
    <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-3" data-testid="q2-test-form">
      <MutationError error={error} />
      <FormField id="tst-type" label={t("type")} required><Select value={f.test_type_id} onChange={set("test_type_id")} data-testid="tst-type"><option value="">{tc("select")}</option>{tts.map((x) => <option key={x.id} value={x.id}>{x.code} — {ar ? x.name_ar || x.name_en : x.name_en}</option>)}</Select></FormField>
      <FormField id="tst-lab" label={t("lab")} required><Select value={f.lab_supplier_id} onChange={set("lab_supplier_id")} data-testid="tst-lab"><option value="">{tc("select")}</option>{labs.map((x) => <option key={x.id} value={x.id}>{x.supplier_code}</option>)}</Select></FormField>
      {profile === "construction" ? <FormField id="tst-pour" label={t("pour")}><Select value={f.pour_id} onChange={set("pour_id")} data-testid="tst-pour"><option value="">—</option>{(pours.data?.items ?? []).map((x) => <option key={x.id} value={x.id}>{x.pour_no}</option>)}</Select></FormField> : null}
      <FormField id="tst-site" label={t("site")} required={!f.pour_id}><Select value={f.site_id} onChange={set("site_id")} data-testid="tst-site"><option value="">—</option>{opts.sites.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <FormField id="tst-eng" label={t("contractor")}><Select value={f.engagement_id} onChange={set("engagement_id")} data-testid="tst-engagement"><option value="">—</option>{opts.engagements.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <FormField id="tst-loc" label={t("location")}><Input value={f.location_ref} onChange={set("location_ref")} data-testid="tst-location" /></FormField>
      <div className="flex gap-2 sm:col-span-3">
        <Button disabled={busy || !f.test_type_id || !f.lab_supplier_id || (!f.site_id && !f.pour_id)} onClick={() => void save()} data-testid="tst-save">{tc("save")}</Button>
        <Button variant="outline" onClick={onDone}>{tc("cancel")}</Button>
      </div>
    </CardContent></Card>
  );
}

export function TestDetailPage({ id }: { id: string }) {
  return <QGate>{(p) => <TestDetail project={p} id={id} />}</QGate>;
}

type Vals = Record<string, Record<string, string>>;

function TestDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.tst");
  const tq = useTranslations("quality.q2");
  const { l } = useQLabels();
  const ar = useLocale() === "ar";
  const { date, dateTime } = useFormatters(project.id);
  const q = useQTest(id);
  const mte = useQMte(project.id, { page_size: 200 });
  const { run, busy, error } = useRun();
  const [sampleRef, setSampleRef] = useState("");
  const [mteId, setMteId] = useState("");
  const [vals, setVals] = useState<Vals>({});
  const [results, setResults] = useState<Record<string, string>>({});
  const [reportNo, setReportNo] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [amending, setAmending] = useState(false);
  const [declining, setDeclining] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const x = q.data;
  if (!x) return null;
  const path = { params: { path: { test_id: x.id } } };
  const can = (a: string) => x.actions.includes(a);
  const fields = x.result_fields;
  const det = x.verdict_detail as Record<string, unknown>;
  const specRows = () => Object.entries(vals).map(([sid, v]) => ({ id: sid, values: v }));
  const fieldLabel = (f: (typeof fields)[number]) => `${ar ? f.label_ar || f.label_en : f.label_en}${f.unit ? ` (${f.unit})` : ""}`;
  return (
    <div data-testid="q2-test-detail" data-status={x.status} data-verdict={x.verdict}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/tests" }, { label: x.test_no }]} />
      <PageHeader title={<span className="ltr">{x.test_no}</span>} description={`${x.test_type_code} — ${ar ? x.test_type_name_ar || x.test_type_name_en : x.test_type_name_en}`}
        badge={<span className="flex gap-2"><Q2Badge value={x.status} label={l("test_status", x.status)} testId="q2-test-status" /><Q2Badge value={x.verdict} label={l("test_verdict", x.verdict)} testId="q2-test-verdict" /></span>}
        actions={<>
          {can("deliver") ? <Button disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/tests/{test_id}/deliver", { ...path, body: {} })))} data-testid="q2-test-deliver">{t("deliver")}</Button> : null}
          {can("verify") ? <Button onClick={() => setVerifying(true)} data-testid="q2-test-verify">{t("verify")}</Button> : null}
          {can("amend") ? <Button variant="outline" onClick={() => setAmending(true)} data-testid="q2-test-amend">{t("amend")}</Button> : null}
          {can("cancel") ? <Button variant="outline" onClick={() => setCancelling(true)}>{t("cancel")}</Button> : null}
        </>} />
      <MutationError error={error} />
      <ApiWarnings warnings={x.warnings} className="mb-3" />
      {x.verdict === "fail" ? <Alert tone="danger" className="mb-3" data-testid="q2-test-fail">{ar ? String(det.reason_ar ?? "") : String(det.reason_en ?? "")}</Alert> : null}
      {can("ncr_decision") ? (
        <Alert tone="warning" className="mb-3" data-testid="q2-ncr-prompt">
          <p className="mb-2">{t("ncrPrompt")}</p>
          <div className="flex gap-2">
            <Button size="sm" disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/tests/{test_id}/ncr-decision", { ...path, body: { raise_ncr: true } })))} data-testid="q2-ncr-raise">{t("raiseNcr")}</Button>
            <Button size="sm" variant="outline" onClick={() => setDeclining(true)} data-testid="q2-ncr-decline">{t("declineNcr")}</Button>
          </div>
        </Alert>
      ) : null}
      {x.ncr_decision.ncr_id ? <Alert tone="info" className="mb-3"><Link href={`/quality/ncrs/${String(x.ncr_decision.ncr_id)}`} className="text-primary hover:underline" data-testid="q2-test-ncr-link">{t("ncrRaised", { no: String(x.ncr_decision.ncr_no ?? "") })}</Link></Alert> : null}
      <Card className="mb-4"><CardContent className="p-4"><FieldList>
        <FieldItem label={t("criterion")} ltr>{x.criterion_code ? `${x.criterion_code} v${x.criterion_version}` : "—"}</FieldItem>
        <FieldItem label={t("site")} ltr>{[x.site_code, x.zone_code].filter(Boolean).join(" / ")}</FieldItem>
        <FieldItem label={t("location")}>{x.location_ref}</FieldItem>
        <FieldItem label={t("lab")} ltr>{x.lab_code}</FieldItem>
        <FieldItem label={t("pour")} ltr>{x.pour_id ? <Link href={`/quality/pours/${x.pour_id}`} className="text-primary hover:underline">{x.pour_no}</Link> : "—"}</FieldItem>
        <FieldItem label={t("sampled")}>{dateTime(x.sampled_at)}{x.sample_ref ? <span className="ltr"> · {x.sample_ref}</span> : null}</FieldItem>
        <FieldItem label={t("requestedBy")}>{userText(x.requested_by, ar)}</FieldItem>
        <FieldItem label={t("report")} ltr>{x.report_no ?? "—"}</FieldItem>
        <FieldItem label={t("resultVersion")} ltr>{x.result_version || "—"}</FieldItem>
        {det.test ? <FieldItem label={t("strengthTest")} ltr>{String(det.test)} {det.mean3 ? `· ${t("mean3")} ${String(det.mean3)}` : ""}</FieldItem> : null}
        {x.verdict !== "fail" && det.reason_en ? <FieldItem label={t("reason")} wide>{ar ? String(det.reason_ar ?? "") : String(det.reason_en ?? "")}</FieldItem> : null}
      </FieldList></CardContent></Card>
      {can("sample") ? (
        <Card className="mb-4" data-testid="q2-sample-form"><CardContent className="grid gap-3 p-4 sm:grid-cols-3">
          <FormField id="tst-sref" label={t("sampleRef")} required><Input value={sampleRef} onChange={(e) => setSampleRef(e.target.value)} dir="ltr" data-testid="q2-sample-ref" /></FormField>
          <FormField id="tst-mte" label={t("instrument")}><Select value={mteId} onChange={(e) => setMteId(e.target.value)} data-testid="q2-sample-mte"><option value="">—</option>{(mte.data?.items ?? []).map((m) => <option key={m.id} value={m.id}>{m.mte_no} — {m.description}</option>)}</Select></FormField>
          {fields.filter(() => x.specimens.length === 0).map((f) => <FormField key={f.key} id={`tst-r-${f.key}`} label={fieldLabel(f)}><Input value={results[f.key] ?? ""} onChange={(e) => setResults({ ...results, [f.key]: e.target.value })} dir="ltr" /></FormField>)}
          <Button className="self-end" disabled={busy || !sampleRef} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/tests/{test_id}/sample", { ...path, body: { sample_ref: sampleRef, mte_ids: mteId ? [mteId] : [], results: clean(results) } })))} data-testid="q2-sample-save">{t("sample")}</Button>
        </CardContent></Card>
      ) : null}
      {x.specimens.length ? (
        <Card className="mb-4"><CardContent className="p-4">
          <h3 className="mb-2 text-sm font-semibold">{t("specimens")}</h3>
          <Table compact data-testid="q2-specimens"><THead><TR><TH>{t("specimen")}</TH><TH>{t("age")}</TH><TH>{t("dueOn")}</TH>{fields.map((f) => <TH key={f.key}>{fieldLabel(f)}</TH>)}</TR></THead>
            <TBody>{x.specimens.map((s) => (
              <TR key={s.id} data-age={s.age_days ?? ""}>
                <TD label={t("specimen")} className="ltr">{s.specimen_ref}{s.spare ? ` (${t("spare")})` : ""}</TD>
                <TD label={t("age")}>{s.age_days != null ? t("days", { n: s.age_days }) : "—"}</TD>
                <TD label={t("dueOn")}>{date(s.due_on)}</TD>
                {fields.map((f) => (
                  <TD key={f.key} label={fieldLabel(f)} className="ltr">
                    {can("specimens") && !s.spare ? (
                      <Input aria-label={`${s.specimen_ref} ${f.key}`} value={vals[s.id]?.[f.key] ?? String((s.values as Record<string, unknown>)[f.key] ?? "")} onChange={(e) => setVals({ ...vals, [s.id]: { ...(vals[s.id] ?? {}), [f.key]: e.target.value } })} className="w-28" inputMode="decimal" data-testid="q2-specimen-value" />
                    ) : String((s.values as Record<string, unknown>)[f.key] ?? "—")}
                  </TD>
                ))}
              </TR>
            ))}</TBody></Table>
          {can("specimens") ? <Button className="mt-2" size="sm" variant="outline" disabled={busy || !Object.keys(vals).length} onClick={() => void run(() => unwrap(api.PUT("/api/v1/quality/tests/{test_id}/specimens", { ...path, body: { specimens: specRows() } })))} data-testid="q2-specimens-save">{t("saveSpecimens")}</Button> : null}
        </CardContent></Card>
      ) : null}
      {can("results") ? (
        <Card className="mb-4" data-testid="q2-results-form"><CardContent className="grid gap-3 p-4 sm:grid-cols-3">
          <h3 className="text-sm font-semibold sm:col-span-3">{t("results")}</h3>
          {x.specimens.length === 0 ? fields.map((f) => <FormField key={f.key} id={`tst-res-${f.key}`} label={fieldLabel(f)}><Input value={results[f.key] ?? String((x.results as Record<string, unknown>)[f.key] ?? "")} onChange={(e) => setResults({ ...results, [f.key]: e.target.value })} dir="ltr" data-testid={`q2-result-${f.key}`} /></FormField>) : null}
          <FormField id="tst-rno" label={t("report")} required><Input value={reportNo} onChange={(e) => setReportNo(e.target.value)} dir="ltr" data-testid="q2-report-no" /></FormField>
          <div className="sm:col-span-3"><Attachments ownerType="q_test_report" ownerId={x.id} canUpload /></div>
          <Button className="self-end" disabled={busy || !reportNo} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/tests/{test_id}/results", { ...path, body: { report_no: reportNo, specimens: specRows(), results: clean(results) } })))} data-testid="q2-results-save">{t("enterResults")}</Button>
        </CardContent></Card>
      ) : x.report_count ? <Card className="mb-4"><CardContent className="p-4"><h3 className="mb-2 text-sm font-semibold">{t("reportFiles")}</h3><Attachments ownerType="q_test_report" ownerId={x.id} canUpload={can("amend")} /></CardContent></Card> : null}
      {x.history.length ? (
        <Card className="mb-4" data-testid="q2-test-history"><CardContent className="p-4">
          <h3 className="mb-2 text-sm font-semibold">{t("history")}</h3>
          <ul className="text-sm">{x.history.map((h, i) => <li key={i}>{t("amendedNote", { v: String(h.version), verdict: l("test_verdict", String(h.verdict)), at: dateTime(String(h.amended_at)) })} — <span dir="auto">{String(h.reason ?? "")}</span></li>)}</ul>
        </CardContent></Card>
      ) : null}
      <Signoffs recordType="test_request" recordId={x.id} />
      <HistoryPanel entityType="q_test_request" entityId={x.id} projectId={project.id} />
      <DecisionDialog open={verifying} onOpenChange={setVerifying} title={t("verify")} testId="q2-verify-dialog"
        options={[{ value: "approved", label: tq("approve") }, { value: "returned", label: tq("return") }]} needsComment={(v) => v === "returned"}
        onSubmit={(d, c) => unwrap(api.POST("/api/v1/quality/tests/{test_id}/verify", { ...path, body: { decision: d as "approved", comment: c || null } })).then(() => q.refetch())} />
      <ReasonDialog open={amending} onOpenChange={setAmending} title={t("amend")} description={t("amendHint")} confirm={t("amend")} testId="q2-amend-dialog"
        onSubmit={(reason) => unwrap(api.POST("/api/v1/quality/tests/{test_id}/amend", { ...path, body: { reason, report_no: `${x.report_no ?? ""}-A${x.result_version}`, specimens: specRows(), results: clean(results) } })).then(() => q.refetch())} />
      <ReasonDialog open={declining} onOpenChange={setDeclining} title={t("declineNcr")} confirm={t("declineNcr")} testId="q2-decline-dialog"
        onSubmit={(reason) => unwrap(api.POST("/api/v1/quality/tests/{test_id}/ncr-decision", { ...path, body: { raise_ncr: false, reason } })).then(() => q.refetch())} />
      <ReasonDialog open={cancelling} onOpenChange={setCancelling} title={t("cancel")} confirm={t("cancel")}
        onSubmit={(reason) => unwrap(api.POST("/api/v1/quality/tests/{test_id}/cancel", { ...path, body: { reason } })).then(() => q.refetch())} />
    </div>
  );
}

/* ═════════════ test types `/quality/test-types` (Q-TST-01) ═════════════ */

export function TestTypesPage() {
  return <QGate>{() => <TestTypes />}</QGate>;
}

function TestTypes() {
  const t = useTranslations("quality.ttype");
  const tc = useTranslations("quality.common");
  const { l } = useQLabels();
  const ar = useLocale() === "ar";
  const r = useQTestTypes({});
  const { run, busy, error } = useRun();
  const items = r.data ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <MutationError error={error} />
      {r.isLoading ? <LoadingState /> : r.isError ? <ErrorState error={r.error} onRetry={() => r.refetch()} /> : (
        <Table compact data-testid="q2-test-type-table">
          <THead><TR><TH>{t("code")}</TH><TH>{t("name")}</TH><TH>{t("profile")}</TH><TH>{t("standard")}</TH><TH>{t("plan")}</TH><TH>{t("evaluation")}</TH><TH>{tc("status")}</TH><TH /></TR></THead>
          <TBody>{items.map((x) => (
            <TR key={x.id} data-testid="q2-test-type-row" data-code={x.code}>
              <TD label={t("code")} className="ltr font-medium">{x.code} v{x.version}</TD>
              <TD label={t("name")}>{ar ? x.name_ar || x.name_en : x.name_en}</TD>
              <TD label={t("profile")}>{l("profile", x.profile)}</TD>
              <TD label={t("standard")} className="ltr text-xs">{x.standard_ref ?? "—"}</TD>
              <TD label={t("plan")} className="ltr text-xs">{x.specimen_plan.map((p) => `${p.count}×${p.age_days ?? "—"}d${p.spare ? "*" : ""}`).join(", ") || "—"}</TD>
              <TD label={t("evaluation")} className="ltr text-xs">{x.criterion_code ?? Object.values(x.field_criteria).join(", ") ?? "—"}</TD>
              <TD label={tc("status")}><Q2Badge value={x.status} label={l("test_type_status", x.status)} /></TD>
              <TD label="">{x.status === "published" ? <Button size="sm" variant="ghost" disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/test-types/{type_id}/new-version", { params: { path: { type_id: x.id } }, body: {} })))}>{t("newVersion")}</Button>
                : x.status === "draft" ? <Button size="sm" variant="ghost" disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/test-types/{type_id}/transitions", { params: { path: { type_id: x.id } }, body: { action: "publish" } })))}>{t("publish")}</Button> : null}</TD>
            </TR>
          ))}</TBody>
        </Table>
      )}
    </div>
  );
}

/* ═════════════ pours `/quality/pours` (Q-TST-11…13) ═════════════ */

export function PourListPage() {
  return <QGate>{(p) => <Pours project={p} />}</QGate>;
}

function Pours({ project }: { project: Project }) {
  const t = useTranslations("quality.pour");
  const tc = useTranslations("quality.common");
  const { l } = useQLabels();
  const caps = useQCaps(project.id);
  const s = useSearchState();
  const { date } = useFormatters(project.id);
  const page = s.getInt("page", 1) ?? 1;
  const r = useQPours(project.id, { page, page_size: PAGE_SIZE });
  const [adding, setAdding] = useState(false);
  const items = r.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")}
        actions={caps.write("test.record") && !adding ? <Button onClick={() => setAdding(true)} data-testid="q2-pour-new"><Plus aria-hidden />{t("new")}</Button> : null} />
      {adding ? <PourForm project={project} onDone={() => setAdding(false)} /> : null}
      {r.isLoading ? <LoadingState /> : r.isError ? <ErrorState error={r.error} onRetry={() => r.refetch()} /> : items.length ? (
        <>
          <Table compact data-testid="q2-pour-table">
            <THead><TR><TH>{t("no")}</TH><TH>{t("element")}</TH><TH>{t("grade")}</TH><TH>{t("volume")}</TH><TH>{t("sets")}</TH><TH>{t("date")}</TH><TH>{tc("status")}</TH></TR></THead>
            <TBody>{items.map((x) => (
              <TR key={x.id} data-testid="q2-pour-row" data-no={x.pour_no}>
                <TD label={t("no")}><Link href={`/quality/pours/${x.id}`} className="ltr font-medium text-primary hover:underline">{x.pour_no}</Link></TD>
                <TD label={t("element")} dir="auto">{x.element}</TD>
                <TD label={t("grade")} className="ltr">{x.grade}</TD>
                <TD label={t("volume")} className="ltr">{x.volume_m3} m³</TD>
                <TD label={t("sets")} className={x.sets_taken < x.sets_required ? "ltr font-semibold text-danger" : "ltr"}>{x.sets_taken} / {x.sets_required}</TD>
                <TD label={t("date")}>{date(x.started_at ?? x.planned_on)}</TD>
                <TD label={tc("status")}><Q2Badge value={x.status} label={l("pour_status", x.status)} /></TD>
              </TR>
            ))}</TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={r.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : <EmptyState message={t("empty")} />}
    </div>
  );
}

function PourForm({ project, onDone }: { project: Project; onDone: () => void }) {
  const t = useTranslations("quality.pour");
  const tc = useTranslations("quality.common");
  const opts = useProjectOptions(project.id);
  const mars = useQMars(project.id, { status: ["approved", "approved_as_noted"], category: "concrete_mix", page_size: 100 });
  const router = useRouter();
  const { run, busy, error } = useRun();
  const [f, setF] = useState({ element: "", site_id: "", engagement_id: "", mar_id: "", grade: "", volume_m3: "", location_ref: "", planned_on: "" });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  async function save() {
    const out = await run(() => unwrap(api.POST("/api/v1/projects/{project_id}/quality/pours", { params: { path: { project_id: project.id } }, body: clean(f) as unknown as S["QPourCreate"] })));
    if (out) { onDone(); router.push(`/quality/pours/${out.id}`); }
  }
  return (
    <Card className="mb-4"><CardContent className="grid gap-3 p-4 sm:grid-cols-3" data-testid="q2-pour-form">
      <MutationError error={error} />
      <FormField id="pour-el" label={t("element")} required className="sm:col-span-2"><Input value={f.element} onChange={set("element")} data-testid="pour-element" /></FormField>
      <FormField id="pour-site" label={t("site")} required><Select value={f.site_id} onChange={set("site_id")} data-testid="pour-site"><option value="">{tc("select")}</option>{opts.sites.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <FormField id="pour-eng" label={t("contractor")}><Select value={f.engagement_id} onChange={set("engagement_id")} data-testid="pour-engagement"><option value="">—</option>{opts.engagements.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select></FormField>
      <FormField id="pour-mar" label={t("mix")}><Select value={f.mar_id} onChange={set("mar_id")}><option value="">—</option>{(mars.data?.items ?? []).map((m) => <option key={m.id} value={m.id}>{m.mar_no} — {m.title_en}</option>)}</Select></FormField>
      <FormField id="pour-grade" label={t("grade")} required><Input value={f.grade} onChange={set("grade")} dir="ltr" placeholder="C40" data-testid="pour-grade" /></FormField>
      <FormField id="pour-vol" label={t("volume")} required><Input value={f.volume_m3} onChange={set("volume_m3")} dir="ltr" inputMode="decimal" data-testid="pour-volume" /></FormField>
      <FormField id="pour-loc" label={t("location")}><Input value={f.location_ref} onChange={set("location_ref")} /></FormField>
      <FormField id="pour-date" label={t("date")}><Input type="date" value={f.planned_on} onChange={set("planned_on")} /></FormField>
      <div className="flex gap-2 sm:col-span-3">
        <Button disabled={busy || !f.element || !f.site_id || !f.grade || !f.volume_m3} onClick={() => void save()} data-testid="pour-save">{tc("save")}</Button>
        <Button variant="outline" onClick={onDone}>{tc("cancel")}</Button>
      </div>
    </CardContent></Card>
  );
}

export function PourDetailPage({ id }: { id: string }) {
  return <QGate>{(p) => <PourDetail project={p} id={id} />}</QGate>;
}

function PourDetail({ project, id }: { project: Project; id: string }) {
  const t = useTranslations("quality.pour");
  const { l } = useQLabels();
  const { date, dateTime } = useFormatters(project.id);
  const q = useQPour(id);
  const tests = useQTests(project.id, { pour_id: id, page_size: 100 });
  const { run, busy, error } = useRun();
  const [cancelling, setCancelling] = useState(false);
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const x = q.data;
  if (!x) return null;
  const path = { params: { path: { pour_id: x.id } } };
  const ms = x.mix_status;
  return (
    <div data-testid="q2-pour-detail" data-status={x.status}>
      <Breadcrumbs items={[{ label: t("title"), href: "/quality/pours" }, { label: x.pour_no }]} />
      <PageHeader title={<span className="ltr">{x.pour_no}</span>} description={x.element}
        badge={<Q2Badge value={x.status} label={l("pour_status", x.status)} testId="q2-pour-status" />}
        actions={<>
          {x.actions.includes("start") ? <Button disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/pours/{pour_id}/start", { ...path, body: {} })))} data-testid="q2-pour-start">{t("start")}</Button> : null}
          {x.actions.includes("close") ? <Button disabled={busy} onClick={() => void run(() => unwrap(api.POST("/api/v1/quality/pours/{pour_id}/close", { ...path, body: {} })))} data-testid="q2-pour-close">{t("close")}</Button> : null}
          {x.actions.includes("cancel") ? <Button variant="outline" onClick={() => setCancelling(true)}>{t("cancel")}</Button> : null}
        </>} />
      <MutationError error={error} />
      <ApiWarnings warnings={x.warnings} className="mb-3" />
      {x.sets_taken < x.sets_required && x.status !== "planned" ? <Alert tone="warning" className="mb-3" data-testid="q2-pour-short">{t("short", { have: x.sets_taken, need: x.sets_required })}</Alert> : null}
      {ms?.flagged ? <Alert tone="danger" className="mb-3" data-testid="q2-pour-flagged">{t("flagged")}</Alert> : null}
      <Card className="mb-4"><CardContent className="p-4"><FieldList>
        <FieldItem label={t("grade")} ltr>{x.grade}{x.fc_mpa ? ` (f'c ${x.fc_mpa})` : ""}</FieldItem>
        <FieldItem label={t("volume")} ltr>{x.volume_m3} m³</FieldItem>
        <FieldItem label={t("sets")} ltr>{x.sets_taken} / {x.sets_required}</FieldItem>
        <FieldItem label={t("mix")} ltr>{x.mar_no ?? "—"}</FieldItem>
        <FieldItem label={t("supplier")} ltr>{x.supplier_code ?? "—"}</FieldItem>
        <FieldItem label={t("site")} ltr>{[x.site_code, x.zone_code].filter(Boolean).join(" / ")}</FieldItem>
        <FieldItem label={t("location")}>{x.location_ref ?? "—"}</FieldItem>
        <FieldItem label={t("date")}>{date(x.planned_on)}</FieldItem>
        <FieldItem label={t("started")}>{dateTime(x.started_at)}</FieldItem>
        <FieldItem label={t("finished")}>{dateTime(x.finished_at)}</FieldItem>
      </FieldList></CardContent></Card>
      <Card className="mb-4"><CardContent className="p-4">
        <h3 className="mb-2 text-sm font-semibold">{t("tests")}</h3>
        {(tests.data?.items ?? []).length ? <ul className="text-sm">{(tests.data?.items ?? []).map((tt) => <li key={tt.id}><Link href={`/quality/tests/${tt.id}`} className="ltr text-primary hover:underline">{tt.test_no}</Link> · {tt.test_type_code} · <Q2Badge value={tt.verdict} label={l("test_verdict", tt.verdict)} /></li>)}</ul> : <p className="text-sm text-muted-foreground">{t("noTests")}</p>}
      </CardContent></Card>
      {ms && ms.tests.length ? (
        <Card className="mb-4" data-testid="q2-mix-status"><CardContent className="p-4">
          <h3 className="mb-2 text-sm font-semibold">{t("mixStatus")}</h3>
          <Table compact><THead><TR><TH>{t("test")}</TH><TH>{t("pourCol")}</TH><TH>{t("cast")}</TH><TH>{t("strength")}</TH><TH>{t("mean3")}</TH><TH>{t("verdict")}</TH></TR></THead>
            <TBody>{ms.tests.map((m) => <TR key={m.test_id}><TD label={t("test")} className="ltr">{m.test_no}</TD><TD label={t("pourCol")} className="ltr">{m.pour_no ?? "—"}</TD><TD label={t("cast")}>{date(m.cast_date)}</TD><TD label={t("strength")} className="ltr">{m.test ?? "—"}</TD><TD label={t("mean3")} className="ltr">{m.mean3 ?? "—"}</TD><TD label={t("verdict")}><Q2Badge value={m.verdict} label={`${l("test_verdict", m.verdict)}${m.clause ? ` (${m.clause})` : ""}`} /></TD></TR>)}</TBody></Table>
        </CardContent></Card>
      ) : null}
      <HistoryPanel entityType="q_pour" entityId={x.id} projectId={project.id} />
      <ReasonDialog open={cancelling} onOpenChange={setCancelling} title={t("cancel")} confirm={t("cancel")}
        onSubmit={(reason) => unwrap(api.POST("/api/v1/quality/pours/{pour_id}/cancel", { ...path, body: { reason } })).then(() => q.refetch())} />
    </div>
  );
}
