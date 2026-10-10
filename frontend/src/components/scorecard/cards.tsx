"use client";
import { AlertTriangle, Lock } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Countdown } from "@/components/followup/common";
import { Link } from "@/i18n/navigation";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useScCard, useScCards, useScRanking, useScRefresh } from "@/lib/api/scorecard";
import { useDisplay } from "@/lib/digits";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { Commended, GradeBadge, LineStatusBadge, Num, RankText, ScBadge, ScSubNav, TrendMark, WatchLevelBadge, previousMonth, recentMonths, useScCaps, useScRef } from "./common";
import { RemarkList, NewRemarkButton } from "./remarks";

type S = Schemas;
type Project = S["ProjectRead"];

const GRADES: S["ScGrade"][] = ["A", "B", "C", "D"];
const STATUSES: S["ScCardStatus"][] = ["provisional", "issued", "final", "superseded"];

/* ═════════════ register: ranking of the month + every card (§8.3) ═════════════ */

export function ScorecardsPage() {
  return <ProjectGate>{(p) => <Register project={p} />}</ProjectGate>;
}

function Register({ project }: { project: Project }) {
  const t = useTranslations("sc.register");
  const tc = useTranslations("common");
  const te = useTranslations("enums");
  const caps = useScCaps(project.id);
  const show = useDisplay(project.id);
  const s = useSearchState();
  const month = s.get("month") || previousMonth();
  const grade = (s.get("grade") as S["ScGrade"] | null) ?? "";
  const status = (s.get("status") as S["ScCardStatus"] | null) ?? "";
  const scope = (s.get("scope") as S["ScScope"] | null) ?? "";
  const ranking = useScRanking(project.id, month, { enabled: caps.view });
  const cards = useScCards(project.id, { month, grade: grade || null, status: status || null, scope: scope || null, page_size: 200 }, { enabled: caps.view });
  const [finalise, setFinalise] = useState(false);
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const r = ranking.data;
  const items = cards.data?.items ?? [];
  return (
    <div>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          caps.manage && r?.status === "issued" ? (
            <Button onClick={() => setFinalise(true)} data-testid="sc-finalise">
              <Lock aria-hidden />
              {t("finalise")}
            </Button>
          ) : null
        }
      />
      <ScSubNav />
      <ListToolbar>
        <SelectFilter id="sc-month" label={t("month")} value={month} onChange={(v) => s.set({ month: v || null })} options={recentMonths(15).map((m) => ({ value: m, label: m }))} allLabel={previousMonth()} />
        <SelectFilter id="sc-status" label={t("status")} value={status} onChange={(v) => s.set({ status: v || null })} options={STATUSES.map((x) => ({ value: x, label: te(`scCardStatus.${x}`) }))} />
        <SelectFilter id="sc-grade" label={t("grade")} value={grade} onChange={(v) => s.set({ grade: v || null })} options={GRADES.map((g) => ({ value: g, label: `${g} · ${te(`scGrade.${g}`)}` }))} />
        <SelectFilter id="sc-scope" label={t("scope")} value={scope} onChange={(v) => s.set({ scope: v || null })} options={(["own", "tree"] as const).map((x) => ({ value: x, label: te(`scScope.${x}`) }))} />
      </ListToolbar>

      <section aria-labelledby="sc-rank-h" className="mb-6">
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="sc-rank-h" className="text-base font-semibold">
            {t("ranking", { month })}
          </h2>
          {r ? (
            <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              {r.status ? <ScBadge group="scCardStatus" status={r.status} testId="sc-month-status" /> : null}
              <span data-testid="sc-median">{t("median", { v: show(r.median_display) })}</span>
              <span>·</span>
              <span>{t("rankedOf", { n: show(String(r.ranked_count)) })}</span>
              <span>·</span>
              <bdi className="ltr font-mono text-xs">{r.profile}</bdi>
            </p>
          ) : null}
        </div>
        {ranking.isLoading ? (
          <LoadingState />
        ) : ranking.isError ? (
          <ErrorState error={ranking.error} onRetry={() => ranking.refetch()} />
        ) : r && r.rows.length ? (
          <RankingTable rows={r.rows} show={show} />
        ) : (
          <EmptyState message={t("noCards")} />
        )}
        {r?.status === "provisional" || r?.status === "issued" ? <p className="mt-2 text-xs text-muted-foreground">{t(r.status === "issued" ? "issuedHint" : "provisionalHint")}</p> : null}
      </section>

      <section aria-labelledby="sc-cards-h">
        <h2 id="sc-cards-h" className="mb-2 text-base font-semibold">
          {t("cards")}
        </h2>
        {cards.isLoading ? (
          <LoadingState />
        ) : cards.isError ? (
          <ErrorState error={cards.error} onRetry={() => cards.refetch()} />
        ) : items.length ? (
          <Table data-testid="sc-card-list">
            <THead>
              <TR>
                <TH>{t("no")}</TH>
                <TH>{t("engagement")}</TH>
                <TH>{t("scope")}</TH>
                <TH>{t("status")}</TH>
                <TH className="text-end">{t("score")}</TH>
                <TH>{t("grade")}</TH>
                <TH>{t("disputes")}</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((c) => (
                <TR key={`${c.scorecard_no}-${c.revision}-${c.scope}`} data-testid="sc-card-row" data-engagement={c.engagement_code} data-scope={c.scope}>
                  <TD label={t("no")}>
                    {c.id ? (
                      <Link href={`/scorecards/${c.id}`} className="text-primary hover:underline">
                        <Code>{c.scorecard_no}</Code>
                      </Link>
                    ) : (
                      <Code>{c.scorecard_no}</Code>
                    )}{" "}
                    <span className="text-xs text-muted-foreground">{t("rev", { n: show(String(c.revision)) })}</span>
                  </TD>
                  <TD label={t("engagement")}>
                    <Code>{c.engagement_code}</Code>
                  </TD>
                  <TD label={t("scope")}>{te(`scScope.${c.scope}`)}</TD>
                  <TD label={t("status")}>
                    <span className="flex flex-wrap items-center gap-1">
                      <ScBadge group="scCardStatus" status={c.status} />
                      {c.revised_since_final ? (
                        <span className="inline-flex items-center gap-1 text-xs text-warning" data-testid="sc-revised">
                          <AlertTriangle aria-hidden className="size-3.5" />
                          {t("revised")}
                        </span>
                      ) : null}
                    </span>
                  </TD>
                  <TD label={t("score")} className="text-end font-semibold tabular-nums">
                    {show(c.score_display)}
                    {c.indicative ? <span className="block text-xs font-normal text-muted-foreground">{t("indicative")}</span> : null}
                  </TD>
                  <TD label={t("grade")}>
                    <GradeBadge grade={c.grade} band={c.band_grade} />
                  </TD>
                  <TD label={t("disputes")}>{c.open_disputes ? <span className="font-medium text-warning">{show(String(c.open_disputes))}</span> : "—"}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        ) : (
          <EmptyState message={t("noCards")} />
        )}
      </section>
      {finalise ? <FinaliseDialog projectId={project.id} month={month} onClose={() => setFinalise(false)} /> : null}
    </div>
  );
}

function RankingTable({ rows, show }: { rows: S["ScRankingRow"][]; show: (v: string) => string }) {
  const t = useTranslations("sc.register");
  const te = useTranslations("enums");
  return (
    <Table data-testid="sc-ranking">
      <THead>
        <TR>
          <TH>{t("rank")}</TH>
          <TH>{t("engagement")}</TH>
          <TH className="text-end">{t("score")}</TH>
          <TH>{t("grade")}</TH>
          <TH>{t("caps")}</TH>
          <TH>{t("trend")}</TH>
          <TH className="text-end">{t("coverage")}</TH>
          <TH>{t("watch")}</TH>
        </TR>
      </THead>
      <TBody>
        {rows.map((r) => (
          <TR key={r.engagement_id} data-testid="sc-rank-row" data-engagement={r.engagement_code} data-rank={r.rank ?? ""}>
            <TD label={t("rank")} className="font-semibold tabular-nums">
              {r.rank ? show(String(r.rank)) : <span className="text-xs font-normal text-muted-foreground">{r.rank_status ? te(`scRankStatus.${r.rank_status}`) : "—"}</span>}
            </TD>
            <TD label={t("engagement")}>
              <span className="flex flex-wrap items-center gap-1">
                {r.card_id ? (
                  <Link href={`/scorecards/${r.card_id}`} className="text-primary hover:underline">
                    <Code>{r.engagement_code}</Code>
                  </Link>
                ) : (
                  <Code>{r.engagement_code}</Code>
                )}
                <Commended on={r.commended} />
              </span>
              {r.tree_score_display ? <span className="block text-xs text-muted-foreground">{t("tree", { v: show(r.tree_score_display) })}</span> : null}
            </TD>
            <TD label={t("score")} className="text-end text-base font-semibold tabular-nums" data-testid="sc-rank-score">
              {show(r.score_display)}
            </TD>
            <TD label={t("grade")}>
              <GradeBadge grade={r.grade} band={r.band_grade} />
            </TD>
            <TD label={t("caps")}>{r.caps.length ? <span className="font-mono text-xs">{r.caps.join(" · ")}</span> : "—"}</TD>
            <TD label={t("trend")}>
              <TrendMark label={r.trend_label} show={show} />
            </TD>
            <TD label={t("coverage")} className="text-end tabular-nums">
              {show(r.coverage_display)}
            </TD>
            <TD label={t("watch")}>{r.watch_level ? <WatchLevelBadge level={r.watch_level} /> : "—"}</TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}

function FinaliseDialog({ projectId, month, onClose }: { projectId: string; month: string; onClose: () => void }) {
  const t = useTranslations("sc.finalise");
  const refresh = useScRefresh();
  return (
    <StepDialog
      title={t("title", { month })}
      description={t("body")}
      confirmLabel={t("confirm")}
      testId="sc-finalise-confirm"
      onConfirm={async () => {
        const r = await unwrap(api.POST("/api/v1/projects/{project_id}/scorecards/finalise", { params: { path: { project_id: projectId } }, body: { month } }));
        await refresh();
        toast.success(t("done", { n: r.finalised, scp: r.scp_issued }));
      }}
      onClose={onClose}
    />
  );
}

/* ═════════════ one card: pillars, lines, caps, grade, rank (§3.2–§3.3) ═════════════ */

export function ScorecardPage({ id }: { id: string }) {
  const t = useTranslations("sc.card");
  const tn = useTranslations("sc.nav");
  const te = useTranslations("enums");
  const q = useScCard(id);
  const c = q.data;
  const caps = useScCaps(c?.project_id);
  const show = useDisplay(c?.project_id);
  const { dateTime } = useFormatters(c?.project_id);
  const ref = useScRef();
  const [reissue, setReissue] = useState(false);
  const [now] = useState(() => Date.now());
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!c) return <LoadingState />;
  const windowOpen = c.status === "issued" && Boolean(c.comment_until) && Date.parse(c.comment_until as string) >= now;
  return (
    <div className="flex flex-col gap-6">
      <Breadcrumbs items={[{ label: tn("cards"), href: `/scorecards?month=${c.month}` }, { label: c.scorecard_no }]} />
      <div className="flex flex-col gap-2">
        <p className="text-sm text-muted-foreground">
          <Code data-testid="sc-no">{c.scorecard_no}</Code> · {t("rev", { n: show(String(c.revision)) })} · {te(`scScope.${c.scope}`)}
        </p>
        <h1 className="flex flex-wrap items-center gap-2 text-xl font-semibold">
          <Code>{c.engagement_code}</Code>
          <span>· {c.month}</span>
          <ScBadge group="scCardStatus" status={c.status} testId="sc-card-status" />
          <Commended on={c.commended} />
          <WatchLevelBadge level={c.watch_level} />
        </h1>
      </div>
      {c.status === "provisional" ? (
        <Alert tone="warning" data-testid="sc-banner">
          {t("provisionalBanner")}
        </Alert>
      ) : null}
      {c.revised_since_final ? (
        <Alert tone="warning" data-testid="sc-revised-alert">
          <span className="flex flex-col gap-2">
            {t("revisedBody", { final: show(c.score_display), now: show(c.recomputed_score ? Number(c.recomputed_score).toFixed(1) : "—") })}
            {caps.manage && c.status === "final" ? (
              <Button size="sm" variant="outline" className="w-fit" onClick={() => setReissue(true)} data-testid="sc-reissue">
                {t("reissue")}
              </Button>
            ) : null}
          </span>
        </Alert>
      ) : null}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label={t("summary")}>
        <Card>
          <CardContent className="flex flex-col gap-1 p-4">
            <span className="text-xs font-medium text-muted-foreground">{t("score")}</span>
            <span className="text-4xl font-semibold tabular-nums" data-testid="sc-score">
              {show(c.score_display)}
            </span>
            {c.indicative ? <span className="text-xs text-warning">{t("indicative")}</span> : null}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex flex-col gap-2 p-4">
            <span className="text-xs font-medium text-muted-foreground">{t("grade")}</span>
            <GradeBadge grade={c.grade} band={c.band_grade} testId="sc-card-grade" />
            {c.caps_applied.map((cp) => (
              <span key={cp.cap_code} className="text-xs" data-testid="sc-cap" data-cap={cp.cap_code}>
                <span className="font-mono font-semibold">{cp.cap_code}</span> {ref.label("caps", cp.cap_code)}
                {cp.refs.length ? (
                  <span className="mt-0.5 flex flex-wrap gap-1">
                    {cp.refs.map((r) => (
                      <Code key={r}>{r}</Code>
                    ))}
                  </span>
                ) : null}
              </span>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex flex-col gap-1 p-4">
            <span className="text-xs font-medium text-muted-foreground">{t("rank")}</span>
            <span className="text-2xl font-semibold">
              <RankText r={c.ranking} show={show} />
            </span>
            <span className="text-xs text-muted-foreground" data-testid="sc-card-median">
              {t("median", { v: show(c.ranking.median_display) })}
            </span>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex flex-col gap-1 p-4">
            <span className="text-xs font-medium text-muted-foreground">{t("trend")}</span>
            <TrendMark label={c.trend_label} delta={c.trend_delta} show={show} />
            <span className="text-xs text-muted-foreground">{t("coverage", { v: show(c.coverage_display) })}</span>
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("about")}</CardTitle>
        </CardHeader>
        <CardContent>
          <FieldList>
            <FieldItem label={t("profile")} ltr>
              {c.profile_code} v{c.profile_version}
            </FieldItem>
            <FieldItem label={t("monthHours")}>
              <Num>{show(Number(c.month_man_hours).toLocaleString("en-US"))}</Num>
            </FieldItem>
            <FieldItem label={t("r12Hours")}>
              <Num>{show(Number(c.r12_man_hours).toLocaleString("en-US"))}</Num>
            </FieldItem>
            <FieldItem label={t("z")}>
              <Num>{show(c.credibility_z_display)}</Num>
            </FieldItem>
            <FieldItem label={t("commentUntil")}>
              {c.comment_until ? (
                <span className="flex flex-col gap-1">
                  {dateTime(c.comment_until)}
                  <Countdown due={c.comment_until} open={c.status === "issued"} projectId={c.project_id} />
                </span>
              ) : (
                "—"
              )}
            </FieldItem>
            <FieldItem label={t("issuedAt")}>{c.issued_at ? dateTime(c.issued_at) : "—"}</FieldItem>
            <FieldItem label={t("finalisedAt")}>{c.finalised_at ? dateTime(c.finalised_at) : "—"}</FieldItem>
            {c.reissue_reason ? (
              <FieldItem label={t("reissueReason")} wide>
                {c.reissue_reason}
              </FieldItem>
            ) : null}
          </FieldList>
          <p className="mt-3 text-xs text-muted-foreground">{t("noTyping")}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("pillars")}</CardTitle>
        </CardHeader>
        <CardContent>
          <Table data-testid="sc-pillars">
            <THead>
              <TR>
                <TH>{t("pillar")}</TH>
                <TH className="text-end">{t("weight")}</TH>
                <TH className="text-end">{t("effWeight")}</TH>
                <TH className="text-end">{t("pillarScore")}</TH>
              </TR>
            </THead>
            <TBody>
              {(c.pillars ?? []).map((p) => (
                <TR key={p.pillar_code} data-testid="sc-pillar" data-pillar={p.pillar_code}>
                  <TD label={t("pillar")}>
                    <span className="font-mono text-xs">{p.pillar_code}</span> {ref.label("pillars", p.pillar_code)}
                    {p.redistributed ? <span className="block text-xs text-muted-foreground">{t("redistributed")}</span> : null}
                  </TD>
                  <TD label={t("weight")} className="text-end tabular-nums">
                    {show(Number(p.weight).toFixed(1))}
                  </TD>
                  <TD label={t("effWeight")} className="text-end tabular-nums" data-testid="sc-pillar-eff">
                    {show(p.effective_weight_display)}
                  </TD>
                  <TD label={t("pillarScore")} className="text-end font-semibold tabular-nums">
                    {show(p.score_display)}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("lines")}</CardTitle>
          <p className="text-xs text-muted-foreground">{t("linesHint")}</p>
        </CardHeader>
        <CardContent>
          <Table data-testid="sc-lines">
            <THead>
              <TR>
                <TH>{t("metric")}</TH>
                <TH>{t("window")}</TH>
                <TH className="text-end">{t("value")}</TH>
                <TH className="text-end">{t("points")}</TH>
                <TH>{t("lineStatus")}</TH>
                <TH className="text-end">{t("effWeight")}</TH>
              </TR>
            </THead>
            <TBody>
              {(c.lines ?? []).map((l) => (
                <TR key={l.metric_code} data-testid="sc-line" data-metric={l.metric_code} className={cn(l.line_status !== "scored" && "text-muted-foreground")}>
                  <TD label={t("metric")}>
                    <span className="font-mono text-xs">{l.metric_code}</span> · <span className="font-mono text-xs">{l.kpi_ref}</span>
                    <span className="block">{ref.label("metrics", l.metric_code)}</span>
                    {l.note ? <span className="block text-xs">{l.note}</span> : null}
                  </TD>
                  <TD label={t("window")}>{te(`scWindow.${l.window}`)}</TD>
                  <TD label={t("value")} className="text-end tabular-nums">
                    {show(l.value_display)}
                    {l.window === "r12_rate" && l.own_value !== null && l.project_value !== null ? (
                      <span className="block text-xs text-muted-foreground">{t("blend", { own: show(Number(l.own_value).toFixed(2)), project: show(Number(l.project_value).toFixed(2)) })}</span>
                    ) : null}
                  </TD>
                  <TD label={t("points")} className="text-end font-medium tabular-nums">
                    {show(l.points_display)}
                  </TD>
                  <TD label={t("lineStatus")}>
                    <LineStatusBadge status={l.line_status} />
                  </TD>
                  <TD label={t("effWeight")} className="text-end tabular-nums">
                    {show(l.effective_weight_display)}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>

      {c.id && c.status !== "provisional" ? (
        <Card>
          <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
            <CardTitle className="text-base">{t("remarks")}</CardTitle>
            {caps.comment && c.status === "issued" && (windowOpen || !caps.rep) ? <NewRemarkButton card={c} /> : null}
          </CardHeader>
          <CardContent>
            {c.status === "issued" && !windowOpen && caps.rep ? <p className="mb-2 text-sm text-muted-foreground">{t("windowClosed")}</p> : null}
            <RemarkList projectId={c.project_id} cardId={c.id} />
          </CardContent>
        </Card>
      ) : null}
      {reissue ? <ReissueCardDialog card={c} onClose={() => setReissue(false)} /> : null}
    </div>
  );
}

function ReissueCardDialog({ card, onClose }: { card: S["ScCardRead"]; onClose: () => void }) {
  const t = useTranslations("sc.reissue");
  const tf = useTranslations("fu.common");
  const refresh = useScRefresh();
  const [reason, setReason] = useState("");
  return (
    <StepDialog
      title={t("title", { no: card.scorecard_no })}
      description={t("body")}
      confirmLabel={t("confirm")}
      testId="sc-reissue-confirm"
      disabled={reason.trim().length < 20}
      onConfirm={async () => {
        await unwrap(api.POST("/api/v1/scorecards/{card_id}/reissue", { params: { path: { card_id: card.id as string } }, body: { reason: reason.trim() } }));
        await refresh();
        toast.success(t("done"));
      }}
      onClose={onClose}
    >
      <FormField id="sc-reissue-reason" label={tf("reason")} required hint={tf("reasonMin", { min: 20, n: reason.trim().length })}>
        <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} data-testid="sc-reissue-reason" />
      </FormField>
    </StepDialog>
  );
}
