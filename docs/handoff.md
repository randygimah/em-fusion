# Handoff

Written at the end of a working session so the next one starts with context rather than
archaeology. Overwritten each session — this is the current state, not a log. History lives in git.

**Session date:** 2026-08-21
**Branch:** `main`, in sync with `origin/main`

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
replayed aviation telemetry and synthetic RF observations fused through a Data Abstraction Layer,
deviations detected deterministically, evidence bundles turned into schema-validated,
grounding-checked AI hypotheses for analyst review. Decision support, not autonomous
decision-making.

This session built the whole DAL — canonical model, validation, quarantine, provenance, identifier
pseudonymisation — deliberately ahead of the database, then closed the corpus tooling with a
command-line entrypoint and fixed the backend command surface.

## Current state

The DAL is complete and the corpus is rebuildable in one command. Nothing persists to a database
yet: the repository port has one implementation, an in-memory fake in `backend/tests/fakes.py`.

| | |
|---|---|
| Backend suite | **128 passed, 99% coverage on `app/`.** Only miss is `app/corpus/extract.py:246`, pre-existing |
| Tooling | `make check` **works now** — format, lint, type-check, test, all through `uv run`, coverage gated at 90% |
| Spec items passing | **8 of 80**: `api-001`, `adp-004`, `adp-005`, `adp-006`, `dal-001`, `dal-002`, `dal-003`, `dal-004` |
| Corpus | Rebuilt this session. Box 49–54°N, 3–11°E; 133,634 rows; content checksum `7ce83881…be05`, now stable across four builds |
| Seed | `PSEUDONYM_SEED` set in `backend/.env` (gitignored). Fingerprint `8696f2f2…1de7` committed in the manifest |

**The corpus rebuild is done and committed** (`36d36c9`). `data/opensky/manifest.json` now carries
`pseudonym_seed_sha256` and passes `validate_manifest`. The CLI was then run against the real corpus
as an end-to-end check and produced an **empty `git diff`** — which is what proves the derived
download date works (it held at `2026-08-13` rather than advancing to today) and that the
content-checksum guard passes rather than being bypassed.

### Decisions the next session should not re-litigate

All four are written up in `docs/thesis_notes.md` under System Design and Architecture, with the
reasoning and the rejected alternatives.

- **The DAL was built before the database, behind a repository port.** `db-003` requires that seam
  whatever the order, so this adds a second implementation rather than a second layer, and the DAL
  logic is written once either way. See `docs/qa.md` §26.
- **No field anywhere in the canonical model can hold `icao24` or `callsign`.** A test asserts it
  across all four models. `dal-004` therefore changes how `aircraft_id` is *derived*, not the shape
  of any record.
- **The pseudonymisation seed is not committed and is not in the manifest** — the manifest records
  its SHA-256 fingerprint. A seed over a 24-bit input space is a key, not a salt. See `docs/qa.md`
  §27 and §28.
- **`QuarantineRecord` does not store the raw source row.** A quarantined OpenSky row still carries a
  real `icao24`. It holds the failing field, the reason, and best-effort attribution; the run is
  always known because `scenario_run_id` comes from the ingest context rather than the record.

Two behaviours that are enforced rather than conventional: a record arriving with its own
`provenance`, or with `aircraft_id`/`flight_id` already populated, is **rejected** — in both cases an
adapter doing the DAL's job.

### What "the DAL items pass" does and does not assert

It asserts DAL behaviour: the DAL refuses to construct a record with provenance missing, and splits a
batch into observations and quarantine rows without dropping anything. It does **not** assert that
the schema would also refuse a bad record — those are `db-001`'s `NOT NULL` constraints, to be proven
there. The spec text for `dal-002` and `dal-003` was amended to say so rather than leaving
`passes: true` to imply more than it demonstrates.

## Files in flight

The tree is clean and pushed. Files `adp-001` will open:

- `backend/app/dal/` — complete. `adp-001` calls
  `ingest_batch(records, context, repository, pseudonymiser)` and needs no change to any of it.
- `backend/app/corpus/extract.py` — `read_rows` already yields the corpus rows `adp-001` replays,
  and the source-record shape it must produce is in `tests/test_dal_pseudonymise.py::_track_record`.

## Changed

Nineteen commits on top of `31c1521`; 25 files, +3,109/−122.

| Commit | What |
|---|---|
| `63ef556` | `docs: record qa 26 — DAL behind a repository port, and what it costs` |
| `44912f6` | `spec: amend dal-002, dal-003` |
| `7cf37ff` `fae7bbe` | `dal-001` — canonical observation model and validation |
| `4192386` | `docs: record two DAL design decisions in thesis_notes` |
| `ea23219` `12ed303` | `dal-002`, `dal-003` — quarantine and provenance |
| `1cb1057` | handoff update (superseded by this one) |
| `3d497f3` | `spec: amend dal-004 — the seed is not committed` |
| `0bf85b0` `05e7856` | `dal-004` — seeded identifier pseudonymisation |
| `82b74b2` | `docs: record qa 27 and the seed reversal in thesis_notes` |
| `528c929` | handoff update (superseded by this one) |
| `6028ad1` | `docs: record qa 28 — the two seeds, and why the manifest is stale` |
| `36d36c9` | `chore: record the pseudonymisation fingerprint` — the corpus rebuild |
| `d58ff3e` | `spec: add adp-006, amend adp-005` |
| `f831456` `6a090bf` | `adp-006` — corpus build CLI |
| `d3908cf` | `fix: make check runs without an activated venv` |

Added: `backend/app/dal/{models,validation,repository,ingest,pseudonymise}.py`,
`backend/app/corpus/build.py`, and four test modules plus `tests/fakes.py`. Modified:
`docs/spec.jsonl` (four items amended, five set to `passes: true`, one added), `docs/qa.md` (§26–§28,
nine glossary terms), `docs/thesis_notes.md` (three subsections), `README.md` (a corpus section that
did not exist), `backend/{Makefile,pyproject.toml,.env.example}`, `app/corpus/{extract,fetch}.py`,
`data/opensky/manifest.json`.

No new dependencies. `python-dotenv` was already declared and unused; `app/corpus/build.py` is now
its first consumer.

## Failed attempts

- **The previous handoff's "next step: `dal-004`" was not directly actionable.** `dal-004`
  pseudonymises identifiers on a canonical observation that did not exist. The real choice was
  database-first versus port-first, and it had to be made before any code was written.
- **`dal-004`'s own spec text contained a contradiction that survived several readings.** It required
  the seed to be recorded in the committed manifest *and* required that no readable reverse mapping
  exist. `icao24` is 24 bits, so a published seed reverses the whole corpus by exhaustive search in
  seconds — the item forbade the thing it mandated. The underlying mistake was treating the seed as a
  salt rather than a key. Written up in `docs/qa.md` §27 and `docs/thesis_notes.md`.
- **`dal-001`'s source-record shape was wrong, and `dal-004` exposed it.** Its fixtures had the
  adapter supplying a ready-made opaque `aircraft_id`, which means the *adapter* was pseudonymising —
  exactly what `dal-004` forbids. Source records now carry `icao24` and `callsign`. The canonical
  model was untouched, which is what the "no field can hold an `icao24`" decision bought.
- **`adp-005` claimed a one-command rebuild it did not deliver.** The claim was met by a multi-line
  `python -c` invocation, which is not a command and carried the download-date trap by hand. That is
  `adp-006`, and `adp-005`'s text now points at it.
- **Three tests were wrong before any code was, all caught the same way** — by stubbing the unbuilt
  module so pytest collects and each test fails individually, rather than accepting the import-level
  collection error as the red bar. **Keep doing this**; it caught one bad test per spec item.
  - `test_the_canonical_model_has_no_field_for_a_source_aircraft_identifier` passed against an empty
    stub, because `isdisjoint` is trivially true of a model with no fields.
  - `test_a_failing_repository_leaves_nothing_persisted` used a bare `pytest.raises(RuntimeError)`,
    and `NotImplementedError` subclasses `RuntimeError`.
  - `test_the_seed_is_not_a_command_line_flag` passed against an empty parser for the same reason as
    the first.
- **Deviation: three `dal-001` tests were written after the implementation**, to close coverage on
  three dead failure paths. Coverage moving 92% → 100% evidences they execute those lines, but they
  had no red step of their own.
- **Deviation: three `dal-003` tests passed before the implementation existed.** `dal-001`'s models
  already discharge that failure case. Kept as regression guards rather than contorted into failing.
- **The Bash working directory does not persist reliably between calls.** A `cd backend && cat > …`
  heredoc silently wrote nothing when the `cd` failed because the shell was already there. Use
  absolute paths for file writes.

## Next step

1. **`adp-001`** — replay the extract through the DAL. The DAL is complete and needs no change; this
   is an adapter that reads Parquet rows via `read_rows` and hands mappings to `ingest_batch`. It is
   the last piece before persistence becomes the blocker.
2. **`db-005` then `db-001`** — engine and session, then schema and migrations, at which point the
   PostGIS implementation of `ObservationRepository` lands and the `NOT NULL` half of `dal-002` and
   `dal-003` gets asserted.
3. **Phase 5** — `/api/v1/operational-picture` against the frontend contract, then swap the mock.

Owed, with an owner but no date:

- **Scenario type 4 must exclude the 10 tracks carrying a natural dropout** from injection sites.
  Seven of the ten fall in the 100–300 s band the scenario injects, so without the exclusion the type
  4 false-positive rate is confounded. The coverage report identifies the tracks.
- **Re-run the coverage acceptance check as originally specified** — `Normal baseline` through the
  extract — once the scenario engine exists.
- **Record whether the repository port's signature survived the PostgreSQL implementation
  unchanged**, and if not, which of geometry, identity, or atomicity was got wrong. The prediction on
  record is that geometry and atomicity are the risks and identity is not.

Open and unowned:

- **mypy does not check `tests/`.** The dead `tests.*` override was removed rather than the check
  extended, because `mypy app/ tests/` currently reports **18 errors**, nearly all from deliberate
  type violations in negative tests. Extending it would mean ~18 `# type: ignore` annotations, which
  arguably documents the violations as intentional. Cost is now quantified; the call is not made.
- **CI still does not exist** (`ops-002`). `make check` is now the command CI would call, but nothing
  enforces it on push — which is what would have caught the broken Makefile four sessions earlier.
- Track 0: the data-egress question (employer) and the licence-version divergence (shipped 2017
  `LICENSE.txt` vs the operative published terms) both remain open.
