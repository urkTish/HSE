"use client";
import { Lock, ShieldAlert } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import type { Schemas } from "@/lib/api/client";

type S = Schemas;

/** Hard stop (blocks in every stage, HK4-3) vs transition warning (HK4-4) — visually distinct everywhere. */
export function HookSeverity({ hardStop, warn }: { hardStop?: boolean; warn?: boolean }) {
  const t = useTranslations("cert");
  if (hardStop)
    return (
      <Badge tone="danger" data-testid="hard-stop">
        <Lock aria-hidden />
        {t("hardStop")}
      </Badge>
    );
  if (warn)
    return (
      <Badge tone="warning" data-testid="transition-warning">
        <ShieldAlert aria-hidden />
        {t("transitionWarning")}
      </Badge>
    );
  return null;
}

export function HookConditions({ items }: { items: S["HookCondition"][] | null | undefined }) {
  const t = useTranslations("cert");
  const locale = useLocale();
  if (!items?.length) return null;
  return (
    <div className="rounded-md border border-warning/40 bg-warning-bg/40 p-2 text-sm" data-testid="hook-conditions">
      <p className="text-xs font-semibold">{t("conditions")}</p>
      <ul className="mt-1 list-disc ps-5">
        {items.map((c, i) => (
          <li key={`${c.code}-${i}`} data-code={c.code}>
            {locale === "ar" ? c.text_ar : c.text_en}
            {c.value ? <bdi className="ltr ms-1 font-medium rtl:ms-0 rtl:me-1">{c.value}</bdi> : null}
            {c.source_ref ? (
              <span className="ms-1 text-xs text-muted-foreground">
                (<bdi className="ltr">{c.source_ref}</bdi>)
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

