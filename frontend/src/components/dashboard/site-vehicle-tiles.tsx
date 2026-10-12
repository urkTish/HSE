"use client";
import { TriangleAlert } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { PrototypeBadge, useSvAny } from "@/components/site-vehicles/common";
import { Link } from "@/i18n/navigation";
import type { Schemas } from "@/lib/api/client";
import type { KpiQuery } from "@/lib/api/kpi";
import { useSiteVehicleKpis, useSvSettings } from "@/lib/api/site-vehicles";
import { isReadOnly } from "@/lib/permissions";
import { useMeData } from "@/components/shell/me-context";
import { cn } from "@/lib/utils";

const METRICS: Schemas["KpiMetric"][] = ["K-138", "K-139", "K-140"];

/**
 * "Site vehicles (Prototype)" tiles K-138…K-140 (7b §8, D-256): read from GET /kpi/site-vehicles with the
 * dashboard filters; values, chips and "—" exactly as the server returns them. Shown when 7b is switched on.
 */
export function SiteVehicleTiles({ query, projectId, show }: { query: KpiQuery; projectId: string | null; show: (v: string) => string }) {
  const t = useTranslations("sv.dash");
  const any = useSvAny(projectId);
  const settings = useSvSettings(projectId ?? "", { enabled: Boolean(projectId) && any });
  const live = Boolean(projectId) && any && Boolean(settings.data?.live);
  const q = useSiteVehicleKpis({ ...query, metric: METRICS }, { enabled: live });
  if (!live || !q.data) return null;
  return (
    <section aria-labelledby="sv-tiles-h" data-testid="sv-tiles">
      <h2 id="sv-tiles-h" className="mb-2 flex items-center gap-2 text-sm font-semibold">
        {t("title")}
        <PrototypeBadge compact />
      </h2>
      <div className={cn("grid grid-cols-1 gap-3 sm:grid-cols-3 transition-opacity", q.isPlaceholderData && "opacity-60")}>
        {METRICS.map((m) => {
          const v = q.data.metrics.find((x) => x.metric === m);
          return v ? <Tile key={m} v={v} projectId={projectId} show={show} /> : null;
        })}
      </div>
    </section>
  );
}

const CHIP_TONE: Record<string, string> = {
  "readiness:docs_expired": "border-danger/30 text-danger",
  "readiness:defect_hold": "border-danger/30 text-danger",
  "readiness:not_certified": "border-danger/30 text-danger",
};

function Tile({ v, projectId, show }: { v: Schemas["KpiValue"]; projectId: string | null; show: (v: string) => string }) {
  const t = useTranslations("sv.dash");
  const te = useTranslations("enums");
  const ar = useLocale() === "ar";
  const me = useMeData();
  // The Viewer / Client sees aggregates only (P7b-1): the registers behind the tile are not linked.
  const href = projectId && !isReadOnly(me, projectId) ? (v.metric === "K-138" ? "/site-vehicles" : v.metric === "K-140" ? "/site-vehicles/checks" : "/site-vehicles/authorisations") : null;
  const value = (
    <span className={cn("text-3xl font-semibold tabular-nums", v.rag === "red" && "text-danger", v.rag === "amber" && "text-warning")} data-testid="sv-tile-value">
      {show(v.display)}
    </span>
  );
  return (
    <div className="flex flex-col gap-1.5 rounded-xl border bg-surface p-4 shadow-xs" data-testid="sv-tile" data-metric={v.metric} data-value={v.value ?? ""}>
      <span className="flex items-center justify-between gap-2 text-xs font-medium text-muted-foreground">
        <span>{ar ? v.short_label_ar : v.short_label_en}</span>
        <span className="ltr font-mono">{v.metric}</span>
      </span>
      {href ? (
        <Link href={href} className="self-start rounded hover:underline" aria-label={t("open", { label: ar ? v.label_ar : v.label_en })}>
          {value}
        </Link>
      ) : (
        value
      )}
      {v.null_reason ? <span className="text-xs text-muted-foreground">{te.has(`nullReason.${v.null_reason}` as "nullReason.NO_DENOMINATOR") ? te(`nullReason.${v.null_reason}` as "nullReason.NO_DENOMINATOR") : v.null_reason}</span> : null}
      {v.numerator !== null && v.denominator !== null && v.value !== null ? (
        <span className="text-xs text-muted-foreground tabular-nums">
          {t("fraction", { n: show(String(v.numerator)), d: show(String(v.denominator)) })}
        </span>
      ) : null}
      {v.rag && v.rag !== "green" ? (
        <span className={cn("inline-flex items-center gap-1 text-xs font-medium", v.rag === "red" ? "text-danger" : "text-warning")}>
          <TriangleAlert aria-hidden className="size-3.5" />
          {te(`rag.${v.rag}`)}
        </span>
      ) : null}
      {v.components.length ? (
        <ul className="flex flex-wrap gap-1" data-testid="sv-tile-chips">
          {v.components.map((c) => (
            <li key={c.key} className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] text-muted-foreground", CHIP_TONE[c.key])} data-testid="sv-chip" data-key={c.key} data-value={c.value ?? ""}>
              {ar ? c.label_ar : c.label_en}
              <span className="font-semibold text-foreground tabular-nums">{show(c.display)}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <span className="text-xs text-muted-foreground">{ar ? v.label_ar : v.label_en}</span>
    </div>
  );
}
