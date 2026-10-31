import { ClipboardCheck, FileStack, ListTodo, MapPinned, Route } from "lucide-react";
import type { QualityNavItem } from "./types";

const C: QualityNavItem["profiles"] = ["construction"];

/** Sidebar items of package Q1 construction: ITPs, inspection requests, punch list, floor plans and handover
 * dossiers (spec 8-quality §B.8). Construction profile only: a logistics project (RUH-CCH) hides them (Q-NAV-01). */
export const navQ1: QualityNavItem[] = [
  { href: "/quality/itps", labelKey: "q1.nav.itps", Icon: Route, capabilities: ["quality.view", "itp.author"], profiles: C, testId: "nav-q-itps", order: 100 },
  { href: "/quality/inspection-requests", labelKey: "q1.nav.irs", Icon: ClipboardCheck, capabilities: ["quality.view", "ir.submit", "ir.inspect"], profiles: C, testId: "nav-q-irs", order: 101 },
  { href: "/quality/punch", labelKey: "q1.nav.punch", Icon: ListTodo, capabilities: ["quality.view", "punch.record", "punch.verify"], profiles: C, testId: "nav-q-punch", order: 102 },
  { href: "/quality/floor-plans", labelKey: "q1.nav.plans", Icon: MapPinned, capabilities: ["quality.view", "punch.record"], profiles: C, testId: "nav-q-plans", order: 103 },
  { href: "/quality/dossiers", labelKey: "q1.nav.dossiers", Icon: FileStack, capabilities: ["quality.view", "dossier.compile", "dossier.accept"], profiles: C, testId: "nav-q-dossiers", order: 104 },
];
