// FigureValue (design/components.md §3): the one way a figure is displayed.
// Value and unit, figure kind in words, period, verification as icon + word,
// a staleness badge more than 60 days after the period ends (SPEC §2.7), and
// a link-only state when the figure is not stored in the map (D-008, Phase 1).
import type { Verification } from "../kb/types";

const STATUS: Record<Verification["status"], { icon: string; word: string; cls: string }> = {
  verified: { icon: "✓", word: "Verified", cls: "text-status-good" },
  partially_verified: { icon: "◐", word: "Partially verified", cls: "text-status-info" },
  unverified: { icon: "○", word: "Unverified", cls: "text-ink-3" },
  disputed: { icon: "!", word: "Disputed", cls: "text-status-warning" },
  outdated: { icon: "⌛", word: "Outdated", cls: "text-status-warning" },
};

const KIND: Record<string, string> = {
  survey: "survey figure",
  asking: "asking figure",
  transaction: "transaction figure",
  index: "index (benchmark)",
  estimate: "estimate",
};

/** Last day of a YYYY, YYYY-MM or YYYY-Qn period. */
export function periodEnd(period: string | null | undefined): Date | null {
  if (!period) return null;
  const q = /^(\d{4})-Q([1-4])$/.exec(period);
  if (q) return new Date(Date.UTC(Number(q[1]), Number(q[2]) * 3, 0));
  const m = /^(\d{4})-(\d{2})$/.exec(period);
  if (m) return new Date(Date.UTC(Number(m[1]), Number(m[2]), 0));
  const y = /^(\d{4})$/.exec(period);
  if (y) return new Date(Date.UTC(Number(y[1]), 12, 0));
  return null;
}

interface Props {
  label: string;
  value: number | string | null;
  unit?: string;
  figureKind?: string;
  period?: string | null;
  verification: Verification;
  linkOnly?: { label: string; url: string; reason: string };
}

export default function FigureValue({ label, value, unit, figureKind, period, verification, linkOnly }: Props) {
  const st = STATUS[verification.status];
  const end = periodEnd(period);
  const stale = end ? Date.now() - end.getTime() > 60 * 86_400_000 : false;
  return (
    <div className="rounded-md border border-line px-3 py-2">
      <div className="text-sm text-ink">{label}</div>
      <div className="mt-0.5 text-sm">
        {value !== null && value !== undefined ? (
          <span className="font-semibold tabular-nums">
            {typeof value === "number" ? value.toLocaleString("en-CA") : value}
            {unit ? ` ${unit}` : ""}
          </span>
        ) : linkOnly ? (
          <span className="text-ink-2">
            Not stored in the map —{" "}
            <a className="underline" href={linkOnly.url} target="_blank" rel="noopener noreferrer">
              {linkOnly.label}
            </a>
          </span>
        ) : (
          <span className="text-ink-3">— No data</span>
        )}
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-2xs text-ink-3">
        {figureKind && <span>{KIND[figureKind] ?? figureKind}</span>}
        {period && <span>Period {period}</span>}
        <span className={st.cls}>
          <span aria-hidden="true">{st.icon}</span> {st.word}
        </span>
        {stale && (
          <span className="rounded-xs bg-status-warning-soft px-1 text-status-warning">
            <span aria-hidden="true">⏱</span> Older than 60 days
          </span>
        )}
      </div>
      {linkOnly && value === null && <p className="mt-1 text-2xs text-ink-3">{linkOnly.reason}</p>}
    </div>
  );
}
