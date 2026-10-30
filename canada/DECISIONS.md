# Decisions

One entry per non-obvious choice: what, why, alternatives, date.

- **D-001 (2026-10-30) — Location of the project.** The Canada system lives in
  `canada/` inside the `urkTish/HSE` repository on branch
  `claude/great-hamilton-xcla51`, because that is the repository and branch
  the user opened the session in. The HSE CI jobs run only in `backend/` and
  `frontend/`, so the folder cannot break them. Alternative: a separate
  repository; deferred to the user (`OPEN-QUESTIONS.md` item 11).
- **D-002 (2026-10-30) — Coordinator.** The orchestrating session acts as
  Agent 07 rather than spawning a seventh agent: it already holds the full
  context, owns git, and is the only party that can commit. Specialists do
  not run git.
- **D-003 (2026-10-30) — Specification v1.1 supersedes v1.0.** Reasons in
  `SPEC-REVIEW.md`. v1.0 is archived unchanged.
- **D-004 (2026-10-30) — Climate reference period.** ECCC 1991–2020 normals
  where published for the station, otherwise 1981–2010, labelled per record.
  Alternative: 1981–2010 everywhere for consistency; rejected because the
  newer period better reflects current conditions where it exists.
- **D-005 (2026-10-30) — Default map stack.** MapLibre GL JS with open vector
  tiles, Statistics Canada boundaries, NRCan elevation, OSM features under
  ODbL, open geocoding and routing, Vite + React + TypeScript + Tailwind.
  Mapbox rejected as a dependency because it needs a paid account. Agent 05
  may revise with a new entry here.
- **D-006 (2026-10-30) — Comparison method.** Ordinal bands with written
  thresholds, user weights, essential-requirement gates and a sensitivity
  view (SPEC §4), resolving the v1.0 contradiction between "no manufactured
  scores" and "weighted comparisons".
- **D-007 (2026-10-30) — Agent model.** Specialist agents run on Opus at high
  effort, as the user requested.
- **D-008 (2026-10-30) — Market figures and publication, provisional.** CREA
  (MLS® HPI) and CMHC terms forbid republishing their figures without
  consent (Agent 02, `knowledge-base/real-estate/METHODOLOGY.md`). Until the
  user decides whether the map is private or published
  (`OPEN-QUESTIONS.md`, Agent 02 item), the map is treated as private to the
  user, and in every case the build step keeps `re` records whose only
  sources are CREA or CMHC out of any published GeoJSON; benchmark prices
  are linked to the CREA HPI tool rather than displayed from storage.
  Two-bedroom survey rents may be displayed because Statistics Canada
  republishes them under its open licence and the values match.
- **D-009 (2026-10-30) — Source conflict: insured-mortgage price cap.** The
  Financial Consumer Agency of Canada page still states $1 million; the
  Department of Finance raised the cap to $1.5 million from 15 December
  2024. `nat-ca-mortgage-down-payment-insurance-rules` follows Finance (the
  rule-making body); the FCAC page is noted as outdated. Period, not
  methodology, explains the difference.
- **D-010 (2026-10-30) — Two records for the federal buyer ban.** Agent 01
  (`nat-ca-residential-property-purchase-by-non-canadians`) and Agent 02
  (`nat-ca-non-canadian-residential-purchase-prohibition`) both describe the
  Prohibition on the Purchase of Residential Property by Non-Canadians Act.
  They agree on substance (in force since 2023-01-01, scheduled end
  2027-01-01, exemption for work-permit holders with at least 183 days
  remaining, one property). Both stay. Agent 02's record is canonical for
  the rule (verified against the Justice Laws consolidation); Agent 01's is
  the status-dependency cross-reference used by the "what each status
  allows" table. New facts go to the canonical record first.
- **D-011 (2026-10-30) — Manitoba 2026 tax thresholds, disputed.** The CRA
  current-year rates page shows $47,564 / $101,200; CRA's payroll formulas
  show $47,000 / $100,000, matching Manitoba's indexation freeze.
  `nat-mb-income-and-sales-tax-2026` uses $47,000 / $100,000 and stays
  `disputed`; the effect is under $70 a year. Re-check against Manitoba
  Finance when its site is reachable.
- **D-012 (2026-10-30) — Quebec three-year cap on temporary English
  schooling.** Agent 01's `nat-qc-english-schooling-eligibility` carried the
  cap as reported (partially verified). Agent 03 read the Bill 96 statute
  and the 1997 regulation text (Charter s. 84.1: up to three years, not
  renewable, extended to 30 June). Agent 03's
  `nat-qc-education-english-instruction-eligibility` is canonical for the
  cap and for unsubsidised private schools, home schooling and CEGEP; Agent
  01's record remains canonical for public and subsidised school
  eligibility and cites it. The consolidated LégisQuébec text is still to be
  read (sites returned 403 to both agents).
- **D-013 (2026-10-30) — Base map.** OpenFreeMap vector styles (Positron for
  light, Dark for dark mode), no key, with a built-in no-network fallback
  style after six seconds. Proposed by Agent 05 (P-05-1); consistent with
  D-005.
- **D-014 (2026-10-30) — First-pass gazetteer.** Province boundaries and the
  31 principal `city` records come from Natural Earth v5.1.2 (public domain)
  for Phase 1; Statistics Canada boundaries and census subdivisions replace
  them in Phase 2. City records carry `data_kind: official_fact` with
  `source_type: other` and the dataset named in `coord_source`; when the
  Statistics Canada source lands they become official facts in the strict
  sense (P-05-2).
- **D-015 (2026-10-30) — What never enters static files.** Market values,
  tuition amounts, dollar figures in free text and anything that reads as a
  forecast are stripped from the generated GeoJSON; the school year and the
  source link stay, and the amount is shown on demand from the record.
  Legislated figures in `nat` records (tax brackets, credits, programme fees)
  stay. Stricter than SPEC §9 B on tuition; to be revisited with the
  private-versus-published decision (D-008) (P-05-3).
- **D-016 (2026-10-30) — Build behaviour on invalid records.** `build-data`
  skips records that fail validation and fails only if the map's own lane
  fails; `build-data --strict` fails on any invalid record and is the
  coordinator's pre-commit check (P-05-4).
- **D-017 (2026-10-30) — Generated data is not committed.** `public/data/` is
  rebuilt by `dev`, `build` and `build-data`; only the 276 KB Natural Earth
  source extract is committed (P-05-5).
- **D-018 (2026-10-30) — Toolchain.** Vite 8, React 19, TypeScript 6,
  Tailwind 4, MapLibre GL JS 6 as resolved on 2026-10-30; MapLibre 6
  requires the worker URL to be registered explicitly (P-05-6).
