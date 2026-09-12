# Handoff

Written at the end of a working session so the next one starts with context rather than
archaeology. Overwritten each session — this is the current state, not a log. History lives in git.

**Session date:** 2026-09-11 to 2026-09-12
**Branch:** `main`, clean. Sixteen commits. No worktrees, no branches.

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
replayed aviation telemetry and synthetic RF observations fused through a Data Abstraction Layer,
deviations detected deterministically, evidence bundles turned into schema-validated,
grounding-checked AI hypotheses for analyst review. Decision support, not autonomous
decision-making.

This session landed **`adp-002`** (the synthetic RF adapter) and **`scn-003`** (batch execution, in
two passes). `adp-002` was not on the plan — `scn-003` was, and `adp-002` turned out to be the body
its loop executes, so it went first (`docs/qa.md` §52). **Phase 7 now has one item left: the
Scenario Control screen.**

## Current state

| | |
|---|---|
| Backend suite | **554 passed, 99.93%** via `make test-backend`, database tier live |
| Frontend suite | **Not run this session.** Last known green at 23 passed |
| Spec items passing | **24 of 84** — `adp` 7/8, `scn` 4/5 |
| `app/pipeline.py` · `app/adapters/synthetic_rf.py` | 193 and 11 statements, both 100% |
| `make generate` | **Works for the first time.** 20 runs, 52.5 s, ~510k rows |
| New dependencies | None |

### What exists now, end to end

`make generate` runs a batch unattended: per-run seeds and corpus windows derived from one base
seed, each run opening its own row, emitting the RF grid, replaying a corpus window through the
perturber, recording the finished answer key and marking completion. A failing run is recorded and
stepped over. `python -m app.pipeline` takes the scenario type, base seed, run count, duration and
all five incident dials; `PIPELINE_ARGS` carries them through Compose.

### Measurements taken this session

- **Storing one run:** 5,040 readings in 0.45 / 0.44 / 0.43 s into PostGIS, all 5,040 cells distinct.
- **One batch:** 20 coverage-gap runs of ten simulated minutes, 52.5 s, ~510k rows, **0–11 aircraft
  staged per run — one run staged none.**
- **Zone traffic**, over the default five-minute window (10,759 rows, 410 aircraft in the box):
  Schiphol 75, Lelystad 74, Rotterdam 71, Köln/Bonn 28, Düsseldorf 28, Weeze 25, **Eindhoven 18**.
- **Thirty derived seeds** from base 20220627 are all distinct and land on all seven receivers, two
  to six runs each.
- **Window collisions:** whole-second offsets for 25 runs in a one-hour corpus give 25 distinct
  windows for base 20220627 and **24 for base 1** — collisions about one time in eight.

### Mutation results, all from committed baselines

| Item | Mutation | Red |
|---|---|---|
| `adp-002` | incident never planned · replayed mode · derives its own value · own run row · batch per tick | 2 · 2 · 3 · 1 · 1 |
| `scn-003` pass 1 | seeds from a sequence · base ignored · no re-derivation · one window · row drops window · unknown parameter dropped | 1 · 1 · 2 · 2 · 5 · 1 |
| `scn-003` pass 2 | track half never replayed · tracks marked synthetic · failing run aborts · stage-nothing accepted · completion before answer key | 10 · 1 · 2 · 2 · 1 |

## Files in flight

Nothing half-built; the tree is clean.

## Changed

Sixteen commits, `8d9bc1c` through `a9fa759`. In order: `adp-002` (spec amendment, qa 52, tests,
implementation, flip, thesis note); `scn-003` (qa 53, spec amendment with `ops-003`, pass 1 tests,
pass 1 implementation, pass 2 tests, pass 2 implementation and flip, write-up); plus the repo map,
phase checklist and handoff.

Added: `app/adapters/synthetic_rf.py`, `app/pipeline.py`, `tests/test_adp_synthetic_rf.py`,
`tests/test_scn_batch.py`, `tests/test_scn_pipeline.py`. Modified: `app/scenario/emitter.py`
(`as_parameters` carries the window, `RunSpec.from_record` added), root `Makefile` (`generate`
rewritten, `build-pipeline` added, `PIPELINE_ARGS`), `tests/test_ops_command_surface.py`,
`docs/spec.jsonl` (`adp-002`, `scn-003`, `ops-003`), `docs/qa.md` (§52–53), `docs/thesis_notes.md`,
`docs/implementation.md`, `CLAUDE.md`.

**Outside the repo:** the progress note was republished twice to the same URL —
<https://claude.ai/code/artifact/7f3060f9-29d5-46de-b12b-eddd3824cccc>. It now carries the synthetic
half reaching the store and a whole section on the batch, with a figure drawn from the twenty
windows the real run chose.

## Failed attempts

- **A pair of tests compared two things that were not comparable.** Stored observations reduced to
  timestamp-plus-payload against emitted records digested whole. The equality test could not pass
  however correct the code was; **its inequality twin could not fail however wrong it was**, and had
  been green since written. Only the first announced itself.
- **The window-distinctness test would have passed on the fixture's own seed and failed on the next
  one.** Measured before implementing: 25/25 distinct for base 20220627, 24/25 for base 1. The batch
  now guarantees distinctness by re-deriving rather than trusting the space.
- **A mutation hung the suite instead of failing it**, and stranded a mutated file when it was
  killed. The retry loop had no bound, so a derivation that stops keying on its retry counter spins
  forever. Now bounded and named; the mutation harness runs each case under a timeout.
- **The structural no-randomness rule did not reach the new module.** Replacing keyed derivation
  with a seeded sequence left all 18 tests green: both give the same prefix property, so no
  behavioural test can separate them. `scn-001` asserts the constraint only over `app/scenario/`.
- **The ordering mutation took two attempts to catch.** Swapping "record the answer key" and "mark
  complete" left 26 tests green. The first fix refused the second database transaction — still
  green, because under the swap that *is* the completion call, so both orders fail identically.
  Refusing the third is what separates them.
- **A Makefile assertion passed against a comment.** `"app.pipeline" in makefile` matched the
  comment saying the pipeline service named a module that did not exist. Sixth appearance of
  text-matching where parsing was needed.
- **`make generate` died on a missing library**: the pipeline service builds its own image and had
  no build prerequisite, so a cached image predating SQLAlchemy ran. Fixed with `build-pipeline`.
- **The first working batch reported twenty successes and produced twenty mislabelled controls.** A
  two-minute run with the default two-minute incident offset staged every incident after its own run
  ended. Every line of that code was covered by passing tests.
- **A test was written after its implementation** (the unknown-parameter refusal), because the
  coverage gate passed at 99.85% while that branch was never exercised. The guard test likewise came
  from mutation rather than the test stage. Both recorded in their own docstrings.
- **I reached for a clarifying question where a recommendation was wanted.** Two scoping questions
  were put up and declined; both were answerable from the code and the specs.

## Next step

1. **`scn-004` — the Scenario Control screen.** The last item in Phase 7. The seed field must be
   visible and editable; replay of a listed run reuses its exact recorded seed and parameters, which
   `RunSpec.from_record` now makes possible.
2. **Phase 8** — baseline engine, then the deterministic detectors. The first thing that will ever
   read an answer key.

Owed, with an owner but no date:

- **Decide whether parameters vary within a batch.** `scn-003`'s input says "a parameter
  distribution"; today every run in a batch is configured identically and only the seed, place,
  traffic and noise differ. Varying difficulty per run interacts directly with the 0–11 staging
  spread, so it is a deliberate decision — left for `eval-001`.
- **`op-001`'s badge must key off the run, not off an observation's data mode.** A run's track half
  is stored as `replayed`, because a perturbed row is a real recorded observation a scenario edited.
  The `DataMode` docstring's claim that the badge reads the data is now imprecise for that half.
- **A floor on the affected-aircraft count** rather than a bare 8% — decide when the detectors exist
  and the clustering rule's sensitivity to dropout count is known.
- **Record the measured false-positive rate on the coverage-gap type with and without the
  exclusion** — the gap left in `thesis_notes.md` when `adp-008` landed.
- **Confirm the digest survives an x86-64 run.** The first CI job produces this for free.
- **Detector radii for `anom-005` and `anom-007`** from the measured band [55.7, 85.7) km.
- **The frozen-position shortcut is a limitation, not a bug.**
- **Adopt TanStack Query at the Phase 3 view filter, not before.**
- **`scenario.health` renders as a bare `unknown`**; left for `op-001`.
- **The parity test compares field names, not types.**
- **The frontend's structural checks scrub rather than parse.**
- **`app/corpus/build.py` resolves `.env` from the repository root.**

Open and unowned:

- **Root `make check` has still not been run in full**; the frontend suite has not run this session.
- **mypy does not check `tests/`.**
- **CI still does not exist** (`ops-002`).
- Track 0: the data-egress question (employer) and the licence-version divergence remain open.
