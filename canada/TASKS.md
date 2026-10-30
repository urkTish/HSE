# Task board

Status: `todo` · `doing` · `blocked` · `done`. Agents edit only their own
section. A request to another agent is a new line under that agent with
`from: agent-0X` and the reason.

## Agent 01 — National Intelligence (`knowledge-base/national/`)

- [done] 01-1 Immigration pathways overview (Express Entry incl. category-based selection, PNPs by province, family, work permits), current Levels Plan, processing times; `nat` records for status-dependent rights.
- [done] 01-2 Provincial tax comparison for the current tax year: income tax brackets, sales taxes, worked take-home examples with stated assumptions.
- [done] 01-3 Healthcare by province: eligibility by status, newcomer waiting periods, regular-provider attachment, drug coverage.
- [done] 01-4 Employment and credential recognition: how regulated professions are licensed per province; Job Bank outlook method; placeholder for the user's NOC once known.
- [done] 01-5 Quebec language rules affecting newcomers (work, services, schooling eligibility) as `nat` records.
- [done] 01-6 `STATUS.md`, open questions appended to `OPEN-QUESTIONS.md`.
- [todo] 01-7 Re-check in early November 2026: 2027–2029 Levels Plan (due 1 Nov), Express Entry CRS change in force 3 Nov and the list of high-wage occupations, the non-Canadian buyer ban (expires 1 Jan 2027), and Quebec policy under the new government.
- [todo] 01-8 Fill Phase 1 gaps: IRCC permanent-residence processing times (null), CLB minimums for CEC/FST, PEI and Nunavut newcomer waiting periods, Quebec drug-plan premium and the temporary English-schooling regulation text, check of the take-home estimates against the CRA Payroll Deductions Online Calculator.
- [todo] 01-9 Once USER-PROFILE.md names the occupation, citizenship and family: fill the occupation placeholder in employment-and-credentials.md and add regulator records for the shortlisted provinces.

## Agent 02 — Real Estate (`knowledge-base/real-estate/`)

- [done] 02-1 Source register and methodology: CREA/boards, CMHC, StatCan, assessment databases, listing platforms; terms of use per source; on-demand retrieval design for the map.
- [done] 02-2 Dated market snapshot for 15–20 CMAs: benchmark/average prices and CMHC survey rents, as `re` records with period and figure kind.
- [done] 02-3 Rules by province: eligibility to buy by status (federal prohibition and exemptions, provincial non-resident taxes), land-transfer taxes, rent control, tenant protections, short-term rental rules.
- [done] 02-4 Investment model template with formulas and stated assumptions (no stored rates).
- [done] 02-5 `STATUS.md`, open questions.
- [todo] 02-6 Phase 1 leftovers (parked): eviction notice rules per province; transfer costs AB/SK/NL/PE; PEI 2026 rent increase; Kelowna and Sherbrooke CMA-level board prices; Ottawa/Hamilton vacant-unit taxes; STR rules Calgary/Edmonton/Ottawa/Halifax. See `knowledge-base/real-estate/STATUS.md`.

## Agent 03 — Alternative Education (`knowledge-base/education/`)

- [done] 03-1 Regulation by province and territory: private/independent school law, registration, inspection, diplomas, homeschooling, online schooling; Quebec language eligibility.
- [done] 03-2 Candidate institutions, each as a `school` record with `qualifying` status and reason; verified coordinates; tuition with school year; priority provinces BC, AB, ON, QC, NS, then the rest.
- [done] 03-3 Comparative evaluation of qualifying institutions by the SPEC §7 criteria.
- [done] 03-4 `STATUS.md`, open questions ("Hand in Hand").
- [todo] 03-5 (Phase 1 follow-up) Confirm fees/years for the 11 `unverified_candidate` schools (SelfDesign, Oak and Orca, ERSM, Orford, Lauremont, VHS, CMA, HIS, Whistler Waldorf, Shambhala, Phoenix); regulation sections for MB, SK, NB, PE, NL, YT, NT, NU; read consolidated Québec texts when LégisQuébec is reachable.
- [todo] 03-6 (re-routed by the coordinator) `city` records live in `knowledge-base/places/` (Agent 05, from Natural Earth; 31 so far, principal cities only). Agent 03 computes `nearby_cities_km` from those in Phase 2 and asks Agent 05 for any missing towns (Nelson, Squamish, Whistler, Lunenburg, Vaughan, North Vancouver) as `city` records.

## Agent 04 — Geography & Climate (`knowledge-base/geography-climate/`)

- [done] 04-1 Province and territory comparison: physiographic regions, landscapes, hazards, lifestyle, key cities; `region` and `landform` records.
- [done] 04-2 Climate normals for at least 20 representative cities as `clim` records (ECCC; 1991–2020 where published, else 1981–2010; station and period stated).
- [done] 04-3 Hazard records by region (wildfire, flood, coastal, drought, heat, cold, avalanche, ice storm, permafrost).
- [done] 04-4 First answers to the comparative questions, labelled as professional interpretation with evidence IDs.
- [done] 04-5 `STATUS.md`, open questions.
- [todo] 04-6 Parked from Phase 1 (see `geography-climate/STATUS.md`): Thunder Bay precipitation normals; PEI coastal-erosion source; official figures for the 2013 southern Alberta flood; Chic-Chocs/Appalachian Uplands descriptive source; city-centre stations for Montréal, Calgary and Halifax.
- [todo] 04-7 handoff request for Agent 02 (from: agent-04; coordinator please move under Agent 02, since agents edit only their own section) — `re` records for the candidate mountain towns (Nelson, Castlegar, Cranbrook, Kamloops, Penticton, Prince George, Corner Brook, Whitehorse, Sherbrooke) so `comparative-answers.md` can fill the housing-cost column.

## Agent 05 — Map Architect (`map/`)

- [done] 05-1 `ARCHITECTURE.md` and `DATA-SOURCES.md` (licences, attribution).
- [done] 05-2 Running skeleton: MapLibre base map of Canada, province boundaries, layer toggles, knowledge-base loader, location profile panel, climate chart component bound to the `clim` schema; lint, typecheck and build pass.
- [done] 05-3 Build step that converts validated records into GeoJSON for the map.
- [done] 05-4 `STATUS.md`.
- [doing] 05-5 from: agent-06 — adopt `design/tokens.css` and the component inventory once delivered. Tokens: done (app imports `design/tokens.css` and `design/tailwind-theme.css` unchanged). Components: MarkerGlyph, PlacesInViewList, FigureValue, NotYetResearched, LiveAnnouncer, SkipLinks adopted; the rest (MapControls, BottomSheet, ProfileTabs, SheetMargin, Breadcrumb, AboutDataDialog, fonts) in Phase 2, see `map/STATUS.md`.
- [done] 05-6 from: agent-06 — work through review findings F-01 to F-07 in `design/review-2026-10-30.md` (F-01 critical: per-layer marker shapes and minimum zoom; F-02 keyboard reach and focus management; F-03 keep `re`/`nat` records out of "Nearby" and add a "Living" section with `FigureValue`); then Agent 06 re-reviews (06-6). Result: F-01, F-02, F-03, F-05, F-06, F-07 fixed; F-04 partly (wordmark hidden, attribution collapsed, city tiers; bottom sheet open); F-10, F-11, F-12, F-13 (partly) also fixed. Details in `map/STATUS.md`.
- [todo] 05-7 from: agent-06 (re-review `design/review-2026-10-30-b.md`, 8/10) — Phase 2 first: (a) attribution and scale text legible in dark mode (`--ce-ink-2`) and never hidden behind the profile panel at 1440 px (licence requirement; F-05 remainder, R-3); (b) mobile: one-row top bar, layers and "Places in view" in one sheet, profile in a bottom sheet with snap points, top map padding on mobile (F-04, F-07, R-4; wireframe 06); (c) clusters of different layers overlap at one spot (R-1); (d) skip-link target needs `tabindex="-1"` (F-02 remainder); then F-14 fonts and F-08 per-section provenance. Rebuild to pick up the dark `--ce-marker-halo` token change (R-2).

## Agent 06 — UI/UX (`design/`)

- [done] 06-1 `design-system.md` and `tokens.css` (light and dark), plus `tailwind-theme.css` (Tailwind v4 mapping, already imported by the app).
- [done] 06-2 Wireframes: country, province, city with profile, comparison, search, mobile (`design/wireframes/`, index.html).
- [done] 06-3 `components.md` inventory for Agent 05.
- [done] 06-4 First review of the Agent 05 skeleton (`review-2026-10-30.md`: 15 findings + 2 architecture notes).
- [done] 06-5 `STATUS.md`.
- [done] 06-6 Re-review (`design/review-2026-10-30-b.md`): score 8/10; F-01, F-02, F-03, F-06, F-09, F-10, F-11, F-12 fixed; F-04, F-05, F-07, F-13 partly; 4 minor side effects (R-2 fixed in tokens by Agent 06).

## Agent 07 — Coordinator (repository root of `canada/`)

- [done] 07-1 Spec review v1.1, schemas, validator, charters, profile, questions.
- [doing] 07-2 Spawn Agents 01–06 for Phase 1; integrate results; run validator; commit; open draft PR.
- [todo] 07-3 Consolidate Phase 1 into `PROGRESS.md`; batch open questions for the user.
