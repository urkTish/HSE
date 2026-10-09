"use client";
import { Ban, ClipboardList, FileText, Play, Plus, Save, Send, ShieldAlert, XCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Attachments } from "@/components/common/attachments";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { CheckboxField, FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { ProjectGate } from "@/components/common/project-gate";
import { UserSelect, useProjectOptions, useUserOptions } from "@/components/common/pickers";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import { Code, StepDialog } from "@/components/access/common";
import { UserName } from "@/components/cert/common";
import { StackedDate } from "@/components/medical/common";
import { Link, useRouter } from "@/i18n/navigation";
import { api, ApiError, unwrap, type Schemas } from "@/lib/api/client";
import { useAuditProgramme, useFieldAudit, useFieldAudits, useFieldRefresh, useTemplates } from "@/lib/api/field";
import { AUDIT_STATUSES } from "@/lib/field-enums";
import { useSearchState } from "@/lib/url-state";
import { fromLocalInput, toLocalInput } from "@/components/emergency/common";
import { AuditStatusBadge, FieldAuditSubNav, FieldReasonDialog, GradeBadge, NoNamesHint, Score, useBi, useFieldCaps, useFieldRef } from "./common";
import { FindingsTable } from "./inspect";
import { answerReady, emptyAnswer, ItemAnswer, ManualFindings, toAnswerInput, toManualInput, useSections, type AnswerState, type ManualFinding } from "./run";

type S = Schemas;
type Project = S["ProjectRead"];
type Audit = S["AuditRead"];

/* ═════════════ audit register (§3.7, AUD-1…AUD-8) ═════════════ */

export function FieldAuditsPage() {
  return <ProjectGate>{(p) => <Audits project={p} />}</ProjectGate>;
}

function Audits({ project }: { project: Project }) {
  const t = useTranslations("field.audits");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useFieldCaps(project.id);
  const opts = useProjectOptions(project.id);
  const { label, items: refItems } = useFieldRef();
  const s = useSearchState();
  const type = (s.get("type") ?? "") as S["AuditType"] | "";
  const status = (s.get("status") ?? "") as S["AuditStatus"] | "";
  const eng = s.get("eng") ?? "";
  const page = Number(s.get("page") ?? 1);
  const q = useFieldAudits(project.id, { audit_type: type || null, status: status ? [status] : null, auditee_engagement_id: eng || null, page, page_size: 50 }, { enabled: caps.view || caps.audit });
  const [planning, setPlanning] = useState(false);
  if (!caps.view && !caps.audit) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.audit ? (
            <Button onClick={() => setPlanning(true)} data-testid="audit-plan">
              <Plus aria-hidden />
              {t("plan")}
            </Button>
          ) : null
        }
      />
      <FieldAuditSubNav />
      <ListToolbar>
        <SelectFilter id="au-type" label={t("type")} value={type} onChange={(v) => s.set({ type: v, page: null })} options={refItems("audit_types").map((x) => ({ value: x.code as S["AuditType"], label: label("audit_types", x.code) }))} />
        <SelectFilter id="au-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v, page: null })} options={AUDIT_STATUSES.map((x) => ({ value: x, label: te(`fdAuditStatus.${x}`) }))} />
        <SelectFilter id="au-eng" label={t("auditee")} value={eng} onChange={(v) => s.set({ eng: v, page: null })} options={opts.engagements.map((x) => ({ value: x.value, label: x.label }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data?.items.length ? (
        <>
          <Table data-testid="audits-table">
            <THead>
              <TR>
                <TH>{t("audit")}</TH>
                <TH>{t("auditee")}</TH>
                <TH>{t("lead")}</TH>
                <TH>{t("fieldwork")}</TH>
                <TH className="text-end">{t("score")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {q.data.items.map((a) => (
                <TR key={a.id} data-testid="audit-row" data-no={a.audit_no} data-status={a.status}>
                  <TD label={t("audit")}>
                    <Link href={`/field-audits/${a.id}`} className="font-medium text-primary hover:underline">
                      <Code>{a.audit_no}</Code>
                    </Link>
                    <span className="block text-xs text-muted-foreground">
                      {label("audit_types", a.audit_type)} · <Code>{a.template_code}</Code>
                    </span>
                  </TD>
                  <TD label={t("auditee")}>
                    {a.auditee_engagement ? <Code>{a.auditee_engagement.short_code}</Code> : t("projectScope")}
                    <span className="block text-xs text-muted-foreground">{a.sites.map((x) => x.code).join(" · ")}</span>
                  </TD>
                  <TD label={t("lead")}>
                    <UserName u={a.lead_auditor} />
                  </TD>
                  <TD label={t("fieldwork")}>
                    <StackedDate v={a.fieldwork_end ?? a.planned_end} />
                  </TD>
                  <TD label={t("score")} className="text-end">
                    {a.response?.submitted ? (
                      <span className="inline-flex flex-col items-end gap-1">
                        <Score v={a.response.score_pct} />
                        <GradeBadge grade={a.response.grade} />
                      </span>
                    ) : (
                      "—"
                    )}
                  </TD>
                  <TD label={tc("status")}>
                    <AuditStatusBadge status={a.status} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={50} total={q.data.total} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState message={t("empty")} />
      )}
      {planning ? <PlanAuditDialog project={project} onClose={() => setPlanning(false)} /> : null}
    </div>
  );
}

/** AUD-3 / AUD-4 refusals (SOD_CONFLICT) get their own explanation, not just the code. */
function IndependenceError({ error }: { error: unknown }) {
  const t = useTranslations("field.audits");
  if (!(error instanceof ApiError) || error.code !== "SOD_CONFLICT") return <MutationError error={error} />;
  return (
    <Alert tone="danger" data-testid="sod-conflict">
      <span className="flex items-start gap-2">
        <ShieldAlert aria-hidden className="mt-0.5 size-5 shrink-0" />
        <span>
          <span className="block font-semibold">{t("sodTitle")}</span>
          <span className="block text-sm">{t("sodText")}</span>
          <span className="mt-1 block text-xs opacity-80">{error.message}</span>
        </span>
      </span>
    </Alert>
  );
}

function PlanAuditDialog({ project, onClose }: { project: Project; onClose: () => void }) {
  const t = useTranslations("field.audits");
  const tc = useTranslations("common");
  const bi = useBi();
  const { label, items: refItems } = useFieldRef();
  const opts = useProjectOptions(project.id);
  const users = useUserOptions(project.id);
  const router = useRouter();
  const refresh = useFieldRefresh();
  const [type, setType] = useState<S["AuditType"]>("contractor_hse");
  const tpls = useTemplates({ kind: "audit", status: ["published"], project_id: project.id });
  const choices = (tpls.data?.items ?? []).filter((x) => x.audit_type === type || (type === "client_requested" && x.audit_type === "contractor_hse"));
  const [tpl, setTpl] = useState("");
  const [eng, setEng] = useState("");
  const [sites, setSites] = useState<string[]>([]);
  const [lead, setLead] = useState("");
  const [team, setTeam] = useState<string[]>([]);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const needsAuditee = type === "contractor_hse";
  const valid = tpl && sites.length && lead && start && end && end >= start && (!needsAuditee || eng);
  async function save() {
    const a = await unwrap(
      api.POST("/api/v1/projects/{project_id}/field-audits", {
        params: { path: { project_id: project.id } },
        body: { audit_type: type, template_code: tpl, auditee_engagement_id: type === "system_iso45001" ? null : eng || null, site_ids: sites, lead_auditor_id: lead, team_ids: team, planned_start: start, planned_end: end },
      }),
    );
    await refresh();
    router.push(`/field-audits/${a.id}`);
  }
  return (
    <StepDialog wide title={t("plan")} description={t("planHint")} confirmLabel={t("planConfirm")} disabled={!valid} testId="audit-plan-confirm" onConfirm={save} onClose={onClose} renderError={(e) => <IndependenceError error={e} />}>
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="ap-type" label={t("type")} required>
          <Select value={type} onChange={(e) => (setType(e.target.value as S["AuditType"]), setTpl(""))} data-testid="ap-type">
            {refItems("audit_types").map((x) => (
              <option key={x.code} value={x.code}>
                {label("audit_types", x.code)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="ap-tpl" label={t("template")} required>
          <Select value={tpl} onChange={(e) => setTpl(e.target.value)} data-testid="ap-template">
            <option value="">—</option>
            {choices.map((x) => (
              <option key={x.id} value={x.template_code}>
                {x.template_code} v{x.version} · {bi(x.title_en, x.title_ar)}
              </option>
            ))}
          </Select>
        </FormField>
        {type !== "system_iso45001" ? (
          <FormField id="ap-eng" label={t("auditee")} required={needsAuditee}>
            <Select value={eng} onChange={(e) => setEng(e.target.value)} data-testid="ap-auditee">
              <option value="">—</option>
              {opts.engagements.map((x) => (
                <option key={x.value} value={x.value}>
                  {x.label}
                </option>
              ))}
            </Select>
          </FormField>
        ) : null}
        <MultiSelect id="ap-sites" label={t("sites")} options={opts.sites.map((x) => ({ value: x.value, label: x.code }))} value={sites} onChange={setSites} allLabel={tc("select")} testId="ap-sites" className="lg:w-full" />
        <FormField id="ap-lead" label={t("lead")} required>
          <UserSelect projectId={project.id} value={lead} onChange={(e) => setLead(e.target.value)} data-testid="ap-lead" />
        </FormField>
        <MultiSelect id="ap-team" label={t("team")} options={users.filter((u) => u.value !== lead)} value={team} onChange={(v) => setTeam(v.slice(0, 5))} allLabel={t("noTeam")} className="lg:w-full" />
        <FormField id="ap-start" label={t("plannedStart")} required>
          <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} data-testid="ap-start" />
        </FormField>
        <FormField id="ap-end" label={t("plannedEnd")} required hint={t("maxDays")}>
          <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} data-testid="ap-end" />
        </FormField>
      </div>
      <p className="text-xs text-muted-foreground">{t("independenceHint")}</p>
    </StepDialog>
  );
}

/* ═════════════ audit detail: conduct, fieldwork, issue (§4.4) ═════════════ */

export function FieldAuditPage({ id }: { id: string }) {
  const tn = useTranslations("field.nav");
  const q = useFieldAudit(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  return (
    <div>
      <Breadcrumbs items={[{ label: tn("audits"), href: "/field-audits" }, { label: q.data.audit_no }]} />
      <AuditDetail a={q.data} key={q.data.id} />
    </div>
  );
}

function fromRead(a: S["AnswerRead"]): AnswerState {
  return { ...emptyAnswer(), answer: a.answer ?? "", numeric: a.numeric_value ?? "", count: a.count_value === null || a.count_value === undefined ? "" : String(a.count_value), note: a.note ?? "", equipment_ref: a.equipment_ref ?? "" };
}

function AuditDetail({ a }: { a: Audit }) {
  const t = useTranslations("field.audits");
  const { label } = useFieldRef();
  const caps = useFieldCaps(a.project_id);
  const refresh = useFieldRefresh();
  const [dialog, setDialog] = useState<"meetings" | "issue" | "cancel" | "void" | null>(null);
  const [conducting, setConducting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const lead = a.lead_auditor?.id === caps.meId;
  const onTeam = lead || a.team.some((u) => u.id === caps.meId);
  const canConduct = caps.audit && (onTeam || caps.publish);
  const r = a.response;

  async function step(action: S["app__core__field_enums__AuditAction"]) {
    setError(null);
    try {
      await unwrap(api.POST("/api/v1/field-audits/{audit_id}/transitions", { params: { path: { audit_id: a.id } }, body: { action, ca_for_observations: false } }));
      await refresh();
      toast.success(t("saved"));
    } catch (e) {
      setError(e);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card data-testid="audit-detail" data-status={a.status}>
        <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
          <div>
            <p className="text-sm text-muted-foreground">
              {label("audit_types", a.audit_type)} · <Code>{a.template_code}</Code>
              {a.template_version ? <span className="ltr"> v{a.template_version}</span> : null}
            </p>
            <CardTitle className="flex flex-wrap items-center gap-2">
              <Code>{a.audit_no}</Code>
              <AuditStatusBadge status={a.status} />
            </CardTitle>
          </div>
          <div className="flex flex-wrap gap-2">
            {a.status === "planned" && canConduct ? (
              <Button size="sm" onClick={() => void step("start")} data-testid="audit-start">
                <Play aria-hidden />
                {t("start")}
              </Button>
            ) : null}
            {(a.status === "planned" || a.status === "in_progress") && canConduct ? (
              <Button size="sm" variant={a.status === "in_progress" ? "default" : "outline"} onClick={() => setConducting(true)} data-testid="audit-conduct">
                <ClipboardList aria-hidden />
                {t("conduct")}
              </Button>
            ) : null}
            {(a.status === "planned" || a.status === "in_progress") && canConduct ? (
              <Button size="sm" variant="outline" onClick={() => setDialog("meetings")} data-testid="audit-meetings">
                {t("meetings")}
              </Button>
            ) : null}
            {a.status === "in_progress" && (lead || caps.publish) ? (
              <Button size="sm" variant="outline" onClick={() => void step("complete_fieldwork")} data-testid="audit-complete">
                {t("completeFieldwork")}
              </Button>
            ) : null}
            {a.status === "fieldwork_complete" && caps.issue && !lead ? (
              <Button size="sm" onClick={() => setDialog("issue")} data-testid="audit-issue">
                <Send aria-hidden />
                {t("issue")}
              </Button>
            ) : null}
            {a.status === "planned" && caps.audit ? (
              <Button size="sm" variant="outline" onClick={() => setDialog("cancel")} data-testid="audit-cancel">
                <XCircle aria-hidden />
                {t("cancel")}
              </Button>
            ) : null}
            {(a.status === "in_progress" || a.status === "fieldwork_complete" || a.status === "issued") && caps.void ? (
              <Button size="sm" variant="ghost" onClick={() => setDialog("void")} data-testid="audit-void">
                <Ban aria-hidden />
                {t("void")}
              </Button>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {a.status === "fieldwork_complete" && lead && caps.issue ? <Alert tone="info" data-testid="issue-not-lead">{t("issueNotLead")}</Alert> : null}
          <IndependenceError error={error} />
          <FieldList>
            <FieldItem label={t("auditee")}>{a.auditee_engagement ? <Code>{a.auditee_engagement.short_code}</Code> : t("projectScope")}</FieldItem>
            <FieldItem label={t("sites")}>{a.sites.map((x) => x.code).join(" · ")}</FieldItem>
            <FieldItem label={t("lead")}>
              <UserName u={a.lead_auditor} />
            </FieldItem>
            <FieldItem label={t("team")}>{a.team.length ? a.team.map((u) => <span key={u.id} className="me-2"><UserName u={u} /></span>) : "—"}</FieldItem>
            <FieldItem label={t("planned")}>
              <span className="inline-flex gap-2">
                <StackedDate v={a.planned_start} /> – <StackedDate v={a.planned_end} />
              </span>
            </FieldItem>
            <FieldItem label={t("fieldwork")}>
              {a.fieldwork_start ? (
                <span className="inline-flex gap-2">
                  <StackedDate v={a.fieldwork_start} /> – <StackedDate v={a.fieldwork_end} />
                </span>
              ) : (
                "—"
              )}
            </FieldItem>
            <FieldItem label={t("opening")}>
              <StackedDate v={a.opening_meeting_at} time />
            </FieldItem>
            <FieldItem label={t("closing")}>
              <StackedDate v={a.closing_meeting_at} time />
            </FieldItem>
            <FieldItem label={t("attendees")}>{a.auditee_attendee_roles || "—"}</FieldItem>
            <FieldItem label={t("reportDue")}>
              <StackedDate v={a.report_due_by} />
            </FieldItem>
            {a.issued_at ? (
              <FieldItem label={t("issued")}>
                <UserName u={a.issued_by} /> · <StackedDate v={a.issued_at} time />
              </FieldItem>
            ) : null}
            {a.status_reason ? (
              <FieldItem label={t("reason")} wide>
                <span dir="auto">{a.status_reason}</span>
              </FieldItem>
            ) : null}
            {a.summary_en || a.summary_ar ? (
              <FieldItem label={t("summary")} wide>
                <span dir="auto" className="whitespace-pre-line">{a.summary_en}</span>
                {a.summary_ar ? (
                  <span dir="rtl" className="mt-1 block whitespace-pre-line">
                    {a.summary_ar}
                  </span>
                ) : null}
              </FieldItem>
            ) : null}
          </FieldList>
        </CardContent>
      </Card>
      {a.report_en_id || a.report_ar_id ? (
        <Card data-testid="audit-reports">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FileText aria-hidden className="size-5" />
              {t("reports")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Attachments ownerType="field_audit_report" ownerId={a.id} canUpload={false} />
          </CardContent>
        </Card>
      ) : null}
      {r ? (
        <Card data-testid="audit-result">
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-3 text-base">
              {t("result")}
              <Score v={r.score_pct} className="text-2xl font-semibold" testId="audit-score" />
              <GradeBadge grade={r.grade} />
              {!r.submitted ? <StatusBadge status="draft" label={t("provisional")} /> : null}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {r.section_scores.length ? (
              <Table data-testid="section-scores">
                <THead>
                  <TR>
                    <TH>{t("section")}</TH>
                    <TH className="text-end">{t("score")}</TH>
                  </TR>
                </THead>
                <TBody>
                  {r.section_scores.map((s) => (
                    <TR key={s.section_code}>
                      <TD label={t("section")}>
                        <Code>{s.section_code}</Code> <SectionTitle s={s} />
                      </TD>
                      <TD label={t("score")} className="text-end">
                        <Score v={s.score_pct} testId="section-score" />
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            ) : null}
            <FindingsTable findings={r.findings} />
          </CardContent>
        </Card>
      ) : null}
      {conducting ? <Conduct a={a} onClose={() => setConducting(false)} /> : null}
      {dialog === "meetings" ? <MeetingsDialog a={a} onClose={() => setDialog(null)} /> : null}
      {dialog === "issue" ? <IssueDialog a={a} onClose={() => setDialog(null)} /> : null}
      {dialog === "cancel" ? (
        <FieldReasonDialog
          title={t("cancel")}
          confirmLabel={t("cancel")}
          onConfirm={(reason) => unwrap(api.POST("/api/v1/field-audits/{audit_id}/transitions", { params: { path: { audit_id: a.id } }, body: { action: "cancel", reason, ca_for_observations: false } }))}
          onClose={() => setDialog(null)}
        />
      ) : null}
      {dialog === "void" ? (
        <FieldReasonDialog
          title={t("void")}
          description={t("voidHint")}
          confirmLabel={t("void")}
          onConfirm={(reason) => unwrap(api.POST("/api/v1/field-audits/{audit_id}/transitions", { params: { path: { audit_id: a.id } }, body: { action: "void", reason, ca_for_observations: false } }))}
          onClose={() => setDialog(null)}
        />
      ) : null}
    </div>
  );
}

function SectionTitle({ s }: { s: S["SectionScore"] }) {
  const bi = useBi();
  return <>{bi(s.title_en, s.title_ar)}</>;
}

function Conduct({ a, onClose }: { a: Audit; onClose: () => void }) {
  const t = useTranslations("field.audits");
  const bi = useBi();
  const refresh = useFieldRefresh();
  const tpl = useTemplates({ template_code: a.template_code, kind: "audit" });
  const template = (tpl.data?.items ?? []).find((x) => (a.template_version ? x.version === a.template_version : x.status === "published")) ?? null;
  const sections = useSections(template, true);
  const all = sections.flatMap((x) => x.items);
  const [answers, setAnswers] = useState<Record<string, AnswerState>>(() => Object.fromEntries((a.response?.answers ?? []).map((x) => [x.item_code, fromRead(x)])));
  const [manual, setManual] = useState<ManualFinding[]>(() =>
    (a.response?.findings ?? []).filter((f) => !f.item_code).map((f) => ({ severity: f.severity, description: f.description_en ?? f.description_ar ?? "", ca_required: f.ca_required, fixed_on_spot: false })),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const done = all.filter((i) => answerReady(i, answers[i.item_code]) && answers[i.item_code]?.answer).length;
  async function save() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(
        api.PUT("/api/v1/field-audits/{audit_id}/answers", {
          params: { path: { audit_id: a.id } },
          body: { answers: all.map((i) => toAnswerInput(i, answers[i.item_code], true)).filter((x): x is S["AnswerInput"] => x !== null && Boolean(x.answer || x.numeric_value || x.count_value !== undefined)), manual_findings: manual.filter((m) => m.description.trim()).map(toManualInput) },
        }),
      );
      await refresh();
      toast.success(t("answersSaved"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  if (!template) return <LoadingState />;
  return (
    <Card data-testid="audit-conduct-card">
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">
          {t("conduct")} · <Code>{template.template_code}</Code> {bi(template.title_en, template.title_ar)}
        </CardTitle>
        <span className="text-sm font-medium tabular-nums" data-testid="audit-progress">
          {t("progress", { done, total: all.length })}
        </span>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-xs text-muted-foreground">{t("photosResend")}</p>
        {sections.map(({ s, items }) => (
          <section key={s.code} className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold text-muted-foreground">
              <Code>{s.code}</Code> {bi(s.title_en, s.title_ar)}
            </h3>
            <ol className="flex flex-col gap-3">
              {items.map((it) => (
                <ItemAnswer key={it.item_code} it={it} audit a={answers[it.item_code] ?? emptyAnswer()} onChange={(x) => setAnswers({ ...answers, [it.item_code]: x })} />
              ))}
            </ol>
          </section>
        ))}
        <div>
          <p className="mb-2 text-sm font-medium">{t("manualFindings")}</p>
          <ManualFindings value={manual} onChange={setManual} audit />
        </div>
        <MutationError error={error} />
        <div className="sticky bottom-0 flex flex-wrap gap-2 border-t bg-background py-3">
          <Button className="min-h-11" disabled={busy} onClick={() => void save()} data-testid="audit-save-answers">
            <Save aria-hidden />
            {busy ? t("saving") : t("saveAnswers")}
          </Button>
          <Button variant="ghost" className="min-h-11" onClick={onClose}>
            {t("closeConduct")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function MeetingsDialog({ a, onClose }: { a: Audit; onClose: () => void }) {
  const t = useTranslations("field.audits");
  const refresh = useFieldRefresh();
  const [opening, setOpening] = useState(toLocalInput(a.opening_meeting_at));
  const [closing, setClosing] = useState(toLocalInput(a.closing_meeting_at));
  const [fs, setFs] = useState(a.fieldwork_start ?? "");
  const [fe, setFe] = useState(a.fieldwork_end ?? "");
  const [roles, setRoles] = useState(a.auditee_attendee_roles ?? "");
  return (
    <StepDialog
      title={t("meetings")}
      confirmLabel={t("save")}
      testId="meetings-save"
      onConfirm={async () => {
        await unwrap(
          api.PATCH("/api/v1/field-audits/{audit_id}", {
            params: { path: { audit_id: a.id } },
            body: { opening_meeting_at: fromLocalInput(opening), closing_meeting_at: fromLocalInput(closing), fieldwork_start: fs || null, fieldwork_end: fe || null, auditee_attendee_roles: roles.trim() || null },
          }),
        );
        await refresh();
      }}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="am-open" label={t("opening")}>
          <Input type="datetime-local" value={opening} onChange={(e) => setOpening(e.target.value)} />
        </FormField>
        <FormField id="am-close" label={t("closing")}>
          <Input type="datetime-local" value={closing} onChange={(e) => setClosing(e.target.value)} data-testid="am-close" />
        </FormField>
        <FormField id="am-fs" label={t("fieldworkStart")}>
          <Input type="date" value={fs} onChange={(e) => setFs(e.target.value)} data-testid="am-fs" />
        </FormField>
        <FormField id="am-fe" label={t("fieldworkEnd")}>
          <Input type="date" value={fe} onChange={(e) => setFe(e.target.value)} data-testid="am-fe" />
        </FormField>
      </div>
      <FormField id="am-roles" label={t("attendees")} hint={t("attendeesHint")}>
        <Input maxLength={300} value={roles} onChange={(e) => setRoles(e.target.value)} />
      </FormField>
    </StepDialog>
  );
}

function IssueDialog({ a, onClose }: { a: Audit; onClose: () => void }) {
  const t = useTranslations("field.audits");
  const refresh = useFieldRefresh();
  const [en, setEn] = useState(a.summary_en ?? "");
  const [ar, setAr] = useState(a.summary_ar ?? "");
  const [obs, setObs] = useState(false);
  async function go() {
    await unwrap(api.PATCH("/api/v1/field-audits/{audit_id}", { params: { path: { audit_id: a.id } }, body: { summary_en: en.trim() || null, summary_ar: ar.trim() || null } }));
    await unwrap(api.POST("/api/v1/field-audits/{audit_id}/transitions", { params: { path: { audit_id: a.id } }, body: { action: "issue", ca_for_observations: obs } }));
    await refresh();
  }
  const nc = (a.response?.findings ?? []).filter((f) => f.severity === "major_nc" || f.severity === "minor_nc").length;
  return (
    <StepDialog wide title={t("issueTitle")} description={t("issueHint", { n: nc })} confirmLabel={t("issue")} disabled={!(en.trim() || ar.trim())} testId="issue-confirm" onConfirm={go} onClose={onClose} renderError={(e) => <IndependenceError error={e} />}>
      <FormField id="ai-en" label={t("summaryEn")} required hint={<NoNamesHint />}>
        <Textarea rows={5} maxLength={3000} value={en} onChange={(e) => setEn(e.target.value)} data-testid="ai-summary" />
      </FormField>
      <FormField id="ai-ar" label={t("summaryAr")}>
        <Textarea dir="rtl" rows={4} maxLength={3000} value={ar} onChange={(e) => setAr(e.target.value)} />
      </FormField>
      <CheckboxField id="ai-obs" label={t("caForObservations")}>
        <Checkbox checked={obs} onChange={(e) => setObs(e.target.checked)} />
      </CheckboxField>

    </StepDialog>
  );
}

/* ═════════════ audit programme (§3.8, §6.4, AUD-6, AUD-7) ═════════════ */

export function AuditProgrammePage() {
  return <ProjectGate>{(p) => <Programme project={p} />}</ProjectGate>;
}

function Programme({ project }: { project: Project }) {
  const t = useTranslations("field.programme");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useFieldCaps(project.id);
  const { label } = useFieldRef();
  const q = useAuditProgramme(project.id, { enabled: caps.view || caps.audit });
  if (!caps.view && !caps.audit) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const lines = q.data?.lines ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <FieldAuditSubNav />
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : lines.length ? (
        <Table data-testid="programme-table">
          <THead>
            <TR>
              <TH>{t("scope")}</TH>
              <TH>{t("type")}</TH>
              <TH>{t("every")}</TH>
              <TH>{t("lastAudit")}</TH>
              <TH>{t("dueBy")}</TH>
              <TH>{tc("status")}</TH>
            </TR>
          </THead>
          <TBody>
            {lines.map((l, i) => (
              <TR key={`${l.engagement?.id ?? "p"}-${l.audit_type}-${i}`} data-testid="programme-line" data-scope={l.engagement?.short_code ?? "project"} data-status={l.status}>
                <TD label={t("scope")}>{l.engagement ? <Code>{l.engagement.short_code}</Code> : t("project")}</TD>
                <TD label={t("type")}>{label("audit_types", l.audit_type)}</TD>
                <TD label={t("every")}>{t("months", { n: l.frequency_months })}</TD>
                <TD label={t("lastAudit")}>
                  {l.last_satisfied_by ? <Code>{l.last_satisfied_by}</Code> : <span className="text-muted-foreground">{t("none")}</span>}
                  {l.items.length ? (
                    <span className="mt-1 flex flex-col gap-0.5 text-xs text-muted-foreground">
                      {l.items.map((it) => (
                        <span key={`${it.due_by}-${it.audit_no}`} data-testid="programme-item" data-on-time={it.met_on_time ? "yes" : "no"}>
                          {it.due_by} · {it.audit_no ?? "—"} · {it.met_on_time ? t("onTime") : t("late")}
                        </span>
                      ))}
                    </span>
                  ) : null}
                </TD>
                <TD label={t("dueBy")}>
                  <StackedDate v={l.due_by} />
                </TD>
                <TD label={tc("status")}>
                  <span data-testid="line-status" data-status={l.status}>
                    <StatusBadge status={l.status} label={te(`fdLineStatus.${l.status}`)} />
                  </span>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <EmptyState message={t("empty")} />
      )}
    </div>
  );
}
