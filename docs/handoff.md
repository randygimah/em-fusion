# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
replayed aviation telemetry and synthetic RF observations go through a Data Abstraction Layer,
deterministic rules detect deviations, and evidence bundles become schema-validated,
grounding-checked AI hypotheses for an analyst to review. It is decision support, not autonomous
decision-making.

This session continued Phase 9, the hypothesis layer. It finished `db-002` (hypothesis persistence),
then took the phase 9 document's own build order forward: **step 2**, the amendments owed before any
model code, and **step 4**, `ai-007`, the correctness fallback. Step 3 (`ai-009`, the run-level call
budget) is deliberately *not* done and is the next item — see Next step.

## Current state

**`ai-007` is built, green, and committed.** `backend/app/ai/fallback.py`, 44 tests in
`backend/tests/test_ai_fallback.py`, **1241 passed at 99.85%** on the backend tier, **100% on
`app/ai/fallback.py` and on `app/ai/service.py`**, ruff and mypy clean across 60 source files,
**mutation 32 of 32 with no survivors** after a first pass killed 29.

**`docs/spec.jsonl` is 53 of 99 passing.** The published progress note was updated and republished
for `db-002` and `ai-007` together (new section, all three headline figures, the progress table, four
stale bullets in *what it does not do yet*, and both *what happens next* tiers that had gone out of
date). No standing URL is tracked, by policy — publish `docs/progress_note.html` again when it is
wanted.

What the item is, in one line: a decorator over `ai-003`'s port that retries a model arm a **fixed**
number of times on a refusal and then produces `ai-002`'s mechanical explanation instead, with a
record of why.

Three things about it that are load-bearing and were decided this session:

- **The ceiling is a required argument with no default.** A retry count is a spending decision, and
  one made by omission is one nobody chose — the rule `GenerationConfig.model_id` already follows.
- **The recommended value (2) is chosen, not measured**, and it is the only figure in the package
  without a corpus behind it. A retry sends the *identical* request and the gate pins temperature 0
  with a fixed seed, so on a deterministic provider a retry is a second payment for the same refusal.
  The §8 determinism probe settles it; the arithmetic that makes 2 safe in the interim is asymmetric,
  not confident (~20 extra calls against a 200-call budget, against understating the model arm in a
  comparison that cannot be re-run).
- **It catches `GenerationRefused` and is blind to `ProviderUnavailable`.** That is `ai-006`'s, and
  merging the two fallbacks is the failure the phase document names as likeliest. The suite proves
  the blindness by scripting the answer a wrongly-retried arm would give, so widening the `except`
  to the shared parent returns a hypothesis where the test demands a raise.

**Amendments landed (build-order step 2):**

- `ai-007` — §10 defect 4 (the two triggers are not of equal standing), plus two defects found while
  planning: the determinism/retry contradiction above, and the fact that the two refusal categories
  leave records of **different strength** (an ungrounded hypothesis is a stored row with grounding
  FAILED; a malformed response leaves **no row at all**, only a log line and a counted call).
- Phase 8.5 gate, *N generations* — settled. N=1 scored at temperature 0, plus a separate
  non-scored N=3 determinism probe. The item had asked for one decision where there were two.
- Phase 8.5 gate + `eval-004`, *scoring corpus* — stratified on **bundle kind** (10 interference,
  10 fault), not scenario type. Five scenario types produce two kinds of bundle, so "five per
  anomalous type" needed bundles from a type that produces none.

**One small additive change to `ai-003`:** `GenerationRefused` now carries an optional `ModelCall`.
A malformed answer never becomes a `GenerationResult`, so nothing else holds the tokens it consumed,
and `ai-009`'s budget is about a retry loop — only visible if the calls that *failed* are counted.
`ProviderUnavailable` deliberately has no such field: nothing was served.

**Measurements from this session:** the full tier ran in **4m22s**, against 41 minutes last session
when the Docker daemon was wedged. Nothing was changed to achieve that; it is the daemon's state,
not a result.

## Files in flight

**The tree is clean.** `ai-007` is finished and committed, write-ups included.

One thing worth knowing before the next mutation pass: it is slow — **about 2.5 minutes per
mutant**, because each source edit invalidates the Docker image's `COPY app/` layer and forces a
rebuild before the tests run. 32 mutants is about 80 minutes, and running it twice (once to find
gaps, once to record the figure) is most of an afternoon. Worth backgrounding from the start.

## Changed

Commits this session, in order:

- `7fad3e4` `spec: amend ai-007, eval-004 and the two Phase 8.5 gate items`
- `2e0355c` `test: add tests for ai-007`
- `bba43f5` `test: strengthen six ai-007 tests that passed against a stub`

Earlier in the session (before the compaction boundary): `db-002` through `14e342c`.

New files: `backend/app/ai/fallback.py`, `backend/tests/test_ai_fallback.py`,
`backend/measurements/mutation/mutate_ai007_fallback.py`. No new dependencies.

## Failed attempts

- **The first red proof was worthless.** Running the new tests with no module produced a single
  collection error, not 42 failures — which proves the import is missing and nothing else. Redone
  properly against a deliberately naive stub, following what `ai-002` taught. **Thirteen of 42
  passed.** Two were wrong tests: one asserted the ordinary path and could not tell "checked and
  passed" from "never checked", because it never asserted the check had *run*; the other claimed to
  prove that a `None` check means no check, on a stub that ran no check under any setting. Four more
  passed trivially because they assert a *negative* — an implementation catching nothing satisfies
  "does not catch `ProviderUnavailable`" for free. Those were sharpened against the realistic defect
  rather than rewritten. Eleven now pass by nature and the test module's docstring names them.
- **A mutation anchor was written with the wrong indentation** (32 spaces where the file has 28) and
  would have been silently scored `INVALID`. Caught by validating every anchor matches exactly once
  *before* running the pass, which took seconds and is worth doing every time.
- **The mutation pass found three tests that were not testing what their names said**, and one was
  hiding a defect rather than merely being weak. Nothing had ever made the injected grounding check
  raise anything but a refusal — so a crash *inside `ai-008`* would have been caught by this layer
  and recorded as the model being ungrounded, inflating a **reported evaluation result** with the
  checker's own fault. The behaviour was already correct; nothing proved it, which means nothing
  would have noticed it changing. The other two: a log test satisfied by the *fallback summary*
  line, which names the same category and the same reason as the per-refusal line it was meant to
  check, and a tuple coercion no call site exercised because every internal caller already passes a
  tuple. 4 tests added, 2 rewritten, 0 implementation changes.
- **`make format` was not run**, again. It reformats ~900 lines across nine files from earlier
  items, which would bury this item's diff. Still owed as a commit of its own. One import-ordering
  error from ruff was fixed by hand instead.

## Next step

1. **`ai-009`** — the run-level call budget, build-order step 3. It was skipped to get here and is
   owed *before the first real call*, not after the first surprise. `ai-007` already gives it its
   hook: `generate_recorded` returns every refusal, and each one exposes the call it paid for
   through a single property, so the budget counts failed calls without knowing how they failed.
2. **`ai-004`**, the hosted arm — **prompt first and reviewed**, then the adapter, with tests that
   mock the provider and never make a real call. Two gate items are still open and both block it:
   the dated model ID, and the API key in an environment variable with a `.env.example` entry.
3. **`ai-008`**, the grounding check. Cheap to validate, because the template generator is an input
   whose correct answer is known in advance: anything flagged on a template hypothesis is a defect
   in the check. It plugs into `ai-007` as the injected `GroundingCheck` with no change to either.
4. **Revisit the local arm** with the hosted arm's measured reliability in hand.

Open and unowned:

- The **determinism probe** is now load-bearing for two separate things — reproducibility, and
  whether `ai-007`'s retry is a mechanism or a tax. Run it with `ai-004`.
- Regenerate corpus v2 for `eval-001`.
- Nothing builds a `GenerationConfig` from the environment; deferred to the first arm needing a
  credential, which is `ai-004`.
- Several committed files are not Black-formatted (~900 lines of churn, one commit of its own).
- Frontend suite exits non-zero: `control.runs.map is not a function` at `scenarioControl.tsx:344`.
- Broadband generation arm; nine measurement scripts still select runs by means other than
  `scn-008`'s provenance; `CORPUS_V2_PLAN.md` and `DEV_BATCH_PLAN.md` still sit at the repo root.
- The master `docs/progress_note.html` begins with its own `<!doctype html><html><head>` wrapper,
  left over from a read-back in an earlier session; the publish tool adds another, so the page
  double-wraps. It has rendered correctly for five versions, so it was left alone rather than
  touched mid-task. Worth one small commit of its own.
