# Module Spec — Phase 2: Site / Airport Access Permits

**Version:** v1.2 · **Date:** 2026-10-08 · **Author:** HSE Consultant Agent · **Status:** Draft for HSE Manager review
**Builds on:** `0-foundation.md` v1.0 (Project, Site, Zone incl. airside attributes, Contractor, Project engagement, User, Role assignment, Audit log, settings, roles §3.8, permission matrix §5.10 rows 1–19, PDPL P1–P13) and `1-dashboard.md` v1.0 (matrix rows 20–45, KPI catalogue K-01…K-47, leading warnings E1–E4, action panel, expiring-items endpoint, AI tools T1–T13, P1-x rules).
**Covers (build order):** 2.1 Worker register & project deployment · 2.2 Site induction & project access card · 2.3 Zone access profiles & eligibility engine (incl. Phase 3/4/5 hooks) · 2.4 Airport ID pass applications & passes (sponsor, background check, categories, area/colour codes, escort) · 2.5 Airside driving permits (ADP) & offences · 2.6 Vehicle register & airside vehicle permits (AVP) · 2.7 Airside works clearances: NOTAM-dependent works & GACA obstacle/crane clearances · 2.8 Work-area access permits (WAP) & operational suspensions (LVP etc.) · 2.9 Credential lifecycle: validity, suspension, revocation, return, loss · 2.10 Gate/access check (QR verify) · 2.11 KPIs, alerts and dashboard feeds.
**Deliberately not in Phase 2 (hooks only, §5.3):** Phase 3 PTW (hazardous-work permits incl. the "airside works" PTW type, JSA, isolations, SIMOPS) — Phase 2 only says *who may be in which zone, when, with which vehicles*. Phase 4 third-party certification (crane/MEWP/forklift certificates, operator/rigger cards, blacklisting of personnel certificates). Phase 5 training matrix (AVSEC awareness, airside driver course, WAH etc.). Phase 6 medical fitness, heat stress, emergency.

Conventions: `VERIFY` = clause/number/deadline to be confirmed against current official text or the airport operator's rules. `ASSUMPTION` = Consultant default; HSE Manager may override (§10). "Must" = enforced server-side. Rule prefixes: WK worker, IN induction, ZP zone profile/eligibility, HK hooks, AP airport pass, DP ADP, VP vehicle/AVP, NT NOTAM, OB obstacle, WA work-area permit, LC lifecycle, GC gate check, P2- PDPL, KA KPI. Error codes are stable strings (Phase 0 rule 48).

**Important boundary:** the airport operator's own security ID system and AVSEC screening remain the legal access control at airside security checkpoints. The platform tracks applications and credentials, enforces the project's own rules (induction, WAP, NOTAM, clearance) and gives a pre-check verdict at contractor gates; it never replaces or overrides the operator's decision (rule AP-1).

---

## 1. Purpose

On an airport project the HSE Manager must be able to prove, for any person or vehicle in any zone at any time, that they were inducted, held a valid airport pass for that area (or were escorted), held a valid airside driving or vehicle permit, worked under an approved work-area permit, and — where the works touched the movement area, an ILS critical/sensitive area or the obstacle limitation surfaces — that a NOTAM and a GACA/operator obstacle clearance covered them. On a high-rise project the same applies in a lighter form: nobody enters without a valid site induction. Today this lives in spreadsheets, pass-office emails and paper registers, expiries are missed, unreturned passes cost fines, and gate guards cannot tell a lapsed induction from a valid one. Phase 2 gives one worker register (reused by PTW, certification and training later), records every access credential with its dependencies and validity, blocks what is not valid, lets gates verify a QR card in seconds, and feeds expiring items and access leading indicators to the dashboard.

## 2. Regulatory basis

| # | Source | What it drives here |
|---|---|---|
| R1 | **ICAO Annex 17** (Security), ch. 4.2 — access control to security restricted areas (SRA), identification systems, background checks before unescorted access and recurrent checks, escort of persons without unescorted access; ch. 3.4/4.2 security awareness training before ID issue `VERIFY` standard numbers in current amendment (Amdt 18) | Pass categories, escort rules, background-check status and recheck, AVSEC training hook |
| R2 | **KSA National Civil Aviation Security Program (NCASP)** issued by GACA, and the airport operator's Airport Security Programme / ID pass procedures (e.g. Matarat / airport cluster pass office rules) `VERIFY` document names, pass validity limits, lost-pass reporting time, unreturned-pass penalties | Pass validity caps, return/loss rules, sponsor requirements; strictest-wins source |
| R3 | **ICAO Annex 14 Vol I** — ch. 4 (obstacle limitation surfaces), ch. 6 (marking and lighting of obstacles and of vehicles/mobile objects on the movement area), ch. 9 (aerodrome operational services incl. vehicle operations; works on the movement area) `VERIFY` section numbers | Obstacle clearance, vehicle beacon/marking checklist, works in movement area |
| R4 | **ICAO Doc 9137 Airport Services Manual** Part 6 (Control of Obstacles) and Part 8 (Airport Operational Services — airside vehicle control, driver permits) | ADP categories/tests, AVP inspection, escort vehicles |
| R5 | **ICAO Doc 9981 PANS-Aerodromes** — aerodrome works safety, works on the movement area, coordination with ATS `VERIFY` chapter | WAP rules, Works Safety Plan reference, FOD hand-back |
| R6 | **ICAO Doc 9870** Manual on the Prevention of Runway Incursions — driver training, RTF competence for manoeuvring area, runway-crossing discipline | ADP manoeuvring category, offence OFF-05 immediate suspension |
| R7 | **ICAO Annex 10 Vol I** (ILS critical and sensitive areas, Attachment C) and LVP practice (Doc 9365) `VERIFY` | ILS-zone WAP conditions, LVP withdrawal |
| R8 | **ICAO Annex 15 / Doc 10066 PANS-AIM** — NOTAM format and times in UTC, AIRAC cycle (28 days; submission lead) `VERIFY` lead days | NOTAM record, lead-time rules |
| R9 | **GACAR Part 139** (aerodrome certification) and GACA obstruction / airspace evaluation requirements for structures and temporary obstacles (cranes) `VERIFY` part number and notification thresholds; KSA AIS/NOTAM office operated by **SANS** (Saudi Air Navigation Services) `VERIFY` | Obstacle clearance workflow, thresholds, NOTAM routing via airport operator |
| R10 | **MHRSD Labour Law** & OSH regulations — employer duty to inform/train workers on hazards before work; prohibition of minors in hazardous work `VERIFY` articles | Induction before access; adult attestation |
| R11 | **KSA Residency (Iqama) rules** — employer must keep residents' Iqama valid `VERIFY` | ID expiry blocks access |
| R12 | **KSA Traffic Law** — driving licence classes, vehicle registration (Istimara), periodic technical inspection (MVPI / "Fahas"), compulsory motor insurance `VERIFY` classes and whether the Saudi licence number equals the holder's ID number | ADP licence checks, AVP document checks |
| R13 | **ISO 45001:2018** cl. 7.2 (competence), 7.3 (awareness), 7.4 (communication — language), 8.1.4 (contractors) | Induction content/language/test, contractor control |
| R14 | **PDPL** + Implementing Regulations (Phase 0 R1/R2); NCA ECC (Phase 0 R3) | ID encryption/masking, background data, photos, gate logs, retention |
| R15 | Client / airport operator airside rules (Airside Driving Rules, Works on Airside procedure, Contractor Access procedure) | Escort ratios, speed limits, offence points, lead times — entered as settings; strictest wins |

Strictest-wins applied in this spec:
- Pass, ADP and AVP **effective validity** is the minimum of every applicable limit (card expiry, ID expiry, deployment end, background-check recheck, licence/registration/insurance expiry, client cap) — §6 X2/X3.
- Where the operator allows escorted persons to drive with an escort, the platform still refuses an ADP to an escorted-pass holder (DP-3) unless the HSE Manager changes the setting.
- Escort ratios, lead times and validity caps take the most restrictive of operator, client and platform default.
- Contractor suspension (Phase 0 rule 28: "later phases additionally block permits") blocks new applications and WAPs and denies gate checks by default (setting `suspended_contractor_gate = deny`).

## 3. Entities & fields

PDPL column: **none / personal / sensitive** (Phase 0 P1–P2). Every entity carries Phase 0 system fields (id UUID, created_at/by, updated_at/by), is audited (Phase 0 rule 35) and stores `seed_fake` (bool). AR label shown in UI.

### 3.1 Worker (person master, org-wide) — العامل / الشخص

One record per real person across all projects. Reused by Phase 3 (PTW crew, issuer competence), Phase 4 (personnel certificates) and Phase 5 (training records). Phase 1 injury case gains an optional `worker_id` (nullable FK, pre-fills name/ID/trade; no Phase 1 rule changes).

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| worker_no | رقم العامل | string | sys | `WKR-` + 6 digits, sequential, immutable | WKR-000002 | none |
| person_type | فئة الشخص | enum | Y | `contractor_worker` عامل مقاول, `client_pmc_staff` موظف العميل/الاستشاري, `visitor` زائر | contractor_worker | none |
| full_name_en / full_name_ar | الاسم الكامل | string(120) ×2 | Y/Y | name_ar Arabic script; as on ID | Rajesh Nair / راجيش ناير | personal |
| id_type | نوع الهوية | enum | Y | `iqama` إقامة, `national_id` هوية وطنية, `gcc_id` هوية خليجية, `passport` جواز سفر (visitors / not-yet-resident only) | iqama | personal |
| id_number | رقم الهوية | string | Y | iqama `^2\d{9}$`, national_id `^1\d{9}$`, gcc_id `^[A-Z0-9]{6,15}$`, passport `^[A-Z0-9]{6,9}$`; Saudi IDs pass the Luhn-style check digit `VERIFY` algorithm; **encrypted at rest (app-level), masked in lists** (§5.12) | 2000001002 → `2*******02` | **sensitive** (P2) |
| id_number_bidx | — | string | sys | HMAC-SHA256(id_type ‖ normalised id_number ‖ passport_country) with a key separate from the encryption key; unique; never returned | — | sensitive (derived) |
| passport_country | دولة الجواز | ISO alpha-2 | cond. | required iff id_type = passport | GB | personal |
| id_expiry_date | تاريخ انتهاء الهوية | date | Y | > today at creation (warning only on edit) | 2027-03-14 | personal |
| nationality | الجنسية | ISO alpha-2 | Y | needed by pass office; analysis only as aggregates (P1-4) | IN | personal |
| adult_attestation | إقرار بلوغ 18 سنة | bool | Y | must be true (rule WK-6); no date of birth stored (minimisation) | true | personal |
| photo | الصورة الشخصية | file (jpg/png ≤ 2 MB, ≥ 400×400) | Y for airside/pass, else N | stored in encrypted bucket; served via signed URL ≤ 5 min; never used for face recognition | — | personal |
| primary_language | لغة العامل | enum | Y | `ar`, `en`, `ur`, `hi`, `bn`, `ne`, `tl`, `ml`, `ta`, `other` (for induction delivery) | ml | personal |
| user_id | حساب المستخدم | FK | N | link when the person is also a platform user (e.g. HSE Officer going airside) | — | personal |
| status | الحالة | enum | Y | §4.1 | active | none |
| ban_reason | سبب الحظر | text(500) | cond. | required iff status = banned; P3 hint "no medical or criminal details" | — | personal |

### 3.2 Worker deployment (worker on a project) — تعيين العامل في المشروع

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| worker_id, project_id | العامل، المشروع | FK | Y | one non-demobilised deployment per worker per project | WKR-000002, ANIA-EXP | none |
| engagement_id | جهة العمل | FK | cond. | required iff person_type = contractor_worker; engagement on project, contractor Approved | GULFPAVE@ANIA-EXP | personal |
| employee_no | الرقم الوظيفي | string(20) | N | unique within engagement | GP-0412 | personal |
| trade | المهنة | enum | Y | Phase 1 list T | plant_operator | personal |
| site_ids | المواقع | FK[] | Y | ⊆ engagement.site_ids (contractor) or project sites | [S-AIR] | none |
| mobilised_on | تاريخ التعبئة | date | Y | ≥ engagement mobilisation_date | 2025-04-20 | personal |
| planned_demob_on | تاريخ التسريح المخطط | date | N | ≥ mobilised_on; ≤ engagement demobilisation_date if set | — | personal |
| demobilised_on | تاريخ التسريح الفعلي | date | cond. | set by Demobilise transition | — | personal |
| access_card_token | رمز بطاقة الدخول | string | sys | §3.20; one active token per deployment | — | none (opaque) |
| access_card_issued_on / reissue_count | تاريخ إصدار البطاقة / عدد مرات الإعادة | date / int | sys | — | 2025-04-20 / 0 | none |
| status | الحالة | enum | Y | §4.2 | mobilised | none |

### 3.3 Induction course (reference, per project) — دورة التعريف بالسلامة

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| code | الرمز | string(10) | Y | unique within project | AIR | none |
| induction_type | نوع التعريف | enum | Y | `general_site` تعريف عام بالموقع, `airside` تعريف الجانب الجوي, `zone_specific` تعريف خاص بمنطقة, `visitor` تعريف الزوار | airside | none |
| name_en / name_ar | الاسم | string(150) ×2 | Y | — | Airside Safety & FOD Awareness / السلامة في الجانب الجوي والتوعية بالأجسام الغريبة | none |
| version | الإصدار | string(10) | Y | `^\d+\.\d+$` | 2.0 | none |
| requires_reinduction | يتطلب إعادة التعريف | bool | Y | set on a new major version (rule IN-9) | false | none |
| validity_months | مدة الصلاحية (أشهر) | int | Y | 1–36; visitor type uses `validity_days` | 12 | none |
| validity_days | مدة الصلاحية (أيام) | int | cond. | visitor only, 1–7 | 1 | none |
| min_duration_minutes | الحد الأدنى للمدة | int | Y | ≥ 15 | 90 | none |
| test_required / pass_mark_pct | اختبار مطلوب / درجة النجاح | bool / int | Y | pass_mark 50–100, default setting 80 | true / 80 | none |
| languages_offered | اللغات المتاحة | enum[] | Y | ≥ 1 from §3.1 primary_language | [ar, en, ur, hi, bn, ne, tl, ml] | none |
| prerequisite_codes | المتطلبات المسبقة | string[] | N | other course codes of same project (e.g. AIR requires GEN) | [GEN] | none |
| delivered_by_roles | جهات التقديم | enum[] | Y | subset of {hse_manager, hse_officer, contractor_hse_rep}; airside and zone_specific on airside zones exclude contractor_hse_rep (IN-3) | [hse_officer] | none |
| active | فعال | bool | Y | — | true | none |

### 3.4 Induction record — سجل التعريف بالسلامة

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| induction_no | رقم التعريف | string | sys | `IND-<project>-<yyyy>-<nnnnn>` | IND-ANIA-EXP-2026-03117 | none |
| worker_id, project_id, course_id | العامل، المشروع، الدورة | FK | Y | worker has a deployment on project (status mobilised or pending_induction) | WKR-000004, ANIA-EXP, AIR | personal |
| course_version | إصدار الدورة | string | sys | copied from course at completion | 2.0 | none |
| session_ref | مرجع الجلسة | string(30) | N | groups attendees | AIR-2025-10-14-AM | none |
| delivered_at | تاريخ ووقت التقديم | timestamptz | Y | ≤ now | 2025-10-14T06:00Z | personal |
| delivered_by_user_id | المقدِّم | FK | Y | role ∈ course.delivered_by_roles on project; ≠ the worker's own user | Noura | personal |
| delivery_language | لغة التقديم | enum | Y | ∈ course.languages_offered; warning if ≠ worker.primary_language and interpreter_used = false | bn | personal |
| interpreter_used | مترجم | bool | Y | — | true | none |
| duration_minutes | المدة | int | Y | ≥ course.min_duration_minutes | 95 | none |
| test_score_pct | درجة الاختبار | decimal(5,2) | cond. | required iff test_required; 0–100 | 86.00 | personal |
| attempt_no | رقم المحاولة | int | sys | 1 + previous attempts of same course & project within 30 days | 1 | personal |
| result | النتيجة | enum | Y | `passed` ناجح, `failed` راسب (derived: score ≥ pass mark when test required; otherwise attendance confirmed = passed) | passed | personal |
| privacy_notice_version | إصدار إشعار الخصوصية | string | Y | worker privacy notice (rule P2-9) read out/given in delivery language | WPN-1.0 | personal |
| signature | التوقيع | file / drawn image | Y | attendance + privacy acknowledgement | — | personal |
| valid_from / valid_until | ساري من / إلى | date | sys | §6 X1; null if failed | 2025-10-14 / 2026-10-13 | none |
| helmet_sticker_no | رقم ملصق الخوذة | string(20) | N | unique within project when set | AIR-00877 | none |
| status | الحالة | enum | Y | §4.3 | valid | none |

### 3.5 Zone access profile (1:1 with zone) — متطلبات الدخول للمنطقة

Created automatically with defaults (rule ZP-1) when the zone is created; editable by capability 81. Extends Phase 0 zones without changing their table.

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| zone_id | المنطقة | FK | Y | unique | Z-TWB | none |
| required_inductions | التعريفات المطلوبة | course code[] | Y | ≥ 1 (GEN of project) | [GEN, AIR] | none |
| airport_pass_area_code | رمز منطقة تصريح المطار | string | cond. | required iff zone airside with security_restricted_area = true; from list AP-AREA | M | none |
| access_permit_required | يتطلب تصريح دخول منطقة | bool | Y | default per ZP-1 | true | none |
| adp_category_required | فئة تصريح القيادة المطلوبة | enum | cond. | required iff zone.adp_required; `apron`, `manoeuvring`, `airside_roads` | manoeuvring | none |
| avp_area_required | منطقة تصريح المركبة | enum | cond. | same values; required iff airside | manoeuvring | none |
| escort_ratio_max | الحد الأقصى للمرافقة | int | cond. | ≤ project setting for that area kind (stricter only) | 2 | none |
| lvp_withdrawal_required | الانسحاب عند الرؤية المنخفضة | bool | Y | default per ZP-1 | true | none |
| ils_outage_notam_required | يتطلب NOTAM لتعطيل ILS | bool | Y | default true iff airside_area ∈ {ils_critical} | false | none |
| hook_requirements | متطلبات المراحل اللاحقة | list of {kind, code} | N | kinds `training_course` (Phase 5), `personnel_certificate` (Phase 4), `equipment_certificate` (Phase 4), `medical_fitness` (Phase 6); codes free until those modules publish their lists | [{training_course, AVSEC-AWR}] | none |

### 3.6 Airport pass category (reference, per airport project) — فئات تصاريح المطار (AP-CAT)

| Field | AR label | Type | Req | Validation | Example |
|---|---|---|---|---|---|
| code | الرمز | string(8) | Y | unique within project | PERM |
| name_en / name_ar | الاسم | string ×2 | Y | — | Permanent Airport ID / تصريح مطار دائم |
| escorted | بمرافقة | bool | Y | true = holder must be escorted in SRA | false |
| background_check_required | يتطلب تحققاً أمنياً | bool | Y | true for unescorted categories (rule AP-4) | true |
| max_validity_days | أقصى صلاحية (أيام) | int | Y | ≤ setting `pass_max_validity_months` × 31 | 730 |
| card_colour | لون البطاقة | enum | Y | `red`, `blue`, `green`, `yellow`, `orange`, `white`, `grey` | red |
| allows_adp | يسمح بتصريح قيادة | bool | Y | false when escorted (DP-3) | true |

### 3.7 Airport pass area code (reference, per airport project) — رموز مناطق تصريح المطار (AP-AREA)

| Field | AR label | Type | Req | Validation | Example |
|---|---|---|---|---|---|
| code | الرمز | string(4) | Y | unique within project; as printed on the operator's card | A |
| name_en / name_ar | الاسم | string ×2 | Y | — | Apron & Stands / الساحات ومواقف الطائرات |
| colour | اللون | enum | Y | as AP-CAT colours | red |
| area_kind | نوع المنطقة | enum | Y | `apron`, `manoeuvring`, `terminal_airside`, `airside_roads`, `other_sra` | apron |
| zone_ids | المناطق المشمولة | FK[] | N | airside zones of the project | [Z-APR-21] |

### 3.8 Airport pass application — طلب تصريح دخول المطار

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| application_no | رقم الطلب | string | sys | `APA-<project>-<yyyy>-<nnnn>` | APA-ANIA-EXP-2026-0142 | none |
| application_type | نوع الطلب | enum | Y | `new` جديد, `renewal` تجديد, `replacement_lost` بدل فاقد, `replacement_damaged` بدل تالف, `area_change` تعديل المناطق | new | none |
| worker_id / deployment_id | العامل | FK | Y | deployment mobilised on this airport project | WKR-000004 | personal |
| sponsor_engagement_id | المقاول الراعي | FK | Y | = deployment.engagement_id (contractor) or null for client staff | GULFPAVE@ANIA-EXP | none |
| sponsor_letter_ref | مرجع خطاب الرعاية | string(40) | Y | — | GP/SEC/2026/118 | none |
| client_sponsor_user_id | الراعي من جهة العميل | FK | cond. | set at Endorse; user with employer_type ∈ {client, pmc_consultant} ASSUMPTION | Noura | personal |
| pass_category | فئة التصريح | code | Y | AP-CAT | TEMP-E | none |
| requested_area_codes | المناطق المطلوبة | code[] | Y | ≥ 1 from AP-AREA; each must map to a zone in deployment.site_ids or justification ≥ 20 chars | [A] | none |
| requested_valid_until | الصلاحية المطلوبة حتى | date | Y | ≤ min(id_expiry_date, planned_demob_on, engagement demob, project planned_end_date, today + category max_validity_days) — rule AP-6 | 2026-11-12 | none |
| justification | المبرر | text(500) | Y | P3 hint | Night paving crew, TWY B rehabilitation | none |
| id_copy | صورة الهوية | file | Y for new/renewal | encrypted bucket; auto-deleted `id_copy_retention_days` after Issued/Refused/Withdrawn (P2-5) | — | **sensitive** |
| prerequisite_snapshot | فحص المتطلبات | JSON | sys | eligibility result (§5.3 ZP-5) at Endorse: inductions, hooks | — | none |
| lodged_at / authority_ref | تاريخ التقديم للجهة / مرجع الجهة | timestamptz / string(40) | cond. | set at Lodged | 2026-09-28 / OEXX-PASS-TEST-55120 | none |
| background_check_status | حالة التحقق الأمني | enum | cond. | `not_required` غير مطلوب, `submitted` مقدَّم, `in_progress` قيد الإجراء, `cleared` مجتاز, `not_cleared` غير مجتاز, `expired` منتهي | in_progress | **sensitive** |
| background_check_date / recheck_due | تاريخ التحقق / موعد إعادة التحقق | date | cond. | recheck_due = date + `bg_recheck_months` (§6 X2) | — | **sensitive** |
| outcome_note | ملاحظة النتيجة | text(300) | N | must not contain the security reason (P2-4) | — | personal |
| status | الحالة | enum | Y | §4.4 | lodged | none |

### 3.9 Airport pass (issued credential) — تصريح دخول المطار

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| pass_no | رقم التصريح | string(30) | Y | as printed by the authority; unique within project | ANIA-AP-26-01877 | personal |
| application_id, worker_id, deployment_id | الطلب، العامل | FK | Y | application status Approved | — | personal |
| pass_category | الفئة | code | Y | = application | PERM | none |
| area_codes | المناطق الممنوحة | code[] | Y | ⊆ requested (authority may grant fewer) | [A, M] | none |
| card_colour | اللون | enum | sys | from category | red | none |
| escorted | بمرافقة | bool | sys | from category | false | none |
| issued_on / card_expiry_date | تاريخ الإصدار / الانتهاء على البطاقة | date | Y | expiry > issued_on | 2025-06-01 / 2027-05-31 | none |
| effective_valid_until | الصلاحية الفعلية | date | sys | §6 X2 (recomputed on any dependency change) | 2027-03-14 | none |
| validity_status | حالة الصلاحية | enum | Y | §4.5 | active | none |
| custody_status | حالة الحيازة | enum | Y | §4.9 (`held`, `return_due`, `returned`, `lost`) | held | none |
| return_due_on / returned_at / received_by | موعد الإرجاع / تاريخ الإرجاع / المستلم | date / timestamptz / FK | cond. | §5.9 | — | none |
| lost_reported_at / authority_notified_at | تاريخ الإبلاغ عن الفقد / إبلاغ الجهة | timestamptz | cond. | §5.9 LC-12 | — | none |

### 3.10 Airside driving permit (ADP) — تصريح القيادة في الجانب الجوي

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| adp_no | رقم التصريح | string(30) | Y | unique within project | ADP-OEXX-26-0042 | personal |
| worker_id, deployment_id | العامل | FK | Y | holds active unescorted pass (DP-3) | WKR-000002 | personal |
| category | الفئة | enum | Y | `apron` الساحات, `manoeuvring` منطقة المناورة (incl. apron & roads), `airside_roads` طرق الجانب الجوي | manoeuvring | none |
| vehicle_classes | فئات المركبات | enum[] | Y | `light` خفيفة, `heavy` ثقيلة, `special_plant` معدات خاصة | [light, special_plant] | none |
| licence_issuer | جهة إصدار الرخصة | enum | Y | `ksa`, `gcc`, `international` (international not accepted for residents, DP-4) | ksa | personal |
| licence_class | فئة الرخصة | enum | Y | `private` خاصة, `public_transport` نقل عام, `heavy_transport` نقل ثقيل, `heavy_equipment` معدات ثقيلة, `motorcycle` دراجة `VERIFY` R12 classes | heavy_equipment | personal |
| licence_expiry_date | انتهاء الرخصة | date | Y | > today at issue | 2029-06-30 | personal |
| licence_number | رقم الرخصة | — | — | **not stored** for KSA licences (= holder's ID number `VERIFY` R12); minimisation | — | — |
| theory_test_date / score_pct | الاختبار النظري | date / decimal | Y | score ≥ setting `adp_theory_pass_pct` (80) | 2026-01-20 / 88.00 | personal |
| practical_test_date / result / examiner | الاختبار العملي | date / enum / string(120) | Y | result `passed`; examiner = airport ops/authorised driving assessor | 2026-01-27 / passed / Airside Ops (fake) | personal |
| rtf_competence | كفاءة الاتصال اللاسلكي | bool | cond. | must be true for manoeuvring (DP-5) | true | personal |
| issued_on / own_valid_until | الإصدار / الانتهاء | date | Y | own_valid_until ≤ issued_on + `adp_validity_months` | 2026-02-02 / 2028-02-01 | none |
| effective_valid_until | الصلاحية الفعلية | date | sys | §6 X3 | 2027-03-14 | none |
| points_12m | النقاط خلال 12 شهراً | int | sys | §6 X5 | 0 | personal |
| validity_status / custody_status | الحالة / الحيازة | enum | Y | §4.5 / §4.9 | active / held | none |

### 3.11 Airside driving offence — مخالفة قيادة في الجانب الجوي

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| offence_no | رقم المخالفة | string | sys | `OFF-<project>-<yyyy>-<nnnn>` | OFF-ANIA-EXP-2026-0031 | none |
| adp_id / worker_id | التصريح / العامل | FK | Y | — | ADP-…-0057 | personal |
| offence_code | نوع المخالفة | code | Y | list OFF (§3.21) | OFF-01 | personal |
| offence_at / zone_id | الوقت / المنطقة | timestamptz / FK | Y | zone airside | 2026-09-14T22:40Z / Z-APR-21 | personal |
| vehicle_id | المركبة | FK | N | — | VEH-0002 | none |
| points | النقاط | int | sys | from list OFF at offence time | 3 | personal |
| reported_by_user_id / evidence | المُبلِّغ / الدليل | FK / file[] | Y / N | — | Khalid | personal |
| incident_ref | مرجع الحادثة | FK | N | Phase 1 incident (e.g. runway incursion) | — | none |
| status | الحالة | enum | Y | `recorded` مسجلة, `disputed` معترض عليها, `upheld` مثبتة, `withdrawn` ملغاة; only recorded/upheld count points | upheld | personal |

### 3.12 Vehicle / mobile plant — المركبة / المعدة المتحركة

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| vehicle_no | رقم المركبة بالنظام | string | sys | `VEH-` + 4 digits per project | VEH-0002 | none |
| project_id, engagement_id | المشروع، المقاول المالك/المشغل | FK | Y | contractor Approved | GULFPAVE@ANIA-EXP | none |
| owner_type | نوع الملكية | enum | Y | `company` شركة, `rental` مستأجرة, `individual` فرد | company | none |
| category | الفئة | enum | Y | list VC (§3.21) | pickup | none |
| plate_type | نوع اللوحة | enum | Y | `private` خصوصي, `transport` نقل, `heavy_equipment` معدات ثقيلة, `none` بدون لوحة (unregistered plant) | private | none |
| plate_letters_ar / plate_letters_en / plate_digits | حروف/أرقام اللوحة | string(3) / string(3) / string(4) | cond. | required iff plate_type ≠ none; Saudi format 3 letters + 1–4 digits; unique per (letters, digits) | ح ط ر / H T R / 9012 | none; **personal iff owner_type = individual** |
| fleet_no / serial_or_vin | رقم الأسطول / الرقم التسلسلي أو الشاصي | string(20) / string(30) | Y / Y | VIN `^[A-HJ-NPR-Z0-9]{17}$` when road vehicle | GP-LV-07 / TESTVIN0000000002 | none |
| make_model / year / colour | الطراز / السنة / اللون | string / int / string | Y / Y / Y | year 1990–current+1 | Toyota Hilux / 2023 / white | none |
| travel_height_m | ارتفاع السير (م) | decimal(5,2) | Y | 0.5–20 | 1.90 | none |
| max_working_height_m_agl | أقصى ارتفاع تشغيلي (م) | decimal(6,2) | Y | ≥ travel_height_m; boom/mast fully extended incl. load & rigging (OB-2) | 1.90 | none |
| istimara_expiry | انتهاء الاستمارة | date | cond. | required iff plate_type ≠ none | 2027-04-30 | none |
| insurance_policy_no / insurance_expiry | وثيقة التأمين / انتهاؤها | string(40) / date | Y | airside third-party liability cover amount ≥ operator minimum `VERIFY` R2 | TEST-POL-0002 / 2026-10-20 | none |
| mvpi_expiry | انتهاء الفحص الدوري | date | cond. | required iff plate_type ≠ none (Fahas) | 2027-01-15 | none |
| status | الحالة | enum | Y | `active`, `off_site`, `withdrawn` | active | none |

### 3.13 Airside vehicle permit (AVP) — تصريح المركبة في الجانب الجوي

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| avp_no | رقم التصريح | string(30) | Y | unique within project | AVP-OEXX-26-0118 | none |
| vehicle_id | المركبة | FK | Y | one active AVP per vehicle | VEH-0002 | none |
| areas | المناطق | enum[] | Y | ⊆ {apron, manoeuvring, airside_roads} | [apron, manoeuvring] | none |
| inspection_date / inspector / result | الفحص | date / string(120) / enum | Y | result `passed` required to issue | 2026-02-26 / Airside Ops (fake) / passed | none |
| checklist | قائمة الفحص | map item → pass/fail/n.a. | Y | items: amber_beacon, company_marking, chequered_flag_or_marking (manoeuvring), radio_fitted (manoeuvring), fire_extinguisher, spill_kit, fod_bin, tyres_brakes, reverse_alarm, lights, no_loose_items, height_marking (if > 3 m); every item pass or n.a. (VP-4) | — | none |
| sticker_no / sticker_token | رقم الملصق / رمز QR | string(20) / string | Y / sys | §3.20 | AVP-S-0118 | none |
| issued_on / own_valid_until | الإصدار / الانتهاء | date | Y | ≤ issued_on + `avp_validity_months` | 2026-03-01 / 2027-02-28 | none |
| effective_valid_until | الصلاحية الفعلية | date | sys | min(own, istimara, insurance, mvpi, equipment-cert hook) — §6 X3 | 2026-10-20 | none |
| validity_status / custody_status | الحالة / الحيازة | enum | Y | §4.5 / §4.9 (custody = sticker removed & returned) | active / held | none |

### 3.14 NOTAM works clearance — طلب/سجل إشعار NOTAM للأعمال

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| ntm_no | الرقم | string | sys | `NTM-<project>-<yyyy>-<nnnn>` | NTM-ANIA-EXP-2026-0012 | none |
| zone_ids | المناطق | FK[] | Y | airside zones with notam_required_for_works = true | [Z-TWB] | none |
| works_impact | أثر الأعمال | enum[] | Y | `taxiway_closure` إغلاق ممر, `runway_closure` إغلاق مدرج, `declared_distances_change` تغيير المسافات المعلنة, `ils_outage` تعطيل ILS, `lighting_outage` تعطيل الإنارة, `stand_closure` إغلاق موقف, `obstacle` عائق, `other` | [taxiway_closure] | none |
| description_en / description_ar | الوصف | text(1000) | Y | — | TWY B closed between B2 and B4 for night paving | none |
| requested_start_utc / requested_end_utc | البداية/النهاية المطلوبة (UTC) | timestamptz | Y | end > start; lead per NT-2 | 2026-10-01T20:00Z / 2026-10-22T02:00Z | none |
| schedule_text | الجدول (البند D) | string(200) | N | e.g. `DAILY 2000-0200` | DAILY 2000-0200 | none |
| submitted_to_ops_at | تاريخ الإرسال لعمليات المطار | timestamptz | cond. | set at Submitted | 2026-09-22T07:00Z | none |
| notam_number | رقم NOTAM | string(12) | cond. | `^[A-Z]\d{4}/\d{2}$`; required at Issued | A0999/26 | none |
| notam_type | نوع NOTAM | enum | cond. | `N` new, `R` replace, `C` cancel | N | none |
| effective_from_utc / effective_to_utc | ساري من/إلى (UTC) | timestamptz | cond. | as issued (items B/C); `PERM` not allowed for works | 2026-10-01T20:00Z / 2026-10-22T02:00Z | none |
| item_e_text | نص البند E | text(2000) | N | copied from issued NOTAM | TWY B BTN B2 AND B4 CLSD DUE WIP | none |
| replaces_ntm_id | يحل محل | FK | cond. | iff notam_type = R | — | none |
| status | الحالة | enum | Y | §4.6 | issued | none |

### 3.15 Obstacle / crane clearance — موافقة العوائق والرافعات (GACA)

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| obs_no | الرقم | string | sys | `OBS-<project>-<yyyy>-<nnnn>` | OBS-ANIA-EXP-2026-0004 | none |
| project_id, zone_id | المشروع، المنطقة | FK | Y / N | zone required on airport projects; any project may raise one (OB-1) | Z-APR-21 | none |
| vehicle_id / equipment_desc | المعدة | FK / string(150) | one Y | vehicle from §3.12, or description until Phase 4 equipment register | VEH-0003 50 t mobile crane | none |
| equipment_item_id | المعدة في سجل المعدات | FK | N | v1.2: Phase 4 equipment item (`4-third-party-cert.md` §3.4); when set, Phase 4 configuration changes re-check this clearance (CF-4, OB-6) | EQP-000101 | none |
| equipment_type | نوع المعدة | enum | Y | `mobile_crane`, `tower_crane`, `crawler_crane`, `piling_rig`, `drilling_rig`, `mewp`, `concrete_pump_boom`, `excavator`, `temporary_structure`, `other` | mobile_crane | none |
| location_lat / location_lng | الإحداثيات | decimal(9,6) | Y | KSA bbox (Phase 0) ; within site radius 5 km ASSUMPTION | 24.951200, 46.701900 | none |
| location_desc | وصف الموقع | string(150) | Y | — | Stand 22, light mast LM-22 | none |
| ground_elevation_m_amsl | منسوب الأرض (م فوق سطح البحر) | decimal(7,2) | Y | 0–3000 | 612.40 | none |
| max_height_m_agl | أقصى ارتفاع (م فوق الأرض) | decimal(6,2) | Y | ≥ vehicle.max_working_height_m_agl when vehicle linked | 32.00 | none |
| top_elevation_m_amsl | منسوب القمة | decimal(7,2) | sys | §6 X4 | 644.40 | none |
| ols_surface | سطح الحد من العوائق | enum | cond. | `approach`, `take_off_climb`, `transitional`, `inner_horizontal`, `conical`, `inner_approach`, `inner_transitional`, `balked_landing`, `none_applicable`; required on airport projects | inner_horizontal | none |
| ols_limit_m_amsl | حد السطح (م فوق سطح البحر) | decimal(7,2) | cond. | default zone.ols_height_limit_m_amsl; point value from operator's OLS drawing overrides with `ols_source_ref` | 655.00 | none |
| ols_source_ref | مرجع مخطط OLS | string(40) | cond. | required when ols_limit differs from zone value | OEXX-OLS-DWG-TEST-03 | none |
| clearance_reasons | أسباب طلب الموافقة | enum[] | sys | §5.7 OB-3: `zone_height_exceeded`, `ols_penetration`, `within_ols_buffer`, `height_threshold`, `operator_requires` | [zone_height_exceeded] | none |
| penetration_m | مقدار الاختراق | decimal(6,2) | sys | max(0, top − ols_limit) | 0.00 | none |
| requested_from / requested_to | الفترة المطلوبة | date | Y | lead per OB-5 | 2026-10-04 / 2026-10-10 | none |
| submitted_at / authority_ref | تاريخ التقديم / مرجع الجهة | timestamptz / string(40) | cond. | — | GACA-OBS-TEST-0004 | none |
| decision | القرار | enum | cond. | `approved`, `approved_with_conditions`, `rejected` | approved_with_conditions | none |
| approved_max_height_m_agl / approved_top_m_amsl | الارتفاع المعتمد | decimal | cond. | ≤ requested | 32.00 / 644.40 | none |
| conditions | الشروط | enum[] + text | cond. | `obstruction_light` إنارة العائق, `day_marking` علامات نهارية, `lower_when_idle` إنزال الذراع عند التوقف, `lower_at_night` إنزال الذراع ليلاً, `notam_required` يتطلب NOTAM, `ats_coordination_each_lift` تنسيق مع المراقبة الجوية, `daylight_only` نهاراً فقط | [obstruction_light, lower_at_night] | none |
| valid_from / valid_to | ساري من/إلى | date | cond. | within requested window | 2026-10-04 / 2026-10-10 | none |
| linked_ntm_ids | NOTAM المرتبط | FK[] | cond. | required when conditions ∋ notam_required (OB-7) | — | none |
| status | الحالة | enum | Y | §4.7 | approved | none |

### 3.16 Work-area access permit (WAP) — تصريح دخول منطقة العمل

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| wap_no | رقم التصريح | string | sys | `WAP-<project>-<yyyy>-<nnnn>` | WAP-ANIA-EXP-2026-0031 | none |
| project_id, site_id, zone_ids | المشروع، الموقع، المناطق | FK | Y | ≥ 1 zone, all of one site, each with access_permit_required = true or chosen voluntarily | S-AIR, [Z-TWB] | none |
| engagement_id | المقاول | FK | Y | contractor Approved and not Suspended (WA-3) | GULFPAVE@ANIA-EXP | none |
| requested_by_user_id | مقدم الطلب | FK | Y | — | Ahmed (rep) | personal |
| supervisor_worker_id | المشرف المسؤول | FK | Y | crew member with role supervisor | WKR-000005 | personal |
| scope_en / scope_ar | نطاق العمل | text(500) | Y | — | Night asphalt paving TWY B (B2–B4) | none |
| works_safety_plan_ref | خطة سلامة الأعمال | string(40) | cond. | required iff any zone in_movement_area (WA-6); default zone value | WSP-TWB-007 | none |
| valid_from / valid_to | ساري من / إلى (تاريخ محلي) | date | Y | valid_to − valid_from + 1 ≤ `wap_max_days` | 2026-10-01 / 2026-10-21 | none |
| windows | فترات العمل اليومية | list {start_local, end_local, weekdays[]} | Y | 1–3 windows; end may be < start (crosses midnight, WA-9); weekdays Sun..Sat | [{23:00, 05:00, all}] | none |
| crew | الطاقم | list {worker_id, crew_role, escort_worker_id} | Y | crew_role `worker`, `supervisor`, `escort`, `driver`, `banksman`; escorted members need escort_worker_id (WA-11) | 9 persons | personal |
| vehicles | المركبات | list {vehicle_id, escort_vehicle_id, height_limited_to_m} | N | AVP or escort vehicle (WA-12); height_limited_to_m ≤ vehicle.max_working_height_m_agl, set only when a height limiter is fitted and locked (WA-8) | [VEH-0001, VEH-0002] | none |
| operator_permit_ref | مرجع تصريح مشغل المطار | string(40) | N | the airport operator's own airside works/access permit number, when the operator issues one (§10 Q18) | AOP-WP-TEST-2231 | none |
| linked_ntm_ids / linked_obs_ids | NOTAM / موافقات العوائق | FK[] | cond. | WA-7, WA-8 | [NTM-…-0012] | none |
| fod_handback_required | فحص الأجسام الغريبة عند التسليم | bool | sys | true iff any zone fod_control_required | true | none |
| conditions_en / conditions_ar | شروط إضافية | text(1000) | N | — | Withdraw on LVP; report to Ground Control on ch. (fake) | none |
| approved_by_user_id / approved_at | المعتمِد | FK / timestamptz | cond. | ≠ requested_by (WA-4) | Khalid | personal |
| blockers | المعوقات | list {code, detail} | sys | computed (WA-13) | [] | none |
| status | الحالة | enum | Y | §4.8 | active | none |

### 3.17 Operational suspension event (LVP, weather, security) — إيقاف تشغيلي

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| ops_no | الرقم | string | sys | `OPS-<project>-<yyyy>-<nnnn>` | OPS-ANIA-EXP-2026-0009 | none |
| type | النوع | enum | Y | `lvp` إجراءات الرؤية المنخفضة, `dust_sandstorm` عاصفة غبارية, `thunderstorm_lightning` عاصفة رعدية, `security_alert` إنذار أمني, `aircraft_emergency` طوارئ طائرة, `atc_instruction` تعليمات المراقبة الجوية, `vip_movement` حركة رسمية, `other` | lvp | none |
| zone_ids | المناطق المتأثرة | FK[] | Y | default: all zones with lvp_withdrawal_required when type ∈ {lvp, dust_sandstorm} | [Z-TWB, Z-ILS33R] | none |
| source / source_ref | المصدر | enum / string(40) | Y | `aocc` مركز عمليات المطار, `atc` المراقبة الجوية, `airport_security`, `hse` | aocc / AOCC-LOG-TEST-221 | none |
| started_at / ended_at | البداية / النهاية | timestamptz | Y / N | — | 2026-09-28T01:10Z / 2026-09-28T04:40Z | none |
| declared_by_user_id | المُعلِن | FK | Y | capability 67 | Khalid | personal |

### 3.18 Credential status event (suspension / revocation / reinstatement log) — سجل تغيير حالة التصريح

| Field | Type | Req | Validation | PDPL |
|---|---|---|---|---|
| credential_kind | enum | Y | `induction`, `airport_pass`, `adp`, `avp`, `wap`, `access_card`, `worker` | none |
| credential_id | UUID | Y | — | none |
| action | enum | Y | `suspend_raised`, `suspend_confirmed`, `reinstated`, `revoked`, `expired`, `return_due`, `returned`, `lost_reported`, `token_rotated`, `auto_suspended`, `auto_reinstated` | none |
| reason_code | enum | Y | list LC-R (§3.21) | personal |
| reason_text | text(500) | cond. | required for manual actions; P3 hint | personal |
| actor_user_id | FK | cond. | null = system job | personal |
| occurred_at | timestamptz | Y | — | none |
| expires_at | timestamptz | cond. | for `suspend_raised` = occurred_at + `raised_suspension_max_hours` | none |

### 3.19 Gate and gate device — البوابة وجهاز التحقق

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| gate_code | رمز البوابة | string(12) | Y | unique within project | G-AAP3 | none |
| name_en / name_ar | الاسم | string ×2 | Y | — | Contractor Airside Access Point 3 / نقطة دخول المقاولين للجانب الجوي 3 | none |
| site_id / protected_zone_ids | الموقع / المناطق المحمية | FK / FK[] | Y / Y | zones of that site; empty = whole site (site gate) | S-AIR / [Z-APR-21, Z-TWB, Z-ILS33R] | none |
| gate_type | النوع | enum | Y | `site_gate` بوابة الموقع, `zone_entry` مدخل منطقة, `airside_precheck` تحقق مسبق للجانب الجوي | airside_precheck | none |
| devices | الأجهزة | list {device_id, label, registered_at, last_seen_at, revoked_at} | N | device token issued once, rotated on revoke; device sessions can only call gate-check endpoints | GATE-TAB-07 | none |
| status | الحالة | enum | Y | `active`, `inactive` | active | none |

### 3.20 QR token (on access card, AVP sticker, WAP print; v1.1 also PTW permit print) — رمز التحقق QR

| Field | Type | Rule |
|---|---|---|
| payload | string | `HSE2:<kind>:<token>` where kind ∈ {`AC` access card, `VS` vehicle sticker, `WP` WAP, `PT` PTW permit print (v1.1, generated by Phase 3), `EQ` equipment sticker (v1.2, generated by Phase 4, `4-third-party-cert.md` §3.5)} and token = 22-char base64url of 128 random bits. **No personal data, no ID number, no name in the QR.** |
| signature | — | none in v1.0 (online lookup only); format reserves `.<sig>` suffix for a later offline mode (§10 Q12) |
| status | enum | `active`, `rotated` (replaced after loss/reissue), `revoked` |
| printed_ref | string | human-readable number printed beside the QR (deployment worker_no + project, AVP sticker no, WAP no) for manual fallback lookup |

### 3.21 Reference lists (seeded EN/AR, HSE Manager editable, codes immutable)

| List | Values (code — EN / AR) |
|---|---|
| **OFF** airside driving offences (points) — fictional defaults, `VERIFY` against operator's Airside Driving Rules | OFF-01 Speeding (> apron limit 25 km/h, > airside road limit 40 km/h ASSUMPTION) تجاوز السرعة — 3 · OFF-02 No beacon / lights on airside تشغيل بدون إضاءة أو منارة — 3 · OFF-03 Driving behind aircraft with engines running / in jet-blast zone القيادة خلف طائرة محركاتها تعمل — 6 · OFF-04 Failure to give way to aircraft or emergency vehicle عدم إعطاء الأولوية للطائرات — 6 · OFF-05 Entering runway/taxiway without ATC clearance (incursion) دخول المدرج أو الممر دون تصريح المراقبة — 12 + immediate suspension · OFF-06 Driving without valid ADP or outside ADP category القيادة دون تصريح ساري — 12 + immediate suspension · OFF-07 Mobile phone use while driving استخدام الجوال أثناء القيادة — 3 · OFF-08 FOD left / no FOD check ترك أجسام غريبة — 2 · OFF-09 Parking in prohibited area / across equipment restraint line الوقوف في منطقة محظورة — 2 · OFF-10 Vehicle without AVP and without escort مركبة دون تصريح أو مرافقة — 6 |
| **LC-R** status reason codes | `violation` مخالفة · `investigation_pending` قيد التحقيق · `contractor_suspended` المقاول موقوف · `contractor_blacklisted` المقاول محظور · `worker_banned` العامل محظور · `id_expired` انتهاء الهوية · `licence_expired` انتهاء الرخصة · `vehicle_document_expired` انتهاء وثيقة المركبة · `dependency_invalid` متطلب سابق غير ساري · `points_threshold` تجاوز حد النقاط · `security_request` طلب أمني · `ops_suspension` إيقاف تشغيلي · `demobilised` تسريح · `superseded` استبدال · `lost_stolen` فقد/سرقة · `fraud_misuse` تزوير/سوء استخدام · `other` أخرى |
| **VC** vehicle categories | light_vehicle مركبة خفيفة · pickup بيك أب · van فان · bus حافلة · truck شاحنة · tipper قلاب · water_tanker صهريج مياه · fuel_bowser صهريج وقود · concrete_mixer خلاطة خرسانة · mobile_crane رافعة متحركة · crawler_crane رافعة مجنزرة · mewp منصة رفع أفراد · forklift رافعة شوكية · telehandler رافعة تلسكوبية · excavator حفارة · wheel_loader لودر · grader قريدر · roller مدحلة · paver فرادة أسفلت · milling_machine كاشطة · line_marking_vehicle مركبة تخطيط · sweeper كانسة · lighting_tower برج إنارة · trailer مقطورة · other أخرى |
| **GC-X** gate reason codes (§5.10 GC-6) | full list with EN/AR in i18n files; severities `deny` / `warn` |

### 3.22 Phase 2 project settings (extend Phase 0 §3.9 and Phase 1 §3.10; HSE Manager only, audited)

| Key | AR label | Type | Default | Allowed |
|---|---|---|---|---|
| induction_pass_mark_pct | درجة النجاح في التعريف | int | 80 ASSUMPTION | 50–100 (course may only raise) |
| induction_retest_wait_hours | مدة الانتظار لإعادة الاختبار | int | 0 | 0–72 |
| induction_max_attempts_30d | أقصى محاولات خلال 30 يوماً | int | 3 ASSUMPTION | 1–5 |
| reinduction_absence_days | إعادة التعريف بعد الغياب (أيام) | int / null | null (off) ASSUMPTION | 30–365 |
| reinduction_grace_days | مهلة إعادة التعريف للإصدار الجديد | int | 30 | 0–90 |
| id_expiry_blocks_access | انتهاء الهوية يمنع الدخول | bool | true | — |
| pass_max_validity_months | أقصى صلاحية لتصريح المطار | int | 24 `VERIFY` R2 | 1–36 |
| temp_escorted_pass_max_days | أقصى صلاحية للتصريح المؤقت بمرافقة | int | 30 ASSUMPTION | 1–90 |
| visitor_pass_max_days | أقصى صلاحية لتصريح الزائر | int | 1 | 1–7 |
| bg_recheck_months | إعادة التحقق الأمني (أشهر) | int | 24 `VERIFY` R1/R2 | 12–60 |
| application_stale_days | تأخر الطلب (أيام) | int | 30 | 7–90 |
| id_copy_retention_days | مدة الاحتفاظ بصورة الهوية | int | 30 ASSUMPTION | 0–180 |
| pass_return_days | مهلة إرجاع التصريح | int | 3 ASSUMPTION `VERIFY` R2 | 1–14 |
| lost_report_hours | مهلة الإبلاغ عن الفقد | int | 24 `VERIFY` R2 | 1–72 |
| escort_ratio_max_apron / _manoeuvring / _other | الحد الأقصى للمرافقة | int | 5 / 2 / 5 ASSUMPTION `VERIFY` | 1–10 |
| vehicle_escort_ratio_max_apron / _manoeuvring | الحد الأقصى لمرافقة المركبات | int | 3 / 1 ASSUMPTION | 1–5 |
| escort_pairing_seconds | مهلة مسح المرافق | int | 120 | 30–600 |
| adp_validity_months | صلاحية تصريح القيادة | int | 24 `VERIFY` R2 | 6–36 |
| adp_theory_pass_pct | درجة النجاح النظري | int | 80 | 50–100 |
| adp_points_threshold / adp_points_window_days | حد النقاط / نافذة النقاط | int / int | 12 / 365 ASSUMPTION | 3–24 / 90–730 |
| adp_suspension_days | مدة الإيقاف بالنقاط | int | 30 ASSUMPTION | 7–180 |
| adp_revoke_after_suspensions / _window_days | السحب بعد عدد إيقافات | int / int | 2 / 730 ASSUMPTION | 1–5 / 365–1095 |
| avp_validity_months | صلاحية تصريح المركبة | int | 12 | 1–24 |
| wap_max_days | أقصى مدة لتصريح المنطقة | int | 30 ASSUMPTION | 1–90 |
| wap_exit_grace_minutes | مهلة الخروج بعد انتهاء الفترة | int | 15 | 0–60 |
| notam_request_lead_days | مهلة طلب NOTAM | int | 7 ASSUMPTION `VERIFY` R2/R8 | 1–30 |
| airac_lead_days | مهلة AIRAC | int | 42 `VERIFY` R8 | 28–84 |
| obstacle_clearance_lead_days | مهلة طلب موافقة العوائق | int | 30 ASSUMPTION `VERIFY` R9 | 3–90 |
| obstacle_height_threshold_m | حد الارتفاع لطلب الموافقة (مشاريع غير المطارات) | decimal | 45.00 ASSUMPTION `VERIFY` R9 | 10–150 |
| ols_buffer_m | هامش الأمان تحت سطح OLS | decimal | 3.00 ASSUMPTION | 0–30 |
| raised_suspension_max_hours | مدة الإيقاف المؤقت قبل التأكيد | int | 72 | 4–168 |
| suspended_contractor_gate | نتيجة البوابة لمقاول موقوف | enum | deny | deny · warn |
| hook_policy.training_course / personnel_certificate / equipment_certificate / medical_fitness | سياسة المتطلبات اللاحقة | enum | warn (until module live) | warn · block |
| alert_schedule_long_days | جدول التنبيهات (طويلة) | int[] | [30, 14, 7, 0] (Phase 0/1 convention) | — |
| alert_schedule_short_hours | جدول التنبيهات (قصيرة) | int[] | [72, 24, 0] ASSUMPTION | — |
| gate_log_retention_months | مدة الاحتفاظ بسجل البوابات | int | 12 ASSUMPTION `VERIFY` R2 | 3–60 |
| worker_retention_years | مدة الاحتفاظ ببيانات العامل بعد التسريح | int | 5 ASSUMPTION | 1–15 |
| induction_coverage_warning_pct | حد تغطية التعريف | int | 98 ASSUMPTION | 80–100 |
| induction_register_from | بدء احتساب التعريفات من السجل | date / null | Phase 1 setting (v1.1 §3.10); set to the Phase 2 go-live date on the project | ≥ project start (K-38, KA-2) |

## 4. Workflow / states

Who = capability numbers (§5.13). All transitions audited with before/after (Phase 0 rule 35). "Job" = scheduler at 00:05 Asia/Riyadh unless stated.

### 4.1 Worker (org-wide)
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Active | نشط | 47 | Create; uniqueness by id_number_bidx (WK-2) |
| Active → Banned | محظور | 49 | Reason required; cascades LC-9 |
| Banned → Active | نشط | 49 | Reason required; credentials stay revoked (new applications needed) |
| Active → Inactive | غير نشط | Job | No non-demobilised deployment for 30 days |
| Inactive → Active | نشط | 47 | New deployment |
| any → Anonymised | مجهول الهوية | Job | P2-7 retention reached; terminal |

### 4.2 Worker deployment
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Pending Induction | بانتظار التعريف | 47 | Create |
| Pending Induction → Mobilised | مُعبّأ | System | First passed induction of the project's `general_site` course; access card token issued |
| Mobilised → Demobilised | مُسرّح | 47; Job (engagement demobilisation_date passed; contractor demobilised/blacklisted) | Sets demobilised_on; cascades LC-8 |
| Demobilised → Pending Induction | بانتظار التعريف | 47 | Remobilisation (new deployment row ASSUMPTION — history kept) |

### 4.3 Induction record
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Valid | ساري | 51 | Saved with result passed |
| — → Failed | راسب | 51 | Saved with result failed (terminal; new attempt = new record) |
| Valid → Suspended | موقوف | 57 (raise) / 58 (confirm) | Reason; LC-3 |
| Suspended → Valid | ساري | 58 | Reason; only if valid_until ≥ today |
| Valid/Suspended → Revoked | ملغى | 52 | Reason; re-induction required (terminal) |
| Valid → Superseded | مُستبدل | System | A newer passed record of the same course & project (terminal) |
| Valid/Suspended → Expired | منتهي | Job | today > valid_until (terminal) |

### 4.4 Airport pass application
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Draft | مسودة | 53 | Create |
| Draft → Submitted | مُقدَّم | 53 | All required fields; worker photo present; AP-5 checks pass |
| Submitted → Draft | مسودة | 54 | Returned with comment |
| Submitted → Endorsed | مُعتمد من الراعي | 54 | client_sponsor_user_id set; prerequisite_snapshot all met (or hook warn) |
| Endorsed → Lodged | مُقدَّم للجهة | 55 | lodged_at + authority_ref |
| Lodged → Approved | موافق عليه | 55 | Authority approval recorded; bg status cleared or not_required |
| Lodged → Refused | مرفوض | 55 | Authority refusal; bg status may be not_cleared (sensitive); terminal |
| Approved → Issued | صادر | 55 | Pass record (§3.9) created; terminal for the application |
| Draft/Submitted/Endorsed/Lodged → Withdrawn | مسحوب | 53 (own) / 54 | Reason; terminal |
| Approved → Cancelled | ملغى | 55 | Not collected within 30 days ASSUMPTION or worker demobilised; terminal |

### 4.5 Airport pass / ADP / AVP — validity status
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Active | ساري | 55 / 61 / 64 | Issue recorded; DP-3/VP-3 preconditions |
| Active → Suspended | موقوف | 57 (raised), 58 (confirmed); System (LC-6 dependency, DP-8 points, OFF-05/06, LC-7 contractor) | Reason code LC-R |
| Suspended → Active | ساري | 58; System `auto_reinstated` only for dependency suspensions when the dependency becomes valid again (LC-6) | Never automatic for violation/points/security reasons |
| Active/Suspended → Revoked | مسحوب | 58; System (LC-8 blacklist, DP-9) | Reason; terminal; custody → return_due |
| Active/Suspended → Expired | منتهي | Job | today > effective_valid_until where the limiting date is the credential's own/card expiry (terminal); if the limiting date is a dependency, status → Suspended (`dependency_invalid`) instead (LC-6) |

### 4.6 NOTAM works clearance
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Draft | مسودة | 69 | Create |
| Draft → Submitted to Ops | مُرسل لعمليات المطار | 69 | NT-2 lead check (warning, not block) |
| Submitted to Ops → Requested from AIS | مطلوب من خدمات معلومات الطيران | 70 | Ops forwarded the request |
| Requested → Issued | صادر | 70 | notam_number, effective times |
| Submitted/Requested → Rejected | مرفوض | 70 | Reason; terminal |
| Issued → Replaced | مُستبدل | 70 | NOTAMR issued (new record with replaces_ntm_id); terminal |
| Issued → Cancelled | ملغى | 70 | NOTAMC / works finished early; terminal; cascades WA-15 |
| Issued → Expired | منتهي | Job (every 5 min) | now_utc > effective_to_utc; terminal |

"In effect" (ساري الآن) is derived: Issued and effective_from_utc ≤ now ≤ effective_to_utc.

### 4.7 Obstacle / crane clearance
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Draft | مسودة | 71 | Create; system computes top, penetration, reasons |
| Draft → Submitted | مُقدَّم | 71 | OB-5 lead check (warning) |
| Submitted → Approved / Approved with Conditions / Rejected | معتمد / معتمد بشروط / مرفوض | 72 | Authority decision recorded |
| Approved* → Suspended | موقوف | 72; System (linked NOTAM cancelled/expired, OB-7) | Reason |
| Suspended → Approved* | معتمد | 72 | Condition restored |
| Approved* → Withdrawn | مسحوب | 71 (own) / 72 | Works finished; terminal |
| Approved* → Expired | منتهي | Job | today > valid_to; terminal |

### 4.8 Work-area access permit (WAP)
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Draft | مسودة | 65 | Create |
| Draft → Submitted | مُقدَّم | 65 | Required fields; crew ≥ 1 incl. supervisor |
| Submitted → Draft | مسودة | 66 | Returned with comment |
| Submitted → Approved | معتمد | 66 | Approver ≠ requester (WA-4); blockers allowed (recorded) |
| Submitted → Rejected | مرفوض | 66 | Reason; terminal |
| Approved → Active | ساري | System | At valid_from local 00:00 or on approval if later, **only when blockers = [] (WA-13)**; otherwise stays Approved and alerts |
| Active → Suspended | موقوف | 67; System (ops event §3.17, WA-15 dependency loss, contractor suspended) | Reason code |
| Suspended → Active | ساري | 66 ("resume") | Blockers = []; if fod_handback_required, FOD check confirmation (WA-17) |
| Active/Suspended → Closed | مغلق | 68; Job at valid_to + 1 day 00:05 | Closure: FOD hand-back confirmed when required; terminal |
| Draft/Submitted/Approved → Cancelled | ملغى | 68 | Terminal |
| Approved → Expired | منتهي | Job | valid_to passed without ever activating; terminal |

### 4.9 Custody (physical pass card, ADP card, AVP sticker, access card)
| From → To | AR | Who | Trigger |
|---|---|---|---|
| — → Held | بحوزة الحامل | System | On issue |
| Held → Return Due | مستحق الإرجاع | System | Revoked, Expired, deployment Demobilised, replacement issued, contractor blacklisted/demobilised (LC-10); return_due_on = trigger date + pass_return_days |
| Return Due → Returned | مُعاد | 59 | returned_at, received_by |
| Held/Return Due → Lost | مفقود | 59 | Lost/stolen report; token rotated/revoked (LC-12); terminal |

"Overdue" (متأخر) is derived: Return Due and today > return_due_on.

## 5. Business rules

### 5.1 Worker register (WK)
- WK-1. A worker is one org-wide record per person; work on a project is a deployment. The same person on ANIA-EXP and RBT-52 is one worker with two deployments.
- WK-2. `id_number_bidx` is unique. Creating a duplicate returns 409 `WORKER_EXISTS` with the existing worker_no if the caller can see that worker (capability 46 in scope), otherwise 409 `WORKER_EXISTS_OUT_OF_SCOPE` with no name, worker_no or employer.
- WK-3. ID search is exact full-number match only, through the blind index; prefix, partial or wildcard search on id_number is not offered by any endpoint.
- WK-4. **Masking:** Iqama/National ID show first digit + 7 `*` + last 2 (`2*******02`, same as Phase 1 P1-x); GCC ID/passport show first 2 + `*` per hidden char + last 2 (`TE*****12`). Masking applies in lists, detail views without capability 48, gate results (where the ID is not shown at all, GC-7), notifications, exports without capability 79 and audit before/after values.
- WK-5. Unmasking (capability 48) is a separate request with a reason (`pass_application`, `authority_request`, `identity_verification`, `incident_investigation`, `other`+text) and writes `sensitive_field_read` (Phase 0 P5).
- WK-6. `adult_attestation` must be true; otherwise 422 `ADULT_ATTESTATION_REQUIRED`. No date of birth is collected.
- WK-7. When `id_expiry_blocks_access` = true and id_expiry_date < today, the worker fails every eligibility check (`ID_EXPIRED`) and every credential is dependency-suspended (LC-6) until a new expiry date is saved.
- WK-8. A contractor_worker may be registered with a passport (new arrival before Iqama); the Contractor HSE Rep is alerted at mobilised_on + 60 days and + 90 days ASSUMPTION to replace it with the Iqama. Not a block.
- WK-9. Changing id_type/id_number (e.g. passport → Iqama) needs capability 47; the old value is kept encrypted in history; the audit shows masked values only.
- WK-10. A worker has at most one non-demobilised deployment per project; changing employer on the same project means demobilising and creating a new deployment (409 `DEPLOYMENT_EXISTS`).
- WK-11. A Contractor HSE Rep can create/edit workers only through deployments of engagements in their C scope and sees a worker only while one of the worker's deployments is in scope.
- WK-12. A Banned worker cannot get a new deployment, application, induction or WAP crew place on any project (`WORKER_BANNED`).

### 5.2 Site induction (IN)
- IN-1. A deployment becomes Mobilised only after a passed induction on the project's `general_site` course (§4.2). Until then the access card token is not issued.
- IN-2. valid_from = local date of delivered_at; valid_until per §6.1 (X1). Visitor courses: valid_until = valid_from + validity_days − 1.
- IN-3. Courses of type `airside`, and `zone_specific` courses used by an airside zone profile, cannot list `contractor_hse_rep` in delivered_by_roles (422 `DELIVERER_NOT_ALLOWED`).
- IN-4. A course with prerequisite_codes needs a Valid record of each prerequisite at delivered_at (422 `INDUCTION_PREREQUISITE`).
- IN-5. With a test: score ≥ max(course.pass_mark_pct, `induction_pass_mark_pct`) → passed, else failed. A fourth attempt within 30 days (setting 3) is rejected `INDUCTION_ATTEMPTS_EXCEEDED` until an HSE Officer records a re-training note.
- IN-6. delivery_language ≠ worker.primary_language with interpreter_used = false saves with warning `LANGUAGE_MISMATCH`, shown on the record and counted in the data-quality list (§8.3).
- IN-7. duration_minutes < course.min_duration_minutes is rejected (`INDUCTION_TOO_SHORT`).
- IN-8. A new passed record of the same course and project supersedes the older one; validity is computed from the new date only (no carry-over).
- IN-9. Publishing a course version with requires_reinduction = true sets `reinduction_due_on` = publish date + `reinduction_grace_days` on every Valid record of older versions; on that date they become Expired unless superseded.
- IN-10. When `reinduction_absence_days` is set and the worker has no `in` gate check on the project for that many days, the general induction counts as not valid (`INDUCTION_ABSENCE`) until re-induction. Off by default.
- IN-11. Induction records are never deleted; edits after 24 h only by HSE Manager with reason.
- IN-12. delivered_at ≤ now; the deliverer cannot be the worker (linked user_id).
- IN-13. helmet_sticker_no is unique within the project when set.

### 5.3 Zone access profiles, eligibility and hooks (ZP, HK)
- ZP-1. **Defaults on zone creation:** landside/other zones → required_inductions = [project GEN course], access_permit_required = false, no pass/ADP/AVP. Airside zones → [GEN, project airside course]; airport_pass_area_code = the AP-AREA code whose zone_ids contain the zone (required when security_restricted_area); access_permit_required = security_restricted_area OR in_movement_area; adp_category_required (only if zone.adp_required) = `manoeuvring` for airside_area ∈ {runway, runway_strip, resa, taxiway, taxiway_strip, ils_critical, ils_sensitive}, `apron` for apron, `airside_roads` for airside_road; avp_area_required likewise; lvp_withdrawal_required = true for the same manoeuvring set (ASSUMPTION, strictest; `VERIFY` R7 against the operator's LVP procedure); escort_ratio_max = setting for that area kind.
- ZP-2. Profile edits may only tighten what Phase 0 attributes imply: removing the airside course from an airside zone, setting access_permit_required = false on a movement-area or SRA zone, or raising escort_ratio_max above the setting is rejected `PROFILE_LOOSENING`. To loosen, the Phase 0 zone attribute itself must change (audited).
- ZP-3. **Eligibility function** E(worker, zone, at, context) returns one result per requirement: {kind, code, status ∈ met / not_met / expiring / warn / not_evaluated, valid_until, ref, reason_code}. The worker is eligible iff no result is not_met (and, under `block` hook policy, none is not_evaluated). v1.2: "not_met under warn" exists only in the Phase 4 transition stage (HK-4): a provider not_met without hard_stop is returned as `warn` with `HOOK_NOT_MET_WARN`; a hard_stop not_met is not_met in every stage. "expiring" = met with valid_until ≤ local date(at) + 7 days.
- ZP-4. Requirements E checks, in order: (1) deployment Mobilised on the project and zone.site ∈ deployment.site_ids; (2) worker not Banned; (3) contractor not Blacklisted, and not Suspended (or warn when `suspended_contractor_gate` = warn); (4) ID not expired (WK-7); (5) each required induction Valid at `at`; (6) if airport_pass_area_code set: an Active pass whose area_codes contain it — an escorted pass returns `ESCORT_REQUIRED` (met only with a valid escort, GC-8/WA-11); (7) context = gate: if access_permit_required, an Active WAP listing the worker (not excluded) for that zone with `at` inside a window (WA-9); (8) hook requirements (HK-4).
- ZP-5. E is evaluated at: application Endorse (inductions of the requested areas' zones), WAP Submit / Approve / Activation and at each window start, every gate check, and (later) Phase 3 PTW crew checks.
- HK-1. Hook kinds: `training_course` (Phase 5), `personnel_certificate` (Phase 4), `equipment_certificate` (Phase 4, for vehicles/plant), `medical_fitness` (Phase 6). Phase 2 stores the requirement and evaluates it through a provider; it does not model those records.
- HK-2. Hook requirements can be attached to: a zone profile (worker entering), an AP-CAT pass category (checked at Endorse, e.g. `training_course: AVSEC-AWR`), an ADP category (e.g. `training_course: AIRSIDE-DRV`), a vehicle category VC (e.g. `equipment_certificate: CRANE-TPI` for mobile_crane/crawler_crane, `MEWP-TPI`, `FORKLIFT-TPI`, `TELEHANDLER-TPI`), and a WAP crew_role (e.g. `personnel_certificate: BANKSMAN` for banksman, `RIGGER` for lifting crews). v1.2 seeded defaults added by Phase 4 (HK4-12): VC excavator and wheel_loader → `equipment_certificate: PLANT-TPI`; WAP crew_role banksman → `personnel_certificate: BANKSMAN`. v1.1: hook requirements on PTW permit types, PTW crew roles, equipment lines and appointments are stored and evaluated by Phase 3 through this same contract (`3-ptw.md` HK3-2); Phase 2 stores none of them.
- HK-3. Provider contract (to be implemented by Phases 4/5/6): `check(subject_type ∈ {worker, vehicle, equipment_tag}, subject_id, kind, code, at) → {status ∈ met | not_met | expiring | unknown_code, valid_until?, ref?, reason_code?}`. Without a registered provider the result is `not_evaluated`. v1.1: `equipment_tag` is for equipment not in the vehicle register (tower cranes, lifting accessories, MEWPs, scaffolds); its subject is {category, tag} instead of an id; Phase 2 stores no such record and Phase 4 providers map tags to the equipment register. v1.2 (`4-third-party-cert.md` HK4-8): optional `context` {project_id (required for equipment_tag), zone_id, permit_id, critical, use, equipment_ref (vehicle_id | equipment_tag), rated_capacity_t, operator_worker_id}; result adds `hard_stop` (bool), `conditions[]` ({code, text}) and `swl_t`. Callers treat a hard_stop not_met as not_met in every policy stage.
- HK-4. Hook policy per kind (setting): `warn` → not_evaluated becomes `warn` with `HOOK_NOT_AVAILABLE` ("Training check available from Phase 5 / فحص التدريب متاح من المرحلة 5") and never blocks; `block` → not_evaluated counts as not_met. Switching a kind to `block` is rejected `HOOK_PROVIDER_MISSING` while no provider is registered; every switch is audited. v1.2: for `personnel_certificate` and `equipment_certificate` the effective policy per (project, kind, code) is resolved from the Phase 4 hook policy state (`4-third-party-cert.md` §3.14, §4.8, HK4-4…HK4-6): no provider → `warn` as above; **transition** (from provider registration) → not_met without hard_stop becomes `warn` with reason `HOOK_NOT_MET_WARN` (detail reason kept) and never blocks; **block** (critical codes from registration + 7 days, others + 30 days, or earlier by HSE Manager) → not_met blocks (`HOOK_NOT_MET`). No return from block to warn (`HOOK_POLICY_LOOSENING`). The project setting above remains the policy for `training_course` and `medical_fitness`.
- HK-5. Provider results may be cached ≤ 60 s. From the day a provider is registered, its valid_until joins the effective validity of AVPs (equipment certificate) and the gate result; Phase 2 stores no hook dates.
- HK-6. **Phase 3 PTW hook:** Phase 2 exposes read-only services `access_eligibility(worker_id, zone_id, at)` (E with context = ptw) and `active_waps(zone_id, engagement_id, at)`. Phase 3 will require an Active WAP for PTWs in zones with access_permit_required and will reference wap_no, NOTAM and obstacle clearance numbers. Phase 2 never reads PTW data. v1.1 clarifications (`3-ptw.md` §11): (a) context `ptw` evaluates ZP-4 steps 1–6 and 8 only (no WAP step 7 — Phase 3 checks the WAP itself); (b) `active_waps` returns wap_no, status, windows, blockers, crew {worker_id, crew_role, status, escort_worker_id} and vehicles; Phase 3 calls it for the engagement and each ancestor engagement; (c) Phase 2 publishes internal domain events `wap.status_changed`, `wap.crew_changed`, `wap.blockers_changed`, `ntm.status_changed`, `obs.status_changed`, `ops_event.started` / `ops_event.ended`, `credential.status_changed`, `deployment.status_changed`, `worker.status_changed`, delivered at least once within 60 s; publishing them changes no Phase 2 behaviour.
- HK-7. Phase 5 may read induction records as training evidence (read-only); induction remains owned by Phase 2.
- HK-8. Phase 4 personnel-certificate blacklisting does not change worker status; a Phase 2 worker ban is a separate, explicit act (capability 49).

### 5.4 Airport passes (AP)
- AP-1. The platform records the issuing authority's decisions; a pass can be Issued only with the authority's pass_no and card dates. No platform action marks a person cleared or grants an area the authority did not grant.
- AP-2. Airport passes, ADPs, AVPs and NOTAM records exist only on projects with is_airport = true (422 `NOT_AIRPORT_PROJECT`). Obstacle clearances are allowed on every project (OB-1).
- AP-3. At most one open application (Draft…Approved) per worker per project (409 `APPLICATION_OPEN`).
- AP-4. Categories with background_check_required = true can be Approved only with background_check_status = `cleared`; escorted categories may be Approved with status `in_progress` or `not_required`.
- AP-5. Submit requires: deployment Mobilised; worker photo present; id_expiry_date > today + 30 days ASSUMPTION (else `ID_EXPIRES_SOON`); contractor not Suspended (`CONTRACTOR_SUSPENDED`); worker not Banned.
- AP-6. requested_valid_until ≤ min(worker.id_expiry_date, deployment.planned_demob_on, engagement.demobilisation_date, project.planned_end_date, today + category.max_validity_days; for TEMP-E today + `temp_escorted_pass_max_days` − 1; for VIS today + `visitor_pass_max_days` − 1). Otherwise 422 `VALIDITY_EXCEEDS_LIMIT` naming the limiting field.
- AP-7. Endorse requires Valid GEN and airside inductions of the project and, for each requested area code, the induction requirements of its mapped zones; pass-category hook results are stored in prerequisite_snapshot.
- AP-8. Endorser ≠ submitter, and the endorser's employer_type ∈ {client, pmc_consultant} ASSUMPTION (`ENDORSER_NOT_ALLOWED`).
- AP-9. Issued area_codes ⊆ requested_area_codes; card_expiry_date is entered exactly as printed; effective_valid_until per §6.2.
- AP-10. Visitor (VIS) passes are always escorted, valid ≤ `visitor_pass_max_days`, and need a Valid visitor induction on the day.
- AP-11. A worker holds at most one Active pass per project. Issuing a renewal/replacement/area-change pass sets the previous one to Revoked (`superseded`) on the new issued_on and its custody to Return Due.
- AP-12. When background_check recheck_due < today without a newer `cleared` result, background_check_status becomes `expired` and the pass is suspended (`dependency_invalid`) until a new cleared result is recorded (LC-6).
- AP-13. Roles without capability 56 see a Refused application only as "Refused by issuing authority / مرفوض من جهة الإصدار"; background status, dates and outcome_note are omitted from their API responses.
- AP-14. An application Lodged for more than `application_stale_days` appears in the action panel (§8.3) and alerts the HSE Officer.

### 5.5 Airside driving permits (DP)
- DP-1. ADP category coverage: `manoeuvring` ⊇ `apron` ⊇ `airside_roads`. A zone's adp_category_required is met by an equal or wider category.
- DP-2. One Active ADP per worker per project.
- DP-3. Issue requires an Active, unescorted pass (category allows_adp = true) whose area codes include an area of each kind the category covers (manoeuvring → codes of kind manoeuvring and apron; apron → apron) — else 422 `ADP_PASS_REQUIRED`. Escorted-pass holders never receive an ADP (strictest-wins, §2).
- DP-4. Residents (id_type iqama/national_id) need licence_issuer = `ksa`; licence_expiry_date > today; vehicle_classes must be allowed by licence_class (heavy → heavy_transport or heavy_equipment; special_plant → heavy_equipment) `VERIFY` R12. Else `LICENCE_NOT_VALID`.
- DP-5. Category `manoeuvring` requires rtf_competence = true and a practical test that included the manoeuvring area (`RTF_REQUIRED`).
- DP-6. Theory score ≥ `adp_theory_pass_pct` and practical result passed, both within 90 days before issued_on ASSUMPTION.
- DP-7. Licence expiry → auto-suspend (`licence_expired`); pass suspended/expired/revoked → auto-suspend (`dependency_invalid`); both auto-reinstate when the dependency is valid again (LC-6).
- DP-8. When points_12m (§6.5) ≥ `adp_points_threshold` the ADP is auto-suspended (`points_threshold`) for `adp_suspension_days` (suspension_end = start + days − 1). Reinstatement only by capability 58 and only after suspension_end (422 `SUSPENSION_PERIOD_RUNNING`).
- DP-9. Offences OFF-05 and OFF-06 suspend the ADP immediately (`violation`) whatever the points. The `adp_revoke_after_suspensions`-th suspension (points or violation) within `adp_revoke_after_suspensions_window_days` revokes the ADP automatically.
- DP-10. Offences in status recorded or upheld count; disputed offences keep counting until withdrawn ASSUMPTION; withdrawing an offence recomputes points but never auto-reinstates a suspension — the HSE Officer is notified.
- DP-11. An offence on a worker without an Active ADP (OFF-06) is recorded against the worker; the ADP field is then null.

### 5.6 Vehicles and AVPs (VP)
- VP-1. (plate_letters, plate_digits) is unique across the org; serial_or_vin is unique within the project.
- VP-2. One Active AVP per vehicle; AVP areas must correspond to airside sites in the owning engagement's site_ids.
- VP-3. Issue requires an inspection passed ≤ 14 days before issued_on, istimara/insurance/MVPI (where applicable) expiring after today, a complete checklist (VP-4), and for area `manoeuvring`: radio_fitted and chequered_flag_or_marking = pass (`AVP_PRECONDITION`).
- VP-4. Every checklist item is pass or n.a.; n.a. is not allowed for amber_beacon, company_marking, fire_extinguisher, tyres_brakes, lights; height_marking is required when max_working_height_m_agl > 3.00 m.
- VP-5. AVP effective_valid_until per §6.2; any document expiry auto-suspends (`vehicle_document_expired`) and auto-reinstates when a later expiry is saved (LC-6).
- VP-6. Vehicles of categories with an equipment_certificate hook (HK-2) are checked at AVP issue and at every gate check under the hook policy.
- VP-7. A vehicle whose max_working_height_m_agl (or the WAP's height_limited_to_m) exceeds the zone's max_equipment_height_m_agl may enter that zone only on an Active WAP linked to an Approved/Approved-with-conditions obstacle clearance for that vehicle, zone and date; otherwise gate result DENIED `HEIGHT_CLEARANCE_REQUIRED`.
- VP-8. A vehicle without an AVP for the zone's avp_area_required may enter only paired with an escort vehicle holding that AVP, driven by an ADP holder of the zone's category; escorted vehicles per escort vehicle ≤ `vehicle_escort_ratio_max_*` (GC-9).

### 5.7 NOTAM works clearances (NT) and obstacle/crane clearances (OB)
- NT-1. The platform does not file NOTAMs. It records the contractor's request to Airport Operations and the NOTAM as issued by the AIS (via the operator), entered by capability 70.
- NT-2. Lead time: submitted_to_ops_at ≤ requested_start_utc − `notam_request_lead_days`; when works_impact ∋ `declared_distances_change`, or ∋ `runway_closure` with requested duration > 24 h, the lead is `airac_lead_days` ASSUMPTION `VERIFY` R8. A shorter lead is allowed with justification and sets `late_request` = true (K-59).
- NT-3. NOTAM times are stored in UTC and shown both as NOTAM format (YYMMDDHHMM UTC) and local Asia/Riyadh (UTC+3).
- NT-4. A WAP with any zone having notam_required_for_works = true is activation-blocked unless a linked NTM is Issued and every window (converted to UTC, §6.7) of every remaining WAP day lies within [effective_from_utc, effective_to_utc]; at each window start the NOTAM must be in effect.
- NT-5. An NTM moving to Cancelled or Expired, or Replaced without a linked successor, suspends linked Active WAPs (`dependency_invalid`) within 60 s. A NOTAMR record (notam_type R, replaces_ntm_id) is auto-linked to the WAPs of the replaced record.
- NT-6. Zones with ils_outage_notam_required = true need a linked NTM whose works_impact includes `ils_outage` (blocker `ILS_OUTAGE_NOTAM_REQUIRED`).
- NT-7. notam_number is unique per project.
- OB-1. Obstacle clearances may be raised on any project (e.g. tower cranes near an aerodrome); on airport projects zone_id and ols_surface are required.
- OB-2. max_height_m_agl is the highest point of the equipment in its planned configuration: boom/jib fully raised at the planned radius, mast, load and rigging included; tower cranes: apex/jib top or, for luffing jibs, jib tip at maximum luff.
- OB-3. Reasons (computed, §6.4): `zone_height_exceeded` if max_height_m_agl > zone.max_equipment_height_m_agl; `ols_penetration` if top > ols_limit; `within_ols_buffer` if ols_limit − `ols_buffer_m` < top ≤ ols_limit; `height_threshold` on non-airport projects if max_height_m_agl ≥ `obstacle_height_threshold_m`; `operator_requires` on airport projects for equipment_type ∈ {mobile_crane, tower_crane, crawler_crane, piling_rig, drilling_rig, concrete_pump_boom} in an airside zone ASSUMPTION. Clearance is required iff reasons ≠ ∅.
- OB-4. A decision of approved/approved_with_conditions on a record with `ols_penetration` must include conditions `notam_required` and `obstruction_light` and an authority_ref; otherwise 422 `OB_CONDITIONS_REQUIRED` (Annex 14 ch. 6, strictest-wins).
- OB-5. Lead: submitted_at ≤ requested_from − `obstacle_clearance_lead_days`; shorter is allowed with justification and `late_request` = true.
- OB-6. The approved height is a hard cap: a WAP vehicle linked to the clearance must have max_working_height_m_agl ≤ approved_max_height_m_agl, or height_limited_to_m ≤ approved_max_height_m_agl (blocker `HEIGHT_CLEARANCE_REQUIRED`).
- OB-7. With condition `notam_required`, from valid_from onward the clearance is system-Suspended on any day not covered by an Issued linked NTM, and dependent WAPs are blocked/suspended; the system lifts this suspension automatically once an Issued linked NTM covers the day (as LC-6).
- OB-8. A Rejected clearance cannot be linked to a WAP.
- OB-9. Heights are shown in m and ft (1 ft = 0.3048 m exactly), 2 dp, round half-up.

### 5.8 Work-area access permits (WA)
- WA-1. Every zone with access_permit_required = true needs an Active WAP for entry (gate, ZP-4 step 7). Other zones may be put on a WAP voluntarily.
- WA-2. All zones of a WAP belong to one site; every crew member's deployment covers that site. Crew come from the WAP's engagement or its ancestor engagements (e.g. a tier-1 supervisor) ASSUMPTION.
- WA-3. A Suspended or Blacklisted contractor cannot submit a WAP (`CONTRACTOR_SUSPENDED`); its Active WAPs are suspended with reason `contractor_suspended` (extends Phase 0 rule 28).
- WA-4. Segregation of duties: approver ≠ requester, and the approver is not employed by the WAP's contractor or any ancestor of it (`SOD_CONFLICT`). ASSUMPTION — tied to Phase 0 §10 Q2.
- WA-5. valid_from ≥ today at Submit; (valid_to − valid_from + 1) ≤ `wap_max_days`.
- WA-6. A WAP with any zone in_movement_area = true needs works_safety_plan_ref (`WSP_REQUIRED`).
- WA-7. NOTAM rules NT-4 to NT-6 apply.
- WA-8. Vehicles exceeding the zone's max_equipment_height need a linked approved obstacle clearance (VP-7, OB-6) covering the vehicle, zone and every WAP day the vehicle is listed for.
- WA-9. A window whose end ≤ start crosses midnight and belongs to the start date: window on local date d = [d + start, d + 1 + end). Windows apply only on their weekdays and only for d within [valid_from, valid_to].
- WA-10. Crew eligibility (E without step 7) is evaluated at Submit, Approve, Activation and each window start. An ineligible non-supervisor is set `excluded` (with reason) automatically and the requester and supervisor are notified; re-included automatically at the next evaluation once eligible. An ineligible supervisor makes blocker `SUPERVISOR_INELIGIBLE` (an Active WAP is Suspended).
- WA-11. Each crew member with an escorted pass names an escort crew member (crew_role escort) who holds an Active unescorted pass covering the zone's area code, has Valid zone inductions, and, for manoeuvring zones, an Active manoeuvring ADP ASSUMPTION. Per escort, escorted members ≤ zone escort_ratio_max. An escort cannot themself be escorted. Violations exclude the escorted member (`ESCORT_MISSING`, `ESCORT_RATIO_EXCEEDED`).
- WA-12. Each listed vehicle has an Active AVP covering the zone's avp_area_required or an escort_vehicle_id of a listed vehicle that has one (ratio VP-8). Each crew member with crew_role driver needs an ADP covering the zone's adp_category_required.
- WA-13. **Blockers** (recomputed on every change and at each window start): `NOTAM_NOT_ISSUED`, `NOTAM_NOT_COVERING_WINDOW`, `ILS_OUTAGE_NOTAM_REQUIRED`, `HEIGHT_CLEARANCE_REQUIRED`, `OBS_NOT_ACTIVE`, `WSP_REQUIRED`, `SUPERVISOR_INELIGIBLE`, `NO_ELIGIBLE_CREW`, `CONTRACTOR_SUSPENDED`, `OPS_SUSPENSION_ACTIVE`. Approved → Active only when blockers = []; a blocker appearing on an Active WAP suspends it (`dependency_invalid`, or the matching reason).
- WA-14. On an Active WAP, adding crew/vehicles (capability 65) takes effect once each addition is evaluated. Changing zones, dates, windows or NOTAM/clearance links creates a revision in Submitted; the current revision stays Active until the new one is Approved (then replaced) or Rejected.
- WA-15. **Operational suspension:** when an ops event (§3.17) starts, every Active WAP with a zone in the event's zones becomes Suspended (`ops_suspension`) within 60 s, and the supervisor, requester, approver and HSE Officers are notified. Ending the event does not resume WAPs; each is resumed by capability 66 (WA-17).
- WA-16. Events of type lvp or dust_sandstorm default to all zones of the site with lvp_withdrawal_required; the declarer may add zones but not remove default ones.
- WA-17. Resume and Close of a WAP with fod_handback_required need a FOD check record (fod_checked_by worker/user, fod_checked_at ≤ now, result `clear`) — else 422 `FOD_HANDBACK_REQUIRED`.
- WA-18. WAP print/QR (kind WP) shows crew names and worker_no only — never ID numbers.
- WA-19. Roles without capability 46 (e.g. Viewer/Client) see WAPs with crew count and vehicle count, not crew names.

### 5.9 Credential lifecycle — validity, suspension, revocation, return (LC)
- LC-1. A credential is valid on every local date ≤ its effective_valid_until (inclusive). The expiry job runs at 00:05 Asia/Riyadh; gate checks evaluate validity live and never depend on the job (LC-13).
- LC-2. effective_valid_until is recomputed whenever any dependency date changes; it never exceeds the credential's own/card date.
- LC-3. A **raised** suspension (capability 57) lasts at most `raised_suspension_max_hours`; unless confirmed by capability 58 it lifts automatically (`auto_reinstated`), notifying the raiser and HSE Officers. A confirmed suspension lasts until lifted by 58 or the credential ends.
- LC-4. Every manual suspension, reinstatement or revocation needs reason_code and reason_text (≥ 10 chars) and writes a §3.18 event; notifications per §7.
- LC-5. Revocation is terminal; regaining access needs a new application/induction/ADP/AVP.
- LC-6. **Dependency suspensions** (`dependency_invalid`, `id_expired`, `licence_expired`, `vehicle_document_expired`, background-check expiry) are applied and lifted by the system only: lifted automatically when the dependency becomes valid again, provided no other open suspension exists on the credential.
- LC-7. Contractor Suspended (Phase 0 §4.2): new applications, ADP/AVP applications and WAPs are blocked; Active WAPs suspend (WA-3); authority-issued passes/ADPs/AVPs are not changed, but gate checks return DENIED `CONTRACTOR_SUSPENDED` (or warn per setting). Reinstating the contractor does not resume WAPs (capability 66 per WAP).
- LC-8. Contractor Blacklisted (Phase 0 rule 27): its deployments are demobilised, all its workers' and vehicles' credentials on every project are Revoked (`contractor_blacklisted`), custody → Return Due, access-card tokens revoked, and the HSE Officers are told to inform the pass office. Descendant engagements are flagged only (Phase 0 rule 27c).
- LC-9. Worker Banned: every credential of the worker on every project is Revoked (`worker_banned`); custody → Return Due.
- LC-10. Deployment Demobilised: the worker's pass and ADP on that project are Revoked (`demobilised`), custody → Return Due with return_due_on = demobilised_on + `pass_return_days`; the access-card token is revoked; Active WAP crew entries are removed.
- LC-11. Return: returned_at ≤ now, received_by = recording user; the return is late when local date(returned_at) > return_due_on.
- LC-12. Loss: a lost report rotates the access-card token or marks the pass/ADP/AVP Lost; authority_notified_at must be recorded within `lost_report_hours` (alert). Any later scan of a lost/rotated/revoked token returns DENIED `CREDENTIAL_LOST` / `CREDENTIAL_REVOKED` and alerts the HSE Officer immediately with gate and time.
- LC-13. The expiry job is idempotent; running it twice changes nothing.
- LC-14. No credential, application, offence, event or gate log is hard-deleted by users (retention purges only, P2-6/P2-7).

### 5.10 Gate / access check (GC)
- GC-1. Gate-check endpoints accept (a) logged-in users with capability 74 or (b) a registered gate-device session bound to one gate. A device session expires after 12 h idle ASSUMPTION, can call only gate-check endpoints, and is revoked with the device.
- GC-2. Input: QR payload (or printed_ref typed manually), gate_id, direction (`in`/`out`), target zone (default: the gate's single protected zone; the scanner picks one when the gate protects several; site gate → site), optional pairing_id.
- GC-3. Unknown or malformed payload → DENIED `TOKEN_UNKNOWN`. Rate limit 120 checks/min per device or user.
- GC-4. Access card: site gate → ZP-4 steps 1–5 for the site's GEN; zone entry/airside pre-check → full E(worker, zone, now, gate).
- GC-5. Results: `GRANTED` مسموح (green) · `GRANTED_WITH_WARNING` مسموح مع تنبيه (amber) · `DENIED` مرفوض (red) · `PENDING_ESCORT` بانتظار المرافق · `PENDING_DRIVER` بانتظار السائق · `PENDING_ESCORT_VEHICLE` بانتظار مركبة المرافقة · `EXIT_RECORDED` تم تسجيل الخروج.
- GC-6. Reason codes (severity): DENY — `TOKEN_UNKNOWN`, `OUT_OF_SCOPE`, `WORKER_NOT_DEPLOYED`, `WORKER_BANNED`, `CONTRACTOR_SUSPENDED`, `CONTRACTOR_BLACKLISTED`, `ID_EXPIRED`, `INDUCTION_MISSING`, `INDUCTION_EXPIRED`, `INDUCTION_SUSPENDED`, `INDUCTION_ABSENCE`, `PASS_MISSING`, `PASS_AREA_NOT_COVERED`, `PASS_SUSPENDED`, `PASS_EXPIRED`, `CREDENTIAL_REVOKED`, `CREDENTIAL_LOST`, `ESCORT_REQUIRED`, `ESCORT_INVALID`, `ESCORT_RATIO_EXCEEDED`, `WAP_MISSING`, `WAP_NOT_ACTIVE`, `WAP_SUSPENDED`, `WAP_OUTSIDE_WINDOW`, `CREW_EXCLUDED`, `ADP_MISSING`, `ADP_CATEGORY`, `ADP_SUSPENDED`, `AVP_MISSING`, `AVP_AREA`, `AVP_SUSPENDED`, `VEHICLE_DOC_EXPIRED`, `HEIGHT_CLEARANCE_REQUIRED`, `HOOK_NOT_MET`, v1.2 equipment-sticker checks (order per `4-third-party-cert.md` GE-2) `EQUIPMENT_BLACKLISTED`, `EQUIPMENT_NOT_DEPLOYED`, `EQUIPMENT_NOT_APPROVED`, `EQUIPMENT_OUT_OF_SERVICE`, `EQUIPMENT_QUARANTINED`; WARN — `EXPIRING_7D`, `HOOK_NOT_AVAILABLE`, `HOOK_NOT_MET_WARN` (v1.2), `ARRIVAL_INSPECTION_DUE` (v1.2), `ALSO_SCAN_VEHICLE_STICKER` (v1.2), `CONTRACTOR_SUSPENDED` (warn mode), `LANGUAGE_MISMATCH` (induction). Any DENY → DENIED; else any WARN → GRANTED_WITH_WARNING.
- GC-7. The result screen shows: photo, full name EN/AR, worker_no, employer short code, trade, result and reasons (EN/AR), each relevant credential with valid_until (inductions; pass category, colour and area codes; ADP category; WAP no and today's window), "Escort required / يتطلب مرافقة" badge. It never shows the ID number, nationality, background status or offence history. The screen clears after 30 s; devices cache no personal data.
- GC-8. **Escort pairing:** an escorted holder's scan returns PENDING_ESCORT with a pairing_id. If the escort's card is scanned on the same device within `escort_pairing_seconds`, the escort is checked (unescorted pass covering the zone area, zone inductions, manoeuvring ADP where WA-11 applies, active escort count < ratio) and both are GRANTED or both DENIED (`ESCORT_INVALID` / `ESCORT_RATIO_EXCEEDED`). On timeout the escorted person is DENIED `ESCORT_REQUIRED`. Active escort count (§6.6) = the escort's `in` pairings today (local) − `out` pairings today.
- GC-9. **Vehicle sticker:** checks AVP area, AVP status, vehicle documents, height vs zone (VP-7), hooks, and — when the zone has access_permit_required — that the vehicle (or the escorted vehicle's escort vehicle) is listed on an Active WAP for that zone with now inside a window (`WAP_MISSING` / `WAP_NOT_ACTIVE` / `WAP_OUTSIDE_WINDOW`); then PENDING_DRIVER until a driver card with ADP of the zone's category is scanned within the pairing time. A vehicle without an AVP for the area returns PENDING_ESCORT_VEHICLE until an escort vehicle sticker (with AVP) is scanned; vehicle ratio VP-8.
- GC-10. WAP QR at a zone entry shows WAP status, whether now is inside a window, blockers, crew (names, worker_no, eligibility now) and vehicles; it logs a `wap_view` entry but records no individual's entry. v1.1: a `PT` token is treated the same way — read-only permit summary (`3-ptw.md`), logs `ptw_view`, records no entry.
- GC-11. Direction `out` never denies; it logs EXIT_RECORDED and ends escort pairings. Leaving within `wap_exit_grace_minutes` after a window end is not flagged; later exits are flagged `late_exit` in the log.
- GC-12. Every check writes an immutable gate-log row: occurred_at, gate, device or user, direction, subject (deployment/vehicle/WAP; v1.2 `equipment_deployment` for EQ sticker checks, excluded from K-52/K-53 per `4-third-party-cert.md` GE-6), zone, result, reason codes, pairing_id, `admitted_despite_denial` flag.
- GC-13. A Contractor HSE Rep scanning a subject outside their C scope gets `OUT_OF_SCOPE` with no personal data and no hint of the result.
- GC-14. The platform has no override. If a guard admits a person or vehicle despite DENIED, they set `admitted_despite_denial` = true with a reason; this alerts the HSE Officer and HSE Manager immediately and counts in K-53b.
- GC-15. p95 response < 1.5 s on the reference machine ASSUMPTION. v1.0 is online-only; with no connection the device shows "No connection — call the HSE Officer / لا يوجد اتصال — اتصل بمسؤول السلامة" (offline mode, §10 Q12).
- GC-16. QR payloads carry no personal data (§3.20); reissuing a card rotates the token and the old one returns `CREDENTIAL_REVOKED`.

### 5.11 KPIs and AI (KA)
- KA-1. All access KPIs are computed by the backend (Phase 1 D-1); the frontend only formats.
- KA-2. Phase 1 **K-38 Inductions** (Phase 1 v1.1 §6.1): for days on/after `induction_register_from` = count of induction records of course type `general_site` with result passed and local delivered date on that day; days before it (or setting null) use the daily-return `inductions` field. Other types appear as a breakdown. When register and daily-return totals differ by > 5 % for the register days of a period, the K-38 tile shows a reconciliation note ASSUMPTION.
- KA-3. Gate KPIs count `in` direction checks only; pairing scans count as one check per person/vehicle.
- KA-4. Viewer/Client sees access KPIs and the expiring-items counts as aggregates only (no names, worker_no or plates).
- KA-5. AI tool **T14 `get_access_kpis`** (project_ids, period, filters {site, zone, engagement, include_descendants}, metrics K-38/K-48…K-60, group_by {kind, reason_code, contractor, zone, month}) returns aggregates only; T13 additionally returns warnings E5–E7. AI-5 applies: no names, IDs, worker_no, photos, plates or offence details per person are sent to the model.

### 5.12 PDPL handling (P2-x, extends Phase 0 P1–P13 and Phase 1 P1-x)
- P2-1. Classes are those in §3. **Sensitive:** id_number, id_number_bidx, id_copy, background_check_status/date/recheck_due. **Personal:** names, photo, nationality, ID expiry, licence data, test scores, offences, deployment data, crew lists, gate logs, worker privacy acknowledgements.
- P2-2. id_number (incl. history) and background_check_* columns are encrypted at application level (AES-256-GCM, key in a KSA-hosted KMS, Phase 0 P10/P11); photos and ID copies are in an encrypted bucket served by signed URLs ≤ 5 min; the blind-index HMAC key is separate from the encryption key and a re-index job supports key rotation.
- P2-3. The API returns masked IDs by default (WK-4); the full value only from the unmask endpoint (capability 48, WK-5).
- P2-4. Background checks: the platform stores status and dates only — never the reason for a refusal, criminal-record data or the authority's report. outcome_note is scanned for prohibited terms list ASSUMPTION and shows the hint "Do not record security reasons / لا تسجل الأسباب الأمنية".
- P2-5. ID copies are deleted `id_copy_retention_days` after the application reaches Issued, Refused, Withdrawn or Cancelled; deletion is audited.
- P2-6. Gate-log rows are deleted after `gate_log_retention_months`, except rows linked to a Phase 1 incident or investigation, which follow that incident's retention.
- P2-7. `worker_retention_years` after the last deployment's demobilised_on, if no open incident link: names → "Anonymised worker WKR-nnnnnn", photo, id_number, id history, bidx and nationality deleted; worker_no, trade and induction/credential statistics kept. Workers linked to an injury case follow Phase 1 P1-5 instead.
- P2-8. Purpose limitation: worker data is used for access control, HSE compliance and incident investigation only — not for attendance, payroll or HR performance ASSUMPTION (§10 Q11). Gate logs are not exposed through any time-and-attendance export.
- P2-9. Workers without accounts get the **worker privacy notice** (WPN, EN/AR, read out in the delivery language) at induction; its version and the signature are stored on the induction record.
- P2-10. Exports (capability 78) mask IDs; full IDs only with capability 79 and a stated purpose (`pass_office`, `authority_request`, `legal`, `other`+text) in the `export` audit entry; photos and ID copies are never in bulk exports; gate-log export needs capability 76.
- P2-11. Data-subject requests for workers are handled by the HSE Manager under Phase 0 P8; capability 79 can produce a per-worker data report (all Phase 2 records of that person).
- P2-12. Minimisation: no date of birth, place of birth, parents' names, home address, religion, marital status, blood group or medical data in Phase 2.
- P2-13. Phase 1 P1-8 (free-text scan for 10-digit IDs) applies to every Phase 2 free-text field.

### 5.13 Permission matrix — Phase 2 extension (continues Phase 1 §5.10; legend unchanged A/P/S/C/C1/R/—)

| # | Capability | HSE Mgr | HSE Officer | Site Eng/Sup | Permit Issuer | Permit Receiver | Contractor HSE Rep | Viewer/Client |
|---|---|---|---|---|---|---|---|---|
| 46 | View worker register (name, photo, employer, trade, masked ID, credential summary) | A | P | S | S | C1 | C | — |
| 47 | Create/edit workers & deployments; demobilise | A | P | — | — | — | C | — |
| 48 | Unmask full ID number / open ID copy (audited) | A | P | — | — | — | C ASSUMPTION (§10 Q14) | — |
| 49 | Ban / lift ban on a worker | A | — | — | — | — | — | — |
| 50 | Manage induction courses & sessions | A | P | — | — | — | — | — |
| 51 | Record induction attendance & results | A | P | — | — | — | C (courses listing contractor_hse_rep only, IN-3) | — |
| 52 | Suspend (confirm) / revoke induction | A | P | — | — | — | — | — |
| 53 | Create / submit / withdraw airport pass application | A | P | — | — | — | C | — |
| 54 | Endorse or return application (sponsor check) | A | P | — | — | — | — | — |
| 55 | Record pass-office progress, decision and issued pass | A | P | — | — | — | — | — |
| 56 | View background-check status and dates | A | P | — | — | — | — | — |
| 57 | Raise suspension of induction/pass/ADP/AVP (≤ 72 h, LC-3) | A | P | S | S | — | — | — |
| 58 | Confirm/lift suspension; revoke pass/ADP/AVP | A | P | — | — | — | — | — |
| 59 | Record return or loss of pass/ADP/AVP/access card | A | P | — | — | — | C (loss report; return to contractor) | — |
| 60 | Apply for ADP | A | P | — | — | — | C | — |
| 61 | Record ADP tests and issue ADP | A | P | — | — | — | — | — |
| 62 | Record airside driving offence | A | P | S | S | — | — | — |
| 63 | Create/edit vehicles; apply for AVP | A | P | — | — | — | C | — |
| 64 | Record AVP inspection and issue AVP | A | P | — | — | — | — | — |
| 65 | Create / submit / amend WAP | A | P | S | — | C1 | C | — |
| 66 | Approve / reject / resume WAP | A | P | — | S | — | — | — |
| 67 | Suspend WAP; declare / end operational suspension (LVP etc.) | A | P | S | S | — | — | — |
| 68 | Close / cancel WAP | A | P | S | S | C1 (own) | C (own tree) | — |
| 69 | Create/edit/submit NOTAM works request | A | P | S | — | — | C | — |
| 70 | Record NOTAM progress, number, effective times, cancel | A | P | — | — | — | — | — |
| 71 | Create/submit/withdraw obstacle (crane) clearance | A | P | S | — | — | C | — |
| 72 | Record GACA/operator decision on obstacle clearance | A | P | — | — | — | — | — |
| 73 | View WAPs, NOTAM records, obstacle clearances, ops events | A | P | S | S | C1 | C | P (WA-19) |
| 74 | Perform gate check (scan) | A | P | S | S | — | C (GC-13) | — |
| 75 | Register gates and gate devices | A | P | — | — | — | — | — |
| 76 | View / export gate-check log | A | P | S | — | — | C | — |
| 77 | View access KPIs, expiring items, access action panel | A | P | S | S | C1 | C | P (aggregates, KA-4) |
| 78 | Export access registers (IDs masked) | A | P | S | — | — | C | — |
| 79 | Export with full IDs / per-worker data report (purpose required) | A | P | — | — | — | — | — |
| 80 | Edit Phase 2 settings, reference lists (AP-CAT, AP-AREA, OFF, VC), hook policy | A | — | — | — | — | — | — |
| 81 | Edit zone access profiles (ZP-2) | A | P | — | — | — | — | — |

Gate devices (GC-1) hold only capability 74 for their gate. Suspended-contractor users keep reads and lose writes (Phase 0 rule 28). Phase 0 rule 16 (issuer/receiver segregation) and WA-4 both apply to WAPs.

## 6. Calculations

All dates are local Asia/Riyadh (Phase 0 K2); NOTAM times UTC. Rounding half-up at output (Phase 1 K-R8); comparisons use unrounded values.

### 6.1 Validity dates
- `add_months(d, m)` = same day-of-month m months later, clamped to the last day of the target month.
- Induction / ADP own / AVP own: valid_until = add_months(valid_from, validity_months) − 1 day.
- Visitor induction: valid_until = valid_from + validity_days − 1.
- days_left = valid_until − today (negative = expired).

### 6.2 Effective validity (strictest-wins)
- Pass: eff = min(card_expiry_date, worker.id_expiry_date, deployment.planned_demob_on, engagement.demobilisation_date, project.planned_end_date, background recheck_due (unescorted categories)). Null terms are ignored.
- ADP: eff = min(own_valid_until, pass.effective_valid_until, licence_expiry_date).
- AVP: eff = min(own_valid_until, istimara_expiry, insurance_expiry, mvpi_expiry, equipment-certificate valid_until from hook provider when registered).
- `limiting_factor` = the name of the term giving the minimum (shown in UI and alerts).

### 6.3 Alert dates
- Long-validity credentials (inductions, passes, ADPs, AVPs, vehicle documents, worker ID, background recheck): alert on eff − n for n ∈ `alert_schedule_long_days` = 30, 14, 7, 0 (Phase 0/1 convention); an alert date already past at creation fires once immediately with the current days_left.
- Short-window items (WAP valid_to, NOTAM effective_to, obstacle clearance valid_to): alerts at 72 h, 24 h and 0 h before the end (end of valid_to local day = 24:00 local; NOTAM effective_to_utc).

### 6.4 Obstacle heights
- top_elevation_m_amsl = ground_elevation_m_amsl + max_height_m_agl.
- margin_m = ols_limit_m_amsl − top_elevation_m_amsl (negative = penetration); penetration_m = max(0, −margin_m).
- ft = m ÷ 0.3048.
- Reasons per OB-3.

### 6.5 ADP points
points_12m(as_of) = Σ points of the worker's offences with status ∈ {recorded, upheld} and local offence date in (as_of − `adp_points_window_days`, as_of] (window excludes the start date).

### 6.6 Escort counts
active_escorted(escort, day) = n(pairings with escort as escort, direction in, local date = day) − n(matching out scans the same day); must be < zone escort_ratio_max before a new pairing.

### 6.7 WAP windows in UTC
window(d) local [d + start, d′ + end) where d′ = d + 1 if end ≤ start else d; UTC = local − 3 h.

### 6.8 KPI catalogue (continues Phase 1 §6.1)

| ID | Metric (EN / AR) | Formula | Unit / display | Better |
|---|---|---|---|---|
| K-38 | Inductions (source per KA-2) / التعريفات | days ≥ induction_register_from: n(passed `general_site` records delivered); earlier days: Σ daily-return inductions; other types as breakdown | count | — |
| K-48 | Active deployed workers / العمال المعيّنون النشطون | n(contractor_worker deployments Mobilised at as_of) | count | — |
| K-49 | **Induction coverage** / تغطية التعريف بالسلامة | n(K-48 deployments with a Valid `general_site` induction at as_of) ÷ K-48 × 100; K-48 = 0 → "—" | %, 1 dp | higher |
| K-50 | Induction first-attempt pass rate / نسبة النجاح من المحاولة الأولى | n(attempt_no = 1 and passed, delivered in period) ÷ n(attempt_no = 1, delivered in period) × 100 | %, 1 dp | higher |
| K-51 | Credentials expiring ≤ 30 days / التصاريح القريبة من الانتهاء | n(credentials in a valid/active state with eff in [as_of, as_of + 30]) by kind: induction, airport_pass, adp, avp, worker_id, vehicle_document, bg_recheck, obstacle_clearance | count | lower |
| K-52 | Gate checks / عمليات التحقق عند البوابات | n(in-direction checks in period) | count | — |
| K-53 | **Gate denial rate** / نسبة الرفض عند البوابات | n(in checks with result DENIED) ÷ K-52 × 100; breakdown by reason code (a check counts once, under its first DENY reason in GC-6 order) | %, 2 dp | lower |
| K-53b | Admitted despite denial / دخول رغم الرفض | n(gate-log rows with admitted_despite_denial in period) | count | lower |
| K-54 | **Pass return compliance** / الالتزام بإرجاع التصاريح | n(custody items with return_due_on in period and ≤ as_of, returned with local date ≤ return_due_on) ÷ n(custody items with return_due_on in period and ≤ as_of) × 100; items = pass, ADP card, AVP sticker | %, 1 dp | higher |
| K-55 | Unreturned overdue / تصاريح غير مُعادة متأخرة | n(custody Return Due and as_of > return_due_on); ageing 1–7, 8–30, > 30 days | count | lower |
| K-56 | Pass application lead time / مدة إصدار التصريح | median over applications Issued in period of (issued date − submitted date) in days; plus n(Lodged > application_stale_days at as_of) | days 1 dp; count | lower |
| K-57 | Airside driving offence rate / معدل مخالفات القيادة الجوية | n(offences recorded/upheld with offence date in period) × 100 ÷ n(Active ADPs at as_of); plus ADP suspensions in period and OFF-05 count | per 100 ADPs, 2 dp | lower |
| K-58 | WAP activity / نشاط تصاريح دخول المناطق | approved in period; Active at as_of; suspensions in period by reason (ops / violation / dependency); WAP-days blocked (Approved, inside validity, not Active) | counts | — |
| K-59 | **NOTAM request lead-time compliance** / الالتزام بمهلة طلب NOTAM | n(NTM submitted to ops in period with late_request = false) ÷ n(NTM submitted in period) × 100 | %, 1 dp | higher |
| K-60 | Obstacle clearances / موافقات العوائق | Active (Approved*, valid today) at as_of; expiring ≤ 7 days; rejected in period; active with ols_penetration | counts | — |

### 6.9 Leading-indicator warnings (extend Phase 1 §6.9; monthly job on day 2, per project and per tier-1 tree)
- **E5** K-49 at end of month M < `induction_coverage_warning_pct` (unrounded).
- **E6** K-53(M) ≥ 2 × mean(K-53 of M−3, M−2, M−1) **AND** K-53(M) ≥ 1.00 % ASSUMPTION.
- **E7** n(OFF-05 offences in M) ≥ 1, or ADP suspensions in M ≥ 3 ASSUMPTION.

### 6.10 Worked examples (exact; backend unit tests must match)

**X1 — induction validity.** GEN delivered 2026-01-12, 12 months → valid_until = add_months(2026-01-12, 12) − 1 = **2027-01-11**. AIR delivered 2025-10-14 → **2026-10-13**; long alerts on 2026-09-13, 09-29, **10-06**, 10-13; status Expired from 2026-10-14 00:05. Month-end: 2026-08-31 + 6 months → add_months = 2027-02-28 → valid_until **2027-02-27**.

**X2 — pass effective validity (Rajesh Nair).** card 2027-05-31, Iqama 2027-03-14, no planned demob, engagement demob null, project end 2028-12-31, background cleared 2025-05-20 → recheck_due 2027-05-20. eff = **2027-03-14**, limiting_factor = `worker.id_expiry_date`; 30-day alert **2027-02-12**. After Iqama renewal to 2028-03-14: eff = min(2027-05-31, 2028-03-14, 2028-12-31, 2027-05-20) = **2027-05-20** (limiting: background recheck).

**X3 — ADP / AVP.** Rajesh ADP own 2028-02-01, licence 2029-06-30, pass eff 2027-03-14 → ADP eff **2027-03-14**. VEH-0002 AVP own 2027-02-28, istimara 2027-04-30, insurance 2026-10-20, MVPI 2027-01-15 → eff **2026-10-20** (insurance); on 2026-10-06 days_left = **14** → 14-day alert today. (v1.2 note: this example is on the Phase 2 seed, with no equipment provider. With the Phase 4 seed, VEH-0003's AVP AVP-OEXX-26-0120 has effective validity 2026-11-05, limiting factor `equipment_certificate` — `4-third-party-cert.md` Z10.)

**X4 — obstacle heights.** (a) OBS-0004: 612.40 + 32.00 = **644.40 m AMSL**; OLS 655.00 → margin **10.60 m** (34.78 ft); zone max 12.00 → reasons [`zone_height_exceeded`, `operator_requires`]. (b) 25 m crane on Z-TWB: top 637.40; OLS 642.50 → margin **5.10 m** (16.73 ft) > buffer 3.00 → reasons [`zone_height_exceeded` (25 > 6), `operator_requires`]. (c) OBS-0009, 35 m crane on Z-TWB: top **647.40**; margin −4.90 → penetration **4.90 m (16.08 ft)** → reasons [`zone_height_exceeded`, `ols_penetration`, `operator_requires`]. (d) 30 m crane on Z-TWB: top 642.40, margin 0.10 ≤ buffer 3.00 → `within_ols_buffer` added.

**X5 — ADP points (Jomar Santos).** Offences 2025-11-20 OFF-01 (3), 2026-03-05 OFF-04 (6), 2026-09-14 OFF-01 (3). points_12m(2026-09-14) = window (2025-09-14, 2026-09-14] → 3 + 6 + 3 = **12** ≥ 12 → suspended 2026-09-14, suspension_end = 2026-09-14 + 30 − 1 = **2026-10-13**; reinstatement allowed from **2026-10-14**. points_12m(2026-11-20) = window (2025-11-20, 2026-11-20] → **9** (the 2025-11-20 offence drops out).

**X6 — induction coverage, as_of 2026-09-30.** ANIA-EXP: 3,371 ÷ 3,412 × 100 = 98.798… → **98.8 %** (no E5). RBT-52: 640 ÷ 654 × 100 = 97.859… → **97.9 %** < 98 → **E5 raised** for RBT-52, Sep 2026.

**X7 — gate denial rate, Sep 2026.** ANIA-EXP 449 ÷ 74,880 × 100 = 0.5996… → **0.60 %**; previous months 0.55 %, 0.62 %, 0.58 % (unrounded fixture values 412/74,909, 470/75,806, 433/74,655 → 0.5500 %, 0.6200 %, 0.5800 %) → mean 0.5833 % → 2 × mean = 1.1667 % → no E6. RBT-52 62 ÷ 13,520 = 0.4586 → **0.46 %**.

**X8 — pass returns, Sep 2026 ANIA-EXP.** 12 items due (return_due_on in Sep, ≤ as_of 2026-09-30): 9 returned on time, 1 returned late (due 09-23, returned 09-26), 2 not returned (Arjun Pillai pass + ADP, due 09-23). K-54 = 9 ÷ 12 = **75.0 %**; K-55 = **2** (7 days overdue, bucket 1–7).

**X9 — WAP window vs NOTAM.** WAP-0031 window 23:00–05:00 on 2026-10-05 = 2026-10-05T20:00Z → 2026-10-06T02:00Z; NTM-0012 effective 2026-10-01T20:00Z → 2026-10-22T02:00Z, DAILY 2000-0200 → covered. Last window 2026-10-21 23:00 → 2026-10-22 05:00 local = 02:00Z = effective_to → covered. A scan 2026-10-07 04:30 local is inside the window of 2026-10-06 → allowed; 2026-10-06 22:00 local → `WAP_OUTSIDE_WINDOW`; an `out` scan at 05:12 local is not flagged (grace 15 min), at 05:20 is flagged `late_exit`.

**X10 — offence rate, Sep 2026 ANIA-EXP.** 4 offences, 236 Active ADPs at 2026-09-30 → 4 × 100 ÷ 236 = 1.6949 → **1.69 per 100 ADPs**; ADP suspensions 1; OFF-05 0 → no E7. NOTAM lead compliance: 6 requests submitted in Sep, 5 on time → **83.3 %**.

**X11 — K-50 fixture (not seed).** 40 first attempts in the month, 37 passed → **92.5 %**; second attempts are excluded from both terms.

## 7. Alerts & expiries

Channels as Phase 1 (in-app + email; email in recipient language). Workers have no accounts: alerts about a worker go to the Contractor HSE Rep of the deployment's engagement (C scope, i.e. also parent-tree reps) and to HSE Officers. Texts carry worker_no, name and credential number but **never ID numbers or background status**.

| Trigger | Recipient | Timing | Channel |
|---|---|---|---|
| Induction expiry (any course) | Contractor HSE Rep; HSE Officer at 7 and 0 | 30 / 14 / 7 / 0 days before valid_until | In-app; email digest 07:00 |
| Re-induction due (new course version, IN-9) | Contractor HSE Reps; HSE Officers | On publish; 7 days before and on reinduction_due_on | In-app + email |
| Worker ID (Iqama) expiry | Contractor HSE Rep; HSE Officer at 0 | 30 / 14 / 7 / 0 days | In-app + email |
| Passport registration > 60 / 90 days (WK-8) | Contractor HSE Rep | On day 60 and 90 | In-app |
| Airport pass expiry (effective, with limiting factor) | Contractor HSE Rep; HSE Officer | 30 / 14 / 7 / 0 | In-app + email |
| Background recheck due | HSE Officer only (sensitive) | 30 / 14 / 7 / 0 days before recheck_due | In-app + email |
| Application submitted / returned / endorsed / decided | HSE Officer (submitted); submitter (returned, decided — Refused shown generically, AP-13) | Immediately | In-app |
| Application stale (AP-14) | HSE Officer; HSE Manager at 2 × stale days | At stale days, then weekly | In-app + email |
| ADP / AVP expiry; vehicle document expiry | Contractor HSE Rep; HSE Officer at 7 and 0 | 30 / 14 / 7 / 0 | In-app + email |
| ADP auto-suspended (points, OFF-05/06) or revoked | Contractor HSE Rep; HSE Officer; HSE Manager (OFF-05, revocation) | Immediately | In-app + email |
| ADP suspension period ended (reinstatement possible) | HSE Officer | On suspension_end + 1 | In-app |
| Raised suspension awaiting confirmation (LC-3) | HSE Officers | Immediately; at 48 h; auto-lift notice at 72 h | In-app + email |
| Any suspension / revocation of a credential | Contractor HSE Rep of the subject; HSE Officers | Immediately | In-app + email |
| Return due / overdue | Contractor HSE Rep; HSE Officer from 1 day overdue; HSE Manager at 7 days overdue | On Return Due; daily 07:00 while overdue | In-app + email (digest) |
| Lost pass reported; authority not notified within lost_report_hours | HSE Officer; HSE Manager at deadline | Immediately; at deadline | In-app + email |
| Scan of a lost/revoked/rotated token (LC-12) | HSE Officer; HSE Manager | Immediately | In-app + email + SMS ASSUMPTION |
| Admitted despite denial (GC-14) | HSE Officer; HSE Manager | Immediately | In-app + email |
| WAP submitted / approved / rejected / returned | Approvers (submitted); requester (others) | Immediately | In-app |
| WAP Approved but blocked at valid_from (WA-13) | Requester; supervisor's Contractor HSE Rep; approver | At valid_from 00:00 and each window start while blocked | In-app + email |
| WAP crew member auto-excluded (WA-10) | Requester; Contractor HSE Rep | Immediately | In-app |
| WAP suspended (ops / dependency / contractor) | Requester; Contractor HSE Rep; approver; HSE Officers | Within 60 s | In-app + email + SMS for ops events ASSUMPTION |
| WAP / NOTAM / obstacle clearance ending | Requester; Contractor HSE Rep | 72 h / 24 h / 0 h before end | In-app |
| NOTAM request late (NT-2) or still not Issued 48 h before requested start | Requester; HSE Officer | On submit; at T−48 h | In-app + email |
| NOTAM cancelled / expired with linked WAPs | Requesters; approvers; HSE Officers | Immediately | In-app + email |
| Obstacle clearance submitted late / decision recorded / suspended (OB-7) | Requester; HSE Officer | Immediately | In-app + email |
| Operational suspension started / ended | All requesters/supervisors' reps and approvers of affected WAPs; HSE Officers | Within 60 s | In-app + email + SMS ASSUMPTION |
| Leading warnings E5–E7 | HSE Manager; HSE Officers; Contractor HSE Rep of affected tree | Monthly, day 2 | In-app + email |

## 8. Reports / KPIs fed

### 8.1 Dashboard additions (Phase 1 §8.1)
1. **Leading tiles** (new): induction coverage K-49, gate denial rate K-53 (+ K-53b chip), pass return compliance K-54, NOTAM lead-time compliance K-59, airside offence rate K-57. K-38 tile switches source (KA-2).
2. **Access band** (airport projects): active deployed workers K-48, active passes / ADPs / AVPs, Active WAPs now, Active obstacle clearances K-60, ops suspension in force (yes/no with zones).
3. **Chart C10** Gate checks by month (bars) with denial rate line; **C11** denial reasons breakdown (top 8) for the period; **C12** expiring credentials next 90 days by week and kind.
4. Filters D-2 apply (site, zone, contractor with subcontractors, period); gate KPIs also filter by gate.

### 8.2 Expiring-items panel (Phase 1 `GET /dashboard/expiring-items`) — new `ExpiringItemKind` values
`induction_expiry`, `reinduction_due`, `worker_id_expiry`, `airport_pass_expiry`, `bg_recheck_due` (HSE Manager/Officer only), `adp_expiry`, `adp_suspension_end`, `avp_expiry`, `vehicle_document_expiry`, `wap_expiry`, `notam_expiry`, `obstacle_clearance_expiry`, `pass_return_due`. Each item: ref (credential number), title (worker_no + name, or vehicle_no + fleet_no, or WAP no) — names only for capability 46 holders, otherwise "Worker WKR-nnnnnn"; due_date = effective_valid_until (or return_due_on); days_left; engagement; limiting_factor; detail_path.

### 8.3 Action panel additions
Applications stale (AP-14); raised suspensions awaiting confirmation; unreturned overdue (K-55); lost passes without authority notification; WAPs Approved-but-blocked today; Active ops suspensions; NOTAM requests not Issued within 48 h of start; scans of lost/revoked tokens (last 7 days); admitted despite denial (last 7 days); induction records with LANGUAGE_MISMATCH (last 30 days).

### 8.4 Registers and reports
Worker register; induction register (by course, contractor, validity); pass application tracker (status ageing); pass/ADP/AVP registers with effective validity and limiting factor; offence register; vehicle register; WAP register and today's WAP board per zone (crew counts, windows, NOTAM, clearance); NOTAM log; obstacle clearance register with heights in m/ft; ops suspension log; gate log (capability 76). Exports per P2-10.

### 8.5 Feeds to later phases
Worker + deployment (Phases 3–5 reuse); eligibility service and WAP services (HK-6, Phase 3); hook provider interface (HK-3, Phases 4/5/6); vehicles (Phase 4 equipment register links by vehicle_no/serial); induction records as training evidence (Phase 5); gate logs and offences as contractor-scoring inputs (Phase 6); Phase 1 injury case `worker_id` link (days_on_site from deployment.mobilised_on).

## 9. Acceptance criteria

Fixtures: Appendix A seed; "today" = 2026-10-06 (Asia/Riyadh) unless stated.

**Worker register & PDPL**
1. **Given** worker Rajesh Nair (Iqama 2000001002) exists **When** Contractor HSE Rep Ahmed (RAWABI tree) creates a worker with the same Iqama **Then** 409 `WORKER_EXISTS` with worker_no WKR-000002.
2. **Given** the same duplicate attempt by Contractor HSE Rep Yousef (QIMMA, RBT-52) **Then** 409 `WORKER_EXISTS_OUT_OF_SCOPE` and the body contains no name, worker_no or employer.
3. **Given** HSE Officer Noura lists ANIA-EXP workers **Then** Rajesh's id_number shows `2*******02` and the full number is absent from the payload.
4. **Given** Noura calls unmask on Rajesh with reason `pass_application` **Then** the full number is returned and a `sensitive_field_read` entry with field `id_number` exists.
5. **Given** Site Engineer Omar **When** he calls unmask **Then** 403; **and** Viewer Sarah listing workers gets 403.
6. **Given** a worker payload with adult_attestation = false **Then** 422 `ADULT_ATTESTATION_REQUIRED`.
7. **Given** any search request with a partial ID "2000001" **Then** no worker is matched (exact match only).
8. **Given** the database row of any worker **Then** id_number is not stored in plaintext (ciphertext ≠ value; CI check on seed).
9. **Given** Osman Idris (Iqama expiry 2026-10-20) **Then** a 14-day `worker_id_expiry` alert to Contractor HSE Rep Ahmed (RAWABI tree, which contains NAJD) exists today and its text contains no ID number.

**Induction**
10. **Given** GEN delivered 2026-01-12 (12 months) **Then** valid_until = 2027-01-11; delivered 2026-08-31 with 6 months **Then** 2027-02-27 (X1).
11. **Given** Hamza Al-Shehri scored 65 % on 2026-09-02 **Then** the record is Failed and the deployment stays Pending Induction; **given** 85 % on 2026-09-03 **Then** Valid until 2027-09-02 and the deployment becomes Mobilised with an access-card token.
12. **Given** a worker with 3 failed GEN attempts in 30 days **When** a 4th is recorded **Then** 422 `INDUCTION_ATTEMPTS_EXCEEDED`.
13. **Given** Contractor HSE Rep Ahmed **When** he records an AIR induction **Then** 403 `DELIVERER_NOT_ALLOWED`.
14. **Given** an AIR induction for a worker without Valid GEN **Then** 422 `INDUCTION_PREREQUISITE`.
15. **Given** delivery_language `en` for Abdul Karim Mia (primary bn) with interpreter_used = false **Then** saved with warning `LANGUAGE_MISMATCH` and listed in the action panel.
16. **Given** Suman Tamang's GEN valid_until 2026-09-30 **When** the job runs 2026-10-01 00:05 **Then** status Expired; running it again changes nothing.
17. **Given** course AIR v3.0 published 2026-10-06 with requires_reinduction **Then** every Valid AIR v2.0 record has reinduction_due_on 2026-11-05.
18. **Given** ANIA-EXP induction_register_from = 2025-03-01 **When** K-38 is requested for Sep 2026 **Then** it equals the count of passed `general_site` induction records delivered in Sep 2026 (= the seeded daily-return sum, no reconciliation note); **given** induction_register_from = null **Then** it equals the daily-return sum.

**Zone profiles & hooks**
19. **Given** a new airside zone with airside_area taxiway_strip **Then** its profile has [GEN, AIR], access_permit_required = true, adp_category_required = manoeuvring, lvp_withdrawal_required = true.
20. **Given** Noura sets access_permit_required = false on Z-TWB **Then** 422 `PROFILE_LOOSENING`.
21. **Given** hook policy training_course = warn and Z-APR-21 requires `training_course: AVSEC-AWR` **When** Saad Al-Dosari is checked **Then** that item is `warn` with `HOOK_NOT_AVAILABLE` and he remains eligible.
22. **Given** no Phase 5 provider is registered **When** HSE Manager sets hook_policy.training_course = block **Then** 422 `HOOK_PROVIDER_MISSING`.
23. **Given** a test provider returning not_met for AVSEC-AWR and policy block **Then** Saad is not eligible for Z-APR-21 with reason `HOOK_NOT_MET`.

**Airport passes**
24. **Given** RBT-52 (not airport) **When** a pass application is created **Then** 422 `NOT_AIRPORT_PROJECT`.
25. **Given** a PERM application for Rajesh with requested_valid_until 2027-05-31 **Then** 422 `VALIDITY_EXCEEDS_LIMIT` naming `worker.id_expiry_date`; with 2027-03-14 it is accepted.
26. **Given** application APA-ANIA-EXP-2026-0142 (PERM, bg in_progress) **When** Approve is recorded **Then** 422 `BACKGROUND_NOT_CLEARED` (AP-4); after background status `cleared` it succeeds.
27. **Given** an application submitted by Noura **When** Noura endorses it **Then** 422 `ENDORSER_NOT_ALLOWED`.
28. **Given** Refused application APA-ANIA-EXP-2026-0118 (Waleed Saleh) **When** Contractor HSE Rep Ahmed reads it **Then** status shows "Refused by issuing authority" and no background_check_* field is present; Noura sees background_check_status `not_cleared` and a `sensitive_field_read` entry is written.
29. **Given** Rajesh's pass **Then** effective_valid_until = 2027-03-14 with limiting_factor `worker.id_expiry_date`; **when** his Iqama expiry changes to 2028-03-14 **Then** pass eff = 2027-05-20 (background recheck) and ADP eff = 2027-05-20 (X2/X3).
30. **Given** a renewal pass is issued for Saad **Then** his previous pass is Revoked `superseded` with custody Return Due, return_due_on = issue date + 3.
31. **Given** an ID copy on an application Issued 31 days ago **When** the retention job runs **Then** the file is deleted and the deletion audited.

**ADP / offences**
32. **Given** Abdul Karim Mia holds escorted pass TEMP-E **When** an ADP is issued **Then** 422 `ADP_PASS_REQUIRED`.
33. **Given** a manoeuvring ADP with rtf_competence = false **Then** 422 `RTF_REQUIRED`.
34. **Given** Jomar Santos's offences (X5) **Then** after the 2026-09-14 offence his ADP is Suspended `points_threshold`; reinstatement on 2026-10-13 → 422 `SUSPENSION_PERIOD_RUNNING`; on 2026-10-14 by Noura → Active.
35. **Given** points_12m for Jomar on 2026-11-20 **Then** 9.
36. **Given** an OFF-05 offence recorded for Saad **Then** his ADP is Suspended `violation` immediately and HSE Manager is alerted; a second suspension within 730 days revokes it.
37. **Given** Rajesh's pass becomes Suspended **Then** his ADP becomes Suspended `dependency_invalid`; reinstating the pass reinstates the ADP automatically (no other suspension open).

**Vehicles / AVP**
38. **Given** VEH-0002 **Then** AVP eff = 2026-10-20 (insurance) and a 14-day alert exists today; **when** the insurance expiry passes unchanged **Then** on 2026-10-21 the AVP is Suspended `vehicle_document_expired`, and a new insurance expiry 2027-10-20 reinstates it automatically.
39. **Given** an AVP checklist with amber_beacon = n.a. **Then** 422 `AVP_PRECONDITION`.
40. **Given** two vehicles with plate ح ط ر 9012 **Then** the second is rejected.

**NOTAM / obstacle**
41. **Given** NTM-0014 submitted 2026-10-03T08:00Z for start 2026-10-08T04:00Z **Then** late_request = true and K-59 counts it as not compliant.
42. **Given** OBS-0009 (35 m on Z-TWB) **Then** top 647.40, penetration 4.90 m / 16.08 ft and reasons include `ols_penetration`; **when** approved without `notam_required` and `obstruction_light` **Then** 422 `OB_CONDITIONS_REQUIRED`.
43. **Given** OBS-0004 **Then** top 644.40, margin 10.60 and reasons [zone_height_exceeded, operator_requires] (X4).
44. **Given** a 30 m crane on Z-TWB **Then** reasons include `within_ols_buffer`.
45. **Given** OBS-0007 (condition notam_required, linked NTM-0014 not Issued) **When** the date reaches 2026-10-08 **Then** OBS-0007 is Suspended (system) and WAP-0035 shows blockers NOTAM_NOT_ISSUED and OBS_NOT_ACTIVE.

**WAP & ops suspension**
46. **Given** WAP-0035 Approved with blocker NOTAM_NOT_ISSUED **When** valid_from 2026-10-08 arrives **Then** it stays Approved and the blocked alert is sent; **when** NTM-0014 is Issued covering 04:00–13:00Z daily 08–12 Oct **Then** it becomes Active.
47. **Given** GULFPAVE's WAP requested by Ahmed **When** a permit_issuer test user employed by RAWABI (GULFPAVE's parent) approves **Then** 422 `SOD_CONFLICT`; **when** Khalid approves a WAP he requested himself **Then** 422 `SOD_CONFLICT`; Khalid approving Ahmed's WAP succeeds.
48. **Given** a WAP with valid_from 2026-10-07 and valid_to 2026-11-06 (31 days) **Then** 422 (wap_max_days 30).
49. **Given** DLIFT is Suspended **When** a WAP is submitted for DLIFT **Then** 403 `CONTRACTOR_SUSPENDED`.
50. **Given** WAP-0031 Active **When** an LVP ops event is declared on S-AIR **Then** within 60 s WAP-0031 (Z-TWB) is Suspended `ops_suspension` and WAP-0033 (Z-APR-21, apron) is not; ending the event leaves WAP-0031 Suspended; resume without FOD check → 422 `FOD_HANDBACK_REQUIRED`; with FOD check `clear` → Active.
51. **Given** WAP-0031 and Abdul Karim's AIR induction valid_until 2026-10-13 **When** the window of 2026-10-14 starts **Then** he is `excluded` with INDUCTION_EXPIRED, the requester is notified, and the WAP stays Active.
52. **Given** NTM-0012 is cancelled **Then** WAP-0031 becomes Suspended `dependency_invalid` within 60 s.
53. **Given** Viewer Sarah opens WAP-0031 **Then** she sees crew count 9 and no crew names.

**Gate check**
54. **Given** Suman Tamang's card at G-AAP3 for Z-APR-21 **Then** DENIED `INDUCTION_EXPIRED`; the response contains no ID number or nationality.
55. **Given** Bikash Rai (DLIFT, suspended) at G-RBT-01 **Then** DENIED `CONTRACTOR_SUSPENDED`; with setting warn → GRANTED_WITH_WARNING.
56. **Given** Abdul Karim's card at G-AAP3 for Z-TWB on 2026-10-06 23:30 **Then** PENDING_ESCORT; Tariq Mahmood's card within 120 s → Abdul GRANTED_WITH_WARNING (`EXPIRING_7D`) and Tariq GRANTED; Tariq's card after 121 s → Abdul DENIED `ESCORT_REQUIRED`.
57. **Given** Mahmoud Fathy already escorts 5 persons in on Z-APR-21 today **When** a 6th escorted visitor is paired **Then** DENIED `ESCORT_RATIO_EXCEEDED`.
58. **Given** Rajesh at G-AAP3 for Z-TWB at 2026-10-06 22:00 **Then** DENIED `WAP_OUTSIDE_WINDOW`; at 2026-10-07 04:30 **Then** GRANTED.
59. **Given** Arjun Pillai's (demobilised) card **Then** DENIED `WORKER_NOT_DEPLOYED`; a lost-and-rotated card token returns DENIED `CREDENTIAL_LOST` and alerts the HSE Officer.
60. **Given** VEH-0004 (no AVP, listed on WAP-0033) at G-AAP3 for Z-APR-21 on 2026-10-06 10:00 **Then** PENDING_ESCORT_VEHICLE; VEH-0006 sticker within 120 s → PENDING_DRIVER; Mahmoud Fathy's card → GRANTED. VEH-0002 (not on a Z-APR-21 WAP) as escort vehicle → DENIED `WAP_MISSING`.
61. **Given** VEH-0005 (max working 9.50 m) for Z-ILS33R on 2026-10-09 with WAP-0035 not Active **Then** DENIED with `WAP_NOT_ACTIVE` and `HEIGHT_CLEARANCE_REQUIRED`.
62. **Given** Ali Hassan at G-RBT-TC for Z-TC01 with hook personnel_certificate (Phase 4, warn) **Then** GRANTED_WITH_WARNING `HOOK_NOT_AVAILABLE`.
63. **Given** Contractor HSE Rep Yousef scans Bikash (DLIFT, in QIMMA tree) **Then** the full result is shown; Ahmed (no RBT-52 assignment) scanning the same card **Then** `OUT_OF_SCOPE` with no personal data.
64. **Given** any QR payload generated by the seed **Then** it matches `^HSE2:(AC|VS|WP|PT|EQ):[A-Za-z0-9_-]{22}$` and contains no name or ID (CI check).
65. **Given** a guard admits Suman despite DENIED with a reason **Then** the gate-log row has admitted_despite_denial = true and the HSE Officer and HSE Manager receive an immediate alert.
66. **Given** a gate device session **When** it calls the worker list endpoint **Then** 403.

**KPIs & dashboard**
67. **Given** the seed, as_of 2026-09-30 **Then** K-49 ANIA-EXP = 98.8 %, RBT-52 = 97.9 % and E5 is raised for RBT-52 only (X6).
68. **Given** Sep 2026 **Then** K-53 ANIA-EXP = 0.60 %, RBT-52 = 0.46 %, and no E6 (X7).
69. **Given** Sep 2026 ANIA-EXP **Then** K-54 = 75.0 % and K-55 = 2 (X8); K-57 = 1.69 per 100 ADPs; K-59 = 83.3 % (X10).
70. **Given** the X11 fixture **Then** K-50 = 92.5 %.
71. **Given** expiring items for ANIA-EXP with within_days = 30 today **Then** the list includes Abdul Karim's AIR induction (7 days), Osman's worker ID (14), VEH-0002 AVP (14, limiting factor insurance), and no background recheck item for Contractor HSE Rep Ahmed.
72. **Given** Viewer Sarah opens the access KPIs **Then** values are shown and no list contains names, worker_no or plates.
73. **Given** the AI is asked "How many airport passes expire this month?" **Then** T14 is called and the model input contains no worker names, IDs, worker_no or plates (AI-5 log check).

**i18n**
74. **Given** the UI in Arabic **Then** every Phase 2 status, reason code and field label in this spec renders in Arabic (CI key check, Phase 0 rule 41), plate letters render in Arabic with digits LTR, and NOTAM numbers/times render LTR.

## 10. Open questions for the HSE Manager

1. **Airport pass scheme:** will the airport operator give you its official pass categories, area codes and colours (the AP-CAT/AP-AREA seeds are fictional)? Who is your interface to the pass office — an HSE Officer, a security coordinator, or a client security team?
2. **Roles:** pass processing is given to HSE Officers and gate checks to gate devices plus existing roles. Do you want new roles (e.g. "Security / Pass Coordinator", "Gate Guard") instead? That changes the Phase 0 role list.
3. **Background checks:** confirm the platform keeps only the status and dates (never the reason). What recheck interval does the operator apply (assumed 24 months)?
4. **Validity defaults:** pass ≤ 24 months, temporary escorted 30 days, ADP 24 months, AVP 12 months, GEN/AIR induction 12 months, ILS briefing 6 months, tower-crane zone briefing 12 months. Which are the client's or operator's values?
5. **Escort ratios:** 1 : 5 on apron, 1 : 2 on the manoeuvring area, vehicle escort 1 : 3 apron / 1 : 1 manoeuvring. Must manoeuvring-area escorts also hold a manoeuvring ADP (assumed yes)?
6. **ADP points:** adopt the operator's offence/points scheme (OFF list is a fictional default: 12 points in 12 months → 30-day suspension; second suspension in 2 years → revocation)?
7. **Lead times and thresholds:** NOTAM request 7 days (AIRAC-type changes 42 days), obstacle clearance 30 days, OLS safety buffer 3.00 m, height threshold 45 m for non-airport projects. Please confirm the operator's/GACA's current values.
8. **RBT-52 tower cranes:** a 52-storey tower in Riyadh will very likely need GACA height approval for the building and its cranes. Should RBT-52 track obstacle clearances in Phase 2? (Recommended. v1.1: provisionally answered yes — seed OBS-RBT-52-2026-0001 for TC-01 added at Phase 3's request; confirm.)
9. **Suspended contractors at the gate:** deny all its workers (current default, strictest) or allow with warning so they can demobilise and fix the issue?
10. **Hooks:** when Phase 4/5 go live, should the hook policy switch to "block" automatically, or stay "warn" until you switch it? — v1.2: answered for Phase 4 kinds by `4-third-party-cert.md` HK4-5 (automatic after a 7-day / 30-day transition; confirm via its §10 Q5); Phase 5/6 kinds still open.
11. **Gate logs:** keep 12 months? Is any use for attendance/payroll or client headcount reporting wanted? Today it is prohibited (P2-8).
12. **Offline gates:** is mobile data reliable at your airside access points? If not, we need an offline mode (signed QR + revocation list cached ≤ 15 min), which needs a spec change.
13. **Induction delivery:** may contractor HSE reps deliver the general site induction (assumed yes), or only the client/PMC HSE team?
14. **Full ID numbers for contractor reps:** may a tier-1 rep unmask IDs of its subcontractors' workers (assumed yes, needed for pass applications), or only its own engagement's?
15. **Pass return:** 3 days after demobilisation? Does the operator fine contractors for unreturned passes, and should the platform track the fines?
16. **K-38 source:** switch the dashboard's induction count from the daily return to the induction register (assumed), and drop the daily-return field later?
17. **Re-induction after absence:** do you want automatic re-induction after a long absence (e.g. 90 days without any gate entry)? Off by default.
18. **Operator works permit:** does the airport operator issue its own airside works/access permit number that we should record on each WAP (field `operator_permit_ref` provided), and must its approval come before ours?
19. **WAP approver:** is the client's Permit Issuer the right approver for airside access, or must the airport operator's airside operations approve each WAP (then we record their approval as a precondition)?

---

## Appendix A — Seed data (fictional; `seed_fake = true` on every row; all names, IDs, plates, numbers fake)

### A.1 Principles
1. IDs follow Phase 1 A.1 pattern `^[12]0{5}\d{4}$`: named workers 2000000017 and 20000010xx/11xx; bulk workers 2000002000–2000009999 (Iqama) and 1000002000–1000002999 (National ID); passports `TEST` + 5 digits. CI check rejects any other ID in seeds.
2. Plates: digits 9001–9099 only; VINs `TESTVIN` + 10 digits; pass/permit/NOTAM/GACA refs contain `TEST` or use NOTAM series numbers A0990–A1010/26 (fictional).
3. Bulk deployments Mobilised at 2026-09-30: ANIA-EXP RAWABI 1,380 · NAJD 960 · GULFPAVE 720 · SAHARA 352 (= 3,412, K-48) — RBT-52 QIMMA 590 · DLIFT 64 (= 654). Named workers below are included in these counts. GEN Valid at 2026-09-30: ANIA-EXP 3,371, RBT-52 640 (X6). Airside crew (GULFPAVE + RAWABI S-AIR share) ≈ 900 workers with AIR and passes; 236 Active ADPs at 2026-09-30.
4. Induction history 2025-03 … 2026-09: per engagement-month, passed GEN records = the Phase 1 seeded daily-return Σ inductions (so KA-2 shows no reconciliation note); seed `induction_register_from` = ANIA-EXP 2025-03-01, RBT-52 2025-01-15 (project starts); ≈ 8 % extra failed first attempts; delivery languages ≈ ur 25 %, hi 20 %, bn 15 %, ar 12 %, ne 10 %, tl 8 %, en 10 %.
5. Gate log totals (in-direction): ANIA-EXP Jun 74,909 / 412 denied, Jul 75,806 / 470, Aug 74,655 / 433, Sep 74,880 / 449 (reasons Sep: INDUCTION_EXPIRED 151, PASS_AREA_NOT_COVERED 88, WAP_MISSING 71, ESCORT_REQUIRED 54, ADP_MISSING 33, ID_EXPIRED 29, others 23; admitted_despite_denial 2). RBT-52 Sep 13,520 / 62 (INDUCTION_EXPIRED 30, CONTRACTOR_SUSPENDED 18, INDUCTION_MISSING 14). Working-week pattern per Phase 1 A.4.
6. Names bilingual from the Phase 1 fake list plus those below; no real persons.

### A.2 Reference lists (ANIA-EXP; fictional — `VERIFY` with operator)

**Induction courses**

| Project | Code | Type | EN / AR | Version | Validity | Pass mark | Prereq | Delivered by |
|---|---|---|---|---|---|---|---|---|
| ANIA-EXP | GEN | general_site | General Site HSE Induction / التعريف العام بالسلامة في الموقع | 3.1 | 12 m | 80 | — | hse_officer, contractor_hse_rep |
| ANIA-EXP | AIR | airside | Airside Safety & FOD Awareness / السلامة في الجانب الجوي والتوعية بالأجسام الغريبة | 2.0 | 12 m | 80 | GEN | hse_officer |
| ANIA-EXP | ILS | zone_specific | ILS Critical/Sensitive Area Briefing / إحاطة المناطق الحرجة والحساسة لنظام ILS | 1.0 | 6 m | 90 | AIR | hse_officer |
| ANIA-EXP | VIS | visitor | Visitor Safety Briefing / إحاطة السلامة للزوار | 1.0 | 1 day | — (no test) | — | hse_officer |
| RBT-52 | GEN | general_site | General Site HSE Induction / التعريف العام بالسلامة في الموقع | 2.4 | 12 m | 80 | — | hse_officer, contractor_hse_rep |
| RBT-52 | TC | zone_specific | Tower Crane Exclusion Zone Briefing / إحاطة منطقة حظر الرافعة البرجية | 1.2 | 12 m | 80 | GEN | hse_officer, contractor_hse_rep |

**Pass categories (AP-CAT)**: PERM Permanent Airport ID / تصريح مطار دائم — unescorted, bg required, 730 days, red, allows ADP · TEMP-U Temporary Unescorted / تصريح مؤقت دون مرافقة — unescorted, bg required, 90 days, blue, allows ADP · TEMP-E Temporary Escorted / تصريح مؤقت بمرافقة — escorted, bg not required, 30 days, yellow, no ADP · VIS Visitor Escorted / تصريح زائر بمرافقة — escorted, 1 day, white, no ADP.

**Area codes (AP-AREA)**: A Apron & Stands / الساحات ومواقف الطائرات — red — apron — [Z-APR-21] · M Manoeuvring Area / منطقة المناورة — yellow — manoeuvring — [Z-TWB, Z-ILS33R] · T Terminal Airside / الجانب الجوي للمبنى — blue — terminal_airside — [] · R Airside Service Roads / طرق الخدمة الجوية — orange — airside_roads — [].

**Zone access profiles**

| Zone | Inductions | Pass area | WAP | ADP / AVP | Escort ratio | LVP | ILS NOTAM | Hooks |
|---|---|---|---|---|---|---|---|---|
| Z-APR-21 | GEN, AIR | A | yes | apron / apron | 5 | no | no | training_course AVSEC-AWR |
| Z-TWB | GEN, AIR | M | yes | manoeuvring / manoeuvring | 2 | yes | no | training_course AVSEC-AWR |
| Z-ILS33R | GEN, AIR, ILS | M | yes | manoeuvring / manoeuvring | 2 | yes | yes | training_course AVSEC-AWR |
| Z-PIERB, Z-MSCP, Z-LAY1 | GEN | — | no | — | — | no | no | — |
| RBT-52 Z-CORE, Z-B4, Z-FAC | GEN | — | no | — | — | no | no | — |
| RBT-52 Z-TC01 | GEN, TC | — | no | — | — | no | no | personnel_certificate CRANE-OPERATOR (for crane_operator trade), RIGGER (rigger) |

Vehicle-category hooks: mobile_crane/crawler_crane → equipment_certificate CRANE-TPI; mewp → MEWP-TPI; forklift → FORKLIFT-TPI; telehandler → TELEHANDLER-TPI. ADP category hooks: manoeuvring/apron → training_course AIRSIDE-DRV. Pass category hooks: PERM/TEMP-U → training_course AVSEC-AWR. All policies `warn`.

### A.3 Named workers

| Worker | Name EN / AR | Nat. | ID (type) · expiry | Project · engagement · trade · site | Inductions (valid_until) | Pass / ADP | Scenario |
|---|---|---|---|---|---|---|---|
| WKR-000001 | Imran Hussain / عمران حسين | PK | 2000000017 (iqama) · 2027-08-31 | ANIA-EXP · NAJD · scaffolder · S-LAND | GEN 2026-08-25 → 2027-08-24 | — | Linked to injury case INC-ANIA-EXP-2026-0147-P1 (worker_id) |
| WKR-000002 | Rajesh Nair / راجيش ناير | IN | 2000001002 · 2027-03-14 | ANIA-EXP · GULFPAVE · plant_operator · S-AIR | GEN → 2027-01-11; AIR → 2027-01-12 | PERM ANIA-AP-26-01877 [A, M] card 2025-06-01…2027-05-31, bg cleared 2025-05-20; ADP-OEXX-26-0042 manoeuvring, own 2028-02-01, licence ksa heavy_equipment 2029-06-30 | X2/X3; WAP-0031 driver |
| WKR-000003 | Jomar Santos / جومار سانتوس | PH | 2000001003 · 2027-07-10 | ANIA-EXP · GULFPAVE · driver · S-AIR | GEN → 2027-02-19; AIR → 2027-02-20 | PERM ANIA-AP-25-01422 [A] card →2027-04-30; ADP-OEXX-25-0057 apron, own 2027-07-31 — **Suspended (points) 2026-09-14…10-13** | X5; offences OFF-ANIA-EXP-2025-0044, -2026-0012, -2026-0031 |
| WKR-000004 | Abdul Karim Mia / عبد الكريم ميا | BD | 2000001004 · 2027-11-30 | ANIA-EXP · GULFPAVE · labourer · S-AIR | GEN → 2027-01-31; **AIR 2025-10-14 → 2026-10-13** | TEMP-E ANIA-AP-26-02210 [A, M] 2026-09-29 → 2026-10-28 (via APA-…-0139 Issued); PERM application **APA-ANIA-EXP-2026-0142 Lodged, bg in_progress** | Escorted crew on WAP-0031 (escort Tariq); 7-day alert today; excluded from 2026-10-14 |
| WKR-000005 | Mahmoud Fathy / محمود فتحي | EG | 2000001005 · 2028-01-20 | ANIA-EXP · RAWABI · supervisor · S-AIR | GEN, AIR, ILS valid (→ 2027-03-09, 2027-03-10, 2026-12-15) | PERM ANIA-AP-25-00710 [A, M] →2027-09-30; ADP-OEXX-25-0019 manoeuvring | WAP-0033 supervisor; escort of visitor WKR-000012; ratio test |
| WKR-000006 | Suman Tamang / سومان تامانغ | NP | 2000001006 · 2027-05-05 | ANIA-EXP · RAWABI · electrician · S-AIR | **GEN 2025-10-01 → 2026-09-30 (Expired)**; AIR → 2027-02-14 | PERM ANIA-AP-25-01105 [A] | Gate DENIED INDUCTION_EXPIRED |
| WKR-000007 | Saad Al-Dosari / سعد الدوسري | SA | 1000001007 (national_id) · 2030-02-11 | ANIA-EXP · RAWABI · engineer · S-AIR, S-LAND | GEN, AIR, ILS valid | PERM ANIA-AP-25-00402 [A, M]; ADP-OEXX-25-0008 manoeuvring | Hook warn test; renewal/OFF-05 tests |
| WKR-000008 | Waleed Saleh / وليد صالح | YE | 2000001008 · 2027-01-25 | ANIA-EXP · SAHARA · scaffolder · S-LAND | GEN valid | **APA-ANIA-EXP-2026-0118 Refused 2026-09-10** (bg not_cleared — sensitive) | AP-13 visibility |
| WKR-000009 | Osman Idris / عثمان إدريس | SD | 2000001009 · **2026-10-20** | ANIA-EXP · NAJD · rigger · S-LAND | GEN valid | — | 14-day ID alert today |
| WKR-000010 | Arjun Pillai / أرجون بيلاي | IN | 2000001010 · 2027-06-01 | ANIA-EXP · GULFPAVE · driver · S-AIR — **Demobilised 2026-09-20** | GEN, AIR (unchanged) | PERM ANIA-AP-25-00933 and ADP-OEXX-25-0031 **Revoked (demobilised), Return Due 2026-09-23, not returned** | X8; gate WORKER_NOT_DEPLOYED |
| WKR-000011 | Noura Al-Qahtani / نورة القحطاني | SA | 1000001011 · 2031-04-02 | ANIA-EXP · client_pmc_staff (user noura) · S-AIR, S-LAND | GEN, AIR, ILS valid | PERM ANIA-AP-25-00011 [A, M] | Client staff with pass |
| WKR-000012 | David Brown / ديفيد براون | GB | TEST00012 (passport) · 2033-08-14 | ANIA-EXP · visitor | VIS 2026-10-06 → 2026-10-06 | VIS ANIA-AP-26-V0412 [A] 2026-10-06 | Escorted by Mahmoud Fathy |
| WKR-000013 | Tariq Mahmood / طارق محمود | PK | 2000001013 · 2027-12-12 | ANIA-EXP · GULFPAVE · supervisor · S-AIR | GEN, AIR, ILS valid | PERM ANIA-AP-25-00988 [A, M]; ADP-OEXX-25-0044 manoeuvring | WAP-0031 supervisor & escort |
| WKR-000101 | Imtiaz Ahmed / امتياز أحمد | PK | 2000001101 · 2027-09-30 | RBT-52 · QIMMA · steel_fixer · S-TWR | GEN 2026-04-20 → 2027-04-19 | — | Normal access |
| WKR-000102 | Ali Hassan / علي حسن | EG | 2000001102 · 2027-02-28 | RBT-52 · QIMMA · crane_operator · S-TWR | GEN, TC valid | — | Phase 4 hook warn at Z-TC01 |
| WKR-000103 | Ramon Cruz / رامون كروز | PH | 2000001103 · 2027-08-08 | RBT-52 · QIMMA · electrician · S-POD | **GEN 2025-11-06 → 2026-11-05** | — | 30-day alert today |
| WKR-000104 | Bikash Rai / بيكاش راي | NP | 2000001104 · 2027-03-03 | RBT-52 · DLIFT · rigger · S-TWR | GEN valid | — | Contractor suspended → gate DENIED |
| WKR-000105 | Hamza Al-Shehri / حمزة الشهري | SA | 1000001105 · 2032-01-19 | RBT-52 · QIMMA · supervisor · S-TWR | GEN attempt 1 2026-09-02 65 % failed; attempt 2 2026-09-03 85 % → 2027-09-02 | — | Retest |

### A.4 Vehicles (ANIA-EXP)

| Vehicle | Owner | Category | Plate (AR / EN / digits) | Fleet · serial | Travel / max working (m) | Documents | AVP |
|---|---|---|---|---|---|---|---|
| VEH-0001 | GULFPAVE | paver | none | GP-PV-02 · TESTSN-PV-0001 | 3.90 / 3.90 | insurance →2027-03-31 | AVP-OEXX-26-0117 [apron, manoeuvring] own →2027-02-28 |
| VEH-0002 | GULFPAVE | pickup | ح ط ر / J T R / 9012 `VERIFY` letter mapping | GP-LV-07 · TESTVIN0000000002 | 1.90 / 1.90 | istimara →2027-04-30, **insurance →2026-10-20**, MVPI →2027-01-15 | AVP-OEXX-26-0118 [apron, manoeuvring] own →2027-02-28, eff 2026-10-20 |
| VEH-0003 | RAWABI | mobile_crane (50 t) | ر ع ق / R E G / 9003 | RW-MC-03 · TESTVIN0000000003 | 3.95 / 32.00 | istimara →2027-05-31, insurance →2027-05-31, MVPI →2027-02-28 | AVP-OEXX-26-0120 [apron] own →2027-03-31 (hook CRANE-TPI warn) |
| VEH-0004 | RAWABI | tipper | د ل ك / D L K / 9004 | RW-TP-11 · TESTVIN0000000004 | 3.40 / 3.40 | all valid | **none** (escort required) |
| VEH-0006 | RAWABI | pickup | س ص ن / S X N / 9006 | RW-LV-02 · TESTVIN0000000006 | 1.95 / 1.95 | all valid | AVP-OEXX-26-0125 [apron] own →2027-03-31 |
| VEH-0005 | GULFPAVE | excavator (20 t) | none | GP-EX-05 · TESTSN-EX-0005 | 3.10 / 9.50 | insurance →2027-01-31 | AVP-OEXX-26-0131 [apron, manoeuvring] own →2027-03-31 |

### A.5 NOTAM records, obstacle clearances, WAPs, ops events (ANIA-EXP)

| Record | Key data | Status (2026-10-06) |
|---|---|---|
| NTM-ANIA-EXP-2026-0012 | Z-TWB; taxiway_closure; requested 2026-10-01T20:00Z → 10-22T02:00Z, DAILY 2000-0200; submitted 2026-09-22T07:00Z; NOTAM A0999/26 (N), effective as requested; item E "TWY B BTN B2 AND B4 CLSD DUE WIP" | Issued |
| NTM-ANIA-EXP-2026-0014 | Z-ILS33R; ils_outage; requested 2026-10-08T04:00Z → 10-12T13:00Z, DAILY 0400-1300; submitted 2026-10-03T08:00Z → late_request | Requested from AIS |
| NTM-ANIA-EXP-2026-0007…0011 | Background Sep 2026 requests (5), one late (NTM-0009) — with NTM-0012 gives K-59 Sep = 5/6 | Expired/Issued |
| OBS-ANIA-EXP-2026-0004 | VEH-0003 at stand 22 (LM-22), Z-APR-21; ground 612.40; 32.00 m AGL; top 644.40; inner_horizontal 655.00 (OEXX-OLS-DWG-TEST-03); submitted 2026-09-02; GACA-OBS-TEST-0004; approved_with_conditions [obstruction_light, lower_at_night, lower_when_idle]; valid 2026-10-04 → 10-10 | Approved with conditions |
| OBS-ANIA-EXP-2026-0007 | VEH-0005 in Z-ILS33R; 4.50 m (height limiter) > zone 3.00; top 616.90; ols none_applicable; conditions [notam_required, daylight_only, day_marking]; linked NTM-0014; valid 2026-10-08 → 10-12; GACA-OBS-TEST-0007 | Approved with conditions (suspends 10-08 if NTM-0014 not Issued) |
| OBS-ANIA-EXP-2026-0009 | 35 m crane proposal, Z-TWB; top 647.40; OLS 642.50; penetration 4.90 m | Rejected 2026-09-25 |
| OBS-RBT-52-2026-0001 (v1.1) | Tower crane TC-01 (QIMMA), Z-TC01; ground 618.00; 236.00 m AGL; top 854.00 m AMSL; reason height_threshold; GACA-OBS-TEST-0101; conditions [obstruction_light, day_marking]; valid 2026-01-20 → 2027-06-30 | Approved with conditions |
| WAP-ANIA-EXP-2026-0031 | GULFPAVE; Z-TWB; 2026-10-01 → 10-21; 23:00–05:00 daily; crew 9 (Tariq supervisor/escort, Rajesh driver, Abdul Karim escorted by Tariq, 6 bulk workers); VEH-0001, VEH-0002; NTM-0012; WSP-TWB-007; requested by Ahmed, approved by Khalid 2026-09-29 | Active |
| WAP-ANIA-EXP-2026-0033 | RAWABI; Z-APR-21; 2026-10-04 → 10-10; 06:00–18:00; crew 6 (Mahmoud supervisor; v1.1: one crew member is named Zaheer Abbas WKR-000019, crane operator — part of the A.1 bulk counts, K-48 unchanged); VEH-0003, VEH-0004 (escort vehicle VEH-0006), VEH-0006; OBS-0004; approved by Khalid | Active |
| WAP-ANIA-EXP-2026-0035 | GULFPAVE; Z-ILS33R; 2026-10-08 → 10-12; 07:00–16:00; crew 5 (Tariq supervisor, Saad Al-Dosari as RAWABI engineer — ancestor-engagement crew, WA-2); VEH-0005 height_limited_to 4.50; OBS-0007; NTM-0014 | Approved — blocker NOTAM_NOT_ISSUED |
| WAP-ANIA-EXP-2026-0029 | GULFPAVE; Z-TWB; 2026-09-20 → 09-30; 23:00–05:00; suspended by OPS-ANIA-EXP-2026-0009, resumed 2026-09-28 23:00 local after FOD check | Closed 2026-10-01 |
| OPS-ANIA-EXP-2026-0009 | lvp (dust reducing visibility); zones Z-TWB, Z-ILS33R; source aocc AOCC-LOG-TEST-221; 2026-09-28T01:10Z → 04:40Z; declared by Khalid | Ended |

### A.6 Gates and devices
G-ANIA-01 Main Construction Gate / البوابة الرئيسية للإنشاءات — site_gate, S-LAND · G-AAP3 Contractor Airside Access Point 3 / نقطة دخول المقاولين للجانب الجوي 3 — airside_precheck, S-AIR → [Z-APR-21, Z-TWB, Z-ILS33R] · G-RBT-01 Tower Site Gate / بوابة موقع البرج — site_gate, S-TWR · G-RBT-TC Tower Crane Zone Entry / مدخل منطقة الرافعة البرجية — zone_entry, Z-TC01. Devices GATE-TAB-01 … GATE-TAB-08 (two per gate).

### A.7 Other seed items
- Offences Sep 2026 ANIA-EXP: 4 (Jomar OFF-01 2026-09-14; three bulk GULFPAVE/RAWABI drivers OFF-07, OFF-08, OFF-09), no OFF-05 (X10).
- Pass returns Sep 2026 ANIA-EXP: 12 due — per X8.
- Ops events Jun–Sep 2026: 6 (4 dust_sandstorm, 1 lvp, 1 thunderstorm_lightning) for history charts.

---

### Change log
- v1.0 (2026-10-06) — first issue; K-38 setting aligned with Phase 1 v1.1 (`induction_register_from`). Phase 1 v1.1 carries: optional `worker_id` on injury case; K-38 source switch (KA-2); new ExpiringItemKind values (§8.2); AI tool T14 and warnings E5–E7.
- v1.1 (2026-10-07) — changes required by Phase 3 (`3-ptw.md` v1.0 §11); behaviour of existing Phase 2 rules and every worked example unchanged: (1) HK-3 subject_type `equipment_tag`; (2) HK-6 clarified — `ptw` context steps, `active_waps` return fields, internal domain events; (3) §3.20 QR kind `PT`, GC-10 extended to `PT` (`ptw_view`), AC64 pattern updated; (4) HK-2 note that PTW hook attach points live in Phase 3; (5) Appendix A seed: OBS-RBT-52-2026-0001 for TC-01 (§10 Q8 provisionally answered) and Zaheer Abbas named on WAP-ANIA-EXP-2026-0033.
- v1.2 (2026-10-08) — changes required by Phase 4 (`4-third-party-cert.md` v1.0 §11.3); behaviour of existing Phase 2 rules on the Phase 2 seed and every worked example unchanged: (1) HK-3 optional `context` and result fields `hard_stop`, `conditions[]`, `swl_t`; (2) HK-4 effective policy per (project, kind, code) from the Phase 4 hook policy state, transition stage with `HOOK_NOT_MET_WARN`; ZP-3 clarified; (3) §3.20 QR kind `EQ`, AC64 pattern; (4) GC-6 equipment DENY codes and WARN codes `HOOK_NOT_MET_WARN`, `ARRIVAL_INSPECTION_DUE`, `ALSO_SCAN_VEHICLE_STICKER`; (5) GC-12 gate-log subject `equipment_deployment` (excluded from K-52/K-53); (6) HK-2 seeded defaults PLANT-TPI and BANKSMAN; (7) §3.15 optional `equipment_item_id`; (8) X3 note on the Phase 4 seed; (9) §10 Q10 answered for Phase 4 kinds.
