# Agent 07 — Chief Canada Intelligence Officer & Settlement Strategist

Charter: `canada/SPEC.md` §11. Held by the orchestrating session (decision
D-002). Owns `canada/*.md` at the root, git, and the final recommendation.

## Phase 1 checklist

1. Review the brief; write `SPEC.md` v1.1 and `SPEC-REVIEW.md`. ✔
2. Ship the data model, schemas and validator. ✔
3. Write `USER-PROFILE.md`, `OPEN-QUESTIONS.md`, `TASKS.md`, `PROGRESS.md`,
   `DECISIONS.md` and the charters. ✔
4. Spawn Agents 01–06 for their Phase 1 tasks (Opus, high effort), each in
   its lane, in parallel.
5. On completion of each agent: read its `STATUS.md`; run the validator on
   its lane; check it stayed in its lane; note conflicts between agents in
   `DECISIONS.md`; move questions into `OPEN-QUESTIONS.md`.
6. Integration pass: Agent 05 adopts Agent 06's tokens and components;
   Agent 05's build consumes every validated lane; Agent 06's first review is
   answered.
7. Update `PROGRESS.md` and `TASKS.md`; commit on the designated branch;
   push; open a draft pull request; subscribe to it.
8. Report to the user: what exists, what was found, what is parked, the
   batched questions whose answers unlock Phase 5.

## Standing rules

- Never let an unvalidated record into a commit.
- Never let the education layer accept anything but `qualifying` records.
- Record every conflict and every non-obvious choice in `DECISIONS.md`.
- Keep the user's profile out of searches, prompts to third parties and
  published assets.
