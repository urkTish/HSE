import type { ComponentType, SVGProps } from "react";
import type { Capability } from "@/lib/permissions";

export type QualityProfile = "construction" | "logistics";

/**
 * One item of the sidebar group "Quality" (spec 8-quality Q-NAV-01). Each part lists its items in
 * `nav/q<n>.ts`; `labelKey` is a key under `quality.` in the part's message file.
 */
export interface QualityNavItem {
  href: string;
  labelKey: string;
  Icon: ComponentType<SVGProps<SVGSVGElement>>;
  /** Shown when the user holds any of these on the current project. */
  capabilities: Capability[];
  /** Profiles the item belongs to; items of the inactive profile are hidden (Q-NAV-01). */
  profiles: QualityProfile[];
  testId: string;
  /** Q0 only: the "Awaiting my sign-off" count. */
  badge?: "awaiting";
  /** Item order inside the group (Q0 uses 0–99, parts 100+). */
  order: number;
}
