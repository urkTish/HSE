# Module Spec — Phase 6g: Contractor HSE Scorecard and Reports Export Pack (monthly weighted score per contractor from existing KPIs, with normalisation, small-number handling, grades, caps, trend, ranking, contractor comment and dispute, watch list and links to contractor status; monthly client HSE report in EN / AR PDF and XLSX, issue / freeze / re-issue, scheduled generation and distribution; one generic register-export mechanism with PDPL masking and purpose rules)

**Version:** v1.0 · **Date:** 2026-10-09 · **Author:** HSE Consultant Agent · **Status:** Draft. The HSE Manager asked us to proceed without waiting for approval and will review the choices later (§10).
**Builds on:**
- `0-foundation.md` v1.2 (v1.3 after 6e): contractor states (§4.2, suspension rule 28), engagements and tiers (§3.5), scoping legend, rule 42 (RTL numbers), rule 48 (error codes), rule 49 (exports), PDPL P1–P13, capability 18.
- `1-dashboard.md` v1.8 (v1.9 after 6f): KPI rules K-R1…K-R15, the KPI catalogue K-01…K-47, D-7 / D-10, P1-1…P1-8, `privacy_case`, month lock (§4.1, `month_lock_day`), AI-19 (monthly report structure) and AI-20 (Draft → Reviewed → Published, frozen snapshot), T1…T13, capabilities 41–43, worked examples W2 and W3.
- Every module KPI catalogue: Phase 2 K-48…K-60, Phase 3 K-61…K-71, Phase 4 K-72…K-81, Phase 5 K-82…K-88, 6a K-89…K-96, 6b K-97…K-103, 6c K-104…K-109, 6d K-110…K-117, 6e K-118…K-126, 6f K-127…K-131. 6g **reads** these values. It never redefines them.
- Earlier export capabilities 42/43, 78/79, 104, 123, 144, 163, 176, 189, 200, 202, 215/222 and `docs/DECISIONS.md` #1–#186, in particular #19 (D-10 PDF deferred), #53 (tier-1 trees) and #78 (export audit).
- `6f-incident-followup.md` v1.0: numbering ends at capability 223, K-131, E24, T24, C38.

**Numbering taken by 6g:** capabilities **224–232**; KPIs **K-132…K-135**; warning **E25**; AI tool **T25**; charts **C39–C40**; CA source_type **`scorecard`**; `ExpiringItemKind` `scorecard_comment_window`, `scorecard_dispute_due`, `scorecard_finalise_due`, `report_pack_due`, `pip_due`.

**Covers (build order):**
1. 6g.1 Scorecard profile: pillars, metrics, weights, anchors, caps, grade bands, source live-from dates.
2. 6g.2 Monthly scorecard computation: normalisation, small-number handling, weight redistribution, score, grade, caps, trend, ranking.
3. 6g.3 Issue for comment, comment and dispute, finalisation, re-issue.
4. 6g.4 Consequences: watch list, improvement plan, suspension review (links to Phase 0), commendation, pre-qualification summary.
5. 6g.5 Report packs: monthly client HSE report (MCR), contractor scorecard pack (SCP), OSHA 300 / 300A-style log, heat season report PDF; issue / freeze / re-issue; schedules; distribution.
6. 6g.6 Generic register export: the dataset registry, column PDPL classes, masking, purpose, files, audit, subscriptions.
7. 6g.7 KPIs, warning, dashboard and AI.

**Not in 6g:**
- New KPIs about site activity. Every input already exists in an earlier module. The four new KPIs (K-132…K-135) measure the scorecard and the reports.
- Changing any earlier KPI formula, attribution rule or rate base.
- Contract money (retention, penalties, back-charges). The scorecard records a recommendation and the HSE Manager's decision. Commercial action stays outside the platform.
- Automatic contractor suspension. The platform proposes. The HSE Manager decides through the Phase 0 transition.
- Electronic submission to the client's systems. Packs are emailed or downloaded.

Conventions: `VERIFY` = clause or number to confirm against the current official text or the client's contract. `ASSUMPTION` = Consultant default; the HSE Manager may override it (§10). "Must" = enforced server-side. Rule prefixes: SP profile, SN small numbers, WR weight redistribution, SG score and grade, RK ranking and visibility, DP comment and dispute, FN finalisation, WL watch list, RP report packs, DL distribution, SC scheduling, EX exports, GK KPIs/AI, P6g- PDPL, BD6g boundary. Error codes are stable strings (Phase 0 rule 48). Times are local Asia/Riyadh.

**The principle that shapes this module:** a contractor's score is only ever arithmetic on records that the contractor can see and dispute. Nobody types a score, and a small contractor is never ranked on luck.

---

## 1. Purpose

The HSE Manager runs a monthly meeting with each main contractor and sends a monthly HSE report to the client. Today both are assembled by hand from twelve dashboards. The contractor table in the Phase 1 monthly report ranks firms on TRIR alone, so a 40-person subcontractor with one cut finger looks worse than a 900-person firm with an overdue-CA backlog and lapsed crane certificates. Contractors argue about numbers they never saw. A firm that gets worse month after month is noticed only after the incident. The client wants a PDF in English and Arabic, a spreadsheet, and the same figures next month even if a case is reclassified later. Every module since Phase 2 has parked its register exports and PDFs ("6g export pack").

Phase 6g provides:
- a **configurable weighted scorecard** per contractor engagement per month, built only from existing lagging and leading KPIs. Rates are normalised per exposure hours or headcount. Small exposure is blended with the project rate. Missing modules are excluded and their weight is redistributed. The result is a score from 0 to 100, a grade A–D, caps for fatalities, LTIs and statutory breaches, a trend and a ranking;
- a monthly cycle: **issued for comment → disputes resolved → Final** (frozen), with re-issue when data are restated;
- **consequences**: watch list → improvement plan (CAs) → suspension review that hands over to the Phase 0 contractor transition; a commendation for sustained grade A; and a 12-month pre-qualification summary;
- **report packs**: the monthly client HSE report (EN PDF, AR PDF, XLSX) assembled from the published Phase 1 monthly report, the module sections and the Final scorecards; scorecard packs for each contractor; an OSHA 300 / 300A-style annual log; the heat-season PDF. Each pack has document numbering, an issue / freeze / re-issue cycle, schedules and a distribution log;
- **one export mechanism** for every register, with column-level PDPL classes, masking, a recorded purpose, audit, expiring files and subscriptions. It delivers the exports that earlier phases parked;
- KPIs K-132…K-135, warning E25, AI tool T25 and charts C39–C40.

## 2. Regulatory basis

| # | Source | What it drives here |
|---|---|---|
| R1 | **ISO 45001:2018** cl. 8.1.4 (procurement, contractors: criteria for evaluating and selecting contractors, coordination), cl. 9.1 (monitoring, measurement, analysis and performance evaluation), cl. 9.3 (management review inputs) | Scorecard exists and covers both leading and lagging indicators; pre-qualification summary |
| R2 | **Client contract / HSE plan** (PMC contractor-management procedure; Saudi Aramco CSM contractor HSE performance evaluation where flowed down `VERIFY`; airport-operator contractor HSE requirements `VERIFY`): monthly HSE report to the client by a set day, contractor performance evaluation, escalation to warning letter / improvement plan / removal | Report due day, distribution, watch-list levels, suspension review |
| R3 | **MHRSD OSH regulations** and the **Labour Law**: the main employer's duty to coordinate safety with contractors on the same site `VERIFY` article | Scorecards cover every tier; tier-1 trees roll up (RK-3) |
| R4 | **OSHA 29 CFR 1904** (benchmark, as Phase 1): 300 log columns, 300A summary, privacy cases 1904.29(b)(6)–(9), annual summary posting | OSHA 300 / 300A-style log (RP-9); privacy-case masking |
| R5 | **ANSI / ASSP Z16.1**, ILO and OSHA rate conventions (per 200,000 h / 1,000,000 h) | Canonical bases for anchors (SP-4); normalisation |
| R6 | **PDPL** and its Implementing Regulations: purpose limitation, minimisation, disclosure to third parties, records of processing; cross-border transfer rules (Phase 0 P10 `VERIFY`) | Export purposes, masking, external distribution of de-identified aggregates only, file expiry |
| R7 | **Saudi Contractors Authority** classification / contractor evaluation `VERIFY` whether HSE performance data are requested | None in v1.0. The pre-qualification summary can be printed for it |
| R8 | **Hijri calendar** for formal letters (Phase 0 rule 34) | Report cover shows Umm al-Qura date when `show_hijri` |

Strictest-wins in this spec (and why):
- **Caps override averages** (SG-4). A good leading score never hides a fatality or a statutory breach in the same month. ISO 45001 cl. 9.1 requires performance evaluation and does not allow trading compliance against activity.
- **Lagging weight bounded 20–50 %** (SP-3). Below 20 % injuries stop mattering. Above 50 % the score rewards under-reporting. Late incident reporting is itself a cap (CP-3).
- **External recipients get de-identified aggregates only** (P6g-3). The client contract is the basis for disclosure of aggregates. Person-level data never leave by email.

## 3. Entities & fields

PDPL column: **none / personal / sensitive** (Phase 0 P1–P2). Every entity carries the Phase 0 system fields, is audited (Phase 0 rule 35) and stores `seed_fake`. AR labels are shown in the UI.

### 3.1 Scorecard profile — ملف معايير التقييم

One organisation default (`ORG`) plus an optional copy per project. A project without its own profile uses `ORG`. Versions are immutable once active.

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| profile_code / version | الرمز / الإصدار | string(16) / int | Y / sys | `ORG` or project code; version + 1 on every activation | ORG / 1 | none |
| effective_from_month | يسري من شهر | yyyy-mm | Y | ≥ first month not yet Final on any project using it (`PROFILE_BACKDATED`) | 2026-07 | none |
| pillars | المحاور | list {pillar_code (list PL), weight} | Y | Σ weight = 100.0 exactly (`WEIGHTS_NOT_100`); lagging 20.0–50.0 (`LAGGING_WEIGHT_OUT_OF_RANGE`) | LAG 30 … | none |
| metrics | المقاييس | list {metric_code (list SM), weight, good, bad, min_volume, enabled} | Y | per pillar Σ metric weight = pillar weight; weight 0.5–30.0; good ≠ bad; anchors in the canonical base (SP-4) | SM-TRIR 12, good 0.00, bad 1.00 | none |
| caps | الحدود القصوى للتقدير | list {cap_code (list CP), max_grade, enabled} | Y | CP-1 always enabled with max D (`CAP_REQUIRED`) | CP-2 → C | none |
| bands | نطاقات التقدير | list {grade, min_score} | Y | A > B > C, D = rest; default list GB | A 90.0 | none |
| status | الحالة | enum | sys | `draft` · `active` · `retired` | active | none |

### 3.2 Engagement scorecard — بطاقة أداء المقاول (one per engagement × month × revision)

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| scorecard_no | الرقم | string | sys | `SCR-<project>-<engagement short_code>-<yyyy>-<mm>` + revision | SCR-ANIA-EXP-NAJD-2026-09 R0 | none |
| engagement_id / month / revision | المقاول / الشهر / المراجعة | FK / yyyy-mm / int | sys | unique; created only when month man-hours > 0 (SG-1) | NAJD@ANIA-EXP / 2026-09 / 0 | none |
| scope | النطاق | enum | sys | `own` (official, ranked) · `tree` (with descendants, information; tier-1 and tier-2 with subs) | own | none |
| profile_code / profile_version | الملف | string / int | sys | profile in force for the month | ORG / 1 | none |
| month_man_hours / r12_man_hours / credibility_z | ساعات الشهر / 12 شهراً / معامل الموثوقية | int / int / decimal(4) | sys | §6.4 | 240,000 / 2,500,000 / 1.0000 | none |
| score | النتيجة | decimal | sys | 0–100, stored unrounded, shown 1 dp | 80.858… → 80.9 | none |
| coverage_pct | نسبة التغطية | decimal | sys | Σ original weight of scored lines (§6.3) | 90.0 | none |
| band_grade / grade | التقدير قبل الحد / التقدير | enum / enum | sys | list GB; grade = min(band_grade, caps); `—` when coverage < `scorecard_min_coverage_pct` | B / C | none |
| caps_applied | الحدود المطبقة | list {cap_code, refs} | sys | refs = incident / audit / patrol / requirement refs, no names | [CP-2 INC-ANIA-EXP-2026-nnnn] | none |
| trend_delta / trend_label | التغير / الاتجاه | decimal / enum | sys | §6.6: `improving` · `stable` · `declining` · `—` | −5.1 / stable | none |
| rank / rank_of / rank_status | الترتيب | int / int / enum | sys | RK-1; `ranked` · `low_exposure` · `low_coverage` | 3 / 4 / ranked | none |
| inputs_hash | بصمة المدخلات | string(64) | sys | SHA-256 of all line inputs | — | none |
| comment_until | نهاية فترة الملاحظات | timestamptz | sys | DP-1 | 2026-10-14 23:59 | none |
| status | الحالة | enum | sys | §4.1 | issued | none |
| revised_since_final | تغيّرت الأرقام بعد الاعتماد | bool | sys | FN-4 | false | none |

### 3.3 Scorecard line — بند المقياس

scorecard_id; metric_code; pillar_code; kpi_ref (e.g. `K-21`); window (list SM); value (decimal, unrounded), numerator, denominator, base (for rates), own_value and project_value (r12 rates, SN-2); points (0–100, unrounded); line_status `scored` محتسب · `not_applicable` غير منطبق · `insufficient_volume` حجم غير كافٍ · `source_not_live` الوحدة غير مفعلة · `excluded_by_manager` مستبعد بقرار (DP-4); original_weight; effective_weight (§6.3); contribution (= effective_weight × points ÷ 100). PDPL: none.

### 3.4 Comment and dispute — ملاحظة / اعتراض

scorecard_id; line metric_code or cap_code or null (whole card); kind `comment` ملاحظة · `dispute` اعتراض; reason_code (list DR, disputes only); text (20–1,000 chars, P1-8 scan); files ≤ 3 (PDF / image, 10 MB each); raised_by / raised_at (personal); due_at (sys: raised_at + `dispute_resolution_days`); resolution `upheld_data_corrected` قُبل وصُحّحت البيانات (corrected_record_ref required) · `upheld_metric_excluded` قُبل واستُبعد المقياس (HSE Manager only) · `rejected` رُفض; resolution_text (≥ 20 chars); resolved_by / resolved_at (personal); status `open` · `resolved` · `withdrawn`. PDPL: text and files personal (possible); author identities personal.

### 3.5 Watch-list entry — قائمة المراقبة

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| entry_no | الرقم | string | sys | `WL-<project>-<yyyy>-<nnn>` | WL-ANIA-EXP-2026-002 | none |
| engagement_id | المقاول | FK | Y | one open entry per engagement (`WATCH_ENTRY_OPEN`) | SAHARA@ANIA-EXP | none |
| level | المستوى | enum | Y | list WLL | watch | none |
| trigger_refs | أسباب الإدراج | list {month, trigger (WL-1 code), scorecard_no} | sys | — | [2026-07 C, 2026-08 C] | none |
| baseline_score | النتيجة عند الإدراج | decimal | sys | score of the opening month | 71.5 | none |
| pip_ca_refs / pip_due_on / pip_accepted_at | خطة تحسين الأداء | FK[] / date / timestamptz | cond. | level ≥ improvement_plan (WL-3) | — | none |
| decision | قرار المراجعة | enum + text | cond. | level `suspension_review`: `suspend` · `continue_with_conditions` · `remove_from_project` (demobilise); text ≥ 20 chars | — | none |
| contractor_status_ref | مرجع حالة المقاول | audit ref | cond. | Phase 0 transition record when `suspend` was applied (WL-5) | — | none |
| closed_reason | سبب الإغلاق | text(500) | cond. | ≥ 20 chars | — | none |
| status | الحالة | enum | sys | `open` · `closed` | open | none |

### 3.6 Report pack — حزمة التقارير

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| doc_no / revision | رقم الوثيقة / المراجعة | string / int | sys | `<type>-<project>[-<engagement>]-<yyyy>[-<mm>]`; Rev 0, 1… | MCR-ANIA-EXP-2026-08 / 1 | none |
| report_type | نوع التقرير | enum | Y | list RT | MCR | none |
| project_id / engagement_id / period | المشروع / المقاول / الفترة | FK / FK / range | Y / cond. / Y | SCP needs engagement; MCR one month; OSHA300 a calendar year or YTD | ANIA-EXP / — / 2026-08 | none |
| sources | المصادر | list {kind, ref, version, hash} | sys | Phase 1 report id + snapshot hash; scorecard nos + revisions; module section snapshot hashes | — | none |
| snapshot | البيانات المجمدة | json | sys | every number printed (RP-3) | — | none |
| files | الملفات | {pdf_en, pdf_ar, xlsx} | sys | rendered at Issue (RP-5); SHA-256 each | — | none (P6g-2) |
| scorecards_provisional | بطاقات أداء مبدئية | bool + reason | cond. | RP-4; reason ≥ 20 chars | false | none |
| prepared_by / reviewed_by / issued_by + timestamps | أعدّه / راجعه / أصدره | FK ×3 | sys | reviewer holds 229; issuer holds 230; reviewer ≠ issuer (`SELF_REVIEW`) | Noura / Noura / Faisal | personal |
| reissue_reason | سبب إعادة الإصدار | text(500) | cond. | revision > 0, ≥ 20 chars | "August reclassification FAC→MTC (restated)" | none |
| due_on | تاريخ الاستحقاق | date | sys | SC-2 | 2026-09-15 | none |
| revised_since_issue | تغيّرت الأرقام بعد الإصدار | bool | sys | RP-7 | false | none |
| status | الحالة | enum | sys | §4.4 | issued | none |

### 3.7 Distribution list and delivery — قائمة التوزيع وسجل الإرسال

**List** (per project × report type): members {kind `user` (FK) · `external` (display_name_or_role_en/ar string(120), organisation string(120), email)}; language per external member (`en` · `ar` · `both`, default both). PDPL: external names and emails personal.
**Delivery** (per pack revision × member): sent_at; channel `in_app` · `email`; attachments (file names); status `queued` · `sent` · `bounced` · `failed`; error text. PDPL: personal (recipient).

### 3.8 Export dataset (registry, system-defined) and export job

**Dataset registry entry** (seeded by code, one per register; not editable in the UI): dataset_code (e.g. `incidents`, `permits`, `heat_patrols`); owner module; view_capability (the row scope = what the user can list on screen); export_capability (e.g. 104); columns list {column_code, label_en/ar, pdpl_class `none` · `personal` · `sensitive` · `never`, needs_capability (personal / sensitive columns, e.g. 46, 29, 43, 79), mask_mode (list MM), default (bool)}; purpose_required_when (`sensitive_column` · `injured_identity` · `always` · `never`); aggregate (bool; small-cell rule EX-9); pdf_allowed (bool).
**Export job:** export_id `EXP-<yyyy>-<nnnnnn>`; dataset_code; format `csv` · `xlsx` · `pdf`; filters (json); columns (list); purpose (list EP) + purpose_text; row_count; file (encrypted bucket) + SHA-256; contains_personal / contains_sensitive (bool, sys); status `queued` · `ready` · `expired` · `failed`; expires_at; requested_by (personal). The export job is also the `export` audit row's subject.
**Subscription:** user; dataset_code; filters; format; frequency `weekly` (Sunday 05:30) · `monthly` (day 1, 05:30); active. Allowed only for column sets with no personal or sensitive column (`SUBSCRIPTION_PERSONAL_DATA`).

### 3.9 Phase 6g project settings

Only the HSE Manager edits them (capability 225); audited; values outside "Allowed" get 422 `SETTING_OUT_OF_RANGE`.

| Key | AR label | Type | Default | Allowed |
|---|---|---|---|---|
| scorecard_from_month | بدء بطاقات الأداء | yyyy-mm / null | null | ≥ project start month; once a month is Final, only moves earlier |
| source_live_from | بدء احتساب كل وحدة | map module → date / null | SN-5 prefill | per module; null = not live |
| scorecard_min_exposure_hours | حد ساعات الموثوقية | int | 100,000 ASSUMPTION | 50,000–1,000,000 |
| scorecard_min_coverage_pct | الحد الأدنى للتغطية | decimal | 60.0 ASSUMPTION | 50.0–90.0 |
| scorecard_comment_days | فترة الملاحظات (أيام) | int | 3 ASSUMPTION | 2–10 |
| dispute_resolution_days | مهلة البت في الاعتراض | int | 3 ASSUMPTION | 1–10 |
| scorecard_trend_points | حد تغيّر الاتجاه | decimal | 5.0 | 2.0–15.0 |
| scorecard_drop_points | حد الانخفاض للإنذار | decimal | 10.0 | 5.0–25.0 |
| pip_submit_days | مهلة تقديم خطة التحسين | int | 7 ASSUMPTION | 3–14 |
| client_report_due_day | يوم استحقاق تقرير العميل | int | 15 ASSUMPTION `VERIFY` contract | `month_lock_day` + 1 … 28 |
| external_distribution_enabled / external_domains | الإرسال الخارجي / النطاقات المسموحة | bool / string[] | false / [] | domains as `example.com`; ≥ 1 when enabled |
| report_languages | لغات التقرير | enum | `en_ar_separate` (two PDFs) | `en_ar_separate` · `bilingual_single` (EN then AR in one file) |

### 3.10 Reference lists (seeded EN/AR; codes immutable)

**PL — pillars** (default weight): `LAG` المؤشرات المتأخرة 30 · `OBS` الملاحظات والإبلاغ 7 · `CA` الإجراءات التصحيحية 10 · `PTW` تصاريح العمل 10 · `CERT` الشهادات والمعدات 8 · `TRN` التدريب والتعريف 7 · `FIT` اللياقة الطبية 4 · `HEAT` الإجهاد الحراري 4 · `EMG` الطوارئ 4 · `INS` التفتيش والتدقيق 7 · `TBT` اجتماعات التوعية 3 · `ENV` البيئة 3 · `NOT` الإخطار والدروس 3. Σ = 100.

**SM — scorecard metrics (default profile ORG v1, all ASSUMPTION).** Window: `r12_rate` = rolling 12 months ending at month end, rate with credibility (SN-2); `month` = calendar month, as_of = month end; `month_end` = point-in-time at the last day of the month; `latest_3m` = latest record in the month or the two months before. Direction: ↓ lower is better. Rates are in the canonical base (SP-4).

| Code | Pillar | KPI source (module) | Window | Good → Bad | Min volume | Weight |
|---|---|---|---|---|---|---|
| SM-TRIR | LAG | K-21 TRIR (P1) | r12_rate | 0.00 → 1.00 per 200,000 h ↓ | R12 MH > 0 | 12 |
| SM-LTIFR | LAG | K-20 LTIFR (P1) | r12_rate | 0.00 → 2.00 per 1,000,000 h ↓ | R12 MH > 0 | 8 |
| SM-LTISR | LAG | K-23 LTISR (P1) | r12_rate | 0.00 → 20.00 per 200,000 h ↓ | R12 MH > 0 | 5 |
| SM-HIPO | LAG | K-44 HiPo events as a rate (P1) | r12_rate | 0.00 → 1.00 per 200,000 h ↓ | R12 MH > 0 | 5 |
| SM-OBS | OBS | K-32 observation rate (P1) | month | 100 → 20 per 200,000 h | month MH > 0 | 4 |
| SM-UNSAFE-CLOSE | OBS | K-33 unsafe observation close-out (P1) | month | 95.0 → 50.0 % | 5 unsafe obs | 3 |
| SM-CA-ONTIME | CA | K-41 CA on-time closure (P1) | month | 95.0 → 60.0 % | 5 CAs due | 6 |
| SM-CA-OVERDUE | CA | K-42 overdue CAs per 100 average workers (K-42 at month end × 100 ÷ K-03) (P1) | month | 0.0 → 2.0 ↓ | K-03 > 0 | 4 |
| SM-PTW-AUDIT | PTW | K-61 PTW audit compliance (P3) | month | 100.0 → 80.0 % | 3 field audits | 5 |
| SM-PTW-CRIT | PTW | K-64 critical findings per 100 field audits (P3) | month | 0.0 → 10.0 ↓ | 3 field audits | 3 |
| SM-PTW-CLOSE | PTW | K-69 permit closure compliance (P3) | month | 100.0 → 80.0 % | 5 permits ended | 2 |
| SM-EQ-CERT | CERT | K-72 equipment certificate compliance (P4) | month_end | 100.0 → 80.0 % | 3 deployments | 3 |
| SM-PERS-CERT | CERT | K-76 personnel certification compliance (P4) | month_end | 100.0 → 80.0 % | 5 deployments | 3 |
| SM-SCAF-TAG | CERT | K-81 scaffold tag compliance (P4) | month_end | 100.0 → 80.0 % | 3 scaffolds | 2 |
| SM-TRAIN | TRN | K-82 training matrix compliance (P5) | month_end | 100.0 → 80.0 % | 10 requirements | 5 |
| SM-INDUCT | TRN | K-49 induction coverage (P2) | month_end | 100.0 → 80.0 % | 5 deployments | 2 |
| SM-FIT | FIT | K-89 medical fitness compliance (6a) | month_end | 100.0 → 80.0 % | 10 requirements | 4 |
| SM-HEAT-WELF | HEAT | K-101 heat welfare compliance (6b) | month, heat season only | 100.0 → 80.0 % | 10 items | 2 |
| SM-HEAT-BAN | HEAT | K-100 midday-ban violations per 100 patrols (6b) | month, heat season only | 0.0 → 5.0 ↓ | 5 valid patrols | 2 |
| SM-EMG-COVER | EMG | K-106 emergency team coverage, roster-owner engagement (6c) | month | 100.0 → 80.0 % | 1 required site-shift-day | 2 |
| SM-EMG-EQUIP | EMG | K-107 emergency equipment readiness, owner engagement (6c) | month_end | 100.0 → 80.0 % | 3 assets | 2 |
| SM-CHECKLIST | INS | K-110 checklist compliance score (6d) | month | 95.0 → 75.0 % | 3 inspections | 3 |
| SM-INSP-COVER | INS | K-113 contractor inspection coverage (6d) | month | 100.0 → 70.0 % | 1 required engagement-site-week | 2 |
| SM-AUDIT | INS | K-115 HSE audit score (6d) | latest_3m | 90.0 → 60.0 % | 1 audit issued | 2 |
| SM-TBT | TBT | K-116 toolbox weekly reach (6d) | month | 95.0 → 60.0 % | 1 unit | 3 |
| SM-WASTE-COC | ENV | K-121 waste chain of custody on time (6e) | month | 100.0 → 80.0 % | 3 consignments | 1 |
| SM-SPILL | ENV | K-124 spills as a rate (6e) | r12_rate | 0.00 → 1.00 per 200,000 h ↓ | R12 MH > 0 | 2 |
| SM-NOTIF | NOT | K-127 notifications on time (6f) | month | 100.0 → 80.0 % | 3 requirements | 2 |
| SM-LESSON-ACK | NOT | K-130 lesson acknowledgement on time (6f) | month | 100.0 → 50.0 % | 3 items | 1 |

**CP — caps:** `CP-1` fatality or permanent disability case attributed to the engagement in the month (K-05, K-05b) → max **D** (always on) · `CP-2` ≥ 1 LTI attributed in the month (K-06 minus CP-1 cases) → max **C** · `CP-3` statutory or reporting breach in the month: ≥ 1 `unpermitted_work` PTW audit (K-64 part), ≥ 1 valid midday-ban violation (K-100), a statutory 6f requirement of the engagement overdue at month end (K-128 statutory), or ≥ 1 incident of the engagement reported more than 24 h late (K-47) → max **B**.

**GB — grade bands** (same thresholds as 6d list AG, ASSUMPTION): `A` جيد ≥ 90.0 (green) · `B` مُرضٍ 75.0–89.9 (green) · `C` يحتاج إلى تحسين 60.0–74.9 (amber) · `D` ضعيف < 60.0 (red) · `—` بيانات غير كافية (grey). Comparison on the unrounded score.

**DR — dispute reasons:** `data_error` خطأ في البيانات · `wrong_attribution` نُسب لمقاول آخر · `not_applicable` لا ينطبق على نشاطنا · `other` أخرى.

**WLL — watch-list levels:** `watch` تحت المراقبة · `improvement_plan` خطة تحسين الأداء · `suspension_review` مراجعة الإيقاف.

**RT — report types:** `MCR` monthly client HSE report تقرير الصحة والسلامة الشهري للعميل (project, month; EN PDF, AR PDF, XLSX) · `SCP` contractor scorecard pack حزمة بطاقة أداء المقاول (engagement, month; EN + AR PDF) · `CPS` contractor performance summary ملخص أداء المقاول (contractor master, last 12 Final months; EN + AR PDF; HSE Manager only) · `OSHA300` annual injury log and summary سجل الإصابات السنوي (project, calendar year or YTD; XLSX + EN/AR PDF) · `HEAT` heat season report تقرير موسم الحرارة (project, season year; the 6b report rendered to PDF).

**EP — export purposes:** `gosi` · `mhrsd` · `client_report` · `legal` · `insurance` · `audit` (internal or certification audit) · `data_subject_request` · `internal_analysis` · `other` (text ≥ 20 chars).

**MM — mask modes:** `omit` (column dropped) · `mask_id` (`2*******89`, Phase 0 P4) · `person_n` ("Person n · trade · employer", numbered within the file, Phase 1 P1-2) · `role_only` (a user shown by role) · `privacy_case` ("Privacy case / حالة خصوصية", always applied to `privacy_case` rows, R4).

## 4. Workflow / states

"Who" = capability numbers (§5.10). Jobs: `scorecard_monthly` (daily 06:00 from day `month_lock_day` + 1 until the previous month is issued), `scorecard_daily` 00:20 (comment window, dispute due, finalise due, restatement check), `report_pack_daily` 07:00 (MCR drafts, due alerts, restatement check on Issued packs), `export_jobs` (queue worker), `export_subscriptions` 05:30, `export_purge` 03:00.

### 4.1 Engagement scorecard
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Provisional | مبدئية | System | live view of the current month and of the previous month until issue; recomputed on read, not stored (K-R1) |
| Provisional → Issued | صادرة للملاحظات | System | `scorecard_monthly` after the project's month M is Locked (Phase 1 §4.1); lines frozen; comment_until = issued date + `scorecard_comment_days` at 23:59 |
| Issued → Final | معتمدة | 226 | FN-1 (window closed, no open dispute); the whole project-month at once |
| Final → Superseded (new revision Issued) | مستبدلة | 226 | FN-4 re-issue with reason ≥ 20 chars |

### 4.2 Dispute
Open (227) → Resolved (228; `upheld_metric_excluded` 226 only) · Open → Withdrawn (raiser). A resolution `upheld_data_corrected` recomputes the Issued scorecard from current data (revision unchanged while Issued) and records the corrected record ref.

### 4.3 Watch-list entry
— → Open `watch` (System at finalisation, WL-1; or 226 manually with reason) → `improvement_plan` (226 confirms the system proposal, WL-3) → `suspension_review` (System proposal confirmed by 226, WL-4) → decision recorded (226) · any level → Closed (226; WL-6).

### 4.4 Report pack
Draft (System or 229) → In Review (229) → Issued (230; files rendered, frozen, distributed) · In Review → Draft (229, with comment) · Issued → Superseded (230 re-issue: a new revision starts as Draft, and the old one is Superseded when the new revision is Issued). An Issued pack is immutable (`PACK_ISSUED_IMMUTABLE`, 409).

## 5. Business rules

### 5.1 Profile (SP)
- SP-1. The HSE Manager edits a Draft profile version and activates it. Activation checks WEIGHTS_NOT_100, LAGGING_WEIGHT_OUT_OF_RANGE, CAP_REQUIRED and PROFILE_BACKDATED. The active version applies from effective_from_month to all months not yet Final. Final scorecards keep the version they were computed with.
- SP-2. Only metrics of list SM can be used. A metric with `enabled` false is treated as `not_applicable` and its weight is redistributed (WR-1). Anchors and min_volume are editable per metric.
- SP-3. The LAG pillar weight must be 20.0–50.0 and SM-TRIR must stay enabled.
- SP-4. **Canonical bases:** anchors of rate metrics are stored per 200,000 h (SM-LTIFR per 1,000,000 h). Values are converted before scoring: value_canonical = value × canonical_base ÷ project_base. A change of the project's `ltifr_base_hours` / `rate_base_hours` never changes a score (Phase 0 rule 32).
- SP-5. A project profile is created as a copy of `ORG` and edited in the same way. A cross-project comparison (CPS, K-132 for "All projects") prints the profile code and version used by each project.

### 5.2 Small numbers and sources (SN)
- SN-1. Lagging rates (window `r12_rate`) use the 12 months ending at the scored month's end. The month's own counts are shown on the card for information but are not scored. Monthly rates on one contractor's hours are noise.
- SN-2. **Credibility blending:** Z = min(1, engagement R12 man-hours ÷ `scorecard_min_exposure_hours`). rate_used = Z × own R12 rate + (1 − Z) × project R12 rate (all engagements of the project, same window and definition). Both rates and Z are stored on the line (§6.4).
- SN-3. A percentage or per-100 metric whose denominator is below its min_volume gets `insufficient_volume` and is excluded. A denominator of 0 on a `month_end` metric (e.g. no scaffolds) gets `not_applicable`. Zero events with a valid denominator are scored normally (0 overdue CAs → 100 points).
- SN-4. Heat metrics apply only to months with at least one day inside the Phase 1 `heat_season`. Outside it they are `not_applicable`.
- SN-5. **Source live-from:** a metric whose module date in `source_live_from` is null or later than the first day of the month gets `source_not_live`. At 6g deployment the map is prefilled from the module's own switch where one exists (Phase 2 `induction_register_from`; 6d `toolbox_register_from` for SM-TBT; 6f `followup_rules_from` for the NOT pillar). Otherwise it is prefilled with the first day of the month after the module's first record on the project. The HSE Manager confirms the prefilled map before the first issue (`SOURCES_NOT_CONFIRMED`).
- SN-6. Contractor attribution of every input follows the owning module's rule (K-R4, KP-3, KC-3, TK-2, MK-2, FM-1, EK-1, FK-1; 6b / 6c by contractor breakdown and roster or asset owner). The `own` scope uses "this contractor only" and the `tree` scope uses "with descendants" (K-R5).

### 5.3 Weight redistribution (WR)
- WR-1. Lines with status other than `scored` get effective weight 0. Their original weight goes first to the scored lines of the **same pillar**, in proportion to their original weights.
- WR-2. A pillar with no scored line is excluded, and its weight goes to the remaining pillars in proportion to their pillar weights.
- WR-3. Effective weights of a card always sum to 100.0 (unrounded). The card lists every excluded line with its status and every redistributed pillar.
- WR-4. coverage_pct = Σ original weights of scored lines. With coverage below `scorecard_min_coverage_pct` the score is shown as "indicative", grade is `—`, the card is not ranked and it never triggers the watch list.

### 5.4 Score and grade (SG)
- SG-1. A card exists for each engagement with month man-hours > 0 (Submitted / Verified / Locked daily returns, W-2), from `scorecard_from_month`. A tier-1 engagement, and a tier-2 engagement with subcontractors, also gets a `tree` card (information only).
- SG-2. Points per line: linear between the anchors and clipped to 0–100 (§6.2). Score = Σ contributions (§6.3). Nothing is rounded before the end (K-R8). There is no API or UI for typing points or a score.
- SG-3. band_grade from list GB.
- SG-4. **Caps:** each enabled cap whose condition is true in the month lowers the grade to at most its max_grade. The score is not changed. The card shows "B → C (CP-2: INC-…)" with record refs and no names.
- SG-5. Provisional cards (current month) carry the banner "Provisional — changes until issue" and are never used by WL, ranking history or packs.

### 5.5 Ranking and visibility (RK)
- RK-1. Within a project and month, `own` cards with grade ≠ `—` and Z = 1 are ranked by score (unrounded, descending). Ties go to the lower R12 TRIR, then the higher month man-hours, then short_code. Other cards are listed after the ranked ones with rank_status `low_exposure` or `low_coverage`.
- RK-2. **Contractor view:** a Contractor HSE Rep sees cards, lines, disputes and watch-list entries only for engagements in their C scope (own + downstream). For each such card they also see "rank n of N" and the project median score of ranked cards. They never see another engagement's name, score or grade. Requesting one returns 404 (Phase 0 rule 12).
- RK-3. A tier-1 tree card is shown to the client next to the tier-1 own card. Ranking always uses `own` cards.
- RK-4. Viewer/Client sees Final cards, ranking and watch-list levels (not texts, not disputes). Site engineers see Issued and Final cards of their project (read).

### 5.6 Comment and dispute (DP)
- DP-1. While a card is Issued and now ≤ comment_until, a Contractor HSE Rep with C scope over the engagement may comment or dispute (227). After that a dispute gets 422 `COMMENT_WINDOW_CLOSED`. HSE Officers may comment (internal notes, not visible to reps) at any time before Final.
- DP-2. A dispute names a line or cap, a reason (list DR), text ≥ 20 chars, and optionally files. Its due_at is raised_at + `dispute_resolution_days` (end of day). The HSE Officers and the HSE Manager are alerted.
- DP-3. `upheld_data_corrected` needs corrected_record_ref, which must point to a record in its owning module that was changed after the dispute was raised (`CORRECTION_NOT_FOUND`). The card recomputes, and the resolution shows old and new points.
- DP-4. `upheld_metric_excluded` is for the HSE Manager only. The line becomes `excluded_by_manager` and its weight is redistributed (WR-1). It is listed on the card and in the SCP with the reason. CP caps cannot be excluded this way. Removing a cap needs a data correction (`CAP_NOT_EXCLUDABLE`).
- DP-5. `rejected` needs a reason ≥ 20 chars. The rep is notified of every resolution in-app and by email.

### 5.7 Finalisation and re-issue (FN)
- FN-1. The HSE Manager finalises a project-month when every card's comment window has closed and no dispute is open (`COMMENT_WINDOW_OPEN`, `DISPUTES_OPEN`). Final freezes lines, inputs_hash, rank and caps. SCP packs are generated and distributed (RP-8), and WL-1 is evaluated.
- FN-2. Finalise-due alert: from comment window close + 2 days, daily to the HSE Manager.
- FN-3. Contractor reps get the Final SCP in their language. The client sees Final cards immediately.
- FN-4. **Restatement:** `scorecard_daily` recomputes Final cards of the last 12 months. If the inputs hash differs (e.g. Phase 1 restated period, a 6d response voided), the card gets revised_since_final = true, shows the recomputed score beside the Final one, and alerts the HSE Manager once. The HSE Manager may re-issue (reason ≥ 20 chars). The new revision is Issued for comment, then Final, and the old revision becomes Superseded. Watch-list effects are re-evaluated only forward. An escalation already made is never undone automatically.

### 5.8 Watch list and consequences (WL)
- WL-1. **Triggers** at finalisation of month M for each `own` card with grade ≠ `—`: (a) grade D; (b) grade C in M and in M − 1 (both Final); (c) CP-1 applied. With no open entry, an entry opens at `watch`. With an open entry, the trigger is added to trigger_refs and WL-3 / WL-4 are evaluated.
- WL-2. On opening: alerts go to the engagement's Contractor HSE Reps and the reps of its parent engagements, the project HSE Officers and the HSE Manager. The SCP of M carries the level. A review meeting CA is created (source_type `scorecard`, priority high, owner = the engagement's rep, due 7 days).
- WL-3. **Escalation to `improvement_plan`** (proposed by the system, confirmed by 226): a second trigger within 3 Final months of opening, or score in each of the 2 Final months after opening ≤ baseline_score. The rep must submit a performance improvement plan (PIP) within `pip_submit_days`: ≥ 3 Phase 1 CAs with source_type `scorecard`, each due ≤ 30 days, at least one at control level engineering or higher where the triggering lines are hazard-related (AI-11 hierarchy). Otherwise 422 `PIP_INCOMPLETE`. The HSE Manager accepts it (pip_accepted_at).
- WL-4. **Escalation to `suspension_review`** (proposed, confirmed by 226): at `improvement_plan`, any of: another D; the PIP not submitted by pip_due_on; a PIP CA overdue > 14 days. A decision task goes on the HSE Manager's action panel. The decision is recorded on the entry: `suspend`, `continue_with_conditions` or `remove_from_project`.
- WL-5. **Link to Phase 0:** the platform never changes a contractor status by itself. `suspend` opens the Phase 0 §4.2 Approved → Suspended form prefilled with status_reason "HSE performance — <entry_no>". The form warns that suspension applies to the contractor master on every project (Phase 0 rule 28) and lists the contractor's other engagements. `remove_from_project` opens the engagement's demobilisation date edit (capability 7). The resulting audit refs are stored on the entry.
- WL-6. **Exit:** after two consecutive Final months at grade B or better with no cap applied, the system proposes closure. The HSE Manager closes the entry with a reason. Manual opening (e.g. client instruction) needs a reason ≥ 20 chars.
- WL-7. **Commendation:** grade A in three consecutive Final months with no cap → the engagement is "Commended" on the next SCP and on the ranking. This is information only.
- WL-8. **CPS (pre-qualification):** for a contractor master, the last 12 Final months on all projects: the man-hour-weighted mean score (month man-hours as weights, unrounded), grade mix, caps applied, watch-list entries and decisions. HSE Manager only (capability 226, organisation scope).

### 5.9 Report packs (RP)
- RP-1. **MCR content**, in order:
  - (0) cover and document control: doc_no, revision, period, rate bases, prepared / reviewed / issued by (name and role), issue date (Gregorian, plus Umm al-Qura when `show_hijri`), distribution list (organisations and roles);
  - (1) the **Published** Phase 1 monthly report of the month: AI-19 sections 2–12 from its frozen snapshot, with section 7 replaced by the scorecard summary when 6g cards exist;
  - (2) module sections in this order, each included only if the module is live for the month (SN-5): Access (K-49, K-53, K-54, K-57, K-59; airport projects), PTW (K-46, K-46b, K-61, K-64, K-66, K-69), Certification (K-72, K-74, K-76, K-80, K-81), Training (K-37, K-82…K-88), Occupational health (K-89, K-90, K-93, K-94; aggregates only), Heat (K-97…K-103; heat-season months), Emergency (K-104…K-109), Field assurance (K-110…K-117), Environmental (K-118…K-126), Incident follow-up (K-127…K-131). Each section has a KPI table (month, previous, YTD, R12 where the KPI defines a rate, target) and the module's warnings of the month;
  - (3) contractor scorecards: ranking table (score, grade, caps, trend, coverage), pillar chart C40, watch list (levels), commendations;
  - (4) appendix: definitions and bases (Phase 1 §6 and the cited module formulas), data quality and restatements, the list of modules not yet live.
- RP-2. **No new numbers or text:** every figure comes from a stored snapshot (Phase 1 AI-20 snapshot, module KPI snapshot taken when the MCR is generated, Final scorecard revisions). The only narrative is the Phase 1 report's. 6g calls no AI and AI-1 / AI-2 are untouched.
- RP-3. A Draft is regenerated on request (229), which refreshes the module snapshots. Issue freezes the snapshot and the files.
- RP-4. Issue needs the Phase 1 report for the month Published (`SOURCE_REPORT_NOT_PUBLISHED`) and the review step done by a different user (`SELF_REVIEW`). If the month's scorecards are not Final, the HSE Manager either waits or sets scorecards_provisional with a reason. Section (3) is then watermarked "Provisional — subject to contractor comment / مبدئي — قابل لملاحظات المقاول".
- RP-5. **Rendering:** EN PDF (LTR) and AR PDF (RTL, embedded Arabic font, numbers and codes LTR per Phase 0 rule 42; digits per the `digits` setting), or one bilingual file per `report_languages`. A4 portrait with landscape tables allowed. Each page footer: doc_no · Rev n · page x of y · first 12 characters of the snapshot SHA-256 · "CONFIDENTIAL". The XLSX has one sheet per KPI table and the scorecard table, with EN and AR header rows, numbers as numeric cells (display rounding by cell format; "—" as empty cell with a note), and a "Document" sheet with the control data. The project logo is printed when set (design P9).
- RP-6. **Re-issue** (230, reason ≥ 20 chars) creates revision n + 1 as a Draft from current data. On Issue, the previous revision becomes Superseded and its view and files are watermarked "SUPERSEDED BY Rev n+1".
- RP-7. **Restatement watch:** `report_pack_daily` compares the source hashes of Issued packs of the last 12 months with current data (Phase 1 restated flags, scorecard revisions, module snapshot recomputation). On a difference, the pack gets revised_since_issue and one alert goes to the HSE Manager. Re-issue is never automatic.
- RP-8. **SCP:** generated and issued by the system at finalisation (FN-1) for each `own` card: card summary, pillars, every line with value, points, status and effective weight, caps, trend chart C39 (12 months), disputes with resolutions, watch-list level, rank "n of N" and project median (RK-2). No other contractor is named.
- RP-9. **OSHA300:** for a calendar year or YTD per project: the 300-style log (case no., trade as job title, date, site / zone as "where", de-identified description, classification columns death / days away / job transfer or restriction / other recordable, days away and restricted (capped, Phase 1 §6.3), injury or illness type) and the 300A-style summary (totals by column, man-hours K-01, average headcount K-03, TRIR and DART at the project base). Person column = `person_n` by default; names only with capability 43 and a purpose, and never on an external distribution (`RECIPIENT_SCOPE`). Privacy cases are always `privacy_case`. Commuting and non-contractor cases follow the Phase 1 rate settings, and the settings used are printed. The title reads "OSHA 300-style log (benchmark; not a KSA statutory form)".
- RP-10. **HEAT:** the 6b season report (6b §8, on-screen and XLSX there) rendered through RP-5 as a pack, with the same issue and distribution cycle.

### 5.10 Distribution (DL)
- DL-1. Distribution lists are kept per project and report type (230). A `user` member must hold the view right for the type on the project (231). Otherwise 422 `RECIPIENT_SCOPE`.
- DL-2. Contractor HSE Reps and Permit Receivers cannot be members of MCR, OSHA300 or CPS lists, because these show other contractors (`RECIPIENT_SCOPE`). They receive their SCP automatically (RP-8).
- DL-3. `external` members are allowed only for MCR, OSHA300 (de-identified) and HEAT, with `external_distribution_enabled` true and the email domain in `external_domains` (`EXTERNAL_NOT_ALLOWED`).
- DL-4. At Issue: users get an in-app notice and an email with a link. External members get an email with the files of their language attached and the XLSX. If attachments exceed 20 MB, Issue is refused with `PACK_TOO_LARGE_FOR_EMAIL` and the issuer must choose `en_ar_separate` or remove the XLSX for externals. Each send is logged (§3.7). Bounces alert the issuer.
- DL-5. A re-issue goes to the same list with the subject "Rev n supersedes Rev n−1 — <reason>".

### 5.11 Scheduling (SC)
- SC-1. `scorecard_monthly` issues month M − 1's cards on the first run after the project's month M − 1 is Locked. If the month is still unlocked on day `month_lock_day` + 2, the HSE Manager is alerted daily.
- SC-2. MCR due_on = day `client_report_due_day` of month M + 1. From day `month_lock_day` + 1, `report_pack_daily` creates the Draft on its first run after the Phase 1 report of M is Published. Alerts: to the HSE Officers and the HSE Manager at due_on − 3 days if no Draft exists or the Phase 1 report is not Published; to the HSE Manager on due_on if not Issued; daily while overdue.
- SC-3. OSHA300 Draft for year Y is created on 01-15 of Y + 1 (due 01-31 ASSUMPTION). HEAT Draft is created 10 days after the end of the project's `heat_season` (due 20 days after it).
- SC-4. Subscriptions run at their time and place a ready export in the user's export list with an in-app notice (no attachment).

### 5.12 Generic register export (EX)
- EX-1. Every register export of every module goes through the dataset registry and the existing endpoint `GET /exports/{dataset}`, plus `POST /exports` for asynchronous jobs. Datasets of Phases 0–6f are registered with the column rules their own specs already set (e.g. DECISIONS #78, capabilities 79, 123, 144, 163, 176, 189, 200, 202, 215, 222). Registering a dataset never widens who sees what (BD6g-2).
- EX-2. **Rows** = exactly the rows the user can list on screen with the same filters (role scope first, Phase 1 D-3).
- EX-3. **Columns:** the default set is the dataset's de-identified default. A `personal` column needs its needs_capability. A `sensitive` column needs its needs_capability and a purpose. A `never` column (scans, photos, signatures, medical attachments, gas readings per #78, verification-failure details, ban reasons, passwords) is rejected with 422 `COLUMN_NOT_EXPORTABLE`. Explicitly requesting a column without the right gives 403 `COLUMN_NOT_PERMITTED`. Columns dropped from the default set because of rights are listed in the job's notes (Phase 0 rule 49).
- EX-4. **Masking** follows each column's mask_mode (list MM) whenever the user lacks the right. Privacy cases are always masked. ID numbers are `mask_id` unless the dataset's full-ID capability (e.g. 79, 43) is held and a purpose is given.
- EX-5. **Purpose** (list EP) is required when purpose_required_when is met (`PURPOSE_REQUIRED`). The `export` audit row records dataset, filters, columns, row_count, purpose, file SHA-256 and export_id. Each sensitive column also writes `sensitive_field_read` (Phase 0 P5).
- EX-6. **Formats:** CSV is UTF-8 with BOM, ISO dates and local timestamps with offset. Cells starting with `=`, `+`, `-` or `@` are prefixed with `'` (formula-injection guard). XLSX has EN and AR header rows. PDF (only when pdf_allowed) is for ≤ 2,000 rows, landscape, in the user's language. XLSX and PDF carry the footer "Exported <date time> by <user> · <export_id> · CONFIDENTIAL — PDPL".
- EX-7. **Size:** up to 5,000 rows run synchronously. 5,001–100,000 rows run as a job with an in-app notice when ready. Over 100,000 rows gets 422 `EXPORT_TOO_LARGE`. Limit 50 exports per user per day (429).
- EX-8. **Files** are stored in the encrypted bucket and downloaded through signed URLs valid ≤ 5 min. They are deleted after 7 days, or 24 h when contains_sensitive, and the job becomes `expired`. Files with personal or sensitive columns are never emailed.
- EX-9. **Small cells:** in aggregate datasets, for users without capability 39, cells representing 1–2 persons show "<3" (Phase 1 D-7 / T3).
- EX-10. The export log (232) shows each user their own jobs. HSE Officers see their projects' jobs and the HSE Manager sees all, with purpose and columns, never file contents.
- EX-11. **PDF prints of dashboards** (Phase 1 D-10) use the RP-5 renderer with the footer of EX-6, from the KPI endpoint values (D-1), and write an `export` audit row.

### 5.13 KPIs and AI (GK)
- GK-1. K-132…K-135 are computed from stored cards, entries and packs (K-R1). Attribution: cards → their month; disputes → due_at date; packs → due_on. Contractor filter with descendants (K-R5) applies to K-132 and K-133.
- GK-2. **T25 `get_contractor_scorecards`** (project_ids, months, filters {engagement_ids, include_descendants, scope own/tree, status provisional/final}, fields {score, grade, band_grade, caps, coverage, pillars, lines, rank, trend, watch_level}) returns aggregates of cards in the caller's scope. For a Contractor HSE Rep, that is their C scope plus median and "n of N" (RK-2). It returns no comment or dispute text, no names and no record refs other than incident, permit and requirement refs. T13 returns E25. AI-19 section 7 uses T25 when cards exist.
- GK-3. AI-10 (3) "contractor ranking" answers from T25 when the project has cards, and states the profile version and coverage. Otherwise it keeps the Phase 1 behaviour.

### 5.14 PDPL (P6g-x)
- P6g-1. **Classes:** profiles, cards, lines, caps, ranks, watch-list levels and decisions are company performance data: **none**. Comment and dispute texts and files, authors, preparers, reviewers, issuers, external recipients, export requesters: **personal**. Export files: as their columns.
- P6g-2. Report packs (MCR, SCP, CPS, HEAT, default OSHA300) hold no injured-person names, ID numbers, nationality or medical details. Case lists are de-identified (Phase 1 AI-19 (5), P1-2). Nationality and age-band breakdowns (D-7) are never printed in a pack. Breakdown cells of 1–2 persons print "<3".
- P6g-3. Only de-identified aggregate packs may go to `external` members (DL-3). An OSHA300 with names (capability 43) is download-only for its requester, expires per EX-8 and can never be distributed.
- P6g-4. Comment and dispute texts get the P1-8 scan (warning). Text that matches an injured person's name of an incident attributed to the engagement gets 422 `IDENTITY_IN_TEXT` (as 6f P6f-3).
- P6g-5. **Retention:** Final cards, lines, watch-list entries and Issued packs are kept for project life + 10 years ASSUMPTION (aligned with P1-5). Dispute files: 3 years after Final ASSUMPTION. Export files: EX-8. Delivery logs: 5 years.
- P6g-6. External email recipients are recorded with the HSE Manager's acknowledgement that the client contract allows disclosure of aggregate HSE statistics to them. Transfer outside KSA (recipient domains abroad) follows Phase 0 P10 `VERIFY`.

### 5.15 Permission matrix — Phase 6g extension
Continues 6f §5.10. Legend A/P/S/C/C1/R/—.

| # | Capability | HSE Mgr | HSE Officer | Site Eng/Sup | Permit Issuer | Permit Receiver | Contractor HSE Rep | Viewer/Client | OH Pract. |
|---|---|---|---|---|---|---|---|---|---|
| 224 | View scorecards, lines, ranking, watch list | A | P | P (R, Issued/Final) | — | — | C (RK-2) | P (Final; no disputes) | — |
| 225 | Edit scorecard profiles, `source_live_from` and 6g settings | A | — | — | — | — | — | — | — |
| 226 | Finalise and re-issue scorecards; exclude a metric; open, escalate, decide and close watch-list entries; accept PIPs; view CPS | A | — | — | — | — | — | — | — |
| 227 | Comment on and dispute a scorecard | A | P (comment only) | — | — | — | C | — | — |
| 228 | Resolve disputes (except metric exclusion) | A | P | — | — | — | — | — | — |
| 229 | Generate, regenerate and review report packs | A | P | — | — | — | — | — | — |
| 230 | Issue and re-issue packs; distribution lists; schedules | A | — | — | — | — | — | — | — |
| 231 | View Issued packs and delivery log | A | P | P | — | — | C (own SCP only) | P (MCR, OSHA300 de-identified, HEAT) | — |
| 232 | View export log (own jobs for every role; project jobs for P; all for A); manage own subscriptions | A | P | ✓ own | ✓ own | ✓ own | ✓ own | ✓ own | ✓ own |

Exports themselves keep each dataset's own capability (EX-1). Suspended-contractor users keep reads and lose writes (Phase 0 rule 28), so they cannot dispute.

### 5.16 Phase-boundary rules (BD6g)
- BD6g-1. 6g owns no hook kind. It reads KPI-engine values (numerators, denominators, counts) and module records for caps. It writes cards, entries, packs, export jobs and CAs (source `scorecard`). It changes contractor status only through the Phase 0 form that the HSE Manager submits.
- BD6g-2. 6g never changes a KPI formula, an attribution rule or who may export which column. The registry encodes the existing rules.
- BD6g-3. AI-19 / AI-20 keep their workflow. The MCR consumes the Published snapshot and never edits it.

### 5.17 Error codes (new)
422 `WEIGHTS_NOT_100`, `LAGGING_WEIGHT_OUT_OF_RANGE`, `CAP_REQUIRED`, `PROFILE_BACKDATED`, `SOURCES_NOT_CONFIRMED`, `COMMENT_WINDOW_CLOSED`, `COMMENT_WINDOW_OPEN`, `DISPUTES_OPEN`, `CORRECTION_NOT_FOUND`, `CAP_NOT_EXCLUDABLE`, `WATCH_ENTRY_OPEN`, `PIP_INCOMPLETE`, `SOURCE_REPORT_NOT_PUBLISHED`, `SELF_REVIEW`, `RECIPIENT_SCOPE`, `EXTERNAL_NOT_ALLOWED`, `PACK_TOO_LARGE_FOR_EMAIL`, `COLUMN_NOT_EXPORTABLE`, `PURPOSE_REQUIRED`, `EXPORT_TOO_LARGE`, `SUBSCRIPTION_PERSONAL_DATA`, `IDENTITY_IN_TEXT`, `SETTING_OUT_OF_RANGE`; 403 `COLUMN_NOT_PERMITTED`; 409 `PACK_ISSUED_IMMUTABLE`, `SCORECARD_FINAL`; 429 `EXPORT_RATE_LIMIT`.

## 6. Calculations

Exact decimal arithmetic. Round half-up at output only (K-R8): score, points and pillar values 1 dp; Z 4 dp; rates 2 dp; percentages 1 dp. Comparisons use unrounded values.

### 6.1 Line value
- `month` / `month_end` / `latest_3m`: value = the KPI value from the KPI engine for the engagement (own or tree), the window and as_of = the month's last day (K-R13 numerator and denominator stored).
- Derived lines: SM-HIPO = K-44 count × 200,000 ÷ MH; SM-SPILL = K-124 count × 200,000 ÷ MH; SM-CA-OVERDUE = K-42 (as_of month end) × 100 ÷ K-03 (month); SM-PTW-CRIT and SM-HEAT-BAN = the KPI's per-100 rate.
- Rates are converted to the canonical base (SP-4).

### 6.2 Points
For "higher is better" (good > bad): points = 100 if v ≥ good; 0 if v ≤ bad; else (v − bad) ÷ (good − bad) × 100. For "lower is better" (good < bad): points = 100 if v ≤ good; 0 if v ≥ bad; else (bad − v) ÷ (bad − good) × 100.

### 6.3 Score, redistribution and coverage
For pillar p with original weight W_p and scored lines i (original weights w_i):
- pillar score S_p = Σ w_i × points_i ÷ Σ w_i (WR-1);
- pillar effective weight W′_p = W_p × 100 ÷ Σ W_q over pillars q with ≥ 1 scored line (WR-2);
- line effective weight = W′_p × w_i ÷ Σ w_i; contribution = effective weight × points_i ÷ 100;
- **score = Σ_p W′_p × S_p ÷ 100**; coverage_pct = Σ w_i over all scored lines.

### 6.4 Credibility (SN-2)
Z = min(1, MH_R12,own ÷ `scorecard_min_exposure_hours`); rate_used = Z × rate_own + (1 − Z) × rate_project. If MH_R12,own = 0 there is no card (SG-1 already needs month MH > 0).

### 6.5 Grade
band_grade = highest grade whose min_score ≤ score; grade = the lower of band_grade and every applied cap's max_grade (order A > B > C > D); grade = `—` when coverage_pct < `scorecard_min_coverage_pct`.

### 6.6 Trend
trend_delta = score(M) − score(M − 1), both Final or current revision, unrounded then 1 dp. trend_label: with ≥ 3 Final months before M, `improving` if score(M) − mean(score M−3…M−1) ≥ `scorecard_trend_points`, `declining` if ≤ −`scorecard_trend_points`, else `stable`; with fewer, `—`.

### 6.7 KPI catalogue (continues 6f §6.2)

| ID | Metric (EN / AR) | Formula | Unit / display | Better |
|---|---|---|---|---|
| K-132 | **Contractor HSE score** / مؤشر أداء المقاول في السلامة | one engagement: its card score (Final revision; else provisional, flagged); several engagements: Σ (score × month MH) ÷ Σ month MH over `own` cards with grade ≠ `—`; chips: grade mix, coverage | score 0–100, 1 dp | higher |
| K-133 | **Contractors on watch list** / المقاولون تحت المراقبة | n(open watch-list entries at as_of); chips by level | count | lower |
| K-134 | Dispute resolution on time / البت في الاعتراضات في الموعد | n(disputes resolved on or before due_at) ÷ n(disputes, not withdrawn, with due_at in period and ≤ as_of) × 100 | %, 1 dp | higher |
| K-135 | **Client report issued on time** / إصدار تقرير العميل في الموعد | n(MCR Rev 0 Issued on or before due_on) ÷ n(MCR with due_on in period and ≤ as_of) × 100 | %, 1 dp | higher |

Denominator 0 → "—".

### 6.8 Leading-indicator warning
**E25 Contractor performance decline** (per project and per tier-1 tree, DECISIONS #53), evaluated at finalisation of month M: any `own` card with grade D; or score(M) ≤ mean(Final scores M−3…M−1) − `scorecard_drop_points` (needs 3 prior Final months); or a watch-list escalation to `improvement_plan` or `suspension_review` in M. T13 inputs: engagement short_codes, scores, grades, caps, thresholds; no names.

### 6.9 Worked examples (exact; backend unit tests must match)

All examples use the default profile ORG v1 (§3.10) and ANIA-EXP bases (B_L = 1,000,000, B = 200,000) unless stated.

**SG1 — NAJD own, September 2026** (fixture, consistent with Phase 1 W2 and W3). Month MH 240,000 (W2). R12 to 2026-09-30: MH 2,500,000; TRI 3 (LTI 1 on 2026-09-08 with 20 lost days, MTC 2); HiPo 2; spills 0 → Z = min(1, 2,500,000 ÷ 100,000) = **1.0000**. `source_live_from`: all modules live before 2026-09-01 except 6f (`followup_rules_from` 2026-10-01).

| Pillar (W) | Line: value → points | Status notes | S_p |
|---|---|---|---|
| LAG (30) | TRIR 3 × 200,000 ÷ 2,500,000 = 0.24 → **76.0**; LTIFR 1 × 1,000,000 ÷ 2,500,000 = 0.40 → **80.0**; LTISR 20 × 200,000 ÷ 2,500,000 = 1.60 → **92.0**; HiPo 2 × 200,000 ÷ 2,500,000 = 0.16 → **84.0** | — | (12×76 + 8×80 + 5×92 + 5×84) ÷ 30 = 2,432 ÷ 30 = **81.066…** |
| OBS (7) | K-32 150 obs × 200,000 ÷ 240,000 = 125.0 → **100.0**; K-33 38 ÷ 40 = 95.0 % → **100.0** | — | **100.0** |
| CA (10) | K-41 9 ÷ 12 = 75.0 % → (75 − 60) ÷ 35 × 100 = **42.857…**; K-42 3 overdue × 100 ÷ K-03 800 = 0.375 → **81.25** | — | (6 × 42.857… + 4 × 81.25) ÷ 10 = **58.214…** |
| PTW (10) | K-61 90.0 % (12 audits) → **50.0**; K-64 1 × 100 ÷ 12 = 8.333… → **16.666…**; K-69 20 ÷ 20 → **100.0** | — | **50.0** |
| CERT (8) | K-72 10 ÷ 10 → **100.0**; K-76 95 ÷ 100 → **75.0** | K-81 not_applicable (no scaffolds) | (3×100 + 3×75) ÷ 6 = **87.5** |
| TRN (7) | K-82 97.0 % → **85.0**; K-49 99.0 % → **95.0** | — | **87.857…** |
| FIT (4) | K-89 98.0 % → **90.0** | — | **90.0** |
| HEAT (4) | K-101 96.0 % → **80.0**; K-100 0 in 20 patrols → **100.0** | September is in `heat_season` | **90.0** |
| EMG (4) | K-106 100.0 % → **100.0** | K-107 not_applicable (owns no assets) | **100.0** |
| INS (7) | K-110 92.0 % → **85.0**; K-113 100.0 % → **100.0** | K-115 insufficient_volume (no audit Jul–Sep) | (3×85 + 2×100) ÷ 5 = **91.0** |
| TBT (3) | K-116 90.0 % → (90 − 60) ÷ 35 × 100 = **85.714…** | — | **85.714…** |
| ENV (3) | K-124 R12 0 → **100.0** | K-121 not_applicable (no consignments) | **100.0** |
| NOT (3) | — | both source_not_live (6f from 2026-10-01) | pillar excluded |

Included pillar weight = 97 → W′_p = W_p × 100 ÷ 97. Σ W_p × S_p = 54,903 ÷ 7 = 7,843.285…; score = that ÷ 97 = **54,903 ÷ 679 = 80.858…** → **80.9**. Coverage = 100 − (2 + 2 + 2 + 1 + 2 + 1) = **90.0 %**. band_grade **B**; CP-2 applies (the NAJD LTI of 2026-09-08; card shows its Phase 1 seed incident ref) → grade **C** ("B → C (CP-2)"). LAG effective weight = 30 × 100 ÷ 97 = **30.9**.

**SG2 — credibility** (fixture, test-only engagement TSUB@RBT-52; RBT-52 bases as ANIA-EXP). R12 MH 60,000, MTC 1, no LTI, no lost days, no HiPo. Project R12: TRIR 0.50, LTIFR 0.40, LTISR 1.00, HiPo rate 0.20. Z = 60,000 ÷ 100,000 = **0.6000**. TRIR own 3.333… → used 0.6 × 3.333… + 0.4 × 0.50 = **2.20** → **0.0** points; LTIFR used 0.4 × 0.40 = **0.16** → **92.0**; LTISR used **0.40** → **98.0**; HiPo used **0.08** → **92.0**. LAG S_p = (0 + 8×92 + 5×98 + 5×92) ÷ 30 = **56.2**. rank_status **low_exposure** (Z < 1). If RBT-52 used `rate_base_hours` 1,000,000, the stored rates are 5× larger, but the canonical values and the points are identical (SP-4).

**SG3 — ranking and contractor view** (seed, ANIA-EXP September 2026, Issued at the clock). Own scores: RAWABI 88.4 (B), GULFPAVE 84.1 (B), NAJD 80.858… (C, capped), SAHARA 76.2 (B, Z = 1). Ranking: RAWABI 1, GULFPAVE 2, NAJD 3, SAHARA 4 (score, not grade). Median of ranked = (84.1 + 80.858…) ÷ 2 = **82.479…** → **82.5**. Tariq (NAJD tree rep) sees NAJD "3 of 4" and SAHARA "4 of 4", each with median 82.5, and gets 404 for RAWABI and GULFPAVE. Ahmed (RAWABI tree) sees all four. K-132 ANIA-EXP September (MH-weighted, W2 MH) = (88.4 × 360,000 + 84.1 × 180,000 + 80.858… × 240,000 + 76.2 × 90,000) ÷ 870,000 = **84.167…** → **84.2**.

**SG4 — watch list** (seed). SAHARA own: July 2026 Final 68.0 (C), August Final 71.5 (C). At August finalisation (2026-09-15 09:00) WL-1 (b) opens **WL-ANIA-EXP-2026-002** at `watch` with baseline 71.5, alerts Tariq, Ahmed (parent tree), Noura and Faisal, and creates the review-meeting CA due 2026-09-22. September is Issued at 76.2 (B, no cap). The exit proposal (WL-6) needs September and October Final at B or better with no cap, so the earliest is at October's finalisation. Variant: if September were Final at 70.0 (C), the trigger is added (C in Aug and Sep) within 3 months of opening → the system proposes `improvement_plan`.

**SG5 — monthly client report** (seed). August 2026 MCR due **2026-09-15**. MCR-ANIA-EXP-2026-08 Rev 0 Issued 2026-09-15 11:20 → on time. On 2026-09-27 Phase 1 restated August (a FAC reclassified to MTC, Phase 1 AC28) → revised_since_issue, one alert to Faisal. Rev 1 Issued 2026-09-28 with reason "August restated: a first-aid case reclassified to MTC". Rev 0 Superseded. K-135 ANIA-EXP September (packs due in September) = 1 ÷ 1 = **100.0 %**. September MCR due **2026-10-15**. At the clock its Draft exists (Phase 1 September report Published 2026-10-11 09:12; Draft created by `report_pack_daily` on 2026-10-12 07:00) and its scorecards are Issued, not Final.

**SG6 — OSHA 300A-style summary** (ANIA-EXP, YTD Jan–Sep 2026, from Phase 1 W3 monthly composition). Deaths **0**; days-away cases (LTI) **2** (May, Sep); job transfer or restriction (RWC 5 + JTC 2) **7**; other recordable (MTC) **15**; total **24** (= W3 YTD TRI); days away **35**; man-hours **7,030,000**; TRIR at B = 24 × 200,000 ÷ 7,030,000 = **0.68** (= W3).

## 7. Alerts & expiries

Channels as Phases 1–6f (in-app and email in the recipient's language; push on the phone web app; no SMS, DECISIONS #124). Each (subject, step) is sent once unless "daily".

| Trigger | Recipient | Timing | Channel |
|---|---|---|---|
| Cards Issued for comment | Reps of each engagement (C scope); HSE Officers | At issue | In-app + email |
| Comment window closes in 24 h | Reps with Issued cards | comment_until − 24 h | In-app |
| Dispute raised / due / overdue | HSE Officers, HSE Manager / resolver | At raise; at due_at; daily after | In-app + email |
| Dispute resolved | Raiser | At resolution | In-app + email |
| Finalise due (FN-2) | HSE Manager | comment close + 2 days; daily | In-app + email |
| Month not locked for scorecards (SC-1) | HSE Manager | `month_lock_day` + 2; daily | In-app |
| Watch-list open / escalation / decision task | Reps (engagement + parents), HSE Officers, HSE Manager | At event | In-app + email |
| PIP due / overdue | Engagement reps; HSE Manager at overdue | pip_due_on − 2; day after | In-app + email |
| Card or pack revised after Final / Issue | HSE Manager | Once per revision | In-app + email |
| MCR due (SC-2) | HSE Officers, HSE Manager | due − 3; due; daily overdue | In-app + email |
| Pack Issued | Distribution list (DL-4); reps (SCP) | At issue | In-app + email |
| Delivery bounced | Issuer | At bounce | In-app |
| Export job ready / failed | Requester | At completion | In-app |
| E25 | HSE Manager; HSE Officers; tier-1 rep of the tree | At finalisation | In-app + email |

Alert texts carry engagement codes, scores, grades and refs; never injured persons' names (P6).

## 8. Reports / KPIs fed

### 8.1 Dashboard additions (Phase 1 §8.1)
1. **Tiles:** K-132 contractor HSE score (grade mix chip) · K-133 contractors on watch list (by level) · K-135 client report on time (chip K-134).
2. **Scorecard band:** ranking table for the selected month (score, grade, cap marker, trend arrow, coverage, watch level), Issued / Final status, open disputes.
3. **Charts:** C39 score trend by engagement, 12 months, with grade bands as background; C40 pillar contribution per engagement for the month (stacked horizontal bars, effective weights).

### 8.2 Expiring items and action panel
- `ExpiringItemKind`: `scorecard_comment_window`, `scorecard_dispute_due`, `scorecard_finalise_due`, `report_pack_due`, `pip_due`.
- Action panel: disputes open past due; project-months awaiting finalisation; watch-list proposals awaiting confirmation; suspension-review decisions; PIPs overdue; packs In Review; MCR overdue; cards / packs revised after Final / Issue.

### 8.3 Registers and prints
Scorecard register (filters month, engagement, grade, status, cap), watch-list register, dispute register, report-pack register with revisions and delivery log, export log. Prints: SCP, CPS, MCR, OSHA300, HEAT (RP-5).

### 8.4 Feeds to other phases
- **Phase 0:** prefilled suspension / demobilisation forms (WL-5). **Phase 1:** CAs (source `scorecard`), K-132…K-135, E25, T25, AI-19 section 7, the D-10 PDF (EX-11). **Phases 2–6f:** their register exports, the 6b HEAT PDF and the 6d audit PDF through the shared renderer (§11.3).

## 9. Acceptance criteria

Fixtures: the Appendix A seed with the Phase 0–6f seeds; clock `HSE_CLOCK_AT` = **2026-10-12 10:00** unless stated. Users as 6f §9 (Faisal HSE Manager; Noura HSE Officer ANIA-EXP; Lina HSE Officer RBT-52; Omar site engineer; Ahmed Contractor HSE Rep RAWABI tree; Yousef Contractor HSE Rep QIMMA; Sarah viewer; Ramesh permit receiver NAJD) plus **Tariq** (Contractor HSE Rep, NAJD tree, A.2).

**Profile and computation**
1. **Given** Faisal activates a profile whose weights sum to 99.5 **Then** 422 `WEIGHTS_NOT_100`; LAG 55 **Then** `LAGGING_WEIGHT_OUT_OF_RANGE`; CP-1 disabled **Then** `CAP_REQUIRED`; Noura editing a profile **Then** 403 (225).
2. **Given** a new profile version with effective_from_month 2026-08 while August is Final **Then** 422 `PROFILE_BACKDATED`; from 2026-09 **Then** active, and August cards keep ORG v1.
3. **Given** SG1 **Then** every line value and points, pillar scores, score 80.9, coverage 90.0 %, band B, grade C with CP-2 citing the 2026-09-08 LTI incident ref, and LAG effective weight 30.9 are as tabled.
4. **Given** SG1 **Then** K-81, K-107, K-121 are `not_applicable`, K-115 is `insufficient_volume`, K-127 and K-130 are `source_not_live`, and the effective weights of the card sum to 100.0.
5. **Given** SG2 **Then** Z = 0.6000, used rates 2.20 / 0.16 / 0.40 / 0.08, LAG S_p 56.2 and rank_status `low_exposure`; with RBT-52 at base 1,000,000 **Then** identical points.
6. **Given** a card with K-41 based on 4 CAs due **Then** SM-CA-ONTIME is `insufficient_volume`, and its weight goes to SM-CA-OVERDUE within CA.
7. **Given** October 2026 with the default `heat_season` **Then** both heat lines are `not_applicable` and the HEAT pillar weight is redistributed to the other pillars.
8. **Given** a card whose scored weights sum to 55 **Then** grade `—`, score labelled indicative, not ranked, and no watch-list trigger.
9. **Given** an incident of SAHARA reported 30 h after occurrence in September **Then** CP-3 applies and caps SAHARA's grade at B; a fatality case **Then** CP-1 caps at D.
10. **Given** an engagement with no Submitted daily return in a month **Then** no card exists for it; DLIFT (suspended, no hours) has no September card.
11. **Given** the tree card of RAWABI **Then** its inputs use "with descendants" (equal to project values on ANIA-EXP) and it is not in the ranking.
12. **Given** no endpoint or UI **Then** a score or points value can be typed; a PATCH on a line's points returns 405.

**Cycle, disputes and finalisation**
13. **Given** ANIA-EXP September Locked on 2026-10-10 **Then** `scorecard_monthly` on 2026-10-11 06:00 issues the four own cards and the RAWABI and NAJD tree cards with comment_until 2026-10-14 23:59, and reps and Noura are alerted.
14. **Given** a project (fixture) whose previous month is still not Locked on day `month_lock_day` + 2 **Then** no cards are issued for it and Faisal receives the SC-1 alert that day and daily after.
15. **Given** Tariq disputes NAJD's SM-PTW-AUDIT line with reason `wrong_attribution` and 25 chars **Then** open, due 2026-10-15 end of day, Noura and Faisal alerted; Ramesh disputing **Then** 403 (227).
16. **Given** a dispute raised on 2026-10-15 **Then** 422 `COMMENT_WINDOW_CLOSED`.
17. **Given** Noura resolves Tariq's dispute `upheld_data_corrected` citing an audit not changed since the dispute **Then** 422 `CORRECTION_NOT_FOUND`; after the audit's engagement is corrected in Phase 3 **Then** accepted, and the card recomputes with old and new points shown.
18. **Given** Noura chooses `upheld_metric_excluded` **Then** 403; Faisal **Then** the line is `excluded_by_manager` with its weight redistributed; an attempt to exclude CP-2 **Then** 422 `CAP_NOT_EXCLUDABLE`.
19. **Given** Faisal finalises ANIA-EXP September on 2026-10-13 **Then** 422 `COMMENT_WINDOW_OPEN`; on 2026-10-15 with Tariq's dispute open **Then** `DISPUTES_OPEN`; after resolution **Then** all cards are Final, SCPs are issued to the reps, and WL-1 is evaluated.
20. **Given** a Final card and a later edit of a Phase 6d response in that month **Then** the next `scorecard_daily` sets revised_since_final, shows the recomputed score, and alerts Faisal once; re-issue without a reason **Then** 422; with a reason **Then** revision 1 is Issued and revision 0 Superseded.
21. **Given** a dispute text containing a NAJD injured worker's name **Then** 422 `IDENTITY_IN_TEXT`; a 10-digit number starting with 2 **Then** the P1-8 warning.

**Ranking, visibility and watch list**
22. **Given** SG3 **Then** ranks 1–4 as stated, median 82.5, and K-132 ANIA-EXP September = 84.2.
23. **Given** Tariq **Then** he sees NAJD "3 of 4" and SAHARA "4 of 4" with median 82.5; RAWABI's card by ID **Then** 404; T25 for him returns only NAJD and SAHARA.
24. **Given** Sarah **Then** she sees August Final cards, ranking and the SAHARA watch level, not dispute texts and not the Issued September cards; Yousef sees no ANIA-EXP card.
25. **Given** SG4 **Then** WL-ANIA-EXP-2026-002 opened at August finalisation at `watch` with baseline 71.5, alerts to Tariq, Ahmed, Noura and Faisal, and a high-priority CA with source_type `scorecard` due 2026-09-22.
26. **Given** the SG4 variant (September Final at 70.0) **Then** the system proposes `improvement_plan`; after Faisal confirms, a PIP of 2 CAs **Then** 422 `PIP_INCOMPLETE`; 3 CAs due ≤ 30 days including one engineering control **Then** accepted.
27. **Given** an `improvement_plan` entry whose PIP CA is overdue 15 days **Then** a `suspension_review` proposal and a decision task for Faisal; choosing `suspend` **Then** the Phase 0 suspension form opens prefilled with "HSE performance — WL-ANIA-EXP-2026-002", warns that the contractor master is suspended on all projects, and the contractor status is unchanged until Faisal submits it.
28. **Given** a second watch-list entry opened manually for SAHARA **Then** 422 `WATCH_ENTRY_OPEN`.
29. **Given** an engagement (fixture) at grade A for July, August and September (Final, no cap) **Then** it is Commended on the September SCP and ranking.
30. **Given** E25 rules **Then** E25 is raised at finalisation for a grade D card and for a drop of ≥ 10.0 below the 3-month mean, with T13 inputs without names.

**Report packs and distribution**
31. **Given** SG5 **Then** MCR-ANIA-EXP-2026-08 has Rev 0 Superseded and Rev 1 Issued with the reason, the Rev 0 PDF shows "SUPERSEDED BY Rev 1", and K-135 September = 100.0 %.
32. **Given** the September MCR Draft **Then** its sections follow RP-1 in order; the Phase 1 sections equal the Published snapshot; Incident follow-up is omitted for September and listed in the appendix as not live; Heat is included.
33. **Given** Faisal issues the September MCR before the scorecards are Final, without scorecards_provisional **Then** 422; with it and a reason **Then** Issued with section (3) watermarked "Provisional".
34. **Given** the RBT-52 September MCR when the Phase 1 report is still Draft **Then** issue → 422 `SOURCE_REPORT_NOT_PUBLISHED`; Noura reviewing and Faisal issuing **Then** allowed; Faisal reviewing and issuing his own **Then** 422 `SELF_REVIEW`.
35. **Given** an Issued MCR **Then** EN PDF (LTR), AR PDF (RTL, numbers and refs LTR), and XLSX with EN and AR header rows and numeric cells exist; each PDF page footer shows doc_no, Rev, page x of y and the hash prefix; editing it **Then** 409 `PACK_ISSUED_IMMUTABLE`.
36. **Given** an MCR whose numbers would change after a Phase 1 restatement **Then** the Issued files still print the frozen numbers, the pack shows revised_since_issue, and Faisal gets one alert.
37. **Given** Faisal adds Ahmed to the MCR distribution list **Then** 422 `RECIPIENT_SCOPE`; adds an external `pmc@example.com` with external distribution disabled **Then** 422 `EXTERNAL_NOT_ALLOWED`; with it enabled and the domain listed **Then** saved.
38. **Given** the MCR is Issued **Then** Sarah gets an in-app notice and link, the external member gets an email with the PDFs and XLSX attached, and the delivery log has one row per member; a bounce alerts Faisal.
39. **Given** SG6 **Then** the OSHA300 YTD 2026 summary for ANIA-EXP shows 0 / 2 / 7 / 15, total 24, 35 days away, 7,030,000 h and TRIR 0.68; persons appear as "Person n"; a privacy case appears as "Privacy case" even for Faisal with capability 43 and a purpose.
40. **Given** an OSHA300 exported with names by Faisal (43, purpose `legal`) **Then** it is download-only, expires in 24 h, and adding it to a distribution **Then** 422 `RECIPIENT_SCOPE`.
41. **Given** August is Final **Then** Tariq received the NAJD and SAHARA SCPs in his language, which name no other contractor and show rank "n of 4" and the median.
42. **Given** `report_pack_daily` on 2026-10-12 with the RBT-52 Phase 1 September report not Published **Then** no RBT-52 Draft is created and the due − 3 alert is sent to Lina and Faisal.

**Generic exports**
43. **Given** Omar exports the incident register (42) **Then** rows are limited to S-AIR, persons appear as "Person n · trade · employer", and the `export` audit row has columns, filters, row count and export_id.
44. **Given** Noura requests the incident register with `person_name` and `id_number` without a purpose **Then** 422 `PURPOSE_REQUIRED`; with purpose `gosi` **Then** the file includes them, `sensitive_field_read` is written, and the file expires in 24 h.
45. **Given** Ahmed explicitly requests `id_number` on the access worker register **Then** 403 `COLUMN_NOT_PERMITTED`; Noura requesting `medical_attachments` or gas readings **Then** 422 `COLUMN_NOT_EXPORTABLE`.
46. **Given** a CSV cell value `=HYPERLINK("x")` in an observation description **Then** the exported cell starts with `'`; the CSV opens in Excel with correct Arabic text (UTF-8 BOM).
47. **Given** an export of 12,000 rows **Then** it runs as a job and notifies when ready; 150,000 rows **Then** 422 `EXPORT_TOO_LARGE`; the 51st export of the day **Then** 429.
48. **Given** Sarah exports the 6b heat patrol register (176) **Then** aggregate rows only, cells of 1–2 persons as "<3", and no photos; Phase 3 permits for Sarah have no names (DECISIONS #78 unchanged).
49. **Given** a weekly subscription to the PTW permit register with names **Then** 422 `SUBSCRIPTION_PERSONAL_DATA`; without names **Then** the Sunday 05:30 run places the file in Noura's export list with an in-app notice and no email attachment.
50. **Given** each parked dataset (6a registers with tier columns, 6b 176, 6c 189, 6d 200, 6f 215 / 222) **Then** it is exportable through the registry with the column rules of its spec, and the dashboard PDF print (D-10) writes an `export` audit row.

**KPIs, AI, PDPL, settings, i18n**
51. **Given** the AI is asked "rank our contractors this month" by Noura **Then** T25 is called, the answer cites the profile version and coverage, uses scores verbatim, and adds Sources; Tariq asking "what is GULFPAVE's score?" **Then** the assistant says it has no access.
52. **Given** the seed at the clock **Then** K-134 for October = "—" (Tariq's dispute is due 10-15, after as_of) and K-133 = 1 (`watch`); **Given** that dispute resolved on 10-16 **Then** K-134 October as_of 10-31 = 0 ÷ 1 = 0.0 %.
53. **Given** Faisal sets `scorecard_min_exposure_hours` 20,000 or `client_report_due_day` 5 (with `month_lock_day` 10) **Then** 422 `SETTING_OUT_OF_RANGE`; a valid change **Then** saved and audited; Noura **Then** 403.
54. **Given** the first issue on a project (fixture) whose `source_live_from` was prefilled but not confirmed **Then** 422 `SOURCES_NOT_CONFIRMED` and Faisal is alerted; after confirmation **Then** cards are issued.
55. **Given** the UI and the packs in Arabic **Then** every 6g label, status, list value, alert, error, report heading and XLSX header has its AR text, and numbers, codes and refs stay left-to-right inside RTL.
56. **Given** the seed **Then** Phase 1 W1–W3 values, the 6f KPIs and every earlier register export result are unchanged by 6g.

## 10. Open questions for the HSE Manager

Each has a default so the build can start.
1. **Weights:** lagging 30 % and leading / compliance 70 % across 13 pillars (§3.10). Do your client contracts prescribe a scorecard (e.g. a CSM-style evaluation form) that we should copy instead?
2. **Grade bands:** A ≥ 90, B 75–89.9, C 60–74.9, D < 60 (same as the 6d audit grades). Keep them?
3. **Caps:** fatality → D, LTI → C, statutory breach or late report → B. Too strict or too lenient?
4. **Consequences:** watch → improvement plan → suspension review, decided by you. Should the client or PMC be part of the suspension decision, and should there be a formal warning-letter step?
5. **Small contractors:** blended with the project rate below 100,000 h in 12 months and not ranked. Is 100,000 h right for your subcontractor sizes?
6. **Client report:** due on the 15th, EN and AR as two PDFs plus XLSX. Does any client require its own template (cell mapping) or a bilingual single file?
7. **Contractor visibility:** reps see their own cards, rank "n of N" and the project median, but never other names. Do you want to show anonymous peer scores?

## 11. Changes required in earlier specs (applied 2026-10-10: 0-foundation v1.5, 1-dashboard v1.10, 6b-heat-stress v1.2, 6d-field-assurance v1.3; §11.3 item 1 is the dataset registry itself)

### 11.1 `0-foundation.md` (v1.3 after 6e) → next
1. Matrix rows 224–232 (§5.15).
2. §5.8 rule 49 gains: "Exports go through the 6g dataset registry (6g EX-1…EX-11); column classes, masking and purposes are defined there per dataset."
3. §4.2 Approved → Suspended: the reason may cite a 6g watch-list entry; the form shows the contractor's engagements on all projects (6g WL-5).

### 11.2 `1-dashboard.md` (v1.9 after 6f) → v1.10
1. §3.8 CA `source_type` adds `scorecard` (source_id = 6g watch-list entry).
2. D-10: "PDF exports are rendered by the 6g renderer (6g EX-11)"; parked item and DECISIONS #19 closed.
3. AI-19 section 7: "when 6g cards exist for the month, the contractor table is the 6g ranking (T25: score, grade, caps, coverage, trend); otherwise as before". AI-20 unchanged; the MCR consumes the Published snapshot.
4. §5.9: T25; T13 returns E25; AI-10 (3) per 6g GK-3. §6.9 / §7: E25 by reference. K-132…K-135 by reference.
5. §8.1: tiles, scorecard band, C39–C40; `ExpiringItemKind` and action-panel items of 6g §8.2.

### 11.3 Phases 2–6f
1. Each register export list is registered in the 6g dataset registry with its existing column rules (no rule changes): Phase 2 (78 / 79), Phase 3 (104, DECISIONS #78), Phase 4 (123), Phase 5 (144), 6a (163, tier columns), 6b (176), 6c (189), 6d (200), 6e (202), 6f (215, 222).
2. `6b-heat-stress.md`: the season-report PDF is the 6g `HEAT` pack (6b §1 "not in 6b" line now points to 6g RP-10).
3. `6d-field-assurance.md`: the audit report PDF (AUD-4) uses the 6g renderer (RP-5); D-177 HTML fallback is retired.
4. No KPI, rule or worked example changes value.

## Appendix A — Seed data (fictional; `seed_fake = true`; references contain `TEST` where external)

### A.1 Principles
- Builds on the Phase 0–6f seeds. Clock `HSE_CLOCK_AT` = 2026-10-12T10:00:00+03:00. The generator never changes earlier values. Line values of seeded cards are computed by the engine from the seeded records. Only SG1 / SG2 are exact fixtures for unit tests; SG3–SG5 scores are fixture values that the seed writes as Final snapshots for July and August and that the integration test reads back.
- Settings: ANIA-EXP `scorecard_from_month` 2026-07, `source_live_from` confirmed (6f = 2026-10-01; others before 2026-07-01), `external_distribution_enabled` true with `example.com`; RBT-52 `scorecard_from_month` 2026-09 (September cards Issued 2026-10-11 for QIMMA; DLIFT has no hours), Phase 1 September report still Draft at the clock. Other settings at §3.9 defaults.

### A.2 Users
- **Tariq Al-Mutairi / طارق المطيري**, tariq.mutairi@example.com, +966500000009, employer NAJD, contractor_hse_rep · ANIA-EXP · NAJD (+ subs).

### A.3 Scorecards and watch list (ANIA-EXP)
- July and August 2026 Final (ORG v1) for RAWABI, NAJD, GULFPAVE, SAHARA (own) and the RAWABI tree. SAHARA July 68.0 C, August 71.5 C → WL-ANIA-EXP-2026-002 `watch` (SG4). August issued 2026-09-11 06:00 and finalised 2026-09-15 09:00 by Faisal.
- September Issued 2026-10-11 06:00 (SG3 scores; NAJD as SG1). One open dispute: Tariq on NAJD SM-PTW-AUDIT, `wrong_attribution`, raised 2026-10-12 08:30.
- WL-ANIA-EXP-2026-001: closed 2026-08-16 (GULFPAVE, opened April after a D, exited after June and July at B).

### A.4 Report packs and distribution
- MCR-ANIA-EXP-2026-07 Rev 0 Issued 2026-08-13; MCR-ANIA-EXP-2026-08 Rev 0 (Superseded) and Rev 1 (Issued 2026-09-28), as SG5; MCR-ANIA-EXP-2026-09 Draft (2026-10-12 07:00).
- Distribution ANIA-EXP MCR: Faisal, Noura, Sarah; external "Gulf PMC Consultants (test) — PMC HSE Lead", pmc.hse@example.com, both languages.
- SCPs for July and August for each ANIA-EXP engagement; HEAT-ANIA-EXP-2026 Draft created 2026-10-10 (`heat_season` ends 09-30; due 2026-10-20), In Review at the clock.

### A.5 Exports
- 12 historical export jobs (mixed datasets, two with purpose `gosi`, all expired except three of the last 7 days); one weekly subscription for Noura (PTW permits, no names).

## Change log

| Version | Date | Author | Change |
|---|---|---|---|
| v1.0 | 2026-10-09 | HSE Consultant Agent | First issue. §1–§11 and Appendix A: configurable contractor HSE scorecard (13 pillars, 29 metrics drawn from existing KPIs K-20…K-130; canonical-base anchors; R12 lagging rates with credibility blending; minimum volumes; source live-from dates; weight redistribution within pillar then across pillars; coverage; grades A–D; caps for fatality, LTI and statutory or reporting breaches; trend; ranking; contractor view limited to own scope with rank and median), monthly issue-for-comment, disputes, finalisation and re-issue; watch list with improvement plan and suspension review handing over to the Phase 0 transition; commendation; pre-qualification summary; report packs (monthly client report EN/AR PDF + XLSX assembled from the Published Phase 1 report, module sections and Final scorecards; scorecard packs; OSHA 300/300A-style log; heat season PDF) with document numbers, freeze, re-issue, restatement watch, schedules and distribution; one dataset-registry export mechanism with PDPL column classes, masking, purposes, expiring files and subscriptions. Capabilities 224–232, KPIs K-132…K-135, warning E25, AI tool T25, charts C39–C40, CA source `scorecard`. 56 acceptance criteria. Earlier-spec changes in §11, not yet applied. |
