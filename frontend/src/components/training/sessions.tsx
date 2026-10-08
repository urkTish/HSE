"use client";
import { useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, CheckCheck, PenLine, Plus, Save, Trash2, UserMinus, UserPlus } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
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
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { UserSelect, useProjectOptions } from "@/components/common/pickers";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Code, DeploymentPicker, SignaturePad, StepDialog, WorkerLabel } from "@/components/access/common";
import { UploadField, UserName } from "@/components/cert/common";
import { Link, useRouter } from "@/i18n/navigation";
import { ApiError, api, postForm, unwrap, type Schemas } from "@/lib/api/client";
import { tk, useNominations, useTrainingCourse, useTrainingSession, useTrainingSessions, useTrainingRefresh } from "@/lib/api/training";
import { todayInZone } from "@/lib/datetime";
import { DELIVERY_MODES, SESSION_STATUSES, SESSION_VOID_REASONS, TRAINER_ROLES, WORKER_LANGUAGES } from "@/lib/train-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { CourseLabel, DateFilter, Hours, NominationBadge, ProviderLabel, ProviderSelect, ResultBadge, SessionStatusBadge, useCodeText, useCourseCatalogue, useTrainingCaps, isOn } from "./common";

type S = Schemas;
const PAGE_SIZE = 50;

/* ───────────── list ───────────── */

export function SessionListPage() {
  return <ProjectGate>{(p) => <SessionList project={p} />}</ProjectGate>;
}

function SessionList({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("training.sessions");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const caps = useTrainingCaps(project.id);
  const { courses } = useCourseCatalogue(project.id);
  const { date } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as S["SessionStatus"][];
  const q = useTrainingSessions(project.id, {
    status: status.length ? status : null,
    course_code: s.get("course_code") || null,
    date_from: s.get("date_from") || null,
    date_to: s.get("date_to") || null,
    close_overdue: isOn(s.get("close_overdue")) ? true : null,
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
          caps.sessionManage ? (
            <Button asChild data-testid="new-session">
              <Link href="/training-sessions/new">
                <Plus aria-hidden />
                {t("new")}
              </Link>
            </Button>
          ) : null
        }
      />
      <ListToolbar actions={caps.export ? <ExportButtons dataset="training_sessions" params={{ project_id: project.id }} /> : null}>
        <MultiSelect id="ss-status" label={tc("status")} options={SESSION_STATUSES.map((x) => ({ value: x, label: te(`sessionStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <SelectFilter id="ss-course" label={t("course")} value={s.get("course_code") ?? ""} onChange={(v) => s.set({ course_code: v })} options={courses.map((c) => ({ value: c.code, label: c.code }))} />
        <DateFilter id="ss-from" label={t("from")} value={s.get("date_from") ?? ""} onChange={(v) => s.set({ date_from: v })} />
        <DateFilter id="ss-to" label={t("to")} value={s.get("date_to") ?? ""} onChange={(v) => s.set({ date_to: v })} />
        <SelectFilter id="ss-overdue" label={t("closeOverdue")} value={isOn(s.get("close_overdue")) ? "1" : ""} onChange={(v) => s.set({ close_overdue: v })} options={[{ value: "1", label: tc("yes") }]} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="sessions-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("course")}</TH>
                <TH>{t("dates")}</TH>
                <TH>{t("provider")}</TH>
                <TH>{t("places")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((x) => (
                <TR key={x.id} data-testid="session-row" data-no={x.session_no}>
                  <TD label={t("no")}>
                    <Link href={`/training-sessions/${x.id}`} className="font-medium text-primary hover:underline">
                      <Code>{x.session_no}</Code>
                    </Link>
                  </TD>
                  <TD label={t("course")}>
                    <Code className="font-medium">{x.course.code}</Code>
                    <span className="block text-xs text-muted-foreground">{locale === "ar" ? x.course.name_ar : x.course.name_en}</span>
                  </TD>
                  <TD label={t("dates")}>
                    <span className="ltr">{date(x.first_day)}</span>
                    {x.last_day !== x.first_day ? (
                      <>
                        {" – "}
                        <span className="ltr">{date(x.last_day)}</span>
                      </>
                    ) : null}
                    <span className="block text-xs text-muted-foreground">
                      {te(`workerLanguage.${x.language}`)}
                      {x.site_code ? ` · ${x.site_code}` : ""}
                    </span>
                  </TD>
                  <TD label={t("provider")}>
                    <Code>{x.provider_code}</Code>
                  </TD>
                  <TD label={t("places")}>
                    <span className="ltr tabular-nums">
                      {x.nominated} / {x.capacity}
                    </span>
                  </TD>
                  <TD label={tc("status")}>
                    <span className="flex flex-wrap gap-1">
                      <SessionStatusBadge status={x.status} />
                      {x.close_overdue ? <Badge tone="danger">{t("closeOverdue")}</Badge> : null}
                    </span>
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

/* ───────────── create / edit / from plan ───────────── */

type TrainerRow = { kind: "user" | "worker" | "external"; user: string; dep: S["DeploymentRead"] | null; workerId: string | null; workerLabel: S["WorkerRef"] | null; external: string; roles: S["TrainerRole"][] };
type DayRow = { date: string; start: string; end: string; brk: string };

function netMinutes(d: DayRow): number | null {
  const m = (x: string) => {
    const [h, mm] = x.split(":").map(Number);
    return (h ?? 0) * 60 + (mm ?? 0);
  };
  if (!d.start || !d.end) return null;
  return m(d.end) - m(d.start) - (Number(d.brk) || 0);
}

export function SessionNewPage() {
  return <ProjectGate>{(p) => <SessionForm project={p} />}</ProjectGate>;
}

function SessionForm({ project, session }: { project: S["ProjectRead"]; session?: S["SessionRead"] }) {
  const t = useTranslations("training.sessions");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const qc = useQueryClient();
  const router = useRouter();
  const refresh = useTrainingRefresh();
  const s = useSearchState();
  const fromPlan = !session && s.get("from_plan") === "1";
  const planRecords = (s.get("records") ?? "").split(",").filter(Boolean);
  const opts = useProjectOptions(project.id);
  const { courses, get } = useCourseCatalogue(project.id, { active: true });
  const [course, setCourse] = useState(session?.course.code ?? s.get("course") ?? "");
  const [provider, setProvider] = useState(session?.provider.id ?? "");
  const [providerKind, setProviderKind] = useState<S["TrainingProviderKind"] | null>(session?.provider.kind ?? null);
  const [mode, setMode] = useState<S["DeliveryMode"]>(session?.delivery_mode ?? "classroom");
  const [trainers, setTrainers] = useState<TrainerRow[]>(
    session?.trainers.map((x) => ({
      kind: x.user ? "user" : x.worker ? "worker" : "external",
      user: x.user?.id ?? "",
      dep: null,
      workerId: x.worker?.id ?? null,
      workerLabel: x.worker,
      external: x.external_name ?? "",
      roles: x.roles,
    })) ?? [{ kind: "user", user: "", dep: null, workerId: null, workerLabel: null, external: "", roles: ["trainer", "assessor"] }],
  );
  const [site, setSite] = useState(session?.location.site?.id ?? "");
  const [zone, setZone] = useState(session?.location.zone?.id ?? "");
  const [offsite, setOffsite] = useState(session?.location.offsite_text ?? "");
  const [lang, setLang] = useState<S["WorkerLanguage"]>(session?.language ?? "ar");
  const [interp, setInterp] = useState<S["WorkerLanguage"][]>(session?.interpreter_languages ?? []);
  const [days, setDays] = useState<DayRow[]>(session?.days.map((d) => ({ date: d.date, start: d.start_time.slice(0, 5), end: d.end_time.slice(0, 5), brk: String(d.break_minutes) })) ?? [{ date: "", start: "07:00", end: "16:00", brk: "60" }]);
  const [capacity, setCapacity] = useState(String(session?.capacity ?? ""));
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const info = get(course);
  // Default the capacity to the course's max class size once (render-time adjustment, no effect).
  const [capDefaulted, setCapDefaulted] = useState(false);
  if (!session && !capDefaulted && info?.max_class_size && !capacity) {
    setCapDefaulted(true);
    setCapacity(String(info.max_class_size));
  }
  const external = providerKind === "external";
  const totalNet = days.reduce((a, d) => a + (netMinutes(d) ?? 0), 0);
  const minNet = info?.min_duration_hours ? Number(info.min_duration_hours) * 60 : 0;
  const trainersOk = trainers.length > 0 && trainers.every((x) => x.roles.length && (x.kind === "user" ? x.user : x.kind === "worker" ? x.dep || x.workerId : x.external.trim()));
  const valid = course && provider && trainersOk && (site || offsite.trim()) && days.length && days.every((d) => d.date && d.start && d.end) && Number(capacity) > 0;
  function fields(): S["SessionFields"] {
    return {
      provider_id: provider,
      delivery_mode: mode,
      trainers: trainers.map((x) => ({
        user_id: x.kind === "user" ? x.user : null,
        worker_id: x.kind === "worker" ? (x.dep?.worker_id ?? x.workerId) : null,
        external_name: x.kind === "external" ? x.external.trim() : null,
        roles: x.roles,
      })),
      location: { site_id: site || null, zone_id: zone || null, offsite_text: offsite.trim() || null },
      language: lang,
      interpreter_languages: interp,
      days: days.map((d) => ({ date: d.date, start_time: d.start, end_time: d.end, break_minutes: Number(d.brk) || 0 })),
      capacity: Number(capacity),
    };
  }
  async function save() {
    setBusy(true);
    setError(null);
    try {
      if (session) {
        const r = await unwrap(api.PATCH("/api/v1/training-sessions/{session_id}", { params: { path: { session_id: session.id } }, body: fields() }));
        qc.setQueryData(tk.session(session.id), r);
        await refresh();
        toast.success(tc("saved"));
        s.set({ edit: "" });
        return;
      }
      const r = fromPlan
        ? await unwrap(api.POST("/api/v1/projects/{project_id}/training-sessions/from-plan", { params: { path: { project_id: project.id } }, body: { course_code: course, record_ids: planRecords, language: lang, session: fields() } }))
        : await unwrap(api.POST("/api/v1/projects/{project_id}/training-sessions", { params: { path: { project_id: project.id } }, body: { ...fields(), course_code: course } }));
      await refresh();
      toast.success(t("created", { no: r.session_no }));
      router.push(`/training-sessions/${r.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const zones = opts.zones.filter((z) => !site || z.siteId === site);
  return (
    <div className="flex flex-col gap-5">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/training-sessions" }, { label: session ? session.session_no : t("new") }]} />
        <PageHeader title={session ? t("edit") : fromPlan ? t("newFromPlan") : t("new")} description={fromPlan ? t("fromPlanHint", { n: planRecords.length || t("allNotBooked") }) : t("newHint")} />
      </div>
      <FormSection title={t("courseSection")}>
        <FormField id="ss-course-in" label={t("course")} required>
          <Select value={course} disabled={Boolean(session) || fromPlan} onChange={(e) => setCourse(e.target.value)} data-testid="ss-course-in">
            <option value="">{tc("select")}</option>
            {courses
              .filter((c) => c.category !== "induction_link")
              .map((c) => (
                <option key={c.code} value={c.code}>
                  {c.code} — {c.name_en}
                </option>
              ))}
          </Select>
        </FormField>
        <ProviderSelect
          id="ss-provider"
          label={t("provider")}
          value={provider}
          onChange={(v, p) => {
            setProvider(v);
            setProviderKind(p?.kind ?? null);
          }}
          courseCode={course}
          required
          hint={t("providerHint")}
        />
        <FormField id="ss-mode" label={t("deliveryMode")} required hint={info?.practical_required ? t("practicalHint") : undefined}>
          <Select value={mode} onChange={(e) => setMode(e.target.value as S["DeliveryMode"])} data-testid="ss-mode">
            {(info?.delivery_modes.length ? info.delivery_modes : DELIVERY_MODES).map((x) => (
              <option key={x} value={x}>
                {te(`deliveryMode.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="ss-capacity" label={t("capacity")} required hint={info?.max_class_size ? t("capacityHint", { n: info.max_class_size }) : undefined}>
          <Input type="number" min={1} max={info?.max_class_size ?? 60} value={capacity} onChange={(e) => setCapacity(e.target.value)} className="ltr" data-testid="ss-capacity" />
        </FormField>
        <FormField id="ss-lang" label={t("language")} required>
          <Select value={lang} onChange={(e) => setLang(e.target.value as S["WorkerLanguage"])} data-testid="ss-lang">
            {(info?.languages_offered.length ? info.languages_offered : WORKER_LANGUAGES).map((x) => (
              <option key={x} value={x}>
                {te(`workerLanguage.${x}`)}
              </option>
            ))}
          </Select>
        </FormField>
        <MultiSelect id="ss-interp" label={t("interpreters")} allLabel={t("none")} options={WORKER_LANGUAGES.filter((x) => x !== lang).map((x) => ({ value: x, label: te(`workerLanguage.${x}`) }))} value={interp} onChange={setInterp} />
      </FormSection>
      <FormSection title={t("trainersSection")}>
        <div className="flex flex-col gap-3 sm:col-span-2" data-testid="ss-trainers">
          <p className="text-xs text-muted-foreground">{external ? t("externalTrainersHint") : t("internalTrainersHint")}</p>
          {trainers.map((x, i) => {
            const patch = (p: Partial<TrainerRow>) => setTrainers(trainers.map((y, j) => (j === i ? { ...y, ...p } : y)));
            return (
              <div key={i} className="flex flex-col gap-2 rounded-md border p-3" data-testid="ss-trainer-row">
                <div className="flex flex-wrap items-center gap-3 text-sm">
                  {(["user", "worker", "external"] as const).map((k) => (
                    <label key={k} className="flex min-h-touch items-center gap-2">
                      <input type="radio" checked={x.kind === k} onChange={() => patch({ kind: k })} />
                      {t(`trainerKind.${k}`)}
                    </label>
                  ))}
                  <Button variant="ghost" size="sm" className="ms-auto" disabled={trainers.length === 1} onClick={() => setTrainers(trainers.filter((_, j) => j !== i))}>
                    <Trash2 aria-hidden />
                    <span className="sr-only">{tc("remove")}</span>
                  </Button>
                </div>
                {x.kind === "user" ? (
                  <FormField id={`ss-tr-user-${i}`} label={t("trainer")} required>
                    <UserSelect id={`ss-tr-user-${i}`} projectId={project.id} value={x.user} onChange={(e) => patch({ user: e.target.value })} data-testid={`ss-tr-user-${i}`} />
                  </FormField>
                ) : x.kind === "worker" ? (
                  x.workerLabel && !x.dep ? (
                    <p className="text-sm">
                      <WorkerLabel w={x.workerLabel} />
                    </p>
                  ) : (
                    <DeploymentPicker id={`ss-tr-worker-${i}`} projectId={project.id} value={x.dep} onChange={(d) => patch({ dep: d })} label={t("trainer")} required />
                  )
                ) : (
                  <FormField id={`ss-tr-ext-${i}`} label={t("externalName")} required hint={t("externalNameHint")}>
                    <Input value={x.external} onChange={(e) => patch({ external: e.target.value })} maxLength={120} data-testid={`ss-tr-ext-${i}`} />
                  </FormField>
                )}
                <CheckboxGroup id={`ss-tr-roles-${i}`} legend={t("roles")} required options={TRAINER_ROLES.map((r) => ({ value: r, label: te(`trainerRole.${r}`) }))} value={x.roles} onChange={(v) => patch({ roles: v })} />
              </div>
            );
          })}
          <Button variant="outline" size="sm" className="self-start" onClick={() => setTrainers([...trainers, { kind: external ? "external" : "user", user: "", dep: null, workerId: null, workerLabel: null, external: "", roles: ["trainer"] }])} data-testid="ss-add-trainer">
            <Plus aria-hidden />
            {t("addTrainer")}
          </Button>
        </div>
      </FormSection>
      <FormSection title={t("whereWhen")}>
        <FormField id="ss-site" label={t("site")}>
          <Select
            value={site}
            onChange={(e) => {
              setSite(e.target.value);
              setZone("");
            }}
            data-testid="ss-site"
          >
            <option value="">{t("offsiteOption")}</option>
            {opts.sites.map((x) => (
              <option key={x.value} value={x.value}>
                {x.label}
              </option>
            ))}
          </Select>
        </FormField>
        {site ? (
          <FormField id="ss-zone" label={t("zone")}>
            <Select value={zone} onChange={(e) => setZone(e.target.value)}>
              <option value="">—</option>
              {zones.map((z) => (
                <option key={z.value} value={z.value}>
                  {z.label}
                </option>
              ))}
            </Select>
          </FormField>
        ) : null}
        <FormField id="ss-offsite" label={site ? t("room") : t("offsite")} required={!site}>
          <Input value={offsite} onChange={(e) => setOffsite(e.target.value)} maxLength={200} data-testid="ss-offsite" />
        </FormField>
        <div className="flex flex-col gap-2 sm:col-span-2" data-testid="ss-days">
          <p className="text-sm font-medium">{t("days")}</p>
          {days.map((d, i) => {
            const patch = (p: Partial<DayRow>) => setDays(days.map((y, j) => (j === i ? { ...y, ...p } : y)));
            const net = netMinutes(d);
            return (
              <div key={i} className="grid grid-cols-2 gap-2 rounded-md border p-2 sm:grid-cols-[3rem_1fr_7rem_7rem_6rem_auto] sm:items-end" data-testid="ss-day-row">
                <span className="col-span-2 text-sm font-medium sm:col-span-1 sm:self-center">{t("dayNo", { n: i + 1 })}</span>
                <FormField id={`ss-day-date-${i}`} label={t("date")} required>
                  <Input type="date" className="ltr" value={d.date} onChange={(e) => patch({ date: e.target.value })} data-testid={`ss-day-date-${i}`} />
                </FormField>
                <FormField id={`ss-day-start-${i}`} label={t("start")} required>
                  <Input type="time" className="ltr" value={d.start} onChange={(e) => patch({ start: e.target.value })} data-testid={`ss-day-start-${i}`} />
                </FormField>
                <FormField id={`ss-day-end-${i}`} label={t("end")} required>
                  <Input type="time" className="ltr" value={d.end} onChange={(e) => patch({ end: e.target.value })} data-testid={`ss-day-end-${i}`} />
                </FormField>
                <FormField id={`ss-day-break-${i}`} label={t("breakMin")}>
                  <Input type="number" min={0} className="ltr" value={d.brk} onChange={(e) => patch({ brk: e.target.value })} data-testid={`ss-day-break-${i}`} />
                </FormField>
                <div className="flex items-center gap-2 sm:self-center">
                  <span className="text-xs text-muted-foreground tabular-nums">{net !== null ? t("netMin", { n: net }) : ""}</span>
                  <Button variant="ghost" size="sm" disabled={days.length === 1} onClick={() => setDays(days.filter((_, j) => j !== i))}>
                    <Trash2 aria-hidden />
                    <span className="sr-only">{tc("remove")}</span>
                  </Button>
                </div>
              </div>
            );
          })}
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="outline" size="sm" disabled={days.length >= 15} onClick={() => setDays([...days, { ...(days[days.length - 1] ?? { start: "07:00", end: "16:00", brk: "60" }), date: "" }])} data-testid="ss-add-day">
              <CalendarPlus aria-hidden />
              {t("addDay")}
            </Button>
            <span className={cn("text-xs", minNet && totalNet < minNet ? "text-warning" : "text-muted-foreground")} data-testid="ss-total-net">
              {t("totalNet", { n: totalNet, min: minNet })}
            </span>
          </div>
        </div>
      </FormSection>
      <MutationError error={error} />
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => void save()} disabled={!valid || busy} data-testid="save-session">
          {busy ? tc("saving") : session ? tc("save") : t("saveDraft")}
        </Button>
        <Button variant="outline" asChild>
          <Link href={session ? `/training-sessions/${session.id}` : "/training-sessions"}>{tc("cancel")}</Link>
        </Button>
      </div>
    </div>
  );
}

/* ───────────── detail ───────────── */

export function SessionDetail({ id }: { id: string }) {
  const q = useTrainingSession(id);
  const s = useSearchState();
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  return <ProjectById id={q.data.project_id}>{(p) => (s.get("edit") === "1" ? <SessionForm project={p} session={q.data} /> : <SessionView project={p} x={q.data} />)}</ProjectById>;
}

type Step = "schedule" | "record_delivered" | "cancel" | "close" | "void" | null;

function SessionView({ project, x }: { project: S["ProjectRead"]; x: S["SessionRead"] }) {
  const t = useTranslations("training.sessions");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const s = useSearchState();
  const { date, dateTime } = useFormatters(project.id);
  const refresh = useTrainingRefresh();
  const course = useTrainingCourse(x.course.code, project.id);
  const [step, setStep] = useState<Step>(null);
  const [reason, setReason] = useState("");
  const [sheet, setSheet] = useState<string | null>(x.attendance_sheet_attachment_id);
  const [voidCode, setVoidCode] = useState<S["SessionVoidReason"]>("trainer_not_competent");
  const has = (a: string) => x.allowed_actions.includes(a);
  async function transition(action: S["SessionAction"]) {
    await unwrap(api.POST("/api/v1/training-sessions/{session_id}/transitions", { params: { path: { session_id: x.id } }, body: { action, reason: reason.trim() || null } }));
    await refresh();
    toast.success(te(`sessionAction.${action}`));
  }
  const closeStep = (
    <>
      {has("close") ? (
        <Button onClick={() => setStep("close")} data-testid="session-close">
          {t("close")}
        </Button>
      ) : null}
    </>
  );
  return (
    <div className="flex flex-col gap-5">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/training-sessions" }, { label: x.session_no }]} />
        <PageHeader
          title={x.session_no}
          description={`${x.course.code} — ${locale === "ar" ? x.course.name_ar : x.course.name_en}`}
          actions={
            <>
              <SessionStatusBadge status={x.status} />
              {has("edit") ? (
                <Button variant="outline" onClick={() => s.set({ edit: "1" })} data-testid="edit-session">
                  {tc("edit")}
                </Button>
              ) : null}
              {has("schedule") ? (
                <Button onClick={() => setStep("schedule")} data-testid="session-schedule">
                  {te("sessionAction.schedule")}
                </Button>
              ) : null}
              {has("record_delivered") ? (
                <Button variant="outline" onClick={() => setStep("record_delivered")} data-testid="session-record-delivered">
                  {te("sessionAction.record_delivered")}
                </Button>
              ) : null}
              {closeStep}
              {has("cancel") ? (
                <Button variant="destructive-outline" onClick={() => setStep("cancel")} data-testid="session-cancel">
                  {te("sessionAction.cancel")}
                </Button>
              ) : null}
              {has("void") ? (
                <Button variant="destructive-outline" onClick={() => setStep("void")} data-testid="session-void">
                  {t("void")}
                </Button>
              ) : null}
            </>
          }
        />
      </div>
      {x.close_overdue ? (
        <Alert tone="danger" data-testid="close-overdue">
          {t("closeOverdueHint", { date: x.close_due_on ? date(x.close_due_on) : "—" })}
        </Alert>
      ) : x.status === "delivered" && x.close_due_on ? (
        <Alert tone="info">{t("closeDue", { date: date(x.close_due_on) })}</Alert>
      ) : null}
      <ApiWarnings warnings={x.blockers} />
      {x.void ? (
        <Alert tone="danger" data-testid="session-voided">
          {t("voidedBy", { reason: te(`sessionVoidReason.${x.void.reason_code}`), at: dateTime(x.void.at) })}
          {x.void.reason_text ? ` — ${x.void.reason_text}` : ""}
        </Alert>
      ) : null}
      {x.status_reason && x.status === "cancelled" ? <Alert tone="info">{x.status_reason}</Alert> : null}
      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardContent className="pt-5">
            <FieldList>
              <FieldItem label={t("course")} wide>
                <Link href={`/training-courses/${encodeURIComponent(x.course.code)}`} className="hover:underline">
                  <CourseLabel course={x.course} />
                </Link>
              </FieldItem>
              <FieldItem label={t("provider")} wide>
                <ProviderLabel p={x.provider} />
              </FieldItem>
              <FieldItem label={t("deliveryMode")}>{te(`deliveryMode.${x.delivery_mode}`)}</FieldItem>
              <FieldItem label={t("language")}>
                {te(`workerLanguage.${x.language}`)}
                {x.interpreter_languages.length ? <span className="block text-xs text-muted-foreground">{t("withInterpreters", { langs: x.interpreter_languages.map((l) => te(`workerLanguage.${l}`)).join(", ") })}</span> : null}
              </FieldItem>
              <FieldItem label={t("location")}>
                {x.location.site ? <Code>{x.location.site.code}</Code> : null}
                {x.location.zone ? <Code className="ms-1">{x.location.zone.code}</Code> : null}
                {x.location.offsite_text ? <span className="ms-1">{x.location.offsite_text}</span> : null}
              </FieldItem>
              <FieldItem label={t("places")}>
                <span className="ltr tabular-nums" data-testid="session-places">
                  {x.counts.nominated} / {x.capacity}
                </span>
              </FieldItem>
              <FieldItem label={t("trainers")} wide>
                <ul className="flex flex-col gap-1" data-testid="session-trainers">
                  {x.trainers.map((tr, i) => (
                    <li key={i} className="text-sm">
                      {tr.user ? <UserName u={tr.user} /> : tr.worker ? <WorkerLabel w={tr.worker} /> : <span>{tr.external_name}</span>}
                      <span className="ms-1 text-xs text-muted-foreground">({tr.roles.map((r) => te(`trainerRole.${r}`)).join(", ")})</span>
                      {tr.authorisation_no ? <Code className="ms-1 text-xs text-muted-foreground">{tr.authorisation_no}</Code> : null}
                    </li>
                  ))}
                </ul>
              </FieldItem>
              {x.closed_by ? (
                <FieldItem label={t("closedBy")}>
                  <UserName u={x.closed_by} /> · {x.closed_at ? dateTime(x.closed_at) : ""}
                </FieldItem>
              ) : null}
            </FieldList>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("days")}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col divide-y text-sm" data-testid="session-days">
              {x.days.map((d) => (
                <li key={d.day_no} className="flex flex-wrap justify-between gap-2 py-1.5">
                  <span>
                    {t("dayNo", { n: d.day_no })} · <span className="ltr">{date(d.date)}</span>
                  </span>
                  <span className="ltr tabular-nums text-muted-foreground">
                    {d.start_time.slice(0, 5)}–{d.end_time.slice(0, 5)} · {t("netMin", { n: d.net_minutes })}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-muted-foreground">{t("totalNetShort", { n: x.net_minutes_total })}</p>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs" data-testid="session-counts">
              {(["attended", "partial", "absent", "passed", "failed", "incomplete"] as const).map((k) => (
                <div key={k} className="rounded border p-1.5" data-k={k}>
                  <span className="block text-base font-semibold tabular-nums">{x.counts[k]}</span>
                  {k === "attended" || k === "partial" || k === "absent" ? te(`nominationStatus.${k}`) : te(`attendanceResult.${k}`)}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
      <AttendanceRegister session={x} project={project} course={course.data ?? null} />
      <HistoryPanel entityType="training_session" entityId={x.id} projectId={project.id} />
      {step === "schedule" || step === "record_delivered" || step === "cancel" ? (
        <StepDialog
          title={t("confirm", { action: te(`sessionAction.${step}`) })}
          description={step === "schedule" ? t("scheduleHint") : step === "record_delivered" ? t("recordDeliveredHint") : t("cancelHint")}
          confirmLabel={te(`sessionAction.${step}`)}
          destructive={step === "cancel"}
          dismissLabel={step === "cancel" ? t("keep") : undefined}
          disabled={step === "cancel" && reason.trim().length < 5}
          onClose={() => {
            setStep(null);
            setReason("");
          }}
          onConfirm={() => transition(step)}
          testId="session-confirm"
        >
          {step === "cancel" ? (
            <FormField id="ss-cancel-reason" label={tc("reason")} required>
              <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} data-testid="ss-cancel-reason" />
            </FormField>
          ) : null}
        </StepDialog>
      ) : null}
      {step === "close" ? (
        <StepDialog
          title={t("closeTitle")}
          description={t("closeHint")}
          confirmLabel={t("close")}
          onClose={() => setStep(null)}
          onConfirm={async () => {
            await unwrap(api.POST("/api/v1/training-sessions/{session_id}/close", { params: { path: { session_id: x.id } }, body: { attendance_sheet_attachment_id: sheet } }));
            await refresh();
            toast.success(t("closed"));
          }}
          testId="session-close-confirm"
          wide
        >
          <UploadField id="ss-sheet" label={t("attendanceSheet")} ownerType="training_attendance_sheet" ownerId={x.id} accept="application/pdf,image/jpeg" value={sheet} onChange={(v) => setSheet(v)} hint={t("sheetHint")} />
        </StepDialog>
      ) : null}
      {step === "void" ? (
        <StepDialog
          title={t("voidTitle")}
          description={t("voidHint")}
          confirmLabel={t("void")}
          destructive
          disabled={reason.trim().length < 20}
          onClose={() => {
            setStep(null);
            setReason("");
          }}
          onConfirm={async () => {
            await unwrap(api.POST("/api/v1/training-sessions/{session_id}/void", { params: { path: { session_id: x.id } }, body: { reason_code: voidCode, reason_text: reason.trim() } }));
            await refresh();
          }}
          testId="session-void-confirm"
        >
          <FormField id="ss-void-code" label={t("voidReason")} required>
            <Select value={voidCode} onChange={(e) => setVoidCode(e.target.value as S["SessionVoidReason"])} data-testid="ss-void-code">
              {SESSION_VOID_REASONS.map((r) => (
                <option key={r} value={r}>
                  {te(`sessionVoidReason.${r}`)}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField id="ss-void-text" label={t("voidDetails")} required hint={t("reason20")}>
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="ss-void-text" />
          </FormField>
        </StepDialog>
      ) : null}
    </div>
  );
}

/* ───────────── attendance register (mobile first: one card per attendee) ───────────── */

type Local = { status: S["NominationStatus"]; minutes: Record<number, string>; theory: string; practical: S["PracticalResult"] | "" };

function toLocal(n: S["NominationRead"]): Local {
  return {
    status: n.status,
    minutes: Object.fromEntries(Object.entries(n.minutes_by_day ?? {}).map(([k, v]) => [Number(k), String(v)])),
    theory: n.theory_score_pct ?? "",
    practical: n.practical_result ?? "",
  };
}

async function uploadSignature(nominationId: string, b64: string) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const form = new FormData();
  form.set("owner_type", "training_attendance_signature");
  form.set("owner_id", nominationId);
  form.set("file", new Blob([bytes], { type: "image/png" }), "signature.png");
  const a = await postForm<S["AttachmentRead"]>("/api/v1/attachments", form);
  return unwrap(api.POST("/api/v1/training-nominations/{nomination_id}/signature", { params: { path: { nomination_id: nominationId } }, body: { signature_attachment_id: a.id } }));
}

const ATT_STATUSES: S["NominationStatus"][] = ["attended", "partial", "absent"];

function AttendanceRegister({ session, project, course }: { session: S["SessionRead"]; project: S["ProjectRead"]; course: S["CourseRead"] | null }) {
  const t = useTranslations("training.sessions");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useTrainingCaps(project.id);
  const codeText = useCodeText();
  const q = useNominations(session.id);
  const refresh = useTrainingRefresh();
  const qc = useQueryClient();
  const items = useMemo(() => q.data?.items ?? [], [q.data]);
  const [local, setLocal] = useState<Record<string, Local>>({});
  const [dirty, setDirty] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [nominate, setNominate] = useState(false);
  const [sign, setSign] = useState<S["NominationRead"] | null>(null);
  const [withdraw, setWithdraw] = useState<S["NominationRead"] | null>(null);
  // Reset the editable copy whenever the server list changes (render-time adjustment, no effect).
  const [seen, setSeen] = useState<typeof items | null>(null);
  if (seen !== items) {
    setSeen(items);
    setLocal(Object.fromEntries(items.map((n) => [n.id, toLocal(n)])));
    setDirty(new Set());
  }
  const live = session.status === "in_progress" || session.status === "delivered" || session.status === "scheduled";
  const canRecord = caps.attendance && live;
  const today = todayInZone();
  const reachedDays = session.days.filter((d) => d.date <= today);
  const theory = course?.theory_required ?? false;
  const practical = course?.practical_required ?? false;
  const scoresVisible = items.some((n) => n.theory_score_pct !== null || n.practical_result !== null) || caps.attendance;
  function patch(id: string, p: Partial<Local>) {
    setLocal((l) => ({ ...l, [id]: { ...(l[id] as Local), ...p } }));
    setDirty((d) => new Set(d).add(id));
  }
  function allPresent() {
    const next: Record<string, Local> = { ...local };
    const changed = new Set(dirty);
    for (const n of items) {
      if (n.status === "withdrawn") continue;
      next[n.id] = { ...(next[n.id] as Local), status: "attended", minutes: Object.fromEntries(reachedDays.map((d) => [d.day_no, String(d.net_minutes)])) };
      changed.add(n.id);
    }
    setLocal(next);
    setDirty(changed);
  }
  async function saveAttendance() {
    setBusy(true);
    setError(null);
    try {
      const entries = items
        .filter((n) => dirty.has(n.id) && n.status !== "withdrawn")
        .map((n) => {
          const l = local[n.id] as Local;
          const minutes = Object.fromEntries(Object.entries(l.minutes).filter(([, v]) => v !== "").map(([k, v]) => [k, Number(v)]));
          return { nomination_id: n.id, status: l.status, minutes_by_day: l.status === "absent" ? {} : minutes };
        });
      if (entries.length) {
        const r = await unwrap(api.PUT("/api/v1/training-sessions/{session_id}/attendance", { params: { path: { session_id: session.id } }, body: { entries } }));
        qc.setQueryData(tk.nominations(session.id), r);
      }
      const assess = items
        .filter((n) => dirty.has(n.id) && (theory || practical))
        .map((n) => {
          const l = local[n.id] as Local;
          return { nomination_id: n.id, theory_score_pct: theory && l.theory !== "" ? l.theory : null, practical_result: practical && l.practical ? l.practical : null };
        })
        .filter((e) => e.theory_score_pct !== null || e.practical_result !== null);
      if (assess.length) {
        const r = await unwrap(api.PUT("/api/v1/training-sessions/{session_id}/assessments", { params: { path: { session_id: session.id } }, body: { entries: assess } }));
        qc.setQueryData(tk.nominations(session.id), r);
      }
      await refresh();
      toast.success(t("attendanceSaved"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="flex flex-col gap-3" data-testid="attendance-register" aria-labelledby="att-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="att-title" className="text-lg font-semibold">
          {t("attendees")} <span className="text-sm font-normal text-muted-foreground tabular-nums">({items.filter((n) => n.status !== "withdrawn").length})</span>
        </h2>
        <div className="flex flex-wrap gap-2">
          {session.allowed_actions.includes("nominate") && caps.nominate ? (
            <Button variant="outline" onClick={() => setNominate(true)} data-testid="nominate">
              <UserPlus aria-hidden />
              {t("nominate")}
            </Button>
          ) : null}
          {canRecord && items.length ? (
            <Button variant="outline" onClick={allPresent} data-testid="all-present">
              <CheckCheck aria-hidden />
              {t("allPresent")}
            </Button>
          ) : null}
        </div>
      </div>
      {q.isLoading ? (
        <LoadingState rows={3} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <ApiWarnings warnings={q.data?.warnings ?? []} />
          <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {items.map((n) => {
              const l = local[n.id] ?? toLocal(n);
              const withdrawn = n.status === "withdrawn";
              return (
                <li key={n.id} className={cn("flex flex-col gap-3 rounded-xl border bg-surface p-3 shadow-xs", withdrawn && "opacity-60", dirty.has(n.id) && "border-primary")} data-testid="attendee" data-worker={n.worker.worker_no} data-status={n.status} data-result={n.result}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <WorkerLabel w={n.worker} link />
                      <span className="block text-xs text-muted-foreground">
                        {n.engagement?.short_code ?? ""}
                        {n.worker_language ? ` · ${te(`workerLanguage.${n.worker_language}`)}` : ""}
                        {n.attempt_no > 1 ? ` · ${t("attempt", { n: n.attempt_no })}` : ""}
                      </span>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <NominationBadge status={n.status} />
                      <ResultBadge result={n.result} />
                    </div>
                  </div>
                  {n.understood_language !== "session_language" ? (
                    <Badge tone={n.understood_language === "none" ? "warning" : "info"} data-testid="understood" data-understood={n.understood_language}>
                      {te(`understoodLanguage.${n.understood_language}`)}
                    </Badge>
                  ) : null}
                  {n.result_reason ? <p className="text-xs text-destructive">{codeText(n.result_reason)}</p> : null}
                  {n.warnings.length ? <ApiWarnings warnings={n.warnings} /> : null}
                  {canRecord && !withdrawn ? (
                    <>
                      <div role="radiogroup" aria-label={t("attendance")} className="grid grid-cols-3 gap-1">
                        {ATT_STATUSES.map((st) => (
                          <button
                            key={st}
                            type="button"
                            role="radio"
                            aria-checked={l.status === st}
                            onClick={() =>
                              patch(n.id, {
                                status: st,
                                minutes: st === "attended" && !Object.keys(l.minutes).length ? Object.fromEntries(reachedDays.map((d) => [d.day_no, String(d.net_minutes)])) : l.minutes,
                              })
                            }
                            className={cn(
                              "min-h-touch rounded-md border px-2 text-sm font-medium",
                              l.status === st ? (st === "absent" ? "border-destructive bg-danger-bg text-destructive" : st === "partial" ? "border-warning bg-warning-bg" : "border-success bg-success-bg text-success") : "bg-background",
                            )}
                            data-testid={`att-${st}`}
                          >
                            {te(`nominationStatus.${st}`)}
                          </button>
                        ))}
                      </div>
                      {l.status !== "absent" ? (
                        <div className="grid grid-cols-2 gap-2">
                          {session.days.map((d) => (
                            <FormField key={d.day_no} id={`att-${n.id}-${d.day_no}`} label={t("minutesDay", { n: d.day_no, max: d.net_minutes })}>
                              <Input
                                type="number"
                                inputMode="numeric"
                                min={0}
                                max={d.net_minutes}
                                className="ltr"
                                value={l.minutes[d.day_no] ?? ""}
                                onChange={(e) => patch(n.id, { minutes: { ...l.minutes, [d.day_no]: e.target.value } })}
                                data-testid={`att-min-${d.day_no}`}
                              />
                            </FormField>
                          ))}
                        </div>
                      ) : null}
                      {(theory || practical) && scoresVisible ? (
                        <div className="grid grid-cols-2 gap-2">
                          {theory ? (
                            <FormField id={`th-${n.id}`} label={t("theoryScore", { pct: course?.effective_pass_mark_pct ?? course?.pass_mark_pct ?? "—" })}>
                              <Input type="number" inputMode="decimal" step="0.01" min={0} max={100} className="ltr" value={l.theory} onChange={(e) => patch(n.id, { theory: e.target.value })} data-testid="att-theory" />
                            </FormField>
                          ) : null}
                          {practical ? (
                            <FormField id={`pr-${n.id}`} label={t("practical")}>
                              <Select value={l.practical} onChange={(e) => patch(n.id, { practical: e.target.value as S["PracticalResult"] | "" })} data-testid="att-practical">
                                <option value="">—</option>
                                <option value="pass">{t("pass")}</option>
                                <option value="fail">{t("fail")}</option>
                              </Select>
                            </FormField>
                          ) : null}
                        </div>
                      ) : null}
                    </>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      <Hours v={n.attended_hours} />
                      {n.theory_score_pct !== null ? ` · ${t("scoreValue", { pct: n.theory_score_pct })}` : ""}
                      {n.practical_result ? ` · ${n.practical_result === "pass" ? t("pass") : t("fail")}` : ""}
                    </p>
                  )}
                  <div className="flex flex-wrap items-center gap-2">
                    {n.signed_on_device ? (
                      <Badge tone="success" data-testid="signed">
                        <PenLine aria-hidden />
                        {t("signedOnDevice")}
                      </Badge>
                    ) : canRecord && !withdrawn && n.status !== "absent" && n.status !== "nominated" ? (
                      <Button size="sm" variant="outline" onClick={() => setSign(n)} data-testid="sign">
                        <PenLine aria-hidden />
                        {t("signOnDevice")}
                      </Button>
                    ) : null}
                    {n.record ? (
                      <Link href={`/training-records/${n.record.id}`} className="text-xs text-primary hover:underline" data-testid="attendee-record">
                        <Code>{n.record.record_no}</Code>
                      </Link>
                    ) : null}
                    {caps.nominate && n.status === "nominated" && (session.status === "draft" || session.status === "scheduled") ? (
                      <Button size="sm" variant="ghost" className="ms-auto" onClick={() => setWithdraw(n)} data-testid="withdraw-nominee">
                        <UserMinus aria-hidden />
                        {t("withdraw")}
                      </Button>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
          {canRecord ? (
            <div className="sticky bottom-2 z-10 flex flex-col gap-2 rounded-xl border bg-surface/95 p-2 shadow-md backdrop-blur sm:static sm:border-0 sm:bg-transparent sm:p-0 sm:shadow-none">
              <MutationError error={error} />
              <Button onClick={() => void saveAttendance()} disabled={!dirty.size || busy} className="w-full sm:w-auto" data-testid="save-attendance">
                <Save aria-hidden />
                {busy ? tc("saving") : t("saveAttendance", { n: dirty.size })}
              </Button>
            </div>
          ) : null}
        </>
      ) : (
        <EmptyState message={t("noAttendees")} />
      )}
      {nominate ? <NominateDialog session={session} project={project} onClose={() => setNominate(false)} /> : null}
      {sign ? <SignDialog n={sign} onClose={() => setSign(null)} /> : null}
      {withdraw ? (
        <StepDialog
          title={t("withdrawTitle")}
          confirmLabel={t("withdraw")}
          destructive
          onClose={() => setWithdraw(null)}
          onConfirm={async () => {
            await unwrap(api.POST("/api/v1/training-nominations/{nomination_id}/withdraw", { params: { path: { nomination_id: withdraw.id } }, body: { reason: null } }));
            await refresh();
          }}
          testId="withdraw-nominee-confirm"
        >
          <p className="text-sm">
            <WorkerLabel w={withdraw.worker} />
          </p>
        </StepDialog>
      ) : null}
    </section>
  );
}

function SignDialog({ n, onClose }: { n: S["NominationRead"]; onClose: () => void }) {
  const t = useTranslations("training.sessions");
  const refresh = useTrainingRefresh();
  const [sig, setSig] = useState<string | null>(null);
  return (
    <StepDialog
      title={t("signTitle")}
      description={t("signHint")}
      confirmLabel={t("confirmSignature")}
      disabled={!sig}
      onClose={onClose}
      onConfirm={async () => {
        await uploadSignature(n.id, sig as string);
        await refresh();
      }}
      testId="sign-confirm"
    >
      <p className="text-sm">
        <WorkerLabel w={n.worker} />
      </p>
      <SignaturePad id="att-signature" label={t("signature")} onChange={setSig} />
    </StepDialog>
  );
}

type MetaError = { worker_id?: string; code?: string; course_code?: string | null };

function NominateDialog({ session, project, onClose }: { session: S["SessionRead"]; project: S["ProjectRead"]; onClose: () => void }) {
  const t = useTranslations("training.sessions");
  const tc = useTranslations("common");
  const codeText = useCodeText();
  const refresh = useTrainingRefresh();
  const [dep, setDep] = useState<S["DeploymentRead"] | null>(null);
  const [picked, setPicked] = useState<S["DeploymentRead"][]>([]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const free = session.capacity - session.counts.nominated + session.counts.withdrawn;
  const metaErrors: MetaError[] = error instanceof ApiError && Array.isArray(error.meta.errors) ? (error.meta.errors as MetaError[]) : [];
  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const r = await unwrap(api.POST("/api/v1/training-sessions/{session_id}/nominations", { params: { path: { session_id: session.id } }, body: { worker_ids: picked.map((d) => d.worker_id) } }));
      await refresh();
      toast.success(t("nominated", { n: picked.length }));
      if (r.warnings?.length) toast.warning(r.warnings.map((w) => w.message).join(" · "));
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open onOpenChange={(o) => (!o ? onClose() : undefined)}>
      <DialogContent closeLabel={tc("close")} className="max-w-xl" data-testid="nominate-dialog">
        <DialogHeader>
          <DialogTitle>{t("nominateTitle", { no: session.session_no })}</DialogTitle>
          <DialogDescription>{t("nominateHint", { n: Math.max(free, 0) })}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <div className="flex-1">
            <DeploymentPicker id="nom-worker" projectId={project.id} value={dep} onChange={setDep} label={t("worker")} status={["mobilised", "pending_induction"]} />
          </div>
          <Button
            variant="outline"
            disabled={!dep || picked.some((p) => p.id === dep.id)}
            onClick={() => {
              if (dep) setPicked([...picked, dep]);
              setDep(null);
            }}
            data-testid="nom-add"
          >
            <Plus aria-hidden />
            {t("add")}
          </Button>
        </div>
        {picked.length ? (
          <ul className="flex flex-col divide-y rounded-md border text-sm" data-testid="nom-picked">
            {picked.map((d) => {
              const errs = metaErrors.filter((e) => e.worker_id === d.worker_id);
              return (
                <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 p-2" data-worker={d.worker_no}>
                  <span>
                    <WorkerLabel w={{ id: d.worker_id, worker_no: d.worker_no, full_name_en: d.full_name_en, full_name_ar: d.full_name_ar }} />
                    {errs.map((e, i) => (
                      <span key={i} className="block text-xs text-destructive" data-testid="nom-error" data-code={e.code}>
                        {codeText(e.code)}
                        {e.course_code ? ` (${e.course_code})` : ""}
                      </span>
                    ))}
                  </span>
                  <Button size="sm" variant="ghost" onClick={() => setPicked(picked.filter((p) => p.id !== d.id))}>
                    <Trash2 aria-hidden />
                    <span className="sr-only">{tc("remove")}</span>
                  </Button>
                </li>
              );
            })}
          </ul>
        ) : null}
        <MutationError error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button onClick={() => void submit()} disabled={!picked.length || busy} data-testid="nom-submit">
            {busy ? tc("saving") : t("nominateN", { n: picked.length })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
