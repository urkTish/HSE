import { Award, Beaker, ClipboardCheck, FlaskConical, Gauge, Layers, PackageCheck, PackageX, Wrench } from "lucide-react";
import type { QualityNavItem } from "./types";

const C: QualityNavItem["profiles"] = ["construction"];
const BOTH: QualityNavItem["profiles"] = ["construction", "logistics"];

/** Sidebar items of package Q2 materials, testing and lab, welding, calibration, competence (spec 8-quality §C.7). */
export const navQ2: QualityNavItem[] = [
  { href: "/quality/materials", labelKey: "nav.materials", Icon: PackageCheck, capabilities: ["quality.view", "material.submit", "material.decide"], profiles: C, testId: "nav-q-materials", order: 200 },
  { href: "/quality/material-inspections", labelKey: "nav.materialInspections", Icon: ClipboardCheck, capabilities: ["quality.view", "material.submit", "material.decide"], profiles: C, testId: "nav-q-mirs", order: 201 },
  { href: "/quality/quarantine", labelKey: "nav.quarantine", Icon: PackageX, capabilities: ["quality.view", "material.submit", "material.decide"], profiles: C, testId: "nav-q-quarantine", order: 202 },
  { href: "/quality/tests", labelKey: "nav.tests", Icon: FlaskConical, capabilities: ["quality.view", "test.record", "test.verify"], profiles: BOTH, testId: "nav-q-tests", order: 210 },
  { href: "/quality/test-types", labelKey: "nav.testTypes", Icon: Beaker, capabilities: ["quality.view", "quality.author"], profiles: BOTH, testId: "nav-q-test-types", order: 211 },
  { href: "/quality/pours", labelKey: "nav.pours", Icon: Layers, capabilities: ["quality.view", "test.record"], profiles: C, testId: "nav-q-pours", order: 212 },
  { href: "/quality/welding", labelKey: "nav.welding", Icon: Wrench, capabilities: ["quality.view", "welding.record", "welding.approve"], profiles: C, testId: "nav-q-welding", order: 220 },
  { href: "/quality/calibration", labelKey: "nav.calibration", Icon: Gauge, capabilities: ["quality.view", "mte.manage", "calibration.decide"], profiles: BOTH, testId: "nav-q-calibration", order: 230 },
  { href: "/quality/competence", labelKey: "nav.competence", Icon: Award, capabilities: ["competence.manage"], profiles: BOTH, testId: "nav-q-competence", order: 240 },
];
