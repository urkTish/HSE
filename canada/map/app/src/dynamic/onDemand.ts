// Dynamic retrieval module (SPEC §9 E, §12 "retrieved or refreshed on demand").
//
// Phase 1 has no on-demand service. Prices, rents, tuition amounts, mortgage
// rates and forecasts are deliberately absent from the static data (see
// scripts/build-data.mjs and ARCHITECTURE.md §4). Phase 4 implements the
// sources designed by Agent 02 (knowledge-base/real-estate/METHODOLOGY.md §5):
//   - Statistics Canada Web Data Service, getDataFromVectorsAndLatestNPeriods
//     (two-bedroom rents, vacancy rates; cache 7 days per vector);
//   - Bank of Canada Valet, series V80691335 (posted 5-year rate; cache 24 h;
//     calculator pre-fill only, never stored);
//   - CREA HPI and CMHC pages as link-outs only (DECISIONS D-008).
// This module is the only place the UI calls. Every available answer carries
// the value and unit, metric and figure kind, period, source and retrieval
// date; a failed fetch returns the source link and never an estimate.

export interface OnDemandSource {
  url: string;
  publisher: string;
  /** Table or series, e.g. "Table 34-10-0133-01, v3824154" or "Valet V80691335". */
  series?: string;
}

export interface OnDemandAnswer {
  status: "available" | "unavailable";
  value?: number;
  unit?: string;
  /** Metric and figure kind in words, e.g. "average rent, 2-bedroom, survey". */
  label?: string;
  period?: string;
  /** ISO date the figure was retrieved. */
  retrieved?: string;
  /** True when the period's release is more than 60 days old (SPEC §2.7). */
  olderThan60Days?: boolean;
  source?: OnDemandSource;
  /** Link to open when the figure is unavailable. */
  fallbackUrl?: string;
  reason?: string;
}

export type OnDemandQuery =
  | { kind: "market-figure"; recordId: string }
  | { kind: "tuition"; recordId: string }
  | { kind: "mortgage-rate-posted-5y" };

export async function requestOnDemand(query: OnDemandQuery): Promise<OnDemandAnswer> {
  void query;
  return {
    status: "unavailable",
    reason: "No on-demand data service is connected yet (planned for Phase 4). Changing figures are never stored in the map's files.",
  };
}
