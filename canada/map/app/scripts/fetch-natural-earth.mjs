#!/usr/bin/env node
// Regenerates the two Natural Earth derivatives the map needs (Agent 05).
// Needs network once; the outputs are committed so the build works offline.
//
//   node scripts/fetch-natural-earth.mjs
//
// Inputs (pinned to the Natural Earth v5.1.2 release, public domain; see
// canada/map/DATA-SOURCES.md entries NE-ADMIN1 and NE-PLACES):
//   ne_50m_admin_1_states_provinces.geojson
//   ne_10m_populated_places_simple.geojson
// Outputs:
//   app/data-src/natural-earth/ca-provinces.geojson   13 provinces and territories
//   canada/knowledge-base/places/city-<pr>-<slug>.json  principal-city records
//
// Selection rule for principal cities (written down so it can be revised):
//   Natural Earth features with adm0_a3 = CAN whose featurecla is
//   "Admin-0 capital" or "Admin-1 capital", or whose pop_max >= 100000.
// Province assignment: the point must fall inside the Natural Earth polygon of
// the province named by adm1name; otherwise the containing polygon is used
// and the disagreement is written into the record's limitations.

import { mkdirSync, writeFileSync, readFileSync, existsSync, readdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const appRoot = resolve(here, "..");
const kbRoot = resolve(appRoot, "../../knowledge-base");
const cacheDir = join(appRoot, ".cache/natural-earth");
const outBoundary = join(appRoot, "data-src/natural-earth/ca-provinces.geojson");
const placesDir = join(kbRoot, "places");

const NE_VERSION = "v5.1.2";
const NE_BASE = `https://raw.githubusercontent.com/nvkelso/natural-earth-vector/${NE_VERSION}/geojson`;
const FILES = {
  admin1: "ne_50m_admin_1_states_provinces.geojson",
  places: "ne_10m_populated_places_simple.geojson",
};
const TODAY = "2026-10-30";
const NEXT_REVIEW = "2027-10-30"; // SPEC §2.7: boundaries and coordinates yearly

async function load(name) {
  mkdirSync(cacheDir, { recursive: true });
  const path = join(cacheDir, name);
  if (!existsSync(path)) {
    const url = `${NE_BASE}/${name}`;
    process.stdout.write(`downloading ${url}\n`);
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
    writeFileSync(path, Buffer.from(await res.arrayBuffer()));
  }
  return JSON.parse(readFileSync(path, "utf8"));
}

const round = (n, d) => Math.round(n * 10 ** d) / 10 ** d;
const roundCoords = (c, d) => (typeof c[0] === "number" ? [round(c[0], d), round(c[1], d)] : c.map((x) => roundCoords(x, d)));

function pointInRing(pt, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if ((yi > pt[1]) !== (yj > pt[1]) && pt[0] < ((xj - xi) * (pt[1] - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
function pointInGeometry(pt, g) {
  const polys = g.type === "Polygon" ? [g.coordinates] : g.coordinates;
  return polys.some((rings) => pointInRing(pt, rings[0]) && !rings.slice(1).some((h) => pointInRing(pt, h)));
}

const slugify = (s) =>
  s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/['’.]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

async function main() {
  const admin1 = await load(FILES.admin1);
  const places = await load(FILES.places);

  // 1. Province and territory boundaries.
  const provinces = admin1.features
    .filter((f) => f.properties.adm0_a3 === "CAN")
    .map((f) => ({
      type: "Feature",
      properties: {
        code: f.properties.postal,
        iso_3166_2: f.properties.iso_3166_2,
        name: f.properties.name_en || f.properties.name,
        name_fr: f.properties.name_fr || null,
        kind: f.properties.type_en || null,
      },
      geometry: { type: f.geometry.type, coordinates: roundCoords(f.geometry.coordinates, 4) },
    }))
    .sort((a, b) => a.properties.code.localeCompare(b.properties.code));
  if (provinces.length !== 13) throw new Error(`expected 13 provinces and territories, got ${provinces.length}`);
  mkdirSync(dirname(outBoundary), { recursive: true });
  writeFileSync(
    outBoundary,
    JSON.stringify({
      type: "FeatureCollection",
      name: "ca-provinces",
      source: `Natural Earth ${NE_VERSION} ne_50m_admin_1_states_provinces, filtered to adm0_a3=CAN, coordinates rounded to 4 decimals. Public domain.`,
      features: provinces,
    }) + "\n",
  );
  const byName = new Map(admin1.features.filter((f) => f.properties.adm0_a3 === "CAN").map((f) => [f.properties.name, f.properties.postal]));

  // 2. Principal-city records.
  const selected = places.features.filter((f) => {
    const p = f.properties;
    return p.adm0_a3 === "CAN" && (p.featurecla === "Admin-0 capital" || p.featurecla === "Admin-1 capital" || p.pop_max >= 100000);
  });
  mkdirSync(placesDir, { recursive: true });
  for (const name of readdirSync(placesDir)) if (/^city-.*\.json$/.test(name)) rmSync(join(placesDir, name));

  const written = [];
  for (const f of selected) {
    const p = f.properties;
    const pt = [p.longitude, p.latitude];
    const declared = byName.get(p.adm1name) || null;
    const containing = provinces.find((pr) => pointInGeometry(pt, pr.geometry))?.properties.code || null;
    const province = containing || declared;
    if (!province) {
      console.warn(`skipped ${p.name}: no province could be determined`);
      continue;
    }
    const limitations = [
      "Gazetteer record only: name, representative point and capital status from Natural Earth. It carries no population, climate, housing or school facts; those belong to Agents 01–04 records.",
      "The point is Natural Earth's representative location at 1:10 million scale, not a surveyed city centre or a Statistics Canada boundary centroid; expect offsets of up to a few kilometres.",
      "Selected because Natural Earth lists it as a national or provincial/territorial capital or gives it pop_max >= 100000; Natural Earth population figures have no stated census vintage and are not reproduced here.",
      "The English name is Natural Earth's `name` field; official French names are not yet recorded (name_fr null).",
    ];
    if (declared && containing && declared !== containing) {
      limitations.push(`Natural Earth adm1name says ${p.adm1name} (${declared}) but the point lies inside the ${containing} polygon; the record uses ${containing}. Needs checking against Statistics Canada boundaries.`);
    }
    const capital = p.featurecla === "Admin-0 capital" ? "national" : p.featurecla === "Admin-1 capital" ? "provincial_territorial" : null;
    const id = `city-${province.toLowerCase()}-${slugify(p.nameascii || p.name)}`;
    const record = {
      id,
      category: "city",
      subcategory: "principal city",
      name: p.name,
      name_fr: null,
      geo: {
        province,
        region: null,
        city: p.name,
        neighbourhood: null,
        address: null,
        lat: round(p.latitude, 6),
        lon: round(p.longitude, 6),
        coord_precision: "approximate",
        coord_source: `Natural Earth ${NE_VERSION} 1:10m Populated Places (ne_10m_populated_places_simple), ne_id ${p.ne_id}`,
        extent: null,
      },
      description:
        capital === "national"
          ? `${p.name}, ${provinces.find((x) => x.properties.code === province).properties.name}: the national capital of Canada. Principal-city point for the map.`
          : capital
            ? `${p.name}: capital of ${provinces.find((x) => x.properties.code === province).properties.name}. Principal-city point for the map.`
            : `${p.name}, ${provinces.find((x) => x.properties.code === province).properties.name}. Principal-city point for the map.`,
      attributes: {
        capital,
        natural_earth: {
          ne_id: p.ne_id,
          featurecla: p.featurecla,
          scalerank: p.scalerank,
          labelrank: p.labelrank,
          min_zoom: p.min_zoom,
        },
        selection_rule: "Natural Earth Canadian populated place that is a national or provincial/territorial capital, or has pop_max >= 100000.",
      },
      data_kind: "official_fact",
      sources: [
        {
          url: "https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-populated-places/",
          title: "Natural Earth 1:10m Cultural Vectors — Populated Places",
          publisher: "Natural Earth (North American Cartographic Information Society)",
          source_type: "other",
          accessed: TODAY,
          data_period: NE_VERSION,
          methodology: `GeoJSON from https://github.com/nvkelso/natural-earth-vector/tree/${NE_VERSION}/geojson; filtered and checked by canada/map/app/scripts/fetch-natural-earth.mjs (point-in-polygon against ne_50m_admin_1_states_provinces).`,
          licence: "Public domain",
        },
      ],
      units: null,
      verification: {
        status: "partially_verified",
        confidence: "medium",
        verified_by: "agent-05",
        last_verified: TODAY,
        next_review: NEXT_REVIEW,
        notes: "Province checked by point-in-polygon against Natural Earth admin-1. Not yet cross-checked against Statistics Canada census subdivision boundaries (Phase 2).",
      },
      responsible_agent: "agent-05",
      limitations: limitations.join(" "),
      created: TODAY,
      updated: TODAY,
    };
    if (written.some((w) => w.id === id)) throw new Error(`duplicate id ${id}`);
    writeFileSync(join(placesDir, `${id}.json`), JSON.stringify(record, null, 2) + "\n");
    written.push(record);
  }
  console.log(`wrote ${provinces.length} boundaries to ${outBoundary}`);
  console.log(`wrote ${written.length} city records to ${placesDir}`);
  for (const r of written) console.log(`  ${r.id}  ${r.attributes.capital ?? ""}`);
}

main().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
