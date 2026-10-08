"use client";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import type { Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { DrillNumber } from "./drill";

type Tile = Schemas["KpiTile"];
type Value = Schemas["KpiValue"];

const RAG_CLASS: Record<Schemas["Rag"], string> = {
  green: "bg-safety-ok",
  amber: "bg-safety-caution",
  red: "bg-safety-critical",
};

export function Comparison({ c, show }: { c: Schemas["KpiComparison"]; show: (v: string) => string }) {
  const t = useTranslations("dashboard");
  const te = useTranslations("enums");
  const ar = useLocale() === "ar";
  const Icon = c.abs_delta === null || c.direction === "n/a" ? Minus : Number(c.abs_delta) > 0 ? ArrowUpRight : Number(c.abs_delta) < 0 ? ArrowDownRight : Minus;
  // A worse delta is "at risk" (amber), not critical: red is kept for genuinely critical states (alarm fatigue).
  const tone = c.direction === "better" ? "text-success" : c.direction === "worse" ? "text-warning" : "text-muted-foreground";
  return (
    <p className="flex flex-wrap items-center gap-1 text-xs" data-testid="tile-comparison" data-direction={c.direction}>
      <span className={cn("inline-flex items-center gap-0.5 font-medium", tone)}>
        <Icon aria-hidden className="size-3.5 rtl:-scale-x-100" />
        {show(c.pct_delta_display !== "n/a" ? c.pct_delta_display : c.abs_delta_display)}
        <span className="sr-only">{te(`direction.${c.direction}`)}</span>
      </span>
      <span className="text-muted-foreground">
        {t("vs", { label: ar ? c.label_ar : c.label_en })} ({show(c.display)})
      </span>
    </p>
  );
}

/** 12-month sparkline: one hue, 2px line, last point marked; each point has a hover title. */
export function Sparkline({ points, show, label }: { points: Schemas["SparkPoint"][]; show: (v: string) => string; label: string }) {
  const ar = useLocale() === "ar";
  const [hover, setHover] = useState<number | null>(null);
  const vals = points.map((p) => (p.value === null ? null : Number(p.value)));
  const nums = vals.filter((v): v is number => v !== null && Number.isFinite(v));
  if (nums.length < 2) return null;
  const w = 120;
  const h = 32;
  const min = Math.min(...nums, 0);
  const max = Math.max(...nums);
  const span = max - min || 1;
  const xs = (i: number) => {
    const x = (i / Math.max(1, points.length - 1)) * (w - 8) + 4;
    return ar ? w - x : x;
  };
  const ys = (v: number) => h - 4 - ((v - min) / span) * (h - 8);
  const segs: string[] = [];
  let cur = "";
  vals.forEach((v, i) => {
    if (v === null) {
      if (cur) segs.push(cur);
      cur = "";
      return;
    }
    cur += `${cur ? "L" : "M"}${xs(i).toFixed(1)},${ys(v).toFixed(1)}`;
  });
  if (cur) segs.push(cur);
  const lastIdx =
    vals
      .map((v, i) => (v === null ? -1 : i))
      .filter((i) => i >= 0)
      .at(-1) ?? 0;
  const lastV = vals[lastIdx] ?? 0;
  const hp = hover !== null ? points[hover] : null;
  return (
    <div className="relative" data-testid="sparkline">
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} role="img" aria-label={label} className="overflow-visible" onMouseLeave={() => setHover(null)}>
        {segs.map((d, i) => (
          <path key={i} d={d} fill="none" stroke="var(--series-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        ))}
        <circle cx={xs(lastIdx)} cy={ys(lastV)} r={3.5} fill="var(--series-1)" stroke="var(--surface)" strokeWidth={2} />
        {points.map((p, i) => (
          <rect key={p.period_start} x={xs(i) - w / points.length / 2} y={0} width={w / points.length} height={h} fill="transparent" onMouseEnter={() => setHover(i)}>
            <title>{`${ar ? p.label_ar : p.label_en}: ${show(p.display)}`}</title>
          </rect>
        ))}
        {hover !== null && vals[hover] !== null ? (
          <circle cx={xs(hover)} cy={ys(vals[hover] as number)} r={4} fill="var(--series-1)" stroke="var(--surface)" strokeWidth={2} />
        ) : null}
      </svg>
      {hp ? (
        <span className="pointer-events-none absolute -top-6 start-0 rounded bg-foreground px-1.5 py-0.5 text-[10px] whitespace-nowrap text-background">
          {ar ? hp.label_ar : hp.label_en}: {show(hp.display)}
        </span>
      ) : null}
    </div>
  );
}

/** The unit is shown after the value unless the backend `display` already carries it (e.g. "70.0 %"). */
function showUnit(tile: Tile): boolean {
  const u = tile.unit_en?.trim();
  if (!u || tile.kind === "count") return false;
  return !tile.display.trim().endsWith(u);
}

export function KpiTile({ tile, show }: { tile: Tile; show: (v: string) => string }) {
  const t = useTranslations("dashboard");
  const te = useTranslations("enums");
  const ar = useLocale() === "ar";
  const label = ar ? tile.short_label_ar || tile.label_ar : tile.short_label_en || tile.label_en;
  const full = ar ? tile.label_ar : tile.label_en;
  const cmp = tile.comparisons[0];
  return (
    <div className="flex min-w-0 flex-col gap-1.5 rounded-xl border bg-surface p-3 shadow-xs" data-testid="kpi-tile" data-metric={tile.metric}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium text-muted-foreground" title={full}>
          {label}
        </p>
        {tile.rag ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground" data-testid="tile-rag" data-rag={tile.rag}>
            <span aria-hidden className={cn("inline-block size-2.5 rounded-full", RAG_CLASS[tile.rag])} />
            {te(`rag.${tile.rag}`)}
          </span>
        ) : null}
      </div>
      <DrillNumber metric={tile.metric} label={full} className="text-2xl leading-tight font-semibold">
        <span data-testid="tile-value">{show(tile.display)}</span>
        {showUnit(tile) ? <span className="ms-1 text-xs font-normal text-muted-foreground">{ar ? tile.unit_ar : tile.unit_en}</span> : null}
      </DrillNumber>
      {cmp ? <Comparison c={cmp} show={show} /> : null}
      {tile.components.length > 0 ? (
        <p className="text-xs text-muted-foreground">{tile.components.map((c) => `${ar ? c.label_ar : c.label_en} ${show(c.display)}`).join(" · ")}</p>
      ) : null}
      {tile.target_display ? <p className="text-[11px] text-muted-foreground">{t("target", { value: show(tile.target_display) })}</p> : null}
      <TileSourceNotes v={tile} />
      {tile.warnings.length > 0 ? (
        <ul className="flex flex-wrap gap-1">
          {tile.warnings.map((w) => (
            <li key={w} className="rounded bg-warning-bg px-1.5 py-0.5 text-[10px] text-warning" data-testid="tile-warning">
              {te(`kpiWarning.${w}`)}
            </li>
          ))}
        </ul>
      ) : null}
      <div className="mt-auto pt-1">
        <Sparkline points={tile.sparkline} show={show} label={`${full} — ${t("sparkline")}`} />
      </div>
    </div>
  );
}

/** Headline figure (K-01..K-04, K-28/29): no sparkline, comparison when present. `inline` lays it out as one row. */
export function HeadlineValue({ v, show, big, caption, inline }: { v: Value; show: (v: string) => string; big?: boolean; caption?: string; inline?: boolean }) {
  const ar = useLocale() === "ar";
  const label = ar ? v.label_ar : v.label_en;
  return (
    <div className={cn("flex min-w-0", inline ? "flex-row flex-wrap items-baseline gap-x-4 gap-y-1" : "flex-col gap-1")} data-testid="headline-value" data-metric={v.metric}>
      <p className="text-xs font-medium text-muted-foreground">
        {ar ? v.short_label_ar || label : v.short_label_en || label}
        {caption ? <span className="font-normal"> · {caption}</span> : null}
      </p>
      <DrillNumber metric={v.metric} label={label} className={cn("leading-tight font-semibold", big ? "text-3xl" : "text-xl")}>
        {show(v.display)}
      </DrillNumber>
      {v.components.length > 0 ? (
        <p className="text-xs text-muted-foreground">{v.components.map((c) => `${ar ? c.label_ar : c.label_en} ${show(c.display)}`).join(" · ")}</p>
      ) : null}
      {v.comparisons[0] ? <Comparison c={v.comparisons[0]} show={show} /> : null}
      <TileSourceNotes v={v} />
    </div>
  );
}

/** K-37 (5-training TH-6/TH-7): the hours source label and per-tile notes (register vs daily returns, sessions not closed). */
export function TileSourceNotes({ v }: { v: Pick<Tile, "data_source" | "notes"> }) {
  const t = useTranslations("dashboard");
  const te = useTranslations("enums");
  const ar = useLocale() === "ar";
  const notes = v.notes ?? [];
  if (!v.data_source && !notes.length) return null;
  return (
    <div className="flex flex-col gap-1">
      {v.data_source ? (
        <p className="text-[11px] text-muted-foreground" data-testid="tile-source" data-source={v.data_source}>
          {t("dataSource", { source: te(`trainingHoursSource.${v.data_source}`) })}
        </p>
      ) : null}
      {notes.length ? (
        <ul className="flex flex-wrap gap-1">
          {notes.map((n) => (
            <li key={n.code} className={cn("rounded px-1.5 py-0.5 text-[10px]", n.severity === "info" ? "bg-muted text-muted-foreground" : "bg-warning-bg text-warning")} data-testid="tile-note" data-code={n.code}>
              {ar ? n.message_ar : n.message_en}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
