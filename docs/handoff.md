# Handoff

Written at the end of a working session so the next one starts with context rather than
archaeology. Overwritten each session — this is the current state, not a log. History lives in git.

**Session date:** 2026-08-14
**Branch:** `main` (clean, all work committed)

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
replayed aviation telemetry and synthetic RF observations fused through a Data Abstraction Layer,
deviations detected deterministically, evidence bundles turned into schema-validated,
grounding-checked AI hypotheses for analyst review. Decision support, not autonomous
decision-making.

This session's objective was narrower: get the real OpenSky data in, and build the corpus extraction
around it.

## Current state

The corpus is downloaded and integrity-verified. The extraction library is implemented and green.
The network half of the extraction is specified but not built.

| | |
|---|---|
| Corpus | `data/opensky/raw/states_2022-06-27-12.csv.tar`, 179,763,200 bytes, SHA-256 `6e0d2278…91e2`, MD5 matches the S3 ETag. Gitignored. |
| Backend suite | 32 passed, 99% coverage on `app/`, ruff / black / mypy all clean |
| `adp-004` | Implemented and tested, but **`passes: false`** — the fetch-and-filter entrypoint clause is not built, so the item is not complete |
| `adp-005` | Drafted this session, agreed, no tests and no code yet |
| `dal-004` | Drafted and agreed, no tests and no code yet |
| Bounding box | **Not chosen.** A candidate (47–55°N, 3–15°E) was measured but not committed to |

Corpus measurements taken this session, for whoever picks this up: 2,858,582 rows, 14,334 distinct
aircraft, 220,908 rows (7.73%) with a null `lat` or `lon`, 14,781 rows whose `icao24` is all digits
with a leading zero. The candidate box yields 255,145 rows, 1,580 aircraft, 360 distinct timestamps
(exactly 3600/10, so the hour has no globally missing time steps).

## Files in flight

Nothing is half-edited — the tree is clean. These are the files the next piece of work will open:

- `backend/app/corpus/extract.py` — the filter, manifest builder, and coverage report. `adp-005`
  adds a sibling module beside it, not changes to it: the filter must stay network-free.
- `backend/tests/test_corpus_extract.py` — 27 tests; `adp-005`'s tests go in a new file.
- `docs/spec.jsonl` — `adp-005` and `dal-004` are the two open items with agreement but no tests.

## Changed this session

Seven commits, `0f5f922` through `6c2e89e`:

| Commit | What |
|---|---|
| `0f5f922` | `spec: add adp-004` |
| `b9e08be` | `spec: amend adp-004 for the OpenSky licence` |
| `e61f238` | `spec: add dal-004, reopen the data-egress assessment` |
| `c3194b3` | `spec: amend adp-004 to retain null-position rows` |
| `6734e49` | `test: add tests for adp-004` |
| `5e032cc` | `chore: switch the test client dependency to httpx2` |
| `6c2e89e` | `feat(adp-004): extraction, manifest, and coverage functions - tests pass` |

Files touched: `.gitignore`, `backend/app/corpus/` (new), `backend/tests/test_corpus_extract.py`
(new), `backend/pyproject.toml`, `backend/uv.lock`, and five documents — `docs/spec.jsonl`,
`requirements.md`, `implementation.md`, `qa.md`, `thesis_notes.md`, `em_fusion_v2.md`.

New requirements: `FR-111` and `NFR-405` (identifier de-identification). New dependency: `pyarrow`,
plus a mypy override because it ships no stubs.

## Failed attempts

- **Guessed the OpenSky dataset URL.** `opensky-network.org/data/datasets` does not exist; the real
  page is `/data/scientific`. Corrected by the user, not by checking.
- **`WebFetch` on `opensky-network.org` returns 403.** Bot protection. `curl` with a browser
  user-agent works, and the `datasets/` browser is a JavaScript shell over a public S3 bucket at
  `s3.opensky-network.org/data-samples` — that bucket is the real address, listable anonymously.
- **The recorded data-source decision was wrong.** `em_fusion_v2.md` and `thesis_notes.md` described
  "published tables as of 2026-03-01", conflating dataset 1 (Weekly 24 Hours of State Vector Data,
  2017–2022, the one actually used) with dataset 11 (Complete Trino Tables Snapshot, March 2026).
  Corrected.
- **`FR-110` and the first `adp-004` required committing the extract.** Reversed on reading the
  licence: OpenSky DLA §3(iii) forbids making the data available outside the licensee's institute.
  The failed assumption was that a bounding-box-filtered subset is a derived work.
- **Claimed the tarball holds one member.** It holds three — the `.csv.gz`, `LICENSE.txt` and
  `README.txt`. The claim came from reading only the first 3 KB of the tar.
- **Misdiagnosed the broken test environment.** Reported that starlette 1.x had renamed its test
  client dependency and that `pyproject.toml` therefore had to change. It had not: starlette falls
  back to `httpx` with a deprecation warning, and the actual fault was a `.venv` that had drifted
  from `uv.lock` because `uv` was not installed on the machine at all. The switch to `httpx2` went
  ahead as hygiene, not as the fix.
- **Three `adp-004` tests were written after the implementation**, not before, to close coverage
  gaps — the null-coordinate round trip, the boolean round trip, and the tar-with-no-csv-member
  case. This inverts the spec → test → code order and is recorded rather than hidden.

## Next step

1. **`adp-005`** — tests first, then the fetch entrypoint: download, verify the SHA-256 before
   filtering, temp-file-then-move, skip when the local file already matches, explicit licence
   acceptance. Then `adp-004` and `adp-005` can both be marked `passes: true`.
2. **Choose the bounding box** by running the coverage report over candidates and reading the gap
   distribution. This is the gate: the box feeds the Phase 4 PMTiles cut as well, so a late change
   is expensive.
3. **`dal-004`** — pseudonymisation at the DAL, built alongside `dal-001`, before `adp-001` replays
   a single real row.

Not blocking, but open and unowned:

- `backend/Makefile` calls bare `ruff` / `mypy` / `pytest`, so every target depends on the caller
  having `.venv` activated. This is how the environment drift went unnoticed. `uv run` would fix it.
- `--disable-warnings` in pytest `addopts` hid the starlette deprecation entirely.
- The mypy `tests.*` override is dead config: `make type-check` only runs `mypy app/`.
- Track 0: the data-egress item is reopened for the employer question, and the licence-version
  divergence (shipped 2017 `LICENSE.txt` vs the operative published terms) needs confirming.
