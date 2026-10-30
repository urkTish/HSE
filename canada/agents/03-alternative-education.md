# Agent 03 — Canadian Private Alternative Education & Schooling Specialist

Charter: `SPEC.md` §7. Common rules: `agents/00-common-rules.md`.
Lane: `knowledge-base/education/`.

## Phase 1 deliverables

1. **`regulation-by-province.md`** — one section per province and territory:
   legal term and definition for a non-public school; registration,
   accreditation and inspection; funding categories; curriculum
   obligations; whether and how a non-public school grants the provincial
   diploma; homeschooling law (registration, supervision, funding); rules
   for online and distance schools; parent obligations. For Quebec, the
   Charter of the French Language eligibility rules for English-language
   instruction as they apply to newcomer children, and how unsubsidised
   private schools fit, with the source and date. Create `nat-<prov>-*`
   records (`responsible_agent: agent-03`) at least for BC, AB, ON, QC and
   NS.
2. **`schools/<id>.json`** — `school` records. Target at least twenty-five
   institutions, priority provinces BC, AB, ON, QC, NS, then the rest. Each
   record states `qualifying` (`qualifying`, `unverified_candidate`,
   `excluded`) and the reason. A `qualifying` record must be `verified`
   (official website read, model confirmed beyond marketing, legal status
   confirmed against the provincial register where one is public, tuition
   with its school year). Coordinates come from the official address;
   state `coord_precision`. Link official photographs; copy nothing.
   Public schools and public alternative programmes are `excluded` with the
   reason, so nobody re-adds them.
3. **`schools-overview.md`** — a comparative table (province, city, model,
   ages, tuition and year, legal status, qualifying status) and a short
   evaluation of the qualifying institutions by the SPEC §7 criteria.
4. **`comparators.md`** — what "comparable to Clonlara" means in attributes
   (accreditation, learner-directed programme, distance support, diploma);
   the "Hand in Hand" ambiguity and the candidates it could refer to; which
   Canadian institutions come closest.
5. **`STATUS.md`** and your open questions in `OPEN-QUESTIONS.md`.

## Standards specific to this lane

- Many "Montessori" schools stop at age six; record the real age range.
- A religious school qualifies only for an independently qualifying model.
- Tuition `next_review`: the start of the next school year.
