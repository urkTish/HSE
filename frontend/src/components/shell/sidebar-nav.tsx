"use client";
import {
  Bot,
  Building2,
  CalendarCheck,
  ClipboardCheck,
  ClipboardList,
  Eye,
  FileText,
  Gauge,
  ListChecks,
  ListTree,
  ShieldAlert,
  SlidersHorizontal,
  Timer,
  HardHat,
  Home,
  LayoutGrid,
  MapPinned,
  Network,
  ScrollText,
  Settings,
  UserRound,
  Users,
} from "lucide-react";
import type { ComponentType, SVGProps } from "react";
import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { cn } from "@/lib/utils";
import { can, type Capability } from "@/lib/permissions";
import { useCurrentProject } from "@/lib/current-project";
import { useMeData } from "@/components/shell/me-context";

interface Item {
  href: string;
  label: string;
  Icon: ComponentType<SVGProps<SVGSVGElement>>;
  exact?: boolean;
  testId: string;
}

function NavLink({ item, onNavigate }: { item: Item; onNavigate?: () => void }) {
  const pathname = usePathname();
  const active = item.exact ? pathname === item.href : pathname === item.href || pathname.startsWith(`${item.href}/`);
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      data-testid={item.testId}
      className={cn(
        "relative flex min-h-touch items-center gap-3 rounded-md px-3 text-sm text-sidebar-foreground/85 transition-colors hover:bg-sidebar-active hover:text-sidebar-foreground",
        "focus-visible:outline-sidebar-indicator",
        active &&
          "bg-sidebar-active font-semibold text-sidebar-foreground before:absolute before:inset-y-2 before:start-0 before:w-1 before:rounded-full before:bg-sidebar-indicator",
      )}
    >
      {/* Icons are not directional, so they are not mirrored in RTL. */}
      <item.Icon aria-hidden className={cn("size-5 shrink-0", active ? "text-sidebar-indicator" : "text-sidebar-muted")} />
      <span className="truncate">{item.label}</span>
    </Link>
  );
}

export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const t = useTranslations("nav");
  const me = useMeData();
  const { project } = useCurrentProject();
  const g = (c: Capability, pid?: string | null) => can(me, c, pid);

  const main: Item[] = [
    { href: "/", label: g("dashboard.view") ? t("dashboard") : t("home"), Icon: g("dashboard.view") ? Gauge : Home, exact: true, testId: "nav-home" },
    ...(g("project.view") ? [{ href: "/projects", label: t("projects"), Icon: Building2, exact: true, testId: "nav-projects" }] : []),
    ...(g("contractor.view") ? [{ href: "/contractors", label: t("contractors"), Icon: HardHat, testId: "nav-contractors" }] : []),
    ...(g("user.view_directory") ? [{ href: "/users", label: t("users"), Icon: Users, testId: "nav-users" }] : []),
    ...(g("audit_log.read") ? [{ href: "/audit-log", label: t("auditLog"), Icon: ScrollText, testId: "nav-audit" }] : []),
    ...(me.is_hse_manager ? [{ href: "/ai-logs", label: t("aiLogs"), Icon: Bot, testId: "nav-ai-logs" }] : []),
    ...(g("hse_settings.edit") ? [{ href: "/reference-lists", label: t("referenceLists"), Icon: ListTree, testId: "nav-reference-lists" }] : []),
  ];
  const pid = project?.id;
  const projectItems: Item[] = pid
    ? [
        { href: `/projects/${pid}`, label: t("overview"), Icon: LayoutGrid, exact: true, testId: "nav-project-overview" },
        ...(g("site_zone.view", pid)
          ? [
              { href: `/projects/${pid}/sites`, label: t("sites"), Icon: MapPinned, testId: "nav-sites" },
              { href: `/projects/${pid}/zones`, label: t("zones"), Icon: ClipboardList, testId: "nav-zones" },
            ]
          : []),
        ...(g("contractor.view", pid)
          ? [{ href: `/projects/${pid}/engagements`, label: t("engagements"), Icon: Network, testId: "nav-engagements" }]
          : []),
        ...(g("settings.view", pid)
          ? [{ href: `/projects/${pid}/settings`, label: t("settings"), Icon: Settings, testId: "nav-settings" }]
          : []),
      ]
    : [];

  const dash = pid ? g("dashboard.view", pid) : false;
  const hseItems: Item[] = pid
    ? [
        ...(g("workforce.view", pid) ? [{ href: "/workforce", label: t("workforce"), Icon: Timer, testId: "nav-workforce" }] : []),
        ...(g("incident.view", pid) ? [{ href: "/incidents", label: t("incidents"), Icon: ShieldAlert, testId: "nav-incidents" }] : []),
        ...(g("observation.create", pid) || dash ? [{ href: "/observations", label: t("observations"), Icon: Eye, testId: "nav-observations" }] : []),
        ...(g("inspection.record", pid) || g("inspection.plan_manage", pid) || dash
          ? [{ href: "/inspections", label: t("inspections"), Icon: ClipboardCheck, testId: "nav-inspections" }]
          : []),
        ...(g("ca.create", pid) || g("ca.update_own", pid) || dash ? [{ href: "/actions", label: t("actions"), Icon: ListChecks, testId: "nav-actions" }] : []),
        ...(dash ? [{ href: "/meetings", label: t("meetings"), Icon: CalendarCheck, testId: "nav-meetings" }] : []),
        ...(g("monthly_report.view", pid) || g("monthly_report.generate", pid)
          ? [{ href: "/reports", label: t("reports"), Icon: FileText, testId: "nav-reports" }]
          : []),
        ...(g("settings.view", pid) ? [{ href: "/hse-settings", label: t("hseSettings"), Icon: SlidersHorizontal, testId: "nav-hse-settings" }] : []),
      ]
    : [];

  return (
    <nav aria-label={t("main")} className="flex flex-1 flex-col gap-5 p-3">
      <ul className="flex flex-col gap-1">
        {main.map((i) => (
          <li key={i.href}>
            <NavLink item={i} onNavigate={onNavigate} />
          </li>
        ))}
      </ul>
      {project ? (
        <div>
          <p className="flex items-center gap-1.5 border-t border-white/10 px-3 pt-4 pb-2 text-xs font-medium text-sidebar-muted">
            <span>{t("currentProject")}</span>
            <span aria-hidden>·</span>
            <span className="ltr rounded bg-sidebar-active px-1.5 py-0.5 font-semibold text-sidebar-foreground">{project.code}</span>
          </p>
          {hseItems.length > 0 ? (
            <>
              <p className="px-3 pt-1 pb-1 text-xs font-medium text-sidebar-muted">{t("hseData")}</p>
              <ul className="mb-3 flex flex-col gap-1" data-testid="nav-hse">
                {hseItems.map((i) => (
                  <li key={i.href}>
                    <NavLink item={i} onNavigate={onNavigate} />
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          <ul className="flex flex-col gap-1">
            {projectItems.map((i) => (
              <li key={i.href}>
                <NavLink item={i} onNavigate={onNavigate} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <ul className="mt-auto flex flex-col gap-1 border-t border-white/10 pt-3">
        <li>
          <NavLink item={{ href: "/profile", label: t("profile"), Icon: UserRound, testId: "nav-profile" }} onNavigate={onNavigate} />
        </li>
      </ul>
    </nav>
  );
}
