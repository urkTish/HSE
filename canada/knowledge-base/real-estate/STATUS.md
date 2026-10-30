# Agent 02 — Real estate · STATUS

Phase 1 · 2026-10-30 · lane `knowledge-base/real-estate/`

## Done

| File | Contents |
|---|---|
| `METHODOLOGY.md` | Vocabulary (benchmark, average, median, survey, asking); source register of 15 sources with URL, content, frequency, geography, terms of use and a store/fetch decision; how the figures were produced; stored-versus-on-demand table; **on-demand retrieval design for Agent 05** (StatCan WDS vectors for 20 CMAs, Bank of Canada Valet, link-out targets, caching, display line, build-step licence filter) |
| `market-snapshot-2026-10.md` | 20 CMAs: MLS® HPI composite and apartment benchmarks (September 2026) with y/y, 5- and 10-year annualised change and distance from peak; CMHC two-bedroom purpose-built and condominium survey rents and vacancy (October 2025); interpretation |
| `rules-by-province.md` | Who may buy by status (federal ban, end date 1 January 2027, exemptions); BC/ON/NS foreign or non-resident taxes; transfer taxes and first-time-buyer relief with a $600,000 comparison; vacancy taxes; 2026 rent limits and notice for all 10 provinces (PEI unverified); short-term rental rules in BC, Montréal, Toronto |
| `investment-model.md` | Formulas (down payment, insurance premium, semi-annual-compounding payment, stress test, GDS/TDS, transfer tax, NOI, yields, cash flow, appreciation scenarios); worked example on declared hypothetical inputs; 15-CMA screening yield table (estimate); calculator spec for Agent 05 |
| 96 `re-*.json` records | 20 two-bedroom purpose-built rents, 20 vacancy rates, 15 condominium two-bedroom rents, 20 HPI composite and 19 HPI apartment benchmarks, 2 national HPI |
| 32 `nat-*.json` records | 5 federal (`nat-ca-*`), 7 BC, 6 ON, 3 QC, 1 AB, 1 SK, 2 MB, 2 NB, 3 NS, 1 NL, 1 PE; all `responsible_agent: agent-02` |

**Validator:** `node knowledge-base/scripts/validate.mjs knowledge-base/real-estate`
→ `128 record(s) checked, 0 failed, 0 warning(s), 0 non-record JSON file(s) skipped.`

Also edited: own section of `TASKS.md` (02-1 to 02-5 done, 02-6 added
for leftovers); four lines appended to `OPEN-QUESTIONS.md`.

## In progress / parked

| Item | Reason | Next step |
|---|---|---|
| Kelowna CMA board price | AOR September 2026 release not found (news page 404; PDF pattern 404). Only CREA `INTERIOR_BC` (a much larger region) is stored, labelled | Fetch AOR "Central Okanagan" benchmark from the release PDF when the URL is known |
| Sherbrooke CMA price | CREA publishes `ESTRIE` only; QPAREB/Centris median not retrieved | Fetch QPAREB Sherbrooke CMA quarterly median (label `median_price`, `transaction`) |
| PEI 2026 allowable rent increase | princeedwardisland.ca blocks automated fetches; only secondary sources (2%) | Read the Director's Gazette notice manually or via IRAC; record is null until then (`nat-pe-rent-increase-2026`) |
| Eviction rules (landlord's use, renovation, notice, compensation) | Not reached in the time budget | One line per province from each tenancy authority |
| Transfer costs AB, SK, NL, PEI; Quebec City and Sherbrooke upper brackets | Not reached | Add `nat-*` records |
| Vacant-unit taxes Ottawa, Hamilton; STR rules Calgary, Edmonton, Ottawa, Halifax; Toronto STR night cap; BC SVT taxable regions (page 404) | Not reached / page error | Add `nat-*` records |
| Vancouver Empty Homes Tax 2026 rate | vancouver.ca 403 twice; 3% from search summary; 5% proposal status unknown | Re-check the by-law amendment of July 2026 |

## Key findings

1. **The federal ban on non-Canadian buyers is scheduled to end on 1 January 2027**; no extension had been announced on official sites by 30 October 2026. While it runs, work-permit holders with 183+ days of validity may buy one home, and PRs, citizens and protected persons are unaffected. The BC 20%, Ontario 25% and Nova Scotia 10% foreign/non-resident taxes are separate and do not expire with it (`nat-ca-non-canadian-residential-purchase-prohibition`, `nat-on-non-resident-speculation-tax`).
2. **Nova Scotia's non-resident deed transfer tax doubled to 10%** (agreements from April 2025); a newcomer who proves NS residency within 12 months avoids it (`nat-ns-non-resident-deed-transfer-tax`).
3. **Ontario's high-growth markets are 28–33% below their February 2022 peaks** and still falling (Toronto, Hamilton–Burlington, Kitchener–Waterloo, London), while Prairie, Quebec and Atlantic markets sit within a few percent of peaks set in 2024–2026 (`market-snapshot-2026-10.md`).
4. **Condominium apartment prices are falling fastest** (Kitchener–Waterloo −12.8% y/y, London −9.6%, Moncton −8.9%), good for owner-occupiers, a warning for investors.
5. **Rental vacancy rose in 19 of 20 centres in October 2025**; Kelowna 6.4% and Calgary 5.0% are the loosest, Charlottetown 1.6% and St. John's 2.0% the tightest. The October 2026 survey (due December 2026) will update this.
6. **Cheapest two-bedroom survey rents** are in Quebec and Atlantic Canada (Sherbrooke $1,062, Québec $1,277, Charlottetown $1,300, Montréal $1,346); highest in Vancouver ($2,363), Victoria, Kelowna and Toronto. Rent growth is fastest where rents are lowest (Sherbrooke +9.8%, St. John's +7.6%, Montréal +7.2%).
7. **Rent limits for 2026**: BC 2.3%, Ontario 2.1% (post-2018 units uncapped), Manitoba 1.8%, NB 3%, NS 5%, Quebec TAL base 3.1%; no cap in Alberta, Saskatchewan, NL.
8. **Short-term rental is not a viable investment plan** in BC cities of 10,000+, Toronto or Montréal (principal-residence rules).
9. **Hypothetical worked example**: a $600,000 Ontario condo with 20% down at a hypothetical 4.5% rate and $2,400 rent loses about $17,000 a year before tax; screening gross yields run from about 5% (Vancouver, Montréal) to about 10% (Edmonton), before condo fees and taxes (`investment-model.md`).
10. **Licensing**: CREA and CMHC terms forbid republishing their figures; Statistics Canada republishes the CMHC rents under an open licence (all 20 values matched), so the public map can show rents but should only link to benchmark prices.

## Open questions added (to `OPEN-QUESTIONS.md`)

- The user's immigration status on the purchase date (decides the federal ban and BC/ON/NS foreign taxes).
- Rent first and buy later? Own home only, or also an investment?
- Bedrooms and home type needed (decides which series are compared).
- Will the map be private or published (CREA/CMHC terms; ask for permission or link only)?

## Next step

- Coordinator: decide (with the user) whether the map is private; record in `DECISIONS.md` how CREA/CMHC figures are handled.
- Agent 05: implement `METHODOLOGY.md` §5 (StatCan WDS vectors, Valet rate prefill, link-outs, build-step licence filter) and the calculator in `investment-model.md` §5.
- Agent 02, next session: re-check the federal ban before 1 December 2026; refresh all `re` records when CREA (17 November 2026) and CMHC (December 2026) publish; clear the parked items above.
