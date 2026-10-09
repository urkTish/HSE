# Module Spec — Phase 6d: Field Assurance (inspection and audit checklist library, inspection and audit programme, phone execution with findings and stop rules, audit scoring and trends, toolbox talks with attendance and briefing campaigns, K-34/K-35/K-36 register switch)

**Version:** v1.2 · **Date:** 2026-10-09 · **Author:** HSE Consultant Agent · **Status:** Draft. The HSE Manager asked to proceed without waiting for approval and will review the choices later (§10).
**Builds on:**
- `0-foundation.md` v1.1: projects, sites, zones (zone_type, airside attributes), engagement tree, roles, scoping legend, `week_start`, rules 28, 35 and 48, PDPL P1–P13, the capability matrix (6c ends at 190).
- `1-dashboard.md` v1.6: daily returns (§3.1, `toolbox_talks` / `toolbox_attendees`, import warnings W01–W07), inspection plans and inspections (§3.7, §4.4, N-1…N-5), CAs (§3.8, CA-1…CA-8, `ca_due_days`), K-34, K-35, K-35b, K-36, K-R2/K-R4/K-R8, warnings E1–E19, AI tools T1–T20 (T8 `list_inspections_summary`, T13), AI-19, charts up to C30, the action panel and the expiring-items endpoint, P1-8, list I (inspection types), list O (observation categories), seed A.3 and W1.
- `2-access-permits.md` v1.5: workers (`primary_language`), deployments and `person_type`, access-card QR tokens (§3.20 kind `AC`), P2-7, P2-8.
- `3-ptw.md` v1.4: suspension reason `stop_work` (list SR), SH-2, SH-3, SH-4 crew briefing, PTW audits (§3.15, list A, AU-1…AU-8, §6.8 score) as the pattern for item scoring, excavation field records.
- `4-third-party-cert.md` v1.2: equipment stickers (QR kind `EQ`), scaffold tags (§3.8), manual defects (DF-10).
- `5-training.md` v1.2: attendance with device signature or signed sheet (§3.7, SS-8), language rule AT-6, BD5-5, TH-5 and the register switch TH-6/TH-7 (pattern for SRC rules).
- `6b-heat-stress.md` v1.0 (welfare checks, list HW) and `6c-emergency-drills.md` v1.0 (asset checks, list EC; format template; numbering ends at capability 190, K-109, E19, T20, C30, QR kinds `EA` / `MP`).
- `docs/DECISIONS.md` #1–#168, in particular #20 (inspection visibility), #53 (tier-1 trees), #78 (export audit), #124 (no SMS channel), #157 (programme lines computed on read).

**Numbering taken by 6d:** capabilities **191–201**; KPIs **K-110…K-117** (and new definitions of K-34/K-35 inputs and K-36 sources); warnings **E20–E21**; AI tool **T21**; charts **C31–C33**; CA source_type `field_audit`; daily-return import warning **W08**. No new QR kind (attendance uses the Phase 2 access card, kind `AC`).

**Covers (build order):**
1. 6d.1 Checklist template library: org-wide, versioned, bilingual, item types, weights, critical items, stop rules.
2. 6d.2 Inspection programme: Phase 1 plans gain a template, rotation by zone or contractor and a quarterly frequency; contractor coverage.
3. 6d.3 Execution on phone: answers, photos, offline drafts, findings → Phase 1 CAs, repeat findings, critical-item stop rules and stop-work orders.
4. 6d.4 HSE audits (contractor HSE audits, ISO 45001 internal audits): audit programme, rating scale, grading, NC findings → CAs, report.
5. 6d.5 Toolbox talks: topic library, talk record, named attendance by card scan or list, signatures, language, suggestions, briefing campaigns linked to incidents.
6. 6d.6 Register switch for K-34/K-35 (template required) and K-36 (toolbox register), no double counting.
7. 6d.7 KPIs, warnings, dashboard and AI.

**Not in 6d:**
- PTW audits (Phase 3 §3.15, list A, K-61) and the permit crew briefing (Phase 3 SH-4). They keep their own forms and KPIs.
- Scaffold tagging and inspection before use (Phase 4 §3.8), equipment certificates and pre-use certification (Phase 4), excavation inspections recorded on a permit (Phase 3 field records).
- Heat welfare checks and midday-ban patrols (6b), emergency asset checks and drill evaluation (6c). They keep their fixed lists in v1.0 (§10 Q7).
- Environmental monitoring (6e will use 6d templates for environmental inspections), lessons-learned bulletins (6f; 6d links them when 6f exists), contractor scorecard (6g), document read-and-acknowledge (deferred, `6-proposal.md` §3).
- Training and inductions (Phases 5 and 2). A toolbox talk is never a training record or training hours (BD5-5, TH-5).

Conventions: `VERIFY` = clause or number to confirm against the current official text or the client's procedure. `ASSUMPTION` = Consultant default; the HSE Manager may override it (§10). "Must" = enforced server-side. Rule prefixes: TPL templates, ISP inspection programme, EXE execution, FND findings and stop rules, AUD audits, TBT toolbox talks, CMP campaigns, SRC register switch, FM KPIs/AI, P6d- PDPL, BD6d boundary. Error codes are stable strings (Phase 0 rule 48). Times are local Asia/Riyadh unless marked UTC.

**The principle that shapes this module:** a checklist is evidence, not a form. Every score is computed from item answers, a critical failure always fails the inspection whatever the score, a non-compliance creates a tracked action, and a talk counts as a briefing only for workers who were named, present and understood the language.

---

## 1. Purpose

Field inspections and toolbox talks are the two forms supervisors fill most often on a KSA site, and the two the HSE Manager trusts least. Today Phase 1 records an inspection as two numbers (`items_checked`, `items_compliant`) and toolbox talks as two numbers on the daily return. The HSE Manager cannot see which items fail most, whether the same guardrail fails every week on Pier B, whether a critical failure stopped the work, whether the scaffold contractor was audited this half-year, or whether the night crew on the apron were actually briefed after last week's LTI in a language they understand.

Phase 6d provides:
- an org-wide, versioned, bilingual checklist library (general site, scaffold area, excavation, electrical, lifting gear, housekeeping, airside FOD walk, fire safety, welfare, environmental, plant, PPE, leadership walk, contractor HSE audit, ISO 45001 internal audit) with scored, critical and informational items;
- inspection plans that use a template and rotate through zones or contractors, and a weekly contractor coverage measure;
- phone execution that works through short loss of signal, with photos, automatic findings and Phase 1 CAs, repeat-finding escalation and a stop-work order when a critical item fails;
- contractor and system audits with a programme, a 0–3 rating scale, grades and NC findings;
- a toolbox-talk register with a topic library, named attendance (card scan or list), signatures, language check, topic suggestions from incidents and failed items, and mandatory briefing campaigns;
- K-34/K-35 fed only by template-based answers and K-36 fed only by the register from a switch date (no double counting, as Phase 5 TH-6);
- KPIs K-110…K-117, warnings E20–E21, AI tool T21 and charts C31–C33.

## 2. Regulatory basis

| # | Source | What it drives here |
|---|---|---|
| R1 | **MHRSD Labour Law and OSH Regulations**: employer duty to inform workers of workplace hazards and protective measures before and during work, and to inspect workplaces and correct hazards. `VERIFY` article numbers and any NCOSH inspection guidance | Toolbox register, inspection programme, CA follow-up |
| R2 | **ISO 45001:2018** cl. 7.3 (awareness), 7.4 (communication, language), 9.1 (monitoring), 9.2 (internal audit programme, auditor objectivity), 10.2 (nonconformity and corrective action) | Talks and language, programme, audits, NC grading, CAs |
| R3 | **ISO 19011:2018** (auditing management systems): audit programme, auditor independence, findings as nonconformities and opportunities for improvement | AUD rules, list AF |
| R4 | **OSHA 29 CFR 1926.20(b)(2)** (frequent and regular inspections by competent persons), **1926.21(b)(2)** (instruct each employee in recognising and avoiding hazards), 1926.451(f)(3), 1926.651(k), 1926.251(a)(6). International benchmark `VERIFY` paragraph letters | Inspection frequency defaults, item content of seeded templates |
| R5 | **ICAO Annex 14 / Doc 9137**, **FAA AC 150/5210-24** (FOD management) as benchmark, **GACAR Part 139** and the airport operator's Works Safety Plan (FOD walks, airside housekeeping) `VERIFY` the operator's FOD inspection frequency | FOD template, airside-only items, critical FOD items |
| R6 | **Saudi Civil Defense** / **SBC 801** fire safety during construction (housekeeping, combustibles, extinguishers) `VERIFY` | Fire safety template items |
| R7 | **Client standards** flowed down (PMC HSE plan: weekly inspections per contractor, monthly audits, weekly toolbox talk per worker; Saudi Aramco CSM inspection checklists and weekly safety meetings where applicable `VERIFY`) | Tighten-only settings, K-113, K-116 |
| R8 | **PDPL** (attendance places a named person at a place and time; signatures; photos) | P6d rules |

Strictest-wins applied in this spec (and why):
- **A critical failure fails the inspection whatever the score** (FND-6). A 95 % score with an open slab edge is not a pass.
- **Severity can be raised, never lowered** (FND-1), as Phase 3 audits.
- **Every worker is briefed at least weekly** (K-116, R7). Many client plans ask for a daily pre-start talk; the daily talk is recorded the same way and simply raises reach.
- **A talk in a language the worker does not understand is not a briefing** (TBT-6, R2 cl. 7.4). It still counts as delivered (K-36), not as reach (K-116) or campaign evidence.
- **Auditors do not audit their own work** (AUD-3, R3).
- **Programme intervals and pass marks only tighten** (settings §3.14).

## 3. Entities & fields

PDPL column: **none / personal / sensitive** (Phase 0 P1–P2). Every entity carries the Phase 0 system fields, is audited (Phase 0 rule 35) and stores `seed_fake`. AR labels are shown in the UI.

### 3.1 Checklist template (org-wide, versioned) — نموذج قائمة التحقق

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| template_code | رمز النموذج | string(8) | Y | `^[A-Z]{2,8}$`, stable across versions | GSI | none |
| version | الإصدار | int | sys | 1, 2, …; one Published version per code | 3 | none |
| kind | النوع | enum | Y | `inspection` تفتيش · `audit` تدقيق | inspection | none |
| inspection_type / audit_type | نوع التفتيش / نوع التدقيق | enum | Y (by kind) | Phase 1 list I / list AT | general_site | none |
| title_en / title_ar | العنوان | string(150) ×2 | Y | both required to publish | General site inspection / التفتيش العام على الموقع | none |
| sections | الأقسام | list {code, title_en, title_ar, order} | Y | ≥ 1 | [A Access & edges, B Electrical, …] | none |
| zone_types | أنواع المناطق | enum[] | Y | ⊆ {airside, landside, other}; `TEMPLATE_NOT_APPLICABLE` outside | [airside, landside, other] | none |
| project_ids | المشاريع | FK[] | N | empty = all projects (client-specific templates) | [] | none |
| pass_mark_pct | درجة النجاح | decimal(4,1) | Y | 50.0–100.0; default 85.0 | 85.0 | none |
| review_due_on | موعد المراجعة | date | sys | published_at + 24 months − 1 day | 2028-03-31 | none |
| change_note | ملاحظة التغيير | text(500) | cond. | required for version ≥ 2 | GSI-05 split into slab edge and floor openings | none |
| authored_by / published_by / published_at | أعدّه / نشره / تاريخ النشر | FK / FK / timestamptz | sys | publisher holds 193 | Noura / Faisal / 2026-04-01 | personal |
| status | الحالة | enum | Y | §4.1 | published | none |

### 3.2 Template item — بند قائمة التحقق

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| item_code | رمز البند | string(12) | Y | `<template_code>-<nn>`; unique within the version; kept across versions while the meaning is unchanged | GSI-05 | none |
| section_code / order | القسم / الترتيب | string / int | Y | — | A / 5 | none |
| text_en / text_ar | نص البند | string(300) ×2 | Y | both required to publish | Slab edges and floor openings protected (guardrail, toe-board or fixed cover) / حواف البلاطات والفتحات محمية | none |
| guidance_en / guidance_ar | إرشاد | text(1000) | N | — | Guardrail top 0.95–1.15 m, mid-rail, toe-board ≥ 150 mm | none |
| item_type | نوع البند | enum | Y | list IT | yes_no | none |
| weight | الوزن | int | Y | 1–5; default 1, critical default 3 | 3 | none |
| critical | بند حرج | bool | Y | only on scored types | true | none |
| stop_rule | قاعدة الإيقاف | enum | Y | `none` · `stop_work` إيقاف العمل; `stop_work` only when critical | stop_work | none |
| na_allowed | يسمح بـ "لا ينطبق" | bool | Y | — | false | none |
| photo_required_on_fail | صورة عند عدم المطابقة | bool | Y | forced true when critical | true | none |
| default_severity | الخطورة الافتراضية | enum | cond. | non-critical scored items: `minor` · `major` | — | none |
| airside_only | للجانب الجوي فقط | bool | Y | hidden and not applicable in non-airside zones | false | none |
| numeric_rule | قاعدة القيمة | {unit, min, max} | cond. | numeric only; compliant ⇔ min ≤ value ≤ max | {ms, 0, 40} | none |
| options | الخيارات | list {code, label_en, label_ar, maps_to compliant / non_compliant / info} | cond. | single_select only, 2–8 options | — | none |
| suggested_ca_en / _ar / suggested_control_level | الإجراء المقترح / مستوى التحكم | text(300) / enum | N | Phase 1 control levels | Install guardrail and toe-board / engineering | none |
| reference | المرجع | string(80) | N | standard clause, shown to inspector | OSHA 1926.501(b)(1) | none |

### 3.3 Inspection plan — Phase 1 §3.7 plan, fields added by 6d

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| template_code | النموذج | string | cond. | a template of kind inspection whose inspection_type = plan.inspection_type; required for new plans from `inspection_template_required_from` | GSI | none |
| frequency | التكرار | enum | Y | Phase 1 values + `quarterly` ربع سنوي (same weekday rule as monthly: the start date's day of month every 3 months, clamped) | weekly | none |
| rotation | التدوير | enum | Y | `none` · `zones` · `engagements` (ISP-2) | zones | none |
| rotation_list | قائمة التدوير | FK[] | cond. | 2–20 zones of the plan site, or engagements on the site | [Z-PIERB, Z-MSCP, Z-LAY1] | none |

### 3.4 Checklist response (one per inspection or audit) — إجابات قائمة التحقق

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| response_id / client_uuid | المعرّف / معرّف الجهاز | UUID / UUID | sys / Y | client_uuid unique per project (idempotency, EXE-6) | — | none |
| owner | المصدر | {type: inspection / audit, id} | sys | exactly one owner | INS-ANIA-EXP-2026-01377 | none |
| template_id / version | النموذج / الإصدار | FK / int | sys | pinned at start (EXE-1) | GSI v3 | none |
| started_at / completed_at | البدء / الإنجاز | timestamptz | Y | device time; completed_at ≤ received_at + 5 min (`CLOCK_SKEW`); completed_at ≥ received_at − `offline_submit_max_hours` (`OFFLINE_SUBMIT_TOO_LATE`) | 2026-09-24 09:12 / 09:41 | none |
| received_at / offline_delay_min | وقت الاستلام / التأخير | timestamptz / int | sys | delay = minutes(completed_at, received_at) when > 15 | — | none |
| answers | الإجابات | list §3.5 | Y | EXE-2 | — | personal (photos possible) |
| applicable_count / compliant_count | البنود المنطبقة / المطابقة | int / int | sys | §6.2 | 21 / 19 | none |
| applicable_weight / earned_weight | الوزن المنطبق / المحقق | decimal(8,3) ×2 | sys | §6.2 | 29.000 / 27.000 | none |
| score_pct | النسبة | decimal(5,1) | sys | §6.2 | 93.1 | none |
| critical_fail_count | إخفاقات حرجة | int | sys | — | 0 | none |
| result / grade | النتيجة / التقدير | enum / enum | sys | inspection: `pass` · `fail`; audit: list AG | pass | none |
| findings | الملاحظات | list §3.6 | sys / N | FND-1, FND-2 | — | none |
| stop_work_order_id | أمر الإيقاف | FK | cond. | FND-7 | — | none |
| self_inspection | تفتيش ذاتي | bool | sys | inspector is a Contractor HSE Rep or receiver of the inspected engagement tree | false | none |

### 3.5 Item answer — إجابة البند

item_code; answer (yes_no: `compliant` مطابق · `non_compliant` غير مطابق · `na` لا ينطبق; rating_0_3: 0–3 or `na`; numeric: value; single_select: option code; text: text ≤ 500; photo: file; count: int ≥ 0); note (text 500; ≥ 10 chars required when non-compliant or rating ≤ 1); photos (≤ 3, jpg/png ≤ 5 MB after on-device compression; EXIF stripped server-side); equipment_ref (optional scanned `EQ`/`EA` token or tag, information only, EXE-8); fixed_on_spot (bool, FND-3). PDPL: personal when a photo is attached.

### 3.6 Finding — ملاحظة

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| finding_no | رقم الملاحظة | string | sys | `<owner ref>-F<nn>` | INS-ANIA-EXP-2026-01377-F01 | none |
| item_code | البند | string | N | null = manual finding (FND-2) | GSI-12 | none |
| severity | الخطورة | enum | Y | inspections: list FS; audits: list AF | minor | none |
| description_en / _ar | الوصف | text(1000) | Y (one language) | P1-8 scan; hint "no names" | Loose cable drums blocking stair 3 access | none |
| repeat_of | تكرار لـ | FK | sys | FND-5 | INS-…-01290-F02 | none |
| fixed_on_spot | صُحح فوراً | bool | N | FND-3 | false | none |
| ca_id | الإجراء التصحيحي | FK | cond. | FND-3 | CA-ANIA-EXP-2026-00811 | none |
| responsible_engagement_id | المقاول المسؤول | FK | Y | default = owner's engagement, else the site's tier-1 engagement | NAJD@ANIA-EXP | none |

Phase 1 read model: the inspection's `findings` list shows these findings with severity mapped observation → `low`, minor → `medium`, major → `high`, critical → `critical`, and `ca_required` = (ca_id set).

### 3.7 Audit — تدقيق السلامة

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| audit_no | رقم التدقيق | string | sys | `AUD-<project>-<yyyy>-<nnn>` | AUD-ANIA-EXP-2026-011 | none |
| audit_type | نوع التدقيق | enum | Y | list AT | contractor_hse | none |
| template_code | النموذج | string | Y | kind audit, same audit_type | CHA | none |
| auditee_engagement_id | الجهة المدققة | FK | cond. | required for contractor_hse; null for system_iso45001 (project scope) | SAHARA@ANIA-EXP | none |
| site_ids | المواقع | FK[] | Y | ≥ 1 | [S-LAND] | none |
| lead_auditor_id / team_ids | رئيس فريق التدقيق / الفريق | FK / FK[] | Y / N | holders of 194; team ≤ 5; AUD-3 | Noura / [Fahad] | personal |
| planned_start / planned_end | الموعد المخطط | date ×2 | Y | end ≥ start; ≤ 10 days | 2026-09-07 / 2026-09-08 | none |
| fieldwork_start / fieldwork_end | تنفيذ التدقيق | date ×2 | cond. | required at Fieldwork Complete | 2026-09-07 / 2026-09-08 | none |
| opening_meeting_at / closing_meeting_at | الاجتماع الافتتاحي / الختامي | timestamptz ×2 | cond. | closing required at Fieldwork Complete | — | none |
| auditee_attendee_roles | حضور الجهة المدققة | string(300) | N | roles, not names (hint) | Project manager, HSE manager, site supervisor | none |
| response_id | الإجابات | FK | sys | §3.4 | — | personal (photos) |
| summary_en / _ar | الملخص | text(3000) | cond. | required to issue | — | none |
| report_file | التقرير | file (PDF, generated) | sys | generated at issue (EN + AR) | — | personal (auditor names) |
| issued_by / issued_at | أصدره / تاريخ الإصدار | FK / timestamptz | sys | holder of 195 ≠ lead auditor (AUD-4) | Faisal / 2026-09-12 | personal |
| status / status_reason | الحالة | enum / text | Y | §4.4 | issued | none |

### 3.8 Audit programme line (computed on read, as DECISIONS #157) — بند برنامج التدقيق

scope (`engagement` + engagement_id · `project`), audit_type, frequency_months, due_by (§6.4), last_satisfied_by (audit_id), status (`due` · `overdue`). PDPL: none.

### 3.9 Stop-work order — أمر إيقاف العمل

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| order_no | رقم الأمر | string | sys | `SWO-<project>-<yyyy>-<nnn>` | SWO-ANIA-EXP-2026-007 | none |
| response_id / item_code | الإجابات / البند | FK / string | sys | the failed `stop_work` item | GSI-05 | none |
| site_id / zone_id / engagement_id | الموقع / المنطقة / المقاول | FK ×3 | Y / N / Y | from the inspection | S-LAND / Z-PIERB / NAJD | none |
| activity_en / _ar | النشاط الموقوف | string(300) | Y (one language) | — | Formwork striking at level 3, east slab edge | none |
| instructed_role / instructed_at | من أُبلغ / وقت الإبلاغ | enum / timestamptz | Y | `supervisor` · `foreman` · `operator` · `permit_receiver` · `other`; instructed_at ≤ completed_at + 10 min | supervisor / 09:35 | none |
| permit_ids | التصاريح | FK[] | N | Issued/Active permits whose zones include zone_id (FND-9) | [PTW-…] | none |
| released_by / released_at / release_note / release_photos | رفع الإيقاف | FK / timestamptz / text / file[] | cond. | FND-8 | Fahad / 16:40 / Guardrail fitted along grid C-14 to C-20 | personal |
| status | الحالة | enum | Y | `active` ساري · `released` مرفوع · `voided` ملغى | released | none |

### 3.10 Toolbox topic (org-wide, versioned) — موضوع اجتماع التوعية

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| topic_code / version | رمز الموضوع / الإصدار | string(10) / int | Y / sys | `^TT-[0-9]{3}$`; one Published version per code | TT-014 v2 | none |
| category | الفئة | enum | Y | Phase 1 list O ∪ {`general` عام, `emergency` طوارئ, `health` صحة} | work_at_height | none |
| title_en / title_ar | العنوان | string(150) ×2 | Y | both required to publish | Edges and openings: never remove a guardrail / الحواف والفتحات | none |
| key_points_en / _ar | النقاط الرئيسية | list text(300) ×2 | Y | 3–10 points each | — | none |
| translations | الترجمات | list {language (Phase 2 primary_language), key_points[], reviewed_by_name_role} | N | language ≠ ar/en | [{ur, …}, {bn, …}] | none |
| linked_refs | المراجع المرتبطة | list {kind: incident / observation_category / template_item / lesson (6f), ref} | N | incident refs only (no names, P6d-2) | [incident INC-ANIA-EXP-2026-0147, item GSI-05] | none |
| review_due_on | موعد المراجعة | date | sys | published_at + 24 months − 1 day | 2028-04-14 | none |
| status | الحالة | enum | Y | §4.1 (same as templates) | published | none |

### 3.11 Toolbox talk — اجتماع التوعية (Toolbox Talk)

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| talk_no / client_uuid | رقم الاجتماع / معرّف الجهاز | string / UUID | sys / Y | `TBT-<project>-<yyyy>-<nnnnn>`; client_uuid unique per project | TBT-ANIA-EXP-2026-04412 | none |
| site_id / zone_ids | الموقع / المناطق | FK / FK[] | Y / N | zones of the site | S-LAND / [Z-PIERB] | none |
| host_engagement_id | المقاول المنظم | FK | Y | engagement on the site; C scope for reps (TBT-3) | NAJD@ANIA-EXP | none |
| shift | الوردية | enum | Y | `day` · `night` | day | none |
| delivered_at / duration_minutes | وقت الاجتماع / المدة | timestamptz / int | Y | ≤ received_at + 5 min; ≥ received_at − `offline_submit_max_hours`; 5–120 (TBT-4) | 2026-09-14 06:30 / 15 | none |
| presenter | المقدم | {user_id} or {deployment_id} | Y | a user, or a Mobilised deployment (supervisor without an account) | Rafiq Islam (deployment) | personal |
| recorded_by | سجّله | FK | sys | holder of 198 | Ahmed | personal |
| topics | المواضيع | list {topic_id + version} or {free_title_en/ar, category} | Y | 1–3; ≥ 1 library topic, or free title with category | [TT-014 v2] | none |
| language / interpreter_languages | لغة الاجتماع / لغات الترجمة | enum / enum[] | Y / N | Phase 2 primary_language values | ur / [bn, hi] | none |
| campaign_id | الحملة | FK | N | an Issued campaign whose topic is in topics | CMP-ANIA-EXP-2026-004 | none |
| attendance_rows | الحضور | list §3.12 | cond. | TBT-5…TBT-7 | 38 rows | personal |
| unnamed_count | حضور غير مسمى | int | N | 0–200; needs sheet_photos | 0 | none |
| sheet_photos | صور كشف الحضور | file[] ≤ 4 | cond. | TBT-7 | — | personal |
| questions_raised | أسئلة/ملاحظات العمال | text(1000) | N | P1-8 scan | Lighting on stair 3 poor at 05:30 | none |
| status | الحالة | enum | Y | §4.6 | delivered | none |

### 3.12 Talk attendance row — سجل حضور

deployment_id (Mobilised on the project at delivered_at, `WORKER_NOT_MOBILISED`); method (`card_scan` · `list`); scanned_token (offline scans only, resolved at sync and then deleted, EXE-6); signature (drawn image, N); understood_language (sys: `talk_language` · `interpreter` · `none`, as Phase 5 AT-6); counted_person_type (sys, from the deployment: contractor_worker / client_pmc_staff). PDPL: personal.

### 3.13 Briefing campaign — حملة توعية إلزامية

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| campaign_no | رقم الحملة | string | sys | `CMP-<project>-<yyyy>-<nnn>` | CMP-ANIA-EXP-2026-004 | none |
| topic_id + version | الموضوع | FK | Y | Published, review not overdue (`TOPIC_REVIEW_OVERDUE`) | TT-014 v2 | none |
| reason / reason_ref | السبب / المرجع | enum / string | Y / cond. | `incident` (Phase 1 incident ref required) · `lesson` (6f) · `client_instruction` · `regulatory` · `seasonal` · `audit_finding` | incident / INC-ANIA-EXP-2026-0147 | none |
| message_en / _ar | رسالة الحملة | text(1000) | Y (one language) | P1-8 scan; no names | Two falls from open edges in 30 days… | none |
| site_ids | المواقع | FK[] | Y | ≥ 1 | [S-LAND] | none |
| pairs | المقاولون المطلوبون | list {engagement_id, site_id} | sys | CMP-2 | 3 pairs | none |
| issued_by / issued_at / due_date | أصدرها / تاريخ الإصدار / الاستحقاق | FK / timestamptz / date | sys / sys / Y | due ≥ issue date + 1; default + `campaign_default_days` | Faisal / 2026-09-09 / 2026-09-16 | personal |
| status | الحالة | enum | Y | `draft` · `issued` · `closed` · `cancelled` | closed | none |

### 3.14 Phase 6d project settings
Only the HSE Manager edits them (capability 193); every change is audited; "Allowed" is the only range accepted; a loosening value gets 422 `SETTING_LOOSENING`.

| Key | AR label | Type | Default | Allowed |
|---|---|---|---|---|
| inspection_template_required_from | بدء إلزام قوائم التحقق | date / null | null | ≥ project start; ≤ today; once set only moves earlier |
| toolbox_register_from | بدء احتساب اجتماعات التوعية من السجل | date / null | null | same |
| inspection_pass_mark_pct | درجة النجاح للمشروع | decimal | 85.0 ASSUMPTION | 50.0–100.0; the higher of this and the template's applies; only raise |
| repeat_finding_days | مدة الملاحظة المتكررة | int | 30 ASSUMPTION | 14–90; only raise |
| contractor_audit_months / system_audit_months | تكرار تدقيق المقاولين / النظام | int / int | 6 / 12 ASSUMPTION | 3–12 / 6–12; only lower |
| first_audit_grace_days | مهلة أول تدقيق | int | 60 ASSUMPTION | 30–90; only lower |
| audit_report_days | مهلة إصدار التقرير | int | 7 | 3–14 |
| offline_submit_max_hours / offline_cache_hours | مهلة الإرسال دون اتصال / مدة التخزين | int / int | 72 / 72 ASSUMPTION | 12–72 / 24–72 |
| tbt_min_minutes | الحد الأدنى لمدة الاجتماع | int | 10 ASSUMPTION | 5–30; only raise |
| tbt_edit_window_hours | مهلة تعديل الحضور | int | 24 | 4–48 |
| campaign_default_days | مدة الحملة الافتراضية | int | 7 | 1–30 |
| inspection_coverage_warning_pct / audit_programme_warning_pct / tbt_reach_warning_pct | حدود الإنذار | decimal ×3 | 90.0 / 90.0 / 85.0 ASSUMPTION | 50.0–100.0 |
| critical_fail_warning_per_100 | حد الإخفاقات الحرجة لكل 100 تفتيش | decimal | 5.00 ASSUMPTION | 1.00–20.00 |
| photo_retention_months | الاحتفاظ بالصور | int | 24 | 12–60 |

### 3.15 Reference lists (seeded EN/AR; codes immutable)

**IT — item types:** `yes_no` نعم/لا (scored) · `rating_0_3` تقييم 0–3 (scored; 0 not in place, 1 partly, 2 mostly, 3 fully) · `numeric` قيمة رقمية (scored by numeric_rule) · `single_select` اختيار (scored unless every option is `info`) · `text` نص · `photo` صورة · `count` عدد (unscored).

**FS — inspection finding severity:** `minor` بسيطة · `major` جوهرية · `critical` حرجة (life-threatening if not corrected now).

**AT — audit types:** `contractor_hse` تدقيق السلامة للمقاول · `system_iso45001` تدقيق داخلي لنظام ISO 45001 · `client_requested` تدقيق بطلب العميل (counts as contractor_hse when an auditee is set).

**AF — audit finding grades:** `major_nc` عدم مطابقة رئيسية · `minor_nc` عدم مطابقة ثانوية · `observation` ملاحظة · `ofi` فرصة للتحسين.

**AG — audit grades** (ASSUMPTION): `A` جيد ≥ 90.0 · `B` مُرضٍ 75.0–89.9 · `C` يحتاج إلى تحسين 60.0–74.9 · `D` ضعيف < 60.0; a `major_nc` on a critical item caps the grade at C (§6.2).

**Seeded templates** (org-wide, v1, Published 2026-04-01 except GSI v3; item counts, critical items ★ and stop rules ⛔; full item texts in the seed file):

| Code | Kind / type | Items | Critical items | Notes |
|---|---|---|---|---|
| GSI | inspection / general_site | 24 (2 airside_only) | GSI-05 ★⛔ slab edges and floor openings protected · GSI-09 ★⛔ excavation edges barricaded, safe access · GSI-13 ★⛔ temporary electrical: RCD protection, no damaged cables · GSI-17 ★ lifting exclusion zone in place | v3 (2026-08-20); GSI-12 housekeeping and access routes (minor), GSI-19 signage (minor), GSI-23/24 FOD control and vehicle beacons (airside_only) |
| SCA | inspection / scaffold | 12 | SCA-02 ★⛔ scaffold in use shows a green Phase 4 tag (does not set tags, BD6d-2) · SCA-07 ★ edge protection on working platforms | area and use, not structural inspection |
| EXC | inspection / excavation | 14 | EXC-03 ★⛔ protective system (slope, shoring, box) in place for depth ≥ 1.2 m · EXC-06 ★ safe access within 7.5 m travel | permit field records stay in Phase 3 |
| ELD | inspection / electrical | 12 | ELD-02 ★⛔ DBs locked, covers on, live parts shielded · ELD-04 ★ RCD trip time ≤ 40 ms (numeric, ms, 0–40) | — |
| LGP | inspection / lifting_equipment | 10 | LGP-01 ★ slings and shackles tagged, in date, undamaged | pre-use visual, not the Phase 4 certificate |
| HSK | inspection / housekeeping | 10 | HSK-04 ★ escape routes clear | — |
| FOD | inspection / airside_fod_walk | 10, zone_types [airside] | FOD-03 ★ no loose debris within the work area and adjacent pavement · FOD-06 ★ FOD bins lidded and secured | R5 |
| FIR | inspection / fire_safety | 10 | FIR-02 ★ combustibles ≥ 11 m from hot work or shielded · FIR-05 ★ extinguishers at the work point | complements 6c assets |
| WEL | inspection / welfare | 12 | WEL-01 ★ drinking water available · WEL-06 ★ toilets per headcount, clean | heat stations stay 6b |
| ENV | inspection / environmental | 10 | ENV-02 ★ no uncontained fuel or chemical | 6e may supersede |
| PLT | inspection / plant_vehicle | 10 | PLT-03 ★ reversing alarm, beacon and seatbelt working | — |
| PPE | inspection / ppe | 8 | none | — |
| LDW | inspection / leadership_walk | 8 (text and count items, 2 yes_no) | none | conversations held, positives, concerns |
| CHA | audit / contractor_hse | 40 in 8 sections (rating_0_3) | CHA-12 ★ PTW compliance sampled · CHA-27 ★ competence of high-risk roles sampled | R3 |
| ISO | audit / system_iso45001 | 48 (rating_0_3), clauses 4–10 | ISO-31 ★ hazard identification (6.1.2) · ISO-44 ★ incident investigation and CA (10.2) | R2 |

## 4. Workflow / states

"Who" = capability numbers (§5.13). Jobs: `field_minute` (every 60 s: stop-work alerts and permit suspensions from synced submissions), `field_daily` 00:09:00 (programme lines, campaign status, repeat-window housekeeping, photo retention; after `emergency_daily`), `field_alerts` 07:06.

### 4.1 Template and topic version
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Draft | مسودة | 192 | new code, or new version copied from the Published one |
| Draft → Published | منشور | 193 | TPL-2 completeness; the previous Published version → Superseded |
| Published → Retired | متوقف | 193 | reason ≥ 20 chars; TPL-5 |
| Draft → deleted | — | author | never published |

### 4.2 Inspection (Phase 1 §4.4, as extended)
Phase 1 states unchanged (Planned, Completed, Missed, Completed late, Cancelled, Completed unplanned) plus **Completed → Voided** (201, reason ≥ 20 chars): a voided planned instance returns to Planned or Missed by its dates (EXE-9). A response in progress on a device or saved as a server draft does not change the inspection status.

### 4.3 Stop-work order
Active (at submission, FND-7) → Released (196, FND-8) · Active → Voided (201; raised in error, reason ≥ 20 chars; named permits keep their suspension until the issuer resumes).

### 4.4 Audit
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Planned | مخطط | 194 | AUD-1…AUD-3 |
| Planned → In Progress | جارٍ | lead auditor | opening meeting recorded or first answer saved |
| In Progress → Fieldwork Complete | انتهى العمل الميداني | lead auditor | every item answered (EXE-2), closing meeting recorded |
| Fieldwork Complete → Issued | صدر التقرير | 195 ≠ lead auditor | summary; CAs created (AUD-5); report generated |
| Issued → Closed | مغلق | System | every CA of the audit Closed or Cancelled |
| Planned → Cancelled | ملغى | 194 | reason ≥ 20 chars |
| In Progress / Fieldwork Complete / Issued → Voided | باطل | 201 | reason ≥ 20 chars; leaves KPIs and the programme; CAs stay open |

### 4.5 Briefing campaign
Draft (197) → Issued (197; pairs fixed, CMP-2) → Closed (System, due_date + 7 days) · Draft / Issued → Cancelled (197, reason).

### 4.6 Toolbox talk
Delivered (on submission) → Locked (System, delivered_at + `tbt_edit_window_hours`) · Delivered / Locked → Voided (201, reason ≥ 20 chars). Drafts live on the device or as a server draft and count nowhere.

## 5. Business rules

### 5.1 Template library (TPL)
- TPL-1. Templates and topics are org-wide. A template with project_ids is offered only on those projects.
- TPL-2. **Publish completeness** (each failure → 422 `TEMPLATE_INCOMPLETE` with the list): ≥ 1 scored item; every item and section has EN and AR text; weights 1–5; item codes unique in the version; numeric items have numeric_rule; single_select items have 2–8 options; stop_rule `stop_work` only on critical items; photo_required_on_fail is set true on critical items by the server.
- TPL-3. A Published version is immutable (`TEMPLATE_IMMUTABLE`, 409). Changes create a new version; publishing it supersedes the previous one.
- TPL-4. A response pins the version Published at its started_at; a response started on a version that became Superseded before submission is accepted on that version.
- TPL-5. A template code cannot be retired while an active plan uses it (`TEMPLATE_IN_USE`).
- TPL-6. Review due (review_due_on): alerts at 30 / 0 days to the HSE Manager; an overdue template stays usable and shows "review overdue".

### 5.2 Inspection programme (ISP)
- ISP-1. Plans, instances, grace, on-time, late and missed stay Phase 1 (N-1…N-5). From `inspection_template_required_from`, a new or edited plan needs a template_code (`TEMPLATE_REQUIRED`); existing plans without one keep generating instances and are listed in the action panel ("plan without checklist").
- ISP-2. **Rotation:** instance k (k = 0, 1, … in planned_date order from the plan's start) takes rotation_list[k mod n] as its zone (rotation `zones`) or engagement (rotation `engagements`). Editing the list affects only future Planned instances.
- ISP-3. **Contractor coverage (K-113):** an engagement-site-week is *required* when the engagement has ≥ 1 Phase 1 daily return with headcount > 0 on that site in that week, and *covered* when ≥ 1 inspection (planned or unplanned, Completed, not Voided) with that engagement and site has completed_at in that week. Weeks start on the project `week_start` and belong to the period containing their last day.
- ISP-4. On the day before the last day of a week, engagement-sites still not covered that week appear in the action panel and alert the engagement's Contractor HSE Rep and the site engineers (once).

### 5.3 Execution (EXE)
- EXE-1. **Start:** from a Planned or Missed instance (assignee or capability 33 holder in scope) or as unplanned (template, site, zone optional, engagement optional). The template must apply to the zone's zone_type (`TEMPLATE_NOT_APPLICABLE`; no zone → any). airside_only items are not shown and not applicable outside airside zones.
- EXE-2. **Submit:** every shown item answered; `na` only where na_allowed (`NA_NOT_ALLOWED`); a non-compliant answer (yes_no non_compliant, rating ≤ 1, numeric out of range, option mapped non_compliant) needs a note ≥ 10 chars and, where photo_required_on_fail, ≥ 1 photo (`PHOTO_REQUIRED`).
- EXE-3. Submission sets the Phase 1 inspection Completed (or Completed late / unplanned) with completed_at = response.completed_at, inspector = the submitting user, items_checked = applicable_count, items_compliant = compliant_count and score_pct = the 6d score (§6.2). From `inspection_template_required_from`, completing an inspection without a response is refused (`TEMPLATE_REQUIRED`); before it, Phase 1 manual entry stays available.
- EXE-4. Phase 1 scoping applies (capability 33): a Contractor HSE Rep records inspections of engagements in their C scope or with no engagement; the response is flagged self_inspection when the inspector belongs to the inspected engagement tree (shown as a K-110 breakdown, not excluded) ASSUMPTION.
- EXE-5. Photos: ≤ 3 per item, ≤ 40 per response; hint "photograph the condition, not people / صوّر الحالة لا الأشخاص"; EXIF location and device data stripped on receipt.
- EXE-6. **Offline tolerance** (phone web app): the user may download, for offline use, their Planned instances for the next 3 days with the pinned template versions, the Published template and topic libraries, and the deployment list of their scope (name, worker_no, trade, primary_language; no ID numbers, no card tokens). Drafts, answers, photos and card scans are kept encrypted on the device and submitted when a connection returns. Each submission carries client_uuid; a repeated client_uuid returns the stored record and creates nothing twice (no second CA, alert or stop-work order). The server refuses completed_at older than `offline_submit_max_hours` before received_at (`OFFLINE_SUBMIT_TOO_LATE`) and completed_at later than received_at + 5 min (`CLOCK_SKEW`). On-time / late (Phase 1 N-2) uses completed_at. The cache is deleted at logout or after `offline_cache_hours`.
- EXE-7. A submission more than 15 min after completed_at is stored with offline_delay_min and labelled "recorded offline" wherever shown; its alerts say "recorded offline at <time>".
- EXE-8. An answer may carry a scanned `EQ` or `EA` sticker. A non-compliant answer on a Phase 4 item shows "Raise a defect for <tag>" (Phase 4 DF-10, manual); 6d never creates Phase 4 defects or 6c checks itself.
- EXE-9. **Void** (201): the response and its findings leave every KPI; CAs and a stop-work order already created stay (the order may be voided separately); a planned instance returns to Planned or Missed by its dates.

### 5.4 Findings and stop rules (FND)
- FND-1. Each non-compliant scored answer creates one finding: severity `critical` for a critical item, else the item's default_severity. The inspector may raise a severity, never lower it (`SEVERITY_LOWERED`).
- FND-2. Manual findings (no item) may be added with any severity; they do not change the score.
- FND-3. **CAs:** each critical or major finding creates one Phase 1 CA at submission (source_type `inspection`, or `field_audit` for audits; priority critical → `critical`, major → `high`, minor → `medium`; due per Phase 1 `ca_due_days`; title and control level from the item's suggestion, editable; responsible = the finding's engagement; owner = the first active Contractor HSE Rep of that engagement, else of its tier-1 engagement; verifier = the inspector when CA-5 allows, else the project's first HSE Officer). A minor finding creates a CA only when the inspector ticks "CA required" or FND-5 applies. `fixed_on_spot` is allowed only on minor findings (`FIX_ON_SPOT_NOT_ALLOWED`); it closes the finding without a CA and the answer stays non-compliant in the score. Phase 1 N-4 is met by these CAs.
- FND-4. Findings never name workers (Phase 1 O-4); descriptions get the P1-8 scan.
- FND-5. **Repeat finding:** a non-compliant answer is a repeat when the same item_code was non-compliant in a Completed, not voided response for the same zone (or site, when the inspection has no zone) and the same engagement (or both null) within the previous `repeat_finding_days`, counted from that latest previous non-compliance. A repeat sets repeat_of, raises minor to major (major and critical stay), and so creates a CA.
- FND-6. **Result:** an inspection with ≥ 1 critical non-compliance is `fail` whatever its score; otherwise `pass` ⇔ score ≥ the pass mark (§6.2). A critical non-compliance alerts within 60 s of receipt the site engineers of the site, the HSE Officers and the Contractor HSE Rep of the engagement.
- FND-7. **Stop rule:** a non-compliance on an item with stop_rule `stop_work` cannot be submitted without the stop-work fields (`STOP_RECORD_REQUIRED`): activity, instructed_role, instructed_at and, optionally, live permits on the zone. The phone shows "STOP the activity now and tell the supervisor / أوقف النشاط الآن وأبلغ المشرف" at the moment of the answer, also offline. On receipt the order is Active, alerts go within 60 s (in-app + push + email) to the HSE Manager, HSE Officers, site engineers of the site and the Contractor HSE Rep of the engagement, and it is listed on the action panel and the field band.
- FND-8. **Release** (196): only when the linked CA is In Progress, Pending Verification or Closed (`STOP_RELEASE_CA_REQUIRED`), with release_note ≥ 20 chars and ≥ 1 photo. A Contractor HSE Rep or receiver never releases (matrix 196).
- FND-9. **Permits:** each permit named on an Active order is suspended within 60 s with Phase 3 reason `stop_work` (non-routine; auto_source_ref = order_no). Phase 3 resume (SH-3) is refused while the order is Active (`STOP_WORK_ACTIVE`); after release the issuer resumes as for any non-routine suspension.

### 5.5 Audits (AUD)
- AUD-1. Audits are planned by 194 with a template of kind audit and matching audit_type. contractor_hse requires an auditee engagement on the project; system_iso45001 has project scope.
- AUD-2. Items are answered as in EXE-2 (offline allowed, EXE-6). Rating 0 → finding `major_nc`, rating 1 → `minor_nc`, rating 2 → `observation`; a critical item rated 0 or 1 → `major_nc`. Auditors may add manual findings of any grade, including `ofi`, and may raise a grade, never lower it.
- AUD-3. **Independence** (`SOD_CONFLICT`): the lead auditor and team members are not employed by the auditee engagement (a Contractor HSE Rep may audit engagements strictly below their own in the tree, never their own engagement); for system audits, the lead auditor is not an HSE Officer of that project ASSUMPTION (another project's officer or the HSE Manager).
- AUD-4. **Issue** by 195 ≠ lead auditor. Each `major_nc` creates a CA (priority high), each `minor_nc` a CA (priority medium); observations and OFIs create none unless the issuer asks. CA source `field_audit`. The PDF report (EN and AR) lists scope, team (names), score, grade, section scores and findings; it never names auditee workers.
- AUD-5. Not issued within `audit_report_days` of fieldwork_end → alert to the lead auditor and the HSE Officer, and to the HSE Manager 3 days later.
- AUD-6. **Programme lines:** one contractor_hse line per engagement (any tier) with daily-return headcount > 0 on the project in the last 90 days, frequency `contractor_audit_months`; one system_iso45001 line per project, frequency `system_audit_months`.
- AUD-7. **Satisfying a line:** an audit Issued or Closed (not Voided) of the same type and scope; met **on time** for K-114 when fieldwork_end ≤ due_by. due_by per §6.4. A line is overdue from the day after due_by; alerts at 30 / 7 / 0 days and on the first overdue day to the HSE Officers and the engagement's Contractor HSE Rep.
- AUD-8. Audits are not Phase 1 inspections: they never enter K-34, K-35 or K-35b.

### 5.6 Toolbox talks (TBT)
- TBT-1. Topics follow §4.1 (draft 192, publish 193). Publishing needs EN and AR title and key points (`TOPIC_INCOMPLETE`). Translations into worker languages are optional and show the reviewer's role.
- TBT-2. A topic past review_due_on shows warning `TOPIC_REVIEW_OVERDUE` when used in a talk and cannot be used in a new campaign.
- TBT-3. Talks are recorded by 198: Contractor HSE Reps and receivers for host engagements in their C / C1 scope; site engineers and issuers for their sites.
- TBT-4. duration 5–120 min; below `tbt_min_minutes` → warning `TBT_SHORT` (still counted).
- TBT-5. **Attendance:** by scanning the worker's access-card QR (Phase 2 kind `AC`) or picking from the deployment list. The deployment must be Mobilised on the project at delivered_at (`WORKER_NOT_MOBILISED`) and appear once per talk (`DUPLICATE_ATTENDEE`). A scan never creates a gate-log row and never runs the access eligibility check. Offline scans store the token; at sync it is resolved to a deployment and deleted; an unknown or revoked token rejects that row (`TOKEN_UNKNOWN`, listed to the recorder) and the talk is saved.
- TBT-6. **Language:** understood_language = `talk_language` if worker.primary_language = talk language, `interpreter` if it is in interpreter_languages, else `none` (warning `LANGUAGE_MISMATCH`). A `none` row counts as an attendee for K-36 but not as briefed (K-116, CMP-3).
- TBT-7. **Evidence:** each named row has a card scan or a device signature, or the talk has ≥ 1 sheet photo (`ATTENDANCE_EVIDENCE_REQUIRED`); unnamed_count > 0 needs ≥ 1 sheet photo.
- TBT-8. Rows can be added or removed until Locked (`TALK_LOCKED`, 409), then only void.
- TBT-9. **Suggested topics** (shown when recording; deterministic order): (1) topics of Issued campaigns with an unmet pair for the host engagement on the site, by due date; (2) topics linked to incidents of the project in the last 30 days, newest first; (3) topics linked to the 3 item_codes with most non-compliant answers for the host engagement in the last 30 days; (4) topics of the 3 unsafe-observation categories most recorded for the host engagement in the last 30 days. Topics already delivered by that engagement on that site in the last 7 days are moved last.
- TBT-10. A Phase 3 crew briefing (SH-4) is never a toolbox talk, and a toolbox talk never satisfies SH-4 (BD6d-1).

### 5.7 Briefing campaigns (CMP)
- CMP-1. Issued by 197 with a Published, in-review topic; reason `incident` requires a Phase 1 incident ref the issuer can see; the message gets the P1-8 scan and the hint "no names or medical details".
- CMP-2. Pairs are fixed at Issue: every (engagement, site) with daily-return headcount > 0 on a campaign site in the 14 days before issue.
- CMP-3. A pair is **met** when ≥ 1 attendance row with understood_language ≠ `none` of a worker deployed with that engagement belongs to a Delivered or Locked talk on that site, with the campaign topic (any version), delivered between issued_at and the end of due_date; it is **met on time** for K-117 when that first qualifying talk is on or before due_date.
- CMP-4. Alerts: at issue to the Contractor HSE Reps of the pair engagements and the site engineers; at due_date − 2 days to reps of unmet pairs; on the day after due_date for unmet pairs to the HSE Officers.

### 5.8 Register switch (SRC)
- SRC-1. **K-34 / K-35:** formulas unchanged. From `inspection_template_required_from`, every Completed inspection carries a response (EXE-3), so items_checked, items_compliant and score_pct come only from answers. Phase 3 PTW audits, Phase 4 scaffold inspections, 6b welfare checks and patrols, 6c asset checks and 6d audits are never Phase 1 inspections and never enter K-34, K-35 or K-35b. Voided inspections are excluded.
- SRC-2. **K-36 (no double counting, as Phase 5 TH-6):** for each day d, K-36 uses exactly one source: d ≥ `toolbox_register_from` → the register (talks Delivered or Locked, not Voided, with local delivered date d; attendees = named rows with person_type contractor_worker + unnamed_count); d < `toolbox_register_from`, or the setting null → the daily-return `toolbox_talks` / `toolbox_attendees`. The daily-return fields stay editable but are ignored for register days; the import gives warning **W08** "toolbox talks from the register are used for this date" when either field > 0 on a register day.
- SRC-3. **Reconciliation note:** for register days with a daily-return sum > 0, if |register − daily return| > 5 % of the daily-return sum for talks or for attendees, the K-36 tile shows "Daily returns differ from the toolbox register by x % (talks / attendees)" ASSUMPTION, as TH-7.
- SRC-4. K-116 and K-117 are shown only for periods on or after `toolbox_register_from` (else "—").

### 5.9 KPIs and AI (FM)
- FM-1. All 6d KPIs are computed by the backend from stored records (K-R1). Attribution: inspections → completed_at local date (K-110, K-111, K-112), audits → issued_at (K-115), talks → delivered date, weeks per ISP-3. Contractor attribution: response → its engagement (no engagement → only without a contractor filter); talks and K-116 → the attendee's deployment engagement; campaigns → the pair engagement. Contractor filter with descendants as K-R5.
- FM-2. AI tool **T21 `get_field_assurance_kpis`** (project_ids, period, filters {site, zone, engagement, include_descendants, inspection_type, template_code, audit_type, topic_category}, metrics K-34, K-35, K-36, K-110…K-117, group_by {template, item_code, inspection_type, contractor, zone, month, week, topic, language}) returns aggregates only: counts, scores, item codes with item text, topic codes and titles; never names, finding or note texts, photos, signatures or worker_no. T8 adds pooled score (K-110) and critical fails; T13 returns E20–E21; AI-19 gains a section "Field assurance" (K-110…K-117, top 5 failed items, stop-work orders count).
- FM-3. "Most failed items" = item codes ranked by non-compliant answers in the period, ties by fail rate (non-compliant ÷ applicable), then code; items with < 5 applicable answers are listed only with the note "small sample".

### 5.10 PDPL (P6d-x)
- P6d-1. **Personal:** inspector, auditor, presenter, recorder and releaser identities; attendance rows (a named worker at a place and time) and signatures; understood language; photos (may show people); the device cache. **None:** templates, topics, scores, findings, campaigns, programme lines. **Sensitive:** none (6d stores no health or ID data).
- P6d-2. Free texts (notes, findings, questions, messages) get the P1-8 scan and the hint "no names or medical details"; topics and campaigns may cite incident refs, never injured persons.
- P6d-3. Photos are visible to holders of 200 except Viewer/Client (never photos); kept `photo_retention_months`, or as long as a linked open CA, stop-work order or incident needs them.
- P6d-4. Attendance names and signatures are visible to 199 holders in scope; exports with names write an `export` audit row (DECISIONS #78); signatures are never exported (only "signed: yes / no"). Attendance follows the worker's anonymisation (P2-7); signatures are deleted then.
- P6d-5. Card scans for talks are HSE briefing evidence only: never gate logs, never used for time-keeping, attendance pay or discipline reports, and not read by 6c coverage (purpose limitation, P2-8 extended §11.3).
- P6d-6. The offline cache is encrypted at rest, limited to the user's scope, holds no ID numbers or card tokens, and is deleted at logout or after `offline_cache_hours`.
- P6d-7. Records (responses, audits, talks, stop-work orders, campaigns) are kept for the project life + 5 years ASSUMPTION.

### 5.11 Phase-boundary rules (BD6d)
- BD6d-1. 6d owns no hook kind. It reads Phase 1 daily returns, incidents and observations, Phase 2 deployments and access-card tokens, Phase 3 live permits, Phase 4 and 6c stickers (information only). It writes Phase 1 inspections, findings and CAs (sources `inspection`, `field_audit`) and, through §11.4, Phase 3 `stop_work` suspensions.
- BD6d-2. Scaffold tags, certificates and defects stay in Phase 4; SCA-02 reads the tag colour as an answer, it never sets one.
- BD6d-3. PTW audits stay in Phase 3 (K-46, K-61, K-64); 6b welfare checks and 6c asset checks keep their fixed lists and KPIs; none of them is counted by 6d KPIs.
- BD6d-4. Toolbox talks are not training (Phase 5 BD5-5, TH-5) and not inductions (Phase 2).

### 5.12 Error and warning codes (new)
422 `TEMPLATE_INCOMPLETE`, `TEMPLATE_IN_USE`, `TEMPLATE_REQUIRED`, `TEMPLATE_NOT_APPLICABLE`, `NA_NOT_ALLOWED`, `PHOTO_REQUIRED`, `SEVERITY_LOWERED`, `FIX_ON_SPOT_NOT_ALLOWED`, `STOP_RECORD_REQUIRED`, `STOP_RELEASE_CA_REQUIRED`, `STOP_WORK_ACTIVE`, `OFFLINE_SUBMIT_TOO_LATE`, `CLOCK_SKEW`, `TOPIC_INCOMPLETE`, `TOPIC_REVIEW_OVERDUE` (campaign), `WORKER_NOT_MOBILISED`, `DUPLICATE_ATTENDEE`, `ATTENDANCE_EVIDENCE_REQUIRED`, `SOD_CONFLICT`, `SETTING_LOOSENING`; 409 `TEMPLATE_IMMUTABLE`, `TALK_LOCKED`. Warnings: `TOPIC_REVIEW_OVERDUE` (talk), `TBT_SHORT`, `LANGUAGE_MISMATCH`; row rejection `TOKEN_UNKNOWN`.

### 5.13 Permission matrix — Phase 6d extension
Continues 6c §5.13. Legend A/P/S/C/C1/R/—. Recording inspections and managing plans stay Phase 1 capability 33.

| # | Capability | HSE Mgr | HSE Officer | Site Eng/Sup | Permit Issuer | Permit Receiver | Contractor HSE Rep | Viewer/Client | OH Pract. |
|---|---|---|---|---|---|---|---|---|---|
| 191 | View template and topic libraries | A | P | P | P | P | P | P | P |
| 192 | Author template and topic drafts | A | P | — | — | — | — | — | — |
| 193 | Publish / retire templates and topics; edit 6d settings and switch dates | A | — | — | — | — | — | — | — |
| 194 | Plan, cancel and conduct audits (lead or team); view audit programme | A | P | S (team member only) | — | — | C (AUD-3) | — | — |
| 195 | Issue audit reports | A | P | — | — | — | — | — | — |
| 196 | Release stop-work orders | A | P | S | — | — | — | — | — |
| 197 | Issue / cancel briefing campaigns | A | P | — | — | — | — | — | — |
| 198 | Record toolbox talks and attendance | A | P | S | S | C1 | C | — | — |
| 199 | View talk attendance names and signatures | A | P | S | S | C1 | C | — | — |
| 200 | View 6d registers, responses, KPIs, action panel; export (names per 199) | A | P | S | S | C1 | C | P (aggregates, no photos) | — |
| 201 | Void inspections (6d), audits, talks, stop-work orders | A | P | — | — | — | — | — | — |

Suspended-contractor users keep reads and lose writes (Phase 0 rule 28).

## 6. Calculations

Rounding half-up at output only (K-R8): percentages 1 dp, rates per 100 to 2 dp. Comparisons and warnings use unrounded values.

### 6.1 Earned and applicable weight per answer (w = item weight)
- yes_no: compliant → applicable w, earned w; non_compliant → applicable w, earned 0; na → not applicable.
- rating_0_3: r ∈ {0,1,2,3} → applicable w, earned w × r ÷ 3; compliant for items_compliant ⇔ r ≥ 2; na → not applicable.
- numeric: applicable w; earned w if min ≤ value ≤ max else 0.
- single_select: option `compliant` → w / w; `non_compliant` → w / 0; `info` → not applicable.
- text, photo, count, and airside_only items outside airside zones: not applicable.

### 6.2 Response score, result and grade
- applicable_weight = Σ applicable w; earned_weight = Σ earned; **score_pct = earned ÷ applicable × 100**; applicable_weight 0 → score "—" and result pass unless a critical fail (leadership walks).
- applicable_count = n(applicable answers); compliant_count = n(compliant answers).
- Inspection result: `fail` if critical_fail_count ≥ 1, else `pass` ⇔ score_pct ≥ max(template pass_mark_pct, `inspection_pass_mark_pct`).
- Audit grade: by list AG on the unrounded score; capped at C when any `major_nc` is on a critical item.
- Section score (audit report, C31): same formula over the section's items.

### 6.3 Repeat window
repeat ⇔ ∃ previous non-compliant answer (FND-5 key) with completed date p and current completed date c: 0 ≤ c − p ≤ `repeat_finding_days` (days, local dates), p the latest such date.

### 6.4 Audit programme due dates
add_months as Phase 5 TR1 (month-end clamp). due_by = add_months(fieldwork_end of the last satisfying audit, f) − 1 day; with none, the line start (the later of the engagement's mobilisation date and the date the project's first 6d audit template was Published, or project start for system lines) + `first_audit_grace_days`. **K-114 items:** each (line, due_by) with due_by in the period and ≤ as_of.

### 6.5 Weeks, coverage and reach
- Week = 7 days from `week_start`; it belongs to the period containing its last day; only weeks with last day ≤ as_of count.
- K-113 unit = engagement-site-week required per ISP-3.
- K-116 unit u = engagement-site-week with ≥ 1 daily-return day with headcount > 0 and every day of the week ≥ `toolbox_register_from`. H(u) = mean daily headcount of the engagement on the site over that week's days with headcount > 0 (daily returns, all shifts summed per day). B(u) = n(distinct deployments of that engagement with ≥ 1 briefed row — understood_language ≠ none — at a talk on that site in the week) + Σ unnamed_count of talks hosted by that engagement on that site in the week ASSUMPTION. reach(u) = min(B(u), H(u)).
- **K-116 = Σ reach(u) ÷ Σ H(u) × 100** (pooled, not an average of percentages).

### 6.6 K-36 with the register switch
K-36 talks(period) = Σ_d [d ≥ R ? n(register talks on d) : Σ daily-return toolbox_talks(d)]; attendees likewise with register attendees (SRC-2); R null → daily returns only. reconciliation_pct = |Σ register(register days) − Σ daily return(register days)| ÷ Σ daily return(register days) × 100, computed separately for talks and attendees, not computed when the daily-return sum is 0.

### 6.7 KPI catalogue (continues 6c §6.8)

| ID | Metric (EN / AR) | Formula | Unit / display | Better |
|---|---|---|---|---|
| K-110 | **Checklist compliance score** / نسبة المطابقة في قوائم التفتيش | Σ earned_weight ÷ Σ applicable_weight × 100 over responses of Completed, not voided inspections with completed_at in period (pooled); chips: pass rate, n inspections | %, 1 dp | higher |
| K-111 | **Critical item failures** / إخفاقات البنود الحرجة | n(critical non-compliant answers in those inspections); rate = n × 100 ÷ n(those inspections) (0 inspections → "—"); chip: stop-work orders raised | count; per 100 inspections, 2 dp | lower |
| K-112 | Repeat findings / الملاحظات المتكررة | n(findings with repeat_of) ÷ n(item findings) × 100 in those inspections | %, 1 dp | lower |
| K-113 | **Contractor inspection coverage** / تغطية التفتيش للمقاولين | covered ÷ required engagement-site-weeks × 100 (ISP-3); 0 → "—" | %, 1 dp | higher |
| K-114 | **Audit programme compliance** / الالتزام ببرنامج التدقيق | items met on time ÷ items (§6.4) × 100; 0 items → "—" | %, 1 dp | higher |
| K-115 | HSE audit score / نتيجة تدقيق السلامة | pooled Σ earned ÷ Σ applicable × 100 over audits Issued (not voided) in period; chips: major_nc, minor_nc counts; grade mix | %, 1 dp | higher |
| K-116 | **Toolbox weekly reach** / الوصول الأسبوعي لاجتماعات التوعية | §6.5; chip: language-match % = rows with understood_language ≠ none ÷ named rows × 100 | %, 1 dp | higher |
| K-117 | Briefing campaign completion / إنجاز حملات التوعية | pairs met on time ÷ pairs of campaigns (Issued or Closed) with due_date in period and ≤ as_of × 100 | %, 1 dp | higher |

K-34, K-35, K-35b keep their Phase 1 formulas (SRC-1); K-36 per §6.6.

### 6.8 Leading-indicator warnings
Monthly job, day 2 at 07:00, per project and per tier-1 tree (DECISIONS #53).
- **E20 Field assurance** in M: K-113(M) < `inspection_coverage_warning_pct`, or K-114(M) < `audit_programme_warning_pct`, or (≥ 20 inspections in M and K-111 rate(M) ≥ `critical_fail_warning_per_100`), or a stop-work order Active for > 7 days at month end.
- **E21 Toolbox engagement** in M: K-116(M) < `tbt_reach_warning_pct`, or K-117(M) < 100.0. Not evaluated before `toolbox_register_from`.
- T13 inputs: numerators, denominators, thresholds, order and campaign numbers; never names.

### 6.9 Worked examples (exact; backend unit tests must match)

**FD1 — inspection score.** GSI v3 at Z-PIERB (landside), engagement NAJD, 2026-09-24. 24 items; GSI-23/24 airside_only → not applicable; GSI-21 `na` (allowed). Applicable 21: 4 critical × weight 3 = 12 + 17 × 1 = 17 → applicable_weight **29**. Non-compliant GSI-12 and GSI-19 (minor) → earned 27 → 27 ÷ 29 × 100 = 93.103… → **93.1 %**, items 21 / 19, result **pass** (≥ 85.0). (b) GSI-05 also non-compliant → 24 ÷ 29 = 82.758… → **82.8 %**, **fail**, stop-work fields required. (c) Only GSI-05 non-compliant → 26 ÷ 29 = 89.655… → **89.7 %** but **fail** (critical).

**FD2 — audit score.** CHA v1, AUD-ANIA-EXP-2026-011, SAHARA, fieldwork 2026-09-07…09-08. 40 items, 2 `na` → 38 applicable; critical CHA-12 and CHA-27 weight 3, others 1 → applicable_weight 36 + 6 = **42**. Ratings: both critical 3 → 6.000; 36 others: 20 × 3 → 20.000, 10 × 2 → 6.667, 4 × 1 → 1.333, 2 × 0 → 0 → earned **34.000** → 34 ÷ 42 × 100 = 80.952… → **81.0 %**, grade **B**. Findings: 2 `major_nc`, 4 `minor_nc`, 10 `observation`; at issue 2 CAs high + 4 CAs medium (source `field_audit`). Variant: CHA-27 rated 1 instead of 3 → earned 32.000 → 76.2 % (B by score) but `major_nc` on a critical item → grade **C**.

**FD3 — repeat finding.** GSI-12 non-compliant at Z-MSCP / NAJD on 2026-09-10 and 2026-09-24 → the 09-24 finding is a repeat (14 days): minor → **major**, CA high. On 2026-10-12 non-compliant again → 18 days after 09-24 → **repeat**. Had 09-24 been compliant: 10-12 − 09-10 = 32 days > 30 → **not a repeat**, minor, no CA.

**FD4 — programme dates.** SAHARA last contractor audit fieldwork_end 2026-03-10 → due add_months(2026-03-10, 6) − 1 = **2026-09-09**; AUD-…-011 fieldwork_end 2026-09-08 → met on time; next due **2027-03-07**. GULFPAVE last 2026-03-20 → due **2026-09-19**; AUD-ANIA-EXP-2026-012 fieldwork_end 2026-09-23 → late (K-114 miss); next due **2027-03-22**. An engagement mobilised 2026-10-10 → first due 2026-10-10 + 60 = **2026-12-09**.

**FD5 — K-36 switch (W1 workforce fixture, ANIA-EXP, September 2026, toolbox fields added for this example; `toolbox_register_from` = 2026-09-16).** Daily returns 09-01…09-15: talks **240**, attendees **6,900**. Daily returns 09-16…09-30: 260 / 7,500 (ignored). Register 09-16…09-30: 268 Delivered/Locked talks; attendees 7,520 named contractor_worker + 380 unnamed = **7,900**. Not counted: 2 voided talks, 3 drafts, 14 client/PMC staff rows. K-36 = 240 + 268 = **508 talks**; 6,900 + 7,900 = **14,800 attendees**. Reconciliation: talks |268 − 260| ÷ 260 = 3.08 % (no note); attendees |7,900 − 7,500| ÷ 7,500 = 5.333… % > 5 → note **"5.3 % (attendees)"**. With the setting null → **500 / 14,400**.

**FD6 — weekly reach, week 2026-09-13…09-19 (W1 headcounts).** NAJD S-LAND: H = 800; briefed named 742 (21 `none` rows excluded) + unnamed 30 = 772 → reach 772 (96.5 %). GULFPAVE S-AIR: H = 600; B = 510 → 85.0 %. SAHARA S-LAND: H = 300; 290 + 40 = 330 → capped **300**. Pooled = (772 + 510 + 300) ÷ (800 + 600 + 300) = 1,582 ÷ 1,700 × 100 = 93.058… → **93.1 %**.

**FD7 — contractor coverage, ANIA-EXP, September 2026.** week_start Sunday → weeks ending 09-05, 09-12, 09-19, 09-26 (the week ending 10-03 belongs to October). Engagement-sites with work: RAWABI@S-AIR, RAWABI@S-LAND, NAJD@S-LAND, GULFPAVE@S-AIR, SAHARA@S-LAND → 20 required; SAHARA@S-LAND week ending 09-26 has no inspection → 19 ÷ 20 = **95.0 %**.

**FD8 — edges.** (a) Pooling: inspections with 10/10 and 20/40 weight → K-110 = 30 ÷ 50 = **60.0 %** (not 75.0). (b) ELD-04 numeric 0–40 ms: 38 → compliant; 45 → non-compliant critical → fail. (c) A single_select whose chosen option is `info` → not applicable. (d) K-111 with 0 inspections → "—".

**FD9 — September 2026 KPIs = seed (Appendix A.6).**

| Metric | ANIA-EXP calculation | ANIA-EXP | RBT-52 calculation | RBT-52 |
|---|---|---|---|---|
| K-34 / K-35 / K-35b | Phase 1 A.3 unchanged: 34 ÷ 40; 37 ÷ 40; 37 + 5 | **85.0 % / 92.5 % / 42** | as Phase 1 seed | unchanged |
| K-36 | register from 09-01 = A.3 values | **520 talks** (attendees = daily-return sum; reconciliation 0) | daily returns (register null) | unchanged |
| K-110 | 1,135 ÷ 1,250 × 100 (42 inspections) | **90.8 %** | 430 ÷ 460 × 100 = 93.478… (16 inspections) | **93.5 %** |
| K-111 | 2 × 100 ÷ 42 = 4.761… | **2 / 4.76** | 0 × 100 ÷ 16 | **0 / 0.00** |
| K-112 | 6 ÷ 64 × 100 = 9.375 | **9.4 %** | 2 ÷ 25 × 100 | **8.0 %** |
| K-113 | FD7 | **95.0 %** | 8 ÷ 8 (QIMMA S-TWR, S-POD × 4 weeks; DLIFT no hours) | **100.0 %** |
| K-114 | FD4: 1 ÷ 2 | **50.0 %** | no item due | **—** |
| K-115 | (34 + 36) ÷ (42 + 43) × 100 = 82.352…; major 2 + 1, minor 4 + 3 | **82.4 %** · 3 major · 7 minor | none | **—** |
| K-116 | Σ reach ÷ Σ H over 20 units (A.6) | **92.4 %** | register null | **—** |
| K-117 | CMP-004 3/3 + CMP-005 1/2 → 4 ÷ 5 | **80.0 %** | none | **—** |

Expected warnings for September 2026: **E20 ANIA-EXP** (K-114 50.0 < 90.0; project and the RAWABI tree) · **E21 ANIA-EXP** (K-117 80.0 < 100.0; RAWABI tree) · none for RBT-52.

## 7. Alerts & expiries

Channels as Phases 1–6c (in-app and email in the recipient's language; push on the phone web app; SMS items sent in-app + email, DECISIONS #124). Each (subject, step) is sent once; re-running a job never sends twice; alerts from offline submissions say "recorded offline at <time>".

| Trigger | Recipient | Timing | Channel |
|---|---|---|---|
| Stop-work order Active (FND-7) | HSE Manager; HSE Officers; site engineers of the site; Contractor HSE Rep of the engagement; issuers and receivers of named permits | Within 60 s of receipt | In-app + push + email |
| Stop-work order Active > 24 h | HSE Officers; HSE Manager | Daily 07:06 | In-app + email |
| Critical item failure (FND-6) | Site engineers; HSE Officers; Contractor HSE Rep | Within 60 s of receipt | In-app + push |
| CA created from a finding | CA owner (Phase 1 "CA assigned") | Immediately | In-app + email |
| Engagement-site not inspected this week (ISP-4) | Contractor HSE Rep; site engineers | Day before week end, 07:06 | In-app |
| Audit line due / overdue (AUD-7) | HSE Officers; Contractor HSE Rep of the engagement | 30 / 7 / 0 days; first overdue day, then weekly | In-app + email |
| Audit report not issued (AUD-5) | Lead auditor; HSE Officer; HSE Manager + 3 days | At the deadline, then daily | In-app + email |
| Campaign issued / due − 2 / overdue (CMP-4) | Reps of pair engagements and site engineers / reps of unmet pairs / HSE Officers | At issue; due − 2 days 07:06; day after due | In-app + push + email |
| Offline submission rejected (late) | Submitting user; HSE Officer | At sync | In-app |
| Template or topic review due | HSE Manager | 30 / 0 days | In-app |
| E20 / E21 | HSE Manager; HSE Officers; tier-1 Contractor HSE Rep for its tree | Monthly job, day 2, 07:00 | In-app + email |

## 8. Reports / KPIs fed

### 8.1 Dashboard additions (Phase 1 §8.1)
1. **Leading tiles:** K-110 checklist score (chip K-111 critical fails + stop-work orders) · K-113 contractor inspection coverage · K-114 audit programme (chip K-115) · K-116 toolbox reach (chip K-117 and language match). The K-34/K-35 tile shows "checklist-based from <date>"; the K-36 tile shows its source (Toolbox register / Daily returns / Mixed) and the SRC-3 note.
2. **Field band** (live): Active stop-work orders; critical failures today; engagement-sites not yet inspected this week; open campaigns with unmet pairs; audits due in 30 days.
3. **Charts:** C31 K-110 by month by inspection type with the pass-mark line (and audit section scores on the audit page); C32 most failed items (FM-3), top 10 bars with fail-rate dots; C33 K-116 by contractor by week (heat grid).
4. Filters D-2 apply, plus inspection type, template and topic category.

### 8.2 Expiring items and action panel
- `ExpiringItemKind`: `audit_due`, `campaign_due`, `checklist_template_review`, `toolbox_topic_review`.
- Action panel: Active stop-work orders; plans without checklist after the switch (ISP-1); engagement-sites not inspected this week (ISP-4); audit lines overdue; audit reports overdue; campaigns with unmet pairs at due − 2 days or overdue; offline submissions rejected in the last 7 days.

### 8.3 Registers and prints
Template library (versions, change notes), topic library, inspection register with scores and results, findings register (repeat flag, CA status), stop-work register, audit register and programme, talk register, campaign register. Prints: blank checklist (EN/AR, for paper fallback), completed inspection and audit reports (PDF), talk attendance sheet (pre-filled with the topic, blank rows; names printed only for 199). Exports (200) write an `export` audit row.

### 8.4 Feeds to other phases
- **Phase 1:** inspection answers and scores, findings, CAs (`inspection`, `field_audit`), K-34/K-35 inputs, K-36 source switch, K-110…K-117, E20–E21, T21, T8 extension, AI-19 section.
- **Phase 3:** `stop_work` suspensions and the resume block (§11.4).
- **6e:** environmental inspections use 6d templates (ENV). **6f:** lessons may be linked to topics and campaigns (reason `lesson`). **6g:** K-110, K-113, K-115, K-116 per contractor.

## 9. Acceptance criteria

Fixtures: the Appendix A seed with the Phase 0–6c seeds; clock `HSE_CLOCK_AT` = **2026-10-06 10:00** unless stated. Users as 6c §9 (Faisal HSE Manager; Noura HSE Officer ANIA-EXP; Lina HSE Officer RBT-52; Omar site engineer S-AIR; Fahad site engineer S-LAND; Khalid issuer; Ramesh receiver NAJD; Ahmed Contractor HSE Rep RAWABI; Yousef Contractor HSE Rep QIMMA; Sarah viewer).

**Template library**
1. **Given** Noura has a GSI v4 draft **When** she publishes it **Then** 403 (193); Faisal publishes **Then** v4 Published, v3 Superseded, and a response started on v3 before publication is accepted on v3 (TPL-4).
2. **Given** a draft with one item missing text_ar and a `stop_work` item that is not critical **Then** publish → 422 `TEMPLATE_INCOMPLETE` listing both; a critical item saved with photo_required_on_fail false is stored true.
3. **Given** a Published version **When** any item is edited **Then** 409 `TEMPLATE_IMMUTABLE`; **When** Faisal retires GSI while a plan uses it **Then** 422 `TEMPLATE_IN_USE`.
4. **Given** a template with project_ids [RBT-52] **Then** it is not offered on ANIA-EXP; **given** FOD (zone_types [airside]) started on Z-PIERB **Then** 422 `TEMPLATE_NOT_APPLICABLE`.
5. **Given** Faisal sets `inspection_pass_mark_pct` 80.0, `repeat_finding_days` 20 or `contractor_audit_months` 9 **Then** 422 `SETTING_LOOSENING`; 90.0, 45 and 4 **Then** saved and audited; Noura editing any 6d setting **Then** 403.

**Inspection programme**
6. **Given** a weekly GSI plan on S-LAND with rotation zones [Z-PIERB, Z-MSCP, Z-LAY1] **Then** its first four instances are Z-PIERB, Z-MSCP, Z-LAY1, Z-PIERB; changing the list changes only future Planned instances.
7. **Given** `inspection_template_required_from` = 2026-09-01 **When** a plan is created without template_code **Then** 422 `TEMPLATE_REQUIRED`; an older plan without one keeps generating instances and is listed "plan without checklist"; completing its instance with manual counts **Then** 422 `TEMPLATE_REQUIRED`. With the setting null, manual counts are accepted (Phase 1 unchanged).
8. **Given** a quarterly plan starting 2026-01-31 **Then** instances fall on 2026-01-31, 2026-04-30, 2026-07-31, 2026-10-31.
9. **Given** FD7 **Then** K-113 for ANIA-EXP September 2026 = 95.0 % with the uncovered unit SAHARA@S-LAND week ending 09-26; the week ending 10-03 is not in September.
10. **Given** the clock week (Sun 10-04…Sat 10-10) and NAJD@S-LAND not inspected **Then** on 10-09 07:06 one alert goes to Ahmed and Fahad and the action panel lists it.

**Execution**
11. **Given** FD1 **Then** score 93.1 %, items 21 / 19, result pass, and the Phase 1 inspection shows items_checked 21, items_compliant 19, score_pct 93.1.
12. **Given** FD1 (b) and (c) **Then** 82.8 % fail and 89.7 % fail; neither can be submitted without the stop-work fields.
13. **Given** `na` on GSI-05 (na not allowed) **Then** 422 `NA_NOT_ALLOWED`; GSI-13 non-compliant without a photo **Then** 422 `PHOTO_REQUIRED`; a non-compliant answer with a 5-char note **Then** 422.
14. **Given** FD8 (a)–(c) **Then** K-110 = 60.0 % and the ELD-04 and select cases behave as stated.
15. **Given** an inspection completed offline at 2026-10-05 08:00 and received 2026-10-06 09:00 **Then** it is accepted, completed_at 08:00 decides on-time, offline_delay_min = 1,500 and it shows "recorded offline"; received 2026-10-08 08:01 **Then** 422 `OFFLINE_SUBMIT_TOO_LATE`.
16. **Given** the same submission sent twice with one client_uuid **Then** one inspection, one set of CAs and one stop-work order exist; **given** completed_at 10 min after received_at **Then** 422 `CLOCK_SKEW`.
17. **Given** Ahmed records a GSI inspection for NAJD **Then** saved with self_inspection = true; for a QIMMA engagement **Then** refused (out of scope); Ramesh recording any inspection **Then** 403 (capability 33).
18. **Given** an LGP answer with a scanned `EQ` sticker and LGP-01 non-compliant **Then** "Raise a defect for <tag>" is offered and no Phase 4 defect exists until a user raises it.
19. **Given** photos with EXIF GPS **Then** the stored files have no location data.
20. **Given** Noura voids a Completed planned inspection (reason ≥ 20 chars) **Then** it leaves K-110…K-112, the instance returns to Planned or Missed by its dates and its CAs stay open; Fahad voiding **Then** 403.

**Findings and stop rules**
21. **Given** FD1 (b) submitted **Then** one CA critical (due +1 day, source `inspection`, owner Ahmed as NAJD's tree rep, control level from the item suggestion) and no CA for the minor GSI-12 and GSI-19; ticking "CA required" on GSI-12 adds a CA medium.
22. **Given** a minor finding marked fixed_on_spot **Then** no CA and the answer stays non-compliant in the score; fixed_on_spot on a critical finding **Then** 422 `FIX_ON_SPOT_NOT_ALLOWED`; lowering a major to minor **Then** 422 `SEVERITY_LOWERED`.
23. **Given** FD3 **Then** the 09-24 and 10-12 findings are repeats raised to major with a CA high, and the 32-day variant is not a repeat.
24. **Given** a critical non-compliance on HSK-04 (no stop rule) **Then** result fail and Fahad, Noura and Ahmed are alerted within 60 s; no stop-work order.
25. **Given** FD1 (b) with stop-work fields and an Active WAH permit on Z-PIERB named **Then** SWO Active, alerts within 60 s to Faisal, Noura, Fahad, Ahmed and the permit's issuer and receiver, and the permit is Suspended `stop_work` with auto_source_ref = the order number.
26. **Given** that suspended permit **When** the issuer resumes while the order is Active **Then** 422 `STOP_WORK_ACTIVE`; after release **Then** the issuer resumes per SH-3.
27. **Given** the order's CA still Open **When** Fahad releases **Then** 422 `STOP_RELEASE_CA_REQUIRED`; with the CA In Progress, a note ≥ 20 chars and a photo **Then** Released; Ahmed releasing **Then** 403.
28. **Given** a stop-work answer recorded offline at 09:35 and synced at 11:10 **Then** the phone showed the STOP instruction at 09:35 and the alerts at 11:10 say "recorded offline at 09:35".
29. **Given** a Template-based inspection **Then** the Phase 1 read model lists its findings with mapped severities and ca_required, so N-4 passes without manual findings.

**Audits**
30. **Given** FD2 **Then** score 81.0 %, grade B, 2 major_nc, 4 minor_nc, 10 observations; at issue 2 CAs high and 4 CAs medium with source `field_audit`; the variant gives grade C.
31. **Given** Ahmed plans an audit of NAJD **Then** allowed; of RAWABI (own engagement) **Then** 422 `SOD_CONFLICT`; Noura as lead auditor issuing her own report **Then** 422 `SOD_CONFLICT`; Faisal issues it **Then** Issued with an EN and AR PDF that names no auditee workers.
32. **Given** an audit with fieldwork_end 2026-09-28 not issued by 2026-10-05 **Then** the lead auditor and Noura are alerted on 10-05 and Faisal on 10-08.
33. **Given** FD4 **Then** SAHARA's line is met on time with next due 2027-03-07, GULFPAVE's is late with next due 2027-03-22, and the new engagement's first due is 2026-12-09.
34. **Given** a Voided or Cancelled audit **Then** it satisfies no line and leaves K-115; **given** any audit **Then** it is absent from K-34, K-35 and K-35b (AUD-8).
35. **Given** all CAs of AUD-…-011 Closed **Then** the audit becomes Closed automatically.

**Toolbox talks**
36. **Given** Ahmed records a NAJD talk on Z-PIERB with 3 card scans, 2 list picks with device signatures and 1 list pick without signature and no sheet photo **Then** 422 `ATTENDANCE_EVIDENCE_REQUIRED`; with a sheet photo **Then** saved with 6 rows.
37. **Given** a scan of a demobilised worker **Then** 422 `WORKER_NOT_MOBILISED` for that row; the same worker scanned twice **Then** `DUPLICATE_ATTENDEE`; no gate-log row is created and no eligibility check runs.
38. **Given** a talk in `ur` with interpreter `bn` **Then** a `ml` worker's row has understood_language none with warning `LANGUAGE_MISMATCH`; it counts in K-36 attendees and not in K-116 or campaign evidence; a `bn` worker is `interpreter` and counts.
39. **Given** unnamed_count 12 without a sheet photo **Then** 422 `ATTENDANCE_EVIDENCE_REQUIRED`; duration 4 min **Then** 422; 8 min **Then** saved with warning `TBT_SHORT`.
40. **Given** a talk delivered 2026-10-05 06:30 **When** a row is added on 10-06 07:00 **Then** 409 `TALK_LOCKED`.
41. **Given** an offline talk with one scanned token revoked before sync **Then** the talk is saved, that row is rejected `TOKEN_UNKNOWN` and listed to the recorder, and no token is stored after sync.
42. **Given** a topic draft without AR key points **Then** publish → 422 `TOPIC_INCOMPLETE`; a topic past review used in a talk **Then** warning `TOPIC_REVIEW_OVERDUE`, and in a new campaign **Then** 422.
43. **Given** NAJD on S-LAND with an unmet CMP pair, a September incident linked to TT-014 and GSI-12 as its most failed item **Then** the suggestions list the campaign topic first, then TT-014, then the GSI-12 topic, in TBT-9 order.
44. **Given** a Phase 3 crew briefing recorded on a permit **Then** it does not appear in the talk register or K-36, and a toolbox talk does not satisfy SH-4.
45. **Given** a toolbox talk of 30 min **Then** K-37 training hours are unchanged (TH-5).

**Campaigns**
46. **Given** CMP-ANIA-EXP-2026-005 issued 09-23 due 09-30 on S-AIR **Then** pairs RAWABI@S-AIR and GULFPAVE@S-AIR; GULFPAVE met 09-24 on time, RAWABI met 10-01 late; K-117 September ANIA-EXP = 80.0 %.
47. **Given** that campaign **Then** Ahmed is alerted at issue and on 09-28 (RAWABI unmet), and Noura on 10-01.
48. **Given** a campaign with reason `incident` and no incident ref **Then** 422; a message containing a 10-digit number starting with 2 **Then** saved with the P1-8 warning.

**Register switch**
49. **Given** FD5 **Then** K-36 = 508 talks / 14,800 attendees with the note "5.3 % (attendees)"; with `toolbox_register_from` null **Then** 500 / 14,400.
50. **Given** a daily-return import for 2026-09-20 with toolbox_talks 4 on a project with `toolbox_register_from` 2026-09-01 **Then** the row is imported with warning W08.
51. **Given** `toolbox_register_from` = 2026-09-01 **When** Faisal sets 2026-09-10 **Then** 422 `SETTING_LOOSENING`; 2026-08-20 **Then** saved.
52. **Given** the seed for September 2026 **Then** K-34 85.0 %, K-35 92.5 %, K-35b 42 and K-36 520 talks are unchanged with both switches set on ANIA-EXP (no double counting), and no 6b, 6c or PTW audit record is counted in K-34/K-35.

**KPIs, warnings, AI, PDPL**
53. **Given** FD6 **Then** K-116 for the three units = 93.1 % and SAHARA's reach is capped at 300.
54. **Given** September 2026 **Then** K-110…K-117 match FD9 for both projects.
55. **Given** September 2026 **Then** E20 and E21 are raised for ANIA-EXP as FD9 lists (project and RAWABI tree), none for RBT-52, with T13 inputs and no names.
56. **Given** an order Active from 2026-09-21 to month end **Then** E20 is raised for that month even with all KPIs above threshold.
57. **Given** the AI is asked "which checklist items fail most on Pier B?" **Then** T21 groups by item_code with zone Z-PIERB and the answer cites item codes and texts; "who failed the inspection?" **Then** no names are returned and the assistant says identities are not available to it.
58. **Given** Sarah **Then** she sees K-110…K-117 and registers without photos, attendee names or signatures; Ahmed sees attendance names only for RAWABI-tree workers; an export with names writes an `export` audit row and contains "signed: yes / no", never signature images.
59. **Given** a user logs out of the phone app or 72 h pass **Then** the offline cache is deleted; the cache never contains ID numbers or card tokens.
60. **Given** photos older than 24 months not linked to an open CA, Active order or incident **Then** the retention job deletes them; scores and findings remain.
61. **Given** the UI in Arabic **Then** every 6d label, status, list value, item and topic text, alert, print and error has its AR text; codes, scores and times stay left-to-right inside the RTL layout.

## 10. Open questions for the HSE Manager

Each has a default so the build can start.
1. **Toolbox frequency:** K-116 measures at least one briefing per worker per week. Does the client require a daily pre-start talk to be measured instead?
2. **Scoring:** pass mark 85 %, critical items weight 3, any critical failure = fail. Acceptable, or does the client use its own scoring?
3. **Audit programme:** every contractor with hours audited every 6 months, ISO 45001 internal audit yearly, independent lead auditor. Should tier-3 subcontractors be audited by their tier-1 instead of the PMC?
4. **Offline:** answers and card scans may be kept on the phone up to 72 h, with the crew list of the user's scope cached. Is this acceptable for your sites and the client's IT policy?
5. **Stop-work release:** HSE Officers and site engineers release; contractor staff never. Should the client's representative also sign the release on airside?
6. **Repeat window:** 30 days for the same item, zone and contractor. Longer?
7. **6b and 6c checks:** keep their fixed lists, or move heat welfare and emergency asset checks onto 6d templates in a later version?
8. **Client forms:** does the airport operator or the client require their own FOD walk or audit form to be reproduced exactly?

## 11. Changes required in earlier specs (applied 2026-10-09: 0-foundation v1.2, 1-dashboard v1.7, 2-access-permits v1.6, 3-ptw v1.5, 4-third-party-cert v1.3, 5-training v1.3, 6b-heat-stress v1.1, 6c-emergency-drills v1.1)

### 11.1 `0-foundation.md` v1.1 → v1.2
1. Matrix rows 191–201 (§5.13).

### 11.2 `1-dashboard.md` v1.6 → v1.7
1. §3.7 plan: template_code, rotation, rotation_list, frequency `quarterly` (§3.3); inspection: response link, offline_delay_min, findings read model from 6d (§3.6 mapping); §4.4 Completed → Voided (201).
2. §3.2 import warning **W08** (SRC-2); §3.10 settings `inspection_template_required_from`, `toolbox_register_from` (edited through 193).
3. §3.8 CA `source_type` adds `field_audit` (source_id = 6d audit); `inspection` CAs may be created by 6d (FND-3).
4. §6.1 K-34/K-35/K-35b: inputs from responses from the switch date, Voided excluded (SRC-1); K-36 per SRC-2 / §6.6 with the reconciliation note; new K-110…K-117 by reference.
5. §5.9 AI: T21 (FM-2); T8 adds pooled score and critical fails; T13 returns E20–E21; AI-19 section "Field assurance".
6. §6.9 / §7: E20–E21, same monthly job and recipients.
7. §8.1: tiles, field band, charts C31–C33; `ExpiringItemKind` and action-panel items of §8.2.
8. W1, W7 and every Phase 1 AC stay valid: the W1 fixture has both switches null.

### 11.3 `2-access-permits.md` v1.5 → v1.6
1. §3.20: an `AC` token may be read for toolbox attendance (TBT-5); like a muster scan it creates no gate-log row and runs no eligibility check.
2. P2-8: "card scans at toolbox talks are briefing evidence only; never used for time-keeping or discipline" (P6d-5).

### 11.4 `3-ptw.md` v1.4 → v1.5
1. SH-2: automatic `stop_work` suspension within 60 s for permits named on an Active 6d stop-work order (FND-9; auto_source_ref = order_no).
2. SH-3: resume after a 6d `stop_work` suspension is refused while the order is Active (`STOP_WORK_ACTIVE`).
3. SH-4 note: crew briefings are not toolbox talks (TBT-10). PTW audits unchanged (BD6d-3).

### 11.5 `4-third-party-cert.md`, `5-training.md`, 6b, 6c
No rule changes. Notes only: Phase 4 — 6d reads scaffold tag colour and `EQ` stickers, never writes (BD6d-2, EXE-8); Phase 5 §8.5 — toolbox talks are recorded in 6d and are not training hours (BD5-5 unchanged); 6b/6c — their check lists stay outside 6d in v1.0 (§10 Q7).

## Appendix A — Seed data (fictional; `seed_fake = true`; refs contain `TEST` where printed)

### A.1 Principles
- Builds on the Phase 0–6c seeds. Clock `HSE_CLOCK_AT` = 2026-10-06T10:00:00+03:00.
- Settings: ANIA-EXP `inspection_template_required_from` = **2026-09-01**, `toolbox_register_from` = **2026-09-01**; RBT-52 `inspection_template_required_from` = **2026-09-01**, `toolbox_register_from` = null. All other 6d settings at the §3.14 defaults.
- The generator creates only 6d records and links. It never changes Phase 1–6c KPI values: September 2026 inspection counts equal Phase 1 A.3 and K-36 talks equal A.3 (520). If the Phase 1 generator differs, the backend records the difference in DECISIONS.

### A.2 Libraries
- The 15 templates of §3.15 (GSI at v3; v1 and v2 Superseded with change notes), Published by Faisal.
- 24 topics TT-001…TT-024 (EN/AR; ur, hi, bn translations for 10 of them), e.g. TT-003 heat illness recognition (linked to the W1 #4 incident), TT-014 edges and openings (linked to INC-ANIA-EXP-2026-0147 and GSI-05), TT-019 FOD on the airside (linked to FOD-03), TT-022 temporary electrical safety (ELD-02). TT-009 has review_due_on 2026-09-30 (overdue at the clock, AC42).

### A.3 Plans and inspections (September 2026)
- ANIA-EXP: the Phase 1 A.3 plans get templates (GSI weekly rotating zones on S-LAND; FOD nightly on S-AIR rotating Z-APR-21 / Z-TWB; ELD fortnightly; SCA weekly for SAHARA). September: 40 planned (34 on time, 3 late, 3 missed) + 2 cancelled + 5 unplanned, all 42 completed ones with responses: Σ applicable_weight 1,250, earned 1,135; 64 item findings, 6 repeats; critical fails 2 (below). SAHARA@S-LAND has no inspection in the week ending 09-26.
- Named: **INS-ANIA-EXP-2026-01377** (FD1, Fahad, NAJD, Z-PIERB, 09-24; no earlier GSI-12 non-compliance at Z-PIERB in the window) and the 09-10 and 09-24 GSI-12 non-compliances at Z-MSCP / NAJD (FD3).
- RBT-52: 16 completed inspections in September, Σ 460 / 430, 25 findings, 2 repeats, no critical fail.

### A.4 Stop-work orders and critical fails
| Record | Data |
|---|---|
| SWO-ANIA-EXP-2026-007 | GSI-05 fail at Z-PIERB, NAJD, 2026-09-17 09:30 by Fahad ("open slab edge level 3, grid C-14 to C-20"); instructed supervisor 09:35; no permit named; CA critical; released 2026-09-17 16:40 by Fahad |
| FOD critical fail | FOD-03 at Z-TWB, GULFPAVE, 2026-09-21 02:10 by Omar (night walk); CA critical closed 09-21; no stop rule |

### A.5 Audits
| Audit | Data |
|---|---|
| AUD-ANIA-EXP-2026-011 | CHA, SAHARA, S-LAND, lead Noura, team Fahad, fieldwork 09-07…09-08, issued 09-12 by Faisal, FD2 (34 / 42), 2 major / 4 minor / 10 observations |
| AUD-ANIA-EXP-2026-012 | CHA, GULFPAVE, S-AIR, lead Noura, fieldwork 09-22…09-23, issued 09-27 by Faisal, 1 item `na`, 36 / 43 (83.7 %, B), 1 major / 3 minor |
| History | contractor audits: RAWABI 2026-05-12, NAJD 2026-06-02, SAHARA 2026-03-10, GULFPAVE 2026-03-20; system audit 2026-02-15; QIMMA 2026-06-20 (RBT-52); nothing else due in September |

### A.6 Toolbox talks and campaigns
- ANIA-EXP September: 520 Delivered/Locked talks (day count per date equal to the daily-return toolbox_talks, attendees equal to toolbox_attendees), most in ur, hi, bn or ar with interpreters; about 2 % of named rows `none`. Reach: Σ H over the 20 units (about 11,600, from the Phase 1 seed) = D; the generator places briefed attendance so that Σ reach = round_half_up(0.9240 × D) → K-116 **92.4 %**.
- Named: TBT-ANIA-EXP-2026-04412 (NAJD, Z-PIERB, 2026-09-14 06:30, presenter Rafiq Islam, TT-014, ur + bn interpreter, 38 rows).
- **CMP-ANIA-EXP-2026-004**: TT-014, reason incident INC-ANIA-EXP-2026-0147, issued 2026-09-09 by Faisal, due 09-16, S-LAND: RAWABI, NAJD, SAHARA, all met on time.
- **CMP-ANIA-EXP-2026-005**: TT-003, reason incident (W1 #4), issued 2026-09-23 by Noura, due 09-30, S-AIR: GULFPAVE met 09-24, RAWABI met 10-01 (late).
- RBT-52: daily-return toolbox fields only (register null).

## Change log

| Version | Date | Author | Change |
|---|---|---|---|
| v1.0 | 2026-10-09 | HSE Consultant Agent | First issue. §1–§11 and Appendix A: org-wide versioned bilingual checklist library (item types, weights, critical items, stop rules); Phase 1 plans with templates, rotation and quarterly frequency; weekly contractor coverage; phone execution with offline drafts, photos, findings → Phase 1 CAs, repeat findings, critical-item fail rule and stop-work orders with Phase 3 suspension; contractor and ISO 45001 audits with programme, 0–3 rating, grades and NC findings; toolbox topic library, talks with named attendance (card scan or list), signatures and language check, suggestions, briefing campaigns; K-34/K-35 from answers and K-36 register switch (W08). Capabilities 191–201, KPIs K-110…K-117, warnings E20–E21, AI tool T21, charts C31–C33, CA source `field_audit`. 61 acceptance criteria. Earlier-spec changes in §11, not yet applied. |
| v1.1 | 2026-10-09 | HSE Consultant Agent | Change required by Phase 6e (`6e-environmental.md` v1.0 §11.5); no rule changes: §3.15 seeded templates — ENV v2 supersedes ENV v1; WSA and DSN added (inspection_type `environmental`). |
| v1.2 | 2026-10-09 | HSE Consultant Agent | Changes required by Phase 6f (`6f-incident-followup.md` v1.0 §11.3); the 6d worked examples and seed values are unchanged: (1) §3.10 linked_refs kind `lesson` is validated against Published 6f lessons; CMP-1 reason `lesson` requires a Published lesson the issuer can see (`LESSON_NOT_PUBLISHED`, 6f LK-2); (2) §3.1 the library shows open 6f template change requests on a template to 192 / 193 holders; publishing a version whose change_note names the lesson no. adopts them with that version (6f LK-3); (3) TBT-9 gains step (1b): topics linked to lessons published to the project in the last 30 days, newest first (6f LK-4). |
