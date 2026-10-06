"use client";
import { useLocale } from "next-intl";
import { useCallback, useMemo } from "react";
import type { Schemas } from "@/lib/api/client";
import { useReferenceLists } from "@/lib/api/hse";

export type RefList = Schemas["ReferenceList"];
export type RefItem = Schemas["ReferenceItemRead"];

/**
 * Seeded reference lists (§3.11) with EN/AR labels from the API, so HSE Manager label edits
 * show everywhere. Falls back to the code while loading.
 */
export function useRefLists() {
  const q = useReferenceLists();
  const locale = useLocale();
  const byList = useMemo(() => {
    const m = new Map<string, RefItem[]>();
    for (const l of q.data?.lists ?? []) m.set(l.name, [...l.items].sort((a, b) => a.sort_order - b.sort_order));
    return m;
  }, [q.data]);
  const label = useCallback(
    (list: RefList, code: string | number | null | undefined): string => {
      if (code === null || code === undefined || code === "") return "—";
      const item = byList.get(list)?.find((i) => i.code === String(code));
      if (!item) return String(code);
      return locale === "ar" && item.label_ar ? item.label_ar : item.label_en;
    },
    [byList, locale],
  );
  const items = useCallback((list: RefList): RefItem[] => byList.get(list) ?? [], [byList]);
  const options = useCallback(
    (list: RefList) => (byList.get(list) ?? []).map((i) => ({ value: i.code, label: locale === "ar" && i.label_ar ? i.label_ar : i.label_en, group: i.group ?? null })),
    [byList, locale],
  );
  return { label, items, options, isLoading: q.isLoading, query: q };
}
