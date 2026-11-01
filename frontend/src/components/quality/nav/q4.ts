import { BarChart3, ClipboardList, FileCheck2, FileStack, Gauge, LineChart, Send, Star, Users } from "lucide-react";
import type { QualityNavItem } from "./types";

const B: QualityNavItem["profiles"] = ["construction", "logistics"];

/** Sidebar items of package Q4 (spec 8-quality §E.11); shared by both profiles (Q-NAV-01). */
export const navQ4: QualityNavItem[] = [
  { href: "/quality/kpis", labelKey: "q4.nav.kpis", Icon: Gauge, capabilities: ["quality.view"], profiles: B, testId: "nav-q4-kpis", order: 400 },
  { href: "/quality/documents", labelKey: "q4.nav.documents", Icon: FileCheck2, capabilities: ["quality.view", "document.author", "document.approve"], profiles: B, testId: "nav-q4-documents", order: 401 },
  { href: "/quality/transmittals", labelKey: "q4.nav.transmittals", Icon: Send, capabilities: ["document.author"], profiles: B, testId: "nav-q4-transmittals", order: 402 },
  { href: "/quality/audits", labelKey: "q4.nav.audits", Icon: ClipboardList, capabilities: ["quality.view", "quality_audit.conduct", "quality_audit.issue"], profiles: B, testId: "nav-q4-audits", order: 403 },
  { href: "/quality/audit-programme", labelKey: "q4.nav.programme", Icon: FileStack, capabilities: ["quality_audit.conduct"], profiles: B, testId: "nav-q4-programme", order: 404 },
  { href: "/quality/management-reviews", labelKey: "q4.nav.mrv", Icon: Users, capabilities: ["quality_audit.conduct", "quality_audit.issue"], profiles: B, testId: "nav-q4-mrv", order: 405 },
  { href: "/quality/supplier-scores", labelKey: "q4.nav.suppliers", Icon: Star, capabilities: ["supplier.manage", "supplier.approve"], profiles: B, testId: "nav-q4-suppliers", order: 406 },
  { href: "/quality/spc", labelKey: "q4.nav.spc", Icon: LineChart, capabilities: ["quality.view"], profiles: B, testId: "nav-q4-spc", order: 407 },
  { href: "/quality/reports", labelKey: "q4.nav.reports", Icon: BarChart3, capabilities: ["quality_report_pack.manage"], profiles: B, testId: "nav-q4-reports", order: 408 },
];
