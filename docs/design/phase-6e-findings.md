# Phase 6e design pass: UX findings

Scope: the Phase 6e "Environmental management" screens (spec `docs/specs/6e-environmental.md`):
- Phone reading entry (MON-3) and the waste storage-area check (AIR-2, WST-5): fast entry outdoors.
- Readings against limits, exceedances and background dust (EXD-3, EXD-4): how a result and its status read.
- Waste dispatch and its licence check (CON-2…CON-4): why a dispatch is refused.
- The spill report (SPL-2, SPL-3) and spill page.
- Environmental KPIs (K-118…K-126).
- Checked without changes: overview band and action panel, settings, aspects, permits, providers, streams, consignment register and detail, points register, water, complaints.

Main users: a site engineer or HSE officer on a phone in the sun (Omar records dust, Fahad checks the hazardous store), often in Arabic; the HSE Manager reading exceedances and KPIs in the site office. Priorities: say in words what still blocks a save, show a result against its limit at a glance, never let "Background dust" look like "fine" or like "deleted", and say why a dispatch will be refused before the truck is waiting. Shared patterns kept: `ChoiceMark` answers, `StackedDate`, icon + words for every state, 48 px phone targets, irreversible actions in the page-end `RecordActions` band, safety prompts at the top.

## Method

- **Setup.** Real backend on a fresh, migrated and seeded database (`hse_e2e_design6e`), shared e2e clock at 2026-10-06 10:00 Riyadh, production build. Backend and frontend ran from a clean `git archive HEAD` export in the scratchpad on their own ports (8466 / 3466), because other agents were working in the tree. The "before" set was taken first, from HEAD `caf7a69`, before any change.
- **Users.** Noura Al-Qahtani (HSE Officer, desktop and spill on the phone), Omar Siddiqui (site engineer, reading at 390 px), Fahad Al-Mutairi (area check at 390 px).
- **Screenshots.** `screenshots-p6e.spec.ts` has a design set that runs with `SCREENSHOTS=1 SHOT_SUFFIX=before|after` (the demo set is skipped then). Before / after pairs, EN and AR, in `docs/screenshots/phase-6e/design/`:

| Files | Screen |
|---|---|
| `02-env-kpis-{en,ar}-{before,after}` | Environmental KPIs, September, desktop |
| `14-dispatch-refused-{en,ar}-{before,after}` | Dispatch of used oil with GREENHAUL → refused, desktop |
| `16-point-detail-{en,ar}-{before,after}` | Monitoring point D-SAIR-01, desktop |
| `18-exceedances-{en,ar}-{before,after}` | Exceedance register, desktop |
| `19-exceedance-background-{en,ar}-{before,after}` | ENX-ANIA-EXP-2026-0018 (background dust), desktop |
| `23-spill-reportable-phone-{en,ar}-{before,after}` | Spill report, 25 L reached a drain, 390 px |
| `27-phone-reading-empty-{en,ar}-{before,after}` | Reading entry, point picked, no score yet, 390 px |
| `27-phone-reading-{en,ar}-{before,after}` | Reading entry, score 2 picked, 390 px |
| `28-phone-area-check-{en,ar}-{before,after}` | HWS-SLAND-01 check, "Covered" set to No, 390 px |

Effort: **S** < 1 h · **M** ≤ 1 day · **L** a redesign or a contract change that needs the user's approval.

## Ranked findings

| # | Impact | Problem | Where / evidence | Fix | Effort | Status |
|---|---|---|---|---|---|---|
| 1 | High | **Dispatch: a transporter that will be refused showed a green "Valid" licence.** GREENHAUL holds a valid licence for inert and non-hazardous waste only; for used oil the form showed "Valid · 237 days left" and the refusal came only after Dispatch, as "The licence does not cover this activity or waste class." without saying which provider | `14-dispatch-refused-en-before` | Under each provider, from the licence scopes the page already loads (CON-2, list TR): "Licence covers this waste class (Hazardous)" with a tick, or "Licence does not cover this waste class (Hazardous): dispatch will be refused" / "…does not cover this route…" with a cross, in red. "No valid licence" gets a cross icon. While a chosen provider will be refused, a red box above Dispatch says "This dispatch will be refused" and what to do. When the server refuses (`PROVIDER_LICENCE_INVALID`, `LICENCE_SCOPE_MISMATCH`, `PROVIDER_NOT_APPROVED`, `PRODUCER_REGISTRATION_INVALID`), a "Dispatch refused. There is no override." line with a ban icon and the next step sits above the server message. Dispatch stays enabled: the server decides | `14-dispatch-refused-*-after` | M | Done |
| 2 | High | **Background dust did not say what it means.** An exceedance during a dust storm showed a red "Exceedance" badge and a blue "Background dust" pill; nothing said it does not count against the project (EXD-4, K-123), and on the KPI page the chip read "Background: 1" | `18-exceedances-en-before`, `02-env-kpis-en-before` | `BackgroundBadge` takes `explain`: under the pill, "Not counted as project-caused" (the reading stays an exceedance: it is never removed). Used in the exceedance register and page, and in a reading result when it is over the limit. K-123's chip reads "Background dust, not counted" with the cloud icon | `18-…-after`, `19-…-after`, `02-…-after` | S | Done |
| 3 | High | **Grey Save buttons with no reason** on the phone reading and the spill report: Omar picks the point, the score is missing, Save is grey and nothing says why | `27-phone-reading-empty-en-before`, `23-spill-reportable-phone-en-before` | `StillNeeded` above Save: "Still needed to save:" and one line per missing item with a dashed-circle icon ("Pick the dust score", "Set the start and end", "Pick the instrument", "Confirm the field calibration check", "Fill in the incident details"…). Built from exactly the conditions of the existing `ready`; gone when complete (6d run-bar convention) | `27-…-empty-*-after`, `23-…-after` | S | Done |
| 4 | High | **Peak against limit was three loose numbers.** The exceedance page listed Peak 1240.0, Limit 500.0, Over by 148.0 % as equal fields; the register showed "1240.0 / 500.0" with no unit and "+148.0 %" | `19-exceedance-background-en-before`, `18-exceedances-en-before` | `LimitBar` on the exceedance page: one bar, the limit as a dark marker, the part within the limit grey and the part over it red, with "Peak 1240.0 µg/m³" (cross icon) and "Limit 500.0 µg/m³" under it; it starts from the logical start, so it mirrors in Arabic. Register: "1240.0 / 500.0 µg/m³" and "over by 148.0 %" in red | `19-…-after`, `18-…-after` | S | Done |
| 5 | Medium | **Reading entry: the limit was a grey sentence; the score buttons read "2 2 · Visible at the boundary".** | `27-phone-reading-en-before` | The limit is a box: what is measured on one side, "Alert at 2" and "Limit in force **2.0**" (larger) on the other. Score buttons: the big number, then the words only (`envDesign.visual.*`) | `27-…-after` | S | Done |
| 6 | Medium | **Area check: the hazardous "filling since" dates were three look-alike fields, the hint repeated under each, and "Emptied" looked like a label.** The deadline of each stream was only at the top of the page | `28-phone-area-check-en-before` | One "Hazardous waste: filling since" group with the hint once; per stream its name, the date, Today and an outlined 48 px **"Emptied: clear the date"** with an eraser icon; under it either "Not filling" or that stream's deadline chip (hourglass, days left; shown only while the date is the saved one). The top summary stays | `28-…-after` | S | Done |
| 7 | Medium | **Area check: no sign that answers are not saved yet.** Walking away after tapping "No" lost it silently | `28-phone-area-check-en-before` | "Changed, not saved yet." with an hourglass, in amber, above Save check once anything differs from what was loaded; gone after saving | `28-…-after` | S | Done |
| 8 | Medium | **Spill report: "Likely reportable" listed every rule** ("20 L or more, reached a drain or water, not contained, or on the airside") whatever was entered | `23-spill-reportable-phone-en-before` | "Reportable because:" and only the rules that apply, each with an icon ("25 L is at or over the 20 L threshold", "it reached a drain or water", "it is not contained", "it is on the airside"), then "A Phase 1 environmental incident is created with it, unless you link one." Same SPL-2 preview the form already made. The kit hint now sits under the kit picker and shows only with it | `23-…-after` | S | Done |
| 9 | Medium | **KPI tiles: Waste "717.4" and Water "6,960" with no unit; the K-120 target only in a band above the tiles** | `02-env-kpis-en-before` | The unit after the value (t, m³) unless it is a plain count or the display already carries it (dashboard `KpiTile` rule). The diversion tile shows "Target: 70.0 %" from the server's note (the note band is unchanged). No figure is computed | `02-…-after` | S | Done |
| 10 | Low | **Point page "Recent readings" did not line up and gave no limit** | `16-point-detail-en-before` | Four columns on desktop (window end, parameter, value with "limit …" under it, result), two on a phone | `16-…-after` | S | Done |
| 11 | Low | **"Ncec" as the limit source** (the server capitalises its plain-list codes in English) | `16-point-detail-en-before` | English names for capitalised acronyms in `useEnvRef` (`envDesign.refEn`: NCEC, NCM warning, AOCC). Arabic is the server's | `16-…-after` | S | Done (contract request below) |
| 12 | — | **Safety prompts and record actions.** Checked: the airside dust alert sits at the top of an open exceedance (danger, plane icon); Void (reading excepted, see P42), Close area, Cancel / Archive are in the page-end `RecordActions` band; the spill page puts Clean up / Close at the top as the next steps. No change | `19`, `22`, `28` | — | — | OK |
| 13 | — | **States and dates.** Permit, provider, consignment, spill and complaint states use icon + words; dates are `StackedDate`; codes are LTR isolates in Arabic. No change | `01`–`26` | — | — | OK |

## Proposals (need the HSE Manager)

| # | Proposal | Effort |
|---|---|---|
| P39 | **"Contained?" starts unanswered on the spill report.** It defaults to Yes today. A wrong "Yes" turns a reportable spill into a minor one (SPL-2) with no incident and no K-16; asking for an explicit answer (as for the other required fields) costs one tap. It changes a form default, so it is left for the HSE Manager | S |
| P40 | **Readings chart on the point page (C35).** Readings against the alert and limit lines with background events shaded would replace scanning 20 rows; it needs the C35 chart data (not built in the backend) | M (backend) |
| P41 | **Sticky Save on the phone forms.** The spill report is about 2,300 px tall with the incident fields; a sticky bottom bar (missing items + Save, as the 6d checklist run) would keep the reason and the button under the thumb. Shared with P2 | M |
| P42 | **Void a reading from a reading page, not from the register row.** Manual readings have a red "Void" in every register row (43 on one page). A small reading page (value, window, photos, instrument, history) with Void in `RecordActions` would follow the "irreversible at the page end" rule | M |
| P43 | **Dispatch pre-check from the server.** The licence hint is worked out in the browser from the licence scopes; a `GET …/waste-consignments/check` (or `dry_run`) returning the CON-2…CON-5 verdict per provider, including the producer registration, would make the hint exact and reusable by the AI tool | S (backend) |

## Contract requests (for the backend)

- English labels of the plain reference lists (`config._plain`): `str.capitalize()` gives "Ncec", "Ncm warning", "Aocc"; the frontend fixes those three in English. A `label_en` table like the Arabic one would make exports and the AI tool right too.
- K-120: `target_display` on the KPI value (today the target comes only as a note string, parsed by the page).

## Not changed on purpose

- Business logic, API calls, permissions and the data shown are unchanged. No request was added. The dispatch hint uses the providers and licence scopes the form already loaded; the "still needed" lists repeat the existing `ready` conditions; the spill reasons are the existing SPL-2 preview split into its parts; the bar and units show the server's numbers.
- Dispatch stays enabled when the hint says it will be refused: the server is the authority (there is no override, and a stale licence list must not block a valid dispatch).
- E2E selectors are unchanged (`rd-limit`, `rd-visual-*`, `rd-save`, `reading-saved`, `saved-exceedance`, `background-badge`, `background-note`, `exceedance-row`, `exceedance-peak`, `exceedance-margin`, `haz-deadlines`, `haz-deadline`, `area-check`, `check-*`, `check-save`, `acc-*`, `cn-*`, `provider-licence`, `form-error`, `sp-*`, `sp-reportable-preview`, `ek-tile`, `ek-value`, `ek-note`, `ek-chips`, `ek-breakdown`). New: `rd-missing`, `sp-missing`, `still-needed`, `background-not-counted`, `limit-bar` / `exceedance-bar`, `point-readings`, `acc-fields`, `acc-clear-*`, `acc-deadline`, `check-unsaved`, `licence-fit`, `cn-precheck`, `cn-refused`, `sp-reportable-why`, `ek-tile-target`, `ek-background`.
- Red stays for an exceedance, a refused dispatch and an overdue store; amber for alert results, a deadline ≤ 14 days, unsaved answers and the reportable preview; background dust is blue (information), never green.

## Design system additions (Phase 6e)

- **`components/env/common.tsx`**: `StillNeeded` (what blocks a phone save), `LimitBar` (value against limit, mirrored in Arabic), `BackgroundBadge explain`, English acronym fixes in `useEnvRef`.
- **`components/env/waste.tsx`**: `licenceFit` / `ProviderLicenceLine` with the CON-2 hint, the dispatch refusal line, the grouped hazardous dates in `AreaCheck`.
- Strings: `envDesign.*` in `scripts/i18n/p6-envdesign.py` (new keys only; a full `merge.py` adds them and changes nothing else).
- Screenshot spec: the design set in `screenshots-p6e.spec.ts` (`SHOT_SUFFIX`).
