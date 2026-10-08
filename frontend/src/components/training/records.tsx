"use client";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, FileImage, IdCard, Pencil, Plus, Printer, RefreshCcw, ShieldCheck } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiWarnings } from "@/components/common/api-warnings";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { ExportButtons } from "@/components/common/export-buttons";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { AccessPrintHeader, BiLabel, Code, DaysLeft, DeploymentPicker, QrImage, StepDialog, WorkerLabel } from "@/components/access/common";
import { Tick, UploadField, UserName } from "@/components/cert/common";
import { DateTimeInput } from "@/components/ptw/common";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { tk, useTrainingCertificate, useTrainingRecord, useTrainingRecords, useTrainingRefresh, useTrainingVerificationLog, useTrainingVerifications } from "@/lib/api/training";
import { WORKER_ID_TYPES } from "@/lib/access-enums";
import { SCAN_REASONS } from "@/lib/cert-enums";
import { RECORD_SOURCES, RECORD_STATUSES, TRAINING_STATUS_REASONS, TRAINING_VERIFICATION_METHODS, TRAINING_VERIFICATION_OUTCOMES, VERIFICATION_DIFFERENCES, VERIFICATION_STATUSES } from "@/lib/train-enums";
import { useDebounced } from "@/lib/use-debounced";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { CourseLabel, DateFilter, ProviderLabel, ProviderSelect, RecordStatusBadge, TrainingRecordsSubNav, TrainingStatePanel, TrainingValidityView, TrainingVerificationBadge, useCodeText, useCourseCatalogue, useTrainingCaps, isOn } from "./common";

type S = Schemas;
const PAGE_SIZE = 50;

/* ───────────── list ───────────── */

export function RecordListPage() {
  return <ProjectGate>{(p) => <RecordList project={p} />}</ProjectGate>;
}

function RecordList({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("training.records");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const caps = useTrainingCaps(project.id);
  const opts = useProjectOptions(project.id);
  const { courses } = useCourseCatalogue(project.id);
  const { date } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as S["TrainingRecordStatus"][];
  const verif = s.getAll("verification_status") as S["VerificationStatus"][];
  const source = s.getAll("source") as S["TrainingRecordSource"][];
  const codes = s.getAll("course_code");
  const q = useTrainingRecords(project.id, {
    q: s.get("q") || null,
    course_code: codes.length ? codes : null,
    status: status.length ? status : null,
    verification_status: verif.length ? verif : null,
    source: source.length ? source : null,
    engagement_id: s.get("engagement_id") ? [s.get("engagement_id") as string] : null,
    include_subcontractors: true,
    worker_id: s.get("worker_id") || null,
    session_id: s.get("session_id") || null,
    in_force: s.get("in_force") === "1" ? true : s.get("in_force") === "0" ? false : null,
    expiring_days: s.getInt("expiring_days", 0) || null,
    awaiting_review: isOn(s.get("awaiting_review")) ? true : null,
    verification_overdue: isOn(s.get("verification_overdue")) ? true : null,
    historic: isOn(s.get("historic")) ? true : null,
    page,
    page_size: PAGE_SIZE,
  });
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.recordSubmit ? (
            <Button asChild data-testid="new-record">
              <Link href="/training-records/new">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <TrainingRecordsSubNav />
      <ListToolbar actions={caps.export ? <ExportButtons dataset="training_records" params={{ project_id: project.id }} /> : null}>
        <SearchFilter id="tr-q" value={s.get("q") ?? ""} onChange={(v) => s.set({ q: v })} placeholder={t("searchHint")} />
        <MultiSelect id="tr-course" label={t("course")} options={courses.map((c) => ({ value: c.code, label: c.code }))} value={codes} onChange={(v) => s.set({ course_code: v })} />
        <MultiSelect id="tr-status" label={tc("status")} options={RECORD_STATUSES.map((x) => ({ value: x, label: te(`recordStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <MultiSelect id="tr-verif" label={t("verification")} options={VERIFICATION_STATUSES.map((x) => ({ value: x, label: te(`verificationStatus.${x}`) }))} value={verif} onChange={(v) => s.set({ verification_status: v })} />
        <SelectFilter id="tr-eng" label={tc("contractor")} value={s.get("engagement_id") ?? ""} onChange={(v) => s.set({ engagement_id: v })} options={opts.engagements.map((x) => ({ value: x.value, label: x.label }))} />
        <MultiSelect id="tr-source" label={t("source")} options={RECORD_SOURCES.map((x) => ({ value: x, label: te(`recordSource.${x}`) }))} value={source} onChange={(v) => s.set({ source: v })} />
        <SelectFilter
          id="tr-inforce"
          label={t("inForce")}
          value={s.get("in_force") ?? ""}
          onChange={(v) => s.set({ in_force: v })}
          options={[
            { value: "1", label: tc("yes") },
            { value: "0", label: tc("no") },
          ]}
        />
        <SelectFilter
          id="tr-exp"
          label={t("expiring")}
          value={s.get("expiring_days") ?? ""}
          onChange={(v) => s.set({ expiring_days: v })}
          options={[
            { value: "30", label: t("withinDays", { n: 30 }) },
            { value: "60", label: t("withinDays", { n: 60 }) },
          ]}
        />
        <SelectFilter id="tr-awaiting" label={t("awaitingReview")} value={isOn(s.get("awaiting_review")) ? "1" : ""} onChange={(v) => s.set({ awaiting_review: v })} options={[{ value: "1", label: tc("yes") }]} />
        <SelectFilter id="tr-overdue" label={t("verificationOverdue")} value={isOn(s.get("verification_overdue")) ? "1" : ""} onChange={(v) => s.set({ verification_overdue: v })} options={[{ value: "1", label: tc("yes") }]} />
        <SelectFilter id="tr-historic" label={t("historic")} value={isOn(s.get("historic")) ? "1" : ""} onChange={(v) => s.set({ historic: v })} options={[{ value: "1", label: tc("yes") }]} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="records-table">
            <THead>
              <TR>
                <TH>{t("holder")}</TH>
                <TH>{t("course")}</TH>
                <TH>{t("recordNo")}</TH>
                <TH>{t("validUntil")}</TH>
                <TH>{t("verification")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((r) => (
                <TR key={r.id} data-testid="record-row" data-record-no={r.record_no} data-worker={r.worker.worker_no} data-course={r.course_code}>
                  <TD label={t("holder")}>
                    <WorkerLabel w={r.worker} />
                    {r.engagement ? <span className="block text-xs text-muted-foreground">{r.engagement.short_code}</span> : null}
                  </TD>
                  <TD label={t("course")}>
                    <Code className="font-medium">{r.course_code}</Code>
                    <span className="block text-xs text-muted-foreground">{locale === "ar" ? r.course_name_ar : r.course_name_en}</span>
                  </TD>
                  <TD label={t("recordNo")}>
                    <Link href={`/training-records/${r.id}`} className="font-medium text-primary hover:underline">
                      <Code>{r.record_no}</Code>
                    </Link>
                    <span className="block text-xs text-muted-foreground">
                      <Code>{r.provider_code}</Code> · <Code>{r.certificate_no}</Code>
                    </span>
                  </TD>
                  <TD label={t("validUntil")}>
                    {r.valid_until ? <span className="ltr">{date(r.valid_until)}</span> : t("noExpiry")} {r.in_force ? <DaysLeft days={r.days_left} /> : null}
                    <span className="mt-0.5 block">
                      {r.in_force ? <Badge tone={r.expiring ? "warning" : "success"}>{t("inForce")}</Badge> : r.historic ? <Badge tone="neutral">{t("historic")}</Badge> : null}
                    </span>
                  </TD>
                  <TD label={t("verification")}>
                    <TrainingVerificationBadge status={r.verification_status} />
                    <span className="block text-xs text-muted-foreground">{te(`recordSource.${r.source}`)}</span>
                  </TD>
                  <TD label={tc("status")}>
                    <RecordStatusBadge status={r.status} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState />
      )}
    </div>
  );
}

/* ───────────── create / edit an external certificate ───────────── */

export function RecordNewPage() {
  return <ProjectGate>{(p) => <RecordForm project={p} />}</ProjectGate>;
}

function RecordForm({ project, rec }: { project: S["ProjectRead"]; rec?: S["TrainingRecordRead"] }) {
  const t = useTranslations("training.records");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const router = useRouter();
  const refresh = useTrainingRefresh();
  const caps = useTrainingCaps(project.id);
  const codeText = useCodeText();
  const { get } = useCourseCatalogue(project.id, { active: true });
  const [dep, setDep] = useState<S["DeploymentRead"] | null>(null);
  const [idOnCard, setIdOnCard] = useState<S["IdOnCard"]>({ shown: true, id_type: "iqama", id_number: "" });
  const [course, setCourse] = useState(rec?.course.code ?? "");
  const [provider, setProvider] = useState(rec?.provider.id ?? "");
  const [certNo, setCertNo] = useState(rec?.certificate_no ?? "");
  const [completed, setCompleted] = useState(rec?.completed_on ?? "");
  const [expiry, setExpiry] = useState(rec?.printed_expiry ?? "");
  const [theory, setTheory] = useState(rec?.theory_score_pct ?? "");
  const [practical, setPractical] = useState<S["PracticalResult"] | "">(rec?.practical_result ?? "");
  const [hours, setHours] = useState(rec?.hours ?? "");
  const [sponsored, setSponsored] = useState(rec?.project_sponsored ?? false);
  const [nameAs, setNameAs] = useState(rec?.name_as_printed ?? "");
  const [url, setUrl] = useState(rec?.provider_verification_url ?? "");
  const [historic, setHistoric] = useState(rec?.historic ?? false);
  const [prereq, setPrereq] = useState(rec?.prerequisite_evidenced_on_certificate ?? false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const info = get(course);
  const workerId = rec?.worker.id ?? dep?.worker_id ?? "";
  const base = {
    course_code: course,
    provider_id: provider,
    certificate_no: certNo.trim(),
    completed_on: completed,
    printed_expiry: expiry || null,
    theory_score_pct: theory === "" ? null : theory,
    practical_result: practical || null,
    hours: hours === "" ? null : hours,
    project_sponsored: sponsored,
    sponsoring_project_id: sponsored ? project.id : null,
    name_as_printed: nameAs.trim(),
    provider_verification_url: url.trim() || null,
    prerequisite_evidenced_on_certificate: prereq,
  };
  const ready = Boolean(workerId && course && provider && certNo.trim() && completed && nameAs.trim() && (!sponsored || hours !== ""));
  const idValid = !idOnCard.shown || Boolean(idOnCard.id_number?.trim()) || Boolean(rec);
  const previewKey = useDebounced(JSON.stringify({ ...base, worker_id: workerId, project_id: project.id }), 600);
  const preview = useQuery({
    queryKey: ["training-record-preview", project.id, previewKey],
    queryFn: () => unwrap(api.POST("/api/v1/projects/{project_id}/training-records/preview", { params: { path: { project_id: project.id } }, body: JSON.parse(previewKey) as S["TrainingRecordPreviewRequest"] })),
    enabled: ready,
    retry: false,
    placeholderData: keepPreviousData,
  });
  async function save() {
    setBusy(true);
    setError(null);
    try {
      if (rec) {
        const r = await unwrap(api.PATCH("/api/v1/training-records/{record_id}", { params: { path: { record_id: rec.id } }, body: { ...base, id_on_card: idOnCard.id_number ? idOnCard : null, reason: reason.trim() || null } }));
        qc.setQueryData(tk.record(rec.id, ""), r);
        await refresh();
        toast.success(tc("saved"));
        router.push(`/training-records/${rec.id}`);
      } else {
        const r = await unwrap(
          api.POST("/api/v1/projects/{project_id}/training-records", {
            params: { path: { project_id: project.id } },
            body: { ...base, worker_id: workerId, project_id: project.id, historic, id_on_card: { ...idOnCard, id_number: idOnCard.shown ? idOnCard.id_number?.trim() || null : null } },
          }),
        );
        await refresh();
        toast.success(t("created", { no: r.record_no }));
        router.push(`/training-records/${r.id}`);
      }
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const pv = preview.data;
  const lockedAfterAccept = rec && rec.status !== "draft";
  return (
    <div className="flex flex-col gap-5">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/training-records" }, { label: rec ? rec.record_no : t("new") }]} />
        <PageHeader title={rec ? t("edit") : t("new")} description={t("newHint")} />
      </div>
      <FormSection title={t("holderSection")}>
        {rec ? (
          <FieldItem label={t("holder")}>
            <WorkerLabel w={rec.worker} />
          </FieldItem>
        ) : (
          <div className="sm:col-span-2">
            <DeploymentPicker id="tr-holder" projectId={project.id} value={dep} onChange={setDep} label={t("holder")} required />
          </div>
        )}
        <FormField id="tr-name" label={t("nameAsPrinted")} required hint={t("nameAsPrintedHint")}>
          <Input value={nameAs} onChange={(e) => setNameAs(e.target.value)} data-testid="tr-name-as-printed" />
        </FormField>
        <div className="flex flex-col gap-2 sm:col-span-2" data-testid="id-on-card">
          <Tick id="tr-id-shown" label={t("idShownOnCard")} checked={Boolean(idOnCard.shown)} onChange={(v) => setIdOnCard({ ...idOnCard, shown: v })} />
          {idOnCard.shown ? (
            <div className="grid gap-2 sm:grid-cols-[10rem_1fr]">
              <FormField id="tr-id-type" label={t("idType")}>
                <Select value={idOnCard.id_type ?? "iqama"} onChange={(e) => setIdOnCard({ ...idOnCard, id_type: e.target.value as S["WorkerIdType"] })}>
                  {WORKER_ID_TYPES.map((x) => (
                    <option key={x} value={x}>
                      {te(`workerIdType.${x}`)}
                    </option>
                  ))}
                </Select>
              </FormField>
              <FormField id="tr-id-num" label={t("idOnCard")} required={!rec} hint={t("idOnCardHint")}>
                <Input value={idOnCard.id_number ?? ""} onChange={(e) => setIdOnCard({ ...idOnCard, id_number: e.target.value })} className="ltr font-mono" autoComplete="off" data-testid="tr-id-number" />
              </FormField>
            </div>
          ) : null}
        </div>
      </FormSection>
      <FormSection title={t("certSection")}>
        <FormField id="tr-course" label={t("course")} required>
          <CourseSelectInline value={course} onChange={setCourse} projectId={project.id} />
        </FormField>
        <ProviderSelect id="tr-provider" label={t("provider")} value={provider} onChange={(v) => setProvider(v)} courseCode={course} required />
        <FormField id="tr-cert-no" label={t("certificateNo")} required>
          <Input value={certNo} onChange={(e) => setCertNo(e.target.value)} className="ltr" data-testid="tr-cert-no" />
        </FormField>
        <FormField id="tr-completed" label={t("completedOn")} required>
          <Input type="date" className="ltr" value={completed} onChange={(e) => setCompleted(e.target.value)} data-testid="tr-completed" />
        </FormField>
        <FormField id="tr-expiry" label={t("printedExpiry")} hint={info?.validity_months ? t("printedExpiryHint", { months: info.validity_months }) : undefined}>
          <Input type="date" className="ltr" value={expiry} onChange={(e) => setExpiry(e.target.value)} data-testid="tr-expiry" />
        </FormField>
        {info?.theory_required ? (
          <FormField id="tr-theory" label={t("theoryScore")}>
            <Input type="number" step="0.01" min={0} max={100} className="ltr" value={theory} onChange={(e) => setTheory(e.target.value)} data-testid="tr-theory" />
          </FormField>
        ) : null}
        {info?.practical_required ? (
          <FormField id="tr-practical" label={t("practical")}>
            <Select value={practical} onChange={(e) => setPractical(e.target.value as S["PracticalResult"] | "")}>
              <option value="">—</option>
              <option value="pass">{t("pass")}</option>
              <option value="fail">{t("fail")}</option>
            </Select>
          </FormField>
        ) : null}
        <FormField id="tr-url" label={t("verificationUrl")} hint={t("verificationUrlHint")}>
          <Input type="url" value={url} onChange={(e) => setUrl(e.target.value)} className="ltr" data-testid="tr-url" />
        </FormField>
        <div className="flex flex-col gap-2 sm:col-span-2">
          <Tick id="tr-sponsored" label={t("projectSponsored")} checked={sponsored} onChange={setSponsored} />
          {sponsored ? (
            <FormField id="tr-hours" label={t("hours")} required hint={t("hoursHint")}>
              <Input type="number" step="0.25" min={0} className="ltr" value={hours} onChange={(e) => setHours(e.target.value)} data-testid="tr-hours" />
            </FormField>
          ) : null}
          {caps.recordReview && !rec ? <Tick id="tr-historic" label={t("historicLabel")} checked={historic} onChange={setHistoric} /> : null}
          {caps.recordReview && info?.prerequisite_codes.length ? <Tick id="tr-prereq" label={t("prereqEvidenced", { codes: info.prerequisite_codes.join(", ") })} checked={prereq} onChange={setPrereq} /> : null}
        </div>
        {lockedAfterAccept ? (
          <FormField id="tr-edit-reason" label={tc("reason")} required hint={t("editReasonHint")}>
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} data-testid="tr-edit-reason" />
          </FormField>
        ) : null}
      </FormSection>
      <Card data-testid="record-preview">
        <CardHeader>
          <CardTitle className="text-base">{t("preview")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          {!ready ? (
            <p className="text-muted-foreground">{t("previewNeeds")}</p>
          ) : preview.isError ? (
            <ErrorState error={preview.error} onRetry={() => preview.refetch()} />
          ) : pv ? (
            <>
              <TrainingValidityView v={pv.validity} projectId={project.id} />
              <span className="flex flex-wrap items-center gap-2">
                <span data-testid="preview-name-match" data-match={pv.name_match}>
                  <Badge tone={pv.name_match === "exact" ? "success" : pv.name_match === "partial" ? "warning" : "danger"}>{t("nameMatch", { m: te(`nameMatch.${pv.name_match}`) })}</Badge>
                </span>
                <span data-testid="preview-provider" data-acceptable={pv.provider_acceptable ? "yes" : "no"}>
                  {pv.provider_acceptable ? <Badge tone="success">{t("providerAcceptable")}</Badge> : <Badge tone="danger">{t("providerNotAcceptable")}</Badge>}
                </span>
                {pv.provider_reason ? <span className="text-xs text-destructive">{te.has(`providerUnacceptable.${pv.provider_reason as S["ProviderUnacceptableReason"]}`) ? te(`providerUnacceptable.${pv.provider_reason as S["ProviderUnacceptableReason"]}`) : codeText(pv.provider_reason)}</span> : null}
              </span>
              <IssueList errors={pv.errors} warnings={pv.warnings} />
            </>
          ) : (
            <LoadingState rows={1} />
          )}
        </CardContent>
      </Card>
      <MutationError error={error} />
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => void save()} disabled={!ready || !idValid || busy || (Boolean(lockedAfterAccept) && reason.trim().length < 5)} data-testid="save-record">
          {busy ? tc("saving") : rec ? tc("save") : t("saveDraft")}
        </Button>
        <Button variant="outline" asChild>
          <Link href={rec ? `/training-records/${rec.id}` : "/training-records"}>{tc("cancel")}</Link>
        </Button>
      </div>
      {!rec ? <p className="text-xs text-muted-foreground">{t("scanAfterSave")}</p> : null}
    </div>
  );
}

function CourseSelectInline({ value, onChange, projectId }: { value: string; onChange: (v: string) => void; projectId: string }) {
  const tc = useTranslations("common");
  const locale = useLocale();
  const { courses } = useCourseCatalogue(projectId, { active: true });
  return (
    <Select id="tr-course" value={value} onChange={(e) => onChange(e.target.value)} data-testid="tr-course">
      <option value="">{tc("select")}</option>
      {courses
        .filter((c) => c.category !== "induction_link")
        .map((c) => (
          <option key={c.code} value={c.code}>
            {c.code} — {locale === "ar" ? c.name_ar : c.name_en}
          </option>
        ))}
    </Select>
  );
}

function IssueList({ errors, warnings }: { errors: S["ApiWarning"][]; warnings: S["ApiWarning"][] }) {
  const locale = useLocale();
  const msg = (w: S["ApiWarning"]) => (locale === "ar" && w.message_ar ? w.message_ar : w.message);
  if (!errors.length && !warnings.length) return null;
  return (
    <ul className="flex flex-col gap-1" data-testid="preview-issues">
      {errors.map((w, i) => (
        <li key={`e${i}`} className="flex gap-2 text-destructive" data-code={w.code} data-kind="error">
          <Badge tone="danger">{w.code}</Badge>
          {msg(w)}
        </li>
      ))}
      {warnings.map((w, i) => (
        <li key={`w${i}`} className="flex gap-2" data-code={w.code} data-kind="warning">
          <Badge tone="warning">{w.code}</Badge>
          {msg(w)}
        </li>
      ))}
    </ul>
  );
}

/* ───────────── detail ───────────── */

export function RecordDetail({ id }: { id: string }) {
  const s = useSearchState();
  const q = useTrainingRecord(id, "");
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const pid = q.data.project_id;
  if (!pid) return <RecordView project={null} r={q.data} />;
  return <ProjectById id={pid}>{(p) => (s.get("edit") === "1" ? <RecordForm project={p} rec={q.data} /> : <RecordView project={p} r={q.data} />)}</ProjectById>;
}

const REASON_MIN: Partial<Record<S["TrainingRecordAction"], number>> = { return: 10, reject: 5, suspend: 20, reinstate: 5, revoke: 20 };
const DESTRUCTIVE: S["TrainingRecordAction"][] = ["reject", "suspend", "revoke"];

function RecordView({ project, r }: { project: S["ProjectRead"] | null; r: S["TrainingRecordRead"] }) {
  const t = useTranslations("training.records");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const s = useSearchState();
  const qc = useQueryClient();
  const pid = project?.id ?? null;
  const caps = useTrainingCaps(pid);
  const { date, dateTime } = useFormatters(pid);
  const refresh = useTrainingRefresh();
  const verifs = useTrainingVerifications(r.id, { enabled: caps.recordReview || caps.recordView });
  const [action, setAction] = useState<S["TrainingRecordAction"] | null>(null);
  const [reason, setReason] = useState("");
  const [reasonCode, setReasonCode] = useState<S["TrainingStatusReason"] | "">("");
  const [identity, setIdentity] = useState(false);
  const [scan, setScan] = useState(false);
  const [verify, setVerify] = useState(false);
  const [reissue, setReissue] = useState(false);
  const notAccepted = locale === "ar" ? r.not_accepted_message_ar : r.not_accepted_message_en;
  async function setScanId(id: string | null) {
    const x = await unwrap(api.PATCH("/api/v1/training-records/{record_id}", { params: { path: { record_id: r.id } }, body: { scan_attachment_id: id } }));
    qc.setQueryData(tk.record(r.id, ""), x);
    await refresh();
  }
  async function transition(a: S["TrainingRecordAction"]) {
    const x = await unwrap(
      api.POST("/api/v1/training-records/{record_id}/transitions", {
        params: { path: { record_id: r.id } },
        body: { action: a, reason: reason.trim() || null, reason_code: reasonCode || null, identity_confirmed_by_provider: identity },
      }),
    );
    qc.setQueryData(tk.record(r.id, ""), x);
    await refresh();
    toast.success(te(`recordStatus.${x.status}`));
  }
  const editable = (caps.recordSubmit && r.status === "draft") || (caps.manager && r.status === "accepted");
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/training-records" }, { label: r.record_no }]} />
        <PageHeader
          title={`${r.course.code} — ${r.record_no}`}
          description={`${locale === "ar" ? r.course.name_ar : r.course.name_en} · ${te(`recordSource.${r.source}`)}`}
          actions={
            <>
              <RecordStatusBadge status={r.status} />
              <TrainingVerificationBadge status={r.verification_status} />
              {editable ? (
                <Button variant="outline" onClick={() => s.set({ edit: "1" })} data-testid="edit-record">
                  <Pencil aria-hidden />
                  {tc("edit")}
                </Button>
              ) : null}
              {r.allowed_actions.map((a) => (
                <Button key={a} variant={a === "accept" || a === "submit" ? "default" : DESTRUCTIVE.includes(a) ? "destructive-outline" : "outline"} onClick={() => setAction(a)} data-testid={`record-${a}`}>
                  {te(`recordAction.${a}`)}
                </Button>
              ))}
            </>
          }
        />
      </div>
      {notAccepted ? (
        <Alert tone="danger" data-testid="not-accepted">
          {notAccepted}
        </Alert>
      ) : null}
      {(r.prompts ?? []).map((p, i) => (
        <Alert key={i} tone="info" data-testid="record-prompt" data-code={p.code}>
          {locale === "ar" && p.message_ar ? p.message_ar : p.message}
          {/ban/i.test(p.code) ? (
            <Link href={`/workers/${r.worker.id}`} className="ms-2 font-medium underline">
              {t("openWorker")}
            </Link>
          ) : null}
        </Alert>
      ))}
      {r.status === "draft" && !r.has_scan ? <Alert tone="info">{t("scanNeeded")}</Alert> : null}
      <ApiWarnings warnings={r.warnings} />
      {r.status_reason ? (
        <Alert tone={r.status === "suspended" || r.status === "revoked" || r.status === "rejected" ? "danger" : "info"} data-testid="status-reason" data-reason={r.status_reason}>
          {te(`trainingStatusReason.${r.status_reason}`)}
          {r.status_reason_text ? ` — ${r.status_reason_text}` : ""}
        </Alert>
      ) : null}
      <TrainingStatePanel status={r.status} v={r.validity} projectId={pid} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardContent className="pt-5">
            <FieldList>
              <FieldItem label={t("holder")} wide>
                <WorkerLabel w={r.worker} link />
                {r.engagement ? <Code className="ms-2 text-muted-foreground">{r.engagement.short_code}</Code> : null}
              </FieldItem>
              <FieldItem label={t("course")} wide>
                <Link href={`/training-courses/${encodeURIComponent(r.course.code)}`} className="hover:underline">
                  <CourseLabel course={r.course} />
                </Link>
              </FieldItem>
              <FieldItem label={t("provider")} wide>
                <ProviderLabel p={r.provider} />
              </FieldItem>
              {r.session ? (
                <FieldItem label={t("session")}>
                  <Link href={`/training-sessions/${r.session.id}`} className="text-primary hover:underline">
                    <Code>{r.session.session_no}</Code>
                  </Link>
                </FieldItem>
              ) : null}
              <FieldItem label={t("certificateNo")} ltr>
                {r.certificate_no}
              </FieldItem>
              <FieldItem label={t("completedOn")}>{date(r.completed_on)}</FieldItem>
              <FieldItem label={t("printedExpiry")}>{r.printed_expiry ? date(r.printed_expiry) : "—"}</FieldItem>
              <FieldItem label={t("storedValidUntil")}>
                {r.valid_until ? date(r.valid_until) : t("noExpiry")}
                <span className="block text-xs text-muted-foreground">{te(`trainingLimitingFactor.${r.limiting_factor}`)}</span>
              </FieldItem>
              {r.theory_score_pct !== undefined && r.theory_score_pct !== null ? (
                <FieldItem label={t("theoryScore")} ltr>
                  {r.theory_score_pct} %
                </FieldItem>
              ) : null}
              {r.practical_result ? <FieldItem label={t("practical")}>{r.practical_result === "pass" ? t("pass") : t("fail")}</FieldItem> : null}
              <FieldItem label={t("hours")} ltr>
                {r.hours ?? "—"}
                {r.project_sponsored ? <span className="ms-1 text-xs text-muted-foreground">({t("sponsored")})</span> : null}
              </FieldItem>
              {r.name_as_printed ? (
                <FieldItem label={t("nameAsPrinted")}>
                  {r.name_as_printed}{" "}
                  {r.name_match ? (
                    <span data-testid="name-match" data-match={r.name_match}>
                      <Badge tone={r.name_match === "exact" ? "success" : r.name_match === "partial" ? "warning" : "danger"}>{te(`nameMatch.${r.name_match}`)}</Badge>
                    </span>
                  ) : null}
                  {r.identity_confirmed_by_provider ? <Badge tone="info">{t("identityConfirmed")}</Badge> : null}
                </FieldItem>
              ) : null}
              {r.id_match_result ? (
                <FieldItem label={t("idMatch")}>
                  <span data-testid="id-match" data-result={r.id_match_result}>
                    <IdCard aria-hidden className="me-1 inline size-4" />
                    {te(`idMatch.${r.id_match_result}`)}
                  </span>
                </FieldItem>
              ) : null}
              <FieldItem label={t("submitted")}>
                {r.submitted_by ? (
                  <>
                    <UserName u={r.submitted_by} /> · {r.submitted_at ? dateTime(r.submitted_at) : ""}
                  </>
                ) : (
                  "—"
                )}
              </FieldItem>
              <FieldItem label={t("reviewed")}>
                {r.reviewed_by ? (
                  <>
                    <UserName u={r.reviewed_by} /> · {r.reviewed_at ? dateTime(r.reviewed_at) : ""}
                  </>
                ) : (
                  "—"
                )}
              </FieldItem>
              <FieldItem label={t("verificationDue")}>{r.verification_due_on ? date(r.verification_due_on) : "—"}</FieldItem>
              {r.superseded_by_id ? (
                <FieldItem label={te("recordStatus.superseded")} wide>
                  <Link href={`/training-records/${r.superseded_by_id}`} className="text-primary hover:underline">
                    {t("newerRecord")}
                  </Link>
                </FieldItem>
              ) : null}
            </FieldList>
          </CardContent>
        </Card>
        <div className="flex flex-col gap-4">
          {r.has_qr ? <CertificateCard r={r} onReissue={() => setReissue(true)} canReissue={caps.recordReview} /> : null}
          {r.source !== "session" ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <FileImage aria-hidden className="size-4" />
                  {t("scan")}
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2 text-sm">
                {r.has_scan ? (
                  caps.scan ? (
                    <Button size="sm" variant="outline" className="self-start" onClick={() => setScan(true)} data-testid="open-scan">
                      <Eye aria-hidden />
                      {t("openScan")}
                    </Button>
                  ) : (
                    <span className="text-xs text-muted-foreground">{t("scanOnFile")}</span>
                  )
                ) : (
                  <span className="text-xs text-muted-foreground">{t("noScan")}</span>
                )}
                {caps.recordSubmit && r.status === "draft" ? (
                  <UploadField id="tr-scan" label={t("uploadScan")} ownerType="training_record_scan" ownerId={r.id} accept="image/jpeg,image/png,application/pdf" value={null} onChange={(v) => void setScanId(v)} hint={t("scanHint")} />
                ) : null}
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
      {r.source !== "session" ? (
        <Card>
          <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
            <CardTitle className="text-base">{t("verifications")}</CardTitle>
            {caps.recordReview && (r.status === "submitted" || r.status === "accepted") ? (
              <Button variant="outline" onClick={() => setVerify(true)} data-testid="record-verification">
                <ShieldCheck aria-hidden />
                {t("recordVerification")}
              </Button>
            ) : null}
          </CardHeader>
          <CardContent>
            <VerificationTable items={verifs.data?.items ?? []} projectId={pid} loading={verifs.isLoading} error={verifs.error} onRetry={() => void verifs.refetch()} />
          </CardContent>
        </Card>
      ) : null}
      {/* P5-4: status reasons are for HSE staff; a contractor rep sees only "not accepted", so the change history is not shown to him. */}
      {caps.recordReview || caps.manager ? <HistoryPanel entityType="training_record" entityId={r.id} projectId={pid ?? undefined} /> : null}
      {scan ? <ScanDialog id={r.id} onClose={() => setScan(false)} /> : null}
      {verify ? <VerifyDialog r={r} onClose={() => setVerify(false)} /> : null}
      {reissue ? <ReissueDialog r={r} onClose={() => setReissue(false)} /> : null}
      {action ? (
        <StepDialog
          title={te(`recordAction.${action}`)}
          description={action === "accept" ? t("acceptHint") : DESTRUCTIVE.includes(action) ? t("hardStopHint") : action === "submit" ? t("submitHint") : undefined}
          confirmLabel={te(`recordAction.${action}`)}
          destructive={DESTRUCTIVE.includes(action)}
          disabled={reason.trim().length < (REASON_MIN[action] ?? 0)}
          onClose={() => {
            setAction(null);
            setReason("");
            setReasonCode("");
          }}
          onConfirm={() => transition(action)}
          testId="record-confirm"
        >
          {action === "accept" && r.name_match && r.name_match !== "exact" ? <Tick id="tr-identity" label={t("identityTick")} checked={identity} onChange={setIdentity} /> : null}
          {action === "suspend" || action === "revoke" || action === "reject" ? (
            <FormField id="tr-reason-code" label={t("reasonCode")}>
              <Select value={reasonCode} onChange={(e) => setReasonCode(e.target.value as S["TrainingStatusReason"])} data-testid="tr-reason-code">
                <option value="">—</option>
                {TRAINING_STATUS_REASONS.filter((x) => ["document_review", "verification_failed", "hse_suspension", "hse_revocation", "other"].includes(x)).map((x) => (
                  <option key={x} value={x}>
                    {te(`trainingStatusReason.${x}`)}
                  </option>
                ))}
              </Select>
            </FormField>
          ) : null}
          {REASON_MIN[action] ? (
            <FormField id="tr-reason" label={tc("reason")} required hint={t("reasonMin", { n: REASON_MIN[action] ?? 0 })}>
              <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="tr-reason" />
            </FormField>
          ) : null}
        </StepDialog>
      ) : null}
    </div>
  );
}

function CertificateCard({ r, canReissue, onReissue }: { r: S["TrainingRecordRead"]; canReissue: boolean; onReissue: () => void }) {
  const t = useTranslations("training.records");
  return (
    <Card data-testid="tr-certificate">
      <CardHeader>
        <CardTitle className="text-base">{t("certificate")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2 text-sm">
        <p className="text-muted-foreground">{t("certificateHint")}</p>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" asChild data-testid="print-certificate">
            <Link href={`/training-records/${r.id}/certificate`}>
              <Printer aria-hidden />
              {t("printCertificate")}
            </Link>
          </Button>
          {canReissue ? (
            <Button size="sm" variant="outline" onClick={onReissue} data-testid="reissue-certificate">
              <RefreshCcw aria-hidden />
              {t("reissue")}
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function ReissueDialog({ r, onClose }: { r: S["TrainingRecordRead"]; onClose: () => void }) {
  const t = useTranslations("training.records");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  return (
    <StepDialog
      title={t("reissueTitle")}
      description={t("reissueHint")}
      confirmLabel={t("reissue")}
      disabled={reason.trim().length < 5}
      onClose={onClose}
      onConfirm={async () => {
        const c = await unwrap(api.POST("/api/v1/training-records/{record_id}/certificate/reissue", { params: { path: { record_id: r.id } }, body: { reason: reason.trim() } }));
        qc.setQueryData(tk.certificate(r.id), c);
        toast.success(t("reissued"));
      }}
      testId="reissue-confirm"
    >
      <FormField id="tr-reissue-reason" label={tc("reason")} required>
        <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} data-testid="tr-reissue-reason" />
      </FormField>
    </StepDialog>
  );
}

/** P5-3: opening a scan needs a reason, is audited and the signed URL lives ≤ 5 min. */
function ScanDialog({ id, onClose }: { id: string; onClose: () => void }) {
  const t = useTranslations("training.records");
  const te = useTranslations("enums");
  const [reason, setReason] = useState<S["ScanReason"]>("verification");
  const [text, setText] = useState("");
  async function open() {
    const r = await unwrap(api.POST("/api/v1/training-records/{record_id}/scan-url", { params: { path: { record_id: id } }, body: { reason, reason_text: text.trim() || null } }));
    window.open(r.url, "_blank", "noopener");
  }
  return (
    <StepDialog title={t("openScanTitle")} description={t("openScanHint")} confirmLabel={t("openScan")} onConfirm={open} onClose={onClose} disabled={reason === "other" && text.trim().length < 5} testId="scan-confirm">
      <FormField id="tr-scan-reason" label={t("scanReason")} required>
        <Select value={reason} onChange={(e) => setReason(e.target.value as S["ScanReason"])} data-testid="scan-reason">
          {SCAN_REASONS.map((x) => (
            <option key={x} value={x}>
              {te(`scanReason.${x}`)}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="tr-scan-text" label={t("details")} required={reason === "other"}>
        <Input value={text} onChange={(e) => setText(e.target.value)} maxLength={200} data-testid="scan-reason-text" />
      </FormField>
    </StepDialog>
  );
}

/* ───────────── verification ───────────── */

function VerificationTable({ items, projectId, loading, error, onRetry }: { items: S["TrainingVerificationRead"][]; projectId: string | null; loading?: boolean; error?: unknown; onRetry?: () => void }) {
  const t = useTranslations("training.records");
  const te = useTranslations("enums");
  const { dateTime } = useFormatters(projectId);
  if (loading) return <LoadingState rows={2} />;
  if (error) return <ErrorState error={error} onRetry={onRetry} />;
  if (!items.length) return <EmptyState message={t("noVerifications")} />;
  return (
    <Table data-testid="verifications-table">
      <THead>
        <TR>
          <TH>{t("performedAt")}</TH>
          <TH>{t("method")}</TH>
          <TH>{t("channel")}</TH>
          <TH>{t("outcome")}</TH>
          <TH>{t("reference")}</TH>
          <TH>{t("by")}</TH>
          <TH>{t("verification")}</TH>
        </TR>
      </THead>
      <TBody>
        {items.map((v) => (
          <TR key={v.id} data-testid="verification-row" data-outcome={v.outcome ?? ""}>
            <TD label={t("performedAt")}>{dateTime(v.performed_at)}</TD>
            <TD label={t("method")}>
              {te.has(`trainingVerificationMethod.${v.method}`) ? te(`trainingVerificationMethod.${v.method}`) : v.method}
              {!v.counts_as_verification ? <span className="block text-xs text-muted-foreground">{t("doesNotCount")}</span> : null}
            </TD>
            <TD label={t("channel")}>
              <bdi className="ltr text-xs break-all">{v.channel_used}</bdi>
            </TD>
            <TD label={t("outcome")}>
              {v.outcome ? te(`trainingVerificationOutcome.${v.outcome}`) : "—"}
              {v.differences.length ? <span className="block text-xs text-muted-foreground">{v.differences.map((d) => te(`verificationDifference.${d}`)).join(" · ")}</span> : null}
            </TD>
            <TD label={t("reference")}>
              <Code className="text-xs break-all">{v.reference}</Code>
            </TD>
            <TD label={t("by")}>
              <UserName u={v.performed_by} />
            </TD>
            <TD label={t("verification")}>
              <TrainingVerificationBadge status={v.verification_status_after} />
            </TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}

/** VR-2…VR-4: not by the submitter or the holder's employer; channel registered on the provider; evidence unless phone. */
function VerifyDialog({ r, onClose }: { r: S["TrainingRecordRead"]; onClose: () => void }) {
  const t = useTranslations("training.records");
  const te = useTranslations("enums");
  const refresh = useTrainingRefresh();
  const [method, setMethod] = useState<S["TrainingVerificationMethod"]>("provider_portal");
  const [channel, setChannel] = useState(r.provider_verification_url ?? "");
  const [outcome, setOutcome] = useState<S["TrainingVerificationOutcome"]>("confirmed");
  const [diffs, setDiffs] = useState<S["VerificationDifference"][]>([]);
  const [diffText, setDiffText] = useState("");
  const [reference, setReference] = useState("");
  const [at, setAt] = useState("");
  const [evidence, setEvidence] = useState<string | null>(null);
  const phone = method === "provider_phone";
  const valid = channel.trim().length > 2 && (phone ? reference.trim().length >= 20 : reference.trim().length > 1 && Boolean(evidence)) && (outcome !== "details_differ" || diffs.length > 0);
  async function save() {
    const v = await unwrap(
      api.POST("/api/v1/training-records/{record_id}/verifications", {
        params: { path: { record_id: r.id } },
        body: { method, channel_used: channel.trim(), outcome, differences: outcome === "details_differ" ? diffs : [], differences_text: diffText.trim() || null, reference: reference.trim(), evidence_attachment_id: phone ? null : evidence, performed_at: at || null },
      }),
    );
    await refresh();
    toast.success(te(`verificationStatus.${v.verification_status_after}`));
  }
  return (
    <StepDialog title={t("recordVerification")} description={t("verifyHint", { provider: r.provider.provider_code })} confirmLabel={t("recordVerification")} onConfirm={save} onClose={onClose} disabled={!valid} wide testId="verify-confirm">
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="tv-method" label={t("method")} required>
          <Select value={method} onChange={(e) => setMethod(e.target.value as S["TrainingVerificationMethod"])} data-testid="tv-method">
            {TRAINING_VERIFICATION_METHODS.filter((m) => m !== "provider_register_file").map((m) => (
              <option key={m} value={m}>
                {te(`trainingVerificationMethod.${m}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="tv-channel" label={t("channel")} required hint={t("channelHint")}>
          <Input value={channel} onChange={(e) => setChannel(e.target.value)} className="ltr" data-testid="tv-channel" />
        </FormField>
        <FormField id="tv-outcome" label={t("outcome")} required>
          <Select value={outcome} onChange={(e) => setOutcome(e.target.value as S["TrainingVerificationOutcome"])} data-testid="tv-outcome">
            {TRAINING_VERIFICATION_OUTCOMES.map((m) => (
              <option key={m} value={m}>
                {te(`trainingVerificationOutcome.${m}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="tv-ref" label={t("reference")} required hint={phone ? t("referencePhoneHint") : t("referenceHint")}>
          <Input value={reference} onChange={(e) => setReference(e.target.value)} className="ltr" data-testid="tv-reference" />
        </FormField>
      </div>
      {outcome === "details_differ" ? <CheckboxGroup id="tv-diffs" legend={t("differences")} options={VERIFICATION_DIFFERENCES.map((d) => ({ value: d, label: te(`verificationDifference.${d}`) }))} value={diffs} onChange={setDiffs} /> : null}
      {outcome !== "confirmed" ? (
        <FormField id="tv-difftext" label={t("differencesText")}>
          <Textarea value={diffText} onChange={(e) => setDiffText(e.target.value)} maxLength={500} />
        </FormField>
      ) : null}
      {!phone ? <UploadField id="tv-evidence" label={t("evidence")} ownerType="training_verification_evidence" ownerId={r.id} accept="application/pdf,image/png,image/jpeg,message/rfc822,.eml" value={evidence} onChange={(v) => setEvidence(v)} required hint={t("evidenceHint")} /> : null}
      <FormField id="tv-at" label={t("performedAt")} hint={t("performedAtHint")}>
        <DateTimeInput id="tv-at" value={at} onChange={setAt} />
      </FormField>
    </StepDialog>
  );
}

/* ───────────── verification log ───────────── */

export function VerificationLogPage() {
  return <ProjectGate>{(p) => <VerificationLog project={p} />}</ProjectGate>;
}

function VerificationLog({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("training.records");
  const caps = useTrainingCaps(project.id);
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const methods = s.getAll("method") as S["TrainingVerificationMethod"][];
  const q = useTrainingVerificationLog(project.id, {
    method: methods.length ? methods : null,
    failed_only: isOn(s.get("failed_only")),
    date_from: s.get("from") || null,
    date_to: s.get("to") || null,
    page,
    page_size: PAGE_SIZE,
  });
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("logTitle")} description={t("logSubtitle")} />
      <TrainingRecordsSubNav />
      <ListToolbar actions={caps.export ? <ExportButtons dataset="training_verifications" params={{ project_id: project.id }} /> : null}>
        <MultiSelect id="vl-method" label={t("method")} options={TRAINING_VERIFICATION_METHODS.map((x) => ({ value: x, label: te(`trainingVerificationMethod.${x}`) }))} value={methods} onChange={(v) => s.set({ method: v })} />
        <SelectFilter id="vl-failed" label={t("failedOnly")} value={isOn(s.get("failed_only")) ? "1" : ""} onChange={(v) => s.set({ failed_only: v })} options={[{ value: "1", label: tc("yes") }]} />
        <DateFilter id="vl-from" label={t("from")} value={s.get("from") ?? ""} onChange={(v) => s.set({ from: v })} />
        <DateFilter id="vl-to" label={t("to")} value={s.get("to") ?? ""} onChange={(v) => s.set({ to: v })} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="verification-log">
            <THead>
              <TR>
                <TH>{t("performedAt")}</TH>
                <TH>{t("recordNo")}</TH>
                <TH>{t("method")}</TH>
                <TH>{t("outcome")}</TH>
                <TH>{t("by")}</TH>
                <TH>{t("verification")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((v) => (
                <TR key={v.id} data-testid="verif-log-row" data-outcome={v.outcome ?? ""}>
                  <TD label={t("performedAt")}>{dateTime(v.performed_at)}</TD>
                  <TD label={t("recordNo")}>
                    <Link href={`/training-records/${v.record_id}`} className="text-primary hover:underline">
                      <Code>{v.record_no}</Code>
                    </Link>
                    <span className="block text-xs text-muted-foreground">
                      <Code>{v.worker_no}</Code> · <Code>{v.course_code}</Code> · <Code>{v.provider_code}</Code>
                    </span>
                  </TD>
                  <TD label={t("method")}>
                    {te.has(`trainingVerificationMethod.${v.method}`) ? te(`trainingVerificationMethod.${v.method}`) : v.method}
                    <bdi className="ltr block text-xs break-all text-muted-foreground">{v.channel_used}</bdi>
                  </TD>
                  <TD label={t("outcome")}>{v.outcome ? te(`trainingVerificationOutcome.${v.outcome}`) : "—"}</TD>
                  <TD label={t("by")}>
                    <UserName u={v.performed_by} />
                  </TD>
                  <TD label={t("verification")}>
                    <TrainingVerificationBadge status={v.verification_status_after} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState />
      )}
    </div>
  );
}

/* ───────────── TR certificate (print) ───────────── */

export function CertificatePrintPage({ id }: { id: string }) {
  const t = useTranslations("training.records");
  const tc = useTranslations("common");
  const q = useTrainingCertificate(id);
  const { date } = useFormatters();
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const c = q.data;
  const rows: [Parameters<typeof BiLabel>[0]["k"], ReactNode][] = [
    ["trWorker", <span key="w">{c.worker_name_en}{c.worker_name_ar ? <span lang="ar" dir="rtl" className="block">{c.worker_name_ar}</span> : null}</span>],
    ["trWorkerNo", <Code key="n">{c.worker_no}</Code>],
    ["trCourse", <span key="c"><Code className="font-semibold">{c.course_code}</Code> {c.course_name_en}<span lang="ar" dir="rtl" className="block">{c.course_name_ar}</span></span>],
    ["trCompleted", <span key="d" className="ltr">{date(c.completed_on)}</span>],
    ["trValidUntil", <span key="v" className="ltr">{c.valid_until ? date(c.valid_until) : "—"}</span>],
    ["trProvider", <span key="p"><Code>{c.provider_code}</Code> {c.provider_name_en}<span lang="ar" dir="rtl" className="block">{c.provider_name_ar}</span></span>],
    ["trTrainers", <span key="t">{c.trainer_names.join(", ") || "—"}</span>],
    ["trSession", <Code key="s">{c.session_no}</Code>],
    ["trCertificateNo", <Code key="cn">{c.certificate_no}</Code>],
  ];
  return (
    <div className="flex flex-col items-center gap-4">
      <div className="flex gap-2 print:hidden">
        <Button onClick={() => window.print()} data-testid="do-print">
          <Printer aria-hidden />
          {tc("print")}
        </Button>
        <Button variant="outline" asChild>
          <Link href={`/training-records/${id}`}>{tc("back")}</Link>
        </Button>
      </div>
      {/* A4 landscape-ish bilingual certificate: no ID number, score or photo (P5-6). */}
      <div className="paper flex w-full max-w-[250mm] flex-col gap-4 rounded-xl border-4 border-double border-black bg-white p-[8mm] text-black" data-testid="certificate-print" dir="ltr">
        <AccessPrintHeader title="trainingCertificate" />
        <div className="grid gap-6 sm:grid-cols-[1fr_auto]">
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            {rows.map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="pt-0.5">
                  <BiLabel k={k} stack className="text-[8pt] text-black/70" />
                </dt>
                <dd className="font-medium">{v}</dd>
              </div>
            ))}
          </dl>
          <div className="flex flex-col items-center gap-1">
            <QrImage payload={c.qr_payload} size={170} label={t("qrLabel", { no: c.record_no })} />
            <p className="ltr font-mono text-sm font-bold tracking-wider" data-testid="printed-ref">
              {c.printed_ref}
            </p>
            <BiLabel k="trScanToCheck" stack className="text-center text-[8pt]" />
          </div>
        </div>
        <p className="border-t border-black pt-2 text-[8pt] text-black/70">
          <Code>{c.record_no}</Code> · {date(c.issued_at)}
        </p>
      </div>
    </div>
  );
}
