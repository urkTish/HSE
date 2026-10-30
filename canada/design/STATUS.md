# Agent 06 — UI/UX design lane: status

Updated 2026-10-30, end of Phase 1 (after re-review 06-6). Lane: `canada/design/`.

## Done

| File | What it is |
|---|---|
| `design-system.md` | Direction (three options, "Survey sheet" chosen, signature element), 8 principles, typography with licences and fallbacks, light/dark colour systems with a computed WCAG 2.2 contrast table, spacing/radius/elevation/motion, map rules (12 layers × shape × colour × zoom, hover/selected/cluster, labels, terrain mode, token reading into MapLibre), provenance rules, climate-chart rules, comparison rules (SPEC §4 bands, missing data, gates, sensitivity), empty/loading/error states, accessibility. |
| `tokens.css` | 142 `--ce-*` custom properties. `:root` light; dark under `@media (prefers-color-scheme: dark)` + `:root:not([data-theme="light"])` and under `:root[data-theme="dark"]` (70 themed values each, checked identical); reduced-motion and forced-colours overrides. |
| `tailwind-theme.css` | Tailwind v4 `@theme inline` mapping (`bg-surface-1`, `text-ink-3`, `shadow-3`, `font-display`, …). Agent 05 already imports both files unchanged. |
| `wireframes/` | Seven self-contained HTML files, no external scripts, fonts or images: `01-country-view`, `02-province-view`, `03-city-profile` (working reference implementation of the climate chart: hover, ← → keyboard reading, live region, Chart/Table toggle, null-month hatch), `04-comparison` (toggle between unweighted and weighted states), `05-search` (type-ahead and concept search), `06-mobile-360` (four 360 px frames), `index.html`. Each opens with a note on what it decides and has an OS/Light/Dark switch. All rendered in Chromium, no console errors, no horizontal scroll at 360 px. |
| `components.md` | Inventory of about 45 components in six groups (shell, map, profile, comparison, search, primitives): purpose, props, states, accessibility, views, phase. Uses Agent 05's existing component names. |
| `review-2026-10-30.md` | Review of the running app (desktop light/dark, 360 px), source and `ARCHITECTURE.md`: score 6.5/10, 15 findings (1 critical, 6 major, 6 minor, 2 polish) plus 2 architecture notes and a risk table for SPEC §9 B–D. |
| `review-2026-10-30-b.md` | Re-review (task 06-6) of the findings Agent 05 addressed, on a fresh `build-data` + `build`, 1440 and 360 px, light and dark: score 8/10. Fixed F-01, F-02, F-03, F-06, F-09, F-10, F-11, F-12; partly F-04, F-05, F-07, F-13; F-08, F-14, F-15 deferred to Phase 2; 4 minor side effects (R-1 to R-4). |
| `OPEN-QUESTIONS.md` | Three questions appended (see below). |
| `TASKS.md` | 06-1 to 06-6 done. |

Validator: not applicable (this lane produces no records). Colour checks:
dataviz `validate_palette.js` for map-layer hues (all-pairs, light and dark)
and a WCAG contrast script for every text/UI pair; results in
design-system §4.3–4.4.

## In progress / parked

- Re-review side effect R-2 (dark-mode city marker read as a bullseye) came
  from my token value; fixed in `tokens.css` (dark `--ce-marker-halo`
  `#ece9e2` → `#0f0f0d`, value only, logged in design-system §13), app
  rebuilt and checked, wireframes regenerated.
- Nothing parked. Not done by design (Phase 2+): high-fidelity mock-ups with
  the real fonts loaded, neighbourhood view wireframe (zoom ≥ 11), print
  styles, French UI copy.
- Base-map recolouring to the paper/ink palette depends on Agent 05 verifying
  which OpenFreeMap styles allow it; recorded as Phase 2 in design-system §7.1.

## Key design decisions

1. Direction "Survey sheet": ink-and-paper chrome from Canadian topographic
   map sheets; the map and the data own the colour.
2. Signature element: the *sheet margin* — every evidence block ends with a
   ruled strip of SOURCE · PERIOD · STATION · ACCESSED · RECORD (SPEC
   principle 6 made visible).
3. Map layers use four domain hues (climate blue, nature green, education
   magenta, housing amber) plus neutral ink, and **shape is the primary
   identity** (circle, ring, diamond, hexagon, triangles, pentagon, square,
   tag): seven separate hues failed the colour-blind all-pairs check.
4. One accent, survey vermilion, reserved for selection, focus and the active
   state; selection drawn as a four-corner survey bracket.
5. Climate chart = small multiples on one month axis (temperature range split
   at a labelled 0 °C line, precipitation mm, snowfall cm); no dual axis, no
   weather icons, no current-month marker; "30-year averages, not a
   forecast" and the station are always visible.
6. Comparison shows worded ordinal bands with a monochrome five-segment
   meter; "No data" is explicit and never zero; no rank until the user sets
   weights; a failed essential criterion keeps the column visible; any
   composite number carries its sensitivity range.
7. Concept search echoes the query back as editable criteria chips; criteria
   that need the user's own facts (budget) stay unapplied until set.
8. Archivo + Source Sans 3 (both SIL OFL 1.1), self-hosted via Fontsource,
   never from a CDN; Lucide icons (ISC); markers drawn at runtime.
9. Every displayed figure goes through one `FigureValue` component that
   shows verification, figure kind and staleness.

## Coordinator requirements adopted (note of 2026-10-30)

- **Verification status on every figure.** design-system §8 "Verification
  on every figure": the record's `verification.status` sits next to each
  value as a Lucide icon plus a word (never colour alone); disputed values
  get a "Disputed" badge linked to `DECISIONS.md` and a dotted underline;
  records with cautions (for example territorial doctor-access figures)
  get "Use with caution" quoting `verification.notes`. Comparison cells
  show the *weakest* status among their evidence, and a row on disputed
  evidence gets the chip "Disputed evidence" (§10.2). New component
  `FigureValue`; `BandCell` props extended (components.md).
- **Market figures (D-008).** Figure-kind badge (Survey, Asking,
  Transaction, Index, Estimate) before every market value; "Older than 60
  days" staleness badge; CREA- or CMHC-only figures are link-only ("View on
  the CREA HPI tool", with the reason) rather than displayed; Statistics
  Canada–republished survey rents may be shown with Statistics Canada named.
- Both are shown in `wireframes/04-comparison.html` (cell badges, disputed
  healthcare row) and `wireframes/03-city-profile.html` (Residential
  intelligence section).

## Open questions added

- Interface language: English only, or English and French (or another)?
- Mostly computer or phone?
- Are the comparison band words clear, or should others be used?

## Next step

Agent 05, Phase 2 first: (1) finish mobile (F-04, plus F-07 top padding):
one-row top bar, layers and "Places in view" in one sheet, profile in a
bottom sheet; (2) dark-mode attribution and scale legibility, and keep the
attribution clear of the profile panel (F-05 remainder, R-3); (3) self-hosted
fonts with the display-size place name, then `SheetMargin` per section
(F-14, F-08). Agent 06 next: neighbourhood-view wireframe, high-fidelity
profile header with the real fonts, and a third review after those changes.
