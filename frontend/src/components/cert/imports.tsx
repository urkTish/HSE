"use client";
import { AlertTriangle, CheckCircle2, Download, FileUp, Trash2, XCircle } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { CheckboxField, FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Code } from "@/components/access/common";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { api, downloadFile, postForm, unwrap, type Schemas } from "@/lib/api/client";
import { useCertImport, useCertImports, useCertRefresh } from "@/lib/api/cert";
import { CERT_IMPORT_SOURCES, CERT_IMPORT_STATUSES, CERT_IMPORT_TEMPLATES } from "@/lib/cert-enums";
import { useErrorMessage } from "@/lib/i18n-helpers";
import { canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { TpiSelect, UserName } from "./common";

type S = Schemas;
const PAGE_SIZE = 25;
const COUNT_KEYS = ["rows_total", "rows_ok", "rows_warning", "rows_error", "certificates_valid", "items_to_create", "certificates_created", "certificates_left_draft", "items_created"] as const;

export function CertImportListPage() {
  return <ProjectGate>{(p) => <CertImports project={p} />}</ProjectGate>;
}

function CertImports({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("certImports");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const msg = useErrorMessage();
  const router = useRouter();
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const list = useCertImports(project.id, {
    status: (s.get("status") as S["CertImportStatus"]) || null,
    template: (s.get("template") as S["CertImportTemplate"]) || null,
    page,
    page_size: PAGE_SIZE,
  });
  const allowed = canWrite(me, "cert.import", project.id);
  const officer = me.is_hse_manager || canWrite(me, "cert.review", project.id);
  const [template, setTemplate] = useState<S["CertImportTemplate"]>("equipment_certificates");
  const [source, setSource] = useState<S["CertImportSource"]>("contractor_file");
  const [file, setFile] = useState<File | null>(null);
  const [scans, setScans] = useState<File | null>(null);
  const [evidence, setEvidence] = useState<File | null>(null);
  const [tpi, setTpi] = useState("");
  const [createItems, setCreateItems] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const register = source === "tpi_register_file";
  const ready = !!file && (!register || (!!evidence && !!tpi));

  async function check() {
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.set("file", file);
    form.set("template", template);
    form.set("source", source);
    form.set("create_items", template === "equipment_certificates" && createItems ? "true" : "false");
    if (tpi) form.set("tpi_id", tpi);
    if (scans) form.set("scans_zip", scans);
    if (register && evidence) form.set("evidence_file", evidence);
    try {
      const res = await postForm<S["CertImportRead"]>(`/api/v1/projects/${project.id}/certificate-imports`, form);
      router.push(`/certificate-imports/${res.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function download(tpl: S["CertImportTemplate"], format: S["ExportFormat"], headers: "en" | "ar") {
    try {
      await downloadFile(`/api/v1/certificate-imports/template?template=${tpl}&format=${format}&headers=${headers}`, `${tpl}-template-${headers}.${format}`);
    } catch (e) {
      toast.error(msg(e));
    }
  }

  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{t("check")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {allowed ? (
              <>
                <div className="grid gap-3 sm:grid-cols-2">
                  <FormField id="ci-template" label={t("template")} required>
                    <Select id="ci-template" value={template} onChange={(e) => setTemplate(e.target.value as S["CertImportTemplate"])} data-testid="ci-template">
                      {CERT_IMPORT_TEMPLATES.map((x) => (
                        <option key={x} value={x}>
                          {te(`certImportTemplate.${x}`)}
                        </option>
                      ))}
                    </Select>
                  </FormField>
                  <FormField id="ci-source" label={t("source")} hint={register ? t("registerHint") : undefined}>
                    <Select id="ci-source" value={source} onChange={(e) => setSource(e.target.value as S["CertImportSource"])} data-testid="ci-source">
                      {CERT_IMPORT_SOURCES.filter((x) => x === "contractor_file" || officer).map((x) => (
                        <option key={x} value={x}>
                          {te(`certImportSource.${x}`)}
                        </option>
                      ))}
                    </Select>
                  </FormField>
                </div>
                <FormField id="ci-file" label={t("file")} required hint={t("fileHint")}>
                  <Input id="ci-file" type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={(e) => setFile(e.target.files?.[0] ?? null)} data-testid="ci-file" />
                </FormField>
                <FormField id="ci-scans" label={t("scansZip")} hint={t("scansHint")}>
                  <Input id="ci-scans" type="file" accept=".zip,application/zip" onChange={(e) => setScans(e.target.files?.[0] ?? null)} data-testid="ci-scans" />
                </FormField>
                <TpiSelect id="ci-tpi" label={register ? t("tpiRequired") : t("tpiOptional")} value={tpi} onChange={setTpi} projectId={project.id} required={register} />
                {register ? (
                  <FormField id="ci-evidence" label={t("evidence")} required hint={t("evidenceHint")}>
                    <Input id="ci-evidence" type="file" accept=".pdf,.eml,application/pdf,message/rfc822" onChange={(e) => setEvidence(e.target.files?.[0] ?? null)} data-testid="ci-evidence" />
                  </FormField>
                ) : null}
                {template === "equipment_certificates" && officer ? (
                  <CheckboxField id="ci-create" label={t("createItems")}>
                    <Checkbox checked={createItems} onChange={(e) => setCreateItems(e.target.checked)} data-testid="ci-create" />
                  </CheckboxField>
                ) : null}
                <MutationError error={error} />
                <div>
                  <Button onClick={() => void check()} disabled={!ready || busy} data-testid="ci-check">
                    <FileUp aria-hidden />
                    {busy ? t("checking") : t("check")}
                  </Button>
                </div>
              </>
            ) : (
              <Alert tone="info">{tc("notAllowed")}</Alert>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t("templates")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {CERT_IMPORT_TEMPLATES.map((tpl) => (
              <div key={tpl} className="flex flex-col gap-1">
                <span className="text-sm font-medium">{te(`certImportTemplate.${tpl}`)}</span>
                <div className="flex flex-wrap gap-2">
                  {(["en", "ar"] as const).map((h) => (
                    <Button key={h} variant="outline" size="sm" onClick={() => void download(tpl, "xlsx", h)} data-testid={`ci-tpl-${tpl}-${h}`}>
                      <Download aria-hidden />
                      {h === "en" ? t("excelEn") : t("excelAr")}
                    </Button>
                  ))}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
      <h2 className="mt-8 mb-3 text-lg font-semibold">{t("history")}</h2>
      <ListToolbar>
        <SelectFilter id="ci-f-status" label={tc("status")} value={s.get("status") ?? ""} onChange={(v) => s.set({ status: v })} options={CERT_IMPORT_STATUSES.map((x) => ({ value: x, label: te(`certImportStatus.${x}`) }))} />
        <SelectFilter id="ci-f-template" label={t("template")} value={s.get("template") ?? ""} onChange={(v) => s.set({ template: v })} options={CERT_IMPORT_TEMPLATES.map((x) => ({ value: x, label: te(`certImportTemplate.${x}`) }))} />
      </ListToolbar>
      {list.isLoading ? (
        <LoadingState rows={2} />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : (list.data?.items.length ?? 0) === 0 ? (
        <EmptyState message={t("noImports")} />
      ) : (
        <>
          <Table data-testid="ci-history">
            <THead>
              <TR>
                <TH>{t("fileName")}</TH>
                <TH>{t("template")}</TH>
                <TH>{tc("status")}</TH>
                <TH className="text-end">{t("counts.rows_ok")}</TH>
                <TH className="text-end">{t("counts.rows_error")}</TH>
                <TH className="text-end">{t("counts.certificates_created")}</TH>
                <TH>{t("uploadedBy")}</TH>
              </TR>
            </THead>
            <TBody>
              {list.data?.items.map((b) => (
                <TR key={b.id}>
                  <TD label={t("fileName")}>
                    <Link href={`/certificate-imports/${b.id}`} className="font-medium text-primary hover:underline ltr">
                      {b.file_name}
                    </Link>
                  </TD>
                  <TD label={t("template")}>
                    {te(`certImportTemplate.${b.template}`)}
                    <span className="block text-xs text-muted-foreground">{te(`certImportSource.${b.source}`)}</span>
                  </TD>
                  <TD label={tc("status")}>
                    <StatusBadge status={b.status} label={te(`certImportStatus.${b.status}`)} />
                  </TD>
                  <TD label={t("counts.rows_ok")} className="text-end tabular-nums">
                    {b.counts.rows_ok}
                  </TD>
                  <TD label={t("counts.rows_error")} className="text-end tabular-nums">
                    {b.counts.rows_error}
                  </TD>
                  <TD label={t("counts.certificates_created")} className="text-end tabular-nums">
                    {b.counts.certificates_created}
                  </TD>
                  <TD label={t("uploadedBy")}>
                    <UserName u={b.uploaded_by} /> · {dateTime(b.created_at)}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={list.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      )}
    </div>
  );
}

export function CertImportDetail({ id }: { id: string }) {
  const t = useTranslations("certImports");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const me = useMeData();
  const router = useRouter();
  const msg = useErrorMessage();
  const refresh = useCertRefresh();
  const [showOk, setShowOk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const q = useCertImport(id, showOk);
  const pid = q.data?.project_id ?? null;
  const { dateTime } = useFormatters(pid);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const b = q.data;
  const allowed = canWrite(me, "cert.import", b.project_id);
  const pending = b.status === "validated";
  const personnel = b.template === "personnel_certificates";
  const text = (i: S["CertImportIssue"]) => (locale === "ar" ? i.message_ar : i.message_en);
  const shownCounts = COUNT_KEYS.filter((k) => (b.status === "committed" ? !["certificates_valid", "items_to_create"].includes(k) : !["certificates_created", "certificates_left_draft", "items_created"].includes(k)));

  async function act(kind: "commit" | "discard") {
    setBusy(true);
    setError(null);
    try {
      const res =
        kind === "commit"
          ? await unwrap(api.POST("/api/v1/certificate-imports/{batch_id}/commit", { params: { path: { batch_id: b.id } } }))
          : await unwrap(api.POST("/api/v1/certificate-imports/{batch_id}/discard", { params: { path: { batch_id: b.id } } }));
      refresh();
      toast.success(kind === "commit" ? t("committed", { n: res.counts.certificates_created }) : t("discarded"));
      if (kind === "discard") router.push("/certificate-imports");
    } catch (e) {
      setError(e);
      toast.error(msg(e));
      refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="ci-report">
      <Breadcrumbs items={[{ label: t("title"), href: "/certificate-imports" }, { label: b.file_name }]} />
      <PageHeader
        title={t("reportTitle")}
        description={`${b.file_name} · ${te(`certImportTemplate.${b.template}`)} · ${te(`certImportSource.${b.source}`)}${b.tpi_code ? ` · ${b.tpi_code}` : ""} · ${dateTime(b.created_at)}`}
        badge={<StatusBadge status={b.status} label={te(`certImportStatus.${b.status}`)} />}
      />
      <dl className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6" data-testid="ci-counts">
        {shownCounts.map((k) => (
          <div
            key={k}
            className={cn(
              "rounded-xl border bg-surface p-3 shadow-xs",
              k === "rows_error" && b.counts[k] > 0 && "border-danger/60 bg-danger-bg",
              (k === "rows_warning" || k === "certificates_left_draft") && b.counts[k] > 0 && "border-warning/60 bg-warning-bg",
            )}
            data-testid={`ci-count-${k}`}
          >
            <dt className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
              {k === "rows_error" && b.counts[k] > 0 ? <XCircle aria-hidden className="size-3.5 text-danger" /> : null}
              {k === "rows_warning" && b.counts[k] > 0 ? <AlertTriangle aria-hidden className="size-3.5 text-warning" /> : null}
              {t(`counts.${k}`)}
            </dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums">{b.counts[k]}</dd>
          </div>
        ))}
      </dl>
      <div className="mb-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span>
          {t("uploadedBy")}: <UserName u={b.uploaded_by} />
        </span>
        <span className="ltr">SHA-256 {b.file_sha256.slice(0, 12)}…</span>
        {b.scans_zip_name ? <span>{t("scansFound", { name: b.scans_zip_name, n: b.scans_count ?? 0 })}</span> : null}
        {b.evidence_file_name ? <span>{t("evidenceFile", { name: b.evidence_file_name })}</span> : null}
        {b.sensitive ? <span className="font-medium text-warning">{t("sensitive")}</span> : null}
      </div>
      {b.file_issues.length > 0 ? (
        <Alert tone="danger" className="mb-4">
          <p className="font-medium">{t("fileIssues")}</p>
          <ul className="list-disc ps-5">
            {b.file_issues.map((i, n) => (
              <li key={n}>
                <span className="font-mono ltr">{i.code}</span> {i.column ? <span className="ltr">[{i.column}]</span> : null} {text(i)}
              </li>
            ))}
          </ul>
        </Alert>
      ) : null}
      {pending ? (
        <div className="mb-4 flex flex-col gap-3 rounded-xl border bg-surface p-4 shadow-xs sm:flex-row sm:items-center sm:justify-between">
          <div className="text-sm">
            {b.counts.rows_error > 0 ? (
              <p className="flex items-center gap-1.5 font-medium" data-testid="ci-partial">
                <AlertTriangle aria-hidden className="size-4 shrink-0 text-warning" />
                {b.counts.certificates_valid > 0 ? t("partialCommit", { ok: b.counts.certificates_valid, err: b.counts.rows_error }) : t("nothingValid")}
              </p>
            ) : null}
            <p className="text-muted-foreground">{t("submittedNote")}</p>
            <p className="text-muted-foreground">{t("expiresAt", { time: dateTime(b.expires_at) })}</p>
          </div>
          {allowed ? (
            <div className="flex gap-2">
              <Button onClick={() => void act("commit")} disabled={busy || b.counts.certificates_valid === 0} data-testid="ci-commit">
                <CheckCircle2 aria-hidden />
                {t("commit", { n: b.counts.certificates_valid })}
              </Button>
              <Button variant="outline" onClick={() => void act("discard")} disabled={busy} data-testid="ci-discard">
                <Trash2 aria-hidden />
                {t("discard")}
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}
      {b.status === "expired" ? (
        <Alert tone="warning" className="mb-4">
          {t("expiredNote")}
        </Alert>
      ) : null}
      {b.status === "committed" ? (
        <Alert tone="success" className="mb-4" data-testid="ci-committed">
          {t("committedNote", { n: b.counts.certificates_created, draft: b.counts.certificates_left_draft })}{" "}
          <Link className="text-primary hover:underline" href={personnel ? "/personnel-certificates?status=submitted" : "/equipment-certificates?status=submitted"}>
            {t("viewCertificates")}
          </Link>
        </Alert>
      ) : null}
      <MutationError error={error} />
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold">{t("rows")}</h2>
        <CheckboxField id="ci-show-ok" label={t("showOk")}>
          <Checkbox checked={showOk} onChange={(e) => setShowOk(e.target.checked)} />
        </CheckboxField>
      </div>
      {b.report.length === 0 ? (
        <EmptyState message={t("noIssues")} />
      ) : (
        <Table data-testid="ci-rows">
          <THead>
            <TR>
              <TH>{t("rowNo")}</TH>
              <TH>{tc("status")}</TH>
              <TH>{t("codes")}</TH>
              <TH>{t("messages")}</TH>
              <TH>{t("certificate")}</TH>
              <TH>{personnel ? t("holder") : t("item")}</TH>
              <TH>{t("scan")}</TH>
              <TH>{t("action")}</TH>
            </TR>
          </THead>
          <TBody>
            {b.report.map((r) => (
              <TR key={r.row_no} data-testid="ci-row" data-row={r.row_no} data-status={r.status}>
                <TD label={t("rowNo")} className="tabular-nums">
                  {r.row_no}
                </TD>
                <TD label={tc("status")}>
                  <StatusBadge status={r.status} label={te(`importRowStatus.${r.status}`)} />
                </TD>
                <TD label={t("codes")}>
                  <span className="flex flex-wrap gap-1">
                    {r.codes.map((c) => (
                      <span key={c} title={te(`certImportCode.${c}`)} className={cn("rounded px-1 font-mono text-xs ltr", c.startsWith("E") ? "bg-danger-bg text-danger" : "bg-warning-bg text-warning")}>
                        {c}
                      </span>
                    ))}
                    {!r.codes.length ? "—" : null}
                  </span>
                </TD>
                <TD label={t("messages")}>
                  <ul className="flex flex-col gap-0.5">
                    {r.issues.map((i, n) => (
                      <li key={n}>{text(i)}</li>
                    ))}
                  </ul>
                </TD>
                <TD label={t("certificate")}>
                  <span className="ltr">
                    {r.tpi_code ? `${r.tpi_code} ` : ""}
                    {r.cert_no ? <Code>{r.cert_no}</Code> : "—"}
                  </span>
                  {r.cert_type ? <span className="block text-xs text-muted-foreground">{r.cert_type}</span> : null}
                </TD>
                <TD label={personnel ? t("holder") : t("item")}>
                  {personnel ? (
                    <span className="ltr">
                      {r.worker_no ?? "—"}
                      {r.id_masked ? <span className="block text-xs text-muted-foreground">{r.id_masked}</span> : null}
                    </span>
                  ) : (
                    <span className="ltr">
                      {r.tag ?? "—"}
                      {r.category ? <span className="block text-xs text-muted-foreground">{te.has(`eqc.${r.category as S["EquipmentCertCategory"]}`) ? te(`eqc.${r.category as S["EquipmentCertCategory"]}`) : r.category}</span> : null}
                    </span>
                  )}
                </TD>
                <TD label={t("scan")}>{r.scan_found == null ? "—" : r.scan_found ? t("scanYes") : t("scanNo")}</TD>
                <TD label={t("action")}>{r.action ?? "—"}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}
