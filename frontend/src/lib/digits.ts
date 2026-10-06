"use client";
import { useCallback } from "react";
import { useProjectSettings } from "@/lib/api/queries";
import { useCurrentProject } from "@/lib/current-project";

const ARABIC_INDIC = ["٠", "١", "٢", "٣", "٤", "٥", "٦", "٧", "٨", "٩"];

/** Replace Western digits with Arabic-Indic ones. Nothing else changes (no recomputation). */
export function toArabicIndic(s: string): string {
  return s.replace(/[0-9]/g, (d) => ARABIC_INDIC[Number(d)] ?? d);
}

/**
 * Show backend `display` strings as they are; the only client-side change allowed is the
 * digit mapping when the project's `digits` setting is `arabic_indic` (spec AI-13, D-1).
 */
export function useDisplay(projectId?: string | null) {
  const { projectId: current } = useCurrentProject();
  const settings = useProjectSettings(projectId ?? current);
  const arabic = settings.data?.digits === "arabic_indic";
  return useCallback(
    (v: string | number | null | undefined): string => {
      if (v === null || v === undefined || v === "") return "—";
      const s = String(v);
      return arabic ? toArabicIndic(s) : s;
    },
    [arabic],
  );
}

/** True when the project's number setting asks for Arabic-Indic digits (charts' tick labels). */
export function useArabicDigits(projectId?: string | null): boolean {
  const { projectId: current } = useCurrentProject();
  const settings = useProjectSettings(projectId ?? current);
  return settings.data?.digits === "arabic_indic";
}

/**
 * Thousands grouping for raw decimal strings from record APIs (e.g. man-hours "870000.00" → "870,000").
 * Presentation only: no rounding beyond two decimals, which the API already applied. KPI values keep
 * their backend `display` strings and never go through this.
 */
export function groupDecimal(v: string | number | null | undefined): string | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(n);
}
