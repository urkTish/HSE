# Progress — Canada Intelligence & Exploration System

## Current

- **Phase 1 — Research foundation: done 2026-10-30.** Definition of done
  (SPEC §13) checked below.
- **Phase 2 — Geographic and climate foundation: next.**
- Repository: `urkTish/Canada` (D-019). Coordinator: the orchestrating
  session (Agent 07). Specialists ran on Opus at high effort (D-007).

## Phase 1 — definition of done, checked

- Schemas and validator exist and pass on every lane:
  `node knowledge-base/scripts/validate.mjs` → 358 records, 0 failed.
- Agents 01–04 each have a `STATUS.md` and validated records:
  national 54 `nat`; real estate 96 `re` + 32 `nat`; education 26 `school`
  (11 qualifying, 11 unverified candidates, 4 excluded) + 6 `nat`;
  geography and climate 61 `clim` (38 cities and towns, all 13
  jurisdictions), 18 `landform`, 13 `region`, 21 `hazard`; plus 31 `city`
  gazetteer records from Agent 05.
- Agent 05: `map/ARCHITECTURE.md`, `map/DATA-SOURCES.md`, a running app
  (`lint`, `typecheck`, `build-data --strict`, `build` all pass; 286 records
  published, 72 excluded by rule: 15 non-qualifying schools and 57 CREA or
  CMHC-only market figures under D-008). Twelve layers with distinct marker
  shapes, province profiles, city profiles with the climate chart, keyboard
  path, attribution from the data-source register.
- Agent 06: `design/design-system.md`, `tokens.css` (light and both dark
  scopes), `tailwind-theme.css`, six self-contained wireframes,
  `components.md`, two dated reviews (6.5/10 then 8/10 after fixes).
- `OPEN-QUESTIONS.md` lists the seven essential unknowns plus twenty
  agent questions.

## Lane highlights (details in each lane's STATUS.md)

- **National (01):** Express Entry now favours candidates in Canada or in a
  category; ranking rules change 3 November 2026; permanent-resident
  targets flat at 380,000 for 2026–2028; health-plan waiting periods differ
  by province; Quebec without French is high-friction. Quebec official
  sites blocked fetches, so those records are partially verified.
- **Real estate (02):** federal non-Canadian purchase ban scheduled to end
  1 January 2027; provincial non-resident taxes (BC 20%, ON 25%, NS 10%)
  do not; Ontario markets 28–33% below 2022 peaks; vacancy up in 19 of 20
  centres; cheapest two-bedroom survey rents in Sherbrooke, Québec,
  Charlottetown and Montréal; CREA and CMHC terms forbid republishing.
- **Education (03):** BC is the strongest province for funded alternative
  schooling; SelfDesign is the closest Canadian analogue to Clonlara
  (unverified fees); Ontario does not oversee non-credit private schools;
  Quebec caps temporary English schooling at three years (statute read);
  "Hand in Hand" matches no Canadian school.
- **Geography and climate (04):** Victoria is the only city in the top two
  bands for both winter mildness and sunshine; southern BC interior is mild
  but smoky and dull in winter; Calgary is the sunniest; airport stations
  can mislead by 2 °C or 30% precipitation; sunshine normals exist only for
  1981–2010.
- **Map (05) and design (06):** see `map/STATUS.md` and `design/STATUS.md`.

## Next

- **User:** answer `OPEN-QUESTIONS.md` items 1–7; they unlock the
  settlement shortlist (Phase 5).
- **Map (05):** 05-7 attribution legible and never hidden (licence
  requirement), mobile bottom sheet, cluster overlap; 05-8 city population
  and small towns; Statistics Canada boundaries; NRCan terrain;
  code-splitting the 1.35 MB bundle.
- **Real estate (02):** 02-6 parked rules; 02-6b mountain-town `re`
  records; Statistics Canada vector IDs on `re` records for Phase 4.
- **Education (03):** 03-5 settle the 11 unverified candidates; `nat`
  records for the remaining provinces and territories; 03-6 distances.
- **Geography and climate (04):** 04-6 parked gaps (Thunder Bay
  precipitation, Nelson, PEI erosion, 2013 Alberta flood figures,
  Appalachian pages); parks and trails.
- **National (01):** 01-7 to 01-9 (2027–2029 Levels Plan in November,
  3 November ranking change, IRCC processing times, Quebec sources).
- **Design (06):** Phase 2 high-fidelity mock-ups with the real fonts,
  neighbourhood view, French copy.

## Parked

- Listed per lane in `TASKS.md` (02-6, 03-5, 04-6) and each `STATUS.md`.

## Known limitations

- No user facts yet: every recommendation is conditional.
- Several official sites (Revenu Québec, RAMQ, LégisQuébec, PEI, some
  cities) block automated fetches; affected records are
  `partially_verified` or `null`.
- 1991–2020 normals carry no sunshine; sunshine comparisons use 1981–2010.
- Market figures are dated snapshots (MLS HPI September 2026; CMHC survey
  October 2025); the map stores none of them.
- Natural Earth boundaries and cities are a first pass; Statistics Canada
  replaces them in Phase 2.
