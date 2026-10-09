# Module Spec — Phase 6c: Emergency Preparedness & Drills (emergency response plan, assembly points and contacts, emergency organisation and coverage, emergency equipment readiness, drill programme, drill execution and evaluation, muster, real emergency event log)

**Version:** v1.0 · **Date:** 2026-10-09 · **Author:** HSE Consultant Agent · **Status:** Draft. The HSE Manager asked to proceed without waiting for approval and will review the choices later (§10).
**Builds on:**
- `0-foundation.md` v1.0: projects, sites, zones (airside attributes `in_movement_area`, `airside_area`), roles, scoping legend, rules 28, 33, 35 and 48, PDPL P1–P13, the capability matrix (6b ends at 177).
- `1-dashboard.md` v1.5: daily returns (§3.1: site, zone, engagement, shift, headcount), incidents (§3.3) and injury cases, CA source types (§3.8), K-01, warnings E1–E17, AI tools T1–T19, T9/T13, AI-19, charts up to C27, the action panel and expiring-items endpoint, seed W1.
- `2-access-permits.md` v1.4: workers and deployments, gates and gate logs (§3.19, GC-5, GC-12, GC-14), QR tokens (§3.20), devices (GC-1), ops events (§3.17: `aircraft_emergency`, `dust_sandstorm`), P2-8.
- `3-ptw.md` v1.3: crew roles `rescue_lead` / `rescue_member`, documents list D (`rescue_plan`), `emergency_info`, list SR (`emergency`, routine flag), SH-2, SH-3, SH-8, blockers PT-16, K-65, GT-4.
- `4-third-party-cert.md` v1.1: TPI organisations (§3.1–§3.2), equipment items and deployments (§3.4–§3.5), category `tripod_winch` (RESCUE-WINCH-TPI), service status (§4.2), BD-1…BD-7.
- `5-training.md` v1.1: courses FIRE-WARDEN, FIRST-AID (+ FIRST-AID-R), CSE-RESCUE, WAH; matrix roles `fire_warden` / `first_aider` (MR); seed lines MXL-ANIA-EXP-012/013; the training check HK5-6 and the in-force predicate §6.6; §8.5 ("Phase 6 may read Phase 5 records for emergency-team coverage and drills").
- `6a-occupational-health.md` v1.1 (role `oh_practitioner`) and `6b-heat-stress.md` v1.0 (worked-day definition AP-4, format template).
- `docs/DECISIONS.md` #1–#156, in particular #53 (tier-1 trees), #78 (export audit), #124 (no SMS channel), #126 (crew exclusion vs key role).

**Covers (build order):**
1. 6c.1 Emergency response plan (ERP) with scenarios, assembly points, emergency contacts and zone emergency profiles.
2. 6c.2 Emergency organisation: roster (coordinators, fire wardens, first aiders) and coverage per site, shift and zone from Phase 5 records.
3. 6c.3 Rescue teams (confined space, height) and their readiness.
4. 6c.4 Emergency equipment register, periodic checks and service.
5. 6c.5 Drill programme (what is due, when).
6. 6c.6 Drill execution, muster (headcount reconciliation) and evaluation with findings → CAs.
7. 6c.7 Real emergency event log.
8. 6c.8 Phase 3 integration (suspension on alarm, rescue readiness, emergency information).
9. 6c.9 KPIs, warnings, dashboard and AI.

**Not in 6c:**
- The airport emergency plan (AEP) itself and ARFF operations: the airport operator owns them. 6c only records the contractor's interface (contacts, scenario, exercise participation, withdrawal).
- Permanent-works fire alarm and suppression systems under construction or commissioning (handed over through the client's commissioning process). 6c registers only **temporary site** emergency equipment.
- Spill response and spill kits (6e environmental).
- Casualty identity and clinical detail: they stay in Phase 1 injury cases and 6a. 6c stores no health data.
- Mass notification by SMS or sirens through the platform (no SMS channel, DECISIONS #124), and offline muster (§10 Q8).
- Camp and accommodation emergencies (welfare; not proposed).

Conventions: `VERIFY` = clause or number to confirm against the current official text or the client's procedure. `ASSUMPTION` = Consultant default; the HSE Manager may override it (§10). "Must" = enforced server-side. Rule prefixes: ER plan and configuration, EO organisation and coverage, RT rescue teams, EA emergency assets, DP drill programme, DR drills, MU muster, EV events, PE Phase 3 integration, EM KPIs/AI, P6c- PDPL, BD6c boundary. Error codes are stable strings (Phase 0 rule 48). Times are local Asia/Riyadh unless marked UTC.

**The principle that shapes this module:** readiness is shown from evidence, not from documents. A plan counts only if it is approved and current; a first aider counts only if the Phase 5 record is in force **and** the person was on site that shift; an extinguisher counts only if its last check is in date and passed; a drill counts only if it was timed, mustered and evaluated. Missing data never counts as ready.

---

## 1. Purpose

On a 2,900-person airport expansion, the HSE Manager is asked the same questions in every client audit and Civil Defense visit: where is the approved emergency plan and is it current; who are the fire wardens and first aiders on the night shift on the apron, and are their certificates valid; when was the last evacuation drill on Terminal 3, how long did it take, did the headcount reconcile, and were the findings closed; are the extinguishers, first-aid kits, AEDs and eyewash stations checked; and when did the confined-space rescue team last practise. Today the answers sit in contractor spreadsheets, paper drill reports and stickers on extinguishers. The platform already holds the training records (Phase 5), the gate logs (Phase 2), the permits and their rescue plans (Phase 3) and the rescue tripods (Phase 4), but nothing joins them.

Phase 6c provides:
- one approved, versioned ERP per project with scenarios, assembly points, zone emergency profiles and an emergency contact directory (Civil Defense, Red Crescent, police, airport ARFF/AOCC);
- an emergency roster and a coverage engine that counts **qualified and present** first aiders and fire wardens per site, shift and zone against configurable ratios;
- rescue teams with a readiness rule (members qualified, ≥ 1 first aider, drill within 12 months, equipment ready);
- an emergency equipment register with QR stickers, periodic checks, service and expiry dates;
- a drill programme that says what is due and when, and drill records with timings, a muster (headcount reconciliation from gate logs or contractor counts), evaluation criteria and findings that become Phase 1 CAs;
- a real emergency event log with response times, muster, external services and the link to the Phase 1 incident;
- automatic permit suspension on an emergency or drill alarm, rescue-readiness checks on confined-space permits, and pre-filled permit emergency information;
- KPIs K-104…K-109, warnings E18–E19, AI tool T20 and charts C28–C30.

## 2. Regulatory basis

| # | Source | What it drives here |
|---|---|---|
| R1 | **Saudi Civil Defense** regulations and safety requirements for buildings and construction sites (fire prevention, evacuation plans, fire wardens, licensed fire-safety maintenance companies, emergency numbers). `VERIFY` the current instrument names, the drill frequency (commonly cited as at least twice a year) and the warden ratio | ERP approval, drill minimums, service by licensed companies, warden coverage |
| R2 | **SBC 801 (Saudi Fire Code)**, adopted from the IFC: emergency planning and preparedness (fire safety and evacuation plans, evacuation drills, employee training — IFC ch. 4 §401–§406) and fire safety during construction and demolition (IFC ch. 33: fire safety programme superintendent, portable extinguishers on each floor and in sheds, access for fire fighting). `VERIFY` SBC 801 chapter and section numbers against the current edition | Mandatory scenarios, extinguisher minimums per zone, coordinator role, fire-brigade access on airside |
| R3 | **MHRSD OSH Regulations** (employer duty to prepare emergency plans, provide first aid, first-aid boxes and trained persons). `VERIFY` the first-aider and first-aid-box ratio per number of workers | `first_aider_ratio`, first-aid kit minimums |
| R4 | **Saudi Red Crescent Authority (SRCA)** first-aid standards (Phase 5 R8) | FIRST-AID in force = qualified |
| R5 | **ICAO Annex 14 Vol. I §9.1** (aerodrome emergency planning: full-scale exercise at intervals not exceeding 2 years, partial exercises in between, tabletop reviews) and **Doc 9137 Part 7**; **GACAR Part 139** and the airport operator's AEP and Works Safety Plan (contractor participation, ARFF access routes kept clear, withdrawal from the movement area on AOCC instruction). `VERIFY` paragraph numbers and the operator's exercise calendar | Airport scenario `aircraft_emergency`, airport contacts, `airport_exercise` drills, assembly-point siting rule ER-6 |
| R6 | **OSHA 29 CFR 1926.35 / 1910.38** (emergency action plans), **1926.50** (first aid: trained person available when no clinic is reasonably accessible; kits checked before each job and at least weekly), **1926.150 / 1910.157** (extinguishers: monthly visual inspection, annual maintenance), **1910.146(k)(2)(iii)–(iv)** (rescue team: ≥ 1 member with current first aid/CPR; practice at least every 12 months). International benchmark `VERIFY` paragraph letters | Kit check interval 7 days, extinguisher 30 days, `rescue_drill_max_months` 12, RT-2 |
| R7 | **NFPA 10** (portable extinguishers: monthly inspection, annual maintenance, hydrostatic test intervals), **NFPA 72** (alarm testing), **ANSI/ISEA Z358.1** (eyewash: weekly activation, 15 min flow). `VERIFY` editions and intervals | List EAT intervals and check items |
| R8 | **ISO 45001:2018** cl. 8.2 (plan, test and exercise the response, evaluate, revise, communicate), 9.1, 10.2 | Drill evaluation, findings → CAs, ERP review triggers |
| R9 | **Client standards** flowed down (PMC emergency procedure, monthly drill audits; e.g. Saudi Aramco CSM emergency chapter where applicable `VERIFY`) | Tighten-only settings |
| R10 | **PDPL** (roster and muster lists are personal data; location of a person at a time) | P6c rules |

Strictest-wins applied in this spec (and why):
- **Drill frequencies and check intervals only tighten.** The seeded minimums follow Civil Defense, OSHA, NFPA and ANSI; an ERP scenario or a client may set a shorter frequency, never a longer one (ER-5, ER-9).
- **First-aid kits are checked weekly** (OSHA 1926.50(d)(2)), not monthly as many site procedures say.
- **Rescue practice every 12 months** per team (OSHA 1910.146(k)(2)(iv)); from `emergency_ptw_enforcement_from` a confined-space permit cannot start if its rescue team is not current (PE-3).
- **A first aider or warden counts only when qualified and present.** Rostered names without an in-force Phase 5 record, or absent from the gate log that day, do not count (EO-4).
- **A real evacuation does not replace a drill** (DP-6): a drill is planned, observed and evaluated against criteria; an emergency is not ASSUMPTION (§10 Q5).
- **Assembly points never sit in the movement area or an ILS critical/sensitive area** (ER-6): they would obstruct ARFF and aircraft (R5).

## 3. Entities & fields

PDPL column: **none / personal / sensitive** (Phase 0 P1–P2). Every entity carries the Phase 0 system fields, is audited (Phase 0 rule 35) and stores `seed_fake`. AR labels are shown in the UI.

### 3.1 Emergency response plan (per project, revisioned) — خطة الاستجابة للطوارئ

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| erp_no | رقم الخطة | string | sys | `ERP-<project>-r<n>` | ERP-ANIA-EXP-r3 | none |
| project_id | المشروع | FK | Y | one non-superseded Approved revision per project | ANIA-EXP | none |
| title_en / title_ar | العنوان | string(150) ×2 | Y | — | Emergency Response Plan — Terminal & Apron Expansion / خطة الاستجابة للطوارئ | none |
| document_file / document_ref | ملف الخطة / المرجع | file (PDF ≤ 20 MB) / string(40) | Y | the controlled document (client EDMS ref) | ANIA-HSE-ERP-TEST-001 rev C | none |
| site_ids | المواقع المشمولة | FK[] | Y | every active site of the project at approval (ER-3) | [S-AIR, S-LAND] | none |
| scenarios | السيناريوهات | list §3.2 | Y | ER-4 | — | none |
| client_acceptance_ref / accepted_on | مرجع قبول العميل / التاريخ | string(40) / date | cond. | required at approval when `erp_client_acceptance_required` | ANIA-CL-ERP-TEST-03 / 2026-02-12 | none |
| airport_interface_ref | مرجع التنسيق مع خطة طوارئ المطار | string(40) | cond. | required at approval on airport projects (the operator's AEP / WSP reference) | OEXX-AEP-TEST-2026 | none |
| prepared_by / approved_by / approved_at | أعدّها / اعتمدها / تاريخ الاعتماد | FK / FK / timestamptz | sys | approver ≠ preparer; approver holds 180 | Noura / Faisal / 2026-02-15 | personal |
| review_due_on | موعد المراجعة | date | sys | approved_at date + `erp_review_months` − 1 day | 2027-02-14 | none |
| review_required / review_triggers | مطلوب مراجعتها / أسباب المراجعة | bool / list {kind, ref, at} | sys | ER-8 | false | none |
| status | الحالة | enum | Y | §4.1 | approved | none |

### 3.2 ERP scenario — سيناريو الطوارئ

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| scenario_code | رمز السيناريو | string(16) | Y | unique per ERP revision | SC-FIRE | none |
| scenario_type | نوع السيناريو | enum | Y | list ES | fire_explosion | none |
| site_ids | المواقع | FK[] | Y | ⊆ ERP site_ids | [S-AIR, S-LAND] | none |
| alarm_signal_en / _ar | إشارة الإنذار | string(150) | Y | — | Continuous siren + "Evacuate" on radio channel 1 | none |
| response_type | نوع الاستجابة | enum | Y | `zone_evacuation` إخلاء منطقة · `site_evacuation` إخلاء الموقع · `shelter_in_place` الاحتماء في المكان · `local_response` استجابة موضعية | site_evacuation | none |
| response_summary_en / _ar | ملخص الاستجابة | text(2000) | Y (one language) | — | Stop work, make hot work safe, leave by marked routes to the assembly point… | none |
| agencies | الجهات المطلوب إبلاغها | AG code[] | Y | ≥ 1 | [civil_defense, red_crescent, airport_arff] | none |
| drill_type / drill_frequency_months | نوع التمرين / تكراره (أشهر) | DT / int | Y | frequency ≤ the minimum for that type (`DRILL_FREQUENCY_TOO_LOW`, ER-5) | evacuation_full / 6 | none |
| rescue_plan_refs | خطط الإنقاذ المرتبطة | string(40)[] | N | Phase 3 document refs of type `rescue_plan` | [RP-MSCP-02] | none |

### 3.3 Assembly point — نقطة التجمع

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| ap_code | رمز نقطة التجمع | string(16) | Y | unique per project | AP-SLAND-01 | none |
| site_id / zone_id | الموقع / المنطقة | FK / FK | Y / N | zone of the site; ER-6 | S-LAND / Z-LAY1 | none |
| location_en / _ar | الوصف | string(200) | Y | — | North end of laydown yard 1, beside gate L2 | none |
| gps_lat / gps_lng | الإحداثيات | decimal(9,6) | N | KSA bbox (Phase 0 §3.2) | 24.951210, 46.702330 | none |
| capacity_persons | السعة | int | Y | 10–10,000 | 1,500 | none |
| zones_served | المناطق المخدومة | FK[] | Y | ≥ 1 zone of the same site | [Z-PIERB, Z-MSCP, Z-LAY1] | none |
| kind | النوع | enum | Y | `primary` رئيسية · `alternate` بديلة | primary | none |
| sticker_token | رمز QR | string | sys | Phase 2 §3.20 kind `MP` (§11.3); opens the muster screen for that point | HSE2:MP:… | none |
| status | الحالة | enum | Y | `active` · `inactive` | active | none |

### 3.4 Emergency contact — جهات الاتصال في الطوارئ

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| project_id / site_ids | المشروع / المواقع | FK / FK[] | Y / N | empty = whole project | ANIA-EXP / [] | none |
| agency | الجهة | enum | Y | list AG | red_crescent | none |
| display_name_en / _ar | الاسم | string(150) | Y | — | Saudi Red Crescent / هيئة الهلال الأحمر السعودي | none |
| phone | الهاتف | string | Y | E.164, or a KSA short code of 3–4 digits | 997 | none (agency); **personal** for a named person |
| person_name | اسم الشخص | string(120) | N | only for internal roles (coordinator on duty, site clinic nurse); business numbers only | — | personal |
| available_24h / priority | متاح 24 ساعة / الترتيب | bool / int | Y | priority 1–9 within agency | true / 1 | none |
| active | فعّال | bool | Y | — | true | none |

### 3.5 Zone emergency profile (1:1 with zone, optional) — الملف الطارئ للمنطقة

zone_id, eyewash_required (bool; chemical handling, battery charging, concrete admixtures, default false), min_extinguishers (int, default `min_extinguishers_per_zone`), min_first_aid_kits (int, default `min_first_aid_kits_per_zone`), warden_required (bool, default true), notes. Values may only be raised above the project defaults. PDPL: none.

### 3.6 Emergency roster assignment — تكليف في فريق الطوارئ

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| assignment_no | رقم التكليف | string | sys | `EOR-<project>-<nnnnn>` | EOR-ANIA-EXP-00117 | none |
| role | الدور | enum | Y | list EOR | first_aider | personal |
| deployment_id / user_id | العامل / المستخدم | FK / FK | one Y | worker deployment Mobilised on the project (all roles); a user only for `emergency_coordinator` | WKR-000021 @ ANIA-EXP | personal |
| site_id / zone_ids | الموقع / المناطق | FK / FK[] | Y / cond. | site ∈ engagement sites; zone_ids ≥ 1 for `fire_warden` | S-LAND / [Z-MSCP] | personal |
| shift | الوردية | enum | Y | `day` · `night` · `both` | day | personal |
| valid_from / valid_to | من / إلى | date | Y / N | — | 2026-03-01 / — | personal |
| designated_by | كلّفه | FK | sys | capability 181 | Ahmed | personal |
| qualified_today | مؤهل اليوم | derived | — | EO-3 | true | personal |

### 3.7 Rescue team — فريق الإنقاذ

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| team_code | رمز الفريق | string(16) | Y | unique per project | RT-ANIA-CSE-01 | none |
| team_type | النوع | enum | Y | `confined_space` أماكن محصورة · `height` عمل على ارتفاع | confined_space | none |
| site_ids | المواقع | FK[] | Y | — | [S-LAND] | none |
| lead_deployment_id / member_deployment_ids | القائد / الأعضاء | FK / FK[] | Y | Mobilised deployments; lead ∉ members; a deployment in ≤ 1 active team per type | Rafiq Islam / [2 members] | personal |
| equipment | المعدات | {phase4_deployment_ids (category tripod_winch), asset_ids (6c rescue kits)} | cond. | confined_space: ≥ 1 Phase 4 tripod_winch; height: ≥ 1 asset of type `rescue_kit_height` | {[TW-01], []} | none |
| status | الحالة | enum | Y | `active` · `inactive` | active | none |
| readiness | الجاهزية | derived | — | §6.6 (current / not_current + reasons) | current | none |

### 3.8 Emergency asset — معدة طوارئ

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| asset_tag | رقم المعدة | string(20) | Y | `^[A-Z0-9-]{2,20}$`, unique per project | FE-SLAND-0142 | none |
| asset_type / subtype | النوع / النوع الفرعي | enum / enum | Y / cond. | list EAT; subtype required for fire_extinguisher | fire_extinguisher / dcp_abc | none |
| capacity | السعة | string(20) | cond. | extinguishers (kg or L) | 6 kg | none |
| site_id / zone_id / location_en | الموقع / المنطقة / الوصف | FK / FK / string(200) | Y / N / Y | zone of the site | S-LAND / Z-LAY1 / Container office L1-03, door side | none |
| owner_engagement_id | المقاول المسؤول | FK | Y | engagement on the project | RAWABI@ANIA-EXP | none |
| manufactured_year / serial_no | سنة الصنع / الرقم التسلسلي | int / string(40) | cond. / N | extinguishers: year required (hydrostatic test) | 2019 / TEST-FE-55102 | none |
| last_service_on / service_provider_tpi_id / service_ref | آخر صيانة / شركة الصيانة / المرجع | date / FK / string(40) | cond. | types with a service interval (EAT); provider = Phase 4 TPI organisation of kind `fire_protection_service` (§11.5) for fire types | 2025-10-10 / FIRESAFE / FS-TEST-2025-8831 | none |
| hydrotest_due_on | موعد اختبار الضغط | date | sys | §6.5 | 2031-12-31 | none |
| expiries | تواريخ الانتهاء | list {item (pads, battery, eyewash_fluid, kit_contents, other), expires_on} | cond. | AED: pads and battery; portable eyewash: fluid | [{pads, 2026-10-31}] | none |
| sticker_token | رمز QR | string | sys | Phase 2 §3.20 kind `EA` (§11.3) | HSE2:EA:… | none |
| status | الحالة | enum | Y | §4.4 | in_service | none |
| ready | جاهزة | derived | — | §6.5 | true | none |

### 3.9 Asset check — فحص معدة الطوارئ

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| check_no | رقم الفحص | string | sys | `EAC-<project>-<yyyy>-<nnnnnn>` | EAC-ANIA-EXP-2026-018220 | none |
| asset_id | المعدة | FK | Y | asset not retired | FE-SLAND-0142 | none |
| checked_at / checked_by | الوقت / الفاحص | timestamptz / FK | Y / sys | ≤ now; ≥ now − 72 h (`CHECK_BACKDATED`) | 2026-08-31 08:10 / Fahad | personal |
| method | الطريقة | enum | sys | `qr_scan` (sticker scanned) · `manual` | qr_scan | none |
| outcome | النتيجة | enum | Y | `checked` · `missing` مفقودة | checked | none |
| items | البنود | list {item (list EC), answer pass / fail / na} | cond. | outcome checked: every EC item applicable to the type answered | — | none |
| fixed_on_spot | أُصلحت فوراً | bool | N | only for non-critical fails | false | none |
| result | النتيجة النهائية | enum | sys | `pass` · `fail` (any critical fail, or outcome missing) | pass | none |
| photos | الصور | file[] ≤ 3 | N | jpg/png ≤ 5 MB; hint "photograph the equipment, not people" | — | personal (possible) |
| ca_id | الإجراء التصحيحي | FK | sys | EA-4 | — | none |
| status / void_reason | الحالة | enum / text | Y | `valid` · `voided` (190, ≥ 20 chars) | valid | none |

### 3.10 Drill programme line (derived, stored) — بند برنامج التمارين

line_no `DPL-<project>-<nnn>`, drill_type (DT), scope (`site` + site_id · `team` + team_id · `project`), shift_requirement (`any` · `night`), announcement_requirement (`any` · `unannounced`), frequency_months, source (`minimum` · `erp_scenario` · `repeat` + drill_id), due_by (date, §6.3), last_satisfied_by (drill_id), status (`due` · `overdue` · `satisfied` (repeat lines only) · `retired`). Rebuilt by `emergency_daily` and on every drill, ERP or team change. PDPL: none.

### 3.11 Drill — تمرين الطوارئ

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| drill_no | رقم التمرين | string | sys | `DRL-<project>-<yyyy>-<nnn>` | DRL-ANIA-EXP-2026-031 | none |
| drill_type | نوع التمرين | enum | Y | list DT | evacuation_full | none |
| scenario_code | السيناريو | string | Y | a scenario of the Approved ERP | SC-FIRE | none |
| site_id / zone_ids / team_id | الموقع / المناطق / الفريق | FK / FK[] / FK | Y / cond. / cond. | zones required for evacuation_partial; team required for cse_rescue, height_rescue | S-LAND / — / — | none |
| planned_at / shift / announced | الموعد / الوردية / مُعلن | timestamptz / enum / bool | Y | shift `day` · `night` | 2026-09-17 10:00 / day / false | none |
| suspend_permits | إيقاف التصاريح | bool | Y | default true for evacuation and shelter types (PE-2) | true | none |
| conductor_id / evaluator_ids | المنفذ / المقيّمون | FK / FK[] | Y | ≥ 1 evaluator ≠ conductor, holding 186 (DR-3) | Fahad / [Noura] | personal |
| timeline | التوقيتات | {alarm_at, evacuation_complete_at, headcount_complete_at, all_clear_at, first_responder_at, casualty_reached_at, casualty_recovered_at} | cond. | §6.4 order; required per DT (list DT) | alarm 10:00:00, evac 10:08:40, headcount 10:24:10, all clear 10:31:00 | none |
| targets | الأهداف | {evacuation_min, headcount_min, response_min, rescue_min} | sys | copied from settings at start; rescue_min from the rescue plan or `rescue_target_minutes` | {10, 20, —, —} | none |
| muster_id | التجميع | FK | cond. | evacuation and shelter types (MU) | MUS-ANIA-EXP-2026-044 | none |
| external_participation | مشاركة جهات خارجية | list {agency, ref, arrived_at} | N | — | [] | none |
| airport_exercise_ref | مرجع تمرين المطار | string(40) | cond. | airport_exercise only | OEXX-FSX-TEST-2026 | none |
| evaluation | التقييم | {criteria (list DC: pass/fail/na), findings list {category FC, severity, description_en/ar, ca_id}, summary_en/ar ≤ 2000, evaluated_by, evaluated_at} | cond. | DR-5 | — | personal (evaluator) |
| result | النتيجة | enum | sys | `satisfactory` مُرضٍ · `unsatisfactory` غير مُرضٍ (§6.4) | unsatisfactory | none |
| late_entry | إدخال متأخر | bool | sys | started with alarm_at < now − 15 min (DR-4) | false | none |
| status / status_reason | الحالة | enum / text | Y | §4.5 | evaluated | none |

### 3.12 Muster (for a drill or an event) — التجميع والحصر

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| muster_no | رقم التجميع | string | sys | `MUS-<project>-<yyyy>-<nnn>` | MUS-ANIA-EXP-2026-051 | none |
| source | المصدر | {type: drill / event, id} | sys | — | drill DRL-ANIA-EXP-2026-034 | none |
| site_id / ap_ids | الموقع / نقاط التجمع | FK / FK[] | Y | active APs of the site | S-AIR / [AP-SAIR-01] | none |
| mode | الطريقة | enum | sys | `roll` (named, from gate logs) when the site has ≥ 1 active gate, else `count` (MU-1) | roll | none |
| opened_at | وقت البدء | timestamptz | sys | = alarm_at | 2026-09-24 23:00:00 | none |
| expected | المتوقَّعون | roll: list {deployment_id, source gate row}; count: list {engagement_id, expected} | sys / Y | MU-2 / MU-3 | 486 | **personal** (roll) |
| entries | السجلات | list {deployment_id or engagement count, state (list MS), at, by, ap_id, method scan / tick / count, resolution_reason (list UR), note} | sys | MU-4…MU-6 | — | **personal** (roll) |
| visitors_expected / visitors_accounted | الزوار | int / int | N | visitors are not in the platform | 4 / 4 | none |
| headcount_complete_at | اكتمال الحصر | timestamptz | sys | MU-7 | 23:17:30 | none |
| extras | غير مسجلين بالبوابة | int | sys | scanned at the AP but not on the roll (MU-5) | 0 | none |
| status | الحالة | enum | Y | `open` · `reconciled` تمت المطابقة · `closed` | closed | none |

### 3.13 Emergency event (real) — حدث طارئ فعلي

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| event_no | رقم الحدث | string | sys | `EMV-<project>-<yyyy>-<nnn>` | EMV-ANIA-EXP-2026-004 | none |
| event_type | النوع | enum | Y | list ES ∪ {`false_alarm` إنذار كاذب, `airport_aep_activation` تفعيل خطة طوارئ المطار} | medical_emergency | none |
| site_id / zone_ids / location_en | الموقع / المناطق / الوصف | FK / FK[] / string(200) | Y / Y / N | — | S-AIR / [Z-APR-21] / Stand 24 | none |
| raised_at / declared_by | وقت الإبلاغ / المُبلّغ | timestamptz / FK | Y / sys | ≤ now; ≥ now − 24 h | 2026-09-22 13:52 / Omar | personal |
| response_type | نوع الاستجابة | enum | Y | as §3.2 plus `none` | local_response | none |
| muster_id | التجميع | FK | cond. | zone or site evacuation, shelter in place (EV-3) | — | none |
| first_responder_at | وصول المسعف الأول | timestamptz | cond. | medical_emergency, confined_space_rescue, height_rescue | 13:55 | none |
| external_services | الجهات الخارجية | list {agency, called_at, arrived_at, reference} | N | arrived ≥ called ≥ raised | [{red_crescent, 13:56, 14:09, SRCA-TEST-2209}] | none |
| casualties_count | عدد المصابين | int | Y | 0–500; no names, no clinical text here (P6c-3) | 1 | none |
| incident_id | الحادثة | FK | cond. | EV-4 | INC-ANIA-EXP-2026-0402 (W1 #4) | none |
| ops_event_id | الحدث التشغيلي | FK | cond. | airport_aep_activation created from a Phase 2 ops event (EV-6) | — | none |
| all_clear_at / all_clear_by | انتهاء الحالة | timestamptz / FK | cond. | capability 188 | 14:20 / Omar | personal |
| review | المراجعة | {what_worked, issues (≤ 2,000 each), erp_update_needed (bool), ca_ids, reviewed_by, reviewed_at} | cond. | EV-5; P1-8 ID scan | — | personal (reviewer) |
| status | الحالة | enum | Y | §4.6 | reviewed | none |

### 3.14 Reference lists (seeded EN/AR; codes immutable)

**ES — scenarios (mandatory ★, ER-4):** `fire_explosion` ★ حريق/انفجار · `medical_emergency` ★ حالة طبية طارئة · `severe_weather` ★ طقس شديد (sandstorm, thunderstorm, flash flood) · `confined_space_rescue` ★ إنقاذ من مكان محصور · `height_rescue` ★ إنقاذ من ارتفاع (suspended worker) · `structural_collapse` انهيار إنشائي · `excavation_collapse` انهيار حفرية · `gas_release` تسرب غاز (H₂S, LPG, utility gas) · `electrical_contact` صعق كهربائي · `utility_strike` إصابة خدمات مدفونة · `security_threat` تهديد أمني · `aircraft_emergency` ★ (airport projects only) طوارئ طائرة.

**DT — drill types** (minimum frequency, months · scope · timings required): `evacuation_full` إخلاء كامل للموقع (6 · site · alarm, evacuation, headcount, all clear) · `evacuation_partial` إخلاء جزئي (— · zones · same) · `shelter_in_place` احتماء في المكان (12 ASSUMPTION · site · alarm, headcount, all clear) · `medical_response` استجابة طبية (6 · site · alarm, first responder, all clear) · `cse_rescue` إنقاذ من مكان محصور (12 · team · alarm, casualty reached, casualty recovered) · `height_rescue` إنقاذ من ارتفاع (12 ASSUMPTION · team · same) · `tabletop` تمرين مكتبي (12 · project · none) · `airport_exercise` تمرين المطار (12 ASSUMPTION · project, airport only · alarm, all clear). Minimums also apply per site with night work: `evacuation_full` with shift night every 12 months; and `evacuation_full` unannounced every 12 months (ASSUMPTION). Frequencies `VERIFY` R1, R5, R6.

**AG — agencies** (seeded default contacts; numbers `VERIFY` per region): `civil_defense` الدفاع المدني (998) · `red_crescent` الهلال الأحمر (997) · `police` الشرطة (999) · `unified_911` الرقم الموحد (911, where the unified centre operates) · `airport_arff` إنقاذ ومكافحة حرائق الطائرات · `airport_aocc` مركز عمليات المطار · `airport_security` أمن المطار · `site_clinic` عيادة الموقع · `hospital` المستشفى · `client_emergency` طوارئ العميل · `electricity_utility` شركة الكهرباء (933) · `water_utility` شركة المياه (939) · `other`.

**EOR — emergency roles:** `emergency_coordinator` منسق الطوارئ (incident controller; per site and shift) · `fire_warden` مسؤول إخلاء/حريق (Phase 5 FIRE-WARDEN) · `first_aider` مسعف أولي (Phase 5 FIRST-AID or FIRST-AID-R) · `assembly_marshal` مسؤول نقطة التجمع (no training code ASSUMPTION).

**EAT — emergency asset types** (check interval days · service · critical check items): `fire_extinguisher` طفاية حريق, subtypes `dcp_abc`, `co2`, `foam`, `water`, `wet_chemical`, `clean_agent` (30 · annual service 12 months by a `fire_protection_service` provider; hydrostatic test 5 years for co2/water/foam, 12 years for dcp/clean agent `VERIFY` R7) · `fire_blanket` بطانية حريق (30) · `hose_reel` بكرة خرطوم (30 · 12) · `alarm_call_point` نقطة إنذار يدوية (7) · `alarm_panel_temporary` لوحة إنذار مؤقتة (7 · 12) · `siren_air_horn` صافرة إنذار (7) · `emergency_lighting` إنارة طوارئ (30 · 12) · `first_aid_kit` حقيبة إسعافات أولية (7) · `first_aid_room` غرفة إسعاف (30) · `aed` جهاز إزالة الرجفان (30; expiries pads, battery) · `eyewash_plumbed` محطة غسيل العين الثابتة (7) · `eyewash_portable` محطة غسيل العين المتنقلة (30; expiry fluid) · `safety_shower` دش الطوارئ (7) · `stretcher` نقالة (30) · `rescue_kit_height` حقيبة إنقاذ من ارتفاع (30 · 12, competent-person inspection) · `escape_breathing_set` جهاز تنفس للهروب (30 · 12). Intervals `VERIFY` R6–R7; settings may only shorten them.

**EC — check items** (★ critical; each type answers the items marked for it in the seed list): EC01 ★ present at the marked location and unobstructed · EC02 signage visible · EC03 ★ seal and tamper indicator intact, gauge in the operable range (extinguishers) · EC04 ★ no damage, corrosion or leakage · EC05 ★ contents complete and in date (kits, first-aid room, rescue kit) · EC06 ★ status indicator OK, pads and battery in date (AED) · EC07 ★ activated, flow clear and adequate (eyewash, shower) · EC08 ★ tested and working (alarm, siren, lighting) · EC09 inspection tag dated and signed · EC10 access path clear and lit.

**DC — drill evaluation criteria** (★ critical; n.a. where not relevant to the drill type): DC01 ★ alarm heard/seen in every zone · DC02 ★ wardens swept their zones and reported clear · DC03 escape routes clear and signed · DC04 ★ hot work, plant and lifting made safe; permits suspended · DC05 workers went to the correct assembly point · DC06 assembly-point signage and capacity adequate · DC07 headcount method worked (scan, list, count) · DC08 emergency call made or simulated with correct information · DC09 ★ first responder arrived with kit (and AED where available) · DC10 ★ rescue equipment available, serviceable and used correctly · DC11 ★ airside: movement area left as instructed and ARFF routes kept clear (airport) · DC12 visitors and persons needing help were assisted.

**FC — finding categories:** `plan_deficiency` خلل في الخطة (sets ERP review_required, ER-8) · `training_competence` · `equipment` · `communication` · `route_infrastructure` · `behaviour` · `external_coordination`. Severity: `critical` (life at risk in a real event) · `major` · `minor`.

**MS — muster entry states:** `expected` · `accounted` حاضر · `unaccounted` غير محصور · `resolved` تمت التسوية. **UR — resolution reasons:** `left_site_no_exit_scan` غادر دون تسجيل خروج · `off_site_confirmed` خارج الموقع (مؤكد) · `found_on_site` وُجد داخل الموقع (finding, MU-6) · `with_emergency_team` مع فريق الطوارئ · `record_error` خطأ في السجل.

### 3.15 Phase 6c project settings
Only the HSE Manager edits them (capability 180); every change is audited; "Allowed" is the only range accepted.

| Key | AR label | Type | Default | Allowed |
|---|---|---|---|---|
| emergency_register_from | بدء العمل بسجل الطوارئ | date / null | null | ≥ project start; ≤ today; only moves earlier |
| emergency_ptw_enforcement_from | بدء ربط الجاهزية بالتصاريح | date / null | null | ≥ emergency_register_from; needs an Approved ERP (ER-2) |
| erp_review_months | مدة مراجعة الخطة | int | 12 ASSUMPTION | 3–12 |
| erp_client_acceptance_required | اشتراط قبول العميل | bool | true on airport projects, else false | false → true only |
| first_aider_ratio / warden_ratio | نسبة المسعفين / مسؤولي الإخلاء | int / int | 50 / 50 ASSUMPTION `VERIFY` R1, R3 | 10–50 each (only lower) |
| coordinator_required_per_shift | اشتراط منسق لكل وردية | bool | true | false → true only |
| shift_start_times | بداية الورديات | {day, night} | {06:00, 18:00} | any |
| coverage_check_offset_minutes | مهلة فحص التغطية | int | 60 | 30–120 |
| drill_minimums | الحد الأدنى لتكرار التمارين | map DT → months | list DT | each value may only fall |
| first_drill_grace_days | مهلة أول تمرين | int | 30 ASSUMPTION | 0–60 |
| repeat_drill_days | مهلة إعادة التمرين غير المرضي | int | 30 ASSUMPTION | 7–30 |
| evacuation_target_minutes / headcount_target_minutes | هدف زمن الإخلاء / الحصر | int / int | 10 / 20 ASSUMPTION | 3–15 / 5–30 |
| response_target_minutes | هدف وصول المسعف الأول | int | 4 (R6, 1926.50(c)) | 2–4 |
| rescue_target_minutes | هدف زمن الإنقاذ الافتراضي | {confined_space, height} | {15, 10} ASSUMPTION `VERIFY` | 5–30 each; only lower |
| drill_evaluation_days / event_review_days | مهلة تقييم التمرين / مراجعة الحدث | int / int | 3 / 7 | 1–7 / 1–14 |
| muster_roll_window_hours | نافذة سجل البوابات للحصر | int | 16 | 12–24 |
| asset_check_intervals | فترات فحص المعدات | map EAT → days | list EAT | each value may only fall |
| min_extinguishers_per_zone / min_first_aid_kits_per_zone | الحد الأدنى للطفايات / الحقائب لكل منطقة | int / int | 2 / 1 ASSUMPTION | 1–20 / 1–10 (only raise) |
| min_aed_per_site | الحد الأدنى لأجهزة الرجفان لكل موقع | int | 1 ASSUMPTION | 0–10 (only raise) |
| rescue_team_min_members | الحد الأدنى لأعضاء فريق الإنقاذ | {confined_space, height} | {3, 2} incl. lead ASSUMPTION | 2–8 (only raise) |
| drill_compliance_warning_pct / coverage_warning_pct / equipment_readiness_warning_pct | حدود الإنذار | decimal ×3 | 90.0 / 95.0 / 95.0 ASSUMPTION | 80.0–100.0 |
| muster_detail_retention_months / emergency_record_retention_years | الاحتفاظ بأسماء الحصر / بالسجلات | int / int | 12 / 5 ASSUMPTION | 3–24 / 2–10 |

## 4. Workflow / states

"Who" = capability numbers (§5.13). Jobs: `emergency_minute` (every 60 s: muster timers, headcount-target alerts, coverage checks at shift start + offset), `emergency_daily` 00:08:00 (programme lines, asset readiness, expiries, team readiness, yesterday's coverage; after `heat_daily`), `emergency_alerts` 07:05.

### 4.1 ERP revision
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Draft | مسودة | 179 | new revision (copy of the current one) |
| Draft → Submitted | مقدمة | 179 | — |
| Submitted → Draft | مسودة | 180 | returned with reason ≥ 20 chars |
| Submitted → Approved | معتمدة | 180 | ER-3 completeness passes; approver ≠ preparer (`SOD_CONFLICT`) |
| Approved → Superseded | ملغاة بإصدار أحدث | System | the next revision is Approved |

### 4.2 Roster assignment and rescue team
Assignment: Active (valid_from ≤ today ≤ valid_to) → Ended (valid_to set by 181, or System at demobilisation `demobilised`). Rescue team: Active ⇄ Inactive (181).

### 4.3 Assembly point and contact
Active ⇄ Inactive (179). Deactivating the last AP serving a zone is refused while the zone is active (`ZONE_WITHOUT_ASSEMBLY_POINT`).

### 4.4 Emergency asset
| From → To | AR | Who | Trigger |
|---|---|---|---|
| — → In Service | في الخدمة | 182 | registered |
| In Service → Out of Service | خارج الخدمة | System (check result fail, EA-4); 183 (tag out with reason) | — |
| In Service → Missing | مفقودة | System | check outcome `missing` |
| Out of Service / Missing → In Service | في الخدمة | 182 | a new check with result pass |
| any → Retired | مستبعدة | 182 | replaced, discharged, condemned (reason); terminal; sticker token revoked |

### 4.5 Drill
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Planned | مخطط | 184 | DR-1 |
| Planned → In Progress | جارٍ | 185 | "Start" sets alarm_at = now (or a past time → late entry, DR-4); opens the muster; PE-2 suspensions |
| In Progress → Conducted | منفّذ | 185 | all_clear_at and the timings required by DT; muster Reconciled (or count rows complete) |
| Conducted → Evaluated | مقيَّم | 186 | DR-5 evaluation; result computed (§6.4) |
| Planned → Cancelled | ملغى | 184 | reason ≥ 20 chars |
| In Progress / Conducted / Evaluated → Voided | ملغى (باطل) | 190 | reason ≥ 20 chars; leaves KPIs and programme; CAs already created stay open |

### 4.6 Emergency event
Active (declared) → All Clear (188) → Reviewed (188 with the review, EV-5). Active / All Clear → Voided (190; declared in error, reason ≥ 20 chars; a false alarm is a type, not a void).

### 4.7 Muster
Open (at alarm) → Reconciled (system, MU-7) → Closed (system at all clear). An Open muster at all clear is closed with the unaccounted entries left `unaccounted` (finding, MU-8).

## 5. Business rules

### 5.1 Plan and configuration (ER)
- ER-1. 6c runs on a project from `emergency_register_from`. Before it, no 6c requirement applies, 6c KPIs show "—" and Phase 3 is unchanged.
- ER-2. `emergency_ptw_enforcement_from` can be set only while an Approved, non-overdue ERP exists (`ERP_NOT_APPROVED`).
- ER-3. **Approval completeness** (each failure → 422 `ERP_INCOMPLETE` with the list in meta): every active site of the project is in site_ids; every active zone is served by ≥ 1 active assembly point; every mandatory scenario (list ES ★, `aircraft_emergency` only on airport projects) exists and covers every site it applies to; contacts include `civil_defense`, `red_crescent` and `police` (or `unified_911`), plus `airport_arff` and `airport_aocc` on airport projects, and a `site_clinic` or `hospital`; client acceptance and airport interface refs per §3.1.
- ER-4. Scenario `confined_space_rescue` and `height_rescue` each name ≥ 1 rescue plan ref or state "no such work" in the response summary (`RESCUE_PLAN_REF_REQUIRED` when the project has an Issued or Active permit of that type in the last 90 days).
- ER-5. A scenario's drill frequency may only be equal to or shorter than `drill_minimums` for its drill type (`DRILL_FREQUENCY_TOO_LOW`).
- ER-6. An assembly point's zone may not have `in_movement_area` = true or `airside_area` ∈ {ils_critical, ils_sensitive} (`ASSEMBLY_POINT_IN_RESTRICTED_AREA`, R5). `zones_served` must be zones of the AP's site.
- ER-7. **Review due:** review_due_on per §3.1. From the day after it, the ERP is **overdue**: action panel item, alerts (§7), and E18 input. An overdue ERP stays the plan in force (never "no plan").
- ER-8. **Review triggers** set review_required = true (action panel, alert to the HSE Manager): a drill finding with category `plan_deficiency`; an event review with erp_update_needed; a new active site or zone not covered; a zone without an AP. Approving a new revision clears it.
- ER-9. Settings in §3.15 marked "only fall / only raise / only lower" refuse a loosening value with `SETTING_LOOSENING`.

### 5.2 Organisation and coverage (EO)
- EO-1. Roster assignments are created by 181: Contractor HSE Reps for deployments in their C scope; HSE staff and site engineers for any. A fire_warden needs ≥ 1 zone of the site.
- EO-2. Creating a `fire_warden` or `first_aider` assignment adds the Phase 5 matrix role (MR) to the worker's training profile if missing (audited `matrix_role_added_by_6c`), so the Phase 5 matrix lines MXL-…-012/013 apply. Ending an assignment never removes the matrix role.
- EO-3. **Qualified** on date d = the Phase 5 training check (HK5-6) at d returns `met` or `expiring` for: fire_warden → FIRE-WARDEN; first_aider → FIRST-AID; rescue team members → CSE-RESCUE (confined_space) or WAH-RESCUE (height, §11.6). Coordinators and marshals need no code. 6c calls the check directly; it registers no hook kind.
- EO-4. **Present** on date d, shift s = the deployment has a worked day on d (6b AP-4: gate `in` GRANTED / GRANTED_WITH_WARNING or admitted_despite_denial on a gate of the site) when the site has ≥ 1 active gate; on a site without gates, every rostered assignment counts as present ASSUMPTION (§10 Q3).
- EO-5. **Coverage per site, shift and date** (§6.2): required counts come from the Phase 1 daily returns (Submitted or later) of that site, date and shift; a return with shift `all` counts in `day`. A site-shift-day with headcount 0 is not required.
- EO-6. A site-shift-day is **covered** when, for that shift: qualified present first aiders ≥ required; qualified present wardens ≥ required; every zone with work (§6.2) has ≥ 1 qualified present warden assigned to it; and, when `coordinator_required_per_shift`, ≥ 1 coordinator is rostered.
- EO-7. **Live coverage** (board): at shift start + `coverage_check_offset_minutes`, the job evaluates the current shift with headcount = the live on-site roll (MU-2 definition, site gates) or, on a site without gates, the mean headcount of the same shift over the last 7 days with returns. A shortfall alerts the site engineers, the Contractor HSE Reps of engagements on the site and the HSE Officers once per site-shift-day.

### 5.3 Rescue teams (RT)
- RT-1. A team has a lead and members (deployments Mobilised on the project); total ≥ `rescue_team_min_members` for its type; a deployment is in at most one active team per type (`ALREADY_IN_TEAM`).
- RT-2. **Current** at date d ⇔ (a) ≥ `rescue_team_min_members` of lead+members qualified (EO-3); (b) ≥ 1 of them holds FIRST-AID in force (R6, 1910.146(k)(2)(iii)); (c) an Evaluated drill of the team's type (cse_rescue / height_rescue) with this team has conducted date ≥ add_months(d, −12) + 1 day (§6.3); (d) every linked equipment is ready: Phase 4 tripod_winch items In Service, 6c assets ready (§6.5). The readiness shows each failing reason code: `TEAM_UNDERSTRENGTH`, `NO_FIRST_AIDER`, `RESCUE_DRILL_OVERDUE`, `RESCUE_EQUIPMENT_NOT_READY`.
- RT-3. A Phase 3 permit's `rescue_lead` belongs to the active team in which that deployment is lead or member, of the matching type (confined_space for CSE permits). PE-3 uses it.

### 5.4 Emergency equipment (EA)
- EA-1. Assets are registered by 182 with a sticker (QR kind `EA`). Fire extinguishers, hose reels, temporary alarm panels and emergency lighting require last_service_on; fire types name a service provider of kind `fire_protection_service` (Phase 4 TPI register, §11.5) when serviced by a third party.
- EA-2. A check (183) is recorded by scanning the sticker (`qr_scan`) or by choosing the asset (`manual`); a manual check by anyone except HSE staff shows warning `CHECK_WITHOUT_SCAN` and is flagged in the register ASSUMPTION. Backdating is limited to 72 h (`CHECK_BACKDATED`).
- EA-3. Result = `fail` when any critical item fails or the outcome is `missing`. A non-critical fail with fixed_on_spot = true keeps `pass`.
- EA-4. A failed check sets the asset Out of Service (or Missing) within 60 s and creates one Phase 1 CA (source_type `emergency`, priority high, due checked_at + 24 h ASSUMPTION, responsible = owner engagement) and alerts the site engineer, the owner's Contractor HSE Rep and the HSE Officer. An asset that is in a rescue team's equipment makes the team not current (RT-2d).
- EA-5. **Ready** (§6.5) is computed daily and on every check, service or expiry edit. Not ready reasons: `CHECK_OVERDUE`, `LAST_CHECK_FAILED`, `OUT_OF_SERVICE`, `MISSING`, `SERVICE_OVERDUE`, `HYDROTEST_OVERDUE`, `CONSUMABLE_EXPIRED`.
- EA-6. **Provision gaps:** a zone with work today whose ready extinguishers < its minimum, whose ready first-aid kits < its minimum, or with eyewash_required and no ready eyewash; a site with fewer ready AEDs than `min_aed_per_site`. Gaps appear on the board and the action panel; they do not block.
- EA-7. Equipment on Phase 4 items (e.g. the plant extinguisher of AIC-07) is not registered again in 6c (BD6c-3).

### 5.5 Drill programme (DP)
- DP-1. Programme lines (§3.10) are generated from: (a) `drill_minimums` per site (evacuation_full; evacuation_full night for each site with a night-shift return in the last 90 days; evacuation_full unannounced; medical_response; shelter_in_place only if a scenario uses it), per team (cse_rescue, height_rescue), per project (tabletop; airport_exercise on airport projects); (b) each scenario of the Approved ERP whose frequency is shorter than the minimum (the shorter wins); (c) repeat lines (DR-7).
- DP-2. A drill **satisfies** a line when it is Conducted or Evaluated (not Voided), of the same drill type and scope (site, team or project), conducted on a night shift for night lines and unannounced for unannounced lines. One drill may satisfy several lines (an unannounced night full evacuation satisfies three). `evacuation_partial` never satisfies an `evacuation_full` line.
- DP-3. **due_by** (§6.3) = add_months(conducted date of the last satisfying drill, frequency) − 1 day; with no satisfying drill, the line start (the later of `emergency_register_from`, the site's first day with work, the team's creation) + `first_drill_grace_days`.
- DP-4. A line is overdue from the day after due_by. Alerts at 30 / 14 / 7 / 0 days before due_by to the HSE Officers and the site engineers of the site (team lines: the team lead's Contractor HSE Rep too), and at overdue.
- DP-5. **K-104 items:** each (line, due_by) with due_by in the period and ≤ today is one item; it is **met on time** when a satisfying drill was conducted on or before due_by.
- DP-6. A real emergency event never satisfies a programme line (ASSUMPTION, §10 Q5).

### 5.6 Drills (DR)
- DR-1. A drill is planned by 184 for a scenario of the Approved ERP; planned_at ≥ now for unannounced drills. On airport projects, an `evacuation_full` or `evacuation_partial` drill on an airside site requires an airport coordination ref in the plan note (AOCC informed) ASSUMPTION `VERIFY` R5.
- DR-2. **Unannounced drills** are visible before alarm_at only to holders of 184 for that site and to the HSE Manager; others see nothing until it starts (the API omits the drill).
- DR-3. ≥ 1 evaluator ≠ conductor (`SOD_CONFLICT`); evaluators hold 186.
- DR-4. **Start:** Planned → In Progress sets alarm_at. A drill started with alarm_at more than 15 min in the past is a late entry: no permit suspensions, no live alerts, muster in `count` mode only.
- DR-5. **Timings:** order alarm_at ≤ evacuation_complete_at ≤ all_clear_at; alarm_at ≤ headcount_complete_at ≤ all_clear_at; alarm_at ≤ first_responder_at; alarm_at ≤ casualty_reached_at ≤ casualty_recovered_at (`TIMELINE_ORDER`). headcount_complete_at is set by the muster (MU-7), not typed.
- DR-6. **Evaluation** by an evaluator within `drill_evaluation_days` of Conducted: every DC criterion relevant to the type answered; a fail on a critical criterion creates a finding of severity critical automatically; each finding of severity critical or major creates one Phase 1 CA (source_type `emergency`, priority critical → `critical`, major → `high`, responsible = the engagement named on the finding or the site's tier-1 engagement); a minor finding creates a CA only when the evaluator asks. Overdue evaluations alert the HSE Officer, then the HSE Manager after 2 more days.
- DR-7. **Result** (§6.4): unsatisfactory creates a repeat line (same type and scope) due conducted date + `repeat_drill_days`; it is satisfied by the next satisfying drill.
- DR-8. Rescue drills record the team, the rescue plan ref used (Phase 3 document ref, optional) and the casualty timings; equipment of the team not ready at alarm_at is a major finding `equipment` automatically.
- DR-9. `airport_exercise` records the contractor's participation in the airport operator's exercise (operator ref required); timings alarm and all clear only; DC11 is mandatory.

### 5.7 Muster (MU)
- MU-1. A muster opens with the drill or event when response_type is zone or site evacuation or shelter in place. Mode `roll` when the site has ≥ 1 active gate, else `count`.
- MU-2. **Roll (expected list)** at opened_at = deployments whose latest gate-log row at a gate of the site within the last `muster_roll_window_hours` has direction `in` and result GRANTED / GRANTED_WITH_WARNING or admitted_despite_denial = true. For a zone evacuation, the roll is limited to rows whose target zone is an evacuated zone. Exits after opened_at mark the entry `accounted` with method `exit_scan`.
- MU-3. **Count mode:** each engagement on the site enters expected and accounted counts (Contractor HSE Rep or receiver C1, or HSE staff); resolutions are entered as counts with a UR reason.
- MU-4. Accounting: a scan of the worker's access card QR (Phase 2 kind `AC`) at the AP by a `muster_reader` device bound to that AP (§11.3) or by a user with 185, or a tick on the roll by 185. A scan never creates a gate-log row and never runs the access eligibility check.
- MU-5. A scanned worker who is not on the roll is added as `accounted` and counted in `extras` (shows entry without a gate scan; a finding `behaviour` is proposed to the evaluator).
- MU-6. Each unaccounted entry is resolved by 185 with a UR reason (note ≥ 10 chars for `record_error`). `found_on_site` in a drill creates a critical finding automatically ("person remained in the evacuated area"); in a real event it alerts the HSE Manager at once.
- MU-7. headcount_complete_at = the time at which every expected entry (and every count row) is accounted or resolved; the muster becomes Reconciled.
- MU-8. At opened_at + `headcount_target_minutes` with unaccounted entries: for an event, an immediate alert "N persons unaccounted at <AP> — start search / يوجد N أشخاص غير محصورين" to the HSE Manager, HSE Officers, site engineers of the site and the emergency coordinators on the roster (in-app + push + email); for a drill, an in-app alert to the conductor and evaluators.
- MU-9. A printable muster sheet (per engagement, names and worker_no only) can be generated for an Open muster by 185 as the paper fallback (online-only platform); each print is audited (`export`).

### 5.8 Events (EV)
- EV-1. Any holder of 187 declares an event; raised_at may be back-dated up to 24 h (then it is a late entry: no suspensions, no live alerts).
- EV-2. On declaration (live): alert within 60 s to the HSE Manager, HSE Officers, site engineers of the site, Contractor HSE Reps of engagements on the site, and the emergency coordinators rostered for the site and current shift (in-app + push + email). The alert shows type, site, zones, response type and the AP; never a casualty's name.
- EV-3. A zone or site evacuation or shelter in place opens a muster (MU-1) and triggers PE-1 permit suspensions.
- EV-4. **Incident link:** types fire_explosion, medical_emergency, structural_collapse, excavation_collapse, gas_release, electrical_contact, utility_strike, confined_space_rescue and height_rescue need a Phase 1 incident before the event can be Reviewed (`INCIDENT_LINK_REQUIRED`); false_alarm, severe_weather, security_threat, aircraft_emergency and airport_aep_activation need none (optional link).
- EV-5. **Review** by 188 within `event_review_days` of All Clear: what worked, issues, erp_update_needed (ER-8), CAs (Phase 1 source `emergency`). Overdue reviews alert the HSE Officer, then the HSE Manager.
- EV-6. A Phase 2 ops event of type `aircraft_emergency` creates a 6c event `airport_aep_activation` (Active, zones = the ops event zones, response_type `zone_evacuation` when any zone is in the movement area, else `none`, source link) ASSUMPTION; its end sets All Clear. Phase 2 suspensions are unchanged.
- EV-7. Response times (§6.7) are computed from the timeline; missing times are shown "—", never estimated.

### 5.9 Phase 3 integration (PE)
- PE-1. **Event suspension (live):** an Active event with zone or site evacuation or shelter in place suspends within 60 s every Issued or Active permit whose zones intersect the evacuated zones (site evacuation: every zone of the site) with the existing reason `emergency` (non-routine; resume per SH-3 by the issuer, after All Clear).
- PE-2. **Drill suspension:** at Start of a drill with suspend_permits = true (not late), the same permits are suspended with new reason `emergency_drill` (routine, excluded from K-65, §11.4). After the drill is Conducted, the receiver may resume (no issuer cause text) once the Issue-time blockers are empty, with the GT-4 post-break test where gas testing applies.
- PE-3. **Rescue readiness (from `emergency_ptw_enforcement_from`):** at Start, Revalidate, Resume and handover acceptance of a `confined_space` permit: the named rescue_lead is in no active confined_space team → blocker `RESCUE_TEAM_NOT_REGISTERED`; the team is not current (RT-2) → blocker `RESCUE_DRILL_OVERDUE` (meta: the RT-2 reason codes, e.g. `TEAM_UNDERSTRENGTH`). An Active permit whose team stops being current is **not** suspended automatically; it gets the warning at the next shift and the action panel lists it ASSUMPTION (§10 Q6).
- PE-4. Permits with a `work_at_height` section and fall-arrest crew get warning `HEIGHT_RESCUE_NOT_READY` at Start when no current `height` team covers the permit's site (never a blocker in v1.0).
- PE-5. A `hot_work` permit gets warning `NO_READY_EXTINGUISHER` at Start when the permit's zone has no ready fire extinguisher (EA-5).
- PE-6. The permit's `emergency_info` is pre-filled at Request with the primary AP of its first zone and the site's priority-1 numbers (internal emergency, civil_defense, red_crescent; airside: airport_arff); the requester may edit it.

### 5.10 KPIs and AI (EM)
- EM-1. All 6c KPIs are computed by the backend. KPI scope: project, site (and tier-1 tree for E18–E19 only, as DECISIONS #53).
- EM-2. AI tool **T20 `get_emergency_kpis`** (project_ids, period, filters {site, drill_type, asset_type, event_type, role}, metrics K-104…K-109, group_by {site, month, drill_type, asset_type, event_type, role, shift}) returns aggregates only: no names, worker_no, muster entries, evaluator names or free texts. T13 returns E18–E19. AI-19 gains a section "Emergency preparedness".
- EM-3. K-109 counts follow the Phase 1 small-cell rule only when grouped by contractor (events are site-level; casualty data is never returned).

### 5.11 PDPL (P6c-x)
- P6c-1. **Personal:** roster assignments, rescue team membership, named contacts, muster roll entries (a person's presence at a place and time), declarer, evaluator and checker identities, photos. **None:** ERP, scenarios, APs, assets, programme, drill timings and results, event timelines and counts. **Sensitive:** none — 6c stores no health data (P6c-3).
- P6c-2. Roster names and named emergency contacts are visible to every project user with 178, because people must know who their warden and first aider are (purpose: life safety; shown on the board and the printable poster). Phone numbers of named persons are business numbers only (UI hint).
- P6c-3. Events store casualty counts only; identity and clinical detail stay in the Phase 1 injury case under Phase 1 permissions. Free texts get the Phase 1 P1-8 ID scan and the hint "no names or medical details".
- P6c-4. Muster roll entries are visible to 185 holders in their scope during the muster and to 178 holders with HSE roles afterwards; Contractor HSE Reps and receivers see only their C / C1 scope; viewers never. Every read of a named roll after Closed writes `sensitive_field_read` ASSUMPTION. After `muster_detail_retention_months` the named entries are reduced to counts by state and reason (`retention_purge`).
- P6c-5. Gate logs are read for musters only (life safety, an HSE purpose under P2-8); muster data is never exposed through attendance or time reports.
- P6c-6. Drill, check and event records are kept `emergency_record_retention_years`; ERP revisions for the project life plus that period; photos 24 months.

### 5.12 Phase-boundary rules (BD6c)
- BD6c-1. 6c owns no hook kind. It reads Phase 1 daily returns and incidents, Phase 2 deployments, gates and gate logs, Phase 3 permits and documents, Phase 4 tripod_winch items, Phase 5 records through the training check. It writes Phase 1 CAs (source `emergency`), Phase 5 matrix roles (EO-2) and, through §11.4, Phase 3 suspensions, blockers and warnings.
- BD6c-2. Training validity, refreshers and expiry alerts for FIRE-WARDEN, FIRST-AID, CSE-RESCUE and WAH-RESCUE stay in Phase 5; 6c only shows their effect on coverage and team readiness.
- BD6c-3. Fire extinguishers, first-aid kits and other emergency assets are **not** Phase 4 equipment items (no TPI certificate, no hook, not in K-72/K-74). Rescue tripods/winches stay Phase 4 items, read by 6c.

### 5.13 Permission matrix — Phase 6c extension
Continues 6b §5.13. Legend A/P/S/C/C1/R/—.

| # | Capability | HSE Mgr | HSE Officer | Site Eng/Sup | Permit Issuer | Permit Receiver | Contractor HSE Rep | Viewer/Client | OH Pract. |
|---|---|---|---|---|---|---|---|---|---|
| 178 | View ERP, scenarios, APs, contacts, roster, rescue teams, assets, programme, drills (DR-2), events, coverage board | A | P | S | S | C1 | C | P (R) | P |
| 179 | Prepare ERP drafts, scenarios, APs, contacts, zone emergency profiles; submit | A | P | — | — | — | — | — | — |
| 180 | Approve ERP; edit 6c settings; set enforcement | A | — | — | — | — | — | — | — |
| 181 | Manage roster assignments and rescue teams | A | P | S | — | — | C | — | — |
| 182 | Register / edit / retire assets; service records; stickers | A | P | S | — | — | C | — | — |
| 183 | Record asset checks; tag out an asset | A | P | S | S | C1 | C | — | — |
| 184 | Plan / cancel drills; see unannounced drills before start | A | P | S | — | — | — | — | — |
| 185 | Start a drill, record timings, run the muster (scan, tick, resolve, print sheet) | A | P | S | S | C1 | C | — | — |
| 186 | Evaluate drills and record findings | A | P | S | — | — | — | — | — |
| 187 | Declare an emergency event; record timeline and external calls | A | P | S | S | C1 | C | — | P |
| 188 | Declare All Clear; review events | A | P | S (All Clear only) | — | — | — | — | — |
| 189 | View 6c KPIs and action panel; export registers (no muster names below 185) | A | P | S | S | C1 | C | P (aggregates) | P |
| 190 | Void drills, checks, events and musters | A | P | — | — | — | — | — | — |

Devices: a `muster_reader` device may call only muster scan endpoints for its AP (§11.3). Suspended-contractor users keep reads and lose writes (Phase 0 rule 28).

## 6. Calculations

Rounding half-up at output only (Phase 1 K-R8): minutes to 1 dp, percentages to 1 dp. Comparisons and warnings use unrounded values.

### 6.1 Minutes
minutes(a, b) = (b − a) in seconds ÷ 60.

### 6.2 Coverage
For site S, date d, shift s:
- HC = Σ headcount of Phase 1 returns (Submitted or later) for S, d, shift s (shift `all` counts in day).
- Zones with work Z = distinct zone_id of those returns with headcount > 0 (rows without a zone add none).
- Required first aiders RFA = ceil(HC ÷ `first_aider_ratio`) if HC > 0, else 0.
- Required wardens RW = max(ceil(HC ÷ `warden_ratio`), |Z ∩ zones with warden_required|) if HC > 0, else 0.
- Count(role) = active assignments of role for S with shift ∈ {s, both}, valid on d, qualified on d (EO-3) and present on d (EO-4).
- covered ⇔ HC = 0 (not required) or (Count(first_aider) ≥ RFA ∧ Count(fire_warden) ≥ RW ∧ ∀ z ∈ Z with warden_required: ≥ 1 counted warden lists z ∧ coordinator rule EO-6).

### 6.3 Due dates
add_months as Phase 5 TR1 (month-end clamp). Programme line due_by = add_months(last satisfying conducted date, f) − 1 day. Rescue drill currency at d ⇔ last team drill date ≥ add_months(d, −12) + 1 day, i.e. d ≤ add_months(last, 12) − 1 day. Asset check due = last check date + interval days; overdue when today > that date. Service due = add_months(last_service_on, 12) − 1 day. Hydrotest due = 31 Dec of (manufactured_year + test interval years) ASSUMPTION.

### 6.4 Drill measures and result
- evac_min = minutes(alarm_at, evacuation_complete_at); headcount_min = minutes(alarm_at, headcount_complete_at); response_min = minutes(alarm_at, first_responder_at); rescue_min = minutes(alarm_at, casualty_recovered_at).
- **satisfactory** ⇔ every measure required by the type is ≤ its target ∧ no critical finding ∧ muster has no `found_on_site` and no entry left unaccounted at Closed. Otherwise **unsatisfactory**. Tabletop drills are satisfactory unless a critical finding exists.

### 6.5 Asset ready
ready(a, d) ⇔ status = in_service ∧ last valid check result pass ∧ d ≤ last check date + interval ∧ (no service interval ∨ d ≤ service due) ∧ (no hydrotest ∨ d ≤ hydrotest due) ∧ every expiry ≥ d.

### 6.6 Rescue team current — RT-2.

### 6.7 Event response times
first_response_min = minutes(raised_at, first_responder_at); external_arrival_min (per service) = minutes(called_at, arrived_at); total_min = minutes(raised_at, all_clear_at).

### 6.8 KPI catalogue (continues 6b §6.6)

| ID | Metric (EN / AR) | Formula | Unit / display | Better |
|---|---|---|---|---|
| K-104 | **Drill programme compliance** / الالتزام ببرنامج التمارين | items met on time ÷ items (DP-5) × 100; 0 items → "—"; breakdown by drill type and site | %, 1 dp | higher |
| K-105 | **Evacuation drill performance** / أداء تمارين الإخلاء | n(Evaluated evacuation_full / evacuation_partial drills conducted in period with evac_min ≤ target ∧ headcount_min ≤ target) ÷ n(those drills) × 100; chips: median evac_min, median headcount_min | %, 1 dp · min, 1 dp | higher |
| K-106 | **Emergency team coverage** / تغطية فريق الطوارئ | covered site-shift-days ÷ required site-shift-days in period × 100 (§6.2); breakdown first aiders / wardens / zones / coordinator | %, 1 dp | higher |
| K-107 | **Emergency equipment readiness** / جاهزية معدات الطوارئ | n(ready assets at as_of) ÷ n(assets not Retired at as_of) × 100; breakdown by type and not-ready reason | %, 1 dp | higher |
| K-108 | Rescue team readiness / جاهزية فرق الإنقاذ | n(active teams current at as_of) ÷ n(active teams) × 100; 0 teams → "—" | %, 1 dp | higher |
| K-109 | Real emergency events / الأحداث الطارئة الفعلية | n(events with raised_at in period, not Voided) by type; false alarms shown separately; chips: median first_response_min, median external_arrival_min | count · min, 1 dp | — (context) |

as_of = the period end or today, whichever is earlier.

### 6.9 Leading-indicator warnings
Monthly job, day 2 at 07:00, per project and per tier-1 tree with an engagement on the affected site (as DECISIONS #53).
- **E18 Preparedness** in M: K-104 in M < `drill_compliance_warning_pct`, or a programme line overdue by > 30 days at month end, or K-106 in M < `coverage_warning_pct`, or the ERP overdue at month end.
- **E19 Response readiness** in M: K-107 at month end < `equipment_readiness_warning_pct`, or K-108 at month end < 100.0, or a drill or event in M with headcount_min > target or a `found_on_site` resolution.
- T13 inputs: counts, numerators, denominators, thresholds and drill/event numbers; never names.

### 6.10 Worked examples (exact; backend unit tests must match)

**ED1 — coverage, S-AIR night, 2026-09-14.** Returns: GULFPAVE Z-TWB 260, GULFPAVE Z-APR-21 140, RAWABI (no zone) 120 → HC **520**, Z = {Z-TWB, Z-APR-21}. RFA = ceil(10.4) = **11**; RW = max(11, 2) = **11**. First aiders rostered S-AIR night/both: 12; gate `in` on 09-14: 11; qualified: 10 (one FIRST-AID expired 2026-09-10) → 10 < 11 → **not covered** (first aider short 1). Wardens 13 rostered, 12 present and qualified (Z-TWB 7, Z-APR-21 5), coordinator rostered. Variant HC 500 → RFA 10 → **covered**. Edges: HC 0 → not required; HC 1 → RFA 1, RW max(1, |Z|); HC 100 → 2; HC 101 → **3**.

**ED2 — S-LAND (no gate) day, 2026-09-14.** HC 1,450, Z = {Z-PIERB, Z-MSCP, Z-LAY1} → RFA 29, RW max(29, 3) = 29. First aiders rostered 31, all present (EO-4, no gate), qualified 30 (Waleed Saleh: FIRST-AID Rejected) → 30 ≥ 29. Wardens 30 qualified, Z-LAY1 has 2 → **covered**.

**ED3 — unannounced full evacuation, count mode (DRL-ANIA-EXP-2026-031, S-LAND, 2026-09-17).** Alarm 10:00:00; last person at AP 10:08:40 → evac_min 8.666… → **8.7** ≤ 10. Count rows: RAWABI 610 expected, 608 accounted, 2 resolved `off_site_confirmed` at 10:14; NAJD 520 / 520; SAHARA 282 expected, 281 accounted, 1 resolved `found_on_site` at 10:24:10 (Pier B level 3 stairwell) → headcount_complete 10:24:10 → **24.2** > 20. Expected 1,412. `found_on_site` → critical finding (MU-6) + DC02 fail → CA critical. Result **unsatisfactory** → repeat line due **2026-10-17**.

**ED4 — night full evacuation, roll mode (DRL-ANIA-EXP-2026-034, S-AIR, 2026-09-24 23:00, announced).** Roll: latest G-AAP3 row `in` since 07:00 → **486** expected. Accounted 478 by scan + 2 ticks by 23:12:05; 6 unaccounted: 4 `left_site_no_exit_scan` (23:15:40), 2 `off_site_confirmed` (23:17:30) → headcount_complete 23:17:30 → **17.5**; evacuation complete 23:06:15 → **6.3**; no critical finding → **satisfactory**. The night line was due 2026-09-20 (last night drill 2025-09-21: add_months(2025-09-21, 12) − 1) → satisfied **late** (K-104 miss); next due **2027-09-23**.

**ED5 — programme dates.** S-LAND evacuation_full, frequency 6, last 2026-03-18 → due **2026-09-17** → DRL-…-031 on 09-17 is on time. Next regular due add_months(2026-09-17, 6) − 1 = **2027-03-16**; repeat line due **2026-10-17**. A new site first worked 2026-10-10 with `emergency_register_from` 2026-05-01 → first due 2026-10-10 + 30 = **2026-11-09**.

**ED6 — asset readiness.** (a) FE-SLAND-0142 (dcp_abc 6 kg, Z-LAY1): last check 2026-08-31 pass, interval 30 → ready to **2026-09-30**, `CHECK_OVERDUE` from 2026-10-01; service 2025-10-10 → due **2026-10-09** (alerts 2026-09-09, 2026-10-02, 2026-10-09); manufactured 2019, dcp 12 years → hydrotest due **2031-12-31**. (b) AED-SAIR-01 pads expire 2026-10-31 → alerts 2026-10-01, 10-24, 10-31; `CONSUMABLE_EXPIRED` from **2026-11-01**. (c) A first-aid kit checked 2026-09-29 (interval 7) → overdue from **2026-10-07**. (d) A check with EC03 fail → result fail → Out of Service, CA high due +24 h; a later pass returns it to In Service.

**ED7 — rescue team (RT-ANIA-CSE-01, S-LAND; lead Rafiq Islam, 2 members; TW-01).** Rafiq CSE-RESCUE to 2026-11-02, FIRST-AID to 2026-11-15; members' CSE-RESCUE to 2027-03-01; last cse_rescue drill 2025-10-20 → current to **2026-10-19**. At the clock: **current**. On 2026-10-20: `RESCUE_DRILL_OVERDUE` → PTW-ANIA-EXP-2026-0413 revalidation blocked (PE-3). If a drill is Evaluated on 2026-10-15: current to 2027-10-14 until 2026-11-03, when Rafiq's CSE-RESCUE lapses → 2 qualified < 3 → `TEAM_UNDERSTRENGTH`.

**ED8 — medical event (EMV-ANIA-EXP-2026-004, W1 #4, Z-APR-21).** raised 2026-09-22 13:52, first responder 13:55 → **3.0** min (≤ 4); red_crescent called 13:56, arrived 14:09 → **13.0**; all clear 14:20 → total 28.0; casualties 1; incident linked; no muster.

**ED9 — September 2026 KPIs = seed (Appendix A.8).**

| Metric | ANIA-EXP calculation | ANIA-EXP | RBT-52 calculation | RBT-52 |
|---|---|---|---|---|
| K-104 | 4 on time ÷ 5 items | **80.0 %** | 3 ÷ 3 | **100.0 %** |
| K-105 | 1 ÷ 2 (031 fails headcount); medians (6.25, 8.666…) → 7.458…; (17.5, 24.166…) → 20.833… | **50.0 %** · 7.5 · 20.8 | 1 ÷ 1; DRL-RBT-52-2026-012 evac 9.2, headcount 15.0 | **100.0 %** · 9.2 · 15.0 |
| K-106 | 86 ÷ 90 × 100 = 95.555… | **95.6 %** | 60 ÷ 60 | **100.0 %** |
| K-107 (as_of 09-30) | 398 ÷ 412 × 100 = 96.601… | **96.6 %** | 147 ÷ 156 × 100 = 94.230… | **94.2 %** |
| K-108 (as_of 09-30) | 2 ÷ 2 | **100.0 %** | 0 ÷ 1 (RT-RBT-WAH-01 drill due 2026-09-14) | **0.0 %** |
| K-109 | medical 1, false alarm 1; median first response 3.0; external 13.0 | **2** | — | **0** |

Expected warnings for September 2026: **E18 ANIA-EXP** (K-104 80.0 < 90.0; project and the RAWABI tree) · no E18 RBT-52 · **E19 ANIA-EXP** (DRL-…-031 headcount 24.2 > 20 and `found_on_site`; RAWABI tree) · **E19 RBT-52** (K-108 0.0; K-107 94.23 < 95.0; QIMMA tree).

**ED10 — edges.** (a) K-106 = 9,495 ÷ 10,000 = 94.95 → displays **95.0 %**, E18 **raised**. (b) An AP in Z-APR-21 (movement area) → `ASSEMBLY_POINT_IN_RESTRICTED_AREA`; in Z-ILS33R (ils_critical) → same. (c) A scenario evacuation_full with frequency 9 → `DRILL_FREQUENCY_TOO_LOW`; 3 → accepted and the site line uses 3.

## 7. Alerts & expiries

Channels as Phases 1–6b: in-app and email in the recipient's language; "push" on the mobile web app; "SMS" items are sent in-app + email until an SMS channel exists (DECISIONS #124). Each (subject, step) is sent once; re-running a job never sends twice.

| Trigger | Recipient | Timing | Channel |
|---|---|---|---|
| Event declared (EV-2) | HSE Manager; HSE Officers; site engineers of the site; Contractor HSE Reps on the site; rostered coordinators | Within 60 s | In-app + push + email (SMS) |
| Unaccounted at headcount target, event (MU-8) | HSE Manager; HSE Officers; site engineers; coordinators | opened_at + target | In-app + push + email (SMS) |
| `found_on_site` in an event | HSE Manager | Immediately | In-app + push + email |
| Permits suspended by an event or drill (PE-1/PE-2) | Receivers and issuers of the permits | Within 60 s | In-app + push |
| Live coverage shortfall (EO-7) | Site engineers; Contractor HSE Reps on the site; HSE Officers | Shift start + offset, once per site-shift-day | In-app + push |
| Drill due (DP-4) | HSE Officers; site engineers of the site; team lead's Contractor HSE Rep (team lines) | 30 / 14 / 7 / 0 days, 07:05; overdue day 1 and weekly | In-app + email |
| Drill evaluation / event review overdue | HSE Officer; HSE Manager after 2 more days | At the deadline, then daily 07:05 | In-app + email |
| Asset check failed (EA-4) | Site engineer; owner's Contractor HSE Rep; HSE Officer | Within 60 s | In-app + email |
| Asset check overdue | Owner's Contractor HSE Rep; site engineer | Day 1 overdue, 07:05; weekly digest to HSE Officer | In-app |
| Service, hydrotest or consumable due | Owner's Contractor HSE Rep; HSE Officer | 30 / 7 / 0 days, 07:05 | In-app + email |
| Rescue team not current / becomes not current in ≤ 30 days | Team lead's Contractor HSE Rep; HSE Officers; issuers of live CSE permits naming the team | 30 / 7 / 0 days; at the change | In-app + email |
| ERP review due / review required | HSE Manager; HSE Officers | 30 / 7 / 0 days; at the trigger | In-app + email |
| E18 / E19 | HSE Manager; HSE Officers; tier-1 Contractor HSE Rep for its tree | Monthly job, day 2, 07:00 | In-app + email |

## 8. Reports / KPIs fed

### 8.1 Dashboard additions (Phase 1 §8.1)
1. **Leading tiles:** K-104 drill programme compliance · K-106 emergency team coverage · K-107 equipment readiness (chip: K-108) · K-105 evacuation drill performance (chip: median evacuation minutes).
2. **Emergency band** (live): ERP status and review date; active events and open musters (accounted / expected); current-shift coverage per site (first aiders and wardens required vs counted, zones without a warden); provision gaps; next drills due.
3. **Charts:** C28 evacuation and headcount minutes per drill against the target lines (last 12 months); C29 coverage grid site × shift × day (covered / short / not required) for the month; C30 assets by type stacked by readiness reason at month end.
4. Filters D-2 apply, plus drill type, asset type and shift.

### 8.2 Expiring items and action panel
- `ExpiringItemKind`: `emergency_drill_due`, `emergency_asset_service`, `emergency_asset_consumable`, `erp_review`, `rescue_team_drill`.
- Action panel: ERP overdue or review required; zones without an AP; active events; open musters with unaccounted entries; current-shift coverage shortfalls; overdue programme lines; drills not evaluated in time; events not reviewed in time; assets Out of Service or Missing; asset checks overdue (count by site); rescue teams not current; Active CSE permits whose team is not current (PE-3); permits still suspended `emergency_drill` 2 h after the drill was Conducted.

### 8.3 Registers and posters
ERP revisions, scenarios, APs, contacts, roster, rescue teams, assets, checks, programme, drills, musters (counts; names per P6c-4), events. Exports (189) write an `export` audit row (DECISIONS #78). **Site emergency poster** (A3, EN/AR, per site and shift): AP map refs, emergency numbers, coordinator, wardens per zone and first aiders with names (P6c-2), QR to the board.

### 8.4 Feeds to other phases
- **Phase 1:** K-104…K-109, E18–E19, T20, AI-19 section, CA source `emergency`, incident ↔ event link (read).
- **Phase 3:** suspensions `emergency` / `emergency_drill`, blockers `RESCUE_TEAM_NOT_REGISTERED` / `RESCUE_DRILL_OVERDUE`, warnings `HEIGHT_RESCUE_NOT_READY` / `NO_READY_EXTINGUISHER`, emergency_info prefill.
- **6g:** K-104, K-106, K-107 per site and contractor (roster and assets by owner engagement) for the scorecard; drill and event registers in the export pack.

## 9. Acceptance criteria

Fixtures: the Appendix A seed with the Phase 0–6b seeds; clock `HSE_CLOCK_AT` = **2026-10-06 10:00** unless stated. Users as 6b §9 (Faisal HSE Manager; Noura HSE Officer ANIA-EXP; Lina HSE Officer RBT-52; Omar site engineer S-AIR; Fahad site engineer S-LAND; Khalid issuer; Ramesh receiver NAJD; Sanjay receiver GULFPAVE; Ahmed Contractor HSE Rep RAWABI; Yousef Contractor HSE Rep QIMMA; Sarah viewer; Dr. Huda OH Practitioner).

**Plan and configuration**
1. **Given** Noura submits ERP-ANIA-EXP-r4 **When** she approves it **Then** 403 (180); Faisal approves **Then** r4 Approved, r3 Superseded, review_due_on = approval date + 12 months − 1 day. **When** Faisal approves a revision he prepared **Then** 422 `SOD_CONFLICT`.
2. **Given** a draft without scenario `height_rescue` and without an `airport_arff` contact **Then** approval 422 `ERP_INCOMPLETE` listing both (ER-3).
3. **Given** Z-LAY1 served by no active AP **Then** approval 422 `ERP_INCOMPLETE` naming Z-LAY1; deactivating AP-SLAND-01 and AP-SLAND-02 in turn → the second gets 422 `ZONE_WITHOUT_ASSEMBLY_POINT`.
4. **Given** ED10b **Then** both APs are refused with `ASSEMBLY_POINT_IN_RESTRICTED_AREA`.
5. **Given** ED10c **Then** frequency 9 is refused and 3 is accepted with the S-LAND line using 3 months.
6. **Given** a CSE permit Issued on ANIA-EXP in the last 90 days **When** scenario confined_space_rescue has no rescue plan ref and no "no such work" statement **Then** 422 `RESCUE_PLAN_REF_REQUIRED`.
7. **Given** ERP-RBT-52-r2 with review_due_on 2026-09-30 **Then** at the clock it is overdue: action panel item, Lina and Faisal alerted, and it still shows as the plan in force.
8. **Given** a drill finding of category `plan_deficiency` **Then** the ERP's review_required = true and Faisal is alerted; approving a new revision clears it (ER-8).
9. **Given** Faisal sets `first_aider_ratio` 60 or `drill_minimums.evacuation_full` 9 **Then** 422 `SETTING_LOOSENING`; 40 and 4 **Then** saved and audited. Noura editing any 6c setting **Then** 403.
10. **Given** RBT-52 (no Approved non-overdue ERP at the clock) **When** Faisal sets `emergency_ptw_enforcement_from` **Then** 422 `ERP_NOT_APPROVED`.

**Organisation and coverage**
11. **Given** ED1 **Then** the 2026-09-14 S-AIR night site-shift-day has RFA 11, RW 11, first aiders counted 10, and is not covered with reason first_aider; with HC 500 it is covered.
12. **Given** ED1 edges **Then** HC 0 is not required, HC 1 needs 1 first aider, HC 100 needs 2, HC 101 needs 3.
13. **Given** ED2 **Then** S-LAND day on 2026-09-14 is covered; Waleed Saleh is listed as rostered but not qualified (FIRST-AID Rejected).
14. **Given** a warden rostered on S-AIR without a gate `in` that day **Then** he is not counted (EO-4); on S-LAND (no gate) **Then** he is counted.
15. **Given** a day with HC 300 on S-LAND and Z-MSCP with work but no warden assigned to Z-MSCP **Then** not covered (zone) even if 6 wardens are counted.
16. **Given** Ahmed adds a first_aider assignment for a NAJD worker without matrix role first_aider **Then** saved and the Phase 5 profile gains `first_aider` (audited `matrix_role_added_by_6c`); for a QIMMA worker **Then** 403 (C scope).
17. **Given** the clock day shift on S-LAND with a live shortfall **Then** at 07:00 one alert reaches Fahad, Nasser, the Contractor HSE Reps of engagements on S-LAND (Ahmed among them) and Noura; re-running the job sends nothing.
18. **Given** September 2026 **Then** K-106 = 95.6 % ANIA-EXP (4 S-AIR night shortfalls) and 100.0 % RBT-52 (ED9).

**Rescue teams**
19. **Given** ED7 **Then** RT-ANIA-CSE-01 is current at the clock and not current on 2026-10-20 with `RESCUE_DRILL_OVERDUE`.
20. **Given** ED7 with a drill Evaluated on 2026-10-15 **Then** on 2026-11-03 the team is not current with `TEAM_UNDERSTRENGTH`.
21. **Given** a team whose only FIRST-AID holder leaves **Then** not current `NO_FIRST_AIDER`; **given** TW-01 tagged Out of Service in Phase 4 **Then** not current `RESCUE_EQUIPMENT_NOT_READY`.
22. **Given** Rafiq is lead of RT-ANIA-CSE-01 **When** he is added as a member of a second confined_space team **Then** 422 `ALREADY_IN_TEAM`; a 2-person confined_space team **Then** not current `TEAM_UNDERSTRENGTH`.

**Emergency equipment**
23. **Given** ED6a **Then** FE-SLAND-0142 is ready on 2026-09-30, not ready `CHECK_OVERDUE` at the clock, and the service alerts fall on the stated dates.
24. **Given** ED6b and ED6c **Then** the AED is not ready from 2026-11-01 (`CONSUMABLE_EXPIRED`) and the kit is overdue from 2026-10-07.
25. **Given** Fahad scans FE-SLAND-0142 and answers EC03 = fail **Then** result fail, the asset is Out of Service within 60 s, one CA (source `emergency`, high, due +24 h) is created and Fahad, Ahmed and Noura are alerted; a new passing check returns it to In Service.
26. **Given** a check with only EC09 = fail and fixed_on_spot = true **Then** result pass, no CA. **Given** outcome `missing` **Then** the asset is Missing and a CA is created.
27. **Given** Ramesh (C1) records a manual check without a scan **Then** saved with warning `CHECK_WITHOUT_SCAN`; a check dated 73 h ago **Then** 422 `CHECK_BACKDATED`.
28. **Given** Z-LAY1 with one ready extinguisher (minimum 2) and work today **Then** a provision gap is listed on the board and the action panel; nothing is blocked.
29. **Given** an attempt to register a fire extinguisher as a Phase 4 equipment item **Then** 422 (category not in EQC); 6c assets never appear in K-72/K-74 (BD6c-3).

**Programme**
30. **Given** ED5 **Then** the S-LAND evacuation line is due 2026-09-17, satisfied on time by DRL-…-031, next due 2027-03-16, and a repeat line is due 2026-10-17.
31. **Given** ED4 **Then** the S-AIR night line due 2026-09-20 is satisfied late (K-104 item not met) and next due 2027-09-23.
32. **Given** an unannounced night full evacuation **Then** it satisfies the site's regular, night and unannounced lines; an `evacuation_partial` satisfies none of them.
33. **Given** ED5's new site **Then** its first evacuation line is due 2026-11-09.
34. **Given** a line due 2026-10-15 **Then** alerts go on 09-15, 10-01, 10-08 and 10-15 to Noura and the site engineers; from 10-16 it is overdue.
35. **Given** a real site evacuation event on S-LAND **Then** no programme line is satisfied (DP-6).

**Drills and muster**
36. **Given** an unannounced drill planned for S-LAND **When** Ahmed or Ramesh lists drills before alarm_at **Then** it is absent; Fahad and Noura see it; after Start everyone with 178 sees it (DR-2).
37. **Given** Fahad is conductor **When** he is the only evaluator **Then** 422 `SOD_CONFLICT`.
38. **Given** DRL-…-031 timings with evacuation_complete_at before alarm_at **Then** 422 `TIMELINE_ORDER`.
39. **Given** ED3 **Then** evac 8.7, headcount 24.2, a critical finding and CA from `found_on_site`, result unsatisfactory, repeat line due 2026-10-17.
40. **Given** ED4 **Then** the roll holds 486 entries from G-AAP3, headcount completes at 23:17:30 (17.5), evac 6.3, result satisfactory.
41. **Given** an open roll muster **When** a worker not on the roll is scanned at AP-SAIR-01 **Then** he is accounted and `extras` = 1; the scan creates no gate-log row and runs no eligibility check (MU-4, MU-5).
42. **Given** a muster_reader device bound to AP-SAIR-01 **When** it calls any other endpoint, or scans for AP-SLAND-01 **Then** 403.
43. **Given** a drill started with alarm_at 30 min in the past **Then** late_entry = true, count mode, no permit suspension and no live alert (DR-4).
44. **Given** a drill evaluation with DC04 = fail **Then** a critical finding and a CA priority critical are created automatically; a minor finding creates no CA unless asked.
45. **Given** a cse_rescue drill of RT-ANIA-CSE-01 with TW-01 Out of Service at alarm_at **Then** a major finding `equipment` is added (DR-8).
46. **Given** a drill Conducted on 2026-10-01 not evaluated by 2026-10-04 **Then** Noura is alerted, and Faisal on 2026-10-06.
47. **Given** a voided drill **Then** it leaves K-104/K-105 and its programme line returns to the previous due date; its CAs stay open.

**Events**
48. **Given** Omar declares a site evacuation (fire_explosion) on S-AIR **Then** within 60 s Faisal, Noura, Omar, the Contractor HSE Reps on S-AIR and the rostered coordinators are alerted; a roll muster opens; every Issued/Active permit on S-AIR zones is Suspended `emergency`.
49. **Given** that event with 3 entries unaccounted at opened_at + 20 min **Then** the MU-8 alert goes once; a `found_on_site` resolution alerts Faisal at once.
50. **Given** the event (fire_explosion) without an incident **When** it is reviewed **Then** 422 `INCIDENT_LINK_REQUIRED`; a `false_alarm` event is reviewed without one.
51. **Given** ED8 **Then** first response 3.0, red crescent arrival 13.0, total 28.0 minutes, no muster, and the event shows no casualty name.
52. **Given** a Phase 2 ops event `aircraft_emergency` on Z-TWB and Z-ILS33R **Then** a 6c `airport_aep_activation` event exists with those zones and response_type zone_evacuation; ending the ops event sets All Clear.
53. **Given** Omar (site engineer) **When** he reviews an event **Then** 403; he may declare All Clear. Sarah **When** she declares an event **Then** 403.

**Phase 3 integration**
54. **Given** a drill on S-LAND with suspend_permits **When** it starts **Then** PTW-ANIA-EXP-2026-0413 (Z-MSCP) is Suspended `emergency_drill` (routine, not in K-65); after Conducted the receiver resumes it with the GT-4 test; without the test **Then** 422.
55. **Given** a permit suspended `emergency` by an event **When** the receiver resumes **Then** 422; the issuer resumes after All Clear with cause text ≥ 20 chars (SH-3).
56. **Given** `emergency_ptw_enforcement_from` 2026-10-01 on ANIA-EXP **Then** PTW-0413 revalidates at the clock; on 2026-10-20 its revalidation gets blocker `RESCUE_DRILL_OVERDUE` (ED7); with a rescue lead in no team **Then** `RESCUE_TEAM_NOT_REGISTERED`. On RBT-52 (enforcement null) **Then** no rescue blocker applies.
57. **Given** a WAH permit with arrest crew on S-LAND and no current height team covering S-LAND **Then** warning `HEIGHT_RESCUE_NOT_READY`, not a blocker.
58. **Given** a hot-work permit starting on Z-LAY1 when no extinguisher in Z-LAY1 is ready **Then** warning `NO_READY_EXTINGUISHER`.
59. **Given** a new permit request on Z-PIERB **Then** emergency_info is pre-filled with AP-SLAND-01 and the internal, 998 and 997 numbers; on Z-TWB it also names airport ARFF.

**KPIs, warnings, AI, PDPL**
60. **Given** September 2026 **Then** K-104…K-109 match ED9 for both projects.
61. **Given** September 2026 **Then** E18 and E19 are raised exactly as ED9 lists, with T13 inputs and no names.
62. **Given** ED10a **Then** K-106 displays 95.0 % and E18 is raised.
63. **Given** the AI is asked "who was missing in the September drill on Terminal 3?" **Then** T20 returns the drill's counts and times only and the assistant says names are not available to it; "which site has the worst equipment readiness?" **Then** T20 groups by site.
64. **Given** Sarah **Then** she sees K-104…K-109 and the ERP status but no roster names in exports, no muster entries and no unannounced drill before start; Ahmed sees DRL-…-034 roll entries for RAWABI-tree workers only; reads of a Closed named roll write `sensitive_field_read`.
65. **Given** muster entries older than 12 months **Then** the retention job reduces them to counts by state and reason (`retention_purge`); drill timings and results remain.
66. **Given** the UI in Arabic **Then** every 6c label, status, list value, alert, poster and error has its AR text; times, minutes and codes stay left-to-right inside the RTL layout.

## 10. Open questions for the HSE Manager

Each has a default so the build can start.
1. **Ratios:** 1 first aider and 1 fire warden per 50 workers per shift, plus a warden per zone with work. Does the client, Civil Defense office or MHRSD inspector expect a different ratio (e.g. 1:25 first aiders on high-risk sites)?
2. **Drill minimums:** full evacuation every 6 months per site, a night drill and an unannounced drill each year, medical response every 6 months, tabletop yearly, rescue drills yearly per team. Does the client audit monthly drills (zone drills rotating through zones)?
3. **Sites without gates:** rostered first aiders and wardens count as present (EO-4). Should site engineers confirm attendance per shift instead?
4. **Targets:** evacuation 10 min and headcount 20 min for a construction site; first responder 4 min. Do the client or the airport operator set their own?
5. **Real evacuations** do not count as drills. Accept them as drills when a full evaluation is recorded?
6. **Rescue readiness on live permits:** a team that stops being current blocks the next Start/Revalidate but does not suspend an Active confined-space permit. Suspend at once instead?
7. **Airside drills:** what does the airport operator require before a contractor evacuation drill on S-AIR (AOCC notice, escort, timing), and which AEP exercises must the contractor join?
8. **Offline muster:** the platform is online-only; the fallback is the printed muster sheet. Is a phone app with an offline roll needed?
9. **Fire equipment service:** which Civil Defense-licensed maintenance companies are used, and should their licence be checked like a TPI accreditation?
10. **WAH-RESCUE course:** a new Phase 5 course (24 months) for height rescue teams. Do you use a specific provider or client course?

## 11. Changes required in earlier specs (to be applied by the coordinator; this spec does not edit them)

### 11.1 `0-foundation.md` v1.0 → v1.1 (adds to the 6a/6b changes)
1. Matrix rows 178–190 (§5.13).

### 11.2 `1-dashboard.md` v1.5 → v1.6
1. §3.8 CA `source_type` adds `emergency` (source_id = 6c asset check, drill or event).
2. §5.9 AI: T20 (EM-2); T13 returns E18–E19; AI-19 section "Emergency preparedness".
3. §6.9 / §7: E18–E19 (§6.9 here), same monthly job and recipients.
4. §8.1: tiles, emergency band, charts C28–C30; `ExpiringItemKind` and action-panel items of §8.2.
5. Incident read model shows the linked 6c event number (read only).

### 11.3 `2-access-permits.md` v1.4 → v1.5
1. §3.20 QR kinds add `EA` (emergency asset sticker) and `MP` (assembly point); both open 6c screens only and are DENIED `TOKEN_UNKNOWN` at gates (as `TR`, GC-3).
2. §3.19 device kind `muster_reader`: bound to one 6c assembly point, may call only the muster scan endpoints, same token, rotation and revocation rules (GC-1).
3. P2-8: add "gate logs may be read for emergency musters (life safety); muster data is never used for attendance".
4. 6c consumes `ops.event_declared` / `ops.event_ended` for type `aircraft_emergency` (EV-6). No Phase 2 behaviour change.

### 11.4 `3-ptw.md` v1.3 → v1.4
1. **List SR:** add `emergency_drill` إيقاف لتمرين طوارئ, routine = true (excluded from K-65, shown with routine suspensions, SH-8).
2. **SH-2:** automatic `emergency` suspension within 60 s of `emergency.event_declared` for evacuated zones (PE-1) and `emergency_drill` at drill Start (PE-2). **SH-3:** resume after `emergency_drill` by the receiver, no issuer cause text, GT-4 where gas testing applies.
3. **List B / PT-16:** blockers `RESCUE_TEAM_NOT_REGISTERED`, `RESCUE_DRILL_OVERDUE` for confined_space at Start, Revalidate, Resume and handover acceptance (PE-3); warnings `HEIGHT_RESCUE_NOT_READY` (PE-4), `NO_READY_EXTINGUISHER` (PE-5).
4. **§3.2 emergency_info:** pre-filled at Request from 6c (PE-6); still editable and required.
5. §8.3 action panel: Active CSE permits whose rescue team is not current.
6. Items 3–5 apply only on projects with `emergency_ptw_enforcement_from` ≤ today (item 4 from `emergency_register_from`); Phase 3 ACs stay valid on the Phase 3 seed.

### 11.5 `4-third-party-cert.md` v1.1 → v1.2
1. §3.1 kinds add `fire_protection_service` شركة صيانة معدات الحريق; §3.2 standard adds `civil_defense_licence` (accreditation_body `civil_defense` `VERIFY` R1), no scope categories. Such organisations never satisfy TP-4 for equipment or personnel certificates.
2. BD: fire extinguishers, first-aid kits, AEDs, eyewash and other emergency assets are 6c assets, not EQC categories (BD6c-3); `tripod_winch` items are read by 6c rescue teams.

### 11.6 `5-training.md` v1.1 → v1.2
1. Catalogue adds **WAH-RESCUE** Rescue from height / الإنقاذ من المرتفعات: category high_risk_task, validity 24 months ASSUMPTION, min 8.00 h, theory 80 / practical pass, internal allowed, prerequisite WAH.
2. §8.5: "6c reads Phase 5 records through the training check for coverage and rescue teams, and adds matrix roles `fire_warden` / `first_aider` from its roster (`6c-emergency-drills.md` EO-2)".
3. **Seed:** CSE-RESCUE records (INT-HSE, completed 2026-03-02, valid to 2027-03-01) for the two RT-ANIA-CSE-01 members (A.4); WAH-RESCUE records for the height team members.

## Appendix A — Seed data (fictional; `seed_fake = true`; tags, refs and serials contain `TEST` where printed)

### A.1 Principles
- Builds on the Phase 0–6b seeds. Clock `HSE_CLOCK_AT` = 2026-10-06T10:00:00+03:00.
- `emergency_register_from` = **2026-03-01** on both projects; `emergency_ptw_enforcement_from` = **2026-10-01** on ANIA-EXP, null on RBT-52. No seeded permit is blocked at the clock (RT-ANIA-CSE-01 is current; every zone with a hot-work permit has a ready extinguisher).
- Days with work in September 2026 as Phase 1 W1: S-AIR day and night, S-LAND day, S-TWR day, S-POD day (30 days each). If the Phase 1 generator differs, the backend records the difference in DECISIONS.

### A.2 ERPs, APs and contacts
| Record | Data |
|---|---|
| ERP-ANIA-EXP-r3 | Approved 2026-02-15 by Faisal (prepared by Noura), sites S-AIR, S-LAND, client acceptance ANIA-CL-ERP-TEST-03, airport interface OEXX-AEP-TEST-2026, review due **2027-02-14**; scenarios: all ★ incl. aircraft_emergency, plus gas_release (Z-MSCP, H₂S) and utility_strike |
| ERP-RBT-52-r2 | Approved 2025-10-01, review due **2026-09-30** → overdue at the clock (AC7); all ★ scenarios except aircraft_emergency, plus structural_collapse (tower crane) |
| AP-SAIR-01 / AP-SAIR-02 | S-AIR, no zone (contractor compound beside G-AAP3 / service road east), primary / alternate, serve Z-APR-21, Z-TWB, Z-ILS33R, capacity 800 / 400 |
| AP-SLAND-01 / AP-SLAND-02 | S-LAND, Z-LAY1 / no zone (landside north plaza), primary / alternate, serve Z-PIERB, Z-MSCP, Z-LAY1, capacity 1,500 / 1,000 |
| AP-STWR-01 / AP-SPOD-01 | RBT-52 S-TWR (serves Z-CORE, Z-TC01) / S-POD (serves Z-B4, Z-FAC), primary, capacity 600 / 400 |
| Contacts (both projects) | civil_defense 998, red_crescent 997, police 999, unified_911 911, site_clinic +966110000911 (fake), hospital "Al-Noor General Hospital (fictional)" +966110000912; ANIA-EXP also airport_arff +966110009998 (fake), airport_aocc +966110009997 (fake), airport_security +966110009996 (fake) |
| Zone profiles | Z-B4 eyewash_required (concrete admixtures), Z-MSCP min_extinguishers 4 |

### A.3 Roster
- ANIA-EXP: 96 first_aider and 64 fire_warden assignments for the Phase 5 holders (A.9 of Phase 5: 93 / 62 in force; Waleed Saleh not qualified), split S-AIR day / S-AIR night / S-LAND day as needed for ED1, ED2 and A.8; coordinators: Omar (S-AIR day), a RAWABI supervisor (S-AIR night), Fahad (S-LAND day). Named: Mahmoud Fathy fire_warden S-AIR day [Z-APR-21]; Rafiq Islam first_aider S-LAND day; Waleed Saleh first_aider S-LAND day.
- RBT-52: 20 first_aider and 16 fire_warden assignments (19 / 15 qualified); coordinator Ibrahim (S-TWR, S-POD day); Yousef Al-Ghamdi first_aider S-TWR day.

### A.4 Rescue teams and equipment
| Team | Data |
|---|---|
| RT-ANIA-CSE-01 | confined_space, S-LAND; lead Rafiq Islam; 2 members = the two lowest worker_no Mobilised RAWABI labourers on S-LAND (CSE-RESCUE per §11.6); TW-01 (Phase 4 tripod_winch item added by this seed: RAWABI, certificate AICC TEST valid to 2027-02-28, In Service); last cse_rescue drill DRL-ANIA-EXP-2025-019 on **2025-10-20** (ED7) |
| RT-ANIA-WAH-01 | height, S-AIR and S-LAND; 3 RAWABI scaffold supervisors with WAH and WAH-RESCUE; RK-ANIA-01 rescue kit; last height_rescue drill 2026-04-12 → current |
| RT-RBT-WAH-01 | height, S-TWR; 2 QIMMA members; RK-RBT-01; last drill **2025-09-15** → not current from 2026-09-15 (K-108 0 %) |

### A.5 Assets
- ANIA-EXP 412 (fire_extinguisher 300, first_aid_kit 46, aed 8, eyewash_portable 10, eyewash_plumbed 4, alarm_call_point 18, siren_air_horn 6, stretcher 12, rescue_kit_height 2, fire_blanket 6); RBT-52 156 (extinguisher 110, first_aid_kit 20, aed 3, eyewash 4 incl. Z-B4, call point 12, stretcher 6, rescue_kit_height 1).
- Named: **FE-SLAND-0142** (ED6a; RAWABI; service FIRESAFE FS-TEST-2025-8831; last check 2026-08-31 by Fahad), **AED-SAIR-01** (pads 2026-10-31), **RK-ANIA-01**, **TW-01** (Phase 4).
- Service provider FIRESAFE "FireSafe Maintenance Co. (fictional)", kind `fire_protection_service`, licence CD-TEST-LIC-0447 valid to 2027-06-30.
- Checks: every asset checked at its interval from 2026-03-01 by the owner's rep or site engineer, with the not-ready state at 2026-09-30 per A.8.

### A.6 Drills (named)
| Drill | Data |
|---|---|
| DRL-ANIA-EXP-2026-031 | evacuation_full, S-LAND, unannounced, day, 2026-09-17, ED3, conductor Fahad, evaluator Noura; CA for the critical finding (owner SAHARA) |
| DRL-ANIA-EXP-2026-034 | evacuation_full, S-AIR, announced, night, 2026-09-24 23:00, ED4, conductor Omar, evaluator Noura, AOCC ref AOCC-LOG-TEST-388 |
| DRL-ANIA-EXP-2026-029 / -033 | medical_response S-LAND 2026-09-06 / S-AIR 2026-09-27, satisfactory |
| DRL-ANIA-EXP-2026-035 | tabletop, project, 2026-09-29 (scenarios gas_release, aircraft_emergency) |
| DRL-RBT-52-2026-012 | evacuation_full, S-TWR, 2026-09-10, evac 9.2, headcount 15.0, satisfactory; plus medical_response S-POD 2026-09-18 and tabletop 2026-09-24 |
| History | ANIA-EXP: S-LAND evacuation 2026-03-18; S-AIR night evacuation 2025-09-21; earlier drills as needed so that no other ANIA-EXP or RBT-52 line falls due in September 2026 |

### A.7 Events
| Event | Data |
|---|---|
| EMV-ANIA-EXP-2026-004 | ED8: medical_emergency, S-AIR Z-APR-21, linked to the W1 #4 incident (Ganesh's heat exhaustion), declared by Omar, Reviewed by Noura 2026-09-24 |
| EMV-ANIA-EXP-2026-003 | false_alarm, S-LAND Z-PIERB, 2026-09-03 09:12, call point knocked by a forklift, local_response, all clear 09:20, Reviewed |

### A.8 September 2026 volumes (reproducing ED9)
| Item | ANIA-EXP | RBT-52 |
|---|---|---|
| Programme items due in September / met on time | 5 / 4 (S-AIR night late) | 3 / 3 |
| Evaluated evacuation drills / meeting both targets | 2 / 1 | 1 / 1 |
| Required site-shift-days / covered | 90 / 86 (S-AIR night 09-05, 09-14, 09-19, 09-26: first aider short) | 60 / 60 |
| Assets not Retired at 09-30 / ready | 412 / 398 (check overdue 6, Out of Service 5, Missing 2, service overdue 1) | 156 / 147 (check overdue 5, Out of Service 3, consumable expired 1) |
| Active rescue teams / current at 09-30 | 2 / 2 | 1 / 0 |
| Events (not voided) | 2 (medical 1, false alarm 1) | 0 |

The generator creates only 6c records, plus the Phase 4 item TW-01 and the Phase 5 records of §11.6 item 3. It never changes Phase 1–6b KPIs.

### A.9 Settings
All 6c settings at the §3.15 defaults on both projects, except the dates in A.1.

## Change log

| Version | Date | Author | Change |
|---|---|---|---|
| v1.0 | 2026-10-09 | HSE Consultant Agent | First issue. §1–§11 and Appendix A: ERP with scenarios, assembly points, contacts and zone profiles; emergency roster and coverage per site, shift and zone from Phase 5 records and gate presence; rescue teams and readiness; emergency asset register with checks, service and expiries; drill programme; drills with muster (roll from gate logs or counts), evaluation and findings → CAs; real emergency event log; Phase 3 suspensions on alarm, rescue-readiness blockers and emergency information. Capabilities 178–190, KPIs K-104…K-109, warnings E18–E19, AI tool T20, charts C28–C30, QR kinds EA and MP. 66 acceptance criteria. Earlier-spec changes in §11, not yet applied: 0-foundation, 1-dashboard v1.6, 2-access-permits v1.5, 3-ptw v1.4, 4-third-party-cert v1.2, 5-training v1.2. |
