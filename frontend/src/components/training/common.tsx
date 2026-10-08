"use client";
import { Archive, CalendarClock, CircleCheck, CircleX, Clock, OctagonX } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { FormField } from "@/components/common/form-field";
import { StatusBadge } from "@/components/common/status-badge";
import { Code, DaysLeft, SubNav } from "@/components/access/common";
import { CertStatePanel } from "@/components/cert/common";
import { useMeData } from "@/components/shell/me-context";
import type { Schemas } from "@/lib/api/client";
import { useTrainingCourses, useTrainingProviders } from "@/lib/api/training";
import { can, canWrite } from "@/lib/permissions";
import { useFormatters } from "@/lib/use-formatters";

type S = Schemas;

/* ───────────── capabilities ───────────── */

/** Phase 5 capabilities (spec §5.15, 125–145) for the current project. */
export function useTrainingCaps(projectId?: string | null) {
  const me = useMeData();
  const pid = projectId ?? null;
  return {
    view: can(me, "training_catalogue.view", pid),
    courseEdit: canWrite(me, "training_course.edit", pid),
    providerEdit: canWrite(me, "training_provider.edit", pid),
    providerDecide: canWrite(me, "training_provider.decide", pid),
    matrixEdit: canWrite(me, "training_matrix.edit", pid),
    profileEdit: canWrite(me, "training_profile.edit", pid),
    authorise: canWrite(me, "trainer.authorise", pid),
    sessionManage: canWrite(me, "training_session.manage", pid),
    nominate: canWrite(me, "training.nominate", pid),
    attendance: canWrite(me, "training_attendance.record", pid),
    close: canWrite(me, "training_session.close", pid),
    recordView: can(me, "training_record.view", pid),
    recordSubmit: canWrite(me, "training_record.submit", pid),
    recordReview: canWrite(me, "training_record.review", pid),
    scan: can(me, "training_scan.view", pid),
    recordSuspend: canWrite(me, "training_record.suspend", pid),
    import: canWrite(me, "training.import", pid),
    check: can(me, "training.check", pid),
    kpi: can(me, "training_kpi.view", pid),
    export: can(me, "export.training", pid),
    settings: canWrite(me, "training_settings.edit", pid),
    names: can(me, "worker.view", pid),
    manager: me.is_hse_manager,
  };
}

/* ───────────── sub navigation ───────────── */

export function TrainingCatalogueSubNav() {
  const t = useTranslations("training.nav");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/training-courses", label: t("courses"), testId: "sub-tr-courses" },
        { href: "/training-providers", label: t("providers"), testId: "sub-tr-providers" },
        { href: "/trainer-authorisations", label: t("trainers"), show: can(me, "training_catalogue.view"), testId: "sub-tr-trainers" },
      ]}
    />
  );
}

export function TrainingMatrixSubNav() {
  const t = useTranslations("training.nav");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/training-matrix", label: t("matrix"), testId: "sub-tr-matrix" },
        { href: "/training-gaps", label: t("gaps"), show: can(me, "training_record.view") || can(me, "training_kpi.view"), testId: "sub-tr-gaps" },
        { href: "/refresher-plan", label: t("plan"), show: can(me, "training_kpi.view"), testId: "sub-tr-plan" },
        { href: "/training-exemptions", label: t("exemptions"), show: can(me, "training_record.view") || can(me, "training_matrix.edit"), testId: "sub-tr-exemptions" },
      ]}
    />
  );
}

export function TrainingRecordsSubNav() {
  const t = useTranslations("training.nav");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/training-records", label: t("records"), testId: "sub-tr-records" },
        { href: "/training-verification-log", label: t("verificationLog"), show: can(me, "training_record.review"), testId: "sub-tr-verif" },
        { href: "/training-imports", label: t("imports"), show: can(me, "training.import"), testId: "sub-tr-imports" },
      ]}
    />
  );
}

/* ───────────── badges ───────────── */

export function ProviderStatusBadge({ status }: { status: S["TrainingProviderStatus"] | null | undefined }) {
  const te = useTranslations("enums");
  if (!status) return null;
  return (
    <span data-testid="provider-status" data-status={status}>
      <StatusBadge status={status} label={te(`providerStatus.${status}`)} />
    </span>
  );
}

export function SessionStatusBadge({ status }: { status: S["SessionStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="session-status" data-status={status}>
      <StatusBadge status={status} label={te(`sessionStatus.${status}`)} />
    </span>
  );
}

export function RecordStatusBadge({ status }: { status: S["TrainingRecordStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="record-status" data-status={status}>
      <StatusBadge status={status} label={te(`recordStatus.${status}`)} />
    </span>
  );
}

export function NominationBadge({ status }: { status: S["NominationStatus"] }) {
  const te = useTranslations("enums");
  return <StatusBadge status={status} label={te(`nominationStatus.${status}`)} />;
}

export function ResultBadge({ result }: { result: S["AttendanceResult"] }) {
  const te = useTranslations("enums");
  return <StatusBadge status={result} label={te(`attendanceResult.${result}`)} />;
}

export function RequirementStateBadge({ state }: { state: S["RequirementState"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="req-state" data-state={state}>
      <StatusBadge status={state} label={te(`requirementState.${state}`)} />
    </span>
  );
}

export function PlanStateBadge({ state }: { state: S["RefresherPlanState"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="plan-state" data-state={state}>
      <StatusBadge status={state} label={te(`planState.${state}`)} />
    </span>
  );
}

export function TrainerStatusBadge({ status }: { status: S["TrainerAuthorisationStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="trainer-status" data-status={status}>
      <StatusBadge status={status} label={te(`trainerStatus.${status}`)} />
    </span>
  );
}

export function TrainingVerificationBadge({ status }: { status: S["VerificationStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="verification-status" data-status={status}>
      <StatusBadge status={`verif_${status}`} label={te(`verificationStatus.${status}`)} />
    </span>
  );
}

/* ───────────── labels and pickers ───────────── */

export function CourseLabel({ course, code, nameOnly }: { course?: { code: string; name_en: string; name_ar: string } | null; code?: string; nameOnly?: boolean }) {
  const locale = useLocale();
  const c = course?.code ?? code ?? "";
  const name = course ? (locale === "ar" ? course.name_ar : course.name_en) : null;
  if (nameOnly && name) return <span>{name}</span>;
  return (
    <span>
      <Code className="font-medium">{c}</Code>
      {name ? <span className="ms-1.5">{name}</span> : null}
    </span>
  );
}

/** Course labels from the org catalogue (codes are strings). */
export function useCourseCatalogue(projectId?: string | null, opts: { active?: boolean } = {}) {
  const locale = useLocale();
  const q = useTrainingCourses({ project_id: projectId || null, active: opts.active ?? null });
  const courses = q.data?.items ?? [];
  const label = (code: string) => {
    const x = courses.find((c) => c.code === code);
    return x ? (locale === "ar" ? x.name_ar : x.name_en) : code;
  };
  const get = (code: string) => courses.find((c) => c.code === code);
  return { courses, label, get, isLoading: q.isLoading };
}

export function CourseSelect({
  id,
  label,
  value,
  onChange,
  required,
  projectId,
  filter,
  allowEmpty = true,
  hint,
  disabled,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (code: string, c?: S["CourseRead"]) => void;
  required?: boolean;
  projectId?: string | null;
  filter?: (c: S["CourseRead"]) => boolean;
  allowEmpty?: boolean;
  hint?: string;
  disabled?: boolean;
}) {
  const tc = useTranslations("common");
  const locale = useLocale();
  const { courses } = useCourseCatalogue(projectId, { active: true });
  const list = courses.filter((c) => (filter ? filter(c) : true));
  return (
    <FormField id={id} label={label} required={required} hint={hint}>
      <Select
        value={value}
        disabled={disabled}
        onChange={(e) =>
          onChange(
            e.target.value,
            list.find((c) => c.code === e.target.value),
          )
        }
        data-testid={id}
      >
        {allowEmpty ? <option value="">{tc("select")}</option> : null}
        {list.map((c) => (
          <option key={c.code} value={c.code}>
            {c.code} — {locale === "ar" ? c.name_ar : c.name_en}
          </option>
        ))}
      </Select>
    </FormField>
  );
}

export function ProviderLabel({ p }: { p: { provider_code: string; legal_name_en: string; legal_name_ar: string } | null | undefined }) {
  const locale = useLocale();
  if (!p) return <>—</>;
  return (
    <span>
      <Code className="font-medium">{p.provider_code}</Code>
      <span className="ms-1.5">{locale === "ar" ? p.legal_name_ar : p.legal_name_en}</span>
    </span>
  );
}

export function ProviderSelect({
  id,
  label,
  value,
  onChange,
  required,
  kinds,
  courseCode,
  hint,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (id: string, p?: S["ProviderListItem"]) => void;
  required?: boolean;
  kinds?: S["TrainingProviderKind"][];
  courseCode?: string | null;
  hint?: string;
}) {
  const tc = useTranslations("common");
  const te = useTranslations("enums");
  const locale = useLocale();
  const q = useTrainingProviders({ page_size: 200, kind: kinds?.length ? kinds : null });
  const items = q.data?.items ?? [];
  return (
    <FormField id={id} label={label} required={required} hint={hint}>
      <Select value={value} onChange={(e) => onChange(e.target.value, items.find((p) => p.id === e.target.value))} data-testid={id}>
        <option value="">{tc("select")}</option>
        {items.map((p) => (
          <option key={p.id} value={p.id}>
            {p.provider_code} — {locale === "ar" ? p.legal_name_ar : p.legal_name_en}
            {p.status && p.status !== "approved" ? ` (${te(`providerStatus.${p.status}`)})` : ""}
            {courseCode && p.accredited_course_codes.includes(courseCode) ? " ✓" : ""}
          </option>
        ))}
      </Select>
    </FormField>
  );
}

/* ───────────── validity (server-computed; the UI never computes it) ───────────── */

export function TrainingValidityView({ v, projectId, compact, hideBadge }: { v: S["TrainingValidity"]; projectId?: string | null; compact?: boolean; hideBadge?: boolean }) {
  const t = useTranslations("training.common");
  const te = useTranslations("enums");
  const { date, dateTime } = useFormatters(projectId);
  return (
    <div className="flex flex-col gap-1 text-sm" data-testid="training-validity" data-in-force={v.in_force ? "yes" : "no"} data-valid-until={v.valid_until ?? ""} data-factor={v.limiting_factor}>
      <span className="flex flex-wrap items-center gap-2">
        {hideBadge ? null : v.in_force ? (
          <Badge tone={v.expiring ? "warning" : "success"}>
            <CircleCheck aria-hidden />
            {t("inForce")}
          </Badge>
        ) : (
          <Badge tone="danger">
            <CircleX aria-hidden />
            {t("notInForce")}
          </Badge>
        )}
        {v.valid_until ? (
          <span>
            {t("validUntil")}: <span className="ltr font-medium">{date(v.valid_until)}</span>
          </span>
        ) : (
          <span>{t("noExpiry")}</span>
        )}
        {v.in_force ? <DaysLeft days={v.days_left} /> : null}
      </span>
      {v.limiting_factor !== "none" ? (
        <span className="text-xs text-muted-foreground" data-testid="training-limiting-factor" data-factor={v.limiting_factor}>
          {t("limitedBy", { factor: te(`trainingLimitingFactor.${v.limiting_factor}`) })}
        </span>
      ) : null}
      {!compact && v.stored_valid_until && v.valid_until && v.stored_valid_until !== v.valid_until ? (
        <span className="text-xs text-muted-foreground">{t("projectOverrideNote", { stored: date(v.stored_valid_until) })}</span>
      ) : null}
      {!compact && v.printed_expiry && v.course_end && v.printed_expiry !== v.course_end ? (
        <span className="text-xs text-muted-foreground">{t("printedVsCourse", { printed: date(v.printed_expiry), course: date(v.course_end) })}</span>
      ) : null}
      {!v.in_force && v.not_in_force_reason ? (
        <span className="text-xs font-medium text-destructive" data-testid="not-in-force-reason" data-reason={v.not_in_force_reason}>
          {te(`hookReason.${v.not_in_force_reason}`)}
        </span>
      ) : null}
      {v.unverified_window_until ? <span className="text-xs text-warning">{t("unverifiedWindow", { until: dateTime(v.unverified_window_until) })}</span> : null}
    </div>
  );
}

const PENDING: S["TrainingRecordStatus"][] = ["draft", "submitted"];
const ENDED: S["TrainingRecordStatus"][] = ["superseded", "expired"];

/** One-glance "is this training in force today" panel (Phase 4 state-panel pattern). */
export function TrainingStatePanel({ status, v, projectId, children }: { status: S["TrainingRecordStatus"]; v: S["TrainingValidity"]; projectId?: string | null; children?: ReactNode }) {
  const t = useTranslations("training.common");
  const te = useTranslations("enums");
  const pending = !v.in_force && PENDING.includes(status);
  const ended = !v.in_force && ENDED.includes(status);
  return (
    <CertStatePanel
      tone={v.in_force ? (v.expiring ? "warning" : "success") : pending ? "info" : ended ? "neutral" : "danger"}
      Icon={v.in_force ? (v.expiring ? CalendarClock : CircleCheck) : pending ? Clock : ended ? Archive : OctagonX}
      word={v.in_force ? t("inForce") : t("notInForce")}
      sub={!v.in_force ? te(`recordStatus.${status}`) : undefined}
      line={v.in_force ? t("inForceLine") : pending ? t("pendingLine") : t("notInForceLine")}
      testId="training-state"
      data={{ "data-in-force": v.in_force ? "yes" : "no" }}
    >
      <TrainingValidityView v={v} projectId={projectId} hideBadge />
      {children}
    </CertStatePanel>
  );
}

/** Requirement in words: one code, or "any of" a set. */
export function RequirementText({ r }: { r: { course_code?: string | null; any_of?: string[] | null } }) {
  const t = useTranslations("training.common");
  if (r.any_of?.length)
    return (
      <span>
        {t("anyOf")}{" "}
        {r.any_of.map((c, i) => (
          <span key={c}>
            {i ? " · " : ""}
            <Code>{c}</Code>
          </span>
        ))}
      </span>
    );
  return <Code className="font-medium">{r.course_code ?? "—"}</Code>;
}

/** Decimal hours as returned by the API (string), never recomputed. */
export function Hours({ v }: { v: string | number | null | undefined }) {
  const t = useTranslations("training.common");
  if (v === null || v === undefined || v === "") return <>—</>;
  return <span className="ltr tabular-nums">{t("hours", { h: String(v) })}</span>;
}

/** Server error code in words (errors.code.*), else the code. */
export function useCodeText() {
  const tErr = useTranslations("errors");
  return (c: string | null | undefined) => (c ? (tErr.has(`code.${c}` as never) ? tErr(`code.${c}` as never) : c) : "");
}

/** Date filter for list toolbars (as-of, from, to). */
export function DateFilter({ id, label, value, onChange }: { id: string; label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-col gap-1.5 lg:w-44">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} type="date" className="ltr" value={value} onChange={(e) => onChange(e.target.value)} data-testid={id} />
    </div>
  );
}

/** URL flag: dashboard / action-panel links carry `true`, the filter bar writes `1`. */
export function isOn(v: string | null | undefined): boolean {
  return v === "1" || v === "true";
}
