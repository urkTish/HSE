# Module Spec — Phase 4: Third-Party Certification (equipment, personnel, TPIs)

**Version:** v1.0 · **Date:** 2026-10-08 · **Author:** HSE Consultant Agent · **Status:** Draft for HSE Manager review
**Builds on:** `0-foundation.md` v1.0 (projects/sites/zones, contractors & engagement tree, rule 27 blacklisting, rule 28 "later phases additionally block permits", rule 45 Arabic search normalisation, matrix rows 1–19, PDPL P1–P13) · `1-dashboard.md` v1.3 (matrix rows 20–45, KPI catalogue K-01…K-47, rounding K-R8, CA entity, incidents, warnings E1–E9, expiring-items endpoint, action panel, AI tools T1–T15, import-batch pattern §3.2) · `2-access-permits.md` v1.2 (worker register, deployments, ID encryption/blind index/masking WK-4/WK-5, vehicle register §3.12, AVP effective validity X3, obstacle clearances, QR tokens §3.20, gate check GC-x, **hook interface HK-1…HK-8 with `warn` policy**, matrix rows 46–81, KPIs K-48…K-60, alert schedules, P2-x) · `3-ptw.md` v1.1 (crew roles CR, equipment lines with `equipment_tag`, gas detector register §3.9, appointments §3.4, **HK3-1…HK3-5 incl. LF-4 "a permit cannot use an expired operator or uncertified crane"**, blockers list B, matrix rows 82–104, KPIs K-61…K-71, warnings E8–E9) · `docs/DECISIONS.md` #1–#62.
**Covers (build order):** 4.1 TPI organisations, accreditations, client approvals · 4.2 Equipment register & project deployment (links to Phase 2 vehicles and Phase 3 gas detectors) · 4.3 Equipment inspection certificates, configuration events, stickers · 4.4 Scaffold register & tagging · 4.5 Personnel certifications · 4.6 Verification (QR / sticker check, manual verification with the TPI) · 4.7 Defects → out-of-service → return to service · 4.8 Suspension & blacklisting (equipment, persons, TPIs) · 4.9 Hook providers and the warn → block transition · 4.10 Gate equipment check · 4.11 Certificate imports (CSV/Excel, dry-run) · 4.12 KPIs, alerts, dashboard and AI feeds.
**Not in Phase 4:** training courses, training matrix, refreshers (Phase 5 — boundary in §5.1); induction (Phase 2); gas-detector calibration and bump tests (stay in Phase 3, §5.2 EQ-3); vehicle road documents, AVP and ADP (Phase 2); medical fitness (Phase 6).

Conventions: `VERIFY` = clause/number to confirm against the current official text or the client's procedure. `ASSUMPTION` = Consultant default; HSE Manager may override (§10). "Must" = enforced server-side. Rule prefixes: BD boundary, TP TPI, EQ equipment register, EM mobilisation, EC equipment certificate, CF configuration change, SF scaffold, PC personnel certificate, VF verification, DF defect, BL suspension/blacklisting, HK4 hooks, GE gate equipment, CK certification check, IM import, KC KPIs/AI, P4- PDPL. Error codes are stable strings (Phase 0 rule 48). Times are local Asia/Riyadh unless marked UTC.

**Important boundary:** the platform records what an accredited third party certified, checks that the record is genuine, current and within scope, and stops the use of equipment and people that are not. It does not inspect equipment or assess people, and it never extends a TPI's validity. A TPI certificate is a minimum: the daily pre-use check by the operator and the PTW pre-issue checks (Phase 3 LF-03, WH-01) still apply.

---

## 1. Purpose

On a KSA mega-project the cranes, MEWPs, forklifts, hoists, slings and scaffolds that kill people when they fail are certified by third parties on paper: a sticker on the boom, a PDF in an email, an operator card in a wallet. Certificates lapse unnoticed, a crane is climbed and used before it is re-examined, a sling that failed an inspection stays in the rigging loft, a forged operator card from an unknown "inspection company" passes the gate, and the HSE Manager cannot answer "how many cranes on site have a valid certificate today?". Phase 4 gives one register of certifiable equipment and of personnel certifications, records each certificate with its TPI, scope, SWL, conditions and defects, verifies it with the issuing TPI, tracks expiry with 30/14/7/0-day alerts, tags out defective equipment until it is repaired and re-certified, blacklists equipment, persons and TPIs that cannot be trusted, and — through the hook interface that Phases 2 and 3 already call in `warn` mode — makes gates, work-area permits and permits to work refuse an expired operator, an uncertified crane, an out-of-service MEWP or an untagged scaffold. It feeds certification KPIs (K-72…K-81), warnings E10–E11 and the AI layer.

## 2. Regulatory basis

| # | Source | What it drives here |
|---|---|---|
| R1 | **ASME B30.5** (mobile and locomotive cranes — frequent and periodic inspection, periodic ≤ 12 months, after repair/alteration, rated load test), **B30.3** (tower cranes — inspection after erection, after each climbing/jacking or configuration change, load test), **B30.9** (slings — periodic ≤ 12 months, removal criteria), **B30.10** (hooks), **B30.20** (below-the-hook devices, spreader beams), **B30.26** (rigging hardware), **B30.23** (personnel lifting) `VERIFY` edition and paragraph numbers | Equipment categories, inspection types, configuration-change rule CF-1, accessory removal (DF-7), personnel-lifting limitation |
| R2 | **OSHA 29 CFR 1926.1412** (crane inspections: annual comprehensive, after modification/repair), **1926.1427** (operator qualification/certification by an accredited testing organisation; certification by type and capacity), **1926.1428** (signal person qualification), **1926.251** (rigging equipment), **1926.451/.454** (scaffolds: competent-person inspection before each shift and after any occurrence; trained erectors), **1926.453** (aerial lifts), **1910.178(l)** (powered industrial truck operator evaluation ≥ every 3 years) | Operator scope by type and capacity (PC-7), signaller, scaffold inspection triggers (SF-5), forklift operator cap |
| R3 | **UK LOLER 1998 reg. 9** (thorough examination: lifting accessories and equipment for lifting persons ≤ 6 months, other lifting equipment ≤ 12 months, after installation and after exceptional circumstances; reg. 10 defect reporting — "existing or imminent danger" vs "will become dangerous") — used as the "LOLER-equivalent" benchmark named in the consultant brief | Interval defaults (6 / 12 months), defect categories A/B (DF-1), accessory and man-basket intervals — strictest-wins over ASME's 12 months |
| R4 | **ANSI/SAIA A92.22 / A92.24** and **ISO 18878** (MEWP inspection ≤ 13 months; operator training by MEWP group/type 1a–3b) `VERIFY` | MEWP operator scope; 6-month MEWP interval wins (R3, carries persons) |
| R5 | **ITSDF B56.1 / B56.6** (forklifts, rough-terrain/telehandlers) `VERIFY` | Forklift and telehandler categories, capacity at load centre |
| R6 | **BS EN 12811-1** (scaffold load classes 1–6), **NASC TG20** (design triggers, inspection ≤ 7 days and after alteration/adverse weather), **BS EN 12810**; OSHA 1926.451(f)(3) | Scaffold register, design trigger, 7-day tag, re-inspection triggers |
| R7 | **ASME BPVC Sec. VIII** / **API 510** (pressure vessel in-service inspection); **UK PSSR 2000** (written scheme of examination) as benchmark `VERIFY`; Saudi Civil Defense / SASO requirements for pressure equipment on construction sites `VERIFY` | Pressure-vessel category (air receivers, accumulators), 12-month default, relief-valve fields |
| R8 | **ISO/IEC 17020** (inspection bodies), **ISO/IEC 17024** (personnel certification bodies), **ISO/IEC 17025** (calibration labs); **ILAC MRA**; **Saudi Accreditation Center (SAC)** `VERIFY` current name and register URL | TPI kinds, accreditation scope check at issue date (TP-4), independence (TP-6) |
| R9 | **ISO 9712** / ASNT SNT-TC-1A (NDT personnel, RT level II for radiographers); **IRATA / SPRAT**-type rope-access schemes (3-year validity); **CISRS**-type scaffolder/scaffold-inspector schemes — referenced as scheme *types*, not brands | Personnel certificate types, levels and default validity caps |
| R10 | **Saudi Aramco GI 7.030** (inspection and testing of elevating/lifting equipment), Aramco heavy-equipment operator/rigger certification and approved-TPI requirements, **CSM** chapters on cranes, rigging and scaffolds `VERIFY` GI numbers, editions, intervals and whether the client flows them down | Client-approved TPI list (TP-5), colour coding of lifting gear (EC-12), stricter client intervals |
| R11 | **MHRSD** OSH regulations — employer duty to keep work equipment safe and periodically examined by qualified/accredited bodies, and to use only qualified operators `VERIFY` article numbers | Legal basis for blocking uncertified equipment and operators |
| R12 | **ISO 45001:2018** cl. 7.2 (competence, documented evidence), 8.1.4 (contractors), 9.1 (monitoring); **BS 7121-1** (appointed person, thorough examination before use) | Competence evidence, contractor control, KPIs |
| R13 | **PDPL** + Implementing Regulations (Phase 0 R1/R2); KSA **anti-forgery provisions** for forged documents `VERIFY` (the platform records facts only; reporting to authorities is a legal decision outside the platform) | Personnel card scans with ID/photo, blind-index ID match, suspected-forgery data, certification bans (§5.13) |

Strictest-wins applied in this spec (and why):
- **Intervals:** where ASME (≤ 12 months) and LOLER (≤ 6 months for accessories and for equipment lifting persons) differ, the shorter wins: lifting accessories, MEWPs, man-baskets, construction hoists, mast climbers, BMUs and rescue tripods/winches 6 months; cranes, forklifts, telehandlers, plant and pressure vessels 12 months. A client value shorter than these is entered in settings; settings only shorten (§3.17).
- **Effective validity** = the earlier of the TPI's printed date and the platform interval (§6.1). A 12-month sticker on a MEWP is valid for 6 months here.
- **Personnel certificates** with no printed expiry, or a printed validity longer than the platform cap for the type, are capped (§6.2).
- **Tower cranes** must be re-examined after every erection, climb/jacking, jib or tie-in change (ASME B30.3) — the old certificate stops on the configuration event even if its date is still valid (CF-1).
- **Positive knowledge of danger blocks immediately**, whatever the hook policy: an out-of-service, blacklisted or configuration-changed item, a revoked or forged certificate, a banned holder (HK4-3). The `warn` transition only tolerates *missing or not-yet-uploaded* data.
- **Accessories with a category A defect are destroyed or returned to the manufacturer**, never repaired on site (DF-7, ASME B30.9 removal criteria).
- **Verification**: a certificate counts only after it is confirmed with the issuing TPI (VF-1); document sighting alone is not enough.

## 3. Entities & fields

PDPL column: **none / personal / sensitive** (Phase 0 P1–P2). Every entity carries Phase 0 system fields (id UUID, created_at/by, updated_at/by), is audited (Phase 0 rule 35) and stores `seed_fake` (bool). AR label shown in UI.

### 3.1 TPI organisation (org-wide) — جهة الفحص والاعتماد (طرف ثالث)

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| tpi_code | رمز الجهة | string(12) | Y | `^[A-Z0-9-]{2,12}$`, unique org-wide, immutable | AICC | none |
| legal_name_en / legal_name_ar | الاسم القانوني | string(200) ×2 | Y / Y | unique (Phase 0 rule 45 normalisation); name_ar Arabic script | Arabian Inspection & Certification Co. (fictional) / الشركة العربية للتفتيش وإصدار الشهادات | none |
| kinds | نوع الجهة | enum[] | Y | ≥ 1 of `inspection_body` جهة تفتيش (ISO/IEC 17020), `personnel_certification_body` جهة اعتماد أفراد (ISO/IEC 17024), `calibration_lab` مختبر معايرة (ISO/IEC 17025), `client_scheme` نظام اعتماد العميل | [inspection_body, personnel_certification_body] | none |
| country | الدولة | ISO alpha-2 | Y | — | SA | none |
| cr_number / foreign_reg_no | السجل التجاري / رقم التسجيل الأجنبي | string(10) / string(30) | cond. | cr_number required iff country = SA, Phase 0 CR format; else foreign_reg_no required | 1010000101 | none |
| verification_portal_url | بوابة التحقق | url | cond. | https only; host ∈ verification_domains | https://verify.aicc.example.com | none |
| verification_domains | نطاقات التحقق المعتمدة | string[] | Y | ≥ 1 lower-case FQDN; used by VF-4 | [aicc.example.com] | none |
| verification_email / verification_phone | بريد / هاتف التحقق | email / E.164 | N | email domain ∈ verification_domains | certs@aicc.example.com / +966110000101 | none |
| contact_name / contact_mobile | جهة الاتصال | string(120) / E.164 | N | — | Hisham Al-Rashid (fake) | personal |
| affiliated_contractor_ids | مقاولون مرتبطون | FK[] | N | contractors that share ownership or management with the TPI (TP-6) | [] | none |
| status | الحالة | enum | Y | §4.1 | approved | none |
| status_reason | سبب الحالة | text(500) | cond. | required for suspended / blacklisted; P3 hint | — | none (company) |
| blacklist_scope / blacklist_from | نطاق الحظر / من تاريخ | enum / date | cond. | iff blacklisted: `all_certificates` كل الشهادات, `issued_from` الشهادات الصادرة من تاريخ; date required for issued_from | all_certificates | none |

### 3.2 TPI accreditation — اعتماد الجهة

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| tpi_id | الجهة | FK | Y | — | AICC | none |
| accreditation_body | جهة الاعتماد | enum | Y | `sac` المركز السعودي للاعتماد `VERIFY`, `ilac_mra_other` جهة اعتماد أخرى موقِّعة على ILAC MRA, `client` العميل (only with standard client_scheme) | sac | none |
| standard | المعيار | enum | Y | `iso_iec_17020`, `iso_iec_17024`, `iso_iec_17025`, `client_scheme`; must correspond to one of the TPI's kinds | iso_iec_17020 | none |
| accreditation_no | رقم الاعتماد | string(40) | Y | unique per accreditation_body | SAC-TEST-IB-0101 | none |
| scope_categories | نطاق المعدات | EQC code[] | cond. | required for 17020 / 17025; ⊆ list EQC (§3.16) | [mobile_crane, crawler_crane, tower_crane, lifting_accessory, mewp, forklift, telehandler, man_basket, construction_hoist] | none |
| scope_cert_types | نطاق شهادات الأفراد | PCT code[] | cond. | required for 17024 / client_scheme personnel; ⊆ list PCT | [CRANE-OPERATOR, RIGGER, SIGNALLER] | none |
| valid_from / valid_until | ساري من / إلى | date | Y / Y | until > from | 2024-01-01 / 2027-12-31 | none |
| certificate_file | شهادة الاعتماد | file (PDF ≤ 10 MB) | Y | — | — | none |
| register_checked_at / register_checked_by | تاريخ التحقق من سجل جهة الاعتماد / المتحقق | timestamptz / FK | Y to count | accreditation confirmed on the accreditation body's public register (TP-3) | 2026-01-10 / Noura | personal (user) |

### 3.3 Client approval of a TPI (per project) — موافقة العميل على الجهة

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| project_id, tpi_id | المشروع، الجهة | FK | Y | unique pair | ANIA-EXP, AICC | none |
| approval_ref | مرجع الموافقة | string(40) | Y | — | ANIA-CL-TPI-TEST-007 | none |
| scope_categories / scope_cert_types | النطاق | code[] | Y (≥ 1 overall) | ⊆ the TPI's accredited scope | [mobile_crane, …] | none |
| valid_until | صالحة حتى | date | Y | — | 2027-06-30 | none |
| status | الحالة | enum | Y | `active` سارية, `withdrawn` مسحوبة | active | none |

### 3.4 Equipment item (org-wide master) — المعدة

One record per physical machine or accessory, reused across projects (a rented crane moves between sites). Scaffolds are in their own register (§3.8); gas detectors stay in Phase 3 (EQ-3).

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| equipment_no | رقم المعدة | string | sys | `EQP-` + 6 digits, sequential, immutable | EQP-000101 | none |
| category / subtype | الفئة / النوع الفرعي | enum / enum | Y / cond. | list EQC (§3.16); subtype required for lifting_accessory, mewp, pressure_vessel | tower_crane / flat_top | none |
| manufacturer / model | الشركة المصنعة / الطراز | string(80) ×2 | Y | — | Flat-top tower crane 12 t (fake) / FT-1260 | none |
| serial_no | الرقم التسلسلي | string(40) | Y | as on the manufacturer's plate; `serial_norm` (sys) = upper-case, spaces/`-`/`/` removed; (manufacturer_norm, serial_norm) unique org-wide (EQ-1) | TESTSN-TC-0001 | none |
| year_of_manufacture | سنة الصنع | int | Y | 1970 … current year | 2018 | none |
| owner_contractor_id | المقاول المالك/المسؤول | FK | Y | Phase 0 contractor; for hired-in equipment the hiring contractor (EQ-6) | QIMMA | none |
| hired_from | مستأجرة من | string(120) | N | rental company name; P3 hint | Gulf Crane Rentals (fictional) | none (personal iff an individual) |
| owner_fleet_no | رقم الأسطول | string(20) | N | — | QM-TC-01 | none |
| vehicle_id | المركبة (المرحلة 2) | FK | cond. | Phase 2 vehicle; 1 : 1; required when the item has a Saudi plate or is in the vehicle register; categories must be a pair in mapping VC→EQC (§3.16) | VEH-0003 | none |
| rated_capacity_t | الحمولة المقررة القصوى (طن) | decimal(8,3) | cond. | > 0; cranes (max on chart), hoists, forklifts, telehandlers, accessories (WLL), man-baskets (kg ÷ 1000) | 12.000 | none |
| max_radius_m / max_height_m | أقصى نصف قطر / أقصى ارتفاع (م) | decimal(6,2) | cond. | cranes: radius; MEWP: platform height; hoist/tower crane: configured height (§3.7) | 60.00 / 236.00 | none |
| persons_capacity | عدد الأشخاص | int | cond. | MEWP, man-basket, hoist, BMU, mast climber | — | none |
| pressure fields | بيانات الضغط | {design_pressure_bar, mawp_bar, volume_l, relief_set_bar} | cond. | pressure_vessel: relief_set_bar ≤ mawp_bar (`RELIEF_ABOVE_MAWP`) | {12.0, 11.0, 500, 11.0} | none |
| lifting_duty | يستخدم للرفع | bool | cond. | excavator/telehandler/loader: true if used to lift suspended loads (EC-9) | false | none |
| safety_devices | أجهزة السلامة | enum[] | cond. | cranes require `lmi_rci` (and `anti_two_block` for mobile/crawler); tower cranes `lmi_rci`, `anemometer`, plus `anti_collision` when SM-R11 overlap exists; MEWP `tilt_alarm`, `emergency_lowering`, `overload_cutout` | [lmi_rci, anemometer, anti_collision] | none |
| documents | المستندات | list {doc_type ∈ load_chart, operator_manual, foundation_design, erection_drawing, written_scheme, other; ref; file} | cond. | cranes: load_chart; tower cranes: foundation_design + erection_drawing; pressure vessels: written_scheme | — | none |
| service_status | حالة الخدمة | enum | sys | §4.2 | in_service | none |
| service_status_reason | سبب الحالة | enum + text(500) | cond. | list SSR (§3.16) | — | none |

### 3.5 Equipment deployment (item on a project) — تعيين المعدة في المشروع

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| deployment_no | رقم التعيين | string | sys | `EQD-<project>-<nnnn>` | EQD-RBT-52-0001 | none |
| equipment_id, project_id | المعدة، المشروع | FK | Y | one non-demobilised deployment per item org-wide (EM-4) | EQP-000101, RBT-52 | none |
| engagement_id | المقاول | FK | Y | engagement of the owner contractor (or hiring contractor) on the project; contractor Approved | QIMMA@RBT-52 | none |
| tag | رقم الوسم بالموقع | string(20) | Y | `^[A-Z0-9-]{2,20}$`; unique per project among non-demobilised deployments; this is the Phase 3 `equipment_tag.tag` | TC-01 | none |
| site_ids / zone_id | المواقع / المنطقة الحالية | FK[] / FK | Y / N | ⊆ engagement.site_ids | [S-TWR] / Z-TC01 | none |
| planned_arrival_on | تاريخ الوصول المخطط | date | Y | — | 2026-01-10 | none |
| approved_by / approved_at | المعتمِد | FK / timestamptz | cond. | EM-2 | Lina | personal (user) |
| arrived_at | وقت الوصول | timestamptz | cond. | gate-in or manual (EM-3) | 2026-01-12T07:10 | none |
| arrival_inspection | فحص الوصول | {at, by_user_id, checklist (list AIC), result ∈ pass/fail, notes} | cond. | EM-3 | pass | personal (user) |
| sticker_token / sticker_printed_ref | رمز الملصق / المرجع المطبوع | string / string | sys | Phase 2 §3.20 format, new kind `EQ` (§11); printed_ref = `<project>-<tag>` | HSE2:EQ:… / RBT-52-TC-01 | none |
| demobilised_on | تاريخ التسريح | date | cond. | — | — | none |
| status | الحالة | enum | Y | §4.3 | on_site | none |

### 3.6 Equipment inspection certificate — شهادة فحص المعدة

A certificate (report) from one TPI, with one or more lines (one per item: a crane certificate has one line; a lifting-gear register inspection may have 40).

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| cert_no | رقم الشهادة | string(40) | Y | as printed; unique per TPI (EC-1) | NKTI-TEST-26-0929 | none |
| tpi_id | جهة الفحص | FK | Y | TP-4 at inspected_on | NKTI | none |
| inspection_type | نوع الفحص | enum | Y | `initial` أولي, `periodic` دوري, `after_repair` بعد الإصلاح, `after_configuration_change` بعد تغيير التهيئة, `after_incident` بعد حادثة, `pre_mobilisation` قبل التعبئة | after_configuration_change | none |
| inspected_on / issued_on | تاريخ الفحص / الإصدار | date | Y | inspected_on ≤ issued_on ≤ today (EC-2) | 2026-09-29 / 2026-09-29 | none |
| printed_next_due | موعد الفحص التالي المطبوع | date | N | > inspected_on; null = not printed | 2027-09-28 | none |
| inspector_name / inspector_staff_no | اسم المفتش / رقمه لدى الجهة | string(120) / string(30) | Y / N | TPI staff number, never a national ID | Eng. Karim Nassar (fake) / NKTI-INS-071 | personal |
| scan_file | نسخة الشهادة | file (PDF ≤ 20 MB) | Y to Submit | stored in the documents bucket | — | personal (inspector signature) |
| tpi_verification_url | رابط التحقق لدى الجهة | url | N | from the TPI's QR on the certificate/sticker; VF-4 domain check | https://verify.nkti.example.com/c/TEST0929 | none |
| status | الحالة | enum | Y | §4.4 | accepted | none |
| verification_status | حالة التحقق | enum | sys | `not_verified` غير متحقق منها, `verified` متحقق منها, `failed` فشل التحقق, `unable_to_verify` تعذر التحقق (§4.4, VF) | verified | none (failed: sensitive iff personnel, P4-4) |
| submitted_by / reviewed_by / reviewed_at | مقدم الشهادة / المراجع | FK / FK / timestamptz | sys | reviewer ≠ submitter (EC-14) | Ibrahim / Lina | personal (users) |
| source | المصدر | enum | sys | `manual`, `import`, `tpi_register_file` (IM-6) | manual | none |

**Certificate line** — بند الشهادة:

| Field | AR label | Type | Req | Validation | Example |
|---|---|---|---|---|---|
| equipment_id | المعدة | FK | Y | one line per item per certificate | EQP-000101 |
| serial_as_printed | الرقم التسلسلي في الشهادة | string(40) | Y | serial_norm must equal the item's (EC-5) | TESTSN-TC-0001 |
| result | النتيجة | enum | Y | `pass` مقبول, `pass_with_conditions` مقبول بشروط, `fail` غير مقبول | pass_with_conditions |
| swl_t | الحمولة الآمنة (طن) | decimal(8,3) | cond. | lifting categories; ≤ item.rated_capacity_t | 12.000 |
| configuration_ref | التهيئة المفحوصة | string(100) | cond. | tower cranes, hoists: height/jib/tie-ins as inspected (CF-3) | HUH 236.00 m, jib 60 m, 9 tie-ins |
| load_test | اختبار التحميل | {performed bool, percent_of_swl decimal(5,1), test_weight_t} | cond. | required true for initial, after_repair (structural) and after_configuration_change of cranes/hoists (EC-7) | {true, 110.0, 13.200} |
| colour_code | رمز اللون | enum | cond. | when the colour scheme is enabled (EC-12) | — |
| limitations | الشروط والقيود | list {code (list LIM), value, text} | N | — | [{max_wind_ms, 20.0}] |
| defects | العيوب | list {category A/B/C, description, tpi_due_date} | N | each creates a Defect (DF-2) | [] |
| valid_until | صالحة حتى (فعلياً) | date | sys | §6.1 | 2027-09-28 |
| limiting_factor | العامل المحدِّد | enum | sys | `printed_next_due` / `category_interval` | printed_next_due |

### 3.7 Configuration event — حدث تغيير التهيئة

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| equipment_id | المعدة | FK | Y | categories tower_crane, construction_hoist, mast_climber, bmu, mobile_crane, crawler_crane | EQP-000101 | none |
| event_type | نوع الحدث | enum | Y | `erection` تركيب, `climb_jacking` رفع/تسلق البرج, `jib_change` تغيير الذراع, `tie_in_change` تغيير التثبيت, `relocation` نقل, `mast_extension` إطالة الصاري, `major_repair` إصلاح جوهري, `storm_exceedance` تجاوز رياح التوقف, `boom_configuration_change` تغيير تهيئة الذراع | climb_jacking | none |
| occurred_at | وقت الحدث | timestamptz | Y | ≤ now | 2026-09-28T14:00 | none |
| new_configuration | التهيئة الجديدة | string(100) | Y | — | HUH 236.00 m, 9 tie-ins | none |
| recorded_by | المسجِّل | FK | sys | capability 106 | Ibrahim | personal |

### 3.8 Scaffold (per project) — السقالة

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| scaffold_no | رقم السقالة | string | sys | `SCF-<project>-<nnnn>` | SCF-ANIA-EXP-0142 | none |
| tag | رقم البطاقة | string(20) | Y | unique per project among non-dismantled scaffolds; = Phase 3 `scaffold_tag_ref` / `equipment_tag.tag` | SC-0142 | none |
| engagement_id | المقاول المُركِّب | FK | Y | — | SAHARA@ANIA-EXP | none |
| zone_id / location_desc / level_code / grid_x_m, grid_y_m | المنطقة / الموقع / المستوى / الإحداثيات | FK / string(150) / string(10) / decimal | Y / Y / N / N | zone of the engagement's sites | Z-PIERB / Gridline P7–P9 east face | none |
| scaffold_type | نوع السقالة | enum | Y | `independent_tied` مستقلة مثبتة, `system_modular` نظام معياري, `mobile_tower` برج متنقل, `birdcage` قفص, `cantilever` كابولية, `suspended_hanging` معلقة, `loading_bay` منصة تحميل, `other` | system_modular | none |
| height_m | الارتفاع (م) | decimal(5,2) | Y | > 0 | 14.50 | none |
| load_class | فئة التحميل | int | Y | EN 12811-1 class 1–6 (0.75 / 1.5 / 2.0 / 3.0 / 4.5 / 6.0 kN/m²) | 3 | none |
| design_ref | مرجع التصميم | string(40) | cond. | required when SF-2 design trigger applies | — | none |
| erection_supervisor_worker_id / erection_crew | مشرف التركيب / الطاقم | FK / worker_id[] | Y / Y | crew trade scaffolder; hooks SF-3 | WKR-000008 / [WKR-000022, …] | personal |
| tag_status | حالة البطاقة | enum | sys | `none` بدون, `green` أخضر — آمنة للاستخدام, `yellow` أصفر — استخدام بقيود, `red` أحمر — ممنوع الاستخدام, `expired` منتهية, `inspection_required` تتطلب فحصاً (SF-5) | green | none |
| tag_valid_until | البطاقة سارية حتى | date | sys | §6.4 | 2026-10-07 | none |
| sticker_token | رمز QR | string | sys | kind `EQ` (one token family for equipment and scaffolds) | HSE2:EQ:… | none |
| status | الحالة | enum | Y | §4.6 | in_use | none |

**Scaffold inspection** — فحص السقالة: scaffold_id; inspection_type (`handover` تسليم, `periodic` دوري, `after_alteration` بعد التعديل, `after_adverse_weather` بعد طقس سيئ, `after_incident` بعد حادثة); inspected_at (≤ now, no back-dating > 60 min ASSUMPTION as Phase 3 GT-5); inspector_worker_id (in-force SCAFFOLD-INSPECTOR, SF-4); checklist (list SIC, every item pass/fail/n.a.); result (`green` / `yellow` / `red`); restrictions_en/ar (text 300, required for yellow); photos. PDPL: personal (inspector).

### 3.9 Personnel certificate — شهادة كفاءة الأفراد

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| record_no | رقم السجل | string | sys | `PCR-` + 6 digits | PCR-000019 | none |
| worker_id | حامل الشهادة | FK | Y | Phase 2 worker, not Anonymised (PC-1) | WKR-000019 | personal |
| cert_type | نوع الشهادة | code | Y | list PCT (§3.16) | CRANE-OPERATOR | personal |
| tpi_id | جهة الاعتماد | FK | Y | TP-4 for personnel (PC-5) | AICC | personal (link) |
| cert_no | رقم الشهادة/البطاقة | string(40) | Y | as printed; unique per (TPI, cert_type) | AICC-OP-TEST-24-0412 | personal |
| issued_on / printed_expiry | تاريخ الإصدار / الانتهاء المطبوع | date / date | Y / N | issued_on ≤ today; expiry > issued_on | 2024-04-01 / 2027-03-31 | personal |
| valid_until | صالحة حتى (فعلياً) | date | sys | §6.2 | 2027-03-31 | personal |
| scope_categories | نطاق المعدات | EQC code[] | cond. | operator types: ≥ 1, ⊆ the type's allowed categories (list PCT) | [mobile_crane, crawler_crane] | personal |
| max_capacity_t | أقصى حمولة مسموحة (طن) | decimal(8,3) | cond. | operator types where the scheme states a capacity; null = unlimited within categories | 60.000 | personal |
| level | المستوى | enum | cond. | RIGGER 1/2/3, ROPE-ACCESS 1/2/3, RADIOGRAPHER II/III (I not accepted, PC-7), SCAFFOLDER basic/advanced | — | personal |
| limitations | القيود | list {code (list LIM-P), text} | N | non-medical only (P4-6) | [] | personal |
| medical_restriction_on_card | قيد طبي مذكور في البطاقة | bool | Y | true when the card states any health-related restriction; **detail is not recorded** (P4-6) | false | **sensitive** |
| name_as_printed | الاسم كما في الشهادة | string(120) | Y | compared with the worker name (PC-4) | Zaheer Abbas | personal |
| id_entered_for_match | رقم الهوية في الشهادة (للمطابقة) | string | transient | **never stored**; HMAC compared with the worker's blind index (PC-3, P4-2) | — | sensitive (transient) |
| id_match_result | نتيجة مطابقة الهوية | enum | sys | `matched` مطابق, `matched_previous_id` مطابق لهوية سابقة, `not_shown` غير مذكور | matched | personal |
| name_match | مطابقة الاسم | enum | sys | `exact` تامة, `partial` جزئية, `none` لا توجد | exact | personal |
| assessment | التقييم | {theory_on, practical_on, language} | N | — | {2024-03-25, 2024-03-27, en} | personal |
| scan_front / scan_back | صورة البطاقة (أمام / خلف) | file (jpg/png/pdf ≤ 5 MB) | Y to Submit | encrypted personal bucket, signed URL ≤ 5 min (P4-3) | — | **sensitive** (shows ID/photo) |
| tpi_verification_url | رابط التحقق لدى الجهة | url | N | VF-4 | — | personal |
| status / verification_status | الحالة / حالة التحقق | enum / enum | Y / sys | §4.4 | accepted / verified | personal (failed: sensitive) |
| submitted_by / reviewed_by | المقدِّم / المراجع | FK | sys | reviewer ≠ submitter | Ahmed / Noura | personal |

### 3.10 Verification record (equipment and personnel certificates) — سجل التحقق

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| cert_kind / cert_id | نوع الشهادة / الشهادة | enum / FK | Y | `equipment`, `personnel` | personnel, PCR-000019 | none |
| method | طريقة التحقق | enum | Y | `tpi_portal` بوابة الجهة, `tpi_qr_url` رابط QR للجهة, `tpi_email` بريد الجهة, `tpi_phone` هاتف الجهة, `tpi_register_file` سجل مرسل من الجهة, `client_register` سجل العميل, `original_sighted` معاينة الأصل | tpi_portal | none |
| channel_used | القناة المستخدمة | string(200) | Y | must be one of the TPI's registered portal URL host, verification_domains, email or phone (VF-3) | verify.aicc.example.com | none |
| outcome | النتيجة | enum | Y | `confirmed` مؤكدة, `not_found` غير موجودة لدى الجهة, `details_differ` بيانات مختلفة, `revoked_by_tpi` ملغاة من الجهة, `no_response` لا يوجد رد | confirmed | none; not_found/details_differ on personnel: **sensitive** |
| differences | الفروقات | enum[] + text(300) | cond. | iff details_differ: `holder`, `serial`, `dates`, `scope`, `swl`, `result`, `other` | — | sensitive (personnel) |
| reference | المرجع | string(100) | Y | portal result id, email subject/date, call log ref | AICC portal ref TEST-77812 | none |
| evidence_file | الدليل | file (pdf/png ≤ 5 MB) | cond. | required except for `tpi_phone` (then reference ≥ 20 chars naming the TPI person's role, not their mobile) | screenshot | personal |
| performed_by / performed_at | المتحقق / الوقت | FK / timestamptz | sys | capability 108; ≠ submitter (VF-2) | Noura / 2026-02-03T09:12 | personal |

### 3.11 Defect — عيب المعدة

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| defect_no | رقم العيب | string | sys | `DEF-<project>-<yyyy>-<nnnn>` | DEF-ANIA-EXP-2026-0007 | none |
| equipment_id / scaffold_id | المعدة / السقالة | FK | one Y | item with a deployment on the project, or scaffold | EQP-000003 | none |
| source / source_ref | المصدر / المرجع | enum / string | Y / cond. | `tpi_inspection` (cert line), `pre_use_check`, `arrival_inspection`, `site_inspection` (Phase 1 inspection ref), `incident` (Phase 1 incident ref), `observation` (Phase 1), `ptw_audit` (Phase 3 audit), `operator_report`, `other` | pre_use_check | none |
| category | الفئة | enum | Y | `A` خطير — إيقاف فوري, `B` يُصلح قبل موعد محدد, `C` ملاحظة (DF-1) | A | none |
| description_en / description_ar | الوصف | text(1000) | Y / N | P3 hint | Hydraulic oil leak at boom lift cylinder gland | none |
| photos | الصور | file[] | N | "avoid faces" hint (as Phase 3 AU-8) | — | personal (possible) |
| raised_by_user_id / raised_by_worker_id | المُبلِّغ | FK | one Y | — | Omar | personal |
| raised_at | وقت الإبلاغ | timestamptz | Y | ≤ now | 2026-09-26T06:40 | none |
| tpi_due_date / due_date | موعد الجهة / الموعد الفعلي | date / date | cond. / sys | B only; §6.3 | — | none |
| rectification | الإصلاح | {description, done_by_text, done_at, evidence files} | cond. | DF-5 | — | none |
| closure | الإغلاق | {method ∈ tpi_certificate (cert line ref) / hse_verification, closed_by, closed_at, note} | cond. | DF-6 | — | personal (user) |
| status | الحالة | enum | Y | §4.5 | open | none |

### 3.12 Certification ban (person) — حظر الشهادات للشخص

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| worker_id | الشخص | FK | Y | — | WKR-000022 | personal |
| scope | النطاق | `all` or PCT code[] | Y | — | all | personal |
| reason_code | سبب الحظر | enum | Y | list BR: `forged_certificate` شهادة مزورة مشتبه بها, `certificate_misuse` إساءة استخدام شهادة, `unsafe_operation` تشغيل غير آمن, `incident_investigation` تحقيق في حادثة, `other` | forged_certificate | **sensitive** |
| reason_text | التفاصيل | text(500) | Y | facts only, ≥ 20 chars; hint "no criminal-law conclusions" | — | **sensitive** |
| from / review_due_on | من / موعد المراجعة | date | Y / sys | review_due_on = from + `ban_review_months` | 2026-09-17 / 2027-03-17 | sensitive |
| status | الحالة | enum | Y | `active` ساري, `lifted` مرفوع | active | sensitive |
| lifted_at / lifted_by / lift_reason | الرفع | timestamptz / FK / text | cond. | capability 115 | — | sensitive |

### 3.13 Equipment blacklist record — حظر المعدة
Stored on the item (service_status = blacklisted) with an event row: equipment_id, reason_code (list EBR: `forged_certificate` شهادة مزورة, `identity_unverifiable` تعذر التحقق من هوية المعدة (لوحة الرقم معدلة/مفقودة), `structural_damage` ضرر إنشائي غير قابل للإصلاح, `repeated_dangerous_defects` عيوب خطيرة متكررة, `recall_unresolved` استدعاء غير منفذ من المصنع, `other`), reason_text (≥ 20 chars), from, by (capability 115), lifted_at/by/reason. PDPL: none.

### 3.14 Hook policy state (per project and kind) — حالة سياسة المتطلبات

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| project_id / kind | المشروع / النوع | FK / enum | Y | kind ∈ {`personnel_certificate`, `equipment_certificate`}; unique pair | ANIA-EXP / equipment_certificate | none |
| provider_registered_on | تاريخ تفعيل المزوّد | date | sys | set when Phase 4 goes live on the project (HK4-1) | 2026-10-01 | none |
| critical_block_from | بدء الحظر للرموز الحرجة | date | sys | §6.5 | 2026-10-08 | none |
| general_block_from | بدء الحظر لبقية الرموز | date | sys | §6.5; may be moved once (HK4-6) | 2026-10-31 | none |
| deferral | التأجيل | {new_date, reason (≥ 30 chars), by, at} | N | at most one per kind and project | — | personal (user) |
| early_switch | التفعيل المبكر | {at, by, codes or all} | N | HK4-5 | — | personal (user) |
| stage | المرحلة | enum | sys | §4.8 | transition | none |

### 3.15 Certificate import batch — دفعة استيراد الشهادات
Same fields and lifecycle as Phase 1 §3.2 (file, sha256, size, mode `insert_only` only, status validated / committed / discarded / expired after 60 min, counts, per-row report), plus `template` (`equipment_certificates` / `personnel_certificates`), `source` (`contractor_file` / `tpi_register_file`), optional `scans_zip` (≤ 200 MB, files named `<cert_no>.pdf|jpg|png`, front/back as `<cert_no>_front`/`_back`), `evidence_file` (required for tpi_register_file: the TPI's email as PDF/EML). Templates and codes in §5.11. PDPL: the uploaded file is **sensitive** when it contains an ID column (IM-4).

### 3.16 Reference lists (seeded EN/AR, codes immutable, HSE Manager edits labels and tightens values)

**EQC — equipment categories** (interval = default maximum between thorough examinations, months; hook code = equipment_certificate code that the category satisfies; "operator" = personnel_certificate code required of its operator, HK4-9):

| Code | EN / AR | Interval | Hook code | Operator code |
|---|---|---|---|---|
| tower_crane | Tower crane / رافعة برجية | 12 + CF-1 | CRANE-TPI | CRANE-OPERATOR |
| mobile_crane | Mobile crane / رافعة متحركة | 12 | CRANE-TPI | CRANE-OPERATOR |
| crawler_crane | Crawler crane / رافعة مجنزرة | 12 | CRANE-TPI | CRANE-OPERATOR |
| loader_crane | Lorry loader crane / رافعة محمولة على شاحنة | 12 | CRANE-TPI | CRANE-OPERATOR |
| overhead_gantry_crane | Overhead / gantry crane / رافعة علوية / جسرية | 12 | CRANE-TPI | CRANE-OPERATOR |
| construction_hoist | Construction hoist (persons/materials) / مصعد إنشائي | 6 + CF-1 | HOIST-TPI | HOIST-OPERATOR |
| mast_climber | Mast-climbing work platform / منصة صاعدة على صاري | 6 + CF-1 | HOIST-TPI | HOIST-OPERATOR |
| bmu | Building maintenance unit / وحدة صيانة المباني | 6 | HOIST-TPI | HOIST-OPERATOR |
| mewp | MEWP (subtypes scissor, boom, vertical_mast) / منصة رفع أفراد متحركة | 6 | MEWP-TPI | MEWP-OPERATOR |
| man_basket | Crane-suspended man-basket / سلة رفع أفراد | 6 | MAN-BASKET-TPI | — |
| forklift | Forklift / رافعة شوكية | 12 | FORKLIFT-TPI | FORKLIFT-OPERATOR |
| telehandler | Telehandler / رافعة تلسكوبية | 12 (6 when a man-basket attachment is certified) | TELEHANDLER-TPI | TELEHANDLER-OPERATOR |
| excavator | Excavator / حفارة | 12 | PLANT-TPI | PLANT-OPERATOR |
| wheel_loader | Wheel loader / backhoe loader / لودر | 12 | PLANT-TPI | PLANT-OPERATOR |
| piling_rig | Piling / drilling rig / حفارة خوازيق | 12 | PLANT-TPI | PLANT-OPERATOR |
| concrete_pump_boom | Concrete pump boom / مضخة خرسانة بذراع | 12 | PLANT-TPI | PLANT-OPERATOR |
| lifting_accessory | Lifting accessory (subtypes wire_rope_sling, chain_sling, synthetic_sling, shackle, hook, eyebolt, spreader_beam, lifting_beam, plate_clamp, chain_block, lever_hoist, beam_clamp, other) / ملحقات الرفع | 6 | LIFTING-ACCESSORY-TPI | — |
| tripod_winch | CSE rescue tripod / winch / حامل ورافعة إنقاذ | 6 | RESCUE-WINCH-TPI | — |
| pressure_vessel | Pressure vessel (subtypes air_receiver, hydraulic_accumulator, other) / وعاء ضغط | 12 `VERIFY` R7 | PRESSURE-TPI | — |
| scaffold | Scaffold (separate register §3.8) / سقالة | 7 days (SF-5) | SCAFFOLD-TAG | — |

`VERIFY` every interval against R1–R4, R7 and the client (R10). Gas detectors are not an EQC category (EQ-3).

**Mappings** — Phase 2 VC → EQC (allowed pairs): mobile_crane→mobile_crane; crawler_crane→crawler_crane; mewp→mewp; forklift→forklift; telehandler→telehandler; excavator→excavator; wheel_loader→wheel_loader; truck→loader_crane; other→any. Phase 3 EQ → EQC: tower_crane, mobile_crane, crawler_crane, mewp, man_basket, mast_climber, bmu, scaffold, tripod_winch → same code; lifting_accessory→lifting_accessory; spreader_beam→lifting_accessory (subtype spreader_beam); other EQ codes → not certifiable (no hook).

**PCT — personnel certificate types** (cap = default maximum validity in months, §6.2; "satisfies" = hook codes met by an in-force certificate of the type; scope = what PC-7 checks):

| Code | EN / AR | Cap | Satisfies | Scope checked |
|---|---|---|---|---|
| CRANE-OPERATOR | Crane operator / مشغل رافعة | 36 `VERIFY` | CRANE-OPERATOR | categories ⊆ {tower_crane, mobile_crane, crawler_crane, loader_crane, overhead_gantry_crane}; max_capacity_t |
| RIGGER | Rigger (level 1, 2, 3) / عامل ربط | 36 | RIGGER | level ≥ `rigger_level_critical_min` on critical lifts |
| SIGNALLER | Signal person (lifting) / موجه إشارات الرفع | 36 | SIGNALLER | — |
| BANKSMAN | Banksman / plant marshaller / منظم حركة المعدات | 36 | BANKSMAN | — |
| SIGNALLER-BANKSMAN | Combined signaller & banksman card / بطاقة موجه إشارات ومنظم حركة | 36 | SIGNALLER, BANKSMAN | — |
| MEWP-OPERATOR | MEWP operator (groups/types 1a…3b) / مشغل منصة رفع أفراد | 60 | MEWP-OPERATOR | subtype ⊆ scope |
| FORKLIFT-OPERATOR | Forklift operator / مشغل رافعة شوكية | 36 (OSHA 1910.178(l)(4)(iii)) | FORKLIFT-OPERATOR | max_capacity_t |
| TELEHANDLER-OPERATOR | Telehandler operator / مشغل رافعة تلسكوبية | 36 | TELEHANDLER-OPERATOR | man-basket use needs limitation-free scope |
| PLANT-OPERATOR | Earthmoving/plant operator / مشغل معدات ثقيلة | 36 | PLANT-OPERATOR | categories ⊆ {excavator, wheel_loader, piling_rig, concrete_pump_boom} |
| HOIST-OPERATOR | Hoist / mast-climber / BMU operator / مشغل مصعد إنشائي أو منصة صاعدة | 36 | HOIST-OPERATOR | categories |
| SCAFFOLDER | Scaffolder (basic, advanced) / عامل سقالات | 60 | SCAFFOLDER | advanced required for cantilever, suspended_hanging, birdcage > 6 m ASSUMPTION |
| SCAFFOLD-INSPECTOR | Scaffold inspector / مفتش سقالات | 60 | SCAFFOLD-INSPECTOR | — |
| GAS-TESTER | Authorised gas tester card / بطاقة فاحص غاز معتمد | 24 ASSUMPTION | GAS-TESTER | — |
| RADIOGRAPHER | Industrial radiographer (ISO 9712 RT level II/III) / فني تصوير إشعاعي | 60 | RADIOGRAPHER | level ≥ II |
| ROPE-ACCESS | Rope access technician (level 1–3) / فني الوصول بالحبال | 36 | ROPE-ACCESS | — |
| LIFT-SUPERVISOR | Lift supervisor / مشرف رفع | 36 | LIFT-SUPERVISOR | optional appointment hook (BD-5) |
| APPOINTED-PERSON-LIFTING | Appointed person (lifting) / الشخص المعيّن لعمليات الرفع | 60 | APPOINTED-PERSON-LIFTING | optional appointment hook |
| AP-ELEC-LV / AP-ELEC-HV | Authorised person, electrical LV / HV / شخص مخوَّل كهربائياً (جهد منخفض/عالٍ) | 36 | same code | optional appointment hook |
| CSE-STANDBY-CARD | Confined-space standby/attendant card (third-party) / بطاقة مناوب الأماكن المحصورة | 24 | CSE-STANDBY-CARD | optional (BD-6) |
| LOTO-AUTHORISED-CARD | Authorised isolator card (third-party) / بطاقة منفذ عزل معتمد | 36 | LOTO-AUTHORISED-CARD | optional (BD-6) |

**LIM — equipment limitation codes:** `derated_swl` حمولة مخفّضة (value t) · `no_personnel_lifting` يمنع رفع الأشخاص · `max_wind_ms` حد الرياح (value) · `daylight_only` نهاراً فقط · `fixed_configuration_only` بالتهيئة المفحوصة فقط · `outriggers_full_extension_only` بالمساند ممتدة بالكامل فقط · `supervised_use_only` تحت إشراف فقط · `reinspect_after_hours` إعادة الفحص بعد ساعات تشغيل (value) · `other` (text). **LIM-P — personnel limitation codes (non-medical):** `supervised_only` تحت إشراف · `trainee_logbook` متدرب بسجل · `specific_model_only` طراز محدد فقط (text) · `other` (text).
**AIC — arrival inspection checklist:** AIC-01 TPI sticker present and number = certificate · AIC-02 serial plate legible and = register · AIC-03 no visible structural damage, cracks, leaks · AIC-04 safety devices functional (LMI/RCI, limits, alarms, emergency stop/lowering) · AIC-05 load chart and operator manual in cab · AIC-06 tyres/tracks, outriggers and pads · AIC-07 fire extinguisher and spill kit (plant) · AIC-08 lights, beacon, reverse alarm (mobile plant).
**SIC — scaffold inspection checklist:** SIC-01 foundations, base plates, sole boards · SIC-02 standards plumb, ledgers, transoms · SIC-03 bracing · SIC-04 ties/anchors to design · SIC-05 platforms fully boarded, no gaps · SIC-06 guardrail (≥ 950 mm), mid-rail, toe board · SIC-07 safe access (secured ladder/stair) · SIC-08 load class signage and loading within class · SIC-09 no unauthorised alterations · SIC-10 nets/sheeting secured (n.a. allowed) · SIC-11 clearance to live services/plant.
**SSR — service status reasons:** `awaiting_certificate` · `certificate_expired` · `certificate_suspended` · `certificate_revoked` · `certificate_unverified` · `configuration_changed` · `failed_inspection` · `defect_a` · `defect_b_overdue` · `tpi_blacklisted` · `manual_tag_out` · `blacklisted` · `retired_destroyed` · `retired_sold` · `retired_other`.

### 3.17 Phase 4 project settings (extend Phase 0 §3.9, Phase 1 §3.10, Phase 2 §3.22, Phase 3 §3.17; HSE Manager only, audited; "Allowed" is the only range accepted)

| Key | AR label | Type | Default | Allowed |
|---|---|---|---|---|
| equipment_interval_months | فترات الفحص حسب الفئة | map EQC → int | list EQC | 1 … default (shorten only) |
| personnel_cert_cap_months | أقصى صلاحية حسب نوع الشهادة | map PCT → int | list PCT | 6 … default (shorten only) |
| require_client_approved_tpi | اشتراط موافقة العميل على الجهة | bool | false ASSUMPTION (§10 Q1) | true · false (false → true only once certificates are re-checked, TP-5) |
| unverified_acceptance_hours | قبول الشهادة قبل التحقق (ساعات) | int | **0** ASSUMPTION (§10 Q3) | 0–24 |
| verification_due_days | مهلة التحقق | int | 3 | 1–14 |
| defect_b_max_days | أقصى مهلة لإصلاح عيب B | int | 30 | 1–30 |
| defect_b_default_days | المهلة الافتراضية لعيب B | int | 14 | 1 … defect_b_max_days |
| scaffold_inspection_interval_days | فترة فحص السقالات | int | 7 | 1–7 |
| scaffold_design_height_m | ارتفاع يتطلب تصميم السقالة | decimal | 20.00 ASSUMPTION `VERIFY` TG20 / client | 6.00–20.00 |
| arrival_inspection_hours | مهلة فحص الوصول | int | 24 | 1–24 |
| rigger_level_critical_min | أدنى مستوى لعامل الربط في الرفع الحرج | int | 2 ASSUMPTION | 1–3 (raise only above 1 once set) |
| trade_cert_requirements | الشهادات المطلوبة حسب المهنة | map trade → PCT code | crane_operator → CRANE-OPERATOR · rigger → RIGGER · scaffolder → SCAFFOLDER | add / tighten only |
| hook_transition_days | المرحلة الانتقالية (أيام) | int | 30 ASSUMPTION | 0–30 |
| hook_critical_codes | الرموز الحرجة | code[] | CRANE-TPI, CRANE-OPERATOR, LIFTING-ACCESSORY-TPI, MAN-BASKET-TPI, MEWP-TPI, HOIST-TPI, RIGGER, SIGNALLER | add only |
| hook_critical_transition_days | المرحلة الانتقالية للرموز الحرجة | int | 7 ASSUMPTION | 0–7 |
| lifting_gear_colour_scheme | نظام ألوان ملحقات الرفع | {enabled, periods [{from MM-DD, to MM-DD, colour}]} | enabled = false `VERIFY` R10 | — |
| equipment_cert_warning_pct / personnel_cert_warning_pct / scaffold_tag_warning_pct | حدود إنذار الامتثال | decimal | 98.0 / 95.0 / 95.0 ASSUMPTION | 80.0–100.0 |
| dangerous_defect_warning_count | حد إنذار العيوب الخطيرة | int | 3 ASSUMPTION | 1–20 |
| ban_review_months | مراجعة حظر الشهادات | int | 6 ASSUMPTION | 1–12 |
| cert_scan_retention_years | الاحتفاظ بصور بطاقات الأفراد بعد انتهائها | int | 2 ASSUMPTION | 1–10 |
| alert_schedule_long_days | جدول التنبيهات | int[] | [30, 14, 7, 0] (Phase 0/1/2 convention) | — |

## 4. Workflow / states

Who = capability numbers (§5.15). Every transition is audited with before/after (Phase 0 rule 35). "Job" = scheduler `cert_daily` at 00:05:45 Asia/Riyadh, `cert_minute` every 60 s for event-driven recomputation (§5.10 HK4-10).

### 4.1 TPI organisation
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Draft | مسودة | 114 | Create |
| Draft → Pending Approval | بانتظار الاعتماد | 114 | ≥ 1 accreditation with register_checked_at (TP-3), or kind client_scheme with a client approval |
| Pending Approval → Approved | معتمدة | 115 | — |
| Pending Approval → Draft | مسودة | 115 | Returned with comment |
| Approved → Suspended | موقوفة | 115 | Reason; BL-6 |
| Suspended → Approved | معتمدة | 115 | Reason |
| Approved/Suspended → Blacklisted | محظورة | 115 | Reason, blacklist_scope; BL-7; terminal except "lift blacklist" → Suspended (as Phase 0 §4.2) |
| Approved → Accreditation lapsed (derived) | الاعتماد منتهٍ | — | No accreditation valid today for any kind (display only; TP-4 uses dates) |

### 4.2 Equipment item — service status (system-maintained unless stated)
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Awaiting Certificate | بانتظار الشهادة | 106 | Create |
| Awaiting Certificate / Quarantined → In Service | في الخدمة | System | A certificate line becomes in force (§6.6) and no open A or overdue B defect |
| In Service → Quarantined | معزولة عن الاستخدام | System | No line in force: expired (job), certificate Suspended/Revoked, unverified after acceptance window, configuration event (CF-1), TPI blacklisted (BL-7) |
| In Service / Quarantined → Out of Service | خارج الخدمة | 110 (tag out); System (A defect DF-3, B overdue DF-4, failed inspection EC-6) | Reason SSR |
| Out of Service → In Service / Quarantined | في الخدمة / معزولة | 112 | DF-6 return-to-service conditions; target state follows certificate state |
| any (not Retired) → Blacklisted | محظورة | 115 | BL-3 |
| Blacklisted → Out of Service | خارج الخدمة | 115 | Lift blacklist (reason); a new TPI certificate is needed before use |
| any → Retired | مستبعدة | 112 (sold, other); System (`retired_destroyed` from DF-7) | Terminal; sticker tokens revoked |

### 4.3 Equipment deployment
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Planned | مخطط | 106 | Create (EM-1) |
| Planned → Approved for Mobilisation | معتمد للتعبئة | 109 | EM-2; sticker token issued |
| Planned → Cancelled | ملغى | 106 / 109 | Terminal |
| Approved → On Site | في الموقع | System (gate `in` scan, GE-3) or 109 (manual arrival) | arrived_at set |
| On Site → Demobilised | مُسرّح | 109; System (contractor blacklisted/demobilised, item blacklisted, engagement ended) | demobilised_on; token revoked (EM-5) |

### 4.4 Certificate (equipment and personnel) and verification
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Draft | مسودة | 106 (equipment) / 118 (personnel); 120 (import) | Create |
| Draft → Submitted | مُقدَّمة | same | Scan attached; EC-1…EC-5 / PC-1…PC-7 pass |
| Submitted → Draft | مسودة | 107 | Returned with comment (≥ 10 chars) |
| Submitted → Accepted | مقبولة | 107 (reviewer ≠ submitter) | Document review: identity, dates, scope, TPI acceptability; may precede verification |
| Submitted → Rejected | مرفوضة | 107; System (verification failed, VF-6) | Reason; terminal |
| Accepted → Superseded | مُستبدلة | System | A newer certificate for the same item/line (EC-10) or the same (worker, type) (PC-9) becomes in force |
| Accepted → Suspended | موقوفة | 116; System (CF-1 configuration change; TPI suspension notice) | Reason; hard stop (HK4-3) |
| Suspended → Accepted | مقبولة | 116 | Reason; never for `configuration_changed` (a new certificate is needed) |
| Accepted/Suspended → Revoked | ملغاة | 107 (TPI revocation notice), System (VF-6 failed after acceptance; BL-7 TPI blacklisted) | Terminal; hard stop |
| Accepted → Expired | منتهية | Job | today > valid_until (all lines); terminal |

Verification status (independent, §3.10): `not_verified` → `verified` (outcome confirmed) · `not_verified` → `failed` (not_found, details_differ, revoked_by_tpi) · `not_verified` → `unable_to_verify` (no_response recorded twice ≥ 24 h apart) → `verified` / `failed` on a later attempt. **In force** (سارية) is derived (§6.6).

### 4.5 Defect
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Open | مفتوح | 110; System (TPI certificate line defect) | Category A → item Out of Service immediately (DF-3) |
| Open → Rectified | تم الإصلاح | 111 | Rectification record (DF-5) |
| Rectified → Closed | مغلق | 112 (≠ rectifier) | DF-6 (TPI certificate for A on lifting/hoisting/person-carrying items; HSE verification otherwise) |
| Rectified → Open | مفتوح | 112 | Verification failed (reason) |
| Open (A, lifting_accessory) → Closed (item Retired) | مغلق (إتلاف) | 112 | DF-7: destroyed / returned to manufacturer |
| Open/Rectified → Cancelled | ملغى | 112 | Raised in error (reason ≥ 20 chars); not for TPI-raised defects |

### 4.6 Scaffold
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Under Erection | قيد التركيب | 106 | Create; tag_status red ("not complete — do not use") |
| Under Erection → In Use | قيد الاستخدام | 113 | Handover inspection green or yellow (SF-4) |
| In Use → In Use | — | 113 | Periodic / after-alteration / after-weather inspection green or yellow |
| In Use → Closed (Red) | مغلقة (حمراء) | 113; System (SF-5 expired or re-inspection required is shown as tag_status only — status stays In Use but use is not permitted) | Inspection result red |
| Closed (Red) / In Use → Under Alteration | قيد التعديل | 106 | Alteration started (tag red) |
| Under Alteration / Closed (Red) → In Use | قيد الاستخدام | 113 | New inspection green/yellow |
| any → Dismantled | مُفككة | 106 | Terminal; token revoked |

### 4.7 Certification ban and equipment blacklist
Certification ban: — → Active (115) → Lifted (115, reason; certificates stay Revoked/Rejected; new ones must be submitted). Equipment blacklist: §4.2. TPI blacklist: §4.1.

### 4.8 Hook policy per project and kind (the warn → block switch)
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| Stage 0 `warn` (no provider) → Stage 1 `transition` | انتقالية | System | Phase 4 provider registered on the project (HK4-1); dates computed (§6.5) |
| Stage 1 → Stage 2 `block` (critical codes) | حظر (الرموز الحرجة) | System at critical_block_from 00:00; 124 earlier (HK4-5) | Audited (actor null = system); alerts §7 |
| Stage 1 → Stage 2 `block` (all codes) | حظر (كل الرموز) | System at general_block_from 00:00; 124 earlier | Same |
| Stage 1 general_block_from → later date | تأجيل | 124 | Once, ≤ 30 days, reason (HK4-6); never for critical codes |
| Stage 2 → Stage 1 | — | — | **Not allowed** (`HOOK_POLICY_LOOSENING`); a return to warn needs a spec change |

Hard stops (HK4-3) block in every stage.

### 4.9 Import batch
As Phase 1 §4.1/§3.2: Uploaded → Validated (dry-run) → Committed / Discarded; Validated → Expired after 60 min.

## 5. Business rules

### 5.1 Boundary with Phase 5 training (BD)
- BD-1. **Phase 4 personnel certification** = a credential that (a) is issued by a body registered here as a TPI organisation with kind `personnel_certification_body` or `client_scheme`, (b) attests competence after an assessment (practical and/or theory) for a defined scope (equipment type, capacity, level, activity), (c) carries a number the issuer can confirm, and (d) has an expiry (or receives the PCT cap). Types are list PCT (hook kind `personnel_certificate`).
- BD-2. **Phase 5 training certificate** = evidence of attending or completing a course from a training provider (internal or external), including courses with a test: induction-type and awareness courses, WAH, LOTO awareness, confined-space entrant/attendant/rescue courses, fire watch, first aid, fire warden, PTW issuer/receiver, NEBOSH/IOSH, refreshers (hook kind `training_course`).
- BD-3. A credential type exists in exactly one catalogue: PCT codes and Phase 5 course codes are disjoint; creating a Phase 4 type whose code exists as a Phase 5 course (or the reverse) is rejected `CODE_IN_OTHER_CATALOGUE`. A training provider cannot be registered as a TPI organisation (no kind for it).
- BD-4. When a competence needs both, both hooks are attached and both must be met (strictest wins) — e.g. gas tester: Phase 3 HK3-2 already requires `personnel_certificate: GAS-TESTER` **and** `training_course: GAS-TEST`.
- BD-5. Phase 3 PTW appointments (issuer, area authority, gas tester, authorised person, isolation authority) are **project authorisations**, not certificates. A certificate may be made a precondition of an appointment through the HK3-2 appointment attach point (types LIFT-SUPERVISOR, APPOINTED-PERSON-LIFTING, AP-ELEC-LV/HV); none is attached by default ASSUMPTION (§10 Q10).
- BD-6. LOTO and confined-space attendants default to Phase 5 training (Phase 3 hooks `training_course: LOTO`, `LOTO-AUTHORITY`, `CSE-ATTENDANT` stay as they are). Where a client scheme issues third-party cards, the HSE Manager additionally attaches `personnel_certificate: LOTO-AUTHORISED-CARD` / `CSE-STANDBY-CARD`.
- BD-7. Phase 2 induction stays in Phase 2 (HK-7); Phase 4 never reads induction records.

### 5.2 TPI organisations (TP)
- TP-1. A TPI is an organisation record, not a contractor engagement; it has no users in v1.0 ASSUMPTION.
- TP-2. Status Approved requires capability 115; HSE Officers create and submit (114).
- TP-3. An accreditation counts only when `register_checked_at` is set (the accreditation was confirmed on the accreditation body's public register) and today ≤ valid_until for current acceptance.
- TP-4. **Acceptability at issue:** an equipment certificate is accepted only if, on its `inspected_on` date, the TPI (a) was Approved (not Draft/Pending, not Suspended, not Blacklisted), (b) held a counted 17020 accreditation (or, for client_scheme, an active client approval) whose valid_from ≤ inspected_on ≤ valid_until and whose scope_categories contain every line's item category. Personnel certificates: same with 17024 / client_scheme and scope_cert_types ∋ cert_type on `issued_on`. Otherwise 422 `TPI_NOT_ACCEPTABLE` with meta reason ∈ {`TPI_NOT_APPROVED`, `TPI_SUSPENDED`, `TPI_BLACKLISTED`, `TPI_ACCREDITATION_INVALID`, `TPI_SCOPE_NOT_COVERED`}.
- TP-5. With `require_client_approved_tpi` = true, TP-4 additionally needs an active client approval for the project covering the category/type at the inspection/issue date (`TPI_NOT_CLIENT_APPROVED`). Switching the setting to true lists every in-force certificate that would fail; they turn Quarantined/not met after 7 days unless re-covered ASSUMPTION.
- TP-6. **Independence:** the TPI must not be the equipment's owner contractor or the holder's employer, nor listed in the TPI's affiliated_contractor_ids, nor share a CR number with that contractor (`TPI_NOT_INDEPENDENT`). Client-scheme TPIs are exempt from the holder's-employer check only when the client is not that employer.
- TP-7. An accreditation that later expires does not invalidate certificates issued while it was valid; their records show a "TPI accreditation since lapsed" note, and new certificates are refused (TP-4).
- TP-8. Accreditation and client-approval expiries alert on 30 / 14 / 7 / 0 days (§7).

### 5.3 Equipment register and mobilisation (EQ, EM)
- EQ-1. (manufacturer_norm, serial_norm) is unique org-wide; a duplicate returns 409 `EQUIPMENT_EXISTS` with equipment_no when the caller can see it (capability 105 on a project where it is deployed), else 409 `EQUIPMENT_EXISTS_OUT_OF_SCOPE`. A serial matching a Blacklisted item returns 409 `EQUIPMENT_BLACKLISTED` to every caller.
- EQ-2. An item linked to a Phase 2 vehicle must have a category paired with the vehicle's VC (§3.16), else 422 `CATEGORY_MISMATCH`; the same vehicle cannot be linked to two items.
- EQ-3. **Gas detectors are linked, not merged:** they stay in the Phase 3 detector register (calibration, bump tests, quarantine); creating an item for a detector is rejected `USE_DETECTOR_REGISTER`. Phase 4 adds only the optional `calibration_body_id` on the detector (§11) so that a calibration lab is a registered TPI (kind calibration_lab) and BL-7 can quarantine detectors it calibrated.
- EQ-4. Category-required attributes (§3.4) must be present at Submit of the first certificate (`ATTRIBUTE_REQUIRED` naming the field): cranes rated_capacity_t, max_radius_m, load_chart, safety_devices ∋ lmi_rci; tower cranes also foundation_design, erection_drawing, anemometer; MEWP max_height_m, persons_capacity; pressure vessel pressure fields and written_scheme.
- EQ-5. The item's owner_contractor_id must be Approved (Phase 0 rule 26 by analogy) to create deployments.
- EQ-6. Hired-in equipment is registered under the hiring contractor (owner_contractor_id) with hired_from text; the hiring contractor is accountable for its certificates ASSUMPTION (§10 Q14).
- EM-1. A deployment needs the engagement on the project, a tag unique on the project (`TAG_EXISTS`) and site_ids ⊆ engagement.site_ids.
- EM-2. **Mobilisation approval** (capability 109) requires: item In Service (certificate in force and verified per §6.6) — not Awaiting, Quarantined, Out of Service, Blacklisted or Retired (`EQUIPMENT_NOT_IN_SERVICE` with the SSR reason); engagement contractor not Suspended or Blacklisted (`CONTRACTOR_SUSPENDED`); when vehicle_id is set, the Phase 2 vehicle exists on the project's engagement. Approval issues the EQ sticker token.
- EM-3. **Arrival:** first `in` scan of the sticker at a gate (GE-3) or a manual arrival record sets On Site. An arrival inspection (list AIC, every item pass or n.a.) is recorded within `arrival_inspection_hours`; until it passes, the hook provider returns not_met `ARRIVAL_INSPECTION_MISSING` for the item. A failed item creates a Defect (source arrival_inspection) with the category chosen by the inspector.
- EM-4. An item has at most one non-demobilised deployment org-wide (`EQUIPMENT_DEPLOYED_ELSEWHERE`); moving a crane to another project = demobilise, then a new deployment.
- EM-5. Demobilisation revokes the sticker token (later scans → `CREDENTIAL_REVOKED`) and closes the item's open Phase 3 equipment-line eligibility on that project.
- EM-6. Contractor Blacklisted (Phase 0 rule 27): its deployments are Demobilised by the job (as Phase 2 LC-8); items are not blacklisted automatically. Contractor Suspended: no new approvals; gate results per Phase 2 `suspended_contractor_gate`; certificates may still be submitted by HSE Officers (contractor users lose writes, Phase 0 rule 28).

### 5.4 Equipment certificates and configuration changes (EC, CF)
- EC-1. cert_no is unique per TPI (`CERT_EXISTS`); the same number reused on another item is a red flag shown to the reviewer (`CERT_NO_REUSED`, meta: existing item) and blocks Submit.
- EC-2. inspected_on ≤ issued_on ≤ today; a certificate whose computed valid_until (§6.1) is already < today is rejected `CERT_ALREADY_EXPIRED` (it may be attached to the history as "historic" by capability 107, never in force).
- EC-3. TPI acceptability per TP-4/TP-5 at inspected_on.
- EC-4. Independence per TP-6.
- EC-5. Every line's serial_as_printed normalised must equal the item's serial_norm (`SERIAL_MISMATCH`); a certificate cannot be moved to another item.
- EC-6. **Result:** `pass` or `pass_with_conditions` → line may be in force; `fail` → the certificate is still recorded (evidence), the line is never in force, the item becomes Out of Service (`failed_inspection`) and each failure reason becomes a category A defect unless the TPI classed it B or C.
- EC-7. Load test: required (performed = true, percent_of_swl ≥ 100.0) for lines of inspection_type `initial`, `after_configuration_change`, and `after_repair` with a structural repair, on cranes, hoists, mast climbers, BMUs and man-baskets (`LOAD_TEST_REQUIRED`) ASSUMPTION `VERIFY` R1/R10 percentages.
- EC-8. swl_t ≤ item.rated_capacity_t (`SWL_ABOVE_RATING`); a lower swl_t or a `derated_swl` limitation is a hard cap returned to Phase 3 (HK4-8).
- EC-9. An excavator, loader or telehandler with lifting_duty = true needs a certificate line with swl_t set and lifting duty certified; otherwise the provider returns not_met `LIFTING_DUTY_NOT_CERTIFIED` when Phase 3 uses it as `lifting_appliance`.
- EC-10. When a newer line for the same item (later inspected_on) becomes in force, the older line is Superseded; a newer **failed** line takes the item out of service even though the older line's date is still valid.
- EC-11. Limitations (list LIM) are returned with the provider result (`conditions[]`) and Phase 3 copies them into permit conditions (as LF-9 does for obstacle clearances); `no_personnel_lifting` on a crane makes LF-7 personnel lifts not_met `LIMITATION_CONFLICT`.
- EC-12. When `lifting_gear_colour_scheme.enabled`, lifting_accessory lines record colour_code; the provider returns the colour of the current period, and an accessory whose line colour ≠ current period colour returns not_met `COLOUR_CODE_OUT_OF_PERIOD` from the first day of the new period ASSUMPTION `VERIFY` R10.
- EC-13. The expiry job sets Expired when every line's valid_until < today; item status is recomputed.
- EC-14. Reviewer ≠ submitter (`SOD_CONFLICT`, 422 as DECISIONS #43); a contractor user cannot accept certificates.
- CF-1. **Configuration event** on a tower crane, construction hoist, mast climber or BMU (any event type), or a `major_repair` / `storm_exceedance` / `boom_configuration_change` on a mobile or crawler crane: every in-force line of the item becomes Suspended (`configuration_changed`) at occurred_at; the item is Quarantined; the provider returns not_met with **hard_stop** (HK4-3) until a certificate of inspection_type `after_configuration_change` (or `after_repair`) inspected on or after occurred_at is accepted and verified.
- CF-2. Configuration events cannot be back-dated more than 24 h (`BACKDATED_EVENT`); a climb recorded late alerts the HSE Manager.
- CF-3. The new line's configuration_ref must equal the event's new_configuration text, else review warning `CONFIGURATION_MISMATCH` (reviewer must confirm).
- CF-4. When a tower crane's configured height changes, the item's max_height_m is updated and Phase 2 obstacle clearances linked to the item are re-checked (OB-6: approved height still ≥ new height, otherwise Phase 2 shows `HEIGHT_CLEARANCE_REQUIRED`) ASSUMPTION via §11 link.

### 5.5 Scaffolds (SF)
- SF-1. Only scaffolds with tag_status green or yellow and tag_valid_until ≥ today may be used; the provider for `SCAFFOLD-TAG` maps Phase 3 `scaffold_tag_ref` / equipment_tag {scaffold, tag} to the scaffold register of the permit's project.
- SF-2. Design is required (design_ref) when height_m > `scaffold_design_height_m`, or scaffold_type ∈ {cantilever, suspended_hanging, loading_bay}, or load_class ≥ 4, or sheeting/netting is fitted ASSUMPTION `VERIFY` TG20; handover without it → `SCAFFOLD_DESIGN_REQUIRED`.
- SF-3. Erection crew members need in-force `SCAFFOLDER` (advanced for SF-2 design scaffolds) — evaluated at handover under the project's hook stage (transition: warning; block: `CREW_NOT_CERTIFIED`).
- SF-4. **Inspector**: the inspection's inspector_worker_id must hold an in-force `SCAFFOLD-INSPECTOR` certificate at inspected_at — this is a Phase 4 native rule and is enforced in every hook stage (`INSPECTOR_NOT_CERTIFIED`); for the handover inspection the inspector ≠ erection_supervisor ASSUMPTION (`SOD_CONFLICT`).
- SF-5. **Re-inspection triggers:** periodic — tag valid on local dates [inspection date, inspection date + `scaffold_inspection_interval_days` − 1]; after the last day tag_status = `expired`. Alteration started → red. "Require re-inspection" (capability 112) for a site/zone with reason (adverse weather, nearby impact, incident) and every Phase 2 ops event of type dust_sandstorm or thunderstorm_lightning on the site → tag_status `inspection_required` for every In Use scaffold in scope, immediately; a hard stop until a new inspection (HK4-3).
- SF-6. Yellow tags must state restrictions (e.g. "harness and lanyard required — guardrail removed at loading bay"); the provider returns met with reason `SCAFFOLD_YELLOW_TAG` and the restrictions in `conditions[]`; Phase 3 shows them as permit conditions.
- SF-7. Phase 3 WH-01 (access equipment inspected/tagged) remains the pre-shift check by the permit's competent person (OSHA 1926.451(f)(3)); the 7-day tag does not replace it.

### 5.6 Personnel certificates (PC)
- PC-1. The holder is a Phase 2 worker; a Contractor HSE Rep may submit only for workers with a deployment in their C scope (WK-11); HSE Officers for any worker with a deployment on their project.
- PC-2. (TPI, cert_type, cert_no) is unique (`CERT_EXISTS`); the same cert_no presented for another worker blocks Submit (`CERT_NO_REUSED`) and alerts the HSE Officer.
- PC-3. **ID match without storing the ID:** the submitter types the ID number shown on the card into `id_entered_for_match`; the server computes HMAC(id_type ‖ normalised number ‖ passport_country) with the Phase 2 blind-index key and compares it with the worker's id_number_bidx (and with bidx values of the worker's ID history, WK-9). Equal → `matched` / `matched_previous_id`; card shows no ID → `not_shown` (then VF-1 needs a method in {tpi_portal, tpi_qr_url, tpi_email, tpi_register_file} whose evidence shows the holder's name or photo); any other value → 422 `CERT_ID_MISMATCH` (nothing stored, attempt audited with masked value).
- PC-4. name_as_printed is compared with the worker's full_name_en/ar after Phase 0 rule 45 normalisation, token-wise: all tokens equal → exact; ≥ 2 tokens equal → partial; else none. `none` requires the reviewer to tick "identity confirmed by TPI" at Accept (`NAME_MISMATCH_CONFIRMATION`).
- PC-5. TPI acceptability per TP-4/TP-5 at issued_on (17024 or client_scheme scope ∋ cert_type).
- PC-6. valid_until per §6.2.
- PC-7. **Scope:** operator types require scope_categories ⊆ the type's allowed set; RADIOGRAPHER level I is rejected (`LEVEL_NOT_ACCEPTED`); scope is evaluated at use with the context (HK4-8): the equipment's category ∈ scope_categories, the equipment's rated_capacity_t ≤ max_capacity_t (when set), RIGGER level ≥ `rigger_level_critical_min` when the permit is critical, SCAFFOLDER advanced for SF-2 scaffolds — else not_met `CERT_SCOPE_MISMATCH` (meta: which).
- PC-8. Limitations `supervised_only` and `trainee_logbook` make the provider return not_met `CERT_LIMITATION` for key roles (crane_operator, rigger, signaller) on critical lifts; elsewhere met with the limitation in `conditions[]`.
- PC-9. A worker has at most one in-force certificate per type; a renewal becomes in force only when Accepted and verified, and then supersedes the older one (no gap: the older stays in force until then, within its own validity).
- PC-10. HSE suspension (capability 116; reason e.g. unsafe operation pending reassessment, involvement in a HiPo incident) is a hard stop; reinstatement by 116 with reason.
- PC-11. Phase 2 HK-8 stands: a Phase 4 certification ban or certificate revocation never changes worker status; the HSE Manager is prompted ("Consider a worker ban under capability 49?") but no ban is automatic.
- PC-12. **Trade requirement:** a Mobilised deployment whose trade maps in `trade_cert_requirements` without an in-force certificate of that type shows warning `TRADE_CERT_MISSING` on the deployment, counts against K-76, and alerts the Contractor HSE Rep; it is not a deployment block (access and permits are blocked through hooks).
- PC-13. medical_restriction_on_card = true is visible only to capability 119 holders and returns, for key roles, a provider result `met` with reason `CARD_RESTRICTION_REVIEW` until an HSE Officer records "restriction reviewed" (no detail) ASSUMPTION — Phase 6 owns medical fitness.

### 5.7 Verification (VF)
- VF-1. A certificate line (equipment) or certificate (personnel) is **in force** only when verification_status = `verified`, except that within `unverified_acceptance_hours` of Accept (default 0 = never) it may count as in force with warning `CERT_UNVERIFIED` (never for hook_critical_codes) ASSUMPTION (§10 Q3).
- VF-2. The verifier (capability 108) ≠ the submitter and is not employed by the certificate holder's employer or the equipment's owner contractor (`SOD_CONFLICT`).
- VF-3. Verification must use a channel registered on the TPI record (portal host, verification domain, email, phone); a channel not on the record is rejected `CHANNEL_NOT_REGISTERED`. Methods that count as verified: tpi_portal, tpi_qr_url, tpi_email, tpi_phone, tpi_register_file, client_register (client_scheme only). `original_sighted` is recorded but leaves the status not_verified.
- VF-4. **TPI QR codes:** a URL read from the TPI's own QR is stored in tpi_verification_url; if its host is not in the TPI's verification_domains the record shows warning `VERIFICATION_URL_FOREIGN_DOMAIN` (possible fake QR) and that URL cannot be used as the verification channel. The platform never fetches external URLs itself; the verifier opens the TPI page on their own device and records the outcome ASSUMPTION.
- VF-5. Outcome `no_response` twice ≥ 24 h apart sets `unable_to_verify`, alerts the HSE Manager and keeps the certificate not in force.
- VF-6. Outcome `not_found`, `details_differ` or `revoked_by_tpi` sets verification `failed`: Submitted → Rejected / Accepted → Revoked (`verification_failed`); every hook result for it is not_met with hard_stop; the HSE Manager is alerted; the action panel lists it for a decision (certification ban BL-4, equipment blacklist BL-3, TPI review BL-7). Raises E11 (§6.9).
- VF-7. Verification is repeated for each new certificate; a renewal is never "verified by inheritance".
- VF-8. **Platform sticker check (QR kind `EQ`):** any user with capability 121 (and gate devices, GE) scanning an EQ sticker sees the item category, tag, owner code, service status (colour), current certificate number, TPI code, valid_until, SWL and limitations — no personal data (inspector names omitted). A scan of a rotated/revoked token → `CREDENTIAL_REVOKED`.
- VF-9. **Personnel certification check (CK):** scanning a worker's Phase 2 access card (kind AC) in "certificates" mode, or entering a cert_no, shows the worker's name, worker_no, photo (as GC-7), and per certificate: type, cert_no, TPI code, valid_until, in force yes/no with reason, scope and non-medical limitations. Never ID numbers, scans, the medical flag or verification-failure details; logs `cert_check_view` and records no entry.

### 5.8 Defects, out of service, return to service (DF)
- DF-1. Categories (LOLER reg. 10 logic): **A** — existing or imminent danger: the item must not be used from raised_at; **B** — will become dangerous: rectify by due_date (§6.3); **C** — observation, no due date, reviewed at the next thorough examination.
- DF-2. Each defect on a TPI certificate line creates a Defect automatically with the TPI's category and due date; site users (capability 110) raise defects from pre-use checks, inspections, incidents, observations and PTW audits.
- DF-3. A category A defect sets the item Out of Service (`defect_a`) within 60 s: the sticker scan shows red "OUT OF SERVICE / خارج الخدمة", the provider returns not_met with hard_stop, Phase 3 suspends live permits using it (`hook_not_met`, SH-2) and Phase 2 denies gate entry for its vehicle (HOOK_NOT_MET). The physical red "Do not use" tag is applied by the raiser (checkbox `physical_tag_applied`, required).
- DF-4. A B defect not Closed by due_date sets the item Out of Service (`defect_b_overdue`) at due_date + 1 00:05 (job).
- DF-5. Rectification (capability 111) records what was done, by whom (OEM/contractor text) and evidence; it does not return the item to service.
- DF-6. **Return to service** (capability 112, user ≠ rectifier and not employed by the owner contractor): every A defect and overdue B defect is Closed; for A defects on cranes, hoists, mast climbers, BMUs, MEWPs, man-baskets and telehandlers/forklifts with structural, hydraulic-holding or safety-device defects, closure needs an accepted and verified certificate line of type `after_repair` inspected after rectification (`TPI_REINSPECTION_REQUIRED`); other defects close by HSE verification with photo evidence.
- DF-7. A category A defect on a lifting_accessory or tripod_winch cannot be rectified (`ACCESSORY_REPAIR_NOT_ALLOWED`): it is closed by "destroyed / returned to manufacturer" and the item is Retired (`retired_destroyed`) ASSUMPTION (ASME B30.9 removal criteria).
- DF-8. Manual tag-out (capability 110, any user in scope) is a stop-use act and is never blocked by any rule (as Phase 3 SH-1); it needs a reason ≥ 10 chars and notifies the owner's Contractor HSE Rep and HSE Officer.
- DF-9. A Phase 1 dangerous occurrence or incident whose agency is `crane_lifting_gear`, `mewp` or `scaffold` prompts the investigator to link or raise a Defect (not mandatory) ASSUMPTION; the defect stores source_ref = incident ref and does not change any Phase 1 field.
- DF-10. Defects never create Phase 1 corrective actions automatically; the HSE Officer may raise one (Phase 1 CA, new source_type `equipment_defect`, §11).

### 5.9 Suspension and blacklisting (BL)
- BL-1. Three subjects, three tools: **equipment** (tag-out §5.8 — temporary; blacklist — org-wide ban), **persons** (certificate suspension PC-10 — one certificate; certification ban — all or listed types, org-wide), **TPIs** (suspension — no new certificates; blacklist — certificates invalidated per scope).
- BL-2. Blacklisting and bans are HSE Manager only (capability 115), need reason_code + reason_text ≥ 20 chars, are audited and alert the affected contractor's HSE Rep and HSE Officers of every project where the subject is deployed.
- BL-3. **Equipment blacklist:** item → Blacklisted on every project; deployments Demobilised (job ≤ 60 s); tokens revoked; future registration of the same serial rejected (EQ-1); provider hard stop.
- BL-4. **Certification ban:** every certificate of the worker in the ban scope → hook not_met with hard_stop `CERT_HOLDER_BANNED`; new submissions of those types are rejected (`HOLDER_BANNED`); review_due_on reminder to the HSE Manager; lifting the ban does not restore revoked/rejected certificates.
- BL-5. Contractor HSE Reps see a ban only as "Certification not accepted on this organisation's projects / الشهادة غير مقبولة في مشاريع هذه الجهة" with no reason (P4-4).
- BL-6. **TPI suspended:** certificates inspected/issued on or after the suspension date are refused (TP-4); existing ones stay in force; contractors' new submissions show the TPI as "Not accepted".
- BL-7. **TPI blacklisted:** scope `all_certificates` → every certificate of the TPI is Revoked (`tpi_blacklisted`) at once; scope `issued_from` → those inspected/issued on or after blacklist_from are Revoked. Affected items become Quarantined, personnel certificates not in force (hard stop) within 60 s; Phase 3 detectors with calibration_body_id = the TPI and calibrated in scope are Quarantined. The HSE Officer gets a list of affected items and holders for re-certification.
- BL-8. Lifting a TPI blacklist returns it to Suspended; revoked certificates stay revoked.

### 5.10 Hook providers and the warn → block transition (HK4)
- HK4-1. **Provider registration:** Phase 4 registers providers for kinds `personnel_certificate` and `equipment_certificate` per project when the HSE Manager enables Phase 4 on the project (provider_registered_on = that local date). From then the Phase 2 result `not_evaluated` / `HOOK_NOT_AVAILABLE` is no longer produced for these kinds on that project.
- HK4-2. **Codes implemented** (exactly those already called by Phases 2–3, plus the Phase 4 additions marked +): personnel — CRANE-OPERATOR, RIGGER, SIGNALLER, BANKSMAN, GAS-TESTER, RADIOGRAPHER, ROPE-ACCESS, MEWP-OPERATOR, + FORKLIFT-OPERATOR, + TELEHANDLER-OPERATOR, + PLANT-OPERATOR, + HOIST-OPERATOR, + SCAFFOLDER, + SCAFFOLD-INSPECTOR, + LIFT-SUPERVISOR, + APPOINTED-PERSON-LIFTING, + AP-ELEC-LV, + AP-ELEC-HV, + CSE-STANDBY-CARD, + LOTO-AUTHORISED-CARD; equipment — CRANE-TPI, MEWP-TPI, FORKLIFT-TPI, TELEHANDLER-TPI, LIFTING-ACCESSORY-TPI, MAN-BASKET-TPI, SCAFFOLD-TAG, + HOIST-TPI, + PLANT-TPI, + RESCUE-WINCH-TPI, + PRESSURE-TPI. Any other code of these kinds → `unknown_code` (configuration error, shown to the HSE Manager; counts as not_met under block).
- HK4-3. **Hard stops** — the provider returns `not_met` with `hard_stop = true`, which blocks in **every** stage (Phase 2/3 treat it as not_met, §11): item Out of Service, Blacklisted or Retired; line Suspended for `configuration_changed`; scaffold tag red or `inspection_required`; certificate Revoked or verification failed; holder certification ban; certificate HSE-suspended (PC-10); TPI blacklisted. Rationale: these are positive knowledge of danger, not missing data.
- HK4-4. **Stages** (§4.8): Stage 1 `transition` — for codes not yet blocked, a `not_met` without hard_stop is returned to callers as status `warn` with reason `HOOK_NOT_MET_WARN` and the detail reason (e.g. CERT_EXPIRED, CERT_MISSING) — it never blocks; `met` and `expiring` are passed through. Stage 2 `block` — not_met (and unknown_code) block: Phase 2 `HOOK_NOT_MET` (gate DENY, eligibility not_met), Phase 3 blocker `HOOK_NOT_MET` (Issue/Revalidate/Resume blocked; an Active permit Suspended `hook_not_met` within 60 s, SH-2).
- HK4-5. **When the switch happens:** critical codes (`hook_critical_codes`) block from `critical_block_from` = provider_registered_on + `hook_critical_transition_days` (default 7); all other Phase 4 codes from `general_block_from` = provider_registered_on + `hook_transition_days` (default 30). The switch is automatic (job at 00:00:30 local on that date, actor null), audited and alerted. The HSE Manager (capability 124) may switch any code or all codes earlier at any time (stricter — always allowed).
- HK4-6. **Deferral:** general_block_from may be moved later once per project and kind, by ≤ 30 days, with a reason ≥ 30 chars (capability 124). Critical codes cannot be deferred (`CRITICAL_CODE_NO_DEFERRAL`); a second deferral → `DEFERRAL_USED`; returning a blocked code to warn → `HOOK_POLICY_LOOSENING`.
- HK4-7. **Readiness report** (capability 122): per code, n(subjects requiring it) and n(in force), list of not-met subjects with reason, and a preview of live permits/WAPs/gates that the block will affect. Shown from provider registration; it never prevents the switch.
- HK4-8. **Context** (§11 HK-3 extension): callers pass {project_id (required for equipment_tag subjects), zone_id, permit_id, critical, use, equipment_ref (vehicle_id | equipment_tag), rated_capacity_t, operator_worker_id}. The equipment provider resolves vehicle_id → item via vehicle link and {category, tag} → the project's deployment by tag with category mapping EQ→EQC (else not_met `EQUIPMENT_NOT_REGISTERED` / `CATEGORY_MISMATCH`), then checks in this order: blacklist/retired → out of service → deployment Approved or On Site on the project (`EQUIPMENT_NOT_DEPLOYED`) → arrival inspection (EM-3) → line in force at `at` (`CERT_MISSING`, `CERT_EXPIRED`, `CERT_UNVERIFIED`, `CERT_SUSPENDED`, `CERT_REVOKED`) → context checks (rated_capacity_t ≤ certified swl/derated limit → else `SWL_LIMITATION`; use = personnel_lift vs `no_personnel_lifting` → `LIMITATION_CONFLICT`; lifting duty EC-9; colour EC-12). The personnel provider checks: ban → certificate in force (`CERT_MISSING`, `CERT_EXPIRED`, `CERT_UNVERIFIED`, `CERT_SUSPENDED`, `CERT_REVOKED`, `CERT_ID_MISMATCH` never stored, so only valid records exist) → scope with context (PC-7, PC-8). Result: {status, valid_until, ref (cert_no), reason_code, hard_stop, conditions[], swl_t}.
- HK4-9. **Operator binding:** for an equipment line whose category has an operator code (list EQC), Phase 3 names the operator (`operator_worker_id`, §11) and calls the personnel provider for that code with context equipment_ref, so a mobile-crane card does not cover a tower crane and a 50 t card does not cover a 60 t crane.
- HK4-10. **Events:** Phase 4 publishes `cert.status_changed`, `equipment.status_changed`, `scaffold.tag_changed`, `holder.ban_changed`, `tpi.status_changed`, `hook_policy.changed`, delivered at least once within 60 s; Phase 2 and Phase 3 re-evaluate affected credentials, WAPs and permits on them (§11). Provider results may be cached ≤ 60 s (HK-5) and the cache is cleared on these events.
- HK4-11. valid_until returned by the equipment provider joins Phase 2 AVP effective validity (HK-5, X3) as `equipment_certificate` limiting factor; the expiry of the certificate therefore suspends the AVP by dependency (LC-6) and reinstates it on renewal.
- HK4-12. Default attach points added by Phase 4 (seeded, HSE Manager editable, tighten only): Phase 2 VC excavator, wheel_loader → `PLANT-TPI`; Phase 2 WAP crew_role banksman → `BANKSMAN` (already in HK-2 example; now seeded); Phase 3 crew role banksman → `BANKSMAN`; Phase 3 EQ tripod_winch → `RESCUE-WINCH-TPI`, mast_climber/bmu → `HOIST-TPI`; Phase 3 operator binding per HK4-9.

### 5.11 Imports (IM)
- IM-1. Two templates (header row in EN or AR, order free, case-insensitive), `.csv` (UTF-8, comma or semicolon) or `.xlsx` (first sheet), ≤ 5 MB, ≤ 5,000 rows; dry-run first, commit only a Validated batch ≤ 60 min old, as Phase 1 §3.2.
- IM-2. **Equipment certificates** columns: project_code, tag (or equipment_no), category, manufacturer, serial_no, tpi_code, cert_no, inspection_type, inspected_on, issued_on, printed_next_due, result, swl_t, load_test_pct, limitations (`code:value;…`), defects (`A|B|C:text;…`), colour_code. Rows sharing (tpi_code, cert_no) form one multi-line certificate. Unknown tag + `create_items = Y` (HSE Officer only) creates Awaiting Certificate items and Planned deployments.
- IM-3. **Personnel certificates** columns: worker_no **or** (id_type, id_number[, passport_country]) for lookup, cert_type, tpi_code, cert_no, issued_on, printed_expiry, scope_categories, max_capacity_t, level, limitations, name_as_printed, id_on_card (`same_as_lookup` / blank / number). ID numbers in the file are used only for blind-index lookup and PC-3 matching.
- IM-4. Files with an ID column are sensitive: stored encrypted, deleted at commit, discard or expiry; the dry-run report masks IDs (WK-4) and shows worker_no.
- IM-5. Committed rows create certificates in status Submitted (never Accepted): each still needs review (107) and verification (108). Scans from scans_zip are attached by cert_no; rows without a scan stay Draft.
- IM-6. Source `tpi_register_file` (capability 120 for HSE Officer/Manager only): the evidence file must be an email from one of the TPI's verification_domains; committed certificates receive a verification record method `tpi_register_file`, outcome confirmed, reference = evidence sha256, performed_by = importer (VF-2 still applies against the holder's employer/owner); they are still reviewed.
- IM-7. **Validation codes** (errors block the row; a file-level error blocks the file):

| Code | Level | Condition |
|---|---|---|
| E01 | error | project_code unknown or not the batch project |
| E02 | error | tag/equipment_no unknown and create_items ≠ Y; worker not found by worker_no / blind index |
| E03 | error | category not in EQC, or not matching the item; cert_type not in PCT |
| E04 | error | tpi_code unknown, or TPI not acceptable at the date (TP-4/TP-5, meta reason) |
| E05 | error | serial_no ≠ item serial (EC-5) |
| E06 | error | duplicate (tpi_code, cert_no[, line]) within the file or in the DB (EC-1/PC-2) |
| E07 | error | date order invalid (EC-2) or certificate already expired |
| E08 | error | result not pass/pass_with_conditions/fail; swl_t > rated capacity |
| E09 | error | id_on_card does not match (PC-3) |
| E10 | error | row outside the uploader's scope (engagement / worker deployment) |
| E11 | error | holder banned or item blacklisted |
| E12 | error | unparseable date/number; missing required column (whole file rejected) |
| W01 | warning | printed date beyond the platform interval/cap (valid_until will be shortened) |
| W02 | warning | name_as_printed match `none` or `partial` |
| W03 | warning | no scan in the zip for this cert_no (row stays Draft) |
| W04 | warning | TPI accreditation expires within 30 days |
| W05 | warning | same file_sha256 already committed on this project |
| W06 | warning | certificate expires within 30 days |

### 5.12 Gate equipment check (GE)
- GE-1. Gate-check endpoints (Phase 2 GC-1/GC-2) accept QR kind `EQ` (and typed printed_ref `<project>-<tag>`) at every gate type; gate devices use their existing capability 74.
- GE-2. Checks in order, first DENY reason first: `TOKEN_UNKNOWN` · `OUT_OF_SCOPE` (deployment of another project / caller scope, as GC-13) · `CREDENTIAL_REVOKED` (rotated, demobilised or retired token) · `EQUIPMENT_BLACKLISTED` · `EQUIPMENT_NOT_DEPLOYED` (no non-demobilised deployment on the project) · `EQUIPMENT_NOT_APPROVED` (deployment Planned) · `CONTRACTOR_SUSPENDED` / `CONTRACTOR_BLACKLISTED` (per Phase 2 setting) · `EQUIPMENT_OUT_OF_SERVICE` · `EQUIPMENT_QUARANTINED` (detail = SSR reason). WARN: `EXPIRING_7D`, `ARRIVAL_INSPECTION_DUE`, `ALSO_SCAN_VEHICLE_STICKER`. These are Phase 4 native checks on Phase 4 records and apply in every hook stage (equipment gets a sticker only after EM-2).
- GE-3. Direction `in` on an Approved deployment sets On Site and arrived_at; `out` never denies and logs EXIT_RECORDED.
- GE-4. When the item is linked to a Phase 2 vehicle and the gate protects zones with avp_area_required or access_permit_required, the result adds `ALSO_SCAN_VEHICLE_STICKER`: the Phase 2 vehicle check (GC-9) remains the access decision for the vehicle; the EQ scan is the certification decision. A DENIED EQ result with a GRANTED vehicle scan is still a denial for the equipment (the guard sees both).
- GE-5. The result screen shows category, tag, owner code, status colour, certificate no., TPI code, valid_until, SWL, limitations; no personal data.
- GE-6. Every EQ check writes a Phase 2 gate-log row with subject type `equipment_deployment` (§11); EQ checks are **excluded** from K-52/K-53 (people and vehicle access) and reported in the equipment gate log.
- GE-7. `admitted_despite_denial` (GC-14) applies to EQ checks with the same alerts.

### 5.13 KPIs and AI (KC)
- KC-1. All certification KPIs are computed by the backend (Phase 1 D-1).
- KC-2. Population date = as_of end of day (local); "on site" = deployment status On Site at as_of; "in force" per §6.6.
- KC-3. Contractor attribution: equipment → deployment engagement; personnel → the worker's deployment engagement on the project; defects → the item's deployment engagement at raised_at; filter with descendants as Phase 1 K-R5.
- KC-4. AI tool **T16 `get_certification_kpis`** (project_ids, period, filters {site, zone, engagement, include_descendants, category, cert_type}, metrics K-72…K-81, group_by {category, cert_type, contractor, tpi, defect_category, reason_code, month}) returns aggregates only. Equipment tags and TPI codes may appear in group rows; **no names, worker_no, cert numbers, ID data, ban reasons or verification-failure details** (AI-5). T13 also returns E10–E11.
- KC-5. Viewer/Client sees certification KPIs, counts and expiring-item counts as aggregates only.

### 5.14 PDPL (P4-x, extends P1–P13, P1-x, P2-x, P3-x)
- P4-1. Classes as in §3. **Sensitive:** personnel certificate scans (front/back — they show ID numbers and photos), medical_restriction_on_card, verification records with outcome not_found/details_differ on personnel certificates (suspected forgery), certification-ban reason and status, import files with ID columns. **Personal:** holder names, cert numbers, scope, dates, levels, limitations, name/ID match results, inspector names, verifier/reviewer identities, defect raisers, TPI contact person.
- P4-2. **No second copy of ID numbers:** ID numbers on certificates are matched through the Phase 2 blind index (PC-3) and never stored; only the match result is kept.
- P4-3. Scans live in the encrypted personal bucket (Phase 2 P2-2), are served by signed URLs ≤ 5 min only to capability 119 with a reason (`verification`, `authority_request`, `incident_investigation`, `client_audit`, `other`+text), each opening writes `sensitive_field_read` (fields_read ["cert_scan"]); never in bulk exports or AI inputs.
- P4-4. Suspected-forgery and ban details are shown only to hse_manager and hse_officer; all other roles see "Certificate not accepted / الشهادة غير مقبولة" or BL-5 text. The platform draws no criminal-law conclusion; reporting to authorities is a legal decision outside the platform (legal exposure: R13).
- P4-5. **Legal exposure — blacklisting persons and TPIs:** a ban affects a person's employment and a TPI's business. Required: factual reason_text, HSE Manager decision, review_due_on (≤ `ban_review_months`), the holder's employer informed only of the BL-5 text, data-subject access through Phase 0 P8 (the person may see the ban, its date and reason code). TPI status shown to contractors as "Not accepted / غير مقبولة" without reason.
- P4-6. Minimisation: limitations are non-medical codes only; a medical restriction is recorded as a flag without detail (Phase 6 owns fitness); no date of birth, nationality or photo is copied from cards (the photo stays on the Phase 2 worker).
- P4-7. Retention: certificate metadata follows the worker (Phase 2 P2-7 — anonymised with the worker; cert_no and holder name removed, type/validity kept for statistics); scans are deleted `cert_scan_retention_years` after the certificate ends (Expired/Superseded/Revoked/Rejected) unless linked to an incident (then Phase 1 P1-5); equipment records are not personal and follow project retention + `ptw_retention_years`.
- P4-8. Permit prints, gate screens, sticker checks and alerts carry no ID numbers, scans, medical flags or ban reasons (P3-2).
- P4-9. Phase 1 P1-8 ID scan applies to every Phase 4 free-text field.

### 5.15 Permission matrix — Phase 4 extension (continues Phase 3 §5.14; legend A/P/S/C/C1/R/—)

| # | Capability | HSE Mgr | HSE Officer | Site Eng/Sup | Permit Issuer | Permit Receiver | Contractor HSE Rep | Viewer/Client |
|---|---|---|---|---|---|---|---|---|
| 105 | View equipment register, deployments, equipment certificates, scaffolds, defects, TPI list (no personal data) | A | P | S | S | C1 | C | P (R) |
| 106 | Register/edit equipment items, deployments, scaffolds; submit equipment certificates; record configuration events | A | P | S (scaffolds, configuration events) | — | — | C | — |
| 107 | Review / accept / return / reject certificates (equipment and personnel); record TPI revocation | A | P | — | — | — | — | — |
| 108 | Record verification with the TPI | A | P | — | — | — | — | — |
| 109 | Approve mobilisation, record arrival and arrival inspection, demobilise | A | P | S (arrival, arrival inspection) | — | — | C (demobilise own) | — |
| 110 | Raise defect / tag out equipment or scaffold (stop use) | A | P | S | S | C1 | C | — |
| 111 | Record rectification | A | P | S | — | — | C | — |
| 112 | Close defect / return to service; retire item; require scaffold re-inspection | A | P | — | — | — | — | — |
| 113 | Record scaffold inspection (inspector must hold SCAFFOLD-INSPECTOR, SF-4) | A | P | S | — | — | C | — |
| 114 | Create / edit / submit TPI organisations, accreditations, client approvals | A | P | — | — | — | — | — |
| 115 | Approve / suspend / blacklist / lift TPI; blacklist / lift equipment; certification ban / lift | A | — | — | — | — | — | — |
| 116 | Suspend / reinstate a certificate | A | P | — | — | — | — | — |
| 117 | View personnel certificates (also needs 46; ID shown only as match result) | A | P | S | S | C1 | C | — |
| 118 | Submit personnel certificates | A | P | — | — | — | C | — |
| 119 | Open personnel certificate scans; see medical-restriction flag (audited, reason) | A | P | — | — | — | C ASSUMPTION (§10 Q12) | — |
| 120 | Import certificates (dry-run, commit); `tpi_register_file` source | A | P | — | — | — | C (contractor_file only) | — |
| 121 | Certification check (EQ sticker, AC card in certificates mode, cert_no lookup) | A | P | S | S | C1 | C | — |
| 122 | View certification KPIs, expiring items, action panel, readiness report | A | P | S | S | C1 | C | P (aggregates) |
| 123 | Export certification registers (IDs never; names only with 46) | A | P | S | — | — | C | P (no names) |
| 124 | Edit Phase 4 settings and reference lists (tighten only); early hook switch; one deferral | A | — | — | — | — | — | — |

Gate devices: capability 74 covers EQ scans at their gate. Suspended-contractor users keep reads and lose writes (Phase 0 rule 28).

## 6. Calculations

All dates local Asia/Riyadh (Phase 0 K2). `add_months` as Phase 2 §6.1 (clamped to month end). Rounding half-up at output (Phase 1 K-R8); comparisons on unrounded values.

### 6.1 Equipment certificate line validity (strictest-wins)
interval_end = add_months(inspected_on, equipment_interval_months[category]) − 1 day (scaffolds §6.4).
valid_until = min(printed_next_due, interval_end), where printed_next_due is read as the last valid day as printed (ASSUMPTION); null printed_next_due → interval_end. limiting_factor = the term giving the minimum (`printed_next_due` on a tie).
days_left = valid_until − today.

### 6.2 Personnel certificate validity
cap_end = add_months(issued_on, personnel_cert_cap_months[cert_type]) − 1 day; valid_until = min(printed_expiry, cap_end); null printed_expiry → cap_end; limiting_factor as §6.1.

### 6.3 Defect due date
B: due_date = min(tpi_due_date (if set), raised local date + `defect_b_max_days`); when neither the TPI nor the raiser gives a date: raised date + `defect_b_default_days`. Out of Service at due_date + 1 00:05 if not Closed. A: due "immediately" (no due_date). C: none.

### 6.4 Scaffold tag validity
tag_valid_until = inspection local date + `scaffold_inspection_interval_days` − 1 (green/yellow results); red → none. tag_status = expired when today > tag_valid_until.

### 6.5 Hook block dates
critical_block_from = provider_registered_on + `hook_critical_transition_days`; general_block_from = provider_registered_on + `hook_transition_days` (+ deferral ≤ 30 days). Block starts at 00:00 local on that date (job 00:00:30).

### 6.6 In-force predicates
- Equipment line in force at local date d: certificate status Accepted ∧ line result ∈ {pass, pass_with_conditions} ∧ (verification verified ∨ VF-1 window) ∧ inspected_on ≤ d ≤ valid_until ∧ not superseded by a later line (EC-10) ∧ TPI not blacklisted in scope.
- **Item has a valid certificate** (for K-72) = some line in force. **Item usable** (provider met, In Service) = valid certificate ∧ service_status ∉ {out_of_service, blacklisted, retired} ∧ no CF-1 suspension ∧ (on a project) arrival inspection passed.
- Personnel certificate in force at d: status Accepted ∧ verified (or VF-1 window, never for critical codes) ∧ issued_on ≤ d ≤ valid_until ∧ no active ban covering the type ∧ TPI not blacklisted in scope.
- Expiring = in force ∧ valid_until ≤ d + 7 (as Phase 2 ZP-3).

### 6.7 KPI catalogue (continues Phase 3 §6.11)

| ID | Metric (EN / AR) | Formula | Unit / display | Better |
|---|---|---|---|---|
| K-72 | **Equipment certificate compliance** / نسبة المعدات بشهادات سارية | n(On Site deployments at as_of, category ≠ scaffold, item has a valid certificate) ÷ n(On Site deployments at as_of, category ≠ scaffold) × 100; denominator 0 → "—"; breakdown by category | %, 1 dp | higher |
| K-73 | Equipment certificates expiring ≤ 30 days / شهادات معدات تنتهي خلال 30 يوماً | n(On Site items with a valid certificate whose valid_until ∈ [as_of, as_of + 30]) by category | count | lower |
| K-74 | **Out-of-service equipment** / المعدات خارج الخدمة | n(On Site deployments whose item is Out of Service at as_of); plus n(category A defects raised in period) | count; count | lower |
| K-75 | **Inspections overdue** / الفحوص المتأخرة | equipment: n(On Site deployments whose latest line's valid_until < as_of and no line in force); scaffolds: n(In Use scaffolds with tag_status expired at as_of) | count · count | lower |
| K-76 | **Personnel certification compliance** / نسبة الأفراد بشهادات سارية | n(Mobilised contractor-worker deployments at as_of whose trade maps in `trade_cert_requirements` and whose worker holds an in-force certificate of the mapped type) ÷ n(those deployments) × 100; breakdown by type | %, 1 dp | higher |
| K-77 | Personnel certificates expiring ≤ 30 days / شهادات أفراد تنتهي خلال 30 يوماً | n(in-force certificates of workers Mobilised on the project with valid_until ∈ [as_of, as_of + 30]) by type | count | lower |
| K-78 | **Blacklisted / banned** / المحظورون | at as_of: equipment Blacklisted with any deployment on the project · workers with an active certification ban and any deployment on the project · TPIs Blacklisted (org-wide) | count · count · count | — |
| K-79 | Verification timeliness / الالتزام بمهلة التحقق | n(certificates submitted in period with a conclusive verification (confirmed, not_found, details_differ, revoked_by_tpi) within `verification_due_days` of submission) ÷ n(certificates submitted in period, excluding those whose due window has not ended at as_of and are still unverified) × 100; plus n(failed verifications in period) | %, 1 dp; count | higher; lower |
| K-80 | **Defect rectification on time** / إصلاح العيوب في الموعد | n(B defects with due_date in period and ≤ as_of, Closed with closure local date ≤ due_date) ÷ n(B defects with due_date in period and ≤ as_of, not Cancelled) × 100 | %, 1 dp | higher |
| K-81 | **Scaffold tag compliance** / امتثال بطاقات السقالات | n(In Use scaffolds at as_of with tag_status green or yellow) ÷ n(In Use scaffolds at as_of, excluding Closed (Red) and Under Erection/Alteration) × 100 | %, 1 dp | higher |

### 6.8 Readiness (report only, HK4-7)
readiness_pct(code) = n(subjects requiring code with provider status met or expiring) ÷ n(subjects requiring code) × 100, subjects = On Site items of the code's categories (equipment) or Mobilised workers whose trade maps to the code plus workers named in a crew role with that hook on a non-terminal permit or Active WAP (personnel).

### 6.9 Leading-indicator warnings (extend Phase 1 §6.9; monthly job day 2, per project and per tier-1 tree)
- **E10** at the end of month M: K-72 < `equipment_cert_warning_pct` **or** K-76 < `personnel_cert_warning_pct` **or** K-81 < `scaffold_tag_warning_pct` (unrounded).
- **E11** in M: ≥ 1 failed verification (not_found / details_differ) **or** n(category A defects raised) ≥ `dangerous_defect_warning_count`.

### 6.10 Worked examples (exact; backend unit tests must match)

**Z1 — equipment validity and alerts.** (a) SH-MEWP-12 (MEWP, interval 6): inspected 2026-09-02, printed next due 2027-09-01 → interval_end = add_months(2026-09-02, 6) − 1 = **2027-03-01**; valid_until = min(2027-09-01, 2027-03-01) = **2027-03-01**, limiting `category_interval`; alerts 30/14/7/0 on **2027-01-30, 2027-02-15, 2027-02-22, 2027-03-01**; Quarantined 2027-03-02 00:05 without a new line. (b) RW-MC-03 (VEH-0003, mobile crane, interval 12): inspected 2025-11-06, printed 2026-11-05 → interval_end 2026-11-05 → valid_until **2026-11-05** (tie → `printed_next_due`); on 2026-10-06 days_left = **30** → 30-day alert today. (c) Month-end: a forklift inspected 2026-08-31 with no printed date → add_months(2026-08-31, 12) = 2027-08-31 → valid_until **2027-08-30**. (d) NAJD accessory batch AICC-EQ-TEST-26-0914 inspected 2026-09-14, printed 2027-09-13 → interval 6 → **2027-03-13** for all 38 lines.

**Z2 — personnel validity caps.** (a) Joel Bautista RIGGER: issued 2023-10-21, printed 2026-10-20, cap 36 → cap_end 2026-10-20 → **2026-10-20**; on 2026-10-06 days_left **14** → 14-day alert; PTW-RBT-52-2026-0290 on 2026-10-07 → met (13 days > 7); a permit shift on 2026-10-14 → `expiring` (6 days) → Phase 3 warning EXPIRING_7D; on 2026-10-21 → not_met CERT_EXPIRED. (b) A FORKLIFT-OPERATOR card issued 2025-02-10 printed 2030-02-09 (5 years) → cap 36 → **2028-02-09**, limiting `cap`, import warning W01. (c) Salem Al-Harthi GAS-TESTER issued 2026-04-20, printed 2028-04-19, cap 24 → **2028-04-19**. (d) Imran Hussain SCAFFOLDER issued 2021-10-11, printed 2026-10-10, cap 60 → **2026-10-10**; renewal DSPC-SC-TEST-26-1002 submitted 2026-10-04 08:30 → verification due 2026-10-07; if verified 2026-10-06 it supersedes the old card on that day.

**Z3 — tower crane configuration change (TC-01, RBT-52).** Line NKTI-TEST-26-0118 (erection, inspected 2026-01-18, printed 2027-01-17) in force. Climb event 2026-09-28 14:00 → line Suspended `configuration_changed` at 14:00, item Quarantined, provider not_met hard_stop → any live lifting permit on TC-01 Suspended `hook_not_met` within 60 s, in every hook stage. Certificate NKTI-TEST-26-0929 (after_configuration_change, inspected 2026-09-29, load test 110.0 %, configuration "HUH 236.00 m, jib 60 m, 9 tie-ins", printed 2027-09-28) accepted 2026-09-29 15:40 and verified 16:00 → in force from **2026-09-29 16:00**, valid_until = min(2027-09-28, add_months(2026-09-29, 12) − 1 = 2027-09-28) = **2027-09-28**. A certificate inspected 2026-09-27 (before the event) cannot clear it (`INSPECTION_BEFORE_EVENT`).

**Z4 — hook stages (ANIA-EXP, provider registered 2026-10-01).** critical_block_from = 2026-10-01 + 7 = **2026-10-08**; general_block_from = 2026-10-01 + 30 = **2026-10-31**. (a) Fixture lifting permit with a chain sling whose line expired 2026-10-03 (LIFTING-ACCESSORY-TPI, critical): on 2026-10-06 → warning `HOOK_NOT_MET_WARN` (CERT_EXPIRED), Issue allowed; on 2026-10-08 → blocker `HOOK_NOT_MET`. (b) Fixture excavator with an expired PLANT-TPI line on a WAP vehicle: warn until 2026-10-30; gate DENIED `HOOK_NOT_MET` from 2026-10-31. (c) RW-MEWP-07 (Out of Service, A defect) on a WAH permit on 2026-10-06 → `HOOK_NOT_MET` (hard stop) although in transition. (d) Deferral of general_block_from to the maximum: 2026-10-31 + 30 = **2026-11-30**; a second deferral → `DEFERRAL_USED`; deferring CRANE-OPERATOR → `CRITICAL_CODE_NO_DEFERRAL`.

**Z5 — defect dates.** (a) DEF-ANIA-EXP-2026-0005 (B, TPI due 2026-10-31) raised 2026-09-24 → due = min(2026-10-31, 2026-09-24 + 30 = 2026-10-24) = **2026-10-24**; Out of Service 2026-10-25 00:05 if not Closed. (b) B raised 2026-10-06 with TPI due 2026-10-20 → **2026-10-20**. (c) B raised 2026-10-06 with no date → + 14 = **2026-10-20**. (d) A on sling WRS-NJ-0117 (from INC-ANIA-EXP-2026-0150, 2026-09-11) → item Retired `retired_destroyed` 2026-09-12; repair attempt → `ACCESSORY_REPAIR_NOT_ALLOWED`.

**Z6 — scaffold tags.** SC-0142 (SCF-ANIA-EXP-0142) inspected green 2026-10-01 → tag valid **2026-10-01…2026-10-07**; 2026-10-08 → expired → SCAFFOLD-TAG not_met `SCAFFOLD_INSPECTION_OVERDUE` (warn in transition until 2026-10-30, as SCAFFOLD-TAG is not a critical code). "Require re-inspection" on S-LAND at 2026-10-06 10:30 (adverse weather) → SC-0142 tag_status `inspection_required` at 10:30 → hard stop; Ferdinand Reyes inspects green at 13:10 → tag valid **2026-10-06…2026-10-12**.

**Z7 — scope matching.** Zaheer Abbas CRANE-OPERATOR [mobile_crane, crawler_crane] ≤ 60.000 t: RW-MC-03 (mobile, 50.000 t) → **met** (valid_until 2027-03-31); TC-01 (tower) → not_met `CERT_SCOPE_MISMATCH` (category); DL-MC-01 (mobile, 60.000 t) → scope met (60 ≤ 60); a 70.000 t crane → `CERT_SCOPE_MISMATCH` (capacity). Ali Hassan [tower_crane] ≤ 16.000 t: TC-01 12.000 t → **met**. Riggers on critical PTW-0290 (min level 2): Joel level 2 → met; Osman Idris level 1 on a critical lift → `CERT_SCOPE_MISMATCH` (level); on a routine lift → met.

**Z8 — TPI acceptability by date.** NKTI 17020 accreditation valid to **2026-11-02**: a line inspected 2026-11-02 → accepted; inspected 2026-11-03 with no renewal → 422 `TPI_NOT_ACCEPTABLE` (`TPI_ACCREDITATION_INVALID`); NJ-MC-02 (to 2027-03-15) and TC-01 (to 2027-09-28) stay in force with note "TPI accreditation since lapsed" (TP-7). Accreditation alerts: 2026-10-03 (30 days), **2026-10-19** (14), 2026-10-26 (7), 2026-11-02 (0). QUICKCERT blacklisted 2026-09-20 (all_certificates) → GP-FL-03 line QC-EQ-TEST-26-0042 Revoked 2026-09-20 → Quarantined; AICC line inspected and verified 2026-09-23 → In Service 2026-09-23.

**Z9 — ID match.** Card for Zaheer shows 2000001019 → HMAC = WKR-000019 bidx → `matched`; a typed 2000001091 → 422 `CERT_ID_MISMATCH`, nothing stored, audit shows `2*******91`. A card issued when the worker held passport TEST00019 and now Iqama → `matched_previous_id`.

**Z10 — AVP link.** VEH-0003 AVP AVP-OEXX-26-0120: own 2027-03-31, istimara 2027-05-31, insurance 2027-05-31, MVPI 2027-02-28, CRANE-TPI valid_until 2026-11-05 → AVP effective validity **2026-11-05**, limiting factor `equipment_certificate` (HK4-11); Phase 2 30-day alert on 2026-10-06.

**Z11 — KPI fixture = seed, September 2026 (as_of 2026-09-30).**

| Metric | ANIA-EXP calculation | ANIA-EXP | RBT-52 calculation | RBT-52 |
|---|---|---|---|---|
| K-72 | 181 ÷ 186 × 100 = 97.311… (not valid: 2 expired, 2 unverified, 1 failed inspection) | **97.3 %** | 49 ÷ 50 × 100 (DL-MC-01 expired) | **98.0 %** |
| K-73 | | **11** | | **4** |
| K-74 | Out of Service 3 (RW-MEWP-07, failed-inspection telehandler, 1 bulk B-overdue); A defects raised in Sep 4 | **3 · 4** | | **0 · 0** |
| K-75 | equipment 2; scaffolds 3 | **2 · 3** | equipment 1 (DL-MC-01); scaffolds 0 | **1 · 0** |
| K-76 | 209 ÷ 220 × 100 (crane_operator 14, rigger 46, scaffolder 160) | **95.0 %** | 46 ÷ 48 × 100 = 95.833… (6 / 18 / 24) | **95.8 %** |
| K-77 | | **17** | | **5** |
| K-78 | equipment 1 (SH-TH-02), persons 1 (Nadeem Akhtar), TPIs 1 (QUICKCERT) | **1 · 1 · 1** | | **0 · 0 · 1** |
| K-79 | 131 ÷ 148 × 100 = 88.513…; failed 1 | **88.5 % · 1** | 37 ÷ 40 × 100; failed 0 | **92.5 % · 0** |
| K-80 | 10 ÷ 12 × 100 = 83.333… | **83.3 %** | 3 ÷ 3 × 100 | **100.0 %** |
| K-81 | 93 ÷ 96 × 100 = 96.875 | **96.9 %** | 22 ÷ 22 × 100 | **100.0 %** |

Expected warnings Sep 2026: **E10 ANIA-EXP** (K-72 97.3 % < 98.0; K-76 = 95.0 % is not < 95.0; K-81 96.9 % ≥ 95.0); no E10 RBT-52 (98.0 % is not < 98.0). **E11 ANIA-EXP** (1 failed verification; A defects 4 ≥ 3); no E11 RBT-52. Both are raised once for the project and once for the RAWABI tree (DECISIONS #53).

**Z12 — rounding edges.** K-72 197 ÷ 200 = 98.5 → **98.5 %**; 1,961 ÷ 2,000 = 98.05 → **98.1 %** (half-up); E10 compares the unrounded 98.05 with 98.0 → no warning; 1,959 ÷ 2,000 = 97.95 → displayed **98.0 %** but E10 **raised** (97.95 < 98.0).

## 7. Alerts & expiries

Channels as Phase 1/2/3: in-app and email in the recipient's language; SMS where marked (ASSUMPTION). Workers have no accounts, so alerts about a holder go to the Contractor HSE Rep of the worker's engagement (C scope) and to the HSE Officers of every project where the worker is Mobilised. Alert texts carry the equipment tag or worker_no, type or category, reference number and reason. They never carry ID numbers, scan links, the medical flag, ban reasons or verification-failure details (P4-4). Recipients with capability 46 see names. The long schedule is `alert_schedule_long_days` = 30 / 14 / 7 / 0 days before the last valid day, sent at 07:00 local (Phase 2 convention). Each step is sent once; if a renewal comes into force, the steps still to come are cancelled.

| Trigger | Recipient | Timing | Channel |
|---|---|---|---|
| Equipment certificate line expiry (valid_until) | Owner contractor's HSE Rep; HSE Officer at 7 and 0; HSE Manager at 0 for critical-code categories | 30 / 14 / 7 / 0 days | In-app + email |
| Item Quarantined by expiry (EC-13) | Owner's HSE Rep; HSE Officer; receivers and issuers of live permits naming the item | At 00:05 on valid_until + 1 | In-app + email |
| Personnel certificate expiry | Engagement's HSE Rep; HSE Officer at 7 and 0 | 30 / 14 / 7 / 0 days | In-app + email |
| Personnel certificate expiring while the holder is named on a permit or WAP crew | Receiver; Contractor HSE Rep | When the permit or WAP is created or changed, if valid_until ≤ its end (Phase 3 EXPIRING_7D still applies) | In-app |
| TPI accreditation expiry (TP-8) | HSE Officers; HSE Manager | 30 / 14 / 7 / 0 days | In-app + email |
| TPI client approval expiry | HSE Officers; HSE Manager | 30 / 14 / 7 / 0 days | In-app + email |
| Certificate submitted (review queue) | HSE Officers of the project | Immediately; reminder at 24 h | In-app |
| Verification due (`verification_due_days` after submission) | HSE Officers; HSE Manager when overdue | 1 day before; on the due day; daily while overdue | In-app + email |
| Verification `unable_to_verify` (VF-5) | HSE Manager; HSE Officers | Immediately | In-app + email |
| Verification failed (VF-6) | HSE Manager; HSE Officers; Contractor HSE Rep (message: "Certificate not accepted / الشهادة غير مقبولة", no detail) | Immediately | In-app + email + SMS (HSE Manager) |
| Certificate returned or rejected | Submitter | Immediately | In-app |
| Scaffold tag expiry (SF-5) | Scaffold's engagement HSE Rep; site engineer of the zone | The day before tag_valid_until (07:00); on tag_valid_until (07:00) | In-app (+ push) |
| Scaffold tag turned red or `inspection_required` | Engagement HSE Rep; HSE Officer; receivers of live permits whose scaffold_tag_ref is that scaffold | Within 60 s | In-app + email |
| Category A defect raised or item tagged out (DF-3/DF-8) | Owner's HSE Rep; HSE Officer; HSE Manager for cranes, hoists, man-baskets and MEWPs; receivers and issuers of live permits naming the item | Within 60 s | In-app + email + SMS (HSE Officer) |
| Category B defect rectification due | Owner's HSE Rep; HSE Officer at 0 | 7 / 3 / 0 days before due_date | In-app + email |
| Item Out of Service for an overdue B defect (DF-4) | Owner's HSE Rep; HSE Officer | At 00:05 on due_date + 1 | In-app + email |
| Configuration event recorded (CF-1); late record (CF-2) | HSE Officer; HSE Manager; owner's HSE Rep; receivers of live permits on the item | Within 60 s | In-app + email |
| Arrival inspection not recorded (EM-3) | Owner's HSE Rep; site engineer | arrived_at + `arrival_inspection_hours` − 4 h; at the deadline | In-app |
| Equipment blacklisted; certification ban; TPI blacklisted or suspended (BL-2) | HSE Officers of every affected project; affected Contractor HSE Reps (no reason, BL-5); receivers of affected live permits | Within 60 s | In-app + email |
| Ban review due (`ban_review_months`) | HSE Manager | 14 days before and on review_due_on | In-app + email |
| Hook block date approaching (critical / general) | HSE Manager; HSE Officers; Contractor HSE Reps of every engagement on the project (with their own readiness counts) | 7 days and 1 day before the block date (07:00); on the switch (00:00:30) | In-app + email |
| Early switch, deferral or policy change (HK4-5/HK4-6) | HSE Officers; Contractor HSE Reps | Immediately | In-app + email |
| Trade certificate missing on a Mobilised deployment (PC-12) | Engagement HSE Rep | At mobilisation; then weekly on Sunday 07:00 while it is missing | In-app |
| Gate EQ denial / `admitted_despite_denial` (GE-7) | As Phase 2 GC-14 | Immediately | As Phase 2 |
| Import batch Validated / committed / expired | Uploader | Immediately | In-app |
| E10 / E11 leading warnings (§6.9) | HSE Manager; HSE Officers of the project; tier-1 Contractor HSE Rep for its tree | Monthly job, day 2, 07:00 | In-app + email |

Expiry and quarantine jobs run in `cert_daily` (00:05:45). An alert whose subject was demobilised, retired or superseded before its send time is dropped. Alerts are de-duplicated per (subject, step), so re-running a job never sends twice.

## 8. Reports / KPIs fed

### 8.1 Dashboard additions (Phase 1 §8.1)
1. **Leading tiles:** K-72 equipment certificate compliance (category breakdown on hover) · K-76 personnel certification compliance · K-74 out-of-service equipment (with an "A defects this period" chip) · K-80 defect rectification on time · K-81 scaffold tag compliance.
2. **Certification band** (all projects): items On Site by service status (In Service, Quarantined, Out of Service) · certificates awaiting review and verification (with an overdue chip) · K-73 and K-77 expiring ≤ 30 days · K-75 inspections overdue · K-78 blacklisted/banned · the hook stage per kind with the next block date (e.g. "Critical codes block from 2026-10-08").
3. **Charts:** C16 K-72 and K-76 by month (lines) with the E10 thresholds as reference lines · C17 defects raised by month, stacked A/B/C, with K-80 as a line · C18 the certificate expiry profile for the next 90 days, as weekly bars split equipment/personnel.
4. Filters D-2 apply (site, zone, contractor with subcontractors, period), plus equipment category and certificate type.

### 8.2 Expiring-items panel — new `ExpiringItemKind` values
`equipment_cert_expiry`, `personnel_cert_expiry`, `scaffold_inspection_due`, `defect_rectification_due`, `tpi_accreditation_expiry`, `tpi_client_approval_expiry`, `certificate_verification_due`, `hook_block_date`. Item fields are as in Phase 2 §8.2. ref is the tag, cert_no, scaffold no., defect no., TPI code or "hook policy". Titles show worker_no and no name for callers without capability 46. Viewer/Client sees counts only (KC-5).

### 8.3 Action panel additions
Certificates awaiting review > 24 h · verifications overdue · verification failed with no decision recorded (VF-6) · `unable_to_verify` · A defects open · B defects due ≤ 3 days · items On Site Quarantined or Out of Service that are named on non-terminal permits · arrival inspections overdue · scaffolds In Use with an expired or red tag · Mobilised deployments with TRADE_CERT_MISSING · hook block date ≤ 7 days with readiness < 100 % · ban reviews due.

### 8.4 Registers and reports
- TPI register: kinds, accreditations, client approvals, status and expiries.
- Equipment register: item, deployments, service status, current line, SWL, limitations and history.
- Equipment certificate register.
- Scaffold register: tag board per zone.
- Personnel certification register: per worker and per type, with worker_no, and names only with capability 46.
- Verification log.
- Defect register: by category and age.
- Blacklist and ban register (HSE Manager; Contractor HSE Rep sees "not accepted" only).
- Equipment gate log (GE-6).
- Hook readiness report (HK4-7).
- Import history.

Exports (capability 123) never contain ID numbers, scans, the medical flag, ban reasons or verification-failure details.

### 8.5 Feeds to other phases
- **Phase 1:**
  - CA source_type `equipment_defect` (DF-10).
  - Incident agency link to a defect (DF-9).
  - T16 and E10–E11.
- **Phase 2:**
  - Providers for `personnel_certificate` and `equipment_certificate` (HK-3) at gates, ADP/AVP eligibility and WAP crews.
  - AVP `equipment_certificate` limiting factor (HK4-11).
  - QR kind `EQ` at gates.
- **Phase 3:**
  - Providers for permit hooks: lifting appliance and accessories, operator binding (HK4-9), scaffold tag (SF-1), crew roles and appointments.
  - Hard-stop suspensions of live permits (HK4-3).
  - Detector quarantine via `calibration_body_id` (BL-7).
- **Phase 5:** gets no data from Phase 4, only the boundary (BD-1…BD-4). Phase 5 owns `training_course` hooks.
- **Phase 6:**
  - The medical-restriction flag is a pointer only (PC-13).
  - Equipment-related incidents and defects feed Phase 6 trend reporting (aggregates).

## 9. Acceptance criteria

Fixtures:
- Appendix A seed.
- "Today" is the shared e2e/demo clock `HSE_CLOCK_AT` = 2026-10-06 10:00 Asia/Riyadh unless another date or time is given (Appendix A.1).
- Phase 2 and Phase 3 seed state are as in their Appendix A.
- Phase 4 providers were registered 2026-10-01 on both projects, so both are in hook stage `transition`. Critical codes block from 2026-10-08 and the others from 2026-10-31.

Users:
- Faisal: HSE Manager.
- Noura: HSE Officer, ANIA-EXP.
- Lina: HSE Officer, RBT-52.
- Ahmed: Contractor HSE Rep, RAWABI tree.
- Yousef: Contractor HSE Rep, QIMMA.
- Omar and Fahad: site engineers.
- Khalid and Majed: permit issuers.
- Sarah: viewer.

**Boundary and catalogues**
1. **Given** PCT contains `RIGGER` **When** Faisal tries to create a Phase 5 course code `RIGGER`, or a PCT type whose code is an existing Phase 5 course code **Then** 422 `CODE_IN_OTHER_CATALOGUE` (BD-3).
2. **Given** the TPI create form **Then** the allowed kinds are inspection_body, personnel_certification_body, calibration_lab, ndt_body and client_scheme, with no training-provider kind (BD-3).
3. **Given** Phase 3 gas tester hooks **Then** PTW issue for Salem Al-Harthi evaluates both `personnel_certificate: GAS-TESTER` (Phase 4, met until 2028-04-19) and `training_course: GAS-TEST` (Phase 5 or not_evaluated), each separately (BD-4).

**TPI organisations**
4. **Given** Noura **When** she sets a TPI to Approved **Then** 403. **When** Faisal approves it **Then** success, audited (TP-2).
5. **Given** an accreditation without register_checked_at **Then** it does not count for TP-4, and a certificate relying on it gets 422 `TPI_ACCREDITATION_INVALID` (TP-3).
6. **Given** NKTI's 17020 accreditation is valid to 2026-11-02 **When** a crane certificate inspected 2026-11-02 is submitted **Then** it is accepted. **When** one inspected 2026-11-03 is submitted with no renewal recorded **Then** 422 `TPI_NOT_ACCEPTABLE` with reason `TPI_ACCREDITATION_INVALID` (Z8).
7. **Given** NKTI's accreditation lapses on 2026-11-03 **Then** NJ-MC-02 (valid until 2027-03-15) and TC-01 (valid until 2027-09-28) stay in force, with the note "TPI accreditation since lapsed" (TP-7).
8. **Given** NKTI's accreditation is valid to 2026-11-02 **Then** 30-day alerts were sent on 2026-10-03, and 14-day, 7-day and 0-day alerts are scheduled for 2026-10-19, 2026-10-26 and 2026-11-02 (TP-8).
9. **Given** a TPI whose accreditation scope is pressure_vessel only **When** a MEWP certificate from it is submitted **Then** 422 `TPI_SCOPE_NOT_COVERED`.
10. **Given** a TPI listing RAWABI in affiliated_contractor_ids **When** it certifies a RAWABI-owned crane **Then** 422 `TPI_NOT_INDEPENDENT` (TP-6).
11. **Given** `require_client_approved_tpi` = false (seed) **When** Faisal sets it to true **Then** the response lists every in-force certificate whose TPI has no active client approval for the project. Seven days later they are Quarantined or not in force unless the approval is recorded (TP-5).
12. **Given** a TPI is Suspended on 2026-10-06 **When** a certificate inspected 2026-10-06 is submitted **Then** 422 `TPI_SUSPENDED`. **And** a certificate inspected 2026-10-05 is still accepted, and existing ones stay in force (BL-6).

**Equipment register and mobilisation**
13. **Given** RW-MC-03 (serial TESTSN-MC-0003) exists **When** Ahmed registers the same manufacturer and serial with different case and spacing **Then** 409 `EQUIPMENT_EXISTS` with EQP number. **When** Yousef (QIMMA, no deployment of it in scope) does the same **Then** 409 `EQUIPMENT_EXISTS_OUT_OF_SCOPE` (EQ-1).
14. **Given** SH-TH-02 is Blacklisted **When** anyone registers its serial **Then** 409 `EQUIPMENT_BLACKLISTED` (EQ-1, BL-3).
15. **Given** VEH-0003 is a Phase 2 vehicle of VC mobile_crane **When** it is linked to an item of category forklift **Then** 422 `CATEGORY_MISMATCH`. **When** a second item is linked to VEH-0003 **Then** 422 as well (EQ-2).
16. **Given** a request to create an equipment item for gas detector GD-0007 **Then** 422 `USE_DETECTOR_REGISTER` (EQ-3).
17. **Given** a new mobile crane without load_chart **When** its first certificate is submitted **Then** 422 `ATTRIBUTE_REQUIRED` (field load_chart) (EQ-4).
18. **Given** DL-MC-01 is Quarantined (expired 2026-08-14) **When** Lina approves a new deployment of it **Then** 422 `EQUIPMENT_NOT_IN_SERVICE` with reason certificate_expired (EM-2).
19. **Given** RW-MC-03 is On Site at ANIA-EXP **When** a deployment is created for RBT-52 **Then** 422 `EQUIPMENT_DEPLOYED_ELSEWHERE` (EM-4).
20. **Given** a tag `MC-03` already used on ANIA-EXP **When** another deployment uses `mc-03` **Then** 409 `TAG_EXISTS` (EM-1).
21. **Given** a deployment is Approved **When** its EQ sticker is first scanned `in` at G-LAND-1 **Then** it becomes On Site with arrived_at. Until an arrival inspection passes, the provider returns not_met `ARRIVAL_INSPECTION_MISSING`, shown as warn in transition (EM-3).
22. **Given** a demobilised deployment **When** its old sticker is scanned **Then** `CREDENTIAL_REVOKED` (EM-5).

**Equipment certificates and configuration**
23. **Given** SH-MEWP-12 inspected 2026-09-02 with printed next due 2027-09-01 **Then** valid_until = 2027-03-01, limiting `category_interval`, and import or form warning W01 (Z1a).
24. **Given** RW-MC-03 certificate AICC-EQ-TEST-25-1106 **Then** valid_until = 2026-11-05, limiting `printed_next_due`. **And** a 30-day alert for it is sent today to Ahmed and none to Yousef (Z1b).
25. **Given** a forklift inspected 2026-08-31 with no printed date **Then** valid_until = 2027-08-30 (Z1c).
26. **Given** the NAJD accessory batch AICC-EQ-TEST-26-0914 (38 lines) **Then** every line is valid until 2027-03-13 (Z1d).
27. **Given** cert_no AICC-EQ-TEST-26-0914 already exists for AICC **When** it is submitted for another item **Then** 409 `CERT_EXISTS`, or `CERT_NO_REUSED` blocking Submit (EC-1).
28. **Given** a certificate inspected 2025-08-01 for a MEWP **Then** its computed valid_until 2026-01-31 is before today, so 422 `CERT_ALREADY_EXPIRED`. **When** Noura attaches it as historic **Then** it is stored and never in force (EC-2).
29. **Given** a line whose serial_as_printed is TESTSN-MC-0030 for RW-MC-03 **Then** 422 `SERIAL_MISMATCH` (EC-5).
30. **Given** a failed result line for a telehandler **Then** the certificate is stored, the item turns Out of Service (`failed_inspection`), and each failure reason without a TPI category becomes a category A defect (EC-6).
31. **Given** an `initial` crane line with load test 95.0 % **Then** 422 `LOAD_TEST_REQUIRED`. **With** 110.0 % **Then** accepted (EC-7).
32. **Given** RW-MC-03 rated 50.000 t **When** a line has swl_t 55.000 **Then** 422 `SWL_ABOVE_RATING` (EC-8).
33. **Given** an excavator with lifting_duty = true and no lifting-duty line **When** a Phase 3 permit names it as lifting_appliance **Then** provider not_met `LIFTING_DUTY_NOT_CERTIFIED`, warn in transition (EC-9).
34. **Given** RW-MB-01 man-basket with limitation `no_personnel_lifting` on the carrying crane's line (fixture) **When** an LF-7 personnel lift uses that crane **Then** not_met `LIMITATION_CONFLICT` (EC-11).
35. **Given** a newer failed line for an item whose older line is still in date **Then** the item is Out of Service and the provider returns hard_stop (EC-10, HK4-3).
36. **Given** Noura submitted AICC certificate AICC-EQ-TEST-26-0923 for GP-FL-03 **When** Noura tries to accept it **Then** 422 `SOD_CONFLICT`. **When** a GULFPAVE Contractor HSE Rep tries **Then** 403 (EC-14, row 107).
37. **Given** TC-01 is in force on NKTI-TEST-26-0118 **When** the climb event at 2026-09-28 14:00 is recorded **Then** the line is Suspended `configuration_changed`, TC-01 is Quarantined, and any live lifting permit on TC-01 is Suspended `hook_not_met` within 60 s, although the hook stage is transition (Z3, CF-1).
38. **Given** the TC-01 climb **When** a certificate inspected 2026-09-27 is offered to clear it **Then** 422 `INSPECTION_BEFORE_EVENT`. **When** NKTI-TEST-26-0929 is accepted 15:40 and verified 16:00 **Then** in force from 2026-09-29 16:00, valid_until 2027-09-28 (Z3).
39. **Given** a configuration event dated 2026-10-04 09:00 is recorded today at 10:00 **Then** 422 `BACKDATED_EVENT` (CF-2).
40. **Given** a new line whose configuration_ref differs from the event's new_configuration **Then** review warning `CONFIGURATION_MISMATCH`, and Accept requires the reviewer's confirmation tick (CF-3).
41. **Given** `lifting_gear_colour_scheme.enabled` = false (seed) **Then** colour_code is optional and no `COLOUR_CODE_OUT_OF_PERIOD` result is produced (EC-12).

**Scaffolds**
42. **Given** SC-0142 inspected green 2026-10-01 **Then** the tag is valid to 2026-10-07. On 2026-10-06 the provider returns met. On 2026-10-07 07:00 alerts are sent (day-before alert on 10-06 07:00 already sent). On 2026-10-08 the tag is expired and the provider returns not_met `SCAFFOLD_INSPECTION_OVERDUE`, shown as warn until 2026-10-30 (Z6).
43. **Given** SC-0150 is red **When** a Phase 3 WAH permit references scaffold_tag_ref SC-0150 **Then** `HOOK_NOT_MET` (hard stop) today, in transition (HK4-3).
44. **Given** SC-0151 is yellow with restriction text **Then** the provider returns met with `SCAFFOLD_YELLOW_TAG`, and the restriction appears as a permit condition (SF-6).
45. **Given** Imran Hussain records an inspection of SC-0142 **Then** 422 `INSPECTOR_NOT_CERTIFIED`, because he holds SCAFFOLDER and not SCAFFOLD-INSPECTOR. **When** Ferdinand Reyes records it **Then** success, in every hook stage (SF-4).
46. **Given** Ferdinand Reyes is the erection supervisor of a new scaffold **When** he records its handover inspection **Then** 422 `SOD_CONFLICT` (SF-4).
47. **Given** a 24.00 m independent scaffold without design_ref **When** it is handed over **Then** 422 `SCAFFOLD_DESIGN_REQUIRED` (SF-2).
48. **Given** a Phase 2 ops event dust_sandstorm on S-LAND **Then** every In Use scaffold in S-LAND turns `inspection_required` within 60 s, and the provider returns hard_stop until re-inspected (SF-5).
49. **Given** a handover crew including Nadeem Akhtar (certification ban) **Then** `CREW_NOT_CERTIFIED` with hard stop, in every stage (SF-3, BL-4).

**Personnel certificates**
50. **Given** Joel Bautista's RIGGER card valid until 2026-10-20 **Then** a 14-day alert to Yousef is sent today. PTW-RBT-52-2026-0290 on 2026-10-07 gets met. A shift on 2026-10-14 gets `expiring` and Phase 3 EXPIRING_7D. On 2026-10-21 it is not_met `CERT_EXPIRED` and blocks, because RIGGER is critical and its block started 2026-10-08 (Z2a).
51. **Given** a FORKLIFT-OPERATOR card issued 2025-02-10 printed 2030-02-09 **Then** valid_until is 2028-02-09, limiting `cap` (Z2b).
52. **Given** Imran Hussain's renewal DSPC-SC-TEST-26-1002 is submitted 2026-10-04 08:30 **Then** verification is due 2026-10-07. Today the old card is still in force (to 2026-10-10). **When** the renewal is verified today **Then** it supersedes the old card today, with no gap (Z2d, PC-9).
53. **Given** Ahmed submits a card for Zaheer Abbas and types 2000001019 **Then** id_match = `matched`, and no ID number is stored on the certificate or in its audit row. **When** he types 2000001091 **Then** 422 `CERT_ID_MISMATCH`, the audit shows `2*******91`, and nothing is stored (Z9, PC-3, P4-2).
54. **Given** a card whose name matches no token **When** Noura accepts without ticking "identity confirmed by TPI" **Then** 422 `NAME_MISMATCH_CONFIRMATION` (PC-4).
55. **Given** a RADIOGRAPHER level I card **Then** 422 `LEVEL_NOT_ACCEPTED`. Vinod's level II card is valid until 2027-05-31 (PC-7).
56. **Given** Zaheer Abbas (CRANE-OPERATOR [mobile_crane, crawler_crane] ≤ 60.000 t):
    - **When** he is named operator of RW-MC-03 **Then** met.
    - Of TC-01 **Then** not_met `CERT_SCOPE_MISMATCH`.
    - Of DL-MC-01 **Then** the scope is met, but the equipment check is not_met.
    - Of a 70.000 t crane **Then** `CERT_SCOPE_MISMATCH`.

    (Z7, HK4-9.)
57. **Given** Ali Hassan (tower crane ≤ 16 t) **When** he is named operator of TC-01 (12 t) **Then** met.
58. **Given** Osman Idris (RIGGER level 1) on a critical lift with `rigger_level_critical_min` = 2 **Then** not_met `CERT_SCOPE_MISMATCH` (PC-7). It is shown as warn until 2026-10-07 and blocks from 2026-10-08.
59. **Given** a SIGNALLER card with limitation `trainee_logbook` **When** its holder is signaller on a critical lift **Then** not_met `CERT_LIMITATION`. On a routine lift **Then** met, with the limitation in conditions (PC-8).
60. **Given** a worker with two valid RIGGER cards **When** the second is accepted and verified **Then** only one is in force, and the older is Superseded (PC-9).
61. **Given** Faisal HSE-suspends Zaheer's CRANE-OPERATOR certificate **Then** hard stop, and live permits with him as operator are Suspended `hook_not_met` within 60 s. Worker status is unchanged and Faisal sees the prompt "Consider a worker ban under capability 49?" (PC-10, PC-11).
62. **Given** Bikash Rai (RIGGER expired 2026-08-31, trade rigger) **Then** his deployment shows `TRADE_CERT_MISSING`, counts against K-76 and is not blocked from deployment (PC-12).
63. **Given** a card with medical_restriction_on_card = true **When** Fahad (capability 117 only) views it **Then** the flag is absent from the response. The provider returns met `CARD_RESTRICTION_REVIEW` until Noura records "restriction reviewed" (PC-13, P4-1).

**Verification**
64. **Given** `unverified_acceptance_hours` = 0 **When** a card is Accepted but not verified **Then** it is not in force (`CERT_UNVERIFIED`). **When** Faisal sets 24 hours **Then** a non-critical card counts as in force for 24 h with a warning, and a CRANE-OPERATOR card does not (VF-1).
65. **Given** Noura submitted a card for Osman Idris **When** Noura records its verification **Then** 422 `SOD_CONFLICT`. **When** Ahmed tries **Then** 403 (VF-2, row 108).
66. **Given** AICC verification domains [verify.aicc-test.example] **When** Noura records method tpi_email from an address at another domain **Then** 422 `CHANNEL_NOT_REGISTERED` (VF-3).
67. **Given** a TPI QR URL on host aicc-verify-test.example.net (not registered) **Then** warning `VERIFICATION_URL_FOREIGN_DOMAIN`, and that URL cannot be used as the channel. The server makes no outbound request (VF-4).
68. **Given** two `no_response` outcomes 26 h apart **Then** status `unable_to_verify`, the HSE Manager is alerted, and the certificate is not in force (VF-5).
69. **Given** Nadeem Akhtar's QUICKCERT card QC-SC-TEST-26-0777 verified `not_found` on 2026-09-17 **Then** it is Rejected (verification_failed), E11 for ANIA-EXP September is raised, and the action panel shows it as decided (ban recorded 2026-09-17) (VF-6).
70. **Given** an original was sighted only **Then** verification_status stays not_verified (VF-3).
71. **Given** Omar scans RW-MC-03's EQ sticker **Then** he sees category mobile_crane, tag, owner RAWABI, status In Service (green), cert AICC-EQ-TEST-25-1106, TPI AICC, valid_until 2026-11-05, SWL 50.000 t and limitations, with no personal data (VF-8).
72. **Given** Omar scans Joel Bautista's AC card in certificates mode **Then** he sees RIGGER (to 2026-10-20) and SIGNALLER (to 2028-03-02), in force yes, with name, worker_no and photo. The response contains no ID number, scan URL, medical flag or verification history, and a `cert_check_view` audit row is written (VF-9).

**Defects and service status**
73. **Given** RW-MEWP-07 with A defect DEF-ANIA-EXP-2026-0007 (2026-09-26) **Then** status is Out of Service, and its sticker scan shows red "OUT OF SERVICE / خارج الخدمة". A WAH permit naming it today gets `HOOK_NOT_MET` (hard stop) although the stage is transition (Z4c, DF-3).
74. **Given** DEF-ANIA-EXP-2026-0005 (B, raised 2026-09-24, TPI due 2026-10-31) **Then** due_date = 2026-10-24. Alerts go 2026-10-17, 2026-10-21 and 2026-10-24. If not Closed, the item is Out of Service at 2026-10-25 00:05 (Z5a, DF-4).
75. **Given** a B defect raised today with no date **Then** due_date = 2026-10-20 (Z5c).
76. **Given** sling WRS-NJ-0117 (A, retired 2026-09-12) **When** a rectification is recorded **Then** 422 `ACCESSORY_REPAIR_NOT_ALLOWED` (Z5d, DF-7).
77. **Given** RW-MEWP-07 is rectified by RAWABI **When** Ahmed, or the rectifier, returns it to service **Then** 403/422 `SOD_CONFLICT`. **When** Noura closes it without an accepted, verified `after_repair` line inspected after rectification **Then** 422 `TPI_REINSPECTION_REQUIRED` (DF-6).
78. **Given** Fahad tags out GP-EX-05 with reason "boom cylinder weeping" **Then** it is accepted with no rule able to block it, the item is Out of Service, and the GULFPAVE Contractor HSE Rep and Noura are notified (DF-8).
79. **Given** a Phase 1 incident with agency mewp **Then** the investigator is prompted to link or raise a defect. No Phase 1 field changes and no CA is created automatically (DF-9, DF-10).

**Blacklisting and bans**
80. **Given** Noura **When** she blacklists an item **Then** 403. **When** Faisal blacklists one with reason_text < 20 chars **Then** 422 (BL-2).
81. **Given** SH-TH-02 Blacklisted 2026-09-05 **Then** its deployment is Demobilised, its token is revoked, and K-78 counts it for ANIA-EXP September (BL-3).
82. **Given** Nadeem Akhtar has a certification ban (all types) from 2026-09-17 **When** Ahmed submits a new SCAFFOLDER card for him **Then** 422 `HOLDER_BANNED`. Ahmed sees "Certification not accepted on this organisation's projects", with no reason. His Phase 2 worker status is unchanged (BL-4, BL-5, PC-11).
83. **Given** QUICKCERT blacklisted 2026-09-20 with scope all_certificates **Then** GP-FL-03's QC-EQ-TEST-26-0042 is Revoked (`tpi_blacklisted`) and the item was Quarantined until AICC-EQ-TEST-26-0923 came into force on 2026-09-23. Phase 3 detectors with calibration_body_id = QUICKCERT are Quarantined (none in seed) (BL-7).
84. **Given** Faisal lifts the QUICKCERT blacklist **Then** it becomes Suspended, and QC-EQ-TEST-26-0042 stays Revoked (BL-8).

**Hooks and transition**
85. **Given** ANIA-EXP providers registered 2026-10-01 **Then** critical_block_from = 2026-10-08 and general_block_from = 2026-10-31. Alerts were sent 2026-10-01 and 2026-10-07 (critical) and are due 2026-10-24 and 2026-10-30 (general) (Z4).
86. **Given** a lifting permit with chain sling FX-ACC-0219 (line expired 2026-10-03) **When** it is issued today **Then** warning `HOOK_NOT_MET_WARN` (CERT_EXPIRED) and Issue is allowed. On 2026-10-08 the job at 00:00:30 switches the critical codes, the permit's next evaluation gives `HOOK_NOT_MET`, and the live permit is Suspended `hook_not_met` (Z4a).
87. **Given** an excavator with an expired PLANT-TPI line on a WAP vehicle **Then** gate GRANTED with a warning until 2026-10-30, and DENIED `HOOK_NOT_MET` from 2026-10-31 (Z4b).
88. **Given** Faisal defers general_block_from **Then** the latest date allowed is 2026-11-30. A second deferral gets `DEFERRAL_USED`. Deferring CRANE-OPERATOR gets `CRITICAL_CODE_NO_DEFERRAL`. Returning a blocked code to warn gets `HOOK_POLICY_LOOSENING` (Z4d, HK4-6).
89. **Given** Faisal switches all codes on RBT-52 to block today **Then** it is effective at once, audited, and alerted to Lina and Yousef (HK4-5).
90. **Given** an equipment_tag hook call without project_id in context **Then** not_met `EQUIPMENT_NOT_REGISTERED`, and the call is logged as a caller error (HK4-8).
91. **Given** a Phase 4 `cert.status_changed` event **Then** affected Phase 2 credentials and Phase 3 permits are re-evaluated within 60 s, and the provider cache is cleared (HK4-10).
92. **Given** VEH-0003 AVP AVP-OEXX-26-0120 **Then** effective validity is 2026-11-05 with limiting factor `equipment_certificate`. On 2026-11-06, if the crane has not been renewed, the AVP is suspended by dependency, and it is reinstated when the crane is renewed (Z10, HK4-11).
93. **Given** the readiness report for ANIA-EXP today **Then** each code shows required and in-force counts, the not-met subjects with reasons, and the live permits affected on 2026-10-08. It never prevents the switch (HK4-7).

**Gate equipment check**
94. **Given** RW-MEWP-07's EQ sticker scanned `in` at G-LAND-1 **Then** DENIED `EQUIPMENT_OUT_OF_SERVICE`. **Given** SH-TH-02's old sticker **Then** `CREDENTIAL_REVOKED`, because that check comes before `EQUIPMENT_BLACKLISTED` (GE-2).
95. **Given** RW-MC-03 (linked to VEH-0003) scanned at an AVP gate **Then** GRANTED with `ALSO_SCAN_VEHICLE_STICKER` (GE-4).
96. **Given** 40 EQ scans today at ANIA-EXP **Then** K-52 and K-53 are unchanged and the scans appear in the equipment gate log with subject type `equipment_deployment` (GE-6).
97. **Given** a guard admits a DENIED item **Then** `admitted_despite_denial` is recorded with the Phase 2 GC-14 alerts (GE-7).

**Imports**
98. **Given** an equipment certificate file with 120 rows, of which 3 have an unknown tpi_code, 2 a serial mismatch and 5 a printed date beyond the interval **Then** the dry-run reports 5 errors (E04 × 3, E05 × 2) and 5 W01 warnings. Commit is possible for the 115 valid rows only when the batch is ≤ 60 min old (IM-1, IM-7).
99. **Given** committed rows **Then** certificates are Submitted, never Accepted, and each needs review and verification (IM-5).
100. **Given** a personnel file with an id_number column **Then** the dry-run masks IDs as WK-4, the file is deleted at commit, discard or expiry, and no ID is stored on certificates (IM-3, IM-4).
101. **Given** Ahmed **When** he uploads with source `tpi_register_file` **Then** 403 (IM-6). **When** Noura uploads an AICC register email from verify.aicc-test.example **Then** the committed certificates get verification records with method `tpi_register_file`, outcome confirmed and reference = the file sha256.
102. **Given** the same file uploaded again **Then** warning W05 (IM-7).

**KPIs, AI, permissions, PDPL**
103. **Given** the Appendix A seed **When** KPIs for September 2026 are computed **Then** they equal Z11 for both projects, to the decimal.
104. **Given** Z11 **Then** E10 and E11 are raised for ANIA-EXP and for the RAWABI tree on 2026-10-02 07:00. Neither is raised for RBT-52 (K-72 = 98.0 % is not < 98.0).
105. **Given** Z12 values **Then** the displayed values and E10 decisions match exactly.
106. **Given** T16 called with group_by contractor **Then** the response holds aggregates only, with no names, worker_no, cert numbers, ID data, ban reasons or verification details. Sarah gets aggregates only (KC-4, KC-5).
107. **Given** Sarah **When** she calls GET personnel certificates **Then** 403 (row 117).
108. **Given** Yousef (C scope QIMMA) **Then** he sees certificates of QIMMA tree workers only. Opening a scan needs a reason and writes `sensitive_field_read`, and scan URLs expire in ≤ 5 min (P4-3, row 119).
109. **Given** Fahad (S on ANIA-EXP) **When** he records an inspection of a scaffold on S-LAND **Then** allowed if the inspector worker holds SCAFFOLD-INSPECTOR. **When** he accepts an equipment certificate **Then** 403 (rows 107, 113).
110. **Given** a suspended contractor's HSE Rep **When** he submits a certificate **Then** 403, while reads still work (Phase 0 rule 28).
111. **Given** an export of the personnel certification register by Omar without capability 46 **Then** it has worker_no and no names, and no ID, scan or medical columns (row 123).
112. **Given** a personnel certificate that ended (Expired or Superseded) more than `cert_scan_retention_years` (2) ago **Then** the retention job deletes its scans, keeps the metadata, and records the deletion in the audit log (P4-7).
113. **Given** every Phase 4 mutation **Then** an audit row exists with before/after, and no ID numbers are in any audit diff (Phase 0 rule 35, P4-2).
114. **Given** the UI in Arabic **Then** every Phase 4 label, status and error message in this spec is shown with the AR text from §3/§4, and tags, cert numbers and dates are shown left-to-right inside RTL layout (Phase 0 i18n).

## 10. Open questions for the HSE Manager

Each question has a default, so the build can start. The default is the strictest reasonable choice unless it would stop the site from working.

1. **Client-approved TPI list:** do the airport client and the PMC keep a list of approved TPIs, and must every certificate come from it? Default: `require_client_approved_tpi` = false. A TPI must be accredited (ISO/IEC 17020 or 17024) and HSE Manager Approved. If a client list exists, switch to true (TP-5).
2. **Inspection intervals:** the defaults are 6 months for lifting accessories, MEWPs, man-baskets, hoists, mast climbers, BMUs and tripod winches, and 12 months for cranes, forklifts, telehandlers, plant and pressure vessels. Does the client or the SBC/MOMRAH current text require shorter intervals (e.g. 3 months for accessories in severe service, or 6 months for tower cranes)? `VERIFY` R1/R2/R10.
3. **Accept before verification:** default 0 h, so a certificate is never in force before it is verified with the TPI. Is a 24 h window wanted for non-critical types to avoid holding up work? Critical codes would never get it.
4. **Personnel certificate caps:** defaults are 36 months for operators, riggers and signallers, 24 for gas testers, 60 for scaffolders and radiographers (or as printed, if shorter). Do the client scheme and the TPIs (e.g. an operator card scheme) use other periods? `VERIFY`.
5. **Hook warn → block switch:** default 7 days after provider registration for critical lifting codes and 30 days for the rest. The switch is automatic, with one deferral of ≤ 30 days for non-critical codes and no return to warn. This answers Phase 2 open question Q10. Confirm, or set 0 days (block from day one).
6. **Scaffold inspection:** default 7-day tags; the inspector must hold a SCAFFOLD-INSPECTOR certificate; green, yellow and red tags; a design is required above 20.00 m or for special scaffolds. Does the client require a different tag system (e.g. Scafftag) or a lower design height? `VERIFY` TG20 / client procedure.
7. **Lifting-gear colour coding:** off by default. Does the project use a quarterly or six-monthly colour scheme for accessories? If so, give the colours and periods.
8. **Rigger levels:** default level 2 is the minimum for critical lifts. Do the TPI schemes on site use levels 1–3 like this?
9. **Earthmoving plant:** the default needs a `PLANT-TPI` certificate for excavators and wheel loaders on WAP vehicles, and a lifting-duty certificate when they lift. Confirm that all earthmoving plant needs TPI inspection, not only plant used for lifting.
10. **Authorised persons, LOTO, confined-space cards:** by default these are Phase 5 training, and no certificate is a precondition of a PTW appointment. Does the client issue third-party cards (LOTO-AUTHORISED-CARD, CSE-STANDBY-CARD, AP-ELEC-LV/HV) that must be checked here? Should LIFT-SUPERVISOR or APPOINTED-PERSON-LIFTING be required for lift-supervisor appointments?
11. **Banning persons and TPIs:** the HSE Manager alone decides, a review is due every ≤ 6 months, the employer sees "not accepted" only, and nothing is reported to authorities automatically. Is legal or HR review needed before a person's certification ban? Should a forged card lead to a worker ban (Phase 2 capability 49) automatically? Default: prompt only.
12. **Contractor HSE Reps opening scans** (capability 119, C scope): allowed by default with a reason, and audited. Restrict to HSE staff only?
13. **Pressure vessels and compressors:** in scope by default with 12-month TPI inspection and a written scheme. Are air receivers below a size threshold exempt? Are site-fabricated vessels expected? `VERIFY` R8.
14. **Hired equipment:** by default the hiring contractor is the accountable owner. Should the rental company be registered as a separate record, or as a contractor engagement?
15. **Defects:** category B is due within ≤ 30 days (14 when no date is given). Category A on accessories means destroy or return to the manufacturer, never repair. Confirm, or set shorter.
16. **Who verifies:** by default HSE Officers verify with the TPI through registered channels (portal, the TPI's own QR URL, email, phone), and the platform never opens external URLs. Will the client or TPIs provide a register file or an API later? (v1.0 accepts register files, IM-6.)
17. **Warning thresholds:** E10 triggers below 98.0 % for equipment and below 95.0 % for personnel and scaffolds. E11 triggers on ≥ 1 failed verification or ≥ 3 A defects per month. Confirm.
18. **Load-test percentages:** ≥ 100 % SWL is required on initial, after-configuration-change and after-structural-repair inspections for cranes, hoists, man-baskets, mast climbers and BMUs. Should it be 110 % or 125 % by category? `VERIFY` R1/R10.

## 11. Changes required in earlier specs (applied 2026-10-08: `1-dashboard.md` v1.3, `2-access-permits.md` v1.2, `3-ptw.md` v1.1)

### 11.1 `0-foundation.md` v1.0
No change. Phase 0 rules 26–28 (contractor approval, blacklisting, "later phases additionally block permits"), rule 35 (audit), rule 45 (normalisation) and rule 48 (stable codes) are used as they are.

### 11.2 `1-dashboard.md` v1.2 → v1.3
1. **AI tools:** add T16 `get_certification_kpis` (KC-4) to the tool list. Extend T13 (leading warnings) to return E10–E11. Add AI-19 report sections "Equipment & personnel certification" (K-72…K-81, aggregates only).
2. **§6.9 / §7:** add E10 and E11 (§6.9 here) to the leading-indicator warnings, with the same monthly job (day 2) and recipients.
3. **§8.1:**
   - Leading tiles K-72, K-76, K-74, K-80 and K-81.
   - Certification band.
   - Charts C16–C18.
   - `ExpiringItemKind` values from §8.2 here.
   - Action panel items from §8.3 here.
4. **CA entity:** new `source_type` value `equipment_defect` (source_ref = DEF number). No automatic creation. The Phase 1 W-examples are unchanged.
5. **Incident → defect:** the investigator is prompted to link or raise a defect (DF-9). No Phase 1 field is added; the defect stores the incident ref.

### 11.3 `2-access-permits.md` v1.1 → v1.2
1. **HK-3 interface:** add an optional `context` {project_id (required for subject equipment_tag), zone_id, permit_id, critical, use, equipment_ref, rated_capacity_t, operator_worker_id}. Add result fields `hard_stop` (bool), `conditions[]` (text and code) and `swl_t`. Callers treat hard_stop not_met as not_met in every policy stage.
2. **HK-4 effective policy:** resolve each (project, kind, code) to `warn` or `block` from the Phase 4 hook policy state (§3.14, §4.8). Add the **transition** stage: a not_met without hard_stop → `warn` with reason `HOOK_NOT_MET_WARN`. Add `HOOK_NOT_MET_WARN` to the GC-6 WARN list.
3. **ZP-3 clarification:** "not_met under warn" means the transition stage above. Hard stops always block.
4. **QR kinds:** add kind `EQ` (`HSE2:EQ:<22-char token>`) to the QR spec. Update the AC64 regex to `^HSE2:(AC|VS|WP|PT|EQ):[A-Za-z0-9_-]{22}$`.
5. **GC-6:**
   - Add DENY codes `EQUIPMENT_BLACKLISTED`, `EQUIPMENT_NOT_DEPLOYED`, `EQUIPMENT_NOT_APPROVED`, `EQUIPMENT_OUT_OF_SERVICE` and `EQUIPMENT_QUARANTINED`.
   - Add WARN codes `ARRIVAL_INSPECTION_DUE` and `ALSO_SCAN_VEHICLE_STICKER`.
   - The check order is GE-2.
6. **Gate log:** new subject type `equipment_deployment`. It is excluded from K-52/K-53 (GE-6), so the Phase 2 KPI examples are unchanged.
7. **HK-2 default attach points (seeded):**
   - VC excavator and wheel_loader → `equipment_certificate: PLANT-TPI`.
   - WAP crew_role banksman → `personnel_certificate: BANKSMAN`.
8. **Obstacle clearance:** an optional `equipment_item_id` for CF-4 re-checks.
9. **AVP effective validity (X3):** the `equipment_certificate` limiting factor becomes live. In the Phase 4 seed, VEH-0003's AVP AVP-OEXX-26-0120 has effective validity 2026-11-05 (Z10). The Phase 2 X3 worked example is unchanged on the Phase 2 seed, where there is no provider.
10. **Open question Q10 (hook transition):** answered by HK4-5 / §10 Q5 here.

### 11.4 `3-ptw.md` v1.0 → v1.1
1. **Equipment lines:**
   - Add `equipment_item_id` (optional; resolved from tag when blank).
   - Add `operator_worker_id`, required for categories that have an operator code in EQC (HK4-9).
   - Pass the HK-3 context on every equipment and crew hook call.
2. **HK3-2 default hooks:**
   - Operator codes per equipment category: CRANE-OPERATOR, MEWP-OPERATOR, FORKLIFT-OPERATOR, TELEHANDLER-OPERATOR, PLANT-OPERATOR, HOIST-OPERATOR.
   - Crew role banksman → `BANKSMAN`.
   - EQ tripod_winch → `RESCUE-WINCH-TPI`; mast_climber and bmu → `HOIST-TPI`.
3. **LF-4 wording:** "not_met under warn policy" → "not_met under the transition stage gives warning HOOK_NOT_MET_WARN. Hard stops block in every stage."
4. **scaffold_tag_ref:** resolve it against the Phase 4 scaffold register of the permit's project (SF-1). Copy the yellow-tag restrictions and equipment limitations (`conditions[]`) into permit conditions, as LF-9 does.
5. **Gas detectors (§4.6):**
   - Add an optional `calibration_body_id` (FK TPI kind calibration_lab).
   - Add the quarantine trigger "calibration body blacklisted in scope" (BL-7).
6. **HK3-5 events:** subscribe to the Phase 4 events (HK4-10) and suspend live permits (`hook_not_met`) on hard stops and on not_met after the block date.
7. **AC17/AC18:** they stay valid on the Phase 3 seed, where no providers are registered. The Phase 4 behaviour is covered by ACs 37, 73 and 86 here.

## Appendix A — Seed data (fictional; `seed_fake = true` on every row; all names, IDs, numbers, licences, TPIs and references are fake)

### A.1 Principles
- The seed builds on the Phase 0–3 seeds; no earlier seed row changes. **Seed clock = the shared e2e/demo clock `HSE_CLOCK_AT` = 2026-10-06T10:00:00+03:00 (Asia/Riyadh)**, the same instant used by the Phase 1–3 seeds; every "today" in §6.10 and §9 is this clock.
- **Block-switch dates relative to the clock:** providers were registered 2026-10-01 (5 days before the clock), so at the clock both projects are in the `transition` stage. Critical codes switch to block at 2026-10-08 00:00:30 (clock + 2 days) and the other codes at 2026-10-31 00:00:30 (clock + 25 days). ACs that expect blocking for a non-hard-stop not_met (e.g. 50, 58, 86, 87) advance the clock to the stated date; every AC at the clock itself expects `HOOK_NOT_MET_WARN`, except hard stops, which block at once.
- Phase 4 was enabled on both projects on **2026-10-01**: providers registered, hook stage `transition`, critical_block_from 2026-10-08 and general_block_from 2026-10-31, no deferral used.
- TPI names and domains are invented and end in `-test.example`. Certificate numbers contain `TEST`. Serials start `TESTSN-`.
- Named workers are the Phase 2 workers. WKR-000022 and WKR-000023 are added as named rows **within** the Phase 2 bulk counts (SAHARA), so Phase 2 K-48 is unchanged.
- The bulk generator creates the unnamed items, certificates, scaffolds and defects so that the September 2026 KPIs equal Z11 exactly. Its counts are in A.10. Bulk rows use refs FX-… (equipment) and SC-0xxx (scaffolds).

### A.2 TPI organisations

| Code | Name / الاسم | Kinds | Status | Accreditation (ISO/IEC, scope, valid) | Verification channels | Notes |
|---|---|---|---|---|---|---|
| AICC | Arabian Inspection & Certification Co. (test) / العربية للفحص والشهادات (تجريبي) | inspection_body, personnel_certification_body | Approved 2026-01-10 (Faisal) | 17020: all lifting categories, MEWP, forklift, telehandler, plant, pressure_vessel → 2027-06-30; 17024: CRANE-OPERATOR, RIGGER, SIGNALLER, BANKSMAN, MEWP-OPERATOR, FORKLIFT-OPERATOR, TELEHANDLER-OPERATOR, PLANT-OPERATOR → 2027-06-30; register_checked 2026-01-10 Noura | portal verify.aicc-test.example; email certs@verify.aicc-test.example | client approval none (setting false) |
| NKTI | Najm Kingdom Technical Inspection (test) / نجم المملكة للفحص الفني (تجريبي) | inspection_body | Approved | 17020: tower_crane, mobile_crane, crawler_crane, construction_hoist, pressure_vessel → **2026-11-02** | portal nkti-test.example | Z8 |
| MLIS | Mediterranean Lifting Inspection Services (test) / (تجريبي) | inspection_body | Pending (optional foreign TPI, not used) | 17020 lifting_accessory → 2027-12-31, register not checked | email inspect@mlis-test.example | does not count (TP-3) |
| DSPC | Desert Skills Personnel Certification (test) / الصحراء لاعتماد الكفاءات (تجريبي) | personnel_certification_body | Approved | 17024: SCAFFOLDER, SCAFFOLD-INSPECTOR, GAS-TESTER, ROPE-ACCESS → 2027-09-30 | portal dspc-test.example | |
| FNDT | Falcon NDT Certification (test) / الصقر لاعتماد الفحص غير الإتلافي (تجريبي) | ndt_body | Approved | ISO 9712 scheme RADIOGRAPHER → 2028-01-31 | email verify@fndt-test.example | |
| GCAL | Gulf Calibration Laboratory (test) / مختبر الخليج للمعايرة (تجريبي) | calibration_lab | Approved | 17025 gas detectors → 2027-03-31 | email cal@gcal-test.example | link target for Phase 3 detectors |
| QUICKCERT | QuickCert Inspections (test) / كويك سيرت (تجريبي) | inspection_body, personnel_certification_body | **Blacklisted 2026-09-20** (Faisal; scope all_certificates; reason "certificates not traceable in TPI records; verification returned not found", review 2027-03-20) | 17020 claimed, register check failed | — | BL-7 |

### A.3 Equipment items and deployments (named)

| Item | Tag · project · owner | Category · rating | Link | Certificate (TPI, inspected → valid_until) | Status at seed |
|---|---|---|---|---|---|
| EQP-000003 | RW-MC-03 · ANIA-EXP · RAWABI | mobile_crane · 50.000 t | VEH-0003 | AICC-EQ-TEST-25-1106 (AICC, 2025-11-06 → **2026-11-05**) verified | In Service; 30-day alert today (Z1b, Z10) |
| EQP-000005 | GP-EX-05 · ANIA-EXP · GULFPAVE | excavator · lifting_duty false | VEH-0005 | AICC-EQ-TEST-26-0210 PLANT-TPI (2026-02-10 → 2027-02-09) | In Service |
| EQP-000007 | RW-MEWP-07 · ANIA-EXP · RAWABI | mewp boom · 18.00 m · 2 persons | — | AICC-EQ-TEST-26-0605 (2026-06-05 → 2026-12-04) | **Out of Service** `defect_a` DEF-ANIA-EXP-2026-0007 (2026-09-26, hydraulic leak on slew ring, physical tag applied) |
| EQP-000012 | NJ-MC-02 · ANIA-EXP · NAJD | mobile_crane · 40.000 t | — | NKTI-TEST-26-0331 (NKTI, 2026-03-16 → 2027-03-15) | In Service |
| EQP-000017 | WRS-NJ-0117 · ANIA-EXP · NAJD | lifting_accessory wire-rope sling 8.5 t | — | AICC batch 2026-05 | **Retired** `retired_destroyed` 2026-09-12 (DEF-ANIA-EXP-2026-0004 A from INC-ANIA-EXP-2026-0150) |
| EQP-000021 | GP-FL-03 · ANIA-EXP · GULFPAVE | forklift · 3.000 t | — | QC-EQ-TEST-26-0042 (QUICKCERT) **Revoked** 2026-09-20; AICC-EQ-TEST-26-0923 (2026-09-23 → 2027-09-22) verified 09-23 | In Service from 2026-09-23 |
| EQP-000024 | RW-MB-01 · ANIA-EXP · RAWABI | man_basket · 2 persons · 0.300 t | — | AICC-EQ-TEST-26-0715 (2026-07-15 → 2027-01-14) | In Service |
| EQP-000031 | SH-TH-02 · ANIA-EXP · SAHARA | telehandler | — | — | **Blacklisted** 2026-09-05 (`identity_unverifiable`: serial plate re-stamped); deployment Demobilised |
| EQP-000032 | SH-MEWP-12 · ANIA-EXP · SAHARA | mewp scissor · 12.00 m | — | AICC-EQ-TEST-26-0902 (2026-09-02, printed 2027-09-01 → **2027-03-01**) | In Service (Z1a) |
| EQP-000040…077 | NAJD accessory batch NJ-ACC-01…38 · ANIA-EXP · NAJD | lifting_accessory | — | AICC-EQ-TEST-26-0914 (38 lines, 2026-09-14 → **2027-03-13**) | In Service (Z1d) |
| EQP-000101 | TC-01 · RBT-52 · QIMMA | tower_crane flat-top · 12.000 t · jib 60 m · TESTSN-TC-0001 | — | NKTI-TEST-26-0118 (erection 2026-01-18) **Suspended** 2026-09-28 14:00 `configuration_changed`; NKTI-TEST-26-0929 (after_configuration_change, 2026-09-29, load test 110.0 %, "HUH 236.00 m, jib 60 m, 9 tie-ins" → **2027-09-28**) verified 16:00 | In Service from 2026-09-29 16:00 (Z3) |
| EQP-000104 | SB-RBT-04 · RBT-52 · QIMMA | lifting_accessory spreader beam 20 t | — | AICC-EQ-TEST-26-0811 (2026-08-11 → 2027-02-10) | In Service |
| EQP-000110 | DL-MC-01 · RBT-52 · DLIFT | mobile_crane · 60.000 t | VEH-0110 (Phase 2 bulk) | AICC-EQ-TEST-25-0815 (2025-08-15 → 2026-08-14) | **Quarantined** `certificate_expired` since 2026-08-15; On Site |
| EQP-000112 | CH-RBT-01 · RBT-52 · QIMMA | construction_hoist | — | NKTI-TEST-26-0820 (2026-08-20 → 2027-02-19) | In Service |

### A.4 Fixture items for KPIs and ACs (ANIA-EXP; all RAWABI tree)

| Item | Owner | Category | State at 2026-09-30 | Used by |
|---|---|---|---|---|
| FX-ACC-0201 | NAJD | lifting_accessory shackle | line expired 2026-09-18 (no renewal) | K-72, K-75 |
| FX-FL-06 | RAWABI | forklift | line expired 2026-09-25 | K-72, K-75 |
| FX-ACC-0230, FX-ACC-0231 | RAWABI | lifting_accessory | accepted 2026-09-29, verification pending (`unverified_acceptance_hours` 0 → not in force) | K-72 |
| FX-TH-04 | RAWABI | telehandler | periodic line 2026-09-22 **fail** (supersedes the older line, EC-10); Out of Service; A defect DEF-ANIA-EXP-2026-0008. A failed line has no valid_until, so K-75 does not count it (it is counted in K-74) | K-72, K-74 |
| FX-EX-11 | NAJD | excavator | B defect DEF-ANIA-EXP-2026-0003 raised 2026-08-21, due 2026-09-20, not closed → Out of Service 2026-09-21 00:05; certificate valid | K-74, K-80 |
| FX-ACC-0240 | NAJD | lifting_accessory chain sling | A defect DEF-ANIA-EXP-2026-0006 2026-09-19 → Retired (demobilised) | K-74 (A raised) |
| FX-ACC-0219 | NAJD | lifting_accessory chain sling | line valid to **2026-10-03** (counts in K-73 on 09-30); expired at seed | AC86, Z4a |

### A.5 Defects (named)

| No. | Item | Cat. | Raised | Due | Status at seed |
|---|---|---|---|---|---|
| DEF-ANIA-EXP-2026-0003 | FX-EX-11 | B | 2026-08-21 | 2026-09-20 | Open (overdue; item Out of Service) |
| DEF-ANIA-EXP-2026-0004 | WRS-NJ-0117 | A | 2026-09-11 (INC-ANIA-EXP-2026-0150) | — | Closed (destroyed) 2026-09-12 |
| DEF-ANIA-EXP-2026-0005 | NJ-MC-02 (worn hook latch spring, TPI due 2026-10-31) | B | 2026-09-24 | **2026-10-24** | Open (Z5a) |
| DEF-ANIA-EXP-2026-0006 | FX-ACC-0240 | A | 2026-09-19 | — | Closed (destroyed) |
| DEF-ANIA-EXP-2026-0007 | RW-MEWP-07 | A | 2026-09-26 | — | Open; rectification not recorded |
| DEF-ANIA-EXP-2026-0008 | FX-TH-04 | A | 2026-09-22 (TPI fail) | — | Open |

### A.6 Scaffolds (ANIA-EXP, zone Z-PIERB unless stated)

| No. | Tag | Owner | Height · type | Last inspection | Tag status at seed |
|---|---|---|---|---|---|
| SCF-ANIA-EXP-0142 | SC-0142 | SAHARA | 14.00 m · independent tied | 2026-10-01 green (Ferdinand Reyes); previous 2026-09-24 green | green → 2026-10-07 (Z6) |
| SCF-ANIA-EXP-0150 | SC-0150 | SAHARA | 8.00 m · mobile tower | 2026-09-29 **red** (missing toe-boards, base plate on sand) | red (Closed); excluded from K-81 |
| SCF-ANIA-EXP-0151 | SC-0151 | NAJD | 6.00 m · birdcage | 2026-10-02 **yellow** "harness and lanyard required — guardrail removed at loading point" | yellow → 2026-10-08 |
| SC-0160, SC-0161, SC-0162 (bulk) | — | RAWABI | — | last valid to 2026-09-28 / 09-29 / 09-29 | expired at 2026-09-30 (K-75 · K-81) |

### A.7 Personnel certificates (named)

| Worker | Type · scope | Cert no. (TPI) | Issued → valid_until | Status at seed |
|---|---|---|---|---|
| WKR-000019 Zaheer Abbas (RAWABI) | CRANE-OPERATOR [mobile_crane, crawler_crane] ≤ 60.000 t | AICC-OP-TEST-24-0412 (AICC) | 2024-04-01 → 2027-03-31 | in force; id_match matched |
| WKR-000102 Ali Hassan (QIMMA) | CRANE-OPERATOR [tower_crane] ≤ 16.000 t | AICC-OP-TEST-25-0815 | 2025-08-15 → 2028-08-14 | in force |
| WKR-000108 Joel Bautista (QIMMA) | RIGGER level 2 | AICC-RG-TEST-23-1021 | 2023-10-21 → **2026-10-20** | in force; 14-day alert today (Z2a) |
| WKR-000108 Joel Bautista | SIGNALLER | AICC-SG-TEST-25-0303 | 2025-03-03 → 2028-03-02 | in force |
| WKR-000009 Osman Idris (NAJD) | RIGGER level 1 | AICC-RG-TEST-24-0601 | 2024-06-01 → 2027-05-31 | in force |
| WKR-000104 Bikash Rai (NAJD) | RIGGER level 1 | AICC-RG-TEST-23-0901 | 2023-09-01 → 2026-08-31 | Expired; TRADE_CERT_MISSING |
| WKR-000018 Salem Al-Harthi | GAS-TESTER | DSPC-GT-TEST-26-0420 (DSPC) | 2026-04-20 → 2028-04-19 | in force (Z2c) |
| WKR-000020 Vinod | RADIOGRAPHER level II | FNDT-RT-TEST-22-0601 (FNDT) | 2022-06-01 → 2027-05-31 | in force |
| WKR-000001 Imran Hussain (NAJD) | SCAFFOLDER basic | DSPC-SC-TEST-21-1011 | 2021-10-11 → **2026-10-10** | in force; renewal DSPC-SC-TEST-26-1002 Submitted 2026-10-04 08:30, verification due 2026-10-07 (Z2d) |
| WKR-000022 Nadeem Akhtar / نديم أختر (SAHARA, scaffolder) | SCAFFOLDER | QC-SC-TEST-26-0777 (QUICKCERT) | submitted 2026-09-15 | **Rejected** (verification not_found 2026-09-17); **certification ban** all types from 2026-09-17, review 2027-03-17 |
| WKR-000023 Ferdinand Reyes / فرديناند رييس (SAHARA, scaffold inspector) | SCAFFOLD-INSPECTOR | DSPC-SI-TEST-25-0110 | 2025-01-10 → 2030-01-09 | in force |
| Rajesh Nair (Phase 3 plant operator) | PLANT-OPERATOR [excavator] | AICC-PO-TEST-25-0505 | 2025-05-05 → 2028-05-04 | in force |

### A.8 Bans, blacklists, hook policy state
- Equipment blacklist: SH-TH-02 (2026-09-05, Faisal).
- Certification ban: WKR-000022 (2026-09-17, Faisal).
- TPI blacklist: QUICKCERT (2026-09-20, Faisal).
- Hook policy state, for each project × kind (`personnel_certificate`, `equipment_certificate`): provider_registered_on 2026-10-01, stage transition, critical_block_from 2026-10-08, general_block_from 2026-10-31, deferral_used false.

### A.9 Settings
All Phase 4 settings are at the defaults in §3.17. `require_client_approved_tpi` = false, `unverified_acceptance_hours` = 0, `lifting_gear_colour_scheme.enabled` = false.

### A.10 Bulk volumes (as of 2026-09-30, reproducing Z11)

| Population | ANIA-EXP | RBT-52 |
|---|---|---|
| On Site non-scaffold deployments (K-72 denominator) | 186 = mobile_crane 6, crawler_crane 1, mewp 14, forklift 8, telehandler 6, excavator 18, man_basket 2, pressure_vessel 9, lifting_accessory 122. RAWABI tree 120 (all 5 invalid items in A.4), GULFPAVE + SAHARA 66 (all valid) | 50 = tower_crane 1, mobile_crane 2, construction_hoist 2, mewp 4, forklift 1, telehandler 2, man_basket 1, lifting_accessory 34, pressure_vessel 3 |
| Valid certificate | 181 (RAWABI tree 115 → 95.833 %, so E10 for the tree too) | 49 (DL-MC-01 not) |
| Valid, valid_until 2026-09-30…2026-10-30 (K-73) | 11 (FX-ACC-0219 + 10 bulk) | 4 bulk |
| Out of Service · A defects raised in Sep (K-74) | 3 (RW-MEWP-07, FX-TH-04, FX-EX-11) · 4 (0004, 0006, 0007, 0008) | 0 · 0 |
| Equipment overdue · scaffolds expired (K-75) | 2 (FX-ACC-0201, FX-FL-06) · 3 (SC-0160…0162) | 1 (DL-MC-01) · 0 |
| Mobilised deployments by mapped trade · with in-force certificate (K-76) | crane_operator 14 · 13; rigger 46 · 44 (Bikash Rai + 1 bulk not); scaffolder 160 · 152 (Nadeem Akhtar + 7 bulk not) → 209 / 220 | 6 · 6; 18 · 17; 24 · 23 → 46 / 48 |
| In-force certificates of Mobilised workers expiring ≤ 30 days (K-77) | 17 (incl. Imran Hussain SCAFFOLDER) | 5 (incl. Joel Bautista RIGGER) |
| Blacklisted · banned · TPIs (K-78) | 1 · 1 · 1 | 0 · 0 · 1 |
| Certificates submitted in Sep (eligible) · verified in time · failed (K-79) | 148 · 131 · 1 (QC-SC-TEST-26-0777) | 40 · 37 · 0 |
| B defects due in Sep · closed on time (K-80) | 12 · 10 (FX-EX-11 open; 1 bulk closed 1 day late) | 3 · 3 |
| In Use scaffolds (excl. red / under erection) · green or yellow (K-81) | 96 · 93 | 22 · 22 |

## Change log

| Version | Date | Author | Change |
|---|---|---|---|
| v1.0 | 2026-10-08 | HSE Consultant Agent | First issue. §1–§11, Appendix A. Capabilities 105–124, KPIs K-72…K-81, warnings E10–E11, AI tool T16, charts C16–C18, QR kind EQ. Earlier-spec changes in §11 applied the same day (1-dashboard v1.3, 2-access-permits v1.2, 3-ptw v1.1); seed clock tied to the shared `HSE_CLOCK_AT` 2026-10-06 10:00 Riyadh. |
