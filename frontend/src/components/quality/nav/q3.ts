import { Biohazard, Boxes, Bug, ClipboardCheck, FileUp, Lock, Map, PackageCheck, PackageX, RotateCcw, Snowflake, Thermometer, ThermometerSnowflake, Truck } from "lucide-react";
import type { QualityNavItem } from "./types";

const L: QualityNavItem["profiles"] = ["logistics"];

/** Sidebar items of package Q3 logistics (spec 8-quality §D.10); shown on logistics projects only (Q-NAV-01). */
export const navQ3: QualityNavItem[] = [
  { href: "/quality/receiving", labelKey: "logistics.nav.receiving", Icon: PackageCheck, capabilities: ["quality.view", "receiving.record"], profiles: L, testId: "nav-q3-receiving", order: 300 },
  { href: "/quality/storage", labelKey: "logistics.nav.storage", Icon: Snowflake, capabilities: ["quality.view", "storage.manage"], profiles: L, testId: "nav-q3-storage", order: 301 },
  { href: "/quality/readings", labelKey: "logistics.nav.readings", Icon: Thermometer, capabilities: ["reading.record"], profiles: L, testId: "nav-q3-readings", order: 302 },
  { href: "/quality/excursions", labelKey: "logistics.nav.excursions", Icon: ThermometerSnowflake, capabilities: ["quality.view", "excursion.assess"], profiles: L, testId: "nav-q3-excursions", order: 303 },
  { href: "/quality/holds", labelKey: "logistics.nav.holds", Icon: Lock, capabilities: ["quality.view", "hold.manage"], profiles: L, testId: "nav-q3-holds", order: 304 },
  { href: "/quality/stock", labelKey: "logistics.nav.stock", Icon: Boxes, capabilities: ["quality.view", "stock.record"], profiles: L, testId: "nav-q3-stock", order: 305 },
  { href: "/quality/transport", labelKey: "logistics.nav.transport", Icon: Truck, capabilities: ["quality.view", "transport.record"], profiles: L, testId: "nav-q3-transport", order: 306 },
  { href: "/quality/recalls", labelKey: "logistics.nav.recalls", Icon: Biohazard, capabilities: ["quality.view", "recall.manage"], profiles: L, testId: "nav-q3-recalls", order: 307 },
  { href: "/quality/returns", labelKey: "logistics.nav.returns", Icon: RotateCcw, capabilities: ["quality.view", "stock.record"], profiles: L, testId: "nav-q3-returns", order: 308 },
  { href: "/quality/mapping", labelKey: "logistics.nav.mapping", Icon: Map, capabilities: ["quality.view", "storage.manage"], profiles: L, testId: "nav-q3-mapping", order: 309 },
  { href: "/quality/hygiene", labelKey: "logistics.nav.hygiene", Icon: ClipboardCheck, capabilities: ["quality.view", "storage.manage"], profiles: L, testId: "nav-q3-hygiene", order: 310 },
  { href: "/quality/pest", labelKey: "logistics.nav.pest", Icon: Bug, capabilities: ["quality.view", "storage.manage"], profiles: L, testId: "nav-q3-pest", order: 311 },
  { href: "/quality/imports", labelKey: "logistics.nav.imports", Icon: FileUp, capabilities: ["reading.record", "stock.record"], profiles: L, testId: "nav-q3-imports", order: 312 },
  { href: "/quality/products", labelKey: "logistics.nav.products", Icon: PackageX, capabilities: ["quality.view", "stock.record"], profiles: L, testId: "nav-q3-products", order: 313 },
];
