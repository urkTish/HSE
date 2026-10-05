# Module Spec — Phase 0: Foundation

**Version:** v1.0 · **Date:** 2026-10-05 · **Author:** HSE Consultant Agent · **Status:** Draft for HSE Manager review
**Covers:** auth & roles, permission matrix & scoping, projects → sites → zones, contractors, users, audit log, project settings, i18n EN/AR, PDPL baseline.
**Out of scope:** dashboard, man-hours, incidents (Phase 1); permits, certificates, training (Phases 2–5). Anything found for later phases goes to `docs/PROGRESS.md` → "Parked".

Conventions: `VERIFY` = clause/number to be confirmed against current official text. `ASSUMPTION` = default chosen by the Consultant; HSE Manager may override (see §10). All "must" statements are enforced **server-side**.

---

## 1. Purpose

Every later module (incidents, KPIs, permits, certificates) needs the same backbone: who the user is, what they may see, which project/site/zone a record belongs to, which contractor (and tier) is responsible, how dates/rates/languages display, and a tamper-evident trail of who did what. Phase 0 gives the HSE Manager a single place to set up projects (including airport airside/landside zoning), register main and sub-contractors, invite users with scoped roles, and fix project-wide settings — with PDPL protections built in so later modules inherit them instead of re-inventing them.

## 2. Regulatory basis

| # | Source | What it drives here |
|---|---|---|
| R1 | **KSA PDPL** (Royal Decree M/19 of 1443H, amended M/148 of 1444H) + Implementing Regulations; regulator **SDAIA** / National Data Management Office `VERIFY` current amendment status | Data classification, minimisation, purpose limitation, data-subject rights, breach notification, retention, cross-border transfer |
| R2 | PDPL Regulation on Personal Data Transfer outside the Kingdom `VERIFY` | Hosting / backup location of personal data (§5 rule P10) |
| R3 | **NCA Essential Cybersecurity Controls (ECC-2:2024)** — identity & access management, event logs, retention ≥ 12 months `VERIFY` (control numbers and whether ECC applies to the client as a government/CI entity) | Password/lockout/session rules, audit-log retention minimum |
| R4 | **ISO 45001:2018** cl. 5.3 (roles, responsibilities, authorities), 7.5 (documented information, control & retention), 8.1.4 (contractors) | Role definitions, audit trail, contractor register & tiers |
| R5 | **ICAO Annex 14 Vol. I**, **Doc 9981 PANS-Aerodromes**, **Doc 9137 Part 6/8**; **GACAR Part 139** (aerodrome certification) `VERIFY` part numbers | Airside zone attributes: movement area, runway strip/RESA, ILS critical/sensitive areas, OLS height limits, NOTAM dependency, escort/ADP needs |
| R6 | KSA **Commercial Registration Law** (CR via Ministry of Commerce; unified 10-digit national number starting `7` introduced 2025) `VERIFY` format transition | Contractor CR validation |
| R7 | **MHRSD Labour Law** & OSH regulations — contractor/employer responsibility | Contractor accountability chain (tier/parent) |
| R8 | OSHA 29 CFR 1904 rate logic (200,000 h base); client/industry LTIFR (1,000,000 h base) | KPI normalisation setting |
| R9 | Umm al-Qura calendar (official KSA Hijri calendar) | Hijri display |

Strictest-wins: where client standard (e.g. airport operator cybersecurity policy) is stricter than R3, the client value is entered in settings and the system enforces the stricter one.

## 3. Entities & fields

PDPL column: **none** / **personal** / **sensitive**. Arabic label shown in UI for each user-facing field.

### 3.1 Project — مشروع

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| code | رمز المشروع | string(12) | Y | `^[A-Z0-9-]{3,12}$`, unique | `ANIA-EXP` | none |
| name_en / name_ar | اسم المشروع | string(150) ×2 | Y/Y | non-empty; name_ar must contain Arabic script | Al-Noor Intl Airport Expansion / مشروع توسعة مطار النور الدولي | none |
| project_type | نوع المشروع | enum | Y | `airport`, `building_highrise`, `infrastructure`, `industrial`, `other` | airport | none |
| is_airport | مشروع مطار | bool | Y | derived = (project_type = airport) | true | none |
| client_name_en/ar | العميل | string(150) | Y | — | Al-Noor Airport Company (fictional) | none |
| city | المدينة | string(80) | Y | — | Riyadh | none |
| start_date / planned_end_date | تاريخ البدء / تاريخ الانتهاء المخطط | date | Y/N | end ≥ start | 2025-03-01 / 2028-12-31 | none |
| status | الحالة | enum | Y | see §4.1 | active | none |
| airport_icao | رمز المطار (ICAO) | string(4) | if airport | `^[A-Z]{4}$`; Saudi codes start `OE` | `OEXX` (fake) | none |

### 3.2 Site — موقع

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| project_id | المشروع | FK | Y | project not `closed` | ANIA-EXP | none |
| code | رمز الموقع | string(12) | Y | unique within project | `S-AIR` | none |
| name_en / name_ar | اسم الموقع | string(150) ×2 | Y/Y | — | Airside Works / أعمال الجانب الجوي | none |
| site_side | جانب الموقع | enum | Y | `airside`, `landside`, `mixed`, `other`; `airside`/`mixed` only if project.is_airport | airside | none |
| gps_lat / gps_lng | الإحداثيات | decimal(9,6) | N | lat 16–33, lng 34–56 (KSA bbox) | 24.95, 46.70 | none |
| status | الحالة | enum | Y | `active`, `inactive` | active | none |

### 3.3 Zone — منطقة

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| site_id | الموقع | FK | Y | site `active` | S-AIR | none |
| code | رمز المنطقة | string(16) | Y | unique within site | `Z-APR-21` | none |
| name_en / name_ar | اسم المنطقة | string(150) ×2 | Y/Y | — | Apron Stands 21–28 / ساحة الوقوف 21–28 | none |
| zone_type | نوع المنطقة | enum | Y | `airside` (جوي), `landside` (أرضي), `other` (أخرى); `airside`/`landside` only if project.is_airport; must not contradict site_side (airside site → airside zones only; landside site → landside/other) | airside | none |
| status | الحالة | enum | Y | see §4.4 | active | none |
| **Airside attributes** (required block when zone_type = airside, must be null otherwise) | | | | | | |
| airside_area | نوع المنطقة الجوية | enum | Y | `runway`, `runway_strip`, `resa`, `taxiway`, `taxiway_strip`, `apron`, `ils_critical`, `ils_sensitive`, `airside_road`, `other_airside` | apron | none |
| in_movement_area | ضمن منطقة الحركة | bool | Y | true for runway/taxiway/apron/strips/resa | true | none |
| runway_ref | مرجع المدرج | string(10) | N | `^\d{2}[LRC]?/\d{2}[LRC]?$` | 15L/33R | none |
| security_restricted_area | منطقة أمنية مقيدة | bool | Y | default true | true | none |
| notam_required_for_works | يتطلب إشعار NOTAM | bool | Y | default true if in_movement_area | true | none |
| ols_height_limit_m_amsl | حد ارتفاع الأسطح (م فوق سطح البحر) | decimal(7,2) | N | 0–3000 | 642.50 | none |
| max_equipment_height_m_agl | أقصى ارتفاع للمعدات (م فوق الأرض) | decimal(6,2) | N | 0–300 | 12.00 | none |
| escort_required | يتطلب مرافقة | bool | Y | — | true | none |
| adp_required | يتطلب تصريح قيادة جوي | bool | Y | — | true | none |
| fod_control_required | يتطلب التحكم بالأجسام الغريبة | bool | Y | default true | true | none |
| works_safety_plan_ref | مرجع خطة سلامة الأعمال | string(40) | N | — | WSP-APR-004 | none |

Phase 0 only stores these attributes; Phases 2–3 will enforce them (escort, ADP, NOTAM, crane height).

### 3.4 Contractor (master record) — مقاول

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| legal_name_en / legal_name_ar | الاسم التجاري | string(200) ×2 | Y/Y | unique (case/diacritic-insensitive) | Al-Rawabi Construction Co. / شركة الروابي للمقاولات | none |
| short_code | الرمز المختصر | string(10) | Y | `^[A-Z0-9]{2,10}$`, unique | RAWABI | none |
| cr_number | رقم السجل التجاري | string(10) | Y | 10 digits; unique; legacy prefix `1/2/4/5` or unified prefix `7` `VERIFY` | 1010000001 | none |
| cr_expiry_date | تاريخ انتهاء السجل | date | N | ASSUMPTION: optional (unified CR may have no expiry) `VERIFY` | 2027-06-30 | none |
| vat_number | الرقم الضريبي | string(15) | N | 15 digits, starts and ends with `3` | 300000000000003 | none |
| contractor_category | الفئة | enum | Y | `civil`, `mep`, `steel`, `airfield`, `scaffolding`, `lifting`, `facade`, `specialist`, `consultant`, `other` | civil | none |
| primary_contact_name | اسم جهة الاتصال | string(120) | Y | — | Ahmed Al-Zahrani | personal |
| primary_contact_mobile | جوال جهة الاتصال | string(13) | Y | E.164 KSA mobile `^\+9665\d{8}$` (foreign E.164 allowed) | +966500000101 | personal |
| primary_contact_email | بريد جهة الاتصال | email | Y | RFC 5322 | rawabi.hse@example.com | personal |
| status | الحالة | enum | Y | see §4.2 | approved | none |
| status_reason | سبب الحالة | text(500) | cond. | required for suspended/blacklisted | — | none |

### 3.5 Project engagement (contractor on a project) — ارتباط المقاول بالمشروع

Tier and parent are **per project** (a firm may be main contractor on one project and subcontractor on another).

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| project_id, contractor_id | المشروع، المقاول | FK | Y | unique pair | ANIA-EXP, NAJD | none |
| tier | المستوى | int | Y | 1 = main contractor (مقاول رئيسي), 2 = subcontractor (مقاول باطن), 3 = sub-subcontractor (مقاول باطن من الدرجة الثانية); max 3 ASSUMPTION | 2 | none |
| parent_engagement_id | المقاول الأعلى | FK | cond. | null iff tier = 1; parent.tier = tier − 1; same project; no cycles | RAWABI@ANIA-EXP | none |
| scope_of_work_en/ar | نطاق العمل | text(500) | Y | — | Structural steel erection, Pier B | none |
| site_ids | المواقع | FK[] | Y | ≥ 1, sites of same project | S-LAND | none |
| mobilisation_date / demobilisation_date | تاريخ التعبئة / التسريح | date | Y/N | demob ≥ mob | 2025-05-01 | none |

### 3.6 User — مستخدم

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| email (login) | البريد الإلكتروني | email | Y | unique, lower-cased | noura.qahtani@example.com | personal |
| full_name_en / full_name_ar | الاسم الكامل | string(120) ×2 | Y/N | — | Noura Al-Qahtani / نورة القحطاني | personal |
| mobile | الجوال | string(15) | N | E.164 | +966500000002 | personal |
| employer_type | جهة العمل | enum | Y | `client`, `pmc_consultant`, `contractor` | contractor | personal |
| employer_contractor_id | المقاول | FK | cond. | required iff employer_type = contractor | NAJD | personal |
| job_title | المسمى الوظيفي | string(80) | N | — | HSE Officer | personal |
| preferred_language | اللغة المفضلة | enum | Y | `en`, `ar`; default = project default_language | ar | none |
| status | الحالة | enum | Y | see §4.3 | active | none |
| password_hash | — | string | Y | Argon2id/bcrypt; never returned, logged or exported | — | sensitive (secret) |
| mfa_enabled | التحقق الثنائي | bool | Y | default false; see §10 Q3 | false | none |
| last_login_at, failed_login_count, locked_until | — | timestamp/int | — | system-managed | — | personal |
| privacy_notice_ack_at / version | إقرار إشعار الخصوصية | timestamp / string | Y before first use | — | 2026-10-05T08:00Z / PN-1.0 | personal |

**Not collected in Phase 0 (minimisation):** National ID/Iqama, nationality, date of birth, photo, medical data. These arrive only with the module that needs them (Phases 2/4/5) under §5.9 rules.

### 3.7 Role assignment — إسناد الدور

| Field | AR label | Type | Req | Validation | Example |
|---|---|---|---|---|---|
| user_id | المستخدم | FK | Y | user not deactivated | — |
| role | الدور | enum | Y | §3.8 | contractor_hse_rep |
| project_id | المشروع | FK | cond. | null only for `hse_manager` (org-wide) | ANIA-EXP |
| site_ids | المواقع | FK[] | N | empty = all sites of project; sites must belong to project | [S-AIR] |
| contractor_engagement_id | المقاول | FK | cond. | **required** for contractor_hse_rep and permit_receiver; must equal user's employer on that project | RAWABI@ANIA-EXP |
| valid_from / valid_to | من / إلى | date | Y/N | to ≥ from | 2026-01-01 / — |

### 3.8 Roles — الأدوار

| Code | EN | AR | Scope |
|---|---|---|---|
| hse_manager | HSE Manager (admin) | مدير الصحة والسلامة والبيئة (مسؤول النظام) | Organisation (all projects) |
| hse_officer | HSE Officer | مسؤول الصحة والسلامة والبيئة | Assigned project(s) |
| site_engineer | Site Engineer / Supervisor | مهندس / مشرف الموقع | Assigned project, optionally sites |
| permit_issuer | Permit Issuer | مُصدِر التصريح | Assigned project, optionally sites |
| permit_receiver | Permit Receiver | مستلم التصريح | Assigned project + own contractor |
| contractor_hse_rep | Contractor HSE Rep | ممثل السلامة للمقاول | Assigned project + own contractor and its downstream subcontractors |
| viewer_client | Viewer / Client | مُطّلع / العميل | Assigned project(s), read-only |

### 3.9 Project settings — إعدادات المشروع

| Key | AR label | Type | Default | Allowed |
|---|---|---|---|---|
| ltifr_base_hours | أساس معدل الإصابات المضيعة للوقت | int | 1,000,000 | 200,000 · 1,000,000 |
| rate_base_hours (TRIR, DART, LTISR, other rates) | أساس المعدلات الأخرى | int | 200,000 | 200,000 · 1,000,000 |
| timezone | المنطقة الزمنية | IANA tz | Asia/Riyadh | Asia/Riyadh only in v1.0 ASSUMPTION |
| show_hijri | عرض التاريخ الهجري | bool | false | true/false |
| hijri_calendar | التقويم الهجري | enum | umm_al_qura | umm_al_qura |
| default_language | اللغة الافتراضية | enum | en ASSUMPTION | en · ar |
| week_start | بداية الأسبوع | enum | sunday | sunday · monday |
| digits | نمط الأرقام | enum | western (0-9) | western · arabic_indic (٠-٩) |
| date_format_en | تنسيق التاريخ | enum | DD MMM YYYY | DD MMM YYYY · DD/MM/YYYY |
| audit_retention_years | مدة الاحتفاظ بسجل التدقيق | int | 5 ASSUMPTION | 1–10 (min from R3) |
| inactive_account_days | أيام الخمول قبل التعطيل | int | 90 ASSUMPTION | 30–365 |

### 3.10 Audit log entry — سجل التدقيق

| Field | Type | Notes | PDPL |
|---|---|---|---|
| id | UUID | | none |
| occurred_at | timestamptz (UTC) | server clock | none |
| actor_user_id / actor_role / on_behalf_project_id | FK / enum / FK | null actor = system job | personal |
| ip_address, user_agent | string | | personal |
| action | enum | §5.6 list | none |
| entity_type / entity_id | string / UUID | | none |
| project_id | FK | for scoping | none |
| before / after | JSON | changed fields only; personal values stored, **sensitive values masked** (`***`); secrets never | personal |
| fields_read | string[] | for sensitive-read events | none |
| result | enum | `success`, `denied`, `failed` | none |
| request_id | string | correlates with app logs | none |
| prev_hash / hash | string | SHA-256 chain for tamper evidence | none |

## 4. Workflow / states

### 4.1 Project

| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Planning | تخطيط | HSE Manager | Create |
| Planning → Active | نشط | HSE Manager | ≥ 1 site, settings saved |
| Active → On Hold | معلّق | HSE Manager | Reason required |
| On Hold → Active | نشط | HSE Manager | — |
| Active/On Hold → Closed | مغلق | HSE Manager | Reason required; project becomes read-only |
| Closed → Active | نشط | HSE Manager | Reason required (reopen) |

### 4.2 Contractor (master)

| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Draft | مسودة | HSE Manager, HSE Officer | Create |
| Draft → Pending Approval | بانتظار الاعتماد | HSE Officer, HSE Manager | All required fields valid |
| Pending Approval → Approved | معتمد | HSE Manager | — |
| Pending Approval → Draft | مسودة | HSE Manager | Returned with comment |
| Approved → Suspended | موقوف | HSE Manager | Reason required |
| Suspended → Approved | معتمد | HSE Manager | Reason required |
| Approved/Suspended → Demobilised | مُسرَّح | HSE Manager | All engagements have demobilisation_date ≤ today |
| any → Blacklisted | محظور | HSE Manager | Reason required; terminal except Manager "lift blacklist" → Suspended |

### 4.3 User

| From → To | AR | Who | Trigger |
|---|---|---|---|
| — → Invited | مدعو | HSE Manager; HSE Officer (non-admin roles on own projects) | Invite email sent |
| Invited → Active | نشط | User | Sets password via link within 72 h + acknowledges privacy notice |
| Invited → Invited | — | inviter | Re-send (new token, old invalidated) |
| Active → Locked | مقفل | System | 5 failed logins within 15 min |
| Locked → Active | نشط | System (after 15 min) or HSE Manager (unlock) | — |
| Active/Locked → Deactivated | معطّل | HSE Manager; System (inactivity, contractor blacklisted) | Reason recorded |
| Deactivated → Active | نشط | HSE Manager | Forces password reset |

### 4.4 Zone

Active (نشطة) → Temporarily Closed (مغلقة مؤقتاً) → Active; Active/Temporarily Closed → Archived (مؤرشفة). Who: HSE Manager, HSE Officer of the project. Archived zones cannot receive new records; existing records keep the link.

## 5. Business rules

### 5.1 Authentication
1. Login is email + password; email matching is case-insensitive.
2. Password: ≥ 12 characters, at least 3 of 4 classes (upper, lower, digit, symbol), not equal to email local-part, not in a top-10,000 breached-password list. `VERIFY` against R3 and client policy.
3. 5 consecutive failed attempts within 15 min lock the account for 15 min; the response for a wrong email and a wrong password is identical.
4. Sessions expire after 30 min idle and 12 h absolute. ASSUMPTION
5. Password reset tokens are single-use and expire after 60 min; invite tokens expire after 72 h.
6. A user cannot use any feature until `privacy_notice_ack_at` is set for the current notice version; a new version forces re-acknowledgement.
7. Deactivating or locking a user revokes all their active sessions within 60 s.

### 5.2 Roles & scoping
8. Every API request is authorised server-side from the user's **active** role assignments (today within valid_from–valid_to). UI hiding is not a control.
9. Permissions are the union of the user's active assignments **within the project being accessed**; assignments on project A grant nothing on project B.
10. A Contractor HSE Rep or Permit Receiver sees contractor-owned records only where `record.contractor_engagement` is their engagement or a descendant of it (Rep) / exactly their engagement (Receiver). ASSUMPTION (§10 Q1).
11. A role assignment with `site_ids` restricts visibility to records in those sites; project-level records (settings, contractor list) remain visible.
12. Requesting an out-of-scope record by ID returns **404** (not 403) and writes an audit event `access_denied`.
13. There must always be ≥ 1 active HSE Manager; deactivating or demoting the last one is rejected.
14. An HSE Officer may invite users and assign only the roles site_engineer, permit_issuer, permit_receiver, contractor_hse_rep, viewer_client, and only on projects where they hold hse_officer.
15. No user may change their own roles or status.
16. Permit Issuer and Permit Receiver cannot be held by the same user on the same project (segregation of duties for Phase 3 PTW).

### 5.3 Organisation hierarchy
17. A zone belongs to exactly one site; a site to exactly one project; codes are unique within their parent.
18. zone_type `airside` or `landside` is allowed only when project.is_airport = true; non-airport projects use `other`.
19. When zone_type = airside, all required airside attributes (§3.3) must be present; when not airside, they must be null.
20. `in_movement_area` must be true when airside_area ∈ {runway, runway_strip, resa, taxiway, taxiway_strip, apron}.
21. Changes to any airside attribute are audited with before/after values.
22. A project in status Closed rejects every create/update on itself, its sites, zones, engagements and settings (HTTP 409), except reopen by HSE Manager.
23. Sites, zones, projects and contractors are never hard-deleted once referenced; they are archived/inactivated.

### 5.4 Contractors
24. CR number and short_code are unique across all contractors.
25. Engagement tier 1 has no parent; tier n > 1 has a parent engagement on the same project with tier n − 1; max tier 3.
26. A contractor can be engaged on a project only if its status is Approved.
27. Blacklisting a contractor: (a) deactivates every user whose employer is that contractor, (b) end-dates its role assignments, (c) flags descendant engagements "parent blacklisted" for HSE Manager review. Descendants are **not** auto-blacklisted.
28. Suspending a contractor keeps its users' read access but blocks every create/update by those users (HTTP 403 "contractor suspended"). Later phases additionally block permits.
29. A user with employer_type = contractor must have employer_contractor_id; role assignments with contractor scope must match that employer.

### 5.5 Settings
30. Only HSE Manager can change project settings; every change is audited with old/new value.
31. KPI bases accept only 200,000 or 1,000,000; the base in use is printed next to every rate wherever displayed (e.g. "LTIFR (per 1,000,000 h)").
32. Changing a KPI base never changes stored data; all rates are recomputed at read time.
33. All timestamps are stored in UTC; all displays and day boundaries (e.g. "today", daily man-hours in Phase 1) use the project timezone.
34. When show_hijri = true, dates display as Gregorian with Umm al-Qura Hijri in secondary position (e.g. "05 Oct 2026 · 13 Rabi' II 1448 هـ"); input is always Gregorian. ASSUMPTION

### 5.6 Audit log
35. Logged actions (minimum): `login_success`, `login_failed`, `logout`, `account_locked`, `password_reset_requested`, `password_changed`, `mfa_changed`; `user_invited`, `user_status_changed`, `role_assigned`, `role_revoked`; `create`, `update`, `status_change`, `archive` on every entity; `settings_changed`; `sensitive_field_read`; `export`; `access_denied`; `audit_log_viewed`; `retention_purge`.
36. The audit log is append-only: no API or UI path updates or deletes an entry; DB role used by the app has INSERT/SELECT only on the table.
37. Each entry stores `hash = SHA-256(prev_hash + canonical entry)`; a verification job reports any break in the chain to HSE Manager.
38. Readers: HSE Manager = full log; HSE Officer = entries for their projects excluding IP/user-agent and auth events of other users; all other roles = only the change history of records they can already see (who/when/what changed), no IP.
39. Viewing or exporting the audit log is itself logged.
40. Retention: entries older than `audit_retention_years` (min 1 year, default 5) are purged by a monthly job that writes one `retention_purge` entry with the count and date range.

### 5.7 i18n EN/AR
41. Every user-facing string (labels, enums, errors, emails) exists in EN and AR resource files; CI fails on a missing key in either locale.
42. Selecting Arabic sets `dir="rtl"` and `lang="ar"`; layout, icons with direction, tables, breadcrumbs and charts mirror; numbers, codes, emails and CR numbers render LTR inside RTL text.
43. Display language = user preferred_language, falling back to project default_language, then `en`.
44. Bilingual entities show the name in the display language; if the AR name is empty (only allowed for user full_name_ar) the EN name is shown.
45. Search across names normalises Arabic: ignore diacritics (tashkeel) and tatweel, treat أ/إ/آ/ا as ا, ة as ه, ى as ي; English search is case-insensitive.
46. Sorting uses locale collation (Arabic alphabetical order in AR).
47. Emails/notifications are sent in the recipient's preferred language.
48. Server errors return a stable code (e.g. `CONTRACTOR_SUSPENDED`) and the frontend maps it to EN/AR text.

### 5.8 Exports
49. Exports (CSV/Excel) contain only fields the exporting user may read; contact fields are included only for roles with capability 11/3 (§5.10); every export is audited with row count and filter.

### 5.9 PDPL baseline (inherited by all later modules)
- P1. Every field in every spec carries a PDPL class: none / personal / sensitive. Programmers must not add a field without a class.
- P2. **Sensitive** (platform definition, stricter than PDPL where noted): health/medical data, injury details linked to a named person, criminal/security background results, biometric data, and — platform policy ASSUMPTION — government ID numbers (National ID, Iqama, passport).
- P3. Minimisation: collect only fields a spec lists with a stated purpose; free-text fields carry a hint "Do not enter ID or medical details".
- P4. Sensitive fields are returned by the API only to roles granted read on that field; otherwise the field is omitted, or masked (e.g. Iqama `2*******89`) where a spec says so.
- P5. Every read of a sensitive field (detail view, export, API) writes `sensitive_field_read` with the field names.
- P6. Personal data in dashboards/AI answers is aggregated; no names appear in KPI widgets or AI summaries. The AI layer receives no sensitive fields.
- P7. Retention: each entity has a configurable retention period; on expiry personal fields are anonymised (record kept for statistics). Defaults set per module spec.
- P8. Data-subject requests (access, correction, destruction) are logged by HSE Manager in the platform and must be closed within 30 days `VERIFY` PDPL Implementing Regulations deadline.
- P9. Personal-data breach: platform supports an incident record and export of affected-subject list; notification to SDAIA within 72 h of awareness `VERIFY`.
- P10. Production data, backups and file storage are hosted in KSA; any transfer outside KSA requires HSE Manager + client written approval `VERIFY` R2.
- P11. Encryption: TLS 1.2+ in transit; database and object storage encrypted at rest; sensitive columns additionally encrypted at application level.
- P12. Seeds, demos and test fixtures use only fake data (`@example.com`, `+96650000xxxx`, IDs `2XXXXXXXXX`).
- P13. Privacy notice (EN/AR) shown and acknowledged before first use (rule 6); text supplied by client/legal (§10 Q6).

### 5.10 Permission matrix (role × capability)

Legend: **A** = all projects · **P** = assigned project(s) · **S** = assigned sites (or whole project if none set) · **C** = own contractor engagement + downstream subs · **C1** = own engagement only · **R** = read-only · **—** = none.

| # | Capability | HSE Mgr | HSE Officer | Site Eng/Sup | Permit Issuer | Permit Receiver | Contractor HSE Rep | Viewer/Client |
|---|---|---|---|---|---|---|---|---|
| 1 | Create/edit projects; change project status | A | — | — | — | — | — | — |
| 2 | View projects | A | P | P | P | P | P | P |
| 3 | Create/edit/archive sites & zones (incl. airside attrs) | A | P | — | — | — | — | — |
| 4 | View sites & zones (incl. airside attrs) | A | P | S | S | S | S | P |
| 5 | Create contractor / submit for approval | A | P | — | — | — | — | — |
| 6 | Approve, suspend, demobilise, blacklist contractor | A | — | — | — | — | — | — |
| 7 | Create/edit project engagements (tier/parent) | A | P | — | — | — | — | — |
| 8 | View contractor list & engagements | A | P | P | P | C1 | C | P |
| 9 | View contractor contact details | A | P | P | P | C1 | C | — |
| 10 | Invite users / assign roles | A | P (limited, rule 14) | — | — | — | — | — |
| 11 | View user directory (name, role, employer) | A | P | P | P | C1 | C | — |
| 12 | View user email/mobile | A | P | P | P | C1 | C | — |
| 13 | Deactivate / unlock users | A | — | — | — | — | — | — |
| 14 | Edit project settings | A | — | — | — | — | — | — |
| 15 | View project settings | A | P | P | P | P | P | P |
| 16 | Read full audit log | A | P (rule 38) | — | — | — | — | — |
| 17 | View change history of visible records | A | P | S | S | C1 | C | P |
| 18 | Export lists (CSV/Excel) | A | P | S | — | — | C | P (no contacts) |
| 19 | Edit own profile (name, mobile, language, password) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

Later phases extend this table (e.g. PTW issue/receive in Phase 3); they may not loosen Phase 0 rows without a spec version change.

## 6. Calculations

| # | Calculation | Formula | Units / notes |
|---|---|---|---|
| K1 | Generic rate (declared here, used in Phase 1) | rate = count × base ÷ man-hours | base = `ltifr_base_hours` for LTIFR, `rate_base_hours` for others; man-hours = 0 → rate shown as "—" (not 0) |
| K2 | Local date | local_date = (utc_ts converted to project timezone).date | Asia/Riyadh = UTC+03:00, no DST |
| K3 | Hijri display | Umm al-Qura conversion of local_date | Use a library implementing Umm al-Qura tables (e.g. ICU `islamic-umalqura`); no manual arithmetic |
| K4 | Contractor descendants | recursive set of engagements where parent chain reaches the given engagement | Used by rule 10; depth ≤ 2 below tier 1 |
| K5 | Audit purge cutoff | cutoff = now_utc − audit_retention_years | Calendar years |
| K6 | Inactivity | days_inactive = today_local − last_login_at.local_date | Never-logged-in active users counted from activation date |

Worked example K1 (for Phase 1 test continuity): 2 LTIs, 1,250,000 man-hours → LTIFR @1,000,000 = 2 × 1,000,000 ÷ 1,250,000 = **1.60**; @200,000 = **0.32**.

## 7. Alerts & expiries

| Trigger | Recipient | Timing | Channel |
|---|---|---|---|
| Invite sent / not accepted | Invitee; inviter | On send; reminder at 48 h; inviter told at expiry (72 h) | Email |
| Password reset requested | User | Immediately | Email |
| Account locked | User; HSE Manager if ≥ 3 locks in 24 h | Immediately | Email + in-app |
| New login from new device/IP | User | Immediately ASSUMPTION | Email |
| Inactive account | User at day (limit − 7); HSE Manager at deactivation | Daily job | Email |
| Contractor CR expiry | HSE Manager; HSE Officers of engaged projects; Contractor HSE Rep | 30 / 14 / 7 / 0 days before cr_expiry_date | Email + in-app |
| Contractor submitted for approval | HSE Manager | Immediately | In-app |
| Contractor suspended/blacklisted/reinstated | HSE Officers of engaged projects; Contractor HSE Reps of that contractor and its parent | Immediately | Email + in-app |
| Role assignment ending | User; inviter | 7 days before valid_to | Email |
| Project settings changed | HSE Officers of project | Immediately | In-app |
| Audit chain break detected | HSE Manager | On detection (daily job) | Email + in-app |
| Last HSE Manager risk (only 1 active) | HSE Manager | Weekly while true ASSUMPTION | In-app |

## 8. Reports / KPIs fed

Phase 0 computes no HSE KPIs; it supplies the dimensions and settings every KPI uses:

1. Filter dimensions for the Phase 1 dashboard: project, site, zone, zone_type (airside/landside/other), airside_area, contractor, tier, parent contractor.
2. KPI base labels and calculation (K1) driven by settings.
3. Roll-up rule: subcontractor man-hours/incidents roll up to the tier-1 contractor (engagement tree) and are also reportable per tier.
4. Admin lists: users by role/status, contractors by status/tier, upcoming CR expiries, locked/inactive accounts.
5. Audit report: logins, denied accesses, sensitive reads per period (HSE Manager only).

## 9. Acceptance criteria

1. **Given** user `faisal.harbi@example.com` with a correct password **When** they log in **Then** they reach the home screen and a `login_success` audit entry exists.
2. **Given** any email **When** login fails with an unknown email or a wrong password **Then** both responses have identical status and message.
3. **Given** 5 failed logins within 15 min **When** a 6th attempt uses the correct password **Then** it is rejected as locked, the user status is Locked and `account_locked` is logged.
4. **Given** an invite issued 73 h ago **When** the invitee opens the link **Then** it is rejected as expired.
5. **Given** a new active user who has not acknowledged privacy notice PN-1.0 **When** they call any API other than acknowledge/logout **Then** the response is 403 `PRIVACY_ACK_REQUIRED`.
6. **Given** Contractor HSE Rep Ahmed (RAWABI@ANIA-EXP) **When** he lists engagements on ANIA-EXP **Then** he sees RAWABI, NAJD, GULFPAVE and SAHARA, and not QIMMA or DLIFT.
7. **Given** Contractor HSE Rep Yousef (QIMMA@RBT-52) **When** he requests ANIA-EXP project by ID **Then** he gets 404 and an `access_denied` entry is logged.
8. **Given** Permit Receiver Ramesh (NAJD) **When** he views the contractor list **Then** only NAJD is returned and contact fields of other contractors are absent.
9. **Given** Viewer Sarah **When** she sends any POST/PUT/PATCH/DELETE to project data **Then** the response is 403 and nothing changes.
10. **Given** Site Engineer Omar assigned to site S-AIR only **When** he lists zones of ANIA-EXP **Then** only zones of S-AIR are returned.
11. **Given** Faisal is the only active HSE Manager **When** he tries to deactivate himself or remove his role **Then** the request is rejected with `LAST_HSE_MANAGER`.
12. **Given** HSE Officer Noura **When** she tries to assign role hse_manager or hse_officer **Then** the request is rejected with 403.
13. **Given** a user holding permit_issuer on ANIA-EXP **When** permit_receiver on ANIA-EXP is assigned to them **Then** the request is rejected with `SOD_CONFLICT`.
14. **Given** project RBT-52 (building_highrise) **When** a zone with zone_type airside is created **Then** it is rejected with a validation error on zone_type.
15. **Given** a new airside zone with airside_area = taxiway_strip and in_movement_area = false **When** saved **Then** it is rejected.
16. **Given** a landside zone payload containing adp_required = true **When** saved **Then** it is rejected (airside attributes must be null).
17. **Given** a tier-3 engagement whose parent is tier 1 **When** saved **Then** it is rejected; with a tier-2 parent on the same project it succeeds.
18. **Given** a contractor with CR `1010000001` exists **When** another contractor is created with the same CR **Then** it is rejected; CR `12345` is rejected as invalid format.
19. **Given** contractor DLIFT is Suspended **When** a DLIFT user attempts any update **Then** 403 `CONTRACTOR_SUSPENDED`; reads still succeed.
20. **Given** contractor SAHARA is blacklisted with a reason **Then** all SAHARA users become Deactivated, their sessions end within 60 s, and their role assignments are end-dated today.
21. **Given** a contractor in status Pending Approval **When** an engagement is created for it **Then** it is rejected with `CONTRACTOR_NOT_APPROVED`.
22. **Given** project ANIA-EXP is Closed **When** an HSE Officer edits a zone **Then** 409 `PROJECT_CLOSED`.
23. **Given** HSE Manager changes `ltifr_base_hours` from 1,000,000 to 200,000 **Then** a `settings_changed` entry holds old and new values and the label reads "per 200,000 h"; with 2 LTIs and 1,250,000 h the displayed LTIFR changes from 1.60 to 0.32.
24. **Given** `ltifr_base_hours` = 500,000 **When** saved **Then** it is rejected.
25. **Given** a record created at 2026-10-04T22:30:00Z **When** displayed in Asia/Riyadh **Then** its date is 05 Oct 2026 01:30.
26. **Given** show_hijri = true **When** 2026-10-05 is displayed **Then** the Umm al-Qura Hijri date from the conversion library is shown beside it (value asserted against the library, not hard-coded).
27. **Given** the UI language is switched to Arabic **Then** `<html dir="rtl" lang="ar">` is set and the login page shows no untranslated EN key (e2e scan).
28. **Given** contractor "شركة الروابي للمقاولات" **When** a user searches "الروابى" or "شركه الروابي" **Then** RAWABI is found.
29. **Given** an AR resource file missing key `contractor.status.suspended` **When** CI runs **Then** the i18n check fails.
30. **Given** any audit entry **When** an API or DB app-role tries to UPDATE or DELETE it **Then** the operation fails; tampering with an entry's `after` field directly in the DB is reported by the chain-verification job.
31. **Given** HSE Officer Noura **When** she opens the audit log **Then** she sees ANIA-EXP entries only, without IP/user-agent, and an `audit_log_viewed` entry is written.
32. **Given** an audit entry older than `audit_retention_years` **When** the monthly purge runs **Then** it is removed and one `retention_purge` entry records the count and range.
33. **Given** Viewer Sarah exports the contractor list **Then** the file has no contact name/mobile/email columns and an `export` entry with the row count is logged.
34. **Given** the seed data is loaded **Then** every email ends in `@example.com` and every mobile matches `^\+96650000\d{4}$` (CI check).
35. **Given** a user update API response **Then** `password_hash` is never present.

## 10. Open questions for the HSE Manager

1. Contractor HSE Rep visibility: own contractor **plus** its downstream subcontractors (current assumption), or own contractor only? Should a tier-1 rep be able to *edit* subcontractor records?
2. Permit Issuer: must they be client/PMC staff, or may a main-contractor (tier-1) employee issue permits on your projects?
3. MFA: mandatory for HSE Manager/Officer (and is it a client cybersecurity requirement, e.g. NCA ECC applicability)? Which method — authenticator app or SMS/email OTP?
4. KPI bases: confirm the client's convention — LTIFR per 1,000,000 h and TRIR/DART/LTISR per 200,000 h — or one base for all rates?
5. Default UI language for site users: English or Arabic? Do you want Arabic-Indic digits (٠-٩) by default in Arabic?
6. Privacy notice and data-processing basis: will the client/legal team supply the EN/AR privacy notice text, and who is the named data controller (client, PMC or main contractor)?
7. Audit-log retention: does the client or airport operator require more than 5 years (e.g. contract record-keeping clauses)? Any requirement to hold logs in a client-owned SIEM?
8. Hosting: client-mandated hosting (on-prem, specific KSA cloud region) and whether any backup outside KSA is permitted.
9. Maximum subcontractor depth: is tier 3 enough, or do your contracts allow deeper chains?
10. Airside zoning: will the airport operator provide official zone codes/drawings (stand numbers, ILS areas, OLS heights) to load, or will the HSE team define zones?
11. Is a separate "Client" role with approval rights (beyond read-only Viewer) needed, e.g. client HSE sign-off on contractor approval?

---

## Appendix A — Seed data (fictional; all names, codes, CRs, phones and emails are fake)

### A.1 Projects

| Code | Name EN | Name AR | Type | ICAO | City | Status | Settings |
|---|---|---|---|---|---|---|---|
| ANIA-EXP | Al-Noor International Airport — Terminal & Apron Expansion | مشروع توسعة صالة وساحات مطار النور الدولي | airport | OEXX | Riyadh | active | LTIFR 1,000,000; rates 200,000; Hijri on; default ar |
| RBT-52 | Riyadh Business Tower — 52-Storey Mixed-Use | برج الرياض للأعمال — 52 طابقاً | building_highrise | — | Riyadh | active | LTIFR 200,000; rates 200,000; Hijri off; default en |

### A.2 Sites & zones

| Project | Site (side) | Zone code | Zone EN / AR | zone_type | Airside attributes |
|---|---|---|---|---|---|
| ANIA-EXP | S-AIR Airside Works / أعمال الجانب الجوي (airside) | Z-APR-21 | Apron Stands 21–28 / ساحة الوقوف 21–28 | airside | apron; movement area; SRA; NOTAM; escort; ADP; FOD; max equip 12 m AGL; WSP-APR-004 |
| ANIA-EXP | S-AIR | Z-TWB | Taxiway B Strip / شريط الممر B | airside | taxiway_strip; movement area; SRA; NOTAM; escort; ADP; OLS 642.50 m AMSL; max equip 6 m |
| ANIA-EXP | S-AIR | Z-ILS33R | RWY 33R Glide Path Critical Area / المنطقة الحرجة لمسار الانزلاق 33R | airside | ils_critical; runway_ref 15L/33R; not movement area; SRA; NOTAM; escort; ADP; max equip 3 m |
| ANIA-EXP | S-LAND Terminal 3 Building / مبنى الصالة 3 (landside) | Z-PIERB | Pier B Structure / هيكل الرصيف B | landside | — |
| ANIA-EXP | S-LAND | Z-MSCP | Multi-Storey Car Park / مواقف السيارات متعددة الطوابق | landside | — |
| ANIA-EXP | S-LAND | Z-LAY1 | Contractor Laydown Yard 1 / ساحة تخزين المقاولين 1 | other | — |
| RBT-52 | S-TWR Main Tower / البرج الرئيسي (other) | Z-CORE | Tower Core L1–L52 / قلب البرج ط1–ط52 | other | — |
| RBT-52 | S-TWR | Z-TC01 | Tower Crane TC-01 Exclusion Zone / منطقة حظر الرافعة البرجية TC-01 | other | — |
| RBT-52 | S-POD Podium & Basement / المنصة والقبو (other) | Z-B4 | Basement Excavation B1–B4 / حفريات القبو ق1–ق4 | other | — |
| RBT-52 | S-POD | Z-FAC | Facade Hoist Zone / منطقة رافعة الواجهات | other | — |

### A.3 Contractors & engagements

| Code | Name EN | Name AR | CR | Category | Status | Engagement (project · tier · parent) | Contact (fake) |
|---|---|---|---|---|---|---|---|
| RAWABI | Al-Rawabi Construction Co. | شركة الروابي للمقاولات | 1010000001 | civil | approved | ANIA-EXP · 1 · — | rawabi.hse@example.com, +966500000101 |
| NAJD | Najd Steel Erection Est. | مؤسسة نجد لتركيب الحديد | 1010000002 | steel | approved | ANIA-EXP · 2 · RAWABI | najd.hse@example.com, +966500000102 |
| GULFPAVE | Gulf Airfield Paving Co. | شركة الخليج لرصف المطارات | 1010000003 | airfield | approved | ANIA-EXP · 2 · RAWABI | gulfpave.hse@example.com, +966500000103 |
| SAHARA | Sahara Scaffolding Services | شركة الصحراء لخدمات السقالات | 1010000004 | scaffolding | approved | ANIA-EXP · 3 · NAJD | sahara.hse@example.com, +966500000104 |
| QIMMA | Al-Qimma Towers Contracting | شركة القمة لمقاولات الأبراج | 1010000005 | civil | approved | RBT-52 · 1 · — | qimma.hse@example.com, +966500000105 |
| DLIFT | Desert Lift Crane Services | مؤسسة رافعات الصحراء | 1010000006 | lifting | suspended ("TPI certificate lapsed — test data") | RBT-52 · 2 · QIMMA | dlift.hse@example.com, +966500000106 |

### A.4 Users (one per role, plus one extra rep for scoping tests). Seed password set via env var, never committed.

| Name EN / AR | Email | Mobile | Employer | Role · scope |
|---|---|---|---|---|
| Faisal Al-Harbi / فيصل الحربي | faisal.harbi@example.com | +966500000001 | client | hse_manager · org |
| Noura Al-Qahtani / نورة القحطاني | noura.qahtani@example.com | +966500000002 | pmc_consultant | hse_officer · ANIA-EXP |
| Omar Siddiqui / عمر صديقي | omar.siddiqui@example.com | +966500000003 | contractor RAWABI | site_engineer · ANIA-EXP · S-AIR |
| Khalid Al-Otaibi / خالد العتيبي | khalid.otaibi@example.com | +966500000004 | client | permit_issuer · ANIA-EXP |
| Ramesh Kumar / راميش كومار | ramesh.kumar@example.com | +966500000005 | contractor NAJD | permit_receiver · ANIA-EXP · NAJD |
| Ahmed Al-Zahrani / أحمد الزهراني | ahmed.zahrani@example.com | +966500000006 | contractor RAWABI | contractor_hse_rep · ANIA-EXP · RAWABI (+ subs) |
| Sarah Mitchell / سارة ميتشل | sarah.mitchell@example.com | +966500000007 | client | viewer_client · ANIA-EXP, RBT-52 |
| Yousef Al-Ghamdi / يوسف الغامدي | yousef.ghamdi@example.com | +966500000008 | contractor QIMMA | contractor_hse_rep · RBT-52 · QIMMA (+ subs) |

---

### Change log
- v1.0 (2026-10-05) — first issue.
