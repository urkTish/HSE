"use client";
import { useLocale, useTranslations } from "next-intl";
import { useCallback } from "react";
import { ApiError } from "@/lib/api/client";

/** Bilingual entity name in the display language, falling back to English (rule 44). */
export function useLocalizedName() {
  const locale = useLocale();
  return useCallback(
    (en: string | null | undefined, ar: string | null | undefined): string => {
      if (locale === "ar" && ar && ar.trim()) return ar;
      return en ?? ar ?? "";
    },
    [locale],
  );
}

const SERVER_TEXT_FIRST = new Set<string>(["LICENCE_READ_ONLY", "LICENCE_LIMIT_REACHED", "LICENCE_KEY_INVALID"]);

/** Map a stable server error code to translated text (rule 48). */
export function useErrorMessage() {
  const t = useTranslations("errors");
  const locale = useLocale();
  return useCallback(
    (err: unknown): string => {
      if (err instanceof ApiError) {
        // Licence errors (D-296): the server text names the end date, the limit and the counts.
        if (SERVER_TEXT_FIRST.has(err.code) && (locale === "ar" ? err.messageAr : err.message)) {
          return (locale === "ar" ? err.messageAr : err.message) ?? err.message;
        }
        const key = `code.${err.code}` as const;
        if (t.has(key)) return t(key);
        if (locale === "ar" && err.messageAr) return err.messageAr;
        return err.message;
      }
      return t("code.UNKNOWN");
    },
    [t, locale],
  );
}

/** Field-level server validation messages: English text as sent, generic translated text in Arabic. */
export function useFieldErrorTranslator() {
  const t = useTranslations("errors");
  const locale = useLocale();
  // The API sends both texts (FieldError.msg / msg_ar, v0.3.1); the generic Arabic message is only a fallback.
  return useCallback(
    (_type: string, msg: string, msgAr?: string | null) =>
      locale === "ar" ? msgAr || t("fieldInvalid") : msg,
    [t, locale],
  );
}

/**
 * Join display items with the separator of the page language ("، " in Arabic, ", " otherwise).
 * Only used on data rendered after client-side fetches, so reading <html lang> is safe.
 */
export function joinList(items: readonly string[]): string {
  const ar =
    typeof document !== "undefined" && document.documentElement.lang === "ar";
  return items.join(ar ? "، " : ", ");
}
