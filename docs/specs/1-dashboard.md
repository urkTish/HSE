# Module Spec — Phase 1: Dashboard & Core Data (with AI)

**Version:** v1.7 · **Date:** 2026-10-09 · **Author:** HSE Consultant Agent · **Status:** Draft for HSE Manager review
**Builds on:** `0-foundation.md` v1.0 — reuses its entities (Project, Site, Zone, Contractor, Project engagement, User, Role assignment, Audit log), role codes (§3.8), settings (§3.9, incl. `ltifr_base_hours` default 1,000,000 and `rate_base_hours` default 200,000), calculation K1, roll-up rule (§8.3) and PDPL baseline P1–P13.
**Covers (in build order):** 1.1 Workforce & man-hours (entry + CSV/Excel import) · 1.2 Incident register · 1.3 Observations · 1.4 Inspections · 1.5 Corrective actions · 1.6 KPI engine · 1.7 Dashboard · 1.8 AI assistant.
**Out of scope:** training records/matrix (Phase 5), inspection checklists, toolbox-talk module, WBGT heat-stress module, GOSI e-filing (Phase 6). Placeholders are named where the dashboard will later consume them.

Conventions: `VERIFY` = clause/number/deadline to be confirmed against current official text. `ASSUMPTION` = Consultant default; HSE Manager may override (§10). "Must" = enforced server-side. All KPI numbers shown anywhere are computed by the backend KPI engine (§6); the frontend and the AI never compute KPIs.

---

## 1. Purpose

The HSE Manager needs one trustworthy set of safety numbers per project, site, zone and contractor — man-hours, injuries classified to OSHA recordability logic, near misses, observations, inspections and corrective actions — calculated the same way every time, comparable month-on-month, year-on-year and on a rolling 12-month basis, and explainable on demand. Phase 1 captures the core data with validation strong enough to stand up to client audit, computes every lagging and leading indicator with exact, configurable formulas, presents them on a bilingual dashboard with an action panel, and adds an AI assistant that answers questions and drafts the monthly report strictly from platform data, citing its numbers, without exposing injured persons' identities.

## 2. Regulatory basis

| # | Source | What it drives here |
|---|---|---|
| R1 | **OSHA 29 CFR 1904** — 1904.4 (recording criteria), 1904.5 (work-relatedness), 1904.7 (general recording criteria; (b)(3) day counting, calendar days, 180-day cap; (b)(5) medical treatment vs first-aid list), 1904.29 (Forms 300/300A/301), 1904.29(b)(6)–(9) privacy-concern cases | Injury case categories, FAC/MTC derivation, lost-day counting, privacy cases. Used as international benchmark (Phase 0 R8). |
| R2 | OSHA rate formulas (200,000 h base = 100 FTE × 40 h × 50 weeks) — TRIR, DART | §6 formulas |
| R3 | **MHRSD** Labour Law (Royal Decree M/51) — work-injury obligations, working hours (8 h/day, 48 h/week; Ramadan 6 h/day for Muslim workers), overtime `VERIFY` article numbers | Plausibility checks on hours/person; Ramadan seed pattern |
| R4 | MHRSD **midday outdoor work ban** 12:00–15:00, 15 Jun–15 Sep `VERIFY` annual ministerial decision | Heat-season analysis dimension, seed pattern |
| R5 | **GOSI** Occupational Hazards Branch — employer notification of work injury (deadline commonly cited as 3 days `VERIFY`); GOSI covers commuting accidents `VERIFY` | Notification tracking fields, commuting flag |
| R6 | **MHRSD/NCOSH** serious-injury and fatality notification requirements `VERIFY` deadline and channel | Notification tracking, alert timing |
| R7 | **Saudi Civil Defense** — fire incidents notification `VERIFY` | Notification flag |
| R8 | **GACA** occurrence reporting (GACAR Part 139 / safety occurrence reporting) and airport operator occurrence procedures — runway incursions, FOD, aircraft/GSE damage, works-related airside events `VERIFY` part and timing | Airside incident flags and notification tracking |
| R9 | **ISO 45001:2018** cl. 9.1 (monitoring, measurement, analysis), 9.1.2, 10.2 (incident, nonconformity and corrective action), 5.4 (worker participation — reporting) | Observations, investigation, CA workflow and effectiveness verification |
| R10 | **NEBOSH** 5×5 risk matrix; active vs reactive monitoring | Severity scale, leading/lagging split |
| R11 | **ICAM** (Incident Cause Analysis Method) four-level model: Absent/Failed Defences, Individual/Team Actions, Task/Environmental Conditions, Organisational Factors `VERIFY` taxonomy codes against the licence version the client uses | Root-cause categories |
| R12 | **ILO Code of Practice — Recording and notification of occupational accidents and diseases** (1996) | Data elements, classification by nature/body part/agency |
| R13 | ANSI Z16.1 (withdrawn) — 6,000-day charge for fatality / permanent total disability `VERIFY` if client still uses it | Optional setting `fatality_lost_days_charge` |
| R14 | **PDPL** + Implementing Regulations (Phase 0 R1, R2) — health data is sensitive; cross-border transfer rules | Injured-person data handling; AI data flow (§5.8, rule AI-14) |
| R15 | Client / airport operator HSE requirements (e.g. monthly statistics report format, KPI bases) | Strictest-wins: client definitions entered as settings; never loosen R1 recordability |

Strictest-wins applied: OSHA does not count commuting injuries; GOSI does. The platform records commuting cases and tracks GOSI notification (stricter for notification), but excludes them from rates by default to keep OSHA comparability (setting, §3.10).

## 3. Entities & fields

PDPL column: **none / personal / sensitive** (Phase 0 P1–P2). AR label shown in UI. Every entity also carries Phase 0 system fields (id UUID, created_at/by, updated_at/by) and is audited (Phase 0 rule 35).

### 3.1 Workforce daily return — بيان القوى العاملة اليومي

One row per **work_date × site × zone (optional) × engagement × shift**. Man-hours = Σ (headcount × hours) is entered as the row total.

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| project_id | المشروع | FK | Y | project Active or On Hold | ANIA-EXP | none |
| site_id | الموقع | FK | Y | belongs to project; site in engagement.site_ids | S-AIR | none |
| zone_id | المنطقة | FK | N | belongs to site; not Archived | Z-APR-21 | none |
| engagement_id | المقاول | FK | Y | engagement on project; work_date within mobilisation–demobilisation | GULFPAVE@ANIA-EXP | none |
| work_date | تاريخ العمل | date (local) | Y | ≤ today (project tz); ≥ project.start_date | 2026-09-14 | none |
| shift | الوردية | enum | Y | `day` نهارية, `night` ليلية, `all` كامل اليوم | night | none |
| no_work | لا يوجد عمل | bool | Y | default false; if true headcount = 0 and man_hours = 0 | false | none |
| headcount | عدد العاملين | int | Y | 0–20,000 | 600 | none |
| man_hours | ساعات العمل | decimal(10,2) | Y | ≥ 0; ≤ headcount × 16 (`max_hours_per_person_day`); headcount = 0 ⇒ man_hours = 0 | 6,000.00 | none |
| toolbox_talks | اجتماعات التوعية (Toolbox) | int | N | ≥ 0, default 0 | 4 | none |
| toolbox_attendees | حضور اجتماعات التوعية | int | N | ≥ 0; ≤ headcount × 2 | 560 | none |
| inductions | عدد التعريفات بالسلامة | int | N | ≥ 0 | 12 | none |
| training_hours | ساعات التدريب | decimal(8,2) | N | ≥ 0; ≤ man_hours | 48.00 | none |
| remarks | ملاحظات | text(500) | N | P3 hint "Do not enter names, ID or medical details" | Night paving TWB | none |
| source | المصدر | enum | Y | `manual`, `import` (system) | import | none |
| import_batch_id | دفعة الاستيراد | FK | cond. | set iff source = import | — | none |
| status | الحالة | enum | Y | §4.1 | submitted | none |

Derived (not stored): **tier class** = `direct` (مباشر) if engagement.tier = 1, `subcontractor` (مقاول باطن) if tier ≥ 2 ASSUMPTION (§10 Q1).

### 3.2 Workforce import batch — دفعة استيراد القوى العاملة

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| file_name, file_sha256, file_size | الملف | string / string / int | Y | `.csv` (UTF-8, with or without BOM; comma or semicolon) or `.xlsx` (first sheet); ≤ 5 MB; ≤ 20,000 data rows | sep-returns.xlsx | none |
| mode | نمط الاستيراد | enum | Y | `insert_only` (إضافة فقط), `upsert` (إضافة أو استبدال) | insert_only | none |
| status | الحالة | enum | Y | `validated` (dry-run done), `committed`, `discarded`, `expired` (dry-run older than 60 min) | committed | none |
| counts | الإحصاءات | JSON | Y | rows_total, rows_ok, rows_warning, rows_error, rows_inserted, rows_replaced | — | none |
| report | تقرير التحقق | JSON | Y | per row: row_no, status, codes[], message_en, message_ar | — | none |
| uploaded_by, project_id | — | FK | Y | — | — | personal (user ref) |

**Import template columns** (header row in EN or AR; order free; case-insensitive):

| Column | AR header | Maps to | Format |
|---|---|---|---|
| work_date | تاريخ_العمل | work_date | `YYYY-MM-DD` or Excel date cell; `DD/MM/YYYY` accepted |
| project_code | رمز_المشروع | project | code |
| site_code | رمز_الموقع | site | code |
| zone_code | رمز_المنطقة | zone | code or blank |
| contractor_code | رمز_المقاول | engagement (via contractor short_code + project) | short_code |
| shift | الوردية | shift | `day/night/all` or `نهارية/ليلية/كامل` |
| headcount | عدد_العاملين | headcount | integer |
| man_hours | ساعات_العمل | man_hours | number, `.` decimal; thousands separators rejected |
| no_work | لا_يوجد_عمل | no_work | `Y/N`, `1/0`, `نعم/لا`; blank = N |
| toolbox_talks, toolbox_attendees, inductions, training_hours | … | same | numbers, blank = 0 |
| remarks | ملاحظات | remarks | text |

**Import validation codes** (errors block commit; warnings do not):

| Code | Level | Condition |
|---|---|---|
| E01 | error | project_code unknown or not the batch project |
| E02 | error | site_code not in project |
| E03 | error | zone_code not in site, or zone Archived |
| E04 | error | contractor_code not engaged on project, or site not in engagement.site_ids |
| E05 | error | work_date outside engagement mobilisation–demobilisation |
| E06 | error | work_date in the future (project tz) or before project.start_date |
| E07 | error | headcount not an integer 0–20,000 |
| E08 | error | man_hours < 0, non-numeric, or > headcount × `max_hours_per_person_day` |
| E09 | error | duplicate key (date, site, zone, contractor, shift) within the file |
| E10 | error | key already exists in DB and mode = insert_only |
| E11 | error | key exists in a Locked period (any mode) |
| E12 | error | row outside the uploader's scope (site/contractor) |
| E13 | error | headcount = 0 and man_hours > 0, or no_work = Y with headcount/man_hours > 0 |
| E14 | error | unparseable date or number; missing required column (whole file rejected) |
| W01 | warning | man_hours ÷ headcount > `warn_hours_per_person_day` (default 12) |
| W02 | warning | headcount differs > 50 % from the same engagement/site 7-day average |
| W03 | warning | contractor status Suspended (hours still accepted — work may have occurred) |
| W04 | warning | work_date older than 30 days |
| W05 | warning | same file_sha256 already committed on this project |
| W06 | warning | shift `all` and a `day`/`night` row exist for same key date/site/zone/contractor (possible double count) |
| W07 | warning | v1.4: training_hours > 0 on a work_date ≥ `training_register_from` — "training hours from the training register are used for this date" (K-37; row still imported, `5-training.md` TH-6) |

### 3.3 Incident — حادثة

Reference format `INC-<project_code>-<YYYY>-<seq4>` (seq per project per year), e.g. `INC-ANIA-EXP-2026-0147`.

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| ref | الرقم المرجعي | string | sys | as above, immutable | INC-ANIA-EXP-2026-0147 | none |
| project_id, site_id, zone_id | المشروع، الموقع، المنطقة | FK | Y/Y/N | hierarchy consistent; zone not Archived | ANIA-EXP / S-LAND / Z-PIERB | none |
| location_detail | وصف الموقع | string(200) | N | — | Grid C-14, Level 2 deck | none |
| responsible_engagement_id | المقاول المسؤول | FK | Y | engagement on project | NAJD@ANIA-EXP | none |
| occurred_at | تاريخ ووقت الوقوع | timestamptz | Y | ≤ now; displayed in project tz | 2026-09-08 09:40 (+03) | none |
| reported_at | تاريخ الإبلاغ | timestamptz | sys | set on Draft → Reported | 2026-09-08 10:05 | none |
| reported_by | المُبلِّغ | FK user | sys | — | — | personal |
| shift | الوردية | enum | Y | `day`, `night` | day | none |
| incident_types | نوع الحادثة | enum[] | Y | ≥ 1 of `injury_illness` إصابة/مرض, `near_miss` حادث وشيك, `property_damage` أضرار ممتلكات, `environmental` حادث بيئي, `dangerous_occurrence` حدث خطير; `near_miss` cannot be combined with any other type | [injury_illness] | none |
| primary_type | النوع الرئيسي | enum | Y | one of incident_types | injury_illness | none |
| title | العنوان | string(150) | Y | P3 hint; no person names | Fall from scaffold working platform | none |
| description | الوصف | text(4000) | Y | P3 hint | … | personal (may contain) |
| immediate_actions | الإجراءات الفورية | text(2000) | Y | — | Area barricaded, scaffold tagged red | none |
| activity | النشاط | enum | Y | §3.11 list A | scaffolding | none |
| work_related | مرتبط بالعمل | bool | Y | default true | true | none |
| work_related_rationale | سبب عدم الارتباط بالعمل | text(500) | cond. | required if work_related = false (OSHA 1904.5 exception chosen from list: `off_duty_camp`, `personal_task`, `pre_existing_condition`, `commuting`, `voluntary_wellness`, `other`) | off_duty_camp | none |
| actual_severity | الشدة الفعلية | int 1–5 | Y | §3.11 list S | 3 | none |
| potential_severity | الشدة المحتملة | int 1–5 | Y | ≥ actual_severity | 4 | none |
| hipo | عالي الخطورة المحتملة | bool | derived | = potential_severity ≥ 4 | true | none |
| ambient_temp_c | درجة الحرارة | decimal(4,1) | N | 0–60 | 43.5 | none |
| airside_flags | مؤشرات الجانب الجوي | enum[] | N | only if zone_type = airside: `runway_incursion`, `fod_event`, `aircraft_involved`, `gse_damage`, `notam_breach`, `ols_infringement`, `wildlife`, `airside_vehicle_incident` | [fod_event] | none |
| pd_asset_type, pd_estimated_cost_sar | نوع الأصل، التكلفة التقديرية | enum / decimal(12,2) | if property_damage | asset: `plant`, `vehicle`, `structure`, `utility`, `airport_asset`, `aircraft`, `other`; cost ≥ 0 | vehicle / 18,000 | none |
| env_category, env_substance, env_quantity_l, env_contained, env_reached | الفئة البيئية … | enum / string / decimal / bool / enum | if environmental | category `spill`, `emission`, `dust`, `noise`, `waste`, `water`, `wildlife_habitat`; reached `none`, `soil`, `drain`, `water_body` | spill / diesel / 40 / true / soil | none |
| do_category | فئة الحدث الخطير | enum | if dangerous_occurrence | `crane_lifting_failure`, `scaffold_collapse`, `structural_collapse`, `excavation_collapse`, `electrical_short_fire`, `fire_explosion`, `gas_release`, `pressure_failure`, `vehicle_overturn`, `other` | crane_lifting_failure | none |
| notifications | الإخطارات الخارجية | list | N | per item: body `gosi`, `mhrsd`, `civil_defense`, `gaca`, `airport_operator`, `client`, `police`; required (derived §5.2 rule I-20), notified_at, reference_no, notified_by | gosi / 2026-09-09 / GOSI-TEST-0001 | none |
| status | الحالة | enum | Y | §4.2 | under_investigation | none |
| void_reason | سبب الإلغاء | text | cond. | required for Voided | duplicate of 0146 | none |
| attachments | المرفقات | file[] | N | images/PDF ≤ 20 MB each; P3 hint "no faces / no medical documents here" | — | personal |

### 3.4 Injury case (one per injured/ill person) — حالة إصابة

An `injury_illness` incident has ≥ 1 injury case. **KPIs count cases, not events.**

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| case_no | رقم الحالة | string | sys | `<incident ref>-P<n>` | INC-ANIA-EXP-2026-0147-P1 | none |
| person_type | فئة الشخص | enum | Y | `contractor_worker` عامل مقاول, `client_pmc_staff` موظف العميل/الاستشاري, `visitor` زائر, `third_party_public` طرف ثالث | contractor_worker | none |
| employer_engagement_id | جهة العمل | FK | cond. | required iff contractor_worker; engagement on project | NAJD@ANIA-EXP | none |
| person_name | اسم المصاب | string(120) | Y | — | (fake) Imran Hussain / عمران حسين | **sensitive** (linked to injury) |
| id_type, id_number | نوع ورقم الهوية | enum / string(10) | N | `iqama` (`^2\d{9}$`), `national_id` (`^1\d{9}$`), `passport` (`^[A-Z0-9]{6,9}$`); masked `2*******01` | iqama / 2000000017 | **sensitive** (P2) |
| employee_no | الرقم الوظيفي | string(20) | N | — | NJ-0457 | personal |
| nationality | الجنسية | ISO 3166 alpha-2 | N | analysis only (§5.8) | PK | personal |
| trade | المهنة | enum | Y | §3.11 list T | scaffolder | personal |
| age_band | الفئة العمرية | enum | N | `<20`, `20-29`, `30-39`, `40-49`, `50-59`, `60+` (no date of birth — minimisation) | 30-39 | personal |
| site_start_date | تاريخ بدء العمل بالموقع | date | N | ≤ incident date | 2026-08-25 | personal |
| days_on_site | أيام العمل بالموقع | int | derived | incident local date − site_start_date | 14 | personal |
| hours_into_shift | ساعات العمل قبل الحادثة | decimal(3,1) | N | 0–16 | 3.5 | personal |
| illness | مرض مهني | bool | Y | default false | false | sensitive |
| body_part, body_side | جزء الجسم، الجهة | enum / enum | Y / N | §3.11 list B; side `left`, `right`, `both`, `n/a` | wrist / right | sensitive |
| nature | طبيعة الإصابة | enum | Y | §3.11 list N | fracture | sensitive |
| mechanism | آلية الإصابة | enum | Y | §3.11 list M | fall_from_height | none (event attribute) |
| agency | المسبب | enum | Y | §3.11 list G | scaffold | none |
| treatments | العلاج المقدم | enum[] | Y | ≥ 1; §3.11 list F (first aid) + list MT (medical treatment) | [rigid_splint, x_ray_diagnosis] | sensitive |
| loss_of_consciousness | فقدان الوعي | bool | Y | — | false | sensitive |
| treated_at | مكان العلاج | enum | Y | `site_clinic`, `hospital_outpatient`, `hospital_admitted`, `none` | hospital_outpatient | sensitive |
| fatal, date_of_death | وفاة، تاريخ الوفاة | bool / date | Y / cond. | date ≥ incident date | false | sensitive |
| away_start_date | بداية الغياب | date | cond. | default incident date + 1; > incident date | 2026-09-09 | sensitive |
| rtw_date | تاريخ العودة للعمل | date | N | first day back on any duty (full or restricted); > away_start_date; null = still away | 2026-09-29 | sensitive |
| restricted_start, restricted_end | العمل المقيد من/إلى | date | N | end inclusive; start > incident date; no overlap with away period | 2026-09-16 / 2026-09-20 | sensitive |
| transfer_start, transfer_end | النقل لعمل آخر من/إلى | date | N | as restricted | — | sensitive |
| permanent_disability | عجز دائم | enum | Y | `none`, `partial`, `total` | none | sensitive |
| case_category | تصنيف الحالة | enum | derived + confirmable | §5.2 rules I-5…I-9: `FAT` وفاة, `LTI` إصابة مضيعة للوقت, `RWC` حالة عمل مقيد, `JTC` حالة نقل لعمل آخر, `MTC` حالة علاج طبي, `FAC` حالة إسعاف أولي | LTI | none (aggregate) |
| classification_status | حالة التصنيف | enum | Y | `provisional` مبدئي, `confirmed` مؤكد | confirmed | none |
| commuting | حادث أثناء التنقل | bool | Y | default false | false | none |
| privacy_case | حالة خصوصية | bool | Y | OSHA 1904.29(b)(7) list (sexual assault, mental illness, HIV/hepatitis/TB, needlestick with contaminated object, reproductive organs, other at employee request) | false | sensitive |
| days_away / restricted_days / transfer_days | أيام الغياب / المقيد / النقل | int | derived | §6.3 | 20 / 0 / 0 | sensitive (person-level) |
| medical_notes | ملاحظات طبية | text(2000) | N | — | — | **sensitive** |
| medical_attachments | مرفقات طبية | file[] | N | stored in separate encrypted bucket | — | **sensitive** |
| gosi_case_ref | مرجع GOSI | string(30) | N | — | GOSI-TEST-0001 | personal |
| worker_id | العامل (سجل العمال) | FK | N | v1.1: Phase 2 worker (`2-access-permits.md` §3.1) with a deployment on the incident's project; when set, pre-fills person_name, id_type/id_number, employee_no, trade and site_start_date (= deployment.mobilised_on), all still editable; no rule of this spec depends on it | WKR-000001 | personal |

### 3.5 Investigation — التحقيق (1 per incident when level ≥ 1)

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| level | مستوى التحقيق | enum | Y | `L1` بسيط, `L2` متوسط, `L3` شامل (ICAM) — derived minimum §5.2 rule I-14; may be raised, never lowered below minimum | L3 | none |
| lead_investigator_id | قائد التحقيق | FK user | Y | role hse_manager/hse_officer for L3; any of hse_officer/site_engineer/contractor_hse_rep for L1–L2 | — | personal |
| team_member_ids | فريق التحقيق | FK user[] | cond. | ≥ 2 members for L3, incl. ≥ 1 from responsible contractor | — | personal |
| due_date | تاريخ الاستحقاق | date | sys | occurred date + 3 (L1) / 7 (L2) / 14 (L3) calendar days ASSUMPTION; extension by HSE Manager with reason | 2026-09-22 | none |
| preliminary_report_at | التقرير المبدئي | timestamptz | cond. | required within 48 h for L3 ASSUMPTION | — | none |
| method | المنهجية | enum | Y | `simple` (L1), `five_why`, `icam`, `taproot` (if client licence) | icam | none |
| sequence_of_events | تسلسل الأحداث | text(4000) | Y at submit | — | … | personal (may contain) |
| immediate_causes | الأسباب المباشرة | text(2000) | Y at submit | — | … | none |
| root_causes | الأسباب الجذرية | list | Y at submit | ≥ 1 item for L2/L3; each = ICAM level + code (§3.11 list R) + text | OF-04 inadequate supervision | none |
| lessons_learned | الدروس المستفادة | text(2000) | Y for L3 | — | … | none |
| ptw_ids | تصاريح العمل المرتبطة | FK[] | N | v1.2: Phase 3 permits of the same project (`3-ptw.md` §3.5); the UI suggests permits that were Issued, Active or Suspended in the incident's zone at occurred_at | [PTW-ANIA-EXP-2026-0412] | none |
| ptw_involved, ptw_ref | تصريح عمل مرتبط | bool / string | N | ptw_involved: set true automatically when ptw_ids is non-empty (still settable manually otherwise); ptw_ref: legacy free text, read-only once ptw_ids is set (v1.2) | true / PTW-WAH-0912 | none |
| submitted_at, approved_by, approved_at | — | — | sys | approver ≠ lead investigator | — | personal |

### 3.6 Observation — ملاحظة سلامة

Ref `OBS-<project>-<YYYY>-<seq5>`.

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| project_id, site_id, zone_id | — | FK | Y/Y/N | hierarchy | ANIA-EXP / S-AIR / Z-TWB | none |
| observed_at | وقت الملاحظة | timestamptz | Y | ≤ now | 2026-09-14 23:10 | none |
| observer_id | المُلاحِظ | FK user | sys | current user | — | personal |
| anonymous | مجهول الهوية | bool | Y | default false; if true observer visible to hse_manager only | false | none |
| observed_engagement_id | المقاول المعني | FK | Y | engagement on project | GULFPAVE@ANIA-EXP | none |
| obs_type | نوع الملاحظة | enum | Y | `safe_behaviour` سلوك آمن, `safe_condition` وضع آمن, `unsafe_act` تصرف غير آمن, `unsafe_condition` وضع غير آمن | unsafe_condition | none |
| category | الفئة | enum | Y | §3.11 list O | fod_control | none |
| risk_rating | تقييم الخطورة | enum | cond. | required if unsafe: `low`, `medium`, `high` | high | none |
| description | الوصف | text(1000) | Y | P3 hint; no names of observed workers (minimisation) | Loose aggregate on TWB shoulder | none |
| photo | صورة | file[] | N | ≤ 3; hint "avoid faces" | — | personal (possible) |
| stop_work_applied | تطبيق إيقاف العمل | bool | Y | — | false | none |
| immediate_action | الإجراء الفوري | text(500) | cond. | required if unsafe | Swept, FOD walk repeated | none |
| closed_on_spot | أغلقت فوراً | bool | cond. | unsafe only | true | none |
| status | الحالة | enum | Y | §4.3 | closed | none |

### 3.7 Inspection plan & inspection — خطة التفتيش والتفتيش

**Inspection plan** (generates planned instances):

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| name_en / name_ar | اسم الخطة | string(150) | Y | — | Weekly scaffold inspection — Pier B / فحص السقالات الأسبوعي | none |
| inspection_type | نوع التفتيش | enum | Y | §3.11 list I | scaffold | none |
| site_id, zone_id, engagement_id | — | FK | Y/N/N | hierarchy | S-LAND / Z-PIERB / SAHARA | none |
| frequency | التكرار | enum | Y | `daily`, `weekly`, `fortnightly`, `monthly`, `once` | weekly | none |
| weekday | يوم الأسبوع | enum | cond. | weekly/fortnightly | sunday | none |
| start_date / end_date | من / إلى | date | Y/N | end ≥ start | 2026-01-04 / — | none |
| assignee_role / assignee_user_id | المكلَّف | enum / FK | Y | one of hse_officer, site_engineer, contractor_hse_rep | contractor_hse_rep | personal |
| active | فعّالة | bool | Y | — | true | none |

**Inspection** (instance or unplanned): ref `INS-<project>-<YYYY>-<seq5>`.

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| plan_id | الخطة | FK | N | null = unplanned (غير مخطط) | — | none |
| planned_date | التاريخ المخطط | date | cond. | required iff plan_id | 2026-09-13 | none |
| completed_at | تاريخ التنفيذ | timestamptz | cond. | required for Completed; ≤ now | 2026-09-14 10:00 | none |
| inspector_id | المفتش | FK user | cond. | Completed | — | personal |
| items_checked / items_compliant | البنود / المطابقة | int | N | compliant ≤ checked | 40 / 36 | none |
| score_pct | نسبة المطابقة | decimal(5,1) | derived | compliant ÷ checked × 100 | 90.0 | none |
| findings | الملاحظات | list | N | each: description, severity (`low/medium/high/critical`), ca_required | — | none |
| status | الحالة | enum | Y | §4.4 | completed | none |
| cancel_reason | سبب الإلغاء | text | cond. | Cancelled | Area handed over | none |

### 3.8 Corrective action — إجراء تصحيحي

Ref `CA-<project>-<YYYY>-<seq5>`.

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| source_type, source_id | المصدر | enum / FK | Y | `incident`, `observation`, `inspection`, `ptw_audit` (v1.2; source_id = PTW audit, `3-ptw.md` §3.15), `equipment_defect` (v1.3; source_id = Phase 4 defect, `4-third-party-cert.md` §3.11, raised manually only, DF-10), `heat_check` (v1.5; source_id = 6b heat welfare check or midday-ban patrol, `6b-heat-stress.md` §3.8/§3.9, RS-3/MB-3), `emergency` (v1.6; source_id = 6c asset check, drill or event, `6c-emergency-drills.md` EA-4/DR-6/EV-5), `field_audit` (v1.7; source_id = 6d audit, `6d-field-assurance.md` AUD-4; `inspection` CAs may also be created by 6d FND-3), `ai_recommendation` (after human confirmation), `other` | incident / INC-…-0147 | none |
| project_id, site_id, zone_id | — | FK | Y/Y/N | from source by default | — | none |
| responsible_engagement_id | المقاول المسؤول | FK | Y | — | NAJD@ANIA-EXP | none |
| title / description | العنوان / الوصف | string(150) / text(2000) | Y | — | Install toe-boards and double guardrails on all Pier B platforms | none |
| control_level | مستوى التحكم | enum | Y | hierarchy: `elimination` إزالة, `substitution` استبدال, `engineering` هندسي, `administrative` إداري, `ppe` معدات الوقاية | engineering | none |
| priority | الأولوية | enum | Y | `critical` حرجة, `high` عالية, `medium` متوسطة, `low` منخفضة | high | none |
| owner_id | المسؤول عن التنفيذ | FK user | Y | active user with access to project/engagement | — | personal |
| verifier_id | المُحقِّق | FK user | Y | ≠ owner; role per §5.5 rule CA-6 | — | personal |
| due_date | تاريخ الاستحقاق | date | Y | default created date + priority days (§3.10); ≥ created date | 2026-09-15 | none |
| original_due_date | تاريخ الاستحقاق الأصلي | date | sys | set at creation, immutable | 2026-09-15 | none |
| extensions | التمديدات | list | N | ≤ `ca_max_extensions` (2); each: new_due, reason, requested_by, approved_by, approved_at | — | personal (user refs) |
| completed_at | تاريخ الإنجاز | timestamptz | sys | set on → Pending Verification; cleared on rejection | — | none |
| evidence_text / evidence_files | دليل الإنجاز | text / file[] | Y at completion | ≥ 1 of text (≥ 20 chars) or file | photo of guardrails | personal (possible) |
| verified_at, verification_comment | التحقق | timestamptz / text | sys / cond. | comment required on rejection | — | none |
| status | الحالة | enum | Y | §4.5 | in_progress | none |
| cancel_reason | سبب الإلغاء | text | cond. | Cancelled | superseded by CA-…-00412 | none |
| overdue | متأخر | bool | derived | §6.6 | true | none |

### 3.9 HSE meeting — اجتماع الصحة والسلامة (minimal, for leading indicator K-39)

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| project_id, engagement_id | — | FK | Y/N | — | ANIA-EXP / — | none |
| meeting_type | نوع الاجتماع | enum | Y | `hse_committee`, `contractor_hse`, `management_walk`, `other` | hse_committee | none |
| planned_date / held_date | المخطط / المنعقد | date | Y/N | — | 2026-09-07 | none |
| invited_count / attended_count | المدعوون / الحاضرون | int | Y/cond. | attended ≤ invited | 18 / 15 | none |
| minutes_file | المحضر | file | N | — | — | personal |

### 3.10 Phase 1 project settings (extends Phase 0 §3.9; HSE Manager only, audited)

| Key | AR label | Type | Default | Allowed |
|---|---|---|---|---|
| lost_days_cap | الحد الأقصى لأيام الغياب | int | 180 | 180 (OSHA) · 0 = no cap |
| fatality_lost_days_charge | أيام محتسبة للوفاة/العجز الكلي | int | 0 ASSUMPTION | 0 · 6000 (ANSI Z16.1) |
| include_commuting_in_rates | احتساب حوادث التنقل في المعدلات | bool | false | — |
| include_non_contractor_cases_in_rates | احتساب حالات موظفي العميل | bool | false ASSUMPTION | — |
| max_hours_per_person_day | أقصى ساعات للفرد يومياً | int | 16 | 12–24 |
| warn_hours_per_person_day | حد التنبيه للساعات | int | 12 | 8–16 |
| daily_return_deadline | موعد البيان اليومي | time | 10:00 next day | — |
| completeness_threshold_pct | حد اكتمال البيانات | int | 95 | 50–100 |
| inspection_grace_days | مهلة التفتيش | int | 2 ASSUMPTION | 0–7 |
| ca_due_days | مدة الإجراء حسب الأولوية | map | critical 1, high 7, medium 14, low 30 ASSUMPTION | 1–90 each |
| ca_max_extensions | أقصى عدد تمديدات | int | 2 | 0–5 |
| new_starter_days | حد العامل الجديد | int | 30 | 7–90 |
| heat_season | موسم الحرارة | date range (MM-DD) | 06-01 → 09-30 ASSUMPTION (covers midday ban 06-15 → 09-15) | — |
| low_exposure_hours | حد التعرض المنخفض | int | 200,000 | — |
| leading_warning_drop_pct | حد انخفاض البلاغات | int | 20 | 5–90 |
| leading_warning_rise_pct | حد ارتفاع المتأخرات | int | 25 | 5–200 |
| kpi_targets | المستهدفات | map metric → decimal | none (no RAG colour until set) | per metric |
| month_lock_day | يوم قفل الشهر | int | 10 (day of next month) ASSUMPTION | 1–28 |
| injury_identity_retention_years | مدة الاحتفاظ بهوية المصاب | int | 10 ASSUMPTION `VERIFY` | 5–30 |
| ai_enabled | تفعيل المساعد الذكي | bool | true | — |
| induction_register_from | بدء احتساب التعريفات من السجل | date / null | null (v1.1) | any date ≥ project start; set when Phase 2 induction register goes live on the project (K-38) |
| training_register_from | بدء احتساب ساعات التدريب من السجل | date / null | null (v1.4) | ≥ project start; ≤ today; once set may only move earlier; set when the Phase 5 training register goes live on the project (K-37, `5-training.md` TH-6) |

### 3.11 Reference lists (seeded enums, EN/AR, editable by HSE Manager — codes immutable)

| List | Values (code — EN / AR) |
|---|---|
| **S** Severity (1–5) | 1 Negligible (first aid / no damage < SAR 5k) طفيف · 2 Minor (MTC/RWC, damage < 50k, contained spill) بسيط · 3 Serious (LTI, damage < 500k, off-site env impact) جسيم · 4 Major (permanent disability, multiple LTIs, damage < 5M, regulatory env breach) كبير · 5 Catastrophic (fatality, damage ≥ 5M, major env) كارثي ASSUMPTION thresholds |
| **A** Activity | excavation حفر · concrete خرسانة · formwork شدات · rebar حديد تسليح · steel_erection تركيب حديد إنشائي · scaffolding سقالات · lifting رفع · work_at_height عمل على ارتفاع · electrical كهرباء · mep_installation تركيبات كهروميكانيكية · hot_work أعمال ساخنة · paving_asphalt رصف وأسفلت · airfield_lighting إنارة المدارج · road_works أعمال طرق · demolition هدم · driving_transport قيادة ونقل · material_handling مناولة مواد · housekeeping نظافة الموقع · survey مساحة · testing_commissioning اختبار وتشغيل · maintenance صيانة · other أخرى |
| **T** Trade | labourer عامل · carpenter نجار · steel_fixer حداد مسلح · steel_erector مركب حديد · scaffolder عامل سقالات · rigger عامل ربط · crane_operator مشغل رافعة · plant_operator مشغل معدات · driver سائق · electrician كهربائي · plumber سباك · welder لحام · mason بنّاء · painter دهان · surveyor مساح · supervisor مشرف · engineer مهندس · hse_staff موظف سلامة · flagman منظم حركة · other أخرى |
| **B** Body part | head الرأس · eye العين · face الوجه · neck الرقبة · shoulder الكتف · upper_arm العضد · elbow المرفق · forearm الساعد · wrist الرسغ · hand اليد · finger الإصبع · chest الصدر · upper_back أعلى الظهر · lower_back أسفل الظهر · abdomen البطن · hip_pelvis الورك/الحوض · thigh الفخذ · knee الركبة · lower_leg الساق · ankle الكاحل · foot القدم · toe إصبع القدم · multiple متعدد · internal_systemic داخلي/جهازي |
| **N** Nature | fracture كسر · laceration جرح قطعي · abrasion سحجة · contusion كدمة · sprain_strain التواء/شد · puncture وخز · burn_thermal حرق حراري · burn_chemical حرق كيميائي · electric_shock صدمة كهربائية · amputation بتر · crush سحق · dislocation خلع · foreign_body_eye جسم غريب في العين · concussion ارتجاج · heat_exhaustion إجهاد حراري · heat_stroke ضربة شمس · inhalation_poisoning استنشاق/تسمم · noise_hearing فقدان سمع · dermatitis التهاب جلد · multiple متعدد · other أخرى |
| **M** Mechanism | fall_from_height سقوط من ارتفاع · slip_trip_same_level انزلاق/تعثر · struck_by_falling_object اصطدام بجسم ساقط · struck_by_moving_object اصطدام بجسم متحرك · struck_against ارتطام بجسم · caught_in_between انحشار · contact_electricity تماس كهربائي · contact_hot_fire تماس حراري/حريق · contact_chemical تماس كيميائي · overexertion_manual_handling إجهاد/مناولة يدوية · repetitive_motion حركة متكررة · vehicle_plant_collision تصادم مركبة/معدة · vehicle_overturn انقلاب مركبة · exposure_heat تعرض للحرارة · exposure_noise تعرض للضوضاء · bite_sting لدغة · assault اعتداء · other أخرى |
| **G** Agency | scaffold سقالة · ladder سلم · mewp رافعة أفراد · crane_lifting_gear رافعة/معدات رفع · earthmoving معدات حفر · light_vehicle مركبة خفيفة · heavy_vehicle مركبة ثقيلة · airside_gse معدات خدمة أرضية · aircraft طائرة · hand_tool أداة يدوية · power_tool أداة كهربائية · formwork شدات · rebar_steel حديد · materials مواد · electrical_installation تمديدات كهربائية · chemical مادة كيميائية · hot_work_equipment معدات لحام · ground_surface أرضية · stairs_openings درج/فتحات · excavation_trench حفرية · weather_sun الطقس/الشمس · other أخرى |
| **F** First-aid treatments (OSHA 1904.7(b)(5)(ii)) | otc_medication_otc_strength دواء بدون وصفة · tetanus_immunisation تطعيم كزاز · wound_cleaning تنظيف جرح · wound_covering_steristrips ضماد/لاصق · hot_cold_therapy كمادات · non_rigid_support رباط مرن · temporary_immobilisation_transport تثبيت مؤقت للنقل · nail_drilling ثقب الظفر · eye_patch رقعة عين · eye_irrigation_swab غسل العين · splinter_removal إزالة شظية · finger_guard واقي إصبع · massage تدليك · fluids_oral_heat سوائل فموية للحرارة |
| **MT** Medical treatments (any ⇒ beyond first aid) | sutures_staples_glue غرز/دبابيس · rigid_splint جبيرة صلبة · prescription_medication دواء بوصفة · otc_at_prescription_strength جرعة وصفية · iv_fluids سوائل وريدية · physiotherapy علاج طبيعي · foreign_body_removal_eye_tools إزالة جسم من العين بأداة · surgical_debridement تنظيف جراحي · hospital_admission تنويم · other_medical أخرى طبية. Diagnostic-only items `x_ray_diagnosis`, `observation_only` are neither FA nor MT. |
| **O** Observation category | work_at_height · lifting · excavation · scaffolding · electrical · hot_work · ppe · housekeeping · traffic_plant · airside_fod_control · airside_driving · heat_stress · confined_space · manual_handling · tools_equipment · environmental · fire_safety · welfare · permit_compliance · behaviour_other (EN/AR in i18n files) |
| **I** Inspection type | general_site · scaffold · lifting_equipment · electrical · excavation · housekeeping · fire_safety · welfare · airside_fod_walk · plant_vehicle · environmental · ppe · leadership_walk |
| **R** Root cause (ICAM) `VERIFY` | **AD** Absent/Failed Defences: AD-01 physical barrier/edge protection, AD-02 isolation/LOTO, AD-03 PPE, AD-04 permit/authorisation, AD-05 warning/detection, AD-06 exclusion zone, AD-07 supervision as a defence · **IT** Individual/Team Actions: IT-01 slip/lapse, IT-02 mistake (knowledge/rule), IT-03 routine violation, IT-04 exceptional violation · **TE** Task/Environmental Conditions: TE-01 heat/weather, TE-02 fatigue/shift, TE-03 time pressure, TE-04 lighting/visibility, TE-05 workplace layout/access, TE-06 equipment condition, TE-07 language/communication, TE-08 new to task/site · **OF** Organisational Factors: OF-01 training/competence, OF-02 procedures, OF-03 risk assessment/JSA, OF-04 supervision, OF-05 planning/resourcing, OF-06 contractor management, OF-07 management of change, OF-08 maintenance, OF-09 design, OF-10 culture/incentives |

## 4. Workflow / states

### 4.1 Workforce daily return

| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Draft | مسودة | Contractor HSE Rep (C), HSE Officer, HSE Manager, Site Engineer (S) | Create (manual) |
| Draft → Submitted | مُقدَّم | same | All validations pass; import commit creates rows directly as Submitted |
| Submitted → Draft | مسودة | creator, HSE Officer | Edit before verification |
| Submitted → Verified | مُعتمد | HSE Officer, HSE Manager | Row or bulk verify; verifier ≠ creator ASSUMPTION |
| Verified → Submitted | مُقدَّم | HSE Officer, HSE Manager | Correction with reason |
| Submitted/Verified → Locked | مقفل | System on `month_lock_day` of following month; or HSE Manager "lock month" | Whole month per project |
| Locked → Verified | مُعتمد | HSE Manager only | Reason required; audited; KPI "restated" marker on affected periods |

KPIs use Submitted, Verified and Locked rows; Drafts are excluded.

### 4.2 Incident

| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Draft | مسودة | any role except viewer_client | Create; auto-saved |
| Draft → Reported | مُبلَّغ | reporter | Required fields valid; sets reported_at; triggers §7 alerts |
| Reported → Under Investigation | قيد التحقيق | HSE Officer, HSE Manager | Classification reviewed (cases may stay provisional), investigation level + lead + due date set |
| Under Investigation → Pending Review | بانتظار المراجعة | lead investigator | Investigation required fields complete (§3.5); CAs created for each root cause or "no action" justification |
| Pending Review → Under Investigation | قيد التحقيق | approver | Returned with comment |
| Pending Review → Actions Pending | إجراءات قيد التنفيذ | HSE Officer (L1/L2); HSE Manager (L3) | Investigation approved; all injury cases `confirmed`; ≥ 1 CA not Closed/Cancelled |
| Pending Review / Actions Pending → Closed | مغلق | System (when last CA Closed/Cancelled) or approver if zero open CAs | All CAs Closed or Cancelled |
| Reported / Under Investigation → Voided | ملغى | HSE Officer, HSE Manager | Reason required (duplicate, not an incident). Excluded from KPIs |
| Closed → Under Investigation | قيد التحقيق | HSE Manager | Reopen with reason |
| Voided → Reported | مُبلَّغ | HSE Manager | Un-void with reason |

Near miss and L1 events may skip investigation: Reported → Closed by HSE Officer when level = L1 and no CA required (`L1 quick close`), still requires immediate_actions.

### 4.3 Observation

| From → To | AR | Who | Trigger |
|---|---|---|---|
| — → Closed | مغلقة | observer | Safe types, or unsafe with closed_on_spot = true and no CA |
| — → Open | مفتوحة | observer | Unsafe, not closed on spot |
| Open → Action Raised | تم إنشاء إجراء | HSE Officer, Site Engineer, Contractor HSE Rep (C) | CA created from it |
| Open → Closed | مغلقة | same | Closure comment |
| Action Raised → Closed | مغلقة | System | All linked CAs Closed/Cancelled |

### 4.4 Inspection

| From → To | AR | Who | Trigger |
|---|---|---|---|
| — → Planned | مخطط | System | Generated from active plan daily for next 35 days |
| Planned → Completed | منجز | assignee / any user with capability 33 | Record results |
| Planned → Missed | فائت | System (00:05 project tz) | today > planned_date + inspection_grace_days and not Completed |
| Missed → Completed (late) | منجز متأخر | assignee | Late recording allowed; stays "late" for KPIs |
| Planned/Missed → Cancelled | ملغى | HSE Officer, HSE Manager | Reason required; excluded from planned count |
| — → Completed (unplanned) | منجز غير مخطط | capability 33 | Ad-hoc |

### 4.5 Corrective action

| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Open | مفتوح | creators per capability 34 | Create |
| Open → In Progress | قيد التنفيذ | owner | Accept |
| Open/In Progress → Pending Verification | منجز – بانتظار التحقق | owner | Evidence required; sets completed_at |
| Pending Verification → Closed | مغلق | verifier | Effectiveness confirmed; sets verified_at |
| Pending Verification → In Progress | قيد التنفيذ | verifier | Rejected with comment; completed_at cleared |
| Open/In Progress → Cancelled | ملغى | HSE Officer, HSE Manager | Reason required |
| Closed → In Progress | قيد التنفيذ | HSE Manager | Reopen with reason |
| (due date) extension | تمديد | owner requests; HSE Officer/Manager approves | ≤ ca_max_extensions; reason required |

`Overdue` (متأخر) is a derived flag, not a state (§6.6).

## 5. Business rules

### 5.1 Workforce & man-hours (W)
- W-1. Uniqueness key: (project, work_date, site, zone or null, engagement, shift). A second row with the same key is rejected (manual) or handled per import mode.
- W-2. Man-hours used by every KPI = Σ man_hours of Submitted/Verified/Locked rows in scope; all subcontractor tiers included (roll-up per Phase 0 §8.3).
- W-3. Direct/subcontractor split is by engagement tier (§3.1 derived) and reported per tier 1/2/3.
- W-4. A Contractor HSE Rep may create/import rows only for their engagement and its descendants (Phase 0 rule 10, K4); a Site Engineer only for their sites.
- W-5. Import is two-step: (a) **dry-run** validates every row and returns the full report with counts, writes nothing to returns; (b) **commit** of that batch id within 60 min, allowed only if rows_error = 0. Commit is atomic (all rows or none).
- W-6. In `upsert` mode, rows matching an existing Draft/Submitted/Verified key replace it (old values kept in audit before/after); Locked keys are E11 in any mode. Replaced Verified rows return to Submitted.
- W-7. Warnings do not block commit but are stored on the batch and shown to the verifier.
- W-8. A day counts as reported for completeness (K-45) when a row exists for the engagement × site with no_work = true or headcount > 0.
- W-9. Rows for a Suspended contractor are accepted with W03 (work may physically have occurred and must be counted); Blacklisted/Demobilised after demobilisation_date → E05.
- W-10. Editing or deleting a Locked row is possible only for HSE Manager via Locked → Verified with reason (§4.1); the KPI engine marks any period whose inputs changed after lock as "restated".
- W-11. Man-hours are stored to 2 decimals; displayed as integers with thousands separators (round half-up).
- W-12. Daily return reminders: missing return for an engagement × site by `daily_return_deadline` raises alert (§7).

### 5.2 Incidents & injury cases (I)
- I-1. Reported incidents cannot be deleted; only Voided (with reason). Drafts may be deleted by their creator.
- I-2. An `injury_illness` incident must have ≥ 1 injury case before Draft → Reported.
- I-3. Near miss = an event with no injury, illness, damage or environmental impact that had potential to cause one; `near_miss` cannot be combined with other types (rule enforced).
- I-4. A case counts in rates only if: incident status ∉ {Draft, Voided} AND work_related = true AND person_type = contractor_worker (or client_pmc_staff when `include_non_contractor_cases_in_rates` = true) AND (commuting = false OR `include_commuting_in_rates` = true). Excluded cases still appear in counts lists labelled "excluded from rates" with reason.
- I-5. **Category derivation** (system proposes; HSE Officer confirms), first match wins: (1) fatal = true → **FAT**; (2) days_away ≥ 1 OR permanent_disability ≠ none → **LTI**; (3) restricted_days ≥ 1 → **RWC**; (4) transfer_days ≥ 1 → **JTC**; (5) any treatment in list MT, OR loss_of_consciousness = true, OR nature ∈ {fracture, dislocation, amputation, concussion, heat_stroke} (significant diagnosed injury), OR treated_at = hospital_admitted → **MTC**; (6) otherwise → **FAC**.
- I-6. A confirmed category may differ from the derived one only with a justification text (≥ 20 chars) by HSE Manager; the deviation is flagged in the register and audit.
- I-7. Day of injury is never counted as a lost, restricted or transfer day (OSHA 1904.7(b)(3)); a worker who returns for their next full shift is not LTI, even if they missed part of the injury shift.
- I-8. LTI requires days_away ≥ 1 (or permanent disability); an LTI with rtw_date null is "open" and its days accrue daily until rtw_date is set or the cap is reached (§6.3).
- I-9. A case is re-derived whenever its dates/treatments change; a category change on a case in a Locked month marks that period "restated" and notifies HSE Manager.
- I-10. Fatalities count in FAT, are also included in the LTI count used for LTIFR and LTI-free counters, are included once in TRIR, and are **not** in DART (OSHA column G vs H/I).
- I-11. Permanent disability cases are LTI (rule I-5 step 2) and are additionally reported as a separate count (K-05b).
- I-12. Privacy cases: person_name is replaced by "Privacy case / حالة خصوصية" for every role except hse_manager; id_number hidden for all except hse_manager.
- I-13. HiPo = potential_severity ≥ 4; HiPo incidents (including near misses) require investigation level L3.
- I-14. **Minimum investigation level:** L3 if any case FAT/LTI or permanent disability, or dangerous_occurrence, or HiPo, or environmental with env_reached ∈ {drain, water_body}, or airside_flags contains runway_incursion/aircraft_involved/ols_infringement; L2 if any case RWC/JTC/MTC, or property damage ≥ SAR 50,000 ASSUMPTION, or any airside flag; otherwise L1.
- I-15. Lead investigator must not be the injured person's direct supervisor ASSUMPTION; L3 team must include ≥ 1 member from the responsible contractor and the lead must be hse_officer or hse_manager.
- I-16. Pending Review requires: each root cause has ≥ 1 linked CA or a "no further action" justification; L2/L3 have ≥ 1 root cause; L3 has lessons_learned.
- I-17. For incidents with potential_severity ≥ 4, at least one linked CA must have control_level ∈ {elimination, substitution, engineering}, or the approver records why no higher control is reasonably practicable.
- I-18. An incident may only reference zones of its site; `airside_flags` only for airside zones.
- I-19. occurred_at more than 24 h before reported_at flags "late report" (counted in K-47).
- I-20. Notifications required (derived; each shows "due / done / overdue"): `gosi` for every contractor_worker case FAT/LTI/RWC/JTC/MTC and every commuting case (deadline `VERIFY` R5, default 3 calendar days from occurrence ASSUMPTION); `mhrsd` for FAT and permanent disability `VERIFY` R6; `civil_defense` for fire/explosion DO; `gaca` + `airport_operator` for any airside flag in {runway_incursion, aircraft_involved, ols_infringement, notam_breach} — immediately `VERIFY` R8; `client` per contract for FAT/LTI/DO/HiPo within 24 h ASSUMPTION; `police` for FAT.
- I-21. The platform tracks notifications; it does not submit to GOSI/MHRSD/GACA systems in Phase 1.

### 5.3 Observations (O)
- O-1. Any role except viewer_client may submit an observation for any engagement within their site scope (a Contractor HSE Rep may observe other contractors on shared sites ASSUMPTION; C-scope applies to *editing*, not to creating).
- O-2. Unsafe observations with risk_rating = high and closed_on_spot = false must have a CA within 24 h, otherwise alert (§7).
- O-3. Safe observations are closed on submission and are immutable after 24 h.
- O-4. The observed worker's name is never collected (no field exists); photos display a warning to avoid faces.
- O-5. Anonymous observations hide observer_id from every role except hse_manager, including in exports and audit views for other roles.

### 5.4 Inspections (N)
- N-1. Plans generate instances on each due date between start_date and end_date; changing a plan affects only future Planned instances.
- N-2. An inspection is **on time** if completed_at local date ≤ planned_date + inspection_grace_days; **late** if completed after that; **missed** if not completed (status Missed).
- N-3. Cancelled instances are excluded from planned counts; cancellation after the instance became Missed requires HSE Manager.
- N-4. Findings with ca_required = true must have a linked CA before the inspection can be saved as Completed.
- N-5. Unplanned inspections count in "inspections done" (K-35b) but not in compliance % (K-34/K-35).

### 5.5 Corrective actions (CA)
- CA-1. Every CA has exactly one source, one owner, one verifier, one responsible engagement and a due date.
- CA-2. Default due_date = created date + ca_due_days[priority]; owner may not set a later due date than default without extension approval.
- CA-3. Extensions: max ca_max_extensions; each requires reason and approval by hse_officer/hse_manager (not the owner); original_due_date never changes.
- CA-4. completed_at requires evidence (text ≥ 20 chars or ≥ 1 file).
- CA-5. Verifier ≠ owner. Verifier role: hse_officer or hse_manager for critical/high; additionally site_engineer or contractor_hse_rep (C scope, not of own CA) for medium/low ASSUMPTION.
- CA-6. A CA with control_level = ppe as the only CA of an incident with potential_severity ≥ 3 triggers a warning to the approver "PPE is the lowest control — record why higher controls are not reasonably practicable" (rule I-17 is the hard block at ≥ 4).
- CA-7. AI-recommended actions are created only by a human clicking "Create CA" and editing the draft; source_type = ai_recommendation with the AI answer id.
- CA-8. Cancelled CAs are excluded from every CA KPI.

### 5.6 KPI engine (K)
- K-R1. KPIs are computed on read from stored records (no stored KPI values) except published monthly report snapshots (§5.9 AI-20).
- K-R2. Date attribution (project tz): man-hours → work_date; injury cases and events → incident occurred_at local date; observations → observed_at; inspections → planned_date (compliance) / completed_at (done count); CAs → due_date (on-time closure), created_at (raised), as_of (overdue); meetings → planned_date.
- K-R3. **Lost days attribution:** all lost days of a case are attributed to the period containing the injury date (case-based, like the OSHA 300 log) ASSUMPTION (§10 Q4). Open cases use days accrued up to the as_of date.
- K-R4. **Contractor attribution:** injury cases → injured person's employer_engagement; NM/PD/ENV/DO events → responsible_engagement; observations → observed_engagement; CAs → responsible_engagement; inspections → plan/instance engagement (unassigned ones are included only when no contractor filter is applied).
- K-R5. Contractor filter default = selected engagement **plus descendants** (roll-up); toggle "this contractor only". Man-hours and incidents always use the same population.
- K-R6. Zone/zone_type filter: counts use record zone; rates use man-hours rows with that zone. If Σ man-hours in filter = 0 → rates "—" with note "Man-hours not recorded at zone level"; if the filtered sites have unzoned man-hours rows in the period → rates shown with warning "partial exposure".
- K-R7. Rate with man-hours = 0 → "—" (Phase 0 K1). Rate with count 0 and man-hours > 0 → 0.00.
- K-R8. **Rounding:** compute with exact decimal arithmetic from unrounded sums; round only for display/API output, **half-up** (ROUND_HALF_UP): rates 2 dp; percentages 1 dp; ratios 1 dp; averages (headcount) 0 dp; training hours/worker 2 dp. Never sum or average rounded values.
- K-R9. Deltas: abs Δ = current − comparison (unrounded, then 2 dp); % Δ = (current − comparison) ÷ comparison × 100 (1 dp); comparison = 0 or "—" → % Δ "n/a".
- K-R10. **Periods:** presets day, week (week_start setting), month, quarter, year, MTD, QTD, YTD, R12 (rolling 12 months), ITD (project to date), custom range. All inclusive of start and end dates.
- K-R11. **Comparisons:** previous period = same preset immediately preceding (previous calendar month/quarter/year; custom range of N days → the N days ending the day before start); SPLY = same start/end dates minus 1 year (29 Feb → 28 Feb); R12 window ending at period end = [add_months(end, −12) + 1 day, end].
- K-R12. Multi-project aggregation (HSE Manager "All projects") is allowed only when the selected projects share the same `ltifr_base_hours` and `rate_base_hours`; otherwise rates are computed at 1,000,000/200,000 and a banner states the bases used.
- K-R13. Every rate in API responses returns: value, numerator, denominator (man-hours), base, period, filters, data_completeness_pct, provisional_cases_count, restated flag.
- K-R14. Provisional classifications are included in KPIs and flagged ("n provisional"); Voided incidents never.
- K-R15. Display label always includes the base, e.g. "TRIR (per 200,000 h) / معدل الحالات المسجلة (لكل 200,000 ساعة)" (Phase 0 rule 31).

### 5.7 Dashboard (D)
- D-1. Every tile, chart and table value comes from a KPI-engine endpoint; the frontend performs no arithmetic other than formatting.
- D-2. Filters: project (single; "All projects" for hse_manager), site (multi), zone (multi), zone_type (airside/landside/other), contractor (engagement, with "include subcontractors" toggle, default on), tier (1/2/3), period preset/custom, comparison (previous / SPLY / R12 — default previous). Filters persist per user (localStorage + server preference).
- D-3. Role scoping is applied server-side before filters: a Contractor HSE Rep sees their C scope only, and "All contractors" for them means their C scope.
- D-4. Lagging tiles: decrease = good (green arrow), increase = bad (red). Leading tiles: increase = good, except overdue CAs (decrease = good). With a target set: green if meets target, amber if within 20 % of target, red otherwise ASSUMPTION.
- D-5. The headline LTI-free counter shows days and man-hours "since last LTI on <date> (<incident ref, if user may see it>)" or "since <start date>" if none.
- D-6. Data completeness < completeness_threshold_pct shows a banner "Man-hours incomplete for n engagement-days — rates may be overstated".
- D-7. Breakdown dimensions by nationality and age band are visible only to hse_manager and hse_officer; any breakdown cell representing 1–2 persons is shown only to those roles.
- D-8. No person names appear in any dashboard widget (P6); incident refs link to the register where field access rules apply.
- D-9. Dashboard loads in < 3 s for a project with 3 years of data (p95, local docker reference machine) ASSUMPTION.
- D-10. Exports of dashboard tables (CSV/Excel/PDF) follow Phase 0 rule 49 and are audited.

### 5.8 PDPL handling of injured-person and observation data (P1-x, extends Phase 0 P1–P13)
- P1-1. Sensitive fields (§3.4): person_name, id_number, illness, body_part, nature, treatments, loss_of_consciousness, treated_at, fatal/date_of_death, all dates of absence/restriction, medical_notes, medical_attachments, privacy_case, days_* per person. Their read access follows capabilities 29–30 (§5.10); every read writes `sensitive_field_read` (P5).
- P1-2. Aggregated statistics by body part/nature/category are not personal data when shown as counts without identity; the register list view for roles without capability 29 shows case rows as "Person 1 · scaffolder · NAJD" (no name, no ID).
- P1-3. Medical attachments live in a separate encrypted bucket with per-object access via short-lived signed URLs (≤ 5 min); not included in any bulk export.
- P1-4. Nationality, age band, trade and days_on_site are collected for analysis only (stated in the privacy notice); used in AI analysis only as aggregates for roles hse_manager/hse_officer.
- P1-5. Retention: incident and case statistical fields retained for project life + 10 years ASSUMPTION; identity fields (person_name, id_number, employee_no, gosi_case_ref, medical_notes, medical_attachments) anonymised `injury_identity_retention_years` after incident closure (default 10 `VERIFY` against GOSI claims and civil limitation periods). Anonymisation keeps category, body part, nature, dates and contractor.
- P1-6. Exports of the incident register include identity columns only for capability 29 holders and require a stated purpose (dropdown: GOSI, client report, legal, insurance, other+text) recorded in the `export` audit entry.
- P1-7. Workforce returns contain no personal data; observer and CA owner/verifier are user references (personal, not sensitive).
- P1-8. Free-text fields are scanned on save for 10-digit numbers starting with 1 or 2 (possible ID) and warn the user (not block) ASSUMPTION.

### 5.9 AI assistant (AI)
Model: default `claude-sonnet-5-5`; `claude-opus-5-5` for monthly report drafting and "deep analysis" requests (build plan §3). The model calls only the tools below; it never writes SQL and never receives sensitive fields.

**Tools** (all read-only; executed server-side with the asking user's identity and scope; parameters out of scope are silently narrowed and the narrowing reported in the tool result):

| # | Tool | Parameters | Returns |
|---|---|---|---|
| T1 | `get_kpis` | project_ids, period {preset or start/end}, filters {site_ids, zone_ids, zone_type, engagement_ids, include_descendants, tier}, metrics[] (K-ids), compare[] {previous, sply, r12} | per metric: value, numerator, denominator, base, comparisons with abs/% deltas (K-R9), completeness, provisional count, restated flag |
| T2 | `get_kpi_timeseries` | metric, granularity {week, month}, start, end, filters | series of {period, value, numerator, denominator}, plus R12 series and 3-period moving average |
| T3 | `get_breakdown` | measure {injury_cases, events_by_type, observations, cas, inspections}, dimension (§6.8 list), period, filters, top_n ≤ 20 | rows {dimension value, count, man-hours if exposure-based, rate, share %}; cells < 3 persons suppressed to "<3" for non-manager/officer roles |
| T4 | `search_incidents` | filters {period, types, categories, site, zone, contractor, activity, mechanism, agency, hipo, status}, limit ≤ 50 | de-identified rows: ref, date, shift, types, case categories, site/zone, contractor code, activity, mechanism, agency, actual/potential severity, status, title (names stripped); v1.2: linked permit numbers and types (no names) |
| T5 | `get_incident` | ref | de-identified detail: as T4 + description (names/IDs redacted server-side), immediate actions, investigation (level, causes, root-cause codes, lessons learned), linked CA refs/status/control level; v1.2: linked permit numbers and types (no names) |
| T6 | `list_corrective_actions` | filters {status, overdue, priority, control_level, source_type, contractor, due range}, limit ≤ 100 | ref, title, priority, control level, responsible contractor code, owner **role** (not name), due, days overdue, extensions count, status |
| T7 | `list_observations_summary` | period, filters, group_by {category, obs_type, contractor, site, zone, week} | counts and safe/unsafe split |
| T8 | `list_inspections_summary` | period, filters, group_by {type, site, contractor, week} | planned, on time, late, missed, cancelled, unplanned, avg score |
| T9 | `compare_groups` | measure (injury cases by category set, or events by type), dimension {heat_season, shift, hour_band, weekday, contractor, activity, new_starter, site, zone_type, ptw_involved, ca_overdue_at_event, ptw_audit_band (v1.2: contractor-months with K-61 < `ptw_audit_warning_pct` vs ≥, `3-ptw.md` KP-5), training_gap_at_event (v1.4: yes / no / unknown, `5-training.md` TR9)}, period, filters | per group: count, exposure (man-hours where available, else headcount-days, else none), rate, rate ratio vs reference group, 95 % CI, p-value (exact Poisson/conditional binomial for 2 groups; chi-square for > 2), `sample_sufficient` flag per §5.9 AI-9 |
| T10 | `get_data_quality` | period, filters | completeness % and missing engagement-days, provisional cases, late reports, restated periods, investigations overdue |
| T11 | `get_lti_free` | filters, as_of | days, man-hours, last LTI date and ref, run start basis |
| T12 | `get_settings_and_targets` | project_id | bases, thresholds, targets, heat season, new_starter_days |
| T13 | `get_leading_warnings` | project_id, months | backend-computed warnings E1–E4 (§6.9) and, v1.1, E5–E7 (`2-access-permits.md` §6.9) and, v1.2, E8–E9 (`3-ptw.md` §6.12) and, v1.3, E10–E11 (`4-third-party-cert.md` §6.9) and, v1.4, E12–E13 (`5-training.md` §6.9) with inputs |
| T14 | `get_access_kpis` (v1.1) | project_ids, period, filters {site_ids, zone_ids, engagement_ids, include_descendants, gate_ids}, metrics[] (K-38, K-48…K-60, K-53b), group_by {kind, reason_code, contractor, zone, gate, month} | aggregates only, per `2-access-permits.md` §6.8 and KA-5: value, numerator, denominator, breakdown rows; no names, ID numbers, worker_no, photos or plates |
| T15 | `get_ptw_kpis` (v1.2) | project_ids, period, filters {site, zone, engagement, include_descendants, type}, metrics[] (K-46, K-46b, K-61…K-71), group_by {type, contractor, zone, month, week, suspension_reason, audit_item, simops_rule} | aggregates only, per `3-ptw.md` §6.11 and KP-5: value, numerator, denominator, breakdown rows; no names, worker_no, signatures or appointment holders |
| T16 | `get_certification_kpis` (v1.3) | project_ids, period, filters {site, zone, engagement, include_descendants, category, cert_type}, metrics[] (K-72…K-81), group_by {category, cert_type, contractor, tpi, defect_category, reason_code, month} | aggregates only, per `4-third-party-cert.md` §6.7 and KC-4: value, numerator, denominator, breakdown rows; equipment tags and TPI codes may appear; no names, worker_no, cert numbers, ID data, ban reasons or verification-failure details |
| T17 | `get_training_kpis` (v1.4) | project_ids, period, filters {site, zone, engagement, include_descendants, trade, course_code, course_category}, metrics[] (K-37, K-82…K-88), group_by {course, course_category, contractor, trade, provider, source, month} | aggregates only, per `5-training.md` §6.8 and TK-4: value, numerator, denominator, breakdown rows; no names, worker_no, certificate numbers, scores, ID data or verification-failure details |

**Rules:**
- AI-1. Every numeric statement (count, rate, %, date, delta) in an answer must come verbatim (after display rounding) from a tool result in the same conversation turn. The model does not do its own arithmetic; derived comparisons must be requested from tools (T1/T2/T9 return deltas and ratios).
- AI-2. **Number-grounding check:** before display, the backend extracts every number from the answer and verifies it appears in that turn's tool outputs (exact match at display precision; ordinal words and years in period names exempt). On failure the answer is regenerated once with the failing numbers listed; on second failure the user sees "I could not produce a verified answer" plus the raw tool table. Failures are logged.
- AI-3. Every answer ends with a **Sources** block listing metric/tool, period, filters and base for each figure, and incident/CA refs used (e.g. "TRIR 0.92 — get_kpis, ANIA-EXP, Sep 2026, all contractors, per 200,000 h").
- AI-4. Answers are scoped to the user's permissions; if the user asks for out-of-scope data the AI says it has no access (no hints whether data exists).
- AI-5. **No person names, ID numbers, contact details, medical notes or observer identities** are ever sent to the model or output by it — for every role, including hse_manager (Phase 0 P6). If asked "who was injured", the AI gives incident/case refs and states that identities are available in the incident register to authorised roles. (See §10 Q9.)
- AI-6. Nationality, age band and trade analyses are available only to hse_manager and hse_officer, as aggregates; groups with < 3 persons are reported as "<3".
- AI-7. Insufficient data: (a) man-hours = 0 → "No man-hours recorded for <scope/period>; rates cannot be calculated"; (b) man-hours < low_exposure_hours → rate given with "low exposure — one case changes the rate by <X>" where X = base ÷ man-hours from T1; (c) data completeness < threshold → caveat stating the %; (d) provisional cases > 0 → caveat; (e) the requested period has no records → say so, do not substitute another period silently.
- AI-8. Trend statements ("increasing/decreasing trend") require ≥ 6 monthly points with man-hours > 0; month-over-month needs both months; YoY needs SPLY man-hours > 0. Otherwise the AI reports the values only and says a trend cannot be established.
- AI-9. Association statements require T9 `sample_sufficient` = true (≥ 10 events in total and ≥ 3 in the higher group ASSUMPTION) **and** p < 0.05; the AI must say "associated with", never "caused by", and mention the exposure basis. Otherwise: "No statistically supported difference (n = …)".
- AI-10. **Analyses the AI must support on demand:** (1) any KPI for any filter/period with comparisons; (2) MoM, YoY, R12 and 3-month moving-average trends for lagging and leading indicators; (3) contractor ranking by TRIR/LTIFR with exposure; (4) breakdowns by mechanism, agency, body part, nature, activity, root cause, site/zone, airside/landside, shift, hour band, weekday, trade, days-on-site band; (5) correlations via T9: heat season vs incidents (incl. heat-illness cases), shift/time of day, contractor, activity, new starters (≤ new_starter_days) vs others, PTW involved vs not, PTW audit band vs incident rate (v1.2, T9 `ptw_audit_band`), overdue-CA count vs repeat events (same mechanism + same contractor within 90 days), Ramadan months vs others; (6) leading-indicator warnings (T13) explained with their inputs; (7) repeat-event detection (same mechanism/agency/contractor ≥ 2 in 90 days) via T4; (8) data-quality summary; (9) monthly report draft.
- AI-11. **Recommendations** must: cite the data each relies on (AI-3); be ordered by the hierarchy of controls (elimination → substitution → engineering → administrative → PPE); include at least one control above `administrative` where one is technically feasible for the hazard; **never recommend PPE alone** where a higher control is feasible; never propose anything that lowers a legal or client requirement; be marked "AI-generated — to be reviewed by a competent person / مُولَّد آلياً — يُراجع من شخص مختص".
- AI-12. The AI does not give medical, legal-liability or disciplinary advice about individuals; regulatory references it cites must come from the platform's spec library and keep any `VERIFY` marker.
- AI-13. Language: answers in the user's UI language (EN/AR); numbers in the project `digits` setting; units and bases always stated.
- AI-14. **Data transfer:** only de-identified, aggregated tool outputs are sent to the AI provider. Because the provider may process outside KSA, enabling AI on a project requires HSE Manager confirmation that the client approved this transfer (Phase 0 P10, `VERIFY` R14); `ai_enabled` stays false until the approval date and approver are recorded. ASSUMPTION
- AI-15. User prompts are scanned before sending; 10-digit IDs (`^[12]\d{9}$`), emails and +966 mobiles are masked and the user warned.
- AI-16. Logging: question, tool calls (name, params), tool result hashes, answer, grounding-check result, model, tokens and latency are logged per turn; retention 12 months ASSUMPTION; visible to hse_manager.
- AI-17. Rate limit: 60 questions/user/day; monthly report generation 10/project/month ASSUMPTION.
- AI-18. If the AI provider is unavailable the dashboard is unaffected; the assistant shows "AI unavailable" — never cached or fabricated answers.
- AI-19. **Monthly report draft** (EN and AR versions; opus model) — numeric tables are rendered by the backend from T1–T17 outputs (v1.4), the model writes narrative only; structure:
  1. Cover: project, month, bases, prepared by (user), status "DRAFT — AI-assisted".
  2. Executive summary (≤ 150 words): headline numbers, LTI-free days/hours, top 3 issues, top 3 positives.
  3. KPI table: each K-metric for month, previous month, SPLY, YTD, R12, target, with Δ.
  4. Manpower & exposure: man-hours and average/peak headcount by contractor and tier; direct vs subcontractor; data completeness.
  5. Lagging indicators: safety pyramid; de-identified list of recordable cases and HiPo events (ref, date, contractor, category, mechanism, short description).
  6. Leading indicators: observations, inspections compliance, toolbox talks, training h/worker, HSE meetings, CA closure; access indicators (K-49, K-53, K-54, K-59, K-57) on projects with `induction_register_from` set; v1.2 PTW indicators K-46, K-46b, K-61, K-64, K-66, K-69 (`3-ptw.md` §6.11); v1.3 certification indicators K-72, K-74, K-76, K-80, K-81 (`4-third-party-cert.md` §6.7, aggregates only); v1.4 section "Training & competence": K-37, K-82…K-88 (`5-training.md` §6.8, aggregates only); warnings E1–E13.
  7. Contractor performance table (MH, TRI, TRIR, LTIFR, NM, unsafe obs, overdue CAs) — ranking only if each contractor's man-hours ≥ low_exposure_hours, else flagged.
  8. Investigations & root-cause themes (counts by ICAM level/code; overdue investigations).
  9. Corrective actions: raised/closed/on-time %, overdue ageing, control-level mix (% engineering-or-higher).
  10. Trends & insights (AI, each with Sources).
  11. Recommendations (AI-11 rules) and focus areas for next month (e.g. heat season, Ramadan hours, night airside works).
  12. Data-quality notes and restatements.
  13. Appendix: definitions and formulas (§6), bases in use.
- AI-20. Report workflow: Draft → Reviewed (hse_officer) → Published (hse_manager). Publishing freezes a snapshot (numbers + text + data hash); later restatements show "figures revised since publication" on the dashboard and in the report view.

### 5.10 Permission matrix — Phase 1 extension (continues Phase 0 §5.10 numbering; legend unchanged: A/P/S/C/C1/R/—)

| # | Capability | HSE Mgr | HSE Officer | Site Eng/Sup | Permit Issuer | Permit Receiver | Contractor HSE Rep | Viewer/Client |
|---|---|---|---|---|---|---|---|---|
| 20 | Create/edit workforce daily returns | A | P | S | — | — | C | — |
| 21 | Import workforce CSV/Excel (dry-run + commit) | A | P | — | — | — | C | — |
| 22 | Verify workforce returns | A | P | — | — | — | — | — |
| 23 | Lock month / unlock (Locked → Verified) | A / A | — | — | — | — | — | — |
| 24 | View workforce returns & man-hours | A | P | S | S | C1 | C | P |
| 25 | Report incident (create, submit) | A | P | S | S | C1 | C | — |
| 26 | Classify cases, set investigation level/lead, void | A | P | — | — | — | — | — |
| 27 | Edit investigation (as lead/team member) | A | P | S (if assigned) | — | — | C (if assigned) | — |
| 28 | Approve investigation / close incident | A (all); L3 only A | P (L1/L2) | — | — | — | — | — |
| 29 | View injured-person identity (name, ID, employee no., GOSI ref) | A | P | — | — | — | C ASSUMPTION (§10 Q3) | — |
| 30 | View medical details (treatments, notes, attachments, absence dates per person) | A | P | — | — | — | — | — |
| 31 | View incident register (de-identified) | A | P | S | S | C1 | C | P |
| 32 | Create observation / close own-scope observation | A / A | P / P | S / S | S / — | C1 / — | C / C | — / — |
| 33 | Manage inspection plans / record inspections | A / A | P / P | — / S | — / — | — / — | — / C | — / — |
| 34 | Create CA | A | P | S | — | — | C | — |
| 35 | Update CA as owner (progress, evidence) | ✓ own | ✓ own | ✓ own | ✓ own | ✓ own | ✓ own | — |
| 36 | Verify/close CA (rule CA-5) | A | P | S (medium/low) | — | — | C (medium/low, not own) | — |
| 37 | Approve CA extension; cancel CA | A | P | — | — | — | — | — |
| 38 | View dashboard & KPIs | A | P | S | S | C1 | C | P |
| 39 | View nationality/age breakdowns | A | P | — | — | — | — | — |
| 40 | Ask AI assistant | A | P | S | S | C1 | C | P |
| 41 | Generate / review / publish monthly report | A / A / A | P / P / — | — | — | — | — | R (published only) |
| 42 | Export incidents/KPIs (de-identified) | A | P | S | — | — | C | P |
| 43 | Export incidents with identity (purpose required) | A | P | — | — | — | — | — |
| 44 | Edit Phase 1 settings & targets; enable AI | A | — | — | — | — | — | — |
| 45 | View anonymous observer identity | A | — | — | — | — | — | — |

Suspended-contractor users keep reads, lose all writes (Phase 0 rule 28).

## 6. Calculations

Notation: MH = Σ man_hours in scope and period (§5.6); B_L = `ltifr_base_hours`; B = `rate_base_hours`; counts are of cases/events eligible per I-4 and K-R2…K-R5. Rounding per K-R8.

### 6.1 KPI catalogue

| ID | Metric (EN / AR) | Formula | Unit / display | Better |
|---|---|---|---|---|
| K-01 | Man-hours / ساعات العمل | Σ man_hours | h, integer | — |
| K-02 | Direct / subcontractor man-hours and share / ساعات المباشر والباطن | Σ by tier class; share = part ÷ K-01 × 100 | h; % 1 dp | — |
| K-03 | Average daily headcount / متوسط العمالة اليومية | Σ headcount ÷ number of distinct dates whose total headcount in scope > 0 | integer | — |
| K-04 | Peak daily headcount / ذروة العمالة | max over dates of Σ headcount | integer | — |
| K-05 | Fatalities / الوفيات | n(FAT) | count | lower |
| K-05b | Permanent disability cases / حالات العجز الدائم | n(permanent_disability ≠ none) | count | lower |
| K-06 | LTIs (incl. fatalities) / الإصابات المضيعة للوقت | n(FAT) + n(LTI) | count | lower |
| K-07 | Restricted work cases / حالات العمل المقيد | n(RWC) | count | lower |
| K-08 | Job transfer cases / حالات النقل | n(JTC) | count | lower |
| K-09 | Medical treatment cases / حالات العلاج الطبي | n(MTC) | count | lower |
| K-10 | Total recordable injuries (TRI) / إجمالي الإصابات المسجلة | n(FAT)+n(LTI)+n(RWC)+n(JTC)+n(MTC) | count | lower |
| K-11 | DART cases / حالات DART | n(LTI)+n(RWC)+n(JTC) (FAT excluded) | count | lower |
| K-12 | First aid cases / حالات الإسعاف الأولي | n(FAC) | count | lower |
| K-13 | Near misses / الحوادث الوشيكة | n(events with near_miss) | count | higher (reporting) |
| K-14 | Dangerous occurrences / الأحداث الخطيرة | n(events with dangerous_occurrence) | count | lower |
| K-15 | Property damage events / أضرار الممتلكات | n(events with property_damage); Σ pd_estimated_cost_sar | count; SAR | lower |
| K-16 | Environmental incidents / الحوادث البيئية | n(events with environmental) | count | lower |
| K-17 | Lost days / أيام العمل الضائعة | Σ days_away (capped, §6.3) over LTI cases + n(FAT ∪ permanent total) × fatality_lost_days_charge | days | lower |
| K-18 | Restricted + transfer days / أيام العمل المقيد والنقل | Σ restricted_days + transfer_days (capped) | days | lower |
| K-20 | **LTIFR** / معدل تكرار الإصابات المضيعة للوقت | K-06 × B_L ÷ MH | per B_L h, 2 dp | lower |
| K-21 | **TRIR (TRCF)** / معدل الإصابات المسجلة | K-10 × B ÷ MH | per B h, 2 dp | lower |
| K-22 | **DART rate** / معدل DART | K-11 × B ÷ MH | per B h, 2 dp | lower |
| K-23 | **LTISR (severity)** / معدل شدة الإصابات | K-17 × B ÷ MH | days per B h, 2 dp | lower |
| K-24 | FA rate / معدل الإسعاف الأولي | K-12 × B ÷ MH | per B h | lower |
| K-25 | NM rate / معدل الحوادث الوشيكة | K-13 × B ÷ MH | per B h | higher |
| K-26 | DO / PD / ENV rates | K-14/K-15/K-16 × B ÷ MH | per B h | lower |
| K-27 | **Near-miss ratio** / نسبة الحوادث الوشيكة إلى الإصابات | K-13 ÷ (K-10 + K-12); denominator 0 → "—" | "x.x : 1" 1 dp ASSUMPTION (§10 Q5) | higher |
| K-28 | **LTI-free days** / أيام بدون إصابة مضيعة للوقت | §6.4 | days | higher |
| K-29 | **LTI-free man-hours** / ساعات بدون إصابة مضيعة للوقت | §6.4 | h | higher |
| K-30 | Observations total / safe / unsafe (acts, conditions) / الملاحظات | counts by obs_type | count | higher |
| K-31 | Safe observation share / نسبة الملاحظات الآمنة | safe ÷ total × 100 | % | higher |
| K-32 | Observation rate / معدل الملاحظات | K-30 total × B ÷ MH | per B h | higher |
| K-33 | Unsafe observation close-out % / نسبة إغلاق الملاحظات غير الآمنة | unsafe with status Closed ÷ unsafe × 100 (observed in period, status at as_of) | % | higher |
| K-34 | **Inspection compliance (on time)** / الالتزام بالتفتيش في الموعد | on_time ÷ D_insp × 100 | % | higher |
| K-35 | Inspection completion (incl. late) / نسبة إنجاز التفتيش | (on_time + late) ÷ D_insp × 100; D_insp = instances with planned_date in period, status ≠ Cancelled, and (Completed or planned_date + grace < as_of) | % | higher |
| K-35b | Inspections done / عدد عمليات التفتيش المنجزة | completed (planned + unplanned) with completed_at in period | count | higher |
| K-36 | Toolbox talks & attendance / اجتماعات التوعية والحضور | Σ toolbox_talks; Σ toolbox_attendees | count | higher |
| K-37 | Training hours per worker / ساعات التدريب لكل عامل | Σ training_hours ÷ K-03. v1.4: per day exactly one source — days d ≥ `training_register_from`: Phase 5 register hours (Closed, not voided sessions' attended minutes ÷ 60 of contractor_worker attendees + sponsored verified external records, `5-training.md` §6.4); earlier days, or setting null: daily-return training_hours. If the period contains register days and |register − daily return| > 5 % of the daily-return sum for those days, the tile shows a reconciliation note ASSUMPTION; chip "n sessions not closed" | h, 2 dp | higher |
| K-38 | Inductions / التعريفات | v1.1: for days d < `induction_register_from` (or when it is null): Σ daily-return inductions; for d ≥ `induction_register_from`: n(Phase 2 induction records with course type `general_site`, result passed, local delivered date = d). Period value = sum over its days. Other induction types are shown as a breakdown, not in the value. If the period contains days ≥ the date and |register − daily return| > 5 % for those days, the tile shows a reconciliation note ASSUMPTION | count | — |
| K-39 | HSE meeting attendance % / نسبة حضور اجتماعات السلامة | Σ attended ÷ Σ invited × 100 (meetings held in period); meetings held ÷ planned × 100 | % | higher |
| K-40 | CAs raised / closed / الإجراءات المنشأة والمغلقة | created_at in period; verified_at in period | count | — |
| K-41 | **CA on-time closure %** / نسبة إغلاق الإجراءات في الموعد | n(due_date in period, ≤ as_of, status Closed, completed_at local date ≤ due_date) ÷ n(due_date in period, ≤ as_of, status ≠ Cancelled) × 100 | % | higher |
| K-42 | **Overdue CAs** / الإجراءات المتأخرة | n(status ∈ {Open, In Progress} and as_of > due_date); ageing buckets 1–7, 8–30, 31–60, > 60 days (days overdue = as_of − due_date) | count | lower |
| K-42b | Verification overdue / تحقق متأخر | n(Pending Verification and as_of > completed_at date + 3) | count | lower |
| K-43 | Control-level mix / توزيع مستويات التحكم | share of CAs (created in period) by control_level; "engineering or higher %" | % | higher |
| K-44 | HiPo events / أحداث عالية الخطورة المحتملة | n(hipo) | count | — |
| K-45 | Data completeness / اكتمال البيانات | reported engagement-site-days ÷ expected × 100; expected = Σ over engagements × engagement.site_ids of days in [max(period start, mobilisation), min(period end, demobilisation, as_of − 1)] | % | higher |
| K-46 | PTW field audits / تدقيقات تصاريح العمل الميدانية | v1.2: n(field audits completed in period), defined in `3-ptw.md` §6.11 | count | higher |
| K-46b | PTW audit coverage / تغطية تدقيق التصاريح | v1.2: distinct permits field-audited ÷ distinct permits live in period × 100, defined in `3-ptw.md` §6.11 | %, 1 dp | higher |
| K-47 | Late reports / البلاغات المتأخرة | n(reported_at − occurred_at > 24 h) | count | lower |

### 6.2 Generic rate (Phase 0 K1)
rate = count × base ÷ MH; MH = 0 → "—"; result rounded half-up to 2 dp at output.

### 6.3 Lost-day counting (per case)
1. Calendar days, not scheduled working days (OSHA 1904.7(b)(3)(iv)); day of injury excluded.
2. days_away = (rtw_date − away_start_date) if rtw_date set; else (as_of + 1 − away_start_date) — i.e. every calendar day from away_start_date to as_of inclusive. away_start_date defaults to injury date + 1.
3. restricted_days = restricted_end − restricted_start + 1 (end = min(end or as_of, as_of)); transfer_days likewise.
4. Cap: days_away = min(days_away, lost_days_cap); restricted_days + transfer_days ≤ lost_days_cap − days_away (combined 180 per OSHA).
5. Once a case reaches the cap it stops accruing and is flagged "capped".
6. Fatality / permanent total disability: days_away for the case is replaced by fatality_lost_days_charge when > 0 (default 0 → the case contributes its actual days away, normally 0).
7. Lost days are attributed to the injury-date period (K-R3).

### 6.4 LTI-free counters
1. Last LTI in scope = latest injury date among counted (I-4) FAT or LTI cases in the filter scope (site/zone/contractor per K-R4/K-R5) on or before as_of.
2. If a last LTI exists: LTI-free days = as_of − last_LTI_date (the LTI day itself = day 0); LTI-free man-hours = Σ man_hours in scope with last_LTI_date < work_date ≤ as_of.
3. If none: run start = latest of project.start_date and, under a contractor filter, the earliest mobilisation_date in scope; LTI-free days = as_of − run_start + 1; man-hours = Σ man_hours with run_start ≤ work_date ≤ as_of; label "since start".
4. as_of default = today (project tz); man-hours for as_of day are included only if returns exist.
5. Reclassification of a case to/from LTI recalculates the counter immediately.
6. Longest LTI-free run (days) in ITD is also returned (informational).

### 6.5 Inspection compliance — see K-34/K-35 (D_insp excludes not-yet-missable pending items).

### 6.6 CA overdue
overdue = status ∈ {Open, In Progress} AND as_of (local date) > due_date (current approved). Days overdue = as_of − due_date.

### 6.7 Period windows
Per K-R10/K-R11. R12 ending 2026-09-30 = 2025-10-01 … 2026-09-30. SPLY of Sep 2026 = Sep 2025. Previous of Sep 2026 = Aug 2026.

### 6.8 Breakdown dimensions
site, zone, zone_type, airside_area, contractor (engagement), tier, activity, mechanism, agency, body_part, nature, case_category, incident type, root-cause ICAM level and code, shift, hour band (2-h bands of occurred_at local), weekday, month, heat_season (in/out), Ramadan (in/out, from Umm al-Qura library), days-on-site band (0–7, 8–30, 31–90, 91–365, > 365), trade, age band*, nationality* (*D-7/AI-6 restricted), observation category, inspection type, control level, CA priority.

### 6.9 Leading-indicator warnings (computed by backend; AI explains)
Evaluated for each complete month M per project (and per tier-1 contractor tree):
- **E1** NM rate(M) ≤ (1 − leading_warning_drop_pct/100) × mean(NM rate of M−3, M−2, M−1) **AND** overdue CAs at end of M ≥ (1 + leading_warning_rise_pct/100) × mean(overdue at end of M−3, M−2, M−1). Means of unrounded values.
- **E2** Inspection compliance K-34 < 80 % in two consecutive months ASSUMPTION.
- **E3** Unsafe share of observations > 40 % in M with ≥ 50 observations ASSUMPTION.
- **E4** ≥ 2 HiPo events in M, or a repeat event (same mechanism + same contractor tree within 90 days).
- **E5–E7** (v1.1, defined in `2-access-permits.md` §6.9): E5 induction coverage K-49 below `induction_coverage_warning_pct`; E6 gate denial rate K-53 ≥ 2 × prior-3-month mean and ≥ 1.00 %; E7 ≥ 1 OFF-05 runway-incursion driving offence or ≥ 3 ADP suspensions in M. Same job, scope (project and tier-1 tree) and alert as E1–E4.
- **E8–E9** (v1.2, defined in `3-ptw.md` §6.12): E8 PTW audit compliance K-61 below `ptw_audit_warning_pct` (≥ 10 field audits) or critical PTW findings K-64 ≥ `ptw_critical_findings_warning`; E9 closure compliance K-69 below `ptw_closure_warning_pct` (≥ 10 ended permits) or a shift-lapse spike K-70. Same job, scope and alert as E1–E4.
- **E10–E11** (v1.3, defined in `4-third-party-cert.md` §6.9): E10 equipment certificate compliance K-72 < `equipment_cert_warning_pct` or personnel certification compliance K-76 < `personnel_cert_warning_pct` or scaffold tag compliance K-81 < `scaffold_tag_warning_pct` (unrounded); E11 ≥ 1 failed certificate verification or category A equipment defects ≥ `dangerous_defect_warning_count` in M. Same job, scope and alert as E1–E4.
- **E12–E13** (v1.4, defined in `5-training.md` §6.9): E12 training matrix compliance K-82 < `training_matrix_warning_pct` (unrounded; not raised when the K-82 denominator is 0); E13 ≥ 1 failed training verification (not_found, details_differ, revoked_by_provider) or ≥ 1 training session voided in M. Same job, scope and alert as E1–E4.

### 6.10 Worked examples (exact expected values — backend unit tests must match)

All W-examples use ANIA-EXP settings: B_L = 1,000,000, B = 200,000, lost_days_cap = 180, fatality_lost_days_charge = 0, inspection_grace_days = 2. All cases are work-related contractor_worker, confirmed, not commuting.

#### W1 — single month, ANIA-EXP, September 2026 (as_of 2026-09-30)

Workforce fixture: every day 2026-09-01 … 2026-09-30 (30 days), shift `all`, Submitted:

| Engagement (tier, parent) | Headcount/day | Man-hours/day | Man-hours Sep |
|---|---|---|---|
| RAWABI (1, —) | 1,200 | 12,000 | 360,000 |
| NAJD (2, RAWABI) | 800 | 8,000 | 240,000 |
| GULFPAVE (2, RAWABI) | 600 | 6,000 | 180,000 |
| SAHARA (3, NAJD) | 300 | 3,000 | 90,000 |
| **Total** | **2,900** | **29,000** | **870,000** |

Incident fixture (occurred dates in Sep 2026):

| # | Date | Type | Employer / responsible | Case data | Category |
|---|---|---|---|---|---|
| 1 | 09-08 | injury | NAJD | fall from scaffold, wrist fracture; away_start 09-09, rtw 09-29 | LTI, days_away 20 |
| 2 | 09-15 | injury | SAHARA | struck by falling object; restricted 09-16 … 09-20 | RWC, restricted 5 |
| 3 | 09-20 | injury | RAWABI | hand laceration, sutures | MTC |
| 4 | 09-22 | injury | GULFPAVE | heat exhaustion, IV fluids, back next shift | MTC |
| 5–10 | various | injury | RAWABI ×3, NAJD ×1, GULFPAVE ×1, SAHARA ×1 | cleaning/plaster only | FAC ×6 |
| 11–34 | various | near miss | RAWABI ×10, NAJD ×6, GULFPAVE ×5, SAHARA ×3 | — | NM ×24 |
| 35–36 | various | property damage | RAWABI ×1, GULFPAVE ×1 | — | PD ×2 |
| 37 | 09-25 | environmental | GULFPAVE | diesel spill 40 L, contained | ENV ×1 |
| 38 | 09-11 | dangerous occurrence | NAJD | rigging failure, load dropped, no injury | DO ×1 |
| 39 | 09-17 | injury, work_related = false | RAWABI | off-duty camp illness | excluded |
| 40 | 09-18 | near miss, Voided (duplicate of #12) | — | — | excluded |

The W1 fixture contains no workforce or incident records outside September 2026; engagement mobilisation dates are those of §A.2.

Expected (scope: ANIA-EXP, all contractors, Sep 2026):

| Metric | Calculation | Expected |
|---|---|---|
| K-01 MH | | **870,000** |
| K-02 direct / sub | 360,000 (41.4 %) / 510,000 (58.6 %) | **41.4 % / 58.6 %** |
| K-03 / K-04 headcount | 87,000 ÷ 30 | **2,900 / 2,900** |
| K-06 LTI | | **1** |
| K-10 TRI | 1 LTI + 1 RWC + 2 MTC | **4** |
| K-11 DART cases | 1 + 1 | **2** |
| K-12 FAC | | **6** |
| K-13 NM | voided #40 excluded | **24** |
| K-14 / K-15 / K-16 | | **1 / 2 / 1** |
| K-17 lost days | | **20** |
| K-18 restricted days | | **5** |
| K-20 LTIFR (per 1,000,000) | 1 × 1,000,000 ÷ 870,000 = 1.149425… | **1.15** |
| K-20 LTIFR if B_L = 200,000 | 1 × 200,000 ÷ 870,000 = 0.229885… | **0.23** |
| K-21 TRIR | 4 × 200,000 ÷ 870,000 = 0.919540… | **0.92** |
| K-22 DART | 2 × 200,000 ÷ 870,000 = 0.459770… | **0.46** |
| K-23 LTISR | 20 × 200,000 ÷ 870,000 = 4.597701… | **4.60** |
| K-24 FA rate | 6 × 200,000 ÷ 870,000 = 1.379310… | **1.38** |
| K-25 NM rate | 24 × 200,000 ÷ 870,000 = 5.517241… | **5.52** |
| K-27 NM ratio | 24 ÷ (4 + 6) = 2.4 | **2.4 : 1** |
| K-28 LTI-free days | 2026-09-30 − 2026-09-08 | **22** |
| K-29 LTI-free man-hours | 22 days (09-09 … 09-30) × 29,000 | **638,000** |

Leading-indicator fixture for the same month: observations 420 safe (300 behaviour + 120 condition), 180 unsafe (60 acts + 120 conditions); 40 planned inspections (34 on time, 3 late, 3 missed) + 2 cancelled + 5 unplanned; 50 CAs due in September (41 Closed with completed_at ≤ due, 9 not), 7 overdue at 09-30; training_hours Σ = 4,350.

| Metric | Calculation | Expected |
|---|---|---|
| K-30 | 600 total / 420 safe / 180 unsafe | **600 / 420 / 180** |
| K-31 | 420 ÷ 600 × 100 | **70.0 %** |
| K-32 | 600 × 200,000 ÷ 870,000 = 137.931… | **137.93** |
| K-34 | 34 ÷ 40 × 100 | **85.0 %** |
| K-35 | 37 ÷ 40 × 100 | **92.5 %** |
| K-35b | 37 + 5 | **42** |
| K-37 | 4,350 ÷ 2,900 | **1.50 h** |
| K-41 | 41 ÷ 50 × 100 | **82.0 %** |
| K-42 | | **7** |

#### W2 — contractor filter, same fixture as W1

| Scope | MH | Cases / events | LTIFR | TRIR | DART | LTISR | FA rate | NM ratio | LTI-free days / MH |
|---|---|---|---|---|---|---|---|---|---|
| RAWABI + subs (= whole project) | 870,000 | as W1 | **1.15** | **0.92** | **0.46** | **4.60** | **1.38** | **2.4 : 1** | **22 / 638,000** |
| NAJD + subs (NAJD, SAHARA) | 330,000 | LTI 1, RWC 1, FAC 2, NM 9, DO 1, lost 20 | 1×1,000,000÷330,000 = **3.03** | 2×200,000÷330,000 = **1.21** | **1.21** | 20×200,000÷330,000 = **12.12** | **1.21** | 9 ÷ 4 = 2.25 → **2.3 : 1** (half-up) | **22 / 242,000** (22 × 11,000) |
| NAJD only | 240,000 | LTI 1, FAC 1, NM 6, DO 1, lost 20 | **4.17** | 1×200,000÷240,000 = **0.83** | **0.83** | **16.67** | **0.83** | 6 ÷ 2 = **3.0 : 1** | **22 / 176,000** |
| RAWABI only | 360,000 | MTC 1, FAC 3, NM 10, PD 1 | **0.00** | **0.56** | **0.00** | **0.00** | **1.67** | 10 ÷ 4 = **2.5 : 1** | no LTI in W1 fixture → since mobilisation 2025-03-01: **579 / 360,000** |
| GULFPAVE | 180,000 | MTC 1, FAC 1, NM 5, PD 1, ENV 1 | **0.00** | **1.11** | **0.00** | **0.00** | **1.11** | **2.5 : 1** | since 2025-04-15: **534 / 180,000** |
| SAHARA | 90,000 | RWC 1, FAC 1, NM 3 | **0.00** | **2.22** | **2.22** | **0.00** | **2.22** | **1.5 : 1** | since 2025-06-01: **487 / 90,000** |

Check: the property-damage, environmental and DO events do not change any injury rate. W2 "since mobilisation" values use the A.2 mobilisation dates; man-hours equal the September rows only because the W1 fixture holds no earlier returns.

#### W3 — multi-month, rolling 12 and comparisons (ANIA-EXP, KPI-engine aggregate test)

Monthly fixture (results do not depend on daily distribution; integration tests may spread each month's MH over its days in any way). FAT = 0 in all months. LTI dates: 2025-09-17 (RAWABI, 12 days away), 2025-12-14 (RAWABI, 9), 2026-05-19 (GULFPAVE, 15), 2026-09-08 (NAJD, 20).

| Month | MH | LTI | RWC | JTC | MTC | FAC | NM | Lost days | TRI | Monthly TRIR | Monthly LTIFR |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2025-09 | 610,000 | 1 | 0 | 0 | 1 | 5 | 14 | 12 | 2 | 0.66 | 1.64 |
| 2025-10 | 640,000 | 0 | 1 | 0 | 1 | 4 | 16 | 0 | 2 | 0.63 | 0.00 |
| 2025-11 | 660,000 | 0 | 0 | 0 | 2 | 6 | 18 | 0 | 2 | 0.61 | 0.00 |
| 2025-12 | 700,000 | 1 | 0 | 0 | 1 | 5 | 20 | 9 | 2 | 0.57 | 1.43 |
| 2026-01 | 720,000 | 0 | 0 | 1 | 1 | 7 | 21 | 0 | 2 | 0.56 | 0.00 |
| 2026-02 | 690,000 | 0 | 1 | 0 | 0 | 4 | 19 | 0 | 1 | 0.29 | 0.00 |
| 2026-03 | 650,000 | 0 | 0 | 0 | 1 | 5 | 17 | 0 | 1 | 0.31 | 0.00 |
| 2026-04 | 760,000 | 0 | 1 | 0 | 2 | 6 | 22 | 0 | 3 | 0.79 | 0.00 |
| 2026-05 | 800,000 | 1 | 0 | 0 | 1 | 7 | 23 | 15 | 2 | 0.50 | 1.25 |
| 2026-06 | 830,000 | 0 | 1 | 0 | 3 | 8 | 20 | 0 | 4 | 0.96 | 0.00 |
| 2026-07 | 850,000 | 0 | 0 | 1 | 2 | 9 | 18 | 0 | 3 | 0.71 | 0.00 |
| 2026-08 | 860,000 | 0 | 1 | 0 | 3 | 7 | 21 | 0 | 4 | 0.93 | 0.00 |
| 2026-09 | 870,000 | 1 | 1 | 0 | 2 | 6 | 24 | 20 | 4 | 0.92 | 1.15 |

Expected aggregates:

| Window | MH | LTI | TRI | DART cases | FAC | NM | Lost days | LTIFR | TRIR | DART | LTISR | FA rate | NM rate | NM ratio |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R12 to Sep 2026 (2025-10-01 … 2026-09-30) | 9,030,000 | 3 | 30 | 11 | 74 | 239 | 44 | **0.33** | **0.66** | **0.24** | **0.97** | **1.64** | **5.29** | 239 ÷ 104 = **2.3 : 1** |
| R12 to Aug 2026 (2025-09-01 … 2026-08-31) | 8,770,000 | 3 | 28 | 10 | 73 | 229 | 36 | **0.34** | **0.64** | **0.23** | **0.82** | **1.66** | **5.22** | **2.3 : 1** |
| YTD 2026 (Jan–Sep) | 7,030,000 | 2 | 24 | 9 | 59 | 185 | 35 | **0.28** | **0.68** | **0.26** | **1.00** | **1.68** | **5.26** | **2.2 : 1** |

R12-to-Sep composition: RWC 6, JTC 2, MTC 19 → TRI = 3 + 6 + 2 + 19 = 30; DART = 3 + 6 + 2 = 11.

Comparisons for TRIR, period = Sep 2026 (current unrounded 0.919540…):

| Comparison | Comparison value (unrounded → display) | Abs Δ | % Δ |
|---|---|---|---|
| Previous (Aug 2026) | 0.930233 → 0.93 | **−0.01** | **−1.1 %** |
| SPLY (Sep 2025) | 0.655738 → 0.66 | **+0.26** | **+40.2 %** |
| R12 to Sep 2026 | 0.664452 → 0.66 | **+0.26** | **+38.4 %** |

Also: LTIFR Sep 2026 vs SPLY = 1.149425 vs 1.639344 → Δ **−0.49**, **−29.9 %**; MH Sep 2026 vs Aug = **+1.2 %**, vs SPLY **+42.6 %**; R12 TRIR to Sep vs R12 to Aug = 0.664452 vs 0.638541 → Δ **+0.03**, **+4.1 %**.

#### W4 — LTI-free counters by filter (W3 LTI dates; as_of 2026-09-30)
Mobilisation dates (seed, §A.2): RAWABI 2025-03-01, NAJD 2025-05-01, GULFPAVE 2025-04-15, SAHARA 2025-06-01; project start 2025-03-01.

| Scope | Last LTI | Expected LTI-free days |
|---|---|---|
| ANIA-EXP (all) | 2026-09-08 | **22** |
| NAJD + subs | 2026-09-08 | **22** |
| RAWABI only | 2025-12-14 | **290** |
| GULFPAVE | 2026-05-19 | **134** |
| SAHARA (no LTI ever) | — (since mobilisation 2025-06-01) | 2026-09-30 − 2025-06-01 + 1 = **487** |
| Longest ITD run, ANIA-EXP | 2026-05-19 → 2026-09-08 | **112** days |

(Hours for these scopes are asserted only in W1/W2 where daily rows are defined.)

#### W5 — lost-day counting

| # | Case | as_of | Expected |
|---|---|---|---|
| a | Injury 2026-09-08, away from 09-09, rtw 2026-09-29 | any ≥ 09-29 | days_away **20**; LTI |
| b | Injury 2026-09-22, still away | 2026-09-30 | days_away **8** (09-23 … 09-30); LTI open |
| b′ | same case | 2026-10-31 | **39** |
| b″ | same case, rtw 2026-10-12 recorded | any | **19** (09-23 … 10-11); all 19 attributed to Sep 2026 (K-R3) |
| c | Injury 2026-01-05, still away | 2026-09-30 | raw 268 → capped **180**, flag "capped" |
| d | Injury 2026-06-01, away 06-02 … 06-11 (rtw 06-12), then restricted 06-12 … 07-11 | any ≥ 07-11 | days_away **10**, restricted **30**; category **LTI** (most severe wins) |
| e | Injury 2026-09-10 14:00, sent home, back for full next shift 09-11 | any | days_away **0** → not LTI; category from treatment (e.g. MTC if sutures) |
| f | Fatality 2026-03-03 | any | FAT; K-06 +1; K-10 +1; K-11 +0; lost days **0** with default charge; **6,000** if fatality_lost_days_charge = 6000 |
| g | Restricted 2026-09-25 … open (no end) | 2026-09-30 | restricted_days **6** (09-25 … 09-30) |

#### W6 — rounding half-up (RBT-52, R12 to Sep 2026)
RBT-52 settings: B_L = 200,000, B = 200,000. MH R12 = 1,600,000; cases: 1 MTC, 0 LTI.
TRIR = 1 × 200,000 ÷ 1,600,000 = 0.125 → **0.13** (banker's rounding would give 0.12 — wrong). LTIFR = **0.00** (per 200,000 h).

#### W7 — inspection pending exclusion
Plan weekly, planned_date 2026-09-09, grace 2. Period MTD as_of 2026-09-10, not completed → excluded from D_insp (09-09 + 2 = 09-11 ≥ as_of). On 2026-09-12 still not completed → status Missed, included: compliance for that single item **0.0 %**. Completed 2026-09-11 → on time; completed 2026-09-12 → late (counts in K-35 not K-34).

#### W8 — corrective actions (as_of 2026-09-30, period Sep 2026)

| CA | Due | State at as_of | completed_at | In K-41 denominator | In K-41 numerator | Overdue (days) |
|---|---|---|---|---|---|---|
| CA-1 | 09-10 | Closed | 09-09 | yes | yes | — |
| CA-2 | 09-15 | Closed | 09-18 | yes | no (late) | — |
| CA-3 | 09-20 | In Progress | — | yes | no | yes (10) |
| CA-4 | 09-25 | Pending Verification | 09-24 | yes | no (not yet Closed) | no |
| CA-5 | 09-28 | Cancelled | — | no | — | — |
| CA-6 | 10-05 | Open | — | no (due after period) | — | no |
| CA-7 | 08-31 | Open | — | no (due before period) | — | yes (30) |

Expected: K-41 = 1 ÷ 4 = **25.0 %**; K-42 = **2** (both in the 8–30 bucket); K-42b = **1** (CA-4: as_of 09-30 > 09-24 + 3 = 09-27).

## 7. Alerts & expiries

| Trigger | Recipient | Timing | Channel |
|---|---|---|---|
| FAT, permanent disability, DO, HiPo, or airside flag runway_incursion/aircraft_involved reported | HSE Manager; HSE Officers of project; Contractor HSE Rep of responsible tree; Viewer/Client (summary, no names) | Immediately on Reported | Email + in-app + SMS (FAT/HiPo) ASSUMPTION |
| LTI / RWC / JTC / MTC reported | HSE Officers; HSE Manager; Contractor HSE Rep | Immediately | Email + in-app |
| FAC / NM / PD / ENV reported | HSE Officers; Contractor HSE Rep | Immediately (in-app); daily digest email 18:00 | In-app, email digest |
| Incident still Reported (not classified) | HSE Officers; then HSE Manager | 24 h; 48 h escalation | In-app + email |
| External notification due (I-20) | HSE Officer; Contractor HSE Rep; HSE Manager at overdue | At creation; 24 h before due; at due | In-app + email |
| Investigation due | lead investigator; HSE Officer | 2 days before due; at due; every 3 days overdue; HSE Manager at 7 days overdue | In-app + email |
| L3 preliminary report not filed | lead; HSE Manager | 48 h after occurrence | In-app + email |
| Open LTI case without rtw_date | HSE Officer | Every 7 days; at cap | In-app |
| Case category change in Locked month (restatement) | HSE Manager | Immediately | In-app + email |
| CA assigned | owner | Immediately | In-app + email |
| CA due | owner | 3 days before; on due date | In-app + email |
| CA overdue | owner + owner's Contractor HSE Rep; HSE Officer at 7 days overdue; HSE Manager at 30 days | Daily 07:00 while overdue | In-app + email (digest) |
| CA pending verification | verifier | Immediately; reminder at 3 days | In-app |
| High-risk unsafe observation without CA | HSE Officer; Contractor HSE Rep | 24 h after submission | In-app |
| Daily return missing | Contractor HSE Rep of engagement; HSE Officer after 2 consecutive days | At daily_return_deadline | In-app + email |
| Data completeness < threshold for previous month | HSE Officer; HSE Manager | 3rd day of month | In-app |
| Month lock approaching | HSE Officers; Contractor HSE Reps | 3 days before month_lock_day | In-app |
| Inspection due / missed | assignee; HSE Officer on Missed | On planned date 07:00; at Missed | In-app |
| Leading-indicator warning E1–E13 raised | HSE Manager; HSE Officers; Contractor HSE Rep of affected tree | Monthly job on 2nd day of month | In-app + email |
| LTI-free milestone (1, 2, 5, 10 million h; 100/365 days) | HSE Manager; HSE Officers | On reaching | In-app |
| Monthly report draft ready | HSE Officer; HSE Manager | When generated | In-app |
| Import committed with warnings | HSE Officers (verifiers) | On commit | In-app |

Alert texts never contain injured names (P6); they contain the incident ref and category.

## 8. Reports / KPIs fed

### 8.1 Dashboard layout (desktop; stacks on mobile; mirrors in RTL)
1. **Filter bar** (D-2) + period/comparison selector + data completeness chip + "provisional n" chip.
2. **Headline band:** LTI-free days and man-hours (K-28/K-29), man-hours period and ITD (K-01), average/peak headcount (K-03/K-04), direct/sub split (K-02).
3. **Lagging tiles** (value, comparison Δ, sparkline 12 months): FAT (K-05), LTI (K-06), LTIFR (K-20), TRI (K-10), TRIR (K-21), DART (K-22), LTISR (K-23), MTC (K-09), FAC + FA rate (K-12/K-24), NM + NM rate (K-13/K-25), DO (K-14), PD (K-15 incl. SAR), ENV (K-16), HiPo (K-44).
4. **Leading tiles:** observations total + safe % (K-30/K-31), observation rate (K-32), inspection compliance (K-34/K-35), toolbox talks & attendance (K-36), training h/worker (K-37), HSE meeting attendance (K-39), CA on-time closure (K-41), overdue CAs (K-42), NM ratio (K-27); v1.2 PTW tiles per `3-ptw.md` §8.1: K-46 PTW field audits with K-46b coverage chip, K-61, K-64, K-66, K-69; v1.3 certification tiles per `4-third-party-cert.md` §8.1: K-72, K-76, K-74 (with A-defects chip), K-80, K-81; v1.4 training tiles per `5-training.md` §8.1: K-82, K-83, K-84 (hook-code gaps chip), K-88 (K-85 chip); the K-37 tile shows its source (Training register / Daily returns / Mixed).
   **PTW band** (v1.2): live permit board per `3-ptw.md` §8.1 (2).
   **Certification band** (v1.3): per `4-third-party-cert.md` §8.1 (2).
   **Training band** (v1.4): per `5-training.md` §8.1 (2).
5. **Charts:**
   - C1 Man-hours by month, stacked tier 1/2/3, with average headcount line.
   - C2 Monthly TRIR (bars) + R12 TRIR and R12 LTIFR (lines) + target line if set.
   - C3 Events by type by month (stacked: LTI, RWC+JTC, MTC, FAC, NM, DO, PD, ENV).
   - C4 **Safety pyramid** (period): FAT → LTI → RWC+JTC → MTC → FAC → NM → unsafe observations (acts + conditions), counts with each layer's ratio to TRI.
   - C5 Leading trends: safe vs unsafe observations by month; inspection compliance % line; CA overdue count bars.
   - C6 **Contractor league table:** engagement, tier, MH, TRI, TRIR, LTIFR, LTI-free days, NM, unsafe obs, CA on-time %, overdue CAs; sortable; contractors with MH < low_exposure_hours flagged "low exposure".
   - C7 Breakdowns (switchable dimension, §6.8): mechanism, agency, body part, nature, activity, root cause, site/zone, airside vs landside, shift, hour band, weekday, days-on-site band.
   - C8 Heat-season view: injury cases and heat-related cases by month with heat_season band shading.
   - C9 CA ageing (buckets) and control-level mix.
   - C13–C15 (v1.2, `3-ptw.md` §8.1): permits issued by month by type; K-61 with K-64; non-routine suspensions by reason.
   - C16–C18 (v1.3, `4-third-party-cert.md` §8.1): K-72 and K-76 by month with E10 reference lines; defects by month A/B/C with K-80; certificate expiry profile next 90 days.
   - C19–C21 (v1.4, `5-training.md` §8.1): K-82 and K-83 by month with the E12 reference line; training person-hours by month by course category with K-37 as a line; training expiry profile next 90 days (booked / not booked).
6. **Action panel** (counts, each opens a pre-filtered list): overdue CAs (by contractor); CAs pending verification > 3 days; investigations overdue; incidents unclassified > 24 h; external notifications due/overdue; open LTI cases without rtw_date; missed inspections (last 7 days); missing daily returns (yesterday); high-risk unsafe observations without CA; leading warnings E1–E13 active; v1.1: Phase 2 access items (`2-access-permits.md` §8.3); v1.2: Phase 3 PTW items (`3-ptw.md` §8.3); v1.3: Phase 4 certification items (`4-third-party-cert.md` §8.3); v1.4: Phase 5 training items (`5-training.md` §8.3).
   **Expiring-items panel** (`GET /dashboard/expiring-items`): kinds ca_due, investigation_due, external_notification_due, inspection_planned, month_lock and, v1.1, induction_expiry, reinduction_due, worker_id_expiry, airport_pass_expiry, bg_recheck_due (hse_manager/hse_officer only), adp_expiry, adp_suspension_end, avp_expiry, vehicle_document_expiry, wap_expiry, notam_expiry, obstacle_clearance_expiry, pass_return_due and, v1.2, ptw_valid_to, ptw_shift_end, gas_retest_due, fire_watch_end, gas_detector_calibration_due, ptw_appointment_expiry, isolation_review_due, jsa_template_review_due (`3-ptw.md` §8.2) and, v1.3, equipment_cert_expiry, personnel_cert_expiry, scaffold_inspection_due, defect_rectification_due, tpi_accreditation_expiry, tpi_client_approval_expiry, certificate_verification_due, hook_block_date (`4-third-party-cert.md` §8.2; v1.4 also for kind training_course) and, v1.4, training_record_expiry, training_refresher_due, trainer_authorisation_expiry, training_provider_accreditation_expiry, training_verification_due, training_session_close_due (`5-training.md` §8.2); item fields and name rules per `2-access-permits.md` §8.2.
7. **AI panel:** "Ask about your HSE data" input, suggested questions, and "Draft monthly report" button (capability 41).

### 8.2 Feeds to later phases
Incidents with agency crane_lifting_gear, mewp or scaffold prompt the investigator to link or raise a Phase 4 defect (v1.3, `4-third-party-cert.md` DF-9; no Phase 1 field changes, the defect stores the incident ref); incidents' ptw_ids (v1.2: Phase 3 links PTW; "PTW audit performance vs incidents" via T9 `ptw_audit_band`); trade/days_on_site (Phase 5 training gaps); contractor KPIs (Phase 6 contractor scoring); heat cases (Phase 6 heat stress).

## 9. Acceptance criteria

**Workforce & import**
1. **Given** W1 workforce fixture **When** KPIs for ANIA-EXP Sep 2026 are requested **Then** K-01 = 870,000, direct 41.4 %, subcontractor 58.6 %, K-03 = 2,900.
2. **Given** a return for (2026-09-14, S-AIR, no zone, GULFPAVE, night) exists **When** a second identical key is saved manually **Then** it is rejected `DUPLICATE_RETURN`.
3. **Given** a CSV with 100 valid rows and 1 row with headcount 10 and man_hours 200 **When** dry-run **Then** the report shows rows_error = 1 with code E08 on that row number, nothing is written, and commit is refused.
4. **Given** a dry-run with 0 errors and 2 W01 warnings **When** committed within 60 min **Then** all rows are inserted as Submitted, the batch status is committed, and the warnings are stored.
5. **Given** a dry-run 61 min old **When** commit is called **Then** it is rejected `IMPORT_EXPIRED`.
6. **Given** mode insert_only and a row whose key exists **Then** E10; **Given** mode upsert and the existing row is Verified **Then** it is replaced, becomes Submitted, and audit holds before/after.
7. **Given** August 2026 is Locked **When** any import row has work_date in August **Then** E11 in either mode.
8. **Given** Contractor HSE Rep Ahmed (RAWABI + subs) **When** he imports a row for QIMMA or for a contractor outside his tree **Then** E12 (QIMMA additionally E01/E04 as applicable); a row for SAHARA is accepted.
9. **Given** an Excel file with Arabic headers (`تاريخ_العمل`, `رمز_المقاول`…) and shift `ليلية` **When** dry-run **Then** it parses identically to the English template.
10. **Given** a row with no_work = Y and headcount 5 **Then** E13.
11. **Given** a return for DLIFT (Suspended) entered by HSE Officer **Then** it is accepted with W03; **Given** a DLIFT user tries to submit **Then** 403 `CONTRACTOR_SUSPENDED`.
12. **Given** a Locked row corrected by HSE Manager with reason **Then** the month shows "restated" in KPI responses and the audit log has before/after.

**Incidents & classification**
13. **Given** a case with treatments [wound_cleaning, wound_covering_steristrips] only **Then** derived category = FAC; adding `sutures_staples_glue` changes it to MTC.
14. **Given** a case with nature fracture and treatments [temporary_immobilisation_transport] only **Then** derived category = MTC (significant diagnosed injury).
15. **Given** W5 case d **Then** category = LTI, days_away = 10, restricted_days = 30.
16. **Given** W5 case e **Then** days_away = 0 and category ≠ LTI.
17. **Given** W5 cases a, b, b′, b″, c, g **Then** day counts equal 20, 8, 39, 19, 180 (flag capped), 6.
18. **Given** W5 case f with default settings **Then** K-06 and K-10 increase by 1, K-11 does not, lost days 0; **When** fatality_lost_days_charge = 6000 **Then** lost days 6,000.
19. **Given** an incident with types [near_miss, property_damage] **When** submitted **Then** rejected `NEAR_MISS_EXCLUSIVE`.
20. **Given** an incident of type injury_illness with no case **When** Draft → Reported **Then** rejected.
21. **Given** W1 incident #39 (work_related = false) and #40 (Voided) **Then** neither appears in any W1 count or rate, and #39 is listed as "excluded from rates — off_duty_camp".
22. **Given** a commuting case with default settings **Then** it is excluded from TRIR but a GOSI notification is required (I-20).
23. **Given** potential_severity 4 on a near miss **Then** hipo = true and minimum investigation level = L3; attempting L2 is rejected.
24. **Given** an L3 incident whose linked CAs are all administrative/ppe **When** the approver approves without justification **Then** rejected `HIGHER_CONTROL_REQUIRED` (I-17).
25. **Given** an incident in Actions Pending **When** its last open CA is Closed **Then** the incident becomes Closed automatically.
26. **Given** an incident Voided with reason **Then** it is excluded from KPIs and still visible in the register filter "Voided".
27. **Given** occurred_at 2026-09-10 08:00 and reported_at 2026-09-11 09:00 **Then** "late report" flag and K-47 +1.
28. **Given** a case classified FAC in Locked August is changed to MTC **Then** August KPIs show restated = true and HSE Manager receives the alert.

**PDPL**
29. **Given** Site Engineer Omar **When** he opens INC with an injured NAJD worker **Then** the case shows "Person 1 · scaffolder · NAJD" and person_name, id_number, treatments, medical_notes are absent from the API response.
30. **Given** HSE Officer Noura opens the same case **Then** the name and ID (masked `2*******17`) are returned and a `sensitive_field_read` entry lists the fields.
31. **Given** a privacy_case = true **When** Noura opens it **Then** person_name = "Privacy case"; Faisal (HSE Manager) sees the name.
32. **Given** Viewer Sarah exports the incident register **Then** no identity or medical columns exist; **Given** Noura exports with identity **Then** a purpose is required and recorded in the `export` audit entry.
33. **Given** an incident description containing "2000000017" **When** saved **Then** the user sees the possible-ID warning.
34. **Given** a medical attachment **Then** it is served only via a signed URL that expires ≤ 5 min and is never included in bulk exports.
35. **Given** an anonymous observation **When** HSE Officer Noura views it **Then** observer is hidden; Faisal sees it.

**Observations, inspections, CAs**
36. **Given** a high-risk unsafe observation not closed on spot and no CA after 24 h **Then** the alert fires to HSE Officer and Contractor HSE Rep.
37. **Given** W7 **Then** compliance behaves as described (excluded at 09-10; 0.0 % on 09-12 if not done; late vs on-time per completion date).
38. **Given** W1 leading fixture **Then** K-31 = 70.0 %, K-32 = 137.93, K-34 = 85.0 %, K-35 = 92.5 %, K-35b = 42, K-37 = 1.50, K-41 = 82.0 %, K-42 = 7.
39. **Given** W8 **Then** K-41 = 25.0 %, K-42 = 2 (ageing bucket 8–30 = 2), K-42b = 1.
40. **Given** a CA owned by Ramesh **When** Ramesh tries to verify it **Then** rejected `VERIFIER_IS_OWNER`.
41. **Given** a CA with 2 approved extensions **When** a third is requested **Then** rejected; original_due_date unchanged throughout.
42. **Given** a CA moved to Pending Verification without evidence **Then** rejected `EVIDENCE_REQUIRED`.
43. **Given** a CA rejected by the verifier **Then** status In Progress, completed_at null.

**KPI engine**
44. **Given** W1 **Then** all expected values in the W1 tables match exactly (LTIFR 1.15, TRIR 0.92, DART 0.46, LTISR 4.60, FA 1.38, NM rate 5.52, NM ratio 2.4 : 1, LTI-free 22 days / 638,000 h).
45. **Given** W1 and B_L changed to 200,000 **Then** LTIFR = 0.23 and the label reads "per 200,000 h".
46. **Given** W2 **Then** every cell in the W2 table matches, including NM ratio 2.3 : 1 for NAJD + subs (half-up from 2.25).
47. **Given** W2 with "include subcontractors" on and contractor = RAWABI **Then** results equal the whole-project W1 values.
48. **Given** W3 **Then** R12 to Sep 2026, R12 to Aug 2026 and YTD 2026 match the W3 table, and the TRIR comparison table (−0.01/−1.1 %, +0.26/+40.2 %, +0.26/+38.4 %) matches.
49. **Given** W4 **Then** LTI-free days match per scope (22, 22, 290, 134, 487) and longest run = 112.
50. **Given** W6 **Then** RBT-52 R12 TRIR = 0.13.
51. **Given** a scope with man-hours = 0 **Then** every rate is "—" (null + reason `NO_EXPOSURE`), counts still returned.
52. **Given** a zone filter on Z-APR-21 where no man-hours rows carry a zone **Then** rates are "—" with note `NO_ZONE_EXPOSURE`; counts are returned.
53. **Given** a custom period 2026-09-05 … 2026-09-14 **Then** previous period = 2026-08-26 … 2026-09-04 and SPLY = 2025-09-05 … 2025-09-14.
54. **Given** period 2024-02-29 (leap day) **Then** SPLY = 2023-02-28.
55. **Given** "All projects" selected with ANIA-EXP (LTIFR 1,000,000) and RBT-52 (LTIFR 200,000) **Then** the banner states bases 1,000,000/200,000 are used.
56. **Given** any KPI response **Then** it contains value, numerator, denominator, base, completeness and provisional count.
57. **Given** a fixture with 120 expected engagement-site-days and 3 missing **Then** K-45 = 97.5 % and no banner (threshold 95); with 7 missing → 94.2 % and banner shown.
58. **Given** seed data (§A) **Then** warning E1 is raised for ANIA-EXP July 2026 and not for August or September 2026.

**Dashboard**
59. **Given** Contractor HSE Rep Yousef (QIMMA + subs) **When** he opens the RBT-52 dashboard **Then** all tiles reflect QIMMA + DLIFT only, and ANIA-EXP is not selectable.
60. **Given** Permit Receiver Ramesh (NAJD only, C1) **Then** the dashboard shows NAJD-only values (W2 row "NAJD only").
61. **Given** Viewer Sarah **Then** no nationality/age breakdown is offered, and no widget contains a person name (e2e scan against the seeded names list).
62. **Given** the UI in Arabic **Then** all tile labels, chart axes and legends are Arabic, layout mirrored, numbers per `digits` setting, base labels present.
63. **Given** the frontend receives a KPI payload **Then** displayed values equal the payload's display values (no client-side recomputation — contract test).
64. **Given** an overdue CA exists **Then** the action panel count equals K-42 and the link opens the filtered CA list.

**AI assistant**
65. **Given** W1 data **When** Noura asks "What was our TRIR in September 2026?" **Then** the answer states 0.92 per 200,000 h, cites get_kpis with scope and period, and the grounding check passes.
66. **Given** a simulated model answer containing a number not present in tool outputs **Then** the grounding check fails, one regeneration is attempted, and on second failure the fallback message and raw table are shown and logged.
67. **Given** Faisal asks "Who was injured on 8 September?" **Then** the answer gives the incident/case ref and states identities are in the register; no name appears; tool payloads sent to the model contain no person_name/id_number fields (log assertion).
68. **Given** Yousef asks about ANIA-EXP **Then** the AI replies it has no access to that data and no ANIA-EXP figures appear in tool results.
69. **Given** a scope with 2 months of data **When** asked "Is TRIR trending up?" **Then** the AI gives both monthly values and states a trend cannot be established (< 6 months).
70. **Given** T9 returns sample_sufficient = false for heat season vs other **Then** the AI says no statistically supported difference and gives n.
71. **Given** T9 returns p = 0.01, sample_sufficient = true for new starters **Then** the AI uses "associated with" (not "caused") and states the exposure basis.
72. **Given** a request for recommendations on falls from scaffolds **Then** every recommendation list contains ≥ 1 control at engineering or higher, is ordered by hierarchy, cites data, carries the AI-generated label, and no item is PPE-only.
73. **Given** ai_enabled = false (no transfer approval recorded) **Then** the assistant is hidden and the API returns `AI_DISABLED`.
74. **Given** a user prompt containing "+966500000123" **Then** it is masked before sending and the user is warned.
75. **Given** the AI provider times out **Then** the dashboard still loads and the assistant shows "AI unavailable".
76. **Given** "Draft monthly report" for ANIA-EXP Sep 2026 **Then** a draft with the 13 sections of AI-19 is produced in EN and AR, its KPI table equals T1 output for Sep 2026 (W3 values), and status is Draft.
77. **Given** a published report and a later restatement of Sep 2026 **Then** the report view shows the frozen numbers with "figures revised since publication".

**Seeds**
78. **Given** seed data loaded **Then** every injured-person id_number matches `^[12]0{5}\d{4}$`, every name carries the seed marker in the `seed_fake=true` column, and ANIA-EXP monthly MH/case counts equal §A.3 exactly.

## 10. Open questions for the HSE Manager

1. **Direct vs subcontractor:** is "direct" = the tier-1 main contractor's own workforce (current assumption), or do you also need client/PMC staff man-hours captured and counted (and their injuries in rates)?
2. **Man-hours granularity:** will contractors report daily per site (assumed), or per zone too (needed for zone-level rates, e.g. airside apron vs taxiway)? Is a weekly/monthly return acceptable for small subcontractors?
3. **Injured-person identity for Contractor HSE Reps:** may a tier-1 rep see names/IDs of injured workers of its subcontractors (needed for GOSI follow-up), or own engagement only?
4. **Lost days:** attribute all lost days to the injury month (assumed, OSHA-300-like) or accrue them in the month they occur? Cap at 180 (OSHA) and fatality charge 0, or does your client use 6,000 days (ANSI Z16.1)?
5. **Near-miss ratio:** NM ÷ (recordables + first aid) (assumed), NM ÷ recordables, or NM per 200,000 h only? Any client target (e.g. ≥ 10 : 1)?
6. **Investigation timelines:** L1 3 days / L2 7 days / L3 14 days with 48 h preliminary report — or your client's procedure values? Property-damage threshold for L2 (SAR 50,000)?
7. **External notification deadlines** your client/contract imposes (client within 24 h? GACA/airport operator immediate?) and confirmation of GOSI 3-day and MHRSD requirements as you apply them.
8. **CA defaults:** due days by priority (1/7/14/30), max 2 extensions, and whether on-time closure should be measured against the original due date instead of the approved extended date.
9. **AI and names:** Phase 0 P6 keeps names out of the AI entirely, even for you. Do you want an exception for HSE Manager/Officer (e.g. "show the cases of worker X"), knowing it means sending identity data to the AI provider?
10. **AI data transfer:** will the client approve sending de-identified aggregated HSE data to the AI provider outside KSA, or must the AI run through a KSA-hosted endpoint? Who signs the approval?
11. **Severity matrix:** adopt the 5-level actual/potential scale in §3.11 S, or load your client's risk matrix and SAR thresholds?
12. **Month lock:** lock on the 10th of the following month (assumed)? Who may unlock besides you?
13. **KPI targets** for ANIA-EXP and RBT-52 (e.g. TRIR ≤ 0.50, LTIFR ≤ 0.30, inspection compliance ≥ 95 %, CA on-time ≥ 90 %) for RAG colouring.
14. **Commuting accidents** (GOSI-covered): exclude from rates (assumed) or include?
15. **Heat season** definition for analysis: 1 Jun–30 Sep (assumed) or the midday-ban dates only (15 Jun–15 Sep)?

---

## Appendix A — Seed data guidance (fictional; all names, IDs, refs fake; `seed_fake = true` on every row)

### A.1 Principles
1. Seeds cover **2025-09-01 … 2026-09-30** (13 months, so SPLY and R12 work), with lighter ramp-up data from project start; all on Phase 0 projects/sites/zones/contractors.
2. Monthly totals for ANIA-EXP must equal the W3 table exactly (the dashboard demo then reproduces W3). Daily distribution is realistic (A.4); the W1 constant-day fixture is a **separate test fixture**, not the seed.
3. Injured-person IDs: Iqama `2000000001`–`2000000999`, National ID `1000000001`–`1000000999` (pattern `^[12]0{5}\d{4}$`, clearly fake); employee numbers `<CODE>-0001…`; GOSI refs `GOSI-TEST-0001…`.
4. Names: fake bilingual pairs from a fixed list, e.g. Imran Hussain / عمران حسين (PK), Rajesh Nair / راجيش ناير (IN), Abdul Karim Mia / عبد الكريم ميا (BD), Mahmoud Fathy / محمود فتحي (EG), Jomar Santos / جومار سانتوس (PH), Suman Tamang / سومان تامانغ (NP), Saad Al-Dosari / سعد الدوسري (SA), Waleed Saleh / وليد صالح (YE), Osman Idris / عثمان إدريس (SD). No real persons.
5. Text fields bilingual where user-facing; descriptions in English for ~70 % and Arabic for ~30 % of records to exercise RTL rendering.

### A.2 Engagement mobilisation (adds to Phase 0 A.3)
RAWABI@ANIA-EXP 2025-03-01 (sites S-AIR, S-LAND) · NAJD 2025-05-01 (S-LAND) · GULFPAVE 2025-04-15 (S-AIR) · SAHARA 2025-06-01 (S-LAND) · QIMMA@RBT-52 2025-01-15 (S-TWR, S-POD) · DLIFT 2025-03-01 (S-TWR), no hours after its suspension 2026-08-15. Project start dates: ANIA-EXP 2025-03-01, RBT-52 2025-01-15 ASSUMPTION.

### A.3 ANIA-EXP monthly targets
Use the W3 table for MH and case counts. Contractor man-hour share per month: RAWABI 41 %, NAJD 28 %, GULFPAVE 21 %, SAHARA 10 % (rounding remainder to RAWABI); Sep 2026 exactly as W1 (360,000 / 240,000 / 180,000 / 90,000). LTIs: dates and contractors per W3/W4. Other monthly counts:

| Month | Obs (safe/unsafe) | Insp planned / on time / late / missed | CAs raised | CA overdue at month end | DO | PD | ENV | TBT talks |
|---|---|---|---|---|---|---|---|---|
| 2025-09 | 300/150 | 32/26/3/3 | 38 | 4 | 0 | 1 | 0 | 380 |
| 2025-10 | 320/150 | 34/29/2/3 | 40 | 3 | 1 | 1 | 1 | 400 |
| 2025-11 | 330/150 | 34/30/2/2 | 41 | 3 | 0 | 2 | 0 | 410 |
| 2025-12 | 350/160 | 36/31/3/2 | 44 | 4 | 0 | 1 | 1 | 430 |
| 2026-01 | 360/160 | 36/32/2/2 | 45 | 3 | 1 | 1 | 0 | 440 |
| 2026-02 | 340/150 | 36/30/3/3 | 42 | 3 | 0 | 2 | 0 | 420 |
| 2026-03 | 320/140 | 36/29/3/4 | 40 | 3 | 0 | 1 | 1 | 400 |
| 2026-04 | 380/170 | 38/33/2/3 | 47 | 3 | 1 | 2 | 0 | 470 |
| 2026-05 | 390/170 | 38/33/3/2 | 48 | 4 | 0 | 1 | 1 | 480 |
| 2026-06 | 380/180 | 40/32/4/4 | 50 | 6 | 0 | 2 | 1 | 490 |
| 2026-07 | 350/190 | 40/30/4/6 | 49 | 9 | 1 | 1 | 0 | 480 |
| 2026-08 | 370/190 | 40/31/4/5 | 52 | 11 | 0 | 2 | 1 | 500 |
| 2026-09 | 420/180 | 40/34/3/3 | 55 | 7 | 1 | 2 | 1 | 520 |

(July 2026 values are chosen so E1 fires: NM rate 4.24 vs prior-3-month mean 5.45 = −22.3 %; overdue 9 vs mean 4.33 = +107.7 %. August: NM −1.0 % → no E1. September: NM +18.8 % → no E1.)

### A.4 Daily realism rules for the generator
1. Working week Sat–Thu; Fridays ≈ 15 % of a normal day's hours (critical works only).
2. Ramadan (from Umm al-Qura library; ≈ 2025-03-01…03-29 and 2026-02-18…03-19) — 6 h/person/day for 60 % of workers (Muslim workers, Labour Law), others 8 h ASSUMPTION; Eid al-Fitr and Eid al-Adha: 4 days `no_work` for most engagements.
3. Midday ban 15 Jun–15 Sep: outdoor engagements (GULFPAVE, part of RAWABI S-AIR) shift hours to early morning/night; GULFPAVE ≈ 60 % night shift on S-AIR year-round (airside works windows).
4. Ensure month totals hit A.3 exactly: distribute, then add the rounding remainder to the last working day.
5. Data-completeness demo: leave 3 GULFPAVE engagement-days missing in Jul 2026 (ANIA-EXP July 152 ÷ 155 = 98.1 % → no banner; GULFPAVE-filtered July 28 ÷ 31 = 90.3 % → banner). Expected engagement-site-days for ANIA-EXP in a 31-day month = RAWABI 2 sites × 31 + NAJD 31 + GULFPAVE 31 + SAHARA 31 = 155. Month totals still hit A.3 (hours per day stay within the E08 limit).

### A.5 Incident distribution patterns (so AI analyses find something)
1. Heat: 60 % of Jun–Sep MTCs are heat_exhaustion with mechanism exposure_heat, mostly GULFPAVE/RAWABI on S-AIR, hour band 10–12 and 15–17; ambient_temp_c 42–47.
2. New starters: 35 % of injury cases with days_on_site ≤ 30 (vs ≈ 10 % of workforce) — T9 should flag association.
3. Night shift: airside NM/PD events concentrated on GULFPAVE night shift (FOD, GSE/vehicle damage) with airside_flags fod_event / airside_vehicle_incident.
4. Mechanism mix (all injury cases): slip/trip 22 %, struck by falling object 15 %, manual handling 14 %, caught in/between 10 %, fall from height 9 %, struck against 9 %, heat 12 %, other 9 %.
5. Root causes on L2/L3: OF-04 supervision and TE-08 new to task most frequent; AD-01 edge protection on the Sep 2026 LTI.
6. Key named fake incidents (descriptions EN/AR):
   - INC-ANIA-EXP-2026-0147 — 2026-09-08 09:40, NAJD scaffolder (fake Imran Hussain, Iqama 2000000017, days_on_site 14), fall from scaffold working platform at Pier B grid C-14, right wrist fracture, LTI 20 days, L3 ICAM, root causes AD-01, OF-04, TE-08; CAs: engineering — install double guardrails/toe-boards (high), administrative — scaffold inspection tagging re-briefing (medium).
   - INC-ANIA-EXP-2026-0093 — 2026-05-19 23:15 night, GULFPAVE plant operator, caught between paver and kerb on Taxiway B strip, LTI 15 days, airside_flags [airside_vehicle_incident].
   - INC-ANIA-EXP-2025-0201 — 2025-12-14, RAWABI labourer, struck by falling formwork panel, LTI 9 days.
   - INC-ANIA-EXP-2026-0121 — 2026-07-22, GULFPAVE, near miss FOD (loose bolts) found on Apron stand 23 during live operations, HiPo potential 4, airside_flags [fod_event], notifications airport_operator.
   - INC-ANIA-EXP-2026-0150 — 2026-09-11, NAJD dangerous occurrence: sling failure, 1.2 t steel beam dropped in exclusion zone, no injury, L3.
7. RBT-52: R12 to Sep 2026 MH = 1,600,000 (monthly 120k, 125k, 130k, 130k, 135k, 135k, 135k, 140k, 140k, 140k, 135k, 135k for Oct 2025…Sep 2026), 1 MTC (2026-03-10, QIMMA, hand laceration), FAC 1–3/month, NM 4–8/month, no LTI since project start (LTI-free since 2025-01-15).

---

### Change log
- v1.0 (2026-10-05) — first issue.
- v1.1 (2026-10-06) — changes required by Phase 2 (`2-access-permits.md` v1.0); no existing rule, formula or worked example changes value: (1) §3.4 optional `worker_id` on injury case; (2) §3.10 new setting `induction_register_from` and §6.1 K-38 counts passed `general_site` induction-register records from that date (daily returns before it; null = daily returns only, so W-examples are unchanged); (3) §8.1 expiring-items panel gains 13 Phase 2 kinds and the action panel Phase 2 items; (4) §5.9 AI tool T14 `get_access_kpis`, T13 returns E5–E7, monthly report uses T1–T14; (5) §6.9/§7/§8.1 warnings E5–E7.
- v1.2 (2026-10-07) — changes required by Phase 3 (`3-ptw.md` v1.0 §11); no existing rule, formula or worked example changes value: (1) §6.1 K-46 defined as PTW field audits and K-46b coverage added (both per `3-ptw.md` §6.11); §1 out-of-scope no longer lists PTW audits; (2) §3.5 investigation `ptw_ids`, `ptw_involved` derived from it, `ptw_ref` legacy read-only; §8.2 updated; (3) §3.8 CA source_type `ptw_audit`; (4) §5.9 AI tool T15 `get_ptw_kpis`, T13 returns E8–E9, T9 dimension `ptw_audit_band`, T4/T5 linked permit numbers and types, AI-10 (5) PTW audit band vs incident rate, AI-19 PTW indicators and T1–T15; (5) §6.9 warnings E8–E9, §7 alert row E1–E9; (6) §8.1 PTW tiles replace the K-46 placeholder, PTW band, charts C13–C15, Phase 3 expiring-item kinds and action-panel items.
- v1.3 (2026-10-08) — changes required by Phase 4 (`4-third-party-cert.md` v1.0 §11.2); no existing rule, formula or worked example changes value: (1) §3.8 CA source_type `equipment_defect` (manual only); (2) §5.9 AI tool T16 `get_certification_kpis`, T13 returns E10–E11, AI-19 certification indicators and T1–T16; (3) §6.9 warnings E10–E11, §7 alert row E1–E11; (4) §8.1 certification tiles and band, charts C16–C18, Phase 4 expiring-item kinds and action-panel items; (5) §8.2 incident → defect prompt.
- v1.4 (2026-10-08) — changes required by Phase 5 (`5-training.md` v1.0 §11.2); the W1/W2 fixtures have `training_register_from` null, so no existing worked example or AC changes value (AC38 K-37 = 1.50 holds): (1) §3.10 setting `training_register_from`; (2) §6.1 K-37 per-day source switch, reconciliation note and "sessions not closed" chip; (3) §3.2 import warning W07; (4) §5.9 AI tool T17 `get_training_kpis`, T13 returns E12–E13, T9 dimension `training_gap_at_event`, AI-19 training section and T1–T17; (5) §6.9 warnings E12–E13, §7 alert row E1–E13; (6) §8.1 training tiles and band, charts C19–C21, Phase 5 expiring-item kinds and action-panel items.
- v1.5 (2026-10-09) — changes required by Phase 6b (`6b-heat-stress.md` v1.0 §11.2); no existing rule, formula, worked example or KPI value changes: (1) §3.8 CA source_type `heat_check` (source_id = welfare check or patrol); (2) §5.9 AI tool T19 `get_heat_stress_kpis` (6b HM-2), T13 returns E16–E17, T9 dimensions `wbgt_regime_at_event` and `acclimatisation_at_event`, AI-19 section "Heat stress" (aggregates); (3) §6.9 / §7 warnings E16–E17 (6b §6.8), same monthly job and recipients; (4) §8.1 heat tiles (K-97, K-99 + K-100 chip, K-101, K-103), heat band, charts C25–C27, C8 heat-case source from `heat_register_from`; `ExpiringItemKind` `heat_instrument_calibration`, `ban_exemption_end` and the 6b §8.2 action-panel items; (5) seed: the September 2026 GULFPAVE heat-exhaustion case (W1 #4) has zone Z-APR-21 and occurred_at 13:50; Jun–Aug heat cases placed as 6b HS8 requires (W3 counts unchanged). 6b §11 numbers this document as if the 6a §11 changes were applied first; those 6a changes are implemented in the backend but not yet written into this document.
- v1.6 (2026-10-09) — changes required by Phase 6c (`6c-emergency-drills.md` v1.0 §11.2); no existing rule, formula, worked example or KPI value changes: (1) §3.8 CA source_type `emergency` (source_id = 6c asset check, drill or event); (2) §5.9 AI tool T20 `get_emergency_kpis` (6c EM-2), T13 returns E18–E19, AI-19 section "Emergency preparedness"; (3) §6.9 / §7 warnings E18 Preparedness and E19 Response readiness (6c §6.9), same monthly job and recipients; (4) §8.1 tiles K-104…K-107, emergency band, charts C28–C30; `ExpiringItemKind` adds `emergency_drill_due`, `emergency_asset_service`, `emergency_asset_consumable`, `erp_review`, `rescue_team_drill`, and the 6c §8.2 action-panel items; (5) the incident read model shows the linked 6c event number (read only).
- v1.7 (2026-10-09) — changes required by Phase 6d (`6d-field-assurance.md` v1.0 §11.2); the W1/W2 fixtures have both switches null, so no existing rule, worked example, AC or KPI value changes: (1) §3.7 plan gains template_code, rotation (`none` · `zones` · `engagements`), rotation_list and frequency `quarterly`; inspection gains a 6d response link, offline_delay_min and the findings read model from 6d (severity observation → low, minor → medium, major → high, critical → critical); §4.4 Completed → Voided (capability 201); (2) §3.2 import warning W08 (register day); §3.10 settings `inspection_template_required_from` and `toolbox_register_from` (edited through 193); (3) §3.8 CA source_type `field_audit`; (4) §6.1 K-34/K-35/K-35b inputs from checklist responses from the switch date, Voided excluded (6d SRC-1); K-36 per 6d SRC-2 / §6.6 with the reconciliation note; K-110…K-117 by reference; (5) §5.9 AI tool T21 `get_field_assurance_kpis`, T8 adds pooled score and critical fails, T13 returns E20–E21, AI-19 section "Field assurance"; (6) §6.9 / §7 warnings E20 Field assurance and E21 Toolbox engagement (monthly job, same recipients); (7) §8.1 tiles, field band, charts C31–C33; `ExpiringItemKind` adds audit_due, campaign_due, checklist_template_review, toolbox_topic_review and the action-panel items of 6d §8.2.
