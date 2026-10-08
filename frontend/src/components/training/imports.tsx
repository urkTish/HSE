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
import { UserName } from "@/components/cert/common";
import { Link, useRouter } from "@/i18n/navigation";
import { ApiError, api, downloadFile, postForm, unwrap, type Schemas } from "@/lib/api/client";
import { useTrainingImport, useTrainingImports, useTrainingRefresh, useTrainingSessions } from "@/lib/api/training";
import { useErrorMessage } from "@/lib/i18n-helpers";
import { TRAINING_IMPORT_SOURCES, TRAINING_IMPORT_STATUSES, TRAINING_IMPORT_TEMPLATES } from "@/lib/train-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { ProviderSelect, TrainingRecordsSubNav, useTrainingCaps } from "./common";

type S = Schemas;
const PAGE_SIZE = 25;
type CountKey = keyof S["TrainingImportCounts"];

export function TrainingImportListPage() {
  return <ProjectGate>{(p) => <TrainingImports project={p} />}</ProjectGate>;
}

function TrainingImports({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("training.imports");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const msg = useErrorMessage();
  const router = useRouter();
  const caps = useTrainingCaps(project.id);
  const { dateTime, date } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const list = useTrainingImports(project.id, {
    status: (s.get("status") as S["TrainingImportStatus"]) || null,
    template: (s.get("template") as S["TrainingImportTemplate"]) || null,
    page,
    page_size: PAGE_SIZE,
  });
  const officer = caps.manager || caps.recordReview;
  const [template, setTemplate] = useState<S["TrainingImportTemplate"]>("training_records");
  const [source, setSource] = useState<S["TrainingImportSource"]>("contractor_file");
  const [file, setFile] = useState<File | null>(null);
  const [scans, setScans] = useState<File | null>(null);
  const [evidence, setEvidence] = useState<File | null>(null);
  const [provider, setProvider] = useState("");
  const [session, setSession] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const attendance = template === "session_attendance";
  const register = !attendance && source === "provider_register_file";
  const sessions = useTrainingSessions(project.id, { status: ["delivered"], page_size: 100 }, { enabled: attendance });
  const ready = !!file && (!attendance || !!session) && (!register || (!!evidence && !!provider));

  async function check() {
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.set("file", file);
    form.set("template", template);
    form.set("source", attendance ? "contractor_file" : source);
    if (attendance) form.set("session_id", session);
    if (!attendance && scans) form.set("scans_zip", scans);
    if (register) {
      form.set("provider_id", provider);
      if (evidence) form.set("evidence_file", evidence);
    }
    try {
      const res = await postForm<S["TrainingImportRead"]>(`/api/v1/projects/${project.id}/training-imports`, form);
      router.push(`/training-imports/${res.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function download(tpl: S["TrainingImportTemplate"], headers: "en" | "ar") {
    try {
      await downloadFile(`/api/v1/training-imports/template?template=${tpl}&format=xlsx&headers=${headers}`, `${tpl}-template-${headers}.xlsx`);
    } catch (e) {
      toast.error(msg(e));
    }
  }

  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <TrainingRecordsSubNav />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{t("check")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {caps.import ? (
              <>
                <div className="grid gap-3 sm:grid-cols-2">
                  <FormField id="ti-template" label={t("template")} required>
                    <Select id="ti-template" value={template} onChange={(e) => setTemplate(e.target.value as S["TrainingImportTemplate"])} data-testid="ti-template">
                      {TRAINING_IMPORT_TEMPLATES.map((x) => (
                        <option key={x} value={x}>
                          {te(`trainingImportTemplate.${x}`)}
                        </option>
                      ))}
                    </Select>
                  </FormField>
                  {!attendance ? (
                    <FormField id="ti-source" label={t("source")} hint={register ? t("registerHint") : undefined}>
                      <Select id="ti-source" value={source} onChange={(e) => setSource(e.target.value as S["TrainingImportSource"])} data-testid="ti-source">
                        {TRAINING_IMPORT_SOURCES.filter((x) => x === "contractor_file" || officer).map((x) => (
                          <option key={x} value={x}>
                            {te(`trainingImportSource.${x}`)}
                          </option>
                        ))}
                      </Select>
                    </FormField>
                  ) : (
                    <FormField id="ti-session" label={t("session")} required hint={t("sessionHint")}>
                      <Select id="ti-session" value={session} onChange={(e) => setSession(e.target.value)} data-testid="ti-session">
                        <option value="">{tc("select")}</option>
                        {(sessions.data?.items ?? []).map((x) => (
                          <option key={x.id} value={x.id}>
                            {x.session_no} · {x.course.code} · {date(x.first_day)}
                          </option>
                        ))}
                      </Select>
                    </FormField>
                  )}
                </div>
                <FormField id="ti-file" label={t("file")} required hint={t("fileHint")}>
                  <Input id="ti-file" type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={(e) => setFile(e.target.files?.[0] ?? null)} data-testid="ti-file" />
                </FormField>
                {!attendance ? (
                  <FormField id="ti-scans" label={t("scansZip")} hint={t("scansHint")}>
                    <Input id="ti-scans" type="file" accept=".zip,application/zip" onChange={(e) => setScans(e.target.files?.[0] ?? null)} data-testid="ti-scans" />
                  </FormField>
                ) : null}
                {register ? (
                  <>
                    <ProviderSelect id="ti-provider" label={t("provider")} value={provider} onChange={(v) => setProvider(v)} required />
                    <FormField id="ti-evidence" label={t("evidence")} required hint={t("evidenceHint")}>
                      <Input id="ti-evidence" type="file" accept=".pdf,.eml,application/pdf,message/rfc822" onChange={(e) => setEvidence(e.target.files?.[0] ?? null)} data-testid="ti-evidence" />
                    </FormField>
                  </>
                ) : null}
                <MutationError error={error} />
                <FileErrorDetail error={error} />
                <div>
                  <Button onClick={() => void check()} disabled={!ready || busy} data-testid="ti-check">
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
            {TRAINING_IMPORT_TEMPLATES.map((tpl) => (
              <div key={tpl} className="flex flex-col gap-1">
                <span className="text-sm font-medium">{te(`trainingImportTemplate.${tpl}`)}</span>
                <div className="flex flex-wrap gap-2">
                  {(["en", "ar"] as const).map((h) => (
                    <Button key={h} variant="outline" size="sm" onClick={() => void download(tpl, h)} data-testid={`ti-tpl-${tpl}-${h}`}>
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
        <SelectFilter id="ti-f-status" label={tc("status")} value={s.get("status") ?? ""} onChange={(v) => s.set({ status: v })} options={TRAINING_IMPORT_STATUSES.map((x) => ({ value: x, label: te(`trainingImportStatus.${x}`) }))} />
        <SelectFilter id="ti-f-template" label={t("template")} value={s.get("template") ?? ""} onChange={(v) => s.set({ template: v })} options={TRAINING_IMPORT_TEMPLATES.map((x) => ({ value: x, label: te(`trainingImportTemplate.${x}`) }))} />
      </ListToolbar>
      {list.isLoading ? (
        <LoadingState rows={2} />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : (list.data?.items.length ?? 0) === 0 ? (
        <EmptyState message={t("noImports")} />
      ) : (
        <>
          <Table data-testid="ti-history">
            <THead>
              <TR>
                <TH>{t("fileName")}</TH>
                <TH>{t("template")}</TH>
                <TH>{tc("status")}</TH>
                <TH className="text-end">{t("counts.rows_ok")}</TH>
                <TH className="text-end">{t("counts.rows_error")}</TH>
                <TH className="text-end">{t("counts.records_created")}</TH>
                <TH>{t("uploadedBy")}</TH>
              </TR>
            </THead>
            <TBody>
              {list.data?.items.map((b) => (
                <TR key={b.id}>
                  <TD label={t("fileName")}>
                    <Link href={`/training-imports/${b.id}`} className="font-medium text-primary hover:underline ltr">
                      {b.file_name}
                    </Link>
                  </TD>
                  <TD label={t("template")}>
                    {te(`trainingImportTemplate.${b.template}`)}
                    <span className="block text-xs text-muted-foreground">{te(`trainingImportSource.${b.source}`)}</span>
                  </TD>
                  <TD label={tc("status")}>
                    <StatusBadge status={b.status} label={te(`trainingImportStatus.${b.status}`)} />
                  </TD>
                  <TD label={t("counts.rows_ok")} className="text-end tabular-nums">
                    {b.counts.rows_ok}
                  </TD>
                  <TD label={t("counts.rows_error")} className="text-end tabular-nums">
                    {b.counts.rows_error}
                  </TD>
                  <TD label={t("counts.records_created")} className="text-end tabular-nums">
                    {b.template === "session_attendance" ? b.counts.attendance_rows_applied : b.counts.records_created}
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

export function TrainingImportDetail({ id }: { id: string }) {
  const t = useTranslations("training.imports");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const router = useRouter();
  const msg = useErrorMessage();
  const refresh = useTrainingRefresh();
  const [showOk, setShowOk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const q = useTrainingImport(id, showOk);
  const pid = q.data?.project_id ?? null;
  const caps = useTrainingCaps(pid);
  const { dateTime } = useFormatters(pid);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const b = q.data;
  const pending = b.status === "validated";
  const attendance = b.template === "session_attendance";
  const committed = b.status === "committed";
  const valid = b.counts.rows_total - b.counts.rows_error;
  const text = (i: S["TrainingImportIssue"]) => (locale === "ar" ? i.message_ar : i.message_en);
  const shown: CountKey[] = ["rows_total", "rows_ok", "rows_warning", "rows_error", ...(committed ? (attendance ? (["attendance_rows_applied"] as CountKey[]) : (["records_created", "records_left_draft"] as CountKey[])) : [])];

  async function act(kind: "commit" | "discard") {
    setBusy(true);
    setError(null);
    try {
      const res =
        kind === "commit"
          ? await unwrap(api.POST("/api/v1/training-imports/{batch_id}/commit", { params: { path: { batch_id: b.id } } }))
          : await unwrap(api.POST("/api/v1/training-imports/{batch_id}/discard", { params: { path: { batch_id: b.id } } }));
      await refresh();
      toast.success(kind === "commit" ? t("committed", { n: attendance ? res.counts.attendance_rows_applied : res.counts.records_created }) : t("discarded"));
      if (kind === "discard") router.push("/training-imports");
    } catch (e) {
      setError(e);
      toast.error(msg(e));
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="ti-report">
      <Breadcrumbs items={[{ label: t("title"), href: "/training-imports" }, { label: b.file_name }]} />
      <PageHeader
        title={t("reportTitle")}
        description={`${b.file_name} · ${te(`trainingImportTemplate.${b.template}`)} · ${te(`trainingImportSource.${b.source}`)}${b.provider_code ? ` · ${b.provider_code}` : ""} · ${dateTime(b.created_at)}`}
        badge={<StatusBadge status={b.status} label={te(`trainingImportStatus.${b.status}`)} />}
      />
      <dl className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6" data-testid="ti-counts">
        {shown.map((k) => (
          <div
            key={k}
            className={cn(
              "rounded-xl border bg-surface p-3 shadow-xs",
              k === "rows_error" && b.counts[k] > 0 && "border-danger/60 bg-danger-bg",
              (k === "rows_warning" || k === "records_left_draft") && b.counts[k] > 0 && "border-warning/60 bg-warning-bg",
            )}
            data-testid={`ti-count-${k}`}
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
        {b.session_id ? (
          <Link href={`/training-sessions/${b.session_id}`} className="text-primary hover:underline">
            {t("openSession")}
          </Link>
        ) : null}
        {b.scans_zip_name ? <span>{t("scansFound", { name: b.scans_zip_name, n: b.scans_count ?? 0 })}</span> : null}
        {b.evidence_file_name ? <span>{t("evidenceFile", { name: b.evidence_file_name })}</span> : null}
        {b.sensitive ? <span className="font-medium text-warning">{t("sensitive")}</span> : null}
      </div>
      {b.file_issues.length > 0 ? (
        <Alert tone="danger" className="mb-4">
          <p className="font-medium">{t("fileIssues")}</p>
          <ul className="list-disc ps-5">
            {b.file_issues.map((i, n) => (
              <li key={n} data-testid="ti-file-issue" data-code={i.code}>
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
              <p className="flex items-center gap-1.5 font-medium" data-testid="ti-partial">
                <AlertTriangle aria-hidden className="size-4 shrink-0 text-warning" />
                {valid > 0 ? t("partialCommit", { ok: valid, err: b.counts.rows_error }) : t("nothingValid")}
              </p>
            ) : null}
            <p className="text-muted-foreground">{attendance ? t("attendanceNote") : t("submittedNote")}</p>
            <p className="text-muted-foreground">{t("expiresAt", { time: dateTime(b.expires_at) })}</p>
          </div>
          {caps.import ? (
            <div className="flex gap-2">
              <Button onClick={() => void act("commit")} disabled={busy || valid <= 0 || b.file_issues.length > 0} data-testid="ti-commit">
                <CheckCircle2 aria-hidden />
                {t("commit", { n: valid })}
              </Button>
              <Button variant="outline" onClick={() => void act("discard")} disabled={busy} data-testid="ti-discard">
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
      {committed ? (
        <Alert tone="success" className="mb-4" data-testid="ti-committed">
          {attendance ? t("committedAttendance", { n: b.counts.attendance_rows_applied }) : t("committedNote", { n: b.counts.records_created, draft: b.counts.records_left_draft })}{" "}
          {attendance && b.session_id ? (
            <Link className="text-primary hover:underline" href={`/training-sessions/${b.session_id}`}>
              {t("openSession")}
            </Link>
          ) : (
            <Link className="text-primary hover:underline" href="/training-records?status=submitted">
              {t("viewRecords")}
            </Link>
          )}
        </Alert>
      ) : null}
      <MutationError error={error} />
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold">{t("rows")}</h2>
        <CheckboxField id="ti-show-ok" label={t("showOk")}>
          <Checkbox checked={showOk} onChange={(e) => setShowOk(e.target.checked)} />
        </CheckboxField>
      </div>
      {b.report.length === 0 ? (
        <EmptyState message={t("noIssues")} />
      ) : (
        <Table data-testid="ti-rows">
          <THead>
            <TR>
              <TH>{t("rowNo")}</TH>
              <TH>{tc("status")}</TH>
              <TH>{t("codes")}</TH>
              <TH>{t("messages")}</TH>
              <TH>{t("worker")}</TH>
              {attendance ? <TH>{t("dayNo")}</TH> : <TH>{t("certificate")}</TH>}
              {!attendance ? <TH>{t("scan")}</TH> : null}
            </TR>
          </THead>
          <TBody>
            {b.report.map((r) => (
              <TR key={r.row_no} data-testid="ti-row" data-row={r.row_no} data-status={r.status}>
                <TD label={t("rowNo")} className="tabular-nums">
                  {r.row_no}
                </TD>
                <TD label={tc("status")}>
                  <StatusBadge status={r.status} label={te(`importRowStatus.${r.status}`)} />
                </TD>
                <TD label={t("codes")}>
                  <span className="flex flex-wrap gap-1">
                    {r.codes.map((c) => (
                      <span key={c} title={te(`trainingImportCode.${c}`)} className={cn("rounded px-1 font-mono text-xs ltr", c.startsWith("E") ? "bg-danger-bg text-danger" : "bg-warning-bg text-warning")}>
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
                <TD label={t("worker")}>
                  <span className="ltr">
                    {r.worker_no ?? "—"}
                    {r.id_masked ? (
                      <span className="block text-xs text-muted-foreground" data-testid="ti-id-masked">
                        {r.id_masked}
                      </span>
                    ) : null}
                  </span>
                </TD>
                {attendance ? (
                  <TD label={t("dayNo")} className="tabular-nums">
                    {r.day_no ?? "—"}
                  </TD>
                ) : (
                  <TD label={t("certificate")}>
                    <span className="ltr">
                      {r.provider_code ? `${r.provider_code} ` : ""}
                      {r.certificate_no ? <Code>{r.certificate_no}</Code> : "—"}
                    </span>
                    {r.course_code ? <span className="block text-xs text-muted-foreground">{r.course_code}</span> : null}
                  </TD>
                )}
                {!attendance ? <TD label={t("scan")}>{r.scan_found == null ? "—" : r.scan_found ? t("scanYes") : t("scanNo")}</TD> : null}
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}

/** A rejected file (IMPORT_FILE_INVALID) carries the template code (e.g. E12) and the server's own wording of what is missing. */
function FileErrorDetail({ error }: { error: unknown }) {
  const locale = useLocale();
  if (!(error instanceof ApiError) || error.code !== "IMPORT_FILE_INVALID") return null;
  const code = typeof error.meta.code === "string" ? error.meta.code : "";
  return (
    <p className="text-sm text-destructive" data-testid="ti-file-error" data-code={code}>
      {code ? <span className="me-1 font-mono ltr">{code}</span> : null}
      {locale === "ar" && error.messageAr ? error.messageAr : error.message}
    </p>
  );
}
