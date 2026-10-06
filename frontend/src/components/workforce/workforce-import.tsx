"use client";
import { CheckCircle2, Download, FileUp, Trash2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
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
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { api, downloadFile, postForm, unwrap, type Schemas } from "@/lib/api/client";
import { hk, useWorkforceImport, useWorkforceImports } from "@/lib/api/hse";
import { useDisplay } from "@/lib/digits";
import { IMPORT_MODES } from "@/lib/enums";
import { useErrorMessage, useLocalizedName } from "@/lib/i18n-helpers";
import { canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";

const COUNT_KEYS = ["rows_total", "rows_ok", "rows_warning", "rows_error", "rows_inserted", "rows_replaced"] as const;

export function WorkforceImportPage({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("imports");
  const tn = useTranslations("nav");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const msg = useErrorMessage();
  const router = useRouter();
  const name = useLocalizedName();
  const show = useDisplay(project.id);
  const { dateTime } = useFormatters(project.id);
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<Schemas["ImportMode"]>("insert_only");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const recent = useWorkforceImports(project.id, { page: 1, page_size: 10 });
  const allowed = canWrite(me, "workforce.import", project.id);

  async function check() {
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.set("file", file);
    form.set("mode", mode);
    try {
      const res = await postForm<Schemas["WorkforceImportRead"]>(`/api/v1/projects/${project.id}/workforce-imports`, form);
      router.push(`/workforce/imports/${res.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function template(format: Schemas["ExportFormat"], headers: "en" | "ar") {
    try {
      await downloadFile(`/api/v1/workforce-imports/template?format=${format}&headers=${headers}`, `workforce-template-${headers}.${format}`);
    } catch (e) {
      toast.error(msg(e));
    }
  }

  return (
    <div>
      <Breadcrumbs items={[{ label: tn("workforce"), href: "/workforce" }, { label: t("title") }]} />
      <PageHeader title={t("title")} description={t("subtitle")} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{t("check")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {allowed ? (
              <>
                <FormField id="import-file" label={t("file")} required>
                  <Input type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={(e) => setFile(e.target.files?.[0] ?? null)} data-testid="import-file" />
                </FormField>
                <FormField id="import-mode" label={t("mode")} hint={t("modeHint")}>
                  <Select value={mode} onChange={(e) => setMode(e.target.value as Schemas["ImportMode"])} data-testid="import-mode">
                    {IMPORT_MODES.map((m) => (
                      <option key={m} value={m}>
                        {te(`importMode.${m}`)}
                      </option>
                    ))}
                  </Select>
                </FormField>
                <MutationError error={error} />
                <div>
                  <Button onClick={() => void check()} disabled={!file || busy} data-testid="import-check">
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
            {(["en", "ar"] as const).map((h) => (
              <div key={h} className="flex flex-wrap items-center gap-2">
                <span className="min-w-28 text-sm">{h === "en" ? t("templateEn") : t("templateAr")}</span>
                <Button variant="outline" size="sm" onClick={() => void template("xlsx", h)}>
                  <Download aria-hidden />
                  Excel
                </Button>
                <Button variant="outline" size="sm" onClick={() => void template("csv", h)}>
                  <Download aria-hidden />
                  CSV
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
      <h2 className="mt-8 mb-3 text-lg font-semibold">{t("recent")}</h2>
      {recent.isLoading ? (
        <LoadingState rows={2} />
      ) : (recent.data?.items.length ?? 0) === 0 ? (
        <EmptyState />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>{t("fileName")}</TH>
              <TH>{t("mode")}</TH>
              <TH>{tc("status")}</TH>
              {COUNT_KEYS.slice(0, 4).map((k) => (
                <TH key={k} className="text-end">
                  {t(`counts.${k}`)}
                </TH>
              ))}
              <TH>{t("uploadedBy")}</TH>
            </TR>
          </THead>
          <TBody>
            {recent.data?.items.map((b) => (
              <TR key={b.id}>
                <TD label={t("fileName")}>
                  <Link href={`/workforce/imports/${b.id}`} className="font-medium text-primary hover:underline ltr">
                    {b.file_name}
                  </Link>
                </TD>
                <TD label={t("mode")}>{te(`importMode.${b.mode}`)}</TD>
                <TD label={tc("status")}>
                  <StatusBadge status={b.status} label={te(`importStatus.${b.status}`)} />
                </TD>
                {COUNT_KEYS.slice(0, 4).map((k) => (
                  <TD key={k} label={t(`counts.${k}`)} className="text-end tabular-nums">
                    {show(b.counts[k])}
                  </TD>
                ))}
                <TD label={t("uploadedBy")}>
                  {name(b.uploaded_by.full_name_en, b.uploaded_by.full_name_ar)} · {dateTime(b.created_at)}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}

export function ImportReport({ id }: { id: string }) {
  const t = useTranslations("imports");
  const tn = useTranslations("nav");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const me = useMeData();
  const qc = useQueryClient();
  const router = useRouter();
  const msg = useErrorMessage();
  const name = useLocalizedName();
  const [showOk, setShowOk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const q = useWorkforceImport(id, showOk);
  const pid = q.data?.project_id ?? null;
  const show = useDisplay(pid);
  const { dateTime } = useFormatters(pid);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const b = q.data;
  const allowed = canWrite(me, "workforce.import", b.project_id);
  const pending = b.status === "validated";
  const text = (i: Schemas["ImportIssue"]) => (locale === "ar" ? i.message_ar : i.message_en);

  async function act(kind: "commit" | "discard") {
    setBusy(true);
    setError(null);
    try {
      const res =
        kind === "commit"
          ? await unwrap(api.POST("/api/v1/workforce-imports/{batch_id}/commit", { params: { path: { batch_id: b.id } } }))
          : await unwrap(api.POST("/api/v1/workforce-imports/{batch_id}/discard", { params: { path: { batch_id: b.id } } }));
      qc.setQueryData(hk.importBatch(b.id, showOk), res);
      await qc.invalidateQueries({ queryKey: ["workforce-imports"] });
      await qc.invalidateQueries({ queryKey: ["workforce-returns"] });
      toast.success(kind === "commit" ? t("committed", { count: res.counts.rows_inserted + res.counts.rows_replaced }) : t("discarded"));
      if (kind === "discard") router.push("/workforce/import");
    } catch (e) {
      setError(e);
      toast.error(msg(e));
      await qc.invalidateQueries({ queryKey: ["workforce-import", b.id] });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="import-report">
      <Breadcrumbs items={[{ label: tn("workforce"), href: "/workforce" }, { label: t("title"), href: "/workforce/import" }, { label: b.file_name }]} />
      <PageHeader
        title={t("reportTitle")}
        description={`${b.file_name} · ${te(`importMode.${b.mode}`)} · ${name(b.uploaded_by.full_name_en, b.uploaded_by.full_name_ar)} · ${dateTime(b.created_at)}`}
        badge={<StatusBadge status={b.status} label={te(`importStatus.${b.status}`)} />}
      />
      <dl className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6" data-testid="import-counts">
        {COUNT_KEYS.map((k) => (
          <div key={k} className="rounded-xl border bg-surface p-3 shadow-xs" data-testid={`count-${k}`}>
            <dt className="text-xs font-medium text-muted-foreground">{t(`counts.${k}`)}</dt>
            <dd className="mt-1 text-2xl font-semibold">{show(b.counts[k])}</dd>
          </div>
        ))}
      </dl>
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
            {b.counts.rows_error > 0 ? <p className="font-medium text-danger" data-testid="commit-blocked">{t("blockedByErrors")}</p> : null}
            <p className="text-muted-foreground">{t("expiresAt", { time: dateTime(b.expires_at) })}</p>
          </div>
          {allowed ? (
            <div className="flex gap-2">
              <Button onClick={() => void act("commit")} disabled={busy || b.counts.rows_error > 0} data-testid="import-commit">
                <CheckCircle2 aria-hidden />
                {t("commit")}
              </Button>
              <Button variant="outline" onClick={() => void act("discard")} disabled={busy} data-testid="import-discard">
                <Trash2 aria-hidden />
                {t("discard")}
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}
      {b.status === "expired" ? <Alert tone="warning" className="mb-4">{t("expiredNote")}</Alert> : null}
      {b.status === "committed" ? (
        <p className="mb-4">
          <Link className="text-primary hover:underline" href={`/workforce?import_batch_id=${b.id}`}>
            {t("viewRows")}
          </Link>
        </p>
      ) : null}
      <MutationError error={error} />
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold">{t("messages")}</h2>
        <CheckboxField id="show-ok" label={t("showOk")}>
          <Checkbox checked={showOk} onChange={(e) => setShowOk(e.target.checked)} />
        </CheckboxField>
      </div>
      {b.report.length === 0 ? (
        <EmptyState message={t("noIssues")} />
      ) : (
        <Table data-testid="import-rows">
          <THead>
            <TR>
              <TH>{t("rowNo")}</TH>
              <TH>{tc("status")}</TH>
              <TH>{t("codes")}</TH>
              <TH>{t("messages")}</TH>
              <TH>{tc("date")}</TH>
              <TH>{tc("site")}</TH>
              <TH>{tc("contractor")}</TH>
              <TH>{t("action")}</TH>
            </TR>
          </THead>
          <TBody>
            {b.report.map((r) => (
              <TR key={r.row_no} data-testid="import-row" data-row={r.row_no} data-status={r.status}>
                <TD label={t("rowNo")} className="tabular-nums">
                  {show(r.row_no)}
                </TD>
                <TD label={tc("status")}>
                  <StatusBadge status={r.status} label={te(`importRowStatus.${r.status}`)} />
                </TD>
                <TD label={t("codes")}>
                  <span className="font-mono text-xs ltr">{r.codes.join(", ") || "—"}</span>
                </TD>
                <TD label={t("messages")}>
                  <ul className="flex flex-col gap-0.5">
                    {r.issues.map((i, n) => (
                      <li key={n}>{text(i)}</li>
                    ))}
                  </ul>
                </TD>
                <TD label={tc("date")}>
                  <span className="ltr">{r.work_date ?? "—"}</span>
                </TD>
                <TD label={tc("site")}>
                  <span className="ltr">{[r.site_code, r.zone_code].filter(Boolean).join(" / ") || "—"}</span>
                </TD>
                <TD label={tc("contractor")}>
                  <span className="ltr">{r.contractor_code ?? "—"}</span> {r.shift ? `· ${te(`shift.${r.shift}`)}` : ""}
                </TD>
                <TD label={t("action")}>{r.action && ["insert", "replace", "none"].includes(r.action) ? t(`actionValue.${r.action as "insert"}`) : "—"}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}
