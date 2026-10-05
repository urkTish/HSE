# Progress

## Current
- Phase: 0 — Foundation
- Module: foundation (auth & roles, projects/sites/zones, contractors, audit log, i18n/RTL shell, CI)
- Step: Build (backend implemented & tested; frontend in progress)

## Done

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

## Design proposals
