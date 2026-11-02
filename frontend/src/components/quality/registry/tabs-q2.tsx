import { MteCalibrationsTab, MteLabelTab, MteOotTab } from "../q2/calibration";
import type { QualityTab } from "./types";

/** Extra tabs that package Q2 adds to the Q0 M&TE detail page (spec 8-quality §C.7): calibrations, out-of-tolerance reviews and the status label. */
export const tabsQ2: QualityTab[] = [
  { key: "calibrations", host: "mte", labelKey: "cal.tabCalibrations", render: (p) => <MteCalibrationsTab {...p} /> },
  { key: "oot", host: "mte", labelKey: "cal.tabOot", render: (p) => <MteOotTab {...p} /> },
  { key: "label", host: "mte", labelKey: "cal.tabLabel", render: (p) => <MteLabelTab {...p} /> },
];
