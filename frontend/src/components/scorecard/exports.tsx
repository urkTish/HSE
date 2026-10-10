"use client";
import { Bell, Download, FileDown, Loader2, Printer, Settings2, ShieldAlert, Trash2, UserRound } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Code } from "@/components/access/common";
import { ExportButtons } from "@/components/common/export-buttons";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { useMeData } from "@/components/shell/me-context";
import { Choices } from "@/components/followup/common";
import { Link } from "@/i18n/navigation";
import { api, downloadFile, unwrap, type Schemas } from "@/lib/api/client";
import type { KpiQuery } from "@/lib/api/kpi";
import { useExportDatasets, useExportJobs, useExportSubscriptions, useScRefresh } from "@/lib/api/scorecard";
import { useCurrentProject } from "@/lib/current-project";
import { useErrorMessage, useLocalizedName } from "@/lib/i18n-helpers";
import { can, type Capability } from "@/lib/permissions";
import { useDisplay } from "@/lib/digits";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState, toQueryString } from "@/lib/url-state";
import { ReportsSubNav, ScBadge, useScCaps } from "./common";

type S = Schemas;
type Dataset = S["XpDatasetRead"];

const PURPOSES: S["XpPurpose"][] = ["gosi", "mhrsd", "client_report", "legal", "insurance", "audit", "data_subject_request", "internal_analysis", "other"];

/* ═════════════ generic register export (EX-1…EX-10) ═════════════ */

export function ExportsPage() {
  const t = useTranslations("xp");
  const ar = useLocale() === "ar";
  const me = useMeData();
  const { project } = useCurrentProject();
  const pid = project?.id ?? null;
  const s = useSearchState();
  const q = useExportDatasets();
  const datasets = useMemo(() => (q.data?.items ?? []).filter((d) => (!d.project_required || pid) && can(me, d.export_capability as Capability, d.project_required ? pid : null)), [q.data, me, pid]);
  const code = s.get("dataset") ?? "";
  const ds = datasets.find((d) => d.dataset_code === code) ?? null;
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <ReportsSubNav />
      <div className="flex flex-col gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("newExport")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {q.isLoading ? (
              <LoadingState rows={2} />
            ) : q.isError ? (
              <ErrorState error={q.error} onRetry={() => q.refetch()} />
            ) : (
              <FormField id="xp-dataset" label={t("dataset")}>
                <div className="sm:w-96">
                  <Select id="xp-dataset" value={code} onChange={(e) => s.set({ dataset: e.target.value || null })} data-testid="xp-dataset">
                    <option value="">—</option>
                    {datasets.map((d) => (
                      <option key={d.dataset_code} value={d.dataset_code}>
                        {ar ? d.label_ar : d.label_en}
                      </option>
                    ))}
                  </Select>
                </div>
              </FormField>
            )}
            {ds ? <ExportForm key={ds.dataset_code} ds={ds} projectId={pid} /> : <p className="text-sm text-muted-foreground">{t("pick")}</p>}
          </CardContent>
        </Card>
        <Jobs />
        <Subscriptions />
      </div>
    </div>
  );
}

function ExportForm({ ds, projectId }: { ds: Dataset; projectId: string | null }) {
  const t = useTranslations("xp");
  const te = useTranslations("enums");
  const tf = useTranslations("fu.common");
  const ar = useLocale() === "ar";
  const refresh = useScRefresh();
  const defaults = ds.columns.filter((c) => c.default).map((c) => c.column_code);
  const [cols, setCols] = useState<string[]>(defaults);
  const [format, setFormat] = useState<S["XpFormat"]>("csv");
  const [purpose, setPurpose] = useState<S["XpPurpose"] | "">("");
  const [purposeText, setPurposeText] = useState("");
  const [freq, setFreq] = useState<S["XpFrequency"]>("weekly");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [job, setJob] = useState<S["XpJobRead"] | null>(null);
  const changed = cols.slice().sort().join() !== defaults.slice().sort().join();
  const sensitive = ds.columns.some((c) => cols.includes(c.column_code) && c.pdpl_class === "sensitive");
  const personal = ds.columns.some((c) => cols.includes(c.column_code) && c.pdpl_class !== "none" && !c.default);
  const needPurpose = ds.purpose_required_when === "always" || sensitive;
  const body = (): S["XpExportRequest"] => ({
    dataset: ds.dataset_code,
    format,
    project_id: ds.project_required ? projectId : null,
    columns: changed ? cols : [],
    purpose: purpose || null,
    purpose_text: purpose === "other" ? purposeText.trim() : null,
  });

  async function run() {
    setBusy(true);
    setError(null);
    setJob(null);
    try {
      const j = await unwrap(api.POST("/api/v1/exports", { body: body() }));
      setJob(j);
      await refresh();
      toast.success(j.status === "ready" ? t("ready", { no: j.export_no }) : t("queued", { no: j.export_no }));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function subscribe() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(api.POST("/api/v1/export-subscriptions", { body: { dataset: ds.dataset_code, project_id: ds.project_required ? projectId : null, columns: changed ? cols : [], format, frequency: freq } }));
      await refresh();
      toast.success(t("subscribed"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4" data-testid="xp-form">
      {ds.aggregate ? <Alert tone="info">{t("aggregate")}</Alert> : null}
      {ds.columns.length ? (
        <fieldset>
          <legend className="mb-2 text-sm font-medium">{t("columns")}</legend>
          <ul className="grid gap-1 sm:grid-cols-2 lg:grid-cols-3" data-testid="xp-columns">
            {ds.columns.map((c) => {
              const never = c.pdpl_class === "never";
              const disabled = never || !c.allowed;
              return (
                <li key={c.column_code}>
                  <label className={`flex min-h-touch items-center gap-2 rounded-md px-2 text-sm ${disabled ? "text-muted-foreground" : ""}`} data-testid="xp-column" data-column={c.column_code} data-pdpl={c.pdpl_class}>
                    <Checkbox
                      checked={cols.includes(c.column_code)}
                      disabled={disabled}
                      onChange={(e) => setCols(e.target.checked ? [...cols, c.column_code] : cols.filter((x) => x !== c.column_code))}
                    />
                    <span className="min-w-0 flex-1">{ar ? c.label_ar : c.label_en}</span>
                    {c.pdpl_class !== "none" ? (
                      <span className={`inline-flex items-center gap-1 rounded px-1.5 text-xs ${c.pdpl_class === "sensitive" || never ? "bg-danger-bg text-danger" : "bg-warning-bg text-warning"}`}>
                        {c.pdpl_class === "sensitive" || never ? <ShieldAlert aria-hidden className="size-3.5" /> : <UserRound aria-hidden className="size-3.5" />}
                        {te(`xpPdpl.${c.pdpl_class}`)}
                      </span>
                    ) : null}
                  </label>
                  {c.mask_mode && !cols.includes(c.column_code) && !never ? <p className="ps-9 text-xs text-muted-foreground">{t("maskedAs", { m: te(`xpMaskMode.${c.mask_mode}`) })}</p> : null}
                  {never ? <p className="ps-9 text-xs text-muted-foreground">{t("never")}</p> : !c.allowed ? <p className="ps-9 text-xs text-muted-foreground">{t("noRight")}</p> : null}
                </li>
              );
            })}
          </ul>
        </fieldset>
      ) : (
        <p className="text-sm text-muted-foreground">{t("defaultColumns")}</p>
      )}
      <fieldset className="flex flex-col gap-1">
        <legend className="mb-1 text-sm font-medium">{t("format")}</legend>
        <Choices
          label={t("format")}
          testId="xp-format"
          value={format}
          options={(["csv", "xlsx", ...(ds.pdf_allowed ? (["pdf"] as const) : [])] as S["XpFormat"][]).map((f) => ({ value: f, label: te(`xpFormat.${f}`) }))}
          onChange={setFormat}
        />
      </fieldset>
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="xp-purpose" label={t("purpose")} required={needPurpose} hint={needPurpose ? t("purposeNeeded") : t("purposeHint")}>
          <Select id="xp-purpose" value={purpose} onChange={(e) => setPurpose(e.target.value as S["XpPurpose"])} data-testid="xp-purpose">
            <option value="">—</option>
            {PURPOSES.map((p) => (
              <option key={p} value={p}>
                {te(`xpPurpose.${p}`)}
              </option>
            ))}
          </Select>
        </FormField>
        {purpose === "other" ? (
          <FormField id="xp-purpose-text" label={t("purposeText")} required hint={tf("reasonMin", { min: 20, n: purposeText.trim().length })}>
            <Input id="xp-purpose-text" value={purposeText} onChange={(e) => setPurposeText(e.target.value)} data-testid="xp-purpose-text" />
          </FormField>
        ) : null}
      </div>
      {sensitive ? <Alert tone="warning">{t("sensitiveNote")}</Alert> : null}
      <MutationError error={error} />
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => void run()} disabled={busy} data-testid="xp-run">
          <FileDown aria-hidden />
          {t("run")}
        </Button>
        {job ? <JobDownload job={job} /> : null}
      </div>
      <div className="flex flex-wrap items-end gap-2 border-t pt-4">
        <FormField id="xp-freq" label={t("frequency")}>
          <Select id="xp-freq" value={freq} onChange={(e) => setFreq(e.target.value as S["XpFrequency"])} data-testid="xp-frequency">
            {(["weekly", "monthly"] as const).map((f) => (
              <option key={f} value={f}>
                {te(`xpFrequency.${f}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <Button variant="outline" onClick={() => void subscribe()} disabled={busy || personal} data-testid="xp-subscribe">
          <Bell aria-hidden />
          {t("subscribe")}
        </Button>
        <p className="w-full text-xs text-muted-foreground">{personal ? t("subscribeNoPersonal") : t("subscribeHint")}</p>
      </div>
    </div>
  );
}

function JobDownload({ job }: { job: S["XpJobRead"] }) {
  const t = useTranslations("xp");
  const [error, setError] = useState<unknown>(null);
  if (job.status !== "ready") return <ScBadge group="xpJobStatus" status={job.status} />;
  return (
    <>
      <Button
        variant="outline"
        size="sm"
        onClick={async () => {
          setError(null);
          try {
            const u = await unwrap(api.GET("/api/v1/export-jobs/{job_id}/file-url", { params: { path: { job_id: job.id } } }));
            window.open(u.url, "_blank", "noopener");
          } catch (e) {
            setError(e);
          }
        }}
        data-testid="xp-download"
      >
        <Download aria-hidden />
        {t("download")}
      </Button>
      <MutationError error={error} />
    </>
  );
}

/* ═════════════ export log (232): own jobs; project jobs for officers; all for the HSE Manager ═════════════ */

function Jobs() {
  const t = useTranslations("xp");
  const te = useTranslations("enums");
  const ar = useLocale() === "ar";
  const datasets = useExportDatasets();
  const dsLabel = (code: string) => {
    const d = datasets.data?.items.find((x) => x.dataset_code === code);
    return d ? (ar ? d.label_ar : d.label_en) : null;
  };
  const name = useLocalizedName();
  const caps = useScCaps();
  const show = useDisplay();
  const { dateTime } = useFormatters();
  const s = useSearchState();
  const status = (s.get("status") as S["XpJobStatus"] | null) ?? "";
  const mine = s.get("mine") !== "0";
  const q = useExportJobs({ status: status || null, mine, page_size: 100 });
  const items = q.data?.items ?? [];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t("log")}</CardTitle>
        <p className="text-xs text-muted-foreground">{t("logHint")}</p>
      </CardHeader>
      <CardContent>
        <ListToolbar>
          <SelectFilter id="xj-status" label={t("status")} value={status} onChange={(v) => s.set({ status: v || null })} options={(["queued", "ready", "expired", "failed"] as const).map((x) => ({ value: x, label: te(`xpJobStatus.${x}`) }))} />
          {caps.me?.is_hse_manager || can(caps.me, "report_pack.prepare") ? (
            <SelectFilter id="xj-mine" label={t("whose")} value={mine ? "" : "0"} onChange={(v) => s.set({ mine: v || null })} options={[{ value: "0", label: t("allJobs") }]} allLabel={t("myJobs")} />
          ) : null}
        </ListToolbar>
        {q.isLoading ? (
          <LoadingState rows={2} />
        ) : items.length ? (
          <Table data-testid="xp-jobs">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("dataset")}</TH>
                <TH>{t("rows")}</TH>
                <TH>{t("purpose")}</TH>
                <TH>{t("status")}</TH>
                <TH>{t("expires")}</TH>
                <TH>{t("by")}</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {items.map((j) => (
                <TR key={j.id} data-testid="xp-job" data-dataset={j.dataset} data-status={j.status}>
                  <TD label={t("no")}>
                    <Code>{j.export_no}</Code>
                    <span className="block text-xs text-muted-foreground">
                      {te(`xpFormat.${j.format}`)} · {dateTime(j.created_at)}
                    </span>
                  </TD>
                  <TD label={t("dataset")}>
                    {dsLabel(j.dataset) && dsLabel(j.dataset) !== j.dataset ? <span className="block">{dsLabel(j.dataset)}</span> : null}
                    <bdi className="ltr font-mono text-xs text-muted-foreground">{j.dataset}</bdi>
                    {j.contains_sensitive ? (
                      <span className="flex items-center gap-1 text-xs font-medium text-danger">
                        <ShieldAlert aria-hidden className="size-3.5" />
                        {te("xpPdpl.sensitive")}
                      </span>
                    ) : j.contains_personal ? (
                      <span className="flex items-center gap-1 text-xs font-medium text-warning">
                        <UserRound aria-hidden className="size-3.5" />
                        {te("xpPdpl.personal")}
                      </span>
                    ) : null}
                    {j.notes.length ? <span className="block text-xs text-muted-foreground">{j.notes.join(" · ")}</span> : null}
                  </TD>
                  <TD label={t("rows")} className="tabular-nums">
                    {j.row_count === null || j.row_count === undefined ? "—" : show(String(j.row_count))}
                  </TD>
                  <TD label={t("purpose")}>{j.purpose ? te(`xpPurpose.${j.purpose}`) : "—"}</TD>
                  <TD label={t("status")}>
                    <ScBadge group="xpJobStatus" status={j.status} />
                  </TD>
                  <TD label={t("expires")}>{j.expires_at ? dateTime(j.expires_at) : "—"}</TD>
                  <TD label={t("by")}>{j.requested_by ? name(j.requested_by.full_name_en, j.requested_by.full_name_ar) : "—"}</TD>
                  <TD label="">{j.requested_by?.id === caps.me?.id && j.status === "ready" ? <JobDownload job={j} /> : null}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        ) : (
          <EmptyState message={t("noJobs")} />
        )}
      </CardContent>
    </Card>
  );
}

function Subscriptions() {
  const t = useTranslations("xp");
  const te = useTranslations("enums");
  const refresh = useScRefresh();
  const { dateTime } = useFormatters();
  const q = useExportSubscriptions();
  const [error, setError] = useState<unknown>(null);
  const items = q.data?.items ?? [];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t("subscriptions")}</CardTitle>
      </CardHeader>
      <CardContent>
        <MutationError error={error} />
        {items.length ? (
          <ul className="flex flex-col divide-y rounded-md border" data-testid="xp-subscriptions">
            {items.map((x) => (
              <li key={x.id} className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm" data-testid="xp-subscription" data-dataset={x.dataset}>
                <bdi className="ltr font-mono text-xs">{x.dataset}</bdi>
                <span>
                  {te(`xpFrequency.${x.frequency}`)} · {te(`xpFormat.${x.format}`)}
                </span>
                <span className="flex-1 text-xs text-muted-foreground">{x.last_run_at ? t("lastRun", { at: dateTime(x.last_run_at) }) : t("notRunYet")}</span>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={t("unsubscribe")}
                  onClick={async () => {
                    setError(null);
                    try {
                      await unwrap(api.DELETE("/api/v1/export-subscriptions/{subscription_id}", { params: { path: { subscription_id: x.id } } }));
                      await refresh();
                    } catch (e) {
                      setError(e);
                    }
                  }}
                  data-testid="xp-unsubscribe"
                >
                  <Trash2 aria-hidden />
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState message={t("noSubscriptions")} />
        )}
      </CardContent>
    </Card>
  );
}

/* ═════════════ entry points from the earlier registers (EX-1) ═════════════ */

/** Quick CSV / XLSX (the de-identified default) plus a link to the full export screen, for a registry dataset. Hidden without the dataset's export right. */
export function RegistryExport({ dataset, projectId }: { dataset: S["ExportDataset"]; projectId: string | null }) {
  const t = useTranslations("xp");
  const me = useMeData();
  const q = useExportDatasets();
  const ds = q.data?.items.find((d) => d.dataset_code === dataset);
  if (!ds || !can(me, ds.export_capability as Capability, projectId)) return null;
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="registry-export">
      <ExportButtons dataset={dataset} params={{ project_id: ds.project_required ? projectId : null }} />
      <Link href={`/exports?dataset=${dataset}`} className="inline-flex min-h-touch items-center gap-1.5 rounded-md px-2 text-sm font-medium text-primary hover:bg-accent hover:underline" data-testid="registry-export-more">
        <Settings2 aria-hidden className="size-4" />
        {t("moreOptions")}
      </Link>
    </div>
  );
}

/** Dashboard PDF print (D-10, EX-11): the server renders the KPI tiles with the current filters. */
export function DashboardPrintButton({ query }: { query: KpiQuery }) {
  const t = useTranslations("xp");
  const td = useTranslations("scDesign");
  const msg = useErrorMessage();
  const [busy, setBusy] = useState(false);
  async function run() {
    setBusy(true);
    try {
      const qs = toQueryString({
        project_id: query.project_id ?? undefined,
        all_projects: query.all_projects ? "true" : undefined,
        site_id: query.site_id ?? undefined,
        zone_id: query.zone_id ?? undefined,
        zone_type: query.zone_type ?? undefined,
        engagement_id: query.engagement_id ?? undefined,
        include_subcontractors: query.include_subcontractors === false ? "false" : undefined,
        tier: query.tier?.map(String) ?? undefined,
        period: query.period ?? undefined,
        anchor: query.anchor ?? undefined,
        start: query.start ?? undefined,
        end: query.end ?? undefined,
        as_of: query.as_of ?? undefined,
        compare: query.compare ?? undefined,
      });
      await downloadFile(`/api/v1/dashboard-print${qs}`, "dashboard.pdf");
      toast.success(t("printed"));
    } catch (e) {
      toast.error(`${t("printFailed")}: ${msg(e)}`);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Button variant="outline" onClick={() => void run()} disabled={busy} aria-busy={busy} data-testid="dashboard-print">
      {busy ? <Loader2 aria-hidden className="animate-spin" /> : <Printer aria-hidden />}
      {busy ? td("printing") : t("printPdf")}
    </Button>
  );
}
