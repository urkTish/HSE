# Module Spec — Phase 6b: Heat Stress Management (WBGT, work/rest regimes, acclimatisation, welfare checks, midday-ban compliance, heat-illness log)

**Version:** v1.0 · **Date:** 2026-10-09 · **Author:** HSE Consultant Agent · **Status:** Draft. The HSE Manager asked to proceed without waiting for approval and will review the choices later (§10).
**Builds on:**
- `0-foundation.md` v1.0: roles, scoping legend, rules 14, 28, 35 and 48, PDPL P1–P13, the capability matrix.
- `1-dashboard.md` v1.4: setting `heat_season` (06-01 → 09-30), list N natures `heat_exhaustion` / `heat_stroke`, mechanism `exposure_heat`, observation category `heat_stress`, CA source types (§3.8), K-01 man-hours, warnings E1–E15, AI tools T1–T18, T9 dimension `heat_season`, chart C8, the action panel and expiring-items endpoint, seed W1/W3 and A.5.
- `2-access-permits.md` v1.3: workers, deployments, trades, gate logs (GC-12) and gate devices (§3.19, GC-1).
- `3-ptw.md` v1.2 with the 6a §11.4 changes: zone `default_exposure`, permit `exposure`, HT-1…HT-6, settings `midday_ban_period` / `midday_ban_hours` / `midday_ban_prewarn_minutes`, shift record (`ambient_temp_c`, `crew_present`, `pauses`), suspension list SR, SH-2/SH-3/SH-9, blockers PT-16, audit item A19.
- `5-training.md` v1.0: course HEAT-AWR, GP-6, the training hook check.
- `6a-occupational-health.md` v1.0: HEAT-EXPOSURE-FIT, restriction `no_heat_exposure`, exposure group `heat_outdoor` (reserved for 6b), hold reason `heat_illness`, referral reason `heat_illness_episode`, settings `heat_illness_natures`, access tiers OH-2 (capabilities 155–157), RW-4, small-cell rule MK-3.
- `docs/DECISIONS.md` #1–#142, in particular #121, #124, #126 and #131.

**Covers (build order):**
1. 6b.1 Instruments, monitoring points and the regime table.
2. 6b.2 WBGT readings (manual, station, import) and the zone regime in force.
3. 6b.3 Heat alerts to supervisors.
4. 6b.4 Acclimatisation plans (new starters, returners, after heat illness).
5. 6b.5 Rest stations and heat welfare checks.
6. 6b.6 Midday-ban compliance for work without a permit: patrol checks and exemptions.
7. 6b.7 Heat-illness log (linked to Phase 1 cases, 6a referrals and holds).
8. 6b.8 Phase 3 integration (WBGT stop, rest pauses, crew heat checks).
9. 6b.9 KPIs, warnings, dashboard, AI and the season report.

**Not in 6b:**
- Medical fitness, restrictions and holds themselves (6a). 6b only reads them.
- Weather forecasts and NCM heat warnings (no interface assumed, §10 Q9).
- Indoor thermal comfort and confined-space internal temperature (Phase 3 HT-6 stays as is).
- Camp and accommodation heat conditions (welfare; not proposed).
- PDF output of the season report (6g export pack; on-screen and XLSX here).
- Personal physiological monitoring (heart rate, core temperature wearables). This is health data, and it is out of scope (§10 Q10).

Conventions: `VERIFY` = clause or number to confirm against the current official text or the client's procedure. `ASSUMPTION` = Consultant default; the HSE Manager may override it (§10). "Must" = enforced server-side. Rule prefixes: HS configuration, WB readings, WR work/rest regime, HA heat alerts, AP acclimatisation, RS rest stations and welfare checks, MB midday ban (non-permit), HI heat-illness log, PH Phase 3 integration, HM KPIs/AI/season report, P6b- PDPL, BD6b boundary. Error codes are stable strings (Phase 0 rule 48). Times are local Asia/Riyadh unless marked UTC.

**The principle that shapes this module:** the regime is driven by a measured WBGT, not by the calendar. The heat season and the midday ban are fixed dates (legal and analytical). The work/rest regime applies whenever the reading demands it, in October as well as in July. The calendar only decides when monitoring, welfare checks and acclimatisation are **mandatory** (`heat_controls_period`).

---

## 1. Purpose

In Riyadh, outdoor WBGT on an apron or a tower crane base passes 30 °C on most summer days. Heat illness is 12 % of the seeded injury mechanisms (Phase 1 A.5), with new starters over-represented. Today the HSE Manager has a midday-ban rule for work that has a permit (Phase 3 HT-1…HT-4) and an ambient temperature on the permit shift, but no WBGT. Nobody can show the client or an MHRSD inspector which work/rest regime was in force on Taxiway B at 10:30, whether the new GULFPAVE labourers were acclimatised, whether water and shade were checked, or whether the laydown yard was quiet between 12:00 and 15:00, where no permit exists.

Phase 6b provides:
- WBGT readings per site or zone, entered by hand from a calibrated meter or pushed by a weather station;
- an automatic work/rest regime per reading, workload, clothing and acclimatisation (ACGIH TLV / Action Limit basis, tighten-only);
- alerts to supervisors when the regime gets worse or work must stop;
- acclimatisation plans for new starters, returners and workers coming back after a heat illness;
- a register of rest stations with daily water/shade/rest checks;
- midday-ban patrol checks and HSE Manager exemptions for **non-permit** outdoor work;
- a heat-illness log that adds the exposure context (reading, regime, acclimatisation, ban, welfare) to Phase 1 cases and 6a referrals, with a short controls review;
- a WBGT-driven stop and rest pauses on Phase 3 permits;
- KPIs K-97…K-103, warnings E16–E17, AI tool T19, charts C25–C27 and a season report for the client.

## 2. Regulatory basis

| # | Source | What it drives here |
|---|---|---|
| R1 | **MHRSD ministerial decision on the midday outdoor work ban**: no work under direct sun 12:00–15:00 from 15 June to 15 September, issued yearly; fines per violation. `VERIFY` the current decision number, dates, the list of exempted activities and the fine schedule | MB rules; Phase 3 settings reused (single source) |
| R2 | **MHRSD OSH Regulations / NCOSH guidance on heat stress**: employer duties to provide drinking water, shade and rest, and to protect workers from heat. `VERIFY` whether a KSA WBGT table or heat-index method is published, and which one | Welfare checks, regime basis |
| R3 | **ACGIH TLV® for heat stress and strain** (WBGT TLV for acclimatised workers, Action Limit for unacclimatised workers, work/rest allocation, metabolic rate classes, clothing adjustment factors). `VERIFY` the values against the current TLV booklet edition | Regime table §3.4, list WL, list CL |
| R4 | **ISO 7243:2017** (WBGT index: formulas with and without solar load, instrument requirements) | Formula §6.1, instrument rule HS-2 |
| R5 | **NIOSH Criteria for a Recommended Standard: Occupational Exposure to Heat and Hot Environments** (2016): acclimatisation schedules (new workers ≤ 20 % on day 1 then +20 %/day; experienced workers 50/60/80/100 %), loss of acclimatisation after about a week away, water about 1 cup every 15–20 min, cool water 10–15 °C. `VERIFY` | AP schedules, `deacclimatisation_days`, `cool_water_max_c` |
| R6 | **OSHA** Heat Illness Prevention (national emphasis programme; proposed standard 29 CFR 1910.148 / 1926.62 `VERIFY` status) and **1904.7** recordability | International benchmark; heat-illness log categories come from Phase 1 |
| R7 | **Client standards** flowed down (e.g. Saudi Aramco GI / CSM heat stress chapter, PMC heat plan). They may use a heat index or a stricter table. `VERIFY` per contract | Tighten-only regime table, `wbgt_limit_offset_c` |
| R8 | **ISO 45001:2018** cl. 6.1.2, 8.1.2, 9.1 | Monitoring, KPIs |
| R9 | **PDPL** (heat-illness events are health data: sensitive) | P6b rules, tiers reused from 6a |
| R10 | Phase 1 R4, Phase 3 R12, Phase 5 R14, 6a R15 | Season dates, ban, HEAT-AWR, holds |

Strictest-wins applied in this spec (and why):
- **Regime limits only tighten.** The seeded table follows ACGIH. A client table or a project offset may lower limits, never raise them (WR-6).
- **Unacclimatised workers use the Action Limit.** Anyone in an acclimatisation plan, or with no acclimatisation status, is held to the stricter table (WR-3).
- **Worse at once, better slowly.** A higher regime applies from the reading that causes it; a lower regime applies only after `regime_relax_minutes` of readings that all support it (WR-8).
- **A stale reading never improves the regime** (WR-9). Missing data never relaxes a control.
- **Ban dates come from one source** (the Phase 3 settings, which may only widen), and the controls period must contain both the ban and the heat season (HS-6).
- **No exemption by default.** Non-permit ban exemptions are granted only by the HSE Manager, per engagement, zone and date range (MB-5), as for permits (Phase 3 HT-4).
- **A physician's `no_heat_exposure` restriction keeps the worker off direct-sun permits on any date**, not only in summer (PH-6).

## 3. Entities & fields

PDPL column: **none / personal / sensitive** (Phase 0 P1–P2). Every entity carries the Phase 0 system fields, is audited (Phase 0 rule 35) and stores `seed_fake`. AR labels are shown in the UI.

### 3.1 Heat instrument — جهاز قياس الإجهاد الحراري

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| instrument_no | رقم الجهاز | string | sys | `HSM-<project>-nn` | HSM-ANIA-EXP-02 | none |
| project_id | المشروع | FK | Y | — | ANIA-EXP | none |
| kind | النوع | enum | Y | `handheld_meter` جهاز محمول · `fixed_station` محطة ثابتة | handheld_meter | none |
| make_model / serial_no | الطراز / الرقم التسلسلي | string(80) / string(40) | Y | serial unique per project | WBGT meter (test) / SN-TEST-44017 | none |
| iso7243_compliant | مطابق لـ ISO 7243 | bool | Y | must be true to activate (HS-2) | true | none |
| calibration_valid_until / calibration_cert_ref | صلاحية المعايرة / مرجع الشهادة | date / string(40) | Y | > today at activation | 2026-10-20 / CAL-TEST-0917 | none |
| device_id | جهاز المحطة | string | cond. | fixed_station only: a registered `weather_station` device (§11.3) | DEV-WS-ANIA-01 | none |
| status | الحالة | enum | Y | `active` · `quarantined` موقوف (job at calibration expiry, or manual) · `retired` | active | none |

### 3.2 Monitoring point — نقطة القياس

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| point_code | رمز النقطة | string(16) | Y | unique per project | P-SAIR-STN | none |
| site_id | الموقع | FK | Y | — | S-AIR | none |
| zone_ids | المناطق المغطاة | FK[] | Y | ≥ 1 zone of the site; a zone belongs to at most one active point (`ZONE_ALREADY_COVERED`) | [Z-APR-21, Z-TWB, Z-ILS33R] | none |
| source_kind | طريقة القياس | enum | Y | `manual` يدوي · `station` محطة | station | none |
| instrument_id | الجهاز | FK | cond. | station: an active fixed_station; manual: none (the reading names the meter) | HSM-ANIA-EXP-01 | none |
| solar_load | معرض للشمس | bool | Y | true → ISO 7243 outdoor formula (§6.1) | true | none |
| active | فعّالة | bool | Y | — | true | none |

### 3.3 WBGT reading — قراءة مؤشر WBGT

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| reading_no | رقم القراءة | string | sys | `WBG-<project>-<yyyymmdd>-<nnnn>` | WBG-ANIA-EXP-20261006-0041 | none |
| point_id | النقطة | FK | Y | active point | P-SAIR-STN | none |
| measured_at | وقت القياس | timestamptz | Y | ≤ now + 2 min; manual ≥ now − `reading_backdate_max_hours` (`BACKDATED_READING`); station/import any past time | 2026-10-06 10:00 | none |
| source | المصدر | enum | sys | `manual` · `station` · `import` | station | none |
| instrument_id | الجهاز | FK | Y | active, calibration_valid_until ≥ local date(measured_at) (`INSTRUMENT_CALIBRATION_EXPIRED`) | HSM-ANIA-EXP-01 | none |
| ta_c / tnwb_c / tg_c / rh_pct | الجاف / الرطب الطبيعي / الكرة / الرطوبة | decimal(4,1) ×3 / int | N | ta 0–60, tnwb 0–45, tg 0–90, rh 0–100 (`VALUE_OUT_OF_RANGE`) | 41.0 / 22.4 / 52.0 / 9 | none |
| wbgt_entered_c | المؤشر المُدخل | decimal(4,1) | cond. | required unless tnwb and tg (and ta when solar_load) are given; 10.0–45.0 | 30.2 | none |
| wbgt_c | المؤشر المعتمد | decimal(4,1) | sys | §6.1 | 30.2 | none |
| regime_cells | النظام لكل فئة | map | sys | §6.2: regime per (acclimatisation × workload) for clothing work_clothes | {acc.heavy: R3, …} | none |
| recorded_by | سجّلها | FK | sys | user (manual) or device (station) | Noura | personal |
| late_entry | إدخال متأخر | bool | sys | measured_at < created_at − 15 min; late readings count for coverage but raise no live alert (HA-5) | false | none |
| status / void_reason | الحالة / سبب الإلغاء | enum / text(300) | Y / cond. | `valid` · `voided` (capability 177, reason ≥ 20 chars) | valid | none |

### 3.4 Regime table (org-wide, seeded, tighten only) — جدول نظام العمل والراحة

One row per (acclimatisation basis, regime, workload). `limit_c` = the highest effective WBGT at which that regime is allowed. Seed values (°C), per R3 `VERIFY`; ★ = ASSUMPTION where ACGIH gives no value ("—"):

**Acclimatised (TLV)**

| Regime | light | moderate | heavy | very_heavy |
|---|---|---|---|---|
| R0 continuous (work 75–100 %) | 31.0 | 28.0 | 25.0 ★ | 23.0 ★ |
| R1 45 min work / 15 min rest | 31.0 | 29.0 | 27.5 | 25.5 ★ |
| R2 30 / 30 | 32.0 | 30.0 | 29.0 | 28.0 |
| R3 15 / 45 | 32.5 | 31.5 | 30.5 | 30.0 |

**Unacclimatised (Action Limit)**

| Regime | light | moderate | heavy | very_heavy |
|---|---|---|---|---|
| R0 continuous | 28.0 | 25.0 | 22.5 ★ | 21.0 ★ |
| R1 45 / 15 | 28.5 | 26.0 | 24.0 | 23.0 ★ |
| R2 30 / 30 | 29.5 | 27.0 | 25.5 | 24.5 |
| R3 15 / 45 | 30.0 | 29.0 | 28.0 | 27.0 |

Above the R3 limit the regime is **R4 stop**. Fields: basis, regime, workload, limit_c, changed_by/at (history kept). PDPL: none.

### 3.5 Zone heat state (derived, stored as intervals) — الحالة الحرارية للمنطقة

zone_id, from_at, to_at, wbgt_c, governing_reading_id, state (`current` · `stale` · `unknown`), regime_cells (map), headline_regime (the cell acclimatised × `headline_workload`). Rebuilt by the `heat_minute` job and on every reading or void. Source of K-98, the board, alerts and Phase 3. PDPL: none.

### 3.6 Acclimatisation plan — خطة التأقلم

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| plan_no | رقم الخطة | string | sys | `ACP-<project>-<yyyy>-<nnnnn>` | ACP-ANIA-EXP-2026-00412 | none |
| deployment_id | التعيين | FK | Y | Phase 2 deployment with exposure group `heat_outdoor` (AP-1) | WKR-000033 @ ANIA-EXP | personal |
| plan_type | نوع الخطة | enum | Y | list APT | post_heat_illness | **sensitive** for `post_heat_illness`, else personal (P6b-3) |
| trigger | سبب الإنشاء | {kind: mobilisation / absence / hold_release / period_start / manual, ref} | sys | — | hold_release MFH-ANIA-EXP-2026-00019 | sensitive when hold_release |
| schedule_pct | النسب اليومية | int[] | sys | copied from the setting at creation | [50, 60, 80, 100] | personal |
| prior_heat_experience | خبرة سابقة بالحرارة | {by, text ≥ 20} | N | new_worker only; switches the schedule to `returner` (AP-3) | — | personal |
| days | الأيام | list {day_no, work_date, max_pct, max_minutes, confirmed_by, confirmed_at, followed (bool), note} | sys | work_date = the n-th worked day (§6.4) | — | personal |
| status | الحالة | enum | Y | §4.2 | waiting_restriction | personal |
| status_reason | سبب الحالة | text(300) / system code | cond. | cancel: ≥ 20 chars; system `season_ended`, `demobilised`, `superseded` | — | personal |

### 3.7 Rest station — محطة الراحة

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| station_code | رمز المحطة | string(16) | Y | unique per project | RS-SAIR-01 | none |
| site_id / zone_ids | الموقع / المناطق المخدومة | FK / FK[] | Y | zones of the site | S-AIR / [Z-APR-21] | none |
| station_type | النوع | enum | Y | `cooled_cabin` كابينة مكيفة · `shaded_shelter` مظلة · `mobile_shade_unit` وحدة تظليل متنقلة · `indoor_rest_area` استراحة داخلية | cooled_cabin | none |
| capacity_persons | السعة | int | Y | 1–200 | 20 | none |
| cooling | التبريد | enum | Y | `none` · `fans` · `misting` · `air_conditioning` | air_conditioning | none |
| active | فعّالة | bool | Y | — | true | none |

### 3.8 Heat welfare check — فحص تدابير الإجهاد الحراري

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| check_no | رقم الفحص | string | sys | `HWC-<project>-<yyyy>-<nnnnn>` | HWC-ANIA-EXP-2026-03117 | none |
| station_id | المحطة | FK | Y | active station (`STATION_INACTIVE`) | RS-SAIR-01 | none |
| checked_at / checked_by | الوقت / الفاحص | timestamptz / FK | Y / sys | ≤ now; ≥ now − 24 h | 2026-09-22 07:30 / Omar | personal |
| items | البنود | list {item (list HW), answer pass / fail / na, note} | Y | every HW item answered; `na` only where list HW allows it | — | none |
| water_temp_c | حرارة الماء | decimal(3,1) | N | 0–50; > `cool_water_max_c` forces HW02 = fail | 12.5 | none |
| persons_present | العدد الحاضر | int | N | 0–500 | 14 | none |
| ca_ids | الإجراءات التصحيحية | FK[] | sys | RS-3 | — | none |
| status / void_reason | الحالة | enum / text | Y | `valid` · `voided` (177) | valid | none |

### 3.9 Midday-ban patrol check — جولة التحقق من حظر العمل وقت الظهيرة

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| patrol_no | رقم الجولة | string | sys | `MBP-<project>-<yyyy>-<nnnnn>` | MBP-ANIA-EXP-2026-00214 | none |
| zone_id | المنطقة | FK | Y | — | Z-LAY1 | none |
| checked_at / checked_by | الوقت / المدقق | timestamptz / FK | Y / sys | inside the ban hours of a ban date (`NOT_IN_BAN_WINDOW`); ≤ now; ≥ now − 4 h | 2026-09-08 12:40 / Fahad | personal |
| outcome | النتيجة | enum | Y | list BO | violation | none |
| engagement_id / headcount / activity | المقاول / العدد / النشاط | FK / int / text(200) | cond. | violation and exempt_work: required; headcount 1–500 | SAHARA / 4 / loading scaffold tubes | none |
| exemption_ref | الاستثناء | FK | cond. | exempt_work: a Phase 3 HT-4 exemption or a 6b exemption active at checked_at covering engagement and zone (`NO_ACTIVE_EXEMPTION`) | — | none |
| permit_id | التصريح | FK | N | when the work had a permit (MB-4) | — | none |
| photos | الصور | file[] ≤ 3 | N | jpg/png ≤ 5 MB; hint "Photograph the work, not faces / صوّر العمل لا الوجوه" | — | personal |
| ca_id | الإجراء التصحيحي | FK | sys | violation (MB-3) | CA-ANIA-EXP-2026-0611 | none |
| status / void_reason | الحالة | enum / text | Y | `valid` · `voided` (177) | valid | none |

### 3.10 Non-permit ban exemption — استثناء من حظر الظهيرة لأعمال دون تصريح

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| exemption_no | رقم الاستثناء | string | sys | `MBX-<project>-<yyyy>-<nnn>` | MBX-ANIA-EXP-2026-004 | none |
| engagement_id / zone_ids | المقاول / المناطق | FK / FK[] | Y | — | RAWABI / [Z-LAY1] | none |
| date_from / date_to | من / إلى | date | Y | inside the ban period; ≤ 14 days ASSUMPTION | 2026-07-20 / 2026-07-21 | none |
| reason | السبب | enum | Y | as Phase 3 HT-4: `emergency_repair` · `exempt_activity_mhrsd` (`VERIFY` R1 list) · `shaded_and_cooled_workplace` | emergency_repair | none |
| controls_en / controls_ar | الضوابط | text ≥ 30 | Y | one language required | Water main repair; shade canopy; 15/45 regime; paramedic on standby | none |
| granted_by / granted_at | مَن منح | FK / timestamptz | sys | capability 171 | Faisal | personal |
| status | الحالة | enum | Y | `active` · `expired` (job after date_to) · `revoked` (171, reason ≥ 20) | active | none |

### 3.11 Heat-illness log entry — سجل حالات الإجهاد الحراري

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| entry_no | رقم السجل | string | sys | `HIL-<project>-<yyyy>-<nnn>` | HIL-ANIA-EXP-2026-014 | none |
| source | المصدر | {type: injury_case / referral, id}; related_referral_id | sys | HI-1, HI-2 | injury_case (W1 #4 case) | sensitive |
| worker_id | العامل | FK | cond. | from the source; null when the case has no worker | WKR-000033 | personal |
| event_at / zone_id | وقت الحدث / المنطقة | timestamptz / FK | Y | case: incident occurred_at and zone; referral: raised_at; zone entered at review when unknown | 2026-09-22 13:50 / Z-APR-21 | none |
| context | السياق عند الحدث | snapshot (§6.7) | sys | computed at creation; recomputed only when event_at or zone changes before review | — | sensitive |
| review | المراجعة | {answers per list HC: yes / no / unknown; factors_text ≤ 500; reviewed_by; reviewed_at} | cond. | required to set status reviewed; P1-8 ID scan on text | — | sensitive |
| control_gap | خلل في الضوابط | bool | sys | HI-5 | true | sensitive |
| status | الحالة | enum | Y | `open` · `reviewed` · `voided` (system, source voided) | reviewed | sensitive |

The entry stores **no clinical data**: nature and category stay in Phase 1 and are shown from there under Phase 1 permissions.

### 3.12 Season report — تقرير موسم الحرارة

report_no `HSR-<project>-<yyyy>-r<n>`, project_id, season_year, period (the controls period of that year), status (`draft` live · `issued` frozen · `superseded`), metrics (frozen JSON of §8.4 at issue), comments_en/ar (≤ 2,000), issued_by/at. PDPL: none (aggregates only, HM-3).

### 3.13 Reference lists (seeded EN/AR; codes immutable)

**WL — workload (metabolic rate, R3):** `light` خفيف (< 180 W: standing, inspection, driving, crane or plant cab, flagging) · `moderate` متوسط (180–300 W: walking with light loads, welding, rigging, carpentry, electrical installation) · `heavy` شاق (300–415 W: shovelling, rebar tying, scaffold erection, masonry, manual digging, carrying) · `very_heavy` شاق جداً (> 415 W: fast digging, carrying loads up stairs, hand-mixing). Examples `VERIFY` R3.

**CL — clothing adjustment (°C added to WBGT, R3 `VERIFY`):** `work_clothes` ملابس العمل 0.0 · `cloth_coveralls` أفرول قماش 0.0 · `double_layer_woven` طبقتان منسوجتان (and welding leathers, ASSUMPTION) 3.0 · `sms_coveralls` أفرول SMS 0.5 · `polyolefin_coveralls` أفرول بولي أوليفين 1.0 · `vapour_barrier_coveralls` أفرول عازل للبخار 11.0. A hood adds 1.0 (`hood` flag).

**RGM — regimes:** `R0` عمل مستمر مع شرب الماء · `R1` 45 عمل / 15 راحة · `R2` 30 / 30 · `R3` 15 عمل / 45 راحة · `R4` إيقاف العمل الخارجي · `unknown` لا توجد قراءة. Every regime card shows "Drink 1 cup (250 mL) of cool water every 15–20 minutes / اشرب كوباً من الماء البارد كل 15–20 دقيقة" (R5).

**APT — acclimatisation plan types:** `new_worker` عامل جديد · `returner` عائد بعد غياب · `post_heat_illness` بعد إجهاد حراري (displayed as `returner` below tier 2, P6b-3) · `period_start` بداية فترة الضوابط.

**HW — welfare check items** (★ = critical, a fail creates a CA, RS-3; n.a. allowed where marked): HW01 ★ cool drinking water available at or near the station · HW02 water temperature ≤ `cool_water_max_c` (n.a. when not measured) · HW03 cups or bottles and refill available · HW04 electrolyte / ORS sachets available · HW05 ★ shade adequate for the persons present · HW06 cooling working (n.a. when cooling = none) · HW07 seating available · HW08 ★ heat first-aid kit (ice, cooling towels) and emergency number posted · HW09 current regime posted · HW10 ★ workers observed following the rest regime (n.a. when the zone regime is R0 or unknown).

**BO — patrol outcomes:** `no_outdoor_work` لا يوجد عمل خارجي · `compliant_shaded_or_indoor` العمل في الظل أو داخل المبنى · `exempt_work` عمل مستثنى · `violation` مخالفة.

**HC — heat-illness review questions:** HC1 water available at the workface · HC2 shade/rest station within reach · HC3 regime in force was followed · HC4 acclimatisation plan followed (n.a. if acclimatised) · HC5 buddy/supervisor checks done · HC6 clothing and PPE appropriate to the regime.

### 3.14 Phase 6b project settings
They extend the earlier settings. Only the HSE Manager edits them (capability 175); every change is audited; "Allowed" is the only range accepted.

| Key | AR label | Type | Default | Allowed |
|---|---|---|---|---|
| heat_register_from | بدء العمل بسجل الإجهاد الحراري | date / null | null | ≥ project start; ≤ today; only moves earlier |
| heat_ptw_enforcement_from | بدء ربط الإجهاد الحراري بالتصاريح | date / null | null | ≥ heat_register_from; set only with full coverage (HS-7) |
| heat_controls_period | فترة ضوابط الحرارة الإلزامية | MM-DD range | 05-01 → 09-30 ASSUMPTION | must contain Phase 1 `heat_season` and Phase 3 `midday_ban_period`; only widens |
| heat_monitoring_hours | ساعات القياس الإلزامية | time range | 07:00–18:00 ASSUMPTION | only widens |
| reading_valid_minutes | صلاحية القراءة | {manual, station} | {60, 20} | manual 15–60, station 5–30 |
| regime_relax_minutes | مدة التأكد قبل تخفيف النظام | int | 30 ASSUMPTION | 30–60 |
| wbgt_limit_offset_c | تعديل حدود المؤشر للمشروع | decimal | 0.0 | −3.0 … 0.0 |
| headline_workload | فئة الحمل للتنبيهات | WL | heavy ASSUMPTION | moderate, heavy, very_heavy |
| trade_workload_defaults | الحمل الافتراضي حسب المهنة | map trade → WL | labourer, steel_fixer, steel_erector, scaffolder, mason: heavy; rigger, carpenter, welder, electrician, other: moderate; plant_operator, crane_operator, driver, flagman, supervisor, engineer, hse_staff: light | a value may only move heavier |
| reading_backdate_max_hours | أقصى تأخير للقراءة اليدوية | int | 24 | 0–24 |
| wbgt_component_tolerance_c | فرق مسموح بين المكونات والمُدخل | decimal | 0.5 | 0.2–1.0 |
| acclimatisation_schedules | جداول التأقلم | {new_worker, returner} | {[20, 40, 60, 80, 100], [50, 60, 80, 100]} (R5) | each % may only fall; days may only be added |
| standard_shift_hours | ساعات الوردية المرجعية | decimal | 10.0 | 8.0–12.0 |
| deacclimatisation_days | أيام فقدان التأقلم | int | 7 (R5) | 3–7 |
| acclimatisation_restart_gap_days | انقطاع يعيد الخطة | int | 4 ASSUMPTION | 2–4 |
| plan_confirmation_hours | مهلة تأكيد يوم الخطة | int | 24 | 4–24 |
| cool_water_max_c | أقصى حرارة لمياه الشرب | decimal | 15.0 (R5) `VERIFY` | 10.0–15.0 |
| welfare_checks_per_station_day / ban_patrols_per_zone_day | الفحوص اليومية المطلوبة | int / int | 1 / 1 ASSUMPTION | 1–4 / 1–4 |
| heat_illness_review_days | مهلة مراجعة الحالة | int | 3 | 1–7 |
| heat_case_merge_hours | ربط الإحالة بالحالة | int | 48 | 24–72 |
| wbgt_coverage_warning_pct / welfare_compliance_warning_pct / ban_patrol_coverage_warning_pct | حدود الإنذار | decimal ×3 | 95.0 ×3 ASSUMPTION | 80.0–100.0 |
| heat_fitness_required | اشتراط لياقة العمل في الحرارة | bool | false ASSUMPTION (§10 Q6) | false → true only |
| heat_photo_retention_months / heat_record_retention_years | الاحتفاظ بالصور / بالسجلات | int / int | 24 / 5 ASSUMPTION | 6–36 / 2–10 |

The midday-ban dates, hours and pre-warning are **not** 6b settings: 6b reads Phase 3 `midday_ban_period`, `midday_ban_hours` and `midday_ban_prewarn_minutes`.

## 4. Workflow / states

"Who" = capability numbers (§5.12). Jobs: `heat_minute` (every 60 s: zone heat state, stale and unknown detection, events, ban pre-warning), `heat_daily` 00:07:00 (plans, coverage, calibration, exemptions; after `medical_daily`), `heat_alerts` 07:04.

### 4.1 Instrument
— → Active (168, ISO flag true, calibration valid) · Active → Quarantined (job at calibration expiry `calibration_expired`, or 168 with reason) · Quarantined → Active (168, new calibration date and cert ref) · any → Retired (168; terminal).

### 4.2 Acclimatisation plan
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Planned | مخططة | System | AP-1 triggers |
| — → Waiting Restriction | بانتظار رفع القيد | System | post_heat_illness while `no_heat_exposure` is in force or GEN-FIT is not in force (AP-6) |
| Waiting Restriction → Planned | مخططة | System | restriction lifted by a new accepted assessment and GEN-FIT in force |
| Planned → Active | جارية | System | first worked day (§6.4) |
| Active → Completed | مكتملة | System | the last schedule day is worked (end of that day) |
| Active → Interrupted | منقطعة | System | gap ≥ `acclimatisation_restart_gap_days` (AP-5); a new plan of the same type is created |
| Planned / Waiting / Active → Cancelled | ملغاة | 172 (reason ≥ 20); System (`season_ended`, `demobilised`, `superseded`) | AP-7 |

### 4.3 Exemption · reading · check · patrol
- Exemption: — → Active (171) → Expired (job) / Revoked (171).
- Reading, welfare check, patrol: — → Valid → Voided (177, reason ≥ 20 chars). A void recomputes the zone heat state and KPIs; a CA already created stays open (the CA owner closes it).

### 4.4 Heat-illness log entry
— → Open (system, HI-1/HI-2) → Reviewed (173 with the review) · Open/Reviewed → Voided (system: source case or incident Voided, or nature leaves `heat_illness_natures` and no heat referral is linked). A reviewed entry can be re-opened by 173 with a reason ≥ 20 chars.

### 4.5 Season report
Draft (always live for the current or last season) → Issued r1 (175) → Superseded by r2 when re-issued (175, reason ≥ 20). Issued revisions are never edited.

## 5. Business rules

### 5.1 Configuration (HS)
- HS-1. 6b runs on a project from `heat_register_from`. Before it, no 6b requirement applies, 6b KPIs show "—" and Phase 3 is unchanged.
- HS-2. An instrument is activated only when `iso7243_compliant` is true and calibration_valid_until > today (`INSTRUMENT_NOT_COMPLIANT` / `INSTRUMENT_CALIBRATION_EXPIRED`). At calibration expiry the job quarantines it; readings dated after expiry are refused.
- HS-3. A zone is covered by at most one active point (`ZONE_ALREADY_COVERED`). Every zone whose Phase 3 `default_exposure` = `outdoor_direct_sun` is a **required zone**; a required zone without an active point is a coverage gap (board, action panel).
- HS-4. A station point needs an active fixed_station instrument with a registered `weather_station` device. Device sessions can call only the reading-ingest endpoint (as Phase 2 GC-1).
- HS-5. The regime table is edited only by 175 and only downward (`REGIME_LOOSENING`). `wbgt_limit_offset_c` (≤ 0) is subtracted from every limit on the project.
- HS-6. `heat_controls_period` must contain Phase 1 `heat_season` and Phase 3 `midday_ban_period` (`PERIOD_TOO_SHORT`). When either earlier setting widens beyond it, the controls period widens with it (audited `auto_widened`).
- HS-7. Setting `heat_ptw_enforcement_from` requires that every required zone of the project is covered by an active point (`HEAT_COVERAGE_INCOMPLETE`, meta: zone list).

### 5.2 Readings (WB)
- WB-1. Manual readings are recorded by 167 for a point in the user's scope, with a named active meter calibrated on the reading date. Station readings arrive through the device; a repeated (device, measured_at) is ignored (idempotent).
- WB-2. wbgt_c is computed by §6.1 when the components are present; the entered value is then kept for audit only. If |entered − computed| > `wbgt_component_tolerance_c`, the save returns warning `WBGT_COMPONENT_MISMATCH` and the computed value is used.
- WB-3. Dry-bulb temperature alone is never accepted as a reading (`WBGT_REQUIRED`). Phase 3 `ambient_temp_c` stays a separate field.
- WB-4. Manual readings may be back-dated up to `reading_backdate_max_hours` (`BACKDATED_READING`); readings older than 15 min at entry are `late_entry`. Imports (template `wbgt_readings`, capability 168, .csv/.xlsx ≤ 5 MB, dry-run then commit as Phase 1 §3.2) may load any past date and are always late entries.
- WB-5. A void needs 177 and a reason ≥ 20 chars. The zone heat state, Phase 3 blockers and KPIs are recomputed within 60 s.

### 5.3 Work/rest regime (WR)
- WR-1. **Effective WBGT** for a work group = wbgt_c + clothing adjustment (list CL, + 1.0 with hood) (§6.2).
- WR-2. **Regime** = the first of R0, R1, R2, R3 whose limit (table row for the basis and workload, minus the project offset) ≥ the effective WBGT; otherwise R4. Comparison uses the 1-dp values.
- WR-3. **Basis:** `acclimatised` workers use the TLV table; workers in a Planned, Active or Waiting Restriction plan, or with status `not_acclimatised`, use the Action Limit table (§6.4 status).
- WR-4. The **workload** of a permit is its `heat_workload` (§11.4); of non-permit work, the trade default (`trade_workload_defaults`). The board always shows every cell.
- WR-5. Each reading stores its regime cells for work_clothes (§3.3). Other clothing is computed on read.
- WR-6. The seeded table can only be lowered (HS-5). A client table is entered as lower limits, never as a separate method.
- WR-7. **Zone reading:** a zone uses the readings of its covering point. A zone with no covering point has state `unknown`, except that a manual reading recorded on a Phase 3 permit shift for that zone (PH-2) serves that permit only.
- WR-8. **Worse at once, better slowly:** each valid reading r applies its regime from r.measured_at until r.measured_at + `regime_relax_minutes`. The regime of a cell at t = the highest regime among the readings that apply at t and the latest reading at or before t (§6.3).
- WR-9. **Stale:** when the latest reading is older than `reading_valid_minutes` for its source, the state is `stale` and the regime stays that of the latest reading (it never improves). With no reading on the local date before t, the state is `unknown`.
- WR-10. The midday ban is separate from the regime: in ban hours of ban dates, outdoor direct-sun work is banned whatever the reading (Phase 3 HT-1, MB rules).

### 5.4 Heat alerts (HA)
- HA-1. **Regime raised:** when a zone's headline regime gets worse (and on the first R4 of any acclimatised cell that day), alert within 60 s: the site engineers of the site, the receivers and issuers of Issued/Active permits with outdoor exposure in the zone, the Contractor HSE Reps of engagements with Mobilised deployments on the site, and the HSE Officers. The alert shows the WBGT, the time, the regime for light / moderate / heavy / very heavy (acclimatised and unacclimatised) and the rest minutes per hour.
- HA-2. **Stop:** when an acclimatised cell reaches R4, the alert says "Stop outdoor <workload> work in <zone> / أوقف العمل الخارجي <الحمل> في <المنطقة>"; when it drops below R4 (after WR-8), "Work may resume under regime <Rn>".
- HA-3. Each (zone, regime, direction) is alerted at most once per 60 min; an unchanged regime never repeats.
- HA-4. **Reading overdue:** in the controls period, during monitoring hours on a day with work (§6.5), a required zone that becomes stale or stays unknown 15 min into an hour slot alerts the HSE Officers and the site engineers of the site (once per zone per slot).
- HA-5. Late entries and imports never trigger HA-1/HA-2 alerts; they update the state for coverage and the log context only.
- HA-6. **Ban pre-warning (non-permit work):** on ban dates at 12:00 − `midday_ban_prewarn_minutes`, the site engineers and the Contractor HSE Reps of engagements Mobilised on sites with required zones receive "Midday ban from 12:00 — stop work in direct sun / حظر العمل وقت الظهيرة يبدأ 12:00".

### 5.5 Acclimatisation (AP)
- AP-1. **Population:** deployments with exposure group `heat_outdoor` (6a profile; trade defaults per §11.5). **Plans are created** in the controls period of the year, from `heat_register_from`:
  - (a) `new_worker`: at the first worked day of a deployment whose worker had no Mobilised deployment on any project of the org in the previous 60 days;
  - (b) `returner`: at the first worked day after ≥ `deacclimatisation_days` consecutive calendar days without a worked day, for an acclimatised worker;
  - (c) `post_heat_illness`: at the release of a 6a hold with reason `heat_illness` (any date, AP-7);
  - (d) `period_start`: on the first day of the controls period, for every population deployment with < 7 worked days in the 14 days before it (schedule `returner`).
- AP-2. Schedules come from `acclimatisation_schedules`: new_worker 20/40/60/80/100 %; returner, post_heat_illness and period_start 50/60/80/100 %. max_minutes = round(max_pct × `standard_shift_hours` × 60 ÷ 100).
- AP-3. A Contractor HSE Rep or supervisor (172) may record `prior_heat_experience` on a new_worker plan before day 2 (text ≥ 20 chars, e.g. "worked outdoors in Dammam until 3 weeks ago"); the plan switches to the returner schedule.
- AP-4. **Worked day** = a local date with a Phase 2 gate check direction `in` GRANTED or GRANTED_WITH_WARNING, or `admitted_despite_denial`, on the project. Projects without gates use the deployment's daily attendance in Phase 3 crew_present ASSUMPTION.
- AP-5. A gap of ≥ `acclimatisation_restart_gap_days` calendar days without a worked day during an Active plan makes it Interrupted; a new plan of the same type starts at the next worked day.
- AP-6. A post_heat_illness plan waits (Waiting Restriction) while the worker has `no_heat_exposure` in force or no in-force GEN-FIT line (6a §6.2). A restriction that lapses at its review date is **not** lifted; only a new accepted assessment without it releases the wait.
- AP-7. Plans that are Planned when the controls period ends are Cancelled `season_ended`, except post_heat_illness. Demobilisation cancels (`demobilised`). A new trigger supersedes an older open plan (`superseded`).
- AP-8. **Daily confirmation:** each worked plan day is confirmed by 172 within `plan_confirmation_hours` after the day ends, with followed yes/no (note ≥ 10 chars when no). An unconfirmed day alerts the Contractor HSE Rep and then the HSE Officer.
- AP-9. Plans never block gates or permits. Phase 3 shows them as crew warnings (PH-7). The **heat duty list** (§8.4) shows each engagement's supervisors who is acclimatising today, the day and the maximum minutes.

### 5.6 Rest stations and welfare checks (RS)
- RS-1. Stations are registered by 168. In the controls period every active station needs `welfare_checks_per_station_day` checks on each day with work on its site (§6.5).
- RS-2. A check answers every HW item. `water_temp_c` > `cool_water_max_c` forces HW02 = fail. HW10 is n.a. only when every zone the station serves is at R0 or unknown at checked_at.
- RS-3. A fail on a critical item (HW01, HW05, HW08, HW10) creates one Phase 1 CA per check (source_type `heat_check`, priority high, due checked_at + 24 h ASSUMPTION, responsible = the engagement named on the check or, if none, the tier-1 engagement of the site) and alerts the site engineer and the HSE Officer at once. Non-critical fails create no CA.
- RS-4. Contractor HSE Reps (C) and receivers (C1) may record checks at any station on sites where their engagement is Mobilised.

### 5.7 Midday ban — work without a permit (MB)
- MB-1. A patrol check is valid only inside `midday_ban_hours` of a date in `midday_ban_period` (`NOT_IN_BAN_WINDOW`). Recorders: 170 (HSE staff, site engineers, permit issuers); contractors do not record patrols (independence, ASSUMPTION).
- MB-2. **Required patrols:** on each ban date with work on the site (§6.5), each required zone (HS-3) needs ≥ `ban_patrols_per_zone_day` valid patrol checks.
- MB-3. A `violation` needs engagement, headcount and activity. It creates a Phase 1 CA (source_type `heat_check`, priority high, due the next day 12:00 ASSUMPTION, responsible = the engagement) and alerts at once the Contractor HSE Rep of the engagement and of its tier-1 parent, the HSE Officers and the HSE Manager. The alert notes possible MHRSD fines (`VERIFY` R1).
- MB-4. A violation with a permit_id also raises the Phase 3 action-panel item "outdoor work during midday ban on a permit" (the permit should have been suspended under HT-3) and links the patrol to the permit's audit history.
- MB-5. **Exemptions** for non-permit work are granted only by the HSE Manager (171), per engagement, zones and dates inside the ban period (≤ 14 days), with a reason from the HT-4 list and controls text ≥ 30 chars. They are listed in the action panel while active. `exempt_work` is accepted only with an exemption active at checked_at that covers the engagement and zone (`NO_ACTIVE_EXEMPTION`); otherwise the recorder must choose `violation`.
- MB-6. Exempt work still follows the regime: an exemption never relaxes a WBGT stop (HA-2).

### 5.8 Heat-illness log (HI)
- HI-1. A Phase 1 injury case (work-related, incident not Voided) whose nature ∈ 6a `heat_illness_natures` creates one entry when the case is created or its nature changes into the set. Any category counts, first aid included.
- HI-2. A 6a referral with reason `heat_illness_episode` creates an entry when raised. If a case per HI-1 for the same worker follows within `heat_case_merge_hours`, the referral entry becomes the case entry (source = case, related_referral_id kept); one entry per event.
- HI-3. The **context snapshot** (§6.7) is computed at creation from the event time and zone. It is not recomputed after review. A later void of the reading used marks the context `reading_voided` (kept, flagged).
- HI-4. **Review** within `heat_illness_review_days` of creation by 173: answer HC1–HC6 and, optionally, the factors text. Overdue reviews alert the HSE Officer and then the HSE Manager.
- HI-5. **control_gap** = true when any HC answer is `no`, or the context shows any of: state stale/unknown, plan day not followed or plan not confirmed, HEAT-AWR not in force, `possible_ban_breach`, or the last welfare check of the zone's station within 24 h failed a critical item.
- HI-6. An entry links the 6a hold created by the same case or referral. 6b never creates, releases or changes holds.

### 5.9 Phase 3 integration (PH) — active from `heat_ptw_enforcement_from` (§11.4)
- PH-1. Outdoor permits carry `heat_workload` (default per permit type, §11.4) and `heat_clothing` (default work_clothes). The permit's regime = the zone regime for the acclimatised basis, that workload and clothing.
- PH-2. In the controls period, during monitoring hours, Start, Revalidate, Resume and handover acceptance of an `outdoor_direct_sun` permit need the zone state `current` (blocker `WBGT_READING_REQUIRED`). The receiver may clear it by recording a manual reading (167) for the zone with a calibrated meter.
- PH-3. **WBGT stop:** when the permit's regime is R4, blocker `HEAT_STOP` applies at Start/Revalidate/Resume, and an Active permit is Suspended `heat_stress_stop` within 60 s (routine = true ASSUMPTION, §10 Q4). Resume is allowed once `HEAT_STOP` clears (WR-8) and other Issue-time blockers are empty, by the receiver (no issuer cause text), with the GT-4 test where gas testing applies.
- PH-4. **Rest pauses:** the shift shows the regime and the rest minutes per hour. Pauses with reason `heat_rest` record the rest. SH-9 is unchanged: a pause ≥ `gas_break_retest_minutes` on a gas-tested permit needs the GT-4 test before work restarts.
- PH-5. A crew member whose own basis is unacclimatised and whose cell is R4 while the permit is not stopped is removed from crew_present for the shift with warning `HEAT_STOP_FOR_WORKER` (the receiver sees "Not for heat work now — acclimatising / غير مسموح بالعمل في الحرارة الآن — في فترة التأقلم").
- PH-6. **Restriction:** a worker with `no_heat_exposure` in force cannot be in the crew of an `outdoor_direct_sun` permit on any date, or of an `outdoor_shaded` permit in the controls period. Non-key crew are excluded (`HEAT_RESTRICTION`, as DECISIONS #126); a key role gives blocker `KEY_ROLE_INELIGIBLE`. Display follows 6a HK6-7: tier 1 sees "Not eligible — HSE check".
- PH-7. An acclimatising crew member gives warning `WORKER_ACCLIMATISING` (day n, max minutes) on crew add and at shift start. Not a blocker (AP-9).
- PH-8. Indoor permits are unaffected. The midday ban (HT-1…HT-4) is unchanged.

### 5.10 KPIs, AI and season report (HM)
- HM-1. All 6b KPIs are computed by the backend. Period scope: dates in the controls period for K-97, K-101, K-102; ban dates for K-99, K-100; any date for K-98 and K-103.
- HM-2. AI tool **T19 `get_heat_stress_kpis`** (project_ids, period, filters {site, zone, engagement, include_descendants}, metrics K-97…K-103, group_by {zone, site, contractor, month, week, regime}) returns aggregates only: no names, worker_no, photos or review texts. T13 returns E16–E17. T9 gains dimensions `wbgt_regime_at_event` (R0–R4 / unknown, headline workload) and `acclimatisation_at_event` (acclimatised / acclimatising / not_acclimatised / n.a.).
- HM-3. Heat-illness counts follow the Phase 1 small-cell rule (T3, < 3) because they are Phase 1 injury data; per-worker 6b data never reaches the AI.
- HM-4. The **season report** (§8.4) is live as Draft from the first day of the controls period. Issue (175) freezes the metrics; re-issue creates r+1 and supersedes the previous one. Viewer/Client sees issued revisions only.

### 5.11 PDPL (P6b-x)
- P6b-1. **Sensitive:** heat-illness log entries (source, context, review, control_gap), post_heat_illness plan type and trigger. **Personal:** plans of other types, recorder identities, patrol photos. **None:** readings, regimes, stations, checks, exemptions, season report.
- P6b-2. Log entries are visible to 173. Worker names appear only to holders of Phase 1 capability 29 (injured-person identity); others see worker_no. Contractor HSE Reps see C-scope entries without review texts ASSUMPTION. Every read writes `sensitive_field_read`.
- P6b-3. Below 6a tier 2 (capability 156), a post_heat_illness plan is shown as `returner` and its trigger as "absence" (it would otherwise reveal a health event).
- P6b-4. Patrol photos: the UI hint asks for work, not faces; photos are kept `heat_photo_retention_months`, then purged (`retention_purge`). Readings, checks, patrols and plans are kept `heat_record_retention_years`; log entries follow the Phase 1 incident retention (P1-5).
- P6b-5. AI: aggregates only (HM-2, HM-3). Alerts never name a worker in connection with a heat illness; they cite the entry number.
- P6b-6. Free text fields get the Phase 1 P1-8 ID scan.

### 5.12 Phase-boundary rules (BD6b)
- BD6b-1. 6b owns no hook kind. It reads Phase 1 cases, Phase 2 deployments and gate logs, Phase 3 zone profiles, permits and shifts, Phase 5 HEAT-AWR results and 6a restrictions, holds and referrals. It writes Phase 1 CAs (source `heat_check`) and, through §11.4, Phase 3 blockers and suspensions only.
- BD6b-2. Phase 3 keeps the midday ban for permits; 6b adds patrols and exemptions for non-permit work only.

### 5.13 Permission matrix — Phase 6b extension
Continues 6a §5.15. Legend A/P/S/C/C1/R/—.

| # | Capability | HSE Mgr | HSE Officer | Site Eng/Sup | Permit Issuer | Permit Receiver | Contractor HSE Rep | Viewer/Client | OH Pract. |
|---|---|---|---|---|---|---|---|---|---|
| 166 | View heat board, readings, stations, exemptions, patrol results, heat duty list | A | P | S | S | C1 | C | P (R) | P |
| 167 | Record manual WBGT readings | A | P | S | S | C1 | C | — | — |
| 168 | Manage instruments, monitoring points, station devices, rest stations; import readings | A | P | — | — | — | — | — | — |
| 169 | Record heat welfare checks | A | P | S | S | C1 | C | — | — |
| 170 | Record midday-ban patrol checks | A | P | S | S | — | — | — | — |
| 171 | Grant / revoke non-permit midday-ban exemptions | A | — | — | — | — | — | — | — |
| 172 | Confirm plan days; record prior heat experience; cancel plans | A | P | S | — | C1 | C | — | P |
| 173 | View and review the heat-illness log | A | P | S (view) | — | — | C (view, P6b-2) | — | P (view) |
| 174 | View 6b KPIs, action panel, season report | A | P | S | S | C1 | C | P (aggregates, issued reports) | P |
| 175 | Edit 6b settings and regime table; enable PTW enforcement; issue season reports | A | — | — | — | — | — | — | — |
| 176 | Export 6b registers (never photos or review texts below 173) | A | P | S | — | — | C | P (aggregates) | — |
| 177 | Void readings, checks and patrols | A | P | — | — | — | — | — | — |

## 6. Calculations

Rounding is half-up at output only (Phase 1 K-R8): WBGT to 1 dp at storage, percentages to 1 dp, rates to 2 dp. Comparisons and warnings use unrounded KPI values.

### 6.1 WBGT (ISO 7243)
- With solar load (point.solar_load = true): **WBGT = 0.7 × Tnwb + 0.2 × Tg + 0.1 × Ta**.
- Without solar load: **WBGT = 0.7 × Tnwb + 0.3 × Tg**.
- wbgt_c = round(computed, 1) when components are present, else wbgt_entered_c.

### 6.2 Effective WBGT and regime
- eff = wbgt_c + CAF(clothing) + (hood ? 1.0 : 0).
- limit(basis, Rn, workload) = table value + `wbgt_limit_offset_c`.
- regime = min{Rn ∈ R0…R3 : eff ≤ limit(basis, Rn, workload)}; none → R4.
- Rest minutes per hour: R0 0 (normal breaks), R1 15, R2 30, R3 45, R4 60.

### 6.3 Zone regime in force at t
- Applying readings A(t) = valid readings r of the covering point with r.measured_at ≤ t < r.measured_at + `regime_relax_minutes`, plus L = the latest valid reading with measured_at ≤ t on the local date.
- cell regime(t) = max over A(t) of r's cell regime (R0 < … < R4).
- state = `unknown` if L is none; `stale` if t − L.measured_at > `reading_valid_minutes`[L.source]; else `current`.
- headline = cell (acclimatised, `headline_workload`).

### 6.4 Acclimatisation status and plan days
- Worked day per AP-4. Day n of a plan = the n-th worked day from the trigger date.
- status(worker, d) = `acclimatising` if a plan is Active or Planned on d; `not_acclimatised` if a plan is Waiting Restriction or Interrupted without a successor that has started; `acclimatised` otherwise for population deployments; `n.a.` outside the population.
- A plan is **completed as planned** ⇔ Completed and every day confirmed with followed = true.

### 6.5 Days with work and required slots
- A **day with work** on a site = a local date with a Phase 1 daily return (Submitted or later) with headcount > 0 for any engagement on that site.
- Required monitoring slots = Σ over required zones' covering points (and uncovered required zones, counted per zone) × days with work in the controls period × whole hours of `heat_monitoring_hours`. A slot [hh:00, hh+1:00) is **covered** if ≥ 1 valid reading of the point has measured_at in it. An uncovered zone's slots are never covered.
- Required patrol zone-days = required zones × ban dates with work on their site. A zone-day is **patrolled** if it has ≥ `ban_patrols_per_zone_day` valid patrols.
- Required welfare station-days = active stations × days with work in the controls period; **checked** if ≥ `welfare_checks_per_station_day` valid checks.

### 6.6 KPI catalogue (continues 6a §6.6)

| ID | Metric (EN / AR) | Formula | Unit / display | Better |
|---|---|---|---|---|
| K-97 | **WBGT monitoring coverage** / تغطية قياس المؤشر الحراري | covered slots ÷ required slots × 100; denominator 0 → "—" | %, 1 dp | higher |
| K-98 | Heat-stop zone-hours / ساعات الإيقاف الحراري | Σ over required zones of hours in monitoring hours where the headline cell = R4; breakdown hours by regime R0…R4 / stale / unknown | h, 1 dp | — (context) |
| K-99 | **Midday-ban patrol coverage** / تغطية جولات حظر الظهيرة | patrolled zone-days ÷ required zone-days × 100 | %, 1 dp | higher |
| K-100 | **Midday-ban violations** / مخالفات حظر الظهيرة | n(valid violation patrols); rate = n × 100 ÷ n(valid patrols); breakdown by contractor | count · per 100 patrols, 2 dp | lower |
| K-101 | **Heat welfare compliance** / الامتثال لتدابير الراحة والماء | compliant items ÷ applicable items (pass + fail) × 100; chip: checked station-days ÷ required × 100 | %, 1 dp · % | higher |
| K-102 | Acclimatisation compliance / الالتزام بخطط التأقلم | plans Completed in period and completed as planned ÷ plans Completed in period × 100 | %, 1 dp | higher |
| K-103 | **Heat-illness cases** / حالات الإجهاد الحراري | n(log entries with source injury_case, event in period, not voided); rate = n × 200,000 ÷ K-01; recordable subset (category ≠ FAC) with its own rate | count · rate 2 dp | lower |

### 6.7 Context snapshot of a heat-illness entry
At event_at e in zone z for worker w: reading_no and wbgt_c of the zone state at e (state current / stale / unknown); workload = w's trade default; basis and status(w, local date(e)) with plan_no and day; regime for that cell and work_clothes; ban_in_force (e within ban hours of a ban date) and `possible_ban_breach` = ban_in_force ∧ zone required; permit_ids from the incident; days_on_site band (Phase 1); HEAT-AWR in force at e (Phase 5 hook check, yes/no); the last valid welfare check of a station serving z within 24 h before e (pass / critical fail / none); the 6a hold number and status.

### 6.8 Leading-indicator warnings
Monthly job, day 2 at 07:00, per project and per tier-1 tree (as DECISIONS #53).
- **E16** (months with ban dates): K-100 in M ≥ 1, or K-99 in M < `ban_patrol_coverage_warning_pct`.
- **E17** (months overlapping the controls period, and any month with a heat-illness entry): ≥ 1 entry with event in M and control_gap = true, or K-97 in M < `wbgt_coverage_warning_pct`, or K-101 in M < `welfare_compliance_warning_pct`.
- T13 inputs: the counts, numerators, denominators and thresholds; never names or review texts.

### 6.9 Worked examples (exact; backend unit tests must match)

**HS1 — WBGT formula.** (a) Solar: Tnwb 22.4, Tg 52.0, Ta 41.0 → 15.68 + 10.40 + 4.10 = 30.18 → **30.2**. (b) No solar: Tnwb 24.0, Tg 34.0 → 16.80 + 10.20 = **27.0**. (c) Entered 31.0 with the components of (a) → |31.0 − 30.18| = 0.82 > 0.5 → warning `WBGT_COMPONENT_MISMATCH`, stored **30.2**.

**HS2 — regime cells (work clothes, offset 0).**

| wbgt | Acc. light | Acc. moderate | Acc. heavy | Acc. very heavy | Unacc. light | Unacc. moderate | Unacc. heavy | Unacc. very heavy |
|---|---|---|---|---|---|---|---|---|
| 27.8 | R0 | R0 | **R2** | R2 | R0 | R3 | R3 | R4 |
| 30.2 | R0 | R3 | R3 | R4 | R4 | R4 | R4 | R4 |
| 31.4 | R2 | R3 | R4 | R4 | R4 | R4 | R4 | R4 |
| 32.1 | R3 | R4 | R4 | R4 | R4 | R4 | R4 | R4 |

- 28.0 with double_layer_woven → eff 31.0 → acclimatised moderate **R3** (vs R0 in work clothes). vapour_barrier_coveralls → eff 39.0 → **R4** for every cell.
- Offset −1.0: at 27.8 acclimatised moderate → limit R0 27.0 no, R1 28.0 yes → **R1**.

**HS3 — zone state at the clock (2026-10-06, P-SAIR-STN, station, valid 20 min, relax 30 min).** Readings 09:30 26.9, 09:45 27.2, 10:00 27.8. Headline (acclimatised heavy): 26.9 and 27.2 → R1; 27.8 → R2. At 10:00 the headline rises R1 → **R2** → HA-1 alert at 10:00 to Omar, Ahmed, Noura (no Issued/Active outdoor permit on S-AIR at 10:00). If the 10:15 reading is 27.0 (R1), the regime stays R2 until **10:30:00** (10:00 + 30 min), then R1 if no newer reading supports R2. If no reading arrives after 10:00, the state is `stale` after 10:20:00 with R2 kept (WR-9). No HA-4 alert is sent, because 2026-10-06 is outside the controls period (05-01 → 09-30).

**HS4 — acclimatisation (fixture, clock advanced; controls period 2027-05-01 → 09-30).**
- (a) New labourer FX-NEW mobilised 2027-06-02 (Wed), gate entries 06-02, 06-03, 06-05, 06-06, 06-07 (06-04 Friday off): days 1–5 = **06-02 20 % (120 min), 06-03 40 % (240), 06-05 60 % (360), 06-06 80 % (480), 06-07 100 % (600)** with standard_shift_hours 10; Completed at the end of 06-07.
- (b) Same worker, entries 06-02, 06-03, then 06-08: 06-04…06-07 is a 4-day gap → plan Interrupted; new new_worker plan, day 1 = **06-08**.
- (c) Acclimatised worker with no entry 2027-07-01…07-07 (7 days), entry 07-08 → returner plan: **07-08 50 %, then 60, 80, 100** on the next worked days.
- (d) Ganesh Shrestha: hold MFH-ANIA-EXP-2026-00019 released 2026-09-23 06:31 with no_heat_exposure (review 2026-10-07) → post_heat_illness plan **ACP-ANIA-EXP-2026-00412, Waiting Restriction**. On 2026-10-08 the restriction review passes without a new assessment: still Waiting (AP-6).

**HS5 — Phase 3 WBGT stop (fixture permit FX-HEAT, GULFPAVE airside_works + excavation, Z-TWB, 2027-07-14 Wed, windows 06:00–12:00 and 15:00–18:00; heat_workload heavy, work clothes; crew acclimatised except FX-NEW2 on plan day 2).**
- 07:00 reading 27.6 → permit regime (acc. heavy) **R2 30/30**; FX-NEW2 (unacc. heavy) R3, warning `WORKER_ACCLIMATISING`.
- 09:00 reading 30.2 → permit R3; FX-NEW2 R4 → removed from crew_present, `HEAT_STOP_FOR_WORKER`.
- 10:15 reading 30.7 → acc. heavy **R4** → permit Suspended `heat_stress_stop` by 10:16 (routine).
- 10:30 30.4, 10:45 30.3, 11:00 30.1 (all R3). The 10:15 reading applies until 10:45:00 → Resume at 10:44 → `HEAT_STOP`; at **10:45** allowed (receiver; no gas test, Z-TWB is not a gas-test zone).
- 11:45 ban pre-warning; 12:00 Suspended `midday_ban` (Phase 3 HT-3).

**HS6 — heat-illness context (Ganesh, the W1 #4 GULFPAVE case, event 2026-09-22 13:50, Z-APR-21).** Reading WBG-ANIA-EXP-20260922-0032 at 13:45 = **30.4** (current); labourer → heavy; acclimatised (the generator gives him gate entries on ≥ 7 of the 14 days before 2026-05-01, so no plan); regime **R3 15/45**; ban not in force (after 09-15); HEAT-AWR in force; last welfare check RS-SAIR-01 07:30 pass; hold MFH-ANIA-EXP-2026-00019. Review by Noura 2026-09-24: HC3 = **no** (crew worked about 40 min without rest) → control_gap = **true**.

**HS7 — KPI fixture = seed (September 2026; Appendix A.8).**

| Metric | ANIA-EXP calculation | ANIA-EXP | RBT-52 calculation | RBT-52 |
|---|---|---|---|---|
| K-97 | (328 + 312) ÷ (330 + 330) × 100 = 96.969… | **97.0 %** | 310 ÷ 330 × 100 = 93.939… | **93.9 %** |
| K-98 | S-AIR zones 3 × 47 h | **141.0 h** | Z-TC01 + Z-FAC 2 × 38 h | **76.0 h** |
| K-99 | 58 ÷ 60 × 100 = 96.666… | **96.7 %** | 30 ÷ 30 | **100.0 %** |
| K-100 | 2 violations ÷ 70 patrols × 100 = 2.857… | **2 · 2.86** | 0 ÷ 32 | **0 · 0.00** |
| K-101 | 1,087 ÷ 1,120 × 100 = 97.053…; chip 116 ÷ 120 = 96.7 % | **97.1 %** | 566 ÷ 580 × 100 = 97.586…; chip 60 ÷ 60 | **97.6 %** |
| K-102 | 44 ÷ 48 × 100 = 91.666… | **91.7 %** | 9 ÷ 9 | **100.0 %** |
| K-103 | 1 case (MTC); 1 × 200,000 ÷ 870,000 = 0.2298… | **1 · 0.23** (recordable 1 · 0.23) | 0 | **0 · 0.00** |

Expected warnings for September 2026: **E16 ANIA-EXP** (2 violations; project and the RAWABI tree, which contains SAHARA via NAJD) · no E16 RBT-52 · **E17 ANIA-EXP** (HIL-ANIA-EXP-2026-014 control gap; tree RAWABI) · **E17 RBT-52** (K-97 93.94 < 95.0; tree QIMMA).

**HS8 — season 2026 (ANIA-EXP, 2026-05-01 → 09-30).** K-01 = 800,000 + 830,000 + 850,000 + 860,000 + 870,000 = **4,210,000**. Heat-illness entries 16 (MTC 6, FAC 10) → rate 16 × 200,000 ÷ 4,210,000 = **0.76**; recordable 6 × 200,000 ÷ 4,210,000 = **0.29**. Ban zone-days 93 × 4 = 372, patrolled 360 → K-99 **96.8 %**; violations **9**.

**HS9 — edges.** (a) K-97 = 9,495 ÷ 10,000 = 94.95 → displays **95.0 %**, E17 **raised**. (b) A patrol at 15:00:00 on 2026-09-15 is accepted (ban hours inclusive, as HT-1); 15:00:01 → `NOT_IN_BAN_WINDOW`; any time on 2026-09-16 → `NOT_IN_BAN_WINDOW`. (c) HSM-ANIA-EXP-02 calibration valid to 2026-10-20: alerts **2026-09-20, 2026-10-06, 2026-10-13, 2026-10-20**; a reading dated 2026-10-21 → `INSTRUMENT_CALIBRATION_EXPIRED`.

## 7. Alerts & expiries

Channels as Phases 1–6a: in-app and email in the recipient's language; "SMS" items are sent in-app + email until an SMS channel exists (DECISIONS #124). Each (subject, step) is sent once; re-running a job never sends twice.

| Trigger | Recipient | Timing | Channel |
|---|---|---|---|
| Regime raised / stop / may resume (HA-1, HA-2) | Site engineers of the site; receivers and issuers of outdoor permits in the zone; Contractor HSE Reps of engagements on the site; HSE Officers | Within 60 s; ≤ 1 per (zone, regime, direction) per 60 min | In-app + push; SMS on stop |
| Reading overdue (HA-4) | HSE Officers; site engineers | 15 min into the slot, once per zone per slot | In-app |
| Ban pre-warning, non-permit (HA-6) | Site engineers; Contractor HSE Reps on sites with required zones | 12:00 − prewarn, ban dates | In-app + push |
| Ban violation (MB-3) | Contractor HSE Rep of the engagement and its tier-1 parent; HSE Officers; HSE Manager | Immediately | In-app + email |
| Exemption granted / ending tomorrow / revoked | HSE Officers; Contractor HSE Rep of the engagement | Immediately / 07:04 the day before date_to | In-app |
| Critical welfare fail (RS-3) | Site engineer; HSE Officer; CA owner | Immediately | In-app + email |
| Welfare checks missing yesterday (controls period) | HSE Officer; site engineer | 07:04 | In-app |
| Plan created (heat duty list) | Contractor HSE Rep and receivers of the engagement (type per P6b-3) | At creation | In-app |
| Plan day not confirmed (AP-8) | Contractor HSE Rep; HSE Officer after a further 24 h | At the deadline | In-app |
| Heat-illness entry created | HSE Officers; OH Practitioners; HSE Manager when the nature is heat_stroke | Within 60 s | In-app + email |
| Heat-illness review overdue (HI-4) | HSE Officer; HSE Manager after a further 2 days | At the deadline, then daily 07:04 | In-app + email |
| Instrument calibration expiry | HSE Officers | 30 / 14 / 7 / 0 days, 07:04 | In-app + email |
| Required zone without an active point | HSE Officers; HSE Manager | When it arises; daily in the controls period | In-app |
| E16 / E17 | HSE Manager; HSE Officers; tier-1 Contractor HSE Rep for its tree | Monthly job, day 2, 07:00 | In-app + email |

## 8. Reports / KPIs fed

### 8.1 Dashboard additions (Phase 1 §8.1)
1. **Leading tiles:** K-97 monitoring coverage · K-99 ban patrol coverage (chip K-100 violations) · K-101 welfare compliance (coverage chip) · K-103 heat-illness cases (rate chip).
2. **Heat band** (live): per required zone the current WBGT, age of reading, state, the regime for light / moderate / heavy (acclimatised; unacclimatised on hover), ban in force, active exemptions; acclimatising workers today (count); open log reviews.
3. **Charts:** C25 daily maximum WBGT per monitoring point with regime bands for the headline workload; C26 zone-hours by regime per month (stacked, K-98); C27 heat-illness cases per week (bars) against the weekly maximum WBGT (line). Phase 1 C8 gains the heat-illness log as its heat-case source from `heat_register_from`.
4. Filters D-2 apply, plus zone.

### 8.2 Expiring items and action panel
- `ExpiringItemKind`: `heat_instrument_calibration`, `ban_exemption_end`.
- Action panel: required zones without a point; readings overdue now; zones at R4 with an Active outdoor permit not yet suspended (must be 0); ban violations whose CA is not In Progress; patrol or welfare coverage missed yesterday; plan days unconfirmed > 24 h; heat-illness reviews overdue; active non-permit exemptions; quarantined instruments still named on a point.

### 8.3 Registers
Readings (with regime cells), instruments, monitoring points, rest stations, welfare checks, patrols, exemptions, acclimatisation plans (type per P6b-3), heat-illness log (P6b-2). Exports (176) write an `export` audit row (as DECISIONS #78).

### 8.4 Heat duty list and season report
- **Heat duty list** (per engagement and day, 166): workers acclimatising (day, max minutes), workers "Not for heat work — HSE check" (tier 1 wording for `no_heat_exposure`), the zone regimes now.
- **Season report** (per project and season year): (1) period and coverage K-97, K-99, K-101 by month; (2) WBGT maximum and mean of daily maxima by point and month; (3) K-98 hours by regime by zone; (4) midday ban: patrols, violations by contractor (no names), exemptions granted; (5) acclimatisation: plans by type (post_heat_illness merged into returner), K-102; (6) heat-illness: K-103 by month and category, rate, control-gap share, comparison with the previous season when that season has data, else "—"; (7) HEAT-AWR compliance at the first day of the controls period (Phase 5 K-82 filtered to HEAT-AWR); (8) CAs raised from `heat_check` and their closure; (9) comments. On screen and XLSX; PDF in 6g.

### 8.5 Feeds to other phases
- **Phase 1:** K-97…K-103, E16–E17, T19, T9 dimensions, CA source `heat_check`, AI-19 section "Heat stress" (aggregates), chart C8 source.
- **Phase 3:** blockers `HEAT_STOP`, `WBGT_READING_REQUIRED`, suspension `heat_stress_stop`, crew warnings, pause reason `heat_rest`.
- **6g:** K-99, K-100, K-101 per contractor for the scorecard; the season report in the export pack.

## 9. Acceptance criteria

Fixtures: the Appendix A seed with the Phase 0–6a seeds; clock `HSE_CLOCK_AT` = **2026-10-06 10:00** unless stated. Fixtures marked "summer" advance the clock to the stated 2027 date with `heat_ptw_enforcement_from` = 2026-10-01 and no other seed change. Users as 6a §9.

**Configuration and instruments**
1. **Given** Noura **When** she lowers a regime-table value or edits a setting **Then** 403 (175). Faisal lowers acclimatised heavy R2 from 29.0 to 28.5 **Then** saved and audited; raising it to 29.5 **Then** 422 `REGIME_LOOSENING`.
2. **Given** `wbgt_limit_offset_c` = +0.5 **Then** 422; −1.0 **Then** saved and HS2's offset row holds (27.8 acclimatised moderate = R1).
3. **Given** `heat_controls_period` 06-15 → 09-15 **Then** 422 `PERIOD_TOO_SHORT` (Phase 1 heat_season 06-01 → 09-30 not contained).
4. **Given** an instrument with iso7243_compliant = false **Then** activation 422 `INSTRUMENT_NOT_COMPLIANT`. **Given** HSM-ANIA-EXP-02 **Then** calibration alerts on the HS9c dates; on 2026-10-21 the job quarantines it.
5. **Given** P-SLAND-M1 covers Z-LAY1 **When** a new point also lists Z-LAY1 **Then** 422 `ZONE_ALREADY_COVERED`.
6. **Given** RBT-52 with Z-FAC removed from P-STWR-M1 **When** Faisal sets `heat_ptw_enforcement_from` **Then** 422 `HEAT_COVERAGE_INCOMPLETE` naming Z-FAC; the action panel lists the gap.
7. **Given** device DEV-WS-ANIA-01 **When** it calls any endpoint except reading ingest **Then** 403; after revocation its ingest call **Then** 401.

**Readings and regime**
8. **Given** HS1 **Then** (a) 30.2, (b) 27.0, (c) warning `WBGT_COMPONENT_MISMATCH` with 30.2 stored.
9. **Given** a manual reading with only ta_c = 44.0 **Then** 422 `WBGT_REQUIRED`; wbgt 46.0 **Then** `VALUE_OUT_OF_RANGE`.
10. **Given** Omar enters a reading measured 25 h ago **Then** 422 `BACKDATED_READING`; 3 h ago **Then** saved with late_entry = true and no HA-1 alert.
11. **Given** the station sends the same (device, measured_at) twice **Then** one reading exists.
12. **Given** HS2 **Then** every cell matches for 27.8, 30.2, 31.4 and 32.1, and the clothing rows hold (double_layer_woven R3, vapour_barrier R4).
13. **Given** HS3 **Then** the headline is R2 at 10:00, an alert goes to Omar, Ahmed and Noura, and a 10:15 reading of 27.0 keeps R2 until 10:30:00 and gives R1 after (WR-8).
14. **Given** no reading after 10:00 on P-SAIR-STN **Then** at 10:21 the state is `stale` with R2 kept; a 10:25 reading of 26.0 with an earlier R2 reading still applying keeps R2 until 10:30.
15. **Given** Z-PIERB (no covering point) **Then** its state is `unknown` and it is not a required zone (outdoor_shaded).
16. **Given** Noura voids the 10:00 reading with a 10-char reason **Then** 422; with ≥ 20 chars **Then** voided and the regime is recomputed within 60 s (R1).

**Alerts**
17. **Given** readings at 10:00 (R2), 10:05 (R2), 10:10 (R2) **Then** exactly one HA-1 alert (HA-3).
18. **Given** summer 2027-07-14 with P-SLAND-M1 not read since 09:00 **Then** at 10:15 HA-4 alerts Noura and Fahad once for the 10:00 slot.
19. **Given** summer 2027-07-14 **Then** at 11:45 HA-6 reaches Omar, Fahad, Ahmed and the other Contractor HSE Reps with Mobilised engagements on S-AIR and S-LAND.

**Phase 3 integration (summer, HS5)**
20. **Given** FX-HEAT **Then** each HS5 step happens as stated: R2 at 07:00, `WORKER_ACCLIMATISING` at shift start, FX-NEW2 removed at 09:00 with `HEAT_STOP_FOR_WORKER`, Suspended `heat_stress_stop` (routine) by 10:16, Resume refused at 10:44 with `HEAT_STOP` and allowed at 10:45, `midday_ban` at 12:00.
21. **Given** FX-HEAT suspended `heat_stress_stop` **Then** K-65 does not count it; K-98 counts the stop hours.
22. **Given** an outdoor_direct_sun permit starting 2027-07-14 07:00 on Z-LAY1 with no reading since yesterday **Then** Start 422 blocker `WBGT_READING_REQUIRED`; after the receiver records a manual reading **Then** Start allowed.
23. **Given** the same permit on 2026-10-06 (outside the controls period) or on a project without `heat_ptw_enforcement_from` **Then** no WBGT blocker applies.
24. **Given** a lifting permit (default heat_workload moderate) **When** clothing is changed to vapour_barrier_coveralls at 28.0 **Then** `HEAT_STOP` (eff 39.0).
25. **Given** Ganesh (no_heat_exposure in force to 2026-10-07) **When** he is added as a labourer to an outdoor_direct_sun permit on 2026-10-06 **Then** excluded with `HEAT_RESTRICTION`; Sanjay (receiver, tier 1) sees "Not eligible — HSE check"; Noura (156) sees the restriction. As permit supervisor (key role) **Then** blocker `KEY_ROLE_INELIGIBLE`.
26. **Given** Ganesh on an outdoor_shaded permit on 2026-10-06 (outside the controls period) **Then** allowed; on 2027-07-14 with the restriction still in force **Then** excluded (PH-6).
27. **Given** an indoor permit at R4 outside **Then** no heat blocker, warning or exclusion (PH-8).
28. **Given** a CSE permit in regime R2 **When** a `heat_rest` pause of 30 min ends **Then** the GT-4 post-break test is required before work restarts (PH-4).

**Acclimatisation**
29. **Given** HS4a **Then** plan days, percentages and minutes are as stated and the plan is Completed after 06-07.
30. **Given** HS4b **Then** the first plan is Interrupted and a new plan starts on 06-08 with day 1 = 20 %.
31. **Given** HS4c **Then** a returner plan starts on 07-08 at 50 %.
32. **Given** Ahmed records prior_heat_experience with 12 chars **Then** 422; with ≥ 20 chars on day 1 **Then** the schedule becomes 50/60/80/100; on day 3 **Then** 422 `TOO_LATE_TO_CHANGE`.
33. **Given** HS4d **Then** Ganesh's plan is Waiting Restriction at the clock and on 2026-10-08. **When** Dr. Huda accepts a new GEN-FIT fit (no restriction) **Then** the plan becomes Planned and starts on his next worked day.
34. **Given** Ahmed (no capability 156) views Ganesh's plan **Then** type "returner" and trigger "absence"; Noura sees post_heat_illness and the hold reference (P6b-3).
35. **Given** a plan day of 2027-06-03 not confirmed by 2027-06-05 00:00 **Then** Ahmed is alerted, and Noura 24 h later; the plan does not count as completed as planned (K-102).
36. **Given** a new_worker plan still Planned on 2027-09-30 **Then** on 10-01 it is Cancelled `season_ended`; a post_heat_illness plan is not.
37. **Given** a heat_outdoor labourer with 9 worked days in 2027-04-17…04-30 **Then** no period_start plan on 05-01; one with 4 worked days **Then** a period_start plan (50 % on his next worked day).

**Welfare checks**
38. **Given** a check at RS-SAIR-01 with HW05 = fail **Then** one CA (source `heat_check`, priority high, due +24 h) and alerts to Omar and Noura; a check failing only HW07 **Then** no CA.
39. **Given** water_temp_c 18.0 with HW02 = pass **Then** HW02 is stored as fail (cool_water_max_c 15.0).
40. **Given** HW10 = na while Z-APR-21 is at R2 **Then** 422 `NA_NOT_ALLOWED`; at R0 **Then** accepted.
41. **Given** an inactive station **Then** 422 `STATION_INACTIVE`. **Given** Ramesh (C1, NAJD Mobilised on S-LAND) **Then** he may check RS-SLAND-01 but gets 404 for RS-TWR-01.

**Midday ban (non-permit)**
42. **Given** HS9b **Then** the patrol times are accepted or refused as stated.
43. **Given** Ahmed **When** he records a patrol **Then** 403 (MB-1). Fahad records `violation` on Z-LAY1 without headcount **Then** 422; with SAHARA, 4, "loading scaffold tubes" **Then** a CA is created (due next day 12:00) and Ahmed (RAWABI tree), the SAHARA rep, Noura and Faisal are alerted.
44. **Given** Noura **When** she grants an exemption **Then** 403. Faisal grants MBX for RAWABI on Z-LAY1 for 2027-07-20…07-21 with reason emergency_repair and controls ≥ 30 chars **Then** active and in the action panel; 15 days **Then** 422; dates outside the ban period **Then** 422 `OUTSIDE_BAN_PERIOD`.
45. **Given** a patrol `exempt_work` for GULFPAVE on Z-LAY1 on 2027-07-20 **Then** 422 `NO_ACTIVE_EXEMPTION` (the exemption covers RAWABI only); for RAWABI **Then** accepted.
46. **Given** an exemption active on 2027-07-20 **When** Z-LAY1 reaches R4 for moderate work **Then** the stop alert is still sent (MB-6).
47. **Given** a violation with a permit_id **Then** the Phase 3 action-panel item appears for that permit (MB-4).

**Heat-illness log**
48. **Given** the W1 #4 heat-exhaustion case (Ganesh) **Then** HIL-ANIA-EXP-2026-014 exists with the HS6 context, and Noura's review makes control_gap true (HI-5).
49. **Given** a FAC case with nature heat_exhaustion **Then** an entry is created (any category, HI-1); a case with nature laceration **Then** none.
50. **Given** a referral `heat_illness_episode` at 2027-07-14 11:00 and a heat-exhaustion case for the same worker created 2027-07-15 09:00 **Then** one entry, source = the case, related_referral_id set; a case created 2027-07-16 12:00 (> 48 h) **Then** two entries.
51. **Given** an entry open for 3 days **Then** Noura is alerted; after 2 more days Faisal.
52. **Given** the source incident is Voided **Then** the entry is Voided and leaves K-103.
53. **Given** Sanjay (receiver) **When** he opens the log **Then** 403. **Given** Ahmed **Then** he sees RAWABI-tree entries with worker_no only and no review text; every read writes `sensitive_field_read` (P6b-2).

**KPIs, warnings, AI, season report**
54. **Given** September 2026 **Then** K-97…K-103 match HS7 for both projects.
55. **Given** September 2026 **Then** E16 and E17 are raised exactly as HS7 lists, with the T13 inputs and no names.
56. **Given** HS9a **Then** K-97 displays 95.0 % and E17 is raised.
57. **Given** HS8 **Then** the ANIA-EXP 2026 season draft shows K-01 4,210,000, 16 heat-illness cases, rate 0.76, recordable 0.29, K-99 96.8 % and 9 violations.
58. **Given** Faisal issues the 2026 report **Then** r1 is frozen; a later void of a September patrol changes the draft but not r1; re-issue creates r2 and marks r1 superseded. Sarah sees only issued revisions; Noura **When** she issues **Then** 403.
59. **Given** the AI is asked "how many heat-illness cases did GULFPAVE have in September and on which zone?" **Then** T19 returns the count (displayed "<3" to roles below the HSE Manager, HM-3) and no worker data; T9 with `wbgt_regime_at_event` returns groups with `sample_sufficient`.
60. **Given** patrol photos older than 24 months **Then** the retention job purges them (`retention_purge`); readings older than 5 years are deleted.
61. **Given** the UI in Arabic **Then** every 6b label, status, list value, alert and error has its AR text; WBGT values, times and codes stay left-to-right inside the RTL layout.

## 10. Open questions for the HSE Manager

Each has a default so the build can start.
1. **Regime basis:** ACGIH TLV / Action Limit table (default). Does a client or PMC heat procedure (heat index or another WBGT table) govern instead? It can be entered as lower limits.
2. **Controls period 05-01 → 09-30 and monitoring 07:00–18:00:** right for Riyadh. A coastal (Jeddah, Dammam) project needs a longer period and night monitoring because of humidity. Widen?
3. **Headline workload for alerts:** heavy (most outdoor trades here). Moderate would mean fewer alerts.
4. **WBGT stop as a routine suspension** (not in K-65), resumed by the receiver without the issuer. Treat it as non-routine instead?
5. **Acclimatisation is a warning, not a block** at permits and gates. Block unacclimatised workers on outdoor permits at R2 or above?
6. **HEAT-EXPOSURE-FIT** (6a) is not required by default. Require it for all `heat_outdoor` workers, or only for returners after heat illness?
7. **Patrol frequency** one per required zone per ban day; contractors may not record patrols. Enough, and who patrols on Fridays?
8. **Exempt activities** under the MHRSD decision: which activities does the client accept as exempt, and should anyone besides you grant non-permit exemptions?
9. **Weather station:** which make or API will the PMC install, and does the client want NCM heat warnings shown on the board?
10. **Wearables** (heart rate, core temperature) stay out of scope as health data. Confirm.

## 11. Changes required in earlier specs (to be applied by the coordinator; this spec does not edit them)

### 11.1 `0-foundation.md` v1.0 → v1.1 (adds to the 6a changes)
1. Matrix rows 166–177 (§5.13).

### 11.2 `1-dashboard.md` v1.5 (after 6a) → v1.6
1. §3.8 CA `source_type` adds `heat_check` (source_id = welfare check or patrol).
2. §5.9 AI: T19 (HM-2); T13 returns E16–E17; T9 dimensions `wbgt_regime_at_event`, `acclimatisation_at_event`; AI-19 section "Heat stress".
3. §6.9 / §7: E16–E17 (§6.8 here), same monthly job and recipients.
4. §8.1: tiles, heat band, charts C25–C27, C8 heat-case source; `ExpiringItemKind` and action-panel items of §8.2.
5. **Seed:** the September 2026 GULFPAVE heat-exhaustion case (W1 #4) has zone Z-APR-21 and occurred_at 13:50; the generator places the Jun–Aug heat cases as HS8 requires (heat MTC Jun 2, Jul 2, Aug 1; heat FAC Jun 3, Jul 4, Aug 3; Sep FAC 0). No KPI value changes (W3 counts are unchanged).

### 11.3 `2-access-permits.md` v1.4 (after 6a) → v1.5
1. §3.19 devices gain kind `weather_station`: not bound to a gate, may call only the 6b reading-ingest endpoint, same token, rotation and revocation rules (GC-1).
2. 6b consumes `gate.check_recorded` (6a §11.3 item 5) for worked days. No behaviour change.

### 11.4 `3-ptw.md` v1.3 (after 6a) → v1.4 — the WBGT-driven pause and suspension
1. **§3.2 permit:** add `heat_workload` (list WL; required when exposure is outdoor_*; default by type: hot_work moderate, confined_space heavy, work_at_height moderate, excavation heavy, electrical_isolation light, lifting moderate, radiography light, airside_works heavy, general moderate; the heaviest type default wins for multi-type permits, ASSUMPTION) and `heat_clothing` (list CL, default work_clothes; `hood` bool).
2. **§3.13 shift:** add `wbgt_reading_id` (the zone reading in force at shift start, or a manual reading by the receiver) and show the regime with rest minutes per hour. `ambient_temp_c` stays.
3. **§3.13 pauses:** reason list adds `heat_rest` راحة حرارية. SH-9 limits are unchanged.
4. **List SR:** add `heat_stress_stop` إيقاف بسبب الإجهاد الحراري, routine = true (excluded from K-65 like `midday_ban`).
5. **List B / PT-16:** add Issue-time blockers `HEAT_STOP` and `WBGT_READING_REQUIRED` (PH-2, PH-3), checked at Start, Revalidate, Resume and handover acceptance. **SH-2** adds the automatic suspension `heat_stress_stop` within 60 s of `heat.regime_changed` (new 6b event). **SH-3:** resume after `heat_stress_stop` follows PH-3 (receiver; no issuer cause text).
6. **Crew rules:** a crew-eligibility step "heat" after the hook steps: `HEAT_RESTRICTION` exclusion or `KEY_ROLE_INELIGIBLE` (PH-6), `HEAT_STOP_FOR_WORKER` removal from crew_present (PH-5), warning `WORKER_ACCLIMATISING` (PH-7).
7. **HT-5:** replace "WBGT-based work/rest regimes are Phase 6" with "WBGT regimes, stops and rest pauses come from `6b-heat-stress.md` from `heat_ptw_enforcement_from`". HT-1…HT-4 and HT-6 unchanged.
8. **§8.3 action panel:** "outdoor work during midday ban on a permit" (from MB-4).
9. All six items apply only on projects with `heat_ptw_enforcement_from` ≤ today; Phase 3 ACs stay valid on the Phase 3 seed.

### 11.5 `6a-occupational-health.md` v1.0 → v1.1
1. `exposure_group_trade_defaults.heat_outdoor` default = labourer, steel_fixer, steel_erector, scaffolder, rigger, mason, carpenter, flagman, welder (add only). Existing profiles get the group lazily, as DECISIONS #127.
2. RW-4: "the heat-illness log is `6b-heat-stress.md` §3.11; it links 6a holds and stores no clinical data".
3. When 6b `heat_fitness_required` = true, a hook-free manual plan line `exposure_group heat_outdoor → HEAT-EXPOSURE-FIT` (due 0) is created.
4. 6b consumes `medical.hold_changed` (release → AP-1c) and `medical.fitness_changed` (AP-6). No 6a behaviour change.

### 11.6 `5-training.md` v1.0 → v1.1 (adds to the 6a changes)
1. **GP-6:** the refresher plan date for HEAT-AWR = min(valid_until − `refresher_planning_days`, start of the earlier of Phase 1 `heat_season` and 6b `heat_controls_period`, minus 60 days). With the defaults: 05-01 − 60 = 03-02.

## Appendix A — Seed data (fictional; `seed_fake = true`; serials, devices and certificate numbers contain `TEST`)

### A.1 Principles
- Builds on the Phase 0–6a seeds. Clock `HSE_CLOCK_AT` = 2026-10-06T10:00:00+03:00.
- `heat_register_from` = **2026-05-01** on both projects (6b in use for the 2026 season); `heat_ptw_enforcement_from` = **2026-10-01**. Before 10-01 no Phase 3 heat rule ran, so Phase 3 history is unchanged.
- 2026-10-06 is outside the controls period: no reading is mandatory, but the S-AIR station reports every 15 min (HS3). No seeded reading on 10-06 makes any Phase 3 permit stop.
- Days with work in September 2026: every day (Phase 1 W1, 30 days) on S-AIR, S-LAND, S-TWR and S-POD. If the Phase 1 generator differs, the backend records the difference in DECISIONS (as #121).

### A.2 Instruments, devices and points
| Instrument | Kind | Calibration → | Point | Covers |
|---|---|---|---|---|
| HSM-ANIA-EXP-01 (station sensor, DEV-WS-ANIA-01) | fixed_station | 2027-03-31 | P-SAIR-STN (station, solar) | Z-APR-21, Z-TWB, Z-ILS33R |
| HSM-ANIA-EXP-02 (handheld) | handheld_meter | **2026-10-20** (HS9c) | P-SLAND-M1 (manual, solar) | Z-LAY1 |
| HSM-RBT-52-01 (handheld) | handheld_meter | 2027-02-28 | P-STWR-M1 (manual, solar) | Z-TC01, Z-FAC |

### A.3 Rest stations
| Code | Site · zones | Type · cooling · capacity |
|---|---|---|
| RS-SAIR-01 | S-AIR · Z-APR-21 | cooled_cabin · air_conditioning · 20 |
| RS-SAIR-02 | S-AIR · Z-TWB, Z-ILS33R | mobile_shade_unit · misting · 12 |
| RS-SLAND-01 | S-LAND · Z-LAY1 | shaded_shelter · fans · 30 |
| RS-SLAND-02 | S-LAND · Z-PIERB, Z-MSCP | indoor_rest_area · air_conditioning · 40 |
| RS-TWR-01 | S-TWR · Z-TC01 | cooled_cabin · air_conditioning · 25 |
| RS-TWR-02 | S-POD · Z-FAC | shaded_shelter · fans · 15 |

### A.4 Readings at the clock
P-SAIR-STN on 2026-10-06, every 15 min from 06:00 to 10:00: 24.1, 24.6, 25.0, 25.3, 25.7, 26.0, 26.3, 26.6, 26.8 (08:00), 26.7, 26.8, 26.9, 26.9 (09:00), 27.0, 26.9 (09:30), 27.2 (09:45), **27.8 (10:00)**. Headline (acclimatised heavy): R0 to 06:30, R1 from 06:45 (alert at 06:45), R2 from 10:00 (HS3). P-SLAND-M1: manual by Fahad at 08:00 25.9 and 09:00 26.8 (HSM-ANIA-EXP-02). P-STWR-M1: Lina at 09:00 25.4.

### A.5 Named records
| Record | Data |
|---|---|
| HIL-ANIA-EXP-2026-014 | Ganesh Shrestha (WKR-000033), source the W1 #4 injury case, event 2026-09-22 13:50 Z-APR-21, context HS6, reviewed by Noura 2026-09-24, control_gap true |
| ACP-ANIA-EXP-2026-00412 | Ganesh, post_heat_illness, trigger MFH-ANIA-EXP-2026-00019 released 2026-09-23 06:31, **Waiting Restriction** |
| MBP-ANIA-EXP-2026-00188 | 2026-09-08 12:40, Z-LAY1, Fahad, violation, SAHARA, 4, "loading scaffold tubes in direct sun", CA-ANIA-EXP-2026-0598 (Closed 09-09) |
| MBP-ANIA-EXP-2026-00214 | 2026-09-14 13:15, Z-LAY1, Noura, violation, RAWABI, 3, "unloading cement bags", CA-ANIA-EXP-2026-0611 (Closed 09-15) |
| MBX-ANIA-EXP-2026-004 | RAWABI, Z-LAY1, 2026-07-20 → 07-21, emergency_repair, "Water main repair; shade canopy; 15/45 regime; paramedic on standby", Faisal, Expired |
| HWC-ANIA-EXP-2026-03117 | RS-SAIR-01, 2026-09-22 07:30, Omar, all pass, water 12.5 °C |

### A.6 Season 2026 history (generator)
- Readings: station every 15 min 05:00–20:00 for 2026-05-01…09-30; manual points hourly in monitoring hours, with the misses of A.8. Daily maxima on P-SAIR-STN: May 27–30, Jun–Aug 29–33, Sep 28–31.
- Acclimatisation plans: created per AP-1 from the Phase 2 mobilisation dates and gate logs; confirmations as A.8.
- Heat-illness entries 16 on ANIA-EXP (HS8), with 10 FAC and 6 MTC per §11.2 item 5; 2 on RBT-52 (FAC, July).
- Patrols, welfare checks and violations per A.8; 9 ANIA-EXP violations in the season (2 in September); 4 exemptions in the season (MBX-001…004).

### A.7 Settings
All 6b settings at the §3.14 defaults on both projects, except the dates in A.1.

### A.8 September 2026 volumes (reproducing HS7)
| Item | ANIA-EXP | RBT-52 |
|---|---|---|
| Monitoring slots required (points × 30 days × 11 h) | 660 (P-SAIR-STN 330, P-SLAND-M1 330) | 330 |
| Covered | 640 (station 328: missing 2026-09-17 10:00 and 11:00; manual 312) | 310 |
| Headline R4 hours on the covering point | 47 (× 3 zones = 141.0) | 38 (× 2 zones = 76.0) |
| Ban dates with work / required zone-days / patrolled / patrols / violations | 15 / 60 / 58 / 70 / 2 | 15 / 30 / 30 / 32 / 0 |
| Station-days required / checked / applicable items / compliant / critical fails (CAs) | 120 / 116 / 1,120 / 1,087 / 6 | 60 / 60 / 580 / 566 / 2 |
| Plans Completed in September / completed as planned | 48 / 44 | 9 / 9 |
| Heat-illness entries | 1 (HIL-…-014) | 0 |

The generator creates only 6b records. It never changes Phase 1–6a records or KPIs, except the two seed details in §11.2 item 5.

## Change log

| Version | Date | Author | Change |
|---|---|---|---|
| v1.0 | 2026-10-09 | HSE Consultant Agent | First issue. §1–§11 and Appendix A: instruments and monitoring points; WBGT readings (manual, station, import); ACGIH-based regime table (tighten only) with clothing and acclimatisation basis; zone heat state with relax and stale rules; heat alerts; acclimatisation plans (new worker, returner, post heat illness, period start); rest stations and welfare checks; midday-ban patrols and HSE Manager exemptions for non-permit work; heat-illness log with exposure context and controls review; Phase 3 WBGT stop, rest pauses and crew heat checks; season report. Capabilities 166–177, KPIs K-97…K-103, warnings E16–E17, AI tool T19, charts C25–C27. 61 acceptance criteria. Earlier-spec changes in §11, not yet applied: 0-foundation, 1-dashboard v1.6, 2-access-permits v1.5, 3-ptw v1.4, 6a v1.1, 5-training. |
