"use client";
import { AlertTriangle, CheckCircle2, Download, FileUp, Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Code } from "@/components/access/common";
import { UserName } from "@/components/cert/common";
import { Link, useRouter } from "@/i18n/navigation";
import { ApiError, api, downloadFile, postForm, unwrap, type Schemas } from "@/lib/api/client";
import { useMedicalImport, useMedicalImports, useMedicalRefresh } from "@/lib/api/medical";
import { useErrorMessage } from "@/lib/i18n-helpers";
import { MED_IMPORT_SOURCES, MED_IMPORT_STATUSES } from "@/lib/med-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { FitnessCasesSubNav, MedProviderSelect, useMedCaps } from "./common";

type S = Schemas;
const PAGE_SIZE = 25;
const COUNT_KEYS = ["rows", "ok", "warnings", "errors"] as const;

export function MedicalImportsPage() {
  return <ProjectGate>{(p) => <MedicalImports project={p} />}</ProjectGate>;
}

function MedicalImports({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("medical.imports");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const msg = useErrorMessage();
  const router = useRouter();
  const caps = useMedCaps(project.id);
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const list = useMedicalImports(project.id, { status: (s.get("status") as S["MedicalImportStatus"]) || null, page, page_size: PAGE_SIZE });
  const [source, setSource] = useState<S["MedicalImportSource"]>(caps.clinical ? "clinic_register_file" : "contractor_file");
  const [file, setFile] = useState<File | null>(null);
  const [provider, setProvider] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const register = source === "clinic_register_file";
  const ready = !!file && (!register || !!provider);

  async function check() {
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.set("file", file);
    form.set("source", source);
    if (register) form.set("provider_id", provider);
    try {
      const res = await postForm<S["MedicalImportBatchRead"]>(`/api/v1/projects/${project.id}/medical-imports`, form);
      router.push(`/medical-imports/${res.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function download(headers: "en" | "ar") {
    try {
      await downloadFile(`/api/v1/medical-imports/template?format=csv&headers=${headers}`, `medical-import-template-${headers}.csv`);
    } catch (e) {
      toast.error(msg(e));
    }
  }

  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <FitnessCasesSubNav />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{t("check")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {caps.import ? (
              <>
                <Alert tone="info">{t("statusOnly")}</Alert>
                <div className="grid gap-3 sm:grid-cols-2">
                  <FormField id="mi-source" label={t("source")} hint={register ? t("registerHint") : t("contractorHint")}>
                    <Select id="mi-source" value={source} onChange={(e) => setSource(e.target.value as S["MedicalImportSource"])} data-testid="mi-source">
                      {MED_IMPORT_SOURCES.filter((x) => x === "contractor_file" || caps.clinical).map((x) => (
                        <option key={x} value={x}>
                          {te(`medImportSource.${x}`)}
                        </option>
                      ))}
                    </Select>
                  </FormField>
                  {register ? <MedProviderSelect id="mi-provider" label={t("provider")} projectId={project.id} value={provider} onChange={setProvider} required /> : null}
                </div>
                <FormField id="mi-file" label={t("file")} required hint={t("fileHint")}>
                  <Input id="mi-file" type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={(e) => setFile(e.target.files?.[0] ?? null)} data-testid="mi-file" />
                </FormField>
                <MutationError error={error} />
                <FileErrorDetail error={error} />
                <div>
                  <Button onClick={() => void check()} disabled={!ready || busy} data-testid="mi-check">
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
            <CardTitle>{t("template")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            <p className="text-xs text-muted-foreground">{t("templateHint")}</p>
            <div className="flex flex-wrap gap-2">
              {(["en", "ar"] as const).map((h) => (
                <Button key={h} variant="outline" size="sm" onClick={() => void download(h)} data-testid={`mi-tpl-${h}`}>
                  <Download aria-hidden />
                  {h === "en" ? t("csvEn") : t("csvAr")}
                </Button>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
      <h2 className="mt-8 mb-3 text-lg font-semibold">{t("history")}</h2>
      <ListToolbar>
        <SelectFilter id="mi-f-status" label={tc("status")} value={s.get("status") ?? ""} onChange={(v) => s.set({ status: v })} options={MED_IMPORT_STATUSES.map((x) => ({ value: x, label: te(`medImportStatus.${x}`) }))} />
      </ListToolbar>
      {list.isLoading ? (
        <LoadingState rows={2} />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : (list.data?.items.length ?? 0) === 0 ? (
        <EmptyState message={t("noImports")} />
      ) : (
        <>
          <Table data-testid="mi-history">
            <THead>
              <TR>
                <TH>{t("fileName")}</TH>
                <TH>{t("source")}</TH>
                <TH>{tc("status")}</TH>
                <TH className="text-end">{t("counts.ok")}</TH>
                <TH className="text-end">{t("counts.errors")}</TH>
                <TH>{t("uploadedBy")}</TH>
              </TR>
            </THead>
            <TBody>
              {list.data?.items.map((b) => (
                <TR key={b.id} data-testid="mi-batch" data-status={b.status}>
                  <TD label={t("fileName")}>
                    <Link href={`/medical-imports/${b.id}`} className="font-medium text-primary hover:underline ltr">
                      {b.file_name}
                    </Link>
                  </TD>
                  <TD label={t("source")}>{te(`medImportSource.${b.source}`)}</TD>
                  <TD label={tc("status")}>
                    <StatusBadge status={b.status} label={te(`medImportStatus.${b.status}`)} />
                  </TD>
                  <TD label={t("counts.ok")} className="text-end tabular-nums">
                    {b.counts.ok ?? 0}
                  </TD>
                  <TD label={t("counts.errors")} className="text-end tabular-nums">
                    {b.counts.errors ?? 0}
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

export function MedicalImportDetail({ id }: { id: string }) {
  const t = useTranslations("medical.imports");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const router = useRouter();
  const msg = useErrorMessage();
  const refresh = useMedicalRefresh();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const q = useMedicalImport(id);
  const pid = q.data?.project_id ?? null;
  const caps = useMedCaps(pid);
  const { dateTime } = useFormatters(pid);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const b = q.data;
  const pending = b.status === "validated";
  const valid = (b.counts.rows ?? 0) - (b.counts.errors ?? 0);
  const text = (i: S["MedicalImportIssue"]) => (locale === "ar" ? i.message_ar : i.message_en);

  async function act(kind: "commit" | "discard") {
    setBusy(true);
    setError(null);
    try {
      const res =
        kind === "commit"
          ? await unwrap(api.POST("/api/v1/medical-imports/{batch_id}/commit", { params: { path: { batch_id: b.id } } }))
          : await unwrap(api.POST("/api/v1/medical-imports/{batch_id}/discard", { params: { path: { batch_id: b.id } } }));
      refresh();
      toast.success(kind === "commit" ? t("committed", { n: res.committed_assessment_nos.length }) : t("discarded"));
      if (kind === "discard") router.push("/medical-imports");
    } catch (e) {
      setError(e);
      toast.error(msg(e));
      refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="mi-report">
      <Breadcrumbs items={[{ label: t("title"), href: "/medical-imports" }, { label: b.file_name }]} />
      <PageHeader title={t("reportTitle")} description={`${b.file_name} · ${te(`medImportSource.${b.source}`)} · ${dateTime(b.created_at)}`} badge={<StatusBadge status={b.status} label={te(`medImportStatus.${b.status}`)} />} />
      <dl className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4" data-testid="mi-counts">
        {COUNT_KEYS.map((k) => {
          const n = b.counts[k] ?? 0;
          return (
            <div key={k} className={cn("rounded-xl border bg-surface p-3 shadow-xs", k === "errors" && n > 0 && "border-danger/60 bg-danger-bg", k === "warnings" && n > 0 && "border-warning/60 bg-warning-bg")} data-testid={`mi-count-${k}`}>
              <dt className="text-xs font-medium text-muted-foreground">{t(`counts.${k}`)}</dt>
              <dd className="mt-1 text-2xl font-semibold tabular-nums">{n}</dd>
            </div>
          );
        })}
      </dl>
      <div className="mb-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span>
          {t("uploadedBy")}: <UserName u={b.uploaded_by} />
        </span>
        <span className="ltr">SHA-256 {b.file_sha256.slice(0, 12)}…</span>
      </div>
      {b.file_issues.length > 0 ? (
        <Alert tone="danger" className="mb-4">
          <p className="font-medium">{t("fileIssues")}</p>
          <ul className="list-disc ps-5">
            {b.file_issues.map((i, n) => (
              <li key={n} data-testid="mi-file-issue" data-code={i.code}>
                <span className="font-mono ltr">{i.code}</span> {i.field ? <span className="ltr">[{i.field}]</span> : null} {text(i)}
              </li>
            ))}
          </ul>
        </Alert>
      ) : null}
      {pending ? (
        <div className="mb-4 flex flex-col gap-3 rounded-xl border bg-surface p-4 shadow-xs sm:flex-row sm:items-center sm:justify-between">
          <div className="text-sm">
            {(b.counts.errors ?? 0) > 0 ? (
              <p className="flex items-center gap-1.5 font-medium" data-testid="mi-partial">
                <AlertTriangle aria-hidden className="size-4 shrink-0 text-warning" />
                {valid > 0 ? t("partialCommit", { ok: valid, err: b.counts.errors ?? 0 }) : t("nothingValid")}
              </p>
            ) : null}
            <p className="text-muted-foreground">{b.source === "clinic_register_file" ? t("registerNote") : t("contractorNote")}</p>
            <p className="text-muted-foreground">{t("expiresAt", { time: dateTime(b.expires_at) })}</p>
          </div>
          {caps.import ? (
            <div className="flex gap-2">
              <Button onClick={() => void act("commit")} disabled={busy || valid <= 0 || b.file_issues.length > 0} data-testid="mi-commit">
                <CheckCircle2 aria-hidden />
                {t("commit", { n: valid })}
              </Button>
              <Button variant="outline" onClick={() => void act("discard")} disabled={busy} data-testid="mi-discard">
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
        <Alert tone="success" className="mb-4" data-testid="mi-committed">
          <p>{t("committedNote", { n: b.committed_assessment_nos.length })}</p>
          <p className="mt-1 flex flex-wrap gap-1">
            {b.committed_assessment_nos.map((no) => (
              <Link key={no} href={`/fitness-assessments?q=${encodeURIComponent(no)}`} className="text-primary hover:underline">
                <Code>{no}</Code>
              </Link>
            ))}
          </p>
        </Alert>
      ) : null}
      <MutationError error={error} />
      <h2 className="mb-3 text-lg font-semibold">{t("rows")}</h2>
      {b.rows.length === 0 ? (
        <EmptyState message={t("noRows")} />
      ) : (
        <Table data-testid="mi-rows">
          <THead>
            <TR>
              <TH>{t("rowNo")}</TH>
              <TH>{tc("status")}</TH>
              <TH>{t("worker")}</TH>
              <TH>{t("code")}</TH>
              <TH>{t("certificate")}</TH>
              <TH>{t("issues")}</TH>
            </TR>
          </THead>
          <TBody>
            {b.rows.map((r) => (
              <TR key={r.row_no} data-testid="mi-row" data-row={r.row_no} data-status={r.status}>
                <TD label={t("rowNo")} className="tabular-nums">
                  {r.row_no}
                </TD>
                <TD label={tc("status")}>
                  <StatusBadge status={r.status} label={te.has(`importRowStatus.${r.status as "ok"}`) ? te(`importRowStatus.${r.status as "ok"}`) : r.status} />
                </TD>
                <TD label={t("worker")}>
                  <span className="ltr">
                    {r.worker_no ?? "—"}
                    {r.id_masked ? (
                      <span className="block text-xs text-muted-foreground" data-testid="mi-id-masked">
                        {r.id_masked}
                      </span>
                    ) : null}
                  </span>
                </TD>
                <TD label={t("code")}>{r.code ? <Code>{r.code}</Code> : "—"}</TD>
                <TD label={t("certificate")}>{r.certificate_no ? <Code>{r.certificate_no}</Code> : "—"}</TD>
                <TD label={t("issues")}>
                  <ul className="flex flex-col gap-0.5">
                    {r.issues.map((i, n) => (
                      <li key={n} data-testid="mi-issue" data-code={i.code}>
                        <span className={cn("me-1 rounded px-1 font-mono text-xs ltr", i.code.startsWith("E") ? "bg-danger-bg text-danger" : "bg-warning-bg text-warning")}>{i.code}</span>
                        {text(i)}
                      </li>
                    ))}
                    {!r.issues.length ? "—" : null}
                  </ul>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}

function FileErrorDetail({ error }: { error: unknown }) {
  const locale = useLocale();
  if (!(error instanceof ApiError) || error.code !== "IMPORT_FILE_INVALID") return null;
  const code = typeof error.meta.code === "string" ? error.meta.code : "";
  return (
    <p className="text-sm text-destructive" data-testid="mi-file-error" data-code={code}>
      {code ? <span className="me-1 font-mono ltr rtl:me-0 rtl:ms-1">{code}</span> : null}
      {locale === "ar" && error.messageAr ? error.messageAr : error.message}
    </p>
  );
}
