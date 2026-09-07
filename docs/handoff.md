# Handoff

Written at the end of a working session so the next one starts with context rather than
archaeology. Overwritten each session — this is the current state, not a log. History lives in git.

**Session date:** 2026-09-07
**Branch:** `main`. Three commits pushed-ready; the documentation written this session is
uncommitted at the time of writing. No worktrees, no branches.

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
replayed aviation telemetry and synthetic RF observations fused through a Data Abstraction Layer,
deviations detected deterministically, evidence bundles turned into schema-validated,
grounding-checked AI hypotheses for analyst review. Decision support, not autonomous
decision-making.

This session built one item — **`scn-001`**, seeded reproducibility, landed together with the
smallest emitter that has randomness to be deterministic about. It is **implemented, green and
mutation-tested, and deliberately still `passes: false`**, pending the user's review of code and
write-up together.

`scn-005` and the ethics work landed in the previous session, which did not refresh this file.

## Current state

| | |
|---|---|
| Backend suite | **415 passed, 99.91%** via `make test-backend`, database tier live |
| Backend suite, host | 21 passed, 2 skipped for `scn-001`'s file alone; 351 passed, 61 skipped for the whole suite with no database |
| Frontend suite | **Not run this session.** Last known green at 23 passed |
| Lint / types | `make format`, `ruff check` and `mypy app` all green (run directly, not through the root `check`) |
| Spec items passing | **19 of 83** — `scn-005` since the last handoff. `scn-001` is built but not flipped |
| Emission cost | A full hour of the shipped layout is 20,160 records: **0.11 s to emit, 0.10 s to digest**, three runs varying by 5 ms |
| Cross-platform digest | Identical on macOS/arm64/py3.14.3 and Linux/aarch64/py3.13.15 |
| New dependencies | None |

### `scn-001`, as built

Four files. `app/scenario/seeding.py` is the only source of invented numbers — a BLAKE2b digest over
the seed and the cell's own coordinates, reduced to a uniform, shaped by Box–Muller, plus a seed draw
bounded to the 32-bit width of `scenario_runs.seed`. `app/scenario/emitter.py` holds
`BaselineParameters`, `RunSpec` (with `create`, the only place a seed may be drawn), `emit_baseline`
and `stream_digest`. `create_scenario_run` moved into `app/db/repository.py`, and `app/replay.py` lost
both its inline `INSERT` and its `sqlalchemy` import.

**Keyed derivation rather than sequential draws** is the decision the item turns on: no cell can see
any other, so traversal order is not an input, and `scn-002` adding an injected component per cell
will not move the values already there. Full reasoning in `thesis_notes.md`; plain-English version in
`qa.md` §47.

**Scope held deliberately narrow.** The emitter produces the unperturbed baseline in *source-record*
shape and hands it to nobody: injection and ground truth are `scn-002`'s, DAL wiring is `adp-002`'s.
`RunSpec` carries the scenario type because the run row needs it, and the emitter never reads it
(`api-009`).

### The mutations, which are the item's real evidence

From a committed baseline, each substitution confirmed before running and reverted after:

| Mutation | Red | Green |
|---|---|---|
| `derive_unit` uses the built-in salted `hash` | 2 | **19** |
| A wall-clock read inside each reading | 5 | 16 |
| The emitter ignores its seed entirely | **1** | 20 |
| `replay.py` re-implements the run row in SQL | 1 | — |

Rows one and three are the finding: a generator that cannot reproduce a campaign leaves nineteen of
twenty-one tests green, and one that ignores its seed is caught by a single test. The two that catch
them are the cross-process `PYTHONHASHSEED` comparison and the different-seeds arm — both named in
the spec's failure cases, and both the kind of test that gets left out.

Fourth appearance of the parse-versus-grep defect: `seeding.py` says `hash` three times and `random`
twice, all in prose explaining why neither is used, and the AST check over it passes.

## Files in flight

Nothing half-built. Uncommitted at the time of writing: `docs/thesis_notes.md` (two System Design and
two Implementation subsections), `docs/qa.md` (§47, §48, six glossary rows), `docs/implementation.md`
(Phase 7 checkboxes) and `CLAUDE.md` (the `app/scenario/` repo-map row).

- `docs/spec.jsonl` — `scn-001` is still `passes: false` and is the one deliberate falsehood in the
  tree. Flip it after review.
- `backend/app/scenario/emitter.py` — `scn-002` extends this file rather than replacing it: the
  injected component is a second derived quantity per cell, tagged so it cannot disturb the noise.

## Changed

Three commits, plus uncommitted documentation.

| Commit | What |
|---|---|
| `80ee3d9` | `spec: amend scn-001` — named the emitter, the recorded seed, the run-row move, and a fourth failure case on parameter sensitivity |
| `8ad2e96` | `test: add tests for scn-001` — 23 tests, 21 unit and 2 database-tier |
| `6b3a140` | `feat(scn-001): seeded reproducibility and the baseline RF emitter - tests pass` |

Added: `backend/app/scenario/seeding.py`, `backend/app/scenario/emitter.py`,
`backend/tests/test_scn_seeded.py`. Modified: `backend/app/db/repository.py` (`create_scenario_run`,
plus `json` and `Mapping` imports), `backend/app/replay.py` (SQL and `sqlalchemy` removed,
`REPLAY_SEED` added), `docs/spec.jsonl`.

**Outside the repo:** nothing. The progress note has **not** been republished for `scn-001` and is
owed — it currently tells the story up to `api-003`.

## Failed attempts

- **The stub practice recorded at the end of `scn-005` was not followed, and it should have been.**
  The first run of the new tests produced a single collection error — which satisfies the letter of
  "prove they fail" and establishes nothing, exactly as the `db-005` entry in `thesis_notes.md`
  describes. The reason was momentum, not judgement. In fairness the stub would not have caught the
  defect below, because that one only becomes visible once the import exists.
- **One test asserted the wrong thing and survived to the green stage.**
  `test_replay_holds_no_sql_of_its_own` checked `not hasattr(app.replay, "create_scenario_run")`,
  which is false the moment `replay.py` imports the name it is supposed to use — so the test failed
  against correct code. Rewritten to assert that the module defines no function of that name and that
  the name it holds *is* the storage layer's function. Sharper than the original, and red under the
  mutation.
- **`scenario_runs.seed` is 32-bit and nearly was not noticed.** A seed drawn from a wider range
  inserts fine until it does not, at an unpredictable run inside a batch. Caught by writing the test
  for the column width rather than by an insert failing.
- **Two `cd`-prefixed shell invocations failed** because the working directory had already moved;
  cosmetic, but absolute paths are cheaper than reasoning about shell state.

## Next step

Phase 7 continues in the order settled 2026-09-05, which is the reverse of what the identifiers
suggest. `scn-005` and `scn-001` are done.

1. **Review `scn-001` and flip `passes: true`.** Everything else in this list assumes it.
2. **`scn-002` — the five scenario types**, with ground truth recorded at generation time. It extends
   `emitter.py` with a per-cell injected component, tagged so the baseline values do not move.
   `normal-baseline` must inject nothing at all — `anom-008` and the false-positive rate depend on it.
   Spectral extent is a *parameter* of `gnss-degradation`, never a sixth type.
3. **`adp-002` — the synthetic RF adapter**, wiring the emitted stream through the DAL into storage
   on the full sensor × channel × time grid.
4. **`scn-003` — batch execution**, 20–30 runs from one base seed.

Owed, with an owner but no date:

- **Republish the progress note for `scn-005` and `scn-001`.** Two items behind. The pipeline-spine
  figure and the progress-by-area table both encode current state and are the first to rot.
- **Confirm the digest survives an x86-64 run.** Two-platform agreement spans an OS and a Python
  minor version but not a processor architecture; the first CI job (`ops-002`) produces this for free.
- **Adopt TanStack Query at the Phase 3 view filter, not before.** Trigger is a second polled
  endpoint (`api-007`). `src/lib/api.ts` stays the fetcher, so the swap touches the hook only.
- **`scenario.health` renders as a bare `unknown`** in the status bar and reads as a fault. Left for
  `op-001`, which rebuilds that bar with a real system-health strip.
- **The parity test compares field names, not types**, with the two detection fields excepted.
- **The frontend's structural checks scrub rather than parse**, unlike the backend's.
- **`app/corpus/build.py` resolves `.env` from the repository root** and will break the first time
  anyone containerises the corpus build.
- **Scenario type 4 must exclude the 10 tracks carrying a natural dropout** from injection sites;
  seven of the ten fall in the 100–300 s band the scenario injects. This lands with `scn-002`.
- **Re-run the coverage acceptance check as originally specified** once the scenario engine exists.
- **Record whether any Phase 6 detection rule needs altitude on more than 77% of samples** — 94 of
  the 412 tracks served by the endpoint carry none.
- **Detector radii for `anom-005` and `anom-007`** should be chosen from the measured band
  [55.7, 85.7) km, and the layout records 70 km.

Open and unowned:

- **Root `make check` has still not been run in full.** This session ran `format`, `ruff`, `mypy` and
  `test-backend` separately; the frontend suite was not run at all.
- **`make generate` is broken** — the `pipeline` service names `app.pipeline`, which does not exist
  until `scn-003`. Carried knowingly.
- **mypy does not check `tests/`.** Nearly all errors when last measured were deliberate type
  violations in negative tests.
- **CI still does not exist** (`ops-002`).
- Track 0: the data-egress question (employer) and the licence-version divergence remain open.
