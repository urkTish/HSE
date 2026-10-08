"use client";
import { Download, HeartPulse, Pencil, ShieldAlert, Stethoscope, UserX } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { CheckboxGroup } from "@/components/common/checkbox-group";
import { FormField } from "@/components/common/form-field";
import { PageHeader } from "@/components/common/page-header";
import { ProjectGate } from "@/components/common/project-gate";
import { ErrorState, LoadingState } from "@/components/common/states";
import { Code, StepDialog, WorkerLabel } from "@/components/access/common";
import { UserName } from "@/components/cert/common";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useDeployments } from "@/lib/api/access";
import { useFitnessRequirements, useHealthProfile, useMedicalRefresh, useWorkerFitness } from "@/lib/api/medical";
import { EXPOSURE_GROUPS } from "@/lib/med-enums";
import { useErrorMessage } from "@/lib/i18n-helpers";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { PlaceHoldDialog, RaiseReferralDialog } from "./holds";
import { FitnessCodeLabel, HookBandBadge, MedicalPlanSubNav, MedWorkerPicker, OutcomeBadge, RequirementStateBadge, RestrictionList, TierNote, useFitnessCatalogue, useMedCaps, workerHealthHref, type MedWorker } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];

/* ═════════════ lookup ═════════════ */

export function WorkerHealthLookupPage() {
  return <ProjectGate>{(p) => <Lookup project={p} />}</ProjectGate>;
}

function Lookup({ project }: { project: Project }) {
  const t = useTranslations("medical.worker");
  const router = useRouter();
  const [w, setW] = useState<MedWorker | null>(null);
  return (
    <div>
      <PageHeader title={t("lookupTitle")} description={t("lookupHint")} />
      <MedicalPlanSubNav />
      <Card>
        <CardContent className="flex flex-col gap-3 pt-5">
          <MedWorkerPicker
            id="wh-worker"
            projectId={project.id}
            value={w}
            onChange={(x) => {
              setW(x);
              if (x) router.push(workerHealthHref(x.worker_id, x.deployment_id));
            }}
            label={t("worker")}
          />
        </CardContent>
      </Card>
    </div>
  );
}

/* ═════════════ worker health page (WP, fitness status, requirements) ═════════════ */

export function WorkerHealthPage({ workerId }: { workerId: string }) {
  return <ProjectGate>{(p) => <WorkerHealth project={p} workerId={workerId} />}</ProjectGate>;
}

function WorkerHealth({ project, workerId }: { project: Project; workerId: string }) {
  const t = useTranslations("medical.worker");
  const te = useTranslations("enums");
  const locale = useLocale();
  const caps = useMedCaps(project.id);
  const { date } = useFormatters(project.id);
  const { label } = useFitnessCatalogue(project.id);
  const msg = useErrorMessage();
  const s = useSearchState();
  const fitness = useWorkerFitness(workerId, project.id, { enabled: caps.status });
  const f = fitness.data;
  // Without ?dep=, capability 46 holders resolve the deployment by worker number.
  const byNo = useDeployments(project.id, { q: f?.worker.worker_no ?? null, page_size: 5 }, { enabled: caps.names && !s.get("dep") && !!f });
  const depId = s.get("dep") || byNo.data?.items.find((x) => x.worker_id === workerId)?.id || "";
  const reqs = useFitnessRequirements(depId, {}, { enabled: caps.status && !!depId });
  const profile = useHealthProfile(depId, { enabled: (caps.status || caps.profileEdit) && !!depId });
  const [editProfile, setEditProfile] = useState(false);
  const [refer, setRefer] = useState(false);
  const [hold, setHold] = useState(false);
  const tier2 = f?.tier === "functional" || f?.tier === "clinical_admin";
  const tier3 = f?.tier === "clinical_admin";
  if (!caps.status) return <Alert tone="info">{t("noAccess")}</Alert>;
  if (fitness.isError) return <ErrorState error={fitness.error} onRetry={() => fitness.refetch()} />;
  if (!f) return <LoadingState />;
  const d: MedWorker = { worker_id: workerId, worker_no: f.worker.worker_no, full_name_en: f.worker.full_name_en, full_name_ar: f.worker.full_name_ar, deployment_id: depId || null };
  const trade = profile.data?.trade;
  async function report() {
    try {
      const r = await unwrap(api.GET("/api/v1/workers/{worker_id}/fitness-report", { params: { path: { worker_id: d.worker_id }, query: { purpose: "data_subject_request" } } }));
      const blob = new Blob([JSON.stringify(r, null, 2)], { type: "application/json" });
      const href = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = href;
      a.download = `fitness-report-${d.worker_no}.json`;
      a.click();
      URL.revokeObjectURL(href);
      toast.success(t("reportDone"));
    } catch (e) {
      toast.error(msg(e));
    }
  }
  const assessQuery = new URLSearchParams({ worker_no: d.worker_no }).toString();
  return (
    <div>
      <Breadcrumbs items={[{ label: t("lookupTitle"), href: "/worker-health" }, { label: d.worker_no }]} />
      <PageHeader
        title={
          <span className="inline-flex items-center gap-2">
            <HeartPulse aria-hidden className="size-6 text-primary" />
            <WorkerLabel w={{ id: d.worker_id, worker_no: d.worker_no, full_name_en: d.full_name_en, full_name_ar: d.full_name_ar }} link={caps.names} />
          </span>
        }
        description={`${project.code}${trade ? ` · ${te(`trade.${trade}`)}` : ""}`}
        badge={f?.on_hold ? (
          <Badge tone="danger" data-testid="on-hold">
            <UserX aria-hidden />
            {t("onHold")}
          </Badge>
        ) : null}
        actions={
          <>
            {caps.recordClinic || caps.submitExternal ? (
              <Button asChild>
                <Link href={`/fitness-assessments/new?${assessQuery}`} data-testid="wh-new-assessment">
                  <Stethoscope aria-hidden />
                  {t("newAssessment")}
                </Link>
              </Button>
            ) : null}
            {caps.refer ? (
              <Button variant="outline" onClick={() => setRefer(true)} data-testid="wh-refer">
                {t("refer")}
              </Button>
            ) : null}
            {caps.holdManage ? (
              <Button variant="destructive-outline" onClick={() => setHold(true)} data-testid="wh-hold">
                <ShieldAlert aria-hidden />
                {t("hold")}
              </Button>
            ) : null}
            {caps.subjectReport ? (
              <Button variant="outline" onClick={() => void report()} data-testid="wh-report">
                <Download aria-hidden />
                {t("report")}
              </Button>
            ) : null}
          </>
        }
      />
      <div className="flex flex-col gap-4">
        {caps.status ? (
          <Card data-testid="worker-fitness">
            <CardHeader>
              <CardTitle className="text-base">{t("fitnessTitle")}</CardTitle>
            </CardHeader>
            <CardContent>
              {f ? (
                <>
                  <TierNote tier={f.tier} />
                  <Table>
                    <THead>
                      <TR>
                        <TH>{t("code")}</TH>
                        <TH>{t("status")}</TH>
                        <TH>{t("validUntil")}</TH>
                        {tier2 ? <TH>{t("outcome")}</TH> : null}
                        {tier2 ? <TH>{t("restrictions")}</TH> : null}
                        {tier3 ? <TH>{t("reason")}</TH> : null}
                      </TR>
                    </THead>
                    <TBody>
                      {f.items.map((i) => (
                        <TR key={i.code} data-testid="fitness-item" data-code={i.code} data-status={i.status}>
                          <TD label={t("code")}>
                            <FitnessCodeLabel code={i.code} name={locale === "ar" ? i.name_ar : i.name_en} />
                            {!i.required ? <span className="block text-xs text-muted-foreground">{t("notRequired")}</span> : null}
                          </TD>
                          <TD label={t("status")}>
                            <HookBandBadge band={i.band} en={i.text_en} ar={i.text_ar} />
                            {i.hard_stop ? (
                              <Badge tone="danger" className="ms-1" data-testid="hard-stop">
                                {t("hardStop")}
                              </Badge>
                            ) : null}
                          </TD>
                          <TD label={t("validUntil")}>
                            <span data-testid="item-valid-until">{i.valid_until ? date(i.valid_until) : "—"}</span>
                          </TD>
                          {tier2 ? (
                            <TD label={t("outcome")}>
                              <OutcomeBadge outcome={i.outcome} />
                              {i.restriction_review_date ? <span className="block text-xs">{t("reviewOn", { d: date(i.restriction_review_date) })}</span> : null}
                              {i.unfit_review_date ? <span className="block text-xs">{t("reassessOn", { d: date(i.unfit_review_date) })}</span> : null}
                            </TD>
                          ) : null}
                          {tier2 ? (
                            <TD label={t("restrictions")}>
                              <RestrictionList items={i.restrictions} />
                            </TD>
                          ) : null}
                          {tier3 ? (
                            <TD label={t("reason")}>
                              {i.reason_code ? <span data-testid="item-reason">{te(`hookReason.${i.reason_code}`)}</span> : "—"}
                              {i.assessment_no ? <Code className="block text-xs">{i.assessment_no}</Code> : null}
                            </TD>
                          ) : null}
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                </>
              ) : null}
            </CardContent>
          </Card>
        ) : null}
        {caps.status ? (
          <Card data-testid="fitness-requirements">
            <CardHeader>
              <CardTitle className="text-base">{t("requirementsTitle")}</CardTitle>
            </CardHeader>
            <CardContent>
              {!depId ? (
                <p className="text-sm text-muted-foreground" data-testid="req-no-deployment">
                  {t("requirementsFromGaps")}
                </p>
              ) : reqs.isLoading ? (
                <LoadingState rows={2} />
              ) : reqs.isError ? (
                <ErrorState error={reqs.error} onRetry={() => reqs.refetch()} />
              ) : reqs.data?.items.length ? (
                <Table>
                  <THead>
                    <TR>
                      <TH>{t("code")}</TH>
                      <TH>{t("lines")}</TH>
                      <TH>{t("state")}</TH>
                      <TH>{t("dueDate")}</TH>
                      <TH>{t("validUntil")}</TH>
                      {tier2 ? <TH>{t("outcome")}</TH> : null}
                    </TR>
                  </THead>
                  <TBody>
                    {reqs.data.items.map((r) => (
                      <TR key={r.code} data-testid="req-row" data-code={r.code} data-state={r.state}>
                        <TD label={t("code")}>
                          <FitnessCodeLabel code={r.code} name={label(r.code)} />
                          <span className="mt-1 flex flex-wrap gap-1">
                            {r.hook_code ? <Badge tone="info">{t("hookCode")}</Badge> : null}
                            {r.critical ? <Badge tone="danger">{t("critical")}</Badge> : null}
                            {!r.counted ? <Badge tone="neutral">{t("notCounted")}</Badge> : null}
                          </span>
                        </TD>
                        <TD label={t("lines")}>
                          <span className="text-xs">{r.line_nos.join(" · ")}</span>
                        </TD>
                        <TD label={t("state")}>
                          <RequirementStateBadge state={r.state} />
                          {tier3 && r.reason_code ? <span className="block text-xs text-muted-foreground">{te(`hookReason.${r.reason_code}`)}</span> : null}
                        </TD>
                        <TD label={t("dueDate")}>{date(r.due_date)}</TD>
                        <TD label={t("validUntil")}>{r.valid_until ? date(r.valid_until) : "—"}</TD>
                        {tier2 ? (
                          <TD label={t("outcome")}>
                            <OutcomeBadge outcome={r.outcome} />
                          </TD>
                        ) : null}
                      </TR>
                    ))}
                  </TBody>
                </Table>
              ) : (
                <p className="text-sm text-muted-foreground">{t("noRequirements")}</p>
              )}
            </CardContent>
          </Card>
        ) : null}
        {profile.data ? (
          <Card data-testid="health-profile">
            <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
              <CardTitle className="text-base">{t("profileTitle")}</CardTitle>
              {caps.profileEdit ? (
                <Button size="sm" variant="outline" onClick={() => setEditProfile(true)} data-testid="edit-exposure">
                  <Pencil aria-hidden />
                  {t("editExposure")}
                </Button>
              ) : null}
            </CardHeader>
            <CardContent className="flex flex-col gap-3 text-sm">
              <p className="text-xs text-muted-foreground">{t("profileHint")}</p>
              <div className="flex flex-wrap gap-2" data-testid="exposure-groups">
                {profile.data.exposure_groups.length ? (
                  profile.data.exposure_groups.map((g) => (
                    <Badge key={g} tone="info" data-group={g}>
                      {te(`exposureGroup.${g}`)}
                    </Badge>
                  ))
                ) : (
                  <span className="text-muted-foreground">{t("noExposure")}</span>
                )}
              </div>
              {profile.data.history.length ? (
                <ul className="flex flex-col gap-1 text-xs text-muted-foreground">
                  {profile.data.history.map((h, i) => (
                    <li key={i}>
                      {date(h.from_date)} → {h.to_date ? date(h.to_date) : t("current")}: {h.value.map((g) => te(`exposureGroup.${g}`)).join(" · ") || "—"} · <UserName u={h.by} />
                    </li>
                  ))}
                </ul>
              ) : null}
            </CardContent>
          </Card>
        ) : null}
      </div>
      {editProfile && profile.data ? <ExposureDialog profile={profile.data} onClose={() => setEditProfile(false)} /> : null}
      {refer ? <RaiseReferralDialog project={project} worker={d} onClose={() => setRefer(false)} /> : null}
      {hold ? <PlaceHoldDialog project={project} worker={d} onClose={() => setHold(false)} /> : null}
    </div>
  );
}

function ExposureDialog({ profile, onClose }: { profile: S["HealthProfileRead"]; onClose: () => void }) {
  const t = useTranslations("medical.worker");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const refresh = useMedicalRefresh();
  const [groups, setGroups] = useState<S["ExposureGroup"][]>(profile.exposure_groups);
  const [reason, setReason] = useState("");
  const removed = profile.exposure_groups.some((g) => !groups.includes(g));
  return (
    <StepDialog
      title={t("editExposure")}
      description={t("exposureHint")}
      confirmLabel={tc("save")}
      testId="save-exposure"
      onConfirm={async () => {
        await unwrap(api.PATCH("/api/v1/deployments/{deployment_id}/health-profile", { params: { path: { deployment_id: profile.deployment_id } }, body: { exposure_groups: groups, reason: reason.trim() || null } }));
        toast.success(tc("saved"));
        await refresh();
      }}
      onClose={onClose}
    >
      <CheckboxGroup id="wh-groups" legend={t("exposureGroups")} options={EXPOSURE_GROUPS.map((g) => ({ value: g, label: te(`exposureGroup.${g}`) }))} value={groups} onChange={setGroups} />
      {removed ? (
        <FormField id="wh-reason" label={t("removeReason")} hint={t("removeReasonHint", { n: reason.trim().length })}>
          <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="wh-reason" />
        </FormField>
      ) : null}
    </StepDialog>
  );
}
