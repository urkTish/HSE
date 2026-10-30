// Small geographic helpers. Distances are straight-line (great-circle), never route lengths.
import type { IndexEntry } from "./types";

export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const r = 6371.0088;
  const rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad;
  const dLon = (lon2 - lon1) * rad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(a));
}

export const normalise = (s: string | null | undefined) =>
  (s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();

export function nearby(from: { lat: number; lon: number; id: string }, all: IndexEntry[], radiusKm: number, limit: number) {
  return all
    .filter((e) => e.id !== from.id && e.lat !== null && e.lon !== null)
    .map((e) => ({ entry: e, km: haversineKm(from.lat, from.lon, e.lat as number, e.lon as number) }))
    .filter((x) => x.km <= radiusKm)
    .sort((a, b) => a.km - b.km)
    .slice(0, limit);
}
