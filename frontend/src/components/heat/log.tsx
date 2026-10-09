"use client";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { PossibleIdHint } from "@/components/common/api-warnings";
import { FieldItem, FieldList } from "@/components/common/field-list";
import { FormField } from "@/components/common/form-field";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { ProjectById, ProjectGate } from "@/components/common/project-gate";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, LoadingState, MutationError } from "@/components/common/states";
import { Code, WorkerLabel } from "@/components/access/common";
import { UserName } from "@/components/cert/common";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useHeatLog, useHeatLogEntry, useHeatRefresh, useHeatReference } from "@/lib/api/heat";
import { HEAT_LOG_STATUSES, REVIEW_ANSWERS, REVIEW_QUESTIONS } from "@/lib/heat-enums";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { FreeText, HeatReasonDialog, RegimeBadge, SensitiveNote, Wbgt, useHeatCaps } from "./common";

type S = Schemas;
type Project = S["ProjectRead"];
type Entry = S["HeatLogRead"];
const PAGE_SIZE = 50;
const LOG_TONE: Record<S["HeatLogStatus"], string> = { open: "open", reviewed: "reviewed", voided: "voided" };

export function HeatLogStatusBadge({ status }: { status: S["HeatLogStatus"] }) {
  const te = useTranslations("enums");
  return (
    <span data-testid="log-status" data-status={status}>
      <StatusBadge status={LOG_TONE[status]} label={te(`heatLogStatus.${status}`)} />
    </span>
  );
}

function ControlGap({ gap }: { gap: boolean }) {
  const t = useTranslations("heat.log");
  return gap ? (
    <Badge tone="danger" data-testid="control-gap" data-gap="yes">
      <AlertTriangle aria-hidden />
      {t("gap")}
    </Badge>
  ) : (
    <Badge tone="success" data-testid="control-gap" data-gap="no">
      <CheckCircle2 aria-hidden />
      {t("noGap")}
    </Badge>
  );
}

/* ═════════════ heat-illness log (§3.11, HI-1…HI-6, P6b-2) ═════════════ */

export function HeatLogPage() {
  return <ProjectGate>{(p) => <Log project={p} />}</ProjectGate>;
}

function Log({ project }: { project: Project }) {
  const t = useTranslations("heat.log");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const caps = useHeatCaps(project.id);
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const page = s.getInt("page", 1) ?? 1;
  const status = (s.get("status") ?? "") as S["HeatLogStatus"] | "";
  const q = useHeatLog(project.id, { status: status || null, page, page_size: PAGE_SIZE }, { enabled: caps.log });
  if (!caps.log) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <SensitiveNote>{t("noClinical")}</SensitiveNote>
      <ListToolbar>
        <SelectFilter id="hl-status" label={tc("status")} value={status} onChange={(v) => s.set({ status: v })} options={HEAT_LOG_STATUSES.map((x) => ({ value: x, label: te(`heatLogStatus.${x}`) }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <Table data-testid="log-table">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("worker")}</TH>
                <TH>{t("event")}</TH>
                <TH>{t("source")}</TH>
                <TH>{t("controlGap")}</TH>
                <TH>{t("reviewDue")}</TH>
                <TH>{tc("status")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((e) => (
                <TR key={e.id} data-testid="log-row" data-no={e.entry_no} data-status={e.status}>
                  <TD label={t("no")}>
                    <Link href={`/heat-illness-log/${e.id}`} className="font-medium text-primary hover:underline" data-testid="log-link">
                      <Code>{e.entry_no}</Code>
                    </Link>
                  </TD>
                  <TD label={t("worker")}>{e.worker ? <WorkerLabel w={e.worker} /> : "—"}</TD>
                  <TD label={t("event")}>
                    <span className="whitespace-nowrap">{dateTime(e.event_at)}</span>
                    {e.zone_code ? <Code className="block text-xs text-muted-foreground">{e.zone_code}</Code> : null}
                  </TD>
                  <TD label={t("source")}>
                    {te(`heatLogSource.${e.source_type}`)}
                    {e.source_ref ? <Code className="block text-xs text-muted-foreground">{e.source_ref}</Code> : null}
                  </TD>
                  <TD label={t("controlGap")}>{e.status === "reviewed" ? <ControlGap gap={e.control_gap} /> : e.control_gap ? <ControlGap gap /> : "—"}</TD>
                  <TD label={t("reviewDue")}>{e.status === "open" ? <span className="whitespace-nowrap">{dateTime(e.review_due_at)}</span> : "—"}</TD>
                  <TD label={tc("status")}>
                    <HeatLogStatusBadge status={e.status} />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pagination page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPage={(p) => s.set({ page: p })} />
        </>
      ) : (
        <EmptyState message={status ? undefined : t("empty")} />
      )}
    </div>
  );
}

/* ═════════════ entry: context snapshot (§6.7), review (HI-4, HI-5), re-open ═════════════ */

export function HeatLogEntryPage({ id }: { id: string }) {
  const q = useHeatLogEntry(id);
  if (q.isLoading) return <LoadingState />;
  if (q.isError || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const e = q.data;
  return <ProjectById id={e.project_id}>{(p) => <EntryView project={p} e={e} />}</ProjectById>;
}

type Ctx = {
  state?: S["HeatStateKind"];
  reading_no?: string | null;
  wbgt_c?: string | null;
  reading_voided?: boolean;
  workload?: S["Workload"];
  basis?: S["AcclimatisationBasis"];
  acclimatisation?: S["AcclimatisationStatus"];
  plan_no?: string | null;
  plan_day?: number | null;
  plan_day_confirmed?: boolean;
  plan_day_followed?: boolean | null;
  regime?: S["Regime"];
  ban_in_force?: boolean;
  possible_ban_breach?: boolean;
  permit_nos?: string[];
  days_on_site_band?: string | null;
  heat_awr_in_force?: boolean | null;
  welfare?: { result?: string; check_no?: string | null; station_code?: string | null };
  hold_no?: string | null;
  hold_status?: S["HoldStatus"];
};

function EntryView({ project, e }: { project: Project; e: Entry }) {
  const t = useTranslations("heat.log");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const locale = useLocale();
  const caps = useHeatCaps(project.id);
  const ref = useHeatReference();
  const { dateTime } = useFormatters(project.id);
  const [reopen, setReopen] = useState(false);
  const c = e.context as Ctx;
  const yn = (v: boolean | null | undefined) => (v === null || v === undefined ? "—" : v ? tc("yes") : tc("no"));
  const qLabel = (code: string) => {
    const m = ref.data?.review_questions.find((x) => x.code === code);
    return m ? (locale === "ar" ? m.label_ar : m.label_en) : te(`reviewQuestion.${code}` as never);
  };
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={
          <>
            {t("entryTitle")} <Code>{e.entry_no}</Code>
          </>
        }
        badge={<HeatLogStatusBadge status={e.status} />}
        actions={
          caps.reviewer && e.status === "reviewed" ? (
            <Button variant="outline" onClick={() => setReopen(true)} data-testid="log-reopen">
              {t("reopen")}
            </Button>
          ) : null
        }
      />
      <SensitiveNote>{t("noClinical")}</SensitiveNote>
      <Card>
        <CardContent className="p-4">
          <FieldList>
            <FieldItem label={t("worker")}>{e.worker ? <WorkerLabel w={e.worker} /> : "—"}</FieldItem>
            <FieldItem label={t("event")}>
              {dateTime(e.event_at)} {e.zone_code ? <Code>{e.zone_code}</Code> : null}
            </FieldItem>
            <FieldItem label={t("source")}>
              {te(`heatLogSource.${e.source_type}`)} {e.source_ref ? <Code>{e.source_ref}</Code> : null}
              {e.related_referral_no ? (
                <span className="block text-xs text-muted-foreground">
                  {t("relatedReferral")} <Code>{e.related_referral_no}</Code>
                </span>
              ) : null}
            </FieldItem>
            <FieldItem label={t("hold")}>{e.hold_no ? <Code>{e.hold_no}</Code> : "—"}</FieldItem>
            <FieldItem label={t("controlGap")}>
              <ControlGap gap={e.control_gap} />
            </FieldItem>
            {e.status === "open" ? <FieldItem label={t("reviewDue")}>{dateTime(e.review_due_at)}</FieldItem> : null}
          </FieldList>
        </CardContent>
      </Card>
      <Card data-testid="log-context">
        <CardHeader>
          <CardTitle className="text-base">{t("context")}</CardTitle>
          <p className="text-xs text-muted-foreground">{t("contextHint")}</p>
        </CardHeader>
        <CardContent>
          {c.reading_voided ? (
            <Alert tone="warning" className="mb-3">
              {t("readingVoided")}
            </Alert>
          ) : null}
          <FieldList>
            <FieldItem label={t("ctx.reading")}>
              <span data-testid="ctx-wbgt">
                <Wbgt v={c.wbgt_c} />
              </span>{" "}
              {c.reading_no ? <Code className="text-xs text-muted-foreground">{c.reading_no}</Code> : null} {c.state ? <span className="text-xs">({te(`heatState.${c.state}`)})</span> : null}
            </FieldItem>
            <FieldItem label={t("ctx.regime")}>
              <RegimeBadge regime={c.regime ?? null} />
            </FieldItem>
            <FieldItem label={t("ctx.workload")}>{c.workload ? te(`workload.${c.workload}`) : "—"}</FieldItem>
            <FieldItem label={t("ctx.acclimatisation")}>
              {c.acclimatisation ? te(`acclStatus.${c.acclimatisation === "n.a." ? "na" : c.acclimatisation}`) : "—"}
              {c.plan_no ? (
                <span className="block text-xs text-muted-foreground">
                  <Code>{c.plan_no}</Code> {c.plan_day ? t("ctx.planDay", { n: c.plan_day }) : null}
                </span>
              ) : null}
            </FieldItem>
            <FieldItem label={t("ctx.ban")}>
              {yn(c.ban_in_force)}
              {c.possible_ban_breach ? (
                <Badge tone="danger" className="ms-1">
                  {t("ctx.possibleBreach")}
                </Badge>
              ) : null}
            </FieldItem>
            <FieldItem label={t("ctx.heatAwr")}>{yn(c.heat_awr_in_force)}</FieldItem>
            <FieldItem label={t("ctx.welfare")}>
              {c.welfare?.result ? te(`welfareResult.${c.welfare.result}` as never) : "—"}
              {c.welfare?.check_no ? <Code className="ms-1 text-xs">{c.welfare.check_no}</Code> : null}
            </FieldItem>
            <FieldItem label={t("ctx.permits")}>{c.permit_nos?.length ? c.permit_nos.map((p) => <Code key={p} className="me-1">{p}</Code>) : "—"}</FieldItem>
            <FieldItem label={t("ctx.daysOnSite")}>
              <bdi className="ltr">{c.days_on_site_band ?? "—"}</bdi>
            </FieldItem>
          </FieldList>
        </CardContent>
      </Card>
      <Card data-testid="log-review">
        <CardHeader>
          <CardTitle className="text-base">{t("review")}</CardTitle>
        </CardHeader>
        <CardContent>
          {e.review ? (
            <div className="flex flex-col gap-3">
              <Table>
                <TBody>
                  {REVIEW_QUESTIONS.map((qc) => (
                    <TR key={qc} data-testid="review-answer" data-q={qc} data-answer={e.review?.answers[qc] ?? ""}>
                      <TD label={qc}>
                        <Code className="me-2 font-semibold">{qc}</Code>
                        {qLabel(qc)}
                      </TD>
                      <TD className="text-end">{e.review?.answers[qc] ? <AnswerBadge a={e.review.answers[qc]!} /> : "—"}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
              {e.review.factors_text ? (
                <p className="text-sm">
                  <span className="font-medium">{t("factors")}: </span>
                  <FreeText testId="review-factors">{e.review.factors_text}</FreeText>
                </p>
              ) : null}
              {e.review.reviewed_at ? (
                <p className="text-xs text-muted-foreground">
                  {t("reviewedBy")} <UserName u={e.review.reviewed_by} /> · {dateTime(e.review.reviewed_at)}
                </p>
              ) : null}
            </div>
          ) : caps.reviewer && e.status === "open" ? (
            <ReviewForm e={e} qLabel={qLabel} />
          ) : (
            <p className="text-sm text-muted-foreground">{t("notReviewed")}</p>
          )}
        </CardContent>
      </Card>
      {reopen ? (
        <HeatReasonDialog
          title={t("reopenTitle", { no: e.entry_no })}
          confirmLabel={t("reopen")}
          destructive={false}
          onConfirm={async (reason) => {
            await unwrap(api.POST("/api/v1/heat-illness-log/{entry_id}/reopen", { params: { path: { entry_id: e.id } }, body: { reason } }));
          }}
          onClose={() => setReopen(false)}
        />
      ) : null}
    </div>
  );
}

function AnswerBadge({ a }: { a: S["ReviewAnswer"] }) {
  const te = useTranslations("enums");
  return <Badge tone={a === "no" ? "danger" : a === "yes" ? "success" : "neutral"}>{te(`reviewAnswer.${a}`)}</Badge>;
}

function ReviewForm({ e, qLabel }: { e: Entry; qLabel: (q: string) => string }) {
  const t = useTranslations("heat.log");
  const te = useTranslations("enums");
  const refresh = useHeatRefresh();
  const [answers, setAnswers] = useState<Record<string, S["ReviewAnswer"]>>({});
  const [factors, setFactors] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const all = REVIEW_QUESTIONS.every((q) => answers[q]);
  async function save() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(api.POST("/api/v1/heat-illness-log/{entry_id}/review", { params: { path: { entry_id: e.id } }, body: { answers, factors_text: factors.trim() || null } }));
      await refresh();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-3" data-testid="review-form">
      <p className="text-sm text-muted-foreground">{t("reviewHint")}</p>
      <ol className="flex flex-col divide-y rounded-md border">
        {REVIEW_QUESTIONS.map((q) => (
          <li key={q} className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:justify-between">
            <span className="text-sm">
              <Code className="me-2 font-semibold">{q}</Code>
              {qLabel(q)}
            </span>
            <span className="grid grid-cols-4 gap-1" role="radiogroup" aria-label={q}>
              {REVIEW_ANSWERS.filter((a) => a !== "na" || q === "HC4").map((a) => (
                <Button key={a} type="button" size="sm" role="radio" aria-checked={answers[q] === a} variant={answers[q] === a ? (a === "no" ? "destructive" : "default") : "outline"} onClick={() => setAnswers({ ...answers, [q]: a })} data-testid={`rv-${q}-${a}`}>
                  {te(`reviewAnswer.${a}`)}
                </Button>
              ))}
            </span>
          </li>
        ))}
      </ol>
      <FormField id="rv-factors" label={t("factors")} hint={t("factorsHint")}>
        <Textarea value={factors} onChange={(ev) => setFactors(ev.target.value)} maxLength={500} data-testid="rv-factors" />
      </FormField>
      <PossibleIdHint text={factors} />
      <MutationError error={error} />
      <Button className="self-start" disabled={!all || busy} onClick={() => void save()} data-testid="rv-save">
        {t("saveReview")}
      </Button>
    </div>
  );
}
