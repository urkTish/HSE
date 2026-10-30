# Specification review — v1.0 → v1.1

Reviewed 2026-10-30 by the coordinating session (Agent 07 role). The original
is kept unchanged at `archive/spec-v1.0-original.md`; the corrected
specification is `SPEC.md`.

## Verdict

The v1.0 brief is strong on *what* each agent should know and weak on *how*
the agents work together: it had no data model, no handoff mechanism, no
user profile, and two internal contradictions. It also carried Pandoc
conversion damage that flattened most lists into run-on paragraphs, which
would have degraded it as an agent prompt. All of this is fixed in v1.1
without changing the roster, the two product modes, the phase order or the
product vision.

## Findings and fixes

| # | Severity | Where in v1.0 | Issue | Fix in v1.1 |
|---|---|---|---|---|
| 1 | High | Whole document | Pandoc artefacts: lists collapsed into paragraphs ("Identify: - Advantages…"), a grid table, `---` for dashes, inconsistent numbering. | Reformatted throughout: real lists, a pipe table, normalised headings. Content preserved. |
| 2 | High | §1 "Shared research record"; Phase 1 "Define shared data schemas" | Fields were listed but there was no schema, ID convention, enumeration set, unit/CRS/date rule or file layout. Four research agents would have produced four incompatible formats. | §2 shared data model; JSON schemas in `knowledge-base/schema/`; validator `knowledge-base/scripts/validate.mjs`. |
| 3 | High | Every "work with…", "request…", "supply…" | No mechanism for file-based agents to hand off work, record status, or resolve conflicting figures. | §3 coordination protocol: `TASKS.md`, per-lane `STATUS.md`, lanes, `DECISIONS.md`, conflict rule. |
| 4 | High | Agent 07 "Do not invent the user's preferences" | The brief contains no facts about the user. Immigration feasibility, tax, schooling eligibility and budget all depend on them, yet nothing captured the gap. | §0 lists the essential unknowns; `USER-PROFILE.md` and `OPEN-QUESTIONS.md` created; inferred preferences marked "to confirm". |
| 5 | High | Agent 04 "Scoring system" vs Phase 5 "weighted comparisons" | Contradiction: "never manufacture precise scores" against "generate weighted comparisons". No method reconciled them. | §4 comparison method: evidence-backed ordinal bands with written thresholds, user weights, essential-requirement gates, sensitivity shown, missing data shown as missing. |
| 6 | High | Agents 01 and 03 | Quebec's Charter of the French Language (eligibility for English-language schooling, language of work and services) was absent. For a newcomer family weighing Quebec it changes the education layer entirely. | Added to Agent 01 (B) and Agent 03 (legal section) as a required research item. |
| 7 | Medium | Agent 04 climate | "1991–2020 where applicable" left the period choice open. ECCC publishes 1991–2020 normals for a subset of stations; most long records are 1981–2010. Mixed periods would have been compared silently. | Reference-period rule: 1991–2020 where published, otherwise 1981–2010, always labelled per row; station and distance from the city centre stated. |
| 8 | Medium | Agent 04 physical geography | The Hudson Bay Lowlands, Arctic Lowlands and Innuitian Mountains, the Laurentians and the Torngat Mountains were missing from the list of landforms. | Added, framed by Canada's physiographic regions. |
| 9 | Medium | Agent 03 scope | "Hand in Hand" is ambiguous (several unrelated organisations share the name); Clonlara was cited without saying which attributes matter. | Open question for the user; working definition given until answered. |
| 10 | Medium | Agent 03 profile item 12; Agent 05 "Photographs" | Copying school, park and tourism photographs is a copyright problem the brief did not address. | Principle 12: link to official media, store only openly licensed imagery with attribution; `map/DATA-SOURCES.md`. |
| 11 | Medium | Agent 02 | Who may buy depends on immigration status: the federal prohibition on purchases by non-Canadians and provincial non-resident taxes were not named, and no dependency on Agent 01 existed. The brief also did not say *why* the map must not store prices (board and CREA terms of use). | Added to Agent 02 (C) and research standards; dependency on Agent 01 `nat` records. |
| 12 | Medium | Agent 02 rental markets | Survey rents (CMHC) and asking rents (listing platforms), and benchmark (HPI) versus average/median prices, were not distinguished. | Added to areas A and B and to the comparative rules. |
| 13 | Medium | Agent 05 H | "Mapbox or MapLibre" and an open list of options would let agents diverge, and Mapbox requires a paid account. | Defaults chosen (MapLibre GL JS, open vector tiles, Statistics Canada boundaries, NRCan elevation, OSM under ODbL, open routing/geocoding, Vite + React + TypeScript + Tailwind), each revisable through `DECISIONS.md`. |
| 14 | Medium | Agent 05 G | The map receives from Agents 01–04 only; Agent 06's tokens, components and reviews were not an input although Agent 06 is told to "work directly with the Map Architect". | Agent 06 added as an input in §9 G. |
| 15 | Medium | Agent 06 | No concrete deliverables; "wireframes and prototypes" unspecified; no accessibility standard. | Deliverables list (design-system.md, tokens.css, wireframes/, components.md, dated reviews); WCAG 2.2 AA, keyboard, reduced motion. |
| 16 | Medium | §10 phases | No definition of done or acceptance check for any phase. | A "done when" line per phase in §13. |
| 17 | Medium | Principle 7 "next review date" | No default review cadences, so every record would need an ad-hoc date. | §2.7 freshness table. |
| 18 | Medium | — | No privacy rule for the user's personal and family profile, which could otherwise leak into web searches or published map assets. | Principle 11. |
| 19 | Low | §1 units | No coordinate reference system, precision rule or date format. | §2.4. |
| 20 | Low | Agent 07 "ask one focused question" | Blocks autonomous runs. | Unattended rule in §0 and §11: proceed on the smallest labelled assumption, log the question. |
| 21 | Low | Agent 01 C | Credential recognition stated generically; the user's own profession and NOC code should come first. | Added. |
| 22 | Low | Agent 04 F | Duplicates Agent 01 and 02 research (tax, healthcare, housing). | Cite their records instead of re-researching. |
| 23 | Low | — | No repository layout, so lanes and outputs had no home. | §14. |
| 24 | Low | Intro, §1 | Agent 06 is a designer, yet the research-record rules were written as if for six researchers. | §3 roles; principle 8 now refers to records produced by whoever produces them. |
| 25 | Low | Agent 05 B residential | "Do not permanently embed" was clear; added that figures are never built into the application's static assets, which is the practical failure mode. | Clarified. |
| 26 | Info | — | The host repository is an unrelated HSE platform. | Decision D-001: the Canada system lives in `canada/` on the designated branch, isolated from the HSE CI, and can be split out later. |

## What was deliberately not changed

- The seven-agent roster and each agent's domain.
- The two application modes and the stored-versus-on-demand split.
- The phase order.
- The strict rule that the education layer shows only verified qualifying
  private alternative schools.
- The product vision.
