# Agent 01 — Canada National Intelligence & Advisory Agent

Charter: `canada/SPEC.md` §5. Common rules: `agents/00-common-rules.md`.
Lane: `canada/knowledge-base/national/`.

## Phase 1 deliverables

1. **`immigration-pathways.md`** — Express Entry (Federal Skilled Worker,
   Canadian Experience Class, Federal Skilled Trades; how the Comprehensive
   Ranking System works; the category-based selection categories in force
   this year and recent draw dates and cut-offs with their dates); Provincial
   Nominee Programmes, one short subsection per province and territory naming
   the streams relevant to skilled workers and whether they are Express
   Entry-aligned; family sponsorship; work permits (LMIA-based and
   International Mobility Program) and study-to-work routes; the current
   Immigration Levels Plan targets; processing times and fees as of the
   access date. End with a table "what each status allows" (work, study,
   provincial health coverage, buying residential property, children's
   schooling, path to permanent residence) built from your `nat` records.
2. **`taxes-by-province.md`** plus one `nat-<prov>-income-and-sales-tax-2026`
   record per province and territory: federal and provincial brackets for the
   current tax year, basic personal amounts, sales taxes (GST, HST, PST,
   QST), notable payroll items (CPP/QPP, EI, QPIP), and the provincial
   health premium where one exists. Then worked take-home examples at three
   gross salaries of your choosing, labelled `estimate`, with the method
   shown.
3. **`healthcare-by-province.md`** plus one `nat-<prov>-health-coverage`
   record per province and territory: who is eligible by immigration status,
   the newcomer waiting period if any, how to apply, drug coverage model,
   and the latest official share of residents without a regular health-care
   provider (Statistics Canada or CIHI) with its survey year.
4. **`employment-and-credentials.md`** — regulated versus unregulated
   occupations; how to identify the regulator (CICIC) and the typical
   licensing process, cost and duration; how to read Job Bank outlooks;
   a placeholder section for the user's own occupation, to be filled once
   `USER-PROFILE.md` names it.
5. **`quebec-language-rules.md`** plus `nat-qc-*` records: the Charter of the
   French Language as it affects newcomers (language of work and of public
   services; eligibility for English-language schooling and how it applies
   to children of temporary and permanent residents; francisation
   obligations), with the dates of the latest amendments.
6. **`STATUS.md`** and your open questions in `OPEN-QUESTIONS.md`.

## Standards specific to this lane

- Every rule names its jurisdiction and whether it is in force or proposed.
- Where a rule depends on the user's status, say so and point to the
  unknown in `USER-PROFILE.md` instead of assuming a status.
- Processing times and draw data are dated snapshots; set `next_review` 30
  days out.
