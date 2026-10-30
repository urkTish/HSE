// Twelve-month climate-normals chart bound to climate-normals.schema.json.
// Hand-written SVG, three small panels sharing one month axis (no dual axis):
// temperature range (average daily low → high, split at 0 °C), precipitation
// (mm) and snowfall (cm). Period, station and source are always shown, and a
// table view carries the same numbers for screen readers and print.
import { useId, useState, type ReactNode } from "react";
import type { ClimMonth, ClimRecord } from "../kb/types";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const W = 360;
const ML = 34;
const MR = 8;
const PLOT_W = W - ML - MR;
const STEP = PLOT_W / 12;
const BAR_W = Math.min(14, STEP * 0.55);
const cx = (i: number) => ML + STEP * i + STEP / 2;

const fmt = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined ? "—" : v.toLocaleString("en-CA", { maximumFractionDigits: digits, minimumFractionDigits: 0 });
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

function niceTicks(min: number, max: number, target = 4): number[] {
  const span = Math.max(1, max - min);
  const raw = span / target;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const ticks: number[] = [];
  const end = Math.ceil(max / step) * step;
  for (let t = Math.floor(min / step) * step; t <= end + 1e-9; t += step) ticks.push(Math.round(t * 100) / 100);
  return ticks;
}

interface PanelProps {
  title: ReactNode;
  height: number;
  ticks: number[];
  y: (v: number) => number;
  active: number | null;
  setActive: (i: number | null) => void;
  monthAxis?: boolean;
  missing: boolean[];
  patternId: string;
  children: ReactNode;
}

function Panel({ title, height, ticks, y, active, setActive, monthAxis, missing, patternId, children }: PanelProps) {
  const top = 6;
  const bottom = height - (monthAxis ? 16 : 4);
  return (
    <figure className="m-0">
      <figcaption className="mb-0.5 text-2xs text-ink-2">{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${height}`} className="block h-auto w-full" aria-hidden="true">
        {active !== null && <rect x={ML + STEP * active} y={top} width={STEP} height={bottom - top} fill="var(--ce-surface-2)" />}
        {ticks.map((t) => (
          <g key={t}>
            <line x1={ML} x2={W - MR} y1={y(t)} y2={y(t)} stroke="var(--ce-chart-grid)" strokeWidth={1} />
            <text x={ML - 4} y={y(t) + 3.5} textAnchor="end" fontSize={10} fill="var(--ce-ink-3)">
              {fmt(t, 0)}
            </text>
          </g>
        ))}
        {missing.map((m, i) =>
          m ? <rect key={i} x={cx(i) - BAR_W / 2} y={top} width={BAR_W} height={bottom - top} fill={`url(#${patternId})`} /> : null,
        )}
        {children}
        {monthAxis &&
          MONTHS.map((m, i) => (
            <text key={m} x={cx(i)} y={height - 3} textAnchor="middle" fontSize={10} fill="var(--ce-ink-3)">
              {m[0]}
            </text>
          ))}
        {MONTHS.map((m, i) => (
          <rect
            key={m}
            x={ML + STEP * i}
            y={0}
            width={STEP}
            height={height}
            fill="transparent"
            onMouseEnter={() => setActive(i)}
            onMouseLeave={() => setActive(null)}
          />
        ))}
      </svg>
    </figure>
  );
}

function bars(values: (number | null)[], y: (v: number) => number, colour: string) {
  return values.map((v, i) => {
    if (v === null) return null;
    const y0 = y(0);
    // Zero is data (null is not): a 1px baseline tick.
    if (v === 0) return <line key={i} x1={cx(i) - BAR_W / 2} x2={cx(i) + BAR_W / 2} y1={y0 - 0.5} y2={y0 - 0.5} stroke={colour} strokeWidth={1} />;
    const y1 = y(v);
    const h = Math.max(0, y0 - y1);
    // 2px rounded data-end anchored to the baseline.
    const r = Math.min(2, h / 2, BAR_W / 2);
    const x = cx(i) - BAR_W / 2;
    const d = `M${x},${y0} V${y1 + r} Q${x},${y1} ${x + r},${y1} H${x + BAR_W - r} Q${x + BAR_W},${y1} ${x + BAR_W},${y1 + r} V${y0} Z`;
    return <path key={i} d={d} fill={colour} />;
  });
}

export default function ClimateChart({ record }: { record: ClimRecord }) {
  const a = record.attributes;
  const patternId = `hatch-${useId().replace(/[^a-zA-Z0-9-]/g, "")}`;
  const [active, setActive] = useState<number | null>(null);

  const months: ClimMonth[] = MONTHS.map(
    (_, i) => a.months.find((m) => m.month === i + 1) ?? { month: i + 1, tmax_c: null, tmin_c: null, precip_mm: null },
  );
  const hi = months.map((m) => num(m.tmax_c));
  const lo = months.map((m) => num(m.tmin_c));
  const mean = months.map((m) => num(m.tmean_c));
  const pr = months.map((m) => num(m.precip_mm));
  const sn = months.map((m) => num(m.snow_cm));
  const sun = months.map((m) => num(m.sunshine_h));
  const hasSnow = sn.some((v) => v !== null);
  const hasSun = sun.some((v) => v !== null);
  const src = record.sources[0];

  // Temperature scale (always includes 0 °C).
  const temps = [...hi, ...lo].filter((v): v is number => v !== null);
  const tMin = Math.min(0, ...temps);
  const tMax = Math.max(0, ...temps);
  const tTicks = niceTicks(tMin, tMax);
  const tLo = Math.min(tTicks[0] ?? tMin, tMin);
  const tHi = Math.max(tTicks[tTicks.length - 1] ?? tMax, tMax);
  const TH = 130;
  const yT = (v: number) => 14 + ((tHi - v) / (tHi - tLo || 1)) * (TH - 14 - 14);

  const pMax = Math.max(10, ...pr.filter((v): v is number => v !== null));
  const pTicks = niceTicks(0, pMax, 3);
  const pTop = Math.max(pMax, pTicks[pTicks.length - 1] ?? pMax);
  // The precipitation panel carries the month axis when there is no snowfall panel.
  const PH = hasSnow ? 72 : 84;
  const pBottom = hasSnow ? 4 : 16;
  const yP = (v: number) => 6 + ((pTop - v) / pTop) * (PH - pBottom - 6);

  const sMax = Math.max(10, ...sn.filter((v): v is number => v !== null));
  const sTicks = niceTicks(0, sMax, 3);
  const sTop = Math.max(sMax, sTicks[sTicks.length - 1] ?? sMax);
  const SH = 88;
  const yS = (v: number) => 6 + ((sTop - v) / sTop) * (SH - 16 - 6);

  const warmest = hi.reduce<number | null>((b, v, i) => (v !== null && (b === null || v > (hi[b] as number)) ? i : b), null);
  const coldest = lo.reduce<number | null>((b, v, i) => (v !== null && (b === null || v < (lo[b] as number)) ? i : b), null);

  const summary =
    `Climate normals ${a.normals_period} at ${a.station_name}. ` +
    (warmest !== null ? `Warmest average high ${fmt(hi[warmest])} °C in ${MONTHS[warmest]}. ` : "") +
    (coldest !== null ? `Coldest average low ${fmt(lo[coldest])} °C in ${MONTHS[coldest]}. ` : "") +
    (num(a.annual?.precip_mm) !== null ? `Annual precipitation ${fmt(a.annual.precip_mm, 0)} mm. ` : "") +
    (num(a.annual?.snow_cm) !== null ? `Annual snowfall ${fmt(a.annual.snow_cm, 0)} cm.` : "");

  const am = active !== null ? months[active] : null;

  return (
    <div
      className="relative rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      role="group"
      aria-label={`${summary} Use the left and right arrow keys to read each month.`}
      tabIndex={0}
      onKeyDown={(e) => {
        const next = e.key === "ArrowRight" ? (active ?? -1) + 1 : e.key === "ArrowLeft" ? (active ?? 12) - 1 : e.key === "Home" ? 0 : e.key === "End" ? 11 : null;
        if (next === null) return;
        e.preventDefault();
        setActive(Math.max(0, Math.min(11, next)));
      }}
      onBlur={() => setActive(null)}
    >
      <svg width="0" height="0" className="absolute" aria-hidden="true">
        <defs>
          <pattern id={patternId} width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="4" stroke="var(--ce-chart-missing)" strokeWidth="1" />
          </pattern>
        </defs>
      </svg>

      <p className="text-sm font-semibold text-ink">Climate normals, {a.normals_period.replace("-", "–")}</p>
      <p className="mb-2 text-xs text-ink-2">30-year averages, not a forecast.</p>
      {a.normals_period !== "1991-2020" && (
        <p className="mb-2 rounded-sm bg-status-info-soft px-2 py-1 text-xs text-status-info">
          Older period: ECCC has not published 1991–2020 normals for this station.
        </p>
      )}
      {num(a.distance_to_city_centre_km) !== null && (a.distance_to_city_centre_km as number) > 10 && (
        <p className="mb-2 rounded-sm bg-status-info-soft px-2 py-1 text-xs text-status-info">
          Station is {fmt(a.distance_to_city_centre_km, 0)} km from the centre; airport stations can be cooler or windier.
        </p>
      )}

      <div className="space-y-1">
        <Panel
          title={<>Temperature, °C: bar spans the average daily low to the average daily high{mean.some((v) => v !== null) ? "; tick = monthly mean" : ""}</>}
          height={TH}
          ticks={tTicks}
          y={yT}
          active={active}
          setActive={setActive}
          missing={months.map((_, i) => hi[i] === null || lo[i] === null)}
          patternId={patternId}
        >
          <line x1={ML} x2={W - MR} y1={yT(0)} y2={yT(0)} stroke="var(--ce-chart-reference)" strokeWidth={1.5} />
          {months.map((_, i) => {
            const h = hi[i] ?? null;
            const l = lo[i] ?? null;
            if (h === null || l === null) return null;
            const x = cx(i) - BAR_W / 2;
            const parts: ReactNode[] = [];
            if (l < 0) parts.push(<rect key="c" x={x} y={yT(Math.min(h, 0))} width={BAR_W} height={yT(l) - yT(Math.min(h, 0))} rx={2} fill="var(--ce-chart-cold)" />);
            if (h >= 0) parts.push(<rect key="w" x={x} y={yT(h)} width={BAR_W} height={yT(Math.max(l, 0)) - yT(h)} rx={2} fill="var(--ce-chart-warm)" />);
            const m = mean[i] ?? null;
            return (
              <g key={i}>
                {parts}
                {m !== null && <line x1={x - 2} x2={x + BAR_W + 2} y1={yT(m)} y2={yT(m)} stroke="var(--ce-chart-mean)" strokeWidth={2} />}
              </g>
            );
          })}
          {warmest !== null && (
            <text x={cx(warmest)} y={yT(hi[warmest] as number) - 3} textAnchor="middle" fontSize={10} fill="var(--ce-ink-2)">
              {fmt(hi[warmest])}
            </text>
          )}
          {coldest !== null && (
            <text x={cx(coldest)} y={yT(lo[coldest] as number) + 11} textAnchor="middle" fontSize={10} fill="var(--ce-ink-2)">
              {fmt(lo[coldest])}
            </text>
          )}
        </Panel>

        <Panel
          title={<>Precipitation, mm (rain and melted snow){num(a.annual?.precip_mm) !== null ? `, annual ${fmt(a.annual.precip_mm, 0)} mm` : ""}</>}
          height={PH}
          ticks={pTicks}
          y={yP}
          active={active}
          setActive={setActive}
          missing={pr.map((v) => v === null)}
          patternId={patternId}
          monthAxis={!hasSnow}
        >
          {bars(pr, yP, "var(--ce-chart-precip)")}
        </Panel>

        {hasSnow ? (
          <Panel
            title={<>Snowfall, cm{num(a.annual?.snow_cm) !== null ? `, annual ${fmt(a.annual.snow_cm, 0)} cm` : ""}</>}
            height={SH}
            ticks={sTicks}
            y={yS}
              active={active}
            setActive={setActive}
            missing={sn.map((v) => v === null)}
            patternId={patternId}
            monthAxis
          >
            {bars(sn, yS, "var(--ce-chart-snow)")}
          </Panel>
        ) : null}
      </div>

      <p className="sr-only" aria-live="polite">
        {am
          ? `${MONTHS[am.month - 1]}: high ${fmt(am.tmax_c)} °C, low ${fmt(am.tmin_c)} °C, precipitation ${fmt(am.precip_mm)} mm${hasSnow ? `, snowfall ${fmt(am.snow_cm)} cm` : ""}.`
          : ""}
      </p>
      {am && (
        <div className="pointer-events-none absolute right-0 top-8 z-10 min-w-36 rounded-md bg-surface-inverse px-2 py-1.5 text-xs text-ink-inverse shadow-3" role="status">
          <div className="font-semibold">{MONTHS[am.month - 1]}</div>
          <div>High {fmt(am.tmax_c)} °C · Low {fmt(am.tmin_c)} °C</div>
          {num(am.tmean_c) !== null && <div>Mean {fmt(am.tmean_c)} °C</div>}
          <div>Precipitation {fmt(am.precip_mm)} mm</div>
          {hasSnow && <div>Snowfall {fmt(am.snow_cm)} cm</div>}
        </div>
      )}

      <p className="mt-2 text-2xs leading-snug text-ink-3">
        <span className="font-semibold text-ink-2">Normals {a.normals_period}</span> · Station {a.station_name} (Climate ID {a.climate_id}
        {num(a.elevation_m) !== null ? `, ${fmt(a.elevation_m, 0)} m` : ""}
        {num(a.distance_to_city_centre_km) !== null ? `, ${fmt(a.distance_to_city_centre_km)} km from the city centre` : ""}) · Source:{" "}
        {src ? (
          <>
            <a className="underline" href={src.url} target="_blank" rel="noopener noreferrer">
              {src.publisher}
            </a>
            , accessed {src.accessed}
          </>
        ) : (
          "not recorded"
        )}
        {record.sources.length > 1 ? ` (+${record.sources.length - 1} more under Sources)` : ""}
      </p>

      <details className="mt-2 text-xs">
        <summary className="cursor-pointer text-ink-2">Show the numbers as a table</summary>
        <div className="mt-1 overflow-x-auto">
          <table className="w-full border-collapse text-right tabular-nums">
            <caption className="sr-only">Monthly climate normals {a.normals_period}, {a.station_name}</caption>
            <thead>
              <tr className="bg-surface-2 text-ink-2">
                <th scope="col" className="px-1 py-0.5 text-left">Month</th>
                <th scope="col" className="px-1">High °C</th>
                <th scope="col" className="px-1">Low °C</th>
                <th scope="col" className="px-1">Mean °C</th>
                <th scope="col" className="px-1">Precip. mm</th>
                <th scope="col" className="px-1">Rain mm</th>
                <th scope="col" className="px-1">Snow cm</th>
                {hasSun && <th scope="col" className="px-1">Sun h</th>}
              </tr>
            </thead>
            <tbody>
              {months.map((m) => (
                <tr key={m.month} className="border-b border-line">
                  <th scope="row" className="px-1 py-0.5 text-left font-normal">{MONTHS[m.month - 1]?.slice(0, 3)}</th>
                  <td className="px-1">{fmt(m.tmax_c)}</td>
                  <td className="px-1">{fmt(m.tmin_c)}</td>
                  <td className="px-1">{fmt(m.tmean_c)}</td>
                  <td className="px-1">{fmt(m.precip_mm)}</td>
                  <td className="px-1">{fmt(m.rain_mm)}</td>
                  <td className="px-1">{fmt(m.snow_cm)}</td>
                  {hasSun && <td className="px-1">{fmt(m.sunshine_h, 0)}</td>}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="font-semibold">
                <th scope="row" className="px-1 py-0.5 text-left">Year</th>
                <td className="px-1" />
                <td className="px-1" />
                <td className="px-1">{fmt(a.annual?.tmean_c)}</td>
                <td className="px-1">{fmt(a.annual?.precip_mm, 0)}</td>
                <td className="px-1">{fmt(a.annual?.rain_mm, 0)}</td>
                <td className="px-1">{fmt(a.annual?.snow_cm, 0)}</td>
                {hasSun && <td className="px-1">{fmt(a.annual?.sunshine_h, 0)}</td>}
              </tr>
            </tfoot>
          </table>
          <p className="mt-1 text-2xs text-ink-3">— = not published for this station. Annual values are the record's own, never recomputed from months.</p>
        </div>
      </details>
    </div>
  );
}
