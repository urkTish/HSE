# Market snapshot — October 2026 (data to September 2026 for prices, October 2025 for rents)

Agent 02 · researched 2026-10-30 · next review 2026-12-29 (60 days; the CMHC
October 2026 survey is due around December 2026 and CREA releases October data
on 17 November 2026)

This snapshot covers 20 census metropolitan areas (Charlottetown is a census
agglomeration) across every region. It answers two questions per place: what
does a typical home sell for, and what does a two-bedroom rental cost and how
easy is it to find one. Every number is a record in this folder; the record IDs
are in the last column. Methods and licences are in `METHODOLOGY.md`.

**Read the labels before comparing columns.**

- Prices are **MLS® HPI benchmark prices** (CREA): the modelled price of a
  typical home with fixed attributes, built from **completed sales**. They are
  not averages, not medians and not asking prices. Composite = all property
  types; apartment = apartment/condominium units of all sizes.
- Rents are **CMHC survey averages** for October 2025: what sitting tenants
  and vacant units rent for in purpose-built apartments (and, separately, in
  condominiums rented by their owners). They are not **asking** rents; a
  newcomer signing a new lease today will usually pay more than the survey
  average. No asking rents are stored in Phase 1.
- Price areas are **board-defined CREA market areas**, which do not coincide
  with the CMA boundaries used for rents. Kelowna, Sherbrooke and Charlottetown
  have no CMA-level HPI: the nearest series is a region or the whole province,
  and it is labelled.
- Letters in brackets are CMHC quality grades: a excellent, b very good, c
  good, d poor (use with caution). "n.s. (++)" = CMHC says the change is not
  statistically significant.
- y/y, 5-year and 10-year annualised changes and "vs peak" are computed by
  Agent 02 from the CREA series (nominal, not inflation-adjusted, not
  seasonally adjusted).
- **Licence.** CREA and CMHC terms do not allow republishing these figures.
  This file is internal analysis with attribution; the public map must link to
  the source or show the Statistics Canada open-licence copy of the rents
  (`METHODOLOGY.md` §4–5).

### Table A — Prices: MLS® HPI benchmark, September 2026 (index-based benchmark from completed sales; not average, not median, not asking)

| CMA | HPI market area (CREA) | Composite benchmark | y/y | Apartment benchmark | y/y | 5-yr ann. | 10-yr ann. | vs peak (month) | Records |
|---|---|---|---|---|---|---|---|---|---|
| Vancouver | GREATER_VANCOUVER | $1,075,900 | -5.5% | $682,500 | -6.2% | -0.5% | +0.7% | -14.1% (2022-04) | `re-bc-greater-vancouver-hpi-composite-2026-09`, `re-bc-greater-vancouver-hpi-apartment-2026-09` |
| Victoria | VICTORIA | $877,000 | -0.1% | $542,800 | +0.3% | +1.4% | +4.9% | -9.7% (2022-04) | `re-bc-victoria-hpi-composite-2026-09`, `re-bc-victoria-hpi-apartment-2026-09` |
| Kelowna | INTERIOR_BC | $664,600 | +1.4% | $434,700 | +4.0% | +1.3% | +5.4% | -8.6% (2022-04) | `re-bc-interior-bc-hpi-composite-2026-09`, `re-bc-interior-bc-hpi-apartment-2026-09` |
| Calgary | CALGARY | $569,200 | +0.2% | $304,900 | -6.0% | +4.5% | +3.2% | -3.5% (2024-06) | `re-ab-calgary-hpi-composite-2026-09`, `re-ab-calgary-hpi-apartment-2026-09` |
| Edmonton | EDMONTON | $416,700 | -0.1% | $197,800 | -0.9% | +2.4% | +1.8% | -3.8% (2025-06) | `re-ab-edmonton-hpi-composite-2026-09`, `re-ab-edmonton-hpi-apartment-2026-09` |
| Saskatoon | SASKATOON | $439,600 | +2.5% | $265,200 | +1.9% | +4.9% | +3.2% | -2.0% (2026-06) | `re-sk-saskatoon-hpi-composite-2026-09`, `re-sk-saskatoon-hpi-apartment-2026-09` |
| Regina | REGINA | $343,900 | +2.9% | $234,500 | +6.8% | +2.1% | +1.5% | -3.5% (2026-06) | `re-sk-regina-hpi-composite-2026-09`, `re-sk-regina-hpi-apartment-2026-09` |
| Winnipeg | WINNIPEG | $392,100 | +3.1% | $237,500 | +1.9% | +3.5% | +4.2% | -2.8% (2026-06) | `re-mb-winnipeg-hpi-composite-2026-09`, `re-mb-winnipeg-hpi-apartment-2026-09` |
| Toronto | GREATER_TORONTO | $917,600 | -4.6% | $527,200 | -6.7% | -3.0% | +2.6% | -28.3% (2022-02) | `re-on-greater-toronto-hpi-composite-2026-09`, `re-on-greater-toronto-hpi-apartment-2026-09` |
| Ottawa | OTTAWA | $623,500 | -0.3% | $380,800 | -6.1% | +0.8% | +5.8% | -11.3% (2022-03) | `re-on-ottawa-hpi-composite-2026-09`, `re-on-ottawa-hpi-apartment-2026-09` |
| Hamilton | HAMILTON_BURLINGTON | $718,600 | -5.1% | $447,400 | -7.6% | -3.1% | +4.0% | -30.3% (2022-02) | `re-on-hamilton-burlington-hpi-composite-2026-09`, `re-on-hamilton-burlington-hpi-apartment-2026-09` |
| Kitchener–Cambridge–Waterloo | KITCHENER_WATERLOO | $630,200 | -5.6% | $356,300 | -12.8% | -3.8% | +5.6% | -33.2% (2022-02) | `re-on-kitchener-waterloo-hpi-composite-2026-09`, `re-on-kitchener-waterloo-hpi-apartment-2026-09` |
| London | LONDON_ST_THOMAS | $552,500 | -2.6% | $317,100 | -9.6% | -1.9% | +8.6% | -29.2% (2022-02) | `re-on-london-st-thomas-hpi-composite-2026-09`, `re-on-london-st-thomas-hpi-apartment-2026-09` |
| Montréal | MONTREAL_CMA | $578,200 | +0.0% | $427,900 | +0.1% | +4.1% | +7.1% | -3.0% (2026-06) | `re-qc-montreal-cma-hpi-composite-2026-09`, `re-qc-montreal-cma-hpi-apartment-2026-09` |
| Québec | QUEBEC_CMA | $445,800 | +4.7% | $311,200 | +6.8% | +9.1% | +6.8% | -2.7% (2026-04) | `re-qc-quebec-cma-hpi-composite-2026-09`, `re-qc-quebec-cma-hpi-apartment-2026-09` |
| Sherbrooke | ESTRIE | $475,400 | +7.3% | $324,400 | +4.2% | +9.6% | +10.2% | -4.1% (2026-08) | `re-qc-estrie-hpi-composite-2026-09`, `re-qc-estrie-hpi-apartment-2026-09` |
| Halifax | HALIFAX_DARTMOUTH | $541,700 | -4.1% | $423,500 | -5.3% | +3.8% | +7.4% | -5.4% (2026-05) | `re-ns-halifax-dartmouth-hpi-composite-2026-09`, `re-ns-halifax-dartmouth-hpi-apartment-2026-09` |
| Moncton | GREATER_MONCTON | $377,400 | +0.4% | $311,800 | -8.9% | +6.4% | +10.2% | -6.6% (2026-05) | `re-nb-greater-moncton-hpi-composite-2026-09`, `re-nb-greater-moncton-hpi-apartment-2026-09` |
| St. John's | ST_JOHNS_NL | $421,800 | +6.8% | $261,400 | +5.3% | +7.1% | +4.0% | -1.4% (2026-07) | `re-nl-st-johns-hpi-composite-2026-09`, `re-nl-st-johns-hpi-apartment-2026-09` |
| Charlottetown | PRINCE_EDWARD_ISLAND | $377,900 | +0.5% | not published | — | +3.1% | +7.8% | -2.7% (2026-07) | `re-pe-prince-edward-island-hpi-composite-2026-09` |
| Canada | AGGREGATE | $651,400 | -3.4% | $455,700 | -4.9% | -1.6% | +2.8% | -22.5% (2022-03) | `re-ca-national-hpi-composite-2026-09`, `re-ca-national-hpi-apartment-2026-09` |

### Table B — Rents: CMHC Rental Market Survey, October 2025 (survey averages of sitting tenants and vacant units; not asking rents)

| CMA | 2-bed purpose-built avg rent | Oct 2024 | Same-sample change | Vacancy, all apartments (2-bed) | 2-bed rental condo avg rent | Condo vacancy | Records |
|---|---|---|---|---|---|---|---|
| Vancouver | $2,363 (a) | $2,314 | +2.2% (b) | 3.7% (3.3%) | $2,900 (b) | 1.5% | `re-bc-vancouver-cma-cmhc-rent-2bed-2025-10`, `re-bc-vancouver-cma-cmhc-vacancy-2025-10`, `re-bc-vancouver-cma-cmhc-condo-rent-2bed-2025-10` |
| Victoria | $2,120 (a) | $1,993 | +5.1% (b) | 3.3% (3.0%) | $2,688 (c) | 0.3% | `re-bc-victoria-cma-cmhc-rent-2bed-2025-10`, `re-bc-victoria-cma-cmhc-vacancy-2025-10`, `re-bc-victoria-cma-cmhc-condo-rent-2bed-2025-10` |
| Kelowna | $2,118 (a) | $1,935 | +2.4% (c) | 6.4% (5.2%) | suppressed / not surveyed | — | `re-bc-kelowna-cma-cmhc-rent-2bed-2025-10`, `re-bc-kelowna-cma-cmhc-vacancy-2025-10` |
| Calgary | $1,914 (a) | $1,882 | n.s. (++) | 5.0% (5.7%) | $2,030 (b) | 2.2% | `re-ab-calgary-cma-cmhc-rent-2bed-2025-10`, `re-ab-calgary-cma-cmhc-vacancy-2025-10`, `re-ab-calgary-cma-cmhc-condo-rent-2bed-2025-10` |
| Edmonton | $1,603 (a) | $1,536 | +3.5% (a) | 3.8% (3.8%) | $1,655 (b) | 1.7% | `re-ab-edmonton-cma-cmhc-rent-2bed-2025-10`, `re-ab-edmonton-cma-cmhc-vacancy-2025-10`, `re-ab-edmonton-cma-cmhc-condo-rent-2bed-2025-10` |
| Saskatoon | $1,548 (a) | $1,471 | +5.2% (a) | 3.3% (3.1%) | $1,590 (b) | 0.8% | `re-sk-saskatoon-cma-cmhc-rent-2bed-2025-10`, `re-sk-saskatoon-cma-cmhc-vacancy-2025-10`, `re-sk-saskatoon-cma-cmhc-condo-rent-2bed-2025-10` |
| Regina | $1,473 (a) | $1,415 | +4.2% (a) | 2.7% (2.2%) | $1,460 (b) | 1.3% | `re-sk-regina-cma-cmhc-rent-2bed-2025-10`, `re-sk-regina-cma-cmhc-vacancy-2025-10`, `re-sk-regina-cma-cmhc-condo-rent-2bed-2025-10` |
| Winnipeg | $1,571 (a) | $1,507 | +1.9% (b) | 2.8% (3.0%) | $1,468 (c) | 1.1% | `re-mb-winnipeg-cma-cmhc-rent-2bed-2025-10`, `re-mb-winnipeg-cma-cmhc-vacancy-2025-10`, `re-mb-winnipeg-cma-cmhc-condo-rent-2bed-2025-10` |
| Toronto | $2,046 (a) | $1,974 | +3.4% (b) | 3.0% (2.5%) | $2,891 (a) | 0.9% | `re-on-toronto-cma-cmhc-rent-2bed-2025-10`, `re-on-toronto-cma-cmhc-vacancy-2025-10`, `re-on-toronto-cma-cmhc-condo-rent-2bed-2025-10` |
| Ottawa | $1,926 (a) | $1,880 | +3.4% (b) | 3.0% (2.9%) | $2,503 (d) | 0.6% | `re-on-ottawa-cma-cmhc-rent-2bed-2025-10`, `re-on-ottawa-cma-cmhc-vacancy-2025-10`, `re-on-ottawa-cma-cmhc-condo-rent-2bed-2025-10` |
| Hamilton | $1,656 (a) | $1,632 | +1.6% (c) | 3.6% (2.9%) | $2,831 (c) | 1.2% | `re-on-hamilton-cma-cmhc-rent-2bed-2025-10`, `re-on-hamilton-cma-cmhc-vacancy-2025-10`, `re-on-hamilton-cma-cmhc-condo-rent-2bed-2025-10` |
| Kitchener–Cambridge–Waterloo | $1,832 (a) | $1,766 | +3.3% (b) | 4.1% (4.0%) | $2,197 (a) | 0.8% | `re-on-kitchener-cambridge-waterloo-cma-cmhc-rent-2bed-2025-10`, `re-on-kitchener-cambridge-waterloo-cma-cmhc-vacancy-2025-10`, `re-on-kitchener-cambridge-waterloo-cma-cmhc-condo-rent-2bed-2025-10` |
| London | $1,651 (a) | $1,548 | +4.1% (b) | 4.0% (4.0%) | $2,132 (b) | 0.2% | `re-on-london-cma-cmhc-rent-2bed-2025-10`, `re-on-london-cma-cmhc-vacancy-2025-10`, `re-on-london-cma-cmhc-condo-rent-2bed-2025-10` |
| Montréal | $1,346 (a) | $1,176 | +7.2% (a) | 2.9% (2.9%) | $1,826 (a) | 2.1% | `re-qc-montreal-cma-cmhc-rent-2bed-2025-10`, `re-qc-montreal-cma-cmhc-vacancy-2025-10`, `re-qc-montreal-cma-cmhc-condo-rent-2bed-2025-10` |
| Québec | $1,277 (a) | $1,159 | +6.1% (b) | 2.4% (2.5%) | $1,377 (a) | 0.6% | `re-qc-quebec-cma-cmhc-rent-2bed-2025-10`, `re-qc-quebec-cma-cmhc-vacancy-2025-10`, `re-qc-quebec-cma-cmhc-condo-rent-2bed-2025-10` |
| Sherbrooke | $1,062 (a) | $1,002 | +9.8% (b) | 2.7% (3.0%) | suppressed / not surveyed | — | `re-qc-sherbrooke-cma-cmhc-rent-2bed-2025-10`, `re-qc-sherbrooke-cma-cmhc-vacancy-2025-10` |
| Halifax | $1,826 (a) | $1,707 | +6.7% (b) | 2.7% (2.4%) | $2,465 (b) | 2.5% | `re-ns-halifax-cma-cmhc-rent-2bed-2025-10`, `re-ns-halifax-cma-cmhc-vacancy-2025-10`, `re-ns-halifax-cma-cmhc-condo-rent-2bed-2025-10` |
| Moncton | $1,453 (a) | $1,353 | +4.7% (c) | 3.9% (4.2%) | suppressed / not surveyed | — | `re-nb-moncton-cma-cmhc-rent-2bed-2025-10`, `re-nb-moncton-cma-cmhc-vacancy-2025-10` |
| St. John's | $1,361 (b) | $1,250 | +7.6% (b) | 2.0% (1.7%) | suppressed / not surveyed | — | `re-nl-st-johns-cma-cmhc-rent-2bed-2025-10`, `re-nl-st-johns-cma-cmhc-vacancy-2025-10` |
| Charlottetown (CA) | $1,300 (a) | $1,196 | +4.7% (d) | 1.6% (1.9%) | suppressed / not surveyed | — | `re-pe-charlottetown-ca-cmhc-rent-2bed-2025-10`, `re-pe-charlottetown-ca-cmhc-vacancy-2025-10` |

Sources: CREA, MLS® HPI data download `MLS_HPI_Oct_2026.zip` (data to
September 2026), accessed 2026-10-30; CMHC, Rental Market Survey data tables
2025 (one workbook per centre), accessed 2026-10-30, cross-checked against
Statistics Canada table 34-10-0133-01.

## What the snapshot says

*Professional interpretation by Agent 02 of the records above; not a forecast.*

1. **Two different price regimes.** The Ontario markets that ran up fastest
   to early 2022 are now 28–33% below their February 2022 benchmark peaks
   (Toronto `re-on-greater-toronto-hpi-composite-2026-09`, Hamilton–Burlington,
   Kitchener–Waterloo, London–St. Thomas) and still falling year over year.
   The Prairies, Quebec, St. John's and Charlottetown sit within about 1–4% of
   peaks set between 2024 and 2026, and their composites are flat or rising year
   over year. Vancouver (−14%), Ottawa (−11%) and
   Victoria (−10%) lie in between.
2. **Condominium apartments are the weakest segment.** Apartment benchmarks
   fell faster than composites in nearly every Ontario market (Kitchener–Waterloo
   −12.8%, London −9.6%, Hamilton −7.6%, Toronto −6.7%), in Calgary (−6.0%) and
   Ottawa (−6.1%), and in Moncton (−8.9%). For a buyer this is a better entry
   price; for an investor it signals supply that has outrun demand.
3. **Rental vacancy rose in 19 of the 20 centres in October 2025** (St. John's
   dipped from 2.1% to 2.0%). Purpose-built vacancy was at or above 3% in 12 of
   the 20, with Kelowna (6.4%),
   Calgary (5.0%), Kitchener–Cambridge–Waterloo (4.1%) and London (4.0%) the
   loosest. Only Charlottetown (1.6%) and St. John's (2.0%) remained tight. A
   renter arriving in 2026–27 should have more choice than in 2022–23; the
   October 2026 survey (due December 2026) will confirm or not.
4. **Survey rent growth is slowing in the West and Ontario but still high in
   Quebec and Atlantic Canada.** Same-sample two-bedroom rent growth was
   +1.6% to +3.5% in Hamilton, Winnipeg, Vancouver, Kelowna, Kitchener–
   Cambridge–Waterloo, Toronto, Ottawa and Edmonton, but +6% to +10% in
   Sherbrooke, St. John's, Montréal, Halifax and Québec. Calgary's change was
   not statistically significant.
5. **Cheapest two-bedroom survey rents**: Sherbrooke ($1,062), Québec
   ($1,277), Charlottetown ($1,300), Montréal ($1,346), St. John's ($1,361).
   **Highest**: Vancouver ($2,363), Victoria ($2,120), Kelowna ($2,118),
   Toronto ($2,046). Condominium rentals cost more than purpose-built units in
   every centre except Regina and Winnipeg; in Toronto and Hamilton the gap is
   over $800 a month, which is closer to what a newcomer will see in listings.
6. **Affordability ordering is not the same as investment ordering.** Low
   prices (Edmonton apartments $197,800, Regina, Winnipeg) come with lower
   long-run appreciation (10-year annualised +1.5% to +4.2%), while the
   strongest 10-year gains (Estrie +10.2%, Greater Moncton +10.2%, London
   +8.6%, PEI +7.8%) include markets that have since fallen hard (London).
   See `investment-model.md` for the yield screen.

## What this snapshot does not cover

- Neighbourhood variation inside each CMA (CMHC zones and board sub-areas
  exist and can be fetched on demand).
- Detached, townhouse and one-storey benchmarks (in the CREA file, not stored).
- Average and median sale prices, sales volumes, new listings and months of
  inventory from boards (link out; Phase 2 if needed).
- Asking rents (listing platforms; never stored).
- New-construction prices (Statistics Canada NHPI, table 18-10-0205-01).
- Hazard and insurance effects on price (Agent 04's hazard records, Phase 2).
