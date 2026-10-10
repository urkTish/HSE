# Phase 6f design pass: UX findings

Scope: the Phase 6f "Incident follow-up" screens (spec `docs/specs/6f-incident-followup.md`):
- Incident page: the "Notifications & follow-up" panel and the similar-lessons card.
- Follow-up section: overview (band + action panel), notifications register, notification pack page, KPIs K-127…K-131, rules and settings.
- Lessons: library, lesson page (distribution, 6d links, effectiveness check), acknowledgements, effectiveness checks.

Main users: the HSE Manager and HSE Officer (Noura) racing statutory and client deadlines from the site office, often at night; Contractor HSE Reps (Ahmed) on a phone, preparing GOSI packs and acknowledging lessons; the client viewer (Sarah) reading statuses. Priorities: a deadline that reads at a glance (how long is left, or how late), the same meaning for every date-only deadline (the end of that day, Riyadh time, D-220), no button that the server will refuse without saying why, and no injured-person identity on a client copy or for a viewer. Shared patterns kept: `StackedDate`, `ChoiceMark` choices, icon + words for every state, 48 px phone targets, irreversible actions in the page-end `RecordActions` band, safety prompts at the top.

## Method

- **Setup.** Real backend on a fresh, migrated and seeded private database (`hse_design6f`), shared e2e clock at 2026-10-06 10:00 Riyadh, production build. Backend and frontend ran from a clean `git archive HEAD` export in the scratchpad on their own ports (8026 / 3026), because other agents were working in the tree. The "before" set was taken first, from HEAD `649a024`, before any change.
- **Users.** Noura Al-Qahtani (HSE Officer, desktop and 390 px), Ahmed Al-Zahrani (Contractor HSE Rep, desktop and 390 px), Sarah Mitchell (Viewer / Client).
- **Screenshots.** `screenshots-p6f.spec.ts` has a design set that runs with `SCREENSHOTS=1 SHOT_SUFFIX=before|after` (the demo set is skipped then). Before / after pairs, EN and AR, in `docs/screenshots/phase-6f/design/`:

| Files | Screen |
|---|---|
| `01-incident-panel-{en,ar}-{before,after}` | INC-ANIA-EXP-2026-0294 follow-up panel, Noura, desktop |
| `02-overview-{en,ar}-…` | Follow-up overview (band + action panel) |
| `03-register-{en,ar}-…` | Notifications register, desktop |
| `04-client-pack-{en,ar}-…` | NP-ANIA-EXP-2026-0001 client flash report |
| `05-kpis-{en,ar}-…` | K-127…K-131, October |
| `06-library-{en,ar}-…`, `07-lesson-{en,ar}-…` | Lesson library, LL-2026-007 |
| `08-acks-{en,ar}-…`, `09-effectiveness-{en,ar}-…` | Acknowledgements, effectiveness checks |
| `10-settings-{en,ar}-…` | Rules and settings |
| `11-incident-panel-phone-{en,ar}-…`, `12-register-phone-{en,ar}-…` | Panel and register at 390 px, Noura |
| `13-incident-panel-ahmed-{en,ar}-…` | Panel as Ahmed (Contractor HSE Rep) |
| `14-gaca-pack-ahmed-{en,ar}-…` | A draft GACA occurrence pack (prepared by Noura) opened by Ahmed |
| `15-acks-phone-ahmed-{en,ar}-…` | Ahmed's acknowledgements, SAHARA overdue, 390 px |
| `16-incident-panel-viewer-{en,ar}-…` | Panel as Sarah (Viewer / Client) |

Effort: **S** < 1 h · **M** ≤ 1 day · **L** a redesign or a contract change that needs the user's approval.

## Ranked findings

| # | Impact | Problem | Where / evidence | Fix | Effort | Status |
|---|---|---|---|---|---|---|
| 1 | High | **Countdowns were 12 px grey-ish text; an overdue item read like a footnote.** "Overdue by 4 d 10 h" on LL-2026-007 / SAHARA was a small red line next to a blue "Pending" badge; "Due in 78 d 13 h" carried meaningless hours | `15-acks-phone-ahmed-*-before`, `07-lesson-en-before`, `01-…-before` | `Countdown` is a chip at 14 px semi-bold with a 16 px icon: overdue = red chip with a warning triangle, under 6 h = amber chip with an alarm clock, otherwise muted with a clock. Spans of 7 days or more show whole days ("Due in 12 d"). Still presentation of the server's due time only (`fu-countdown`, `data-overdue` unchanged) | `15-…-after`, `13-…-after` | S | Done |
| 2 | High | **Date-only deadlines did not say when they end.** Lesson publish-by, acknowledge-by and check due dates showed a bare date, while the countdown ran to 23:59:59 Riyadh (D-220); "CL-FIN due 18 Oct 2026 23:59" did not say it is the end of the investigation due day; nothing said times are Riyadh time | `07-lesson-en-before`, `08-acks-*-before`, `01-…-before`, `10-settings-en-before` | `DayDue` for every date-only deadline: the date (`StackedDate`), "by 23:59 Riyadh time, end of that day", then the countdown. Requirement due times at 23:59 Riyadh get "end of day" under them. One line, "Times are Riyadh time. A date-only deadline runs to 23:59 of that day.", under the panel header and on the register, acknowledgements and checks pages. The rule profile shows "end of day" under "Investigation due date" | `07-…-after`, `08-…-after`, `13-…-after`, `10-…-after` | S | Done |
| 3 | High | **An overdue acknowledgement said only "Pending".** The status badge is the server's (`pending`), so the late item looked like the others | `15-acks-phone-ahmed-*-before`, `07-lesson-en-before` | A red "Overdue" badge (triangle) beside "Pending" once the acknowledge-by day has ended; the server status is unchanged | `15-…-after`, `07-…-after` | S | Done |
| 4 | High | **"Generate pack" offered where the server refuses it.** Everybody, Ahmed included, saw "Generate pack" on CL-FIN while the investigation is not approved (→ `INVESTIGATION_NOT_APPROVED`, PK-5); users without injured-person identity access would see it on GOSI-WIR / MHRSD-LTR (→ 403, PK-1) | `13-incident-panel-ahmed-en-before`, `01-…-before`, `03-register-en-before` | `usePackGate` from data the page already holds: on the incident page (the incident carries `investigation.approved_at`) CL-FIN's Generate is hidden with "The final report can be generated once the investigation is approved."; on the register, where that is not known, the button stays with "Needs the approved investigation: the pack is refused until then."; GOSI-WIR / MHRSD-LTR without capability 29 (GOSI also 30, unless Contractor HSE Rep) hide Generate with a lock and "This pack holds the injured person's identity… ask the HSE Officer". No request added; the server still decides | `13-…-after`, `01-…-after`, `03-…-after` | S | Done |
| 5 | High | **Ahmed saw "Approve pack" on a GACA pack** and the server refuses it (PK-6: Contractor HSE Reps approve GOSI packs only; AC17) | `14-gaca-pack-ahmed-en-before` | For a Contractor HSE Rep (role in this project, not the HSE Manager) on a non-GOSI pack, Approve and Return to draft are hidden and "An HSE Officer approves this pack. Contractor HSE Reps approve GOSI work-injury packs only." is shown | `14-…-after` | S | Done |
| 6 | Medium | **Approve sat in the everyday button row** beside Download and Open the incident, while the convention puts irreversible record actions (void, waive, approve) at the page end | `04-…-before`, `14-…-before` | Approve moves into the page-end `RecordActions` band with "New pack version" ("Approve or replace this version"). `pack-approve`, `pack-regenerate`, `pack-end` unchanged | `14-…-after` | S | Done |
| 7 | Medium | **"Submitted" and "Due" shared the clock icon** (blue vs amber only: colour alone) | `03-register-en-before` | Submitted requirements, packs and recorded submissions use a paper-plane (`fu_sent` in `StatusBadge`, additive) | `03-…-after` | S | Done |
| 8 | Medium | **Pack data showed the incident date as "2026-10-04"** (ISO, no Hijri) | `04-client-pack-en-before` | `StackedDate` for `occurred_date` and `first_day_off` in the frozen snapshot | `04-…-after` | S | Done |
| 9 | Medium | **Identity on a client copy depended on the server alone.** Checked: the client flash pack shows "Person n · trade · employer" labels only, the viewer's panel shows case numbers (P1…), no pack links, and the pack page returns 403 to the viewer (AC44). No leak found | `04-…`, `16-…` | Belt and braces in the pack page: on a client / PMC pack the case rows never render ID type, ID number, nationality, nature, treating facility or first day off, whatever a snapshot holds (P6f-2) | `04-…-after` | S | Done |
| 10 | Low | **Action panel: every count was amber**, including overdue notifications | `02-overview-en-before` | Overdue kinds get a warning triangle in the count; "Notifications overdue" is red (statutory late = critical), the others stay amber | `02-…-after` | S | Done |
| 11 | — | **Safety prompts and record actions.** Checked: Void submission and Waive requirement are in the page-end band of the requirement details; Archive / Delete lesson in the lesson page band; the panel sits with the incident's notifications. No change | `01`, `07` | — | — | OK |
| 12 | — | **States, dates and touch targets.** Requirement, pack, lesson, distribution and check states use icon + words; dates are `StackedDate`; response and channel buttons are 48 px `ChoiceMark` choices; codes are LTR isolates in Arabic. No change | `01`–`16` | — | — | OK |

## Proposals (need the HSE Manager)

| # | Proposal | Effort |
|---|---|---|
| P44 | **Fold finished requirements on phones.** On the register and the incident panel at 390 px, four submitted / acknowledged items take as much height as the three open ones (≈ 2,400 px). Open items first in full, then "Done (4)" as one-line rows (body · stage, submission no., on time) that expand on tap | M |
| P45 | **Server reason for pack generation.** A `pack_blocker` (or `can_generate` + code) on `FuRequirementRead` (investigation not approved, identity access, filer scope) would replace the browser's guess, cover the register (where the investigation state is unknown) and the filer-engagement scope the browser cannot see | S (backend) |
| P46 | **"Overdue" as a distribution state.** `overdue: bool` on `FuDistributionRead` (like `FuCheckRead.overdue`) instead of the browser comparing `ack_due_on` with the clock; also lets the acknowledgements list sort overdue first | S (backend) |
| P47 | **Approver hint from the server.** `can_approve` on `FuPackRead` would replace the role test for PK-6 (Contractor HSE Rep, GOSI only, filer engagement in C scope) | S (backend) |

## Contract requests (for the backend)

- `FuRequirementRead.pack_blocker` (P45), `FuDistributionRead.overdue` (P46), `FuPackRead.can_approve` (P47).
- `deadline_basis` on `FuRequirementRead`, so "end of the investigation due day" does not have to be read from a 23:59 due time.

## Not changed on purpose

- Business logic, API calls, permissions and the data shown are unchanged. No request was added. The pack hints use the incident and `me` the page already has; the overdue badge and the countdown compare the server's dates with the clock; the client-copy guard only removes fields from display.
- On the register, CL-FIN's Generate stays (with a hint): the page does not load investigations, and a hidden button there could be wrong.
- E2E selectors are unchanged (`fu-req`, `fu-status`, `fu-countdown`, `data-overdue`, `fu-generate`, `fu-submit`, `fu-pack-status`, `pack-approve`, `pack-approve-confirm`, `pack-return`, `pack-regenerate`, `pack-end`, `dist-item`, `dist-status`, `ack-*`, `check-*`). New: `fu-pack-gate` (`data-reason`), `fu-end-of-day`, `fu-deadline-rule`, `pack-approver-note`.
- Red stays for overdue notifications and acknowledgements and for the "overdue" countdown; amber for under 6 h and for packs awaiting approval; submitted is blue with a paper-plane, never green until acknowledged.

## Design system additions (Phase 6f)

- **`components/followup/common.tsx`**: `Countdown` as a chip (days only from 7 days), `DayDue` (date-only deadline with "end of that day"), `endOfDay` / `dayPassed`, `DeadlineRule`.
- **`components/followup/requirements.tsx`**: `usePackGate` (why Generate would be refused), `DueAt` ("end of day" at 23:59 Riyadh).
- **`components/common/status-badge.tsx`**: `fu_sent` tone (info, paper-plane).
- Strings: `fuDesign.*` in `scripts/i18n/p6-followupdesign.py` (new keys only; a full `merge.py` adds them and changes nothing else).
- Screenshot spec: the design set in `screenshots-p6f.spec.ts` (`SHOT_SUFFIX`).
