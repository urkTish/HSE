# Data sources, tiles, fonts and images used by the map

Owner: Agent 05. Last reviewed: 2026-10-30.

**Rule.** Nothing enters the application without a line in this file:
dataset, tile service, style, font, icon, image or code library. Each line
names the licence, the attribution text, and the usage limits we must
respect. The table in *Attribution rendered on the map* is machine-read by
`app/scripts/build-data.mjs` and written to `app/public/data/attribution.json`;
the map's attribution control shows exactly those strings, so edit them here
and nowhere else.

## 1. In use (Phase 1)

| ID | What | Provider / URL | Licence | Attribution required | Usage limits we respect |
|---|---|---|---|---|---|
| OFM-STYLE | Base-map style "Positron" (style JSON) | OpenFreeMap — `https://tiles.openfreemap.org/styles/positron` (verified HTTP 200, 2026-10-30) | Style code BSD 3-Clause; design CC BY 4.0 (OpenMapTiles), derived from CARTO basemaps by Stamen and Paul Norman, CC BY 3.0 (OpenFreeMap `LICENSE.md`) | Yes — see `OFM-STYLE` row below | Free public instance, "no limits on the number of map views or requests", no API key, no cookies (openfreemap.org, read 2026-10-30). Terms of Service last updated 2026-10-14: no automated collection except offline downloads of ≤ 3,000 tiles or 50 MB, ≤ 4 parallel requests, unique User-Agent. The app performs **no** bulk or offline downloads. Service is "as-is" and may be discontinued without notice → fallback style below. |
| OFM-STYLE-DARK | Base-map style "Dark" (Dark Matter), used when the interface is in dark mode | OpenFreeMap — `https://tiles.openfreemap.org/styles/dark` (verified HTTP 200, 2026-10-30; OpenFreeMap notes it is "not yet complete", unmodified from upstream except fonts) | Code BSD 3-Clause; design CC BY 4.0 (openmaptiles/dark-matter-gl-style), derived from CARTO Dark Matter, CC BY 3.0 | Yes — `OFM-STYLE` row in §3 | As OFM-STYLE. |
| OFM-TILES | OpenMapTiles-schema vector tiles of OpenStreetMap (`https://tiles.openfreemap.org/planet`, TileJSON 3.0.0, max zoom 14) | OpenFreeMap / OpenStreetMap contributors | Data: ODbL 1.0 (OpenStreetMap); schema/code: BSD 3-Clause (OpenMapTiles) | Yes. The TileJSON supplies "OpenFreeMap © OpenMapTiles Data from OpenStreetMap", which MapLibre renders automatically; we also render the OSM line below. Share-alike applies to any database we derive from OSM data (none in Phase 1). | As OFM-STYLE. |
| OFM-RELIEF | Natural Earth II with shaded relief, raster tiles `https://tiles.openfreemap.org/natural_earth/ne2sr/{z}/{x}/{y}.png` (max zoom 6), used by layer 4 "Elevation and topography" | Natural Earth data, hosted by OpenFreeMap | Public domain (Natural Earth) | Not required; credited as "Made with Natural Earth" | As OFM-STYLE. Small-scale only (z ≤ 6); not an elevation dataset. |
| OFM-FONTS | Map label glyphs, Noto Sans Regular/Bold/Italic (`https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf`) | OpenFreeMap (Google Noto) | SIL Open Font License 1.1 | No on-map attribution required by OFL | As OFM-STYLE. |
| OFM-SPRITES | Base-map icon sprite (`https://tiles.openfreemap.org/sprites/ofm_f384/ofm`) | OpenFreeMap; Maki POI icons | CC0 1.0 (Maki); arrow from Wikimedia Commons, public domain | No | As OFM-STYLE. |
| NE-ADMIN1 | Province and territory boundaries: `ne_50m_admin_1_states_provinces` filtered to `adm0_a3 = CAN`, coordinates rounded to 4 decimals → `app/data-src/natural-earth/ca-provinces.geojson` (273 KB, committed) | Natural Earth v5.1.2, `https://github.com/nvkelso/natural-earth-vector/tree/v5.1.2/geojson`; terms `https://www.naturalearthdata.com/about/terms-of-use/` | Public domain | Optional; we show "Made with Natural Earth" | None. 1:50 million generalisation; not for legal or cadastral use. Replace with Statistics Canada boundaries in Phase 2 (`STATCAN-PR`). |
| NE-PLACES | Principal cities: `ne_10m_populated_places_simple`, Canadian capitals and places with `pop_max ≥ 100000` → 31 `city` records in `knowledge-base/places/` | Natural Earth v5.1.2 (same repository and terms) | Public domain | Optional; covered by "Made with Natural Earth" | None. Points are representative at 1:10 million; population fields are not reproduced. |
| KB | Knowledge-base records of Agents 01–05 (`knowledge-base/**`), converted to GeoJSON by `build-data.mjs` | This project | Each record lists its own sources and licences in `sources[]`; the profile panel shows them | Per record, shown in the profile panel; plus the OGL line below when records cite Government of Canada data | Prices, rents, tuition amounts and any `forecast` record are **not** written to static files (see ARCHITECTURE §4). |

Software libraries shipped in the bundle (licences only; no data):

| ID | Library | Licence |
|---|---|---|
| LIB-MAPLIBRE | MapLibre GL JS 6.x (`maplibre-gl`) | BSD 3-Clause |
| LIB-REACT | React 19, React DOM 19 | MIT |
| LIB-TAILWIND | Tailwind CSS 4 (build-time) | MIT |

Fonts in the user interface: the system font stack only (no web fonts are
downloaded). Images and photographs: **none** in Phase 1. When added, each
image gets a row here with its Wikimedia Commons (or equivalent) page, author
and licence; school, park and tourism photographs are linked to their
official source, not copied (SPEC §1.12).

## 2. Fallback when the base map is unavailable

If the OpenFreeMap style cannot be fetched within 6 seconds, the app switches
to a built-in style (`app/src/map/basemap.ts`, `FALLBACK_STYLE`): a plain
background plus the Natural Earth province polygons and the knowledge-base
layers. It makes no network request other than to the app itself, so it has
no base-map labels; city points are drawn without labels, and names appear on hover and in
the profile panel. No third-party demo tile servers are used as a fallback,
because their terms do not allow production use.

## 3. Attribution rendered on the map

Machine-read. Columns: `id`, `text` (plain text, shown verbatim), `url`
(linked), `when` (`always`, `layer:<layer id>` when that layer is on, or
`category:<category>` when at least one record of that category is loaded).

<!-- attribution:begin -->
| id | text | url | when |
|---|---|---|---|
| OSM | © OpenStreetMap contributors (ODbL) | https://www.openstreetmap.org/copyright | always |
| OFM-STYLE | Base-map style © OpenMapTiles (CC BY 4.0), after CARTO | https://openmaptiles.org/ | always |
| NE | Made with Natural Earth | https://www.naturalearthdata.com/ | always |
| OGL-CA | Contains information licensed under the Open Government Licence – Canada | https://open.canada.ca/en/open-government-licence-canada | category:clim |
| KB | Knowledge base: sources listed in each profile |  | always |
<!-- attribution:end -->

The OpenFreeMap / OpenMapTiles line comes from the tile source itself and is
rendered by MapLibre automatically.

## 4. Planned (not yet in the app; each needs its row moved to §1 when used)

| ID | What | Provider | Licence | Notes |
|---|---|---|---|---|
| STATCAN-PR | Provinces and territories, census subdivisions, census metropolitan areas — cartographic boundary files (2021 Census) | Statistics Canada | Open Government Licence – Canada | Phase 2 replacement for NE-ADMIN1; attribution "Source: Statistics Canada, … Reproduced and distributed on an 'as is' basis with the permission of Statistics Canada." plus the OGL line. Needs generalisation (mapshaper) for web size. |
| NRCAN-CDEM | Canadian Digital Elevation Model / HRDEM (hillshade, contours) | Natural Resources Canada | Open Government Licence – Canada | Phase 2 terrain; would be pre-rendered to raster or terrain-RGB tiles we host. |
| TERRAIN-RGB | An open terrain-RGB/terrarium tile source (for example the AWS Open Data "Terrain Tiles") | Various; check per source | Varies (attribution list per source) | Only if its licence and usage policy are recorded here first. |
| PARKS | Parks Canada and provincial protected-area datasets; Canadian Protected and Conserved Areas Database | Parks Canada; ECCC | Open Government Licence – Canada (provincial licences vary) | Phase 4 parks layer. |
| NEF | National Ecological Framework for Canada (ecozones, ecoregions) | Agriculture and Agri-Food Canada | Open Government Licence – Canada | Physical-geography layer. |
| STATCAN-WDS | On-demand rents and vacancy rates per CMA (tables 34-10-0133-01, 34-10-0130-01) via the Web Data Service | Statistics Canada, `https://www150.statcan.gc.ca/t1/wds/rest/` | Statistics Canada Open Licence | Phase 4; no key; cache 7 days per vector (Agent 02 METHODOLOGY §5). Attribution "Source: Statistics Canada, Table 34-10-0133-01 …" next to each figure. |
| BOC-VALET | Posted 5-year conventional mortgage rate, series V80691335 | Bank of Canada Valet API, `https://www.bankofcanada.ca/valet/` | Bank of Canada terms of use (free reuse with attribution) — confirm text before use | Phase 4 calculator pre-fill only; cache 24 h; never stored. |
| CREA-HPI, CMHC-RMR | MLS® Home Price Index tool; CMHC rental market reports | CREA; CMHC | Proprietary: republishing requires prior written consent (DECISIONS D-008) | **Link-out only.** `build-data.mjs` keeps `re` records without a Statistics Canada source out of every published file. |
| NOMINATIM | Geocoding (address search) | OpenStreetMap Foundation, `nominatim.openstreetmap.org` | ODbL data | Usage policy: max 1 request/second, valid User-Agent/Referer, no autocomplete, caching required. Use only on explicit user search, or self-host / use Photon. |
| ROUTING | Routing (OSRM / Valhalla / openrouteservice) | Varies | Varies | Phase 6; public demo servers are not for production; deep links to external navigation apps preferred. |
