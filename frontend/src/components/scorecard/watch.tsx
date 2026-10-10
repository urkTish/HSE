"use client";
import { Eye, ShieldAlert } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Code, StepDialog } from "@/components/access/common";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { Choices, DayDue } from "@/components/followup/common";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useCorrectiveActions } from "@/lib/api/hse";
import { useEngagements } from "@/lib/api/queries";
import { usePerformanceSummary, useScRefresh, useSuspensionForm, useWatchEntry, useWatchList } from "@/lib/api/scorecard";
import { useDisplay } from "@/lib/digits";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { GradeBadge, ScBadge, ScSubNav, WatchLevelBadge, useScCaps } from "./common";

type S = Schemas;
type Entry = S["ScWatchRead"];

/* ═════════════ watch-list register (§3.5, §8.3) ═════════════ */

export function WatchListPage() {
  return <ProjectGate>{(p) => <Register project={p} />}</ProjectGate>;
}

function Register({ project }: { project: S["ProjectRead"] }) {
  const t = useTranslations("sc.watch");
  const tc = useTranslations("common");
  const te = useTranslations("enums");
  const caps = useScCaps(project.id);
  const show = useDisplay(project.id);
  const { date } = useFormatters(project.id);
  const s = useSearchState();
  const status = (s.get("status") as S["ScWatchStatus"] | null) ?? "";
  const q = useWatchList(project.id, { status: status || null, page_size: 200 }, { enabled: caps.view });
  const [open, setOpen] = useState(false);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.manage ? (
            <Button onClick={() => setOpen(true)} data-testid="wl-open">
              <Eye aria-hidden />
              {t("openManual")}
            </Button>
          ) : null
        }
      />
      <ScSubNav />
      <ListToolbar>
        <SelectFilter id="wl-status" label={t("status")} value={status} onChange={(v) => s.set({ status: v || null })} options={(["open", "closed"] as const).map((x) => ({ value: x, label: te(`scWatchStatus.${x}`) }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <Table data-testid="wl-list">
          <THead>
            <TR>
              <TH>{t("no")}</TH>
              <TH>{t("engagement")}</TH>
              <TH>{t("level")}</TH>
              <TH>{t("status")}</TH>
              <TH className="text-end">{t("baseline")}</TH>
              <TH>{t("opened")}</TH>
              <TH>{t("proposal")}</TH>
            </TR>
          </THead>
          <TBody>
            {items.map((w) => (
              <TR key={w.id} data-testid="wl-row" data-engagement={w.engagement_code} data-status={w.status}>
                <TD label={t("no")}>
                  <Link href={`/watch-list/${w.id}`} className="text-primary hover:underline">
                    <Code>{w.entry_no}</Code>
                  </Link>
                </TD>
                <TD label={t("engagement")}>
                  <Code>{w.engagement_code}</Code>
                </TD>
                <TD label={t("level")}>
                  <WatchLevelBadge level={w.level} />
                </TD>
                <TD label={t("status")}>
                  <ScBadge group="scWatchStatus" status={w.status} />
                </TD>
                <TD label={t("baseline")} className="text-end tabular-nums">
                  {w.baseline_score ? show(Number(w.baseline_score).toFixed(1)) : "—"}
                </TD>
                <TD label={t("opened")}>{date(w.opened_at)}</TD>
                <TD label={t("proposal")}>{w.proposal ? <span className="font-medium text-warning">{te(`scWatchProposal.${w.proposal}`)}</span> : "—"}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <EmptyState message={t("empty")} />
      )}
      {open ? <OpenDialog projectId={project.id} onClose={() => setOpen(false)} /> : null}
    </div>
  );
}

function OpenDialog({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const t = useTranslations("sc.watch");
  const tf = useTranslations("fu.common");
  const refresh = useScRefresh();
  const engs = useEngagements(projectId, { page_size: 200 });
  const [eng, setEng] = useState("");
  const [reason, setReason] = useState("");
  const n = reason.trim().length;
  return (
    <StepDialog
      title={t("openTitle")}
      description={t("openBody")}
      confirmLabel={t("openConfirm")}
      testId="wl-open-confirm"
      disabled={!eng || n < 20}
      onConfirm={async () => {
        const w = await unwrap(api.POST("/api/v1/projects/{project_id}/watch-list", { params: { path: { project_id: projectId } }, body: { engagement_id: eng, reason: reason.trim() } }));
        await refresh();
        toast.success(t("opened", { no: w.entry_no }));
      }}
      onClose={onClose}
    >
      <FormField id="wl-eng" label={t("engagement")} required>
        <Select id="wl-eng" value={eng} onChange={(e) => setEng(e.target.value)} data-testid="wl-engagement">
          <option value="">—</option>
          {(engs.data?.items ?? []).map((e) => (
            <option key={e.id} value={e.id}>
              {e.contractor.short_code}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField id="wl-reason" label={tf("reason")} required hint={tf("reasonMin", { min: 20, n })}>
        <Textarea id="wl-reason" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="wl-reason" />
      </FormField>
    </StepDialog>
  );
}

/* ═════════════ one entry: levels, PIP, decision, closure (WL-1…WL-6) ═════════════ */

const TRIGGERS = new Set(["WL-1a", "WL-1b", "WL-1c"]);

type Act = "confirm_escalation" | "submit_pip" | "accept_pip" | "decide" | "close";

export function WatchEntryPage({ id }: { id: string }) {
  const t = useTranslations("sc.watch");
  const tn = useTranslations("sc.nav");
  const te = useTranslations("enums");
  const q = useWatchEntry(id);
  const w = q.data;
  const caps = useScCaps(w?.project_id);
  const show = useDisplay(w?.project_id);
  const { dateTime } = useFormatters(w?.project_id);
  const [act, setAct] = useState<Act | null>(null);
  const [suspend, setSuspend] = useState(false);
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!w) return <LoadingState />;
  const open = w.status === "open";
  const pipStage = w.level === "improvement_plan" && !w.pip_accepted_at;
  return (
    <div className="flex flex-col gap-6">
      <Breadcrumbs items={[{ label: tn("watch"), href: "/watch-list" }, { label: w.entry_no }]} />
      <div className="flex flex-col gap-2">
        <p className="text-sm text-muted-foreground">
          <Code data-testid="wl-no">{w.entry_no}</Code>
        </p>
        <h1 className="flex flex-wrap items-center gap-2 text-xl font-semibold">
          <Code>{w.engagement_code}</Code>
          <WatchLevelBadge level={w.level} />
          <ScBadge group="scWatchStatus" status={w.status} testId="wl-status" />
        </h1>
      </div>
      {w.proposal && open ? (
        <Alert tone="warning" data-testid="wl-proposal">
          <span className="flex flex-col gap-2">
            <span className="font-medium">{t("proposalTitle", { p: te(`scWatchProposal.${w.proposal}`) })}</span>
            {w.proposal_reason ? <span>{w.proposal_reason}</span> : null}
            {caps.manage ? (
              <Button size="sm" className="w-fit" onClick={() => setAct(w.proposal === "close" ? "close" : "confirm_escalation")} data-testid="wl-confirm-proposal">
                {w.proposal === "close" ? t("closeEntry") : t("confirmEscalation")}
              </Button>
            ) : null}
          </span>
        </Alert>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("about")}</CardTitle>
        </CardHeader>
        <CardContent>
          <FieldList>
            <FieldItem label={t("baseline")}>{w.baseline_score ? show(Number(w.baseline_score).toFixed(1)) : "—"}</FieldItem>
            <FieldItem label={t("opened")}>{dateTime(w.opened_at)}</FieldItem>
            {w.opened_reason ? (
              <FieldItem label={t("openedReason")} wide>
                {w.opened_reason}
              </FieldItem>
            ) : null}
            <FieldItem label={t("triggers")} wide>
              <ul className="flex flex-col gap-1" data-testid="wl-triggers">
                {w.trigger_refs.map((r, i) => (
                  <li key={`${r.month}-${i}`} className="text-sm">
                    <span className="font-mono">{r.month}</span> · {TRIGGERS.has(r.trigger) ? te(`scWatchTrigger.${r.trigger.replace("-", "_")}` as "scWatchTrigger.WL_1a") : r.trigger}
                    {r.scorecard_no ? (
                      <>
                        {" "}
                        · <Code>{r.scorecard_no}</Code>
                      </>
                    ) : null}
                  </li>
                ))}
              </ul>
            </FieldItem>
            <FieldItem label={t("reviewCa")}>{w.review_ca_ref ? <Code>{w.review_ca_ref}</Code> : "—"}</FieldItem>
            {w.level !== "watch" ? (
              <>
                <FieldItem label={t("pipDue")}>
                  <DayDue date={w.pip_due_on} open={open && !w.pip_submitted_at} projectId={w.project_id} />
                </FieldItem>
                <FieldItem label={t("pipCas")}>
                  {w.pip_ca_refs.length ? (
                    <span className="flex flex-wrap gap-1">
                      {w.pip_ca_refs.map((r) => (
                        <Code key={r}>{r}</Code>
                      ))}
                    </span>
                  ) : (
                    "—"
                  )}
                </FieldItem>
                <FieldItem label={t("pipSubmitted")}>{w.pip_submitted_at ? dateTime(w.pip_submitted_at) : "—"}</FieldItem>
                <FieldItem label={t("pipAccepted")}>{w.pip_accepted_at ? dateTime(w.pip_accepted_at) : "—"}</FieldItem>
              </>
            ) : null}
            {w.decision ? (
              <FieldItem label={t("decision")} wide>
                <span className="font-medium" data-testid="wl-decision">
                  {te(`scWatchDecision.${w.decision}`)}
                </span>
                {w.decision_text ? <span className="block text-sm">{w.decision_text}</span> : null}
              </FieldItem>
            ) : null}
            {w.contractor_status_ref ? <FieldItem label={t("statusRef")}>{<Code>{w.contractor_status_ref}</Code>}</FieldItem> : null}
            {w.closed_reason ? (
              <FieldItem label={t("closedReason")} wide>
                {w.closed_reason}
              </FieldItem>
            ) : null}
          </FieldList>
        </CardContent>
      </Card>
      {open ? (
        <div className="flex flex-wrap gap-2 border-t pt-4" data-testid="wl-actions">
          {pipStage && caps.rep && caps.comment && !w.pip_submitted_at ? (
            <Button onClick={() => setAct("submit_pip")} data-testid="wl-submit-pip">
              {t("submitPip")}
            </Button>
          ) : null}
          {caps.manage && w.pip_submitted_at && !w.pip_accepted_at ? (
            <Button onClick={() => setAct("accept_pip")} data-testid="wl-accept-pip">
              {t("acceptPip")}
            </Button>
          ) : null}
          {caps.manage && w.level === "suspension_review" && !w.decision ? (
            <Button onClick={() => setAct("decide")} data-testid="wl-decide">
              {t("decide")}
            </Button>
          ) : null}
          {caps.manage && w.decision === "suspend" && !w.contractor_status_ref ? (
            <Button variant="destructive" onClick={() => setSuspend(true)} data-testid="wl-suspension-form">
              <ShieldAlert aria-hidden />
              {t("openSuspension")}
            </Button>
          ) : null}
          {caps.manage ? (
            <Button variant="outline" onClick={() => setAct("close")} data-testid="wl-close">
              {t("closeEntry")}
            </Button>
          ) : null}
        </div>
      ) : null}
      {act ? <TransitionDialog entry={w} action={act} onClose={() => setAct(null)} /> : null}
      {suspend ? <SuspensionDialog entry={w} onClose={() => setSuspend(false)} /> : null}
    </div>
  );
}

function TransitionDialog({ entry, action, onClose }: { entry: Entry; action: Act; onClose: () => void }) {
  const t = useTranslations("sc.watch");
  const tf = useTranslations("fu.common");
  const te = useTranslations("enums");
  const refresh = useScRefresh();
  const [reason, setReason] = useState("");
  const [decision, setDecision] = useState<S["ScWatchDecision"] | "">("");
  const [cas, setCas] = useState<string[]>([]);
  const needsText = action === "close" || action === "decide";
  const n = reason.trim().length;
  const ok = (!needsText || n >= 20) && (action !== "decide" || Boolean(decision)) && (action !== "submit_pip" || cas.length >= 3);
  return (
    <StepDialog
      title={t(`act.${action}`)}
      description={t(`actBody.${action}`)}
      confirmLabel={t(`act.${action}`)}
      testId="wl-transition-confirm"
      wide={action === "submit_pip"}
      disabled={!ok}
      onConfirm={async () => {
        await unwrap(
          api.POST("/api/v1/watch-list/{entry_id}/transitions", {
            params: { path: { entry_id: entry.id } },
            body: { action, reason: reason.trim() || null, decision: decision || null, pip_ca_ids: action === "submit_pip" ? cas : null },
          }),
        );
        await refresh();
        toast.success(t("saved"));
      }}
      onClose={onClose}
    >
      {action === "decide" ? (
        <fieldset className="flex flex-col gap-1">
          <legend className="mb-1 text-sm font-medium">{t("decision")}</legend>
          <Choices
            label={t("decision")}
            testId="wl-decision-choice"
            value={decision}
            options={(["suspend", "continue_with_conditions", "remove_from_project"] as const).map((d) => ({ value: d, label: te(`scWatchDecision.${d}`) }))}
            onChange={setDecision}
          />
          {decision === "suspend" ? <p className="text-xs text-muted-foreground">{t("suspendHint")}</p> : null}
        </fieldset>
      ) : null}
      {action === "submit_pip" ? <PipPicker projectId={entry.project_id} engagementId={entry.engagement_id} value={cas} onChange={setCas} /> : null}
      {needsText ? (
        <FormField id="wl-act-reason" label={tf("reason")} required hint={tf("reasonMin", { min: 20, n })}>
          <Textarea id="wl-act-reason" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="wl-act-reason" />
        </FormField>
      ) : null}
    </StepDialog>
  );
}

/** WL-3: at least 3 scorecard CAs due ≤ 30 days, one at engineering level or higher. The server checks; this lists the candidates. */
function PipPicker({ projectId, engagementId, value, onChange }: { projectId: string; engagementId: string; value: string[]; onChange: (v: string[]) => void }) {
  const t = useTranslations("sc.watch");
  const te = useTranslations("enums");
  const { date } = useFormatters(projectId);
  const q = useCorrectiveActions(projectId, { source_type: "scorecard", engagement_id: [engagementId], page_size: 100 });
  const items = q.data?.items ?? [];
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-muted-foreground">{t("pipRule")}</p>
      {q.isLoading ? (
        <LoadingState rows={2} />
      ) : items.length ? (
        <ul className="flex flex-col divide-y rounded-md border" data-testid="wl-pip-cas">
          {items.map((c) => (
            <li key={c.id}>
              <label className="flex min-h-touch items-center gap-3 px-3 py-2 text-sm">
                <input type="checkbox" className="size-5" checked={value.includes(c.id)} onChange={(e) => onChange(e.target.checked ? [...value, c.id] : value.filter((x) => x !== c.id))} />
                <Code>{c.ref}</Code>
                <span className="min-w-0 flex-1 truncate">{c.title}</span>
                <span className="text-xs text-muted-foreground">
                  {te(`controlLevel.${c.control_level}`)} · {date(c.due_date)}
                </span>
              </label>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState message={t("pipNoCas")} />
      )}
      <Link href="/actions/new" className="text-sm text-primary hover:underline">
        {t("pipNewCa")}
      </Link>
    </div>
  );
}

/** WL-5: the Phase 0 Approved → Suspended form, prefilled; nothing changes until the HSE Manager submits it. */
function SuspensionDialog({ entry, onClose }: { entry: Entry; onClose: () => void }) {
  const t = useTranslations("sc.watch");
  const q = useSuspensionForm(entry.id);
  const refresh = useScRefresh();
  const f = q.data;
  const [reason, setReason] = useState<string | null>(null);
  const text = reason ?? f?.status_reason ?? "";
  return (
    <StepDialog
      title={t("suspensionTitle", { code: f?.contractor_code ?? "" })}
      description={t("suspensionBody")}
      warning={f ? <SuspensionWarning form={f} /> : undefined}
      confirmLabel={t("suspensionSubmit")}
      destructive
      testId="wl-suspend-submit"
      wide
      disabled={!f || text.trim().length < 20}
      onConfirm={async () => {
        await unwrap(api.POST("/api/v1/contractors/{contractor_id}/transitions", { params: { path: { contractor_id: f!.contractor_id } }, body: { to_status: "suspended", reason: text.trim() } }));
        await refresh();
        toast.success(t("suspended", { code: f!.contractor_code }));
      }}
      onClose={onClose}
    >
      {q.isLoading ? <LoadingState rows={2} /> : q.isError ? <ErrorState error={q.error} /> : null}
      {f ? (
        <>
          <FormField id="wl-susp-reason" label={t("statusReason")} required>
            <Textarea id="wl-susp-reason" value={text} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="wl-suspend-reason" />
          </FormField>
          <div>
            <p className="mb-1 text-sm font-medium">{t("otherEngagements")}</p>
            <ul className="flex flex-col gap-1 text-sm" data-testid="wl-suspend-engagements">
              {f.engagements.map((e) => (
                <li key={`${e.project_code}-${e.engagement_code}`}>
                  <Code>{e.project_code}</Code> · <Code>{e.engagement_code}</Code> · {t("tier", { n: e.tier })}
                </li>
              ))}
            </ul>
          </div>
        </>
      ) : null}
    </StepDialog>
  );
}

function SuspensionWarning({ form }: { form: S["ScSuspensionForm"] }) {
  const ar = useLocale() === "ar";
  return <span data-testid="wl-suspend-warning">{ar ? form.warning_ar : form.warning_en}</span>;
}

/* ═════════════ contractor performance summary, 12 Final months (WL-8, CPS) ═════════════ */

export function PerformanceSummaryPage({ contractorId }: { contractorId: string }) {
  const t = useTranslations("sc.cps");
  const tc = useTranslations("common");
  const te = useTranslations("enums");
  const caps = useScCaps();
  const show = useDisplay();
  const q = usePerformanceSummary(contractorId, { enabled: caps.manage });
  if (!caps.manage) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data;
  if (!d) return <LoadingState />;
  return (
    <div className="flex flex-col gap-6">
      <Breadcrumbs items={[{ label: d.contractor_code, href: `/contractors/${contractorId}` }, { label: t("title") }]} />
      <PageHeader title={t("title")} description={t("subtitle")} />
      <div className="grid gap-3 sm:grid-cols-3">
        <Card>
          <CardContent className="flex flex-col gap-1 p-4">
            <span className="text-xs font-medium text-muted-foreground">{t("mean")}</span>
            <span className="text-3xl font-semibold tabular-nums" data-testid="cps-mean">
              {show(d.weighted_mean_display)}
            </span>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex flex-col gap-1 p-4">
            <span className="text-xs font-medium text-muted-foreground">{t("gradeMix")}</span>
            <span className="flex flex-wrap gap-2 text-sm">
              {Object.entries(d.grade_mix).map(([g, n]) => (
                <span key={g}>
                  <span className="font-mono font-bold">{g}</span> × {show(String(n))}
                </span>
              ))}
            </span>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex flex-col gap-1 p-4">
            <span className="text-xs font-medium text-muted-foreground">{t("caps")}</span>
            <span className="text-3xl font-semibold tabular-nums">{show(String(d.caps_applied))}</span>
          </CardContent>
        </Card>
      </div>
      {d.months.length ? (
        <Table data-testid="cps-months">
          <THead>
            <TR>
              <TH>{t("project")}</TH>
              <TH>{t("month")}</TH>
              <TH className="text-end">{t("score")}</TH>
              <TH>{t("grade")}</TH>
              <TH>{t("caps")}</TH>
              <TH>{t("profile")}</TH>
            </TR>
          </THead>
          <TBody>
            {d.months.map((m) => (
              <TR key={`${m.project_code}-${m.month}`}>
                <TD label={t("project")}>
                  <Code>{m.project_code}</Code>
                </TD>
                <TD label={t("month")}>
                  <span className="font-mono">{m.month}</span>
                </TD>
                <TD label={t("score")} className="text-end tabular-nums">
                  {show(m.score_display)}
                </TD>
                <TD label={t("grade")}>
                  <GradeBadge grade={m.grade} />
                </TD>
                <TD label={t("caps")}>{m.caps.length ? m.caps.join(" · ") : "—"}</TD>
                <TD label={t("profile")}>
                  <bdi className="ltr font-mono text-xs">{m.profile}</bdi>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : (
        <EmptyState message={t("empty")} />
      )}
      {d.watch_entries.length ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("watch")}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-2 text-sm">
              {d.watch_entries.map((w) => (
                <li key={w.id} className="flex flex-wrap items-center gap-2">
                  <Code>{w.entry_no}</Code>
                  <WatchLevelBadge level={w.level} />
                  <ScBadge group="scWatchStatus" status={w.status} />
                  {w.decision ? <span>{te(`scWatchDecision.${w.decision}`)}</span> : null}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
