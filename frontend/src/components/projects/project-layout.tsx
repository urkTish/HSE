"use client";
import { useTranslations } from "next-intl";
import { useEffect, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Alert } from "@/components/ui/alert";
import { Breadcrumbs } from "@/components/common/breadcrumbs";
import { StatusBadge } from "@/components/common/status-badge";
import { ErrorState, LoadingState } from "@/components/common/states";
import { useMeData } from "@/components/shell/me-context";
import { Link, usePathname } from "@/i18n/navigation";
import { useProject } from "@/lib/api/queries";
import { useCurrentProject } from "@/lib/current-project";
import { useLocalizedName } from "@/lib/i18n-helpers";
import { can, isReadOnly } from "@/lib/permissions";
import { cn } from "@/lib/utils";

export function ProjectLayout({ projectId, children }: { projectId: string; children: ReactNode }) {
  const t = useTranslations("project");
  const tn = useTranslations("nav");
  const tc = useTranslations("common");
  const me = useMeData();
  const name = useLocalizedName();
  const pathname = usePathname();
  const q = useProject(projectId);
  const { setProjectId, projectId: current } = useCurrentProject();

  useEffect(() => {
    if (q.data && current !== q.data.id) setProjectId(q.data.id);
  }, [q.data, current, setProjectId]);

  if (q.isLoading) return <LoadingState />;
  if (q.isError || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const p = q.data;
  const base = `/projects/${p.id}`;
  const tabs = [
    { href: base, label: tn("overview"), exact: true, show: true },
    { href: `${base}/sites`, label: tn("sites"), show: can(me, "site_zone.view", p.id) },
    { href: `${base}/zones`, label: tn("zones"), show: can(me, "site_zone.view", p.id) },
    { href: `${base}/engagements`, label: tn("engagements"), show: can(me, "contractor.view", p.id) },
    { href: `${base}/settings`, label: tn("settings"), show: can(me, "settings.view", p.id) },
  ].filter((x) => x.show);

  return (
    <div>
      <Breadcrumbs items={[{ label: tn("projects"), href: "/projects" }, { label: p.code, href: base }]} />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <h1 className="text-2xl font-semibold tracking-tight" data-testid="project-title">
          {name(p.name_en, p.name_ar)}
        </h1>
        <Badge tone="neutral" className="ltr">
          {p.code}
        </Badge>
        <StatusBadge status={p.status} label={t(`status.${p.status}`)} />
        {isReadOnly(me, p.id) ? (
          <Badge tone="warning" title={tc("readOnlyHint")} data-testid="read-only-badge">
            {tc("readOnly")}
          </Badge>
        ) : null}
      </div>
      {p.status === "closed" ? (
        <Alert tone="warning" className="mb-4" data-testid="closed-banner">
          {t("closedBanner")}
        </Alert>
      ) : null}
      <nav aria-label={tn("currentProject")} className="mb-6 overflow-x-auto border-b">
        <ul className="flex gap-1">
          {tabs.map((tab) => {
            const active = tab.exact ? pathname === tab.href : pathname.startsWith(tab.href);
            return (
              <li key={tab.href}>
                <Link
                  href={tab.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "inline-flex min-h-touch items-center border-b-2 px-3 text-sm whitespace-nowrap",
                    active ? "border-primary font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
                  )}
                >
                  {tab.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      {children}
    </div>
  );
}
