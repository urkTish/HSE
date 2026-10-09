# Cross-module consistency pass: what changed

Scope: the screens built before the 6b–6d conventions settled: Phase 0 (foundation), 1 (dashboard with AI and the Phase 1 registers), 2 (site and airport access), 3 (permit to work), 4 (third-party certification) and 6a (occupational health). Every one of these had its own design pass; this pass brings them up to the conventions the newer modules use, starting with the most-used phone screens (gate check, permit detail, scaffold board, dashboard, worker and equipment pages), then the registers around them.

Conventions applied (from the 5, 6c and 6d findings):
- **`StackedDate`**: Gregorian date (and time) on one unbroken line, the Hijri date muted under it.
- **`ChoiceMark`**: radio-style answer buttons show a filled / empty circle, not only a fill colour.
- **Never colour alone**: a status shown in red / amber / green text also has an icon.
- **Dangerous actions at the page end**: void / revoke / retire / blacklist / ban / withdraw / cancel sit in a "Record actions" band after the content (`RecordActions`, the 6c muster and 6d audit pattern), as `destructive-outline`.
- **Plurals**: EN and AR ICU plurals instead of "1 days" / "scaffold(s)"; Arabic uses its one / two / few / many forms.
- **English inside Arabic**: codes stay LTR isolates with spacing that works in both directions; localised (Arabic) dates are no longer forced LTR.
- **Touch targets**: 44 px is already the token minimum on touch screens (Phase 0); the changed choice buttons keep it.

Method: one pass, code-reading of every Phase 0–4 / 6a screen against the conventions, then before / after screenshots of the most-used screens. No logic, API call, permission or data shown changed. Every existing test id and e2e selector is kept; only buttons moved within their page.

## Shared (used by all modules below)

| Change | Where |
|---|---|
| `RecordActions`: a labelled band at the page end ("Record actions" / "إجراءات السجل", or a page-specific label), border on top, buttons end-aligned | `components/common/record-actions.tsx` (new) |
| `StackedDate` takes an optional `className` (e.g. `items-end` in end-aligned columns) | `components/medical/common.tsx` |
| Strings: `consistency.*` and the plural fixes below | `scripts/i18n/consistency.py` (new). `merge.py` now runs it after the phase files, so a full merge keeps these values; a full merge changes nothing else in `messages/*.json` |

## Per module

### Phase 0 — foundation
- **Status moves** (project, site, zone, contractor, user pages; `TransitionActions`): destructive moves (close, archive, blacklist, deactivate) are listed last, as `destructive-outline`, set apart from the everyday moves. They were solid red buttons in the order the state machine listed them. Moving them to the page end needs a per-page change: proposal **P35**.

### Phase 1 — dashboard and registers
- **Dashboard, "Due soon"**: the due date is a `StackedDate` (end-aligned) instead of "29 Sept 2026 14:40 · 18 Rabiʻ II 1448 AH" on one line; "1 days overdue" / "متأخر 3 يوم" → proper plurals (`dashboard.daysOverdue`, and the Arabic `daysLeft`). Drill-down "{count} records" and "Longest run {days} days" → plurals. The call sites pass the plain number `n` beside the formatted figure so the plural form is chosen from the number, not from Arabic-Indic digits.
- **Dashboard headline / ops band**: the last-LTI incident ref and the ops zone codes are LTR isolates whose margin was on the wrong side in Arabic (`ms-*` on an LTR element resolves to the left). Fixed with `rtl:` margins.
- **Corrective actions**: due date `StackedDate`; "{n} days overdue" gets a warning icon and a plural.
- **Incidents, observations, inspections, meetings**: occurred / observed / planned / completed / held dates are `StackedDate` in the registers. The provisional-cases count on an incident row gets an icon.
- **Monthly reports**: "Revised since publication" gets an icon.
- **Observations**: "1 photo(s) selected" → ICU plural (EN / AR). **Workforce import**: "{count} rows saved as submitted" → plural.
- **HSE settings**: KPI metric code spacing fixed in Arabic.

### Phase 2 — site and airport access
- **Gate check (phone)**: WAP "inside / outside the work window" now has a tick / cross icon (the permit card already had one); WAP blockers get a cross icon like the permit blockers; "Escort required" gets a people icon; "Late exit" a clock. The permit card's "Valid to" used the browser's `toLocaleString` inside a forced-LTR span, so in Arabic the date read back to front; it now uses the gate's own date format and is not forced LTR.
- **Gate log**: occurred-at is a `StackedDate` (time on the first line); "Late exit" gets a clock icon.
- **Worker page**: **Ban** moves from the header (solid red, next to Edit and Add photo) to the page end (`RecordActions`, outlined). **Demobilise** moves from the deployment card header (solid red, next to Edit) to the end of the card, outlined, with an icon. ID expiry, mobilised / planned demob / demobilised dates and credential valid-until are `StackedDate`.
- **Credential panel** (pass, ADP, AVP, induction, access card): Revoke and Report loss are no longer solid red buttons in the same row as Suspend / Confirm; they sit at the end of the card, outlined, after a divider. Effective-until is a `StackedDate`; "Authority not notified yet" gets an icon.
- **ADP / AVP application**: Withdraw moves from the action row (solid red next to Issue) to the page end, outlined. The action row now shows only when there is an issue step.
- **Pass and WAP registers**: requested / card expiry / effective-until dates and the WAP from–to dates are `StackedDate`. Works: "System suspended" gets an icon. `passes.staleHint` → plural.

### Phase 3 — permit to work
- **Permit page (phone)**: **Cancel** and **Delete** (cannot be undone) move from the action bar under the state panel to a band at the page end (labelled "Cannot be undone"), as long as the bar has another step to show; with nothing else they stay in the bar so it is never empty. **Suspend** and **Gas alarm** stay at the top in their "Stop work" group on purpose: a stop must be reachable at once (see P38).
- Validity, current window and next window are `StackedDate` from–to pairs instead of four dates on one wrapped line.
- Shifts: "Gas not compliant" gets a cross icon. Isolation summary "{n} points · {locks} personal locks" → plurals.
- **Arabic dates no longer forced LTR**: 37 places in the PTW pages (permit detail, gas tests, detectors, isolations, JSA, SIMOPS, audits, board, field records, signatures) wrapped a localised date in an `ltr` span, so an Arabic date ("06 أكتوبر 2026 10:00") read in the wrong order. They are now plain bidi isolates (`unicode-bidi: isolate`) that follow the page direction. The A4 print stays LTR by design.
- **LTR codes in Arabic**: obstacle / incident refs, checklist item codes, audit item codes, ref letters, thresholds and worker refs had their logical margin on the wrong side in Arabic; fixed with `rtl:` margins.
- **Permit register**: validity from / to as `StackedDate` with a mirrored arrow; the blocker count and "post-expiry check pending" get icons.
- **Board**: "Still suspended" gets an icon. **Isolations**: "Review by …" (an Arabic sentence that was forced LTR) and "Long term" get an icon and follow the page direction. **Audits**: critical count / hint get an icon. **Readiness**: "Not ready" gets an icon.
- **Pre-issue / closure checklists**: Yes / No / N/A buttons show a radio mark, the chosen answer a 2 px border, and an unchosen "No" keeps a faint red border (6d run convention).
- **PTW appointment**: Revoke moves from the header to the page end. **Gas detector**: Retire moves from the action row to the page end.

### Phase 4 — third-party certification
- **Scaffold board (phone)**: "Request re-inspection" (a site-wide hard stop for every scaffold in use) moves from the header, where it was the first button on the phone, to the end of the board under "Affects every scaffold in use". "{n} scaffolds" and "{n} scaffold(s) now need re-inspection" → plurals.
- **Scaffold page**: Dismantle moves to the page end. "Close (red tag)" stays at the top: it is a stop-use step.
- **Equipment page**: Retire and Blacklist move from the header (six buttons before the state panel on a phone) to a page-end band labelled "Cannot be undone"; Retire gets an icon. Tag out stays at the top (stop-use). The current certificate's "In force" / "Not in force" badges get icons; valid-until, status history and configuration-event dates are `StackedDate`; "Late record", "Not cleared" and "TPI accreditation lapsed" get icons. "{n} certificate line(s) suspended" → plural.
- **Equipment deployment**: Cancel moves to the page end. **TPI**: Blacklist moves to the page end; "Does not count" gets an icon. **Defect**: Destroy moves to the page end; the category buttons show a radio mark.
- **Scaffold inspection, arrival inspection**: Pass / Fail / N/A and the tag result show a radio mark.
- **Certificate validity view**: valid-until follows the page direction (was forced LTR); "Unverified window" gets an icon. Verification log dates are `StackedDate`. Import "sensitive" gets an icon; "{n} certificates created" → plural. Limitation / hook values: LTR spacing fixed in Arabic.

### Phase 6a — occupational health
- **Worker health page**: "Place on fitness hold" moves from the header (four buttons above the fitness state on a phone) to the page end; New assessment, Refer and the data report stay at the top.
- Imports "Commit {n} rows" / "{n} records created" and plan "{n} gaps as of {d}" → plurals. "{n} settings saved." is left as it is: `p6a-settings.spec.ts` asserts the text "1 settings saved." (noted for the fixer; the plural is ready to add to `consistency.py` once the spec reads "1 setting saved."). Exposure-limit value and import code spacing fixed in Arabic.

## Checked, no change
- Touch targets: buttons, inputs and selects are 44 px on touch screens from the Phase 0 tokens; the gate's thumb bar is 48–56 px.
- State panels: permit (Phase 3), equipment / scaffold / personnel (Phase 4) and fitness (6a) already use icon + word + sentence.
- Dashboard bands (PTW, certification, training): warning / danger figures already carry icons.

## Proposals (need the HSE Manager)

| # | Proposal | Effort |
|---|---|---|
| P1 (partly done) | Two-line dates are now in the most-used registers and detail pages listed above. Still one line: dates inside sentences ("Tag valid until …", "Last LTI …"), history panels, detail fields of lower-traffic pages. A `DateText` in `components/common` (moving `StackedDate` out of the medical module) would let every module share it | M |
| P34 | **"Stop" vs "record" actions.** This pass kept the safety stops at the top (permit Suspend and Gas alarm, equipment Tag out, scaffold red-tag Close, ops-event declaration) and moved only irreversible record actions to the page end. Confirm that rule, so the newer modules follow it too (6b–6d already match it) | S |
| P35 | **Phase 0 status moves at the page end.** Close project / archive zone / blacklist contractor / deactivate user are now last and outlined in the status row, but still at the top of the page. Moving them to a `RecordActions` band needs each page to split its options | M |
| P36 | **Gate crew reasons are raw codes.** On the gate's WAP and permit cards a crew member who is not eligible shows codes (`INDUCTION_EXPIRED, …`). EN / AR labels from the gate reason list would make them readable; the codes are not in `enums` yet | S (needs the code list) |
| P37 | **One LTR-isolate rule.** Codes are isolated in four different ways (`Code`, `bdi.ltr`, `span.ltr`, `dir="ltr"`), and a logical margin on an LTR isolate lands on the wrong side in Arabic. A lint rule (no `ms-*` / `me-*` on `.ltr`, use `gap`) would stop new cases | S |

## Not changed on purpose
- No business logic, API calls, permissions, KPI values or data shown changed. Only buttons moved within their page and labels, icons and date layout changed.
- E2E selectors and test ids are unchanged (`ban-worker`, `demobilise`, `act-cancel`, `act-delete`, `request-reinspection`, `retire-equipment`, `blacklist-equipment`, `scaffold-dismantle`, `wh-hold`, `cred-revoke`, `cred-loss`, `withdraw-adp`, `withdraw-avp`, `tpi-blacklist`, `defect-destroy`, `cancel-eq-deployment`, `revoke-appointment`, `retire-detector`, `transition-*`, `ans-*`, `sic-*`, `aic-*`, `df-cat-*`, `si-result-*`, `permit-actions`, …). New: `permit-end-actions`.
- Out of scope (open proposals for the HSE Manager): P2 sticky phone action bar, P17 / P22 kiosk and TV modes, P21 R3 colour token, P23 / P26 / P33 offline queue and badges.
- The A4 prints (permit, access card, stickers, muster sheet) stay fixed LTR bilingual sheets.

## Screenshots
`docs/screenshots/consistency/*-after.png` (from `e2e/screenshots-consistency.spec.ts`, `SCREENSHOTS=1`, `SHOT_SUFFIX=after`, fresh seed, shared e2e clock, production build of this pass). The "before" set (`SHOT_SUFFIX=before` against the build at `e29ec2a`) did not complete: on both attempts the base build's gate page never showed the device sign-in within the 5-minute test limit (the first attempt also hit a full temp disk), so per the two-attempt rule it was left; the spec can produce it on demand.

| Files | Screen |
|---|---|
| `01-gate-phone-{en,ar}-after` | Gate check result on a phone |
| `02-permit-phone-{en,ar}-after` | Permit PTW-ANIA-EXP-2026-0413 on a phone (full page) |
| `03-scaffold-board-phone-{en,ar}-after` | Scaffold board on a phone (full page) |
| `04-worker-phone-{en,ar}-after` | Worker page WKR-000022 on a phone (full page) |
| `05-dashboard-{en,ar}-after` | Dashboard, desktop (full page) |
| `06-equipment-{en,ar}-after` | Equipment RW-MC-03, desktop (full page) |
| `07-worker-health-{en,ar}-after` | Worker health WKR-000034, desktop (full page) |

## Checks
- Lint, typecheck and i18n check green on a clean `git archive HEAD` export (the shared tree's typecheck currently fails on another agent's uncommitted `schema.d.ts`; see below). A full `merge.py` on HEAD leaves `messages/*.json` unchanged.
- E2E of the changed modules (Phase 0 auth / org / contractors / design / scoping, p1, p2, p3, p4, p6a) on a fresh seed: 155 passed, 8 failed, 9 did not run. One failure was this pass (`p6a-settings` asserts "1 settings saved."; the plural was reverted). Re-run alone, `auth` AC3, `p2-passes` AP-4, `p2-waps` WA, `p3-config` AC2 and `p3-lifecycle` AC86 pass (order / timing: AC3 leaves Khalid locked when its unlock step times out at login, and AC2 then cannot pick him). `contractors` AC17 (no tier-2 parent offered) and `p2-workers` IN (POST inductions → 422) depend on earlier tests in their files and touch no changed screen.

## For the fixer
- `p6a-settings.spec.ts:19` asserts "1 settings saved."; once it reads "1 setting saved." the ICU plural can go into `consistency.py`.
- `contractors.spec.ts` AC17 and `p2-workers.spec.ts` IN fail in a full older-module run (422 on POST inductions; no tier-2 parent engagement); `auth` AC3 login after the lockout times out intermittently and cascades into `p3-config` AC2.
- The shared tree has an uncommitted `frontend/src/lib/api/schema.d.ts` (6e) that breaks `npm run typecheck` there: `caSource.environmental`, `externalBody.ncec` and `entity.env_*` have no EN / AR labels yet.
