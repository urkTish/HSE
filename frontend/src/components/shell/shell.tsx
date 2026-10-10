"use client";
import { Menu, ShieldCheck, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { Suspense, useState, type ReactNode } from "react";
import { Dialog as D } from "radix-ui";
import { Button } from "@/components/ui/button";
import { Link } from "@/i18n/navigation";
import { SidebarNav } from "@/components/shell/sidebar-nav";
import { ProjectSwitcher } from "@/components/shell/project-switcher";
import { LanguageSwitch } from "@/components/shell/language-switch";
import { NotificationsBell } from "@/components/shell/notifications-bell";
import { ThemeToggle } from "@/components/shell/theme-toggle";
import { UserMenu } from "@/components/shell/user-menu";
import { FieldOfflineSync } from "@/components/field/offline";

function Brand({ onNavigate }: { onNavigate?: () => void }) {
  const t = useTranslations("meta");
  return (
    <Link
      href="/"
      onClick={onNavigate}
      className="flex min-h-touch items-center gap-2.5 rounded-md px-2 font-semibold leading-tight text-sidebar-foreground"
    >
      <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-sidebar-active shadow-[inset_0_1px_0_rgb(255_255_255/0.08)] ring-1 ring-sidebar-indicator/30">
        <ShieldCheck aria-hidden className="size-5 text-sidebar-indicator" />
      </span>
      <span className="tracking-[0.01em]">{t("appName")}</span>
    </Link>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const t = useTranslations("common");
  const [mobileOpen, setMobileOpen] = useState(false);
  return (
    <div className="flex min-h-dvh">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:start-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-surface focus:p-3 focus:shadow-lg"
      >
        {t("skipToContent")}
      </a>
      <FieldOfflineSync />
      <aside
        className="sticky top-0 hidden h-dvh w-(--sidebar-width) shrink-0 print:!hidden flex-col overflow-y-auto border-e border-sidebar-border bg-sidebar bg-[linear-gradient(180deg,rgb(255_255_255/0.025),transparent_40%)] lg:flex"
        data-testid="sidebar"
      >
        <div className="px-3 pt-3 pb-1">
          <Brand />
        </div>
        <SidebarNav />
      </aside>
      <D.Root open={mobileOpen} onOpenChange={setMobileOpen}>
        <D.Portal>
          <D.Overlay className="fixed inset-0 z-40 bg-overlay lg:hidden" />
          <D.Content
            className="fixed inset-y-0 start-0 z-50 flex w-[min(20rem,85vw)] flex-col overflow-y-auto bg-sidebar shadow-lg lg:hidden"
            aria-describedby={undefined}
            data-testid="mobile-nav"
          >
            <D.Title className="sr-only">{t("openMenu")}</D.Title>
            <div className="flex items-center justify-between gap-2 px-3 pt-3 pb-1">
              <Brand onNavigate={() => setMobileOpen(false)} />
              <D.Close
                className="inline-flex size-touch shrink-0 items-center justify-center rounded-md text-sidebar-foreground hover:bg-sidebar-active"
                aria-label={t("close")}
              >
                <X aria-hidden className="size-5" />
              </D.Close>
            </div>
            <SidebarNav onNavigate={() => setMobileOpen(false)} />
          </D.Content>
        </D.Portal>
      </D.Root>
      <div className="flex min-w-0 flex-1 flex-col">
        <header
          className="sticky top-0 z-30 flex flex-wrap print:!hidden items-center gap-x-1 gap-y-0 border-b border-border bg-surface/95 px-2 shadow-xs backdrop-blur supports-[backdrop-filter]:bg-surface/85 sm:flex-nowrap sm:gap-2 sm:px-4"
          data-testid="topbar"
        >
          <div className="flex h-(--topbar-h) items-center lg:hidden">
            <Button variant="ghost" size="icon" aria-label={t("openMenu")} onClick={() => setMobileOpen(true)} data-testid="open-menu">
              <Menu aria-hidden />
            </Button>
          </div>
          {/* Phones: the project switcher gets its own full-width row under the icons. */}
          <div className="order-last flex w-full min-w-0 pb-2 sm:order-none sm:w-auto sm:flex-1 sm:pb-0">
            <ProjectSwitcher />
          </div>
          <div className="flex h-(--topbar-h) flex-1 items-center justify-end gap-0.5 sm:flex-none sm:gap-1">
            <LanguageSwitch persist />
            <ThemeToggle />
            <NotificationsBell />
            <UserMenu />
          </div>
        </header>
        <main id="main" tabIndex={-1} className="flex-1 px-4 py-5 outline-none sm:px-6 sm:py-6 lg:px-8 lg:py-8">
          <div className="mx-auto max-w-7xl">
            <Suspense>{children}</Suspense>
          </div>
        </main>
      </div>
    </div>
  );
}
