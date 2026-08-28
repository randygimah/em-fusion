# Handoff

Written at the end of a working session so the next one starts with context rather than
archaeology. Overwritten each session — this is the current state, not a log. History lives in git.

**Session date:** 2026-08-26 to 2026-08-28
**Branch:** `main`, **8 commits ahead of `origin/main` — not pushed.** Working tree clean.

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
replayed aviation telemetry and synthetic RF observations fused through a Data Abstraction Layer,
deviations detected deterministically, evidence bundles turned into schema-validated,
grounding-checked AI hypotheses for analyst review. Decision support, not autonomous
decision-making.

This session opened the persistence strand. It began as a request to clarify `db-005` and `db-001`
before building either, and that clarification was worth more than the code: it found that the
previous handoff had **conflated `db-001` with `db-003`**, and it surfaced four decisions that no
document had settled. `db-005` was then built and passes. Nothing has been written to a database
yet — `db-001` is the next item and is where a live PostGIS first becomes necessary.

## Current state

The backend can now reach a database. It has not yet been asked to store anything: the repository
port still has one implementation, the in-memory fake in `backend/tests/fakes.py`.

| | |
|---|---|
| Backend suite | **179 passed, 99.84% coverage on `app/`.** `app/db/session.py` and `app/main.py` both 100%. Only miss is `app/corpus/extract.py:246`, pre-existing |
| Spec items passing | **10 of 80**: `api-001`, `adp-001`, `adp-004`, `adp-005`, `adp-006`, `dal-001`, `dal-002`, `dal-003`, `dal-004`, **`db-005`** |
| Corpus | Unchanged. Box 49–54°N, 3–11°E; 133,634 rows; content checksum `7ce83881…be05` |
| Tooling | `backend/make check` green. Root **`make test-backend` run and agrees** — 179 passed, 99.84%, so the two surfaces have not drifted. Root `make check` (lint, format, type-check, frontend) still not run |
| New dependencies | `sqlalchemy` 2.0.52, `psycopg[binary]` 3.3.4. Added bare, not `>=`-pinned, matching the file's existing style; `uv.lock` pins them |

### The persistence strand, as now sequenced

**`db-005` → `db-001` → `db-003`**, three items, not two. The previous handoff said `db-001` was the
point "at which the PostGIS implementation of `ObservationRepository` lands". That was wrong:
`db-001`'s description is schema and migrations only, and the repository is `db-003`. They fail
differently and at different times — a wrong column type fails at migration time against an empty
database, a wrong repository fails at write time against a populated one — so fused into one item a
red test cannot say which is broken.

### Decisions the next session should not re-litigate

All four in `docs/thesis_notes.md` with their rejected alternatives; explained in `docs/qa.md` §34.

- **Alembic**, revisions hand-written, autogenerate **off** — it does not understand PostGIS geometry
  columns. Its version table *is* `db-001`'s "apply twice from empty must not error" failure case, so
  ordered SQL files would mean hand-rolling and testing what the dependency already provides.
- **A disposable `test_em_fusion` database in the existing `postgis` service**, DB tests marked and
  skipped when `DATABASE_URL` is absent. Not testcontainers: §18 measured this image at ~2.5× slower
  under amd64 emulation, paid on every run.
- **`geometry(…, 4326)` with `::geography` casts at query time**, GiST-indexed. `db-004` requires the
  distance to be PostGIS's arithmetic rather than the application's, and a cast satisfies that while
  keeping the full geometry function set for Phase 6 clustering.
- **The coverage omission is conditional on database availability, not on which Makefile was typed.**
  Stated that second way it would make the two surfaces enforce two different rules — the drift the
  root `Makefile`'s own `PYTEST_ARGS` comment exists to prevent. One rule: measure over what was
  exercisable here. The containerised run is authoritative because nothing is excluded there.
- **`app/main.py` will not call `load_dotenv`** (decided 2026-08-28, `qa.md` §37). Compose supplies
  `DATABASE_URL` with a `:-` default, so `make up` needs no `.env` at all. The accepted cost: native
  `uvicorn` permanently requires `uv run --env-file .env` or an exported variable, which is
  documented in `README.md` rather than fixed in code, and it makes `app.main` behave differently
  from `app.corpus.build`, which does load `.env`.

### `db-005`, as built

`app/db/session.py` — `database_url()`, `init_engine()`, `get_engine()`, `get_sessionmaker()`,
`dispose_engine()`, `get_session()`, plus `MissingDatabaseUrlError` and `EngineNotInitialisedError`.
`app/main.py`'s lifespan builds the Engine and disposes it in a `finally`. `tests/conftest.py` is new
and sets `DATABASE_URL` for every test to `postgresql+psycopg://nobody@127.0.0.1:1/none` — an address
where nothing listens, which is a *stricter* fixture than a working one: anything that connects
eagerly during startup fails the suite instead of quietly acquiring a Docker dependency.

Three deliberate calls, in case they look arbitrary later:

- **`init_engine()` is idempotent rather than raising on a second call**, so a test client entered
  twice reuses the pool instead of leaking one.
- **`get_engine()` never lazily builds.** It raises. A caller reaching for the Engine outside the
  lifespan gets an error rather than a second pool nobody knows about. This is also why `lru_cache`
  was rejected when asked about (`qa.md` §36) — it would return an Engine where two tests assert a
  raise.
- **The session dependency closes but does not commit.** Committing at the request boundary would
  make the request the unit of work and split `dal-002`'s "observations and quarantine records
  together, or neither" guarantee in two, with no visible failure.

## Files in flight

Nothing in flight. The tree is clean; the 8 commits are local only.

- `backend/app/db/session.py` — complete. `db-001` adds `app/db/` siblings but will not change it.
- `docs/spec.jsonl` — `db-001` and `ops-003` **amended this session but not yet built**. Read
  `db-001`'s new text before starting: it now names Alembic, the column types, the test tier, and
  five failure cases where it had two.
- `adp-007` is still **deliberately unwritten**, still deferred until after `db-001`.
- **Still no committed way to re-run the full-corpus replay.** The 2.46 s figure and the 133,134 /
  500 counts came from an ad-hoc script in a scratch directory that is gone. That gap remains the
  whole argument for `adp-007`.

## Changed

Eight commits on top of `3433dfa`. **None pushed.**

| Commit | What |
|---|---|
| `ac120ba` | `docs: record the db-005/db-001 clarification and the four persistence decisions` |
| `6889e84` | `spec: amend db-001, ops-003` |
| `6446cd5` | `docs: record the coverage-exclusion refinement` |
| `b6b44fb` | `test: add tests for db-005` |
| `4f177a8` | `feat(db-005): engine, session, and configuration - tests pass` |
| `23f96a6` | `docs: record what the db-005 stub run exposed about proving test failure` |
| `8c94b7c` | `docs: correct the native-run env instructions, add qa 36` |
| `c0dfe82` | `docs: qa 37 — no load_dotenv in main.py, and the seed gap it leaves for adp-007` |

Added: `backend/app/db/{__init__,session}.py`, `backend/tests/test_db_session.py` (21 tests),
`backend/tests/conftest.py`. Modified: `app/main.py` (lifespan), `tests/fakes.py` (docstring said the
PostGIS implementation lands with `db-001`; it is `db-003`), `backend/pyproject.toml` and `uv.lock`
(two dependencies), `docs/spec.jsonl` (`db-001` and `ops-003` amended, `db-005` set passing),
`docs/qa.md` (§34–§37, seven glossary terms), `docs/thesis_notes.md` (three subsections),
`docs/implementation.md` (Phase 6 first item), `README.md` (native-run env instructions, twice).

## Failed attempts

- **The previous handoff's Next step was wrong, and it was my own claim.** It said `db-001` is where
  the PostGIS `ObservationRepository` lands. It is not — that is `db-003`. Two sessions' worth of
  "next step" pointed at an item that does not contain the thing it promised. Corrected in the spec
  text and in `qa.md` §34, not just here.
- **The first red run proved almost nothing.** Running the 20 new tests against a non-existent module
  produced a *single collection error*. That satisfies "the tests fail" while establishing nothing,
  because a collection error is produced by every test in the file regardless of what it asserts. A
  `NotImplementedError` stub was written, run, and deleted before committing. **18 failed, 4 passed** —
  and each of the three reasons was a real defect:
  - **`NotImplementedError` subclasses `RuntimeError`**, so `pytest.raises(RuntimeError)` caught the
    stub itself. Any "fails loudly" test written against the base class proves nothing. Fixed with
    named types, still `RuntimeError` subclasses so the loudness guarantee is unchanged.
  - **A test calling `dispose_engine()` twice and asserting no exception** is satisfied by `pass`.
    Rewritten to exercise a full construct-and-dispose cycle first.
  - **Two structural guards passed vacuously** — they assert an *absence* (no `Engine` built outside
    `app/db/`, no DSN literal under `app/`) and cannot fail until the violation exists. Not deleted:
    **mutation-tested**, violation introduced, confirmed red, reverted. A third mutation put a DSN in
    a *docstring* and confirmed the test stayed green, because the adapter's import check broke
    exactly that way last session. Results are in the tests' own docstrings with the date.
  - The generalisable finding, written up in `thesis_notes.md`: *"the tests failed"* is three
    different facts — implementation absent, test wrong, or module wouldn't load — and only a stub run
    tells them apart.
- **`tests/conftest.py` broke a test the moment it landed.** `test_missing_database_url_fails_loudly`
  assumed a clean environment; once the autouse fixture set `DATABASE_URL` for every test, it was
  asserting against the fixture rather than against absence. Fixed with an explicit
  `monkeypatch.delenv`. The fixture working as intended, but it went red first.
- **Deviation: one test written after the implementation.** Coverage showed `get_sessionmaker()`'s
  uninitialised branch untested — asserted for `get_engine` and not its sibling. Test added
  afterwards to close it, and the comment in the test says so.
- **I wrote a README instruction that does not work, and a user question caught it.** The native-run
  block said `cp .env.example .env && uvicorn app.main:app`, which implies the file is read. It is
  not: `load_dotenv` is called only in `app/corpus/build.py`, never in `app/main.py`, so a bare
  `uvicorn` fails at startup *with a correct `.env` sitting beside it*, and the error points at the
  environment rather than the file. Corrected to `uv run --env-file .env`. **The lesson is that the
  documentation was written from the design rather than from running it.**
- **`uv add` wrote `>=`-pinned dependencies** (`sqlalchemy>=2.0.52`) into a file whose every other
  entry is a bare name relying on `uv.lock` for pinning. Normalised by hand and re-locked. Worth
  knowing the tool does not match the file's convention.
- **`timeout` does not exist on macOS**, so a guarded command run failed outright. Trivial, but it
  cost a round trip.

## Next step

1. **`db-001`** — read its amended spec text first; it changed substantially this session. Three
   things land together: Alembic scaffolding plus a first revision creating all six tables; the
   disposable-database test tier with its marker; and the conditional coverage rule. Two knock-ons
   are already specified in `ops-003` and must not be forgotten: a **`migrate`** target, and
   **`test-backend` losing `--no-deps`** (it currently starts the backend container alone, so every
   database test would skip while the target reported success).
   Note that the first revision must create `evidence_bundles`, `hypotheses`, `analyst_feedback` and
   `scenario_runs` even though nothing will read them for several phases — `raw_response` is not
   retrofittable after a campaign has run.
2. **`db-003`** — the PostGIS `ObservationRepository`. Answers the standing prediction about the port
   signature, and is where the replay path first persists anything.
3. **`adp-007`** — `python -m app.replay` and a `make replay` target. Still deferred until there is a
   real repository to replay into.
4. **Phase 5** — `/api/v1/operational-picture` against the frontend contract, then swap the mock. Not
   blocked by any of the above and never was; its position here is scheduling, not dependency.

Owed, with an owner but no date:

- **`compose.yaml` passes `DATABASE_URL` and nothing else** — no `env_file:`, no `PSEUDONYM_SEED` in
  any service. Harmless today; breaks `adp-007`, whose containerised replay pseudonymises at ingest
  and will fail with an error message pointing at "project configuration held outside the
  repository". Pass the seed from the host environment, never a committed default (`dal-004`).
- **Scenario type 4 must exclude the 10 tracks carrying a natural dropout** from injection sites.
  Seven of the ten fall in the 100–300 s band the scenario injects, so without the exclusion the type
  4 false-positive rate is confounded. The coverage report identifies the tracks.
- **Re-run the coverage acceptance check as originally specified** — `Normal baseline` through the
  extract — once the scenario engine exists.
- **Record whether the repository port's signature survived the PostgreSQL implementation
  unchanged**, and if not, which of geometry, identity, or atomicity was got wrong. The prediction on
  record is that geometry and atomicity are the risks and identity is not. This is `db-003`'s to
  answer, not `db-001`'s.
- **Re-record the 2.46 s replay figure against the PostGIS repository.** The current number measures
  the reader and the DAL only; the one that will bound a scenario run includes persistence.
- **Record whether any Phase 6 detection rule needs altitude on more than 77% of samples**, given
  22.7% of positioned rows carry none.

Open and unowned:

- **8 commits are unpushed.** Local and remote `main` are out of sync for the first time in several
  sessions.
- **Root `make check` has still not been run in full.** Only `make test-backend` was run this
  session; lint, format, type-check and the frontend suite were not exercised in containers.
- **mypy does not check `tests/`.** `mypy app/ tests/` reported 18 errors when last measured, nearly
  all from deliberate type violations in negative tests. Cost is quantified; the call is not made.
- **CI still does not exist** (`ops-002`). Until it does, a green `make check` is evidence about one
  machine at one moment. `ops-003` remains `passes: false` and now has more in its description to
  satisfy.
- Track 0: the data-egress question (employer) and the licence-version divergence (shipped 2017
  `LICENSE.txt` vs the operative published terms) both remain open.
