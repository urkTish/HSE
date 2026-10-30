# Task board

Status: `todo` · `doing` · `blocked` · `done`. Agents edit only their own
section. A request to another agent is a new line under that agent with
`from: agent-0X` and the reason.

## Agent 01 — National Intelligence (`knowledge-base/national/`)

- [doing] 01-1 Immigration pathways overview (Express Entry incl. category-based selection, PNPs by province, family, work permits), current Levels Plan, processing times; `nat` records for status-dependent rights.
- [doing] 01-2 Provincial tax comparison for the current tax year: income tax brackets, sales taxes, worked take-home examples with stated assumptions.
- [doing] 01-3 Healthcare by province: eligibility by status, newcomer waiting periods, regular-provider attachment, drug coverage.
- [doing] 01-4 Employment and credential recognition: how regulated professions are licensed per province; Job Bank outlook method; placeholder for the user's NOC once known.
- [doing] 01-5 Quebec language rules affecting newcomers (work, services, schooling eligibility) as `nat` records.
- [doing] 01-6 `STATUS.md`, open questions appended to `OPEN-QUESTIONS.md`.

## Agent 02 — Real Estate (`knowledge-base/real-estate/`)

- [doing] 02-1 Source register and methodology: CREA/boards, CMHC, StatCan, assessment databases, listing platforms; terms of use per source; on-demand retrieval design for the map.
- [doing] 02-2 Dated market snapshot for 15–20 CMAs: benchmark/average prices and CMHC survey rents, as `re` records with period and figure kind.
- [doing] 02-3 Rules by province: eligibility to buy by status (federal prohibition and exemptions, provincial non-resident taxes), land-transfer taxes, rent control, tenant protections, short-term rental rules.
- [doing] 02-4 Investment model template with formulas and stated assumptions (no stored rates).
- [doing] 02-5 `STATUS.md`, open questions.

## Agent 03 — Alternative Education (`knowledge-base/education/`)

- [doing] 03-1 Regulation by province and territory: private/independent school law, registration, inspection, diplomas, homeschooling, online schooling; Quebec language eligibility.
- [doing] 03-2 Candidate institutions, each as a `school` record with `qualifying` status and reason; verified coordinates; tuition with school year; priority provinces BC, AB, ON, QC, NS, then the rest.
- [todo] 03-3 Comparative evaluation of qualifying institutions by the SPEC §7 criteria.
- [todo] 03-4 `STATUS.md`, open questions ("Hand in Hand").

## Agent 04 — Geography & Climate (`knowledge-base/geography-climate/`)

- [doing] 04-1 Province and territory comparison: physiographic regions, landscapes, hazards, lifestyle, key cities; `region` and `landform` records.
- [doing] 04-2 Climate normals for at least 20 representative cities as `clim` records (ECCC; 1991–2020 where published, else 1981–2010; station and period stated).
- [doing] 04-3 Hazard records by region (wildfire, flood, coastal, drought, heat, cold, avalanche, ice storm, permafrost).
- [doing] 04-4 First answers to the comparative questions, labelled as professional interpretation with evidence IDs.
- [doing] 04-5 `STATUS.md`, open questions.

## Agent 05 — Map Architect (`map/`)

- [doing] 05-1 `ARCHITECTURE.md` and `DATA-SOURCES.md` (licences, attribution).
- [doing] 05-2 Running skeleton: MapLibre base map of Canada, province boundaries, layer toggles, knowledge-base loader, location profile panel, climate chart component bound to the `clim` schema; lint, typecheck and build pass.
- [doing] 05-3 Build step that converts validated records into GeoJSON for the map.
- [todo] 05-4 `STATUS.md`.
- [todo] 05-5 from: agent-06 — adopt `design/tokens.css` and the component inventory once delivered.

## Agent 06 — UI/UX (`design/`)

- [doing] 06-1 `design-system.md` and `tokens.css` (light and dark).
- [doing] 06-2 Wireframes: country, province, city with profile, comparison, search, mobile.
- [doing] 06-3 `components.md` inventory for Agent 05.
- [todo] 06-4 First review of the Agent 05 skeleton (`review-YYYY-MM-DD.md`).
- [todo] 06-5 `STATUS.md`.

## Agent 07 — Coordinator (repository root of `canada/`)

- [done] 07-1 Spec review v1.1, schemas, validator, charters, profile, questions.
- [doing] 07-2 Spawn Agents 01–06 for Phase 1; integrate results; run validator; commit; open draft PR.
- [todo] 07-3 Consolidate Phase 1 into `PROGRESS.md`; batch open questions for the user.
