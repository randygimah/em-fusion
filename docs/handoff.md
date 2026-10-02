# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational
awareness: it fuses replayed aviation telemetry and synthetic RF observations through a Data
Abstraction Layer, detects deviations deterministically, and turns evidence bundles into
schema-validated, grounding-checked AI hypotheses for analyst review. Decision support, not
autonomous decision-making.

One item this session, and it is the last piece of the question that reframed the roadmap two
sessions ago — *does detector output on injected anomalies show in the app at all?*

**`anom-016`, the detection pass fires when a generation batch completes.** `anom-015` built the
pass and `api-012` built the screen that renders it, and nothing called the pass. So every run in
the store honestly reported itself unexamined, and finishing a batch from the screen changed
nothing. This is the trigger.

Its real cost was not the trigger. **The detector settings every figure of record was measured
under lived only in a measurement script**, plus a copy in the test suite — so a trigger inside the
application would have had to declare a third set with the same standing as the other two.

## Current state

Backlog **73 of 107** (`anom-016` is new). Tree clean except `docs/` and the mutation log at the
time of writing.

- Backend: **1874 passed, 99.92% total coverage, exit 0**, in containers (1830 and 99.83% before).
- `app/detection/settings.py` (15 statements) and `app/scenario/batch.py` (68) both at **100%**.
  Total missed statements across the package went 9 → 4, and the five that disappeared are exactly
  the ones `batch.py` had.
- `make lint`, `make format` and mypy clean (79 source files, was 78).
- Frontend untouched: the payload shape did not change, only whether a stamp exists.
- Mutation: **28 of 29 valid killed, no unexpected survivors**, one proven equivalent declared
  in advance (`measurements/mutation/mutate_anom016_batch_trigger.log`). **0 test changes, 0
  implementation changes** — the first pass here to need neither, which is attributable to the
  two corrections the red run had already forced out. Its first attempt aborted on its own
  sentinel: see Failed attempts.

### What the item actually does

| | |
|---|---|
| Where scoring lives | `run_batch_now`, after `run_batch` returns. `app/pipeline.py`'s `main()` calls `run_batch` directly, so `make generate` is unscored **by construction** |
| Which runs | only this batch's completed runs, from `BatchSummary.runs` — never the store |
| Baseline | one per batch, over the store's completed `normal-baseline` runs |
| Settings | `POLICIES_OF_RECORD`, from the new `app/detection/settings.py` |
| On failure | per-run recorded and skipped; whole-batch refusal reported separately; nothing raises out |
| Cost | 11.2 s baseline + 1.22 s a run ≈ 35 s on a twenty-run batch |

### The three things worth knowing

**Eleven numbers were homeless, not thirteen.** The explanation given before the item was written
said "thirteen detector settings". Thirteen is a figure about what the *export* records. Four of the
six policy objects — the sensor-fault rule, the fusion rule, the precedence ladder and the
clustering rule — are taken at their defaults, and defaults have always lived in the package. What
existed nowhere in `app/` is `ThresholdPolicy`'s five required fields, `GapPolicy`'s two, and the
corpus box's four coordinates. The box was present only as a CLI `metavar`. That makes the finding
sharper: most of the record *was* in the right place, which is most of why nobody noticed the rest
was not.

**One definition plus one pin, which are different things.** Moving the values removes the copies
and leaves a change to them silent. So the eleven are also written out verbatim in a test — not a
fourth copy: a definition is what something runs under, a pin is an assertion about it. Elsewhere a
digest does this (`ai-004`'s prompt, `eval-003`'s provenance record); here a digest is unavailable
because the values themselves are what is pinned. A second test pins the other half — that four of
the six policies equal their own defaults — so a policy growing a required field makes the eleven
twelve visibly.

**Two paths that differ, asserted in both directions.** `python -m app.pipeline` built the 300 hours
behind every figure and must not score them, or the hours and the settings are welded together and
the same hours can never be re-read under another threshold. The guard walks the import graph —
and "the corpus command reaches no detector" is satisfied by a project with no detection at all, so
the positive direction is asserted beside it.

## Files in flight

- `docs/handoff.md` (this file), `docs/thesis_notes.md`, `docs/detection_layer.md`,
  `docs/implementation.md`, `CLAUDE.md`, `backend/measurements/README.md` — the write-up commit.
- `backend/measurements/mutation/mutate_anom016_batch_trigger.py` + `.log` — untracked until the
  pass finishes.

## Changed

Commits, oldest first:

| Commit | Message |
|---|---|
| `2a39f0e` | `spec: add anom-016` |
| `d552cf7` | `docs: qa entry 143 — why the batch trigger needs the settings moved first` |
| `2a0f69c` | `test: add tests for anom-016` |
| `8c2dd58` | `feat(anom-016): the detection pass fires when a batch completes - tests pass` |

**New files**

- `backend/app/detection/settings.py` — the eleven values, with the box here rather than in
  `app/corpus/` because what reads it is a detector.
- `backend/tests/test_anom_batch_trigger.py` — 42 cases.
- `backend/measurements/mutation/mutate_anom016_batch_trigger.py` + `.log`.

**Changed, backend**

- `app/detection/chain.py` — `measure_normality`. Takes the metric from the policy the deviation
  will be read against, and refuses an empty run list with its own message.
- `app/db/repository.py` — `quiet_run_ids` (completed `normal-baseline` runs, ordered, empty rather
  than raising) and `run_summary` (one run as its row holds it, None when absent).
- `app/scenario/batch.py` — `BatchScoring`, `score_batch`, the call in `run_batch_now`, and the
  request schema moved behind `TYPE_CHECKING`.
- `measurements/corpus/detection_metrics.py` — imports the record and builds its baseline through
  `measure_normality`; its own observation reader is now dead and removed.
- `tests/test_anom_chain.py` — `POLICIES` is the record, and the threshold-moved test uses
  `dataclasses.replace` rather than restating four of the record's values.
- `tests/test_api_scenario.py` — the two launcher fakes return an empty `BatchSummary`.

## Failed attempts

**A refusal whose message was about the wrong thing.** `measure_normality` was written with no
refusal for an empty run list, on the reasoning that two already exist upstream —
`compute_rf_baselines` will not take an empty allowlist, `Normality` will not hold an empty
provenance. The test for the fresh-database case failed, and the reason is the finding: the refusal
that actually fires first is the baseline's, and it talks about an *allowlist an engine cannot
widen*, while the fact a caller needs is that **this store holds no quiet runs at all**. Since the
refusal reaches a log line and nothing else, the wording is the entire diagnostic. Three refusals
for one condition, each a different statement.

**I claimed thirteen settings were homeless and it is eleven.** Thirteen is `eval-003`'s export
floor count. Four of the six policy objects were already at their defaults inside `app/`. Corrected
before the spec item was written, and the spec says eleven.

**I asserted a batch takes ~105 s and could not source it.** The only figure on record is
`api-006`'s "roughly seventy seconds". The spec item now says that and says whose figure it is. The
105 came from somewhere in a previous session and survives nowhere.

**An import cycle that had never fired.** `app/scenario/batch.py` imports a request schema from
`app.api.v1.schemas.scenario`; importing anything under `app.api.v1` runs that package's
`__init__`, which imports the route module, which imports `app/scenario/batch.py`. The cycle has
existed since that module was written and never fired, because every path into it went through the
API package first. A test that imports the domain module directly is what surfaced it. Fixed by
moving the import behind `TYPE_CHECKING`, which it qualifies for — it is only ever an annotation.

**Two launcher tests broke, and the first instinct was wrong.** Both patched `run_batch` with a fake
returning `None`, which was faithful while the launcher ignored the return value. The tempting fix
was to stub `score_batch` out; that would have left those tests passing over a launcher whose new
half had been removed. The fakes now return what the real function returns — an empty
`BatchSummary`, which the scoring stage treats as nothing to examine.

**The mutation pass aborted on its own sentinel.** The sentinel set the radio threshold to 99 dB to
prove that source edits reach the tests. `ThresholdPolicy` refuses bands that do not increase past
the threshold, so the module raised on import, the suite reported `3 errors in 1.28s`, and the
harness refused to read that as a kill — correctly: a mutant killed by an import error is the
runtime twin of one that does not parse and says nothing about the tests. Two value mutants had the
same defect (swapping the two severity steps breaks the same rule) and were replaced with
single-step moves. Recorded as the eighth hazard in `measurements/README.md`, with the rule that a
mutation table over a *configuration* module is also a table of things that must stay
constructible — check by constructing each one first.

**And then I re-ran it from the wrong directory.** `cd backend` from a session already in `backend`,
so the pass never started and the stale log made it look like the same failure twice.

**`make test-backend` spent ten minutes rebuilding before running anything.** Not a defect, but the
first run looked hung. `test-backend-nobuild` exists for exactly this and is what the mutation pass
uses.

## Next step

1. **Re-score the corpus.** The 300 stored runs have findings and **no stamp**, so every one still
   reads as unexamined — correct, and still the reason the screen shows nothing for them. `anom-016`
   covers new batches only; the existing corpus needs one pass by hand, ~6 minutes at 1.22 s a run.
   Deliberately not behaviour: a command you run once.
2. **Re-run the figures of record.** `detection_metrics.py` now imports the settings and builds its
   baseline through `measure_normality`. The values are unchanged and the equivalence is asserted at
   unit scale, but `anom-015` validated its own refactor by reproducing the figures byte for byte
   and that has not been done for this one.
3. **`op-003` and `op-006`**, the two panels `api-012` unblocked and that now have something to
   show. The summary panel is deliberately minimal and the timeline strip is not rendered at all.
4. **`hypotheses`**, the last producer-less field. 155 rows exist. Which arm an analyst sees,
   whether a row whose grounding check FAILED may be shown, and what `NOT_CHECKED` renders as.
5. **`eval-006`** still waits on a second rater, mid-October.

Open and unowned:

- The progress note has not been updated for `anom-016`. Its pipeline spine now has a trigger and
  its "what it deliberately does not do yet" section should lose the entry saying nothing fires the
  pass. Offer before the next item.
- **`docs/thesis_notes.md` is misfiled from about line 6785 onwards.** Everything after `##
  Evaluation` is appended there regardless of chapter, so implementation findings — the allowlist
  that named a module, the concurrent suites, and now all seven `anom-016` entries — sit under
  Evaluation. Not corrected mid-item; worth one pass before write-up.
- A `normal-baseline` batch is scored against a baseline that includes its own runs, because the
  baseline is a property of the store and not of the batch. Same self-reference `anom-008`'s bands
  carry. Recorded rather than prevented; excluding the batch would mean a store holding one batch
  could not be scored at all.
- Nothing mechanical stops a **third** file declaring its own eleven values. The guard catches the
  regrowth of the two copies that existed, by parsing them; the pin catches a change to the values.
  A new file is caught by neither.
