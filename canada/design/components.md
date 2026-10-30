# Component inventory — for Agent 05

Owner: Agent 06. Version 1.0, 2026-10-30. Rules live in `design-system.md`
(§ numbers below point there); tokens in `tokens.css`; layouts in
`wireframes/`. Names match Agent 05's existing files where one exists
(`MapView`, `LayerPanel`, `ProfilePanel`, `ClimateChart`, `SearchBox`);
new components are marked **new**. Phase marks what Phase 1 needs (P1) and
what can wait (P2).

Conventions for every component:

- Styling only through tokens (Tailwind utilities from `tailwind-theme.css`
  or `var(--ce-*)`); no raw hex.
- Icons: Lucide (`lucide-react`, ISC), 16/20/24px, `currentColor`; icon-only
  buttons have `aria-label` and a tooltip. No emoji, including "✕" and "✓"
  as text — use Lucide `X` and `Check`.
- Every interactive element: 44 × 44px hit area, `:focus-visible` ring
  (`outline-2 outline-focus outline-offset-2`), states default / hover /
  active / focus / disabled.
- Motion via `--ce-duration-*`; reduced motion handled by tokens.

Views key: **C** country · **P** province · **Ci** city profile · **N**
neighbourhood · **Cmp** comparison · **S** search · **M** mobile.

---

## 1. Shell and navigation

### AppShell (new, P1)
- **Purpose:** grid of TopBar, LayerRail, MapView, ProfilePanel, ComparisonTray; owns URL state (§6.3).
- **Props:** `children`; reads `useUrlState()` → `{ view, id, z, c, layers, cmp, theme }`.
- **States:** desktop (≥1024), tablet (768–1023, rail collapsed), mobile (<768, sheet layout).
- **A11y:** landmarks `header`, `nav` (rail), `main` (map), `aside` (profile); `SkipLinks` first in DOM.
- **Views:** all.

### SkipLinks (new, P1)
- **Purpose:** "Skip to search", "Skip to map", "Skip to places in view".
- **Props:** `targets: { id: string; label: string }[]`.
- **States:** hidden until focused, then a paper chip top-left.
- **Views:** all.

### TopBar (new, P1)
- **Purpose:** wordmark, Breadcrumb, SearchBox, Compare button with count, ThemeToggle, "About the data".
- **Props:** `compareCount: number; onOpenCompare(); onOpenAbout()`.
- **States:** default; mobile collapses to the search pill + Layers button (wireframe 06).
- **A11y:** `header`; Compare button announces count ("Compare, 3 places").
- **Views:** all.

### Breadcrumb (new, P1)
- **Purpose:** "where am I" + zoom-out: Canada › Province › City › Neighbourhood.
- **Props:** `trail: { label: string; onSelect?: () => void }[]`.
- **States:** last item is current (`aria-current="page"`, not a link).
- **A11y:** `nav aria-label="Location"`.
- **Views:** C, P, Ci, N, Cmp.

### ThemeToggle (new, P1)
- **Purpose:** OS / Light / Dark; sets or removes `data-theme` on `<html>`, stores the choice in `localStorage` (try/catch).
- **Props:** `value: 'os'|'light'|'dark'; onChange(v)`.
- **States:** three-way segmented control; map re-reads tokens on change (§7.8).
- **A11y:** `role="group"` of `aria-pressed` buttons.
- **Views:** all.

### LiveAnnouncer (new, P1)
- **Purpose:** single `aria-live="polite"` region for layer toggles, selection, search counts.
- **Props:** `announce(text: string)` via context.
- **Views:** all.

### AboutDataDialog (new, P1)
- **Purpose:** licences and attribution (from `DATA-SOURCES.md`), validator summary, method links, how bands are set. Consistent-help location (WCAG 3.2.6).
- **Props:** `open; onClose; attribution: AttributionEntry[]; validator: string`.
- **States:** closed / open. Modal 640px, focus-trapped, Escape closes, focus returns.
- **Views:** all.

---

## 2. Map

### MapView (exists, P1)
- **Purpose:** MapLibre canvas, base style, boundaries, knowledge-base layers, hover and selection.
- **Props (keep current, add):** `padding: { right: number; bottom: number }` (from panel/sheet size, applied with `map.setPadding`); `theme: 'light'|'dark'`; `onViewChange(view: 'country'|'province'|'city'|'neighbourhood', zoom)`; `onFeaturesInView(list: IndexEntry[])` on `moveend`.
- **States:** loading style · basemap fallback · ready · terrain on · reduced motion (jumpTo).
- **A11y:** container `role="region" aria-label="Map of Canada"`; MapLibre keyboard handler on; markers are not focusable, so **PlacesInViewList is required**. Hover tooltip must not be `role="status"` (it would announce on every mouse move); announce selection instead.
- **Views:** C, P, Ci, N, S (results), M.

### Map layer specification (P1)
Per layer from `layers.config.json`, add two fields: `shape` and `minzoom`.

| id | shape | minzoom | cluster |
|---|---|---|---|
| cities | circle (3 sizes by `rank`/population tier) | tier 1: 0, 2: 5, 3: 7 | no |
| neighbourhoods | ring | 10 | no |
| physical | triangle-outline (labels italic) | 5 | no |
| elevation | — (raster) | — | — |
| climate | ring-dot | 4 | yes |
| real-estate | tag | 6 | no |
| schools | diamond | 0 | yes |
| parks | hexagon | 4 | yes |
| trails | inverted triangle (+ dashed line) | 9 | yes |
| natural | triangle | 5 | yes |
| tourism | pentagon | 6 | yes |
| transport | square | 4 | no |

Render points as a `symbol` layer with runtime images (`drawMarker(shape, fill, stroke, halo)` on a canvas at `pixelRatio: 2`, registered with `map.addImage`, refreshed with `map.updateImage` on theme change). Hover: separate `circle` layer with `feature-state` hover ring. Selection: `symbol` layer filtered by id showing the survey bracket image.

### MarkerGlyph (new, P1)
- **Purpose:** one source of truth for marker shapes: draws to canvas for MapLibre and renders as inline SVG for the legend, search results and chips, so legend and map always match.
- **Props:** `shape: 'circle'|'ring'|'ring-dot'|'diamond'|'triangle'|'triangle-down'|'triangle-outline'|'hexagon'|'pentagon'|'square'|'tag'; colorToken: string; size?: 10|14|18|22; state?: 'default'|'hover'|'selected'|'muted'`.
- **States:** default 14px · hover 18px · selected 22px + bracket · muted 40% opacity (empty layer).
- **A11y:** decorative in lists (`aria-hidden`); the row text names the layer.
- **Views:** all.

### LayerPanel → LayerRail (exists as LayerPanel, P1)
- **Purpose:** the twelve layers grouped (Places, Living, Nature, Environment, Visiting & moving), doubling as the legend.
- **Props:** `layers: LayerDef[]; layersOn; countsInView: Record<string, number>; countsTotal; onToggle(id); collapsed: boolean; onCollapse()`.
- **Row (LayerToggleRow):** MarkerGlyph · label · "n in view" / "No records yet" / "zoom 9+" · switch.
- **States per row:** off · on · on-empty (inline note with the layer's `emptyNote`) · on-zero-in-view ("0 in view · Zoom to layer") · loading (spinner-free: "Loading…" text) · error (critical icon + "Couldn't load" + Retry).
- **A11y:** each row is a `role="switch"` (or checkbox) with an accessible name "Parks, 27 in view"; group headings are `h3`; collapsed rail shows glyphs with tooltips and keeps names via `aria-label`.
- **Views:** C, P, Ci, N; on M as a full-screen sheet.

### MapControls (new, P1)
- **Purpose:** zoom ±, Terrain toggle, Reset to Canada, compass only when rotated.
- **Props:** `onZoomIn; onZoomOut; terrain: boolean; onTerrain(v); onReset()`.
- **States:** default · pressed (terrain) · disabled (zoom limit).
- **A11y:** 44px buttons with labels; replaces MapLibre's NavigationControl so icons follow tokens in dark mode.
- **Views:** all map views.

### HoverCard (new, P1)
- **Purpose:** name + kind + "Click to open" near the pointer; clusters: "12 schools — click to zoom in".
- **Props:** `x; y; title; meta?`.
- **States:** shown on hover / keyboard focus from PlacesInViewList; hidden on move.
- **A11y:** `aria-hidden` (selection is announced by LiveAnnouncer instead).
- **Views:** C, P, Ci, N.

### PlacesInViewList (new, P1)
- **Purpose:** keyboard and screen-reader equivalent of the markers on screen (§12).
- **Props:** `items: { id; name; layerId; shape; colorToken; km?: number }[]; onSelect(id); onHover(id|null)`.
- **States:** collapsed (button "Places in view (31)") · open list (≤ 50, sorted by layer then name) · empty ("Nothing in view. Zoom out or turn on a layer.").
- **A11y:** list of buttons; arrow keys move; Enter selects; focus/hover mirrors the map hover ring.
- **Views:** C, P, Ci, N; on M a tab in the layers sheet.

### Attribution (exists via MapLibre control, P1)
- **Purpose:** licence strings from `DATA-SOURCES.md`.
- **States:** expanded on ≥ 768px; compact "i" on mobile, **collapsed by default** on mobile so it does not cover the map; always keyboard reachable.
- **Views:** all map views.

### BasemapNotice (exists inline in App, P1)
- **Purpose:** non-blocking notice when the base style fails, with Retry.
- **States:** warning (fallback in use) · hidden.
- **A11y:** `role="status"`.

---

## 3. Profile

### ProfilePanel (exists, P1) / BottomSheet (new, P1 mobile)
- **Purpose:** the location profile (§9 B) on the right (440/560px) or in a mobile sheet with snaps 148px / 50% / 92%.
- **Props:** `selection; onClose; onAddToCompare(id); inCompare: boolean; onOpen(entry)`; sheet adds `snap: 'peek'|'half'|'full'; onSnap(s)`.
- **States:** loading (header from the clicked feature immediately, static tonal blocks below) · ready · error (what + why + Retry) · record missing.
- **A11y:** `aside aria-labelledby` the place heading; on open focus moves to the heading (`tabIndex={-1}`); Escape closes and **returns focus to the invoking element**; sheet handle is a button cycling snaps (no drag required).
- **Views:** P (province variant), Ci, N, M.

### ProfileHeader (new, P1)
- **Purpose:** eyebrow (kind · province · region), place name at `--ce-text-display` in Archivo wide capitals, French name (`lang="fr"`), VerificationBadge + DataKindBadge, actions.
- **Props:** `kind; name; nameFr?; placeLine; verification; dataKind; actions: ReactNode`.
- **Actions:** one primary "Add to comparison" (ink), secondary "Copy link", ghost "Close".
- **Views:** P, Ci, N, M.

### LocationPlate (new, P2)
- **Purpose:** art-directed placeholder when no openly licensed photo exists: graticule field + coordinates; or the linked photo with credit, licence, source.
- **Props:** `lat; lon; precision; photo?: { url; credit; licence; sourceUrl }`.
- **Views:** Ci, N, M.

### ProfileTabs (new, P1)
- **Purpose:** Overview · Geography · Climate · Living · Schools · Nature; only tabs with data are enabled.
- **Props:** `tabs: { id; label; hasData: boolean }[]; active; onChange`.
- **States:** active (vermilion 2px underline) · empty tab (disabled with "not yet researched" tooltip).
- **A11y:** WAI-ARIA tabs pattern (arrow keys, `aria-selected`, `aria-controls`).
- **Views:** P, Ci, N, M.

### ProfileSection (exists as `Section`, P1)
- **Purpose:** one evidence block: title, body, SheetMargin.
- **Props:** `title; kind?: DataKind; children; provenance: Provenance`.
- **Views:** P, Ci, N, M.

### SheetMargin (new, P1 — the signature)
- **Purpose:** provenance strip ending every evidence block (§8).
- **Props:** `sources: Source[]; period?: string; station?: { name; climateId }; accessed: string; recordId: string; verification?: Verification; asOf?: string`.
- **States:** single source · "+n sources" expanded · stale (past `next_review`: warning badge "Due for review since …") · disputed (link to DECISIONS entry).
- **A11y:** `<footer>` inside the section; labels are real text (not `::before`); external links say "(opens in new tab)" to screen readers.
- **Views:** every evidence block, all views.

### DataKindBadge, VerificationBadge (new, P1)
- **Purpose:** typographic badges (§8): data kind by border style (solid/dashed/dotted) + word; verification by Lucide icon + word.
- **Props:** `kind: DataKind` · `status; confidence`.
- **A11y:** text is the label; never colour alone.
- **Views:** all.

### NotYetResearched (new, P1)
- **Purpose:** closes the profile with "Not yet researched for this place: Schools · Trails · Rents", so omitted sections are explicit.
- **Props:** `missing: string[]`.
- **Views:** P, Ci, N, M.

### OnDemandFigure (new, P1 shell, P2 service)
- **Purpose:** rents/prices fetched on request (§8).
- **Props:** `label; request: () => Promise<{ value; unit; asOf; source }>`.
- **States:** idle ("Fetch current rents") · loading ("Fetching from CMHC…" + Cancel) · ready (value + margin with "as of") · stale > 60 days (warning) · error (what/why/next) · offline (disabled with reason) · not available yet (Phase 1: explains the service does not exist yet).
- **Views:** Ci, N, Cmp.

### MarketObservationList (new, P1)
- **Purpose:** groups `re` records under the city's "Living" tab (metric, property type, period, figure kind, source), instead of listing them as nearby places.
- **Props:** `records: IndexEntry[]` filtered to the city/CMA.
- **Views:** Ci.

### SchoolCard (new, P1)
- **Purpose:** one `qualifying` school: name, models, ages/grades, legal status, language, tuition (only via OnDemandFigure or with school year), website, linked official media, "why it qualifies".
- **Props:** `school: SchoolAttributes & { id; name; distanceKm? }`.
- **States:** default · compact (in lists) · no tuition on record.
- **A11y:** heading per card; website link names the school.
- **Views:** Ci, N, S results.

### NearbyList (exists inline, P1)
- **Purpose:** places nearby with straight-line distance, grouped by layer with MarkerGlyph; excludes `re` and `nat` records (those are not places).
- **Props:** `items: { entry; km }[]; onOpen`.
- **Views:** Ci, N.

### ClimateChart (exists, P1)
- **Purpose:** climate normals small multiples (§9). Reference implementation of the full interaction: `wireframes/03-city-profile.html` (inline `renderClimate`).
- **Props:** `record: ClimRecord; domain?: { tMin; tMax }` (shared y-domain when several cities are compared); `width?: number`.
- **Panels:** Temperature range (cold/warm split at a labelled 0 °C line, mean tick) · Precipitation mm · Snowfall cm · More measures (accordion).
- **States:** full · partial months (hatched nulls, "–" labels) · no snow data (panel omitted with a sentence) · older period (info badge) · station far from centre (note) · Chart | Table toggle.
- **A11y:** `role="group"` with summary `aria-label`; focusable; ← → / Home / End move by month with the same tooltip as hover; live region mirrors the tooltip; table twin.
- **Views:** Ci, N, M; Cmp (climate row expand).

### AnnualStats, SeasonList (new, P1)
- **Purpose:** non-null annual figures as stat tiles (proportional figures); seasons Dec–Feb, Mar–May, Jun–Aug, Sep–Nov from `seasonal_summary` with the Interpretation badge.
- **Props:** `annual: ClimRecord['attributes']['annual']` · `seasonal: SeasonalSummary`.
- **Views:** Ci, N, M.

---

## 4. Comparison

### ComparisonTray (new, P1)
- **Purpose:** bottom-centre chips of pinned places (max 4), opens the comparison.
- **Props:** `items: { id; name; slot: 1|2|3|4 }[]; onRemove(id); onOpen()`.
- **States:** hidden (0) · one ("Add one more place to compare") · 2–4 · full (Add disabled with reason "Up to 4 places").
- **A11y:** `region aria-label="Comparison"`; remove buttons named "Remove Halifax from comparison".
- **Views:** C, P, Ci, N.

### ComparisonView (new, P2 — design ready)
- **Purpose:** criteria × places grid (§10), locator, weights, sensitivity.
- **Props:** `places: Place[]; criteria: Criterion[]; bands: Record<placeId, Record<criterionId, Band|null>>; weights?: Weights; onReorder(id, dir); onRemove(id)`.
- **States:** weights not set (banner, no rank) · weights set (rank + range) · essential failed column · too little evidence column · "Show differences only".
- **A11y:** `role="table"` with row/column headers; reorder by buttons, not drag.
- **Views:** Cmp; M as CriterionCard stack.

### BandCell, BandMeter, NoDataCell (new, P2)
- **BandCell props:** `band: 1..5; words: [string ×5]; records: string[]; dataDate: string; dataKinds: DataKind[]; expanded; onToggle`.
- **BandMeter:** five 14×6px segments, filled count = band, `--ce-band-fill` / `--ce-band-track`; screen-reader text "band 3 of 5, Moderate".
- **NoDataCell:** italic "No data", hatched meter (`--ce-band-nodata`), reason line; never zero.
- **Views:** Cmp, M.

### WeightsDrawer, GateBadge, SensitivityPanel (new, P2)
- **WeightsDrawer:** per criterion Essential (with minimum band) / Strong / Flexible / Ignore; reads defaults from the user profile only inside the app's local build, never sent anywhere.
- **GateBadge:** critical icon + "Fails essential: X (needs Moderate or better)"; "Unresolved: no data on essential X" (info) when the essential criterion has no data.
- **SensitivityPanel:** "Order stable for n of m one-step changes"; lists swaps.
- **Views:** Cmp.

---

## 5. Search

### SearchBox (exists, P1)
- **Purpose:** one field for names (type-ahead) and concepts.
- **Props (add):** `onConcept(query: string)`; grouped results `{ group: 'Places'|'Records'|'Ideas'; items }[]`.
- **States:** empty · typing with groups · no results (spelling hint, nearest match, "try an idea") · concept mode.
- **A11y:** combobox pattern (already correct); Escape closes the list **without** closing the profile (stop propagation); `/` focuses the field; result count announced.
- **Views:** all.

### ConceptQueryPanel, CriterionChip, ResultMatchMatrix (new, P2)
- **ConceptQueryPanel:** textarea + "We read this as n criteria" + chips + results; parser is local (no network).
- **CriterionChip props:** `label; category: Category; threshold?: { value; unit; editable; isDefault }; needsUserInput?: boolean`. States: applied · default ("Our default") · needs user input (dashed warning, not applied) · editing.
- **ResultMatchMatrix:** one 12px square per criterion: meets (filled ink) / does not meet (outlined with slash) / no data (hatched); legend always shown; `aria-label` "4 met, 1 not met, 1 no data".
- **Views:** S, M.

---

## 6. Primitives

| Component | Notes |
|---|---|
| Button | `variant: primary (ink fill) / secondary (outline) / ghost`; sizes 32/40/48 visual with 44 hit area; one primary per section; loading keeps width. |
| IconButton | Lucide icon, `aria-label`, tooltip on hover and focus. |
| Switch | Track 30×18, ink when on; `role="switch"`. |
| SegmentedControl | Ink fill for the pressed option; `aria-pressed`. |
| Badge | `neutral / info / good / warning / critical / dashed / dotted`; text 13px; status variants always carry an icon. |
| InlineNote | Empty-state note on surface-2, 13px ink-2. |
| Notice | Non-blocking status line (fallback, offline); `role="status"`. |
| ErrorBlock | What + why + what now + Retry; `role="alert"` only for user-initiated failures. |
| LoadingBar | 2px indeterminate under TopBar after 300ms; static under reduced motion. |
| SkeletonBlock | Static tonal block (no shimmer) at final height. |
| Tooltip | Inverse surface, 13px, 8px offset; shown on hover and focus; never the only path to information. |
