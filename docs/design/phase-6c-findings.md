# Phase 6c design pass: UX findings

Scope: the Phase 6c screens in the "Emergency" nav section and the permit "Resume after drill" step:
- Emergency board (with the action panel and KPIs), emergency events and the declare dialog, event detail.
- Muster / headcount (roll and count modes) and the printable muster sheet.
- Drills: programme, register, drill detail with the evaluation form and the evaluated view.
- Organisation: roster, coverage, rescue teams. Equipment: assets, checks, check entry.
- Plan and setup: ERPs, assembly points, contacts, zone profiles, muster readers, emergency info, settings.
- Permits: the receiver's "Resume after drill" step (PE-2).

Main user: a site engineer or warden on a phone at an assembly point during a drill or a real alarm, often in Arabic, in sun. So the priorities were: the missing figure first and huge, a state you read from an icon and words as well as colour, large targets, nothing destructive near the thumb, and a paper sheet that works when the phone does not. Shared components were changed only where a 6c screen needed it, and they stay consistent with 6a / 6b (`StatusBadge`, `StackedDate`, the lock-note style of `PrivacyNote`, `ChoiceMark` in `AnswerButtons`, `AccessPrintHeader` / `BiLabel` on paper).

## Method

- **Setup.** The p6c e2e setup: real backend on a fresh, migrated and seeded database (`hse_e2e`), shared e2e clock at 2026-10-06 10:00 Riyadh, production build. The backend was run from a clean `git archive HEAD` export (the working tree had uncommitted Phase 6d backend work).
- **Users.** Noura Al-Qahtani (HSE Officer) for the screenshots; Omar (muster scan) and Fahad (counts on the phone, drill timings) in the p6c specs.
- **Screenshots.** The 6c screens in EN and AR at 1440 px, the board and the muster at 390 px, and (new) the muster sheet as printed (A4 print media), from `screenshots-p6c.spec.ts`. The screenshot muster now has a realistic state: eight S-AIR workers on site (their latest seeded gate entries copied to 30 min ago, screenshot setup only), five scanned, three missing. The "before" muster had nobody expected (0 / 3 extras), so the before / after pair shows the layout, not the same numbers. Before / after pairs in `docs/screenshots/phase-6c/design/`:

| Files | Screen |
|---|---|
| `27-muster-phone-{en,ar}-{before,after}` | Muster / headcount, phone |
| `26-emergency-board-phone-{en,ar}-{before,after}` | Emergency board, phone |
| `21-muster-counts-en-{before,after}` | Count-mode muster, desktop |
| `20-drill-evaluated-{en,ar}-{before,after}` | Evaluated drill, desktop |
| `28-muster-sheet-{en,ar}-after` | Printed muster sheet (no printable "before" screenshot existed) |

Effort: **S** < 1 h · **M** ≤ 1 day · **L** a redesign or a contract change that needs the user's approval.

## Ranked findings

| # | Impact | Problem | Where / evidence | Fix | Effort | Status |
|---|---|---|---|---|---|---|
| 1 | High | **The missing figure, the one number a warden acts on, looked like the others.** Four equal 30 px tiles (Expected / Accounted / Missing / Resolved) with 12 px labels; "Missing" was second-last and only its number turned red. No icon on any tile, so at arm's length "0" and "3" in the third tile read the same as the others | `27-muster-phone-en-before` | Missing first, full width: a 2 px bordered panel, 48–60 px number, a 40 px icon whose **shape** changes with the state (person-with-cross when someone is missing, tick when nobody is), "3 people missing" / "No one missing" and a one-line next step ("Search for them or resolve each with a reason."). Below it Expected / Accounted / Resolved at 36–48 px with an icon each (people / person-tick / clipboard) and 14 px labels, then a progress line "5 of 8 accounted for" with a bar (fills from the right in Arabic). Same counts the server sends; nothing recomputed beyond the sums the page already did | M | Done |
| 2 | High | **Void sat between the title and the counts on the phone**, the first button under the thumb on a stressed screen | `27-muster-phone-en-before` | Void moves to the end of the page under a separator ("Record actions"); the header keeps only "Print sheet". Same capability check, same reason dialog | S | Done |
| 3 | High | **The printable muster sheet was a screen table, not a paper form.** Thin grey borders, a 12 px "☐" glyph, one name in the page language, no project / site / time block, no "present __ of N" per contractor and nowhere to sign; the confidentiality note was a grey line | Muster sheet (not in the earlier screenshot set) | A4 paper layout like the permit print: `AccessPrintHeader` (project code and name, "Muster sheet / كشف التجمع"), a fact row (muster, site, printed at, number on the list), the confidentiality note in a bordered box in EN and AR, one table per contractor with black rules, bilingual column heads, names in **both** scripts, a 5 mm tick box and an empty Notes column for pen, "Present ______ / N" per contractor, and a signature block (assembly point / warden, counted by, signature, time). Every printed page carries the muster no. and the destroy-after note in the @page footer. Laid out LTR like the permit print; the Arabic print date is isolated (`dir="auto"`) so it reads in order | M | Done |
| 4 | High | **"3 / 0" on the board's open-muster card was ambiguous**, and in Arabic the LTR isolate made it read backwards to an Arabic reader ("accounted / expected" or "expected / accounted"?). A muster with people missing looked the same amber as one with nobody missing | `26-emergency-board-phone-{en,ar}-before` | "5 of 8 accounted for" / "تم حصر 5 من 8" in 18 px bold; the "3 unaccounted" badge gains an icon; the card turns red-bordered only while someone is unaccounted (amber otherwise); the arrow stays on the card's edge instead of wrapping onto its own line | S | Done |
| 5 | High | **Criterion code glued to its label in Arabic** ("DC02مسح مسؤولو…"): the code is an LTR isolate with `me-1`, so in RTL the margin landed on its outer side and the space collapsed at the isolate boundary. Same in the evaluation form | `20-drill-evaluated-ar-before` | `CriterionLabel`: code and label as two flex items with a real `gap` (works in both directions); the code is muted 12 px semibold so the label leads | S | Done |
| 6 | Medium | **Pass / Fail in the evaluated view was colour only** (green / red pills with words but no icon) and the pills had different widths, so the failed row did not stand out when scanning 10–12 criteria | `20-drill-evaluated-en-before` | Tick / cross / dash icon in each pill, pills a fixed minimum width so the codes align; the "criteria failed" note gets a cross icon. Two columns from 1024 px (was 640 px, where long Arabic labels wrapped badly) | S | Done |
| 7 | Medium | **Over-target times were shown by red text only** ("Headcount 24.2 min (target 20)") | `20-drill-evaluated-en-before`, event detail | `Minutes` adds a warning-triangle icon when over target (the screen-reader "over target" text was already there). Applies to drill timings and event response times | S | Done |
| 8 | Medium | **Roll list on the phone: small row actions.** "Present" and "Resolve" were 44 px buttons packed at the row end; the filter tabs (Missing / Accounted / Resolved / All) were words only | `27-muster-phone-en-before` | Row actions are a two-column 48 px grid under each person on phones (unchanged on desktop); each filter tab gets the same icon as its counter tile; "No one is missing." shows with a tick in green | S | Done |
| 9 | Medium | **Count mode: "{n} outstanding" was red text only**, "All accounted" plain grey; the per-reason badges ("Found on site: 1") had no icon | `21-muster-counts-en-before` | Person-with-cross icon on outstanding, tick on "All accounted"; octagon on "Found on site", clipboard on the other resolution reasons | S | Done |
| 10 | Medium | **Board phone: the next-drill rows wrapped unpredictably**: the date and the status pill broke onto separate lines in different places per row | `26-emergency-board-phone-en-before` | Two-column row: drill type and qualifiers (Unannounced / Repeat) start-aligned, date over status end-aligned. Reads as a list in both languages | S | Done |
| 11 | Low | **"1 criteria failed: findings are added for them."** | Drill evaluation | ICU plural in EN and AR ("1 criterion failed: a finding is added for it.") | S | Done |
| 12 | Low | **Arabic finding text in the evaluated view laid out LTR** when the server text starts with a code ("DC02: مسح…" with `dir="auto"`) | `20-drill-evaluated-ar-before` | `dir="rtl"` when the Arabic text is shown, `auto` otherwise | S | Done |
| 13 | — | **Roster privacy note.** Checked: the lock note ("Names are shown to HSE staff, the site engineers and the person's own Contractor HSE Rep.") sits above the roster filters in the 6a / 6b lock-note style, and the muster shows the same note in place of the roll when names are hidden. The printed sheet now carries its own bordered note. No change needed on the roster | `12-emergency-roster-*` | — | — | OK |
| 14 | — | **Empty states.** Checked: board ("No sites…", "No headcount for the current shift yet."), roll ("No one is missing." / "No entries."), findings ("No findings"), events / drills / assets lists all have their own sentence. No change beyond #8 | — | — | — | OK |
| 15 | — | **Permit "Resume after drill".** Checked: same shape as the 6b heat resume (reason line, hint, crew present, temperature / wind when outdoor), primary tone, Play icon, ≥ 44 px. Info tone (a drill is planned) where heat uses warning. No change | Permit detail | — | — | OK |
| 16 | Medium | **No "who is still missing" view for the person in charge across assembly points.** During a real evacuation the incident controller wants the missing names grouped by contractor and last-known gate, refreshed live, on a tablet or TV, without the scan controls | Muster | **P25.** A read-only "controller view" of an open muster: the missing panel, the missing list grouped by contractor with last gate entry time, large type, auto-refresh, no chrome (shares the P17 / P22 kiosk mode). Needs the last gate row per entry in `MusterEntryRead` (contract change) | L | Proposal P25 |
| 17 | Medium | **Scans while offline at the assembly point.** Assembly points are often at the site edge with poor signal; a scan that fails is lost and the warden has to type the card code again | Muster scan | **P26.** Queue scans on the device with the scan time, send on reconnect, mark "pending sync" in the roll (MU-4 rules apply server-side). Same idempotency question as P23 | L | Proposal P26 |
| 18 | Low | **Declare dialog: the Zones picker is narrower than the other fields** and opens as a pop-over, which is fiddly on a phone under stress | Declare emergency | **P27.** Full-width zone checklist inside the dialog on phones (shared `MultiSelect` change, affects every phase's filters) | M | Proposal P27 |
| 19 | Medium | **Phone: actions before the state, two-calendar dates.** Phase 0 proposals P1 (two-line dates platform-wide) and P2 (sticky phone action bar) apply unchanged; on the muster, a sticky "Scan access card" bar would keep the main action under the thumb while scrolling the roll | — | Proposals P1, P2 | L | Proposals P1, P2 |

## Not changed on purpose

- Business logic, API calls, permissions and the data shown are unchanged. No request was added. The missing panel, the tiles and the progress line use the counts the page already summed (`expected`, `accounted`, `unaccounted` / `outstanding`, `resolved`).
- The muster sheet still fetches once (audited export, no background refetch); it shows the `name_en` and `name_ar` the sheet response already carries.
- E2E selectors are unchanged: `mc-missing` (now the panel) keeps `data-n`; `mc-expected` / `mc-accounted` / `mc-resolved`, `muster-void`, `muster-sheet`, `roll-*`, `eval-answer`, `eval-criterion`, `measure-*` (`data-over`) are where they were. New: `mc-progress`, `board-muster-progress`, `sheet-confidential`, `sheet-sign`.
- The success "Everyone is accounted for or resolved." alert on a reconciled muster is dropped because the missing panel says it; the warning alert for a closed muster with people outstanding stays (`muster-done`).
- Red is used only while someone is missing / unaccounted, for a person found on site and for failed criteria; a reconciled muster is green, an open one with nobody missing amber.

## Design system additions (Phase 6c)

- **`components/emergency/muster.tsx`**: the headcount `Counters` (missing panel + three tiles + progress line), the paper `SheetBody` with `SheetFooter` (@page margin boxes) and `SheetFact`.
- **`components/emergency/drills.tsx`**: `CriterionLabel` (code + label with a real gap in both directions).
- **`components/emergency/common.tsx`**: `Minutes` shows a warning icon when over target.
- Strings: `emDesign.*` and the `accessPrint.muster*` print labels in `scripts/i18n/p6-emdesign.py`; `emergency.eval.failNote` is now an ICU plural.
- Screenshot spec: `28-muster-sheet-{en,ar}` (print media, A4 width) and a muster with people missing.
