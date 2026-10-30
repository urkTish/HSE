# Agent 01 — National Intelligence: status

Last updated 2026-10-30 by Agent 01, Phase 1. Written for someone who did not watch the work.

## Done

**Validator:** `node knowledge-base/scripts/validate.mjs knowledge-base/national` →
`54 record(s) checked, 0 failed, 0 warning(s), 0 non-record JSON file(s) skipped.`

**Records: 54 `nat` records.**

- 23 verified, 30 partially verified, 1 disputed.
- 52 `official_fact`, 1 `estimate` and 1 `professional_interpretation`.

**Prose documents** (each cites record ids):

- `immigration-pathways.md` — Express Entry, CRS and the 3 November 2026 change, 2026 categories and
  rounds, PNPs for every province and territory, family sponsorship, work and study-to-work rules,
  the Levels Plan, fees and processing times, and a "what each status allows" table.
- `taxes-by-province.md` — federal and provincial brackets, basic personal amounts, sales taxes,
  CPP/QPP/EI/QPIP, the Ontario Health Premium, and take-home estimates at $60k, $100k and $150k
  with the method.
- `healthcare-by-province.md` — eligibility by status, waiting periods, how to apply, drug plans and
  regular-provider shares (CIHI 2025).
- `employment-and-credentials.md` — regulated versus non-regulated occupations, CICIC, the licensing
  process, the Job Bank outlook method, and a placeholder for the user's occupation.
- `quebec-language-rules.md` — public services, English-schooling eligibility, language of work,
  francization, amendment dates and the proposed Bill 1.

**Records by group:**

| Group | Count | Ids |
|---|---|---|
| Tax | 15 | `nat-ca-federal-income-tax-and-payroll-2026`, `nat-ca-take-home-pay-examples-2026`, `nat-{ab,bc,mb,nb,nl,ns,nt,nu,on,pe,qc,sk,yt}-income-and-sales-tax-2026` |
| Health | 13 | `nat-{ab,bc,mb,nb,nl,ns,nt,nu,on,pe,qc,sk,yt}-health-coverage` |
| Immigration (federal) | 9 | `nat-ca-express-entry-2026`, `nat-ca-express-entry-crs-changes-2026-11-03`, `nat-ca-immigration-levels-plan-2026-2028`, `nat-ca-ircc-fees-2026`, `nat-ca-ircc-processing-times-2026-10-29`, `nat-ca-work-permits-and-study-to-work-2026`, `nat-ca-family-sponsorship-2026`, `nat-ca-residential-property-purchase-by-non-canadians`, `nat-ca-rights-by-immigration-status` |
| Provincial immigration | 12 | `nat-{ab,bc,mb,nb,nl,ns,nt,on,pe,sk,yt}-provincial-nominee-program`, `nat-qc-skilled-worker-selection-program` |
| Quebec language | 5 | `nat-qc-public-services-language`, `nat-qc-english-schooling-eligibility`, `nat-qc-language-of-work-and-francization`, `nat-qc-francisation-quebec`, `nat-qc-constitution-bill-1-2025` |

**Also updated:** `TASKS.md` (01-1 to 01-6 done; 01-7 to 01-9 added as todo) and
`OPEN-QUESTIONS.md` (five lines appended).

## In progress / parked

- **Parked: IRCC permanent-residence processing times.** These are Express Entry, PNP, spousal and
  citizenship times. The interactive page loads them dynamically, and the two data files read did
  not contain them. They are recorded as null. Next step: find the data file behind the page or read
  it in a browser.
- **Parked: Quebec sources blocked.** Revenu Québec, RAMQ and LégisQuébec returned HTTP 403 on two
  attempts each. Quebec tax rates, RAMQ eligibility and the 3-year cap on temporary English schooling
  rest on search extracts and secondary sources, so those records are `partially_verified`. Next
  step: read them manually, or find alternative official copies (for example CanLII for the
  Charter and its regulation).
- **Disputed: Manitoba bracket thresholds.** Two CRA pages disagree ($47,000/$100,000 against
  $47,564/$101,200). The records use the payroll-guide figures, which match Manitoba's indexation
  freeze. The difference is under $70 a year. Next step: check the Manitoba Finance page.
- **Not done in Phase 1** (scope):
  - dental, optical and mental-health coverage, and the Canadian Dental Care Plan;
  - Atlantic Immigration Program and community pilots in detail;
  - spousal-sponsorship income rules;
  - tax residency and treaties;
  - remote work and self-employment;
  - everyday-life, legal and safety areas (SPEC §5 B and F).
- **Not yet checked:** the take-home estimates have not been compared with CRA's Payroll Deductions
  Online Calculator.

## Key findings

1. **Immigration routes now favour people already in Canada or in a category.** Since August 2026
   there have been no all-programme Express Entry rounds. CEC rounds cut off at 516–523. French
   rounds were 382–435 and healthcare and trades about 475. A provincial nomination (+600) is the
   main lever for applicants abroad.
2. **Express Entry rescoring takes effect on 3 November 2026 (announced).** A Canadian job offer
   or Canadian experience in a high-wage occupation is worth up to 150 points, and no LMIA is needed
   for the offer. The user's occupation and wage level will matter much more. Invitation rounds
   pause for up to two weeks.
3. **Permanent-resident targets are flat at 380,000 a year (2026–2028)**, and temporary arrivals
   are being cut (385,000 in 2026). The 2027–2029 plan is due by 1 November 2026: re-check within
   days.
4. **The provincial programmes are volatile.** Ontario closed eight streams in June 2026. NB narrowed
   its occupations. Yukon and NWT intakes for 2026 are closed. The parents-and-grandparents programme
   has been paused since 15 July 2026.
5. **Take-home pay at $100,000 ranges from about $68,900 (Nova Scotia) to $76,700 (Nunavut).**
   Among the large provinces, B.C. ($75,400), Alberta ($74,500) and Ontario ($74,200) are close.
   Quebec is about $69,300 (estimate). Sales tax runs from 5% (Alberta, territories) to 15% (NB, NL,
   PE).
6. **Health coverage starts on arrival in ON, MB, NB, NS and NL for eligible permanent residents.**
   B.C., Saskatchewan, Quebec and Yukon impose up to about 3 months. Work-permit holders face
   province-specific conditions, for example 6 months' work in Ontario or a 12-month permit in
   Manitoba. Budget for private insurance at first.
7. **Finding a family doctor is hardest in PEI, Quebec and Newfoundland and Labrador.** In 2025,
   34%, 28% and 24% of adults had no regular provider, against 11% in Ontario and 17% nationally
   (CIHI).
8. **Quebec is high-friction without French.** Provincial services are French-only after six
   months. Children of permanent residents attend French school, and temporary English authorization
   is reportedly capped at 3 years. Francization obligations now reach firms with 25 or more
   employees. A new Parti Québécois minority government (October 2026) adds policy uncertainty.
9. **The federal ban on non-Canadians buying homes ends on 1 January 2027 unless extended.** Some
   work-permit holders are exempt now: at least 183 days left on the permit, and one property.

## Open questions added

The following were appended to `OPEN-QUESTIONS.md`, under "From Agent 01":

- Canadian work or study, or a Canadian job offer?
- Membership of a 2026 Express Entry category occupation?
- A sibling or family in Canada, and where?
- Acceptance of French schooling and French-only services if Quebec ranks well?
- Income, property or pensions kept in the current country?

## Next step

1. Early November 2026 (task 01-7): update the Levels Plan record with the 2027–2029 plan.
   Confirm the 3 November CRS change and capture the high-wage occupation list. Re-check the
   non-Canadian buyer ban and Quebec immigration policy.
2. Fill the Phase 1 gaps (task 01-8).
3. When `USER-PROFILE.md` gains citizenship, occupation and family, filter every record by status
   (task 01-9). Fill the occupation placeholder, add regulator records, and rank provinces on
   immigration feasibility using SPEC §4 bands.
