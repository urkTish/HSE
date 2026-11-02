"use client";
import { useTranslations } from "next-intl";
import type { ComponentType, ReactNode, SVGProps } from "react";
import { Badge } from "@/components/ui/badge";
import { useMeData } from "@/components/shell/me-context";
import { useQAwaiting, useQSettings } from "@/lib/api/quality/q0";
import { can } from "@/lib/permissions";
import { QUALITY_NAV } from "./index";

export interface QualityNavLink {
  href: string;
  label: string;
  Icon: ComponentType<SVGProps<SVGSVGElement>>;
  exact?: boolean;
  testId: string;
  badge?: ReactNode;
}

/**
 * The sidebar group "Quality" (Q-NAV-01): every part's items the user may open on the current
 * project, for the active sector profile. Before the profile is chosen only Home and Settings show.
 */
export function useQualityNavItems(pid: string | null | undefined): QualityNavLink[] {
  const t = useTranslations("quality");
  const me = useMeData();
  const id = pid ?? "";
  const allowed = QUALITY_NAV.filter((i) => Boolean(pid) && i.capabilities.some((c) => can(me, c, pid)));
  const enabled = allowed.length > 0;
  const settings = useQSettings(id, { enabled });
  const profile = settings.data?.sector_profile ?? null;
  const awaiting = useQAwaiting(id, { enabled: enabled && Boolean(profile) });
  if (!enabled || !settings.data) return [];
  const count = awaiting.data?.items.length ?? 0;
  return allowed
    .filter((i) => (profile ? i.profiles.includes(profile) : i.href === "/quality" || i.href === "/quality/settings"))
    .map((i) => ({
      href: i.href,
      label: t(i.labelKey as never),
      Icon: i.Icon,
      exact: i.href === "/quality",
      testId: i.testId,
      badge: i.badge === "awaiting" && count ? <Badge tone="warning" className="ltr" data-testid="nav-q-awaiting-count">{count}</Badge> : undefined,
    }));
}
