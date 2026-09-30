# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational
awareness: it fuses replayed aviation telemetry and synthetic RF observations through a Data
Abstraction Layer, detects deviations deterministically, and turns evidence bundles into
schema-validated, grounding-checked AI hypotheses for analyst review. Decision support, not
autonomous decision-making.

This session built **`eval-002`, the detection metrics** and **`eval-003`, the metrics export**, then
ran **`eval-005`'s per-arm campaign figures end to end** for the first time. Between them: the
results table for the detection chapter, the per-writer table for the AI chapter, and files a thesis
row can be traced back through. Everything in the evaluation phase that does not need a second
person is now done.

## Current state

Backlog **68 of 104**. Tree clean at `85c5682`. Progress note published at v21.

- `backend/app/evaluation/metrics.py` — 237 statements, **100%**, 50 tests.
- `backend/app/evaluation/export.py` — 190 statements, **100%**, 40 tests.
- Backend suite: **1,434 passed / 288 skipped** locally; **1,682 at 99.89%** in containers.
  ruff and mypy clean.
- Mutation: **40 of 41** (`mutate_eval002_metrics.log`), **39 of 39** (`mutate_eval003_export.log`).
- Three corpus measurements of record: `detection_metrics.log` (300 runs),
  `campaign_statistics.log` (80 generations re-read), `track_gap_recall.log`.

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

### The campaign results, per arm

| Arm | Gens | Bundles | Checked | Caught | Catch | Retry | Fallback | Calls | Spend | Seconds |
|---|---|---|---|---|---|---|---|---|---|---|
| `template` (oracle) | 20 | 20 | 20 | 0 | 0.000 | 0.000 | 0.000 | 0 | $0.000000 | 0.008 |
| `hosted` | 60 | 20 | 60 | 0 | 0.000 | 0.000 | 0.000 | 60 | $0.854364 | 334.197 |
| `local` | 0 | 0 | 0 | 0 | — | — | — | 0 | $0.000000 | 0.000 |

Agreement across the three generations per bundle, hosted arm over 20 bundles: grounding **1.000**,
confidence **1.000**, cited evidence kinds **1.000**.

**That last figure corrects a prediction on `eval-005`.** The amendment written after the
three-bundle trial expected the *cited set* to be the dimension carrying the result, having seen it
move on one of three bundles. Over twenty it moved on none. The widening to three dimensions was
still right; the prediction about which one would matter was not. What is left is sharper: across
sixty generations the only thing that differed between repeated answers was the **prose**, which
none of the three measures and which `eval-004`'s blind scoring is what examines. Recorded on the
spec item, in `thesis_notes.md`, `qa.md` §121, `evaluation_harness.md` and the progress note.

The `local` row is the `None`-over-empty-population rule arriving on real data for the first time —
blank, not 0.000, with denominators of zero beside it saying which.

### The exported files

Two directories, deliberately separate: the halves were measured on **different corpora on different
dates**, and one summary file holding both would read as one measurement.

| | Stamp | Resolves to |
|---|---|---|
| `measurements/exports/detection/` | `c421c41506fd` | corpus v2, three base seeds in wave order, 300 runs, thirteen detector settings, 2026-09-30 |
| `measurements/exports/campaign/` | `9cce33897e53` | `gpt-4.1-2025-04-14`, frozen parameters, prompt digest `af153726…`, sample seed 20260928, population by bundle id, 2026-09-28 |

### Two limitations that must not be dropped

**The detection table measures wiring, not accuracy.** Every rate in it is 1.000 or 0.000. The radio
side is synthetic with the injected incident well above threshold by construction, the corpus holds
no near-misses, and one of three reportable types has no rule. The only figure carrying information
from outside the generator is the per-aircraft recall, and that is 0.587 on two arms of three.

**The retry and fallback paths never fired.** Nothing was refused and nothing fell back on the scored
campaign, so a fallback rate of zero reports that the path was *not exercised* — not that it works.

Both are recorded in `thesis_notes.md`, `evaluation_harness.md`, `qa.md` (§115, §121),
`measurements/README.md` and the progress note.

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
| `a73c798` | `docs: handoff after eval-002 and eval-003` |
| `dfd438a` | `docs: progress note — charts over the exported results, and provenance` |
| `423cf32` | `measure(eval-005, eval-003): the campaign's per-arm figures, end to end` |
| `85c5682` | `docs: the campaign's per-arm figures, and a prediction they correct` |

New files: `app/evaluation/metrics.py`, `app/evaluation/export.py`, `tests/test_eval_metrics.py`,
`tests/test_eval_export.py`, `measurements/corpus/detection_metrics.py` + `.log`,
`measurements/corpus/campaign_statistics.py` + `.log`,
`measurements/mutation/mutate_eval002_metrics.py` + `.log`,
`measurements/mutation/mutate_eval003_export.py` + `.log`,
`measurements/exports/detection/` (6 files), `measurements/exports/campaign/` (3 files).

Edited: `docs/spec.jsonl` (`eval-002` and `eval-003` amended and passing, `eval-005` amended with its
measured result), `docs/qa.md` (§110-123 + 16 glossary rows, now 125 entries), `docs/thesis_notes.md`
(18 subsections, now 236), `docs/evaluation_harness.md`, `docs/implementation.md` (two Phase 11 items
ticked), `docs/progress_note.html` (results section, three charts, provenance section, campaign
figures; published v19→v21), `backend/measurements/README.md`, `CLAUDE.md`.

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
- **A cascade miss in the progress note, present before this session.** `.dim` had only ever been
  styled inside `.record`, so every em-dash marked with it rendered unstyled. Found while adding a
  table that used it; a bare rule now exists.
- **The campaign statistics export landed in `backend/exports/` on its first run.** Off-by-one:
  `HERE` was already the directory, so `HERE.parents[1]` climbed one level too far. Removed and
  re-run.
- **`eval-005` could not simply be run**, and that is a finding rather than a slip. `ai-012`
  serialises the budget and the grounding ledger as *figures* rather than as contents, and `eval-005`
  is per arm while the stored budget is pooled — so the one artefact the campaign produced cannot
  answer the question the item after it asks of it. Two items passed independently with that join
  never exercised. Worked around by rebuilding the record with nothing invented and reconciling it
  twice; the durable fix is owed on `ai-012`.
- **`quiet_run_background`'s row in `measurements/README.md` still quoted n=20 figures** eleven days
  after the three-wave re-measurement moved them. Its own `.log` was correct. Corrected in place.
- **The progress note was two items behind and quoted a stale test count**, a stale quiet-hour count
  (twenty, not sixty) and a "what happens next" entry describing the results table as pending. All
  corrected; container suite re-run to get the real figure rather than extrapolating it.
- **The browser extension was not connected**, so the one visual pass over the three new charts could
  not be taken. Verified arithmetically instead: every drawn shape inside its viewBox, every bar
  width matching its value to the pixel, both stacked bars summing to exactly 380px and 300 aircraft.
  Worth a real look next session.
- **`make format` reformatted 12 unrelated files again.** Worked around by running `black` on the
  files in hand rather than the whole tree. Standing item below.
- **Workflow deviations, recorded rather than hidden:** in both spec items, tests were added *after*
  the implementation in response to the mutation pass — which is its purpose — and two `eval-002`
  tests came from correcting the track-side guard. Three `eval-003` test expectations were corrected
  after first green, where the flattening rule turned out more correct than the test assumed.

## Next step

1. **Serialise enough for the campaign record to round-trip** (`ai-012`). The budget and the ledger
   go out as figures, so the per-arm cost had to be rebuilt from the generations and reconciled. It
   works and is checked, but the next campaign should not need it. A spec amendment, tests, and
   `mutate_ai012_campaign`'s pass re-run. **It would not help the existing artefact**, which predates
   it, and re-running the campaign costs money and would replace a pre-registered corpus.
2. **`eval-006`** stays deferred until the second rater returns mid-October. It is the only thing
   between here and a complete evaluation chapter.
3. **A corpus with near-misses** is what would turn the detection table from a consistency result
   into an accuracy one. Out of scope for the dissertation, named as such in five places.

### Open and unowned

- **`cost_is_complete` is vacuously true on an arm that made no calls** — the same defect `eval-005`
  fixed for its rates, surviving in the one field that is a boolean rather than a rate. It reads
  correctly only because the call count of zero sits beside it in the export. Recorded in
  `thesis_notes.md` and `qa.md` §123 rather than changed, because changing a passing item to fix a
  field that reads correctly in context should be argued for first.
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
- `docs/phase9_hypothesis_layer.md` §8 still says N=1 — and the twenty-bundle agreement figures are
  now the measurement that settles what N=3 only suggested.
- Rebuilding evidence bundles corpus-wide would renumber the scored population (bundle ids 247-308)
  and stop `draw_scored_sample.py` reproducing its own draw.
