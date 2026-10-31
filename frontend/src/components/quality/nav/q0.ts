import { AlertOctagon, BadgeCheck, Boxes, Building2, ClipboardX, Gauge, Inbox, ListChecks, MessageSquareWarning, Network, ScanEye, SlidersHorizontal, Truck } from "lucide-react";
import type { QualityNavItem } from "./types";

const BOTH: QualityNavItem["profiles"] = ["construction", "logistics"];
const VIEW = ["quality.view", "ncr.raise", "quality.settings"] as QualityNavItem["capabilities"];

/** Q0 items (spec 8-quality Q-NAV-02). */
export const navQ0: QualityNavItem[] = [
  { href: "/quality", labelKey: "nav.home", Icon: Gauge, capabilities: VIEW, profiles: BOTH, testId: "nav-q-home", order: 0 },
  { href: "/quality/awaiting", labelKey: "nav.awaiting", Icon: Inbox, capabilities: ["quality.view", "ncr.approve"], profiles: BOTH, testId: "nav-q-awaiting", badge: "awaiting", order: 1 },
  { href: "/quality/ncrs", labelKey: "nav.ncrs", Icon: ClipboardX, capabilities: VIEW, profiles: BOTH, testId: "nav-q-ncrs", order: 10 },
  { href: "/quality/observations", labelKey: "nav.observations", Icon: ScanEye, capabilities: ["quality.view", "ncr.raise"], profiles: BOTH, testId: "nav-q-observations", order: 11 },
  { href: "/quality/alerts", labelKey: "nav.alerts", Icon: AlertOctagon, capabilities: ["quality.view", "quality.acknowledge"], profiles: BOTH, testId: "nav-q-alerts", order: 12 },
  { href: "/quality/complaints", labelKey: "nav.complaints", Icon: MessageSquareWarning, capabilities: ["quality.view", "complaint.manage"], profiles: BOTH, testId: "nav-q-complaints", order: 13 },
  { href: "/quality/suppliers", labelKey: "nav.suppliers", Icon: Truck, capabilities: ["quality.view", "supplier.manage"], profiles: BOTH, testId: "nav-q-suppliers", order: 80 },
  { href: "/quality/customers", labelKey: "nav.customers", Icon: Building2, capabilities: ["quality.view", "complaint.manage"], profiles: BOTH, testId: "nav-q-customers", order: 81 },
  { href: "/quality/systems", labelKey: "nav.systems", Icon: Network, capabilities: ["quality.view"], profiles: ["construction"], testId: "nav-q-systems", order: 82 },
  { href: "/quality/mte", labelKey: "nav.mte", Icon: Boxes, capabilities: ["quality.view", "mte.manage"], profiles: BOTH, testId: "nav-q-mte", order: 83 },
  { href: "/quality/criteria", labelKey: "nav.criteria", Icon: ListChecks, capabilities: ["quality.view", "quality.author"], profiles: BOTH, testId: "nav-q-criteria", order: 84 },
  { href: "/checklist-templates?kind=quality", labelKey: "nav.checklists", Icon: BadgeCheck, capabilities: ["quality.author", "quality.settings"], profiles: BOTH, testId: "nav-q-checklists", order: 85 },
  { href: "/quality/settings", labelKey: "nav.settings", Icon: SlidersHorizontal, capabilities: ["quality.settings"], profiles: BOTH, testId: "nav-q-settings", order: 99 },
];
