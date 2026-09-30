# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational
awareness: it fuses replayed aviation telemetry and synthetic RF observations through a Data
Abstraction Layer, detects deviations deterministically, and turns evidence bundles into
schema-validated, grounding-checked AI hypotheses for analyst review. Decision support, not
autonomous decision-making.

This session built **`eval-002`, the detection metrics** — the results table of the detection
chapter, and the largest remaining gap between the scope document and the build. It was the last
detection item with nothing computed behind it: precision, F1 and detection latency had never been
measured at all.

## Current state

**`eval-002` passes.** Backlog **67 of 104**. Tree clean at `5142060`.

- `backend/app/evaluation/metrics.py` — 237 statements, **100%** line coverage, 50 tests in
  `backend/tests/test_eval_metrics.py`.
- Whole backend suite: **1,394 passed / 288 skipped** locally, 93% overall coverage. ruff and mypy
  clean.
- Mutation pass: **40 of 41 killed**, `measurements/mutation/mutate_eval002_metrics.log`.
- Corpus measurement: **300 runs**, `measurements/corpus/detection_metrics.log`.

### The figures, measured over corpus v2 (all 300 runs)

| Arm | Runs | Decided correctly | Recall per run | Recall per staged aircraft |
|---|---|---|---|---|
| `rf-sensor-fault` | 60 | 60 | 1.000 | — |
| `gnss-degradation` | 60 | 60 | 1.000 | 0.823 |
| `ambiguous-mixed-evidence` | 60 | 60 | 1.000 | **0.587** |
| `normal-baseline` | 60 | silent 60 | — | — |
| `aircraft-coverage-gap` | 60 | silent 60 | — (unjudged) | 0.587 |

Precision 1.000 on both built reportable types (120 of 120 fault claims, 60 of 60 interference).
F1 **1.000** for `possible_interference_zone`; **withheld** for `possible_sensor_fault`, which two
arms produce. `possible_data_source_issue` is a coverage row, not a score — `anom-006` is unbuilt.

False positives: **0 of 60 from nothing** and **0 of 60 cross-modal**, never pooled. Only the first
is control-backed.

Latency, conditional on detection — **the project's first latency figures on real data**:

| Arm | Detections | Median | Min | Max |
|---|---|---|---|---|
| `rf-sensor-fault` | 60 | 10 s | 10 s | 90 s |
| `ambiguous-mixed-evidence` | 60 | 10 s | 10 s | 90 s |
| `gnss-degradation` | 60 | 20 s | 10 s | 90 s |

The 10 s floor is `anom-014`'s minimum episode duration. No negative latency, no undecidable claim.

Confusion matrix diagonal; 0 runs excluded for staging nothing; 0 runs claimed two types.

### The result worth carrying into the write-up

`ambiguous-mixed-evidence` reads **1.000 run-level and 0.587 per-aircraft on the same sixty runs**.
Both correct: the system named the right anomaly on every hour while saying nothing about four in ten
of the aircraft interfered with, because that arm's reportable verdict rests on the radio evidence
and needs no aircraft. It is the strongest available argument for never merging the two recalls.

### The limitation that must not be dropped

Every rate in the table is 1.000 or 0.000. That establishes the layer is **correctly wired**, not
that it detects real interference: the radio side is synthetic with the injected incident well above
threshold by construction, the corpus holds no near-misses, and one of three reportable types has no
rule. The only figure carrying information from outside the generator is the per-aircraft recall, and
that is 0.587 on two arms of three. Recorded in `thesis_notes.md`, `evaluation_harness.md`, `qa.md`
§115 and `measurements/README.md`.

## Files in flight

Tree is clean. Nothing half-finished.

## Changed

| Commit | What |
|---|---|
| `07d4e91` | `spec: amend eval-002 — what the figures are indexed by` |
| `81fbaab` | `test: add tests for eval-002` (44 at that point, red at collection) |
| `1c13210` | `feat(eval-002): detection metrics indexed by what they are about - tests pass` |
| `c65522f` | `measure(eval-002): mutation pass — 40 of 41` |
| `c22418b` | `measure(eval-002): the results table over corpus v2` |
| `5142060` | `docs: eval-002 write-up — qa, thesis notes, harness page, README, repo map` |

New files: `backend/app/evaluation/metrics.py`, `backend/tests/test_eval_metrics.py`,
`backend/measurements/corpus/detection_metrics.py` + `.log`,
`backend/measurements/mutation/mutate_eval002_metrics.py` + `.log`.

Edited: `docs/spec.jsonl` (amended + passing), `docs/qa.md` (§110-115 + 7 glossary rows),
`docs/thesis_notes.md` (8 subsections), `docs/evaluation_harness.md` (results table, two vocabulary
rows, one new limitation), `docs/implementation.md` (Phase 11 item ticked),
`backend/measurements/README.md` (2 new rows + one stale figure corrected), `CLAUDE.md` (repo map).

No new dependencies. No new requirements.

## Failed attempts

- **The spec amendment was asked for on `eval-005` and written on `eval-002`.** The six points are
  entirely `eval-002`'s; `eval-005` already passes and its only role here is the `None`-over-empty
  convention. The user confirmed the slip mid-turn.
- **The track-side guard was written against the wrong rule.** First version refused a per-aircraft
  recall on any arm that was not `POSITIVE`. That is wrong: `anom-011` measures
  `aircraft-coverage-gap`, which is `UNJUDGED`. The correct rule is "an arm that stages nothing",
  which excludes only `normal-baseline`. Caught by the one test that failed on the first green run.
- **The mutation pass reported seven survivors, five of which were real gaps in the tests.** The
  false-negative rate was asserted at a recall of one half, where the figure and its complement are
  the same number and the assertion proves nothing. The confusion row for a run claiming two types
  was never checked. The arms behind an unbuilt type were never asserted empty. The silent-arm rate
  was tested with one claim per run, where per-run and per-claim counting agree. And F1 over a
  precision and recall of both zero was untested — a division by zero, not a score of zero.
- **A sixth survivor was a redundancy in the code, not a gap in the tests.** Two checks held the
  one-arm-per-type rule — one in the F1 property, one where the row is built — and either could be
  removed with no behavioural change, which means neither was being proved. Fixed by making the
  contradiction unconstructible: a type row carrying a single arm's recall while two arms produce it
  now raises. This is the pattern to look for when a mutant survives on a guarded rule.
- **`quiet_run_background`'s row in `measurements/README.md` still quoted n=20 figures** (0 of 20
  quiet runs, bands 9-19 and 5-9) eleven days after the three-wave re-measurement moved them to
  n=60 and 8-22 / 4-10. Its own `.log` was correct. Corrected in place. A figure of record in the
  file whose job is to be the figure of record.
- **`make format` reformatted 12 unrelated files again.** Reverted by hand for the third session
  running. Standing item below.
- **Workflow deviations, recorded rather than hidden:** two tests (`..._stages_nothing_is_refused`,
  `..._still_carries_a_track_side_recall`) and five more closing mutation gaps were written *after*
  the implementation. The five were written in response to the mutation pass, which is its purpose;
  the two came from correcting the guard.

## Next step

1. **`eval-003` — CSV/JSON metrics export.** Now unblocked: `DetectionMetrics.as_json()` exists and
   round-trips, and one test already names `eval-003` as its consumer. The smallest remaining
   evaluation item.
2. **Offer the progress note an update.** `eval-002` changes the story it tells — it is the first
   time the note could carry a results table at all, and the two-recalls figure is the kind of thing
   the note exists for. Not yet done.
3. **`eval-006`** stays deferred until the second rater returns mid-October.

### Open and unowned

- Mutation harnesses for the four other evaluation modules — `pack.py`, `sampling.py`,
  `statistics.py`, `workbook.py` — 104 tests with nothing establishing they are load-bearing.
  `metrics.py` now has one; it found five real gaps, which is the argument.
- Only `mutate_anom009_latency.py`, `mutate_anom008_control.py` and `mutate_eval002_metrics.py`
  check that a mutant parses; the last also checks a mutant is not identical to the original.
- The corpus holds **no near-misses**, which is what caps the detection table at "correctly wired".
  Generating a corpus with incidents near the detection threshold is the obvious next experiment.
- The 0.39 rate-excess singleton (a run with fewer dropouts inside the incident window than outside),
  seen once at n=40 and surviving to n=60 with no second example.
- 12 files not Black-formatted; `make format` touches them on every run.
- Frontend suite exits non-zero (`control.runs.map is not a function`, `scenarioControl.tsx:344`).
- Nothing applies migrations to the application database in the ordinary path.
- Six measurement harnesses lack the guard-file-and-sentinel pattern.
- `ai-011`'s harness has not been re-run since the corpus was regenerated.
- The credential loader is not generalised.
- `ai-008`'s superseded case has no corpus demonstration.
- `docs/phase9_hypothesis_layer.md` §8 still says N=1.
- Rebuilding evidence bundles corpus-wide would renumber the scored population (bundle ids 247-308)
  and stop `draw_scored_sample.py` reproducing its own draw.
