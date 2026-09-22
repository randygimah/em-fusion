# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
replayed aviation telemetry and synthetic RF observations go through a Data Abstraction Layer,
deterministic rules detect deviations, and evidence bundles become schema-validated,
grounding-checked AI hypotheses for an analyst to review. It is decision support, not autonomous
decision-making.

This session continued Phase 9, the hypothesis layer, and took the phase 9 document's own build
order forward: **step 2** (the amendments owed before any model code), **step 4** (`ai-007`, the
correctness fallback) and **step 3** (`ai-009`, the run-level call budget). Everything that had to
exist *before the first real model request* now does, in code. What remains before that request is
not code — see Next step.

## Current state

**`ai-007` and `ai-009` are both built, green and committed.** `docs/spec.jsonl` is **54 of 99**.

| | `ai-007` | `ai-009` |
|---|---|---|
| Module | `backend/app/ai/fallback.py` | `backend/app/ai/budget.py` |
| Tests | 44 | 46 |
| Coverage | 100% | 100% |
| Mutation | **32 of 32, no survivors** (first pass 29) | **30 of 33**, all three survivors proven equivalent (first pass 28) |

Backend tier: **1287 passed at 99.85%**, ruff and mypy clean across 61 source files.

**`ai-007` — the correctness fallback.** A decorator over `ai-003`'s port that retries a model arm a
fixed number of times on a refusal, then produces `ai-002`'s mechanical explanation, with a record of
why. Three things about it are load-bearing:

- The ceiling is a **required argument with no default** — a retry count is a spending decision, and
  one made by omission is one nobody chose.
- Its recommended value (2) is **chosen, not measured**, and labelled so in the code. A retry sends
  the *identical* request and `ai-004` pins temperature 0 with a fixed seed, so on a deterministic
  provider it is a second payment for the same refusal. §8's non-scored N=3 determinism probe settles
  it and is already in the plan for an unrelated reason.
- It catches `GenerationRefused` and is **blind to `ProviderUnavailable`**, which is `ai-006`'s. The
  suite proves the blindness by scripting the answer a wrongly-retried arm would give.

**`ai-009` — the run-level call budget.** One `CallBudget` per run holding the limits and the ledger,
with a thin per-arm wrapper sharing it. Also three:

- **The call ceiling is the guard; the spend ceiling is a tripwire.** A call count is checkable
  *before* the call and a cost is not, and `Usage.cost_usd` is `float | None` on purpose, so a spend
  ceiling on the local arm enforces nothing while looking configured.
- **`BudgetExceeded` is outside the `GenerationError` tree**, for `ConfigurationError`'s reason —
  the second exception carved out on that argument. Proved by a composition test through a real
  `CorrectnessFallback`, not a subclass check.
- **It wraps the arm and the fallback wraps it.** Outside, it would count one call per bundle and
  miss every retry, which is the only failure mode the item names.

**Amendments landed:** `ai-007` (§10 defect 4 plus the determinism contradiction and the
record-strength asymmetry), `ai-009` (the "calls **or** spend" defect, how the run aborts, and where
the budget sits), `eval-004` and both Phase 8.5 gate items (N=1 scored plus a separate N=3
determinism probe; the scoring corpus stratified on **bundle kind**, since five scenario types
produce two kinds of bundle).

**Small additive change to `ai-003`:** `GenerationRefused` carries an optional `ModelCall`. A
malformed answer never becomes a `GenerationResult`, so nothing else holds the tokens it consumed —
and those are the calls a retry loop is made of.

**The progress note was updated and republished twice**, for `db-002`/`ai-007` and for `ai-009`. No
standing URL is tracked, by policy: publish `docs/progress_note.html` again when it is wanted.

## Files in flight

**The tree is clean.** Both items are finished and committed, write-ups included.

Two things to know before the next mutation pass. It is slow — **about 2.5 minutes per mutant**,
because each source edit invalidates the Docker image's `COPY app/` layer and forces a rebuild before
the tests run; 33 mutants is about 80 minutes, and running it twice (once to find gaps, once to
record the figure) is most of an afternoon. Background it from the start. And **validate every anchor
matches exactly once before running** — it takes seconds and a mis-indented anchor is otherwise
silently scored `INVALID` after an hour of waiting.

## Changed

Commits this session, in order:

- `7fad3e4` `spec: amend ai-007, eval-004 and the two Phase 8.5 gate items`
- `2e0355c` `test: add tests for ai-007`
- `bba43f5` `test: strengthen six ai-007 tests that passed against a stub`
- `b6a19e3` `feat(ai-007): correctness fallback, model arm to template - tests pass`
- `8c72ac0` `spec: amend ai-009 — the call budget is the guard, spend is a tripwire`
- `96630b9` `test: add tests for ai-009`
- `250bd54` `test: strengthen two ai-009 tests that passed against a stub`

New files: `backend/app/ai/fallback.py`, `backend/app/ai/budget.py`, their two test modules, and
`measurements/mutation/mutate_ai007_fallback.py` and `mutate_ai009_budget.py` with their logs. No new
dependencies.

## Failed attempts

- **`ai-009`'s implementation made exactly the error its own spec amendment had just corrected.** The
  amendment says the call ceiling and the spend ceiling are different instruments — one checkable
  before a call, one only after. The first draft then shared a single private `_enforce()` between the
  pre-flight check and the post-record check, because it looked like removing a duplication. That
  evaluated the call ceiling *after* recording, so a ceiling of N aborted on the call that **filled**
  the budget and only N−1 ever returned. Seven tests caught it in a minute. The lesson is not the
  off-by-one: **a distinction argued in prose does not survive a tidy-up unless something structural
  resists it.**
- **The first red proof for each item was worthless** — one collection error, which proves the import
  is missing and nothing else. Redone against a deliberately naive stub both times. `ai-007`: 13 of 42
  passed, of which 2 were wrong tests and 4 passed trivially because they assert a *negative*.
  `ai-009`: 14 of 45, of which 2 were wrong tests. All six rewritten or sharpened; the pass-by-nature
  ones are named in each test module's docstring.
- **A mutation survivor hid a defect rather than a weak test.** Nothing had ever made `ai-007`'s
  injected grounding check raise anything but a refusal, so a crash *inside `ai-008`* would have been
  caught and recorded as the model being ungrounded — inflating a **reported evaluation result** with
  the checker's own fault. The behaviour was already correct; nothing proved it.
- **A test that could not be repaired by choosing better values.** `ai-009`'s abort message names both
  the spend and the ceiling, and the assertion looked for the ceiling's *value* — which the call count
  also supplied. The usual fix is unavailable: the ceiling fires exactly when the count reaches it, so
  the two are equal at the only moment the message exists. The assertion had to move to the message's
  structure.
- **A mutation anchor was written with the wrong indentation** (32 spaces where the file has 28) and
  would have been silently scored `INVALID` after an hour. Caught by validating anchors first.
- **`make format` was not run**, again. It reformats ~900 lines across nine files from earlier items,
  which would bury these diffs. Still owed as a commit of its own. Long lines from ruff were fixed by
  hand instead.

## Next step

1. **`ai-004`, the hosted arm** — build-order step 5, and the first thing that spends money. **The
   prompt is written and reviewed first**, then the adapter, with tests that mock the provider and
   never make a real call. Two gate items block it and neither is code:
   - **A dated model ID**, pinned, not a moving alias. An alias changing mid-campaign invalidates the
     comparison with no visible failure.
   - **The hard spend cap set at the provider console**, and an API key in an environment variable
     with a `backend/.env.example` entry. The console cap is the guard that works when the code is the
     broken thing, and the in-code budget explicitly does not replace it.
2. **`ai-008`, the grounding check.** Unusually cheap to validate: the template generator is an input
   whose correct answer is known in advance, so anything flagged on a template hypothesis is a defect
   in the check. It plugs into `ai-007` as the injected `GroundingCheck` with no change to either.
3. **Revisit the local arm** (`ai-005`/`ai-006`) with the hosted arm's measured reliability in hand.

Open and unowned:

- The **determinism probe** is now load-bearing for two separate things — reproducibility, and
  whether `ai-007`'s retry is a mechanism or a tax. Run it with `ai-004`.
- Nothing builds a `GenerationConfig` from the environment; deferred to `ai-004`, the first arm
  needing a credential.
- The run budget is **held in memory**, so a process that dies and restarts counts from zero. That is
  a second reason the console cap exists rather than a belt-and-braces one, and it is recorded on the
  progress note as a limitation.
- Regenerate corpus v2 for `eval-001`.
- Several committed files are not Black-formatted (~900 lines of churn, one commit of its own).
- Frontend suite exits non-zero: `control.runs.map is not a function` at `scenarioControl.tsx:344`.
- Broadband generation arm; nine measurement scripts still select runs by means other than `scn-008`'s
  provenance; `CORPUS_V2_PLAN.md` and `DEV_BATCH_PLAN.md` still sit at the repo root.
- The master `docs/progress_note.html` begins with its own `<!doctype html><html><head>` wrapper, left
  over from a read-back in an earlier session; the publish tool adds another, so the page
  double-wraps. It has rendered correctly for seven versions, so it was left alone rather than touched
  mid-task. Worth one small commit of its own.
