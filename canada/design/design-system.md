# Design system — Canada Intelligence & Exploration System

Owner: Agent 06 (Principal UI/UX Designer). Version 1.0, 2026-10-30.
Applies to the map application in `map/app/` (Vite, React, TypeScript,
Tailwind v4, MapLibre GL JS). Companion files in this folder:

| File | What it is |
|---|---|
| `tokens.css` | CSS custom properties. Agent 05 imports it as-is. Names are a contract (§13). |
| `tailwind-theme.css` | `@theme inline` mapping so utilities like `bg-surface-1 text-ink` read the tokens. |
| `components.md` | Component inventory: props, states, accessibility, views. |
| `wireframes/*.html` | Low-fidelity, self-contained layouts for the six views. |
| `review-2026-10-30.md` | First review of Agent 05's work. |

Sections: 1 Direction · 2 Principles · 3 Typography · 4 Colour · 5 Space,
radius, elevation, motion · 6 Layout and navigation · 7 Map · 8 Provenance ·
9 Climate charts · 10 Comparison · 11 States · 12 Accessibility · 13 Icons,
imagery, asset licences, token changelog.

---

## 1. Direction

**Audience.** One household deciding where to settle in a country they have
not yet lived in. They are careful, not hurried; the stakes are high (a
family move, money, children's schooling); many facts are unknown to them,
and some are unknown to the system too (SPEC §0). They need to *trust* what
they see, *explore* freely, and *compare* without being steered by false
precision.

**Brand adjectives, ranked.** 1. **Evidenced** (every figure shows where it
came from) · 2. **Exploratory** (the map invites wandering) · 3. **Calm**
(no alarm, no hype). "Evidenced" wins every tie.

**Material world.** Canadian topographic map sheets (NTS 1:50 000) and the
Atlas of Canada: ink on off-white paper, colour reserved for features
(water, vegetation, contours), italic lettering for physical features,
spaced capitals for regions, and the sheet *margin* that states datum,
survey date and sources. ECCC climate normals tables (twelve columns,
station header, period). Surveyors' field notes.

**Emotional job.** Reassure through honesty; then invite exploration.

**Three directions considered**

- **A. Survey sheet (chosen).** Ink-and-paper chrome; the map and the data
  own the colour; sharp radii; Archivo (wide capitals for places, like atlas
  lettering) with Source Sans 3 for reading; signature: the *sheet margin*.
- **B. Field notebook.** Kraft tones, rounded cards, photo-led profiles,
  casual voice. Rejected: it depends on photography we may only link, not
  store (SPEC principle 12), and its tone undersells legal and immigration
  content.
- **C. Night atlas.** Dark-first, glowing markers on navy, monospace
  everywhere. Rejected: reads as an operations dashboard (the brief forbids
  dashboard aesthetics) and fails the brand-swap test.

**Pick: A**, because "evidenced" is the first adjective and the map-sheet
tradition is literally the visual language of stated provenance. It costs
B's warmth (we recover some through warm paper neutrals and the large place
name) and C's drama in dark mode (dark theme is fully designed, but light is
primary).

**Signature element — the sheet margin.** Every block that shows evidence
ends in a ruled marginalia strip, as on a map sheet: a 1px `--ce-ink-2`
rule, then 12px spaced small capitals: `SOURCE · PERIOD · STATION ·
ACCESSED · RECORD`. It is visible without hover, everywhere, at full
strength; it is the product's memorable feature and it implements SPEC
principle 6. No other decorative device competes with it.

**Banned-list departures.** No Inter/system default (Archivo + Source
Sans 3); no centred hero (the map is the hero); no three-card grids; no
glassmorphism over the map (opaque paper panels with shadow); no
same-card-for-everything (sections are divided by rules and type, cards only
for repeatable items such as schools); place names at display scale (36–56px).

---

## 2. Principles

1. **The map is the stage.** Chrome is ink and paper; colour belongs to
   data. Panels never cover more than 40% of the map on desktop; the map
   re-pads (`map.setPadding`) so the selection stays centred in what is
   visible.
2. **Provenance is never one click away.** Source, period, date and record
   ID sit in the sheet margin of each block, not in a tooltip.
3. **Absence is information.** Missing data is shown and named ("No data —
   no `re` record for this city"), never zero, never averaged, never a blank.
4. **Normals are not weather.** Climate visuals describe 30-year averages;
   nothing looks like a forecast (§9).
5. **Bands, not scores.** Comparison shows SPEC §4 ordinal bands as words
   plus a five-segment meter; a composite number appears only with its
   sensitivity range (§10).
6. **Progressive disclosure by zoom.** Country → province → city →
   neighbourhood: each zoom band shows only what is useful at that scale
   (§6.2, §7.3).
7. **Shape before colour.** Every map layer has a distinct marker shape; every
   status an icon and a word; every band a count. Colour reinforces, never
   carries alone.
8. **One accent, used for attention.** Survey vermilion marks selection,
   focus and the active state. It is never decorative and never a series
   colour.

---

## 3. Typography

### 3.1 Faces and licences

| Role | Face | Licence | Source / package | Fallback stack |
|---|---|---|---|---|
| Display (place names, view titles, province labels in UI) | **Archivo** variable (wght 100–900, wdth 62–125), Omnibus-Type | SIL Open Font License 1.1 | npm `@fontsource-variable/archivo` (package MIT, font OFL); upstream github.com/Omnibus-Type/Archivo | "Arial Narrow", "Helvetica Neue", Arial, sans-serif |
| Text and UI (body, controls, tables, charts) | **Source Sans 3** variable (wght 200–900), Adobe | SIL Open Font License 1.1 | npm `@fontsource-variable/source-sans-3`; upstream github.com/adobe-fonts/source-sans | "Segoe UI", system-ui, -apple-system, Roboto, sans-serif |
| Record IDs, coordinates, climate IDs | System monospace (no web font) | n/a (OS fonts) | — | ui-monospace, SFMono-Regular, Cascadia Mono, DejaVu Sans Mono, Menlo, Consolas |
| Map labels (inside the WebGL canvas) | **Noto Sans** Regular / Bold / Italic as served by the tile style's glyph endpoint | SIL Open Font License 1.1 | OpenFreeMap glyphs (verify font-stack names in the style JSON) | — |

Why: Archivo's width axis gives atlas-style spaced, wide capitals for place
names and a condensed cut for dense labels from one file; Source Sans 3 is a
humanist sans that stays legible at 12–13px, has true tabular figures and
complete French diacritics (é è ê ç œ ï), which Quebec and bilingual names
require. Self-host through npm (Fontsource): **never load fonts from a
third-party CDN** — that would send every visit to a third party (SPEC
principle 11 spirit). Use `font-display: swap` (Fontsource default).

Phase 2 option: generate Archivo glyph PBFs with `maplibre/font-maker` and
self-host them so map labels match the UI face. Until then map labels use
Noto Sans; do not request a font stack the glyph server lacks (labels
silently disappear).

### 3.2 Scale (ratio 1.25, 16px body)

| Token | Size | Use | Face / weight / tracking |
|---|---|---|---|
| `--ce-text-display` | clamp 36–56px | Place name in profile header | Archivo 700, `wdth` 112, uppercase, `--ce-tracking-display` |
| `--ce-text-2xl` | 32px | View titles (Compare, Search results) | Archivo 650, wdth 100 |
| `--ce-text-xl` | 25px | Panel section group titles | Archivo 600 |
| `--ce-text-lg` | 20px | Section titles in panels | Source Sans 3 600 |
| `--ce-text-base` | 16px | Body, descriptions | Source Sans 3 400, leading 1.5 |
| `--ce-text-sm` | 14px | Controls, secondary text, table body | Source Sans 3 400/600 |
| `--ce-text-xs` | 13px | Meta, badges, dense tables | Source Sans 3 500 |
| `--ce-text-2xs` | 12px | Sheet margin, chart ticks, eyebrows | Source Sans 3 600, uppercase or `font-variant-caps: all-small-caps`, `--ce-tracking-caps` |

Rules: maximum two faces on screen (mono is a utility for IDs only). Figures
in tables, chart ticks and the comparison grid use
`font-variant-numeric: tabular-nums`; large standalone values (stat tiles)
use proportional figures. Units follow values with a thin no-break space:
`25.0 °C`, `75 mm`, `131 cm`. Thousands follow the locale through
`Intl.NumberFormat`: `2,020 h` in English, `2 020 h` (narrow no-break space)
in French.
Negative temperatures use the true minus sign `−` (U+2212), not a hyphen.

French names: when a record has `name_fr`, show it beneath the English name
in Source Sans 3 italic, `lang="fr"`. For Quebec places whose official name
is French, the French name leads.

---

## 4. Colour

### 4.1 Logic

60–30–10: paper surfaces (60) · ink text and rules (30) · colour (10),
where the 10 is almost entirely **data**: map-layer domain hues, climate
chart marks and status. The single chrome accent is survey vermilion. Gray
temperature is warm throughout (paper, graphite ink); no pure black or white.

### 4.2 Palettes (values in `tokens.css`)

| Role | Light | Dark | Use |
|---|---|---|---|
| bg | `#ece9e1` | `#0f0f0d` | App plane |
| surface-1 | `#fbfaf6` | `#1a1917` | Panels, rail, popovers |
| surface-2 | `#f4f2ec` | `#23221f` | Inset, hover, headers, inputs |
| surface-3 | `#e9e6dd` | `#2d2c28` | Pressed, selected row |
| ink / ink-2 / ink-3 | `#1e1d1a` / `#4b4842` / `#6a665e` | `#ece9e2` / `#c2bdb2` / `#9c978c` | Text tiers |
| line / line-strong | `#ddd9cf` / `#8c877c` | `#34322d` / `#7d786d` | Hairline / control boundary |
| accent | `#b83f14` | `#f0875c` | Selection, focus, active |
| status info / good / warning / critical | `#2f5f8a` `#2e6b34` `#855400` `#a82820` | `#8db8e0` `#84c98c` `#e8b85a` `#f08a80` | With icon + label only |

Dark mode is its own palette, not an inversion: lighter surfaces mean higher
elevation, accents are lightened and desaturated, shadows deepen but carry
less of the hierarchy.

### 4.3 Map-layer domain hues

Four hues for four domains, plus neutral ink for settlement, transport and
heritage (distinguished by shape, §7.2). Validated with the dataviz
palette validator in all-pairs mode (a map is a scatter):

| Domain | Token | Light | Dark |
|---|---|---|---|
| Climate | `--ce-layer-climate` | `#2a78d6` | `#3987e5` |
| Nature (parks, trails, natural attractions) | `--ce-layer-nature` | `#16692c` | `#237d3c` |
| Education (verified schools) | `--ce-layer-education` | `#b03a8f` | `#c05cb0` |
| Housing (real estate) | `--ce-layer-housing` | `#eda100` | `#cf9a00` |
| Settlement | `--ce-layer-settlement` | `#1e1d1a` | `#ece9e2` |
| Transport, heritage | `--ce-layer-transport`, `--ce-layer-heritage` | `#4b4842` | `#c2bdb2` |

Validator results (surface = basemap land):

- Light, surface `#f2efe9`, `--pairs all`: lightness band PASS, chroma PASS,
  **CVD PASS** (worst education↔climate ΔE 12.6 deutan), normal-vision PASS
  (23.3), contrast WARN for housing amber (1.89:1) — relief: every marker
  carries a 1.5px `--ce-marker-stroke` ring (14.7:1), so the amber never
  stands alone.
- Dark, surface `#26251f`, `--pairs all`: **CVD PASS** (worst ΔE 9.2
  protan), normal-vision PASS; lightness band flags housing `#cf9a00` at
  L 0.717 (band 0.48–0.67) — accepted for map markers because the ring and
  shape carry identity; nature `#237d3c` is 2.98:1 on that surface, 3.23:1 on
  the dark basemap land `#1f1e1b` — passes 3:1 on the real basemap.
- Seven separate hues (one per layer) were tried and failed all-pairs CVD in
  every variant; that is why layers share domain hues and rely on shape.

### 4.4 Contrast table (WCAG 2.2, computed 2026-10-30)

Text needs 4.5:1 (SC 1.4.3); UI boundaries and meaningful graphics 3:1
(SC 1.4.11).

| Pair | Light | Dark | Need |
|---|---|---|---|
| ink on surface-1 / 2 / 3 | 16.14 / 15.06 / 13.51 | 14.49 / 13.12 / 11.53 | 4.5 |
| ink on bg | 13.89 | 15.83 | 4.5 |
| ink-2 on surface-1 / 2 | 8.72 / 8.14 | 9.38 / 8.50 | 4.5 |
| ink-3 on surface-1 / 2 / 3 | 5.47 / 5.10 / 4.58 | 6.04 / 5.47 / 4.80 | 4.5 |
| line-strong on surface-1 / 2 | 3.42 / 3.19 | 4.00 / 3.62 | 3 |
| accent on surface-1 (text and UI) | 5.35 | 6.96 | 4.5 |
| accent on surface-2 | 4.99 | 6.31 | 4.5 |
| accent on map land | 4.87 | 6.61 | 3 |
| on-accent on accent | 5.46 | 7.50 | 4.5 |
| accent on accent-soft | 4.63 | 5.85 | 4.5 |
| status info / good / warning / critical on its soft | 5.62 / 5.41 / 5.49 / 5.63 | 7.02 / 7.56 / 7.88 / 6.36 | 4.5 |
| status info / good / warning / critical on surface-1 | 6.43 / 6.15 / 6.16 / 6.73 | 8.42 / 8.96 / 9.57 / 7.24 | 4.5 |
| chart cold / warm on surface | 4.23 / 4.37 | 6.23 / 6.39 | 3 |
| chart precip / snow / sun on surface | 5.11 / 3.93 / 4.03 | 7.03 / 8.35 / 7.81 | 3 |
| chart reference (0 °C) | 8.72 | 9.38 | 3 |
| marker climate / nature / education on land | 3.85 / 5.92 / 4.76 | 4.58 / 3.23 / 4.29 | 3 |
| marker climate on water | 3.18 | 4.02 | 3 |
| marker stroke (ink) on land / water | 14.69 / 12.15 | 13.75 / 12.08 | 3 |

`--ce-chart-axis` (1.98 / 2.25) and `--ce-chart-grid` are decorative: every
axis carries labelled ticks in `--ce-ink-3`, so the rule itself conveys
nothing that is not also in text. `--ce-ink-disabled` is exempt (SC 1.4.3,
inactive components).

Re-check with `node <dataviz>/scripts/validate_palette.js` and a WCAG
contrast calculator whenever a value changes, and update this table.

---

## 5. Space, radius, elevation, motion

**Spacing.** 4px base, 8px rhythm: `--ce-space-{0-5,1,2,3,4,5,6,8,10,12,16}`
= 2 4 8 12 16 20 24 32 40 48 64 px. Equals Tailwind v4's default
`--spacing: 0.25rem`, so `p-4` = `--ce-space-4`. Internal ≤ external: a
section's padding (24) exceeds the gap between its rows (12); cards in a list
have 16 padding and 12 gap only when separated by a rule, otherwise 16 gap.
Panel padding 24 desktop, 16 mobile.

**Radius (map-sheet sharp).** none 0 · xs 2 (badges, meter segments, bar
ends) · sm 4 (inputs, buttons, chips) · md 6 (cards, popovers) · lg 8
(floating panels over the map) · full (clusters, toggles). Children have a
smaller radius than their parents.

**Elevation.** `--ce-shadow-1` controls on the map · `-2` rail, map controls
· `-3` profile panel, popovers, search results · `-4` modal, mobile sheet at
full height. Shadows are tinted with the warm ink; in dark mode surfaces get
lighter (surface-2, -3) as they rise, and shadows are secondary.

**Motion.** Every animation answers "where did this come from" or "what
changed".

| Token | Value | Use |
|---|---|---|
| `--ce-duration-instant` | 80ms | hover, press |
| `--ce-duration-fast` | 140ms | toggles, tooltips, layer fade-in |
| `--ce-duration-base` | 220ms | panel enter (translateX 24px + opacity) |
| `--ce-duration-slow` | 320ms | mobile sheet snap, comparison column add |
| `--ce-duration-exit` | 160ms | anything leaving — always faster |
| `--ce-duration-map` | 1200ms | `flyTo` between views (`essential: false`) |
| `--ce-ease-out` / `-in` / `-in-out` | cubic-beziers | enter / exit / move |

Only `transform` and `opacity` animate. Map camera: `flyTo` for view changes
(country → province → city), `easeTo` 400ms for small pans, never chained
animations. Layer toggles fade features in with `*-opacity-transition`
140ms. Under `prefers-reduced-motion: reduce` all durations are 0, the map
uses `jumpTo`, panels appear without travel, nothing pulses or loops.

---

## 6. Layout and navigation

### 6.1 Desktop shell (≥ 1024px; designed at 1440 × 900)

```
┌ top bar 56 ─ wordmark · breadcrumb (Canada › BC › Vancouver) · search ──── compare(n) · theme · About the data ┐
├ rail 64/296 ┬───────────────── map (MapLibre) ──────────────────────┬ profile panel 440 (560 ≥1536) ┤
│ layer groups│  scale bar · zoom ± · terrain toggle · attribution     │ header, tabs, sections,       │
│ = legend    │                                                        │ sheet margins                 │
├─────────────┴────────────────────── comparison tray (when ≥1 pinned) ┴───────────────────────────────┤
```

- **Layer rail = legend.** Each toggle shows the layer's marker shape in its
  colour, the name, and a count of features in view. One control, so the
  legend can never disagree with what is on.
- **Profile panel** docks right, overlays the map, and calls
  `map.setPadding({ right: panelWidth })` so the selection re-centres in the
  visible map. Closing restores padding.
- **Comparison tray** appears bottom-centre when a location is pinned
  ("Add to comparison"), holds up to four chips, and opens the comparison
  view.
- **Breadcrumb** is both "where am I" and zoom-out navigation.

### 6.2 Views are zoom bands, not pages

| View | Zoom (approx.) | Shows by default | Click does |
|---|---|---|---|
| Country | ≤ 4.5 | Provinces/territories (hover fill, label in spaced caps), tier-1 cities | Province → province view (fit bounds) |
| Province | 4.5–7 | Province selected outline, other provinces dimmed 40%, tier-1/2 cities, active layers clustered | City → city view |
| City | 7–11 | City marker selected, profile panel open, tier-3 towns, active layers unclustered as density allows | Feature → its profile |
| Neighbourhood | ≥ 11 | Neighbourhood outlines and labels, trails, trailheads | Neighbourhood → profile |

Selecting from search or the list flies the camera to the matching band.
Zooming manually changes the breadcrumb but does not open or close panels.

### 6.3 URL state

`?v=city&id=city-bc-vancouver&z=10.2&c=-123.12,49.28&l=cities,schools,parks&cmp=city-bc-vancouver,city-ns-halifax&theme=dark`.
Browser Back closes the panel before it moves the camera. Links are
shareable within the repository's deployment; no user-profile data ever goes
into the URL.

### 6.4 Breakpoints

| Width | Layout |
|---|---|
| ≥ 1536 | Panel 560, rail open by default |
| 1280–1535 | Panel 440, rail open |
| 1024–1279 | Panel 440, rail collapsed (64) by default |
| 768–1023 | Rail collapsed; panel overlays with scrim-free shadow; comparison max 3 columns |
| < 768 (designed at 360) | Mobile: full-bleed map, top search pill, Layers button → full-screen sheet, profile in a bottom sheet with snaps at 148px / 50% / 92%, comparison transposed (criterion cards) |

---

## 7. Map

### 7.1 Basemap

Muted vector basemap so data colour leads: OpenFreeMap **Positron** (light)
and its dark counterpart (Agent 05 to verify which dark style OpenFreeMap
serves, record it in `DATA-SOURCES.md`, keep a fallback style). Phase 2:
restyle land, water and labels to `--ce-map-land`, `--ce-map-water` and the
paper/ink neutrals via `setPaintProperty` so the map and the chrome share one
palette.

### 7.2 Layers, shapes, colours

Shapes are drawn at runtime from geometric primitives (no icon font, no
licence question): circle, ring, diamond, triangle, inverted triangle,
hexagon, pentagon, square, tag.

| # | SPEC §9 C layer | Token | Geometry on map | Point marker | Points appear from | Cluster | Default |
|---|---|---|---|---|---|---|---|
| 1 | Cities and towns | settlement | point + label | **circle**, 3 sizes by population tier (10/14/18px) | tier 1 z3, tier 2 z5, tier 3 z7 | no; collision by `symbol-sort-key` = population rank | on |
| 2 | Neighbourhoods | settlement | outline 1px + label | small **ring** 8px at centroid | z10 | no | on (appears at z10) |
| 3 | Physical geography and terrain | terrain-ink | hillshade + landform labels in *italic* | **triangle outline** (peaks) label only | z5 | no | off |
| 4 | Elevation and topography | terrain-ink | contours, hypsometric tint | — | contours z9 | — | off |
| 5 | Climate regions and climate information | climate | region fill 8% + 1px line; station markers | **ring with centre dot** (station symbol) | z4 | yes | off |
| 6 | Real estate | housing | CMA outline 1.5px; on-demand figure chip at centroid | **tag** (rounded rect with figure + date when fetched) | z6 | no | off |
| 7 | Verified alternative schools | education | point (only `qualifying`) | **diamond** | z3 (clustered) | yes | off |
| 8 | National and provincial parks | nature | polygon fill 14% + 1px line | **hexagon** | z4 | yes | off |
| 9 | Hiking trails | nature | line 2px, dash 2 2 (map convention for trails) | trailhead **inverted triangle** | z9 | yes (trailheads) | off |
| 10 | Natural attractions | nature | point | **triangle** | z5 | yes | off |
| 11 | Tourism and historical attractions | heritage | point | **pentagon** | z6 | yes | off |
| 12 | Transport and infrastructure | transport | emphasised basemap roads/rail; hubs | **square** | airports z4, stations z9 | no | off |

Marker anatomy (base 14px): fill = layer token · 1.5px ring
`--ce-marker-stroke` · 2px outer halo `--ce-marker-halo`. Generate one RGBA
image per (layer × theme) on a canvas at `pixelRatio: 2` and register with
`map.addImage`; re-generate with `map.updateImage` on theme change. (SDF
icons allow only one halo, which loses the ink ring that rescues the amber.)

Contextual visibility: never more than about 300 point markers in view; above
that a layer clusters. At country view only tier-1 cities and clusters.
Every layer row in the rail shows "n in view"; a layer with zero records says
so (§11).

### 7.3 Hover and selection

| State | Point marker | Region (province, park, CMA) |
|---|---|---|
| Default | 14px marker | 1px `--ce-map-region-line` |
| Hover | ring layer under the marker: circle radius 12, 2px `--ce-map-hover`; cursor pointer; label shown if hidden | `--ce-map-region-hover-fill`, line 1.5px ink (via `feature-state`) |
| Focused (keyboard, from list) | same as hover + label always shown | same as hover |
| Selected | 22px marker + **survey bracket**: four corner ticks (6px arms, 2px) in `--ce-map-selected` at 16px from centre; label bold | 2.5px `--ce-map-selected` outline + `--ce-map-region-selected-fill`; other regions dim 40% at province view |
| Pinned for comparison | small numbered tab (1–4) on the marker's upper right, ink on paper | — |

Hover uses `feature-state` on a circle layer (paint properties accept
feature-state; layout properties such as `icon-size` do not). Selection is a
separate symbol layer filtered to the selected id. Hover never opens
anything; click (or Enter on the list) selects.

### 7.4 Clusters

Per-layer GeoJSON sources with `cluster: true`, `clusterRadius: 48`,
`clusterMaxZoom: 12`. Cluster = paper disc (`--ce-map-cluster-fill`), 3px ring
in the layer colour, count in ink, Noto Sans Bold 12px, tabular. Diameter
steps 28 / 36 / 44px at counts < 10 / < 100 / ≥ 100; counts abbreviate
`1.2k`. Click → `getClusterExpansionZoom` then `easeTo`. A cluster's
accessible name: "12 schools, zoom in to see them".

### 7.5 Labels

Cartographic conventions: settlements upright ink with 1.5px halo
(`--ce-map-label-halo`); provinces in spaced capitals (`text-transform:
uppercase`, `text-letter-spacing: 0.15`) in `--ce-ink-3`; physical features
*italic* in `--ce-layer-terrain-ink`; water features *italic* in
`--ce-layer-water-ink`. Bilingual names: `name_en` on line one, `name_fr`
smaller on line two where they differ (Phase 2).

### 7.6 Terrain mode (layers 3 and 4)

A toggle on the map controls ("Terrain"). When on:

- Hillshade `hillshade-exaggeration` 0.35, shadow `--ce-map-hillshade-shadow`,
  highlight `--ce-map-hillshade-highlight`, illumination from the
  north-west (335°).
- Basemap land and landcover fills drop to 60% opacity so relief reads;
  roads stay.
- Marker halo widens from 2 to 3px and label halos from 1.5 to 2.5px; the
  cluster disc stays opaque. Text over relief must remain 4.5:1 against its
  halo, which it does because the halo is opaque paper.
- Contours `--ce-map-contour`, index contours every fifth line at 1px,
  others 0.5px, labelled in italic terrain ink at z12+.
- 3D terrain (`setTerrain`, pitch ≤ 60°) is optional and off by default;
  under reduced motion it never animates the pitch.

The terrain source and its licence come from Agent 05's `DATA-SOURCES.md`.

### 7.7 Controls and attribution

Bottom-right stack: zoom in/out (44px), compass (only when rotated),
"Terrain" toggle, "Reset to Canada". Scale bar bottom-left (metric).
Attribution bottom-right, always keyboard reachable, showing the strings from
`DATA-SOURCES.md`; expanded by default on desktop, compact (i) on < 768px.

### 7.8 Reading tokens into MapLibre

```ts
const css = () => getComputedStyle(document.documentElement);
export const token = (name: string) => css().getPropertyValue(name).trim();

export function applyMapTheme(map: maplibregl.Map) {
  map.setPaintProperty('provinces-line', 'line-color', token('--ce-map-region-line'));
  map.setPaintProperty('clusters-schools', 'circle-stroke-color', token('--ce-layer-education'));
  // … one call per themed paint property; regenerate marker images:
  // map.updateImage('marker-schools', drawMarker('diamond', token('--ce-layer-education')))
}
// Re-run on: matchMedia('(prefers-color-scheme: dark)').change, and on
// MutationObserver of <html data-theme>. Run after 'style.load'.
```

---

## 8. Provenance and data honesty

**Sheet margin** (the signature). At the foot of every evidence block
(profile section, chart, comparison cell expansion, school card):

```
──────────────────────────────────────────────────────────────── (1px ink-2)
SOURCE ECCC Canadian Climate Normals · PERIOD 1991–2020 · STATION EXAMPLE STATION 0000000
ACCESSED 2026-10-30 · RECORD clim-xx-example · ✓ VERIFIED (high)
```

12px, uppercase labels in `--ce-ink-3`, values in `--ce-ink-2`, record ID in
mono. Source names are links to the source URL (underlined, open in a new
tab with an external-link icon and "(opens in new tab)" for screen readers).
Multiple sources: first source shown, "+2 sources" expands inline.

**`data_kind` badge** (typographic, colour-independent): `Official fact`
solid 1px border · `Estimate`, `Assumption`, `Forecast` dashed border ·
`Interpretation`, `Subjective` dotted border. Text 13px ink-2. Shown next to
every value or section title whose kind is not `official_fact`.

**Verification badge**: icon + word — verified (check, good) · partially
verified (half-circle, info) · unverified (circle-dashed, ink-3) · disputed
(alert-triangle, warning, links to the `DECISIONS.md` entry) · outdated
(clock-alert, warning). Past `next_review`: "Due for review since <date>".

**Verification on every figure (coordinator requirement, 2026-10-30).**
Every displayed figure — a profile value, a stat tile, a comparison cell, a
search-result fact — carries its record's `verification.status` next to it,
not only in the margin: a 16px Lucide icon plus the word, never colour
alone. Compact form in dense cells: icon + short word ("Verified",
"Partial", "Unverified", "Disputed", "Outdated"); the full word and
confidence are in the tooltip and the margin. `verified` may be shown as the
icon alone *only* inside a block whose margin states "Verified (high)";
every other status always shows its word. **Disputed** values (for example
the Manitoba tax thresholds in Phase 1) get the warning badge "Disputed"
linked to the `DECISIONS.md` entry, and the figure itself is set in ink-2
with a dotted underline so it is not read as settled. Records whose notes
carry a caution (for example the territorial doctor-access figures) show an
info badge "Use with caution" whose tooltip quotes `verification.notes`.

**Market figures (D-008).** Every price, rent or market metric carries:
(1) a **figure-kind label** from the record's `figure_kind` — *Survey*,
*Asking*, *Transaction*, *Index* or *Estimate* — as a typographic badge
before the value ("Survey · $1,850 / month"); asking prices and estimates
use the dashed border, survey, transaction and index the solid border;
(2) the period and "as of" date in the margin; (3) a **staleness badge**
"Older than 60 days" (warning, clock icon) when the data period ends more
than 60 days before today (SPEC §2.7). Figures whose only sources are CREA
(MLS® HPI) or CMHC are **not displayed from storage**: the slot shows the
metric, period and figure kind with a link "View on the CREA HPI tool"
(external-link icon) and the line "Not republished here: the publisher's
terms do not allow it." Two-bedroom survey rents republished by Statistics
Canada under its open licence may be displayed, with Statistics Canada
named as the source.

**On-demand figures** (rents, prices — SPEC §9 B, E): never pre-rendered.
The slot shows "Fetch current figure" (secondary button) → loading line
"Fetching from <publisher>…" with Cancel → value with "as of <date>,
<source>" in the margin. A snapshot older than 60 days (SPEC §2.7) shows a
warning badge "Older than 60 days".

**Disagreements** between agents: both values shown in the block, each with
its margin, and a note "Sources disagree — see DECISIONS D-0xx".

---

## 9. Climate charts (normals)

Data: `clim` records (`climate-normals.schema.json`).

### 9.1 Form

Small multiples on one shared month axis (Jan → Dec, always starting in
January — never "from this month"), stacked vertically in this order. **No
dual axis**: temperature and precipitation are never drawn on one plot with
two scales (the classic climograph is ruled out).

1. **Temperature (°C).** For each month a floating range bar from `tmin_c`
   (mean daily minimum) to `tmax_c` (mean daily maximum), 10px wide with 2px
   rounded ends; a 2px horizontal tick at `tmean_c` in `--ce-chart-mean`.
   The part of a bar below 0 °C is `--ce-chart-cold`, at or above is
   `--ce-chart-warm`; a labelled `0 °C` reference line in
   `--ce-chart-reference` makes the split readable without colour. Height
   160px.
2. **Precipitation (mm).** Bars of `precip_mm` (total, water equivalent),
   `--ce-chart-precip`, baseline at 0. Height 88px.
3. **Snowfall (cm).** Bars of `snow_cm`, `--ce-chart-snow`. Own panel because
   snowfall is a depth in cm and precipitation a water equivalent in mm;
   never stacked together. Omitted entirely if every month is null; months
   of `0` draw a 1px baseline tick (zero is data, null is not). Height 88px.
4. **More measures** (collapsed accordion): sunshine hours (`sunshine_h`,
   only if ≥ 10 months present), days with precipitation, end-of-month snow
   depth, humidity, wind, and `daylight_h_computed` labelled "computed from
   latitude, not observed".

Each panel: title with unit in the title ("Precipitation, mm"), 3–4 y ticks
in `--ce-ink-3`, solid hairline grid, 2px surface gap between bars, direct
label only on the maximum and minimum month. Comparing cities: same y-domain
for every city's temperature panel (SPEC §8 B: consistent table), shown as
columns of small multiples, never as overlaid lines in different colours.

### 9.2 What is always visible (never only in a tooltip)

- Chart title: **"Climate normals, 1991–2020"** with the sub-line
  "30-year averages, not a forecast".
- Station line: station name, climate ID, elevation, distance to city centre.
- Sheet margin: source (ECCC Canadian Climate Normals, linked), period,
  accessed date, record ID, verification.
- If `normals_period` is `1981-2010` or `1971-2000`: an info badge "Older
  period" with "ECCC has not published 1991–2020 normals for this station."
- If `distance_to_city_centre_km` > 10 or the station is an airport: "Station
  is N km from the centre; airport stations can be cooler or windier."
- Units in every panel title; table headers repeat them.

### 9.3 Never

Weather pictograms (sun, cloud, raindrop icons) on months; a "today" or
current-month highlight; day names or calendar dates; the words "expected",
"will", "forecast", "chance of"; gradients or animated drawing that imply
a trend over time; lines connecting months across a null; interpolated
values; a single provincial average presented for a city.

### 9.4 Missing data

A null month leaves its slot empty with a 45° hatch in `--ce-chart-missing`
at 30% height and the label "–" under the axis; the table shows "—" with the
footnote "Not published by ECCC for this station". Annual figures are never
recomputed by the app from partial months; show the record's `annual` values
or "—".

### 9.5 Interaction and alternatives

- Hover or keyboard focus on a month highlights a full-height month column
  (surface-3, 60%) across all panels and shows one tooltip with every
  measure of that month. The chart group is focusable; ← → move by month;
  Home/End jump to January/December; the tooltip text is mirrored in an
  `aria-live="polite"` region.
- **Chart | Table** segmented control above the chart. The table is the full
  equivalent: 12 rows, columns High, Low, Mean (°C), Precip (mm), Rain (mm),
  Snow (cm), Sun (h), tabular numerals, right-aligned, sticky header.
- Annual stat strip under the chart (only non-null): Mean °C · Precipitation
  mm · Snowfall cm · Days > 30 °C · Days < −20 °C · Frost-free days.
- Seasons: four rows (Winter Dec–Feb, Spring Mar–May, Summer Jun–Aug,
  Autumn Sep–Nov) from `seasonal_summary`, each with the `Interpretation`
  badge because the text is Agent 04's reading of the normals.

---

## 10. Comparison (SPEC §4)

### 10.1 Structure

- Two to four locations of the same kind (city with city, neighbourhood with
  neighbourhood, province with province). Mixing kinds is allowed with a
  warning chip "Different scales: province vs city".
- Grid: criteria as rows (sticky first column), locations as columns (sticky
  header with name, province, and "n of 11 criteria rated").
- Criteria (SPEC §4.1): Affordability, Climate, Physical environment and
  natural beauty, Hiking and recreation, Employment, Healthcare, Education
  (alternative schools), Safety, Transportation, Immigration feasibility,
  Overall quality of life. Added criteria append with their decision ID.

### 10.2 Cell anatomy

```
Strong                         ← band word, 14px semibold ink
▮▮▮▮▯                          ← 5-segment meter, filled = band (1–5), 8×4px segments, 2px gaps
3 records · data 2025-10       ← evidence count (button) · data date, 12px ink-3
✓ Verified  [Survey]           ← weakest verification.status among the evidence (icon + word)
                                  · figure kind for market criteria · data_kind badge if not official_fact
[Older than 60 days]           ← staleness badge when a market figure's period is > 60 days old
```

The cell shows the **weakest** verification status among its evidence
records (order: disputed < outdated < unverified < partially verified <
verified), so one disputed record cannot hide behind verified ones; the
expanded evidence list shows each record's own status. A band resting on a
disputed record also gets the row chip "Disputed evidence".

Expanding the evidence count lists record IDs (mono, linked to their
profiles) and the band thresholds used ("How this band is set").

**Band words.** Default five: *Very weak · Weak · Moderate · Strong · Very
strong*, meaning favourability on that criterion. A criterion may define its
own five words (for example climate winter severity *Very harsh · Harsh ·
Moderate · Mild · Very mild*) in its threshold document; the meter position
keeps the order comparable. No decimals, no stars, no traffic-light colours:
the meter is monochrome `--ce-band-fill` on `--ce-band-track`.

### 10.3 Missing data (explicit)

- A criterion without a record shows **"No data"** in ink-3 italic, a
  hatched empty meter (`--ce-band-nodata`), and the reason: "No `re` record
  for this city yet".
- Never zero, never an average of other columns, never a hidden row.
- Column header tally: "8 of 11 rated · 3 no data". A location with fewer
  than half the criteria rated shows a warning "Too little evidence to
  compare fairly".
- "Show differences only" hides rows where all bands are equal; rows with any
  "No data" are never hidden by it.
- If data dates in one row differ by more than 12 months, the row shows a
  chip "Dates differ" with the dates on expand. Climate rows also show each
  column's normals period and warn "Periods differ" when they do.

### 10.4 Weights, gates, order, sensitivity

- **Until the user's weights exist** (OPEN-QUESTIONS #10): banner "Weights
  not set — bands are shown unweighted. Columns are in the order you added
  them; this is not a ranking." No rank, no composite.
- **With weights:** a Weights drawer (one row per criterion: Essential /
  Strong / Flexible / Ignore, each with the minimum band for essentials).
  Columns reorder by weighted order and show "Rank 2 · range 1–3 when any
  weight moves one step". A composite figure, if shown at all, is always
  "Composite 3.6 (range 3.2–3.9)".
- **Essential gate failed:** column header shows a critical icon and "Fails
  essential: Affordability (needs Moderate or better)"; the column is
  de-emphasised (values ink-3, meter 40% opacity) and moved to the end, but
  stays visible with "Remove from shortlist". It is never silently dropped.
- **Sensitivity panel:** for each criterion, "Raise one step / Lower one
  step" shows whether the order changes ("Order stable" or "Halifax and
  Victoria swap"). Robust conclusions are labelled as such.

---

## 11. Empty, loading and error states

| Situation | Treatment |
|---|---|
| Layer with zero records (expected in Phase 1) | Rail row: shape glyph at 40% + "No records yet" badge; toggling on shows an inline note under the row: "No verified schools in the knowledge base yet. Research is in progress (Agent 03)." Map unchanged; no toast. |
| Layer with records but none in view | Row count "0 in view" + "Zoom out" link that fits the layer's bounds |
| Profile section with no data | Section omitted, but the profile ends with "Not yet researched for this place: Residential, Education" so absence is explicit |
| Search with no results | "No places or records match 'xyz'." + suggestions: check spelling, search a province, or try a concept ("mild winters"). Show the nearest name match if edit distance ≤ 2. |
| Concept search with unmet criteria | Results list states which criteria had no evidence ("Rents: no data for 9 of 12 results") instead of silently ignoring them |
| Comparison with < 2 locations | Tray shows "Add one more place to compare" with a pick-from-search button |
| Initial load | Paper background with the Canada outline drawn by the map as soon as the style loads; a 2px indeterminate bar under the top bar appears only after 300ms |
| Profile loading | Real section headings with static tonal blocks (no shimmer) at the expected heights; header shows the name immediately from the clicked feature |
| On-demand fetch | Inline "Fetching from CMHC…" + Cancel; keep the previous render at 50% opacity on refetch, no skeleton flash |
| Base style fails | Switch to the fallback style; a non-blocking notice "Base map unavailable from <provider>; showing a simplified map." with Retry |
| Data file fails (`*.geojson`) | Rail row error: critical icon + "Couldn't load schools data" + Retry; other layers unaffected |
| On-demand fetch fails | In the section: what happened ("CMHC didn't respond"), why if known, what now ("Try again, or open the source"); never show an undated old figure |
| Offline | Top-bar notice "Offline — showing data already loaded"; disable fetch buttons with the reason |
| Stale record | Warning badge "Due for review since <date>" in the margin |

Copy rules: name the outcome on buttons ("Add to comparison", "Fetch current
rents"), errors say what + why + what now, no exclamation marks.

---

## 12. Accessibility (WCAG 2.2 AA)

- **Keyboard path:** skip links ("Skip to search", "Skip to map", "Skip to
  places in view") → top bar → layer rail → map → **Places in view list** →
  profile panel. The map canvas is focusable (MapLibre keyboard handler:
  arrows pan, +/− zoom, Shift+arrows rotate — rotation disabled by default).
- **Places in view list** is the accessible equivalent of the markers:
  a list (≤ 50 items, sorted by layer then name) that updates on `moveend`,
  each item a button that selects the feature; collapsible on desktop, a tab
  on mobile. Canvas markers are not focusable, so this list is required.
- **Focus:** `:focus-visible` ring 2px `--ce-focus-ring` with 2px
  `--ce-focus-offset`, never removed. Opening the profile moves focus to its
  heading; Escape closes it and returns focus to the invoking control
  (SC 2.4.3). The profile panel must not cover the focused list item
  (SC 2.4.11): use `scroll-margin` and map padding.
- **Targets:** 44 × 44px minimum for every control (dense 32px controls get
  padded hit areas). Exceeds SC 2.5.8 (24px).
- **Dragging alternatives (SC 2.5.7):** map pan has buttons and keys;
  comparison column reorder uses "Move left/right" buttons; the mobile sheet
  has a tappable handle that cycles snaps.
- **Reduced motion:** honoured globally through tokens (§5); `jumpTo` instead
  of `flyTo`.
- **Colour independence:** shapes per layer, icon + word per status, meter
  count per band, 0 °C line for temperature, text badges for data kinds.
- **Screen readers:** `aria-live="polite"` region announces "Schools layer
  on, 12 in view", search result counts and selection ("Vancouver, British
  Columbia, selected"). Charts have `role="group"` with an `aria-label`
  summarising period and station, plus the table view. French names carry
  `lang="fr"`.
- **Reflow:** usable at 320 CSS px and 400% zoom (mobile layout).
- **Forced colours:** tokens fall back to system colours (see `tokens.css`).
- **Consistent help (SC 3.2.6):** "About the data" stays in the top bar on
  every view.

---

## 13. Icons, imagery, asset licences, token changelog

**Icons:** Lucide (`lucide-react`), **ISC licence**. One family only, 1.5px
stroke at 20px, sizes 16 / 20 / 24, `currentColor`. Icon-only buttons have
`aria-label` and a tooltip. No emoji anywhere in the UI.

**Map markers and brackets:** drawn at runtime from geometric primitives;
self-produced, no third-party licence.

**Photographs:** official school, park and tourism photos are **linked**
to their source (thumbnail not stored). Openly licensed images (Wikimedia
Commons) show author, licence (for example CC BY-SA 4.0) and source link in
the caption. No image without a licence line in `map/DATA-SOURCES.md`.
**Placeholder when no image exists:** a "location plate" — the place name in
Archivo wide capitals over a `--ce-surface-2` field with the coordinates in
mono and a faint 1px graticule; never a grey box with a picture icon.

**Asset licence summary**

| Asset | Licence |
|---|---|
| Archivo | SIL OFL 1.1 |
| Source Sans 3 | SIL OFL 1.1 |
| Noto Sans (map glyphs) | SIL OFL 1.1 |
| Fontsource npm packages | MIT (packaging) |
| Lucide icons | ISC |
| Markers, brackets, placeholders | Self-produced (this lane) |
| Wireframes in `wireframes/` | Self-produced; no external assets |

**Token changelog** (names are stable; any rename or removal is listed here
with a date and the replacement, and stays aliased for one phase):

- 2026-10-30 — v1.0, initial set.
- 2026-10-30 (b) — value only: dark `--ce-marker-halo` `#ece9e2` → `#0f0f0d`.
  With a light halo, the light settlement fill and dark stroke read as a
  bullseye, confusable with the ring-dot climate marker (re-review R-2). On
  the dark basemap every layer fill already clears 3:1 against land
  (§4.4), so a dark halo loses no contrast; outline shapes (ring,
  ring-dot, triangle-outline) now fill dark.
