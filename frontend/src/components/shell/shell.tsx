"use client";
import { Menu, ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";
import { Dialog as D } from "radix-ui";
import { Button } from "@/components/ui/button";
import { Link } from "@/i18n/navigation";
import { SidebarNav } from "@/components/shell/sidebar-nav";
import { ProjectSwitcher } from "@/components/shell/project-switcher";
import { LanguageSwitch } from "@/components/shell/language-switch";
import { NotificationsBell } from "@/components/shell/notifications-bell";
import { UserMenu } from "@/components/shell/user-menu";

function Brand() {
  const t = useTranslations("meta");
  return (
    <Link href="/" className="flex items-center gap-2 px-4 py-4 font-semibold text-sidebar-foreground">
      <ShieldCheck aria-hidden className="size-6" />
      <span>{t("appName")}</span>
    </Link>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const t = useTranslations("common");
  const [mobileOpen, setMobileOpen] = useState(false);
  return (
    <div className="flex min-h-dvh">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:start-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:p-2">
        {t("skipToContent")}
      </a>
      <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 flex-col overflow-y-auto bg-sidebar lg:flex" data-testid="sidebar">
        <Brand />
        <SidebarNav />
      </aside>
      <D.Root open={mobileOpen} onOpenChange={setMobileOpen}>
        <D.Portal>
          <D.Overlay className="fixed inset-0 z-40 bg-black/40 lg:hidden" />
          <D.Content className="fixed inset-y-0 start-0 z-50 w-72 overflow-y-auto bg-sidebar lg:hidden" aria-describedby={undefined}>
            <D.Title className="sr-only">{t("openMenu")}</D.Title>
            <Brand />
            <SidebarNav onNavigate={() => setMobileOpen(false)} />
          </D.Content>
        </D.Portal>
      </D.Root>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b bg-surface/95 px-3 backdrop-blur sm:px-4" data-testid="topbar">
          <Button variant="ghost" size="icon" className="lg:hidden" aria-label={t("openMenu")} onClick={() => setMobileOpen(true)}>
            <Menu aria-hidden />
          </Button>
          <ProjectSwitcher />
          <div className="flex-1" />
          <LanguageSwitch persist />
          <NotificationsBell />
          <UserMenu />
        </header>
        <main id="main" tabIndex={-1} className="flex-1 p-4 sm:p-6 lg:p-8">
          <div className="mx-auto max-w-7xl">{children}</div>
        </main>
      </div>
    </div>
  );
}
