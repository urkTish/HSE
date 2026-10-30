# Agent 05 — Interactive Canada Map Architect

Charter: `canada/SPEC.md` §9 (defaults in §9 H). Common rules:
`agents/00-common-rules.md`. Lane: `canada/map/`, plus one exception:
you own `canada/knowledge-base/places/` for gazetteer-type `city` records
derived from open datasets (not research).

## Phase 1 deliverables

1. **`ARCHITECTURE.md`** — modules (map, knowledge-base loader, dynamic
   retrieval, UI), data flow from validated records to GeoJSON to layers,
   how on-demand figures will be fetched and displayed with date and source,
   how the education layer is restricted to `qualifying` records, and the
   Phase 2–4 plan. Record any deviation from the §9 H defaults as a
   proposed `DECISIONS.md` entry in your STATUS (you do not edit
   `DECISIONS.md`).
2. **`DATA-SOURCES.md`** — every dataset, tile source, font and image source
   with licence, attribution text and usage limits. Nothing enters the app
   without a line here.
3. **The application** at `canada/map/app/`: Vite, React, TypeScript,
   Tailwind, MapLibre GL JS. Use open vector tiles that need no key (for
   example OpenFreeMap styles); verify the style URL loads before relying
   on it, and keep a fallback. Required in Phase 1:
   - Full-country view with province and territory boundaries (Natural Earth
     admin-1 filtered to Canada is acceptable now; note Statistics Canada
     boundaries for Phase 2) with hover and click.
   - `city` records for the principal cities, generated from Natural Earth
     populated places (public domain) into `canada/knowledge-base/places/`,
     validated, with `coord_source` named.
   - A build step `app/scripts/build-data.mjs` that runs the knowledge-base
     validator, then converts every record under `canada/knowledge-base/`
     into `app/public/data/<category>.geojson` plus an `index.json`.
     The education GeoJSON includes only `attributes.qualifying ===
     "qualifying"`.
   - Layer toggles for the twelve layers of §9 C (empty layers show an
     honest empty state).
   - A location profile panel that opens on click and renders what the
     record has, section by section, hiding sections with no data.
   - A climate chart component bound to the `clim` schema (twelve months of
     high, low, precipitation and snow) that always shows `normals_period`,
     station and source. Prefer a small hand-written SVG component over a
     heavy charting dependency.
   - Search over record names.
   - Attribution control showing the strings from `DATA-SOURCES.md`.
   - Scripts: `npm run dev`, `build`, `lint`, `typecheck`, `validate`
     (calls the knowledge-base validator), `build-data`. All of `lint`,
     `typecheck`, `build-data` and `build` must pass before you finish.
   - Styling: define CSS custom properties in one tokens file. Before you
     finish, check whether `canada/design/tokens.css` exists; if it does,
     import it and map your Tailwind theme to those variables; if not, note
     the task as waiting for Agent 06 in your STATUS.
4. **`app/.gitignore`** for `node_modules/`, `dist/`, caches. Do not commit
   generated GeoJSON if it exceeds a few megabytes; generate it in the
   build instead and say so.
5. **`STATUS.md`** (completed functionality, status, outstanding tasks,
   limitations, sources, next milestone) and your open questions.

## Standards specific to this lane

- No Mapbox, no API keys, no secrets, no analytics.
- Never embed prices, rents or forecasts in static assets.
- Respect tile and API usage policies named in `DATA-SOURCES.md`.
- Keep the Vite app self-contained; do not touch `frontend/` or `backend/`
  of the host repository.
