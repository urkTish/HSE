"use client";
import { CheckCircle2, XCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { PossibleIdHint } from "@/components/common/api-warnings";
import { Code, StepDialog, WorkerLabel } from "@/components/access/common";
import { UserName } from "@/components/cert/common";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useAcclimatisationPlan, useAcclimatisationPlans, useHeatRefresh } from "@/lib/api/heat";
import { PLAN_STATUSES, PLAN_TYPES } from "@/lib/heat-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { ChoiceMark, FreeText, HeatFieldSubNav, HeatReasonDialog, PlanStatusBadge, useHeatCaps } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];
type Plan = S["PlanRead"];
const PAGE_SIZE = 50;

/* ═════════════ plans register (§3.6, §4.2, P6b-3) ═════════════ */

export function AcclimatisationPlansPage() {
  return <ProjectGate>{(p) => <Plans project={p} />}</ProjectGate>;
}

function Plans({ project }: { project: Project }) {
  const t = useTranslations("heat.plans");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useHeatCaps(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll("status") as S["PlanStatus"][];
  const type = (s.get("type") ?? "") as S["PlanType"] | "";
  const q = useAcclimatisationPlans(project.id, { status: status.length ? status : null, plan_type: type || null, page, page_size: PAGE_SIZE }, { enabled: caps.view });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <HeatFieldSubNav />
      <ListToolbar>
        <MultiSelect id="pl-status" label={tc("status")} options={PLAN_STATUSES.map((x) => ({ value: x, label: te(`planStatus.${x}`) }))} value={status} onChange={(v) => s.set({ status: v })} />
        <SelectFilter id="pl-type" label={t("type")} value={type} onChange={(v) => s.set({ type: v })} options={PLAN_TYPES.map((x) => ({ value: x, label: te(`planType.${x}`) }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="plans-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("worker")}</TH>
                <TH>{t("type")}</TH>
                <TH>{t("trigger")}</TH>
                <TH>{t("schedule")}</TH>
                <TH>{t("progress")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((p) => (
                <TR key={p.id} data-testid="plan-row" data-no={p.plan_no} data-type={p.plan_type} data-status={p.status}>
                  <TD label={t("no")}>
                    <Link href={`/acclimatisation-plans/${p.id}`} className="font-medium text-primary hover:underline" data-testid="plan-link">
                      <Code>{p.plan_no}</Code>
                    </Link>
                  </TD>
                  <TD label={t("worker")}>
                    <WorkerLabel w={p.worker} />
                  </TD>
                  <TD label={t("type")}>
                    <span data-testid="plan-type">{te(`planType.${p.plan_type}`)}</span>
                  </TD>
                  <TD label={t("trigger")}>
                    <span data-testid="plan-trigger">{te(`planTrigger.${p.trigger.kind}`)}</span>
                    {p.trigger.ref ? <Code className="block text-xs text-muted-foreground">{p.trigger.ref}</Code> : null}
                  </TD>
                  <TD label={t("schedule")}>
                    <bdi className="ltr text-xs">{p.schedule_pct.map((x) => `${x}%`).join(" · ")}</bdi>
                  </TD>
                  <TD label={t("progress")}>{t("progressValue", { done: p.days.filter((d) => d.confirmed_at).length, total: p.days.length })}</TD>
                  <TD label={tc("status")}>
                    <PlanStatusBadge status={p.status} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState message={status.length || type ? undefined : t("empty")} />
      )}
    </div>
  );
}

/* ═════════════ plan detail (days, AP-3, AP-8, cancel) ═════════════ */

export function AcclimatisationPlanPage({ id }: { id: string }) {
  const q = useAcclimatisationPlan(id);
  if (q.isLoading) return <LoadingState />;
  if (q.isError || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const plan = q.data;
  return <ProjectById id={plan.project_id}>{(p) => <PlanDetail project={p} plan={plan} />}</ProjectById>;
}

function PlanDetail({ project, plan }: { project: Project; plan: Plan }) {
  const t = useTranslations("heat.plans");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useHeatCaps(project.id);
  const { date, dateTime } = useFormatters(project.id);
  const [confirm, setConfirm] = useState<S["PlanDay"] | null>(null);
  const [prior, setPrior] = useState(false);
  const [cancel, setCancel] = useState(false);
  const open = ["planned", "waiting_restriction", "active"].includes(plan.status);
  const day2Worked = plan.days.some((d) => d.day_no >= 2 && d.work_date);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={
          <>
            {t("detailTitle")} <Code>{plan.plan_no}</Code>
          </>
        }
        badge={<PlanStatusBadge status={plan.status} />}
        actions={
          caps.plan && open ? (
            <>
              {plan.plan_type === "new_worker" && !plan.prior_heat_experience && !day2Worked ? (
                <Button variant="outline" onClick={() => setPrior(true)} data-testid="plan-prior">
                  {t("prior")}
                </Button>
              ) : null}
              <Button variant="destructive-outline" onClick={() => setCancel(true)} data-testid="plan-cancel">
                {t("cancel")}
              </Button>
            </>
          ) : null
        }
      />
      <Card>
        <CardContent className="p-4">
          <FieldList>
            <FieldItem label={t("worker")}>
              <WorkerLabel w={plan.worker} />
            </FieldItem>
            <FieldItem label={t("type")}>
              <span data-testid="plan-type">{te(`planType.${plan.plan_type}`)}</span>
            </FieldItem>
            <FieldItem label={t("trigger")}>
              <span data-testid="plan-trigger">{te(`planTrigger.${plan.trigger.kind}`)}</span>
              {plan.trigger.ref ? (
                <>
                  {" "}
                  <Code data-testid="plan-trigger-ref">{plan.trigger.ref}</Code>
                </>
              ) : null}
              {plan.trigger.on ? <span className="ms-1 text-muted-foreground">· {date(plan.trigger.on)}</span> : null}
            </FieldItem>
            <FieldItem label={t("schedule")}>
              <bdi className="ltr">{plan.schedule_pct.map((x) => `${x}%`).join(" · ")}</bdi>
            </FieldItem>
            {plan.prior_heat_experience ? (
              <FieldItem label={t("priorShown")} wide>
                <FreeText>{String((plan.prior_heat_experience as { text?: string }).text ?? "")}</FreeText>
              </FieldItem>
            ) : null}
            {plan.status_reason ? (
              <FieldItem label={t("statusReason")} wide>
                <FreeText>{te.has(`planStatusReason.${plan.status_reason}` as never) ? te(`planStatusReason.${plan.status_reason}` as never) : plan.status_reason}</FreeText>
              </FieldItem>
            ) : null}
            {plan.completed_as_planned !== null ? <FieldItem label={t("asPlanned")}>{plan.completed_as_planned ? tc("yes") : tc("no")}</FieldItem> : null}
          </FieldList>
          {plan.status === "waiting_restriction" ? (
            <Alert tone="warning" className="mt-3" data-testid="plan-waiting">
              {t("waitingHint")}
            </Alert>
          ) : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("days")}</CardTitle>
          <p className="text-xs text-muted-foreground">{t("daysHint")}</p>
        </CardHeader>
        <CardContent>
          <Table data-testid="plan-days">
            <THead>
              <TR>
                <TH>{t("dayNo")}</TH>
                <TH>{t("workDate")}</TH>
                <TH>{t("maxPct")}</TH>
                <TH>{t("maxMinutes")}</TH>
                <TH>{t("confirmed")}</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {plan.days.map((d) => (
                <TR key={d.day_no} data-testid="plan-day" data-day={d.day_no} data-confirmed={d.confirmed_at ? "yes" : "no"}>
                  <TD label={t("dayNo")}>{d.day_no}</TD>
                  <TD label={t("workDate")}>{d.work_date ? date(d.work_date) : "—"}</TD>
                  <TD label={t("maxPct")}>
                    <bdi className="ltr">{d.max_pct} %</bdi>
                  </TD>
                  <TD label={t("maxMinutes")}>{t("minutes", { n: d.max_minutes })}</TD>
                  <TD label={t("confirmed")}>
                    {d.confirmed_at ? (
                      <span className="flex flex-col text-xs">
                        <Badge tone={d.followed ? "success" : "danger"}>
                          {d.followed ? <CheckCircle2 aria-hidden /> : <XCircle aria-hidden />}
                          {d.followed ? t("followed") : t("notFollowed")}
                        </Badge>
                        <span className="text-muted-foreground">
                          <UserName u={d.confirmed_by} /> · {dateTime(d.confirmed_at)}
                        </span>
                        <FreeText className="text-muted-foreground">{d.note}</FreeText>
                      </span>
                    ) : (
                      "—"
                    )}
                  </TD>
                  <TD>
                    {caps.plan && d.work_date && !d.confirmed_at ? (
                      <Button size="sm" variant="outline" onClick={() => setConfirm(d)} data-testid="day-confirm">
                        {t("confirmDay")}
                      </Button>
                    ) : null}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>
      {confirm ? <ConfirmDayDialog plan={plan} day={confirm} onClose={() => setConfirm(null)} /> : null}
      {prior ? <PriorDialog plan={plan} onClose={() => setPrior(false)} /> : null}
      {cancel ? (
        <HeatReasonDialog
          title={t("cancelTitle", { no: plan.plan_no })}
          confirmLabel={t("cancel")}
          onConfirm={async (reason) => {
            await unwrap(api.POST("/api/v1/acclimatisation-plans/{plan_id}/cancel", { params: { path: { plan_id: plan.id } }, body: { reason } }));
          }}
          onClose={() => setCancel(false)}
        />
      ) : null}
    </div>
  );
}

function ConfirmDayDialog({ plan, day, onClose }: { plan: Plan; day: S["PlanDay"]; onClose: () => void }) {
  const t = useTranslations("heat.plans");
  const refresh = useHeatRefresh();
  const [followed, setFollowed] = useState<"yes" | "no" | "">("");
  const [note, setNote] = useState("");
  return (
    <StepDialog
      title={t("confirmTitle", { n: day.day_no })}
      description={t("confirmHint", { pct: day.max_pct, minutes: day.max_minutes })}
      confirmLabel={t("confirmDay")}
      disabled={!followed || (followed === "no" && note.trim().length < 10)}
      testId="day-confirm-submit"
      onConfirm={async () => {
        await unwrap(
          api.POST("/api/v1/acclimatisation-plans/{plan_id}/days/{day_no}/confirm", {
            params: { path: { plan_id: plan.id, day_no: day.day_no } },
            body: { followed: followed === "yes", note: note.trim() || null },
          }),
        );
        await refresh();
      }}
      onClose={onClose}
    >
      <fieldset className="grid grid-cols-2 gap-2">
        <legend className="mb-1 text-sm font-medium">{t("followedQ")}</legend>
        {(["yes", "no"] as const).map((v) => (
          <Button key={v} type="button" variant={followed === v ? "default" : "outline"} className="min-h-12" onClick={() => setFollowed(v)} aria-pressed={followed === v} data-testid={`followed-${v}`}>
            <ChoiceMark on={followed === v} />
            {v === "yes" ? t("followed") : t("notFollowed")}
          </Button>
        ))}
      </fieldset>
      <FormField id="pd-note" label={t("note")} required={followed === "no"} hint={t("noteHint")}>
        <Textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} data-testid="pd-note" />
      </FormField>
      <PossibleIdHint text={note} />
    </StepDialog>
  );
}

function PriorDialog({ plan, onClose }: { plan: Plan; onClose: () => void }) {
  const t = useTranslations("heat.plans");
  const tcm = useTranslations("heat.common");
  const refresh = useHeatRefresh();
  const [text, setText] = useState("");
  return (
    <StepDialog
      title={t("prior")}
      description={t("priorHint")}
      confirmLabel={t("priorSave")}
      disabled={text.trim().length < 20}
      testId="prior-confirm"
      onConfirm={async () => {
        await unwrap(api.POST("/api/v1/acclimatisation-plans/{plan_id}/prior-experience", { params: { path: { plan_id: plan.id } }, body: { text: text.trim() } }));
        await refresh();
      }}
      onClose={onClose}
    >
      <FormField id="pr-text" label={t("priorShown")} required hint={tcm("reasonMin", { min: 20, n: text.trim().length })}>
        <Textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={300} data-testid="pr-text" />
      </FormField>
      <PossibleIdHint text={text} />
    </StepDialog>
  );
}
