# Module Spec — Phase 8: Quality (QA/QC) — NCR, ITP and inspection requests, materials and testing, welding, calibration, competence, cold-chain logistics, documents, audits, suppliers, KPIs, SPC, COPQ

**Version:** v1.0 · **Date:** 2026-10-31 · **Author:** Quality Consultant Agent · **Status:** Draft. Turki (owner) asked to build everything and review afterwards (handover §1); defaults are chosen so the build can start (§7).
**Builds on:**
- `docs/HANDOVER-quality.md` (sections 2 and 4 are binding; section 5 sets the packages Q0–Q4 and the integration package I).
- `0-foundation.md` v1.6: projects, sites, zones, engagement tree, roles and scoping legend, rules 8–16, 22, 28, 33–35, 48, PDPL P1–P13, the capability matrix (7b ends at 237).
- `1-dashboard.md` v1.12: corrective actions (§3.8, CA-1…CA-8, `ca_due_days`), K-40…K-43, the KPI engine (K-R1…K-R8), the action panel, `ExpiringItemKind`, AI tools T1…T25 pattern, charts up to C41.
- `2-access-permits.md` v1.6: workers (`user_id` link), vehicles (§3.12), the hook provider interface HK-1…HK-5 (`app/services/access/hooks.py`).
- `4-third-party-cert.md` v1.3: TPIs (kinds `calibration_lab`, `ndt_body`), accreditations, personnel certificates and the in-force predicate, cert types (`cert_types`), equipment items.
- `5-training.md` v1.3: training records and the training-course hook.
- `6d-field-assurance.md` v1.4: checklist templates, scoring (§6.1–§6.2), responses, findings, audits (`field_audits`), offline rules EXE-6.
- `6g-scorecard-reports.md` v1.0: renderer (fpdf2 + HarfBuzz, RP-5), report packs (`rp_packs`), dataset registry (EX-1…EX-11), scorecard maths (`points`, `band`).
- `7b-fleet-driver.md` v2.1: site vehicle readiness and pre-use checks (read only).
- `docs/DECISIONS.md` #1–#307, in particular D-222 (renderer), D-282 (photo shrinking), D-289…D-297 (licence, read-only mode), D-302 (virus scan), D-303 (Hijri).

**Numbering taken by Phase 8:** capabilities **238–280**; roles `qa_qc_manager`, `quality_engineer`, `qc_inspector`, `warehouse_qc`, `responsible_person`; KPIs **K-141…K-169**; warnings **E26–E28**; AI tools **T26–T29**; charts **C42–C51**; CA source types `quality_ncr`, `quality_observation`, `quality_complaint`, `quality_audit`, `quality_review`; 6d template kind `quality` and response owner types §A.7; 6d audit domain `quality` (§E.2); `ExpiringItemKind` values §E.7; report pack types §E.8; project type `logistics`. Decisions **D-308…D-319** for this spec.

**Covers (parts = packages, handover §5):**

| Part | Package | Branch | Content |
|---|---|---|---|
| §3 | all | — | Package boundaries, file ownership, plug-in registries (read first) |
| **A** | **Q0** foundation + NCR core | `claude/quality-q0-foundation` | Roles, sector profile, settings, responsible-person matrix, numbering, criteria library, quality checklists on 6d, shared registers (systems, suppliers master, customers, M&TE master, links, sign-offs), NCR with containment / RCA / disposition / CAPA / cost, observations and quality alerts, customer complaints, permission matrix 238–280, navigation, PDPL |
| **B** | **Q1** construction | `claude/quality-q1-itp` | ITP builder and revisions, inspection requests with hold / witness / review / surveillance points, punch lists with plan pins, handover dossier |
| **C** | **Q2** materials and measurement | `claude/quality-q2-materials` | Material approval (MAR), material inspection on delivery (MIR), quarantine, test types and lab results with automatic pass / fail, concrete pours, welding (WPS / PQR / WPQ, weld log, NDT %), calibration and out-of-tolerance review, competence |
| **D** | **Q3** logistics | `claude/quality-q3-logistics` | Product master and CSV imports, receiving inspection, storage zones and readings, excursions and product impact, temperature mapping, hygiene and pest control, FEFO / expiry / holds / damage / returns / recalls / cycle counts, transport (pre-loading, in transit, proof of delivery) |
| **E** | **Q4** analytics | `claude/quality-q4-analytics` | Document control (light), quality audits and management review, supplier evaluation and scorecards, KPI catalogue K-141…K-169, SPC, COPQ, DPMO and sigma, Pareto, dashboard, report packs, exports, AI tools, seed consolidation |

**Not in Phase 8** (handover §4 "out of scope"): a full EDMS (no drawing register, no markup, no workflow beyond §E.1); a BIM or drawing viewer (plan pins are on a plain image, §B.6); ERP, WMS or TMS functions (stock, orders and shipments arrive by CSV import only; the platform never adjusts stock); live IoT streams (logger files are imported); payment; multi-tenancy. No client standard (Aramco, NEOM, ROSHN, SFDA inspection checklists and the like) is built in; criteria, checklists, numbering and sign-off owners are data (handover §2.2).

Conventions: `[VERIFY]` = regulation, clause or number to confirm against the current official text before a customer relies on it. `ASSUMPTION` = Consultant default; Turki may change it (§7). "Must" = enforced server-side. Rule IDs `Q-<AREA>-<nn>`; acceptance criteria `AC-Q<n>-<nn>` cite rule IDs. Error codes are stable strings (Phase 0 rule 48). Times are Asia/Riyadh unless marked UTC; dates are local dates (Phase 0 K2). Money is SAR with 2 decimals. Temperatures are °C (CSV files in °F are converted on import, §D.1).

**The principle that shapes this module:** quality is shown by records, not by claims. Every acceptance is made by a named responsible person against stated criteria; the person who did or requested the work never accepts it; a failed result is never edited into a pass; every nonconformity is recorded, contained, decided and verified before it closes; product that may be affected is held until a named person releases it; and a measurement is only as good as the instrument's calibration on the day it was used.

---

## 1. Purpose

The HSE platform already knows the project, its sites and zones, the contractor tree, the workforce and their certificates and training, equipment, vehicles, checklists, corrective actions and report packs. A Quality Manager on a KSA megaproject or in a 3PL cold store keeps the same kind of evidence for a different purpose: to prove that the work or the product meets its requirements. Today that evidence lives in spreadsheets, paper IR forms and logger software, and nobody can answer quickly: which hold points were released without the consultant; which NCRs are older than 90 days and what they cost; which concrete pours have failed cubes; which welders have lapsed continuity; which thermometer was out of tolerance and which receipts it measured; which batches were in the chilled room during last night's excursion and who released them.

Phase 8 provides one Quality module with two sector profiles (Construction, Logistics), sharing NCR, CAPA, calibration, competence, documents, audits, suppliers and KPIs, and reusing the platform's corrective actions, checklists, attachments, renderer, notifications, audit log, KPI engine, AI layer and licence.

## 2. Regulatory and good-practice basis

| # | Source | What it drives here |
|---|---|---|
| R1 | **ISO 9001:2015** cl. 4.4 (processes), 5.3 (roles), 6.1 / 6.2 (risk, objectives), 7.1.5 (monitoring and measuring resources, traceability), 7.2 (competence), 7.5 (documented information), 8.4 (externally provided processes), 8.5.1 (controlled conditions), 8.5.2 (identification, traceability), 8.5.4 (preservation), 8.6 (release, "authorized person"), 8.7 (nonconforming outputs), 9.1.2 (customer satisfaction), 9.1.3 (analysis), 9.2 (internal audit), 9.3 (management review), 10.2 (nonconformity and corrective action) | Every part; the "responsible person" is the 8.6 authorized person |
| R2 | **ISO 19011:2018** | Audit programme, auditor competence and independence, finding grades (§E.2) |
| R3 | **ISO/IEC 17025:2017** ideas: 7.1.3 decision rules, 7.6 uncertainty (optional), 7.8 report content, 7.8.8 amendments | Test results, lab accreditation, amended reports with history (§C.2) |
| R4 | ISO 10002:2018 (complaints), ISO 10005:2018 (quality plans), ISO 10012:2003 (measurement management) | Complaints (§A.10), PQP as a document type (§E.1), M&TE (§C.4) |
| R5 | **Saudi Building Code** (SBC 201, 301, 304, 306, 501, 701, 801) as references printed on forms; SBC 304 is based on ACI 318 `[VERIFY]` edition and acceptance clauses | ITP references, concrete acceptance rule sets (§C.2) |
| R6 | International test and acceptance standards, stored as **data** (criteria and test types): ACI 318 `[VERIFY]` §26.12; ASTM C31, C39, C42, C94, C143, C1064; BS EN 206, 12350-2, 12390-3; ASTM D1556, D1557, D6938, D2726, D6927; AWS D1.1, ASME IX, ASME B31.3, ISO 9606-1, ISO 15614-1, ISO 9712; SSPC-PA 2, ISO 19840; ASTM D4541 | Seeded test types and criteria (§C.2, Appendix A) |
| R7 | ISO 2859-1 (sampling by attributes) | Receiving sample size hints (§D.2) |
| R8 | Cold chain good practice: **WHO TRS 961 Annex 9** and its technical supplements (temperature mapping, qualification of temperature-controlled transport) `[VERIFY]` current numbering; WHO GDP (TRS 957 Annex 5 / TRS 1025 Annex 7) `[VERIFY]`; **SFDA** Good Storage and Distribution Practice for medicinal products and SFDA requirements for food warehouses and refrigerated transport `[VERIFY]`; Saudi Food Law `[VERIFY]`; Codex CXC 1-1969 (general principles of food hygiene) and CXC 8-1976 (quick-frozen foods, −18 °C) `[VERIFY]`; USP <1079.2> (MKT) `[VERIFY]` | Storage classes, excursions, mapping, transport, recalls (Part D) |
| R9 | Lean Six Sigma and SPC conventions: ISO 7870-2 (Shewhart charts), ISO 22514 (capability), Western Electric rules, DPMO with the 1.5 σ shift, Juran / ASQ cost of poor quality | KPIs, SPC, COPQ (§E.4–§E.6) |
| R10 | **PDPL** and SDAIA rules (Phase 0 R1, P1–P13) | P8 rules (§A.14) |
| R11 | SASO / SABER conformity certificates for regulated imported products `[VERIFY]`; NRRC licence for nuclear density gauges `[VERIFY]` | MAR evidence fields; M&TE note |

Design choices that follow (strictest-wins where sources differ):
- **The requester never accepts** (Q-RPM-06). A contractor QC engineer who raises an IR cannot also approve it, even if they hold the capability.
- **A hold point is a hard stop** (Q-IR-08); a witness point may be waived only after notice and only by recording it (Q-IR-10).
- **Results are evidence:** a verified test result, an imported logger file and a reading are never edited; corrections are amendments with a reason and keep the original (Q-TST-09, Q-STO-07).
- **Classification can go up freely, down only with the responsible person's reasoned approval** (Q-NCR-05).
- **Doubtful product is held** until a named responsible person releases it, and a hold linked to an NCR cannot be released before the NCR disposition is approved (Q-HLD-04).
- **A logistics release after an excursion needs the goods owner's decision** where the goods belong to a customer (3PL), not only the warehouse's (Q-EXC-09).

## 3. Package boundaries and plug-in contract (read before building any part)

The handover asks that Q1, Q2 and Q3 build in parallel from the Q0 branch head without editing the same files, apart from the known shared files of handover §3. This section makes that possible. **Q0 pre-registers every shared value; later parts plug in through registries and their own files.**

### 3.1 What Q0 pre-registers for every part (in files that exist before wave 2)

| Shared thing | Where it lives | What Q0 adds once, for all parts |
|---|---|---|
| Capabilities and the matrix | `app/core/enums.py` (`Capability`), `app/services/permissions.py` (`PHASE8_MATRIX`) | All of 238–280 (§A.11) and the 5 roles (§A.1) |
| Roles | `app/core/enums.py` (`Role`) | `qa_qc_manager`, `quality_engineer`, `qc_inspector`, `warehouse_qc`, `responsible_person` |
| CA source types | `app/core/hse_enums.py` (`CaSourceType`) | `quality_ncr`, `quality_observation`, `quality_complaint`, `quality_audit`, `quality_review` |
| Attachment owners | `app/core/hse_enums.py` (`AttachmentOwner`) | every value of list QAO (§A.8.7), one dispatch branch in `app/services/attachments.py` |
| Audit entity types and notification kinds | `app/core/enums.py` (`EntityType`, `NotificationKind`) | every Phase 8 record type of list QRT (§A.4.2) and one notification kind `quality` |
| 6d checklist kind and owners | `app/core/field_enums.py` (`TemplateKind`, `ResponseOwnerType`) | kind `quality`; owner types of §A.7 |
| Project type | `app/core/enums.py` (`ProjectType`) | `logistics` (D-309) |
| Record types, NCR sources, settings keys, numbering, RP matrix rows | `app/core/quality/common.py` (new) | lists QRT, NS (§A.9.2) and every settings key of every part (§A.3) with defaults |

A later part that finds a missing value in these shared enums asks the orchestrator; it does not add it in its own branch (the integrator adds it once).

### 3.2 Registries (Q0 defines them; parts register into them from their own files)

All registries live in `app/services/quality/registry.py` (backend) and `src/components/quality/registry/` (frontend). A part registers in the `register()` function of its own package `app/services/quality/q<n>/__init__.py`; Q0 imports `q1`…`q4` once (Q0 creates each as an empty stub).

| Registry | Key | A part provides | Used by |
|---|---|---|---|
| `NCR_SOURCES` | `NcrSourceType` | `resolve(db, project, source_id) → SourceInfo(ref, title, site_id, zone_id, system_id, engagement_id, supplier_id, item_key, detection_stage)`, optional `on_ncr_status(db, ncr, new_status)` and `close_check(db, ncr) → list[blocker]` | NCR create, close (Q-NCR-02, Q-NCR-15) |
| `RECORD_TYPES` | `QRecordType` | `get(db, id)`, `scope(p, row)`, `ref(row)`, `link_path(row)` | sign-offs, links, M&TE usage, "Awaiting me" |
| `PENDING_STEPS` | part code | `pending(db, p, project_id) → list[PendingStep]` | "Awaiting my sign-off" inbox (§A.12) |
| `ATTACHMENT_OWNERS` | `AttachmentOwner` | `owner(db, p, owner_id, write) → (project_id, editable)` | `attachments._owner` quality branch |
| `CRITERIA_EVALUATORS` | rule code | `evaluate(params, values) → Verdict` | criteria library (§A.6) |
| `HOLD_CHECKS` | `"itp_point"` | `released(db, itp_point_id, location_key) → True / False / None` | Q2 pours (Q-TST-12); provided by Q1 |
| `COMPETENCE` | — | `check(db, user_id, requirement_code, at) → CompetenceVerdict` | Q1 IR inspectors, Q3 mapping lead, Q4 auditors; provided by Q2; default "not configured" |
| `DOSSIER_SECTIONS` | section code | `items(db, dossier) → list[DossierItem]`, `blockers(db, dossier)` | Q1 dossier engine (§B.7) |
| `JOBS` | job code | `run(db, at)` with schedule | `app/services/quality/jobs.py`, wired once into `app/scheduler.py` |
| `DATASETS` | dataset code | 6g `Dataset` rows | appended once to `app/services/scorecard/datasets.py` `NATIVE` |
| `SEEDS` | part code | `seed(db)` | `app/seed_quality.py` |
| `SUPPLIER_GATES` | — | `approval_blockers(db, supplier)` | Q0 supplier transitions; provided by Q4 |
| Frontend nav | part file `src/components/quality/nav/q<n>.ts` | `QualityNavItem[]` (href, label key, icon, capability, profiles) | "Quality" sidebar group |
| Frontend messages | `messages/quality/q<n>.{en,ar}.json` | keys under `quality.<area>` only | merged by `src/i18n/request.ts`; checked by `scripts/check-i18n.mjs` (Q0 extends both once) |
| Frontend detail tabs | `src/components/quality/registry/tabs-q<n>.tsx` | extra tabs on NCR, supplier and M&TE pages | NCR, supplier and M&TE detail pages |

### 3.3 File and table ownership

Every part owns the files below and edits no other part's files. "Stub" = Q0 creates an empty file that the owning part fills.

| Part | Tables (all new; prefix `q_`) | Backend files | Frontend route folders under `src/app/[locale]/(app)/quality/` | Tests and e2e |
|---|---|---|---|---|
| **Q0** | `q_settings`, `q_positions`, `q_position_holders`, `q_rp_rules`, `q_numbering`, `q_criteria`, `q_systems`, `q_suppliers`, `q_supplier_accreditations`, `q_customers`, `q_mte_items`, `q_mte_usage`, `q_links`, `q_signoffs`, `q_ncrs`, `q_ncr_lines`, `q_ncr_costs`, `q_ncr_rca`, `q_observations`, `q_alerts`, `q_alert_acks`, `q_complaints`; columns added to `checklist_templates` (`quality_type`, `sector_profiles`) | `app/core/quality/common.py`; `app/models/quality/__init__.py`, `q0.py`; `app/schemas/quality/q0/`; `app/services/quality/{registry,settings,rpm,numbering,criteria,signoff,links,suppliers,customers,systems,mte,files,jobs}.py`, `app/services/quality/ncr/`, `alerts.py`, `complaints.py`; `app/api/routers/quality/__init__.py`, `q0/`; `app/seed_quality.py`; migration `q0_…` on `c0025`; one-line hooks in `main.py`, `scheduler.py`, `models/__init__.py`, `attachments.py`, `corrective_actions.py`, `permissions.py`, `kpi/data.py`, `dashboard.py`, `scorecard/datasets.py` | `ncrs/`, `observations/`, `alerts/`, `complaints/`, `settings/`, `criteria/`, `suppliers/`, `customers/`, `systems/`, `awaiting/`, `page.tsx` (Quality home) | `tests/quality/q0/`; `e2e/quality/q0-*.spec.ts` |
| **Q1** | `q_itps`, `q_itp_points`, `q_irs`, `q_ir_rounds`, `q_ir_comments`, `q_floor_plans`, `q_punch_items`, `q_dossiers`, `q_asbuilt_items` | `app/core/quality/q1.py`, `app/models/quality/q1.py`, `app/schemas/quality/q1/`, `app/services/quality/q1/`, `app/api/routers/quality/q1/`, `app/seed_quality_q1.py`, migration `q1_…` | `itps/`, `inspection-requests/`, `punch/`, `floor-plans/`, `dossiers/` | `tests/quality/q1/`; `e2e/quality/q1-*.spec.ts` |
| **Q2** | `q_mars`, `q_mirs`, `q_quarantine_items`, `q_test_types`, `q_test_requests`, `q_test_specimens`, `q_pours`, `q_wps`, `q_pqrs`, `q_welders`, `q_wpqs`, `q_welds`, `q_calibrations`, `q_oot_reviews`, `q_oot_items`, `q_competence_reqs` | same pattern with `q2` | `materials/`, `material-inspections/`, `quarantine/`, `tests/`, `test-types/`, `pours/`, `welding/`, `mte/`, `calibration/`, `competence/` | `tests/quality/q2/`; `e2e/quality/q2-*.spec.ts` |
| **Q3** | `q_products`, `q_import_batches`, `q_storage_zones`, `q_monitoring_points`, `q_readings`, `q_excursions`, `q_excursion_impacts`, `q_mapping_studies`, `q_check_schedules`, `q_pest_stations`, `q_pest_visits`, `q_receipts`, `q_receipt_lines`, `q_stock_snapshots`, `q_stock_lines`, `q_fefo_checks`, `q_holds`, `q_hold_lines`, `q_damage_reports`, `q_returns`, `q_return_lines`, `q_recalls`, `q_recall_items`, `q_cycle_counts`, `q_cycle_count_lines`, `q_shipments`, `q_shipment_lines`, `q_trips`, `q_pods`, `q_throughput` | same pattern with `q3` | `receiving/`, `storage/`, `readings/`, `excursions/`, `mapping/`, `hygiene/`, `pest/`, `stock/`, `holds/`, `returns/`, `recalls/`, `transport/`, `imports/`, `products/` | `tests/quality/q3/`; `e2e/quality/q3-*.spec.ts` |
| **Q4** | `q_documents`, `q_document_revisions`, `q_doc_distribution`, `q_doc_acks`, `q_transmittals`, `q_transmittal_items`, `q_processes`, `q_audit_programme_lines`, `q_management_reviews`, `q_supplier_evaluations`, `q_supplier_scores`, `q_kpi_targets`, `q_spc_charts`, `q_work_value`; columns added to `field_audits` (`domain`, `auditee_supplier_id`, `process_ids`) | same pattern with `q4`; plus `app/kpi/quality.py`, `app/kpi/quality_views.py`, AI tools in `app/ai/tools.py`, 6d audit and KPI edits (§E.2), 6g pack types | `documents/`, `transmittals/`, `audits/`, `audit-programme/`, `management-reviews/`, `supplier-scores/`, `kpis/`, `spc/`, `reports/` | `tests/quality/q4/`; `e2e/quality/q4-*.spec.ts` |

Shared files that wave-2 parts may still touch (all known to the integrator, handover §3): their own Alembic file (re-chained by the integrator), `docs/contracts/openapi.yaml` and `frontend/src/lib/api/schema.d.ts` (regenerated by the integrator; packages regenerate locally but never bump `CONTRACT_VERSION`), `docs/DECISIONS.md` (own range only, appended) and `docs/PROGRESS.md` (own section only). Nothing else. Q4 runs alone in wave 3 and may edit Q0 files and the 6d / 6g / KPI / AI files listed in its row.

### 3.4 Cross-part links without foreign keys

Records of different wave-2 parts refer to each other only through `q_links` (§A.8.5) or a `(record_type, record_id)` pair, never through a foreign key to another part's table. Examples: a Q2 pour links the Q1 IR of the pre-pour hold point; a Q2 test request links the Q1 IR it serves; a Q3 hold links the Q0 NCR. Cross-part behaviour (a failed test blocks an IR, a hold point gates a pour) goes through the registries of §3.2 and is completed by the integrator's cross-package tests (handover §7.5).

### 3.5 Per-part working values (handover §5)

| Part | Decisions | DB prefix (tests) | Ports | Alembic slug |
|---|---|---|---|---|
| Q0 | D-320…D-329 | `q0_` | 8200 / 3200 | `q0_quality_foundation` on `c0025` |
| Q1 | D-330…D-339 | `q1_` | 8201 / 3201 | `q1_quality_itp` on Q0 head |
| Q2 | D-340…D-349 | `q2_` | 8202 / 3202 | `q2_quality_materials` on Q0 head |
| Q3 | D-350…D-359 | `q3_` | 8203 / 3203 | `q3_quality_logistics` on Q0 head |
| Q4 | D-360…D-369 | `q4_` | 8204 / 3204 | `q4_quality_analytics` on q3 head |

---

# Part A — Q0: foundation and NCR core

## A.1 Roles and scoping (Q-ROL)

| Code | EN | AR | Typical holder |
|---|---|---|---|
| `qa_qc_manager` | QA/QC Manager | مدير ضبط وتوكيد الجودة | PMC or client QA/QC manager; contractor QA/QC manager (with an engagement); 3PL quality manager |
| `quality_engineer` | Quality Engineer | مهندس الجودة | Contractor or PMC quality engineer; materials / welding engineer; 3PL quality engineer |
| `qc_inspector` | QC Inspector | مفتش ضبط الجودة | Discipline QC inspector, welding inspector, receiving inspector |
| `warehouse_qc` | Warehouse QC / Storekeeper | مراقب جودة المستودع / أمين المخزن | Receiving checker, storekeeper, transport supervisor |
| `responsible_person` | Responsible Person | الشخص المسؤول | Consultant inspector, client representative, warehouse manager, responsible pharmacist: people who only sign what they are named for |

- **Q-ROL-01.** The five roles are project roles (Phase 0 §3.7). The HSE Manager and the project's `qa_qc_manager` (assigned without an engagement) may assign them (capability 239 extends Phase 0 capability 10 for these roles only); an HSE Officer may not.
- **Q-ROL-02.** A quality role may be assigned with a `contractor_engagement_id`. Then every Quality grant of that assignment is narrowed to that engagement and its descendants (scope C), whatever the matrix says. Without an engagement, the matrix scope applies. `site_ids` restrict as Phase 0 rule 11.
- **Q-ROL-03.** A contractor-assigned quality role never edits Quality settings (239) or voids records (244), and never resolves as responsible person for a record of its own engagement tree unless the matrix row allows it (`own_tree_allowed`, default false; Q-RPM-07).
- **Q-ROL-04.** `responsible_person` holds the approval capabilities with scope **N**: it acts only on records where it resolves as the responsible person for a pending step (Q-RPM-03), and reads only those records, their links and the project registers they need to see them (no KPIs, no exports). It is not in `MFA_REQUIRED_ROLES` by default.
- **Q-ROL-05.** Phase 0 rules 12 (404 out of scope), 15 (no self role change) and 28 (suspended contractor: reads only) apply to every Quality endpoint.

## A.2 Sector profile (Q-PRF)

- **Q-PRF-01.** Each project has one `sector_profile`: `construction` (إنشاءات) or `logistics` (لوجستيات), set by 239 when Quality is first configured; until then the Quality home shows "Choose the sector profile" to 239 holders and nothing to others.
- **Q-PRF-02.** The profile decides which navigation items, record types, checklists, criteria, KPIs and seed defaults the project shows (list QRT column "Profile", §A.4.2). Shared record types serve both.
- **Q-PRF-03.** The profile may be changed by 239 with a reason ≥ 20 chars; the change is audited (`settings_changed`, old / new). Records made under the other profile stay, keep their numbers and stay readable and exportable.
- **Q-PRF-04.** After a change, creating a record of a type that belongs only to the inactive profile gives 409 `PROFILE_INACTIVE`. Open records of that type may still be progressed to a final state (e.g. an open IR may be decided, an open hold released) so nothing is stranded; the screen shows "Other profile — finish only".
- **Q-PRF-05.** KPIs of a profile-specific type are computed for any period that has records (a project that changed profile still reports its old IRs); the dashboard shows tiles of the current profile and the shared ones (§E.7).
- **Q-PRF-06.** A new project type `logistics` (لوجستيات / مستودعات) is added to Phase 0 §3.1 (D-309). A `logistics` project defaults to the logistics profile; every other type defaults to construction. The profile, not the project type, drives Quality.

## A.3 Quality settings (Q-SET)

One row per project in `q_settings`: `sector_profile`, `quality_start_date` (records before it are allowed but flagged "before Quality start" and excluded from KPIs), `values` (JSON, merged over the registry defaults on read, as `project_field_settings`). Only 239 holders edit; every change is audited; values outside "Allowed" give 422 `SETTING_OUT_OF_RANGE`.

- **Q-SET-01.** The settings registry (`app/core/quality/common.py` `SETTINGS`) declares every key of every part: key, part, type, default, allowed range, profile. `GET /projects/{id}/quality/settings/schema` returns it, and the settings screen renders the form from it, so later parts add no settings UI.
- **Q-SET-02.** Changing a setting never rewrites stored records; it applies to records created or evaluated after the change (KPIs re-computed at read time use the setting valid on the record's date only where a rule says so).

| Key | Part | AR label | Type | Default | Allowed |
|---|---|---|---|---|---|
| `ncr_containment_hours` | Q0 | مهلة الاحتواء | {critical, major, minor} h | 24 / 72 / 168 ASSUMPTION | 4–720 |
| `ncr_target_close_days` | Q0 | مدة الإغلاق المستهدفة | {critical, major, minor} days | 21 / 30 / 30 ASSUMPTION | 3–180 |
| `ncr_repeat_days` | Q0 | مدة التكرار | int | 90 | 30–365 |
| `ncr_effectiveness_days` | Q0 | موعد فحص الفعالية | int | 90 | 30–365 |
| `rca_method_by_class` | Q0 | طريقة تحليل السبب | {critical, major, minor} → methods | critical: `eight_d`; major: `five_why` / `ishikawa` / `eight_d`; minor: any incl. `simple` | subsets of list RCA |
| `quality_ca_due_days` | Q0 | مدة الإجراءات التصحيحية للجودة | {critical, high, medium, low} days | 14 / 30 / 45 / 60 ASSUMPTION | 1–180 |
| `labour_rate_sar_h` | Q0 | سعر ساعة العمل | decimal | 85.00 ASSUMPTION | 10–1,000 |
| `plant_rate_sar_h` | Q0 | سعر ساعة المعدات | decimal | 250.00 ASSUMPTION | 10–5,000 |
| `delay_rate_sar_day` | Q0 | تكلفة يوم التأخير | decimal / null | null (a delay cost line needs it) | 0–10,000,000 |
| `mte_use_policy` | Q0 | سياسة استخدام أجهزة غير معايرة | enum | `warn` | `warn` · `block` |
| `competence_policy` | Q0 | سياسة الكفاءة | enum | `warn` | `warn` · `block` |
| `complaint_ack_hours` / `complaint_response_days` | Q0 | مهلة الإقرار / الرد | int / int | 24 / 10 | 1–168 / 1–60 |
| `paper_signoff_default` | Q0 | السماح بالتوقيع الورقي | bool | true | — |
| IR, punch and dossier keys | Q1 | — | — | §B.2 | — |
| Materials, testing, welding, calibration, competence keys | Q2 | — | — | §C.1 | — |
| Logistics keys | Q3 | — | — | §D.1 | — |
| Documents, audits, suppliers, SPC, KPI targets | Q4 | — | — | §E.1 | — |

## A.4 Responsible-person matrix (Q-RPM)

### A.4.1 Positions — مناصب المشروع
A **position** is a project title that is not a platform role, e.g. "Consultant Resident Engineer (Civil)", "Client Representative", "Warehouse Manager", "Responsible Pharmacist". `q_positions`: code (`^[A-Z0-9_]{2,20}$`, unique per project), name EN / AR, profile (both / construction / logistics), active. `q_position_holders`: position, user, valid_from, valid_to (holders may overlap: a deputy is a second holder). Positions are edited by 239.

### A.4.2 Record types and steps (list QRT; the matrix has one row per type and step)

| Record type | EN / AR | Part | Profile | Prefix | Steps that need a responsible person (default assignee) |
|---|---|---|---|---|---|
| `ncr` | Nonconformance Report / تقرير عدم مطابقة | Q0 | both | NCR | `disposition` (role qa_qc_manager), `concession` for use-as-is / repair (position CONSULTANT_RE construction; WAREHOUSE_MGR logistics), `close` (role qa_qc_manager) |
| `observation` | Quality Observation / ملاحظة جودة | Q0 | both | QOB | `close` (role quality_engineer) |
| `quality_alert` | Quality Alert / تنبيه جودة | Q0 | both | QAL | `issue` (role qa_qc_manager) |
| `complaint` | Customer Complaint / شكوى عميل | Q0 | both | CCM | `response` (role qa_qc_manager), `close` (role qa_qc_manager) |
| `itp` | Inspection and Test Plan / خطة الفحص والاختبار | Q1 | construction | ITP | `approve` (position CONSULTANT_RE) |
| `ir` | Inspection Request / طلب فحص | Q1 | construction | IR | `inspect` per point type: H and W → position CONSULTANT_RE; R → role quality_engineer; S → role qc_inspector (ITP point override allowed) |
| `punch_item` | Punch Item / بند قائمة النواقص | Q1 | construction | PCH | `verify` (position CONSULTANT_RE) |
| `dossier` | Handover Dossier / ملف التسليم | Q1 | construction | DOS | `accept` (position CLIENT_REP) |
| `mar` | Material Approval Request / طلب اعتماد مواد | Q2 | construction | MAR | `approve` (position CONSULTANT_RE) |
| `mir` | Material Inspection Request / طلب فحص المواد الموردة | Q2 | construction | MIR | `decide` (position CONSULTANT_RE) |
| `quarantine` | Quarantined Material / مواد محجوزة | Q2 | construction | QTN | `dispose` (role qa_qc_manager) |
| `test_request` | Test Request / طلب اختبار | Q2 | both | TST | `verify` (role quality_engineer) |
| `pour` | Concrete Pour / صبّة خرسانية | Q2 | construction | POUR | — |
| `wps` / `pqr` | Welding Procedure Spec. / Procedure Qualification Record / مواصفة إجراء اللحام / سجل تأهيل الإجراء | Q2 | construction | WPS / PQR | `approve` (position CONSULTANT_RE) |
| `wpq` | Welder Qualification / تأهيل اللحّام | Q2 | construction | WPQ | `approve` (role quality_engineer) |
| `weld` | Weld Joint / وصلة لحام | Q2 | construction | (joint id) | — |
| `mte` | Measuring and Test Equipment / جهاز قياس واختبار | Q0 table, Q2 rules | both | MTE | — |
| `calibration` | Calibration Record / سجل معايرة | Q2 | both | CAL | `accept` (role quality_engineer) |
| `oot_review` | Out-of-Tolerance Review / مراجعة الخروج عن التفاوت | Q2 | both | OOT | `decide` (role qa_qc_manager) |
| `receipt` | Receiving Inspection / فحص الاستلام | Q3 | logistics | RCV | `deviation` and `reject` (role qa_qc_manager) |
| `excursion` | Temperature Excursion / انحراف حراري | Q3 | logistics | EXC | `impact` (position WAREHOUSE_MGR; position RESP_PHARMACIST for storage class `pharma_2_8`) |
| `mapping_study` | Temperature Mapping Study / دراسة التوزيع الحراري | Q3 | logistics | MAP | `approve` (role qa_qc_manager) |
| `hold` | Hold / Quarantine / حجز وعزل | Q3 | logistics | HLD | `release`, `reject` (position WAREHOUSE_MGR; RESP_PHARMACIST for pharma) |
| `return` | Return Inspection / فحص المرتجعات | Q3 | logistics | RET | `disposition` (role qa_qc_manager) |
| `recall` | Recall / استدعاء منتج | Q3 | logistics | RCL | `close` (role qa_qc_manager) |
| `damage_report` / `fefo_check` / `cycle_count` | Damage report / FEFO check / Cycle count / بلاغ تلف / فحص الأقدم انتهاءً / جرد دوري | Q3 | logistics | DMG / FEF / CC | — |
| `trip` | Transport Trip / رحلة نقل | Q3 | logistics | TRP | `dispatch_override` (position WAREHOUSE_MGR) |
| `document` | Controlled Document / وثيقة مضبوطة | Q4 | both | per type | `review` (role quality_engineer), `approve` (role qa_qc_manager) |
| `transmittal` | Transmittal / مذكرة إحالة | Q4 | both | TRM | — |
| `q_audit` | Quality Audit / تدقيق الجودة | Q4 | both | QAU | `issue` (role qa_qc_manager, ≠ lead auditor) |
| `management_review` | Management Review / مراجعة الإدارة | Q4 | both | MRV | `approve` (role qa_qc_manager) |
| `supplier` | Supplier / مورد | Q0 table, Q4 rules | both | SUP | `approve`, `suspend` (role qa_qc_manager) |
| `supplier_evaluation` | Supplier Evaluation / تقييم المورد | Q4 | both | SEV | `approve` (role qa_qc_manager) |

Seeded positions per profile: construction CONSULTANT_RE (Consultant Resident Engineer / المهندس المقيم للاستشاري), CONSULTANT_INSP (Consultant Inspector / مفتش الاستشاري), CLIENT_REP (Client Representative / ممثل العميل); logistics WAREHOUSE_MGR (Warehouse Manager / مدير المستودع), RESP_PHARMACIST (Responsible Pharmacist / الصيدلي المسؤول `[VERIFY]` SFDA requirement for medicinal-product stores), TRANSPORT_SUP (Transport Supervisor / مشرف النقل).

### A.4.3 Matrix rows and rules

`q_rp_rules`: project, record_type, step, optional qualifier (discipline, ITP point type, storage class, NCR class), assignee_kind (`user` · `role` · `position`), assignee (user id, role code or position code), `self_approval_allowed` (default false), `own_tree_allowed` (default false), `paper_allowed` (default `paper_signoff_default`), active. Q0 seeds the defaults of §A.4.2 for each project on first Quality use.

- **Q-RPM-01.** Every step in list QRT names its responsible person through this matrix. No code path has a fixed "consultant signs" or "client signs" rule; tests change the matrix and expect the change to take effect (AC-Q0-12).
- **Q-RPM-02.** Lookup order: the record's own override (e.g. an ITP point's `rp_override`), then the most specific matrix row (qualifier match), then the general row for the type and step. No active row → 422 `RESPONSIBLE_PERSON_NOT_SET` when the step is attempted, and the record shows "No responsible person set" to 239 holders.
- **Q-RPM-03.** A user **resolves** as responsible person for a step when: (a) `user` → that user; `role` → the user holds that platform role on the project with a scope covering the record; `position` → the user is an active holder of that position on the record's date; and (b) the user holds the step's capability (§A.11) on the project.
- **Q-RPM-04.** The resolved set may contain several users (e.g. two position holders); any one of them may act; the sign-off records who did.
- **Q-RPM-05.** A responsible-person action writes one `q_signoffs` row: record type, record id, step, decision (from the step's list, e.g. approved / approved_with_comments / rejected / returned), comment, signed_by_user_id, signed_at, signer's role or position at that time, `channel` (`in_app` · `paper`), evidence attachment ids, and the matrix row used. Rows are append-only.
- **Q-RPM-06.** **Segregation:** the user who created, requested or last submitted the record, or recorded the result being decided, cannot sign its step (`SOD_CONFLICT`) unless the matrix row has `self_approval_allowed`. The HSE Manager is not exempt.
- **Q-RPM-07.** A contractor-assigned user (Q-ROL-02) cannot sign a step on a record whose responsible engagement is in their own tree unless the row has `own_tree_allowed` (contractor self-certification is a project decision, not a default).
- **Q-RPM-08.** **External sign-off.** A person without an account is invited as a user with role `responsible_person` (Phase 0 invite flow, 72 h token, privacy notice) and added as position holder. Where the row has `paper_allowed`, a holder of the step's capability may instead record the decision **on behalf of** a named external signatory: name, organisation, position, signed date and ≥ 1 scanned signed form (PDF / image). The sign-off is stored with channel `paper` and shown "Signed on paper by <name> (<organisation>), recorded by <user>". Paper sign-offs are counted (K-141 chip, §E.4).
- **Q-RPM-09.** The HSE Manager and 239 holders may **re-assign** the responsible person of one pending step on one record (reason ≥ 20 chars, audited); they never sign in the resolved person's place unless they resolve themselves.
- **Q-RPM-10.** A matrix change applies to steps not yet signed; signed steps keep their sign-off. Open records whose resolved set becomes empty are listed on the Quality home ("steps without a responsible person").
- **Q-RPM-11.** "Awaiting my sign-off" lists every pending step where the current user resolves, across all parts (registry `PENDING_STEPS`), oldest first, with the record ref, step, waiting time and a link.

## A.5 Numbering (Q-NUM)

- **Q-NUM-01.** Each record type of list QRT has a format in `q_numbering` (editable by 239): tokens `{PFX}` (type prefix), `{PROJECT}` (project code), `{SITE}` (site code), `{DISC}` (discipline code where the type has one), `{YYYY}`, `{YY}`, `{SEQ3}`…`{SEQ6}` (zero-padded sequence), literal `-` `/` `_` and letters. Default `{PFX}-{PROJECT}-{YYYY}-{SEQ4}` (e.g. `NCR-ANIA-EXP-2026-0041`); ITP `{PFX}-{PROJECT}-{DISC}-{SEQ3}`; reset `yearly` (default) or `never`.
- **Q-NUM-02.** A format must contain one `{SEQn}` and, when reset is yearly, `{YYYY}` or `{YY}` (`NUMBER_FORMAT_INVALID`). The rendered number is ≤ 40 characters.
- **Q-NUM-03.** Numbers are assigned when a record leaves Draft (drafts show "Draft"), from a per-project, per-type, per-year sequence locked with the project row (`hse_common.next_seq` pattern), so two submissions never get the same number (AC-Q0-17). Numbers are never reused, including after void.
- **Q-NUM-04.** A format change applies to numbers assigned after it; existing numbers never change. Revisable records (ITP, MAR, WPS, documents) append the revision in display (`… Rev.2`), not in the number.

## A.6 Acceptance criteria library (Q-CRT)

`q_criteria` (org-wide, versioned like 6d templates): code (`^[A-Z0-9-]{3,20}$`), version, title EN / AR, profile (both / construction / logistics), kind (list CK), unit, min, max, target, tol_minus, tol_plus, rule code and params (for kind `rule`), reference (standard clause, spec section, contract clause — text, ≤ 120), note EN / AR, status `draft` · `published` · `superseded` · `retired` (6d §4.1 transitions; author 240, publish 239). Project-specific criteria have `project_ids`.

**CK — criterion kinds:** `range` (min ≤ v ≤ max) · `min` (v ≥ min) · `max` (v ≤ max) · `target_tolerance` (target − tol_minus ≤ v ≤ target + tol_plus) · `pass_fail` (entered verdict) · `text` (described; verdict entered by the inspector) · `rule` (a coded evaluator from registry `CRITERIA_EVALUATORS`, e.g. `aci318_strength`, `en206_strength`, `sspc_pa2`, `pressure_hold`, `slump_astm_c94`, `remaining_shelf_life`, `arrival_temperature`).

- **Q-CRT-01.** `criteria.evaluate(criterion_version, values)` returns `pass` · `fail` · `indicative` (information only, e.g. 7-day cubes) · `not_evaluable` (missing input), with the reason in EN / AR. Comparisons use unrounded values; boundaries are inclusive.
- **Q-CRT-02.** A record that uses a criterion pins its version; publishing a new version never changes past verdicts.
- **Q-CRT-03.** Criteria are data: no Q-rule hard-codes a numeric acceptance limit except the platform defaults that seed the library (Appendix A.2), all of which can be edited or retired.

## A.7 Quality checklists on the 6d engine (Q-CHK)

- **Q-CHK-01.** Quality checklists are 6d `checklist_templates` with kind `quality` and two new columns: `quality_type` (list QCT) and `sector_profiles` (both / construction / logistics). Items, weights, critical items, numeric rules, versions, publish completeness (TPL-2), immutability (TPL-3) and version pinning (TPL-4) are unchanged. Template codes start with `Q` (e.g. `QCON`, `QRCV`) so they never collide with HSE codes. Author 240, publish 239 (the 6d capabilities 192 / 193 do not apply to kind `quality`).
- **Q-CHK-02.** Answers are scored by `app/services/field/scoring.evaluate` and stored as `checklist_responses` with the owner types below (`store_answers`, as 7b does). Stop rules (`stop_work`) are not allowed on kind `quality` (`STOP_RULE_NOT_ALLOWED`); a critical failure fails the response (6d FND-6 logic) and the owning part decides what that means (e.g. IR rejected).
- **Q-CHK-03.** Quality responses never create 6d findings or Phase 1 CAs by themselves and never enter K-34, K-35, K-36 or K-110…K-117. Non-compliant items count as defects for DPMO (§E.6).
- **Q-CHK-04.** `checklist_default` settings per record type (and discipline / storage class) name the template a new record proposes; the user may pick any Published quality template whose `quality_type` and profile match.

**QCT — quality checklist types:** `ir_inspection` (Q1) · `punch_walkdown` (Q1) · `mir_inspection` (Q2) · `receiving` (Q3) · `reefer_preload` (Q3) · `hygiene` (Q3) · `pest_visit` (Q3) · `return_inspection` (Q3) · `q_audit` (Q4, kind `audit` stays 6d's; quality audits use kind `quality` with this type) · `supplier_audit` (Q4).
**Response owner types added:** `q_ir_round`, `q_punch_walkdown`, `q_mir`, `q_receipt`, `q_trip_preload`, `q_hygiene`, `q_pest_visit`, `q_return`, `q_audit`.

## A.8 Shared registers owned by Q0 (Q-SHR)

### A.8.1 Systems — الأنظمة
`q_systems`: code (`^[A-Z0-9-]{2,20}$`, unique per project), name EN / AR, discipline (list DSC, §B.1), parent system (≤ 3 levels), zone_ids, status active / archived. Used by Q1 (IRs, punch, dossiers) and Q2 (tests, welds).

### A.8.2 Supplier master — سجل الموردين
Org-wide, like contractors (Phase 0 §3.4). `q_suppliers`: supplier_code (`^[A-Z0-9]{2,12}$`, unique), legal_name_en / _ar (unique, normalised as Phase 0 rule 45), cr_number (optional; same validation as contractors), vat_number (optional), country, categories (list SC, ≥ 1), contractor_id (optional link when the supplier is also a contractor), scope_en / _ar (what they supply), contact name / mobile / email (personal), status (list SS), status_reason, approved_scope (text), next_evaluation_due (sys, Q4), `tpi_id` (optional link to a Phase 4 TPI, for calibration and NDT bodies). `q_supplier_accreditations`: body (`sac` · `ilac_mra_other` · `other`), standard (`iso_iec_17025` · `iso_iec_17020` · `iso_9001` · `iso_22000` · `other`), number, scope (text and test-type codes), valid_from, valid_until, certificate file.

**SC — supplier categories:** `material_supplier` مورد مواد · `manufacturer` مصنّع · `subcontractor` مقاول باطن · `testing_lab` مختبر اختبارات · `calibration_lab` مختبر معايرة · `ndt_provider` مزود فحص غير إتلافي · `carrier` ناقل · `pest_control` مكافحة آفات · `cleaning` تنظيف · `packaging` تغليف · `shipper` شاحن / مورد البضاعة · `service` خدمات · `other` أخرى.
**SS — supplier status:** `draft` مسودة → `pending_approval` بانتظار الاعتماد → `approved` معتمد · `conditional` معتمد بشروط · `suspended` موقوف · `disqualified` مستبعد.

- **Q-SHR-01.** Transitions: draft → pending_approval (278); pending_approval → approved / conditional / back to draft (279 + RPM `supplier.approve`; registry `SUPPLIER_GATES` may add blockers, Q4 adds "an approved evaluation is required"); approved ↔ conditional, approved / conditional → suspended (279 + RPM `supplier.suspend`, reason); suspended → approved / conditional (reason); any → disqualified (279, reason; terminal except "lift" → suspended).
- **Q-SHR-02.** Records that name a supplier (MAR, receipt, test request, calibration, trip, NCR) warn `SUPPLIER_NOT_APPROVED` when the supplier is not approved / conditional on the record date, and refuse a `disqualified` supplier (`SUPPLIER_DISQUALIFIED`). A conditional supplier shows its condition text.
- **Q-SHR-03.** A testing or calibration lab used for a test type or M&TE type outside its accreditation scope, or with no accreditation valid on the test or calibration date, gives warning `LAB_NOT_ACCREDITED_FOR_SCOPE` (not a block: unaccredited labs exist, and the decision is recorded) ASSUMPTION.

### A.8.3 Customers — العملاء
`q_customers` (per project): code, name EN / AR, kind (`client` العميل · `depositor` مالك البضاعة · `consignee` المستلم · `end_user` المستخدم النهائي), contact name / mobile / email (personal), approval-required flags (`owner_release_approval` for depositors, Q-EXC-09), status active / inactive.

### A.8.4 M&TE master — سجل أجهزة القياس والاختبار
Q0 owns the table so every part can cite instruments; Q2 owns calibration behaviour (§C.4). `q_mte_items`: mte_no (numbering `MTE`), type (list MT, §C.4), description, manufacturer, model, serial_no (unique with manufacturer per project), range, resolution, tolerance (± value and unit), owner (`own` · engagement · supplier), site / zone, custodian user, `check_kind` (`calibration` · `verification` · `none`), interval_months, `cal_status` (sys, list CS §C.4), `cal_due_on` (sys), `last_calibration_id` (sys), `equipment_item_id` (optional Phase 4 link), status `active` · `retired` · `lost`, label printed at.

`q_mte_usage`: mte_id, project_id, record_type, record_id, used_at, verdict at use (`ok` · `warned` · `blocked_overridden`), recorded_by. **Q-SHR-04.** Any part that records a measurement with an instrument calls `mte.record_usage(...)`. With `cal_status` `overdue` or `out_of_service`, or a status `retired` / `lost`, the call warns `MTE_NOT_CALIBRATED` (policy `warn`) or refuses (policy `block`, 422 `MTE_NOT_CALIBRATED`). `unknown` (Q2 not yet installed) always warns.

### A.8.5 Links — الروابط
`q_links`: from_type, from_id, to_type, to_id, kind (`raised_from` · `relates` · `evidence` · `requires` · `supersedes`), created_by, created_at. **Q-SHR-05.** A link is created only when both ends resolve through `RECORD_TYPES` on the same project and the user can see both; it shows on both records. Links have no foreign keys and are never cascaded; a voided end shows "voided".

### A.8.6 Sign-offs — التوقيعات
`q_signoffs` (Q-RPM-05). Append-only; shown on every record in a "Sign-offs" panel and printed on forms.

### A.8.7 Attachments
All Quality files go through `attachments.store` (virus scan D-302, photo shrinking D-282, storage cap D-293). **QAO — attachment owner values (all added by Q0):** `q_ncr`, `q_ncr_evidence`, `q_observation`, `q_alert`, `q_complaint`, `q_signoff_scan`, `q_supplier_doc`, `q_mte_doc`, `q_itp`, `q_ir_round`, `q_punch`, `q_floor_plan`, `q_dossier`, `q_mar`, `q_mir`, `q_quarantine`, `q_test_report`, `q_wps`, `q_wpq`, `q_weld`, `q_calibration_cert`, `q_receipt`, `q_import_file`, `q_mapping_report`, `q_pest_visit`, `q_hold`, `q_damage`, `q_return`, `q_recall`, `q_trip`, `q_pod`, `q_document_file`, `q_transmittal`, `q_audit_report`, `q_mgmt_review`, `q_supplier_eval`, `q_report_pack`. Document scans (signed forms, certificates, test reports, delivery notes) use the scan profile of D-282; photos the photo profile.

## A.9 Nonconformance Report (NCR) — تقرير عدم مطابقة

### A.9.1 Entity `q_ncrs`

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| ncr_no | رقم التقرير | string(40) | sys | Q-NUM; at Draft → Open | NCR-ANIA-EXP-2026-0044 | none |
| profile | القطاع | enum | sys | profile at raise | construction | none |
| source_type / source_id / source_ref | المصدر | enum / UUID / string | Y / cond. / sys | list NS; id required except `manual`; ref copied (Q-NCR-02) | test_result / … / TST-ANIA-EXP-2026-0388 | none |
| site_id / zone_id / system_id / location_ref | الموقع / المنطقة / النظام / الموقع التفصيلي | FK / FK / FK / string(120) | Y / N / N / N | from the source when it has them | S-LAND / Z-PIERB / — / Level 3 slab, grid C14–C20 | none |
| title | العنوان | string(150) | Y | — | 28-day cube strength below acceptance, pour POUR-0077 | none |
| requirement_en / _ar | المتطلب | text(1000) | Y (one language) | what was required: criterion, spec clause, drawing | f'c 40 MPa; ACI 318 §26.12.3.1 `[VERIFY]` | none |
| finding_en / _ar | الوضع الفعلي | text(2000) | Y (one language) | what was found; hint "no names or ID numbers" (P1-8 scan) | Set 3 average 33.2 MPa < 36.0 MPa | none |
| category | فئة العيب | enum | Y | list NCAT | material | none |
| detection_stage | مرحلة الاكتشاف | enum | Y | list DS; default from the source | in_process | none |
| classification | التصنيف | enum | Y at Open | list NC; Q-NCR-04/05 | critical | none |
| responsible_engagement_id | الجهة المسؤولة | FK | Y | engagement on the project; default from the source | RAWABI@ANIA-EXP | none |
| supplier_id / customer_id | المورد / العميل | FK / FK | N / N | Q-SHR-02 | Riyadh Readymix | none |
| item_key | مفتاح البند | string(80) | sys | from the source adapter (e.g. `ITP:CIV-001:30`, `TT:CONC-CUBE`, `SKU:NDC-1001`) | TT:CONC-CUBE | none |
| quantity / unit / lot_refs | الكمية / الوحدة / الدفعات | decimal / string(10) / string[] | N | lots, heats, batches, serials (≤ 50) | 186 / m3 / [mix C40-B12] | none |
| raised_by / opened_at | أعدّه / تاريخ الفتح | FK / timestamptz | sys | — | Bilal / 2026-09-29 11:20 | personal |
| owner_id | مسؤول المعالجة | FK | Y at Open | user on the project holding 242 | Bilal | personal |
| containment_en / _ar, containment_done_at, containment_by | الاحتواء | text(1000) / timestamptz / FK | cond. | Q-NCR-07 | Slab load restricted, props kept, cores ordered | personal (by) |
| cause_category | فئة السبب الجذري | enum | cond. | list 6M; required to leave Open | material | none |
| rca_id | تحليل السبب | FK | cond. | Q-NCR-09 | — | none |
| disposition_lines | المعالجة | list {disposition, quantity, note} | cond. | list DP; Q-NCR-11 | [{use_as_is, 186 m3}] | none |
| disposition_justification_en / _ar | مبرر المعالجة | text(2000) | cond. | ≥ 50 chars for use_as_is / repair | Cores avg 37.9 MPa ≥ 0.85 f'c… | none |
| implementation_note / implemented_at | تنفيذ المعالجة | text(1000) / timestamptz | cond. | at Pending Verification | — | none |
| supplier_response | رد المورد | {requested_at, due_on, received_at, accepted, note, file} | N | SCAR (Q-NCR-13) | — | none |
| repeat_of_id | تكرار لـ | FK | sys | Q-NCR-16 | — | none |
| target_close_date / containment_due_at | تاريخ الإغلاق المستهدف / مهلة الاحتواء | date / timestamptz | sys | §A.3 by class at Open | 2026-10-20 | none |
| closed_at / closed_date | تاريخ الإغلاق | timestamptz / date | sys | — | — | none |
| effectiveness | الفعالية | {due_on, result effective / not_effective, note, by, at} | N | Q-NCR-17 | — | personal (by) |
| cost_gross_sar / cost_recovered_sar | التكلفة / المسترد | decimal ×2 | sys | Σ cost lines (§A.9.6) | 20,010.00 / 4,250.00 | none |
| duplicate_of_id / status / status_reason | — | FK / enum / text | — / Y / cond. | §A.9.3 | open | none |

Attachments (`q_ncr` photos, `q_ncr_evidence` evidence files). Every change audited.

### A.9.2 Lists

**NS — NCR source types** (each with its owning part; adapters are registered in `NCR_SOURCES`):

| Code | EN / AR | Part | Default class | Raise mode |
|---|---|---|---|---|
| `manual` | Manual / يدوي | Q0 | entered | manual |
| `observation` | Escalated observation / ملاحظة مُصعّدة | Q0 | minor | manual |
| `complaint` | Customer complaint / شكوى عميل | Q0 | major | manual (justified complaint) |
| `ir` | Inspection request rejected / رفض طلب فحص | Q1 | minor | prompt on rejection |
| `punch_item` | Escalated punch item / بند نواقص مُصعّد | Q1 | minor | manual |
| `mir` | Material rejected on delivery / رفض مواد موردة | Q2 | major | auto on rejection |
| `test_result` | Failed test result / نتيجة اختبار فاشلة | Q2 | major (critical for structural strength) | auto (setting `test_auto_ncr`) |
| `weld` | Weld repair limit or lot expansion / تجاوز حد إصلاح اللحام | Q2 | major | auto (Q-WLD-10) |
| `oot_review` | Out-of-tolerance impact / أثر الخروج عن التفاوت | Q2 | major | from the review decision |
| `receipt` | Receiving deviation or rejection / انحراف أو رفض عند الاستلام | Q3 | minor (reject: major) | prompt |
| `excursion` | Temperature excursion / انحراف حراري | Q3 | by severity | auto for major / critical |
| `stock_check` | FEFO, expiry, damage, cycle count / فحص المخزون | Q3 | minor | manual or prompt |
| `return` | Return inspection / فحص المرتجعات | Q3 | minor | prompt |
| `recall` | Recall / استدعاء | Q3 | critical | auto |
| `trip` | Transport pre-load fail, transit excursion, delivery exception / النقل | Q3 | by severity | auto for transit excursion major / critical, else prompt |
| `hygiene_pest` | Hygiene or pest finding / نظافة أو آفات | Q3 | minor | prompt |
| `q_audit_finding` | Quality audit finding / ملاحظة تدقيق جودة | Q4 | major_nc → major, minor_nc → minor | auto at audit issue |

**NCAT — defect categories** (Pareto dimension; editable labels, codes fixed): `workmanship` جودة التنفيذ · `material` المواد · `design_documentation` التصميم والوثائق · `dimensional` الأبعاد · `testing_failure` فشل الاختبار · `procedure_not_followed` عدم اتباع الإجراء · `damage` تلف · `temperature` الحرارة · `labelling` الملصقات · `expiry_shelf_life` الصلاحية · `contamination_hygiene` التلوث والنظافة · `quantity` الكمية · `traceability` التتبع · `packaging` التغليف · `calibration` المعايرة · `other` أخرى.
**DS — detection stage:** internal: `receiving` الاستلام · `in_process` أثناء التنفيذ · `final_inspection` الفحص النهائي · `internal_audit` تدقيق داخلي · `storage` التخزين; external: `at_customer` لدى العميل · `after_handover` بعد التسليم · `regulator` جهة رقابية.
**NC — classification:** `minor` طفيفة: does not affect fitness for use, safety, compliance or traceability and can be put right to the requirement · `major` جوهرية: affects fitness for use, durability, a key characteristic or a contract requirement, needs a concession or repair, or shows a process failure · `critical` حرجة: affects the safety of people, structural integrity, product safety (food / medicine), legal compliance, or has reached the customer for a safety characteristic.
**6M — cause categories:** `people` الأفراد · `machine` المعدات · `method` الطريقة · `material` المواد · `measurement` القياس · `environment` البيئة.
**DP — dispositions:** `use_as_is` استخدام كما هو (logistics label: "release, no impact" إفراج بدون أثر) · `repair` إصلاح (acceptable but not the original requirement; approved repair procedure) · `rework` إعادة العمل (back to full conformity) · `reject_return` رفض وإرجاع للمورد · `reject_scrap` رفض وإتلاف.
**RCA — methods:** `simple` بيان السبب · `five_why` لماذا الخمسة · `ishikawa` مخطط عظم السمكة · `eight_d` منهجية 8D.

### A.9.3 States and transitions

| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Draft | مسودة | 241 | new, or prefilled from a source (Q-NCR-02) |
| Draft → Open | مفتوح | 241 (raiser) | Q-NCR-03; number assigned; target dates set; owner notified |
| — → Open | مفتوح | System | auto-raise from a source (list NS); raiser = the user whose action triggered it, or System for jobs |
| Draft → deleted | — | raiser | never opened |
| Open → Disposition Proposed | معالجة مقترحة | 242 (owner or 242 holder in scope) | containment (Q-NCR-07), cause category, RCA by class (Q-NCR-09), disposition lines (Q-NCR-11), CA plan (Q-CAP-02) |
| Disposition Proposed → Disposition Approved | معالجة معتمدة | 243 + RPM `ncr.disposition` (and `ncr.concession` for use_as_is / repair lines) | Q-NCR-12 |
| Disposition Proposed → Open | مفتوح | 243 + RPM `ncr.disposition` | returned, comment ≥ 20 chars |
| Disposition Approved → Pending Verification | بانتظار التحقق | 242 | implementation note and evidence; every linked CA In Progress, Pending Verification or Closed |
| Pending Verification → Closed | مغلق | 243 + RPM `ncr.close` | Q-NCR-15 |
| Pending Verification → Disposition Approved | معالجة معتمدة | 243 + RPM `ncr.close` | verification failed, comment ≥ 20 chars |
| Closed → Open | مفتوح | 239 | reopen within 30 days of closure, reason ≥ 20 chars; dates and KPIs follow §E.4 |
| Draft / Open / Disposition Proposed / Disposition Approved → Voided | ملغى | 244 | reason ≥ 20 chars; `duplicate_of` required when the reason is duplicate; linked CAs stay (Q-CAP-08) |

### A.9.4 Rules (Q-NCR)
- **Q-NCR-01.** An NCR can be raised from any record that has a source adapter (list NS), from the NCR register (`manual`), and from the phone ("Raise NCR" with photo and location). Raising needs 241 on the project and a site in the user's scope.
- **Q-NCR-02.** From a source, the adapter fills site, zone, system, engagement, supplier, item_key, detection stage, title and requirement; the user may edit all but source and item_key. A link `raised_from` is created. One source record may have several NCRs; the source shows them.
- **Q-NCR-03.** Draft → Open needs: title, requirement, finding (one language), category, detection stage, classification, responsible engagement, owner, ≥ 1 photo or evidence file for `critical` (`EVIDENCE_REQUIRED`).
- **Q-NCR-04.** The raiser sets the class; the source default (list NS) is proposed. An excursion, recall, failed structural strength test or transit excursion proposes the class the source computed.
- **Q-NCR-05.** The class may be **raised** by any 242 holder at any time before closure (target dates are recomputed from the original opened_at). It may be **lowered** only by a user who resolves for `ncr.disposition`, with a reason ≥ 20 chars (`CLASS_LOWERED_NEEDS_APPROVAL` otherwise); both are audited with old / new.
- **Q-NCR-06.** Opening an NCR notifies the owner, the responsible engagement's quality contact (contractor-assigned quality users of that engagement), the users who resolve for `ncr.disposition` and, for critical, every 239 holder within 60 s (in-app + email; push on the phone).
- **Q-NCR-07.** **Containment** (what was done to stop the effect: segregate, tag, hold, stop the activity) is required for major and critical before Disposition Proposed (`CONTAINMENT_REQUIRED`), due by `containment_due_at`. For logistics product, containment means a Q3 hold (linked) or the statement "no product affected" with reason. Overdue containment alerts the owner and 239 holders (§A.13).
- **Q-NCR-08.** Correction (immediate fix) and corrective action (removing the cause) are kept apart: the disposition fixes the product; CAs remove the cause (Q-CAP).
- **Q-NCR-09.** **RCA** (`q_ncr_rca`): the method must be allowed for the class by `rca_method_by_class` (`RCA_METHOD_NOT_ALLOWED`). Completeness (`RCA_INCOMPLETE`): `simple` — a cause statement ≥ 30 chars; `five_why` — 3 to 7 "why" answers of ≥ 10 chars and a root-cause statement; `ishikawa` — causes in ≥ 2 of the 6M categories and ≥ 1 cause marked root; `eight_d` — D1 team (≥ 2 users), D2 problem statement (what, where, when, how many; is / is not), D3 containment (= Q-NCR-07), D4 root cause and escape point (why it was not detected), D5 chosen permanent actions (≥ 1 CA), D6 implementation and validation dates, D7 prevention of recurrence (process, ITP, procedure or FMEA change, optionally linked to a Q4 document), D8 closure note. The root cause's 6M category becomes `cause_category`.
- **Q-NCR-10.** RCA texts get the P1-8 scan and the hint "describe causes, not people"; a 5-Why answer "operator error" (or AR equivalent) shows warning `HUMAN_ERROR_NOT_ROOT_CAUSE` ("ask why the error was possible").
- **Q-NCR-11.** **Disposition lines** cover the affected quantity: the sum of line quantities equals the NCR quantity when a quantity is given (`DISPOSITION_QTY_MISMATCH`). `use_as_is` and `repair` need a justification ≥ 50 chars and ≥ 1 evidence file (e.g. calculation, core results, stability data) (`CONCESSION_EVIDENCE_REQUIRED`); `repair` names the repair procedure (document or text); `reject_return` names the return note or supplier claim no. by closure; `reject_scrap` needs destruction evidence by closure (for food or medicine: a certificate from a licensed disposal provider `[VERIFY]` MWAN / SFDA).
- **Q-NCR-12.** **Approval** of the disposition is one sign-off per required step: `ncr.disposition` always; plus `ncr.concession` when any line is use_as_is or repair; a step may resolve to the same user (one sign-off then covers both only if the matrix rows name the same assignee). Q-RPM-06 applies: the owner and the raiser cannot approve.
- **Q-NCR-13.** **Supplier response (SCAR):** when supplier_id is set, the owner may request a supplier response (due date, default +14 days); the received response (file, e.g. the supplier's 8D) is accepted or rejected by the owner. A missing or late response feeds the supplier score (§E.3), never blocks closure on its own.
- **Q-NCR-14.** **Costs** are entered at any time before closure (§A.9.6). Closure needs ≥ 1 cost line or the confirmation "no cost incurred" with a reason (`COST_NOT_RECORDED`).
- **Q-NCR-15.** **Close** needs: disposition implemented; every linked CA Closed or Cancelled (cancelled with reason); every `reject_return` / `reject_scrap` line evidenced; costs recorded (Q-NCR-14); and no blocker from the source adapter's `close_check` (e.g. a rework IR not yet approved, a hold not released or rejected). The verifier is the user who resolves for `ncr.close`; Q-RPM-06 applies.
- **Q-NCR-16.** **Repeat NCR:** on Open, an NCR is a repeat when a not-voided NCR with the same `category`, the same responsible party (supplier when set, else responsible engagement) and the same `item_key` was opened within the previous `ncr_repeat_days`. A repeat sets `repeat_of`, raises minor to major (Q-NCR-05 raise), and requires RCA method `five_why`, `ishikawa` or `eight_d`.
- **Q-NCR-17.** **Effectiveness:** at closure, `effectiveness.due_on` = closed_date + `ncr_effectiveness_days`. On the due date the job proposes "effective" when no repeat (Q-NCR-16 key) was opened since closure, else "not effective"; a 242 holder confirms. "Not effective" offers a new linked NCR (source `manual`, link `relates`). The closed NCR stays closed.
- **Q-NCR-18.** Ageing and timing: age_days = local today − local date(opened_at) for NCRs not Closed or Voided; closure_days = closed_date − local date(opened_at); on-time ⇔ closed_date ≤ target_close_date. A reopened NCR keeps its opened_at and target date; its closure_days use the final closure.
- **Q-NCR-19.** The NCR PDF (EN or AR, Hijri date, project, all sections, sign-offs, photos thumbnails, cost summary without rates if the reader lacks 242) uses the 6g renderer.

### A.9.5 CAPA through the existing corrective actions (Q-CAP)
- **Q-CAP-01.** Corrective actions of Quality records are Phase 1 `corrective_actions` rows with `source_type` `quality_ncr` (or `quality_observation`, `quality_complaint`, `quality_audit`, `quality_review`) and `source_id` = the record. There is no second CAPA table. CA states, extensions (CA-2), evidence and verification are unchanged.
- **Q-CAP-02.** Major and critical NCRs need ≥ 1 CA (not cancelled) before Disposition Proposed (`CA_REQUIRED`); for minor NCRs a CA is optional unless the RCA method is not `simple`.
- **Q-CAP-03.** Priority from class: critical → `critical`, major → `high`, minor → `medium` (editable down by one level with a reason). The latest due date uses `quality_ca_due_days` instead of Phase 1 `ca_due_days` for quality source types (`corrective_actions.new_ca` reads a due-days provider by source type, Q0 adds it).
- **Q-CAP-04.** Verifier for quality CAs: a user holding 243 on the project, or the HSE Manager; never the owner (CA-5 unchanged). Phase 1 verifier-role rules for HSE CAs are unchanged.
- **Q-CAP-05.** `control_level` keeps its values; for quality source types the UI shows quality labels: elimination → "Remove the cause (design or process change)" / إزالة السبب; substitution → "Change material, method or supplier" / تغيير المادة أو الطريقة أو المورد; engineering → "Error-proof (fixture, poka-yoke, automation)" / منع الخطأ; administrative → "Procedure, instruction or training" / إجراء أو تعليمات أو تدريب; ppe → "Extra inspection only (detection)" / فحص إضافي فقط. A CA set with `ppe` on a major or critical NCR shows warning `DETECTION_ONLY_ACTION`.
- **Q-CAP-06.** Quality CAs are excluded from HSE KPIs K-40…K-43 (`app/kpi/data.py` filters the quality source types), from the HSE dashboard open-CA counts and from 6g scorecard inputs; they are counted in K-146 (§E.4). The CA register gains a `domain` filter (HSE · Quality · All), default HSE for HSE roles and Quality for quality roles. Quality CAs are visible to holders of 238 in scope as well as to Phase 1 viewers (`corrective_actions.can_view` and `scoped_query` extended).
- **Q-CAP-07.** When the last open CA of an NCR is Closed, the NCR owner is told "all actions closed — ready for verification"; the NCR does not change state by itself.
- **Q-CAP-08.** Voiding an NCR leaves its CAs as they are and flags them "source voided" for the CA verifier to cancel or keep.

### A.9.6 NCR costs and COPQ input (Q-COST)
`q_ncr_costs`: cost_type (list CT), description, quantity, unit, rate_sar, amount_sar, recoverable (bool), recovered_sar, entered_by, entered_at.

**CT — cost types:** `rework_labour` إعادة العمل (h × `labour_rate_sar_h` default) · `repair_labour` الإصلاح (h × rate) · `material` مواد بديلة · `plant` معدات (h × `plant_rate_sar_h`) · `retest_reinspection` إعادة الاختبار والفحص · `scrap_writeoff` إتلاف / شطب (product value) · `delay` تأخير (days × `delay_rate_sar_day`, `DELAY_RATE_NOT_SET` without it) · `transport_return` نقل وإرجاع · `disposal` تخلص · `customer_credit` تعويض للعميل · `claim_penalty` غرامة أو مطالبة · `other` أخرى.

- **Q-COST-01.** amount_sar = quantity × rate_sar (2 dp, half-up) for rate-based types; a lump sum has quantity 1. Amounts ≥ 0.
- **Q-COST-02.** Failure class: `internal` when detection_stage is internal (list DS), `external` otherwise; COPQ (§E.6) uses it. cost_gross_sar = Σ amount; cost_recovered_sar = Σ recovered (≤ amount per line).
- **Q-COST-03.** Rates in use are stored on the line (later setting changes do not alter it). Cost lines are visible to 242 and 239 holders and the HSE Manager; others see totals only.
- **Worked example QX1.** NCR-ANIA-EXP-2026-0044: rework labour 36 h × 85.00 = 3,060.00; material 4,250.00 (recoverable, recovered 4,250.00); retest 2 × 350.00 = 700.00; delay 1 day × 12,000.00 = 12,000.00 → gross **20,010.00**, recovered **4,250.00**, net 15,760.00; detection `in_process` → internal failure.

## A.10 Observations, quality alerts and customer complaints

### A.10.1 Quality observation — ملاحظة جودة (Q-OBS)
`q_observations`: obs_no, site / zone / system / location_ref, category (NCAT), description (P1-8 scan), photos, suggested action, raised_by, status `open` مفتوحة → `actioned` تم اتخاذ إجراء (CA source `quality_observation`, or escalated to an NCR source `observation`) · `closed` مغلقة (RPM `observation.close`, reason).
- **Q-OBS-01.** An observation is a weakness or risk that does not yet breach a requirement; if a requirement is breached the screen asks "Raise an NCR instead?" and offers the conversion (the observation closes as `actioned` with the link).
- **Q-OBS-02.** Observations never count as NCRs; they feed K-169's chip and the Pareto when the setting `pareto_include_observations` (Q4) is true.

### A.10.2 Quality alert — تنبيه جودة (Q-OBS-03…05)
`q_alerts`: alert_no, title EN / AR, message EN / AR (P1-8 scan), severity (`info` معلومة · `warning` تحذير · `stop_use` إيقاف الاستخدام), applies_to (sites, disciplines, suppliers, SKUs, lots — text and refs), valid_until, distribution (roles, positions, engagements, users), ack_required, status `draft` → `issued` (RPM `quality_alert.issue`) → `expired` (System, valid_until) · `withdrawn` (239, reason). `q_alert_acks`: alert, user, acked_at.
- **Q-OBS-03.** Issuing notifies every distribution member in-app and by email in their language. A `stop_use` alert shows a red banner on the Quality home of the listed sites until expiry.
- **Q-OBS-04.** With ack_required, each member acknowledges once (275); acknowledgement % is shown on the alert; members who have not acknowledged after 3 days are reminded once.
- **Q-OBS-05.** Alerts are information. They block nothing in other records (a `stop_use` alert on a lot is enforced by a hold or quarantine, not by the alert).

### A.10.3 Customer complaint — شكوى عميل (Q-CMP)
`q_complaints`: complaint_no, customer_id, received_at, channel (`email` · `phone` · `letter` · `meeting` · `portal` · `other`), customer reference, category (NCAT), description (P1-8 scan), product / SKU / lot / location refs, severity (`low` · `medium` · `high`), acknowledged_at, investigation note, justified (yes / no / partly), linked NCR, response_en / _ar, responded_at, customer satisfied (yes / no / no reply), status.

| From → To | AR | Who | Condition |
|---|---|---|---|
| — → Received | مستلمة | 245 | — |
| Received → Acknowledged | تم الإقرار | 245 | acknowledgement sent (date, method) |
| Acknowledged → Under Investigation | قيد التحقيق | 245 | — |
| Under Investigation → Responded | تم الرد | 245 + RPM `complaint.response` | justified set; response text; a justified complaint links an NCR (source `complaint`, detection `at_customer`) (`NCR_REQUIRED_FOR_JUSTIFIED`) |
| Responded → Closed | مغلقة | 245 + RPM `complaint.close` | satisfaction recorded or "no reply" after 14 days; the linked NCR may still be open |
| Received / Acknowledged / Under Investigation → Withdrawn | مسحوبة | 245 | customer withdrew, note |

- **Q-CMP-01.** Acknowledgement is due within `complaint_ack_hours`, the response within `complaint_response_days` of received_at; overdue alerts 239 holders.
- **Q-CMP-02.** Customer contact data are personal (P8-2) and shown only to 245 holders.

## A.11 Permission matrix — Phase 8 (capabilities 238–280; Q0 adds all)

Legend as Phase 0 §5.10 (A all projects · P project · S assigned sites · C own engagement tree · C1 own engagement · R read-only · — none) plus **N** = only records where the user resolves as responsible person for a pending or signed step (Q-ROL-04). Every grant of a quality role is narrowed by Q-ROL-02 (engagement) and Phase 0 rule 11 (sites). Steps marked (RPM) also need the user to resolve as responsible person (Q-RPM-03). Writes on profile-specific capabilities follow Q-PRF-04.

| # | Capability | QA/QC Mgr | Q Eng | QC Insp | Whse QC | Resp. Person | HSE Mgr | HSE Off | Site Eng | C-HSE Rep | Viewer |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 238 | View Quality home, registers, NCRs, KPIs (profile-aware) | P | P | P | P | N | A | P | S | C | P (aggregates, no names, no costs) |
| 239 | Edit Quality settings, profile, positions, matrix, numbering; publish criteria and quality checklists; assign quality roles | P (not contractor-assigned) | — | — | — | — | A | — | — | — | — |
| 240 | Author criteria and quality checklist drafts | P | P | — | — | — | A | — | — | — | — |
| 241 | Raise NCRs and observations | P | P | P | P | N | A | P | S | — | — |
| 242 | Manage NCRs (owner work: containment, RCA, CA plan, disposition proposal, costs, SCAR) | P | P | P | P | — | A | — | — | — | — |
| 243 | Approve NCR disposition, concession and close (RPM); verify quality CAs | P | P | — | — | N | A | — | — | — | — |
| 244 | Void Quality records | P (not contractor-assigned) | — | — | — | — | A | — | — | — | — |
| 245 | Customer complaints | P | P | — | P | — | A | — | — | — | — |
| 246 | Export Quality registers | P | P | P | P | — | A | P | S | C | P (no names, no costs) |
| 247 | Author ITPs | P | P | — | — | — | A | — | — | — | — |
| 248 | Approve ITPs (RPM) | P | P | — | — | N | A | — | — | — | — |
| 249 | Raise and submit IRs; respond to IR comments | P | P | P | — | — | A | — | S | — | — |
| 250 | Schedule, inspect and decide IRs (RPM) | P | P | P | — | N | A | — | — | — | — |
| 251 | Record punch items | P | P | P | — | N | A | — | S | — | — |
| 252 | Verify and close punch items (RPM) | P | P | P | — | N | A | — | — | — | — |
| 253 | Compile and submit dossiers; as-built lists | P | P | — | — | — | A | — | — | — | — |
| 254 | Accept dossiers (RPM) | P | — | — | — | N | A | — | — | — | — |
| 255 | Submit MARs and MIRs | P | P | P | — | — | A | — | S | — | — |
| 256 | Decide MARs and MIRs; dispose of quarantined material (RPM) | P | P | P (MIR) | — | N | A | — | — | — | — |
| 257 | Test requests, sampling, specimens, results entry, pours | P | P | P | P | — | A | — | S | — | — |
| 258 | Verify and amend test results (RPM) | P | P | — | — | N | A | — | — | — | — |
| 259 | Welding records (WPS / PQR drafts, welders, WPQs, weld log, NDT) | P | P | P | — | — | A | — | — | — | — |
| 260 | Approve WPS, PQR, WPQ (RPM) | P | P | — | — | N | A | — | — | — | — |
| 261 | M&TE register and calibration records | P | P | P | P | — | A | — | — | — | — |
| 262 | Accept calibrations; decide out-of-tolerance reviews (RPM) | P | P | — | — | N | A | — | — | — | — |
| 263 | Competence requirements (edit: QA/QC Mgr, Q Eng); competence matrix (view) | P | P | P (view) | P (view) | — | A | — | — | — | — |
| 264 | Receiving inspections (record, accept) | P | P | P | P | — | A | — | — | — | — |
| 265 | Receiving deviation and rejection decisions (RPM) | P | P | — | P | N | A | — | — | — | — |
| 266 | Storage zones, monitoring points, mapping studies, check schedules, pest stations, hygiene and pest records | P | P | — | P | — | A | — | — | — | — |
| 267 | Readings (manual entry, logger CSV import) | P | P | P | P | — | A | — | — | — | — |
| 268 | Assess excursions and product impact (RPM for approval) | P | P | — | P | N | A | — | — | — | — |
| 269 | Stock quality records (imports, FEFO checks, damage, returns, cycle counts, throughput) | P | P | — | P | — | A | — | — | — | — |
| 270 | Place holds (all with 269); release or reject holds (RPM) | P | P | — | P (place only) | N | A | — | — | — | — |
| 271 | Recalls and mock recalls | P | P | — | P | N | A | — | — | — | — |
| 272 | Transport records (trips, pre-load checks, transit readings, POD) | P | P | P | P | N (override) | A | — | — | — | — |
| 273 | Author documents, revisions, distribution, transmittals | P | P | — | P | — | A | — | — | — | — |
| 274 | Review and approve documents (RPM) | P | P | — | — | N | A | — | — | — | — |
| 275 | Acknowledge documents and quality alerts | every user named in a distribution | | | | | | | | | |
| 276 | Plan and conduct quality audits, audit programme, management reviews, process register | P | P | — | — | — | A | — | — | — | — |
| 277 | Issue quality audit reports; approve management review minutes (RPM) | P | — | — | — | N | A | — | — | — | — |
| 278 | Supplier register, evaluations, scorecards | P | P | — | P | — | A | — | — | — | — |
| 279 | Approve, suspend, disqualify suppliers (RPM) | P | — | — | — | N | A | — | — | — | — |
| 280 | Quality report packs (prepare, issue, distribution) | P | P | — | — | — | A | R (issued) | — | — | R (issued) |

Permit Issuer, Permit Receiver and the OH Practitioner get no Phase 8 capability. Suspended-contractor users keep reads and lose writes (Phase 0 rule 28). The HSE Manager holds every capability org-wide but resolves as responsible person only through the matrix (Q-RPM-03, Q-RPM-09).

## A.12 Navigation and Q0 screens (Q-NAV)

- **Q-NAV-01.** The sidebar gains one group **Quality / الجودة** after the HSE groups, shown when the user holds 238 on the current project (or 241 / N steps). Items come from the registry files `nav/q0…q4.ts`, each with `profiles`; items of the inactive profile are hidden except "Other profile — finish only" lists when such open records exist (Q-PRF-04).
- **Q-NAV-02.** Q0 items: Quality home, Awaiting my sign-off (badge = count), NCRs, Observations, Quality alerts, Complaints, Suppliers, Customers, Systems (construction), Criteria library, Quality settings (239).

| Screen | Phone (field) | Desk |
|---|---|---|
| Quality home `/quality` | Big buttons: Raise NCR, Observation, Awaiting me (count); my open NCR tasks | Profile badge; tiles from §E.7 when Q4 exists (Q0 shows NCR counts by class and status, overdue containment, steps without a responsible person); stop-use alerts banner |
| Raise NCR `/quality/ncrs/new` | One screen: photo (camera), title, finding, category, class, location (site / zone from GPS-free picker), source picked by scanning or searching; saves as Draft offline (6d EXE-6 cache rules) | Full form with requirement, quantity, lots, supplier |
| NCR register `/quality/ncrs` | Card list, filters: mine, open, overdue | Table: no, class chip, status, category, source, responsible, supplier, age, target date, cost; filters incl. repeat, profile, detection stage; export (246) |
| NCR detail `/quality/ncrs/[id]` | Read, add photo, containment, CA progress | Tabs: Details · Containment · Root cause (method-specific form: 5-Why chain, Ishikawa 6M board, 8D D0–D8) · Disposition · Actions (Phase 1 CA cards, create CA inline) · Costs · Supplier response · Sign-offs · Links · History; PDF EN / AR; tabs registered by later parts |
| Awaiting me `/quality/awaiting` | Same list, tap to act | Grouped by record type |
| Settings `/quality/settings` | — | Tabs: Profile · Responsible persons (matrix grid record type × step, qualifier rows) · Positions and holders · Numbering (live preview) · Checklist defaults · Part settings (rendered from the schema, Q-SET-01) |
| Criteria, suppliers, customers, systems | Read | Registers with versions (criteria), accreditation and status (suppliers) |

## A.13 Notifications (all parts follow these rules)

Channels as earlier phases (in-app and email in the recipient's language; push on the phone web app; no SMS, DECISIONS #124). Each (record, step, recipient) is sent once; re-running a job never sends twice. Q0 alerts:

| Trigger | Recipient | Timing | Channel |
|---|---|---|---|
| NCR opened | owner; engagement quality contacts; `ncr.disposition` resolvers; 239 holders for critical | within 60 s | in-app + email (+ push critical) |
| Step pending for me (any part) | resolved responsible persons | at the step; reminder daily 07:12 while pending > 24 h | in-app + email |
| Containment overdue | owner; 239 holders | at containment_due_at, then daily | in-app + email |
| NCR target close date passed | owner; 239 holders; engagement quality contacts | day after, then weekly | in-app + email |
| All CAs of an NCR closed | owner | immediately | in-app |
| Effectiveness check due | owner | on due_on 07:12 | in-app |
| Quality alert issued / ack reminder | distribution | at issue / +3 days | in-app + email |
| Complaint ack / response overdue | 245 holders; 239 holders | at the deadline | in-app + email |
| Supplier response (SCAR) overdue | NCR owner | day after due | in-app |
| Step without responsible person | 239 holders | daily digest | in-app |

## A.14 PDPL (P8; all parts)
- **P8-1. Personal:** user identities on records (raisers, inspectors, signers, custodians); external signatory names; supplier and customer contacts; worker links of welders and inspectors; POD receiver names and signatures; photos (may show people); the offline cache. **Sensitive:** none (Phase 8 stores no health or ID numbers; welder ID numbers are never copied from Phase 2, P2-7).
- **P8-2.** Free texts get the P1-8 scan with the hint "no names, ID or medical details". Supplier and customer contacts are visible to 278 / 245 holders only and are omitted from exports for Viewer / Client.
- **P8-3.** Photos follow 6d P6d-3 (hint "photograph the work or the product, not people"; EXIF stripped; Viewer / Client never sees photos).
- **P8-4.** KPIs and AI answers are aggregates; no person names (T26–T29, §E.9). Supplier, contractor and customer names are business names and may appear.
- **P8-5.** Retention: Quality records are kept for the project life + 10 years ASSUMPTION (handover dossiers and test records support the building's defects-liability and the Saudi decennial liability for structures `[VERIFY]` Civil Transactions Law); logistics records for 5 years after the record date ASSUMPTION (`[VERIFY]` SFDA record retention for medicinal-product distribution). Personal fields are anonymised at the end; signatures are deleted then.
- **P8-6.** Paper sign-off scans carry personal data and are shown only to 238 holders of the record's scope (not Viewer / Client).

## A.15 Error and warning codes (Q0; later parts add their own in their section)
422 `PROFILE_REQUIRED`, `SETTING_OUT_OF_RANGE`, `RESPONSIBLE_PERSON_NOT_SET`, `SOD_CONFLICT`, `NUMBER_FORMAT_INVALID`, `EVIDENCE_REQUIRED`, `CLASS_LOWERED_NEEDS_APPROVAL`, `CONTAINMENT_REQUIRED`, `RCA_METHOD_NOT_ALLOWED`, `RCA_INCOMPLETE`, `DISPOSITION_QTY_MISMATCH`, `CONCESSION_EVIDENCE_REQUIRED`, `CA_REQUIRED`, `COST_NOT_RECORDED`, `DELAY_RATE_NOT_SET`, `NCR_CLOSE_BLOCKED` (with the blocker list), `NCR_REQUIRED_FOR_JUSTIFIED`, `SUPPLIER_DISQUALIFIED`, `MTE_NOT_CALIBRATED` (block mode), `STOP_RULE_NOT_ALLOWED`, `LINK_NOT_ALLOWED`; 409 `PROFILE_INACTIVE`, `INVALID_TRANSITION`, `CRITERION_IMMUTABLE`. Warnings: `SUPPLIER_NOT_APPROVED`, `LAB_NOT_ACCREDITED_FOR_SCOPE`, `MTE_NOT_CALIBRATED` (warn mode), `HUMAN_ERROR_NOT_ROOT_CAUSE`, `DETECTION_ONLY_ACTION`, `COMPETENCE_NOT_MET` (warn mode).

## A.16 Acceptance criteria — Q0

Fixtures: the Phase 0–7b seed plus Appendix A; clock `HSE_CLOCK_AT` = **2026-10-06 10:00** (+03:00) via the `clock` fixture; users as Appendix A.1 (Hatem QA/QC Manager ANIA-EXP; Bilal Quality Engineer RAWABI-assigned; Joseph QC Inspector RAWABI; Abdullah responsible person, position CONSULTANT_RE; Sultan responsible person, position CLIENT_REP; Reem QA/QC Manager RUH-CCH; Imran Warehouse QC; Saad responsible person, position WAREHOUSE_MGR; Lama responsible person, RESP_PHARMACIST).

**Roles, profile, settings**
1. **AC-Q0-01** (Q-ROL-02) **Given** Bilal holds quality_engineer on ANIA-EXP with engagement RAWABI **When** he lists NCRs **Then** only NCRs whose responsible engagement is RAWABI, NAJD, GULFPAVE or SAHARA are returned; an NCR of a QIMMA engagement on RBT-52 by id → 404 and `access_denied` logged.
2. **AC-Q0-02** (Q-ROL-03) **Given** Bilal **When** he PATCHes Quality settings or voids an NCR **Then** 403.
3. **AC-Q0-03** (Q-ROL-04) **Given** Abdullah (responsible_person) **When** he lists NCRs **Then** he sees only NCRs with a step where he resolves or has signed; `GET /quality/kpis` → 403.
4. **AC-Q0-04** (Q-PRF-01) **Given** a new project with no profile **When** a user raises an NCR **Then** 422 `PROFILE_REQUIRED`; after Hatem sets `construction` it succeeds.
5. **AC-Q0-05** (Q-PRF-03, Q-PRF-04) **Given** ANIA-EXP switched to `logistics` with reason **Then** the change is audited with old / new; creating an IR → 409 `PROFILE_INACTIVE`; deciding an IR that was Scheduled before the switch succeeds; the NCR register still lists construction NCRs.
6. **AC-Q0-06** (Q-PRF-06) **Given** a project created with type `logistics` **Then** its Quality profile defaults to logistics; a `building_highrise` project defaults to construction.
7. **AC-Q0-07** (Q-SET-01) **Given** `GET /quality/settings/schema` **Then** every key of §A.3 and of §B.2, §C.1, §D.1, §E.1 is listed with default and range; PATCH `ncr_repeat_days` = 20 → 422 `SETTING_OUT_OF_RANGE`; 120 → saved and audited.

**Responsible-person matrix and sign-offs**
8. **AC-Q0-08** (Q-RPM-03) **Given** the default row `ir.inspect` H → position CONSULTANT_RE held by Abdullah **Then** Abdullah resolves for a hold-point IR and Hatem does not.
9. **AC-Q0-09** (Q-RPM-02) **Given** no active row for `ncr.close` **When** the owner asks to close **Then** 422 `RESPONSIBLE_PERSON_NOT_SET` and the NCR is listed under "steps without a responsible person".
10. **AC-Q0-10** (Q-RPM-06) **Given** Hatem raised NCR-…-0044 and also resolves for `ncr.disposition` **When** he approves the disposition **Then** 422 `SOD_CONFLICT`; with `self_approval_allowed` true on that row **Then** allowed.
11. **AC-Q0-11** (Q-RPM-07) **Given** a matrix row naming role quality_engineer for `ncr.close` and Bilal (RAWABI-assigned) **When** he closes a RAWABI NCR **Then** 422 `SOD_CONFLICT`; for a GULFPAVE NCR with `own_tree_allowed` false **Then** still refused (GULFPAVE is in RAWABI's tree); for an NCR whose responsible engagement is outside his tree **Then** 404.
12. **AC-Q0-12** (Q-RPM-01) **Given** the `ncr.disposition` row changed from role qa_qc_manager to user Sultan **Then** Sultan resolves and Hatem no longer does, without a code change.
13. **AC-Q0-13** (Q-RPM-08) **Given** a row with `paper_allowed` **When** Hatem records an external approval without a scan **Then** 422; with name, organisation, position, date and a PDF **Then** a sign-off with channel `paper` is stored and printed "Signed on paper by …, recorded by Hatem"; with `paper_allowed` false **Then** 422.
14. **AC-Q0-14** (Q-RPM-09) **Given** Faisal (HSE Manager) who does not resolve **When** he approves a step **Then** 403; when he re-assigns the step to Sultan with a reason **Then** Sultan resolves for that record only and an audit entry exists.
15. **AC-Q0-15** (Q-RPM-05) **Given** any sign-off **When** an UPDATE or DELETE is attempted through the API **Then** 405 / no route exists; the row is shown on the record with role or position at signing.
16. **AC-Q0-16** (Q-RPM-11) **Given** Abdullah resolves for 3 pending steps (an IR, an ITP, an NCR concession) **Then** "Awaiting my sign-off" lists the 3, oldest first, with the badge 3.

**Numbering, criteria, checklists, shared registers**
17. **AC-Q0-17** (Q-NUM-03) **Given** two NCRs opened concurrently on ANIA-EXP **Then** they get consecutive, different numbers; a voided NCR's number is never reused.
18. **AC-Q0-18** (Q-NUM-02, Q-NUM-04) **Given** a format `{PFX}-{PROJECT}` **Then** 422 `NUMBER_FORMAT_INVALID`; changing NCR format to `{PFX}/{PROJECT}/{YY}/{SEQ5}` leaves existing numbers unchanged and the next NCR is `NCR/ANIA-EXP/26/00045`.
19. **AC-Q0-19** (Q-CRT-01) **Given** criterion `COMP-95` (kind min, 95.0 %) **Then** 96.2 → pass, 95.0 → pass, 94.4 → fail; criterion kind target_tolerance 100 ± 25 mm: 75 and 125 pass, 130 fails.
20. **AC-Q0-20** (Q-CRT-02) **Given** a record pinned to COMP-95 v1 **When** v2 (98.0 %) is published **Then** the record's verdict is unchanged.
21. **AC-Q0-21** (Q-CHK-01, Q-CHK-02) **Given** a quality template draft with a `stop_work` item **Then** publish → 422 `STOP_RULE_NOT_ALLOWED`; Noura (HSE Officer, capability 193) publishing a kind `quality` template → 403.
22. **AC-Q0-22** (Q-CHK-03) **Given** quality checklist responses in September **Then** K-34, K-35 and K-110 for September are unchanged.
23. **AC-Q0-23** (Q-SHR-02) **Given** supplier GULFPIPE suspended **When** a MAR names it **Then** warning `SUPPLIER_NOT_APPROVED`; a disqualified supplier → 422 `SUPPLIER_DISQUALIFIED`.
24. **AC-Q0-24** (Q-SHR-04) **Given** M&TE MTE-0015 with cal_status overdue and `mte_use_policy` warn **When** a usage is recorded **Then** stored with verdict `warned` and warning `MTE_NOT_CALIBRATED`; with policy `block` **Then** 422.
25. **AC-Q0-25** (Q-SHR-05) **Given** a link from an NCR on ANIA-EXP to a record on RUH-CCH **Then** 422 `LINK_NOT_ALLOWED`.

**NCR**
26. **AC-Q0-26** (Q-NCR-03) **Given** a critical draft without photo or evidence **When** opened **Then** 422 `EVIDENCE_REQUIRED`; with a photo **Then** Open, number assigned, target close = opened date + 21 days, containment due = opened_at + 24 h.
27. **AC-Q0-27** (Q-NCR-06) **Given** a critical NCR opened at 11:20 **Then** within 60 s the owner, the RAWABI quality contacts, the disposition resolvers and Hatem have in-app and email notifications.
28. **AC-Q0-28** (Q-NCR-05) **Given** a major NCR **When** the owner sets minor **Then** 422 `CLASS_LOWERED_NEEDS_APPROVAL`; Hatem (resolver, not the raiser) lowers it with a reason **Then** saved and audited; raising minor → major by the owner is allowed.
29. **AC-Q0-29** (Q-NCR-07) **Given** a major NCR without containment **When** the owner proposes the disposition **Then** 422 `CONTAINMENT_REQUIRED`; at containment_due_at the owner and Hatem are alerted once.
30. **AC-Q0-30** (Q-NCR-09) **Given** a critical NCR with RCA method five_why **Then** 422 `RCA_METHOD_NOT_ALLOWED`; an eight_d with only one team member **Then** 422 `RCA_INCOMPLETE`; a five_why answer "operator error" on a major NCR **Then** warning `HUMAN_ERROR_NOT_ROOT_CAUSE`.
31. **AC-Q0-31** (Q-NCR-11) **Given** NCR quantity 186 m3 and lines 100 rework + 80 use_as_is **Then** 422 `DISPOSITION_QTY_MISMATCH`; a use_as_is line with a 30-char justification **Then** 422 `CONCESSION_EVIDENCE_REQUIRED`.
32. **AC-Q0-32** (Q-NCR-12) **Given** a use_as_is disposition **Then** approval needs a `ncr.disposition` sign-off and a `ncr.concession` sign-off (Abdullah); with only the first **Then** the NCR stays Disposition Proposed.
33. **AC-Q0-33** (Q-CAP-02) **Given** a major NCR with no CA **When** the disposition is proposed **Then** 422 `CA_REQUIRED`; with one CA created inline **Then** the CA has source_type `quality_ncr`, priority high and due ≤ created + 30 days; a due date of +31 days → 422 `DUE_DATE_TOO_LATE`.
34. **AC-Q0-34** (Q-CAP-04) **Given** a quality CA **When** Noura (HSE Officer, no 243) is set as verifier **Then** 422 `VERIFIER_ROLE_NOT_ALLOWED`; Hatem **Then** accepted.
35. **AC-Q0-35** (Q-CAP-06) **Given** the September seed **Then** K-41 and K-42 for ANIA-EXP equal their pre-Phase-8 values (quality CAs excluded) and the CA register with domain Quality lists the quality CAs only.
36. **AC-Q0-36** (Q-NCR-15) **Given** an NCR with an open CA, a reject_scrap line without destruction evidence and no cost line **When** close is attempted **Then** 422 `NCR_CLOSE_BLOCKED` listing the three blockers.
37. **AC-Q0-37** (Q-COST-01, QX1) **Given** QX1 lines **Then** gross 20,010.00, recovered 4,250.00, failure class internal; a delay line with `delay_rate_sar_day` null → 422 `DELAY_RATE_NOT_SET`.
38. **AC-Q0-38** (Q-NCR-16) **Given** NCR A (material, Riyadh Readymix, `TT:CONC-CUBE`) opened 2026-07-02 **When** NCR B with the same key opens 2026-09-29 (89 days) **Then** B is a repeat, raised to major and RCA `simple` refused; opened on 2026-10-01 (91 days) **Then** not a repeat.
39. **AC-Q0-39** (Q-NCR-17) **Given** an NCR closed 2026-07-01 and no repeat since **Then** on 2026-09-29 the job proposes "effective"; with a repeat on 2026-08-15 **Then** "not effective" is proposed.
40. **AC-Q0-40** (Q-NCR-18) **Given** an NCR opened 2026-08-10 and still open at the clock **Then** age 57 days; closed 2026-09-15 with target 2026-09-09 **Then** closure_days 36, not on time.
41. **AC-Q0-41** (Q-NCR-19) **Given** an NCR **When** the PDF is generated in AR **Then** it is RTL, shows the Hijri date of issue (from `app.core.hijri`), sign-offs and cost totals; for a user without 242 rates are absent.

**Observations, alerts, complaints, navigation, licence, PDPL**
42. **AC-Q0-42** (Q-OBS-01) **Given** an observation converted to an NCR **Then** the NCR has source `observation`, a `raised_from` link, and the observation is `actioned`.
43. **AC-Q0-43** (Q-OBS-03, Q-OBS-04) **Given** a stop_use alert with ack_required to role qc_inspector on S-LAND **Then** Joseph sees the banner and acknowledges once; a second ack is idempotent; non-ackers get one reminder on day 3.
44. **AC-Q0-44** (Q-CMP) **Given** a complaint marked justified without an NCR **When** responded **Then** 422 `NCR_REQUIRED_FOR_JUSTIFIED`; acknowledgement 25 h after receipt with `complaint_ack_hours` 24 **Then** the overdue alert was sent at 24 h.
45. **AC-Q0-45** (Q-NAV-01) **Given** RUH-CCH (logistics) **Then** the Quality group shows no ITP, IR, MAR or welding items; ANIA-EXP shows no receiving, storage or transport items; both show NCRs, suppliers and documents.
46. **AC-Q0-46** (D-290, D-319) **Given** the licence is read-only **Then** every Quality POST / PATCH / PUT → 403 `LICENCE_READ_ONLY`, while `GET` registers, NCR PDFs and `POST /exports` of Quality datasets work.
47. **AC-Q0-47** (P8-2, P8-4) **Given** Sarah (Viewer) **Then** Quality registers show no person names, no photos, no costs and no supplier contacts; an export with names by Hatem writes an `export` audit row.
48. **AC-Q0-48** (rule 41) **Given** the UI in Arabic **Then** every Q0 label, status, list value, error, email and PDF has AR text; numbers, codes and dates stay LTR inside RTL; the i18n check covers `messages/quality/*.json`.
