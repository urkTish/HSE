# Decisions

| # | Date | Decision | Why |
|---|---|---|---|
| 1 | 2026-10-05 | All phases are developed on one working branch (`claude/hse-platform-build-kannxy`) instead of `phase-<n>/<module>` branches; each phase is a reviewable set of commits. | The session can only push to its designated branch. |
| 2 | 2026-10-05 | Audit log append-only is enforced by a DB trigger; the only delete path is the `hse_audit_purge()` SECURITY DEFINER function. A restricted `hse_app` role (if present) gets INSERT/SELECT only. | Spec rule 36; works even when the app connects as table owner in dev. |
| 3 | 2026-10-05 | Audit hash chain verification accepts sequence gaps only where a `retention_purge` entry recorded the purged sequence ranges. | Per-project retention leaves gaps in the global chain; unrecorded gaps (manual deletes) are still detected. |
| 4 | 2026-10-05 | Audit entries that must survive a failed request (`access_denied`, `login_failed`) are queued and written after rollback by the DB dependency. | A 404/401 response rolls back the request transaction. |
| 5 | 2026-10-05 | Sessions are stored server-side (`user_sessions`) and checked on every request; the JWT carries only user and session ids. | Rules 4 and 7 (idle timeout, revocation within 60 s). |
| 6 | 2026-10-05 | Lockout responds `ACCOUNT_LOCKED` only when the password is correct; otherwise the generic `INVALID_CREDENTIALS`. | AC3 needs a locked response; this leaks the least to guessers (rule 3). |
| 7 | 2026-10-05 | HSE Officers see the whole contractor register (with contacts); other roles see contractors engaged within their scope. | Officers onboard contractors (capability 5) before any engagement exists. Open question logged. |
| 8 | 2026-10-05 | Site restrictions (`site_ids`) on an assignment limit site/zone records for every role, not only S-scope roles. | Rule 11 is stated for any assignment. |
| 9 | 2026-10-05 | Duplicates return 409 `DUPLICATE_VALUE` (with field errors); expired invite/reset links return 410. | Conflict vs validation; the frontend shows field errors either way. |
| 10 | 2026-10-05 | Zone airside attributes are a nested `airside` object in the API, stored as flat nullable columns. | Clean typing for the frontend; rule 19 becomes 'object present iff airside'. |
| 11 | 2026-10-05 | SoD (rule 16) is checked before the employer/engagement rule (29). | AC13 expects `SOD_CONFLICT` regardless of employer data. |
| 12 | 2026-10-05 | Emails go to an `email_outbox` table (EN/AR by recipient language); no SMTP sender yet. | No provider decided; keeps flows testable. |
| 13 | 2026-10-05 | Hijri dates are formatted by the frontend (ICU islamic-umalqura); the backend stores `show_hijri`/`hijri_calendar` only. | Display concern (rule 34, K3). |
| 14 | 2026-10-05 | Breached-password list: SecLists 10k-most-common (MIT) in `backend/app/data/`. | Rule 2. |
