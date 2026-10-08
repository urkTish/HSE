# Module Spec — Phase 6a: Occupational Health & Medical Fitness (fitness register, restrictions, holds, return to work, `medical_fitness` hook)

**Version:** v1.0 · **Date:** 2026-10-08 · **Author:** HSE Consultant Agent · **Status:** Draft. The HSE Manager asked to proceed without waiting for approval and will review the choices later (§10).
**Builds on:**
- `0-foundation.md` v1.0: roles, scoping legend, rules 14, 16, 28, 35, 45 and 48, PDPL P1–P13, matrix rows 1–19.
- `1-dashboard.md` v1.4: injury cases §3.4 (worker_id, case_category, nature, rtw_date), list N natures heat_exhaustion / heat_stroke, the I-rules, capabilities 29–30, rounding K-R8, warnings E1–E13, the AI tools T1–T17, the action panel and the expiring-items endpoint.
- `2-access-permits.md` v1.3: workers and deployments, blind index WK-4/WK-5, zone profiles, the ZP-4 eligibility steps, **hook kinds HK-1 (`medical_fitness` = Phase 6)**, HK-3/HK-4, setting `hook_policy.medical_fitness`, gate rules GC-4/GC-6/GC-7/GC-14, ADP categories, P2-12.
- `3-ptw.md` v1.2: crew roles list CR, **CS-3 / HK3-2 `medical_fitness: CSE-ENTRY-FIT`**, **HK3-4 / P3-3** fitness display, HT-5, PT-8 / LF-5 evaluation times, SH-2 suspensions, SH-4 crew_present.
- `4-third-party-cert.md` v1.1: hook policy state §3.14 and the warn → block mechanism §4.8 / HK4-3…HK4-7, operator binding HK4-9 with list EQC, PC-13 `medical_restriction_on_card`, VF-9.
- `5-training.md` v1.0: the provider pattern HK5-x, matrix pattern MX-x, verification pattern VR-x, imports IM5-x, competence view CK5-2, capabilities 125–145, KPIs K-82…K-88, T17.
- `docs/DECISIONS.md` #1–#101, in particular #43, #55, #56, #79 and #83.

**Covers (build order):**
1. 6a.1 OH Practitioner role and the access tiers.
2. 6a.2 Fitness code catalogue and the restriction and exposure lists.
3. 6a.3 Medical providers (clinics) and examiner registrations.
4. 6a.4 Requirement plan and worker health profiles.
5. 6a.5 Fitness assessments: site clinic, external certificates, verification.
6. 6a.6 Fitness holds, referrals and return to work.
7. 6a.7 The hook provider for `medical_fitness` and the warn → block switch.
8. 6a.8 Imports.
9. 6a.9 KPIs, alerts, dashboard and AI.

**Not in 6a:**
- WBGT, work/rest regimes, acclimatisation and heat-season controls (6b; 6a only provides HEAT-EXPOSURE-FIT, the `no_heat_exposure` restriction and heat-illness holds).
- Exposure *monitoring* (noise surveys, dust or silica sampling; 6e). 6a only schedules the *health surveillance* of exposed workers.
- First-aider and emergency-team coverage (6c).
- Drug and alcohol testing (§10 Q14).
- Camp and food-handler health certificates (welfare; not proposed).
- Clinical records of any kind (see the boundary below).

Conventions: `VERIFY` = clause or number to confirm against the current official text or the client's procedure. `ASSUMPTION` = Consultant default; the HSE Manager may override it (§10). "Must" = enforced server-side. Rule prefixes: OH role and tiers, MC catalogue, MP provider, EX examiner, MR requirement plan, WP worker health profile, FA fitness assessment, FV verification, FH fitness hold, RF referral, RW return to work, HK6 hooks, IM6 import, MK KPIs/AI, P6- PDPL. Error codes are stable strings (Phase 0 rule 48). Times are local Asia/Riyadh unless marked UTC.

**The boundary that shapes this whole module:** the platform is the *employer-facing fitness register*. It is not a medical record. The clinic keeps the clinical file: history, examination findings, test values, diagnoses and medication. The platform receives only what an employer may lawfully know under occupational-health ethics (ILO 1998 guidelines, ICOH code, R10–R11):
- per fitness code, the outcome (fit / fit with restrictions / temporarily unfit / permanently unfit);
- the **functional** restrictions (what the person must not do, never why);
- the dates and the examining physician.

Fields that would hold clinical data do not exist, and P6-2 lists data that must never be entered.

---

## 1. Purpose

On a KSA mega-project the HSE Manager has to show the client, MHRSD inspectors and GOSI that every worker was medically fit for the work they did. Two cases matter most: work where the person's health is itself the hazard (confined-space entry, crane operation, working at height, respirator use, radiation work, airside driving), and the return of injured or heat-affected workers. Today the evidence sits in contractor folders. Fitness certificates are photocopied, often show diagnoses that should never reach a supervisor, and nobody can say who is overdue for an audiogram. A worker sent to hospital with heat exhaustion can be back on the scaffold the next morning without anyone with authority clearing him. Phases 2 and 3 already ask "is this person medically fit for this zone or this crew role?" (hook kind `medical_fitness`), but no provider answers, so confined-space entrants on live permits are not checked at all.

Phase 6a provides:
- a catalogue of fitness codes with validity and examiner rules;
- registers of licensed clinics and physicians;
- a per-project requirement plan (by trade, exposure group, airside driving and PTW crew role);
- fitness assessments recorded by the site clinic or submitted as external certificates and verified with the issuing clinic;
- functional work restrictions that the permit and access checks enforce;
- **fitness holds**, which keep a worker off site after a lost-time injury, a heat illness or a supervisor's referral until a physician clears them;
- the `medical_fitness` hook provider with the same warn → block transition as Phases 4 and 5;
- new KPIs (K-89…K-96), warnings (E14–E15) and an aggregates-only AI tool (T18).

A new role, the Occupational Health Practitioner, does all of this, so HSE staff and contractors never handle more health information than the functional result.

## 2. Regulatory basis

| # | Source | What it drives here |
|---|---|---|
| R1 | **KSA Labour Law** (Royal Decree M/51, 1426H, as amended), the chapters on occupational safety, health protection, work injuries and occupational diseases. Employer duties to protect workers' health, to arrange medical examinations, and to keep workers out of work that endangers them. `VERIFY` article numbers and the latest amendments | Pre-placement (GEN-FIT) and periodic fitness, holds, records |
| R2 | **MHRSD OSH Regulations / ministerial decisions on occupational safety and health in establishments**: initial and periodic medical examinations for workers exposed to occupational hazards, health records, first aid `VERIFY` decision number and exposure list | Requirement plan (trade and exposure lines), surveillance codes, retention |
| R3 | **NCOSH** regulations and guidance on medical surveillance and fitness for work `VERIFY` current documents | Same, as the KSA benchmark |
| R4 | **GOSI** Occupational Hazards Branch: work injuries, occupational-disease schedule, medical reports and return to work after a work injury `VERIFY` | RTW holds (RW), retention of surveillance outcomes (P6-8) |
| R5 | **MOH** health-facility licensing and **SCFHS** (Saudi Commission for Health Specialties) professional registration and classification of physicians and nurses `VERIFY` register names and how to check them | Provider licence (MP-2), examiner registration (EX-1…EX-4) |
| R6 | **PDPL** (Royal Decree M/19, 1443H, amended M/148, 1444H) and its Implementing Regulations: health data is **sensitive data**; processing is limited to what is necessary; access is restricted to the minimum number of persons; specific safeguards apply `VERIFY` article numbers for health data and for the legal-obligation basis | Access tiers (OH-2), minimisation (P6-2), encryption, retention, no consent-based processing (P6-3) |
| R7 | **OSHA 29 CFR 1910.134(e)** (medical evaluation before respirator use; re-evaluation when indicated); **1910.95(g)** (baseline audiogram within 6 months of first exposure, then annual); **1926.1153(h)** (silica surveillance within 30 days of assignment, then every 3 years); **1910.1020** (access to medical and exposure records; retention for the duration of employment + 30 years). International benchmark `VERIFY` paragraph letters | RESPIRATOR-FIT, NOISE-SURV, SILICA-SURV validity and due days; surveillance retention |
| R8 | **ASME B30.5** (mobile and locomotive cranes) and **B30.3** (tower cranes) operator physical qualifications: vision (with correction), depth perception, colour discrimination, hearing, no disqualifying condition such as seizures `VERIFY` edition and clause | CRANE-OPERATOR-FIT examiner rules and tests list |
| R9 | **NRRC** (Nuclear and Radiological Regulatory Commission) rules for occupationally exposed workers, including health surveillance; **IAEA GSR Part 3** `VERIFY` | RAD-WORKER-FIT, occupational-physician requirement |
| R10 | **ILO Technical and Ethical Guidelines for Workers' Health Surveillance** (1998) and **ILO C161** (Occupational Health Services); KSA ratification `VERIFY`. The employer receives only the conclusion on fitness, not medical information | Platform boundary, tiers, the scan rule FA-9 |
| R11 | **ICOH International Code of Ethics for Occupational Health Professionals**: confidentiality; only fitness conclusions and functional limitations are communicated | Same |
| R12 | **GACA / airport operator** airside driving permit rules: driver medical fitness `VERIFY` whether a medical is required for ADP and at what interval | DRIVER-FIT attached to ADP categories |
| R13 | **Saudi Aramco CSM / GIs** and client contractor-health requirements where flowed down (e.g. annual medicals for crane operators and confined-space entrants) `VERIFY` | Validity defaults, critical codes |
| R14 | **ISO 45001:2018** cl. 6.1.2 (health hazards), 8.1.2 (eliminating hazards, adapting work to workers), 9.1 (monitoring); **ILO-OSH 2001** 3.10.1 | Requirement plan, restrictions, KPIs |
| R15 | Phase 1 R5/R6 (GOSI and MHRSD notification) and Phase 3 R12 (midday ban) | RTW linkage, the heat-illness hold |

Strictest-wins applied in this spec (and why):
- **Validity:** the effective valid_until is the earliest of the clinic's printed next-due date, examined_on + catalogue validity, examined_on + the project override, and, for an outcome with reviewable restrictions, the restriction review date (§6.1). A restricted worker who has not been reviewed is not cleared.
- **Unfit stays unfit:** a temporarily-unfit outcome remains a hard stop after its review date until a new assessment is accepted. The platform never assumes recovery (HK6-3).
- **Restrictions travel with the person:** a functional restriction recorded on any in-force line negates every code it conflicts with, whatever other line says "fit" (HK6-6 step 6).
- **General unfitness:** GEN-FIT temporarily or permanently unfit is a hard stop for every code.
- **Holds before data:** after a lost-time injury, a heat illness or a referral with removal from work, the worker is held until a physician clears them, including in the warn and transition stages (hard stop).
- **External certificates count only after verification with the issuing clinic** (FV-1), as Phases 4 and 5. Contractor-run clinics may certify only GEN-FIT, and only for their own contractor tree (MP-3).
- **Respirator and confined-space fitness are critical codes** (7-day transition), because unfitness there kills quickly. GEN-FIT, WAH-FIT and driver/plant codes get 30 days because of the population size (§10 Q7).
- **Surveillance first exam within 30 days** (OSHA 1926.1153(h)(2)) for silica, and the same 30 days for noise. That is stricter than the OSHA 6-month baseline allowance for audiometry.
- **Privacy is strictest too:** health data is shown at the lowest tier that does the job (OH-2), small cells are suppressed below 5 (stricter than Phase 1's < 3), and scans are deleted after 12 months (shorter than the 2 years in Phases 4/5).

## 3. Entities & fields

PDPL column: **none / personal / sensitive** (Phase 0 P1–P2). Every entity carries the Phase 0 system fields (id UUID, created_at/by, updated_at/by), is audited (Phase 0 rule 35) and stores `seed_fake` (bool). The AR label is shown in the UI. **Sensitive** columns in this spec are encrypted at application level (as Phase 2 P2-2) and every read writes `sensitive_field_read` (Phase 0 P5).

### 3.0 Role — Occupational Health Practitioner (Phase 0 §3.8 addition, §11.1)

| Code | EN | AR | Scope |
|---|---|---|---|
| oh_practitioner | Occupational Health Practitioner (site clinic physician or nurse) | ممارس الصحة المهنية (طبيب أو ممرض عيادة الموقع) | Assigned project(s) |

An OH Practitioner user may be linked to an examiner registration (§3.3, `user_id`), which makes the user a physician who can sign assessments. Without that link the user is a nurse or administrator who can record but not sign (FA-6). Only the HSE Manager assigns this role (Phase 0 rule 14 extension, §11.1).

### 3.1 Fitness code (org-wide catalogue) — رمز اللياقة الطبية

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| code | الرمز | string(24) | Y | `^[A-Z0-9-]{2,24}$`; unique org-wide; immutable; must not exist in Phase 4 list PCT or the Phase 5 catalogue (`CODE_IN_OTHER_CATALOGUE`, MC-2) | CSE-ENTRY-FIT | none |
| name_en / name_ar | الاسم | string(150) ×2 | Y / Y | name_ar in Arabic script | Confined space entry fitness / اللياقة لدخول الأماكن المحصورة | none |
| category | الفئة | enum | Y | list FCAT (§3.10) | task | none |
| validity_months | مدة الصلاحية (أشهر) | int | Y | 1–60 | 12 | none |
| examiner_classes | فئات الفاحص المسموح بها | enum[] | Y | ⊆ list EXC minus `nurse` (a nurse never signs, EX-3) | [occupational_physician, physician] | none |
| provider_kinds | أنواع الجهات المسموح بها | enum[] | Y | ⊆ {`site_clinic`, `external_clinic`, `contractor_clinic`}; `contractor_clinic` only when category = general (MC-4) | [site_clinic, external_clinic] | none |
| typical_tests | الفحوص المعتادة (للعلم) | enum[] | N | list TST. Informational for the clinic only; **no result is ever stored** (P6-2) | [spirometry, cardio_exam, claustrophobia_screen] | none |
| negated_by | تنفيه القيود | RC code[] | sys | from list RC `negates` (§3.10) | [no_confined_space] | none |
| hook_code | مستخدم كمتطلب | bool | sys | true when any Phase 2/3 attach point or the Phase 2 project hook list uses it (HK6-2) | true | none |
| active | فعّال | bool | Y | inactive codes get no new lines; existing lines stay | true | none |

### 3.2 Medical provider (clinic, org-wide) — مقدم الخدمة الطبية (العيادة)

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| provider_code | رمز الجهة | string(12) | Y | `^[A-Z0-9-]{2,12}$`; unique; immutable | SHIFA-ANIA | none |
| legal_name_en / legal_name_ar | الاسم | string(200) ×2 | Y / Y | unique after Phase 0 rule 45 normalisation | Shifa Occupational Health Services — ANIA site clinic (test) / شفاء لخدمات الصحة المهنية — عيادة موقع مطار النور (تجريبي) | none |
| kind | النوع | enum | Y | `site_clinic` عيادة الموقع (run for the client/PMC; serves named projects) · `external_clinic` عيادة/مستشفى خارجي مرخص · `contractor_clinic` عيادة تابعة لمقاول | site_clinic | none |
| project_ids | المشاريع | FK[] | cond. | required iff site_clinic | [ANIA-EXP] | none |
| contractor_id | المقاول | FK | cond. | required iff contractor_clinic | RAWABI | none |
| moh_licence_no / licence_valid_until | رقم ترخيص وزارة الصحة / صالح حتى | string(40) / date | Y / Y | unique; valid_until > today at approval | MOH-TEST-FAC-0457 / 2027-12-31 | none |
| licence_checked_at / by | تاريخ ومن تحقق من الترخيص | timestamptz / FK | Y to approve | MP-2 | 2026-07-20 / Faisal | none (user: personal) |
| verification_domains / verification_email / verification_phone / verification_portal_url | قنوات التحقق | string[] / email / E.164 / url | cond. | external and contractor clinics: ≥ 1 domain; email and portal hosts ∈ domains (as Phase 4 §3.1) | [salama-test.example] | none |
| status | الحالة | enum | Y | §4.1 | approved | none |
| status_reason | سبب الحالة | text(500) | cond. | required for suspended / blacklisted; P3 hint | — | none |
| blacklist_scope / blacklist_from | نطاق الحظر / من تاريخ | enum / date | cond. | `all_records` · `issued_from` (as Phase 4 §3.1) | — | none |

### 3.3 Examiner registration (org-wide) — تسجيل الفاحص الطبي

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| examiner_no | رقم الفاحص | string | sys | `EXR-` + 4 digits | EXR-0001 | none |
| full_name_en / full_name_ar | الاسم | string(120) ×2 | Y | — | Dr. Huda Al-Mansour / د. هدى المنصور | personal |
| scfhs_licence_no | رقم الترخيص المهني (الهيئة السعودية للتخصصات الصحية) | string(30) | Y | unique | SCFHS-TEST-14-0457 | personal |
| classification | التصنيف المهني | enum | Y | list EXC | occupational_physician | personal |
| licence_valid_until | صلاحية الترخيص | date | Y | > today at creation | 2027-06-30 | personal |
| licence_checked_at / by | تاريخ التحقق / المتحقق | timestamptz / FK | Y to activate | EX-1 | 2026-07-20 / Faisal | personal |
| provider_ids | الجهات التي يعمل بها | FK[] | Y | ≥ 1 approved provider | [SHIFA-ANIA, SHIFA-RBT] | personal |
| user_id | حساب المستخدم | FK | N | an `oh_practitioner` user; unique; makes the user a signing physician (FA-6) | huda.mansour | personal |
| status | الحالة | enum | Y | `active` ساري · `suspended` موقوف · `withdrawn` مسحوب · `expired` منتهٍ (job) | active | personal |

### 3.4 Requirement plan line (per project, versioned) — بند خطة المتطلبات الطبية

Same versioning and fields as Phase 5 §3.4, with these differences:
- line_no `MRL-<project>-nnn` (hook-derived lines H nn, enforcement-only lines E nn);
- `applies_to_kind` ∈ {`all_workers`, `trade`, `exposure_group`, `adp_category`, `zone`, `project_hook`, `crew_role`, `operator_binding`};
- `requirement` is one fitness code (no any_of);
- `level` is always `mandatory` (there are no recommended medical lines);
- `due_within_days` is 0…`medical_line_max_due_days` and must be 0 when the code is a hook code on the project (`DUE_DAYS_NOT_ALLOWED`);
- **there are no exemptions** (MR-6).

PDPL: none.

### 3.5 Worker health profile (per deployment) — الملف الصحي المهني للعامل

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| deployment_id | التعيين | FK | Y | unique; Phase 2 deployment | WKR-000020 @ ANIA-EXP | personal |
| exposure_groups | مجموعات التعرض | EG code[] | N | list EG; defaults from `exposure_group_trade_defaults` at mobilisation (WP-1) | [ionising_radiation] | personal |
| history | السجل | list {value, from_date, to_date, by} | sys | each change opens a row dated today (no back-dating) | — | personal |

Exposure groups describe the *job*, not the person's health, so they are personal and not sensitive.

### 3.6 Fitness assessment — تقييم اللياقة الطبية

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| assessment_no | رقم التقييم | string | sys | `MFA-<project>-<yyyy>-<nnnnn>` | MFA-ANIA-EXP-2026-00412 | none |
| worker_id / project_id | العامل / المشروع | FK / FK | Y | Phase 2 worker, not Anonymised, with a non-demobilised deployment on the project (FA-1) | WKR-000001 / ANIA-EXP | personal |
| assessment_type | نوع التقييم | enum | Y | list AT6 | return_to_work | **sensitive** |
| source | المصدر | enum | Y | `site_clinic` سجل عيادة الموقع · `external_certificate` شهادة خارجية · `import` استيراد | site_clinic | personal |
| provider_id / examiner_id | الجهة / الفاحص | FK / FK | Y | MP-3, EX-2 on examined_on | SHIFA-ANIA / EXR-0001 | sensitive |
| examined_on | تاريخ الفحص | date | Y | ≤ today; site_clinic ≥ today − `assessment_backdate_max_days` (FA-2) | 2026-09-28 | sensitive |
| certificate_no | رقم الشهادة | string(40) | Y | site_clinic: system `MFC-<project>-<yyyy>-<nnnnn>`; external: as printed; unique per provider (FA-10) | MFC-ANIA-EXP-2026-00412 | personal |
| lines | بنود اللياقة | list of §3.6a | Y | 1–11 lines; ≤ 1 per code (FA-3) | [GEN-FIT fit, WAH-FIT fit] | **sensitive** |
| related_hold_id / related_referral_id | الإيقاف / الإحالة المرتبطة | FK / FK | cond. | return_to_work → an Active hold of the worker; referral → an Open referral (FA-5) | MFH-ANIA-EXP-2026-00015 | sensitive |
| purpose_notice_given | تم إبلاغ العامل بالغرض | bool | Y | must be true (P6-3, `PURPOSE_NOTICE_REQUIRED`) | true | personal |
| name_as_printed / id_entered_for_match / id_match_result | الاسم كما في الشهادة / رقم الهوية للمطابقة / النتيجة | string(120) / transient / enum | cond. | external only; as Phase 4 PC-3/PC-4: the ID is never stored | — | personal (id: sensitive, transient) |
| scan_file | نسخة الشهادة | file (pdf/jpg/png ≤ 5 MB) | cond. | external: required to Submit; encrypted medical bucket (P6-5) | — | **sensitive** |
| clinical_data_present | الشهادة تحتوي بيانات سريرية | bool | cond. | reviewer's answer at review (FA-9) | false | sensitive |
| status | الحالة | enum | Y | §4.3 | accepted | sensitive |
| verification_status | حالة التحقق | enum | sys | `verified` (site clinic, at sign-off) · `not_verified` · `failed` · `unable_to_verify` | verified | sensitive |
| recorded_by / signed_by / signed_at | سجّله / وقّعه الطبيب / وقت التوقيع | FK / FK / timestamptz | sys | signer = examiner.user_id (FA-6) | Grace / Huda | personal |
| submitted_by / reviewed_by / reviewed_at | المقدم / المراجع | FK / FK / timestamptz | sys | external: reviewer ≠ submitter (FA-8) | Ahmed / Huda | personal |
| revoke | الإلغاء | {reason_text ≥ 20, by, at} | N | capability 157 (FA-14) | — | sensitive |

#### 3.6a Assessment line — بند التقييم

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| code | الرمز | FC code | Y | active; examiner class ∈ code.examiner_classes; provider kind ∈ code.provider_kinds | WAH-FIT | sensitive |
| outcome | النتيجة | enum | Y | list OUT | fit | **sensitive** |
| restrictions | القيود الوظيفية | list {code (list RC), value?, text?} | cond. | ≥ 1 iff outcome = fit_with_restrictions (`RESTRICTIONS_REQUIRED`); none otherwise (`RESTRICTIONS_NOT_ALLOWED`) | [{no_work_at_height}] | **sensitive** |
| restriction_review_date | تاريخ مراجعة القيود | date | cond. | required iff any restriction has review_required = true; ≤ examined_on + `restriction_review_max_days` (`REVIEW_DATE_INVALID`) | 2026-12-15 | sensitive |
| unfit_review_date | تاريخ إعادة التقييم | date | cond. | required iff temporarily_unfit; examined_on < date ≤ examined_on + `unfit_review_max_days` | — | sensitive |
| printed_next_due | الاستحقاق المطبوع | date | N | > examined_on | — | sensitive |
| valid_until | صالح حتى | date | sys | §6.1 (stored org default; per-project effective value computed on read) | 2027-09-27 | sensitive |
| limiting_factor | العامل المحدِّد | enum | sys | `printed_next_due` / `code_validity` / `project_override` / `restriction_review` | code_validity | sensitive |
| line_state | حالة البند | enum | sys | `governing` ساري (the latest for the code) · `superseded` مستبدل · `revoked` ملغى · `rejected` مرفوض (§4.3) | governing | sensitive |

### 3.7 Fitness hold — إيقاف لأسباب اللياقة

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| hold_no | رقم الإيقاف | string | sys | `MFH-<project>-<yyyy>-<nnnnn>` | MFH-ANIA-EXP-2026-00027 | none |
| worker_id / project_id | العامل / المشروع | FK / FK | Y | — | WKR-000034 / ANIA-EXP | personal |
| reason | السبب | enum | Y | list HR | referral | **sensitive** |
| source_ref | المرجع | {type: injury_case / referral / manual, id} | Y | — | MFR-ANIA-EXP-2026-00031 | sensitive |
| reason_text | التفاصيل | text(300) | cond. | manual holds: ≥ 20 chars; functional wording (P6-2 hint) | — | sensitive |
| started_at | بداية الإيقاف | timestamptz | sys | creation time; never back-dated (FH-5) | 2026-10-06 08:40 | sensitive |
| status | الحالة | enum | Y | `active` ساري · `released` مرفوع · `cancelled` ملغى (§4.4) | active | sensitive |
| released_at / release_assessment_id | وقت الرفع / التقييم | timestamptz / FK | cond. | released only (FH-3) | — | sensitive |
| cancel_reason / cancelled_by | سبب الإلغاء | text / FK | cond. | ≥ 20 chars, or system code `source_voided` / `source_reclassified` | — | sensitive |
| work_during_hold | عمل أثناء الإيقاف | list {event_type, ref, at} | sys | FH-8 detections | — | sensitive |

### 3.8 Fitness referral — إحالة لتقييم اللياقة

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| referral_no | رقم الإحالة | string | sys | `MFR-<project>-<yyyy>-<nnnnn>` | MFR-ANIA-EXP-2026-00031 | none |
| worker_id / project_id | العامل / المشروع | FK / FK | Y | worker with a Mobilised deployment on the project; scope per RF-2 | WKR-000034 | personal |
| reason | سبب الإحالة | enum | Y | list RR | observed_unwell | **sensitive** |
| note | ملاحظة | text(300) | N | P6-2 hint "Describe what you saw, not a diagnosis / صف ما شاهدته وليس تشخيصاً"; Phase 1 P1-8 ID scan | Dizzy and sweating on level 2 at 08:30 | sensitive |
| remove_from_work | إبعاد عن العمل فوراً | bool | Y | true creates a hold (FH-1b) | true | sensitive |
| raised_by / raised_at | المحيل / الوقت | FK / timestamptz | sys | capability 158 | Fahad / 2026-10-06 08:40 | personal |
| due_at | موعد التقييم | timestamptz | sys | raised_at + `referral_assessment_hours` | 2026-10-07 08:40 | personal |
| status | الحالة | enum | Y | `open` مفتوحة · `assessed` تم التقييم · `cancelled` ملغاة | open | personal |
| assessment_id / assessed_at | التقييم / وقت التقييم | FK / timestamptz | cond. | assessed only; assessed_at = the assessment's accepted_at (sign-off time) | — | sensitive |

### 3.9 Hook policy state (reused) — حالة سياسة المتطلبات

Phase 4 §3.14 entity with `kind` extended to `medical_fitness` (§11.5). There is one row per project for that kind. Its dates come from the 6a settings `medical_hook_*` (§3.12), and the policy actions are 6a capability 164.

### 3.10 Reference lists (seeded EN/AR, codes immutable; the HSE Manager edits labels and may only tighten values)

**EXC — examiner classification:** `occupational_physician` طبيب صحة مهنية (specialist or consultant in occupational medicine) · `physician` طبيب مرخص (any other licensed physician) · `nurse` ممرض/ممرضة (may record, never signs).

**FCAT — fitness code categories:** `general` عامة · `task` مهمة محددة · `surveillance` مراقبة صحية للتعرض.

**OUT — outcomes:** `fit` لائق · `fit_with_restrictions` لائق مع قيود · `temporarily_unfit` غير لائق مؤقتاً · `permanently_unfit` غير لائق نهائياً (for that code).

**AT6 — assessment types:** `pre_placement` قبل التعيين · `periodic` دوري · `return_to_work` العودة للعمل · `referral` بناءً على إحالة · `change_of_task` تغيير المهمة · `post_exposure` بعد التعرض · `exit` عند انتهاء الخدمة.

**RC — functional restriction codes** (`negates` = fitness codes that the restriction makes not_met; `review` = review_required):

| Code | EN / AR | Value | negates | review |
|---|---|---|---|---|
| no_work_at_height | No work at height / لا عمل على ارتفاعات | — | WAH-FIT | yes |
| no_confined_space | No confined-space entry / لا دخول للأماكن المحصورة | — | CSE-ENTRY-FIT | yes |
| no_driving | No driving / لا قيادة | — | DRIVER-FIT | yes |
| no_plant_operation | No operation of cranes or mobile plant / لا تشغيل للرافعات أو المعدات | — | CRANE-OPERATOR-FIT, PLANT-OPERATOR-FIT | yes |
| no_respirator_use | No tight-fitting respirator / لا استخدام لأجهزة التنفس المحكمة | — | RESPIRATOR-FIT | yes |
| no_heat_exposure | No outdoor work in direct sun or hot spaces / لا عمل في الشمس المباشرة أو الأماكن الحارة | — | HEAT-EXPOSURE-FIT | yes |
| no_noise_exposure | No work in noise ≥ 85 dBA / لا عمل في ضوضاء ≥ 85 ديسيبل | — | NOISE-SURV | yes |
| no_radiation_work | No radiation work / لا عمل إشعاعي | — | RAD-WORKER-FIT | yes |
| lifting_limit_kg | Manual lifting limit / حد للرفع اليدوي | int 5–25 kg | — | yes |
| no_night_work | No night work / لا عمل ليلي | — | — | yes |
| no_lone_work | No lone work / لا عمل منفرد | — | — | yes |
| light_duties_only | Light duties only / أعمال خفيفة فقط | — | — | yes |
| requires_corrective_lenses | Must wear corrective lenses / يجب ارتداء النظارات الطبية | — | — | **no** |
| other_functional | Other functional limit / قيد وظيفي آخر | text ≤ 100 (functional wording) | — | yes |

**EG — exposure groups:** `noise_85` ضوضاء ≥ 85 ديسيبل (8-h TWA) · `silica_rcs` غبار السيليكا البلورية القابلة للاستنشاق · `ionising_radiation` إشعاع مؤين · `heat_outdoor` عمل خارجي في الحرارة (reserved for 6b; no 6a line uses it).

**HR — hold reasons:** `rtw_after_injury` عودة بعد إصابة · `heat_illness` إجهاد حراري · `referral` إحالة مع إبعاد عن العمل · `manual` إيقاف يدوي لمخاوف اللياقة.

**RR — referral reasons:** `observed_unwell` ظهرت عليه أعراض مرضية · `heat_illness_episode` نوبة إجهاد حراري · `self_reported` بلاغ ذاتي من العامل · `return_after_absence` عودة بعد غياب · `post_incident_no_injury` بعد حادث دون إصابة مسجلة · `certificate_restriction` قيد طبي مذكور في بطاقة كفاءة (Phase 4 PC-13) · `supervisor_concern` ملاحظة المشرف · `other` أخرى.

**TST — typical tests (informational):** `history_questionnaire` · `vision_acuity` · `colour_vision` · `depth_perception` · `audiometry` · `spirometry` · `chest_xray` · `cardio_exam` · `blood_pressure` · `balance_vertigo_screen` · `claustrophobia_screen` · `respirator_questionnaire` · `blood_count` · `musculoskeletal_exam` (EN/AR in the i18n files). Results are never recorded.

**FC — fitness code catalogue (seed, org-wide)**. Validity in months; ★ = critical (§3.12):

| Code | EN / AR | Cat. | Valid. | Examiner | Providers | Hook use (attach points, §5.7a HK6-2) |
|---|---|---|---|---|---|---|
| GEN-FIT | General fitness for construction work / اللياقة العامة لأعمال البناء | general | 24 ASSUMPTION `VERIFY` R2 | occ. phys., physician | site, external, contractor (own tree) | Phase 2 project hook (site gates, every zone, PTW crew via ZP-4 step 8) |
| WAH-FIT | Working at height fitness / اللياقة للعمل على ارتفاعات | task | 12 ASSUMPTION | occ. phys., physician | site, external | Phase 3 every crew member on a work-at-height section |
| CSE-ENTRY-FIT ★ | Confined space entry fitness / اللياقة لدخول الأماكن المحصورة | task | 12 `VERIFY` R13 | occ. phys., physician | site, external | Phase 3 entrant (existing CS-3), rescue_lead, rescue_member |
| CRANE-OPERATOR-FIT ★ | Crane operator physical qualification / اللياقة البدنية لمشغل الرافعة | task | 12 `VERIFY` R8, R13 | occ. phys., physician | site, external | Phase 3 crew role crane_operator and operator binding of crane categories; Phase 2 Z-TC01 for trade crane_operator |
| PLANT-OPERATOR-FIT | Mobile plant / MEWP / hoist operator fitness / لياقة مشغلي المعدات المتحركة | task | 24 ASSUMPTION | occ. phys., physician | site, external | Phase 3 operator binding of hoist, MEWP, forklift, telehandler, excavator, wheel loader, piling rig, concrete pump boom |
| DRIVER-FIT | Driver fitness (heavy and airside vehicles) / لياقة السائقين | task | 24 `VERIFY` R12 | occ. phys., physician | site, external | Phase 2 ADP categories apron, manoeuvring; Phase 3 crew role driver |
| RESPIRATOR-FIT ★ | Respirator user medical evaluation / التقييم الطبي لمستخدم جهاز التنفس | task | 12 ASSUMPTION (R7 sets no fixed interval) | occ. phys., physician | site, external | Phase 3 rescue_lead, rescue_member |
| HEAT-EXPOSURE-FIT | Fitness for work in hot environments / اللياقة للعمل في البيئات الحارة | task | 12 | occ. phys., physician | site, external | none in 6a (6b) |
| NOISE-SURV | Hearing conservation audiometry / فحص السمع ضمن برنامج المحافظة على السمع | surveillance | 12 (R7) | occ. phys., physician | site, external | none (KPI line only) |
| SILICA-SURV | Respirable silica health surveillance / المراقبة الصحية للتعرض للسيليكا | surveillance | 36 (R7) | occ. phys., physician | site, external | none (KPI line only) |
| RAD-WORKER-FIT ★ | Radiation worker health surveillance / المراقبة الصحية للعاملين في الإشعاع | surveillance | 12 `VERIFY` R9 | **occ. phys. only** ASSUMPTION | site, external | Phase 3 crew roles radiographer and rpo |

Every code is disjoint from Phase 4 list PCT and the Phase 5 catalogue (for example `CRANE-OPERATOR-FIT` ≠ `CRANE-OPERATOR`, and `WAH-FIT` ≠ `WAH`).

### 3.11 Import batch — دفعة استيراد سجلات اللياقة
Same fields and lifecycle as Phase 5 §3.13, with these differences:
- template `fitness_records` only;
- source `clinic_register_file` (OH Practitioner / HSE Manager only; evidence = the clinic's email from one of its verification domains, or for a site clinic the clinic manager's signed export) or `contractor_file` (Contractor HSE Rep);
- no scans zip;
- the uploaded file is **sensitive** (it holds outcomes) and is stored encrypted, then deleted at commit, discard or expiry (IM6-4).

### 3.12 Phase 6a project settings
These extend Phase 0 §3.9, Phase 1 §3.10, Phase 2 §3.22, Phase 3 §3.17, Phase 4 §3.17 and Phase 5 §3.16. Only the HSE Manager edits them; every change is audited; "Allowed" is the only range accepted.

| Key | AR label | Type | Default | Allowed |
|---|---|---|---|---|
| medical_register_from | بدء العمل بسجل اللياقة | date / null | null; set when the site clinic starts recording on the platform | ≥ project start; ≤ today; once set, it may only move earlier |
| fitness_validity_months | مدة صلاحية رموز اللياقة للمشروع | map code → int | catalogue | 1 … catalogue value (shorten only) |
| medical_hook_transition_days | المرحلة الانتقالية لمتطلبات اللياقة | int | 30 ASSUMPTION (as Phases 4/5) | 0–30 |
| medical_hook_critical_transition_days | المرحلة الانتقالية للرموز الحرجة | int | 7 | 0–7 |
| medical_hook_critical_codes | رموز اللياقة الحرجة | code[] | CSE-ENTRY-FIT, CRANE-OPERATOR-FIT, RESPIRATOR-FIT, RAD-WORKER-FIT | add only |
| unverified_fitness_acceptance_hours | قبول الشهادة الخارجية قبل التحقق | int | **0** | 0–24; never for critical codes |
| fitness_verification_due_days | مهلة التحقق من الشهادة | int | 3 | 1–14 |
| referral_assessment_hours | مهلة تقييم الإحالة (ساعات) | int | 24 ASSUMPTION | 4–72 |
| signoff_due_hours | مهلة توقيع الطبيب (ساعات) | int | 72 | 24–72 |
| assessment_backdate_max_days | أقصى مدة لتسجيل فحص سابق | int | 7 | 0–14 |
| restriction_review_max_days | أقصى مدة للقيود قبل المراجعة | int | 90 ASSUMPTION | 30–180 |
| unfit_review_max_days | أقصى مدة لعدم اللياقة المؤقت قبل إعادة التقييم | int | 90 | 14–180 |
| medical_line_max_due_days | أقصى مهلة لبند الخطة | int | 30 (R7 silica) | 0–30 |
| rtw_hold_case_categories | تصنيفات الإصابة التي توجب إيقافاً حتى التقييم | case_category[] | [LTI, RWC, JTC] | add only (MTC, FAC may be added) |
| heat_illness_natures | طبائع الإصابة الحرارية | nature[] | [heat_exhaustion, heat_stroke] | add only |
| exposure_group_trade_defaults | مجموعات التعرض الافتراضية حسب المهنة | map EG → trade[] | noise_85: [plant_operator, welder]; silica_rcs: [mason]; ionising_radiation: []; heat_outdoor: [] | add only |
| medical_compliance_warning_pct | حد إنذار الامتثال الطبي | decimal | 98.0 ASSUMPTION | 80.0–100.0 |
| health_cell_min | الحد الأدنى لحجم الخلية الإحصائية | int | 5 | 5–10 |
| fitness_scan_retention_months | الاحتفاظ بصور الشهادات | int | 12 ASSUMPTION | 6–24 |
| fitness_record_retention_years | الاحتفاظ بنتائج اللياقة | int | 10 ASSUMPTION `VERIFY` R1/R4 | 5–30 |
| surveillance_record_retention_years | الاحتفاظ بنتائج المراقبة الصحية | int | 30 `VERIFY` R4/R7 | 10–40 |
| worker_purpose_notice_version | إصدار إشعار الغرض للعامل | string | supplied by client/legal (§10 Q4) | — |
| alert_schedule_long_days | جدول التنبيهات | int[] | [30, 14, 7, 0] | — |

## 4. Workflow / states

"Who" = capability numbers (§5.15). Every transition is audited with before and after values (Phase 0 rule 35). Audit diffs of sensitive fields are readable only by capability 157 holders. "Job" means the scheduler job `medical_daily` at 00:06:30 Asia/Riyadh (after `training_daily`) or `medical_minute`, which runs every 60 s.

### 4.1 Medical provider
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Draft | مسودة | 148 | Create |
| Draft → Pending Approval | بانتظار الاعتماد | 148 | MOH licence fields complete; licence_checked_at set (MP-2) |
| Pending Approval → Approved | معتمدة | 149 | Licence valid today |
| Pending Approval → Draft | مسودة | 149 | Returned with a comment |
| Approved → Suspended → Approved | موقوفة / معتمدة | 149 | Reason. Job: licence_valid_until passed → Suspended `licence_expired` |
| Approved/Suspended → Blacklisted | محظورة | 149 | Reason and scope (MP-6); "lift blacklist" → Suspended |

### 4.2 Examiner registration
- — → Active: created by 148 with licence_checked_at set.
- Active → Suspended → Active: 149, with a reason.
- Active/Suspended → Withdrawn: 149, reason; terminal.
- Active → Expired: job, when today > licence_valid_until; terminal. A renewed licence makes a new registration (EX-4).

### 4.3 Fitness assessment
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Draft | مسودة | 152 (site clinic) · 153 (external) · 161 (import) | Create |
| Draft → Awaiting Sign-off | بانتظار توقيع الطبيب | 152 | Site clinic; recorder is not the examiner's linked user (FA-6) |
| Draft → Accepted | مقبول | 152 | Site clinic; recorder is the examiner's linked user (signs on save, with step-up re-auth, DECISIONS #56); verification `verified` (method `site_clinic_record`) |
| Awaiting Sign-off → Accepted | مقبول | the examiner's linked user (152) | Signature + re-auth; verified |
| Awaiting Sign-off → Draft | مسودة | the examiner's linked user | Returned with a comment ≥ 10 chars |
| Draft → Submitted | مُقدَّم | 153 | External: scan attached, FA-1…FA-5 and FA-10 pass |
| Submitted → Draft | مسودة | 154 | Returned with a comment ≥ 10 chars |
| Submitted → Accepted | مقبول | 154 (≠ submitter) | Document review (FA-8); in force only once verified (FV-1) |
| Submitted → Rejected | مرفوض | 154; System | Reason; `CLINICAL_DATA_IN_SCAN` (FA-9) or verification failed (FV-5); terminal |
| Accepted → Revoked | ملغى | 157; System (FV-5 after acceptance; MP-6 blacklist) | Reason ≥ 20 chars; terminal; every line `revoked` |

Line states (derived on save of any assessment of the worker, §6.2): the latest Accepted, non-revoked line per (worker, code) by examined_on (ties: later accepted_at) is `governing`; older lines are `superseded`. Expiry is not a state; it is computed from valid_until (§6.6).

### 4.4 Fitness hold
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Active | ساري | System (FH-1a, FH-1b) · 159 (FH-1c) | Injury case trigger, referral with removal from work, or a manual hold |
| Active → Released | مرفوع | System | An Accepted assessment meeting FH-3 |
| Active → Cancelled | ملغى | 159 (OH Practitioner, HSE Manager); System | Reason ≥ 20 chars; System codes `source_voided` (case or incident Voided, worker link removed) and `source_reclassified` (case leaves the trigger set before release, FH-4) |

### 4.5 Referral
- Open → Assessed: system, when a linked assessment of type `referral` is Accepted (RF-4).
- Open → Cancelled: the referrer before the due time when remove_from_work = false; otherwise 159 only. A reason ≥ 20 chars is required (RF-5).
- "Overdue" is derived: now > due_at and status Open.

### 4.6 Hook policy for kind `medical_fitness`
Phase 4 §4.8 applies unchanged with kind medical_fitness:
- Stage 0 `warn` (no provider; Phase 2 HK-4 `HOOK_NOT_AVAILABLE`) → Stage 1 `transition`: capability 164 (enable medical hooks, HK6-1).
- Stage 1 → Stage 2 `block` for critical codes: system at critical_block_from 00:00:30, or 164 earlier.
- Stage 1 → Stage 2 `block` for all codes: system at general_block_from 00:00:30, or 164 earlier.
- One deferral of general_block_from, ≤ 30 days, reason ≥ 30 chars, never for critical codes.
- Stage 2 → any earlier stage: not allowed (`HOOK_POLICY_LOOSENING`).

Hard stops (HK6-3) block in every stage.

### 4.7 Import batch
As Phase 1 §3.2: Uploaded → Validated (dry-run) → Committed / Discarded; Validated → Expired after 60 min.

## 5. Business rules

### 5.1 Role and access tiers (OH)
- OH-1. The role `oh_practitioner` is assigned by the HSE Manager only (rule 14 extension). Users of this role hold no capability of Phases 1–5 except those listed in §11.1.
- OH-2. **Access tiers for fitness data.** Each tier includes the one before it.
  - **Tier 1 — status (capability 155):** per requirement, met / expiring / due / not cleared, the valid_until date and the generic text "Not eligible — HSE check / غير مؤهل — مراجعة السلامة".
  - **Tier 2 — functional (capability 156):** + the outcome category, the active restriction codes and values, hold yes/no, the review dates, and the kind and code on Phase 2/3 hook results.
  - **Tier 3 — clinical-administrative (capability 157):** + hold, referral and assessment reasons and texts, assessment type, provider and examiner, scan access (with 160), verification outcomes and the hook reason_code.

  The API omits fields above the caller's tier (Phase 0 P4). Every tier-2 or tier-3 read writes `sensitive_field_read` with the field names.
- OH-3. The HSE Manager's org-wide grant **excludes capability 152** (recording clinical assessments), as DECISIONS #55. `Me.org_capabilities` omits it.
- OH-4. A physician signs only through their own linked user. No other role can create an Accepted site-clinic assessment.

### 5.2 Catalogue (MC)
- MC-1. The catalogue is org-wide. Only the HSE Manager (147) creates or edits codes. Codes are immutable. A code in use cannot be deleted, only made inactive.
- MC-2. A new code must not exist in Phase 4 list PCT or the Phase 5 course catalogue, and no later Phase 4/5 code may reuse a 6a code (`CODE_IN_OTHER_CATALOGUE`, checked both ways as DECISIONS #96).
- MC-3. Edits may only tighten. Allowed: a shorter validity, fewer examiner classes, fewer provider kinds, a restriction added to another code's `negates`. Anything else gives `CATALOGUE_LOOSENING`. A shorter validity recomputes every line's stored valid_until, and the workers who now expire within 30 days are alerted (as Phase 5 CC-2).
- MC-4. `contractor_clinic` may be allowed only for category general codes (`PROVIDER_KIND_NOT_ALLOWED`).
- MC-5. Project overrides (`fitness_validity_months`) only shorten validity.

### 5.3 Providers (MP) and examiners (EX)
- MP-1. HSE Officers and OH Practitioners (148) create and submit providers. Only the HSE Manager (149) approves, suspends or blacklists them.
- MP-2. Approval requires `licence_checked_at` / `licence_checked_by` (the MOH licence was checked against the MOH register, `VERIFY` R5) and licence_valid_until ≥ today.
- MP-3. **Acceptability** of a provider for a line (code C, worker W, date d = examined_on) needs all of:
  - (a) status Approved on d, and not suspended or blacklisted from a date ≤ d;
  - (b) licence_valid_until ≥ d;
  - (c) provider kind ∈ C.provider_kinds;
  - (d) site_clinic: the assessment's project ∈ project_ids;
  - (e) contractor_clinic: W has a deployment on the project under an engagement of that contractor or its descendants (independence, as Phase 5 PV-3c).

  Otherwise 422 `MEDICAL_PROVIDER_NOT_ACCEPTABLE` with meta reason ∈ {`PROVIDER_NOT_APPROVED`, `PROVIDER_SUSPENDED`, `PROVIDER_BLACKLISTED`, `LICENCE_INVALID`, `PROVIDER_KIND_NOT_ALLOWED`, `NOT_PROJECT_CLINIC`, `NOT_OWN_TREE`}.
- MP-4. A suspended provider's existing accepted lines stay in force. New lines examined on or after the suspension date are refused.
- MP-5. Licence expiry alerts at 30 / 14 / 7 / 0 days; at expiry the job suspends the provider (`licence_expired`).
- MP-6. **Blacklist:** scope `all_records` revokes every assessment of the provider; `issued_from` revokes those examined on or after blacklist_from. Revocation is a hard stop within 60 s, and the OH Practitioners receive the list of affected workers for re-examination (as Phase 5 PV-6).
- EX-1. An examiner registration counts only with licence_checked_at set (SCFHS register check, `VERIFY` R5).
- EX-2. On examined_on the examiner must be Active, have licence_valid_until ≥ examined_on, belong to the assessment's provider, and have classification ∈ the code's examiner_classes. Errors: `EXAMINER_LICENCE_INVALID` / `EXAMINER_NOT_QUALIFIED`.
- EX-3. Classification `nurse` can never sign a line (`EXAMINER_NOT_QUALIFIED`).
- EX-4. A licence renewal is a new registration. Lines signed under the old one keep their validity.
- EX-5. Examiner licence expiry alerts at 30 / 14 / 7 / 0 days to the OH Practitioners and HSE Officers. Assessments still awaiting that examiner's sign-off are flagged.

### 5.4 Requirement plan (MR) and worker health profiles (WP)
- MR-1. Each project has one requirement plan (§3.4). Manual lines are edited by capability 150. Every version is kept; lines cannot be back-dated.
- MR-2. **Hook-derived lines** are kept in step automatically with the `medical_fitness` attach points of the project:
  - the Phase 2 project hook list → `project_hook` (H, kpi_counted);
  - Phase 2 zone profiles → `zone` (H, kpi_counted);
  - Phase 2 ADP categories → `adp_category` (H, kpi_counted);
  - Phase 3 crew roles and operator bindings → `crew_role` / `operator_binding` (E, enforcement-only, kpi_counted = false).

  Derived lines are read-only (`LINE_DERIVED_FROM_HOOK`) and have due_within_days 0.
- MR-3. **Applicability** of a kpi_counted line to a deployment at as_of follows Phase 5 MX-4. In addition, `exposure_group` → profile.exposure_groups ∩ values ≠ ∅ at as_of, and `project_hook` → always. The KPI population is contractor_worker deployments only. Client/PMC staff are evaluated and shown, but not counted.
- MR-4. Due date and de-duplication follow Phase 5 MX-5 and MX-6 (§6.3).
- MR-5. Removing a manual line, or raising its due_within_days, needs the HSE Manager and a reason ≥ 20 chars (`PLAN_LOOSENING` for others).
- MR-6. **No exemptions.** A requirement that does not fit a worker is removed by changing the exposure group or trade that triggers it, which is audited (`EXEMPTION_NOT_ALLOWED` on any exemption call).
- WP-1. When a deployment becomes Mobilised, its exposure_groups are set from `exposure_group_trade_defaults` for its trade. Capability 151 edits them later. A Contractor HSE Rep edits only C-scope deployments. Changes apply from today (no back-dating).
- WP-2. Removing an exposure group while a surveillance line for it is `gap` needs a reason ≥ 20 chars and alerts the OH Practitioner (it might hide a missed exam).

### 5.5 Fitness assessments (FA)
- FA-1. The worker is a Phase 2 worker, not Anonymised, with a non-demobilised deployment on the project. A pre-placement assessment may precede mobilisation (deployment Pending Induction). A Contractor HSE Rep submits only for C-scope workers.
- FA-2. examined_on ≤ today. Site-clinic records need examined_on ≥ today − `assessment_backdate_max_days` (`BACKDATED_ASSESSMENT`). An external certificate whose every line's valid_until < today is rejected `FITNESS_ALREADY_EXPIRED`. 157 holders may attach it as historic, which is never in force.
- FA-3. There are 1 to 11 lines, at most one per code (`DUPLICATE_CODE_LINE`). Each line passes MP-3 and EX-2. Outcome rules:
  - fit_with_restrictions needs ≥ 1 restriction and, when any restriction has review_required, a restriction_review_date ≤ examined_on + `restriction_review_max_days`;
  - temporarily_unfit needs an unfit_review_date ≤ examined_on + `unfit_review_max_days`;
  - permanently_unfit needs examiner classification occupational_physician (`EXAMINER_NOT_QUALIFIED`) ASSUMPTION;
  - fit and the unfit outcomes carry no restrictions.
- FA-4. A `restriction` of code other_functional must be ≤ 100 chars, and the UI shows the hint "Functional limit only — no diagnosis / قيد وظيفي فقط — دون تشخيص". The Phase 1 P1-8 ID scan applies.
- FA-5. A `return_to_work` assessment must reference an Active hold of the worker with reason rtw_after_injury or heat_illness. A `referral` assessment must reference an Open referral. Either must include a GEN-FIT line, with examined_on ≥ the local date of the hold or referral start (`HOLD_REFERENCE_INVALID`).
- FA-6. **Site-clinic recording and sign-off:** the recorder holds capability 152. When the recorder is the examiner's linked user, saving signs the assessment, with step-up re-auth (DECISIONS #56), and it becomes Accepted and verified. Otherwise it waits in Awaiting Sign-off until the examiner's linked user signs (re-auth). An examiner without a linked user cannot sign on the platform, so their findings are entered as an external certificate (scan) instead (`EXAMINER_NOT_LINKED`). Sign-off is due within `signoff_due_hours`.
- FA-7. `purpose_notice_given` must be true (`PURPOSE_NOTICE_REQUIRED`, P6-3).
- FA-8. **External certificates:** the scan is required to Submit. The reviewer (154) ≠ the submitter (`SOD_CONFLICT`, 422 as DECISIONS #43). A Contractor HSE Rep cannot review.
- FA-9. **Clinical data in a scan:** the reviewer must answer `clinical_data_present`. When true, the assessment is Rejected `CLINICAL_DATA_IN_SCAN`, the scan is deleted within 60 s (audited `retention_purge` with reason `clinical_data`), and the submitter is told to obtain the platform's fitness certificate form (§8.4), which carries outcomes and functional restrictions only.
- FA-10. (provider, certificate_no) is unique (`CERT_EXISTS`). The same number presented for another worker gives 409 `CERT_NO_REUSED` and alerts the OH Practitioners. Identity is matched as Phase 4 PC-3/PC-4: the name is compared, and a typed ID is checked through the blind index, never stored (`CERT_ID_MISMATCH`, audited with the masked value).
- FA-11. **Governing line:** per (worker, code), the latest Accepted non-revoked line by examined_on (ties: later accepted_at) governs, *whatever its outcome*. A newer unfit outcome therefore replaces an older fit one at once, and a newer fit outcome ends an older unfit one, subject to FA-12.
- FA-12. **Second opinion after permanent unfitness:** after a governing permanently_unfit line for code C, a new fit or fit_with_restrictions line for C needs an examiner of class occupational_physician who did not sign the permanently_unfit line (`SECOND_OPINION_REQUIRED`) ASSUMPTION. The HSE Manager is notified with no detail.
- FA-13. Lines never carry pending results. If results are awaited, nothing is recorded and the worker stays not cleared (minimisation, testability).
- FA-14. Assessments are never deleted. An Accepted assessment cannot be edited after 24 h. A correction means Revoke (157, reason ≥ 20 chars) plus a new assessment.
- FA-15. Assessments follow the worker org-wide (as Phase 5 TR-16). Each project applies its own validity override on read (§6.1).
- FA-16. A Phase 2 worker ban, or Phase 4/5 suspensions, never change assessments. An unfit outcome never bans, suspends or demobilises a worker by itself (no automated employment decision, P6-11).

### 5.6 Verification of external certificates (FV)
- FV-1. An external line is in force only when the assessment's verification_status is `verified`. The exception is the first `unverified_fitness_acceptance_hours` after Accept (default 0, so never), and the exception never applies to critical codes (`MEDICAL_UNVERIFIED`).
- FV-2. The verifier holds capability 154, is not the submitter and is not employed by the worker's employer (`SOD_CONFLICT`).
- FV-3. Channels: the provider's registered portal, domain email or phone (`CHANNEL_NOT_REGISTERED` otherwise). The server never fetches external URLs (as Phase 4 VF-4). Seeing the original certificate does not verify it.
- FV-4. `no_response` twice, ≥ 24 h apart, gives `unable_to_verify` and alerts the HSE Manager. The certificate is not in force.
- FV-5. `not_found`, `details_differ` or `revoked_by_clinic` gives `failed`: Submitted → Rejected, or Accepted → Revoked `verification_failed`. It is a hard stop when it was the latest line for a code (HK6-3). The OH Practitioners and the HSE Manager are alerted. The action panel asks for a decision (provider review, or a Phase 2 worker ban prompt only, never automatic).
- FV-6. Site-clinic assessments are verified at sign-off (method `site_clinic_record`).

### 5.7 Fitness holds (FH)
- FH-1. **Creation:**
  - (a) **Injury case:** a Phase 1 injury case with `worker_id` set, at the first moment its case_category (derived or confirmed) ∈ `rtw_hold_case_categories`, or its nature ∈ `heat_illness_natures` (any category, including FAC), creates a hold with reason `rtw_after_injury` or `heat_illness` (heat wins when both apply). The source is the case. There is one hold per case.
  - (b) **Referral:** a referral with remove_from_work = true creates a hold with reason `referral`.
  - (c) **Manual:** capability 159 creates a hold with reason `manual` and reason_text ≥ 20 chars.

  A worker may have several Active holds. Each needs its own release.
- FH-2. **Effect:** while any hold of the worker is Active, every `medical_fitness` hook check for that worker on any project returns not_met with hard_stop = true and reason `MEDICAL_HOLD` (HK6-6 step 3). Phase 2 then denies at site gates and zone gates (`HOOK_NOT_MET`, §11.3), and Phase 3 blocks crew lines and suspends live permits per HK3-5.
- FH-3. **Release:** an assessment that becomes Accepted releases a hold when all of the following hold:
  - it is of type `return_to_work` (holds `rtw_after_injury` / `heat_illness`) or `referral` (holds `referral`, via its referral), or of either type for a `manual` hold;
  - it references the hold (FA-5);
  - examined_on ≥ the local date of started_at;
  - its GEN-FIT line is fit or fit_with_restrictions.

  released_at = the assessment's accepted_at. A GEN-FIT temporarily or permanently unfit outcome also closes the hold (status Released, with the unfit line now governing as a hard stop). Any other attempt gives `HOLD_RELEASE_REQUIRES_ASSESSMENT`.
- FH-4. **Cancellation:** by 159 with a reason ≥ 20 chars, or by the system when the source case or incident is Voided or the worker link is removed (`source_voided`), or when an injury-case hold's case leaves both trigger sets before release (`source_reclassified`).
- FH-5. started_at = the creation time. It is never back-dated, even when the injury case is entered late.
- FH-6. Tiering: hold existence is tier 2 (156) and the reason is tier 3 (157). Every other surface shows "Not eligible — HSE check / غير مؤهل — مراجعة السلامة".
- FH-7. Holds never demobilise, ban or suspend a deployment.
- FH-8. **Work during hold** (for K-94, E15 and the alerts) is detected when any of these happens between started_at and released_at (or now):
  - (a) a Phase 2 gate check, direction `in`, with result GRANTED or GRANTED_WITH_WARNING, or with `admitted_despite_denial` = true, at any gate of a project where the worker has a deployment;
  - (b) the worker is in `crew_present` of a Phase 3 permit shift that started in the interval;
  - (c) for injury-case holds, the case's Phase 1 rtw_date < the local date of released_at (or the hold is still Active).

  Each detection is appended to `work_during_hold`, and the OH Practitioners and the HSE Manager are alerted at once (when the detection happens live).

### 5.8 Referrals (RF)
- RF-1. Raised by capability 158 with a reason (list RR), an optional note (tier 3) and remove_from_work.
- RF-2. Scope: a Permit Receiver may refer only workers of their own engagement (C1); a Contractor HSE Rep, C-scope workers; site engineers and permit issuers, workers deployed to their sites; HSE Officers and OH Practitioners, any worker on their projects.
- RF-3. due_at = raised_at + `referral_assessment_hours`. The OH Practitioners get an in-app, email and SMS alert at once when remove_from_work = true (in-app and email otherwise), and again at due_at − 2 h if still Open.
- RF-4. A referral is Assessed when a `referral` assessment referencing it becomes Accepted (FA-5). assessed_at = accepted_at.
- RF-5. Cancellation: by the referrer before due_at only when remove_from_work = false; otherwise by 159 only. A reason ≥ 20 chars is required.
- RF-6. A referral with reason `heat_illness_episode` returns warning `INCIDENT_RECORD_EXPECTED` and pre-fills a Phase 1 incident draft link (illness, nature unspecified). The referral is saved anyway, and the platform never creates the incident itself.
- RF-7. When 6a hooks are enabled on a project, every Phase 4 personnel certificate with `medical_restriction_on_card` = true that has no "restriction reviewed" record creates a referral with reason `certificate_restriction` and remove_from_work = false. From then on, Phase 4 PC-13 is answered by the OH Practitioner (§11.6).

### 5.9 Return to work (RW)
- RW-1. For an injury-case hold, an OH Practitioner holding the Phase 1 capabilities 29–30 (§11.1) sees the case ref, category, dates and medical fields in Phase 1. 6a copies none of them.
- RW-2. When a Phase 1 user saves an rtw_date earlier than the release date of the case's hold, or saves it while the hold is still Active, Phase 1 shows warning `RTW_BEFORE_CLEARANCE` and saves anyway (Phase 1 records facts). FH-8c records the breach.
- RW-3. When the releasing assessment of an `rtw_after_injury` hold is fit_with_restrictions, the incident's HSE Officer receives the prompt "Check whether restricted-work days apply to case <case_no> (OSHA 1904.7(b)(4)) / تحقق من أيام العمل المقيد". This is a prompt only; 6a never changes the case.
- RW-4. Heat-illness holds of 6a are the "heat-illness log" that 6b will analyse. 6a stores no temperatures and no clinical details.

### 5.10 Hook provider and the warn → block transition (HK6)
- HK6-1. **Provider registration:** the HSE Manager enables medical hooks on a project (capability 164). This requires `medical_register_from` set and ≤ today (`MEDICAL_REGISTER_NOT_LIVE`), at least one Approved site_clinic or external_clinic serving the project (`NO_MEDICAL_PROVIDER`), and the readiness report shown first (HK6-9). provider_registered_on = that local date. From then on, Phase 2 no longer returns `HOOK_NOT_AVAILABLE` for kind medical_fitness on the project, and the Phase 2 setting `hook_policy.medical_fitness` is superseded by the hook policy state (§11.3).
- HK6-2. **Codes implemented:** the 11 catalogue codes. Any other code gives `unknown_code` (a configuration error for the HSE Manager; not_met under block). These **default attach points** are seeded on enable; the HSE Manager may edit them, tighten only:
  - Phase 2 project hook list: GEN-FIT;
  - Phase 2 Z-TC01 zone profile, for trade crane_operator: CRANE-OPERATOR-FIT;
  - Phase 2 ADP categories apron and manoeuvring: DRIVER-FIT;
  - Phase 3 crew roles: entrant, rescue_lead and rescue_member → CSE-ENTRY-FIT; rescue_lead and rescue_member → RESPIRATOR-FIT; every crew member on a work_at_height section → WAH-FIT; crane_operator → CRANE-OPERATOR-FIT; driver → DRIVER-FIT; radiographer and rpo → RAD-WORKER-FIT;
  - Phase 3 operator binding (HK4-9): crane categories (tower, mobile, crawler, loader, overhead/gantry) → CRANE-OPERATOR-FIT; construction_hoist, mast_climber, bmu, mewp, forklift, telehandler, excavator, wheel_loader, piling_rig and concrete_pump_boom → PLANT-OPERATOR-FIT.
- HK6-3. **Hard stops** (`not_met`, hard_stop = true; they block in every stage):
  - an Active hold;
  - a governing GEN-FIT line that is temporarily or permanently unfit (applies to every code);
  - a governing line for the code that is temporarily unfit (including after its review date) or permanently unfit;
  - an active restriction that negates the code;
  - no line in force for the code while the latest line for it was Revoked or failed verification.

  Rationale: positive knowledge that the person must not do the work.
- HK6-4. **Stages** follow Phase 4 HK4-4. In transition, a not_met without hard_stop is returned as `warn` (`HOOK_NOT_MET_WARN`, with the detail reason kept), and met and expiring pass through. Under block, not_met and unknown_code block: Phase 2 `HOOK_NOT_MET`, Phase 3 blocker `HOOK_NOT_MET` / `KEY_ROLE_INELIGIBLE`, and live permits are Suspended `hook_not_met` within 60 s.
- HK6-5. **Switch dates:** critical codes block from provider_registered_on + `medical_hook_critical_transition_days`; all others from + `medical_hook_transition_days`. The switch runs automatically at 00:00:30 and is audited and alerted. The HSE Manager may switch early (164). One deferral of general_block_from is allowed (≤ 30 days, reason ≥ 30 chars). Critical codes cannot be deferred (`CRITICAL_CODE_NO_DEFERRAL`); a second deferral gives `DEFERRAL_USED`; block → warn gives `HOOK_POLICY_LOOSENING`.
- HK6-6. **Check algorithm** — `check(subject_type = worker, subject_id, kind = medical_fitness, code, at, context)`, with d = local date(at). The first step that applies decides:
  1. The worker does not exist or is Anonymised → not_met `WORKER_UNKNOWN`.
  2. The code is unknown → `unknown_code`.
  3. An Active hold → not_met `MEDICAL_HOLD`, hard stop.
  4. The governing GEN-FIT line is temporarily or permanently unfit → not_met `MEDICAL_UNFIT`, hard stop.
  5. The code's governing line:
     - none: not_met `MEDICAL_PENDING_REVIEW` when a Submitted or Awaiting Sign-off line exists; `MEDICAL_UNVERIFIED` when an Accepted line is not yet verified; `MEDICAL_REVOKED` / `MEDICAL_VERIFICATION_FAILED` (hard stop) when the latest line was revoked or failed; otherwise `MEDICAL_MISSING`;
     - outcome temporarily or permanently unfit → not_met `MEDICAL_UNFIT`, hard stop.
  6. Any restriction in force at d negates the code → not_met `RESTRICTION_CONFLICT`, hard stop, with meta restriction code.
  7. d > the effective valid_until → not_met `MEDICAL_REVIEW_DUE` when limiting_factor = restriction_review, otherwise `MEDICAL_EXPIRED`.
  8. `met` when valid_until > d + 7, otherwise `expiring`. conditions[] = the non-negating restrictions in force at d ({code, value}).

  Result: {status, valid_until, ref (assessment_no), reason_code, hard_stop, conditions[]}. Subject types `vehicle` and `equipment_tag` → `unknown_code`.
- HK6-7. **Display by callers:**
  - kind and code are shown to capability 156 holders, and the reason_code to 157 holders only;
  - everyone else sees "Not eligible — HSE check / غير مؤهل — مراجعة السلامة" (not_met), "HSE check due / مراجعة السلامة مستحقة" (warn) or "Work restriction applies — ask your supervisor / يوجد قيد على العمل — راجع المشرف" (met with conditions);
  - gate screens never show the word "medical" (GC-7 extension, §11.3);
  - gate logs store reason `HOOK_NOT_MET` / `HOOK_NOT_MET_WARN` with the kind only, never the medical reason code (P6-7).

  This supersedes DECISIONS #79's use of capability 56.
- HK6-8. **Events:** 6a publishes `medical.fitness_changed` (an assessment accepted, revoked or expired; a line superseded; verification changed), `medical.hold_changed`, `medical.provider_changed` and `hook_policy.changed` (kind medical_fitness), at least once within 60 s. Phases 2 and 3 re-evaluate affected credentials, WAPs and permits (as HK4-10 / HK5-8). Cached results (≤ 60 s) are cleared on these events. The daily job publishes `medical.fitness_changed` for each line that expired, and for each restriction or unfit review date reached, at 00:06:30.
- HK6-9. **Readiness report** (capability 162; names per tier), as Phase 5 HK5-9: per code, the subjects requiring it, met / expiring counts, the not-met list with reason category (tier 1: "not cleared"; tier 2+: outcome category; tier 3: reason), and a preview of affected gates, WAPs and permits.
- HK6-10. Phases 2 and 3 are otherwise unchanged: PT-8 evaluation times, and LF-5 / HK3-3 "valid_until must cover the shift's planned end".

### 5.11 Imports (IM6)
- IM6-1. One template, `fitness_records`: header in EN or AR, any column order, case-insensitive; `.csv` (UTF-8) or `.xlsx`, ≤ 5 MB, ≤ 5,000 rows; dry-run first; commit only a Validated batch ≤ 60 min old.
- IM6-2. **Columns:** worker_no or (id_type, id_number[, passport_country]); project_code, provider_code, examiner_no, assessment_type, examined_on, certificate_no, code, outcome, restrictions (`code[:value];…`), restriction_review_date, unfit_review_date, printed_next_due. Rows that share (provider_code, certificate_no) form one assessment.
- IM6-3. `clinic_register_file` (157 holders only): committed assessments are Accepted. They are verified when the evidence matches the provider (a domain email for external clinics; a signed export for the site clinic), with method `clinic_register_file`, and are dated per row. `contractor_file` (C): committed assessments are Submitted, need review (FA-8) and verification, and have no scan (the scan must be added before Submit, so they stay Draft).
- IM6-4. Files are sensitive: stored encrypted, deleted at commit, discard or expiry. The dry-run masks IDs and shows worker_no. The audit stores sha256 only.
- IM6-5. **Validation codes:**

| Code | Level | Condition |
|---|---|---|
| E01 | error | worker not found or Anonymised |
| E02 | error | code unknown or inactive; or a code of another catalogue (`CODE_IN_OTHER_CATALOGUE`) |
| E03 | error | provider not acceptable on examined_on (MP-3, meta reason) |
| E04 | error | examiner not valid or not qualified for the code (EX-2) |
| E05 | error | duplicate (provider, certificate_no) for another worker, or a duplicate code within one certificate |
| E06 | error | outcome / restriction / review-date rules (FA-3) |
| E07 | error | examined_on in the future; or every line already expired (FA-2) |
| E08 | error | row outside the uploader's scope |
| E09 | error | ID mismatch (FA-10) |
| E10 | error | unparseable date; missing required column (whole file rejected) |
| W01 | warning | printed_next_due later than the code validity (valid_until is shortened) |
| W02 | warning | a line expires within 30 days |
| W03 | warning | the same file sha256 was already committed on this project |
| W04 | warning | permanently_unfit outcome (the HSE Manager is notified at commit, no detail) |

### 5.12 KPIs and AI (MK)
- MK-1. All 6a KPIs are computed by the backend; the frontend only formats them.
- MK-2. Population date = the end of the as_of day (local). The population for K-89…K-92 and K-96 is the contractor_worker deployments Mobilised at as_of. Contractor attribution is the deployment's engagement (filter with descendants per Phase 1 K-R5).
- MK-3. **Small-cell rule (health data):** any breakdown cell, or any headline count of K-91 workers, K-93 or K-96, of 1–4 persons is shown as "<5" to every role except the HSE Manager and OH Practitioners. Zero is shown as 0. This is stricter than Phase 1 T3's "<3".
- MK-4. AI tool **T18 `get_occupational_health_kpis`** (project_ids, period, filters {site, engagement, include_descendants, trade, code, code_category}, metrics [K-89…K-96], group_by {code, code_category, contractor, trade, month}) returns aggregates only, with MK-3 applied for every caller. It returns **no names, worker_no, outcomes per person, restrictions per person, hold or referral reasons, examiners or clinics**. T13 also returns E14–E15. T9 gains the dimension `medical_gap_at_event` (yes / no / unknown, §6.9 MF8), with groups < 5 suppressed.
- MK-5. Viewer/Client sees 6a KPIs as aggregates with MK-3, and sees no lists.
- MK-6. The AI never comments on an individual's health and never recommends an employment action about a person (Phase 1 AI-12 restated).

### 5.13 PDPL (P6-x; extends P1–P13, P1-x, P2-x, P3-x, P4-x, P5-x)
- P6-1. **Sensitive:** assessment types, outcomes, restrictions and review dates, assessment status and verification, provider and examiner per assessment, holds (existence, reason, dates, work-during-hold), referral reasons and notes, scans, import files, medical hook results. **Personal:** exposure groups, the requirement status at tier 1, examiner registrations, referral existence and raiser, recorder and signer identities.
- P6-2. **Minimisation and prohibited data.** No field exists for, and no free text may contain, diagnoses, symptoms beyond what a referrer saw, test values (vision, audiogram, spirometry, blood pressure, BMI, laboratory), medication, pregnancy, infectious-disease status, mental-health information, drug or alcohol results, or genetic data. Scans showing clinical data are rejected and deleted (FA-9). The platform's fitness certificate form (§8.4) is the only recommended scan.
- P6-3. **Legal basis and notice:** processing relies on the employer's legal obligations (R1–R2) and on protecting workers' vital interests, not on consent `VERIFY` R6. Before each assessment the worker is given the purpose notice (`worker_purpose_notice_version`, EN/AR and read out in the worker's primary language), and the recorder ticks `purpose_notice_given` (FA-7).
- P6-4. Tiers per OH-2. Every tier-2 or tier-3 read writes `sensitive_field_read`. Lists show worker names only to capability 46 holders; everyone else sees worker_no, or "Worker" for Viewer/Client (DECISIONS #48).
- P6-5. Sensitive columns are encrypted at application level. Scans live in a **separate medical bucket** (not the Phase 2 personal bucket), served by signed URLs ≤ 5 min only to capability 160 holders with a reason (`verification`, `authority_request`, `gosi_claim`, `legal`, `other`+text). Scans are never in exports, AI inputs or emails.
- P6-6. AI: aggregates only, MK-3 and MK-4.
- P6-7. Alerts, gate screens, permit prints, the action panel for tier-1 roles, and exports for tier-1 roles carry no outcome, restriction, reason or clinic. The texts are "Fitness requirement not met / متطلب اللياقة غير مستوفى", "Fitness certificate due / شهادة اللياقة مستحقة" and "Worker removed from work pending HSE check / تم إبعاد العامل عن العمل لحين مراجعة السلامة".
- P6-8. **Retention:**
  - outcome lines: `fitness_record_retention_years` after the worker's last demobilisation, or `surveillance_record_retention_years` for surveillance codes (R4, R7), after which they are anonymised (statistics kept);
  - scans: `fitness_scan_retention_months` after the assessment's Accept, Reject or Revoke;
  - referral notes and hold reason texts: 2 years after closure ASSUMPTION.

  Records linked to an open injury case follow Phase 1 P1-5. Deletions are audited `retention_purge`.
- P6-9. **Data-subject access:** capability 165 produces a per-worker report (assessments, outcomes, restrictions, holds, referrals). It is handed over by the OH Practitioner and the export is audited with purpose `data_subject_request`.
- P6-10. **Employer disclosure:** Contractor HSE Reps (the employer) get tier 2 for C scope: status, outcome category and functional restrictions, so that they can assign suitable duties. They never get tier 3.
- P6-11. **No automated decisions:** unfitness is decided by a licensed physician. The platform only enforces access and permits through hooks and never changes employment status (FA-16, FH-7) `VERIFY` R6 provisions on automated decisions.
- P6-12. A personal-data breach involving 6a data is a health-data breach for Phase 0 P9 and is flagged as such in the breach record.
- P6-13. Phase 1 P1-8 (the 10-digit ID scan) applies to every 6a free-text field.

### 5.14 Phase-boundary rules (BD6)
- BD6-1. 6a owns hook kind `medical_fitness` only. It reads Phase 1 injury cases (for FH-1a, FH-8c and RW), Phase 2 workers, deployments, gate logs (FH-8a) and ADPs, Phase 3 crews and crew_present (FH-8b), and Phase 4 PC-13 flags (RF-7). It never writes their records.
- BD6-2. Fitness never satisfies a training or certification hook, and the reverse is also true. A worker can need WAH (Phase 5), WAH-FIT (6a) and a scaffold tag (Phase 4) at the same time.

### 5.15 Permission matrix — Phase 6a extension
Continues Phase 5 §5.15. Legend A/P/S/C/C1/R/—. The column **OH Pract.** is the new role (§3.0). Earlier rows for that role are in §11.1.

| # | Capability | HSE Mgr | HSE Officer | Site Eng/Sup | Permit Issuer | Permit Receiver | Contractor HSE Rep | Viewer/Client | OH Pract. |
|---|---|---|---|---|---|---|---|---|---|
| 146 | View fitness catalogue, providers (no licences of examiners), requirement plan | A | P | S | S | C1 | C | P (R) | P |
| 147 | Create / edit the fitness code catalogue (tighten only) | A | — | — | — | — | — | — | — |
| 148 | Create / edit / submit medical providers and examiner registrations | A | P | — | — | — | — | — | P |
| 149 | Approve / suspend / blacklist providers; suspend / withdraw examiner registrations | A | — | — | — | — | — | — | — |
| 150 | Edit requirement plan (manual lines; loosening HSE Mgr only, MR-5) | A | P | — | — | — | — | — | P |
| 151 | Edit worker health profiles (exposure groups) | A | P | S | — | — | C | — | P |
| 152 | Record site-clinic assessments; sign as linked examiner | — (OH-3) | — | — | — | — | — | — | P |
| 153 | Submit external fitness certificates | A | P | — | — | — | C | — | P |
| 154 | Review / accept / return / reject external certificates; record verification | A ASSUMPTION (§10 Q2) | — | — | — | — | — | — | P |
| 155 | View fitness status — tier 1 (OH-2) | A | P | S | S | C1 | C | — | P |
| 156 | View outcome category, functional restrictions, hold yes/no — tier 2 | A | P | S | — | — | C | — | P |
| 157 | View clinical-administrative detail — tier 3; revoke assessments | A | — | — | — | — | — | — | P |
| 158 | Raise fitness referral | A | P | S | S | C1 | C | — | P |
| 159 | Place manual hold; cancel holds and referrals with holds | A | P (place only) | — | — | — | — | — | P |
| 160 | Open fitness certificate scans (audited, reason) | A ASSUMPTION (§10 Q2) | — | — | — | — | — | — | P |
| 161 | Import fitness records (`clinic_register_file`: A, OH; `contractor_file`: C) | A | — | — | — | — | C | — | P |
| 162 | View 6a KPIs, expiring items, action panel, readiness report (per tier) | A | P | S | S | C1 | C | P (aggregates, MK-3) | P |
| 163 | Export 6a registers (tier rules; never scans) | A | P | S | — | — | C | P (aggregates) | P |
| 164 | Edit 6a settings; enable medical hooks; early switch; one deferral | A | — | — | — | — | — | — | — |
| 165 | Per-worker medical-fitness data-subject report | A | — | — | — | — | — | — | P |

Gate devices keep capability 74 only. Suspended-contractor users keep reads and lose writes (Phase 0 rule 28).

## 6. Calculations

All dates are local Asia/Riyadh. `add_months` works as in Phase 2 §6.1 (clamped to month end). Rounding is half-up at output only (Phase 1 K-R8): percentages to 1 dp. Comparisons and warnings use unrounded values. Day differences are calendar days.

### 6.1 Line validity (strictest wins)
- code_end = add_months(examined_on, catalogue validity_months) − 1 day.
- restriction_end = restriction_review_date when the line is fit_with_restrictions and any restriction has review_required; otherwise none.
- **valid_until (stored, org default)** = min(printed_next_due, code_end, restriction_end). Null terms are ignored.
- **valid_until (effective on project P, computed on read)** = min(stored valid_until, add_months(examined_on, P override) − 1 day).
- limiting_factor = the term giving the minimum. Ties resolve in this order: `restriction_review`, `printed_next_due`, `code_validity`, `project_override`.
- Lines with an unfit outcome have no valid_until. They govern until superseded (HK6-3).
- days_left(d) = valid_until − d.

### 6.2 Governing line and in-force predicate
- governing(W, C) = argmax over W's lines for C with assessment status Accepted and line not revoked, ordered by (examined_on, accepted_at).
- A line L is **in force** at local date d on project P ⇔ L is governing at d, L.outcome ∈ {fit, fit_with_restrictions}, the assessment is verified (or inside FV-1's window for a non-critical code), examined_on ≤ d ≤ effective valid_until, and the provider is not blacklisted in a scope covering L.
- **Restrictions in force at d** = the restrictions of every line that is in force at d. Lines that are not in force carry none.

### 6.3 Requirement due date and state (per deployment × de-duplicated code)
- applies_from = max(deployment.mobilised_on, line.effective_from, the date the line began to apply through trade, exposure group or ADP).
- due_date = applies_from + due_within_days.
- State at d (end of day), first match wins:
  1. `met`: the hook check at d (HK6-6, project P) returns met or expiring, shown as `expiring` when valid_until ≤ d + 30 (KPI meaning).
  2. `due`: d < due_date.
  3. `gap`: otherwise. The gap reason is the HK6-6 reason_code.
- **Counted** (K-89…K-91) = a kpi_counted line, a Mobilised contractor_worker deployment at d, and state ∈ {met, expiring, gap}.

### 6.4 Hold durations and work during hold
- hold_hours = (released_at or now) − started_at, in hours to 1 dp.
- A hold is **compliant** ⇔ work_during_hold (FH-8) is empty when it is released. The FH-8c day test is rtw_date < local date(released_at).

### 6.5 Referral timeliness
- A referral is **counted** for K-95 in period [s, e] ⇔ raised_at ∈ [s, e], status ≠ cancelled, and due_at ≤ e end-of-day (its window has closed).
- It is **on time** ⇔ assessed_at ≤ due_at.

### 6.6 KPI catalogue (continues Phase 5 §6.8)

| ID | Metric (EN / AR) | Formula | Unit / display | Better |
|---|---|---|---|---|
| K-89 | **Medical fitness compliance** / نسبة الامتثال للياقة الطبية | n(counted requirements at as_of with state met or expiring) ÷ n(counted requirements at as_of) × 100; denominator 0 → "—"; breakdown by code, trade, contractor | %, 1 dp | higher |
| K-90 | **Workers medically cleared** / العمال المستوفون للياقة | n(Mobilised contractor_worker deployments with ≥ 1 counted requirement and no `gap`) ÷ n(those with ≥ 1 counted requirement) × 100 | %, 1 dp | higher |
| K-91 | **Fitness gaps** / فجوات اللياقة | at as_of: n(counted requirements in gap) · n(deployments with ≥ 1 gap) · n(gaps on hook codes of the project); breakdown by gap reason for tier 2+ only | count · count · count | lower |
| K-92 | Fitness expiring ≤ 30 days / شهادات لياقة تنتهي خلال 30 يوماً | n(distinct lines in force at as_of with valid_until ∈ [as_of, as_of + 30] that satisfy a counted requirement) | count | lower |
| K-93 | **Active fitness holds** / حالات الإيقاف لأسباب اللياقة | at as_of: n(Active holds of contractor_worker deployments on the project) · n(of those with reason referral or manual and as_of > started_at + `referral_assessment_hours`) | count · count (MK-3) | lower |
| K-94 | **Holds cleared before work** / حالات الإيقاف المرفوعة قبل العودة للعمل | n(holds Released in period and compliant, §6.4) ÷ n(holds Released in period) × 100; denominator 0 → "—" | %, 1 dp | higher |
| K-95 | Referrals assessed on time / الإحالات المقيمة في الموعد | n(counted referrals on time, §6.5) ÷ n(counted referrals) × 100 | %, 1 dp | higher |
| K-96 | Workers on work restrictions / عمال عليهم قيود عمل | at as_of: n(Mobilised contractor_worker deployments whose worker has ≥ 1 restriction in force with review_required = true) | count (MK-3) | — (context) |

### 6.7 Leading-indicator warnings
These extend Phase 1 §6.9. The monthly job runs on day 2 at 07:00, per project and per tier-1 tree (DECISIONS #53).
- **E14**, at the end of month M: K-89 (as_of the last day of M, unrounded) < `medical_compliance_warning_pct`. Not raised when the denominator is 0.
- **E15**, in M: K-94 for M < 100.0, meaning at least one hold released in M had work during the hold (FH-8). It is also raised when a hold that is still Active at the end of M has a work-during-hold detection dated in M.
- Inputs returned by T13: K-89 numerator, denominator and threshold (E14); the count of holds with work during hold, by detection type (E15). Never identities or reasons.

### 6.8 Hook block dates (kind medical_fitness)
- critical_block_from = provider_registered_on + `medical_hook_critical_transition_days`.
- general_block_from = provider_registered_on + `medical_hook_transition_days`, plus at most one deferral of ≤ 30 days.
- The block starts at 00:00 local on that date (job at 00:00:30).

### 6.9 Worked examples (exact; backend unit tests must match)

**MF1 — validity (strictest wins).**
- (a) Zaheer Abbas, CRANE-OPERATOR-FIT examined 2025-10-10 (12 months): add_months = 2026-10-10, so valid_until = **2026-10-09**, limiting `code_validity`. At the clock (2026-10-06) days_left = **3**, so the result is `expiring`.
- (b) External DRIVER-FIT examined 2026-02-15 with printed_next_due 2027-01-31: code_end = 2028-02-14, so valid_until = **2027-01-31**, limiting `printed_next_due`.
- (c) Osman Idris, GEN-FIT examined 2026-09-15, fit_with_restrictions [no_work_at_height], review 2026-12-15: code_end = 2028-09-14, so valid_until = **2026-12-15**, limiting `restriction_review`.
- (d) Jomar Santos, DRIVER-FIT examined 2026-02-20, fit_with_restrictions [requires_corrective_lenses] (review not required): valid_until = **2028-02-19**, limiting `code_validity`.
- (e) Month-end clamp: examined 2026-08-31 with 12 months gives **2027-08-30**; examined 2024-02-29 with 12 months gives add_months 2025-02-28 and valid_until **2025-02-27** (as Phase 5 TR1e).
- (f) Hypothetical project override (not seeded): RBT-52 sets GEN-FIT = 12. Ali Hassan's GEN-FIT examined 2026-06-14 has stored valid_until **2028-06-13**, but on RBT-52 it is **2027-06-13** (`project_override`).

**MF2 — hook results at the clock (2026-10-06 10:00, stage `transition`; critical block from 2026-10-08, general from 2026-10-31).**

| Worker · code | Governing line / hold | Result at clock | Changes |
|---|---|---|---|
| Kamal Hossain · CSE-ENTRY-FIT (entrant, PTW-0413) | MFA-ANIA-EXP-2026-00118, fit, → 2027-03-01 | **met** | — |
| Rafiq Islam · CSE-ENTRY-FIT and RESPIRATOR-FIT (rescue lead, PTW-0413) | MFA-ANIA-EXP-2025-00402, fit, → 2026-10-31 | **met** (days_left 25) | `expiring` from 2026-10-25; not_met `MEDICAL_EXPIRED` from 2026-11-01, which blocks (critical) |
| Zaheer Abbas · CRANE-OPERATOR-FIT (PTW-0410 crane operator) | MFA-ANIA-EXP-2025-00391 → 2026-10-09 | **expiring** → PTW-0410 warning `EXPIRING_7D` | 2026-10-10: not_met `MEDICAL_EXPIRED`; blocks (critical from 10-08), so PTW blocker `KEY_ROLE_INELIGIBLE` |
| Osman Idris · WAH-FIT | WAH line MFA-ANIA-EXP-2026-00055 fit → 2027-02-28; GEN line 00398 restriction no_work_at_height | **not_met `RESTRICTION_CONFLICT`, hard stop** (blocks now) | until the restriction is lifted by a new assessment |
| Osman Idris · GEN-FIT | MFA-ANIA-EXP-2026-00398 → 2026-12-15 | **met**, conditions [no_work_at_height] | `MEDICAL_REVIEW_DUE` from 2026-12-16 (blocks: after 10-31) |
| Ganesh Shrestha · GEN-FIT | MFA-ANIA-EXP-2026-00405, fit_with_restrictions [no_heat_exposure], → 2026-10-07 | **expiring** (1 day), condition no_heat_exposure | 2026-10-08 … 10-30: warn `HOOK_NOT_MET_WARN` (MEDICAL_REVIEW_DUE); from 10-31 DENIED |
| Sunil Gurung · GEN-FIT | hold MFH-ANIA-EXP-2026-00027 (referral 00031, 08:40 today) | **not_met `MEDICAL_HOLD`, hard stop** → G-ANIA-01 DENIED `HOOK_NOT_MET` | released by a referral assessment (FH-3) |
| Jomar Santos · DRIVER-FIT | external SALAMA, verified → 2028-02-19 | **met**, conditions [requires_corrective_lenses] | — |
| NAJD bulk worker · GEN-FIT | QUICKMED QM-TEST-26-0917 Rejected (verification not_found 2026-09-24) | **not_met `MEDICAL_VERIFICATION_FAILED`, hard stop** | — |
| A bulk worker with no GEN-FIT | — | warn `HOOK_NOT_MET_WARN` (MEDICAL_MISSING) at site gates | DENIED from 2026-10-31 |

**MF3 — holds and return to work.**
- (a) Imran Hussain, INC-ANIA-EXP-2026-0147-P1. The case was first classified LTI on 2026-09-09 08:00, which created hold MFH-ANIA-EXP-2026-00015 (`rtw_after_injury`). RTW assessment MFA-ANIA-EXP-2026-00412 was examined 2026-09-28 by Dr. Huda and Accepted at 10:42 (GEN-FIT fit → **2028-09-27**; WAH-FIT fit → **2027-09-27**). The hold was released 2026-09-28 10:42; hold_hours = 19 d 2 h 42 min = **458.7 h**. Phase 1 rtw_date 2026-09-29 ≥ 2026-09-28, no gate entry between 09-09 08:00 and 09-28 10:42, no crew_present, so the hold is **compliant**.
- (b) Ganesh Shrestha, the 2026-09-22 GULFPAVE heat-exhaustion MTC (Phase 1 seed, Sep 2026, W1 #4 pattern), case created 2026-09-22 14:35: hold MFH-ANIA-EXP-2026-00019 (`heat_illness`, nature heat_exhaustion although the category is MTC). RTW assessment 00405 was examined 2026-09-23 and Accepted at 06:31 (fit_with_restrictions [no_heat_exposure], review 2026-10-07). hold_hours = 15 h 56 min = **15.9 h**. First gate entry: 2026-09-23 06:45 at G-AAP3 (after release), so the hold is **compliant**.
- (c) Breach: MFR-ANIA-EXP-2026-00012 was raised 2026-09-11 16:20 (RAWABI bulk labourer, remove_from_work) and created hold MFH-ANIA-EXP-2026-00016, due 2026-09-12 16:20. The worker entered at G-ANIA-01 on 2026-09-12 06:52, GRANTED (medical hooks were not enabled in September, so the gate checked no fitness). The referral assessment was Accepted 2026-09-13 09:00. The referral is **late** (40.7 h > 24 h) and the hold is **not compliant** (FH-8a). This is the only breach in September, so it raises **E15** for ANIA-EXP and the RAWABI tree.
- (d) Sunil Gurung: referral MFR-ANIA-EXP-2026-00031 by Fahad at 2026-10-06 08:40 created hold 00027, due 2026-10-07 08:40. At the clock, G-ANIA-01 gives DENIED `HOOK_NOT_MET` and the guard sees "Not eligible — HSE check". If Grace records the referral assessment at 14:00 and Dr. Huda signs at 15:10 (GEN-FIT fit), the hold is released at 15:10 (hold_hours 6.5 h) and the referral is on time.

**MF4 — KPI fixture = seed (as_of 2026-09-30; period September 2026; Appendix A.9).**

| Metric | ANIA-EXP calculation | ANIA-EXP | RBT-52 calculation | RBT-52 |
|---|---|---|---|---|
| K-89 | 5,019 ÷ 5,115 × 100 = 98.1231… | **98.1 %** | 687 ÷ 703 × 100 = 97.7240… | **97.7 %** |
| K-90 | (3,412 − 87) ÷ 3,412 × 100 = 3,325 ÷ 3,412 = 97.4501… | **97.5 %** | (654 − 15) ÷ 654 × 100 = 639 ÷ 654 = 97.7064… | **97.7 %** |
| K-91 | gaps 96 · workers 87 · hook-code gaps 76 (GEN-FIT 52, WAH-FIT 15, PLANT-OPERATOR-FIT 3, DRIVER-FIT 6) | **96 · 87 · 76** | 16 · 15 · 16 (GEN-FIT 14, WAH-FIT 2) | **16 · 15 · 16** |
| K-92 | lines in force with valid_until 2026-09-30…10-30 (incl. Zaheer 10-09, Ganesh 10-07) | **71** | | **12** |
| K-93 | 3 Active holds; 1 referral hold past 24 h (raised 2026-09-29 15:00) | **3 · 1** | 1 · 0 (raised 2026-09-30 11:00) | **1 · 0** shown to tier-1 roles as **<5 · 0** |
| K-94 | released in Sep 9 (Imran, Ganesh, 7 referral holds); compliant 8 → 8 ÷ 9 × 100 = 88.888… | **88.9 %** | 2 ÷ 2 × 100 | **100.0 %** |
| K-95 | raised in Sep 14; 2 with windows open at 09-30 end (raised 09-30 10:00 and 13:30) → counted 12; on time 10 → 10 ÷ 12 × 100 = 83.333… | **83.3 %** | raised 4; 1 open window → counted 3; on time 3 | **100.0 %** |
| K-96 | | **41** | | **6** |

Expected warnings for September 2026:
- **No E14 for ANIA-EXP** (98.123 ≥ 98.0).
- **E14 for RBT-52** (97.724 < 98.0), raised for the project and the QIMMA tree.
- **E15 for ANIA-EXP** (MF3c), raised for the project and the RAWABI tree.
- No E15 for RBT-52.

**MF5 — rounding and boundary edges.**
- K-89 = 9,795 ÷ 10,000 = 97.95 is displayed **98.0 %**, but E14 is **raised** (97.95 < 98.0).
- K-94 = 1 ÷ 3 = 33.333… is displayed **33.3 %**.
- A referral raised 2026-10-06 08:40 and assessed at 2026-10-07 08:40:00 exactly is on time (≤ due_at). At 08:40:01 it is late.
- Restriction review: a line with restriction_review_date 2026-10-07 is in force on 2026-10-07 and not on 2026-10-08.

**MF6 — alert dates.**
- Zaheer CRANE-OPERATOR-FIT (valid 2026-10-09): 30 / 14 / 7 / 0 alerts on **2026-09-09, 2026-09-25, 2026-10-02, 2026-10-09**.
- Dr. Arun Menon's SCFHS licence (valid 2026-10-20): **2026-09-20, 2026-10-06 (today, 07:00), 2026-10-13, 2026-10-20**.
- Osman's restriction review (2026-12-15): 14 / 0-day review alerts **2026-12-01, 2026-12-15**.
- Ganesh's restriction review (2026-10-07): **2026-09-23** (sent 07:00, after the 06:31 acceptance) and **2026-10-07**.
- Rafiq's CSE-ENTRY-FIT (2026-10-31): **2026-10-01, 2026-10-17, 2026-10-24, 2026-10-31**.

**MF7 — provider and examiner acceptability.**
- (a) RAWABI-CC (contractor_clinic) recording CSE-ENTRY-FIT gives `MEDICAL_PROVIDER_NOT_ACCEPTABLE` (`PROVIDER_KIND_NOT_ALLOWED`).
- (b) RAWABI-CC recording GEN-FIT for a QIMMA worker gives `NOT_OWN_TREE`.
- (c) SHIFA-RBT recording for an ANIA-EXP assessment gives `NOT_PROJECT_CLINIC`.
- (d) Dr. Arun Menon (physician, licence to 2026-10-20) signing RAD-WORKER-FIT gives `EXAMINER_NOT_QUALIFIED`. Signing GEN-FIT examined 2026-10-21 gives `EXAMINER_LICENCE_INVALID`.
- (e) QUICKMED (Suspended 2026-09-25): a certificate examined 2026-09-25 gives `PROVIDER_SUSPENDED`; one examined 2026-09-24 may be submitted.

**MF8 — medical gap at event (T9 dimension).**
- medical_gap_at_event(incident) = **yes** when any worker linked to the incident had, on the event's local date, a counted requirement in state gap; **no** when all linked workers had none; **unknown** when no worker is linked, or when the date is before `medical_register_from`.
- INC-ANIA-EXP-2026-0147 (2026-09-08, Imran Hussain) gives **no**: his GEN-FIT and WAH-FIT from 2026-08-20 were in force. This contrasts with Phase 5 TR9 = yes (training gap).

## 7. Alerts & expiries

Channels are as in Phases 1–5: in-app and email in the recipient's language, and SMS where marked (ASSUMPTION). Alerts about a worker go to the Contractor HSE Rep of the worker's engagement and to the OH Practitioners of the project. HSE Officers are added where marked. Texts follow P6-7: worker_no (names only with capability 46), code (tier 2+ recipients only), date and reference; never an outcome for tier-1 recipients, never a reason, never a clinic. The long schedule (30 / 14 / 7 / 0) is sent at 07:00 local. Each step is sent once per (subject, step); steps still to come are cancelled when a renewal comes into force; re-running a job never sends twice.

| Trigger | Recipient | Timing | Channel |
|---|---|---|---|
| Fitness line expiry (it satisfies a counted or hook requirement) | Contractor HSE Rep ("Fitness certificate due"); OH Practitioners at 30 and 7; HSE Officer at 0; HSE Manager at 0 for critical codes | 30 / 14 / 7 / 0 days | In-app + email |
| Line expiring while the worker is on a non-terminal permit crew or an Active WAP | Receiver ("crew member HSE check due"); OH Practitioners | On crew add / change if valid_until ≤ the permit's end; at the 7-day step | In-app |
| Restriction review / temporarily-unfit review date | OH Practitioners; Contractor HSE Rep ("Fitness review due") | 14 and 0 days before | In-app + email |
| Hold created (any reason) | OH Practitioners (reason for tier 3); Contractor HSE Rep ("Worker removed from work pending HSE check"); receivers of live permits naming the worker | Within 60 s | In-app + email; SMS to OH Practitioners when the reason is referral or heat_illness |
| Referral raised | OH Practitioners | Immediately; again at due_at − 2 h if Open | In-app + email (+ SMS when remove_from_work) |
| Referral overdue | OH Practitioners; HSE Officer; HSE Manager at due + 24 h | At due_at; daily 07:00 while overdue | In-app + email |
| Work during hold detected (FH-8) | OH Practitioners; HSE Manager; HSE Officer (no reason) | Immediately | In-app + email + SMS (HSE Manager) |
| `RTW_BEFORE_CLEARANCE` (RW-2) | OH Practitioners; HSE Manager | Immediately | In-app + email |
| Restricted-days prompt (RW-3) | Incident's HSE Officer | At hold release | In-app |
| Sign-off due (FA-6) | Examiner's linked user; OH Practitioners | 24 h before `signoff_due_hours`; at the deadline | In-app |
| External certificate submitted | OH Practitioners | Immediately; reminder at 24 h | In-app |
| Verification due / unable_to_verify / failed | OH Practitioners; HSE Manager (unable / failed) | Due −1 day and on the due day / immediately | In-app + email (+ SMS HSE Manager on failed) |
| `CLINICAL_DATA_IN_SCAN` rejection | Submitter (with the form link) | Immediately | In-app + email |
| Certificate number reused (FA-10) | OH Practitioners | Immediately | In-app |
| Permanently-unfit outcome accepted | HSE Manager (no detail); Contractor HSE Rep (tier 2: outcome category only) | Immediately | In-app |
| Provider licence / examiner licence expiry | OH Practitioners; HSE Officers; HSE Manager | 30 / 14 / 7 / 0 days | In-app + email |
| Provider suspended / blacklisted | OH Practitioners; HSE Officers; affected Contractor HSE Reps (no reason) | Within 60 s | In-app + email |
| Hook block date approaching (critical / general, kind medical_fitness) | HSE Manager; HSE Officers; OH Practitioners; Contractor HSE Reps (with their readiness counts) | 7 days and 1 day before (07:00); at the switch | In-app + email |
| Early switch, deferral or policy change | HSE Officers; OH Practitioners; Contractor HSE Reps | Immediately | In-app + email |
| Import batch Validated / committed / expired | Uploader | Immediately | In-app |
| E14 / E15 | HSE Manager; HSE Officers; OH Practitioners; tier-1 Contractor HSE Rep for its tree | Monthly job, day 2, 07:00 | In-app + email |

An alert whose subject was demobilised, superseded or anonymised before its send time is dropped.

## 8. Reports / KPIs fed

### 8.1 Dashboard additions (Phase 1 §8.1)
1. **Leading tiles:** K-89 medical fitness compliance (breakdown by code on hover; E14 threshold marker) · K-90 workers medically cleared · K-91 fitness gaps (chip: hook-code gaps) · K-94 holds cleared before work (chip: K-93 active holds, MK-3).
2. **Occupational health band** (tier 2+ roles and HSE Manager): holds active (overdue chip), referrals awaiting assessment, external certificates awaiting review or verification, sign-offs due, K-92 expiring ≤ 30 days, and the hook stage for kind medical_fitness with the next block date. Tier-1 roles see counts only, with MK-3.
3. **Charts:**
   - C22: K-89 and K-90 by month (lines), with the E14 threshold as a reference line;
   - C23: holds by month, released vs still active, with K-94 as a line (secondary axis); MK-3 applies;
   - C24: fitness expiry profile for the next 90 days, weekly bars by code category.
4. Filters D-2 apply, plus trade, code and code category.

### 8.2 Expiring-items panel — new `ExpiringItemKind` values
`fitness_expiry`, `fitness_restriction_review`, `fitness_unfit_review`, `referral_assessment_due`, `fitness_signoff_due`, `fitness_verification_due`, `examiner_licence_expiry`, `medical_provider_licence_expiry`. `hook_block_date` (Phase 4) is reused with kind medical_fitness. Item text per P6-7; Viewer/Client sees counts only, with MK-3.

### 8.3 Action panel additions
- referrals overdue;
- holds with work during hold;
- `RTW_BEFORE_CLEARANCE` cases;
- external certificates awaiting review > 24 h;
- verifications overdue, failed without a decision, and `unable_to_verify`;
- sign-offs past `signoff_due_hours`;
- hard-stop medical results for workers on non-terminal permits or Active WAPs (with permit/WAP number; reason per tier);
- lines expiring ≤ 7 days for crew of live permits;
- hook block date ≤ 7 days with medical readiness < 100 %;
- examiners with expired licences who still have assessments awaiting their sign-off.

### 8.4 Registers and reports
- Fitness code catalogue (EN/AR) with validity, examiner and provider rules, and hook use.
- Provider register and examiner register (licences, status, expiries).
- Requirement plan per project (current version and history), with applicability counts.
- Worker fitness status register (tier-aware columns) and gap register.
- Holds and referrals register (tier 2 lists; reasons tier 3).
- Verification log (tier 3).
- **Fitness certificate form** (bilingual PDF template for clinics). It has fields for worker name and worker_no, code lines with outcome, functional restrictions and review dates, examiner name, SCFHS number, clinic stamp and the date, and the printed notice "No diagnosis or test results on this form / لا يذكر التشخيص أو نتائج الفحوص في هذا النموذج".
- Readiness report (HK6-9).
- Import history.

Exports (capability 163) follow the tiers. They never include scans, ID numbers or reason texts below tier 3. Every export writes an `export` audit entry with dataset, columns and filters (as DECISIONS #78).

### 8.5 Feeds to other phases
- **Phase 1:** K-89…K-96, E14–E15, T18, T9 dimension `medical_gap_at_event`, an AI-19 monthly-report section "Occupational health" (aggregates, MK-3), the warning `RTW_BEFORE_CLEARANCE` and the RW-3 prompt.
- **Phase 2:** the provider for `medical_fitness` at the project hook list (site gates and every zone), the Z-TC01 crane-operator hook and the ADP categories; hard stops at gates.
- **Phase 3:** the provider for crew roles and operator bindings; hard-stop and post-block suspensions via HK6-8 events.
- **Phase 4:** PC-13 handled through RF-7; the hook policy state shared with kind medical_fitness; the VF-9 combined view gains a Fitness section at tier 1 (cleared yes/no per code).
- **Phase 5:** the CK5-2 competence view shows the same tier-1 Fitness section.
- **6b (heat stress):** HEAT-EXPOSURE-FIT, the `no_heat_exposure` restriction, heat-illness holds and their timing (aggregates), and exposure group `heat_outdoor`.
- **6c / 6g:** first-aid and emergency data stay in Phase 5 / 6c; 6g may weight K-89, K-90 and K-94 in the contractor scorecard (aggregates only).

## 9. Acceptance criteria

Fixtures:
- The Appendix A seed, with the Phase 0–5 seed state as in their appendices.
- "Today" is the shared e2e/demo clock `HSE_CLOCK_AT` = **2026-10-06 10:00 Asia/Riyadh** unless another time is given.
- Medical hooks were enabled on both projects on 2026-10-01 (stage `transition`): critical codes block from 2026-10-08, the others from 2026-10-31.
- `medical_register_from` = 2026-08-01 on both projects.

Users:
- Faisal (HSE Manager); Noura (HSE Officer, ANIA-EXP); Lina (HSE Officer, RBT-52);
- **Dr. Huda Al-Mansour** (OH Practitioner, both projects, linked to examiner EXR-0001); **Grace Villanueva** (OH Practitioner, RBT-52 and ANIA-EXP, nurse, not linked to an examiner);
- Ahmed (Contractor HSE Rep, RAWABI tree); Yousef (Contractor HSE Rep, QIMMA);
- Omar and Fahad (site engineers); Khalid and Majed (permit issuers); Faris, Sanjay and Joseph (permit receivers); Sarah (viewer).

**Role, tiers and boundary**
1. **Given** Noura **When** she assigns role oh_practitioner to a user **Then** 403 (OH-1). Faisal assigns it, audited.
2. **Given** Faisal **When** he records a site-clinic assessment **Then** 403 (OH-3: capability 152 is not in his org-wide grant). `Me.org_capabilities` omits 152.
3. **Given** Osman Idris **When** Omar (S-AIR; Osman is on S-LAND) reads Osman's fitness **Then** 404 (out of scope). **When** Fahad (S-LAND, capabilities 155–156) reads it **Then** he sees GEN-FIT met, valid_until 2026-12-15, outcome fit_with_restrictions, restriction no_work_at_height, and no assessment type, examiner, clinic or reason. Two `sensitive_field_read` rows are written.
4. **Given** Ramesh (receiver, NAJD) **When** he reads Osman (NAJD) **Then** only tier 1: GEN-FIT "met, valid to 2026-12-15"; WAH-FIT "Not eligible — HSE check".
5. **Given** Ahmed (C scope) **When** he reads Sunil Gurung (RAWABI) **Then** he sees "hold: yes" and GEN-FIT not cleared, without the referral reason or note (P6-10).
6. **Given** Faisal **When** he creates fitness code `WAH` or `CRANE-OPERATOR` **Then** 422 `CODE_IN_OTHER_CATALOGUE`. **When** a Phase 5 course `GEN-FIT` is created later **Then** the same error (MC-2).

**Catalogue**
7. **Given** Noura **When** she edits a fitness code **Then** 403 (147).
8. **Given** CSE-ENTRY-FIT validity 12 **When** Faisal sets 24 **Then** 422 `CATALOGUE_LOOSENING`. **When** he sets 6 **Then** saved, every CSE-ENTRY-FIT line is recomputed (Kamal → 2026-09-01, now expired), and the workers now expiring ≤ 30 days are alerted (MC-3).
9. **Given** GEN-FIT **When** Faisal removes `contractor_clinic` from its provider kinds **Then** saved (tightening). **When** he adds `contractor_clinic` to WAH-FIT **Then** 422 `PROVIDER_KIND_NOT_ALLOWED` (MC-4).
10. **Given** RAD-WORKER-FIT examiner_classes [occupational_physician] **When** Faisal adds `physician` **Then** 422 `CATALOGUE_LOOSENING`.
11. **Given** a code with lines **When** it is deleted **Then** 409. Made inactive, its existing lines stay in force (MC-1).
12. **Given** a project override GEN-FIT = 30 on RBT-52 **Then** 422 (catalogue 24, shorten only); 12 **Then** saved, and Ali Hassan's effective GEN-FIT on RBT-52 is 2027-06-13 (MF1f).

**Providers and examiners**
13. **Given** Noura **When** she approves a provider **Then** 403. Faisal approves SALAMA with licence_checked_at set, audited (MP-1, MP-2).
14. **Given** a provider without licence_checked_at **When** it is submitted for approval **Then** 422.
15. **Given** RAWABI-CC **When** an assessment line CSE-ENTRY-FIT is saved with it **Then** 422 `MEDICAL_PROVIDER_NOT_ACCEPTABLE` (`PROVIDER_KIND_NOT_ALLOWED`) (MF7a).
16. **Given** RAWABI-CC **When** GEN-FIT is recorded for a QIMMA worker **Then** `NOT_OWN_TREE` (MF7b).
17. **Given** SHIFA-RBT **When** used for an ANIA-EXP assessment **Then** `NOT_PROJECT_CLINIC` (MF7c).
18. **Given** QUICKMED Suspended 2026-09-25 **Then** a certificate examined 2026-09-25 gets `PROVIDER_SUSPENDED`; one examined 2026-09-24 can be submitted (MF7e).
19. **Given** Faisal blacklists a test provider with scope `all_records` **Then** within 60 s every assessment of that provider is Revoked, the hook returns not_met `MEDICAL_REVOKED` with hard_stop for codes with no other in-force line, and the OH Practitioners receive the affected-worker list (MP-6).
20. **Given** Dr. Arun Menon (physician) **When** he is examiner on a RAD-WORKER-FIT line **Then** 422 `EXAMINER_NOT_QUALIFIED`. **When** a GEN-FIT line is examined 2026-10-21 **Then** `EXAMINER_LICENCE_INVALID` (MF7d).
21. **Given** a nurse-classified examiner **When** they are examiner on any line **Then** `EXAMINER_NOT_QUALIFIED` (EX-3).
22. **Given** Dr. Arun Menon's licence valid to 2026-10-20 **Then** licence alerts were sent on 2026-09-20 and 2026-10-06 07:00 and are scheduled for 2026-10-13 and 2026-10-20 (MF6).

**Requirement plan and profiles**
23. **Given** ANIA-EXP at 2026-09-30 **Then** MRL-ANIA-EXP-002 (WAH-FIT for scaffolder, steel_erector, rigger) has 519 counted requirements, 504 met or expiring, and 15 gaps (A.9).
24. **Given** the Phase 2 project hook GEN-FIT **Then** a read-only line MRL-ANIA-EXP-H01 exists. **When** Noura edits it **Then** 422 `LINE_DERIVED_FROM_HOOK` (MR-2).
25. **Given** derived line E01 (crew_role entrant → CSE-ENTRY-FIT) **Then** kpi_counted = false and it is not in K-89 (MR-2).
26. **Given** a manual line for DRIVER-FIT with due_within_days 14 **Then** 422 `DUE_DAYS_NOT_ALLOWED` (DRIVER-FIT is a hook code).
27. **Given** Noura **When** she removes the manual NOISE-SURV line **Then** 422 `PLAN_LOOSENING`. Faisal removes it with a reason ≥ 20 chars: effective_to = yesterday, and history is kept (MR-5).
28. **Given** any exemption request **Then** 422 `EXEMPTION_NOT_ALLOWED` (MR-6).
29. **Given** a welder mobilised 2026-10-06 **Then** the profile gets exposure group noise_85 from the trade defaults (WP-1), NOISE-SURV is due 2026-11-05 and is in state `due` until then.
30. **Given** Ahmed **When** he edits exposure groups of a QIMMA worker **Then** 403. For a NAJD worker **Then** saved from today (WP-1).
31. **Given** a mason with a SILICA-SURV gap **When** Noura removes silica_rcs with a 10-char reason **Then** 422. With ≥ 20 chars **Then** saved and the OH Practitioners alerted (WP-2).

**Assessments — site clinic**
32. **Given** Dr. Huda (linked to EXR-0001) **When** she records a periodic assessment for Prakash Thapa with GEN-FIT fit and passes re-auth **Then** it is Accepted at once, verified (`site_clinic_record`), with certificate_no MFC-ANIA-EXP-2026-…, and the old GEN-FIT line becomes superseded (FA-6, FA-11).
33. **Given** Grace (not linked) records Sunil's referral assessment with examiner EXR-0001 **Then** status Awaiting Sign-off and the hook is still `MEDICAL_HOLD`. **When** Dr. Huda signs with re-auth **Then** Accepted, the hold is released and the referral Assessed (FA-6, FH-3).
34. **Given** an assessment awaiting sign-off for 48 h (`signoff_due_hours` 72) **Then** an alert goes to Dr. Huda. At 72 h it appears in the action panel.
35. **Given** Grace selects examiner Dr. Samir Khoury (no linked user) on a site-clinic assessment **Then** 422 `EXAMINER_NOT_LINKED` (FA-6).
36. **Given** examined_on 2026-09-28 entered on 2026-10-06 (8 days) **Then** 422 `BACKDATED_ASSESSMENT`. 2026-09-29 is accepted (FA-2).
37. **Given** purpose_notice_given = false **Then** 422 `PURPOSE_NOTICE_REQUIRED` (FA-7).
38. **Given** a fit_with_restrictions line without restrictions **Then** `RESTRICTIONS_REQUIRED`. A fit line with restrictions gives `RESTRICTIONS_NOT_ALLOWED`. no_work_at_height without a review date gives `REVIEW_DATE_INVALID`. A review date 91 days after examined_on gives `REVIEW_DATE_INVALID` (FA-3).
39. **Given** requires_corrective_lenses only **Then** no review date is needed and valid_until = the code validity (MF1d).
40. **Given** a temporarily_unfit line without unfit_review_date **Then** 422. With 2026-11-05 **Then** saved; the hook returns `MEDICAL_UNFIT` hard_stop, still after 2026-11-05, until a new assessment (HK6-3).
41. **Given** a permanently_unfit line signed by a `physician` **Then** `EXAMINER_NOT_QUALIFIED`. Signed by Dr. Huda (occupational_physician) **Then** saved, and Faisal is notified without detail (FA-3).
42. **Given** a governing permanently_unfit WAH-FIT signed by Dr. Huda **When** Dr. Huda later signs WAH-FIT fit **Then** `SECOND_OPINION_REQUIRED`. Another occupational physician **Then** accepted (FA-12).
43. **Given** two lines for GEN-FIT in one assessment **Then** `DUPLICATE_CODE_LINE` (FA-3).
44. **Given** an Accepted assessment older than 24 h **When** Grace edits a line **Then** 409. Dr. Huda revokes it with a reason ≥ 20 chars and records a new one (FA-14).
45. **Given** a restriction text "epilepsy — no heights" **Then** the save is allowed, but the field shows the functional-only hint and the action panel lists it for OH review ASSUMPTION. A 10-digit number in it triggers the Phase 1 P1-8 warning (FA-4, P6-13).

**External certificates and verification**
46. **Given** Ahmed submits Jomar's SALAMA certificate without a scan **Then** 422. With a scan **Then** Submitted (FA-8).
47. **Given** Ahmed **When** he accepts it **Then** 403 (154). Dr. Huda accepts it; it is not in force until verified: hook `MEDICAL_UNVERIFIED` (FV-1).
48. **Given** Dr. Huda verifies via the SALAMA portal on salama-test.example **Then** verified and in force (FV-3).
49. **Given** a QR URL on a foreign domain **Then** it cannot be chosen as the channel and no outbound request is made (FV-3).
50. **Given** Faisal sets `unverified_fitness_acceptance_hours` = 24 **Then** an accepted DRIVER-FIT line is in force for 24 h before verification; a CSE-ENTRY-FIT line is not (FV-1).
51. **Given** two no_response attempts 2026-10-01 09:00 and 2026-10-02 10:00 **Then** `unable_to_verify` and Faisal alerted (FV-4).
52. **Given** the QUICKMED certificate QM-TEST-26-0917 verified not_found on 2026-09-24 **Then** it is Rejected, the hook gives `MEDICAL_VERIFICATION_FAILED` with hard_stop, Faisal gets an SMS, and the action panel asks for a decision (no automatic ban) (FV-5, MF2).
53. **Given** the reviewer answers clinical_data_present = true **Then** Rejected `CLINICAL_DATA_IN_SCAN`, the scan is deleted within 60 s (audited `retention_purge`, reason clinical_data), and Ahmed is alerted with the form link (FA-9).
54. **Given** the same certificate_no from SALAMA for another worker **Then** 409 `CERT_NO_REUSED` and the OH Practitioners are alerted (FA-10).
55. **Given** a certificate ID typed 2000001071 for Jomar (2000001003) **Then** 422 `CERT_ID_MISMATCH`, nothing stored, and the audit shows `2*******71` (FA-10).
56. **Given** a NAJD employee with capability 154 (test) verifying a NAJD worker's certificate **Then** `SOD_CONFLICT` (FV-2).
57. **Given** Dr. Huda submitted a certificate herself **When** she accepts it **Then** `SOD_CONFLICT` (FA-8).
58. **Given** an external certificate whose only line expired 2026-09-30 **Then** `FITNESS_ALREADY_EXPIRED`. Dr. Huda may attach it as historic, which is never in force (FA-2).

**Holds**
59. **Given** a new injury case linked to WKR-000016 (Kamal) is classified LTI **Then** an `rtw_after_injury` hold is created within 60 s, Kamal's CSE-ENTRY-FIT on PTW-0413 becomes not_met `MEDICAL_HOLD` with hard_stop, and PTW-0413 shows blocker `KEY_ROLE_INELIGIBLE` and, if Active, is Suspended `hook_not_met` within 60 s (FH-1a, FH-2).
60. **Given** a linked case with nature heat_exhaustion and category FAC **Then** a `heat_illness` hold is created (FH-1a).
61. **Given** a linked case classified MTC with nature laceration **Then** no hold (MTC is not in the default set).
62. **Given** the hold of AC59 **When** the case is reclassified to FAC (nature not heat) before release **Then** the hold is Cancelled `source_reclassified` (FH-4).
63. **Given** an incident Voided while its hold is Active **Then** the hold is Cancelled `source_voided`.
64. **Given** an incident entered on 2026-10-06 for an event on 2026-10-03 **Then** the hold's started_at is the creation time on 2026-10-06, not 10-03 (FH-5).
65. **Given** Sunil's hold **When** Faisal tries to release it without an assessment **Then** 422 `HOLD_RELEASE_REQUIRES_ASSESSMENT` (FH-3).
66. **Given** Imran's RTW assessment that included only WAH-FIT **Then** 422 `HOLD_REFERENCE_INVALID` (GEN-FIT required, FA-5).
67. **Given** an RTW assessment with GEN-FIT temporarily_unfit **Then** the hold is closed as Released, and the hook returns `MEDICAL_UNFIT` with hard_stop for every code (FH-3, HK6-6 step 4).
68. **Given** Noura places a manual hold with a 10-char reason **Then** 422. With ≥ 20 chars **Then** Active. **When** Noura tries to cancel it **Then** 403 (place only, row 159).
69. **Given** Sunil's hold **Then** his deployment stays Mobilised and his worker status Active (FH-7).
70. **Given** Sunil's hold and a guard at G-ANIA-01 sets admitted_despite_denial = true at 10:20 **Then** `work_during_hold` records the gate event, Faisal gets an SMS, and when the hold is later released K-94 counts it as not compliant (FH-8a).

**Referrals**
71. **Given** Faris (receiver, RAWABI) **When** he refers a NAJD worker **Then** 403 (C1). He can refer a RAWABI worker (RF-2).
72. **Given** Fahad's referral of Sunil with remove_from_work **Then** hold 00027 is created, due_at 2026-10-07 08:40, and Dr. Huda and Grace get in-app, email and SMS alerts (RF-3).
73. **Given** Fahad tries to cancel his referral **Then** 403 (remove_from_work = true → 159 only). **Given** a referral without removal **Then** Fahad may cancel it with a reason ≥ 20 chars before due_at (RF-5).
74. **Given** the referral is still Open at 2026-10-07 08:40 **Then** it is overdue: alerts go to Dr. Huda, Grace and Noura, and to Faisal at 2026-10-08 08:40 (§7).
75. **Given** a referral with reason heat_illness_episode **Then** it is saved with warning `INCIDENT_RECORD_EXPECTED` and a Phase 1 draft link, and no incident is created automatically (RF-6).
76. **Given** medical hooks are enabled on a project with a Phase 4 card flagged medical_restriction_on_card and no review **Then** a referral with reason `certificate_restriction`, without removal, is created (RF-7).
77. **Given** MF3c **Then** referral 00012 is late (40.7 h) and K-95 counts it as not on time.

**Return to work**
78. **Given** Imran's case **Then** hold 00015 was released 2026-09-28 10:42 by MFA-ANIA-EXP-2026-00412, and the hold is compliant (MF3a).
79. **Given** a Phase 1 user sets rtw_date 2026-09-27 on a case whose hold was released 2026-09-28 **Then** the save succeeds with warning `RTW_BEFORE_CLEARANCE`, the hold gets a work-during-hold entry, and the OH Practitioners and Faisal are alerted (RW-2, FH-8c).
80. **Given** a releasing RTW assessment fit_with_restrictions after an LTI **Then** the incident's HSE Officer gets the restricted-days prompt and the case is unchanged (RW-3).
81. **Given** Dr. Huda (capabilities 29–30 through §11.1) **When** she opens INC-ANIA-EXP-2026-0147-P1 **Then** she sees the medical fields, and a `sensitive_field_read` row is written (RW-1).
82. **Given** Ganesh's heat hold **Then** it is released 2026-09-23 06:31 and compliant; his first gate entry was 06:45 (MF3b).

**Hooks and the warn → block switch**
83. **Given** medical_register_from is null on a test project **When** Faisal enables medical hooks **Then** 422 `MEDICAL_REGISTER_NOT_LIVE`. With no approved clinic **Then** `NO_MEDICAL_PROVIDER` (HK6-1).
84. **Given** hooks enabled 2026-10-01 **Then** the policy state for kind medical_fitness shows critical_block_from 2026-10-08, general_block_from 2026-10-31 and stage transition, and Phase 2 no longer returns `HOOK_NOT_AVAILABLE` for medical codes (§6.8).
85. **Given** enable on 2026-10-01 **Then** the default attach points of HK6-2 exist (project hook GEN-FIT; Z-TC01 crane_operator CRANE-OPERATOR-FIT; ADP apron and manoeuvring DRIVER-FIT; the Phase 3 crew and operator-binding hooks) and are audited.
86. **Given** Kamal **When** PTW-0413 is evaluated at the clock **Then** CSE-ENTRY-FIT is met (MF2).
87. **Given** Zaheer **When** PTW-0410 is issued at 13:00 **Then** warning `EXPIRING_7D` for CRANE-OPERATOR-FIT (3 days) and the issue proceeds. **Given** the clock at 2026-10-10 **Then** blocker `KEY_ROLE_INELIGIBLE` (MF2).
88. **Given** Osman is added as crew on a permit with a work_at_height section **Then** not_met `RESTRICTION_CONFLICT` with hard_stop: a blocker at once, although in transition (HK6-3, MF2).
89. **Given** Sunil at G-ANIA-01 at 10:00 **Then** DENIED `HOOK_NOT_MET`, the guard sees "Not eligible — HSE check / غير مؤهل — مراجعة السلامة", and the gate log stores reason HOOK_NOT_MET with kind medical_fitness and no medical reason code (HK6-7).
90. **Given** a bulk worker with no GEN-FIT at G-ANIA-01 at the clock **Then** GRANTED_WITH_WARNING `HOOK_NOT_MET_WARN`. **Given** the clock at 2026-10-31 00:01 **Then** DENIED `HOOK_NOT_MET`.
91. **Given** Ganesh at G-AAP3 on 2026-10-08 **Then** GRANTED_WITH_WARNING (MEDICAL_REVIEW_DUE, warn until 10-31). At the clock **Then** GRANTED_WITH_WARNING `EXPIRING_7D`, plus "Work restriction applies" for callers without 156 (MF2).
92. **Given** Jomar's DRIVER-FIT **When** checked for an ADP **Then** met with conditions [requires_corrective_lenses]. Khalid (without 156) sees "Work restriction applies — ask your supervisor"; Noura sees the code.
93. **Given** Faisal defers general_block_from to 2026-11-30 with a reason ≥ 30 chars **Then** saved. A second deferral gives `DEFERRAL_USED`. Deferring CSE-ENTRY-FIT gives `CRITICAL_CODE_NO_DEFERRAL`. Switching a blocked code back to warn gives `HOOK_POLICY_LOOSENING` (HK6-5).
94. **Given** an attach point with code `SCBA-FIT` (not in the catalogue) **Then** `unknown_code`: warn in transition, block after 2026-10-31, and a configuration error shown to Faisal (HK6-2).
95. **Given** Rafiq's CSE-ENTRY-FIT valid to 2026-10-31 **When** the clock is 2026-11-01 00:07 and PTW-0413 is Active (test) **Then** within 60 s PTW-0413 is Suspended `hook_not_met` (critical code, block) (HK6-8).
96. **Given** an assessment is accepted for a worker on a live permit **Then** `medical.fitness_changed` is published, Phase 3 re-evaluates within 60 s, and a cached result older than the event is not used (HK6-8).
97. **Given** the readiness report for ANIA-EXP **Then** per code it lists subjects, met/expiring counts, the not-met list with reason category per caller tier, and affected gates, WAPs and permits. Ahmed sees his tree only (HK6-9).
98. **Given** Noura (156, not 157) views PTW-0413's crew eligibility for a held worker **Then** she sees kind medical_fitness and code GEN-FIT but no reason_code. Faris sees "Not eligible — HSE check" (HK6-7; supersedes the capability-56 rule of DECISIONS #79).
99. **Given** Zaheer's shift planned to end 2026-10-09 19:00 **Then** met (valid_until covers the shift's date). A shift on 2026-10-10 gives not_met (HK6-10).
100. **Given** subject_type vehicle **Then** `unknown_code`.

**KPIs, warnings and AI**
101. **Given** the seed **When** KPIs for ANIA-EXP as of 2026-09-30 are requested **Then** K-89 98.1 %, K-90 97.5 %, K-91 96 · 87 · 76, K-92 71, K-93 3 · 1, K-94 88.9 %, K-95 83.3 %, K-96 41 (MF4).
102. **Given** the seed **When** KPIs for RBT-52 as of 2026-09-30 are requested by Faisal **Then** K-89 97.7 %, K-90 97.7 %, K-91 16 · 15 · 16, K-92 12, K-93 1 · 0, K-94 100.0 %, K-95 100.0 %, K-96 6. **By Sarah Then** K-93 shows "<5 · 0" (MK-3).
103. **Given** the monthly job on 2026-10-02 **Then** E14 is raised for RBT-52 and the QIMMA tree and not for ANIA-EXP, and E15 is raised for ANIA-EXP and the RAWABI tree and not for RBT-52 (§6.7).
104. **Given** K-89 = 9,795 / 10,000 **Then** displayed 98.0 % and E14 raised (MF5).
105. **Given** a K-91 breakdown by trade where a trade cell has 3 workers with gaps **Then** Noura and Ahmed see "<5". Faisal and Dr. Huda see 3 (MK-3).
106. **Given** T18 called for ANIA-EXP, Sep 2026, grouped by code **Then** it returns aggregates matching MF4, with no names, worker_no, outcomes per person, reasons, clinics or examiners, and with MK-3 applied even for Faisal (MK-4).
107. **Given** T9 with dimension `medical_gap_at_event` **Then** INC-ANIA-EXP-2026-0147 is in group "no" (MF8), and groups < 5 are returned as "<5".
108. **Given** a user asks the AI "which workers are medically unfit?" **Then** the AI refuses to list individuals, gives the K-91 aggregates, and points to the register for authorised roles (MK-6, Phase 1 AI-5).
109. **Given** the contractor filter RAWABI with subcontractors on ANIA-EXP **Then** K-89…K-96 equal the project values.
110. **Given** the frontend **Then** it renders KPI values exactly as returned (MK-1).

**Alerts**
111. **Given** Zaheer's line **Then** alerts went out 2026-09-09, 09-25 and 10-02 and are scheduled for 10-09. The 0-day alert goes to Noura and to Faisal (critical code) (MF6).
112. **Given** a renewal accepted before the 7-day step **Then** the 7- and 0-day steps are cancelled.
113. **Given** an alert text to Ahmed about Osman **Then** it reads "Fitness review due" with worker_no and date, and no restriction or reason (P6-7). Ahmed has tier 2, but alert channels carry tier 1 only.
114. **Given** the job re-runs on the same day **Then** no alert is sent twice.
115. **Given** the medical hook critical date 2026-10-08 **Then** the 7-day alert went out at enable on 2026-10-01, the 1-day alert on 2026-10-07 07:00, and the switch alert on 2026-10-08 00:00:30.

**Imports**
116. **Given** a clinic_register_file from SALAMA whose evidence email comes from salama-test.example, with 3 rows (valid; unknown worker; examiner not qualified) **When** dry-run **Then** row 1 OK, row 2 E01, row 3 E04, IDs masked. Commit creates 1 Accepted, verified assessment (IM6-3).
117. **Given** a contractor_file from Ahmed **Then** committed rows are Draft (no scan), never Accepted (IM6-3).
118. **Given** a row for a QIMMA worker in Ahmed's file **Then** E08.
119. **Given** a Validated batch 61 minutes old **Then** commit gives 409.
120. **Given** a row with permanently_unfit **Then** W04, and at commit Faisal is notified without detail.
121. **Given** a committed file **Then** the stored file is deleted and the audit keeps sha256 only (IM6-4).

**PDPL, permissions and audit**
122. **Given** Dr. Huda opens Jomar's scan with reason `verification` **Then** she gets a signed URL ≤ 5 min from the medical bucket, and a `sensitive_field_read` row with fields_read ["fitness_scan"]. Without a reason **Then** 422 (P6-5).
123. **Given** Noura **When** she opens a scan **Then** 403 (160).
124. **Given** Lina exports the worker fitness register **Then** it has status columns and the outcome category and restrictions (she holds 156), no reasons, no scans and no IDs. Fahad's export (S scope) has the same tier-2 columns; Sarah's export has aggregates only (§8.4, P6-7).
125. **Given** any free-text field **When** a prohibited-data hint applies **Then** the EN/AR hint is shown (P6-2).
126. **Given** an assessment Revoked more than 12 months ago **Then** the retention job deletes its scan, keeps the lines, and audits `retention_purge` (P6-8).
127. **Given** a worker demobilised more than 10 years ago with GEN-FIT lines and a NOISE-SURV line **Then** the GEN-FIT lines are anonymised, and the NOISE-SURV line is kept until 30 years (P6-8).
128. **Given** Faisal runs the data-subject report for Osman **Then** it lists assessments, outcomes, restrictions, holds and referrals, and the export is audited with purpose `data_subject_request` (P6-9).
129. **Given** a suspended contractor's HSE Rep **When** he submits a certificate **Then** 403; reads still work (Phase 0 rule 28).
130. **Given** a gate device **Then** it can call no 6a endpoint (capability 74 only).
131. **Given** every 6a mutation **Then** an audit row exists. Before/after values of sensitive fields are visible only to 157 holders (§4).
132. **Given** Sarah **Then** she sees K-89…K-96 tiles and charts C22–C24 as aggregates with MK-3, and no lists or names (MK-5).
133. **Given** a Phase 4 card check (VF-9) or a Phase 5 competence view (CK5-2) by Fahad **Then** a Fitness section lists each required medical code as cleared yes/no and nothing more (§8.5).
134. **Given** a worker status of Banned (Phase 2) **Then** his assessments are unchanged, and an unfit outcome never bans anyone (FA-16).
135. **Given** the UI in Arabic **Then** every 6a label, status, list value and error is shown with its AR text from §3/§4, and codes, numbers and dates are shown left-to-right inside the RTL layout.

## 10. Open questions for the HSE Manager

Each question has a default so the build can start. The default is the strictest reasonable choice unless it would stop the site from working.

1. **New role.** Default: a separate **Occupational Health Practitioner** role (site clinic physician or nurse) owns clinical-administrative data; HSE Officers see status and functional restrictions only. Alternative: HSE Officers record outcomes themselves. This is simpler, but it puts health data with HSE staff (a weaker PDPL position). Is there a site clinic with a physician and a nurse on both projects?
2. **HSE Manager access to tier 3 and scans** (capabilities 154, 157, 160). Default: yes, as the platform administrator and as fallback reviewer when no OH Practitioner is available. Restrict it to OH Practitioners only (strictest)?
3. **Contractor HSE Reps (the employer) seeing functional restrictions and the outcome category** (tier 2). Default: yes, because the employer must assign suitable duties. Status only?
4. **Worker purpose notice:** the text must come from client/legal (as Phase 0 Q6). Until it exists the seed uses a placeholder version "WPN-MED-0.1 (draft)". Who supplies it?
5. **GEN-FIT for everyone, checked at site gates.** Default: every contractor worker needs a pre-placement fitness certificate (24 months), and it is checked at site gates and zone gates from 2026-10-31 (warn until then). Is 24 months right (`VERIFY` R2), or does the client require annual medicals for all workers?
6. **Validities set as ASSUMPTION:** WAH-FIT 12, CSE-ENTRY-FIT 12, CRANE-OPERATOR-FIT 12, PLANT-OPERATOR-FIT 24, DRIVER-FIT 24, RESPIRATOR-FIT 12, HEAT-EXPOSURE-FIT 12, NOISE-SURV 12, SILICA-SURV 36, RAD-WORKER-FIT 12. Confirm or shorten (client CSM, NRRC, GACA).
7. **Critical codes and transition:** default critical = CSE-ENTRY-FIT, CRANE-OPERATOR-FIT, RESPIRATOR-FIT, RAD-WORKER-FIT (7 days); WAH-FIT is general (30 days) because 519 + 42 workers need it. Make WAH-FIT critical too (as Phase 5 makes WAH training critical)?
8. **Hold triggers:** default LTI, RWC, JTC and any heat illness (heat exhaustion or heat stroke, even first aid). Add MTC (any medical treatment), or remove RWC/JTC (the worker is still at work, just restricted)?
9. **Referral response time:** default 24 h. Is a physician available every day, including Fridays and nights? Night airside crews (GULFPAVE) may need 12 h, or a remote physician.
10. **Restriction review:** default every functional restriction is reviewed within 90 days (except corrective lenses), or the worker becomes "review due". Allow longer, up to 180 days, for long-term restrictions?
11. **Second opinion after permanent unfitness** (FA-12): default a different occupational physician must clear the worker. Acceptable, or should the original physician be able to reverse it?
12. **Retention:** default fitness outcomes 10 years after demobilisation and surveillance outcomes 30 years (international benchmark for occupational-disease claims); scans 12 months. Confirm with legal (`VERIFY` R4/R6).
13. **Contractor clinics:** default allowed only for GEN-FIT and only for their own contractor tree. Allow them for task codes too, or ban them altogether?
14. **Drug and alcohol testing:** not in 6a (KSA zero-tolerance policy, highly sensitive data). Do the client or contract require testing records (for example for crane operators and airside drivers)? If yes, it would be a separate, restricted add-on with result yes/no only.
15. **External certificates before verification:** default 0 h (never in force until verified with the clinic). Allow 24 h for non-critical codes?
16. **Exposure groups by trade:** default noise for plant operators and welders, silica for masons, radiation by manual assignment. Should others be added (e.g. steel_fixers cutting rebar for noise, labourers on concrete breaking for silica) once the 6e exposure monitoring exists?

## 11. Changes required in earlier specs (to be applied by the coordinator; this spec does not edit them)

### 11.1 `0-foundation.md` v1.0 → v1.1
1. **§3.8 roles:** add `oh_practitioner` (Occupational Health Practitioner / ممارس الصحة المهنية), scope = assigned project(s). Only the HSE Manager assigns it (rule 14: the HSE Officer's limited invite list does not include it).
2. **§5.10 matrix:** add an "OH Pract." column. For rows 1–19: 2 P, 4 P, 8 P, 11 P, 12 P, 15 P, 17 P, 19 ✓; every other row —.
3. **P2:** no change. Health data is already sensitive. P9 gains the "health-data breach" flag (P6-12).
4. Capability rows 146–165 continue the matrix (§5.15).

### 11.2 `1-dashboard.md` v1.4 → v1.5
1. **Matrix rows 20–45 for OH Pract.:** 29 P and 30 P (view injured-person identity and medical details, needed for RW-1); 31 P (incident register read); every other row —.
2. **Injury case events:** publish `incident.case_changed` (case created, category or nature changed, worker_id set or removed, rtw_date changed, incident Voided) at least once within 60 s. No Phase 1 rule changes.
3. **rtw_date warning:** saving an rtw_date earlier than the release date of the case's 6a hold, or while that hold is still Active, returns warning `RTW_BEFORE_CLEARANCE` (save allowed) (RW-2).
4. **§5.9 AI:** add T18 `get_occupational_health_kpis` (MK-4); T13 returns E14–E15; T9 gains dimension `medical_gap_at_event` with groups < 5 suppressed; AI-19 gains the section "Occupational health" (K-89…K-96, aggregates, MK-3); AI-5 restated for health data (MK-6).
5. **§6.9 / §7:** add E14 and E15 (§6.7 here), with the same monthly job, scope and recipients, plus the OH Practitioners.
6. **§8.1:** tiles K-89, K-90, K-91, K-94 (K-93 chip); the occupational-health band; charts C22–C24; `ExpiringItemKind` values from §8.2 here; action-panel items from §8.3 here.
7. **Seed:** the September 2026 GULFPAVE heat-exhaustion MTC (W1 #4 pattern) gets `worker_id` = WKR-000033 (Ganesh Shrestha). No KPI changes (worker_id drives no Phase 1 rule).

### 11.3 `2-access-permits.md` v1.3 → v1.4
1. **New setting `project_hook_requirements`** (list of {kind, code}; default []; HSE Manager; tighten only once 6a is enabled). ZP-4 step 8 evaluates it for every zone. **GC-4:** site gates also evaluate the project hook requirements after steps 1–5. 6a seeds [{medical_fitness, GEN-FIT}] on enable (HK6-2).
2. **HK-4:** the effective policy for kind `medical_fitness` comes from the hook policy state (kind medical_fitness) once 6a registers its provider on the project (HK6-1). The setting `hook_policy.medical_fitness` remains for projects without it. Medical hard stops (HK6-3) block in every stage.
3. **GC-7 / GC-12 display and logging for kind medical_fitness:** the guard sees only "Not eligible — HSE check / غير مؤهل — مراجعة السلامة" (DENIED), "HSE check due / مراجعة السلامة مستحقة" (warn) or "Work restriction applies — ask your supervisor" (met with conditions). The log stores `HOOK_NOT_MET` / `HOOK_NOT_MET_WARN` and the kind only (HK6-7).
4. **Default attach points** (seeded on 6a enable): Z-TC01 zone profile, trade crane_operator → `medical_fitness: CRANE-OPERATOR-FIT`; ADP categories apron and manoeuvring → `medical_fitness: DRIVER-FIT`.
5. **Events consumed by 6a:** gate-check rows (FH-8a) through the existing event stream; add `gate.check_recorded` (subject, gate, direction, result, admitted_despite_denial) if not already published. No behaviour change.
6. **P2-12** stays true: Phase 2 stores no medical data. Hook results are transient, and the log keeps only the kind.
7. **Seed:** convert two unnamed bulk workers into named workers within the existing counts (K-48 unchanged): WKR-000033 Ganesh Shrestha (GULFPAVE, labourer, S-AIR, NP, Iqama 2000001033, primary_language ne) and WKR-000034 Sunil Gurung (RAWABI, labourer, S-LAND, NP, Iqama 2000001034, primary_language ne). Trade, sites and mobilisation date of the converted rows are kept (DECISIONS #100).
8. AC21–AC23 (hook not available) stay valid on the Phase 2 seed, where no medical provider is registered.

### 11.4 `3-ptw.md` v1.2 → v1.3
1. **HK3-2 default hooks (medical):** entrant → CSE-ENTRY-FIT (existing); rescue_lead and rescue_member → CSE-ENTRY-FIT + RESPIRATOR-FIT; every crew member on a work_at_height section → WAH-FIT; crane_operator → CRANE-OPERATOR-FIT; driver → DRIVER-FIT; radiographer and rpo → RAD-WORKER-FIT; operator binding (HK4-9): crane categories → CRANE-OPERATOR-FIT, and hoist, MEWP, forklift, telehandler and plant categories → PLANT-OPERATOR-FIT (HK6-2).
2. **HK3-4 / P3-3 / DECISIONS #79:** the kind and code of medical results are shown to capability **156** holders and the reason only to **157** holders (replacing capability 56); everyone else sees "Not eligible — HSE check". Conditions (restrictions) follow HK6-7.
3. **HK3-5:** subscribe to `medical.fitness_changed`, `medical.hold_changed`, `medical.provider_changed` and `hook_policy.changed` (kind medical_fitness). Suspend live permits (`hook_not_met`) on hard stops and on not_met after the block date, within 60 s.
4. **crew_present events:** publish `ptw.crew_present_recorded` (permit, shift, worker_ids, at) for FH-8b, if not already published. No behaviour change.
5. HT-5 is unchanged; WBGT stays for 6b.
6. AC99 and the other Phase 3 ACs stay valid on the Phase 3 seed (no medical provider). The 6a behaviour is covered by ACs 59, 86–88, 95 and 98 here.

### 11.5 `4-third-party-cert.md` v1.1 → v1.2
1. **§3.14 hook policy state:** `kind` adds `medical_fitness` (owned by 6a; dates from the 6a settings `medical_hook_*`; policy actions by 6a capability 164).
2. **PC-13:** once 6a hooks are enabled on the project, "restriction reviewed" is recorded by an OH Practitioner (capability 157), and RF-7 creates the referral. The provider result `CARD_RESTRICTION_REVIEW` clears when that review is recorded. The flag stays visible to capability 119 holders as today.
3. **VF-9 combined view:** a Fitness section at tier 1 (each required medical code cleared yes/no), in the same single `cert_check_view` audit row.
4. **BD-3:** the catalogue disjointness check also covers 6a fitness codes (MC-2).
5. **§8.2:** `hook_block_date` also covers kind medical_fitness.

### 11.6 `5-training.md` v1.0 → v1.1
1. **CK5-2:** the competence view adds the tier-1 Fitness section (same audit row).
2. **CC / BD5-2:** course codes must also be disjoint from 6a fitness codes (MC-2).
3. No other change. HEAT-AWR and the GP-6 timing are untouched until 6b.

## Appendix A — Seed data (fictional; `seed_fake = true` on every row; all names, IDs, licences, clinics and certificate numbers are fake)

### A.1 Principles
- Builds on the Phase 0–5 seeds; no earlier seed row changes except the additions in §11 (two bulk workers converted to named workers; one Phase 1 case gets a worker_id). **Seed clock = `HSE_CLOCK_AT` = 2026-10-06T10:00:00+03:00.**
- `medical_register_from` = **2026-08-01** on ANIA-EXP and RBT-52. Earlier examinations exist as imported records (`clinic_register_file` from SHIFA, verified) so that validity dates are realistic. Requirement-plan lines are effective 2026-08-01.
- Medical hooks were enabled on both projects on **2026-10-01** (Faisal): stage `transition`, critical_block_from **2026-10-08**, general_block_from **2026-10-31**, no deferral. ACs that expect blocking for a non-hard-stop not_met advance the clock; hard stops block at the clock.
- In September 2026 no medical hook was evaluated (no provider before 2026-10-01). That is why MF3c's gate entry was GRANTED.
- Clinic names and domains end in `-test.example`; licence and certificate numbers contain `TEST`.
- **No re-trading** (DECISIONS #100). Trade populations at 2026-09-30 are those in Phase 5 A.9.
- **Crews of non-terminal permits at the clock:** every member is medically cleared with valid_until > 2026-10-13, except Zaheer Abbas (CRANE-OPERATOR-FIT expiring 2026-10-09, PTW-0410). Phase 3/5 tests that assert complete warning lists run on their own seeds (as Phase 5 §11.3–11.4).
- **Data note for the coordinator:** Phase 5 A.5/A.6 has Imran Hussain attending WAH session TRS-ANIA-EXP-2026-00031 on 2026-09-20, but Phase 1 records him as away from work 2026-09-09…09-28 (LTI, rtw 2026-09-29). 6a does not change either record and adds no gate or crew_present event for him during his hold, so MF3a stays compliant. Training attendance is not a work-activity event in FH-8.

### A.2 New users (Phase 0 seed additions)
| Name / الاسم | Email | Mobile | Employer | Role · scope | Examiner link |
|---|---|---|---|---|---|
| Dr. Huda Al-Mansour / د. هدى المنصور | huda.mansour@example.com | +966500000017 | client (site clinic contract) | oh_practitioner · ANIA-EXP, RBT-52 | EXR-0001 |
| Grace Villanueva / غريس فيلانويفا | grace.villanueva@example.com | +966500000018 | client (site clinic contract) | oh_practitioner · ANIA-EXP, RBT-52 (nurse) | — |

### A.3 Medical providers
| Code | Name / الاسم | Kind | Status | MOH licence → valid | Channels | Notes |
|---|---|---|---|---|---|---|
| SHIFA-ANIA | Shifa Occupational Health Services — ANIA-EXP site clinic (test) / شفاء لخدمات الصحة المهنية — عيادة موقع مطار النور (تجريبي) | site_clinic [ANIA-EXP] | Approved 2026-07-20 (Faisal) | MOH-TEST-FAC-0457 → 2027-12-31 | — | site records |
| SHIFA-RBT | Shifa Occupational Health Services — RBT-52 site clinic (test) / شفاء — عيادة موقع برج الرياض (تجريبي) | site_clinic [RBT-52] | Approved 2026-07-20 | MOH-TEST-FAC-0458 → 2027-12-31 | — | |
| SALAMA | Al-Salama Medical Polyclinic (test) / مجمع السلامة الطبي (تجريبي) | external_clinic | Approved 2026-07-25 | MOH-TEST-FAC-1188 → 2027-03-31 | portal verify.salama-test.example; email fitness@salama-test.example | Jomar's DRIVER-FIT |
| RAWABI-CC | Rawabi Camp Clinic (test) / عيادة سكن الروابي (تجريبي) | contractor_clinic (RAWABI) | Approved | MOH-TEST-FAC-2203 → 2027-05-31 | email clinic@rawabi-cc-test.example | GEN-FIT only (MF7a–b) |
| QUICKMED | QuickMed Clinic (test) / عيادة كويك ميد (تجريبي) | external_clinic | **Suspended 2026-09-25** (Faisal; "certificate QM-TEST-26-0917 not found in clinic records") | MOH-TEST-FAC-3310 → 2027-01-31 | email info@quickmed-test.example | MF2, MF7e |

### A.4 Examiner registrations
| No. | Name | Class | SCFHS licence → valid | Providers | User |
|---|---|---|---|---|---|
| EXR-0001 | Dr. Huda Al-Mansour / د. هدى المنصور | occupational_physician | SCFHS-TEST-14-0457 → 2027-06-30 | SHIFA-ANIA, SHIFA-RBT | huda.mansour |
| EXR-0002 | Dr. Arun Menon / د. أرون مينون | physician | SCFHS-TEST-11-2210 → **2026-10-20** | SHIFA-ANIA | — (MF6, MF7d) |
| EXR-0003 | Dr. Samir Khoury / د. سمير خوري | physician | SCFHS-TEST-09-7781 → 2028-01-31 | SALAMA | — |
| EXR-0004 | Dr. Faheem Qureshi / د. فهيم قريشي | physician | SCFHS-TEST-16-0315 → 2027-04-30 | RAWABI-CC | — |
| EXR-0005 | Dr. Nadia Rahman / د. نادية رحمن | occupational_physician | SCFHS-TEST-12-0921 → 2027-11-30 | SHIFA-RBT, SHIFA-ANIA | — (second-opinion tests, AC42) |

### A.5 Requirement plan (effective 2026-08-01)
| Line | Applies to | Code | Due | Counted |
|---|---|---|---|---|
| MRL-<p>-001 | all_workers | GEN-FIT | 0 | yes |
| MRL-<p>-002 | trade scaffolder, steel_erector, rigger | WAH-FIT | 0 | yes |
| MRL-<p>-003 | trade crane_operator | CRANE-OPERATOR-FIT | 0 | yes |
| MRL-<p>-004 | trade plant_operator | PLANT-OPERATOR-FIT | 0 | yes |
| MRL-<p>-005 | trade driver | DRIVER-FIT | 0 | yes |
| MRL-<p>-006 | exposure_group noise_85 | NOISE-SURV | 30 | yes |
| MRL-<p>-007 | exposure_group silica_rcs | SILICA-SURV | 30 | yes |
| MRL-<p>-008 | exposure_group ionising_radiation | RAD-WORKER-FIT | 0 | yes |
| MRL-<p>-H01 | project_hook (Phase 2) | GEN-FIT | 0 | yes (de-duplicated with 001) |
| MRL-ANIA-EXP-H02 | adp_category apron, manoeuvring | DRIVER-FIT | 0 | yes (de-duplicated with 005) |
| MRL-RBT-52-H03 | zone Z-TC01, trade crane_operator | CRANE-OPERATOR-FIT | 0 | yes (de-duplicated with 003) |
| MRL-<p>-E01…E07 | crew_role entrant / rescue_lead / rescue_member → CSE-ENTRY-FIT; rescue roles → RESPIRATOR-FIT; WAH-section crew → WAH-FIT; crane_operator → CRANE-OPERATOR-FIT; driver → DRIVER-FIT; radiographer, rpo → RAD-WORKER-FIT; operator binding → CRANE-/PLANT-OPERATOR-FIT | — | 0 | no (enforcement-only) |

Exposure-group profiles: trade defaults (noise_85 for plant_operator and welder; silica_rcs for mason). Vinod Menon (WKR-000020, trade `other`, DECISIONS #70) has ionising_radiation added manually by Noura on 2026-08-01.

### A.6 Named assessments (examiner EXR-0001 at the site clinic unless stated; lines → valid_until)
| Worker | Assessment · type · examined | Lines | State at clock |
|---|---|---|---|
| WKR-000001 Imran Hussain (NAJD scaffolder) | MFA-ANIA-EXP-2026-00287 · pre_placement · 2026-08-20 | GEN-FIT fit → 2028-08-19; WAH-FIT fit → 2027-08-19 | superseded by 00412 |
| | MFA-ANIA-EXP-2026-00412 · return_to_work (hold 00015) · 2026-09-28, accepted 10:42 | GEN-FIT fit → **2028-09-27**; WAH-FIT fit → **2027-09-27** | governing (MF3a) |
| WKR-000002 Rajesh Nair (GULFPAVE plant_operator; ADP) | MFA-ANIA-EXP-2026-00021 · periodic · 2026-01-12 | GEN-FIT → 2028-01-11; PLANT-OPERATOR-FIT → 2028-01-11; DRIVER-FIT → 2028-01-11; NOISE-SURV → 2027-01-11 | met |
| WKR-000003 Jomar Santos (GULFPAVE driver) | SALAMA SAL-TEST-26-0220 · periodic · 2026-02-20 (examiner EXR-0003), submitted by Ahmed, accepted and verified by Dr. Huda 2026-02-23 | DRIVER-FIT fit_with_restrictions [requires_corrective_lenses] → 2028-02-19; GEN-FIT fit → 2028-02-19 | met with condition (MF1d) |
| WKR-000005 Mahmoud Fathy · WKR-000007 Saad Al-Dosari · WKR-000013 Tariq Mahmood (ADP holders) | MFA-ANIA-EXP-2026-00031 / 00032 / 00033 · periodic · 2026-01-20 | GEN-FIT → 2028-01-19; DRIVER-FIT → 2028-01-19 | met |
| WKR-000009 Osman Idris (NAJD rigger) | MFA-ANIA-EXP-2026-00055 · periodic · 2026-03-01 | WAH-FIT fit → 2027-02-28; GEN-FIT fit → 2028-02-29 | WAH line governing but negated |
| | MFA-ANIA-EXP-2026-00398 · periodic · 2026-09-15 | GEN-FIT fit_with_restrictions [no_work_at_height], review 2026-12-15 → **2026-12-15** | WAH-FIT `RESTRICTION_CONFLICT` (MF2) |
| WKR-000014 Prakash Thapa (NAJD welder) | MFA-ANIA-EXP-2026-00220 · periodic · 2026-05-04 | GEN-FIT → 2028-05-03; NOISE-SURV → 2027-05-03 | met |
| WKR-000015 Ahmed Raza · WKR-000017 Biju Thomas · WKR-000018 Salem Al-Harthi · WKR-000004 Abdul Karim Mia | MFA-ANIA-EXP-2026-00060…00063 · periodic · 2026-02-10 | GEN-FIT → 2028-02-09 | met |
| WKR-000016 Kamal Hossain (entrant) | MFA-ANIA-EXP-2026-00118 · change_of_task · 2026-03-02 | GEN-FIT → 2028-03-01; CSE-ENTRY-FIT → **2027-03-01** | met (MF2) |
| WKR-000019 Zaheer Abbas (crane operator) | MFA-ANIA-EXP-2025-00391 · periodic · 2025-10-10 | GEN-FIT → 2027-10-09; CRANE-OPERATOR-FIT → **2026-10-09** | expiring (MF1a) |
| WKR-000020 Vinod Menon (radiographer) | MFA-ANIA-EXP-2026-00150 · periodic · 2026-04-01 | GEN-FIT → 2028-03-31; RAD-WORKER-FIT → 2027-03-31 | met |
| WKR-000021 Rafiq Islam (rescue lead) | MFA-ANIA-EXP-2025-00402 · periodic · 2025-11-01 | GEN-FIT → 2027-10-31; CSE-ENTRY-FIT → **2026-10-31**; RESPIRATOR-FIT → **2026-10-31** | met; 30-day alert sent 2026-10-01 |
| WKR-000033 Ganesh Shrestha (GULFPAVE labourer) | MFA-ANIA-EXP-2026-00170 · pre_placement · 2026-04-20 | GEN-FIT → 2028-04-19 | superseded by 00405 |
| | MFA-ANIA-EXP-2026-00405 · return_to_work (hold 00019) · 2026-09-23, accepted 06:31 | GEN-FIT fit_with_restrictions [no_heat_exposure], review 2026-10-07 → **2026-10-07** | expiring; review due 10-08 (MF2) |
| WKR-000034 Sunil Gurung (RAWABI labourer) | MFA-ANIA-EXP-2026-00092 · periodic · 2026-02-14 | GEN-FIT → 2028-02-13 | hold 00027 (MF3d) |
| NAJD bulk worker (fixture `FX-QM`) | QUICKMED QM-TEST-26-0917 · examined 2026-09-08, submitted 2026-09-22 by Ahmed | GEN-FIT fit | **Rejected** — not_found 2026-09-24 (Dr. Huda, email channel) → hard stop |
| WKR-000101 Imtiaz Ahmed · WKR-000108 Joel Bautista · WKR-000105 Hamza Al-Shehri (RBT-52) | MFA-RBT-52-2026-00041 / 00042 / 00043 · periodic · 2026-05-05 | GEN-FIT → 2028-05-04; WAH-FIT → 2027-05-04 | met |
| WKR-000102 Ali Hassan (RBT-52 crane operator) | MFA-RBT-52-2026-00061 · periodic · 2026-06-14 | GEN-FIT → 2028-06-13; CRANE-OPERATOR-FIT → 2027-06-13 | met |
| WKR-000106 Dinesh Kumar (RBT-52 welder) · WKR-000107 Rohan Fernando · WKR-000103 Ramon Cruz | MFA-RBT-52-2026-00070…00072 · periodic · 2026-06-20 | GEN-FIT → 2028-06-19 (Dinesh also NOISE-SURV → 2027-06-19) | met |

Bulk crew members named on non-terminal Phase 3 permits hold in-force lines for every medical code their crew roles need, with valid_until > 2026-10-13 (A.1).

### A.7 Holds and referrals (named)
| Record | Data | Status at clock |
|---|---|---|
| MFH-ANIA-EXP-2026-00015 | Imran Hussain; rtw_after_injury; source INC-ANIA-EXP-2026-0147-P1; started 2026-09-09 08:00 | Released 2026-09-28 10:42 by 00412; compliant |
| MFR-ANIA-EXP-2026-00012 / MFH-ANIA-EXP-2026-00016 | RAWABI bulk labourer (fixture `FX-BREACH`); observed_unwell; remove_from_work; raised 2026-09-11 16:20 by Omar; gate entry G-ANIA-01 2026-09-12 06:52 GRANTED (an existing Phase 2 bulk gate row of that worker) | Assessed and released 2026-09-13 09:00 (late; not compliant; E15) |
| MFH-ANIA-EXP-2026-00019 | Ganesh Shrestha; heat_illness; source: the 2026-09-22 GULFPAVE heat-exhaustion case (§11.2 item 7); started 2026-09-22 14:35 | Released 2026-09-23 06:31; compliant |
| MFR-ANIA-EXP-2026-00031 / MFH-ANIA-EXP-2026-00027 | Sunil Gurung; observed_unwell; note "Dizzy and sweating on level 2 at 08:30"; remove_from_work; raised 2026-10-06 08:40 by Fahad; due 2026-10-07 08:40 | **Open / Active** |
| Three ANIA-EXP bulk referral holds (labourers) raised 2026-09-29 15:00, 2026-09-30 10:00 and 2026-09-30 13:30 | — | Active at 09-30 (K-93 3 · 1); released 2026-10-01/02 (fit) |
| One RBT-52 bulk referral hold (QIMMA labourer) raised 2026-09-30 11:00 | — | Active at 09-30 (K-93 1 · 0); released 2026-10-01 |

### A.8 Named worker additions (K-48 unchanged)
WKR-000033 Ganesh Shrestha / غانيش شريستا and WKR-000034 Sunil Gurung / سونيل غورونغ, as in §11.3 item 7. Phase 5 training records: the bulk rows they were converted from keep their Phase 5 bulk records (IND-GENERAL and HEAT-AWR met), so Phase 5 TR7 is unchanged.

### A.9 Bulk volumes (as of 2026-09-30, reproducing MF4)

Counted requirements are given as applicable · met (incl. expiring) · gap. Requirements that are not yet due are excluded from all three.

**ANIA-EXP** (3,412 Mobilised contractor_worker deployments):

| Line | Applicable · met · gap | Gap reasons |
|---|---|---|
| GEN-FIT | 3,412 · 3,360 · 52 | missing 33, verification failed 1 (FX-QM), expired 10, hold 3, temporarily unfit 5 (labourers and carpenters only) |
| WAH-FIT (scaffolder 160, steel_erector 313, rigger 46) | 519 · 504 · 15 | missing 8, expired 4, restriction conflict 2 (Osman Idris + 1 SAHARA scaffolder), temporarily unfit 1 (steel_erector) |
| CRANE-OPERATOR-FIT | 14 · 14 · 0 | incl. Zaheer (expiring) |
| PLANT-OPERATOR-FIT | 158 · 155 · 3 | expired 3 |
| DRIVER-FIT (drivers 214 + ADP holders who are not drivers 86: plant_operator 70, electrician 12, supervisor 3, engineer 1) | 300 · 294 · 6 | missing 4, expired 2 |
| NOISE-SURV (plant_operator 158 + welder 320 = 478; not yet due 22, i.e. mobilised on or after 2026-09-01) | 456 · 442 · 14 | missing 9, expired 5 |
| SILICA-SURV (mason 267; not yet due 12) | 255 · 249 · 6 | missing 6 |
| RAD-WORKER-FIT | 1 · 1 · 0 | Vinod Menon |
| **Total** | **5,115 · 5,019 · 96** | |

- Deployments with ≥ 1 gap: **87**. 9 workers have two gaps (GEN-FIT missing together with WAH-FIT missing 4, NOISE-SURV missing 3, or DRIVER-FIT missing 2). The hold and temporarily-unfit GEN-FIT gaps fall on workers with no other line.
- Hook-code gaps: **76**.
- K-92 = 71 lines expiring 2026-09-30…10-30 (incl. Zaheer and Ganesh).
- K-96 = 41 deployments with reviewable restrictions in force (incl. Osman, Ganesh and the SAHARA scaffolder; Jomar is excluded, since corrective lenses need no review).
- September holds released 9 (Imran, Ganesh, 7 referral holds); 1 breach (MFH-00016).
- September referrals: 14 raised (10 with remove_from_work: 7 released in September + 3 active at 09-30; 4 without), 2 with open windows at the end of 09-30, 12 counted, 10 on time.

**RBT-52** (654):

| Line | Applicable · met · gap | Gap reasons |
|---|---|---|
| GEN-FIT | 654 · 640 · 14 | missing 9, expired 4, hold 1 |
| WAH-FIT (scaffolder 24, rigger 18) | 42 · 40 · 2 | missing 1, expired 1 |
| CRANE-OPERATOR-FIT | 6 · 6 · 0 | incl. Ali Hassan |
| NOISE-SURV (welder 1) | 1 · 1 · 0 | Dinesh Kumar |
| **Total** | **703 · 687 · 16** | |

- Deployments with ≥ 1 gap: **15** (one rigger is missing both GEN-FIT and WAH-FIT). Hook-code gaps: **16**. K-92 = 12; K-96 = 6.
- September holds released 2 (both compliant); referrals raised 4 (1 with an open window), 3 counted, 3 on time.

The generator assigns only health profiles, assessments, holds and referrals. It never changes deployments, trades, gate counts or Phase 1–5 KPIs.

### A.10 Settings
All 6a settings are at the §3.12 defaults; `medical_register_from` = 2026-08-01 (both projects); no `fitness_validity_months` overrides; `unverified_fitness_acceptance_hours` = 0; `medical_compliance_warning_pct` = 98.0; `worker_purpose_notice_version` = "WPN-MED-0.1 (draft)". Phase 2 `project_hook_requirements` = [{medical_fitness, GEN-FIT}] on both projects (seeded on enable, 2026-10-01).

## Change log

| Version | Date | Author | Change |
|---|---|---|---|
| v1.0 | 2026-10-08 | HSE Consultant Agent | First issue. §1–§11 and Appendix A. New role `oh_practitioner` with three access tiers; fitness code catalogue (11 codes) and restriction/exposure lists; providers and examiners; requirement plan and health profiles; site-clinic and external assessments with verification; holds, referrals and return to work; the `medical_fitness` hook provider with the Phase 4 warn → block mechanism; imports. Capabilities 146–165, KPIs K-89…K-96, warnings E14–E15, AI tool T18, charts C22–C24. Earlier-spec changes listed in §11, not yet applied: 0-foundation v1.1, 1-dashboard v1.5, 2-access-permits v1.4, 3-ptw v1.3, 4-third-party-cert v1.2, 5-training v1.1. |
