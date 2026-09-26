# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
it fuses replayed aviation telemetry and synthetic RF observations through a Data Abstraction Layer,
detects deviations deterministically, and turns evidence bundles into schema-validated,
grounding-checked AI hypotheses for an analyst to review. Decision support, never autonomous
decision-making.

This session built **`ai-008`, the grounding check**, then **`ai-011`, run assembly**, and took the
project to the point where **one command makes the first real model request**. `ai-011` was not on
the plan: it was added because the gate could not be reached without it.

## Current state

**Both items pass. 57 of 100 spec items.** 1439 tests at 99.86% in the container.

| Item | Tests | Module coverage | Mutation |
|---|---|---|---|
| `ai-008` grounding check | 58 | 100% | **46 of 46**, no survivors |
| `ai-011` run assembly | 39 | 100% (+ registry) | **36 of 36**, no survivors |

**`ai-008`** resolves every citation against the bundle it came from. Three verdicts, not two: the
bundle deliberately carries the claims the ladder *rejected*, so a check verifying that an identifier
*exists* would certify a hypothesis citing one as support — reading two rules' disagreement as two
rules' agreement, the exact error it exists to catch. Matching is exact and near misses are recorded
without softening the verdict. The arm is declared, and a catch rate over zero checks is `None`
rather than 0.0.

Measured over the 41 stored bundles (`measurements/corpus/grounding_catch_rate.log`): **0 flagged of
164 citations**, and **164 of 164 deliberate corruptions caught**, 41 of 41 on each of four kinds.

**`ai-011`** composes the arm. The budget nests inside the fallback; the arm is named once and
derived at all three places needing it; prices reach the adapter through the registry. Two bad
configurations are unconstructible (exactly one price; a price of zero) and one is refused (a spend
ceiling with no prices — the only place that can see both).

**The model is pinned: `gpt-4.1-2025-04-14`.** Chosen for the two properties the reproducibility
claim rests on — schema-constrained output and honouring `temperature` — not price or recency.

**Ready and not yet run:** `measurements/corpus/hosted_smoke_test.py`. Three bundles, printed in full
to be hand-read. Refuses without `SMOKE_TEST_CONFIRM=yes`. Pre-flight verified: the credential is
readable inside the container (never printed), the spend guard refuses, ceiling 6 calls / $0.25,
expected spend about $0.03.

```
make measure SCRIPT=corpus/hosted_smoke_test.py CORPUS=dev SMOKE_TEST_CONFIRM=yes
```

## Files in flight

The tree is clean except for the documentation commit in progress. Nothing half-built.

Added this session: `backend/app/ai/grounding.py`, `backend/app/ai/assembly.py`,
`backend/tests/test_ai_grounding.py`, `backend/tests/test_ai_assembly.py`,
`backend/measurements/corpus/grounding_catch_rate.py` (+ `.log`),
`backend/measurements/corpus/hosted_smoke_test.py`,
`backend/measurements/mutation/mutate_ai008_grounding.py` (+ `.log`),
`backend/measurements/mutation/mutate_ai011_assembly.py` (+ `.log`).

Modified: `backend/app/ai/registry.py` (forwards construction keywords), `Makefile`, `.gitignore`,
`README.md`, `docs/spec.jsonl`, `docs/thesis_notes.md`, `docs/qa.md`, `docs/implementation.md`,
`docs/progress_note.html`, `backend/measurements/README.md`, `CLAUDE.md`.

## Changed

| Commit | What |
|---|---|
| `08e4748` | `spec: amend ai-008 — the arm is declared, the oracle must not share the fault` |
| `6805a40` / `26ce6a6` | ai-008 tests, then strengthened against a permissive check |
| `e6d3232` | `feat(ai-008): the automated grounding check - tests pass` |
| `6509355` / `9a3d87c` | ai-008 write-up, then the corpus measurement log of record |
| `077ef3c` | `docs: progress note — checking what a model says against what it was shown` |
| `51974dd` | `docs: qa 93 — what the catch rate counts, and why near misses do not add to it` |
| `fa6720d` / `5451556` | `spec: add ai-011`, then corrected — the ceilings arrive inside the budget |
| `f45905b` | `spec: amend ai-003 — the registry forwards construction keywords` |
| `32da64c` | `feat(ai-011): run assembly for a model arm - tests pass` |
| `0a9c715` | `test: strengthen two ai-011 refusal tests after the mutation pass` |
| `ab79a2d` | `feat: the three-bundle hosted smoke test, and a root .env guard` |

## Failed attempts

- **A coverage figure was wrong and it was my doing.** The first full-suite run reported 99.50% with
  18 missed statements. I had run Black over the source *while the suite ran against the bind mount*,
  so coverage mapped stale line numbers onto a changed file. The clean re-run gave 99.86%, 5 missed.
  **Do not touch `backend/` during a containerised run.**
- **A mutation anchor was silently scored INVALID.** Black had collapsed a wrapped call onto one line
  and the anchor was written against the wrapped form, so it matched zero times. Write anchors
  against the **formatted** source.
- **A mutant was written with unbalanced parentheses** and came back INCONCLUSIVE rather than
  surviving. Rewritten, inverting the budget/fallback nesting fails 15 tests. An inconclusive mutant
  is not a passing one — the harness reporting the two separately is what caught it.
- **Four refusal tests matched something weaker than their name**, twice in each item. `ai-008`'s two
  were found by a permissive stub before the implementation existed; `ai-011`'s two by the mutation
  pass. The template-as-arm test asserted only that *something* raised, and `ai-009` refuses a
  budgeted template anyway, so the guard could be deleted and stay green. The spend-ceiling test
  matched the bare word "price", which survives in the message's tail when the sentence naming what
  is missing is deleted. This is now the third and fourth occurrence of the defect `evb-002` first
  recorded.
- **`ai-009`'s arm guard caught my test before my test caught anything.** I scripted the local arm
  returning a result declaring *hosted*; the budget refused it. The test was wrong and the guard was
  right.
- **I nearly introduced a credential bug while "fixing" one.** I was about to add
  `OPENAI_API_KEY: ${OPENAI_API_KEY}` to Compose, which sets the variable to an **empty string** in
  the container — and `load_dotenv(override=False)` treats present-but-empty as present, so it would
  have shadowed a perfectly good `backend/.env`. `app/dal/pseudonymise.py` already records that exact
  trap for the seed. I had also claimed the seed "never reaches the container", which was wrong: the
  app loads `backend/.env` itself, anchored to the package so it resolves through the bind mount.
- **Docker's daemon wedged** after a full suite plus two image builds, killing a measurement mid-run.
  The log was deliberately **not** hand-written from captured stdout: a transcribed log produces
  spurious differences against a re-run and destroys the diff-against-the-log protocol it exists for.
  Recorded as owed, then captured properly after an OrbStack restart — and the second run's figures
  matched the first exactly, so the numbers are confirmed rather than merely restated.
- **`make measure` passes `--no-deps`**, so it does not start the database. After a Docker restart
  the measurement died on `failed to resolve host 'postgis'`, which reads like a defect in the script
  and is not one. `docker compose up -d postgis` first.

## Next step

1. **Run the three-bundle smoke test and read the output.** It is the only outstanding gate, and the
   command is above. Four things to look for: whether temperature and seed were accepted; which
   schema keywords strict mode actually honoured; how the estimated cost compares with the provider's
   own billing page (*only comparable now*, while three calls are the account's whole history); and
   whether the grounding check flagged anything on a real model. **A catch is a finding either way** —
   the safeguard earning its place, or a prompt needing a word changed before twenty bundles run
   through it. Record the result in `docs/thesis_notes.md` under the model-selection section, which
   carries an explicit gap note for it.
2. **The determinism probe** (N = 3, non-scored), load-bearing for two separate things:
   reproducibility, and whether `ai-007`'s retry is a mechanism or a tax.
3. **A campaign runner** — iterate bundles, store through `db-002`, report through `eval-005`.
   Deliberately excluded from `ai-011`, which assembles and does not run.
4. **Revisit the local arm** (`ai-005`/`ai-006`) with the hosted arm's measured reliability in hand.

Open and unowned:

- **The credential-loading remedy now exists in two places.** `app/dal/pseudonymise.py` has the
  seed-specific one and the smoke test carries a copy, with the debt recorded in its docstring. That
  module's own note warns a remedy copied twice is one the third caller will not know about — so
  **generalise it when the campaign runner lands in `app/`**, which needs a spec item rather than a
  measurement script's convenience.
- `ai-008`'s **superseded failure case has no corpus demonstration**: 0 of 41 bundles carry a
  superseded claim, because the ladder suppressed 0 of 188. Proved by unit tests over constructed
  bundles; the corpus demonstration is owed to a second producing rule. The measurement counts them,
  so the figure moves on its own.
- **The near-miss "rule under another finding type" bucket conflates two mistakes** — a genuine type
  confusion and a circular citation, 41 of each in the corpus measurement. Split it into a fourth
  near-miss kind *before* the campaign if that bucket turns out to carry weight, since the
  classification is what gets reported.
- **The other mutation harnesses still lack the crash guard and the sentinel** (~5 lines each).
  `ai-008`'s and `ai-011`'s have both.
- The run budget is **held in memory**, so a process that dies and restarts counts from zero — a
  second, independent reason the console cap exists.
- Regenerate corpus v2 for `eval-001`.
- 13 committed files are not Black-formatted (~900 lines, one commit of its own). None are this
  session's.
- Frontend suite exits non-zero: `control.runs.map is not a function` at `scenarioControl.tsx:344`.
- Broadband generation arm; nine measurement scripts still select runs by means other than `scn-008`'s
  provenance; `CORPUS_V2_PLAN.md` and `DEV_BATCH_PLAN.md` still sit at the repo root.
- `docs/progress_note.html` begins with its own `<!doctype html><html><head>` wrapper, so the
  published page double-wraps. It has rendered correctly for ten versions and is left alone
  deliberately. Worth one small commit of its own.
