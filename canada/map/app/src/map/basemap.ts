// Base-map style resolution (DATA-SOURCES.md: OFM-STYLE, OFM-STYLE-DARK, fallback §2).
import type { StyleSpecification } from "maplibre-gl";

export const STYLE_URLS = {
  light: "https://tiles.openfreemap.org/styles/positron",
  dark: "https://tiles.openfreemap.org/styles/dark",
} as const;

/** Natural Earth II shaded relief, hosted by OpenFreeMap (DATA-SOURCES.md: OFM-RELIEF). */
export const RELIEF_TILES = "https://tiles.openfreemap.org/natural_earth/ne2sr/{z}/{x}/{y}.png";

export const CANADA_BOUNDS: [[number, number], [number, number]] = [
  [-141.1, 41.6],
  [-52.5, 83.2],
];

/** Base-map layers that belong to layer 12, "Transportation and infrastructure". */
export const TRANSPORT_SOURCE_LAYERS = new Set(["transportation", "transportation_name", "aeroway", "aerodrome_label"]);

export type BasemapMode = "openfreemap" | "fallback";
export type Theme = "light" | "dark";

/** Built-in style with no third-party requests: used when OpenFreeMap is unreachable. */
export function fallbackStyle(theme: Theme): StyleSpecification {
  return {
    version: 8,
    name: "canada-explorer-fallback",
    sources: {},
    layers: [{ id: "background", type: "background", paint: { "background-color": theme === "dark" ? "#1f1e1b" : "#f2efe9" } }],
  };
}

export async function resolveStyle(theme: Theme, timeoutMs = 6000): Promise<{ style: StyleSpecification; mode: BasemapMode }> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(STYLE_URLS[theme], { signal: ctrl.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const style = (await res.json()) as StyleSpecification;
    if (style.version !== 8 || !Array.isArray(style.layers)) throw new Error("not a style");
    return { style, mode: "openfreemap" };
  } catch {
    return { style: fallbackStyle(theme), mode: "fallback" };
  } finally {
    clearTimeout(timer);
  }
}

export function currentTheme(): Theme {
  const forced = document.documentElement.dataset.theme;
  if (forced === "dark" || forced === "light") return forced;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** Reads a design token from canada/design/tokens.css (MapLibre cannot read CSS variables). */
export function token(name: string, fallback: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

export const prefersReducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
