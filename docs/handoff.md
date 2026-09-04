# Handoff

Written at the end of a working session so the next one starts with context rather than
archaeology. Overwritten each session — this is the current state, not a log. History lives in git.

**Session date:** 2026-09-04
**Branch:** `main`, **in sync with `origin/main`** apart from this handoff. Working tree clean.

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
replayed aviation telemetry and synthetic RF observations fused through a Data Abstraction Layer,
deviations detected deterministically, evidence bundles turned into schema-validated,
grounding-checked AI hypotheses for analyst review. Decision support, not autonomous
decision-making.

This session built **`db-007`**, the scenario run completion flag, ahead of Phase 5 rather than
after it. The reasoning was that a second Alembic revision is cheaper against a database nothing
reads than against one the detectors do, and the item is small.

It also produced a measurement that contradicts one already published, and a process failure in the
mutation-testing routine. Both are below.

## Current state

The pipeline is connected end to end from source to store, and a run now records whether it
finished. Nothing reads back out of the store yet — no endpoint, no detector.

| | |
|---|---|
| Backend suite, containerised | **288 passed, 99.87%** via `make test-backend`. Authoritative: nothing is excluded there |
| Spec items passing | **15 of 83** — `api-001`, `adp-001`, `adp-004`–`adp-007`, `dal-001`–`dal-004`, `db-001`, `db-003`, `db-005`, `db-007`, `ops-003` |
| Lint / types | `make lint` and `make type-check` both green |
| Full-corpus replay | 133,634 read, 133,134 accepted, 500 quarantined, 12 batches. **Timing revised — see below** |
| Migrations | Two revisions. `0002_scenario_run_completion` applied to the development database this session |
| New dependencies | None |

### `db-007`, as built

- **`backend/alembic/versions/0002_scenario_run_completion.py`** — `completed_at`, a nullable
  `timestamptz` on `scenario_runs`, no server default, no backfill.
- **`complete_scenario_run(session_factory, run_id)`** in `app/db/repository.py` — a free function,
  not a repository method, because every producer of a run must set the flag and the scenario
  generator will create runs without writing observations. Raises `LookupError` when the id matches
  no row, because an `UPDATE` matching nothing is a success by default.
- **`app/replay.py`** marks its run as the last statement of the `try` block, after every batch has
  committed.

10 tests across `test_db_schema.py`, `test_db_repository.py` and `test_replay.py` — the file-per-
module convention wins over a file-per-spec-item one. Four mutations recorded in the test files
themselves: removing the `WHERE` clause, setting the flag before the batches, backfilling in the
revision, and adding a server default. Each turns the intended tests red and no others.

One decision was not in the item as first written and was added to it before the tests: **an unknown
run id must raise.** Committed as `spec: amend db-007`.

### Verified on the development database, not only on fixtures

`make migrate` then `make replay`, against a database already holding a replay from an earlier
session:

- the pre-existing run **stayed null** — the no-backfill failure case, on real rows rather than a
  fixture;
- the new run recorded `completed_at - started_at` of **9.765 s** against the summary's
  self-reported **9.75 s**. First time the replay's own timing has been corroborated by a clock the
  application does not control.

### The replay timing figure is revised, and is condition-dependent

Three consecutive full replays measured **9.75 s, 9.64 s, 10.01 s — about 9.8 s**, against the
13.60 s and 14.25 s recorded last session and published on the progress note as "about 14 s". The
counts were identical in every run, so this is the same work taking less time.

The condition that differs and can be named: the earlier figures were taken shortly after the
database container started, against a freshly migrated empty schema; these were taken against a
long-running container and a database already holding 133,134 rows. The naive expectation runs the
other way, which points at the emulated PostGIS image warming up rather than at the data. **That is
a hypothesis and is recorded as one.** What is safe to state is that the figure varies by roughly
40% with the state of the stack — far more than the ~5% run-to-run variance measured earlier.

The batch-size comparison from last session survives: those four sizes were measured in one session
against the same warm state, so the shape holds even though the absolute values do not.

## Files in flight

Nothing in flight. The tree is clean.

- `backend/app/db/repository.py` — `db-004`'s spatial query lands here, and it is still the only
  place SQL may go.
- `docs/spec.jsonl` — `db-006` is written and **unbuilt**; read it before starting `api-002`, which
  is where it lands.

## Changed

Five commits on top of `7871acf`, **pushed**.

| Commit | What |
|---|---|
| `ebb51c0` | `spec: amend db-007 — an unknown run id must fail loudly` |
| `580d1b3` | `test: add tests for db-007` |
| `a12d7ff` | `feat(db-007): scenario run completion flag - tests pass` |
| `0dc008b` | `feat(db-007): mutation results, db-007 passes` |
| `b1a1efd` | `docs: db-007 in the notes, the revised replay timing, refresh handoff` |

Added: `backend/alembic/versions/0002_scenario_run_completion.py`. Modified:
`backend/app/db/repository.py`, `backend/app/replay.py`, the three test files, `docs/spec.jsonl`,
`docs/thesis_notes.md`, `docs/implementation.md`.

**Outside the repo:** the progress note was republished to the same URL —
<https://claude.ai/code/artifact/7f3060f9-29d5-46de-b12b-eddd3824cccc>. The wall-time figure is now
"about ten seconds" with a panel explaining that an earlier version of the page said fourteen and
why; the batch-size table gained the condition it was measured under; the partial-run bullet moved
out of the gaps list into a new section, "So which of the two are you looking at?", with a figure
contrasting a stamped run against an unstamped one; three tables in the storage list are now marked
as written to; the totals read 15 of 83.

## Failed attempts

- **A mutation test reverted with `git checkout` deleted the implementation it was testing.** The
  routine is: mutate, assert the substitution applied, run, revert. It was run against an
  implementation that had not been committed, so `git checkout <file>` restored the version from the
  *test* commit and destroyed two files of finished work. Retyping cost ten minutes. **The dangerous
  part was the next mutation run, which produced exactly the red result it was meant to produce, for
  entirely the wrong reason** — the absence of any implementation at all — and would have been
  recorded as evidence had the guard assertion not failed first. New rule alongside "assert the
  mutation applied": **mutate only from a committed baseline.**
- **A `-k` expression passed through `PYTEST_ARGS` was split by the shell.**
  `PYTEST_ARGS="... -k complete or interrupted"` reached pytest as three arguments and pytest tried
  to collect a file called `or`. Make does not re-quote. Run the whole file instead.
- **mypy rejected `result.rowcount`.** `Session.execute` is typed as returning `Result`, which does
  not carry it. Switched to `session.connection().execute(...)`, which returns a `CursorResult` —
  the same connection and the same transaction, and the same call the reflection code one function
  up already makes. No cast.
- **A number I published was wrong, for the second session running.** Last session it was an
  attribution ("5.8× the read"); this session it is the total itself. The pattern is the same both
  times: a figure measured once, under conditions that were not recorded alongside it, then quoted
  as a property of the system.

## Next step

1. **Phase 5 — `api-002`**: `/api/v1/operational-picture` returning the frontend contract's shape.
   Then `api-003`, swapping the mock in `App.tsx` for a fetch. This is also where **`db-006`** gets
   its first real test, since it needs a data-serving route to assert against.
2. **`scn-001`/`scn-002`** — the scenario generator, which supersedes `adp-007`'s placeholder run
   and becomes the second producer that has to set `completed_at`.

Owed, with an owner but no date:

- **`create_scenario_run` is still raw SQL in `app/replay.py`** while `complete_scenario_run` is in
  the storage layer. The run lifecycle is split across two modules. Left deliberately: `adp-007`
  justified the placement and `scn-001` will move it, and editing a passing item outside its own
  spec is how the drift in §38/§39 started.
- **`app/corpus/build.py` resolves `.env` from the repository root** and will break the first time
  anyone containerises the corpus build. One line, unchanged, for the same reason.
- **Scenario type 4 must exclude the 10 tracks carrying a natural dropout** from injection sites.
  Seven of the ten fall in the 100–300 s band the scenario injects.
- **Re-run the coverage acceptance check as originally specified** once the scenario engine exists.
- **Record whether any Phase 6 detection rule needs altitude on more than 77% of samples**, given
  22.7% of positioned rows carry none.

Open and unowned:

- **Root `make check` has still not been run in full.** `format`, `lint`, `type-check` and
  `test-backend` were each run separately this session and were green.
- **The frontend suite has not been run for four sessions.** `pnpm test` fails on the shell's
  default Node 20; `frontend/.nvmrc` pins ≥ 22.13 and `nvm use` is required first.
- **`make generate` is broken** — the `pipeline` service's command names `app.pipeline`, which does
  not exist until `scn-003`. Carried knowingly; recorded in `ops-003`'s own text.
- **mypy does not check `tests/`.** 18 errors when last measured, nearly all deliberate type
  violations in negative tests.
- **CI still does not exist** (`ops-002`).
- Track 0: the data-egress question (employer) and the licence-version divergence both remain open.
