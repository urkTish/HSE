# Phase 6g design pass: UX findings

Scope: the Phase 6g "Contractor HSE scorecard + reports export pack" screens (spec `docs/specs/6g-scorecard-reports.md`, decisions D-232…D-236):
- Scorecards: register (monthly ranking and every card), card page, comments and disputes, watch list and entry (PIP, decision, suspension form), KPIs K-132…K-135, settings and profile versions.
- Reports & exports: report packs (register, pack page), distribution lists, exports (form, job log, subscriptions).
- Contractor performance summary (`/contractors/{id}/performance`), the quick CSV / XLSX buttons on the earlier registers and the dashboard "Print PDF".

Main users: the HSE Manager (Faisal) finalising the month and issuing the client report from the site office; HSE Officers (Noura) preparing packs; Contractor HSE Reps (Tariq, NAJD and its subcontractor SAHARA) on a phone, reading their card and disputing a line before the window closes. Priorities: why a card has the grade it has (caps), where a contractor stands without ever naming the others, whether comments are still possible, and whether a pack has gone out (Draft vs Issued, provisional watermark). Shared patterns kept: `StackedDate`, `ChoiceMark` choices, icon + words for every state, 44–48 px phone targets, irreversible actions in the page-end `RecordActions` band, safety prompts at the top.

## Method

- **Setup.** Real backend on a fresh, migrated and seeded private database (`hse_design6g`, restored from a template copy before every run), shared e2e clock at 2026-10-06 10:00 Riyadh, production build. Backend and frontend ran from a clean `git archive HEAD` export in the scratchpad on their own ports (8046 / 3046), because another agent was working in the tree. The "before" set was taken first, from HEAD `bddb551`, before any change.
- **Users.** Faisal Al-Harbi (HSE Manager, desktop and 390 px), Tariq Al-Mutairi (Contractor HSE Rep, NAJD, desktop and 390 px).
- **Screenshots.** `screenshots-p6g.spec.ts` has a design set that runs with `SCREENSHOTS=1 SHOT_SUFFIX=before|after` (the demo set is skipped then). Before / after pairs, EN and AR, in `docs/screenshots/phase-6g/design/`:

| Files | Screen |
|---|---|
| `01-register-{en,ar}-{before,after}` | Scorecards, September 2026, Faisal |
| `02-card-najd-{en,ar}-…` | SCR-ANIA-EXP-NAJD-2026-09 (band B, capped to C by CP-2) |
| `03-remarks-…` | Comments and disputes |
| `04-watch-entry-…` | WL-ANIA-EXP-2026-002 (SAHARA, Watch) |
| `05-kpis-…`, `06-settings-…` | K-132…K-135 (September), settings and profile |
| `07-packs-…` | Report-pack register |
| `08-mcr-july-provisional-…` | MCR July, issued with provisional scorecards |
| `09-mcr-september-draft-…` | MCR September, Draft |
| `10-mcr-august-issued-…` | MCR August Rev 1, issued, delivery log |
| `11-distribution-…`, `12-exports-…` | Distribution list (MCR), exports with the job log |
| `13-performance-…` | NAJD performance summary |
| `14-register-export-…`, `15-dashboard-print-…` | Ban-patrol register quick export, dashboard Print PDF |
| `16-register-phone-…`, `17-draft-pack-phone-…`, `18-register-export-phone-…` | Faisal at 390 px |
| `19-card-phone-rep-…`, `20-register-phone-rep-…`, `21-remarks-phone-rep-…`, `22-watch-phone-rep-…` | Tariq at 390 px |
| `23-register-rep-…` | Tariq, desktop register |

Effort: **S** < 1 h · **M** ≤ 1 day · **L** a redesign or a contract change that needs the user's approval.

## Ranked findings

| # | Impact | Problem | Where / evidence | Fix | Effort | Status |
|---|---|---|---|---|---|---|
| 1 | High | **Why a card is capped was barely legible.** The grade tile showed a 12 px struck-through "B →" and one small line "CP-2 Lost-time injury → max C INC-…"; the register's Caps column showed only "CP-2", a code nobody outside the HSE team knows | `02-card-najd-*-before`, `01-register-*-before`, `19-…-before` | `CapExplain` on the card: "Lowered from band B to C by", then each cap as an amber box (code, what it means, "Because of" + the record numbers). `GradeBadge` shows the band at 14 px with a down-arrow and a screen-reader text ("The score's band was B; a cap lowered the grade"). `CapList` in the register and the performance summary: arrow + code + meaning. `sc-cap` (with the refs) and `sc-grade` unchanged | `02-…-after`, `01-…-after` | S | Done |
| 2 | High | **The comment window had no state.** "Comments until 14 Oct 2026 23:59" sat in the details card with a "Due in 8 d" line; nothing said whether the rep can still comment, or that a closed window means "waiting for Final" | `02-…-before`, `19-card-phone-rep-*-before` | `CommentWindow` band under the title and in the comments card: open (speech bubble, blue, "until …" + countdown), closed ("awaiting the HSE Manager's Final", lock), Final ("comments and disputes are closed"), not issued yet. Presentation of `status` and `comment_until` only; the server still refuses late remarks | `02-…-after`, `19-…-after` | S | Done |
| 3 | High | **Reps saw ranks 3 and 4 with no explanation.** The ranking showed only NAJD and SAHARA (server scope, RK-2), rows 1–2 silently missing; the card said "3 of 4" and "Project median 82.5" without saying where that leaves NAJD | `23-register-rep-*-before`, `19-…-before` | Under the rep's ranking: "Only your own contractors are listed. Ranks are out of 4 ranked contractors on the project; the others are not named." (eye-off icon). On the card: above / below / at the project median in words with an arrow, and, for reps, "Other contractors' names and scores are not shown to contractor reps." No other contractor is ever named; `sc-rank` text unchanged ("3 of 4") | `23-…-after`, `20-…-after`, `19-…-after` | S | Done |
| 4 | High | **A Draft pack looked like an issued one.** The September MCR showed only a small "Draft" badge; nothing said nobody has received it. The provisional watermark of an issued pack was a small amber field inside Document control | `09-mcr-september-draft-*-before`, `17-…-before`, `08-mcr-july-provisional-*-before` | State band under the title: Draft / In review = dashed grey box "Draft: not issued — nobody on the distribution list has received it" (pen icon); Issued = green box "Issued {date} by {name}" + "frozen" (lock). Provisional = thick amber box "PROVISIONAL SCORECARDS" with a stamp icon; the section watermark chips get the stamp too. Register rows in Draft / In review say "Not issued" | `09-…-after`, `17-…-after`, `08-…-after`, `07-…-after` | S | Done |
| 5 | High | **The card page was 13,400 px long on a phone.** Pillars and 33 metric lines stacked into label/value cards (≈ 300 px each) | `19-card-phone-rep-*-before` | Pillars and metrics are compact tables on phones too (`stack={false}`, scroll inside the table); the result column comes first (pillar score; points, then status, value, window, weight); score and rank side by side on phones, the grade tile full width. 5,000 px after | `19-…-after` | S | Done |
| 6 | Medium | **Issue / Re-issue and the watch-list decisions sat in the everyday button row** (Issue next to Return to draft; Close entry, Record decision and the suspension form under the details) | `10-…-before`, `04-watch-entry-*-before` | Page-end `RecordActions` bands: pack "Issue: freezes the files and notifies the list" / "Replace this issued pack with a new revision" (`rp-end`); watch entry "Decide or close this entry" (`wl-actions`). Rebuild / submit / return / review stay in `rp-actions`; submit / accept PIP in `wl-steps`. All test ids unchanged | `10-…-after`, `04-…-after` | S | Done |
| 7 | Medium | **Watch-list level had no ladder.** "Watch" was one badge; nothing showed that it is step 1 of watch → improvement plan → suspension review | `04-…-before`, `22-…-before` | `LevelLadder`: three numbered steps, the current one bordered with "Current level" (words, not colour alone; done steps get a tick) | `04-…-after` | S | Done |
| 8 | Medium | **Months as "2026-09" everywhere**, and "09-2026" in Arabic (bidi): the ranking heading, the card title, month pickers, watch triggers, the performance summary, pack periods "2026-09-01 → 2026-09-30" | `01-register-ar-before`, `13-…-before`, `09-…-before` | `useMonthName` ("September 2026" / "سبتمبر 2026", Gregorian, project digits) and `usePeriodLabel` (whole month / year as a name; the ISO range kept small under it on the pack page). URL values unchanged | `01-…-after`, `09-…-after` | S | Done |
| 9 | Medium | **Delivery log rows 128 px tall** with the attachment names in one unbroken line pushing the table wide | `10-mcr-august-issued-*-before` | Attachments as a list (paperclip, wrapping), revision with project digits | `10-…-after` | S | Done |
| 10 | Medium | **Contractor performance summary unreachable** (only by typing `/contractors/{id}/performance`); grade mix "B × 2" in plain text; watch entries not linked | `13-…-before` | "Performance summary" button on the contractor page for the HSE Manager (`contractor-performance`, same right as the page); grade mix as grade badges; month names; caps with meaning; watch entries link to the entry | `13-…-after` | S | Done |
| 11 | Medium | **Export log** showed `heat_patrols` codes, "Expired" twice per row (status and the download column), and the PDPL marks as coloured text only; the register select drew its chevron at the card's far edge | `12-exports-*-before` | Dataset name over the code (when the server gives one), download only on ready rows, sensitive / personal with a shield / person icon (also on the column chips); select wrapper fixed | `12-…-after` | S | Done |
| 12 | Low | **Pillar weight total** only turned red when off 100 (colour alone); Activate was disabled while unsaved with no reason | `06-settings-*-before` | Total with a tick / warning triangle and "should total 100"; "Save the changes before activating." under the buttons | `06-…-after` | S | Done |
| 13 | Low | **Small fixes.** Internal comments marked with a lock; open disputes with a warning triangle; the "More export options" link is a 44 px target with an icon; the dashboard Print button says "Preparing the PDF…" while busy; long card numbers wrap on phones instead of being cut off | `03`, `14`, `15`, `16`, `18` | As described | `…-after` | S | Done |
| 14 | — | **Safety prompts and states.** Checked: the suspension form is a destructive step dialog with the server's warning on top; card, pack, remark, watch and job states use icon + words; dates are `StackedDate` / Hijri where shown; KPI tiles say red / amber in words with a triangle. No change | `01`–`23` | — | — | OK |

## Proposals (need the HSE Manager)

| # | Proposal | Effort |
|---|---|---|
| P48 | **Compact ranking rows on phones.** At 390 px each ranking row is a 300 px label/value card (rank, contractor, score, grade, caps, trend, coverage, watch). A one-line row (rank · contractor · score · grade) that expands for caps, trend and coverage would show the whole month on one screen | M |
| P49 | **Comment-window and rank-scope fields from the server.** `comment_window: open \| closed \| final \| not_issued` and `can_remark` on `ScCardRead`, and `visible_rows` / `scoped` on the ranking, would replace the browser's clock comparison and role test (the rep note) | S (backend) |
| P50 | **Confirm before activating a scoring profile.** Activation is immediate (one click, no dialog) and changes every card from its effective month; a step dialog naming the month and the version it replaces would match the other irreversible steps | S |
| P51 | **Confirm before withdrawing a dispute.** Withdraw is one tap next to the dispute text on the phone and cannot be undone | S |

## Backend asks

- Arabic labels for the wrapped Phase 0–5 export datasets: `label_ar` is the dataset code (`incidents`, `inspections`, `corrective_actions`), so the Arabic register picker and job log show English codes (`12-exports-ar-*`).
- The MCR snapshot lists "Contractor scorecards" twice (sections 6 and 21) in the September draft and the August / July packs; check the RP-1 section order.
- P49 fields.

## Not changed on purpose

- Business logic, API calls, permissions and the data shown are unchanged. No request was added (the export log reuses the dataset list the page already loads). The median position compares the card's own score with the median the server returns; the comment-window state compares `comment_until` with the clock; month names format the same `yyyy-mm` values.
- E2E selectors are unchanged (`sc-rank`, `sc-card-median`, `sc-cap`, `sc-grade`, `sc-month-status`, `sc-pillar-eff`, `sc-line-status`, `rp-actions`, `rp-issue`, `rp-reissue`, `rp-watermark`, `wl-actions`, `wl-close`, `sp-sum`, `registry-export-more`, `dashboard-print`…). New: `sc-cap-explain`, `sc-caps`, `sc-grade-band`, `sc-median-position`, `sc-rep-scope`, `sc-comment-window` / `sc-remarks-window` (`data-state`), `sc-remark-internal`, `rp-state` (`data-state`), `rp-provisional-banner`, `rp-end`, `wl-ladder`, `wl-steps`, `cps-grade`, `contractor-performance`.
- Column order of the card's pillar and metric tables now puts the result first (pillar score; points and status); the cells and their test ids are the same.
- Red stays for sensitive export columns and failed / expired states; amber for caps, "below the median" and the provisional watermark; green for issued packs.

## Design system additions (Phase 6g)

- **`components/scorecard/common.tsx`**: `useMonthName`, `usePeriodLabel`, `CapExplain`, `CapList`, `MedianPosition`, `CommentWindow`; `GradeBadge` with a legible band and an accessible "capped" text.
- **`components/scorecard/watch.tsx`**: `LevelLadder` (watch → improvement plan → suspension review).
- **`components/scorecard/packs.tsx`**: pack state band (Draft / In review / Issued) and the provisional banner.
- Strings: `scDesign.*` in `scripts/i18n/p6-scorecarddesign.py` (new keys only; a full `merge.py` adds them and changes nothing else).
- Screenshot spec: the design set in `screenshots-p6g.spec.ts` (`SHOT_SUFFIX`).
