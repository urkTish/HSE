# Module Spec — Phase 6e: Environmental Management (aspects and impacts, environmental permits and licences, waste management and chain of custody, dust / noise / water monitoring with exceedances, spill kits and spill response, water use and dewatering, environmental inspections)

**Version:** v1.1 · **Date:** 2026-10-09 · **Author:** HSE Consultant Agent · **Status:** Draft. The HSE Manager asked to proceed without waiting for approval and will review the choices later (§10).
**Builds on:**
- `0-foundation.md` v1.2: projects, sites, zones (zone_type, airside attributes), engagement tree, roles, scoping legend, `week_start`, rules 28, 35 and 48, PDPL P1–P13, the capability matrix (6d ends at 201).
- `1-dashboard.md` v1.7: daily returns (headcount, man-hours), incidents (§3.3 type `environmental`, env_category / env_substance / env_quantity_l / env_contained / env_reached, notifications and I-20), I-14, CAs (§3.8, CA-1…CA-8, `ca_due_days`), K-16, K-26, warnings E1–E21, AI tools T1–T21, charts up to C33, the action panel and the expiring-items endpoint, P1-8, list I (`environmental` inspection type), list O (`environmental`), W1 #37 and seed A.3.
- `2-access-permits.md` v1.6: ops events (§3.17 `dust_sandstorm`, `lvp`; domain events `ops_event.started` / `ended`), capability 67, devices (§3.19), vehicles and AVPs (read only).
- `6b-heat-stress.md` v1.1: instrument, monitoring point and reading pattern (§3.1–§3.3, HS-2, WB-1), "days with work".
- `6c-emergency-drills.md` v1.1: emergency asset register (§3.8, QR kind `EA`), checks (§3.9, list EC), readiness (§6.5), K-107.
- `6d-field-assurance.md` v1.0: checklist templates, inspections, findings → CAs, stop rules (FND-1…FND-9), seeded template ENV v1; numbering ends at capability 201, K-117, E21, T21, C33, W08.
- `docs/DECISIONS.md` #1–#186, in particular #53 (tier-1 trees), #78 (export audit), #124 (no SMS channel).

**Numbering taken by 6e:** capabilities **202–214**; KPIs **K-118…K-126**; warnings **E22–E23**; AI tool **T22**; charts **C34–C36**; CA source_type **`environmental`**; Phase 1 notification body **`ncec`**; Phase 2 device kind **`env_monitor`**; 6c asset type **`spill_kit`**. No new QR kind (spill kits use 6c `EA`) and no new import warning.

**Covers (build order):**
1. 6e.1 Aspects and impacts register; permits and licences register (project and provider) with expiry tracking; service providers.
2. 6e.2 Waste: streams, storage areas, consignments (consignment notes / manifests) with licence checks, receipts, discrepancies, hazardous storage limits; tonnage and diversion.
3. 6e.3 Monitoring: instruments, points, limits, readings (manual, station, lab), background events, exceedances → CAs; airside dust link to Phase 2 ops events.
4. 6e.4 Spills: spill log, Phase 1 incident link, spill-kit use (6c assets).
5. 6e.5 Water use and dewatering discharge.
6. 6e.6 Complaints from neighbours and authorities.
7. 6e.7 Environmental inspections on 6d templates; KPIs, warnings, dashboard and AI.

**Not in 6e:**
- Occupational exposure of workers to dust, silica or noise (personal sampling, audiometry): that is health surveillance (6a). 6e measures the environment at boundaries, receptors and discharge points.
- The checklist engine, stop-work orders and inspection KPIs (6d). Environmental inspections are 6d inspections with environmental templates.
- Spill-kit registration, QR stickers and periodic checks (6c asset register). 6e records their use and owns the spill-kit readiness KPI.
- Declaring operational suspensions or suspending WAPs and permits (Phase 2, capability 67). 6e alerts only.
- Fire safety of fuel and chemical stores (Civil Defense; 6c / 6d FIR). Energy and carbon accounting (not requested; §10 Q8).

Conventions: `VERIFY` = clause or number to confirm against the current official text or the client's procedure. `ASSUMPTION` = Consultant default; the HSE Manager may override it (§10). "Must" = enforced server-side. Rule prefixes: ASP aspects, PRM permits, PRV providers, WST waste, CON consignments, MON monitoring, LIM limits, EXD exceedances, AIR airside, SPL spills, WAT water, CPL complaints, ENI inspections, EK KPIs/AI, P6e- PDPL, BD6e boundary. Error codes are stable strings (Phase 0 rule 48). Times are local Asia/Riyadh unless marked UTC.

**The principle that shapes this module:** an environmental record is evidence for the regulator. Every tonne leaves site under a valid licence and comes back with a ticket, every reading is compared with the strictest applicable limit, and a background dust event is a labelled exception, never a deletion.

---

## 1. Purpose

On a KSA airport or high-rise project the environmental file is what NCEC inspectors, MWAN, the municipality, the airport operator and the client ask for first, and it is usually spread over spreadsheets, paper consignment notes and the dust contractor's emails. The HSE Manager cannot see at a glance which permit expires next month, whether every skip that left site last week reached a licensed facility, what share of waste was recycled, whether the dust monitor at the taxiway boundary exceeded its trigger during paving, or whether last night's concrete pour broke the night noise limit next to the residential tower.

Phase 6e provides:
- an aspects and impacts register with significance scoring, controls and monitoring links (ISO 14001 cl. 6.1.2);
- a register of project permits and approvals (NCEC environmental permit, MWAN producer registration, municipal permits, dewatering discharge, airport operator / client CEMP approval) and of providers' licences (MWAN transport, recycling, treatment, disposal), with expiry alerts;
- waste streams, storage areas and consignments with licence checks at dispatch, weighbridge receipts, discrepancy review, a hazardous storage time limit, tonnage and diversion rate;
- dust (PM10, PM2.5, visual), noise and discharge-water monitoring with calibrated instruments, the strictest applicable limits, automatic exceedances, background-event labelling from Phase 2 ops events, and CAs;
- a spill log linked to Phase 1 environmental incidents and to 6c spill kits;
- water use and dewatering discharge records, a complaints log, and environmental inspections on 6d templates;
- KPIs K-118…K-126, warnings E22–E23, AI tool T22 and charts C34–C36.

## 2. Regulatory basis

| # | Source | What it drives here |
|---|---|---|
| R1 | **Environmental Law** (Royal Decree M/165, 19/11/1441H) and its **Implementing Regulations** (2021): environmental permits for construction and operation by impact category, duty to prevent pollution, keep records, report environmental incidents and emergencies, penalties `VERIFY` regulation titles, articles and incident-reporting time | Permit register, spill → incident → `ncec` notification, record retention |
| R2 | **NCEC** (National Center for Environmental Compliance): permit issue and renewal through its portal, compliance inspections, **ambient air quality standards** (PM10 24-h 340 µg/m³, PM2.5 24-h 35 µg/m³ `VERIFY` current values and allowed exceedances) and **ambient noise limits by land use** `VERIFY`; accredited laboratories and consultants for compliance monitoring `VERIFY` | Limit library list DL, instrument and lab rules |
| R3 | **Waste Management Law** (Royal Decree M/3, 5/1/1443H) and Implementing Regulations; **MWAN** (National Center for Waste Management): producer registration, licences for collection / transport / storage / treatment / recycling / disposal, tracking documents (e-manifest), hazardous waste segregation, labelling and maximum storage time, C&D waste rules `VERIFY` each | Providers, licence checks (CON-2…CON-4), manifest ref, hazardous storage limit (WST-5) |
| R4 | **MOMRAH / Balady and the city municipality** (e.g. Riyadh Municipality; Royal Commission for Riyadh City where applicable): construction permit conditions on dust, hoarding, mud on roads, C&D waste to approved sites, working hours and noise, dewatering discharge to storm drains `VERIFY` | Permit types, noise day / night hours, discharge permit |
| R5 | **MEWA / NWC**: water supply, tanker water, sewer and septic discharge, treated effluent reuse `VERIFY` | Water entries, sewage stream, discharge limits |
| R6 | **ICAO Annex 14 Vol I** (§9.4 wildlife strike hazard reduction: no waste attractants on or near the aerodrome; FOD control), **Doc 9137 Part 3** (wildlife), **GACAR Part 139**, and the airport operator's environmental requirements and Works Safety Plan (dust affecting visibility, fuel-spill reporting airside) `VERIFY` | AIR rules, airside storage, airside spills always reportable |
| R7 | **ISO 14001:2015** cl. 6.1.2 (aspects), 6.1.3 (compliance obligations), 8.1 (operational control, contractors), 8.2 (emergency preparedness: spills), 9.1.1 (monitoring, calibrated equipment), 9.1.2 (evaluation of compliance), 10.2 (nonconformity and CA) | Register structure, calibration, CAs |
| R8 | **International benchmarks** where KSA limits are silent, never to relax them: IFC EHS General Guidelines 1.1 (air), 1.6 (waste), 1.7 (noise: 55 / 45 dB(A) residential, 70 / 70 industrial); IAQM guidance on construction dust monitoring (1-h trigger levels); BS 5228-1 (construction noise); IEC 61672-1 (sound level meters) | Project trigger levels, noise categories, SLM class |
| R9 | **Client standards** flowed down (client or airport CEMP; Saudi Aramco environmental standards where applicable `VERIFY`): diversion targets, monthly environmental report | Settings, K-120 target |
| R10 | **PDPL**: driver names and vehicle plates on manifests; complainants' contact data; photos | P6e rules |

Strictest-wins applied in this spec (and why):
- **The lowest applicable limit is used** for each point and parameter (NCEC standard, permit condition, client CEMP, project trigger). Library values may only be tightened (LIM-2).
- **Every airside spill is reportable** whatever its size (SPL-2): fuel on aircraft pavement is a slip, fire and FOD hazard for the operator, not only an environmental one.
- **No licence, no dispatch** (CON-2): a waste load cannot be dispatched with an expired or out-of-scope transporter or facility licence, or without a valid producer registration. There is no override.
- **Hazardous waste storage limit 90 days ASSUMPTION** (WST-5); MWAN conditions on the registration may be shorter `VERIFY`; the setting only lowers.
- **A background label never removes a reading** (EXD-4): it only stops the exceedance counting as project-caused.

## 3. Entities & fields

PDPL column: **none / personal / sensitive** (Phase 0 P1–P2). Every entity carries the Phase 0 system fields, is audited (Phase 0 rule 35) and stores `seed_fake`. AR labels are shown in the UI.

### 3.1 Aspect register entry — الجوانب والتأثيرات البيئية

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| aspect_no | الرقم | string | sys | `ASP-<project>-<nnn>` | ASP-ANIA-EXP-004 | none |
| activity | النشاط | enum | Y | Phase 1 list A (activity) | paving_asphalt | none |
| aspect / impact | الجانب / التأثير | enum / enum | Y | list AS / list IM | dust_emission / aviation_safety | none |
| condition | الحالة التشغيلية | enum | Y | `normal` عادية · `abnormal` غير عادية · `emergency` طارئة | normal | none |
| site_ids / engagement_ids | المواقع / المقاولون | FK[] / FK[] | Y / N | sites of the project | [S-AIR] / [GULFPAVE] | none |
| severity / likelihood | الشدة / الاحتمالية | int / int | Y | 1–5 each | 4 / 3 | none |
| legal_requirement / permit_ids | متطلب قانوني / التصاريح | bool / FK[] | Y / N | — | true / [EPL-…-001] | none |
| stakeholder_concern | اهتمام الأطراف المعنية | bool | Y | e.g. airport operator, neighbours | true | none |
| score / significant | الدرجة / جوهري | int / bool | sys | §6.1 | 12 / true | none |
| controls | الضوابط | list {text_en/ar, control_level (Phase 1 list)} | cond. | ≥ 1 when significant (ASP-2) | water bowser on haul roads / engineering | none |
| monitoring_links | روابط الرصد | list {point_id + parameter} or {template_code} | cond. | ≥ 1 when significant | [D-SAIR-01 pm10, DSN] | none |
| review_due_on / review_flag | موعد المراجعة / مراجعة مطلوبة | date / bool | sys | activation + `aspect_review_months` − 1 day; flag ASP-3 | 2027-04-30 / false | none |
| status | الحالة | enum | Y | `draft` · `active` · `archived` | active | none |

### 3.2 Environmental service provider (org-wide) — مقدم خدمة بيئية

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| provider_code | الرمز | string(12) | Y | `^[A-Z0-9-]{2,12}$`, unique | HAZMOVE | none |
| name_en / name_ar | الاسم | string(150) ×2 | Y | — | Gulf Hazardous Logistics (test) / الخليج للنقل الخطر | none |
| cr_number | السجل التجاري | string(10) | Y | `^\d{10}$` | 1010000207 | none |
| kinds | النوع | enum[] | Y | ≥ 1 of list PK | [transporter] | none |
| facilities | المنشآت | list {facility_code, name_en/ar, city, kind (list PK site kinds)} | cond. | required for recycler, treatment_facility, landfill | [OILREF-1 Riyadh re-refinery] | none |
| contact_email / phone | التواصل | string | N | organisation contact, not a person | ops@example.com | none |
| status | الحالة | enum | Y | `approved` معتمد · `suspended` موقوف · `blacklisted` محظور (213) | approved | none |

### 3.3 Permit / licence — التصاريح والتراخيص البيئية

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| record_no | الرقم | string | sys | `EPL-<project or provider>-<nnn>` | EPL-ANIA-EXP-002 | none |
| holder | صاحب التصريح | {project_id} or {provider_id} | Y | exactly one | ANIA-EXP | none |
| permit_type | النوع | enum | Y | list PT (project or provider types) | mwan_producer_registration | none |
| issuer | الجهة المصدرة | enum | Y | list IS | mwan | none |
| requirement_code | رمز المتطلب | string(20) | cond. | project holder: groups renewals of one obligation (PRM-2) | MWAN-REG | none |
| required | مطلوب | bool | Y | project holder: counts in K-118 | true | none |
| applies_from / applies_to | فترة الانطباق | date / date | N | e.g. dewatering period; null = project life | — | none |
| reference_no | رقم التصريح | string(40) | cond. | required unless status pending | MWAN-PRD-TEST-0420 | none |
| scope | النطاق | {activities: list LA[], waste_classes: list WC[], site_ids, facility_code} | cond. | providers: activities and classes required | {[collection_transport], [hazardous, liquid]} | none |
| valid_from / valid_to | تاريخ السريان / الانتهاء | date / date | cond. | valid_to null only for types marked "no expiry" in list PT | 2025-11-01 / 2026-10-31 | none |
| conditions | الاشتراطات | list {code, text_en/ar, link: point+parameter / template_code / none} | N | permit conditions shown on linked points (LIM-2) | [C3 PM10 boundary monitoring weekly] | none |
| document | المستند | file (PDF/image ≤ 20 MB) | cond. | required unless pending | — | none |
| supersedes_id | يحل محل | FK | N | same holder and requirement_code | EPL-…-001 | none |
| status | الحالة | enum | sys | §4.2 | expiring | none |

### 3.4 Waste stream (project) — مسار النفايات

stream_code (list WS code, one per project); class (sys from list WS: `inert` · `non_hazardous` · `hazardous` · `liquid_sewage`); default_route (list TR, editable); density (t/m³, or kg/L for liquids; list WS default, editable 0.01–3.00); wildlife_attractant (sys from WS); excluded_from_tonnage (sys: true for `liquid_sewage`, counted in m³); active (bool). PDPL: none.

### 3.5 Waste storage area — منطقة تخزين النفايات

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| area_code | الرمز | string(16) | Y | unique per project | HWS-SLAND-01 | none |
| site_id / zone_id | الموقع / المنطقة | FK / FK | Y / N | — | S-LAND / Z-LAY1 | none |
| type | النوع | enum | Y | list SA | hazardous_store | none |
| accepted_streams | المسارات المقبولة | stream codes[] | Y | hazardous streams only in hazardous_store / liquid_store (`STREAM_NOT_ACCEPTED`) | [used_oil, oily_absorbents, chemical_containers] | none |
| capacity_m3 | السعة | decimal(7,1) | Y | > 0 | 24.0 | none |
| secondary_containment_pct | الاحتواء الثانوي | int | cond. | hazardous_store / liquid_store: ≥ `containment_min_pct` (`CONTAINMENT_INSUFFICIENT`) | 110 | none |
| covered / lidded_secured / signage_bilingual | مغطاة / محكمة الإغلاق / لافتات ثنائية اللغة | bool ×3 | Y | AIR-2 | true / true / true | none |
| accumulation | بدء التجميع | list {stream_code, started_on} | cond. | hazardous streams: WST-5 | [{chemical_containers, 2026-07-20}] | none |
| status | الحالة | enum | Y | `active` · `closed` | active | none |

### 3.6 Waste consignment (consignment note / manifest) — إشعار نقل النفايات

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| consignment_no | الرقم | string | sys | `WCN-<project>-<yyyy>-<nnnnn>` | WCN-ANIA-EXP-2026-00412 | none |
| stream_code / storage_area_id | المسار / منطقة التخزين | string / FK | Y / N | area must accept the stream | used_oil / HWS-SLAND-01 | none |
| generator_engagement_id | المقاول المولد | FK | Y | engagement on the project; C scope for reps | RAWABI@ANIA-EXP | none |
| quantity / unit | الكمية / الوحدة | decimal(9,3) / enum | Y | > 0; `t` · `m3` · `L` | 1,000 / L | none |
| estimated_t | الوزن التقديري | decimal(9,3) | sys | §6.3 | 0.900 | none |
| route | طريقة المعالجة | enum | Y | list TR; default from stream | recovery | none |
| transporter_id / transporter_licence_id | الناقل / ترخيصه | FK / FK | Y / sys | CON-2 | HAZMOVE / EPL-HAZMOVE-001 | none |
| facility (provider_id + facility_code) / facility_licence_id | المنشأة / ترخيصها | FK / FK | Y / sys | CON-2 | OILREF / OILREF-1 | none |
| vehicle_plate | لوحة المركبة | string(12) | Y | 3–12 chars | 4521 RBA (test) | personal |
| driver_name / driver_mobile | السائق | string(120) / string(15) | N | — | — | personal |
| mwan_manifest_ref | رقم بيان النقل (موان) | string(40) | cond. | CON-5 | MWAN-MF-TEST-77120 | none |
| dispatched_at / dispatched_by | وقت الإرسال / أرسله | timestamptz / FK | Y / sys | ≤ now + 5 min; ≥ now − 72 h | 2026-09-22 08:30 / Fahad | personal |
| due_on | موعد إثبات الاستلام | date | sys | local date(dispatched_at) + `manifest_return_days` | 2026-09-29 | none |
| received_at / received_net_t / ticket_ref / ticket_file | الاستلام / الوزن الصافي / رقم التذكرة / صورة التذكرة | timestamptz / decimal(9,3) / string(40) / file | cond. | required to record receipt | 2026-09-22 14:10 / 0.820 / WB-TEST-55120 | none |
| receipt_recorded_at | تاريخ تسجيل الاستلام | timestamptz | sys | K-121 on-time test | 2026-09-30 11:00 | none |
| discrepancy_pct / discrepancy_reason | فرق الوزن / السبب | decimal / text(500) | sys / cond. | §6.3; reason required when > `weight_discrepancy_pct` | 8.9 / — | none |
| rejection_reason | سبب الرفض | text(500) | cond. | status rejected | — | none |
| status | الحالة | enum | Y | §4.3 | closed | none |

### 3.7 Environmental instrument — جهاز رصد بيئي

As 6b §3.1: instrument_no `EMI-<project>-nn`; kind (list IK); make_model / serial_no (serial unique per project); standard_class (sound level meters: IEC 61672-1 class `1` or `2`; others null); calibration_valid_until / calibration_cert_ref (> today at activation); device_id (station kinds: a registered `env_monitor` device, §11.3); status `active` · `quarantined` (job at calibration expiry, or manual) · `retired`. PDPL: none.

### 3.8 Monitoring point — نقطة الرصد البيئي

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| point_code | الرمز | string(16) | Y | unique per project | D-SAIR-01 | none |
| site_id / zone_id | الموقع / المنطقة | FK / FK | Y / N | — | S-AIR / Z-TWB | none |
| kind | نوع النقطة | enum | Y | list MPK | airside | none |
| noise_area_category | فئة المنطقة الصوتية | enum | cond. | points with laeq: list NA | industrial | none |
| source_kind / instrument_id | طريقة القياس / الجهاز | enum / FK | Y / cond. | `manual` · `station` (active station instrument) · `visual` | station / EMI-ANIA-EXP-01 | none |
| permit_id | التصريح المرتبط | FK | cond. | `discharge` points: the discharge permit (WAT-3) | — | none |
| requirements | متطلبات الرصد | list §3.9 | Y | ≥ 1 | — | none |
| active | فعّالة | bool | Y | — | true | none |

### 3.9 Monitoring requirement (point × parameter) — متطلب الرصد

parameter (list PA); averaging (list AV); schedule (`continuous` مستمر · `daily` يومي · `weekly` أسبوعي · `monthly` شهري · `campaign` حسب الحاجة); period (`any` · `day` · `night`, noise only); alert_value / limit_value (or limit_min / limit_max for pH); limit_source (`ncec` · `municipality` · `permit_condition` · `client` · `project_trigger`); library_ref (list DL row it was prefilled from). PDPL: none.

### 3.10 Reading — قراءة الرصد

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| reading_no | الرقم | string | sys | `ENR-<project>-<yyyymmdd>-<nnnnn>` | ENR-ANIA-EXP-20260916-00412 | none |
| point_id / parameter / averaging | النقطة / المؤشر / فترة المتوسط | FK / enum / enum | Y | a requirement of the point, or `15min` raw for station kinds | D-SAIR-01 / pm10 / 1h | none |
| window_start / window_end | بداية / نهاية الفترة | timestamptz ×2 | Y | end > start; end ≤ now + 2 min; manual ≥ now − 72 h (`BACKDATED_READING`), lab and station any past time | 2026-09-16 10:00 / 11:00 | none |
| source | المصدر | enum | sys | `manual` · `station` · `derived` · `lab` · `import` | derived | none |
| value | القيمة | decimal(8,2) | Y | per list PA range (`VALUE_OUT_OF_RANGE`) | 640.00 | none |
| instrument_id | الجهاز | FK | cond. | not visual / lab: active, calibration_valid_until ≥ local date(window_end) (`INSTRUMENT_CALIBRATION_EXPIRED`) | EMI-ANIA-EXP-01 | none |
| lab_provider_id / lab_report_ref | المختبر / رقم التقرير | FK / string(40) | cond. | source lab: provider of kind environmental_lab with a valid licence on the sample date | ENVLAB / LAB-TEST-0924 | none |
| field_calibration_checked | فحص المعايرة الميدانية | bool | cond. | manual laeq: must be true (`FIELD_CALIBRATION_REQUIRED`) | true | none |
| background / background_ref | خلفية طبيعية / المرجع | bool / string | sys | EXD-3 | false | none |
| result | النتيجة | enum | sys | `ok` · `alert` · `exceedance` · `no_limit` (§6.2) | exceedance | none |
| late_entry | إدخال متأخر | bool | sys | created_at − window_end > 15 min (manual), > 2 h (station) | false | none |
| recorded_by / photos | سجّلها / الصور | FK / file[] ≤ 3 | sys / N | visual checks: photo hint "photograph the dust, not people" | Omar | personal |
| status / void_reason | الحالة | enum / text | Y / cond. | `valid` · `voided` (214, ≥ 20 chars) | valid | none |

### 3.11 Background dust declaration — إعلان غبار طبيعي

declaration_no `BGD-<project>-<yyyy>-<nnn>`; site_ids; from / to (timestamptz; to − from ≤ 72 h); source (`ncm_warning` إنذار المركز الوطني للأرصاد · `aocc` · `visual_regional` · `other`); source_ref string(40); declared_by (208). PDPL: none (declarer personal).

### 3.12 Exceedance — تجاوز الحد

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| exceedance_no | الرقم | string | sys | `ENX-<project>-<yyyy>-<nnnn>` | ENX-ANIA-EXP-2026-0017 | none |
| point_id / parameter / averaging | النقطة / المؤشر / المتوسط | FK / enum / enum | sys | from the first reading | D-SAIR-01 / pm10 / 1h | none |
| reading_ids | القراءات | FK[] | sys | EXD-2 episode | 1 reading | none |
| peak_value / limit_value / margin_pct | القيمة القصوى / الحد / نسبة التجاوز | decimal ×3 | sys | margin = (peak − limit) ÷ limit × 100 (pH: distance outside the range) | 640 / 500 / 28.0 | none |
| started_at / ended_at | البداية / النهاية | timestamptz ×2 | sys | episode window | — | none |
| suggested_cause | السبب المقترح | enum | sys | `background_natural` when EXD-3 applies, else null | — | none |
| cause | السبب | enum | cond. | list EC; required to review | project_activity | none |
| responsible_engagement_id / activity_en/_ar | المقاول المسؤول / النشاط | FK / string(300) | cond. | cause project_activity (`ENGAGEMENT_REQUIRED`) | GULFPAVE / Asphalt milling Twy B | none |
| immediate_action_en/_ar | الإجراء الفوري | text(1000) | cond. | required to review | Milling paused, bowser added | none |
| ca_id | الإجراء التصحيحي | FK | sys | EXD-5 | CA-ANIA-EXP-2026-00902 | none |
| reviewed_by / reviewed_at | راجعه | FK / timestamptz | sys | 210 | Noura / 09-16 13:05 | personal |
| status | الحالة | enum | Y | §4.5 | closed | none |

### 3.13 Spill — انسكاب

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| spill_no / client_uuid | الرقم / معرّف الجهاز | string / UUID | sys / Y | `SPL-<project>-<yyyy>-<nnnn>`; client_uuid unique per project | SPL-ANIA-EXP-2026-0031 | none |
| occurred_at | وقت الحدوث | timestamptz | Y | ≤ now; ≥ now − 72 h | 2026-09-25 03:20 | none |
| site_id / zone_id | الموقع / المنطقة | FK / FK | Y / N | — | S-AIR / Z-APR-21 | none |
| responsible_engagement_id | المقاول المسؤول | FK | Y | — | GULFPAVE@ANIA-EXP | none |
| substance / source | المادة / المصدر | enum / enum | Y | list SS / `plant_leak` · `refuelling` · `container_failure` · `tanker` · `other` | diesel / refuelling | none |
| quantity_l | الكمية (لتر) | decimal(8,1) | Y | 0.1–100,000; estimate | 40.0 | none |
| surface | السطح | enum | Y | `paved` · `unpaved_soil` · `drain` · `water_body` | paved | none |
| contained / reached | تم الاحتواء / وصل إلى | bool / enum | Y | reached as Phase 1 env_reached | true / none | none |
| spill_kit_asset_ids | حقائب الانسكاب المستخدمة | FK[] | N | 6c assets of type spill_kit (scan `EA` or pick) | [SK-SAIR-02] | none |
| reportable | واجب الإبلاغ | bool | sys | SPL-2 | true | none |
| incident_id | الحادثة | FK | cond. | SPL-3 | INC-ANIA-EXP-2026-0158 | none |
| incident_fields | بيانات الحادثة | {actual_severity, potential_severity, activity, shift, description, immediate_actions} | cond. | reportable and no existing incident linked (`INCIDENT_FIELDS_REQUIRED`) | {2, 3, driving_transport, night, …} | none |
| cleanup_completed_at / cleanup_waste | انتهاء التنظيف / نفايات التنظيف | timestamptz / {consignment_ids or storage_area_id} | cond. | required to close (SPL-6) | 09-25 05:00 / HWS-SLAND-01 | none |
| photos | الصور | file[] ≤ 5 | N | hint "photograph the spill, not people" | — | personal (possible) |
| status | الحالة | enum | Y | §4.6 | closed | none |

### 3.14 Water entries — سجلات المياه

- **Monthly water use** (per site, month, source): site_id; month (`YYYY-MM`); source (`network` شبكة · `tanker` صهريج · `groundwater_dewatering_reuse` · `treated_effluent` مياه معالجة); volume_m3 (decimal(10,1) ≥ 0); purpose split (optional: dust_suppression, concrete_curing, welfare, other, summing to volume); evidence (meter photo or tanker invoices, N). Unique per (site, month, source) (`DUPLICATE_WATER_ENTRY`). PDPL: none.
- **Dewatering discharge day**: point (kind `discharge`); date; volume_m3; readings for pH / TSS / oil_grease are §3.10 readings on that point. PDPL: none.

### 3.15 Complaint — شكوى بيئية

complaint_no `ECP-<project>-<yyyy>-<nnn>`; received_at; channel (`phone` · `email` · `in_person` · `via_client` · `via_authority`); category (`dust` · `noise` · `odour` · `waste` · `water` · `mud_on_road` · `light` · `other`); site_id; location_text (string 200); anonymous (bool); complainant_name / complainant_contact (string 120 / string 60; only when not anonymous; **personal**, P6e-2); description (text 2000, P1-8 scan); linked reading / exceedance ids; investigation_en/_ar (text 2000); response_due_on (sys: CPL-1); response_sent_at / response_summary; ca_id; status `open` · `responded` · `closed` · `voided`.

### 3.16 Phase 6e project settings

Only the HSE Manager edits them (capability 213); every change is audited; "Allowed" is the only range accepted; a loosening value gets 422 `SETTING_LOOSENING`.

| Key | AR label | Type | Default | Allowed |
|---|---|---|---|---|
| permit_alert_days | تنبيهات انتهاء التصاريح | int[] | [90, 60, 30, 14, 7, 0] ASSUMPTION | values 0–180; may add days, never remove |
| provider_licence_alert_days | تنبيهات تراخيص المقدمين | int[] | [30, 14, 7, 0] | same |
| manifest_return_days | مهلة إثبات الاستلام | int | 7 ASSUMPTION | 1–14; only lower |
| weight_discrepancy_pct | حد فرق الوزن | decimal | 10.0 ASSUMPTION | 2.0–20.0; only lower |
| mwan_manifest_required_for | إلزام بيان موان | enum[] | [hazardous] ASSUMPTION `VERIFY` R3 | ⊆ {hazardous, non_hazardous, inert, liquid_sewage}; may add |
| haz_storage_max_days | أقصى مدة لتخزين النفايات الخطرة | int | 90 ASSUMPTION `VERIFY` R3 | 30–90; only lower |
| containment_min_pct | الحد الأدنى للاحتواء الثانوي | int | 110 ASSUMPTION | 110–150; only raise |
| spill_reportable_l | حد الانسكاب واجب الإبلاغ | decimal | 20.0 ASSUMPTION | 1.0–200.0; only lower |
| airside_spill_always_reportable | كل انسكاب في الجانب الجوي واجب الإبلاغ | bool | true | true only |
| data_capture_pct | نسبة اكتمال البيانات | decimal | 75.0 ASSUMPTION | 50.0–100.0; only raise |
| noise_day_start / noise_night_start | بداية النهار / الليل | time | 07:00 / 22:00 `VERIFY` R2/R4 | night may start earlier, day later |
| background_ops_event_types | أنواع الأحداث المعتبرة غباراً طبيعياً | enum[] | [dust_sandstorm, lvp] ASSUMPTION | ⊆ Phase 2 types; may remove only |
| post_storm_check_hours | مهلة الفحص بعد العاصفة | int | 4 ASSUMPTION | 1–12; only lower |
| exceedance_review_days | مهلة مراجعة التجاوز | int | 3 | 1–7; only lower |
| complaint_response_days / authority_complaint_response_days | مهلة الرد على الشكوى | int / int | 7 / 3 ASSUMPTION | 1–14 / 1–7; only lower |
| aspect_review_months | دورية مراجعة الجوانب | int | 12 | 6–12; only lower |
| diversion_target_pct | هدف تحويل النفايات | decimal | 70.0 ASSUMPTION | 0.0–100.0; only raise |
| monitoring_warning_pct / custody_warning_pct | حدود الإنذار | decimal ×2 | 95.0 / 95.0 ASSUMPTION | 50.0–100.0 |
| exceedance_warning_count | عدد التجاوزات للإنذار | int | 2 ASSUMPTION | 1–10; only lower |
| env_notifications_from | بدء قواعد الإخطار البيئي | date / null | null | §11.2; once set only moves earlier |
| photo_retention_months / complainant_retention_months | الاحتفاظ بالصور / ببيانات الشاكي | int / int | 24 / 12 | 12–60 / 6–24 |

### 3.17 Reference lists (seeded EN/AR; codes immutable)

**AS — aspects:** `dust_emission` انبعاث الغبار · `exhaust_emission` عوادم · `noise_vibration` ضوضاء واهتزاز · `waste_generation` توليد النفايات · `hazardous_material_storage` تخزين المواد الخطرة · `fuel_spill_risk` خطر انسكاب الوقود · `wastewater_discharge` تصريف المياه · `water_consumption` استهلاك المياه · `land_disturbance` تعرية التربة · `wildlife_attraction` جذب الحياة البرية · `fod_generation` توليد الأجسام الغريبة · `light_spill` التلوث الضوئي · `odour` الروائح.
**IM — impacts:** `air_quality` · `community_nuisance` · `soil_contamination` · `groundwater_contamination` · `resource_depletion` · `aviation_safety` (dust visibility, FOD, wildlife strikes) · `ecology` · `climate`.
**PT — permit types** (holder · issuer · expiry): `ncec_env_permit_construction` تصريح بيئي للإنشاء (project · ncec · yes) · `ncec_env_permit_operation` تصريح بيئي للتشغيل, e.g. on-site batching plant or crusher (project · ncec · yes) · `eia_approval` موافقة دراسة الأثر البيئي (project · ncec · no) · `mwan_producer_registration` تسجيل منتج النفايات (project · mwan · yes) · `municipal_construction_permit` رخصة البناء البلدية (project · momrah_municipality · yes) · `dewatering_discharge_permit` تصريح تصريف مياه نزح (project · momrah_municipality or nwc `VERIFY` · yes) · `sewer_discharge_permit` (project · nwc · yes) · `cemp_approval` اعتماد خطة الإدارة البيئية (project · airport_operator or client · no; review date) · `mwan_licence` ترخيص موان (provider · mwan · yes) · `facility_authorisation` (provider · momrah_municipality / nwc / mewa, for municipal landfills and sewage plants · yes) · `lab_accreditation` اعتماد مختبر (provider · ncec or saac `VERIFY` · yes) · `other` (either · other · optional).
**IS — issuers:** `ncec` المركز الوطني للرقابة على الالتزام البيئي · `mwan` المركز الوطني لإدارة النفايات · `momrah_municipality` البلدية · `nwc` شركة المياه الوطنية · `mewa` وزارة البيئة والمياه والزراعة · `airport_operator` مشغل المطار · `gaca` الهيئة العامة للطيران المدني · `client` العميل · `saac` المركز السعودي للاعتماد · `other`.
**PK — provider kinds:** `transporter` ناقل · `recycler` منشأة تدوير · `treatment_facility` منشأة معالجة · `landfill` مردم · `sewage_tanker` صهريج صرف صحي · `environmental_lab` مختبر بيئي.
**LA — licence activities:** `collection_transport` · `storage` · `sorting` · `treatment` · `recycling` · `disposal`. **WC — waste classes:** `inert` · `non_hazardous` · `hazardous` · `liquid_sewage`.
**TR — routes** (diverted ✔): `reuse` إعادة استخدام ✔ · `recycle` تدوير ✔ · `recovery` استرداد (incl. oil re-refining, energy recovery) ✔ · `treatment` معالجة · `disposal_landfill` طمر. Facility activity needed: reuse / recycle → recycling; recovery → recycling or treatment; treatment → treatment; disposal_landfill → disposal.
**WS — waste streams** (class · default route · density): `inert_cd` مخلفات بناء وهدم خاملة (inert · recycle · 1.50 t/m³) · `asphalt_planings` كشط أسفلت (inert · recycle · 1.40) · `surplus_excavated_soil` فائض تربة (inert · disposal_landfill · 1.60) · `metal_scrap` خردة معدنية (non_hazardous · recycle · 0.50) · `wood` أخشاب (non_hazardous · recycle · 0.25) · `packaging` تغليف ورق وبلاستيك (non_hazardous · recycle · 0.10) · `general_mixed` نفايات عامة مختلطة (non_hazardous · disposal_landfill · 0.30) · `food_domestic` نفايات طعام ومنزلية (non_hazardous · disposal_landfill · 0.35; wildlife_attractant) · `used_oil` زيوت مستعملة (hazardous · recovery · 0.90 kg/L) · `oily_absorbents` مواد ماصة ملوثة (hazardous · treatment · 0.40) · `chemical_containers` عبوات كيميائية فارغة (hazardous · treatment · 0.10) · `paint_solvent` دهانات ومذيبات (hazardous · treatment · 1.00 kg/L) · `batteries` بطاريات (hazardous · recycle · 1.20) · `e_waste` نفايات إلكترونية (hazardous · recycle · 0.20) · `contaminated_soil` تربة ملوثة (hazardous · treatment · 1.60) · `clinical_first_aid` نفايات طبية من العيادة (hazardous · treatment · 0.10; MOH rules `VERIFY`) · `sewage` صرف صحي (liquid_sewage · treatment · m³ only). Densities ASSUMPTION; used only when no weighbridge ticket exists.
**SA — storage area types:** `skip` حاوية مفتوحة · `segregated_bay` حجيرات فرز · `hazardous_store` مخزن نفايات خطرة · `liquid_store` مخزن سوائل بحوض احتواء · `compactor` كابسة · `sealed_bin_station` محطة حاويات محكمة.
**IK — instrument kinds:** `pm_station` محطة جسيمات · `pm_portable` جهاز جسيمات محمول · `pm_sampler_24h` جهاز سحب عينات 24 ساعة · `sound_level_meter` مقياس مستوى الصوت · `noise_station` محطة ضوضاء · `water_quality_meter` جهاز جودة المياه.
**MPK — point kinds:** `boundary` حدود الموقع · `sensitive_receptor` مستقبِل حساس (homes, school, hospital) · `airside` الجانب الجوي · `background_upwind` نقطة خلفية · `discharge` نقطة تصريف · `work_area` منطقة العمل (visual).
**PA — parameters** (unit · range): `pm10` (µg/m³ · 0–20,000) · `pm2_5` (µg/m³ · 0–10,000) · `visual_dust` (score 0 none, 1 slight within site, 2 visible at the boundary, 3 crossing the boundary or reducing visibility on airside · 0–3) · `laeq` (dB(A) · 20–140) · `ph` (· 0–14) · `tss` (mg/L · 0–100,000) · `oil_grease` (mg/L · 0–10,000) · `turbidity` (NTU · 0–10,000). **AV — averaging:** `15min` (raw station data, never compared) · `1h` · `24h` · `spot` (visual, grab sample) · `measurement` (manual ≥ 15 min, compared with the 1-h limit, ASSUMPTION).
**DL — default limit library** (parameter · averaging · alert / limit · source): pm10 · 24h · 250 / **340** · ncec `VERIFY` R2 · pm10 · 1h · 300 / **500** · project_trigger ASSUMPTION (R8; no NCEC 1-h PM10 value `VERIFY`) · pm2_5 · 24h · 25 / **35** · ncec `VERIFY` · visual_dust · spot · 2 / **2** (score 3 = exceedance) · laeq · 1h / measurement by list NA, alert = limit − 3 dB · ph · spot · range **6.0–9.0** · tss · spot · — / **50** mg/L · oil_grease · spot · — / **10** mg/L (discharge values ASSUMPTION; the discharge permit's conditions replace them when lower, LIM-2).
**NA — noise area categories** (day / night LAeq limit, dB(A); `VERIFY` R2 Saudi noise standard, IFC benchmark R8): `residential` 55 / 45 · `mixed_commercial` 65 / 55 · `industrial` 70 / 70 · `sensitive` (hospital, school) 50 / 40.
**SS — spill substances:** `diesel` · `petrol` · `hydraulic_oil` · `engine_oil` · `bitumen_emulsion` · `paint` · `solvent` · `concrete_washout` · `sewage` · `chemical_other` · `other`.
**EC — exceedance causes:** `project_activity` نشاط المشروع · `background_natural` غبار طبيعي/خلفية · `third_party` طرف ثالث · `instrument_fault` عطل الجهاز · `unknown` غير معروف.

**Seeded 6d templates** (org-wide, Published 2026-10-01 by Faisal; inspection_type `environmental`; ★ critical, ⛔ stop rule):

| Code | Items | Critical items | Notes |
|---|---|---|---|
| ENV v2 | 16 (2 airside_only) | ENV-02 ★ no uncontained fuel or chemical (drip trays, bunds) · ENV-05 ★ spill kit at refuelling and storage points · ENV-09 ★ no wastewater or concrete washout to ground or drains | supersedes 6d ENV v1 (change note: aligned to 6e); ENV-15/16 airside_only: containers lidded and secured, no waste attractants |
| WSA | 12 (1 airside_only) | WSA-03 ★ hazardous waste in a bunded, labelled, segregated store · WSA-05 ★ containers not overfilled, lids closed · WSA-07 ★ (airside_only) every container lidded and tied down | WSA-10 consignment notes available for the last dispatch |
| DSN | 12 (2 airside_only) | DSN-02 ★⛔ no visible dust leaving the boundary, onto a public road or onto live airside pavement · DSN-04 ★ dust suppression on haul roads operating | DSN-06 stockpiles covered or damped · DSN-08 site speed on unpaved roads ≤ 20 km/h · DSN-10 noisy work inside the permitted hours · DSN-11/12 airside_only |

## 4. Workflow / states

"Who" = capability numbers (§5.17). Jobs: `env_minute` (every 60 s: station aggregates, exceedances, airside alerts, spill-kit status), `env_daily` 00:11:00 (permit and licence status, consignment due, hazardous storage, monitoring slots, post-storm tasks, aspect reviews, retention; after `field_daily`), `env_alerts` 07:08.

### 4.1 Aspect
Draft (203) → Active (203; ASP-2) → Archived (203, reason ≥ 20 chars). Review: an Active entry stays Active; review (203) resets review_due_on and clears review_flag.

### 4.2 Permit / licence status (derived daily, plus manual states)
`pending` قيد الإصدار (applied, no reference yet) · `valid` ساري · `expiring` قارب على الانتهاء (valid_to − today ≤ 30 days) · `expired` منتهي (today > valid_to) · `suspended` موقوف (204, reason; e.g. NCEC suspension) · `superseded` (a renewal of the same requirement_code is valid) · `cancelled` (204, reason). A valid record is **in force** on date d ⇔ valid_from ≤ d ≤ valid_to (or valid_to null) and not suspended or cancelled on d.

### 4.3 Consignment
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Dispatched | مُرسلة | 206 | CON-1…CON-5 at submission |
| Dispatched → Received | مُستلمة | 206 / 207 | ticket fields recorded (CON-6) |
| Received → Closed | مغلقة | 207 | discrepancy reason when needed (CON-7) |
| Dispatched → Rejected | مرفوضة من المنشأة | 207 | facility refused the load; reason; CON-8 |
| any except Closed → Voided | ملغاة | 214 | reason ≥ 20 chars; leaves KPIs |
A Closed consignment is immutable (`CONSIGNMENT_CLOSED`, 409).

### 4.4 Instrument
As 6b §4.1: — → Active (208, calibration valid) · Active → Quarantined (job at calibration expiry, or 208 with reason) · Quarantined → Active (208, new calibration) · any → Retired.

### 4.5 Exceedance
Open (System, EXD-1) → Reviewed (210; cause, immediate action; CA created when EXD-5) → Closed (System when its CA is Closed, or at review when no CA is needed) · Open / Reviewed → Voided (214; e.g. readings voided as instrument fault).

### 4.6 Spill
Reported (211, on submission) → Cleaned up (211; cleanup_completed_at) → Closed (210; SPL-6) · any → Voided (214, reason ≥ 20 chars; a linked incident is not voided automatically).

### 4.7 Complaint
Open (212) → Responded (212; response_sent_at and summary) → Closed (212) · Open → Voided (214).

## 5. Business rules

### 5.1 Aspects (ASP)
- ASP-1. score = severity × likelihood; **significant** ⇔ score ≥ 12, or legal_requirement, or stakeholder_concern ASSUMPTION.
- ASP-2. A significant entry needs ≥ 1 control and ≥ 1 monitoring link to be activated (`ASPECT_CONTROL_REQUIRED`). Controls follow the Phase 1 hierarchy; PPE alone is refused as the only control of a significant aspect (`CONTROL_LEVEL_TOO_LOW`).
- ASP-3. **Review triggers:** review_flag is set on every Active entry of the site whose aspect matches when (a) a project_activity exceedance is reviewed (pm10 / pm2_5 / visual_dust → dust_emission; laeq → noise_vibration; ph / tss / oil_grease → wastewater_discharge), or (b) a reportable spill occurs (fuel_spill_risk, hazardous_material_storage); the HSE Officers get one alert per entry. Annual review alerts at 30 / 0 days before review_due_on.

### 5.2 Permits and licences (PRM)
- PRM-1. Project permits and provider licences are managed by 204. A project record with `required` true is a compliance obligation; renewals are new records with the same requirement_code and supersedes_id.
- PRM-2. **Requirement in force on d** ⇔ some record of the project with that requirement_code is in force on d (§4.2). A requirement with applies_from / applies_to is evaluated only inside that window.
- PRM-3. Alerts at each of `permit_alert_days` before valid_to (project) and `provider_licence_alert_days` (providers used by the project in the last 90 days), to the HSE Officers and the HSE Manager; they stop once a renewal record of the same requirement exists that is (or will be) in force on the day after valid_to. Expiry with no renewal alerts on the day after valid_to and lists the requirement on the action panel.
- PRM-4. **Producer registration:** while the project has a required `mwan_producer_registration` requirement that is not in force today, no consignment can be dispatched (`PRODUCER_REGISTRATION_INVALID`).
- PRM-5. Permit conditions linked to a point and parameter appear on the point; a condition limit lower than the requirement's limit replaces it (LIM-2).

### 5.3 Providers (PRV)
- PRV-1. Providers are org-wide; created by 204, approved, suspended or blacklisted by 213 (reason ≥ 20 chars). A suspended or blacklisted provider cannot be named on a new consignment or lab reading (`PROVIDER_NOT_APPROVED`).
- PRV-2. A provider is usable for a consignment only with a licence (§4.2 in force on the dispatch date) covering the activity and waste class needed (CON-2).

### 5.4 Waste streams and storage (WST)
- WST-1. Streams are activated per project by 205 from list WS; density and default route are editable (audited).
- WST-2. Storage areas are managed by 205. Hazardous streams only in `hazardous_store` or `liquid_store` (`STREAM_NOT_ACCEPTED`); those types need secondary_containment_pct ≥ `containment_min_pct` (`CONTAINMENT_INSUFFICIENT`).
- WST-3. Waste storage areas in airside zones: AIR-2.
- WST-4. The storage area page lists the last 6d WSA / ENV inspection answers in its zone (non-compliant first) and the last consignments from it.
- WST-5. **Hazardous storage time:** for each hazardous stream in an area, accumulation.started_on is set by 205 when the first item goes in. deadline = started_on + `haz_storage_max_days` (§6.6). Alerts at deadline − 14 days and on the deadline to the site engineers and HSE Officers; the day after, the area is listed as overdue and one CA (priority high, source `environmental`) is created. A Dispatched consignment of that stream from that area clears started_on (full removal ASSUMPTION; a partial removal is recorded by re-entering started_on, never a later date than the oldest item still stored).

### 5.5 Consignments (CON)
- CON-1. Recorded by 206: site engineers for their sites; Contractor HSE Reps for generator engagements in their C scope. dispatched_at may be back-dated up to 72 h.
- CON-2. **Licence check at dispatch (no override):** transporter has a licence in force on local date(dispatched_at) with activity `collection_transport` and the stream's class; the facility has a licence or authorisation in force with the activity required by the route (list TR) and the class; else 422 `PROVIDER_LICENCE_INVALID` (none in force) or `LICENCE_SCOPE_MISMATCH` (wrong activity or class). Sewage needs a `sewage_tanker` transporter and a treatment facility with a `facility_authorisation`.
- CON-3. PRM-4 producer registration check.
- CON-4. Both providers approved (PRV-1).
- CON-5. mwan_manifest_ref required for classes in `mwan_manifest_required_for` (`MANIFEST_REF_REQUIRED`) `VERIFY` R3 (MWAN e-manifest scope).
- CON-6. **Receipt:** received_at ≥ dispatched_at, received_net_t > 0, ticket_ref and ticket_file required; receipt_recorded_at is set by the server. A Dispatched consignment with no receipt after due_on is **overdue**: alerts to the dispatcher, the generator's Contractor HSE Rep and the HSE Officers on the day after due_on, then weekly.
- CON-7. **Discrepancy:** discrepancy_pct = |received − estimated| ÷ estimated × 100; above `weight_discrepancy_pct` Close needs discrepancy_reason ≥ 20 chars (`DISCREPANCY_REASON_REQUIRED`). Quantities used in KPIs follow §6.3 whatever the discrepancy.
- CON-8. **Rejected** loads (facility refused them, e.g. contaminated load) need a reason and create one CA (priority high, source `environmental`); the waste must leave again on a new consignment, which may name the rejected one.
- CON-9. Airside source areas: AIR-3.

### 5.6 Monitoring (MON) and limits (LIM)
- MON-1. Instruments and points are managed by 208. Activation of an instrument needs calibration_valid_until > today; sound level meters need class 1 or 2 (IEC 61672-1) ASSUMPTION; at calibration expiry the job quarantines it and readings dated after expiry are refused (`INSTRUMENT_CALIBRATION_EXPIRED`). Alerts at 30 / 14 / 7 / 0 days to the HSE Officers.
- MON-2. Station instruments push `15min` values through an `env_monitor` device (§11.3) that can call only the 6e ingest endpoint; a repeated (device, parameter, window_start) is ignored (idempotent). The job derives `1h` and `24h` readings (source `derived`) per §6.2 as soon as a window closes.
- MON-3. Manual readings are recorded by 209 for points in the user's scope with a named active instrument (none for visual); manual laeq needs field_calibration_checked true (`FIELD_CALIBRATION_REQUIRED`) and a measurement of ≥ 15 min. Lab results are recorded by 209 with the lab provider and report ref; their window is the sampling window.
- MON-4. **Slots and coverage** (§6.5) count only days with work on the point's site (Phase 1 daily returns headcount > 0), as 6b.
- LIM-1. Each requirement row is prefilled from list DL (and list NA for noise).
- LIM-2. **Tighten only:** alert and limit values may be set ≤ the DL value (pH: range inside the DL range) by 208; a looser value → 422 `LIMIT_LOOSENING`. A permit condition with a lower limit replaces the row value and source `permit_condition`.
- LIM-3. Noise rows exist per period: `day` and `night` per §3.16 hours; a 1-h window belongs to the period of its start time.

### 5.7 Exceedances (EXD)
- EXD-1. A valid reading (not `15min`) with result `exceedance` (§6.2) opens an exceedance for its point, parameter and averaging, or joins the open episode (EXD-2). Alerts within 60 s (in-app + push + email) to the HSE Officers and site engineers of the site; AIR-1 adds recipients for airside points.
- EXD-2. **Episode:** consecutive exceeding readings of the same point, parameter and averaging join one exceedance; the episode ends at the first valid non-exceeding reading. A later exceeding reading opens a new exceedance.
- EXD-3. **Background suggestion:** for pm10, pm2_5 and visual_dust, the reading is flagged background (background_ref = the event) when its window overlaps a Phase 2 ops event of a type in `background_ops_event_types` covering the point's zone (or, for a point without zone, any zone of its site), or a background declaration (§3.11) covering its site. A background exceedance gets suggested_cause `background_natural`, is auto-reviewed with that cause after `exceedance_review_days` unless a reviewer changes it, and creates no CA.
- EXD-4. Background flags never delete or alter a reading; background exceedances are shown and charted (shaded) but not counted in K-123. A reviewer may reclassify a background exceedance as `project_activity` (e.g. a plume seen leaving the works during a dust event).
- EXD-5. **Review** (210) within `exceedance_review_days` (alert at the deadline to the HSE Officers, then daily): cause and immediate action required; `project_activity` requires responsible_engagement_id (`ENGAGEMENT_REQUIRED`) and creates one Phase 1 CA (source `environmental`, priority high, owner the first active Contractor HSE Rep of the engagement, else of its tier-1 engagement; due per `ca_due_days`). `third_party` and `unknown` create a CA only when the reviewer asks; `instrument_fault` requires the readings to be voided or the instrument quarantined.
- EXD-6. A lab or late reading that exceeds creates the exceedance with its own window date (K-123 attribution) and alerts at creation, labelled "late result".

### 5.8 Airside link (AIR)
- AIR-1. **Airside dust alert:** an exceedance (not background) or a visual_dust score 3 on a point whose zone is airside (or kind `airside`) alerts within 60 s, in addition to EXD-1, the holders of Phase 2 capability 67 on that site and the HSE Manager, with the message "Works dust may affect visibility on the airside — consider an operational suspension / قد يؤثر غبار الأعمال على الرؤية في الجانب الجوي". The alert links to the Phase 2 ops-event form; 6e never declares an ops event or suspends a WAP or permit (BD6e-4).
- AIR-2. Storage areas in airside zones must have lidded_secured true and type `sealed_bin_station`, `hazardous_store` or `liquid_store` (`AIRSIDE_STORAGE_NOT_SECURED`). On an airport project, wildlife_attractant streams (`food_domestic`) are accepted only in `sealed_bin_station` or `compactor` areas with lidded_secured true, anywhere on the project (`AIRSIDE_STORAGE_NOT_SECURED`, R6).
- AIR-3. A consignment from an airside storage area checks vehicle_plate against Phase 2 vehicles with an Active AVP on the dispatch date; no match → warning `AVP_NOT_FOUND` (saved; the vehicle may have been escorted, Phase 2 rules).
- AIR-4. **Post-storm check:** when a Phase 2 ops event of type `dust_sandstorm` ends, each site of its zones that has an active storage area gets a task due at ended_at + `post_storm_check_hours`: met by a Completed 6d inspection with template WSA, ENV or FOD on that site with completed_at in [ended_at, due]. Unmet at due → action panel and alert to the HSE Officers and site engineers.
- AIR-5. Every airside spill is reportable (SPL-2).

### 5.9 Spills (SPL)
- SPL-1. Recorded by 211 (also offline as 6d EXE-6, with client_uuid idempotency).
- SPL-2. **Reportable** ⇔ quantity_l ≥ `spill_reportable_l`, or reached ∈ {drain, water_body}, or contained = false, or (zone_type airside and `airside_spill_always_reportable`). Otherwise the spill is **minor**.
- SPL-3. **Phase 1 link:** a reportable spill must link a Phase 1 incident: either an existing incident of the same project with type environmental and occurred_at within ±24 h on the same site (else `INCIDENT_NOT_ENVIRONMENTAL`), or, by default, one created at submission as Reported with types [environmental], primary_type environmental, env_category spill, env_substance, env_quantity_l, env_contained, env_reached copied, the spill's site, zone, engagement and occurred_at, and incident_fields (`INCIDENT_FIELDS_REQUIRED` when missing). Phase 1 rules then apply (K-16, I-14, I-20, investigation).
- SPL-4. A minor spill creates no incident and never enters K-16 (BD6e-2).
- SPL-5. **Spill kits:** each scanned or picked kit becomes not ready with reason `used_replenish` until its next passing 6c check (§11.4); K-125 reflects it.
- SPL-6. Close needs cleanup_completed_at and cleanup_waste (a consignment of oily_absorbents / contaminated_soil / other hazardous stream, or an active hazardous_store area); else 422 `CLEANUP_WASTE_UNTRACKED`. Minor spills of < 1 L on paved ground may be closed with "absorbed and binned" ASSUMPTION.
- SPL-7. **Spill-kit coverage:** every active hazardous_store or liquid_store, and every zone named in an active aspect `fuel_spill_risk`, needs ≥ 1 in-service 6c spill_kit asset in the same zone; else listed on the action panel.

### 5.10 Water (WAT)
- WAT-1. Monthly water entries by 209; one per (site, month, source); a month's entries may be edited until the 10th day of the next month, then only by 214 void and re-entry.
- WAT-2. Dewatering discharge days are recorded on a `discharge` point by 209; pH, TSS and oil_grease readings follow §5.6–§5.7.
- WAT-3. A discharge day or reading on a date when the point's permit requirement is not in force is saved with warning `PERMIT_NOT_VALID` and alerts the HSE Officers and the HSE Manager once per day.

### 5.11 Complaints (CPL)
- CPL-1. response_due_on = received date + `complaint_response_days` (`authority_complaint_response_days` for via_authority). Alerts at due − 1 day and on the day after due to the HSE Officers; via_authority complaints also alert the HSE Manager at receipt.
- CPL-2. Category dust or noise lists the readings of points on the site within ± 2 h of the reported time for linking.
- CPL-3. Complainant data per P6e-2.

### 5.12 Environmental inspections (ENI)
- ENI-1. Environmental inspections are 6d inspections (inspection_type `environmental`) with the seeded ENV v2, WSA and DSN templates or others the HSE Manager publishes; 6d rules apply unchanged (findings, CAs with source `inspection`, DSN-02 stop rule, K-34 / K-35, K-110).
- ENI-2. The 6e pages show environmental inspections by site and zone; the K-122 tile shows "inspections done vs planned (environmental)" as a chip from 6d data, not a separate KPI.

### 5.13 KPIs and AI (EK)
- EK-1. All 6e KPIs are computed from stored records (K-R1). Attribution: consignments → local date(dispatched_at), engagement = generator; readings and exceedances → local date(window_end) of the first reading; spills → occurred_at, responsible engagement; water → month; permits → as_of (project level only; with a contractor filter K-118 shows "—"). Contractor filter with descendants as K-R5.
- EK-2. AI tool **T22 `get_environmental_kpis`** (project_ids, period, filters {site, zone, engagement, include_descendants, stream, class, route, point, parameter, substance}, metrics K-118…K-126, group_by {stream, class, route, transporter, facility, point, parameter, month, week, contractor, cause, substance}) returns aggregates only: provider names (organisations) may be returned; never driver names or plates, complainant data, reviewer names, photos or free texts. T13 returns E22–E23; AI-19 gains a section "Environment" (K-118…K-126, top 3 streams by tonnes, exceedances by parameter and cause).

### 5.14 PDPL (P6e-x)
- P6e-1. **Personal:** driver name and mobile, vehicle plate, complainant name and contact, recorder / reviewer / dispatcher identities, photos. **None:** everything else. **Sensitive:** none.
- P6e-2. Complainant name and contact are visible only to 212 holders; others see "contact held by the HSE team". They are deleted `complainant_retention_months` after the complaint is Closed; the complaint stays. Anonymous complaints are accepted.
- P6e-3. Driver name is optional (minimisation); plates and driver names are hidden from Viewer/Client and from AI tools; exports containing them write an `export` audit row (DECISIONS #78).
- P6e-4. Free texts get the P1-8 scan and the hint "no names or medical details"; the incident created from a spill copies only spill facts, never names.
- P6e-5. Photos are kept `photo_retention_months` or as long as a linked open CA, exceedance, spill or incident needs them. Consignments, permits, readings and exceedances are kept for the project life + 5 years ASSUMPTION (MWAN / NCEC record retention `VERIFY`).

### 5.15 Phase-boundary rules (BD6e)
- BD6e-1. 6e owns no hook kind. It reads Phase 1 daily returns and incidents, Phase 2 ops events, devices, vehicles and AVPs, 6c spill-kit assets and checks, and 6d inspections. It writes Phase 1 incidents (SPL-3) and CAs (source `environmental`) and the 6c `used_replenish` state (§11.4).
- BD6e-2. Phase 1 K-16 counts incidents only; minor spills, exceedances and complaints never enter K-16 or K-26.
- BD6e-3. Spill kits are registered and checked in 6c; K-107 excludes `spill_kit`, which 6e reports as K-125.
- BD6e-4. Only Phase 2 declares ops events (capability 67).
- BD6e-5. Worker exposure monitoring is 6a; 6e readings are never linked to a worker.

### 5.16 Error and warning codes (new)
422 `ASPECT_CONTROL_REQUIRED`, `CONTROL_LEVEL_TOO_LOW`, `PRODUCER_REGISTRATION_INVALID`, `PROVIDER_LICENCE_INVALID`, `LICENCE_SCOPE_MISMATCH`, `PROVIDER_NOT_APPROVED`, `STREAM_NOT_ACCEPTED`, `CONTAINMENT_INSUFFICIENT`, `AIRSIDE_STORAGE_NOT_SECURED`, `MANIFEST_REF_REQUIRED`, `DISCREPANCY_REASON_REQUIRED`, `INSTRUMENT_CALIBRATION_EXPIRED`, `FIELD_CALIBRATION_REQUIRED`, `BACKDATED_READING`, `VALUE_OUT_OF_RANGE`, `LIMIT_LOOSENING`, `ENGAGEMENT_REQUIRED`, `INCIDENT_FIELDS_REQUIRED`, `INCIDENT_NOT_ENVIRONMENTAL`, `CLEANUP_WASTE_UNTRACKED`, `DUPLICATE_WATER_ENTRY`, `SETTING_LOOSENING`; 409 `CONSIGNMENT_CLOSED`. Warnings: `PERMIT_NOT_VALID`, `AVP_NOT_FOUND`.

### 5.17 Permission matrix — Phase 6e extension
Continues 6d §5.13. Legend A/P/S/C/C1/R/—.

| # | Capability | HSE Mgr | HSE Officer | Site Eng/Sup | Permit Issuer | Permit Receiver | Contractor HSE Rep | Viewer/Client | OH Pract. |
|---|---|---|---|---|---|---|---|---|---|
| 202 | View 6e registers, KPIs, action panel; export (personal fields per P6e) | A | P | S | S | C1 | C | P (aggregates and registers without personal fields or photos) | — |
| 203 | Manage the aspects register | A | P | — | — | — | — | — | — |
| 204 | Manage permits, licences and providers (create, edit, suspend permit records) | A | P | — | — | — | — | — | — |
| 205 | Manage waste streams and storage areas | A | P | S | — | — | — | — | — |
| 206 | Record consignments and receipts | A | P | S | — | — | C | — | — |
| 207 | Close consignments; resolve discrepancies and rejections | A | P | — | — | — | — | — | — |
| 208 | Manage instruments, points, limits, devices, background declarations | A | P | — | — | — | — | — | — |
| 209 | Record readings (manual, visual, lab) and water entries | A | P | S | — | — | C | — | — |
| 210 | Review exceedances; close spills | A | P | — | — | — | — | — | — |
| 211 | Record spills and spill-kit use | A | P | S | S | C1 | C | — | — |
| 212 | Record and handle complaints; view complainant data | A | P | — | — | — | — | — | — |
| 213 | Edit 6e settings; approve, suspend or blacklist providers | A | — | — | — | — | — | — | — |
| 214 | Void 6e records | A | P | — | — | — | — | — | — |

Suspended-contractor users keep reads and lose writes (Phase 0 rule 28).

## 6. Calculations

Rounding half-up at output only (K-R8): percentages 1 dp, tonnes 1 dp (3 dp stored), intensities and L per man-hour 2 dp, dB(A) and µg/m³ 1 dp. Comparisons and warnings use unrounded values.

### 6.1 Aspect score
score = severity × likelihood (1–25); significant per ASP-1.

### 6.2 Averages and results
- **PM and water parameters:** arithmetic mean. **laeq:** energy mean, L = 10 · log10( (1/n) Σ 10^(Lᵢ/10) ).
- A `1h` value is derived when n(valid `15min` values in the hour) ÷ 4 × 100 ≥ `data_capture_pct`; a `24h` value (local day 00:00–24:00) when n(valid derived `1h` values) ÷ 24 × 100 ≥ `data_capture_pct`, as the mean of those hours (energy mean for laeq). Otherwise "insufficient data" (no value, no exceedance).
- **Result:** for a requirement (point, parameter, averaging, period): value > limit → `exceedance`; alert ≤ value ≤ limit → `alert`; else `ok`; pH: value < limit_min or > limit_max → `exceedance`; no matching row → `no_limit`.

### 6.3 Tonnes
t(consignment) = received_net_t when a receipt is recorded, else estimated_t (shown "provisional"). estimated_t = quantity (unit t); quantity × density (m³); quantity × density ÷ 1,000 (L, density in kg/L). `sewage` is counted in m³ only (excluded from tonnage and diversion). Voided and Rejected consignments are excluded (the re-dispatch counts).

### 6.4 Diversion and intensity
- **K-119** = Σ t over consignments dispatched in the period; intensity = K-119 × 100,000 ÷ man-hours (Phase 1, same scope and period) per 100,000 h; chip hazardous t.
- **K-120** = Σ t (route ∈ {reuse, recycle, recovery}) ÷ K-119 × 100; 0 t → "—".

### 6.5 Monitoring slots (K-122)
For each active requirement with schedule ≠ campaign: `continuous` → one slot per day with work, met ⇔ a `24h` value was derived (§6.2) for that day; `daily` → one slot per day with work, met ⇔ ≥ 1 valid reading that day; `weekly` → one slot per week (project `week_start`, belongs to the period of its last day, only weeks with last day ≤ as_of) with ≥ 1 day with work, met ⇔ ≥ 1 valid reading in the week; `monthly` → one slot per calendar month with work. Visual points count as daily. **K-122 = met ÷ required × 100** (pooled).

### 6.6 Hazardous storage deadline
deadline = started_on + `haz_storage_max_days` days; reminder at deadline − 14; overdue from deadline + 1.

### 6.7 KPI catalogue (continues 6d §6.7)

| ID | Metric (EN / AR) | Formula | Unit / display | Better |
|---|---|---|---|---|
| K-118 | **Environmental permit compliance** / الالتزام بالتصاريح البيئية | n(required requirements in force at as_of) ÷ n(required requirements applicable at as_of) × 100 (PRM-2); chip: expiring ≤ 30 days | %, 1 dp | higher |
| K-119 | Waste generated / النفايات المتولدة | §6.4; chips: hazardous t, intensity per 100,000 h, sewage m³ | t, 1 dp | lower |
| K-120 | **Waste diversion rate** / نسبة تحويل النفايات عن الطمر | §6.4; target line `diversion_target_pct` | %, 1 dp | higher |
| K-121 | Waste chain-of-custody on time / إثبات استلام النفايات في الموعد | n(consignments with due_on in period, ≤ as_of, receipt_recorded_at local date ≤ due_on) ÷ n(consignments, not voided, with due_on in period and ≤ as_of) × 100 | %, 1 dp | higher |
| K-122 | **Monitoring compliance** / الالتزام بخطة الرصد | §6.5 | %, 1 dp | higher |
| K-123 | **Project-caused exceedances** / التجاوزات بسبب المشروع | n(exceedances not voided whose cause, or while unreviewed whose suggested_cause, is not `background_natural`), by first-reading date; chips: background count, by parameter | count | lower |
| K-124 | Spills / الانسكابات | n(spills not voided, occurred in period); chip reportable | count | lower |
| K-125 | Spill-kit readiness / جاهزية حقائب الانسكاب | n(spill_kit assets ready at as_of, 6c §6.5 + SPL-5) ÷ n(spill_kit assets not Retired) × 100 | %, 1 dp | higher |
| K-126 | Water use / استهلاك المياه | Σ volume_m3 of months in period; L per man-hour = m³ × 1,000 ÷ man-hours; chip treated_effluent % | m³; L/h 2 dp | lower |

### 6.8 Leading-indicator warnings
Monthly job, day 2 at 07:00, per project and per tier-1 tree (DECISIONS #53); K-118 at project level only.
- **E22 Environmental compliance** in M: K-118 at month end < 100.0, or K-121(M) < `custody_warning_pct` (≥ 10 items), or K-122(M) < `monitoring_warning_pct`, or a hazardous storage deadline passed in M, or a consignment Dispatched for > 30 days at month end.
- **E23 Environmental performance** in M: K-123(M) ≥ `exceedance_warning_count`, or ≥ 1 reportable spill in M, or (K-119(M) ≥ 10 t and K-120(M) < `diversion_target_pct`), or a via_authority complaint received in M.
- T13 inputs: numerators, denominators, thresholds and record numbers; never names.

### 6.9 Worked examples (exact; backend unit tests must match)

**EV1 — waste, ANIA-EXP, September 2026** (man-hours 870,000, Phase 1 W1 / A.3).

| Stream | Route | t |
|---|---|---|
| inert_cd → RECYCON | recycle | 420.0 |
| asphalt_planings → RECYCON | recycle | 150.0 |
| metal_scrap → METALCO | recycle | 38.5 |
| wood → METALCO | recycle | 22.0 |
| packaging → METALCO | recycle | 9.5 |
| used_oil → OILREF | recovery | 1.8 |
| general_mixed → RIYADH-LF (incl. 3.600 t provisional, EV1b) | disposal_landfill | 61.0 |
| food_domestic → RIYADH-LF | disposal_landfill | 14.0 |
| oily_absorbents → HAZTREAT | treatment | 0.6 |
| **Total** | | **717.4** |

Diverted = 420.0 + 150.0 + 38.5 + 22.0 + 9.5 + 1.8 = 641.8 → K-120 = 641.8 ÷ 717.4 × 100 = 89.461… → **89.5 %**. Hazardous 1.8 + 0.6 = **2.4 t**. Intensity = 717.4 × 100,000 ÷ 870,000 = 82.459… → **82.46 t per 100,000 h**. Sewage 310 m³ (chip, not in tonnes). (EV1b) a skip of 12 m³ general_mixed without ticket → 12 × 0.30 = **3.600 t provisional**; when a ticket of 3.420 t is recorded, totals use 3.420.

**EV2 — dust, D-SAIR-01** (airside, PM10; 1-h alert 300 / limit 500; 24-h alert 250 / limit 340). 2026-09-16 10:00–11:00 quarter-hours 610, 655, 640, 655 → mean **640.0** > 500 → exceedance ENX-ANIA-EXP-2026-0017, margin (640 − 500) ÷ 500 = **28.0 %**, airside alert (AIR-1); review: project_activity, GULFPAVE, asphalt milling Twy B → CA high. 11:00–12:00 = 420.0 → alert, episode ends. 24-h mean of 09-16 = **212.4** → ok. (b) 2026-09-28 05:00–06:00: 1,180, 1,260, 1,250, 1,270 → **1,240.0**, window overlaps OPS-ANIA-EXP-2026-0009 (lvp, 04:10–07:40 local, zone Z-TWB) → background, no CA, not in K-123. (c) 2026-09-05: 17 valid hours → 17 ÷ 24 = 70.8 % < 75.0 → no 24-h value, slot **not met**; with 18 hours → 75.0 % → met.

**EV3 — noise, N-STWR-01** (RBT-52, mixed_commercial: day 65 / alert 62, night 55 / alert 52). 2026-09-10 23:00–24:00 LAeq,15min 60.0, 62.0, 61.0, 62.0 → 10·log10((10^6.0 + 10^6.2 + 10^6.1 + 10^6.2) ÷ 4) = 10·log10(1,357,178) = 61.326… → **61.3 dB(A)** > 55 → night exceedance (arithmetic mean 61.25 is not used). 21:00–22:00 = 63.0 → day period, alert (62 ≤ 63.0 ≤ 65), no exceedance.

**EV4 — permit alerts.** MWAN-PRD-TEST-0420 (ANIA-EXP producer registration) valid_to 2026-10-31, default alert days → alerts **2026-08-02, 2026-09-01, 2026-10-01, 2026-10-17, 2026-10-24, 2026-10-31**; status `expiring` at the clock (25 days). No renewal → **expired** on 2026-11-01; dispatches on 11-01 → `PRODUCER_REGISTRATION_INVALID`; K-118 at 11-01 = 3 ÷ 4 = 75.0 %. RBT-52 dewatering permit EPL-RBT-52-004 valid_to **2026-09-20**, discharge continued → K-118 RBT-52 at 09-30 = 3 ÷ 4 = **75.0 %**; discharge records 09-21…09-30 carry `PERMIT_NOT_VALID`.

**EV5 — consignment.** WCN-ANIA-EXP-2026-00412: used_oil 1,000 L × 0.90 ÷ 1,000 = **0.900 t**, HAZMOVE → OILREF, dispatched 2026-09-22 08:30, due_on **2026-09-29**. Receipt 0.820 t recorded 2026-09-30 → discrepancy |0.820 − 0.900| ÷ 0.900 = **8.9 %** (no reason needed) and **late** for K-121. Variant 0.780 t → **13.3 %** > 10.0 → reason required to close. Variant: HAZMOVE licence valid_to 2026-09-21 → dispatch 09-22 → `PROVIDER_LICENCE_INVALID`; GREENHAUL (no hazardous class) → `LICENCE_SCOPE_MISMATCH`.

**EV6 — monitoring compliance, September 2026.** ANIA-EXP: D-SAIR-01 continuous 30 slots, 28 met (09-05 17 h, 09-12 14 h) · V-SAIR daily 30 / 30 · V-SLAND daily 30 / 29 (09-19 missed) · D-SLAND-01 weekly 4 / 4 · N-SLAND-01 weekly 4 / 4 → 95 ÷ 98 = 96.938… → **96.9 %** (weeks ending 09-05, 09-12, 09-19, 09-26). RBT-52: D-STWR-01 weekly 4 / 4 · V-STWR 30 / 30 · V-SPOD 30 / 28 · N-STWR-01 continuous 30 / 30 · W-SPOD-01 daily (pH, TSS lab) 30 / 27 → 119 ÷ 124 = 95.967… → **96.0 %**.

**EV7 — spill classification** (threshold 20 L). (a) 40 L diesel, contained, paved, Z-APR-21 → **reportable** (≥ 20 and airside). (b) 8 L diesel, contained, paved, Z-LAY1 → **minor**. (c) 8 L diesel, contained, Z-APR-21 → **reportable** (airside). (d) 15 L hydraulic oil reached drain, Z-MSCP → **reportable**. (e) 25 L concrete washout contained on Z-PIERB → **reportable** (≥ 20). (f) 5 L contained = false on Z-LAY1 → **reportable**.

**EV8 — hazardous storage.** HWS-SLAND-01 chemical_containers started_on 2026-07-20, 90 days → deadline **2026-10-18**; reminder **2026-10-04**; at the clock "12 days left"; on **2026-10-19** overdue → one CA high.

**EV9 — September 2026 KPIs = seed (Appendix A).**

| Metric | ANIA-EXP calculation | ANIA-EXP | RBT-52 calculation | RBT-52 |
|---|---|---|---|---|
| K-118 (as_of 09-30) | 4 ÷ 4 | **100.0 %** | 3 ÷ 4 (dewatering expired) | **75.0 %** |
| K-119 | EV1 | **717.4 t** · 2.4 haz · 82.46 | 186.0 × 100,000 ÷ 135,000 = 137.777… | **186.0 t** · 3.6 haz · 137.78 |
| K-120 | EV1 | **89.5 %** | 98.4 ÷ 186.0 × 100 = 52.903… | **52.9 %** |
| K-121 | 90 ÷ 92 × 100 = 97.826… | **97.8 %** | 28 ÷ 30 × 100 = 93.333… | **93.3 %** |
| K-122 | EV6 | **96.9 %** | EV6 | **96.0 %** |
| K-123 | ENX-…-0017 (background 1: EV2b) | **1** | N-STWR-01 night (EV3) + W-SPOD-01 TSS (background 1: 09-03 declaration) | **2** |
| K-124 | 4 spills (1 reportable) | **4 · 1** | 1 minor | **1 · 0** |
| K-125 | 11 ÷ 12 × 100 = 91.666… | **91.7 %** | 5 ÷ 5 | **100.0 %** |
| K-126 | 6,960 m³; 6,960,000 ÷ 870,000; treated 4,350 ÷ 6,960 | **6,960 m³ · 8.00 L/h · 62.5 %** | 1,215 m³; 1,215,000 ÷ 135,000 | **1,215 m³ · 9.00 L/h · 0.0 %** |

RBT-52 waste: inert_cd 120.0 (60.0 recycle, 60.0 landfill), metal_scrap 18.4, wood 12.0, packaging 8.0 (recycle), general_mixed 24.0 (landfill), paint_solvent 3.6 (treatment) → 186.0 t, diverted 98.4 t.
Expected warnings for September 2026: **E22 RBT-52** (K-118 75.0; K-121 93.3 < 95.0; project, and the QIMMA tree on K-121) · **E23 ANIA-EXP** (reportable spill SPL-ANIA-EXP-2026-0031; project and RAWABI tree) · **E23 RBT-52** (K-123 2 ≥ 2; K-120 52.9 < 70.0 with 186.0 t; project and QIMMA tree) · no E22 for ANIA-EXP.

## 7. Alerts & expiries

Channels as Phases 1–6d (in-app and email in the recipient's language; push on the phone web app; no SMS, DECISIONS #124). Each (subject, step) is sent once; re-running a job never sends twice.

| Trigger | Recipient | Timing | Channel |
|---|---|---|---|
| Exceedance opened (EXD-1, EXD-6) | HSE Officers; site engineers of the site | Within 60 s | In-app + push + email |
| Airside dust alert (AIR-1) | + capability 67 holders on the site; HSE Manager | Within 60 s | In-app + push + email |
| Exceedance not reviewed (EXD-5) | HSE Officers | At deadline, then daily | In-app + email |
| Reportable spill (SPL-3) | HSE Officers; HSE Manager; site engineers; Contractor HSE Rep (Phase 1 incident alerts also apply) | Within 60 s | In-app + push + email |
| Permit expiry (PRM-3) | HSE Officers; HSE Manager | `permit_alert_days`, 07:08; day after expiry | In-app + email |
| Provider licence expiry (PRM-3) | HSE Officers | `provider_licence_alert_days`, 07:08 | In-app + email |
| Instrument calibration (MON-1) | HSE Officers | 30 / 14 / 7 / 0 days | In-app + email |
| Consignment overdue (CON-6) | Dispatcher; generator's Contractor HSE Rep; HSE Officers | Day after due_on, then weekly | In-app + email |
| Consignment rejected (CON-8) | HSE Officers; Contractor HSE Rep | At recording | In-app + email |
| Hazardous storage (WST-5) | Site engineers; HSE Officers | Deadline − 14, deadline; overdue day | In-app + email |
| Post-storm check unmet (AIR-4) | HSE Officers; site engineers | At due | In-app + push |
| Discharge without valid permit (WAT-3) | HSE Officers; HSE Manager | Once per day | In-app + email |
| Complaint received / due (CPL-1) | HSE Officers (HSE Manager for via_authority) | At receipt; due − 1; day after due | In-app + email |
| Aspect review (ASP-3) | HSE Officers | Flag set; 30 / 0 days | In-app |
| E22 / E23 | HSE Manager; HSE Officers; tier-1 Contractor HSE Rep for its tree | Monthly job, day 2, 07:00 | In-app + email |

## 8. Reports / KPIs fed

### 8.1 Dashboard additions (Phase 1 §8.1)
1. **Tiles:** K-120 diversion (chips K-119 t and intensity) · K-122 monitoring compliance (chip K-123 and background count) · K-118 permits (chip expiring ≤ 30 days) · K-124 spills (chips reportable, K-125 kit readiness). K-16 tile unchanged.
2. **Environment band** (live): open exceedances (airside first); airside dust alerts in the last 24 h; permits and licences expiring ≤ 30 days; consignments overdue; hazardous storage ≤ 14 days to deadline; post-storm checks due.
3. **Charts:** C34 waste tonnes by class by month (stacked) with the diversion % line and target; C35 readings vs alert and limit lines per point and parameter, with background events shaded; C36 exceedances (project / background) and spills (minor / reportable) by month.
4. Filters D-2 apply, plus stream, class, point and parameter.

### 8.2 Expiring items and action panel
- `ExpiringItemKind`: `env_permit`, `provider_licence`, `env_instrument_calibration`, `haz_storage_deadline`, `aspect_review`.
- Action panel: exceedances awaiting review; requirements not in force; consignments overdue or rejected; hazardous storage overdue; discharge without valid permit; post-storm checks unmet; storage areas or fuel-risk zones without a spill kit (SPL-7); spills not closed after 7 days; complaints past due.

### 8.3 Registers and prints
Aspects register, permit and licence register, provider register, consignment register (filters by stream, provider, status; driver and plate per P6e-3), storage areas, readings, exceedances, spills, water, complaints. Prints: consignment note (EN/AR, for the driver), monthly environmental report (K-118…K-126, charts C34–C36, exceedances with causes and CAs), waste summary by stream, route, transporter and facility for any period (for the MWAN periodic return `VERIFY` format). Exports (202) write an `export` audit row.

### 8.4 Feeds to other phases
- **Phase 1:** reportable spills as environmental incidents (K-16, I-14, I-20 with `ncec`), CAs (`environmental`), K-118…K-126, E22–E23, T22, AI-19 section.
- **6c:** `used_replenish` on spill kits. **6d:** environmental templates and inspections (K-34, K-35, K-110). **6g:** K-120, K-121, K-123, K-124 per contractor.

## 9. Acceptance criteria

Fixtures: the Appendix A seed with the Phase 0–6d seeds; clock `HSE_CLOCK_AT` = **2026-10-06 10:00** unless stated. Users as 6d §9 (Faisal HSE Manager; Noura HSE Officer ANIA-EXP; Lina HSE Officer RBT-52; Omar site engineer S-AIR; Fahad site engineer S-LAND; Khalid issuer; Ramesh receiver NAJD; Ahmed Contractor HSE Rep RAWABI; Yousef Contractor HSE Rep QIMMA; Sarah viewer).

**Aspects**
1. **Given** a draft aspect severity 4 × likelihood 3 **Then** score 12, significant; activating without a control or monitoring link → 422 `ASPECT_CONTROL_REQUIRED`; with a PPE-only control → 422 `CONTROL_LEVEL_TOO_LOW`; with an engineering control and link D-SAIR-01 pm10 **Then** Active with review_due_on = activation date + 12 months − 1 day.
2. **Given** severity 2 × likelihood 3 with legal_requirement true **Then** significant; with all flags false **Then** not significant and activates without links.
3. **Given** ENX-ANIA-EXP-2026-0017 reviewed as project_activity **Then** ASP-ANIA-EXP-004 (dust_emission, S-AIR) gets review_flag and Noura one alert; a noise exceedance on S-LAND does not flag it.

**Permits, licences and providers**
4. **Given** EV4 **Then** MWAN-PRD-TEST-0420 alerts on the six listed dates, is `expiring` at the clock, `expired` on 11-01, a dispatch on 11-01 → 422 `PRODUCER_REGISTRATION_INVALID`, and K-118 at 11-01 = 75.0 %.
5. **Given** a renewal record with requirement_code MWAN-REG valid 2026-11-01…2027-10-31 recorded on 10-20 **Then** no alert is sent on 10-24 or 10-31, the old record becomes `superseded` on 11-01 and dispatch on 11-01 is accepted.
6. **Given** EV4 RBT-52 **Then** K-118 = 75.0 % at 09-30, discharge records from 09-21 carry `PERMIT_NOT_VALID`, and Lina and Faisal get one alert per day.
7. **Given** Ahmed creates a permit **Then** 403 (204); Noura **Then** saved; Faisal removes 90 from `permit_alert_days` **Then** 422 `SETTING_LOOSENING`; Noura blacklisting a provider **Then** 403 (213).
8. **Given** EV5 variants **Then** `PROVIDER_LICENCE_INVALID` and `LICENCE_SCOPE_MISMATCH`; a blacklisted transporter → 422 `PROVIDER_NOT_APPROVED`; a sewage load with a non-`sewage_tanker` transporter → 422 `LICENCE_SCOPE_MISMATCH`.

**Waste**
9. **Given** a hazardous_store with containment 100 % **Then** 422 `CONTAINMENT_INSUFFICIENT`; 110 % **Then** saved; used_oil added to a `skip` **Then** 422 `STREAM_NOT_ACCEPTED`.
10. **Given** a storage area on Z-APR-21 of type skip or with lidded_secured false **Then** 422 `AIRSIDE_STORAGE_NOT_SECURED`; food_domestic accepted in an open skip on S-LAND (airport project) **Then** 422.
11. **Given** EV5 **Then** 0.900 t estimated, 8.9 % discrepancy closes without a reason, 13.3 % needs one (`DISCREPANCY_REASON_REQUIRED`), and editing a Closed consignment → 409 `CONSIGNMENT_CLOSED`.
12. **Given** a hazardous consignment without mwan_manifest_ref **Then** 422 `MANIFEST_REF_REQUIRED`; a non-hazardous one without it **Then** saved.
13. **Given** WCN-…-00412 not received by 09-29 **Then** on 09-30 07:08 Fahad, Ahmed and Noura are alerted; the receipt recorded 09-30 counts as late in K-121.
14. **Given** EV1b **Then** the skip shows 3.600 t "provisional" and after the ticket K-119 uses 3.420 t.
15. **Given** EV1 **Then** K-119 = 717.4 t, hazardous 2.4 t, intensity 82.46, K-120 = 89.5 %; a voided or rejected consignment is excluded and sewage shows 310 m³ outside the tonnes.
16. **Given** a rejected load **Then** one CA high (source `environmental`) exists and a new consignment may reference it.
17. **Given** EV8 **Then** Fahad and Noura are alerted on 10-04, the area shows "12 days left" at the clock, a CA high is created on 10-19, and a chemical_containers consignment dispatched from HWS-SLAND-01 clears started_on.
18. **Given** Ahmed records a consignment for NAJD **Then** saved; for QIMMA **Then** 404 (RBT-52 not visible to him); Ahmed closing it **Then** 403 (207).
19. **Given** a consignment from WSA-SAIR-01 with a plate without an Active AVP **Then** saved with warning `AVP_NOT_FOUND`.

**Monitoring and exceedances**
20. **Given** an instrument whose calibration ended 2026-10-05 **Then** a reading with window_end 10-06 → 422 `INSTRUMENT_CALIBRATION_EXPIRED`, the job quarantined it on 10-06, and alerts went at 30 / 14 / 7 / 0 days.
21. **Given** a manual laeq reading without field_calibration_checked **Then** 422 `FIELD_CALIBRATION_REQUIRED`; a manual reading 80 h old **Then** 422 `BACKDATED_READING`; pm10 = 25,000 **Then** 422 `VALUE_OUT_OF_RANGE`.
22. **Given** Noura sets D-SAIR-01 pm10 24-h limit 400 **Then** 422 `LIMIT_LOOSENING`; 300 **Then** saved and audited; a permit condition of 280 linked to that row **Then** the row uses 280 with source permit_condition.
23. **Given** EV2 **Then** the 1-h value is 640.0, ENX-…-0017 opens with margin 28.0 %, Noura and Omar are alerted within 60 s, and Khalid and Faisal get the airside dust alert linking to the ops-event form; no ops event or WAP change is made by 6e.
24. **Given** three consecutive exceeding hours, one compliant hour, then one exceeding hour **Then** two exceedances exist, the first with 3 readings.
25. **Given** EV2b **Then** the reading is flagged background (OPS-ANIA-EXP-2026-0009), the exceedance is auto-reviewed `background_natural` after 3 days with no CA and is not in K-123; reclassified by Noura as project_activity with GULFPAVE **Then** a CA high is created and K-123 counts it.
26. **Given** BGD-RBT-52-2026-001 on S-TWR 2026-09-03 08:00–20:00 **Then** the D-STWR-01 24-h sample of 09-03 is background, and a noise reading in that window is not.
27. **Given** EV2c **Then** 17 valid hours give "insufficient data" and an unmet slot, 18 give a 24-h value and a met slot.
28. **Given** EV3 **Then** 61.3 dB(A) night exceedance and the 21:00 hour is `alert` only.
29. **Given** a visual_dust score 3 at V-SAIR **Then** an exceedance with the airside alert; score 2 **Then** result alert, no exceedance.
30. **Given** a review with cause project_activity and no engagement **Then** 422 `ENGAGEMENT_REQUIRED`; with GULFPAVE **Then** CA high owned by Ahmed (RAWABI tree rep); unreviewed after 3 days **Then** Noura is alerted daily.
31. **Given** the W-SPOD-01 TSS lab result 85 mg/L sampled 09-24 and recorded 09-27 **Then** an exceedance dated 09-24 labelled "late result" is created and alerts at recording; it counts in K-123 for September.
32. **Given** EV6 **Then** K-122 = 96.9 % (ANIA-EXP) and 96.0 % (RBT-52); a day with no daily-return headcount on the site creates no slot.
33. **Given** a station pushes the same 15-min value twice **Then** one reading exists; the `env_monitor` device token calling a gate-check endpoint **Then** 403.

**Airside**
34. **Given** a `dust_sandstorm` ops event on S-AIR ending 14:00 **Then** a post-storm task is due 18:00; a WSA inspection Completed on S-AIR at 15:30 meets it; with none, Noura and Omar are alerted at 18:00 and the action panel lists it.
35. **Given** DSN-02 non-compliant on Z-TWB **Then** 6d requires the stop-work fields (`STOP_RECORD_REQUIRED`) and creates a CA critical with source `inspection`.

**Spills**
36. **Given** EV7 (a)–(f) **Then** the reportable flags are as listed.
37. **Given** EV7 (a) submitted with incident fields **Then** a Phase 1 incident is Reported with types [environmental], env_category spill, substance diesel, 40 L, contained, reached none, zone Z-APR-21, and K-16 increases by 1; EV7 (b) **Then** no incident, K-16 unchanged, K-124 + 1.
38. **Given** a reportable spill linked to an existing environmental incident on the same site 10 h earlier **Then** no new incident; linking an injury-only incident **Then** 422 `INCIDENT_NOT_ENVIRONMENTAL`; a reportable spill with no link and no severity **Then** 422 `INCIDENT_FIELDS_REQUIRED`.
39. **Given** SK-SAIR-02 scanned as used **Then** it is not ready (`used_replenish`) and K-125 falls until a passing 6c check.
40. **Given** a reportable spill closed without cleanup waste **Then** 422 `CLEANUP_WASTE_UNTRACKED`; with HWS-SLAND-01 **Then** Closed by Noura; Fahad closing **Then** 403 (210).
41. **Given** `env_notifications_from` = 2026-10-01 and EV7 (d) on 2026-10-06 **Then** the Phase 1 incident requires `ncec` (due 24 h) and EV7 (a) on 10-06 requires `airport_operator`; the September seed incidents keep their Phase 1 notifications unchanged.
42. **Given** HWS-SLAND-01 and no in-service spill kit in Z-LAY1 **Then** the action panel lists it (SPL-7).
43. **Given** the same spill submitted twice offline with one client_uuid **Then** one spill and one incident exist.

**Water and complaints**
44. **Given** ANIA-EXP September water entries **Then** K-126 = 6,960 m³, 8.00 L/h, treated 62.5 %; a second S-AIR 2026-09 `tanker` entry **Then** 422 `DUPLICATE_WATER_ENTRY`.
45. **Given** W-SPOD-01 pH 9.4 or 5.8 **Then** exceedance; 7.5 **Then** ok.
46. **Given** a via_authority complaint received 10-06 **Then** due 10-09 and Faisal is alerted at receipt; a phone complaint is due 10-13; CPL-2 lists N-STWR-01 readings within ± 2 h for a noise complaint.
47. **Given** ECP-RBT-52-2026-004 **Then** Lina sees the complainant contact; Sarah and Yousef see "contact held by the HSE team"; 12 months after closure the contact is deleted and the complaint remains.

**Inspections, KPIs, warnings, AI, PDPL**
48. **Given** the 6e seed **Then** ENV v2 is Published and ENV v1 Superseded; WSA-07 is hidden on landside zones; the environmental plans start 2026-10-01, so K-34 85.0 %, K-35 92.5 % and K-110 90.8 % for September 2026 are unchanged.
49. **Given** a WSA inspection with WSA-03 non-compliant on Z-LAY1 **Then** the HWS-SLAND-01 page lists that answer first and the 6d CA (source `inspection`).
50. **Given** September 2026 **Then** K-118…K-126 match EV9 for both projects.
51. **Given** September 2026 **Then** E22 and E23 are raised exactly as EV9 lists, with T13 inputs and no names; ANIA-EXP has no E22.
52. **Given** Ahmed with the RAWABI tree filter **Then** K-119…K-126 cover RAWABI-tree engagements and K-118 shows "—".
53. **Given** the AI is asked "which transporter carried most hazardous waste in September?" **Then** T22 groups by transporter and names HAZMOVE; "who complained about the noise?" or "who drove WCN-…-00412?" **Then** no personal data is returned and the assistant says it is not available to it.
54. **Given** Sarah **Then** she sees 6e KPIs and registers without driver names, plates, complainant data or photos; an export with driver names by Noura writes an `export` audit row.
55. **Given** Faisal sets `spill_reportable_l` 30, `manifest_return_days` 10 or `airside_spill_always_reportable` false **Then** 422 `SETTING_LOOSENING`; 10 L and 5 days **Then** saved and audited; Noura editing any 6e setting **Then** 403.
56. **Given** Noura voids a Dispatched consignment (reason ≥ 20 chars) **Then** it leaves K-119…K-121; Fahad voiding **Then** 403 (214).
57. **Given** the seed **Then** Phase 1 K-16 for ANIA-EXP September = 1 (the spill-linked incident), 6c K-107 for September stays 96.6 % / 94.2 % with the spill kits seeded (excluded), and K-125 = 91.7 % / 100.0 %.
58. **Given** the UI in Arabic **Then** every 6e label, status, list value, alert, print and error has its AR text; numbers, units and codes stay left-to-right inside the RTL layout.

## 10. Open questions for the HSE Manager

Each has a default so the build can start.
1. **Permits:** which NCEC permit (category and phase) does each project hold, and does the municipality or NWC issue the RBT-52 dewatering discharge approval?
2. **Dust triggers:** 1-h boundary trigger 300 / 500 µg/m³ PM10 (project ASSUMPTION) with the NCEC 24-h value 340. Does the client CEMP or the airport operator set its own?
3. **Noise:** RBT-52 boundary as mixed_commercial (65 / 55 dB(A)), night from 22:00. What hours and limits does the municipal permit allow for night pours?
4. **Spills:** reportable from 20 L and every airside spill. Does the airport operator's procedure require a different threshold or a direct report to the AOCC?
5. **Hazardous storage:** 90 days maximum. Do your MWAN registration conditions set a shorter limit?
6. **Diversion target:** 70 % by weight (client target?), and should inert C&D waste count in the diversion rate or be reported separately?
7. **Receipt proof:** HSE Officers close consignments from the weighbridge ticket. Should the contractor's environmental officer be allowed to close their own loads?
8. **Scope:** carbon and energy reporting (fuel, electricity) is not included. Is it needed for the client's sustainability reporting (e.g. Mostadam or LEED)?

## 11. Changes required in earlier specs (applied 2026-10-09: 0-foundation v1.3, 1-dashboard v1.8, 2-access-permits v1.7, 6c-emergency-drills v1.2, 6d-field-assurance v1.1)

### 11.1 `0-foundation.md` v1.2 → v1.3
1. Matrix rows 202–214 (§5.17).

### 11.2 `1-dashboard.md` v1.7 → v1.8
1. §3.8 CA `source_type` adds `environmental` (source_id = 6e exceedance, consignment, storage area, complaint or spill).
2. §3.3 notifications: body `ncec` (المركز الوطني للرقابة على الالتزام البيئي). §5.2 I-20, for incidents with occurred_at ≥ setting `env_notifications_from` (§3.10, edited through 213; null = rule off): `ncec` required for environmental incidents with env_reached ∈ {drain, water_body} or actual_severity ≥ 3, deadline 24 h ASSUMPTION `VERIFY` R1; `airport_operator` required for environmental incidents in airside zones, immediately `VERIFY` R6. W1 and the seed are unchanged (the setting is null in W1 and 2026-10-01 in the seed).
3. Incident read model shows the linked 6e spill number (read only); an incident created by 6e SPL-3 is a normal Phase 1 incident.
4. §5.9 AI: T22 (EK-2); T13 returns E22–E23; AI-19 section "Environment".
5. §6.9 / §7: E22 Environmental compliance and E23 Environmental performance, same monthly job and recipients; K-118…K-126 by reference; K-16 and K-26 unchanged.
6. §8.1: tiles, environment band, charts C34–C36; `ExpiringItemKind` and the action-panel items of §8.2.

### 11.3 `2-access-permits.md` v1.6 → v1.7
1. §3.19 device kind `env_monitor`: not bound to a gate, may call only the 6e reading-ingest endpoint; GC-1 token, rotation and revocation rules.
2. 6e consumes `ops_event.started` / `ops_event.ended` (EXD-3, AIR-4) and reads vehicles and AVPs (AIR-3); no Phase 2 behaviour changes.

### 11.4 `6c-emergency-drills.md` v1.1 → v1.2
1. List EAT adds `spill_kit` حقيبة احتواء الانسكابات, subtypes `general` · `oil_only` · `chemical`, check interval 30 days, critical items EC01 and EC05, plus EC04.
2. §6.5 readiness: a spill kit recorded as used in a 6e spill is not ready (reason `used_replenish`) until its next passing check.
3. K-107 and E19 exclude asset_type `spill_kit` (reported as 6e K-125), so the 6c worked examples and seed values are unchanged.

### 11.5 `6d-field-assurance.md` v1.0 → v1.1
1. §3.15 seeded templates: ENV v2 supersedes ENV v1; WSA and DSN added (inspection_type `environmental`). No rule changes.

### 11.6 `3-ptw.md`, `4-third-party-cert.md`, `5-training.md`, 6a, 6b
No changes. Note: 6b readings and 6e readings are separate registers; a site may have both a WBGT point and a dust point.

## Appendix A — Seed data (fictional; `seed_fake = true`; licence, permit and ticket numbers contain `TEST`)

### A.1 Principles
- Builds on the Phase 0–6d seeds. Clock `HSE_CLOCK_AT` = 2026-10-06T10:00:00+03:00.
- Settings: both projects at the §3.16 defaults, `env_notifications_from` = **2026-10-01**.
- The generator never changes Phase 1–6d values: September K-16 stays 1 on ANIA-EXP (that incident is linked to SPL-ANIA-EXP-2026-0031; if the Phase 1 generator's incident differs in date, engagement or zone, the spill takes the incident's values and the backend records the difference in DECISIONS); 6c K-107 excludes the spill kits; environmental 6d plans start 2026-10-01.

### A.2 Providers (org-wide, approved)
| Code | Kind | Licence (activity · classes · valid_to) |
|---|---|---|
| GREENHAUL | transporter | MWAN-TR-TEST-1101 · collection_transport · inert, non_hazardous · 2027-05-31 |
| HAZMOVE | transporter | MWAN-TR-TEST-1102 · collection_transport · hazardous · **2026-11-15** |
| SEWTANK | sewage_tanker | MWAN-TR-TEST-1103 · collection_transport · liquid_sewage · 2027-01-31 |
| RECYCON | recycler (RECYCON-1 Riyadh) | MWAN-RC-TEST-2201 · recycling · inert · 2027-02-28 |
| METALCO | recycler (METALCO-1) | MWAN-RC-TEST-2202 · recycling · non_hazardous · 2027-08-31 |
| OILREF | recycler (OILREF-1 re-refinery) | MWAN-TF-TEST-3301 · recycling, treatment · hazardous · 2027-03-31 |
| HAZTREAT | treatment_facility (HAZTREAT-1) | MWAN-TF-TEST-3302 · treatment · hazardous · 2026-12-31 |
| RIYADH-LF | landfill (municipal) | facility_authorisation MUN-LF-TEST-4401 (momrah_municipality) · disposal · inert, non_hazardous · 2027-12-31 |
| STP-RUH | treatment_facility (sewage plant) | facility_authorisation NWC-STP-TEST-5501 (nwc) · treatment · liquid_sewage · 2027-06-30 |
| ENVLAB | environmental_lab | lab_accreditation NCEC-LAB-TEST-6601 · 2027-04-30 |

### A.3 Project permits (required)
| Project | Record | Type · requirement_code | valid_to |
|---|---|---|---|
| ANIA-EXP | EPL-ANIA-EXP-001 ENVP-TEST-0001 | ncec_env_permit_construction · NCEC-CONSTR | 2027-03-31 |
| ANIA-EXP | EPL-ANIA-EXP-002 MWAN-PRD-TEST-0420 | mwan_producer_registration · MWAN-REG | **2026-10-31** (EV4) |
| ANIA-EXP | EPL-ANIA-EXP-003 BLD-TEST-7001 | municipal_construction_permit · MUN-BLD | 2027-06-30 |
| ANIA-EXP | EPL-ANIA-EXP-004 CEMP-TEST-AOP-3 | cemp_approval (airport_operator) · CEMP | no expiry |
| RBT-52 | EPL-RBT-52-001 / -002 / -003 | NCEC-CONSTR 2027-01-31 · MWAN-REG 2027-02-28 · MUN-BLD 2027-09-30 | — |
| RBT-52 | EPL-RBT-52-004 DWD-TEST-0310 | dewatering_discharge_permit · DEWATER, applies 2026-06-01…2026-12-31 | **2026-09-20** (expired, EV4) |

### A.4 Streams, storage areas, consignments
- ANIA-EXP streams: the EV1 streams plus sewage. Areas: WSA-SLAND-01 segregated_bay (Z-LAY1: inert_cd, metal_scrap, wood, packaging, general_mixed) · HWS-SLAND-01 hazardous_store 110 % (Z-LAY1: used_oil, oily_absorbents, chemical_containers; chemical_containers started 2026-07-20, EV8) · WSA-SLAND-02 compactor (Z-LAY1: food_domestic) · WSA-SAIR-01 sealed_bin_station lidded (Z-APR-21: general_mixed, packaging) · WSA-SAIR-02 segregated_bay (Z-TWB: asphalt_planings). RBT-52: WSA-SPOD-01 segregated_bay (Z-B4), HWS-SPOD-01 hazardous_store 110 % (Z-B4).
- September 2026 ANIA-EXP: 96 consignments dispatched (EV1 tonnes, generators RAWABI, NAJD, GULFPAVE, SAHARA); K-121 items 92 (due_on 09-01…09-30), 90 on time; late: WCN-ANIA-EXP-2026-00412 (EV5) and one general_mixed load received 2 days late. RBT-52: 34 dispatched (186.0 t), 30 items, 28 on time.

### A.5 Instruments, points, readings
| Project | Point | Kind · source · zone | Requirements | Instrument (calibration →) |
|---|---|---|---|---|
| ANIA-EXP | D-SAIR-01 | airside · station · Z-TWB | pm10 1h and 24h continuous (DL) | EMI-ANIA-EXP-01 pm_station, DEV-EM-ANIA-01 (2027-04-30) |
| ANIA-EXP | D-SLAND-01 | boundary · manual · Z-LAY1 | pm10 24h weekly | EMI-ANIA-EXP-02 pm_sampler_24h (2027-01-31) |
| ANIA-EXP | V-SAIR / V-SLAND | work_area · visual · — | visual_dust daily | — |
| ANIA-EXP | N-SLAND-01 | boundary · manual · Z-PIERB · industrial | laeq measurement weekly (day 70 / night 70) | EMI-ANIA-EXP-03 SLM class 1 (2026-12-15) |
| RBT-52 | D-STWR-01 | sensitive_receptor · manual · Z-CORE | pm10 24h weekly | EMI-RBT-52-01 pm_sampler_24h (2027-02-28) |
| RBT-52 | V-STWR / V-SPOD | work_area · visual | visual_dust daily | — |
| RBT-52 | N-STWR-01 | sensitive_receptor · station · Z-CORE · mixed_commercial | laeq 1h continuous | EMI-RBT-52-02 noise_station, DEV-EM-RBT-01 (2027-03-31) |
| RBT-52 | W-SPOD-01 | discharge · lab · Z-B4 · permit EPL-RBT-52-004 | ph, tss (50), oil_grease (10) daily | ENVLAB |
- Readings fill the EV6 slots exactly (missed slots as listed). Named: EV2 (09-16 and 09-28 hours, 09-05 17 valid hours, 09-12 14 valid hours), EV3 (09-10), W-SPOD-01 TSS 85 mg/L sampled 09-24 recorded 09-27, D-STWR-01 09-03 24-h 410 µg/m³ under BGD-RBT-52-2026-001 (NCM warning NCM-TEST-0903).
- Exceedances: ENX-ANIA-EXP-2026-0017 (EV2, GULFPAVE, CA closed 09-20), ENX-ANIA-EXP-2026-0018 (EV2b, background), ENX-RBT-52-2026-0005 (EV3, QIMMA, CA open), ENX-RBT-52-2026-0006 (TSS, QIMMA, CA open), ENX-RBT-52-2026-0004 (09-03, background).

### A.6 Spills and spill kits
- ANIA-EXP September: **SPL-ANIA-EXP-2026-0031** (2026-09-25 03:20, GULFPAVE, Z-APR-21, diesel 40 L refuelling, contained, paved, kit SK-SAIR-02 used and replenished 09-26, reportable, linked to the September environmental incident, closed with HWS-SLAND-01) and three minor spills (hydraulic oil 5 L Z-LAY1, diesel 8 L Z-LAY1, paint 2 L Z-PIERB; all contained on paved ground). RBT-52: one minor spill (hydraulic oil 6 L, Z-B4).
- Spill kits (6c assets, type spill_kit): ANIA-EXP 12 (SK-SAIR-01…05, SK-SLAND-01…07); SK-SLAND-06 failed its 09-27 check on EC05 → 11 ready. RBT-52 5, all ready.

### A.7 Water, complaints, aspects
- Water September 2026: ANIA-EXP S-AIR tanker 1,800 m³ + treated_effluent 4,350 m³ (dust suppression); S-LAND network 810 m³ → 6,960 m³; sewage 310 m³ via SEWTANK to STP-RUH. RBT-52 network 1,215 m³.
- **ECP-RBT-52-2026-004**: 2026-09-10 23:40, phone, noise, residential building east of S-TWR, complainant (fake) Hamad Al-Otaibi / حمد العتيبي, +966500000999, linked to ENX-RBT-52-2026-0005, responded 09-12, closed 09-20.
- Aspects: ANIA-EXP 14 entries (e.g. ASP-ANIA-EXP-004 asphalt milling dust on S-AIR, severity 4 × likelihood 3, impact aviation_safety, controls water bowser and milling with spray bars, link D-SAIR-01 and DSN); RBT-52 10 entries (night concrete-pour noise, dewatering discharge).

### A.8 Templates and plans
ENV v2, WSA and DSN Published 2026-10-01 by Faisal. Plans from 2026-10-01: WSA weekly per site; DSN daily on S-AIR rotating Z-APR-21 / Z-TWB and daily on S-POD; ENV monthly per site.

## Change log

| Version | Date | Author | Change |
|---|---|---|---|
| v1.0 | 2026-10-09 | HSE Consultant Agent | First issue. §1–§11 and Appendix A: aspects and impacts register with significance; project permits and provider licences with expiry alerts; providers; waste streams, storage areas (airside rules, hazardous storage limit), consignments with licence checks, receipts, discrepancies and rejections; tonnage and diversion; dust, noise and discharge monitoring with calibrated instruments, tighten-only limits, derived averages, exceedance episodes, background labelling from Phase 2 ops events, airside dust alerts and post-storm checks; spills linked to Phase 1 incidents and 6c spill kits; water use and dewatering; complaints; environmental inspections on 6d templates (ENV v2, WSA, DSN). Capabilities 202–214, KPIs K-118…K-126, warnings E22–E23, AI tool T22, charts C34–C36, CA source `environmental`, notification body `ncec`, device kind `env_monitor`, 6c asset type `spill_kit`. 58 acceptance criteria. Earlier-spec changes in §11, not yet applied. |
| v1.1 | 2026-10-09 | HSE Consultant Agent | Note required by Phase 6f (`6f-incident-followup.md` v1.0 §11.4); no rule changes: the `ncec` and environmental `airport_operator` triggers of §11.2 item 2 become the 6f profile rows NCEC-W (`env_ncec`) and AO-W (`env_airside`) for incidents under a project's `followup_rules_from`, still gated by `env_notifications_from` (AC41 unchanged). |
