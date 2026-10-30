# Common rules for every specialist agent

These apply to Agents 01–06. Each agent's own charter adds its deliverables.

## Read first

1. `canada/SPEC.md` §0–§4 (context, principles, data model, coordination,
   comparison method), then your own section.
2. `canada/USER-PROFILE.md` and `canada/OPEN-QUESTIONS.md`: what is known
   about the user (almost nothing yet) and what is already asked.
3. `canada/TASKS.md`: your tasks. Mark them `doing` / `done` as you go.
4. `canada/knowledge-base/schema/*.schema.json` and the example under
   `schema/examples/`, if you produce records.

## Your lane

Write only inside your lane directory (named in your charter), plus your own
section of `canada/TASKS.md` and new lines appended to
`canada/OPEN-QUESTIONS.md`. Do not edit another agent's files. Do not run any
git command; the coordinator commits.

## Research tooling

- Load the web tools first: `ToolSearch` with query
  `select:WebSearch,WebFetch`. Use `WebSearch` to find the official page,
  `WebFetch` to read it. Prefer `.gc.ca`, provincial government domains,
  Statistics Canada, CMHC, regulators and official institution sites.
- Record `accessed: 2026-10-30` (today) on every source.
- Two attempts per page. If a site cannot be fetched, record the gap
  (`null` value plus a note naming the page) and move on. Never fill a gap
  from memory.
- Do not paste anything from `USER-PROFILE.md` into a search.

## Records

- One JSON file per record, file name `<id>.json`, conforming to
  `record.schema.json` and the category schema. Every number carries a
  source with a URL and a date; unknown values are `null` with a note in
  `limitations`.
- Validate until clean:
  `node canada/knowledge-base/scripts/validate.mjs <your lane>`.
  The coordinator rejects lanes that fail.
- Prose documents (Markdown) explain and interpret; they cite record IDs in
  backticks so the map and other agents can follow the evidence.
- `data_kind` is honest: a government figure is `official_fact`; your
  reading of it is `professional_interpretation`; a calculation on stated
  assumptions is `estimate`.

## Scope and time

- Phase 1 only (your charter lists it). Fewer well-sourced records beat many
  thin ones. Do not start Phase 2 work.
- If a task would take more than about an hour without progress, park it in
  your `STATUS.md` with the reason and the next step, and continue.

## STATUS.md (required, last thing you write)

Sections: **Done** (files and record counts, validator result), **In
progress / parked** (with reasons), **Key findings** (five to ten lines a
decision-maker would want), **Open questions added**, **Next step**.

## Final report to the coordinator (short)

- Files written (paths) and record count; validator output line.
- Five to ten key findings.
- Parked items with reasons.
- Open questions you appended.
- Anything another agent needs from you or you need from them.
