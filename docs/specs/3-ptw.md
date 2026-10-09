# Module Spec — Phase 3: Permit to Work (PTW)

**Version:** v1.4 · **Date:** 2026-10-09 · **Author:** HSE Consultant Agent · **Status:** Draft for HSE Manager review
**Builds on:** `0-foundation.md` v1.0 (projects/sites/zones incl. airside attributes, contractors & engagement tree, users, roles `permit_issuer` / `permit_receiver`, rule 16 issuer/receiver segregation, rule 28 "later phases additionally block permits", matrix rows 1–19, PDPL P1–P13) · `1-dashboard.md` v1.2 (matrix rows 20–45, KPI catalogue K-01…K-47 incl. placeholder **K-46 PTW audits**, CA entity, warnings E1–E7, action panel, expiring-items endpoint, AI tools T1–T14, severity list S, rounding K-R8) · `2-access-permits.md` v1.1 (worker register & deployments, eligibility function E and Phase 3 services HK-6, WAP / NOTAM / obstacle clearance / ops suspension, hook interface HK-1…HK-5 with `warn` policy, QR tokens, matrix rows 46–81, KPIs K-48…K-60, alert schedules) · `docs/DECISIONS.md` #1–#54.
**Covers (build order):** 3.1 Configuration: permit types, zone PTW profiles, zone adjacency, SIMOPS rules, PTW appointments · 3.2 Permit core: request → review → approve → issue → active, crew & equipment, type sections · 3.3 JSA / risk assessment (5×5, residual acceptance) and RA/MS documents · 3.4 Gas detectors and gas testing · 3.5 Isolations / LOTO register · 3.6 SIMOPS conflict check & coordination · 3.7 Shifts: handover, revalidation, suspension, closure, expiry · 3.8 Heat / midday-ban rules · 3.9 PTW audits · 3.10 KPIs, alerts, dashboard & AI feeds.
**Hooks only (not specified here):** Phase 4 third-party certification (operator cards, crane/lifting-gear/MEWP certificates) and Phase 5 training/competence, through the Phase 2 hook interface in `warn` mode until those phases exist (§5.10). Phase 6 medical fitness and WBGT heat-stress module (hook kind `medical_fitness`; Phase 3 records only ambient temperature).

Conventions: `VERIFY` = clause/number to confirm against the current official text or the client's procedure. `ASSUMPTION` = Consultant default; HSE Manager may override (§10). "Must" = enforced server-side. Rule prefixes: PT permit core, PR roles/appointments/SoD, JS JSA/RA, GT gas test, IS isolation/LOTO, SM SIMOPS, HW hot work, CS confined space, WH work at height, EX excavation, EL electrical, LF lifting, RG radiography, AW airside works, HT heat/midday ban, SH shift/suspension/handover, CL closure/expiry, HK3 hooks, AU audits, KP KPIs/AI, P3- PDPL. Error codes are stable strings (Phase 0 rule 48). Times are local Asia/Riyadh unless marked UTC (Phase 0 K2).

**Important boundary:** the platform is the system of record for permits, but the permit is only valid when the people named on it have been to the work site. Digital approval never replaces the issuer's site inspection: every Issue, Revalidation, Resume and Closure records `site_visit_confirmed = true` by the issuer (rule PT-14). The platform does not detect work done without a permit; PTW audits do (§5.11).

---

## 1. Purpose

Most fatal accidents on KSA construction and airport projects happen during work that should have been under a permit: hot work that starts a fire, an entrant overcome in a manhole, a fall from a slab edge, a trench collapse, contact with a "dead" cable that was live, a dropped load, a radiography source exposing passers-by, or a works crew on a taxiway without a NOTAM. Paper permit books cannot prove who checked what, cannot see that a hot-work permit was issued ten metres from an open manhole, cannot stop a crane lift when the operator's card has lapsed, and cannot tell the HSE Manager how many permits were audited this week. Phase 3 gives one Permit to Work system for every high-risk activity: a common lifecycle with type-specific sections, named and appointed roles with segregation of duties, a JSA with a 5×5 risk matrix and residual-risk acceptance, gas testing with calibrated instruments, a lock-and-tag isolation register, an automatic SIMOPS conflict check, shift handover and revalidation, safe closure, field audits, and links to Phase 2 access controls (worker eligibility, work-area access permits, NOTAMs, obstacle clearances). It feeds the dashboard's PTW leading indicators (K-46 and K-61…K-71) and the AI layer.

## 2. Regulatory basis

| # | Source | What it drives here |
|---|---|---|
| R1 | **Saudi Aramco GI 2.100 Work Permit System**; **GI 6.012 Isolation, Lockout and Use of Hold Tags**; Aramco gas-testing GI and **Construction Safety Manual (CSM)** chapters on work permits, confined spaces, excavations, fall protection, cranes & lifting, radiation `VERIFY` GI numbers, editions and chapter numbers — used as the KSA client benchmark where stricter | Permit types, single-shift validity, issuer/receiver duties, gas testing before and during work, isolation & hold tags, critical lifts |
| R2 | **OSHA 29 CFR 1910.146** (permit-required confined spaces: acceptable entry conditions, attendant, rescue, permit content, cancelled permits retained 1 year); **1910.147** (control of hazardous energy: group lockout, lock removal by other than the applier (e)(3)); **1926.1200–1213** (confined spaces in construction) | CSE section, standby person, rescue plan, atmospheric limits, LOTO, lock cut procedure |
| R3 | **OSHA 1926 Subpart M** — 1926.501 (6 ft / 1.8 m trigger), 1926.502(d) (anchorage 22.2 kN, free fall ≤ 1.8 m, deceleration ≤ 1.07 m, prompt rescue (d)(20)) | WAH section, fall-clearance calculation, rescue plan |
| R4 | **OSHA 1926 Subpart P** — 1926.651 (utilities, access within 25 ft / 7.6 m, spoil ≥ 2 ft / 0.6 m, hazardous atmospheres, daily inspection by competent person (k)), 1926.652 (protective systems ≥ 5 ft; PE design > 20 ft / 6.1 m) | Excavation section; Aramco/CSM 1.2 m trigger is stricter and wins `VERIFY` |
| R5 | **OSHA 1926 Subpart CC** (cranes: 1926.1400 ff., 1926.1425 keeping clear of the load, 1926.1408 power lines) and **ASME B30.3 / B30.5 / B30.9 / B30.20 / B30.23** (tower/mobile cranes, slings, below-the-hook devices, personnel lifting); **BS 7121 / ISO 12480-1** (safe use of cranes, appointed person, lift categories) | Lifting section, critical-lift criteria, wind limits, lift plan, exclusion zone |
| R6 | **NFPA 70E (2024)** — 110.4 / 130.2 (electrically safe work condition, energized work justification and permit), 120 (LOTO, test for absence of voltage), 130.4 / 130.5 (approach boundaries, arc-flash risk assessment) `VERIFY` article numbers in the edition the client uses; **IEC 60364** voltage bands (LV ≤ 1,000 V AC / 1,500 V DC) | Electrical section, energized-work prohibition/permit, test-for-dead, HV earthing |
| R7 | **Saudi Building Code SBC 801 (Fire Code)** — chapter on welding and other hot work (IFC ch. 35 basis: hot-work permit, fire watch ≥ 30 min after work, 35 ft / 10.7 m combustibles clearance, extinguisher within 30 ft) and fire-protection impairment notification (IFC 901.7 basis: impairment > 4 h in 24 h notified) `VERIFY` SBC 801 section numbers; **Saudi Civil Defense** hot-work and impairment requirements `VERIFY` | Hot-work section, Civil Defense notification of fire-system impairment |
| R8 | **NFPA 51B (2019)** — fire watch ≥ 1 h after hot work, 35 ft (11 m) rule; **OSHA 1926.350–352** (gas cylinders: oxygen/fuel separation 20 ft / 6.1 m or 5 ft / 1.5 m half-hour barrier, flashback protection) | Fire watch 60 min (strictest), cylinder rules |
| R9 | **NIOSH / ACGIH TLVs / OSHA PELs** — O₂ 19.5–23.5 %; H₂S TLV-TWA 1 ppm (STEL 5); CO TLV-TWA 25 ppm (NIOSH REL 35, OSHA PEL 50); flammables 10 % LEL hazardous-atmosphere threshold (1910.146) `VERIFY` current TLV booklet | Gas-test acceptance limits (strictest of the three taken) |
| R10 | **EN 60079-29-2 / ISA-RP12.13** and manufacturers' instructions — bump test before each day's use, calibration interval | Detector register, bump test and calibration rules |
| R11 | **Nuclear and Radiological Regulatory Commission (NRRC)** — licensing of industrial radiography, radiation protection officer, controlled-area marking, transport of sources `VERIFY` regulation titles and the controlled-area dose-rate value; **IAEA SSR-2/1 / SSG-11** (radiation safety in industrial radiography) | Radiography section, barrier calculation, licence checks |
| R12 | **MHRSD midday outdoor work ban** 12:00–15:00, 15 Jun–15 Sep (annual ministerial decision) `VERIFY` dates and exempted activities; MHRSD OSH regulations on heat stress | Midday-ban rules HT-x |
| R13 | **ICAO Annex 14**, **Doc 9981 PANS-Aerodromes** (works on the aerodrome), **Doc 9137 Part 6/8**, **GACAR Part 139** `VERIFY`; airport operator Works Safety Plan / airside works procedure; aviation fuel hydrant operator rules | Airside section; links to Phase 2 WAP, NOTAM, obstacle clearance, FOD hand-back |
| R14 | **ISO 45001:2018** cl. 8.1.2 (hierarchy of controls), 8.1.4 (contractors), 8.2 (emergency), 9.1 (monitoring — audits); **HSG250 (UK HSE) Guidance on permit-to-work systems**; **NEBOSH** 5×5 matrix | Lifecycle, handover, audits, risk matrix |
| R15 | **PDPL** + Implementing Regulations (Phase 0 R1/R2) | Crew data, signatures, fitness results, retention |

Strictest-wins applied in this spec (and why):
- Shift validity ≤ 12 h with revalidation every shift (Aramco GI 2.100 / HSG250) — wins over multi-day permits without revalidation.
- Hot work: fire watch **60 min** after work (NFPA 51B 2019) wins over 30 min (SBC 801/IFC); combustibles clearance **11 m** (NFPA 51B) wins over 10.7 m; hot work requires **0 % LEL** (Aramco-type practice) over < 10 % LEL.
- Gas limits take the lowest of TLV / REL / PEL (H₂S 1 ppm, CO 25 ppm).
- Excavation permit and protective system from **1.2 m** (Aramco CSM) over 1.5 m (OSHA 1926.652); PE design from **6.0 m** (rounded down from 6.1 m); egress travel **7.5 m** (rounded down from 7.6 m).
- Fall-arrest free fall ≤ 1.8 m and deceleration 1.07 m (OSHA) used in the clearance calculation even when the client accepts the manufacturer's value, whichever is larger.
- Any minimum distance computed by the platform is rounded **up** to 0.1 m; any maximum is rounded **down** (rule PT-21).
- A client or operator value stricter than a default here is entered in settings; settings can never be loosened below the "Allowed" range in §3.17.

## 3. Entities & fields

PDPL column: **none / personal / sensitive** (Phase 0 P1–P2). Every entity carries Phase 0 system fields (id UUID, created_at/by, updated_at/by), is audited (Phase 0 rule 35) and stores `seed_fake` (bool). AR label shown in UI.

### 3.1 Permit type configuration (reference, per project; HSE Manager edits within §3.17 ranges) — إعدادات أنواع التصاريح

| Code | EN / AR | Max duration (days) | Max shift (h) | Revalidation | Gas test | HSE review (high-risk) | Mandatory roles (besides receiver, issuer, area authority) | Mandatory documents |
|---|---|---|---|---|---|---|---|---|
| `general` | General / cold work — أعمال عامة (باردة) | 7 | 12 | each shift | if zone `gas_test_zone` or section flag `flammables_in_use` | no | supervisor | method statement (MS) |
| `hot_work` | Hot work — أعمال ساخنة | **1** ASSUMPTION | 12 | one handover allowed | if zone `gas_test_zone`, hazardous area ≠ none, or inside a confined space | if gas_test_zone, hazardous area, fire-system impairment or airside | fire watch, hot-work operative | MS |
| `confined_space` | Confined space entry — دخول الأماكن المحصورة | 1 | 12 | one handover allowed | always (pre-entry + continuous + recorded) | always | standby person, authorised gas tester, ≥ 1 entrant, rescue team lead | rescue plan, MS |
| `work_at_height` | Working at height — العمل على ارتفاع | 7 | 12 | each shift | no | if fall arrest, rope access or suspended access | supervisor; competent person (fall protection) when arrest used | rescue plan when arrest/rope/suspended; MS |
| `excavation` | Excavation — الحفر | 7 | 12 | each shift | if depth ≥ 1.2 m and zone gas_test_zone or `atmosphere_hazard` | if depth ≥ 1.2 m | excavation competent person | utility clearance; excavation plan; PE design when depth ≥ 6.0 m |
| `electrical_isolation` | Electrical work / isolation (LOTO) — الأعمال الكهربائية والعزل | 7 | 12 | each shift | no | if HV or energized work | isolation authority (electrical), authorised person (electrical, LV or HV) | isolation certificate; switching programme (HV) |
| `lifting` | Lifting operations — عمليات الرفع | 7 (routine) · **1** (critical) | 12 | each shift | no | if critical | crane operator, rigger, signaller; lift supervisor; appointed person (critical) | lift plan; critical lift plan (critical) |
| `radiography` | Industrial radiography — التصوير الإشعاعي الصناعي | 1 | 12 | none | no | always | radiation protection officer (RPO), ≥ 1 certified radiographer | NRRC licence, radiation protection plan |
| `airside_works` | Airside works — أعمال الجانب الجوي | 7 (and ≤ linked WAP valid_to) | 12 | each shift | no | if any zone in_movement_area | supervisor; escort as Phase 2 WA-11 | works safety plan ref (Phase 2 WA-6) |

Each type row also holds: `pre_issue_checklist` (codes, §3.16 list C), `closure_checklist` (list X), `mandatory_hazards` (list H, JS-4), `hook_requirements` per crew role/equipment (HK3-2), `ref_letter` for display (GW, HW, CS, WH, EX, EL, LF, RG, AW).

### 3.2 Zone PTW profile (1:1 with zone, created with defaults — rule PT-3) — ملف تصاريح العمل للمنطقة

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| zone_id | المنطقة | FK | Y | unique | Z-APR-21 | none |
| permit_required_all_work | تصريح لكل الأعمال | bool | Y | default true iff airside zone in_movement_area, or zone code listed by HSE Officer (e.g. crane exclusion zone) | true | none |
| gas_test_zone | منطقة تتطلب فحص غاز | bool | Y | presence of fuel, sewer, process or stored flammables/toxics | true (hydrant pits) | none |
| hazardous_area_class | تصنيف المنطقة الخطرة | enum | Y | `none`, `zone_0`, `zone_1`, `zone_2` (IEC 60079-10-1) | zone_2 | none |
| hazardous_area_note | ملاحظة التصنيف | string(200) | cond. | required iff class ≠ none | Within 3 m of hydrant pit valve chambers | none |
| default_exposure | التعرض الافتراضي | enum | Y | `outdoor_direct_sun` في الشمس المباشرة, `outdoor_shaded` خارجي مظلل, `indoor` داخلي | outdoor_direct_sun | none |
| fire_protection_present | أنظمة حماية من الحريق | bool | Y | sprinklers/detection in service in the zone | false | none |
| level_datum_note | مرجع المناسيب | string(100) | N | high-rise: how elevation_m is measured | Site datum ±0.00 = FFL ground | none |
| default_area_authority_ids | مسؤولو المنطقة الافتراضيون | FK user[] | N | users with an Active area_authority appointment covering the zone | [Fahad] | personal |

### 3.3 Zone adjacency (per project) — تجاور المناطق

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| zone_a_id, zone_b_id | المنطقتان | FK | Y | same project; a ≠ b; unordered pair unique | Z-PIERB, Z-MSCP | none |
| distance_m | المسافة (م) | decimal(7,1) | Y | ≥ 0; closest edge-to-edge; 0 = touching/overlapping | 40.0 | none |
| vertical_relation | العلاقة الرأسية | enum | Y | `none`, `a_above_b`, `b_above_a`, `overlapping` | none | none |

### 3.4 PTW appointment (functional authorisation, per project) — تعيين صلاحيات تصاريح العمل

Platform roles (Phase 0 §3.8) say what a user may see and do in the system; an appointment says that a named, competent person may act in a PTW function. No new platform roles are added (open question §10 Q2 of Phase 2 stays as is).

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| appointment_no | رقم التعيين | string | sys | `APT-<project>-<nnnn>` | APT-ANIA-EXP-0007 | none |
| function | الوظيفة | enum | Y | `issuer` مُصدِر, `area_authority` مسؤول المنطقة, `isolation_authority` مسؤول العزل, `gas_tester` فاحص غاز معتمد, `authorised_person` شخص مخوَّل | gas_tester | none |
| discipline | التخصص | enum | cond. | isolation_authority: `electrical_lv`, `electrical_hv`, `mechanical_process`; authorised_person: `electrical_lv`, `electrical_hv`, `lifting_appointed_person` (planner), `lift_supervisor`, `excavation_competent_person`, `fall_protection_competent_person`, `radiation_protection_officer`, `cse_rescue_lead` | — | none |
| holder_user_id / holder_worker_id | صاحب التعيين | FK / FK | one Y | issuer, area_authority, isolation_authority: user required (they sign in the platform); gas_tester, authorised_person: worker or user; a user acting as worker is linked through worker.user_id | Salem (worker WKR-000018) | personal |
| permit_types | أنواع التصاريح | enum[] | Y | ≥ 1 of §3.1; issuer appointments list the types they may issue | [confined_space, hot_work] | none |
| site_ids / zone_ids | المواقع / المناطق | FK[] | Y / N | empty zone_ids = all zones of the sites | [S-LAND] | none |
| basis | أساس التعيين | text(300) | Y | course, assessment or certificate refs; P3 hint | Aramco-equivalent gas tester course, assessed 2026-04-20 | personal |
| valid_from / valid_to | من / إلى | date | Y / Y | valid_to ≤ valid_from + `appointment_max_months` | 2026-04-21 / 2026-10-20 | personal |
| appointed_by_user_id | عيّنه | FK | sys | capability 100 (issuer appointments: HSE Manager only) | Noura | personal |
| status | الحالة | enum | Y | §4.7 | active | none |

### 3.5 Permit (core) — تصريح العمل

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| permit_no | رقم التصريح | string | sys | `PTW-<project>-<yyyy>-<nnnn>`; display adds type letters, e.g. `PTW-RBT-52-2026-0290 · LF` | PTW-ANIA-EXP-2026-0413 | none |
| project_id, site_id | المشروع، الموقع | FK | Y | project Active; site Active | ANIA-EXP, S-LAND | none |
| zone_ids | المناطق | FK[] | Y | 1–3 zones, all of the site, none Archived or Temporarily Closed | [Z-MSCP] | none |
| location_desc | وصف الموقع | string(200) | Y | — | Stormwater manhole MH-07, level B1 ramp | none |
| grid_x_m / grid_y_m | إحداثيات الشبكة (م) | decimal(8,1) | N | site setting-out grid in metres; both or neither | 128.0 / 51.0 | none |
| level_code / elevation_m | المستوى / المنسوب (م) | string(10) / decimal(7,2) | N / cond. | elevation_m required when level_code set; relative to the zone's level datum | B1 / −3.50 | none |
| engagement_id | المقاول المنفذ | FK | Y | engagement on project; contractor Approved and not Suspended (PT-6) | RAWABI@ANIA-EXP | none |
| work_types | أنواع العمل | enum[] | Y | ≥ 1 of §3.1; `airside_works` added automatically for airside zones (AW-1) | [confined_space] | none |
| primary_type | النوع الرئيسي | enum | Y | ∈ work_types; for KPI attribution | confined_space | none |
| high_risk | عالي الخطورة | bool | derived | any type row's HSE-review condition true (§3.1, PT-9) | true | none |
| title / scope_en / scope_ar | العنوان / نطاق العمل | string(150) / text(1000) ×2 | Y / Y / N | P3 hint | Desilting and inspection of MH-07 | none |
| exposure | التعرض | enum | Y | default from zone profile; `outdoor_direct_sun`, `outdoor_shaded`, `indoor` | indoor | none |
| valid_from_at / valid_to_at | ساري من / إلى | timestamp (local) | Y | duration ≤ min(max duration of each type) (PT-11) | 2026-10-06 07:00 / 2026-10-06 19:00 | none |
| windows | فترات العمل | list {start_local, end_local, weekdays[]} | Y | 1–3; may cross midnight (as Phase 2 WA-9); HT-2 | [{07:00, 19:00, all}] | none |
| receiver_user_id | مستلم التصريح | FK | Y | Active permit_receiver role assignment on this engagement (Phase 0 rule 10, C1) | Faris | personal |
| area_authority_user_id | مسؤول المنطقة | FK | Y at Request | Active area_authority appointment covering every zone (PR-3) | Fahad | personal |
| issuer_user_id | مُصدِر التصريح | FK | Y at Approve | Active issuer appointment for every work type and the site (PR-2) | Khalid | personal |
| hse_reviewer_user_id | مراجع السلامة | FK | cond. | required iff high_risk; capability 86 | Noura | personal |
| supervisor_worker_id | المشرف | FK | Y | crew member with crew_role supervisor | WKR-000021 | personal |
| jsa_id | تحليل سلامة العمل | FK | Y at Request | JSA instance status Approved before Approve (JS-6) | JSA-ANIA-EXP-2026-0413 | none |
| documents | المستندات | list {doc_type, ref, revision, file, approved_by_text, valid_until} | cond. | per §3.1 mandatory documents; doc_type list D | [{rescue_plan, RP-MSCP-02, B}] | none |
| linked_wap_ids | تصاريح دخول المنطقة | FK[] | cond. | AW-2 | [WAP-ANIA-EXP-2026-0031] | none |
| linked_obs_ids | موافقات العوائق | FK[] | cond. | LF-9, AW-5 | [OBS-ANIA-EXP-2026-0004] | none |
| isolation_cert_ids | شهادات العزل | FK[] | cond. | required for electrical_isolation; optional for any type that needs energy isolation (IS-1) | [ISO-ANIA-EXP-2026-0061] | none |
| simops_record_ids | سجلات التنسيق | FK[] | sys | SM-6 | [] | none |
| conditions_en / conditions_ar | شروط إضافية | text(1000) | N | issuer conditions | Stop on any gas alarm; ventilation fan to run continuously | none |
| emergency_info | معلومات الطوارئ | text(300) | Y | assembly point, emergency number, nearest first-aid/clinic; no personal mobiles of workers | Assembly point AP-3; site emergency ext. 999 (fake) | none |
| blockers | المعوقات | list {code, detail} | sys | computed (PT-16) | [] | none |
| warnings | التنبيهات | list {code, detail} | sys | computed (e.g. HOOK_NOT_AVAILABLE, EXPIRING_7D) | [HOOK_NOT_AVAILABLE] | none |
| status | الحالة | enum | Y | §4.1 | active | none |
| status_reason | سبب الحالة | enum + text(500) | cond. | list SR (§3.16) for Suspended/Cancelled | gas_test_failed | none |
| current_shift_id | الوردية الحالية | FK | sys | §3.12 | — | none |
| print_token | رمز QR للتصريح | string | sys | Phase 2 §3.20 format with new kind `PT` (§11 change) | HSE2:PT:… | none |
| incident_ids | الحوادث المرتبطة | FK[] | N | Phase 1 incidents (§11 change to Phase 1 §3.5) | — | none |

### 3.6 Permit crew and equipment lines — طاقم ومعدات التصريح

**Crew line** (one per person on the permit):

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| worker_id | العامل | FK | Y | Phase 2 worker with a Mobilised deployment on the project covering the site; not Banned | WKR-000016 | personal |
| crew_role | دور العامل | enum | Y | list CR (§3.16) | entrant | personal |
| key_role | دور رئيسي | bool | derived | crew_role ∈ {supervisor, fire_watch, standby_person, gas_tester, crane_operator, rigger, signaller, lift_supervisor, radiographer, rpo, competent_person, hot_work_operative, rescue_lead} | false | none |
| appointment_id | التعيين | FK | cond. | required for gas_tester, competent_person, rpo, lift_supervisor (PR-4) | APT-ANIA-EXP-0011 | none |
| escort_worker_id | المرافق | FK | cond. | airside escorted pass holders (AW-3) | WKR-000013 | personal |
| eligibility | الأهلية | list (E results) | sys | Phase 2 E(worker, zone, at, ptw) + HK3 hooks | — | personal |
| status | الحالة | enum | sys | `listed` مدرج, `excluded` مستبعد (with reason), `removed` محذوف | listed | personal |

**Equipment line**:

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| vehicle_id | المركبة/المعدة المسجلة | FK | one of | Phase 2 vehicle of the engagement or an ancestor | VEH-0003 | none |
| equipment_tag | المعدة (رقم الوسم) | {category, tag, description, max_working_height_m} | one of | category from list EQ (§3.16); tag unique per project; until Phase 4 the hook subject is `equipment_tag` (§11) | {tower_crane, TC-01, 12 t flat-top, 236.00} | none |
| use | الاستخدام | enum | Y | `lifting_appliance`, `lifting_accessory`, `access_equipment`, `welding_set`, `gas_detector`, `ventilation`, `rescue_equipment`, `excavating_plant`, `radiography_source`, `other` | lifting_appliance | none |
| equipment_item_id | المعدة في سجل المعدات | FK | N | v1.1: Phase 4 equipment item (`4-third-party-cert.md` §3.4); resolved from vehicle_id or from {category, tag} on the permit's project when blank | EQP-000101 | none |
| operator_worker_id | المشغّل | FK | cond. | v1.1: required when the item's category has an operator code in Phase 4 list EQC (HK4-9); must also be on the crew; the operator hook is called with context equipment_ref | WKR-000102 | personal |

### 3.7 Type sections (one per work type on the permit) — أقسام نوع العمل

Fields below are required when the type is on the permit unless marked N. Each section also carries its pre-issue checklist answers `{code → yes / no / n.a.}` (list C) and closure checklist answers (list X).

**3.7.1 Hot work — الأعمال الساخنة**

| Field | AR label | Type | Validation | Example |
|---|---|---|---|---|
| hot_work_kind | نوع العمل الساخن | enum[] | `arc_welding`, `gas_welding_cutting`, `grinding`, `torch_roofing`, `thermal_spraying`, `brazing_soldering`, `other_spark_flame` | [arc_welding, grinding] |
| combustibles_cleared_radius_m | نصف قطر إزالة المواد القابلة للاشتعال | decimal(4,1) | ≥ `hw_combustible_clearance_m` (11.0) or `combustibles_protected` = true with method | 11.0 |
| combustibles_protected_method | طريقة حماية المواد | text(200) | cond. | Fire blankets over timber formwork |
| fire_extinguishers | طفايات الحريق | list {type, count, distance_m} | ≥ 1 with distance_m ≤ `hw_extinguisher_max_m` (9.0); type ∈ `dcp_abc_6kg`, `co2_5kg`, `foam_9l`, `water_9l` | [{dcp_abc_6kg, 2, 4.0}] |
| fire_blanket | بطانية حريق | bool | must be true | true |
| work_height_above_floor_m | ارتفاع العمل عن الأرضية | decimal(5,2) | ≥ 0 | 0.00 |
| openings_below_protected | حماية الفتحات السفلية | enum | `n.a.`, `yes`; `yes` required when work_height_above_floor_m > 0 or floor openings within the clearance radius (HW-6) | n.a. |
| fire_system_impairment | تعطيل نظام الحريق | bool | HW-8 | false |
| impairment_hours_24h / civil_defense_notified_at / impairment_ref | ساعات التعطيل / إبلاغ الدفاع المدني | decimal / timestamp / string(40) | cond. HW-8 | — |
| cylinders | الأسطوانات | enum | `none`, `oxy_fuel`, `fuel_only`, `inert_only` | oxy_fuel |
| flashback_arrestors_both_ends | مانع الارتداد في الطرفين | bool | must be true when oxy_fuel | true |
| hot_work_ended_at | وقت انتهاء العمل الساخن | timestamp | set by receiver; starts fire watch (HW-4) | 2026-10-06 15:20 |
| fire_watch_until | مراقبة الحريق حتى | timestamp | derived = hot_work_ended_at + `fire_watch_post_minutes` | 16:20 |

**3.7.2 Confined space entry — دخول الأماكن المحصورة**

| Field | AR label | Type | Validation | Example |
|---|---|---|---|---|
| space_id_desc | وصف المكان المحصور | string(150) | — | Manhole MH-07, 4.2 m deep, Ø 1.2 m |
| space_hazards | مخاطر المكان | enum[] | `toxic`, `flammable`, `oxygen_deficiency`, `oxygen_enrichment`, `engulfment`, `entrapment_configuration`, `heat`, `mechanical`, `electrical`, `other` | [toxic, oxygen_deficiency, heat] |
| isolations_required | عزل مطلوب | bool | if true, ≥ 1 isolation certificate linked (CS-5) | false |
| ventilation | التهوية | enum | `natural`, `forced_supply`, `forced_extract`, `none_justified`; `none_justified` needs justification | forced_supply |
| continuous_monitor_detector_id | جهاز المراقبة المستمرة | FK | gas detector in service (GT-5); worn by an entrant | GD-ANIA-003 |
| internal_temp_c | درجة الحرارة الداخلية | decimal(4,1) | recorded at each gas test; HT-6 | 34.0 |
| rescue_method | طريقة الإنقاذ | enum | `non_entry_tripod_winch`, `entry_rescue_team`, `external_rescue_service` (only with response ≤ `cse_rescue_max_minutes` documented) | non_entry_tripod_winch |
| rescue_equipment_checked | فحص معدات الإنقاذ | bool | must be true | true |
| communication_method | وسيلة الاتصال | enum | `voice_visual`, `radio`, `rope_signal` | voice_visual |
| entry_log | سجل الدخول والخروج | list {worker_id, in_at, out_at} | sys/receiver; CS-7 | — |

**3.7.3 Working at height — العمل على ارتفاع**

| Field | AR label | Type | Validation | Example |
|---|---|---|---|---|
| max_fall_height_m | أقصى ارتفاع سقوط | decimal(6,2) | ≥ `wah_permit_threshold_m` (1.8) unless the activity is listed in WH-1 | 152.00 |
| access_method | وسيلة الوصول | enum[] | `fixed_platform`, `scaffold`, `mewp`, `ladder`, `mast_climber`, `suspended_platform_bmu`, `rope_access`, `slab_edge` | [slab_edge] |
| fall_protection | الحماية من السقوط | enum | `collective_only` (guardrails/nets), `restraint`, `arrest_lanyard`, `arrest_srl`, `rope_access_two_rope` | arrest_srl |
| anchor_desc / anchor_rating_kn | نقطة التثبيت / تحملها | string(150) / decimal(5,1) | rating ≥ 22.2 kN per person, or certified engineered system (WH-4) | Cast-in anchor CA-38-12 / 22.2 |
| lanyard_length_m | طول الحبل | decimal(3,2) | cond. arrest_lanyard; ≤ 1.80 | — |
| srl_required_clearance_m | الخلوص المطلوب (حسب الصانع) | decimal(4,2) | cond. arrest_srl | 2.40 |
| available_clearance_m | الخلوص المتاح أسفل نقطة العمل | decimal(5,2) | cond. arrest_*; WH-5 | 4.00 |
| scaffold_tag_ref | رقم بطاقة السقالة | string(30) | cond. access_method ∋ scaffold; hook `equipment_certificate: SCAFFOLD-TAG` (HK3-2); v1.1: resolved against the Phase 4 scaffold register of the permit's project (`4-third-party-cert.md` SF-1); yellow-tag restrictions are copied into permit conditions (SF-6) | — |
| drop_zone_controlled | التحكم بمنطقة سقوط الأشياء | bool | must be true | true |
| tool_tethering | ربط الأدوات | bool | must be true when max_fall_height_m > 6.0 ASSUMPTION | true |

**3.7.4 Excavation — الحفر**

| Field | AR label | Type | Validation | Example |
|---|---|---|---|---|
| max_depth_m | أقصى عمق | decimal(5,2) | > 0 | 1.30 |
| method | طريقة الحفر | enum | `hand_dig`, `mechanical`, `vacuum`, `trenchless` | hand_dig |
| soil_type | نوع التربة | enum | `rock`, `type_a`, `type_b`, `type_c` (OSHA App. A); unknown → `type_c` | type_c |
| protective_system | نظام الحماية | enum | `none_lt_1_2m`, `sloping`, `benching`, `trench_box`, `shoring`, `engineered_design`; EX-2 | sloping |
| slope_ratio_h_v | نسبة الميل | decimal(3,2) | cond. sloping; ≥ 1.50 for type_c, 1.00 type_b, 0.75 type_a (OSHA App. B) | 1.50 |
| pe_design_ref | مرجع التصميم الهندسي | string(40) | cond. depth ≥ `ex_pe_design_depth_m` (6.0) | — |
| utility_clearance_ref | مرجع تصريح الخدمات المدفونة | string(40) | Y; drawings + scan (CAT/Genny) by the utility owner or airport operator for airside | AOP-UTIL-TEST-0419 |
| services_within_hand_dig_zone | خدمات ضمن منطقة الحفر اليدوي | bool | if true, method within `ex_hand_dig_distance_m` of the service must be hand_dig or vacuum (EX-4) | true |
| spoil_setback_m | مسافة الأتربة عن الحافة | decimal(4,2) | ≥ `ex_spoil_setback_m` (0.6) | 1.00 |
| egress | وسيلة الخروج | enum | `ladder`, `ramp`, `stairs`; travel to nearest ≤ `ex_egress_max_m` (7.5) when depth ≥ 1.2 m | ladder |
| atmosphere_hazard | احتمال جو خطر | bool | true near fuel lines, sewers, landfill, or zone gas_test_zone | false |
| daily_inspection | الفحص اليومي | list {inspected_at, by appointment, result, after_rain_or_event} | EX-6 | — |

**3.7.5 Electrical work / isolation — الأعمال الكهربائية**

| Field | AR label | Type | Validation | Example |
|---|---|---|---|---|
| system_voltage_v | جهد النظام | int | > 0 | 400 |
| voltage_class | فئة الجهد | enum | derived: `elv` ≤ 50 V AC/120 V DC, `lv` ≤ 1,000 V AC/1,500 V DC, `hv` above | lv |
| work_condition | حالة العمل | enum | `electrically_safe` (isolated, proven dead), `energized` (EL-3) | electrically_safe |
| test_for_dead | التحقق من انعدام الجهد | {done_at, by_worker_id, instrument_tag, proving_unit_used, live_dead_live} | required for electrically_safe before Issue | {2026-10-05 08:20, WKR…, VT-ANIA-07, true, true} |
| hv_earths_applied | تطبيق التأريض (HV) | bool | must be true for hv | — |
| switching_programme_ref | مرجع برنامج التحويل | string(40) | cond. hv | — |
| energized_justification | مبرر العمل المكهرب | enum + text | cond. energized: `greater_hazard_if_deenergized`, `infeasible_due_to_design`, `diagnostic_testing_only` | — |
| limited_approach_m / restricted_approach_m | حدود الاقتراب | decimal(4,2) | cond. energized; from NFPA 70E tables `VERIFY` | 1.07 / 0.30 |
| incident_energy_cal_cm2 / arc_ppe_category | طاقة القوس / فئة المعدات | decimal(5,1) / int 1–4 | cond. energized; arc rating of PPE ≥ incident energy | — |

**3.7.6 Lifting — عمليات الرفع**

| Field | AR label | Type | Validation | Example |
|---|---|---|---|---|
| appliance | معدة الرفع | equipment line | use = lifting_appliance; exactly one per lift plan (multi-crane = one per crane, `tandem` = true) | TC-01 |
| tandem | رفع مشترك | bool | true ⇒ critical | false |
| load_desc / load_weight_t | الحمولة / وزنها (طن) | string(150) / decimal(7,3) | > 0; certified or calculated weight | Precast stair flight PS-38 / 4.200 |
| rigging_weight_t | وزن أدوات الربط | decimal(6,3) | ≥ 0; incl. spreader, slings, shackles; and hook block when the chart excludes it | 0.150 |
| radius_m / rated_capacity_t | نصف القطر / الحمولة المقررة | decimal(5,2) / decimal(7,3) | from the manufacturer's chart for the configuration, at the maximum radius of the lift | 42.00 / 5.000 |
| capacity_pct | نسبة الاستخدام | decimal(5,1) | derived §6.6 | 87.0 |
| critical | رفع حرج | bool | derived LF-2 | true |
| critical_reasons | أسباب الرفع الحرج | enum[] | derived LF-2 | [capacity] |
| personnel_lift | رفع أشخاص | bool | man-basket; LF-7 | false |
| wind_limit_ms | حد سرعة الرياح | decimal(4,1) | ≤ manufacturer's in-service limit; default `lift_wind_limit_ms` (9.8) when the plan gives none; personnel lifts ≤ `man_basket_wind_limit_ms` (7.0) | 13.0 |
| wind_reading | قراءة الرياح | list {measured_at, speed_ms, source} | at Issue and each revalidation (LF-6) | {06:20, 8.2, anemometer TC-01} |
| exclusion_radius_m | نصف قطر منطقة الحظر حول نقطة الإنزال | decimal(5,1) | ≥ 3.0 | 5.0 |
| landing_grid_x_m / landing_grid_y_m | إحداثيات نقطة الإنزال | decimal(8,1) | Y when appliance is a crane | 45.0 / 22.0 |
| slew_radius_m / appliance_grid_x_m / appliance_grid_y_m | نصف قطر الدوران / موقع الرافعة | decimal | cranes | 60.0 / 60.0 / 30.0 |
| ground_bearing_checked | فحص تحمل التربة | bool | mobile/crawler cranes: must be true | — |
| overhead_lines_within_6m | خطوط هوائية ضمن 6 م | bool | true ⇒ critical (power-line rules 1926.1408) | false |

**3.7.7 Radiography — التصوير الإشعاعي**

| Field | AR label | Type | Validation | Example |
|---|---|---|---|---|
| source_type | نوع المصدر | enum | `ir_192`, `se_75`, `co_60`, `x_ray` | ir_192 |
| activity_gbq | النشاط الإشعاعي (GBq) | decimal(7,1) | > 0 for isotopes | 1,110.0 |
| xray_dose_rate_1m_usv_h | معدل الجرعة على 1 م (أشعة سينية) | decimal(10,1) | cond. x_ray (from the set's datasheet) | — |
| collimator_transmission | معامل نفاذ الموجه | decimal(6,4) | 0 < t ≤ 1; 1 = none | 0.0625 |
| computed_barrier_m | المسافة المحسوبة للحاجز | decimal(6,1) | derived §6.7 | 34.7 |
| planned_barrier_m | مسافة الحاجز المخططة | decimal(6,1) | ≥ computed_barrier_m (RG-3) | 40.0 |
| barrier_survey | قياس الحاجز | list {measured_at, max_usv_h, meter_tag} | before first exposure; max ≤ `rg_barrier_limit_usv_h` | {22:35, 5.8, SM-NJ-02} |
| nrrc_licence_no / licence_valid_until | رخصة الهيئة / صلاحيتها | string(40) / date | valid on every permit date | NRRC-TEST-RL-0042 / 2027-03-31 |
| dosimetry_confirmed | التأكد من أجهزة قياس الجرعة | bool | personal dosimeter + alarming ratemeter for each radiographer (no dose values stored, P3-4) | true |
| source_returned_verified | التأكد من إعادة المصدر | {at, survey_usv_h} | closure (X list); reading ≤ 2 × background ASSUMPTION | {04:40, 0.2} |

**3.7.8 Airside works — أعمال الجانب الجوي**

| Field | AR label | Type | Validation | Example |
|---|---|---|---|---|
| wap_id | تصريح دخول المنطقة | FK | Active Phase 2 WAP covering every airside zone (AW-2) | WAP-ANIA-EXP-2026-0031 |
| ntm_ids | NOTAM | FK[] | derived from the WAP (read-only) | [NTM-ANIA-EXP-2026-0012] |
| operator_works_permit_ref | مرجع تصريح المشغل | string(40) | N; required when the operator issues its own (§10 Q10) | — |
| fod_control_plan | خطة التحكم بالأجسام الغريبة | bool | must be true when any zone fod_control_required | true |
| aircraft_proximity | قرب الطائرات | enum | `stand_closed_notam`, `stand_closed_operator`, `no_stand_in_zone`, `live_stand_adjacent` | no_stand_in_zone |
| hydrant_operator_clearance_ref | مرجع موافقة مشغل الوقود | string(40) | cond. AW-6 | — |
| ops_handback_ref | مرجع التسليم للعمليات | string(40) | closure for movement-area zones (AW-8) | AOCC-HB-TEST-0412 |

### 3.8 JSA (template and permit instance) and RA/MS documents — تحليل سلامة العمل وتقييم المخاطر

**JSA** (`JSA-<project>-<yyyy>-<nnnn>`; template = `is_template` true, owned by the project or an engagement):

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| is_template / template_id | قالب / القالب المصدر | bool / FK | Y / N | instance copies the template's steps; edits allowed | false / JSA-T-RBT-52-0004 | none |
| work_types | أنواع العمل | enum[] | Y | ⊇ permit work_types when attached (JS-3) | [work_at_height] | none |
| title_en / title_ar | العنوان | string(150) ×2 | Y / N | — | Slab-edge works L38 | none |
| steps | الخطوات | list {step_no, description_en/ar, hazards[]} | Y | ≥ 1 step | — | none |
| hazard line | خط الخطر | {hazard_code (list H), description, initial_l, initial_s, controls[{text, level}], residual_l, residual_s} | Y | L, S integers 1–5; S scale = Phase 1 list S; control level = Phase 1 CA control_level enum | fall_from_height, 4, 5, …, 2, 5 | none |
| initial_score / residual_score / band | الدرجة / التصنيف | int / int / enum | derived §6.1 | 20 / 10 / high | none |
| governing_residual_band | التصنيف المتبقي الحاكم | enum | derived = highest residual band of all lines | high | none |
| residual_acceptance | قبول المخاطر المتبقية | list {band, accepted_by_user_id, accepted_at, alarp_justification} | cond. | JS-7 | {high, Lina, …, "Collective edge protection installed; arrest only for final 1 m"} | personal |
| review_due_on | موعد المراجعة | date | templates | approved date + `jsa_review_months` | 2027-06-30 | none |
| status | الحالة | enum | Y | §4.3 | approved | none |
| crew_briefings | توعية الطاقم | list {shift_id, worker_ids, briefed_by_user_id, at} | sys | SH-4 | — | personal |

**Document** (on the permit; list D): `method_statement`, `risk_assessment`, `lift_plan`, `critical_lift_plan`, `rescue_plan`, `excavation_plan`, `pe_design`, `utility_drawing`, `switching_programme`, `radiation_protection_plan`, `nrrc_licence`, `fire_impairment_notice`, `other`. Fields: ref (string 40, Y), revision (string 6, Y), file (PDF/image ≤ 20 MB, N), approved_by_text (string 120, Y for lift/critical-lift/rescue/PE plans), valid_until (date, N). PDPL: none (personal possible in files — P3 hint "no IDs").

### 3.9 Gas detector and bump test — جهاز كشف الغاز واختبار الاستجابة

**Detector**:

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| detector_no | رقم الجهاز | string | sys | `GD-<project short>-<nnn>` | GD-ANIA-003 | none |
| engagement_id | المالك | FK | Y | — | RAWABI@ANIA-EXP | none |
| make_model / serial | الطراز / الرقم التسلسلي | string(80) / string(40) | Y | serial unique per project | 4-gas multi detector (fake) / TESTSN-GD-0003 | none |
| sensors | الحساسات | enum[] | Y | ⊆ {o2, lel, h2s, co, voc_pid, nh3, so2, other}; o2 and lel required for any test of CSE or hot work | [o2, lel, h2s, co] | none |
| lel_reference_gas | غاز المعايرة لـ LEL | enum | Y if lel | `methane`, `pentane`, `propane`, `hydrogen` | pentane | none |
| calibrated_on / calibration_cert_ref | تاريخ المعايرة / الشهادة | date / string(40) | Y | ≤ today | 2026-07-02 / CAL-TEST-0003 | none |
| calibration_body_id | جهة المعايرة | FK | N | v1.1: Phase 4 TPI of kind calibration_lab (`4-third-party-cert.md` EQ-3) | GCAL | none |
| calibration_due_on | استحقاق المعايرة | date | sys | min(calibrated_on + `detector_calibration_interval_days`, certificate's due date if entered) | 2026-12-29 | none |
| status | الحالة | enum | Y | §4.6 | in_service | none |

**Bump test**: detector_id, tested_at (≤ now), result (`pass` / `fail`), sensors_responded[] (must equal detector sensors for pass), tested_by (user or worker), gas cylinder lot/expiry (string / date > tested date). PDPL: personal (tester).

### 3.10 Gas test — فحص الغاز

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| test_no | رقم الفحص | string | sys | `GT-<permit_no>-<nn>` | GT-PTW-ANIA-EXP-2026-0413-03 | none |
| permit_id / shift_id | التصريح / الوردية | FK | Y | permit in Approved, Issued, Active or Suspended | — | none |
| test_type | نوع الفحص | enum | Y | `pre_issue` قبل الإصدار, `pre_entry` قبل الدخول, `periodic` دوري, `post_break` بعد الاستراحة, `revalidation` عند إعادة التفعيل, `post_alarm` بعد الإنذار | post_break | none |
| tested_at | وقت الفحص | timestamp | Y | ≤ now; not earlier than 60 min before saving ASSUMPTION (no back-dating) | 2026-10-06 09:48 | none |
| tester_appointment_id | فاحص الغاز | FK | Y | Active gas_tester appointment covering the zone and permit type (GT-2) | APT-ANIA-EXP-0011 | personal |
| recorded_by_user_id / tester_signature | المسجِّل / توقيع الفاحص | FK / image | sys / cond. | signature required when the tester has no user account | Faris / — | personal |
| detector_id | الجهاز | FK | Y | GT-5 | GD-ANIA-003 | none |
| readings | القراءات | list {point ∈ top/middle/bottom/at_work_point/outside, o2_pct, lel_pct, h2s_ppm, co_ppm, other {gas, value, unit}} | Y | CSE: ≥ 3 points (top, middle, bottom) for pre_entry/pre_issue; other: ≥ 1; values within sensor range | see Y2 | none |
| applicable_limits | الحدود المطبقة | JSON | sys | strictest across the permit's types (§6.2) | — | none |
| result | النتيجة | enum | sys | `pass` / `fail` with codes `O2_OUT_OF_RANGE`, `LEL_ABOVE_LIMIT`, `H2S_ABOVE_LIMIT`, `CO_ABOVE_LIMIT`, `OTHER_ABOVE_LIMIT` | pass | none |
| valid_for_start_until | صالح لبدء العمل حتى | timestamp | sys | tested_at + `gas_pre_start_validity_minutes` | 10:18 | none |
| next_due_at | الفحص التالي مستحق | timestamp | sys | §6.3 | 10:48 | none |

### 3.11 Isolations / LOTO — العزل والقفل والوسم

**Isolation certificate** (`ISO-<project>-<yyyy>-<nnnn>`):

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| equipment_desc | المعدة/النظام المعزول | string(200) | Y | — | Feeder Q12 MDB-T3-02 → MCC-3 (Pier B plant room) | none |
| energy_types | أنواع الطاقة | enum[] | Y | `electrical`, `mechanical`, `hydraulic`, `pneumatic`, `process_fluid`, `thermal`, `gravity`, `stored_spring`, `chemical`, `radiation` | [electrical] | none |
| isolation_authority_user_id | مسؤول العزل | FK | Y | Active isolation_authority appointment with matching discipline (electrical_hv for hv) | Nasser | personal |
| lockbox_id | صندوق الأقفال | FK | Y | lock of type lockbox, available or already this certificate's | LB-ANIA-012 | none |
| points | نقاط العزل | list (below) | Y | ≥ 1 | 2 points | none |
| long_term | عزل طويل الأمد | bool | derived | open > `long_term_isolation_days` | false | none |
| status | الحالة | enum | Y | §4.4 | verified | none |

**Isolation point**: point_no; energy_type; device_tag (string 40, e.g. `Q12`); location; method enum (`breaker_racked_out`, `fuse_removed`, `isolator_open_locked`, `cable_disconnected`, `earth_applied`, `valve_closed_locked`, `spade_blind`, `double_block_bleed`, `disconnect_removed_spool`, `mechanical_pin_block`, `bleed_vent_drain`, `other`); isolation_lock_id (FK lock type isolation_lock); tag_no (string 20 — danger/hold tag); applied_by_user_id / applied_at; verified_by (user or worker) / verified_at / verification_method enum (`try_out_start_attempt`, `test_for_dead`, `pressure_gauge_zero`, `visual_air_gap`, `other`); removed_by_user_id / removed_at. PDPL: personal (persons).

**Lock** (register): lock_no (`L-<project short>-<nnnn>` isolation lock, `P-…` personal lock, `LB-…` lockbox), lock_type (`isolation_lock` قفل عزل, `personal_lock` قفل شخصي, `lockbox` صندوق أقفال جماعي), holder_worker_id (personal locks: one holder, one key), status (`available`, `applied`, `lost`, `cut`, `retired`). PDPL: personal (holder).

**Personal lock event**: lock_id, lockbox_id, worker_id, applied_at, removed_at, removed_by (holder or `cut`), cut_record {approved_by_user_id (HSE Manager), supervisor_confirmed_absent_at, contact_attempts text, worker_informed_at} (IS-9). PDPL: personal.

### 3.12 SIMOPS rule, conflict and coordination record — العمليات المتزامنة

**SIMOPS rule** (reference matrix, HSE Manager editable, codes immutable): rule_code (`SM-Rnn`), type_a, type_b (or `any`), condition (§5.6 table), threshold_m (decimal), result (`prohibited` محظور, `conditional` مشروط, `allowed` مسموح), required_controls_en/ar (text). Defaults in §5.6 SM-3.

**Conflict** (system-created when a check finds a rule match): conflict_no `SIM-<project>-<yyyy>-<nnnn>`, permit_a_id, permit_b_id, rule_code, distance_m (computed or adjacency), overlap_from / overlap_to (timestamps of the first overlap), result, status (`open` مفتوح, `coordinated` منسَّق, `resolved_by_change` حُلّ بالتعديل, `closed` مغلق), detected_at.

**Coordination record** (for `conditional`): conflict_id, agreed_controls_en/ar (text ≥ 30 chars), signed_by issuer of permit A and issuer of permit B (one signature if the same user, plus the area authority of the zone), signed_at, valid_until (= earliest valid_to of the two permits). PDPL: personal (signatories).

### 3.13 Permit shift and handover — وردية التصريح والتسليم

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| shift_no | رقم الوردية | int | sys | 1, 2, … per permit | 2 | none |
| started_at / planned_end_at | البداية / النهاية المخططة | timestamp | sys | planned_end_at = min(started_at + `ptw_shift_max_hours`, current window end, valid_to_at) | 07:10 / 19:00 | none |
| receiver_user_id / issuer_user_id | المستلم / المُصدِر | FK | Y | issuer: Active issuer appointment; receiver: permit_receiver on the engagement | — | personal |
| gas_test_id | فحص الغاز | FK | cond. | gas test required (GT-1) | GT-…-01 | none |
| ambient_temp_c | درجة الحرارة | decimal(4,1) | Y if exposure outdoor | 0–60 | 41.5 | none |
| crew_present | الطاقم الحاضر | worker_id[] | Y | ⊆ listed crew; each briefed this shift (SH-4) | — | personal |
| pauses | فترات التوقف | list {from, to, reason ∈ break / prayer / weather / other} | N | recorded by the receiver; work stopped, permit stays Active; a pause never spans the shift end; CSE: entry log shows 0 inside during a pause | [{09:15, 09:50, break}] | none |
| ended_at / end_type | الانتهاء / نوعه | timestamp / enum | sys | `handover` تسليم, `shift_end` نهاية الوردية, `suspended` إيقاف, `lapsed` انقضاء دون تسليم, `closed` إغلاق, `expired` انتهاء | — | none |

**Handover**: from_shift_id, to_receiver_user_id, to_issuer_user_id, initiated_at, accepted_at, status (`initiated` بانتظار القبول, `accepted` مقبول, `lapsed` منقضي), notes_en/ar (text 500: status of work, hazards changed, isolations, entrants inside). PDPL: personal.

### 3.14 Suspension event — حدث الإيقاف

permit_id, suspended_at, reason (list SR), routine (bool — true for `shift_end`, `midday_ban`), raised_by_user_id (null = system), detail (text 500; required for manual), auto_source_ref (e.g. WAP no, gas test no, audit no, ops event no), resumed_at, resumed_by_user_id, resume_gas_test_id. PDPL: personal (users).

### 3.15 PTW audit — تدقيق تصاريح العمل

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| audit_no | رقم التدقيق | string | sys | `PTA-<project>-<yyyy>-<nnnnn>` | PTA-ANIA-EXP-2026-00377 | none |
| audit_type | نوع التدقيق | enum | Y | `field` ميداني (permit Issued/Active/Suspended at audited_at), `document_review` مراجعة مستندية (Closed/Expired permit), `unpermitted_work` عمل دون تصريح | field | none |
| permit_id | التصريح | FK | cond. | required for field and document_review; null for unpermitted_work | PTW-ANIA-EXP-2026-0412 | none |
| site_id / zone_id / engagement_id | الموقع / المنطقة / المقاول | FK | Y | from permit, or entered for unpermitted_work | S-LAND / Z-PIERB / NAJD | none |
| auditor_user_id | المدقق | FK | sys | capability 101; ≠ issuer, receiver, area authority and HSE reviewer of the permit (AU-2) | Noura | personal |
| audited_at | وقت التدقيق | timestamp | Y | ≤ now | 2026-10-06 09:20 | none |
| items | البنود | list {code (list A), answer ∈ compliant / non_compliant / n.a., severity ∈ minor / major / critical, note, photo} | Y | every item of the permit's types answered (AU-3); severity defaults to the item default and may be raised, not lowered | — | personal (photo possible) |
| applicable_count / compliant_count / score_pct | العدد / المطابق / النسبة | int / int / decimal(5,1) | derived | §6.8 | 18 / 17 / 94.4 | none |
| critical_count | عدد المخالفات الحرجة | int | derived | — | 0 | none |
| ca_ids | الإجراءات التصحيحية | FK[] | cond. | AU-5 | — | none |
| status | الحالة | enum | Y | §4.9 | completed | none |

### 3.16 Reference lists (seeded EN/AR, codes immutable, HSE Manager editable labels)

| List | Values (code — EN / AR) |
|---|---|
| **CR** crew roles | worker عامل · supervisor مشرف · hot_work_operative منفذ العمل الساخن · fire_watch مراقب الحريق · entrant الداخل · standby_person الشخص المناوب · rescue_lead قائد الإنقاذ · rescue_member عضو فريق الإنقاذ · gas_tester فاحص الغاز · crane_operator مشغل الرافعة · rigger عامل الربط · signaller موجه الإشارات · lift_supervisor مشرف الرفع · electrician كهربائي · competent_person الشخص الكفء · radiographer فني التصوير الإشعاعي · rpo مسؤول الحماية من الإشعاع · driver سائق · banksman منظم حركة المعدات · escort مرافق |
| **H** hazards | fall_from_height السقوط من ارتفاع · falling_objects سقوط الأجسام · fire_explosion الحريق والانفجار · toxic_atmosphere جو سام · oxygen_deficiency نقص الأكسجين · engulfment الانغمار · electric_shock الصدمة الكهربائية · arc_flash الوميض القوسي · struck_by_load الاصطدام بالحمولة · crane_overturn انقلاب الرافعة · excavation_collapse انهيار الحفرية · buried_services الخدمات المدفونة · ionising_radiation الإشعاع المؤين · heat_stress الإجهاد الحراري · hot_surfaces_burns الحروق · noise الضوضاء · manual_handling المناولة اليدوية · moving_plant المعدات المتحركة · aircraft_jet_blast نفث محركات الطائرات · fod الأجسام الغريبة · stored_energy الطاقة المخزنة · chemical_exposure التعرض الكيميائي · dropped_tools سقوط الأدوات · weather_wind الطقس والرياح · slips_trips الانزلاق والتعثر · other أخرى |
| **SR** suspension / cancellation reasons | shift_end نهاية الوردية (routine) · midday_ban حظر العمل وقت الظهيرة (routine) · heat_stress_stop إيقاف بسبب الإجهاد الحراري (routine, v1.3, 6b PH-3) · shift_lapsed انقضاء الوردية دون تسليم · gas_test_failed فشل فحص الغاز · gas_retest_overdue تأخر إعادة فحص الغاز · gas_alarm إنذار غاز · wap_suspended إيقاف تصريح دخول المنطقة · ops_suspension إيقاف تشغيلي · notam_not_in_effect NOTAM غير ساري · obs_not_active موافقة العائق غير سارية · simops_conflict تعارض عمليات متزامنة · key_role_ineligible عدم أهلية دور رئيسي · hook_not_met متطلب شهادة/تدريب غير مستوفى · wind_limit تجاوز حد الرياح · weather الطقس · audit_critical مخالفة حرجة في التدقيق · stop_work إيقاف العمل · emergency حالة طوارئ · emergency_drill إيقاف لتمرين طوارئ (routine, v1.4, 6c PE-2) · contractor_suspended المقاول موقوف · contractor_blacklisted المقاول محظور · isolation_breach خلل في العزل · rejected مرفوض · not_required غير مطلوب · duplicate مكرر · other أخرى |
| **EQ** equipment categories (equipment_tag) | tower_crane رافعة برجية · mobile_crane رافعة متحركة · crawler_crane رافعة مجنزرة · lifting_accessory ملحقات الرفع · spreader_beam عارضة توزيع · mewp منصة رفع أفراد · man_basket سلة رفع أفراد · mast_climber منصة صاعدة · bmu وحدة صيانة المباني · scaffold سقالة · welding_set ماكينة لحام · gas_cylinder_set طقم أسطوانات · ventilation_fan مروحة تهوية · tripod_winch حامل ورافعة إنقاذ · voltage_tester جهاز فحص الجهد · radiography_projector جهاز التصوير الإشعاعي · survey_meter جهاز قياس الإشعاع · other أخرى |
| **C** pre-issue checklist (per type; answer yes required unless n.a. allowed) | GW-01 area inspected by issuer and receiver · GW-02 barricades/signage in place · GW-03 PPE specified · HW-01 combustibles cleared ≥ 11 m or protected · HW-02 extinguishers ≤ 9 m and fire blanket · HW-03 fire watch briefed and equipped · HW-04 openings/drains below covered (n.a. allowed) · HW-05 cylinders upright, secured, flashback arrestors both ends (n.a. allowed) · HW-06 welding return lead at the work piece · HW-07 fire system status checked / impairment approved (HW-8) · CS-01 space isolated & blinded where required (n.a. allowed) · CS-02 ventilation running · CS-03 standby person at entry, entrant log ready · CS-04 rescue equipment rigged and tested · CS-05 communication tested · WH-01 access equipment inspected/tagged · WH-02 edge protection/nets in place or anchor certified · WH-03 drop zone barricaded · WH-04 rescue kit at level (n.a. if collective_only) · EX-01 utility clearance on site, services marked · EX-02 protective system installed · EX-03 spoil ≥ 0.6 m, edge barriers · EX-04 egress ladder within 7.5 m · EX-05 competent-person inspection done today · EL-01 isolation certificate verified · EL-02 test for dead (live-dead-live) done · EL-03 earths applied (HV, n.a. LV) · EL-04 personal locks applied by all crew · LF-01 lift plan briefed · LF-02 exclusion zone barricaded · LF-03 gear tags checked · LF-04 ground/outrigger mats checked (n.a. tower crane) · LF-05 wind within limit · LF-06 obstacle-clearance conditions applied (n.a. if none) · RG-01 barrier at planned distance, warning lights/signs · RG-02 area cleared and radio announced · RG-03 survey meter checked · AW-01 WAP Active and crew on WAP · AW-02 FOD controls in place · AW-03 vehicles beacons/AVP checked · AW-04 escort arrangements · AW-05 ATC/AOCC contact confirmed (n.a. if not movement area) |
| **X** closure checklist | X-01 work complete / stopped and made safe · X-02 tools, materials, waste removed · X-03 barricades removed or left with reason · X-04 personal locks removed (EL) · X-05 isolations retained or de-isolation requested · X-06 fire watch completed (HW) · X-07 all entrants out — log reconciled (CS) · X-08 covers/edge protection reinstated (CS/WH) · X-09 excavation backfilled or barricaded and lit (EX) · X-10 load landed, crane made safe/boom lowered per clearance conditions (LF) · X-11 source returned and verified (RG) · X-12 FOD check clear and area handed back to operations (AW) |
| **A** audit items (default severity) | A01 permit displayed and legible (minor) · A02 work matches permit scope and location (critical) · A03 permit valid now — status, window, shift (critical) · A04 crew on site = crew on permit, briefed (major) · A05 JSA at site, crew aware of key hazards (major) · A06 gas test valid and within interval (critical, n.a. when not required) · A07 isolations, locks and tags match the certificate; personal locks applied (critical) · A08 fire watch present and equipped (critical, HW) · A09 combustibles and extinguishers (major, HW) · A10 standby person at entry, rescue set ready (critical, CS) · A11 fall protection as permitted (critical, WH) · A12 excavation protection, spoil, egress (major, EX) · A13 lifting exclusion zone, gear tags, signaller (major, LF) · A14 barricades and signage (minor) · A15 PPE as specified (minor) · A16 housekeeping (minor) · A17 radiography barrier and survey (critical, RG) · A18 airside: WAP, escort, FOD, beacons (major, AW) · A19 heat controls: water, shade, rest (major, outdoor) · A20 equipment inspection tags (major) · A00 work requiring a permit done without one (critical; unpermitted_work only) |
| **B** blocker codes (PT-16) | RESCUE_TEAM_NOT_REGISTERED · RESCUE_DRILL_OVERDUE (v1.4, confined_space, 6c PE-3) · HEAT_STOP · WBGT_READING_REQUIRED (v1.3, Issue-time, 6b PH-2/PH-3) · JSA_MISSING · JSA_NOT_APPROVED · JSA_RESIDUAL_EXTREME · RESIDUAL_ACCEPTANCE_MISSING · HSE_REVIEW_MISSING · DOCUMENT_MISSING · CHECKLIST_INCOMPLETE · ROLE_MISSING · APPOINTMENT_INVALID · KEY_ROLE_INELIGIBLE · NO_ELIGIBLE_CREW · HOOK_NOT_MET · GAS_TEST_REQUIRED · GAS_TEST_FAILED · GAS_TEST_EXPIRED · ISOLATION_NOT_VERIFIED · PERSONAL_LOCKS_MISSING · SIMOPS_PROHIBITED · SIMOPS_COORDINATION_REQUIRED · WAP_NOT_ACTIVE · WAP_CREW_MISSING · OUTSIDE_WAP_WINDOW · NOTAM_NOT_IN_EFFECT · OBS_CLEARANCE_REQUIRED · WIND_LIMIT_EXCEEDED · MIDDAY_BAN · OUTSIDE_WINDOW · CONTRACTOR_SUSPENDED · LICENCE_INVALID · BARRIER_NOT_VERIFIED · FIRE_IMPAIRMENT_NOT_APPROVED · UTILITY_CLEARANCE_MISSING · FALL_CLEARANCE_INSUFFICIENT |

### 3.17 Phase 3 project settings (extend Phase 0 §3.9, Phase 1 §3.10, Phase 2 §3.22; HSE Manager only, audited; "Allowed" is the only range accepted)

| Key | AR label | Type | Default | Allowed |
|---|---|---|---|---|
| ptw_shift_max_hours | أقصى مدة للوردية | int | 12 | 4–12 |
| issue_to_start_max_minutes | مهلة البدء بعد الإصدار | int | 60 | 15–120 |
| max_active_permits_per_receiver | أقصى تصاريح سارية لكل مستلم | int | 3 ASSUMPTION | 1–10 |
| type_max_duration_days | أقصى مدة حسب النوع | map | §3.1 | general/WAH/excavation/electrical/airside/routine lifting 1–14; hot_work 1–7; CSE, critical lifting, radiography 1 only |
| gas_pre_start_validity_minutes | صلاحية فحص الغاز قبل البدء | int | 30 | 10–60 |
| gas_retest_interval_minutes | فترة إعادة فحص الغاز | map | confined_space 60 (with continuous monitor), hot_work 120, excavation 120, general 240 ASSUMPTION | 15–240 |
| gas_break_retest_minutes | إعادة الفحص بعد توقف | int | 30 | 15–60 |
| gas_limits | حدود الغازات | map | §6.2 table | tighten only |
| detector_calibration_interval_days | فترة معايرة الجهاز | int | 180 ASSUMPTION `VERIFY` manufacturer | 30–180 |
| fire_watch_post_minutes | مدة مراقبة الحريق بعد العمل | int | 60 (NFPA 51B 2019) | 60–240 |
| hw_combustible_clearance_m | مسافة إزالة المواد القابلة للاشتعال | decimal | 11.0 | 11.0–20.0 |
| hw_extinguisher_max_m | أقصى مسافة للطفاية | decimal | 9.0 `VERIFY` SBC 801 | 3.0–9.0 |
| airside_hotwork_separation_m | فاصل العمل الساخن عن الطائرات/الوقود | decimal | 15.0 ASSUMPTION `VERIFY` operator | 15.0–50.0 |
| wah_permit_threshold_m | حد ارتفاع تصريح العمل على ارتفاع | decimal | 1.8 ASSUMPTION `VERIFY` client | 1.2–1.8 |
| wah_rescue_max_minutes | أقصى زمن للإنقاذ | int | 15 ASSUMPTION | 5–15 |
| cse_rescue_max_minutes | زمن استجابة الإنقاذ (أماكن محصورة) | int | 4 ASSUMPTION | 2–10 |
| cse_heat_control_temp_c | حرارة تتطلب ضوابط إجهاد حراري | decimal | 35.0 ASSUMPTION | 30.0–40.0 |
| ex_permit_depth_m / ex_protective_system_depth_m | عمق تصريح الحفر / نظام الحماية | decimal | 1.2 / 1.2 | 0.6–1.2 |
| ex_pe_design_depth_m | عمق يتطلب تصميم مهندس | decimal | 6.0 | 3.0–6.0 |
| ex_spoil_setback_m / ex_egress_max_m | مسافة الأتربة / أقصى مسافة للخروج | decimal | 0.6 / 7.5 | 0.6–2.0 / 3.0–7.5 |
| ex_hand_dig_distance_m | مسافة الحفر اليدوي من الخدمات | decimal | 1.0 ASSUMPTION `VERIFY` utility owner | 0.5–3.0 |
| critical_lift_capacity_pct | نسبة الرفع الحرج | int | 75 ASSUMPTION `VERIFY` client lifting procedure | 50–90 |
| critical_lift_weight_t | وزن الرفع الحرج | decimal | 20.0 ASSUMPTION | 5.0–50.0 |
| lift_wind_limit_ms / man_basket_wind_limit_ms | حد الرياح للرفع / لسلة الأفراد | decimal | 9.8 / 7.0 ASSUMPTION `VERIFY` manufacturer | 5.0–20.0 / 5.0–9.8 |
| rg_barrier_limit_usv_h | معدل الجرعة عند الحاجز | decimal | 7.5 ASSUMPTION `VERIFY` NRRC | 0.5–7.5 |
| drop_zone_radius_m | نصف قطر منطقة سقوط الأجسام | decimal | 6.0 ASSUMPTION | 3.0–20.0 |
| vertical_separation_m | الفرق الرأسي لاعتبار "أعلى" | decimal | 2.0 | 1.0–5.0 |
| midday_ban_period / midday_ban_hours | فترة وساعات حظر الظهيرة | MM-DD range / time range | 06-15 → 09-15 / 12:00–15:00 `VERIFY` R12 annually | may only widen |
| midday_ban_prewarn_minutes | تنبيه مسبق للحظر | int | 15 | 5–60 |
| jsa_review_months | مراجعة قوالب JSA | int | 12 | 3–24 |
| long_term_isolation_days | العزل طويل الأمد | int | 7 | 1–30 |
| appointment_max_months | أقصى مدة للتعيين | int | 12 ASSUMPTION | 1–24 |
| ptw_audit_min_per_week | الحد الأدنى للتدقيقات أسبوعياً | int | 5 ASSUMPTION | 1–50 |
| ptw_audit_warning_pct / ptw_critical_findings_warning | حد إنذار التدقيق / المخالفات الحرجة | decimal / int | 85.0 / 3 ASSUMPTION | 50–100 / 1–20 |
| ptw_closure_warning_pct | حد إنذار إغلاق التصاريح | decimal | 95.0 ASSUMPTION | 50–100 |
| step_up_reauth_minutes | إعادة التحقق قبل التوقيع | int | 15 ASSUMPTION | 5–60 |
| ptw_retention_years | مدة الاحتفاظ بالتصاريح بعد إغلاق المشروع | int | 5 ASSUMPTION `VERIFY` client contract | 1–15 |
| hook_policy (Phase 2 key, reused) | سياسة المتطلبات اللاحقة | enum per kind | warn | warn · block (HK-4) |

## 4. Workflow / states

Who = capability numbers (§5.14). Every transition is audited with before/after (Phase 0 rule 35) and, for signing transitions (Request, Review, HSE review, Approve, Issue, Accept, Revalidate, Resume, Close, Cancel), requires step-up re-authentication within `step_up_reauth_minutes` (PT-15). "Job" = scheduler (PTW minute job every 60 s unless stated).

### 4.1 Permit

| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Draft | مسودة | 83 | Create (receiver, contractor rep or site engineer prepares) |
| Draft → Requested | مطلوب | 84 (named receiver only) | Required fields complete; JSA attached; documents per §3.1; crew ≥ 1 incl. supervisor; PT-6, PT-10, PT-11, HT-2 pass; SIMOPS check run (results stored, not blocking yet) |
| Requested → Draft | مسودة | 85, 87 | Returned with comment (≥ 10 chars) |
| Requested → Reviewed | تمت المراجعة | 85 (named area authority) | Area authority confirms location, area conditions, SIMOPS list; PR-6 |
| Reviewed → Draft | مسودة | 86, 87 | Returned with comment |
| Reviewed → Approved | معتمد | 87 (issuer with appointment) | high_risk ⇒ HSE review recorded (capability 86); JSA Approved with residual acceptance (JS-6/JS-7); no SIMOPS `prohibited` conflict; blockers other than issue-time ones (§5.1 PT-16 "issue-time") empty |
| Approved → Issued | صادر | 87 | Issuer at site (`site_visit_confirmed`), pre-issue checklist complete, gas test passed within validity (if required), isolations Verified, SIMOPS coordination recorded, Phase 2 links valid, crew eligibility evaluated, now inside a window, **blockers = []**; receiver accepts the issue in the same step (capability 84 signature) |
| Issued → Active | ساري | 84 (receiver) | "Start work": crew_present briefed (SH-4); now ≤ issued_at + `issue_to_start_max_minutes`; gas test still valid for start (GT-3); creates shift 1 |
| Issued → Approved | معتمد | Job | Not started within `issue_to_start_max_minutes` (issue lapses; must be issued again) |
| Active → Active (new shift) | ساري | 84 (incoming receiver) + 87 (issuer) | Handover accepted before planned_end_at of the current shift (SH-6) |
| Active → Suspended | موقوف | 84 (end shift — routine `shift_end`); 88 (stop work, any listed user); System (auto reasons, SH-2) | Reason from list SR; all crew notified via receiver |
| Suspended → Active | ساري | 87 (revalidate after `shift_end` / `shift_lapsed`, or resume after any other reason) + 84 (receiver acceptance) | Same checks as Issue (PT-16) incl. new gas test when required (GT-4), new shift record; still within valid_to_at and a window; the cause of a non-routine suspension recorded as cleared |
| Active/Suspended → Closed | مغلق | 84 (request closure) then 87 (issuer close, `site_visit_confirmed`) | Closure checklist (list X) complete; HW fire watch ended (HW-4); CS entry log reconciled; personal locks removed; airside FOD/hand-back (AW-8) |
| Draft/Requested/Reviewed/Approved/Issued → Cancelled | ملغى | 89 | Reason (SR: rejected, not_required, duplicate, contractor_*, other); Issued → Cancelled only with site_visit_confirmed (area left safe) |
| Approved/Issued/Active/Suspended → Expired | منتهي | Job | now > valid_to_at and not Closed — **except** while a fire watch is running (expiry waits until fire_watch_until; HW-5); triggers the post-expiry check (CL-6) |

Terminal: Closed, Cancelled, Expired. A Closed permit may not be reopened; a new permit is needed.

### 4.2 Shift and handover
| Object | From → To | Who | Trigger |
|---|---|---|---|
| Shift | — → Open | System | Issued → Active, Suspended → Active, or handover accepted |
| Shift | Open → Ended (`shift_end` / `suspended` / `closed` / `expired`) | System | Matching permit transition |
| Shift | Open → Ended (`lapsed`) | Job | now ≥ planned_end_at without end-shift, accepted handover or closure (SH-5) |
| Handover | — → Initiated | 84 (outgoing receiver) | ≤ 60 min before planned_end_at |
| Handover | Initiated → Accepted | 84 (incoming receiver) + 87 (incoming issuer) | Before planned_end_at; SH-6 checks |
| Handover | Initiated → Lapsed | Job | planned_end_at passed |

### 4.3 JSA
| From → To | AR | Who | Trigger |
|---|---|---|---|
| — → Draft | مسودة | 83 (instance), 96 (template) | Create / copy from template |
| Draft → Submitted | مُقدَّم | 83 / 96 | Every hazard line complete; JS-4 mandatory hazards present |
| Submitted → Approved | معتمد | Instance: 87 (issuer) after residual acceptance (JS-7); template: 96 (HSE Officer/Manager) | — |
| Submitted → Draft | مسودة | same | Returned with comment |
| Approved → Superseded | مُستبدل | System | New revision approved (templates) or permit revision |
| Approved (template) → Review Due | بانتظار المراجعة | Job | today > review_due_on; template cannot be copied until re-approved |

### 4.4 Isolation certificate
| From → To | AR | Who | Trigger |
|---|---|---|---|
| — → Planned | مخطط | 92 | Points listed |
| Planned → Isolated | معزول | 92 (isolation authority) | Every point applied with isolation lock + tag; keys in lockbox |
| Isolated → Verified | مُتحقق | 92 (verifier ≠ applier, IS-4) | Every point verified (try-out / test-for-dead / gauge) |
| Verified → De-isolation Requested | طلب إعادة التشغيل | 92 / 84 | IS-7 preconditions |
| De-isolation Requested → De-isolated | تمت إعادة التشغيل | 94 (issuer) + 92 (isolation authority removes) | All points removed; terminal |
| Planned → Cancelled | ملغى | 92 | Never applied; terminal |

### 4.5 Lock
available → applied (point or personal lock event) → available (removed by applier/holder) · applied → cut (IS-9, capability 95) · any → lost (reported; lock replaced) · available → retired.

### 4.6 Gas detector
| From → To | AR | Who | Trigger |
|---|---|---|---|
| — → In Service | في الخدمة | 91 | Calibration recorded and due ≥ today |
| In Service → Quarantined | معزول عن الاستخدام | System | Failed bump test, or calibration_due_on < today (job 00:05), or (v1.1) its calibration_body_id TPI blacklisted with the calibration in scope (`4-third-party-cert.md` BL-7; release needs a new calibration by another lab) |
| Quarantined → In Service | في الخدمة | 91 | New calibration recorded (bump-fail quarantine also needs a new passing bump test after calibration) |
| any → Retired | مُستبعد | 91 | Terminal |

### 4.7 PTW appointment
Active (ساري) → Suspended (موقوف, capability 100, reason) → Active · Active/Suspended → Revoked (ملغى, capability 100; terminal) · Active → Expired (منتهي, job when today > valid_to). Suspension or revocation re-evaluates every non-terminal permit on which the holder acts (PR-8).

### 4.8 SIMOPS conflict
Open → Coordinated (coordination record signed, conditional only) · Open/Coordinated → Resolved by change (re-check finds no match after a permit change) · any → Closed (either permit terminal).

### 4.9 PTW audit
Draft (مسودة) → Completed (منجز, auditor submits; score computed; critical findings act per AU-4) → Locked (مقفل) after 7 days (edits only by HSE Manager with reason).

## 5. Business rules

### 5.1 Permit core (PT)
- PT-1. **When a permit is required:** (a) any activity whose characteristics match a type in §3.1 (hot work; entry into a confined space; work where a person could fall ≥ `wah_permit_threshold_m` or any WH-1 activity; excavation ≥ `ex_permit_depth_m` or any mechanical excavation; work on or near electrical/energy systems needing isolation; any crane, hoist or multi-sling lift; radiography); (b) any work in a zone with `permit_required_all_work`. The platform cannot detect unpermitted work; audits record it as `unpermitted_work` (AU-6).
- PT-2. Permit numbers are sequential per project and year and immutable; a cancelled number is never reused.
- PT-3. **Zone PTW profile defaults** on zone creation (and for existing zones at Phase 3 go-live): permit_required_all_work = (zone airside AND in_movement_area); gas_test_zone = false; hazardous_area_class = none; default_exposure = outdoor_direct_sun for airside zones, else indoor; fire_protection_present = false. Edits by capability 98; setting permit_required_all_work = false on a movement-area zone is rejected `PROFILE_LOOSENING`.
- PT-4. All zones of a permit belong to one site; ≤ 3 zones; airside and landside zones cannot be mixed on one permit (`MIXED_SIDE_ZONES`); zones of different sites → `ZONES_NOT_SAME_SITE`.
- PT-5. The receiver must hold an Active permit_receiver assignment on the permit's engagement (Phase 0 rule 10 C1); a receiver may hold at most `max_active_permits_per_receiver` permits in Issued/Active (`RECEIVER_LIMIT`).
- PT-6. **Contractor status** (Phase 0 rule 28): a permit for a Suspended or Blacklisted contractor cannot be created, requested, approved, issued, revalidated or resumed (`CONTRACTOR_SUSPENDED` / `CONTRACTOR_BLACKLISTED`). On contractor suspension its Issued/Active permits are Suspended (`contractor_suspended`) within 60 s; on blacklisting they are Suspended (`contractor_blacklisted`) and may then only be Closed (work incomplete, area made safe) or Cancelled.
- PT-7. Crew members come from the permit's engagement or its ancestor engagements (as Phase 2 WA-2); a worker on another contractor's tree is rejected `CREW_NOT_IN_TREE`.
- PT-8. Crew eligibility = Phase 2 E(worker, zone, at, context = `ptw`) (ZP-4 steps 1–6 and 8, no WAP step; §11 clarification) for every zone, plus HK3 hooks of the crew role, evaluated at Request (informative), Approve, Issue, every Start/Revalidate/Resume, and when a Phase 2 credential event arrives. An ineligible non-key crew member is set `excluded` with the reason and notified to the receiver; an ineligible key-role member makes blocker `KEY_ROLE_INELIGIBLE` (an Active permit is Suspended `key_role_ineligible`). "Expiring" results (≤ 7 days) add warning `EXPIRING_7D`; an eligibility valid_until earlier than the shift's planned_end_at excludes the person from that shift (`EXPIRES_DURING_SHIFT`).
- PT-9. high_risk is derived from §3.1 (HSE-review column) and recomputed on every change; a permit that becomes high_risk after Review returns to Reviewed and needs the HSE review before Approve.
- PT-10. valid_from_at ≥ now − 15 min at Request (no back-dated permits); valid_to_at > valid_from_at.
- PT-11. Duration (valid_to_at − valid_from_at) ≤ the smallest type_max_duration_days among the permit's types (lifting uses the critical value when critical = true) — 1 day = 24 h; for airside works also ≤ the linked WAP's validity end; otherwise 422 `DURATION_EXCEEDS_LIMIT` naming the limiting type.
- PT-12. Windows: 1–3, rules as Phase 2 WA-9 and §6.5; a shift can start only inside a window; a shift's planned_end_at never exceeds the window end.
- PT-13. Changing zones, location, types, windows, valid_to, equipment or crew roles of key roles after Approve returns the permit to Requested (re-review). Adding non-key crew or extra controls on an Approved/Issued/Active permit takes effect after eligibility evaluation, without re-approval.
- PT-14. Issue, Revalidate, Resume and Close require `site_visit_confirmed = true` by the issuer, with the issuer's device location optional (not stored when declined) ASSUMPTION; Issued → Cancelled requires it too.
- PT-15. Signing transitions require the signer to have authenticated (password, or MFA when enabled) within the last `step_up_reauth_minutes`; otherwise 401 `REAUTH_REQUIRED`. Signatures are stored as {user, role/appointment, transition, timestamp, permit hash}.
- PT-16. **Blockers** (list B) are recomputed on every change, every minute for Issued/Active/Suspended permits, and on every Phase 2 event (§11). Approve-time blockers: JSA_*, RESIDUAL_ACCEPTANCE_MISSING, HSE_REVIEW_MISSING, DOCUMENT_MISSING, ROLE_MISSING, APPOINTMENT_INVALID, SIMOPS_PROHIBITED, CONTRACTOR_SUSPENDED, LICENCE_INVALID, UTILITY_CLEARANCE_MISSING, FALL_CLEARANCE_INSUFFICIENT, FIRE_IMPAIRMENT_NOT_APPROVED, MIDDAY_BAN (windows). Issue-time blockers (also checked at Start/Revalidate/Resume): all of the above plus CHECKLIST_INCOMPLETE, GAS_TEST_*, ISOLATION_NOT_VERIFIED, PERSONAL_LOCKS_MISSING, SIMOPS_COORDINATION_REQUIRED, WAP_*, OUTSIDE_WAP_WINDOW, NOTAM_NOT_IN_EFFECT, OBS_CLEARANCE_REQUIRED, WIND_LIMIT_EXCEEDED, KEY_ROLE_INELIGIBLE, NO_ELIGIBLE_CREW, HOOK_NOT_MET, OUTSIDE_WINDOW, BARRIER_NOT_VERIFIED. A blocker appearing on an Active permit suspends it with the matching SR reason within 60 s (SH-2).
- PT-17. The platform has **no override** of blockers. The only exemptions are those named in this spec (HT-4 midday ban, EL-3 energized work, HW-8 impairment), each granted by the HSE Manager (capability 102) per permit with reason and audited.
- PT-18. Permits are never hard-deleted; Drafts may be deleted by their creator within 7 days if never Requested.
- PT-19. **Viewer/Client and roles without capability 46** see permits with crew count and roles only, no names or worker_no (as Phase 2 WA-19, DECISIONS #48).
- PT-20. The permit print (A4, EN/AR, QR kind `PT`) shows permit no, types, location, validity, windows, current shift and status, receiver/issuer/area authority names, crew names with worker_no and roles (never ID numbers, nationality or fitness detail), latest gas test, isolations with lock and tag numbers, key conditions and emergency information.
- PT-21. Computed minimum distances (barrier, clearance radius) round **up** to 0.1 m; computed maxima round **down**; percentages round half-up to 1 dp (Phase 1 K-R8).

### 5.2 Roles, appointments and segregation of duties (PR)
- PR-1. Function holders on a permit: receiver (permit_receiver user), area authority, issuer, HSE reviewer (high-risk), isolation authority (per isolation certificate), gas tester, authorised persons (per type), fire watch / standby / entrant / crane operator / rigger / signaller / radiographer (crew roles). One person may hold several functions except where PR-5 forbids it.
- PR-2. Issuer: a user with an Active permit_issuer role assignment on the project (site in scope) **and** an Active `issuer` appointment covering every work type on the permit and the site (`APPOINTMENT_INVALID`). Issuer appointments are created by the HSE Manager only (capability 100).
- PR-3. Area authority: an Active `area_authority` appointment covering every zone of the permit, held by a user whose platform role on the project is hse_officer, site_engineer or permit_issuer.
- PR-4. Gas tester, competent persons, lift supervisor, appointed person, RPO, isolation authority: Active appointment with the matching function/discipline, permit type and zone, valid on every permit date; appointment valid_to < permit valid_to_at adds warning `APPOINTMENT_EXPIRES` and blocks any shift starting after valid_to.
- PR-5. **Segregation of duties** (`SOD_CONFLICT`, 422 as DECISIONS #43): (a) issuer ≠ receiver (also Phase 0 rule 16 at assignment level); (b) issuer not employed by the permit's contractor or any ancestor engagement's contractor (as Phase 2 WA-4) ASSUMPTION — tied to Phase 0 §10 Q2; (c) area authority ≠ receiver and ≠ issuer ASSUMPTION; (d) HSE reviewer ≠ receiver and ≠ issuer; (e) isolation verifier ≠ isolation applier (IS-4); (f) fire watch has no other crew role on the permit and is not the hot_work_operative; (g) standby person is not an entrant on the same permit and attends one confined space only; (h) auditor ≠ issuer, receiver, area authority and HSE reviewer of the audited permit (AU-2); (i) a JSA's High residual acceptance is not by its author.
- PR-6. The area authority's review records: area conditions known (yes), other activities in the area reviewed against the SIMOPS result, special area hazards (text), and for airside zones the WAP number.
- PR-7. Every appointment has valid_to ≤ valid_from + `appointment_max_months`; expiry alerts per §7.
- PR-8. Suspending/revoking/expiring an appointment re-evaluates permits: a permit whose issuer appointment is no longer Active cannot be revalidated/resumed/closed by that issuer (another appointed issuer may take over by signing); key-role appointments → KEY_ROLE_INELIGIBLE.
- PR-9. Hook requirements on appointments (HK3-2) are evaluated at appointment creation and at each use; under `warn` they add HOOK_NOT_AVAILABLE only.
- PR-10. **One key role at a time** (`KEY_ROLE_BUSY`): a worker may hold a key crew role (fire watch, standby person, entrant, gas tester on continuous monitoring, crane operator, signaller, radiographer, lift supervisor) on only one permit in Issued/Active at a time; a supervisor may supervise up to 3 Issued/Active permits of the same engagement in the same site ASSUMPTION. A worker may be ordinary crew on several permits only if their shifts do not overlap.

### 5.3 JSA and risk assessment (JS)
- JS-1. Every permit needs a JSA instance before Request (`JSA_MISSING`); one JSA per permit; templates are copied, never attached directly.
- JS-2. Risk score = L × S (§6.1). Bands: **Low 1–4** (منخفض), **Medium 5–9** (متوسط), **High 10–14** (مرتفع), **Extreme 15–25** (حرج) ASSUMPTION (§10 Q4).
- JS-3. The JSA's work_types must include every type on the permit (`JSA_TYPE_MISMATCH`).
- JS-4. **Mandatory hazards** must appear in at least one line: hot_work → fire_explosion, hot_surfaces_burns; confined_space → toxic_atmosphere, oxygen_deficiency (+ engulfment when space_hazards ∋ engulfment); work_at_height → fall_from_height, falling_objects; excavation → excavation_collapse, buried_services; electrical_isolation → electric_shock (+ arc_flash for energized or ≥ 400 V); lifting → struck_by_load, crane_overturn; radiography → ionising_radiation; airside_works → fod, moving_plant (+ aircraft_jet_blast when aircraft_proximity = live_stand_adjacent); any permit with exposure outdoor_direct_sun dated in `heat_season` (Phase 1 setting) → heat_stress. Missing → `JSA_MANDATORY_HAZARD_MISSING`.
- JS-5. residual_l ≤ initial_l and residual_s ≤ initial_s for every line. A line with residual_s < initial_s and no control at level elimination, substitution or engineering raises warning `SEVERITY_REDUCED_WITHOUT_HIGHER_CONTROL` (not a block).
- JS-6. A permit cannot be Approved while any line's residual band is Extreme (`JSA_RESIDUAL_EXTREME`) — the task must be redesigned.
- JS-7. **Residual acceptance by governing band:** Low → receiver; Medium → issuer; High → issuer **and** HSE Officer or HSE Manager (capability 86) with an ALARP justification ≥ 30 chars and at least one control at engineering level or higher on each High line (`HIGHER_CONTROL_REQUIRED`). Missing acceptance → `RESIDUAL_ACCEPTANCE_MISSING`.
- JS-8. PPE-only control sets: a line whose controls are all `ppe` cannot have a residual band below its initial band (`PPE_ONLY_CONTROLS`).
- JS-9. Templates: approved by capability 96; review_due_on = approval + `jsa_review_months`; a template in Review Due cannot be copied (`TEMPLATE_REVIEW_DUE`).
- JS-10. Crew briefing on the JSA is recorded per shift (SH-4); the JSA instance is frozen at Approve; later control changes create a JSA revision and return the permit to Reviewed (PT-13).

### 5.4 Gas testing (GT)
- GT-1. A gas test is required for: every confined_space permit; hot_work when any zone is gas_test_zone, hazardous_area_class ≠ none, or the permit also has confined_space; excavation with depth ≥ 1.2 m and (zone gas_test_zone or atmosphere_hazard); general with flammables_in_use in a gas_test_zone; airside hot work within `airside_hotwork_separation_m` of a hydrant pit (AW-6).
- GT-2. Tests are performed by a person with an Active gas_tester appointment for the zone and type; the recorder may be another user (receiver, issuer) entering the tester's results with the tester's signature.
- GT-3. **Start validity:** Issue, Start, Revalidate and Resume need a passing test with tested_at ≥ now − `gas_pre_start_validity_minutes` (`GAS_TEST_EXPIRED`); confined-space entry additionally needs a `pre_entry` (or pre_issue) test at ≥ 3 points.
- GT-4. **Periodic and post-break** (§6.3): while Active and not paused, the next test is due at last passing test + `gas_retest_interval_minutes[type]` (strictest of the permit's types); if no passing test by next_due_at, the permit is Suspended `gas_retest_overdue`. No test falls due during a pause or suspension; after any stop of work ≥ `gas_break_retest_minutes` (pause, suspension, shift change) a `post_break` test valid for start is needed before work restarts (`GAS_TEST_EXPIRED`).
- GT-5. A test is accepted only when the detector is In Service, calibration_due_on ≥ test date (`DETECTOR_CALIBRATION_OVERDUE`), has a passing bump test on the same local date before tested_at (`BUMP_TEST_MISSING`), and has every sensor required by the applicable limits (O₂ and LEL always for CSE/hot work; H₂S and CO for CSE and excavation) (`DETECTOR_SENSOR_MISSING`). A tested_at more than 60 min before saving is rejected (`BACKDATED_TEST`).
- GT-6. **Limits** (§6.2): pass iff every reading at every point is within the strictest limits of the permit's types; the worst reading governs. A failed test on an Active permit suspends it immediately (`gas_test_failed`), notifies receiver, issuer, HSE Officer (and HSE Manager for CSE), and requires a passing `post_alarm` test after the cause is controlled before Resume.
- GT-7. A continuous monitor alarm reported by the receiver or crew (button "gas alarm") suspends the permit (`gas_alarm`) the same way.
- GT-8. Gas tests are immutable after save; corrections are new tests (the wrong one stays, flagged `superseded` with reason).
- GT-9. CSE internal temperature is recorded at every test; ≥ `cse_heat_control_temp_c` requires HT-6 controls.

### 5.5 Isolations and LOTO (IS)
- IS-1. Any permit whose work requires control of hazardous energy links ≥ 1 isolation certificate; electrical_isolation always does (except energized work under EL-3, which still links the upstream isolation where one is possible).
- IS-2. Each isolation point has one isolation lock and one danger/hold tag; lock numbers are unique per project; one lock per point at a time.
- IS-3. Isolation keys go into the certificate's lockbox; the certificate is Isolated only when every point has applied_at, lock and tag.
- IS-4. Verification by a person other than the applier (user or worker) using the method suitable to the energy (`test_for_dead` for electrical with a proved instrument; `try_out_start_attempt` for machinery; `pressure_gauge_zero` / `visual_air_gap` for fluids) (`VERIFIER_IS_APPLIER`).
- IS-5. **Group lockout:** before a shift starts on a permit linked to a certificate, every crew_present member who will work on the isolated equipment has a personal lock applied on the lockbox (`PERSONAL_LOCKS_MISSING`). A worker removes only their own lock (holder) at shift end.
- IS-6. A certificate may serve several permits; it lists them; a permit cannot be Issued unless every linked certificate is Verified.
- IS-7. **De-isolation** may be requested only when every linked permit is Closed, Cancelled, or Expired with its post-expiry check done, and no personal lock remains on the lockbox (`DEISOLATION_BLOCKED` naming the permits/locks). The issuer authorises (capability 94); the isolation authority removes points.
- IS-8. Isolations Verified longer than `long_term_isolation_days` are long-term: weekly review record by the isolation authority (lock/tag still in place, yes/no); a "no" opens isolation_breach on linked permits (Suspended).
- IS-9. **Lock cut** (removal of a personal lock by someone other than its holder; OSHA 1910.147(e)(3)): requires the supervisor's confirmation that the holder is not on site, documented contact attempts, HSE Manager approval (capability 95) and the holder informed before they return to work; audited and alerted to HSE Manager and HSE Officers.
- IS-10. HV isolations need an `electrical_hv` isolation authority, earths applied as points of method `earth_applied`, and a switching programme document.
- IS-11. Lost isolation/personal lock: status lost, the point is re-locked with a new lock before work continues; the permit is Suspended `isolation_breach` until done.

### 5.6 SIMOPS conflict check (SM)
- SM-1. The check compares the permit with every other permit of the project in Requested…Suspended whose windows overlap in time (§6.5 overlap over the intersection of their validity) and applies every matching rule of the matrix.
- SM-2. **Distance:** both permits with grid points → horizontal distance between the points (§6.4); for lifting the relevant points are the landing point (exclusion) and the appliance point (slew radius). Otherwise same zone → distance 0; zones in the adjacency table → distance_m; other zones → no match. Vertical relation from elevation_m (A above B iff elevation_A ≥ elevation_B + `vertical_separation_m`), else from adjacency vertical_relation, else same-zone-unknown = treated as "possible above" for SM-R06/R07 (strictest).
- SM-3. **Default matrix** (HSE Manager may add rules or tighten thresholds/results; may not delete R01–R12):

| Rule | Permit A | Permit B | Condition | Default result | Required controls (conditional) |
|---|---|---|---|---|---|
| SM-R01 | radiography | any | distance ≤ A.planned_barrier_m | prohibited | — |
| SM-R02 | hot_work | confined_space | distance ≤ 15.0 m, or A located inside B's space | conditional (prohibited when inside the space unless both types on one permit) | ventilation intakes away from hot work; continuous LEL monitoring at both |
| SM-R03 | hot_work | any permit with flammables_in_use (painting, coating, fuel transfer, solvent cleaning) | distance ≤ `hw_combustible_clearance_m` | prohibited | — |
| SM-R04 | hot_work | gas-test-required permit (GT-1) other than R02 | distance ≤ 15.0 m | conditional | LEL test at hot-work point |
| SM-R05a | lifting (crane) | any | B within A.exclusion_radius_m of the landing point | prohibited | — |
| SM-R05b | lifting (crane) | any | B within A.slew_radius_m of the appliance point | conditional | no load over B; banksman; B informed of lift times |
| SM-R06 | work_at_height (A above B) | any | horizontal distance ≤ `drop_zone_radius_m` | conditional | drop-zone barricade or overhead protection for B; tool tethering for A |
| SM-R07 | hot_work at height (work_height_above_floor_m > 0, A above B) | any | horizontal distance ≤ `hw_combustible_clearance_m` | conditional | spark containment; fire watch covers B's level |
| SM-R08 | excavation | lifting or excavating plant | distance ≤ A.max_depth_m (surcharge zone) | conditional | engineering check of surcharge on the protective system |
| SM-R09 | confined_space | excavation / any permit using combustion-engine plant | distance ≤ 10.0 m | conditional | exhaust away from openings; CO monitoring |
| SM-R10 | electrical_isolation (energized) | any | same zone | conditional | approach boundaries barricaded |
| SM-R11 | lifting (crane) | lifting (crane) | distance between appliance points ≤ A.slew_radius_m + B.slew_radius_m | conditional | anti-collision zoning / operator radio protocol |
| SM-R12 | any (contractor X) | any (contractor Y ≠ X), both airside in the same movement-area zone | same zone | conditional | single works coordinator named in agreed controls |

- SM-4. The check runs at Request (stored, informative), Review, Approve, Issue, every Start/Revalidate/Resume, and on any change to location, windows or validity of either permit. Results are stored as conflicts (§3.12) visible on both permits.
- SM-5. **prohibited** → Approve and Issue are blocked (`SIMOPS_PROHIBITED`) while the other permit's overlapping window is still ahead or running; it is resolved only by changing location, windows or validity (status `resolved_by_change`) or the other permit ending.
- SM-6. **conditional** → Issue blocked (`SIMOPS_COORDINATION_REQUIRED`) until a coordination record is signed by the issuers of both permits (one signature when the same user) and the area authority of the zone of permit A; the record expires with the earlier permit.
- SM-7. A new conflict found on an Active permit (e.g. another permit issued later wrongly, or a location change) suspends the later-issued permit (`simops_conflict`) for prohibited, and adds SIMOPS_COORDINATION_REQUIRED to the later one for conditional.
- SM-8. A permit with both types (e.g. hot_work + confined_space on one permit) is not checked against itself; its combined limits apply (§6.2).

### 5.7 Type-specific rules
**Hot work (HW)**
- HW-1. A fire watch (crew_role fire_watch, eligible, hook `training_course: FIRE-WATCH`) is present for the whole hot-work period and the post-work period; one fire watch covers one hot-work location within line of sight ASSUMPTION; Start is blocked without one (`ROLE_MISSING`).
- HW-2. combustibles_cleared_radius_m ≥ `hw_combustible_clearance_m`, or combustibles_protected_method given (fire-resistant blankets/screens); ≥ 1 extinguisher at ≤ `hw_extinguisher_max_m`; fire blanket present.
- HW-3. Hot work requires 0 % LEL at the work point when a gas test is required (§6.2).
- HW-4. The receiver records hot_work_ended_at; fire_watch_until = hot_work_ended_at + `fire_watch_post_minutes`. Closure before fire_watch_until is rejected `FIRE_WATCH_RUNNING`.
- HW-5. Hot work must end no later than valid_to_at − `fire_watch_post_minutes`; a later hot_work_ended_at is accepted but flagged `HOT_WORK_LATE` (counts as an audit-type finding in K-64 ASSUMPTION) and expiry waits for fire_watch_until.
- HW-6. Work above floor level (> 0 m) or with floor openings/drains within the clearance radius needs openings_below_protected = yes and a check of the level(s) below by the fire watch.
- HW-7. Oxy-fuel: cylinders upright and secured, flashback arrestors at regulator and torch (both ends), oxygen and fuel stored ≥ 6.1 m apart or separated by a 1.5 m-high, 30-min fire-rated barrier (OSHA 1926.350(a)(10)).
- HW-8. **Fire-protection impairment** (fire_system_impairment = true, i.e. detection/sprinklers isolated in the zone): requires HSE Manager approval (capability 102) and an impairment ref; when impairment_hours_24h > 4, civil_defense_notified_at must be recorded before Issue (`FIRE_IMPAIRMENT_NOT_APPROVED`) — SBC 801/IFC 901.7 basis `VERIFY`; fire watch covers the impaired area for the whole impairment.
- HW-9. Hot work in hazardous_area_class zone_0 or zone_1 is prohibited (`HAZARDOUS_AREA_PROHIBITED`); zone_2 requires gas test (0 % LEL), continuous LEL monitoring and HSE review.

**Confined space entry (CS)**
- CS-1. Every CSE permit has ≥ 1 entrant, exactly one standby person per space opening in use (never entering; PR-5g), an authorised gas tester, a rescue plan document, rescue equipment checked, and a rescue lead or external service with documented response ≤ `cse_rescue_max_minutes`.
- CS-2. Atmospheric acceptance per §6.2 (CSE limits) at top, middle and bottom before entry (fewer than 3 points → `CSE_POINTS_REQUIRED`); continuous monitoring by a detector worn in the space; recorded tests at ≤ 60 min (GT-4).
- CS-3. Entrants, standby and rescue members need hooks `training_course: CSE-ENTRANT` / `CSE-ATTENDANT` / `CSE-RESCUE` and `medical_fitness: CSE-ENTRY-FIT` (warn until Phases 5/6).
- CS-4. Ventilation `none_justified` requires a justification ≥ 30 chars and HSE reviewer acceptance.
- CS-5. Spaces with mechanical/electrical/process hazards link a Verified isolation certificate (blinds/spades for process lines; double block & bleed only with HSE review).
- CS-6. CSE plus hot work on one permit: hot-work limits (0 % LEL) apply inside the space; fire watch outside the space in addition to the standby person.
- CS-7. Entry log: each entry/exit time per entrant; at shift end, suspension, handover and closure the log must show 0 persons inside (`ENTRANTS_INSIDE`); handover notes must state persons inside when handing over during entry.

**Working at height (WH)**
- WH-1. A WAH permit is required at max_fall_height_m ≥ `wah_permit_threshold_m`, and at any height for: work at unprotected slab edges/openings, roofs, facade/BMU/mast-climber/suspended platforms, rope access, work over water or machinery ASSUMPTION.
- WH-2. Hierarchy: fall_protection = `collective_only` preferred; arrest methods need a rescue plan and rescue kit at the level, rescue ≤ `wah_rescue_max_minutes`, and HSE review (§3.1).
- WH-3. Rope access requires two independent ropes and IRATA/SPRAT-type certification hook `personnel_certificate: ROPE-ACCESS` (warn).
- WH-4. Anchors ≥ 22.2 kN per person attached, or an engineered system with certificate ref.
- WH-5. **Fall clearance** (§6.9): arrest_lanyard requires lanyard_length_m ≤ 1.80, anchor at or above D-ring height, and required clearance ≤ available_clearance_m; arrest_srl requires srl_required_clearance_m ≤ available_clearance_m; else `FALL_CLEARANCE_INSUFFICIENT`.
- WH-6. Scaffold access needs a scaffold tag ref; hook `equipment_certificate: SCAFFOLD-TAG` (Phase 4, warn). MEWPs: hook `equipment_certificate: MEWP-TPI` and operator `personnel_certificate: MEWP-OPERATOR` (warn).
- WH-7. Outdoor WAH: wind reading at Start/Revalidate; > 10.0 m/s ASSUMPTION suspends work on edges, facades and MEWPs (`weather`).

**Excavation (EX)**
- EX-1. An excavation section is required for any mechanical excavation and for any excavation ≥ `ex_permit_depth_m`.
- EX-2. Depth ≥ `ex_protective_system_depth_m` requires protective_system ≠ none_lt_1_2m; sloping requires slope_ratio_h_v ≥ the soil-type minimum; depth ≥ `ex_pe_design_depth_m` requires `engineered_design` with pe_design_ref and a `pe_design` document.
- EX-3. utility_clearance_ref is mandatory before Approve (`UTILITY_CLEARANCE_MISSING`); airside excavations need the airport operator's clearance (AGL/ILS/communications cables).
- EX-4. Within `ex_hand_dig_distance_m` of a located service, method must be hand_dig or vacuum (`MECHANICAL_NEAR_SERVICE`).
- EX-5. Spoil ≥ `ex_spoil_setback_m` from the edge; egress within `ex_egress_max_m` lateral travel at depth ≥ 1.2 m; edge barriers; lighting at night.
- EX-6. A competent-person inspection (appointment `excavation_competent_person`) is recorded before each shift's Start/Revalidate and after rain, sandstorm or any event that could affect stability (`INSPECTION_REQUIRED`); result `unsafe` suspends the permit.
- EX-7. Plant or lifting within the surcharge zone triggers SM-R08.

**Electrical (EL)**
- EL-1. Electrically safe work condition is the default: Verified isolation, test for dead (live-dead-live with proving unit) and, for HV, earths applied; both recorded before Issue.
- EL-2. Authorised person (electrical, LV or HV per voltage_class) is named; HV needs `electrical_hv` appointments for isolation and authorised person.
- EL-3. **Energized work** is prohibited for HV (`ENERGIZED_HV_PROHIBITED`); for LV it needs energized_justification, approach boundaries, incident energy or PPE category, arc-rated PPE ≥ incident energy, HSE Manager approval (capability 102, else `EXEMPTION_REQUIRED`) and HSE review; "convenience" or schedule is not a justification (the enum has no such value).
- EL-4. Hooks: `training_course: LOTO`, `training_course: ELEC-QUALIFIED` for electricians (warn).

**Lifting (LF)**
- LF-1. Every lifting permit has a lift plan document; critical lifts have a critical lift plan approved by a `lifting_appointed_person` and the lift supervisor named on the permit.
- LF-2. **Critical** if any of: capacity_pct ≥ `critical_lift_capacity_pct`; tandem/multi-crane; personnel_lift; gross load ≥ `critical_lift_weight_t`; any zone in_movement_area or the lift within 15.0 m of an operational airside area ASSUMPTION; overhead_lines_within_6m; load passes over occupied buildings, public roads or live plant (flag). critical_reasons lists every met criterion.
- LF-3. capacity_pct > 100.0 is rejected (`CAPACITY_EXCEEDED`); > 90.0 needs HSE Manager approval ASSUMPTION (`EXEMPTION_REQUIRED` until approved).
- LF-4. Crew: crane_operator (hook `personnel_certificate: CRANE-OPERATOR`), rigger (`RIGGER`), signaller (`SIGNALLER`), lift supervisor; appliance hook `equipment_certificate: CRANE-TPI` (vehicle or equipment_tag); accessories `LIFTING-ACCESSORY-TPI`; man-baskets `MAN-BASKET-TPI`. **Under hook policy `block` (from Phase 4 go-live) an expired or missing operator certificate or crane certificate is `HOOK_NOT_MET` and blocks Issue/Revalidate — "a permit cannot use an expired operator or uncertified crane"; under `warn` it adds HOOK_NOT_AVAILABLE.** v1.1: in the Phase 4 transition stage a not_met without hard_stop gives warning `HOOK_NOT_MET_WARN`; a hard stop (item Out of Service, Blacklisted, Retired, configuration_changed, revoked or failed-verification certificate, holder ban, HSE-suspended certificate, TPI blacklisted) blocks in every stage (`4-third-party-cert.md` HK4-3, HK4-4). Provider `conditions[]` (equipment limitations, card limitations) and `swl_t` are copied into permit conditions and cap the lift as LF-9 does.
- LF-5. A certificate (hook) valid_until earlier than the planned shift end excludes that person/appliance from the shift (as PT-8).
- LF-6. Wind reading at Issue and each Start/Revalidate/Resume and on demand; speed > wind_limit_ms → `WIND_LIMIT_EXCEEDED` (Active → Suspended `wind_limit`).
- LF-7. Personnel lifting (man-basket) only when no safer access is practicable (justification), wind ≤ `man_basket_wind_limit_ms`, crane capacity_pct ≤ 50.0 ASSUMPTION (ASME B30.23 basis), and always critical.
- LF-8. Exclusion zone around the landing point barricaded (LF-02); nobody under a suspended load (SM-R05a).
- LF-9. **Height clearance:** if the appliance's max working height > the zone's max_equipment_height_m_agl (airside), or ≥ `obstacle_height_threshold_m` (Phase 2 setting, non-airport projects), an Approved/Approved-with-conditions Phase 2 obstacle clearance covering the equipment, zone and every permit day is linked (`OBS_CLEARANCE_REQUIRED`); its conditions (lower_when_idle, lower_at_night, daylight_only, obstruction_light) are copied into permit conditions and LF-06 is required.

**Radiography (RG)**
- RG-1. Radiography permits need an NRRC licence ref valid on every permit date, a radiation protection plan, an RPO appointment (`radiation_protection_officer`) and ≥ 1 radiographer with hook `personnel_certificate: RADIOGRAPHER` (warn) (`LICENCE_INVALID`).
- RG-2. computed_barrier_m per §6.7 (unshielded inverse square, collimator transmission applied).
- RG-3. planned_barrier_m ≥ computed_barrier_m (`BARRIER_TOO_SMALL`); before the first exposure a barrier survey with max ≤ `rg_barrier_limit_usv_h` is recorded (`BARRIER_NOT_VERIFIED`).
- RG-4. SM-R01: no other permit inside the barrier during overlapping windows; radiography windows default to night hours ASSUMPTION (not enforced).
- RG-5. Closure requires source_returned_verified with a survey ≤ 2 × background ASSUMPTION and barrier removal.
- RG-6. No individual dose values are stored (P3-4).

**Airside works (AW)**
- AW-1. A permit with any airside zone automatically includes `airside_works` (cannot be removed) and is also subject to Phase 2 rules through the WAP.
- AW-2. **WAP link:** an Active Phase 2 WAP of the permit's engagement or an ancestor engagement covering every airside zone of the permit is required at Issue and at every shift start (`WAP_NOT_ACTIVE`), retrieved through `active_waps(zone_id, engagement_id, at)` (HK-6).
- AW-3. Every crew member is on that WAP's crew and not excluded (`WAP_CREW_MISSING`); escorted persons keep their WAP escort (Phase 2 WA-11, DECISIONS #44).
- AW-4. Permit windows lie within the WAP windows on every date (`OUTSIDE_WAP_WINDOW`); NOTAM coverage is inherited: a WAP blocker NOTAM_NOT_ISSUED / NOTAM_NOT_COVERING_WINDOW appears on the permit as `NOTAM_NOT_IN_EFFECT`.
- AW-5. Every equipment line that is a vehicle is on the WAP vehicles list; height rules via LF-9 and Phase 2 VP-7/OB-6.
- AW-6. Hot work on an apron zone with hydrant pits: aircraft_proximity ∈ {stand_closed_notam, stand_closed_operator, no_stand_in_zone}; ≥ `airside_hotwork_separation_m` from any hydrant pit or fuelling vehicle; hydrant_operator_clearance_ref recorded; gas test 0 % LEL at the nearest pit (GT-1). Any failed condition → `AIRCRAFT_PROXIMITY` (aircraft/fuelling) or the matching gas code.
- AW-7. **Suspension cascade:** a WAP that becomes Suspended (ops event, dependency, contractor) suspends every linked Issued/Active permit (`wap_suspended` or `ops_suspension`) within 60 s. WAP resume does not resume the permit; the issuer resumes it (with gas retest if required).
- AW-8. Closure of a permit in a movement-area zone requires a FOD check `clear` (Phase 2 WA-17 record or a permit-level one) and ops_handback_ref (`FOD_HANDBACK_REQUIRED`).

### 5.8 Heat and midday ban (HT)
- HT-1. The midday ban applies to permits with exposure `outdoor_direct_sun` on dates inside `midday_ban_period` (defaults 15 Jun–15 Sep, 12:00–15:00 local) `VERIFY` annual MHRSD decision.
- HT-2. At Request and on every window change, a window overlapping 12:00–15:00 on a ban date is rejected `MIDDAY_BAN_WINDOW` (split it, e.g. 06:00–12:00 and 15:00–18:00), unless an exemption exists (HT-4).
- HT-3. At 12:00 − `midday_ban_prewarn_minutes` the receiver and issuer are warned; at 12:00 every Active non-exempt permit in scope is Suspended `midday_ban` (routine); Resume is allowed from 15:00 and needs the GT-4 post-break test where gas testing applies.
- HT-4. Exemption (capability 102, per permit, per date range): reason ∈ {`emergency_repair`, `exempt_activity_mhrsd` (`VERIFY` list), `shaded_and_cooled_workplace`} plus heat controls text ≥ 30 chars; audited; listed in the action panel while active.
- HT-5. Outdoor permits in `heat_season` (Phase 1 setting) record ambient_temp_c at each shift start; JS-4 requires heat_stress in the JSA. WBGT regimes, stops and rest pauses come from `6b-heat-stress.md` from `heat_ptw_enforcement_from` (v1.3); nothing in Phase 3 lowers them.
- HT-6. CSE internal temperature ≥ `cse_heat_control_temp_c` requires heat controls on the permit (forced cool-air ventilation, stay time per entry ≤ 30 min ASSUMPTION, water at the entry) before entry (`HEAT_CONTROLS_REQUIRED`).

### 5.9 Suspension, shift handover, revalidation (SH)
- SH-1. Any user with capability 88 can suspend (stop work) an Issued/Active permit with reason and detail; the system notifies the receiver immediately. Stop-work is never blocked by any rule.
- SH-2. **Automatic suspensions** (within 60 s): gas test failed / retest overdue / gas alarm; WAP suspended / ops event; NOTAM or obstacle clearance lost; prohibited SIMOPS (SM-7); key role ineligible / hook not met (block policy); wind limit; midday ban; contractor suspended/blacklisted; critical audit finding (AU-4); isolation breach; shift lapsed (SH-5).
- SH-3. Resume after a non-routine suspension needs the issuer to record that the cause is cleared (text ≥ 20 chars) and all Issue-time blockers to be empty; after `audit_critical`, the linked CA must be at least In Progress ASSUMPTION.
- SH-4. **Crew briefing:** at each shift start the receiver records crew_present; each listed worker present must be marked briefed on the JSA and the permit conditions for that shift (signature or tick on the receiver's device); unbriefed workers cannot be in crew_present (`CREW_NOT_BRIEFED`).
- SH-5. **Shift end:** the receiver ends the shift (→ Suspended `shift_end`, routine) or a handover is accepted (SH-6) before planned_end_at; otherwise at planned_end_at the job suspends the permit `shift_lapsed` (K-70) and alerts the receiver, issuer and Contractor HSE Rep.
- SH-6. **Handover** (continuous work): the outgoing receiver initiates with notes (work status, hazards, isolations, persons inside a confined space); the incoming receiver (permit_receiver on the same engagement) and an incoming issuer (Active appointment; may be the same issuer) accept; gas test valid for start when gas testing applies; crew briefing for the new shift; Active continues with a new shift record. Hot work and CSE permits allow at most one handover (§3.1; a second → `HANDOVER_LIMIT`).
- SH-7. **Revalidation** (Suspended `shift_end`/`shift_lapsed` → Active): new shift record, issuer site visit, receiver acceptance, gas test, eligibility, SIMOPS, WAP/NOTAM, wind, checklists re-confirmed; allowed only inside a window and before valid_to_at; types with "none" in §3.1 (radiography) cannot be revalidated (a new permit is needed) (`REVALIDATION_NOT_ALLOWED`; outside a window `OUTSIDE_WINDOW`).
- SH-8. The suspension history is kept per permit (§3.14); routine suspensions (shift_end, midday_ban) are excluded from K-65 and shown separately.
- SH-9. **Pauses** (breaks, prayer, short weather holds) are recorded by the receiver without issuer action; a pause ≥ `gas_break_retest_minutes` needs the GT-4 post-break test before work restarts; a pause longer than 2 h or one that reaches the shift end is not allowed — the receiver ends the shift or suspends instead ASSUMPTION.

### 5.9a Closure and expiry (CL)
- CL-1. **Closure request** (receiver, capability 84): work status `complete` or `incomplete_area_safe` (text ≥ 20 chars on what remains and how it was made safe); closure checklist (list X) answered; crew withdrawn; tools, materials and waste removed; entry log 0 inside (CS-7); personal locks removed from the lockbox (IS-5); for HW, hot_work_ended_at recorded.
- CL-2. **Issuer close** (capability 87): site visit confirmed (`site_visit_confirmed` = true, required); not before fire_watch_until (`FIRE_WATCH_RUNNING`); airside FOD/hand-back done (AW-8); radiography source returned and verified by survey (RG-5). A permit missing any → `CLOSURE_INCOMPLETE` naming the items.
- CL-3. Closing a permit does not de-isolate: isolation points stay on until IS-7 de-isolation; the closure screen lists isolations still applied for the issuer's attention.
- CL-4. Closure of an `incomplete_area_safe` permit adds the remaining work to the permit record; continuing needs a new permit (it may be created as a copy of the closed one, re-entering JSA approval, gas tests and signatures).
- CL-5. Expiry (job, §4.1): every open shift is ended `expired`; crew are notified; the permit counts as not compliant in K-69.
- CL-6. **Post-expiry check** within 24 h by the issuer (or another appointed issuer of the project): site visit, area safe (yes/no + text), entrants 0, personal locks removed, fire watch status for HW; until it is done the permit shows "post-expiry check pending", linked isolations cannot be de-isolated (IS-7), and at 24 h the HSE Officer is alerted. "Area not safe" requires the issuer to raise a corrective action (Phase 1 §3.8, source_type `other`, the permit number in the description) before the check can be saved ASSUMPTION.
- CL-7. A closed, cancelled or expired permit is read-only except attachments added by the issuer within 7 days and audit (document_review) records.

### 5.10 Hooks and Phase 2 links (HK3)
- HK3-1. Phase 3 uses the Phase 2 hook interface HK-3 unchanged in behaviour; subject types: `worker`, `vehicle`, and new `equipment_tag` ({category, tag}) for equipment not in the vehicle register (§11 change). v1.1: every call passes the HK-3 `context` (project_id, zone_id, permit_id, critical, use, equipment_ref, rated_capacity_t, operator_worker_id; `2-access-permits.md` v1.2). Results under `warn` add HOOK_NOT_AVAILABLE ("Certificate check available from Phase 4 / فحص الشهادة متاح من المرحلة 4"; "Training check available from Phase 5 / فحص التدريب متاح من المرحلة 5") and never block; under `block` not_evaluated/not_met → `HOOK_NOT_MET`.
- HK3-2. **Hook requirements registered by Phase 3** (codes free until Phases 4/5 publish lists): crew roles — crane_operator → personnel_certificate CRANE-OPERATOR; rigger → RIGGER; signaller → SIGNALLER; gas_tester → personnel_certificate GAS-TESTER + training_course GAS-TEST; radiographer → RADIOGRAPHER; fire_watch → training_course FIRE-WATCH; entrant → CSE-ENTRANT + medical_fitness CSE-ENTRY-FIT; standby_person → CSE-ATTENDANT; rescue_lead/member → CSE-RESCUE (v1.2: rescue_lead also → training_course FIRST-AID, OSHA 1910.146(k)(2)(iii)); any crew on work_at_height with arrest → training_course WAH (v1.2: **every crew member** on a permit with a work_at_height section, not only arrest users, OSHA 1926.503(a)(1), `5-training.md` §11.4); electrician on electrical_isolation → LOTO, ELEC-QUALIFIED; equipment — tower/mobile/crawler crane → equipment_certificate CRANE-TPI; lifting_accessory/spreader_beam → LIFTING-ACCESSORY-TPI; man_basket → MAN-BASKET-TPI; mewp → MEWP-TPI; scaffold → SCAFFOLD-TAG; appointments — issuer → training_course PTW-ISSUER; receiver (user's linked worker) → PTW-RECEIVER; isolation_authority → LOTO-AUTHORITY. v1.1 defaults added by Phase 4 (HK4-12, codes now published in `4-third-party-cert.md` §3.16): crew role banksman → personnel_certificate BANKSMAN; equipment tripod_winch → equipment_certificate RESCUE-WINCH-TPI; mast_climber/bmu → HOIST-TPI; operator binding per equipment category through operator_worker_id — CRANE-OPERATOR, MEWP-OPERATOR, FORKLIFT-OPERATOR, TELEHANDLER-OPERATOR, PLANT-OPERATOR, HOIST-OPERATOR (HK4-9). v1.2: appointment hooks (issuer, receiver, isolation_authority) are checked for the holder's linked worker (worker.user_id); a holder without a linked worker → not_met `HOLDER_NOT_LINKED` (no hard stop: warn in the transition stage, blocks after the block date; shown to the HSE Manager as a configuration error) (`5-training.md` HK5-7). Phase 5 publishes all these training codes (`5-training.md` §3.15).
- HK3-3. A hook result is evaluated at the times in PT-8; its valid_until must cover the shift's planned_end_at (LF-5).
- HK3-4. Medical-fitness results are shown to roles without capability 56 only as "Not eligible — HSE check / غير مؤهل — مراجعة السلامة" with no detail (P3-3).
- HK3-5. Phase 3 never writes Phase 2 records. It reads through `access_eligibility`, `active_waps` and the Phase 2 event stream (§11): WAP status changed, NTM status changed, OBS status changed, ops event started/ended, credential or worker status changed, deployment demobilised. v1.1: also the Phase 4 events `cert.status_changed`, `equipment.status_changed`, `scaffold.tag_changed`, `holder.ban_changed`, `tpi.status_changed`, `hook_policy.changed` (`4-third-party-cert.md` HK4-10); a hard stop, or a not_met after the code's block date, Suspends live permits `hook_not_met`. v1.2: also the Phase 5 events `training.record_changed`, `training.session_voided`, `training.provider_changed` and `hook_policy.changed` for kind training_course (`5-training.md` HK5-8), same handling. Each event re-evaluates affected permits within 60 s.

### 5.11 PTW audits (AU)
- AU-1. Audit types: `field` (live permit), `document_review` (Closed/Expired permit), `unpermitted_work` (no permit). Only `field` audits feed K-46, K-46b and K-61; unpermitted_work feeds K-64.
- AU-2. Auditor ≠ issuer, receiver, area authority, HSE reviewer of the audited permit (`SOD_CONFLICT`); a Contractor HSE Rep may audit permits of their C scope (self-audit counts) ASSUMPTION.
- AU-3. Items: A01–A05, A14–A16, A20 always apply; type items apply per the permit's types (A06 only if GT-1 applies, A07 if an isolation is linked, A08–A09 hot work, A10 CSE, A11 WAH, A12 excavation, A13 lifting, A17 radiography, A18 airside, A19 outdoor exposure in heat_season); n.a. allowed only for items that do not apply.
- AU-4. A non-compliant item with severity critical on a field audit **suspends the permit** (`audit_critical`) within 60 s and requires a CA (Phase 1, source_type `ptw_audit`, priority critical); major → CA required (priority high); minor → CA optional.
- AU-5. An audit cannot be Completed while a required CA is missing (`CA_REQUIRED`).
- AU-6. `unpermitted_work` audits have one item A00 (critical), require a stop-work record and a critical CA on the engagement; they count in K-64 and in the contractor's critical findings.
- AU-7. Audit plan: each project has a weekly target `ptw_audit_min_per_week`; the action panel shows "behind plan" when completed field audits since the week start (week_start setting) < target × elapsed working days ÷ working days in week ASSUMPTION.
- AU-8. Photos in audits carry the hint "avoid faces"; findings never name workers (as Phase 1 O-4).

### 5.12 KPIs and AI (KP)
- KP-1. All PTW KPIs are computed by the backend (Phase 1 D-1).
- KP-2. Date attribution (project tz): permits issued → first issued_at; permit-shifts → shift started_at; audits → audited_at; suspensions → suspended_at; closures/expiries → the terminal transition time; conflicts → detected_at.
- KP-3. Contractor attribution: permits, shifts, suspensions → permit engagement; audits → audited permit's engagement (unpermitted_work → entered engagement). Contractor filter with descendants as Phase 1 K-R5.
- KP-4. Type attribution: primary_type for counts by type; "any type" breakdown counts a permit once under each of its types.
- KP-5. AI tool **T15 `get_ptw_kpis`** (project_ids, period, filters {site, zone, engagement, include_descendants, type}, metrics K-46, K-46b, K-61…K-71, group_by {type, contractor, zone, month, week, suspension_reason, audit_item, simops_rule}) returns aggregates only; T13 additionally returns E8–E9; T9 gains dimension `ptw_audit_band` (contractor-months with K-61 < `ptw_audit_warning_pct` vs ≥) for "PTW audit performance vs incidents"; T4/T5 add linked permit numbers and types (no names). AI-5 applies: no names, worker_no, signatures or appointment holders are sent to the model.
- KP-6. Viewer/Client sees PTW KPIs, the live board counts and expiring-item counts as aggregates only.

### 5.13 PDPL (P3-x, extends P1–P13, P1-x, P2-x)
- P3-1. Classes as in §3. Personal: crew lists, appointments, signatures, entry logs, gas tester identity, audit photos, lock holders. No sensitive class field is created by Phase 3 except hook results of kind `medical_fitness` (status only, sensitive) displayed per HK3-4.
- P3-2. Minimisation: no ID numbers, nationality, date of birth or medical data on permits, prints, exports or alerts; workers are shown by name and worker_no (capability 46 holders) or by role only.
- P3-3. Fitness outcomes: the platform stores only met / not_met from the Phase 6 provider, never the reason.
- P3-4. Radiography: no personal dose values; only "dosimetry confirmed".
- P3-5. Signatures of workers without accounts (gas tester, crew briefing) are images stored in the encrypted personal bucket (Phase 2 P2-2), served by signed URLs ≤ 5 min, deleted when the worker record is anonymised (Phase 2 P2-7); the permit keeps "signed by Anonymised worker WKR-nnnnnn".
- P3-6. Retention: permits and all linked records are kept for project life + `ptw_retention_years`; permits linked to an incident follow that incident's retention (Phase 1 P1-5); confined-space permits are kept at least 1 year after closure (OSHA 1910.146(e)(6)) — always satisfied by the default.
- P3-7. Exports (capability 104) include names only for capability 46 holders and never signatures; every export is audited (Phase 0 rule 49).
- P3-8. Free-text fields get the P3 hint and the Phase 1 P1-8 ID scan.
- P3-9. Optional issuer device location at site visit (PT-14) is stored only as "confirmed on site: yes" — coordinates are not stored ASSUMPTION.

### 5.14 Permission matrix — Phase 3 extension (continues Phase 2 §5.13; legend A/P/S/C/C1/R/—; "+appt" = also needs the matching Active appointment)

| # | Capability | HSE Mgr | HSE Officer | Site Eng/Sup | Permit Issuer | Permit Receiver | Contractor HSE Rep | Viewer/Client |
|---|---|---|---|---|---|---|---|---|
| 82 | View permits, live board, gas tests, isolations, conflicts (names need 46) | A | P | S | S | C1 | C | P (counts, PT-19) |
| 83 | Prepare/edit Draft permit, JSA instance, documents | — | — | S | — | C1 | C | — |
| 84 | Act as named receiver: request, accept issue, start/end shift, handover, request closure | — | — | — | — | C1 | — | — |
| 85 | Review as area authority (+appt) | — | P | S | S | — | — | — |
| 86 | HSE review of high-risk permits; accept High residual risk | A | P | — | — | — | — | — |
| 87 | Approve, issue, revalidate, resume, close (+appt issuer) | — | — | — | S | — | — | — |
| 88 | Suspend / stop work | A | P | S | S | C1 | C | — |
| 89 | Cancel permit | A | P | — | S | C1 (own, Draft/Requested) | — | — |
| 90 | Record gas test and bump test (as or for an appointed gas tester) | A | P | S | S | C1 | C | — |
| 91 | Manage gas detectors and calibrations | A | P | — | — | — | C | — |
| 92 | Plan, apply, verify, remove isolation points (+appt isolation authority) | — | P | S | S | — | — | — |
| 93 | Record personal locks on/off for crew | — | — | S | S | C1 | C | — |
| 94 | Authorise de-isolation | — | — | — | S | — | — | — |
| 95 | Approve lock cut (IS-9) | A | — | — | — | — | — | — |
| 96 | Manage / approve JSA templates (contractor reps propose) | A | P | — | — | — | C (propose) | — |
| 97 | Sign SIMOPS coordination (as issuer of either permit; area authority +appt) | — | P (as area authority) | S (as area authority) | S | — | — | — |
| 98 | Edit zone PTW profiles and zone adjacency | A | P | — | — | — | — | — |
| 99 | Edit SIMOPS matrix, permit type configuration, checklists, gas limits, Phase 3 settings | A | — | — | — | — | — | — |
| 100 | Manage PTW appointments (issuer appointments HSE Manager only) | A | P (non-issuer) | — | — | — | — | — |
| 101 | Conduct PTW audit (field, document review, unpermitted work) | A | P | S | S | — | C | — |
| 102 | Grant midday-ban exemption; approve energized work; approve fire-system impairment; approve capacity > 90 % | A | — | — | — | — | — | — |
| 103 | View PTW KPIs, PTW band, PTW expiring items and action panel | A | P | S | S | C1 | C | P (aggregates) |
| 104 | Export PTW registers | A | P | S | — | — | C | P (no names) |

Suspended-contractor users keep reads and lose writes (Phase 0 rule 28); a Suspended contractor's receivers cannot act (PT-6). Phase 0 rule 16 and PR-5 both apply.

## 6. Calculations

All times local Asia/Riyadh (Phase 0 K2); exact decimal arithmetic on unrounded values; output rounding per Phase 1 K-R8 except PT-21 (minimum distances rounded up to 0.1 m).

### 6.1 Risk score (5×5)
score = L × S, L (likelihood) and S (severity, Phase 1 list S) integers 1–5. Band: 1–4 Low · 5–9 Medium · 10–14 High · 15–25 Extreme. Governing residual band of a JSA = band of max(residual score) over all lines.

| S \ L | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| 5 | 5 M | 10 H | 15 E | 20 E | 25 E |
| 4 | 4 L | 8 M | 12 H | 16 E | 20 E |
| 3 | 3 L | 6 M | 9 M | 12 H | 15 E |
| 2 | 2 L | 4 L | 6 M | 8 M | 10 H |
| 1 | 1 L | 2 L | 3 L | 4 L | 5 M |

### 6.2 Gas acceptance limits (defaults; tighten only)

| Gas | General / cold work, excavation | Confined space entry | Hot work (incl. hot work inside a confined space) |
|---|---|---|---|
| O₂ (% vol) | 19.5 ≤ x ≤ 23.5 | 19.5 ≤ x ≤ 23.5 | 19.5 ≤ x ≤ 23.5 |
| Flammables (% LEL) | x < 10 | x < 5 ASSUMPTION `VERIFY` client (OSHA: 10) | x < 1 (i.e. 0 on a 1 %-resolution sensor) |
| H₂S (ppm) | x < 1 | x < 1 | x < 1 |
| CO (ppm) | x < 25 | x < 25 | x < 25 |
| Other toxics | < TLV-TWA entered per gas | same | same |

Applicable limit for a permit = the strictest value of each gas across its work types (CSE + hot work → LEL < 1). Result = pass iff every reading at every point satisfies every applicable limit; failing codes list every gas that failed.

### 6.3 Gas-test timing
- valid_for_start_until = tested_at + `gas_pre_start_validity_minutes`.
- next_due_at = tested_at (latest passing test) + interval, interval = min over the permit's types of `gas_retest_interval_minutes[type]` among types requiring tests (GT-1).
- Pauses and suspensions: while the shift is paused (§3.13 pauses) or the permit is Suspended, no test falls due; work may restart only if (a) the pause/suspension lasted < `gas_break_retest_minutes` and now < next_due_at, or (b) a passing test with tested_at ≥ now − `gas_pre_start_validity_minutes` exists.
- **Shift gas compliance (K-66):** a gas-required shift is compliant iff the start test was valid at started_at, at every instant of work in progress (Active, not paused) the latest passing test was ≤ interval old, and every restart after a pause/suspension ≥ `gas_break_retest_minutes` was preceded by a passing test within start validity.

### 6.4 Distance
d(A, B) = √((x_A − x_B)² + (y_A − y_B)²) in site-grid metres (unrounded for comparison; displayed 1 dp). Fallbacks per SM-2. Vertical: A above B iff elevation_A ≥ elevation_B + `vertical_separation_m`.

### 6.5 Windows and overlap
window(d) local = [d + start, d′ + end), d′ = d + 1 if end ≤ start else d (as Phase 2 §6.7); clipped to [valid_from_at, valid_to_at]. Two permits overlap iff any window instance of A intersects any window instance of B (half-open intervals). Shift planned_end_at = min(started_at + `ptw_shift_max_hours`, end of the current window instance, valid_to_at).

### 6.6 Lift capacity
gross_t = load_weight_t + rigging_weight_t; capacity_pct = gross_t ÷ rated_capacity_t × 100 (1 dp half-up for display; LF-2/LF-3 compare unrounded).

### 6.7 Radiography barrier (guidance, unshielded point source, inverse square)
D₁ (µSv/h at 1 m) = Γ × A × 1,000 for isotopes (Γ in mSv·m²·GBq⁻¹·h⁻¹; reference values Ir-192 0.13, Se-75 0.054, Co-60 0.35 `VERIFY` against the licensee's radiation protection plan) or the X-ray set's datasheet value. computed_barrier_m = ceil₀.₁( √(D₁ × collimator_transmission ÷ `rg_barrier_limit_usv_h`) ). The survey (RG-3) is the control; the calculation only prevents an obviously small barrier.

### 6.8 Audit score
score_pct = compliant_count ÷ applicable_count × 100 (n.a. excluded); 1 dp half-up.

### 6.9 Fall clearance (arrest with energy-absorbing lanyard, anchor at or above D-ring)
required_clearance_m = lanyard_length_m (free fall) + max(1.07, manufacturer deceleration) + 0.30 (harness stretch / D-ring shift) + 1.50 (D-ring to feet) + 0.90 (safety margin) ASSUMPTION `VERIFY` manufacturer. SRL: required = srl_required_clearance_m from the manufacturer. Pass iff required ≤ available_clearance_m.

### 6.10 Detector dates
calibration_due_on = min(calibrated_on + `detector_calibration_interval_days`, certificate due date if entered). Bump test valid for tests on the same local date with tested_at after the bump test.

### 6.11 KPI catalogue (continues Phase 2 §6.8; K-46 replaces the Phase 1 placeholder)

| ID | Metric (EN / AR) | Formula | Unit / display | Better |
|---|---|---|---|---|
| K-46 | **PTW field audits** / تدقيقات تصاريح العمل الميدانية | n(audits type field, Completed or Locked, audited_at in period) | count | higher |
| K-46b | PTW audit coverage / تغطية تدقيق التصاريح | n(distinct permits with ≥ 1 field audit in period) ÷ n(distinct permits Issued, Active or Suspended at any time in period) × 100; denominator 0 → "—" | %, 1 dp | higher |
| K-61 | **PTW audit compliance** / نسبة الالتزام في تدقيق التصاريح | Σ compliant_count ÷ Σ applicable_count × 100 over field audits in period | %, 1 dp | higher |
| K-62 | Permits issued / التصاريح الصادرة | n(permits with first issued_at in period); breakdown by primary type, any type, high-risk | count | — |
| K-63 | Permit-shifts / ورديات التصاريح | n(shift records with started_at in period) | count | — |
| K-64 | **Critical PTW findings (PTW violations)** / المخالفات الحرجة لتصاريح العمل | n(critical non-compliant items in field audits in period) + n(unpermitted_work audits in period); rate = count × 100 ÷ K-46 (K-46 = 0 → "—") | count; per 100 field audits, 2 dp | lower |
| K-65 | Non-routine suspensions / الإيقافات غير الاعتيادية | n(suspension events in period with routine = false); rate = count × 100 ÷ K-63; breakdown by reason; routine (shift_end, midday_ban) shown separately | count; per 100 permit-shifts, 2 dp | — (context) |
| K-66 | **Gas-test compliance** / الالتزام بفحص الغاز | n(compliant gas-required shifts ended in period, §6.3) ÷ n(gas-required shifts ended in period) × 100 | %, 1 dp | higher |
| K-67 | Active isolations / العزل النشط | n(certificates Isolated, Verified or De-isolation Requested at as_of); of which long-term | count | — |
| K-68 | SIMOPS conflicts / تعارضات العمليات المتزامنة | n(conflicts detected in period) by result; n(open at as_of) | count | — |
| K-69 | **Permit closure compliance** / الالتزام بإغلاق التصاريح | n(permits Closed in period) ÷ n(permits Closed or Expired in period) × 100 | %, 1 dp | higher |
| K-70 | Shift lapses / انقضاء الورديات دون تسليم | n(shift records with end_type lapsed and ended_at in period) | count | lower |
| K-71 | Permit turnaround / مدة إصدار التصريح | median over permits first Issued in period of (first issued_at − first requested_at) in hours; even n → mean of the two middle values | h, 1 dp | lower |

### 6.12 Leading-indicator warnings (extend Phase 1 §6.9; monthly job day 2, per project and per tier-1 tree)
- **E8** (field audits in M ≥ 10 **and** K-61(M) < `ptw_audit_warning_pct`) **or** K-64 count(M) ≥ `ptw_critical_findings_warning`.
- **E9** (permits Closed + Expired in M ≥ 10 ASSUMPTION **and** K-69(M) < `ptw_closure_warning_pct`) **or** (K-70(M) ≥ 2 × mean(K-70 of M−3, M−2, M−1) **and** K-70(M) ≥ 5).

### 6.13 Worked examples (exact; backend unit tests must match)

**Y1 — JSA risk and acceptance (RBT-52, PTW-RBT-52-2026-0287, slab edge L38).** Line 1 fall_from_height: initial 4 × 5 = **20 Extreme**; controls perimeter edge-protection system (engineering), exclusion of non-essential persons (administrative), SRL on cast-in anchor (PPE); residual 2 × 5 = **10 High**. Line 2 falling_objects: 3 × 4 = **12 High** → toe-boards + debris netting (engineering), drop-zone barricade at L37 and ground (administrative) → 1 × 4 = **4 Low**. Governing residual **High** → acceptance by issuer Majed **and** HSE Officer Lina with ALARP text (JS-7); line 1 has an engineering control → OK. Variants: residual 3 × 5 = **15 Extreme** → Approve rejected `JSA_RESIDUAL_EXTREME`; a line 3 × 3 = 9 Medium with only PPE controls and residual 1 × 3 = 3 Low → `PPE_ONLY_CONTROLS`; residual 2 × 3 = 6 Medium with PPE only → accepted (band unchanged); a line 3 × 4 → 2 × 3 with administrative controls only → warning `SEVERITY_REDUCED_WITHOUT_HIGHER_CONTROL`.

**Y2 — gas acceptance (PTW-ANIA-EXP-2026-0413, manhole MH-07, CSE).** Pre-entry 07:40, GD-ANIA-003: top 20.9 % O₂ / 0 % LEL / 0 ppm H₂S / 3 ppm CO; middle 20.8 / 0 / 0 / 4; bottom 20.6 / 2 / 0 / 6. CSE limits → worst O₂ 20.6 (in range), LEL 2 < 5, H₂S 0 < 1, CO 6 < 25 → **pass**. The same readings on a permit with confined_space + hot_work → LEL 2 ≥ 1 → **fail `LEL_ABOVE_LIMIT`**. Bottom O₂ 19.4 → **fail `O2_OUT_OF_RANGE`**. H₂S 1 ppm → **fail `H2S_ABOVE_LIMIT`**. On a general permit (cold limits) the original readings pass.

**Y3 — gas timing (same permit, CSE interval 60 min, break threshold 30 min).** Bump test 07:30 pass. Test 07:40 pass → valid for start until **08:10**, next due **08:40**. Issued 07:50; Start 07:55 (✓ ≤ 08:10 and ≤ 07:50 + 60). Periodic 08:38 pass → next due **09:38**. Pause 09:15–09:50 (35 min ≥ 30) → post-break test required; 09:48 pass → restart 09:50 ✓, next due **10:48**. No test by 10:48 → Suspended `gas_retest_overdue` at 10:48. Shift compliance: max age of the latest test during work = 58 min (07:40 → 08:38) → **compliant**. Variant without the 08:38 test: due 08:40, work continues → suspended 08:40 and the shift is **non-compliant** for K-66. Variant: test at 07:25 before the 07:30 bump test → rejected `BUMP_TEST_MISSING`.

**Y4 — fire watch (PTW-ANIA-EXP-2026-0412, hot work Pier B, valid 07:00–19:00).** hot_work_ended_at 15:20 → fire_watch_until **16:20**; close at 16:05 → `FIRE_WATCH_RUNNING`; at 16:21 → Closed. Latest compliant end = 19:00 − 60 min = **18:00**; an end at 18:30 → flag `HOT_WORK_LATE`, fire_watch_until 19:30, expiry waits until **19:30** if not closed.

**Y5 — midday ban (fixture, GULFPAVE outdoor_direct_sun permit on Z-APR-21).** Date 2026-09-10, window 06:00–18:00 → 422 **`MIDDAY_BAN_WINDOW`**; windows 06:00–12:00 + 15:00–18:00 → accepted. Active at 11:45 → prewarn; 12:00 → Suspended **`midday_ban`** (routine; shift 1 ends type suspended). Resume at 14:59 → `MIDDAY_BAN`; at 15:00 → Active, shift 2 (post-break gas test only if GT-1 applies). Date 2026-09-16, window 06:00–18:00 → accepted (ban ended 09-15). Date 2026-06-15 → ban applies (inclusive).

**Y6 — shift end, handover, revalidation.** (a) PTW-0412 shift 1 started 07:10 → planned_end_at = min(19:10, window end 19:00, valid_to 19:00) = **19:00**; still Active at 19:00 → `shift_lapsed` (K-70 + 1). (b) PTW-ANIA-EXP-2026-0408 window 23:00–05:00: shift started 2026-10-05 23:05 → planned_end_at **2026-10-06 05:00**; receiver ended it 04:52 → Suspended `shift_end`; revalidation attempt 2026-10-06 22:40 → `OUTSIDE_WINDOW`; at 23:00 → allowed. (c) Fixture general permit, window 06:00–06:00 (24 h): shift 1 06:00 → planned_end_at **18:00** (12 h cap); handover initiated 17:30, accepted 17:50 → shift 2 started 17:50, planned_end_at = min(05:50 next day, 06:00) = **05:50**; if not accepted by 18:00 → handover Lapsed, permit Suspended `shift_lapsed`.

**Y7 — lifting.** (a) PTW-RBT-52-2026-0290, TC-01: gross 4.200 + 0.150 = **4.350 t**; capacity at 42.00 m = 5.000 t → **87.0 %** ≥ 75 → critical [capacity]; duration ≤ 1 day. (b) PTW-ANIA-EXP-2026-0410, VEH-0003: 6.800 + 0.350 = 7.150 t ÷ 12.400 t → **57.7 %** → critical [airside_movement_area] (apron). (c) NAJD Pier B, NJ-MC-02: 2.200 ÷ 9.800 → **22.4 %**, landside, < 20 t → routine. (d) 4.900 + 0.150 = 5.050 ÷ 5.000 → **101.0 %** → `CAPACITY_EXCEEDED`. (e) 4.550 ÷ 5.000 → **91.0 %** → HSE Manager approval required (LF-3). Wind: 0290 limit 13.0 m/s, reading 8.2 → OK, 13.4 → `WIND_LIMIT_EXCEEDED`; 0410 limit 9.8, reading 7.2 → OK, 11.0 → blocked.

**Y8 — SIMOPS distances.** (a) Hot work 0412 at (120.0, 45.0) vs fixture painting permit (flammables_in_use) at (126.0, 53.0): d = **10.0 m** ≤ 11.0 → SM-R03 **prohibited**; at (130.0, 52.5): d = **12.5 m** → no match. (b) Fixture CSE at (128.0, 51.0): d = **10.0 m** ≤ 15.0 → SM-R02 **conditional**. (c) RBT-52 WAH 0287 (40.0, 18.0, elev 152.00) vs hot work 0288 (42.0, 20.0, elev 148.00): d = 2.828… → **2.8 m** ≤ 6.0 and 152.00 ≥ 148.00 + 2.0 → SM-R06 **conditional** (SIM-RBT-52-2026-0019 coordinated). (d) Lift 0290 (appliance (60.0, 30.0), slew 60.0; landing (45.0, 22.0), exclusion 5.0) vs WAH 0287: to landing **6.4 m** > 5.0 → no R05a; to appliance **23.3 m** ≤ 60.0 → SM-R05b **conditional**, overlap 2026-10-07 06:30–10:00 (SIM-RBT-52-2026-0021, open). Fixture hot work at (42.0, 20.0) valid 2026-10-07 07:00–16:00: to landing **3.6 m** ≤ 5.0 → SM-R05a **prohibited** for the overlap 07:00–10:00. Seeded hot work 0288 (valid 2026-10-06 only) has no time overlap with 0290 → no conflict.

**Y9 — radiography barrier (PTW-ANIA-EXP-2026-0399, Ir-192 1,110.0 GBq).** D₁ = 0.13 × 1,110 × 1,000 = **144,300 µSv/h**. No collimator: √(144,300 ÷ 7.5) = √19,240 = 138.708… → **138.8 m**. Collimator transmission 0.0625: √(9,018.75 ÷ 7.5) = √1,202.5 = 34.677… → **34.7 m**. planned_barrier_m 40.0 → OK; 30.0 → `BARRIER_TOO_SMALL`. Survey max 5.8 µSv/h → verified; 8.1 → `BARRIER_NOT_VERIFIED`. Source at (300.0, 200.0): a permit at (320.0, 180.0) is **28.3 m** away ≤ 40.0 → SM-R01 **prohibited**; at (330.0, 230.0) **42.4 m** → no match.

**Y10 — fall clearance.** Lanyard 1.80 m: 1.80 + 1.07 + 0.30 + 1.50 + 0.90 = **5.57 m** > available 4.00 m (L38 → L37 slab) → `FALL_CLEARANCE_INSUFFICIENT`; lanyard 1.20 m → **4.97 m** > 4.00 → still insufficient; SRL with manufacturer clearance 2.40 m ≤ 4.00 → **pass** (seed 0287). Lanyard 1.80 m with available 6.00 m → pass.

**Y11 — detectors and appointments.** GD-ANIA-003 calibrated 2026-07-02 → due **2026-12-29**. GD-ANIA-005 calibrated 2026-03-30 → due **2026-09-26** → Quarantined 2026-09-27 00:05; a test with it on 2026-10-06 → `DETECTOR_CALIBRATION_OVERDUE`. GD-RBT-001 calibrated 2026-05-10 → due **2026-11-06** → 30-day alert on **2026-10-07**. Appointment APT-ANIA-EXP-0011 (Salem, gas tester) valid_to 2026-10-20 → 14-day alert on **2026-10-06**; a CSE permit with valid_to_at 2026-10-21 07:00 naming Salem → warning `APPOINTMENT_EXPIRES`, and a shift starting 2026-10-21 → `APPOINTMENT_INVALID`.

**Y12 — KPI fixture = seed, September 2026 (as_of 2026-09-30).**

| Metric | ANIA-EXP calculation | ANIA-EXP | RBT-52 calculation | RBT-52 |
|---|---|---|---|---|
| K-62 issued | general 34, hot_work 28, WAH 22, lifting 14 (critical 3), excavation 8, electrical 6, CSE 4, radiography 2, airside_works 2 | **120** | WAH 14, hot_work 12, lifting 10 (critical 4), general 5, electrical 2, excavation 1 | **44** |
| K-63 permit-shifts | | **610** | | **240** |
| K-46 field audits | (+ 20 document reviews, not counted) | **64** | | **22** |
| K-46b coverage | 58 ÷ 131 × 100 = 44.274… | **44.3 %** | 21 ÷ 47 × 100 = 44.680… | **44.7 %** |
| K-61 compliance | 1,361 ÷ 1,472 × 100 = 92.459… | **92.5 %** | 471 ÷ 506 × 100 = 93.083… | **93.1 %** |
| K-64 critical findings | 3 field + 1 unpermitted_work = 4; 4 × 100 ÷ 64 | **4 / 6.25** | 1; 1 × 100 ÷ 22 = 4.545… | **1 / 4.55** |
| K-65 non-routine suspensions | ops_suspension 5, gas_test_failed 2, audit_critical 3, stop_work 4, key_role_ineligible 1, wind_limit 2, simops_conflict 1 = 18; 18 × 100 ÷ 610 = 2.950… (routine midday_ban 41) | **18 / 2.95** | 6; 6 × 100 ÷ 240 | **6 / 2.50** |
| K-66 gas compliance | 91 ÷ 96 × 100 = 94.791… | **94.8 %** | no gas-required shifts | **—** |
| K-67 isolations at 09-30 | | **7 (2 long-term)** | | **2 (0)** |
| K-68 conflicts | prohibited 2, conditional 7; open 0 | **9** | conditional 4 | **4** |
| K-69 closure compliance | 113 ÷ (113 + 4) × 100 = 96.581… | **96.6 %** | 38 ÷ 41 × 100 = 92.682… | **92.7 %** |
| K-70 shift lapses | | **5** | | **2** |

Audit history (field audits / K-61 / K-64 count / K-69 / K-70): ANIA-EXP Jun 58 / 90.1 % / 1 / 97.0 % / 3 · Jul 61 / 88.4 % / 2 / 95.8 % / 4 · Aug 60 / 91.0 % / 2 / 96.9 % / 2 · Sep 64 / 92.5 % / 4 / 96.6 % / 5. RBT-52 Jun–Aug: K-61 ≥ 92.0 %, K-64 ≤ 1, K-69 96.0 / 95.5 / 97.1 %, K-70 1 / 2 / 1.
Expected warnings for Sep 2026: **E8 ANIA-EXP** (K-64 = 4 ≥ 3; K-61 92.5 % ≥ 85 does not trigger); no E8 RBT-52; **E9 RBT-52** (K-69 92.7 % < 95.0 with 41 ended permits); no E9 ANIA-EXP (K-69 96.6 %; K-70 5 < 2 × mean(3, 4, 2) = 6.0). No E8/E9 for ANIA-EXP Jun–Aug.

**Y13 — turnaround median (fixture).** Six permits issued in the period with request→issue hours 2.0, 3.5, 4.0, 5.0, 8.0, 26.0 → median = (4.0 + 5.0) ÷ 2 = **4.5 h**; with a seventh at 30.0 h → **5.0 h**.

**Y14 — audit score.** Field audit of PTW-0413 (CSE) at 08:50: applicable A01–A05, A14, A15, A16, A20, A06, A10 = 11; A14 non-compliant (minor) → 10 ÷ 11 × 100 = 90.909… → **90.9 %**. Variant: A10 standby absent (critical) as well → 9 ÷ 11 = **81.8 %**, permit Suspended `audit_critical`, critical CA required. Entity example 17 ÷ 18 → **94.4 %**.

## 7. Alerts & expiries

Channels as Phase 1/2 (in-app + email in recipient language; SMS where marked, ASSUMPTION). Workers have no accounts: alerts about crew go to the receiver and the Contractor HSE Rep of the engagement (C scope). Texts carry the permit number, type letters, zone and reason — never ID numbers, nationality or fitness detail.

| Trigger | Recipient | Timing | Channel |
|---|---|---|---|
| Permit Requested | Area authority | Immediately; reminder at 4 h; HSE Officer at 8 h if still Requested | In-app + email |
| Permit Reviewed (high-risk) | HSE reviewer; issuer | Immediately | In-app |
| Permit Approved / returned / cancelled | Receiver; Contractor HSE Rep | Immediately | In-app |
| Approved but not Issued at window start + 60 min | Receiver; issuer | Once | In-app |
| Issue lapsed (Issued → Approved) | Receiver; issuer | Immediately | In-app |
| Shift end approaching | Receiver; issuer | planned_end_at − 60 min and − 15 min | In-app (+ push) |
| Shift lapsed (SH-5) | Receiver; issuer; Contractor HSE Rep; HSE Officer | Immediately | In-app + email |
| Gas retest due | Receiver; gas tester (if user) | next_due_at − 10 min; at due | In-app (+ push) |
| Gas test failed / gas alarm / retest overdue | Receiver; issuer; HSE Officer; Contractor HSE Rep; HSE Manager for confined space | Immediately | In-app + email + SMS |
| Any automatic non-routine suspension | Receiver; issuer; Contractor HSE Rep; HSE Officer | Within 60 s | In-app + email |
| Midday ban | Receivers and issuers of in-scope Active permits | 12:00 − `midday_ban_prewarn_minutes`; at 12:00 | In-app (+ push) |
| Fire watch ended (closure possible) | Receiver; issuer | At fire_watch_until | In-app |
| Permit valid_to approaching | Receiver; issuer | Duration > 24 h: 72 h / 24 h / 0 h (Phase 2 short schedule); ≤ 24 h: valid_to − 2 h | In-app |
| Permit Expired; post-expiry check pending (CL-6) | Receiver; issuer; HSE Officer | At expiry; HSE Officer again at 24 h if check pending | In-app + email |
| SIMOPS conflict detected (prohibited / conditional) | Issuers and receivers of both permits; area authority | Immediately | In-app + email |
| Critical audit finding / unpermitted work | Receiver; issuer; Contractor HSE Rep; HSE Officer; HSE Manager | Immediately | In-app + email + SMS |
| Audits behind weekly plan (AU-7) | HSE Officers | Daily 07:00 while behind | In-app |
| Gas detector calibration due | Owner's Contractor HSE Rep; HSE Officer at 7 and 0 | 30 / 14 / 7 / 0 days before calibration_due_on | In-app + email |
| Detector quarantined | Owner's Contractor HSE Rep; HSE Officer | Immediately | In-app |
| PTW appointment expiry | Holder (if user); appointing user; HSE Manager for issuer appointments | 30 / 14 / 7 / 0 days | In-app + email |
| JSA template review due | HSE Officers | 30 / 0 days | In-app |
| Long-term isolation weekly review due / missed | Isolation authority; HSE Officer when missed | Weekly; +1 day | In-app |
| Isolation with no live permit > 24 h (orphan) | Isolation authority; issuer; HSE Officer | Daily 07:00 | In-app |
| Lock cut (IS-9) | HSE Manager; HSE Officers; holder's Contractor HSE Rep | Immediately | In-app + email |
| Hook / eligibility valid_until earlier than permit valid_to | Receiver; Contractor HSE Rep | On detection; 7 days before | In-app |
| Exemption requested / granted (HT-4, EL-3, HW-8, LF-3) | HSE Manager (request); HSE Officers (granted) | Immediately | In-app + email |
| Leading warnings E8–E9 | HSE Manager; HSE Officers; Contractor HSE Rep of affected tree | Monthly, day 2 | In-app + email |

## 8. Reports / KPIs fed

### 8.1 Dashboard additions (Phase 1 §8.1)
1. **Leading tiles:** K-46 PTW field audits (replaces the "Phase 3" placeholder) with K-46b coverage chip; K-61 audit compliance; K-64 critical PTW findings (+ rate); K-66 gas-test compliance; K-69 closure compliance.
2. **PTW band** (all projects): Active permits now by primary type; non-routine Suspended now; high-risk Active now (CSE, hot work in gas/hazardous zones, critical lifts, radiography, HV/energized, excavation ≥ 1.2 m, movement-area works); active isolations (K-67, long-term chip); open SIMOPS conflicts; field audits this week vs plan.
3. **Charts:** C13 permits issued by month, stacked by primary type, with high-risk share line; C14 K-61 monthly line with K-64 bars; C15 non-routine suspensions by reason for the period.
4. Filters D-2 apply (site, zone, contractor with subcontractors, period) plus permit type.

### 8.2 Expiring-items panel — new `ExpiringItemKind` values
`ptw_valid_to`, `ptw_shift_end`, `gas_retest_due`, `fire_watch_end`, `gas_detector_calibration_due`, `ptw_appointment_expiry`, `isolation_review_due`, `jsa_template_review_due`. Item fields as Phase 2 §8.2 (ref = permit/detector/appointment no; title without names for callers without capability 46; due_date/due_at; days_left or minutes_left; engagement; detail_path).

### 8.3 Action panel additions
Requested > 4 h not reviewed · Approved not issued at window start + 60 min · non-routine Suspended permits · shift lapses today · Expired permits with post-expiry check pending · gas tests failed (24 h) · open SIMOPS conflicts with a permit starting within 24 h · critical findings whose CA is not In Progress · audits behind plan this week · orphan isolations · quarantined detectors still listed on live permits · active midday-ban exemptions · lock cuts (7 days).

### 8.4 Registers and reports
Permit register (type, status, zone, contractor, dates, high-risk); **live permit board** per zone (Issued/Active/Suspended now, windows, crew counts, gas status and next due, SIMOPS chips, WAP/NOTAM chips); isolation register and lock register; gas test log; detector register; appointment register; JSA template library; SIMOPS conflict log; audit register; suspension log; permit print (PT-20) and closed-permit pack (print view with audit hash footer, Phase 1 design P6).

### 8.5 Feeds to other phases
Phase 1: incident investigation `ptw_ids` (PTW involved vs not, T9), CA source `ptw_audit`, K-46/K-61…K-71, E8–E9. Phase 4: hook requirements of §5.10 become live through providers (crane and operator certificates block under `block` policy); equipment_tag records map to the equipment register. Phase 5: training hooks (PTW-ISSUER, GAS-TEST, CSE-*, FIRE-WATCH, WAH, LOTO). Phase 6: K-61, K-64, K-69 per contractor for contractor scoring; CSE rescue plans for emergency drills; heat module for WBGT regimes.

## 9. Acceptance criteria

Fixtures: Appendix A seed; "today" = 2026-10-06 (Asia/Riyadh), clock times as stated; Phase 2 seed state as in its Appendix A.

**Configuration, appointments, segregation**
1. **Given** a new airside zone with airside_area `taxiway` **Then** its PTW profile has permit_required_all_work = true; **when** HSE Officer Noura sets it to false **Then** 422 `PROFILE_LOOSENING`.
2. **Given** HSE Officer Noura **When** she creates an `issuer` appointment **Then** 403; **when** HSE Manager Faisal creates it **Then** it is Active and audited.
3. **Given** Majed's issuer appointment (RBT-52) does not list radiography **When** he approves a radiography permit **Then** 422 `APPOINTMENT_INVALID`.
4. **Given** PTW-0413 (receiver Faris) **When** Faris is chosen as area authority **Then** 422 `SOD_CONFLICT`; **when** a test permit_issuer user employed by RAWABI approves it **Then** `SOD_CONFLICT`; **when** Khalid approves **Then** success.
5. **Given** Fahad is area authority of PTW-0412 **When** Fahad is set as its issuer **Then** `SOD_CONFLICT`.
6. **Given** Ahmed Raza is fire watch on PTW-0412 **When** he is also listed as hot_work_operative **Then** `SOD_CONFLICT`; **when** he is added as fire watch to a second Active permit **Then** `KEY_ROLE_BUSY`.
7. **Given** Biju Thomas is standby on PTW-0413 **When** he is added as entrant **Then** `SOD_CONFLICT`.
8. **Given** Khalid last authenticated 20 min ago **When** he signs Issue **Then** 401 `REAUTH_REQUIRED`; after re-authentication the Issue succeeds.
9. **Given** HSE Manager edits type_max_duration_days **When** hot_work = 8 or confined_space = 2 **Then** 422 (outside Allowed); hot_work = 7 succeeds and is audited.

**Permit core**
10. **Given** a hot-work Request valid 2026-10-06 07:00 → 2026-10-07 09:00 **Then** 422 `DURATION_EXCEEDS_LIMIT` naming `hot_work`.
11. **Given** zones Z-PIERB (S-LAND) and Z-APR-21 (S-AIR) on one permit **Then** 422 `ZONES_NOT_SAME_SITE`.
12. **Given** DLIFT is Suspended **When** Ibrahim creates a permit for DLIFT@RBT-52 **Then** 422 `CONTRACTOR_SUSPENDED`.
13. **Given** a fixture Active GULFPAVE permit **When** the HSE Manager suspends GULFPAVE **Then** within 60 s it is Suspended `contractor_suspended`; reinstating GULFPAVE leaves it Suspended.
14. **Given** a QIMMA permit **When** Bikash Rai (DLIFT, a QIMMA subcontractor) is added to its crew **Then** 422 `CREW_NOT_IN_TREE`.
15. **Given** Suman Tamang (GEN expired 2026-09-30) is added to a RAWABI S-AIR permit **When** Approve evaluates eligibility **Then** he is `excluded` with `INDUCTION_EXPIRED`; **as supervisor Then** blocker `KEY_ROLE_INELIGIBLE`.
16. **Given** Osman Idris (Iqama expiry 2026-10-20) is rigger on a NAJD lifting permit valid 2026-10-14 → 10-21 **Then** the 10-14 shift starts with warning `EXPIRING_7D`; a shift on 10-21 is blocked `KEY_ROLE_INELIGIBLE` (`ID_EXPIRED`).
17. **Given** PTW-0410 Approved and hook policies `warn` **When** Khalid issues it at 13:05 with wind 7.2 m/s **Then** Issued with warnings `HOOK_NOT_AVAILABLE` for CRANE-OPERATOR (Zaheer) and CRANE-TPI (VEH-0003). (v1.1: valid on the Phase 3 seed, with no Phase 4 providers. With the Phase 4 seed loaded — providers registered 2026-10-01, stage transition at the shared clock 2026-10-06 — both hooks are met: Zaheer's CRANE-OPERATOR to 2027-03-31, VEH-0003 CRANE-TPI to 2026-11-05; see `4-third-party-cert.md` §9.)
18. **Given** a test provider returning not_met for Ali Hassan CRANE-OPERATOR and policy `block` **When** PTW-0290 is issued **Then** 422 `HOOK_NOT_MET`; **given** an Active lifting permit **When** the provider result turns not_met **Then** it is Suspended `hook_not_met` within 60 s. (v1.1: unchanged; Phase 4 behaviour is covered by `4-third-party-cert.md` ACs 37, 73, 86.)
19. **Given** Viewer Sarah opens PTW-0412 **Then** she sees crew count and roles only — no names or worker_no (e2e scan).
20. **Given** Faris is receiver of Active PTW-0413 and PTW-0405 and PTW-0410 is issued (3) **When** a fourth permit for Faris is issued **Then** 422 `RECEIVER_LIMIT`.
21. **Given** a Request with valid_from_at = now − 30 min **Then** 422.
22. **Given** an Approved permit **When** its zone changes **Then** it returns to Requested and the review is cleared.
23. **Given** an Approved permit with blockers **When** Issue is called **Then** 422 listing every blocker code; the contract has no override endpoint.
24. **Given** a permit Issued at 07:00 and not started **When** the job runs at 08:01 **Then** it is Approved again.
25. **Given** any seeded permit print token **Then** it matches `^HSE2:PT:[A-Za-z0-9_-]{22}$` and the print payload contains no ID number or nationality (CI check).

**JSA**
26. **Given** Y1 lines **Then** scores 20/10 and 12/4, governing residual High; **when** only Majed accepts **Then** Approve 422 `RESIDUAL_ACCEPTANCE_MISSING`; after Lina accepts with ALARP text **Then** Approve succeeds; **if** Lina were the JSA author **Then** `SOD_CONFLICT`.
27. **Given** a residual 3 × 5 line **Then** Approve 422 `JSA_RESIDUAL_EXTREME`.
28. **Given** a WAH JSA without `falling_objects` **Then** Submit 422 `JSA_MANDATORY_HAZARD_MISSING`; **given** an outdoor_direct_sun permit dated 2026-07-14 without `heat_stress` **Then** the same error.
29. **Given** a PPE-only line 3 × 3 → 1 × 3 **Then** 422 `PPE_ONLY_CONTROLS`; 3 × 3 → 2 × 3 **Then** accepted.
30. **Given** a template whose review_due_on has passed **When** it is copied **Then** 422 `TEMPLATE_REVIEW_DUE`.

**Gas testing**
31. **Given** the Y2 readings **Then** CSE result pass; CSE + hot work fail `LEL_ABOVE_LIMIT`; bottom O₂ 19.4 fail `O2_OUT_OF_RANGE`; H₂S 1 ppm fail `H2S_ABOVE_LIMIT`.
32. **Given** the Y3 timeline **Then** valid_for_start_until 08:10, next_due 08:40 / 09:38 / 10:48; without a test by 10:48 the permit is Suspended `gas_retest_overdue` at 10:48; the shift is K-66-compliant; the variant without 08:38 is non-compliant.
33. **Given** GD-ANIA-005 (quarantined since 2026-09-27) **When** used for a test **Then** 422 `DETECTOR_CALIBRATION_OVERDUE`; **given** GD-ANIA-003 bump-tested 07:30 **When** a test is saved with tested_at 07:25 **Then** 422 `BUMP_TEST_MISSING`.
34. **Given** a detector without an H₂S sensor **When** used for a CSE test **Then** 422 `DETECTOR_SENSOR_MISSING`.
35. **Given** Faris records Salem's test without Salem's signature **Then** 422; **given** a tester without an Active gas_tester appointment **Then** `APPOINTMENT_INVALID`.
36. **Given** Active PTW-0413 **When** a periodic test fails **Then** it is Suspended `gas_test_failed` immediately, HSE Manager Faisal is alerted, and Resume without a passing `post_alarm` test is 422.
37. **Given** a test saved with tested_at 2 h before saving **Then** 422 `BACKDATED_TEST`.

**Isolations / LOTO**
38. **Given** ISO-ANIA-EXP-2026-0061 points applied by Nasser **When** Nasser verifies them **Then** 422 `VERIFIER_IS_APPLIER`; Faris verifying succeeds.
39. **Given** PTW-0405 shift start with crew_present of 3 and 2 personal locks on LB-ANIA-012 **Then** 422 `PERSONAL_LOCKS_MISSING`.
40. **Given** PTW-0405 Active **When** de-isolation of ISO-0061 is requested **Then** 422 `DEISOLATION_BLOCKED` naming PTW-0405 and personal locks P-ANIA-1101…1103.
41. **Given** a personal lock cut request **When** made without HSE Manager approval **Then** 403; with Faisal's approval, the supervisor's absence confirmation and contact attempts **Then** the lock is `cut` and the alert is sent.
42. **Given** an HV isolation certificate **When** the isolation authority holds only `electrical_lv` **Then** `APPOINTMENT_INVALID`.
43. **Given** a long-term isolation weekly review answered "no" **Then** every linked live permit is Suspended `isolation_breach`.

**SIMOPS**
44. **Given** Y8a (painting permit at 10.0 m from PTW-0412) **Then** Approve 422 `SIMOPS_PROHIBITED` (SM-R03); **when** moved to (130.0, 52.5) **Then** the conflict becomes `resolved_by_change`.
45. **Given** Y8b (CSE at 10.0 m) **Then** Issue 422 `SIMOPS_COORDINATION_REQUIRED` until a record is signed by both issuers and the area authority.
46. **Given** the seed **Then** SIM-RBT-52-2026-0019 (0287 vs 0288, SM-R06, 2.8 m) is coordinated and PTW-0288 is Active; PTW-0290 shows blocker `SIMOPS_COORDINATION_REQUIRED` from SIM-RBT-52-2026-0021 (SM-R05b, 23.3 m); after Majed and Ibrahim sign, the blocker clears.
47. **Given** the Y8d fixture hot work at (42.0, 20.0) on 2026-10-07 07:00–16:00 **When** PTW-0290 is issued at 06:30 **Then** 422 `SIMOPS_PROHIBITED` (SM-R05a, 3.6 m).
48. **Given** Y9 **Then** a permit at (320.0, 180.0) during PTW-0399's window gets `SIMOPS_PROHIBITED` (SM-R01, 28.3 m); at (330.0, 230.0) no conflict.
49. **Given** two permits in Z-PIERB without grid points (hot work + flammables) **Then** distance 0 and SM-R03 applies; **given** hot work in Z-PIERB and CSE in Z-MSCP (adjacency 40.0 m) **Then** no SM-R02 match.
50. **Given** the HSE Manager deletes SM-R01 **Then** 422; tightening SM-R02 to 20.0 m succeeds and is audited.

**Hot work**
51. **Given** Y4 **Then** fire_watch_until 16:20; close at 16:05 `FIRE_WATCH_RUNNING`; at 16:21 Closed; an 18:30 end flags `HOT_WORK_LATE` and expiry waits until 19:30.
52. **Given** fire_system_impairment with impairment_hours_24h 6 and no civil_defense_notified_at **Then** Issue blocked `FIRE_IMPAIRMENT_NOT_APPROVED`; with HSE Manager approval and notification time **Then** allowed.
53. **Given** combustibles_cleared_radius_m 8.0 without a protection method, or an extinguisher at 12.0 m **Then** 422.
54. **Given** hot work in a zone_1 hazardous area **Then** 422 `HAZARDOUS_AREA_PROHIBITED`; **given** hot work on Z-APR-21 (zone_2) **Then** high_risk = true and a gas test with LEL < 1 % is required.
55. **Given** airside hot work on Z-APR-21 with aircraft_proximity `live_stand_adjacent` **Then** 422 `AIRCRAFT_PROXIMITY`.
56. **Given** PTW-0412 **When** Start is attempted without a fire watch in crew_present **Then** 422 `ROLE_MISSING`.

**Confined space**
57. **Given** a CSE permit without rescue plan or standby person **Then** Request 422 `DOCUMENT_MISSING` / `ROLE_MISSING`.
58. **Given** a pre-entry test with 2 points **Then** 422 `CSE_POINTS_REQUIRED`.
59. **Given** PTW-0413 entry log with persons inside (seed: 2) **When** closure, shift end or handover is attempted **Then** 422 `ENTRANTS_INSIDE`.
60. **Given** internal_temp_c 36.0 without heat controls **Then** Start/entry 422 `HEAT_CONTROLS_REQUIRED`.
61. **Given** a CSE permit already handed over once **When** a second handover is initiated **Then** 422 `HANDOVER_LIMIT`.

**Working at height**
62. **Given** Y10 **Then** lanyard 1.80 m with 4.00 m clearance → `FALL_CLEARANCE_INSUFFICIENT` (5.57 m); SRL 2.40 m → pass.
63. **Given** fall_protection `arrest_srl` without a rescue plan **Then** 422 `DOCUMENT_MISSING` and high_risk = true.
64. **Given** an outdoor facade WAH permit **When** revalidated with wind 11.2 m/s **Then** blocked; an Active one is Suspended `weather`.

**Excavation**
65. **Given** PTW-0408 depth 1.30 m **When** protective_system = none_lt_1_2m **Then** 422; sloping 1.00 on type_c **Then** 422; 1.50 **Then** accepted.
66. **Given** depth 6.20 m without engineered_design and pe_design document **Then** 422.
67. **Given** no utility_clearance_ref **Then** Approve blocked `UTILITY_CLEARANCE_MISSING`; mechanical method with services within 1.0 m **Then** 422 `MECHANICAL_NEAR_SERVICE`.
68. **Given** PTW-0408 revalidation at 23:00 without today's competent-person inspection **Then** 422 `INSPECTION_REQUIRED`.

**Electrical**
69. **Given** PTW-0405 **When** Issue is attempted without test_for_dead **Then** blocked `CHECKLIST_INCOMPLETE` (EL-02); **given** energized work on HV **Then** 422 `ENERGIZED_HV_PROHIBITED`; energized LV without HSE Manager approval **Then** 422 `EXEMPTION_REQUIRED`.

**Lifting**
70. **Given** Y7 **Then** capacity 87.0 % critical [capacity]; 57.7 % critical [airside_movement_area]; 22.4 % routine; 101.0 % `CAPACITY_EXCEEDED`; 91.0 % `EXEMPTION_REQUIRED`.
71. **Given** PTW-0290 (critical) with valid_to_at 2026-10-08 10:00 **Then** 422 `DURATION_EXCEEDS_LIMIT`.
72. **Given** PTW-0290 wind 13.4 m/s or PTW-0410 wind 11.0 m/s at Issue **Then** blocked `WIND_LIMIT_EXCEEDED`; an Active lift is Suspended `wind_limit`.
73. **Given** PTW-0290 without OBS-RBT-52-2026-0001 linked **Then** blocker `OBS_CLEARANCE_REQUIRED`; linked **Then** cleared and its conditions appear in the permit conditions.
74. **Given** VEH-0003 (32.00 m) on Z-APR-21 (max 12.00 m) **When** a lifting permit is dated 2026-10-11 (OBS-0004 valid to 10-10) **Then** `OBS_CLEARANCE_REQUIRED`.
75. **Given** a man-basket lift with wind 7.5 m/s **Then** `WIND_LIMIT_EXCEEDED`.

**Radiography**
76. **Given** Y9 **Then** computed_barrier_m 138.8 (no collimator) and 34.7 (t = 0.0625); planned 30.0 → `BARRIER_TOO_SMALL`; survey 8.1 µSv/h → `BARRIER_NOT_VERIFIED`; an NRRC licence expiring before valid_to → `LICENCE_INVALID`; revalidation of a radiography permit → 422 `REVALIDATION_NOT_ALLOWED`.

**Airside works**
77. **Given** PTW-0408 Suspended `shift_end` **When** Khalid revalidates at 23:00 on 2026-10-06 with WAP-0031 Active and NTM-0012 in effect **Then** Active with shift N+1; **when** a crew member not on WAP-0031 is in crew_present **Then** `WAP_CREW_MISSING`.
78. **Given** PTW-0408 Active (fixture night) **When** an LVP ops event on S-AIR suspends WAP-0031 **Then** within 60 s PTW-0408 is Suspended `ops_suspension`; ending the event and resuming WAP-0031 leave PTW-0408 Suspended until Khalid resumes it.
79. **Given** a window 22:00–05:00 on a permit linked to WAP-0031 (23:00–05:00) **Then** 422 `OUTSIDE_WAP_WINDOW`.
80. **Given** closure of PTW-0408 (movement area) without FOD check `clear` or ops_handback_ref **Then** 422 `FOD_HANDBACK_REQUIRED`.
81. **Given** a permit on Z-ILS33R linked to WAP-0035 (blocker NOTAM_NOT_ISSUED) **Then** the permit shows blocker `NOTAM_NOT_IN_EFFECT`.

**Midday ban, shifts, suspension, closure**
82. **Given** Y5 **Then** each outcome as stated (reject 06:00–18:00 on 2026-09-10; suspend at 12:00; resume 14:59 rejected; 15:00 allowed; 2026-09-16 accepted; 2026-06-15 in ban).
83. **Given** HSE Officer Noura grants a midday-ban exemption **Then** 403; Faisal with reason `emergency_repair` and heat controls **Then** the permit is not suspended at 12:00 and appears in the action panel.
84. **Given** Y6 **Then** planned_end_at 19:00 / 05:00 / 18:00 / 05:50 and the lapse outcomes as stated; revalidation of PTW-0408 at 22:40 → `OUTSIDE_WINDOW`.
85. **Given** a worker in crew_present not marked briefed **Then** Start 422 `CREW_NOT_BRIEFED`.
86. **Given** Contractor HSE Rep Ahmed stops work on PTW-0412 **Then** Suspended `stop_work`; Ahmed resuming → 403; Khalid resuming with cause-cleared text → Active.
87. **Given** a permit Active at valid_to_at **When** the job runs **Then** Expired, post-expiry check pending in the action panel, and K-69 counts it as not compliant.

**Audits**
88. **Given** Nasser audits PTW-0413 at 08:50 with A14 non-compliant (minor) **Then** score 90.9 %; with A10 also non-compliant (critical) **Then** 81.8 %, PTW-0413 Suspended `audit_critical`, and Complete without a critical CA → 422 `CA_REQUIRED` (Y14).
89. **Given** Noura (HSE reviewer of PTW-0413) audits it **Then** 422 `SOD_CONFLICT`.
90. **Given** an `unpermitted_work` audit on NAJD **Then** K-64 increases by 1, a critical CA with source_type `ptw_audit` is required and a stop-work record exists.

**KPIs, dashboard, AI**
91. **Given** the seed, Sep 2026 **Then** every value in the Y12 table matches for ANIA-EXP and RBT-52.
92. **Given** the warning job on 2026-10-02 **Then** E8 is raised for ANIA-EXP Sep 2026 only, E9 for RBT-52 Sep 2026 only, and neither for Jun–Aug.
93. **Given** the Phase 1 dashboard **Then** the K-46 tile shows 64 for ANIA-EXP Sep 2026 (no "Phase 3" placeholder) and K-61, K-64, K-66, K-69 tiles are present.
94. **Given** Y13 **Then** K-71 = 4.5 h (6 permits) and 5.0 h (7 permits).
95. **Given** Noura asks the AI "How many critical PTW findings did we have in September 2026?" **Then** the answer states 4 (6.25 per 100 field audits), cites T15, and the model input contains no names, worker_no or signatures (log assertion).
96. **Given** Viewer Sarah opens PTW KPIs and the live board **Then** values and counts are shown and no list contains names or worker_no.
97. **Given** expiring items within 30 days on 2026-10-06 **Then** Salem's appointment APT-ANIA-EXP-0011 (14 days) is listed and GD-RBT-001 (31 days) is not; on 2026-10-07 GD-RBT-001 (30 days) is listed.

**PDPL, i18n**
98. **Given** a gas tester's signature image **Then** it is served only by a signed URL ≤ 5 min to roles with capability 46 and never in exports.
99. **Given** a medical_fitness hook not_met for an entrant **When** receiver Faris views the permit **Then** he sees "Not eligible — HSE check" without kind/code; HSE Officer Noura sees the kind and code but no reason.
100. **Given** the UI in Arabic **Then** every Phase 3 status, reason code (SR), blocker (B), checklist item (C, X, A) and field label renders in Arabic (CI key check); grid coordinates, permit numbers and gas values render LTR.

## 10. Open questions for the HSE Manager

1. **Issuers:** client/PMC staff only (assumed, PR-5b, as Phase 0 §10 Q2 and WAP approvals), or may tier-1 contractor engineers issue permits to their subcontractors on your projects?
2. **Three distinct signatories:** receiver, area authority and issuer must be three different people (assumed). Practical on night airside shifts and on RBT-52, or may the issuer also act as area authority for low-risk permits?
3. **Hot-work duration:** 1 day maximum with one handover (assumed, Aramco-type). Would you accept up to 7 days with shift revalidation for hot work in non-hazardous building areas (e.g. RBT-52 fit-out)?
4. **Risk matrix and acceptance:** bands Low 1–4 / Medium 5–9 / High 10–14 / Extreme 15–25, acceptance receiver / issuer / issuer + HSE — or your client's matrix and authority levels?
5. **Gas limits and intervals:** LEL < 5 % for entry, < 1 % for hot work, H₂S < 1 ppm, CO < 25 ppm; re-test every 60 min (CSE, with continuous monitor) / 120 min (hot work, excavation); re-test after 30 min stop; detector calibration every 180 days. Do your client or the detector manufacturer require different values?
6. **Fire watch and Civil Defense:** 60 min after hot work (NFPA 51B 2019) — or does the client accept 30 min (SBC 801)? How does your site notify Civil Defense of fire-system impairments today?
7. **Critical lifts:** ≥ 75 % of chart capacity, ≥ 20 t, every lift on the apron/movement area, tandem, man-basket, near power lines. Does your client's lifting procedure use other thresholds (e.g. 80 % or 85 %)? Who signs critical lift plans — a named lifting engineer?
8. **Working at height:** permit from 1.8 m (assumed) or from any height / 1.2 m on your client's projects?
9. **Radiography:** barrier at 7.5 µSv/h (assumed until the NRRC value is confirmed). Will radiography be done by a separate licensed NDT subcontractor (it would need its own engagement), and is radiography allowed in the daytime on your sites?
10. **Airport operator:** does the operator issue its own permit for airside works (hot work near hydrants, AGL/ILS cable excavation) whose number must be on our permit, and who confirms stand closures and hydrant clearances?
11. **Midday ban exemptions:** may anyone other than you grant them, and which activities does your client treat as exempt?
12. **PTW audits:** target ≥ 5 field audits per week per project (assumed). Do Contractor HSE Reps' audits of their own permits count, or only client/PMC audits?
13. **Signatures:** is platform e-signature with re-authentication acceptable to the client and the airport operator, or must a wet-signed paper copy remain at the work site?
14. **Isolations on live airport systems:** for existing terminal/airfield systems, must isolations be done by the airport's own O&M staff (then they need user accounts and isolation-authority appointments)?
15. **Receiver workload:** maximum 3 live permits per receiver (assumed) — right for your contractors?

## 11. Changes required in earlier specs (applied 2026-10-07: `1-dashboard.md` v1.2, `2-access-permits.md` v1.1)

**`0-foundation.md` — no change required.** Rule 16 and the permit_issuer / permit_receiver roles are used as written; rule 28 ("later phases additionally block permits") is implemented by PT-6. The eight new users in Appendix A.2 are seed additions only.

**`1-dashboard.md` → v1.2** (no existing formula or worked example changes value):
1. §6.1 K-46: replace "placeholder — Available from Phase 3" with "PTW field audits — n(field audits completed in period), defined in `3-ptw.md` §6.11"; add row K-46b (coverage %, same reference). §1 "Out of scope": remove "PTW audits (Phase 3)".
2. §3.5 Investigation: add `ptw_ids` (FK[] to Phase 3 permits of the project; the UI suggests permits that were Issued, Active or Suspended in the incident's zone at occurred_at); `ptw_involved` becomes true when ptw_ids is non-empty (still settable manually); `ptw_ref` kept as legacy free text, read-only once ptw_ids is set. §8.2: "Phase 3 links PTW" now done via ptw_ids.
3. §3.8 CA `source_type` enum adds `ptw_audit` (source_id = PTW audit).
4. §5.9 AI: new tool **T15 `get_ptw_kpis`** (per `3-ptw.md` KP-5); T13 returns E8–E9; T9 adds dimension `ptw_audit_band`; T4/T5 add linked permit numbers and types (no names); AI-10 (5) adds "PTW audit band vs incident rate"; AI-19 section 6 lists K-46, K-46b, K-61, K-64, K-66, K-69 and E8–E9; monthly-report tables use T1–T15.
5. §6.9: add E8–E9 (defined in `3-ptw.md` §6.12), same job, scope and alert; §7 row "E1–E7" → "E1–E9".
6. §8.1: PTW tiles replace the K-46 placeholder tile; PTW band; charts C13–C15; expiring-items kinds of `3-ptw.md` §8.2; action-panel items of §8.3.

**`2-access-permits.md` → v1.1** (behaviour of existing Phase 2 rules unchanged):
1. HK-3: subject_type adds `equipment_tag` with subject {category, tag} for equipment not in the vehicle register (tower cranes, lifting accessories, MEWPs, scaffolds); Phase 2 stores no such record; Phase 4 providers map tags to the equipment register.
2. HK-6: (a) context `ptw` of E evaluates ZP-4 steps 1–6 and 8 (no WAP step 7); (b) `active_waps(zone_id, engagement_id, at)` returns wap_no, status, windows, blockers, crew {worker_id, crew_role, status, escort_worker_id} and vehicles; Phase 3 calls it for the engagement and each ancestor; (c) Phase 2 publishes internal domain events — `wap.status_changed`, `wap.crew_changed`, `wap.blockers_changed`, `ntm.status_changed`, `obs.status_changed`, `ops_event.started` / `ended`, `credential.status_changed`, `deployment.status_changed`, `worker.status_changed` — delivered at least once within 60 s. Phase 2 still never reads PTW data.
3. §3.20 QR kinds add `PT` (permit print); GC-10 applies to `PT` tokens as to `WP` (read-only permit summary, logs `ptw_view`, records no entry); AC64's pattern becomes `^HSE2:(AC|VS|WP|PT):[A-Za-z0-9_-]{22}$`.
4. HK-2 (documentation): attach points for permit types, PTW crew roles, equipment lines and appointments are stored by Phase 3 (`3-ptw.md` HK3-2).
5. Appendix A (seed): OBS-RBT-52-2026-0001 for tower crane TC-01 (Appendix A.10 below) — answers Phase 2 §10 Q8 provisionally; WAP-ANIA-EXP-2026-0033 names one of its six crew as Zaheer Abbas (crane operator); named Phase 3 workers are part of the A.1 bulk counts (K-48 unchanged).


## Appendix A — Seed data (fictional; `seed_fake = true` on every row; all names, IDs, numbers, licences and references are fake)

### A.1 Principles
- Seed clock: the Phase 2 seed "today" — **2026-10-06 10:00** (Asia/Riyadh). Statuses below are as at that time. Worked examples (§6.13) and acceptance criteria (§9) use these records.
- Identity numbers follow the Phase 2 fake pattern `^[12]0{5}\d{4}$` (1… = Saudi national ID, 2… = Iqama). Mobiles +9665000000nn; emails firstname.lastname@example.com.
- The new named workers (A.4) are **part of** the Phase 2 bulk worker counts (Phase 2 A.1); K-48 and every Phase 2 example keep their values.
- Bulk records (A.9) carry `seed_fake = true` and never use the reserved named references in A.2–A.8 (as DECISIONS #26).
- Every permit has a JSA instance `JSA-<permit_no tail>` (e.g. JSA-ANIA-EXP-2026-0413) in status Approved, with its lines filled from the matching template (JSA-T-<project>-nnnn); only the lines used in examples are listed.

### A.2 New users (Phase 0 seed additions; no Phase 0 rule changes)

| Name / الاسم | Email | Mobile | Org | Role · scope |
|---|---|---|---|---|
| Majed Al-Shammari / ماجد الشمري | majed.shammari@example.com | +966500000009 | pmc_consultant | permit_issuer · RBT-52 |
| Joseph Mathew / جوزيف ماثيو | joseph.mathew@example.com | +966500000010 | contractor QIMMA | permit_receiver · RBT-52 · QIMMA |
| Fahad Al-Mutairi / فهد المطيري | fahad.mutairi@example.com | +966500000011 | contractor RAWABI | site_engineer · ANIA-EXP · S-LAND |
| Ibrahim Al-Saleh / إبراهيم الصالح | ibrahim.saleh@example.com | +966500000012 | contractor QIMMA | site_engineer · RBT-52 · S-TWR, S-POD |
| Lina Haddad / لينا حداد | lina.haddad@example.com | +966500000013 | pmc_consultant | hse_officer · RBT-52 |
| Sanjay Verma / سانجاي فيرما | sanjay.verma@example.com | +966500000014 | contractor GULFPAVE | permit_receiver · ANIA-EXP · GULFPAVE |
| Faris Al-Anazi / فارس العنزي | faris.anazi@example.com | +966500000015 | contractor RAWABI | permit_receiver · ANIA-EXP · RAWABI |
| Nasser Al-Shahrani / ناصر الشهراني | nasser.shahrani@example.com | +966500000016 | contractor RAWABI | site_engineer · ANIA-EXP · S-LAND |

Existing users used: Faisal (HSE Manager), Noura (HSE Officer ANIA-EXP), Omar (site engineer S-AIR), Khalid (permit issuer ANIA-EXP), Ramesh (receiver NAJD), Ahmed (Contractor HSE Rep RAWABI), Yousef (Contractor HSE Rep QIMMA), Sarah (viewer).

### A.3 PTW appointments (all `active`, appointed by Faisal for issuers and by the HSE Officer otherwise; basis texts fake)

| No. | Holder | Function · discipline | Permit types | Sites / zones | Valid |
|---|---|---|---|---|---|
| APT-ANIA-EXP-0001 | Khalid | issuer | all nine | S-AIR, S-LAND | 2026-01-01 → 2026-12-31 |
| APT-ANIA-EXP-0002 | Omar | area_authority | all | S-AIR | 2026-01-01 → 2026-12-31 |
| APT-ANIA-EXP-0003 | Fahad | area_authority | all | S-LAND | 2026-02-01 → 2027-01-31 |
| APT-ANIA-EXP-0004 | Noura | area_authority (backup) | all | S-AIR, S-LAND | 2026-01-01 → 2026-12-31 |
| APT-ANIA-EXP-0005 | Nasser | isolation_authority · electrical_lv, electrical_hv | electrical, general | S-LAND | 2026-03-01 → 2027-02-28 |
| APT-ANIA-EXP-0006 | Nasser | authorised_person · electrical_lv | electrical | S-LAND | 2026-03-01 → 2027-02-28 |
| APT-ANIA-EXP-0007 | Saad (WKR-000007) | authorised_person · lifting_appointed_person | lifting | S-AIR, S-LAND | 2026-01-15 → 2027-01-14 |
| APT-ANIA-EXP-0008 | Mahmoud (WKR-000005) | authorised_person · lift_supervisor | lifting | S-AIR | 2026-01-15 → 2027-01-14 |
| APT-ANIA-EXP-0009 | Tariq (WKR-000013) | authorised_person · excavation_competent_person | excavation | S-AIR | 2026-02-10 → 2027-02-09 |
| APT-ANIA-EXP-0010 | Vinod (WKR-000020) | authorised_person · radiation_protection_officer | radiography | S-LAND | 2026-04-01 → 2027-03-31 |
| APT-ANIA-EXP-0011 | Salem (WKR-000018) | gas_tester | confined_space, hot_work, excavation, general | S-AIR, S-LAND | 2026-04-21 → **2026-10-20** (Y11) |
| APT-ANIA-EXP-0012 | Rafiq (WKR-000021) | authorised_person · cse_rescue_lead | confined_space | S-LAND | 2026-05-01 → 2027-04-30 |
| APT-RBT-52-0001 | Majed | issuer | all except confined_space, radiography (AC3) | S-TWR, S-POD | 2026-01-01 → 2026-12-31 |
| APT-RBT-52-0002 | Ibrahim | area_authority | all | S-TWR, S-POD | 2026-01-01 → 2026-12-31 |
| APT-RBT-52-0003 | Ibrahim | authorised_person · lifting_appointed_person | lifting | S-TWR, S-POD | 2026-01-01 → 2026-12-31 |
| APT-RBT-52-0004 | Hamza (WKR-000105) | authorised_person · lift_supervisor | lifting | S-TWR | 2026-03-01 → 2027-02-28 |
| APT-RBT-52-0005 | Hamza (WKR-000105) | authorised_person · fall_protection_competent_person | work_at_height | S-TWR | 2026-03-01 → 2027-02-28 |
| APT-RBT-52-0006 | Ibrahim | isolation_authority · electrical_lv | electrical | S-TWR, S-POD | 2026-01-01 → 2026-12-31 |
| APT-RBT-52-0007 | Ibrahim | authorised_person · electrical_lv | electrical | S-TWR, S-POD | 2026-01-01 → 2026-12-31 |

Note: on PTW-RBT-52-2026-0279 Ibrahim was area authority and applied ISO-RBT-52-2026-0033 as isolation authority; Joseph (receiver) verified it, so IS-4 and PR-5 are respected.

### A.4 New named workers (Phase 2 worker register additions)

| worker_no | Name / الاسم | Nat. | ID (type) · expiry | Project · contractor · role · site | Inductions | Phase 3 use |
|---|---|---|---|---|---|---|
| WKR-000014 | Prakash Thapa / براكاش ثابا | NP | 2000001014 (iqama) · 2027-06-30 | ANIA-EXP · NAJD · welder · S-LAND | GEN valid | hot_work_operative 0412 |
| WKR-000015 | Ahmed Raza / أحمد رضا | PK | 2000001015 (iqama) · 2027-04-15 | ANIA-EXP · NAJD · fire_watch · S-LAND | GEN valid | fire watch 0412 (AC6) |
| WKR-000016 | Kamal Hossain / كمال حسين | BD | 2000001016 (iqama) · 2027-09-09 | ANIA-EXP · RAWABI · labourer · S-LAND | GEN valid | entrant 0413 |
| WKR-000017 | Biju Thomas / بيجو توماس | IN | 2000001017 (iqama) · 2027-11-02 | ANIA-EXP · RAWABI · labourer · S-LAND | GEN valid | standby person 0413 (AC7) |
| WKR-000018 | Salem Al-Harthi / سالم الحارثي | SA | 1000001018 (national_id) · 2031-05-12 | ANIA-EXP · RAWABI · hse_staff · S-AIR, S-LAND | GEN, AIR valid | gas tester (APT-0011) |
| WKR-000019 | Zaheer Abbas / ظهير عباس | PK | 2000001019 (iqama) · 2027-08-20 | ANIA-EXP · RAWABI · crane_operator · S-AIR | GEN, AIR valid; PERM pass [A] | crane operator 0410; crew on WAP-0033 |
| WKR-000020 | Vinod Menon / فينود مينون | IN | 2000001020 (iqama) · 2027-12-01 | ANIA-EXP · NAJD · ndt_technician · S-LAND | GEN valid | radiographer + RPO 0399 |
| WKR-000021 | Rafiq Islam / رفيق إسلام | BD | 2000001021 (iqama) · 2027-10-18 | ANIA-EXP · RAWABI · supervisor · S-LAND | GEN valid | supervisor + rescue lead 0413 |
| WKR-000106 | Dinesh Kumar / دينيش كومار | IN | 2000001106 (iqama) · 2027-07-07 | RBT-52 · QIMMA · welder · S-TWR | GEN valid | hot_work_operative 0288 |
| WKR-000107 | Rohan Fernando / روهان فرناندو | LK | 2000001107 (iqama) · 2027-05-25 | RBT-52 · QIMMA · fire_watch · S-TWR | GEN valid | fire watch 0288 |
| WKR-000108 | Joel Bautista / جويل باوتيستا | PH | 2000001108 (iqama) · 2028-02-14 | RBT-52 · QIMMA · rigger · S-TWR | GEN, TC valid | rigger/signaller 0290 |

Salem's worker record is linked to no user (he records tests on the receiver's device as a worker signatory; DECISIONS #43 re-authentication applies to the receiver). Phase 2 role codes not in the Phase 2 list (`welder`, `fire_watch`, `ndt_technician`, `hse_staff`) are seeded as reference-list additions on each project ASSUMPTION.

### A.5 Zone PTW profiles and adjacency

| Zone | permit_required_all_work | gas_test_zone | hazardous class (note) | default_exposure | fire protection | Default area authority |
|---|---|---|---|---|---|---|
| Z-APR-21 | true | true | zone_2 (within 3 m of hydrant pit valve chambers) | outdoor_direct_sun | false | Omar |
| Z-TWB | true | false | none | outdoor_direct_sun | false | Omar |
| Z-ILS33R | true | false | none | outdoor_direct_sun | false | Omar |
| Z-PIERB | false | false | none | outdoor_shaded | false | Fahad |
| Z-MSCP | false | true (manholes, sewer) | none | outdoor_shaded | false | Fahad |
| Z-LAY1 | false | false | none | outdoor_direct_sun | false | Fahad |
| Z-CORE | false | false | none (level datum: site ±0.00 = FFL ground; elevation_m from it) | indoor | false | Ibrahim |
| Z-TC01 | true | false | none | outdoor_direct_sun | false | Ibrahim |
| Z-B4 | false | true (dewatering sumps) | none | indoor | false | Ibrahim |
| Z-FAC | true | false | none | outdoor_direct_sun | false | Ibrahim |

Adjacency: Z-PIERB–Z-MSCP 40.0 m none · Z-PIERB–Z-LAY1 120.0 m none · Z-APR-21–Z-TWB 60.0 m none · Z-TWB–Z-ILS33R 150.0 m none · Z-CORE–Z-TC01 0.0 m overlapping · Z-CORE–Z-FAC 0.0 m none · Z-CORE–Z-B4 0.0 m a_above_b.

Site grid (for SIMOPS distances): ANIA-EXP S-LAND and S-AIR use one airport construction grid (metres, origin VERIFY with the PMC surveyor); RBT-52 uses the tower grid with origin at the core's south-west corner.

### A.6 Gas detectors, bump tests and locks

| Detector | Owner | Sensors | Calibrated | Status |
|---|---|---|---|---|
| GD-ANIA-003 | RAWABI | O₂, LEL, H₂S, CO | 2026-07-02 (due 2026-12-29) | in_service; bump test 2026-10-06 07:30 pass (gas lot TEST-LOT-2611, expiry 2027-05-31) |
| GD-ANIA-005 | GULFPAVE | O₂, LEL, H₂S, CO | 2026-03-30 (due 2026-09-26) | **quarantined** 2026-09-27 00:05 (calibration overdue) |
| GD-RBT-001 | QIMMA | O₂, LEL, H₂S, CO | 2026-05-10 (due 2026-11-06) | in_service; 30-day alert 2026-10-07 |

Locks (ANIA-EXP): isolation locks L-ANIA-0231, L-ANIA-0232 (applied, ISO-0061); lockbox LB-ANIA-012 (holds the keys of L-0231/0232); personal locks P-ANIA-1101, P-ANIA-1102, P-ANIA-1103 (applied on LB-ANIA-012 by the three 0405 electricians, 2026-10-06 07:02); L-ANIA-0233…0240 and P-ANIA-1104…1120 available. RBT-52: L-RBT-0101…0110, P-RBT-0201…0215 available; L-RBT-0104 used on ISO-RBT-52-2026-0033 and returned to available on de-isolation.

### A.7 Named permits

| Permit · type | Zone · grid (x, y) · elev | Contractor · receiver · area authority · issuer · HSE review | Crew (named + bulk) | Validity / windows | Links | Status at seed clock |
|---|---|---|---|---|---|---|
| **PTW-ANIA-EXP-2026-0412 · HW** (welding of steel connections) | Z-PIERB · (120.0, 45.0) · 12.00 | NAJD · Ramesh · Fahad · Khalid · not required (not gas_test_zone, not hazardous, no impairment, landside) | Prakash (hot_work_operative), Ahmed Raza (fire watch), 1 bulk NAJD helper | 2026-10-06 07:00–19:00 | JSA residual Medium | **Active** since 07:10 (shift 1, planned_end_at 19:00) |
| **PTW-ANIA-EXP-2026-0413 · CS** (manhole MH-07 inspection and pipe repair) | Z-MSCP · (180.0, 60.0) · −3.20 | RAWABI · Faris · Fahad · Khalid · Noura | Rafiq (supervisor, rescue lead), Biju (standby), Kamal + 1 bulk (entrants), Salem (gas tester) | 2026-10-06 07:00–19:00 | Rescue plan RP-MSCP-02 rev B (retrieval tripod, response ≤ 4 min); detector GD-ANIA-003 | **Active** since 07:55 (issued 07:50); tests 07:40 pre-entry (3 points), 08:38 periodic, 09:48 post-break; pause 09:15–09:50; next due 10:48; entry log shows 2 inside (Kamal and the bulk entrant, since 09:52) |
| **PTW-ANIA-EXP-2026-0405 · EL** (MCC-3 cable termination) | Z-PIERB plant room · (95.0, 20.0) · 0.00 | RAWABI · Faris · Fahad · Khalid · not required | 3 bulk RAWABI electricians (authorised person Nasser on call) | 2026-10-05 07:00 → 2026-10-11 19:00; windows 07:00–17:00 daily | **ISO-ANIA-EXP-2026-0061** (Verified): point 1 Q12 breaker racked out, L-ANIA-0231, tag DT-0231, applied by Nasser 2026-10-05 07:40; point 2 MCC-3 incomer isolator open and locked, L-ANIA-0232, tag DT-0232, applied 07:50; both verified by Faris (test for dead, live-dead-live, proved instrument) 08:20; keys in LB-ANIA-012 | **Active** (shift of 2026-10-06 started 07:05; personal locks P-ANIA-1101…1103 applied 07:02) |
| **PTW-ANIA-EXP-2026-0408 · EX + AW** (AGL cable duct, hand dig) | Z-TWB · (410.0, 95.0) · 0.00 | GULFPAVE · Sanjay · Omar · Khalid · Noura | Tariq (supervisor, escort, excavation competent person), Rajesh (plant operator, standby), Abdul Karim (labourer, escorted by Tariq) + 3 bulk | 2026-10-04 23:00 → 2026-10-10 05:00; windows 23:00–05:00 | WAP-ANIA-EXP-2026-0031, NTM-ANIA-EXP-2026-0012; utility clearance AOP-UTIL-TEST-0419; depth 1.30 m, sloping 1.50 : 1 (34°), soil type C | **Suspended** (`shift_end`, routine) since 2026-10-06 04:52; revalidation allowed from 23:00 (Y6) |
| **PTW-ANIA-EXP-2026-0410 · LF (critical) + AW** (AGL transformer set-down) | Z-APR-21 stand 22 · (520.0, 140.0) · 0.00 | RAWABI · Faris · Omar · Khalid · Noura | Mahmoud (lift supervisor), Zaheer (crane operator), 2 bulk RAWABI riggers | 2026-10-06 13:00–16:00 | VEH-0003 (50 t mobile crane), OBS-ANIA-EXP-2026-0004, WAP-ANIA-EXP-2026-0033; critical lift plan CLP-ANIA-0007 rev A by Saad (APT-0007); load 6.800 t + rigging 0.350 t, capacity 12.400 t (Y7b) | **Approved** 09:30; issue expected 13:00 (AC17); midday ban not in force (October) |
| **PTW-ANIA-EXP-2026-0399 · RG** (pipe-weld radiography) | Z-LAY1 · (300.0, 200.0) · 0.00 | NAJD · Ramesh · Fahad · Khalid · Noura | Vinod (radiographer, RPO) + 1 bulk NAJD assistant radiographer | 2026-10-04 22:00 → 2026-10-05 05:00 | Licence NRRC-TEST-RL-0042 valid to 2027-03-31; Ir-192 1,110.0 GBq with collimator; computed 34.7 m, planned barrier 40.0 m; survey 5.8 µSv/h | **Closed** 2026-10-05 05:10; source returned 04:40, survey 0.2 µSv/h |
| **PTW-RBT-52-2026-0287 · WH** (slab-edge formwork L38) | Z-CORE L38 · (40.0, 18.0) · 152.00 | QIMMA · Joseph · Ibrahim · Majed · Lina | Hamza (supervisor, fall-protection competent person), Imtiaz + 3 bulk | 2026-10-05 06:00 → 2026-10-09 17:00; windows 06:00–17:00 | Rescue plan RP-RBT-L38 rev C; SRL clearance 2.40 m ≤ available 4.00 m (Y10); JSA per Y1 | **Active** (shift of 2026-10-06 started 06:05) |
| **PTW-RBT-52-2026-0288 · HW** (embed plate welding L37) | Z-CORE L37 · (42.0, 20.0) · 148.00 | QIMMA · Joseph · Ibrahim · Majed · not required (indoor, not gas_test_zone) | Dinesh (hot_work_operative), Rohan (fire watch) | 2026-10-06 07:00–16:00 | SIM-RBT-52-2026-0019 (vs 0287, SM-R06, 2.8 m) coordinated 06:50 by Majed and Ibrahim: debris netting at L38 edge, no work above the welding bay 07:00–16:00 except behind netting | **Active** since 07:05 |
| **PTW-RBT-52-2026-0290 · LF (critical)** (curtain-wall unit lift) | Z-TC01 + Z-CORE · appliance (60.0, 30.0) slew 60.0 m; landing (45.0, 22.0) exclusion 5.0 m | QIMMA · Joseph · Ibrahim · Majed · Lina | Hamza (lift supervisor), Ali Hassan (crane operator), Joel (rigger/signaller) | 2026-10-07 06:30–10:00 | Equipment: tower crane tag TC-01 (equipment_tag, height 236.00 m AGL), spreader beam SB-RBT-04; OBS-RBT-52-2026-0001 (A.10); CLP-RBT-0012 rev B by Ibrahim (APT-RBT-52-0003); 4.200 t + 0.150 t at 42.00 m radius, capacity 5.000 t (Y7a); wind limit 13.0 m/s | **Approved** 2026-10-06 09:00; Issue blocked `SIMOPS_COORDINATION_REQUIRED` (SIM-RBT-52-2026-0021 vs 0287, SM-R05b, 23.3 m, Open) |
| **PTW-RBT-52-2026-0279 · EL** (DB-L30-01 replacement) | Z-CORE L30 · (30.0, 12.0) · 120.00 | QIMMA · Joseph · Ibrahim · Majed · not required | Ramon Cruz (electrician) + 1 bulk | 2026-09-29 07:00 → 2026-10-02 17:00 | ISO-RBT-52-2026-0033 (DB-L30-01 incomer, L-RBT-0104), de-isolated 2026-10-02 16:40 | **Closed** 2026-10-02 16:30 |

Note on 0413: with 2 entrants inside at the seed clock, AC59 (closure / shift end / handover → `ENTRANTS_INSIDE`) runs directly on the seed.

### A.8 Named audits

| Audit | Permit | Auditor | Type · time | Result |
|---|---|---|---|---|
| AUD-ANIA-EXP-2026-0187 | PTW-0413 | Nasser (not issuer, receiver, area authority or HSE reviewer of 0413 — AU-2) | field · 2026-10-06 08:50 | 11 applicable items, A14 minor non-compliant (rescue tripod winch inspection tag illegible) → **90.9 %** (Y14); CA CA-ANIA-EXP-2026-0311 (source `ptw_audit`, minor, due 2026-10-09) |
| AUD-ANIA-EXP-2026-0188 | PTW-0412 | Noura | field · 2026-10-06 09:20 | 11 / 11 → **100.0 %** |

### A.9 Bulk volumes (seed_fake)
- Permits, shifts, gas tests, suspensions, SIMOPS conflicts, isolations and audits for **June–September 2026** are generated so that every figure of Y12 and its June–August history is reproduced exactly (counts by type, permit-shifts, field audits and item results, critical findings, suspensions by reason, gas-test compliance, closures/expiries, shift lapses, isolations open at 09-30).
- Bulk permit numbers: ANIA-EXP 2026-0001…0398 and RBT-52 2026-0001…0278 (named permits take the numbers above); bulk audits AUD-…-0001…0186; bulk crew are drawn from Phase 2 bulk workers of the same engagement only.
- No bulk permit is Issued, Active or Suspended at the seed clock (so live-state examples are deterministic); bulk isolations open at 09-30 (ANIA-EXP 7, RBT-52 2) are de-isolated on 2026-10-01 except ISO-0061, which is new.
- JSA templates: ANIA-EXP JSA-T-ANIA-EXP-0001…0014 and RBT-52 JSA-T-RBT-52-0001…0009, all Approved, review due ≥ 2027-01-01; one RBT-52 template (JSA-T-RBT-52-0009) in Review Due for JS-9 tests.

### A.10 Phase 2 seed addition — obstacle clearance for TC-01
OBS-RBT-52-2026-0001: equipment tower crane TC-01 (QIMMA); ground elevation 618.00 m AMSL + 236.00 m height = **854.00 m AMSL**; reason `height_threshold`; authority reference GACA-OBS-TEST-0101; status Approved with conditions [`obstruction_light`, `day_marking`]; valid 2026-01-20 → 2027-06-30. Recorded in Phase 2 (§11 Phase 2 item 5); Phase 3 only links it on 0290.

## Change log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-10-07 | HSE Consultant Agent | First issue: Phase 3 Permit to Work — permit types and lifecycle, appointments and segregation of duties, JSA (5×5), gas testing, isolation/LOTO, SIMOPS, type rules, heat/midday ban, shifts/handover/suspension/closure, PTW audits, KPIs K-46, K-46b, K-61…K-71, warnings E8–E9, AI tool T15, permission matrix rows 82–104, seed data; changes to Phase 1 (→ v1.2) and Phase 2 (→ v1.1) listed in §11. |
| 1.1 | 2026-10-08 | HSE Consultant Agent | Changes required by Phase 4 (`4-third-party-cert.md` v1.0 §11.4); no existing rule, formula or worked example changes value on the Phase 3 seed: (1) §3.6 equipment line `equipment_item_id` and `operator_worker_id`; (2) HK3-1 passes HK-3 context; (3) HK3-2 Phase 4 default hooks (BANKSMAN, RESCUE-WINCH-TPI, HOIST-TPI, operator codes); (4) LF-4 transition-stage wording, hard stops, conditions/SWL; (5) scaffold_tag_ref resolved against the Phase 4 scaffold register; (6) §3.9 detector `calibration_body_id`, §4.6 quarantine on calibration-lab blacklist; (7) HK3-5 Phase 4 events; (8) AC17/AC18 notes for the Phase 4 seed. |
| 1.2 | 2026-10-08 | HSE Consultant Agent | Changes required by Phase 5 (`5-training.md` v1.0 §11.4); AC17/AC18 and every worked example unchanged on the Phase 3 seed (no training provider registered there): (1) HK3-2 WAH for every crew member on a work-at-height section; rescue_lead also FIRST-AID; (2) HK3-2 appointment hooks through the holder's linked worker, `HOLDER_NOT_LINKED`; (3) HK3-5 subscribes to the Phase 5 events and suspends live permits on training hard stops and on not_met after the block date. |
| 1.3 | 2026-10-09 | HSE Consultant Agent | Changes required by Phase 6b (`6b-heat-stress.md` v1.0 §11.4); all items apply only on projects with `heat_ptw_enforcement_from` ≤ today, so every Phase 3 AC and worked example is unchanged on the Phase 3 seed: (1) §3.2 permit `heat_workload` (list WL; required for outdoor exposure; type defaults hot_work moderate, confined_space heavy, work_at_height moderate, excavation heavy, electrical_isolation light, lifting moderate, radiography light, airside_works heavy, general moderate; heaviest wins) and `heat_clothing` (list CL, default work_clothes; `hood`); (2) §3.13 shift `wbgt_reading_id` and the regime with rest minutes per hour; (3) pause reason `heat_rest` (SH-9 unchanged); (4) list SR `heat_stress_stop` (routine, excluded from K-65); (5) list B / PT-16 blockers `HEAT_STOP`, `WBGT_READING_REQUIRED` at Start, Revalidate, Resume and handover acceptance; SH-2 automatic suspension `heat_stress_stop` within 60 s of `heat.regime_changed`; SH-3 resume after `heat_stress_stop` by the receiver without issuer cause text (6b PH-3); (6) crew-eligibility step "heat": `HEAT_RESTRICTION` / `KEY_ROLE_INELIGIBLE`, `HEAT_STOP_FOR_WORKER`, `WORKER_ACCLIMATISING`; (7) HT-5 wording; (8) §8.3 action-panel item "outdoor work during midday ban on a permit" (6b MB-4). 6b §11 numbers this document as if the 6a §11 changes were applied first; those 6a changes are implemented in the backend but not yet written into this document. |
| 1.4 | 2026-10-09 | HSE Consultant Agent | Changes required by Phase 6c (`6c-emergency-drills.md` v1.0 §11.4); items 3–5 apply only on projects with `emergency_ptw_enforcement_from` ≤ today (item 4 from `emergency_register_from`), so every Phase 3 AC and worked example is unchanged on the Phase 3 seed: (1) list SR adds `emergency_drill` (routine, excluded from K-65, shown with routine suspensions, SH-8); (2) SH-2 automatic `emergency` suspension within 60 s of a 6c event for evacuated zones (PE-1) and `emergency_drill` at drill Start (PE-2); SH-3 resume after `emergency_drill` by the receiver, no issuer cause text, GT-4 where gas testing applies; (3) list B / PT-16 blockers `RESCUE_TEAM_NOT_REGISTERED`, `RESCUE_DRILL_OVERDUE` for confined_space at Start, Revalidate, Resume and handover acceptance (PE-3); warnings `HEIGHT_RESCUE_NOT_READY` (PE-4), `NO_READY_EXTINGUISHER` (PE-5); (4) §3.2 emergency_info pre-filled at Request from 6c (PE-6), still editable and required; (5) §8.3 action panel: Active CSE permits whose rescue team is not current. |
