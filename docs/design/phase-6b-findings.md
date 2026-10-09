# Phase 6b design pass: UX findings

Scope: the Phase 6b screens in the "Heat stress" nav section and the permit heat fields:
- Field: heat board, WBGT readings (register and the phone entry), welfare checks (register and entry), heat duty list, acclimatisation plans.
- Midday ban: patrols (register and entry), exemptions.
- Heat-illness log (register, entry with context and controls review), heat actions, heat KPIs, season report.
- Setup: instruments, monitoring points, rest stations, heat settings.
- Permits: heat workload / clothing on the permit form and detail, the regime now on the shift, midday-ban exemption requests.

Main user: a site supervisor on a phone outdoors in bright sun, often in Arabic. So the priorities were legibility, large targets, state colour that always comes with an icon or a shape, and fast entry. Shared components were changed only where a 6b screen needed it, and they stay consistent with Phases 0–6a (`StackedDate`, `FreeText`, the lock-note style of `TierNote`, `StatusBadge`).

## Method

- **Setup.** The p6b e2e setup: real backend on a fresh, migrated and seeded database (`hse_e2e`, `app.seed` + `app.seed_heat`), shared e2e clock at 2026-10-06 10:00 Riyadh (HS3: Z-APR-21 at 27.8 °C → R2; Z-LAY1 stale at 62 min), production build.
- **Users.** Noura Al-Qahtani (HSE Officer) for the screenshots; Fahad Al-Mutairi (site engineer) for the phone reading flow in `p6b-board`.
- **Screenshots.** The 19 Phase 6b screens in EN and AR at 1440 px, plus the board and reading entry at 390 px (`screenshots-p6b.spec.ts`), before and after. Before / after pairs in `docs/screenshots/phase-6b/design/`:

| Files | Screen |
|---|---|
| `20-heat-board-phone-en-{before,after}` | Heat board, EN phone |
| `20-heat-board-phone-ar-{before,after}` | Heat board, AR phone |
| `21-reading-entry-phone-en-{before,after}` | WBGT reading entry, EN phone |
| `02-wbgt-readings-ar-{before,after}` | Readings register, AR desktop |
| `14-heat-illness-log-en-{before,after}` | Heat-illness log, EN desktop |
| `11-welfare-check-entry-en-{before,after}` | Welfare check entry, EN desktop |

Effort: **S** < 1 h · **M** ≤ 1 day · **L** a redesign or a contract change that needs the user's approval.

## Ranked findings

| # | Impact | Problem | Where / evidence | Fix | Effort | Status |
|---|---|---|---|---|---|---|
| 1 | High | **The regime, the thing a supervisor acts on, was the smallest element on the card.** The zone card led with a 30 px WBGT number; the regime in force was a 14 px pill on a line with a 12 px caption. In sun glare on a phone "R2 · 30 work / 30 rest" was hard to read at arm's length | `20-heat-board-phone-en-before` | `HeadlineRegime`: a full-width panel tinted by the regime tone with a 2 px border, a 32 px icon (tick / clock / pause / triangle / octagon), the regime in 18 px bold, the rest minutes under it in 14 px, and the caption ("Regime for acclimatised Heavy work") on top. Same panel on the duty list (it reuses `ZoneCard`) | M | Done |
| 2 | High | **Arabic regime text was scrambled.** "R2 · 30 عمل / 30 راحة" rendered as "30 · R2 عمل / 30 راحة": the bidi algorithm glued "R2 · 30" into one left-to-right run, so the work minutes jumped next to the code. Affects every full regime badge (board, log context, permit detail "regime now") | `20-heat-board-phone-ar-before` | `RegimeBadge` / `HeadlineRegime` isolate the code (`<bdi>R2</bdi> · 30 عمل / 30 راحة`). Text content unchanged, so selectors and assertions still match | S | Done |
| 3 | High | **A stale or unknown zone looked as trustworthy as a current one.** Only a small amber "Stale" pill in the corner told the supervisor that the 62-minute-old 26.8 °C was out of date (WR-9: the regime is kept, it never improves) | `01-heat-board-en-before` (Z-LAY1) | Stale: an amber line with a clock icon "Reading 62 min old: the regime shown is kept until a new reading. Take a new reading.", the WBGT number muted. Unknown: a grey line "No reading today for this zone: take one before relying on a regime." In both cases "Record a reading here" becomes the filled primary button (it is outlined on current zones). Text from the server's `state` and `age_minutes` only | S | Done |
| 4 | Medium | **Regime grid too small to read outdoors.** The 2 × 4 grid (acclimatised / not × light…very heavy) used 12 px code pills | `20-heat-board-phone-en-before` | Grid pills at 14 px semibold with more padding; icons kept (never colour alone). Header labels stay 12 px so "Moderate" / "Heavy" do not collide at 1440 px | S | Done |
| 5 | Medium | **Dense tables pushed the last column off screen.** Readings, welfare checks, patrols and the heat-illness log printed "08 Aug 2026 10:40 · 25 Safar 1448 AH" on one line; at 1440 px the Void button and the Status column were cut off (the readings register in AR, the log in EN) | `02-wbgt-readings-ar-before`, `14-heat-illness-log-en-before` | `StackedDate` (6a finding 4): Gregorian date and time on one unbroken line, the Hijri date muted underneath. All columns now fit at 1440 px | S | Done |
| 6 | Medium | **Answer buttons showed the choice by fill colour only.** Welfare items (Pass / Fail / N/A), patrol outcomes, the controls review (Yes / No / Unknown / N/A) and the plan-day "followed" choice changed only from outline to filled. In glare, or for colour-blind users, the chosen answer of ten rows was hard to scan | `11-welfare-check-entry-en-before` | `ChoiceMark`: every answer button starts with a radio mark (empty circle → dotted circle when chosen), so the choice reads from the shape. Controls-review buttons are 2 × 2 and ≥ 44 px high on phones (they were four 32 px buttons in a row) | S | Done |
| 7 | Medium | **Reading entry: the same point and meter picked every time, and a dead Save button.** A supervisor usually reads the same point with the same meter many times a day; opened from the "Record reading" header button, both selects started empty. The disabled Save gave no reason | `21-reading-entry-phone-en-before` | The last point + meter used on this device are pre-selected when no zone is given and both are still active (browser storage, per-viewer convenience; a zone link and a single active meter still win). Under the form: "To save: choose the point and the meter, then enter the WBGT or the temperatures." | S | Done |
| 8 | Low | **"required" on the zone card was ambiguous** ("Point P-SAIR-STN · required") | `01-heat-board-en-before` | "monitoring required" / "القياس مطلوب" | S | Done |
| 9 | Low | **Typed English text in Arabic pages lost its punctuation** in the permit's midday-ban exemption requests (reason, heat controls) | Permit detail, field records | `dir="auto"` on both texts (6a finding 7). Heat screens already used `FreeText` | S | Done |
| 10 | — | **Privacy note on the heat-illness log.** Checked: the lock note ("Sensitive health data: each view is recorded." + no clinical data stored here) sits above the register and on each entry, in the same style as the 6a `TierNote`. The board shows the open-review count only to users with `heat_log.view`. No change needed | `14-heat-illness-log-*` | — | — | OK |
| 11 | — | **Empty states.** Checked: every 6b list has its own sentence ("No outdoor zones on this project.", "No heat-illness entries.", …) and falls back to the filter message only when a filter is set. No change needed | — | — | — | OK |
| 12 | Medium | **R2 and R3 share one amber.** They differ by icon (pause vs triangle) and words, so the state is never colour-only, but R3 (15 work / 45 rest) is much more restrictive than R2 and looks the same from a distance | Board, grid | **P21.** A "severe" orange step between warning and danger in `tokens.css` (light and dark, AA on its tint), used for R3 here and available to other phases. A token change touches safety semantics platform-wide, so it needs the user's call | M | Proposal P21 |
| 13 | Medium | **Board for outdoor and site-office use.** The board polls every minute but gives no sign that a zone's regime changed since the user last looked; zones are listed by site, not by severity | Board | **P22.** "Changed since you looked" marker on a zone card whose headline regime changed (client-side, from the last board seen), a "worst first" sort, and the P17 kiosk / TV mode for heat (large tiles, auto-refresh, no chrome). Optional "sun mode": forced light theme, heavier weights and borders | L | Proposal P22 |
| 14 | Medium | **Readings without signal.** Outdoor points (aprons, laydown) often have poor coverage; a reading typed while offline is lost on Save | Reading entry | **P23.** An offline queue for manual readings (kept on the device with the measured time, sent on reconnect, marked "pending sync"; late-entry rules apply server-side). Needs agreement on idempotency keys with the backend | L | Proposal P23 |
| 15 | Low | **Saved reading shows the grid but not "what this means for my zone".** The confirmation shows the WBGT and the 2 × 4 grid, not the headline regime of the zones the point covers, because `ReadingRead` has no zone headline | Reading saved | **P24.** `zones: [{zone_code, headline_regime, rest_minutes_per_hour}]` on the reading response (contract change), shown with `HeadlineRegime` | L | Proposal P24 |
| 16 | Medium | **Phone: actions before the state, two-calendar dates.** Phase 0 proposals P1 (two-line dates platform-wide) and P2 (sticky phone action bar) apply unchanged; 6b uses `StackedDate` in its tables already | — | Proposals P1, P2 | L | Proposals P1, P2 |

## Not changed on purpose

- Business logic, API calls, permissions and the data shown are unchanged. No request was added. The stale / unknown lines are worded from the server's `state` and `age_minutes`; the regime comes from `headline_regime` and `rest_minutes_per_hour` as before.
- The stored "last point / meter" is a per-device default only; it never overrides a zone link (`?zone=`), and a point or meter that is no longer active is ignored.
- E2E selectors are unchanged. `data-testid="regime"` stays on `RegimeBadge`; the headline panel adds `data-testid="headline-regime"` with `data-regime`. New: `zone-needs-reading`, `rd-missing`.
- R4 (stop outdoor work) keeps the red card background and the octagon icon; red is still used only for stop-work and critical fails.

## Design system additions (Phase 6b)

- **`components/heat/common.tsx`**: `HeadlineRegime` (large regime panel), `ChoiceMark` (radio mark for large answer buttons), `RegimeBadge` with the code isolated for RTL, `RestMinutes` takes a `className`.
- Reuses the 6a `StackedDate` (`components/medical/common.tsx`) in the 6b tables.
- Strings: `heatDesign.*` in `scripts/i18n/p6-heatdesign.py`.
