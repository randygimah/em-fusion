# Handoff

Written at the end of a working session so the next one starts with context rather than
archaeology. Overwritten each session — this is the current state, not a log. History lives in git.

**Session date:** 2026-09-04 to 2026-09-05
**Branch:** `main`, **9 commits ahead of `origin/main`.** Working tree clean.

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
replayed aviation telemetry and synthetic RF observations fused through a Data Abstraction Layer,
deviations detected deterministically, evidence bundles turned into schema-validated,
grounding-checked AI hypotheses for analyst review. Decision support, not autonomous
decision-making.

This session built **`db-007`** (the run completion flag), **`api-002`** (the operational picture
endpoint), **`db-006`** (nothing in the API layer touches storage directly) and **`api-003`**
(the dashboard polls that endpoint). **Phase 5 is complete: 8 of 8 items, nothing open.** The
loop is closed — an hour of archived air traffic goes in by `make replay` and comes out on a
screen in a browser, with no mock in the path. The store now has a reader as well as a writer: an hour of archived air traffic
goes in by `make replay` and comes back out as a served payload.

## Current state

| | |
|---|---|
| Backend suite | **340 passed, 99.89%** via `make test-backend` |
| Frontend suite | **23 passed** via `make test-frontend`, in its container |
| Lint / types | `make lint` and `make type-check` green |
| Spec items passing | **18 of 83** — `api-001`–`api-003`, `adp-001`, `adp-004`–`adp-007`, `dal-001`–`dal-004`, `db-001`, `db-003`, `db-005`, `db-006`, `db-007`, `ops-003` |
| Endpoint, live | Run 8, **412 tracks, 58 KB, ~1.04 s cold and ~0.40 s warm** over three calls |
| Migrations | Two revisions, both applied to the development database |
| New dependencies | None, in either half |

### `db-007`, as built

`completed_at` on `scenario_runs` — nullable `timestamptz`, no server default, no backfill. A free
function `complete_scenario_run` in `app/db/repository.py`, not a repository method, because every
producer of a run must set it and `scn-001`'s generator will create runs without writing
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
true. `scenario` is nullable for the same reason, which is what lets an empty database return a valid
empty picture rather than a 500.

**The contract violated `FR-715`/`AC-11` and this item fixed it.** `anomalyScore: number` and
`signalIntegrity: number` were rendered as `74.2%` and `0.92`. They are now `Low | Medium | High`,
and `anomalyScore` is `anomalyLevel` because it is no longer a score. The rendering primitive stays
`ui-001`'s job; this item only removed the violation.

Four mutations recorded, each turning the intended tests red and no others: a `ground_truth` field on
the run summary, a field added to the TypeScript contract alone, the ordinary "most recent run"
query, and the percentage sign restored to the screen.

### `db-006`, as built

`backend/tests/test_api_route_purity.py` — 13 tests over every module under `app/api/`, all by AST.
Five rules: no storage-engine import, no `app.db` import other than `repository` and `session`, no
SQL statement in a non-docstring string, no PostGIS function, no session or Engine constructed.

**It was red on arrival for a real reason.** `api-002`'s route imported `sqlalchemy.orm` to annotate
a parameter it never constructed. Fixed by naming the type once in `app/db/session.py` as
`SessionFactory`, which leaves the API layer unable to say `sqlalchemy` at all — a fact about the
import graph rather than an argument about strings.

Mutation-tested both ways, as the item requires:

| Mutation | Result |
|---|---|
| A real query in the handler | 3 assertions red — the import, the statement, the constructor |
| The same text inside the module docstring | all 13 green, while `grep -c` on that file returned 1 |

The second row is the item's whole justification, written up in `thesis_notes.md`: a text-matching
check fails on the clearest documentation of the rule it enforces, so it does not merely fail to
enforce the property — it drives out the explanation of why the property matters. Third appearance of
this defect (`dal-004`, a `compose.yaml` test during `adp-007`, and here).

### `api-003`, as built

`src/lib/api.ts` is the only module that reaches the network; `src/hooks/useOperationalPicture.ts`
owns the 5 s poll, the fallback and the degraded flag; `App.tsx` was the entire change on the screen
side — **no component was touched**, which is the contract-first structure paying off exactly as it
was designed to.

Two behaviours are stronger than the item's literal wording, and both are recorded in the amended
item and in `thesis_notes.md`:

- **A failed poll keeps the last real payload** and changes only the indicator. The mock is the
  fallback only while nothing real has ever arrived. Reverting measured data to invented data on a
  network blip is a downgrade in honesty as well as usefulness.
- **The app reports itself degraded from first paint**, because the mock is what is on screen at that
  moment.

`no push transport anywhere in the repo` is asserted in both suites, since neither container can see
the whole repository: the frontend scans `src/` and `package.json`, the backend scans `app/` and
`pyproject.toml`. The backend half also checks for `@router.websocket`, which needs no dependency and
would therefore pass an import-only check.

### Verified in a browser, which no test could do

Every polling test mocks `fetch`. Against the running stack, in Chrome:

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

- `backend/app/db/repository.py` — now holds writes, the run lifecycle, and two reads. `db-004`'s
  spatial query lands here and it is still the only place SQL may go.
- `docs/spec.jsonl` — nothing specified-and-unbuilt is blocking.

## Changed

Seven commits on top of the last push. `29a3af8` (the progress-note republish and handoff catch-up) and this handoff bracket the five below.

| Commit | What |
|---|---|
| `2e129a5` | `spec: amend api-002 — band the detection scores, say what is served` |
| `f1de2a9` | `test: add tests for api-002` |
| `c653a63` | `feat(api-002): operational picture endpoint - tests pass` |
| `0d7905b` | `feat(api-002): mutation results, api-002 passes` |
| `da416ca` | `docs: api-002 in the notes, qa 41, Phase 5 checklist` |
| `700bac2` | `docs: refresh handoff for db-007 and api-002` |
| `8032069` | `docs: progress note republished for api-002` |
| `f775dd4` | `test: add tests for db-006` |
| `9a509a6` | `feat(db-006): route modules name no storage engine - tests pass` |
| `60b421b` | `feat(db-006): mutation results, db-006 passes` |
| `424283e` | `docs: db-006 in the notes, refresh handoff` |
| `961eab1` | `spec: amend api-003 — placement, interval, degraded from first paint` |
| `06b964f` | `test: add tests for api-003` |
| `c5a1525` | `feat(api-003): poll the endpoint, fall back visibly - tests pass` |
| `650c7bd` | `feat(api-003): mutation results, api-003 passes` |

**Outside the repo:** the progress note was republished to the same URL —
<https://claude.ai/code/artifact/7f3060f9-29d5-46de-b12b-eddd3824cccc>. New section, "The screen
stops making things up": why five seconds, the three-row table of what a failed request could show
and which is honest, a timeline figure of eight polls with the backend stopped in the middle, the
by-hand browser checks, and a subsection on the rule the machine can now check (the parse-versus-grep
contrast from `db-006`). The spine's lede now explains that the pipeline's two ends meet around a
missing middle; the analyst stage reads "One of three, live"; totals read 18 of 83.

**Outside the repo:** the progress note was republished to the same URL —
<https://claude.ai/code/artifact/7f3060f9-29d5-46de-b12b-eddd3824cccc>. It gained a section,
"Asking the store a question": the six-section figure showing two real and four empty, why serving
the mock for the empty four was refused, the blank-versus-`Low` table, the `FR-715` violation and
the compiler error that found it, the parity check in both directions, and the measured
412 / 58 KB / 0.40 s. The spine's store stage now says it is read as well as written, the analyst
stage says the screen has not been pointed at the endpoint yet, and the totals read 16 of 83.

Added: `backend/app/api/v1/operational_picture.py`, `backend/app/api/v1/schemas/`,
`backend/tests/test_api_operational_picture.py`,
`backend/alembic/versions/0002_scenario_run_completion.py`. Modified: `app/dal/models.py`
(`ScenarioRunSummary`), `app/db/repository.py`, `app/replay.py`, `app/api/v1/__init__.py`, the root
`Makefile` (a read-only `frontend/src/types` mount on `test-backend`), and on the frontend the
contract type, the mock, the screen, `src/test/setup.ts` and both test files.

## Failed attempts

- **A mutation test reverted with `git checkout` deleted the implementation it was testing.** The
  routine is: mutate, assert the substitution applied, run, revert. It ran against an implementation
  that had not been committed, so the revert restored the version from the *test* commit and
  destroyed two files of finished work. **The dangerous part was the next mutation run, which
  produced exactly the red result it was meant to produce for entirely the wrong reason** — nothing
  was implemented — and would have been recorded as evidence had the guard assertion not failed
  first. New rule alongside "assert the mutation applied": **mutate only from a committed baseline.**
  Followed for `api-002`'s four mutations.
- **Testing Library's auto-cleanup was never running.** Vitest here has no `globals: true`, so
  Testing Library never registered its teardown, and renders accumulated across tests in a file.
  Three of the new screen tests failed with "found multiple elements" — which reads as a duplicate
  element bug in the component rather than as a missing teardown in the harness. Fixed once in
  `src/test/setup.ts`. It had been invisible because the file previously held a single test.
- **A test constant was wrong and the implementation was right.** The metres-to-feet expectation was
  written as 18,874 from arithmetic done in my head; 5753.1 m is exactly 18,875 ft. Corrected after
  the implementation, which is a deviation from the workflow's order, and it is noted in the test.
- **`-k` passed through `PYTEST_ARGS` was split by the shell**; Make does not re-quote, and pytest
  tried to collect a file called `or`. Run the whole file instead.
- **mypy rejected `result.rowcount`.** `Session.execute` is typed as returning `Result`, which does
  not carry it. Switched to `session.connection().execute(...)`, which returns a `CursorResult`.
- **The replay timing figure I published was wrong.** See below — recorded here because it is the
  second session running in which a number I wrote down had to be corrected.

## The replay figure is condition-dependent

Three consecutive full replays measured **9.75, 9.64 and 10.01 s** against the 13.60 s and 14.25 s
recorded last session and published as "about 14 s". The counts were identical, so this is the same
work taking less time. The nameable difference is the stack: the earlier figures came from a
just-started container writing into an empty store, these from a long-running container and a
database already holding 133,134 rows. The naive expectation runs the other way, which points at the
emulated PostGIS image warming up — **a hypothesis, recorded as one.** What is safe to state is a
~40% swing with stack state against ~5% run-to-run. The batch-size comparison survives, since those
four were measured together against the same state.

## Next step

1. **`scn-001`/`scn-002`** — the scenario generator, which supersedes `adp-007`'s placeholder run and
   becomes the second producer that has to set `completed_at`.

Owed, with an owner but no date:

- **`create_scenario_run` is still raw SQL in `app/replay.py`** while the other three run-lifecycle
  operations are in the storage layer. `scn-001` will move it; editing a passing item outside its own
  spec is how the drift in §38/§39 started.
- **The parity test compares field names, not types**, with the two detection fields as the
  exception. A field that became a string on one side and stayed a number on the other would pass.
  Recorded as a limitation in `qa.md` §41.
- **`app/corpus/build.py` resolves `.env` from the repository root** and will break the first time
  anyone containerises the corpus build.
- **Scenario type 4 must exclude the 10 tracks carrying a natural dropout** from injection sites.
- **Re-run the coverage acceptance check as originally specified** once the scenario engine exists.
- **Record whether any Phase 6 detection rule needs altitude on more than 77% of samples** — 94 of
  the 412 tracks served by the endpoint carry none, which is 22.8% against the corpus-wide 22.7%.

Open and unowned:

- **9 commits unpushed.**
- **Root `make check` has still not been run in full**, though `format`, `lint`, `type-check`,
  `test-backend` and `test-frontend` were each run separately and are green.
- **`make generate` is broken** — the `pipeline` service names `app.pipeline`, which does not exist
  until `scn-003`. Carried knowingly.
- **mypy does not check `tests/`.** 18 errors when last measured, nearly all deliberate type
  violations in negative tests.
- **CI still does not exist** (`ops-002`).
- Track 0: the data-egress question (employer) and the licence-version divergence remain open.
