import type { LayerDef } from "../kb/types";

/** City tiers (design/components.md §2): tier 1 always, tier 2 from z5, tier 3 from z7. */
export const CITY_TIER_MINZOOM: Record<number, number> = { 1: 0, 2: 5, 3: 7 };

/** Every rendered point-layer id of a layer (cities have one per tier). */
export function pointLayerIds(l: LayerDef): string[] {
  return l.id === "cities" ? [1, 2, 3].map((t) => `ce-cities-pt-${t}`) : [`ce-${l.id}-pt`];
}
