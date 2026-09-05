# Handoff

Written at the end of a working session so the next one starts with context rather than
archaeology. Overwritten each session — this is the current state, not a log. History lives in git.

**Session date:** 2026-09-04 to 2026-09-05
**Branch:** `main`, **in sync with `origin/main`** apart from this handoff. Working tree clean.

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
replayed aviation telemetry and synthetic RF observations fused through a Data Abstraction Layer,
deviations detected deterministically, evidence bundles turned into schema-validated,
grounding-checked AI hypotheses for analyst review. Decision support, not autonomous
decision-making.

This session built four items — **`db-007`** (the run completion flag), **`api-002`** (the
operational picture endpoint), **`db-006`** (nothing in the API layer touches storage directly) and
**`api-003`** (the dashboard polls that endpoint). **Phase 5 is complete, 8 of 8, and written up in
`thesis_notes.md`.**

The loop is closed: an hour of archived air traffic goes in by `make replay` and comes out as pixels
in a browser, with no mock in the path.

## Current state

| | |
|---|---|
| Backend suite | **340 passed, 99.89%** via `make test-backend` |
| Frontend suite | **23 passed** via `make test-frontend`, in its container |
| Lint / types | `make lint` and `make type-check` green |
| Spec items passing | **18 of 83** — `api-001`–`api-003`, `adp-001`, `adp-004`–`adp-007`, `dal-001`–`dal-004`, `db-001`, `db-003`, `db-005`–`db-007`, `ops-003` |
| Endpoint, live | Run 8, **412 tracks, 58 KB, ~1.04 s cold and ~0.40 s warm** |
| Full-corpus replay | 133,634 read, 133,134 accepted, 500 quarantined, 12 batches, **~9.8 s warm** (see below) |
| Migrations | Two revisions, both applied to the development database |
| New dependencies | None, in either half |

### `db-007`, as built

`completed_at` on `scenario_runs` — nullable `timestamptz`, no server default, no backfill. A free
function `complete_scenario_run` in `app/db/repository.py`, not a repository method, because every
producer of a run must set it and the scenario generator will create runs without writing
observations. It raises `LookupError` on an unknown id, since an `UPDATE` matching nothing is a
success by default. `app/replay.py` marks its run as the last statement of the `try` block.

Verified on the development database: the run predating the migration stayed null, and the new run's
`completed_at - started_at` read 9.765 s against the command's self-reported 9.75 s.

### `api-002`, as built

`GET /api/v1/operational-picture`. Serves the run **known to have completed** in preference to a more
recent unfinished one — `db-007` paying off a day after it landed — and that run's final-window
positions, one per aircraft, altitude converted from metres to feet.

**The four sections with no producer are served empty, and the detection summary is null rather than
`Low`.** `Low` is a claim about the data; null is a claim about the system, and only the second is
true. `scenario` is nullable for the same reason, which lets an empty database return a valid empty
picture rather than a 500.

**The contract violated `FR-715`/`AC-11` and this item fixed it.** `anomalyScore` and
`signalIntegrity` were rendered as `74.2%` and `0.92`. They are now `Low | Medium | High`, and
`anomalyScore` is `anomalyLevel` because it is no longer a score. The rendering primitive stays
`ui-001`'s job; this item only removed the violation.

### `db-006`, as built

`backend/tests/test_api_route_purity.py` — 13 tests over every module under `app/api/`, all by AST.
Five rules: no storage-engine import, no `app.db` import other than `repository` and `session`, no
SQL statement in a non-docstring string, no PostGIS function, no session or Engine constructed.

**It was red on arrival for a real reason.** `api-002`'s route imported `sqlalchemy.orm` to annotate
a parameter it never constructed. Fixed by naming the type once in `app/db/session.py` as
`SessionFactory`, so the API layer cannot say `sqlalchemy` at all — a fact about the import graph
rather than an argument about strings.

| Mutation | Result |
|---|---|
| A real query in the handler | 3 assertions red — the import, the statement, the constructor |
| The same text inside the module docstring | all 13 green, while `grep -c` on that file returned 1 |

The second row is the item's justification, written up in `thesis_notes.md`: a text-matching check
fails on the clearest documentation of the rule it enforces, so it does not merely fail to enforce
the property — it drives out the explanation of why the property matters. Third appearance of this
defect (`dal-004`, a `compose.yaml` test during `adp-007`, and here).

### `api-003`, as built

`src/lib/api.ts` is the only module that reaches the network; `src/hooks/useOperationalPicture.ts`
owns the 5 s poll, the fallback and the degraded flag; `App.tsx` is the seam.

**The seam claim, measured and stated correctly.** The change touched 4 files, 118 insertions, 3
deletions — of which 101 lines are the two new modules. `App.tsx` is +10 −3. The screen is +10 −1,
and *all* of it is an optional prop and a badge: **nothing about how the screen consumes its data
changed.** The earlier draft of this handoff claimed "no component was touched", which is not true;
the corrected claim is in the Phase 5 write-up.

Two behaviours are stronger than the item's literal wording, both recorded in the amended item:

- **A failed poll keeps the last real payload** and changes only the indicator. The mock is the
  fallback only while nothing real has ever arrived.
- **The app reports itself degraded from first paint**, because the mock is what is on screen then.

`no push transport anywhere in the repo` is asserted in both suites, since neither container sees the
whole repository: the frontend scans `src/` and `package.json`, the backend scans `app/` and
`pyproject.toml`. The backend half also checks for `@router.websocket`, which needs no dependency and
would pass an import-only check.

### Verified in a browser, which no test could do

| Step | Observed |
|---|---|
| Load `localhost:8080` | Renders `replay-only`, `replayed`, dashes — the real payload |
| Watch the network | 5 × `GET /api/v1/operational-picture`, all 200, through nginx |
| `docker compose stop backend` | Badge appears; the last real picture stays on screen |
| `docker compose start backend` | Badge clears on the next successful poll |

Two of those four are unreachable from the suite: that nginx proxies the versioned prefix without
rewriting it, and that the interval survives a restart rather than wedging after the first failure.

## Files in flight

Nothing in flight. The tree is clean.

- `backend/app/db/repository.py` — writes, the run lifecycle, and two reads. `db-004`'s spatial query
  lands here, and it is still the only place SQL may go.
- `docs/spec.jsonl` — nothing specified-and-unbuilt is blocking.

## Changed

Nineteen commits this session, all pushed except this handoff.

| Commits | What |
|---|---|
| `87e2484`, `29a3af8` | `db-007` written up; the corrected replay timing; the progress note republished |
| `2e129a5` … `da416ca` | `api-002`: spec amendment, tests, implementation, mutations, notes |
| `8843881`, `8032069` | handoff refresh and a second progress-note republish |
| `f775dd4` … `be562d5` | `db-006`: tests, implementation, mutations, notes |
| `961eab1` … `b1e5840` | `api-003`: spec amendment, tests, implementation, mutations, notes |
| `a5fb48f` | progress note republished for `api-003` |
| `b16e864` | `qa.md` §42 — TanStack deferred, and why health reads `unknown` |
| `7901bf7` | the Phase 5 write-up |
| `55c1454` | `qa.md` §43 — `scn-001` in plain English, and the ordering problem |

Added: `backend/app/api/v1/operational_picture.py`, `backend/app/api/v1/schemas/`,
`backend/alembic/versions/0002_scenario_run_completion.py`, three backend test files,
`frontend/src/lib/api.ts`, `frontend/src/hooks/useOperationalPicture.ts`, two frontend test files.
Modified: `app/dal/models.py` (`ScenarioRunSummary`), `app/db/repository.py`, `app/db/session.py`
(`SessionFactory`), `app/replay.py`, `app/api/v1/__init__.py`, the root `Makefile` (a read-only
`frontend/src/types` mount on `test-backend`), and on the frontend the contract type, the mock, the
screen, `App.tsx`, `src/test/setup.ts` and both existing test files.

**Outside the repo:** the progress note was republished three times to the same URL —
<https://claude.ai/code/artifact/7f3060f9-29d5-46de-b12b-eddd3824cccc>. It now carries the corrected
replay timing with a panel explaining that an earlier version of the page said fourteen seconds and
why; "Asking the store a question" (the six-section figure, the blank-versus-`Low` table, the
`FR-715` violation, the parity check, and 412 / 58 KB / 0.40 s); and "The screen stops making things
up" (why five seconds, what a failed request should show, a timeline figure with the backend stopped
mid-way, the browser checks, and the parse-versus-grep contrast). Totals read 18 of 83.

## Failed attempts

- **A mutation test reverted with `git checkout` deleted the implementation it was testing.** The
  routine is: mutate, assert the substitution applied, run, revert. It ran against an implementation
  that had not been committed, so the revert restored the version from the *test* commit and
  destroyed two files of finished work. **The dangerous part was the next mutation run, which
  produced exactly the red result it was meant to produce for entirely the wrong reason** — nothing
  was implemented — and would have been recorded as evidence had the guard assertion not failed
  first. New rule alongside "assert the mutation applied": **mutate only from a committed baseline.**
  Followed for every mutation since.
- **Testing Library's auto-cleanup was never running.** Vitest here has no `globals: true`, so
  Testing Library never registered its teardown and renders accumulated across tests in a file.
  Three new screen tests failed with "found multiple elements" — which reads as a duplicate-element
  bug in the component rather than a missing teardown in the harness. Fixed once in
  `src/test/setup.ts`. Invisible until now because that file held a single test.
- **A test constant was wrong and the implementation was right.** The metres-to-feet expectation was
  written as 18,874 from arithmetic done in my head; 5753.1 m is exactly 18,875 ft. Corrected after
  the implementation, which is a deviation from the workflow's order, and noted in the test.
- **I wrote "no component was touched" into the last handoff**, which the diff does not support: the
  screen gained a prop and a badge. The accurate claim is narrower and is now in the Phase 5
  write-up — the *data-consuming* code was untouched.
- **A mutation that did not compile proved nothing.** `new WebSocket("/live")` with the result unused
  was rejected by TypeScript before any test ran, so the first attempt measured the compiler rather
  than the check. Re-run in a form that compiles.
- **`-k` passed through `PYTEST_ARGS` was split by the shell**; Make does not re-quote, and pytest
  tried to collect a file called `or`. Run the whole file instead.
- **mypy rejected `result.rowcount`.** `Session.execute` is typed as returning `Result`, which does
  not carry it. Switched to `session.connection().execute(...)`, which returns a `CursorResult`.
- **A `?raw` glob replaced `node:fs` in a frontend test.** The first version imported `node:fs` and
  failed to compile: `@types/node` is a dev dependency but the app's TypeScript project does not
  include node types, and adding them would let application code reach for the filesystem. Vite's
  `import.meta.glob` reads the sources instead and needs no type configuration.

## The replay figure is condition-dependent

Three consecutive full replays measured **9.75, 9.64 and 10.01 s** against the 13.60 s and 14.25 s
recorded the previous session and published as "about 14 s". The counts were identical, so this is
the same work taking less time. The nameable difference is the stack: the earlier figures came from a
just-started container writing into an empty store, these from a long-running container and a
database already holding 133,134 rows. The naive expectation runs the other way, which points at the
emulated PostGIS image warming up — **a hypothesis, recorded as one.** What is safe to state is a
~40% swing with stack state against ~5% run-to-run. The batch-size comparison survives, since those
four sizes were measured together against the same state.

## Next step

Phase 7, the scenario generator. **The order within it was settled 2026-09-05 and is the reverse of
what the identifiers suggest** — the reasoning is at the head of Phase 7 in
`docs/implementation.md` and in `docs/qa.md` §43.

1. **`scn-005` — the RF sensor and channel layout.** Six to eight sensors at recorded positions,
   eight 2 MHz channels centred 1567.42–1581.42 MHz with one exactly on GNSS L1. It goes first
   because it is the only item in the phase with no dependency on the others: a fixed layout is
   configuration, with no randomness in it. Positions must be chosen so a candidate interference zone
   contains some sensors and excludes others, or `anom-005` and `anom-007` have nothing to
   discriminate.
2. **`scn-001` — seeded reproducibility**, landed with the smallest seeded emitter that has something
   to be deterministic about. It is a *property*, not a feature: proving "same seed, same stream"
   needs a stream. Both halves are required — same seed must give identical output, and **different
   seeds must not**, or the seed controls nothing. The three leaks to design against are wall-clock
   time, unseeded randomness, and process-dependent ordering; the third is the nastiest, being stable
   within a process and different across two.
3. **`scn-002` — the five scenario types**, with ground truth recorded at generation time.
4. **`adp-002` — the synthetic RF adapter**, emitting the full sensor × channel × time grid.

`scn-001` also supersedes `adp-007`'s placeholder run row and becomes the second producer that has to
set `completed_at`.

Owed, with an owner but no date:

- **Adopt TanStack Query at the Phase 3 view filter, not before.** Decided 2026-09-05 and written
  into `docs/implementation.md` at the point it becomes right: a second polled endpoint (`api-007`,
  then `api-008`) is the trigger. `src/lib/api.ts` stays the fetcher, so the swap touches the hook
  only. Rationale in `qa.md` §42 and `thesis_notes.md`.
- **`scenario.health` renders as a bare `unknown`** in the top-right of the status bar and reads as a
  fault rather than a statement. The value is correct — nothing monitors health yet — and the
  presentation is not. Deliberately left for `op-001`, which rebuilds that bar with a real
  system-health strip. More generally: **an absence is only legible when something says what is
  absent**, and this project now reports absence in three places.
- **`create_scenario_run` is still raw SQL in `app/replay.py`** while the other run-lifecycle
  operations are in the storage layer. `scn-001` will move it.
- **The parity test compares field names, not types**, with the two detection fields as the
  exception. A field that became a string on one side and stayed a number on the other would pass.
- **The frontend's structural checks scrub rather than parse**, unlike the backend's. Both were
  mutation-tested, but they are not equally strong.
- **`app/corpus/build.py` resolves `.env` from the repository root** and will break the first time
  anyone containerises the corpus build.
- **Scenario type 4 must exclude the 10 tracks carrying a natural dropout** from injection sites.
  Seven of the ten fall in the 100–300 s band the scenario injects.
- **Re-run the coverage acceptance check as originally specified** once the scenario engine exists.
- **Record whether any Phase 6 detection rule needs altitude on more than 77% of samples** — 94 of
  the 412 tracks served by the endpoint carry none, which is 22.8% against the corpus-wide 22.7%.

Open and unowned:

- **Root `make check` has still not been run in full**, though `format`, `lint`, `type-check`,
  `test-backend` and `test-frontend` were each run separately and are green.
- **`make generate` is broken** — the `pipeline` service names `app.pipeline`, which does not exist
  until `scn-003`. Carried knowingly.
- **mypy does not check `tests/`.** 18 errors when last measured, nearly all deliberate type
  violations in negative tests.
- **CI still does not exist** (`ops-002`).
- Track 0: the data-egress question (employer) and the licence-version divergence remain open.
