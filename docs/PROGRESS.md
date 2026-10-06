# Progress

## Current
- Phase: 1 — Dashboard (with AI)
- Module: dashboard & core data (spec `docs/specs/1-dashboard.md` v1.0)
- Step: Contract v0.2.0 published (backend stage 1: schemas + routers, handlers return 501); backend implementation next

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
- Phase 1 — Dashboard (with AI)

## Parked
- Email delivery: messages go to the `email_outbox` table; an SMTP/provider sender is not built (no provider chosen).
- MFA (`mfa_enabled` stored, not enforced) — waits for §10 Q3.
- Data-subject requests (P8) and breach records (P9) — no Phase 0 endpoints; propose for Phase 6 / when the Consultant specs them.
- Per-entity retention/anonymisation (P7) — no personal-data entities with retention defaults in Phase 0 beyond the audit log.

## Open questions for the HSE Manager
- (Backend, §5.10 row 8) HSE Officers currently see the whole contractor register (needed to onboard and engage contractors). Should they see only contractors engaged on their projects plus drafts they created?
- (Backend, §5.4 rule 28) Users of a suspended contractor are blocked from business-data writes but may still edit their own profile and password. Confirm.
- (Backend, §7) CR-expiry alerts go to reps of the contractor *and* of its parent engagements (the reps whose tree contains it). Confirm.
- (Backend, §5.6 rule 40) Audit entries with no project (logins, contractor master changes) use an org-wide retention (`ORG_AUDIT_RETENTION_YEARS`, default 5). Confirm.

## Contract requests
- (Frontend, low priority, not blocking) `GET /contractors/{id}/engagements` (engagements of one contractor across the caller's projects) so the contractor detail page can list where a firm is engaged. Today that view would need one request per project.

## Design proposals
L items from the Phase 0 design pass, waiting for the user's decision at the phase demo (details in `docs/design/phase-0-findings.md`):
- **P1. Two-line dates.** Show the Hijri date as a muted second line under the Gregorian date in tables and detail fields, instead of "01 Jun 2025 · 5 Dhuʻl-Hijjah 1446 AH" on one line that wraps mid-date. Needs `useFormatters` to return date parts and a `<DateText>` component used everywhere. Data stays the same; only the layout changes.
- **P2. Sticky mobile action bar on detail pages.** On phones the status actions (suspend, close, archive, deactivate) now come after all the details and the history. Proposal: a sticky bottom bar with the primary action, and the others in a menu. The same pattern will serve Phase 3 PTW actions (suspend, close) in the field.
- **P3. Searchable project switcher.** Replace the native select with a combobox: search by code or name, recent projects first, project status shown. This matters once there are more than about 10 projects.
- **P4. Date settings in cross-project lists** (frontend note). Today the projects, contractors and users lists use the *current* project's Hijri/digit settings. Recommendation: keep one consistent format per list (the current project's, as now), and say so in the list footer ("Dates shown in ANIA-EXP display settings"). Mixing formats row by row is harder to scan. Needs the user's call.
- **P5. Collapsible desktop sidebar (icon rail).** Gives about 190 px back to wide tables (audit log, Phase 1 registers) at 1366 px.
- **P6. Print/export styles** for the Phase 1 monthly report and the Phase 3 permits: project logo, bilingual header, page footer with audit hash. Belongs with those phases; noted so the token set (series and safety colours) is reused there.
