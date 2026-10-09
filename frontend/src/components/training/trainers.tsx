"use client";
import { Pencil, Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { ExportButtons } from "@/components/common/export-buttons";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { HistoryPanel } from "@/components/common/history-panel";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { UserSelect } from "@/components/common/pickers";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { Code, DaysLeft, DeploymentPicker, StepDialog, WorkerLabel } from "@/components/access/common";
import { UploadField, UserName } from "@/components/cert/common";
import { StackedDate } from "@/components/medical/common";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useTrainerAuthorisation, useTrainerAuthorisations, useTrainingProviders, useTrainingRefresh } from "@/lib/api/training";
import { todayInZone } from "@/lib/datetime";
import { TRAINER_ROLES, TRAINER_STATUSES } from "@/lib/train-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { ProviderLabel, ProviderSelect, TrainerStatusBadge, TrainingCatalogueSubNav, useCourseCatalogue, useTrainingCaps } from "./common";

type S = Schemas;
const PAGE_SIZE = 50;
const EVIDENCE_CATEGORIES: S["CourseCategory"][] = ["high_risk_task", "ptw_role", "emergency_response"];

function TrainerName({ a }: { a: S["TrainerAuthorisationRead"] }) {
  if (a.trainer_worker) return <WorkerLabel w={a.trainer_worker} />;
  return <UserName u={a.trainer_user} />;
}

/* ───────────── list ───────────── */

export function TrainerListPage() {
  return <ProjectGate>{(p) => <TrainerList project={p} />}</ProjectGate>;
}

function TrainerList({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("training.trainers");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useTrainingCaps(project.id);
  const { courses } = useCourseCatalogue(project.id);
  const providers = useTrainingProviders({ page_size: 200, kind: ["internal", "contractor_internal"] });
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as S["TrainerAuthorisationStatus"][];
  const [create, setCreate] = useState(false);
  const q = useTrainerAuthorisations(project.id, {
    status: status.length ? status : null,
    course_code: s.get("course") || null,
    role: (s.get("role") as S["TrainerRole"]) || null,
    provider_id: s.get("provider") || null,
    expiring_days: s.getInt("expiring", 0) || null,
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
          caps.authorise ? (
            <Button onClick={() => setCreate(true)} data-testid="new-trainer">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <TrainingCatalogueSubNav />
      <ListToolbar actions={caps.export ? <ExportButtons dataset="trainer_authorisations" params={{ project_id: project.id }} /> : null}>
        <MultiSelect id="ta-status" label={tc("status")} options={TRAINER_STATUSES.map((x) => ({ value: x, label: te(`trainerStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <SelectFilter id="ta-course" label={t("course")} value={s.get("course") ?? ""} onChange={(v) => s.set({ course: v })} options={courses.map((c) => ({ value: c.code, label: c.code }))} />
        <SelectFilter id="ta-role" label={t("role")} value={s.get("role") ?? ""} onChange={(v) => s.set({ role: v })} options={TRAINER_ROLES.map((x) => ({ value: x, label: te(`trainerRole.${x}`) }))} />
        <SelectFilter id="ta-provider" label={t("provider")} value={s.get("provider") ?? ""} onChange={(v) => s.set({ provider: v })} options={(providers.data?.items ?? []).map((p) => ({ value: p.id, label: p.provider_code }))} />
        <SelectFilter id="ta-exp" label={t("expiring")} value={s.get("expiring") ?? ""} onChange={(v) => s.set({ expiring: v })} options={[{ value: "30", label: t("withinDays", { n: 30 }) }]} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="trainers-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("trainer")}</TH>
                <TH>{t("provider")}</TH>
                <TH>{t("courses")}</TH>
                <TH>{t("roles")}</TH>
                <TH>{t("validTo")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((a) => (
                <TR key={a.id} data-testid="trainer-row" data-no={a.authorisation_no}>
                  <TD label={t("no")}>
                    <Link href={`/trainer-authorisations/${a.id}`} className="font-medium text-primary hover:underline">
                      <Code>{a.authorisation_no}</Code>
                    </Link>
                  </TD>
                  <TD label={t("trainer")}>
                    <TrainerName a={a} />
                  </TD>
                  <TD label={t("provider")}>
                    <Code>{a.provider.provider_code}</Code>
                  </TD>
                  <TD label={t("courses")}>
                    <span className="text-xs">{a.course_codes.join(" · ")}</span>
                  </TD>
                  <TD label={t("roles")}>{a.roles.map((r) => te(`trainerRole.${r}`)).join(" · ")}</TD>
                  <TD label={t("validTo")}>
                    <StackedDate v={a.valid_to} projectId={project.id} />
                    {a.status === "active" ? (
                      <span className="mt-0.5 block">
                        <DaysLeft days={a.days_left} />
                      </span>
                    ) : null}
                  </TD>
                  <TD label={tc("status")}>
                    <TrainerStatusBadge status={a.status} />
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
      {create ? <TrainerDialog project={project} onClose={() => setCreate(false)} /> : null}
    </div>
  );
}

/* ───────────── create / edit ───────────── */

function TrainerDialog({ project, a, onClose }: { project: S["ProjectRead"]; a?: S["TrainerAuthorisationRead"]; onClose: () => void }) {
  const t = useTranslations("training.trainers");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const router = useRouter();
  const refresh = useTrainingRefresh();
  const { courses } = useCourseCatalogue(project.id, { active: true });
  const [who, setWho] = useState<"user" | "worker">(a?.trainer_worker ? "worker" : "user");
  const [user, setUser] = useState(a?.trainer_user?.id ?? "");
  const [dep, setDep] = useState<S["DeploymentRead"] | null>(null);
  const [provider, setProvider] = useState(a?.provider.id ?? "");
  const [codes, setCodes] = useState<string[]>(a?.course_codes ?? []);
  const [roles, setRoles] = useState<S["TrainerRole"][]>(a?.roles ?? ["trainer"]);
  const [basis, setBasis] = useState(a?.basis ?? "");
  const [evidence, setEvidence] = useState<string[]>(a?.evidence_attachment_ids ?? []);
  const [from, setFrom] = useState(a?.valid_from ?? todayInZone());
  const [to, setTo] = useState(a?.valid_to ?? "");
  const needsEvidence = codes.some((c) => EVIDENCE_CATEGORIES.includes(courses.find((x) => x.code === c)?.category ?? "awareness"));
  const trainerOk = Boolean(a) || (who === "user" ? Boolean(user) : Boolean(dep));
  const valid = trainerOk && provider && codes.length && roles.length && basis.trim().length >= 20 && from && to && to >= from && (!needsEvidence || evidence.length > 0);
  async function save() {
    if (a) {
      await unwrap(api.PATCH("/api/v1/trainer-authorisations/{authorisation_id}", { params: { path: { authorisation_id: a.id } }, body: { course_codes: codes, roles, basis: basis.trim(), evidence_attachment_ids: evidence, valid_to: to } }));
      await refresh();
      toast.success(tc("saved"));
      return;
    }
    const r = await unwrap(
      api.POST("/api/v1/projects/{project_id}/trainer-authorisations", {
        params: { path: { project_id: project.id } },
        body: {
          trainer_user_id: who === "user" ? user : null,
          trainer_worker_id: who === "worker" ? (dep?.worker_id ?? null) : null,
          provider_id: provider,
          course_codes: codes,
          roles,
          basis: basis.trim(),
          evidence_attachment_ids: evidence,
          valid_from: from,
          valid_to: to,
        },
      }),
    );
    await refresh();
    toast.success(t("created", { no: r.authorisation_no }));
    router.push(`/trainer-authorisations/${r.id}`);
  }
  return (
    <StepDialog title={a ? t("edit") : t("new")} description={t("newHint")} confirmLabel={tc("save")} onConfirm={save} onClose={onClose} disabled={!valid} wide testId="save-trainer">
      {!a ? (
        <>
          <fieldset className="flex flex-wrap gap-4 text-sm">
            <legend className="mb-1 text-sm font-medium">{t("trainer")}</legend>
            <label className="flex min-h-touch items-center gap-2">
              <input type="radio" checked={who === "user"} onChange={() => setWho("user")} data-testid="ta-who-user" />
              {t("platformUser")}
            </label>
            <label className="flex min-h-touch items-center gap-2">
              <input type="radio" checked={who === "worker"} onChange={() => setWho("worker")} data-testid="ta-who-worker" />
              {t("worker")}
            </label>
          </fieldset>
          {who === "user" ? (
            <FormField id="ta-user" label={t("platformUser")} required>
              <UserSelect id="ta-user" projectId={project.id} value={user} onChange={(e) => setUser(e.target.value)} data-testid="ta-user" />
            </FormField>
          ) : (
            <DeploymentPicker id="ta-worker" projectId={project.id} value={dep} onChange={setDep} label={t("worker")} required status={["mobilised"]} />
          )}
          <ProviderSelect id="ta-provider" label={t("provider")} value={provider} onChange={(v) => setProvider(v)} kinds={["internal", "contractor_internal"]} required hint={t("providerHint")} />
        </>
      ) : null}
      <MultiSelect id="ta-courses" label={t("courses")} options={courses.filter((c) => c.category !== "induction_link").map((c) => ({ value: c.code, label: `${c.code} — ${c.name_en}` }))} value={codes} onChange={setCodes} testId="ta-courses" />
      <CheckboxGroup id="ta-roles" legend={t("roles")} required options={TRAINER_ROLES.map((x) => ({ value: x, label: te(`trainerRole.${x}`) }))} value={roles} onChange={setRoles} />
      <FormField id="ta-basis" label={t("basis")} required hint={t("basisHint")}>
        <Textarea value={basis} onChange={(e) => setBasis(e.target.value)} maxLength={500} data-testid="ta-basis" />
      </FormField>
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField id="ta-from" label={t("validFrom")} required>
          <Input type="date" className="ltr" value={from} disabled={Boolean(a)} onChange={(e) => setFrom(e.target.value)} data-testid="ta-from" />
        </FormField>
        <FormField id="ta-to" label={t("validTo")} required hint={t("validToHint")}>
          <Input type="date" className="ltr" value={to} onChange={(e) => setTo(e.target.value)} data-testid="ta-to" />
        </FormField>
      </div>
      {/* Evidence is uploaded before the authorisation exists, so its owner is the project (PROGRESS contract request). */}
      <UploadField
        id="ta-evidence"
        label={t("evidence")}
        ownerType="trainer_authorisation_evidence"
        ownerId={a?.id ?? project.id}
        accept="application/pdf"
        value={evidence.length ? evidence[evidence.length - 1] ?? null : null}
        onChange={(v) => (v ? setEvidence([...evidence, v]) : undefined)}
        required={needsEvidence}
        hint={needsEvidence ? t("evidenceRequired") : t("evidenceHint")}
      />
      {evidence.length ? <p className="text-xs text-muted-foreground">{t("evidenceCount", { n: evidence.length })}</p> : null}
    </StepDialog>
  );
}

/* ───────────── detail ───────────── */

export function TrainerDetail({ id }: { id: string }) {
  const q = useTrainerAuthorisation(id);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <LoadingState />;
  return <ProjectById id={q.data.project_id}>{(p) => <TrainerView project={p} a={q.data} />}</ProjectById>;
}

function TrainerView({ project, a }: { project: S["ProjectRead"]; a: S["TrainerAuthorisationRead"] }) {
  const t = useTranslations("training.trainers");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useTrainingCaps(project.id);
  const { date, dateTime } = useFormatters(project.id);
  const refresh = useTrainingRefresh();
  const [action, setAction] = useState<S["TrainerAuthorisationAction"] | null>(null);
  const [edit, setEdit] = useState(false);
  const [reason, setReason] = useState("");
  const actions: S["TrainerAuthorisationAction"][] = !caps.authorise ? [] : a.status === "active" ? ["suspend", "withdraw"] : a.status === "suspended" ? ["reinstate", "withdraw"] : [];
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Breadcrumbs items={[{ label: t("title"), href: "/trainer-authorisations" }, { label: a.authorisation_no }]} />
        <PageHeader
          title={a.authorisation_no}
          description={a.course_codes.join(" · ")}
          actions={
            <>
              <TrainerStatusBadge status={a.status} />
              {caps.authorise && (a.status === "active" || a.status === "suspended") ? (
                <Button variant="outline" onClick={() => setEdit(true)} data-testid="edit-trainer">
                  <Pencil aria-hidden />
                  {tc("edit")}
                </Button>
              ) : null}
              {actions.map((x) => (
                <Button key={x} variant={x === "withdraw" ? "destructive-outline" : x === "suspend" ? "outline" : "default"} onClick={() => setAction(x)} data-testid={`trainer-${x}`}>
                  {te(`trainerAction.${x}`)}
                </Button>
              ))}
            </>
          }
        />
      </div>
      {a.scheduled_sessions_affected > 0 && a.status !== "active" ? <Alert tone="warning">{t("sessionsAffected", { n: a.scheduled_sessions_affected })}</Alert> : null}
      <Card>
        <CardContent className="pt-5">
          <FieldList>
            <FieldItem label={t("trainer")} wide>
              <TrainerName a={a} />
            </FieldItem>
            <FieldItem label={t("provider")} wide>
              <ProviderLabel p={a.provider} />
            </FieldItem>
            <FieldItem label={t("courses")} wide>
              <span className="flex flex-wrap gap-1">
                {a.course_codes.map((c) => (
                  <Link key={c} href={`/training-courses/${encodeURIComponent(c)}`} className="text-primary hover:underline">
                    <Code>{c}</Code>
                  </Link>
                ))}
              </span>
            </FieldItem>
            <FieldItem label={t("roles")}>{a.roles.map((r) => te(`trainerRole.${r}`)).join(" · ")}</FieldItem>
            <FieldItem label={t("valid")}>
              {date(a.valid_from)} – {date(a.valid_to)} {a.status === "active" ? <DaysLeft days={a.days_left} /> : null}
            </FieldItem>
            <FieldItem label={t("basis")} wide>
              {a.basis}
            </FieldItem>
            <FieldItem label={t("evidence")}>{t("evidenceCount", { n: a.evidence_attachment_ids.length })}</FieldItem>
            <FieldItem label={t("authorisedBy")}>
              <UserName u={a.authorised_by} /> · {dateTime(a.authorised_at)}
            </FieldItem>
            {a.status_reason ? (
              <FieldItem label={tc("reason")} wide>
                {a.status_reason}
              </FieldItem>
            ) : null}
          </FieldList>
        </CardContent>
      </Card>
      <HistoryPanel entityType="trainer_authorisation" entityId={a.id} projectId={project.id} />
      {edit ? <TrainerDialog project={project} a={a} onClose={() => setEdit(false)} /> : null}
      {action ? (
        <StepDialog
          title={t("confirmAction", { action: te(`trainerAction.${action}`) })}
          description={action === "reinstate" ? undefined : t("actionHint", { n: a.scheduled_sessions_affected })}
          confirmLabel={te(`trainerAction.${action}`)}
          destructive={action !== "reinstate"}
          disabled={reason.trim().length < 5}
          onClose={() => {
            setAction(null);
            setReason("");
          }}
          onConfirm={async () => {
            await unwrap(api.POST("/api/v1/trainer-authorisations/{authorisation_id}/transitions", { params: { path: { authorisation_id: a.id } }, body: { action, reason: reason.trim() } }));
            await refresh();
          }}
          testId="trainer-confirm"
        >
          <FormField id="ta-reason" label={tc("reason")} required>
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="ta-reason" />
          </FormField>
        </StepDialog>
      ) : null}
    </div>
  );
}
