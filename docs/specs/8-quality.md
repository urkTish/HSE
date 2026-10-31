# Module Spec — Phase 8: Quality (QA/QC) — NCR, ITP and inspection requests, materials and testing, welding, calibration, competence, cold-chain logistics, documents, audits, suppliers, KPIs, SPC, COPQ

**Version:** v1.2 · **Date:** 2026-10-31 · **Author:** Quality Consultant Agent · **Status:** Draft. Turki (owner) asked to build everything and review afterwards (handover §1); defaults are chosen so the build can start (§7).
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
| **Q0** | `q_settings`, `q_positions`, `q_position_holders`, `q_rp_rules`, `q_numbering`, `q_criteria`, `q_systems`, `q_suppliers`, `q_supplier_accreditations`, `q_customers`, `q_mte_items`, `q_mte_usage`, `q_links`, `q_signoffs`, `q_ncrs`, `q_ncr_lines`, `q_ncr_costs`, `q_ncr_rca`, `q_observations`, `q_alerts`, `q_alert_acks`, `q_complaints`; columns added to `checklist_templates` (`quality_type`, `sector_profiles`) | `app/core/quality/common.py`; `app/models/quality/__init__.py`, `q0.py`; `app/schemas/quality/q0/`; `app/services/quality/__init__.py` (calls each part's `register()`), `app/services/quality/{registry,settings,rpm,numbering,criteria,signoff,links,suppliers,customers,systems,mte,files,jobs}.py`, `app/services/quality/ncr/`, `alerts.py`, `complaints.py`; `app/api/routers/quality/__init__.py`, `q0/`; `app/seed_quality.py`; migration `q0_…` on `c0025`; one-line hooks in `main.py`, `scheduler.py`, `models/__init__.py`, `attachments.py`, `corrective_actions.py`, `permissions.py`, `kpi/data.py`, `dashboard.py`, `scorecard/datasets.py`; frontend `src/i18n/request.ts`, `scripts/check-i18n.mjs`, `src/components/quality/nav/`, `src/components/quality/registry/`, `src/lib/api/quality/`, one Quality group in `sidebar-nav.tsx`; all stubs of §3.3a | `ncrs/`, `observations/`, `alerts/`, `complaints/`, `settings/`, `criteria/`, `suppliers/`, `customers/`, `systems/`, `mte/` (M&TE register list and detail; Q2 adds tabs), `awaiting/`, `page.tsx` (Quality home) | `tests/quality/q0/`; `e2e/quality/q0-*.spec.ts` |
| **Q1** | `q_itps`, `q_itp_points`, `q_irs`, `q_ir_rounds`, `q_ir_comments`, `q_floor_plans`, `q_punch_items`, `q_dossiers`, `q_asbuilt_items` | `app/core/quality/q1.py`, `app/models/quality/q1.py`, `app/schemas/quality/q1/`, `app/services/quality/q1/`, `app/api/routers/quality/q1/`, `app/seed_quality_q1.py`, migration `q1_…` | `itps/`, `inspection-requests/`, `punch/`, `floor-plans/`, `dossiers/` | `tests/quality/q1/`; `e2e/quality/q1-*.spec.ts` |
| **Q2** | `q_mars`, `q_mirs`, `q_quarantine_items`, `q_test_types`, `q_test_requests`, `q_test_specimens`, `q_pours`, `q_wps`, `q_pqrs`, `q_welders`, `q_wpqs`, `q_welds`, `q_calibrations`, `q_oot_reviews`, `q_oot_items`, `q_competence_reqs` | same pattern with `q2` | `materials/`, `material-inspections/`, `quarantine/`, `tests/`, `test-types/`, `pours/`, `welding/`, `calibration/`, `competence/` | `tests/quality/q2/`; `e2e/quality/q2-*.spec.ts` |
| **Q3** | `q_products`, `q_import_batches`, `q_storage_zones`, `q_monitoring_points`, `q_readings`, `q_excursions`, `q_excursion_impacts`, `q_mapping_studies`, `q_check_schedules`, `q_pest_stations`, `q_pest_visits`, `q_receipts`, `q_receipt_lines`, `q_stock_snapshots`, `q_stock_lines`, `q_fefo_checks`, `q_holds`, `q_hold_lines`, `q_damage_reports`, `q_returns`, `q_return_lines`, `q_recalls`, `q_recall_items`, `q_cycle_counts`, `q_cycle_count_lines`, `q_shipments`, `q_shipment_lines`, `q_trips`, `q_pods`, `q_throughput` | same pattern with `q3` | `receiving/`, `storage/`, `readings/`, `excursions/`, `mapping/`, `hygiene/`, `pest/`, `stock/`, `holds/`, `returns/`, `recalls/`, `transport/`, `imports/`, `products/` | `tests/quality/q3/`; `e2e/quality/q3-*.spec.ts` |
| **Q4** | `q_documents`, `q_document_revisions`, `q_doc_distribution`, `q_doc_acks`, `q_transmittals`, `q_transmittal_items`, `q_processes`, `q_audit_programme_lines`, `q_management_reviews`, `q_supplier_evaluations`, `q_supplier_scores`, `q_kpi_targets`, `q_spc_charts`, `q_work_value`; columns added to `field_audits` (`domain`, `auditee_supplier_id`, `process_ids`) | same pattern with `q4`; plus `app/kpi/quality.py`, `app/kpi/quality_views.py`, AI tools in `app/ai/tools.py`, 6d audit and KPI edits (§E.2), 6g pack types | `documents/`, `transmittals/`, `audits/`, `audit-programme/`, `management-reviews/`, `supplier-scores/`, `kpis/`, `spc/`, `reports/` | `tests/quality/q4/`; `e2e/quality/q4-*.spec.ts` |

Shared files that wave-2 parts may still touch (all known to the integrator, handover §3): their own Alembic file (re-chained by the integrator), `docs/contracts/openapi.yaml` and `frontend/src/lib/api/schema.d.ts` (regenerated by the integrator; packages regenerate locally but never bump `CONTRACT_VERSION`), `docs/DECISIONS.md` (own range only, appended) and `docs/PROGRESS.md` (own section only). Nothing else. Q4 runs alone in wave 3 and may edit Q0 files and the 6d / 6g / KPI / AI files listed in its row.

### 3.3a Stubs Q0 creates (each owned and filled by the named part)
- Backend: `app/core/quality/q1.py` … `q4.py` (empty enum modules); `app/models/quality/__init__.py` importing `q0.py` and the stub modules `q1.py` … `q4.py` (each with `__all__ = []`), so Alembic autogenerate sees the wave-2 tables once a part adds them; `app/schemas/quality/q1/` … `q4/` packages; `app/services/quality/q1/__init__.py` … `q4/__init__.py`, each with an empty `register()` that `app/services/quality/__init__.py` calls; `app/api/routers/quality/__init__.py` defining one `router` that includes `q0.router` and the empty `APIRouter`s of `q1/` … `q4/` (the only router module added to `main.py`); `app/seed_quality_q1.py` … `q4.py` with an empty `seed(db)`; `tests/quality/q1/` … `q4/` with an empty `conftest.py`.
- Frontend: `src/components/quality/nav/q1.ts` … `q4.ts` (empty arrays) and `nav/index.ts`; `src/components/quality/registry/tabs-q1.tsx` … `tabs-q4.tsx` (empty tab lists); `messages/quality/q0.en.json`, `q0.ar.json` … `q4.en.json`, `q4.ar.json` (`{}` for q1…q4); `src/lib/api/quality/q1.ts` … `q4.ts`.
- i18n wiring: today `src/i18n/request.ts` imports only `messages/{locale}.json` and `scripts/check-i18n.mjs` reads only `en.json` / `ar.json`. Q0 extends `request.ts` to deep-merge the five `messages/quality/q<n>.{locale}.json` files under the `quality` namespace (a key defined twice fails the build), and extends `check-i18n.mjs` to check EN / AR parity and empty values in those files too; Q0 adds a check (script test or CI step) that a key missing from `q1.ar.json` fails.

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
- **Q-PRF-04.** After a change, creating a record of a type that belongs only to the inactive profile, or of the construction-only Q0 register `q_systems`, gives 409 `PROFILE_INACTIVE`. Open records of that type may still be progressed to a final state (e.g. an open IR may be decided, an open hold released) so nothing is stranded; the screen shows "Other profile — finish only".
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
| `weld` | Weld Joint / وصلة لحام | Q2 | construction | (joint id) | `repair2_approve` (role quality_engineer) |
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
| `trip` | Transport Trip / رحلة نقل | Q3 | logistics | TRP | `dispatch_override` (position TRANSPORT_SUP) |
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
- **Q-RPM-07.** A contractor-assigned user (Q-ROL-02) cannot sign a step on a record whose responsible engagement is in their own tree unless the row has `own_tree_allowed` (contractor self-certification is a project decision, not a default). The record's responsible engagement is its `responsible_engagement_id` or `engagement_id` field where the type has one (NCR, observation, ITP, punch item, MAR, test request, quarantine via its MIR); the sys `engagement_id` columns are filled by this chain: IR → its ITP's engagement_id; pour → the ITP of its linked pre-pour IR; test request → its own engagement_id (defaulted from the linked pour or IR); MIR → the MAR's requesting engagement (`q_mars.engagement_id`, copied to `q_mirs`); weld → the engagement of its first root-pass welder (`q_welders.engagement`). Logistics records (receipt, hold, excursion, trip, recall) and records with no engagement → none, and this rule does not apply.
- **Q-RPM-08.** **External sign-off.** A person without an account is invited as a user with role `responsible_person` (Phase 0 invite flow, 72 h token, privacy notice) and added as position holder. Where the row has `paper_allowed`, a holder of the step's capability may instead record the decision **on behalf of** a named external signatory: name, organisation, position, signed date and ≥ 1 scanned signed form (PDF / image). The sign-off is stored with channel `paper` and shown "Signed on paper by <name> (<organisation>), recorded by <user>". Paper sign-offs are counted (K-141 chip, §E.4).
- **Q-RPM-09.** The HSE Manager and 239 holders may **re-assign** the responsible person of one pending step on one record (reason ≥ 20 chars, audited); they never sign in the resolved person's place unless they resolve themselves.
- **Q-RPM-10.** A matrix change applies to steps not yet signed; signed steps keep their sign-off. Open records whose resolved set becomes empty are listed on the Quality home ("steps without a responsible person").
- **Q-RPM-11.** "Awaiting my sign-off" lists every pending step where the current user resolves, across all parts (registry `PENDING_STEPS`), oldest first, with the record ref, step, waiting time and a link.

## A.5 Numbering (Q-NUM)

- **Q-NUM-01.** Each record type of list QRT has a format in `q_numbering` (editable by 239): tokens `{PFX}` (type prefix), `{PROJECT}` (project code), `{SITE}` (site code), `{DISC}` (discipline code where the type has one), `{YYYY}`, `{YY}`, `{SEQ3}`…`{SEQ6}` (zero-padded sequence), literal `-` `/` `_` and letters. Default `{PFX}-{PROJECT}-{YYYY}-{SEQ4}` (e.g. `NCR-ANIA-EXP-2026-0041`); high-volume types (IR, punch item, test request, receipt, FEFO check, trip, damage report) `{PFX}-{PROJECT}-{YYYY}-{SEQ5}`; ITP `{PFX}-{PROJECT}-{DISC}-{SEQ3}` and documents `{PROJECT}-QA-{PFX}-{SEQ3}` (reset `never`); M&TE `{PFX}-{SEQ4}` (reset `never`, unique per project); reset `yearly` (default) or `never`.
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
**Response owner types added:** `q_ir_round`, `q_punch_walkdown`, `q_mir`, `q_receipt`, `q_trip_preload`, `q_hygiene`, `q_pest_visit`, `q_return`. Quality audits keep the 6d owner type `audit` (they are `field_audits` rows, §E.2).

## A.8 Shared registers owned by Q0 (Q-SHR)

### A.8.1 Systems — الأنظمة
`q_systems`: code (`^[A-Z0-9-]{2,20}$`, unique per project), name EN / AR, discipline (list DSC, §B.1), parent system (≤ 3 levels), zone_ids, status active / archived. Used by Q1 (IRs, punch, dossiers) and Q2 (tests, welds). Profile: construction — creating or reactivating a system follows Q-PRF-04 (`PROFILE_INACTIVE`); existing systems stay readable.

### A.8.2 Supplier master — سجل الموردين
Org-wide, like contractors (Phase 0 §3.4). `q_suppliers`: supplier_code (`^[A-Z0-9-]{2,12}$`, unique), legal_name_en / _ar (unique, normalised as Phase 0 rule 45), cr_number (optional; same validation as contractors), vat_number (optional), country, categories (list SC, ≥ 1), contractor_id (optional link when the supplier is also a contractor), scope_en / _ar (what they supply), contact name / mobile / email (personal), status (list SS), status_reason, approved_scope (text), next_evaluation_due (sys, Q4), `tpi_id` (optional link to a Phase 4 TPI, for calibration and NDT bodies). `q_supplier_accreditations`: body (`sac` · `ilac_mra_other` · `other`), standard (`iso_iec_17025` · `iso_iec_17020` · `iso_9001` · `iso_22000` · `other`), number, scope (text and test-type codes), valid_from, valid_until, certificate file.

**SC — supplier categories:** `material_supplier` مورد مواد · `manufacturer` مصنّع · `subcontractor` مقاول باطن · `testing_lab` مختبر اختبارات · `calibration_lab` مختبر معايرة · `ndt_provider` مزود فحص غير إتلافي · `carrier` ناقل · `pest_control` مكافحة آفات · `cleaning` تنظيف · `packaging` تغليف · `shipper` شاحن / مورد البضاعة · `service` خدمات · `other` أخرى.
**SS — supplier status:** `draft` مسودة → `pending_approval` بانتظار الاعتماد → `approved` معتمد · `conditional` معتمد بشروط · `suspended` موقوف · `disqualified` مستبعد.

- **Q-SHR-01.** Transitions: draft → pending_approval (278); pending_approval → approved / conditional / back to draft (279 + RPM `supplier.approve`; registry `SUPPLIER_GATES` may add blockers, Q4 adds "an approved evaluation is required"); approved ↔ conditional, approved / conditional → suspended (279 + RPM `supplier.suspend`, reason); suspended → approved / conditional (reason); any → disqualified (279, reason; terminal except "lift" → suspended).
- **Q-SHR-02.** Records that name a supplier (MAR, receipt, test request, calibration, trip, NCR) warn `SUPPLIER_NOT_APPROVED` when the supplier is not approved / conditional on the record date, and refuse a `disqualified` supplier (`SUPPLIER_DISQUALIFIED`). A conditional supplier shows its condition text.
- **Q-SHR-03.** A testing or calibration lab used for a test type or M&TE type outside its accreditation scope, or with no accreditation valid on the test or calibration date, gives warning `LAB_NOT_ACCREDITED_FOR_SCOPE` (not a block: unaccredited labs exist, and the decision is recorded) ASSUMPTION.

### A.8.3 Customers — العملاء
`q_customers` (per project): code, name EN / AR, kind (`client` العميل · `depositor` مالك البضاعة · `consignee` المستلم · `end_user` المستخدم النهائي), contact name / mobile / email (personal), approval-required flags (`owner_release_approval` for depositors, Q-EXC-09), status active / inactive.

### A.8.4 M&TE master — سجل أجهزة القياس والاختبار
Q0 owns the table, its CRUD endpoints (`/projects/{id}/quality/mte`, `/quality/mte/{id}`), the `/quality/mte` register screens and usage recording, so Q2 and Q3 can create and cite instruments in parallel (Q3 needs its loggers). Until Q2 is installed `cal_status` stays `unknown`. Q2 owns calibration records, OOT reviews, the status recomputation (Q-CAL-02), the status label print (Q-CAL-05) and the `calibration/` route, and adds its M&TE tabs through `tabs-q2.tsx` (§C.4). `q_mte_items`: mte_no (numbering `MTE`), type (list MT, §C.4), description, manufacturer, model, serial_no (unique with manufacturer per project), range, resolution, tolerance (± value and unit), owner (`own` · engagement · supplier), site / zone, custodian user, `check_kind` (`calibration` · `verification` · `none`), interval_months, `cal_status` (sys, list CS §C.4), `cal_due_on` (sys), `last_calibration_id` (sys), `equipment_item_id` (optional Phase 4 link), status `active` · `retired` · `lost`, label printed at.

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
| source_type / source_id / source_ref | المصدر | enum / UUID / string | Y / cond. / sys | list NS; id required except `manual`; ref copied (Q-NCR-02) | test_result / … / TST-ANIA-EXP-2026-00388 | none |
| site_id / zone_id / system_id / location_ref | الموقع / المنطقة / النظام / الموقع التفصيلي | FK / FK / FK / string(120) | Y / N / N / N | from the source when it has them | S-LAND / Z-PIERB / — / Level 3 slab, grid C14–C20 | none |
| title | العنوان | string(150) | Y | — | 28-day cylinder strength below acceptance, pour POUR-ANIA-EXP-2026-0077 | none |
| requirement_en / _ar | المتطلب | text(1000) | Y (one language) | what was required: criterion, spec clause, drawing | f'c 40 MPa; ACI 318 §26.12.3.1 `[VERIFY]` | none |
| finding_en / _ar | الوضع الفعلي | text(2000) | Y (one language) | what was found; hint "no names or ID numbers" (P1-8 scan) | Set 3 average 33.2 MPa < 36.0 MPa | none |
| category | فئة العيب | enum | Y | list NCAT | material | none |
| detection_stage | مرحلة الاكتشاف | enum | Y | list DS; default from the source | in_process | none |
| classification | التصنيف | enum | Y at Open | list NC; Q-NCR-04/05 | critical | none |
| responsible_engagement_id | الجهة المسؤولة | FK | Y | engagement on the project; default from the source | RAWABI@ANIA-EXP | none |
| supplier_id / customer_id | المورد / العميل | FK / FK | N / N | Q-SHR-02 | Riyadh Readymix | none |
| item_key | مفتاح البند | string(80) | sys | from the source adapter (e.g. `ITP:STC-001:30`, `TT:CONC-CYL`, `SKU:NDC-1001`) | TT:CONC-CYL | none |
| quantity / unit / lot_refs | الكمية / الوحدة / الدفعات | decimal / string(10) / string[] | N | lots, heats, batches, serials (≤ 50) | 186 / m3 / [mix C40-B12] | none |
| raised_by / opened_at | أعدّه / تاريخ الفتح | FK / timestamptz | sys | — | Bilal / 2026-09-29 11:20 | personal |
| owner_id | مسؤول المعالجة | FK | Y at Open | user on the project holding 242 | Bilal | personal |
| containment_en / _ar, containment_done_at, containment_by | الاحتواء | text(1000) / timestamptz / FK | cond. | Q-NCR-07 | Slab load restricted, props kept, cores ordered | personal (by) |
| cause_category | فئة السبب الجذري | enum | cond. | list 6M; required to leave Open | material | none |
| rca_id | تحليل السبب | FK | cond. | Q-NCR-09 | — | none |
| disposition_lines | المعالجة | list {disposition, quantity, note} | cond. | list DP; Q-NCR-11 | [{use_as_is, 186 m3}] | none |
| disposition_justification_en / _ar | مبرر المعالجة | text(2000) | cond. | ≥ 50 chars for use_as_is / repair | Cores avg 34.9 MPa ≥ 0.85 f'c (34.0), min 33.6 ≥ 0.75 f'c… | none |
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
- **Q-NCR-12.** **Approval** of the disposition is one sign-off per required step: `ncr.disposition` always; plus `ncr.concession` when any line is use_as_is or repair; `ncr.disposition` and `ncr.concession` are two sign-off rows even when the same user resolves for both; the UI offers them together. Q-RPM-06 applies: the owner and the raiser cannot approve.
- **Q-NCR-13.** **Supplier response (SCAR):** when supplier_id is set, the owner may request a supplier response (due date, default +14 days); the received response (file, e.g. the supplier's 8D) is accepted or rejected by the owner. A missing or late response feeds the supplier score (§E.3), never blocks closure on its own.
- **Q-NCR-14.** **Costs** are entered at any time before closure (§A.9.6). Closure needs ≥ 1 cost line or the confirmation "no cost incurred" with a reason (`COST_NOT_RECORDED`).
- **Q-NCR-15.** **Close** needs: disposition implemented; every linked CA Closed or Cancelled (cancelled with reason); every `reject_return` / `reject_scrap` line evidenced; costs recorded (Q-NCR-14); and no blocker from the source adapter's `close_check` (e.g. a rework IR not yet approved, a hold not released or rejected). The verifier is the user who resolves for `ncr.close`; Q-RPM-06 applies.
- **Q-NCR-16.** **Repeat NCR:** on Open, an NCR is a repeat when a not-voided NCR with the same `category`, the same responsible party (supplier when set, else responsible engagement) and the same `item_key` was opened within the previous `ncr_repeat_days`. A repeat sets `repeat_of`, raises minor to major (Q-NCR-05 raise), and requires RCA method `five_why`, `ishikawa` or `eight_d`.
- **Q-NCR-17.** **Effectiveness:** at closure, `effectiveness.due_on` = closed_date + `ncr_effectiveness_days`. On the due date the job proposes "effective" when no repeat (Q-NCR-16 key) was opened since closure, else "not effective"; a 242 holder confirms. "Not effective" offers a new linked NCR (source `manual`, link `relates`). The closed NCR stays closed.
- **Q-NCR-18.** Ageing and timing: age_days = local today − local date(opened_at) for NCRs not Closed or Voided; closure_days = closed_date − local date(opened_at); on-time ⇔ closed_date ≤ target_close_date. A reopened NCR keeps its opened_at and target date; its closure_days use the final closure. **Worked example QX3:** opened 2026-08-10, still open on 2026-10-06 → age **57** days (bucket 31–60); a major NCR opened 2026-08-10 (target 2026-09-09) and closed 2026-09-15 → closure_days **36**, not on time.
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
`q_observations`: obs_no, site / zone / system / location_ref, category (NCAT), description (P1-8 scan), photos, suggested action, raised_by, status `open` مفتوحة → `actioned` تم اتخاذ إجراء (CA source `quality_observation`, or escalated to an NCR source `observation`) · `closed` مغلقة (RPM `observation.close`, reason). Quality observations are kept apart from Phase 1 observations (`observations`), which are safety observations feeding the HSE leading indicators and HSE CAs; a quality observation never enters HSE KPIs (Q-OBS-02).
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
| 259 | Welding records (WPS / PQR drafts, welders, WPQs, weld log, NDT; RPM for R2 repair approval) | P | P | P | — | — | A | — | — | — | — |
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

Fixtures: the Phase 0–7b seed plus Appendix A; clock `HSE_CLOCK_AT` = **2026-10-06 10:00** (+03:00) via the `clock` fixture; users as Appendix A.1 (Hatem QA/QC Manager ANIA-EXP; Bilal Quality Engineer RAWABI-assigned; Joseph QC Inspector RAWABI; Abdullah responsible person, position CONSULTANT_RE; Sultan responsible person, position CLIENT_REP; Reem QA/QC Manager RUH-CCH; Imran Warehouse QC; Saad responsible person, position WAREHOUSE_MGR; Lama responsible person, RESP_PHARMACIST; Rania Quality Engineer ANIA-EXP, PMC; Mazen QC Inspector ANIA-EXP, PMC; Arun QC Inspector NAJD; Naveen Warehouse QC, position TRANSPORT_SUP).

**Roles, profile, settings**
1. **AC-Q0-01** (Q-ROL-02) **Given** Bilal holds quality_engineer on ANIA-EXP with engagement RAWABI **When** he lists NCRs **Then** only NCRs whose responsible engagement is RAWABI, NAJD, GULFPAVE or SAHARA are returned; an NCR of a QIMMA engagement on RBT-52 by id → 404 and `access_denied` logged.
2. **AC-Q0-02** (Q-ROL-03) **Given** Bilal **When** he PATCHes Quality settings or voids an NCR **Then** 403.
3. **AC-Q0-03** (Q-ROL-04) **Given** Abdullah (responsible_person) **When** he lists NCRs **Then** he sees only NCRs with a step where he resolves or has signed; `GET /quality/kpis` → 403.
4. **AC-Q0-04** (Q-PRF-01) **Given** a new project with no profile **When** a user raises an NCR **Then** 422 `PROFILE_REQUIRED`; after Hatem sets `construction` it succeeds.
5. **AC-Q0-05** (Q-PRF-03, Q-PRF-04) **Given** ANIA-EXP switched to `logistics` with reason **Then** the change is audited with old / new; creating a system (a construction-only Q0 register) → 409 `PROFILE_INACTIVE`; creating an NCR (shared type) still works; the NCR register still lists construction NCRs. Creating and finishing IRs after a switch is integration test §6 #10.
6. **AC-Q0-06** (Q-PRF-06) **Given** a project created with type `logistics` **Then** its Quality profile defaults to logistics; a `building_highrise` project defaults to construction.
7. **AC-Q0-07** (Q-SET-01) **Given** `GET /quality/settings/schema` **Then** every key of §A.3 and of §B.2, §C.1, §D.1, §E.1 is listed with default and range; PATCH `ncr_repeat_days` = 20 → 422 `SETTING_OUT_OF_RANGE`; 120 → saved and audited.

**Responsible-person matrix and sign-offs**
8. **AC-Q0-08** (Q-RPM-03) **Given** the default row `ir.inspect` H → position CONSULTANT_RE held by Abdullah **Then** Abdullah resolves for a hold-point IR and Hatem does not.
9. **AC-Q0-09** (Q-RPM-02) **Given** no active row for `ncr.close` **When** the owner asks to close **Then** 422 `RESPONSIBLE_PERSON_NOT_SET` and the NCR is listed under "steps without a responsible person".
10. **AC-Q0-10** (Q-RPM-06) **Given** Hatem raised an NCR and also resolves for `ncr.disposition` **When** he approves the disposition **Then** 422 `SOD_CONFLICT`; with `self_approval_allowed` true on that row **Then** allowed.
11. **AC-Q0-11** (Q-RPM-07) **Given** a matrix row naming role quality_engineer for `ncr.close` and Bilal (RAWABI-assigned) **When** he closes a RAWABI NCR **Then** 422 `SOD_CONFLICT`; for a GULFPAVE NCR with `own_tree_allowed` false **Then** still refused (GULFPAVE is in RAWABI's tree); for an NCR whose responsible engagement is outside his tree **Then** 404.
12. **AC-Q0-12** (Q-RPM-01) **Given** the `ncr.disposition` row changed from role qa_qc_manager to user Sultan **Then** Sultan resolves and Hatem no longer does, without a code change.
13. **AC-Q0-13** (Q-RPM-08) **Given** a row with `paper_allowed` **When** Hatem records an external approval without a scan **Then** 422; with name, organisation, position, date and a PDF **Then** a sign-off with channel `paper` is stored and printed "Signed on paper by …, recorded by Hatem"; with `paper_allowed` false **Then** 422.
14. **AC-Q0-14** (Q-RPM-09) **Given** Faisal (HSE Manager) who does not resolve **When** he approves a step **Then** 403; when he re-assigns the step to Sultan with a reason **Then** Sultan resolves for that record only and an audit entry exists.
15. **AC-Q0-15** (Q-RPM-05) **Given** any sign-off **When** an UPDATE or DELETE is attempted through the API **Then** 405 / no route exists; the row is shown on the record with role or position at signing.
16. **AC-Q0-16** (Q-RPM-11) **Given** Abdullah resolves for 3 pending NCR steps (two `ncr.concession`, one `ncr.disposition` re-assigned to him by Q-RPM-09) **Then** "Awaiting my sign-off" lists the 3, oldest first, with the badge 3; a test-only `PENDING_STEPS` provider registered in `tests/quality/q0/` adds a fourth item and the list merges it in date order.

**Numbering, criteria, checklists, shared registers**
17. **AC-Q0-17** (Q-NUM-03) **Given** two NCRs opened concurrently on ANIA-EXP **Then** they get consecutive, different numbers; a voided NCR's number is never reused.
18. **AC-Q0-18** (Q-NUM-02, Q-NUM-04) **Given** a format `{PFX}-{PROJECT}` **Then** 422 `NUMBER_FORMAT_INVALID`; changing NCR format to `{PFX}/{PROJECT}/{YY}/{SEQ5}` leaves existing numbers unchanged and the next NCR is `NCR/ANIA-EXP/26/00045`.
19. **AC-Q0-19** (Q-CRT-01) **Given** criterion `COMP-95` (kind min, 95.0 %) **Then** 96.2 → pass, 95.0 → pass, 94.4 → fail; criterion kind target_tolerance 100 ± 25 mm: 75 and 125 pass, 130 fails.
20. **AC-Q0-20** (Q-CRT-02) **Given** a record pinned to COMP-95 v1 **When** v2 (98.0 %) is published **Then** the record's verdict is unchanged.
21. **AC-Q0-21** (Q-CHK-01, Q-CHK-02) **Given** a quality template draft with a `stop_work` item **Then** publish → 422 `STOP_RULE_NOT_ALLOWED`; Noura (HSE Officer, holds 6d capability 192 but not 240) creating a kind `quality` draft → 403; Faisal publishing a clean draft → Published.
22. **AC-Q0-22** (Q-CHK-03) **Given** quality checklist responses in September **Then** K-34, K-35 and K-110 for September are unchanged.
23. **AC-Q0-23** (Q-SHR-02) **Given** supplier GULFPIPE suspended **When** an NCR sets supplier_id = GULFPIPE **Then** warning `SUPPLIER_NOT_APPROVED`; a disqualified supplier → 422 `SUPPLIER_DISQUALIFIED`.
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
38. **AC-Q0-38** (Q-NCR-16) **Given** NCR A (material, Riyadh Readymix, `TT:CONC-CYL`) opened 2026-07-02 **When** NCR B with the same key opens 2026-09-29 (89 days) **Then** B is a repeat, raised to major and RCA `simple` refused; opened on 2026-10-01 (91 days) **Then** not a repeat.
39. **AC-Q0-39** (Q-NCR-17) **Given** an NCR closed 2026-07-01 and no repeat since **Then** on 2026-09-29 the job proposes "effective"; with a repeat on 2026-08-15 **Then** "not effective" is proposed.
40. **AC-Q0-40** (Q-NCR-18) **Given** an NCR opened 2026-08-10 and still open at the clock **Then** age 57 days; closed 2026-09-15 with target 2026-09-09 **Then** closure_days 36, not on time.
41. **AC-Q0-41** (Q-NCR-19) **Given** an NCR **When** the PDF is generated in AR **Then** it is RTL, shows the Hijri date of issue (from `app.core.hijri`), sign-offs and cost totals; for a user without 242 rates are absent.

**Observations, alerts, complaints, navigation, licence, PDPL**
42. **AC-Q0-42** (Q-OBS-01) **Given** an observation converted to an NCR **Then** the NCR has source `observation`, a `raised_from` link, and the observation is `actioned`.
43. **AC-Q0-43** (Q-OBS-03, Q-OBS-04) **Given** a stop_use alert with ack_required to role qc_inspector on S-LAND **Then** Joseph sees the banner and acknowledges once; a second ack is idempotent; non-ackers get one reminder on day 3.
44. **AC-Q0-44** (Q-CMP) **Given** a complaint marked justified without an NCR **When** responded **Then** 422 `NCR_REQUIRED_FOR_JUSTIFIED`; acknowledgement 25 h after receipt with `complaint_ack_hours` 24 **Then** the overdue alert was sent at 24 h.
45. **AC-Q0-45** (Q-NAV-01) **Given** RUH-CCH (logistics) **Then** the Quality group hides construction-only items (in Q0 alone: Systems; once Q1 / Q2 register theirs: ITP, IR, MAR, welding) and ANIA-EXP hides logistics-only items (registered by Q3); both show NCRs, suppliers and complaints.
46. **AC-Q0-46** (D-290, D-319) **Given** the licence is read-only **Then** every Quality POST / PATCH / PUT → 403 `LICENCE_READ_ONLY`, while `GET` registers, NCR PDFs and `POST /exports` of Quality datasets work.
47. **AC-Q0-47** (P8-2, P8-4) **Given** Sarah (Viewer) **Then** Quality registers show no person names, no photos, no costs and no supplier contacts; an export with names by Hatem writes an `export` audit row.
48. **AC-Q0-48** (rule 41) **Given** the UI in Arabic **Then** every Q0 label, status, list value, error, email and PDF has AR text; numbers, codes and dates stay LTR inside RTL; the i18n check covers `messages/quality/*.json`.
49. **AC-Q0-49** (§A.8.4, capability 261) **Given** Q0 alone **When** Imran (warehouse_qc, 261) creates logger MTE-0101 on RUH-CCH **Then** it is stored with `cal_status` `unknown` and recording a usage with it warns `MTE_NOT_CALIBRATED`; Sarah (Viewer, no 261) creating an M&TE item **Then** 403; a duplicate manufacturer + serial on the same project **Then** 422.

---

# Part B — Q1: construction — ITP, inspection requests, punch lists, handover dossier

Profile: construction. Every write in this part needs the project profile `construction` (Q-PRF-04 for leftovers).

## B.1 Lists

**DSC — disciplines** (code used in `{DISC}`): `CIV` civil works أعمال مدنية · `STC` structural concrete خرسانة إنشائية · `STL` structural steel حديد إنشائي · `ARC` architectural معماري · `HVC` HVAC تكييف وتهوية · `PLB` plumbing and drainage سباكة وصرف · `FPS` fire protection حماية من الحريق · `ELE` electrical كهرباء · `ELV` low current / ELV تيار منخفض · `RDS` roads and infrastructure طرق وبنية تحتية · `AFP` airfield pavement رصف المطارات · `GEO` geotechnical and earthworks أعمال ترابية وجيوتقنية · `LSC` landscape تنسيق الموقع · `OTH` other أخرى. Labels editable; codes fixed.

**PT — ITP point types:** `H` Hold point نقطة توقف (work may not proceed past it until the responsible person approves) · `W` Witness point نقطة شهادة (the responsible person is notified and may attend; work may proceed after the notice if they do not, Q-IR-10) · `R` Review point نقطة مراجعة (records reviewed, no attendance) · `S` Surveillance نقطة مراقبة (random or periodic check without notice). Strictness order H > W > R > S.

## B.2 Q1 settings (registry keys)

| Key | AR label | Type | Default | Allowed |
|---|---|---|---|---|
| `ir_notice_hours` | مهلة الإشعار المسبق | {H, W} hours | 24 / 24 ASSUMPTION | 0–168 |
| `ir_schedule_hours` | مهلة الجدولة | hours | 24 | 2–168 |
| `witness_wait_minutes` | مدة انتظار الشاهد | minutes | 60 | 15–480 |
| `witness_review_days` | مهلة مراجعة نقطة الشهادة المتنازل عنها | days | 3 | 1–14 |
| `ir_max_points` | الحد الأقصى للنقاط في الطلب | int | 5 | 1–10 |
| `ir_comment_close_days` | مهلة إغلاق ملاحظات الاعتماد | days | 14 | 1–60 |
| `punch_target_days` | مهلة إغلاق النواقص | {A, B} days | 14 / 30 | 1–180 |
| `dossier_blockers` | شروط اكتمال الملف | set | all of Q-DOS-03 (a)–(f) | subset; a removed blocker becomes a warning |

## B.3 Inspection and Test Plan (ITP) — خطة الفحص والاختبار

### B.3.1 Entities
`q_itps`:

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| itp_no / revision | رقم الخطة / المراجعة | string / int | sys | Q-NUM (`{DISC}`); revision 0, 1, 2 … | ITP-ANIA-EXP-STC-001 Rev.2 | none |
| title_en / _ar | العنوان | string(150) ×2 | Y | both required to submit | Cast-in-situ concrete, Pier B / الخرسانة المصبوبة في الموقع، الرصيف B | none |
| discipline | التخصص | enum | Y | list DSC | STC | none |
| work_package_en / _ar | حزمة العمل / النشاط | string(150) | Y (one language) | — | Pier B superstructure | none |
| engagement_id | المقاول المنفذ | FK | Y | engagement on the project | RAWABI@ANIA-EXP | none |
| zone_ids / system_ids | المناطق / الأنظمة | FK[] | N | empty = whole project | [Z-PIERB] | none |
| spec_refs / code_refs | مراجع المواصفات / الكود | string(120)[] ×2 | N | ≤ 20 each | [03 30 00 Cast-in-place concrete] / [SBC 304] | none |
| method_statement_ref | بيان طريقة العمل | link | N | Q4 document via `q_links` (`requires`) or text | MS-ANIA-EXP-STC-004 | none |
| points | النقاط | list §B.3.2 | Y | ≥ 1 point; ≥ 1 H or W | 9 points | none |
| change_note | ملاحظة التغيير | text(500) | cond. | required for revision ≥ 1 | Point 50 adds concrete temperature ≤ 32 °C | none |
| approval_code | رمز الاعتماد | enum | sys | `A` approved · `B` approved as noted · `C` revise and resubmit · `D` rejected | B | none |
| prepared_by / submitted_at | أعدّها / تاريخ التقديم | FK / timestamptz | sys | 247 holder | Bilal | personal |
| status | الحالة | enum | Y | §B.3.3 | approved | none |

`q_itp_points` (one row per point and revision): seq (10, 20, … unique in the revision), activity_en / _ar, characteristic_en / _ar (what is checked), point_type (list PT), criteria (criteria library version ids, ≥ 0) and/or acceptance_text_en / _ar, reference (spec clause or drawing, ≤ 120), verifying_record (`ir` · `test_request` · `mir` · `document` · `none`), checklist_template_code (quality kind, `quality_type` `ir_inspection`, optional), test_type_codes (codes of Q2 test types as text; validated only when Q2 is installed), frequency_text (e.g. "each pour", "every 500 m²") and frequency_qty / unit (optional), performer (fixed: contractor QC), rp_override (optional assignee spec, Q-RPM-02), notice_hours override (optional), competence_code (optional, Q2 requirement code).

### B.3.2 Example points (ITP-ANIA-EXP-STC-001 Rev.2, seed)
| Seq | Activity | Type | Criteria / acceptance | Verifying record |
|---|---|---|---|---|
| 10 | Approved mix design and materials | R | MAR approved (A or B) | document / MAR |
| 20 | Formwork, line and level | W | ± 5 mm in 3 m (criterion `FORM-TOL`) | IR (checklist QSTC-FW) |
| 30 | Reinforcement before pour (size, spacing, cover, laps) | **H** | Cover 40 ± 5 mm (`COVER-40`), spacers, laps per drawing | IR (checklist QSTC-RB) |
| 40 | Embedded items and MEP sleeves | W | as drawings | IR |
| 50 | Pour: slump, concrete temperature, sampling | W | `SLUMP-100`, `CONC-TEMP-32`, sampling per pour | IR + test requests |
| 60 | Curing for 7 days | S | wet curing, `CURE-7D` | IR |
| 70 | Striking of formwork | H | ≥ 70 % f'c by cubes or 7 days (`STRIKE-70`) | IR + test |
| 80 | 28-day strength | R | `CONC-ACI-40` | test request |
| 90 | Surface finish and dimensions | W | as specification | IR |

### B.3.3 ITP states
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Draft | مسودة | 247 | new ITP, or new revision copied from the current Approved revision |
| Draft → Submitted | مُقدَّمة | 247 | Q-ITP-02 |
| Submitted → Approved | معتمدة | 248 + RPM `itp.approve` | code A or B (B needs a comment); the previous Approved revision → Superseded |
| Submitted → Revise and Resubmit | تعاد للتعديل | 248 + RPM | code C, comment ≥ 20 chars; the author edits and resubmits the same revision |
| Revise and Resubmit → Submitted | مُقدَّمة | 247 | Q-ITP-02 again |
| Submitted → Rejected | مرفوضة | 248 + RPM | code D, comment ≥ 20 chars; terminal for that revision |
| Approved → Superseded | مستبدلة | System | a later revision is approved |
| Approved → Withdrawn | مسحوبة | 239 | reason ≥ 20 chars; no new IRs |

### B.3.4 Rules (Q-ITP)
- **Q-ITP-01.** An ITP belongs to one engagement and one discipline; several ITPs may cover one zone.
- **Q-ITP-02.** Submit completeness (`ITP_INCOMPLETE`): title EN and AR; ≥ 1 point; every point has activity, characteristic, type, and either ≥ 1 criterion or acceptance text; ≥ 1 point of type H or W; seq values unique.
- **Q-ITP-03.** An Approved revision is immutable (`ITP_IMMUTABLE`, 409); changes make a new revision with a change note.
- **Q-ITP-04.** IRs pin the ITP revision current at submission. An IR open on a revision that becomes Superseded continues on its revision; new IRs must use the current Approved revision (`ITP_NOT_APPROVED`).
- **Q-ITP-05.** Point identity across revisions is its seq. Q-IR-08 hold checks match by seq and treat a hold point approved on an earlier revision as released when the point's seq and type are unchanged in the later revision.
- **Q-ITP-06.** The ITP page shows a coverage grid: points × location keys used by its IRs, with the latest IR status in each cell (approved, approved with comments, rejected, scheduled, waived, not started).

## B.4 Inspection Request (IR) — طلب فحص

### B.4.1 Entities
`q_irs`:

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| ir_no | رقم الطلب | string | sys | Q-NUM at submit | IR-ANIA-EXP-2026-00412 | none |
| itp_id + revision / point_seqs | الخطة / النقاط | FK / int[] | Y | current Approved revision; 1…`ir_max_points` points of that ITP | ITP-…-STC-001 Rev.2 / [30] | none |
| engagement_id | المقاول | FK | sys | the ITP's engagement_id (Q-RPM-07) | RAWABI@ANIA-EXP | none |
| governing_type | نوع النقطة الحاكم | enum | sys | strictest type of the points | H | none |
| site_id / zone_id / system_id | الموقع / المنطقة / النظام | FK | Y / N / N | inside the ITP's zones / systems when set | S-LAND / Z-PIERB | none |
| location_ref / location_key | الموقع التفصيلي / مفتاح الموقع | string(120) / sys | Y / sys | key = zone code (or system code) + "\|" + lower-cased, trimmed, single-spaced location_ref | Level 3 slab, grid C14–C20 / `Z-PIERB\|level 3 slab, grid c14–c20` | none |
| extent | النطاق | string(150) | N | quantity description | 420 m², 62 t rebar | none |
| requested_by / submitted_at | مقدم الطلب | FK / timestamptz | sys | 249 holder | Joseph | personal |
| proposed_at | الموعد المقترح | timestamptz | Y | Q-IR-03 | 2026-09-14 08:00 | none |
| self_check_done / self_check_note | الفحص الذاتي للمقاول | bool / text(500) | Y / N | must be true to submit (Q-IR-04) | true | none |
| attachments | المرفقات | files | N | shop drawings, contractor checklist, survey | — | none |
| responsible_set | الأشخاص المسؤولون | sys | sys | resolved at submit (Q-RPM-02; point rp_override) | [Abdullah] | personal |
| current_round | الجولة الحالية | int | sys | 1, 2, … | 2 | none |
| short_notice / short_notice_reason | إشعار قصير | bool / text | sys / cond. | Q-IR-03 | false | none |
| status / status_reason | الحالة | enum / text | Y | §B.4.2 | approved | none |

`q_ir_rounds`: round_no, scheduled_at, scheduled_by, inspector_id (must resolve for `ir.inspect`), attended_at, inspected_at, client_uuid, response_id (6d checklist response, owner type `q_ir_round`), measurements (list {name, value, unit, criterion version, mte_id, verdict}; each M&TE use → `q_mte_usage`), photos (≤ 20), result (list IRR), reject_category (NCAT, required when rejected), ncr_ids (sys), signoff_id (sys), waived_by / waived_at / waiver_evidence (W only), close_comments_before_next_hold (bool).
`q_ir_comments`: ir, round, text EN / AR, status `open` مفتوحة → `responded` تم الرد (249, response text, photo) → `closed` مغلقة (250 + RPM) or back to `open`; due_on = round date + `ir_comment_close_days`.

**IRR — round results:** `approved` معتمد · `approved_with_comments` معتمد مع ملاحظات · `rejected` مرفوض · `not_ready` غير جاهز (works not ready on arrival; a failed round, no NCR) · `waived` تم التنازل عن الحضور (W only, Q-IR-10).

### B.4.2 IR states
| From → To | AR | Who | Trigger / condition |
|---|---|---|---|
| — → Draft | مسودة | 249 | — |
| Draft → Submitted | مُقدَّم | 249 | Q-IR-02 … Q-IR-04, Q-IR-08; number assigned; responsible set resolved and notified |
| Submitted → Draft | مسودة | 250 + RPM `ir.inspect` | returned (documents missing), comment ≥ 20 chars |
| Submitted → Scheduled | مجدول | 250 + RPM | scheduled_at, inspector (a resolver); expected within `ir_schedule_hours` (else alert) |
| Scheduled → Scheduled | — | 250 + RPM | re-schedule with reason (counted, shown) |
| Scheduled → Approved / Approved with Comments / Rejected | معتمد / معتمد مع ملاحظات / مرفوض | 250 + RPM (the inspector) | round result recorded (Q-IR-05, Q-IR-06); sign-off written; `not_ready` also leads to Rejected |
| Scheduled → Witness Waived | تم التنازل عن الشهادة | 249 | governing type W; inspector absent at scheduled_at + `witness_wait_minutes` (Q-IR-10) |
| Witness Waived → Approved / Approved with Comments / Rejected | — | 250 + RPM | records reviewed within `witness_review_days` |
| Rejected → Re-inspection Requested | إعادة فحص مطلوبة | 249 | correction done (note ≥ 20 chars, photo); a new round is created |
| Re-inspection Requested → Scheduled | مجدول | 250 + RPM | as above |
| Draft / Submitted / Scheduled / Rejected → Cancelled | ملغى | 249 (own) or 250 | reason ≥ 20 chars (e.g. works removed, superseded by another IR) |
| Approved / Approved with Comments → Voided | باطل | 244 | reason ≥ 20 chars; leaves KPIs; the hold it released is no longer released (Q-IR-08) |

### B.4.3 Rules (Q-IR)
- **Q-IR-01.** IRs are raised by 249 holders for points of an Approved ITP of an engagement in their scope; a contractor-assigned user raises IRs only for their engagement tree.
- **Q-IR-02.** All points of one IR belong to the same ITP revision and location; the governing type is the strictest of them.
- **Q-IR-03.** **Notice:** for governing type H or W, proposed_at ≥ submitted_at + notice hours (point override, else `ir_notice_hours`) (`IR_NOTICE_TOO_SHORT`); R and S need no notice. An urgent IR may be submitted with less notice with a reason ≥ 20 chars; it is flagged "short notice" and counted (K-141 chip).
- **Q-IR-04.** **Contractor self-check:** `self_check_done` must be true (`SELF_CHECK_REQUIRED`). The contractor may fill the point's checklist as a pre-inspection (round 0); round 0 is never scored in KPIs.
- **Q-IR-05.** **Decision:** a round needs the point's checklist response when the point has a template (6d EXE-2 completeness), every criterion-linked measurement entered, and ≥ 1 photo for `rejected`. A checklist critical failure or a failed criterion makes `approved` / `approved_with_comments` impossible (`IR_RESULT_INCONSISTENT`). `approved_with_comments` needs ≥ 1 comment.
- **Q-IR-06.** **Rejection outcome:** a `rejected` round offers "Raise NCR" (source `ir`, class minor proposed, category from reject_category) and "Request re-inspection". An NCR is required (`NCR_REQUIRED`) when the same IR is rejected in round ≥ 2 or the reject category is `material` or `testing_failure`. `not_ready` never raises an NCR.
- **Q-IR-07.** **Competence:** when a point has a `competence_code`, scheduling and deciding check the inspector through registry `COMPETENCE` (warn or block per `competence_policy`; `COMPETENCE_NOT_MET`). Without Q2 the check returns "not configured" and passes with an info note.
- **Q-IR-08.** **Hold points block the next step.** For an IR whose points include seq s on ITP I at location key L: every point of I with type H and seq < s must have an IR at L in state Approved or Approved with Comments (not voided) before this IR can be submitted (`HOLD_POINT_NOT_RELEASED`, listing the holds). Q1 registers `HOLD_CHECKS["itp_point"]` with the same logic for other parts (Q2 pours, Q-TST-12). Voiding the releasing IR re-blocks later IRs that are not yet decided and notifies their requesters.
- **Q-IR-09.** Hold points are never waived: an IR with governing type H cannot enter Witness Waived (`HOLD_NOT_WAIVABLE`).
- **Q-IR-10.** **Witness waived:** for governing type W, if no inspector has recorded attendance by scheduled_at + `witness_wait_minutes` (`WITNESS_WAIT_NOT_OVER` before that), the requester may record "witness waived" with their own checklist response and ≥ 1 photo; the work may proceed. The responsible person reviews within `witness_review_days` (overdue alert); a rejection after a waiver proposes an NCR. Waived rounds are not first-time passes (K-141) and are counted in their own chip.
- **Q-IR-11.** **Approved with comments:** open comments do not block later points unless the inspector ticks "close comments before the next hold point" on the round; then Q-IR-08 also requires those comments closed. Open comments block dossier completion (Q-DOS-03).
- **Q-IR-12.** **First-time pass** (K-141): the IR's round 1 result is `approved` or `approved_with_comments`. An IR cancelled without a decided round is excluded; an IR whose round 1 is `waived` is excluded from K-141 and counted in the waiver chip.
- **Q-IR-13.** **Forms:** the IR PDF (EN / AR, Hijri date, project and contractor, ITP point, location, rounds, checklist answers, measurements with M&TE numbers and calibration due dates, sign-offs including paper sign-offs) uses the 6g renderer.
- **Q-IR-14.** **Offline:** a round may be recorded on the phone without signal under 6d EXE-6 rules (client_uuid, `OFFLINE_SUBMIT_TOO_LATE`, `CLOCK_SKEW`). Hold-point and M&TE checks run again at sync; a conflict (e.g. the releasing IR was voided meanwhile) stores the round as "needs confirmation", shows it to the inspector and does not count it as decided until confirmed.

## B.5 Punch list — قائمة النواقص

`q_punch_items`:

| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| punch_no | رقم البند | string | sys | Q-NUM | PCH-ANIA-EXP-2026-00318 | none |
| site_id / zone_id / system_id / location_ref | الموقع | FK / FK / FK / string(120) | Y / Y / N / Y | — | S-LAND / Z-PIERB / — / Gate B4 lounge, column C17 | none |
| discipline | التخصص | enum | Y | list DSC | ARC | none |
| description_en / _ar | الوصف | text(500) | Y (one language) | P1-8 scan | Ceiling tile damaged and stained | none |
| category | الفئة | enum | Y | `A` must be closed before acceptance / handover (يجب إغلاقه قبل التسليم) · `B` may be closed after handover by agreement (يمكن إغلاقه بعد التسليم) | B | none |
| raised_during | مرحلة الرصد | enum | Y | `walkdown` · `pre_handover` · `client_inspection` · `ir` · `other` | pre_handover | none |
| responsible_engagement_id | المقاول المسؤول | FK | Y | — | RAWABI@ANIA-EXP | none |
| target_date | التاريخ المستهدف | date | sys / editable | raised date + `punch_target_days` | 2026-10-09 | none |
| photos_before / photos_after | صور قبل / بعد | files | Y / cond. | ≥ 1 before; ≥ 1 after for Ready for Review | — | personal (photos) |
| pin | موقع على المخطط | {floor_plan_id, x_pct, y_pct} | N | 0.0–100.0 each | {Pier B Level 1, 41.2, 63.8} | none |
| status | الحالة | enum | Y | below | ready_for_review | none |

States: `open` مفتوح → `ready_for_review` جاهز للمراجعة (251, after photo and note) → `closed` مغلق (252 + RPM `punch_item.verify`) or back to `open` (252 + RPM, comment); `open` / `ready_for_review` → `voided` ملغى (244, reason). An open item may be escalated to an NCR (source `punch_item`; the item stays open and linked).

- **Q-PUN-01.** Items are raised one by one or in a walkdown session (one checklist response of type `punch_walkdown`; each non-compliant answer or free entry becomes an item).
- **Q-PUN-02.** Ready for Review needs ≥ 1 after photo and a note ≥ 10 chars (`PUNCH_EVIDENCE_REQUIRED`). Q-RPM-06 applies: the user who marked it ready cannot close it.
- **Q-PUN-03.** Overdue = not closed and today > target_date; counted in K-156; the engagement's quality contacts get a weekly digest.
- **Q-PUN-04.** Category A items open in a dossier's scope block dossier submission (Q-DOS-03 c); B items are listed in the dossier as "agreed open items".

## B.6 Floor plans and pins — المخططات

`q_floor_plans`: zone, level label, title EN / AR, revision, image (PNG or JPEG ≤ 10 MB, long edge ≤ 6000 px; PDF is not accepted: export the sheet as an image) (`PLAN_IMAGE_INVALID`), width_px / height_px (sys), status current / superseded.
- **Q-PIN-01.** Pins store percentages of image width and height, so a plan revision with the same aspect ratio (± 1 %) keeps every pin; a revision with another aspect ratio marks the pins "check position" until moved or confirmed.
- **Q-PIN-02.** The plan view shows pins coloured by status (open red, ready amber, closed green) with the category letter; tapping a pin opens the item. Pins are optional; items without a pin are listed beside the plan. No measuring, scale or layers (no BIM, handover §4).

## B.7 Handover dossier — ملف التسليم

`q_dossiers`: dossier_no, title EN / AR, scope (zone_ids and / or system_ids, ≥ 1), sections (codes from registry `DOSSIER_SECTIONS`, default all), status, compiled_at, compiled_by, snapshot (index JSON with every item ref, revision, status and file SHA-256), index_file_en / _ar (PDF), package_file (ZIP), submitted_at, revision (1, 2, …). `q_asbuilt_items`: dossier or scope, drawing_no, title, revision, date, status `submitted` · `approved`, file (optional).

**Sections** (registry `DOSSIER_SECTIONS`; Q1 provides `itp`, `ir`, `punch`, `asbuilt`; Q0 provides `ncr`; Q2 provides `mar`, `mir`, `tests`, `welding`, `calibration`; Q4 provides `documents`): each returns its items in scope and its blockers.

States: `draft` مسودة → `compiled` مُجمَّع (253; snapshot and files made) → `submitted` مُقدَّم (253; no blocker) → `accepted` مقبول (254 + RPM `dossier.accept`) or `returned` مُعاد (254 + RPM, comment) → `draft` (recompile). Accepted is final; a later change makes revision + 1.

- **Q-DOS-01.** A record belongs to a dossier when its zone is in the scope zones or its system is in the scope systems.
- **Q-DOS-02.** Compiling takes a snapshot at that moment; records changed later do not change the compiled files (the snapshot keeps each file's SHA-256).
- **Q-DOS-03.** **Blockers** (each listed with links; setting `dossier_blockers` may turn any into a warning): (a) an ITP point of type H or W with verifying record `ir` and no approved IR at a location key in scope used by any IR of that ITP; (b) an NCR in scope not Closed or Voided; (c) an open category A punch item; (d) an open IR comment; (e) from Q2: a failed test result without a closed NCR, or a rejected MIR whose quarantine item is not disposed; (f) an empty as-built list or an as-built item not approved.
- **Q-DOS-04.** Files: the index PDF (EN and AR, Hijri date, project, scope, each section with item refs, statuses and dates, a sign-off summary) and a ZIP holding the index PDFs and each referenced file under `NN-<section>/<ref>-<filename>`. No PDF-merging library is added (D-319). A package over 2 GB is refused (`DOSSIER_TOO_LARGE`; split the scope).
- **Q-DOS-05.** Viewer / Client may download an accepted dossier's index PDF (no photos); the ZIP needs 253 or 254.

## B.8 Q1 screens

| Screen | Phone | Desk |
|---|---|---|
| ITPs `/quality/itps` | Read the points of an ITP | Register (no, rev, discipline, engagement, status); builder: points table with drag order, type chips H / W / R / S, criteria picker, template picker; revision compare (changed points highlighted); coverage grid (Q-ITP-06) |
| Inspection requests `/quality/inspection-requests` | Raise IR (pick ITP point, location autocomplete from earlier keys, self-check); "My inspections today"; inspection run: 6d checklist runner, measurements with M&TE scan or pick, photos, result buttons, sign | Board by status and date; calendar of scheduled inspections per inspector; IR detail with rounds, comments, sign-offs, links (tests, NCRs); PDF |
| Punch `/quality/punch` | Walkdown mode: plan view, tap to drop a pin, photo, description; contractor "mark fixed" with after photo | Register with filters (zone, category, engagement, overdue); plan view; verify one by one (one sign-off per item) |
| Floor plans `/quality/floor-plans` | View | Upload, revision, pin check |
| Dossiers `/quality/dossiers` | Read status | Scope picker, section selection, blocker list with links, compile, download, submit, accept / return |

## B.9 Q1 notifications
| Trigger | Recipient | Timing | Channel |
|---|---|---|---|
| IR submitted | resolved responsible persons | immediately | in-app + email |
| IR not scheduled within `ir_schedule_hours` | resolvers; 239 holders | at the deadline | in-app + email |
| IR scheduled / rescheduled | requester | immediately | in-app + push |
| IR decided | requester; engagement quality contacts | immediately | in-app + email |
| Witness waived; review due | resolvers | at waiver; at the review deadline | in-app + email |
| Hold re-blocked by a void (Q-IR-08) | requesters of affected IRs | immediately | in-app + email |
| IR comment overdue | requester; engagement quality contacts | day after due | in-app |
| Punch items overdue | engagement quality contacts | weekly, Sunday 07:12 | in-app + email |
| Dossier submitted / decided | `dossier.accept` resolvers / compiler | immediately | in-app + email |

## B.10 Q1 errors
422 `ITP_INCOMPLETE`, `ITP_NOT_APPROVED`, `IR_NOTICE_TOO_SHORT`, `SELF_CHECK_REQUIRED`, `IR_RESULT_INCONSISTENT`, `NCR_REQUIRED`, `HOLD_POINT_NOT_RELEASED`, `HOLD_NOT_WAIVABLE`, `WITNESS_WAIT_NOT_OVER`, `PUNCH_EVIDENCE_REQUIRED`, `DOSSIER_BLOCKED`, `DOSSIER_TOO_LARGE`, `PLAN_IMAGE_INVALID`; 409 `ITP_IMMUTABLE`, `DOSSIER_IMMUTABLE`.

## B.11 Acceptance criteria — Q1
1. **AC-Q1-01** (Q-ITP-02) **Given** an ITP draft with only R and S points **When** submitted **Then** 422 `ITP_INCOMPLETE`; with point 30 changed to H **Then** Submitted.
2. **AC-Q1-02** (§B.3.3, Q-RPM-06) **Given** ITP-…-STC-001 Rev.2 submitted by Bilal **When** Abdullah (CONSULTANT_RE) approves with code B and a comment **Then** Approved, Rev.1 Superseded, a sign-off stored; Bilal approving **Then** 422 `SOD_CONFLICT`.
3. **AC-Q1-03** (Q-ITP-03) **Given** an Approved revision **When** a point is edited **Then** 409 `ITP_IMMUTABLE`.
4. **AC-Q1-04** (Q-ITP-04) **Given** an IR submitted on Rev.1 and Rev.2 approved afterwards **Then** the IR continues on Rev.1; a new IR on Rev.1 **Then** 422 `ITP_NOT_APPROVED`.
5. **AC-Q1-05** (Q-IR-03) **Given** a point 30 (H) IR submitted 2026-10-06 10:00 with proposed_at 2026-10-06 18:00 **Then** 422 `IR_NOTICE_TOO_SHORT`; 2026-10-07 10:00 **Then** accepted; short notice with a reason **Then** accepted and flagged.
6. **AC-Q1-06** (Q-IR-04) **Given** self_check_done false **Then** 422 `SELF_CHECK_REQUIRED`.
7. **AC-Q1-07** (Q-IR-08) **Given** point 30 (H) at key `Z-PIERB|level 3 slab, grid c14–c20` not yet approved **When** Joseph submits a point 40 IR at "Level 3 Slab,  grid C14–C20" (other case and spacing) **Then** 422 `HOLD_POINT_NOT_RELEASED` naming point 30; after IR-…-00412 round 2 is approved **Then** the point 40 IR is accepted.
8. **AC-Q1-08** (Q-IR-08) **Given** IR-…-00412 approved and later voided **Then** a submitted, undecided point 50 IR at the same key is re-blocked and Joseph is notified.
9. **AC-Q1-09** (Q-IR-05) **Given** a round with `COVER-40` measurement 33 mm **When** recorded as approved **Then** 422 `IR_RESULT_INCONSISTENT`; as rejected without a photo **Then** 422.
10. **AC-Q1-10** (Q-IR-06) **Given** IR-…-00412 round 1 rejected (spacers missing, workmanship) **Then** an NCR is offered and optional; round 2 rejected **Then** `NCR_REQUIRED`; a `not_ready` round **Then** no NCR prompt.
11. **AC-Q1-11** (Q-RPM-03) **Given** a RAWABI point 60 (S) IR **Then** Mazen (qc_inspector, no engagement) resolves; Joseph (qc_inspector, RAWABI-assigned) does not (Q-RPM-07); Abdullah does not unless a matrix row names him.
12. **AC-Q1-12** (Q-IR-09, Q-IR-10) **Given** a W IR scheduled 2026-10-06 08:00 with no attendance **When** Joseph records waived at 08:50 **Then** 422 `WITNESS_WAIT_NOT_OVER`; at 09:05 with checklist and photo **Then** Witness Waived; on an H IR **Then** 422 `HOLD_NOT_WAIVABLE`; review not done by 2026-10-09 **Then** Abdullah is alerted.
13. **AC-Q1-13** (Q-IR-11) **Given** an approved-with-comments round with "close comments before the next hold point" and one open comment **Then** the next H-gated IR **Then** 422 `HOLD_POINT_NOT_RELEASED` listing the comment.
14. **AC-Q1-14** (Q-IR-07) **Given** point 50 with competence_code `CONC-FIELD-TECH`, `competence_policy` block and an inspector without it **Then** scheduling **Then** 422 `COMPETENCE_NOT_MET`; with the registry default (Q2 absent) **Then** allowed with an info note.
15. **AC-Q1-15** (Q-IR-12, QX2) **Given** the Appendix A.4 September IR set **Then** K-141 = 80.0 % and K-142 = 19.1 %.
16. **AC-Q1-16** (Q-SHR-04) **Given** a measurement with MTE-0015 (overdue) **Then** the round saves with warning `MTE_NOT_CALIBRATED` and a `q_mte_usage` row exists.
17. **AC-Q1-17** (Q-IR-13) **Given** an IR approved by a paper sign-off **Then** the AR PDF shows "Signed on paper by …", the Hijri date and the M&TE numbers of the measurements.
18. **AC-Q1-18** (Q-IR-14) **Given** a round recorded offline at 08:10 and synced at 11:00 after its hold point was voided **Then** the round is stored as "needs confirmation", shown to the inspector, and not counted as decided.
19. **AC-Q1-19** (Q-PUN-02) **Given** an open punch item **When** marked ready without an after photo **Then** 422 `PUNCH_EVIDENCE_REQUIRED`; the user who marked it ready closing it **Then** 422 `SOD_CONFLICT`; Abdullah closes **Then** Closed.
20. **AC-Q1-20** (Q-PIN-01) **Given** the plan "Pier B Level 1" with 12 pins **When** a revision with the same aspect ratio is uploaded **Then** pins keep their positions; another aspect ratio **Then** pins show "check position".
21. **AC-Q1-21** (Q-PUN-03) **Given** a category A item with target 2026-10-01 still open **Then** it is overdue on 2026-10-06 and is in the next Sunday digest to RAWABI quality contacts.
22. **AC-Q1-22** (Q-DOS-03) **Given** DOS-ANIA-EXP-2026-0001 (Z-PIERB) with one open NCR and one open A item **When** submitted **Then** 422 `DOSSIER_BLOCKED` listing both; with `dossier_blockers` excluding (c) **Then** the A item is a warning only.
23. **AC-Q1-23** (Q-DOS-02, Q-DOS-04) **Given** a compiled dossier **When** a test report in scope is amended later **Then** the ZIP and snapshot hashes are unchanged; index PDFs exist in EN and AR with a Hijri date.
24. **AC-Q1-24** (§B.7) **Given** an accepted dossier **When** compile is attempted **Then** 409 `DOSSIER_IMMUTABLE`; "new revision" makes revision 2 in Draft.
25. **AC-Q1-25** (Q-DOS-05) **Given** Sarah (Viewer) **Then** she can download the accepted index PDF and not the ZIP.
26. **AC-Q1-26** (Q-PRF-04) **Given** RUH-CCH (logistics) **When** an ITP is created **Then** 409 `PROFILE_INACTIVE`.
27. **AC-Q1-27** (rule 41) **Given** the Arabic UI **Then** every Q1 label, point type, status, PDF and email is in Arabic; ITP and IR numbers, grid references and measurements stay LTR.

---

# Part C — Q2: materials, testing and lab, welding, calibration, competence

Profiles: materials (MAR, MIR, quarantine), pours and welding are construction only; test requests, calibration and competence serve both profiles (test types carry a profile, e.g. hygiene swabs for logistics).

## C.1 Q2 settings and lists

| Key | AR label | Type | Default | Allowed |
|---|---|---|---|---|
| `mar_review_days` | مهلة مراجعة طلب الاعتماد | days | 14 | 3–60 |
| `mar_required_categories` | فئات تتطلب اعتماد مواد | set of list MC | all except `consumables` | subset |
| `quarantine_ageing_days` | مدة الحجز قبل التنبيه | days | 14 | 3–90 |
| `test_auto_ncr` | إنشاء تقرير عدم مطابقة تلقائياً للاختبار الفاشل | enum | `auto` | `auto` · `prompt` |
| `test_overdue_days` | مهلة إدخال النتيجة | days after due | 1 | 0–14 |
| `early_age_warning_ratio` | نسبة التحذير المبكر للمقاومة | decimal | 0.65 ASSUMPTION | 0.40–0.90 |
| `pour_sampling_m3` | حجم الصبّة لكل مجموعة عينات | m³ | 50 ASSUMPTION (ACI minimum: once a day, once per 110 m³, once per 460 m² `[VERIFY]`) | 10–150 |
| `wpq_continuity_months` | مدة استمرارية تأهيل اللحّام | months | 6 (`[VERIFY]` ASME IX QW-322.1, AWS D1.1, ISO 9606-1) | 3–12 |
| `wpq_confirmation_mode` | تأكيد استمرارية اللحّام | enum | `weld_log` | `weld_log` · `weld_log_or_confirmation` (ISO 9606-1 six-monthly confirmation) |
| `repair_rate_alert_pct` | حد نسبة الإصلاح للّحام | % | 5.0 ASSUMPTION | 1.0–20.0 |
| `progressive_exam` | الفحص التصاعدي | bool | true | — |
| `mte_due_soon_days` | تنبيه قرب المعايرة | days | 30 | 7–90 |
| `oot_review_days` | مهلة مراجعة الخروج عن التفاوت | days | 14 | 3–60 |
| `competence_expiry_warning_days` | تنبيه انتهاء الكفاءة | days | 30 | 7–90 |

**MC — material categories:** `concrete_mix` خلطة خرسانية · `cement` إسمنت · `aggregates` ركام · `rebar` حديد تسليح · `structural_steel` حديد إنشائي · `blockwork` بلوك · `waterproofing` عزل مائي · `insulation` عزل حراري · `pipes_fittings` أنابيب وتجهيزات · `valves` صمامات · `ductwork` مجاري هواء · `cables` كابلات · `electrical_equipment` معدات كهربائية · `mechanical_equipment` معدات ميكانيكية · `coatings` دهانات وطلاءات · `finishes` تشطيبات · `asphalt` إسفلت · `consumables` مستهلكات · `other` أخرى.

## C.2 Testing and lab — الاختبارات والمختبرات (Q-TST)

### C.2.1 Test types (data) — `q_test_types`
code (`^[A-Z0-9-]{2,16}$`), version, name EN / AR, discipline (DSC) or `logistics`, profile, standard reference (text, e.g. "ASTM C39 / SBC 304"), specimen plan (list {age_days or null, count}), result fields (list {key, label EN / AR, unit, kind `numeric` · `text` · `pass_fail`}), evaluation (`fields` = one criterion per field, or `rule` = a criterion of kind `rule`), `ncr_class_on_fail` (minor / major / critical; may depend on which rule clause failed), competence code (optional), status (6d-style versions).

Seeded test types (Appendix A.2 has their criteria): `CONC-CYL` concrete cylinders (ASTM C31 / C39), `CONC-CUBE` concrete cubes (BS EN 12390-3), `CONC-CORE` cores (ASTM C42), `SLUMP` (ASTM C143), `CONC-TEMP` (ASTM C1064), `PROCTOR` (ASTM D1557), `FDT-SC` field density, sand cone (ASTM D1556), `FDT-NDG` field density, nuclear gauge (ASTM D6938), `CBR` (ASTM D1883), `PSD` grading (ASTM D6913), `ASPH-CORE` asphalt core density and thickness (ASTM D2726), `ASPH-MARSHALL` (ASTM D6927), `REBAR-TENSILE` (ASTM A615 / A370 `[VERIFY]` SASO equivalent), `HYDRO` hydrostatic pressure test (ASME B31.3 §345.4 `[VERIFY]`), `PNEU` pneumatic test, `DUCT-LEAK` duct leakage, `TORQUE` bolt torque, `DFT` coating dry-film thickness (SSPC-PA 2), `PULL-OFF` adhesion (ASTM D4541), `PILE-PIT` pile integrity (ASTM D5882); logistics: `ATP-SWAB` hygiene swab (RLU), `WATER-MICRO` water microbiology.

### C.2.2 Test request — طلب اختبار (`q_test_requests`, `q_test_specimens`)
| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| test_no | رقم الطلب | string | sys | Q-NUM | TST-ANIA-EXP-2026-00388 | none |
| test_type + version | نوع الاختبار | FK | Y | Published; profile matches | CONC-CYL v1 | none |
| site / zone / system / location_ref | الموقع | FK / FK / FK / string | Y / N / N / Y | — | S-LAND / Z-PIERB / — / Level 3 slab bay C14 | none |
| engagement_id | المقاول | FK | N | engagement on the project; default from the linked pour, IR or MIR (Q-RPM-07) | RAWABI@ANIA-EXP | none |
| lab_supplier_id | المختبر | FK | Y | category `testing_lab` (or `ndt_provider`); Q-SHR-02 / -03 | LAB-RGM | none |
| sampled_at / sampled_by / sample_ref | أخذ العينة | timestamptz / FK / string(40) | cond. | at Sampled | 2026-09-01 10:40 / Joseph / S-0077-3 | personal (by) |
| mte_ids | الأجهزة المستخدمة | FK[] | N | M&TE usage (Q-SHR-04) | [MTE-0012] | none |
| specimens | العينات | list {specimen_ref, age_days, due_on, tested_on, values} | sys / Y | from the plan; due_on = cast date + age | 3 at 7 d, 2 at 28 d … | none |
| report_no / report_file / tested_by_name | تقرير المختبر | string / file / string(120) | Y at Results Entered | lab report PDF | RGM-26-11873 | personal (name) |
| verdict / verdict_detail | الحكم | enum / JSON | sys | Q-CRT-01; `pass` · `fail` · `indicative` · `pending` | fail | none |
| linked | الارتباطات | `q_links` | N | IR, MIR, pour, weld, NCR | IR-…-00455, POUR-…-0077 | none |
| status | الحالة | enum | Y | §C.2.3 | verified | none |

### C.2.3 States
| From → To | AR | Who | Condition / error |
|---|---|---|---|
| — → Requested | مطلوب | 257 | Published test type of the project's profile; lab per Q-TST-02 (`SUPPLIER_DISQUALIFIED`) |
| Requested → Sampled | أُخذت العينة | 257 | sampled_at, sample_ref; M&TE usage (Q-SHR-04, `MTE_NOT_CALIBRATED` in block mode); specimens and due dates created |
| Sampled → At Lab | في المختبر | 257 | delivery to the lab recorded (date) |
| At Lab → Results Entered | أُدخلت النتائج | 257 | results of the acceptance age entered (earlier ages are indicative and may be entered while At Lab); Q-TST-04 (`TEST_RESULT_INCOMPLETE`); verdict computed; Q-TST-06 NCR |
| Results Entered → At Lab | في المختبر | 258 + RPM `test_request.verify` | returned for an entry error, comment ≥ 20 chars |
| Results Entered → Verified | معتمدة | 258 + RPM `test_request.verify` | Q-TST-05 (`SOD_CONFLICT`) |
| Verified → Amended | معدّلة | 258 + RPM | amended lab report and reason ≥ 20 chars (Q-TST-09); any other edit → 409 `RESULT_VERIFIED` |
| Amended → Verified | معتمدة | 258 + RPM | new version re-evaluated and verified; Q-RPM-06 |
| Requested / Sampled → Cancelled | ملغى | 257 | reason ≥ 20 chars |
| any (not Voided) → Voided | باطل | 244 | reason ≥ 20 chars; leaves KPIs; linked NCRs stay |

### C.2.4 Rules
- **Q-TST-01.** Test types, specimen plans, fields and acceptance are data (Q-CRT-03). A project may add its own versions; records pin the version.
- **Q-TST-02.** The lab must be a supplier of category `testing_lab` or `ndt_provider`; Q-SHR-02 and Q-SHR-03 apply on the sampling date.
- **Q-TST-03.** Specimen due dates come from the plan; an untested specimen past due_on + `test_overdue_days` alerts the requester (daily job).
- **Q-TST-04.** Results Entered needs the lab report file, the report no and every result field of the tested specimens (`TEST_RESULT_INCOMPLETE`); the verdict is computed at once (Q-CRT-01) and stored with the criterion version.
- **Q-TST-05.** Verification (RPM) checks the report against the entries; Q-RPM-06 applies (the user who entered the results cannot verify).
- **Q-TST-06.** **Failed verdict:** with `test_auto_ncr` = auto, an NCR (source `test_result`, class per `ncr_class_on_fail`, category `testing_failure`) is opened by System at Results Entered (not waiting for verification, so containment starts at once); with `prompt`, the user must raise it or record why not (reason ≥ 20 chars, counted). A failed test linked to an IR shows on the IR.
- **Q-TST-07.** **Indicative results** (e.g. 7-day strength) never fail; a 7-day strength < `early_age_warning_ratio` × f'c gives warning `EARLY_STRENGTH_LOW` to the requester and the pour's quality engineer.
- **Q-TST-08.** **Concrete strength rules** (criteria kind `rule`, params editable):
  - `aci318_strength` (cylinders; `[VERIFY]` ACI 318-19 §26.12.3.1 and SBC 304): a *strength test* = mean of the 28-day specimens of one set (2 × 150 × 300 mm or 3 × 100 × 200 mm). Per mix (MAR + grade), tests in cast-date order: (a) every mean of 3 consecutive tests ≥ f'c; (b) no test < f'c − 3.5 MPa when f'c ≤ 35 MPa, or < 0.90 f'c when f'c > 35 MPa. A test fails when it breaks (b), or completes a run of 3 that breaks (a). (a) is `pending` for the first two tests of a mix.
  - `en206_strength` (cubes; `[VERIFY]` BS EN 206 initial production): groups of 3 consecutive results: mean ≥ fck + 4 MPa and each result ≥ fck − 4 MPa.
  - `aci318_cores` (`[VERIFY]` ACI 318 §26.12.6): mean of 3 cores ≥ 0.85 f'c and no core < 0.75 f'c.
- **Q-TST-09.** **Amendments** (ISO/IEC 17025 7.8.8 idea): a Verified result is never edited. An amendment (lab's amended report, reason ≥ 20 chars) creates a new result version, re-evaluates, and keeps the original visible ("Amended on … — original: fail"). An NCR opened by the original failure stays open; its owner decides (void it with reason "result amended" through 244, or keep it).
- **Q-TST-10.** **Retests** (e.g. cores after failed cylinders) are new test requests linked `relates` to the original; the original verdict never changes.
- **Q-TST-11.** **Pours** (`q_pours`, construction): pour_no, engagement_id (sys: the ITP engagement of the linked pre-pour IR, Q-RPM-07), element, site / zone / location_ref, MAR (approved concrete mix), grade (f'c or fck), volume_m3, supplier (ready-mix), started_at / finished_at, ambient temperature, linked IRs (pre-pour hold and pour witness, via `q_links`), test requests (sets). Required sets = max(1, ⌈volume_m3 ÷ `pour_sampling_m3`⌉) per pour and mix; closing a pour with fewer sets gives warning `POUR_SAMPLING_SHORT` (counted in K-152 chip).
- **Q-TST-12.** **Pour start and the hold point:** starting a pour requires the linked pre-pour hold IR to be released: registry `HOLD_CHECKS["itp_point"]` returns True → allowed; False → 422 `HOLD_POINT_NOT_RELEASED`; None (Q1 not installed, or no link) → warning `HOLD_STATUS_UNKNOWN`.
- **Q-TST-13.** Strength evaluation (Q-TST-08) groups tests by mix across pours; a mix whose 3-test window fails marks every pour of that window on the pour page.
- **Q-TST-14.** Other evaluators: `slump_astm_c94` (target T: T ≤ 50 mm → ± 15; 50 < T ≤ 100 → ± 25; T > 100 → ± 40 `[VERIFY]` ASTM C94); `ratio_min` (field dry density ÷ maximum dry density × 100 ≥ x); `sspc_pa2` (spot = mean of 3 gauge readings; every spot within [0.8 × min, 1.2 × max]; area mean within [min, max] `[VERIFY]` SSPC-PA 2 restriction level); `pressure_hold` (test pressure ≥ factor × design pressure, hold ≥ minutes, pressure drop ≤ allowed, no visible leak).

**Worked examples (backend unit tests must match):**
- **QX4 — ACI 318, f'c = 32 MPa** (≤ 35 → (b) limit 28.5): tests 34.1, 31.2, 33.0, 30.4, 27.9. Test 1, 2: (b) pass, (a) pending → **pass**. Test 3: mean(34.1, 31.2, 33.0) = 32.77 → **pass**. Test 4: mean(31.2, 33.0, 30.4) = 31.53 < 32 → **fail** (a). Test 5: 27.9 < 28.5 → **fail** (b); mean 30.43 also breaks (a). Variant f'c = 40 (> 35 → (b) limit 36.0): a test of 33.2 → **fail** (b) → NCR class critical (CONC-CYL `ncr_class_on_fail` (b) = critical, (a) = major).
- **QX5 — EN 206, fck,cube = 50:** group 58.5, 55.0, 51.5 → mean 55.0 ≥ 54, min 51.5 ≥ 46 → **pass**; group 53.0, 54.5, 52.0 → mean 53.17 < 54 → **fail**.
- **QX6 — cores, f'c = 40:** 36.1, 34.9, 33.6 → mean 34.87 ≥ 34.0 and min 33.6 ≥ 30.0 → **acceptable** (supports a use-as-is disposition, NCR-…-0044).
- **QX7 — slump** target 100 mm: 75 and 125 pass, 130 fails. **Compaction** MDD 2.150 g/cm³: 2.068 → 96.19 % ≥ 95 → pass; 2.030 → 94.42 % → fail. **DFT** spec 125–200 µm: spot means 124, 141, 132, 119, 136 → all within [100, 240], area mean 130.4 within [125, 200] → **pass**; a spot of 96 → **fail**.

## C.3 Materials — المواد (Q-MAT)

### C.3.1 Material Approval Request (MAR) — طلب اعتماد مواد
`q_mars`: mar_no + revision, engagement_id (requesting engagement, required), title EN / AR, category (MC), spec section ref, manufacturer, supplier (Q-SHR-02), country of origin, brand / model, compliance table (list {requirement, offered, result `complies` · `deviation` · `not_applicable`, note}), deviations note (required when any row is `deviation`), documents (technical data sheet, test certificates, conformity certificate e.g. SABER `[VERIFY]`, sample ref), approval code (A / B / C / D, §B.3.1 meanings), comments, status.

States: Draft مسودة (255) → Submitted مُقدَّم (255) → Approved معتمد (A) / Approved as Noted معتمد مع ملاحظات (B) / Revise and Resubmit يعاد للتعديل (C) / Rejected مرفوض (D) (256 + RPM `mar.approve`; B, C, D need a comment ≥ 20 chars). C → the author resubmits a new revision (revision + 1, copied). Approved / Approved as Noted → Superseded (a later revision approved) or Withdrawn (239, reason).
- **Q-MAT-01.** Submit needs ≥ 1 compliance row and the technical data sheet (`MAR_INCOMPLETE`); a `deviation` row needs the deviations note and marks the MAR "with deviations", which the approver must accept explicitly (checkbox recorded in the sign-off).
- **Q-MAT-02.** Not decided within `mar_review_days` of submission → alert to the resolvers and 239 holders.

### C.3.2 Material Inspection Request on delivery (MIR) — طلب فحص المواد الموردة
`q_mirs`: mir_no, MAR + revision (Q-MAT-03), engagement_id (sys, copied from the MAR), delivery note no, PO no, supplier, delivered_at, quantity + unit, batch / heat / lot numbers (list), certificate heat numbers (list, from the mill certificates, EN 10204 type 3.1 / 3.2 for steel), certificates (files), storage zone, checklist response (`quality_type` `mir_inspection`), samples (→ linked test requests), accepted_qty / rejected_qty, result `accepted` مقبول · `accepted_with_comments` مقبول مع ملاحظات · `rejected` مرفوض, status Draft → Submitted → Decided (256 + RPM `mir.decide`) / Cancelled.
- **Q-MAT-03.** A MIR needs a MAR of the same material in Approved or Approved as Noted when the category is in `mar_required_categories` (`MAR_NOT_APPROVED`).
- **Q-MAT-04.** Heat numbers on the material tags that are not on any certificate give warning `HEAT_NUMBER_MISMATCH`; accepting such a MIR needs a comment ≥ 20 chars.
- **Q-MAT-05.** accepted_qty + rejected_qty = quantity (`MIR_QTY_MISMATCH`). A rejected quantity > 0 creates a quarantine item and an NCR (source `mir`, class major) automatically.
- **Q-MAT-06.** "Accepted subject to tests": accepted_with_comments with linked pending test requests; a later failed result shows on the MIR and the NCR prompt offers "quarantine the remaining stock" (creates a quarantine item with the entered quantity).

### C.3.3 Quarantine — المواد المحجوزة
`q_quarantine_items`: tag_no (`QTN` numbering, printed on a red tag label with QR to the record), material description, MIR or source link, quantity + unit, zone / location, photos, NCR link, status `quarantined` محجوز → `released` مُفرج عنه · `returned` مُعاد للمورد · `scrapped` متلف (256 + RPM `quarantine.dispose`).
- **Q-MAT-07.** Release needs a linked NCR whose disposition (use_as_is, repair or rework) is Approved (`QUARANTINE_RELEASE_BLOCKED`); returned needs the return note no; scrapped needs disposal evidence.
- **Q-MAT-08.** Items quarantined longer than `quarantine_ageing_days` alert the NCR owner weekly.

## C.4 Calibration of measuring and test equipment — معايرة أجهزة القياس (Q-CAL)

**MT — M&TE types** (for `q_mte_items`): `tape_rule` · `caliper_micrometer` · `level_theodolite` · `total_station` · `gnss_survey` · `thermometer` · `temp_probe` · `temp_logger` · `humidity_logger` · `infrared_thermometer` · `pressure_gauge` · `torque_wrench` · `dft_gauge` · `holiday_detector` · `hardness_tester` · `compression_machine` · `slump_cone` (verification) · `cube_mould` (verification) · `nuclear_density_gauge` (`[VERIFY]` NRRC licence and leak test) · `scale_balance` · `multimeter_insulation_tester` · `ultrasonic_thickness` · `other`.
**CS — calibration status:** `calibrated` معاير · `due_soon` قريب الاستحقاق · `overdue` متأخر · `out_of_service` خارج الخدمة · `limited_use` استخدام محدود · `not_required` لا يتطلب معايرة · `unknown` غير معروف (only before Q2 is installed).

`q_calibrations`: cal_no, mte, kind (`calibration` · `verification`), cal_date, provider (supplier of category `calibration_lab`, or `in_house` with the reference standard's MTE no), certificate no and file (required for calibration), points (list {nominal, as_found, as_left, error = as_found − nominal, tolerance, in_tolerance}), as_found_ok / as_left_ok (sys: every point in tolerance), traceability statement (e.g. "traceable to SI through a national metrology institute" `[VERIFY]` SASO NMCC), uncertainty (optional), next_due (sys), status `draft` → `accepted` (262 + RPM `calibration.accept`) · `rejected` (certificate not acceptable, comment).

- **Q-CAL-01.** Accepting a calibration sets the M&TE's last calibration and `cal_due_on` = add_months(cal_date, interval_months) − 1 day (month-end clamp, as 6d §6.4).
- **Q-CAL-02.** **Status** (recomputed on every change and by the daily job): manual `out_of_service` / `limited_use` (with reason) win; `check_kind` none → `not_required`; never calibrated → `overdue`; today > cal_due_on → `overdue`; today ≥ cal_due_on − `mte_due_soon_days` → `due_soon`; else `calibrated`.
- **Q-CAL-03.** A calibration with as_left out of tolerance sets the M&TE `out_of_service` until a later accepted calibration is in tolerance.
- **Q-CAL-04.** **Out-of-tolerance review:** an accepted calibration with as_found out of tolerance opens one `q_oot_reviews` record: period from the last accepted calibration whose as_left was in tolerance (or the first usage) to this cal_date; items = every `q_mte_usage` row of that M&TE in the period, plus readings of monitoring points to which the logger was assigned in the period (Q3 provides them through `RECORD_TYPES`). Each item gets a decision: `no_impact` (justify; the screen shows the margin between the recorded value and the nearest criterion limit next to |as-found error|, and proposes no_impact when margin > |error|), `recheck` (link the new inspection or test), or `ncr` (raise an NCR, source `oot_review`). The review closes when every item is decided (262 + RPM `oot_review.decide`); due within `oot_review_days`.
- **Q-CAL-05.** A printable status label (EN / AR): MTE no, status colour, calibration date, due date, QR with the record URL (opens after sign-in; not a token).
- **Q-CAL-06.** Verification-only items (slump cone, cube moulds) use kind `verification` with a checklist or measured dimensions instead of a certificate.
- **Q-CAL-07.** A logger or probe assigned to a monitoring point (Q3) or used in a mapping study should have a calibration point within ± 5 °C of the zone's range ASSUMPTION; otherwise warning `CAL_RANGE_NOT_COVERED`.
- **Worked examples. QX10:** cal_date 2026-01-15, interval 12 → due **2027-01-14**; due_soon from 2026-12-15 (30 days). **QX11:** probe MTE-0042 (tolerance ± 0.5 °C) as-found error **+1.2 °C** at the 0 °C point on 2026-09-10; last in-tolerance calibration 2026-03-08 → 37 receiving checks in the period; 35 have margin > 1.2 °C (no_impact proposed), 2 were within 1.2 °C of the limit → `recheck` of the receipt records → 1 NCR (frozen line at −18.4 °C recorded, true value possibly −17.2 °C).

## C.5 Competence — الكفاءة (Q-CPT)

`q_competence_reqs`: code (`^[A-Z0-9-]{3,20}$`, e.g. `CONC-FIELD-TECH`, `NDT-RT-L2`, `CWI`, `MAPPING-LEAD`, `QMS-AUDITOR`), title EN / AR, applies_to (list CA), filters (discipline, test type, NDT method, storage class), evidence: `any_of` and optional `all_of` lists of {hook kind `training_course` or `personnel_certificate`, code, minimum level}, policy (`inherit` · `warn` · `block`), profile.
**CA — applies to:** `ir_inspector` · `test_technician` · `ndt_technician` · `welding_inspector` · `receiving_inspector` · `mapping_lead` · `auditor` · `calibration_acceptor` · `warehouse_qc` · `pharmacist` · `equipment_operator` مشغل معدات · `other`.

- **Q-CPT-01.** `check(user, code, at)`: the user's linked worker (Phase 2 `workers.user_id`) is evaluated through the Phase 2 hook providers (`app/services/access/hooks.py`: `training_course` from Phase 5, `personnel_certificate` from Phase 4, with their in-force predicates) at `at`; met ⇔ the `any_of` list has one met item and every `all_of` item is met; valid_until = the earliest valid_until of the evidence used. No linked worker → not met, reason `HOLDER_NOT_LINKED`. Q2 registers this as `COMPETENCE`.
- **Q-CPT-02.** Phase 8 stores no copy of a certificate or training record; it reads them.
- **Q-CPT-03.** The competence matrix lists people (users holding quality roles, named inspectors, NDT technicians) × requirements: met (until date) · expiring (≤ `competence_expiry_warning_days`) · not met · not applicable; exportable (246).
- **Q-CPT-04.** Expiring competence alerts the person and 239 holders at 30 / 7 / 0 days.
- **Q-CPT-05.** Policy `block` refuses the action (`COMPETENCE_NOT_MET`); `warn` stores it with the warning (counted in K-155).
- **Q-CPT-06.** Welders are qualified by WPQ (Q-WLD), not by requirement rows.

## C.6 Welding — اللحام (Q-WLD)

**WP — processes:** `SMAW` · `GTAW` · `GMAW` · `FCAW` · `SAW` · `other`. Positions: plate `1G`–`4G`, `1F`–`4F`; pipe `1G`, `2G`, `5G`, `6G`, `6GR`.

| Entity | Main fields | States |
|---|---|---|
| `q_wps` — WPS مواصفة إجراء اللحام | wps_no + revision, standard (`AWS_D1_1` · `ASME_IX` · `ISO_15614_1` · `other`), processes, joint types, base material group (P-No / group), thickness range mm, diameter range mm, positions, filler (classification, F-No, A-No), preheat min °C, interpass max °C, PWHT (none / parameters), gas, `prequalified` (AWS D1.1), supporting PQRs | Draft → Submitted → Approved (260 + RPM `wps.approve`) → Superseded / Withdrawn |
| `q_pqrs` — PQR سجل تأهيل الإجراء | pqr_no, standard, process, test date, results (tensile, bend, impact, macro, hardness: value + pass / fail), lab (supplier), certificate | Draft → Approved (260 + RPM) |
| `q_welders` — اللحّامون | worker_id (Phase 2, required), welder stamp (`^[A-Z0-9-]{2,10}$`, unique per project), engagement, status active / inactive; no ID number copied (P2-7) | — |
| `q_wpqs` — WPQ تأهيل اللحّام | wpq_no, welder, standard, process, test WPS, test date, coupon (thickness, diameter, position), qualified ranges (positions, thickness, diameter min, F-No), test method (`RT` · `bend` · `fracture` · `macro`), result, examiner (supplier or TPI), certificate file, optional Phase 4 personnel certificate link, last_use (sys, per process), continuity_until (sys), revalidation_due (ISO 9606-1, `[VERIFY]` 2 or 3 years) | Draft → Active (260 + RPM `wpq.approve`) → Lapsed (continuity, System) · Expired (revalidation, System) · Revoked (259 + RPM, reason) |
| `q_welds` — سجل اللحام | joint_id (`^[A-Z0-9-]{3,30}$`, unique per project, e.g. `PB-RT-T12-J07`), engagement_id (sys: the first root-pass welder's engagement, Q-RPM-07), drawing ref, zone, system, WPS, joint type (`butt` · `fillet` · `branch` · `socket`), diameter, thickness, length mm, welders (list {welder, passes root / fill / cap}), welded_on, visual result (VT accept / reject), NDT lot code and method, selected_for_ndt (with reason `random` · `progressive` · `100pct`), NDT results (list {method `RT` · `UT` · `MT` · `PT`, report no, file, result accept / reject, defect type, defect length mm, examined length mm, technician name}), repair_count | transition table below |


**Weld transitions:**

| From → To | AR | Who | Condition / error |
|---|---|---|---|
| — → Welded | منفّذ | 259 | Q-WLD-01 (`WPS_RANGE_EXCEEDED`), Q-WLD-02 (`WELDER_NOT_QUALIFIED`) |
| Welded → Visual Accepted | مقبول بصرياً | 259 | VT accept; a weld not selected for NDT stays Visual Accepted and counts as accepted |
| Welded → Visual Rejected | مرفوض بصرياً | 259 | VT reject with defect type |
| Visual Accepted → NDT Pending | بانتظار الفحص غير الإتلافي | 259 | selected for NDT (`random` · `progressive` · `100pct`, Q-WLD-04 / -05) |
| NDT Pending → Accepted | مقبول | 259 | NDT result accept with report no and file; technician competence (Q-WLD-08, `COMPETENCE_NOT_MET` in block mode) |
| NDT Pending → Rejected | مرفوض | 259 | NDT reject with defect type and length; progressive selections created (Q-WLD-05) |
| Visual Rejected / Rejected (repair_count 0) → Repaired R1 | إصلاح أول | 259 | repair recorded by a qualified welder (Q-WLD-02) |
| Rejected (repair_count 1) → Repaired R2 | إصلاح ثانٍ | 259 + RPM `weld.repair2_approve` | Q-WLD-06 (`SIGNOFF_REQUIRED`) |
| Repaired R1 / R2 → NDT Pending (or Visual Accepted for VT-only welds) | — | 259 | re-examination by the same method |
| Rejected (repair_count 2) → Cut Out | مقطوع | 259 | Q-WLD-10 NCR opened by System |
| any (not Voided) → Voided | باطل | 244 | reason ≥ 20 chars; leaves KPIs and continuity |

- **Q-WLD-01.** A weld needs an Approved WPS whose process, position and thickness / diameter ranges cover the joint (`WPS_RANGE_EXCEEDED`).
- **Q-WLD-02.** Every welder on a weld needs an Active WPQ for the process whose positions and ranges cover the joint, with continuity valid on welded_on (`WELDER_NOT_QUALIFIED`). Recording with an override (reason ≥ 20 chars, 260 holder) is possible for a late discovery and raises an NCR (Q-WLD-10).
- **Q-WLD-03.** **Continuity:** last_use(process) = the latest welded_on of not-voided welds by the welder with that process, or the WPQ test date if later; with mode `weld_log_or_confirmation`, a recorded six-monthly confirmation (date, quality engineer) also counts. continuity_until = add_months(last_use, `wpq_continuity_months`) − 1 day; the day after, the WPQ becomes Lapsed for that process (System, daily job), and a new test re-activates it.
- **Q-WLD-04.** **NDT percentage per lot:** for a lot with required r % for a method: n = welds of the lot with visual accepted; e = welds examined by that method at first NDT; achieved = e ÷ n × 100; shortfall = ⌈r × n ÷ 100⌉ − e when > 0, listed on the lot page. "Pick welds" proposes a random selection covering every welder of the lot at least once where possible.
- **Q-WLD-05.** **Progressive examination** (`[VERIFY]` ASME B31.3 §341.3.4) with `progressive_exam`: a rejected random weld adds 2 welds by the same welder in the lot (reason `progressive`); if either is rejected, 2 more for each rejected one; if any of those is rejected, all remaining welds of that welder in the lot are selected (`100pct`).
- **Q-WLD-06.** **Repairs:** a rejected weld is repaired (R1) and re-examined by the same method; a second repair (R2) needs a sign-off of `weld.repair2_approve` (RPM; seeded default role quality_engineer) with a comment ≥ 20 chars; a weld rejected after R2 is cut out.
- **Q-WLD-07.** **Repair rate** per welder and period: rejected first examinations ÷ first examinations × 100 (by joint); by length when lengths are recorded: Σ defect length of rejected first examinations ÷ Σ examined length × 100. Re-examinations of repairs are not counted twice. A welder above `repair_rate_alert_pct` with ≥ 10 first examinations in 90 days alerts the quality engineer (suggest retest or revoke).
- **Q-WLD-08.** NDT technicians must meet the competence requirement for the method and level (e.g. `NDT-RT-L2`, ISO 9712) through `COMPETENCE` (Q-CPT-05 policy).
- **Q-WLD-09.** The weld log and the lot summary export to CSV / XLSX (246) and feed the dossier section `welding`.
- **Q-WLD-10.** NCR (source `weld`, class major) is opened by System when: a weld is cut out; progressive examination reaches 100 % for a welder in a lot; or a weld was recorded with the Q-WLD-02 override.
- **Worked examples. QX8:** lot "PB-ROOF RT 10 %", welder W-017, 40 welds visual accepted → required ⌈4.0⌉ = 4; 4 examined, J07 rejected → progressive: 2 more of W-017 examined, both accepted → lot met (6 of 40 = 15.0 % achieved); J07 repaired R1 and accepted. Repair rate W-017 = 1 ÷ 6 = **16.7 %** (above 5.0 % but fewer than 10 first examinations → no alert). **QX9:** W-021 last SMAW weld 2026-03-28 → continuity_until **2026-09-27**; on 2026-09-28 the WPQ is Lapsed; a weld by W-021 on 2026-10-02 → 422 `WELDER_NOT_QUALIFIED`.

## C.7 Q2 screens

| Screen | Phone | Desk |
|---|---|---|
| Materials (MAR) `/quality/materials` | Read status | Register; form with compliance table; revision history; approval codes |
| Material inspections (MIR) `/quality/material-inspections` | Delivery check at the gate or store: checklist, photos, heat numbers, quantities, accept / reject | Register; certificate comparison panel |
| Quarantine `/quality/quarantine` | Scan the red tag, see status | Register with ageing; release / return / scrap |
| Tests `/quality/tests` and Test types `/quality/test-types` | Sampling entry (time, sample refs, slump, temperature with M&TE) | Specimen calendar (due today / overdue); results entry with automatic verdict; amendment history; test type editor (240 / 239) |
| Pours `/quality/pours` | Pour log entry | Pour list with sets required vs taken and mix strength status |
| Welding `/quality/welding` (WPS, PQR, welders, WPQs, weld log, NDT lots) | Weld entry by stamp, visual result | Continuity board (welder × process, days left), lot NDT %, repair rates |
| M&TE tabs (calibrations, OOT, label) on the Q0 `/quality/mte` page, and Calibration `/quality/calibration` | Scan the label, see status | Register with status chips and due list; calibration entry; OOT reviews with item decisions |
| Competence `/quality/competence` | — | Requirements editor; matrix |

## C.8 Q2 notifications
| Trigger | Recipient | Timing | Channel |
|---|---|---|---|
| MAR submitted / not decided in time | resolvers / resolvers + 239 | immediately / at `mar_review_days` | in-app + email |
| MIR rejected; quarantine ageing | NCR owner; engagement quality contacts | immediately; weekly | in-app + email |
| Specimen test overdue | requester | daily 07:12 | in-app |
| Failed or early-low result | requester; quality engineer; NCR owner | at Results Entered | in-app + email |
| M&TE due soon / overdue | custodian; quality engineers | at 30 / 7 / 0 days; then weekly | in-app + email |
| OOT review opened / overdue | resolvers | immediately / at the deadline | in-app + email |
| WPQ continuity ending | welder's engagement quality contacts; quality engineers | 30 / 7 / 0 days | in-app |
| Repair rate over the limit | quality engineers | at detection | in-app + email |
| Competence expiring | the person; 239 holders | 30 / 7 / 0 days | in-app + email |

## C.9 Q2 errors
422 `TEST_RESULT_INCOMPLETE`, `SIGNOFF_REQUIRED`, `MAR_INCOMPLETE`, `MAR_NOT_APPROVED`, `MIR_QTY_MISMATCH`, `QUARANTINE_RELEASE_BLOCKED`, `HOLD_POINT_NOT_RELEASED`, `WPS_RANGE_EXCEEDED`, `WELDER_NOT_QUALIFIED`, `COMPETENCE_NOT_MET`, `CALIBRATION_CERT_REQUIRED`; 409 `RESULT_VERIFIED` (edit after verification). Warnings: `EARLY_STRENGTH_LOW`, `POUR_SAMPLING_SHORT`, `HOLD_STATUS_UNKNOWN`, `HEAT_NUMBER_MISMATCH`, `CAL_RANGE_NOT_COVERED`, `LAB_NOT_ACCREDITED_FOR_SCOPE`.

## C.10 Acceptance criteria — Q2
1. **AC-Q2-01** (Q-TST-08, QX4) **Given** five CONC-CYL tests of one mix with f'c 32 as QX4 **Then** verdicts pass, pass, pass, fail, fail with the reasons (a) and (b) as stated.
2. **AC-Q2-02** (Q-TST-08) **Given** f'c 40 and a test of 33.2 MPa **Then** fail (b) and an NCR of class critical is opened by System at Results Entered (`test_auto_ncr` auto).
3. **AC-Q2-03** (QX5) **Given** `en206_strength` fck 50 **Then** group (58.5, 55.0, 51.5) passes and (53.0, 54.5, 52.0) fails.
4. **AC-Q2-04** (QX6, Q-TST-10) **Given** cores 36.1, 34.9, 33.6 on a retest linked to the failed cylinder test **Then** acceptable; the original cylinder verdict stays fail.
5. **AC-Q2-05** (QX7) **Given** the slump, compaction and DFT values of QX7 **Then** each verdict is as stated.
6. **AC-Q2-06** (Q-TST-07) **Given** a 7-day mean of 24.0 MPa with f'c 40 (0.60 < 0.65) **Then** verdict indicative and warning `EARLY_STRENGTH_LOW` to the requester.
7. **AC-Q2-07** (Q-TST-04) **Given** results without the lab report file **Then** 422 `TEST_RESULT_INCOMPLETE`.
8. **AC-Q2-08** (Q-TST-05) **Given** Joseph entered the results of a RAWABI pour test (engagement from the pour) **When** Joseph verifies **Then** 422 `SOD_CONFLICT`; Bilal (RAWABI-assigned) verifies **Then** 422 `SOD_CONFLICT` (Q-RPM-07); Rania (PMC quality_engineer, no engagement) verifies **Then** Verified with a sign-off; Hatem (qa_qc_manager, not on the default row) verifying **Then** 403.
9. **AC-Q2-09** (Q-TST-09) **Given** a Verified fail **When** a field is edited **Then** 409 `RESULT_VERIFIED`; an amendment with reason and file **Then** a new version, the original shown, and the NCR still open.
10. **AC-Q2-10** (Q-TST-06) **Given** `test_auto_ncr` prompt and a failed result **When** the user declines without a reason **Then** 422; with a reason ≥ 20 chars **Then** saved and counted.
11. **AC-Q2-11** (Q-TST-02, Q-SHR-03) **Given** LAB-RGM accreditation without CONC-CORE in scope **Then** a CONC-CORE request warns `LAB_NOT_ACCREDITED_FOR_SCOPE`; a disqualified lab → 422 `SUPPLIER_DISQUALIFIED`.
12. **AC-Q2-12** (Q-TST-03) **Given** a 28-day specimen due 2026-10-04 without a result **Then** on 2026-10-06 07:12 the requester is alerted once.
13. **AC-Q2-13** (Q-TST-11) **Given** POUR-…-0077 of 186 m³ with 3 sets **When** closed **Then** warning `POUR_SAMPLING_SHORT` (required 4).
14. **AC-Q2-14** (Q-TST-12) **Given** a pour linked to an IR of point 30 that is Rejected **When** started **Then** 422 `HOLD_POINT_NOT_RELEASED`; without Q1's registry entry **Then** warning `HOLD_STATUS_UNKNOWN`.
15. **AC-Q2-15** (Q-MAT-01) **Given** a MAR with a deviation row and no deviations note **Then** 422 `MAR_INCOMPLETE`; approval code C without comment **Then** 422.
16. **AC-Q2-16** (Q-MAT-03) **Given** MAR-…-0027 (waterproofing) in Revise and Resubmit **When** a MIR for it is submitted **Then** 422 `MAR_NOT_APPROVED`; for category consumables without a MAR **Then** allowed.
17. **AC-Q2-17** (Q-MAT-05) **Given** MIR-…-0112 with quantity 240 m, accepted 180, rejected 60 **Then** a quarantine item of 60 m and an NCR (source mir, major) exist; 180 + 50 → 422 `MIR_QTY_MISMATCH`.
18. **AC-Q2-18** (Q-MAT-04) **Given** a rebar MIR with tag heat H71203 absent from the certificates **Then** warning `HEAT_NUMBER_MISMATCH` and acceptance needs a comment.
19. **AC-Q2-19** (Q-MAT-07) **Given** the quarantine item of AC-Q2-17 and its NCR not yet Disposition Approved **When** released **Then** 422 `QUARANTINE_RELEASE_BLOCKED`; returned with a return note no. **Then** Returned.
20. **AC-Q2-20** (Q-CAL-01, Q-CAL-02, QX10) **Given** a calibration on 2026-01-15 with interval 12 **Then** due 2027-01-14, status due_soon from 2026-12-15 and overdue on 2027-01-15; an M&TE never calibrated is overdue.
21. **AC-Q2-21** (Q-CAL-03) **Given** a calibration with as_left out of tolerance **When** accepted **Then** the M&TE is out_of_service and usage warns / blocks per policy.
22. **AC-Q2-22** (Q-CAL-04, QX11) **Given** MTE-0042 as-found +1.2 °C on 2026-09-10 **Then** an OOT review covers 2026-03-08…2026-09-10 with 37 receiving items; 35 proposed no_impact; the review cannot close until all 37 are decided; one `ncr` decision opens an NCR with source `oot_review`.
23. **AC-Q2-23** (Q-CAL-07) **Given** a logger calibrated only at +5 and +25 °C assigned to the frozen zone (−25 to −18) **Then** warning `CAL_RANGE_NOT_COVERED`.
24. **AC-Q2-24** (Q-CAL) **Given** a calibration without a certificate file **When** accepted **Then** 422 `CALIBRATION_CERT_REQUIRED`; a verification of a slump cone without a certificate **Then** accepted.
25. **AC-Q2-25** (Q-CPT-01) **Given** requirement `NDT-RT-L2` (personnel certificate `ndt_rt` level ≥ 2) and an NDT technician whose certificate ended 2026-09-30 **Then** check on 2026-10-06 → not met; a user without a linked worker → not met `HOLDER_NOT_LINKED`.
26. **AC-Q2-26** (Q-CPT-03, Q-CPT-04) **Given** a QC inspector whose course expires 2026-10-20 **Then** the matrix shows expiring and alerts were sent at 30 days (2026-09-20) and are due at 7 days.
27. **AC-Q2-27** (Q-WLD-01, Q-WLD-02) **Given** WPS-NAJD-SMAW-01 (thickness 5–25 mm) and a 32 mm joint **Then** 422 `WPS_RANGE_EXCEEDED`; a welder without an Active WPQ **Then** 422 `WELDER_NOT_QUALIFIED`.
28. **AC-Q2-28** (Q-WLD-03, QX9) **Given** W-021's last SMAW weld 2026-03-28 **Then** continuity_until 2026-09-27; the job on 2026-09-28 sets the WPQ Lapsed; a weld on 2026-10-02 → 422.
29. **AC-Q2-29** (Q-WLD-04, Q-WLD-05, QX8) **Given** QX8 **Then** required 4, progressive selections 2 with reason `progressive`, achieved 15.0 %, W-017 repair rate 16.7 % and no alert (fewer than 10 examinations).
30. **AC-Q2-30** (Q-WLD-05) **Given** both progressive welds rejected **Then** 2 more for each are selected and, after one more rejection, all remaining W-017 welds of the lot are selected `100pct` and an NCR (source weld) opens.
31. **AC-Q2-31** (Q-WLD-06) **Given** J07 rejected after R1 **When** R2 is recorded without a `weld.repair2_approve` sign-off **Then** 422 `SIGNOFF_REQUIRED`; with the sign-off of a resolver (the test sets the row to user Hatem; Bilal, RAWABI-assigned, is refused for this NAJD weld by Q-RPM-07) **Then** R2 is recorded; rejected after R2 **Then** Cut Out and an NCR opens.
32. **AC-Q2-32** (Q-PRF-04) **Given** RUH-CCH (logistics) **Then** creating a MAR, pour or weld → 409 `PROFILE_INACTIVE`; creating an `ATP-SWAB` test request and an M&TE item succeeds.
33. **AC-Q2-33** (rule 41) **Given** the Arabic UI **Then** every Q2 label, list value, status, label print and PDF is in Arabic; joint ids, heat numbers and values stay LTR.

---

# Part D — Q3: logistics — receiving, storage and cold chain, stock quality, recalls, transport

Profile: logistics (temperature-controlled storage, dry storage and transportation). Every write in this part needs the project profile `logistics` (Q-PRF-04 for leftovers). In a 3PL the goods usually belong to a **customer (depositor)**; the warehouse proves that it kept them right and the owner decides on doubtful product where its contract says so (Q-EXC-09).

## D.1 Q3 settings, storage classes, products and imports

### D.1.1 Settings (registry keys)
| Key | AR label | Type | Default | Allowed |
|---|---|---|---|---|
| `reading_gap_factor` | معامل فجوة القراءات | decimal | 2.0 | 1.5–5.0 |
| `monitoring_gap_alert_minutes` | تنبيه انقطاع المراقبة | minutes | 60 | 15–1,440 |
| `manual_reading_max_age_hours` | أقدم قراءة يدوية مسموحة | hours | 72 | 1–168 |
| `excursion_auto_hold` | حجز تلقائي عند الانحراف | bool | true | — |
| `pharma_impact_all_excursions` | تقييم كل انحرافات الأدوية | bool | true | — |
| `min_remaining_shelf_life_pct` | الحد الأدنى للصلاحية المتبقية | % | 60 ASSUMPTION | 10–100 (product or customer value wins) |
| `near_expiry_days` / `near_expiry_pct` | قرب انتهاء الصلاحية | days / % of shelf life | 30 / 20 | 1–365 / 1–90 |
| `dock_dwell_max_minutes` | أقصى مدة على الرصيف | minutes | 30 ASSUMPTION | 5–180 |
| `hold_ageing_days` | تنبيه تقادم الحجز | days | 7 | 1–60 |
| `fefo_checks_per_week` | عدد فحوص FEFO الأسبوعية | int | 20 | 0–500 |
| `cycle_count_tolerance_units` | تفاوت الجرد | units | 0 | 0–100 |
| `recall_trace_target_hours` | زمن التتبع المستهدف | hours | 4 ASSUMPTION | 1–48 |
| `recall_effectiveness_target_pct` | فعالية الاستدعاء المستهدفة | % | 100.0 | 90.0–100.0 |
| `mock_recall_months` | دورية الاستدعاء التجريبي | months | 12 ASSUMPTION | 3–24 |
| `mapping_validity_months` | صلاحية دراسة التوزيع الحراري | months | 24 ASSUMPTION `[VERIFY]` WHO supplement / SFDA | 6–60 |
| `mapping_min_hours` / `mapping_max_interval_minutes` / `mapping_min_loggers` | حدود دراسة التوزيع | h / min / int | 72 / 5 / 9 ASSUMPTION `[VERIFY]` | 24–336 / 1–15 / 3–200 |
| `otif_window_minutes` | نافذة التسليم في الموعد | minutes | 60 | 0–1,440 |
| `transit_data_due_hours` | مهلة بيانات الرحلة | hours | 48 | 4–168 |
| `import_max_rows` | الحد الأقصى للصفوف | int | 200,000 | 1,000–1,000,000 |

### D.1.2 Storage classes (list SCL; defaults copied into each storage zone and editable there)
| Code | EN / AR | Range °C (min / max) | Alarm delay (min) | Deviation bands d1 / d2 (°C) | Duration bands t1 / t2 (min) | Humidity | Dispatch override allowed (`dispatch_override_allowed`) |
|---|---|---|---|---|---|---|---|
| `frozen` | Frozen / مجمد | −30 / −18 | 30 (defrost) | 3 / 6 | 120 / 480 | — | yes |
| `chilled` | Chilled / مبرد | 0 / 4 | 15 | 2 / 5 | 60 / 240 | — | yes |
| `pharma_2_8` | Medicines 2–8 °C / أدوية 2–8 | 2 / 8 | 10 | 1 / 3 | 30 / 120 | — | no |
| `ambient_controlled` | Controlled ambient 15–25 °C / محيط مضبوط | 15 / 25 | 30 | 3 / 7 | 240 / 1,440 | ≤ 65 % ASSUMPTION | yes |
| `dry` | Dry ambient / جاف | — / 30 | 60 | 3 / 7 | 480 / 2,880 | ≤ 65 % ASSUMPTION | yes |
| `dock_controlled` | Controlled dock / رصيف مبرد | 8 / 15 | 30 | 3 / 6 | 60 / 240 | — | yes |

All defaults are ASSUMPTION `[VERIFY]` against the goods owner's requirements, SFDA rules and the product labels; they are data.

### D.1.3 Products — `q_products`
sku (unique per project and owner), owner customer (`q_customers` kind depositor), description EN / AR, GTIN (optional, 8 / 12 / 13 / 14 digits with a valid check digit), storage class (SCL), range override, shelf_life_days, min_remaining_shelf_life_pct (optional), dated (true = FEFO by expiry; false = FIFO by receipt date), active. Entered or imported (Q-IMP).

### D.1.4 Imports (Q-IMP) — `q_import_batches`
Kinds: `readings` (logger files), `stock_snapshot`, `shipments`, `products`, `cycle_count`. Each batch: kind, import profile (saved column mapping: column names, date format, time zone of the file (`Asia/Riyadh` or UTC or an offset), unit °C / °F, decimal separator, logger serial column), file (attachment `q_import_file`, SHA-256), target (monitoring point, trip, mapping study, receipt), rows read / accepted / rejected, error report, imported_by / at, status `imported` · `refused` · `voided`.
- **Q-IMP-01.** The file is stored unchanged with its SHA-256; the same file again for the same target → 409 `IMPORT_DUPLICATE_FILE`.
- **Q-IMP-02.** Readings files: rows with a bad time, a value outside −80…+80 °C or 0…100 % RH, or a time already stored for the target are rejected row by row (listed with row no and reason); valid rows are stored. Snapshot, shipment and product files are all-or-nothing: any row error refuses the file (`IMPORT_ROWS_INVALID`, with the error list).
- **Q-IMP-03.** °F is converted to °C (°C = (°F − 32) × 5 ÷ 9, kept to 2 dp); times are converted to UTC from the profile's time zone.
- **Q-IMP-04.** Files over `import_max_rows` rows are refused (`IMPORT_TOO_LARGE`).
- **Q-IMP-05.** A batch may be voided by 244 within 24 h of import with a reason ≥ 20 chars (e.g. wrong point mapped); its rows leave every calculation and derived excursions are recomputed. Later, imported data are never changed (Q-STO-07).
- **Q-IMP-06.** Nothing in Phase 8 writes back to a WMS or TMS; holds are exported for the WMS (Q-HLD-08).

## D.2 Receiving inspection — فحص الاستلام (Q-RCV)

`q_receipts`:
| Field | AR label | Type | Req | Validation | Example | PDPL |
|---|---|---|---|---|---|---|
| rcv_no | رقم الاستلام | string | sys | Q-NUM | RCV-RUH-CCH-2026-01877 | none |
| site_id / dock_zone_id | الموقع / الرصيف | FK ×2 | Y | dock zone of the site | S-DC1 / Z-DOCK | none |
| customer_id / supplier_id / carrier_id | المالك / المورد / الناقل | FK ×3 | Y / N / N | Q-SHR-02 | Gulf Frozen Foods / — / CoolRoad | none |
| po_ref / asn_ref | أمر الشراء / إشعار الشحن | string(40) ×2 | N | — | PO-77812 / ASN-GFF-26-0914 | none |
| vehicle_plate / reefer_display_c | لوحة المركبة / عرض حرارة الوحدة | string(20) / decimal | N | — | 4521 RJA / −19.0 | none |
| seal_expected / seal_actual / seal_intact | الختم | string ×2 / bool | N / Y / Y | mismatch flagged (Q-RCV-06) | 0098812 / 0098812 / true | none |
| expected_at / arrived_at / unload_start / unload_end | الموعد / الوصول / بدء وانتهاء التفريغ | timestamptz ×4 | N / Y / Y / Y | order; expected_at = booked slot (feeds supplier on-time delivery, §E.3) | 06:00 / 06:10 / 06:25 / 06:48 | none |
| vehicle_check | فحص المركبة | checklist response (`receiving`) | Y | template QRCV | — | none |
| transit_data | بيانات النقل | import batch | N | logger file of the inbound trip | — | none |
| lines | البنود | list `q_receipt_lines` | Y | ≥ 1 | 6 lines | none |
| status | الحالة | enum | Y | Draft مسودة → Inspected تم الفحص → Decided مقرر; Cancelled ملغى | decided | none |

`q_receipt_lines`: product (sku), batch / lot, expiry date, production date, qty_expected (ASN), qty_received, unit, condition (`good` · `damaged` · `wet` · `crushed` · `leaking` · `pest_signs`), labels_ok (Arabic label present `[VERIFY]` SFDA labelling rules; readable barcode), product temperature (°C) with M&TE, remaining_shelf_life_pct (sys), sample inspected (count; hint from the seeded ISO 2859-1 table, general level II, single sampling `[VERIFY]`), photos, proposed decision (sys), decision (list RD), reason, NCR / claim link, hold link.
**RD — line decisions:** `accept` قبول · `accept_with_deviation` قبول مع انحراف · `quarantine` عزل · `reject` رفض.

- **Q-RCV-01.** The system proposes a line decision from criteria: `arrival_temperature` by storage class (seeded: frozen accept ≤ −18.0, deviation −18.0 < t ≤ −15.0, reject > −15.0; chilled accept −1.0…5.0, deviation 5.0 < t ≤ 7.0, reject > 7.0 or < −1.0; pharma_2_8 accept 2.0…8.0, otherwise quarantine; all ASSUMPTION `[VERIFY]`), `remaining_shelf_life` (≥ the product's, else the customer's, else `min_remaining_shelf_life_pct` → accept, else deviation), condition (damaged / leaking / pest_signs → quarantine) and labels (not ok → deviation). The worst proposal wins.
- **Q-RCV-02.** The user records the final decision. A decision better than the proposal needs a sign-off of `receipt.deviation` with a reason ≥ 20 chars (`DECISION_BETTER_THAN_CRITERIA`).
- **Q-RCV-03.** `accept_with_deviation` needs RPM `receipt.deviation`; when the line's owner has `owner_release_approval`, the owner's written approval file is also required (`OWNER_DECISION_REQUIRED`).
- **Q-RCV-04.** `quarantine` creates a hold (reason `receiving`) with the line, automatically.
- **Q-RCV-05.** `reject` needs RPM `receipt.reject` and either an NCR (source `receipt`, class major) or a supplier / carrier claim no. (`REJECT_NEEDS_NCR_OR_CLAIM`).
- **Q-RCV-06.** A seal mismatch or broken seal flags the receipt; any acceptance then needs RPM `receipt.deviation`.
- **Q-RCV-07.** Lines of storage class frozen, chilled, pharma_2_8 or dock_controlled need a product temperature with an M&TE (`MTE_REQUIRED`; Q-SHR-04 applies).
- **Q-RCV-08.** Dock dwell = unload_end − unload_start for temperature-controlled receipts; over `dock_dwell_max_minutes` gives warning `DOCK_DWELL_LONG` (counted in K-160 chip).
- **Q-RCV-09.** Quantity differences (received vs ASN) are recorded as a quantity deviation note; they are not a quality rejection and do not count in K-160.
- **Worked example QX14.** RCV-RUH-CCH-2026-01877, Gulf Frozen Foods, frozen chicken line: product −16.5 °C → deviation band; received 2026-09-14, expiry 2026-12-20, shelf life 180 days → remaining 97 ÷ 180 = **53.9 %** < 60 → deviation. Proposed **accept_with_deviation**; Reem signs `receipt.deviation` with the owner's approval file attached. A chilled yoghurt line at **+11.0 °C** (RCV-…-01902) → proposed **reject**; rejected with NCR-RUH-CCH-2026-0031.

## D.3 Storage zones, monitoring points and readings (Q-STO)

`q_storage_zones` (one per Phase 0 zone used for storage; PK = zone_id): storage_class, temp_min / temp_max / setpoint, humidity_min / humidity_max, alarm_delay_minutes, bands d1 / d2 / t1 / t2, expected interval_minutes, mapping status (sys: `mapped` until date · `not_mapped` · `remap_required`), active.
`q_monitoring_points`: code, zone, position note (from mapping: hot spot, cold spot, general), interval_minutes, logger assignments (list {mte_id, from, to}), active.
`q_readings`: target (point, trip or mapping study), measured_at (UTC), temperature_c, humidity_pct, source (`manual` · `import`), import batch, entered_by, M&TE (manual), annotation {text, by, at}, flag `probe_fault`. Unique (target, measured_at).

- **Q-STO-01.** A storage zone takes its class defaults (§D.1.2); changing range or bands is audited and sets `remap_required` when the range changes (Q-MAP-06).
- **Q-STO-02.** Manual readings (267) carry the probe's M&TE (usage recorded, Q-SHR-04). measured_at > now + 5 min → `CLOCK_SKEW`; older than `manual_reading_max_age_hours` → `READING_TOO_OLD`.
- **Q-STO-03.** A logger assigned to a point records usage for the assignment period; assigning an M&TE that is not `calibrated` or `due_soon` warns or blocks per `mte_use_policy`; Q-CAL-07 applies.
- **Q-STO-04.** **Coverage and gaps:** a reading covers [measured_at, measured_at + interval). Two consecutive readings of a point more than `reading_gap_factor` × interval apart leave the minutes between unmonitored. A zone minute is *monitored* when ≥ 1 active point of the zone covers it. A gap ≥ `monitoring_gap_alert_minutes` in a zone opens a "monitoring gap" entry and alerts 266 holders. Coverage % = monitored ÷ period minutes × 100.
- **Q-STO-05.** **Time out of range:** a zone minute is *out* when any point covering it is out of range (value < min or > max; the limits themselves are in range). TOR minutes = Σ out minutes, including transients (Q-EXC-03).
- **Q-STO-06.** The zone page shows the profile chart (C48): readings per point against the range, excursions shaded, gaps marked.
- **Q-STO-07.** Readings are never edited or deleted (only Q-IMP-05 batch void). Corrections are annotations; a `probe_fault` flag is set only through an excursion dismissal (Q-EXC-11) and keeps the value visible.

## D.4 Temperature excursions and product impact — الانحرافات الحرارية (Q-EXC)

`q_excursions`: exc_no, kind (`storage` · `transit` · `humidity`), zone or trip, started_at, ended_at (null = ongoing), duration_min, peak value and point, max_deviation (°C beyond the nearest limit), degree_minutes, severity (list ES), data_gap (bool), cause (`door_open` · `defrost` · `power_failure` · `equipment_failure` · `overload` · `loading_delay` · `probe_fault` · `unknown` · `other`), NCR link, hold link, status.
`q_excursion_impacts`: excursion, lines (owner, sku, batch, qty, location — from the hold), per line: stability evidence (file) or justification, decision (`release` · `extend_hold` · `destroy` · `return_to_owner`), owner decision file / owner contact name / date (when required).
**ES — severity:** `minor` طفيف · `major` جوهري · `critical` حرج. 

| From → To | AR | Who | Condition / error |
|---|---|---|---|
| — → Detected | مُكتشف | System | Q-EXC-01 / -02; alerts Q-EXC-04; NCR and hold Q-EXC-05 |
| Detected → Under Assessment | قيد التقييم | 268 | cause entered |
| Under Assessment → Assessed | مُقيَّم | 268 + RPM `excursion.impact` (storage-class qualifier) | Q-EXC-06…09 (`IMPACT_LINES_INCOMPLETE`, `IMPACT_EVIDENCE_REQUIRED`, `OWNER_DECISION_REQUIRED`) |
| Assessed → Under Assessment | قيد التقييم | 268 + RPM | reopened (new stock or stability information), reason ≥ 20 chars |
| Under Assessment → Closed | مغلق | 268 | an excursion for which Q-EXC-06 requires no assessment (minor, and not in a `pharma_2_8` zone while `pharma_impact_all_excursions`); "no product impact" note ≥ 20 chars |
| Assessed → Closed | مغلق | System | every line of the linked hold final and the linked NCR (if any) Closed |
| Detected / Under Assessment → Dismissed | مستبعد | 268 + RPM `excursion.impact` | Q-EXC-11 evidence; readings flagged `probe_fault`; M&TE out_of_service |

- **Q-EXC-01.** **Detection** runs after every import and manual reading, per zone (storage) or trip (transit): a run of out minutes (Q-STO-05) starts at the first out reading's time and ends at the time of the first later reading at which every covering point is in range; duration = end − start. A run with no later in-range reading is ongoing. Runs separated by fewer than `alarm_delay_minutes` of in-range minutes are one excursion.
- **Q-EXC-02.** **Severity** = the worse of: deviation level (max_deviation ≤ d1 → minor, ≤ d2 → major, > d2 → critical) and duration level (duration ≤ t1 → minor, ≤ t2 → major, > t2 → critical). degree_minutes = Σ over out readings of (deviation × that reading's covered minutes). A data gap inside the run counts as out time (conservative) and sets `data_gap`.
- **Q-EXC-03.** A run shorter than `alarm_delay_minutes` is a **transient**: stored, shown on the chart, counted in TOR, not an excursion.
- **Q-EXC-04.** A major or critical excursion alerts within 60 s of detection the 268 holders of the site and the users who resolve for `excursion.impact` with the zone's storage class as qualifier (seeded defaults: position WAREHOUSE_MGR; RESP_PHARMACIST for `pharma_2_8`) (in-app + email + push). An ongoing excursion found by a manual reading alerts the same way at once.
- **Q-EXC-05.** Major and critical excursions open an NCR (source `excursion`, class = severity, category `temperature`) and, with `excursion_auto_hold`, a hold (reason `excursion`) with the stock lines of the zone in the latest stock snapshot taken before started_at; without a snapshot, a zone-level hold that the warehouse completes with lines (Q-HLD-02).
- **Q-EXC-06.** Impact assessment is required for major and critical excursions, and for any excursion in a `pharma_2_8` zone when `pharma_impact_all_excursions`; a minor excursion elsewhere may be closed with a "no product impact" note.
- **Q-EXC-07.** The assessment covers every line of the linked hold (`IMPACT_LINES_INCOMPLETE`).
- **Q-EXC-08.** A `release` decision needs stability evidence (the owner's or manufacturer's allowed excursion, e.g. a degree-minute or time budget) or a justification ≥ 50 chars (`IMPACT_EVIDENCE_REQUIRED`).
- **Q-EXC-09.** **Goods owner's decision:** when the line's owner (`q_customers.owner_release_approval`) requires it, `release` and `destroy` need the owner's written decision file (`OWNER_DECISION_REQUIRED`). The warehouse's responsible person still signs the assessment.
- **Q-EXC-10.** An approved assessment proposes the decisions on the hold lines; the hold release itself is the `hold.release` step (Q-HLD-04), which the same person may sign when they resolve for both.
- **Q-EXC-11.** **Dismissal** (probe fault) needs evidence that the instrument was faulty (a check or calibration of the M&TE showing the error, or a second instrument's readings for the same time) and RPM `excursion.impact`; the readings get the `probe_fault` flag; the excursion leaves K-161 / K-162 (listed separately) and the M&TE is set out_of_service.
- **Q-EXC-12.** **Mean kinetic temperature** (for `ambient_controlled` and `pharma_2_8` points, monthly): MKT = (ΔH/R) ÷ (−ln(Σ e^(−ΔH/(R·Tᵢ)) ÷ n)) − 273.15, with ΔH/R = 10,000 K (ΔH = 83.144 kJ/mol) and Tᵢ in kelvin from hourly means `[VERIFY]` USP <1079.2>. MKT above the range max gives warning `MKT_ABOVE_RANGE`.
- **Worked examples. QX12** (Z-CHL1, chilled 0–4 °C, 15-min readings, 2026-09-17): 08:00 3.6 · 08:15 4.4 · 08:30 5.1 · 08:45 5.6 · 09:00 4.8 · 09:15 3.9 → run 08:15–09:15, duration **60 min** (≥ 15 alarm delay → excursion), max deviation **1.6 °C** (≤ 2 → minor), duration ≤ 60 → minor → **minor**; degree-minutes (0.4 + 1.1 + 1.6 + 0.8) × 15 = **58.5 °C·min**. **QX13** (Z-FRZ1, frozen, 2026-09-22): defrost failure, out from 02:00 to 05:30 (**210 min** > t1 120 → major), peak −13.8 °C → deviation 4.2 (> 3, ≤ 6 → major) → **major**: NCR-RUH-CCH-2026-0034 and HLD-RUH-CCH-2026-0112 with 14 lines from the 2026-09-21 23:00 snapshot. **QX15 MKT** hourly means 21.5, 22.0, 23.0, 24.5, 26.0, 27.5, 24.0 °C → arithmetic mean 24.07, **MKT 24.29 °C** (≤ 25 → no warning).

## D.5 Temperature mapping — دراسة التوزيع الحراري (Q-MAP)

`q_mapping_studies`: map_no, zone, purpose (`initial` · `periodic` · `after_change`), season (`summer` · `winter` · `n_a`), load state (`empty` · `loaded`), planned / actual start and end, interval_minutes, loggers (list {mte_id, position code, description: height and grid}), test windows (list {kind `door_open` · `power_off` · `other`, from, to}, excluded from pass / fail but reported), lead (user; competence `MAPPING-LEAD` through `COMPETENCE`), results (sys: per logger min / max / mean, % time in range; hot spot and cold spot; zone min / max), pass (sys), recommended monitoring positions, report file, status Draft مسودة → Data Loaded تم تحميل البيانات → Evaluated مُقيَّمة → Approved معتمدة (266 + RPM `mapping_study.approve`) / Rejected مرفوضة; valid_until = add_months(approval date, `mapping_validity_months`) − 1 day.

- **Q-MAP-01.** Every logger must be `calibrated` (or `due_soon`) on both the start and end dates (`MAPPING_LOGGER_NOT_CALIBRATED`), with Q-CAL-07 range coverage.
- **Q-MAP-02.** Duration ≥ `mapping_min_hours`, interval ≤ `mapping_max_interval_minutes`, loggers ≥ `mapping_min_loggers` (`MAPPING_DESIGN_INSUFFICIENT`, listing which).
- **Q-MAP-03.** Readings are imported with the study as target; evaluation computes results; pass ⇔ every logger stays within the zone range outside the test windows.
- **Q-MAP-04.** On approval, the zone becomes `mapped` until valid_until; the hot and cold spots are proposed as monitoring point positions.
- **Q-MAP-05.** Alerts at 60 / 30 / 0 days before valid_until; a zone `not_mapped` shows on the zone page and in the K-162 chip; a `pharma_2_8` zone not mapped gives a red banner on the Quality home.
- **Q-MAP-06.** A change of range, a layout change note, or an HVAC change note on the zone sets `remap_required` until a study of purpose `after_change` is approved.

## D.6 Hygiene, cleaning and pest control — النظافة ومكافحة الآفات (Q-HYG)

`q_check_schedules`: site or zone, template (quality kind, `quality_type` `hygiene` or `pest_visit`), frequency (`daily` · `weekly` · `fortnightly` · `monthly`), weekday (weekly), start date, assignee role, active. Due checks are computed on read (as DECISIONS #157): a period is *done* when a response of that template for that zone has completed_date in the period.
`q_pest_stations`: code (unique per site), zone, type (`rodent_bait` · `rodent_trap` · `insect_light_trap` · `glue_board` · `pheromone_trap` · `bird_deterrent`), location note, provider (supplier `pest_control`), active.
`q_pest_visits`: visit_no, provider, visited_at, technician name (personal), chemicals (list {product, registration no `[VERIFY]` MEWA / SFDA pesticide registration, quantity}), station results (list {station, activity `none` · `low` · `medium` · `high`, pest type `rodent` · `cockroach` · `stored_product_insect` · `flying_insect` · `bird` · `other`, bait consumed %, action}), checklist response (optional), report file.

- **Q-HYG-01.** A due check not done by the end of its period is overdue (alerts the assignee role and 266 holders the next morning); counted in K-168.
- **Q-HYG-02.** A hygiene checklist critical failure (e.g. pest evidence, product contamination, chemicals stored with food) proposes an NCR (source `hygiene_pest`) and a hold of the affected stock.
- **Q-HYG-03.** A pest station with activity on 2 consecutive visits, any `high` activity, or any activity in a zone of class chilled, frozen or pharma_2_8 proposes a quality alert and an NCR (source `hygiene_pest`); the station is marked "activity trend".
- **Q-HYG-04.** Every station must appear in each visit's results; a station missing from a visit is listed "not serviced" (`STATION_NOT_SERVICED` warning).

## D.7 Stock quality — جودة المخزون

### D.7.1 Stock snapshots and the near-expiry list (Q-STK)
`q_stock_snapshots` (imported, Q-IMP): site, as_of, rows in `q_stock_lines` (owner, sku, batch, expiry, receipt date, location, zone code, qty, unit, WMS status).
- **Q-STK-01.** The latest snapshot before a time T is "the stock at T" for excursion holds (Q-EXC-05) and FEFO checks (Q-STK-04); recall traces use Q-RCL-02's at-or-after rule instead. The screen always shows the snapshot's as_of; a snapshot older than 24 h when used gives warning `SNAPSHOT_OLD`.
- **Q-STK-02.** **Near-expiry list** (latest snapshot): `expired` (expiry < today) and `near_expiry` (expiry − today ≤ `near_expiry_days`, or remaining ≤ `near_expiry_pct` of the product's shelf life); per owner, exportable. An expired line not on a hold alerts 269 holders daily and offers "Place hold" (reason `expiry`).
- **Q-STK-03.** `q_throughput` (per site and month: units received, units dispatched, deliveries, shipments; entered or derived from imports) is the denominator for damage and complaint rates (§E.4).

### D.7.2 FEFO / FIFO checks — فحص الأقدم انتهاءً أولاً
`q_fefo_checks`: check_no, checked_at, order / pick ref, product, picked batch + expiry (or receipt date when not dated), location, eligible earliest (sys), result (`compliant` · `non_compliant` · `exception`), exception reason (`customer_allocation` · `batch_reserved` · `consignee_min_shelf_life` · `other`, note).
- **Q-STK-04.** Eligible earliest = among the latest snapshot's lines of the same owner and product, not on a Q3 hold, not expired, in zones that are not quarantine or returns, the earliest expiry (dated products) or receipt date (not dated). Compliant ⇔ picked expiry (or receipt date) ≤ eligible earliest; ties are compliant.
- **Q-STK-05.** An `exception` needs a reason and counts as compliant in K-166 when the reason is not `other`; `other` needs a note ≥ 20 chars and the 266 holder's confirmation.
- **Q-STK-06.** Fewer than `fefo_checks_per_week` checks in a week on a site appears on the Quality home (K-166 chip).

### D.7.3 Holds and quarantine — الحجز والعزل (Q-HLD)
`q_holds`: hold_no, site, reason (`excursion` · `receiving` · `damage` · `expiry` · `recall` · `pest_hygiene` · `owner_request` · `contamination` · `other`), source link, zone-level flag, segregation (`moved_to_quarantine` with location · `tagged_in_place`), segregation photo, WMS hold confirmed (bool, time), placed_by / placed_at, status. `q_hold_lines`: owner, product, batch, qty, unit, location, line status `on_hold` محجوز · `released` مُفرج عنه · `rejected` مرفوض, final outcome (`destroyed` أُتلف · `returned_to_owner` أعيد للمالك · `returned_to_supplier` أعيد للمورد), evidence.
**Hold line transitions:**

| From → To | AR | Who | Condition / error |
|---|---|---|---|
| — → On Hold | محجوز | 270 (Warehouse QC may place) or System | Q-HLD-01; segregation Q-HLD-03 |
| On Hold → Released | مُفرج عنه | 270 + RPM `hold.release` | Q-HLD-04 (`HOLD_RELEASE_BLOCKED`), Q-HLD-05 (`OWNER_DECISION_REQUIRED`) |
| On Hold → Rejected | مرفوض | 270 + RPM `hold.reject` | reason ≥ 20 chars; Q-HLD-04 blockers except an open recall (recalled lines may only be rejected) |
| Released → On Hold | محجوز | 270 | re-held on new information, reason ≥ 20 chars |
| Rejected → Destroyed / Returned to Owner / Returned to Supplier | أُتلف / أعيد للمالك / أعيد للمورد | 269 | evidence file (destruction certificate, return note) (Q-HLD-06) |

Hold status (derived): On Hold محجوز (any line on hold) → Released مُفرج عنه (all lines released) · Rejected مرفوض (all lines rejected) · Partly Released مُفرج جزئياً (mix, none on hold) → Closed مغلق (every rejected line has its final outcome evidenced).

- **Q-HLD-01.** Holds are placed by 270 holders (Warehouse QC included) or automatically: receipt quarantine (Q-RCV-04), excursion (Q-EXC-05), recall (Q-RCL-03), hygiene (Q-HYG-02).
- **Q-HLD-02.** A zone-level hold must get its lines within 24 h (alert to the placer and 266 holders); until then the whole zone shows "on hold" on the Quality home.
- **Q-HLD-03.** Segregation is recorded with a photo within 4 h of placing (alert otherwise).
- **Q-HLD-04.** **Release and reject** by line need RPM `hold.release` / `hold.reject` and are refused (`HOLD_RELEASE_BLOCKED`) while: a linked NCR exists whose disposition is not Approved; a linked excursion is not Assessed; or the batch is in an open recall (recalled lines may only be rejected).
- **Q-HLD-05.** Release of a line owned by a customer with `owner_release_approval` needs the owner's decision file (Q-EXC-09 logic).
- **Q-HLD-06.** A rejected line closes only with its final outcome and evidence (destruction certificate, return note).
- **Q-HLD-07.** Holds on hold longer than `hold_ageing_days` alert the users who resolve for `hold.release` on that hold, weekly.
- **Q-HLD-08.** The hold list exports to CSV in a WMS-friendly layout (owner, sku, batch, location, qty, hold no, status); "WMS hold confirmed" is ticked by the user after the WMS update.

### D.7.4 Damage reports, returns and cycle counts
- `q_damage_reports`: dmg_no, stage (`receiving` · `storage` · `picking` · `loading` · `delivery`), product, batch, qty, cause (`forklift` · `stacking_crush` · `packaging_failure` · `temperature` · `water` · `pest` · `other`), photos, hold link, owner notified (time). **Q-STK-07.** A damage report creates a hold (reason `damage`) unless the line is destroyed on the spot with photo evidence and owner notification; units damaged feed K-164.
- `q_returns` / `q_return_lines`: ret_no, customer, RMA ref, received_at, reason, lines {product, batch, qty, temperature history available (bool + file), condition grade `A` resaleable قابل للبيع · `B` repack إعادة تغليف · `C` hold for owner decision حجز لقرار المالك · `D` destroy إتلاف}. **Q-STK-08.** A temperature-controlled line without temperature history cannot be graded A (`COLD_RETURN_NO_HISTORY`); grade C creates a hold; grades are confirmed by RPM `return.disposition`.
- `q_cycle_counts` / `q_cycle_count_lines`: cc_no, counted_at, zones, lines {product, batch, location, system_qty, counted_qty, unit, tolerance (default `cycle_count_tolerance_units`), within_tolerance (sys), variance reason, recount qty}. **Q-STK-09.** within_tolerance ⇔ |counted − system| ≤ tolerance, using the recount when present; feeds K-165. Variances are reported; the platform never adjusts stock (Q-IMP-06).

## D.8 Recalls and mock recalls — استدعاء المنتجات (Q-RCL)

`q_recalls`: rcl_no, type (`supplier` · `regulator` · `owner` · `mock`), class (`I` · `II` · `III` `[VERIFY]` SFDA recall classes), products and batches (list), reason, external ref (e.g. SFDA notice), initiated_at, trace (sys and confirmed), trace_completed_at, consignee contacts (`q_recall_items`: consignee, qty shipped, contacted_at, method, response, qty retrieved, qty confirmed destroyed by consignee), effectiveness (sys), status (table below).

| From → To | AR | Who | Condition / error |
|---|---|---|---|
| — → Open | مفتوح | 271 | Q-RCL-01; real recalls: hold (Q-RCL-03) and NCR (Q-RCL-06) |
| Open → Traced | تم التتبع | 271 | trace (Q-RCL-02) reviewed and confirmed; trace_completed_at set |
| Traced → Recovering | قيد الاسترجاع | 271 | real recalls only; consignee contacts started |
| Recovering → Closed (real) · Traced → Closed (mock) | مغلق | 271 + RPM `recall.close` | Q-RCL-04 (`RECALL_TARGET_NOT_MET` without justification); every recalled hold line rejected with its outcome (real) |
| Open / Traced / Recovering → Cancelled | ملغى | 271 + RPM `recall.close` | reason ≥ 20 chars (e.g. withdrawn by the issuer); its holds stay for a hold decision |

- **Q-RCL-01.** Opening a recall needs ≥ 1 product and batch; type regulator needs the external ref.
- **Q-RCL-02.** **Trace** (system, from Q3 data only): received = Σ receipt lines of the batches; on hand = the latest snapshot at or after initiated_at (or the latest before it with warning `SNAPSHOT_OLD`); shipped = Σ shipment lines of the batches by consignee and date; destroyed = rejected hold lines and damage reports of the batches with outcome destroyed; unaccounted = received − on hand − shipped − destroyed. trace_time = trace_completed_at − initiated_at.
- **Q-RCL-03.** A recall (not mock) places a hold (reason `recall`) at once on every on-hand line of the batches in the snapshot used by Q-RCL-02 (the latest at or after initiated_at, else the latest before it with `SNAPSHOT_OLD`, as Q-STK-01); those lines may only be rejected (Q-HLD-04).
- **Q-RCL-04.** effectiveness % = (on hand + retrieved + confirmed destroyed by consignees + destroyed in the warehouse) ÷ received × 100 for a real recall; for a mock recall = (on hand + shipped and traced to a named consignee + destroyed) ÷ received × 100. Closing below `recall_effectiveness_target_pct` needs a justification ≥ 50 chars (`RECALL_TARGET_NOT_MET`); a trace slower than `recall_trace_target_hours` is flagged.
- **Q-RCL-05.** A site without a closed mock recall in the last `mock_recall_months` alerts 239 holders monthly; counted in the K-166 chip set.
- **Q-RCL-06.** A real recall is class `critical` for its NCR (source `recall`, auto), linked to the supplier when known.
- **Worked example QX16** (mock recall MR of batch NDC-Y-2609, 2026-09-08 09:00): received 4,800; on hand 1,150; shipped 3,620 to 14 consignees; destroyed 0 at first → accounted 4,770 → **99.4 %**; linking DMG-RUH-CCH-2026-00207 (30 units destroyed) → **100.0 %**; trace completed 11:35 → **2 h 35 min** ≤ 4 h.

## D.9 Transport — النقل (Q-TRN)

`q_trips`: trip_no, carrier (supplier `carrier`) or own fleet, vehicle (Phase 2 `vehicles` id, optional; else plate text), reefer unit serial, compartments (1 or more, each with setpoint and class), driver (worker link or name; personal), shipments (imported, linked), range (sys: per compartment, the strictest range of the classes loaded), logger M&TE ids, seal numbers, planned departure, preload response (template QRPL, `quality_type` `reefer_preload`), loading product temperatures (list {shipment, °C, M&TE}), departed_at, PODs (`q_pods`), transit readings (imported or manual, target = trip), status (table below).

| From → To | AR | Who | Condition / error |
|---|---|---|---|
| — → Planned | مخطط | 272 | shipments linked; Q-TRN-01 (`INCOMPATIBLE_LOAD`) |
| Planned → Preload Checked | تم الفحص قبل التحميل | 272 | QRPL response submitted; loading temperatures (Q-TRN-03) |
| Preload Checked → Dispatched | انطلقت | 272 (+ RPM `trip.dispatch_override` after a critical failure) | Q-TRN-02 (`PRELOAD_FAILED`, `OVERRIDE_NOT_ALLOWED`); Q-TRN-04 warning `VEHICLE_NOT_READY` |
| Dispatched → Delivered | تم التسليم | 272 | a POD for every shipment (Q-TRN-06, `POD_REQUIRED`) |
| Delivered → Closed | مغلقة | System | readings imported when a logger is named; transit excursions evaluated (Q-TRN-05, Q-TRN-07) |
| Planned / Preload Checked → Cancelled | ملغاة | 272 | reason ≥ 20 chars |

`q_pods` (per shipment): delivered_at, receiver name and role (personal), signature image or photo of the signed delivery note, seal intact, product temperature at delivery (optional, M&TE), exceptions (list {kind `shortage` · `damage` · `temperature` · `refused` · `other`, qty, note}), photos.

- **Q-TRN-01.** Products of classes that cannot share one compartment (frozen with chilled, pharma_2_8 with food) in one compartment give 422 `INCOMPATIBLE_LOAD`.
- **Q-TRN-02.** Dispatch needs a submitted pre-load checklist. Seeded critical items: pre-cooled (box temperature at loading within the compartment range, frozen ≤ setpoint + 2.0 °C ASSUMPTION `[VERIFY]`), clean and odour-free, doors / gaskets / insulation undamaged, airflow clear, logger placed (M&TE scanned), seal applied. A critical failure blocks dispatch (`PRELOAD_FAILED`) unless RPM `trip.dispatch_override` with a reason ≥ 20 chars; no override when any loaded class has `dispatch_override_allowed` = no (seeded: `pharma_2_8`) (`OVERRIDE_NOT_ALLOWED`).
- **Q-TRN-03.** Loading temperatures: ≥ 1 per shipment and class, with an M&TE; a value outside the class range stops that shipment (hold proposed).
- **Q-TRN-04.** **Link to 7b:** when the trip names a Phase 2 vehicle that has 7b readiness data, the trip shows readiness (document validity, today's pre-use check result) and the driver's authorisation status when the driver is a worker; not ready → warning `VEHICLE_NOT_READY` (7b owns readiness; Phase 8 creates no 7b record and never blocks on it).
- **Q-TRN-05.** **Transit temperature:** readings come from the trip logger file (import, target = trip) or manual entries; excursions use Q-EXC-01…03 with the compartment range and its class bands. A transit excursion of severity major or critical opens an NCR (source `trip`, class = severity) and a "notify consignee" task on the shipments delivered after its start.
- **Q-TRN-06.** **POD:** each shipment needs a POD to reach Delivered (`POD_REQUIRED`); a POD with an exception proposes an NCR (source `trip`) and lets a later customer complaint link to it.
- **Q-TRN-07.** A trip with a logger and no readings imported `transit_data_due_hours` after delivery alerts the users who resolve for `trip.dispatch_override`; the trip closes when PODs and (if a logger is named) readings are in.
- **Q-TRN-08.** **OTIF data:** an imported shipment counts for K-163 when it has promised_at and delivered_at; on time ⇔ delivered_at ≤ promised_at + `otif_window_minutes`; in full ⇔ delivered qty ≥ ordered qty on every line.

## D.10 Q3 screens

| Screen | Phone / tablet (warehouse floor, dock, cab) | Desk |
|---|---|---|
| Receiving `/quality/receiving` | Dock flow: scan or pick ASN, vehicle checklist, line cards with temperature (probe M&TE scan), expiry, condition, photos; proposed decision chip; hold / reject actions | Register with filters (owner, decision, deviation); receipt detail with sign-offs; dock dwell report |
| Storage `/quality/storage` | Zone list with live status colour (in range, excursion, gap, not mapped) | Zone settings (class, range, bands), points and logger assignments, profile chart C48 |
| Readings `/quality/readings` and Imports `/quality/imports` | Manual reading entry | Logger CSV import with profile picker, preview of the first rows, result report; import history |
| Excursions `/quality/excursions` | Alert card with "acknowledge", cause | Register; detail with chart, impact lines table, evidence, owner decision files, sign-offs |
| Mapping `/quality/mapping` | — | Study design, logger grid, import, results (min / max / mean per logger, heat-map table), approval |
| Hygiene `/quality/hygiene` and Pest `/quality/pest` | Run due checks (6d runner); pest visit entry per station | Schedules, due / overdue list; station register and trend |
| Stock `/quality/stock` (near-expiry, FEFO checks, damage, cycle counts, throughput) and Products `/quality/products` | FEFO check form with the computed eligible earliest; damage report with photo | Near-expiry list per owner; FEFO compliance; IRA report |
| Holds `/quality/holds` and Returns `/quality/returns` | Place hold, segregation photo | Hold register with ageing and blockers; line release / reject; WMS export |
| Recalls `/quality/recalls` | — | Recall wizard (batches → trace → holds → consignee contacts), effectiveness and trace time |
| Transport `/quality/transport` | Cab mode: pre-load checklist, loading temperatures, POD with signature on the device | Trip board; transit chart; OTIF |

## D.11 Q3 notifications
| Trigger | Recipient | Timing | Channel |
|---|---|---|---|
| Excursion major / critical (Q-EXC-04) | 268 holders of the site; `excursion.impact` resolvers (storage-class qualifier) | within 60 s of detection | in-app + email + push |
| Monitoring gap ≥ limit | 266 holders | at detection | in-app + push |
| Receiving rejection / deviation needing sign-off | `receipt.*` resolvers | immediately | in-app + push |
| Hold placed / zone-level hold without lines after 24 h / ageing | `hold.release` resolvers; placer | immediately / at 24 h / weekly | in-app + email |
| Expired stock not on hold | 269 holders | daily 07:12 | in-app |
| Mapping valid until in 60 / 30 / 0 days | 266 holders; `mapping_study.approve` resolvers | 07:12 | in-app + email |
| Hygiene / pest check overdue; pest activity trend | assignee role; 266 holders | next morning 07:12; at visit entry | in-app |
| Recall opened (real) | 271 holders; `recall.close` resolvers; `hold.release` resolvers of the recall hold | immediately | in-app + email + push |
| Mock recall due | 239 holders | monthly | in-app |
| No transit data after delivery | `trip.dispatch_override` resolvers | at `transit_data_due_hours` | in-app |
| Pre-load failed / override requested | `trip.dispatch_override` resolvers | immediately | in-app + push |

## D.12 Q3 errors
422 `IMPORT_ROWS_INVALID`, `IMPORT_TOO_LARGE`, `DECISION_BETTER_THAN_CRITERIA`, `OWNER_DECISION_REQUIRED`, `REJECT_NEEDS_NCR_OR_CLAIM`, `MTE_REQUIRED`, `READING_TOO_OLD`, `CLOCK_SKEW`, `IMPACT_LINES_INCOMPLETE`, `IMPACT_EVIDENCE_REQUIRED`, `MAPPING_LOGGER_NOT_CALIBRATED`, `MAPPING_DESIGN_INSUFFICIENT`, `HOLD_RELEASE_BLOCKED`, `COLD_RETURN_NO_HISTORY`, `RECALL_TARGET_NOT_MET`, `INCOMPATIBLE_LOAD`, `PRELOAD_FAILED`, `OVERRIDE_NOT_ALLOWED`, `POD_REQUIRED`; 409 `IMPORT_DUPLICATE_FILE`. Warnings: `DOCK_DWELL_LONG`, `SNAPSHOT_OLD`, `MKT_ABOVE_RANGE`, `STATION_NOT_SERVICED`, `VEHICLE_NOT_READY`.

## D.13 Acceptance criteria — Q3
1. **AC-Q3-01** (Q-IMP-01) **Given** a logger file imported for point CHL1-P2 **When** the same file is imported again **Then** 409 `IMPORT_DUPLICATE_FILE`; the stored file's SHA-256 equals the upload's.
2. **AC-Q3-02** (Q-IMP-02) **Given** a readings file with 3 bad rows out of 2,880 **Then** 2,877 rows are stored and the report lists the 3 rows; a stock snapshot with 1 bad row **Then** 422 `IMPORT_ROWS_INVALID` and nothing stored.
3. **AC-Q3-03** (Q-IMP-03) **Given** a °F file with 39.2 °F **Then** stored 4.00 °C; a file in UTC+00 at 05:15 **Then** shown 08:15 Riyadh.
4. **AC-Q3-04** (Q-IMP-05, Q-STO-07) **Given** a batch imported to the wrong point **When** Reem voids it within 24 h with a reason **Then** its rows and derived excursions disappear from KPIs; after 24 h **Then** 409; a PATCH of a reading value **Then** no route exists.
5. **AC-Q3-05** (Q-RCV-01, QX14) **Given** the frozen chicken line at −16.5 °C and 97 / 180 days remaining **Then** proposed accept_with_deviation; the yoghurt line at +11.0 °C **Then** proposed reject.
6. **AC-Q3-06** (Q-RCV-02) **Given** the yoghurt line **When** Imran records accept **Then** 422 `DECISION_BETTER_THAN_CRITERIA` unless a `receipt.deviation` sign-off with reason is given.
7. **AC-Q3-07** (Q-RCV-03) **Given** Gulf Frozen Foods with owner_release_approval **When** accept_with_deviation is signed without the owner's file **Then** 422 `OWNER_DECISION_REQUIRED`.
8. **AC-Q3-08** (Q-RCV-04, Q-RCV-05) **Given** a line decided quarantine **Then** a hold with that line exists; a reject without NCR or claim no. **Then** 422 `REJECT_NEEDS_NCR_OR_CLAIM`.
9. **AC-Q3-09** (Q-RCV-07, Q-SHR-04) **Given** a chilled line without M&TE **Then** 422 `MTE_REQUIRED`; with an overdue probe under policy warn **Then** saved with warning and a usage row.
10. **AC-Q3-10** (Q-RCV-08) **Given** unloading 06:25–07:05 for a frozen receipt **Then** warning `DOCK_DWELL_LONG` (40 > 30).
11. **AC-Q3-11** (Q-EXC-01, Q-EXC-02, QX12) **Given** QX12 readings **Then** one excursion 08:15–09:15, 60 min, max deviation 1.6, degree-minutes 58.5, severity minor; no NCR; no auto hold.
12. **AC-Q3-12** (Q-EXC-03) **Given** a run of 10 min out of range in Z-CHL1 (alarm delay 15) **Then** a transient: no excursion, no alert, 10 min in TOR.
13. **AC-Q3-13** (Q-EXC-02, Q-EXC-05, QX13) **Given** QX13 **Then** severity major, an NCR (source excursion, class major, category temperature) and HLD-…-0112 with the 14 lines of the 2026-09-21 23:00 snapshot; alerts within 60 s to Reem, Imran and Saad.
14. **AC-Q3-14** (Q-EXC-02) **Given** a frozen run peaking at −11.5 °C (deviation 6.5) for 40 min **Then** severity critical.
15. **AC-Q3-15** (Q-EXC-02) **Given** a run with a 50-min data gap inside **Then** the gap counts as out time and `data_gap` is set.
16. **AC-Q3-16** (Q-EXC-06) **Given** a minor excursion in Z-PHR1 (pharma) **Then** impact assessment is required; a minor in Z-AMB1 **Then** it may close with a "no product impact" note.
17. **AC-Q3-17** (Q-EXC-07, Q-EXC-08) **Given** HLD-…-0112 with 14 lines **When** the assessment decides 13 **Then** 422 `IMPACT_LINES_INCOMPLETE`; a release without evidence and with a 20-char note **Then** 422 `IMPACT_EVIDENCE_REQUIRED`.
18. **AC-Q3-18** (Q-EXC-09) **Given** a Gulf Frozen Foods line released without the owner's decision file **Then** 422 `OWNER_DECISION_REQUIRED`.
19. **AC-Q3-19** (Q-EXC-11) **Given** a dismissal with a calibration showing probe MTE-0051 reading +3.0 °C high **Then** the excursion is Dismissed, the readings flagged `probe_fault`, K-161 excludes it, and MTE-0051 is out_of_service.
20. **AC-Q3-20** (Q-EXC-12, QX15) **Given** QX15 hourly means **Then** MKT = 24.29 °C (2 dp) and no warning; with all values + 2 °C **Then** `MKT_ABOVE_RANGE`.
21. **AC-Q3-21** (Q-STO-04, Q-STO-05, K-162, QX18) **Given** Z-CHL1 in September with 90 unmonitored minutes and 135 out minutes **Then** monitored 43,110 min, TOR 0.31 %, coverage 99.8 %.
22. **AC-Q3-22** (Q-STO-02) **Given** a manual reading dated 80 h ago **Then** 422 `READING_TOO_OLD`; 10 min in the future **Then** 422 `CLOCK_SKEW`.
23. **AC-Q3-23** (Q-MAP-01, Q-MAP-02) **Given** a study with a logger due 2026-09-25 and an end date 2026-09-26 **Then** 422 `MAPPING_LOGGER_NOT_CALIBRATED`; a 48 h study **Then** 422 `MAPPING_DESIGN_INSUFFICIENT`.
24. **AC-Q3-24** (Q-MAP-03, Q-MAP-04) **Given** MAP-RUH-CCH-2026-0004 for Z-FRZ1 with all loggers in range except during a declared door-open window **Then** pass, and approved on 2026-07-28 Z-FRZ1 is mapped until 2028-07-27.
25. **AC-Q3-25** (Q-MAP-05, Q-MAP-06) **Given** Z-PHR1 with mapping valid until 2026-10-20 **Then** the 30-day alert was sent 2026-09-20; changing its range sets `remap_required`.
26. **AC-Q3-26** (Q-HYG-01) **Given** a weekly hygiene schedule on Z-CHL1 with no response in the week ending 2026-10-03 **Then** it is overdue and the assignee role is alerted on 2026-10-04 07:12.
27. **AC-Q3-27** (Q-HYG-03) **Given** station RB-14 in Z-DRY1 with activity on two consecutive visits **Then** a quality alert and an NCR are proposed; any activity in Z-CHL1 proposes them at the first visit.
28. **AC-Q3-28** (Q-STK-02) **Given** the latest snapshot **Then** expired and near-expiry lines are listed per owner; an expired line not on hold triggers the daily alert and "Place hold".
29. **AC-Q3-29** (Q-STK-04) **Given** batch B1 (expiry 2026-11-05) available and B2 (2026-11-30) picked **Then** non_compliant; with B1 on hold **Then** compliant.
30. **AC-Q3-30** (Q-HLD-04) **Given** an excursion hold whose NCR is Open (HLD-…-0112 before its assessment) **When** Saad releases a line **Then** 422 `HOLD_RELEASE_BLOCKED`; after the excursion is Assessed and the NCR disposition Approved **Then** released with a sign-off.
31. **AC-Q3-31** (Q-HLD-02, Q-HLD-03) **Given** a zone-level hold placed 2026-10-05 09:00 without lines **Then** an alert at 2026-10-06 09:00; no segregation photo by 13:00 on the day of placing **Then** an alert at 13:00.
32. **AC-Q3-32** (Q-HLD-06) **Given** a rejected line **When** the hold is closed without a destruction or return document **Then** 422.
33. **AC-Q3-33** (Q-STK-08) **Given** a chilled return line without temperature history **When** graded A **Then** 422 `COLD_RETURN_NO_HISTORY`.
34. **AC-Q3-34** (Q-STK-09) **Given** 400 counted lines of which 388 within tolerance **Then** IRA 97.0 % (K-165).
35. **AC-Q3-35** (Q-RCL-02, Q-RCL-04, QX16) **Given** QX16 **Then** effectiveness 99.4 % before and 100.0 % after linking the damage report; trace time 2 h 35 min within target.
36. **AC-Q3-36** (Q-RCL-03) **Given** a real recall of batch NDC-Y-2611 with 600 units on hand **Then** a hold of those lines exists and releasing them → 422 `HOLD_RELEASE_BLOCKED`.
37. **AC-Q3-37** (Q-TRN-01) **Given** frozen and chilled shipments in a one-compartment trip **Then** 422 `INCOMPATIBLE_LOAD`.
38. **AC-Q3-38** (Q-TRN-02) **Given** a pre-load with box temperature −12 °C for a frozen compartment set at −20 °C **When** dispatched **Then** 422 `PRELOAD_FAILED`; with a `trip.dispatch_override` by Naveen (TRANSPORT_SUP) **Then** dispatched; with a pharma compartment **Then** 422 `OVERRIDE_NOT_ALLOWED`.
39. **AC-Q3-39** (Q-TRN-04) **Given** a trip naming a Phase 2 vehicle whose 7b Istimara expired **Then** warning `VEHICLE_NOT_READY` and no 7b record is created.
40. **AC-Q3-40** (Q-TRN-05, Q-TRN-06) **Given** TRP-RUH-CCH-2026-00921 with a transit excursion of severity major **Then** an NCR (source trip) and a notify-consignee task exist; a shipment without POD **Then** the trip cannot become Delivered (`POD_REQUIRED`).
41. **AC-Q3-41** (Q-TRN-08, QX17) **Given** the September shipments of Appendix A.6 **Then** K-163 = 93.2 %.
42. **AC-Q3-42** (Q-PRF-04) **Given** ANIA-EXP (construction) **Then** creating a receipt → 409 `PROFILE_INACTIVE`.
43. **AC-Q3-43** (rule 41) **Given** the Arabic UI **Then** every Q3 label, storage class, status, alert, PDF and export header is in Arabic; temperatures, batch numbers and times stay LTR, and negative temperatures render with the minus sign before the digits in both directions.

---

# Part E — Q4: documents, audits, suppliers, KPIs, SPC, COPQ, AI, report packs

Q4 runs in wave 3 from `claude/quality-pre-q4` (Q0–Q3 merged, handover §5), so it may read every Phase 8 table and edit Q0 files and the 6d / 6g / KPI / AI files named in §3.3.

## E.1 Q4 settings and document control (light) — ضبط الوثائق

### E.1.1 Settings (registry keys)
| Key | AR label | Type | Default | Allowed |
|---|---|---|---|---|
| `doc_review_months` | دورية مراجعة الوثائق | months | 24 ASSUMPTION | 6–60 |
| `doc_revision_scheme` | نظام ترقيم المراجعات | enum | `letters_then_numbers` (drafts A, B, …; approved 0, 1, …) | `letters_then_numbers` · `numbers` |
| `read_ack_days` | مهلة الإقرار بالاطلاع | days | 7 | 1–30 |
| `q_audit_frequency` | تكرار التدقيق حسب المخاطر | {high, medium, low} audits per year | 2 / 1 / 0.5 ASSUMPTION | 0.25–4 |
| `q_audit_report_days` | مهلة إصدار تقرير التدقيق | days | 7 | 3–30 |
| `mgmt_review_months` | دورية مراجعة الإدارة | months | 12 | 3–12 |
| `supplier_reeval_months` | دورية إعادة تقييم الموردين | months | 12 | 3–36 |
| `supplier_score_period` | فترة بطاقة الأداء | enum | `quarter` | `month` · `quarter` |
| `supplier_score_weights` / anchors / bands | الأوزان / المراجع / الفئات | JSON | §E.3 | weights 0–100; bands increasing |
| `spc_min_subgroups` | الحد الأدنى للمجموعات الفرعية | int | 20 | 8–50 |
| `pareto_include_observations` | تضمين الملاحظات في باريتو | bool | false | — |
| `dpmo_processes` | تعريف الفرص | JSON | §E.6 | — |
| warning thresholds: `ncr_ontime_warning_pct`, `ftpr_warning_pct`, `test_fail_warning_pct`, `tor_warning_pct`, `transport_compliance_warning_pct` | حدود الإنذار | % | 80.0 / 85.0 / 5.0 / 0.50 / 98.0 ASSUMPTION | 0–100 |

KPI targets (quality objectives, ISO 9001 6.2) live in `q_kpi_targets`: project, KPI id, target, valid_from; edited by 239; shown on tiles (RAG) and in packs.

### E.1.2 Documents
`q_documents`: doc_no (Q-NUM), type (list DT), title EN / AR, profile, discipline or process, owner user, current revision (sys), review_due_on (sys), status (sys, from the current revision).
**DT — document types (prefix):** `pqp` Project Quality Plan خطة الجودة للمشروع (PQP) · `quality_manual` دليل الجودة (QM) · `procedure` إجراء (PRC) · `work_instruction` تعليمات عمل (WI) · `sop` إجراء تشغيل قياسي (SOP) · `method_statement` بيان طريقة العمل (MS) · `specification` مواصفة (SPC) · `form` نموذج (FRM) · `other` أخرى (DOC).
`q_document_revisions`: rev code, file (PDF required to approve), source file (optional), change summary, effective_date, reviewers and approver (sys, from sign-offs), status (table below; review sign-offs happen while For Review and do not change the state).

| From → To | AR | Who | Condition / error |
|---|---|---|---|
| — → Draft | مسودة | 273 | new document, or new revision copied from the current approved one |
| Draft → For Review | قيد المراجعة | 273 | PDF attached (`DOCUMENT_FILE_REQUIRED`) |
| For Review → Draft | مسودة | 274 + RPM `document.review` or `document.approve` | returned, comment ≥ 20 chars |
| For Review → Approved | معتمدة | 274 + RPM `document.approve` | ≥ 1 `document.review` sign-off; Q-RPM-06 (`SOD_CONFLICT`); previous approved revision → Superseded; acknowledgement tasks (Q-DOC-05) |
| Approved → Superseded | مستبدلة | System | a later revision approved |
| Approved → Obsolete | ملغاة | 239 | reason ≥ 20 chars; the document is withdrawn |
`q_doc_distribution`: document, members (roles, positions, engagements, users), ack_required. `q_doc_acks`: revision, user, acked_at.

- **Q-DOC-01.** Revision codes follow `doc_revision_scheme`; the first approved revision is 0 (or 1 with `numbers`).
- **Q-DOC-02.** Approval needs the PDF, ≥ 1 sign-off of `document.review` (approved or approved with comments), then `document.approve`; the author cannot review or approve (Q-RPM-06).
- **Q-DOC-03.** An approved revision is immutable (`DOCUMENT_IMMUTABLE`); a new revision starts from the current one; approving it supersedes the previous. Superseded files stay downloadable with a banner and the file name suffix `-SUPERSEDED`.
- **Q-DOC-04.** review_due_on = add_months(approval date, `doc_review_months`) − 1 day; alerts to the owner at 30 / 0 days; an overdue document stays valid and is flagged (K-159).
- **Q-DOC-05.** **Read and acknowledge:** approving a revision with ack_required creates one task per distribution member (resolved at approval); due in `read_ack_days`; one reminder at the due date; ack % per revision is shown (275).
- **Q-DOC-06.** Records cite documents by revision through `q_links` (e.g. ITP → MS Rev.2). When the cited revision is superseded, open citing records show "newer revision available".
- **Q-DOC-07.** **Transmittals** (`q_transmittals`, `q_transmittal_items`): trm_no, to (engagement, supplier, customer or an external organisation name and email), purpose (`for_approval` · `for_review` · `for_information` · `for_construction` · `as_built`), items (document revisions or Phase 8 records such as ITPs and MARs), sent_at, method (`email` · `portal` · `hand`), response due, response received (date, name), per-item response code A / B / C / D, cover sheet PDF (EN / AR, Hijri date). "Send by email" uses the email outbox with attachments (D-280, 20 MB limit) to the external address.
- **Q-DOC-08.** Not an EDMS: no drawing register, markup, check-in / check-out or folder tree (handover §4).

## E.2 Quality audits and management review (Q-AUD, Q-MRV)

### E.2.1 Audits on the 6d engine
Quality audits are rows of 6d `field_audits` with a new column `domain` (`hse` default · `quality`), new audit types (`qms_internal` تدقيق داخلي لنظام إدارة الجودة · `process_quality` تدقيق عملية أو منتج · `supplier_quality` تدقيق مورد · `subcontractor_quality` تدقيق جودة مقاول باطن), `auditee_supplier_id` and `process_ids`. Answers, scoring, grades, findings (`field_findings`, grades AF) and the report renderer are 6d's. `q_processes`: code, name EN / AR, owner user, profile, risk (`high` · `medium` · `low`), linked documents. `q_audit_programme_lines`: project, year, subject (process, supplier, engagement or clause set), risk, planned month, audit link, status `planned` · `scheduled` · `done` · `postponed` (reason) · `cancelled`.

- **Q-AUD-01.** Domain `quality` audits use capabilities 276 / 277 instead of 6d 194 / 195, templates of kind `quality` with `quality_type` `q_audit` or `supplier_audit`, and the Phase 8 numbering (QAU).
- **Q-AUD-02.** **Independence and competence** (ISO 19011): the lead auditor and team are not the owner of an audited process, not employed by the auditee engagement or supplier, and not the author of the audited documents' current revisions (`SOD_CONFLICT`); the lead auditor is checked against competence `QMS-AUDITOR` through `COMPETENCE` (policy).
- **Q-AUD-03.** Items carry ISO 9001 clause references; ratings map to grades as 6d AUD-2. At issue: each `major_nc` opens an NCR (source `q_audit_finding`, class major) and each `minor_nc` an NCR (class minor), with the clause in the requirement text; observations and OFIs create a CA (source `quality_audit`) only when the issuer asks. No 6d HSE CA is created for domain `quality`.
- **Q-AUD-04.** Issue by a 277 holder ≠ lead auditor (RPM `q_audit.issue`); report PDF EN / AR with Hijri date (6d report document); not issued within `q_audit_report_days` of fieldwork end → alerts as 6d AUD-5.
- **Q-AUD-05.** Domain `quality` audits never enter K-114, K-115 or the 6d programme lines (6d code filters `domain = hse`); quality audits count in K-158.
- **Q-AUD-06.** **Programme:** each active process of the project gets lines per year by risk (`q_audit_frequency`: 2 → planned months 3 and 9; 1 → month 6; 0.5 → every other year, month 6) ASSUMPTION, editable; supplier and subcontractor audits are added by hand. A line is *done on time* when an issued audit linked to it has fieldwork_end ≤ the last day of its planned month.
- **Q-AUD-07.** Seeded templates: `Q9K` ISO 9001:2015 internal audit (56 items, clauses 4–10, rating_0_3; critical: 8.5.1 controlled conditions, 8.7 nonconforming outputs, 10.2 corrective action), `QSUP` supplier audit (30 items), `QGDP` cold-chain warehouse audit (40 items, logistics).

### E.2.2 Management review — مراجعة الإدارة
`q_management_reviews`: mrv_no, period covered, held_on, chair, attendees (users and external names), inputs (one entry per ISO 9001 9.3.2 heading: status of previous actions; changes in issues; customer satisfaction and feedback; quality objectives; process performance and conformity; nonconformities and corrective actions; monitoring and measurement results; audit results; performance of external providers; adequacy of resources; actions on risks and opportunities; opportunities for improvement — each a note or "not applicable"), KPI snapshot (sys, frozen), outputs (decisions: improvement opportunities, QMS changes, resource needs; each optionally a CA, source `quality_review`), minutes PDF, status `draft` مسودة → `held` عُقدت → `minutes_issued` صدر المحضر (277 + RPM `management_review.approve`).
- **Q-MRV-01.** Held needs every input heading answered (`MRV_INPUTS_INCOMPLETE`).
- **Q-MRV-02.** The KPI snapshot (K-141…K-169 of the covered period, with targets) is frozen at Held; later recalculation never changes the minutes.
- **Q-MRV-03.** No review held for `mgmt_review_months` → alert to 239 holders.

## E.3 Supplier evaluation and quality scorecards (Q-SUP)

`q_supplier_evaluations`: sev_no, supplier, kind (`initial` · `periodic` · `for_cause`), method (`questionnaire` · `audit` (linked quality audit) · `document_review` · `trial_order`), criteria (list {criterion, weight, score 0–100}), total (sys, weighted mean), recommendation (`approve` · `conditional` · `reject` · `suspend`), conditions, evaluated_at, status (table below).

| From → To | AR | Who | Condition / error |
|---|---|---|---|
| — → Draft | مسودة | 278 | — |
| Draft → Submitted | مُقدَّم | 278 | ≥ 1 criterion with weight > 0; recommendation set |
| Submitted → Approved | معتمد | 279 + RPM `supplier_evaluation.approve` | Q-RPM-06 (`SOD_CONFLICT`); sets next_evaluation_due (Q-SUP-02) |
| Submitted → Draft | مسودة | 279 + RPM | returned, comment ≥ 20 chars |
| Draft / Submitted → Cancelled | ملغى | 278 | reason ≥ 20 chars |
`q_supplier_scores`: supplier, period, metric values and points, score, band, recommendation, status `provisional` → `final` (System, 10 days after period end).

- **Q-SUP-01.** Q4 registers a `SUPPLIER_GATES` blocker: pending_approval → approved needs an approved evaluation with recommendation `approve` within the last 12 months (`conditional` for the conditional status) (`SUPPLIER_EVALUATION_REQUIRED`); labs also show Q-SHR-03 accreditation status.
- **Q-SUP-02.** next_evaluation_due = add_months(last approved evaluation date, `supplier_reeval_months`) − 1 day; overdue alerts 278 holders; status does not change by itself ASSUMPTION.
- **Q-SUP-03.** **Scorecard metrics** (per supplier per period; data from Q2 and Q3; a metric without data is left out and weights are re-normalised):

| # | Metric | Formula | Good / bad anchor | Weight |
|---|---|---|---|---|
| M1 | Acceptance | lines (Q3 receipts) and MIRs (Q2) decided `accept` without deviation ÷ decided × 100 | 100 / 90 | 30 |
| M2 | NCR rate | NCRs with this supplier opened in period ÷ deliveries (receipts + MIRs) × 100 | 0 / 5 | 20 |
| M3 | On-time delivery | receipts with arrived_at ≤ expected_at + `otif_window_minutes` ÷ receipts with expected_at × 100 | 98 / 80 | 20 |
| M4 | Test conformity | passed ÷ (passed + failed) test results linked to the supplier's MIRs × 100 | 100 / 90 | 15 |
| M5 | Responsiveness | supplier responses (SCAR) received by due ÷ requested × 100 | 100 / 50 | 10 |
| M6 | Documents | deliveries with complete certificates ÷ deliveries × 100 | 100 / 90 | 5 |

  points = 6g `calc.points(v, good, bad)` (linear, clipped 0–100); score = Σ wᵢ·pointsᵢ ÷ Σ wᵢ (1 dp); band by 6g `calc.band`: A ≥ 85.0 · B ≥ 70.0 · C ≥ 50.0 · D < 50.0 ASSUMPTION.
- **Q-SUP-04.** Band C asks the supplier for an improvement plan (task to the 278 holder); band D recommends suspension (alert to the 279 resolvers); no automatic status change.
- **Q-SUP-05.** A supplier linked to a contractor (`contractor_id`) shows its latest quality score on the contractor page as information only; it never enters the 6g HSE scorecard.
- **Worked example QX19** (Riyadh Readymix, Q3 2026): M1 97.5 → 75.00; M2 1.2 → 76.00; M3 91.0 → 61.11; M4 95.8 → 58.00; M5 100 → 100.00; M6 no data (left out). Score = (30 × 75 + 20 × 76 + 20 × 61.111 + 15 × 58 + 10 × 100) ÷ 95 = 6,862.22 ÷ 95 = **72.2** → band **B**.

## E.4 KPI catalogue (continues 7b; K-141…K-169)

General (Q-KPI): computed by the backend KPI engine from stored records (K-R1); periods and filters as Phase 1 (D-2), plus profile, supplier, discipline, storage class, test type. Records before `quality_start_date`, voided records and dismissed excursions are excluded. Rounding half-up at output only: % 1 dp (K-162 and K-164 3 dp shown as 2 / 3 dp), money 2 dp, rates 2 dp; comparisons use unrounded values. A KPI with a zero denominator shows "—". Contractor filters include descendants (K-R5); supplier filters use `supplier_id`. KPIs of a profile are shown for any period that has records (Q-PRF-05).

| ID | Metric (EN / AR) | Formula | Profile | Unit | Better |
|---|---|---|---|---|---|
| K-141 | **First-time pass rate** / نسبة النجاح من أول مرة | n(IRs with round 1 decided in period and result approved / approved_with_comments) ÷ n(IRs with round 1 decided in period, result ∈ approved, approved_with_comments, rejected, not_ready) × 100; chips: waived, short notice, paper sign-off % | C | % | higher |
| K-142 | IR rejection rate / نسبة رفض طلبات الفحص | n(rounds decided in period with result rejected or not_ready) ÷ n(rounds decided in period, any of the four results) × 100 | C | % | lower |
| K-143 | NCRs raised / تقارير عدم المطابقة الصادرة | n(NCRs opened in period) by class; chip: open at as_of | both | count | — |
| K-144 | **NCR ageing** / تقادم التقارير المفتوحة | open NCRs at as_of in buckets 0–30, 31–60, 61–90, > 90 days (Q-NCR-18); mean age | both | count, days | lower |
| K-145 | NCR closure time / زمن إغلاق التقارير | median closure_days of NCRs closed in period; chip: mean | both | days | lower |
| K-146 | **NCR on-time closure** / إغلاق التقارير في الموعد | n(NCRs with target_close_date in period and ≤ as_of, closed on or before it) ÷ n(NCRs with target_close_date in period and ≤ as_of) × 100; chip: quality CA on-time closure (K-41 formula over quality source types) | both | % | higher |
| K-147 | Repeat NCR rate / نسبة التقارير المتكررة | n(NCRs opened in period with repeat_of) ÷ n(NCRs opened in period) × 100 | both | % | lower |
| K-148 | **Cost of poor quality** / تكلفة الجودة الرديئة | Σ amount of cost lines of NCRs opened in period (gross); chips: internal / external, recovered, net, COPQ % = gross ÷ `q_work_value` of the period × 100; months with NCRs not closed are "provisional" | both | SAR, % | lower |
| K-149 | **DPMO and sigma level** / العيوب لكل مليون فرصة ومستوى سيجما | §E.6 per process | both | DPMO, σ | lower DPMO |
| K-150 | Pareto of defect causes / باريتو أسباب العيوب | NCR count by category (switch: cause_category 6M; IR reject_category), sorted, cumulative %, vital few (§E.6) | both | count, % | — |
| K-151 | Material rejection rate / نسبة رفض المواد | n(MIRs decided in period with rejected_qty > 0) ÷ n(MIRs decided in period) × 100; chip: by quantity | C | % | lower |
| K-152 | Test failure rate / نسبة فشل الاختبارات | n(test requests with verdict fail, results entered in period) ÷ n(with verdict pass or fail) × 100, by test type; chip: pours with sampling short | both | % | lower |
| K-153 | Weld repair rate / نسبة إصلاح اللحام | Σ rejected first examinations ÷ Σ first examinations × 100 (Q-WLD-07); chips: by length, lots with NDT shortfall, lapsed WPQs | C | % | lower |
| K-154 | **Calibration compliance** / الالتزام بالمعايرة | n(active M&TE with check_kind ≠ none, not out_of_service, status calibrated or due_soon at as_of) ÷ n(active M&TE with check_kind ≠ none, not out_of_service) × 100; chips: overdue, open OOT reviews | both | % | higher |
| K-155 | Competence compliance / الالتزام بالكفاءة | n(person-requirement pairs met at as_of) ÷ n(applicable pairs) × 100; chip: warn-policy overrides in period | both | % | higher |
| K-156 | Punch closure / إغلاق النواقص | n(items closed on or before target with target in period, ≤ as_of) ÷ n(items with target in period, ≤ as_of) × 100; chips: open A, open B | C | % | higher |
| K-157 | Supplier quality score / درجة جودة الموردين | mean of the latest final scores of suppliers used in the period; chip: count by band | both | points | higher |
| K-158 | Quality audit programme compliance / الالتزام ببرنامج تدقيق الجودة | lines done on time ÷ lines with planned month in period and ≤ as_of × 100 (Q-AUD-06); chips: major / minor NC from quality audits issued in period | both | % | higher |
| K-159 | Document control / ضبط الوثائق | n(approved current documents not past review_due_on at as_of) ÷ n(approved current documents) × 100; chip: read-ack completion % (acks ÷ required acks of revisions whose ack due ≤ as_of) | both | % | higher |
| K-160 | **Receiving rejection rate** / نسبة رفض الاستلام | n(receipts decided in period with ≥ 1 line rejected) ÷ n(receipts decided in period) × 100; chips: deviation rate, quarantine rate, line rejection %, dock dwell over limit | L | % | lower |
| K-161 | **Excursions per zone-month** / الانحرافات لكل منطقة شهرياً | n(storage excursions started in period, not dismissed) ÷ n(zone-months monitored in period) (a zone-month = a storage zone with ≥ 1 monitored minute in the month); by severity; chip: transit excursions | L | per zone-month, 2 dp | lower |
| K-162 | **Time out of range** / الزمن خارج النطاق | Σ out minutes ÷ Σ monitored minutes × 100 over storage zones (pooled, Q-STO-04 / -05); chips: coverage %, zones not mapped, gaps | L | %, 2 dp | lower |
| K-163 | On time in full (OTIF) / التسليم في الموعد وكاملاً | n(shipments delivered in period, on time and in full, Q-TRN-08) ÷ n(shipments delivered in period with promised_at and delivered_at) × 100; "—" when no data | L | % | higher |
| K-164 | Damage rate / نسبة التلف | units damaged (damage reports in period) ÷ units handled (Σ throughput received + dispatched) × 100; chip: ppm | L | %, 3 dp | lower |
| K-165 | Inventory record accuracy / دقة سجلات المخزون | lines within tolerance ÷ lines counted × 100 (cycle counts in period) | L | % | higher |
| K-166 | FEFO compliance / الالتزام بالأقدم انتهاءً أولاً | (compliant + exception with a listed reason) ÷ FEFO checks in period × 100; chips: checks vs weekly target, near-expiry lines, expired not on hold, last mock recall | L | % | higher |
| K-167 | Transport temperature compliance / الالتزام الحراري في النقل | n(trips delivered in period with transit data and no transit excursion) ÷ n(trips delivered in period with transit data) × 100; chips: trips without data, pre-load fails, overrides | L | % | higher |
| K-168 | Hygiene and pest check compliance / الالتزام بفحوص النظافة والآفات | due checks done in their period ÷ due checks whose period ended in period and ≤ as_of × 100; chips: mean hygiene score, stations with activity | L | % | higher |
| K-169 | Customer complaints / شكاوى العملاء | n(complaints received in period); rate per 1,000 shipments (logistics; "—" without throughput); chips: justified %, median response days, observations raised | both | count, rate | lower |

**Worked examples (backend unit tests must match):**
- **QX2 — IRs, ANIA-EXP, September 2026:** 120 IRs had round 1 decided in September; 96 approved or approved with comments → K-141 = 96 ÷ 120 = **80.0 %**. Rounds decided in September: 120 first rounds + 21 re-inspections = 141; rejected or not ready: 24 + 3 = 27 → K-142 = 27 ÷ 141 = 19.148… = **19.1 %**. Not counted: 4 waived W rounds (chip), 2 cancelled IRs without a decided round.
- **QX17 — OTIF, RUH-CCH, September 2026:** 1,250 shipments delivered with data; on time 1,190; in full 1,210; both 1,165 → **93.2 %**.
- **QX18 — time out of range:** Z-CHL1 September: period 43,200 min, unmonitored 90 → monitored **43,110**; out 135 (the 60-min QX12 excursion and 75 transient minutes) → 135 ÷ 43,110 = **0.31 %**; coverage 99.79 → **99.8 %**. Pooled over the 7 storage zones: monitored 301,980, out 640 → **0.21 %**.
- **QX20 — damage rate:** 412 units damaged ÷ 1,860,000 handled = **0.022 %** (221.5 ppm).
- **QX21 — K-161:** 5 storage excursions (Z-CHL1 minor 09-17, Z-FRZ1 major 09-22, Z-DOCK 3 minor) ÷ 7 zone-months = **0.71**.

## E.5 Statistical process control (Q-SPC)

`q_spc_charts`: code, title EN / AR, type (`xbar_r` · `imr` · `p`), source (registry list SPCS: `conc_strength_28d` (subgroup = one set's specimens, per mix), `slump` (I-MR), `dft_spot` (X-bar/R, subgroup = the 3 gauge readings of a spot), `compaction_pct` (I-MR), `zone_daily_mean_temp` (I-MR, per zone), `ir_rejection_weekly` (p: defectives = rejected or not-ready rounds, n = rounds per week), `receiving_rejection_weekly` (p: receipts with a rejected line, n = receipts per week)), filters (mix, zone, discipline, test type), subgroup size n (2–10 for X-bar/R), baseline (`frozen` = subgroups chosen by the Quality Engineer, or `rolling` = last 25), spec limits (from a criterion), owner.

Constants (ISO 7870-2):

| n | A2 | D3 | D4 | d2 |
|---|---|---|---|---|
| 2 | 1.880 | 0 | 3.267 | 1.128 |
| 3 | 1.023 | 0 | 2.574 | 1.693 |
| 4 | 0.729 | 0 | 2.282 | 2.059 |
| 5 | 0.577 | 0 | 2.114 | 2.326 |
| 6 | 0.483 | 0 | 2.004 | 2.534 |
| 7 | 0.419 | 0.076 | 1.924 | 2.704 |
| 8 | 0.373 | 0.136 | 1.864 | 2.847 |
| 9 | 0.337 | 0.184 | 1.816 | 2.970 |
| 10 | 0.308 | 0.223 | 1.777 | 3.078 |

- **Q-SPC-01. X-bar / R:** for k baseline subgroups, X̿ = mean of subgroup means, R̄ = mean of ranges; UCL_X = X̿ + A2·R̄, LCL_X = X̿ − A2·R̄; UCL_R = D4·R̄, LCL_R = D3·R̄.
- **Q-SPC-02. I-MR:** MRᵢ = |xᵢ − xᵢ₋₁|; UCL = X̄ + 2.66·MR̄, LCL = X̄ − 2.66·MR̄; UCL_MR = 3.267·MR̄.
- **Q-SPC-03. p-chart:** p̄ = Σ defectives ÷ Σ n over the baseline; for each point i, UCLᵢ / LCLᵢ = p̄ ± 3·√(p̄(1 − p̄) ÷ nᵢ), LCL floored at 0, UCL capped at 1.
- **Q-SPC-04.** With fewer than `spc_min_subgroups` baseline subgroups the limits are labelled "provisional"; with fewer than 8, no limits are drawn.
- **Q-SPC-05. Signals** (Western Electric; zones at 1σ and 2σ from the centre, σ = (UCL − CL) ÷ 3, per point for p-charts): rule 1 — a point beyond a control limit; rule 2 — 2 of 3 consecutive points beyond 2σ on the same side; rule 3 — 4 of 5 consecutive beyond 1σ on the same side; rule 4 — 8 consecutive on the same side of the centre. Rules 2–4 apply to X-bar, I and p charts; R and MR charts use rule 1 only.
- **Q-SPC-06.** A signal is listed on the chart and notifies the chart owner, who may raise a quality observation; no NCR is opened automatically.
- **Q-SPC-07. Capability** (X-bar/R or I-MR with spec limits, ≥ `spc_min_subgroups` baseline subgroups and no rule-1 signal in the baseline): σ̂ = R̄ ÷ d2 (I-MR: MR̄ ÷ 1.128); Cp = (USL − LSL) ÷ 6σ̂; Cpk = min(USL − μ, μ − LSL) ÷ 3σ̂, one-sided with a single limit. Labelled "short-term (within-subgroup)".
- **Q-SPC-08.** Only verified, not-voided results are plotted; an amended result plots its latest version and marks the point.
- **Worked examples. QX22** (CONC-CYL C40 mix, 20 sets of n = 3): X̿ = 46.80 MPa, R̄ = 3.10 → UCL_X = 46.80 + 1.023 × 3.10 = **49.97**, LCL_X = **43.63**; UCL_R = 2.574 × 3.10 = **7.98**, LCL_R = 0; σ̂ = 3.10 ÷ 1.693 = 1.831; LSL = 40 → Cpk = (46.80 − 40) ÷ (3 × 1.831) = **1.24**. **QX23** (ir_rejection_weekly, baseline p̄ = 27 ÷ 141 = 0.1915): a week with n = 35 → UCL **0.391**, LCL **0**; n = 40 → UCL **0.378**, LCL **0.005**.

## E.6 COPQ, DPMO, sigma level and Pareto

- **Q-SIX-01. COPQ** = internal failure costs + external failure costs of NCRs (Q-COST-02); prevention and appraisal costs are not recorded (COPQ, not total cost of quality). `q_work_value` (project, month, value of work done or revenue in SAR, entered by 239) gives COPQ %.
- **Q-SIX-02. DPMO** per process = defects ÷ (units × opportunities per unit) × 1,000,000, with processes defined as data in `dpmo_processes` (seeded):

| Process | Unit | Opportunities per unit | Defect |
|---|---|---|---|
| `ir_inspection` | IR round (round ≥ 1) | applicable scored checklist items of the round | non-compliant scored answer |
| `mir_inspection` | MIR | applicable scored checklist items | non-compliant scored answer |
| `receiving` | receipt line | 4 (temperature, shelf life, condition, labels) | each failed check |
| `picking_fefo` | FEFO check | 1 | non-compliant |
| `delivery` | shipment | 2 (on time, in full) | each miss |
| `inventory` | counted line | 1 | outside tolerance |

- **Q-SIX-03. Sigma level** (short-term, with the conventional 1.5 σ shift) = Φ⁻¹(1 − DPMO ÷ 10⁶) + 1.5, where Φ⁻¹ is the inverse standard normal (Python `statistics.NormalDist().inv_cdf`); DPMO 0 → shown "> 6.0"; 2 dp. Check values: 66,807 → 3.00; 6,210 → 4.00; 233 → 5.00; 3.4 → 6.00.
- **Q-SIX-04. Pareto:** categories sorted by count (ties by code), cumulative % = running sum ÷ total × 100; the *vital few* are the smallest leading set whose cumulative % ≥ 80.0.
- **Worked examples. QX24** (ANIA-EXP IR rounds, September): defects 31, opportunities 4,820 → DPMO = 31 ÷ 4,820 × 10⁶ = **6,431.5** → σ = **3.99**. **QX25** (ANIA-EXP NCRs opened in September, 14): workmanship 6 (42.9 %), material 3 (64.3 %), design_documentation 2 (78.6 %), testing_failure 1 (85.7 %), dimensional 1 (92.9 %), other 1 (100.0 %) → vital few = the first **4** categories. **QX26** (COPQ, ANIA-EXP September): gross **186,450.00** (internal 171,200.00, external 15,250.00), recovered 22,600.00; work value 48,500,000.00 → COPQ **0.38 %**.

## E.7 Dashboard, charts, warnings and expiring items

- **Quality KPIs page** `/quality/kpis` and the Quality home tiles (profile-aware; RAG against `q_kpi_targets`): construction — K-141 (chip K-142), K-143 / K-144, K-148, K-152, K-153, K-154, K-156; logistics — K-160, K-161 / K-162, K-163, K-164, K-165, K-167, K-168; shared — K-146, K-149, K-155, K-157, K-158, K-159, K-169. The Phase 1 HSE dashboard is unchanged.
- **Quality band** (live, Quality home): stop-use alerts; open critical NCRs; containment overdue; IRs awaiting inspection today; holds on hold (and zone-level holds); ongoing excursions; M&TE overdue; steps waiting for me.
- **Charts:** C42 NCRs by month stacked by class with the open-count line; C43 Pareto bars with the cumulative line and an 80 % marker; C44 NCR ageing buckets by class; C45 COPQ by month stacked by cost type with the COPQ % line; C46 K-141 and K-142 by month by discipline; C47 SPC chart (limits, centre, signal markers); C48 zone temperature profile (readings by point, range band, excursion shading, gaps); C49 excursion heat grid (zone × month, worst severity); C50 supplier scores ranked with band colours; C51 sigma level by process. All from the KPI engine only.
- **Warnings** (monthly job, day 2 07:24, per project): **E26 NCR backlog** — K-146(M) < `ncr_ontime_warning_pct`, or ≥ 1 major / critical NCR older than 90 days at month end, or containment overdue at month end. **E27 First-time quality (construction)** — K-141(M) < `ftpr_warning_pct`, or K-152(M) > `test_fail_warning_pct`, or K-153(M) > `repair_rate_alert_pct`. **E28 Cold chain (logistics)** — a critical excursion in M, or K-162(M) > `tor_warning_pct`, or a storage zone not mapped or a monitoring logger overdue at month end, or K-167(M) < `transport_compliance_warning_pct`. T13 returns them with numerators and denominators, never names.
- **ExpiringItemKind** (Phase 1 action panel and expiring-items endpoint): `q_mte_calibration_due`, `q_wpq_continuity`, `q_competence_expiry`, `q_document_review`, `q_mapping_validity`, `q_supplier_evaluation`, `q_ncr_target`.

## E.8 Report packs and exports (Q-RPT)

- **Q-RPT-01.** Report packs reuse 6g `rp_packs` (prepare, review, issue, distribution lists, schedules, email delivery, re-issue) with new pack types: `QMR` monthly quality report (both profiles; sections by profile), `QNCR` NCR register pack, `QSUP` supplier scorecard pack, `QMRV` management review minutes. Prepare and issue need 280.
- **Q-RPT-02.** Every Quality PDF (packs, forms, dossiers, certificates of conformity-type outputs) is rendered EN and AR with the 6g renderer and shows the issue date in Gregorian and Umm al-Qura Hijri (`app.core.hijri`, D-303), whatever the project's `show_hijri`; SBC or standard references print as stored.
- **Q-RPT-03.** QMR contents: KPI summary against targets; NCRs (new, closed, open, ageing, Pareto, repeats, top 5 open by age); COPQ; construction: IRs, tests, welding, punch, M&TE; logistics: receiving, excursions, TOR and MKT per zone, mapping status, holds, recalls, transport, OTIF, damage, IRA, hygiene; competence; audits and management review; supplier scores; complaints; actions. Charts are rendered as tables (the renderer has no chart drawing).
- **Q-RPT-04.** Exports go through the 6g dataset registry. Each part registers its own datasets in `DATASETS` (Q0: `quality_ncrs`, `quality_ncr_costs`, `quality_observations`, `quality_complaints`, `quality_suppliers`, `quality_mte`; Q1: `quality_itps`, `quality_irs`, `quality_punch`; Q2: `quality_mars`, `quality_mirs`, `quality_tests`, `quality_welds`, `quality_wpqs`, `quality_calibrations`, `quality_competence`; Q3: `quality_receipts`, `quality_excursions`, `quality_readings_hourly`, `quality_holds`, `quality_recalls`, `quality_trips`, `quality_fefo`, `quality_cycle_counts`; Q4: `quality_documents`, `quality_audits`, `quality_supplier_scores`); Viewer / Client gets aggregates only (EX-9), costs and personal columns follow P8-2.
- **Q-RPT-05.** Read-only licence mode allows exports and PDFs (D-290); report pack issue is a write and is refused.

## E.9 AI tools (Q-AI; T26–T29)

- **T26 `get_quality_kpis`** (project_ids, period, profile, filters {site, zone, engagement, include_descendants, supplier, discipline, storage_class, test_type}, metrics K-141…K-169, group_by {month, week, discipline, contractor, supplier, category, cause_category, storage_class, zone, test_type, process}) → aggregates only.
- **T27 `search_ncrs`** (project_ids, filters {status, class, category, cause_category, source_type, supplier, engagement, opened_from / to, overdue, repeat}, limit ≤ 50) → ncr_no, title (P1-8 scanned), class, status, category, cause_category, source_type, responsible contractor name, supplier name, age days, target date, repeat flag, cost_gross only when the user holds 242; never person names, finding or RCA texts, photos.
- **T28 `get_spc_status`** (chart codes or all, period) → type, centre and limits, provisional flag, last 25 points, signals (rule and date), Cp / Cpk.
- **T29 `get_cold_chain_summary`** (project_ids, period, zones) → excursions by zone and severity, TOR, coverage, MKT, mapping validity, open holds from excursions, transport compliance.
- **Q-AI-01.** Every tool checks 238 per project; Viewer / Client gets T26, T28, T29 aggregates and no T27. **Q-AI-02.** No person names, signatures or contact data reach the AI layer (P6, P8-4). **Q-AI-03.** AI limits and the licence AI count are unchanged (D-292); read-only mode blocks the assistant (D-290). **Q-AI-04.** T13 returns E26–E28.

## E.10 Seed consolidation (Q4)

Each part seeds its own records through `SEEDS` (Appendix A). Q4 adds the cross-part links that need several parts (e.g. dossier sections, supplier scores from Q2 and Q3 data, KPI targets, documents, audits, the management review) and a backend test `tests/quality/q4/test_seed_kpis.py` that asserts every value of Appendix A.8 for September 2026; where a generator differs, Q4 adds records in its own seed file only and records the difference in its decisions.

## E.11 Q4 screens, notifications and errors

| Screen | Phone | Desk |
|---|---|---|
| Documents `/quality/documents`, Transmittals `/quality/transmittals` | "My acknowledgements" list, read and acknowledge | Register (type, rev, status, review due); revision workflow; distribution and ack %; transmittal builder and cover PDF |
| Audits `/quality/audits`, Programme `/quality/audit-programme` | 6d conduct runner (domain quality) | Plan, team, independence check, issue, findings → NCRs; programme grid (process × month) |
| Management reviews `/quality/management-reviews` | — | Input headings with KPI snapshot, outputs → CAs, minutes PDF |
| Supplier scores `/quality/supplier-scores` (+ tabs on the supplier page) | — | Evaluations; scorecards by period with metric drill-down; ranking C50 |
| KPIs `/quality/kpis`, SPC `/quality/spc`, Reports `/quality/reports` | Tiles | Tiles with targets, charts C42–C51, SPC chart builder and signals, 6g pack screens filtered to Quality types |

Notifications: document review due (owner, 30 / 0 days); ack due and reminder (members); transmittal response overdue (sender); audit line due 30 / 0 days (process owner, lead auditor); audit report overdue (lead, 239); supplier re-evaluation due (278); supplier band D (279 resolvers); SPC signal (chart owner); management review due (239); E26–E28 (239 holders, QA/QC managers; monthly).
Errors: 422 `DOCUMENT_FILE_REQUIRED`, `MRV_INPUTS_INCOMPLETE`, `SUPPLIER_EVALUATION_REQUIRED`, `SOD_CONFLICT`, `SPC_SOURCE_INVALID`; 409 `DOCUMENT_IMMUTABLE`.

## E.12 Acceptance criteria — Q4
1. **AC-Q4-01** (Q-DOC-02) **Given** PQP Rev.B for review authored by Hatem **When** Hatem approves **Then** 422 `SOD_CONFLICT`; approval without any review sign-off **Then** 422; without a PDF **Then** 422 `DOCUMENT_FILE_REQUIRED`.
2. **AC-Q4-02** (Q-DOC-01, Q-DOC-03) **Given** the PQP's Rev.1 approved **When** Rev.2 is approved **Then** Rev.1 is superseded and downloads with the `-SUPERSEDED` suffix; editing Rev.2 **Then** 409 `DOCUMENT_IMMUTABLE`.
3. **AC-Q4-03** (Q-DOC-04) **Given** a procedure approved 2026-10-06 **Then** review_due_on 2028-10-05; alerts at 2028-09-05 and 2028-10-05.
4. **AC-Q4-04** (Q-DOC-05) **Given** distribution role qc_inspector with ack_required **Then** each inspector has a task due in 7 days; acks raise the ack % shown; a second ack is idempotent.
5. **AC-Q4-05** (Q-DOC-06) **Given** an ITP linked to MS Rev.2 **When** MS Rev.3 is approved **Then** the ITP shows "newer revision available".
6. **AC-Q4-06** (Q-DOC-07) **Given** a transmittal by email to an external address **Then** an outbox row with the cover PDF and files exists; per-item codes A–D are recorded on response.
7. **AC-Q4-07** (Q-AUD-01, Q-AUD-05) **Given** a `qms_internal` audit issued in September **Then** it is absent from K-114, K-115 and the 6d programme, and counts in K-158; Noura (194 / 195 only) cannot plan it (403).
8. **AC-Q4-08** (Q-AUD-02) **Given** process RCV owned by Imran **When** Imran is lead auditor of an audit covering RCV **Then** 422 `SOD_CONFLICT`.
9. **AC-Q4-09** (Q-AUD-03) **Given** an audit with 2 `major_nc` and 3 `minor_nc` **When** issued **Then** 5 NCRs (source `q_audit_finding`, 2 major, 3 minor) with clause references, and no HSE CA.
10. **AC-Q4-10** (Q-AUD-04) **Given** the lead auditor issuing **Then** 422 `SOD_CONFLICT`; another resolver issues **Then** EN and AR PDFs with a Hijri date.
11. **AC-Q4-11** (Q-AUD-06) **Given** a high-risk process **Then** lines in months 3 and 9; an audit with fieldwork_end on the last day of month 9 is on time, a day later is not.
12. **AC-Q4-12** (Q-MRV-01, Q-MRV-02) **Given** a management review with one heading empty **When** set Held **Then** 422 `MRV_INPUTS_INCOMPLETE`; once Held, its KPI snapshot stays the same after new NCRs are added for that period.
13. **AC-Q4-13** (Q-SUP-01) **Given** a supplier in pending_approval without an approved evaluation **When** approved **Then** 422 `SUPPLIER_EVALUATION_REQUIRED`.
14. **AC-Q4-14** (Q-SUP-03, QX19) **Given** QX19 data **Then** score 72.2, band B, M6 left out and weights re-normalised.
15. **AC-Q4-15** (Q-SUP-04) **Given** a supplier score of 48.0 **Then** band D, a suspension recommendation alert, and the supplier status unchanged.
16. **AC-Q4-16** (Q-SUP-05) **Given** a supplier linked to contractor RAWABI **Then** the contractor page shows the quality score and RAWABI's 6g HSE scorecard is unchanged.
17. **AC-Q4-17** (K-141, K-142, QX2) **Given** the seed **Then** ANIA-EXP September K-141 = 80.0 %, K-142 = 19.1 %.
18. **AC-Q4-18** (K-146, K-144) **Given** the seed **Then** K-146 = 80.0 % and K-144 buckets 8 / 2 / 1 / 0 for ANIA-EXP at 2026-09-30.
19. **AC-Q4-19** (K-148, QX26) **Given** the seed **Then** K-148 gross 186,450.00, internal 171,200.00, external 15,250.00, COPQ 0.38 %.
20. **AC-Q4-20** (Q-SIX-02, Q-SIX-03, QX24) **Given** 31 defects in 4,820 opportunities **Then** DPMO 6,431.5 and sigma 3.99; DPMO 6,210 → 4.00; 0 → "> 6.0".
21. **AC-Q4-21** (Q-SIX-04, QX25) **Given** the September NCRs **Then** the Pareto lists 6 categories with cumulative 42.9 / 64.3 / 78.6 / 85.7 / 92.9 / 100.0 and vital few = 4.
22. **AC-Q4-22** (Q-SPC-01, Q-SPC-07, QX22) **Given** the 20 sets **Then** UCL_X 49.97, LCL_X 43.63, UCL_R 7.98, Cpk 1.24.
23. **AC-Q4-23** (Q-SPC-03, QX23) **Given** p̄ 0.1915 **Then** n = 35 gives UCL 0.391 and LCL 0; n = 40 gives LCL 0.005.
24. **AC-Q4-24** (Q-SPC-04) **Given** 12 subgroups **Then** limits are "provisional"; 6 subgroups **Then** no limits.
25. **AC-Q4-25** (Q-SPC-05) **Given** 8 consecutive points above the centre **Then** a rule-4 signal; one point above UCL **Then** rule 1; 2 of 3 beyond 2σ on the same side **Then** rule 2; the chart owner is notified and no NCR is created.
26. **AC-Q4-26** (K-160…K-169, Appendix A.8) **Given** the seed **Then** RUH-CCH September K-160 1.9 %, K-161 0.71, K-162 0.21 %, K-163 93.2 %, K-164 0.022 %, K-165 97.0 %, K-166 97.0 %, K-167 98.9 %, K-168 95.0 %, K-169 3 (2.40 per 1,000).
27. **AC-Q4-27** (K-161, Q-EXC-11) **Given** a dismissed excursion in September **Then** K-161 and K-162 exclude it and list it separately.
28. **AC-Q4-28** (§E.7) **Given** September 2026 **Then** E27 is raised for ANIA-EXP (K-141 80.0 < 85.0), no E26 for either project, and no E28 for RUH-CCH; adding a critical excursion on 2026-09-25 **Then** E28 is raised.
29. **AC-Q4-29** (Q-RPT-01, Q-RPT-02) **Given** a QMR pack for September **Then** it issues through the 6g flow with EN and AR PDFs, both showing the Gregorian and Hijri issue dates even when `show_hijri` is false on the project.
30. **AC-Q4-30** (Q-RPT-04, P8-2) **Given** Sarah exports `quality_ncrs` **Then** she receives aggregates only; Hatem's export has rows and an `export` audit entry; cost columns are absent for users without 242.
31. **AC-Q4-31** (Q-AI-01, Q-AI-02) **Given** "which suppliers caused most NCRs this quarter?" **Then** T26 groups by supplier and returns names and counts; "who raised NCR-…-0044?" **Then** no person name is returned; Sarah calling T27 **Then** refused.
32. **AC-Q4-32** (T29) **Given** "how did the cold rooms perform in September?" **Then** T29 returns per-zone excursions, TOR and MKT matching K-161 / K-162 / QX15.
33. **AC-Q4-33** (§E.7) **Given** the logistics project **Then** the Quality KPIs page shows logistics and shared tiles only; ANIA-EXP shows construction and shared tiles; the Phase 1 dashboard is unchanged.
34. **AC-Q4-34** (rule 41) **Given** the Arabic UI **Then** every Q4 label, KPI name, chart axis, pack and AI answer frame is Arabic; numbers, SAR amounts and σ values stay LTR.

---

## 4. Jobs (registry `JOBS`; wired once into `app/scheduler.py` by Q0)

Each part registers its functions in the shared job slots; every function is idempotent (each record and step alerted once, `alerts_sent` lists as earlier phases).

| Job | Time (Riyadh) | Q0 | Q1 | Q2 | Q3 | Q4 |
|---|---|---|---|---|---|---|
| `quality_daily` | 00:21 (after `field_daily`) | NCR effectiveness proposals, containment and target overdue flags | — | M&TE status, WPQ continuity, competence expiry, specimen due | mapping validity, near-expiry list, due checks, hold ageing, zone-level holds without lines, transit data due, mock recall due | document review dates, supplier re-evaluation, score finalisation |
| `quality_alerts` | 07:12 | pending-step reminders, overdue NCR / complaint alerts | IR scheduling and comments overdue | M&TE, OOT, test overdue alerts | expired-not-on-hold, hygiene overdue | document acks, audit lines |
| `quality_weekly` | Sunday 07:12 | — | punch overdue digest | quarantine ageing | hold ageing | — |
| `quality_monthly` | day 2, 07:24 | — | — | — | — | E26–E28, supplier scores of closed periods, management review due |

Excursion detection, auto-NCRs and auto-holds run synchronously at import or reading entry (within 60 s), not in a job.

## 5. Changes required in earlier specs (applied by the package named; the integrator updates the version lines and change logs)

| Spec | New version | Change | Applied by |
|---|---|---|---|
| `0-foundation.md` | v1.7 | §3.1 project type `logistics`; §3.8 roles qa_qc_manager, quality_engineer, qc_inspector, warehouse_qc, responsible_person (Q-ROL-01…05); §5.10 capability rows 238–280 by reference to §A.11; rule 14 note: an HSE Officer cannot assign quality roles | Q0 |
| `1-dashboard.md` | v1.13 | §3.8 CA source types `quality_ncr`, `quality_observation`, `quality_complaint`, `quality_audit`, `quality_review`; due-days provider and verifier rule for those sources (Q-CAP-03, -04); quality CAs excluded from K-40…K-43 and the action-panel CA counts; CA register `domain` filter; control-level labels for quality sources (Q-CAP-05); `ExpiringItemKind` values §E.7; AI tools T26–T29, T13 returns E26–E28; charts C42–C51 on Quality pages | Q0 (CA and KPI exclusion), Q4 (AI, charts, expiring kinds) |
| `2-access-permits.md` | — | No change: hook providers read by Q-CPT-01; vehicles read by Q-TRN-04 | — |
| `4-third-party-cert.md` | — | No rule change. Seed adds cert types `ndt_rt`, `ndt_ut`, `ndt_mt`, `ndt_pt`, `cwi` through `cert_types` when absent; suppliers may link a TPI | Q2 (seed) |
| `5-training.md` | — | No rule change. Seed adds courses `CONC-FIELD-TECH`, `MAPPING-LEAD`, `ISO9001-IA`, `GDP-BASIC` | Q2 (seed) |
| `6d-field-assurance.md` | v1.5 | §3.1 template kind `quality`, columns `quality_type`, `sector_profiles`; capabilities 192 / 193 do not apply to kind `quality` (240 / 239 do); §3.4 response owner types of §A.7; quality responses excluded from K-34…K-36 and K-110…K-117; §3.7 `field_audits.domain`, quality audit types, `auditee_supplier_id`, `process_ids`; K-114, K-115 and programme lines filter `domain = hse` | Q0 (templates, responses), Q4 (audits) |
| `6g-scorecard-reports.md` | v1.1 | Dataset registry accepts Phase 8 datasets (`DATASETS` hook); pack types QMR, QNCR, QSUP, QMRV; contractor page shows the linked supplier quality score as information | Q0 (hook), Q4 (packs, panel) |
| `7b-fleet-driver.md` | — | No change (read only, Q-TRN-04) | — |

## 6. Integration notes (package I)

Cross-package tests the integrator adds (handover §7.5), each referring to the rules it proves:
1. Failed CONC-CYL test linked to an IR → NCR (Q-TST-06) → CA (Q-CAP-02) → IR shows the failure; dossier blocked (Q-DOS-03 e) until the NCR closes.
2. Pour started against a rejected pre-pour hold IR → 422 (Q-TST-12 with Q1's `HOLD_CHECKS`).
3. Calibration out of tolerance (Q-CAL-04) lists IR measurements (Q1), test sampling (Q2) and receiving temperatures and logger readings (Q3) → one item decided `ncr`.
4. Excursion → NCR → hold → impact assessment → NCR disposition approved → hold release (Q-EXC-05…10, Q-HLD-04).
5. MIR rejected → quarantine → NCR reject_return → quarantine returned → NCR closed (Q-MAT-05, -07, Q-NCR-15).
6. Competence `block` refuses an IR inspector (Q-IR-07) and a mapping lead (Q-MAP) through Q2's provider.
7. Supplier gate (Q4) refuses approval without an evaluation; MAR (Q2) and receipt (Q3) warn on a non-approved supplier.
8. KPIs count records of every part (Appendix A.8 for both projects); quality CAs absent from K-41 / K-42.
9. Read-only licence: every Quality write → 403 `LICENCE_READ_ONLY`; exports, PDFs and the dossier download still work.
10. Profile switch (Q-PRF-04) across all parts: other-profile creates refused, open records finishable.

## 7. Open questions for Turki (defaults in place; nothing blocks the build)

| # | Question | Default used |
|---|---|---|
| 1 | May a contractor's own QA/QC sign IRs and NCR closures for its own work (self-certification)? | No (`own_tree_allowed` false); a project can allow it per matrix row |
| 2 | Paper sign-off for external people (consultant signs the paper IR) allowed by default? | Yes, for every step, with the scan required and the share counted |
| 3 | NCR timing: containment 24 / 72 / 168 h and close targets 21 / 30 / 30 days (critical / major / minor)? | As stated, editable |
| 4 | Quality CA due days 14 / 30 / 45 / 60 and quality CAs kept out of HSE KPIs K-40…K-43? | Yes |
| 5 | Concrete acceptance per project: ACI 318 / SBC 304 cylinders or BS EN 206 cubes? | ANIA-EXP cylinders (ACI); both rule sets seeded |
| 6 | Storage class ranges and severity bands (chilled 0–4 °C, pharma 2–8 °C, frozen ≤ −18 °C) and arrival-temperature limits? | Table §D.1.2 and Q-RCV-01, all `[VERIFY]` |
| 7 | Do logistics customers need to approve releases after excursions or deviations (3PL owner approval)? | Per customer flag; seeded on for Gulf Frozen Foods and Sahm Pharma |
| 8 | Medicines in the logistics profile: is a Responsible Pharmacist position needed for 2–8 °C zones? | Yes, position seeded and used for pharma steps |
| 9 | Temperature mapping: validity 24 months, ≥ 72 h, ≥ 9 loggers, ≤ 5-min interval? | As stated, `[VERIFY]` |
| 10 | Supplier register org-wide (shared by projects) rather than per project? | Org-wide, like contractors |
| 11 | COPQ = failure costs only, with labour SAR 85 / h and plant SAR 250 / h? | Yes |
| 12 | Quality KPIs on the main HSE dashboard too? | No; own Quality pages and home |
| 13 | Record retention: project life + 10 years (construction), 5 years (logistics)? | Yes, `[VERIFY]` |
| 14 | Licence: should Quality become a separately sold module? | On in every bundle; an optional `modules` list in the licence payload can switch it off later (D-319) |

---

## Appendix A — Seed data (fictional; `seed_fake = true`; emails `@example.com`, mobiles `+96650000xxxx`)

### A.1 Principles, projects and users
- Clock `HSE_CLOCK_AT` = 2026-10-06T10:00:00+03:00. Each part seeds its own records through `SEEDS` (`app/seed_quality.py` runs after `seed_scorecard_data`); nothing here changes earlier-phase KPI values. RUH-CCH is created by the Quality seed only. Known impact: `backend/tests/test_auth.py:294` asserts `len(sarah["projects"]) == 2`; Q0 updates it to 3 (Sarah is also Viewer on RUH-CCH). Q0 runs `test_auth.py`, `test_org.py`, `test_scoping.py`, `test_kpi_engine.py` and the data-completeness and leading-warning tests after seeding, because a project with no workforce or incident data may add completeness warnings org-wide; RUH-CCH either gets monthly workforce rows of 0 hours or is excluded from the HSE completeness job, and Q0 records the choice in D-320…D-329.
- **Construction:** ANIA-EXP (existing airport project), profile `construction`, `quality_start_date` 2026-01-01, `show_hijri` true.
- **Logistics:** new project **RUH-CCH** "Riyadh Cold Chain Hub — Al-Sulay" / "مركز الرياض لسلسلة التبريد — السلي", type `logistics`, client Al-Wahat Logistics Co. (fictional) / شركة الواحة للخدمات اللوجستية, Riyadh, start 2025-11-01, active, Hijri on, default language ar; profile `logistics`, `quality_start_date` 2026-01-01. Site **S-DC1** Distribution Centre 1 / مركز التوزيع 1; contractor **WAHAT** Al-Wahat Logistics Co. / شركة الواحة للخدمات اللوجستية (CR 1010000007, category other, approved) engaged tier 1 on RUH-CCH.

| User (EN / AR) | Email | Mobile | Project · role · scope / position |
|---|---|---|---|
| Hatem Al-Shehri / حاتم الشهري | hatem.shehri@example.com | +966500000301 | ANIA-EXP · qa_qc_manager (PMC, no engagement) |
| Bilal Qureshi / بلال قريشي | bilal.qureshi@example.com | +966500000302 | ANIA-EXP · quality_engineer · engagement RAWABI |
| Joseph Mathew / جوزيف ماثيو | joseph.mathew@example.com | +966500000303 | ANIA-EXP · qc_inspector · engagement RAWABI |
| Abdullah Al-Dossary / عبدالله الدوسري | abdullah.dossary@example.com | +966500000304 | ANIA-EXP · responsible_person · position CONSULTANT_RE |
| Sultan Al-Mutlaq / سلطان المطلق | sultan.mutlaq@example.com | +966500000305 | ANIA-EXP · responsible_person · position CLIENT_REP |
| Arun Pillai / آرون بيلاي | arun.pillai@example.com | +966500000306 | ANIA-EXP · qc_inspector · engagement NAJD (welding inspector, competence CWI) |
| Rania Al-Zahrani / رانيا الزهراني | rania.zahrani@example.com | +966500000308 | ANIA-EXP · quality_engineer (PMC, no engagement; resolves for the default quality_engineer steps such as `test_request.verify`, `calibration.accept`, `wpq.approve`) |
| Mazen Al-Harbi / مازن الحربي | mazen.harbi@example.com | +966500000307 | ANIA-EXP · qc_inspector (PMC, no engagement; resolves for S points through the default `ir.inspect` S row) |
| Reem Al-Mutairi / ريم المطيري | reem.mutairi@example.com | +966500000311 | RUH-CCH · qa_qc_manager |
| Imran Siddiq / عمران صديق | imran.siddiq@example.com | +966500000312 | RUH-CCH · warehouse_qc |
| Saad Al-Anazi / سعد العنزي | saad.anazi@example.com | +966500000313 | RUH-CCH · responsible_person · position WAREHOUSE_MGR |
| Lama Al-Qarni / لمى القرني | lama.qarni@example.com | +966500000314 | RUH-CCH · responsible_person · position RESP_PHARMACIST |
| Naveen Kumar / نافين كومار | naveen.kumar@example.com | +966500000315 | RUH-CCH · warehouse_qc · position TRANSPORT_SUP |

Faisal (HSE Manager) has every capability org-wide; Sarah (Viewer) is also assigned viewer_client on RUH-CCH. Each quality user has a linked Phase 2 worker record (for competence checks), without ID numbers beyond the Phase 2 fake pattern.

### A.2 Libraries (org-wide)
- **Criteria** (Published v1): `COVER-40` (target_tolerance 40 ± 5 mm), `FORM-TOL` (max 5 mm in 3 m), `SLUMP-100` (rule slump_astm_c94, target 100), `CONC-TEMP-32` (max 32 °C `[VERIFY]` project spec), `CURE-7D` (text), `STRIKE-70` (min 70 % f'c), `CONC-ACI-40` (rule aci318_strength, f'c 40), `CONC-ACI-32` (f'c 32), `CONC-EN206-50` (rule en206_strength, fck 50), `CORE-ACI-40` (rule aci318_cores), `COMP-95` and `COMP-98` (min 95 / 98 %), `DFT-125-200` (rule sspc_pa2), `HYDRO-1.5` (rule pressure_hold, factor 1.5, hold 10 min `[VERIFY]` ASME B31.3), `TORQUE-M20` (target_tolerance 400 ± 20 N·m, illustrative), arrival temperatures `ARR-FROZEN`, `ARR-CHILLED`, `ARR-PHARMA` (rule arrival_temperature, Q-RCV-01), `RSL-60` (rule remaining_shelf_life, 60 %), `PRECOOL-FRZ` (max setpoint + 2.0 °C).
- **Test types:** the 22 of §C.2.1 with specimen plans (CONC-CYL: 2 at 7 d, 2 at 28 d, 1 spare; CONC-CUBE: 3 at 7 d, 3 at 28 d).
- **Quality checklists** (kind `quality`, Published by Faisal 2026-04-01): `QSTC-FW` formwork (12 items), `QSTC-RB` reinforcement before pour (16 items; critical: cover, bar size and spacing, laps), `QSTC-PR` pour (10), `QSTL-WV` weld visual (12), `QMEP-PT` pressure test (10), `QPUN` punch walkdown (free items), `QMIR` material delivery (14; critical: certificate matches material), `QRCV` receiving vehicle check (15; critical: reefer running and at setpoint, seal intact, no pest signs), `QRPL` reefer pre-load (12; critical items of Q-TRN-02), `QHYG` warehouse hygiene (20), `QPST` pest visit (10), `QRET` return inspection (8), `Q9K` (56), `QSUP` (30), `QGDP` (40).
- **Competence requirements:** `CONC-FIELD-TECH` (training course CONC-FIELD-TECH, ACI field technician grade I or equivalent `[VERIFY]`), `NDT-RT-L2` / `NDT-UT-L2` (personnel certificates `ndt_rt` / `ndt_ut`, level ≥ 2, ISO 9712), `CWI` (personnel certificate `cwi`), `MAPPING-LEAD` (course MAPPING-LEAD), `QMS-AUDITOR` (course ISO9001-IA), `GDP-BASIC` (course GDP-BASIC, warehouse QC).
- **Suppliers** (org-wide): `RMX` Riyadh Readymix Concrete Co. (material_supplier, approved) · `ARS` Arabian Rebar & Steel Co. (material_supplier, approved) · `GULFPIPE` Gulf Pipes Industries (manufacturer, **suspended**, reason "2 HDPE rejections Q3 — test data") · `SAHEL` Al-Sahel Waterproofing Est. (material_supplier, approved) · `LAB-RGM` Riyadh Geo-Materials Laboratory (testing_lab, approved; accreditation SAC ISO/IEC 17025 no. TL-0451-TEST, scope CONC-CYL, CONC-CUBE, SLUMP, PROCTOR, FDT-SC, CBR — not CONC-CORE; valid to 2027-05-31) · `CAL-NMS` Najd Metrology Services (calibration_lab, approved; SAC ISO/IEC 17025 CL-0219-TEST) · `DNDT` Desert NDT Services (ndt_provider, approved) · `COOLRD` CoolRoad Transport Est. (carrier, conditional: "logger data to be sent within 24 h") · `SHIELD` Shield Pest Control (pest_control, approved) · `BRIGHT` Bright Hygiene Services (cleaning, approved) · `NDCF` Najd Dairy Factory (shipper, approved). Contacts are fake (`<code>.qa@example.com`, `+9665000004nn`).

### A.3 ANIA-EXP set-up
- Positions: CONSULTANT_RE (Abdullah), CONSULTANT_INSP (none), CLIENT_REP (Sultan). Matrix = §A.4.2 defaults. Numbering = defaults. `delay_rate_sar_day` 12,000.00.
- Systems: `SYS-T3-HVAC` Terminal 3 HVAC (HVC), `SYS-T3-FPS` Terminal 3 fire protection (FPS), `SYS-APR-DRN` apron drainage (PLB, zone Z-APR-21).
- Customers: `ANC` Al-Noor Airport Company (client).
- ITPs (Approved): `ITP-ANIA-EXP-STC-001` Rev.2 (§B.3.2, RAWABI, Z-PIERB; Rev.0 and Rev.1 Superseded), `ITP-ANIA-EXP-STL-001` Rev.1 structural steel welding (NAJD, Pier B roof), `ITP-ANIA-EXP-AFP-001` Rev.0 asphalt surfacing (GULFPAVE, Z-APR-21, Z-TWB), `ITP-ANIA-EXP-HVC-001` Rev.0 ductwork and pressure tests (RAWABI, SYS-T3-HVAC).
- M&TE (selected): `MTE-0012` concrete thermometer (calibrated, due 2027-02-14), `MTE-0015` DFT gauge (**overdue**, due 2026-09-30), `MTE-0021` torque wrench (calibrated), `MTE-0030` total station (calibrated), `MTE-0031` nuclear density gauge (calibrated; note NRRC licence `[VERIFY]`), `MTE-0007` slump cone (verification, monthly); 48 active items with a check kind, 46 compliant at 2026-09-30.
- Floor plan "Pier B Level 1" (current, 4,200 × 2,800 px) with 12 pins.

### A.4 ANIA-EXP records, September 2026 (generator targets and named records)
- **IRs:** 120 IRs with round 1 decided in September (96 approved or approved with comments, 22 rejected, 2 not ready); 21 re-inspection rounds decided (18 approved, 3 rejected); 4 waived W rounds; 2 cancelled without a decided round; checklist answers in decided rounds: 4,820 applicable scored items, 31 non-compliant (QX24). Named: **IR-ANIA-EXP-2026-00412** (STC-001 point 30, `Level 3 slab, grid C14–C20`, Joseph; round 1 2026-09-14 rejected "spacers missing", NCR not raised; round 2 2026-09-15 approved by Abdullah); **IR-ANIA-EXP-2026-00455** (point 50, pour witness 2026-09-01, approved with one comment, closed); **IR-ANIA-EXP-2026-00461** (HVC-001 W point, witness waived 2026-09-18, reviewed and approved 2026-09-20); one IR approved by a paper sign-off of Abdullah.
- **Materials:** MAR-ANIA-EXP-2026-0021 ready-mix C40 (RMX, code A); MAR-0022 rebar B500B (ARS, code B); MAR-0027 waterproofing membrane (SAHEL, code C, Revise and Resubmit); 38 MIRs decided in September, 2 with rejections; named **MIR-ANIA-EXP-2026-0112** HDPE pipes (GULFPIPE, 240 m delivered, 180 accepted, 60 rejected for ovality and damaged ends) → **QTN-ANIA-EXP-2026-0009** (60 m) → **NCR-ANIA-EXP-2026-0041** (major, reject_return, return note pending).
- **Pours and tests:** **POUR-ANIA-EXP-2026-0077** Pier B level 3 slab, 186 m³, C40 (MAR-0021), 2026-09-01, 4 sets (TST-…-00385 … 00388); 28-day result of set 3 (**TST-ANIA-EXP-2026-00388**) mean 33.2 MPa → fail (b) → **NCR-ANIA-EXP-2026-0044** (critical, opened 2026-09-29 11:20 by Bilal, owner Bilal; containment: load restriction and props kept; RCA 8D, cause material; cores TST-…-00431 per QX6; disposition use_as_is approved by Hatem with concession by Abdullah; costs QX1; CA high "tighten water addition control at the batching plant" owned by Bilal's RAWABI colleague; status Disposition Approved at the clock). September test requests with a verdict: 212, failed 6.
- **Welding:** WPS-NAJD-SMAW-01 Rev.0 (AWS D1.1, SMAW, 5–25 mm, positions 1G–4G, approved), PQR-NAJD-001; welders W-017 and W-021 (NAJD); WPQ for both (SMAW); weld log of the Pier B roof lot "PB-ROOF RT 10 %" per QX8; W-021's last SMAW weld 2026-03-28 (QX9). September first NDT examinations 120, rejected 5.
- **Calibration:** MTE-0015 last calibrated 2025-10-01 (interval 12, due 2026-09-30); `CAL-ANIA-EXP-2026-0018` for MTE-0012 (CAL-NMS, accepted).
- **Punch:** 46 items on Pier B level 1 (12 pinned), 30 closed (24 on or before target), 16 open (3 category A, one of them overdue since its target 2026-09-28: **PCH-ANIA-EXP-2026-00318**).
- **Dossier:** **DOS-ANIA-EXP-2026-0001** Z-PIERB level 3 (Draft; blockers: NCR-…-0044 open, PCH-…-00318 open).
- **NCRs:** 44 NCRs in 2026 up to the clock (NCR-ANIA-EXP-2026-0001 … 0044). September: 14 opened (9 minor, 4 major, 1 critical; categories QX25; one repeat); 10 closed in September (median 12 days); 10 with target_close_date in September, 8 closed on time; open at 2026-09-30: 11 (age buckets 8 / 2 / 1 / 0); costs QX26; work value September 48,500,000.00. A July NCR (material, RMX, `TT:CONC-CYL`, opened 2026-07-02) supports AC-Q0-38.
- **Observations, alerts, complaints:** 6 observations in September; **QAL-ANIA-EXP-2026-0003** stop_use "Rebar heat H71203 — do not use pending certificate" (issued 2026-09-10 by Hatem, ack required for qc_inspector on S-LAND, valid to 2026-10-31); **CCM-ANIA-EXP-2026-0002** from ANC "water ponding at stand 23 after rain" (received 2026-09-24, justified, linked NCR, Responded).
- **Competence:** 64 person-requirement pairs, 60 met at 2026-09-30; one QC inspector's CONC-FIELD-TECH expires 2026-10-20.

### A.5 RUH-CCH set-up
- Positions WAREHOUSE_MGR (Saad), RESP_PHARMACIST (Lama), TRANSPORT_SUP (Naveen). Matrix = defaults except `q_audit.issue` → user Faisal (the only QA/QC Manager, Reem, leads the audits).
- Customers (depositors): `NDC` Najd Dairy Co. (owner_release_approval false), `GFF` Gulf Frozen Foods Co. (true), `SAHM` Sahm Pharma Distribution (true).
- Zones of S-DC1 with storage settings (class defaults unless stated): `Z-DOCK` controlled dock (dock_controlled 8–15 °C), `Z-FRZ1` frozen chamber 1 (frozen, setpoint −22), `Z-CHL1` chilled chamber 1 (chilled 0–4), `Z-PHR1` medicines 2–8 °C (pharma_2_8), `Z-AMB1` controlled ambient (15–25), `Z-DRY1` dry store (≤ 30 °C, ≤ 65 % RH), `Z-QRT` quarantine cage (chilled 0–4); `Z-RET` returns area (no temperature monitoring, not a storage zone). Storage zones = 7. 22 monitoring points (2–4 per zone, 15-min interval) with loggers `MTE-0101`…`MTE-0122` (calibrated by CAL-NMS 2026-03, points −25, 0, +5, +25 °C); probes `MTE-0042` (QX11) and `MTE-0051`.
- Products (selected): `NDC-1001` fresh laban 1 L (chilled, 14 d), `NDC-Y` yoghurt 170 g (chilled, 30 d), `NDC-5001` UHT milk 1 L (ambient_controlled, 180 d), `GFF-2001` frozen whole chicken 1,000 g (frozen, 180 d), `GFF-2105` frozen mixed vegetables 2.5 kg (frozen, 540 d), `SAHM-3001` insulin pen box (pharma_2_8, 730 d, min remaining 70 %), `SAHM-3100` eye drops (ambient_controlled, 730 d).
- Mapping: **MAP-RUH-CCH-2026-0004** Z-FRZ1 summer loaded study (2026-07-14…07-21, 27 loggers, 5-min interval, approved 2026-07-28 → valid to 2028-07-27); Z-PHR1 mapped until **2026-10-20** (periodic study planned); Z-CHL1 mapped until 2027-12-31; Z-DOCK, Z-AMB1, Z-DRY1 and Z-QRT mapped until 2027-06-30 (MAP-RUH-CCH-2025-0001…0004).
- Pest stations: 46 (SHIELD); hygiene schedules: daily dock, weekly chambers (QHYG), monthly pest visits (QPST).

### A.6 RUH-CCH records, September 2026
- **Readings:** 22 points × 15-min readings for September (logger CSV imports, one batch per point per week), plus twice-daily manual readings; 90 unmonitored minutes in Z-CHL1, 420 in total; out minutes 640 in total (QX18).
- **Excursions:** Z-CHL1 minor 2026-09-17 08:15–09:15 (QX12); Z-FRZ1 major 2026-09-22 02:00–05:30 (QX13) → NCR-RUH-CCH-2026-0034, HLD-RUH-CCH-2026-0112 (14 lines from the 2026-09-21 23:00 snapshot; impact assessed by Saad, GFF decision file attached; 12 lines released, 2 lines destroyed), Z-DOCK 3 minor; transients in Z-FRZ1 (90 min) and Z-AMB1 (25 min).
- **Receiving:** 640 receipts decided (12 with a rejected line, 25 with a deviation, 8 with a quarantine); named **RCV-RUH-CCH-2026-01877** (QX14, GFF, 2026-09-14) and **RCV-RUH-CCH-2026-01902** (NDC yoghurt +11.0 °C rejected 2026-09-21 → NCR-RUH-CCH-2026-0031 with supplier NDCF).
- **Stock:** daily stock snapshots at 23:00; FEFO checks 200 (194 compliant incl. 2 listed exceptions); cycle counts 400 lines (388 within tolerance); throughput 1,860,000 units handled, 412 damaged (damage reports incl. **DMG-RUH-CCH-2026-00207**, 30 yoghurt units destroyed); mock recall **RCL-RUH-CCH-2026-0002** of batch NDC-Y-2609 (QX16, closed 100.0 %).
- **Transport:** 380 trips delivered with logger data (4 with a transit excursion, incl. **TRP-RUH-CCH-2026-00921** major on 2026-09-26 → NCR-RUH-CCH-2026-0036 and complaint **CCM-RUH-CCH-2026-0005** from GFF "cartons partly thawed at delivery"); 1,250 shipments with promised and delivered times (QX17); 6 pre-load fails, 1 override by Naveen.
- **Hygiene and pest:** 120 due checks in September, 114 done on time; station `RB-14` (Z-DRY1) with activity on the 2026-08-30 and 2026-09-27 visits.
- **NCRs:** 9 opened in September (6 minor, 3 major), RUH-CCH NCR numbers 0001 … 0036 in 2026; complaints received in September: 3.
- **Calibration OOT:** QX11 review **OOT-RUH-CCH-2026-0003** open at the clock (35 items proposed no_impact, 2 recheck, 1 NCR decided).

### A.7 Shared Q4 records
- Documents: ANIA-EXP `ANIA-EXP-QA-PQP-001` Project Quality Plan Rev.1 (approved 2026-03-02) and Rev.B for review (author Hatem); `ANIA-EXP-QA-MS-004` method statement concreting Rev.2 (linked from STC-001); RUH-CCH `RUH-CCH-QA-SOP-001` receiving SOP Rev.0, `RUH-CCH-QA-SOP-007` temperature excursion SOP Rev.1 (distribution warehouse_qc, ack required, 2 of 3 acks).
- Processes RUH-CCH: RCV receiving (owner Imran, high), STO storage (owner Saad, high), DSP dispatch and transport (medium), CAL calibration (low), NCR nonconformity and CAPA (medium).
- Audits: **QAU-RUH-CCH-2026-0006** `qms_internal` on RCV and STO (lead Reem, fieldwork 2026-09-15…16, issued 2026-09-21 by Faisal through the RUH-CCH matrix override `q_audit.issue` → user Faisal; 1 major_nc, 2 minor_nc → 3 NCRs); **QAU-ANIA-EXP-2026-0004** `supplier_quality` of RMX (lead Bilal, 2026-09-08, issued 2026-09-12 by Hatem). Programme lines due in September: ANIA-EXP 2 (both on time), RUH-CCH 2 (both on time) → K-158 100.0 %.
- Management review **MRV-RUH-CCH-2026-0001** (held 2026-07-30, minutes issued).
- Supplier evaluations: initial approved for every approved supplier; supplier scores Q3 2026 final: RMX 72.2 (B, QX19), ARS 88.4 (A), LAB-RGM 91.0 (A), COOLRD 66.5 (C), NDCF 79.0 (B).
- KPI targets (both projects): K-141 ≥ 90 %, K-146 ≥ 85 %, K-148 ≤ 0.5 %, K-160 ≤ 2 %, K-162 ≤ 0.5 %, K-163 ≥ 95 %, K-165 ≥ 98 %.

### A.8 Expected September 2026 values (backend test `test_seed_kpis.py` must match)

| KPI | ANIA-EXP | RUH-CCH |
|---|---|---|
| K-141 / K-142 | **80.0 % / 19.1 %** (QX2) | — |
| K-143 | 14 (9 / 4 / 1); open 11 | 9 (6 / 3 / 0) |
| K-144 at 2026-09-30 | 8 / 2 / 1 / 0 | generator value |
| K-145 / K-146 | 12 days / **80.0 %** | generator value |
| K-147 | 7.1 % (1 ÷ 14) | generator value |
| K-148 | **186,450.00**; COPQ 0.38 % (QX26) | generator value |
| K-149 (process) | ir_inspection DPMO **6,431.5**, σ **3.99** (QX24) | receiving, picking_fefo, delivery, inventory from the seed |
| K-150 | QX25, vital few 4 | generator value |
| K-151 / K-152 / K-153 | 5.3 % (2 ÷ 38) / 2.8 % (6 ÷ 212) / 4.2 % (5 ÷ 120) | — |
| K-154 / K-155 | 95.8 % (46 ÷ 48) / 93.8 % (60 ÷ 64) | generator value |
| K-156 | 52.2 % (24 closed on time ÷ 46 with target in September) | — |
| K-158 | 100.0 % | 100.0 % |
| K-160 | — | **1.9 %** (12 ÷ 640); deviation 3.9 % |
| K-161 / K-162 | — | **0.71** (QX21) / **0.21 %** (QX18) |
| K-163 / K-164 / K-165 | — | **93.2 %** / **0.022 %** / **97.0 %** |
| K-166 / K-167 / K-168 | — | 97.0 % / 98.9 % (376 ÷ 380) / 95.0 % (114 ÷ 120) |
| K-169 | 1 | 3 (2.40 per 1,000 shipments) |
| Warnings | **E27** (K-141 80.0 < 85.0) | none |

"Generator value" = the seed generator's own result, asserted by the test as computed once and recorded in the Q4 decisions (it is not specified here so as not to over-constrain the generator).

## Change log

| Version | Date | Author | Change |
|---|---|---|---|
| v1.0 | 2026-10-31 | Quality Consultant Agent | First issue: Parts A–E mapped to packages Q0–Q4 with file, table and route ownership and plug-in registries (§3); two sector profiles; editable responsible-person matrix with positions, segregation and paper sign-off; NCR with containment, RCA (5-Why, Ishikawa, 8D), disposition, CAPA through Phase 1 CAs and cost; ITP / IR with hold and witness rules, punch with plan pins, handover dossier; MAR / MIR / quarantine, test types with ACI 318 / EN 206 rule sets, pours, welding with continuity, NDT % and progressive examination, calibration with OOT review, competence through the Phase 2 hooks; receiving, storage classes, excursions with severity bands and product impact, mapping, hygiene and pest, FEFO, holds, returns, cycle counts, recalls, transport with POD and 7b link; documents, quality audits on 6d, management review, supplier evaluation and scorecards, KPIs K-141…K-169, SPC, COPQ, DPMO and sigma, Pareto, charts C42–C51, warnings E26–E28, AI tools T26–T29, report packs; capabilities 238–280; 185 acceptance criteria; decisions D-308…D-319. |
| v1.1 | 2026-10-31 | Quality Consultant Agent | Spec review fixes: Q0 acceptance criteria no longer depend on Q1–Q4 records (AC-Q0-05, -16, -23, -45); Q-RPM-07 defines the record's responsible engagement and test requests gain `engagement_id`; PMC-side QC inspector Mazen seeded, AC-Q1-11 and AC-Q2-08 use non-contractor signers; excursion, hold, transport and recall recipients and the R2 weld repair approval go through the responsible-person matrix (new step `weld.repair2_approve`); M&TE register CRUD and screens moved to Q0 (`cal_status` unknown until Q2); full transition tables for test requests, welds, excursions, hold lines, recalls, trips, document revisions and supplier evaluations; §3.3a lists the stubs Q0 creates and the i18n merge / parity-check extension; Appendix A.1 names `test_auth.py:294` and the tests Q0 re-runs; `equipment_operator` in list CA; `dispatch_override_allowed` per storage class; why quality observations are separate; recall hold snapshot; two sign-off rows for disposition and concession. |
| v1.2 | 2026-10-31 | Quality Consultant Agent | Second review fixes: explicit responsible-engagement chain for Q-RPM-07 with sys `engagement_id` on IRs, pours, MIRs and welds and a required `engagement_id` on MARs; PMC quality engineer Rania seeded and used in AC-Q2-08; systems follow Q-PRF-04; row 259 marks the R2 repair approval; TRANSPORT_SUP is the default for `trip.dispatch_override`; excursion close condition points to Q-EXC-06; Q-STK-01 defers recall traces to Q-RCL-02; §3.3 Q0 row lists the §3.3a files; fixtures name Rania, Mazen, Arun and Naveen; new AC-Q0-49 (M&TE register in Q0 with `cal_status` unknown) — 186 acceptance criteria. |
