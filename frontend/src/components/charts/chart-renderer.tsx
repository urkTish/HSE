"use client";
import { BarChart3, Table2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState, type ReactNode } from "react";
import { Area, Bar, CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipContentProps } from "recharts";
import type { NameType, ValueType } from "recharts/types/component/DefaultTooltipContent";
import { Button } from "@/components/ui/button";
import type { Schemas } from "@/lib/api/client";
import { toArabicIndic } from "@/lib/digits";
import { cn } from "@/lib/utils";

type Spec = Schemas["ChartSpec"];
type Series = Schemas["ChartSeries"];

/**
 * Semantic roles map onto fixed series slots so a colour always means the same thing
 * (never cycled). Status colours are not used for series identity.
 *
 * Dashboard colour map (same entity → same colour on every chart):
 *   series-1 blue    injury cases / TRIR / LTI (lagging)
 *   series-2 orange  unsafe observations, rolling R12 TRIR
 *   series-3 aqua    overdue corrective actions (C5, C9)
 *   series-5 magenta heat-related cases
 *   series-6 green   safe observations
 *   series-7 violet  rate lines in a lower panel (inspection compliance, R12 LTIFR)
 *   C13 (permits by type, 9 types): the 8 slots in order plus a neutral grey for "General / cold work" (the
 *   catch-all type), so no hue repeats (the API cycles the 9th type back to series-1); the high-risk share
 *   line is ink, not violet, because violet already means "Lifting" in the same chart.
 */
const ROLE_SLOT: Record<string, string> = {
  target: "var(--muted-foreground)",
  lagging: "var(--series-1)",
  leading: "var(--series-7)",
  safe: "var(--series-6)",
  unsafe: "var(--series-2)",
};

/** Series keys whose backend slot would clash with the colour map above (e.g. aqua = overdue CAs). */
const KEY_SLOT: Record<string, string> = {
  r12_ltifr: "var(--series-7)",
  inspection_compliance: "var(--series-7)",
  general: "var(--series-neutral)",
  airside_works: "var(--series-1)",
  high_risk_share: "var(--foreground)",
};

export function seriesColor(role: string, key?: string): string {
  if (key && KEY_SLOT[key]) return KEY_SLOT[key];
  if (/^series-[1-8]$/.test(role)) return `var(--${role})`;
  return ROLE_SLOT[role] ?? "var(--series-1)";
}

/** Axis caption: the unit is appended only when the label does not already contain it. */
function axisCaption(label: string, unit: string): string {
  if (!unit || label.includes(unit)) return label;
  return `${label} (${unit})`;
}

function num(v: string | null | undefined): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

interface Row {
  x: string;
  label: string;
  [k: string]: string | number | null;
}

export interface ChartRendererProps {
  spec: Spec;
  height?: number;
  /** Map ASCII digits in tick labels to Arabic-Indic (project setting). */
  arabicDigits?: boolean;
  /** Clicking a mark: drill-down. */
  onPointClick?: (seriesKey: string, x: string) => void;
  /** Hide the title (when the surrounding card shows it). */
  hideTitle?: boolean;
  actions?: ReactNode;
  testId?: string;
}

/**
 * The one chart wrapper: draws a backend ChartSpec exactly as given (no aggregation),
 * with the token series palette, a legend for ≥ 2 series, a table view, RTL mirroring,
 * and small multiples instead of a second y-axis.
 */
export function ChartRenderer({ spec, height = 260, arabicDigits = false, onPointClick, hideTitle, actions, testId }: ChartRendererProps) {
  const t = useTranslations("dashboard");
  const locale = useLocale();
  const ar = locale === "ar";
  const [asTable, setAsTable] = useState(spec.kind === "table" || spec.kind === "pyramid");
  const L = (en: string, arabic: string) => (ar ? arabic || en : en);
  const digits = (s: string) => (arabicDigits ? toArabicIndic(s) : s);

  const rows = useMemo<Row[]>(() => {
    const cats = spec.x_axis?.categories ?? [];
    const out = cats.map<Row>((c) => ({
      x: c.key,
      label: ar ? c.label_ar || c.label_en : c.label_en,
    }));
    const byKey = new Map(out.map((r) => [r.x, r]));
    for (const s of spec.series) {
      for (const p of s.points) {
        const r = byKey.get(p.x);
        if (!r) continue;
        r[s.key] = num(p.value);
        r[`${s.key}__d`] = p.display;
      }
    }
    return out;
  }, [spec, ar]);

  const panels = useMemo(() => {
    const axes = spec.y_axes.length ? spec.y_axes : [{ id: "y", label_en: "", label_ar: "", unit_en: null, unit_ar: null }];
    return axes
      .map((axis) => ({
        axis,
        series: spec.series.filter((s) => s.y_axis === axis.id || (axes.length === 1 && !axes.some((a) => a.id === s.y_axis))),
      }))
      .filter((p) => p.series.length > 0);
  }, [spec]);

  const empty = spec.series.every((s) => s.points.every((p) => num(p.value) === null)) && !(spec.table && spec.table.rows.length);
  const title = L(spec.title_en, spec.title_ar);
  const showLegend = spec.series.length >= 2 || spec.bands.length > 0 || spec.reference_lines.length > 0;
  const canChart = spec.kind !== "table" && spec.kind !== "pyramid" && spec.x_axis !== null;
  const horizontal = spec.kind === "horizontal_bar";
  // RTL: a time/category x-axis runs right-to-left, so the plot gets the rows reversed. A horizontal bar
  // chart keeps its order (largest first, top to bottom) in both languages; only its value axis mirrors.
  const plotRows = ar && !horizontal ? [...rows].reverse() : rows;

  return (
    <figure className="flex min-w-0 flex-col gap-2" data-testid={testId ?? `chart-${spec.chart_id}`} data-chart-kind={spec.kind}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        {!hideTitle ? <figcaption className="text-sm font-semibold">{title}</figcaption> : <span />}
        <div className="flex items-center gap-1 print:hidden">
          {actions}
          {canChart ? (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => setAsTable(!asTable)}
              aria-pressed={asTable}
              aria-label={asTable ? t("chart") : t("table")}
              data-testid="chart-toggle-table"
            >
              {asTable ? <BarChart3 aria-hidden /> : <Table2 aria-hidden />}
              <span className="sr-only sm:not-sr-only">{asTable ? t("chart") : t("table")}</span>
            </Button>
          ) : null}
        </div>
      </div>
      {showLegend && !asTable ? (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground" data-testid="chart-legend">
          {spec.series.map((s) => (
            <li key={s.key} className="inline-flex items-center gap-1.5">
              <span aria-hidden className={cn("inline-block", s.kind === "line" ? "h-0.5 w-4" : "size-2.5 rounded-sm")} style={{ background: seriesColor(s.color_role, s.key) }} />
              {L(s.label_en, s.label_ar)}
            </li>
          ))}
          {Array.from(new Map(spec.bands.map((b) => [L(b.label_en, b.label_ar), b])).keys()).map((label) => (
            <li key={`band-${label}`} className="inline-flex items-center gap-1.5">
              <span aria-hidden className="inline-block h-2.5 w-4 rounded-sm border" style={{ background: "var(--muted)" }} />
              {label}
            </li>
          ))}
          {spec.reference_lines.map((r, i) => (
            <li key={`ref-${i}`} className="inline-flex items-center gap-1.5">
              <span aria-hidden className="inline-block h-0 w-4 border-t-2 border-dashed" style={{ borderColor: seriesColor(r.color_role ?? "target") }} />
              {L(r.label_en, r.label_ar)} {digits(r.display)}
            </li>
          ))}
        </ul>
      ) : null}
      {empty ? (
        <p className="py-8 text-center text-sm text-muted-foreground">{t("noData")}</p>
      ) : asTable || !canChart ? (
        <ChartTable spec={spec} rows={rows} ar={ar} digits={digits} />
      ) : (
        <div className="flex flex-col gap-3">
          {panels.map(({ axis, series }, idx) => (
            <div key={axis.id}>
              {panels.length > 1 ? (
                <p className="mb-1 text-xs font-medium text-muted-foreground">
                  {axisCaption(L(axis.label_en, axis.label_ar), axis.unit_en ? L(axis.unit_en, axis.unit_ar ?? "") : "")}
                </p>
              ) : null}
              <div
                style={{
                  height: panels.length > 1 ? Math.max(140, Math.round(height / panels.length) + 30) : height,
                }}
                dir="ltr"
              >
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart
                    data={plotRows}
                    layout={horizontal ? "vertical" : "horizontal"}
                    margin={{ top: 8, right: 12, bottom: 0, left: 12 }}
                    barCategoryGap="20%"
                    accessibilityLayer
                  >
                    <CartesianGrid stroke="var(--chart-grid)" vertical={false} horizontal={!horizontal} strokeDasharray={undefined} />
                    {horizontal ? (
                      <>
                        <XAxis
                          type="number"
                          tick={{
                            fill: "var(--muted-foreground)",
                            fontSize: 11,
                          }}
                          tickFormatter={(v: number) => digits(String(v))}
                          axisLine={false}
                          tickLine={false}
                          reversed={ar}
                        />
                        <YAxis
                          type="category"
                          dataKey="label"
                          width={120}
                          orientation={ar ? "right" : "left"}
                          tick={{
                            fill: "var(--muted-foreground)",
                            fontSize: 11,
                          }}
                          axisLine={{ stroke: "var(--chart-axis)" }}
                          tickLine={false}
                          interval={0}
                        />
                      </>
                    ) : (
                      <>
                        <XAxis
                          dataKey="label"
                          tick={{
                            fill: "var(--muted-foreground)",
                            fontSize: 11,
                          }}
                          axisLine={{ stroke: "var(--chart-axis)" }}
                          tickLine={false}
                          hide={panels.length > 1 && idx < panels.length - 1}
                          interval="preserveStartEnd"
                          minTickGap={8}
                        />
                        <YAxis
                          orientation={ar ? "right" : "left"}
                          width={48}
                          tick={{
                            fill: "var(--muted-foreground)",
                            fontSize: 11,
                          }}
                          tickFormatter={(v: number) => digits(compact(v))}
                          axisLine={false}
                          tickLine={false}
                          allowDecimals
                        />
                      </>
                    )}
                    {!horizontal
                      ? spec.bands.map((b, i) => {
                          const from = rows.find((r) => r.x === b.x_from)?.label;
                          const to = rows.find((r) => r.x === b.x_to)?.label;
                          return from && to ? (
                            <ReferenceArea
                              key={`band-${i}`}
                              x1={ar ? to : from}
                              x2={ar ? from : to}
                              fill="var(--muted)"
                              fillOpacity={0.7}
                              stroke="none"
                              ifOverflow="extendDomain"
                            />
                          ) : null;
                        })
                      : null}
                    {spec.reference_lines
                      .filter((r) => r.y_axis === axis.id || panels.length === 1)
                      .map((r, i) => (
                        <ReferenceLine
                          key={`rl-${i}`}
                          {...(horizontal ? { x: Number(r.value) } : { y: Number(r.value) })}
                          stroke={seriesColor(r.color_role ?? "target")}
                          strokeDasharray="4 4"
                          strokeWidth={1.5}
                          ifOverflow="extendDomain"
                        />
                      ))}
                    <Tooltip content={(p) => <ChartTooltip {...p} series={series} ar={ar} digits={digits} />} cursor={{ fill: "var(--accent)", opacity: 0.5 }} />
                    {series.map((s, si) => {
                      const color = seriesColor(s.color_role, s.key);
                      const lastInStack = s.stack ? series.filter((x) => x.stack === s.stack).at(-1)?.key === s.key : true;
                      const click = onPointClick ? (d: { payload?: Row }) => d.payload && onPointClick(s.key, String(d.payload.x)) : undefined;
                      if (s.kind === "line")
                        return (
                          <Line
                            key={s.key}
                            dataKey={s.key}
                            name={L(s.label_en, s.label_ar)}
                            type="linear"
                            stroke={color}
                            strokeWidth={2}
                            dot={{
                              r: 4,
                              strokeWidth: 2,
                              stroke: "var(--surface)",
                              fill: color,
                            }}
                            activeDot={{
                              r: 6,
                              strokeWidth: 2,
                              stroke: "var(--surface)",
                              fill: color,
                              onClick: onPointClick ? (_e: unknown, d: unknown) => click?.(d as { payload?: Row }) : undefined,
                            }}
                            connectNulls={false}
                            isAnimationActive={false}
                          />
                        );
                      if (s.kind === "area")
                        return (
                          <Area
                            key={s.key}
                            dataKey={s.key}
                            name={L(s.label_en, s.label_ar)}
                            stroke={color}
                            fill={color}
                            fillOpacity={0.15}
                            strokeWidth={2}
                            stackId={s.stack ?? undefined}
                            isAnimationActive={false}
                          />
                        );
                      const r = 4;
                      const radius: [number, number, number, number] = horizontal ? (ar ? [r, 0, 0, r] : [0, r, r, 0]) : [r, r, 0, 0];
                      return (
                        <Bar
                          key={s.key}
                          dataKey={s.key}
                          name={L(s.label_en, s.label_ar)}
                          fill={color}
                          stackId={spec.kind === "stacked_bar" || s.stack ? (s.stack ?? "stack") : undefined}
                          maxBarSize={24}
                          radius={lastInStack ? radius : 0}
                          stroke="var(--surface)"
                          strokeWidth={spec.kind === "stacked_bar" || s.stack ? 1 : 0}
                          isAnimationActive={false}
                          onClick={click}
                          cursor={onPointClick ? "pointer" : undefined}
                          data-series-index={si}
                        />
                      );
                    })}
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>
          ))}
        </div>
      )}
      {spec.table && canChart && !asTable && !empty ? <SpecTable table={spec.table} ar={ar} digits={digits} /> : null}
      {spec.notes.length > 0 ? (
        <ul className="text-xs text-muted-foreground">
          {spec.notes.map((n, i) => (
            <li key={i}>{L(n.message_en, n.message_ar)}</li>
          ))}
        </ul>
      ) : null}
      <p className="text-[11px] text-muted-foreground" data-testid="chart-citation">
        {spec.citation.period_label_en} · {spec.citation.scope_label_en}
        {spec.citation.base_label_en ? ` · ${spec.citation.base_label_en}` : ""}
      </p>
    </figure>
  );
}

function compact(v: number): string {
  const a = Math.abs(v);
  if (a >= 1_000_000) return `${(v / 1_000_000).toFixed(a >= 10_000_000 ? 0 : 1)}M`;
  if (a >= 1_000) return `${(v / 1_000).toFixed(a >= 10_000 ? 0 : 1)}k`;
  return String(Math.round(v * 100) / 100);
}

function ChartTooltip({
  active,
  payload,
  label,
  series,
  ar,
  digits,
}: TooltipContentProps<ValueType, NameType> & {
  series: Series[];
  ar: boolean;
  digits: (s: string) => string;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload as Row | undefined;
  if (!row) return null;
  return (
    <div className="rounded-md border bg-surface px-3 py-2 text-xs shadow-md" dir={ar ? "rtl" : "ltr"}>
      <p className="mb-1 font-medium">{String(label ?? row.label)}</p>
      <ul className="flex flex-col gap-0.5">
        {series.map((s) => (
          <li key={s.key} className="flex items-center justify-between gap-4">
            <span className="inline-flex items-center gap-1.5 text-muted-foreground">
              <span aria-hidden className="inline-block size-2 rounded-sm" style={{ background: seriesColor(s.color_role, s.key) }} />
              {ar ? s.label_ar || s.label_en : s.label_en}
            </span>
            <span className="font-medium tabular-nums">{digits(String(row[`${s.key}__d`] ?? "—"))}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** A backend-supplied companion table (e.g. C9 control-level mix) shown under the chart. */
function SpecTable({ table, ar, digits }: { table: NonNullable<Spec["table"]>; ar: boolean; digits: (s: string) => string }) {
  return (
    <div className="overflow-x-auto" data-testid="chart-spec-table">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-xs text-muted-foreground">
            {table.columns.map((c) => (
              <th key={c.key} className={cn("px-2 py-1.5 font-medium", c.numeric ? "text-end" : "text-start")}>
                {ar ? c.label_ar || c.label_en : c.label_en}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((r, i) => (
            <tr key={i} className="border-b last:border-0">
              {table.columns.map((c) => {
                const v = String((r as Record<string, unknown>)[c.key] ?? "—");
                return (
                  <td key={c.key} className={cn("px-2 py-1.5", c.numeric && "text-end tabular-nums")}>
                    {c.numeric ? digits(v) : v}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ChartTable({ spec, rows, ar, digits }: { spec: Spec; rows: Row[]; ar: boolean; digits: (s: string) => string }) {
  if (spec.table && (spec.kind === "table" || spec.kind === "pyramid" || !spec.x_axis)) {
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-sm" data-testid="chart-table">
          <thead>
            <tr className="border-b text-xs text-muted-foreground">
              {spec.table.columns.map((c) => (
                <th key={c.key} className={cn("px-2 py-1.5 font-medium", c.numeric ? "text-end" : "text-start")}>
                  {ar ? c.label_ar || c.label_en : c.label_en}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {spec.table.rows.map((r, i) => (
              <tr key={i} className="border-b last:border-0">
                {spec.table!.columns.map((c) => (
                  <td key={c.key} className={cn("px-2 py-1.5", c.numeric && "text-end tabular-nums")}>
                    {c.numeric ? digits(String((r as Record<string, unknown>)[c.key] ?? "—")) : String((r as Record<string, unknown>)[c.key] ?? "—")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  const ordered = rows;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" data-testid="chart-table">
        <thead>
          <tr className="border-b text-xs text-muted-foreground">
            <th className="px-2 py-1.5 text-start font-medium">{ar ? spec.x_axis?.label_ar || spec.x_axis?.label_en : spec.x_axis?.label_en}</th>
            {spec.series.map((s) => (
              <th key={s.key} className="px-2 py-1.5 text-end font-medium">
                {ar ? s.label_ar || s.label_en : s.label_en}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ordered.map((r) => (
            <tr key={r.x} className="border-b last:border-0">
              <th scope="row" className="px-2 py-1.5 text-start font-normal">
                {r.label}
              </th>
              {spec.series.map((s) => (
                <td key={s.key} className="px-2 py-1.5 text-end tabular-nums">
                  {digits(String(r[`${s.key}__d`] ?? "—"))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
