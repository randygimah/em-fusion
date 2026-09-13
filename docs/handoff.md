# Handoff

Written at the end of a working session so the next one starts with context rather than
archaeology. Overwritten each time — this is the current state, not a log. History lives in git.

**Session date:** 2026-09-13
**Branch:** `main`, clean. No worktrees, no branches.

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
replayed aviation telemetry and synthetic RF observations fused through a Data Abstraction Layer,
deviations detected deterministically, evidence bundles turned into schema-validated,
grounding-checked AI hypotheses for analyst review. Decision support, not autonomous
decision-making.

This session took the Scenario Control screen from unreachable to live: **`nav-001`** (the three-entry
rail), **`nav-003`** (that rail collapsing), **`api-006`** (the scenario endpoints) and **`api-010`**
(the screen reading them) — plus two defects found only by running it: a caption `scn-004` had
shipped, and a launcher that reported success over failure until the user pressed the button.

## Current state

| | |
|---|---|
| Frontend suite | **81 passed**, 8 files, `tsc -b` and `biome lint` clean |
| Backend suite | **584 passed, 99.88%** via `make test-backend`, database tier live, ~146 s |
| Spec items passing | **29 of 86** — `scn` 5/5, `adp` 7/8, `api` 5/10, `nav` 2/3, `db` 5/7 |
| New dependencies | None. No router library, no icon library, no task queue |
| Stack | **Up**, and **all three report healthy** since the healthcheck fix (`ops-001`). |
| Runs in the database | **120**, the newest `normal-baseline`. The screen lists the 50 most recent. |

### What exists now

**The screen is live and has been used.** `#/scenario-control` lists the runs the database holds —
the 50 most recent of 100 — on a five-second poll, and `START BATCH` posts a configuration and
reports the base seed the server used. Batches of at least three types have now been produced through
it. The fixture is gone, and so is the sentence `nav-001` put on screen describing it.

**`api-006` — the endpoints.** `POST /scenario/start` answers **202** and runs the batch on a daemon
thread; `GET /scenario/runs` lists them newest first with the recorded parameters a replay needs.
Blocking was rejected because a seventy-second request dies at nginx's sixty-second default —
passing in development and failing in the container. A queued row was rejected because nothing would
drain it. **`POST /scenario/reset` is deliberately not built**: a run is a row, `db-007` says nothing
is ever deleted, and "a cleared run state" has no honest meaning until a batch can be abandoned.

Three refusals happen **before any run row is opened**: unknown type, a batch outside 20–30, and an
incident beginning at or after its run ends — the last being the defect that produced twenty
mislabelled controls.

**`api-010` — the wiring.** Both fetches live in `lib/api.ts`, which `transport.test.ts` still
enforces as the only module reaching the network. Before the first answer the table shows **nothing**,
not example rows — the one deliberate divergence from `api-003`, reasoned in `docs/qa.md` §58. A
failed poll keeps the rows and changes only the indicator.

### Verified in the browser, against the full stack

Not reachable from any test, so done by hand through nginx:

| Checked | Observed |
|---|---|
| The screen at `:8080` | 50 real runs listed, no "fixture" anywhere on the page |
| Three refusals via `POST` | 422 each, and the newest run id unchanged at 60 — nothing written |
| Ground truth in the payload | Absent, against runs that have it recorded |
| Backend stopped underneath it | Rows stayed; "Not live — this list is the last one read" appeared |
| Backend restarted | The warning cleared on the next successful poll |
| `START BATCH`, after the fix | 202, then 20 `rf-sensor-fault` runs written and completed inside 10 s, nothing in the failure log |

**`START BATCH` has now been fired against the real stack**, after the user pressed it and reported
nothing happening. It failed — see Failed attempts — and after the fix wrote twenty `rf-sensor-fault`
runs, all complete, with nothing in the failure log.

### Mutation results

| Item | Mutations | Caught |
|---|---|---|
| `nav-001` | 8 | 8 |
| `nav-003` | 11 | 9 — see Failed attempts for the two |
| `api-006` | 8 (6 unit, 2 database) | 8 |
| `api-010` | 9 | 9 |

## Files in flight

Nothing half-built; the tree is clean.

## Changed

Twenty-two commits, `f3adcd4` through `db088cc`, plus this handoff update: four items through
spec → test → code, two defect fixes found by running the thing, two progress-note publishes, and
four docs passes.

Added, frontend: `EmNavRail.tsx`, `useCurrentScreen.ts`, `useRailCollapsed.ts`,
`useScenarioControl.ts`, `lib/scenarioLibrary.ts`, `screens/hypotheses.tsx`, and four test files.
Added, backend: `app/api/v1/scenario.py`, `app/api/v1/schemas/scenario.py`, `app/scenario/batch.py`,
`tests/test_api_scenario.py`. Modified: `routes.ts`, `App.tsx`, `scenarioControl.tsx`, `lib/api.ts`,
`scenarioControlMock.ts`, `navigation.test.tsx`, `app/dal/models.py`, `app/db/repository.py`,
`app/api/v1/__init__.py`, `docs/spec.jsonl`, `docs/thesis_notes.md`, `docs/qa.md` (§57, §58, §59),
`docs/implementation.md`, `CLAUDE.md`, `DESIGN.md`. The launcher fix also touched
`app/dal/pseudonymise.py` (the new shared helper), `app/replay.py` and `app/pipeline.py` (each losing
its own copy of it), and `app/scenario/batch.py`.

**The progress note is at version 17**, carrying a screenshot of the Scenario Control screen with a
control-by-control walkthrough, the per-type table of which dials are inert, and the batch-failure
limitation. It is now a multi-file artifact — the screenshot sits beside the page.

## Failed attempts

- **The batch button reported success over a failure, and only pressing it found that.** Every batch
  started from the screen died instantly on `PSEUDONYM_SEED is not set` while the screen said
  *Batch accepted*. Compose passes that seed from the host, so an unset host variable arrives in the
  container as an **empty string** rather than absent, and `load_dotenv(override=False)` treats
  present-but-empty as present — so nothing shadowed a perfectly good `/app/.env`. **Both
  command-line entrypoints already handled this**, each with its own copy of the remedy and its own
  comment; the launcher was a third site that needed it and had no way to know. Fixed by extracting
  one function all three call. **The launcher's own tests could not have caught it**: they substitute
  the pseudonymiser precisely so the tests need no seed, and that substitution is what made them
  blind.

- **Two `api-010` tests could not fail, and the cause was mine.** Both were written to prove the runs
  on screen come from the database rather than the fixture, and both passed before any implementation
  existed — because I had built the fake API response out of **seed values taken from the fixture**.
  A test asserting API rows was satisfied by fixture rows carrying the same numbers. Fixed by using
  seeds that appear nowhere in the fixture and asserting both halves: the API's rows present, every
  fixture row absent. **A test that distinguishes A from B must be built from values occurring in
  only one of them.**
- **A structural check punished writing the rule down, for the fourth time in this repository.** The
  new "the app imports the fixture nowhere" test failed on the module created to *replace* the
  fixture, because that module's comment explains where it came from. Fixed with a scrubber — but one
  cut differently from `transport.test.ts`'s: that one strips comments *and strings* because it hunts
  `fetch(`; this one strips comments and **keeps** strings, because an import path is a string and
  scrubbing it would make the check pass forever. The scrubber has to be cut to what is searched for.
- **`nav-003`: a width transition added for polish broke the feature it decorated.** Collapsing did
  everything except narrow the rail; mounting already-collapsed rendered 56px correctly. Removed
  rather than debugged, since the item had scoped the animation out as cosmetic. The suite was green
  throughout — the failure was entirely in layout, which jsdom does not model.
- **`nav-003`: one of my tests was satisfied by a tooltip.** "Keeps all three entries with their
  names when collapsed" passed with the label deleted, because a tooltip supplies an accessible name
  when nothing else does. Strengthened to assert the label text; found by mutation, after the fact.
- **I drafted a whole spec item as `nav-002` before checking the id was free.** It was taken by the
  system-health strip — the very item the new one had to constrain. Renumbered to `nav-003`. **Check
  the id first.**
- **I reported a defect that was not one.** With the backend stopped I read `document.body.innerText`
  a beat too early, concluded the "Not live" warning was missing, and said so before re-checking. It
  was rendering correctly. Verify before reporting, especially against a polling screen.
- **`scn-004` shipped a caption rendering below its column headers** (`display: block` on a
  `<caption>`), found by the browser pass and fixed in `c4f8d66`. **No test**: the suite finds that
  table by the accessible name the caption supplies, and that name was right throughout.
- **The three frontend items were flipped to `passes: true` with no coverage measurement.** The gate
  is 90%; the frontend still measures nothing, so mutation stood in. A deviation, not an equivalent.
  The backend has real coverage and it did its job on `api-006` — `app/scenario/batch.py` sat at 65%
  while every other module was at 100%, and the two tests closing it were written after the
  implementation, which is its own deviation.

## Next step

1. **Phase 8** — the baseline engine, then the deterministic detectors. The first thing that will
   ever read an answer key, and the first content for the panel showing two dashes.
2. **A batch that fails after acceptance is invisible** — the first owed item below. Small, and it is
   honesty rather than capability.

Owed, with an owner but no date:

- **A failed batch cannot reach the screen.** The response is sent before the work starts, so a batch
  that dies looks exactly like one still running. Needs a spec item; the open question is where the
  failure lives — a run row, a status endpoint, or in-memory state.
- **The configuration form offers dials that are inert for the selected type**, with nothing saying
  so: zone radius does nothing for `rf-sensor-fault`, and noise elevation and spectral extent do
  nothing for `aircraft-coverage-gap`. The reasons are the design; the silence is not.
- **The runs table shows the 50 most recent, unfiltered and unpaged.** Already hiding half the 100
  rows in the database, and the campaign is 150.
- **`docs/qa.md` has two entries numbered 47** — "When you say 5 dimensions…" (line 3154) and "The
  next implementation is `scn-001`…" (line 3245). Pre-existing, and **not** to be fixed by
  renumbering, which the project's own rule forbids; the fix is a note on the second saying which is
  which.
- **A batch can exhaust the database connection pool and take the API down with it.** Observed, not
  theorised: the backend was found hung on
  `QueuePool limit of size 5 overflow 10 reached, connection timed out`, serving nothing, after
  several batches had been started from the screen. **Measured afterwards: one batch is harmless** —
  it adds a single connection and `/health` stays 200 throughout — so the trigger is *concurrent*
  batches, and nothing limits them: every `POST /scenario/start` spawns another unbounded daemon
  thread, and they share the API's one pool with request serving. The exact number of concurrent
  batches needed was **not** determined, and saying so matters more than guessing it. Nothing sets
  `pool_size` or `max_overflow`, so the ceiling is SQLAlchemy's default 15. Three candidate fixes,
  needing a decision rather than a default: refuse a second batch while one is in flight (which would
  also give a future reset something to cancel); give batches their own small engine so they cannot
  starve the API; or raise the pool, which only moves the cliff. The first two are complementary and
  are what I would recommend.
- **Decide whether the five batches share one base seed.** Recommended and measured; belongs to
  `eval-001` with whether the incident dials vary within a batch. Both must be settled before the
  scoring campaign is generated.
- **Decide on frontend coverage tooling** (`@vitest/coverage-v8`). Argued for by six findings now.
- **`nav-002`, the system-health strip, inherits a question from `nav-003`**: what it shows at 56px.
  It must not be answered by letting a collapse hide health.
- **Reset needs an item** once a batch can be cancelled — `api-006` deferred it, and nothing can stop
  a started batch today.
- **Replay is unreachable through `start`**, which takes a configuration and a batch of 20–30. A
  single-run replay needs its own endpoint or a relaxed bound.
- **The scenario poll runs at five seconds regardless of whether a batch is in flight.** Cheap today;
  revisit if the runs list grows past its 50-row limit.
- **Run `pnpm format` across the frontend** as its own `style:` commit, or drop the formatter config.
- **A run row cannot distinguish a run still going from one that died.** A status column would fix it.
- **`op-001`'s badge must key off the run, not off an observation's data mode.**
- **A floor on the affected-aircraft count** rather than a bare 8%, once detectors exist.
- **Record the measured false-positive rate on the coverage-gap type** with and without the exclusion.
- **Confirm the digest survives an x86-64 run.** The first CI job produces this for free.
- **Detector radii for `anom-005` and `anom-007`** from the measured band [55.7, 85.7) km.
- **The frozen-position shortcut is a limitation, not a bug.**
- **Adopt TanStack Query at the Phase 3 view filter, not before.** Two polled endpoints now exist,
  which is one of the three conditions that decision named.
- **`scenario.health` renders as a bare `unknown`**; left for `op-001`.
- **The parity test compares field names, not types.**
- **`app/corpus/build.py` resolves `.env` from the repository root.**

Open and unowned:

- **Root `make check` has still not been run in full.**
- **mypy does not check `tests/`.**
- **CI still does not exist** (`ops-002`).
- Track 0: the data-egress question (employer) and the licence-version divergence remain open.
