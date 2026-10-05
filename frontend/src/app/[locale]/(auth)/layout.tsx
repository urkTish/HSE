import type { ReactNode } from "react";
import { ShieldCheck } from "lucide-react";
import { getTranslations } from "next-intl/server";
import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { LanguageSwitch } from "@/components/shell/language-switch";
import { ThemeToggle } from "@/components/shell/theme-toggle";

export default async function AuthLayout({ children, params }: { children: ReactNode } & LocaleParams) {
  await initRequestLocale(params);
  const t = await getTranslations("meta");
  return (
    <div className="flex min-h-dvh flex-col bg-background">
      {/* Brand band: anchors the page in the product colours without competing with the form. */}
      <div aria-hidden className="pointer-events-none fixed inset-x-0 top-0 -z-0 h-64 bg-sidebar sm:h-72" />
      <header className="relative flex items-center justify-between gap-2 px-4 py-3 sm:px-8">
        <div className="flex items-center gap-2.5 font-semibold text-sidebar-foreground">
          <span className="flex size-9 items-center justify-center rounded-lg bg-sidebar-active">
            <ShieldCheck aria-hidden className="size-5 text-sidebar-indicator" />
          </span>
          <span>{t("appName")}</span>
        </div>
        <div className="flex items-center gap-1 rounded-lg bg-surface/95 p-0.5 text-foreground shadow-xs">
          <LanguageSwitch />
          <ThemeToggle />
        </div>
      </header>
      <main id="main" className="relative flex flex-1 items-start justify-center px-4 pt-6 pb-10 sm:pt-12">
        <div className="w-full max-w-md [&>div:first-child]:shadow-lg">{children}</div>
      </main>
      <footer className="relative px-4 pb-6 text-center text-xs text-muted-foreground">{t("tagline")}</footer>
    </div>
  );
}
