# Phase 5 design pass: UX findings

Scope: the Phase 5 training screens (training is parked as a module, but its screens are built):
- Catalogue: courses, providers and accreditations, trainer authorisations.
- Matrix: training matrix, competency gaps (summary and register), refresher plan, exemptions.
- Sessions: list, detail, attendance register on the phone.
- Records: list, record detail (external certificate review, verification, suspend / revoke), the TR certificate with QR, verification log, imports (dry run and commit).
- Shared with Phase 4: the training card on the hook policy page. Dashboard: the training band.

Main users: an HSE officer reviewing contractor certificates and planning refreshers at a desk, and a trainer or site engineer taking attendance on a phone in a training room, often in Arabic. So the priorities were: numbers that do not run into each other, the status column visible without sideways scrolling, dates that do not wrap to four lines, choices you read from a mark and not only a colour, and the destructive record actions away from the review decision. The shared conventions from 6a to 6c were reused: `StackedDate` (Gregorian on one line, Hijri muted underneath), state panels with icons (`TrainingStatePanel` was already in place from the Phase 4 pattern), radio-style answer buttons (`ChoiceMark`), 44 px or larger targets and never colour alone.

## Method

- **Setup.** The Phase 5 screenshot spec on a fresh, migrated and seeded database (`hse_e2e_p5design`), shared e2e clock at 2026-10-06 10:00 Riyadh, production build. The backend ran from a clean `git archive HEAD` export (the working tree had uncommitted backend work), and the frontend was built from a copy of the tree on separate ports so the other agents' e2e runs were not disturbed.
- **Users.** Noura Al-Qahtani (HSE Officer) for the registers and records, Faisal Al-Harbi (HSE Manager) for the hook policy and dashboard, Lina (trainer) for attendance on the phone (390 px, Arabic).
- **Screenshots.** "Before" is the Phase 5 build set in `docs/screenshots/phase-5/` (EN, 1440 px, and the Arabic phone attendance), copied to `docs/screenshots/phase-5/design/*-before.png`. "After" is the same views plus new ones: gaps, refresher plan, record and hook policy in Arabic, the matrix on an Arabic phone, the sessions list, the full record page, the printed TR certificate and the attendance cards after "All present". The new views have no "before" because the build set did not include them.

| Files | Screen |
|---|---|
| `01-training-matrix-{before,after}`, `01-training-matrix-phone-ar-after` | Training matrix |
| `02-training-gaps-{before,after}`, `02-training-gaps-ar-after` | Competency gaps (summary and register) |
| `03-session-attendance-phone-ar-{before,after}`, `03-session-attendance-phone-ar-marked-after` | Attendance register, phone |
| `04-record-tr-certificate-{before,after}`, `04-record-tr-certificate-full-after`, `04-record-tr-certificate-ar-after` | Training record (accepted, with TR certificate) |
| `05-refresher-plan-{before,after}`, `05-refresher-plan-ar-after` | Refresher plan |
| `06-hook-policy-training-{before,after}`, `06-hook-policy-training-ar-after` | Hook policy, training card |
| `07-import-dry-run-{before,after}` | Import check (dry run) |
| `08-dashboard-training-band-after` | Dashboard training band (no change) |
| `09-tr-certificate-print-after` | Printed TR certificate (no change) |
| `10-sessions-list-after` | Sessions list |

Effort: **S** < 1 h · **M** ≤ 1 day · **L** a redesign or a contract change that needs the user's approval.

## Ranked findings

| # | Impact | Problem | Where / evidence | Fix | Effort | Status |
|---|---|---|---|---|---|---|
| 1 | High | **Gap breakdown tables: numbers and headers ran into each other.** "Counted requirements" and "Gap" headers overlapped, and contractor rows read "4679118" (4679 counted, 118 gap) because the two number columns had no gap between them. The gap figure was red only | `02-training-gaps-before` (By contractor, By course) | Number columns get a fixed width and start padding, no wrapping, headers bottom-aligned; a gap above zero gets a warning-triangle icon as well as red bold, zero gaps are muted. Cell text unchanged (e2e reads "519" / "12") | S | Done |
| 2 | High | **Refresher plan: the Plan state column was cut off at 1440 px** ("Not boo…", "Booked" without its suffix), so the one column the planner acts on needed a sideways scroll. Cause: three dates per row, each "10 Oct 2026 · 29 Rabiʿ II 1448 AH" on one line | `05-refresher-plan-before` | `StackedDate` for valid until, due from and the booked session's first day; days-left chip under the date; the state cell does not wrap. The state column now fits | S | Done |
| 3 | High | **Attendance on the phone: Attended / Partial / Absent were colour-only choices.** The selected button only changed fill colour (green / amber / red), which washes out in sun and is not readable for colour-blind trainers | `03-session-attendance-phone-ar-before` | Radio mark (`ChoiceMark`, filled / empty circle) in each button, a 2 px border on the chosen one, 48 px tall. Same `att-*` selectors, same patch logic | S | Done |
| 4 | Medium | **Suspend and Revoke sat in the record header, next to the status badges**, the first buttons a reviewer sees on an accepted record. On a record under review, Accept / Reject are the decision and belong there; Suspend / Revoke do not | `04-record-tr-certificate-before` | Suspend / Revoke move to a separate band at the page end ("Actions on an accepted record"), the same pattern as the 6c muster Void. Accept / Reject / Return / Submit / Reinstate stay in the header. Same `record-suspend` / `record-revoke` test ids, same dialogs | S | Done |
| 5 | Medium | **"In force" looked the same whether it was expiring or not**, apart from green vs amber (records list badge and the validity line) | Records list, record validity | Calendar-clock icon on the expiring badge, tick on the in-force one (as in the state panel). Records list: days-left chip moved next to the badge | S | Done |
| 6 | Medium | **Dates wrapped to three or four lines in narrow columns.** Matrix "from 01 Sept 2026 · 19 Rabiʿ I 1448 AH" under the line no.; hook policy "Critical codes block from" and every "Blocks from" cell; record fields (completed on, valid until, reviewed) | `01-training-matrix-before`, `06-hook-policy-training-before`, `04-record-tr-certificate-before` | `StackedDate` in the matrix, gaps register (due date), refresher plan, sessions list (first – last day), trainer list (valid to), provider list (next accreditation expiry), record fields and the Phase 4 / 5 hook policy card. The hook policy card is shared with Phase 4; its dates keep the same Gregorian text ("08 Oct 2026"), so the p4 / p5 hook specs still match | S | Done |
| 7 | Medium | **Matrix: rows were about 140 px tall** because the history / edit / remove icon buttons wrapped into a column, and the requirement showed only a code ("IND-GENERAL", "WAH") | `01-training-matrix-before` | Row actions stay on one line; the course name (from the catalogue the page already loads) shows muted under the code | S | Done |
| 8 | Medium | **Hook policy: "Transition" was amber text only**, "Block" had a lock icon | `06-hook-policy-training-before` | Hourglass icon on Transition (the same icon as the stage badge) | S | Done |
| 9 | Low | **"1 rows can be imported; 2 rows with errors will be skipped." and "Import 1 rows"** | `07-import-dry-run-before` | ICU plurals in EN and AR (`training.imports.partialCommit`, `training.imports.commit`) | S | Done |
| 10 | — | **Record state panel and TR certificate.** Checked: the record page already opens with the Phase 4-style state panel (icon, word, line, valid until, days left, limiting factor). The printed certificate is a bilingual A4 sheet with QR, printed ref and no ID number, score or photo (P5-6). No change | `04-*`, `09-tr-certificate-print-after` | — | — | OK |
| 11 | — | **Dashboard training band.** Checked: period-free counts with labels, the transition notice with an hourglass, numbers drill down. No change | `08-dashboard-training-band-after` | — | — | OK |
| 12 | — | **Empty and error states.** Checked: every training list uses the shared `EmptyState` / `ErrorState` / `LoadingState`; the attendance register has "No attendees" and the preview card on the record form says what it still needs. No change | — | — | — | OK |
| 13 | Medium | **Attendance: practical Pass / Fail is a drop-down** on the phone, one more tap and a native picker per attendee | Attendance register | **P28.** Two radio-style buttons (`AnswerButtons`) instead of the select. Kept as a proposal because the p5-sessions spec drives it with `selectOption`; the fixer owns that spec | S | Proposal P28 |
| 14 | Medium | **External certificate review: the scan and the typed fields are in different cards**, so the reviewer opens the scan in a dialog and compares from memory | Record detail, submitted record | **P29.** A side-by-side review layout on desktop (scan viewer on one side, fields with name / ID match on the other, Accept / Reject under them), stacked on phones | M–L | Proposal P29 |
| 15 | Medium | **Gaps summary: three long tables** (by course, contractor, trade) with a scroll inside each card | `02-training-gaps-after` | **P30.** One "where are the gaps" bar chart (gap count by contractor, sorted, drill-down to the register) with the tables behind a toggle. Needs a chart choice and space on the page | M | Proposal P30 |
| 16 | Low | **Refresher plan: no "who is about to drop off live work" signal.** A worker on a live permit whose critical training expires before the booked session looks the same as one on leave | Refresher plan | **P31.** Show the live-work chips the gaps register already has (`live_permits`, `live_wap_nos`) in the plan, if the plan item carries them (contract change) | L | Proposal P31 |
| 17 | Medium | **Phone: two-calendar dates and sticky actions.** Phase 0 proposals P1 (two-line dates platform-wide) and P2 (sticky phone action bar) apply; the attendance register already has a sticky Save bar | — | Proposals P1, P2 | L | Proposals P1, P2 |

## Not changed on purpose

- Business logic, API calls, permissions, KPI values and the data shown are unchanged. No request was added; the course names in the matrix come from the catalogue query the page already made.
- E2E selectors are unchanged (`gap-by*` cell texts, `plan-row` / `plan-pick`, `matrix-line`, `att-*`, `att-practical`, `record-*`, `critical-from-*` / `general-from-*`, `ti-commit`). New: `record-later-actions`.
- `training.imports.scansHint` was not touched (the fixer owns it). The new strings were merged from `scripts/i18n/p5-design.py` alone, not with `merge.py`, because a full merge would rewrite keys that were fixed directly in the JSON.
- Red stays for gaps, expired / not in force and destructive actions; expiring is amber with a calendar-clock icon; in force is green with a tick.

## Design system additions (Phase 5)

- No new components. `StackedDate` (from `components/medical/common.tsx`) is now used across the training registers and the shared hook policy card; `ChoiceMark` (from `components/heat/common.tsx`) in the attendance buttons.
- `TrainingValidityView`: calendar-clock icon when expiring.
- Strings: `training.matrix.fromLabel`, `training.records.laterActions`, and ICU plurals for `training.imports.partialCommit` / `commit`, in `scripts/i18n/p5-design.py`.
- Screenshot spec `e2e/screenshots-p5.spec.ts`: Arabic desktop views, the Arabic phone matrix, the sessions list, the full record page, the printed certificate and the attendance cards after "All present".
