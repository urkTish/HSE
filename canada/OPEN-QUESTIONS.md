# Open questions for the user

One line per question. Each says which decision it changes. Agents append;
the coordinator groups and removes answered items (recording the answer in
`USER-PROFILE.md` or `DECISIONS.md`).

## Essential (recommendations cannot be finalised without these)

1. What is your citizenship, where do you live now, and do you hold any
   Canadian status or have an application in progress? — decides which
   immigration routes exist at all.
2. What is your occupation, how many years of experience, and what
   credentials do you hold? — decides Express Entry eligibility, category
   draws, provincial nominee streams and licensing needs.
3. Who is moving with you, and how old are any children? — decides the
   school search (ages, grades, timing) and family-size housing.
4. English and French: which tests have you taken or plan to take, and at
   what level? — decides points and whether Quebec is realistic.
5. Housing budget: a monthly rent ceiling and, if buying, a purchase ceiling
   and down payment? — decides which cities pass the affordability gate.
6. When do you intend to arrive? — decides which rule changes matter.
7. Will you work for a local employer, remotely for a foreign employer, or
   self-employed? — decides the immigration route and the tax analysis.

## Important (change the ranking, not the shortlist)

8. Any hard constraints: maximum winter severity, minimum city size, a
   community you want nearby, distance to an international airport?
9. The brief names "Hand in Hand" as a comparator school. Which organisation
   do you mean (city or website)? — decides the education comparator set.
10. How would you weight the criteria in SPEC §4 (affordability, climate,
    nature and hiking, employment, healthcare, education, safety,
    transport, immigration feasibility)? — decides the comparison order.

## Housekeeping

11. Resolved 2026-10-30: the project lives in its own repository, `urkTish/Canada` (D-019).

## From Agent 02 — Real estate (appended 2026-10-30)

- (agent-02) If you buy, what immigration status will you hold on the purchase date (citizen, permanent resident, work permit with at least 183 days left, study permit, none yet)? — decides whether the federal ban (if extended past 1 January 2027) and the BC 20%, Ontario 25% and Nova Scotia 10% foreign/non-resident taxes apply.
- (agent-02) Do you plan to rent first and buy later, and would a purchase be your own home only or also a rental investment? — decides whether the analysis weights rent levels and vacancy, or yields, rent-control exposure and short-term-rental bans.
- (agent-02) How many bedrooms and what type of home do you need (apartment, townhouse, detached)? — decides which rent and price series are compared (Phase 1 uses two-bedroom rents and composite/apartment benchmarks).
- (agent-02, for the coordinator and user) Will the map be private to you or published? CREA (MLS® HPI) and CMHC terms forbid republishing their figures without consent. — decides whether stored benchmark prices may be shown in the map or only linked, and whether to request permission from CREA/CMHC.

## From Agent 06 — UI/UX (appended 2026-10-30)

- (agent-06) Should the interface be in English only, or English and French (or another language you read more easily)? — decides whether labels, number formats and place names ship bilingual from Phase 2.
- (agent-06) Will you use the map mostly on a computer or on a phone? — decides whether the mobile layout gets equal priority with the desktop-first design.
- (agent-06) For comparisons, are worded bands such as "Very weak · Weak · Moderate · Strong · Very strong" (and for winters "Very harsh … Very mild") clear to you, or would you prefer other words? — decides the band vocabulary shown in every comparison.

## From Agent 01 — National intelligence (appended 2026-10-30)

- (agent-01) Has anyone in the household worked or studied in Canada, or do you hold a Canadian job offer (occupation and province)? — decides Canadian Experience Class eligibility and the points available from the Express Entry rules in force from 3 November 2026.
- (agent-01) Does any adult work as a physician, nurse or other health worker, in a skilled trade, in transport (pilot, aircraft mechanic), as a researcher or as a senior manager, or have military experience? — decides which 2026 Express Entry category rounds you could be invited in.
- (agent-01) Do you have a brother or sister, or other close family, who is a Canadian citizen or permanent resident, and in which province? — decides sibling points in Express Entry and the "connection" factors in several provincial nominee streams.
- (agent-01) If Quebec ranked well on other criteria, would you accept French-language schooling for the children and French-only provincial services after six months? — decides whether Quebec stays on the shortlist (permanent residents' children attend French school).
- (agent-01) After moving, will you keep income, property, pensions or a business in your current country? — decides the tax-residence and tax-treaty analysis (Phase 2).

## From Agent 03 — Alternative education (appended 2026-10-30)

- (agent-03) "Hand in Hand": no Canadian school of that name was found. Did you mean the Hand in Hand bilingual school network in Israel, Hand in Hand Christian Montessori (Minnesota, U.S.), Hand in Hand Parenting, or another organisation (please give its city or website)? — decides the comparator set in `education/comparators.md` (Phase 1 reads it as "flexible, learner-led, accredited distance programme", like Clonlara).
- (agent-03) Which educational models matter most to you — learner-directed/self-directed, Waldorf, Montessori, project-based, outdoor/forest — and would full-time distance or home-based learning (e.g. a B.C. online learning school) be acceptable, or must the children attend a campus? — decides which schools qualify and whether province-wide online schools count for every location.
- (agent-03) Must the children's secondary schooling end in a provincial diploma (Dogwood, OSSD, etc.), or is a foreign/accredited diploma (e.g. Clonlara, IB) acceptable? — decides whether non-credit-granting schools and homeschooling are viable at secondary level.
- (agent-03) What annual school budget per child can you accept (for example under $10k, $10–20k, $20–30k, over $30k CAD)? — decides the cost gate; 2026-27 tuition among qualifying schools ranges from $6,240 to $37,400.
- (agent-03) If Quebec stays in scope: would you accept French-language instruction, or would you pay full fees at an unsubsidised English private school, knowing that years there do not create eligibility for English public school? — decides whether Quebec schools enter the education layer.

## From Agent 05 — Map (appended 2026-10-30)

- (agent-05) Besides the 31 principal cities now on the map (capitals and places Natural Earth lists above about 100,000 people), are there smaller towns you already have in mind, for example mountain or lake towns? — decides which places are added first when towns arrive in Phase 2.
- (agent-05) Do you want to use the map offline on a phone while travelling in Canada (saved areas)? — decides whether Phase 6 adds small offline downloads within OpenFreeMap's limits (3,000 tiles or 50 MB each) or self-hosted tiles.

## From Agent 04 — Geography and climate (appended 2026-10-30)

- (agent-04) Which winter is your limit, using the bands in `geography-climate/comparative-answers.md`: very mild (Victoria, Vancouver), mild (Okanagan, Kamloops, Kootenays, Toronto), moderate (Ottawa, Montréal, Halifax, Cranbrook), cold (Calgary, Edmonton, Québec city) or severe (Winnipeg, Saskatoon, the North)? — decides which cities pass the climate gate; Calgary and Cranbrook move in or out on this answer alone.
- (agent-04) By "more sunshine", do you mean sunnier winters (Calgary and Moncton get about 115–120 hours in January against 35–71 in BC cities) or sunnier summers and years overall (the Prairies, Victoria, the southern interior)? — decides whether Calgary or the BC interior ranks higher.
- (agent-04) In southern BC, which is the lesser evil: grey, rainy winters on the coast (Vancouver, Victoria), or hot summers with wildfire-smoke episodes in the interior valleys (Kelowna, Penticton, Kamloops, Nelson)? — decides the order within the BC shortlist.
- (agent-04) Do you plan winter backcountry activities (ski touring, snowshoeing or snowmobiling in avalanche terrain), or mainly resort skiing and summer hiking? — decides whether avalanche exposure and training belong in the location profiles.
