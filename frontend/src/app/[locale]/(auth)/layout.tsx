import type { ReactNode } from "react";
import { ShieldCheck } from "lucide-react";
import { getTranslations } from "next-intl/server";
import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { LanguageSwitch } from "@/components/shell/language-switch";

export default async function AuthLayout({ children, params }: { children: ReactNode } & LocaleParams) {
  await initRequestLocale(params);
  const t = await getTranslations("meta");
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex items-center justify-between px-4 py-3 sm:px-8">
        <div className="flex items-center gap-2 font-semibold">
          <ShieldCheck aria-hidden className="size-6 text-primary" />
          <span>{t("appName")}</span>
        </div>
        <LanguageSwitch />
      </header>
      <main id="main" className="flex flex-1 items-start justify-center px-4 py-8 sm:items-center">
        <div className="w-full max-w-md">{children}</div>
      </main>
    </div>
  );
}
