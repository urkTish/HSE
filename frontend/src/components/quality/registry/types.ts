import type { ReactNode } from "react";
import type { QualityProfile } from "../nav/types";

/** The detail pages that accept extra tabs from later parts (spec 8-quality §3.2). */
export type QualityTabHost = "ncr" | "supplier" | "mte";

/**
 * An extra tab a part adds to an NCR, supplier or M&TE detail page (`registry/tabs-q<n>.tsx`).
 * `labelKey` is a key under `quality.` in the part's message file.
 */
export interface QualityTab {
  key: string;
  host: QualityTabHost;
  labelKey: string;
  profiles?: QualityProfile[];
  render: (props: { recordId: string; projectId: string | null }) => ReactNode;
}
