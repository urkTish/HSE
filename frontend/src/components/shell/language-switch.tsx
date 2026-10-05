"use client";
import { Languages } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { usePathname, useRouter } from "@/i18n/navigation";
import { api, unwrap } from "@/lib/api/client";
import { keys } from "@/lib/api/queries";

/** Switches /en ↔ /ar keeping the current path and query; when signed in also saves the preference. */
export function LanguageSwitch({ persist = false }: { persist?: boolean }) {
  const locale = useLocale();
  const t = useTranslations("shell");
  const pathname = usePathname();
  const router = useRouter();
  const qc = useQueryClient();
  const target = locale === "ar" ? "en" : "ar";

  function onClick() {
    const query = Object.fromEntries(new URLSearchParams(window.location.search).entries());
    router.replace({ pathname, query }, { locale: target });
    if (persist) {
      unwrap(api.PATCH("/api/v1/auth/me", { body: { preferred_language: target } }))
        .then((me) => qc.setQueryData(keys.me, me))
        .catch(() => undefined);
    }
  }

  return (
    <Button variant="ghost" size="sm" onClick={onClick} aria-label={t("switchLanguage")} data-testid="language-switch" lang={target}>
      <Languages aria-hidden />
      {target === "ar" ? t("switchToArabic") : t("switchToEnglish")}
    </Button>
  );
}
