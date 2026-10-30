// Dynamic retrieval module (SPEC §9 E, §12 "retrieved or refreshed on demand").
//
// Phase 1 has no on-demand service. Prices, rents, tuition amounts, mortgage
// rates and forecasts are deliberately absent from the static data (see
// scripts/build-data.mjs). Phase 4 adds a thin service; this module is the
// only place the UI will call it, and every answer must carry its date and
// source. Until then the UI states plainly that the figure is not available.

export interface OnDemandAnswer {
  status: "available" | "unavailable";
  value?: number;
  unit?: string;
  period?: string;
  source?: { url: string; publisher: string; retrieved: string };
  reason?: string;
}

export type OnDemandQuery =
  | { kind: "market-figure"; recordId: string }
  | { kind: "tuition"; recordId: string };

export async function requestOnDemand(query: OnDemandQuery): Promise<OnDemandAnswer> {
  void query;
  return {
    status: "unavailable",
    reason: "No on-demand data service is connected yet (planned for Phase 4). Changing figures are never stored in the map's files.",
  };
}
