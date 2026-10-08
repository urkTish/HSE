# Phase 6 — "Other essentials": ranked proposal

**Version:** v1.0 · **Date:** 2026-10-08 · **Author:** HSE Consultant Agent · **Status:** Proposal. The HSE Manager asked us to proceed without waiting; the order below is the Consultant's default and can be changed at review.
**Builds on:** `0-foundation.md` v1.0 … `5-training.md` v1.0 (with the earlier specs at the versions listed in `5-training.md` §11) and `docs/DECISIONS.md` #1–#101.
**Purpose of this document:** list every Phase 6 candidate from the build plan, say what each one is worth to the HSE Manager, what KSA rule drives it, what the platform already does, how big it is and what it depends on. Then group the candidates into modules 6a, 6b and so on, and recommend a build order. Every module gets its own full Module Spec, written one at a time, in that order (build plan §4, Phase 6 "per item").

Conventions: `VERIFY` = clause or number to confirm against the current official text. `ASSUMPTION` = Consultant default. Size: **S** ≈ 1 entity family, no hook, fewer than about 40 acceptance criteria; **M** ≈ 2–4 entity families, one integration with earlier phases, about 60–110 ACs; **L** ≈ 5 or more entity families or several cross-phase integrations, more than 110 ACs.

---

## 1. Recommended modules (build order)

| # | Module | Groups these candidates | Size | Value | Depends on | Why this position |
|---|---|---|---|---|---|---|
| **6a** | **Occupational health & medical fitness** | Occupational health & medical fitness (incl. return to work, referrals, health surveillance) | M/L | High | Phases 1–5 (hook interface, injury cases, workers, PTW crew roles) | Closes the **last open hook kind** (`medical_fitness`). Phases 2 and 3 already call it (e.g. CSE entrants, `CSE-ENTRY-FIT`), but it is stuck in `warn` with no provider, so live confined-space permits run today with no fitness check. It uses the same provider and warn → block pattern as Phases 4 and 5, so the build risk is low. 6b needs its fitness codes, restrictions and heat-illness holds. |
| **6b** | **Heat stress management** | Heat stress (WBGT, work/rest, acclimatisation, midday-ban compliance for work that has no permit) | M | High (KSA-specific) | 6a (HEAT-EXPOSURE-FIT, `no_heat_exposure` restriction, heat-illness holds), Phase 3 HT-1…HT-6, Phase 5 HEAT-AWR | The heat season (Phase 1 setting, 06-01) and the midday ban (06-15) start in about 8 months. The module must be live and tuned by April 2027, when the Phase 5 HEAT-AWR refresher plan starts (GP-6). Heat injuries are 12 % of the seeded injury mechanisms (Phase 1 A.5). |
| **6c** | **Emergency preparedness & drills** | Emergency response & drills | M | High | Phase 5 (FIRE-WARDEN, FIRST-AID records), Phase 3 rescue plans, Phase 4 (fire equipment as equipment items), Phase 0 zones | Civil Defense and SBC 801 require it, and clients audit drills every month. It reads Phase 5 records for first-aider and fire-warden coverage, so it needs no new hook. |
| **6d** | **Field assurance: inspection & audit checklists + toolbox talks** | Audits & inspection checklists; toolbox talks | M | Medium-high (daily use) | Phase 1 inspections (§3.7, K-34/K-35), Phase 1 daily-return toolbox fields (K-36), Phase 3 audit item pattern | Turns Phase 1's two-number inspections (`items_checked` / `items_compliant`) into real checklists. Gives toolbox talks a register with topics, attendance and language, using the same register-switch pattern as K-37/K-38 for K-36. This is high-volume, low-risk work. |
| **6e** | **Environmental management** | Environmental (waste, dust, noise, spill) | M/L | Medium-high | Phase 1 environmental incidents, Phase 2 ops events (dust/LVP), 6d checklists (environmental inspections) | Driven by the KSA Environmental Law, NCEC permits and MWAN waste rules. Airport works add dust and FOD. It comes after 6d so that environmental inspections reuse the checklist engine. |
| **6f** | **Incident follow-up: notification pack & lessons learned** | GOSI/client incident notifications; lessons learned | S/M | Medium (legal exposure, but tracking is already built) | Phase 1 I-20/I-21 (notification tracking), Phase 1 investigation `lessons_learned` field | Phase 1 already derives which notifications are due and tracks due / done / overdue. What is missing is pre-filled form packs (GOSI work-injury report, client flash report, GACA occurrence), evidence of submission, client-specific deadlines, and a lessons-learned bulletin with distribution and read receipts. |
| **6g** | **Contractor HSE scorecard + reports export pack** | Contractor HSE performance scoring; reports export | M | High for the HSE Manager (contract leverage, monthly client reports) | Every earlier phase and 6a–6f (it only reads KPIs) | It consumes every KPI, so it comes last and so that its weights are not set on incomplete data. The export pack covers the deferred D-10 PDF export (DECISIONS #19): monthly report PDF, client templates and an OSHA 300/300A-style log. |
| defer | Management of change (MOC) | MOC | M | Low-medium on construction | Phase 3 JSA, 6d | See §3. |
| defer | HSE plan & document control | HSE plan/document control | M | Low-medium | — | See §3. |

Total recommended: **7 modules** (6a–6g). Two candidates are deferred.

## 2. Candidate-by-candidate assessment

### 2.1 Emergency response & drills → **6c**
- **Value to the HSE Manager:** one place for the project Emergency Response Plan (ERP) and its revisions, the emergency organisation (fire wardens, first aiders, rescue teams, assembly-point marshals), coverage ratios per site and shift, the drill programme with planned and actual results (evacuation time, head-count reconciliation, lessons, corrective actions), emergency equipment readiness (extinguishers, AEDs, first-aid kits, eye-wash stations, rescue kits — monthly checks), muster points per zone, and the emergency contact directory. Clients and Civil Defense ask for drill records and evacuation times in audits.
- **KSA legal / regulatory driver:** Saudi Civil Defense regulations (fire safety, evacuation, fire wardens) `VERIFY`; **SBC 801** (Saudi Fire Code) and the emergency-planning provisions it adopts from the IFC `VERIFY` chapter; MHRSD OSH Regulations — emergency plans, first aid and first-aider ratios `VERIFY`; Saudi Red Crescent (SRCA) first-aid standards; for ANIA-EXP: **ICAO Annex 14 §9.1** (aerodrome emergency planning), GACAR Part 139 and the airport operator's AEP. Contractor works must integrate with the AEP and with ARFF access routes `VERIFY`. ISO 45001 cl. 8.2.
- **Overlap with what is built:** Phase 5 holds FIRE-WARDEN and FIRST-AID records and the matrix roles `fire_warden` / `first_aider`, and its §8.5 already reserves "emergency-team coverage and drills" for Phase 6. Phase 3 holds CSE and WAH rescue plans per permit (`rescue_plan_ref`) and rescue-team crew roles. Phase 2 ops events record LVP, sandstorm and thunderstorm. Phase 1 CA engine. **Not built:** ERP register, drills, coverage ratios, emergency equipment checks, muster points.
- **Size:** M (ERP + organisation, drills, equipment checks; coverage is computed from Phase 5).
- **Dependencies:** Phase 5 in-force predicate (§6.6) for coverage; 6d checklists would make equipment checks nicer but are not required (6c can ship a fixed equipment-check list and move to 6d templates later).

### 2.2 Heat stress (WBGT, work/rest, midday-ban compliance) → **6b**
- **Value:** WBGT readings per site or zone (manual or from a station), automatic work/rest regime per reading and workload, acclimatisation plans for new starters and returners (Phase 1 data shows new starters over-represented, A.5), water/shade/rest-station checks, heat alerts to supervisors, midday-ban compliance for **non-permit** outdoor work (Phase 3 only covers work with a permit, HT-1…HT-4), a heat-illness log linked to Phase 1 cases, and a season report for the client.
- **KSA driver:** MHRSD ministerial decision on the **midday outdoor work ban** (12:00–15:00, 15 June–15 September) `VERIFY` the annual decision; MHRSD/NCOSH heat-stress guidance `VERIFY`; ACGIH TLV / NIOSH heat-stress criteria (international benchmark) and ISO 7243 (WBGT); client standards (e.g. Saudi Aramco GI 6.0x heat stress) `VERIFY`.
- **Overlap:** Phase 3 HT rules (permit windows, automatic `midday_ban` suspension, exemptions, `ambient_temp_c` at shift start, JSA hazard `heat_stress`); Phase 1 `heat_season` setting, heat natures and mechanism `exposure_heat`, chart C8, T9 dimension `heat_season`; Phase 5 HEAT-AWR course and GP-6 pre-season refreshers; 6a HEAT-EXPOSURE-FIT, the `no_heat_exposure` restriction and heat-illness holds. **Not built:** WBGT, work/rest, acclimatisation, rest-station checks, ban compliance outside permits.
- **Size:** M.
- **Dependencies:** **6a** (fitness codes, restrictions, holds). Phase 3 must accept a WBGT-driven pause or suspension reason (an earlier-spec change in 6b §11).

### 2.3 Environmental (waste, dust, noise, spill) → **6e**
- **Value:** environmental aspects/impacts register; permit register (NCEC environmental permits, municipal permits); waste manifests and the chain of custody to licensed carriers and facilities; dust monitoring (PM10 at the boundary and near airside, visual dust checks, water-bowser log); noise monitoring at the boundary and at night (RBT-52 is in central Riyadh); spill kits and a spill log linked to Phase 1 environmental incidents; and a monthly environmental report for the client.
- **KSA driver:** **Environmental Law** (Royal Decree M/165, 1441H) and its Implementing Regulations (air quality, noise, waste, soil) `VERIFY`; **NCEC** (National Center for Environmental Compliance) permits and inspections; **MWAN** (National Center for Waste Management) — waste producer registration, licensed transporters, manifests `VERIFY`; MOMRAH/Balady municipal construction rules (dust, noise hours) `VERIFY`; ISO 14001; for ANIA-EXP, FOD and dust effects on airside operations (ICAO Annex 14, airport operator).
- **Overlap:** Phase 1 incident type `environment` (K-count ENV), observation category `environmental`; Phase 2 ops events `dust_sandstorm` / `lvp`. **Not built:** everything else.
- **Size:** M/L (waste, monitoring, permits, spills). The spec can split into 6e-1 (waste + spills) and 6e-2 (dust + noise monitoring) if the HSE Manager prefers smaller steps.
- **Dependencies:** 6d checklists (environmental inspections) are preferred, not mandatory.

### 2.4 Occupational health & medical fitness → **6a**
- **Value:** a fitness-for-work register (pre-placement, periodic, task-specific, return to work), functional work restrictions that supervisors can act on, fitness holds that keep an injured or unwell worker off site until a clinician clears them, health surveillance on schedule (noise audiometry, silica, radiation workers), and the **`medical_fitness` hook provider** that Phases 2 and 3 already call. It does this without the platform ever holding a diagnosis.
- **KSA driver:** MHRSD Labour Law and OSH Regulations — pre-employment and periodic medical examinations for workers exposed to occupational hazards, records `VERIFY` articles; NCOSH guidance `VERIFY`; GOSI occupational hazards (work injury, occupational disease, return to work) `VERIFY`; MOH facility licensing and SCFHS registration of the examining physicians `VERIFY`; NRRC for radiation workers `VERIFY`; GACA / airport operator for airside drivers `VERIFY`; OSHA 1910.134(e), 1910.95(g), 1926.1153(h) and ASME B30.5 as international benchmarks; **PDPL** (health data is sensitive data).
- **Overlap / hook:** Phase 2 HK-1 lists kind `medical_fitness` (Phase 6) and the setting `hook_policy.medical_fitness` (warn). Phase 3 CS-3 / HK3-2 register `medical_fitness: CSE-ENTRY-FIT` for entrants, HK3-4 / P3-3 define how fitness results are shown (DECISIONS #79), and HT-5 points at "Phase 6 medical fitness". Phase 4 PC-13 has the `medical_restriction_on_card` flag and its "restriction reviewed" stop-gap. Phase 1 injury cases (with Phase 2 `worker_id`) carry categories, heat natures and rtw_date.
- **Size:** M/L (catalogue, providers and examiners, assessments, holds and referrals, provider hook; no new UI paradigm, since it reuses the Phase 4/5 patterns).
- **Dependencies:** none outstanding. It needs one Phase 0 change: a new role, the Occupational Health Practitioner, which keeps clinical-administrative data out of HSE staff hands.

### 2.5 Audits & inspection checklists → **6d**
- **Value:** a checklist template library (scaffold, excavation, electrical DBs, lifting gear pre-use, housekeeping, airside FOD walk, fire equipment, welfare/camp, environmental), versioned and bilingual, with item-level answers, photos, scoring and automatic CAs for failed critical items. Also HSE system audits (ISO 45001 internal audit, contractor HSE audits) with findings graded major/minor/observation. Phase 1 inspection compliance (K-34/K-35) gains real item data and the AI gains "most failed items".
- **KSA driver:** MHRSD OSH Regulations — workplace inspection duties `VERIFY`; ISO 45001 cl. 9.1 / 9.2; client contract HSE plans (monthly audit programmes); Saudi Aramco CSM inspection checklists where flowed down `VERIFY`.
- **Overlap:** Phase 1 inspection plans and instances (frequency, assignee, `items_checked` / `items_compliant`, findings, CA link); the Phase 3 PTW audit (list A items, scoring §6.8) is a ready pattern; Phase 4 scaffold tags (tagging stays in Phase 4).
- **Size:** M (templates + item answers; Phase 1 entities extended, not replaced).
- **Dependencies:** none; it improves 6c, 6e and 6g.

### 2.6 HSE plan / document control → **defer**
- **Value:** a controlled register of the project HSE plan, procedures, method statements and risk assessments, with revision, review dates, approval workflow and read-and-acknowledge.
- **KSA driver:** ISO 45001 cl. 7.5 (documented information); client contracts require an approved HSE plan before mobilisation. There is no specific KSA statute beyond the general OSH duty.
- **Overlap:** Phase 3 JSA templates (review dates, approval) and RA/MS attachments; Phase 5 trainer evidence files. Mega-projects almost always run a client EDMS (Aconex, ProjectWise and similar), which is the official document control system. A second register in the HSE platform creates two masters.
- **Size:** M.
- **Why defer:** low marginal value and a real risk of duplicating the client EDMS. A minimal alternative, available on request: a read-only "HSE plan and key procedures" link list per project, with a revision number and review date (S, fits inside 6g).

### 2.7 Toolbox talks → **6d** (grouped with checklists)
- **Value:** a toolbox-talk register with a topic library (EN/AR + worker languages), linked to recent incidents, observations and lessons learned (6f); attendance by worker (Phase 2 card scan or list), language understood, supervisor, duration; it becomes the source of K-36 through a register switch, as Phase 2 did for K-38 and Phase 5 for K-37.
- **KSA driver:** MHRSD OSH duty to inform workers of hazards `VERIFY`; ISO 45001 cl. 7.3 / 7.4; client HSE plans (daily or weekly TBTs).
- **Overlap:** Phase 1 daily-return `toolbox_talks` / `toolbox_attendees` (K-36); Phase 5 BD5-5 and TH-5 keep toolbox talks out of training hours; Phase 3 crew briefing SH-4 (permit-specific, stays in Phase 3).
- **Size:** S on its own. Grouped with checklists because both are high-volume field forms done by the same supervisors, and both use a register-switch for a Phase 1 leading indicator.
- **Dependencies:** none.

### 2.8 Management of change (MOC) → **defer**
- **Value:** controlled change of design, temporary works, methods, organisation (e.g. a new subcontractor or key-person change) with risk review and approval before implementation.
- **KSA driver:** none specific for construction. ISO 45001 cl. 8.1.3; it is mandatory in process safety (OSHA 1910.119(l), Saudi Aramco GI 2.xxx `VERIFY`), but those regimes do not apply to these projects.
- **Overlap:** Phase 3 already covers the high-risk part of "change at the workface": JSA revision and approval, permit amendment and SIMOPS. Phase 4 has configuration-change events for equipment (CF rules). Engineering change control belongs to the design/PMC process.
- **Size:** M.
- **Why defer:** low marginal value on building and airport works. Revisit if the platform is used on brownfield, live-terminal or process-plant tie-in works, where an MOC for temporary changes to live airport systems would matter.

### 2.9 Contractor HSE performance scoring → **6g**
- **Value:** a monthly scorecard per contractor tree and engagement, built from lagging indicators (TRIR, LTIFR, severity, HiPo events), leading indicators (observations, inspections, CA closure, PTW audit score K-61, training compliance K-82, medical compliance K-89, certification K-72/K-73), compliance (daily-return completeness, overdue notifications, gate denials) and audit results. It uses configurable weights, bands (green/amber/red), trend, and a link to contract levers (warning letter, improvement plan, suspension as Phase 0 contractor states). The HSE Manager uses it in monthly contractor meetings and in pre-qualification for the next package.
- **KSA driver:** contractual, not statutory (ISO 45001 cl. 8.1.4; client contractor-management procedures; Saudi Aramco CSM contractor evaluation `VERIFY` if flowed down).
- **Overlap:** every KPI already exists by contractor (Phase 1 D-2 filters, W2 examples); Phase 0 contractor suspension and blacklist.
- **Size:** M (weights, normalisation, bands, monthly freeze, appeal/comment, PDF).
- **Dependencies:** all phases; it should come after 6a–6f so that the weights cover the final KPI set.

### 2.10 GOSI / client incident notifications → **6f**
- **Value:** pre-filled, bilingual notification packs (GOSI work-injury notification data set, MHRSD serious-injury report, Civil Defense fire report, GACA/airport operator occurrence report, client flash report at 24 h and full report at 7/14 days), deadlines per body and per client contract, evidence of submission (reference, screenshot, acknowledgement), reminders, and a register of what was sent to whom. No e-filing (no public API is assumed).
- **KSA driver:** **GOSI** Occupational Hazards Branch — employer notification of work injuries (commonly cited as 3 days) `VERIFY`; MHRSD serious-injury and fatality notification `VERIFY`; Civil Defense; GACA occurrence reporting (GACAR) `VERIFY`; PDPL for what each pack may contain.
- **Overlap (large):** Phase 1 already has `notifications` on the incident (bodies gosi, mhrsd, civil_defense, gaca, airport_operator, client, police), the derived "required" logic I-20 with deadlines, due/overdue alerts (§7) and the action-panel item. I-21 says Phase 1 does not submit. The gap is the form content, client deadlines, evidence and pack export.
- **Size:** S.
- **Dependencies:** Phase 1 only. It is grouped with lessons learned because both follow the investigation.

### 2.11 Lessons learned → **6f**
- **Value:** turns the Phase 1 investigation `lessons_learned` text (required for L3) into a published bulletin (EN/AR, de-identified, photo-redacted), distributed to projects, contractors and toolbox-talk topics (6d), with read/briefed confirmation per contractor and a searchable library. The AI layer can then suggest "similar past events" from bulletins only.
- **KSA driver:** none statutory. ISO 45001 cl. 10.2 (incident, nonconformity and corrective action) and the client's HSE plan.
- **Overlap:** Phase 1 investigation field and AI T5 (which returns lessons learned de-identified).
- **Size:** S.
- **Dependencies:** Phase 1; it feeds 6d toolbox topics, so building it before 6d would be marginally better. The value is small enough that the 6d → 6f order stands, and 6d can link bulletins once 6f exists.

### 2.12 Reports export → **6g** (grouped with scoring)
- **Value:** server-rendered PDF/XLSX of the monthly HSE report (Phase 1 AI-19 report, today shown on screen only), the contractor scorecards, an OSHA 300/300A-style annual log (de-identified per 1904.29(b)(6)–(9)), client template mapping (e.g. the airport operator's monthly HSE statistics form `VERIFY`), and scheduled email delivery to named recipients.
- **KSA driver:** contractual (client monthly reporting), PDPL (what may leave the platform). GOSI annual statistics `VERIFY`.
- **Overlap:** per-phase register exports already exist (Phase 0 rule / capability 18; Phase 3 DECISIONS #78; Phases 4/5 exports). D-10 PDF export was deferred and parked (DECISIONS #19).
- **Size:** S/M.
- **Dependencies:** all KPIs; best done together with the scorecard, which is itself a report.

## 3. Deferred items (and what would bring them back)
| Item | Reason | Revisit when |
|---|---|---|
| MOC | Phase 3 JSA/permit amendment and Phase 4 configuration events already cover workface change; engineering change is PMC/design scope | Brownfield / live-terminal tie-ins, process-plant scope, or a client contract that names an MOC procedure |
| HSE plan & document control | The client EDMS is the master; a second register duplicates it | The client has no EDMS, or the HSE Manager wants read-and-acknowledge tracking for procedures (that part could join 6d as "document briefing" records) |

## 4. Dependency sketch and timing
```
Phases 1–5 ──► 6a OH & fitness ──► 6b Heat stress ──┐
          ├──► 6c Emergency & drills ──────────────┤
          ├──► 6d Checklists + TBT ──► 6e Environment┤
          └──► 6f Notifications + lessons ──────────┴──► 6g Scorecard + exports
```
- **Heat deadline:** 6b should be accepted by **2027-03-31**, so that the Phase 5 HEAT-AWR refresher plan (GP-6, 60 days before 06-01) and WBGT calibration run before the season. Given the per-module loop (spec → contract → build → design pass → demo), that leaves room for 6a and 6b first, and is the main reason they lead.
- 6c and 6d are independent of each other and could swap if the HSE Manager prefers daily-use tools first (see the summary of choices).

## 5. Numbering continued by Phase 6 modules
Each Phase 6 module continues the shared sequences in build order, so numbers stay unique across the platform: capabilities after 145 (6a takes 146–165), KPI ids after K-88 (6a takes K-89…K-96), leading warnings after E13 (6a takes E14–E15), AI tools after T17 (6a takes T18), charts after C21 (6a takes C22–C24). A later module takes the next free numbers when its spec is written; nothing is reserved ahead.

## Change log
| Version | Date | Author | Change |
|---|---|---|---|
| v1.0 | 2026-10-08 | HSE Consultant Agent | First issue: 12 candidates assessed, grouped into 7 modules (6a–6g) plus 2 deferred; build order and numbering continuation. |
