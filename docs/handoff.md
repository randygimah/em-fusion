# Handoff

Written at the end of a working session so the next one starts with context rather than
archaeology. Overwritten each session — this is the current state, not a log. History lives in git.

**Session date:** 2026-08-21
**Branch:** `main`

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
replayed aviation telemetry and synthetic RF observations fused through a Data Abstraction Layer,
deviations detected deterministically, evidence bundles turned into schema-validated,
grounding-checked AI hypotheses for analyst review. Decision support, not autonomous
decision-making.

This session built the whole DAL — canonical model, validation, quarantine, provenance, and
identifier pseudonymisation — deliberately ahead of the database, so that `dal-004` landed before
`adp-001` replays a single real row.

## Current state

The DAL accepts records, validates them, quarantines what fails, and stamps provenance on what
passes. Nothing persists yet: the repository port has one implementation, an in-memory fake in
`backend/tests/fakes.py`, and the PostGIS one arrives with `db-001`.

| | |
|---|---|
| Backend suite | **110 passed, 99% coverage on `app/`**; 100% on all four `app/dal` modules. The single miss is pre-existing at `app/corpus/extract.py:245` |
| Tooling | black / ruff / mypy clean. `make check` still cannot run — see Failed attempts |
| Spec items passing | **7 of 79**: `api-001`, `adp-004`, `adp-005`, `dal-001`, `dal-002`, `dal-003`, `dal-004` |
| `dal-004` | **`passes: true`** — seeded pseudonymisation, seed from `PSEUDONYM_SEED` |
| Corpus | Unchanged from last session. Box 49–54°N, 3–11°E; extract 133,634 rows, content checksum `7ce83881…be05`. Gitignored, manifest and coverage report committed |

**Build-order decision, and the reason it matters downstream.** The planned order put persistence
(Phase 6) before the DAL (Phase 7). It was inverted: the DAL is built first, behind a repository
port. `db-003` requires that seam whatever the order, so this adds a second implementation rather
than a second layer, and the DAL logic itself is written once either way. Full reasoning in
`docs/qa.md` §26 and `docs/thesis_notes.md`, "Building the DAL before the database, behind a
repository port".

**What "`dal-002` and `dal-003` pass" does and does not assert.** It asserts DAL behaviour: the DAL
refuses to construct a record with provenance missing, and splits a batch into observations and
quarantine rows without dropping anything. It does *not* assert that the schema would also refuse a
bad record — those are `db-001`'s `NOT NULL` constraints, to be proven there. The spec text for both
items was amended to say so explicitly rather than leaving `passes: true` to imply more than it
demonstrates.

**Two design decisions the next session should not re-litigate**, both written up in
`docs/thesis_notes.md` under System Design and Architecture:

- **No field anywhere in the canonical model can hold `icao24` or `callsign`.**
  `TrackPayload.aircraft_id` is opaque by contract and a test asserts the absence across all four
  models. `dal-004` therefore changes how that value is *derived*, not the shape of any record.
- **`QuarantineRecord` does not store the raw source row.** A quarantined OpenSky row still carries
  a real `icao24`; keeping it for debuggability would put into the database the identifier `dal-004`
  exists to keep out. Quarantine holds the failing field, the reason, and best-effort attribution.
  Attribution is best-effort because a record can fail *because* it is missing the field that
  identifies it; `scenario_run_id` comes from the ingest context and is therefore always known.

One further behaviour worth knowing: a record arriving with its own `provenance` key is **rejected**,
not silently overwritten. Attachment at the DAL is only a guarantee if the DAL is the sole source.

## Files in flight

The tree is clean, but **one committed artefact is now stale and needs you**:

- `data/opensky/manifest.json` — does not carry `pseudonym_seed_sha256`, which `validate_manifest`
  now requires, so the committed manifest no longer validates. `build_corpus` still runs, because
  `read_source_ref` reads only the source URL and checksum. Closing this needs a real seed, which is
  your choice, not mine: set `PSEUDONYM_SEED` in `backend/.env` (gitignored; template in
  `.env.example`) and re-run `build_corpus`, which rewrites the manifest. The raw tarball is still in
  `data/opensky/raw/`, so no re-download is needed. **Pick the seed once and do not change it** —
  every pseudonym in every figure depends on it.

Files `adp-001` will open:

- `backend/app/dal/` — complete. `adp-001` calls `ingest_batch(records, context, repository,
  pseudonymiser)` and needs no change to any of it.
- `backend/app/corpus/extract.py` — `read_rows` already yields the corpus rows `adp-001` replays.

## Changed

Twelve commits on top of `31c1521`:

| Commit | What |
|---|---|
| `63ef556` | `docs: record qa 26 — DAL behind a repository port, and what it costs` |
| `44912f6` | `spec: amend dal-002, dal-003` |
| `7cf37ff` | `test: add tests for dal-001` |
| `fae7bbe` | `feat(dal-001): canonical observation model and validation - tests pass` |
| `4192386` | `docs: record two DAL design decisions in thesis_notes` |
| `ea23219` | `test: add tests for dal-002, dal-003` |
| `12ed303` | `feat(dal-002, dal-003): quarantine and provenance - tests pass` |
| `1cb1057` | `docs: update handoff — DAL built ahead of the database` |
| `3d497f3` | `spec: amend dal-004 — the seed is not committed` |
| `0bf85b0` | `test: add tests for dal-004` |
| `05e7856` | `feat(dal-004): seeded identifier pseudonymisation - tests pass` |
| `82b74b2` | `docs: record qa 27 and the seed reversal in thesis_notes` |

Files added: `backend/app/dal/{__init__,models,validation,repository,ingest,pseudonymise}.py`,
`backend/tests/{fakes,test_dal_models,test_dal_ingest,test_dal_pseudonymise}.py`. Modified:
`docs/spec.jsonl` (three items amended, four set to `passes: true`), `docs/qa.md` (§26, §27, six
glossary terms), `docs/thesis_notes.md` (three subsections under System Design and Architecture),
`backend/.env.example` (`PSEUDONYM_SEED`), and — from the `dal-004` signature change —
`app/corpus/{extract,fetch}.py` plus the `adp-004`/`adp-005` tests.

No new dependencies — `pydantic` was already a runtime dependency.

## Failed attempts

- **The previous handoff's "next step: `dal-004`" was not directly actionable, and taking it at face
  value would have wasted a session.** `dal-004` pseudonymises identifiers on a canonical observation
  that did not exist: `dal-001` was unbuilt, and `dal-002` and `dal-003` are the same code path. All
  three are worded around persistence while `db-001` and `db-005` are also unbuilt. The real choice
  was database-first versus port-first, and it had to be made before any code was written.
- **Two tests were wrong before any code was.** Both were caught by stubbing the unbuilt module so
  pytest collects and each test fails individually, rather than accepting the import-level collection
  error as the red bar. Worth continuing to do — it has now caught one bad test per spec item.
  - `test_the_canonical_model_has_no_field_for_a_source_aircraft_identifier` passed against an empty
    stub, because `isdisjoint` is trivially true of a model with no fields. It now asserts the
    payload is populated first.
  - `test_a_failing_repository_leaves_nothing_persisted` used a bare `pytest.raises(RuntimeError)`,
    and `NotImplementedError` subclasses `RuntimeError`, so it passed against an unbuilt ingest. It
    now matches on the message and asserts the repository was actually called.
- **Deviation: three `dal-001` tests were written after the implementation**, to close coverage on
  three dead failure paths (unknown `source_type`, malformed timestamp, the model's own payload/type
  guard). Coverage moving 92% → 100% on `validation.py` is what evidences they execute those lines
  rather than passing vacuously, but they did not get a red step of their own.
- **Deviation: three `dal-003` tests passed before the implementation existed** — the ones asserting
  a context or provenance with a null `scenario_run_id` or absent `data_mode`. `dal-001`'s models
  already discharge that failure case. They were kept as regression guards rather than contorted into
  failing; recorded here because the workflow's rule is that a test passing early is a wrong test, and
  this is a considered exception rather than an oversight.
- **`dal-004`'s own spec text contained a contradiction that survived several readings.** It
  required the seed to be recorded in the committed manifest *and* required that no readable reverse
  mapping exist. `icao24` is 24 bits, so a published seed reverses the whole corpus by exhaustive
  search in seconds — the item forbade the thing it mandated. The underlying mistake was treating the
  seed as a salt rather than as a key; a salt may be published because its input space resists
  enumeration, and a transponder address does not. The manifest now records the seed's SHA-256
  fingerprint. Written up in `docs/qa.md` §27 and `docs/thesis_notes.md`.
- **`dal-001`'s source-record shape was wrong, and `dal-004` is what exposed it.** Its fixtures had
  the adapter supplying a ready-made opaque `aircraft_id`, which means the *adapter* was doing the
  pseudonymisation — exactly what `dal-004` forbids. Source records now carry `icao24` and `callsign`
  and the DAL replaces them. The canonical model was unaffected, which is what the "no field can hold
  an `icao24`" decision bought; the churn was in test fixtures and three call signatures.
- **`make check` is still broken**, and it cost time again this session. `backend/Makefile` calls
  bare `black` / `ruff` / `mypy` / `pytest`, which are not on `PATH` without the venv activated. Every
  tooling command this session was run as `uv run <tool>` instead. This is the open item below, and
  it is now two sessions old.
- **The Bash working directory does not persist reliably between calls.** A `cd backend && cat > …`
  heredoc silently wrote nothing when the `cd` failed because the shell was already there, and the
  failure was invisible until the next test run. Use absolute paths for file writes.

## Next step

0. **Set `PSEUDONYM_SEED` and rebuild the corpus** — see Files in flight. Blocks nothing in code, but
   the committed manifest is invalid until it is done, and the seed must be fixed before any figure
   is produced.
1. **`adp-001`** — replay the extract through the DAL. The DAL is complete and needs no change; this
   is an adapter that reads Parquet rows and hands mappings to `ingest_batch`.
2. **`db-005` then `db-001`** — engine and session, then schema and migrations, at which point the
   PostGIS implementation of `ObservationRepository` lands and the `NOT NULL` half of `dal-002` and
   `dal-003` gets asserted.
3. **Phase 5** — `/api/v1/operational-picture` against the frontend contract, then swap the mock.

Owed, with an owner but no date:

- **Scenario type 4 must exclude the 10 tracks carrying a natural dropout** from injection sites.
  Seven of those ten fall in the 100–300 s band the scenario itself injects, so without the exclusion
  the type 4 false-positive rate is confounded. The coverage report identifies the tracks. Recorded as
  a threat to validity in `docs/thesis_notes.md`.
- **Re-run the coverage acceptance check as originally specified** — `Normal baseline` through the
  extract — once the scenario engine exists. Last session measured the extract directly instead.
- **Record whether the repository port's signature survived the PostgreSQL implementation unchanged**,
  and if not, which of geometry, identity, or atomicity was got wrong. The prediction on record is
  that geometry and atomicity are the risks and identity is not.

Open and unowned:

- `backend/Makefile` calls bare `ruff` / `mypy` / `pytest`. `uv run` would fix it. Two sessions old
  and it has now cost time in both.
- `--disable-warnings` in pytest `addopts` hides deprecations.
- The mypy `tests.*` override is dead config: `make type-check` only runs `mypy app/`, and mypy
  reports the section as unused on every run.
- Track 0: the data-egress question (employer) and the licence-version divergence (shipped 2017
  `LICENSE.txt` vs the operative published terms) both remain open.
