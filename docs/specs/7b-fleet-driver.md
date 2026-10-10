# Module Spec — Option 7b: Fleet & Driver Safety (company and contractor landside fleet register, driver authorisation, pre-use vehicle checks, journey management, mileage, optional telematics and speeding imports, vehicle gate hook, road-safety KPIs)

**Version:** v1.0 · **Date:** 2026-10-10 · **Author:** HSE Consultant Agent · **Status:** **Planned, not started.** The HSE Manager asked for this option to be planned only. Do not build until he says go.
**Builds on:**
- `0-foundation.md` v1.5: contractors, engagements and tiers, scoping legend, rules 28, 35, 48, PDPL P1–P13, matrix ends at 232.
- `1-dashboard.md` v1.10 (v1.11 after 7a): incidents, KPI rules K-R1…K-R15, T1–T13, `rate_base_hours`.
- `2-access-permits.md` v1.7: worker register §3.1, **vehicle register §3.12** (plate, VC, Istimara, insurance, MVPI expiry), ADP §3.10 and offences §3.11, hooks HK-1…HK-5, gates GC-1…GC-11, QR kind `VS`, reason codes GC-6.
- `5-training.md`: hook provider HK5-x (`training_course`), course catalogue (AIRSIDE-DRV pattern).
- `6a-occupational-health.md`: `medical_fitness` provider, code **DRIVER-FIT**.
- `6d-field-assurance.md`: checklist templates §3.1–§3.2, responses §3.4–§3.5, inspection type `plant_vehicle`, findings → CAs.
- `6f-incident-followup.md`, `6g-scorecard-reports.md` (dataset registry, scorecard metrics list SM).
- **`7a-vehicle-accident-details.md` v1.0 — prerequisite.** 7b reads incident vehicle rows (K-136, VA-x). If Turki chooses 7b, 7a is built first as stage 0.

**Numbering taken by 7b:** capabilities **233–240**; KPIs **K-138…K-144**; warning **E26**; AI tool **T26**; charts **C42–C43**; CA source_type **`fleet`**; hook kind **`driver_authorisation`**; `ExpiringItemKind` `driver_auth_expiry`, `fleet_doc_expiry`, `journey_overdue`, `mileage_return_due`; QR kind reused: `VS` (vehicle sticker) and `AC` (driver's access card).

**Covers (build order):**
1. 7b.1 Fleet register: landside fields on the Phase 2 vehicle, documents, fleet sticker.
2. 7b.2 Driver authorisation with licence, training and medical hooks; points.
3. 7b.3 Pre-use checks on 6d templates; defect hold.
4. 7b.4 Journey management.
5. 7b.5 Mileage returns.
6. 7b.6 Telematics and speeding event imports (optional).
7. 7b.7 Gate hook for vehicles at site gates.
8. 7b.8 KPIs, warning, dashboard, AI.

**Not in 7b:** live GPS tracking or a telematics API connection (CSV import only); fuel management; maintenance scheduling beyond the pre-use defect hold; traffic-fine payment; visitor and delivery vehicle logging (§10 Q6); airside rules (Phase 2 owns ADP / AVP, unchanged).

Conventions as 6g. Rule prefixes: FL fleet, DA driver authorisation, PU pre-use, JM journey, MI mileage, TE telematics, VG vehicle gate, FK KPIs/AI, P7b- PDPL, BD7b boundary.

**The principle:** a vehicle and a driver are checked the same way as a crane and its operator in Phase 4: documents in date, a person authorised for that class, a daily check, and the platform tells the gate.

---

## 1. Purpose

On KSA projects most work-related deaths outside falls happen on roads: crew buses at dawn, pickups on long desert legs, tippers reversing on site roads. Phase 2 registers vehicles only to issue airside permits. Nobody checks that the landside fleet has valid Istimara, insurance and Fahas, that the driver holds the right licence class and a defensive-driving course, that the vehicle was checked this morning, or that the 400 km night trip to the quarry had a journey plan and arrived. The client asks for the motor vehicle crash rate per million km, which needs kilometres nobody collects.

7b adds: a landside fleet register (an extension of the Phase 2 vehicle, not a new register); driver authorisations; daily pre-use checks on 6d checklist templates; journey plans with check-in and overdue escalation; monthly mileage; optional telematics / speeding imports with driver points; a site-gate vehicle check; KPIs K-138…K-144, E26, T26, C42–C43.

## 2. Regulatory basis

| # | Source | What it drives here |
|---|---|---|
| R1 | **KSA Traffic Law** (Royal Decree M/85, 1428H) and Implementing Regulations `VERIFY`: licence classes, Istimara, periodic technical inspection (**MVPI / Fahas**, one inspection), compulsory insurance, seat belts, speed limits | FL-2 documents, DA-2 class check |
| R2 | **Transport General Authority (TGA)** rules for goods and passenger transport: operating card (بطاقة تشغيل) for buses and trucks, driver card, driving and rest hours `VERIFY` | `operating_card_expiry`, JM-4 driving-time limits |
| R3 | **SAMA** compulsory motor insurance (unified policy) `VERIFY` | insurance expiry |
| R4 | **IOGP Report 365** Land transportation safety recommended practice: journey management, in-vehicle monitoring (IVMS), driver training and assessment, KPIs per 1,000,000 km | JM, TE, K-138, K-143 |
| R5 | **ISO 39001:2012** RTS management system: performance factors (speed, seat belt, fitness, journey need) | KPI set, E26 |
| R6 | **Saudi Aramco** motor vehicle safety requirements where flowed down (GI 6.030 / CSM `VERIFY`) | Defensive-driving refresher, IVMS on contract vehicles (settings) |
| R7 | **MHRSD OSH** regulations: employer duty for safe transport of workers `VERIFY` article | Crew bus checks, JM for crew transport |
| R8 | **PDPL**: telematics events and journey data are location data about identifiable drivers | P7b-1…P7b-5 |

Strictest wins: the Fahas / Istimara / insurance dates are hard expiries (law); driving-time limits default to the stricter of TGA and IOGP 365 (ASSUMPTION §3.7); a speeding event never blocks a driver automatically — points do, after review.

## 3. Entities & fields

PDPL column: none / personal / sensitive. Every entity carries the Phase 0 system fields, is audited and stores `seed_fake`.

### 3.1 Fleet vehicle — Phase 2 vehicle (§3.12) with fields added by 7b

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| fleet_scope | نطاق الأسطول | enum | Y | `airside_only` (Phase 2 default for existing rows) · `landside` · `both` | landside | none |
| use_class | فئة الاستخدام | enum | cond. | landside / both: list FU | crew_bus | none |
| seats | عدد المقاعد | int | cond. | crew_bus, pool_car: 2–60 | 30 | none |
| operating_card_no / _expiry | بطاقة التشغيل | string(30) / date | cond. | required for crew_bus and goods_heavy (`OPERATING_CARD_REQUIRED`) `VERIFY` R2 | TEST-OC-5512 / 2027-01-31 | none |
| ivms_fitted / telematics_device_id | جهاز مراقبة / معرّف الجهاز | bool / string(40) | Y / cond. | id unique per project when fitted | true / IVMS-TEST-0107 | none |
| speed_limiter_kmh | محدد السرعة | int | N | 40–140 | 100 | none |
| last_odometer_km / at | آخر قراءة عداد | int / date | sys | from the latest mileage return or check | 84,120 / 2026-09-30 | none |
| fleet_sticker | ملصق الأسطول | QR `VS` | sys | issued when landside docs valid (FL-3); one token per vehicle shared with the AVP sticker when both | VS-…-0107 | none |
| fleet_status | حالة الأسطول | enum | sys | §4.1 | active | none |

Istimara, insurance and MVPI (Fahas) expiries are the existing Phase 2 fields (one MVPI field: MVPI and Fahas are the same inspection).

### 3.2 Driver authorisation — تفويض القيادة

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| auth_no | الرقم | string | sys | `DA-<project>-<nnnn>` | DA-ANIA-EXP-0042 | none |
| worker_id / deployment_id | العامل | FK | Y | Mobilised deployment on the project; one active authorisation per worker | WKR-000003 | personal |
| engagement_id | المقاول | FK | sys | from the deployment | GULFPAVE@ANIA-EXP | none |
| vehicle_groups | فئات المركبات | enum[] | Y | list DG; each must be covered by the licence class (list LCV of 7a, `LICENCE_CLASS_NOT_COVERING`) | [light, bus] | none |
| licence_issuer / class / expiry | الرخصة | enum / enum / date | Y | as Phase 2 ADP; expiry > today; KSA number not stored; prefilled from an ADP when one exists | ksa / public_transport / 2028-05-10 | personal |
| assessment_date / result / assessor | التقييم العملي | date / enum / string(120) | Y | result `passed`; ≤ 12 months before issue; assessor holds a DRV-ASSESSOR authorisation (Phase 5 trainer authorisation) or is external | 2026-08-20 / passed / Test Driving Academy | personal |
| issued_on / own_valid_until | الإصدار / الانتهاء | date | Y | own ≤ issued + `driver_auth_validity_months` | 2026-08-25 / 2028-08-24 | none |
| effective_valid_until | الصلاحية الفعلية | date | sys | §6.1 | 2028-05-10 | none |
| points_12m | النقاط خلال 12 شهراً | int | sys | §6.4 | 3 | personal |
| status | الحالة | enum | sys | §4.2 | active | none |

### 3.3 Pre-use check — الفحص اليومي قبل الاستخدام

A 6d checklist response (§3.4 of 6d) with owner `{type: vehicle_check, id}`; template kind `inspection`, inspection_type `plant_vehicle`, templates **VPU-L** (light), **VPU-H** (heavy / tipper / tanker), **VPU-B** (bus) seeded (Appendix A).

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| check_no | الرقم | string | sys | `VPC-<project>-<yyyymmdd>-<nnnn>` | VPC-ANIA-EXP-20261012-0031 | none |
| vehicle_id | المركبة | FK | Y | fleet_scope landside / both | VEH-0107 | none |
| driver_worker_id | السائق | FK | Y | worker with an active authorisation covering the vehicle's group (`DRIVER_NOT_AUTHORISED`) | WKR-000003 | personal |
| check_date / odometer_km | التاريخ / العداد | date / int | Y | one Completed check per vehicle per date per shift; odometer ≥ last_odometer_km (`ODOMETER_BACKWARDS`, warning when the vehicle was replaced) | 2026-10-12 / 84,302 | none |
| response | الإجابات | 6d response | Y | template pinned at start; result `pass` / `fail` by 6d §6.2; a failed critical item ⇒ defect hold (PU-3) | pass | personal (photos) |
| recorded_by | سجّلها | FK user | sys | the driver (when a user) or a supervisor / rep (236) | Ahmed | personal |
| paper_photo | صورة النموذج الورقي | file | N | when recorded from a signed paper card (PU-5) | — | personal |

### 3.4 Journey plan — خطة الرحلة

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| plan_no | الرقم | string | sys | `JP-<project>-<yyyy>-<nnnn>` | JP-ANIA-EXP-2026-0118 | none |
| vehicle_id / driver_worker_ids | المركبة / السائقون | FK / FK[1–2] | Y | drivers authorised for the group (DA) at departure | VEH-0107 / [WKR-000003] | personal |
| passengers | الركاب | int | Y | 0 … seats − drivers | 22 | none |
| origin / destination / route_text | من / إلى / المسار | string(120) ×2 / text(500) | Y | — | ANIA-EXP camp → Quarry Q3 / Hwy 65 | none |
| route_class | فئة المسار | enum | Y | list JR | desert_remote | none |
| distance_km | المسافة | int | Y | 1–2,000 | 410 | none |
| planned_depart / planned_arrive | المغادرة / الوصول المخطط | timestamptz | Y | arrive > depart; driving time per JM-4 | 2026-10-12 04:30 / 10:00 | none |
| rest_stops | التوقفات | list {place, at} | cond. | JM-4 | [Tamir fuel stn 07:00] | none |
| check_in_interval_min | فترة التواصل | int | Y | 30–240 | 120 | none |
| journey_manager_user_id | مدير الرحلة | FK user | Y | holds 238; ≠ the driver | Noura | personal |
| check_ins | نقاط التواصل | list {at, place, by, kind `depart` · `check_in` · `arrive` · `stopped`} | sys | — | — | personal |
| status | الحالة | enum | sys | §4.3 | in_progress | none |

### 3.5 Mileage return — بيان المسافات (vehicle × month)

vehicle_id; month; start_odometer_km / end_odometer_km (int; end ≥ start, `ODOMETER_BACKWARDS`); km (sys = end − start, or the telematics total when source `telematics`); source `odometer` · `telematics_import`; engagement_id (sys, the operator engagement at month end); remarks; submitted_by / at. One return per vehicle per month; km > `mileage_monthly_max_km` → warning `MILEAGE_UNUSUAL` and reason ≥ 20 chars. PDPL none.

### 3.6 Telematics event — حدث المراقبة (imported)

event_no `TEV-<project>-<yyyy>-<nnnnnn>`; import_batch_id; vehicle_id (matched by telematics_device_id, then plate; unmatched rows rejected `VEHICLE_UNMATCHED`); driver_worker_id (matched by driver tag id, else by the journey plan or the day's pre-use check; else null `driver_unknown`); event_type (list TE); occurred_at; speed_kmh / limit_kmh (speeding); duration_s; location_text (≤ 120, no coordinates stored, P7b-2); points (sys, list TE at import time); review_status `recorded` · `disputed` · `upheld` · `withdrawn` (only recorded / upheld count); reviewer, review note. PDPL personal.

**Import batch:** file (CSV, ≤ 20,000 rows; columns per the template in Appendix A); provider name; period; rows accepted / rejected with reasons; uploaded_by. Re-importing an identical row (device, type, occurred_at) is skipped (idempotent).

### 3.7 Phase 7b project settings (HSE Manager only, capability 240; audited; out of range → `SETTING_OUT_OF_RANGE`)

| Key | AR label | Type | Default | Allowed |
|---|---|---|---|---|
| fleet_register_from | بدء سجل الأسطول | date / null | null | ≤ today + 30; null = 7b off |
| driver_auth_validity_months | مدة تفويض القيادة | int | 24 ASSUMPTION | 12–36 |
| defensive_driving_code | رمز دورة القيادة الوقائية | course code | DEF-DRV | Phase 5 catalogue |
| driver_hook_policy | سياسة فحص السائق | enum | warn | warn · block |
| pre_use_required_groups | الفئات التي تتطلب فحصاً يومياً | DG[] | [light, heavy, bus] | any |
| journey_plan_km | مسافة تتطلب خطة رحلة | int | 150 ASSUMPTION | 50–500 |
| night_window | فترة القيادة الليلية | time range | 22:00–05:00 ASSUMPTION | — |
| max_continuous_drive_min / break_min | أقصى قيادة متصلة / الاستراحة | int / int | 120 / 15 ASSUMPTION `VERIFY` R2 | 60–240 / 10–45 |
| max_daily_drive_h | أقصى ساعات قيادة يومياً | decimal | 10.0 ASSUMPTION `VERIFY` R2 | 6.0–12.0 |
| journey_grace_min / escalate_min | مهلة التأخير / التصعيد | int / int | 30 / 60 | 10–120 / 30–240 |
| mileage_monthly_max_km | أقصى مسافة شهرية معقولة | int | 12,000 | 3,000–30,000 |
| driver_points_suspend | حد النقاط للإيقاف | int | 12 ASSUMPTION | 6–24 |
| fleet_gate_policy | سياسة بوابة المركبات | enum | warn | warn · block |

### 3.8 Reference lists (seeded EN/AR; codes immutable)

**FU — use class:** `pool_car` سيارة عامة · `crew_pickup` بيك أب للطاقم · `crew_bus` حافلة العمال · `goods_light` نقل خفيف · `goods_heavy` نقل ثقيل · `tanker` صهريج · `plant_road` معدة تسير على الطريق.
**DG — driver vehicle groups** (Phase 2 VC grouped): `light` (light_vehicle, pickup, van) · `bus` (bus) · `heavy` (truck, tipper, water_tanker, fuel_bowser, concrete_mixer) · `plant` (plate_type heavy_equipment categories).
**JR — route class:** `urban` · `highway` · `desert_remote` (no mobile coverage likely; check-in by satellite or radio) · `site_internal`.
**TE — telematics events (points, ASSUMPTION):** `speeding_minor` (limit + 10 to + 19 km/h) 1 · `speeding_major` (≥ limit + 20) 3 · `harsh_brake` 0 · `harsh_accel` 0 · `seatbelt_off` (> 30 s moving) 2 · `night_drive_no_plan` 2 · `excess_continuous_drive` 2 · `excess_daily_drive` 3. Zero-point events count in K-143 only.

## 4. Workflow / states

Jobs: `fleet_daily` 00:30 (document and authorisation validity, mileage due, expiring items), `fleet_minute` every 60 s (journey overdue).

### 4.1 Fleet vehicle (`fleet_status`, derived daily and on change)
`active` (all landside documents valid) → `docs_expired` (any of Istimara, insurance, MVPI, operating card past expiry; System) → `active` when renewed · any → `defect_hold` (PU-3; System) → `active` (234 clears with a repair note and a passing check) · any → `withdrawn` (234; Phase 2 status withdrawn).

### 4.2 Driver authorisation
Draft (235 or C proposes) → Active (235; DA-1) → Expired (System at effective_valid_until) · Active → Suspended (System at points ≥ `driver_points_suspend`, or 235 with reason) → Active (235 with reason ≥ 20 chars and, for points, a refresher record) · any → Revoked (235; final).

### 4.3 Journey plan
Draft (237) → Approved (238; JM-2) → In progress (depart check-in) → Arrived (arrive check-in) → Closed (System) · In progress → Overdue (System, JM-5) → Escalated (System) → Arrived / Closed with incident ref · Draft / Approved → Cancelled (237).

## 5. Business rules

### 5.1 Fleet (FL)
- FL-1. From `fleet_register_from`, every vehicle used on a landside site must be in the Phase 2 register with fleet_scope landside or both. Existing airside rows keep `airside_only` until edited.
- FL-2. Landside documents: Istimara, insurance and MVPI expiries required for plated vehicles (Phase 2 rule); operating card for crew_bus and goods_heavy. Expiry alerts at 30 / 14 / 7 / 0 days.
- FL-3. The fleet sticker (`VS`) is issued on the first save with valid documents and re-used for the AVP when the vehicle also gets one; a sticker of a `docs_expired`, `defect_hold` or `withdrawn` vehicle still scans, with the reason (VG-2).
- FL-4. Contractor HSE Reps register their own engagement's vehicles (C scope); the HSE Officer verifies document scans (`verified_by`); unverified documents produce `VEHICLE_DOCS_UNVERIFIED` (warn) at the gate.

### 5.2 Driver authorisation (DA)
- DA-1. Activation requires: licence class covering every group (LCV); licence expiry > today; a passed assessment ≤ 12 months old; hooks per DA-2 evaluated `met` or (policy warn) `warn`.
- DA-2. Hooks: `training_course: <defensive_driving_code>` (Phase 5; new course **DEF-DRV** Defensive driving / القيادة الوقائية, validity 36 months ASSUMPTION, plus **BUS-DRV** for group bus); `medical_fitness: DRIVER-FIT` (6a, existing code). Policy `driver_hook_policy`; Phase 2 HK-4 semantics.
- DA-3. Points: Σ points of recorded / upheld telematics events (TE) and Phase 2 airside offences of the same worker over 12 months. At ≥ `driver_points_suspend` the authorisation is Suspended and the HSE Officer and the rep are alerted. Reinstatement needs a DEF-DRV record dated after the suspension.
- DA-4. **Provider `driver_authorisation`** (new hook kind, HK-3 contract): `check(worker, driver_authorisation, code = DG group, at)` → met / expiring / not_met with `DRIVER_AUTH_MISSING`, `DRIVER_AUTH_SUSPENDED`, `DRIVER_AUTH_EXPIRED`. Used by VG-3 and available to Phase 3 crew role driver (setting, default off).

### 5.3 Pre-use checks (PU)
- PU-1. Required once per vehicle per shift-day for groups in `pre_use_required_groups`, before the first gate exit or journey departure.
- PU-2. Templates VPU-L / VPU-H / VPU-B are 6d templates (versioned, publishable by 193). Critical items: brakes, steering, tyres, seat belts, lights and indicators, reverse alarm (heavy), emergency exits and first-aid kit (bus).
- PU-3. A failed critical item sets fleet_status `defect_hold` and raises a 6d finding → CA (source `fleet`); the vehicle cannot pass a gate in block mode until cleared (VG-2).
- PU-4. A non-critical fail raises a finding only.
- PU-5. Paper fallback: a user with 236 records the answers with a photo of the signed card; marked `paper` in K-141 chips.

### 5.4 Journey management (JM)
- JM-1. A plan is required (`JOURNEY_PLAN_REQUIRED`) when distance_km ≥ `journey_plan_km`, or any part of planned_depart…planned_arrive falls in `night_window`, or route_class desert_remote, or use_class crew_bus off-site.
- JM-2. Approval checks: drivers authorised for the group at departure; vehicle `active`; pre-use check done or due before departure; driving time per JM-4; passengers ≤ seats − drivers; approver ≠ driver.
- JM-3. Check-ins: depart, every check_in_interval_min, arrive. Any user with 238 or the driver (when a user) records them; SMS / phone check-ins are typed in by the journey manager.
- JM-4. Planned driving time = distance ÷ `planned_avg_speed` (80 km/h highway, 60 urban, 50 desert_remote ASSUMPTION); > `max_continuous_drive_min` needs rest stops; > `max_daily_drive_h` per driver needs a second driver (`DRIVING_TIME_EXCEEDED`).
- JM-5. Overdue: no check-in for check_in_interval_min + `journey_grace_min`, or no arrive by planned_arrive + grace → Overdue, alert the journey manager; + `escalate_min` → Escalated, alert HSE Officers and HSE Manager with the last check-in. Closing an Escalated plan needs an outcome (`arrived_late` · `breakdown` · `incident` with ref).

### 5.5 Mileage (MI)
- MI-1. Monthly return per active landside vehicle due on day 5 of the next month (`mileage_return_due`). From the first accepted telematics import for a vehicle, the return is prefilled with the telematics km (source telematics_import).
- MI-2. K-138 and K-143 use only months where every active landside vehicle of the scope has a return (`km_complete`); otherwise they show "—" with "km incomplete: n vehicles missing".

### 5.6 Telematics (TE)
- TE-1. Imports are optional and per provider; 7b stores events, not GPS tracks.
- TE-2. A driver may dispute an event through the rep within 7 days; the HSE Officer upholds or withdraws.
- TE-3. `night_drive_no_plan` is derived at import when a trip in night_window has no Approved plan covering the vehicle.

### 5.7 Vehicle gate hook (VG) — extends Phase 2 GC
- VG-1. At a `site_gate` with `vehicle_checks` on (new gate attribute), a `VS` scan or a typed plate is checked for landside vehicles; then PENDING_DRIVER until the driver's access card is scanned (GC-9 pattern).
- VG-2. New reason codes (severity by `fleet_gate_policy`): `VEHICLE_NOT_REGISTERED` (typed plate not in the register), `VEHICLE_DOC_EXPIRED` (existing), `VEHICLE_DEFECT_HOLD` (always DENY), `PRE_USE_CHECK_MISSING`, `DRIVER_AUTH_MISSING`, `DRIVER_AUTH_SUSPENDED`, `DRIVER_AUTH_EXPIRED`, `JOURNEY_PLAN_REQUIRED` (exit only, WARN), `VEHICLE_DOCS_UNVERIFIED` (WARN).
- VG-3. Direction `out` still never denies (GC-11) except `VEHICLE_DEFECT_HOLD` in block mode ASSUMPTION (a defective bus must not leave with workers).

### 5.8 KPIs and AI (FK)
- FK-1. K-138…K-144 per §6.5; km and events attributed to the engagement operating the vehicle at the event (K-R5 descendants).
- FK-2. **T26 `get_fleet_summary`** (project_ids, period, filters {engagement_ids, include_descendants, use_class, group}, fields {km, mva_rate, events_by_type, events_per_10k_km, pre_use_compliance, journey_on_time, doc_compliance, auth_compliance}) returns aggregates only; no names, plates of individuals or locations. T13 returns E26. T3 gains dimension `use_class`.
- FK-3. 6g option: scorecard metric `SM-MVA` (K-138, pillar new `ROAD`) is listed but disabled in profile ORG (§10 Q5).

### 5.9 PDPL (P7b)
- P7b-1. Driver authorisations, points, check-ins, telematics events: **personal**; visible to A, P, and C for their engagement tree; S sees status only.
- P7b-2. No GPS coordinates or tracks stored; location_text only. Import files are deleted after 30 days (rows kept).
- P7b-3. Telematics events are used for safety coaching and authorisation; not exported to payroll or HR (purpose limitation, export purpose list excludes `disciplinary`).
- P7b-4. Retention: events 24 months; journey plans 5 years; authorisations project life + 2 years ASSUMPTION.
- P7b-5. AI receives aggregates only (FK-2).

### 5.10 Permission matrix — 7b extension (continues 6g §5.15)

| # | Capability | HSE Mgr | HSE Officer | Site Eng/Sup | Permit Issuer | Permit Receiver | Contractor HSE Rep | Viewer/Client | OH Pract. |
|---|---|---|---|---|---|---|---|---|---|
| 233 | View fleet, authorisations, checks, journeys, mileage, events | A | P | S (status only) | — | C1 | C | P (aggregates) | — |
| 234 | Register and edit fleet vehicles; clear defect hold; verify documents | A | P | — | — | — | C (own; no verify) | — | — |
| 235 | Activate, suspend, reinstate, revoke driver authorisations | A | P | — | — | — | C (propose only) | — | — |
| 236 | Record pre-use checks | A | P | S | — | C1 | C | — | — |
| 237 | Create, submit and cancel journey plans | A | P | S | — | C1 | C | — | — |
| 238 | Approve journey plans; act as journey manager; close escalations | A | P | S | — | — | C | — | — |
| 239 | Enter mileage returns; import telematics; review events | A | P | — | — | — | C (own; no review) | — | — |
| 240 | Fleet settings, event points, gate policy | A | — | — | — | — | — | — | — |

### 5.11 Phase-boundary rules (BD7b)
- BD7b-1. Phase 2 keeps the vehicle table, ADP, AVP and all airside rules; 7b only adds columns and the landside gate path.
- BD7b-2. 6d owns templates, responses, findings and CAs; 7b adds the owner type `vehicle_check`.
- BD7b-3. 7a owns accident data; 7b reads it for K-138 and links journey plans and events to incidents.

### 5.12 Error codes (new)
422 `OPERATING_CARD_REQUIRED`, `LICENCE_CLASS_NOT_COVERING`, `DRIVER_NOT_AUTHORISED`, `ODOMETER_BACKWARDS`, `JOURNEY_PLAN_REQUIRED`, `DRIVING_TIME_EXCEEDED`, `JOURNEY_APPROVER_IS_DRIVER`, `VEHICLE_UNMATCHED`, `MILEAGE_RETURN_EXISTS`, `FLEET_NOT_LIVE`, `SETTING_OUT_OF_RANGE`; 409 `VEHICLE_DEFECT_HOLD`, `AUTH_NOT_ACTIVE`; warnings `MILEAGE_UNUSUAL`, `VEHICLE_DOCS_UNVERIFIED`.

## 6. Calculations

### 6.1 Effective validity of an authorisation
effective_valid_until = min(own_valid_until, licence expiry, worker ID / Iqama expiry (Phase 2), deployment end, hook valid_until of DEF-DRV and DRIVER-FIT when the provider is registered).

### 6.2 Pre-use compliance (K-141)
used vehicle-day = (vehicle, date) with a gate `in` / `out`, a journey depart, or a telematics trip; compliant = a Completed check (pass or fail) on that date before the first such event. K-141 = compliant ÷ used × 100.

### 6.3 Driving time
planned_drive_min = distance_km ÷ planned_avg_speed × 60, rounded up to 5 min.

### 6.4 Points
points_12m = Σ points of TE events (recorded / upheld) + Phase 2 offence points (recorded / upheld) with occurred_at in (as_of − 12 months, as_of].

### 6.5 KPI catalogue (continues 7a §6.1)

| ID | Metric (EN / AR) | Formula | Unit | Better |
|---|---|---|---|---|
| K-138 | **Motor vehicle crash rate per million km** / معدل حوادث المركبات لكل مليون كم | n(K-137 events (crashes, own / contractor / hired vehicle, not commuting_own) with road_type site_road or public_road) × 1,000,000 ÷ K-139; airside events are excluded because airside km are not captured; "—" unless km_complete (MI-2) | per 1,000,000 km, 2 dp | lower |
| K-139 | Kilometres driven / المسافة المقطوعة | Σ km of mileage returns in period | km | — |
| K-140 | Driver authorisation compliance / التزام تفويض السائقين | drivers on pre-use checks, journey plans or gate driver scans in period with an Active authorisation at the time ÷ all such drivers × 100 | %, 1 dp | higher |
| K-141 | Pre-use check compliance / الالتزام بالفحص اليومي | §6.2 | %, 1 dp | higher |
| K-142 | Journeys completed without escalation / الرحلات دون تصعيد | n(plans Arrived / Closed in period never Escalated) ÷ n(plans Arrived / Closed in period) × 100 | %, 1 dp | higher |
| K-143 | Telematics events per 10,000 km / أحداث المراقبة لكل 10,000 كم | n(TE events recorded / upheld, IVMS vehicles) × 10,000 ÷ km of IVMS vehicles; chips by type | per 10,000 km, 2 dp | lower |
| K-144 | Fleet document compliance / التزام مستندات الأسطول | landside active vehicles with all documents valid at as_of ÷ landside vehicles not withdrawn × 100 | %, 1 dp | higher |

### 6.6 Leading-indicator warning
**E26 Road risk rising** (per project and per tier-1 tree, evaluated monthly and at each import): K-143 for the month ≥ 1.5 × mean of the 3 prior months with ≥ 10,000 km each; or K-141 < 80.0 %; or ≥ 1 journey Escalated with outcome incident; or ≥ 2 K-136 events for one engagement in the month. T13 inputs: engagement codes, values, thresholds; no names.

### 6.7 Worked examples (exact)
- **FW1** September 2026, ANIA-EXP landside fleet, with the 7a VW1 incidents as fixture: returns for all 38 vehicles, K-139 = 412,500 km. Crashes counted: 0201 (public_road, contractor pickup, MTC). Not counted: 0204 (near miss), 0209 (airside), 0212 (commuting_own, private car). K-138 = 1 × 1,000,000 ÷ 412,500 = 2.4242… = **2.42**.
- **FW2** IVMS vehicles 12, km 158,000, events: speeding_minor 9, speeding_major 2, seatbelt_off 3, harsh_brake 11 → 25 events; K-143 = 25 × 10,000 ÷ 158,000 = **1.58**.
- **FW3** Driver Jomar: speeding_major 3 pts (2026-06-02), speeding_major 3 (08-14), seatbelt_off 2 (09-03), airside offence OFF-01 3 (09-14), speeding_major 3 (10-11) → points_12m at 2026-10-12 = 14 ≥ 12 → Suspended 2026-10-11 at import.

## 7. Alerts & expiries

| Trigger | Recipient | Timing | Channel |
|---|---|---|---|
| Vehicle document expiry | Engagement reps; HSE Officers at 7 / 0 | 30 / 14 / 7 / 0 days | In-app + email |
| Authorisation expiry | Reps; driver's supervisor | 30 / 7 / 0 days | In-app |
| Authorisation suspended (points) | Reps, HSE Officers | At event | In-app + email |
| Defect hold set / cleared | Reps, HSE Officers | At event | In-app |
| Journey overdue / escalated | Journey manager / HSE Officers + HSE Manager | JM-5 | In-app + email + push |
| Mileage return due / overdue | Reps | Day 1 / day 6 | In-app |
| Import finished with rejected rows | Uploader | At completion | In-app |
| E26 | HSE Manager, HSE Officers, tier-1 rep | At evaluation | In-app + email |

## 8. Reports / KPIs fed

- **Dashboard:** "Road safety" band: K-138 (chip K-139), K-141, K-142, K-144 tiles; K-143 when imports exist. **C42** MVA rate per 1,000,000 km, R12 line with monthly km bars; **C43** telematics events per 10,000 km by engagement and type (stacked bars).
- **Expiring items / action panel:** kinds of the header; journeys Overdue / Escalated at the top of the action panel.
- **Registers:** fleet (landside filter, document status, sticker print), authorisations, pre-use checks, journey board (today, in progress, overdue), mileage returns with missing list, telematics events and imports. 6g datasets: `fleet_vehicles`, `driver_authorisations`, `journey_plans`, `mileage_returns`, `telematics_events` (personal columns per P7b-1).
- **Feeds:** Phase 1 CAs (source `fleet`); 7a incident rows link to journey plan and pre-use check of the day; 6g metric SM-MVA (disabled by default).

## 9. Acceptance criteria

Fixtures: Phase 0–6g seeds + 7a + Appendix A; clock 2026-10-12 10:00. Users as 7a plus Tariq (rep NAJD), Lina (HSE Officer RBT-52).

**Fleet**
1. **Given** `fleet_register_from` null **Then** fleet endpoints return 422 `FLEET_NOT_LIVE` and Phase 2 behaviour is unchanged.
2. **Given** a crew_bus without operating card **Then** 422 `OPERATING_CARD_REQUIRED`.
3. **Given** VEH-0107 insurance expiring 2026-10-19 **Then** alerts at 30 / 14 / 7 days were sent once each, and on 2026-10-20 fleet_status = docs_expired.
4. **Given** Ahmed (RAWABI rep) **Then** he registers RAWABI vehicles only; NAJD vehicles are not listed (C scope); he cannot verify documents.
5. **Given** a vehicle with both an AVP and landside use **Then** one `VS` token serves both and the scan shows both statuses.
6. **Given** K-144 at 2026-10-12 on the seed **Then** 36 ÷ 38 = 94.7 %.

**Driver authorisation**
7. **Given** groups [light, bus] with licence class private **Then** 422 `LICENCE_CLASS_NOT_COVERING`; with public_transport **Then** accepted.
8. **Given** an assessment 13 months old **Then** activation refused with the reason listed.
9. **Given** `driver_hook_policy` warn and no DEF-DRV record **Then** activation succeeds with `HOOK_NOT_MET_WARN`; in block **Then** 422.
10. **Given** a DRIVER-FIT expiring before own_valid_until **Then** effective_valid_until = the DRIVER-FIT date (§6.1).
11. **Given** FW3 **Then** points_12m = 14 and the authorisation is Suspended with an alert to Ahmed and Noura.
12. **Given** a Suspended authorisation **When** Noura reinstates without a DEF-DRV record dated after the suspension **Then** 422; with one **Then** Active.
13. **Given** Omar (site engineer) **Then** he sees authorisation status only, no points or licence data.

**Pre-use checks**
14. **Given** a VPU-L check with brakes failed **Then** result fail, fleet_status defect_hold, a finding and a CA (source fleet) exist.
15. **Given** a defect_hold vehicle **When** Noura clears it without a passing check **Then** 409; with one **Then** active.
16. **Given** a second check on the same vehicle, date and shift **Then** 422.
17. **Given** an odometer lower than last_odometer_km **Then** 422 `ODOMETER_BACKWARDS`.
18. **Given** a driver without an authorisation for the group **Then** 422 `DRIVER_NOT_AUTHORISED`.
19. **Given** a paper check recorded by Ahmed with a photo **Then** it counts in K-141 with chip "paper".
20. **Given** the seed for 2026-10-11 **Then** K-141 = compliant ÷ used vehicle-days per §6.2 as tabled in Appendix A (29 ÷ 32 = 90.6 %).

**Journeys**
21. **Given** a 410 km plan **Then** JM-1 requires it; a 90 km daytime urban trip **Then** not required.
22. **Given** a plan with planned drive 5 h 10 min and no rest stop **Then** 422 `DRIVING_TIME_EXCEEDED`; with a stop **Then** accepted; 11 h with one driver **Then** 422.
23. **Given** the journey manager is the driver **Then** 422 `JOURNEY_APPROVER_IS_DRIVER`.
24. **Given** passengers > seats − drivers **Then** 422.
25. **Given** JP-…-0118 departed 04:30 with interval 120 and no check-in by 07:00 **Then** Overdue at 07:00 and Escalated at 08:00 with alerts per §7.
26. **Given** an Escalated plan closed as incident **Then** an incident ref is required and linked.
27. **Given** K-142 for September on the seed **Then** 41 ÷ 43 = 95.3 %.

**Mileage and telematics**
28. **Given** a September return with end < start **Then** 422; with 14,000 km **Then** warning `MILEAGE_UNUSUAL` and a reason required.
29. **Given** one vehicle without a September return **Then** K-138 shows "—" with "km incomplete: 1 vehicle missing".
30. **Given** FW1 **Then** K-139 = 412,500 and K-138 = 2.42.
31. **Given** an import with a device id not in the register **Then** that row is rejected `VEHICLE_UNMATCHED`; the rest are accepted.
32. **Given** the same file imported twice **Then** no duplicate events.
33. **Given** FW2 **Then** K-143 = 1.58 with chips by type.
34. **Given** a night trip with no Approved plan **Then** a `night_drive_no_plan` event is derived (TE-3).
35. **Given** a disputed event withdrawn by Noura **Then** its points leave points_12m.
36. **Given** any fleet table or import **Then** no coordinates are stored (schema check) and import files are purged after 30 days.

**Gate**
37. **Given** `fleet_gate_policy` warn and a typed unknown plate **Then** GRANTED_WITH_WARNING `VEHICLE_NOT_REGISTERED`; in block **Then** DENIED.
38. **Given** a defect_hold vehicle in either policy **Then** DENIED `VEHICLE_DEFECT_HOLD`, also on `out` in block mode.
39. **Given** a valid vehicle and a driver with a Suspended authorisation **Then** after the driver scan the result carries `DRIVER_AUTH_SUSPENDED`.
40. **Given** a vehicle leaving at 23:00 on a trip with no plan **Then** WARN `JOURNEY_PLAN_REQUIRED`.
41. **Given** an airside_precheck gate **Then** Phase 2 GC-9 behaviour is unchanged.

**KPIs, AI, PDPL, i18n**
42. **Given** E26 inputs on the seed (K-141 RBT-52 September 76.0 %) **Then** E26 is raised for RBT-52 only.
43. **Given** the AI asked "speeding per 10,000 km by contractor" **Then** it answers from T26 with no driver names or plates.
44. **Given** Sarah (viewer) **Then** she sees aggregates only (233 P).
45. **Given** Arabic UI **Then** every 7b label, list value, alert and error has AR text; plates, km and refs stay left-to-right.
46. **Given** the seed **Then** Phase 1 W1–W3, Phase 2 gate results for existing tokens, 6g scorecards and 7a VW1 are unchanged.

## 10. Open questions for the HSE Manager

1. **Who is a fleet vehicle?** All company and contractor vehicles on landside sites, including hired buses? Or only vehicles above a size?
2. **Defensive driving:** 36-month refresher and an internal practical assessment every 24 months. Does your client (e.g. Aramco-style) require more?
3. **Journey plan trigger:** ≥ 150 km, night 22:00–05:00, desert routes, crew buses off-site. Right thresholds?
4. **Telematics:** do your contractors have IVMS, and which providers (CSV format)? Should IVMS be mandatory for buses and heavy vehicles?
5. **Scorecard:** add an MVA-rate metric (pillar ROAD) to the 6g contractor scorecard, or keep it on the dashboard only?
6. **Visitor and delivery vehicles:** log them at the gate (plate, company, escort) in 7b, or leave them to site security?
7. **Gate policy:** start in warn mode for 30 days, then block?

## 11. Changes required in earlier specs (to apply when 7b is built)

### 11.1 `0-foundation.md` → next
1. Matrix rows 233–240 (§5.10).

### 11.2 `1-dashboard.md` (v1.11 after 7a) → v1.12
1. §3.8 CA source_type `fleet`. 2. K-138…K-144, E26, T26 (T13 returns E26), T3 dimension `use_class`, C42–C43, the road-safety band and expiring kinds, by reference.

### 11.3 `2-access-permits.md` v1.7 → v1.8
1. §3.12 vehicle fields of 7b §3.1; `fleet_scope` default `airside_only` for existing rows.
2. HK-1 hook kind `driver_authorisation`; gate attribute `vehicle_checks`; GC-6 reason codes of VG-2 (order: after `VEHICLE_DOC_EXPIRED`); GC-9 pattern reused at site gates (VG-1); GC-11 exception VG-3.

### 11.4 `5-training.md`
1. Courses DEF-DRV and BUS-DRV in the catalogue; HK5-2 codes implemented + DEF-DRV, BUS-DRV.

### 11.5 `6a-occupational-health.md`
1. DRIVER-FIT population adds holders of an Active driver authorisation (group bus or heavy).

### 11.6 `6d-field-assurance.md`
1. Response owner type `vehicle_check`; templates VPU-L / VPU-H / VPU-B (Appendix A).

### 11.7 `6g-scorecard-reports.md`
1. Datasets of §8; metric SM-MVA and pillar ROAD listed, disabled in ORG.

### 11.8 `7a-vehicle-accident-details.md`
1. Incident vehicle row gains optional `journey_plan_id` and `pre_use_check_id`; K-138 defined here.

## Appendix A — Seed (fictional; `seed_fake = true`; refs contain `TEST`)

- `fleet_register_from` ANIA-EXP 2026-07-01, RBT-52 2026-09-01; gate G-LAND1 `vehicle_checks` on, policy warn.
- ANIA-EXP: 38 landside vehicles (GULFPAVE 12 incl. VEH-0107 Coaster crew_bus 30 seats, RAWABI 14, NAJD 9, SAHARA 3); 12 with IVMS; 2 with expired documents at the clock (K-144 = 94.7 %). RBT-52: 9 vehicles (QIMMA).
- 52 driver authorisations (WKR-000003 Jomar Santos per FW3, Suspended 2026-10-11); DEF-DRV records for 47.
- Templates VPU-L (14 items, 6 critical), VPU-H (18 / 8), VPU-B (20 / 9). Pre-use checks for September and 2026-10-11 (29 compliant of 32 used vehicle-days); one brakes fail on a RAWABI tipper → defect_hold, CA open.
- 43 journey plans in September (2 Escalated: one arrived_late, one breakdown); JP-ANIA-EXP-2026-0118 in progress at the clock.
- Mileage returns July–September for every vehicle (September total 412,500 km); RBT-52 September missing one return; RBT-52 September pre-use compliance 76.0 % (E26 fixture, AC42).
- Telematics: provider "Test IVMS" CSV, imports for July–October (FW2 for September); template columns: device_id, plate, driver_tag, event_type, occurred_at, speed_kmh, limit_kmh, duration_s, location_text.

## Change log

| Version | Date | Author | Change |
|---|---|---|---|
| v1.0 | 2026-10-10 | HSE Consultant Agent | First issue, planned only (awaiting the HSE Manager's go). |
