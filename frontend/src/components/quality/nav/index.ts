import { navQ0 } from "./q0";
import { navQ1 } from "./q1";
import { navQ2 } from "./q2";
import { navQ3 } from "./q3";
import { navQ4 } from "./q4";
import type { QualityNavItem, QualityProfile } from "./types";

export type { QualityNavItem, QualityProfile };

/** Every part's sidebar items, in order (spec 8-quality §3.2 "Frontend nav"). */
export const QUALITY_NAV: QualityNavItem[] = [...navQ0, ...navQ1, ...navQ2, ...navQ3, ...navQ4].sort((a, b) => a.order - b.order);
