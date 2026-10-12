# Option 7b design pass (Prototype): UX findings

Scope: the Option 7b "Site vehicle & plant readiness" Prototype screens (spec `docs/specs/7b-fleet-driver.md` v2.1, decisions D-258…D-262):
- Site vehicles register with the readiness summary, and the vehicle page (documents, readiness, certification, withdraw).
- Driver / operator authorisations (register and detail, Phase 4 / 5 hook badges, revoke).
- Pre-use checks (register, missing-today list, the pre-use form).
- Journey plans (form with the hint, register, detail, mark arrived, cancel).
- Site-vehicle settings, the dashboard tiles K-138…K-140 and the viewer aggregates.
- Phase 2 vehicle register "Site use" column and the site-use card on the Phase 2 vehicle page.

Main users:
- Noura Al-Qahtani (HSE Officer), who checks readiness every morning on desktop.
- A site engineer or supervisor, who records pre-use checks and journeys on a phone at the gate.
- Sarah Mitchell (Viewer / Client), who sees counts only.

Priorities:
- "Can this vehicle work today, and why not" readable at a glance, without colour alone.
- Phone lists short enough to use on site.
- Irreversible actions (withdraw, revoke, cancel) set apart.

Shared conventions applied:
- D-238 tokens only.
- Irreversible record actions as `destructive-outline` buttons with an icon.
- Icon plus words for every state.
- Plates, fleet numbers, km and refs kept LTR inside Arabic.
- Compact cards at 390 px.
- `StackedDate` (date, Hijri as a muted line) in tables.

## Method

- **Setup.** Same as 7a: the real backend on a fresh, migrated and seeded private database (`hse_e2e_design`, restored from a template copy before each run). The backend ran on port 8010 and the production build on port 3010. The shared e2e clock was 2026-10-06 10:00 Riyadh. The "before" set came from HEAD `3b72f0d`.
- **Screenshots.** `screenshots-p7b.spec.ts` takes `SHOT_SUFFIX=before|after` and writes `docs/screenshots/phase-7b/design/<name>-<locale>-<suffix>.png`. Without the suffix it writes the demo set to `docs/screenshots/phase-7b/` (regenerated after the fixes). Shots 16 and 17 (Phase 2 site use) are new in this pass, so they exist as "after" only.

| Files | Screen |
|---|---|
| `01-site-vehicles-…` | Register with the readiness summary, Noura |
| `02-vehicle-docs-expiring-…`, `03-vehicle-not-certified-…` | Vehicle page, documents expiring / no valid certificate |
| `04-authorisations-…`, `05-authorisation-detail-…` | Authorisations and one authorisation |
| `06-pre-use-checks-…`, `07-pre-use-form-…` | Check register with missing-today list, the pre-use form |
| `08-journey-form-hint-…`, `09-journeys-…` | Journey form with the hint, journey register |
| `10-settings-…`, `11-dashboard-tiles-…`, `12-viewer-aggregates-…` | Settings, K-138…K-140 tiles, the Viewer |
| `13-site-vehicles-390-…`, `14-pre-use-form-390-…`, `15-journeys-390-…` | Phone, 390 px |
| `16-phase2-register-site-use-…`, `17-phase2-vehicle-site-card-…` | Phase 2 vehicle register and vehicle page (after only) |

Effort: **S** < 1 h · **M** ≤ 1 day · **L** a redesign or a contract change that needs the user's approval.

## Ranked findings

| # | Impact | Problem | Where / evidence | Fix | Effort | Status |
|---|---|---|---|---|---|---|
| 1 | High | **Arabic plates broke one letter per line.** The plate chip could wrap, so "أ ب ج 1234" became a column of letters in narrow cells (vehicles, checks, journeys, Phase 2) | `01-*-ar-before`, `13-*-ar-before` | `Plate` chip `whitespace-nowrap` (still an LTR isolate) | `01-…-ar-after`, `13-…-ar-after` | S | Done |
| 2 | High | **Readiness was off-screen at 1280 px.** It was the last of eight columns, beyond the scroll edge, so the register's main answer was hidden | `01-site-vehicles-*-before` | Column order Vehicle, Readiness, Plate, Use class, Contractor, Today's check, Documents. The documents chip wraps inside its cell | `01-…-after` | S | Done |
| 3 | High | **Phone lists were very long.** Every cell became a labelled row: the vehicles list was 9,232 px and the journeys list 7,615 px at 390 px | `13-*-before`, `15-*-before` | New `compact` mode on `Table`: each row is a short card with the title and status badge on one line, then plate / use class / contractor, then dates. Labels only where a value needs one (`data-keep-label`, e.g. "Valid until"). Used on vehicles, authorisations, checks and journeys. Vehicles 9,232 → 4,739 px (EN), journeys 7,615 → 4,013 px | `13-…-after`, `15-…-after` | M | Done |
| 4 | High | **States by colour alone.** "Today's check" was a green / red / grey word; "Unverified" was grey text; the Phase 4 / 5 hook badges and the summary counts relied on colour | `01`, `04`, `05`, `11` before | Icons with the words: check done / defect / missing (CheckCircle2, OctagonAlert, ClipboardX, with a full-sentence title); ShieldQuestion for "Unverified"; CheckCircle2 / TriangleAlert / XCircle on hook badges; a warning icon beside red and amber summary counts above 0 | `01`, `04`, `05`, `11` after | S | Done |
| 5 | Medium | **Withdraw, revoke and cancel looked like ordinary buttons** | `02`, `05`, journey detail before | `destructive-outline` with Ban / XCircle icons (confirm dialogs unchanged) | `02`, `05` after | S | Done |
| 6 | Medium | **The summary row was one flat strip of 13 tiles**, with "Withdrawn" alone on the last line at 1280 px | `01-site-vehicles-*-before` | Two labelled groups, "Readiness now" (7 tiles) and "Today and the next 30 days" (6 tiles), each a grid of 2 / 4 / 7 and 2 / 3 / 6 columns. The tiles stay buttons that filter the list | `01-…-after` | S | Done |
| 7 | Medium | **The journey actions column was clipped at 1280 px** | `09-journeys-*-before` | "Mark arrived" sits under the status badge in the status cell (`jp-arrive` unchanged). Route gets the free width; depart / arrive use `StackedDate` with the time | `09-…-after` | S | Done |
| 8 | Medium | **The route arrow pointed the wrong way in Arabic.** "Origin → Destination" read backwards in RTL, and mixed-script place names reordered | `09-*-ar-before`, journey detail | Arrow follows the locale (← in Arabic); place names are bidi isolates | `09-…-ar-after` | S | Done |
| 9 | Medium | **The journey hint looked like an error** (amber with a lightbulb, reasons run together in one sentence) | `08-journey-form-hint-*-before` | Info tone, bold title, reasons as a bullet list (`jp-hint` and `data-reasons` unchanged) | `08-…-after` | S | Done |
| 10 | Medium | **Pre-use answers had no group semantics.** Pass / defect / N/A were three toggle buttons with extra icons; screen readers heard three unrelated buttons per item. No progress on a 20-item list | `07-pre-use-form-*-before`, `14-*-before` | `role="radiogroup"` / `role="radio"` with `aria-checked` and the shared `ChoiceMark`; the defect choice has a red outline when not chosen. The sticky bar shows "{done} of {total} items answered · defects: {n}" | `07-…-after`, `14-…-after` | S | Done |
| 11 | Medium | **The missing-today list ran long** (every vehicle without a check, one chip each) | `06-pre-use-checks-*-before` | First 6, then "Show all {n}" / "Show fewer" (`sv-missing-more`) | `06-…-after` | S | Done |
| 12 | Low | **Journey form order** put the contact before the driver | `08-*-before` | Vehicle, Driver, Contact | `08-…-after` | S | Done |
| 13 | Low | **Phase 2 "Site use" cell** repeated the use class and readiness as two badges; airside-only vehicles showed an empty badge | `16-*-after` (new) | Readiness badge then the use class in small muted text; airside-only shows a muted "—" with a title | `16-…-after` | S | Done |
| 14 | Low | **"Verified by" showed the English name in Arabic** | `02-*-ar-before` | `useLocalizedName` | `02-…-ar-after` | S | Done |
| 15 | Low | **Authorisation and check dates on one line** ("31 Mar 2027 · 23 Ramadan 1448 AH") wrapped mid-date | `04`, `06` before | `StackedDate` | `04`, `06` after | S | Done |
| 16 | — | **Checked, no change.** Settings (the switches and lists are already short); the dashboard tiles K-138…K-140 (backend displays, Prototype badge); the Viewer sees counts only and no names or plates (AC tests unchanged); the vehicle page's document rows already show the expiry state with icon and words | `10`, `11`, `12`, `03` | — | — | OK |

## Proposals (need the HSE Manager)

| # | Proposal | Effort |
|---|---|---|
| P55 | **Readiness board for the site office.** A kiosk / TV view of "can work today" per contractor with problems first and auto-refresh (shares the pattern of P17, tag board) | L |
| P56 | **Reminder for missing pre-use checks.** A notification to the contractor's HSE rep at a set time when vehicles have no check today (backend job and settings) | M (backend) |
| P57 | **One vehicle page.** Today a plate has a Phase 2 access page and a 7b site-vehicle page linked by a card. One page with tabs (access, site readiness, checks, journeys, incidents from 7a) would end the jumping between them | L |
| P58 | **Missing checks grouped by contractor** with counts and expand, instead of one long chip list, for sites with many contractors | M |

## Not changed on purpose

- Business logic, API calls, permissions and the data shown are unchanged. Readiness, document states, hook results and the journey hint reasons all come from the API, as before.
- Every e2e selector is kept (`sv-*`, `pu-*`, `jp-*`, `vehicle-site-use`, the summary tile buttons). New: `sv-missing-more`, `pu-progress`.
- The Prototype badge and wording stay. Nothing from "Out of scope (security / logistics)" was added.

## Design system additions (Option 7b)

- `components/ui/table.tsx` and `app/globals.css`: the `compact` mode for stacked tables (`data-full`, `data-keep-label`, flex order classes, empty cells hidden). Use it for phone lists where a row has a clear title and one status.
- `components/access/common.tsx`: `Plate` never wraps.
- `components/site-vehicles/common.tsx`: `DocChip` `wrap` option.
- Strings: `svDesign.*` in `scripts/i18n/p7-vehicledesign.py` (new keys only).
- Screenshot spec: `SHOT_SUFFIX` and shots 16 / 17 in `screenshots-p7b.spec.ts`.
