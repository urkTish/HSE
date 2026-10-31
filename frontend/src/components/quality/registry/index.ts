import { tabsQ1 } from "./tabs-q1";
import { tabsQ2 } from "./tabs-q2";
import { tabsQ3 } from "./tabs-q3";
import { tabsQ4 } from "./tabs-q4";
import type { QualityTab, QualityTabHost } from "./types";

export type { QualityTab, QualityTabHost };

const ALL: QualityTab[] = [...tabsQ1, ...tabsQ2, ...tabsQ3, ...tabsQ4];

/** Extra tabs registered by the parts for one host page. */
export function tabsFor(host: QualityTabHost): QualityTab[] {
  return ALL.filter((t) => t.host === host);
}
