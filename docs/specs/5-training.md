# Module Spec — Phase 5: Training Certificates (catalogue, matrix, sessions, records, gaps, hooks)

**Version:** v1.3 · **Date:** 2026-10-09 · **Author:** HSE Consultant Agent · **Status:** Draft for HSE Manager review
**Builds on:** `0-foundation.md` v1.0 (projects/sites/zones, contractors & engagement tree, rule 28, rule 35 audit, rule 45 Arabic normalisation, rule 48 stable codes, matrix rows 1–19, PDPL P1–P13) · `1-dashboard.md` v1.3 (daily return field `training_hours`, **K-37 training hours per worker**, K-38 source-switch pattern `induction_register_from`, rounding K-R8, warnings E1–E11, expiring-items endpoint, action panel, AI tools T1–T16, import-batch pattern §3.2, list T trades, matrix rows 20–45) · `2-access-permits.md` v1.2 (worker register and deployments, blind index and masking WK-4/WK-5, induction courses and records §3.3–§3.4 and **HK-7** "Phase 5 may read induction records", zone access profiles, **hook interface HK-1…HK-8** with `training_course` attach points on zone profiles, pass categories and ADP categories, QR tokens §3.20, gate check GC-x, matrix rows 46–81, K-48/K-49, P2-x) · `3-ptw.md` v1.1 (crew roles list CR, appointments §3.4, **HK3-1…HK3-5** with `training_course` codes FIRE-WATCH, CSE-ENTRANT, CSE-ATTENDANT, CSE-RESCUE, WAH, LOTO, ELEC-QUALIFIED, GAS-TEST, PTW-ISSUER, PTW-RECEIVER, LOTO-AUTHORITY, PT-8 evaluation times, matrix rows 82–104) · `4-third-party-cert.md` v1.0 (**boundary BD-1…BD-7**, hook policy state §3.14 and **warn → block mechanism §4.8, HK4-3…HK4-7**, verification pattern VF-x, ID match PC-3, imports IM-x, matrix rows 105–124, KPIs K-72…K-81, warnings E10–E11, AI tool T16) · `docs/DECISIONS.md` #1–#79.
**Covers (build order):** 5.1 Course catalogue and induction links · 5.2 Training providers and accreditations · 5.3 Trainer authorisations · 5.4 Training matrix and worker training profiles · 5.5 Sessions: scheduling, nomination, attendance, assessment, close-out · 5.6 Training records and certificates (session-issued, external, QR verification) · 5.7 Competency gaps and refresher planning · 5.8 Hook provider for `training_course` and the warn → block switch · 5.9 Training hours and the K-37 source switch · 5.10 Imports (CSV/Excel, dry-run) · 5.11 KPIs, alerts, dashboard and AI.
**Not in Phase 5:** delivery and records of site/airside/zone inductions (Phase 2 IN rules; Phase 5 only links to them, read-only, HK-7) · third-party personnel certification (Phase 4 PCT types, BD-1…BD-7) · PTW appointments (Phase 3 §3.4) · toolbox talks (Phase 6 — the matrix does not need them, §5.4 MX-12) · emergency-team coverage ratios and drills, medical fitness, WBGT heat-stress regimes (Phase 6).

Conventions: `VERIFY` = clause/number to confirm against the current official text or the client's procedure. `ASSUMPTION` = Consultant default; the HSE Manager may override (§10). "Must" = enforced server-side. Rule prefixes: CC catalogue, PV provider, TA trainer, MX matrix, SS session, AT attendance & assessment, TR record, VR verification, GP gap & refresher, HK5 hooks, TH training hours, IM5 import, CK5 competence check, TK KPIs/AI, P5- PDPL. Error codes are stable strings (Phase 0 rule 48). Times are local Asia/Riyadh unless marked UTC.

**Important boundary:** a training record proves that a person attended a course and, where the course has one, passed its assessment. It is not a Phase 3 appointment (authority to act in a PTW function) and not a Phase 4 third-party certificate (an accredited body's attestation of competence for a scope). Where a function needs more than one of these, every one is required (Phase 4 BD-4, strictest wins). Training never replaces supervision, the Phase 2 induction, the PTW briefing (Phase 3 SH-4) or the JSA.

---

## 1. Purpose

On a KSA mega-project most serious incidents have "training/competence" somewhere in the root cause (ICAM OF-01, TE-08), yet the HSE Manager cannot answer simple questions: who on Pier B today has valid working-at-height training, which confined-space standby persons were never trained, how many first-aid cards expire before the heat season, whether the "first aid certificate" a subcontractor uploaded is genuine, and how many training hours per worker the project really delivered. Records live in contractor spreadsheets and photocopies, refreshers are missed, the same hours are counted twice (once in the daily return, once in the training log), and the gates and permits of Phases 2 and 3 can only show "Training check available from Phase 5". Phase 5 gives one org-wide course catalogue with validity and refresher rules, registers internal and external training providers with their accreditations and the trainers allowed to teach, sets a per-project training matrix by trade, role, zone and credential, schedules sessions and records attendance and assessment, issues QR-verifiable certificates, verifies external certificates with their issuer, computes competency gaps per worker and contractor, plans refreshers, alerts before expiry, and implements the `training_course` hook provider so that gates, work-area permits and permits to work stop people without the training they need — using the same warn → block transition as Phase 4. It also becomes the single source of training hours for the Phase 1 leading indicator K-37 and feeds new KPIs K-82…K-88, warnings E12–E13 and the AI layer.

## 2. Regulatory basis

| # | Source | What it drives here |
|---|---|---|
| R1 | **ISO 45001:2018** cl. 7.2 (determine competence, ensure it on the basis of education, training or experience, retain documented information as evidence), 7.3 (awareness), 7.4 (communication — language), 8.1.4 (contractors), 9.1 (monitoring); **ILO-OSH 2001** 3.4 (competence and training) | Catalogue, matrix, documented evidence, contractor gaps, language rule AT-6, KPIs |
| R2 | **MHRSD Labour Law** and **OSH Regulations / Ministerial decisions** — employer duty to inform and train workers on the hazards of their work and the protective measures before they start, and to keep records `VERIFY` article and decision numbers | Training before exposure (MX-5 due dates 0 for hook codes), record keeping, retention |
| R3 | **NCOSH** regulations and guidance on OSH training and competence `VERIFY` current documents | Same, KSA benchmark |
| R4 | **OSHA 29 CFR 1926.21(b)(2)** (instruct each employee in recognition and avoidance of unsafe conditions), **1926.503** (fall-protection training for each employee who might be exposed to fall hazards, written certification record, retraining when knowledge is inadequate), **1926.454** (scaffold users and erectors trained by a qualified person), **1910.146(g)** and **(k)** (confined-space entrant, attendant and supervisor training; rescue-team practice at least every 12 months; at least one rescue-team member with current first aid and CPR), **1910.147(c)(7)** (LOTO training and retraining) — international benchmark `VERIFY` paragraph letters against the current CFR | WAH, SCAFF-AWR, CSE-*, LOTO courses; CSE-RESCUE 12-month validity; rescue first aid (§11.3); WAH for every person on a WAH section (§11.3) |
| R5 | **NFPA 51B** (fire watch trained in the use of fire-extinguishing equipment and alarm; 2019 ed.), **NFPA 10**, **NFPA 70E** (2024) 110.6 (qualified-person training, retraining at intervals not exceeding 3 years, emergency-response training) `VERIFY` edition and paragraph; **Saudi Civil Defense** fire-safety and fire-warden requirements, **SBC 801** `VERIFY` | FIRE-WATCH, FIRE-WARDEN, LOTO, ELEC-QUALIFIED |
| R6 | **ICAO Annex 17** (security awareness training for persons with access to security restricted areas, recurrent training) and the **GACA National Civil Aviation Security Programme / national AVSEC training programme**, plus the airport operator's ID-pass rules `VERIFY` names, recurrence interval and approved-centre list | AVSEC-AWR (hooked by Phase 2 zone profiles and pass categories), provider accreditation `gaca_avsec` |
| R7 | **ICAO Doc 9137** Part 8 (airside driver training), **Doc 9870** (runway-incursion prevention — driver training, radiotelephony for manoeuvring-area drivers) `VERIFY` | AIRSIDE-DRV (hooked by Phase 2 ADP categories), AIRSIDE-RTF (optional, §10 Q6) |
| R8 | **Saudi Red Crescent Authority (SRCA)** approved first-aid training `VERIFY`; **AHA BLS / ERC** course rules (2-year cards) `VERIFY` | FIRST-AID validity 24 months, accreditation `srca` / `aha` / `erc` |
| R9 | **ANSI/ASSP Z390.1** (H₂S training, annual refresher) `VERIFY`; client H₂S requirements (e.g. Saudi Aramco CSM) where flowed down `VERIFY` | H2S-AWR 12 months |
| R10 | **Saudi Aramco CSM** training chapters and client contractor-training matrices, where flowed down by the client `VERIFY` chapter numbers and whether they apply | Matrix defaults, stricter client validity via settings (shorten only) |
| R11 | Awarding-body rules: **NEBOSH** (IGC, ICC, International Diploma — no expiry), **IOSH Managing Safely** (refresher recommended every 3 years `VERIFY`), **OSHA Outreach Training Program** 30-hour construction card (issued through OTI Education Centers; no expiry; voluntary) `VERIFY` | Professional qualifications for HSE staff and supervisors, verification channels |
| R12 | **TVTC** (Technical and Vocational Training Corporation) licensing of private training centres in KSA `VERIFY` | Provider accreditation `tvtc` (recorded; not required by default) |
| R13 | **PDPL** + Implementing Regulations (Phase 0 R1/R2) | Training records, certificate scans (show ID numbers and photos), assessment scores, suspected-forgery data (§5.14) |
| R14 | MHRSD **midday outdoor work ban** and heat-stress guidance `VERIFY` annual decision | HEAT-AWR before the heat season (GP-6) |

Strictest-wins applied in this spec (and why):
- **Validity:** effective valid_until = the earliest of the printed expiry, completion date + catalogue validity, and completion date + the project's override (settings only shorten, §3.16). An external first-aid card printed for 3 years is valid for 24 months here (R8 over UK-style 3-year cards).
- **No carry-over and no grace:** a renewal's validity runs from its own completion date (as Phase 2 IN-8), and a record is not in force on the day after valid_until.
- **Refreshers:** a short refresher course renews a qualification only while the previous record is still in force (`refresher_max_lapse_days` = 0); once lapsed, the full course is needed.
- **Confined-space rescue 12 months** (OSHA 1910.146(k)(2)(iv)) over the 24 months often used for entrant courses; **LOTO and FIRE-WATCH are critical codes** (7-day transition) because their absence kills.
- **WAH for every crew member on a work-at-height section**, not only arrest users (OSHA 1926.503(a)(1)) — requested from Phase 3 in §11.3.
- **Language:** a high-risk course delivered in a language the worker does not understand, without an interpreter, cannot be passed (AT-6; ISO 45001 7.4). Phase 2 inductions only warn; training is stricter because it authorises high-risk tasks.
- **External certificates count only after verification with the issuer** (VR-1), as Phase 4 VF-1.
- **Positive knowledge of a problem blocks in every hook stage:** a revoked record, a failed verification, an HSE-suspended record, a voided session or a blacklisted provider (HK5-3). The `transition` stage only tolerates missing or not-yet-uploaded training.

## 3. Entities & fields

PDPL column: **none / personal / sensitive** (Phase 0 P1–P2). Every entity carries Phase 0 system fields (id UUID, created_at/by, updated_at/by), is audited (Phase 0 rule 35) and stores `seed_fake` (bool). The AR label is shown in the UI.

### 3.1 Training course (org-wide catalogue) — الدورة التدريبية

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| code | رمز الدورة | string(20) | Y | `^[A-Z0-9-]{2,20}$`, unique org-wide, immutable; must not exist in Phase 4 list PCT (`CODE_IN_OTHER_CATALOGUE`, BD-3) | CSE-ATTENDANT | none |
| name_en / name_ar | الاسم | string(150) ×2 | Y / Y | name_ar Arabic script | Confined space attendant (standby) / المناوب عند الأماكن المحصورة | none |
| category | الفئة | enum | Y | list CAT-C (§3.15) | high_risk_task | none |
| induction_link | ربط بالتعريف (المرحلة 2) | {induction_type, project_course_codes{project → code}} | cond. | required iff category = induction_link; induction_type ∈ Phase 2 §3.3 types; codes must exist in that project's Phase 2 courses | {general_site, —} | none |
| validity_months | مدة الصلاحية (أشهر) | int / null | cond. | 1–60; null = no expiry (only for category professional_qualification); ignored for induction_link (Phase 2 validity applies) | 24 | none |
| min_duration_hours | الحد الأدنى للمدة (ساعات) | decimal(5,2) | Y | 0.50–400.00; not used for induction_link | 8.00 | none |
| max_class_size | الحد الأقصى للمتدربين | int | Y | 1–60 | 12 | none |
| delivery_modes | طرق التقديم | enum[] | Y | ⊆ {`classroom` حضوري, `practical` عملي, `blended` مدمج, `e_learning` تعلم إلكتروني}; e_learning alone is not allowed when practical_required = true (CC-5) | [classroom, practical] | none |
| theory_required / pass_mark_pct | اختبار نظري / درجة النجاح | bool / int | Y / cond. | pass mark 50–100; effective mark = max(course, setting `training_pass_mark_pct`) | true / 80 | none |
| practical_required | تقييم عملي | bool | Y | — | true | none |
| prerequisite_codes | المتطلبات المسبقة | code[] | N | active catalogue codes; no cycles (`PREREQUISITE_CYCLE`) | [CSE-ENTRANT, FIRST-AID] | none |
| satisfies | تغطي أيضاً | code[] | N | codes that an in-force record of this course also satisfies (CC-6) | [CSE-ENTRANT, CSE-ATTENDANT] | none |
| renewal_course_code | دورة التجديد (التنشيطية) | code | N | a course whose `satisfies` contains this code and whose `renews_only` = true | FIRST-AID-R | none |
| renews_only | دورة تنشيطية فقط | bool | Y | true → a record counts only as a renewal (TR-11) | false | none |
| provider_rule | شروط الجهة المقدِّمة | {internal_allowed bool, contractor_delivery_allowed bool, accreditation_bodies_required ACB[]} | Y | non-empty accreditation list ⇒ internal_allowed = false (CC-4) | {true, false, []} | none |
| languages_offered | لغات التقديم | enum[] | Y | ≥ 1 of Phase 2 §3.1 primary_language values | [ar, en, ur, hi, bn, ne, tl, ml] | none |
| hook_code | مستخدمة كمتطلب في البوابات/التصاريح | bool | sys | true when any Phase 2/3 attach point uses the code (§5.8 HK5-2) | true | none |
| active | فعالة | bool | Y | inactive codes cannot get new sessions or records; existing records stay | true | none |

Project overrides of validity (shorten only) and of the pass mark (raise only) are project settings (§3.16), not course fields.

### 3.2 Training provider (org-wide) — الجهة المقدِّمة للتدريب

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| provider_code | رمز الجهة | string(12) | Y | `^[A-Z0-9-]{2,12}$`, unique among providers, immutable | HAYAT | none |
| legal_name_en / legal_name_ar | الاسم القانوني | string(200) ×2 | Y / Y | unique after Phase 0 rule 45 normalisation | Al-Hayat Lifesaving Training Centre (test) / مركز الحياة للتدريب على الإسعاف (تجريبي) | none |
| kind | نوع الجهة | enum | Y | `internal` تدريب داخلي (the client/PMC HSE team), `contractor_internal` وحدة تدريب لدى مقاول, `external` جهة تدريب خارجية | external | none |
| contractor_id | المقاول | FK | cond. | required iff kind = contractor_internal; Phase 0 contractor | — | none |
| country / cr_number / foreign_reg_no | الدولة / السجل التجاري | ISO alpha-2 / string | cond. | external: as Phase 4 §3.1 (CR iff SA) | SA / 1010000201 | none |
| verification_portal_url / verification_domains / verification_email / verification_phone | قنوات التحقق | url / string[] / email / E.164 | cond. | external: ≥ 1 domain; portal host and email domain ∈ domains (as Phase 4 §3.1) | https://verify.hayat-test.example | none |
| contact_name / contact_mobile | جهة الاتصال | string / E.164 | N | — | Mona Al-Saeed (fake) | personal |
| status | الحالة | enum | Y | §4.1 | approved | none |
| status_reason | سبب الحالة | text(500) | cond. | required for suspended / blacklisted; P3 hint | — | none |
| blacklist_scope / blacklist_from | نطاق الحظر / من تاريخ | enum / date | cond. | as Phase 4 §3.1: `all_records`, `issued_from` | — | none |

**Provider accreditation** — اعتماد الجهة: provider_id; accreditation_body (list ACB, §3.15); accreditation_no (string 40, unique per body); scope_course_codes (code[] ≥ 1); valid_from / valid_until (until > from); certificate_file (PDF ≤ 10 MB); register_checked_at / register_checked_by (required to count, PV-2). PDPL: none (checker: personal).

### 3.3 Trainer authorisation (per project) — تفويض المدرب

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| authorisation_no | رقم التفويض | string | sys | `TA-<project>-<nnnn>` | TA-ANIA-EXP-0003 | none |
| trainer_user_id / trainer_worker_id | المدرب | FK / FK | one Y | a platform user or a Phase 2 worker | Salem Al-Harthi (WKR-000018) | personal |
| provider_id | الجهة | FK | Y | kind internal or contractor_internal (external trainers are named on the session, TA-5) | INT-HSE | none |
| course_codes | الدورات | code[] | Y | ≥ 1 active codes allowed for the provider (PV-3) | [HEAT-AWR, H2S-AWR, CSE-ENTRANT, CSE-ATTENDANT, GAS-TEST] | personal |
| roles | الدور | enum[] | Y | ⊆ {`trainer` مدرب, `assessor` مقيِّم} | [trainer, assessor] | personal |
| basis | أساس التفويض | text(500) | Y | ≥ 20 chars; P3 hint (no ID or medical details) | Train-the-trainer course TTT-TEST-0042; NEBOSH ICC; 6 years CSE supervision | personal |
| evidence_files | المستندات | file[] (PDF ≤ 10 MB) | cond. | ≥ 1 when any course is category high_risk_task, ptw_role or emergency_response | — | personal |
| valid_from / valid_to | من / إلى | date | Y | valid_to ≤ valid_from + `trainer_authorisation_max_months` − 1 day | 2026-04-01 / 2027-03-31 | personal |
| authorised_by | المفوِّض | FK | sys | capability 131; ≠ the trainer (`SOD_CONFLICT`) | Noura | personal |
| status | الحالة | enum | Y | `active` ساري, `suspended` موقوف, `withdrawn` مسحوب, `expired` منتهٍ (job) | active | personal |

### 3.4 Training matrix line (per project, versioned) — بند مصفوفة التدريب

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| line_no | رقم البند | string | sys | `MXL-<project>-<nnn>` | MXL-ANIA-EXP-003 | none |
| applies_to_kind | ينطبق على | enum | Y | `all_workers` كل العمال, `trade` المهنة, `matrix_role` دور إضافي, `zone` منطقة عمل, `pass_category` فئة تصريح المطار, `adp_category` فئة تصريح القيادة, `crew_role` دور في طاقم التصريح, `appointment_function` تعيين في التصاريح | trade | none |
| applies_to_values | القيم | string[] | cond. | not for all_workers; trade ⊆ Phase 1 list T (+ project additions); matrix_role ⊆ list MR; zone ⊆ project zones; pass_category ⊆ AP-CAT; adp_category ⊆ {apron, manoeuvring, airside_roads}; crew_role ⊆ Phase 3 CR; appointment_function ⊆ Phase 3 §3.4 functions | [scaffolder, steel_erector, rigger] | none |
| requirement | المتطلب | {course_code} or {any_of: code[] (2–6)} | Y | active codes; any_of only for categories professional_qualification and awareness (MX-3) | {course_code: WAH} | none |
| level | المستوى | enum | Y | `mandatory` إلزامي, `recommended` موصى به | mandatory | none |
| due_within_days | المهلة بعد التعبئة (أيام) | int | Y | 0 … `matrix_line_max_due_days`; must be 0 when the code (or a code it satisfies) is a hook code on the project (`DUE_DAYS_NOT_ALLOWED`) | 0 | none |
| source | المصدر | enum | sys | `manual` يدوي, `hook` مشتق من متطلبات المراحل 2/3 (read-only, MX-2) | manual | none |
| kpi_counted | يحتسب في المؤشرات | bool | sys | false for crew_role and appointment_function lines (enforcement-only, MX-2) | true | none |
| effective_from / effective_to | ساري من / إلى | date / date | sys / N | effective_from = save date (no back-dating); a change closes the old version and opens a new one (MX-7) | 2026-09-01 | none |
| reason | السبب | text(300) | cond. | required when a mandatory line is removed or downgraded (MX-8) | — | none |

### 3.5 Worker training profile (per deployment) — الملف التدريبي للعامل

Phase 5 table keyed by the Phase 2 deployment; Phase 2 tables are not changed.

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| deployment_id | التعيين | FK | Y | unique; Phase 2 deployment | WKR-000021 @ ANIA-EXP | personal |
| matrix_roles | الأدوار الإضافية | MR code[] | N | list MR (§3.15) | [first_aider] | personal |
| work_zone_ids | مناطق العمل | FK[] | N | zones of the deployment's site_ids (`ZONE_NOT_IN_DEPLOYMENT_SITES`) | [Z-MSCP] | personal |
| history | السجل | list {field, value, from_date, to_date, by} | sys | every change opens a new row dated today; no back-dating (MX-9) | — | personal |

### 3.6 Training session — الجلسة التدريبية

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| session_no | رقم الجلسة | string | sys | `TRS-<project>-<yyyy>-<nnnnn>` | TRS-ANIA-EXP-2026-00057 | none |
| project_id / course_code | المشروع / الدورة | FK / code | Y | course active and not induction_link (`INDUCTION_OWNED_BY_PHASE2`) | ANIA-EXP / CSE-ATTENDANT | none |
| provider_id | الجهة المقدِّمة | FK | Y | acceptable on every session day (PV-3) | INT-HSE | none |
| delivery_mode | طريقة التقديم | enum | Y | ∈ course.delivery_modes | blended | none |
| trainers | المدربون | list {user_id \| worker_id \| external_name (string 120), role ∈ trainer/assessor} | Y | ≥ 1 trainer; practical_required ⇒ ≥ 1 assessor (may be the trainer); TA-2/TA-5 | [{Salem, trainer+assessor}] | personal |
| location | المكان | {site_id, zone_id} or offsite_text (200) | Y | site/zone of the project | S-LAND / training room T3 | none |
| language / interpreter_languages | لغة التقديم / لغات الترجمة | enum / enum[] | Y / N | language ∈ course.languages_offered | en / [bn, hi] | none |
| days | أيام الجلسة | list {date, start_time, end_time, break_minutes} | Y | 1–15 days; end > start; net minutes per day ≤ `session_day_max_net_hours` × 60; Σ net ≥ course min (SS-2) | [{2026-10-07, 07:00, 16:00, 60}] | none |
| capacity | السعة | int | Y | ≤ course.max_class_size | 10 | none |
| status | الحالة | enum | Y | §4.4 | scheduled | none |
| attendance_sheet | كشف الحضور الموقّع | file (PDF/JPG ≤ 10 MB) | cond. | required at Close unless every attendee signed on the device (SS-8) | — | personal |
| closed_by / closed_at | أغلقها / وقت الإغلاق | FK / timestamptz | sys | capability 135; ≠ any trainer or assessor of the session (SS-8) | Faisal | personal |
| void | الإلغاء بعد الإغلاق | {reason_code (list SV), reason_text ≥ 20, by, at} | N | HSE Manager only (SS-9) | — | personal (user) |

### 3.7 Nomination and attendance — الترشيح والحضور

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| session_id / worker_id | الجلسة / العامل | FK / FK | Y | unique pair; SS-6 | TRS-…-00057 / WKR-000017 | personal |
| nominated_by / nominated_at | رشّحه / وقت الترشيح | FK / timestamptz | sys | capability 133 | Ahmed | personal |
| status | حالة الحضور | enum | Y | `nominated` مرشح, `attended` حضر, `partial` حضور جزئي, `absent` غائب, `withdrawn` منسحب | attended | personal |
| minutes_by_day | دقائق الحضور لكل يوم | map day_no → int | cond. | 0 … that day's net minutes; required for attended/partial | {1: 480} | personal |
| understood_language | لغة مفهومة | enum | sys | `session_language`, `interpreter`, `none` — from worker.primary_language vs session language/interpreters (AT-6) | interpreter | personal |
| theory_score_pct | درجة الاختبار النظري | decimal(5,2) | cond. | required iff course.theory_required and attendance complete; 0–100 | 85.00 | personal |
| practical_result | نتيجة التقييم العملي | enum | cond. | `pass` / `fail`; required iff practical_required | pass | personal |
| attempt_no | رقم المحاولة | int | sys | 1 + earlier attempts of the same course in 30 days (AT-5) | 1 | personal |
| result | النتيجة | enum | sys | `passed` ناجح, `failed` راسب, `incomplete` غير مكتمل, `pending` قيد الانتظار (AT-1…AT-4) | passed | personal |
| signature | التوقيع | drawn image | cond. | on-device signature, or covered by the session attendance_sheet | — | personal |
| record_id | السجل التدريبي | FK | sys | set at Close for passed attendees | TRR-000812 | personal |

### 3.8 Training record — السجل التدريبي

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| record_no | رقم السجل | string | sys | `TRR-` + 6 digits, org-wide, sequential | TRR-000812 | none |
| worker_id | المتدرب | FK | Y | Phase 2 worker, not Anonymised (TR-1) | WKR-000017 | personal |
| course_code | الدورة | code | Y | active, not induction_link | CSE-ATTENDANT | personal |
| source | المصدر | enum | Y | `session` جلسة على المنصة, `external_certificate` شهادة خارجية, `import` استيراد | session | personal |
| provider_id / session_id | الجهة / الجلسة | FK / FK | Y / cond. | session_id iff source = session | INT-HSE / TRS-…-00057 | personal |
| certificate_no | رقم الشهادة | string(40) | Y | session: system `TRC-<project>-<yyyy>-<nnnnn>`; external: as printed, unique per (provider, course) (TR-5) | TRC-ANIA-EXP-2026-00911 | personal |
| completed_on | تاريخ الإتمام | date | Y | ≤ today; session: last session day | 2026-10-07 | personal |
| printed_expiry | الانتهاء المطبوع | date | N | external only; > completed_on | — | personal |
| valid_until | صالح حتى (فعلياً) | date / null | sys | §6.1 (org default); per-project effective date computed on read (§6.1) | 2028-10-06 | personal |
| limiting_factor | العامل المحدِّد | enum | sys | `printed_expiry` / `course_validity` / `project_override` / `none` (no expiry) | course_validity | personal |
| theory_score_pct / practical_result | الدرجة / التقييم العملي | decimal / enum | N | copied from attendance or as printed | 85.00 / pass | personal |
| hours | الساعات | decimal(6,2) | cond. | external: required when project_sponsored = true; ≤ 16 × days between start and completion ASSUMPTION; session: Σ attended minutes ÷ 60 | 8.00 | personal |
| project_sponsored / sponsoring_project_id | تدريب برعاية المشروع | bool / FK | Y / cond. | external only; true ⇒ project where the worker was Mobilised on completed_on (TH-3) | false | personal |
| name_as_printed | الاسم كما في الشهادة | string(120) | cond. | external: required; compared as Phase 4 PC-4 | Biju Thomas | personal |
| id_entered_for_match / id_match_result | رقم الهوية للمطابقة / نتيجة المطابقة | transient / enum | cond. / sys | as Phase 4 PC-3: never stored; result `matched` / `matched_previous_id` / `not_shown` | — / not_shown | sensitive (transient) / personal |
| scan_file | نسخة الشهادة | file (pdf/jpg/png ≤ 5 MB) | cond. | external: required to Submit; encrypted personal bucket (P5-3) | — | **sensitive** (may show ID and photo) |
| provider_verification_url | رابط التحقق لدى الجهة | url | N | from the provider's QR; VR-4 domain check | — | personal |
| qr_token | رمز QR | string | sys | session records: kind `TR` (§5.6 TR-14) | HSE2:TR:… | none (opaque) |
| status | الحالة | enum | Y | §4.6 | accepted | personal |
| verification_status | حالة التحقق | enum | sys | `verified` (session records at creation), `not_verified`, `failed`, `unable_to_verify` (§4.6) | verified | personal (failed: **sensitive**) |
| submitted_by / reviewed_by / reviewed_at | مقدم السجل / المراجع | FK / FK / timestamptz | sys | reviewer ≠ submitter (TR-7) | Ahmed / Noura | personal |
| historic | سجل تاريخي فقط | bool | sys | true when added under TR-3 (already expired); never in force | false | none |

### 3.9 Training verification record — سجل التحقق من الشهادة التدريبية

Same fields as Phase 4 §3.10 with cert_kind = `training` and method list: `provider_portal` بوابة الجهة, `provider_qr_url` رابط QR للجهة, `provider_email` بريد الجهة, `provider_phone` هاتف الجهة, `provider_register_file` سجل مرسل من الجهة, `awarding_body_portal` بوابة جهة المنح (NEBOSH, IOSH, OSHA OTI Education Center, SRCA — channel = the awarding body's registered domain on the accreditation body list ACB), `original_sighted` معاينة الأصل (recorded, does not verify). Outcomes: `confirmed`, `not_found`, `details_differ`, `revoked_by_provider`, `no_response`. performed_by: capability 138, ≠ submitter, not employed by the holder's employer (`SOD_CONFLICT`). PDPL: outcome not_found / details_differ is **sensitive** (suspected forgery).

### 3.10 Requirement status (derived, per deployment × matrix line) — حالة المتطلب

Not stored as a table of truth: computed on read for any as_of from the matrix versions, the training-profile history, deployments and records (§6.2). A daily snapshot (`training_daily`) is kept only for the action panel and alerts.

| Field | AR label | Type | Example |
|---|---|---|---|
| deployment_id, line_no, requirement | التعيين، البند، المتطلب | — | WKR-000017 @ ANIA-EXP, MXL-ANIA-EXP-E05 (crew_role standby_person), CSE-ATTENDANT |
| due_date | تاريخ الاستحقاق | date | 2026-09-01 |
| state | الحالة | `met` مستوفى · `expiring` مستوفى وينتهي قريباً (valid_until ≤ as_of + 30) · `due` لم يحن موعده · `gap` فجوة · `exempt` مستثنى (MX-10) | gap |
| satisfied_by | مستوفى بواسطة | record_no or Phase 2 induction_no | — |
| valid_until | صالح حتى | date | — |
| booked_session | جلسة محجوزة | session_no | TRS-ANIA-EXP-2026-00057 |

### 3.11 Requirement exemption — استثناء من متطلب

deployment_id; line_no; reason (text ≥ 30 chars, e.g. "office-based document controller, never accesses scaffolds"); granted_by (capability 129, HSE Officer or Manager); valid_until (≤ 6 months ASSUMPTION); status active/withdrawn/expired. Not allowed for lines whose code is a hook code on the project or for IND-GENERAL (`EXEMPTION_NOT_ALLOWED`). PDPL: personal.

### 3.12 Hook policy state (reused) — حالة سياسة المتطلبات

Phase 4 §3.14 entity, with `kind` extended to `training_course` (§11.4). One row per project for kind training_course: provider_registered_on, critical_block_from, general_block_from, deferral, early_switch, stage. The dates come from the Phase 5 settings `training_hook_*` (§3.16), not from the Phase 4 keys.

### 3.13 Training import batch — دفعة استيراد التدريب

Same fields and lifecycle as Phase 1 §3.2 (file, sha256, size, mode `insert_only`, status validated / committed / discarded / expired after 60 min, counts, per-row report), plus `template` (`training_records` / `session_attendance`), `source` (`contractor_file` / `provider_register_file`), optional `scans_zip` (≤ 200 MB, files named `<certificate_no>.pdf|jpg|png`), `evidence_file` (required for provider_register_file: the provider's email as PDF/EML), `session_id` (session_attendance only). Templates and codes in §5.12. PDPL: the uploaded file is **sensitive** when it contains an ID column (IM5-4).

### 3.14 Refresher plan item (derived) — بند خطة التجديد

Computed daily: worker, course, current record and valid_until, refresher_due_from (§6.7), still required (a mandatory kpi_counted line, or an enforcement line on a non-terminal permit or Active WAP), booked session (if any), state `not_booked` / `booked_in_time` / `booked_late` (the session's last day is after valid_until). Used by GP-3…GP-5, K-88 and the alerts.

### 3.15 Reference lists (seeded EN/AR, codes immutable, HSE Manager edits labels and tightens values)

**CAT-C — course categories:** `induction_link` ربط بتعريف المرحلة 2 · `awareness` توعية · `high_risk_task` مهام عالية الخطورة · `ptw_role` أدوار تصاريح العمل · `emergency_response` الاستجابة للطوارئ · `aviation_security` أمن الطيران · `airside_operations` عمليات الجانب الجوي · `electrical` السلامة الكهربائية · `professional_qualification` مؤهل مهني في السلامة.

**ACB — accreditation / awarding bodies** (`VERIFY` names, registers and URLs): `srca` هيئة الهلال الأحمر السعودي · `aha` جمعية القلب الأمريكية · `erc` المجلس الأوروبي للإنعاش · `gaca_avsec` مركز تدريب أمن طيران معتمد من الهيئة العامة للطيران المدني · `airport_operator` معتمد من مشغل المطار · `nebosh` شريك تعليمي معتمد من NEBOSH · `iosh` مقدم تدريب معتمد من IOSH · `osha_otc` مركز تعليم معهد تدريب OSHA · `tvtc` مرخص من المؤسسة العامة للتدريب التقني والمهني · `client_approved` معتمد من العميل · `other` أخرى.

**MR — matrix roles (designations on the training profile):** `fire_warden` مسؤول إخلاء/حريق · `first_aider` مسعف أولي · `fire_watch` مراقب حريق معيّن (Phase 1 list T has no fire-watch trade; the built seed gives fire watches trade `other`).

**SV — session void reasons:** `trainer_not_competent` المدرب غير مؤهل · `attendance_falsified` تزوير الحضور · `assessment_compromised` الإخلال بالتقييم · `provider_misconduct` مخالفة من الجهة · `other` أخرى.

**CAT — course catalogue (seed, org-wide)** — validity in months (— = no expiry; L = Phase 2 validity); hours = min_duration_hours; T/P = theory (pass mark) / practical; provider: I = internal allowed, C = contractor delivery allowed, ACB = accreditation required; hook = called by Phase 2/3 today (critical per §3.16 marked ★).

| Code | EN / AR | Cat. | Valid. | Hours | T / P | Provider | Prereq · satisfies · renewal | Hook |
|---|---|---|---|---|---|---|---|---|
| IND-GENERAL | General site induction (link) / التعريف العام بالموقع (ربط) | induction_link | L | — | — | Phase 2 | type general_site (any active course, DECISIONS #47) | Phase 2 native (IN-1) |
| IND-AIRSIDE | Airside induction (link) / التعريف بالجانب الجوي (ربط) | induction_link | L | — | — | Phase 2 | type airside | Phase 2 native |
| IND-ZONE-ILS | ILS critical-area briefing (link) / إحاطة المنطقة الحرجة لنظام ILS (ربط) | induction_link | L | — | — | Phase 2 | ANIA-EXP course ILS | Phase 2 native |
| IND-ZONE-TC | Tower-crane zone briefing (link) / إحاطة منطقة الرافعة البرجية (ربط) | induction_link | L | — | — | Phase 2 | RBT-52 course TC | Phase 2 native |
| AVSEC-AWR | Aviation security awareness / التوعية بأمن الطيران | aviation_security | 12 `VERIFY` R6 | 3.00 | T 80 | ACB gaca_avsec | — | Phase 2 zones, pass categories |
| AIRSIDE-DRV | Airside driver training / تدريب القيادة في الجانب الجوي | airside_operations | 24 | 4.00 | T 80 / P | ACB airport_operator | IND-AIRSIDE | Phase 2 ADP categories |
| AIRSIDE-RTF | Radiotelephony for manoeuvring-area drivers / الاتصال اللاسلكي لسائقي منطقة المناورة | airside_operations | 24 | 4.00 | T 80 / P | ACB airport_operator | AIRSIDE-DRV | — (§10 Q6) |
| WAH | Working at height — user, fall arrest and rescue awareness / العمل على ارتفاعات | high_risk_task | 24 ASSUMPTION | 8.00 | T 80 / P | I | — | Phase 3 WAH crew ★ |
| CSE-ENTRANT | Confined space entrant / الداخل إلى الأماكن المحصورة | high_risk_task | 24 | 8.00 | T 80 / P | I | — | Phase 3 entrant ★ |
| CSE-ATTENDANT | Confined space attendant (standby) / المناوب عند الأماكن المحصورة | high_risk_task | 24 | 8.00 | T 80 / P | I | — | Phase 3 standby_person ★ |
| CSE-RESCUE | Confined space rescue team / فريق إنقاذ الأماكن المحصورة | high_risk_task | 12 (R4) | 16.00 | T 80 / P | I | prereq CSE-ENTRANT, FIRST-AID · satisfies CSE-ENTRANT, CSE-ATTENDANT | Phase 3 rescue_lead/member ★ |
| WAH-RESCUE | Rescue from height / الإنقاذ من المرتفعات (v1.2, 6c) | high_risk_task | 24 ASSUMPTION | 8.00 | T 80 / P | I | prereq WAH | 6c height rescue teams |
| GAS-TEST | Gas testing (atmospheric monitoring) / فحص الغازات | ptw_role | 24 | 8.00 | T 80 / P | I | — | Phase 3 gas_tester ★ (plus Phase 4 GAS-TESTER, BD-4) |
| H2S-AWR | H₂S awareness and escape / التوعية بغاز كبريتيد الهيدروجين والهروب | awareness | 12 (R9) | 4.00 | T 80 / P | I | — | — |
| FIRE-WATCH | Fire watch / مراقب الحريق | ptw_role | 24 ASSUMPTION | 4.00 | T 80 / P | I | — | Phase 3 fire_watch ★ |
| FIRE-WARDEN | Fire warden / مسؤول الإخلاء والحريق | emergency_response | 24 | 4.00 | T 80 / P | I | — | — |
| FIRST-AID | First aid, CPR and AED / الإسعافات الأولية والإنعاش القلبي الرئوي | emergency_response | 24 (R8) | 16.00 | T 80 / P | ACB srca, aha or erc | renewal FIRST-AID-R | §11.3 rescue_lead |
| FIRST-AID-R | First aid refresher / تجديد الإسعافات الأولية | emergency_response | 24 | 8.00 | T 80 / P | ACB srca, aha or erc | renews_only · satisfies FIRST-AID | — |
| SCAFF-AWR | Scaffold user awareness / التوعية باستخدام السقالات | awareness | 24 ASSUMPTION | 2.00 | T 80 | I, C | — | — |
| LOTO | Lockout/tagout awareness (affected and authorised worker) / التوعية بالعزل والقفل والوسم | electrical | 36 (R5) | 4.00 | T 80 / P | I | — | Phase 3 electrician on isolation ★ |
| LOTO-AUTHORITY | Isolation authority / مسؤول العزل | ptw_role | 24 | 16.00 | T 80 / P | I | prereq LOTO · satisfies LOTO | Phase 3 isolation_authority ★ |
| ELEC-QUALIFIED | Electrical safety — qualified person (NFPA 70E) / السلامة الكهربائية — الشخص المؤهل | electrical | 36 (R5) | 16.00 | T 80 / P | I | prereq LOTO | Phase 3 electrician on isolation |
| BANKSMAN-AWR | Banksman / traffic-marshal awareness / التوعية بتنظيم حركة المعدات | awareness | 24 | 4.00 | T 80 / P | I, C | — | — (Phase 4 BANKSMAN card is separate, BD-4) |
| HEAT-AWR | Heat stress awareness / التوعية بالإجهاد الحراري | awareness | 12 | 1.50 | T 80 | I, C | — | — |
| PTW-RECEIVER | PTW receiver / مستلم تصريح العمل | ptw_role | 24 | 8.00 | T 80 | I | — | Phase 3 receiver |
| PTW-ISSUER | PTW issuer / مُصدِر تصريح العمل | ptw_role | 24 | 16.00 | T 80 / P | I | satisfies PTW-RECEIVER | Phase 3 issuer |
| NEBOSH-IGC | NEBOSH International General Certificate / الشهادة العامة الدولية من NEBOSH | professional_qualification | — | 80.00 `VERIFY` | external exam | ACB nebosh | — | — |
| NEBOSH-ICC | NEBOSH International Construction Certificate / شهادة البناء الدولية من NEBOSH | professional_qualification | — | 80.00 `VERIFY` | external exam | ACB nebosh | — | — |
| NEBOSH-DIP | NEBOSH International Diploma / الدبلوم الدولي من NEBOSH | professional_qualification | — | 400.00 `VERIFY` | external exam | ACB nebosh | satisfies NEBOSH-IGC | — |
| IOSH-MS | IOSH Managing Safely / إدارة السلامة من IOSH | professional_qualification | 36 `VERIFY` R11 | 24.00 | external exam | ACB iosh | renewal IOSH-MS-R | — |
| IOSH-MS-R | IOSH Managing Safely refresher / تجديد إدارة السلامة من IOSH | professional_qualification | 36 | 7.00 | external | ACB iosh | renews_only · satisfies IOSH-MS | — |
| OSHA-30 | OSHA 30-hour Construction (Outreach) / دورة OSHA الإنشائية 30 ساعة | professional_qualification | — `VERIFY` client cap | 30.00 | external | ACB osha_otc | — | — |

Every code above is disjoint from Phase 4 list PCT (BD-3): e.g. `BANKSMAN-AWR` ≠ `BANKSMAN`, `GAS-TEST` ≠ `GAS-TESTER`, `LOTO-AUTHORITY` ≠ `LOTO-AUTHORISED-CARD`, `CSE-ATTENDANT` ≠ `CSE-STANDBY-CARD`, `SCAFF-AWR` ≠ `SCAFFOLDER`.

### 3.16 Phase 5 project settings (extend Phase 0 §3.9, Phase 1 §3.10, Phase 2 §3.22, Phase 3 §3.17, Phase 4 §3.17; HSE Manager only, audited; "Allowed" is the only range accepted)

| Key | AR label | Type | Default | Allowed |
|---|---|---|---|---|
| training_register_from | بدء احتساب ساعات التدريب من السجل | date / null | null; set when the Phase 5 register goes live on the project (lives in Phase 1 §3.10, §11.2) | ≥ project start; ≤ today; may only move earlier once set ASSUMPTION |
| course_validity_months | مدة صلاحية الدورات للمشروع | map code → int | catalogue | 1 … catalogue value (shorten only); a value for a no-expiry course sets a cap |
| training_pass_mark_pct | درجة النجاح الدنيا | int | 80 | 50–100 (course may only raise) |
| training_max_attempts_30d | أقصى محاولات خلال 30 يوماً | int | 3 ASSUMPTION | 1–5 |
| unverified_training_acceptance_hours | قبول الشهادة الخارجية قبل التحقق (ساعات) | int | **0** ASSUMPTION (§10 Q4) | 0–24; never for critical codes |
| training_verification_due_days | مهلة التحقق | int | 3 | 1–14 |
| session_close_deadline_days | مهلة إغلاق الجلسة | int | 3 | 1–7 |
| session_backdate_max_days | أقصى مدة لتسجيل جلسة سابقة | int | 7 ASSUMPTION | 0–14 |
| session_day_max_net_hours | أقصى ساعات صافية لليوم التدريبي | decimal | 10.00 ASSUMPTION | 4.00–10.00 |
| trainer_authorisation_max_months | أقصى مدة لتفويض المدرب | int | 24 ASSUMPTION | 6–24 |
| refresher_planning_days | بدء التخطيط للتجديد (أيام) | int | 60 | 30–120 |
| refresher_max_lapse_days | أقصى انقطاع لقبول الدورة التنشيطية | int | 0 | 0–30 ASSUMPTION (§10 Q5) |
| matrix_line_max_due_days | أقصى مهلة لبند المصفوفة | int | 90 | 0–180 |
| language_block_categories | الفئات التي تتطلب لغة مفهومة | CAT-C code[] | [high_risk_task, ptw_role, emergency_response, aviation_security, airside_operations] | add only |
| training_hook_transition_days | المرحلة الانتقالية لمتطلبات التدريب (أيام) | int | 30 ASSUMPTION (as Phase 4) | 0–30 |
| training_hook_critical_transition_days | المرحلة الانتقالية للرموز الحرجة | int | 7 ASSUMPTION (as Phase 4) | 0–7 |
| training_hook_critical_codes | الرموز الحرجة للتدريب | code[] | CSE-ENTRANT, CSE-ATTENDANT, CSE-RESCUE, GAS-TEST, FIRE-WATCH, WAH, LOTO, LOTO-AUTHORITY | add only |
| training_matrix_warning_pct | حد إنذار امتثال مصفوفة التدريب | decimal | 98.0 ASSUMPTION | 80.0–100.0 |
| training_scan_retention_years | الاحتفاظ بصور الشهادات بعد انتهائها | int | 2 ASSUMPTION (as Phase 4) | 1–10 |
| alert_schedule_long_days | جدول التنبيهات | int[] | [30, 14, 7, 0] (Phase 0/1/2 convention) | — |

## 4. Workflow / states

Who = capability numbers (§5.15). Every transition is audited with before/after (Phase 0 rule 35). "Job" = scheduler `training_daily` at 00:06:00 Asia/Riyadh (after Phase 4 `cert_daily` 00:05:45) and `training_minute` every 60 s for event-driven recomputation (HK5-8).

### 4.1 Training provider
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Draft | مسودة | 127 | Create |
| Draft → Pending Approval | بانتظار الاعتماد | 127 | kind internal / contractor_internal: always; external: ≥ 1 accreditation with register_checked_at, or no course in its intended scope requires accreditation |
| Pending Approval → Approved | معتمدة | 128 | — |
| Pending Approval → Draft | مسودة | 128 | Returned with comment |
| Approved → Suspended | موقوفة | 128 | Reason; PV-5 |
| Suspended → Approved | معتمدة | 128 | Reason |
| Approved/Suspended → Blacklisted | محظورة | 128 | Reason, blacklist_scope; PV-6; "lift blacklist" → Suspended |

### 4.2 Trainer authorisation
— → Active (131; authoriser ≠ trainer) → Suspended (131, reason) → Active (131) · Active/Suspended → Withdrawn (131, reason; terminal) · Active → Expired (job, today > valid_to; terminal).

### 4.3 Matrix line
Lines are versioned, not stateful: Save creates a version with effective_from = today; Remove sets effective_to = yesterday. Who: 129 for manual lines; manual mandatory lines can be removed or downgraded only by the HSE Manager (MX-8). Hook-derived lines follow their attach points (MX-2).

### 4.4 Training session
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Draft | مسودة | 132 | Create |
| Draft → Scheduled | مجدولة | 132 | SS-1…SS-4 pass; nominees notified |
| Scheduled → Scheduled (rescheduled) | إعادة جدولة | 132 | Days changed before the first day; nominees re-notified; prerequisites re-checked |
| Scheduled → In Progress | جارية | System | First day start_time reached |
| In Progress → Delivered | منفذة | System | Last day end_time reached |
| Draft → Delivered | منفذة | 132 (HSE Officer / Manager only) | Recording a past session: last day ≥ today − `session_backdate_max_days` (SS-5) |
| Delivered → Closed | مغلقة | 135 (≠ trainer/assessor) | SS-8: every nominee has a final status and result; records issued atomically |
| Draft/Scheduled → Cancelled | ملغاة | 132 | Reason; nominations released; terminal |
| Closed → Voided | ملغاة بعد الإغلاق | 145 (HSE Manager) | SS-9: reason (list SV); every record from the session Revoked; terminal |

### 4.5 Nomination / attendance
nominated → withdrawn (133, before the first day) · nominated → attended / partial / absent (134, per day; final after the last day) · result pending → passed / failed / incomplete at Close (AT-1…AT-4).

### 4.6 Training record and verification
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Accepted (verified) | مقبول (متحقق منه) | System | Session Close for a passed attendee (TR-14) |
| — → Draft | مسودة | 137; 141 (import) | External record created |
| Draft → Submitted | مُقدَّم | 137 | Scan attached; TR-1…TR-6 pass |
| Submitted → Draft | مسودة | 138 | Returned with comment (≥ 10 chars) |
| Submitted → Accepted | مقبول | 138 (reviewer ≠ submitter) | Document review; may precede verification (VR-1) |
| Submitted → Rejected | مرفوض | 138; System (verification failed, VR-6) | Reason; terminal |
| Accepted → Superseded | مُستبدل | System | A newer record of the same course (or a renewal course satisfying it) becomes in force (TR-10) |
| Accepted → Suspended | موقوف | 140 | Reason (e.g. assessment under review, conduct during a HiPo event); hard stop (HK5-3) |
| Suspended → Accepted | مقبول | 140 | Reason |
| Accepted/Suspended → Revoked | ملغى | 140; System (VR-6 after acceptance; PV-6 provider blacklisted; SS-9 session voided) | Terminal; hard stop |
| Accepted → Expired | منتهٍ | Job | today > valid_until; terminal |

Verification status (independent): `not_verified` → `verified` (confirmed) · → `failed` (not_found, details_differ, revoked_by_provider) · → `unable_to_verify` (no_response twice ≥ 24 h apart) → `verified` / `failed` on a later attempt. **In force** (ساري) is derived (§6.6).

### 4.7 Hook policy for kind `training_course` (the warn → block switch)
Phase 4 §4.8 applies unchanged with kind training_course:
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| Stage 0 `warn` (no provider; Phase 2 HK-4 `HOOK_NOT_AVAILABLE`) → Stage 1 `transition` | انتقالية | 145 (enable training hooks, HK5-1) | Provider registered; dates per §6.5 |
| Stage 1 → Stage 2 `block` (critical codes) | حظر (الرموز الحرجة) | System at critical_block_from 00:00:30; 145 earlier | Audited, alerted |
| Stage 1 → Stage 2 `block` (all codes) | حظر (كل الرموز) | System at general_block_from 00:00:30; 145 earlier | Audited, alerted |
| Stage 1 general_block_from → later date | تأجيل | 145 | Once, ≤ 30 days, reason ≥ 30 chars; never for critical codes |
| Stage 2 → Stage 1 | — | — | Not allowed (`HOOK_POLICY_LOOSENING`) |

Hard stops (HK5-3) block in every stage.

### 4.8 Import batch
As Phase 1 §4.1/§3.2: Uploaded → Validated (dry-run) → Committed / Discarded; Validated → Expired after 60 min.

## 5. Business rules

### 5.1 Boundary (re-stated from Phase 4 BD, binding on Phase 5)
- BD5-1. Phase 5 owns hook kind `training_course` only; it never reads or writes Phase 4 certificates, Phase 3 appointments or Phase 2 credentials except Phase 2 induction records, read-only, for `induction_link` codes (HK-7).
- BD5-2. A Phase 5 course code must not exist in Phase 4 list PCT and vice versa (`CODE_IN_OTHER_CATALOGUE`, Phase 4 BD-3, checked both ways).
- BD5-3. A training provider is never a TPI: providers and TPIs are separate registers; a training certificate cannot satisfy a `personnel_certificate` hook and a Phase 4 certificate cannot satisfy a `training_course` hook.
- BD5-4. Phase 5 never delivers or records inductions: a session for an `induction_link` course is rejected `INDUCTION_OWNED_BY_PHASE2`; an external record for one is rejected the same way.
- BD5-5. Toolbox talks stay in Phase 6 and in the Phase 1 daily-return fields (K-36); they are not training records and never count as training hours (TH-5).

### 5.2 Course catalogue (CC)
- CC-1. The catalogue is org-wide; only the HSE Manager (capability 126) creates or edits courses. Codes are immutable; a course in use (records, sessions, matrix lines or hook attach points) cannot be deleted, only made inactive.
- CC-2. Edits may only tighten: validity shorter, pass mark higher, min_duration_hours longer, practical_required false → true, accreditation bodies added; anything else is rejected `CATALOGUE_LOOSENING`. A tightening applies to records completed after the edit; existing records keep their computed valid_until, except a validity shortening, which recomputes every record's valid_until with the new value (strictest) and alerts holders whose record now expires within 30 days ASSUMPTION.
- CC-3. Project overrides (`course_validity_months`) shorten only; the per-project effective validity is §6.1.
- CC-4. A course with accreditation_bodies_required cannot allow internal or contractor delivery (`ACCREDITED_PROVIDER_REQUIRED`).
- CC-5. e_learning is allowed only as part of `blended` when practical_required = true; an e_learning-only session of such a course is rejected `PRACTICAL_REQUIRED`.
- CC-6. **Satisfaction:** a requirement for code X is satisfied by an in-force record of X or of any course whose `satisfies` contains X (one level only; no chains ASSUMPTION). `renews_only` courses satisfy their target only under TR-11.
- CC-7. induction_link courses carry no validity, hours or provider; they are satisfied by a Phase 2 induction record in status Valid at the as_of date of the course's induction_type on the project (general_site: any active course of the type, DECISIONS #47; zone_specific: the mapped project course code).

### 5.3 Training providers (PV)
- PV-1. Providers are created and submitted by HSE Officers (127) and approved, suspended or blacklisted by the HSE Manager only (128).
- PV-2. An accreditation counts only when `register_checked_at` is set and the date tested lies within valid_from…valid_until.
- PV-3. **Acceptability** of a provider for a course on a date d (each session day, or an external record's completed_on): (a) status Approved on d (not Draft, Pending, Suspended from a date ≤ d, Blacklisted); (b) if the course has accreditation_bodies_required, a counted accreditation of one of those bodies whose scope contains the course on d; (c) kind internal → course.internal_allowed; kind contractor_internal → course.contractor_delivery_allowed **and** every attendee/holder is a worker of an engagement of that contractor or its descendants on the project (independence, as Phase 4 TP-6). Otherwise 422 `PROVIDER_NOT_ACCEPTABLE` with meta reason ∈ {`PROVIDER_NOT_APPROVED`, `PROVIDER_SUSPENDED`, `PROVIDER_BLACKLISTED`, `ACCREDITATION_INVALID`, `ACCREDITATION_SCOPE`, `INTERNAL_NOT_ALLOWED`, `CONTRACTOR_DELIVERY_NOT_ALLOWED`, `NOT_OWN_TREE`}.
- PV-4. Internal and contractor_internal sessions need authorised trainers (TA-2); external sessions name the provider's trainer as text (TA-5).
- PV-5. **Suspended provider:** sessions with any day ≥ the suspension date and external records completed on or after it are refused; existing records stay in force.
- PV-6. **Blacklisted provider:** scope `all_records` → every record of the provider Revoked (`provider_blacklisted`) at once; scope `issued_from` → those completed on or after blacklist_from. Revocation is a hard stop (HK5-3) within 60 s; the HSE Officer receives the list of affected holders for re-training.
- PV-7. An accreditation that later lapses does not invalidate records completed while it was valid (as Phase 4 TP-7); new records are refused.
- PV-8. Accreditation expiries alert on 30 / 14 / 7 / 0 days (§7).

### 5.4 Trainer authorisations (TA)
- TA-1. An authorisation names one trainer, one internal or contractor_internal provider, the courses and roles (trainer, assessor); authoriser (capability 131) ≠ trainer; validity ≤ `trainer_authorisation_max_months`; evidence required for high-risk, PTW-role and emergency courses.
- TA-2. Every trainer and assessor of an internal or contractor_internal session holds an Active authorisation for the course and role on every session day (`TRAINER_NOT_AUTHORISED`).
- TA-3. A trainer of a course with a validity (not professional_qualification) must hold an in-force record of that course, or of a course that satisfies it, on every session day (`TRAINER_NOT_TRAINED`) — a WAH trainer must hold WAH.
- TA-4. A trainer or assessor cannot be an attendee of the same session (`SOD_CONFLICT`).
- TA-5. External sessions record each trainer's name as printed by the provider (`external_name`); the provider's acceptability (PV-3) is the competence control.
- TA-6. Contractor HSE Reps may hold authorisations only for courses with contractor_delivery_allowed and only under their own contractor_internal provider.

### 5.5 Training matrix (MX)
- MX-1. Each project has one matrix of lines (§3.4); HSE Officers (129) edit manual lines; every version is kept (effective_from / effective_to).
- MX-2. **Hook-derived lines** are created and kept in step automatically from the `training_course` attach points of the project: Phase 2 zone profiles → `zone` lines; Phase 2 pass categories → `pass_category`; Phase 2 ADP categories → `adp_category`; Phase 3 crew roles, permit-type sections and appointment functions → `crew_role` / `appointment_function` lines. Derived lines are read-only (`LINE_DERIVED_FROM_HOOK`), mandatory, due_within_days = 0. `crew_role` and `appointment_function` lines are **enforcement-only** (kpi_counted = false): they appear in a person's competence profile while the person is on a non-terminal permit crew or holds an Active appointment, and are enforced by the hook (HK5); they are not counted in K-82…K-84.
- MX-3. A requirement is one course code, or `any_of` 2–6 codes for categories professional_qualification and awareness only (`ANY_OF_NOT_ALLOWED`).
- MX-4. **Applicability** of a kpi_counted line to a deployment at as_of: deployment Mobilised; and all_workers → always; trade → deployment.trade ∈ values; matrix_role → profile.matrix_roles ∩ values ≠ ∅ at as_of; zone → profile.work_zone_ids ∩ values ≠ ∅ at as_of; pass_category → the worker holds an Active Phase 2 pass of that category on the project; adp_category → an Active ADP of that category on the project. KPI population = contractor_worker deployments only; client_pmc_staff are evaluated and shown, not counted (TK-2).
- MX-5. **Due date** of a requirement = max(deployment.mobilised_on, line.effective_from, the date the line started to apply to the deployment (e.g. role assigned)) + due_within_days. The requirement is `due` (not yet counted) while as_of < due_date and `gap` from due_date if not satisfied (§6.2).
- MX-6. Requirements are de-duplicated per (deployment, course code or any_of set): two lines requiring WAH give one requirement, with the earliest due date.
- MX-7. Lines cannot be back-dated; a change applies from the save date.
- MX-8. Removing a mandatory manual line, downgrading it to recommended, or raising its due_within_days needs the HSE Manager (`MATRIX_LOOSENING` for others) and a reason ≥ 20 chars.
- MX-9. Training profiles (§3.5) are edited by capability 130; a Contractor HSE Rep edits only C-scope deployments; changes apply from today.
- MX-10. **Exemptions** (§3.11) by capability 129 with reason; never for IND-GENERAL or hook codes (`EXEMPTION_NOT_ALLOWED`); an exempt requirement is excluded from the K-82 population while the exemption is active.
- MX-11. Seeded default matrix lines are in Appendix A.4; they are ordinary manual lines once seeded.
- MX-12. Toolbox talks are not a matrix requirement (BD5-5).

### 5.6 Sessions and nominations (SS)
- SS-1. Scheduling requires: course active and not induction_link; provider acceptable on every day (PV-3); trainers per TA-2…TA-5; location on the project; language ∈ course.languages_offered.
- SS-2. Σ net minutes of the days ≥ course.min_duration_hours × 60 (`SESSION_TOO_SHORT`); each day's net minutes ≤ `session_day_max_net_hours` × 60 (`SESSION_DAY_TOO_LONG`).
- SS-3. Nominations ≤ capacity ≤ course.max_class_size (`SESSION_FULL`).
- SS-4. Scheduled days must not start before now (`SESSION_IN_PAST`); past sessions use SS-5.
- SS-5. A past session may be recorded directly as Delivered by an HSE Officer or the HSE Manager when its last day ≥ today − `session_backdate_max_days` (`BACKDATED_SESSION`); its attendance is entered in the same request or before Close.
- SS-6. **Nomination** requires: worker has a Mobilised or Pending Induction deployment on the project; worker not Banned (`WORKER_BANNED`); prerequisites in force on the first session day (`TRAINING_PREREQUISITE`, naming the missing code); no other nomination of the worker in a session whose days overlap (`SCHEDULE_CLASH`); attempts within limits (AT-5); a Contractor HSE Rep nominates only C-scope workers; language check per AT-6 (warning at nomination).
- SS-7. Attendance is recorded per day, only for days ≤ today, by a trainer of the session who is a user, or by capability 134.
- SS-8. **Close** (capability 135, ≠ every trainer and assessor of the session, `SOD_CONFLICT`): every nomination has a final status; every attended/partial attendee has a result; a signed attendance sheet is attached unless every attendee signed on the device; records are issued atomically for passed attendees (TR-14). Not closed by last day + `session_close_deadline_days` → action panel and alert.
- SS-9. **Void** (HSE Manager, capability 145): a Closed session found invalid (list SV) is Voided; every record it issued is Revoked (hard stop, HK5-3) within 60 s; holders and their Contractor HSE Reps are alerted; the session's hours stay in K-86 history with a "voided" flag but are removed from K-37 from the void date onward ASSUMPTION (they were delivered, but did not create competence) — §10 Q11.
- SS-10. Cancelling a Scheduled session notifies nominees and their Contractor HSE Reps; their refresher plan items return to `not_booked`.

### 5.7 Attendance and assessment (AT)
- AT-1. **Attendance complete** = attended minutes on every session day ≥ that day's net minutes × `attendance_min_pct` / 100, with attendance_min_pct = 100 ASSUMPTION (strict: the whole course). Otherwise status `partial` and result `incomplete` (`ATTENDANCE_INSUFFICIENT`), no assessment, no record.
- AT-2. **Theory:** score ≥ max(course.pass_mark_pct, `training_pass_mark_pct`) → pass.
- AT-3. **Practical:** `pass` recorded by an assessor of the session (practical_required courses).
- AT-4. result = `passed` iff attendance complete ∧ (theory not required ∨ theory pass) ∧ (practical not required ∨ practical pass) ∧ AT-6 allows; `failed` if attendance complete and an assessment failed; `incomplete` otherwise.
- AT-5. A worker may attempt the same course at most `training_max_attempts_30d` times in 30 days; a further nomination is rejected `TRAINING_ATTEMPTS_EXCEEDED` until an HSE Officer records a re-training note (as Phase 2 IN-5).
- AT-6. **Language:** understood_language = `session_language` if worker.primary_language = session language, `interpreter` if it is in interpreter_languages, else `none`. For courses whose category is in `language_block_categories`, `none` makes the result `failed` with reason `LANGUAGE_NOT_UNDERSTOOD` regardless of scores; for other categories it is saved with warning `LANGUAGE_MISMATCH` (as Phase 2 IN-6).
- AT-7. Scores and practical results are visible only to capabilities 136 holders who are HSE Manager, HSE Officer, the session's trainers and the worker's Contractor HSE Rep (P5-5).

### 5.8 Training records and certificates (TR)
- TR-1. The holder is a Phase 2 worker, not Anonymised; a Contractor HSE Rep submits external records only for C-scope workers (as Phase 2 WK-11); HSE Officers for any worker with a deployment on their project.
- TR-2. Provider acceptable for the course on completed_on (PV-3), else 422 `PROVIDER_NOT_ACCEPTABLE`.
- TR-3. completed_on ≤ today; a record whose computed valid_until < today is rejected `RECORD_ALREADY_EXPIRED`; capability 138 may attach it as `historic` (never in force).
- TR-4. valid_until per §6.1.
- TR-5. (provider, course, certificate_no) is unique (`CERT_EXISTS`); the same certificate_no presented for another worker blocks Submit (409 `CERT_NO_REUSED`, as Phase 4 DECISIONS #91) and alerts the HSE Officer.
- TR-6. **Identity:** name_as_printed is compared as Phase 4 PC-4 (`NAME_MISMATCH_CONFIRMATION` at Accept when `none`); if the certificate shows an ID number, the submitter types it for a blind-index comparison exactly as Phase 4 PC-3 — never stored; a mismatch is 422 `CERT_ID_MISMATCH` and the attempt is audited with the masked value.
- TR-7. Reviewer ≠ submitter (`SOD_CONFLICT`, 422 per DECISIONS #43); a Contractor HSE Rep cannot accept records.
- TR-8. External records are in force only when verified (VR-1).
- TR-9. Prerequisites: an external record of a course with prerequisites is accepted only if the holder had each prerequisite in force on completed_on, or the certificate itself evidences it (reviewer tick "prerequisite evidenced on certificate") ASSUMPTION (`TRAINING_PREREQUISITE`).
- TR-10. A worker has at most one in-force record per course; a newer record supersedes the older only when it becomes in force (no gap, as Phase 4 PC-9).
- TR-11. **Refreshers:** a record of a `renews_only` course (e.g. FIRST-AID-R) is accepted only if, on its completed_on, the holder had an in-force record of the target course (or of the refresher), or one that ended no more than `refresher_max_lapse_days` before; otherwise 422 `REFRESHER_NOT_ELIGIBLE` ("full course required"). Its valid_until runs from its own completed_on (§6.1).
- TR-12. Records are never deleted; edits to an Accepted record after 24 h only by the HSE Manager with reason (as Phase 2 IN-11).
- TR-13. HSE suspension and revocation (capability 140) need a reason ≥ 20 chars, are hard stops (HK5-3) and alert the Contractor HSE Rep with "Training record not accepted / السجل التدريبي غير مقبول" (no reason, P5-4).
- TR-14. **Session-issued records** are created at Close with source `session`, status Accepted, verification `verified` (method `session_record`), certificate_no `TRC-<project>-<yyyy>-<nnnnn>` and a QR token of kind `TR`. A bilingual (EN/AR) certificate PDF is generated with worker name, worker_no, course, completion date, valid_until, provider, trainer name(s) and the QR — **no ID number, score or photo** (P5-6).
- TR-15. A Phase 2 worker ban or Phase 4 certification ban never changes training records (as Phase 2 HK-8); a banned worker is ineligible through Phase 2 anyway.
- TR-16. Records follow the worker across projects (org-wide); each project applies its own validity override on read (§6.1).

### 5.9 Verification of external records (VR)
- VR-1. An external record is in force only when verification_status = `verified`, except within `unverified_training_acceptance_hours` of Accept (default 0 = never), and never for training_hook_critical_codes (`TRAINING_UNVERIFIED`).
- VR-2. Verifier (capability 138) ≠ submitter and not employed by the holder's employer (`SOD_CONFLICT`).
- VR-3. Verification uses a channel registered on the provider record or on the awarding body (ACB) list; otherwise `CHANNEL_NOT_REGISTERED`. `original_sighted` leaves the record not_verified.
- VR-4. A provider QR URL whose host is not in the provider's verification_domains shows warning `VERIFICATION_URL_FOREIGN_DOMAIN` and cannot be the channel; the server never fetches external URLs (as Phase 4 VF-4).
- VR-5. `no_response` twice ≥ 24 h apart → `unable_to_verify`; HSE Manager alerted; not in force.
- VR-6. `not_found`, `details_differ` or `revoked_by_provider` → `failed`: Submitted → Rejected / Accepted → Revoked (`verification_failed`); hook result hard stop; HSE Manager alerted; action panel lists it for a decision (provider review PV-5/PV-6, Phase 2 worker ban — prompt only, never automatic); raises E13.
- VR-7. Each record is verified on its own; renewals are never "verified by inheritance".
- VR-8. Source `provider_register_file` imports create verification records with method provider_register_file, outcome confirmed, reference = evidence sha256 (IM5-6).

### 5.10 Competency gaps and refresher planning (GP)
- GP-1. The gap register lists, per deployment, every applicable requirement with its state (§3.10); filters: project, contractor tree, trade, course, state, hook code yes/no.
- GP-2. A Contractor HSE Rep sees gaps of C-scope deployments only; Viewer/Client sees counts only (TK-5).
- GP-3. **Refresher plan:** a record enters the plan on refresher_due_from (§6.7) when it still satisfies a mandatory requirement of a Mobilised deployment (kpi_counted line, or an enforcement line while on a non-terminal permit crew / Active WAP / Active appointment).
- GP-4. "Create session from plan" (capability 132) pre-fills nominees (same course, project, language groups) up to the course's max_class_size; nominees still pass SS-6.
- GP-5. **Booking and alerts:** when the holder is nominated to a Scheduled session whose last day ≤ the record's valid_until (`booked_in_time`), the remaining 30- and 14-day expiry alerts for that record are suppressed; the 7- and 0-day alerts are always sent. A booking that ends after valid_until (`booked_late`) suppresses nothing.
- GP-6. **Heat season:** HEAT-AWR records whose valid_until falls inside the coming heat season (Phase 1 setting) enter the refresher plan 60 days before the season starts (v1.1: the plan date = min(valid_until − `refresher_planning_days`, start of the earlier of Phase 1 `heat_season` and 6b `heat_controls_period`, minus 60 days); with the defaults 05-01 − 60 = 03-02), so that refreshers happen before the season ASSUMPTION `VERIFY` R14.
- GP-7. A gap on a hook code for a worker named on a non-terminal permit or an Active WAP crew is listed in the action panel with the permit/WAP number (P5-2 name rules).
- GP-8. Gaps never block a deployment by themselves (as Phase 4 PC-12); access and permits are blocked through hooks (HK5).

### 5.10a Hook provider and the warn → block transition (HK5)
- HK5-1. **Provider registration:** the HSE Manager enables training hooks on a project (capability 145); this requires `training_register_from` set and ≤ today (`TRAINING_REGISTER_NOT_LIVE`) and shows the readiness report first (HK5-9). The provider for kind `training_course` is registered with provider_registered_on = that local date; from then Phase 2 no longer returns `not_evaluated` / `HOOK_NOT_AVAILABLE` for training codes on that project, and the Phase 2 setting `hook_policy.training_course` is superseded by the hook policy state (§3.12, §11.3).
- HK5-2. **Codes implemented** — exactly those called by Phases 2–3 today: AVSEC-AWR, AIRSIDE-DRV (Phase 2); FIRE-WATCH, CSE-ENTRANT, CSE-ATTENDANT, CSE-RESCUE, WAH, LOTO, ELEC-QUALIFIED, GAS-TEST, PTW-ISSUER, PTW-RECEIVER, LOTO-AUTHORITY (Phase 3); plus every other active catalogue code so the HSE Manager may attach it (e.g. FIRST-AID for rescue_lead, §11.3; H2S-AWR on a zone profile); induction_link codes resolve through Phase 2 records (CC-7). Any other code → `unknown_code` (configuration error shown to the HSE Manager; not_met under block).
- HK5-3. **Hard stops** (`not_met`, `hard_stop = true`, block in every stage): no in-force record satisfies the code **and** the holder's latest record of the code (or of a satisfying course) is Revoked, verification failed, HSE-Suspended, from a Voided session, or from a provider blacklisted in scope. Rationale: positive knowledge that the training evidence is false or withdrawn. If another in-force record satisfies the code, the result is met.
- HK5-4. **Stages** (§4.7) as Phase 4 HK4-4: transition — a not_met without hard_stop is returned as `warn` with `HOOK_NOT_MET_WARN` and the detail reason; never blocks; met and expiring pass through. Block — not_met and unknown_code block: Phase 2 `HOOK_NOT_MET` (gate DENIED, eligibility not_met, WAP crew auto-exclusion), Phase 3 blocker `HOOK_NOT_MET` / `KEY_ROLE_INELIGIBLE` and Active permits Suspended `hook_not_met` within 60 s.
- HK5-5. **Switch dates:** critical codes (`training_hook_critical_codes`) block from provider_registered_on + `training_hook_critical_transition_days`; all other codes from provider_registered_on + `training_hook_transition_days`. Automatic switch at 00:00:30 local (actor null), audited and alerted. Early switch of any code or all codes by the HSE Manager at any time (145). One deferral of general_block_from ≤ 30 days with reason ≥ 30 chars; none for critical codes (`CRITICAL_CODE_NO_DEFERRAL`); second deferral `DEFERRAL_USED`; block → warn `HOOK_POLICY_LOOSENING`.
- HK5-6. **Check:** `check(subject_type = worker, subject_id, kind = training_course, code, at, context {project_id, zone_id, permit_id, crew_role, critical})`. Steps: worker exists and not Anonymised → code known → find the best in-force record at local date(at) satisfying the code (CC-6), using the project's effective validity (§6.1) → result. Status: `met` (valid_until > local date(at) + 7 or null), `expiring` (in force and valid_until ≤ local date(at) + 7), `not_met` with reason ∈ {`TRAINING_MISSING`, `TRAINING_EXPIRED`, `TRAINING_PENDING_REVIEW` (Submitted, not Accepted), `TRAINING_UNVERIFIED`, `TRAINING_SUSPENDED`, `TRAINING_REVOKED`, `TRAINING_VERIFICATION_FAILED`, `INDUCTION_NOT_VALID` (link codes)}. Result fields: {status, valid_until, ref (record_no), reason_code, hard_stop, conditions[] (empty in v1.0)}. Subject types `vehicle` and `equipment_tag` → `unknown_code`.
- HK5-7. **Appointment holders:** Phase 3 calls the provider for an appointment's holder through the holder's worker record (worker.user_id link, Phase 2 §3.1). A holder_user_id without a linked worker → not_met `HOLDER_NOT_LINKED` (no hard stop; shown to the HSE Manager as a configuration error) (§11.4).
- HK5-8. **Events:** Phase 5 publishes `training.record_changed` (record created, superseded, expired, suspended, revoked, verification changed), `training.session_voided`, `training.provider_changed`, and `hook_policy.changed` (kind training_course), at least once within 60 s; Phase 2 and Phase 3 re-evaluate affected credentials, WAPs and permits (as HK4-10). Provider results may be cached ≤ 60 s (Phase 2 HK-5); the cache is cleared on these events. The expiry job publishes `training.record_changed` for every record that expired at 00:06.
- HK5-9. **Readiness report** (capability 143), as Phase 4 HK4-7 for kind training_course: per code, subjects requiring it (workers on WAP crews and non-terminal permit crews in roles hooked to it, holders of hooked appointments and credentials, workers with the zone in their profile), number met/expiring, not-met list with reasons, and a preview of the live permits, WAPs and gates the block will affect. Shown before registration and until the last block date; it never prevents the switch.
- HK5-10. **Phase 2 and Phase 3 behaviour is otherwise unchanged:** PT-8 evaluation times, LF-5/HK3-3 "valid_until must cover the shift's planned end", gate verdicts and WAP crew exclusion all use the result above.

### 5.11 Training hours (TH)
- TH-1. **Person-hours of an attendance** on a session day = attended minutes that day ÷ 60, whatever the result (attended, partial; absent = 0). Only sessions in status Closed count; Delivered sessions not yet closed are reported as "n sessions not closed" on the K-37 tile.
- TH-2. **Attribution:** the session day's local date; the contractor = the attendee's deployment engagement on the session's project on that date. Only attendees with person_type `contractor_worker` count in K-37 and K-86; client/PMC staff hours are reported separately (K-86 "staff hours"); visitors never count.
- TH-3. **External records** count only when project_sponsored = true, the record is Accepted and verified, and the worker had a Mobilised contractor_worker deployment on the sponsoring project on completed_on; their `hours` are attributed to completed_on. Records of prior learning (not sponsored, or completed before the worker's mobilisation) and imported historic records never count.
- TH-4. **Inductions are not training hours:** Phase 2 induction time is counted by K-38 (count of inductions), not by K-37 ASSUMPTION (§10 Q2).
- TH-5. Toolbox talks are not training hours (K-36; Phase 6).
- TH-6. **Register switch (no double counting):** for each day d, K-37's numerator uses exactly one source: d ≥ `training_register_from` → register hours (TH-1…TH-3); d < `training_register_from`, or the setting null → the Phase 1 daily-return `training_hours`. The daily-return field stays editable (no Phase 1 validation changes) but is ignored for register days; the import gives warning W07 for it (§11.2).
- TH-7. **Reconciliation note:** when the period contains register days and, for those days, Σ daily-return training_hours > 0 and |register − daily return| > 5 % of the daily-return sum, the K-37 tile shows "Daily returns differ from the training register by x % for register days" (as Phase 1 K-38) ASSUMPTION.
- TH-8. e-learning parts of a blended session count their scheduled net minutes when the attendee completed them (recorded as attendance minutes).
- TH-9. A voided session's hours are excluded from K-37 for any as_of on or after the void date; K-86 keeps them with a "voided" flag and a separate voided-hours figure (SS-9, §10 Q11).

### 5.12 Imports (IM5)
- IM5-1. Two templates (header row EN or AR, order free, case-insensitive), `.csv` (UTF-8, comma or semicolon) or `.xlsx` (first sheet), ≤ 5 MB, ≤ 5,000 rows; dry-run first; commit only a Validated batch ≤ 60 min old (as Phase 1 §3.2).
- IM5-2. **training_records** columns: worker_no **or** (id_type, id_number[, passport_country]) for lookup, course_code, provider_code, certificate_no, completed_on, printed_expiry, theory_score_pct, practical_result, hours, project_sponsored (Y/N), name_as_printed, id_on_card (`same_as_lookup` / blank / number).
- IM5-3. **session_attendance** columns (for one Delivered session, `session_id` on the batch): worker_no, day_no, minutes, theory_score_pct, practical_result. Committed rows update attendance; Close is still a separate step (SS-8).
- IM5-4. Files with an ID column are sensitive: stored encrypted, deleted at commit, discard or expiry; the dry-run masks IDs (WK-4) and shows worker_no (as Phase 4 IM-4).
- IM5-5. Committed training_records rows create records in status Submitted (never Accepted); rows with a scan in scans_zip are attached by certificate_no; rows without a scan stay Draft.
- IM5-6. Source `provider_register_file` (HSE Officer/Manager only): the evidence email must come from one of the provider's verification_domains; committed records get verification records per VR-8 and are still reviewed.
- IM5-7. **Validation codes** (errors block the row; a file-level error blocks the file):

| Code | Level | Condition |
|---|---|---|
| E01 | error | worker not found by worker_no or blind index, or worker Anonymised |
| E02 | error | course_code unknown, inactive, or induction_link (`INDUCTION_OWNED_BY_PHASE2`) |
| E03 | error | provider_code unknown or provider not acceptable on completed_on (PV-3, meta reason) |
| E04 | error | duplicate (provider_code, course_code, certificate_no) within the file or in the DB |
| E05 | error | completed_on in the future, or record already expired (TR-3) |
| E06 | error | theory_score_pct not 0–100; practical_result not pass/fail; hours missing when project_sponsored = Y |
| E07 | error | id_on_card does not match (TR-6) |
| E08 | error | row outside the uploader's scope (C scope / project) |
| E09 | error | renews_only course without an eligible prior record (TR-11) |
| E10 | error | session_attendance: worker not nominated to the session, day_no not a session day, or minutes > that day's net minutes |
| E11 | error | prerequisite not in force on completed_on and not evidenced (TR-9) |
| E12 | error | unparseable date/number; missing required column (whole file rejected) |
| W01 | warning | printed expiry beyond the course validity (valid_until will be shortened) |
| W02 | warning | name_as_printed match `none` or `partial` |
| W03 | warning | no scan in the zip for this certificate_no (row stays Draft) |
| W04 | warning | provider accreditation expires within 30 days |
| W05 | warning | same file_sha256 already committed on this project |
| W06 | warning | record expires within 30 days |

### 5.13 Competence check and QR verification (CK5)
- CK5-1. **QR kind `TR`** (`HSE2:TR:<22-char token>`) on session-issued certificates. A user with capability 142 scanning it sees: course (EN/AR), worker name and worker_no (names only with capability 46, otherwise "Worker"), completed_on, valid_until, status (in force / expired / revoked, colour), provider code — never ID numbers, scores, scans or verification details. Logs `training_qr_view`; records no entry. Rotated or revoked tokens show "REVOKED / ملغاة".
- CK5-2. **Competence mode** of the Phase 2 access card (kind AC): extends Phase 4 VF-9 "certificates mode" with a Training section listing, per applicable requirement, course, in force yes/no with reason, valid_until and gap state; the response contains no ID, scan, score or medical data and writes `cert_check_view` (one audit row for the combined view).
- CK5-3. There is no public (unauthenticated) verification page in v1.0 (PDPL minimisation) ASSUMPTION (§10 Q10).

### 5.13a KPIs and AI (TK)
- TK-1. All training KPIs are computed by the backend (Phase 1 D-1); the frontend only formats.
- TK-2. Population date = as_of end of day (local); population for K-82…K-85 and K-88 = contractor_worker deployments Mobilised at as_of; contractor attribution = the deployment's engagement (filter with descendants per Phase 1 K-R5).
- TK-3. Period attribution: hours → session day / completed_on (TH-2, TH-3); assessments (K-87) → session closed_at local date; failed verifications (E13) → performed_at.
- TK-4. AI tool **T17 `get_training_kpis`** (project_ids, period, filters {site, zone, engagement, include_descendants, trade, course_code, course_category}, metrics [K-37, K-82…K-88], group_by {course, course_category, contractor, trade, provider, source, month}) returns aggregates only; **no names, worker_no, certificate numbers, scores, ID data or verification-failure details** (AI-5). T13 also returns E12–E13. T9 gains dimension `training_gap_at_event` (§11.2).
- TK-5. Viewer/Client sees training KPIs, gap counts and expiring counts as aggregates only.

### 5.14 PDPL (P5-x, extends P1–P13, P1-x, P2-x, P3-x, P4-x)
- P5-1. Classes as in §3. **Sensitive:** external certificate scans (may show ID numbers and photos), transient ID entered for matching, verification records with outcome not_found / details_differ (suspected forgery), import files with ID columns. **Personal:** training records, course, dates, hours, scores, practical results, attendance, signatures, language understood, trainer authorisations and their basis, training profiles, gaps.
- P5-2. Lists, gap registers, alerts and dashboards show worker name only to capability 46 holders; others see worker_no, or "Worker" where Phase 2 DECISIONS #48 applies (Viewer/Client).
- P5-3. Scans live in the encrypted personal bucket (Phase 2 P2-2), are served by signed URLs ≤ 5 min only to capability 139 with a reason (`verification`, `authority_request`, `incident_investigation`, `client_audit`, `other`+text); each opening writes `sensitive_field_read` (fields_read ["training_scan"]); never in bulk exports or AI inputs.
- P5-4. Suspected-forgery details, suspension and revocation reasons are shown only to hse_manager and hse_officer; other roles see "Training record not accepted / السجل التدريبي غير مقبول".
- P5-5. **Purpose limitation and legal exposure — assessment results:** scores and failed attempts are performance data about a person. They are used only to decide whether the training requirement is met — never for HR performance, pay or discipline ASSUMPTION (§10 Q12); visible per AT-7; excluded from exports except for HSE Manager/Officer; never sent to the AI.
- P5-6. Certificates, QR checks, permit prints, gate screens and alerts carry no ID number, score, photo or verification detail (P3-2).
- P5-7. **No second copy of ID numbers** (as Phase 4 P4-2): IDs on certificates are matched through the Phase 2 blind index and never stored.
- P5-8. **Retention:** training records follow the worker (Phase 2 P2-7): on anonymisation, name-linked fields are removed while course, dates, hours and provider are kept for statistics; certificate scans are deleted `training_scan_retention_years` after the record ends (Expired, Superseded, Revoked, Rejected) unless linked to an incident investigation (then Phase 1 P1-5); attendance signatures follow Phase 3 P3-5 (deleted with the worker's anonymisation).
- P5-9. Data-subject access (Phase 0 P8): the HSE Manager can produce a per-worker training report (records, sessions, scores, gaps) through capability 144 with purpose `data_subject_request`.
- P5-10. Phase 1 P1-8 ID scan applies to every Phase 5 free-text field.

### 5.15 Permission matrix — Phase 5 extension (continues Phase 4 §5.15; legend A/P/S/C/C1/R/—)

| # | Capability | HSE Mgr | HSE Officer | Site Eng/Sup | Permit Issuer | Permit Receiver | Contractor HSE Rep | Viewer/Client |
|---|---|---|---|---|---|---|---|---|
| 125 | View course catalogue, providers, matrix, session calendar (no attendee names) | A | P | S | S | C1 | C | P (R) |
| 126 | Create / edit the course catalogue (tighten only, CC-2) | A | — | — | — | — | — | — |
| 127 | Create / edit / submit training providers and accreditations | A | P | — | — | — | — | — |
| 128 | Approve / suspend / blacklist / lift training providers | A | — | — | — | — | — | — |
| 129 | Edit project training matrix (manual lines; loosening HSE Manager only, MX-8); grant exemptions | A | P | — | — | — | — | — |
| 130 | Edit worker training profiles (matrix roles, work zones) | A | P | S | — | — | C | — |
| 131 | Grant / suspend / withdraw trainer authorisations | A | P | — | — | — | — | — |
| 132 | Create / schedule / reschedule / cancel sessions; create session from refresher plan | A | P | — | — | — | C (contractor_internal provider, TA-6) | — |
| 133 | Nominate / withdraw attendees | A | P | S | — | — | C | — |
| 134 | Record attendance and assessment (also any trainer of the session who is a user) | A | P | — | — | — | C (own sessions) | — |
| 135 | Close session and issue records (≠ trainer/assessor, SS-8) | A | P | — | — | — | — | — |
| 136 | View training records, attendance, gaps (names need 46; scores per AT-7) | A | P | S | S | C1 | C | — |
| 137 | Submit external training records | A | P | — | — | — | C | — |
| 138 | Review / accept / return / reject external records; record verification | A | P | — | — | — | — | — |
| 139 | Open certificate scans (audited, reason) | A | P | — | — | — | C ASSUMPTION (§10 Q13) | — |
| 140 | Suspend / reinstate / revoke training records | A | P | — | — | — | — | — |
| 141 | Import training records / attendance (dry-run, commit); `provider_register_file` | A | P | — | — | — | C (contractor_file only) | — |
| 142 | Competence check (TR QR, AC card in competence mode) | A | P | S | S | C1 | C | — |
| 143 | View training KPIs, expiring items, action panel, refresher plan, readiness report | A | P | S | S | C1 | C | P (aggregates) |
| 144 | Export training registers (IDs and scans never; names only with 46; scores only HSE Mgr/Officer); per-worker report | A | P | S | — | — | C | P (no names) |
| 145 | Edit Phase 5 settings; enable training hooks (HK5-1); early switch; one deferral; void a session | A | — | — | — | — | — | — |

Gate devices keep only capability 74 (Phase 2); training results reach them through the hook. Suspended-contractor users keep reads and lose writes (Phase 0 rule 28).


## 6. Calculations

All dates local Asia/Riyadh (Phase 0 K2). `add_months` as Phase 2 §6.1 (clamped to month end). Rounding half-up at output only (Phase 1 K-R8): percentages 1 dp, hours 2 dp, training hours per worker 2 dp; comparisons and warnings use unrounded values. Day differences are calendar days.

### 6.1 Record validity (strictest wins)
- course_end = add_months(completed_on, validity_months(course, project)) − 1 day, where validity_months(course, project) = min(catalogue validity_months, project `course_validity_months[course]` if set). A no-expiry course (null) gives course_end = null unless the project sets a cap.
- **valid_until (org default, stored)** = min(printed_expiry, add_months(completed_on, catalogue validity) − 1 day); a null term is ignored; both null → null (no expiry). printed_expiry is read as the last valid day as printed ASSUMPTION (as Phase 4 §6.1).
- **valid_until (effective on project P, computed on read)** = min(stored valid_until, add_months(completed_on, P override) − 1 day).
- limiting_factor = the term giving the minimum (`printed_expiry` on a tie, then `course_validity`, then `project_override`); `none` when no term exists.
- Renewals: a new record's validity runs from its own completed_on; remaining days of the previous record are never carried over (TR-11, strictest wins).
- days_left(d) = valid_until − d.

### 6.2 Requirement due date and state (per deployment × de-duplicated requirement, MX-4…MX-6)
- applies_from = max(deployment.mobilised_on, line.effective_from, date the line began to apply to the deployment through trade, matrix role, zone, pass or ADP).
- due_date = applies_from + due_within_days (0 for hook codes, MX-5).
- state at as_of d (end of day):
  1. `exempt` if an active exemption covers (deployment, line) at d;
  2. `met` if some record satisfying the requirement (CC-6; for any_of, any listed code) is in force at d (§6.6) — shown `expiring` when its valid_until ≤ d + 30;
  3. `due` if d < due_date;
  4. `gap` otherwise.
- A requirement is **counted** (K-82…K-84) when its line is mandatory and kpi_counted, the deployment is a Mobilised contractor_worker deployment at d, and state ∈ {met, expiring, gap}. `due` and `exempt` requirements and recommended lines are shown but not counted.

### 6.3 Session minutes
- net_minutes(day) = (end_time − start_time in minutes) − break_minutes.
- session_net_minutes = Σ net_minutes(day); SS-2 requires session_net_minutes ≥ min_duration_hours × 60 and each net_minutes(day) ≤ `session_day_max_net_hours` × 60.
- attendance complete (AT-1) ⇔ for every day, attended minutes ≥ net_minutes(day) (attendance_min_pct = 100).

### 6.4 Person-hours (TH-1…TH-3, TH-6)
- session_hours(day, attendee) = attended minutes ÷ 60 (any result); only Closed, not Voided (or voided after the as_of, TH-9) sessions.
- register_hours(project, engagement, day d) = Σ session_hours over contractor_worker attendees whose deployment engagement on d is that engagement + Σ hours of sponsored external records with completed_on = d (TH-3).
- **K-37 numerator** over a period = Σ_d [ d ≥ training_register_from ? register_hours(d) : daily-return training_hours(d) ]; training_register_from null → daily returns only. Denominator K-03 (Phase 1, unchanged).
- reconciliation_pct = |Σ register_hours(register days) − Σ daily-return training_hours(register days)| ÷ Σ daily-return training_hours(register days) × 100; note shown when > 5.00 (TH-7); not computed when the daily-return sum is 0.

### 6.5 Hook block dates (kind training_course)
critical_block_from = provider_registered_on + `training_hook_critical_transition_days`; general_block_from = provider_registered_on + `training_hook_transition_days` (+ one deferral ≤ 30 days). Block starts 00:00 local on that date (job 00:00:30).

### 6.6 In-force predicate
A record R is **in force** at local date d on project P ⇔ status ∈ {Accepted} ∧ ¬historic ∧ (verification_status = verified ∨ (source ≠ session ∧ within `unverified_training_acceptance_hours` of reviewed_at ∧ course ∉ critical codes)) ∧ completed_on ≤ d ∧ (effective valid_until on P is null ∨ d ≤ effective valid_until) ∧ the provider is not blacklisted in a scope covering R ∧ R's session (if any) is not Voided. Suspended, Revoked, Rejected, Superseded-before-d and Expired records are never in force. **Expiring (hook)** = in force ∧ valid_until ≤ d + 7 (as Phase 2 ZP-3). **Expiring (KPI, alerts)** = in force ∧ valid_until ∈ [d, d + 30].

### 6.7 Refresher planning
refresher_due_from = valid_until − `refresher_planning_days` (HEAT-AWR: min(that date, heat_season_start − 60) per GP-6). Plan state: `booked_in_time` if the holder is nominated (not withdrawn) to a Scheduled or In Progress session of the same course (or of its renewal course) whose last day ≤ valid_until; `booked_late` if the last day > valid_until; `not_booked` otherwise.

### 6.8 KPI catalogue (continues Phase 4 §6.7; K-37 revised source)

| ID | Metric (EN / AR) | Formula | Unit / display | Better |
|---|---|---|---|---|
| K-37 (rev.) | Training hours per worker / ساعات التدريب لكل عامل | §6.4 numerator ÷ K-03; per-day single source; reconciliation note per TH-7; tile chip "n sessions not closed" (TH-1) | h, 2 dp | higher |
| K-82 | **Training matrix compliance** / نسبة الامتثال لمصفوفة التدريب | n(counted requirements at as_of with state met or expiring) ÷ n(counted requirements at as_of) × 100; denominator 0 → "—"; breakdown by course, trade, contractor | %, 1 dp | higher |
| K-83 | **Workers fully trained** / العمال المستوفون لكل متطلباتهم | n(Mobilised contractor_worker deployments at as_of with ≥ 1 counted requirement and no `gap`) ÷ n(Mobilised contractor_worker deployments at as_of with ≥ 1 counted requirement) × 100 | %, 1 dp | higher |
| K-84 | **Competency gaps** / الفجوات في الكفاءة | at as_of: n(counted requirements in state gap) · n(deployments with ≥ 1 gap) · n(gaps whose code is a hook code on the project, HK5-2 first list) | count · count · count | lower |
| K-85 | Training expiring ≤ 30 days / تدريب ينتهي خلال 30 يوماً | n(distinct records in force at as_of with valid_until ∈ [as_of, as_of + 30] that satisfy a counted requirement of a Mobilised contractor_worker deployment on the project); breakdown by course | count | lower |
| K-86 | **Training person-hours** / ساعات التدريب الفعلية | Σ register_hours of the period's days ≥ training_register_from (§6.4), by course category, including hours of sessions voided later (shown as a separate "voided" figure, TH-9); second figure: client/PMC staff hours (not in K-37) | h, 2 dp · h, 2 dp | — |
| K-87 | Assessment pass rate / نسبة النجاح في التقييم | n(attendances with result passed in sessions Closed in period) ÷ n(attendances with result passed or failed in those sessions) × 100 (incomplete excluded; failures for LANGUAGE_NOT_UNDERSTOOD included) | %, 1 dp | — (shown, not targeted) |
| K-88 | **Refreshers booked in time** / التجديدات المحجوزة في الوقت | n(K-85 records with plan state booked_in_time at as_of) ÷ K-85 × 100; K-85 = 0 → "—" | %, 1 dp | higher |

### 6.9 Leading-indicator warnings (extend Phase 1 §6.9; monthly job day 2, 07:00, per project and per tier-1 tree, DECISIONS #53)
- **E12** at the end of month M: K-82 (as_of last day of M, unrounded) < `training_matrix_warning_pct`. Not raised when the K-82 denominator is 0.
- **E13** in M: ≥ 1 training verification with outcome not_found, details_differ or revoked_by_provider performed in M, **or** ≥ 1 session Voided in M.
- Inputs returned by T13: K-82 numerator/denominator and threshold (E12); the count of failed verifications and voided sessions (E13) — never worker identities or failure details (TK-4).

### 6.10 Worked examples (exact; backend unit tests must match)

**TR1 — validity (strictest wins).** (a) Imran Hussain WAH (24): completed 2026-09-20 → add_months(2026-09-20, 24) − 1 = **2028-09-19**, limiting `course_validity`. (b) FIRST-AID completed 2026-08-31 → add_months = 2028-08-31 → **2028-08-30** (month-end clamp not needed; −1 day). (c) External FIRST-AID completed 2025-07-01, printed 2027-06-30: course_end 2027-06-30 → tie → **2027-06-30**, limiting `printed_expiry`. (d) External FIRST-AID completed 2025-02-10 printed **2028-02-09** (3-year card) → course_end 2027-02-09 → valid_until **2027-02-09**, limiting `course_validity`, import warning W01. (e) A record completed 2024-02-29 with 12 months → add_months = 2025-02-28 → **2025-02-27**. (f) Project override (hypothetical, not seeded): RBT-52 sets WAH = 12 → Hamza Al-Shehri WAH completed 2025-03-02 has stored valid_until **2027-03-01** but effective on RBT-52 **2026-03-01** (limiting `project_override`); on ANIA-EXP it would stay 2027-03-01; session TRS-RBT-52-2026-00022 (trainer Hamza) would be refused `TRAINER_NOT_TRAINED`. (g) Noura Al-Qahtani NEBOSH-IGC → valid_until null, limiting `none`. (h) Mahmoud Fathy IOSH-MS completed 2025-02-10 → **2028-02-09**.

**TR2 — due dates and states.** (a) Imran Hussain (scaffolder) mobilised 2026-08-25; WAH line MXL-ANIA-EXP-003 effective 2026-09-01, due 0 → due_date = max(2026-08-25, 2026-09-01) + 0 = **2026-09-01**; state on 2026-09-08 = **gap** (no record until 2026-09-20) → incident INC-ANIA-EXP-2026-0147 on 2026-09-08 gets `training_gap_at_event` = yes (TR9). From 2026-09-20 state met. (b) HEAT-AWR (due 7): a labourer mobilised 2026-09-28 → due_date **2026-10-05**; state `due` on 2026-10-04 (not counted), `gap` on 2026-10-05 if no record. (c) Exempt document controller (exemption on SCAFF-AWR): not counted. (d) A deployment matching two lines requiring WAH (trade scaffolder; zone line WAH due 0) → one requirement (MX-6).

**TR3 — session minutes and hours.** TRS-ANIA-EXP-2026-00057 CSE-ATTENDANT, 2026-10-07 07:00–16:00, break 60 → net = 540 − 60 = **480 min** = 8.00 h ≥ min 8.00 → SS-2 passes; a day 07:00–17:30 break 30 = 600 min = 10.00 h → allowed (= max); 07:00–17:45 break 30 = 615 min → `SESSION_DAY_TOO_LONG`. Ten nominees: 9 attend 480 min, Biju Thomas among them; 1 leaves at 13:30 (attended 390 min) → partial, result incomplete, no record. Person-hours = 9 × 8.00 + 390 ÷ 60 = 72.00 + 6.50 = **78.50 h** (TH-1: partial attendance counts). Biju passes (theory 85.00, practical pass) → record valid **2028-10-06** (add_months(2026-10-07, 24) − 1).

**TR4 — expiry alerts and refreshers.** (a) Ahmed Raza FIRE-WATCH completed 2024-10-11 → valid_until **2026-10-10**; refresher_due_from 2026-08-11; 30/14/7/0 alerts due **2026-09-10, 2026-09-26, 2026-10-03, 2026-10-10**. He was nominated on 2026-09-15 to TRS-ANIA-EXP-2026-00058 (FIRE-WATCH, 2026-10-08) → booked_in_time → 09-26 alert suppressed (GP-5); 09-10 and 10-03 sent. At the clock days_left = **4** → hook `expiring` → Phase 3 warning EXPIRING_7D on PTW-0412. If 00058 closes on 2026-10-08 with a pass → new record valid **2028-10-07**, the old one Superseded 2026-10-08, the 0-day alert cancelled. (b) Rajesh Nair AVSEC-AWR completed 2025-10-13 → **2026-10-12**; alerts 2026-09-12, 2026-09-28, 2026-10-05, 2026-10-12; days_left at clock **6** (expiring); booked on TRS-ANIA-EXP-2026-00061 on 2026-10-15 → `booked_late` (2026-10-15 > 2026-10-12) → nothing suppressed. 2026-10-13…10-15 (until Close): not in force → gate WARN `HOOK_NOT_MET_WARN` (TRAINING_EXPIRED) for Z-TWB, because AVSEC-AWR is a general code that blocks only from 2026-10-31. Renewal completed 2026-10-15 → **2027-10-14**. Without renewal: gate DENIED `HOOK_NOT_MET` from 2026-10-31. (c) Rafiq Islam FIRST-AID completed 2024-11-16 → **2026-11-15**; FIRST-AID-R completed 2026-11-10 → accepted (previous in force) → **2028-11-09**; completed 2026-11-16 → 422 `REFRESHER_NOT_ELIGIBLE` (lapse 1 day > 0). (d) Majed (WKR-000025) PTW-ISSUER completed 2024-10-26 → **2026-10-25**; alerts 2026-09-25, 2026-10-11, 2026-10-18, 2026-10-25; PTW-ISSUER is not critical → 2026-10-26…10-30 Phase 3 warning `HOOK_NOT_MET_WARN`, blocker `KEY_ROLE_INELIGIBLE` from 2026-10-31. (e) Rafiq Islam CSE-RESCUE completed 2025-11-03 (12) → **2026-11-02**, days_left at the clock **27**; it satisfies only enforcement lines for him (rescue lead), so it is not in K-85, but it is in the refresher plan since 2026-09-03 because he is rescue lead on non-terminal PTW-0413 (GP-3).

**TR5 — hook stages (both projects; training provider registered 2026-10-01).** critical_block_from = 2026-10-01 + 7 = **2026-10-08**; general_block_from = 2026-10-01 + 30 = **2026-10-31**; maximum deferral **2026-11-30**. (a) Biju Thomas, standby on Active PTW-0413, has no CSE-ATTENDANT: at the clock → warning `HOOK_NOT_MET_WARN` (TRAINING_MISSING), permit stays Active. If session 00057 is Closed on 2026-10-07 → met. If not, at 2026-10-08 00:00:30 → not_met under block → PTW-0413 (if Active) Suspended `hook_not_met` within 60 s, and a new issue → blocker. (b) Sanjay Verma (WKR-000028, receiver of PTW-0408) has no PTW-RECEIVER: Khalid's revalidation at 23:00 on 2026-10-06 → warning `HOOK_NOT_MET_WARN`; from 2026-10-31 → `KEY_ROLE_INELIGIBLE`. (c) A holder_user_id with no linked worker → `HOLDER_NOT_LINKED` (warn in transition). (d) Deferring WAH → `CRITICAL_CODE_NO_DEFERRAL`; a second deferral → `DEFERRAL_USED`; switching CSE-ATTENDANT back to warn after 2026-10-08 → `HOOK_POLICY_LOOSENING`. (e) Hard stop: if FIRST-AID is attached to rescue_lead (§11.4) and Waleed Saleh (latest FIRST-AID record Rejected `verification_failed`, no other in force) is named rescue lead → not_met `TRAINING_VERIFICATION_FAILED`, hard_stop = true → blocker at once, though in transition.

**TR6 — K-37 source switch (W1 workforce fixture, ANIA-EXP, September 2026; K-03 = 2,900).** Variant: training_register_from = **2026-09-16**. Daily returns 09-01…09-15: Σ training_hours = **2,100.00**; daily returns 09-16…09-30: 2,250.00 (ignored for K-37). Register 09-16…09-30: session hours 2,364.50 + sponsored external FIRST-AID 3 × 16.00 = 48.00 (completed 2026-09-24) = **2,412.50**. Not counted: staff hours 24.00 (client_pmc_staff attendees), an OSHA-30 prior-learning record 30.00 (not sponsored). K-37 = (2,100.00 + 2,412.50) ÷ 2,900 = 4,512.50 ÷ 2,900 = 1.5560… → **1.56 h**. Reconciliation = |2,412.50 − 2,250.00| ÷ 2,250.00 × 100 = 7.222… % > 5 % → note "Daily returns differ from the training register by 7.2 % for register days". With training_register_from = null → (2,100.00 + 2,250.00) ÷ 2,900 = **1.50 h** (Phase 1 W1 unchanged).

**TR7 — KPI fixture = seed (as_of 2026-09-30; Appendix A.9).**

| Metric | ANIA-EXP calculation | ANIA-EXP | RBT-52 calculation | RBT-52 |
|---|---|---|---|---|
| K-82 | 10,826 ÷ 11,019 × 100 = 98.2484… | **98.2 %** | 2,103 ÷ 2,163 × 100 = 97.2260… | **97.2 %** |
| K-83 | 3,241 ÷ 3,412 × 100 = 94.9882… | **95.0 %** | 600 ÷ 654 × 100 = 91.7431… | **91.7 %** |
| K-84 | gaps 193 · workers 171 · hook-code gaps 34 (WAH 12, LOTO 4, ELEC-QUALIFIED 9, AVSEC-AWR 9) | **193 · 171 · 34** | 60 · 54 · 10 (WAH 5, LOTO 2, ELEC-QUALIFIED 3) | **60 · 54 · 10** |
| K-85 | | **64** | | **15** |
| K-86 | contractor 5,124.00; staff 96.00 | **5,124.00 h · 96.00 h** | 1,038.00; 24.00 | **1,038.00 h · 24.00 h** |
| K-87 | 1,356 ÷ 1,412 × 100 = 96.0339… | **96.0 %** | 268 ÷ 281 × 100 = 95.3736… | **95.4 %** |
| K-88 | 41 ÷ 64 × 100 = 64.0625 | **64.1 %** | 12 ÷ 15 × 100 | **80.0 %** |

Expected warnings September 2026: **no E12 ANIA-EXP** (98.248 ≥ 98.0); **E12 RBT-52** (97.226 < 98.0), raised for the project and for the QIMMA tree. **E13 ANIA-EXP** (verification not_found for Waleed Saleh's QUICKTRAIN FIRST-AID card on 2026-09-21), raised for the project and for the RAWABI tree (SAHARA is a RAWABI subcontractor, Phase 0 seed); no E13 RBT-52.

**TR8 — rounding edges.** K-82 9,795 ÷ 10,000 = 97.95 → displayed **98.0 %** but E12 **raised** (97.95 < 98.0); 9,805 ÷ 10,000 = 98.05 → **98.1 %**, no E12. K-37 1,319.50 ÷ 2,900 = 0.455 → **0.46**; 1,305.00 ÷ 2,900 = **0.45**. K-88 1 ÷ 3 = 33.333… → **33.3 %**.

**TR9 — training gap at event (Phase 1 T9 dimension).** training_gap_at_event(incident) = yes if any worker linked to the incident (injury case worker_id, Phase 2 v1.1) had, on the event's local date, a counted requirement in state gap on the incident's project; no if all linked workers had none; unknown if no worker is linked or the date is before training_register_from. INC-ANIA-EXP-2026-0147 (2026-09-08, Imran Hussain) → **yes** (WAH gap, TR2a).

**TR10 — provider acceptability.** (a) HAYAT `srca` accreditation valid to **2027-06-30**: FIRST-AID completed 2027-06-30 → acceptable; completed 2027-07-01 → 422 `PROVIDER_NOT_ACCEPTABLE` (`ACCREDITATION_INVALID`); records already accepted stay in force (PV-7). (b) QUICKTRAIN Suspended 2026-09-22: a record completed 2026-09-22 → `PROVIDER_SUSPENDED`; completed 2026-09-21 → can be submitted, in force only after verification (it then failed, E13). (c) RAWABI-TU (contractor_internal) delivering WAH → `CONTRACTOR_DELIVERY_NOT_ALLOWED`. (d) RAWABI-TU delivering HEAT-AWR to a QIMMA worker → `NOT_OWN_TREE`. (e) INT-HSE delivering FIRST-AID → `INTERNAL_NOT_ALLOWED` (accreditation required). (f) GSA delivering NEBOSH-IGC with `nebosh` accreditation → acceptable to 2027-09-30.

## 7. Alerts & expiries

Channels as Phases 1–4: in-app and email in the recipient's language; SMS where marked (ASSUMPTION). Workers have no accounts, so alerts about a holder go to the Contractor HSE Rep of the worker's engagement (C scope) and to the HSE Officers of every project where the worker is Mobilised. Texts carry worker_no (name only for recipients with capability 46), course, record or session number and the date; never ID numbers, scores, scan links or verification-failure details (P5-4, P5-6). The long schedule `alert_schedule_long_days` = 30 / 14 / 7 / 0 days before the last valid day is sent at 07:00 local. Each step is sent once, de-duplicated per (subject, step); steps still to come are cancelled when a renewal comes into force, and 30/14-day steps are suppressed for `booked_in_time` records (GP-5).

| Trigger | Recipient | Timing | Channel |
|---|---|---|---|
| Training record expiry (record satisfies a requirement of a Mobilised deployment, or a hook code) | Engagement's HSE Rep; HSE Officer at 7 and 0; HSE Manager at 0 for critical codes | 30 / 14 / 7 / 0 days (30/14 suppressed when booked_in_time) | In-app + email |
| Record expiring while the holder is named on a non-terminal permit or Active WAP crew, or holds an Active appointment needing it | Receiver (permit) or WAP supervisor's HSE Rep; HSE Officer | When the permit/WAP/appointment is created or changed if valid_until ≤ its end; and at the 7-day step | In-app |
| Refresher due (record enters the plan, GP-3) | Engagement's HSE Rep; HSE Officer (weekly digest, Sunday 07:00) | On refresher_due_from; then weekly while `not_booked` | In-app + email |
| Refresher booked late (`booked_late`) | HSE Officer; engagement's HSE Rep | When the booking is made | In-app |
| Competency gap on a hook code for a worker on a live permit / WAP (GP-7) | Receiver; HSE Officer; engagement's HSE Rep | Within 60 s of the gap arising; daily 07:00 while it persists | In-app + email |
| New gap at mobilisation (requirement due) | Engagement's HSE Rep | On the day the deployment becomes Mobilised (list of due dates); again 2 days before each due_date | In-app |
| Session scheduled, rescheduled or cancelled | Nominees' HSE Reps; trainers (users) | Immediately | In-app + email |
| Session reminder | Trainers; nominees' HSE Reps | 1 day before the first day, 07:00 | In-app |
| Session close due (SS-8) | HSE Officers; HSE Manager when overdue | On last day + 1 (07:00) and on the deadline; daily while overdue | In-app + email |
| Session voided (SS-9) | Holders' HSE Reps ("Training record not accepted / السجل التدريبي غير مقبول"); HSE Officers; receivers of live permits naming a holder | Within 60 s | In-app + email |
| External record submitted (review queue) | HSE Officers of the project | Immediately; reminder at 24 h | In-app |
| Verification due (`training_verification_due_days` after submission) | HSE Officers; HSE Manager when overdue | 1 day before; on the due day; daily while overdue | In-app + email |
| Verification `unable_to_verify` (VR-5) | HSE Manager; HSE Officers | Immediately | In-app + email |
| Verification failed (VR-6) | HSE Manager; HSE Officers; engagement's HSE Rep (no detail, P5-4) | Immediately | In-app + email + SMS (HSE Manager) |
| Record returned, rejected, suspended or revoked | Submitter; engagement's HSE Rep (no reason, TR-13) | Immediately | In-app |
| Certificate number reused for another worker (TR-5) | HSE Officers | Immediately | In-app + email |
| Trainer authorisation expiry | Trainer (if user); authoriser; HSE Officers | 30 / 14 / 7 / 0 days | In-app + email |
| Trainer authorisation expires or is suspended with sessions still Scheduled | HSE Officers | Immediately (sessions flagged `TRAINER_NOT_AUTHORISED`) | In-app + email |
| Provider accreditation expiry (PV-8) | HSE Officers; HSE Manager | 30 / 14 / 7 / 0 days | In-app + email |
| Provider suspended or blacklisted | HSE Officers of every project; affected HSE Reps (no reason); receivers of live permits naming affected holders | Within 60 s | In-app + email |
| Hook block date approaching (critical / general, kind training_course) | HSE Manager; HSE Officers; Contractor HSE Reps of every engagement on the project (with their own readiness counts, HK5-9) | 7 days and 1 day before (07:00); on the switch (00:00:30) | In-app + email |
| Early switch, deferral or hook policy change | HSE Officers; Contractor HSE Reps | Immediately | In-app + email |
| Training attempts exceeded (AT-5) | HSE Officer; engagement's HSE Rep | On the failed attempt that reaches the limit | In-app |
| Import batch Validated / committed / expired | Uploader | Immediately | In-app |
| E12 / E13 (§6.9) | HSE Manager; HSE Officers of the project; tier-1 Contractor HSE Rep for its tree | Monthly job day 2, 07:00 | In-app + email |

Expiry, plan and alert computation run in `training_daily` (00:06:00); 07:00 sends. An alert whose subject was demobilised, superseded or anonymised before its send time is dropped. Re-running a job never sends twice.

## 8. Reports / KPIs fed

### 8.1 Dashboard additions (Phase 1 §8.1)
1. **Leading tiles:** K-82 training matrix compliance (course breakdown on hover; E12 threshold marker) · K-83 workers fully trained · K-84 competency gaps (chip: hook-code gaps) · K-88 refreshers booked in time (chip: K-85 expiring ≤ 30 days). K-37 keeps its tile; its source label reads "Training register" or "Daily returns" (or "Mixed" when the period spans the switch), with the reconciliation note and the "n sessions not closed" chip.
2. **Training band** (all projects): sessions this week (scheduled, in progress, awaiting close) · external records awaiting review and verification (overdue chip) · K-85 expiring ≤ 30 days · gaps on hook codes for workers on live permits · hook stage for kind training_course with the next block date ("Critical training codes block from 2026-10-08").
3. **Charts:** C19 K-82 and K-83 by month (lines) with the E12 threshold as a reference line · C20 training person-hours by month stacked by course category, with K-37 as a line (secondary axis) · C21 training expiry profile for the next 90 days, weekly bars split booked / not booked.
4. Filters D-2 apply (site, zone, contractor with subcontractors, period), plus trade, course and course category.

### 8.2 Expiring-items panel — new `ExpiringItemKind` values
`training_record_expiry`, `training_refresher_due`, `trainer_authorisation_expiry`, `training_provider_accreditation_expiry`, `training_verification_due`, `training_session_close_due`; `hook_block_date` (Phase 4) is reused with kind training_course. Item fields as Phase 2 §8.2; ref = record_no, session_no, authorisation_no or provider code; worker_no without names for callers without capability 46; Viewer/Client sees counts only (TK-5).

### 8.3 Action panel additions
External records awaiting review > 24 h · training verifications overdue · verification failed with no decision recorded (VR-6) · `unable_to_verify` · sessions Delivered and not Closed after the deadline · hook-code gaps of workers on non-terminal permits or Active WAPs (GP-7) · records expiring ≤ 7 days `not_booked` · hook block date ≤ 7 days with training readiness < 100 % · Scheduled sessions whose trainer authorisation or provider status no longer allows them · appointment holders `HOLDER_NOT_LINKED`.

### 8.4 Registers and reports
- Course catalogue (EN/AR) with validity, provider rule and hook use.
- Provider register with accreditations, status and expiries.
- Trainer authorisation register.
- Training matrix per project (current and versions), with applicability counts.
- Session calendar and session register (attendance, results — scores per AT-7).
- Training record register per worker and per course; the per-worker training passport (printable, QR on session records, no ID/score).
- Gap register (GP-1) and refresher plan (GP-3), exportable for the contractor.
- Verification log.
- Hook readiness report (HK5-9).
- Training hours report: per engagement and month, register vs daily return, with the source used for K-37.
- Import history.

Exports (capability 144) never contain ID numbers or scans; names only with capability 46; scores only for HSE Manager/Officer.

### 8.5 Feeds to other phases
- **Phase 1:** K-37 numerator for register days (TH-6); K-82…K-88; E12–E13; T17; T9 dimension `training_gap_at_event` (TR9); AI-19 report section "Training & competence" (aggregates only).
- **Phase 2:** provider for `training_course` at zone profiles, pass categories and ADP categories (gate checks, eligibility, WAP crew exclusion); QR kind `TR` accepted by the scanner app in competence mode only (never as an access token); induction records read-only (HK-7).
- **Phase 3:** provider for crew roles, permit-type sections and appointment holders; hard-stop and post-block suspensions of live permits via HK5-8 events.
- **Phase 4:** none (boundary BD5-1…BD5-3); the hook policy state entity is shared with kind training_course.
- **Phase 6:** toolbox talks, emergency-team coverage (fire wardens, first aiders per head) and drills may read Phase 5 records (aggregates and in-force predicates). v1.2: 6c reads Phase 5 records through the training check for coverage and rescue teams, and adds matrix roles `fire_warden` / `first_aider` from its roster (`6c-emergency-drills.md` EO-2).

## 9. Acceptance criteria

Fixtures:
- Appendix A seed.
- "Today" is the shared e2e/demo clock `HSE_CLOCK_AT` = 2026-10-06 10:00 Asia/Riyadh unless another date or time is given (Appendix A.1).
- Phase 2, 3 and 4 seed state as in their Appendix A.
- Training hooks were enabled on both projects on 2026-10-01 (stage `transition`): critical training codes block from 2026-10-08, the others from 2026-10-31. `training_register_from` = 2026-09-01 on both projects.

Users (as Phase 4 §9): Faisal HSE Manager · Noura HSE Officer ANIA-EXP · Lina HSE Officer RBT-52 · Ahmed Contractor HSE Rep, RAWABI tree · Yousef Contractor HSE Rep, QIMMA · Omar and Fahad site engineers · Khalid and Majed permit issuers · Faris, Sanjay, Joseph permit receivers · Sarah viewer.

**Boundary and catalogue**
1. **Given** Phase 4 PCT contains `GAS-TESTER` **When** Faisal creates course code `GAS-TESTER` **Then** 422 `CODE_IN_OTHER_CATALOGUE`; **when** he creates `GAS-TEST` **Then** it is rejected only because it already exists (409) (BD5-2).
2. **Given** course IND-GENERAL (induction_link) **When** Noura schedules a session for it **Then** 422 `INDUCTION_OWNED_BY_PHASE2`; **when** Ahmed submits an external record for it **Then** the same error (BD5-4).
3. **Given** Phase 3 gas-tester hooks **When** Salem Al-Harthi is checked for PTW-0413 **Then** `training_course: GAS-TEST` is answered by Phase 5 (met, valid_until 2028-04-14) and `personnel_certificate: GAS-TESTER` by Phase 4 separately; neither satisfies the other (BD5-3).
4. **Given** Noura **When** she edits a course **Then** 403 (capability 126).
5. **Given** WAH validity 24 **When** Faisal sets it to 36 **Then** 422 `CATALOGUE_LOOSENING`; **when** he sets 18 **Then** saved, every WAH record's valid_until is recomputed (Imran Hussain → 2028-03-19), and holders now expiring ≤ 30 days are alerted (CC-2).
6. **Given** FIRST-AID requires accreditation srca/aha/erc **When** Faisal sets internal_allowed = true **Then** 422 `ACCREDITED_PROVIDER_REQUIRED` (CC-4).
7. **Given** CSE-ENTRANT (practical required) **When** a session with delivery_mode e_learning is scheduled **Then** 422 `PRACTICAL_REQUIRED`; blended is accepted (CC-5).
8. **Given** CSE-RESCUE satisfies CSE-ENTRANT and CSE-ATTENDANT **When** a worker holding only CSE-RESCUE (in force) is checked for CSE-ATTENDANT **Then** met with ref = the CSE-RESCUE record (CC-6).
9. **Given** a course with prerequisite A where A has prerequisite the course **Then** 422 `PREREQUISITE_CYCLE`.
10. **Given** a course used by records **When** Faisal deletes it **Then** 409; he can make it inactive and existing records stay in force (CC-1).

**Providers and accreditations**
11. **Given** Noura **When** she approves a provider **Then** 403; Faisal approves it, audited (PV-1).
12. **Given** an accreditation without register_checked_at **Then** it does not count, and a FIRST-AID record from that provider gets 422 `PROVIDER_NOT_ACCEPTABLE` (`ACCREDITATION_INVALID`) (PV-2).
13. **Given** HAYAT srca valid to 2027-06-30 **Then** a FIRST-AID record completed 2027-06-30 is accepted and one completed 2027-07-01 gets `ACCREDITATION_INVALID`; already accepted HAYAT records stay in force after 2027-06-30 (TR10a, PV-7).
14. **Given** HAYAT's accreditation ends 2027-06-30 **Then** alerts are scheduled 2027-05-31, 2027-06-16, 2027-06-23 and 2027-06-30 (PV-8).
15. **Given** QUICKTRAIN Suspended 2026-09-22 **When** a record completed 2026-09-22 is submitted **Then** `PROVIDER_SUSPENDED`; completed 2026-09-21 **Then** it may be submitted (TR10b).
16. **Given** RAWABI-TU (contractor_internal) **When** a WAH session is scheduled with it **Then** `CONTRACTOR_DELIVERY_NOT_ALLOWED`; **when** a HEAT-AWR session includes a QIMMA worker **Then** `NOT_OWN_TREE` (TR10c–d).
17. **Given** INT-HSE **When** a FIRST-AID session is scheduled with it **Then** `INTERNAL_NOT_ALLOWED`.
18. **Given** Faisal blacklists a test provider with scope `all_records` **Then** every record of it is Revoked `provider_blacklisted` within 60 s, the hook returns not_met hard_stop for codes they satisfied, and Noura receives the list of affected holders (PV-6).
19. **Given** scope `issued_from` 2026-09-15 **Then** only records completed on or after 2026-09-15 are revoked.

**Trainer authorisations**
20. **Given** Noura **When** she authorises herself as trainer **Then** 422 `SOD_CONFLICT` (TA-1).
21. **Given** an authorisation for CSE-ENTRANT without evidence files **Then** 422 (evidence required for high_risk_task).
22. **Given** valid_from 2026-10-06 **When** valid_to 2028-10-06 is entered **Then** 422 (max 24 months → ≤ 2028-10-05).
23. **Given** Salem authorised for HEAT-AWR, H2S-AWR, CSE-ENTRANT, CSE-ATTENDANT, GAS-TEST to 2027-03-31 **When** he is trainer on a WAH session **Then** `TRAINER_NOT_AUTHORISED` (TA-2).
24. **Given** Noura authorised for WAH **When** her own WAH record had expired on the session day **Then** `TRAINER_NOT_TRAINED` (TA-3).
25. **Given** Hamza is trainer of TRS-RBT-52-2026-00022 **When** he is also nominated **Then** `SOD_CONFLICT` (TA-4).
26. **Given** Lina **When** she grants Yousef (Contractor HSE Rep, QIMMA) an authorisation for WAH under QIMMA-TU **Then** 422 `TRAINER_NOT_AUTHORISED` (TA-6: WAH does not allow contractor delivery); for HEAT-AWR **Then** accepted.
27. **Given** an authorisation expiring on 2026-10-20 with a session on 2026-10-22 **Then** at expiry the session is flagged `TRAINER_NOT_AUTHORISED` and HSE Officers alerted.

**Matrix and profiles**
28. **Given** ANIA-EXP's WAH line for trades scaffolder, steel_erector and rigger **Then** as of 2026-09-30 it has 519 counted requirements (scaffolder 160, steel_erector 313, rigger 46), 507 met or expiring and 12 gaps (TR7, A.9).
29. **Given** Phase 2 zone profile Z-APR-21 requires AVSEC-AWR **Then** a read-only `zone` line exists; **when** Noura edits it **Then** 422 `LINE_DERIVED_FROM_HOOK` (MX-2).
30. **Given** a derived `crew_role` line (standby_person → CSE-ATTENDANT) **Then** it is kpi_counted = false and does not count in K-82 (MX-2).
31. **Given** a manual line with due_within_days 30 for WAH **Then** 422 `DUE_DAYS_NOT_ALLOWED` (hook code).
32. **Given** `any_of` [NEBOSH-IGC, NEBOSH-ICC, IOSH-MS, OSHA-30] for supervisors **Then** accepted; `any_of` [WAH, SCAFF-AWR] **Then** 422 `ANY_OF_NOT_ALLOWED` (MX-3).
33. **Given** Noura **When** she removes the mandatory HEAT-AWR line **Then** 422 `MATRIX_LOOSENING`; Faisal removes it with a reason ≥ 20 chars → effective_to = yesterday, previous version kept (MX-8).
34. **Given** a line saved on 2026-10-06 **When** effective_from 2026-09-01 is sent **Then** it is ignored and stored as 2026-10-06 (MX-7).
35. **Given** Ahmed **When** he adds matrix role first_aider to a QIMMA worker **Then** 403 (C scope); to a NAJD worker on ANIA-EXP **Then** saved from today (MX-9).
36. **Given** an exemption for IND-GENERAL or WAH **Then** 422 `EXEMPTION_NOT_ALLOWED`; for SCAFF-AWR with a reason ≥ 30 chars **Then** granted and excluded from K-82 (MX-10).
37. **Given** a work zone not on the deployment's sites **Then** 422 `ZONE_NOT_IN_DEPLOYMENT_SITES`.
38. **Given** Imran Hussain mobilised 2026-08-25 and the WAH line effective 2026-09-01 **Then** his WAH due_date is 2026-09-01, state on 2026-09-08 gap, from 2026-09-20 met (TR2a).
39. **Given** a labourer mobilised 2026-09-28 (HEAT-AWR due 7) **Then** state `due` on 2026-10-04 and `gap` on 2026-10-05 without a record (TR2b).

**Sessions**
40. **Given** a CSE-ATTENDANT session with one day 07:00–14:00 break 60 (360 min) **Then** 422 `SESSION_TOO_SHORT` (min 480).
41. **Given** a day 07:00–17:45 break 30 **Then** 422 `SESSION_DAY_TOO_LONG` (615 > 600) (TR3).
42. **Given** capacity 10 and 10 nominations **When** an 11th is added **Then** 422 `SESSION_FULL`.
43. **Given** Noura records a past session whose last day was 2026-09-28 **Then** 422 `BACKDATED_SESSION` (> 7 days); last day 2026-09-30 **Then** Delivered (SS-5).
44. **Given** Ahmed (Contractor HSE Rep) **When** he records a past session **Then** 403 (HSE Officer/Manager only).
45. **Given** Biju Thomas nominated to TRS-ANIA-EXP-2026-00057 **When** he is nominated to another session on 2026-10-07 **Then** 422 `SCHEDULE_CLASH`.
46. **Given** a CSE-RESCUE session **When** a worker without in-force CSE-ENTRANT and FIRST-AID is nominated **Then** 422 `TRAINING_PREREQUISITE` naming the missing code(s) (SS-6).
47. **Given** a worker Banned in Phase 2 **When** nominated **Then** 422 `WORKER_BANNED`.
48. **Given** session 00057 is Scheduled for 2026-10-07 07:00 **Then** at 07:00 it becomes In Progress and at 16:00 Delivered.
49. **Given** Salem is trainer and assessor of 00057 **When** he closes it **Then** 422 `SOD_CONFLICT`; Noura closes it (SS-8).
50. **Given** a nominee without final status **When** Close is attempted **Then** 422 listing the nominee.
51. **Given** no attendance sheet and two attendees without a device signature **Then** Close is refused until the sheet is attached.
52. **Given** 00057 Delivered on 2026-10-07 and not closed **Then** a close-due alert is sent 2026-10-08 07:00 and on 2026-10-10 (deadline), and the action panel lists it from 2026-10-11.
53. **Given** a Scheduled session is cancelled **Then** nominees' HSE Reps are notified and the refresher plan items return to `not_booked` (SS-10).
54. **Given** Faisal voids TRS-ANIA-EXP-2026-00031 with reason `trainer_not_competent` **Then** Imran Hussain's WAH record from it is Revoked within 60 s, the WAH hook is not_met hard_stop (blocks although in transition), Ahmed sees "Training record not accepted / السجل التدريبي غير مقبول", E13 counts the void in October, and K-37 excludes the session's hours for as_of ≥ the void date (SS-9, TH-9).
55. **Given** Noura **When** she voids a session **Then** 403 (capability 145).

**Attendance and assessment**
56. **Given** 00057 with 9 attendees at 480 min and 1 at 390 min **Then** person-hours = 78.50, the 390-min attendee is `partial` / `incomplete` with no record (TR3, AT-1).
57. **Given** theory 79.50 % on an 80 % course **Then** result failed; 80.00 % **Then** passed (with practical pass) (AT-2).
58. **Given** a course with pass mark 70 and setting 80 **Then** the effective mark is 80.
59. **Given** a practical result recorded by a trainer who is not an assessor of the session **Then** 422 (AT-3).
60. **Given** a worker failed WAH 3 times since 2026-09-10 **When** nominated again on 2026-10-06 **Then** 422 `TRAINING_ATTEMPTS_EXCEEDED` until Noura records a re-training note (AT-5).
61. **Given** session 00057 is delivered in en with interpreter_languages [ur, hi] **Then** Biju Thomas (primary_language ur) has understood_language = interpreter and can pass; **when** a worker whose primary_language is ne is nominated **Then** warning `LANGUAGE_MISMATCH`, and at Close his result is failed `LANGUAGE_NOT_UNDERSTOOD` regardless of scores (high_risk_task) (AT-6).
62. **Given** HEAT-AWR (awareness, not in language_block_categories) delivered in ar to an ne-speaking worker **Then** passed with warning `LANGUAGE_MISMATCH`.
63. **Given** Omar (site engineer) **When** he opens attendance of 00057 **Then** he sees status and result, not scores (AT-7).

**Records and certificates**
64. **Given** 00057 closed with Biju passed **Then** a record TRR-… is created Accepted, verification verified (session_record), certificate_no TRC-ANIA-EXP-2026-…, valid_until 2028-10-06, a bilingual PDF with QR `HSE2:TR:…` and no ID number, score or photo (TR-14).
65. **Given** an external record with no scan **When** Ahmed submits **Then** 422 (scan required).
66. **Given** the same (provider, course, certificate_no) exists **Then** 409 `CERT_EXISTS`; the same certificate_no for another worker of the same provider/course **Then** 409 `CERT_NO_REUSED` and HSE Officers alerted (TR-5).
67. **Given** a card showing ID 2000001017 for Biju **Then** `matched`; typed 2000001071 **Then** 422 `CERT_ID_MISMATCH`, nothing stored, audit shows `2*******71` (TR-6).
68. **Given** name_as_printed "B. Thomas" match partial **When** Noura accepts **Then** allowed with W02-style warning; match none **Then** `NAME_MISMATCH_CONFIRMATION` required.
69. **Given** Ahmed submitted a record **When** Ahmed tries to accept it **Then** 403; when Noura accepts it after she submitted it herself **Then** `SOD_CONFLICT` (TR-7).
70. **Given** an external CSE-RESCUE record whose holder had no FIRST-AID in force on completed_on and no evidence tick **Then** 422 `TRAINING_PREREQUISITE` (TR-9).
71. **Given** a record completed 2024-01-10 for HEAT-AWR (12) **Then** `RECORD_ALREADY_EXPIRED`; Noura may attach it as historic, never in force (TR-3).
72. **Given** Rafiq's FIRST-AID valid to 2026-11-15 **When** FIRST-AID-R completed 2026-11-10 **Then** accepted, valid 2028-11-09, old record Superseded when the new one is in force; completed 2026-11-16 **Then** `REFRESHER_NOT_ELIGIBLE` (TR4c).
73. **Given** an Accepted record older than 24 h **When** Noura edits completed_on **Then** 403; Faisal with reason **Then** saved and audited (TR-12).
74. **Given** Noura suspends a record with a 10-char reason **Then** 422; with ≥ 20 chars **Then** Suspended, hook not_met `TRAINING_SUSPENDED` hard_stop, HSE Rep sees "not accepted" without reason (TR-13).
75. **Given** a worker banned in Phase 2 **Then** his training records are unchanged (TR-15).
76. **Given** Imran Hussain's WAH record **When** he is deployed to RBT-52 **Then** the same record satisfies RBT-52 requirements, with RBT-52's validity override applied on read (TR-16).

**Verification**
77. **Given** an external FIRST-AID record Accepted but not_verified **Then** it is not in force (`TRAINING_UNVERIFIED`) (VR-1, setting 0 h).
78. **Given** Faisal sets `unverified_training_acceptance_hours` = 24 **Then** a non-critical record is in force for 24 h after Accept; a CSE-ENTRANT record is not (VR-1).
79. **Given** a QIMMA employee with capability 138 (test) **When** he verifies a QIMMA worker's record **Then** `SOD_CONFLICT` (VR-2).
80. **Given** HAYAT's verification_domains [hayat-test.example] **When** the record's QR URL host is verify.hayat-fake.example **Then** warning `VERIFICATION_URL_FOREIGN_DOMAIN` and that channel cannot be chosen; the server makes no outbound request (VR-4).
81. **Given** two no_response attempts 2026-10-01 09:00 and 2026-10-02 10:00 **Then** `unable_to_verify` and Faisal alerted (VR-5).
82. **Given** Waleed Saleh's QUICKTRAIN FIRST-AID card verified not_found on 2026-09-21 **Then** the record is Rejected `verification_failed`, Faisal is alerted (SMS), the action panel asks for a decision (ban prompt only, never automatic), and E13 is raised for ANIA-EXP and the RAWABI tree for September (VR-6).
83. **Given** a renewal record of a verified holder **Then** it needs its own verification (VR-7).
84. **Given** a provider_register_file import whose evidence email is from a domain not in the provider's verification_domains **Then** the file is rejected; from the provider's domain **Then** committed rows get verification records method provider_register_file, outcome confirmed, still Submitted for review (VR-8, IM5-6).

**Gaps and refreshers**
85. **Given** Ahmed **When** he opens the gap register **Then** he sees RAWABI-tree deployments only; Sarah sees counts only (GP-2).
86. **Given** Rajesh Nair's AVSEC record (valid to 2026-10-12) **Then** it entered the refresher plan on 2026-08-13; his booking on 2026-10-15 is `booked_late` and no alert was suppressed (TR4b, GP-5).
87. **Given** Ahmed Raza booked on 00058 (2026-10-08) on 2026-09-15 **Then** the 2026-09-26 alert was not sent and the 2026-10-03 alert was; at the clock the hook returns `expiring` (4 days) (TR4a).
88. **Given** "create session from plan" for FIRE-WATCH **Then** nominees are pre-filled up to max_class_size and each passes SS-6 (GP-4).
89. **Given** HEAT-AWR records expiring 2027-05-19 and heat season start 2027-06-01 (Phase 1 setting) **Then** they enter the plan on min(2027-03-20, 2027-04-02) = 2027-03-20 (GP-6).
90. **Given** Biju (no CSE-ATTENDANT) is standby on Active PTW-0413 **Then** the action panel lists the gap with the permit number (GP-7), and his deployment stays Mobilised (GP-8).

**Hooks and the warn → block switch**
91. **Given** training_register_from null on a test project **When** Faisal enables training hooks **Then** 422 `TRAINING_REGISTER_NOT_LIVE` (HK5-1).
92. **Given** hooks enabled on 2026-10-01 **Then** the hook policy state for kind training_course shows critical_block_from 2026-10-08, general_block_from 2026-10-31 and stage transition; Phase 2 no longer returns `HOOK_NOT_AVAILABLE` for training codes (TR5).
93. **Given** Biju without CSE-ATTENDANT at the clock **When** PTW-0413 is evaluated **Then** warning `HOOK_NOT_MET_WARN` (TRAINING_MISSING), permit stays Active (HK5-4).
94. **Given** the clock advanced to 2026-10-08 00:01 with Biju still untrained and PTW-0413 Active **Then** PTW-0413 is Suspended `hook_not_met` within 60 s and a new issue shows blocker `HOOK_NOT_MET` (TR5a).
95. **Given** Sanjay Verma without PTW-RECEIVER **When** Khalid revalidates PTW-0408 at 23:00 on 2026-10-06 **Then** warning `HOOK_NOT_MET_WARN`; at 2026-10-31 **Then** blocker `KEY_ROLE_INELIGIBLE` (TR5b).
96. **Given** Rajesh Nair at gate G-AAP3 for Z-TWB on 2026-10-13 (AVSEC expired 2026-10-12, not renewed) **Then** GRANTED_WITH_WARNING `HOOK_NOT_MET_WARN`; on 2026-10-31 **Then** DENIED `HOOK_NOT_MET` (TR4b).
97. **Given** Rajesh at the gate on 2026-10-06 **Then** GRANTED_WITH_WARNING `EXPIRING_7D` for AVSEC-AWR (6 days).
98. **Given** Faisal defers general_block_from to 2026-11-30 with a reason ≥ 30 chars **Then** saved; a second deferral **Then** `DEFERRAL_USED`; deferring WAH **Then** `CRITICAL_CODE_NO_DEFERRAL` (HK5-5).
99. **Given** stage block for CSE-ATTENDANT **When** Faisal switches it back to warn **Then** 422 `HOOK_POLICY_LOOSENING`.
100. **Given** Faisal switches all codes early on 2026-10-10 **Then** stage block for all training codes from that moment, audited, HSE Officers and HSE Reps alerted.
101. **Given** an attach point with code `SCAFF-USER` (not in the catalogue) **Then** the provider returns `unknown_code`, warn in transition and blocks after general_block_from, and the HSE Manager sees a configuration error (HK5-2).
102. **Given** a Revoked WAH record and no other WAH in force **Then** not_met `TRAINING_REVOKED`, hard_stop = true — blocks at the clock (HK5-3); **given** a newer in-force WAH record **Then** met.
103. **Given** an appointment holder_user_id with no linked worker **Then** not_met `HOLDER_NOT_LINKED`, hard_stop false (HK5-7).
104. **Given** a record expires at 00:06 **Then** `training.record_changed` is published and Phase 2/3 re-evaluate within 60 s; a cached provider result older than the event is not used (HK5-8).
105. **Given** the readiness report for ANIA-EXP **Then** per code it lists subjects, met/expiring counts, not-met with reasons and the permits, WAPs and gates affected; Ahmed sees his tree only (HK5-9).
106. **Given** Phase 3 shift planned end 2026-10-10 19:00 and Ahmed Raza's FIRE-WATCH valid to 2026-10-10 **Then** met (valid_until covers the shift's local date); a shift on 2026-10-11 **Then** not_met `TRAINING_EXPIRED` (HK5-10, unless renewed).

**Training hours and K-37**
107. **Given** TR6 (W1 fixture, training_register_from 2026-09-16) **Then** K-37 = 1.56 h and the tile shows the reconciliation note 7.2 %; **with** the setting null **Then** 1.50 h (TH-6, TH-7).
108. **Given** a Delivered, not Closed session in September **Then** its hours are not in K-37/K-86 and the K-37 tile shows "1 session not closed" (TH-1).
109. **Given** client_pmc_staff attendees (e.g. Noura, Khalid) **Then** their hours appear as K-86 staff hours and not in K-37 (TH-2).
110. **Given** an external OSHA-30 record not sponsored **Then** no hours in K-37/K-86 (TH-3).
111. **Given** a daily-return import for 2026-09-20 with training_hours 48.00 on a project with training_register_from 2026-09-01 **Then** the row is imported with warning W07 "training hours from the training register are used for this date" (TH-6, §11.2).
112. **Given** Faisal changes training_register_from from 2026-09-01 to 2026-09-15 **Then** 422 (may only move earlier); to 2026-08-15 **Then** saved, audited.
113. **Given** Phase 2 inductions in September **Then** they count in K-38 and not in K-37 (TH-4).

**Imports**
114. **Given** a training_records file with 3 rows (valid, unknown worker, duplicate certificate) **When** dry-run **Then** row 1 OK, row 2 E01, row 3 E04, IDs masked (`2*******17`), batch Validated; commit creates 1 record in status Submitted (IM5-5).
115. **Given** a Validated batch 61 minutes old **When** commit **Then** 409 (expired).
116. **Given** a row with printed expiry beyond course validity **Then** W01 and valid_until shortened.
117. **Given** Ahmed uploads a row for a QIMMA worker **Then** E08.
118. **Given** a session_attendance file for 00057 with minutes 500 on day 1 **Then** E10 (> 480).
119. **Given** a file with a missing course_code column **Then** E12, whole file rejected.
120. **Given** a committed file with an ID column **Then** the stored file is deleted at commit and the audit records only sha256 (IM5-4).

**QR and competence check**
121. **Given** a site engineer with capability 142 and without capability 46 (the seed grants Omar capability 46, so the test removes it, as Phase 4 AC111) scans Biju's TR QR **Then** he sees course, "Worker", worker_no, completed_on, valid_until, status green, provider INT-HSE — no ID, score or scan; `training_qr_view` is logged (CK5-1).
122. **Given** a revoked record's QR **Then** "REVOKED / ملغاة".
123. **Given** a TR QR presented at a gate as an access token **Then** DENIED `TOKEN_UNKNOWN` (Phase 2 GC-3: TR is not a gate token kind); the scanner app parses `HSE2:TR:<22>` only in competence mode (§11.3).
124. **Given** Fahad opens Biju's AC card in competence mode **Then** the Training section lists each applicable requirement with in force yes/no, reason and valid_until, and one `cert_check_view` audit row is written (CK5-2).
125. **Given** an unauthenticated request to a QR URL **Then** 401; there is no public verification page (CK5-3).

**KPIs, warnings and AI**
126. **Given** the seed **When** KPIs for ANIA-EXP as of 2026-09-30 are requested **Then** K-82 98.2 %, K-83 95.0 %, K-84 193 · 171 · 34, K-85 64, K-86 5,124.00 h · 96.00 h, K-87 96.0 %, K-88 64.1 % (TR7).
127. **Given** the seed **When** KPIs for RBT-52 as of 2026-09-30 **Then** K-82 97.2 %, K-83 91.7 %, K-84 60 · 54 · 10, K-85 15, K-86 1,038.00 h · 24.00 h, K-87 95.4 %, K-88 80.0 % (TR7).
128. **Given** the monthly job on 2026-10-02 **Then** E12 is raised for RBT-52 and the QIMMA tree and not for ANIA-EXP; E13 is raised for ANIA-EXP and the RAWABI tree and not for RBT-52 (§6.9).
129. **Given** K-82 = 9,795 / 10,000 **Then** displayed 98.0 % and E12 raised; 9,805 / 10,000 **Then** 98.1 % and no E12 (TR8).
130. **Given** the contractor filter RAWABI with subcontractors on ANIA-EXP **Then** K-82…K-88 equal the project values (all ANIA-EXP engagements are in the RAWABI tree).
131. **Given** T17 is called for ANIA-EXP Sep 2026 grouped by course **Then** it returns aggregates matching TR7; no names, worker_no, certificate numbers, scores or verification details; T13 returns E12–E13 with inputs (TK-4).
132. **Given** T9 with dimension `training_gap_at_event` **Then** INC-ANIA-EXP-2026-0147 is in the "yes" group (TR9).
133. **Given** Sarah (viewer) **Then** she sees K-82…K-88 tiles and charts C19–C21 as aggregates, and no gap lists or names (TK-5).
134. **Given** the frontend **Then** it renders KPI values exactly as returned by the API (TK-1).

**Alerts**
135. **Given** Majed's PTW-ISSUER valid to 2026-10-25 **Then** the 30-day alert went out 2026-09-25 and alerts are scheduled 2026-10-11, 2026-10-18 and 2026-10-25 to the engagement's HSE Rep, with HSE Officers added at 7 and 0 days; Faisal is not added at 0 because PTW-ISSUER is not a critical code (TR4d).
136. **Given** a record renewed before its 7-day step **Then** the 7- and 0-day steps are cancelled.
137. **Given** the job re-runs on the same day **Then** no alert is sent twice.
138. **Given** the hook block date 2026-10-08 **Then** the 7-day alert went out at registration on 2026-10-01 (the 7-day point is that day), the 1-day alert on 2026-10-07 07:00, and the switch alert on 2026-10-08 00:00:30.

**PDPL, permissions and audit**
139. **Given** Yousef (C scope QIMMA) **When** he opens a QIMMA worker's scan with reason `verification` **Then** a signed URL ≤ 5 min and a `sensitive_field_read` audit row (fields_read ["training_scan"]); without a reason **Then** 422 (P5-3, row 139).
140. **Given** Lina exports the record register **Then** no ID or scan columns; names because she holds capability 46; scores included (HSE Officer). A site engineer without capability 46 gets worker_no only and no scores (row 144, P5-5).
141. **Given** a suspected-forgery record **When** Ahmed views it **Then** "Training record not accepted / السجل التدريبي غير مقبول" without details (P5-4).
142. **Given** a record that became Expired more than 2 years ago **Then** the retention job deletes its scan, keeps metadata and audits the deletion; a scan linked to an incident investigation is kept (P5-8).
143. **Given** Faisal runs a data-subject report for Biju **Then** it lists records, sessions, scores and gaps, and the export is audited with purpose `data_subject_request` (P5-9).
144. **Given** free text with an Iqama-like number in a session note **Then** Phase 1 P1-8 warning applies (P5-10).
145. **Given** a suspended contractor's HSE Rep **When** he nominates a worker **Then** 403; reads still work (Phase 0 rule 28).
146. **Given** a gate device **Then** it holds only capability 74 and cannot call Phase 5 endpoints.
147. **Given** every Phase 5 mutation **Then** an audit row exists with before/after and no ID numbers or scores in any audit diff visible to roles without score rights (Phase 0 rule 35).
148. **Given** the UI in Arabic **Then** every Phase 5 label, status and error message is shown with its AR text from §3/§4, and codes, record numbers and dates are shown left-to-right inside RTL layout (Phase 0 i18n).

## 10. Open questions for the HSE Manager

Each question has a default, so the build can start. The default is the strictest reasonable choice unless it would stop the site from working.

1. **Client training matrix:** do GACA/the airport operator (ANIA-EXP) and the tower developer (RBT-52) issue a contractor training matrix with mandatory courses and validities? Default: the seeded matrix in A.4 and the catalogue validities in §3.15; a client matrix can only tighten them (settings shorten, lines add). `VERIFY` R10.
2. **Inductions and training hours:** default — Phase 2 inductions are **not** training hours (they count in K-38), so K-37 counts formal training only. Many sites include induction time in "training hours". Include it (would add ≈ 2–3 h per new worker)?
3. **AVSEC awareness recurrence:** default 12 months and a GACA-approved centre (`gaca_avsec`). Is the national programme interval different (e.g. 24 or 36 months) and does the airport operator deliver it itself? `VERIFY` R6.
4. **External certificates before verification:** default 0 h — never in force until verified with the issuer. Allow a 24 h window for non-critical courses (never for critical codes)?
5. **Refresher lapse:** default 0 days — a short refresher (FIRST-AID-R, IOSH-MS-R) is accepted only while the previous certificate is still valid; after that, the full course. Allow a grace (e.g. 30 days)? `VERIFY` SRCA/AHA rules.
6. **AIRSIDE-RTF:** the radiotelephony course exists in the catalogue but is not attached to any Phase 2 ADP category. Attach it to `manoeuvring` ADPs (Doc 9870)? Default: not attached.
7. **Validities set as ASSUMPTION:** WAH 24 months, FIRE-WATCH 24, SCAFF-AWR 24, HEAT-AWR 12, CSE entrant/attendant 24, CSE-RESCUE 12, LOTO and ELEC-QUALIFIED 36, PTW roles 24. Confirm or shorten.
8. **Warn → block:** default 7 days for critical training codes (CSE-*, GAS-TEST, FIRE-WATCH, WAH, LOTO, LOTO-AUTHORITY) and 30 days for the rest, same mechanism as Phase 4 (one deferral, no loosening). With the seed this means critical training blocks from **2026-10-08**. Confirm the list and dates, or block from day one.
9. **Session controls:** default 100 % attendance required, 80 % pass mark, max 3 attempts in 30 days, the person who closes a session is not its trainer/assessor, and a signed attendance sheet (or device signatures). Confirm.
10. **Public QR verification page:** default none — a TR QR shows details only to logged-in users with capability 142 (PDPL minimisation). Do clients, other sites or authorities need an unauthenticated "valid / not valid" page (name initials only)?
11. **Voided sessions:** default — hours stay in K-86 history (flagged) but leave K-37 from the void date. Remove them from all history instead?
12. **Assessment scores:** default — used only to decide whether a course is passed; never for HR, pay or discipline; visible to HSE staff, trainers and the worker's Contractor HSE Rep. Confirm with legal/HR (PDPL purpose limitation).
13. **Contractor HSE Reps opening certificate scans** (capability 139, own scope, with reason, audited): allowed by default. Restrict to HSE staff?
14. **Matrix defaults:** SCAFF-AWR for labourers, carpenters, masons, painters and steel fixers (due 14 days); BANKSMAN-AWR for flagmen; supervisors need one of NEBOSH IGC/ICC, IOSH MS or OSHA-30 within 90 days; HSE staff need NEBOSH and FIRST-AID; H2S-AWR for zones Z-MSCP and Z-B4. Confirm or extend (e.g. WAH for all workers on Pier B, first aiders 1 per 50 workers — Phase 6).
15. **No-expiry qualifications:** NEBOSH certificates and OSHA-30 have no expiry. Should the client cap their age (e.g. OSHA-30 within 5 years)? Default: no cap.
16. **Heat-stress awareness:** default 12 months, refreshed before the heat season (plan 60 days before 06-01), due within 7 days of mobilisation. Should it be due before first work (0 days) during the season?
17. **Language:** default — a high-risk, PTW-role, emergency, AVSEC or airside course in a language the worker does not understand (and without an interpreter in it) cannot be passed. Phase 2 inductions only warn. Confirm.
18. **E12 threshold:** default 98.0 % matrix compliance. Confirm or lower (e.g. 95.0 %, as Phase 4 personnel).
19. **Trainers from contractors under the internal provider:** the seed authorises Salem Al-Harthi (RAWABI HSE staff) under INT-HSE. Allowed, or must internal trainers be client/PMC staff only?
20. **Exemptions:** default ≤ 6 months, HSE Officer may grant, never for IND-GENERAL or hook codes. Confirm.

## 11. Changes required in earlier specs (applied 2026-10-08: `1-dashboard.md` v1.4, `2-access-permits.md` v1.3, `3-ptw.md` v1.2, `4-third-party-cert.md` v1.1)

### 11.1 `0-foundation.md` v1.0
No change. Rules 26–28, 35, 45 and 48 and PDPL P1–P13 are used as they are. Capability rows 125–145 continue the matrix (§5.15).

### 11.2 `1-dashboard.md` v1.3 → v1.4
1. **§3.10 settings:** add `training_register_from` (date / null, default null; ≥ project start; ≤ today; may only move earlier once set) next to `induction_register_from`.
2. **§6.1 K-37:** numerator per day from exactly one source (§6.4 here): register hours for d ≥ `training_register_from`, daily-return `training_hours` before it or when null; reconciliation note > 5 % (TH-7); tile chip "n sessions not closed". Denominator K-03 unchanged. The W1/W2 fixtures have the setting null, so **every Phase 1 W-example and AC38 (K-37 = 1.50) is unchanged**.
3. **§3.2 daily-return import:** warning **W07** "training hours from the training register are used for this date" when training_hours > 0 on a date ≥ `training_register_from`. No validation change.
4. **§5.9 AI:** add T17 `get_training_kpis` (TK-4); T13 returns E12–E13; T9 gains dimension `training_gap_at_event` (TR9); AI-19 monthly report gains section "Training & competence" (K-37, K-82…K-88, aggregates only) and uses T1–T17; AI-10 analysis "training gaps vs incidents" via T9.
5. **§6.9 / §7:** add E12 and E13 (§6.9 here); same monthly job (day 2), scope (project and tier-1 tree) and recipients.
6. **§8.1:** leading tiles K-82, K-83, K-84, K-88 (with K-85 chip); K-37 tile source label; training band; charts C19–C21; `ExpiringItemKind` values from §8.2 here; action-panel items from §8.3 here.

### 11.3 `2-access-permits.md` v1.2 → v1.3
1. **HK-4 effective policy for kind training_course:** resolved from the hook policy state (Phase 4 §3.14, kind training_course, §3.12 here); the Phase 2 setting `hook_policy.training_course` is superseded once Phase 5 registers its provider on the project (HK5-1). Transition stage `HOOK_NOT_MET_WARN` and hard stops as for Phase 4 kinds.
2. **§3.20 QR kinds:** add `TR` (`HSE2:TR:<22-char token>`, generated by Phase 5 for session-issued certificates). Update the AC64 regex to `^HSE2:(AC|VS|WP|PT|EQ|TR):[A-Za-z0-9_-]{22}$`. GC-3: a TR token presented at a gate is DENIED `TOKEN_UNKNOWN` (not a gate token kind); the scanner app opens it only in competence mode (CK5-1).
3. **HK-7:** confirm Phase 5 reads induction records (read-only) to answer `induction_link` codes (CC-7).
4. **HK-3 subjects:** confirm `worker.user_id` (§3.1) is the link Phase 3 uses for appointment holders (HK5-7); no field change.
5. **Seed:** Appendix A.8 here converts seven unnamed bulk workers into named workers linked to the receiver, isolation-authority and contractor-rep users (as the Phase 3/4 seeds did) and adds two client/PMC staff rows for the issuers; K-48 and every Phase 2 KPI example are unchanged. No deployment is re-traded (DECISIONS #100).
6. **AC21–AC23** (hook not available / test provider) stay valid on the Phase 2 seed, where no training provider is registered; the Phase 5 behaviour is covered by ACs 92–97 here.
7. **§10 Q10** (hook transition) is answered for kind training_course by HK5-5 / §10 Q8 here.

### 11.4 `3-ptw.md` v1.1 → v1.2
1. **HK3-2 default hooks:** WAH for **every crew member** on a permit with a work-at-height section, not only harness users (OSHA 1926.503(a)(1), strictest wins); crew role `rescue_lead` additionally requires `training_course: FIRST-AID` (1910.146(k)(2)(iii): at least one rescue member with current first aid/CPR).
2. **Appointment hooks:** call the training provider for the holder's linked worker (worker.user_id); a holder without a linked worker → not_met `HOLDER_NOT_LINKED` (warn in transition, never a hard stop) (HK5-7).
3. **HK3-5 events:** subscribe to `training.record_changed`, `training.session_voided`, `training.provider_changed` and `hook_policy.changed` (kind training_course); suspend live permits (`hook_not_met`) on hard stops and on not_met after the block date, within 60 s.
4. **AC17/AC18** stay valid on the Phase 3 seed (no provider registered); Phase 5 behaviour is covered by ACs 93–95 and 102–106 here.

### 11.5 `4-third-party-cert.md` v1.0 → v1.1
1. **§3.14 hook policy state:** `kind` enum adds `training_course`; for that kind the dates come from the Phase 5 settings `training_hook_transition_days`, `training_hook_critical_transition_days` and `training_hook_critical_codes` (§3.16 here); HK4-4…HK4-7 apply unchanged; Phase 5 capability 145 performs the policy actions for that kind.
2. **VF-9 certificates mode:** the access-card view shows a Training section from Phase 5 (CK5-2), in one `cert_check_view` audit row.
3. **BD-3:** already enforced both ways in the build (DECISIONS #96: PCT codes vs `training_course` codes, induction courses and zone-profile training hooks). Record it in BD-3 and name the Phase 5 catalogue as the data source; no behaviour change.
4. **§8.2:** `hook_block_date` also covers kind training_course.

## Appendix A — Seed data (fictional; `seed_fake = true` on every row; all names, IDs, certificate numbers and providers are fake)

### A.1 Principles
- Builds on the Phase 0–4 seeds; no earlier seed row changes (named workers are added within the Phase 2 bulk counts, A.8). **Seed clock = `HSE_CLOCK_AT` = 2026-10-06T10:00:00+03:00 (Asia/Riyadh)**, as in Phases 1–4.
- `training_register_from` = **2026-09-01** on ANIA-EXP and RBT-52 (register go-live). The generator writes Sep 2026 daily-return `training_hours` so that, per engagement-month, they equal the register hours (no reconciliation note); earlier months' daily returns are untouched. Training before 2026-09-01 exists as imported records (source `import`, verified by `provider_register_file` from INT-HSE's own register for internal courses) so that validity dates are realistic.
- Training hooks enabled on both projects on **2026-10-01** (Faisal): stage `transition`, critical_block_from **2026-10-08**, general_block_from **2026-10-31**, no deferral. ACs that expect blocking for a non-hard-stop not_met advance the clock (e.g. 94, 95, 96); hard stops block at the clock.
- Matrix lines effective **2026-09-01** on both projects.
- Provider names and domains end in `-test.example`; external certificate numbers contain `TEST`.
- **No re-trading.** The Phase 5 seed uses the trade populations of the built Phase 0–4 seed as they are (DECISIONS #100; the Phase 4 seed already set crane_operator 14 / 6, rigger 46 / 18 and scaffolder 160 / 24). Phase 1 list T has no fire-watch trade, so fire watches (Ahmed Raza, Rohan Fernando and bulk) carry trade `other` and the matrix role `fire_watch`. Named Phase 3 workers keep the primary_language of the bulk row they were converted from (e.g. Biju Thomas ur, Ahmed Raza hi, Rajesh Nair hi). Gates are named as seeded (S-LAND gate `G-ANIA-01`); Bikash Rai is on RBT-52 and is not used here.
- Bulk records reproduce the KPI values of TR7 exactly (A.9): the generator only assigns matrix roles, work zones, records, sessions and gaps; it never changes deployments.

### A.2 Training providers

| Code | Name / الاسم | Kind | Status | Accreditation (body, no., scope, valid) | Verification channels | Notes |
|---|---|---|---|---|---|---|
| INT-HSE | Project HSE Training (client/PMC) / تدريب السلامة بالمشروع | internal | Approved 2026-08-20 (Faisal) | — | — | delivers all I courses |
| RAWABI-TU | Rawabi Training Unit / وحدة التدريب – روابي | contractor_internal (RAWABI) | Approved | — | — | HEAT-AWR, SCAFF-AWR, BANKSMAN-AWR only (TR10c–d) |
| QIMMA-TU | Qimma Training Unit / وحدة التدريب – قمة | contractor_internal (QIMMA) | Approved | — | — | TRS-RBT-52-2026-00019 |
| ASTA | Airport Security Training Academy (test) / أكاديمية أمن المطارات للتدريب (تجريبي) | external | Approved | gaca_avsec GACA-AVSEC-TEST-031 [AVSEC-AWR] → 2027-12-31; airport_operator AOP-TEST-0007 [AIRSIDE-DRV, AIRSIDE-RTF] → 2027-12-31; register checked 2026-08-20 Noura | portal verify.asta-test.example | |
| HAYAT | Al-Hayat Lifesaving Training Centre (test) / مركز الحياة للتدريب على الإسعاف (تجريبي) | external | Approved | srca SRCA-TC-TEST-114 and aha AHA-TC-TEST-2281 [FIRST-AID, FIRST-AID-R] → **2027-06-30** | portal verify.hayat-test.example; email cards@hayat-test.example | TR10a |
| GSA | Gulf Safety Academy (test) / أكاديمية الخليج للسلامة (تجريبي) | external | Approved | nebosh NEB-LP-TEST-5521 [NEBOSH-IGC, NEBOSH-ICC, NEBOSH-DIP]; iosh IOSH-TP-TEST-0904 [IOSH-MS, IOSH-MS-R] → 2027-09-30 | awarding-body portals (ACB) | |
| OTCME | OSHA Training Center Middle East (test) / مركز تدريب OSHA الشرق الأوسط (تجريبي) | external | Approved | osha_otc OTC-TEST-77 [OSHA-30] → 2027-03-31 | email cards@otcme-test.example | |
| QUICKTRAIN | QuickTrain Safety Courses (test) / كويك ترين لدورات السلامة (تجريبي) | external | **Suspended 2026-09-22** (Faisal; "first-aid cards not traceable with SRCA") | claimed srca, register check failed (not counted) | email info@quicktrain-test.example | E13 source |

### A.3 Trainer authorisations

| No. | Trainer | Provider | Courses · roles | Valid |
|---|---|---|---|---|
| TA-ANIA-EXP-0001 | Noura Al-Qahtani (user noura, WKR-000011) — authorised by Faisal | INT-HSE | WAH, PTW-RECEIVER, FIRE-WATCH · trainer, assessor | 2026-03-01 → 2028-02-29 |
| TA-ANIA-EXP-0003 | Salem Al-Harthi (WKR-000018) — authorised by Noura | INT-HSE | HEAT-AWR, H2S-AWR, CSE-ENTRANT, CSE-ATTENDANT, GAS-TEST · trainer, assessor | 2026-04-01 → 2027-03-31 |
| TA-RBT-52-0001 | Hamza Al-Shehri (WKR-000105) — authorised by Lina | INT-HSE | WAH · trainer, assessor | 2026-03-15 → 2027-03-14 |
| TA-RBT-52-0002 | Yousef Al-Ghamdi (user, WKR-000032) — authorised by Lina | QIMMA-TU | HEAT-AWR · trainer | 2026-06-01 → 2027-05-31 |

### A.4 Matrix lines (effective 2026-09-01; manual lines `MXL-<project>-nnn`; hook-derived lines are numbered H (kpi_counted) and E (enforcement-only) + 2 digits)

**ANIA-EXP**

| Line | Applies to | Requirement | Due (days) | Counted |
|---|---|---|---|---|
| MXL-ANIA-EXP-001 | all_workers | IND-GENERAL | 0 | yes |
| MXL-ANIA-EXP-002 | all_workers | HEAT-AWR | 7 | yes |
| MXL-ANIA-EXP-003 | trade scaffolder, steel_erector, rigger | WAH | 0 | yes |
| MXL-ANIA-EXP-004 | trade electrician | LOTO | 0 | yes |
| MXL-ANIA-EXP-005 | trade electrician | ELEC-QUALIFIED | 0 | yes |
| MXL-ANIA-EXP-006 | trade labourer, carpenter, mason, painter, steel_fixer | SCAFF-AWR | 14 | yes |
| MXL-ANIA-EXP-007 | trade flagman | BANKSMAN-AWR | 7 | yes |
| MXL-ANIA-EXP-008 | matrix_role fire_watch | FIRE-WATCH | 0 | yes |
| MXL-ANIA-EXP-009 | trade supervisor | any_of NEBOSH-IGC, NEBOSH-ICC, IOSH-MS, OSHA-30 | 90 | yes (all `due` until 2026-11-30 in the seed) |
| MXL-ANIA-EXP-010 | trade hse_staff | any_of NEBOSH-IGC, NEBOSH-ICC, NEBOSH-DIP | 0 | yes |
| MXL-ANIA-EXP-011 | trade hse_staff | FIRST-AID | 30 | yes (`due` until 2026-10-01 in the seed) |
| MXL-ANIA-EXP-012 | matrix_role fire_warden | FIRE-WARDEN | 14 | yes |
| MXL-ANIA-EXP-013 | matrix_role first_aider | FIRST-AID | 0 | yes |
| MXL-ANIA-EXP-014 | zone Z-MSCP | H2S-AWR | 0 | yes |
| MXL-ANIA-EXP-H01 | zone Z-APR-21, Z-TWB, Z-ILS33R (Phase 2 zone profiles) | AVSEC-AWR | 0 | yes |
| MXL-ANIA-EXP-H02 | pass_category PERM, TEMP-U | AVSEC-AWR | 0 | yes (de-duplicated with H01, MX-6) |
| MXL-ANIA-EXP-H03 | adp_category apron, manoeuvring | AIRSIDE-DRV | 0 | yes |
| MXL-ANIA-EXP-E01…E11 | crew_role fire_watch → FIRE-WATCH; entrant → CSE-ENTRANT; standby_person → CSE-ATTENDANT (E05); rescue_lead, rescue_member → CSE-RESCUE; gas_tester → GAS-TEST; crew on WAH section → WAH; electrician on isolation → LOTO, ELEC-QUALIFIED; appointment issuer → PTW-ISSUER; receiver → PTW-RECEIVER; isolation_authority → LOTO-AUTHORITY | — | 0 | no (enforcement-only) |

**RBT-52:** lines 001–013 as ANIA-EXP; MXL-RBT-52-014 zone Z-B4 → H2S-AWR; E01…E11 as ANIA-EXP; no H lines (no airside).

### A.5 Named training records (provider; completed → valid_until; state at the clock)

| Worker | Course | Record / certificate | Completed → valid_until | State at clock |
|---|---|---|---|---|
| WKR-000001 Imran Hussain (NAJD, scaffolder) | WAH | TRR-000731 / TRC-ANIA-EXP-2026-00402 (session 00031) | 2026-09-20 → **2028-09-19** | in force; gap 2026-09-01…09-19 (TR2a, TR9) |
| WKR-000001 Imran Hussain | HEAT-AWR | RAWABI-TU session | 2026-08-27 → 2027-08-26 | in force |
| WKR-000002 Rajesh Nair (GULFPAVE) | AVSEC-AWR | ASTA AVS-TEST-25-1013 | 2025-10-13 → **2026-10-12** | expiring (6 days); nominated to 00061 on 2026-10-02 (booked_late) |
| WKR-000002 Rajesh Nair | AIRSIDE-DRV · AIRSIDE-RTF | ASTA ADT-TEST-26-0125 · RTF-TEST-26-0126 | 2026-01-25 → 2028-01-24 · 2026-01-26 → 2028-01-25 | in force |
| WKR-000002 Rajesh Nair | HEAT-AWR | INT-HSE (import) | 2026-05-20 → 2027-05-19 | in force |
| WKR-000005 Mahmoud Fathy (RAWABI supervisor; matrix_role fire_warden) | IOSH-MS · FIRE-WARDEN | GSA IOSH-TEST-25-0210 · INT-HSE | 2025-02-10 → 2028-02-09 · 2025-06-01 → 2027-05-31 | in force |
| WKR-000007 Saad Al-Dosari | AVSEC-AWR | ASTA AVS-TEST-26-0302 | 2026-03-02 → 2027-03-01 | in force |
| WKR-000008 Waleed Saleh (SAHARA; matrix_role first_aider) | FIRST-AID | QUICKTRAIN QT-FA-TEST-26-0912 (completed 2026-09-12, submitted 2026-09-19 by Ahmed) | — | **Rejected** `verification_failed` (not_found, 2026-09-21, Noura via SRCA portal); gap; E13 |
| WKR-000009 Osman Idris (NAJD rigger) | WAH | INT-HSE (import) | 2025-07-14 → 2027-07-13 | in force |
| WKR-000011 Noura Al-Qahtani (client staff) | NEBOSH-IGC · WAH · FIRE-WATCH · PTW-ISSUER · AVSEC-AWR | GSA NEB-TEST-19-0515 · INT-HSE · INT-HSE · INT-HSE · ASTA | 2019-05-15 → — · 2026-02-01 → 2028-01-31 · 2026-02-03 → 2028-02-02 · 2025-09-01 → 2027-08-31 · 2026-01-20 → 2027-01-19 | in force (not counted: staff) |
| WKR-000013 Tariq Mahmood (GULFPAVE supervisor) | OSHA-30 · AVSEC-AWR | OTCME OSHA-TEST-24-0620 · ASTA | 2024-06-20 → — · 2026-05-12 → 2027-05-11 | in force |
| WKR-000015 Ahmed Raza (NAJD, trade other; matrix role fire_watch) | FIRE-WATCH | INT-HSE (import) | 2024-10-11 → **2026-10-10** | expiring (4 days); nominated 2026-09-15 to 00058 (booked_in_time) |
| WKR-000016 Kamal Hossain | CSE-ENTRANT · H2S-AWR | INT-HSE | 2025-12-08 → 2027-12-07 · 2026-02-15 → 2027-02-14 | in force |
| WKR-000017 Biju Thomas (primary_language ur) | CSE-ATTENDANT | — | — | **missing**; standby on PTW-0413 → `HOOK_NOT_MET_WARN`; nominated to 00057 |
| WKR-000018 Salem Al-Harthi (RAWABI hse_staff) | GAS-TEST · CSE-ENTRANT · CSE-ATTENDANT · H2S-AWR · HEAT-AWR · NEBOSH-ICC · FIRST-AID | INT-HSE ×5 · GSA · HAYAT | 2026-04-15 → 2028-04-14 · 2025-03-10 → 2027-03-09 · 2025-03-11 → 2027-03-10 · 2026-02-15 → 2027-02-14 · 2026-04-01 → 2027-03-31 · 2022-11-30 → — · 2025-07-01 (printed 2027-06-30) → 2027-06-30 | in force (TR1c) |
| WKR-000019 Zaheer Abbas | AVSEC-AWR | ASTA | 2026-02-20 → 2027-02-19 | in force |
| WKR-000021 Rafiq Islam (RAWABI supervisor; matrix_role first_aider) | CSE-RESCUE · FIRST-AID · NEBOSH-IGC | INT-HSE · HAYAT HY-FA-TEST-24-1116 · GSA | 2025-11-03 → **2026-11-02** · 2024-11-16 → **2026-11-15** · 2023-04-10 → — | in force; in refresher plan (TR4c, TR4e) |
| WKR-000024 Khalid Al-Otaibi (client staff) | PTW-ISSUER | INT-HSE | 2025-12-01 → 2027-11-30 | in force |
| WKR-000025 Majed Al-Shammari (PMC staff) | PTW-ISSUER | INT-HSE | 2024-10-26 → **2026-10-25** | in force; 14-day alert 2026-10-11 (TR4d) |
| WKR-000026 Ramesh Kumar (NAJD) · WKR-000027 Joseph Mathew (QIMMA) · WKR-000029 Faris Al-Anazi (RAWABI) | PTW-RECEIVER | INT-HSE | 2025-11-20 → 2027-11-19 · 2026-02-08 → 2028-02-07 · 2026-01-12 → 2028-01-11 | in force |
| WKR-000028 Sanjay Verma (GULFPAVE) | PTW-RECEIVER | — | — | **missing** → warn on PTW-0408 (TR5b) |
| WKR-000030 Nasser Al-Shahrani (RAWABI) · WKR-000031 Ibrahim Al-Saleh (QIMMA) | LOTO-AUTHORITY | INT-HSE | 2025-08-18 → 2027-08-17 · 2026-01-05 → 2028-01-04 | in force |
| WKR-000032 Yousef Al-Ghamdi (QIMMA; trade of the converted row) | HEAT-AWR · NEBOSH-IGC · FIRST-AID | INT-HSE · GSA · HAYAT | 2026-04-10 → 2027-04-09 · 2021-03-01 → — · 2025-10-20 → 2027-10-19 | in force |
| WKR-000101 Imtiaz Ahmed (QIMMA steel_fixer) | WAH · SCAFF-AWR | INT-HSE · QIMMA-TU | 2026-04-22 → 2028-04-21 · 2026-04-23 → 2028-04-22 | in force |
| WKR-000103 Ramon Cruz (QIMMA electrician) | LOTO · ELEC-QUALIFIED | INT-HSE (import) · — | 2024-09-30 → 2027-09-29 · — | LOTO in force; **ELEC-QUALIFIED gap** (one of RBT's 3) |
| WKR-000105 Hamza Al-Shehri | WAH · IOSH-MS | INT-HSE · GSA | 2025-03-02 → 2027-03-01 · 2024-05-05 → 2027-05-04 | in force |
| WKR-000107 Rohan Fernando (QIMMA, trade other; matrix role fire_watch) | FIRE-WATCH | INT-HSE | 2026-03-15 → 2028-03-14 | in force |
| WKR-000108 Joel Bautista (QIMMA rigger) | WAH | INT-HSE | 2025-06-02 → 2027-06-01 | in force |

Bulk crew members named on non-terminal Phase 3 permits hold the in-force records their hooks need, so the only training warnings on live permits at the clock are Biju (PTW-0413), Sanjay (PTW-0408) and Ahmed Raza's `expiring` (PTW-0412); no training hard stop exists at the clock.

### A.6 Sessions

| Session | Course · provider | Days | Trainers | Language / interpreters | Nominees | Status at clock |
|---|---|---|---|---|---|---|
| TRS-ANIA-EXP-2026-00031 | WAH · INT-HSE | 2026-09-20 07:00–16:00, break 60 (480) | Noura (trainer, assessor) | en / [ur, hi] | 10 (Imran Hussain + 9 NAJD/SAHARA bulk); 9 passed, 1 failed (theory 72.00) | **Closed** 2026-09-21 by Faisal; person-hours 80.00 |
| TRS-ANIA-EXP-2026-00057 | CSE-ATTENDANT · INT-HSE | 2026-10-07 07:00–16:00, break 60 (480) | Salem (trainer, assessor) | en / [ur, hi] | 10 (Biju Thomas + 9 RAWABI bulk) | Scheduled |
| TRS-ANIA-EXP-2026-00058 | FIRE-WATCH · INT-HSE | 2026-10-08 07:00–12:00, break 30 (270) | Noura | ur / [hi] | 8 (Ahmed Raza + 7 bulk) | Scheduled |
| TRS-ANIA-EXP-2026-00061 | AVSEC-AWR · ASTA (external; trainer "M. Al-Ghamdi" as printed) | 2026-10-15 08:00–12:00, break 15 (225) | external_name | ar / [en, hi, ur] | 12 (Rajesh Nair + 11 GULFPAVE bulk) | Scheduled |
| TRS-RBT-52-2026-00019 | HEAT-AWR · QIMMA-TU | 2026-09-14 06:00–07:45, break 15 (90) | Yousef | hi / [ne, bn] | 24 QIMMA bulk; 23 passed, 1 failed | **Closed** 2026-09-15 by Lina; person-hours 36.00 |
| TRS-RBT-52-2026-00022 | WAH · INT-HSE | 2026-10-06 07:00–16:00, break 60 (480) | Hamza (trainer, assessor) | ar / [ur, tl] | 8 QIMMA bulk | **In Progress** |

### A.7 Verification, suspension and hook policy state
- Waleed Saleh's QUICKTRAIN record: verification not_found 2026-09-21 (method awarding_body_portal, SRCA) → Rejected; QUICKTRAIN Suspended 2026-09-22 (TR10b). This is the only failed training verification in September (E13 ANIA-EXP and RAWABI tree).
- No session Voided; no record Suspended or Revoked at the clock.
- Hook policy state, per project, kind `training_course`: provider_registered_on 2026-10-01, stage transition, critical_block_from 2026-10-08, general_block_from 2026-10-31, deferral_used false, early_switch none.

### A.8 Named worker additions (K-48 unchanged)
- **Converted from unnamed bulk workers of the user's engagement** (as the Phase 3/4 seeds do; trade, sites, mobilisation date and language of the converted row are kept; worker.user_id linked): WKR-000026 Ramesh Kumar (NAJD) · WKR-000027 Joseph Mathew (QIMMA) · WKR-000028 Sanjay Verma (GULFPAVE) · WKR-000029 Faris Al-Anazi (RAWABI) · WKR-000030 Nasser Al-Shahrani (RAWABI) · WKR-000031 Ibrahim Al-Saleh (QIMMA) · WKR-000032 Yousef Al-Ghamdi (QIMMA). Fake IDs 2000001026…2000001032.
- **New client/PMC staff rows** (person_type client_pmc_staff, so not in K-48 or the Phase 5 KPI populations): WKR-000024 Khalid Al-Otaibi (1000001024, user khalid.otaibi) · WKR-000025 Majed Al-Shammari (1000001025, user majed.shammari), each with a Mobilised deployment on the project where they issue permits.
- **Training profiles:** Mahmoud Fathy [fire_warden]; Rafiq Islam and Waleed Saleh [first_aider]; Ahmed Raza (ANIA-EXP) and Rohan Fernando (RBT-52) [fire_watch]; Kamal Hossain, Biju Thomas and Rafiq Islam work zone Z-MSCP. Bulk role and zone assignments in A.9.

### A.9 Bulk volumes (as of 2026-09-30, reproducing TR7)

**Counted requirements (applicable · met or expiring · gap; "not due" excluded from all three).** Trade populations are those of the Phase 0–4 seed at 2026-09-30 (contractor_worker deployments Mobilised): ANIA-EXP labourer 897, welder 320, steel_erector 313, carpenter 296, steel_fixer 288, mason 267, electrician 251, driver 214, flagman 180, scaffolder 160, plant_operator 158, rigger 46, crane_operator 14, supervisor 4, other 2, engineer 1, hse_staff 1 (= 3,412); RBT-52 labourer 173, carpenter 161, electrician 142, steel_fixer 127, scaffolder 24, rigger 18, crane_operator 6, supervisor 1, other 1, welder 1 (= 654). Mobilised on or after 2026-09-24 (HEAT-AWR not yet due): ANIA-EXP 55, RBT-52 5; SCAFF-AWR trades mobilised on or after 2026-09-17: ANIA-EXP 54, RBT-52 15; flagmen mobilised on or after 2026-09-24: 1.

| Line | ANIA-EXP | RBT-52 |
|---|---|---|
| IND-GENERAL | 3,412 · 3,371 · 41 | 654 · 640 · 14 |
| HEAT-AWR (not yet due: ANIA 55, RBT 5) | 3,357 · 3,303 · 54 | 649 · 631 · 18 |
| WAH (scaffolder 160, steel_erector 313, rigger 46 · RBT 24, 0, 18) | 519 · 507 · 12 | 42 · 37 · 5 |
| LOTO (electricians) | 251 · 247 · 4 | 142 · 140 · 2 |
| ELEC-QUALIFIED | 251 · 242 · 9 | 142 · 139 · 3 (incl. Ramon Cruz) |
| SCAFF-AWR (labourer, carpenter, mason, painter, steel_fixer; not yet due: ANIA 54, RBT 15) | 1,694 · 1,640 · 54 | 446 · 432 · 14 |
| BANKSMAN-AWR (flagmen; not yet due 1) | 179 · 178 · 1 | — (no flagmen) |
| FIRE-WATCH (matrix role fire_watch) | 30 · 30 · 0 | 12 · 12 · 0 |
| Supervisor qualification any_of | — (4 supervisors, all due 2026-11-30) | — (1, due 2026-12-02) |
| HSE staff qualification any_of | 1 · 1 · 0 (Salem Al-Harthi) | — |
| HSE staff FIRST-AID | — (due 2026-10-01) | — |
| FIRE-WARDEN (matrix role) | 64 · 62 · 2 | 16 · 15 · 1 |
| FIRST-AID (first_aider role) | 96 · 93 · 3 (incl. Waleed Saleh) | 20 · 19 · 1 |
| AVSEC-AWR (zones ∪ pass categories; = contractor workers with an active PERM or TEMP-U pass; no seeded airside work-zone entry adds anyone) | 844 · 835 · 9 | — |
| AIRSIDE-DRV (active ADPs apron 88 + manoeuvring 148) | 236 · 236 · 0 | — |
| H2S-AWR (Z-MSCP · Z-B4) | 85 · 81 · 4 | 40 · 38 · 2 |
| **Total** | **11,019 · 10,826 · 193** | **2,163 · 2,103 · 60** |

| Population | ANIA-EXP | RBT-52 |
|---|---|---|
| Mobilised contractor_worker deployments (K-83 denominator) · with ≥ 1 gap | 3,412 · 171 | 654 · 54 |
| Hook-code gaps (K-84) | 34 (WAH 12, LOTO 4, ELEC-QUALIFIED 9, AVSEC-AWR 9) | 10 (WAH 5, LOTO 2, ELEC-QUALIFIED 3) |
| K-85 records expiring 2026-09-30…10-30 · of which booked_in_time (K-88) | 64 (incl. Ahmed Raza FIRE-WATCH, Rajesh Nair AVSEC-AWR) · 41 (incl. Ahmed Raza) | 15 · 12 |
| K-86 Sep person-hours by category: awareness · high_risk_task · ptw_role · electrical · emergency_response · aviation_security · airside_operations | 1,848.00 · 1,736.00 · 496.00 · 384.00 · 448.00 (incl. 48.00 sponsored external FIRST-AID) · 156.00 · 56.00 = **5,124.00**; staff 96.00 | 402.00 · 384.00 · 96.00 · 64.00 · 92.00 · — · — = **1,038.00**; staff 24.00 |
| K-87 attendances with result passed · passed + failed (sessions Closed in Sep) | 1,356 · 1,412 | 268 · 281 |

### A.10 Settings
All Phase 5 settings at the §3.16 defaults; `training_register_from` = 2026-09-01 (both projects); no `course_validity_months` overrides; `unverified_training_acceptance_hours` = 0; `refresher_max_lapse_days` = 0; `training_matrix_warning_pct` = 98.0.

## Change log

| Version | Date | Author | Change |
|---|---|---|---|
| v1.0 | 2026-10-08 | HSE Consultant Agent | First issue. §1–§11, Appendix A. Course catalogue (31 courses), providers, trainer authorisations, matrix, sessions, records, verification, gaps and refreshers, `training_course` hook provider with the Phase 4 warn → block mechanism, K-37 source switch, imports. Capabilities 125–145, KPIs K-82…K-88 (K-37 source revised), warnings E12–E13, AI tool T17, charts C19–C21, QR kind TR. Earlier-spec changes in §11 applied the same day (1-dashboard v1.4, 2-access-permits v1.3, 3-ptw v1.2, 4-third-party-cert v1.1). Seed and worked examples aligned with the built Phase 0–4 seed (DECISIONS #87–#101): trade populations as seeded (no re-trading), fire watch as matrix role, seeded languages and user names, 409 `CERT_NO_REUSED`, TR7/A.9 recomputed. |
| v1.1 | 2026-10-09 | HSE Consultant Agent | Changes required by Phase 6b (`6b-heat-stress.md` v1.0 §11.6): GP-6 refresher plan date for HEAT-AWR uses the earlier of Phase 1 `heat_season` and 6b `heat_controls_period` (defaults: 03-02). AC89 holds on projects without 6b (`heat_register_from` null). 6b §11 numbers this document as if the 6a §11 changes were applied first; those 6a changes are implemented in the backend but not yet written into this document. |
| v1.2 | 2026-10-09 | HSE Consultant Agent | Changes required by Phase 6c (`6c-emergency-drills.md` v1.0 §11.6): (1) catalogue adds WAH-RESCUE (high_risk_task, 24 months ASSUMPTION, 8.00 h, T 80 / practical, internal allowed, prerequisite WAH); (2) §8.5 6c reads Phase 5 records through the training check and adds matrix roles `fire_warden` / `first_aider` from its roster (EO-2); (3) seed: CSE-RESCUE records (INT-HSE, completed 2026-03-02, valid to 2027-03-01) for the two RT-ANIA-CSE-01 members and WAH-RESCUE records for the height team members (6c A.4). No existing AC or worked example changes. |
| v1.3 | 2026-10-09 | HSE Consultant Agent | Notes required by Phase 6d (`6d-field-assurance.md` v1.0 §11.5); no rule changes: §8.5 toolbox talks are recorded in 6d and are not training records or training hours (BD5-5, TH-5 unchanged). |
