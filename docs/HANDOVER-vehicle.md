# Handover: vehicle options 7a / 7b (planned, not built)

> **DO NOT START UNTIL TURKI (HSE Manager) SAYS GO, and only for the option he names (A = 7a, B = 7b prototype). B no longer needs A technically; if both are chosen, build A first.**

Written 2026-10-10, revised 2026-10-11 after Turki's answers (§0), by the HSE Consultant agent. This file is self-contained: a fresh session can execute either option from it. A copy lives in the repo at `docs/HANDOVER-vehicle.md`.

## 0. Turki's answers (2026-10-11), verbatim, and what they changed

| # | Question | Answer (verbatim) | Applied |
|---|---|---|---|
| 1 | Should the client get a copy of Najm / police reports? | "No but should be recoreded/archived" | 7a v1.1: report number, date and files archived on the incident for its retention period, files never deleted after Closed (VA-14, `ACCIDENT_REPORT_LOCKED`); no client copy, no client notification, no files in client views or exports (VA-15). |
| 2 | Fleet scope: log visitor and delivery vehicles at the gate? | "Logging is more of Security scope than HSE" | 7b v2.0: gate logging and site-gate vehicle checks moved to "Out of scope (security)"; Phase 2 gates unchanged. |
| 3 | Journey plan triggers (≥ 150 km, night, desert, crew bus)? | "sure but dont put too much project leave it in its prototype since we dont have now" | 7b v2.0: minimal journey-plan form, hint at 150 km or 22:00–05:00, no check-ins, no escalation; overdue is a list flag only. |
| 4 | Telematics / IVMS, 12-point suspension? | "This is for logistics I'm in construction (prototype again)" | 7b v2.0: telematics, speeding events, points and suspension, mileage and km rates, long-haul features moved to "Out of scope (logistics)"; whole module marked **Prototype**, construction-focused. |
| 5 | Are company-bus commuting crashes work-related? | "Not according to OSHA but should be recorded either way if not counted." | 7a v1.1: commuting (own car or company bus) never counted in K-137, regardless of `include_commuting_in_rates`; always recorded and shown as "Recorded, not counted" in counts, lists and C41 (VA-13). |

## 1. The two options

| | Option A — `docs/specs/7a-vehicle-accident-details.md` | Option B — `docs/specs/7b-fleet-driver.md` |
|---|---|---|
| What | A vehicle-accident section on Phase 1 incidents: vehicles (own / contractor / hired / third party / unknown, plate, link to the Phase 2 vehicle), driver (worker or external, licence class and expiry checked at the time), road type, Najm / police report archived on the incident (no client copy), third-party damage, seat belt, speed, commuting link (recorded, not counted); police / Najm rows in 6f; K-136, K-137, C41 | **Prototype**, construction-focused: site vehicle & plant readiness (fields on the Phase 2 vehicle, document expiry, Phase 4 status for certified plant), driver / operator authorisations (licence, DEF-DRV via Phase 5, DRIVER-FIT via 6a, Phase 4 operator certificates), daily pre-use checks on 6d templates with defect hold, a minimal journey-plan form; K-138…K-140, capabilities 233–237. No gate, telematics, points, mileage or escalation. |
| Size | 32 ACs, no new capability, no new screen (incident pages + dashboard) | 24 ACs, 4 small screens (site vehicles, authorisations, pre-use checks, journey plans) + settings, one daily job |
| Depends on | Phase 1, 2, 6f, 6g (all built) | Phases 2, 4, 5, 6a, 6d, 6g (all built); 7a optional (only the §11.8 links) |
| Rough effort | 1 backend + 1 frontend session, short design pass | About the same as A: 1 backend + 1 frontend session, short design pass |

Numbering reserved (do not reuse): 7a = K-136…K-137, C41. 7b = capabilities 233–237, K-138…K-140, CA source `site_vehicle`, 6d owner type `vehicle_check`. Released by the 7b v2.0 shrink (free again): capabilities 238–240, K-141…K-144, E26, T26, C42–C43, CA source `fleet`, hook kind `driver_authorisation`. Check again before building (`grep` the specs, `docs/DECISIONS.md`, `backend/app/core/enums.py`); if anything moved, renumber in the spec first.

## 2. Repo and environment

- Repo `urkTish/HSE`, branch **`claude/hse-platform-build-kannxy`** (no main branch, no PRs, no other branches). Working tree `/home/claude/HSE`.
- **Backend** `backend/`: Python 3.12, uv, FastAPI, SQLAlchemy 2, Alembic, Postgres 16; pytest, ruff, mypy strict. Checks: `uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest`; migrations `uv run alembic upgrade head && uv run alembic check`.
- **Frontend** `frontend/`: Next.js App Router, strict TS, Tailwind, shadcn, TanStack Query, next-intl (`/en`, `/ar`, RTL). Checks: `npm run lint && npm run typecheck && npm run i18n:check && npm run build`, e2e `npm run test:e2e` (Playwright, Chromium at `/opt/pw-browsers`; never `playwright install` locally).
- **Contract-first:** `docs/contracts/openapi.yaml`, generated with `uv run python -m app.export_openapi` (CI checks `--check`). Current **v0.13.0**. Bump: the first option built → v0.14.0, the second → v0.15.0 (one bump if both are built together; say so in PROGRESS). Frontend types: `npm run gen:api`.
- **Postgres** local, user/password `hse`/`hse`, DBs `hse`, `hse_test`; start with `pg_ctlcluster 16 main start` if down. **No Docker.**
- **e2e:** `frontend/e2e/start-backend.sh` drops, migrates and seeds `E2E_DB_NAME` (default `hse_e2e`), runs the API on `E2E_BACKEND_PORT` (default 8000); frontend at `E2E_BASE_URL` (default http://localhost:3000). Shared clock `frontend/e2e/clock.ts`: `E2E_CLOCK_AT` default **2026-10-06T10:00+03:00**, passed to the API as `HSE_CLOCK_AT` (advancing). Specs 6g/7a/7b use `HSE_CLOCK_AT` = 2026-10-12 10:00 for backend tests; pick per test as the 6g tests do.
- **Private DB / ports when other agents run:** use your own `E2E_DB_NAME`, `E2E_BACKEND_PORT` and frontend port; run a clean backend from `git archive HEAD | tar -x -C /tmp/…` with `E2E_BACKEND_DIR=<that dir>` when backend/ has uncommitted work.
- **Screenshots** only with `SCREENSHOTS=1` (writes into `docs/screenshots/phase-…`); otherwise to `test-results/shots`.
- Full e2e run takes ~40 min. Run it once at the end, not in a loop.

## 3. Conventions (must follow)

- `docs/CONVENTIONS.md`: error envelope `{"detail":{"code","message","message_ar"}}`; 401/403/404/409/422; lists `{items,total,page,page_size}`; cookie `hse_session`; QR `HSE2:<kind>:<token>`.
- **D-202 schema prefixes:** a new Pydantic schema or enum whose plain name already exists in another module gets a module prefix (6e used `Env…`). Use `Veh…` (7a) / `SiteVeh…` (7b) (e.g. `VehIncidentVehicleRead`, `SiteVehReadinessRead`) so earlier OpenAPI component names do not change.
- **i18n:** strings are written as EN/AR pairs in `frontend/scripts/i18n/p<phase>-<name>.py` (dict `P`, leaves `[en, ar]`), then `python3 scripts/i18n/merge.py` (globs `p[0-9]-*.py`, runs `consistency.py` last) regenerates `messages/en.json` / `ar.json`. Use `p7-vehicle.py` (7a) and `p7-site-vehicle.py` (7b); add only new keys. ICU: escape `<…>` in messages.
- **Design conventions:** `docs/design/consistency-pass-findings.md` and `docs/design/restyle-findings.md` (D-238: emerald brand `#0c574e`, platinum neutrals, safety-green split from brand; tokens only in `src/styles/tokens.css`). Irreversible record actions (void, revoke, withdraw, clear hold, supersede an archived accident report) go in the **page-end "Record actions" band** (`components/common/record-actions.tsx`); safety stops stay at the top. Month names, not `yyyy-mm`; plates, km and refs LTR inside RTL; compact cards at 390 px.
- **Commits:** WIP commits contain `[skip ci]`. **Never `git add -A`**; stage only your own files. Re-read `docs/PROGRESS.md` and `docs/DECISIONS.md` right before editing them (other agents edit them). Every commit message ends with:
  ```
  Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_019ePKhVEWcGdEt7YFu3vJZQ
  ```
- **Push:** `git push -u origin claude/hse-platform-build-kannxy`; on rejection `git pull --rebase` then push again. No force push.
- Never leave `app.seed` importing a module that does not exist yet. Never skip or disable a test to get green. One reasonable attempt on flaky things, then record in PROGRESS.
- Decisions: next free number is **D-239** (latest D-238, restyle). Add rows to `docs/DECISIONS.md` in order.

## 4. Agents and pipeline

Prompts in `/mnt/project-files/prompts/`: `01-hse-consultant-agent.md` (spec authority; answers questions, bumps spec version), `02-build-plan.md` (shared plan, loaded by 03/04), `03-backend-agent.md`, `04-frontend-agent.md`, `05-uiux-designer-agent.md`, `06-fixer-accelerator-agent.md`.

Pipeline per option: **spec (done) → contract (backend stage 1, openapi bump) → backend (stage 2: models, migration, services, KPIs, seed, tests) → frontend (types, screens, i18n, e2e) → design pass (05, before/after screenshots, findings file) → fixer check (06: full e2e once, CI green)**. Apply the spec's §11 earlier-spec changes in the same backend stage and bump those specs' versions.

## 5. Files each option touches

### Option A (7a)
Backend:
- `backend/app/models/hse.py` — `Incident` (new columns: vehicle_involved, road_type, road_location, journey_purpose, light, surface, report_authority, report_no, report_date, liability_pct_own, third_party_damage_*, recorded_not_counted), new model `IncidentVehicle` (table `incident_vehicles`); report files through the existing attachments with a new owner `incident_accident_report` (superseded flag, no delete after Closed).
- `backend/app/core/hse_enums.py` — `ExternalBody` + `najm`; new enums RoadType, JourneyPurpose, VehicleOwnership, VehicleRole, LicenceCheck, etc.; `backend/app/core/followup_enums.py` — triggers `rta_public_injury`, `rta_public_no_injury`.
- `backend/alembic/versions/` — new `2026xxxx_0016_vehicle_accident.py` (latest is `20261010_0015_phase6g_scorecard_reports.py`).
- `backend/app/schemas/incidents.py` (Veh-prefixed schemas), `backend/app/api/routers/incidents.py`, `backend/app/services/incidents.py` (close check VA-14, recorded_not_counted VA-13), `services/injury_cases.py` (commuting proposal VA-7), `services/investigations.py` (VEHICLE_SECTION_INCOMPLETE, prompts VA-4), `services/access/vehicles.py` (read-only lookup, plate normalisation); attachments service (owner `incident_accident_report`, 29-only, excluded from Viewer/Client and client report packs, VA-15).
- 6f: `backend/app/services/followup/common.py` (statutory rows POL-V etc. live here → add POL-RTA, NAJM-V), `services/followup/requirements.py` (triggers), `services/followup/config.py`.
- KPIs: `backend/app/kpi/catalogue.py` (K-136, K-137), new `backend/app/kpi/vehicle.py` registered in `kpi/engine.py` (pattern: `import app.kpi.scorecard  # registers …` at the end), `kpi/charts.py` (C41), `kpi/breakdowns.py` (road_type etc.).
- AI: `backend/app/ai/tools.py` (T3 dimensions, T4 filters `t_search_incidents`, T5 detail), `ai/masking.py`.
- Exports: `backend/app/services/scorecard/datasets.py` (dataset `incident_vehicles`).
- Seed: `backend/app/seed_hse.py` (or a new `seed_vehicle.py` called from `app/seed.py`); tests `backend/tests/test_vehicle_accident.py` (+ helpers `hse_helpers.py`, `fu_helpers.py`); `backend/tests/test_contract.py` stays green.
Frontend:
- `frontend/src/components/incidents/incident-form.tsx`, `incident-detail.tsx`, `incident-list.tsx`, `case-form.tsx` (commuting proposal), new `vehicle-section.tsx`.
- `frontend/src/lib/api/hse.ts` (+ `schema.d.ts` regenerated), `frontend/src/components/dashboard/*` (tile, C41 via `components/charts/chart-renderer.tsx`), `components/followup/*` (new body label).
- `frontend/scripts/i18n/p7-vehicle.py`; e2e `frontend/e2e/p7a-vehicle.spec.ts`, screenshots spec `screenshots-p7a.spec.ts` → `docs/screenshots/phase-7a/`.
Docs: spec §11 changes in `docs/specs/1-dashboard.md` (v1.11), `6f-incident-followup.md` (v1.1), `6g-scorecard-reports.md` (v1.1); `docs/PROGRESS.md`, `docs/DECISIONS.md`.

### Option B (7b, prototype)
Backend:
- `backend/app/models/access.py` — `Vehicle` (site_scope, use_class, seats, operating card, docs_verified_*, idle_from/to, readiness), new `backend/app/models/site_vehicle.py` (DriverAuthorisation, VehicleCheck, JourneyPlan).
- Enums: new `backend/app/core/site_vehicle_enums.py`; `backend/app/core/enums.py` — `Capability` 233–237 (after `export_log = "export_log.view"  # 232`) and role matrix; `hse_enums.py` CA source `site_vehicle`, ExpiringItemKind `site_vehicle_doc_expiry`, `driver_auth_expiry`.
- Migration `…_0017_site_vehicle_readiness.py` (or `_0016_` if built before 7a).
- Services: new `backend/app/services/site_vehicle/` (vehicles/readiness, authorisations, checks, journeys, settings); reads Phase 4 `services/cert/*` status and personnel-certificate hook, raises Phase 4 defects (source `pre_use_check`); 6d `services/field/execution.py` (owner type `vehicle_check`); Phase 5 / 6a hooks through the existing providers (`services/train/hook.py`, `services/med/hook.py`). **No change** to `services/access/gates.py` or gate reason codes.
- Routers `backend/app/api/routers/site_vehicles.py`; schemas `backend/app/schemas/site_vehicle.py` (SiteVeh-prefixed).
- KPIs `backend/app/kpi/site_vehicle.py`, `catalogue.py` (K-138…K-140), `engine.py`. No warning, chart or AI tool.
- Job `site_vehicle_daily` in `backend/app/scheduler.py`.
- Seed `backend/app/seed_site_vehicle.py` called from `app/seed.py` (after `seed_scorecard`, and after the 7a seed when present); 6d templates VPU-L/H/B; courses DEF-DRV, BUS-DRV.
- Tests `backend/tests/test_site_vehicle_*.py`.
Frontend:
- New `frontend/src/components/site-vehicles/` (vehicles and readiness, authorisations, pre-use checks, journey plans, settings), routes under `src/app/[locale]/(app)/site-vehicles/…`, sidebar entry `nav-site-vehicles` with a "Prototype" badge, `src/lib/api/site-vehicles.ts`.
- Edit `components/access/vehicles.tsx` (site fields), `components/dashboard/*` (three tiles). No gate screen changes.
- `frontend/scripts/i18n/p7-site-vehicle.py`; e2e `p7b-site-vehicles.spec.ts`, screenshots → `docs/screenshots/phase-7b/`.
Docs: §11 of 7b (0-foundation, 1-dashboard, 2-access-permits v1.8, 4 note, 5-training, 6a, 6d, 6g, 7a links).

## 6. Step lists

### A
1. Re-check numbering (§1) and read 7a v1.1 fully plus Phase 1 §3.3–§3.4 and I-4, 6f §3.1/§3.11.
2. Backend stage 1: models, enums, schemas, routes; export contract **v0.14.0**; commit `[skip ci]`; post "contract out" in PROGRESS.
3. Backend stage 2: services (VA-1…VA-15: report archive and lock, no client copy, recorded-not-counted), 6f rows, K-136/K-137, C41 (with the recorded-not-counted segment), T3–T5, dataset, seed (five VW1 incidents incl. 0215), tests for AC 1–32 (unit test VW1 exact: K-136 = 5, K-137 = 0.32). Apply §11 to 1-dashboard v1.11, 6f v1.1, 6g v1.1.
4. Frontend: gen:api, vehicle section and accident-report archive card on form and detail, "Recorded, not counted" badge and filter, register filters, dashboard tile and C41, i18n `p7-vehicle.py`, e2e p7a.
5. Design pass (05): before / after EN/AR, desktop and 390 px; findings `docs/design/phase-7a-findings.md`.
6. Fixer check (06): full e2e once on a fresh seed (baseline 312 passed, 0 failed), CI green; PROGRESS updated.

### B
0. If A is also chosen, do A first (numbering and §11.8 links); otherwise B stands alone.
1. Re-check numbering; read 7b v2.0 fully plus Phase 2 §3.12, Phase 4 §3.4 / §3.9 / §3.11 and list PCT, 5 HK5-x, 6a DRIVER-FIT, 6d §3.1–§3.5.
2. Backend stage 1: models, enums (capabilities 233–237), schemas (SiteVeh-prefixed), routes; contract bump per §2.
3. Backend stage 2 in build order 7b.1 → 7b.5; daily job; seed; tests for AC 1–24 (SW1–SW3 exact). Apply §11 changes. Keep it a prototype: build nothing listed under "Out of scope (security / logistics)".
4. Frontend: site-vehicles section with "Prototype" badges, journey-plan form and list (Overdue flag only), dashboard tiles, i18n `p7-site-vehicle.py`, e2e p7b.
5. Design pass; 6. Fixer check (full e2e once, CI green); PROGRESS.

## 7. Current state (2026-10-12, after the 7a / 7b fixer check)

- All modules built: Phases 0–5, 6a–6g, Option 7a (vehicle accident details) and Option 7b (site vehicle & plant readiness, Prototype), each with spec, backend, screens and design pass; fixer check done.
- CI green on `5155dab` ([run 38270472537](https://github.com/urkTish/HSE/actions/runs/38270472537)): backend lint, format, mypy, alembic, pytest, contract; frontend lint, typecheck, i18n, build and e2e (**340 passed, 0 failed, 33 skipped**, 43.5 min). CI runs the e2e on every push.
- Local full e2e on this (slower) machine: 329 passed, 10 failed, 33 skipped, 1 did not run (1.3 h); on a fresh-seed re-run of the 10, 7 pass and 3 are load timeouts parked in PROGRESS (all three pass on CI).
- Contract **v0.15.1**; latest decision **D-264**; latest migration `20261012_0017_site_vehicle_readiness.py`.
- Numbering in use: capabilities to 237, K-140, C41 (7a / 7b); before them K-135, E25, T25, C40. Some numbered AI tools and chart data of earlier modules are still parked (e.g. 6g T25, C39–C40); see PROGRESS "Parked". 7a/7b numbers continue after them regardless.
- Turki answered five questions on 2026-10-11 (§0); specs revised: 7a v1.1 (32 ACs), 7b v2.0 prototype (24 ACs). Still open: 7a §10 (4 items) and 7b §10 (2 items); none blocks the build.
