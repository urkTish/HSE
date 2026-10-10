"use client";
import { Award, Eye, TrendingDown, TrendingUp, MoveRight } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { SubNav } from "@/components/access/common";
import { StatusBadge } from "@/components/common/status-badge";
import { useMeData } from "@/components/shell/me-context";
import type { Schemas } from "@/lib/api/client";
import { useScReference } from "@/lib/api/scorecard";
import { can, canWrite } from "@/lib/permissions";
import { cn } from "@/lib/utils";

type S = Schemas;

/* ───────────── capabilities (6g §5.15, 224–232) ───────────── */

export function useScCaps(projectId?: string | null) {
  const me = useMeData();
  const pid = projectId ?? null;
  const roles = me?.projects.find((p) => p.project_id === pid)?.roles ?? [];
  return {
    me,
    view: can(me, "scorecard.view", pid),
    settings: canWrite(me, "scorecard.settings", pid),
    manage: canWrite(me, "scorecard.manage", pid),
    comment: canWrite(me, "scorecard.comment", pid),
    resolve: canWrite(me, "scorecard.resolve", pid),
    prepare: canWrite(me, "report_pack.prepare", pid),
    issue: canWrite(me, "report_pack.issue", pid),
    packs: can(me, "report_pack.view", pid) || can(me, "report_pack.prepare", pid),
    exportLog: can(me, "export_log.view", pid),
    /** A Contractor HSE Rep: disputes, never internal notes; sees only their own scope (RK-2). */
    rep: !me?.is_hse_manager && roles.includes("contractor_hse_rep"),
  };
}

/* ───────────── sub navigation ───────────── */

export function ScSubNav() {
  const t = useTranslations("sc.nav");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/scorecards", label: t("cards"), testId: "sub-sc-cards" },
        { href: "/scorecard-remarks", label: t("remarks"), show: can(me, "scorecard.comment") || can(me, "scorecard.resolve"), testId: "sub-sc-remarks" },
        { href: "/watch-list", label: t("watch"), testId: "sub-sc-watch" },
        { href: "/scorecard-kpis", label: t("kpis"), testId: "sub-sc-kpis" },
        { href: "/scorecard-settings", label: t("settings"), show: can(me, "scorecard.settings"), testId: "sub-sc-settings" },
      ]}
    />
  );
}

export function ReportsSubNav() {
  const t = useTranslations("sc.nav");
  const me = useMeData();
  return (
    <SubNav
      items={[
        { href: "/report-packs", label: t("packs"), show: can(me, "report_pack.view") || can(me, "report_pack.prepare"), testId: "sub-rp-packs" },
        { href: "/distribution-lists", label: t("distribution"), show: can(me, "report_pack.issue"), testId: "sub-rp-distribution" },
        { href: "/exports", label: t("exports"), testId: "sub-xp-exports" },
      ]}
    />
  );
}

/* ───────────── reference lists (server EN/AR labels, §3.10) ───────────── */

export function useScRef() {
  const q = useScReference();
  const ar = useLocale() === "ar";
  const lists = q.data?.lists as Record<string, S["ScRefItem"][]> | undefined;
  const items = useCallback((l: string): S["ScRefItem"][] => lists?.[l] ?? [], [lists]);
  const label = useCallback(
    (l: string, code: string | null | undefined): string => {
      if (!code) return "—";
      const it = lists?.[l]?.find((x) => x.code === code);
      return it ? (ar ? it.label_ar : it.label_en) : code;
    },
    [lists, ar],
  );
  return { items, label };
}

/* ───────────── badges (colour + icon + words) ───────────── */

const GRADE_TONE: Record<S["ScGrade"], "success" | "warning" | "danger"> = { A: "success", B: "success", C: "warning", D: "danger" };

/** Grade A–D with its band label; "—" (insufficient data) in grey. Caps show "B → C". */
export function GradeBadge({ grade, band, testId = "sc-grade" }: { grade: S["ScGrade"] | null | undefined; band?: S["ScGrade"] | null; testId?: string }) {
  const te = useTranslations("enums");
  const capped = Boolean(band && grade && band !== grade);
  return (
    <span data-testid={testId} data-grade={grade ?? "none"} className="inline-flex items-center gap-1">
      {capped ? (
        <>
          <span className="font-mono text-xs text-muted-foreground line-through">{band}</span>
          <MoveRight aria-hidden className="size-3.5 text-muted-foreground rtl:-scale-x-100" />
        </>
      ) : null}
      <Badge tone={grade ? GRADE_TONE[grade] : "neutral"}>
        <span className="font-mono font-bold">{grade ?? "—"}</span>
        <span>{te(`scGrade.${grade ?? "none"}`)}</span>
      </Badge>
    </span>
  );
}

const STATUS_TONE: Record<string, string> = {
  provisional: "provisional",
  issued: "issued",
  final: "completed",
  superseded: "superseded",
  draft: "draft",
  in_review: "pending_review",
  active: "active",
  retired: "retired",
  open: "open",
  resolved: "completed",
  withdrawn: "withdrawn",
  closed: "closed",
  queued: "pending",
  ready: "ok",
  expired: "expired",
  failed: "failed",
  sent: "delivered",
  bounced: "error",
};

type Group = "scCardStatus" | "rpStatus" | "scProfileStatus" | "scRemarkStatus" | "scWatchStatus" | "xpJobStatus" | "rpDeliveryStatus";

export function ScBadge({ group, status, testId = "sc-status" }: { group: Group; status: string; testId?: string }) {
  const te = useTranslations("enums");
  return (
    <span data-testid={testId} data-status={status}>
      <StatusBadge status={STATUS_TONE[status] ?? status} label={te(`${group}.${status}` as "scCardStatus.final")} />
    </span>
  );
}

export function LineStatusBadge({ status }: { status: S["ScLineStatus"] }) {
  const te = useTranslations("enums");
  const tone = status === "scored" ? "ok" : status === "excluded_by_manager" ? "excluded" : "not_required";
  return (
    <span data-testid="sc-line-status" data-status={status}>
      <StatusBadge status={tone} label={te(`scLineStatus.${status}`)} />
    </span>
  );
}

export function WatchLevelBadge({ level }: { level: S["ScWatchLevel"] | null | undefined }) {
  const te = useTranslations("enums");
  if (!level) return null;
  return (
    <Badge tone={level === "watch" ? "warning" : "danger"} data-testid="sc-watch-level" data-level={level}>
      <Eye aria-hidden />
      {te(`scWatchLevel.${level}`)}
    </Badge>
  );
}

export function TrendMark({ label, delta, show }: { label: S["ScTrend"] | null | undefined; delta?: string | null; show: (v: string) => string }) {
  const te = useTranslations("enums");
  const Icon = label === "improving" ? TrendingUp : label === "declining" ? TrendingDown : MoveRight;
  return (
    <span className={cn("inline-flex items-center gap-1 text-sm", label === "declining" && "text-danger", label === "improving" && "text-success")} data-testid="sc-trend" data-trend={label ?? "none"}>
      {label ? <Icon aria-hidden className={cn("size-4", label === "stable" && "rtl:-scale-x-100")} /> : null}
      {label ? te(`scTrend.${label}`) : "—"}
      {delta ? <bdi className="ltr text-xs text-muted-foreground tabular-nums">({show(Number(delta) > 0 ? `+${Number(delta).toFixed(1)}` : Number(delta).toFixed(1))})</bdi> : null}
    </span>
  );
}

export function Commended({ on }: { on: boolean }) {
  const t = useTranslations("sc.card");
  if (!on) return null;
  return (
    <Badge tone="success" data-testid="sc-commended">
      <Award aria-hidden />
      {t("commended")}
    </Badge>
  );
}

/** "3 of 4" with the project median (RK-2); unranked cards say why. */
export function RankText({ r, show }: { r: S["ScRankInfo"]; show: (v: string) => string }) {
  const t = useTranslations("sc.card");
  const te = useTranslations("enums");
  if (r.rank && r.rank_of) return <span data-testid="sc-rank">{t("rankOf", { n: show(String(r.rank)), of: show(String(r.rank_of)) })}</span>;
  return <span data-testid="sc-rank">{r.rank_status ? te(`scRankStatus.${r.rank_status}`) : "—"}</span>;
}

export function Num({ children }: { children: ReactNode }) {
  return <bdi className="ltr tabular-nums">{children}</bdi>;
}

/** yyyy-mm of the month before the current one (Riyadh), the month most screens open on. */
export function previousMonth(now = new Date()): string {
  const d = new Date(now.getTime() + 3 * 3_600_000);
  const y = d.getUTCFullYear();
  const m = d.getUTCMonth(); // 0-based → previous month number
  return m === 0 ? `${y - 1}-12` : `${y}-${String(m).padStart(2, "0")}`;
}

/** The last 12 months (yyyy-mm), newest first, for month pickers. */
export function recentMonths(n = 12, now = new Date()): string[] {
  const d = new Date(now.getTime() + 3 * 3_600_000);
  const out: string[] = [];
  let y = d.getUTCFullYear();
  let m = d.getUTCMonth() + 1;
  for (let i = 0; i < n; i++) {
    out.push(`${y}-${String(m).padStart(2, "0")}`);
    m -= 1;
    if (m === 0) {
      m = 12;
      y -= 1;
    }
  }
  return out;
}
