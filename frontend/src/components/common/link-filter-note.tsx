"use client";
import { Filter, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { useSearchState } from "@/lib/url-state";

/** Shown when a list was opened from a dashboard link with filters that have no visible control. */
export function LinkFilterNote({ keys }: { keys: string[] }) {
  const t = useTranslations("common");
  const s = useSearchState();
  const active = keys.filter((k) => s.get(k) !== null);
  if (active.length === 0) return null;
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-info/40 bg-info-bg px-3 py-2 text-sm" data-testid="link-filter-note">
      <Filter aria-hidden className="size-4 text-info" />
      <span className="font-medium">{t("filteredFromLink")}</span>
      <span className="text-xs text-muted-foreground ltr">{active.map((k) => `${k}=${s.getAll(k).join(",")}`).join(" · ")}</span>
      <Button variant="ghost" size="sm" className="ms-auto" onClick={() => s.set(Object.fromEntries(active.map((k) => [k, null])))}>
        <X aria-hidden />
        {t("clearLinkFilters")}
      </Button>
    </div>
  );
}
