# Rules by province — who may buy, transfer taxes, foreign-buyer and vacancy taxes, rent limits, short-term rentals

Agent 02 · researched 2026-10-30 · every rule is a `nat-*` record in this
folder with its source page and that page's "last updated" date. Rules change
on 1 January in several provinces; review date 2027-01-15, except the federal
prohibition (review 2026-12-01).

**The user's immigration status is unknown** (`USER-PROFILE.md`, essential
unknowns 1 and 7). Nothing below assumes a status. Each table shows what
changes with status so the answer can be read off once the status is known.
Agent 01 owns the immigration framing; the status labels below follow the
federal Act's own categories.

## 1. Who may buy residential property

### 1.1 Federal prohibition on non-Canadians — `nat-ca-non-canadian-residential-purchase-prohibition`

- **In force** since 1 January 2023; **scheduled to end 1 January 2027**
  (extended once, announced 4 February 2024). As of 2026-10-30 no further
  extension, repeal or replacement was found on official sites; press reports
  a federal review. This date is two months away: re-check before any
  purchase decision.
- **Covers** residential property of up to three dwelling units (houses,
  semi-detached, condominium units) **inside a census metropolitan area or
  census agglomeration**. Buildings of four or more units, vacant land (since
  27 March 2023) and property outside CMAs/CAs are not covered.
- **Penalty**: fine up to $10,000 and a court-ordered sale.

| Status at the date of purchase | May buy inside a CMA/CA while the ban is in force? |
|---|---|
| Canadian citizen | Yes |
| Permanent resident | Yes |
| Person registered under the Indian Act | Yes |
| Protected person / granted refugee protection | Yes (exempt) |
| Refugee claimant referred to the RPD, or humanitarian public-policy temporary resident | Yes (exempt) |
| Temporary resident with a work permit or work authorization | Yes, if at least 183 days of validity remain on the purchase date and no earlier purchase during the ban (one property) |
| Temporary resident studying | Only if: 5 prior years of Canadian tax returns, 244+ days in Canada in each of those years, price ≤ $500,000, no earlier purchase |
| Spouse/common-law partner buying with a citizen, PR or exempt person | Yes (exempt) |
| Visitor or person living abroad without status | No, unless another exemption applies (inheritance, gift, separation, development) |
| Any status, property outside all CMAs/CAs | Not covered by the ban |

Renting is never restricted by the Act.

### 1.2 Provincial taxes on foreign or non-resident buyers (independent of the federal ban)

| Province | Tax | Rate | Applies to | Relief tied to status | Record |
|---|---|---|---|---|---|
| BC | Additional property transfer tax | 20% of fair market value (your share) | Foreign nationals, foreign corporations, taxable trustees, in Metro Vancouver, Fraser Valley, Capital (Victoria), Central Okanagan (Kelowna) and Nanaimo regional districts | Exempt: confirmed BC Provincial Nominee buying a principal residence (once) | `nat-bc-additional-property-transfer-tax-foreign` |
| ON | Non-Resident Speculation Tax | 25% of consideration | Foreign nationals, foreign corporations, taxable trustees, anywhere in Ontario, 1–6 single-family residences | Exempt: OINP nominees, protected persons, spouse of a citizen/PR. Rebate if the buyer becomes a PR within 4 years | `nat-on-non-resident-speculation-tax` |
| NS | Non-resident deed transfer tax | **10%** (was 5% before April 2025) of the higher of price or assessed value | Non-residents of Nova Scotia (including Canadians from other provinces), ≤3 units | Avoided if the buyer declares intent and proves NS residency within 12 months (transfers from 6 August 2026) | `nat-ns-non-resident-deed-transfer-tax` |
| Other provinces | No foreign/non-resident purchase tax found in Phase 1 | — | — | — | — |

On a hypothetical $600,000 purchase (arithmetic on the rates above, labelled
estimate): BC ATT $120,000; Ontario NRST $150,000; Nova Scotia non-resident tax
$60,000 — all on top of the ordinary transfer tax.

The federal **Underused Housing Tax** no longer applies from the 2025 calendar
year (`nat-ca-underused-housing-tax-status`).

## 2. Transfer taxes and first-time-buyer relief

| Province / city | Rule | Tax on a hypothetical $600,000 home (estimate) | First-time buyer relief (citizen or PR only) | Record |
|---|---|---|---|---|
| BC | 1% to $200k, 2% to $2M, 3% above; +2% on residential over $3M | $10,000 | Exempt on first $500k for homes ≤ $835k (phase-out to $860k): pays $2,000 at $600k | `nat-bc-property-transfer-tax`, `nat-bc-first-time-home-buyers-exemption` |
| Ontario | 0.5% / 1% / 1.5% / 2% / 2.5% at $55k, $250k, $400k, $2M | $8,475 | Refund up to $4,000 | `nat-on-land-transfer-tax`, `nat-on-first-time-buyer-ltt-refund` |
| Toronto (in addition to Ontario) | Same brackets to $3M, then 4.4% to 8.6% (from 1 April 2026) | $8,475 (total $16,950 with Ontario) | Rebate up to $4,475 | `nat-on-toronto-municipal-land-transfer-tax` |
| Montréal | 0.5% / 1% / 1.5% / 2% / 2.5% / 3.5% / 4% at $62,900, $315,000, $552,300, $1,104,700, $2,136,500, $3,113,000 (2026) | $7,349 | none found | `nat-qc-montreal-property-transfer-duties` |
| Manitoba | 0% to $30k, then 0.5% / 1% / 1.5% / 2% at $90k, $150k, $200k | $9,650 | none on the page | `nat-mb-land-transfer-tax` |
| New Brunswick | 1% of the greater of price and assessed value | $6,000 | not researched | `nat-nb-real-property-transfer-tax` |
| Halifax (NS) | 1.5% municipal deed transfer tax | $9,000 | not researched | `nat-ns-halifax-deed-transfer-tax` |
| Alberta, Saskatchewan, Newfoundland and Labrador, PEI, other Quebec and NS municipalities | Not researched in Phase 1 | — | — | — |

## 3. Vacancy and speculation taxes on owners

| Jurisdiction | Tax | Rate | Record |
|---|---|---|---|
| BC (taxable regions) | Speculation and vacancy tax | 2026: 1% for citizens/PRs; 3% for foreign owners and untaxed worldwide earners (satellite families) | `nat-bc-speculation-vacancy-tax` |
| City of Vancouver | Empty Homes Tax | 3% of assessed value (rate for 2026 not confirmed; a 5% proposal existed) | `nat-bc-vancouver-empty-homes-tax` |
| City of Toronto | Vacant Home Tax | 3% of assessed value, from 2024; vacant 6+ months | `nat-on-toronto-vacant-home-tax` |
| Ottawa, Hamilton and other cities | Vacant-unit taxes | Not researched in Phase 1 | — |

## 4. Rent increases for existing tenants (2026)

One line each. "Notice" is for a rent increase; eviction notice periods were
not researched in Phase 1 (see §6).

| Province | 2026 limit | Notice and frequency | Record |
|---|---|---|---|
| BC | 2.3% (2027: 2.2%) | 3 full months, Form RTB-7; once per 12 months | `nat-bc-rent-increase-limit` |
| Alberta | No limit | 3 full months (monthly periodic); once per 365 days; not during a fixed term | `nat-ab-rent-increase-rules` |
| Saskatchewan | No limit | 12 months' notice (periodic); none in first 18 months; once per 12 months | `nat-sk-rent-increase-rules` |
| Manitoba | 1.8% (units under the $1,670 threshold; newer buildings exempt) | 3 months; 2027 guideline not found | `nat-mb-rent-increase-guideline` |
| Ontario | 2.1% (2027: 1.9%); **units first occupied after 15 Nov 2018 are exempt** | 90 days on the LTB form; once per 12 months | `nat-on-rent-increase-guideline` |
| Quebec | No fixed cap: tenant may refuse; TAL fixes rent with a 3.1% base for 2026 plus building-specific items | Lease-renewal notice | `nat-qc-rent-fixing-2026` |
| New Brunswick | 3% (kept for 2027) | 6 months; once per 12 months | `nat-nb-rent-cap` |
| Nova Scotia | 5% per year until 31 Dec 2027 | Not stated on the page | `nat-ns-rent-cap` |
| PEI | **Not verified** (statutory maximum 3%; 2025 was 2.3%) | 3 months (secondary sources) | `nat-pe-rent-increase-2026` |
| Newfoundland and Labrador | No limit | 6 months (monthly or fixed term); once per 12 months | `nat-nl-rent-increase-rules` |

For an investor, the uncapped markets (Alberta, Saskatchewan, NL, and Ontario
post-2018 units) let rent follow the market; for a renter, they are the
markets where a large renewal increase is legal.

## 5. Short-term rentals in the major cities

| Place | Rule | Record |
|---|---|---|
| BC (Vancouver, Victoria, Kelowna and every municipality of 10,000+) | Only the host's principal residence plus one suite or ADU; provincial registration ($100 / $450 a year); local bylaws may be stricter | `nat-bc-short-term-rental-principal-residence` |
| Montréal | Principal residence only, and only 10 June – 10 September; some boroughs ban it | `nat-qc-montreal-short-term-rental` |
| Toronto | Principal residence only; operators and platforms licensed/registered (night limits not confirmed in Phase 1) | — (page read, details incomplete) |
| Calgary, Edmonton, Ottawa, Halifax and others | Not researched in Phase 1 | — |

Consequence: a purchase in Vancouver, Victoria, Kelowna, Toronto or Montréal
cannot be underwritten on short-term-rental income.

## 6. Gaps and next steps

- Eviction rules (landlord's own use, renovation, notice periods and
  compensation) — not researched; next step is one line per province from the
  tenancy authority (BC RTB, Ontario LTB, TAL, etc.).
- Transfer costs in Alberta, Saskatchewan, NL and PEI; Quebec City and
  Sherbrooke upper brackets; first-time-buyer relief in NB, NS, PEI.
- PEI 2026 allowable rent increase (official site blocked automated access).
- Ottawa and Hamilton vacant-unit taxes; STR rules in Calgary, Edmonton,
  Ottawa, Halifax; Toronto STR night cap.
- Taxable regions of the BC speculation and vacancy tax (page 404).
- Federal GST/HST new-housing rebates for first-time buyers — not researched.
