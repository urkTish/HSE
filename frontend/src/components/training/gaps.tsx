"use client";
import { CalendarPlus, Plus } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ExportButtons } from "@/components/common/export-buttons";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { MultiSelect } from "@/components/common/multi-select";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { useProjectOptions } from "@/components/common/pickers";
import { ProjectGate } from "@/components/common/project-gate";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "@/components/common/states";
import { StatusBadge } from "@/components/common/status-badge";
import {
  Code,
  DaysLeft,
  DeploymentPicker,
  StepDialog,
  WorkerLabel,
} from "@/components/access/common";
import { Stat, UserName } from "@/components/cert/common";
import { Link, useRouter } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import {
  useRefresherPlan,
  useTrainingExemptions,
  useTrainingGaps,
  useTrainingGapSummary,
  useTrainingMatrix,
  useTrainingRefresh,
  useTrainingRequirements,
} from "@/lib/api/training";
import { TRADES } from "@/lib/access-enums";
import { PLAN_STATES, REQUIREMENT_STATES } from "@/lib/train-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import {
  DateFilter,
  PlanStateBadge,
  RequirementStateBadge,
  RequirementText,
  TrainingMatrixSubNav,
  useCourseCatalogue,
  useTrainingCaps,
  isOn,
} from "./common";

type S = Schemas;
const PAGE_SIZE = 50;
const DEFAULT_STATES: S["RequirementState"][] = ["gap", "due", "expiring"];

/* ───────────── gap register + summary ───────────── */

export function GapsPage() {
  return <ProjectGate>{(p) => <Gaps project={p} />}</ProjectGate>;
}

function Gaps({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("training.gaps");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const caps = useTrainingCaps(project.id);
  const opts = useProjectOptions(project.id);
  const { courses } = useCourseCatalogue(project.id);
  const { date } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const states = s.getAll("state") as S["RequirementState"][];
  const trades = s.getAll("trade") as S["Trade"][];
  const codes = s.getAll("course_code");
  const asOf = s.get("as_of") || null;
  const eng = s.get("engagement_id") || null;
  const [exempt, setExempt] = useState<S["GapRow"] | null>(null);
  const summary = useTrainingGapSummary(project.id, {
    as_of: asOf,
    engagement_id: eng,
    include_subcontractors: true,
  });
  // GP-2: viewers see counts only — the list is requested only with record-view rights.
  const q = useTrainingGaps(
    project.id,
    {
      as_of: asOf,
      state: states.length ? states : DEFAULT_STATES,
      engagement_id: eng,
      include_subcontractors: true,
      trade: trades.length ? trades : null,
      course_code: codes.length ? codes : null,
      hook_code: isOn(s.get("hook_code")) ? true : null,
      on_live_work: isOn(s.get("on_live_work")) ? true : null,
      counted_only: isOn(s.get("counted_only")),
      page,
      page_size: PAGE_SIZE,
    },
    { enabled: caps.recordView },
  );
  const items = q.data?.items ?? [];
  const tot = summary.data?.totals;
  const label = (r: S["GapSummaryRow"]) =>
    locale === "ar" ? r.label_ar : r.label_en;
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <TrainingMatrixSubNav />
      {summary.data && tot ? (
        <div className="mb-4 flex flex-col gap-3" data-testid="gap-summary">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            <Stat
              label={t("counted")}
              value={tot.counted}
              testId="sum-counted"
            />
            <Stat
              label={te("requirementState.met")}
              value={tot.met}
              tone="success"
              testId="sum-met"
            />
            <Stat
              label={te("requirementState.expiring")}
              value={tot.expiring}
              tone={tot.expiring ? "warning" : undefined}
              testId="sum-expiring"
            />
            <Stat
              label={te("requirementState.gap")}
              value={tot.gap}
              tone={tot.gap ? "danger" : undefined}
              testId="sum-gap"
            />
            <Stat
              label={te("requirementState.due")}
              value={tot.due}
              testId="sum-due"
            />
            <Stat
              label={te("requirementState.exempt")}
              value={tot.exempt}
              testId="sum-exempt"
            />
          </div>
          <p className="text-xs text-muted-foreground">
            {t("asOfNote", { date: date(summary.data.as_of) })}
          </p>
          <div className="grid gap-3 lg:grid-cols-3">
            {(
              [
                ["byCourse", summary.data.by_course],
                ["byContractor", summary.data.by_contractor],
                ["byTrade", summary.data.by_trade],
              ] as const
            ).map(([k, rows]) => (
              <Card key={k}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">{t(k)}</CardTitle>
                </CardHeader>
                <CardContent>
                  {rows.length ? (
                    <div className="max-h-72 overflow-y-auto">
                      <table
                        className="w-full text-sm"
                        data-testid={`gap-${k}`}
                      >
                        <thead>
                          <tr className="text-xs text-muted-foreground">
                            <th className="text-start font-medium">
                              {t("item")}
                            </th>
                            <th className="text-end font-medium">
                              {t("counted")}
                            </th>
                            <th className="text-end font-medium">
                              {te("requirementState.gap")}
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {[...rows]
                            .sort(
                              (a, b) => b.gap - a.gap || b.counted - a.counted,
                            )
                            .map((r) => (
                              <tr
                                key={r.key}
                                className="border-t"
                                data-key={r.key}
                              >
                                <td className="py-1">{label(r)}</td>
                                <td className="ltr py-1 text-end tabular-nums">
                                  {r.counted}
                                </td>
                                <td
                                  className={`ltr py-1 text-end tabular-nums ${r.gap ? "font-semibold text-destructive" : ""}`}
                                >
                                  {r.gap}
                                </td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">—</p>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      ) : summary.isError ? (
        <ErrorState error={summary.error} onRetry={() => summary.refetch()} />
      ) : (
        <LoadingState rows={2} />
      )}
      {caps.recordView ? (
        <>
          <ListToolbar
            actions={
              caps.export ? (
                <ExportButtons
                  dataset="training_gaps"
                  params={{ project_id: project.id }}
                />
              ) : null
            }
          >
            <MultiSelect
              id="gap-state"
              label={t("state")}
              options={REQUIREMENT_STATES.map((x) => ({
                value: x,
                label: te(`requirementState.${x}`),
              }))}
              value={states}
              onChange={(v) => s.set({ state: v })}
              allLabel={t("defaultStates")}
            />
            <DateFilter
              id="gap-asof"
              label={t("asOf")}
              value={s.get("as_of") ?? ""}
              onChange={(v) => s.set({ as_of: v })}
            />
            <SelectFilter
              id="gap-eng"
              label={tc("contractor")}
              value={s.get("engagement_id") ?? ""}
              onChange={(v) => s.set({ engagement_id: v })}
              options={opts.engagements.map((x) => ({
                value: x.value,
                label: x.label,
              }))}
            />
            <MultiSelect
              id="gap-course"
              label={t("course")}
              options={courses.map((c) => ({ value: c.code, label: c.code }))}
              value={codes}
              onChange={(v) => s.set({ course_code: v })}
            />
            <MultiSelect
              id="gap-trade"
              label={t("trade")}
              options={TRADES.map((x) => ({
                value: x,
                label: te(`trade.${x}`),
              }))}
              value={trades}
              onChange={(v) => s.set({ trade: v })}
            />
            <SelectFilter
              id="gap-hook"
              label={t("hookOnly")}
              value={isOn(s.get("hook_code")) ? "1" : ""}
              onChange={(v) => s.set({ hook_code: v })}
              options={[{ value: "1", label: tc("yes") }]}
            />
            <SelectFilter
              id="gap-live"
              label={t("onLiveWork")}
              value={isOn(s.get("on_live_work")) ? "1" : ""}
              onChange={(v) => s.set({ on_live_work: v })}
              options={[{ value: "1", label: tc("yes") }]}
            />
            <SelectFilter
              id="gap-counted"
              label={t("countedOnly")}
              value={isOn(s.get("counted_only")) ? "1" : ""}
              onChange={(v) => s.set({ counted_only: v })}
              options={[{ value: "1", label: tc("yes") }]}
            />
          </ListToolbar>
          {q.isLoading ? (
            <LoadingState />
          ) : q.isError ? (
            <ErrorState error={q.error} onRetry={() => q.refetch()} />
          ) : items.length ? (
            <>
              <Table data-testid="gaps-table">
                <THead>
                  <TR>
                    <TH>{t("worker")}</TH>
                    <TH>{t("requirement")}</TH>
                    <TH>{t("due")}</TH>
                    <TH>{t("state")}</TH>
                    <TH>{t("booked")}</TH>
                    <TH>{t("liveWork")}</TH>
                    <TH>
                      <span className="sr-only">{tc("actions")}</span>
                    </TH>
                  </TR>
                </THead>
                <TBody>
                  {items.map((g, i) => (
                    <TR
                      key={`${g.deployment_id}-${i}`}
                      data-testid="gap-row"
                      data-worker={g.worker.worker_no}
                      data-state={g.state}
                      data-course={
                        g.requirement.course_code ??
                        g.requirement.any_of?.join("|") ??
                        ""
                      }
                    >
                      <TD label={t("worker")}>
                        <WorkerLabel w={g.worker} link />
                        <span className="block text-xs text-muted-foreground">
                          {g.engagement.short_code}
                          {g.trade ? ` · ${te(`trade.${g.trade}`)}` : ""}
                        </span>
                      </TD>
                      <TD label={t("requirement")}>
                        <RequirementText r={g.requirement} />
                        <span className="ms-1 inline-flex gap-1">
                          {g.critical ? (
                            <Badge tone="danger">{t("critical")}</Badge>
                          ) : g.hook_code ? (
                            <Badge tone="info">{t("hook")}</Badge>
                          ) : null}
                          {g.level === "recommended" ? (
                            <Badge tone="neutral">
                              {te("matrixLevel.recommended")}
                            </Badge>
                          ) : null}
                        </span>
                        <span className="block text-xs text-muted-foreground">
                          {g.line_nos.join(", ")}
                        </span>
                      </TD>
                      <TD label={t("due")}>
                        <span className="ltr">{date(g.due_date)}</span>
                        {g.days_overdue ? (
                          <span className="block text-xs font-medium text-destructive">
                            {t("daysOverdue", { n: g.days_overdue })}
                          </span>
                        ) : null}
                        {g.valid_until ? (
                          <span className="block text-xs text-muted-foreground">
                            {t("validUntil", { date: date(g.valid_until) })}
                          </span>
                        ) : null}
                      </TD>
                      <TD label={t("state")}>
                        <RequirementStateBadge state={g.state} />
                      </TD>
                      <TD label={t("booked")}>
                        {g.booked_session ? (
                          <Link
                            href={`/training-sessions/${g.booked_session.id}`}
                            className="text-primary hover:underline"
                          >
                            <Code>{g.booked_session.session_no}</Code>
                          </Link>
                        ) : (
                          "—"
                        )}
                      </TD>
                      <TD label={t("liveWork")}>
                        {g.live_permits.length || g.live_wap_nos.length ? (
                          <span
                            className="flex flex-wrap gap-1"
                            data-testid="gap-live-work"
                          >
                            {g.live_permits.map((p) => (
                              <Link
                                key={p.id}
                                href={`/permits/${p.id}`}
                                className="text-primary hover:underline"
                              >
                                <Code>{p.display_no}</Code>
                              </Link>
                            ))}
                            {g.live_wap_nos.map((w) => (
                              <Code key={w}>{w}</Code>
                            ))}
                          </span>
                        ) : (
                          "—"
                        )}
                      </TD>
                      <TD label={tc("actions")}>
                        {caps.matrixEdit &&
                        g.state !== "exempt" &&
                        !g.hook_code ? (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setExempt(g)}
                            data-testid="gap-exempt"
                          >
                            {t("exempt")}
                          </Button>
                        ) : null}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
              <Pagination
                page={page}
                pageSize={PAGE_SIZE}
                total={q.data?.total ?? 0}
                onPage={(p) => s.set({ page: p })}
              />
            </>
          ) : (
            <EmptyState message={t("empty")} />
          )}
        </>
      ) : (
        <p
          className="text-sm text-muted-foreground"
          data-testid="gaps-counts-only"
        >
          {t("countsOnly")}
        </p>
      )}
      {exempt ? (
        <ExemptionDialog
          project={project}
          deploymentId={exempt.deployment_id}
          worker={exempt.worker}
          onClose={() => setExempt(null)}
        />
      ) : null}
    </div>
  );
}

/* ───────────── exemptions ───────────── */

export function ExemptionsPage() {
  return <ProjectGate>{(p) => <Exemptions project={p} />}</ProjectGate>;
}

function Exemptions({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("training.exemptions");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useTrainingCaps(project.id);
  const { date, dateTime } = useFormatters(project.id);
  const refresh = useTrainingRefresh();
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = s.getAll(
    "status",
  ) as S["app__core__train_enums__ExemptionStatus"][];
  const q = useTrainingExemptions(project.id, {
    status: status.length ? status : null,
    page,
    page_size: PAGE_SIZE,
  });
  const [create, setCreate] = useState(false);
  const [withdraw, setWithdraw] = useState<
    S["app__schemas__training_matrix__ExemptionRead"] | null
  >(null);
  const [reason, setReason] = useState("");
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.matrixEdit ? (
            <Button onClick={() => setCreate(true)} data-testid="new-exemption">
              <Plus aria-hidden />
              {t("new")}
            </Button>
          ) : null
        }
      />
      <TrainingMatrixSubNav />
      <ListToolbar>
        <MultiSelect
          id="ex-status"
          label={tc("status")}
          options={(["active", "withdrawn", "expired"] as const).map((x) => ({
            value: x,
            label: te(`trainingExemptionStatus.${x}`),
          }))}
          value={status}
          onChange={(v) => s.set({ status: v })}
        />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="exemptions-table">
            <THead>
              <TR>
                <TH>{t("worker")}</TH>
                <TH>{t("requirement")}</TH>
                <TH>{tc("reason")}</TH>
                <TH>{t("validUntil")}</TH>
                <TH>{t("granted")}</TH>
                <TH>{tc("status")}</TH>
                <TH>
                  <span className="sr-only">{tc("actions")}</span>
                </TH>
              </TR>
            </THead>
            <TBody>
              {items.map((x) => (
                <TR key={x.id} data-testid="exemption-row">
                  <TD label={t("worker")}>
                    <WorkerLabel w={x.worker} link />
                  </TD>
                  <TD label={t("requirement")}>
                    <RequirementText r={x.requirement} />
                    <span className="block text-xs text-muted-foreground">
                      {x.line_no}
                    </span>
                  </TD>
                  <TD label={tc("reason")}>
                    <span className="text-sm">{x.reason}</span>
                  </TD>
                  <TD label={t("validUntil")}>{date(x.valid_until)}</TD>
                  <TD label={t("granted")}>
                    <span className="text-xs">
                      <UserName u={x.granted_by} /> · {dateTime(x.granted_at)}
                    </span>
                  </TD>
                  <TD label={tc("status")}>
                    <StatusBadge
                      status={x.status}
                      label={te(`trainingExemptionStatus.${x.status}`)}
                    />
                  </TD>
                  <TD label={tc("actions")}>
                    {caps.matrixEdit && x.status === "active" ? (
                      <Button
                        size="sm"
                        variant="destructive-outline"
                        onClick={() => setWithdraw(x)}
                        data-testid="withdraw-exemption"
                      >
                        {t("withdraw")}
                      </Button>
                    ) : null}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={q.data?.total ?? 0}
            onPage={(p) => s.set({ page: p })}
          />
        </>
      ) : (
        <EmptyState />
      )}
      {create ? (
        <ExemptionDialog project={project} onClose={() => setCreate(false)} />
      ) : null}
      {withdraw ? (
        <StepDialog
          title={t("withdrawTitle")}
          description={t("withdrawHint")}
          confirmLabel={t("withdraw")}
          destructive
          disabled={reason.trim().length < 5}
          onClose={() => {
            setWithdraw(null);
            setReason("");
          }}
          onConfirm={async () => {
            await unwrap(
              api.POST("/api/v1/training-exemptions/{exemption_id}/withdraw", {
                params: { path: { exemption_id: withdraw.id } },
                body: { reason: reason.trim() },
              }),
            );
            await refresh();
          }}
          testId="withdraw-exemption-confirm"
        >
          <FormField id="ex-wd-reason" label={tc("reason")} required>
            <Textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={300}
            />
          </FormField>
        </StepDialog>
      ) : null}
    </div>
  );
}

/** Grant an exemption (MX-10): deployment + one requirement line + reason ≥ 30 chars + end date. */
export function ExemptionDialog({
  project,
  deploymentId,
  worker,
  onClose,
}: {
  project: S["ProjectRead"];
  deploymentId?: string;
  worker?: S["WorkerRef"];
  onClose: () => void;
}) {
  const t = useTranslations("training.exemptions");
  const tc = useTranslations("common");
  const refresh = useTrainingRefresh();
  const [dep, setDep] = useState<S["DeploymentRead"] | null>(null);
  const did = deploymentId ?? dep?.id ?? "";
  const reqs = useTrainingRequirements(did, null, { enabled: Boolean(did) });
  const [line, setLine] = useState("");
  const [reason, setReason] = useState("");
  const [until, setUntil] = useState("");
  const options = (reqs.data?.requirements ?? []).filter(
    (r) => !r.hook_code && r.state !== "met" && r.state !== "exempt",
  );
  async function save() {
    await unwrap(
      api.POST("/api/v1/projects/{project_id}/training-exemptions", {
        params: { path: { project_id: project.id } },
        body: {
          deployment_id: did,
          line_id: line,
          reason: reason.trim(),
          valid_until: until,
        },
      }),
    );
    await refresh();
    toast.success(tc("saved"));
  }
  return (
    <StepDialog
      title={t("new")}
      description={t("newHint")}
      confirmLabel={t("grant")}
      onConfirm={save}
      onClose={onClose}
      disabled={!did || !line || reason.trim().length < 30 || !until}
      wide
      testId="save-exemption"
    >
      {worker ? (
        <p className="text-sm">
          <WorkerLabel w={worker} />
        </p>
      ) : (
        <DeploymentPicker
          id="ex-dep"
          projectId={project.id}
          value={dep}
          onChange={setDep}
          label={t("worker")}
          required
          status={["mobilised"]}
        />
      )}
      <ExemptionLineSelect
        projectId={project.id}
        reqs={options}
        value={line}
        onChange={setLine}
      />
      <FormField
        id="ex-reason"
        label={tc("reason")}
        required
        hint={t("reasonHint")}
      >
        <Textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          maxLength={500}
          data-testid="ex-reason"
        />
      </FormField>
      <FormField id="ex-until" label={t("validUntil")} required>
        <Input
          type="date"
          className="ltr"
          value={until}
          onChange={(e) => setUntil(e.target.value)}
          data-testid="ex-until"
        />
      </FormField>
    </StepDialog>
  );
}

/** Lines are picked by line number; the matrix query resolves the line id. */
function ExemptionLineSelect({
  projectId,
  reqs,
  value,
  onChange,
}: {
  projectId: string;
  reqs: S["app__schemas__training_matrix__RequirementStatus"][];
  value: string;
  onChange: (id: string) => void;
}) {
  const t = useTranslations("training.exemptions");
  const tc = useTranslations("common");
  const matrix = useTrainingMatrix(projectId, {}).data?.lines ?? [];
  const lineNos = new Set(reqs.flatMap((r) => r.line_nos));
  const lines = matrix.filter((l) => lineNos.has(l.line_no));
  return (
    <FormField
      id="ex-line"
      label={t("requirement")}
      required
      hint={t("lineHint")}
    >
      <Select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        data-testid="ex-line"
      >
        <option value="">{tc("select")}</option>
        {lines.map((l) => (
          <option key={l.id} value={l.id}>
            {l.line_no} —{" "}
            {l.requirement.course_code ?? l.requirement.any_of?.join(" / ")}
          </option>
        ))}
      </Select>
    </FormField>
  );
}

/* ───────────── refresher plan ───────────── */

export function RefresherPlanPage() {
  return <ProjectGate>{(p) => <RefresherPlan project={p} />}</ProjectGate>;
}

function RefresherPlan({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("training.plan");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useTrainingCaps(project.id);
  const opts = useProjectOptions(project.id);
  const router = useRouter();
  const { courses } = useCourseCatalogue(project.id);
  const { date } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const states = s.getAll("state") as S["RefresherPlanState"][];
  const codes = s.getAll("course_code");
  const q = useRefresherPlan(project.id, {
    as_of: s.get("as_of") || null,
    state: states.length ? states : null,
    course_code: codes.length ? codes : null,
    engagement_id: s.get("engagement_id") || null,
    due_within_days: s.getInt("due_within_days", 0) || null,
    page,
    page_size: PAGE_SIZE,
  });
  const items = q.data?.items ?? [];
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const pickedItems = items.filter((i) => picked.has(i.record.id));
  const pickedCourse = pickedItems[0]?.course.code ?? null;
  const oneCourse = pickedItems.every((i) => i.course.code === pickedCourse);
  function toggle(id: string, on: boolean) {
    const n = new Set(picked);
    if (on) n.add(id);
    else n.delete(id);
    setPicked(n);
  }
  function fromPlan(course: string, ids: string[]) {
    const p = new URLSearchParams({ from_plan: "1", course });
    if (ids.length) p.set("records", ids.join(","));
    router.push(`/training-sessions/new?${p.toString()}`);
  }
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.sessionManage && pickedItems.length && pickedCourse ? (
            <Button
              disabled={!oneCourse}
              onClick={() =>
                fromPlan(
                  pickedCourse,
                  pickedItems.map((i) => i.record.id),
                )
              }
              data-testid="plan-create-session"
            >
              <CalendarPlus aria-hidden />
              {oneCourse
                ? t("createSessionFor", {
                    n: pickedItems.length,
                    code: pickedCourse,
                  })
                : t("oneCourseOnly")}
            </Button>
          ) : null
        }
      />
      <TrainingMatrixSubNav />
      <ListToolbar>
        <MultiSelect
          id="plan-state"
          label={t("state")}
          options={PLAN_STATES.map((x) => ({
            value: x,
            label: te(`planState.${x}`),
          }))}
          value={states}
          onChange={(v) => s.set({ state: v })}
        />
        <MultiSelect
          id="plan-course"
          label={t("course")}
          options={courses.map((c) => ({ value: c.code, label: c.code }))}
          value={codes}
          onChange={(v) => s.set({ course_code: v })}
        />
        <SelectFilter
          id="plan-eng"
          label={tc("contractor")}
          value={s.get("engagement_id") ?? ""}
          onChange={(v) => s.set({ engagement_id: v })}
          options={opts.engagements.map((x) => ({
            value: x.value,
            label: x.label,
          }))}
        />
        <SelectFilter
          id="plan-within"
          label={t("dueWithin")}
          value={s.get("due_within_days") ?? ""}
          onChange={(v) => s.set({ due_within_days: v })}
          options={[
            { value: "14", label: t("days", { n: 14 }) },
            { value: "30", label: t("days", { n: 30 }) },
            { value: "60", label: t("days", { n: 60 }) },
          ]}
        />
        <DateFilter
          id="plan-asof"
          label={t("asOf")}
          value={s.get("as_of") ?? ""}
          onChange={(v) => s.set({ as_of: v })}
        />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="plan-table">
            <THead>
              <TR>
                {caps.sessionManage ? (
                  <TH>
                    <span className="sr-only">{t("select")}</span>
                  </TH>
                ) : null}
                <TH>{t("worker")}</TH>
                <TH>{t("course")}</TH>
                <TH>{t("validUntil")}</TH>
                <TH>{t("dueFrom")}</TH>
                <TH>{t("booked")}</TH>
                <TH>{t("state")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((i) => (
                <TR
                  key={i.record.id}
                  data-testid="plan-row"
                  data-worker={i.worker.worker_no}
                  data-course={i.course.code}
                  data-state={i.state}
                >
                  {caps.sessionManage ? (
                    <TD label={t("select")}>
                      <Checkbox
                        aria-label={t("select")}
                        checked={picked.has(i.record.id)}
                        disabled={Boolean(i.booked_session)}
                        onChange={(e) => toggle(i.record.id, e.target.checked)}
                        data-testid="plan-pick"
                      />
                    </TD>
                  ) : null}
                  <TD label={t("worker")}>
                    <WorkerLabel w={i.worker} link />
                    <span className="block text-xs text-muted-foreground">
                      {i.engagement.short_code}
                      {i.language
                        ? ` · ${te(`workerLanguage.${i.language}`)}`
                        : ""}
                    </span>
                  </TD>
                  <TD label={t("course")}>
                    <Code className="font-medium">{i.course.code}</Code>
                    <span className="block text-xs text-muted-foreground">
                      <Link
                        href={`/training-records/${i.record.id}`}
                        className="hover:underline"
                      >
                        <Code>{i.record.record_no}</Code>
                      </Link>
                    </span>
                  </TD>
                  <TD label={t("validUntil")}>
                    <span className="ltr">{date(i.valid_until)}</span>{" "}
                    <DaysLeft days={i.days_left} />
                  </TD>
                  <TD label={t("dueFrom")}>
                    <span className="ltr">{date(i.refresher_due_from)}</span>
                    {i.reason_required ? (
                      <span className="block text-xs text-muted-foreground">
                        {i.reason_required}
                      </span>
                    ) : null}
                  </TD>
                  <TD label={t("booked")}>
                    {i.booked_session ? (
                      <Link
                        href={`/training-sessions/${i.booked_session.id}`}
                        className="text-primary hover:underline"
                      >
                        <Code>{i.booked_session.session_no}</Code>
                        <span className="block text-xs text-muted-foreground ltr">
                          {date(i.booked_session.first_day)}
                        </span>
                      </Link>
                    ) : (
                      "—"
                    )}
                  </TD>
                  <TD label={t("state")}>
                    <PlanStateBadge state={i.state} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={q.data?.total ?? 0}
            onPage={(p) => s.set({ page: p })}
          />
        </>
      ) : (
        <EmptyState message={t("empty")} />
      )}
      {caps.sessionManage && codes.length === 1 && !pickedItems.length ? (
        <div className="mt-4">
          <Button
            variant="outline"
            onClick={() => fromPlan(codes[0] as string, [])}
            data-testid="plan-create-session-course"
          >
            <CalendarPlus aria-hidden />
            {t("createSessionCourse", { code: codes[0] as string })}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
