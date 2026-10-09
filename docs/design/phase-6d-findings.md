# Phase 6d design pass: UX findings

Scope: the Phase 6d "Inspections, audits & talks" screens:
- Checklist run on the phone (start, answering, critical / stop-work moments, offline "waiting to send"), and the same item answers inside an audit's Conduct dialog.
- Toolbox talk recording on the phone: suggested topics, named attendance (card scan / list / signature), language check.
- Audit detail: score, grade, section scores, findings, record actions.
- Field assurance KPIs (K-34…K-36, K-110…K-117) and their breakdown table.
- Checked without changes: field overview, settings, templates and topics library, findings, stop-work orders, audit programme, talk register, campaigns, plan template.

Main users: an HSE officer or site supervisor walking the site with a phone in one hand, often in Arabic, often with weak signal; the HSE Manager reading audit results and KPIs in the site office. So the priorities were: answer fast with the thumb, always know what is left and what blocks sending, see clearly that a record is waiting on the phone, and read an audit's grade and its reason at a glance. Shared patterns from 6a–6c are reused (`ChoiceMark` radio-style answers, `StackedDate`, state panels with icons, 44–48 px targets, never colour alone, dangerous actions at the page end).

## Method

- **Setup.** The p6d e2e setup: real backend on a fresh, migrated and seeded database (`hse_e2e_design6d`), shared e2e clock at 2026-10-06 10:00 Riyadh, production build. Backend and frontend run from a clean `git archive HEAD` export on their own ports (8377 / 3377), because other agents were working in the tree.
- **Users.** Noura Al-Qahtani (HSE Officer) for the screenshots.
- **Screenshots.** `screenshots-p6d.spec.ts` (`SCREENSHOTS=1`): EN and AR at 1440 px, the checklist run and toolbox attendance at 390 px, and a new **23-checklist-run-offline-phone** (viewport only, signal cut mid-checklist). Before / after pairs in `docs/screenshots/phase-6d/design/`:

| Files | Screen |
|---|---|
| `20-checklist-run-phone-{en,ar}-{before,after}` | Checklist run, phone (full page) |
| `23-checklist-run-offline-phone-{en,ar}-after` | Checklist run, phone, no signal (new shot, no "before") |
| `21-toolbox-attendance-phone-{en,ar}-{before,after}` | Record a toolbox talk, phone |
| `12-field-audit-{en,ar}-{before,after}` | Issued audit detail, desktop |
| `02-field-kpis-{en,ar}-{before,after}` | Field assurance KPIs, desktop |

Effort: **S** < 1 h · **M** ≤ 1 day · **L** a redesign or a contract change that needs the user's approval.

## Ranked findings

| # | Impact | Problem | Where / evidence | Fix | Effort | Status |
|---|---|---|---|---|---|---|
| 1 | High | **KPI breakdown rows showed raw codes** (`airside_fod_walk`, `leadership_walk`, `plant_vehicle`…) in both languages; the server sends the code as `label_en` / `label_ar` for inspection type (and for talk language) | `02-field-kpis-ar-before` | EN / AR names in the frontend: new `enums.fdInspectionType` (the 13 Phase 1 inspection types, same words as the reference list) and the existing `enums.fdLanguage` for the language breakdown. Unknown codes fall back to the server label | S | Done |
| 2 | High | **No sense of "how much is left / what blocks sending" on the phone run.** "5 of 22 answered" sat in the header card that scrolls away; the submit button was disabled at the very end with one generic sentence; nothing took you to the item that still needed work | `20-checklist-run-phone-en-before` | A **sticky bottom bar** while answering: "5 of 22 answered", a progress bar, a "1 not compliant" count with a cross icon, what still blocks sending in words ("17 items to answer", "1 not-compliant item needs a note or photo", "Fill in the stop-work details" in red), a 48 px **Next item to do** button that scrolls to and focuses the next open / incomplete item (then the manual findings, then the stop-work card), and **Submit** beside it under the thumb. When everything is complete it says "Every item answered. Ready to submit." with a tick and Submit takes the full width. Same `answered` / `answerReady` / `ready` rules the page already used | M | Done |
| 3 | High | **"Waiting to send" was only visible after the fact.** With no signal, the only cue was the warning banner at the top of the page (scrolled away while answering); the button still said "Submit inspection" | Run, talk recording | `OfflineSubmitNote` next to the submit button (wifi-off icon, amber box: "No signal: it is kept on this phone and sent when the signal returns.") on the run and the talk form; the run's submit button reads **Save on this phone** with an hourglass icon while offline. The outbox panel ("waiting to send" list, Send now) and the queued screen are unchanged. New shot `23-…-offline-phone` | S | Done |
| 4 | High | **Yes / No buttons took two thirds of the row** (a 3-column grid with 2 options left an empty third), 44 px, 14 px labels; an unselected "No" looked like "Yes" | `20-checklist-run-phone-en-before` | Grid columns match the number of answers (Yes / No halves, with N/A thirds), 48 px, 16 px labels; the non-compliant answer keeps a faint red border even before it is chosen, so it is found without reading. The radio group is labelled with the item text for screen readers. `ChoiceMark` unchanged | S | Done |
| 5 | High | **Audit grade was a small pill next to the score**, with no scale and no reason when the grade is capped (AG: a `major_nc` on a critical item caps at C, so 83 % can be C) | `12-field-audit-en-before` | **Grade panel**: the letter at 48 px in a bordered tile (tone per grade) with the grade words and the score; beside it the **grade scale** A ≥ 90 · B 75–89.9 · C 60–74.9 · D < 60 with the achieved band outlined and ticked (not colour alone); "Capped at C: a major nonconformity on a critical item." with an icon when the server's grade is C but the score sits in A / B. The grade shown is always the server's; the scale is the spec's list AG, used as a legend only | M | Done |
| 6 | Medium | **Findings listed by number**, so 12 observations came before the one major nonconformity; no totals | `12-field-audit-en-before` | "Findings by grade" counts (major NC / minor NC / observation / OFI, each with its badge, zeros dimmed) above the table; the table is sorted by grade, major first (order within a grade unchanged) | S | Done |
| 7 | Medium | **Section scores were a column of numbers**; the weak section (H Improvement 25 %) did not stand out | `12-field-audit-en-before` | A bar per section (fills from the right in Arabic) with the score; the lowest section gets a warning-coloured bar and a "Lowest section" label with a trend-down icon | S | Done |
| 8 | Medium | **Void sat in the audit header** next to Start / Conduct / Issue | `12-field-audit-en-before` | Moved to the page end under "Record actions" as a `destructive-outline` button (6c muster pattern). Same capability check and reason dialog | S | Done |
| 9 | Medium | **Rating 0–3 in an audit did not say what it raises.** The auditor had to remember AUD-2 (0 → major NC, 1 → minor NC, 2 → observation; critical item 0 / 1 → major) | Audit Conduct dialog | Each rating button below 3 carries a second line "Finding: Major nonconformity" etc., from the same `baseSeverity` rule the form already used to pre-fill the grade | S | Done |
| 10 | Medium | **Suggested topics squeezed the title to one word per line** on the phone: the reason badge ("Recent incident · INC-ANIA-EXP-2026-0147") took the row | `21-toolbox-attendance-phone-en-before` | Title (with the topic code) on its own line, the reason badge under it (the ref is an LTR isolate, truncates instead of wrapping), "given recently" with a history icon; 48 px, `aria-pressed` | S | Done |
| 11 | Medium | **Attendance rows on the phone: the name came after the method badge, "Sign" and the bin were small and side by side**, and "Does not speak the talk language" was an amber pill only | `21-toolbox-attendance-phone-en-before` | Row = name (then worker no.) first, method badge (card / list, each with an icon) at the end; the language state on its own line with a languages icon; a row that may not have understood gets an amber start border; Sign is a full-width 48 px button and the bin a separate 48 px target at the end. The count in the card header is a larger pill with a people icon | S | Done |
| 12 | Low | **"1 attendee(s) may not have understood"** | Talk form | ICU plural in EN and AR | S | Done |
| 13 | Low | **Arabic audit header read "v1CHA"**: the version was its own LTR span after the code, so in RTL it landed before it | `12-field-audit-ar-before` | Code and version in one LTR isolate ("CHA v1"). Fixed after the screenshot run, so `12-field-audit-ar-after` still shows the old order | S | Done |
| 14 | Low | **KPI tiles: red / amber shown by number colour only** | KPI page | An icon and the words ("Off target" / "Near target", the `enums.rag` strings) under a red or amber figure. The seeded month has no RAG on the 6d tiles, so the screenshots do not show it | S | Done |
| 15 | — | **Critical and stop-work moments.** Checked: a critical item has the red start border and the star "Critical" badge; a failed stop-work item shows the octagon "Stop the work now" panel at the moment of the answer (also offline), and the stop-work card (red, 2 px) comes after the items and before sending. The new bar names the missing stop-work details in red. No other change | `20-checklist-run-phone-*` | — | — | OK |
| 16 | — | **Field overview, stop-work order, findings, programme, campaigns.** Checked in EN / AR: state tiles have icons, empty states have their own sentence, dates use `StackedDate`. No change | `01`, `08`–`17`, `22` | — | — | OK |
| 17 | Medium | **Answering one item per screen.** On a 40-item audit the phone page is very long. A "focus mode" (one item at a time, swipe / Next, the bar as now) would be faster one-handed | Run, Conduct | **P32.** Optional one-item-per-screen mode for the run and the audit Conduct dialog, remembering the choice per user | L | Proposal P32 |
| 18 | Medium | **"Waiting to send" outside the page.** A record queued on the phone is only visible on the run / talk pages. A small badge in the top bar ("2 waiting to send", hourglass) on every page would stop people from logging out or clearing the browser before it is sent (AC59 wipes the cache at logout) | Shell | **P33.** Outbox badge in the top bar, with a warning in the logout menu when items are waiting. Shared shell change | M | Proposal P33 |
| 19 | Low | **Breakdown labels from the server.** The fix in #1 is frontend-only; `label_en` / `label_ar` on `FieldBreakdownRow` for `inspection_type` and `language` should carry the names (the reference list already has them) so exports and the AI tool T21 get them too | KPI breakdown | Contract request (below) | S (backend) | Request |
| 20 | Low | **Audit grade scale in settings.** The scale on the grade panel is the spec's list AG (marked ASSUMPTION in the spec). If HSE makes it configurable, `grade_scale` on the audit response would keep the legend in step | Audit detail | Contract request (below) | S (backend) | Request |

## Not changed on purpose

- Business logic, API calls, permissions and the data shown are unchanged. No request was added. The bar uses the page's existing `answered`, `answerReady`, `failing` and `ready`; the rating consequence uses the existing `baseSeverity`; the grade, score and section scores are the server's (the AG scale is a legend; the "capped" line only compares the server grade with that legend).
- E2E selectors are unchanged: `run-submit` (now in the sticky bar, still disabled until ready), `run-progress`, `ans-*`, `stop-now`, `stop-fields`, `run-queued`, `offline-banner`, `outbox-*`, `suggestion`, `att-row` (`data-method`, `data-signed`), `att-sign`, `att-count`, `lang-mismatch`, `mismatch-note`, `sheet-needed`, `tf-submit`, `audit-void`, `audit-score`, `audit-grade`, `section-scores`, `section-score`, `fk-tile`, `fk-value`, `fk-row`, `fk-note`. New: `run-bar`, `run-next`, `run-blockers`, `run-ready`, `run-failing`, `offline-submit-note`, `grade-panel`, `grade-scale`, `grade-capped`, `finding-counts`, `section-row` (`data-low`), `fk-rag`.
- The run's "Answer every item… to submit." sentence (`field.run.toSubmit`) is replaced by the itemised list in the bar; the key is kept.
- Red stays for not-compliant answers, critical items, stop-work and grade D / major NC only; grade C and the lowest section are amber.

## Design system additions (Phase 6d)

- **`components/field/run.tsx`**: `RunBar` (sticky progress, blockers, Next, Submit); `AnswerChoices` takes `audit` and shows the finding consequence on rating buttons.
- **`components/field/offline.tsx`**: `OfflineSubmitNote` (shared by the run and the talk form).
- **`components/field/audits.tsx`**: `GradePanel`, `FindingCounts`, `SectionScores`.
- Strings: `fdDesign.*`, `enums.fdInspectionType`, and `field.talks.mismatchNote` as an ICU plural, in `scripts/i18n/p6-fdesign.py`.
- Screenshot spec: `23-checklist-run-offline-phone-{en,ar}`.

## Contract requests (for the backend)

- `FieldBreakdownRow.label_en` / `label_ar`: the reference-list names for `group_by=inspection_type` and the language names for `group_by=language` (today both carry the code).
- Optional `grade_scale` (or the band thresholds) on the audit response, if list AG becomes a setting.

## Note for the i18n owner

Running `scripts/i18n/merge.py` today would revert two Phase 5 import strings in `messages/*.json` (`partialCommit`, `commit`: the messages hold ICU plurals the p5 source does not). This pass merged only its own module to avoid that; the p5 source should be brought in line.
