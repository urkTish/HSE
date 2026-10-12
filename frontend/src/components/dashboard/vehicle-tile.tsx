"use client";
import { Info } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import type { Schemas } from "@/lib/api/client";
import { useKpi, type KpiQuery } from "@/lib/api/kpi";
import { cn } from "@/lib/utils";
import { DrillNumber } from "./drill";

/** C41 drill: the stacked road-type and "recorded, not counted" bars open K-136, the rate line K-137. */
export function C41_METRIC(seriesKey: string): Schemas["KpiMetric"] | null {
  return seriesKey === "k137" ? "K-137" : "K-136";
}

/**
 * K-136 vehicle incidents tile (7a §8): chips by road type, with injury and "Recorded, not counted" as the
 * backend returns them, plus the K-137 rate chip. Every value comes from the KPI engine; nothing is computed here.
 */
export function VehicleTileChips({ tile, query, show }: { tile: Schemas["KpiTile"]; query: KpiQuery; show: (v: string) => string }) {
  const t = useTranslations("veh");
  const ar = useLocale() === "ar";
  const k137 = useKpi("K-137", query);
  const rate = k137.data?.kpi;
  const chips = tile.components.filter((c) => c.key.startsWith("road_type:") || c.key === "with_injury" || c.key === "recorded_not_counted");
  return (
    <ul className="flex flex-wrap gap-1" aria-label={t("dash.chipsLabel")} data-testid="k136-chips">
      {chips.map((c) => {
        const rnc = c.key === "recorded_not_counted";
        return (
          <li
            key={c.key}
            className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px]", rnc ? "border-info/40 bg-info-bg text-info" : "text-muted-foreground")}
            data-testid="k136-chip"
            data-key={c.key}
            data-value={c.value ?? ""}
            title={rnc ? t("rnc.explain") : undefined}
          >
            {rnc ? <Info aria-hidden className="size-3" /> : null}
            {ar ? c.label_ar : c.label_en}
            <span className="font-semibold text-foreground tabular-nums">{show(c.display)}</span>
          </li>
        );
      })}
      {rate ? (
        <li className="inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] text-muted-foreground" data-testid="k136-chip" data-key="K-137" data-value={rate.value ?? ""}>
          <DrillNumber metric="K-137" label={ar ? rate.label_ar : rate.label_en} className="inline-flex items-center gap-1">
            {t("dash.k137")}
            <span className="font-semibold text-foreground tabular-nums">{show(rate.display)}</span>
          </DrillNumber>
        </li>
      ) : null}
    </ul>
  );
}
