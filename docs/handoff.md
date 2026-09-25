# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
it fuses replayed aviation telemetry and synthetic RF observations through a Data Abstraction Layer,
detects deviations deterministically, and turns evidence bundles into schema-validated,
grounding-checked AI hypotheses for an analyst to review. Decision support, never autonomous
decision-making.

This session built **`ai-008`, the automated grounding check** — build-order step 6 of Phase 9, and
the last item before the local arm is revisited. It is the safeguard every claim about the AI layer
rests on: constrained decoding fixes the *shape* of a hosted answer and says nothing about whether
the identifiers inside it exist.

## Current state

**`ai-008` passes.** `app/ai/grounding.py`, 58 tests in `tests/test_ai_grounding.py`, **100% on the
module**, **1400 passed at 99.86%** in the container, ruff and mypy clean. **56 of 99 spec items
passing.**

What it does, and the three decisions that are not obvious from the code:

- **Three verdicts, not two.** A citation is grounded, unknown, or **superseded**. The bundle
  deliberately carries the competing claims `anom-013` rejected, in their own compartment, so a check
  that verified an identifier *exists* would resolve one perfectly and certify a hypothesis citing it
  **as support** — reading two rules' disagreement as two rules' agreement, which is the exact error
  the safeguard exists to catch. Fabrication and misreading are different failures and the rarer one
  is the worse, so they never merge.
- **Matching is exact, near misses are recorded.** Normalising case would silently repair model
  output and understate a catch rate `eval-005` reports as a *result*. Two near-miss kinds are
  recorded without changing the verdict, and the spelling reading is checked **before** the rule-id
  one because both apply at once when a rule carrying several finding types is cited with one of them
  miscapitalised.
- **The arm is declared and 0/0 is `None`.** A `Hypothesis` carries no record of what produced it, so
  the arm is stated where the check is wired in — `ai-009`'s argument for a refused call. A catch
  rate over zero checks is `None` rather than 0.0, because *never caught anything* and *never ran*
  must not read alike.

**Measured, over the 41 stored bundles** (`measurements/corpus/grounding_catch_rate.log`):

| | |
|---|---|
| Flagged on template hypotheses | **0 of 164 citations**, 41 of 41 bundles |
| Template arm catch rate | **0.0 measured**, not `None` |
| Deliberate corruptions caught | **164 of 164**, 41 of 41 on each of four kinds |
| Near misses classified | 123 of 164 — 82 rule-id, 41 spelling, 41 correctly unclassified |
| Bundles carrying a superseded claim | **0 of 41** |

**Mutation: 46 of 46 killed, no survivors, on the first valid pass**
(`measurements/mutation/mutate_ai008_grounding.log`) — the first item to reach that without a second
round. The reason is not that the tests were written better; it is that the gap-finding happened
*before* the implementation existed. See Failed attempts.

Unbuilt and specified: the local arm (`ai-005`/`ai-006`), still deferred with a trigger. The
availability fallback waits on it.

## Files in flight

The tree is clean. Everything below is committed.

Added: `backend/app/ai/grounding.py`, `backend/tests/test_ai_grounding.py`,
`backend/measurements/corpus/grounding_catch_rate.py` (+ `.log`),
`backend/measurements/mutation/mutate_ai008_grounding.py` (+ `.log`).

Modified: `docs/spec.jsonl` (`ai-008` amended, then `passes: true`), `docs/thesis_notes.md`,
`docs/qa.md`, `docs/implementation.md`, `backend/measurements/README.md`, `CLAUDE.md`.

## Changed

| Commit | What |
|---|---|
| `08e4748` | `spec: amend ai-008 — the arm is declared, the oracle must not share the fault` |
| `6805a40` | `test: add tests for ai-008` (58 tests) |
| `26ce6a6` | `test: strengthen two ai-008 tests against a permissive check` |
| `e6d3232` | `feat(ai-008): the automated grounding check - tests pass` |

The spec amendment pinned five things the item did not say: the arm cannot be inferred from a
hypothesis; 0/0 is unmeasured rather than zero; the citation key must be derived independently of the
template that validates it; near misses are reported without changing the verdict; and a real
citation with a false sentence attached is a failure this item **does not** catch.

## Failed attempts

- **The first full-suite figure was wrong, and my own doing.** It reported 99.50% with 18 missed
  statements. I had run Black over `app/ai/grounding.py` and the test file *while the suite was
  running against the bind mount*, so coverage mapped stale line numbers onto a changed file. The
  clean re-run gave **99.86%, 5 missed**. Do not touch `backend/` during a containerised run.
- **A mutation anchor was silently scored INVALID.** Black had collapsed a wrapped call onto one line
  and the anchor was written against the wrapped form, so it matched zero times. This is the
  silent-INVALID failure `measurements/README.md` already records, and it surfaced only because the
  harness reports invalid anchors separately instead of counting them among the killed. Write anchors
  against the **formatted** source, never against what you typed.
- **Two tests were wrong and a permissive stub is what showed it.** Before writing any
  implementation, a throwaway module reporting every citation grounded was run against the suite:
  **24 of 58 passed**. Two were wrong — the statement-is-not-resolved case only asserted that a good
  citation passes, and the evidence-wins case never forced the check to look in the superseded
  compartment at all. Both were strengthened to turn on a differential, re-measured at 36 failed / 22
  passed, and the 22 that pass by nature are named in the file docstring. **This is why the mutation
  pass found nothing**: the same gaps were found earlier and far more cheaply.
- **A third gap was found by writing the mutation harness, not by running it.** `near_misses(arm)`
  pooling every arm's findings would have survived, because the test used one arm. Fixed before the
  pass, so the pass never scored it — recorded here because the score alone would misrepresent how
  the gap was found.
- **The corpus measurement produced a finding the unit tests could not.** A circular citation — the
  bundle's own claim cited as evidence for itself — is classified as `rule_id_under_another_type` on
  every bundle, because the deciding rule genuinely does appear in the evidence under other finding
  types. The verdict is right and only the classification is coarse, but a write-up quoting that
  count as "one rule's findings mistaken for another's" would overstate it.

## Next step

1. **Revisit the local arm** (`ai-005`/`ai-006`) — build-order step 7, and the last item in the Phase
   9 sequence. Deferred 2026-09-21 with a trigger: build `ai-004` first, record how often the hosted
   arm is actually unavailable, then decide. Safe to defer *only* because that arm is not scored.
   Note the trigger has not fired, because no real call has been made yet.
2. **The three non-code gate items before the first real request**, none of which this session
   touched:
   - a **dated model ID** pinned, not a moving alias (a procurement decision);
   - the **hard spend cap at the provider console**, and a real `OPENAI_API_KEY`;
   - the **three-bundle smoke test**, hand-read — which is also what confirms which schema keywords
     strict mode actually accepts.
3. **The determinism probe (N=3, non-scored)**, which is load-bearing for two separate things:
   reproducibility, and whether `ai-007`'s retry is a mechanism or a tax.

Open and unowned:

- `ai-008`'s **superseded failure case has no corpus demonstration** and cannot have one here: 0 of
  41 bundles carry a superseded claim, because `anom-013` suppressed 0 of 188 claims. It is proved by
  unit tests over constructed bundles, and the corpus demonstration is owed to a second producing
  rule alongside the ladder's own arbitration. The measurement counts superseded fields, so the
  figure will move on its own the day one appears.
- **The other mutation harnesses still lack the crash guard and the sentinel** (~5 lines each). The
  `ai-008` harness has both.
- Nothing builds a `GenerationConfig` from the environment; deferred to the first arm that runs.
- The run budget is **held in memory**, so a process that dies and restarts counts from zero — a
  second, independent reason the console cap exists.
- Regenerate corpus v2 for `eval-001`.
- Several committed files are not Black-formatted (13 files, ~900 lines of churn, one commit of its
  own). None of them are `ai-008`'s.
- Frontend suite exits non-zero: `control.runs.map is not a function` at `scenarioControl.tsx:344`.
- Broadband generation arm; nine measurement scripts still select runs by means other than `scn-008`'s
  provenance; `CORPUS_V2_PLAN.md` and `DEV_BATCH_PLAN.md` still sit at the repo root.
- The master `docs/progress_note.html` begins with its own `<!doctype html><html><head>` wrapper, so
  the published page double-wraps. It has rendered correctly for nine versions and is left alone
  deliberately. Worth one small commit of its own.
