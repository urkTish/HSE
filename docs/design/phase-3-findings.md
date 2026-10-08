# Phase 3 design pass: UX findings

Scope: the Phase 3 Permit to Work screens. That covers:
- PTW setup: permit types, zone PTW profiles, adjacency, SIMOPS matrix, 5×5 risk matrix and settings.
- Appointments and the permit register.
- The permit form with its live SIMOPS preview.
- The permit detail page: state, action bar, readiness, countdowns, tabs, the step dialogs with re-authentication and co-signing, exemptions and field records.
- JSA editor and view, gas detectors, gas test entry and detail, isolations / LOTO and the lock register.
- SIMOPS conflicts, the live PTW board and the suspension log.
- Permit print and closure pack, PTW audits.
- The dashboard PTW band, charts C13–C15 and the gate `PTW_VIEW` card.

Shared components changed only where a PTW screen needed it, and they stay consistent with Phases 0–2.

## Method

- **Setup.** The app ran against the real backend on a fresh, migrated and seeded database (`hse_design3`, `app.seed` incl. the Phase 3 seed). The backend clock was pinned with `HSE_CLOCK_AT=2026-10-06T10:00:00+03:00` (`HSE_CLOCK_MODE=fixed`, so the seeded live permits stayed live for the whole pass) and every browser page had its clock installed at the same instant.
- **Users.** Faisal Al-Harbi (HSE Manager), Khalid Al-Otaibi (permit issuer, ANIA-EXP), Faris Al-Anazi (permit receiver; gas test entry) and Majed Al-Shammari (issuer, RBT-52; SIMOPS conflict).
- **Records.**
  - Active permits: 0413 (confined space), 0412 and 0405.
  - Approved: 0410. Suspended at shift end: 0408. Expired: 0465. Closed: 0399.
  - Others: ISO-0061 with three personal locks on, the open SIM-RBT-52-0021 conflict, and the JSA of 0413.
- **Screenshots.** Playwright captured 164 "before" shots. The permit detail (receiver, issuer), the board and the risk matrix were taken in all 8 combinations (EN/AR × 1366 / 390 × light/dark). The other 30 screens were taken in 4 (EN desktop light, AR desktop dark, AR phone light, EN phone dark). On top of that: a print PDF, the C13–C15 section and the gas test entry with a failing H₂S reading.
- **Charts.** I loaded the dataviz guidance before touching C13–C15 and ran its palette validator.

**Screenshots** (`docs/screenshots/phase-3/design/`, 12 files):

| Files | Screen |
|---|---|
| 01/02 | Active permit, receiver, EN phone light |
| 03/04 | Approved permit, issuer, AR phone light |
| 05/06 | Permit print, AR screen, dark |
| 07/08 | 5×5 matrix, AR phone dark |
| 09 / 10 | Gas readings before; live gas result after |
| 11/12 | C13–C15 |

Effort: **S** < 1 h · **M** ≤ 1 day · **L** a redesign that needs the user's approval.

## Ranked findings

| # | Impact | Problem | Where / evidence | Fix | Effort | Status |
|---|---|---|---|---|---|---|
| 1 | High | **No one-glance permit state.** The status was a 12 px pill at the far end of the header (on phones under the title), and the reason was repeated in a separate alert. "Approved", "Issued" and "Active" were all the same green tick, so an approved permit looked as "go" as a live one. Countdowns floated between the action buttons and the readiness card | `01-before`, `03-before`, all `pd-*` shots | New **permit state panel** under the title:<br>• the status in 24 px bold with its own icon (play = active, hand = suspended, shield = approved, file = issued…)<br>• the reason and a plain sentence ("Work in progress…", "Work stopped. It may continue only after…", "Approved. Not valid for work until it is issued at the site")<br>• today's window ("In today's work window until 19:00" / "Outside the work window. Next window opens …")<br>• a blocker count that jumps to Readiness<br>• the live countdowns in larger type<br>Tone: green only for Active, blue for draft…issued, amber for suspended or paused, red for expired, grey for closed/cancelled. `PermitStatusBadge` uses the same tones everywhere (register, board, gate card) | M | Done |
| 2 | High | **Action bar mixed safe and irreversible actions.** On an approved permit "Issue" (blue) and "Cancel permit" (solid red) were side by side at the same size. The receiver saw seven equal buttons with two solid red ones in the middle, plus "Copy". In the cancel dialog the dismiss button read "Cancel" next to "Cancel permit" | `03-before`, `pd-413-faris-*` | Actions are grouped:<br>1. the safe next step (filled, full width on phones);<br>2. the other steps (outline, two per row on phones);<br>3. "Stop work": Suspend as a red outline with a hand icon, Gas alarm stays solid red (emergency);<br>4. "Cannot be undone": Cancel permit / Delete as red outlines, separated and pushed to the end on desktop with a divider.<br>Copy is a quiet ghost button. Cancel, Delete and Close open with "This cannot be undone. Check the permit number…", and the cancel dialog's dismiss button reads "Keep the permit". All `act-*` test ids are unchanged | M | Done |
| 3 | High | **"Valid" was ambiguous.** The gas chip next to the type chips said only "Valid" (in Arabic "ساري", the same word as the permit status "Active") | `pd-413-*`, `board-*` | Gas chips read "Gas: Valid" / "الغاز: ساري" (no prefix inside a "Gas" column). On finished permits the register shows the last gas state as a neutral note, not an amber "No valid test" on every closed row | S | Done |
| 4 | High | **Gas readings and limits were not obvious.** The limits were one line of text. Failing cells were red text only. The worst-reading table overflowed the side panel. On phones the stacked readings showed raw keys (`o2_pct`, `lel_pct`). The pass/fail result was a small badge, and on a phone it sat below the signature and Save | `09-before`, gas entry | **Live result panel:** PASS (tick) or FAIL (octagon) in 24 px with a sentence ("A reading is outside the limits. Do not start or continue work."), and each fail code with a warning icon.<br>**On phones** the same result repeats right under the readings.<br>**Every reading input** shows its limit under it ("Limit < 1.0 ppm"), from the server's applied limits.<br>**Readings tables:** the column heads carry the limit, and a value the server marked as failing gets a red chip with a warning icon and the words "out of limit" (never colour alone). Phone labels are "O₂ % (19.5–23.5)", not `o2_pct`.<br>The worst reading in the side panel is a one-line-per-gas list with no sideways scroll.<br>The UI still evaluates nothing: it only marks the fields named by the server's fail codes | M | Done |
| 5 | High | **Permit print not fit as a controlled document.**<br>• no signature or acceptance block<br>• status, work types, crew roles and the gas result were in the screen language only (the gas result raw: `PASS`)<br>• on an Arabic screen the whole sheet mirrored, and worker numbers ran into the names<br>• the long two-calendar validity wrapped under the QR<br>• a second page could not be matched to its permit | `05-before`, PDF | The sheet is always laid out LTR (English left, Arabic right, like the Phase 2 prints). Status, types, crew roles, gas result and signature purposes are bilingual ("Active / ساري"), from a generated `ptwBi.*` namespace built from the existing enum messages. New pieces:<br>• Validity is split into From / To lines; the QR is fixed to the right<br>• an **Authorisation and acceptance** table (role / name / signature / date for receiver, issuer and area authority), with a note that the electronic signatures are in the platform<br>• a bilingual "Controlled copy — check the live status by scanning the QR" line<br>• every page carries the permit number and "Controlled copy / نسخة مضبوطة" in the A4 margin<br>• sections are not split across pages<br>• page numbers read "1 / 2" on Arabic pages too | M | Done |
| 6 | High | **5×5 matrix: colour-only cells and un-named axes.** Cells showed only the score, so the band was colour only. Axes were "L5…S5" with a cramped "L \ S" corner. The matrix stayed LTR in Arabic. In dark mode the extreme cells were white text on light salmon (unreadable) | `07-before`, `jsa-413-*` | Each cell shows the score and the band word (Low / Medium / High / Extreme). Axes are named "Likelihood (L) ↓" and "Severity (S) →", with the arrow mirrored in Arabic. The grid mirrors in RTL. Highlighted JSA cells get a thick outline plus a corner marker. Extreme cells and chips use the destructive fill with its own foreground token (readable in both themes). In the JSA the matrix sits in a fixed 19 rem side column with a one-column legend, so the hazard steps get the width | S | Done |
| 7 | Medium | **C13 repeated a hue.** The API cycles the 9th permit type (Airside works) back to series-1, so "General work" and "Airside works" were both blue. The high-risk share line was the same violet as "Lifting" | `11-before` | General / cold work (the catch-all type) uses a new neutral series token `--series-neutral` (grey, light and dark steps). Airside works keeps blue. The high-risk share line is ink. Validator (stack order): CVD worst adjacent ΔE 9.1 light / 8.4 dark, normal-vision floor PASS. The grey fails the chroma floor by design (neutral catch-all, as an "Other" slot); legend + table view present | S | Done |
| 8 | Medium | **Board: a routine shift-end suspension had a red bar** while its badge was amber (alarm fatigue) | `board-*` | Routine suspensions (shift end, lapsed shift, midday ban) get an amber bar; stop-work, gas and other suspensions keep red. Titles use `dir="auto"` | S | Done |
| 9 | Medium | **Lock register: every lock on the lockbox had a solid red "Cut lock"**, the loudest thing on the page. Locks on and removed looked the same | `isolation-61-*` | "Cut lock" is a red outline. The dialog opens with "Cutting a personal lock cannot be undone…". Locks still on get a blue start bar, a bold lock icon and an "On" chip; removed locks are muted with an open-lock icon. Isolation "Cancel", appointment "Revoke" and detector "Retire" are red outlines too | S | Done |
| 10 | Medium | **Free text in the other language broke in RTL**: English scope text with a full stop at the wrong end, mixed parentheses in location and title | `pd-410-khalid-ar-m-l` | `dir="auto"` on title, location, scope, conditions, emergency info, high-risk reasons, status detail and the print location / emergency | S | Done |
| 11 | Medium | **Countdowns over a day read "90:59:58"**, and an overdue countdown changed colour only | `pd-408-*` | "3 d 18:59" over 24 h. An overdue countdown swaps its clock icon for a warning triangle | S | Done |
| 12 | Low | **Dashboard PTW band:** the amber values ("Suspended", "Open SIMOPS", "Behind plan") were colour only | Dashboard | Warning icon beside amber values and "Behind plan" | S | Done |
| 13 | Low | **Gate `PTW_VIEW` card:** status, in-window and gas were plain text; blockers had no icon | Gate | Permit status badge, in/outside window with tick / cross, gas badge, cross icon on each blocker | S | Done |
| 14 | Low | **SIMOPS conflict header:** the result ("Conditional") was plain text in the subtitle | `simops-21-*` | Rule code + `SimopsResultBadge` | S | Done |
| 15 | High | **Long action rows on phones**: the field actions still come before the readiness and the tabs, and the "Stop work" group scrolls away | Permit detail on phones | Phase 0 proposal **P2** (sticky phone action bar), now with a concrete PTW layout: the safe next step + "Stop work" pinned to the bottom, others in a sheet | L | Proposal P2 |
| 16 | Medium | **The register opens on closed permits from the bulk history.** Live permits are mixed in, and two-calendar validity makes every row 4 lines | `permits-*` | **P7** (default sort / saved views: "Live now", "Waiting for me", "Suspended") and **P1** (two-line dates) | L | Proposals P7, P1 |
| 17 | Medium | **The permit print runs to two A4 pages** for a 6-person crew (the authorisation block moves to page 2) | PDF | **P12.** A compact one-page layout (crew in two columns, conditions and emergency side by side, signatures beside the QR), plus the project logo (P9) | L | Proposal P12 |
| 18 | Medium | **Live gas preview cannot mark the exact input that fails.** `GasEvaluation.worst` is one aggregate reading (its `point` came back "At the work point" while the entered rows were Top/Middle/Bottom), so the UI cannot outline the failing field in the right row | Gas entry | **P13.** Contract request: per-reading fail codes in the preview, so the failing input itself can turn red (the server still evaluates) | L | Proposal P13 |

## Not changed on purpose

- Business logic, API calls, permissions, KPI values and the data shown are unchanged. `allowed_actions` still decides which buttons exist.
- No field was added to or removed from any screen. The print's signature table uses the receiver, issuer and area authority names the print already returned; its signature and date cells are blank boxes for the paper copy.
- The Gas alarm stays a solid red button: it is an emergency action and must be the easiest thing to hit when needed.
- Blockers on the permit page stay red: they stop the next step.
- Suspend is a red outline, not hidden: stop-work must always be one tap away.
- `HOOK_NOT_AVAILABLE` notes stay a neutral, folded note (Phase 2 rule).
- E2E selectors are unchanged:
  - `permit-status` now sits on the state panel with the same `data-status`;
  - `status-reason` sits on the reason inside it;
  - `live-timers` / `timer-*`, `act-*`, `gas-result`, `preview-fails`, `cut-lock` and `print-*` are kept.
- Dialogs keep "Cancel" as the dismiss label except permit cancel ("Keep the permit") and destructive isolation steps ("Go back"), so existing tests that press "Cancel" in other dialogs still work.

## Design system additions (Phase 3)

- **Permit state panel:** 2 px tinted border with an 8 px start bar in the tone colour, a 36 px icon and a 24 px status word. Use it for any record whose state decides whether work may go on.
- **Permit tones:** `ptw_approved` (blue, shield), `ptw_issued` (blue, file-check) and `ptw_active` (green, play) in `StatusBadge`. Only work in progress is green.
- **Button variant `destructive-outline`:** for hard-to-undo actions that are not the main action (cancel permit, cut lock, revoke, retire). A solid red fill is kept for emergencies (gas alarm) and for the confirm button inside a destructive dialog.
- **Action grouping:** safe next step → other steps → "Stop work" → "Cannot be undone". On phones each group is its own row with a small label.
- **`StepDialog`** has `warning` (already there) for irreversible steps and a new `dismissLabel` for when "Cancel" would read like the action.
- **Gas results:** `GasVerdict` (large PASS/FAIL with icon and sentence); failing values are a chip with icon + "out of limit"; every reading shows its applied limit.
- **Risk matrix:** score + band word in each cell, named axes, mirrors in RTL, outline + marker for highlights.
- **`--series-neutral`:** a grey for a catch-all category only (C13 "General / cold work"), never a 9th hue.
- **Print:** `ptwBi.*` bilingual enum labels ("EN|AR", generated from the enum messages by `scripts/i18n/p3-design.py`). The permit print is fixed LTR, with page-margin text from `--print-footer-start/end` and an authorisation table.
- **Countdown `size="lg"`** for field timers; durations over a day show days.
