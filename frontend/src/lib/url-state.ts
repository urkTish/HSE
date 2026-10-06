"use client";
import { useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";
import { usePathname, useRouter } from "@/i18n/navigation";

export type ParamValue = string | number | boolean | string[] | null | undefined;

/**
 * List filters and dashboard filters live in the URL so views can be shared and
 * dashboard drill-down links (action panel `link.query`) open pre-filtered lists.
 */
export function useSearchState() {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const get = useCallback((key: string): string | null => sp.get(key), [sp]);
  const getAll = useCallback((key: string): string[] => sp.getAll(key).filter(Boolean), [sp]);
  const getBool = useCallback(
    (key: string): boolean | undefined => {
      const v = sp.get(key);
      if (v === null || v === "") return undefined;
      return v === "true" || v === "1";
    },
    [sp],
  );
  const getInt = useCallback(
    (key: string, fallback?: number): number | undefined => {
      const v = sp.get(key);
      if (v === null || v === "" || Number.isNaN(Number(v))) return fallback;
      return Number(v);
    },
    [sp],
  );

  const set = useCallback(
    (updates: Record<string, ParamValue>, opts: { resetPage?: boolean; push?: boolean } = {}) => {
      const next = new URLSearchParams(sp.toString());
      for (const [k, v] of Object.entries(updates)) {
        next.delete(k);
        if (v === null || v === undefined || v === "" || (Array.isArray(v) && v.length === 0)) continue;
        if (Array.isArray(v)) v.forEach((x) => next.append(k, x));
        else next.set(k, String(v));
      }
      if (opts.resetPage !== false && !("page" in updates)) next.delete("page");
      const query = Object.fromEntries(
        Array.from(new Set(next.keys())).map((k) => {
          const all = next.getAll(k);
          return [k, all.length > 1 ? all : all[0]];
        }),
      );
      const nav = opts.push ? router.push : router.replace;
      nav({ pathname, query }, { scroll: false });
    },
    [sp, router, pathname],
  );

  const keys = useMemo(() => Array.from(new Set(sp.keys())), [sp]);
  return { sp, get, getAll, getBool, getInt, set, keys };
}

/** Build a query string (repeat keys for arrays) for links. */
export function toQueryString(query: Record<string, ParamValue>): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === null || v === undefined || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => qs.append(k, x));
    else qs.set(k, String(v));
  }
  const s = qs.toString();
  return s ? `?${s}` : "";
}
