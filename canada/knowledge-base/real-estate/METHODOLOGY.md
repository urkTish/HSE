# Real estate — methodology, source register and on-demand retrieval design

Agent 02 · Phase 1 · researched 2026-10-30 · lane `canada/knowledge-base/real-estate/`

This file says where every price, rent and rule in this lane comes from, what
each figure means, what the licence lets us keep, and how the map (Agent 05)
should fetch market figures when it shows them instead of relying on stored
copies.

## 1. Vocabulary used in every table and record

| Term | Meaning | `figure_kind` / `metric` |
|---|---|---|
| **Benchmark price** (MLS® HPI) | Price of a modelled "typical" home whose attributes are held constant, estimated from **completed MLS® sales**. It is neither an average nor a median, and it is not an asking price. | `index` / `benchmark_price` |
| **Average price** | Sum of sale prices ÷ number of sales in the period. It moves with the mix of what sold (more detached sales push it up). | `transaction` / `average_price` |
| **Median price** | Middle sale price. Less sensitive to a few very expensive sales. | `transaction` / `median_price` |
| **Survey rent** (CMHC) | Average rent across **all sitting tenants and vacant units** in purpose-built rentals (or rented condominiums) on the October survey date. It lags market rents because long-standing tenants pay less. | `survey` / `average_rent` |
| **Asking rent** | Rent advertised on a listing platform for a vacant unit. It is higher than survey rent and covers only units on the market. Never shown as a survey or transaction figure. | `asking` / `asking_rent` |
| **Listings vs completed sales** | New listings and active listings are supply. Sales are completed transactions. Months of inventory = active listings ÷ monthly sales. | `months_of_inventory`, `sales_to_new_listings_ratio` |
| **Vacancy rate** | Share of surveyed rental units vacant and ready to rent on the survey date (CMHC). | `survey` / `vacancy_rate` |

**Geography levels.** `cma` means a Statistics Canada census metropolitan area
or, for Charlottetown, a census agglomeration (CA). `zone` means a
**publisher-defined market area**: a CMHC survey zone, or a real-estate board's
MLS® HPI market (for example CREA's `GREATER_TORONTO` or `INTERIOR_BC`). Board
market areas never coincide exactly with CMAs. Every record's `geography_name`
states which one applies.

**Periods.** The CMHC Rental Market Survey is taken in October and published
in December, so the latest survey figure on 2026-10-30 is **October 2025**
(`period: 2025-10`). The CMHC October 2026 survey should appear around
December 2026, inside the 60-day `next_review` window of every `re` record.
MLS® HPI figures are monthly; the latest on 2026-10-30 is **September 2026**,
released by CREA on 16 October 2026; the next release is 17 November 2026.

## 2. Source register

Order of preference follows the brief: CREA and the MLS® HPI, local boards,
CMHC, Statistics Canada, provincial and municipal government pages, then
listing platforms for clearly labelled asking figures only.

| # | Source | URL | Gives | Frequency | Geography | Terms of use / licence | Map may store? |
|---|---|---|---|---|---|---|---|
| 1 | CREA national statistics | https://creastats.crea.ca/en-CA/ | National and some board sales, new listings, average price (NSA and SA), National Composite HPI | Monthly, mid-month | Canada, provinces, large boards | © CREA; private, non-commercial use; attribution | **No.** Link out; quote only in private analysis |
| 2 | CREA MLS® HPI data download | https://www.crea.ca/files/mls-hpi-data/MLS_HPI_Oct_2026.zip (file name changes monthly; listed on the HPI tool page) | Composite, single-family, one-storey, two-storey, townhouse and apartment HPI and **benchmark prices**, monthly since 2005, for 59 board market areas and provincial aggregates plus the national aggregate (60 sheets) | Monthly | CREA market areas (board-defined) | Terms on https://www.crea.ca/housing-market-stats/mls-home-price-index/hpi-tool/: private, non-commercial use; may be used for analyses and reporting of results with CREA attributed; content may not be published or displayed in whole or in part, modified, merged or redistributed without CREA's prior written consent | **No.** Records here hold single figures for internal analysis, with attribution. The published map must link to CREA, or show the figure only in a private view (see the Agent 02 entry on CREA terms in OPEN-QUESTIONS.md) |
| 3 | Local boards (GVR, VREB, CREB, RAE, TRREB, OREB, Cornerstone, QPAREB/Centris, NSAR, AOR and others) | Each board's market-statistics page | Board HPI by sub-area, sales, listings, average or median prices, months of inventory | Monthly | Board sub-areas | Board terms; generally the same MLS® restrictions as CREA | **No.** Link out. Phase 1 used only the CREA file, which carries the same board HPIs |
| 4 | CMHC Rental Market Survey data tables (Excel) | https://www.cmhc-schl.gc.ca/professionals/housing-markets-data-and-research/market-reports/rental-market-reports-major-centres and https://assets.cmhc-schl.gc.ca/…/rental-market-report-data-tables/2025/rmr-<centre>-2025-en.xlsx | Purpose-built apartment average rents, vacancy, turnover, universe by zone and bedroom count; same-sample rent change; condominium rental rents and vacancy; quality grades a–d | Annual (October survey, December release) | CMA/CA and CMHC zones; provinces; Canada | © CMHC. Terms and Conditions (https://www.cmhc-schl.gc.ca/about-us/terms-conditions): copy, download, print for personal use; no redistribution, republication or reproduction without CMHC's prior written consent | **Not the CMHC file.** The same rents are published by Statistics Canada under an open licence (row 6): store and show those |
| 5 | CMHC Housing Market Information Portal (HMIP) | https://www03.cmhc-schl.gc.ca/hmip-pimh/en | Starts, completions, rental data, absorptions; table exports | Monthly / annual | CMA, zone, neighbourhood | © CMHC; same terms as row 4 | **No.** Link out |
| 6 | Statistics Canada — CMHC average rents | https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013301 (table 34-10-0133-01) | CMHC October average rents by bedroom type and structure type for centres of 10,000+ people | Annual (released 17 Dec 2025 for 2025) | 247 centres | **Statistics Canada Open Licence**; attribution "Source: Statistics Canada" | **Yes.** Values match the CMHC Excel tables for all 20 centres (checked 2026-10-30) |
| 7 | Statistics Canada — CMHC vacancy rates | https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410013001 (table 34-10-0130-01) | Row-and-apartment vacancy rate, CMAs | Annual | CMAs only (no Charlottetown CA) | Statistics Canada Open Licence | **Yes.** Note: row **and** apartment, so it differed by 0 to 0.2 points from the apartment-only rate in our records for October 2025 |
| 8 | Statistics Canada — New Housing Price Index | https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810020501 (table 18-10-0205-01) | Builders' contractor prices for new homes, index | Monthly (latest 2026-09, released 2026-10-22) | Canada, provinces, 27 CMAs | Statistics Canada Open Licence | **Yes** (not stored in Phase 1) |
| 9 | Statistics Canada — CPI | https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401 (table 18-10-0004-01) | CPI including the rent component; used by provinces to set rent guidelines | Monthly (latest 2026-09) | Canada, provinces, some CMAs | Statistics Canada Open Licence | **Yes** (not stored in Phase 1) |
| 10 | Statistics Canada — Canadian Housing Statistics Program | https://www.statcan.gc.ca/en/topics-start/housing (CHSP tables) | Ownership by residency status, assessed values, multiple ownership | Annual | Provinces, CMAs | Statistics Canada Open Licence | Yes (Phase 2) |
| 11 | Bank of Canada Valet API | https://www.bankofcanada.ca/valet/observations/V80691335/json?recent=1 | Chartered banks' 5-year conventional mortgage rate (weekly); 1-year: V80691333; policy rate: V39079 | Weekly / daily | Canada | Bank of Canada terms: https://www.bankofcanada.ca/terms/ | **Fetch only.** Rates are never stored (SPEC §2.7) |
| 12 | Provincial and municipal rule pages | See each `nat-*` record | Transfer taxes, foreign-buyer and vacancy taxes, rent limits, short-term rental rules | When changed | Province / city | Government site terms: link and cite | Store the rule with its `last updated` date; refresh on review |
| 13 | Federal rule pages (Justice Laws, Finance, CMHC, OSFI, FCAC, CRA) | See `nat-ca-*` records | Foreign-buyer prohibition, mortgage rules, stress test | When changed | Canada | Reproduction of federal law permitted; canada.ca non-commercial reproduction with attribution | Store the rule; refresh on review |
| 14 | Municipal assessment bodies (BC Assessment, MPAC in Ontario, municipal assessors elsewhere) | https://www.bcassessment.ca, https://www.mpac.ca | Assessed values per property (BC free lookup; Ontario mainly via account) | Annual roll | Property | **Not reviewed in Phase 1.** Treat as link-only | **No** |
| 15 | Listing platforms (REALTOR.ca, Centris, rentals.ca, others) | https://www.realtor.ca, https://www.centris.ca, https://rentals.ca | Asking prices and asking rents for current listings | Live | Listing | **Not reviewed in Phase 1.** Assume no scraping or redistribution | **No.** Link out with the label "asking" |

### Gaps recorded during Phase 1 (two attempts each)

- **Kelowna board figure.** The Association of Interior REALTORS® September
  2026 release could not be found (site news page 404; PDF name pattern 404).
  The CREA file has only `INTERIOR_BC`, a region much larger than the Kelowna
  CMA, and it is stored with that label (`re-bc-interior-bc-hpi-composite-2026-09`).
- **Sherbrooke.** CREA publishes `ESTRIE` (the region), not the Sherbrooke
  CMA; stored as `re-qc-estrie-hpi-composite-2026-09`. A QPAREB/Centris median
  for the Sherbrooke CMA was not retrieved.
- **Charlottetown.** Only the province-wide PEI composite exists in the CREA
  file, with no apartment series (`re-pe-prince-edward-island-hpi-composite-2026-09`).
- **Kelowna, Sherbrooke, Moncton, St. John's and Charlottetown condominium
  rents.** CMHC suppresses or does not survey them.
- **City of Vancouver pages** returned HTTP 403 twice (Empty Homes Tax read
  from the search summary of the official FAQ).
- **PEI government site** blocked automated fetches (browser check); the 2026
  allowable rent increase is recorded as null in `nat-pe-rent-increase-2026`.

## 3. How the Phase 1 figures were produced

1. **Rents and vacancy.** The 20 CMHC Excel workbooks for October 2025 were
   downloaded and the CMA total row read from Table 1.1.1 (vacancy), 1.1.2
   (average rent), 1.1.3 (universe), 1.1.5 (same-sample rent change) and 4.1.1
   and 4.1.3 (condominium rentals). Every two-bedroom rent was then compared
   with Statistics Canada's open-licence republication through the Web Data
   Service; all 20 matched exactly.
2. **Prices.** The CREA MLS® HPI zip (data through September 2026) was
   downloaded and the not-seasonally-adjusted composite and apartment
   benchmarks read for September 2026 and September 2025. Year-over-year,
   5-year and 10-year annualised changes and the distance from the series peak
   were computed from the same series and are labelled as computed by
   agent-02. Check: the computed national composite change (−3.4%) equals the
   change CREA reported on 16 October 2026.
3. **Rules.** Read from the provincial, municipal or federal page named in each
   `nat` record, with the page's "last updated" date noted. Where a page could
   not be fetched and the figure came from a search summary of the official
   page, the record is marked `partially_verified`.
4. **Nothing was estimated.** Where no source was found, the value is null or
   the record is omitted.

## 4. Stored versus on-demand (SPEC §12)

| Information | In the knowledge base | In the published map bundle | How the map gets the current figure |
|---|---|---|---|
| CMHC survey rents by CMA | `re-*-cmhc-rent-2bed-2025-10` (internal, dated) | **Yes, but only the Statistics Canada copy** (open licence), with period and source | StatCan WDS by vector (§5) |
| CMHC vacancy by CMA | `re-*-cmhc-vacancy-2025-10` (apartment-only, internal) | StatCan row-and-apartment figure only, labelled as such | StatCan WDS by vector |
| CMHC condominium rents | `re-*-cmhc-condo-rent-2bed-2025-10` (internal) | No (not in the StatCan tables) | Link to the CMHC centre page |
| MLS® HPI benchmarks | `re-*-hpi-*-2026-09` (internal analysis, attributed) | **No** | Link to the CREA HPI tool or the board page; show "September 2026 benchmark available at CREA" |
| Board average and median prices | Not stored in Phase 1 | No | Link to the board |
| Asking rents and listings | Never stored | Never | Link to the platform, labelled "asking" |
| Mortgage rates | Never stored | Never | Bank of Canada Valet at calculation time |
| Rules (taxes, rent limits, STR, foreign-buyer ban) | `nat-*` records with `last updated` and `next_review` | Yes (government text, cited) | Re-verified on review; the map shows the record's `last_verified` date |

## 5. On-demand retrieval design for Agent 05

### 5.1 Endpoints

**A. Statistics Canada Web Data Service (open licence; no key).**

```
POST https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods
Content-Type: application/json
[{"vectorId": 3824177, "latestN": 1}, {"vectorId": 1930326, "latestN": 1}]
```

Response fields used: `object.vectorId`, `object.vectorDataPoint[0].refPer`
(e.g. `2025-01-01` = survey year 2025, October survey), `.value`,
`.releaseTime`. Cube freshness: `POST …/getCubeMetadata` with
`[{"productId": 34100133}]` returns `releaseTime` and `cubeEndDate`.

| CMA (StatCan member name) | 2-bedroom average rent, apartment structures 3+ units (34-10-0133-01) | Vacancy, row and apartment (34-10-0130-01) |
|---|---|---|
| Vancouver, British Columbia | v3824177 | v1930326 |
| Victoria, British Columbia | v3824178 | v1930327 |
| Kelowna, British Columbia | v3824194 | v42135451 |
| Calgary, Alberta | v3824154 | v1930302 |
| Edmonton, Alberta | v3824156 | v1930304 |
| Saskatoon, Saskatchewan | v3824171 | v1930320 |
| Regina, Saskatchewan | v3824168 | v1930317 |
| Winnipeg, Manitoba | v3824180 | v1930329 |
| Toronto, Ontario | v3824175 | v1930324 |
| Ottawa-Gatineau, Ontario part | v3824166 | v1930315 |
| Hamilton, Ontario | v3824158 | v1930306 |
| Kitchener-Cambridge-Waterloo, Ontario | v3824159 | v1930307 |
| London, Ontario | v3824160 | v1930308 |
| Montréal, Quebec | v3824161 | v1930310 |
| Québec, Quebec | v3824167 | v1930316 |
| Sherbrooke, Quebec | v3824172 | v1930321 |
| Halifax, Nova Scotia | v3824157 | v1930305 |
| Moncton, New Brunswick | v3824199 | v42135452 |
| St. John's, Newfoundland and Labrador | v3824170 | v1930319 |
| Charlottetown, Prince Edward Island | v3824184 | none (CA not in the table) |

Other bedroom types use the same table with the third coordinate changed
(1 bachelor, 2 one-bedroom, 3 two-bedroom, 4 three-bedroom+); resolve vectors
with `getSeriesInfoFromCubePidCoord`, coordinate `<geo>.1.<unit>.0.0.0.0.0.0.0`.

**B. Bank of Canada Valet (mortgage-rate context for the calculator).**
`GET https://www.bankofcanada.ca/valet/observations/V80691335/json?recent=1`
returns the latest weekly 5-year conventional mortgage rate offered by
chartered banks; `V80691333` (1-year) and `V39079` (policy rate) follow the
same pattern. The calculator pre-fills the user's rate field with this value,
labelled "posted rate, Bank of Canada series V80691335, week of <date>", and
the user overwrites it with a quoted contract rate.

**C. Link-out targets (no fetch).** CREA HPI tool
`https://www.crea.ca/housing-market-stats/mls-home-price-index/hpi-tool/`;
CREA national statistics `https://creastats.crea.ca/en-CA/`; the CMHC centre
page `https://www.cmhc-schl.gc.ca/professionals/housing-markets-data-and-research/market-reports/rental-market-reports-major-centres`;
the board's statistics page (Agent 05 can keep a board-URL table in
`map/DATA-SOURCES.md`).

### 5.2 Caching

| Source | Cache key | Time to live | Invalidation |
|---|---|---|---|
| StatCan WDS values | vector ID | 7 days | Also refresh when `getCubeMetadata.releaseTime` is newer than the cached value (the rent and vacancy tables update once a year in December) |
| StatCan cube metadata | product ID | 24 hours | — |
| Bank of Canada Valet | series ID | 24 hours | — |
| Rule records (`nat-*`) | record ID | Build time | Rebuilt when the knowledge base changes; show `last_verified` |

The cache lives in the browser (IndexedDB or memory) or in a thin server-side
proxy if CORS blocks direct calls. The proxy must not log or forward anything
from `USER-PROFILE.md`.

### 5.3 What the map displays

Every market figure appears as one line with five parts:

> **$2,363 / month** · average rent, 2-bedroom, purpose-built apartments ·
> **October 2025** survey · Source: Statistics Canada table 34-10-0133-01
> (CMHC Rental Market Survey) · retrieved 2026-10-30

- The value with unit; the metric with `figure_kind` in words (survey,
  benchmark, average, median, asking); the period; the source with table or
  series; the retrieval date.
- A figure older than 60 days from its period's release is shown with an
  "older than 60 days" badge (SPEC §2.7).
- Benchmark prices: show a link card "MLS® HPI benchmark — view September 2026
  at CREA", never a stored number, unless the user's answer to the Agent 02 question on CREA terms (OPEN-QUESTIONS.md) is in
  favour of a private view.
- If a fetch fails: show "Not available right now — open source" with the
  link, never a stale number without its date and never an estimate.

### 5.4 Build-step rule for the GeoJSON export

Exclude from published bundles any `re` record whose only sources carry the
CREA or CMHC licence text ("prior written consent"). For CMHC rent records the
build may publish the value only because a Statistics Canada open-licence
source with the same value is listed in `sources[]`.

## 6. Record conventions in this lane

- IDs: `re-<prov>-<area>-cmhc-rent-2bed-<YYYY-MM>`,
  `re-<prov>-<area>-cmhc-vacancy-<YYYY-MM>`,
  `re-<prov>-<area>-cmhc-condo-rent-2bed-<YYYY-MM>`,
  `re-<prov>-<hpi-market>-hpi-<composite|apartment>-<YYYY-MM>`,
  `nat-<prov>-<rule>`. Each new survey or month is a **new record**; old ones
  stay, marked `outdated` at review.
- `data_kind`: `official_fact` for figures read from the publisher. Computed
  changes are labelled in `notes` as computed by agent-02.
- `verification.confidence` follows CMHC's quality grade: a/b high, c medium,
  d low. HPI records for areas that do not match the CMA are `medium`.
- `next_review`: 2026-12-29 for every `re` record (60 days); rules 2027-01-15,
  except the federal foreign-buyer prohibition, 2026-12-01.
