"use client";
import { FileText, NotebookPen, Pencil, Printer } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { FormField } from "@/components/common/form-field";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { useProjectOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { Code, StepDialog, WorkerLabel } from "@/components/access/common";
import { UserName } from "@/components/cert/common";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useTrainingPassport, useTrainingProfile, useTrainingRefresh, useTrainingReport, useTrainingRequirements } from "@/lib/api/training";
import { useCurrentProject } from "@/lib/current-project";
import { MATRIX_ROLES } from "@/lib/train-enums";
import { useFormatters } from "@/lib/use-formatters";
import { CourseSelect, Hours, RecordStatusBadge, RequirementStateBadge, RequirementText, useCodeText, useTrainingCaps } from "./common";

type S = Schemas;
type Req = S["app__schemas__training_matrix__RequirementStatus"];

/** Requirements of one deployment (matrix × records), as the server evaluates them. */
export function RequirementsTable({ items, projectId }: { items: Req[]; projectId: string | null }) {
  const t = useTranslations("training.passport");
  const te = useTranslations("enums");
  const codeText = useCodeText();
  const { date } = useFormatters(projectId);
  if (!items.length) return <EmptyState message={t("noRequirements")} />;
  return (
    <Table data-testid="requirements-table">
      <THead>
        <TR>
          <TH>{t("requirement")}</TH>
          <TH>{t("due")}</TH>
          <TH>{t("state")}</TH>
          <TH>{t("satisfiedBy")}</TH>
        </TR>
      </THead>
      <TBody>
        {items.map((r, i) => (
          <TR key={i} data-testid="requirement-row" data-course={r.requirement.course_code ?? r.requirement.any_of?.join("|") ?? ""} data-state={r.state}>
            <TD label={t("requirement")}>
              <RequirementText r={r.requirement} />
              <span className="ms-1 inline-flex flex-wrap gap-1">
                {r.critical ? <Badge tone="danger">{t("critical")}</Badge> : r.hook_code ? <Badge tone="info">{t("hook")}</Badge> : null}
                {r.level === "recommended" ? <Badge tone="neutral">{te("matrixLevel.recommended")}</Badge> : null}
                {!r.kpi_counted ? <Badge tone="neutral">{t("enforcementOnly")}</Badge> : null}
              </span>
              <span className="block text-xs text-muted-foreground">{r.line_nos.join(", ")}</span>
            </TD>
            <TD label={t("due")}>
              <span className="ltr">{date(r.due_date)}</span>
            </TD>
            <TD label={t("state")}>
              <RequirementStateBadge state={r.state} />
              {r.not_met_reason ? <span className="block text-xs text-destructive">{te.has(`hookReason.${r.not_met_reason as S["HookReasonCode"]}`) ? te(`hookReason.${r.not_met_reason as S["HookReasonCode"]}`) : codeText(r.not_met_reason)}</span> : null}
            </TD>
            <TD label={t("satisfiedBy")}>
              {r.satisfied_by_record ? (
                <Link href={`/training-records/${r.satisfied_by_record.id}`} className="text-primary hover:underline">
                  <Code>{r.satisfied_by_record.record_no}</Code>
                  <span className="ms-1 text-xs">({r.satisfied_by_record.course_code})</span>
                </Link>
              ) : r.satisfied_by_induction_no ? (
                <Code>{r.satisfied_by_induction_no}</Code>
              ) : r.booked_session ? (
                <Link href={`/training-sessions/${r.booked_session.id}`} className="text-xs text-primary hover:underline">
                  {t("booked")} <Code>{r.booked_session.session_no}</Code>
                </Link>
              ) : (
                "—"
              )}
              {r.valid_until ? <span className="block text-xs text-muted-foreground">{t("validUntil", { date: date(r.valid_until) })}</span> : null}
            </TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}

/* ───────────── worker detail: training passport card ───────────── */

export function WorkerTrainingPanel({ workerId, projectId, deploymentId }: { workerId: string; projectId: string; deploymentId: string | null }) {
  const t = useTranslations("training.passport");
  const te = useTranslations("enums");
  const locale = useLocale();
  const caps = useTrainingCaps(projectId);
  const { date } = useFormatters(projectId);
  const q = useTrainingPassport(workerId, projectId);
  const [note, setNote] = useState(false);
  const d = q.data;
  return (
    <Card data-testid="training-passport">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">{t("title")}</CardTitle>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" asChild>
            <Link href={`/workers/${workerId}/training`} data-testid="open-passport">
              <Printer aria-hidden />
              {t("printPassport")}
            </Link>
          </Button>
          {caps.manager && caps.export ? (
            <Button size="sm" variant="outline" asChild>
              <Link href={`/workers/${workerId}/training-report`} data-testid="open-dsr">
                <FileText aria-hidden />
                {t("dataSubjectReport")}
              </Link>
            </Button>
          ) : null}
          {caps.matrixEdit ? (
            <Button size="sm" variant="outline" onClick={() => setNote(true)} data-testid="retraining-note">
              <NotebookPen aria-hidden />
              {t("retrainingNote")}
            </Button>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {q.isLoading ? (
          <LoadingState rows={2} />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : d ? (
          <>
            <section className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold">{t("onThisProject")}</h3>
              <RequirementsTable items={d.requirements} projectId={projectId} />
            </section>
            <section className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold">{t("records")}</h3>
              {d.entries.length ? (
                <ul className="flex flex-col divide-y" data-testid="passport-entries">
                  {d.entries.map((e) => (
                    <li key={e.record_id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm" data-testid="passport-entry" data-course={e.course.code} data-in-force={e.in_force ? "yes" : "no"}>
                      <span>
                        <Code className="font-medium">{e.course.code}</Code> {locale === "ar" ? e.course.name_ar : e.course.name_en}
                        <span className="block text-xs text-muted-foreground">
                          <Link href={`/training-records/${e.record_id}`} className="hover:underline">
                            <Code>{e.record_no}</Code>
                          </Link>{" "}
                          · <Code>{e.provider_code}</Code> · {te(`recordSource.${e.source}`)} · <span className="ltr">{date(e.completed_on)}</span>
                        </span>
                      </span>
                      <span className="flex items-center gap-2">
                        {e.valid_until ? <span className="ltr text-xs">{date(e.valid_until)}</span> : null}
                        {e.in_force ? <Badge tone="success">{t("inForce")}</Badge> : <RecordStatusBadge status={e.status} />}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">{t("noRecords")}</p>
              )}
            </section>
          </>
        ) : null}
        {deploymentId ? <ProfileSection deploymentId={deploymentId} projectId={projectId} /> : null}
      </CardContent>
      {note ? <RetrainingNoteDialog workerId={workerId} projectId={projectId} onClose={() => setNote(false)} /> : null}
    </Card>
  );
}

function ProfileSection({ deploymentId, projectId }: { deploymentId: string; projectId: string }) {
  const t = useTranslations("training.passport");
  const te = useTranslations("enums");
  const caps = useTrainingCaps(projectId);
  const { date } = useFormatters(projectId);
  const q = useTrainingProfile(deploymentId);
  const [edit, setEdit] = useState(false);
  if (q.isError) return null;
  const p = q.data;
  if (!p) return null;
  return (
    <section className="flex flex-col gap-2 border-t pt-3" data-testid="training-profile">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{t("profile")}</h3>
        {caps.profileEdit ? (
          <Button size="sm" variant="outline" onClick={() => setEdit(true)} data-testid="edit-profile">
            <Pencil aria-hidden />
            {t("editProfile")}
          </Button>
        ) : null}
      </div>
      <p className="text-sm">
        <span className="text-muted-foreground">{te("profileField.matrix_roles")}:</span> <span data-testid="profile-roles">{p.matrix_roles.length ? p.matrix_roles.map((r) => te(`matrixRole.${r}`)).join(", ") : "—"}</span>
      </p>
      <p className="text-sm">
        <span className="text-muted-foreground">{te("profileField.work_zone_ids")}:</span> {p.work_zones.length ? p.work_zones.map((z) => z.code).join(", ") : "—"}
      </p>
      {p.history.length ? (
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer">{t("profileHistory")}</summary>
          <ul className="mt-1 flex flex-col gap-0.5">
            {p.history.map((h, i) => (
              <li key={i}>
                {te(`profileField.${h.field}`)}: {h.value.join(", ") || "—"} · <span className="ltr">{date(h.from_date)}</span>
                {h.to_date ? (
                  <>
                    {" – "}
                    <span className="ltr">{date(h.to_date)}</span>
                  </>
                ) : null}
                {h.by ? (
                  <>
                    {" · "}
                    <UserName u={h.by} />
                  </>
                ) : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      {edit ? <ProfileDialog p={p} onClose={() => setEdit(false)} /> : null}
    </section>
  );
}

function ProfileDialog({ p, onClose }: { p: S["TrainingProfileRead"]; onClose: () => void }) {
  const t = useTranslations("training.passport");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const refresh = useTrainingRefresh();
  const opts = useProjectOptions(p.project_id);
  const [roles, setRoles] = useState<S["MatrixRole"][]>(p.matrix_roles);
  const [zones, setZones] = useState<string[]>(p.work_zones.map((z) => z.id));
  return (
    <StepDialog
      title={t("editProfile")}
      description={t("profileHint")}
      confirmLabel={tc("save")}
      onClose={onClose}
      onConfirm={async () => {
        await unwrap(api.PATCH("/api/v1/deployments/{deployment_id}/training-profile", { params: { path: { deployment_id: p.deployment_id } }, body: { matrix_roles: roles, work_zone_ids: zones } }));
        await refresh();
        toast.success(tc("saved"));
      }}
      testId="save-profile"
    >
      <CheckboxGroup id="pf-roles" legend={te("profileField.matrix_roles")} options={MATRIX_ROLES.map((r) => ({ value: r, label: te(`matrixRole.${r}`) }))} value={roles} onChange={setRoles} />
      <MultiSelect id="pf-zones" label={te("profileField.work_zone_ids")} allLabel={t("noZones")} options={opts.zones.map((z) => ({ value: z.value, label: z.label }))} value={zones} onChange={setZones} testId="pf-zones" />
    </StepDialog>
  );
}

/** AT-5: a re-training note lets a worker be nominated again after too many failed attempts. */
function RetrainingNoteDialog({ workerId, projectId, onClose }: { workerId: string; projectId: string; onClose: () => void }) {
  const t = useTranslations("training.passport");
  const refresh = useTrainingRefresh();
  const [course, setCourse] = useState("");
  const [note, setNote] = useState("");
  return (
    <StepDialog
      title={t("retrainingNote")}
      description={t("retrainingHint")}
      confirmLabel={t("saveNote")}
      disabled={!course || note.trim().length < 10}
      onClose={onClose}
      onConfirm={async () => {
        await unwrap(api.POST("/api/v1/workers/{worker_id}/training-retraining-notes", { params: { path: { worker_id: workerId } }, body: { project_id: projectId, course_code: course, note: note.trim() } }));
        await refresh();
        toast.success(t("noteSaved"));
      }}
      testId="retraining-note-confirm"
    >
      <CourseSelect id="rn-course" label={t("course")} value={course} onChange={(v) => setCourse(v)} required projectId={projectId} />
      <FormField id="rn-note" label={t("note")} required hint={t("noteHint")}>
        <Textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} data-testid="rn-note" />
      </FormField>
    </StepDialog>
  );
}

/* ───────────── printable passport ───────────── */

export function TrainingPassportPage({ id }: { id: string }) {
  const t = useTranslations("training.passport");
  const tc = useTranslations("common");
  const te = useTranslations("enums");
  const locale = useLocale();
  const { project } = useCurrentProject();
  const { date } = useFormatters(project?.id);
  const q = useTrainingPassport(id, project?.id ?? "");
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const d = q.data;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2 print:hidden">
        <Breadcrumbs items={[{ label: d.worker.worker_no, href: `/workers/${id}` }, { label: t("title") }]} />
        <Button onClick={() => window.print()} data-testid="do-print">
          <Printer aria-hidden />
          {tc("print")}
        </Button>
      </div>
      <div className="paper flex flex-col gap-4 bg-surface p-4 print:bg-white print:p-0" data-testid="passport-print">
        <PageHeader title={t("passportTitle")} description={t("passportAsOf", { date: date(d.as_of) })} />
        <p className="text-base">
          <WorkerLabel w={d.worker} />
        </p>
        <h2 className="text-sm font-semibold">{t("records")}</h2>
        {d.entries.length ? (
          <Table>
            <THead>
              <TR>
                <TH>{t("course")}</TH>
                <TH>{t("recordNo")}</TH>
                <TH>{t("completedOn")}</TH>
                <TH>{t("validUntilH")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {d.entries.map((e) => (
                <TR key={e.record_id}>
                  <TD label={t("course")}>
                    <Code className="font-medium">{e.course.code}</Code> {locale === "ar" ? e.course.name_ar : e.course.name_en}
                  </TD>
                  <TD label={t("recordNo")}>
                    <Code>{e.record_no}</Code> · <Code>{e.provider_code}</Code>
                  </TD>
                  <TD label={t("completedOn")}>{date(e.completed_on)}</TD>
                  <TD label={t("validUntilH")}>{e.valid_until ? date(e.valid_until) : "—"}</TD>
                  <TD label={tc("status")}>{e.in_force ? <Badge tone="success">{t("inForce")}</Badge> : te(`recordStatus.${e.status}`)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        ) : (
          <p className="text-sm text-muted-foreground">{t("noRecords")}</p>
        )}
        {d.requirements.length ? (
          <>
            <h2 className="text-sm font-semibold">{t("onThisProject")}</h2>
            <RequirementsTable items={d.requirements} projectId={project?.id ?? null} />
          </>
        ) : null}
        <p className="text-xs text-muted-foreground">{t("passportNote")}</p>
      </div>
    </div>
  );
}

/* ───────────── data-subject report (P5-9) ───────────── */

export function TrainingReportPage({ id }: { id: string }) {
  const t = useTranslations("training.passport");
  const tc = useTranslations("common");
  const te = useTranslations("enums");
  const { project } = useCurrentProject();
  const { date, dateTime } = useFormatters(project?.id);
  const q = useTrainingReport(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  const d = q.data;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2 print:hidden">
        <Breadcrumbs items={[{ label: d.worker.worker_no, href: `/workers/${id}` }, { label: t("dataSubjectReport") }]} />
        <Button onClick={() => window.print()} data-testid="do-print">
          <Printer aria-hidden />
          {tc("print")}
        </Button>
      </div>
      <div className="flex flex-col gap-4" data-testid="dsr-report">
        <PageHeader title={t("dataSubjectReport")} description={t("dsrGenerated", { at: dateTime(d.generated_at), purpose: te(`exportPurpose.${d.purpose}`) })} />
        <Alert tone="info">{t("dsrHint")}</Alert>
        <p className="text-base">
          <WorkerLabel w={d.worker} />
        </p>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("records")}</CardTitle>
          </CardHeader>
          <CardContent>
            {d.records.length ? (
              <Table data-testid="dsr-records">
                <THead>
                  <TR>
                    <TH>{t("course")}</TH>
                    <TH>{t("recordNo")}</TH>
                    <TH>{t("completedOn")}</TH>
                    <TH>{t("validUntilH")}</TH>
                    <TH>{tc("status")}</TH>
                  </TR>
                </THead>
                <TBody>
                  {d.records.map((r) => (
                    <TR key={r.id}>
                      <TD label={t("course")}>
                        <Code>{r.course_code}</Code>
                      </TD>
                      <TD label={t("recordNo")}>
                        <Code>{r.record_no}</Code> · <Code>{r.certificate_no}</Code>
                      </TD>
                      <TD label={t("completedOn")}>{date(r.completed_on)}</TD>
                      <TD label={t("validUntilH")}>{r.valid_until ? date(r.valid_until) : "—"}</TD>
                      <TD label={tc("status")}>
                        <RecordStatusBadge status={r.status} />
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            ) : (
              <EmptyState />
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("attendances")}</CardTitle>
          </CardHeader>
          <CardContent>
            {d.attendances.length ? (
              <Table data-testid="dsr-attendances">
                <THead>
                  <TR>
                    <TH>{t("session")}</TH>
                    <TH>{t("course")}</TH>
                    <TH>{t("dates")}</TH>
                    <TH>{t("attendance")}</TH>
                    <TH>{t("scores")}</TH>
                    <TH>{t("result")}</TH>
                  </TR>
                </THead>
                <TBody>
                  {d.attendances.map((a, i) => (
                    <TR key={i}>
                      <TD label={t("session")}>
                        <Code>{a.session_no}</Code>
                      </TD>
                      <TD label={t("course")}>
                        <Code>{a.course_code}</Code>
                      </TD>
                      <TD label={t("dates")}>
                        <span className="ltr">{date(a.first_day)}</span>
                        {a.last_day !== a.first_day ? (
                          <>
                            {" – "}
                            <span className="ltr">{date(a.last_day)}</span>
                          </>
                        ) : null}
                      </TD>
                      <TD label={t("attendance")}>
                        {te.has(`nominationStatus.${a.status as S["NominationStatus"]}`) ? te(`nominationStatus.${a.status as S["NominationStatus"]}`) : a.status} · <Hours v={(a.minutes / 60).toFixed(2)} />
                      </TD>
                      <TD label={t("scores")}>
                        {a.theory_score_pct ? <span className="ltr">{a.theory_score_pct} %</span> : "—"}
                        {a.practical_result ? ` · ${a.practical_result}` : ""}
                      </TD>
                      <TD label={t("result")}>{te.has(`attendanceResult.${a.result as S["AttendanceResult"]}`) ? te(`attendanceResult.${a.result as S["AttendanceResult"]}`) : a.result}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            ) : (
              <EmptyState />
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("gapsTitle")}</CardTitle>
          </CardHeader>
          <CardContent>
            <RequirementsTable items={d.requirements} projectId={project?.id ?? null} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

/* ───────────── deployment detail: requirements with as-of ───────────── */

export function DeploymentTrainingCard({ deploymentId, projectId }: { deploymentId: string; projectId: string }) {
  const t = useTranslations("training.passport");
  const [asOf, setAsOf] = useState("");
  const q = useTrainingRequirements(deploymentId, asOf || null);
  return (
    <Card data-testid="deployment-training">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">{t("requirementsTitle")}</CardTitle>
        <FormField id="dt-asof" label={t("asOf")}>
          <Input type="date" className="ltr h-9 w-44" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
        </FormField>
      </CardHeader>
      <CardContent>
        {q.isLoading ? <LoadingState rows={2} /> : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.data ? <RequirementsTable items={q.data.requirements} projectId={projectId} /> : null}
        {q.data && !q.data.kpi_population ? <p className="mt-2 text-xs text-muted-foreground">{t("notInKpi")}</p> : null}
      </CardContent>
    </Card>
  );
}
