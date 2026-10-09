"use client";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Dangerous record actions (void, revoke, retire, blacklist, ban…) at the end of a page, away from the
 * everyday buttons and the thumb: the 6c muster / 6d audit pattern, shared by the older modules.
 */
export function RecordActions({ children, label, testId, className }: { children: ReactNode; label?: string; testId?: string; className?: string }) {
  const t = useTranslations("consistency");
  return (
    <div role="group" aria-label={label ?? t("recordActions")} className={cn("mt-6 flex flex-wrap items-center justify-between gap-2 border-t pt-4", className)} data-testid={testId}>
      <span className="text-xs text-muted-foreground">{label ?? t("recordActions")}</span>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}
