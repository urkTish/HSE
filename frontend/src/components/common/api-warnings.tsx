"use client";
import { useLocale, useTranslations } from "next-intl";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import type { Schemas } from "@/lib/api/client";

/** Non-blocking warnings returned with a successful write (P1-8 possible ID, CA-6 PPE-only, W03…). */
export function ApiWarnings({ warnings, className }: { warnings: Schemas["ApiWarning"][] | null | undefined; className?: string }) {
  const t = useTranslations("common");
  const text = useWarningText();
  if (!warnings || warnings.length === 0) return null;
  return (
    <Alert tone="warning" className={className} data-testid="api-warnings">
      <p className="font-medium">{t("warningsTitle")}</p>
      <ul className="mt-1 list-disc ps-5">
        {warnings.map((w, i) => (
          <li key={`${w.code}-${i}`} data-code={w.code}>
            {text(w)}
          </li>
        ))}
      </ul>
    </Alert>
  );
}

/** Toast each write warning so it stays visible after navigating to the saved record. */
export function useWarningToasts() {
  const text = useWarningText();
  return (warnings: Schemas["ApiWarning"][] | null | undefined) => {
    for (const w of warnings ?? []) {
      toast.warning(text(w), { duration: 10_000, className: `api-warning-${w.code}` });
    }
  };
}

/** A write warning in the page language: a local string when one exists (apiWarning.<CODE>), else the API text. */
function useWarningText() {
  const t = useTranslations("common");
  const tw = useTranslations("apiWarning");
  const locale = useLocale();
  return (w: Schemas["ApiWarning"]): string => {
    if (w.code === "POSSIBLE_ID_NUMBER") return t("possibleId");
    if (tw.has(w.code as "COMMUTING_PURPOSE_MISMATCH")) return tw(w.code as "COMMUTING_PURPOSE_MISMATCH");
    return locale === "ar" && w.message_ar ? w.message_ar : w.message;
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
