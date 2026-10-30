// Knowledge-base loader: fetches the static files written by scripts/build-data.mjs.
// Everything is relative to the app's base URL so the built app works from any path.
import type { AttributionEntry, Category, KbIndex, KbRecord } from "./types";
import type { FeatureCollection, Point } from "geojson";

const base = `${import.meta.env.BASE_URL}data/`;

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(base + path);
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return (await res.json()) as T;
}

export const loadIndex = () => getJson<KbIndex>("index.json");
export const loadAttribution = () => getJson<AttributionEntry[]>("attribution.json");
export const loadBoundaries = () => getJson<FeatureCollection>("boundaries/ca-provinces.geojson");

export type PointCollection = FeatureCollection<Point, { id: string; name: string; category: Category; layer: string; province: string; rank: number; capital: string }>;
export const loadCategoryGeojson = (c: Category) => getJson<PointCollection>(`${c}.geojson`);

const recordCache = new Map<Category, Promise<Record<string, KbRecord>>>();
export function loadRecords(c: Category): Promise<Record<string, KbRecord>> {
  let p = recordCache.get(c);
  if (!p) {
    p = getJson<Record<string, KbRecord>>(`records/${c}.json`);
    recordCache.set(c, p);
  }
  return p;
}
export async function loadRecord(c: Category, id: string): Promise<KbRecord | null> {
  return (await loadRecords(c))[id] ?? null;
}
