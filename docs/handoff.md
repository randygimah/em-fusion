# Handoff

## Goal

EM Fusion is a human-in-the-loop prototype for explainable electromagnetic situational awareness: it
fuses replayed aviation telemetry with synthetic RF observations through a Data Abstraction Layer,
detects deviations with deterministic rules, and turns evidence bundles into schema-validated,
grounding-checked AI hypotheses an analyst reviews. It is decision support, not autonomous
decision-making.

This session opened Phase 8, the detection layer. It set out to correct three backlog defects found
while reading the phase, then build the phase's foundations in dependency order rather than in
identifier order: the baseline engine, the two rules that sit on it, the storage every rule needs,
and the two spatial queries the fusion rules will sit on.

## Current state

**35 of 90 spec items pass.** The backend suite is **724 passed at 99.90% coverage** in the
container, with ruff, black and mypy all clean.

Built and passing this session, in build order:

| Item | What it is | Tests | Module coverage |
|---|---|---|---|
| `anom-002` | Rolling-average baseline, per sensor per channel | 27 | 100% |
| `anom-001` | `RF-NOISE` threshold rule | 28 | 100% |
| `anom-010` | `TRACK-GAP` continuity rule (new item — FR-304 had none) | 28 | 100% |
| `db-008` | `detection_findings` table, canonical finding, write and read | 17 | 100% |
| `db-004` | PostGIS proximity query (Phase 6's last unticked item) | 15 | 100% |
| `db-009` | PostGIS clustering (new item, split out of `db-004`) | 21 | 100% |

**Measurements taken this session — do not re-derive these.**

- The corpus background is **137.7 aircraft per quiet run** with a track discontinuity, over about
  530 seen. Not ten, which is what `anom-010` was specified against. Staged runs give 141.1, and at
  a 600 s threshold the quiet runs are *higher* than the staged ones (1.0 against 0.6).
- The **two-clock discriminator** (stale position with fresh contact) narrows the background to 24.6
  per run with the staged margin unchanged at 3.4.
- Baseline cells over a quiet run: 56 cells, 1,800 samples each, cell means spanning **0.177 dB**,
  cell standard deviations 1.437–1.551. Per-cell and pooled are indistinguishable on quiet data,
  which is why the granularity tests are built from a constructed loud channel.
- `ST_DWithin` on geography is **not inclusive at its boundary**. `ST_Distance` returns
  34338.94037894 m and `ST_DWithin` at exactly that value returns false, with zero drift in the
  round trip through kilometres.
- `ST_ClusterWithin` has **no geography overload** — both signatures take geometry and a distance in
  the SRID's own units. EPSG:3035 costs at most **2.57 m on a 5 km radius** across the corpus box
  (worst at 54°N 3°E); raw degrees would cost ~62% between the axes at 52°N.
- A 4326→3035→4326 round trip is **not** exact: longitude 5.0 returns as 4.999999999999997.
- An unordered window partition let a centroid move **8e-15 degrees (0.9 nm)** between runs of the
  same input, because `ST_Centroid` sums in collection order and the heap decides that order.
- Centroid in degrees versus in metres differ by **7.69 m** for a cluster spanning 25 km at 52°N.
- The `adp-008` exclusion list validated from a second code path: quiet-run gaps filter 164 → 32
  (airborne) → 23 (interior) → **0** once the list is applied. The 23 belong to 4 aircraft, all on
  the list, none unlisted.

**Specified and unbuilt:** `anom-003` (z-score), `anom-004` (spatial clustering), `anom-005`
(fusion), `anom-006` (source-gap), `anom-007`, `anom-009` (latency), `api-011` (connection-pool
exhaustion), `evb-*`, and everything downstream of them.

**Broken and owed:** the **frontend suite exits non-zero**. `pnpm test` reports 81 passed and then
fails with `TypeError: control.runs.map is not a function` at `scenarioControl.tsx:344`, raised from
`navigation.test.tsx`. Two separate pre-existing `api-010` defects: the test stubs `fetch` with a
single mock resolving `json: async () => operationalPicture` for *every* path, and
`useScenarioControl` never checks the response is an array, so a 200 with the wrong shape crashes
the screen rather than degrading it. **Two earlier handoffs stated this suite was green. It was
not.** It needs a spec item covering both halves.

## Files in flight

None. The working tree is clean at `b9632f3`.

## Changed

Commits this session, oldest first:

- `spec: add anom-010` and the three backlog corrections that opened the phase
- `feat(anom-002)`, `feat(anom-001)`, `feat(anom-010)` — baseline and the two rules
- `spec: add db-008`, `feat(db-008)` — the findings table and canonical shape
- `spec: amend db-004` (three times), `feat(db-004): the PostGIS proximity query - tests pass` — `9cfe74d`
- `spec: amend db-009 — ST_ClusterWithin has no geography variant` — `43b0466`
- `test: add tests for db-009` — `5f611bb`
- `feat(db-009): PostGIS clustering of detection findings - tests pass` — `b9632f3`

Files added: `backend/app/detection/{baseline,rf_noise,track_gap,findings}.py`,
`backend/app/db/findings.py`, `backend/alembic/versions/0003_detection_findings.py`,
`backend/tests/test_anom_{baseline,rf_noise,track_gap}.py`,
`backend/tests/test_db_{findings,proximity,clustering}.py`, `docs/phase8_detection.md`.

Docs: `docs/thesis_notes.md` gained sixteen subsections; `docs/qa.md` gained entries 60–64 and eight
glossary terms; `docs/implementation.md` gained the Phase 8 ordering note and several ticks;
`CLAUDE.md` gained the detection package, the db package, the alembic row, the `phase8_detection.md`
row, and **a new agent instruction**: explain an item in plain terms before building it, as chat
output and never as a file. The published progress note is at version 19.

New dependency on PostGIS behaviour: EPSG:3035 must be present in `spatial_ref_sys`. It ships with
the standard image and is asserted implicitly by the clustering tests.

## Failed attempts

**Four assumptions were confidently wrong and measurement caught each one.** Recording them together
because the pattern is the point: every one concerned a *dependency* or the *data*, never this
system's own code.

1. **`anom-010` was specified against ten corpus tracks.** The real figure is 137.7 per run — wrong
   by two orders of magnitude. The item had to be rescoped mid-build from reportable anomalies to
   intermediate findings, and `anom-008` amended to count only the fused rules.
2. **`anom-002`'s per-channel requirement was specified as provable against quiet data.** It is not:
   a pooled implementation reproduces the per-cell numbers to three decimal places.
3. **`db-004` was amended to claim `ST_DWithin` is inclusive at the boundary**, on the strength of
   the documentation. The database disagrees. The item now brackets the boundary to metre precision.
4. **`db-009` specified grouping "on geography" using a function that has no geography overload.**
   Both halves were written in the same sentence. One catalogue query would have caught it before it
   became a constraint.

**Mutation survivors, each a distinct kind of weak test.** `anom-002`: deleting the empty-baseline
guard left the suite green because the *next* guard raised — the test passed for the wrong reason.
`anom-001`: cells emitted in arrival order survived because the determinism test used a single cell.
`anom-010`: four survivors, two of them boundary cases carried from `anom-001` but not carried
across, one a guard reachable only through its neighbour, and **one an invalid mutation I built
myself** — `zip(reports, reports[1:] or reports)` is equivalent except for single-report aircraft.
An equivalent mutant counted as a survivor makes the score worse, not better.

**`statistics.mean` → `sum()/len()` is an equivalent mutant on CPython 3.12+**, which uses Neumaier
compensated summation. Verified over 300,000 random 30-sample sets.

**Docker hung for about 25 minutes.** A `make test-backend` left to time out at 600 s left
`em-fusion-backend-run-b7279e364837` alive holding a lock; the next run blocked on the schema drop
and `docker ps` itself stopped responding. Cleared with `docker rm -f`. **I then misread the
resulting `Error 137` — SIGKILL from my own cleanup — as a pass**, because the background wrapper
reported exit 0. Check for a stale `em-fusion-backend-run-*` container before blaming the database.

**Commit `0bae703` claimed three files and contained one.** A multi-file edit script's later
assertion failed after earlier writes had already landed, and the commit in the same shell
invocation ran regardless. **Worse: I diagnosed which edit had failed from the traceback's line
number, repaired only that one, and the repo map silently lacked `track_gap.py` for a day.** Second
occurrence of the same shape. The rule now followed is: apply every edit, verify each with an
independent grep, and only then commit. It caught nothing this time because it was followed.

**`make lint` had not been run after `db-004`.** `test_db_proximity.py` carried two E501 violations
into main and they were only found when `db-009` ran the checks. Fixed in `b9632f3`. The root
`make check` has still never been run in full.

**`psql -U em_fusion` fails** — the role is `postgres`. Compose sets `POSTGRES_USER` with a
`postgres` default and only `POSTGRES_DB` is `em_fusion`.

## Next step

1. **`anom-004`** — spatial clustering, the rule over `db-009`. Its description still calls `db-004`
   "the clustering query"; correct that reference when picking it up. **This is where the session's
   central finding gets tested**: whether the ~138 background discontinuities in a quiet run ever
   chain into a group large enough for `SOURCE-GAP` to fire on. If they do, `anom-008`'s
   zero-on-a-clean-run control fails and the radius needs rethinking. Do not pre-tune it.
2. **`anom-003`** — z-score. It carries a recorded, falsifiable prediction: it should need **no
   change** to `app/db/findings.py`. Score that prediction when it lands; it is the RQ1
   extensibility claim at a second seam.
3. **`anom-005`**, then `anom-006` — the fusion rules, which are the first reportable output.

Open and unowned:

- The frontend suite's non-zero exit and `useScenarioControl`'s malformed-success crash. Needs a
  spec item covering the test stub and the array check.
- `adp-008`'s exclusion list is **not applied to baseline windows** — owed to the generator.
  `load_exclusions` already exists in `app/scenario/tracks.py`.
- Detection latency has no definition. It is Track 0 and it gates `anom-009`.
- Detector radii are unchosen; the measured band is [55.7, 85.7) km.
- `anom-008`'s threat to validity must be reported in `eval-002`.
- `api-011` (connection-pool exhaustion), `nav-002`, reset and replay endpoints, `ops-002` (CI).
- `docs/qa.md` has a duplicate §47. Fix by note, never by renumbering.
- Frontend has no coverage tooling; `pnpm format` has not been run; mypy does not check `tests/`.
