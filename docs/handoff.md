# Handoff

Written at the end of a working session so the next one starts with context rather than
archaeology. Overwritten each session — this is the current state, not a log. History lives in git.

**Session date:** 2026-08-26
**Branch:** `main`, **7 commits ahead of `origin/main` and not pushed**

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
replayed aviation telemetry and synthetic RF observations fused through a Data Abstraction Layer,
deviations detected deterministically, evidence bundles turned into schema-validated,
grounding-checked AI hypotheses for analyst review. Decision support, not autonomous
decision-making.

This session built `adp-001`, the OpenSky replay adapter — the last piece before persistence becomes
the blocker. It began as a set of conceptual questions about what an adapter *is* in this project,
and those questions changed the design twice: the adapter lost its clock, and the canonical model
gained a field.

## Current state

The replay path is complete from Parquet to canonical observation. Nothing persists to a database
yet: the repository port still has one implementation, the in-memory fake in `backend/tests/fakes.py`.

| | |
|---|---|
| Backend suite | **158 passed, 99.83% coverage on `app/`.** `app/adapters/opensky.py` at 100%. Only miss is `app/corpus/extract.py:246`, pre-existing |
| Spec items passing | **9 of 80**: `api-001`, `adp-001`, `adp-004`, `adp-005`, `adp-006`, `dal-001`, `dal-002`, `dal-003`, `dal-004` |
| Corpus | Unchanged. Box 49–54°N, 3–11°E; 133,634 rows; content checksum `7ce83881…be05` |
| Tooling | `backend/make check` green. Root `make check` **not run this session** |

### The full-corpus replay, measured

Run against the real 133,634-row extract with an in-memory repository, so it measures the reader and
the DAL and not persistence. Every figure was predicted from the raw Parquet first and reproduced
through the pipeline unchanged.

| Measure | Result |
|---|---|
| Accepted as canonical observations | 133,134 |
| Quarantined | 500, all `location: lat: Input should be a valid number` |
| Repository writes | 1 — the batch commits as one unit of work |
| Wall time, full simulated hour | 2.46 s |
| No altitude reported | 30,276 (22.7%) |
| Blank callsign, so no `flight_id` | 3,754 |
| Fresh contact / stale position | 4,553 — the GNSS-degradation signature |

Position staleness over positioned rows: p50 0.33 s, p90 38.92 s, p99 269.63 s, max 1561.12 s, never
negative. Contact staleness caps at 299.97 s, which is OpenSky's own drop timeout — that ceiling on
one measure and not the other is what proves the two fields are measuring different things.

### Decisions the next session should not re-litigate

All written up in `docs/thesis_notes.md` with their rejected alternatives.

- **The adapter holds no clock.** `read_window` takes a half-open `[start, end)` span of source time
  and keeps no position between calls; the simulated clock belongs to `scn-001`. Latency is measured
  in simulated time, and two components each holding a "now" makes that measurement ambiguous.
- **`altitude_m` takes `baroaltitude`, falling back to `geoaltitude`.** The null sets nest, so the
  fallback fires on zero rows of this corpus. Barometric is one consistent reference, and geoaltitude
  is GNSS-derived — the field the injected interference would itself degrade.
- **`TrackPayload` gained `contact_staleness_s`**, required. Without it, scenario types 2 and 4 are
  indistinguishable in the data the detectors read.
- **`replay_window` lives in `adp-001`**, with repository and pseudonymiser injected. The manifest's
  only job is `available_window`, derived from `snapshot_hour`.
- **The adapter imports nothing from `app.corpus`.** That module is the build-time tool; this one is
  a replay-time consumer. The reader asks the Parquet file for its schema.

## Files in flight

Tree is clean apart from `docs/qa.md` and `docs/thesis_notes.md`, both of which carry this session's
writing and are **uncommitted**. Seven commits are unpushed.

- `backend/app/adapters/opensky.py` — complete. `db-001` will not change it; only its caller changes.
- `docs/spec.jsonl` — `adp-007` is drafted in conversation but **not yet written to the file**, pending
  agreement. See Next step.

## Changed

Seven commits on top of `2fd2b2e`.

| Commit | What |
|---|---|
| `c501661` | `feat: update implementation.md and add to qa` (committed by the user) |
| `91eb84c` | `spec: amend adp-001` — no clock, extract not committed, reader still to be written |
| `905890c` | `docs: record the two adp-001 decisions in thesis_notes` |
| `e17de59` | `spec: amend adp-001 — replay_window and available_window in scope` |
| `8e7e2c7` | `test: add tests for adp-001` |
| `ec5a1bf` | `feat(adp-001, dal-001): OpenSky replay adapter - tests pass` |
| `44ea74e` | `docs: record the contact_staleness_s decision and adp-001 measurements` |

Added: `backend/app/adapters/{__init__,opensky}.py`, `backend/tests/test_adp_opensky.py` (28 tests).
Modified: `app/dal/models.py` (`contact_staleness_s`), three DAL test fixtures, `docs/spec.jsonl`
(`adp-001` amended twice and set passing, `dal-001` amended and cycled), `docs/qa.md` (§30–§33, nine
glossary terms), `docs/thesis_notes.md` (four subsections). No new dependencies.

## Failed attempts

- **The previous handoff's "Files in flight" was wrong, and it was my own claim.** It said `read_rows`
  "already yields the corpus rows `adp-001` replays". It does not: `app/corpus/extract.py:140` reads
  the **raw tarball's** gzipped CSV. `write_parquet` had no counterpart, so a Parquet reader had to be
  written. Work recorded as done that did not exist.
- **`adp-001`'s spec text was stale in two ways and had survived several readings.** It described "a
  committed Parquet file" and replay "reproducible from a fresh clone with no download step". Both
  were true when written and were falsified by `adp-004`'s licence reversal, which made the extract
  gitignored. Amended before tests were written.
- **`contact_staleness_s` was nearly lost silently.** The 2026-08-23 amendment listed the payload as
  exactly the canonical `TrackPayload` fields, which quietly dropped `lastcontact` from `adp-001`'s
  output — the adapter would have read the column and discarded it, because the model had nowhere to
  put it. It surfaced only because a user question about why a test fixture used `-1` and `-2` forced
  an explanation of what the two columns mean. **The general lesson is the one worth keeping: a
  confound built into the canonical model is indistinguishable, in the results, from a detector that
  simply performs badly.** It would have shown up as a poor type-2-vs-type-4 confusion matrix in the
  campaign, months later, with the cause hard to attribute.
- **The import-direction test was wrong twice over.** It read the module's source text and asserted
  `"app.corpus" not in source`, so (a) it failed the moment the implementation's *docstring* explained
  the rule, and (b) it would never have caught `from app import corpus`, which contains no such
  substring. Rewritten to parse the AST, then mutation-tested against both import forms to prove it
  actually fails. This was also the one test that passed against the empty stub — exactly the case the
  last session's notes warned about.
- **Deviation: `dal-001` was reopened.** It was a passing item; adding `contact_staleness_s` changed
  the shape its description claims, so it was set back to `passes: false` (count 8 → 7) and returned
  to `true` only after the new tests went red then green. Leaving the flag set while amending the text
  would have made it assert what the tests did not show.
- **`cd backend && …` silently failed again**, the same trap the last session recorded. The shell's
  working directory does not persist predictably between Bash calls. Separately: running a script by
  **absolute path** puts the *script's* directory on `sys.path`, not the working directory, so
  `import app` fails from inside `backend/`. Both cost a round trip.
- **Black reformatted a long test name into a parenthesised return annotation and pushed the line past
  88 characters**, failing `ruff` after `black` had just "fixed" it. The name was shortened. Worth
  knowing that `make format` succeeding does not imply `make lint` will.

## Next step

1. **Push.** Seven commits are unpushed and `docs/qa.md` and `docs/thesis_notes.md` are uncommitted.
   Local and remote `main` are supposed to be in sync after every merge.
2. **Decide `adp-007`** — a `make replay` target and the module behind it, so the full-corpus replay
   above is reproducible by command rather than by an ad-hoc script. Drafted but not written to
   `spec.jsonl`; needs agreement on scope first. The blocker to note: there is no repository to replay
   *into* until `db-001`, so today it can only be a dry-run that reports counts without persisting.
3. **`db-005` then `db-001`** — engine and session, then schema and migrations, at which point the
   PostGIS implementation of `ObservationRepository` lands and the `NOT NULL` halves of `dal-002` and
   `dal-003` finally get asserted.
4. **Phase 5** — `/api/v1/operational-picture` against the frontend contract, then swap the mock.

Owed, with an owner but no date:

- **Scenario type 4 must exclude the 10 tracks carrying a natural dropout** from injection sites.
  Seven of the ten fall in the 100–300 s band the scenario injects, so without the exclusion the type
  4 false-positive rate is confounded. The coverage report identifies the tracks.
- **Re-run the coverage acceptance check as originally specified** — `Normal baseline` through the
  extract — once the scenario engine exists.
- **Record whether the repository port's signature survived the PostgreSQL implementation
  unchanged**, and if not, which of geometry, identity, or atomicity was got wrong. The prediction on
  record is that geometry and atomicity are the risks and identity is not.
- **Re-record the 2.46 s replay figure against the PostGIS repository.** The current number measures
  the reader and the DAL only; the one that will bound a scenario run includes persistence.
- **Record whether any Phase 6 detection rule needs altitude on more than 77% of samples**, given
  22.7% of positioned rows carry none.

Open and unowned:

- **The root `make check` has not been run since the adapter landed.** The last session's finding was
  that the two command surfaces drift silently; only `backend/make check` was run this session.
- **mypy does not check `tests/`.** `mypy app/ tests/` reported 18 errors when last measured, nearly
  all from deliberate type violations in negative tests. Cost is quantified; the call is not made.
- **CI still does not exist** (`ops-002`). Until it does, a green `make check` is evidence about one
  machine at one moment. `ops-003` also remains `passes: false`.
- Track 0: the data-egress question (employer) and the licence-version divergence (shipped 2017
  `LICENSE.txt` vs the operative published terms) both remain open.
