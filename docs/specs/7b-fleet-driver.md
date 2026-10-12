# Module Spec — Option 7b: Site Vehicle & Plant Readiness — **Prototype** (construction sites: vehicle and plant register fields and document expiry, driver / operator authorisation, daily pre-use checks, a minimal journey-plan form, three readiness KPIs)

**Version:** v2.1 · **Date:** 2026-10-12 · **Author:** HSE Consultant Agent · **Status:** **PROTOTYPE · backend built (v0.15.0).** Built as a prototype on the HSE Manager's go; frontend pending. Every 7b page carries a "Prototype" badge (نموذج أولي); the module is a lightweight first version for construction, to be grown only on his request.
**Builds on:**
- `0-foundation.md` v1.5: contractors, engagements and tiers, scoping legend, rules 28, 35, 48, PDPL P1–P13, matrix ends at 232.
- `1-dashboard.md` v1.10 (v1.11 after 7a): KPI rules K-R1…K-R15, T1 `get_kpis`, CA entity.
- `2-access-permits.md` v1.7: worker register §3.1, **vehicle register §3.12** (plate, VC, Istimara, insurance, MVPI expiry), ADP §3.10, hook policy semantics HK-4.
- `4-third-party-cert.md`: equipment item §3.4 (`vehicle_id` link, service_status), personnel certificates §3.9 and list PCT (PLANT-OPERATOR, FORKLIFT-OPERATOR, TELEHANDLER-OPERATOR …), defects §3.11 (source `pre_use_check`).
- `5-training.md`: hook provider HK5-x (`training_course`), course catalogue.
- `6a-occupational-health.md`: `medical_fitness` provider, code **DRIVER-FIT**.
- `6d-field-assurance.md`: checklist templates §3.1–§3.2, responses §3.4–§3.5, inspection type `plant_vehicle` (template PLT), findings → CAs.
- `7a-vehicle-accident-details.md` v1.1: **not a prerequisite** (7b reads no 7a data). When 7a exists, its incident vehicle row gains two optional links (§11.8). Recommended order is still 7a then 7b.

**Numbering taken by 7b:** capabilities **233–237**; KPIs **K-138…K-140**; no warning, no AI tool, no chart (E26, T26, C42 stay free); CA source_type **`site_vehicle`**; 6d response owner type **`vehicle_check`**; `ExpiringItemKind` `site_vehicle_doc_expiry`, `driver_auth_expiry`. No new QR kind, gate reason code, hook kind or scheduled job beyond one daily job.

**Covers (build order):**
1. 7b.1 Site vehicle & plant readiness: fields on the Phase 2 vehicle, document expiry, readiness status.
2. 7b.2 Driver / operator authorisation through the existing licence, training (Phase 5), medical (6a) and operator-certificate (Phase 4) hooks.
3. 7b.3 Daily pre-use checks on 6d templates; defect hold.
4. 7b.4 Journey plan — minimal form (prototype).
5. 7b.5 KPIs K-138…K-140, dashboard tiles, registers.

**Out of scope (security / logistics)** — HSE Manager 2026-10-11: "Logging is more of Security scope than HSE"; "This is for logistics I'm in construction":
- **Security:** gate logging of visitor and delivery vehicles (plate, company, escort); site-gate vehicle checks and vehicle reason codes at gates. Phase 2 gate behaviour is unchanged.
- **Logistics:** telematics / IVMS imports, speeding and driving-behaviour events, driver points and points-based suspension, mileage returns and kilometre-based rates (crashes per 1,000,000 km, events per 10,000 km), long-haul journey management (check-in intervals, overdue escalation, driving-time and rest-stop rules, desert-route classes, TGA driving-hour limits).

**Also not in 7b:** accident data (7a); TPI certification of plant and operator certificates (Phase 4 owns them; 7b reads them); airside rules (Phase 2 ADP / AVP unchanged); fuel, maintenance scheduling beyond the defect hold, traffic fines.

Conventions as 6g. Rule prefixes: SV site vehicle, DA driver authorisation, PU pre-use, JM journey (prototype), SK KPIs, P7b- PDPL, BD7b boundary.

**The principle:** on a construction site a tipper, a pickup, a crew bus or an excavator is ready when its documents (or Phase 4 certificate) are in date, it passed this morning's check, and its driver or operator is authorised for it.

---

## 1. Purpose

Tippers reversing, pickups on site roads, crew buses at dawn and earthmoving plant are a leading cause of serious injury on KSA construction sites. Phase 2 registers vehicles only for airside permits; Phase 4 certifies lifting and earthmoving plant but not the daily check or who may drive a site pickup or bus. The HSE Manager cannot answer "which site vehicles are not ready today, and who is driving them without authorisation?".

7b adds, as a lightweight prototype: readiness fields on the Phase 2 vehicle (no new register), driver / operator authorisations using hooks that already exist, daily pre-use checks on 6d templates with a defect hold, a minimal journey-plan form for off-site trips, and three KPIs.

## 2. Regulatory basis

| # | Source | What it drives here |
|---|---|---|
| R1 | **KSA Traffic Law** (Royal Decree M/85, 1428H) and Implementing Regulations `VERIFY`: licence classes, Istimara, periodic technical inspection (**MVPI / Fahas**), compulsory insurance | SV-2 documents, DA-1 class check |
| R2 | **Transport General Authority (TGA)**: operating card (بطاقة تشغيل) for buses and heavy goods vehicles on public roads `VERIFY` | `operating_card_expiry` |
| R3 | **OSHA 29 CFR 1926.600–602** (motor vehicles, mechanised equipment: brakes, reverse alarm, seat belts, inspection at the beginning of each shift) | Pre-use check items and critical items (PU-2) |
| R4 | **MHRSD OSH** regulations: employer duty for safe work equipment and safe transport of workers `VERIFY` article | Crew bus checks, authorisation |
| R5 | **ISO 39001:2012** performance factors (fitness, competence, vehicle condition) | KPI set |
| R6 | **PDPL**: authorisations and journey plans identify drivers | P7b-1…P7b-3 |

Strictest wins: Istimara, insurance, MVPI and operating-card dates are hard expiries (law); Phase 4 certificates win over 7b for certifiable plant.

## 3. Entities & fields

PDPL column: none / personal / sensitive. Every entity carries the Phase 0 system fields, is audited and stores `seed_fake`.

### 3.1 Site vehicle — Phase 2 vehicle (§3.12) with fields added by 7b

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| site_scope | نطاق الاستخدام | enum | Y | `airside_only` (Phase 2 default for existing rows) · `site` · `both` | site | none |
| use_class | فئة الاستخدام | enum | cond. | site / both: list SU | tipper | none |
| driver_group | فئة القيادة | enum | sys | from use_class via list SU → DG | heavy | none |
| seats | عدد المقاعد | int | cond. | crew_bus, crew_pickup: 2–60 | 30 | none |
| operating_card_no / _expiry | بطاقة التشغيل | string(30) / date | cond. | required for crew_bus and tipper / goods_heavy driven on public roads (`OPERATING_CARD_REQUIRED`) `VERIFY` R2 | TEST-OC-5512 / 2027-01-31 | none |
| equipment_id | المعدة (المرحلة 4) | FK | sys | read from the Phase 4 equipment item linked to this vehicle, when one exists | EQP-000214 | none |
| docs_verified_by / at | تحقق من المستندات | FK user / timestamptz | N | HSE Officer (SV-4) | Noura | personal (user) |
| idle_from / idle_to | خارج الخدمة مؤقتاً | date / date | N | marks the vehicle off-hire or parked; idle days need no pre-use check | — | none |
| readiness | الجاهزية | enum | sys | §4.1 | ready | none |

Istimara, insurance and MVPI (Fahas) expiries are the existing Phase 2 fields. Plant without a plate has no road documents; its readiness uses the Phase 4 status instead (SV-3).

### 3.2 Driver / operator authorisation — تفويض القيادة والتشغيل

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| auth_no | الرقم | string | sys | `DA-<project>-<nnnn>` | DA-ANIA-EXP-0042 | none |
| worker_id / deployment_id | العامل | FK | Y | Mobilised deployment on the project; one active authorisation per worker | WKR-000003 | personal |
| engagement_id | المقاول | FK | sys | from the deployment | GULFPAVE@ANIA-EXP | none |
| groups | الفئات | enum[] | Y | list DG | [light, bus] | none |
| licence_issuer / class / expiry | الرخصة | enum / enum / date | cond. | required for light, bus, heavy; as Phase 2 ADP; class covers every road group (list LCV of 7a, `LICENCE_CLASS_NOT_COVERING`); expiry > today; KSA number not stored; prefilled from an ADP when one exists | ksa / public_transport / 2028-05-10 | personal |
| assessment_date / assessor | التقييم العملي | date / string(120) | Y | ≤ 12 months before issue (`ASSESSMENT_TOO_OLD`) | 2026-08-20 / Test Driving Academy | personal |
| issued_on / own_valid_until | الإصدار / الانتهاء | date | Y | own ≤ issued + `driver_auth_validity_months` | 2026-08-25 / 2028-08-24 | none |
| effective_valid_until | الصلاحية الفعلية | date | sys | §6.1 | 2028-05-10 | none |
| hook_results | نتائج المتطلبات | list {kind, code, result, valid_until} | sys | DA-2 | — | personal |
| status | الحالة | enum | sys | §4.2 | active | none |

### 3.3 Pre-use check — الفحص اليومي قبل الاستخدام

A 6d checklist response (§3.4 of 6d) with owner `{type: vehicle_check, id}`; template kind `inspection`, inspection_type `plant_vehicle`; templates **VPU-L** (light vehicles and crew pickups), **VPU-H** (heavy vehicles and earthmoving plant), **VPU-B** (crew bus) seeded (Appendix A).

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| check_no | الرقم | string | sys | `VPC-<project>-<yyyymmdd>-<nnnn>` | VPC-ANIA-EXP-20261011-0031 | none |
| vehicle_id | المركبة / المعدة | FK | Y | site_scope site / both | VEH-0107 | none |
| driver_worker_id | السائق / المشغل | FK | Y | worker deployed on the project; PU-6 | WKR-000003 | personal |
| driver_authorised | السائق مفوض | bool | sys | PU-6 | true | personal |
| check_date | التاريخ | date | Y | one Completed check per vehicle per date (`PRE_USE_CHECK_EXISTS`) | 2026-10-11 | none |
| response | الإجابات | 6d response | Y | template pinned at start; result `pass` / `fail` by 6d §6.2; a failed critical item ⇒ PU-3 | pass | personal (photos) |
| recorded_by | سجّلها | FK user | sys | the driver (when a user) or a supervisor / rep (236) | Ahmed | personal |
| paper_photo | صورة النموذج الورقي | file | N | when recorded from a signed paper card (PU-5) | — | personal |

### 3.4 Journey plan (prototype) — خطة الرحلة (نموذج أولي)

A short form for trips off site (e.g. to a quarry, batching plant or another site). No check-ins, no escalation, no driving-time engine.

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| plan_no | الرقم | string | sys | `JP-<project>-<yyyy>-<nnnn>` | JP-ANIA-EXP-2026-0118 | none |
| vehicle_id / driver_worker_id | المركبة / السائق | FK / FK | Y | JM-2 | VEH-0107 / WKR-000003 | personal |
| passengers | الركاب | int | Y | 0 … seats − 1 (`PASSENGERS_EXCEED_SEATS`) | 22 | none |
| origin / destination | من / إلى | string(120) ×2 | Y | — | ANIA-EXP site → Quarry Q3 | none |
| distance_km | المسافة التقريبية | int | Y | 1–1,000 | 160 | none |
| planned_depart / planned_arrive | المغادرة / الوصول | timestamptz | Y | arrive > depart (`JOURNEY_TIMES_INVALID`) | 2026-10-12 05:30 / 08:00 | none |
| contact_user_id | جهة الاتصال | FK user | Y | ≠ the driver | Noura | personal (user) |
| notes | ملاحظات (المسار، التوقفات) | text(500) | N | — | Hwy 65, fuel stop Tamir | none |
| arrived_at | وقت الوصول | timestamptz | N | set by "Mark arrived" (236) | — | none |
| status | الحالة | enum | sys | §4.3 | planned | none |

### 3.5 Phase 7b project settings (HSE Manager only, capability 237; audited; out of range → `SETTING_OUT_OF_RANGE`)

| Key | AR label | Type | Default | Allowed |
|---|---|---|---|---|
| site_vehicles_from | بدء جاهزية مركبات الموقع | date / null | null | ≤ today + 30; null = 7b off |
| driver_auth_validity_months | مدة التفويض | int | 24 ASSUMPTION | 12–36 |
| defensive_driving_code | رمز دورة القيادة الوقائية | course code | DEF-DRV | Phase 5 catalogue |
| driver_hook_policy | سياسة متطلبات السائق | enum | warn | warn · block |
| driver_auth_policy | سياسة السائق غير المفوض في الفحص اليومي | enum | warn | warn · block |
| pre_use_required_groups | الفئات التي تتطلب فحصاً يومياً | DG[] | [light, bus, heavy, plant] | any |
| rest_weekday | يوم الراحة الأسبوعي | weekday | friday ASSUMPTION | any |
| journey_hint_km | مسافة تستدعي خطة رحلة | int | 150 (prototype) | 50–500 |
| journey_hint_night | فترة ليلية تستدعي خطة رحلة | time range | 22:00–05:00 (prototype) | — |

### 3.6 Reference lists (seeded EN/AR; codes immutable)

**SU — site use class → driver group:** `pool_car` سيارة عامة → light · `crew_pickup` بيك أب للطاقم → light · `crew_bus` حافلة العمال → bus · `tipper` قلاب → heavy · `goods_heavy` نقل ثقيل → heavy · `water_tanker` صهريج مياه → heavy · `earthmoving_plant` معدات ترابية → plant · `other_plant` معدة أخرى → plant.
**DG — driver / operator groups:** `light` · `bus` · `heavy` (licence class per LCV) · `plant` (no road licence; Phase 4 operator certificate when the item's EQC has an operator code, else a practical assessment only).

## 4. Workflow / states

One job: `site_vehicle_daily` 00:30 (readiness, document and authorisation expiry, expiring items).

### 4.1 Readiness (derived daily and on change; first matching state wins)
`withdrawn` (234; Phase 2 status withdrawn) · `idle` (today within idle_from…idle_to) · `defect_hold` (PU-3; cleared by 234 with a repair note and a passing check) · `not_certified` (linked Phase 4 item not `in_service`, read-only, SV-3) · `docs_expired` (Istimara, insurance, MVPI or operating card past expiry) · else `ready`.

### 4.2 Driver authorisation
Draft (235 or C proposes) → Active (235; DA-1) → Expired (System at effective_valid_until) · Active → Suspended (235 with reason ≥ 20 chars) → Active (235 with reason) · any → Revoked (235; final). No automatic suspension (no points).

### 4.3 Journey plan (prototype)
Planned (236) → Arrived ("Mark arrived", 236) · Planned → Cancelled (236). **Overdue** is a display flag only: Planned and now > planned_arrive + 60 min. It sends no alert and starts no escalation.

## 5. Business rules

### 5.1 Site vehicles (SV)
- SV-1. From `site_vehicles_from`, every vehicle and item of mobile plant used on the project's construction sites is in the Phase 2 register with site_scope site or both. Existing airside rows keep `airside_only` until edited.
- SV-2. Documents: Istimara, insurance and MVPI expiries required for plated vehicles (Phase 2 rule); operating card per §3.1. Expiry alerts at 30 / 14 / 7 / 0 days.
- SV-3. A vehicle linked to a Phase 4 equipment item takes `not_certified` from Phase 4 (service_status ≠ in_service). 7b never edits Phase 4 certificates or status.
- SV-4. Contractor HSE Reps register their own engagement's vehicles (C scope); the HSE Officer verifies document scans; an unverified vehicle shows `VEHICLE_DOCS_UNVERIFIED` (warning, readiness unchanged).

### 5.2 Driver / operator authorisation (DA)
- DA-1. Activation requires: for road groups, a licence class covering every road group (LCV) with expiry > today; a practical assessment ≤ 12 months old; hooks per DA-2 evaluated `met` or (policy warn) `warn`.
- DA-2. Existing hooks only: `training_course: <defensive_driving_code>` (Phase 5; new catalogue course **DEF-DRV** Defensive driving / القيادة الوقائية, validity 36 months ASSUMPTION; **BUS-DRV** for group bus) for road groups; `medical_fitness: DRIVER-FIT` (6a, existing code) for bus, heavy and plant; for plant, the Phase 4 `personnel_certificate` hook with the operator code of the item's EQC (e.g. PLANT-OPERATOR) when the vehicle links to a Phase 4 item. Policy `driver_hook_policy`; Phase 2 HK-4 semantics (`HOOK_NOT_MET_WARN` / 422 in block).
- DA-3. Hooks are re-evaluated by the daily job; a hook that turns not_met under block moves the authorisation to Expired with the reason.

### 5.3 Pre-use checks (PU)
- PU-1. Required once per vehicle per working day (not `rest_weekday`, not idle) for groups in `pre_use_required_groups`, before first use.
- PU-2. Templates VPU-L / VPU-H / VPU-B are 6d templates (versioned, publishable by 193). Critical items: brakes, steering, tyres, seat belts, lights and indicators, reverse alarm and beacon (heavy, plant), emergency exits and first-aid kit (bus).
- PU-3. A failed critical item: for a vehicle linked to a Phase 4 item, a Phase 4 Defect (source `pre_use_check`) is raised and Phase 4 takes the item out of service (readiness `not_certified`); for any other vehicle, readiness becomes `defect_hold` and a 6d finding → CA (source `site_vehicle`) is raised.
- PU-4. A non-critical fail raises a finding only.
- PU-5. Paper fallback: a user with 236 records the answers with a photo of the signed card; marked `paper` in K-140 chips.
- PU-6. driver_authorised = the driver holds an Active authorisation covering the vehicle's group on check_date. Under `driver_auth_policy` warn the check is saved with `DRIVER_NOT_AUTHORISED_WARN`; under block → 422 `DRIVER_NOT_AUTHORISED`.

### 5.4 Journey plan (JM, prototype)
- JM-1. The form shows the hint "A journey plan is recommended" when distance_km ≥ `journey_hint_km` or the trip touches `journey_hint_night`. The platform does not detect trips and never requires a plan.
- JM-2. Save checks: vehicle readiness ≠ defect_hold / not_certified / withdrawn (409 `VEHICLE_NOT_READY`); driver authorised for the group (PU-6 policy applies); passengers ≤ seats − 1; contact ≠ driver (`JOURNEY_CONTACT_IS_DRIVER`).

### 5.5 KPIs (SK)
- SK-1. K-138…K-140 per §6.4; contractor filter = the engagement operating the vehicle or employing the driver (K-R5 descendants).
- SK-2. AI reads K-138…K-140 through T1 `get_kpis` (aggregates only); no new tool.

### 5.6 PDPL (P7b)
- P7b-1. Authorisations, hook results, the driver on checks and journey plans: **personal**; visible to A, P, and C for their engagement tree; S sees authorisation status only; Viewer/Client sees aggregates only.
- P7b-2. No location data beyond the origin / destination text of a journey plan; no GPS, no tracks.
- P7b-3. Retention: pre-use checks 3 years; journey plans 2 years; authorisations project life + 2 years ASSUMPTION.

### 5.7 Permission matrix — 7b extension (continues 6g §5.15)

| # | Capability | HSE Mgr | HSE Officer | Site Eng/Sup | Permit Issuer | Permit Receiver | Contractor HSE Rep | Viewer/Client | OH Pract. |
|---|---|---|---|---|---|---|---|---|---|
| 233 | View site vehicles, readiness, authorisations, pre-use checks, journey plans | A | P | S (status only) | — | C1 | C | P (aggregates) | — |
| 234 | Register and edit site vehicles; verify documents; clear defect hold; withdraw | A | P | — | — | — | C (own; no verify) | — | — |
| 235 | Activate, suspend, reinstate, revoke driver / operator authorisations | A | P | — | — | — | C (propose only) | — | — |
| 236 | Record pre-use checks; create, cancel and mark arrived journey plans | A | P | S | — | C1 | C | — | — |
| 237 | 7b settings | A | — | — | — | — | — | — | — |

### 5.8 Phase-boundary rules (BD7b)
- BD7b-1. Phase 2 keeps the vehicle table, ADP, AVP, gates and all airside rules; 7b only adds columns. No gate path changes.
- BD7b-2. Phase 4 owns plant certification, operator certificates, defects on certified items and out-of-service; 7b reads them and raises Phase 4 defects (PU-3).
- BD7b-3. 6d owns templates, responses, findings and CAs; 7b adds the owner type `vehicle_check`.
- BD7b-4. 7a owns accident data; 7b offers links only (§11.8).

### 5.9 Error codes (new)
422 `OPERATING_CARD_REQUIRED`, `LICENCE_CLASS_NOT_COVERING`, `ASSESSMENT_TOO_OLD`, `DRIVER_NOT_AUTHORISED`, `PRE_USE_CHECK_EXISTS`, `PASSENGERS_EXCEED_SEATS`, `JOURNEY_TIMES_INVALID`, `JOURNEY_CONTACT_IS_DRIVER`, `SITE_VEHICLES_NOT_LIVE`, `SETTING_OUT_OF_RANGE`; 409 `VEHICLE_DEFECT_HOLD`, `VEHICLE_NOT_READY`, `AUTH_NOT_ACTIVE`; warnings `VEHICLE_DOCS_UNVERIFIED`, `DRIVER_NOT_AUTHORISED_WARN`.

## 6. Calculations

### 6.1 Effective validity of an authorisation
effective_valid_until = min(own_valid_until, licence expiry (road groups), worker ID / Iqama expiry (Phase 2), deployment end, hook valid_until of DEF-DRV / BUS-DRV, DRIVER-FIT and the Phase 4 operator certificate where they apply).

### 6.2 Required vehicle-days (K-140)
required = Σ over vehicles in `pre_use_required_groups` with site_scope site / both of the days in the period that are not `rest_weekday`, not idle, and on which readiness was not `withdrawn`; compliant = required days with a Completed check (pass or fail) on that date.

### 6.3 Authorised-driver records (K-139)
records = pre-use checks and journey plans (not Cancelled) in the period; authorised = those whose driver held an Active authorisation covering the group at the time.

### 6.4 KPI catalogue (continues 7a §6.1)

| ID | Metric (EN / AR) | Formula | Unit | Better |
|---|---|---|---|---|
| K-138 | **Site vehicle & plant readiness** / جاهزية مركبات ومعدات الموقع | vehicles with readiness `ready` at as_of ÷ site vehicles not `withdrawn` and not `idle` × 100; chips by readiness state | %, 1 dp | higher |
| K-139 | Driver / operator authorisation compliance / التزام تفويض السائقين والمشغلين | authorised ÷ records × 100 (§6.3) | %, 1 dp | higher |
| K-140 | Pre-use check compliance / الالتزام بالفحص اليومي | compliant ÷ required × 100 (§6.2); chip "paper" | %, 1 dp | higher |

Denominator 0 → "—".

### 6.5 Worked examples (exact; unit tests must match)
- **SW1** ANIA-EXP at 2026-10-12: 24 site vehicles, 1 idle → 23; not ready: 2 docs_expired, 1 defect_hold (RAWABI tipper), 1 not_certified (NAJD excavator EQP-TEST, Phase 4 out of service) → ready 19. K-138 = 19 ÷ 23 = 82.608… = **82.6 %**.
- **SW2** 2026-10-11 (Sunday): required 23 (24 − 1 idle), Completed checks 20 → K-140 = 20 ÷ 23 = 86.956… = **87.0 %**. Friday 2026-10-09 contributes 0 required days.
- **SW3** September 2026: 412 records (398 checks + 14 journey plans), 400 with an Active authorisation → K-139 = 400 ÷ 412 = 97.087… = **97.1 %**.

## 7. Alerts & expiries

| Trigger | Recipient | Timing | Channel |
|---|---|---|---|
| Vehicle document expiry | Engagement reps; HSE Officers at 7 / 0 | 30 / 14 / 7 / 0 days | In-app + email |
| Authorisation expiry | Reps; driver's supervisor | 30 / 7 / 0 days | In-app |
| Defect hold set / cleared | Reps, HSE Officers | At event | In-app |

No journey alerts (prototype; overdue is a list flag only).

## 8. Screens, reports, KPIs fed

- **Dashboard:** "Site vehicles (Prototype)" tiles K-138, K-139, K-140; no new chart.
- **Expiring items:** kinds of the header.
- **Registers:** site vehicles (readiness filter, document status, Phase 4 link), authorisations, pre-use checks (today's missing list per contractor), journey plans (Planned, Overdue flag, Arrived). Each page shows the "Prototype" badge.
- **Exports:** 6g datasets `site_vehicles`, `driver_authorisations`, `pre_use_checks`, `journey_plans` (personal columns per P7b-1).
- **Feeds:** Phase 1 CAs (source `site_vehicle`); Phase 4 defects (source `pre_use_check`); 7a incident vehicle rows may link the day's check and the journey plan.

## 9. Acceptance criteria

Fixtures: Phase 0–6g seeds (+ 7a when built) + Appendix A; clock 2026-10-12 10:00. Users as 7a plus Tariq (rep NAJD).

**Readiness**
1. **Given** `site_vehicles_from` null **Then** 7b endpoints return 422 `SITE_VEHICLES_NOT_LIVE` and Phase 2 behaviour is unchanged.
2. **Given** a crew_bus without operating card **Then** 422 `OPERATING_CARD_REQUIRED`.
3. **Given** VEH-0107 insurance expiring 2026-10-19 **Then** alerts at 30 / 14 / 7 days were sent once each, and on 2026-10-20 readiness = docs_expired.
4. **Given** Ahmed (RAWABI rep) **Then** he registers RAWABI vehicles only, NAJD vehicles are not listed, and he cannot verify documents.
5. **Given** the NAJD excavator linked to a Phase 4 item that is out of service **Then** readiness = not_certified and 7b offers no action that changes Phase 4 status.
6. **Given** SW1 **Then** K-138 = 82.6 % with chips docs_expired 2, defect_hold 1, not_certified 1.

**Driver / operator authorisation**
7. **Given** groups [light, bus] with licence class private **Then** 422 `LICENCE_CLASS_NOT_COVERING`; with public_transport **Then** accepted.
8. **Given** an assessment 13 months old **Then** 422 `ASSESSMENT_TOO_OLD`.
9. **Given** `driver_hook_policy` warn and no DEF-DRV record **Then** activation succeeds with `HOOK_NOT_MET_WARN`; in block **Then** 422.
10. **Given** group plant for the excavator and no in-force PLANT-OPERATOR certificate **Then** the Phase 4 hook result is not_met (warn / 422 as in AC 9).
11. **Given** a DRIVER-FIT expiring before own_valid_until **Then** effective_valid_until = the DRIVER-FIT date (§6.1).
12. **Given** Omar (site engineer) **Then** he sees authorisation status only, no licence or hook data.

**Pre-use checks**
13. **Given** a VPU-L check with brakes failed on a vehicle without a Phase 4 link **Then** result fail, readiness defect_hold, a finding and a CA (source site_vehicle) exist; clearing without a passing check → 409 `VEHICLE_DEFECT_HOLD`, with one → ready.
14. **Given** a VPU-H critical fail on the Phase 4-linked excavator **Then** a Phase 4 Defect (source pre_use_check) is raised, the item goes out of service and no 7b defect hold is set.
15. **Given** a second check on the same vehicle and date **Then** 422 `PRE_USE_CHECK_EXISTS`.
16. **Given** a driver without an authorisation for the group **Then** under warn the check is saved with `DRIVER_NOT_AUTHORISED_WARN` and counts as not authorised in K-139; under block **Then** 422 `DRIVER_NOT_AUTHORISED`.
17. **Given** a paper check recorded by Ahmed with a photo **Then** it counts in K-140 with chip "paper".
18. **Given** SW2 and SW3 **Then** K-140 for 2026-10-11 = 87.0 %, K-140 for 2026-10-09 = "—", and K-139 for September = 97.1 %.

**Journey plan (prototype)**
19. **Given** a 160 km plan, or a 40 km plan departing 04:30 **Then** the form shows the "recommended" hint; a 40 km daytime plan **Then** no hint; all three save.
20. **Given** a plan for a defect_hold vehicle **Then** 409 `VEHICLE_NOT_READY`; passengers > seats − 1 **Then** 422 `PASSENGERS_EXCEED_SEATS`; contact = driver **Then** 422 `JOURNEY_CONTACT_IS_DRIVER`.
21. **Given** JP-…-0118 still Planned 61 min after planned_arrive **Then** the list shows "Overdue"; no notification is created and no escalation runs; "Mark arrived" sets Arrived.

**Scope, PDPL, i18n**
22. **Given** Sarah (viewer) **Then** she sees K-138…K-140 aggregates only; the AI asked "pre-use compliance by contractor" answers from T1 with K-140 and no names or plates.
23. **Given** the seed **Then** Phase 2 gate results for existing tokens, Phase 4 KPIs, 6g scorecards and 7a VW1 are unchanged, and no gate reason code, telematics, mileage or points table exists (schema check).
24. **Given** Arabic UI **Then** every 7b label, list value, alert, error and the "Prototype" badge has AR text; plates and refs stay left-to-right.

## 10. HSE Manager answers and open questions

Answered by Turki (HSE Manager) on 2026-10-11:
- **Visitor and delivery vehicles / gate logging:** "Logging is more of Security scope than HSE" → out of scope (security); no gate changes.
- **Journey plan triggers:** "sure but dont put too much project leave it in its prototype since we dont have now" → minimal form, hint at 150 km or night, no escalation (§3.4, JM-1).
- **Telematics / points and suspension:** "This is for logistics I'm in construction (prototype again)" → telematics, points, mileage and km rates out of scope (logistics); 7b is a construction prototype.

Still open:
1. **Who is a site vehicle?** All company and contractor vehicles and mobile plant on construction sites, including hired crew buses?
2. **Defensive driving:** 36-month refresher and a practical assessment every 24 months. Does your client require more?

## 11. Changes required in earlier specs (to apply when 7b is built)

### 11.1 `0-foundation.md` → next
1. Matrix rows 233–237 (§5.7).

### 11.2 `1-dashboard.md` (v1.11 after 7a, else v1.10) → next
1. §3.8 CA source_type `site_vehicle`. 2. K-138…K-140, the "Site vehicles (Prototype)" tiles and the expiring kinds, by reference.

### 11.3 `2-access-permits.md` v1.7 → v1.8
1. §3.12 vehicle fields of 7b §3.1; `site_scope` default `airside_only` for existing rows. No gate change.

### 11.4 `4-third-party-cert.md`
1. Note that 7b raises Defects with the existing source `pre_use_check` and reads `personnel_certificate` hooks; no field change.

### 11.5 `5-training.md`
1. Courses DEF-DRV and BUS-DRV in the catalogue; HK5-2 codes implemented + DEF-DRV, BUS-DRV.

### 11.6 `6a-occupational-health.md`
1. DRIVER-FIT population adds holders of an Active authorisation with group bus, heavy or plant.

### 11.7 `6d-field-assurance.md`
1. Response owner type `vehicle_check`; templates VPU-L / VPU-H / VPU-B (Appendix A).

### 11.8 `6g-scorecard-reports.md` and `7a-vehicle-accident-details.md`
1. 6g: datasets of §8. 2. 7a (when built): incident vehicle row gains optional `pre_use_check_id` and `journey_plan_id`.

## Appendix A — Seed (fictional; `seed_fake = true`; refs contain `TEST`)

- `site_vehicles_from` ANIA-EXP 2026-07-01; RBT-52 null (7b off there).
- ANIA-EXP: 24 site vehicles and plant (GULFPAVE 8 incl. VEH-0107 Coaster crew_bus 30 seats; RAWABI 10 incl. 4 tippers; NAJD 6 incl. the excavator linked to Phase 4 item EQP-TEST-0214, out of service at the clock); at the clock 1 idle, 2 docs_expired, 1 defect_hold (RAWABI tipper, brakes fail, CA open) → SW1.
- 30 driver / operator authorisations (WKR-000003 Jomar Santos, groups [light, bus], Active); DEF-DRV records for 27; 2 drivers without an authorisation used on September checks.
- Templates VPU-L (12 items, 6 critical), VPU-H (16 / 8), VPU-B (18 / 9). Pre-use checks for September (398, SW3) and 2026-10-11 (20 of 23 required, SW2; 2 paper).
- 14 journey plans in September (all Arrived); JP-ANIA-EXP-2026-0118 Planned for 2026-10-12 05:30–08:00 (Overdue fixture when the clock is advanced).

## Change log

| Version | Date | Author | Change |
|---|---|---|---|
| v1.0 | 2026-10-10 | HSE Consultant Agent | First issue, planned only (awaiting the HSE Manager's go). |
| v2.0 | 2026-10-11 | HSE Consultant Agent | Reframed per the HSE Manager's answers as a construction-focused **prototype** "Site Vehicle & Plant Readiness". Kept: readiness fields on the Phase 2 vehicle and document expiry; driver / operator authorisation via existing licence, training, medical and Phase 4 operator hooks; pre-use checks on 6d templates; a minimal journey-plan form (hint only, no escalation). Moved to out of scope: gate logging and site-gate vehicle checks (security); telematics, speeding events, points and suspension, mileage and km rates, long-haul journey management (logistics). Numbering shrunk: capabilities 233–240 → 233–237; KPIs K-138…K-144 → K-138…K-140 (K-138 readiness, K-139 authorisation compliance, K-140 pre-use compliance); E26, T26, C42–C43 released; CA source `fleet` → `site_vehicle`; hook kind `driver_authorisation` and QR `VS`/`AC` reuse dropped. 7a no longer a prerequisite. ACs 46 → 24. Still planned only. |
| v2.1 | 2026-10-12 | HSE Consultant Agent | Backend built as a prototype (migration 0017, contract v0.15.0; DECISIONS D-250 onward). Earlier-spec changes of §11 applied (0-foundation v1.6, 1-dashboard v1.12, 2-access-permits v1.8, 4-third-party-cert v1.4, 5-training v1.4, 6a v1.2, 6d v1.4, 6g v1.2, 7a v1.2). Seed: the Phase 4 item linked to the NAJD excavator is the existing FX-EX-11 (EQP-000206) instead of a new EQP-TEST-0214 (D-251). No rule or worked-example value changes (SW1–SW3 exact). |
