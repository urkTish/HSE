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
