# Handoff

## Goal

EM Fusion is a human-in-the-loop prototype for explainable electromagnetic situational awareness: it
fuses replayed aviation telemetry with synthetic RF observations, detects deviations
deterministically, and turns evidence bundles into schema-validated, grounding-checked AI hypotheses
for analyst review. It is decision support, not autonomous decision-making.

This session continued the chain the previous one started: settle detection latency (`anom-009`),
then close the remaining inputs `eval-002` needs. It built **`anom-008`, the quiet-run control**, end
to end — spec refinement, tests, measurement, implementation, mutation pass, documentation.

## Current state

**`anom-008` is closed.** 28 tests, 100% coverage on `app/detection/control.py`, mutation pass **29
of 29 killed with no survivors**. Backlog **65 of 104**.

Suite: **1,343 passed, 288 skipped**. `make lint` and `make type-check` clean. Tree clean.

**The measurement of record** (`measurements/corpus/quiet_run_background.log`, corpus v2, n=20 quiet
runs):

| Producer | Band per quiet run | Median | Silence |
|---|---|---|---|
| `RF-NOISE` / `rf_noise_deviation` | 0–0 | 0 | correct |
| `TRACK-GAP` / `track_continuity_gap` | 9–19 | 16.5 | **fails** |
| `TRACK-CLUSTER` / `track_gap_cluster` | 5–9 | 7 | **fails** |
| `TRACK-GAP` / `track_rate_excess` | 0–0 | 0 | correct, structurally |

**Headline: 0 of 20 quiet runs show the analyst anything** — over **two of the three** reportable
types. `anom-006` has no rule, so it is registered as *not exercised* rather than clean, and the
control carries the coverage figure for `eval-002` to quote beside the rate.

Three design points that are load-bearing and easy to undo by accident:

- The control grades an **account of every registered producer** and refuses a run where one is
  missing. On the reportable side zero is the required answer, so an empty input and a correct run
  are indistinguishable by counting — the refusal, not a count, is what answers *did this detector
  look*.
- The register is keyed on the **`(rule_id, finding_type)` pair**. `anom-012` borrows `anom-010`'s
  rule id; keyed on the rule alone one producer silently replaces the other.
- **"Zero fails" is carried by the measured band, never asserted.** The item's 14 September amendment
  justified the non-zero rule entirely from replayed track data and it does not hold on the synthetic
  RF side.

Standing, unchanged: nothing applies migrations to the application database in the ordinary path; six
mutation harnesses lack the guard+sentinel pair; `ai-011`'s harness has not been re-run; the
credential loader is not generalised; `ai-008`'s superseded case has no corpus demonstration; the
frontend suite exits non-zero (`control.runs.map is not a function`, `scenarioControl.tsx:344`);
`docs/phase9_hypothesis_layer.md` §8 still says N=1; waves 2 and 3 of corpus v2 are not generated.

**12 files are still not Black-formatted.** `make format` reformats them, which is why it was run and
then reverted this session — a formatting sweep does not belong in a feature commit. It is its own
one-line commit whenever somebody wants it.

## Files in flight

None. Tree clean at `0de2fef` plus the documentation commit that follows it.

Added this session:

- `backend/app/detection/control.py` — the control (130 statements, 100%)
- `backend/tests/test_anom_control.py` — 28 tests
- `backend/measurements/corpus/quiet_run_background.py` + `.log`
- `backend/measurements/mutation/mutate_anom008_control.py` + `.log`

## Changed

| Commit | What |
|---|---|
| `bac7810` | `spec: refine anom-008 — the register, the account, and the measured band` |
| `a6ad5d3` | `test: add tests for anom-008` |
| `0de2fef` | `feat(anom-008): the quiet-run control - tests pass` |

Documents updated: `docs/spec.jsonl` (`anom-008` refined and passing), `docs/qa.md` (§105–108 plus
five glossary terms, and **five run-together glossary rows repaired** — a previous session had
written literal `\n` into the table), `docs/thesis_notes.md` (five subsections),
`docs/detection_layer.md` (new section *The other half: the hours where nothing was staged*, plus
three vocabulary rows), `docs/implementation.md` (the `anom-008` accumulation note closed),
`backend/measurements/README.md` (two rows), `CLAUDE.md` (repo map entry for `control.py`).

## Failed attempts

- **The register nearly did not include the unbuilt rule.** The first sketch had `SOURCE-GAP` simply
  absent, to be added when `anom-006` lands. That would have made the control report zero
  `possible_data_source_issue` on every quiet run — quoting the absence of a rule as its accuracy,
  which is the most flattering sentence the instrument could produce. Caught by reading the tail of
  `anom-006`, which records it as closed on measurement rather than merely unbuilt.
- **"Silence means the detector did not look" was nearly written in as a blanket rule for every
  intermediate producer**, which is what the item's own amendment says. It would have failed roughly
  86% of quiet runs (by `anom-014`'s figure) and, as measured here, **100% of them** — the RF rule
  raises nothing on 20 of 20. The amendment's reasoning was drawn entirely from replayed track data
  and does not transfer to the synthetic grid. Fixed by moving the requirement into the measured
  band, which also removed the need for any rule identifier in the comparison.
- **`anom-012` was nearly dropped from the register** on the grounds that it never runs on a quiet
  run. Keeping it was right for two reasons found late: a non-zero count there means an upstream rule
  fired, and it is the register's only real key collision — without it the pair-key argument is
  speculative rather than demonstrated.
- **Two mutants in the first harness run were invalid, and one of them mattered.** Keying the register
  on the rule id alone broke the module at import, so no test ran and the harness reported
  *inconclusive* rather than killed. That is correct behaviour — a mutant killed by the language is
  not killed by the suite — and it is the second time in two items that a mutant appeared to be caught
  by a test that never ran. Replaced with a mutant producing the same defect without preventing
  collection.
- **The module hit 100% line coverage with two guards untested** (negative band floor, duplicate
  registration). Coverage is blind to them because every other test takes the false branch. Found by
  `--cov-report=term-missing`, not by the suite passing.
- **`make format` reformatted 12 unrelated files.** Reverted rather than committed; noted above.

## Next step

1. **`anom-011`** — track-gap recall. The module (`app/detection/sensitivity.py`) and its 478-line
   suite already exist and `passes` is still `false`, because the item requires the figure measured on
   **at least two independently seeded batches** before it is reported as a property of the detector.
   Check what `measurements/corpus/track_gap_recall.py` has actually been run against; this may be a
   measurement away from closing rather than a build.
2. **`eval-002`** — precision, recall, F1, FPR, FNR, latency per scenario type. Its three detection
   inputs are now: latency from `anom-009` (built), false positives from `anom-008` (built), recall
   from `anom-011` (module built, figure owed). **Precision, F1 and latency have never been computed
   at all.** Note the two constraints the item already carries: a run of a staged type that staged
   nothing is excluded from *every* metric with the exclusion count reported, and the false-positive
   rate must be quoted as covering two reportable types of three.
3. **`eval-003`** — CSV/JSON metrics export. Gated on `eval-002`.
4. **`eval-006`** — deferred to mid-October, when the second rater returns and both score sheets exist.

Open and unowned:

- Mutation harnesses for the four evaluation modules — 104 tests with nothing establishing they are
  load-bearing.
- Only `mutate_anom009_latency.py` and `mutate_anom008_control.py` check that a mutant parses.
- The 12 unformatted files.
- The frontend suite failure.
