# Progress

## Current
- Phase: 1 — Dashboard (with AI)
- Module: dashboard & core data (spec `docs/specs/1-dashboard.md` v1.0)
- Step: Backend stage 2 implemented on contract v0.2.0 (no contract changes); frontend e2e green against the seeded backend. Next: phase demo and HSE Manager review of the open questions

## Phase log
- Phase 0 — Foundation: built, e2e green, design pass done (2026-10-05). The user asked to continue phase after phase without per-phase approval; open questions are collected below for a single review.

## Done

### Backend — Phase 1 contract v0.2.0 (stage 1)
- `docs/contracts/openapi.yaml` v0.2.0: 74 new paths (workforce returns/months/import, incidents, injury cases, investigations, external notifications, observations, inspection plans/inspections, corrective actions + extensions, HSE meetings, attachments + signed URLs, Phase 1 settings + AI transfer approval, reference lists, KPI engine endpoints, dashboard action panel/expiring items/preferences, AI ask (SSE)/insights/status/answers/logs, monthly reports). Phase 0 paths and schemas unchanged; capability enum extended with matrix rows 20-45.
- Notes for the frontend:
  - Decimals (man-hours, rates, %) are JSON strings already rounded half-up; every KPI value also has a `display` string. Show `display` as is (only re-map digits for `digits = arabic_indic`).
  - All `/kpi/*`, `/dashboard/action-panel` and `/ai/insights` take the same filters: `project_id` (repeat) or `all_projects`, `site_id`, `zone_id`, `zone_type`, `engagement_id`, `include_subcontractors` (default true), `tier`, `period` (+ `anchor`, or `start`/`end` for custom), `as_of`, `compare` (default previous).
  - Drill-down: `GET /kpi/metrics/{metric}` returns `sources.numerator/denominator` (entity type, count, first ids); `GET /kpi/metrics/{metric}/sources?part=` pages the records with `detail_path` (null if the user may not open it). Action-panel items carry `link {path, query}` that returns exactly the counted records.
  - Charts: `GET /kpi/charts/{C1..C9}` and AI answers both use `ChartSpec` (categories, axes, series with `color_role` tokens, bands, reference lines, optional table).
  - `POST /ai/ask` streams SSE (`AiStreamEvent`): `meta` → `status`* → `delta`* → `citations` → `chart`? → `recommendations`? → `done` (full `AiAnswer`); `error` ends the stream. Send `Accept: application/json` to get only the final answer (Prism mock serves this). Hide the assistant when `GET /ai/status` says `enabled = false` (AC73).
  - Injury cases: identity/medical keys are absent (not null) without capability 29/30; `redacted_groups` says which. Anonymous observations omit `observer`.

### Backend — Phase 1 implementation (stage 2, contract v0.2.0 unchanged)
- All v0.2.0 handlers are implemented (no more 501s). Migration `0002` matches the models (`alembic check` is clean).
- Services implement the spec rules and state machines for: workforce returns, month lock/unlock/restatement and import (dry run, 60 min expiry, insert-only/upsert, E01–E14, W01–W06, EN/AR headers, CSV/XLSX); incidents, injury cases (derived/confirmed classification, PDPL redaction by capabilities 29/30, encrypted IDs), investigations, external notifications; observations; inspection plans and inspections; corrective actions with extensions and verification; HSE meetings; attachments (local storage, scan status `skipped`); Phase 1 settings and the AI transfer approval.
- KPI engine `app/kpi/`: one engine for every K-01…K-47 formula with the spec's rounding. Unit tests reproduce W1–W8 to the decimal. On top of it: scope building (role scope first, D-3), comparisons, trends (trend allowed only with ≥ 6 monthly points), breakdowns, the safety pyramid, the league table, leading warnings E1–E4, data completeness and charts C1–C9. Dashboard queries load facts per scope in a fixed number of queries (no N+1), using the indexes in `0002`.
- Permissions follow the §5.10 matrix rows 20–45. Sensitive reads are audited: identity/medical reveal, sensitive breakdowns and exports. `GET /history/{entity}/{id}` covers the Phase 1 entities.
- Jobs (`app/hse_jobs.py`, 20 jobs, scheduled in `app/scheduler.py`):
  - CA due-soon and overdue alerts, with escalation once per day
  - incident and notification alerts
  - high-risk observations without a CA (24 h)
  - missing daily returns and the completeness check
  - inspection generation, missed inspections and inspections-due alerts
  - leading warnings and LTI-free milestones
  - month auto-lock and injury identity anonymisation
- AI layer (`app/ai/`):
  - Anthropic Python SDK client with tool use and server-side fallbacks. Models come from config: default `claude-sonnet-5-5`, deep analysis `claude-opus-5-5`.
  - 15 tools, each a thin wrapper over the KPI engine and read-only queries, run with the caller's permissions. Tool outputs are de-identified (no names, IDs or contacts) and report `scope_narrowed`.
  - Number-grounding check with one regeneration, then a fallback message and raw table. Language checks: AI-8 trend wording, AI-9 association/causal wording, AI-11 recommendation hierarchy.
  - The server adds the data notes and the Sources block.
  - Prompt masking (mobile, email, ID numbers) with warnings to the user.
  - Rate limits: 60 questions per user per day, 10 reports per project per month.
  - Answer cache and insights cache keyed by the data snapshot.
  - `ai_logs` holds masked prompts and excerpts only.
  - Without `ANTHROPIC_API_KEY` the service returns 503 `AI_UNAVAILABLE`; rule-based insights still work.
  - Monthly report: 13 sections with backend-rendered tables. The model writes the narrative only, checked for grounding. Lifecycle draft → reviewed → published; publishing freezes the figures hash, and a later restatement shows "figures revised since publication".
- Seed (`app/seed_hse.py`, loaded by `python -m app.seed`):
  - Appendix A: 13 months plus ramp-up, deterministic.
  - ANIA-EXP monthly MH and case counts equal W3; observations, inspections, CAs raised, month-end overdue, DO/PD/ENV and toolbox talks equal A.3.
  - July 2026 completeness is 98.1 % (GULFPAVE filter: 90.3 %); E1 fires for Jul 2026 only.
  - Named incidents follow A.5.6. Fake IDs match `^[12]0{5}\d{4}$` and every record has `seed_fake = true`.
  - Each project gets a clearly fake AI transfer approval (`SEED-FAKE-AI-APPROVAL`), so the assistant works once a key is set.
- Tests: 213 passed. They cover AC1–AC60 and AC64–AC78 with a backend side (`test_AC<n>_…`; AC61 checks the backend part), using a fake LLM client (`tests/fake_llm.py`). ruff, ruff format, mypy (strict), `alembic check` and `export_openapi --check` are all green.

### Frontend — Phase 1 Dashboard (against contract v0.2.0)
- Home page = KPI dashboard for capability 38 (users without it keep the Phase 0 home): filter bar with every D-2 filter in the URL (shareable, survives reload; saved per user via `/dashboard/preferences`, a URL with filters wins), completeness / provisional / restated chips and the backend banners, headline band (LTI-free days and hours, man-hours period/ITD, headcount, direct/sub split), lagging and leading tiles (backend `display`, first comparison Δ with direction, 12-month sparkline, RAG + target, warnings), Phase 3 placeholders, charts C1–C3/C5/C7/C8/C9 through one `ChartRenderer` (token palette, semantic colour roles, small multiples instead of a second axis, bands, reference lines, legend, table toggle, RTL mirroring), C7 dimension/measure switch (sensitive dimensions only with `breakdown.sensitive_view`), safety pyramid, sortable contractor league table with roll-up, action panel (each item opens the pre-filtered list), due-soon list, insights, KPI/league CSV exports (capability 42).
- Every number drills down: tiles, headline values, pyramid layers and league cells open a dialog with value, numerator/denominator, warnings and the paged source records (each linking to its detail page). Monthly chart bars whose series key is a KPI metric drill into that month.
- No KPI is computed in the browser: values are the backend `display` strings; the only change is the digit mapping when the project's `digits` setting is `arabic_indic`.
- AI assistant side panel (dashboard header, hidden unless `/ai/status` says enabled + can_ask): SSE streaming parser (meta/status/delta/citations/chart/recommendations/done/error, keep-alive ignored), stage line, markdown answer, Sources list, chart, recommendations ordered by hierarchy of controls with "Create corrective action" (pre-fills the CA form), AI label, masked-input warning, insufficient-data note, fallback table, pre-stream errors (AI_DISABLED / AI_RATE_LIMITED / AI_UNAVAILABLE) and mid-stream `error` shown as such, quota, stop, new conversation. "AI unavailable" state when no provider is configured (AC75).
- Monthly reports: list, "Draft monthly report" (202 then polling every 3 s until draft/failed), view in EN or AR, narrative edit (EN + AR side by side, tables read-only), transitions (mark reviewed, publish, return to draft with comment), "figures revised since publication" banner, print view (`window.print`, shell hidden).
- Modules, each list → detail → create/edit → workflow actions: workforce returns (list with filters, form, verify/bulk verify), import (dry-run report with row codes, commit/discard), month lock/unlock; incidents (register with all filters incl. action-panel links, form with near-miss/primary-type/severity/airside rules and local draft, detail with cases, external notifications, linked CAs, attachments, transitions incl. investigation assignment and HiPo higher-control justification), excluded-cases list, injury cases (form omitting redacted groups, detail with redaction note, masked ID + reveal, medical card, classification confirm/override), investigation (root causes, extension); observations (anonymous option, photos, close); inspection plans and inspections (unplanned form, results with findings and inline CAs, cancel); corrective actions (list, form incl. AI prefill, evidence, verify/reject, extensions request/decide); HSE meetings; HSE settings (ranges, targets from the catalogue, AI transfer approval record/withdraw); reference lists; AI log.
- i18n: all new strings in EN and AR (`scripts/i18n/p1-*.py` → `npm run i18n:check`); RTL verified on the dashboard, AI panel and forms; mobile layout checked at 390 px (no horizontal page scroll).
- E2E (Playwright, real backend): full suite 71 passed, 2 skipped (screenshot specs, on demand) on a fresh migrated + seeded DB — 35 Phase 0 + 36 Phase 1 tests in `e2e/p1-*.spec.ts` — dashboard (AC55, 59, 60, 61, 62, 63, 64, filters in URL, drill-down, charts, mobile), AI (AC65, 72, 73, 74, 75, insufficient data, errors, Arabic) via a recorded SSE stream in `e2e/fixtures/ai-stream.ts` (typed against the contract, replayed with `page.route`; test-only), workforce/import (AC2, 3, 4, 7, 10), incidents/PDPL (AC13, 19, 20, 21, 29, 30, 31, 33), CAs (AC40, 41, 42, 43), observations (AC35) and create flows for observations, inspections, meetings, settings, reports. Phase 0 specs unchanged except a wait in AC12 (options load asynchronously).
- Screenshots: `docs/screenshots/phase-1/` (run `SCREENSHOTS=1 npx playwright test e2e/screenshots-p1.spec.ts`).

### Backend — Phase 0 Foundation (contract v0.1.0)
- Schema + Alembic migration `0001` (audit log append-only trigger, `hse_audit_purge()` SECURITY DEFINER purge path, grants for an optional `hse_app` role).
- Auth: login/logout/me, httpOnly `hse_session` cookie + Bearer, server-side sessions (30 min idle / 12 h absolute, immediate revocation), lockout 5/15 min/15 min, identical failure responses, password policy (12+ chars, 3 of 4 classes, not email name, not in top-10k breached list), invites (72 h, resend supersedes), password reset (60 min, single use), privacy-notice gate (`PRIVACY_ACK_REQUIRED`).
- Permission matrix §5.10 in `app/services/permissions.py`, union per project, site restriction (rule 11), contractor tree / own-engagement scoping (rule 10), out-of-scope → 404 + `access_denied` audit, suspended contractor → 403 `CONTRACTOR_SUSPENDED`, viewer → 403 `READ_ONLY_ROLE`.
- Projects/sites/zones with state machines §4.1/§4.4, airside rules 18-21, closed project read-only (rule 22).
- Contractors (state machine §4.2, blacklisting effects rule 27, Arabic-normalised search rule 45, ICU collation sort rule 46) and engagements (tier/parent rule 25, approved-only rule 26).
- Users & role assignments: rule 13 (last HSE Manager), 14 (officer limits), 15 (no self-change), 16 (SoD), 29 (employer match).
- Settings (rule 30-32, base labels), audit log (hash chain, verify, retention purge, officer view without IP), change history, CSV/XLSX exports (rule 49), in-app notifications + email outbox, scheduled jobs (`app.jobs`, `app.scheduler`), K1 rate in `app/kpi`.
- Seed (`app.seed`, idempotent, Appendix A). Dev password: `SEED_PASSWORD` in `.env.example`.
- Tests: 96 passing; every backend-side AC (1-25, 28, 30-35) has a test named `test_AC<n>_...`. AC26 backend part (setting round-trip) tested; AC27/AC29 are frontend.

### Frontend — Phase 0 Foundation (against contract v0.1.0)
- Stack: Next.js 16 (App Router, TS strict, no `any`), Tailwind 4 + shadcn-style components on Radix, TanStack Query, React Hook Form + Zod, next-intl (`/en`, `/ar`, `dir=rtl`), openapi-fetch with types from `npm run gen:api`; Prism mock via `npm run mock` (use `BACKEND_URL=http://localhost:4010 npm run dev`).
- Design tokens in one file: `frontend/src/styles/tokens.css` (mapped to Tailwind in `src/app/globals.css`).
- Screens: login (invalid/locked/session-expired/signed-out messages), privacy-notice acknowledgement (EN/AR text), invitation acceptance (`/invite?token=`), forgot/reset password; app shell (sidebar, topbar, project switcher, EN/AR switch saved to profile, notifications bell, user menu); placeholder home (Phase 1 dashboard goes here); projects list/create/edit/detail + status transitions; project settings (KPI bases with API labels, Hijri/digits/date format, retention, live date preview); sites list/detail/form + transitions; zones list/detail/form incl. airside attributes + transitions; contractors list/detail/form + full workflow incl. blacklist/lift blacklist; project engagements (tier tree, parent limited to tier − 1, review-flag clearing); users list/invite/edit/detail with role assignments (assign/revoke, SoD and officer limits surfaced), deactivate/unlock/reactivate/resend invite; audit log with filters, details/diff and chain verification; change-history panel on every detail page; CSV/Excel export buttons on every list; own profile + password change.
- Role-aware UI from `Me` capabilities/read_only (server still enforces); contact fields treated as optional; error codes mapped to EN/AR text; dates in Asia/Riyadh with optional Umm al-Qura Hijri (ICU).
- i18n: 574 keys in `messages/en.json` and `messages/ar.json`; `npm run i18n:check` fails on a missing/empty key or an untranslated Arabic value (AC29). Message keys are typed, so typecheck fails on unknown keys.
- E2E: 33 Playwright tests (`frontend/e2e`) run against the real backend on a freshly created, migrated and seeded database (`e2e/start-backend.sh`). Covered UI-side ACs: 1-15, 17, 18, 20, 21, 22, 23, 24, 25, 26, 27, 28, 31, 33 (+ login AR/RTL, language switch, logout, session expiry). AC19 has no seeded DLIFT user (backend test covers it); AC16/30/32/34/35 have no UI side.
- CI: `frontend` job in `.github/workflows/ci.yml` (npm ci, lint, typecheck, i18n check, build, Playwright with Postgres service + real backend via uv).
- Screenshots: `docs/screenshots/phase-0/` (login EN, login AR, projects list AR, zone detail EN).

### Design pass — Phase 0 (UI/UX Designer)
- Design system: `frontend/src/styles/tokens.css` is the only token file. It defines colour roles, safety semantics, a colour-blind-safe chart series palette (8 slots, light and dark), the type scale, spacing, radius, elevation and touch/control heights. Light and dark themes meet WCAG AA in both: status text ≥ 5.5:1, control borders ≥ 3:1.
- IBM Plex Sans and IBM Plex Sans Arabic are self-hosted (`@fontsource-variable/ibm-plex-sans`, `@fontsource/ibm-plex-sans-arabic`). Arabic gets taller lines and no letter-spacing or upper-casing.
- Theme toggle (Light / Dark / Match device) in the top bar and on auth pages, stored per device, applied before first paint.
- Phones:
  - two-row top bar with a full-width project switcher
  - drawer navigation with a close button
  - tables become labelled cards (`TD label`)
  - filters fold behind "More filters"
  - 44 px controls everywhere on touch screens
  - 16 px inputs (no iOS zoom)
- RTL fixes: sidebar icons are not mirrored, the tree connector is mirrored, and LTR codes are isolated in spans.
- Polish: sidebar active indicator, alerts, badges, empty state, Yes/No icons, auth page brand band, project tabs, notifications.
- No business logic, API, permission or data changes.
- New e2e `e2e/design.spec.ts` (theme persistence; phone drawer, 44 px target, stacked-row labels in AR). Suite: 35 passed, 1 skipped (on-demand screenshots).

## Next
- Phase 1 demo; then Phase 2 per the roadmap

## Parked
- (Phase 1, D-10) PDF export of the dashboard/monthly report: deferred by the coordinator. The frontend print view covers it for now.
- (Phase 1, I-15) The check that the supervisor named on an incident holds a supervisor role on that site is not implemented; the field is free text.
- (Phase 1) Attachment virus scanning: files are stored locally with `scan_status = skipped`. A scanner/object store is not chosen yet.
- (Phase 1) Ramadan dates are a table for 2025/2026 marked VERIFY. Replace them with an Umm al-Qura library before go-live.
- Email delivery: messages go to the `email_outbox` table; an SMTP/provider sender is not built (no provider chosen).
- MFA (`mfa_enabled` stored, not enforced) — waits for §10 Q3.
- Data-subject requests (P8) and breach records (P9) — no Phase 0 endpoints; propose for Phase 6 / when the Consultant specs them.
- Per-entity retention/anonymisation (P7) — no personal-data entities with retention defaults in Phase 0 beyond the audit log.

## Open questions for the HSE Manager
- (Backend, Phase 1, defaults pending the HSE Manager — DECISIONS 18-20) AI-8 trend wording; D-10 PDF export deferred; who may see observations/inspections/CAs (incident-register scope via capability 31 plus own/verifier records).
- (Backend, Phase 1, §6.9 E4) A "repeat event" is a recordable case with the same mechanism in the same tier-1 tree within 90 days. With the seed volumes this fires in most months. Should it be limited to LTI/RWC, or need ≥ 2 repeats?
- (Backend, Phase 1, W4) The spec's longest LTI-free run (112 days) does not match its own LTI dates (the actual gaps are longer). The engine computes from the dates.
- (Backend, Phase 1) GOSI notification deadline is set to 3 days from the incident date (spec §10 Q7 still open).
- (Backend, §5.10 row 8) HSE Officers currently see the whole contractor register (needed to onboard and engage contractors). Should they see only contractors engaged on their projects plus drafts they created?
- (Backend, §5.4 rule 28) Users of a suspended contractor are blocked from business-data writes but may still edit their own profile and password. Confirm.
- (Backend, §7) CR-expiry alerts go to reps of the contractor *and* of its parent engagements (the reps whose tree contains it). Confirm.
- (Backend, §5.6 rule 40) Audit entries with no project (logins, contractor master changes) use an org-wide retention (`ORG_AUDIT_RETENTION_YEARS`, default 5). Confirm.

## Contract requests
- (Frontend, medium) `ChartSeries.metric` (KpiMetric | null) and, for period axes, `ChartCategory.start`/`end`: lets a click on a bar/point drill into the exact records. Today the UI drills only when a series key happens to be a metric id (e.g. `K-21`) and derives the month from the category key.
- (Frontend, low) `metric` on each pyramid layer (and one metric for RWC+JTC, e.g. a K-07/K-08 combined drill): the UI maps layers to K-05/06/07/09/12/13/30 itself; RWC_JTC drills K-07 only.
- (Frontend, low) A capability for HSE meetings (none in §5.10): the UI gates meeting edits on `inspection.plan_manage` as an assumption.
- (Frontend, low priority, not blocking) `GET /contractors/{id}/engagements` (engagements of one contractor across the caller's projects) so the contractor detail page can list where a firm is engaged. Today that view would need one request per project.

## Design proposals
L items from the Phase 0 design pass, waiting for the user's decision at the phase demo (details in `docs/design/phase-0-findings.md`):
- **P1. Two-line dates.** Show the Hijri date as a muted second line under the Gregorian date in tables and detail fields, instead of "01 Jun 2025 · 5 Dhuʻl-Hijjah 1446 AH" on one line that wraps mid-date. Needs `useFormatters` to return date parts and a `<DateText>` component used everywhere. Data stays the same; only the layout changes.
- **P2. Sticky mobile action bar on detail pages.** On phones the status actions (suspend, close, archive, deactivate) now come after all the details and the history. Proposal: a sticky bottom bar with the primary action, and the others in a menu. The same pattern will serve Phase 3 PTW actions (suspend, close) in the field.
- **P3. Searchable project switcher.** Replace the native select with a combobox: search by code or name, recent projects first, project status shown. This matters once there are more than about 10 projects.
- **P4. Date settings in cross-project lists** (frontend note). Today the projects, contractors and users lists use the *current* project's Hijri/digit settings. Recommendation: keep one consistent format per list (the current project's, as now), and say so in the list footer ("Dates shown in ANIA-EXP display settings"). Mixing formats row by row is harder to scan. Needs the user's call.
- **P5. Collapsible desktop sidebar (icon rail).** Gives about 190 px back to wide tables (audit log, Phase 1 registers) at 1366 px.
- **P6. Print/export styles** for the Phase 1 monthly report and the Phase 3 permits: project logo, bilingual header, page footer with audit hash. Belongs with those phases; noted so the token set (series and safety colours) is reused there.
