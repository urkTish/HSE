"use client";
import { AlarmClock, ArrowRight, BookOpen, FileCheck2, FileWarning, TriangleAlert } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Fragment } from "react";
import { Alert } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Code } from "@/components/access/common";
import { ListToolbar, SelectFilter } from "@/components/common/list-toolbar";
import { PageHeader } from "@/components/common/page-header";
import { ProjectGate } from "@/components/common/project-gate";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { DateFilter } from "@/components/training/common";
import { Link } from "@/i18n/navigation";
import type { Schemas } from "@/lib/api/client";
import { useFuActionPanel, useFuBand, useFuKpis, useFuRequirements } from "@/lib/api/followup";
import { useDisplay } from "@/lib/digits";
import { useFormatters } from "@/lib/use-formatters";
import { useSearchState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { Countdown, FuSubNav, useFuCaps } from "./common";
import { RequirementList } from "./requirements";

type S = Schemas;
type Project = S["ProjectRead"];

const BODIES: S["ExternalBody"][] = ["gosi", "mhrsd", "civil_defense", "police", "gaca", "airport_operator", "client", "ncec"];
const STAGES: S["FuStage"][] = ["verbal", "written", "interim", "final"];
const STATUSES: S["FuRequirementStatus"][] = ["overdue", "due", "submitted", "acknowledged", "waived", "not_required"];

function actionHref(k: S["FuActionKind"]): string {
  switch (k) {
    case "requirements_overdue":
      return "/notification-register?status=overdue";
    case "packs_awaiting_approval":
      return "/notification-register?status=due";
    case "lessons_past_publish_due":
      return "/lessons?status=draft";
    case "acknowledgements_overdue":
      return "/lesson-acknowledgements";
    case "effectiveness_checks_overdue":
      return "/effectiveness-checks";
    case "template_changes_open":
      return "/lessons";
  }
}

/* ═════════════ overview: live follow-up band + action panel (§8.1 item 2, §8.2) ═════════════ */

export function FollowupOverviewPage() {
  return <ProjectGate>{(p) => <Overview project={p} />}</ProjectGate>;
}

function Overview({ project }: { project: Project }) {
  const t = useTranslations("fu.overview");
  const tc = useTranslations("common");
  const te = useTranslations("enums");
  const caps = useFuCaps(project.id);
  const show = useDisplay(project.id);
  const band = useFuBand(project.id, { enabled: caps.view });
  const panel = useFuActionPanel(project.id, { enabled: caps.view });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const b = band.data;
  const tiles = b
    ? ([
        { k: "verbal", n: b.verbal_due_next_hour.length, icon: AlarmClock, href: "/notification-register?stage=verbal", danger: true },
        { k: "overdue", n: b.overdue.length, icon: TriangleAlert, href: "/notification-register?status=overdue", danger: true },
        { k: "packs", n: b.packs_awaiting_approval, icon: FileCheck2, href: "/notification-register", danger: false },
        { k: "lessons", n: b.lessons_publish_due_soon.length, icon: BookOpen, href: "/lessons?status=in_review", danger: false },
      ] as const)
    : [];
  const items = panel.data?.items ?? [];
  const live = [...(b?.overdue ?? []), ...(b?.verbal_due_next_hour ?? [])];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <FuSubNav />
      <div className="flex flex-col gap-6">
        <section aria-labelledby="fu-band-h">
          <h2 id="fu-band-h" className="mb-2 text-sm font-semibold text-muted-foreground">
            {t("band")}
          </h2>
          {band.isLoading ? (
            <LoadingState />
          ) : band.isError ? (
            <ErrorState error={band.error} onRetry={() => band.refetch()} />
          ) : (
            <div className="grid grid-cols-2 gap-3 xl:grid-cols-4" data-testid="fu-band">
              {tiles.map((x) => {
                const Icon = x.icon;
                const hot = x.danger && x.n > 0;
                return (
                  <Link
                    key={x.k}
                    href={x.href}
                    className={cn("flex min-h-touch flex-col gap-1 rounded-md border p-3 hover:bg-muted/50", hot && "border-danger bg-danger-bg")}
                    data-testid="band-tile"
                    data-kind={x.k}
                  >
                    <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                      <Icon aria-hidden className={cn("size-4 shrink-0", hot && "text-danger")} />
                      {t(`b.${x.k}`)}
                    </span>
                    <span className={cn("text-3xl font-semibold tabular-nums", hot && "text-danger")} data-testid="band-value">
                      {show(String(x.n))}
                    </span>
                  </Link>
                );
              })}
            </div>
          )}
          {live.length ? (
            <ul className="mt-3 flex flex-col divide-y rounded-md border" data-testid="band-items">
              {live.slice(0, 8).map((r) => (
                <li key={r.id} className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm">
                  <Link href={`/incidents/${r.incident_id}`} className="font-medium text-primary hover:underline">
                    <Code>{r.incident_ref}</Code>
                  </Link>
                  <span>
                    {te(`externalBody.${r.body}`)} · {te(`fuStage.${r.stage}`)}
                  </span>
                  <Countdown due={r.due_at} projectId={project.id} />
                </li>
              ))}
            </ul>
          ) : null}
          {b?.lessons_publish_due_soon.length ? (
            <p className="mt-2 flex flex-wrap gap-2 text-sm text-muted-foreground">
              {t("lessonsDue")}
              {b.lessons_publish_due_soon.map((n) => (
                <Code key={n}>{n}</Code>
              ))}
            </p>
          ) : null}
        </section>
        <section aria-labelledby="fu-actions-h">
          <h2 id="fu-actions-h" className="mb-2 text-sm font-semibold text-muted-foreground">
            {t("actions")}
          </h2>
          {panel.isLoading ? (
            <LoadingState />
          ) : panel.isError ? (
            <ErrorState error={panel.error} onRetry={() => panel.refetch()} />
          ) : items.length ? (
            <ul className="flex flex-col divide-y rounded-md border" data-testid="fu-actions">
              {items.map((it) => (
                <li key={it.kind} className="flex flex-col gap-2 px-4 py-3" data-testid="fu-action" data-kind={it.kind}>
                  <span className="flex flex-wrap items-center gap-3">
                    <span className="min-w-10 rounded-md bg-warning-bg px-2 py-1 text-center text-lg font-bold text-warning tabular-nums">{show(String(it.count))}</span>
                    <span className="flex-1 font-medium">{te(`fuActionKind.${it.kind}`)}</span>
                    <Link href={actionHref(it.kind)} className="inline-flex min-h-touch items-center gap-1 text-primary hover:underline">
                      {t("open")}
                      <ArrowRight aria-hidden className="size-4 rtl:-scale-x-100" />
                    </Link>
                  </span>
                  {it.refs.length ? (
                    <ul className="flex flex-wrap gap-2 ps-1 text-sm">
                      {it.refs.slice(0, 8).map((r) => (
                        <li key={r} className="inline-flex items-center gap-1">
                          <FileWarning aria-hidden className="size-4 shrink-0 text-muted-foreground" />
                          <Code>{r}</Code>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState message={t("empty")} />
          )}
        </section>
      </div>
    </div>
  );
}

/* ═════════════ notification register across incidents (§8.3), overdue first ═════════════ */

export function NotificationRegisterPage() {
  return <ProjectGate>{(p) => <Register project={p} />}</ProjectGate>;
}

function Register({ project }: { project: Project }) {
  const t = useTranslations("fu.register");
  const tc = useTranslations("common");
  const te = useTranslations("enums");
  const caps = useFuCaps(project.id);
  const s = useSearchState();
  const body = (s.get("body") as S["ExternalBody"] | null) ?? "";
  const stage = (s.get("stage") as S["FuStage"] | null) ?? "";
  const status = (s.get("status") as S["FuRequirementStatus"] | null) ?? "";
  const q = useFuRequirements(project.id, { body: body ? [body] : null, stage: stage ? [stage] : null, status: status ? [status] : null, page_size: 200 }, { enabled: caps.view });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <FuSubNav />
      <ListToolbar>
        <SelectFilter id="fr-status" label={t("status")} value={status} onChange={(v) => s.set({ status: v || null })} options={STATUSES.map((x) => ({ value: x, label: te(`fuRequirementStatus.${x}`) }))} />
        <SelectFilter id="fr-body" label={t("body")} value={body} onChange={(v) => s.set({ body: v || null })} options={BODIES.map((x) => ({ value: x, label: te(`externalBody.${x}`) }))} />
        <SelectFilter id="fr-stage" label={t("stage")} value={stage} onChange={(v) => s.set({ stage: v || null })} options={STAGES.map((x) => ({ value: x, label: te(`fuStage.${x}`) }))} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length ? (
        <>
          <p className="mb-2 text-xs text-muted-foreground" data-testid="fr-total">
            {t("total", { n: q.data?.total ?? items.length })}
          </p>
          <RequirementList items={items} projectId={project.id} showIncident />
        </>
      ) : (
        <EmptyState message={t("empty")} />
      )}
    </div>
  );
}

/* ═════════════ KPI page (K-127…K-131; aggregates only, FK-1) ═════════════ */

export function FollowupKpiPage() {
  return <ProjectGate>{(p) => <Kpis project={p} />}</ProjectGate>;
}

const PERIODS = ["month", "quarter", "year", "ytd"] as const satisfies readonly S["PeriodPreset"][];
const GROUP_BY: S["FuKpiGroupBy"][] = ["body", "stage", "month", "contractor"];

/** Every number is the server's `display`; nothing is computed here. */
function Kpis({ project }: { project: Project }) {
  const t = useTranslations("fu.kpi");
  const te = useTranslations("enums");
  const tc = useTranslations("common");
  const ar = useLocale() === "ar";
  const caps = useFuCaps(project.id);
  const show = useDisplay(project.id);
  const { dateTime } = useFormatters(project.id);
  const s = useSearchState();
  const groupBy = (s.get("group_by") as S["FuKpiGroupBy"]) || "body";
  const period = (s.get("period") as (typeof PERIODS)[number]) || "month";
  const anchor = s.get("anchor") ?? "";
  const q = useFuKpis({ project_id: [project.id], group_by: [groupBy], period, anchor: anchor || null }, { enabled: caps.view });
  if (!caps.view) return <Alert tone="info">{tc("notAllowed")}</Alert>;
  const d = q.data;
  return (
    <div>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <FuSubNav />
      <ListToolbar>
        <SelectFilter id="fk-period" label={t("period")} value={period} onChange={(v) => s.set({ period: v })} options={PERIODS.map((p) => ({ value: p, label: te(`period.${p}`) }))} allLabel={te("period.month")} />
        <DateFilter id="fk-anchor" label={t("anchor")} value={anchor} onChange={(v) => s.set({ anchor: v })} />
        <SelectFilter id="fk-group" label={t("groupBy")} value={groupBy} onChange={(v) => s.set({ group_by: v })} options={GROUP_BY.map((g) => ({ value: g, label: te(`fuKpiGroupBy.${g}`) }))} allLabel={te("fuKpiGroupBy.body")} />
      </ListToolbar>
      {q.isLoading ? (
        <LoadingState />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : d ? (
        <div className="flex flex-col gap-6">
          <p className="text-xs text-muted-foreground">
            {ar ? d.context.period.label_ar : d.context.period.label_en} · {t("computedAt", { at: dateTime(d.context.computed_at) })}
          </p>
          {d.notes.length ? (
            <ul className="flex flex-col gap-1 rounded-md border bg-muted/30 px-4 py-2 text-sm" data-testid="fk-notes">
              {d.notes.map((n) => (
                <li key={n} data-testid="fk-note">
                  {n.startsWith("K-127 excludes waived") ? t("noteK127") : <bdi>{n}</bdi>}
                </li>
              ))}
            </ul>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid="fk-tiles">
            {d.metrics.map((m) => (
              <Card key={m.metric} data-testid="fk-tile" data-metric={m.metric}>
                <CardContent className="flex flex-col gap-1 p-4">
                  <span className="flex items-center justify-between gap-2 text-xs font-medium text-muted-foreground">
                    <span>{ar ? m.short_label_ar : m.short_label_en}</span>
                    <span className="font-mono ltr">{m.metric}</span>
                  </span>
                  <span className={cn("text-3xl font-semibold tabular-nums", m.rag === "red" && "text-danger", m.rag === "amber" && "text-warning")} data-testid="fk-value">
                    {show(m.display)}
                  </span>
                  {m.rag && m.rag !== "green" ? (
                    <span className={cn("inline-flex items-center gap-1 text-xs font-medium", m.rag === "red" ? "text-danger" : "text-warning")} data-testid="fk-rag">
                      <TriangleAlert aria-hidden className="size-3.5" />
                      {te(`rag.${m.rag}`)}
                    </span>
                  ) : null}
                  {m.null_reason ? <span className="text-xs text-muted-foreground">{te(`nullReason.${m.null_reason}`)}</span> : null}
                  {m.components.length ? (
                    <span className="flex flex-wrap gap-x-3 text-xs text-muted-foreground" data-testid="fk-chips">
                      {m.components.map((c) => (
                        <span key={c.key}>
                          {ar ? c.label_ar : c.label_en}: <span className="font-medium tabular-nums text-foreground">{show(c.display)}</span>
                        </span>
                      ))}
                    </span>
                  ) : null}
                  {m.numerator && m.denominator ? (
                    <span className="text-xs text-muted-foreground">
                      <bdi className="ltr tabular-nums">
                        {show(m.numerator)} / {show(m.denominator)}
                      </bdi>
                    </span>
                  ) : null}
                  <span className="text-xs text-muted-foreground">{ar ? m.label_ar : m.label_en}</span>
                </CardContent>
              </Card>
            ))}
          </div>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("breakdown", { by: te(`fuKpiGroupBy.${groupBy}`) })}</CardTitle>
              <p className="text-xs text-muted-foreground">{t("aggregatesHint")}</p>
            </CardHeader>
            <CardContent>
              <Breakdown breakdowns={d.breakdowns} metrics={d.metrics} show={show} />
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
}

function Breakdown({ breakdowns, metrics, show }: { breakdowns: S["FuBreakdown"][]; metrics: S["KpiValue"][]; show: (v: string) => string }) {
  const t = useTranslations("fu.kpi");
  const ar = useLocale() === "ar";
  if (!breakdowns.length || breakdowns.every((b) => !b.rows.length)) return <EmptyState message={t("noBreakdown")} />;
  const keys: { key: string; label: string }[] = [];
  for (const b of breakdowns) for (const r of b.rows) if (!keys.some((k) => k.key === r.key)) keys.push({ key: r.key, label: ar ? r.label_ar : r.label_en });
  const metricLabel = (id: string) => {
    const m = metrics.find((x) => x.metric === id);
    return m ? (ar ? m.short_label_ar : m.short_label_en) : id;
  };
  return (
    <Table data-testid="fk-breakdown">
      <THead>
        <TR>
          <TH>{t("key")}</TH>
          {breakdowns.map((b) => (
            <TH key={b.metric} className="text-end">
              {metricLabel(b.metric)}
            </TH>
          ))}
        </TR>
      </THead>
      <TBody>
        {keys.map((k) => (
          <TR key={k.key} data-testid="fk-row" data-key={k.key}>
            <TD label={t("key")}>
              <bdi>{k.label}</bdi>
            </TD>
            {breakdowns.map((b) => {
              const r = b.rows.find((x) => x.key === k.key);
              return (
                <Fragment key={b.metric}>
                  <TD label={metricLabel(b.metric)} className="text-end tabular-nums">
                    {r ? show(r.display) : "—"}
                  </TD>
                </Fragment>
              );
            })}
          </TR>
        ))}
      </TBody>
    </Table>
  );
}
