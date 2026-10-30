# Agent 02 — Canadian Real Estate & Property Investment Analyst

Charter: `canada/SPEC.md` §6. Common rules: `agents/00-common-rules.md`.
Lane: `canada/knowledge-base/real-estate/`.

## Phase 1 deliverables

1. **`METHODOLOGY.md`** — the source register: CREA national statistics and
   the MLS Home Price Index; the provincial and local boards; CMHC (Rental
   Market Survey, Housing Market Information Portal, mortgage and consumer
   reports); Statistics Canada (New Housing Price Index, CPI rent, Canadian
   Housing Statistics Program); municipal assessment bodies; listing
   platforms (asking figures only). For each: URL, what it gives, how often,
   geography, and its terms of use or licence, with a line on what the map
   may store versus must fetch or link on demand. Define the on-demand
   retrieval design for Agent 05: which pages or endpoints, what is cached
   and for how long, and what is displayed (figure, period, source, date).
2. **`market-snapshot-2026-10.md`** plus `re` records for fifteen to twenty
   census metropolitan areas across all regions (for example Vancouver,
   Victoria, Kelowna, Calgary, Edmonton, Saskatoon, Regina, Winnipeg,
   Toronto, Ottawa, Hamilton, Kitchener–Waterloo, London, Montréal, Québec,
   Sherbrooke, Halifax, Moncton, St. John's, Charlottetown). For each: the
   latest MLS HPI composite and apartment benchmark (or the board's figure
   when the HPI is not published for that market), and the latest CMHC
   survey average rent for a two-bedroom purpose-built unit with the vacancy
   rate. Every record carries `period`, `figure_kind`, the source and date.
   Omit what cannot be sourced; never estimate a price.
3. **`rules-by-province.md`** plus `nat-<prov>-*` records (you may create
   `nat` records; set `responsible_agent: agent-02`) for the numeric rules:
   who may buy by immigration status (the federal Prohibition on the
   Purchase of Residential Property by Non-Canadians Act, its current end
   date and exemptions, taking statuses from Agent 01's framing); provincial
   and municipal non-resident, speculation and vacancy taxes; land-transfer
   taxes and first-time-buyer rebates; rent-increase limits for the current
   year; notice and eviction rules in one line each; short-term rental
   restrictions in the major cities.
4. **`investment-model.md`** — the calculation template: purchase cost,
   down payment and mortgage default insurance tiers, the federal stress
   test rule as currently in force, closing costs by category with typical
   ranges labelled `estimate`, operating expenses, gross and net yield, cash
   flow, and an appreciation scenario. Show the formulas and one fully
   worked example on inputs you declare hypothetical. Do not store a
   mortgage rate as a fact; show where the map retrieves it.
5. **`STATUS.md`** and your open questions in `OPEN-QUESTIONS.md`.

## Standards specific to this lane

- Distinguish benchmark, average and median; survey, asking and
  transaction; listings and completed sales, in every table.
- Set `next_review` 60 days out for market observations.
