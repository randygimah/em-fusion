# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational
awareness: it fuses replayed aviation telemetry and synthetic RF observations through a Data
Abstraction Layer, detects deviations deterministically, and turns evidence bundles into
schema-validated, grounding-checked AI hypotheses for analyst review. Decision support, not
autonomous decision-making.

This session built **`eval-002`, the detection metrics**, and then **`eval-003`, the metrics
export** — the results table for the detection chapter, and the files a thesis row can be traced
back through. Between them they closed the last two evaluation items that need no second person.

## Current state

Backlog **68 of 104**. Tree clean at `6e9aafc`.

- `backend/app/evaluation/metrics.py` — 237 statements, **100%**, 50 tests.
- `backend/app/evaluation/export.py` — 190 statements, **100%**, 40 tests.
- Backend suite: **1,434 passed / 288 skipped** locally; **1,682 at 99.89%** in containers.
  ruff and mypy clean.
- Mutation: **40 of 41** (`mutate_eval002_metrics.log`), **39 of 39**
  (`mutate_eval003_export.log`).
- Corpus measurement: 300 runs, `measurements/corpus/detection_metrics.log`, exporting to
  `measurements/exports/`.

### The detection results, over all 300 runs of corpus v2

| Arm | Runs | Right | Recall per run | Recall per staged aircraft |
|---|---|---|---|---|
| `rf-sensor-fault` | 60 | 60 | 1.000 | — |
| `gnss-degradation` | 60 | 60 | 1.000 | 0.823 |
| `ambiguous-mixed-evidence` | 60 | 60 | 1.000 | **0.587** |
| `normal-baseline` | 60 | silent 60 | — | — |
| `aircraft-coverage-gap` | 60 | silent 60 | — (unjudged) | 0.587 |

Precision 1.000 on both built reportable types. F1 **1.000** for `possible_interference_zone`;
**withheld** for `possible_sensor_fault`, which two arms produce. Both false-positive rates 0 of 60,
never pooled, only the quiet one control-backed. Confusion matrix diagonal. 0 runs excluded.

Latency, conditional on detection — the project's first on real data: median **10 s** on both fault
arms, **20 s** on interference, min 10 s, max 90 s, over 60 detections each. The floor is
`anom-014`'s minimum episode duration. No negative latency, no undecidable claim.

`ambiguous-mixed-evidence` reads **1.000 run-level and 0.587 per-aircraft on the same sixty runs** —
the strongest argument in the project for never merging the two recalls.

### The exported files

`backend/measurements/exports/`, every row stamped `c421c41506fd`, which resolves in
`provenance.csv` to corpus v2, three base seeds in wave order, 300 runs, thirteen detector settings
and the measurement date. `metrics.json`, `provenance.csv`, `detection_arms.csv`,
`detection_types.csv`, `detection_false_positives.csv`, `detection_confusion.csv`. The campaign half
is wired and waits on the per-arm figures being run end to end.

### The limitation that must not be dropped

Every rate in the detection table is 1.000 or 0.000. That establishes the layer is **correctly
wired**, not that it detects real interference: the radio side is synthetic with the injected
incident well above threshold by construction, the corpus holds no near-misses, and one of three
reportable types has no rule. The only figure carrying information from outside the generator is the
per-aircraft recall, and that is 0.587 on two arms of three. Recorded in `thesis_notes.md`,
`evaluation_harness.md`, `qa.md` §115, `measurements/README.md` and the progress note.

## Files in flight

Tree is clean. Nothing half-finished.

## Changed

| Commit | What |
|---|---|
| `07d4e91` | `spec: amend eval-002 — what the figures are indexed by` |
| `715ba4a` | `test: add tests for eval-002` |
| `1c13210` | `feat(eval-002): detection metrics indexed by what they are about - tests pass` |
| `c65522f` | `measure(eval-002): mutation pass — 40 of 41` |
| `c22418b` | `measure(eval-002): the results table over corpus v2` |
| `5142060` | `docs: eval-002 write-up` |
| `95c31fc` | `docs: handoff for the eval-002 session` |
| `cfd8c06` | `docs: progress note — the detection results section` |
| `5a88adf` | `spec: amend eval-003 — what self-describing has to mean to be checkable` |
| `b4b7e74` | `test: add tests for eval-003` |
| `24f9f91` | `feat(eval-003): metrics exported so a thesis row can be traced back - tests pass` |
| `4f5d4f6` | `measure(eval-003): mutation pass 39 of 39, and the exported files` |
| `6e9aafc` | `docs: eval-003 write-up` |

New files: `app/evaluation/metrics.py`, `app/evaluation/export.py`, `tests/test_eval_metrics.py`,
`tests/test_eval_export.py`, `measurements/corpus/detection_metrics.py` + `.log`,
`measurements/mutation/mutate_eval002_metrics.py` + `.log`,
`measurements/mutation/mutate_eval003_export.py` + `.log`, `measurements/exports/` (6 files).

Edited: `docs/spec.jsonl` (both items amended and passing), `docs/qa.md` (§110-120 + 12 glossary
rows), `docs/thesis_notes.md` (14 subsections), `docs/evaluation_harness.md`,
`docs/implementation.md` (two Phase 11 items ticked), `docs/progress_note.html` (new results
section, published v19), `backend/measurements/README.md`, `CLAUDE.md`.

No new dependencies. No new requirements.

## Failed attempts

- **The `eval-003` spec amendment was asked for on `eval-005`.** The user corrected it mid-turn; the
  six points were `eval-002`'s throughout.
- **`eval-002`'s track-side guard was written against the wrong rule.** First version refused a
  per-aircraft recall on any arm that was not `POSITIVE`. Wrong: `anom-011` measures
  `aircraft-coverage-gap`, which is `UNJUDGED`. The correct rule is "an arm that stages nothing".
- **`eval-002`'s mutation pass reported seven survivors; five were real gaps in the tests.** The
  worst: the false-negative rate was asserted at a recall of one half, where a figure and its
  complement are the same number, so the test could not fail. A sixth was a **redundancy in the
  code** — two checks held the one-arm-per-type rule and either could be removed with no
  behavioural change, meaning neither was proved. Fixed by making the contradiction unconstructible.
- **`eval-003`'s mutation pass reported four survivors, all real.** The declared count-columns were
  never checked against what each rate is taken over; the declaration *set* was never checked for
  completeness; **no fixture value had more than three decimal places**, so a rounding mutant was
  invisible; and the row for a type two arms produce was never asserted to carry neither arm's
  counts.
- **Two later `eval-003` survivors were one dead defence.** A missing-key fallback had been made
  unreachable by the record alignment, so two mutants of it changed nothing. Removed rather than
  marked equivalent: a record missing a column now raises. **Second time this session that a
  survivor on a guarded rule meant the guard was redundant rather than the test missing.**
- **A defect no unit test could catch, found by opening the exported CSV.** A nested record absent
  on one row and present on another flattened two ways, adding an always-blank column that on the
  rows where the record really was absent read as a missing *value* rather than a missing *record*.
  The first fix — drop any column name that prefixes another — was wrong within a minute: it also
  dropped `f1`, because `f1_is_defined` sits beside it, and those are siblings. A rule over names
  cannot tell the two apart.
- **`quiet_run_background`'s row in `measurements/README.md` still quoted n=20 figures** eleven days
  after the three-wave re-measurement moved them. Its own `.log` was correct. Corrected in place.
- **The progress note was two items behind and quoted a stale test count**, a stale quiet-hour count
  (twenty, not sixty) and a "what happens next" entry describing the results table as pending. All
  corrected; container suite re-run to get the real figure rather than extrapolating it.
- **`make format` reformatted 12 unrelated files again.** Worked around by running `black` on the
  two files in hand rather than the whole tree. Standing item below.
- **Workflow deviations, recorded rather than hidden:** in both items, tests were added *after* the
  implementation in response to the mutation pass — which is its purpose — and two `eval-002` tests
  came from correcting the track-side guard. Three `eval-003` test expectations were also corrected
  after first green, where the flattening rule turned out more correct than what the test assumed.

## Next step

1. **The campaign half of the export.** `export.py` takes it and is tested against it; what is
   missing is running `eval-005`'s per-arm figures end to end over the stored campaign, which needs
   the hypotheses read back from the database. That produces `campaign_arms.csv` and is the last
   thing the export is waiting on.
2. **`eval-006`** stays deferred until the second rater returns mid-October.
3. **A corpus with near-misses** is what would turn the detection table from a consistency result
   into an accuracy one. Out of scope for the dissertation, named as such in four places.

### Open and unowned

- Mutation harnesses for the four other evaluation modules — `pack.py`, `sampling.py`,
  `statistics.py`, `workbook.py` — 104 tests with nothing establishing they are load-bearing. The
  two written this session found nine real gaps between them, which is the argument.
- Only `mutate_anom009_latency.py`, `mutate_anom008_control.py`, `mutate_eval002_metrics.py` and
  `mutate_eval003_export.py` check that a mutant parses; the last two also check it is not identical
  to the original.
- The 0.39 rate-excess singleton, seen once at n=40 and surviving to n=60 with no second example.
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
