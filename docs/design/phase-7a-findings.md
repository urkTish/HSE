# Option 7a design pass: UX findings

Scope: the Option 7a "Vehicle accident details" screens (spec `docs/specs/7a-vehicle-accident-details.md` v1.2, decision D-244):
- Incident page: the "Vehicle accident" card (road, journey and conditions; vehicle rows; missing lists; investigation prompts; commuting proposals) and the "Accident report (archive)" card (authority, number, date, liability, close status, files and superseded versions, AC21 offer).
- Vehicle and road dialogs.
- Incident register: the vehicle filters, the "Recorded, not counted" filter and badge, and the plate / report no. column.
- Dashboard: the K-136 tile with its chips and chart C41.

Main users:
- Noura Al-Qahtani (HSE Officer), who records a crash on desktop and checks it on a phone.
- Sarah Mitchell (Viewer / Client), who must never see driver identity or report files.

Priorities:
- Costs readable at a glance.
- The register still shows the vehicle information at 1280 px.
- The archived police / Najm report is easy to find and hard to replace by mistake.
- Vehicle cards stay short at 390 px.

Shared conventions applied:
- D-238 tokens only.
- Irreversible record actions in a `RecordActions` band.
- Icon plus words for every state.
- Plates, refs and report numbers kept LTR inside Arabic.
- Compact cards at 390 px.

## Method

- **Setup.** Real backend on a fresh, migrated and seeded private database. It was `hse_e2e_design`, restored from a template copy before every run. The backend ran on port 8010 and the production build on port 3010. The shared e2e clock was 2026-10-06 10:00 Riyadh. The "before" set was taken first, from HEAD `3b72f0d`, before any change.
- **Users.** Noura (desktop and 390 px) and Sarah (desktop, Viewer).
- **Screenshots.** `screenshots-p7a.spec.ts` now takes `SHOT_SUFFIX=before|after` and then writes `docs/screenshots/phase-7a/design/<name>-<locale>-<suffix>.png`. Without the suffix it still writes the demo set to `docs/screenshots/phase-7a/` (regenerated after the fixes).

| Files | Screen |
|---|---|
| `01-incident-vehicles-{en,ar}-{before,after}` | INC-…-0295 (pickup v private car, Airport Road, Najm report archived), Noura |
| `02-incident-commuting-rnc-…` | INC-…-0299 (crew bus, commuting: recorded, not counted) |
| `03-register-vehicle-filter-…`, `04-register-recorded-not-counted-…` | Register with "Vehicle incidents only", and with "Recorded, not counted" |
| `05-dashboard-k136-…`, `06-dashboard-c41-…` | K-136 tile and C41 (September 2026) |
| `07-vehicle-dialog-…` | Add a vehicle |
| `08-incident-viewer-masked-…` | INC-…-0295 as the Viewer (identity and files withheld) |
| `09-incident-vehicles-390-…`, `10-register-390-…` | Noura at 390 px |

Effort: **S** < 1 h · **M** ≤ 1 day · **L** a redesign or a contract change that needs the user's approval.

## Ranked findings

| # | Impact | Problem | Where / evidence | Fix | Effort | Status |
|---|---|---|---|---|---|---|
| 1 | High | **Costs without thousands separators.** "Major · 18000.00 SAR", "4500.00 SAR" on the vehicle rows and the third-party damage. The Phase 1 property-damage line on the same page showed "… · 68000.00 SAR" with "SAR" in English on the Arabic page | `01-*-before`, `02-*-before`, `08-*-before` | `groupDecimal` (the man-hours helper): "18,000 SAR" / "18,000 ريال", with project digits. Property damage uses the same EN/AR "{cost} SAR" string. Presentation only: the value is the API's | `01-…-after`, `08-…-after` | S | Done |
| 2 | High | **The register lost the vehicle columns off-screen.** With a vehicle on the page, the plate and report no. were columns 10 and 11 of 12. At 1280 px both sat beyond the table's scroll edge, together with the status and the "Recorded, not counted" badge | `03-register-vehicle-filter-*-before` | One "Vehicle / report no." column: plates (LTR chips), then the report no. with a file icon under them. If there is no own plate, the road type shows instead. With the vehicle filter on, the column follows the title so it is in view at 1280 px. The test ids `row-plates` and `row-report-no` (LTR) are unchanged | `03-…-after`, `04-…-after` | S | Done |
| 3 | High | **Replacing an archived report was an inline link-style button.** "Upload corrected file" sat in the file row next to Download. It cannot be undone: the old file stays, marked superseded. The file name was cut to "NJM-TEST-202…" and its upload line wrapped to five lines | `01-*-before` (Report files), `09-*-before` | File rows are now a file icon, the full name (wraps, LTR) and the size, uploader and time, with the state badge, Download and Delete on their own line. Superseded files are struck through and muted. "Upload corrected file" moved to a `RecordActions` band at the card end, as a `destructive-outline` button. The band says "the current file is kept, marked superseded. This cannot be undone". `ar-replace` is unchanged; when there are several current files there is one button each, with its file name | `01-…-after`, `09-…-after` | S | Done |
| 4 | Medium | **The close status had no label.** A lone "Complete" badge under the report fields | `01-*-before` | "Needed to close:" before the badge (`ar-state` unchanged) | `01-…-after` | S | Done |
| 5 | Medium | **The edit and remove icons took their own row** on every vehicle card (≈ 50 px each, separated from the V1 / V2 title they belong to) | `01-*-before`, `09-*-before` | Title block `flex-1`, actions `shrink-0` beside it | `01-…-after`, `09-…-after` | S | Done |
| 6 | Medium | **The licence expiry had no label.** "KSA · Heavy transport · 31 May 2028 · 7 Muharram 1450 AH" read as one string | `01-*-before` | "valid until {date}" on its own muted line under issuer and class | `01-…-after` | S | Done |
| 7 | Medium | **Third-party damage in Arabic ran into the cost.** The English description and "4500.00 ريال" were reordered by bidi into "ريال boot lid · 4500.00" | `08-incident-viewer-masked-ar-before` | The description is `dir="auto"` and the cost is on its own line | `08-…-ar-after` | S | Done |
| 8 | Medium | **The register's yes/no filters were split.** "Recorded, not counted" wrapped onto the road-type line, away from "Vehicle incidents only" | `03-*-before` | The three checkboxes are one group on a row of their own, before the road-type, ownership and licence selects (it wraps to two lines inside the toolbar's filter column, but no longer mixes with a select) | `03-…-after` | S | Done |
| 9 | Low | **Dialog text did not fit the page.** The vehicle and road dialogs said "Vehicles are added on the incident page after saving", which is the incident form's hint, while the user was already on the incident page. In the vehicle dialog, "Documents valid at the time" sat tight on its three fields | `07-vehicle-dialog-*-before` | Text for each dialog: the vehicle one says what a row is and that a registered plate fills the vehicle and documents; the road one says that a change after the investigation is approved needs a reason. The documents group has a real legend with spacing | `07-…-after` | S | Done |
| 10 | Low | **Withheld files (Viewer) were plain grey text** | `08-*-before` | Lock icon with the existing sentence (`ar-files-hidden` unchanged) | `08-…-after` | S | Done |
| 11 | Low | **"Edit report" dropped under the card description** on desktop | `01-*-before` | The title block takes the free width; the button stays at the top end | `01-…-after` | S | Done |
| 12 | — | **Checked, no change.** The "Recorded, not counted — commuting (OSHA)" badge is info blue with an icon and the full words (AC17 / AC32 text unchanged). The K-136 chips show the backend's displays; the rnc chip is info. C41 colours follow the series palette; the K-137 line is on its own axis. Plates and report numbers stay LTR isolates in Arabic. Missing lists and investigation prompts are amber with an icon. At 390 px the vehicle rows are already compact cards (2 columns on desktop) | `05`, `06`, `02`, `09`, `10` | — | — | OK |

## Proposals (need the HSE Manager)

| # | Proposal | Effort |
|---|---|---|
| P52 | **A "Vehicle accidents" register view.** With the vehicle filter on, the register still carries the injury columns (cases, investigation) and hides road type, ownership, report state and liability. A saved view (with P7) whose columns are plate, ownership, road type, report authority / no., report state, liability % and third-party cost would let the HSE Officer chase missing Najm / police reports from one list | M |
| P53 | **Report state on the register row.** `accident_report_state` (`missing` · `complete` · `waived` · `not_required`) on `IncidentListItem` would put a "Report missing" flag in the register and the K-136 drill-down without opening each incident (contract change) | S (backend) |
| P54 | **Arabic chart citations.** C41 (and every chart) ends with "Sep 2026 · ANIA-EXP, all contractors · per 200,000 h" in English on the Arabic dashboard: `ChartSpec.citation` is one string. `citation_ar` (or the parts, to be formatted in the browser) would fix every chart at once | S (backend) |

## Not changed on purpose

- Business logic, API calls, permissions and the data shown are unchanged. Costs are formatted from the API's decimal strings (two decimals at most, no rounding). The register's "vehicle column first" only moves a column when the `vehicle_involved` filter is in the URL.
- Every e2e selector is kept: `vehicle-section`, `veh-row`, `veh-plate`, `veh-driver*`, `veh-licence-check`, `veh-add`, `veh-edit`, `veh-remove`, `accident-report-card`, `ar-number`, `ar-state`, `ar-file`, `ar-replace`, `ar-delete`, `ar-file-input`, `ar-files-hidden`, `ar-offer*`, `rnc-badge`, `rnc-filter`, `row-plates`, `row-report-no`, `incident-row`. New: `veh-cost`, `veh-tp-cost`, `ar-record-actions`.
- Red stays for expired documents and failed licence checks only. Amber is for missing data and prompts. Info blue is for "Recorded, not counted".

## Design system additions (Option 7a)

- `components/incidents/vehicle-section.tsx`:
  - The report-file row layout.
  - The report "Record actions" band.
  - Labelled close state and licence validity.
- `components/incidents/incident-list.tsx`:
  - `vehicleCell`, one column for plates and the report no.
  - The yes/no filter group.
- `components/incidents/incident-detail.tsx`: property damage cost grouped and localised.
- Strings: `vehDesign.*` in `scripts/i18n/p7-vehicledesign.py` (new keys only; `merge.py` adds 27 keys per locale and changes nothing else).
- Screenshot spec: `SHOT_SUFFIX` in `screenshots-p7a.spec.ts`.
