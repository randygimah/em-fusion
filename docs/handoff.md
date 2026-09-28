# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
it fuses replayed aviation telemetry and synthetic RF observations through a Data Abstraction Layer,
detects deviations deterministically, and turns evidence bundles into schema-validated,
grounding-checked AI hypotheses for an analyst to review. Decision support, never autonomous
decision-making.

This session built **`ai-012`, the campaign run**, then the three evaluation items that surround it:
**`eval-004`** on both halves (the sample, and the scoring pack), and **`eval-005`** (per-arm
statistics). Building the campaign forced **three amendments** (two to `db-002`, one to `ai-011`) and
**two changes to the pre-registered scoring instrument**, both argued in its change log before any
scored generation exists.

**Everything is now built except running it.** Nothing between here and a result needs code.

## Current state

**60 of 101 spec items. 1,540 tests at 99.88% in the container.**

| Item | Tests | Module coverage | Mutation |
|---|---|---|---|
| `db-002` (amended) | 58 | 100% | **44 of 44**, no survivors |
| `ai-011` (amended) | 42 | 100% | not re-run since the annotation changed; its 36 anchors were checked and still match |
| `ai-012` campaign run | 28 | 100% | **37 of 39**, no unexpected survivors (2 declared equivalences) |
| `eval-004` sample + pack | 17 + 17 | 100% | not yet written |
| `eval-005` statistics | 20 | 100% | not yet written |

**The three evaluation modules touch no database and no model.** Bundles, hypotheses and scenario
types all arrive as the caller has already read them, so every join that reaches ground truth is in
the open and the corpus decision, the arithmetic and the rendering are all checkable without Docker.
They also run on the host in `backend/.venv`, which is what let them be built while a mutation pass
had the container.

**`ai-012`** asks the model arm through `ai-007`'s *recorded* path, so the ungrounded attempts become
rows rather than disappearing. The verdict written into a row comes from the **pure** check, not the
ledger-attached one — the fallback's checker has already counted that generation, and a second entry
would halve the catch rate `eval-005` reports as a result. The replacement is neither counted against
the arm that was asked nor marked as checked. A per-bundle failure is recorded and skipped;
`BudgetExceeded` and `ConfigurationError` stop the run, needing no `except` clause of their own
because they sit outside the `GenerationError` tree for exactly that reason, and the abort still hands
back the partial record. The sample is an **input** and is never invented.

**Three defects in the store, found by building its first real caller**, each a thing the schema could
express and no code could produce:

1. The three-valued grounding column had a writer for **one** of its three values. `record_grounding`
   now writes the other two, taking `ai-008`'s report rather than a bool so *not yet checked* is
   unconstructible as an input.
2. `ai-003`'s port drops the refusals, which are the rows the append-never-replace rule was argued
   for. `AssembledArm.generator` is now typed as the concrete fallback.
3. A fallback row and the baseline row for one bundle were **byte-identical**. `requested_generator`
   (migration `0007`) fixes it; `generator != requested_generator` is the *definition* of a fallback
   rather than a state to refuse. This also unblocks `ai-010`, which was unbuildable rather than
   unbuilt.

**The pre-registration was amended twice** (`docs/scoring_rubric.md` change log, 2026-09-27):

- The **stratification correction** the backlog made on 21 September and this document was never
  told. 10 interference + 10 fault, not five from each of four scenario types.
- **N raised from 1 to 3 generated, the first scored, never substituted.** N=1 rested on temperature 0
  returning the identical answer; the trial measured 4 of 5 repeated pairs different. Scoring all
  three was rejected **on the consent form, not the budget** — 280 values and ninety minutes is what
  the second rater agreed to, and 560 and three hours is a re-consent.

## Files in flight

Clean apart from the two mutation harnesses and their logs, which are mid-re-run.

Added: `backend/app/ai/campaign.py`, `backend/tests/test_ai_campaign.py`,
`backend/alembic/versions/0007_hypothesis_requested_arm.py`,
`backend/measurements/mutation/mutate_ai012_campaign.py` (+ `.log`).

Modified: `backend/app/db/hypotheses.py`, `backend/app/ai/assembly.py`,
`backend/tests/test_db_hypotheses.py`, `backend/tests/test_ai_assembly.py`,
`backend/tests/conftest.py` (gained the shared database fixtures),
`backend/measurements/mutation/mutate_db002_hypotheses.py`, `docs/spec.jsonl`,
`docs/scoring_rubric.md`, `docs/thesis_notes.md`, `docs/qa.md`, `docs/implementation.md`,
`docs/progress_note.html`, `CLAUDE.md`.

## Changed

| Commit | What |
|---|---|
| `a869658` | `spec: add ai-012, amend db-002, ai-011 and eval-004` |
| `c877627` / `76adac7` | db-002 tests, then the verdict writer and the asked-for-arm column |
| `e5ff7e9` | `docs: scoring rubric — two change-log entries before the first scored request` |
| `aeae297` / `28654cf` | ai-011 tests, then the concrete type on the assembled arm |
| `ed31f81` / `9240fa5` | ai-012 tests, then the campaign run |
| `9e1eefd` | `docs: ai-012 write-up — qa 95 and 96, the phase checklist, the repo map` |
| `c2f1e76` | `docs: progress note — the run that asks twenty questions, and the N change` |
| `2ea451d` | `test: strengthen three ai-012 tests after the mutation pass` |
| `2d1bdd1` | `docs: the mutation-pass findings, and two faults in the instrument` |

Progress note republished as **version 12** at
<https://claude.ai/code/artifact/eb2d4ccd-c424-4fca-871d-b652dd37bc35>.

## Failed attempts

- **A test double returned a hypothesis grounded in one bundle while the sample holds two.** Three
  tests failed reporting counts and verdicts that were entirely correct for what had happened: the
  scripted "correct" answer cited evidence the other bundle did not contain, the grounding check
  caught it exactly as designed, the arm retried and fell back. A double standing in for something
  whose output must be *consistent with its input* cannot be a constant, and the failure it causes is
  diagnosed as a defect in the code under test.
- **A permissive stub found a test weaker than its name**, for the second time in this phase. *"The
  row a fallback delivered is not marked as checked"* passed against a stub that marked **everything**
  not-checked. It now asserts the contrast in the same campaign. Fifth occurrence of that defect
  family.
- **Two gaps the mutation pass found, and they are the same gap twice.** A test asserting the
  in-memory record and never the stored row — which is the defect the verdict writer was added to fix,
  reappearing one layer up, on the same day. And a property whose interesting case no real input can
  reach: the baseline cannot fail the grounding check, being grounded by construction, so swapping the
  recording call for the raising gate changed nothing any test could see.
- **A mutant that does not parse tests nothing.** One new mutant produced an `IndentationError`; the
  module failed to import, 45 tests errored, and the harness saw a non-zero exit plus a test summary
  and scored it KILLED. It slipped past the existing no-summary guard *because* a broken import still
  produces a summary. Second occurrence. Both harnesses now check, before a pass runs, that every
  anchor matches the formatted source exactly once **and** that every mutated file parses.
- **A harness scoped narrower than the thing it scores manufactures gaps.** The mutant widening
  `AssembledArm.generator` survived because the test pinning it lives in `test_ai_assembly.py` and the
  harness ran only `test_ai_campaign.py`. It now runs both.
- **A monitor matched a stale log.** Waiting for the re-run, the until-condition matched the *previous*
  run's output because the second script had not started and its log was untouched. Delete or check
  the mtime of a log before waiting on its contents.
- **`record.skipped` is a tuple and the test compared it to a list.** Caught immediately by the suite;
  noted only because it is the third assertion in this repository to compare two different container
  types and mean equality.

## Next step

**Three commands, then a person.** No code is missing.

1. **Draw the twenty and commit them.** Free, and it must land *before* any scored request:

   ```
   make measure SCRIPT=corpus/draw_scored_sample.py CORPUS=dev
   ```

   then commit `backend/measurements/corpus/scored_sample.json`. The campaign script refuses to run
   without it rather than helpfully drawing one, which is what makes "the corpus was fixed first" a
   property of a file in the repository rather than of a promise.

2. **Run the campaign.** About **80p** of the $4.92 left — 20 bundles x 3 model generations + 1
   baseline, estimated $0.97 before the ~19% the estimate has been running high.

   ```
   make measure SCRIPT=corpus/scored_campaign.py CORPUS=dev CAMPAIGN_CONFIRM=yes
   ```

3. **Emit the pack** and hand it to the second marker. `eval-004`'s export is built; what is missing
   is a thin script to read the campaign record and the stored hypotheses and write the three files.

4. **`eval-006`**, the only unbuilt evaluation item: ingest two completed sheets, join the arm key
   *after* both are in, apply the pre-registered adjudication rule, and report quadratic-weighted
   kappa over the full double-scored corpus.

5. **Revisit the local arm** (`ai-005`/`ai-006`) with the hosted arm's measured reliability in hand.

Open and unowned:

- **`ai-011`'s own mutation harness has not been re-run** since its module changed (one annotation).
  Its 36 anchors were checked and all still match the amended source and parse, so it needs running
  rather than repairing.
- **The three evaluation modules have no mutation harnesses**, which is the largest outstanding
  quality gap: 54 tests with nothing yet establishing that they are load-bearing.
- **`eval-004`'s export has no entry point**, the way the campaign now has one.
- The credential-loading remedy still exists in two places; see step 2.
- `ai-008`'s **superseded failure case has no corpus demonstration** — 0 of 41 bundles carry one.
- The near-miss "rule under another finding type" bucket **conflates two mistakes**; split it before
  the campaign if it turns out to carry weight, since the classification is what gets reported.
- **Six mutation harnesses still lack the crash guard and sentinel.** `ai-008`, `ai-011` and now
  `db-002` and `ai-012` have both.
- `docs/phase9_hypothesis_layer.md` §8 still says N is fixed at 1. Superseded by the `eval-004`
  amendment and the rubric change log; left as pre-build reasoning, following the phase-8 documents.
- The run budget is **held in memory**, so a process that dies and restarts counts from zero.
- Regenerate corpus v2 for `eval-001`.
- 13 committed files are not Black-formatted. `tests/test_db_hypotheses.py` is one of them, and this
  session's additions to it deliberately match its existing style rather than Black's.
- Frontend suite exits non-zero: `control.runs.map is not a function` at `scenarioControl.tsx:344`.
- Broadband generation arm; nine measurement scripts still select runs by means other than `scn-008`'s
  provenance; `CORPUS_V2_PLAN.md` and `DEV_BATCH_PLAN.md` still sit at the repo root.
- `docs/progress_note.html` begins with its own `<!doctype html><html><head>` wrapper, so the
  published page double-wraps. It has rendered correctly for twelve versions and is left alone
  deliberately.
