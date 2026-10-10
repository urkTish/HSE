# Handover: vehicle options 7a / 7b (planned, not built)

> **DO NOT START UNTIL TURKI (HSE Manager) SAYS GO, and only for the option he names (A = 7a, B = 7b; B includes A as stage 0).**

Written 2026-10-10 by the HSE Consultant agent. This file is self-contained: a fresh session can execute either option from it. A copy lives in the repo at `docs/HANDOVER-vehicle.md`.

## 1. The two options

| | Option A — `docs/specs/7a-vehicle-accident-details.md` | Option B — `docs/specs/7b-fleet-driver.md` |
|---|---|---|
| What | A vehicle-accident section on Phase 1 incidents: vehicles (own / contractor / hired / third party / unknown, plate, link to the Phase 2 vehicle), driver (worker or external, licence class and expiry checked at the time), road type, Najm / police report no., third-party damage, seat belt, speed, commuting link; police / Najm rows in 6f; K-136, K-137, C41 | Full module: landside fleet (extends the Phase 2 vehicle), driver authorisations (licence, DEF-DRV via Phase 5, DRIVER-FIT via 6a, points), pre-use checks on 6d templates with defect hold, journey plans with overdue escalation, monthly mileage, optional telematics CSV imports, site-gate vehicle checks; K-138…K-144, E26, T26, C42–C43, capabilities 233–240 |
| Size | 28 ACs, no new capability, no new screen (incident pages + dashboard) | 46 ACs, ~6 new screens, new jobs |
| Depends on | Phase 1, 2, 6f, 6g (all built) | **7a first**, then Phases 2, 5, 6a, 6d, 6g |
| Rough effort | 1 backend + 1 frontend session, short design pass | Like 6e/6g: backend, frontend, design pass each a full session |

Numbering reserved (do not reuse): 7a = K-136…K-137, C41. 7b = capabilities 233–240, K-138…K-144, E26, T26, C42–C43, CA source `fleet`, hook kind `driver_authorisation`. Check again before building (`grep` the specs, `docs/DECISIONS.md`, `backend/app/core/enums.py`); if anything moved, renumber in the spec first.

## 2. Repo and environment

- Repo `urkTish/HSE`, branch **`claude/hse-platform-build-kannxy`** (no main branch, no PRs, no other branches). Working tree `/home/claude/HSE`.
- **Backend** `backend/`: Python 3.12, uv, FastAPI, SQLAlchemy 2, Alembic, Postgres 16; pytest, ruff, mypy strict. Checks: `uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest`; migrations `uv run alembic upgrade head && uv run alembic check`.
- **Frontend** `frontend/`: Next.js App Router, strict TS, Tailwind, shadcn, TanStack Query, next-intl (`/en`, `/ar`, RTL). Checks: `npm run lint && npm run typecheck && npm run i18n:check && npm run build`, e2e `npm run test:e2e` (Playwright, Chromium at `/opt/pw-browsers`; never `playwright install` locally).
- **Contract-first:** `docs/contracts/openapi.yaml`, generated with `uv run python -m app.export_openapi` (CI checks `--check`). Current **v0.13.0**. Bump: 7a → v0.14.0, 7b → v0.15.0 (or v0.14.0 if B is built together with A; then say so in PROGRESS). Frontend types: `npm run gen:api`.
- **Postgres** local, user/password `hse`/`hse`, DBs `hse`, `hse_test`; start with `pg_ctlcluster 16 main start` if down. **No Docker.**
- **e2e:** `frontend/e2e/start-backend.sh` drops, migrates and seeds `E2E_DB_NAME` (default `hse_e2e`), runs the API on `E2E_BACKEND_PORT` (default 8000); frontend at `E2E_BASE_URL` (default http://localhost:3000). Shared clock `frontend/e2e/clock.ts`: `E2E_CLOCK_AT` default **2026-10-06T10:00+03:00**, passed to the API as `HSE_CLOCK_AT` (advancing). Specs 6g/7a/7b use `HSE_CLOCK_AT` = 2026-10-12 10:00 for backend tests; pick per test as the 6g tests do.
- **Private DB / ports when other agents run:** use your own `E2E_DB_NAME`, `E2E_BACKEND_PORT` and frontend port; run a clean backend from `git archive HEAD | tar -x -C /tmp/…` with `E2E_BACKEND_DIR=<that dir>` when backend/ has uncommitted work.
- **Screenshots** only with `SCREENSHOTS=1` (writes into `docs/screenshots/phase-…`); otherwise to `test-results/shots`.
- Full e2e run takes ~40 min. Run it once at the end, not in a loop.

## 3. Conventions (must follow)

- `docs/CONVENTIONS.md`: error envelope `{"detail":{"code","message","message_ar"}}`; 401/403/404/409/422; lists `{items,total,page,page_size}`; cookie `hse_session`; QR `HSE2:<kind>:<token>`.
- **D-202 schema prefixes:** a new Pydantic schema or enum whose plain name already exists in another module gets a module prefix (6e used `Env…`). Use `Veh…` / `Fleet…` (e.g. `FleetVehicleRead`, `VehIncidentVehicleRead`) so earlier OpenAPI component names do not change.
- **i18n:** strings are written as EN/AR pairs in `frontend/scripts/i18n/p<phase>-<name>.py` (dict `P`, leaves `[en, ar]`), then `python3 scripts/i18n/merge.py` (globs `p[0-9]-*.py`, runs `consistency.py` last) regenerates `messages/en.json` / `ar.json`. Use `p7-vehicle.py` (7a) and `p7-fleet.py` (7b); add only new keys. ICU: escape `<…>` in messages.
- **Design conventions:** `docs/design/consistency-pass-findings.md` and `docs/design/restyle-findings.md` (D-238: emerald brand `#0c574e`, platinum neutrals, safety-green split from brand; tokens only in `src/styles/tokens.css`). Irreversible record actions (void, revoke, withdraw, clear hold) go in the **page-end "Record actions" band** (`components/common/record-actions.tsx`); safety stops stay at the top. Month names, not `yyyy-mm`; plates, km and refs LTR inside RTL; compact cards at 390 px.
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
- `backend/app/models/hse.py` — `Incident` (new columns: vehicle_involved, road_type, road_location, journey_purpose, light, surface, report_authority, report_no, report_date, liability_pct_own, third_party_damage_*), new model `IncidentVehicle` (table `incident_vehicles`).
- `backend/app/core/hse_enums.py` — `ExternalBody` + `najm`; new enums RoadType, JourneyPurpose, VehicleOwnership, VehicleRole, LicenceCheck, etc.; `backend/app/core/followup_enums.py` — triggers `rta_public_injury`, `rta_public_no_injury`.
- `backend/alembic/versions/` — new `2026xxxx_0016_vehicle_accident.py` (latest is `20261010_0015_phase6g_scorecard_reports.py`).
- `backend/app/schemas/incidents.py` (Veh-prefixed schemas), `backend/app/api/routers/incidents.py`, `backend/app/services/incidents.py`, `services/injury_cases.py` (commuting proposal VA-7), `services/investigations.py` (VEHICLE_SECTION_INCOMPLETE, prompts VA-4), `services/access/vehicles.py` (read-only lookup, plate normalisation).
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

### Option B (7b) — after A
Backend:
- `backend/app/models/access.py` — `Vehicle` (fleet columns), new `backend/app/models/fleet.py` (DriverAuthorisation, JourneyPlan, JourneyCheckIn, MileageReturn, TelematicsImport, TelematicsEvent, VehicleCheck).
- Enums: new `backend/app/core/fleet_enums.py`; `backend/app/core/enums.py` — `Capability` 233–240 (after `export_log = "export_log.view"  # 232`) and role matrix; `access_enums.py` gate reason codes, hook kind `driver_authorisation`; `hse_enums.py` CA source `fleet`, ExpiringItemKind values.
- Migration `…_0017_fleet_driver.py`.
- Services: new `backend/app/services/fleet/` (vehicles, authorisations, checks, journeys, mileage, telematics, gate, hooks, settings); edit `services/access/gates.py`, `reasons.py`, `hooks.py`, `vehicles.py`; 6d `services/field/execution.py` (owner type `vehicle_check`); Phase 5 / 6a hook calls through the existing providers (`services/train/hook.py`, `services/med/hook.py`).
- Routers: new `backend/app/api/routers/fleet_*.py`; schemas `backend/app/schemas/fleet.py` (Fleet-prefixed).
- KPIs `backend/app/kpi/fleet.py` (+ `fleet_views.py`), `catalogue.py`, `engine.py`, `warnings.py` (E26), `charts.py` (C42–C43); AI `ai/tools.py` (T26 `get_fleet_summary`, T13 E26).
- Jobs `backend/app/fleet_jobs.py` + `backend/app/scheduler.py` (`fleet_daily`, `fleet_minute`).
- Seed `backend/app/seed_fleet.py` called from `app/seed.py` (after `seed_scorecard`); 6d templates VPU-L/H/B; courses DEF-DRV, BUS-DRV.
- Tests `backend/tests/test_fleet_*.py`.
Frontend:
- New `frontend/src/components/fleet/` (fleet register, authorisations, checks, journey board, mileage, telematics imports, settings), routes under `src/app/[locale]/(app)/fleet/…`, sidebar section `nav-fleet` (`components/shell`), `src/lib/api/fleet.ts`.
- Edit `components/access/vehicles.tsx` (fleet fields), `components/gate/*` (site-gate vehicle path), `components/dashboard/*` (road-safety band, C42–C43).
- `frontend/scripts/i18n/p7-fleet.py`; e2e `p7b-fleet.spec.ts`, `p7b-journeys.spec.ts`, `p7b-gate.spec.ts`, `p7b-kpis.spec.ts`, screenshots → `docs/screenshots/phase-7b/`.
Docs: §11 of 7b (0-foundation, 1-dashboard v1.12, 2-access-permits v1.8, 5-training, 6a, 6d, 6g, 7a).

## 6. Step lists

### A
1. Re-check numbering (§1) and read 7a fully plus Phase 1 §3.3–§3.4, 6f §3.1/§3.11.
2. Backend stage 1: models, enums, schemas, routes; export contract **v0.14.0**; commit `[skip ci]`; post "contract out" in PROGRESS.
3. Backend stage 2: services (VA-1…VA-12), 6f rows, K-136/K-137, C41, T3–T5, dataset, seed, tests for AC 1–28 (unit test VW1 exact). Apply §11 to 1-dashboard v1.11, 6f v1.1, 6g v1.1.
4. Frontend: gen:api, vehicle section on form and detail, register filters, dashboard tile and C41, i18n `p7-vehicle.py`, e2e p7a.
5. Design pass (05): before / after EN/AR, desktop and 390 px; findings `docs/design/phase-7a-findings.md`.
6. Fixer check (06): full e2e once on a fresh seed (baseline 312 passed, 0 failed), CI green; PROGRESS updated.

### B
0. Do A (above) if not done.
1. Re-check numbering; read 7b fully plus Phase 2 §3.12 / GC rules, 5 HK5-x, 6a DRIVER-FIT, 6d §3.1–§3.5.
2. Backend stage 1: models, enums (capabilities 233–240), schemas (Fleet-prefixed), routes; contract **v0.15.0**.
3. Backend stage 2 in build order 7b.1 → 7b.8; jobs; seed; tests for AC 1–46 (FW1–FW3 exact). Apply §11 changes.
4. Frontend: fleet section, journey board (overdue first), gate path, dashboard band, i18n `p7-fleet.py`, e2e p7b.
5. Design pass; 6. Fixer check (full e2e once, CI green); PROGRESS.

## 7. Current state (2026-10-10)

- All modules built: Phases 0–5 and 6a–6g, each with spec, backend, screens and design pass; platform restyle D-238 done.
- Full e2e: **312 passed, 0 failed** (25 skipped) on a fresh seed; CI green (backend: lint, format, mypy, alembic, pytest, contract; frontend: lint, typecheck, i18n, build, e2e).
- Contract **v0.13.0**; latest decision **D-238**; latest migration `20261010_0015_phase6g_scorecard_reports.py`.
- Numbering in use: capabilities to 232, K-135, E25, T25, C40. Some numbered AI tools and chart data of earlier modules are still parked (e.g. 6g T25, C39–C40); see PROGRESS "Parked". 7a/7b numbers continue after them regardless.
- Open questions for Turki on vehicles: 7a §10 (5 items) and 7b §10 (7 items).
