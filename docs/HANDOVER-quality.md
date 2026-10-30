# Handover: Quality (QA/QC) module, phase 8

Status: ready to start, 2026-10-30. Repo: urkTish/HSE. Base branch: `claude/hse-platform-build-kannxy` at 39fe53b or later
(trial readiness A + B + C merged; last decision D-307; Alembic head `c0025`; contract 0.17.0).

This file is for the **orchestrator session** that runs the whole build. Read it all, then follow section 6.

## 1. Why

Turki (owner) wants a full QA/QC module in the platform. This build is **his master version**: everything is built and switched
on, he checks and improves it, and later he trims or customises it per customer (bundle / licence, see `docs/LICENSING.md`).
So nothing is left out "for later" because a customer might not need it.

## 2. Decisions already made by Turki (2026-10-30)

1. **Two sector profiles**, chosen per project and editable later: **Construction** and **Logistics**. Logistics covers
   temperature-controlled storage (cold chain), dry storage and transportation. The profile decides which Quality screens,
   record types, checklists and KPIs a project shows; shared parts (NCR, audits, calibration, documents, KPIs) serve both.
   A project can switch profile; records already made stay.
2. **No client standard is targeted** (no Aramco / NEOM / ROSHN / SFDA profile built in). Use general good practice
   (ISO 9001:2015, ISO 19011 for audits, ISO/IEC 17025 ideas for test results, GDP / cold-chain good practice for logistics)
   and make acceptance criteria, checklists, numbering and forms **configurable data**, not code. KSA rules that clearly apply
   (Saudi Building Code references on forms, PDPL for personal data, Riyadh time, Hijri dates on packs) are fine; mark any
   unsure regulation `[VERIFY]` in the spec.
3. **Sign-off = "Responsible person"**. Every approval / witness / acceptance step names a *responsible person*. Who that is
   is editable per project and per record type (a user, or a role such as QA/QC Manager, Consultant, Client Rep,
   Warehouse Manager). No fixed "consultant signs" or "client signs" rule. External sign-off (a person without an account)
   uses the existing invitation / guest patterns where possible.
4. **Full scope** (section 4), including lab tests, welder and inspector qualifications, calibration, SPC, Cost of Poor
   Quality and all logistics items.
5. **Agents split the work.** Builders run on Claude Opus 5.5 at high effort; **Fable 5.1 reviews** the spec and every
   package PR (section 5). The orchestrator fixes CI and integrates.

## 3. Lessons from the trial-readiness build (apply them)

- Parallel packages collide on: Alembic heads, `CONTRACT_VERSION`, `models/__init__.py`, `config.py`, `.env.example`,
  i18n message files, `shell.tsx`/navigation, `docs/DECISIONS.md` and `docs/PROGRESS.md`. Give each package its own
  decision-number range and migration slug, and finish with **one integration branch/PR** that Turki merges instead of the
  package PRs (he merged a package PR early last time; tell him in the report which PR to merge).
- Only the integrator bumps `CONTRACT_VERSION` and regenerates `openapi.yaml` / `schema.d.ts` with the repo tools.
  Packages keep their own contract changes but leave the version line alone.
- Tests must not depend on today's date: use the `clock`/`noon`/`sc_clock` fixtures in `backend/tests/conftest.py`
  (a hard-coded September date broke CI on 2026-10-22).
- e2e: the API clock can lag the Playwright clock by the backend start-up time; never rely on "next 30 s step" style timing.
- Three agents on this 4-CPU / 15 GB machine is the practical maximum for parallel builds. Do not run the full backend suite
  in 4 shards while builders run; let CI do it. The integrator runs the 4-shard suite when the machine is free.
- Postgres 16 runs on localhost:5432 (superuser `hse`/`hse`); start it with `pg_ctlcluster 16 main start` if down.
  Raise `max_connections` to 400 once (`ALTER SYSTEM`, restart) before parallel test runs.
- The cloud worktree guard can block `frontend/e2e/start-backend.sh`; run its steps by hand if so.
- Never `pkill -f <word>`; kill only your own PIDs. Never `git add -A` in a shared tree.

## 4. Scope (the spec writer turns this into `docs/specs/8-quality.md`)

Reuse before building: corrective actions (`services/corrective_actions.py`), inspections and checklists (`services/inspections.py`,
6d field assurance and audits), contractors and scorecards (6g), training and certificates (5, 4), equipment and third-party
certification (4), site vehicles (7b), attachments with photo shrinking and virus scan, PDF renderer (fpdf2 + HarfBuzz, EN/AR),
audit log, notifications/email outbox, AI assistant tools, KPI engine, licence bundle field.

**Shared (both profiles)**
- Quality settings per project: sector profile, responsible-person matrix per record type, numbering formats, acceptance
  criteria library, default checklists.
- Document control (light): Project Quality Plan, procedures, method statements, specifications; revisions, status
  (draft / for review / approved / superseded), transmittals, read-and-acknowledge. Not a full EDMS.
- NCR (تقرير عدم مطابقة): raise from anywhere (inspection, test, receiving, audit, temperature excursion, customer complaint);
  classification (minor / major / critical), containment, root cause (5-Why, Ishikawa, 8D), disposition (use-as-is, repair,
  rework, reject / return / scrap), CAPA linked to the existing corrective actions, verification and close-out by the
  responsible person, cost of the NCR (rework hours, material, delay) feeding Cost of Poor Quality.
- Observations / quality alerts and customer complaints.
- Calibration of measuring and test equipment (M&TE): register, intervals, certificates, out-of-tolerance impact review
  (which inspections used it → possible NCR), status tags. Logistics: temperature loggers and probes are M&TE too.
- Competence: inspector, welder and operator qualifications with expiry, linked to the training / certificates modules.
- Internal audits (ISO 9001 clause checklist, findings → NCR / CA, auditor independence), management review records,
  supplier / subcontractor audits.
- Supplier and subcontractor quality: approved supplier list, evaluation and re-evaluation, quality scorecards
  (fed by NCRs, rejections, on-time delivery), link to contractors.
- KPIs and analytics: first-time pass rate, IR rejection rate, NCR count / ageing / closure time, repeat NCRs, Cost of Poor
  Quality, DPMO and sigma level, Pareto of defect causes, SPC charts (X-bar/R, p-chart) where data allows, logistics KPIs
  below. Dashboard tiles, report packs (PDF EN/AR with Hijri), AI assistant tools to query quality data.

**Construction profile**
- ITP builder per activity / work package: steps with Hold / Witness / Review / Surveillance points, acceptance criteria,
  reference documents, responsible person per point; ITP revisions.
- Inspection Request (IR / RFI) workflow: request → scheduled → inspected (checklist, photos, measurements) →
  approved / approved with comments / rejected (→ NCR or re-inspection); hold points block the next step.
- Material Approval Request (MAR / MAS) and Material Inspection Request on delivery (MIR): submittal, mill / test
  certificates, approval by the responsible person, quarantine of rejected material.
- Testing and lab: test requests and results with acceptance criteria and automatic pass/fail (concrete cubes / cylinders
  7/28-day, slump, compaction / density, soil, asphalt, NDT (UT, RT, MT, PT), pressure / hydro tests, torque, coating DFT,
  others as configurable test types); failed result → NCR; lab as supplier.
- Welding: WPS / PQR register, welder qualification (WPQ) with continuity, weld log and NDT percentage tracking, repair rate.
- Punch lists / snagging by area, with photos and floor-plan pin (simple image pin, no BIM), and the handover dossier
  (compiled PDF: ITPs, IRs, test results, certificates, NCR close-outs, as-built list) per area or system.

**Logistics profile**
- Receiving inspection (goods in): PO / ASN reference, quantity, condition, labels, expiry / batch, temperature on arrival,
  photos; accept / accept with deviation / quarantine / reject → NCR or supplier claim.
- Storage conditions: zones (frozen, chilled, ambient-controlled, dry), set ranges, temperature / humidity readings
  (manual entry and data-logger CSV import), excursion detection with duration and severity, excursion → NCR with product
  impact assessment; temperature mapping studies per zone; pest control and cleaning / hygiene checks.
- Stock quality: FIFO / FEFO checks, expiry and near-expiry lists, quarantine / hold and release by the responsible person,
  damaged goods, returns inspection, recalls (trace batch → locations / shipments).
- Transportation: vehicle / reefer pre-loading checks (pre-cooling, cleanliness, seals), in-transit temperature records,
  delivery proof, excursions in transit → NCR; link to site vehicles (7b) where it fits.
- Logistics KPIs: receiving rejection rate, excursions per zone / month, time out of range, on-time in-full (if data exists),
  damage rate, inventory accuracy from cycle-count checks.

**Out of scope:** full EDMS, BIM / drawings viewer, ERP / WMS / TMS (integrate by CSV import only), IoT live streams
(import logger files instead), payment, multi-tenancy.

## 5. Work packages and waves

All branch from the base. Each package: own branch, own draft PR against the base, own decision range, own DB prefix and ports.

| Wave | Package | Branch | Decisions | DB prefix | Ports (API/web) |
|---|---|---|---|---|---|
| 0 | S: spec `docs/specs/8-quality.md` | `claude/quality-spec` | D-308 … D-319 | — | — |
| 1 | Q0: foundation + NCR core | `claude/quality-q0-foundation` | D-320 … D-329 | `q0_` | 8200 / 3200 |
| 2 | Q1: ITP + Inspection Requests + punch / handover | `claude/quality-q1-itp` | D-330 … D-339 | `q1_` | 8201 / 3201 |
| 2 | Q2: materials, testing / lab, welding, calibration, competence | `claude/quality-q2-materials` | D-340 … D-349 | `q2_` | 8202 / 3202 |
| 2 | Q3: logistics (receiving, storage / cold chain, stock, transport) | `claude/quality-q3-logistics` | D-350 … D-359 | `q3_` | 8203 / 3203 |
| 3 | Q4: documents, audits, suppliers, KPIs / SPC / COPQ, AI tools, report packs, seed | `claude/quality-q4-analytics` | D-360 … D-369 | `q4_` | 8204 / 3204 |
| 4 | I: integration of Q0–Q4 | `claude/quality-integration` | D-370 … D-379 | `qi_` | 8205 / 3205 |

- **Q0** owns: sector profile on the project, Quality settings, responsible-person matrix, numbering, permissions / roles
  (QA/QC Manager, QC Inspector, Quality Engineer, Storekeeper / Warehouse QC, Responsible Person), navigation group
  "Quality" (profile-aware), shared models (NCR, NCR cost, root-cause analysis), NCR screens and the NCR → CA link,
  Alembic `q0_…` on top of `c0025`. Wave 2 starts only when Q0 is merged into the base (or, if Turki is away, branch wave 2
  from the Q0 branch head once Q0 CI is green, and say so in the PRs).
- **Wave 2** packages run in parallel (three agents). Migrations `q1_…`, `q2_…`, `q3_…` all on top of Q0's head; the
  integrator re-chains them.
- **Q4** runs after wave 2 is green, on top of the wave-2 integration or the three branches merged (orchestrator decides).
- **I** merges everything, re-chains Alembic linearly, bumps `CONTRACT_VERSION` to 0.18.0, regenerates the contract,
  runs the full 4-shard suite and full e2e, and opens the PR Turki merges.

Done for each package: every item in its part of the spec works in EN and AR (RTL checked), both profiles where relevant,
backend tests for every new rule, e2e for the main flows, demo seed data for both profiles, CI green, Fable review passed
(no open blocking finding), DECISIONS and PROGRESS updated, PR ready for review.

## 6. Orchestrator steps (the new session)

1. Read this file, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, the last 20 rows of `docs/DECISIONS.md`, `docs/specs/6-proposal.md`
   (style of a spec), one full module spec (e.g. `docs/specs/6d-field-assurance.md`) and `docs/LICENSING.md`.
2. Start Postgres, check `uv sync` / `npm ci` work (warm the caches once in the main checkout).
3. **Wave 0:** launch the spec writer (prompt 7.1, Opus 5.5 high). When it reports, launch the Fable spec reviewer
   (prompt 7.2, model `fable`). Send the findings back to the spec writer (SendMessage) until Fable passes it. Merge-ready
   spec PR; tell Turki in 3 lines (he may skim it; do not wait for him unless he said so).
4. **Wave 1:** launch Q0 (prompt 7.3). On its report, launch the Fable code reviewer (prompt 7.4) on the PR; loop fixes
   through the builder until passed and CI is green.
5. **Wave 2:** launch Q1, Q2, Q3 together (prompt 7.3 each, `isolation: worktree`). Review each with Fable as it reports.
6. **Wave 3:** Q4 the same way.
7. **Wave 4:** integrator (prompt 7.5), then a final Fable review of the integration PR.
8. Subscribe to every PR; fix CI yourself or through the owning builder; never wait idle on a red PR.
9. Report to Turki at the end in 3–5 short lines (he reads on his phone): what is built, **which single PR to merge**,
   what he must decide.

## 7. Prompts

Fill the `<…>` parts. Every builder prompt also gets the shared rules in 7.0.

### 7.0 Shared rules (append to every builder / integrator prompt)

```
Repo urkTish/HSE. Read docs/HANDOVER-quality.md (all), docs/CONVENTIONS.md, docs/PROGRESS.md, the last 20 rows of
docs/DECISIONS.md and docs/specs/8-quality.md (your sections in full, the rest skimmed).
Git: branch <branch> from <start point>; push after every working step (WIP commits with [skip ci]; the final commit
without it); open a draft PR against claude/hse-platform-build-kannxy right after the first push using the GitHub MCP
tools (load with ToolSearch; no gh CLI). Do not subscribe to the PR; the orchestrator does.
Commit messages end with:
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: <session url>
PR bodies end with:
  🤖 Generated with [Claude Code](https://claude.com/claude-code)

  <session url>
No model names anywhere else in commits, PRs or code.
Machine: shared with other agents. Postgres on localhost:5432 (hse/hse), never restart it; use only DBs prefixed <prefix>;
ports <api>/<web>; kill only your own PIDs. Run uv sync and npm ci in your worktree.
Checks before the final push: ruff, ruff format --check, mypy, alembic upgrade head + alembic check (+ downgrade/upgrade
round trip), openapi contract check, your new tests plus the existing test files of every module you touch, frontend lint,
typecheck, i18n parity check, build, and the e2e specs for your screens. Do not run the full 4-shard suite; CI does.
Tests never depend on today's date (use the clock fixtures). Do not bump CONTRACT_VERSION. Decisions only in <range>.
Alembic slug <slug>, down_revision <head>. EN and AR for every string, RTL checked. Both sector profiles where relevant.
Reuse existing services before adding new ones (corrective actions, inspections/checklists, attachments, PDF renderer,
notifications, audit log, KPI engine, AI tools, contractors, training/certificates, equipment, site vehicles).
When done: final push, update the PR description, then report to the orchestrator: branch, PR URL, last SHA, CI state,
what was built per spec item (and anything not finished), migrations, decisions used, anything Turki must decide,
deviations from the spec. Do not mark the PR ready; the orchestrator does after the Fable review and green CI.
```

### 7.1 Spec writer (Opus 5.5, high)

```
You are a senior Quality professional: QA/QC Manager on construction megaprojects and airports in KSA and in 3PL /
cold-chain logistics warehouses, IRCA ISO 9001 Lead Auditor (also ISO 19011, 45001, 14001), Lean Six Sigma Black Belt.
You write the Module Spec for a Quality (QA/QC) module of our HSE platform, in the same structure and depth as the
existing specs in docs/specs/ (read 0-foundation.md, 6-proposal.md and 6d-field-assurance.md first for format: roles,
records and fields, statuses and transitions, rules with IDs, screens per device, notifications, KPIs with formulas,
exports, AI tools, acceptance criteria per rule, Appendix A seed data, open questions).
Inputs: docs/HANDOVER-quality.md sections 2 and 4 are binding (two sector profiles, responsible person editable,
no client standard targeted, full scope, reuse list). Read the existing services and models the reuse list names so the
spec builds on them instead of duplicating them; name the existing tables/services you extend.
Write docs/specs/8-quality.md: one spec, with parts mapped to the packages in HANDOVER-quality.md section 5
(Q0 foundation + NCR, Q1 construction ITP/IR/punch/handover, Q2 materials/testing/welding/calibration/competence,
Q3 logistics, Q4 documents/audits/suppliers/KPIs/SPC/COPQ/AI/reports), so each builder can work from its own part.
Give every rule an ID (e.g. Q-NCR-07) and every acceptance criterion a testable form. Include Arabic names for the main
record types and statuses. Seed data (Appendix A): one Construction project and one Logistics site with realistic KSA
records. Mark unsure regulations [VERIFY]. Plain English, short sentences, tables where useful.
Decisions D-308 … D-319 for anything you settle that the handover leaves open. Branch claude/quality-spec, draft PR.
Report: PR URL, a 10-line summary of the spec, the open questions for Turki (do not block on them; give your default).
```

### 7.2 Fable spec reviewer (model `fable`)

```
You review a Module Spec, docs/specs/8-quality.md on branch claude/quality-spec (PR <n>) of urkTish/HSE, before
developers build from it. Read docs/HANDOVER-quality.md (sections 2, 4, 5 are binding), docs/CONVENTIONS.md, two existing
specs (docs/specs/6d-field-assurance.md and 4-third-party-cert.md) for the expected depth, and skim backend/app/models and
backend/app/services to check the reuse claims.
Check: (1) every handover scope item is covered and mapped to a package; nothing out of scope crept in; (2) both sector
profiles are handled wherever they differ; (3) "responsible person" is editable everywhere, no fixed client/consultant
sign-off; (4) no client standard is hard-coded; criteria and checklists are data; (5) rules have IDs, statuses have full
transition tables, acceptance criteria are testable; (6) reuse of existing tables/services is real (names exist) and no
parallel duplicate (e.g. a second corrective-action table) is introduced; (7) package boundaries let Q1, Q2, Q3 build in
parallel without editing the same files beyond the known shared ones; (8) KPI formulas are correct (DPMO, sigma level,
COPQ, first-time pass rate, SPC control limits); (9) logistics content is sound (cold-chain excursions, mapping, FEFO,
recalls, transport); (10) EN/AR, PDPL, Riyadh time, Hijri on packs.
Do not edit the spec. Report findings as a list, most severe first, each with: severity (blocking / should-fix / nit),
section and rule ID, the problem, and the exact change you propose. End with PASS (no blocking findings) or FAIL.
```

### 7.3 Package builder (Opus 5.5, high; one per package)

```
You build package <Q0|Q1|Q2|Q3|Q4>: <one-line title from HANDOVER-quality.md section 5> of the Quality module of the HSE
platform (urkTish/HSE). Your requirements are docs/specs/8-quality.md part <part> (binding) and HANDOVER-quality.md
sections 2 and 4. Other agents build the other packages in parallel; stay inside your part and the shared files the
handover lists. Backend first (models, migration, services, routers, tests), then frontend (screens on phone and desk,
EN/AR), then e2e and seed data for both sector profiles where your part applies.
<shared rules 7.0, with: branch claude/quality-<pkg>, start point <origin/claude/hse-platform-build-kannxy or Q0 head>,
prefix <qN_>, ports <api>/<web>, range <D-…>, slug <qN_…>, head <down_revision>>
If a Fable review lists findings on your PR, the orchestrator will send them to you: fix every blocking and should-fix
finding (or answer why not, with evidence), push, and report again.
```

### 7.4 Fable code reviewer (model `fable`; one per package PR)

```
You review pull request <n> (branch <branch>) of urkTish/HSE: package <name> of the Quality module. Requirements:
docs/specs/8-quality.md part <part>, docs/HANDOVER-quality.md, docs/CONVENTIONS.md. Check out the branch in your own
worktree (git fetch origin <branch>) and read the diff against origin/claude/hse-platform-build-kannxy (for wave 2,
against the Q0 head the package started from).
Check, with file:line evidence: (1) every rule and acceptance criterion of the part is implemented and tested (list any
missing by rule ID); (2) correctness: state transitions, permissions per role and project scope, responsible-person
checks, sector-profile gating, Riyadh dates, numbering races, NCR/CA links, calculations (pass/fail, excursions, KPIs);
(3) security: authorisation on every endpoint, project scoping in SQL, file uploads through attachments (scan + shrink),
no secrets, PDPL fields masked as elsewhere; (4) reuse instead of duplication; (5) migration matches models, downgrade
works, indexes for list filters; (6) EN/AR parity and RTL, phone layouts; (7) tests are deterministic (clock fixtures,
no sleeps on wall time); (8) conventions in CONVENTIONS.md.
You may run tests locally (DB prefix rv_<pkg>_, ports 8290/3290) but do not push or edit the branch.
Report findings most severe first: severity (blocking / should-fix / nit), file:line, problem, concrete fix. End with
PASS (no blocking or should-fix findings left) or FAIL.
```

### 7.5 Integrator (Opus 5.5, high)

```
You integrate the Quality packages Q0–Q4 of urkTish/HSE into one branch Turki can merge in one go. Read
docs/HANDOVER-quality.md (all, especially section 3), docs/CONVENTIONS.md and docs/specs/8-quality.md.
Inputs: <branches and PRs with last SHAs>. Create claude/quality-integration from origin/claude/hse-platform-build-kannxy,
merge the packages in order Q0, Q1, Q2, Q3, Q4 with merge commits, and resolve every conflict keeping all behaviour.
Re-chain Alembic linearly (c0025 → q0 … → q1 … → q2 … → q3 … → q4 …), editing down_revision only in this branch;
upgrade, check and a downgrade-to-c0025 round trip must pass. Bump CONTRACT_VERSION to 0.18.0 and regenerate
openapi.yaml and schema.d.ts with the repo tools. Keep all i18n keys (parity check), all navigation entries (profile-aware),
all seed data (both profiles), DECISIONS rows in numeric order plus one integration decision in D-370 … D-379, and one
PROGRESS section per package plus an integration section.
Add cross-package tests where packages meet (e.g. failed lab test → NCR → CA; temperature excursion → NCR → quarantine;
calibration out of tolerance → affected inspections; KPIs counting records from every package; read-only licence mode
still blocks Quality writes but allows exports).
The machine is free now: run the full backend suite in 4 shards (qi_test_1..4) and the full e2e suite; fix everything.
<shared rules 7.0, with branch claude/quality-integration, prefix qi_, ports 8205/3205, range D-370 … D-379>
Open a draft PR whose body starts with "Merge this one instead of the package PRs" and lists them.
Report: PR URL, final SHA, migration chain, conflict resolutions, defects found and fixed, shard totals, e2e totals,
what Turki must decide.
```

## 8. Report to Turki (end of build)

3–5 lines: what is built, the single PR to merge, the 2–3 decisions he must make, where the demo data is (Construction
project and Logistics site in the seed).
