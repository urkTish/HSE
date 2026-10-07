# Progress

## Current
- Phase: 2 — Site / Airport access permits
- Module: site & airport access permits (spec `docs/specs/2-access-permits.md`)
- Step: Backend Phase 2 stage 2 done (contract 0.3.1, frontend issues fixed); Frontend Phase 2 built against v0.3.0, e2e green (104 passed); design pass next

## Phase log
- Phase 0 — Foundation: built, e2e green, design pass done (2026-10-05). The user asked to continue phase after phase without per-phase approval; open questions are collected below for a single review.
- Phase 1 — Dashboard (with AI): built, e2e green, design pass done (2026-10-06).

## Done

### Frontend — Phase 2 Site / Airport access (against contract v0.3.0)
- Screens (list → detail → create/edit → workflow actions, EN/AR + RTL, phone layout):
  - workers (masked ID with reveal-on-demand plus reason, deployments, eligibility per zone, access card with QR and printed ref);
  - induction courses and inductions (signature pad, language-mismatch amber warning);
  - zone profiles;
  - pass setup (categories / areas), pass applications (stepper: submit, endorse, lodge, background check, approve, issue) and airport passes with limiting factor;
  - ADPs and airside offences;
  - vehicles (Arabic plate with LTR digits), AVPs with inspection checklist, sticker and print;
  - NOTAM works requests (UTC times, late-request justification, forward, issue);
  - obstacle clearances with live height / OLS preview and decision with conditions plus linked NOTAMs;
  - WAPs (form, crew, submit/approve, suspend/resume with FOD check), WAP board and print view with QR;
  - ops events (LVP etc.) declare/end with the suspended WAPs;
  - credential lifecycle (suspend / revoke / reinstate);
  - gates and devices (register device: token shown once; revoke);
  - access settings (§3.22 ranges, hook policies per kind with provider badge, PATCH sends only changed keys);
  - gate log (filters incl. admitted-despite-denial, late exit, Riyadh day range; export).
- Gate check screen `/gate` (outside the app shell):
  - Runs in a device session (httpOnly cookie) or as a user with `gate.check`. A device token sign-in is offered on 401, and a revoked device ends the session.
  - Mobile-first, one-handed. Gate / zone / direction pickers. Manual printed-ref entry. Camera QR via `@zxing/browser` (dynamic import, rear camera, duplicate reads ignored for 5 s).
  - The e2e test hook is `window.__hseGateScan(payload)`.
  - Big solid-colour verdict (GRANTED green, WARN amber with black text, DENIED red, PENDING blue) with reasons coloured by deny/warn, person / vehicle / WAP cards, escort/driver pairing countdown with polling, and an auto-clear countdown.
  - "Admitted despite denial" requires a reason of at least 10 characters and is recorded.
  - Offline banner.
- Hook `warn` results are amber everywhere, never errors.
- Validation field errors are listed under the form message (VALIDATION_ERROR only).
- Dashboard: access band (passes, ADPs, AVPs, WAPs, obstacles, active ops events; K-48 headline) linking to the registers, a gate filter (`gate_ids`), and charts C10–C12 for `access_kpi.view`.
- Sidebar: "Gate check" item for `gate.check`.
- i18n: `scripts/i18n/p2-*.py`. `limitingFactor` keys nested (no dots in key names). New `joinList` uses the locale's list separator (the English UI was showing the Arabic comma).
- E2E (Playwright, real backend, fresh DB migrated and seeded with the Phase 2 seed): full suite 104 passed, 2 skipped (the on-demand Phase 1 screenshot specs). That is 33 Phase 2 tests plus all Phase 0/1 tests.
  - `p2-smoke`: every Phase 2 register in EN and AR, with no error state, raw keys or page errors.
  - `p2-workers`: masked ID with unmask reason and no caching; zone-specific course plus zone profile; language-mismatch amber warning; access card with QR and printed ref; contractor scope.
  - `p2-passes`: pass category/area setup; apply with ID-copy upload, submit, endorse, lodge; approval refused without a background check (AP-4), then cleared, approved and issued with limiting factor.
  - `p2-vehicles`: Arabic plate with LTR digits; duplicate plate (AC40); AVP inspection with no n.a. for the amber beacon (AC39); issue, sticker and print.
  - `p2-works`: late NOTAM request with justification (AC41); forward and issue; obstacle live preview, and a decision refused without the required conditions and linked NOTAM (AC42, OB-7).
  - `p2-waps`: 31-day WAP refused (AC48); contractor request then issuer approval; board and print QR; viewer sees no crew names or numbers (AC53); LVP declare/end with suspension and FOD resume.
  - `p2-gate`: site gate and device token shown once; mobile EN/AR GRANTED/DENIED; QR test hook; admitted despite denial, then the gate log; revoked device ends the session; offline banner; user gate selection and exit.
  - `p2-settings`: §3.22 ranges; hook block refused (HK-4); no settings nav for a contractor rep; access band and C10–C12; a Phase 2 action-panel item opens the filtered gate log.
  - The camera is never used in tests: scans go through manual entry or `window.__hseGateScan`.
  - Phase 1 spec change: the drill-down assertion in `p1-dashboard` now waits 30 s. Its request queues behind the dashboard's first KPI requests on the heavier seed.
- Screenshots in `docs/screenshots/phase-2/`:
  - gate GRANTED / DENIED, mobile, AR and EN;
  - WAP board;
  - worker detail with masked ID;
  - pass application (draft);
  - dashboard access band.

#### Phase 2 — backend issues found by the frontend (all fixed by the backend in stage 2, contract 0.3.1 — see "Backend — Phase 2 implementation" below)
- Resolved during the run:
  - Attachments, `/kpi/access` and the Phase 2 action-panel items are now live.
  - The backend agent fixed the slow `/kpi/*` calls (all access facts were loaded on every request).
- `GET /history/{entity_type}/{id}` returns 404 "History not found" for Phase 2 entity types (worker, gate, vehicle, notam_request, obstacle_clearance, …). The history panels on those pages show the error state.
- KPI requests are CPU-bound and serialised in one API process. A full airport dashboard is about 15 requests at 0.5–1.2 s each (`/kpi/dashboard` and the action panel about 1.1 s). The UI now loads C10–C12 only when they scroll into view. More API workers or caching would help in production.
- The site-gate general induction check uses the first `general_site` course of the project (arbitrary order). It ignores whether the course is active and does not prefer code GEN. A second general_site course makes workers fail at site gates with INDUCTION_MISSING.
- A WAP read returns the supervisor's `worker_no` to users without `worker.view` (the crew is hidden, but the supervisor is not). The UI hides it (PDPL), but the API should not send it.
- `FieldError.msg` texts are English only, so Arabic forms show English field errors.
- Banning a worker revokes the card, so the gate answers CREDENTIAL_REVOKED rather than WORKER_BANNED. This may be intended; please confirm.
- Not covered by UI e2e yet:
  - escort/driver pairing at the gate (the screen and polling are built);
  - ADP RTF requirement (AC33) and offence entry;
  - credential suspend/revoke/reinstate screens.
  The backend tests cover these rules.

### Backend — Phase 2 implementation (stage 2, contract v0.3.1)
- All 125 Phase 2 operations are live (no more 501). Services under `app/services/access/` (workers, inductions, profiles/eligibility, passes, driving, vehicles, works, waps, credentials/lifecycle, gates, exports, dashboard items, cascades); KPI engine K-48…K-60, K-53b, C10–C12, band, E5–E7 (`app/kpi/access*.py`); AI T14 `get_access_kpis`; seed `python -m app.seed_access` (Appendix A, ~4,000 workers, 313,770 gate rows).
- Jobs (`app/access_jobs.py`, wired in `app/scheduler.py`): `access_daily` 00:05:30, `credential_alerts` 07:00:30, `access_minute` every minute (incl. gate pairing timeouts — coordinator), `access_retention` Fri 03:30. See DECISIONS 37–38.
- Phase 0 contractor status changes cascade to access (LC-7 suspend WAPs; LC-8 blacklist: demobilise, revoke, notify officers).
- Tests: every AC 1–73 has a `test_P2AC<n>_…` test (`tests/test_access_*.py`), plus X1–X11, jobs, cascades, exports, attachments, the frontend follow-ups and the KPI cache. Full suite: see the run below.
- Fixed from the frontend list above:
  - `GET /history/{entity_type}/{id}` serves every Phase 2 entity type (D-50).
  - The WAP read no longer sends the supervisor (or any worker_no) to callers without capability 46; expiring-item titles/refs say "Worker" for them (D-48).
  - Site-gate / visitor induction check: any active course of the type, GEN preferred (D-47).
  - Field errors carry `msg_ar` (D-49).
  - KPI speed: lazy access facts + per-process facts cache (20 s, cleared on any local commit) + 4 uvicorn workers in the image/compose (`WEB_CONCURRENCY`). On the Phase 2 seed: first dashboard request ~1.7 s, following /kpi requests 0.12–0.4 s (D-42).
  - A banned worker's card answers `WORKER_BANNED` (ZP-4 step 2, GC-6 order) (D-46).
- Contract changes since v0.3.0 (all additive, now 0.3.1): `FieldError.msg_ar`; `gate_id` query on `/kpi/access`, `/kpi/charts/{id}`, `/kpi/metrics/{metric}`; injury-case `id_type` + `gcc_id`, `id_number` max 15; `HookRequirement.trades`; attachments and exports for the Phase 2 owners/datasets implemented (descriptions updated); `GateCheckRequest.printed_ref` accepts a typed `vehicle_no` for vehicles without an AVP. Behaviour changes the UI may notice: WAP `SOD_CONFLICT` is 422; a supervisor may be named as escort; K-53 displays 2 decimals; non-46 callers get `supervisor: null` on WAPs and "Worker" titles without worker_no.

### Backend — Phase 2 contract v0.3.0 (stage 1)
- `docs/contracts/openapi.yaml` v0.3.0: 94 new paths / 125 operations, all returning 501 `NOT_IMPLEMENTED` until stage 2 (the Prism mock serves them now). Tags: workers, inductions, airport-passes, airside-driving, airside-works, work-area-permits, credentials, gates, access-settings; plus `GET /kpi/access`.
- Phase 0/1 paths unchanged except additive fields: `ExpiringItem.limiting_factor`, `AppliedFilters.gate_ids`, `DashboardResponse.access_band`, `HseSettings.induction_register_from` (v1.1), injury case `worker_id` (+ `worker_no` on read, v1.1), reference items `points` / `immediate_suspension` (list `airside_offence`), `ErrorDetail.meta`, `gate_id` query on every /kpi endpoint. Enums extended: `Capability` (46-81), `ErrorCode`, `EntityType`, `NotificationKind`, `ExportDataset` (14 access registers), `ExportPurpose` (+pass_office, authority_request), `AttachmentOwner` (+worker_photo, pass_application_id_copy, induction_signature, offence_evidence), `ReferenceList` (+airside_offence, vehicle_category, credential_reason), `KpiMetric` (K-48…K-60, K-53b — return `null` / `NOT_AVAILABLE_YET` until stage 2), `ChartId` (C10-C12), `LeadingWarningCode` (E5-E7), `ActionPanelItem` (10 access items), `ExpiringItemKind` (13 access kinds), `AiTool` (+get_access_kpis).
- The permission matrix rows 46-81 are live, so `Me.capabilities` already shows the Phase 2 capabilities per role.

#### Phase 2 — what the frontend must know
- **IDs and masking.** No endpoint returns a full Iqama/National ID/passport number except `POST /workers/{id}/id-number/unmask` (capability `worker.unmask_id`, body `{reason, reason_text?}` with reasons pass_application / authority_request / identity_verification / incident_investigation / other+text). It is audited as `sensitive_field_read`. Show the value on demand only (e.g. reveal for 30 s), never cache or prefill it. Everything else carries `id_number_masked` (`2*******02`; GCC/passport `TE*****12`). ID search is `POST /workers/lookup {id_type, id_number, passport_country?}` (exact match only, POST so the number stays out of URLs); the list `q` searches names / worker_no only.
- **Duplicates.** `409 WORKER_EXISTS` has `detail.meta = {worker_id, worker_no}` (offer "open existing worker"); `409 WORKER_EXISTS_OUT_OF_SCOPE` has no identifying data. `422 VALIDITY_EXCEEDS_LIMIT` has `meta = {limiting_factor, max_date}` (name the limiting field in the form).
- **Photos, ID copies, signatures** go through `/attachments` (owner types `worker_photo`, `pass_application_id_copy`, `offence_evidence`); open them with `POST /attachments/{id}/signed-url` (≤ 5 min). The ID copy id is only present for capability 48. Induction signatures are sent inline as `signature_png_base64` in the induction body.
- **Hidden keys.** Like Phase 1, some keys are *absent* (not null) when the caller lacks the right: `background_check` / `outcome_note` / `background_recheck_due` need capability 56. A refused application shows `status_label_en/ar` = "Refused by issuing authority / مرفوض من جهة الإصدار" (AP-13). Worker names in `WorkerRef` are null without capability 46. Viewer/Client get WAPs with `crew: []` and only `crew_count` / `vehicle_count` (WA-19), and only aggregates from `/kpi/access`.
- **QR codes.** `GET /deployments/{id}/access-card`, `GET /avps/{id}/sticker`, `GET /waps/{id}/print` return `qr_payload` = `HSE2:<AC|VS|WP>:<22-char token>` (no personal data) and `printed_ref` to print beside the QR (manual fallback). Reissue rotates the token (`…/access-card/reissue`, `…/sticker/reissue`); old tokens then scan as `CREDENTIAL_REVOKED` / `CREDENTIAL_LOST`.
- **Gate screen.**
  - A tablet logs in with `POST /gate-device/login {device_token}`. The token is shown once by `POST /gates/{id}/devices`. The response sets the httpOnly cookie `hse_gate_session` and also returns `access_token` for `Authorization: Bearer`. A device session can call only `/gate-checks/*` and `/gate-device/logout`; anything else returns `403 GATE_DEVICE_FORBIDDEN`. A logged-in user with `gate.check` can use the same endpoints.
  - Start with `GET /gate-checks/context` (gates the caller may use, `escort_pairing_seconds`, `clear_after_seconds` = 30).
  - Scan: `POST /gate-checks {gate_id, payload | printed_ref, direction (in/out), zone_id?, pairing_id?}`. `zone_id` is needed when the gate protects several zones and is omitted at a site gate. Rate limit: 120 per minute (`429 GATE_RATE_LIMITED`).
  - Response `GateCheckResponse`: `result` is GRANTED (green), GRANTED_WITH_WARNING (amber), DENIED (red), PENDING_ESCORT, PENDING_DRIVER, PENDING_ESCORT_VEHICLE, EXIT_RECORDED or WAP_VIEW. `reasons[]` each have `{code, severity deny|warn, message_en, message_ar}`.
  - The response carries one card: `person` (photo URL, names, worker_no, employer, trade, `escort_required` badge, credential lines with valid_until), `vehicle` (with `plate_display`), or `wap` (status, in-window now, blockers, crew eligibility). It never contains an ID number, nationality, background status or offences. Clear the screen after `clear_after_seconds` and cache nothing.
  - **Pairing.** A PENDING_* result has `pairing {pairing_id, waiting_for escort|driver|escort_vehicle, expires_at}`. Scan the next card with that `pairing_id` on the same device. That response's `paired_results[]` holds the final result of the first subject (both GRANTED or both DENIED).
    - Poll `GET /gate-checks/pairings/{id}` to show the countdown. After `expires_at` it returns the timeout result (escorted person DENIED `ESCORT_REQUIRED`).
    - `POST …/cancel` aborts the pairing.
    - Vehicle flow: sticker → PENDING_ESCORT_VEHICLE (no AVP) → escort sticker → PENDING_DRIVER → driver card → GRANTED.
  - Out of scope (Contractor HSE Rep): DENIED with only `OUT_OF_SCOPE` and no card.
  - `out` scans never deny. They return EXIT_RECORDED, with `late_exit = true` after the WAP window + grace.
  - There is no override. If the guard lets a DENIED subject in anyway, call `POST /gate-checks/{check_id}/admitted-despite-denial {reason}`; this alerts the HSE Officer and HSE Manager.
  - Offline: v1.0 is online only. With no connection, show "No connection — call the HSE Officer / لا يوجد اتصال — اتصل بمسؤول السلامة".
- **State machines** (every transition is `POST …/transitions {to_status, …}` unless named below; an invalid transition returns 409 `INVALID_TRANSITION`, a failed precondition returns the specific code):
  - Worker: active ⇄ banned (`worker.ban`, reason ≥ 10 chars). Inactive and anonymised are set by the system.
  - Deployment: pending_induction → mobilised happens automatically on the first passed general_site induction (the access card is issued then; `GET …/access-card` returns 409 before that). mobilised → demobilised by transition. Remobilising creates a new deployment.
  - Induction record: valid | failed (derived from the score), then suspended / revoked / superseded / expired. Suspension and revocation go through `/credentials/induction/{id}/…`.
  - Pass application: draft → submitted → endorsed → lodged → approved → issued (`POST /pass-applications/{id}/issue` creates the pass). Also refused, withdrawn, cancelled, and submitted → draft (returned). Background status: `PUT …/background-check`.
  - Pass / ADP / AVP `validity_status`: active / suspended / revoked / expired. ADPs and AVPs start as `pending` (application) → `…/issue` → active, or `…/withdraw` → withdrawn. `custody_status`: held / return_due / returned / lost; `return_overdue` is derived.
  - Lifecycle for induction, airport_pass, adp, avp and access_card: `/credentials/{kind}/{id}/suspend | confirm-suspension | reinstate | revoke | return | loss | authority-notified`, each returning `CredentialState` (with `open_suspensions[]` and the events). Behaviour:
    - Suspend: with `credential.suspend_raise` only, the suspension is *raised* and lifts automatically after 72 h unless confirmed; with `credential.suspend_confirm` it is confirmed.
    - Reinstate: system suspensions (dependency_invalid, id_expired, licence_expired, vehicle_document_expired) cannot be lifted by hand (409 `SYSTEM_SUSPENSION`). A points suspension can be lifted only after `suspension_end` (422 `SUSPENSION_PERIOD_RUNNING`).
    - Manual actions need `reason_code` (LC-R list) and `reason_text` ≥ 10 characters.
  - NOTAM: draft → submitted_to_ops → requested_from_ais → issued → cancelled or expired, plus rejected. `POST …/replace` records a NOTAMR as a new record. A late submit needs `late_justification` (422 `LATE_JUSTIFICATION_REQUIRED`).
  - Obstacle clearance: draft → submitted → (`POST …/decision`) approved / approved_with_conditions / rejected, then suspended ⇄ approved, withdrawn, expired. `POST /obstacle-clearances/preview` computes heights and reasons for the form without saving (m and ft, strings, 2 dp).
  - WAP: draft → submitted → approved → active (system, only with no blockers) → suspended ⇄ active (resume) → closed. Also rejected, cancelled, expired, and submitted → draft. Details:
    - `blockers[]` is recomputed on every read; show them on Approved WAPs.
    - Resume or close with `fod_handback_required` needs `fod_check {result: clear, checked_at, checked_by_*}` (422 `FOD_HANDBACK_REQUIRED`).
    - Resume with blockers → 409 `WAP_BLOCKED` with `meta.blockers`.
    - On an Approved/Active WAP, change zones, dates, windows or links with `POST /waps/{id}/revisions` (201, a new revision in submitted). Crew and vehicles have their own add/remove endpoints.
    - Window times are local; `current_window` / `next_window` give the UTC instances.
  - Ops event: `POST /projects/{id}/ops-events` suspends the affected Active WAPs. `POST /ops-events/{id}/end` does not resume them.
- **Hook results ("warn").** Until Phases 4/5/6 register providers, hook requirements (AVSEC-AWR training, CRANE-TPI, etc.) come back as eligibility items with `status = warn`, `reason_code = HOOK_NOT_AVAILABLE`, message "Training check available from Phase 5 / فحص التدريب متاح من المرحلة 5". They never block; at the gate they turn the result amber (GRANTED_WITH_WARNING). `GET /hook-providers?project_id=` lists provider availability and policy. Switching a policy to `block` without a provider returns 422 `HOOK_PROVIDER_MISSING`. Show these as amber info, not as errors.
- **Eligibility.** `GET /workers/{id}/eligibility?zone_id&at&context` returns per-requirement items (met / not_met / expiring / warn / not_evaluated) with `valid_until`, `ref` and `reason_code` (the GC-6 codes). Use it on the worker page ("Can enter zone X?").
- **Dates and units.** Credential dates are local dates, inclusive. NOTAM times are UTC (`*_utc`): show both the NOTAM form (`effective_from_notam`, YYMMDDHHMM) and local time, LTR. Plates: Arabic letters with LTR digits. Heights are decimal strings in m with `_ft` twins.
- **Dashboard.** New KPI ids appear in `/kpi/metrics` with `display = "—"` and `null_reason = NOT_AVAILABLE_YET` until stage 2. `/kpi/access` and charts C10-C12 return 501 until then. `DashboardResponse.access_band` is null until then. Expiring items gain 13 kinds and `limiting_factor`; the action panel gains 10 access items, each with a `link`.

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

### Design pass — Phase 1 (UI/UX Designer)
- Design pass: done (Phase 1). Findings, ranking and the Phase 1 design-system additions: `docs/design/phase-1-findings.md`; before/after screenshots: `docs/screenshots/phase-1/design/`.
- Dashboard now answers "are we safe, and what needs me today?" above the fold: compact period bar (scope filters behind "More filters"), headline band, then "Needs attention" and "Due soon" side by side, then tiles, charts, league table, pyramid and insights.
- Safety pyramid rebuilt (real centred bars, one-hue ordinal ramp, counts in text colour); dashboard series colour map (same entity, same colour; aqua = overdue CAs only); C9 control-level table shown; axis units no longer doubled; RTL plot margins; heat-season band in the legend; tile units no longer doubled; worse deltas amber instead of red.
- Due soon, insights, league table, drill-down dialog (grouping, AR labels, bidi), AI label chip, import page (picker, counts, empty text), month lock (locked = neutral), risk/finding badges, investigation sidebar.
- Monthly report print view: bilingual EN/AR header, footer with confidentiality line and figures hash, A4 page numbers, light colours in print.
- Shared: codes in tables no longer break at hyphens; `ListToolbar` folds filters after the 4th on desktop (opens by itself when the URL has filters); styled file inputs; new status badge keys.
- No business logic, API calls, permissions, KPI values or data shown changed. New strings in `scripts/i18n/p1-design.py`.

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

- (Backend, Phase 2, spec conflict) Appendix A puts `training_course: AVSEC-AWR` on every airside zone with hook policy `warn`, so by GC-5 every clean airside scan is GRANTED_WITH_WARNING (`HOOK_NOT_AVAILABLE`) until Phase 5. AC56/AC58/AC60 say "GRANTED"; the tests accept "no DENY reason". Keep the zone hook (amber until Phase 5) or drop it from the zone profiles?
- (Backend, Phase 2, spec conflict) §8.2 says non-46 callers see "Worker WKR-nnnnnn"; KA-4/AC72 say Viewer lists have no worker_no. We follow AC72 ("Worker", no number). Confirm.
- (Backend, Phase 2, WA-11) A WAP supervisor may be named as an escort (Appendix A: Tariq is supervisor & escort). Confirm, or require a separate `escort` crew role.
- (Backend, Phase 2, GC-13) A card of another project scans as DENIED `OUT_OF_SCOPE` (no card) for everyone, not only Contractor HSE Reps. Confirm.
- (Backend, Phase 2 ASSUMPTIONS) Approved-but-uncollected passes are cancelled after 30 days; workers with no deployment for 30 days become Inactive; LC-8 revokes only credentials held through the blacklisted contractor. Confirm the numbers and scope.
- (Backend, ops) With 4 API workers the KPI cache can show figures up to 20 s old after a write made through another worker, and the gate rate limit (120/min) is counted per worker. Acceptable for v1.0?

## Contract requests
- (Frontend, medium) `ChartSeries.metric` (KpiMetric | null) and, for period axes, `ChartCategory.start`/`end`: lets a click on a bar/point drill into the exact records. Today the UI drills only when a series key happens to be a metric id (e.g. `K-21`) and derives the month from the category key.
- (Frontend, low) `metric` on each pyramid layer (and one metric for RWC+JTC, e.g. a K-07/K-08 combined drill): the UI maps layers to K-05/06/07/09/12/13/30 itself; RWC_JTC drills K-07 only.
- (Frontend, low) A capability for HSE meetings (none in §5.10): the UI gates meeting edits on `inspection.plan_manage` as an assumption.
- (Design, low) Arabic labels the UI cannot show today: `ChartCitation.period_label_ar` / `scope_label_ar` / `base_label_ar`, `KpiValue.numerator_label_ar` / `denominator_label_ar`, and AR text in the C9 control-level table rows (the drill dialog falls back to the generic Arabic term plus the English name).
- (Frontend, Phase 2, low) `primary_language` (and other spoken languages) on `DeploymentRead` / the worker summary used by the induction form. The UI can warn about a language mismatch before submitting, instead of only after the hook answers.
- ~~(Frontend, Phase 2, low) The WAP read should omit the supervisor `worker_no` / name for callers without `worker.view`, like the crew.~~ Done in 0.3.1 (`supervisor: null`).
- ~~(Frontend, Phase 2, low) Arabic text for `FieldError` messages (or a stable message code the UI can translate).~~ Done in 0.3.1 (`FieldError.msg_ar`).
- (Frontend, low priority, not blocking) `GET /contractors/{id}/engagements` (engagements of one contractor across the caller's projects) so the contractor detail page can list where a firm is engaged. Today that view would need one request per project.

## Design proposals
L items from the Phase 0 design pass, waiting for the user's decision at the phase demo (details in `docs/design/phase-0-findings.md`):
- **P1. Two-line dates.** Show the Hijri date as a muted second line under the Gregorian date in tables and detail fields, instead of "01 Jun 2025 · 5 Dhuʻl-Hijjah 1446 AH" on one line that wraps mid-date. Needs `useFormatters` to return date parts and a `<DateText>` component used everywhere. Data stays the same; only the layout changes.
- **P2. Sticky mobile action bar on detail pages.** On phones the status actions (suspend, close, archive, deactivate) now come after all the details and the history. Proposal: a sticky bottom bar with the primary action, and the others in a menu. The same pattern will serve Phase 3 PTW actions (suspend, close) in the field.
- **P3. Searchable project switcher.** Replace the native select with a combobox: search by code or name, recent projects first, project status shown. This matters once there are more than about 10 projects.
- **P4. Date settings in cross-project lists** (frontend note). Today the projects, contractors and users lists use the *current* project's Hijri/digit settings. Recommendation: keep one consistent format per list (the current project's, as now), and say so in the list footer ("Dates shown in ANIA-EXP display settings"). Mixing formats row by row is harder to scan. Needs the user's call.
- **P5. Collapsible desktop sidebar (icon rail).** Gives about 190 px back to wide tables (audit log, Phase 1 registers) at 1366 px.
- **P6. Print/export styles** for the Phase 1 monthly report and the Phase 3 permits: project logo, bilingual header, page footer with audit hash. Belongs with those phases; noted so the token set (series and safety colours) is reused there. *Phase 1: done for the monthly report (bilingual header, footer with figures hash, page numbers); the logo is P9.*

L items from the Phase 1 design pass (details in `docs/design/phase-1-findings.md`):
- **P1 (raised priority).** Two-line dates are now the main cause of tall rows in every Phase 1 register (incidents, CAs, meetings, month lock, due soon): "29 Sept 2026 14:40 · 18 Rabiʻ II 1448 AH" wraps to 3–4 lines. Recommended before go-live.
- **P7. Default sort and saved views for registers.** The CA list and incident register open on the oldest records (closed 2025 actions first). Proposal: open/overdue first by due date by default, plus one-click views ("My actions", "Overdue", "Awaiting my verification"). Changes the list query (sort parameter), so it needs approval.
- **P8. KPI tile tiers.** 27 tiles have equal weight. Proposal: a first row of 6 headline KPIs chosen in HSE settings (e.g. LTI, TRIR, HiPo, overdue CAs, inspection compliance, safe %), a "moved most vs previous period" strip, and the rest folded under "All indicators".
- **P9. Project logo** on the monthly report (and later permits): needs a logo upload on the project (contract change). The print header uses the platform mark until then.
