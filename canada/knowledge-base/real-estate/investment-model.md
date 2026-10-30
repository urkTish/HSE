# Investment model — calculation template

Agent 02 · 2026-10-30 · for the map's calculator (Agent 05) and for any
buy-versus-rent or rental-property question the user asks later.

**No mortgage rate is stored here.** Rates are retrieved when the calculation
runs (Bank of Canada Valet, `METHODOLOGY.md` §5.1 B) and then replaced by the
rate the user is actually quoted. Rules (down payment, insurance premiums,
stress test, transfer taxes) come from `nat-*` records; market figures come
from `re-*` records or an on-demand fetch. Everything in the worked example
(§3) is a **hypothetical input**, not a market observation.

## 1. Inputs

| Input | Symbol | Where it comes from |
|---|---|---|
| Purchase price | `P` | User; a reference price is the MLS® HPI benchmark for the area and type (`re-*-hpi-*`), linked to CREA |
| Down payment | `D` | User; must meet the federal minimum (`nat-ca-mortgage-down-payment-insurance-rules`) |
| Contract interest rate (annual, nominal) | `r` | Retrieved at calculation time, then the user's quote. Never stored |
| Amortization (years) | `A` | Insured: 25, or 30 for first-time buyers and new builds; uninsured: set by the lender |
| Province / city | — | Selects the transfer-tax and foreign-buyer rules (`rules-by-province.md`) |
| Buyer status | — | Unknown (`USER-PROFILE.md`); selects federal and provincial foreign-buyer rules |
| Monthly market rent | `R` | CMHC survey rent (`re-*-cmhc-rent-2bed-*` or `re-*-cmhc-condo-rent-2bed-*`) as a floor; a current asking rent (labelled asking) for a new lease |
| Vacancy and credit-loss allowance | `v` | User; CMHC vacancy rate for the CMA is a reference (`re-*-cmhc-vacancy-*`) |
| Operating expenses | `E` | Property tax (municipal), condo fees, insurance, maintenance, management, utilities paid by owner |

## 2. Formulas

**Minimum down payment** (federal, `nat-ca-mortgage-down-payment-insurance-rules`)

```
P ≤ 500,000:             Dmin = 0.05 × P
500,000 < P < 1,500,000: Dmin = 25,000 + 0.10 × (P − 500,000)
P ≥ 1,500,000:           Dmin = 0.20 × P   (no default insurance available)
```

**Mortgage default insurance** (required when D < 20% of P; `nat-ca-cmhc-mortgage-insurance-premiums`)

```
LTV      = (P − D) / P
premium  = rate(LTV) × (P − D)          rate: 0.60% ≤65%, 1.70% ≤75%, 2.40% ≤80%,
                                              2.80% ≤85%, 3.10% ≤90%, 4.00% ≤95%
L        = (P − D) + premium            premium is added to the loan
PST on premium (QC, ON, SK) is paid in cash at closing; its rate is retrieved, not stored.
```

**Monthly payment** (Canadian fixed-rate mortgages compound semi-annually)

```
i  = (1 + r/2)^(2/12) − 1               monthly rate
n  = 12 × A
M  = L × i / (1 − (1 + i)^(−n))
Balance after k payments:  B_k = L(1+i)^k − M × ((1+i)^k − 1) / i
```

**Stress test** (`nat-ca-mortgage-stress-test`)

```
q   = max(5.25%, r + 2.00 points)
M_q = payment at rate q (same L, A)
GDS = (M_q + property tax + heating + 50% of condo fees) / gross monthly income   ≤ 39%
TDS = (GDS items + other debt payments) / gross monthly income                  ≤ 44%
```

**Transfer tax**: bracket sum from the province's record (and city, e.g.
Toronto, Montréal), minus first-time-buyer relief if eligible, plus any
foreign/non-resident tax (BC 20%, ON 25%, NS 10%) where the buyer's status
triggers it.

**Closing costs** `C` = transfer tax + legal fees and disbursements + title
insurance + inspection/appraisal + adjustments (prepaid property tax, condo
fees) + PST on insurance premium.

**Operating return**

```
Gross scheduled rent   GSR = 12 × R
Effective gross income EGI = GSR × (1 − v)
Net operating income   NOI = EGI − E
Gross yield  = GSR / P
Net yield (cap rate) = NOI / P
Annual debt service DS = 12 × M
Cash flow    CF = NOI − DS                (before income tax)
Cash invested I = D + C
Cash-on-cash = CF / I
```

**Appreciation scenario** (a scenario, not a forecast)

```
Value after t years  V_t = P × (1 + g)^t
Equity after t years Q_t = V_t − B_(12t) − selling costs(V_t)
Total return over t  = Q_t − I + Σ CF   (before tax; ignores rent growth)
```

Reference growth rates for `g` can be read from the CREA series: the composite
benchmark's 5- and 10-year annualised changes are in the `notes` of each
`re-*-hpi-composite-2026-09` record and in `market-snapshot-2026-10.md`
(e.g. Greater Toronto −3.0% over 5 years, +2.6% over 10). Past change does not
predict future change; show at least one negative scenario.

## 3. Worked example — hypothetical inputs only

**Every input in this section is invented for illustration.** The rate is not
a market rate; the rent and expenses are not observations. Only the transfer
tax brackets, the stress-test rule and the down-payment rule are sourced.

| Input | Value | Kind |
|---|---|---|
| Location | Ontario, outside Toronto (so no municipal LTT) | hypothetical |
| Property | Two-bedroom condominium apartment | hypothetical |
| Price `P` | $600,000 | hypothetical |
| Down payment `D` | $120,000 (20%, so no default insurance) | hypothetical |
| Contract rate `r` | 4.50% fixed, 5-year term | **hypothetical — not a quoted or observed rate** |
| Amortization `A` | 25 years | hypothetical |
| Rent `R` | $2,400 / month | hypothetical |
| Vacancy and credit loss `v` | 4% | hypothetical |
| Property tax | $4,000 / year | hypothetical |
| Condo fees | $600 / month ($7,200 / year) | hypothetical |
| Insurance (unit owner) | $500 / year | hypothetical |
| Maintenance reserve | $1,200 / year | hypothetical |
| Management | $0 (self-managed) | hypothetical |
| Buyer | Canadian citizen or PR, not a first-time buyer | hypothetical (avoids NRST and FTB refund) |

**Step 1 — Loan and payment.** `L = 600,000 − 120,000 = 480,000`.
`i = (1.0225)^(1/6) − 1 = 0.0037153`; `n = 300`; **`M = $2,656.67` per month**.

**Step 2 — Stress test.** `q = max(5.25%, 4.50% + 2.00) = 6.50%`;
`M_q = $3,215.15`. With property tax $333/month and half the condo fees
$300/month (heating excluded for simplicity), GDS ≤ 39% requires a gross
household income of at least **about $118,400 a year**.

**Step 3 — Closing costs** (`C`)

| Item | Amount | Kind |
|---|---|---|
| Ontario land transfer tax: 0.5%×55,000 + 1%×195,000 + 1.5%×150,000 + 2%×200,000 | **$8,475** | calculation on `nat-on-land-transfer-tax` |
| Legal fees and disbursements | $2,000 (range $1,500–$3,000) | estimate (agent-02, not sourced; replace with a quote) |
| Title insurance | $400 (range $250–$600) | estimate (not sourced) |
| Inspection / status certificate review | $500 | estimate (not sourced) |
| Adjustments (prepaid tax, fees) | $1,000 | estimate (varies with closing date) |
| **Total `C`** | **$12,375** | |

Cash invested `I = 120,000 + 12,375 = $132,375`.

**Step 4 — Operating return (year 1)**

| Line | Amount |
|---|---|
| GSR = 12 × 2,400 | $28,800 |
| EGI = 28,800 × 0.96 | $27,648 |
| Operating expenses E = 4,000 + 7,200 + 500 + 1,200 | $12,900 |
| NOI | $14,748 |
| Gross yield = 28,800 / 600,000 | 4.80% |
| Net yield (cap rate) = 14,748 / 600,000 | 2.46% |
| Debt service = 12 × 2,656.67 | $31,880 |
| **Cash flow before tax** | **−$17,132** |
| Cash-on-cash | −12.9% |
| Principal repaid in year 1 (part of DS, builds equity) | $10,697 |
| Interest paid in year 1 | $21,183 |

**Step 5 — Five-year scenarios** (balance after 60 payments $421,423; selling
costs assumed 4% of sale value — hypothetical)

| Scenario `g` per year | Value in 5 years | Equity after selling costs | Equity − cash invested | Plus 5 years of cash flow (no rent growth) |
|---|---|---|---|---|
| −2% | $542,352 | $99,236 | −$33,139 | −$118,799 |
| 0% | $600,000 | $154,577 | +$22,202 | −$63,458 |
| +2% | $662,448 | $214,528 | +$82,153 | −$3,507 |
| +4% | $729,992 | $279,369 | +$146,994 | +$61,334 |

**Reading the example.** With these invented inputs the property loses money
every month and needs roughly 2% a year of appreciation just to break even
over five years. The method, not the result, is the point: plug in a quoted
rate and a real rent before drawing any conclusion. Income tax on rent (net of
interest and capital cost allowance), the principal-residence exemption and
capital gains are outside this template (Agent 01 covers taxes; Phase 2).

**Sidebar — same home with 10% down.** Minimum down payment at $600,000 is
5% × 500,000 + 10% × 100,000 = $35,000. With $60,000 down, LTV = 90%, so the
premium is 3.10% × 540,000 = **$16,740**, added to the loan; Ontario PST on the
premium is payable in cash (rate retrieved, not stored).

## 4. Screening yields by CMA (estimate)

A first filter only. **Gross yield = 12 × CMHC two-bedroom rental-condo
survey rent (October 2025) ÷ MLS® HPI apartment benchmark (September 2026).**
Calculation by Agent 02 on official figures; `data_kind` would be `estimate`.

| CMA | Condo 2-bed rent (record) | Apartment benchmark (record) | Gross yield |
|---|---|---|---|
| Edmonton | $1,655 (`re-ab-edmonton-cma-cmhc-condo-rent-2bed-2025-10`) | $197,800 (`re-ab-edmonton-hpi-apartment-2026-09`) | 10.0% |
| London | $2,132 (`re-on-london-cma-cmhc-condo-rent-2bed-2025-10`) | $317,100 (`re-on-london-st-thomas-hpi-apartment-2026-09`) | 8.1% |
| Calgary | $2,030 (`re-ab-calgary-cma-cmhc-condo-rent-2bed-2025-10`) | $304,900 (`re-ab-calgary-hpi-apartment-2026-09`) | 8.0% |
| Ottawa | $2,503, quality d (`re-on-ottawa-cma-cmhc-condo-rent-2bed-2025-10`) | $380,800 (`re-on-ottawa-hpi-apartment-2026-09`) | 7.9% |
| Hamilton | $2,831, quality c (`re-on-hamilton-cma-cmhc-condo-rent-2bed-2025-10`) | $447,400 (`re-on-hamilton-burlington-hpi-apartment-2026-09`) | 7.6% |
| Regina | $1,460 (`re-sk-regina-cma-cmhc-condo-rent-2bed-2025-10`) | $234,500 (`re-sk-regina-hpi-apartment-2026-09`) | 7.5% |
| Winnipeg | $1,468, quality c (`re-mb-winnipeg-cma-cmhc-condo-rent-2bed-2025-10`) | $237,500 (`re-mb-winnipeg-hpi-apartment-2026-09`) | 7.4% |
| Kitchener–Cambridge–Waterloo | $2,197 (`re-on-kitchener-cambridge-waterloo-cma-cmhc-condo-rent-2bed-2025-10`) | $356,300 (`re-on-kitchener-waterloo-hpi-apartment-2026-09`) | 7.4% |
| Saskatoon | $1,590 (`re-sk-saskatoon-cma-cmhc-condo-rent-2bed-2025-10`) | $265,200 (`re-sk-saskatoon-hpi-apartment-2026-09`) | 7.2% |
| Halifax | $2,465 (`re-ns-halifax-cma-cmhc-condo-rent-2bed-2025-10`) | $423,500 (`re-ns-halifax-dartmouth-hpi-apartment-2026-09`) | 7.0% |
| Toronto | $2,891 (`re-on-toronto-cma-cmhc-condo-rent-2bed-2025-10`) | $527,200 (`re-on-greater-toronto-hpi-apartment-2026-09`) | 6.6% |
| Victoria | $2,688, quality c (`re-bc-victoria-cma-cmhc-condo-rent-2bed-2025-10`) | $542,800 (`re-bc-victoria-hpi-apartment-2026-09`) | 5.9% |
| Québec | $1,377 (`re-qc-quebec-cma-cmhc-condo-rent-2bed-2025-10`) | $311,200 (`re-qc-quebec-cma-hpi-apartment-2026-09`) | 5.3% |
| Vancouver | $2,900 (`re-bc-vancouver-cma-cmhc-condo-rent-2bed-2025-10`) | $682,500 (`re-bc-greater-vancouver-hpi-apartment-2026-09`) | 5.1% |
| Montréal | $1,826 (`re-qc-montreal-cma-cmhc-condo-rent-2bed-2025-10`) | $427,900 (`re-qc-montreal-cma-hpi-apartment-2026-09`) | 5.1% |

**Why these yields are too high and only rank markets.** The rent is for
two-bedroom units, while the apartment benchmark covers all apartment sizes
(including one-bedrooms and studios), so the ratio overstates the yield of a
real two-bedroom purchase. Rent and price geographies differ (CMA versus
board area). Condo fees and property taxes, which take a large share of rent
in condominiums, are not deducted. Use it to decide where to look, then run §3
with a specific listing, a quoted rate and current asking rents. Kelowna,
Sherbrooke, Moncton, St. John's and Charlottetown are missing because CMHC
publishes no condominium rent or CREA no apartment benchmark for them.

## 5. What the map calculator needs (for Agent 05)

- Input form with the fields in §1; defaults blank, never pre-filled with a
  stored price or rent.
- Rate field pre-filled from Bank of Canada Valet `V80691335` with its date
  and the label "posted 5-year conventional rate"; user overwrites.
- Rule lookups by province and city from the `nat-*` records (brackets, rates
  and exemptions are in `attributes`).
- Output: every line of §3 with its formula visible, and the stress-test
  result, scenario table and the warning "hypothetical unless you entered real
  quotes".
