# Module Spec — Phase 6f: Incident Follow-up (regulatory and client notification packs with deadlines, submission evidence and overdue tracking; lessons learned with review, distribution, acknowledgement, toolbox and checklist links, library and effectiveness checks)

**Version:** v1.0 · **Date:** 2026-10-09 · **Author:** HSE Consultant Agent · **Status:** Draft. The HSE Manager asked to proceed without waiting for approval and will review the choices later (§10).
**Builds on:**
- `0-foundation.md` v1.2: contractors and engagement tree, roles, scoping legend, rules 28, 35 and 48, PDPL P1–P13, the capability matrix (6e ends at 214).
- `1-dashboard.md` v1.7: incidents (§3.3 `notifications`, airside_flags, do_category, hipo), injury cases (§3.4 person_type, case_category, commuting, permanent_disability, identity fields, gosi_case_ref), investigations (§3.5 level, due_date, root_causes, lessons_learned, approved_at), §4.2 incident states, I-14, I-16, **I-20 / I-21**, CAs (§3.8, CA-1…CA-8), P1-1…P1-8, capabilities 29–31 and 43, the §7 "external notification due" alert, T5, AI-19, the action panel and expiring-items endpoint.
- `6d-field-assurance.md` v1.0: toolbox topics (§3.10 linked_refs kind `lesson`), briefing campaigns (§3.13 reason `lesson`, CMP-1…CMP-4, K-117), checklist templates and versions (§3.1, TPL-1…TPL-3, change_note).
- `6e-environmental.md` v1.0: notification body `ncec` and its trigger (6e §11.2 item 2), setting `env_notifications_from`; numbering ends at capability 214, K-126, E23, T22, C36.
- `docs/DECISIONS.md` #1–#186, in particular #53 (tier-1 trees), #78 (export audit), #124 (no SMS channel).

**Numbering taken by 6f:** capabilities **215–223**; KPIs **K-127…K-131**; warning **E24**; AI tools **T23–T24**; charts **C37–C38**; CA source_type **`lesson`**; `ExpiringItemKind` `notification_stage_due`, `lesson_publish_due`, `lesson_ack_due`, `lesson_effectiveness_due`. No new notification body (the eight Phase 1 + 6e bodies are reused; the PMC is a recipient of the `client` body, NR-9).

**Covers (build order):**
1. 6f.1 Notification rule profile per project (bodies × stages × triggers × deadlines), replacing the fixed I-20 deadlines from a switch date.
2. 6f.2 Notification requirements with stages, due / overdue tracking, waivers.
3. 6f.3 Notification packs: pre-filled bilingual forms and letters from incident data, PDPL field sets, approval.
4. 6f.4 Submission evidence and acknowledgements.
5. 6f.5 Lessons learned: drafting from investigations, review and publication, distribution with acknowledgement, 6d topic / campaign / template-change links, searchable library, effectiveness check.
6. 6f.6 KPIs, warning, dashboard and AI.

**Not in 6f:**
- Electronic filing to GOSI, MHRSD (Qiwa / Musaned), NCEC, GACA or airport systems. No public API is assumed (I-21 stays). The pack is what the filer types into the portal or attaches to the letter.
- Classifying incidents and cases, deciding the investigation level, and the investigation itself (Phase 1). 6f reads them.
- Toolbox talks, campaigns, topics and checklist versions (6d). 6f links to them and opens drafts there.
- GOSI claims, compensation, medical reports and return to work (6a RW rules; insurance claims out of scope).

Conventions: `VERIFY` = clause or number to confirm against the current official text or the client's contract. `ASSUMPTION` = Consultant default; the HSE Manager may override it (§10). "Must" = enforced server-side. Rule prefixes: NR notification rules and requirements, PK packs, SB submissions, LL lessons, DS distribution, LK 6d links, EF effectiveness, FK KPIs/AI, P6f- PDPL, BD6f boundary. Error codes are stable strings (Phase 0 rule 48). Times are local Asia/Riyadh unless marked UTC.

**The principle that shapes this module:** a deadline is only met with evidence, and a lesson is only learned when the people who need it have confirmed it and the event has not happened again.

---

## 1. Purpose

Phase 1 already works out which external bodies must be told about an incident (I-20) and shows due / done / overdue, but the HSE Manager still writes every GOSI data sheet, client flash report and airport-operator occurrence report by hand, from the same incident data, in two languages, at night. Deadlines are fixed in code. The register holds a date and a reference, not proof. The client's interim and final reports are not tracked. "Immediately" has no number, so GACA items are overdue the moment they appear. Lessons learned sit in a 2,000-character field on the investigation that nobody outside the investigation team reads. Nobody can show the client that every contractor on every project received last month's scaffold-fall lesson, or that it worked.

Phase 6f provides:
- a per-project **notification rule profile**: statutory rows (GOSI, MHRSD, Civil Defense, police, GACA, airport operator, NCEC) that can only be tightened, and client / PMC rows from the contract; each row has a stage (verbal, written, interim, final), a trigger from the incident's classification and a deadline in hours;
- **requirements** per incident × body × stage with due times, pre-due and overdue alerts, and waivers with reasons;
- **packs**: pre-filled, bilingual (Arabic for government bodies, EN + AR for the client) data sheets and letters, generated from the incident, case and investigation, with a PDPL field set per body and an approval step;
- **submission evidence** (channel, time, reference, screenshot, stamped copy, email) and acknowledgements;
- a **lessons-learned bulletin** drafted from the investigation, de-identified, approved by the HSE Manager, distributed to projects and contractors with acknowledgement, linked to 6d toolbox topics, campaigns and checklist change requests, searchable, and checked for effectiveness after 90 days;
- KPIs K-127…K-131, warning E24, AI tools T23–T24 and charts C37–C38.

## 2. Regulatory basis

| # | Source | What it drives here |
|---|---|---|
| R1 | **Social Insurance Law** (Royal Decree M/33, 1421H) and the **GOSI Occupational Hazards** branch regulations: the employer notifies GOSI of a work injury within a set period after learning of it (commonly cited as **3 days** `VERIFY` working or calendar days and the article); notification through the GOSI business portal (work-injury report e-service) `VERIFY` current channel and data fields; commuting accidents covered `VERIFY` | GOSI row (written, 72 h), filer = the injured worker's employer engagement (NR-6), GOSI data sheet GOSI-WIR |
| R2 | **Labour Law** (Royal Decree M/51, 1426H) and **MHRSD OSH regulations**: employer reports serious work injuries and deaths to the labour office `VERIFY` article, deadline and channel (Qiwa / labour office) | MHRSD row; fatality 24 h ASSUMPTION (stricter than the Phase 1 default of 3 days), permanent disability 72 h |
| R3 | **Saudi Civil Defense** regulations: fires and explosions reported at once (998) with a written report on request `VERIFY` | Civil Defense verbal 1 h + written 24 h ASSUMPTION |
| R4 | **Public Security / police**: deaths at work reported at once (999 / 911 by region `VERIFY`) | Police verbal 1 h |
| R5 | **GACA** occurrence reporting under GACAR (aerodrome / safety occurrence reporting, Part 139 and the mandatory occurrence reporting provisions `VERIFY` part and timing; ICAO Annex 19 benchmark of 72 h) and the **airport operator's** occurrence-reporting procedure and Works Safety Plan (AOCC / duty manager at once, written report within 24 h `VERIFY` per airport) | GACA written 72 h `VERIFY`; airport operator verbal 1 h + written 24 h; who files to GACA (contractor or operator) is recorded per project (NR-10) |
| R6 | **Environmental Law** Implementing Regulations / **NCEC** environmental incident reporting (6e R1) | `ncec` row exactly as 6e (24 h ASSUMPTION `VERIFY`) |
| R7 | **Client contract / HSE plan** (and PMC procedures; Saudi Aramco CSM or airport client standards where flowed down `VERIFY`): verbal notice, flash report (24 h), interim report, final investigation report | Client rows; recipients include the PMC (NR-9) |
| R8 | **ISO 45001:2018** cl. 10.2 (incident, nonconformity, CA; review effectiveness), cl. 7.4 (communication); ILO Code of Practice on recording and notification (1996) | Lessons workflow, distribution, effectiveness check |
| R9 | **PDPL** and its Implementing Regulations: purpose limitation and minimisation for health and identity data disclosed to third parties; disclosure to a public body under a legal obligation is lawful, disclosure to the client needs a contractual basis `VERIFY` | Field sets per body (§3.6 list FS), P6f rules |
| R10 | **Hijri calendar**: government letters carry the Umm al-Qura Hijri date with the Gregorian date | Letter header (PK-4) |

Strictest-wins applied in this spec (and why):
- **Statutory rows only tighten** (NR-3). A client may ask for faster reporting; nobody may slow a legal deadline.
- **"Immediately" = 1 hour ASSUMPTION** for verbal stages. Phase 1 set due = occurred_at, which can never be met; a measurable hour is the strictest workable reading, and the written stage keeps its own deadline.
- **MHRSD fatality 24 h** ASSUMPTION, tighter than the Phase 1 default (3 days), because a death is also reported to the police and the client within hours and the labour office will ask the same day.
- **A reclassification never extends a deadline** (NR-5): the clock starts at occurrence; it starts later only when the trigger itself first became true later (e.g. MTC → LTI), never because the report was late.
- **Client packs are de-identified by default** (P6f-2): the client receives "Person 1 · scaffolder · NAJD", not the name, unless the HSE Manager records the contractual basis.

## 3. Entities & fields

PDPL column: **none / personal / sensitive** (Phase 0 P1–P2). Every entity carries the Phase 0 system fields, is audited (Phase 0 rule 35) and stores `seed_fake`. AR labels are shown in the UI.

### 3.1 Notification rule (project profile row) — قاعدة الإخطار

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| rule_code | الرمز | string(16) | Y | unique per project | GACA-W | none |
| body | الجهة | enum | Y | Phase 1 body: `gosi` · `mhrsd` · `civil_defense` · `police` · `gaca` · `airport_operator` · `client` · `ncec` | gaca | none |
| stage | المرحلة | enum | Y | `verbal` إبلاغ شفهي · `written` إخطار كتابي · `interim` تقرير مرحلي · `final` تقرير نهائي | written | none |
| source | المصدر | enum | sys | `statutory` (seeded, NR-3) · `client` | statutory | none |
| triggers | الحالات الموجبة | enum[] | Y | ≥ 1 of list NT; any one true ⇒ required | [gaca_airside_flag] | none |
| deadline_hours | المهلة (ساعات) | int | cond. | 1–720; not for `final` with basis investigation | 72 | none |
| deadline_basis | أساس المهلة | enum | Y | `trigger` (NR-5) · `investigation_due` (final stage: end of the investigation due_date) | trigger | none |
| form_code | النموذج | enum | cond. | list PF; null for `verbal` | GACA-OCR | none |
| filer | جهة الإبلاغ | enum | Y | `main_contractor` · `employer_engagement` (GOSI) · `airport_operator` (operator files to GACA, NR-10) | main_contractor | none |
| active | فعّالة | bool | Y | statutory rows: true only | true | none |

### 3.2 Project follow-up profile (one per project)

client_recipients list {organisation_en/ar, role `client` العميل · `pmc` الاستشاري, email} (≥ 1 when any client row is active); body_directory list {body, office_name_en/ar (e.g. "GOSI — Riyadh branch"), address_or_portal, email}; letterhead (file, PNG/SVG ≤ 2 MB); signatory_role_en/ar (a role, not a name, e.g. "Project HSE Manager"). PDPL: none.

### 3.3 Notification requirement — متطلب الإخطار (extends the Phase 1 `notifications` item, §11.2)

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| incident_id / body / stage | الحادثة / الجهة / المرحلة | FK / enum / enum | sys | unique (incident, body, stage) | INC-ANIA-EXP-2026-0161 / gaca / written | none |
| rule_code | القاعدة | string | sys | rule in force when first required | GACA-W | none |
| trigger_met_at | وقت تحقق الموجب | timestamptz | sys | NR-5 | 2026-10-04 23:30 | none |
| due_at | موعد الاستحقاق | timestamptz | sys | §6.1 | 2026-10-07 23:30 | none |
| filer_engagement_id | المقاول المُبلِّغ | FK | cond. | GOSI: the case's employer engagement | NAJD@ANIA-EXP | none |
| case_ids | الحالات | FK[] | cond. | GOSI / MHRSD / police: the cases that trigger it (one GOSI requirement per case, NR-6) | [P1] | none |
| status | الحالة | enum | sys | §4.1 | due | none |
| waiver_reason_code / waiver_text | سبب الإعفاء | enum / text(500) | cond. | list WV; text ≥ 20 chars; evidence file for `reported_by_other_party` | — | none |

### 3.4 Notification pack — حزمة الإخطار

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| pack_no | رقم الحزمة | string | sys | `NP-<project>-<yyyy>-<nnnn>` | NP-ANIA-EXP-2026-0058 | none |
| requirement_id / version | المتطلب / الإصدار | FK / int | sys | one non-superseded pack per requirement | — / 1 | none |
| form_code / field_set | النموذج / مجموعة الحقول | enum / enum | sys | from the rule (list PF) and list FS | GOSI-WIR / identity_medical | none |
| languages | اللغات | enum[] | sys | list PF default; client may add `en` / `ar` | [ar] | none |
| snapshot | البيانات المجمّدة | json | sys | field values at generation (PK-2) | — | per field set |
| narrative_en / _ar | السرد | text(3000) ×2 | Y (≥ 1) | prefilled with the de-identified description (PK-3); P6f-3 checks | — | personal (possible) |
| extra_fields | حقول إضافية | json | N | per list PF (e.g. treating facility, employer GOSI no.) | {facility: "King Fahd Hospital (test)"} | personal |
| file | الملف | file (PDF) | sys | rendered at approval; identity packs in the encrypted bucket (P6f-4) | — | per field set |
| prepared_by / approved_by / approved_at | أعدّها / اعتمدها | FK / FK / timestamptz | sys | approver holds 217 | Ahmed / Ahmed / 10-05 10:40 | personal |
| status | الحالة | enum | sys | §4.2 | approved | none |

### 3.5 Submission — إثبات الإرسال

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| submission_no | الرقم | string | sys | `NS-<project>-<yyyy>-<nnnn>` | NS-ANIA-EXP-2026-0071 | none |
| requirement_id / pack_id | المتطلب / الحزمة | FK / FK | Y / cond. | SB-2 | — | none |
| channel | وسيلة الإرسال | enum | Y | `portal` بوابة إلكترونية · `email` بريد · `hand_delivered` تسليم باليد · `courier` بريد سريع · `phone_radio` هاتف/لاسلكي (verbal only) · `meeting` اجتماع (verbal only) | portal | none |
| submitted_at | وقت الإرسال | timestamptz | Y | ≥ incident occurred_at; ≤ now + 5 min (`SUBMITTED_AT_INVALID`) | 2026-10-05 11:00 | none |
| contacted_desk_en/_ar | الجهة/المكتب المُتصل به | string(120) | cond. | verbal: a desk or role (e.g. "AOCC duty manager"), never a private person's name | AOCC duty manager | none |
| reference_no | الرقم المرجعي | string(60) | cond. | SB-3 | GOSI-TEST-0412 | none |
| evidence_files | الأدلة | file[] ≤ 5 | cond. | SB-3: portal screenshot, sent email (.eml/.pdf), stamped copy | — | personal (possible) |
| external_document | مستند خارجي | file | cond. | SB-2: when no approved pack is used | — | per content |
| acknowledged_at / ack_reference / ack_file | الاستلام من الجهة | timestamptz / string(60) / file | N | ≥ submitted_at | 2026-10-05 13:20 / AO-ACK-TEST-77 | none |
| on_time | في الموعد | bool | sys | submitted_at ≤ requirement.due_at | true | none |
| status | الحالة | enum | sys | `recorded` · `acknowledged` · `voided` (217, reason ≥ 20 chars) | recorded | none |

### 3.6 Lesson learned — الدرس المستفاد

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| lesson_no | الرقم | string | sys | `LL-<yyyy>-<nnn>`, org-wide | LL-2026-007 | none |
| source | المصدر | enum + ref | Y | `incident` (Phase 1 incident with an investigation) · `external` (client / industry alert; reference text) | incident INC-ANIA-EXP-2026-0147 | none |
| title_en / _ar | العنوان | string(150) ×2 | Y to publish | — | Unprotected platform edge during scaffold alteration / حافة منصة غير محمية أثناء تعديل السقالة | none |
| what_happened_en / _ar | ماذا حدث | text(1500) ×2 | Y to publish | prefilled de-identified (LL-2); P6f-3 | — | none (checked) |
| why_en / _ar + root_cause_codes | لماذا حدث | text(1500) ×2 + list R codes | Y to publish | codes copied from the investigation, editable | AD-01, OF-04, TE-08 | none |
| key_lessons | الدروس الرئيسية | list {text_en, text_ar} | Y to publish | 1–5 items, both languages | "Never remove a guardrail without a scaffold-alteration permit" | none |
| actions_taken | الإجراءات المتخذة | list {ca_ref, control_level} | N | CAs of the source incident (read) | [CA-…-00871 engineering] | none |
| applicability | نطاق التطبيق | {activities (list A), zone_types, trades (list T), mechanisms (list M), do_categories} | Y (≥ 1 activity) | — | {scaffolding, work_at_height · landside, airside · scaffolder · fall_from_height} | none |
| severity_potential | الشدة المحتملة | int | sys | from the incident | 4 | none |
| photos | الصور | file[] ≤ 4 | N | `redaction_confirmed` true required for each (`REDACTION_NOT_CONFIRMED`) | — | none once redacted |
| distribution | التوزيع | list §3.7 + project_ids | cond. | ≥ 1 project to publish (`NOT_DISTRIBUTED`) | [ANIA-EXP, RBT-52] | none |
| publish_due_on | موعد النشر | date | sys | LL-1 | 2026-10-05 | none |
| author_id / approved_by / published_at | المُعد / المعتمد / تاريخ النشر | FK / FK / timestamptz | sys | approver ≠ author (`SELF_APPROVAL`) | Noura / Faisal / 2026-09-24 10:00 | personal |
| status | الحالة | enum | Y | §4.4 | published | none |

### 3.7 Distribution item — بند التوزيع
lesson_id; project_id; engagement_id (pairs fixed at publication, DS-1); ack_due_on (sys: publication date + `lesson_ack_days`); acknowledged_by / acknowledged_at (personal); response (`will_brief` سيتم التوعية · `not_applicable` لا ينطبق, reason ≥ 20 chars); on_behalf_note (cond., DS-3); status `pending` · `acknowledged` · `not_applicable` · `withdrawn` (lesson archived). PDPL: none except the acknowledging user (personal).

### 3.8 Lesson link — روابط الدرس (to 6d)
kind `topic` (6d topic code; new draft or existing) · `campaign` (6d campaign no., reason `lesson`) · `template_change` (template_code, item_code or "new item", proposed_text_en/_ar, status `open` · `adopted` (version no.) · `rejected` (reason ≥ 20 chars, 193 holder)). PDPL: none.

### 3.9 Effectiveness check — التحقق من الفعالية
lesson_id; due_on (sys: publication date + `lesson_effectiveness_days`); facts (sys snapshot at completion: recurrence incident refs, ack rate, linked campaign pairs met / total, source CAs closed / total); suggested_result (sys, EF-3); result `effective` فعّال · `partly_effective` فعّال جزئياً · `not_effective` غير فعّال; rationale (text ≥ 20 chars, cond. EF-4); follow_up (CA ref or re-issued lesson no., cond. EF-5); completed_by / completed_at (personal). Status `scheduled` · `completed`.

### 3.10 Phase 6f project settings
Only the HSE Manager edits them (capability 218); audited; "Allowed" is the only range accepted; a loosening value gets 422 `SETTING_LOOSENING`.

| Key | AR label | Type | Default | Allowed |
|---|---|---|---|---|
| followup_rules_from | بدء قواعد الإخطار الجديدة | date / null | null | ≥ project start; ≤ today; once set only moves earlier |
| notification_alert_lead_hours | التنبيه قبل الاستحقاق | int | 24 (stages ≥ 24 h); stages < 24 h alert at due − 25 % of the window | 2–48; only raise |
| client_pack_identity | هوية المصاب في تقارير العميل | enum | `none` | `none` · `name_and_trade` (requires a contract-clause text ≥ 20 chars, audited; P6f-2) |
| lesson_required_levels | مستويات التحقيق الموجبة لدرس | enum[] | [L3] | may add L2 |
| lesson_publish_days | مهلة نشر الدرس | int | 14 ASSUMPTION | 3–30; only lower |
| lesson_ack_days | مهلة الإقرار بالدرس | int | 7 ASSUMPTION | 1–14; only lower |
| lesson_effectiveness_days | موعد التحقق من الفعالية | int | 90 ASSUMPTION | 30–180 |
| followup_warning_pct / lesson_ack_warning_pct | حدود الإنذار | decimal ×2 | 95.0 / 85.0 ASSUMPTION | 50.0–100.0; only raise |

### 3.11 Reference lists (seeded EN/AR; codes immutable)

**NT — triggers** (evaluated on the incident and its cases; Draft and Voided incidents trigger nothing): `recordable_contractor_case` (a contractor_worker case FAT/LTI/RWC/JTC/MTC) · `commuting_case` · `fatality` · `permanent_disability` · `lti` · `fire_explosion_do` (do_category fire_explosion) · `any_do` · `hipo` · `gaca_airside_flag` (runway_incursion, aircraft_involved, ols_infringement, notam_breach) · `any_airside_flag` · `env_ncec` (6e condition) · `env_airside` (environmental in an airside zone, 6e) · `any_recordable_case` (any person type) · `property_damage_ge_sar` (parameter, SAR).

**Default statutory profile** (seeded on every project; client rows seeded per §A.2):

| rule_code | body · stage | triggers | deadline | form · filer |
|---|---|---|---|---|
| GOSI-W | gosi · written | recordable_contractor_case, commuting_case | 72 h `VERIFY` R1 | GOSI-WIR · employer_engagement |
| MHRSD-F | mhrsd · written | fatality | 24 h ASSUMPTION `VERIFY` R2 | MHRSD-LTR · main_contractor |
| MHRSD-PD | mhrsd · written | permanent_disability | 72 h `VERIFY` R2 | MHRSD-LTR · main_contractor |
| POL-V | police · verbal | fatality | 1 h | — · main_contractor |
| CD-V / CD-W | civil_defense · verbal / written | fire_explosion_do | 1 h / 24 h ASSUMPTION `VERIFY` R3 | — / CD-LTR · main_contractor |
| GACA-W | gaca · written | gaca_airside_flag | 72 h `VERIFY` R5 | GACA-OCR · main_contractor (or airport_operator, NR-10) |
| AO-V / AO-W | airport_operator · verbal / written | gaca_airside_flag (V); any_airside_flag, env_airside (W) | 1 h / 24 h `VERIFY` R5 | — / AO-OCR · main_contractor |
| NCEC-W | ncec · written | env_ncec | 24 h (6e) | NCEC-EIR · main_contractor |

**PF — forms** (languages · field set): `GOSI-WIR` GOSI work-injury data sheet بيانات بلاغ إصابة عمل (ar · identity_medical: employer name, CR and GOSI establishment no., worker name AR/EN, ID type and number, nationality, occupation, date / time / place, how it happened, body part, nature, treating facility, first day off work, reporter role; fields mirror the portal `VERIFY` R1) · `MHRSD-LTR` letter to the labour office (ar · identity) · `CD-LTR` letter to Civil Defense (ar · none) · `GACA-OCR` / `AO-OCR` occurrence report (en + ar · none: date, time, location with stand / taxiway, aircraft or vehicle involved by registration or fleet no., NOTAM / WSP refs, immediate actions, operational impact) · `NCEC-EIR` environmental incident report (ar · none; 6e spill fields) · `CLIENT-FLASH` / `CLIENT-INTERIM` / `CLIENT-FINAL` (en + ar · `client_pack_identity`: none → case rows "Person n · trade · employer"; FINAL needs an approved investigation and adds causes, root-cause codes, CAs with control levels and the lesson no. when published).

**FS — field sets:** `none` (no identity, no medical) · `identity` (name, ID, nationality, occupation) · `identity_medical` (identity + body part, nature, treating facility, first day off and days off; never treatments, medical notes or attachments).

**WV — waiver reasons:** `not_covered_by_gosi` (e.g. a person not insured by the employer, evidence text) · `body_confirmed_not_required` (written confirmation file) · `reported_by_other_party` (e.g. the airport operator filed to GACA; their reference and file required) · `incident_reclassified` (trigger no longer true before due; system-set, NR-7).

**Default client rows** (`source` client; editable): CL-V client · verbal · [fatality, lti, any_do, hipo] · 1 h ASSUMPTION; CL-F client · written (CLIENT-FLASH) · same triggers · 24 h (Phase 1 default); CL-I client · interim · same · 72 h ASSUMPTION; CL-FIN client · final · [fatality, lti, any_do, hipo] · investigation_due.

## 4. Workflow / states

"Who" = capability numbers (§5.10). Jobs: `followup_minute` (every 60 s: requirement derivation after incident / case changes, verbal-stage alerts), `followup_daily` 00:13:00 (lesson due dates, ack overdue, effectiveness scheduling, retention; after `env_daily`), `followup_alerts` 07:10.

### 4.1 Notification requirement (derived status)
`due` مستحق (no valid submission, now ≤ due_at) · `overdue` متأخر (no valid submission, now > due_at) · `submitted` تم الإرسال (valid submission; on_time or late) · `acknowledged` تم الاستلام · `waived` معفى (218, list WV) · `not_required` (NR-7). A voided submission returns the requirement to due / overdue.

### 4.2 Pack
Draft (216, generated) → Approved (217; file rendered) → Submitted (System, when a submission names it) · Draft / Approved → Superseded (216 regenerates; version + 1) · Approved → Draft (217, before submission). A Submitted pack is immutable (`PACK_IMMUTABLE`, 409).

### 4.3 Submission
Recorded (216) → Acknowledged (216; ack fields) · Recorded / Acknowledged → Voided (217, reason ≥ 20 chars).

### 4.4 Lesson
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Draft | مسودة | System (LL-1) or 219 | investigation approved at a required level, or manual |
| Draft → In Review | قيد المراجعة | 219 (author) | LL-3 completeness |
| In Review → Draft | مسودة | 220 | returned with comment |
| In Review → Published | منشور | 220, ≠ author | distribution chosen; DS-1 pairs fixed; alerts sent |
| Published → Archived | مؤرشف | 220 | reason ≥ 20 chars or superseded by a newer lesson; pending items → withdrawn |
| Draft → deleted | — | author | manual drafts only; system drafts can only be archived by 220 with a reason (LL-1) |

## 5. Business rules

### 5.1 Rules and requirements (NR)
- NR-1. From `followup_rules_from`, the requirements of an incident with occurred_at ≥ that date come from the project's active rules (§3.1); before it, or with the setting null, Phase 1 I-20 applies unchanged and each Phase 1 item is shown as stage `written`.
- NR-2. A requirement exists for each active rule with a true trigger, one per (incident, body, stage); GOSI and MHRSD-F rows produce one requirement per triggering case (NR-6). Derivation reruns within 60 s of any change to the incident, its cases or its investigation.
- NR-3. **Statutory rows only tighten:** deadline_hours may be lowered and triggers added; raising hours, removing triggers or deactivating → 422 `RULE_LOOSENING`. Client rows are edited freely by 218 (contract terms) and every change is audited; a change applies to requirements created after it.
- NR-4. Seeded statutory rows equal the §3.11 table; `ncec` and `env_airside` follow 6e and its `env_notifications_from` (6e AC41 unchanged).
- NR-5. **Clock start:** trigger_met_at = occurred_at when the trigger is true at Reported; otherwise the time of the change that first made it true (e.g. a case reclassified MTC → LTI). A late report never moves trigger_met_at. due_at per §6.1.
- NR-6. **GOSI** is the employer's duty: one requirement per triggering contractor_worker case, filer_engagement = the case's employer engagement; its Contractor HSE Rep and the HSE Officers are alerted. The main contractor tracks it but the evidence is the employer's submission.
- NR-7. A trigger that stops being true before any submission (case downgraded, incident voided) sets `not_required` (reason `incident_reclassified`); a requirement already submitted stays submitted with the note "trigger no longer applies".
- NR-8. **Waiver** by 218 only, with a list WV reason, text ≥ 20 chars and, for `body_confirmed_not_required` and `reported_by_other_party`, an evidence file and (for the latter) the other party's reference (`WAIVER_EVIDENCE_REQUIRED`). Waived items leave K-127 and stay in the register.
- NR-9. The client body addresses every client_recipients row (client and PMC) in one pack and one submission ASSUMPTION; a client row with no recipients cannot be activated (`CLIENT_RECIPIENT_REQUIRED`).
- NR-10. Where the airport operator files to GACA, the GACA-W row's filer is `airport_operator`: the requirement is met by a submission recording the operator's reference (channel `email` or `portal`, evidence = the operator's confirmation) or waived `reported_by_other_party`.

### 5.2 Packs (PK)
- PK-1. A pack is generated by 216 for a requirement with a form; identity field sets need capability 29 (`identity`) and 29 + 30 (`identity_medical`) in scope, else 403. Exception: a Contractor HSE Rep holding 29 in C scope may generate GOSI-WIR for an employer engagement in that scope (the employer is the filer and already holds the data); list FS limits its medical part to body part, nature, treating facility and first day off. Generation and each download write `sensitive_field_read` (P1-1) and an `export` audit row with purpose = the body (P1-6, DECISIONS #78).
- PK-2. Generation copies the field values into `snapshot`; later incident edits do not change the pack. The pack page shows "incident changed since generation" when any snapshot field differs, and regeneration creates version + 1 (the old version Superseded).
- PK-3. The narrative is prefilled from the incident description with injured names and ID numbers redacted server-side (as T5); immediate actions and, for FINAL, the investigation fields are appended.
- PK-4. Rendering: letterhead, addressee from body_directory, pack_no as the letter reference, date in Gregorian and Umm al-Qura Hijri for government forms, bilingual two-column layout for client forms, signatory role, "prepared by" role. Arabic is the legally binding text on government forms; English translation is an annex when the form lists `en`.
- PK-5. FINAL client packs need the investigation Approved (`INVESTIGATION_NOT_APPROVED`).
- PK-6. Approval by 217; a Contractor HSE Rep approves only GOSI packs whose filer engagement is in their C scope.

### 5.3 Submissions (SB)
- SB-1. Recorded by 216 (Contractor HSE Reps: GOSI requirements of their C-scope employer engagements, and other bodies for incidents whose responsible engagement is in their C scope ASSUMPTION).
- SB-2. A `written`, `interim` or `final` submission needs an Approved pack of that requirement or an external_document (`PACK_NOT_APPROVED`); `phone_radio` and `meeting` channels are accepted only for `verbal` stages (`CHANNEL_NOT_ALLOWED`).
- SB-3. **Evidence:** verbal → contacted_desk and (reference_no or call time note); written stages → reference_no or ≥ 1 evidence file, and `hand_delivered` needs a stamped-copy file (`EVIDENCE_REQUIRED`).
- SB-4. The first valid submission sets the requirement's status and fills the Phase 1 `notified_at`, `reference_no`, `notified_by` read fields (one source of truth, §11.2). Recording through the Phase 1 notification endpoint creates a submission with channel `email`, no pack, and is accepted only with an evidence file from `followup_rules_from` on.
- SB-5. A submission is editable for 24 h by its recorder, then only voided (`SUBMISSION_LOCKED`, 409).

### 5.4 Lessons (LL)
- LL-1. When an investigation at a level in `lesson_required_levels` is approved, a Draft lesson is created (author = lead investigator) with publish_due_on = approval date + `lesson_publish_days`, prefilled from the investigation (lessons_learned → key lessons, root-cause codes, title, activity, mechanisms, zone type, CAs). Alerts at publish_due_on − 3 days and on the day after it to the author, the HSE Officers and the HSE Manager.
- LL-2. what_happened is prefilled from the incident with names and IDs redacted (PK-3); dates are reduced to month and year, and the project is named but the zone is generalised to its zone_type.
- LL-3. **Completeness to submit and publish** (`LESSON_INCOMPLETE`, with the list): EN and AR title, what_happened, why and key lessons; ≥ 1 activity; each photo redaction_confirmed. P6f-3 identity check.
- LL-4. Publication by 220, approver ≠ author (`SELF_APPROVAL`), with ≥ 1 project (`NOT_DISTRIBUTED`). A lesson may be published to any project of the organisation (cross-project learning).
- LL-5. Library: Published and Archived lessons are visible to every 222 holder (Archived marked). Search covers EN and AR text with Arabic normalisation (diacritics removed; أ إ آ → ا; ة → ه; ى → ي; leading ال ignored) ASSUMPTION; filters activity, mechanism, root-cause code, zone_type, trade, project, year.
- LL-6. **Similar lessons:** when an incident is Reported, its page lists up to 3 Published lessons, ranked by matches on (activity, mechanism or do_category, root-cause codes), newest first on ties; the investigation team sees them when the investigation opens.

### 5.5 Distribution and acknowledgement (DS)
- DS-1. At publication, one item per (project, engagement) with daily-return headcount > 0 on that project in the 14 days before (as 6d CMP-2). The publisher may remove an engagement before publishing with a reason ≥ 20 chars.
- DS-2. Each project's HSE Officers and site engineers get an in-app notice (no acknowledgement); each item's Contractor HSE Reps get in-app + email with the bulletin PDF (EN + AR).
- DS-3. Acknowledged by 221: a Contractor HSE Rep with C scope over the engagement (a tier-1 rep may acknowledge for descendant engagements ASSUMPTION); an HSE Officer only for an engagement with no active Contractor HSE Rep user, with on_behalf_note ≥ 20 chars (`ON_BEHALF_NOTE_REQUIRED`). `not_applicable` needs a reason ≥ 20 chars and counts as acknowledged.
- DS-4. Reminder at ack_due_on − 2 days to pending items' reps; on the day after ack_due_on, alert to the reps and the project's HSE Officers; weekly while pending.

### 5.6 Links to 6d (LK)
- LK-1. From a lesson, 219 holders may (a) link an existing 6d topic or open a 6d topic Draft prefilled with title and key lessons (published through 6d 193), which adds `lesson` to the topic's linked_refs; (b) open a 6d campaign Draft with reason `lesson` and reason_ref = the lesson no. (issued through 6d 197); (c) raise a template change request.
- LK-2. A 6d campaign with reason `lesson` requires a Published lesson the issuer can see (`LESSON_NOT_PUBLISHED`).
- LK-3. Template change requests appear in the 6d library on that template for 192 / 193 holders. Publishing a 6d version whose change_note contains the lesson no. marks the request `adopted` with that version; 193 may reject it with a reason. Requests open > 30 days are on the action panel.
- LK-4. 6d TBT-9 suggestion order gains, after (1), topics linked to lessons published to the project in the last 30 days, newest first (§11.3).

### 5.7 Effectiveness (EF)
- EF-1. A check is scheduled at publication with due_on = publication date + `lesson_effectiveness_days`; alerts at due_on and weekly while not completed to the HSE Officers of the source project.
- EF-2. **Recurrence:** a non-voided incident on a distributed project, occurred after published_at and on or before the check date, that matches the lesson by (same activity and same mechanism of any case) or (same do_category) or (same activity and ≥ 1 shared root-cause code). The facts snapshot lists them by ref.
- EF-3. **Suggested result:** `not_effective` if a recurrence has potential_severity ≥ 4; else `partly_effective` if any recurrence, or ack rate < 90.0 %, or a linked campaign has unmet pairs, or a source CA is not Closed; else `effective`.
- EF-4. Completed by 223; a result different from the suggestion needs rationale ≥ 20 chars (`RATIONALE_REQUIRED`).
- EF-5. `not_effective` needs follow_up: a Phase 1 CA with source_type `lesson` (priority high, owner chosen by the reviewer) or a new lesson that supersedes it (`FOLLOW_UP_REQUIRED`).

### 5.8 KPIs and AI (FK)
- FK-1. All 6f KPIs are computed from stored records (K-R1). Attribution: requirements → local date(due_at), contractor = incident responsible engagement (GOSI → filer engagement); lessons → publish_due_on; distribution items → ack_due_on, contractor = the item's engagement; checks → completed date. Contractor filter with descendants as K-R5.
- FK-2. **T23 `get_followup_kpis`** (project_ids, period, filters {engagement, include_descendants, body, stage, source}, metrics K-127…K-131, group_by {body, stage, month, contractor, project}) returns aggregates and requirement counts only.
- FK-3. **T24 `search_lessons`** (query, filters as LL-5, limit ≤ 10) returns Published lessons only: lesson_no, titles, key lessons, why text, root-cause codes, applicability, project and month; never source incident identity, packs, submissions or acknowledging users. AI recommendations citing a lesson quote its lesson_no. T13 returns E24; AI-19 gains a section "Incident follow-up" (K-127…K-131, overdue statutory items by body, lessons published).

### 5.9 PDPL (P6f-x)
- P6f-1. **Sensitive:** pack snapshots and files of field sets `identity` and `identity_medical`. **Personal:** preparer, approver, recorder and acknowledger identities; evidence files (may show names); contacted desk. **None:** rules, requirements, lessons (after P6f-3), distribution and check facts.
- P6f-2. Client packs follow `client_pack_identity`; never ID numbers, nationality or medical detail beyond the case category, body part and days off. The PMC receives exactly what the client receives.
- P6f-3. **Identity check:** pack narratives (field set `none`) and lesson texts are checked against the source incident's case person_name tokens (≥ 3 characters) and id_numbers, in AR and EN; a match → 422 `IDENTITY_IN_TEXT`. The P1-8 scan warns as usual.
- P6f-4. Identity pack files live in the encrypted bucket (P1-3) with signed URLs ≤ 5 min; they are never in bulk exports. At identity anonymisation (P1-5) the files and identity snapshot fields are deleted; pack_no, body, stage, dates and submission references remain.
- P6f-5. Viewer/Client sees requirement status and dates, submissions without evidence files, and the lesson library; never packs.
- P6f-6. Requirements, packs (non-identity), submissions and lessons are kept for the project life + 10 years ASSUMPTION (aligned with P1-5 incident retention).

### 5.10 Permission matrix — Phase 6f extension
Continues 6e §5.17. Legend A/P/S/C/C1/R/—.

| # | Capability | HSE Mgr | HSE Officer | Site Eng/Sup | Permit Issuer | Permit Receiver | Contractor HSE Rep | Viewer/Client | OH Pract. |
|---|---|---|---|---|---|---|---|---|---|
| 215 | View notification requirements, submissions, follow-up KPIs and action panel | A | P | S | S | C1 | C | P (no packs or evidence files) | — |
| 216 | Generate packs; record submissions and acknowledgements | A | P | — | — | — | C (SB-1) | — | — |
| 217 | Approve packs; void submissions | A | P | — | — | — | C (GOSI packs, PK-6) | — | — |
| 218 | Edit rule profile, recipients, body directory and 6f settings; waive requirements | A | — | — | — | — | — | — | — |
| 219 | Draft lessons, submit for review; 6d links and change requests | A | P | S | — | — | C | — | — |
| 220 | Publish, return and archive lessons; choose distribution | A | — | — | — | — | — | — | — |
| 221 | Acknowledge lessons for an engagement | A | P (DS-3) | — | — | — | C | — | — |
| 222 | View and search the lesson library | A | P | P | P | P | P | P | P |
| 223 | Complete effectiveness checks | A | P | — | — | — | — | — | — |

Suspended-contractor users keep reads and lose writes (Phase 0 rule 28).

### 5.11 Phase-boundary rules (BD6f)
- BD6f-1. 6f owns no hook kind. It reads Phase 1 incidents, cases, investigations, CAs and daily returns, 6e conditions, and 6d topics, campaigns and versions. It writes requirement state and the Phase 1 notification read fields (SB-4), CAs (source `lesson`), and 6d drafts and linked_refs (LK-1).
- BD6f-2. 6f never changes a case category, investigation level or due date. K-16, K-26 and every Phase 1 rate are unchanged.

### 5.12 Error and warning codes (new)
422 `RULE_LOOSENING`, `CLIENT_RECIPIENT_REQUIRED`, `WAIVER_EVIDENCE_REQUIRED`, `INVESTIGATION_NOT_APPROVED`, `PACK_NOT_APPROVED`, `CHANNEL_NOT_ALLOWED`, `EVIDENCE_REQUIRED`, `SUBMITTED_AT_INVALID`, `IDENTITY_IN_TEXT`, `LESSON_INCOMPLETE`, `REDACTION_NOT_CONFIRMED`, `SELF_APPROVAL`, `NOT_DISTRIBUTED`, `ON_BEHALF_NOTE_REQUIRED`, `LESSON_NOT_PUBLISHED`, `RATIONALE_REQUIRED`, `FOLLOW_UP_REQUIRED`, `SETTING_LOOSENING`; 409 `PACK_IMMUTABLE`, `SUBMISSION_LOCKED`.

## 6. Calculations

Rounding half-up at output only (K-R8): percentages 1 dp. Comparisons use unrounded values.

### 6.1 Due time
- basis `trigger`: due_at = trigger_met_at + deadline_hours.
- basis `investigation_due`: due_at = 23:59:59 local on the investigation due_date in force when the requirement is created (a later Phase 1 extension does not move it ASSUMPTION).
- Pre-due alert at due_at − `notification_alert_lead_hours` for windows ≥ 24 h, else at due_at − 25 % of the window (verbal 1 h → 45 min after trigger).

### 6.2 KPI catalogue (continues 6e §6.7)

| ID | Metric (EN / AR) | Formula | Unit / display | Better |
|---|---|---|---|---|
| K-127 | **Notifications on time** / الإخطارات في الموعد | n(requirements not waived / not_required, due_at in period and ≤ as_of, first valid submission on_time) ÷ n(requirements not waived / not_required, due_at in period and ≤ as_of) × 100; chips: statutory %, client % | %, 1 dp | higher |
| K-128 | **Overdue notifications** / الإخطارات المتأخرة | n(requirements overdue at as_of); chip statutory | count | lower |
| K-129 | Lessons published on time / نشر الدروس في الموعد | n(required lessons published on or before publish_due_on) ÷ n(required lessons with publish_due_on in period and (≤ as_of or published)) × 100 | %, 1 dp | higher |
| K-130 | **Lesson acknowledgement on time** / الإقرار بالدروس في الموعد | n(items acknowledged or not_applicable on or before ack_due_on) ÷ n(items not withdrawn with ack_due_on in period and ≤ as_of) × 100 | %, 1 dp | higher |
| K-131 | Lesson effectiveness / فعالية الدروس | n(checks completed in period with `effective`) ÷ n(checks completed in period) × 100; chip recurrences | %, 1 dp | higher |

Denominator 0 → "—".

### 6.3 Leading-indicator warning
Monthly job, day 2 at 07:00, per project and per tier-1 tree (DECISIONS #53).
- **E24 Incident follow-up** in M: a statutory requirement overdue at month end or submitted late in M; or K-127(M) < `followup_warning_pct` with ≥ 5 items; or K-130(M) < `lesson_ack_warning_pct` with ≥ 5 items; or a required lesson past publish_due_on at month end; or an effectiveness check completed `not_effective` in M. T13 inputs: numerators, denominators, thresholds, requirement bodies and lesson numbers; never names.

### 6.4 Worked examples (exact; backend unit tests must match)

**FU1 — GOSI and reclassification** (fixture; ANIA-EXP, `followup_rules_from` 2026-10-01). Incident occurred **2026-10-03 14:20**, reported 15:00, NAJD steel fixer, case P1 MTC (sutures), potential severity 2. Requirements: GOSI-W (filer NAJD) due **2026-10-06 14:20**; no client rows (MTC, not HiPo). Creation alert to the NAJD-tree rep (Ahmed) and Noura; the pre-due alert would go at 10-05 14:20 but is not sent because the requirement is submitted first. Ahmed generates GOSI-WIR (identity_medical), approves it, records a portal submission 2026-10-05 11:00 ref GOSI-TEST-0412 with screenshot → submitted, on time. On **2026-10-07 09:00** P1 becomes LTI (days away) → trigger_met_at for client rows = 10-07 09:00: CL-V due **10:00**, CL-F due **2026-10-08 09:00**, CL-I due **2026-10-10 09:00**, CL-FIN due the end of the L3 investigation due date (10-03 + 14 = **2026-10-17 23:59:59**); GOSI-W unchanged (already met).

**FU2 — airside aircraft contact** (seed, ANIA-EXP). INC-ANIA-EXP-2026-0161: **2026-10-04 23:30**, Z-APR-21, GULFPAVE escort vehicle contacts a parked aircraft's wingtip, airside_flags [aircraft_involved], property_damage, potential 4 (HiPo). Requirements and status at the clock (2026-10-06 10:00):

| Rule | due_at | Submission | Status |
|---|---|---|---|
| AO-V | 10-05 00:30 | 10-04 23:42 phone_radio, AOCC duty manager, AOCC-TEST-1004 | submitted, on time |
| AO-W | 10-05 23:30 | 10-05 16:10 email, AO-OCR pack NP-ANIA-EXP-2026-0058 | acknowledged 10-05 18:05 |
| CL-V | 10-05 00:30 | 10-05 00:05 phone_radio, PMC duty engineer | submitted, on time |
| CL-F | 10-05 23:30 | 10-05 11:00 email to client + PMC | submitted, on time |
| GACA-W | 10-07 23:30 | — | due |
| CL-I | 10-07 23:30 | — | due |
| CL-FIN | 10-18 23:59:59 | — | due |

K-127 ANIA-EXP October as_of 10-06 = 4 ÷ 4 = **100.0 %** (three not yet due are excluded); K-128 = **0**.

**FU3 — fatality** (fixture; RBT-52, occurred 2026-10-10 08:00, QIMMA steel erector, FAT). POL-V **09:00**, MHRSD-F **2026-10-11 08:00**, GOSI-W **2026-10-13 08:00**, CL-V 09:00, CL-F 10-11 08:00, CL-I 10-13 08:00, CL-FIN 2026-10-24 23:59:59. MHRSD-LTR and GOSI-WIR carry identity; CLIENT-FLASH shows "Person 1 · steel_erector · QIMMA" with `client_pack_identity` none.

**FU4 — monthly timeliness** (fixture; October, as_of 2026-10-31). 21 requirements with due_at in October: 17 submitted on time, 2 late, 1 overdue (GOSI-W), 1 waived `reported_by_other_party` → K-127 = 17 ÷ 20 × 100 = **85.0 %**; K-128 = **1** (statutory 1). E24 raised (statutory overdue; and 85.0 < 95.0 with 20 items).

**FU5 — acknowledgement** (seed). LL-2026-007 published **2026-09-24 10:00** to ANIA-EXP and RBT-52; items ANIA-EXP RAWABI, NAJD, GULFPAVE, SAHARA and RBT-52 QIMMA (DLIFT had no headcount in the 14 days), ack_due_on **2026-10-01**. Acknowledged: NAJD 09-24, RAWABI 09-25, GULFPAVE 09-29, QIMMA 09-30; SAHARA pending. Reminder 09-29 to the reps of SAHARA (Ahmed via the RAWABI tree); overdue alert 10-02 to Ahmed and Noura. K-130 October as_of 10-06 = 4 ÷ 5 × 100 = **80.0 %** (ANIA-EXP alone 3 ÷ 4 = **75.0 %**; RBT-52 1 ÷ 1 = **100.0 %**).

**FU6 — publication timeliness** (seed). INC-ANIA-EXP-2026-0147 investigation (L3) approved 2026-09-21 → LL-2026-007 publish_due_on **2026-10-05**, published 09-24 → on time. INC-ANIA-EXP-2026-0150 (L3) approved 2026-09-28 → LL-2026-008 due **2026-10-12**, In Review at the clock, reminder on **10-09**. K-129 ANIA-EXP October as_of 10-06 = 1 ÷ 1 = **100.0 %** (LL-2026-008 not counted until 10-12 or publication).

**FU7 — effectiveness** (seed). LL-2026-003 (from INC-ANIA-EXP-2026-0093: paving_asphalt, caught_in_between), published 2026-06-10, check due **2026-09-08**. Recurrence 06-10…09-08 on ANIA-EXP: none; acks 4 / 4; source CAs 2 / 2 Closed → suggested **effective**; Noura completes 09-08 → K-131 September = 1 ÷ 1 = **100.0 %**. Variant: a 2026-08-20 GULFPAVE incident, paving_asphalt, caught_in_between, potential 4 → suggested **not_effective**; completing without follow-up → `FOLLOW_UP_REQUIRED`.

## 7. Alerts & expiries

Channels as Phases 1–6e (in-app and email in the recipient's language; push on the phone web app; no SMS, DECISIONS #124). Each (subject, step) is sent once.

| Trigger | Recipient | Timing | Channel |
|---|---|---|---|
| Requirement created (verbal stage) | HSE Officers; HSE Manager; Contractor HSE Rep of the responsible tree | Within 60 s | In-app + push + email |
| Requirement created (other stages) | HSE Officers; filer's Contractor HSE Rep (GOSI) | Within 60 s | In-app + email |
| Pre-due (§6.1) | same | as §6.1 | In-app + push + email |
| Overdue | same + HSE Manager | At due_at; then daily 07:10 | In-app + push + email |
| Pack awaiting approval > 4 h | 217 holders in scope | Once | In-app |
| Lesson publish due / overdue (LL-1) | author; HSE Officers; HSE Manager | publish_due_on − 3; day after | In-app + email |
| Lesson published (DS-2) | reps of items; HSE Officers and site engineers of the projects | At publication | In-app + email (reps) |
| Ack due / overdue (DS-4) | reps of pending items; HSE Officers at overdue | due − 2; day after; weekly | In-app + email |
| Effectiveness check due (EF-1) | HSE Officers of the source project | due_on; weekly | In-app + email |
| E24 | HSE Manager; HSE Officers; tier-1 Contractor HSE Rep for its tree | Monthly job, day 2, 07:00 | In-app + email |

Alert texts carry incident refs, bodies, stages and lesson numbers; never injured names (P6).

## 8. Reports / KPIs fed

### 8.1 Dashboard additions (Phase 1 §8.1)
1. **Tiles:** K-127 notifications on time (chip K-128 overdue, statutory first) · K-130 lesson acknowledgement (chips K-129, K-131).
2. **Follow-up band** (live): verbal stages due in the next hour; requirements overdue (statutory first); packs awaiting approval; lessons due for publication ≤ 3 days.
3. **Charts:** C37 notifications by body by month (on time / late / overdue, stacked); C38 lessons funnel by quarter (required → published → acknowledged → effective).

### 8.2 Expiring items and action panel
- `ExpiringItemKind`: `notification_stage_due` (replaces the Phase 1 item for incidents under the profile), `lesson_publish_due`, `lesson_ack_due`, `lesson_effectiveness_due`.
- Action panel: overdue requirements; packs awaiting approval; lessons past publish_due_on; acknowledgements overdue; effectiveness checks overdue; template change requests open > 30 days.

### 8.3 Registers and prints
Notification register (incident, body, stage, due, status, submission ref; filters by body, stage, status, contractor), pack register (identity packs listed without content for non-29 holders), lesson library (search, filters, PDF bulletin EN + AR one page each), distribution status per lesson, effectiveness register. Exports (215 / 222) write an `export` audit row.

### 8.4 Feeds to other phases
- **Phase 1:** requirement status and notified fields (SB-4), CAs (`lesson`), K-127…K-131, E24, T23–T24, AI-19 section, similar lessons on the incident page.
- **6d:** topic linked_refs, campaigns with reason `lesson`, template change requests, TBT-9 suggestions. **6g:** K-127 and K-130 per contractor.

## 9. Acceptance criteria

Fixtures: the Appendix A seed with the Phase 0–6e seeds; clock `HSE_CLOCK_AT` = **2026-10-06 10:00** unless stated. Users as 6e §9 (Faisal HSE Manager; Noura HSE Officer ANIA-EXP; Lina HSE Officer RBT-52; Omar site engineer S-AIR; Fahad site engineer S-LAND; Ahmed Contractor HSE Rep RAWABI tree; Yousef Contractor HSE Rep QIMMA; Sarah viewer; Dr. Huda OH Practitioner).

**Rules and requirements**
1. **Given** RBT-52 with `followup_rules_from` null **Then** a new LTI there gets exactly the Phase 1 I-20 items and due times (stage written); ANIA-EXP September incidents keep their Phase 1 items.
2. **Given** FU1 **Then** GOSI-W is due 2026-10-06 14:20 with filer NAJD, Ahmed and Noura are alerted at creation, and no client requirement exists while P1 is MTC; **Given** no submission by 10-05 14:20 **Then** the pre-due alert is sent then, and none is sent once a submission exists.
3. **Given** FU1 reclassified to LTI at 10-07 09:00 **Then** CL-V, CL-F, CL-I and CL-FIN are due 10:00, 10-08 09:00, 10-10 09:00 and 10-17 23:59:59; a report entered late does not move any due time.
4. **Given** FU3 **Then** the seven requirements and due times are as listed, and POL-V and CL-V alerts reach Lina and Faisal within 60 s with push.
5. **Given** an incident with two contractor_worker LTI cases of different employers **Then** two GOSI-W requirements exist, one per filer engagement.
6. **Given** Faisal raises GOSI-W to 96 h or deactivates POL-V **Then** 422 `RULE_LOOSENING`; lowers GOSI-W to 48 h **Then** saved, audited, and only requirements created afterwards use 48 h.
7. **Given** Faisal edits CL-F to 12 h **Then** saved; activating a client row on a project without client_recipients **Then** 422 `CLIENT_RECIPIENT_REQUIRED`; Noura editing any rule **Then** 403 (218).
8. **Given** a case downgraded LTI → MTC before the client flash is sent **Then** CL-V/CL-F/CL-I/CL-FIN become `not_required` (`incident_reclassified`); had CL-F been submitted, it stays submitted with "trigger no longer applies".
9. **Given** Faisal waives GACA-W with `reported_by_other_party` without the operator's reference or file **Then** 422 `WAIVER_EVIDENCE_REQUIRED`; with both **Then** waived and excluded from K-127.
10. **Given** 6e EV7 (d) on 2026-10-06 **Then** NCEC-W is due 24 h after occurrence, as 6e AC41.

**Packs**
11. **Given** Ahmed generates GOSI-WIR for FU1 **Then** the pack holds the worker's name, Iqama, body part, nature and treating facility, a `sensitive_field_read` and an `export` audit row (purpose gosi) are written, and the letter shows the Gregorian and Hijri dates.
12. **Given** Fahad (no capability 29) generates GOSI-WIR **Then** 403; he can see the requirement status (215).
13. **Given** the CLIENT-FLASH pack for FU3 **Then** the case appears as "Person 1 · steel_erector · QIMMA", without name, ID or nationality, in EN and AR columns; with `client_pack_identity` `name_and_trade` and a contract-clause text **Then** the name appears and the setting change is audited.
14. **Given** a client pack narrative containing the injured person's name (AR or EN spelling of a token) **Then** 422 `IDENTITY_IN_TEXT`; a 10-digit number starting with 2 **Then** the P1-8 warning.
15. **Given** a CLIENT-FINAL pack before the investigation is approved **Then** 422 `INVESTIGATION_NOT_APPROVED`; after approval **Then** it lists root-cause codes, CAs with control levels and LL-2026-007 when published.
16. **Given** an approved pack and a later edit of the incident description **Then** the pack shows "incident changed since generation"; regenerating creates version 2 and supersedes version 1; editing a Submitted pack **Then** 409 `PACK_IMMUTABLE`.
17. **Given** Ahmed approving an AO-OCR pack **Then** 403 (PK-6); approving a GOSI pack for NAJD **Then** allowed; Yousef approving a NAJD GOSI pack **Then** 404 (not in scope).

**Submissions**
18. **Given** FU2 **Then** the seven requirement statuses at the clock are as tabled, K-127 ANIA-EXP October = 100.0 % and K-128 = 0.
19. **Given** a written submission without an approved pack or external document **Then** 422 `PACK_NOT_APPROVED`; channel `phone_radio` on a written stage **Then** 422 `CHANNEL_NOT_ALLOWED`; `hand_delivered` without a stamped copy **Then** 422 `EVIDENCE_REQUIRED`.
20. **Given** submitted_at before occurred_at or 10 min in the future **Then** 422 `SUBMITTED_AT_INVALID`.
21. **Given** the FU1 GOSI submission **Then** the Phase 1 incident shows gosi notified_at 2026-10-05 11:00 and reference GOSI-TEST-0412; using the Phase 1 notification endpoint without an evidence file on an incident under the profile **Then** 422 `EVIDENCE_REQUIRED`.
22. **Given** a submission recorded 25 h ago **Then** editing → 409 `SUBMISSION_LOCKED`; Noura voids it with a reason **Then** the requirement returns to due or overdue by its due_at.
23. **Given** GACA-W with filer `airport_operator` **Then** a submission carrying the operator's reference and confirmation meets it.
24. **Given** FU2 GACA-W unsubmitted at 10-07 23:30 **Then** it becomes overdue, Faisal is alerted, and daily alerts follow at 07:10.

**Lessons**
25. **Given** INC-ANIA-EXP-2026-0150's L3 investigation approved 09-28 **Then** a Draft lesson exists with publish_due_on 10-12, prefilled root-cause codes and lessons_learned text, and the reminder is sent 10-09.
26. **Given** an L2 investigation approval with default settings **Then** no lesson Draft; after Faisal adds L2 to `lesson_required_levels` **Then** one is created for the next approval.
27. **Given** a draft without the AR key lessons or with an unconfirmed photo **Then** submit → 422 `LESSON_INCOMPLETE` / `REDACTION_NOT_CONFIRMED`; a what_happened text containing the injured worker's name **Then** 422 `IDENTITY_IN_TEXT`.
28. **Given** Noura submits LL-2026-008 and Faisal publishes it with no project **Then** 422 `NOT_DISTRIBUTED`; Faisal publishing a lesson he authored **Then** 422 `SELF_APPROVAL`; Noura publishing **Then** 403 (220).
29. **Given** FU6 **Then** K-129 ANIA-EXP October as_of 10-06 = 100.0 %, and LL-2026-008 enters the denominator on 10-12 or at publication.
30. **Given** FU5 publication **Then** five items exist (no DLIFT item), HSE Officers and site engineers of both projects get the notice, and reps get the EN + AR bulletin.
31. **Given** FU5 **Then** reminders on 09-29, the SAHARA overdue alert on 10-02 to Ahmed and Noura, and K-130 October = 80.0 % (ANIA-EXP 75.0 %, RBT-52 100.0 %).
32. **Given** Ahmed acknowledges SAHARA's item **Then** allowed (tier-1 tree); Noura acknowledging for SAHARA **Then** 422 `ON_BEHALF_NOTE_REQUIRED` while Ahmed is active; `not_applicable` without a reason **Then** 422.
33. **Given** a library search for "سقاله" or "scaffold platform edge" **Then** LL-2026-007 is returned; Sarah and Dr. Huda can search; drafts are not returned to them.
34. **Given** a new incident Reported with activity scaffolding and mechanism fall_from_height **Then** its page lists LL-2026-007 among similar lessons.

**6d links and effectiveness**
35. **Given** Noura opens a topic draft from LL-2026-008 **Then** a 6d Draft topic exists with the key lessons and linked_refs lesson LL-2026-008; publishing it still needs Faisal (6d 193).
36. **Given** a 6d campaign with reason `lesson` and ref LL-2026-008 while In Review **Then** 422 `LESSON_NOT_PUBLISHED`; with LL-2026-007 **Then** issued.
37. **Given** the open change request on SCA from LL-2026-007 **Then** it shows in the 6d library; publishing SCA v2 with change note "LL-2026-007 toe-boards" marks it adopted with v2.
38. **Given** FU7 **Then** suggested effective, completed by Noura, K-131 September = 100.0 %; the variant suggests not_effective and completing without a CA or new lesson → 422 `FOLLOW_UP_REQUIRED`; with a CA **Then** the CA has source_type `lesson`.
39. **Given** a check completed as `partly_effective` where the suggestion was `effective` without rationale **Then** 422 `RATIONALE_REQUIRED`.
40. **Given** NAJD's TBT suggestions on S-LAND after LL-2026-007 linked to TT-014 **Then** TT-014 is suggested right after open-campaign topics (LK-4).

**KPIs, warnings, AI, PDPL, settings**
41. **Given** FU4 **Then** K-127 = 85.0 %, K-128 = 1, and E24 is raised for the project and the responsible tier-1 tree with T13 inputs and no names.
42. **Given** Ahmed with the RAWABI tree filter **Then** K-127…K-130 cover RAWABI-tree items only (GOSI by filer engagement).
43. **Given** the AI is asked "have we had lessons on scaffold edges?" **Then** T24 returns LL-2026-007 with its lesson no.; "what was the name of the injured worker in the GOSI report?" **Then** no identity is returned and the assistant says it is not available to it.
44. **Given** Sarah **Then** she sees requirement statuses and the library, not packs or evidence files; an identity pack download by Noura uses a signed URL ≤ 5 min and is excluded from bulk exports.
45. **Given** identity anonymisation of FU1's case (P1-5) **Then** the GOSI pack file and identity snapshot fields are deleted while pack_no, dates and GOSI-TEST-0412 remain.
46. **Given** Faisal sets `lesson_ack_days` 10 or `followup_warning_pct` 90 **Then** 422 `SETTING_LOOSENING`; 5 days **Then** saved and audited; Noura editing a 6f setting **Then** 403.
47. **Given** the seed **Then** Phase 1 September K-16, rates and notification items are unchanged (INC-ANIA-EXP-2026-0161 counts in October only), and the incident register's notification column for INC-ANIA-EXP-2026-0161 matches FU2.
48. **Given** the UI in Arabic **Then** every 6f label, status, list value, alert, pack, bulletin and error has its AR text; numbers, references and codes stay left-to-right inside the RTL layout.

## 10. Open questions for the HSE Manager

Each has a default so the build can start.
1. **GOSI:** 3 days from the injury, filed by the injured worker's employer on the GOSI portal. Is it 3 calendar or working days on your projects, and does the main contractor file for subcontractor workers?
2. **MHRSD:** fatality within 24 h and permanent disability within 3 days (ASSUMPTION). How does your labour office want them (Qiwa, letter, email)?
3. **GACA / airport operator:** do you file occurrence reports to GACA yourselves, or does the airport operator file (NR-10)? What are the operator's verbal and written deadlines?
4. **Client / PMC:** verbal 1 h, flash 24 h, interim 72 h, final with the investigation (14 days for L3). What does each contract say, and do client and PMC need separate reports?
5. **Client identity:** client reports are de-identified by default. Does any contract require the injured person's name?
6. **Lessons:** required for L3 investigations, published within 14 days, acknowledged within 7 days, checked after 90 days. Should L2 lessons also be required?
7. **Client forms:** should the platform fill the client's own flash-report template (field mapping), or is the platform's bilingual layout acceptable?

## 11. Changes required in earlier specs (applied 2026-10-09: 0-foundation v1.4, 1-dashboard v1.9, 6d-field-assurance v1.2, 6e-environmental v1.1)

### 11.1 `0-foundation.md` v1.2 (v1.3 after 6e) → next
1. Matrix rows 215–223 (§5.10).
2. Contractor: optional `gosi_establishment_no` رقم المنشأة في التأمينات string(20), personal: none, used by GOSI-WIR.

### 11.2 `1-dashboard.md` v1.8 (after 6e) → v1.9
1. §3.3 `notifications`: each item gains stage, rule_code, trigger_met_at, due_at (stored), status (§4.1 of 6f) and waiver fields; notified_at / reference_no / notified_by become read fields filled by the first valid 6f submission (SB-4). Incidents before `followup_rules_from` keep the I-20 behaviour as stage `written`.
2. §5.2 I-20: "from the project's `followup_rules_from`, required notifications, stages and deadlines come from the 6f rule profile (6f §3.1, NR-1…NR-10)". I-21: "the platform does not e-file; 6f generates packs and records evidence".
3. §3.8 CA `source_type` adds `lesson` (source_id = 6f effectiveness check).
4. §3.5 investigation read model shows the lesson no. and status; §7 the "external notification due" row is replaced by 6f §7 for incidents under the profile; the incident page shows similar lessons (LL-6).
5. §5.9 AI: T23, T24; T5 adds the published lesson no.; T13 returns E24; AI-19 section "Incident follow-up".
6. §6.9 / §7: E24, same monthly job and recipients; K-127…K-131 by reference.
7. §8.1: tiles, follow-up band, charts C37–C38; `ExpiringItemKind` and action-panel items of 6f §8.2.

### 11.3 `6d-field-assurance.md` v1.0 (v1.1 after 6e) → next
1. §3.10 linked_refs kind `lesson` validated against Published lessons; CMP-1 reason `lesson` requires a Published lesson (LK-2).
2. §3.1 library shows open 6f template change requests; publishing a version whose change_note names the lesson no. adopts them (LK-3).
3. TBT-9 gains step (1b): topics linked to lessons published to the project in the last 30 days (LK-4).

### 11.4 `6e-environmental.md` v1.0
No rule changes; `ncec` and `airport_operator` environmental triggers become the 6f rows NCEC-W and AO-W (`env_airside`) under the same `env_notifications_from` date.

### 11.5 Phases 2–5, 6a–6c
No changes.

## Appendix A — Seed data (fictional; `seed_fake = true`; references contain `TEST`)

### A.1 Principles
- Builds on the Phase 0–6e seeds. Clock `HSE_CLOCK_AT` = 2026-10-06T10:00:00+03:00.
- Settings: ANIA-EXP `followup_rules_from` = **2026-10-01**; RBT-52 null. Other 6f settings at §3.10 defaults.
- The generator never changes Phase 1–6e values for September: September incidents keep Phase 1 I-20 items; packs and submissions are added only where the Phase 1 seed recorded notified_at (same time and reference). If the Phase 1 generator's refs differ, the seed maps by date and contractor and the backend records it in DECISIONS.

### A.2 Profiles
- Statutory rows per §3.11 on both projects. Client rows CL-V / CL-F / CL-I / CL-FIN on both; client_recipients ANIA-EXP: "Airport Development Client (test)" (client) and "Gulf PMC Consultants (test)" (pmc); RBT-52: "Riyadh Tower Developer (test)". GACA-W filer on ANIA-EXP: main_contractor.
- Body directory: GOSI Riyadh branch, MHRSD Riyadh labour office, Civil Defense Riyadh, AOCC ANIA (test), GACA (test portal), NCEC (test portal).

### A.3 Notifications
- **INC-ANIA-EXP-2026-0161** (FU2): generated by the seed as an October incident (property_damage, L3 due 10-18, GULFPAVE) with the FU2 packs and submissions; Phase 1 September values unchanged.
- INC-ANIA-EXP-2026-0147: GOSI pack NP-ANIA-EXP-2026-0049 (identity_medical) Submitted with the Phase 1 reference GOSI-TEST-0001; client flash pack de-identified, submitted.

### A.4 Lessons
- Library: 9 Published lessons LL-2025-004…LL-2026-007 across both projects (EN/AR), incl. **LL-2026-003** (FU7, check completed effective 09-08) and **LL-2026-007** (FU5 / FU6: "Unprotected platform edge during scaffold alteration", from INC-ANIA-EXP-2026-0147, root causes AD-01, OF-04, TE-08, linked to 6d TT-014 and CMP-ANIA-EXP-2026-004, change request on SCA "toe-boards on every working platform" open, check due 2026-12-23).
- **LL-2026-008**: In Review (FU6), from INC-ANIA-EXP-2026-0150 (sling failure), author Noura.
- One Archived lesson (LL-2025-004, superseded by LL-2026-002) to show the Archived label.

## Change log

| Version | Date | Author | Change |
|---|---|---|---|
| v1.0 | 2026-10-09 | HSE Consultant Agent | First issue. §1–§11 and Appendix A: per-project notification rule profile (statutory tighten-only, client / PMC rows) with stages and trigger-based deadlines replacing the fixed I-20 deadlines from a switch date; requirements with clock-start and reclassification rules, waivers; bilingual pre-filled packs (GOSI, MHRSD, Civil Defense, GACA, airport operator, NCEC, client flash / interim / final) with PDPL field sets and approval; submission evidence and acknowledgements; lessons learned from investigations with de-identification, review, cross-project distribution and acknowledgement, 6d topic / campaign / template-change links, searchable bilingual library, similar-lesson prompts and 90-day effectiveness checks. Capabilities 215–223, KPIs K-127…K-131, warning E24, AI tools T23–T24, charts C37–C38, CA source `lesson`. 48 acceptance criteria. Earlier-spec changes in §11, not yet applied. |
