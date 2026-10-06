"use client";
import { useLocale, useTranslations } from "next-intl";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import type { Schemas } from "@/lib/api/client";

/** Non-blocking warnings returned with a successful write (P1-8 possible ID, CA-6 PPE-only, W03…). */
export function ApiWarnings({ warnings, className }: { warnings: Schemas["ApiWarning"][] | null | undefined; className?: string }) {
  const t = useTranslations("common");
  const locale = useLocale();
  if (!warnings || warnings.length === 0) return null;
  return (
    <Alert tone="warning" className={className} data-testid="api-warnings">
      <p className="font-medium">{t("warningsTitle")}</p>
      <ul className="mt-1 list-disc ps-5">
        {warnings.map((w, i) => (
          <li key={`${w.code}-${i}`} data-code={w.code}>
            {w.code === "POSSIBLE_ID_NUMBER" ? t("possibleId") : locale === "ar" && w.message_ar ? w.message_ar : w.message}
          </li>
        ))}
      </ul>
    </Alert>
  );
}

/** Toast each write warning so it stays visible after navigating to the saved record. */
export function useWarningToasts() {
  const t = useTranslations("common");
  const locale = useLocale();
  return (warnings: Schemas["ApiWarning"][] | null | undefined) => {
    for (const w of warnings ?? []) {
      const text = w.code === "POSSIBLE_ID_NUMBER" ? t("possibleId") : locale === "ar" && w.message_ar ? w.message_ar : w.message;
      toast.warning(text, { duration: 10_000 });
    }
  };
}

const ID_PATTERN = /(^|\D)[12]\d{9}(?!\d)/;

/** P1-8: warn (not block) when free text looks like it holds a 10-digit Saudi ID. */
export function looksLikeId(text: string | null | undefined): boolean {
  return Boolean(text && ID_PATTERN.test(text));
}

export function PossibleIdHint({ text }: { text: string | null | undefined }) {
  const t = useTranslations("common");
  if (!looksLikeId(text)) return null;
  return (
    <p role="status" className="text-xs font-medium text-warning" data-testid="possible-id-hint">
      {t("possibleId")}
    </p>
  );
}
