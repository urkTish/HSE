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

/** Map a stable server error code to translated text (rule 48). */
export function useErrorMessage() {
  const t = useTranslations("errors");
  const locale = useLocale();
  return useCallback(
    (err: unknown): string => {
      if (err instanceof ApiError) {
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
