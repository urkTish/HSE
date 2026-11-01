import { SupplierQualityTab } from "@/components/quality/q4/analytics";
import type { QualityTab } from "./types";

/** Extra tabs that package Q4 adds (spec 8-quality §E.11): supplier evaluations and quality scores on
 * the supplier page (Q-SUP-01…05). */
export const tabsQ4: QualityTab[] = [
  { key: "q4-quality", host: "supplier", labelKey: "q4.sup.tab", render: ({ recordId, projectId }) => <SupplierQualityTab recordId={recordId} projectId={projectId} /> },
];
