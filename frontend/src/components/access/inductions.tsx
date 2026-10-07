"use client";
import { useQueryClient } from "@tanstack/react-query";
import { BookOpen, GraduationCap, NotebookPen, Pencil, Plus, Upload, Users } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiWarnings, useWarningToasts } from "@/components/common/api-warnings";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { ExportButtons } from "@/components/common/export-buttons";
import { FieldItem, FieldList, YesNo } from "@/components/common/field-list";
import { CheckboxField, FormField, FormSection } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SearchFilter, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import { Link, useRouter } from "@/i18n/navigation";
import { INDUCTION_DELIVERER_ROLES, INDUCTION_STATUSES, INDUCTION_TYPES, WORKER_LANGUAGES } from "@/lib/access-enums";
import { ak, useDeployment, useInduction, useInductionCourse, useInductionCourses, useInductions, useWorker } from "@/lib/api/access";
import { ApiError, api, unwrap, type Schemas } from "@/lib/api/client";
import { todayInZone, utcToZonedInput, zonedInputToUtc } from "@/lib/datetime";
import { joinList, useLocalizedName } from "@/lib/i18n-helpers";
import { can, canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { Code, DaysLeft, DeploymentPicker, SignaturePad, personName } from "./common";
import { CredentialPanel } from "./credential-actions";
import { WorkerSubNav } from "./workers";

const PAGE_SIZE = 50;
type Course = Schemas["InductionCourseRead"];
type Lang = Schemas["WorkerLanguage"];

function nowInput(): string {
  return utcToZonedInput(new Date().toISOString());
}

function courseLabel(c: Course, locale: string): string {
  return `${c.code} — ${locale === "ar" ? c.name_ar : c.name_en} (v${c.version})`;
}

/* ───────────────────────────── Records list ───────────────────────────── */

export function InductionListPage() {
  return <ProjectGate>{(p) => <InductionList project={p} />}</ProjectGate>;
}

function InductionList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("inductions");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const locale = useLocale();
  const { date, dateTime } = useFormatters(project.id);
  const opts = useProjectOptions(project.id);
  const courses = useInductionCourses(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as Schemas["InductionStatus"][];
  const courseIds = s.getAll("course_id");
  const engs = s.getAll("engagement_id");
  const q: Parameters<typeof useInductions>[1] = {
    course_id: courseIds.length ? courseIds : null,
    status: status.length ? status : null,
    engagement_id: engs.length ? engs : null,
    worker_id: s.get("worker_id") || null,
    induction_type: (s.get("induction_type") as Schemas["InductionType"] | null) || null,
    language_mismatch: s.getBool("language_mismatch") ?? null,
    expiring_within_days: s.getInt("expiring_within_days", 0) || null,
    session_ref: s.get("session_ref") || null,
    delivered_from: s.get("delivered_from") || null,
    delivered_to: s.get("delivered_to") || null,
    page,
    page_size: PAGE_SIZE,
  };
  const query = useInductions(project.id, q);
  const items = query.data?.items ?? [];
  const canRecord = canWrite(me, "induction.record", project.id);
  return (
    <div>
      <PageHeader
        title={t("records")}
        description={t("subtitle")}
        actions={
          canRecord ? (
            <>
              <Button variant="outline" asChild>
                <Link href="/inductions/session" data-testid="new-session">
                  <Users aria-hidden />
                  {t("batchSession")}
                </Link>
              </Button>
              <Button asChild>
                <Link href="/inductions/new" data-testid="new-induction">
                  <Plus aria-hidden />
                  {t("record")}
                </Link>
              </Button>
            </>
          ) : null
        }
      />
      <WorkerSubNav />
      <ListToolbar actions={can(me, "export.access", project.id) ? <ExportButtons dataset="inductions" params={{ project_id: project.id }} /> : null}>
        <SearchFilter id="in-session" value={s.get("session_ref") ?? ""} onChange={(v) => s.set({ session_ref: v })} placeholder={t("sessionRef")} />
        <MultiSelect
          id="in-course"
          label={t("course")}
          options={(courses.data?.items ?? []).map((c) => ({ value: c.id, label: courseLabel(c, locale) }))}
          value={courseIds}
          onChange={(v) => s.set({ course_id: v })}
        />
        <SelectFilter
          id="in-type"
          label={t("fields.induction_type")}
          value={(q.induction_type ?? "") as Schemas["InductionType"] | ""}
          onChange={(v) => s.set({ induction_type: v })}
          options={INDUCTION_TYPES.map((x) => ({ value: x, label: te(`inductionType.${x}`) }))}
        />
        <MultiSelect id="in-status" label={tc("status")} options={INDUCTION_STATUSES.map((x) => ({ value: x, label: te(`inductionStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <MultiSelect id="in-eng" label={tc("contractor")} options={opts.engagements} value={engs} onChange={(v) => s.set({ engagement_id: v })} allLabel={tc("anyContractor")} />
        <SelectFilter
          id="in-mismatch"
          label={t("languageMismatch")}
          value={s.get("language_mismatch") === "true" ? "true" : ""}
          onChange={(v) => s.set({ language_mismatch: v })}
          options={[{ value: "true", label: tc("yes") }]}
        />
      </ListToolbar>
      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length > 0 ? (
        <>
          <Table data-testid="inductions-table">
            <THead>
              <TR>
                <TH>{t("fields.induction_no")}</TH>
                <TH>{t("worker")}</TH>
                <TH>{t("course")}</TH>
                <TH>{t("fields.delivered_at")}</TH>
                <TH>{t("fields.delivery_language")}</TH>
                <TH>{t("fields.test_score_pct")}</TH>
                <TH>{t("fields.valid_until")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((r) => (
                <TR key={r.id} data-testid="induction-row">
                  <TD label={t("fields.induction_no")}>
                    <Link href={`/inductions/${r.id}`} className="ltr font-medium text-primary hover:underline">
                      {r.induction_no}
                    </Link>
                  </TD>
                  <TD label={t("worker")}>
                    <Link href={`/workers/${r.worker.id}`} className="hover:underline">
                      <Code>{r.worker.worker_no}</Code> {personName(r.worker, locale)}
                    </Link>
                    {r.engagement ? <span className="block text-xs text-muted-foreground">{r.engagement.short_code}</span> : null}
                  </TD>
                  <TD label={t("course")}>
                    <Code>{r.course_code}</Code> <span className="text-xs text-muted-foreground">v{r.course_version}</span>
                  </TD>
                  <TD label={t("fields.delivered_at")}>{dateTime(r.delivered_at)}</TD>
                  <TD label={t("fields.delivery_language")}>
                    {te(`workerLanguage.${r.delivery_language}`)}
                    {r.language_mismatch ? <span className="ms-1"><StatusBadge status="warn" label={t("mismatch")} /></span> : null}
                  </TD>
                  <TD label={t("fields.test_score_pct")}>{r.test_score_pct ?? "—"}</TD>
                  <TD label={t("fields.valid_until")}>
                    {r.valid_until ? date(r.valid_until) : "—"} {r.status === "valid" ? <DaysLeft days={r.days_left} /> : null}
                  </TD>
                  <TD label={tc("status")}>
                    <StatusBadge status={r.status} label={te(`inductionStatus.${r.status}`)} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={query.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState />
      )}
    </div>
  );
}

/* ───────────────────────────── Single record ───────────────────────────── */

export function InductionCreatePage() {
  const t = useTranslations("inductions");
  const s = useSearchState();
  return (
    <div>
      <Breadcrumbs items={[{ label: t("records"), href: "/inductions" }, { label: t("record") }]} />
      <PageHeader title={t("record")} description={t("recordHint")} />
      <ProjectGate>{(p) => <InductionForm project={p} deploymentId={s.get("deployment_id")} />}</ProjectGate>
    </div>
  );
}

function useCourseOptions(projectId: string) {
  const q = useInductionCourses(projectId, {});
  return (q.data?.items ?? []).filter((c) => c.active);
}

function InductionForm({ project, deploymentId }: { project: Schemas["ProjectRead"]; deploymentId: string | null }) {
  const t = useTranslations("inductions");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const locale = useLocale();
  const router = useRouter();
  const qc = useQueryClient();
  const warn = useWarningToasts();
  const me = useMeData();
  const courses = useCourseOptions(project.id);
  const pre = useDeployment(deploymentId ?? "");
  const [dep, setDep] = useState<Schemas["DeploymentRead"] | null>(null);
  const worker = dep ?? (deploymentId ? (pre.data ?? null) : null);
  const [courseId, setCourseId] = useState("");
  const course = courses.find((c) => c.id === courseId) ?? null;
  const [deliveredAt, setDeliveredAt] = useState(nowInput);
  const [duration, setDuration] = useState("");
  const [lang, setLang] = useState<Lang | "">("");
  const [interpreter, setInterpreter] = useState(false);
  const [score, setScore] = useState("");
  const [wpn, setWpn] = useState("WPN-1.0");
  const [helmet, setHelmet] = useState("");
  const [sessionRef, setSessionRef] = useState("");
  const [sig, setSig] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [retrain, setRetrain] = useState(false);
  const person = useWorker(worker?.worker_id ?? "");
  const primary = person.data?.primary_language ?? null;
  const mismatch = Boolean(primary && lang && lang !== primary && !interpreter);

  async function submit() {
    const e: Record<string, string> = {};
    if (!worker) e.worker = tv("required");
    if (!course) e.course = tv("required");
    if (!lang) e.lang = tv("required");
    if (!duration || Number(duration) < 1) e.duration = tv("required");
    else if (course && Number(duration) < course.min_duration_minutes) e.duration = t("tooShort", { min: course.min_duration_minutes });
    if (course?.test_required && score === "") e.score = tv("required");
    if (!wpn.trim()) e.wpn = tv("required");
    if (!sig) e.sig = t("signatureRequired");
    setErrors(e);
    if (Object.keys(e).length || !worker || !course || !lang || !sig) return;
    setBusy(true);
    setError(null);
    try {
      const r = await unwrap(
        api.POST("/api/v1/projects/{project_id}/inductions", {
          params: { path: { project_id: project.id } },
          body: {
            worker_id: worker.worker_id,
            course_id: course.id,
            delivered_at: zonedInputToUtc(deliveredAt),
            duration_minutes: Number(duration),
            delivery_language: lang,
            interpreter_used: interpreter,
            test_score_pct: course.test_required ? score : null,
            privacy_notice_version: wpn.trim(),
            signature_png_base64: sig,
            helmet_sticker_no: helmet.trim() || null,
            session_ref: sessionRef.trim() || null,
          },
        }),
      );
      qc.setQueryData(ak.induction(r.id), r);
      await qc.invalidateQueries({ queryKey: ["inductions"] });
      await qc.invalidateQueries({ queryKey: ["worker"] });
      await qc.invalidateQueries({ queryKey: ["workers"] });
      await qc.invalidateQueries({ queryKey: ["deployment"] });
      await qc.invalidateQueries({ queryKey: ["deployments"] });
      warn(r.warnings);
      toast.success(r.result === "passed" ? t("savedPassed", { no: r.induction_no }) : t("savedFailed", { no: r.induction_no }));
      router.push(`/inductions/${r.id}`);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  const attemptsExceeded = error instanceof ApiError && error.code === "INDUCTION_ATTEMPTS_EXCEEDED";

  return (
    <form
      className="flex max-w-3xl flex-col gap-6"
      noValidate
      autoComplete="off"
      data-testid="induction-form"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <FormSection title={t("whoWhat")}>
        <div className="sm:col-span-2">
          <DeploymentPicker
            id="in-worker"
            projectId={project.id}
            value={worker}
            onChange={setDep}
            status={["pending_induction", "mobilised"]}
            label={t("worker")}
            required
            error={errors.worker}
          />
        </div>
        <FormField id="in-course-sel" label={t("course")} required error={errors.course} className="sm:col-span-2">
          <Select
            value={courseId}
            onChange={(e) => {
              setCourseId(e.target.value);
              const c = courses.find((x) => x.id === e.target.value);
              if (c && !duration) setDuration(String(c.min_duration_minutes));
            }}
            data-testid="in-course-sel"
          >
            <option value="">{tc("select")}</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {courseLabel(c, locale)}
              </option>
            ))}
          </Select>
        </FormField>
        {course && course.prerequisite_codes.length ? (
          <p className="text-sm text-muted-foreground sm:col-span-2">{t("prerequisites", { codes: course.prerequisite_codes.join(", ") })}</p>
        ) : null}
        <FormField id="in-at" label={t("fields.delivered_at")} required>
          <Input type="datetime-local" value={deliveredAt} onChange={(e) => setDeliveredAt(e.target.value)} max={nowInput()} />
        </FormField>
        <FormField id="in-duration" label={t("fields.duration_minutes")} required error={errors.duration} hint={course ? t("minDuration", { min: course.min_duration_minutes }) : undefined}>
          <Input type="number" inputMode="numeric" min={1} value={duration} onChange={(e) => setDuration(e.target.value)} />
        </FormField>
        <FormField id="in-session-ref" label={t("fields.session_ref")}>
          <Input maxLength={30} className="ltr" value={sessionRef} onChange={(e) => setSessionRef(e.target.value)} />
        </FormField>
      </FormSection>
      <FormSection title={t("delivery")}>
        <FormField id="in-lang" label={t("fields.delivery_language")} required error={errors.lang}>
          <Select value={lang} onChange={(e) => setLang(e.target.value as Lang)} data-testid="in-lang">
            <option value="">{tc("select")}</option>
            {(course?.languages_offered ?? WORKER_LANGUAGES).map((x) => (
              <option key={x} value={x}>
                {te(`workerLanguage.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <CheckboxField id="in-interpreter" label={t("fields.interpreter_used")}>
          <Checkbox checked={interpreter} onChange={(e) => setInterpreter(e.target.checked)} />
        </CheckboxField>
        {mismatch && primary ? (
          <Alert tone="warning" className="sm:col-span-2" data-testid="language-mismatch">
            {t("mismatchHint", { lang: te(`workerLanguage.${primary}`) })}
          </Alert>
        ) : null}
        {course?.test_required ? (
          <FormField id="in-score" label={t("fields.test_score_pct")} required error={errors.score} hint={t("passMark", { pct: course.effective_pass_mark_pct ?? 0 })}>
            <Input type="number" inputMode="decimal" min={0} max={100} step="0.01" value={score} onChange={(e) => setScore(e.target.value)} />
          </FormField>
        ) : null}
        <FormField id="in-helmet" label={t("fields.helmet_sticker_no")}>
          <Input maxLength={20} className="ltr" value={helmet} onChange={(e) => setHelmet(e.target.value)} />
        </FormField>
      </FormSection>
      <FormSection title={t("privacyAndSignature")} description={t("privacyHint")}>
        <FormField id="in-wpn" label={t("fields.privacy_notice_version")} required error={errors.wpn}>
          <Input maxLength={20} className="ltr" value={wpn} onChange={(e) => setWpn(e.target.value)} />
        </FormField>
        <div className="sm:col-span-2">
          <SignaturePad id="in-signature" label={t("signature")} onChange={setSig} error={errors.sig} />
        </div>
      </FormSection>
      <MutationError error={error} />
      {attemptsExceeded && worker && course ? (
        <Alert tone="warning">
          {t("attemptsExceeded")}{" "}
          {can(me, "induction.suspend_revoke", project.id) || can(me, "induction.course_manage", project.id) ? (
            <Button type="button" size="sm" variant="outline" onClick={() => setRetrain(true)} data-testid="retraining-note">
              <NotebookPen aria-hidden />
              {t("retrainingNote")}
            </Button>
          ) : null}
        </Alert>
      ) : null}
      <div className="flex gap-2">
        <Button type="submit" disabled={busy} data-testid="save-induction">
          <GraduationCap aria-hidden />
          {busy ? tc("saving") : t("save")}
        </Button>
        <Button type="button" variant="outline" onClick={() => router.back()}>
          {tc("cancel")}
        </Button>
      </div>
      {retrain && worker && course ? <RetrainingDialog projectId={project.id} workerId={worker.worker_id} courseId={course.id} onClose={() => setRetrain(false)} /> : null}
    </form>
  );
}

function RetrainingDialog({ projectId, workerId, courseId, onClose }: { projectId: string; workerId: string; courseId: string; onClose: () => void }) {
  const t = useTranslations("inductions");
  const tc = useTranslations("common");
  const [note, setNote] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(api.POST("/api/v1/projects/{project_id}/induction-retraining-notes", { params: { path: { project_id: projectId } }, body: { worker_id: workerId, course_id: courseId, note: note.trim() } }));
      toast.success(t("retrainingSaved"));
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")}>
        <DialogHeader>
          <DialogTitle>{t("retrainingNote")}</DialogTitle>
          <DialogDescription>{t("retrainingHint")}</DialogDescription>
        </DialogHeader>
        <FormField id="rt-note" label={t("note")} required hint={t("min10")}>
          <Textarea rows={3} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
        </FormField>
        <MutationError error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button onClick={() => void save()} disabled={busy || note.trim().length < 10} data-testid="retraining-save">
            {tc("save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ───────────────────────────── Batch session ───────────────────────────── */

interface Attendee {
  dep: Schemas["DeploymentRead"];
  primary: Lang;
  lang: Lang;
  interpreter: boolean;
  score: string;
  helmet: string;
  sig: string | null;
}

export function InductionSessionPage() {
  const t = useTranslations("inductions");
  return (
    <div>
      <Breadcrumbs items={[{ label: t("records"), href: "/inductions" }, { label: t("batchSession") }]} />
      <PageHeader title={t("batchSession")} description={t("batchHint")} />
      <ProjectGate>{(p) => <SessionForm project={p} />}</ProjectGate>
    </div>
  );
}

function SessionForm({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("inductions");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const locale = useLocale();
  const qc = useQueryClient();
  const courses = useCourseOptions(project.id);
  const [courseId, setCourseId] = useState("");
  const course = courses.find((c) => c.id === courseId) ?? null;
  const [deliveredAt, setDeliveredAt] = useState(nowInput);
  const [duration, setDuration] = useState("");
  const [sessionRef, setSessionRef] = useState("");
  const [wpn, setWpn] = useState("WPN-1.0");
  const [rows, setRows] = useState<Attendee[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Schemas["InductionRecordRead"][] | null>(null);
  const [picker, setPicker] = useState<Schemas["DeploymentRead"] | null>(null);

  async function add(d: Schemas["DeploymentRead"] | null) {
    setPicker(null);
    if (!d || rows.some((r) => r.dep.id === d.id) || rows.length >= 60) return;
    let primary: Lang = "en";
    try {
      const w = await qc.fetchQuery({ queryKey: ak.worker(d.worker_id), queryFn: () => unwrap(api.GET("/api/v1/workers/{worker_id}", { params: { path: { worker_id: d.worker_id } } })) });
      primary = w.primary_language;
    } catch {
      /* keep the default; the server still records the mismatch warning */
    }
    const lang = course && !course.languages_offered.includes(primary) ? (course.languages_offered[0] ?? primary) : primary;
    setRows((rs) => (rs.some((r) => r.dep.id === d.id) ? rs : [...rs, { dep: d, primary, lang, interpreter: false, score: "", helmet: "", sig: null }]));
  }
  function patch(i: number, p: Partial<Attendee>) {
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...p } : r)));
  }
  async function submit() {
    setFormError(null);
    if (!course || !duration || rows.length === 0) {
      setFormError(tv("required"));
      return;
    }
    if (rows.some((r) => !r.sig || (course.test_required && r.score === ""))) {
      setFormError(t("attendeeIncomplete"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await unwrap(
        api.POST("/api/v1/projects/{project_id}/induction-sessions", {
          params: { path: { project_id: project.id } },
          body: {
            course_id: course.id,
            delivered_at: zonedInputToUtc(deliveredAt),
            duration_minutes: Number(duration),
            session_ref: sessionRef.trim() || null,
            attendees: rows.map((a) => ({
              worker_id: a.dep.worker_id,
              delivery_language: a.lang,
              interpreter_used: a.interpreter,
              test_score_pct: course.test_required ? a.score : null,
              privacy_notice_version: wpn.trim(),
              signature_png_base64: a.sig ?? "",
              helmet_sticker_no: a.helmet.trim() || null,
            })),
          },
        }),
      );
      setResult(r.items);
      for (const k of ["inductions", "worker", "workers", "deployment", "deployments"]) await qc.invalidateQueries({ queryKey: [k] });
      toast.success(t("sessionSaved", { count: r.items.length }));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    return (
      <Card data-testid="session-result">
        <CardHeader>
          <CardTitle>{t("sessionResult")}</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="flex flex-col divide-y">
            {result.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-2 py-2">
                <Link href={`/inductions/${r.id}`} className="ltr font-medium text-primary hover:underline">
                  {r.induction_no}
                </Link>
                <span>
                  <Code>{r.worker.worker_no}</Code> {personName(r.worker, locale)}
                </span>
                <StatusBadge status={r.result === "passed" ? "passed" : "failed"} label={te(`inductionResult.${r.result}`)} />
                {r.language_mismatch ? <StatusBadge status="warn" label={t("mismatch")} /> : null}
                <ApiWarnings warnings={r.warnings} />
              </li>
            ))}
          </ul>
          <Button className="mt-4" variant="outline" asChild>
            <Link href="/inductions">{t("records")}</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <form
      className="flex flex-col gap-6"
      noValidate
      autoComplete="off"
      data-testid="session-form"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <FormSection title={t("session")}>
        <FormField id="ss-course" label={t("course")} required className="sm:col-span-2">
          <Select
            value={courseId}
            onChange={(e) => {
              setCourseId(e.target.value);
              const c = courses.find((x) => x.id === e.target.value);
              if (c && !duration) setDuration(String(c.min_duration_minutes));
            }}
          >
            <option value="">{tc("select")}</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {courseLabel(c, locale)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="ss-at" label={t("fields.delivered_at")} required>
          <Input type="datetime-local" value={deliveredAt} onChange={(e) => setDeliveredAt(e.target.value)} max={nowInput()} />
        </FormField>
        <FormField id="ss-duration" label={t("fields.duration_minutes")} required hint={course ? t("minDuration", { min: course.min_duration_minutes }) : undefined}>
          <Input type="number" min={1} value={duration} onChange={(e) => setDuration(e.target.value)} />
        </FormField>
        <FormField id="ss-ref" label={t("fields.session_ref")}>
          <Input maxLength={30} className="ltr" value={sessionRef} onChange={(e) => setSessionRef(e.target.value)} />
        </FormField>
        <FormField id="ss-wpn" label={t("fields.privacy_notice_version")} required>
          <Input maxLength={20} className="ltr" value={wpn} onChange={(e) => setWpn(e.target.value)} />
        </FormField>
      </FormSection>
      <FormSection title={t("attendees", { count: rows.length })} description={t("attendeesHint")}>
        <div className="sm:col-span-2">
          <DeploymentPicker id="ss-add" projectId={project.id} value={picker} onChange={(d) => void add(d)} status={["pending_induction", "mobilised"]} label={t("addAttendee")} />
        </div>
        {rows.map((a, i) => (
          <div key={a.dep.id} className="flex flex-col gap-3 rounded-lg border p-3 sm:col-span-2" data-testid="attendee">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium">
                <Code>{a.dep.worker_no}</Code> {personName(a.dep, locale)}
              </span>
              <Button type="button" size="sm" variant="ghost" onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}>
                {tc("remove")}
              </Button>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <FormField id={`ss-lang-${i}`} label={t("fields.delivery_language")} required>
                <Select value={a.lang} onChange={(e) => patch(i, { lang: e.target.value as Lang })}>
                  {(course?.languages_offered ?? WORKER_LANGUAGES).map((x) => (
                    <option key={x} value={x}>
                      {te(`workerLanguage.${x}`)}
                    </option>
                  ))}
                </Select>
              </FormField>
              {course?.test_required ? (
                <FormField id={`ss-score-${i}`} label={t("fields.test_score_pct")} required>
                  <Input type="number" min={0} max={100} step="0.01" value={a.score} onChange={(e) => patch(i, { score: e.target.value })} />
                </FormField>
              ) : null}
              <FormField id={`ss-helmet-${i}`} label={t("fields.helmet_sticker_no")}>
                <Input maxLength={20} className="ltr" value={a.helmet} onChange={(e) => patch(i, { helmet: e.target.value })} />
              </FormField>
            </div>
            <CheckboxField id={`ss-int-${i}`} label={t("fields.interpreter_used")}>
              <Checkbox checked={a.interpreter} onChange={(e) => patch(i, { interpreter: e.target.checked })} />
            </CheckboxField>
            {a.lang !== a.primary && !a.interpreter ? (
              <Alert tone="warning">{t("mismatchHint", { lang: te(`workerLanguage.${a.primary}`) })}</Alert>
            ) : null}
            <SignaturePad id={`ss-sig-${i}`} label={t("signature")} onChange={(b) => patch(i, { sig: b })} />
          </div>
        ))}
      </FormSection>
      {formError ? <Alert tone="danger">{formError}</Alert> : null}
      <MutationError error={error} />
      <div>
        <Button type="submit" disabled={busy} data-testid="save-session">
          <Upload aria-hidden />
          {busy ? tc("saving") : t("saveSession")}
        </Button>
      </div>
    </form>
  );
}

/* ───────────────────────────── Record detail ───────────────────────────── */

export function InductionDetail({ id }: { id: string }) {
  const t = useTranslations("inductions");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const me = useMeData();
  const q = useInduction(id);
  const qc = useQueryClient();
  const userName = useLocalizedName();
  const [edit, setEdit] = useState(false);
  const { date, dateTime } = useFormatters(q.data?.project_id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const r = q.data;
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("records"), href: "/inductions" }, { label: r.induction_no }]} />
        <PageHeader
          title={r.induction_no}
          description={`${r.worker.worker_no} · ${personName(r.worker, locale)} · ${r.course_code}`}
          actions={
            <>
              <StatusBadge status={r.status} label={te(`inductionStatus.${r.status}`)} />
              {canWrite(me, "induction.record", r.project_id) ? (
                <Button variant="outline" onClick={() => setEdit(true)} data-testid="edit-induction">
                  <Pencil aria-hidden />
                  {tc("edit")}
                </Button>
              ) : null}
            </>
          }
        />
      </div>
      {r.language_mismatch ? (
        <Alert tone="warning" data-testid="language-mismatch">
          {t("mismatchRecorded")}
        </Alert>
      ) : null}
      <ApiWarnings warnings={r.warnings} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardContent className="pt-5">
            <FieldList>
              <FieldItem label={t("worker")}>
                <Link href={`/workers/${r.worker.id}`} className="text-primary hover:underline">
                  <Code>{r.worker.worker_no}</Code> {personName(r.worker, locale)}
                </Link>
              </FieldItem>
              <FieldItem label={tc("contractor")}>{r.engagement?.short_code ?? "—"}</FieldItem>
              <FieldItem label={t("course")}>
                <Link href={`/induction-courses/${r.course_id}`} className="text-primary hover:underline">
                  {r.course_code}
                </Link>{" "}
                v{r.course_version} · {te(`inductionType.${r.induction_type}`)}
              </FieldItem>
              <FieldItem label={t("fields.session_ref")} ltr>
                {r.session_ref ?? "—"}
              </FieldItem>
              <FieldItem label={t("fields.delivered_at")}>{dateTime(r.delivered_at)}</FieldItem>
              <FieldItem label={t("fields.delivered_by")}>{userName(r.delivered_by.full_name_en, r.delivered_by.full_name_ar)}</FieldItem>
              <FieldItem label={t("fields.duration_minutes")}>{r.duration_minutes}</FieldItem>
              <FieldItem label={t("fields.delivery_language")}>{te(`workerLanguage.${r.delivery_language}`)}</FieldItem>
              <FieldItem label={t("fields.interpreter_used")}>
                <YesNo value={r.interpreter_used} yes={tc("yes")} no={tc("no")} />
              </FieldItem>
              <FieldItem label={t("fields.test_score_pct")}>{r.test_score_pct ?? "—"}</FieldItem>
              <FieldItem label={t("fields.attempt_no")}>{r.attempt_no}</FieldItem>
              <FieldItem label={t("fields.result")}>
                <StatusBadge status={r.result} label={te(`inductionResult.${r.result}`)} />
              </FieldItem>
              <FieldItem label={t("fields.valid_from")}>{date(r.valid_from)}</FieldItem>
              <FieldItem label={t("fields.valid_until")}>
                {date(r.valid_until)} {r.status === "valid" ? <DaysLeft days={r.days_left} /> : null}
              </FieldItem>
              {r.reinduction_due_on ? <FieldItem label={t("fields.reinduction_due_on")}>{date(r.reinduction_due_on)}</FieldItem> : null}
              <FieldItem label={t("fields.helmet_sticker_no")} ltr>
                {r.helmet_sticker_no ?? "—"}
              </FieldItem>
              <FieldItem label={t("fields.privacy_notice_version")} ltr>
                {r.privacy_notice_version}
              </FieldItem>
            </FieldList>
          </CardContent>
        </Card>
        {r.result === "passed" ? (
          <CredentialPanel
            kind="induction"
            id={r.id}
            projectId={r.project_id}
            onChanged={() => {
              void qc.invalidateQueries({ queryKey: ak.induction(r.id) });
            }}
          />
        ) : null}
      </div>
      <HistoryPanel entityType="induction_record" entityId={r.id} />
      {edit ? <EditInductionDialog r={r} onClose={() => setEdit(false)} /> : null}
    </div>
  );
}

function EditInductionDialog({ r, onClose }: { r: Schemas["InductionRecordRead"]; onClose: () => void }) {
  const t = useTranslations("inductions");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const [lang, setLang] = useState<Lang>(r.delivery_language);
  const [interp, setInterp] = useState(r.interpreter_used);
  const [helmet, setHelmet] = useState(r.helmet_sticker_no ?? "");
  const [sessionRef, setSessionRef] = useState(r.session_ref ?? "");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [old] = useState(() => Date.now() - new Date(r.created_at).getTime() > 24 * 3600 * 1000);
  async function save() {
    setBusy(true);
    setError(null);
    try {
      const u = await unwrap(
        api.PATCH("/api/v1/inductions/{induction_id}", {
          params: { path: { induction_id: r.id } },
          body: { delivery_language: lang, interpreter_used: interp, helmet_sticker_no: helmet.trim() || null, session_ref: sessionRef.trim() || null, edit_reason: reason.trim() || null },
        }),
      );
      qc.setQueryData(ak.induction(r.id), u);
      await qc.invalidateQueries({ queryKey: ["inductions"] });
      toast.success(tc("saved"));
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")}>
        <DialogHeader>
          <DialogTitle>{t("editTitle")}</DialogTitle>
          <DialogDescription>{old ? t("editAfter24h") : t("editHint")}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <FormField id="ei-lang" label={t("fields.delivery_language")}>
            <Select value={lang} onChange={(e) => setLang(e.target.value as Lang)}>
              {WORKER_LANGUAGES.map((x) => (
                <option key={x} value={x}>
                  {te(`workerLanguage.${x}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <CheckboxField id="ei-int" label={t("fields.interpreter_used")}>
            <Checkbox checked={interp} onChange={(e) => setInterp(e.target.checked)} />
          </CheckboxField>
          <FormField id="ei-helmet" label={t("fields.helmet_sticker_no")}>
            <Input className="ltr" maxLength={20} value={helmet} onChange={(e) => setHelmet(e.target.value)} />
          </FormField>
          <FormField id="ei-ref" label={t("fields.session_ref")}>
            <Input className="ltr" maxLength={30} value={sessionRef} onChange={(e) => setSessionRef(e.target.value)} />
          </FormField>
          <FormField id="ei-reason" label={old ? t("editReason") : t("editReasonOptional")} required={old}>
            <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
          </FormField>
        </div>
        <MutationError error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button onClick={() => void save()} disabled={busy || (old && reason.trim().length < 10)} data-testid="save-induction-edit">
            {tc("save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ───────────────────────────── Courses ───────────────────────────── */

export function CourseListPage() {
  return <ProjectGate>{(p) => <CourseList project={p} />}</ProjectGate>;
}

function CourseList({ project }: { project: Schemas["ProjectRead"] }) {
  const t = useTranslations("inductions");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const me = useMeData();
  const locale = useLocale();
  const q = useInductionCourses(project.id);
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("courses")}
        description={t("coursesHint")}
        actions={
          canWrite(me, "induction.course_manage", project.id) ? (
            <Button asChild>
              <Link href="/induction-courses/new" data-testid="new-course">
                <Plus aria-hidden />
                {t("newCourse")}
              </Link>
            </Button>
          ) : null
        }
      />
      <WorkerSubNav />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="courses-table">
          <THead>
            <TR>
              <TH>{t("fields.code")}</TH>
              <TH>{t("fields.name")}</TH>
              <TH>{t("fields.induction_type")}</TH>
              <TH>{t("fields.version")}</TH>
              <TH>{t("fields.validity")}</TH>
              <TH>{t("fields.test_required")}</TH>
              <TH>{tc("status")}</TH>
            </TR>
          </THead>
          <TBody>
            {items.map((c) => (
              <TR key={c.id} data-testid="course-row">
                <TD label={t("fields.code")}>
                  <Link href={`/induction-courses/${c.id}`} className="ltr font-medium text-primary hover:underline">
                    {c.code}
                  </Link>
                </TD>
                <TD label={t("fields.name")}>{locale === "ar" ? c.name_ar : c.name_en}</TD>
                <TD label={t("fields.induction_type")}>{te(`inductionType.${c.induction_type}`)}</TD>
                <TD label={t("fields.version")}>
                  <span className="ltr">v{c.version}</span>
                </TD>
                <TD label={t("fields.validity")}>{c.validity_days ? t("days", { n: c.validity_days }) : t("months", { n: c.validity_months ?? 0 })}</TD>
                <TD label={t("fields.test_required")}>{c.test_required ? t("passMark", { pct: c.effective_pass_mark_pct ?? 0 }) : tc("no")}</TD>
                <TD label={tc("status")}>
                  <StatusBadge status={c.active ? "active" : "inactive"} label={c.active ? t("active") : t("inactive")} />
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <EmptyState />
      )}
    </div>
  );
}

export function CourseCreatePage() {
  const t = useTranslations("inductions");
  return (
    <div>
      <Breadcrumbs items={[{ label: t("courses"), href: "/induction-courses" }, { label: t("newCourse") }]} />
      <PageHeader title={t("newCourse")} />
      <ProjectGate>{(p) => <CourseForm project={p} />}</ProjectGate>
    </div>
  );
}

export function CourseEditPage({ id }: { id: string }) {
  const t = useTranslations("inductions");
  const q = useInductionCourse(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const c = q.data;
  return (
    <div>
      <Breadcrumbs items={[{ label: t("courses"), href: "/induction-courses" }, { label: c.code, href: `/induction-courses/${c.id}` }, { label: t("editCourse") }]} />
      <PageHeader title={t("editCourse")} />
      <ProjectById id={c.project_id}>{(p) => <CourseForm project={p} course={c} />}</ProjectById>
    </div>
  );
}

function CourseForm({ project, course }: { project: Schemas["ProjectRead"]; course?: Course }) {
  const t = useTranslations("inductions");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const tv = useTranslations("validation");
  const router = useRouter();
  const qc = useQueryClient();
  const all = useInductionCourses(project.id);
  const [code, setCode] = useState(course?.code ?? "");
  const [type, setType] = useState<Schemas["InductionType"]>(course?.induction_type ?? "general_site");
  const [nameEn, setNameEn] = useState(course?.name_en ?? "");
  const [nameAr, setNameAr] = useState(course?.name_ar ?? "");
  const [version, setVersion] = useState(course?.version ?? "1.0");
  const [months, setMonths] = useState(String(course?.validity_months ?? 12));
  const [days, setDays] = useState(String(course?.validity_days ?? 1));
  const [minDur, setMinDur] = useState(String(course?.min_duration_minutes ?? 60));
  const [test, setTest] = useState(course?.test_required ?? false);
  const [passMark, setPassMark] = useState(course?.pass_mark_pct != null ? String(course.pass_mark_pct) : "");
  const [langs, setLangs] = useState<Lang[]>(course?.languages_offered ?? ["ar", "en"]);
  const [prereq, setPrereq] = useState<string[]>(course?.prerequisite_codes ?? []);
  const [roles, setRoles] = useState<Schemas["InductionDelivererRole"][]>(course?.delivered_by_roles ?? ["hse_officer"]);
  const [active, setActive] = useState(course?.active ?? true);
  const [error, setError] = useState<unknown>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const visitor = type === "visitor";
  const airsideNoContractor = type === "airside" && roles.includes("contractor_hse_rep");
  const otherCodes = (all.data?.items ?? []).filter((c) => c.id !== course?.id).map((c) => ({ value: c.code, label: c.code }));

  async function save() {
    setFormError(null);
    if (!code.trim() || !nameEn.trim() || !nameAr.trim() || !/^\d+\.\d+$/.test(version) || langs.length === 0 || roles.length === 0 || Number(minDur) < 15) {
      setFormError(tv("required"));
      return;
    }
    setBusy(true);
    setError(null);
    const common = {
      name_en: nameEn.trim(),
      name_ar: nameAr.trim(),
      validity_months: visitor ? null : Number(months),
      validity_days: visitor ? Number(days) : null,
      min_duration_minutes: Number(minDur),
      test_required: test,
      pass_mark_pct: test && passMark ? Number(passMark) : null,
      languages_offered: langs,
      prerequisite_codes: prereq,
      delivered_by_roles: roles,
      active,
    };
    try {
      const saved = course
        ? await unwrap(api.PATCH("/api/v1/induction-courses/{course_id}", { params: { path: { course_id: course.id } }, body: common }))
        : await unwrap(
            api.POST("/api/v1/projects/{project_id}/induction-courses", {
              params: { path: { project_id: project.id } },
              body: { ...common, code: code.trim().toUpperCase(), induction_type: type, version },
            }),
          );
      qc.setQueryData(ak.course(saved.id), saved);
      await qc.invalidateQueries({ queryKey: ["induction-courses"] });
      toast.success(tc("saved"));
      router.push(`/induction-courses/${saved.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className="flex max-w-3xl flex-col gap-6"
      noValidate
      data-testid="course-form"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <FormSection title={t("course")}>
        <FormField id="c-code" label={t("fields.code")} required>
          <Input maxLength={10} className="ltr uppercase" value={code} disabled={Boolean(course)} onChange={(e) => setCode(e.target.value)} />
        </FormField>
        <FormField id="c-type" label={t("fields.induction_type")} required>
          <Select value={type} disabled={Boolean(course)} onChange={(e) => setType(e.target.value as Schemas["InductionType"])}>
            {INDUCTION_TYPES.map((x) => (
              <option key={x} value={x}>
                {te(`inductionType.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="c-name-en" label={t("fields.name_en")} required>
          <Input dir="ltr" maxLength={150} value={nameEn} onChange={(e) => setNameEn(e.target.value)} />
        </FormField>
        <FormField id="c-name-ar" label={t("fields.name_ar")} required>
          <Input dir="rtl" lang="ar" maxLength={150} value={nameAr} onChange={(e) => setNameAr(e.target.value)} />
        </FormField>
        <FormField id="c-version" label={t("fields.version")} required hint={course ? t("versionHint") : undefined}>
          <Input className="ltr" value={version} disabled={Boolean(course)} onChange={(e) => setVersion(e.target.value)} />
        </FormField>
        {visitor ? (
          <FormField id="c-days" label={t("fields.validity_days")} required>
            <Input type="number" min={1} max={7} value={days} onChange={(e) => setDays(e.target.value)} />
          </FormField>
        ) : (
          <FormField id="c-months" label={t("fields.validity_months")} required>
            <Input type="number" min={1} max={36} value={months} onChange={(e) => setMonths(e.target.value)} />
          </FormField>
        )}
        <FormField id="c-min" label={t("fields.min_duration_minutes")} required>
          <Input type="number" min={15} value={minDur} onChange={(e) => setMinDur(e.target.value)} />
        </FormField>
        <CheckboxField id="c-test" label={t("fields.test_required")}>
          <Checkbox checked={test} onChange={(e) => setTest(e.target.checked)} />
        </CheckboxField>
        {test ? (
          <FormField id="c-pass" label={t("fields.pass_mark_pct")} hint={t("passMarkHint")}>
            <Input type="number" min={50} max={100} value={passMark} onChange={(e) => setPassMark(e.target.value)} />
          </FormField>
        ) : null}
        <MultiSelect id="c-langs" label={t("fields.languages_offered")} options={WORKER_LANGUAGES.map((x) => ({ value: x, label: te(`workerLanguage.${x}`) }))} value={langs} onChange={(v) => setLangs(v as Lang[])} className="lg:w-full" />
        <MultiSelect id="c-roles" label={t("fields.delivered_by_roles")} options={INDUCTION_DELIVERER_ROLES.map((x) => ({ value: x, label: te(`delivererRole.${x}`) }))} value={roles} onChange={(v) => setRoles(v as Schemas["InductionDelivererRole"][])} className="lg:w-full" />
        <MultiSelect id="c-prereq" label={t("fields.prerequisite_codes")} options={otherCodes} value={prereq} onChange={setPrereq} className="lg:w-full" />
        <CheckboxField id="c-active" label={t("active")}>
          <Checkbox checked={active} onChange={(e) => setActive(e.target.checked)} />
        </CheckboxField>
        {airsideNoContractor ? (
          <Alert tone="warning" className="sm:col-span-2">
            {t("airsideDeliverer")}
          </Alert>
        ) : null}
      </FormSection>
      {formError ? <Alert tone="danger">{formError}</Alert> : null}
      <MutationError error={error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={busy} data-testid="save-course">
          {busy ? tc("saving") : tc("save")}
        </Button>
        <Button type="button" variant="outline" onClick={() => router.back()}>
          {tc("cancel")}
        </Button>
      </div>
    </form>
  );
}

export function CourseDetail({ id }: { id: string }) {
  const t = useTranslations("inductions");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const me = useMeData();
  const q = useInductionCourse(id);
  const [publish, setPublish] = useState(false);
  const { date } = useFormatters(q.data?.project_id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const c = q.data;
  const manage = canWrite(me, "induction.course_manage", c.project_id);
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("courses"), href: "/induction-courses" }, { label: c.code }]} />
        <PageHeader
          title={`${c.code} — ${locale === "ar" ? c.name_ar : c.name_en}`}
          description={`v${c.version} · ${te(`inductionType.${c.induction_type}`)}`}
          actions={
            manage ? (
              <>
                <Button variant="outline" asChild>
                  <Link href={`/induction-courses/${c.id}/edit`} data-testid="edit-course">
                    <Pencil aria-hidden />
                    {tc("edit")}
                  </Link>
                </Button>
                <Button onClick={() => setPublish(true)} data-testid="publish-version">
                  <BookOpen aria-hidden />
                  {t("publishVersion")}
                </Button>
              </>
            ) : null
          }
        />
      </div>
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={t("fields.name_en")}>{c.name_en}</FieldItem>
            <FieldItem label={t("fields.name_ar")}>{c.name_ar}</FieldItem>
            <FieldItem label={t("fields.version")}>
              <span className="ltr">v{c.version}</span> {c.version_published_on ? `· ${date(c.version_published_on)}` : ""}
            </FieldItem>
            <FieldItem label={t("fields.requires_reinduction")}>
              <YesNo value={c.requires_reinduction} yes={tc("yes")} no={tc("no")} />
            </FieldItem>
            <FieldItem label={t("fields.validity")}>{c.validity_days ? t("days", { n: c.validity_days }) : t("months", { n: c.validity_months ?? 0 })}</FieldItem>
            <FieldItem label={t("fields.min_duration_minutes")}>{c.min_duration_minutes}</FieldItem>
            <FieldItem label={t("fields.test_required")}>{c.test_required ? t("passMark", { pct: c.effective_pass_mark_pct ?? 0 }) : tc("no")}</FieldItem>
            <FieldItem label={t("fields.languages_offered")}>{joinList(c.languages_offered.map((l) => te(`workerLanguage.${l}`)))}</FieldItem>
            <FieldItem label={t("fields.delivered_by_roles")}>{joinList(c.delivered_by_roles.map((r) => te(`delivererRole.${r}`)))}</FieldItem>
            <FieldItem label={t("fields.prerequisite_codes")} ltr>
              {c.prerequisite_codes.join(", ") || "—"}
            </FieldItem>
            <FieldItem label={tc("status")}>
              <StatusBadge status={c.active ? "active" : "inactive"} label={c.active ? t("active") : t("inactive")} />
            </FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      <HistoryPanel entityType="induction_course" entityId={c.id} />
      {publish ? <PublishDialog course={c} onClose={() => setPublish(false)} /> : null}
    </div>
  );
}

function PublishDialog({ course, onClose }: { course: Course; onClose: () => void }) {
  const t = useTranslations("inductions");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const next = useMemo(() => {
    const [maj, min] = course.version.split(".").map(Number);
    return `${maj}.${(min ?? 0) + 1}`;
  }, [course.version]);
  const [version, setVersion] = useState(next);
  const [reinduct, setReinduct] = useState(false);
  const [on, setOn] = useState(todayInZone());
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    setError(null);
    try {
      const u = await unwrap(api.POST("/api/v1/induction-courses/{course_id}/versions", { params: { path: { course_id: course.id } }, body: { version, requires_reinduction: reinduct, published_on: on || null } }));
      qc.setQueryData(ak.course(course.id), u);
      await qc.invalidateQueries({ queryKey: ["induction-courses"] });
      await qc.invalidateQueries({ queryKey: ["inductions"] });
      toast.success(t("published", { version: u.version }));
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")}>
        <DialogHeader>
          <DialogTitle>{t("publishVersion")}</DialogTitle>
          <DialogDescription>{t("publishHint")}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <FormField id="pv-version" label={t("fields.version")} required>
            <Input className="ltr" value={version} onChange={(e) => setVersion(e.target.value)} />
          </FormField>
          <FormField id="pv-on" label={t("publishedOn")}>
            <Input type="date" value={on} onChange={(e) => setOn(e.target.value)} />
          </FormField>
          <CheckboxField id="pv-re" label={t("fields.requires_reinduction")}>
            <Checkbox checked={reinduct} onChange={(e) => setReinduct(e.target.checked)} />
          </CheckboxField>
          {reinduct ? <Alert tone="warning">{t("reinductionWarning")}</Alert> : null}
        </div>
        <MutationError error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button onClick={() => void save()} disabled={busy || !/^\d+\.\d+$/.test(version)} data-testid="publish-confirm">
            {t("publish")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
