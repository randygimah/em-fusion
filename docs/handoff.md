# Handoff

Written at the end of a working session so the next one starts with context rather than
archaeology. Overwritten each session — this is the current state, not a log. History lives in git.

**Session date:** 2026-09-02 to 2026-09-04
**Branch:** `main`, **4 commits ahead of `origin/main` — not pushed.** Working tree clean.

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
replayed aviation telemetry and synthetic RF observations fused through a Data Abstraction Layer,
deviations detected deterministically, evidence bundles turned into schema-validated,
grounding-checked AI hypotheses for analyst review. Decision support, not autonomous
decision-making.

This session finished the persistence strand and connected it to an operator. **`db-003`** put the
PostGIS implementation behind the DAL's repository port; **`adp-007`** put a command in front of the
whole path. Between them, an hour of archived air traffic now goes from a file on disk to 133,134
rows in PostGIS in about fourteen seconds, reproducibly, by typing `make replay`.

`db-003` also answered the standing prediction about the port signature, and `adp-007` re-took the
corpus timing figure that had been unreproducible for a month.

## Current state

The pipeline is connected end to end from source to store. Nothing reads back out of the store yet —
no endpoint, no detector.

| | |
|---|---|
| Backend suite, native | **237 passed, 41 skipped, 96.66%.** The 41 skips are the `database` tier |
| Backend suite, containerised | **278 passed, 99.87%** via `make test-backend`. Authoritative: nothing is excluded there |
| Spec items passing | **14 of 83**: `api-001`, `adp-001`, `adp-004`, `adp-005`, `adp-006`, **`adp-007`**, `dal-001`, `dal-002`, `dal-003`, `dal-004`, `db-001`, **`db-003`**, `db-005`, `ops-003` |
| Full-corpus replay | 133,634 read, 133,134 accepted, 500 quarantined, 12 batches, **~14 s**. Cross-checks reproduced in the database: 30,276 without altitude, 948 distinct aircraft, all SRID 4326, zero rows mentioning `icao24` or `callsign` |
| Corpus | Unchanged. Box 49–54°N, 3–11°E; 133,634 rows; content checksum `7ce83881…be05` |
| New dependencies | `geoalchemy2`. Added bare, matching the file's style; `uv.lock` pins it |
| Removed | The `geometry` `filterwarnings` entry in `pyproject.toml`, in the same change that added GeoAlchemy2 |

### The spec grew by two items

- **`db-006` (new, unbuilt).** `db-003`'s description turned out to specify a *route-handler* rule —
  no SQL, no session, no spatial logic in handlers — while every planning document used `db-003` to
  mean the PostGIS repository. FR-904 is one sentence with a semicolon; the item was split at it.
  `db-006` is scheduled with `api-002`, because it cannot be proved before a data-serving route
  exists and would otherwise assert vacuously over an empty set of modules.
- **`adp-007` (new, now passing).** It had been referenced in four places for a month and never
  written into `spec.jsonl`.

### `db-003`, as built

`app/db/repository.py` — `PostgisObservationRepository`, taking a `sessionmaker`. **The port
signature did not change.** No session, no ORM model, no WKT/WKB string, no caller-supplied key
crossed it. Three structural tests hold that shape, each mutation-tested.

The prediction on record — *geometry and atomicity are the risks, identity is not* — named the right
risks and overstated both. Geometry resolved one level down, inside the repository; atomicity
resolved because `dal-002` had already required one call carrying both collections, which is what
gave the implementation a transaction to own. **The honest reading is not "the design survived
contact with reality" but "the guarantee was written down early, so the implementation had somewhere
to put it".** In `thesis_notes.md` in that weaker form.

Two decisions worth not re-litigating:

- **The schema is reflected, not redeclared.** The migration stays the single source of truth; a
  second declaration here would be a copy that drifts. This is also what GeoAlchemy2 is *for*: the
  warning `db-001` suppressed was reflection failing, so the dependency and the removal of the
  filter are the same change.
- **Geometry is built as EWKT** (`WKTElement`) rather than cast in SQL, so a point cannot be
  inserted with the SRID unset — and an unset SRID is 0, over which `db-004`'s `ST_DWithin` would
  answer in degrees.

### `adp-007`, as built

`app/replay.py` — `build_parser`, `windows`, `create_scenario_run`, `replay`, `main`. Plus a `make
replay` target and `PSEUDONYM_SEED` in `compose.yaml`. 24 tests in `tests/test_replay.py`.

Four decisions were fixed *before* implementation and are recorded in the item itself:

1. **Replay creates its own `scenario_runs` row**, `scenario_type='replay-only'`, seed 0, null
   ground truth. `observations` has a NOT NULL FK and no generator exists; `scn-001` supersedes it,
   and the placeholder type is what makes those rows findable.
2. **The unit of work is one window, not one run** — a deliberate weakening of `dal-002` at run
   scale, held in place by a test so strengthening it later fails rather than passes.
3. **It loads `.env`**, following `app/corpus/build.py` rather than `app/main.py`.
4. ~~`${PSEUDONYM_SEED:?}`~~ — **reversed during implementation, see *Failed attempts*.**

## Files in flight

Nothing in flight. The tree is clean; the 4 commits are local only.

- `backend/app/replay.py` — complete. `scn-001` will replace its placeholder run row, not the module.
- `backend/app/db/repository.py` — complete. `db-004`'s spatial query lands here, and it is the only
  place SQL may go.
- `docs/spec.jsonl` — `db-006` is written and **unbuilt**; read it before starting `api-002`, which
  is where it lands.

## Changed

Four commits on top of `5f7f0f8`. **None pushed.**

| Commit | What |
|---|---|
| `d715b5d` | `spec: add adp-007, amend ops-003 for the replay target` |
| `78aae11` | `test: add tests for adp-007` |
| `42e1d81` | `feat(adp-007): replay entrypoint, corpus into PostGIS in 14.25 s - tests pass` |
| `371c9a3` | `docs: qa 40, correct the replay measurement, refresh handoff` |

Earlier this session, already pushed: the `db-003` split and implementation, the `CLAUDE.md`
progress-note convention, and the handoff refresh.

Added: `backend/app/replay.py`, `backend/tests/test_replay.py`. Modified: `compose.yaml`
(`PSEUDONYM_SEED` on `backend` and `pipeline`), root `Makefile` (`replay`, `REPLAY_ARGS`, and a
read-only `compose.yaml` mount on `test-backend`), `backend/tests/test_ops_command_surface.py`
(`replay` in the enumerated targets), `docs/spec.jsonl`, `docs/thesis_notes.md`, `docs/qa.md`,
`docs/implementation.md`, `CLAUDE.md` (repo map refreshed — it still called the backend "a minimal
FastAPI skeleton" and listed none of `app/dal/`, `app/db/`, `app/adapters/`, `app/corpus/`).

**Outside the repo:** the progress note was updated twice —
<https://claude.ai/code/artifact/7f3060f9-29d5-46de-b12b-eddd3824cccc>. It now carries a section on
the port that was designed before the database existed, and one on the replay measurement with a
figure showing the twelve batches. `CLAUDE.md` gained a **Progress Note** section defining what goes
in it and how to republish to the same URL.

## Failed attempts

- **I approved-and-then-reversed one of `adp-007`'s four fixed decisions, and only found out by
  running it.** The item specified Compose's required-variable form, `${PSEUDONYM_SEED:?}`, so an
  unset seed would fail on the host. **Compose interpolates the whole file for every command
  regardless of profile**, so that makes `up`, `migrate`, `test` and `demo` all demand a seed only
  `replay` needs — and `make demo` on a clean machine is `AC-12`. Verified: with the seed unset,
  `docker compose config` itself exits non-zero. Replaced with plain `${PSEUDONYM_SEED}`; the loud
  failure moved to `Pseudonymiser.from_environment`, which raises before anything is written.
- **Two defects reached production that no test could have caught**, both found on the first real
  `make replay`. They share a shape: *the place the code runs is not the place the tests describe.*
  - `DEFAULT_ENV_FILE` was anchored to the repository root — correct natively, resolving to
    `/backend/.env` in a container where Compose mounts `./backend` as `/app` and nothing above it
    exists. **`app/corpus/build.py` still has this defect** and escapes it only by never being
    containerised.
  - Compose passes an unset host variable through as **an empty string**, and
    `load_dotenv(override=False)` treats present-but-empty as present — so `/app/.env` was skipped
    and the replay failed reporting a missing seed with the seed in a mounted file. Every test
    either set the variable or deleted it; **none set it to empty, which is the one state the
    platform actually produces.**
- **I overstated a measurement, and a review question caught it.** `thesis_notes.md` and the progress
  note both said persistence costs "5.8x" reading and normalising. The ~2.4 s baseline was native and
  in-memory; the new figure is a container against an emulated database. The gap is *mostly*
  persistence, but the two differ in more than one variable and it should not have been reported as
  an attribution. Corrected, along with the precision: run-to-run variance is ~5%, so the figure is
  "about 14 s", not 14.25 s.
- **I assumed the twelve-batch replay paid for eleven redundant file scans.** `read_window` really
  does walk the whole extract per window. Measured: 1 batch 13.99 s, 4 batches 12.69 s, 12 batches
  13.60 s, 60 batches 23.17 s. A full scan is ~0.16 s and is swamped by per-row DAL work until about
  sixty batches. The inefficiency is real and visible in the source; optimising it at current batch
  sizes would have bought nothing.
- **The Black-reflow trap, again.** An edit anchored on a multi-line `next(...)` in the test file
  failed because Black had collapsed it onto one line — the same failure as the `db-001` mutation
  test two sessions ago. The assertion caught it before any write; the lesson is that any anchor into
  a formatted file should be re-read after formatting, not written from memory.
- **A structural test matched my own explanatory comment rather than the setting it guards.** The
  compose seed test picked the first line containing `PSEUDONYM_SEED`, which was a comment
  explaining why the seed is handled the way it is. Corrected to strip comment lines. Same class as
  the docstring-versus-import defect in §38 — text search cannot tell a rule from a description of
  the rule.
- **Deviation: three tests written after the implementation** — the `.env` loading test, the
  empty-seed regression, and the second one closing the last uncovered line in `app/replay.py`. Each
  says so in its own docstring.

## Next step

1. **Push the four commits.**
2. **Phase 5 — `api-002`**: `/api/v1/operational-picture` returning the frontend contract's shape.
   Then `api-003`, swapping the mock in `App.tsx` for a fetch. This is also where **`db-006`** gets
   its first real test, since it needs a data-serving route to assert against.
3. **`db-007`** — the run completion flag. Small, and cheapest now: the second Alembic revision is
   easier against a database nothing yet reads than against one the detectors do.
4. **`scn-001`/`scn-002`** — the scenario generator, which supersedes `adp-007`'s placeholder run.

Owed, with an owner but no date:

- **`db-007` is specified and unbuilt** (written 2026-09-05): a nullable `completed_at` on
  `scenario_runs`, so a partial run is distinguishable from a finished one. Falls out of `adp-007`'s
  per-batch unit of work. Deleting the run on failure was considered and rejected — the rows are
  evidence, and a cascade over 133,634 observations is a surprising thing for a failure path to do.
  A three-state `status` column was also rejected: a killed process cannot record its own failure, so
  `failed` would be right for caught exceptions and silently wrong otherwise. Rationale in `qa.md`
  §40.
- **`app/corpus/build.py` resolves `.env` from the repository root** and will break the first time
  anyone containerises the corpus build. One line, not yet changed, because editing a passing item
  outside its own spec is how the drift in §38/§39 starts.
- **Scenario type 4 must exclude the 10 tracks carrying a natural dropout** from injection sites.
  Seven of the ten fall in the 100–300 s band the scenario injects.
- **Re-run the coverage acceptance check as originally specified** — `Normal baseline` through the
  extract — once the scenario engine exists.
- **Record whether any Phase 6 detection rule needs altitude on more than 77% of samples**, given
  22.7% of positioned rows carry none.

Open and unowned:

- **4 commits unpushed.**
- **Root `make check` has still not been run in full.** Only `make test-backend` this session.
- **The frontend suite has not been run for three sessions.** `pnpm test` fails on the shell's
  default Node 20; `frontend/.nvmrc` pins ≥ 22.13 and `nvm use` is required first.
- **`make generate` is broken** — the `pipeline` service's command names `app.pipeline`, which does
  not exist until `scn-003`. Carried knowingly; recorded in `ops-003`'s own text.
- **mypy does not check `tests/`.** 18 errors when last measured, nearly all deliberate type
  violations in negative tests.
- **CI still does not exist** (`ops-002`).
- Track 0: the data-egress question (employer) and the licence-version divergence both remain open.
