"use client";
import { Dashboard } from "@/components/dashboard/dashboard";
import { HomePlaceholder } from "@/components/home/home-placeholder";
import { useMeData } from "@/components/shell/me-context";
import { can } from "@/lib/permissions";

/** Users with capability 38 land on the KPI dashboard; others keep the Phase 0 home. */
export function HomePage() {
  const me = useMeData();
  return can(me, "dashboard.view") ? <Dashboard /> : <HomePlaceholder />;
}
