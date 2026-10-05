"use client";
import { useLocale } from "next-intl";
import { useCallback, useMemo } from "react";
import { useProjectSettings } from "@/lib/api/queries";
import { useCurrentProject } from "@/lib/current-project";
import { DEFAULT_TIME_ZONE, formatDate, formatDateTime, formatHijri, type DateDisplayPrefs } from "@/lib/datetime";

/** Date formatters honouring the given project's settings (or the current project's). */
export function useFormatters(projectId?: string | null) {
  const locale = useLocale() === "ar" ? "ar" : "en";
  const { projectId: currentId } = useCurrentProject();
  const settings = useProjectSettings(projectId ?? currentId);
  const s = settings.data;
  const prefs = useMemo<DateDisplayPrefs>(
    () => ({
      locale,
      timeZone: s?.timezone ?? DEFAULT_TIME_ZONE,
      showHijri: s?.show_hijri ?? false,
      digits: s?.digits ?? "western",
      dateFormatEn: s?.date_format_en ?? "DD MMM YYYY",
    }),
    [locale, s],
  );
  const date = useCallback((v: string | null | undefined) => formatDate(v, prefs), [prefs]);
  const dateTime = useCallback((v: string | null | undefined) => formatDateTime(v, prefs), [prefs]);
  const hijri = useCallback((v: string) => formatHijri(v, prefs), [prefs]);
  return { date, dateTime, hijri, prefs };
}
