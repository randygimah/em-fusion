# Handoff

Written at the end of a working session so the next one starts with context rather than
archaeology. Overwritten each session — this is the current state, not a log. History lives in git.

**Session date:** 2026-09-07 to 2026-09-11
**Branch:** `main`. Everything committed; the documentation in this final commit is the only thing
written after the last test run. No worktrees, no branches.

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
replayed aviation telemetry and synthetic RF observations fused through a Data Abstraction Layer,
deviations detected deterministically, evidence bundles turned into schema-validated,
grounding-checked AI hypotheses for analyst review. Decision support, not autonomous
decision-making.

This session built three items — **`scn-001`** (seeded reproducibility with the baseline emitter),
**`adp-008`** (the injection-exclusion list) and **`scn-002`** (the five scenario types, in four
passes). All three pass. **The scenario generator is now complete except for batch execution and the
control screen.**

## Current state

| | |
|---|---|
| Backend suite | **489 passed, 99.92%** via `make test-backend`, database tier live |
| Frontend suite | **Not run this session.** Last known green at 23 passed |
| Lint / types | `black`, `ruff` and `mypy app` green; run directly, not through root `check` |
| Spec items passing | **22 of 84** — `scn` 3/5, `adp` 6/8 |
| `app/scenario/` coverage | 100%, all five modules |
| Cross-platform digest | Identical on macOS/arm64/py3.14.3 and Linux/aarch64/py3.13.15 |
| Emission cost | 20,160 readings per hour: 0.11 s to emit, 0.10 s to digest |
| New dependencies | None |

### What exists now, end to end

A run is `(scenario type, parameters, seed)`. `plan_incident` decides the RF staging and
`plan_track_perturbation` the track staging, both from **one seed-derived centre**, so the two halves
are co-located by construction. `emit_rf` produces the full sensor × channel × tick grid with the
injection added per cell under its own derivation key. `TrackPerturber` suppresses or ages records
between the adapter and the DAL, via a `transform` callable on `replay_window`. `ground_truth`
produces the answer key, and `create_scenario_run` / `record_ground_truth` write it to the run row in
two instalments.

Measured on one fifteen-minute run at seed 20220627: **5,040 readings, 60 changed, 4,980
byte-identical** to the same seed's quiet run. The zone centres on Rotterdam, reaches Schiphol at
45 km, excludes the other five receivers.

### Mutation results, all from committed baselines

| Mutation | Red |
|---|---|
| `derive_unit` uses the built-in salted `hash` | 2 of 21 — **19 stayed green** |
| A wall-clock read inside each reading | 5 |
| The emitter ignores its seed entirely | **1** |
| A sixth scenario type added | 1 |
| Perturbation ignores the zone | 2 |
| The two halves stop sharing a centre | 4 |
| Answer key written as `{}` rather than null | 2 |
| The artefact stores raw `icao24` | 3 |
| The seed itself written into the committed report | 1 |

## Files in flight

Nothing half-built; the tree is clean.

- `backend/app/scenario/` — five modules, all at 100%. `scn-003`'s batch runner sits on top of these
  without changing them.
- `data/opensky/natural_gaps.json` — committed, 10 gaps across 7 aircraft, pseudonyms only.

## Changed

Seventeen commits. In order: `scn-001` (spec amendment, tests, implementation, flip), the write-up,
`adp-008` (new spec item, tests, implementation, flip), then `scn-002` in four
test-then-implementation pairs and a flip.

Added: `app/scenario/seeding.py`, `emitter.py`, `incident.py`, `tracks.py`,
`app/corpus/natural_gaps.py`, `data/opensky/natural_gaps.json`, and five test files
(`test_scn_seeded`, `test_corpus_natural_gaps`, `test_scn_incident`, `test_scn_tracks`,
`test_scn_ambiguous`, `test_scn_ground_truth`).

Modified: `app/db/repository.py` (`create_scenario_run`, `record_ground_truth`), `app/replay.py` (SQL
and `sqlalchemy` removed), `app/adapters/opensky.py` (the `transform` seam),
`app/corpus/fetch.py` and `build.py` (the exclusion list rides the corpus build),
`app/scenario/layout.py` (`great_circle_km` and `site` made public), plus `docs/spec.jsonl`,
`thesis_notes.md`, `qa.md` (§47–§51), `implementation.md` and `CLAUDE.md`.

**Outside the repo:** the progress note was republished four times to the same URL —
<https://claude.ai/code/artifact/7f3060f9-29d5-46de-b12b-eddd3824cccc>. It now carries the seeded
generator with a keyed-vs-sequential figure, the corrected dropout confound, the staged-incident
material with a zone map and a two-signatures timeline, and a full treatment of the five scenarios:
what a quiet run contains, what one seed decides, and both marking paths.

## Failed attempts

- **Pass 2 of `scn-002` shipped a real defect: track targeting ignored the incident's location.** A
  navigation incident centred on Rotterdam would have frozen positions over Cologne while the answer
  key called them one event. The spec said "aircraft inside the affected area" all along — this was a
  partial reading, and **the tests encoded the same partial reading, so nothing failed.** Found only
  when pass 3's correctness depended on the same property from another direction. Tests written from
  the same reading as the implementation cannot catch a misreading of the spec.
- **An `api-009` test matched the substring `"ground"` against `on_ground`**, a legitimate field
  about whether an aircraft is airborne. The identical assertion in pass 1 passed only because RF
  payloads carry no similarly-named field — luck, not correctness. Both now compare structure against
  an unperturbed record. Fifth appearance of text-matching where parsing was needed.
- **`thesis_notes.md` claimed a mitigation that had no input.** It recorded that the coverage report
  "identifies exactly which tracks carry a natural dropout"; it does not, and never did. The
  mitigation would have been found empty at the moment `scn-002` reached for it.
- **The same paragraph's confound figure was wrong**: ten gaps were read as ten tracks. They are
  seven — 0.74% of the fleet, not 1.05%. Corrected in the notes, in `qa.md` and on the progress note.
- **One test asserted `not hasattr(app.replay, "create_scenario_run")`**, which is false as soon as
  the module imports the name it is meant to use. Rewritten to assert the module defines no such
  function and that the name it holds *is* the storage layer's.
- **The stub practice was skipped for `scn-001`** and followed for everything after. The first run
  produced a single collection error, which satisfies the letter of "prove they fail" and establishes
  nothing.
- **Several `cd`-prefixed shell invocations failed** because the working directory had already
  moved, and one of them silently skipped applying a mutation — the container run that followed
  proved nothing until it was redone with absolute paths.

## Next step

Phase 7 has two items left, then Phase 8 opens.

1. **`scn-003` — batch execution.** 20–30 runs from one base seed with derived per-run seeds, each
   with its own recorded parameters and answer key, a failing run skipped rather than aborting the
   batch. Sits on top of `app/scenario/` without changing it. `make generate` is currently broken
   because the `pipeline` service names `app.pipeline`, which this item creates.
2. **`scn-004` — the Scenario Control screen.** The visible face of the harness; the seed field must
   be visible and editable.
3. **Phase 8** — baseline engine, then the deterministic detectors. The first thing that will ever
   read an answer key.

Owed, with an owner but no date:

- **Record the measured false-positive rate on the coverage-gap type with and without the exclusion**
  — the gap left in `thesis_notes.md` when `adp-008` landed.
- **Confirm the digest survives an x86-64 run.** Two-platform agreement spans an OS and a Python
  minor version but not a processor architecture; the first CI job produces this for free.
- **Detector radii for `anom-005` and `anom-007`** should be chosen from the measured band
  [55.7, 85.7) km; the layout records 70 km and the incident radius defaults to 60 km.
- **The frozen-position shortcut is a limitation, not a bug.** The coordinate keeps advancing while
  the reported staleness grows. No Phase 8 rule recomputes staleness from coordinates; one that did
  would silently fail on that scenario type, and the trade would need revisiting.
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
