"use client";
import { useLocale, useTranslations } from "next-intl";
import type { Schemas } from "@/lib/api/client";

/** Privacy notice in the display language, with the other language one click away. */
export function PrivacyText({ notice }: { notice: Schemas["PrivacyNotice"] }) {
  const locale = useLocale();
  const t = useTranslations("auth.privacy");
  const primary = locale === "ar" ? notice.text_ar : notice.text_en;
  const other = locale === "ar" ? notice.text_en : notice.text_ar;
  const otherLang = locale === "ar" ? "en" : "ar";
  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-muted-foreground">{t("version", { version: notice.version })}</p>
      <div className="max-h-72 overflow-y-auto whitespace-pre-line rounded-md border bg-muted/40 p-3 text-sm" data-testid="privacy-text" tabIndex={0}>
        {primary}
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer text-primary">{t("otherLanguage")}</summary>
        <div lang={otherLang} dir={otherLang === "ar" ? "rtl" : "ltr"} className="mt-2 max-h-72 overflow-y-auto whitespace-pre-line rounded-md border bg-muted/40 p-3">
          {other}
        </div>
      </details>
    </div>
  );
}
