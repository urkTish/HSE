# Canada Intelligence & Exploration System

Where in Canada to settle, and how to explore it once there: a coordinated
multi-agent research project with a shared, validated knowledge base and an
interactive map.

**Status:** Phase 1 (research foundation) complete on 2026-10-30. Current
state, next steps and parked items are in `PROGRESS.md`.

## Start here

| File or folder | What it is |
|---|---|
| `SPEC.md` | Master specification, v1.1 |
| `SPEC-REVIEW.md` | What changed from the original brief and why |
| `PROGRESS.md`, `TASKS.md`, `DECISIONS.md` | Coordination: state, task board, decision log |
| `OPEN-QUESTIONS.md`, `USER-PROFILE.md` | Questions for the user; the user's requirements record |
| `agents/` | One charter per agent (01–07) |
| `knowledge-base/` | JSON records by lane with prose, `schema/`, and `scripts/validate.mjs` |
| `map/` | The application (`map/app`), `ARCHITECTURE.md`, `DATA-SOURCES.md` |
| `design/` | Design system, tokens, wireframes, reviews |
| `archive/` | Superseded documents (the v1.0 brief) |

## Validate the knowledge base

```bash
node knowledge-base/scripts/validate.mjs
```

## Run the map

```bash
cd map/app
npm ci
npm run build-data
npm run dev
```

Checks: `npm run lint`, `npm run typecheck`, `npm run build-data -- --strict`,
`npm run build`.

## Rules that shape everything

Primary sources first; provenance on every figure; no fabricated data (unknown
is `null` with a note); prices and rents are never stored in the map, they are
retrieved on demand with their date and source; the education layer shows only
verified, qualifying private alternative schools; climate uses Environment and
Climate Change Canada normals, never forecasts; the user's profile never leaves
this repository.

## Data licences

`map/DATA-SOURCES.md` lists every dataset, tile source and font with its
licence and attribution text. CREA and CMHC figures are not republished
(decision D-008).
