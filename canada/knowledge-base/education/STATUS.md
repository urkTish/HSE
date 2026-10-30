# Agent 03 — Alternative education · STATUS

Phase 1 · last updated 2026-10-30 · written for a reader who did not watch the work.

## Done

Files (all under `canada/knowledge-base/education/`):

- `regulation-by-province.md` — rules for every province and territory (full
  sections for BC, AB, ON, QC, NS; first-pass notes for MB, SK, NB, PE; NL, YT,
  NT, NU parked), the Québec Charter section, and a side-by-side table.
- `regulation/` — 6 `nat` records, `responsible_agent: agent-03`:
  `nat-bc-education-independent-schools-and-home-learning`,
  `nat-ab-education-independent-schools-and-home-education`,
  `nat-on-education-private-schools-and-homeschooling`,
  `nat-qc-education-private-schools-and-home-schooling`,
  `nat-qc-education-english-instruction-eligibility`,
  `nat-ns-education-private-schools-and-home-education`.
  Slugs carry `education-` so they cannot collide with Agent 01's `nat-qc-*` ids.
- `schools/` — 26 `school` records: BC 9, AB 4, ON 7, QC 3, NS 3.
  - **qualifying: 11** — Vancouver Waldorf, Nelson Waldorf, Westmont Montessori,
    Selkirk Montessori, Calgary Waldorf, Banbury Crossroads, Toronto Waldorf
    School, Waldorf Academy, The Mabin School, The Element, Class Afloat.
  - **unverified_candidate: 11** — SelfDesign, Oak and Orca, Coast Mountain
    Academy, Whistler Waldorf, Phoenix Education Foundation, Lauremont, Virtual
    High School, Rudolf Steiner School of Montréal, Montessori Orford, Halifax
    Independent School, Shambhala School.
  - **excluded: 4** — Mountainview Montessori (public, Surrey), Parkside
    Montessori (public, Grande Prairie), ALPHA Alternative (TDSB), École Le
    Vitrail (public, Montréal).
- `schools-overview.md` — comparative table and worded evaluation of the 11
  qualifying schools by the SPEC §7 criteria.
- `comparators.md` — Clonlara attributes, the "Hand in Hand" candidates, the
  closest Canadian institutions.
- Validator: `32 record(s) checked, 0 failed, 0 warning(s), 0 non-record JSON file(s) skipped.`

Method: official school sites read with WebFetch or a direct fetch; legal status
checked against provincial registers downloaded on 2026-10-30 (B.C.
independent-school register with Group Classification; Alberta School and
Authority directory, extract 2026-10-28; Ontario private-school list, updated
2026-10-22; Québec private-installation open data, 2026-10-26; Nova Scotia
recognised private schools, 2026-10-14). Coordinates from register geocodes or
OpenStreetMap Nominatim on the official address, with precision stated. No
images copied; official pages linked.

**Coordinator note (Québec) — done.** Read Agent 01's
`nat-qc-english-schooling-eligibility` and cite it instead of repeating it.
`nat-qc-education-english-instruction-eligibility` now covers what it leaves out
— unsubsidised private schools, home schooling and CEGEP — from primary texts.
It also **sources the three-year cap to the statute**: Charter s.84.1, enacted
by Bill 96 (S.Q. 2022, c.14, s.57). The cap is "up to three years and may not
be renewed", extended to 30 June. Bill 96 s.169 rewrote s.7 of Regulation
C-11, r.7 so that every temporary exemption lasts up to 3 years. The 1997 text
of that regulation (Gazette, O.C. 608-97) is also recorded; it allowed renewal,
which explains the conflicting renewal guidance online. Both texts were read
from Publications du Québec. LégisQuébec and CanLII returned HTTP 403 twice, so
any change after 2022 to the consolidated texts is recorded as a gap.

## In progress / parked

- **11 unverified candidates** (reasons in each record). Fees are unpublished or
  undated at SelfDesign, Oak and Orca, Coast Mountain, Lauremont, VHS, ERSM and
  Orford. Whistler Waldorf (HTTP 403) and Shambhala (HTTP 401) blocked automated
  reading on two attempts. Phoenix showed headings only. Halifax Independent has
  no public N.S. register to check against. Next step: email or phone the
  schools, or retry later; SelfDesign and Oak and Orca come first, as the
  closest Clonlara analogues.
- **Provinces and territories:** MB, SK, NB and PE have first-pass notes only.
  NL, YT, NT and NU are not researched. Next step: read each ministry page and
  add `nat` records.
- **Alberta funding rate (≈70 %)** comes from secondary sources only. Next step:
  the Alberta Funding Manual for School Authorities.
- **Québec consolidated statutes** are blocked (HTTP 403). Next step: retry
  LégisQuébec, or ask the coordinator for another route.
- **`nearby_cities_km`** is left null for every school until Agent 04's city
  records exist (task 03-6).
- The market is not exhausted. Ontario lists about 1,640 private schools,
  including many forest schools, and B.C. about 325 independent schools.
  Phase 1 picked representative, priority-province institutions.

## Key findings

1. **B.C. is the most favourable province for alternative schooling.** Group 1
   independent schools get 50 % of the local per-student grant, so Waldorf and
   Montessori fees are low: Nelson Waldorf $6,240 and Selkirk about $12,000,
   against $22,500–$26,470 for Waldorf in Toronto. Funded independent online
   learning schools offer learner-directed study with a Dogwood diploma.
2. **The closest Canadian analogue to Clonlara is SelfDesign Learning
   Community (B.C.).** It is a Group 1 online school with interest-based plans,
   a certified consultant and a Dogwood. Oak and Orca comes next. Both are
   limited to B.C. residents and are still unverified on cost. SelfDesign is
   full or waitlisted for 2026-27.
3. **Ontario does not oversee private elementary schools.** It gives no
   funding, licensing or inspection unless a school grants OSSD credits, and
   teachers need not be certified. Families must vet these schools themselves.
4. **In Québec, the children of permanent residents who are not citizens are
   taught in French.** Permit-holder families can get English instruction for
   at most three years, non-renewable (Charter s.84.1, Bill 96).
   **Unsubsidised English private schools** are legal at full cost, but years
   spent there do not open the English public system (Bill 104, 2002).
   Home schooling may be in English with French as the second language.
   English CEGEP places are capped (17.5 %) and go first to eligible students.
5. **Montessori beyond age six is rarer than the label suggests.** It is
   confirmed to Grade 8 at Westmont and Selkirk, and for Grades 7–12 at
   The Element. Lauremont stops Montessori at Grade 6.
6. **Waldorf to Grade 12 with a diploma** is confirmed only at the Toronto
   Waldorf School (OSSD). Whistler Waldorf appears K–12 in the B.C. register
   but is unverified.
7. **Alberta lets private authorities supervise home education with public
   money.** Parents can claim 50 % of the grant. Banbury Crossroads
   (self-directed, JK–12, $17,600) is the strongest on-site self-directed
   school found.
8. **"Hand in Hand" matches no Canadian school.** The well-known matches are an
   Israeli bilingual school network and a Minnesota Christian Montessori
   homeschool academy.
9. **Many attractive "alternative" schools are public** and therefore out of
   scope: TDSB's ALPHA, B.C. district Montessori schools and Québec's roughly 50
   RÉPAQ schools. They are recorded as excluded.

## Open questions added (appended to `canada/OPEN-QUESTIONS.md`)

- Which organisation "Hand in Hand" refers to (city or website), with the
  candidates listed.
- Which models matter most, and whether full-time distance or home-based
  learning is acceptable.
- Whether a provincial diploma is required, or a foreign/accredited diploma
  (Clonlara, IB) is enough.
- Annual school budget per child (bands).
- If Québec stays in scope: whether French instruction, or a full-fee
  unsubsidised English private school, is acceptable.

## Next step

Contact or re-fetch the 11 candidates to move them to qualifying or excluded,
starting with SelfDesign and Oak and Orca. Add `nat` records for the remaining
provinces and territories. Once Agent 04's city records exist, fill
`nearby_cities_km`. When the user answers on children's ages, models and budget,
narrow the education layer and widen the search in the shortlisted regions.
