# Module Spec — Option 7a: Vehicle Accident Details (a vehicle-accident section on Phase 1 incidents: vehicles, drivers and licences at the time, road type, Najm / police report, third parties, seat belt and speed, commuting link, police / Najm notifications, vehicle-incident KPIs)

**Version:** v1.0 · **Date:** 2026-10-10 · **Author:** HSE Consultant Agent · **Status:** **Planned, not started.** The HSE Manager asked for this option to be planned only. Do not build until he says go.
**Builds on:**
- `1-dashboard.md` v1.10: incident (§3.3: zone, location_detail, incident_types, airside_flags `airside_vehicle_incident`, pd_asset_type `vehicle`, do_category `vehicle_overturn`, notifications), injury case (§3.4: person_type incl. `third_party_public`, mechanism, agency, commuting, worker_id), I-4 (commuting excluded from rates), I-20, P1-1…P1-8, capabilities 25, 26, 29, 31, lists M (mechanism `vehicle_plant_collision`, `vehicle_overturn`), G (agency `light_vehicle`, `heavy_vehicle`, `airside_gse`), O (`traffic_plant`, `airside_driving`), I (`plant_vehicle`), T3–T5, KPI catalogue K-01…K-47.
- `2-access-permits.md` v1.7: vehicle register §3.12 (plate, category list VC, owner_type, Istimara, insurance, MVPI / Fahas expiry), ADP §3.10 (licence_issuer, licence_class, licence_expiry_date; **KSA licence number not stored**), airside driving offence §3.11 (`incident_ref`), workers §3.1.
- `6f-incident-followup.md` v1.0: notification rules §3.1, triggers list NT, bodies, NR-1…NR-10, waiver list WV.
- `6g-scorecard-reports.md` v1.0: dataset registry (EX-1), numbering ends at capability 232, K-135, E25, T25, C40.

**Numbering taken by 7a:** KPIs **K-136…K-137**; chart **C41**; no new capability, warning or AI tool. Option 7b (`7b-fleet-driver.md`) continues from capability 233, K-138, E26, T26, C42.

**Not in 7a:** fleet and driver registers for landside vehicles, pre-use checks, journey management, mileage and telematics (all in 7b); insurance claim handling and money recovery; traffic fines (Saher).

Conventions as 6g: `VERIFY` = check against the current official text; `ASSUMPTION` = Consultant default the HSE Manager may override (§10); "must" = enforced server-side; rule prefix **VA**; error codes are stable strings (Phase 0 rule 48); times Asia/Riyadh.

---

## 1. Purpose

Road and site-traffic accidents are a top cause of death on KSA projects, yet the incident register today only says "vehicle" through a mechanism, an agency or a damage type. The HSE Manager cannot answer: which plate, whose vehicle, who was driving, was the licence valid for that vehicle on that day, was it on a public road, what is the Najm or police report number, was a third party hurt, was the seat belt worn, how fast. 7a adds one structured section to the incident, a police / Najm notification row through 6f, two KPIs and the AI filters. No new module and no new screens beyond the incident pages.

## 2. Regulatory basis

| # | Source | What it drives here |
|---|---|---|
| R1 | **KSA Traffic Law** (Royal Decree M/85, 1428H) and Implementing Regulations `VERIFY`: duty to stop, report and wait for the traffic police or Najm; licence classes; seat belt mandatory for driver and front passenger | Report fields, licence class check, seat belt field |
| R2 | **Najm for Insurance Services**: handles non-injury collisions in covered cities; issues an accident report number and liability percentage `VERIFY` coverage and whether injury accidents always go to the traffic police | `report_authority`, `report_no`, `liability_pct_own` |
| R3 | **Compulsory motor insurance** (SAMA unified policy) `VERIFY` | Third-party insurer / policy fields |
| R4 | **GOSI** occupational hazards: commuting accidents covered (Phase 1 R5) | Commuting link VA-7 |
| R5 | **ISO 39001:2012** road traffic safety management; **IOGP Report 365** land transport (motor vehicle crash classification, rate per 1,000,000 km) | KPI definitions; km rate deferred to 7b |
| R6 | **GACA / airport operator** airside driving rules (Phase 2 R4) | Airside road type, link to ADP offences |
| R7 | **PDPL** | Third-party names and plates of individuals are personal; masking per P7a |

Strictest wins: an accident on a public road is recorded even when the work_related answer is "commuting" (GOSI counts it; OSHA does not; Phase 1 I-4 unchanged).

## 3. Entities & fields

### 3.1 Incident — new fields (Phase 1 §3.3)

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| vehicle_involved | حادث مركبة | bool | sys + Y | derived true by VA-1; user may set true manually; cannot be false while VA-1 holds | true | none |
| road_type | نوع الطريق | enum | cond. | required when vehicle_involved: `site_road` طريق داخل الموقع · `airside` الجانب الجوي · `public_road` طريق عام; `airside` ⇔ zone_type airside (`ROAD_TYPE_ZONE_MISMATCH`) | public_road | none |
| road_location | موقع الطريق | string(200) | cond. | required for public_road (road name, direction, km marker) | Riyadh–Qassim Rd, northbound km 42 | none |
| journey_purpose | غرض الرحلة | enum | cond. | list JP; required when vehicle_involved | work_task | none |
| light / surface | الإضاءة / سطح الطريق | enum / enum | N | `daylight` · `dusk_dawn` · `dark_lit` · `dark_unlit` / `dry` · `wet` · `sand_on_road` · `gravel_unpaved` · `other` | dark_unlit / sand_on_road | none |
| report_authority | جهة محضر الحادث | enum | cond. | required for public_road: `najm` نجم · `traffic_police` المرور · `airport_operator` مشغل المطار · `none_internal` داخلي فقط (site_road / airside only, VA-5) | najm | none |
| report_no / report_date | رقم المحضر / تاريخه | string(40) / date | cond. | required to close the incident when authority ≠ none_internal (`ACCIDENT_REPORT_MISSING`); date ≥ occurred date | NJM-TEST-2026-00871 / 2026-09-21 | none |
| liability_pct_own | نسبة المسؤولية على مركبتنا | int | N | 0 · 25 · 50 · 75 · 100 (from the Najm / police report) `VERIFY` | 100 | none |
| report_file | صورة المحضر | file | N | PDF / image ≤ 10 MB; P1-3 hint | — | personal |
| third_party_damage_desc / _cost_sar | أضرار الطرف الثالث / تكلفتها | text(500) / decimal(12,2) | N | cost ≥ 0 | Private car rear bumper / 4,500 | none |

### 3.2 Incident vehicle — المركبة المتورطة (1–10 per incident; at least one when vehicle_involved, `VEHICLE_REQUIRED`)

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| seq | الرقم | string | sys | V1, V2 … | V1 | none |
| ownership | الملكية | enum | Y | `own_company` مركبة الشركة · `contractor` مركبة مقاول · `hired` مستأجرة · `third_party` طرف ثالث · `unknown` غير معروفة (hit and run) | contractor | none |
| engagement_id | المقاول | FK | cond. | required for own_company / contractor / hired; engagement on the project | GULFPAVE@ANIA-EXP | none |
| vehicle_id | المركبة في السجل | FK | N | Phase 2 vehicle (§3.12) of the same project; when set, prefills plate, category, make_model and document dates | VEH-0002 | none |
| plate_type / plate_letters_ar / plate_letters_en / plate_digits | اللوحة | enum / string(3) ×2 / string(4) | cond. | Phase 2 plate rules; required unless ownership unknown or plate_type none | private / ح ط ر / H T R / 9012 | none; **personal** for third_party |
| category | الفئة | enum | Y | Phase 2 list VC + `private_car` سيارة خاصة · `motorcycle` دراجة نارية · `bicycle_pedestrian` دراجة / مشاة | pickup | none |
| make_model | الطراز | string(60) | N | — | Toyota Hilux | none |
| role | الدور | enum | Y | `striking` المركبة الصادمة · `struck` المركبة المصدومة · `single_vehicle` حادث منفرد · `parked` متوقفة | striking | none |
| damage / damage_cost_sar | الضرر / التكلفة | enum / decimal(12,2) | Y / N | `none` · `minor` · `major` · `total_loss` | major / 18,000 | none |
| docs_valid_at_time | المستندات سارية وقت الحادث | {istimara, insurance, mvpi} each `valid` · `expired` · `unknown` | sys | from the Phase 2 vehicle when vehicle_id set; else entered | all valid | none |
| insurer / policy_no | شركة التأمين / الوثيقة | string(80) / string(40) | N | third_party only (own vehicles use the register) | Test Takaful / TEST-POL-7781 | personal |
| seat_belt | حزام الأمان (السائق) | enum | Y | `worn` · `not_worn` · `unknown` · `not_fitted` | worn | none |
| speed_kmh / speed_limit_kmh / speed_source | السرعة / الحد / المصدر | int / int / enum | N | 0–250 / 5–140; source `telematics` · `report` · `estimate` · `unknown` | 72 / 80 / report | none |
| driver_kind | السائق | enum | Y | `worker` عامل مسجل · `external` سائق خارجي · `none` لا يوجد (parked) | worker | none |
| worker_id | العامل | FK | cond. | driver_kind worker; Phase 2 worker with a deployment on the project at occurred_at | WKR-000003 | personal |
| external_driver_name | اسم السائق الخارجي | string(120) | cond. | driver_kind external | Test Driver | personal |
| licence_issuer / licence_class / licence_expiry | الرخصة: الجهة / الفئة / الانتهاء | enum / enum / date | cond. | lists as Phase 2 ADP (§3.10); required for driver_kind worker, optional for external; **KSA licence number not stored** (= holder ID, Phase 2); GCC / international number stored in `licence_no` string(30) | ksa / private / 2027-03-01 | personal |
| licence_check | فحص الرخصة وقت الحادث | enum | sys | VA-3: `valid` · `expired` · `wrong_class` · `no_licence` · `not_checked` | valid | personal |
| hours_on_duty | ساعات العمل قبل الحادث | decimal(4,1) | N | 0–24 | 9.5 | personal |
| driver_case_no | حالة الإصابة للسائق | int | N | person_no of a case on this incident | 1 | none |
| adp_offence_ref | مخالفة القيادة | FK | N | Phase 2 offence (§3.11), airside only | — | personal |

Third-party injured persons are injury cases with person_type `third_party_public` (unchanged Phase 1).

### 3.3 Reference lists (seeded EN/AR; codes immutable)

**JP — journey purpose:** `work_task` مهمة عمل · `material_delivery` توصيل مواد · `crew_transport` نقل العمال (company bus) · `commuting_company_transport` تنقل بوسيلة الشركة · `commuting_own` تنقل بوسيلة خاصة · `personal` شخصي · `other` أخرى.

**LCV — licence class covers vehicle category** (VA-3; `VERIFY` R1): `private` → light_vehicle, pickup, van, private_car · `public_transport` → + bus · `heavy_transport` → + truck, tipper, water_tanker, fuel_bowser, concrete_mixer · `heavy_equipment` → plant categories of list VC (cranes, loaders, excavators, rollers …) · `motorcycle` → motorcycle. Airside GSE without plate: ADP class check (Phase 2) instead.

## 4. Workflow

No new states. The section is part of the incident (Phase 1 §4.2). It may be filled at Draft and edited until the incident is Closed. Edits after the investigation is Approved are audited with a reason ≥ 20 chars (Phase 1 rule).

## 5. Business rules

- **VA-1.** vehicle_involved is set true (and cannot be cleared) when any of: a case with mechanism `vehicle_plant_collision` or `vehicle_overturn`; a case with agency `light_vehicle`, `heavy_vehicle` or `airside_gse`; pd_asset_type `vehicle`; do_category `vehicle_overturn`; airside flag `airside_vehicle_incident`. A near miss may set it manually.
- **VA-2.** Submit (Draft → Reported) requires road_type and ≥ 1 vehicle row with ownership and role; the remaining required fields are needed before the investigation is submitted for approval (`VEHICLE_SECTION_INCOMPLETE`, listing the missing fields). Speed of reporting comes first.
- **VA-3.** licence_check is computed when the row is saved: `no_licence` when the worker has no licence fields and driver_kind worker; `expired` when licence_expiry < occurred date (local); `wrong_class` when the class does not cover the category (list LCV); else `valid`. For external drivers without licence data → `not_checked`. A worker driver with an ADP on the project prefills issuer, class and expiry from the ADP (editable, audited).
- **VA-4.** When vehicle_id is set, docs_valid_at_time is computed from the Phase 2 dates at the occurred date and frozen at incident Closed. An expired document or a licence_check ≠ valid raises an **investigation prompt** (a required root-cause consideration: "Vehicle documents / licence not valid at the time"), not a block.
- **VA-5.** road_type public_road requires report_authority ≠ none_internal (`ACCIDENT_REPORT_AUTHORITY_REQUIRED`). report_no is required to close the incident unless waived through the 6f waiver of the police / Najm requirement (reason `body_confirmed_not_required` with evidence).
- **VA-6.** Plates are normalised (Arabic letters mapped to their Latin pair, Phase 2 rule) and matched to the Phase 2 register; a match on an own / contractor row suggests vehicle_id. A plate of the register entered on a third_party row → 422 `PLATE_IS_REGISTERED`.
- **VA-7.** **Commuting link:** journey_purpose `commuting_company_transport` or `commuting_own` ⇒ every case of a worker driver or passenger of an own / contractor / hired vehicle is proposed commuting = true (the classifier confirms). A case with commuting = true on an incident whose journey_purpose is not commuting gets the warning `COMMUTING_PURPOSE_MISMATCH` (not a block). Rates follow Phase 1 I-4 unchanged; GOSI requirements unchanged.
- **VA-8.** On airside, an ADP holder driving an own / contractor vehicle links to the Phase 2 offence when one is recorded for the same event; 7a never creates offences.
- **VA-9.** The incident title and description still pass the P1-3 name check; plates are allowed in text.

### 5.1 Notifications (6f)
- **VA-10.** 6f gets two triggers (list NT): `rta_public_injury` (road_type public_road and ≥ 1 case of any person_type, not FAC-only `VERIFY`) and `rta_public_no_injury` (public_road, no case or FAC only). Phase 1 body list adds `najm`.
- **VA-11.** Seeded statutory rows (only tighten, NR-3): **POL-RTA** police · verbal · [rta_public_injury] · 1 h · main_contractor; **NAJM-V** najm · verbal · [rta_public_no_injury] · 1 h · main_contractor `VERIFY` R2. The submission's reference is the report_no; entering report_no on the incident offers to record the submission. The existing GOSI-W commuting row and POL-V fatality row are unchanged.
- **VA-12.** Before a project's `followup_rules_from`, Phase 1 I-20 adds the item `police` (written stage display) for public-road accidents with injury, and nothing for Najm.

### 5.2 PDPL (P7a)
- **P7a-1.** Driver identity (worker link, external name), licence fields, licence_check, hours_on_duty, third-party plates of private vehicles, insurer and policy are **personal**; visible with capability 29 only. Others see "Driver: worker of GULFPAVE · licence valid" (licence_check stays visible as a category; names, classes, dates hidden).
- **P7a-2.** AI tools and KPIs receive no driver names, plates of third_party rows or report files. T4/T5 return ownership, category, road_type, seat_belt, speed band, licence_check category.
- **P7a-3.** Retention follows Phase 1 P1-5; third-party identity and report files are anonymised with the injured-person identity fields.

### 5.3 Error codes (new)
422 `ROAD_TYPE_ZONE_MISMATCH`, `VEHICLE_REQUIRED`, `VEHICLE_SECTION_INCOMPLETE`, `ACCIDENT_REPORT_AUTHORITY_REQUIRED`, `ACCIDENT_REPORT_MISSING`, `PLATE_IS_REGISTERED`; warnings `COMMUTING_PURPOSE_MISMATCH`, `VEHICLE_DOCS_EXPIRED_AT_TIME`, `LICENCE_NOT_VALID_AT_TIME`.

### 5.4 Capabilities
None new. Report / edit: 25 (submit) and the incident edit rights of Phase 1; driver and third-party identity: 29; register view: 31.

## 6. Calculations

### 6.1 KPI catalogue (continues 6g §6.7)

| ID | Metric (EN / AR) | Formula | Unit | Better |
|---|---|---|---|---|
| K-136 | **Vehicle incidents** / حوادث المركبات | n(incidents with vehicle_involved, status ∉ {Draft, Voided}, occurred in period); chips by road_type, by primary_type, and n with injury; contractor filter = responsible engagement (K-R5) | count | lower |
| K-137 | **Vehicle incident rate** / معدل حوادث المركبات | n(K-136 events whose incident_types include injury_illness or property_damage (crashes; near-miss-only events excluded), with ≥ 1 own_company / contractor / hired vehicle and journey_purpose ≠ commuting_own) × B ÷ MH (B = `rate_base_hours`, 200,000) | per 200,000 h, 2 dp | lower |

- Commuting events stay in K-136 (labelled) and are excluded from K-137 unless `include_commuting_in_rates` = true (Phase 1 setting).
- The distance rate per 1,000,000 km is **K-138 in 7b** and is shown only where 7b captures kilometres. 7a never estimates km.
- Denominator 0 → "—".

### 6.2 Worked example (exact; unit tests must match)
**VW1** ANIA-EXP, September 2026, MH = 1,240,000 h (unit-test fixture; the seed's real September hours give their own value). Vehicle incidents: INC-…-0201 (public_road, contractor pickup, MTC), INC-…-0204 (site_road, near miss, contractor tipper), INC-…-0209 (airside, GSE damage, contractor), INC-…-0212 (public_road, commuting_own, private car, LTI). K-136 = 4 (public_road 2, site_road 1, airside 1; with injury 2). K-137 counts 0201 and 0209 (0204 is a near miss, 0212 is commuting_own in a private car) = 2 × 200,000 ÷ 1,240,000 = 0.32258… = **0.32**. With `include_commuting_in_rates` true, 0212 still has no own / contractor / hired vehicle → K-137 unchanged.

## 7. Alerts

| Trigger | Recipient | Timing | Channel |
|---|---|---|---|
| Police / Najm requirement due / overdue | 6f recipients | 6f rules | 6f |
| Licence or vehicle documents not valid at the time (VA-4) | Investigation lead, HSE Officers | When computed | In-app |
| report_no missing 7 days after a public-road accident | Reporter's HSE Officer | Day 7, then weekly | In-app |

## 8. Dashboard, registers and AI

- **Dashboard:** K-136 tile (chip K-137); chart **C41** vehicle incidents per month for 12 months, stacked by road_type, with the K-137 line.
- **Incident register:** filter "vehicle involved", road_type, ownership, licence_check; columns plate (own / contractor only) and report_no. Incident page: a "Vehicles" section card after the cases; each vehicle row as a compact card on phones.
- **Exports:** 6g dataset `incident_vehicles` (one row per vehicle; driver identity, licence and third-party columns class personal, capability 29).
- **AI:** T3 dimensions + `road_type`, `vehicle_ownership`, `licence_check`, `seat_belt`; T4 filters + `vehicle_involved`, `road_type`; T5 detail + vehicle rows (P7a-2). T9 can compare by `road_type` and `journey_purpose`. AI-10 adds: "vehicle incidents by road type, ownership and contractor; share with seat belt not worn; share with licence not valid".

## 9. Acceptance criteria

Fixtures: Phase 0–6g seeds + Appendix A; clock `HSE_CLOCK_AT` = 2026-10-12 10:00. Users: Faisal (HSE Manager), Noura (HSE Officer ANIA-EXP), Ahmed (Contractor HSE Rep RAWABI tree), Omar (site engineer), Sarah (viewer).

1. **Given** a Draft incident with a case of agency `light_vehicle` **Then** vehicle_involved is true and cannot be set false (422).
2. **Given** a near miss with no vehicle signal **Then** Noura may set vehicle_involved true manually and must add a vehicle row.
3. **Given** vehicle_involved and no road_type **When** Submit **Then** 422 `VEHICLE_SECTION_INCOMPLETE` listing road_type; with road_type and one row (ownership, role) **Then** Reported.
4. **Given** road_type airside on a landside zone **Then** 422 `ROAD_TYPE_ZONE_MISMATCH`.
5. **Given** road_type public_road and report_authority none_internal **Then** 422 `ACCIDENT_REPORT_AUTHORITY_REQUIRED`.
6. **Given** a public-road incident with authority najm and no report_no **When** Faisal closes it **Then** 422 `ACCIDENT_REPORT_MISSING`; with report_no **Then** closed.
7. **Given** a row with vehicle_id VEH-0002 **Then** plate, category and make_model are prefilled and docs_valid_at_time is computed from Phase 2 dates.
8. **Given** VEH-0002 with insurance expired before the occurred date **Then** docs_valid_at_time.insurance = expired, warning `VEHICLE_DOCS_EXPIRED_AT_TIME` and the investigation prompt appear.
9. **Given** a worker driver with licence class private on a tipper **Then** licence_check = wrong_class; with expiry before the occurred date **Then** expired.
10. **Given** a worker driver who holds an ADP **Then** issuer, class and expiry are prefilled from the ADP and no KSA licence number field is offered.
11. **Given** an external driver without licence data **Then** licence_check = not_checked and no block.
12. **Given** a third_party row with a plate that exists in the Phase 2 register **Then** 422 `PLATE_IS_REGISTERED`.
13. **Given** journey_purpose commuting_own **Then** worker cases of that vehicle are proposed commuting = true; Faisal confirms; K-21 TRIR excludes them (I-4 unchanged) and the GOSI requirement exists.
14. **Given** a commuting case on an incident with journey_purpose work_task **Then** warning `COMMUTING_PURPOSE_MISMATCH` is shown and the save succeeds.
15. **Given** a public-road accident with an MTC case after `followup_rules_from` **Then** a POL-RTA police verbal requirement is due at occurred_at + 1 h; with no case **Then** a NAJM-V requirement instead.
16. **Given** the POL-RTA row **When** Faisal raises deadline_hours to 2 **Then** 422 `RULE_LOOSENING`; lowering is accepted.
17. **Given** report_no entered on the incident **Then** the user is offered to record the 6f submission with that reference.
18. **Given** a public-road incident before `followup_rules_from` **Then** Phase 1 I-20 shows a `police` item.
19. **Given** Sarah (viewer) or Omar (site engineer) opens a vehicle incident **Then** they see ownership, category, plate of own / contractor vehicles, licence_check category and no driver name, licence class or expiry, third-party plate or policy (P7a-1).
20. **Given** Noura **Then** she sees driver identity and licence data (capability 29).
21. **Given** VW1 **Then** K-136 = 4 with chips public_road 2, site_road 1, airside 1; K-137 = 0.32 per 200,000 h.
22. **Given** VW1 with `include_commuting_in_rates` true **Then** K-137 is still 0.32.
23. **Given** Ahmed (RAWABI tree) **Then** K-136 and the register show only incidents of his scope.
24. **Given** the dashboard **Then** C41 shows 12 months stacked by road_type with the K-137 line, from the KPI engine only.
25. **Given** the AI asked "vehicle incidents by road type this year" **Then** it answers from T3 with road_type and returns no driver names or third-party plates (P7a-2).
26. **Given** an export of `incident_vehicles` by a user without 29 **Then** identity and licence columns are not offered (`COLUMN_NOT_PERMITTED` if forced).
27. **Given** the seed **Then** Phase 1 W1–W3, the 6f KPIs and 6g scorecards are unchanged by 7a (vehicle fields are additive).
28. **Given** Arabic UI **Then** every 7a label, list value, warning and error has AR text; plates and report numbers stay left-to-right inside RTL.

## 10. Open questions for the HSE Manager

1. **Najm vs police:** we route public-road accidents without injury to Najm and with injury to the traffic police, both within 1 h. Is that how your sites report (and does the client want a copy)?
2. **Licence numbers:** we do not store KSA licence numbers (they equal the ID number, as in Phase 2). Do you need them for insurance claims?
3. **Commuting in the vehicle rate:** excluded by default, like TRIR. Does your client count company-bus commuting crashes as work-related?
4. **Seat belt and speed:** required "worn / not worn / unknown" for every vehicle; speed optional. Enough?
5. **Third-party cost:** we record an estimate only. Do you want the insurer claim number and final settlement?

## 11. Changes required in earlier specs (to apply when 7a is built)

### 11.1 `1-dashboard.md` v1.10 → v1.11
1. §3.3 incident fields of 7a §3.1; new §3.3a incident vehicle (7a §3.2); §3.11 lists JP and LCV; notification body `najm`.
2. §5: VA-1…VA-9 by reference; I-20 `police` item per VA-12.
3. §6: K-136…K-137 by reference; §8.1 tile and C41; register filters.
4. §5.9: T3 dimensions, T4 filters, T5 vehicle rows (7a §8).
5. No existing rule, formula or worked example changes value.

### 11.2 `6f-incident-followup.md` v1.0 → v1.1
1. List NT adds `rta_public_injury`, `rta_public_no_injury`; body list adds `najm`; statutory rows POL-RTA and NAJM-V (VA-11); form `—` (verbal).

### 11.3 `6g-scorecard-reports.md` v1.0 → v1.1
1. Dataset registry adds `incident_vehicles` (§8). Scorecard metrics unchanged (a vehicle metric is a 7b option, §10 of 7b).

### 11.4 `2-access-permits.md`
No change; 7a reads the vehicle register, ADPs and offences.

## Appendix A — Seed (fictional; `seed_fake = true`; report numbers contain `TEST`)

- ANIA-EXP, September 2026, the four VW1 incidents (refs shown as suffixes; the generator takes the next free numbers and the tests look them up by title): **0201** 2026-09-21 06:40, public_road (Airport Rd, km 12), GULFPAVE pickup VEH-0002 striking a private car (third_party, plate test `ا ب ج 1234`), driver Jomar Santos (WKR-000003, licence valid), seat belt worn, speed 72 / 80 report, Najm NJM-TEST-2026-00871, liability 100 %, MTC to the driver; **0204** 2026-09-10 14:15, site_road, near miss, tipper reversing, RAWABI, licence wrong_class (private on tipper); **0209** 2026-09-17 23:30, airside apron, GULFPAVE GSE tug, property damage 12,000 SAR, airside_vehicle_incident; **0212** 2026-09-27 05:50, public_road, commuting_own, NAJD worker's private car, single vehicle, LTI, commuting = true, traffic_police TP-TEST-2026-3310.
- 6f: POL-RTA requirement for 0201 submitted at 07:20 with reference NJM-TEST-2026-00871 (the seed's `followup_rules_from` 2026-10-01 means September incidents use I-20; one October fixture, **0231** 2026-10-11 public_road no injury, creates a NAJM-V requirement, open at the clock).

## Change log

| Version | Date | Author | Change |
|---|---|---|---|
| v1.0 | 2026-10-10 | HSE Consultant Agent | First issue, planned only (awaiting the HSE Manager's go). |
