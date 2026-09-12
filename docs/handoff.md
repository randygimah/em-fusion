# Handoff

Written at the end of a working session so the next one starts with context rather than
archaeology. Overwritten each session — this is the current state, not a log. History lives in git.

**Session date:** 2026-09-11 to 2026-09-12
**Branch:** `main`, clean. Ten commits, all pushed to the local branch. No worktrees, no branches.

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
replayed aviation telemetry and synthetic RF observations fused through a Data Abstraction Layer,
deviations detected deterministically, evidence bundles turned into schema-validated,
grounding-checked AI hypotheses for analyst review. Decision support, not autonomous
decision-making.

This session landed **`adp-002`** (the synthetic RF adapter) and opened **`scn-003`** (batch
execution), whose pass-1 tests are written and red. `adp-002` was not on the plan: `scn-003` was, and
`adp-002` turned out to be the body its loop executes, so it went first. Reasoning in `docs/qa.md`
§52.

## Current state

| | |
|---|---|
| Backend suite | **508 passed, 99.92%** via `make test-backend`, database tier live |
| Frontend suite | **Not run this session.** Last known green at 23 passed |
| Spec items passing | **23 of 84** — `adp` 7/8, `scn` 3/5 |
| `app/adapters/synthetic_rf.py` | 11 statements, 100% |
| Storing one run | 5,040 readings in **0.45 / 0.44 / 0.43 s** into PostGIS, all 5,040 cells distinct |
| New dependencies | None |

### What exists now, end to end

A whole staged run has been driven into the database — **by a throwaway script, not by a command**:
`create_scenario_run` with parameters and planned ground truth → `emit_run` ingesting the RF grid →
`record_ground_truth` → `complete_scenario_run`. The row came back `gnss-degradation`, seed
20220627, ground truth present, completed. That is where the storage figures above come from.

What does not exist is the thing that does it unattended, thirty times, with the track half attached.

### Measurements taken this session

Aircraft within a 60 km zone of each receiver over the default five-minute incident window
(12:02–12:07), from the real corpus — 10,759 rows, 410 distinct aircraft in the whole box:

| Centre | Aircraft | Staged at 8% |
|---|---|---|
| Schiphol 75 · Lelystad 74 · Rotterdam 71 | — | ≈6 |
| Köln/Bonn 28 · Düsseldorf 28 · Weeze 25 | — | ≈2 |
| **Eindhoven 18** | — | **1.4** |

Thirty derived seeds from base 20220627 are all distinct and land on all seven receivers, two to six
runs each. Both figures are written up in `docs/qa.md` §53 and `thesis_notes.md` (Evaluation).

### Mutation results, `adp-002`, all from the committed baseline

| Mutation | Red |
|---|---|
| The incident is never planned | 2 |
| The run is marked replayed | 2 |
| The adapter derives a value of its own | 3 |
| The adapter defines its own `create_scenario_run` | **1** |
| One batch per tick instead of one per run | 1 |

## Files in flight

- `backend/app/pipeline.py` — **stub only.** `MIN_RUNS`, `MAX_RUNS`, and `derive_seeds` /
  `derive_window` raising `NotImplementedError`. Pass 1 implements the two functions.
- `backend/tests/test_scn_batch.py` — 16 tests, **all red**, proven individually against that stub.
- `backend/app/scenario/emitter.py` — **not yet touched.** Pass 1 adds `start` and
  `duration_seconds` to `as_parameters()` and a `RunSpec.from_record` classmethod. Four of the
  sixteen tests are waiting on it. `test_scn_seeded.py:308` asserts only that the seed is absent
  from the recorded parameters, so adding keys does not break it.

## Changed

Ten commits: `8d9bc1c` (spec: amend adp-002), `9d53aee` (qa 52), `223d767` (tests for adp-002),
`9ec96e2` (adp-002 passes), `b76c3eb` (thesis note for adp-002), `583d039` (qa 53), `bc42564` (spec:
amend scn-003 and ops-003), `4be5e5f` (tests for scn-003 pass 1), `279a537` (thesis notes for
scn-003), `1d200a3` (repo map and phase checklist).

Added: `app/adapters/synthetic_rf.py`, `app/pipeline.py` (stub), `tests/test_adp_synthetic_rf.py`,
`tests/test_scn_batch.py`. Modified: `docs/spec.jsonl` (`adp-002` amended and flipped, `scn-003` and
`ops-003` amended), `docs/qa.md` (§52–53), `docs/thesis_notes.md` (one Implementation and two new
subsections), `docs/implementation.md`, `CLAUDE.md` (repo map).

**Outside the repo:** the progress note was republished once, to the same URL —
<https://claude.ai/code/artifact/7f3060f9-29d5-46de-b12b-eddd3824cccc>. It now carries the synthetic
half reaching the store, with a real stored reading, the one-act-versus-twelve figure, the storage
measurements, and the new test-defect family.

## Failed attempts

- **A pair of tests in `test_adp_synthetic_rf.py` compared two things that were not comparable.**
  The stored side was reduced to a timestamp plus payload; the expected side was digested as whole
  source records carrying provenance. The equality test could not pass however correct the adapter
  was, and **its inequality twin could not fail however wrong it was** — and had been green since it
  was written. Only the first announced itself. Found by running the implementation, not by the
  tests. Both sides now reduce to one shape, and mutation A confirms the inequality test is
  sensitive to the thing it exists to detect.
- **`test_a_failed_write_stores_nothing` passed its `pytest.raises(RuntimeError)` against the
  stub**, because `NotImplementedError` is a `RuntimeError`. It failed one line later on the call
  count, so it looked fine. Now matched on the message.
- **I reached for a clarifying question where a recommendation was wanted.** Two scoping questions
  were put up (run scope, `make generate` default) and declined; the user asked for the answer
  instead. Both were answerable from the code and the specs. Default to recommending.
- **The progress note now carries a claim that will need qualifying.** It says an invented run "is
  stored in a single act, and a failure leaves nothing at all behind". That is true of the RF grid
  and becomes half-true when `scn-003` adds the track half's own write. Fix it on the note when the
  item lands, not after.
- **The same note's seven-centres claim is loose**: "thirty runs end up staging thirty different
  incidents rather than thirty copies of one" is thirty different *combinations* but at most seven
  places, repeating two to six times. Now measured; tighten in the same pass.

## Next step

1. **`scn-003` pass 1 — implement.** `derive_seeds` and `derive_window` in `app/pipeline.py`;
   `as_parameters()` gains the window and `RunSpec.from_record` arrives in `emitter.py`. Sixteen
   tests waiting.
2. **`scn-003` pass 2 — spec, tests, code.** The run executor driving both halves under one run id,
   failure isolation, per-run reporting including the staged-aircraft count, the `python -m
   app.pipeline` CLI, and `make generate` with `PIPELINE_ARGS`. `ops-003`'s carve-out is lifted only
   when this passes.
3. **`scn-004`** — the Scenario Control screen. The seed field must be visible and editable.
4. **Phase 8** — baseline engine, then the deterministic detectors. The first thing that will ever
   read an answer key.

Owed, with an owner but no date:

- **Qualify the progress note's single-act claim and tighten its seven-centres sentence** when
  `scn-003` lands.
- **A floor on the affected-aircraft count**, rather than a bare 8% of whatever traffic is present —
  decide when the detectors exist and the clustering rule's sensitivity to dropout count is known.
  Deciding now would be tuning the generator against a detector nobody has written.
- **Record the measured false-positive rate on the coverage-gap type with and without the
  exclusion** — the gap left in `thesis_notes.md` when `adp-008` landed.
- **Confirm the digest survives an x86-64 run.** Two-platform agreement spans an OS and a Python
  minor version but not a processor architecture; the first CI job produces this for free.
- **Detector radii for `anom-005` and `anom-007`** should be chosen from the measured band
  [55.7, 85.7) km; the layout records 70 km and the incident radius defaults to 60 km.
- **The frozen-position shortcut is a limitation, not a bug.** No Phase 8 rule recomputes staleness
  from coordinates; one that did would silently fail on that scenario type.
- **Adopt TanStack Query at the Phase 3 view filter, not before.**
- **`scenario.health` renders as a bare `unknown`** in the status bar; left for `op-001`.
- **The parity test compares field names, not types.**
- **The frontend's structural checks scrub rather than parse**, unlike the backend's.
- **`app/corpus/build.py` resolves `.env` from the repository root** and will break the first time
  anyone containerises the corpus build.

Open and unowned:

- **Root `make check` has still not been run in full**; the frontend suite has not run this session.
- **mypy does not check `tests/`.**
- **CI still does not exist** (`ops-002`).
- Track 0: the data-egress question (employer) and the licence-version divergence remain open.
