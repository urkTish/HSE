# Map architecture

Owner: Agent 05. Written 2026-10-30 for Phase 1. Governing text: SPEC §9
(defaults §9 H), §12; DECISIONS D-005. Licences and attribution:
`DATA-SOURCES.md`. Current state: `STATUS.md`.

## 1. Shape of the system

```
canada/knowledge-base/**/<id>.json          records from Agents 01–05 (validated JSON)
        │   node scripts/build-data.mjs
        │     1. validate.mjs over the whole knowledge base
        │     2. read records that passed; drop forecasts and non-qualifying schools
        │     3. withhold money figures (values, tuition amounts, $ amounts in text)
        │     4. place each record (coordinates → station → campus → city point)
        │     5. assign one of the twelve layers
        ▼
app/public/data/                            generated, git-ignored, never hand-edited
  index.json                 every published record: id, name, category, layer, province, lat/lon, …
  <category>.geojson         points per category (14 files; empty collections allowed)
  records/<category>.json    full sanitised records, loaded lazily for the profile panel
  boundaries/ca-provinces.geojson   copied from app/data-src/natural-earth/
  attribution.json           parsed from DATA-SOURCES.md §3
        │   fetch() at runtime (relative to the app's base URL)
        ▼
Vite + React app  ── kb/ (loader, types, geo) ── map/ (MapLibre) ── ui/ (panels, chart, search) ── dynamic/ (on-demand stub)
```

The app is static: it can be served from any folder or static host. It
makes network requests only to itself and to the OpenFreeMap tile service
(style, vector tiles, glyphs, sprites, relief raster). No keys, cookies or
analytics.

## 2. Modules (SPEC §9 H: map, knowledge base, dynamic retrieval and UI kept separate)

| Module | Path | Responsibility | Knows about |
|---|---|---|---|
| Data build | `app/scripts/build-data.mjs` | Validator run, sanitising, geometry, layer assignment, file output | knowledge base, `layers.config.json`, `DATA-SOURCES.md` |
| Gazetteer import | `app/scripts/fetch-natural-earth.mjs` | Regenerates `knowledge-base/places/city-*.json` and the province boundary file from pinned Natural Earth v5.1.2 | Natural Earth only |
| Knowledge base (client) | `app/src/kb/` | `types.ts` mirrors the JSON schemas; `loader.ts` fetches generated files with a per-category cache; `geo.ts` great-circle distance and accent-insensitive normalisation; `layers.config.json` the twelve layers (shared with the build) | generated files |
| Map | `app/src/map/` | `basemap.ts` style resolution with 6 s timeout and built-in fallback, theme detection, token reader; `MapView.tsx` MapLibre map, province boundaries with hover/selected feature-state, one clustered GeoJSON source per layer, selection ring, attribution control, fly-to | nothing about profiles or search; reports clicks via `onSelect` |
| Dynamic retrieval | `app/src/dynamic/onDemand.ts` | The single entry point for figures that change (rents, prices, tuition amounts, rates, forecasts). Phase 1 returns `unavailable` with a reason | — |
| UI | `app/src/ui/` | `LayerPanel` (12 toggles, counts, honest empty states), `SearchBox` (combobox over names), `ProfilePanel` (record and province profiles, section by section), `ClimateChart` (SVG, bound to the `clim` schema) | kb types, dynamic |
| Shell | `app/src/App.tsx` | Loads data, owns UI state (layers on, selection, focus), composes the modules | all |
| Styling | `app/src/index.css` | Imports Tailwind, `canada/design/tokens.css` and `canada/design/tailwind-theme.css` (Agent 06); the app defines no colours of its own. MapLibre paint colours are read from the same tokens at style load | design lane |

## 3. From validated records to layers

**Validation.** `build-data` runs `knowledge-base/scripts/validate.mjs` over
the whole knowledge base and parses its `✗` lines. A record that fails is
left out and listed in `index.json → excluded`, so one lane's unfinished
file cannot take the map down. The build itself fails only when Agent 05's
own lane (`knowledge-base/places/`) fails, or on any failure with
`--strict` (intended for the coordinator's pre-commit run). The validator's
summary line is shown at the bottom of the layer panel.

**Placement** (first that applies; the profile says which was used):
`geo.lat/lon` → for `clim`, `attributes.station_lat/lon` → for `school`,
the first campus with coordinates → the `city` record with the same
province and normalised `geo.city` name → none (searchable, listed on the
province profile, not drawn).

**Layers** (`app/src/kb/layers.config.json`, SPEC §9 C):

| # | Layer | Categories | Notes |
|---|---|---|---|
| 1 | Cities and towns | `city` | Natural Earth principal cities now; StatCan CSDs in Phase 2 |
| 2 | Neighbourhoods | `nbhd` | none yet |
| 3 | Physical geography and terrain | `region`, `landform` | Agent 04 |
| 4 | Elevation and topography | — (raster) | Natural Earth II shaded relief, z ≤ 6, from OpenFreeMap |
| 5 | Climate regions and climate information | `clim`, `hazard` | Agent 04; `clim` drawn at the station |
| 6 | Real estate | `re` | Agent 02; metadata only, figures withheld |
| 7 | Verified alternative private schools | `school` | Agent 03; `qualifying` only |
| 8 | National and provincial parks | `park` | Agent 04 |
| 9 | Hiking trails | `trail` | Agent 04 |
| 10 | Natural attractions | `attr` whose `subcategory` matches the natural-feature pattern in the config | Agent 04 |
| 11 | Tourism and historical attractions | other `attr` | Agent 04 |
| 12 | Transportation and infrastructure | `route`, `service` + base-map roads, rail, airports | toggles the base map's transportation layers too |

`nat` records have no layer: they are national or provincial rules. They are
searchable and appear on the province profile under "Records without a map
location".

**Contextual visibility.** Every layer except cities is a clustered source
(radius 40 px, clusters up to z9; click zooms to the expansion zoom). Cities
are few and drawn unclustered, with capitals larger and labels ordered by
Natural Earth rank so collisions hide the minor ones first. Only layers 1
and 12 are on by default.

## 4. What is never in static files, and how changing figures will appear

SPEC §9 B and §12 require prices, rents and other changing financial figures
to be fetched on demand and shown with their date and source. The hard rule
for this lane is stricter: no prices, rents or forecasts in static assets.
`build-data` therefore:

- drops every record with `data_kind: "forecast"`;
- drops every `re` record that does not cite Statistics Canada among its
  sources (DECISIONS D-008: CREA and CMHC terms forbid republishing their
  figures; MLS® HPI benchmark prices are linked to the CREA HPI tool, never
  shown from storage). Two-bedroom survey rents and vacancy rates survive
  because Statistics Canada republishes them under its open licence;
- for `re` records removes `attributes.value` and
  `attributes.year_over_year_change_pct`, and redacts dollar amounts and
  percentages written in any text field (`notes`, `methodology`, …) to
  `[amount withheld]` / `[figure withheld]`;
- for `school` records removes `tuition.amount_cad_min/max` (the school
  year stays) and redacts dollar amounts in text;
- for every other category except `nat`, removes numeric fields whose key
  names a price, rent, cost, fee or tuition and redacts dollar amounts in
  text;
- leaves `nat` records intact: tax brackets, credits and programme fees are
  legislated parameters, not market prices (proposed decision P-05-3 in
  `STATUS.md`).

Each sanitised record lists what was removed in `_withheld`; the profile
shows it. The profile's real-estate section shows metric, property type,
bedrooms, period, geography and figure kind, and states that the figure is
not stored in the map.

**Phase 4 on-demand path** (design by Agent 02:
`knowledge-base/real-estate/METHODOLOGY.md` §5 and `investment-model.md`
§5; not implemented in Phase 1). `src/dynamic/onDemand.ts` stays the only
caller; it talks to the sources directly from the browser if CORS allows,
otherwise through a thin proxy that forwards nothing from `USER-PROFILE.md`.

| Figure | Source and call | Cache | Use |
|---|---|---|---|
| Two-bedroom average rent and vacancy rate per CMA | Statistics Canada Web Data Service: `POST https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods` with body `[{"vectorId": N, "latestN": 1}]` (tables 34-10-0133-01 and 34-10-0130-01; vector IDs per CMA in METHODOLOGY §5.1); freshness via `getCubeMetadata` | 7 days per vector; refresh early when the cube's `releaseTime` is newer; cube metadata 24 h | Real-estate profile line |
| 5-year conventional mortgage rate (posted) | Bank of Canada Valet: `GET https://www.bankofcanada.ca/valet/observations/V80691335/json?recent=1` | 24 h | Pre-fills the investment calculator's rate field, labelled with series and week; never stored in a record or file |
| MLS® HPI benchmark prices; CMHC centre pages | Link-out only (CREA HPI tool, CMHC rental market reports) | — | Link card, never a number |

**Display rule for any market figure** (coordinator, 2026-10-30): one line
with the value and unit; the metric and `figure_kind` in words (survey,
benchmark, average, median, asking); the period; the source with table or
series; the retrieval date. A figure more than 60 days past its period's
release carries an "older than 60 days" badge (SPEC §2.7). If a fetch fails
the UI shows "Not available right now" with the source link — never a stale
number without its date and never an estimate. Daily weather is shown only
on explicit request, from a provider recorded in `DATA-SOURCES.md`, visibly
separated from normals.

## 5. Education layer restriction

Enforced twice: `build-data` writes a `school` record to any public file
only when `attributes.qualifying === "qualifying"` (the validator already
requires such records to be `verified`); candidates and excluded schools are
counted in `index.json → excluded` without their names. The profile's
Education section renders only for `school` records, which can only be
qualifying ones. Nothing else populates that section.

## 6. Profiles, search, chart

- **Profile panel.** Header (category, name, French name, place), then only
  the sections the record has: About, Year-round climate, Education, Market
  observation, Details (generic attributes, arrays of rows as tables),
  Withheld figures, Nearby in the knowledge base (≤ 50 km, straight-line,
  labelled as such), Location (coordinates, precision, coordinate source,
  how it was placed), Sources and reliability (data kind, verification,
  sources with access dates and licences, limitations, record ID). A
  `city` profile pulls in `clim` records with the same province and city
  name, or the nearest within 30 km. A province click opens a province
  profile (counts per layer, principal cities, unmapped records, boundary
  caveat).
- **Climate chart.** Hand-written SVG following `design/design-system.md`
  §9: small multiples on one month axis (temperature range bars split at
  0 °C with mean ticks and a 0 °C reference line; precipitation mm;
  snowfall cm, omitted when every month is null), hatched null months, zero
  drawn as a baseline tick, hover and arrow-key month reading with an
  `aria-live` mirror, a full table, and the normals period, station, climate
  ID and source always visible. No dual axis; never labelled as a forecast.
- **Search.** Client-side over `index.json` and the 13 provinces and
  territories; accent-insensitive; every word must match the name, French
  name, city, subcategory, category label or province. Records without
  coordinates are found too and marked "not on map".

## 7. Deviations from SPEC §9 H defaults

None in substance. Natural Earth admin-1 is used as the permitted first
pass for boundaries; the relief layer is a small-scale raster rather than
NRCan elevation. The choices that need a `DECISIONS.md` entry are listed as
proposals P-05-1 … P-05-6 in `STATUS.md`.

## 8. Phase 2–4 plan

**Phase 2 — geographic and climate foundation**
- Replace NE-ADMIN1 with Statistics Canada 2021 cartographic boundaries
  (provinces/territories, CMAs, CSDs), generalised with mapshaper, built by
  a script into `data-src/statcan/`; CMA outlines feed the real-estate layer.
- Cities and towns from StatCan CSDs or the Canadian Geographical Names
  Database (OGL-C), with population tiers from the census, replacing or
  supplementing the Natural Earth points (IDs stay stable).
- Terrain: NRCan CDEM-derived hillshade (and contours at z9+) as
  pre-rendered tiles or PMTiles we host, per design-system §7.6; "Terrain"
  map control.
- Bind Agent 04's `clim` records; consistent temperature domain across
  cities for comparison; annual stat strip; Chart | Table segmented
  control.
- Region polygons: the records carry points only; agree with Agent 04 on a
  GeoJSON geometry convention (for example `knowledge-base/geography-climate/geometry/<id>.geojson`).

**Phase 3 — core interactive map**
- Marker shapes per layer drawn on canvas and registered with `addImage`
  (design-system §7.2), selection bracket, cluster sizes 28/36/44 px.
- Mobile bottom sheet with peek height; layer rail collapsed to icons.
- Re-theme base-map land and water to the design tokens; manual theme toggle.
- Self-host Archivo and Source Sans 3 (SIL OFL) via npm packages, with a
  `DATA-SOURCES.md` row each.
- URL state (selected record, layers, view) so a view can be shared.
- Code-split MapLibre to reduce the 1.3 MB main bundle.

**Phase 4 — specialist data integration**
- On-demand service for `re` figures and tuition (§4), with date and source.
- Comparison of two to four locations following SPEC §4 (ordinal bands,
  evidence IDs, missing data shown, sensitivity range).
- Filters (distance from a selected location, layer-specific facets) and
  concept search combining records ("alternative schools within 20 km with
  milder winters").
- Geocoding (Nominatim/Photon, on explicit search only, policy-compliant)
  and deep links to external navigation apps (Phase 6 routing).
