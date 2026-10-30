# Public health coverage by province and territory — newcomers

Agent 01 · researched 2026-10-30 · jurisdiction: each province or territory (health insurance is
provincial; the federal Canada Health Act sets the conditions) · next review 2026-11-29.

Records: `nat-<prov>-health-coverage` (13 records). Each record gives eligibility by immigration
status, the newcomer waiting period, how to apply, the drug-coverage model and the latest share of
adults with a regular health care provider.

**Status note.** Which rule applies depends on the user's immigration status, which is unknown
(`USER-PROFILE.md`; question 1). No status is assumed below.

---

## 1. Key points for a decision

- **Waiting periods differ by province.** Ontario, Manitoba, New Brunswick, Nova Scotia and
  Newfoundland and Labrador state no wait for eligible arrivals from abroad. B.C., Saskatchewan,
  Quebec and Yukon impose up to about three months. Budget for **private insurance for the first
  three months** wherever you land. Every provincial page that mentions it advises this.
- **Temporary-status coverage is the big divider.**
  - Ontario covers work-permit holders only after 6 months of full-time work for an Ontario employer.
  - Manitoba covers them from the permit's issue date with a 12-month permit.
  - Nova Scotia, Newfoundland and Labrador, Yukon and Nunavut require permits of 12 months or more.
  - Manitoba excludes study-permit holders entirely.
- **Finding a family doctor is hardest in PEI, Quebec, Newfoundland and Labrador, New Brunswick and
  the territories.** In 2025, 33.7% of adults in PEI, 27.7% in Quebec and 24.1% in Newfoundland and
  Labrador had no regular provider. In Ontario the figure was 11.2% (CIHI, 2025).
- **Drug coverage is not universal.** Each province runs a different public drug plan for people
  without employer coverage. In Quebec the public plan covers residents without private coverage and charges an income-based
  premium. Four jurisdictions (B.C., Manitoba, PEI and Yukon) have national-pharmacare agreements
  that cover listed contraceptives and diabetes drugs.

## 2. Comparison table

Regular provider = CIHI "Canadians With a Primary Health Care Provider", adults 18+, from Statistics
Canada's Canadian Community Health Survey. Canada overall: 83.4% (2025). "Without" = 100 − with.

| Prov. | Waiting period, arrivals from abroad | Work-permit holders | Study-permit holders | Without a regular provider (year) | Drug-coverage model | Record (verification) |
|---|---|---|---|---|---|---|
| ON | None ("no longer a waiting period") | After 6 months' full-time work for an Ontario employer | Not listed (contact ServiceOntario) | 11.2% (2025) | Ontario Drug Benefit for 65+ and under-25s without private plans; Trillium for high costs | `nat-on-health-coverage` (verified) |
| BC | Rest of arrival month + 2 months (one page says waived for PRs; conflict) | Some, with permits of 6+ months | Some, with permits of 6+ months | 15.8% (2025) | Fair PharmaCare (income-based deductible); pharmacare agreement | `nat-bc-health-coverage` (partial) |
| AB | From the residency or document date if applied within 3 months (temporary residents); PR timing not confirmed | Permit naming an AB employer or open; 6+ months left; intent to stay 12 months | Separate rules (not read) | 13.8% (2025) | Voluntary premium-based Blue Cross non-group plan | `nat-ab-health-coverage` (partial) |
| SK | On or before the first day of the 3rd month after arrival | Eligible (no minimum stated) | Eligible with permit and full-time enrolment | 17.4% (2025) | Special Support Program (income-tested) | `nat-sk-health-coverage` (verified) |
| MB | None stated | From permit issue date; permit of 12+ months | **Not eligible** (since 2018) | 14.6% (2025) | Pharmacare (income-based deductible); pharmacare agreement | `nat-mb-health-coverage` (verified) |
| QC | Up to 3 months from registration (also applies to citizens; children exempt; agreement countries exempt) | Conditions not captured (RAMQ blocked) | Generally not, with exceptions | 27.7% (2025) | RAMQ public plan for those without private coverage (income-based premium) | `nat-qc-health-coverage` (partial) |
| NB | From the first day of arrival once permanent residence is established | Accepted document; no duration rule stated | Permit for the full school year | 20.5% (2025) | NB Drug Plan (income-based premiums) | `nat-nb-health-coverage` (verified) |
| NS | None (from date of residency) | Permit of 12+ months | From the 13th month, with a 12-month permit | 16.2% (2025) | Family Pharmacare (income-based) | `nat-ns-health-coverage` (verified) |
| PE | Not found (null) | "Working visa" may apply | With enrolment proof | 33.7% (2025) | PEI Pharmacare (payer of last resort); pharmacare agreement | `nat-pe-health-coverage` (partial) |
| NL | None fixed (latest of arrival, start of employment or approval) | Permit of 12+ months plus an employer letter (6 months for PNP/AIP) | Permit of 12+ months | 24.1% (2025) | NL Prescription Drug Program | `nat-nl-health-coverage` (verified) |
| YT | 3 months | Yukon-specific or open permit of 1+ year | Not captured | 23.4% (2024) | Pharmacare 65+, Chronic Disease Program; pharmacare agreement | `nat-yt-health-coverage` (partial) |
| NT | On arrival (2018 booklet; older source) | Conflicting official material | Contact office | 51.8% (2024, use with caution) | Extended Health Benefits for specified groups only | `nat-nt-health-coverage` (partial) |
| NU | Not found (null) | Permit of 1+ year with a Nunavut address | Permit of 1+ year with a Nunavut address | 68.8% (2024, use with caution) | Extended Health Benefits for specified groups | `nat-nu-health-coverage` (partial) |

**Moving between provinces** after arrival usually means a wait until the first day of the third
month, during which the former province's plan applies. This is stated for SK, MB, NB, NS, NT and YT.

## 3. How to apply (common pattern)

Apply **after** arriving and establishing residence, with:

- proof of immigration status (PR confirmation or card, or a work or study permit);
- proof of residence in the province;
- identity documents.

Ontario requires an in-person visit to ServiceOntario with three original documents. Most others
accept online or mail applications. Details are in each record (`how_to_apply`).

## 4. What is not covered (Phase 1 gaps)

- **Dental, optical, mental health and private supplementary insurance** were not researched. The
  federal Canadian Dental Care Plan was not researched either.
- **Drug-plan designs** come from the federal drug-price regulator's summary of the 2020/21 plans
  (published 2024). Premiums and deductibles may have changed. Quebec's public-plan premium amount
  was not captured.
- **Regular-provider shares are provincial averages.** Within-province regions vary widely. For
  example, the Montréal region was at 69.1% with a provider in 2024 and Labrador–Grenfell at 33.9%,
  in CIHI's same table. Regional figures exist in the CIHI file for a Phase 2 city-level layer.
- **2025 survey questions were harmonized**, so compare with 2023–2024 with caution. Territorial
  estimates are 2024 with wide confidence intervals.

## Sources

Provincial health-plan pages (cited per record); CIHI indicator data table, *Canadians With a
Primary Health Care Provider* (data updated October 2026); the federal drug-price regulator's
(PMPRB/NPDUIS) *Public Drug Plan Designs*; Health Canada, *What's covered by national pharmacare*.
All were accessed on 2026-10-30.
