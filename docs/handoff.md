# Handoff

## Goal

EM Fusion is a human-in-the-loop prototype for explainable electromagnetic situational awareness: it
fuses replayed aviation telemetry with synthetic RF observations through a Data Abstraction Layer,
detects deviations with deterministic rules, and turns evidence bundles into schema-validated,
grounding-checked AI hypotheses an analyst reviews. It is decision support, not autonomous
decision-making.

This session built Phase 8's foundations in dependency order — baseline, the two rules, storage, the
two spatial queries — and then spent its second half on a chain of measurements that overturned three
assumptions the phase had been built on. The detection layer now works and is honest about what it
cannot yet do.

## Current state

**37 of 93 spec items pass.** Backend suite **763 passed at 99.91% coverage** in the container, with
ruff, black and mypy clean. Working tree clean at `f7a6126`.

Built and passing this session:

| Item | What it is | Tests | Mutations |
|---|---|---|---|
| `anom-002` | Rolling-average baseline, per sensor per channel | 27 | — |
| `anom-001` | `RF-NOISE` threshold rule | 28 | 15/15 |
| `anom-010` | `TRACK-GAP` continuity rule (new item — FR-304 had none) | 28 | 17/17 |
| `db-008` | `detection_findings` table and the canonical finding | 17 | — |
| `db-004` | PostGIS proximity query (Phase 6's last unticked item) | 15 | — |
| `db-009` | PostGIS clustering (new item, split out of `db-004`) | 21 | 10/10 |
| `anom-004` | `TRACK-CLUSTER` spatial clustering rule | 16 | 11/12 + 1 equivalent |
| `anom-011` | Sensitivity harness (new item) | 19 | 13/14 + 1 invalid |
| `scn-006` | Stage only on aircraft in flight (new item) | 4 | 5/5 |

**The three findings that matter, in the order they were made.**

1. **Clustering does not discriminate.** Over 8 seed-matched triples in batch 1 and 20 in batch 2,
   the largest cluster on a staged run equals the largest on its own control in almost every triple,
   at every radius from 5 to 60 km. `anom-004` was rescoped to an intermediate finding as a result.
2. **The generator was staging on parked aircraft.** 209 of 381 aircraft the answer key called staged
   were on the ground for every report of their run — 55% of every injection landing where nothing
   could be detected. `scn-006` fixes it; measured on a second batch, parked aircraft in the key fall
   to 2% and recall rises from 25% to 69%, 81% for `gnss-degradation`.
3. **The prediction attached to `scn-006` was falsified.** Clustering still does not discriminate.
   The fix raised recall by shrinking the *denominator*, not growing the numerator: detected staged
   findings per run went 1.2 → 1.4, against a background of 15.5.

**Measurements — do not re-derive these.**

- Corpus background: **137.7 aircraft per quiet run** with a track discontinuity (of ~530 seen). The
  two-clock discriminator narrows it to 24.6 at no cost to the staged margin.
- After the airborne and interior filters: **~15.5 track-gap findings per run**, staged or not.
- Baseline cells over a quiet run: 56 cells, 1,800 samples each, means spanning 0.177 dB, sds
  1.437–1.551. Per-cell and pooled are indistinguishable on quiet data.
- `ST_DWithin` on geography is **not inclusive at its boundary** (34338.94037894 m returns false).
- `ST_ClusterWithin` has **no geography overload**. EPSG:3035 costs ≤ 2.57 m on a 5 km radius across
  the corpus box; raw degrees would cost ~62% between the axes at 52°N.
- A 4326→3035→4326 round trip is **not** exact: 5.0 returns as 4.999999999999997.
- An unordered window partition moved a centroid by **8e-15 degrees** between runs of the same input.
- Background clusters reach **4–5 members** unaided; a run supplies **1–2** staged findings.
- A background cluster sits within the fusion radius of the faulty sensor on **70% of
  `rf-sensor-fault` runs** at 60 km.
- Batch 2 staging yield: **10 of 40 runs stage nothing**, against 3 of 80 in batch 1.

**Database holds two batches.** Batch 1, runs 1–120, original generator. Batch 2, runs 121–180, base
seed `20260916`, airborne gate active. Keep both: the pair is the before/after evidence for `scn-006`.

**Broken and owed:** the **frontend suite exits non-zero**. `pnpm test` reports 81 passed then fails
with `TypeError: control.runs.map is not a function` at `scenarioControl.tsx:344`, from
`navigation.test.tsx`. Two pre-existing `api-010` defects: the test stubs `fetch` with one mock
resolving `json: async () => operationalPicture` for every path, and `useScenarioControl` never checks
the response is an array. **Three earlier handoffs said this suite was green. It was not.**

## Files in flight

None. Working tree clean at `f7a6126`.

## Changed

Commits, newest first: `f7a6126` docs (scn-006 measured, prediction falsified) · `f503986`
feat(scn-006) · `0c0a156` test(scn-006) · `e964222` spec(scn-006 + recall correction) · `37145aa`
feat(anom-011) · `a980fda` feat(anom-004) · `3cd8f04` spec(anom-004 amended, anom-011 added) ·
`75a03ba` docs(clustering measurement) · `b9632f3` feat(db-009) · `9cfe74d` feat(db-004).

Files added: `backend/app/detection/{baseline,rf_noise,track_gap,findings,clustering,sensitivity}.py`,
`backend/app/db/findings.py`, `backend/alembic/versions/0003_detection_findings.py`,
`backend/tests/test_{anom_baseline,anom_rf_noise,anom_track_gap,anom_clustering,anom_sensitivity}.py`,
`backend/tests/test_db_{findings,proximity,clustering}.py`, `docs/phase8_detection.md`.

Docs: `thesis_notes.md` gained 23 subsections; `qa.md` entries 60–67 and 13 glossary terms;
`implementation.md` the Phase 8 ordering note and ticks; `CLAUDE.md` a **new agent instruction** —
explain an item in plain terms before building it, as chat output, never as a file. Progress note at
version 22.

## Failed attempts

**Six assumptions were confidently wrong and measurement caught every one.** All six concerned a
*dependency* or the *data*; none concerned this project's own code, where claims are made by reading
it rather than by recalling documentation.

1. `anom-010` was specified against ten corpus tracks. The real figure is 137.7 per run.
2. `anom-002`'s per-channel requirement was specified as provable against quiet data. It is not.
3. `db-004` was amended to claim `ST_DWithin` is inclusive at the boundary, from the documentation.
   The database disagrees.
4. `db-009` specified grouping "on geography" using a function with no geography overload — both
   halves written in the same sentence.
5. **`anom-011` named a cause rather than counting one.** The conclusion "the recall is too small"
   was right about the number and wrong about the cause: 90% of losses were `on_ground`, and 92% of
   those aircraft were parked for the entire run. Corrected in `qa.md` §66, which supersedes §65
   without editing it.
6. **`scn-006`'s prediction was falsified on its first test.** Recorded in advance, reported against
   interest. The arithmetic that would have have saved it — detected staged findings per run, not
   recall — was available before the prediction was made and was not done.

**Mutation survivors, each a distinct kind.** `anom-002`: a test passing for the wrong reason (the
*next* guard raised). `anom-001`: determinism tested with a single cell. `anom-010`: four, including
one invalid mutation I built. `anom-004`: one **equivalent** mutant — `members[0].started_at` equals
`min(...)` because `db-009` orders by start time, proved equivalent by its `ended_at` twin dying
instantly. `anom-011`: two genuine gaps found and closed, plus one more invalid mutation of mine.

**Two tests written for `scn-006` were deleted before implementation** because they passed against
the unfixed code. Recorded as a deviation, though the rule was followed rather than broken.

**Docker hung ~25 minutes** — a timed-out `make test-backend` left a run container holding a lock.
Check for a stale `em-fusion-backend-run-*` before blaming the database. I also misread the resulting
`Error 137` as a pass.

**Four empty files leaked into `backend/`** from `docker compose run -v file:/app/x.py` — `/app` is
itself a bind mount of `./backend`, so Docker created the mount points on the host. Remove them after
any container-mounted measurement.

**`make lint` had not been run after `db-004`**, so two E501 violations reached main. The root
`make check` has still never been run in full.

**`psql -U em_fusion` fails** — the role is `postgres`.

## Next step

**Route B was chosen and measured; `anom-012` is written and unbuilt.** The path is now clear.

1. **Build `anom-012`** — the local rate excess. Findings per unit time inside a disc during a
   window, over the same disc outside it. Centre and window come from a detected RF episode, never
   from ground truth (`api-009`). Measured before it was specified, over 20 seed-matched pairs:
   30 km catches 5 of 20 staged and fires on 2 of 20 controls; 45 km, 10 and 5; 60 km, 16 and 9.
   **Do not fix a radius from that curve.** Fisher's exact gives p=0.407, 0.191 and 0.048 — only the
   widest point separates from its control at all — and Wilson intervals are about ±20 points, so
   choosing a radius from it would be choosing from noise. A second independently seeded batch is
   required first, on `anom-011`'s terms. Youden's J is 0.15–0.35 against a scale where 0 is a coin
   flip; the radio side of the same system is beyond five sigma, so **the two halves of the fusion
   evidence are not comparable in strength** and `anom-005` must not treat them as equal votes. The
   direction of the false-attribution improvement is supported (14/20 [48–85] against 2/20 [3–30]);
   the headline "70% to 10%" was overstated when first written and is corrected in `qa.md` §69.
2. **Settle the ordering of `anom-005`, `anom-006` and `anom-007` before fixing any threshold.**
   `anom-007` separates a sensor fault from interference on the **RF pattern alone** — one sensor
   abnormal, spatial neighbours nominal — which is a far stronger signal than any track evidence
   measured. If it claims those runs first, `anom-012`'s threshold is read from the sensitive end of
   its curve (16 of 20) rather than the specific end (5 of 20). This has never been written down and
   needs a decision, possibly a spec item.
3. **Then `anom-005`** (amended onto `anom-012`), `anom-006`, `anom-007`.

**Rejected, with the reason recorded** so it is not revisited by accident: raising the 8% affected
fraction or splitting the incident radius until clusters stand out. The radius split is a real
structural defect — `IncidentParameters.radius_km` is one number serving the RF side's need for a
**large** zone (the `scn-005` band, so a zone contains some receivers and excludes others) and the
track side's need for a **small** one, with the track half reusing the RF number and the docstring's
entire argument being about receivers. It is worth fixing on its own merits, but **not** as a route
to making clustering work: a parameter chosen by searching for a value where the detector succeeds
makes every later metric a measurement of that search.

Owed, unowned:

- The frontend suite's non-zero exit and `useScenarioControl`'s malformed-success crash.
- **Campaign sizing**: at a 75% staging yield, 150 staged incidents needs ~200 runs, not 150. And a
  run that stages nothing must be excluded from recall explicitly (`measure_recall` refuses it) but
  must not be counted as a staged run in precision or FPR either — `eval-002` needs to say so.
- `adp-008`'s exclusion list is **not applied to baseline windows** — owed to the generator.
- Detection latency has no definition. Track 0, gates `anom-009`.
- `anom-008`'s threat to validity must be reported in `eval-002`.
- `anom-003` (z-score) carries the `db-008` extensibility prediction, now scored once as a **partial**
  by `anom-004`: storage untouched, but `subject` had to widen from one thing to several.
- `api-011`, `nav-002`, reset and replay endpoints, `ops-002` (CI).
- `docs/qa.md` has a duplicate §47. Fix by note, never by renumbering.
- Frontend has no coverage tooling; `pnpm format` has not been run; mypy does not check `tests/`.
