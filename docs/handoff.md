# Handoff

Written at the end of a working session so the next one starts with context rather than
archaeology. Overwritten each session — this is the current state, not a log. History lives in git.

**Session date:** 2026-08-28 to 2026-08-31
**Branch:** `main`, **5 commits ahead of `origin/main` — not pushed.** Working tree clean.

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
replayed aviation telemetry and synthetic RF observations fused through a Data Abstraction Layer,
deviations detected deterministically, evidence bundles turned into schema-validated,
grounding-checked AI hypotheses for analyst review. Decision support, not autonomous
decision-making.

This session closed the middle of the persistence strand: **`db-001`** (Alembic, the core schema,
and the database-backed test tier) and then **`ops-003`** (the root `Makefile` targets that make
that tier actually run in containers). `ops-003` was taken second and deliberately — without it the
containerised run reported success over a suite that silently skipped every database test. The
session also produced a plain-English progress note as a published artifact; see *Changed*.

Nothing has been written to a database yet. The schema exists and is empty; `db-003` is the item
that fills it.

## Current state

The store exists and is versioned. The repository port still has exactly one implementation, the
in-memory fake in `backend/tests/fakes.py`.

| | |
|---|---|
| Backend suite, native | **210 passed, 22 skipped, 99.84% coverage on `app/`.** Only miss is `app/corpus/extract.py:246`, pre-existing. The 22 skips are the `database`-marked tier |
| Backend suite, containerised | **232 passed** via `make test-backend`, from a *dropped* `test_em_fusion` — the target provisions it. Nothing is excluded there, which is why it is the authoritative run |
| Spec items passing | **12 of 80**: `api-001`, `adp-001`, `adp-004`, `adp-005`, `adp-006`, `dal-001`, `dal-002`, `dal-003`, `dal-004`, `db-005`, **`db-001`**, **`ops-003`** |
| Corpus | Unchanged. Box 49–54°N, 3–11°E; 133,634 rows; content checksum `7ce83881…be05` |
| Tooling | `backend/make check` green. `make migrate` verified: applies `0001_core_schema` to the running database, and a second run is a clean no-op. Root `make check` (lint, format, type-check, frontend) **still not run in full** |
| New dependencies | `alembic` 1.19.1. Added bare, not `>=`-pinned, matching the file's existing style; `uv.lock` pins it |

### `db-001`, as built

`backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/versions/0001_core_schema.py`, and
`backend/app/db/migrations.py`. 22 database-marked tests in `tests/test_db_schema.py`, 4 non-database
unit tests in `tests/test_db_migrations.py`.

**Seven tables, not six.** `quarantined_records` was added because the ERD in `em_fusion_v2.md` §9
had no home for the records `dal-002` requires — see *Failed attempts*. The others: `scenario_runs`,
`observations`, `evidence_bundles`, `anomalies`, `hypotheses`, `analyst_feedback`.

Details that will look arbitrary later:

- **`sqlalchemy.url` in `alembic.ini` is deliberately empty** (NFR-401). `env.py` falls back to
  `database_url()`, so the DSN is read from the environment in exactly one place.
- **`alembic_config()` sets an absolute `script_location`**, because the backend is run from
  `backend/`, from the repo root, and from `/app` in the container.
- **`_require_postgis()` asserts rather than creates.** `CREATE EXTENSION` needs superuser and is the
  image's job; a migration that creates it can never *fail* for its absence, which is the failure
  case `db-001` exists to guard.
- **Geometry columns are explicit DDL, not GeoAlchemy2.** That library earns its place at query time
  in `db-003`. Here it would add a dependency to hide two lines. `pyproject.toml` carries a
  `filterwarnings` entry ignoring SQLAlchemy's `Did not recognize type 'geometry'` — **remove it when
  GeoAlchemy2 lands.**
- **`hypotheses` carries `generator`/`model_id`/`generation_params`/`raw_response` from revision
  one**, plus CHECK constraints on `generator` and `confidence`. The database cannot hold a
  confidence that is not Low/Medium/High.

### `ops-003`, as built

`tests/test_ops_command_surface.py` — 27 tests parsing the root `Makefile`. Three `Makefile` changes:

- **`migrate`** — `compose run --rm backend alembic upgrade head`.
- **`db-test-create`** — idempotent by checking `pg_database` first, because `createdb` on an
  existing database exits non-zero. It creates the extension too, since the migrations assert it.
- **`test-backend`** lost `--no-deps`, gained `db-test-create` as a prerequisite, `-e
  TEST_DATABASE_URL`, and a read-only mount of the root `Makefile` at `/repo/Makefile` (Compose
  mounts only `./backend`, so the tests could not otherwise see the file they assert against — same
  pattern as `generate`'s `DATA_DIR` mount).

**The tests are structural.** They parse the file; they do not prove a command works against a
daemon. What they do prove is the narrower and more useful claim: that a target cannot *silently do
nothing*. Three absence assertions were mutation-tested — `|| true` on a recipe, a bare
`uv run pytest`, `--no-deps` restored — each turned the right test red.

## Files in flight

Nothing in flight. The tree is clean; the 5 commits are local only.

- `backend/alembic/versions/0001_core_schema.py` — complete. `db-003` reads it, does not change it.
- `backend/app/db/session.py` — unchanged this session, still complete.
- `adp-007` is still **deliberately unwritten**. It is now unblocked in principle but should wait for
  `db-003`, so the replay it commits actually persists.
- **Still no committed way to re-run the full-corpus replay.** The ~2.4 s figure and the
  133,134 / 500 counts came from an ad-hoc script in a scratch directory that is gone. That gap
  remains the whole argument for `adp-007`.

## Changed

Five commits on top of `297de4a`. **None pushed.**

| Commit | What |
|---|---|
| `2d15994` | `spec: amend db-001 — seventh table, TEST_DATABASE_URL` |
| `4f60aba` | `test: add tests for db-001` |
| `54d137b` | `feat(db-001): core schema and migrations - tests pass` |
| `23b687e` | `spec: amend ops-003 — db-test-create, drop the unbuilt omission clause` |
| `e8c87e9` | `feat(ops-003): migrate and db-test-create targets, database tier runs in containers - tests pass` |

Added: `backend/alembic.ini`, `backend/alembic/env.py`,
`backend/alembic/versions/0001_core_schema.py`, `backend/app/db/migrations.py`,
`backend/tests/test_db_schema.py`, `backend/tests/test_db_migrations.py`,
`backend/tests/test_ops_command_surface.py`. Modified: root `Makefile` (three targets),
`backend/tests/conftest.py` (the database tier: `requires_database`, `live_database_url`,
`empty_database`, `database_without_postgis`), `backend/pyproject.toml` and `uv.lock` (alembic,
`filterwarnings`, the `database` marker), `docs/spec.jsonl` (`db-001` and `ops-003` amended, both set
passing), `docs/em_fusion_v2.md` §9 (ERD gained `QUARANTINED_RECORDS`), `docs/qa.md` (§38),
`docs/thesis_notes.md` (five subsections), `docs/implementation.md` (Phase 6 ticks), `README.md`
(migrations section, database-test section, two `Makefile` targets).

**Outside the repo:** a plain-English progress note was published as an artifact —
<https://claude.ai/code/artifact/7f3060f9-29d5-46de-b12b-eddd3824cccc>. It explains the project and
everything built so far for a reader who knows none of it, with three figures (the bounding box, the
two staleness clocks, the pipeline spine). It is **updated on request, not automatically**, and
republishing to that same URL requires passing the URL. It is a companion to `thesis_notes.md`, not
a replacement: notes hold the reasoning, the artifact holds the explanation.

## Failed attempts

- **Two spec claims in `db-001` were stale before its tests were written, and both were mine.** Each
  was true when written and falsified by later work in a *different* item. Read immediately before
  writing tests, which is the only reason they were caught:
  - the six-table list, which predates `quarantined_records` existing at all;
  - the conditional coverage-omission clause, which described machinery for a module that turned out
    not to need it.
  The pattern is named in `qa.md` §38: **spec text describing the state of something outside its own
  item is a claim with no test behind it, and it decays silently.** The only mitigation found is
  procedural — re-read the item immediately before writing its tests.
- **A mutation test reported a false pass.** Black had collapsed
  `op.execute(f"CREATE INDEX ...")` onto one line, so my multi-line replacement string matched
  nothing and the GiST test "passed" against an unmutated file. Redone with
  `assert s.count(old) == 1, "MUTATION DID NOT APPLY"` first — then confirmed red. **Every mutation
  now asserts its own substitution applied before it asserts anything about the test.** A mutation
  test that does not verify the mutation is a test of nothing.
- **`test_geography_distance_works_over_the_stored_geometry` was a weak test.** It computed a
  distance between two literal points, so it would have passed against a schema with no geometry
  columns at all. Rewritten as `test_db004s_query_shape_compiles_against_the_stored_columns`, running
  `db-004`'s actual `ST_DWithin` predicate against the real columns over zero rows.
- **The ERD amendment failed on a wrong anchor.** I assumed `SCENARIO_RUNS ||--o{ OBSERVATIONS` was
  the last relationship line in `em_fusion_v2.md` §9; it was `ANOMALIES }o--|| EVIDENCE_BUNDLES`. The
  edit asserted its anchor and refused, before any write.
- **`test_database_url` in `conftest.py` would have been collected by pytest** as a test, because of
  its name. Renamed `live_database_url`.
- **The container failed with `No module named 'alembic.config'`** on a stale image — Compose
  bind-mounts source but not site-packages. Fixed with `make build-backend`. This is exactly the trap
  the root `Makefile`'s own comment documents, and I walked into it anyway.
- **I created `test_em_fusion` by hand while building `db-001`**, which made the green run depend on
  an undocumented manual step — the thing `AC-12` forbids. `db-test-create` removed it, and the proof
  was dropping the database entirely and running `make test-backend` from nothing.
- **`app/db/migrations.py` sat at 70% coverage natively**, and the specified fix was the conditional
  omission machinery. Four unit tests took it to 100% instead — path resolution and ini parsing need
  no database. **The clause was then deleted from both `db-001` and `ops-003` rather than left
  describing machinery that does not exist**, and named as returning with `db-003`. Written up in
  `thesis_notes.md`: a spec describing unbuilt machinery is worse than one that never mentioned it,
  because it reads as a completed design and survives review by being internally coherent.
- **The full-corpus replay wall time is recorded inconsistently across three documents** —
  `thesis_notes.md:1059` says **2.44 s**, `handoff.md` and `qa.md` §2246 both say **2.46 s**. The
  measuring script is gone, so neither can be checked. Not yet reconciled; see *Owed* below. This is
  a number that would otherwise have reached the dissertation twice with different values.

## Next step

1. **`db-003`** — the PostGIS `ObservationRepository`. Where the replay path first persists anything,
   and where the conditional coverage-omission rule returns. It answers the standing prediction about
   whether the port signature survived contact with a real database unchanged; the prediction on
   record is that **geometry and atomicity are the risks and identity is not.** Record the answer
   either way.
2. **`adp-007`** — `python -m app.replay` plus a `make replay` target. `ops-003` will need amending
   again, since its description enumerates the targets. Needs `PSEUDONYM_SEED` passed into the
   `pipeline`/`backend` Compose services from the host environment first, never a committed default.
3. **Phase 5** — `/api/v1/operational-picture` against the frontend contract, then swap the mock. Not
   blocked by any of the above and never was; its position here is scheduling, not dependency.

Owed, with an owner but no date:

- **Reconcile the 2.44 / 2.46 s replay figure** across `thesis_notes.md`, `qa.md` and this file, or
  strike it until `adp-007` can re-measure. Then re-record it against the PostGIS repository — the
  current number measures the reader and the DAL only; the one that will bound a scenario run
  includes persistence.
- **`compose.yaml` passes `DATABASE_URL` and nothing else** — no `env_file:`, no `PSEUDONYM_SEED` in
  any service. Harmless today; breaks `adp-007`, whose containerised replay pseudonymises at ingest
  and will fail with an error message pointing at "project configuration held outside the
  repository". Pass the seed from the host environment, never a committed default (`dal-004`).
- **Scenario type 4 must exclude the 10 tracks carrying a natural dropout** from injection sites.
  Seven of the ten fall in the 100–300 s band the scenario injects, so without the exclusion the type
  4 false-positive rate is confounded. The coverage report identifies the tracks.
- **Re-run the coverage acceptance check as originally specified** — `Normal baseline` through the
  extract — once the scenario engine exists.
- **Remove the `geometry` `filterwarnings` entry** from `backend/pyproject.toml` when GeoAlchemy2
  lands with `db-003`. A permanent warning filter hides the next unrecognised type too.
- **Record whether any Phase 6 detection rule needs altitude on more than 77% of samples**, given
  22.7% of positioned rows carry none.

Open and unowned:

- **5 commits are unpushed.**
- **Root `make check` has still not been run in full.** Only `make test-backend` was run this
  session; lint, format, type-check and the frontend suite were not exercised in containers.
- **The frontend suite was not run this session.** `pnpm test` fails on the shell's default Node 20;
  `frontend/.nvmrc` pins ≥ 22.13 and `nvm use` is required first.
- **mypy does not check `tests/`.** `mypy app/ tests/` reported 18 errors when last measured, nearly
  all from deliberate type violations in negative tests. Cost is quantified; the call is not made.
- **CI still does not exist** (`ops-002`). Until it does, a green `make check` is evidence about one
  machine at one moment.
- Track 0: the data-egress question (employer) and the licence-version divergence (shipped 2017
  `LICENSE.txt` vs the operative published terms) both remain open.
