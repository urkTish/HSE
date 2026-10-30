#!/usr/bin/env node
// Knowledge base → map data (Agent 05, SPEC §9 G–H, ARCHITECTURE.md §3).
//
//   node scripts/build-data.mjs           build; fail only if Agent 05's own lane fails validation
//   node scripts/build-data.mjs --strict  fail when any record anywhere fails validation
//
// 1. Runs canada/knowledge-base/scripts/validate.mjs over the whole knowledge base.
// 2. Reads every record that passed. Records that failed are left out and listed
//    in index.json → excluded, so one lane's half-finished file cannot break the map.
// 3. Applies the static-asset rules: no prices, rents, tuition amounts or forecasts
//    in public files; schools only when attributes.qualifying === "qualifying".
// 4. Writes public/data/<category>.geojson, records/<category>.json, index.json,
//    boundaries/ca-provinces.geojson and attribution.json (from DATA-SOURCES.md).
// public/data/ is generated and git-ignored; never edit it by hand.

import { spawnSync } from "node:child_process";
import { readFileSync, writeFileSync, readdirSync, statSync, mkdirSync, rmSync, copyFileSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const appRoot = resolve(here, "..");
const kbRoot = resolve(appRoot, "../../knowledge-base");
const mapRoot = resolve(appRoot, "..");
const outDir = join(appRoot, "public/data");
const strict = process.argv.includes("--strict");
const OWN_LANE = "places";

const layerConfig = JSON.parse(readFileSync(join(appRoot, "src/kb/layers.config.json"), "utf8"));

// ---------- 1. validate ----------
const run = spawnSync(process.execPath, [join(kbRoot, "scripts/validate.mjs"), kbRoot], { cwd: kbRoot, encoding: "utf8" });
if (run.error) throw run.error;
const vOut = run.stdout || "";
const summaryLine = vOut.trim().split("\n").filter(Boolean).pop() || "(no validator output)";
const failedFiles = new Set(
  vOut.split("\n").filter((l) => l.startsWith("✗ ")).map((l) => resolve(kbRoot, l.slice(2).trim())),
);
console.log(`validator: ${summaryLine}`);
const ownFailures = [...failedFiles].filter((f) => relative(kbRoot, f).split(sep)[0] === OWN_LANE);
if (ownFailures.length) {
  console.error(vOut);
  console.error(`build-data: Agent 05's lane (knowledge-base/${OWN_LANE}) fails validation; fix it first.`);
  process.exit(1);
}
if (strict && failedFiles.size) {
  console.error(vOut);
  console.error(`build-data --strict: ${failedFiles.size} record file(s) fail validation.`);
  process.exit(1);
}

// ---------- 2. read records ----------
const SKIP_DIRS = new Set(["schema", "scripts", "node_modules", ".git"]);
function walk(dir, out = []) {
  for (const name of readdirSync(dir).sort()) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) {
      if (!SKIP_DIRS.has(name)) walk(p, out);
    } else if (name.endsWith(".json")) out.push(p);
  }
  return out;
}

const excluded = [];
const records = [];
for (const file of walk(kbRoot)) {
  const rel = relative(kbRoot, file);
  if (failedFiles.has(file)) {
    excluded.push({ file: rel, reason: "fails validation" });
    continue;
  }
  let data;
  try {
    data = JSON.parse(readFileSync(file, "utf8"));
  } catch {
    excluded.push({ file: rel, reason: "invalid JSON" });
    continue;
  }
  if (!data || data.type === "FeatureCollection" || (data.$schema && !data.id)) continue;
  if (data.data_kind === "forecast") {
    excluded.push({ file: rel, id: data.id, reason: "forecast: never stored in static assets (served on demand)" });
    continue;
  }
  if (data.category === "school" && data.attributes?.qualifying !== "qualifying") {
    excluded.push({ file: rel, id: data.id, reason: `school with qualifying = ${data.attributes?.qualifying}: education layer shows qualifying schools only` });
    continue;
  }
  records.push({ rel, data });
}

// ---------- 3. static-asset rules ----------
// Keys whose numeric values are money; withheld everywhere (SPEC §9 B, §12).
const MONEY_KEY = /(^|_)(price|prices|rent|rents|tuition|fee|fees|cost|costs|amount|cad)(_|$)/i;
function stripMoney(obj, path, withheld) {
  if (Array.isArray(obj)) return obj.map((v, i) => stripMoney(v, `${path}[${i}]`, withheld));
  if (obj && typeof obj === "object") {
    const out = {};
    for (const [k, v] of Object.entries(obj)) {
      if (typeof v === "number" && MONEY_KEY.test(k)) {
        withheld.push(`${path}.${k}`);
        continue;
      }
      out[k] = stripMoney(v, `${path}.${k}`, withheld);
    }
    return out;
  }
  return obj;
}
function sanitize(rec) {
  const withheld = [];
  const r = structuredClone(rec);
  if (r.category === "re" && r.attributes) {
    // A market observation's figures are changing financial data: keep what was measured, where and when; withhold the numbers.
    for (const k of ["value", "year_over_year_change_pct"]) {
      if (k in r.attributes && r.attributes[k] !== null) {
        withheld.push(`attributes.${k}`);
        delete r.attributes[k];
      }
    }
  }
  r.attributes = stripMoney(r.attributes ?? {}, "attributes", withheld);
  if (withheld.length) r._withheld = withheld;
  return r;
}

// ---------- 4. geometry and layers ----------
const norm = (s) => (s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
const cityIndex = new Map();
for (const { data } of records) {
  if (data.category === "city" && typeof data.geo.lat === "number") cityIndex.set(`${data.geo.province}|${norm(data.name)}`, data);
}
function locate(rec) {
  const g = rec.geo || {};
  if (typeof g.lat === "number" && typeof g.lon === "number") return { lat: g.lat, lon: g.lon, geom_source: "record" };
  const a = rec.attributes || {};
  if (rec.category === "clim" && typeof a.station_lat === "number" && typeof a.station_lon === "number")
    return { lat: a.station_lat, lon: a.station_lon, geom_source: "station" };
  if (rec.category === "school" && Array.isArray(a.campuses)) {
    const c = a.campuses.find((x) => typeof x.lat === "number" && typeof x.lon === "number");
    if (c) return { lat: c.lat, lon: c.lon, geom_source: "campus" };
  }
  const city = g.city && cityIndex.get(`${g.province}|${norm(g.city)}`);
  if (city && city.id !== rec.id) return { lat: city.geo.lat, lon: city.geo.lon, geom_source: `city:${city.id}` };
  return { lat: null, lon: null, geom_source: null };
}
const layerFor = (rec) => {
  for (const l of layerConfig.layers) {
    if (!l.categories.includes(rec.category)) continue;
    if (l.subcategoryPattern && !new RegExp(l.subcategoryPattern, "i").test(rec.subcategory ?? "")) continue;
    return l.id;
  }
  return null; // e.g. `nat`: searchable and listed by province, not drawn
};
const rankFor = (rec) => {
  if (rec.category !== "city") return 5;
  const ne = rec.attributes?.natural_earth;
  if (rec.attributes?.capital === "national") return 0;
  return typeof ne?.scalerank === "number" ? Math.min(10, ne.scalerank) : 8;
};

// ---------- 5. write ----------
rmSync(outDir, { recursive: true, force: true });
mkdirSync(join(outDir, "records"), { recursive: true });
mkdirSync(join(outDir, "boundaries"), { recursive: true });

const byCategory = {};
const index = [];
for (const { rel, data } of records) {
  const rec = sanitize(data);
  const loc = locate(rec);
  const layer = layerFor(rec);
  const entry = {
    id: rec.id,
    name: rec.name,
    name_fr: rec.name_fr ?? null,
    category: rec.category,
    subcategory: rec.subcategory ?? null,
    layer,
    province: rec.geo.province,
    city: rec.geo.city ?? null,
    lat: loc.lat,
    lon: loc.lon,
    geom_source: loc.geom_source,
    rank: rankFor(rec),
    capital: rec.category === "city" ? (rec.attributes?.capital ?? null) : null,
    file: rel,
  };
  index.push(entry);
  (byCategory[rec.category] ??= { records: {}, features: [] }).records[rec.id] = { ...rec, _map: { layer, geom_source: loc.geom_source, file: rel } };
  if (loc.lat !== null && layer) {
    byCategory[rec.category].features.push({
      type: "Feature",
      id: rec.id,
      properties: { id: rec.id, name: rec.name, category: rec.category, layer, province: rec.geo.province, rank: entry.rank, capital: entry.capital ?? "" },
      geometry: { type: "Point", coordinates: [loc.lon, loc.lat] },
    });
  }
}

const allCategories = Object.keys(layerConfig.categoryLabels);
const files = {};
for (const cat of allCategories) {
  const c = byCategory[cat] ?? { records: {}, features: [] };
  writeFileSync(join(outDir, `${cat}.geojson`), JSON.stringify({ type: "FeatureCollection", features: c.features }));
  writeFileSync(join(outDir, "records", `${cat}.json`), JSON.stringify(c.records));
  files[cat] = { geojson: `${cat}.geojson`, records: `records/${cat}.json`, features: c.features.length, records_count: Object.keys(c.records).length };
}
copyFileSync(join(appRoot, "data-src/natural-earth/ca-provinces.geojson"), join(outDir, "boundaries/ca-provinces.geojson"));
const provinces = JSON.parse(readFileSync(join(appRoot, "data-src/natural-earth/ca-provinces.geojson"), "utf8")).features.map((f) => f.properties);

// Attribution strings from DATA-SOURCES.md (single source of truth).
const ds = readFileSync(join(mapRoot, "DATA-SOURCES.md"), "utf8");
const block = ds.split("<!-- attribution:begin -->")[1]?.split("<!-- attribution:end -->")[0];
if (!block) throw new Error("DATA-SOURCES.md has no attribution block");
const attribution = block
  .split("\n")
  .filter((l) => l.startsWith("|") && !/^\|\s*(id|---)/.test(l))
  .map((l) => l.split("|").slice(1, -1).map((c) => c.trim()))
  .map(([id, text, url, when]) => ({ id, text, url: url || null, when: when || "always" }));
writeFileSync(join(outDir, "attribution.json"), JSON.stringify(attribution, null, 2));

const byLayer = Object.fromEntries(layerConfig.layers.map((l) => [l.id, index.filter((e) => e.layer === l.id && e.lat !== null).length]));
writeFileSync(
  join(outDir, "index.json"),
  JSON.stringify({
    generated_at: new Date().toISOString(),
    validator: { summary: summaryLine, failed_files: [...failedFiles].map((f) => relative(kbRoot, f)) },
    counts: { records: index.length, on_map: index.filter((e) => e.lat !== null && e.layer).length, by_layer: byLayer },
    files,
    provinces,
    excluded,
    records: index,
  }),
);

console.log(`build-data: ${index.length} record(s) → ${outDir}`);
console.log(`  on map by layer: ${Object.entries(byLayer).map(([k, v]) => `${k} ${v}`).join(", ")}`);
console.log(`  excluded: ${excluded.length}${excluded.length ? " (" + excluded.map((e) => `${e.file}: ${e.reason}`).join("; ") + ")" : ""}`);
