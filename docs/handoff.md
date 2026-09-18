# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
it fuses replayed aviation telemetry and synthetic RF observations through a Data Abstraction Layer,
detects deviations deterministically, and turns evidence bundles into schema-validated,
grounding-checked AI hypotheses for an analyst to review. Decision support, never autonomous
decision-making.

This session did two things the previous one had left as open decisions. It moved **the measurement
kit into the repo**, because every detection figure the project quotes was produced by a script
living in a session-scoped temporary directory — the conclusions were committed and the reproduction
was not. Then it built **`anom-014`** and **`scn-007`**, the two items that had been specified and
deliberately left unbuilt because both require regenerating the corpus. Both are built, both
parameters were measured rather than chosen, and the regeneration itself has **not** been run.

## Current state

**The corpus has been regenerated and the whole detection layer re-measured.** Corpus v2 is 300 runs
in twelve batches of twenty, from three base seeds recorded *before* generation, one generator, one
run length, every run carrying its batch provenance. **45 spec items passing of 98.** Unit tier 748
passed; database tier 934 passed; ruff and mypy clean.

### Corpus v2

| | v1 (240 runs, ids 1-240) | v2 (300 runs, ids 241-540) |
|---|---|---|
| Generator versions | **three** | one |
| Run length | 600 s and 900 s | 900 s throughout |
| Base seeds recorded | one, by accident | **all three, on every row, re-derivable** |
| Runs staging no aircraft | 11 of 40 | **0 of 60** |
| Seeds carrying all five arms | none | **60 of 60** |

Base seeds: `1412660662`, `965530111`, `655209063`, recorded in `CORPUS_V2_PLAN.md`. Every staged run
now has a same-seed `normal-baseline` twin, which v1 never had.

**Both corpora are in the database** (`db-007` forbids deleting). `measurements/corpus/_corpus.py`
selects between them **on the recorded base seed, not an id range** — `parameters->>'base_seed' IS
NOT NULL` names v2 exactly and survives re-runs and shifted ids. Default v2, `CORPUS=v1` overrides.

### What the re-measurement said, in both directions

| Measurement | v1 | v2 |
|---|---|---|
| Spurious sensor faults, all arms | 17 | **0** |
| False `anom-001` episodes | 80 | **0** — population empty by construction |
| Zero-length episodes | 300 of 1257 | **0 of 1137** |
| Ladder, all five arms | 60/60, 60/60, 20/20, 75/80, 19/20 | **60/60 on all five** |
| Zones given two answers | 0 | **0** |
| Rate excess, median | 3.87 | **9.61** |
| Runs clearing the threshold | 26 of 40 | **58 of 60** |
| Unusable windows | 7 | **0** |
| Corroborated zones | 7 of 61 | **18 of 60** |
| **Not measurable** | 47 of 61 | **41 of 60** |
| `anom-006` run-level excess | +1.0 | +2.7 (against sd 3.3 — still 0.8 sd) |
| `anom-006` zone-level, 20 km | 7:3 (chance) | **20:7** |

**`anom-006` is re-opened, as buildable-to-try and not as known-buildable.** The zone-level signal is
real, but a sign test over matched pairs says the staged zone *tends to* beat its control and says
nothing about whether a single-run threshold separates them — which is the question a detector faces.
The threshold measurement comes before any threshold. Recorded on the item.

**The fusion limitation stands.** 41 of 60 reported zones still have no measurable track side. Better
than 47 of 61; the same sentence.

### Also built this session

- **`scn-008`** — batch provenance on every run row, verified against real data: every run re-derives
  its own seed from what its row records. 10 of 11 mutants killed, survivor unreachable.
- **`db-010`** — `observations` had **no index on `scenario_run_id`**, a foreign key with
  `ON DELETE CASCADE`, on a 20.7M-row 12 GB table. Every measurement was running one sequential scan
  of the whole table *per run*. Migration `0004`. Index scan now, 135 ms.
- **The measurement kit** is in the repo at `backend/measurements/` — 47 files, each with its
  committed log of record, plus a README carrying the run commands and the re-measurement protocol.

## Files in flight

Tree is clean apart from the documentation commit this handoff belongs to. `anom-014` and `scn-007`
are both at `passes: true`.

## Changed

- `bb08323` docs: move the measurement kit into the repo
- `dff3756` spec: amend anom-014 — suppressed episodes are their own kind, not unjudged cells
- `aa6a551` test: add tests for anom-014
- `b8ad5c2` spec: amend scn-007 — the floor needs a survey pass the seam cannot do; tests for scn-007
- `8599376` feat(anom-014, scn-007): the minimum duration and the staged-aircraft floor
- `7088f3c` feat(anom-014): the minimum episode duration is 10 s - tests pass
- `6cbe3fd` test: close four scn-007 gaps a mutation pass found
- `eacb6fe` feat(scn-007): the staged-aircraft floor is 5 - tests pass
- New: `backend/measurements/` (45 files incl. README), `measurements/corpus/rf_noise_episode_duration.py`,
  `measurements/corpus/scn007_floor.py`, `measurements/mutation/mutate_anom014_minimum_duration.py`,
  `measurements/mutation/mutate_scn007_floor.py`
- Changed: `app/detection/rf_noise.py` (`SuppressedEpisode`, `minimum_duration`,
  `DEFAULT_MINIMUM_DURATION`), `app/scenario/tracks.py` (`TargetSelection`, `select_targets`,
  `TrackPerturbation.admits`, `DEFAULT_MINIMUM_AIRCRAFT`), `app/scenario/incident.py` (three answer-key
  fields), `app/pipeline.py` (the survey pass), `CLAUDE.md` repo map and documents table,
  `docs/thesis_notes.md` (four new Implementation subsections), `docs/qa.md` §78,
  `docs/detection_layer.md` (ladder row, vocabulary, blocking section rewritten)
- Existing `anom-001` fixtures lengthened from one reading to two, so they exercise the shipped policy
  rather than pinning the minimum to zero

## Failed attempts

- **The floor was first measured across two different generators, and the figure was withdrawn.**
  `scn007_floor.py` was run over all 60 seed-matched pairs in the corpus without checking whether
  those pairs came from the same generator. They do not: **runs 1-100 predate `scn-006`'s airborne
  gate** and name a mean of 4.4-5.2 staged aircraft against 1.6-1.9 afterwards, most of the difference
  being parked aircraft `anom-010` correctly refuses. The high-count cells of that curve — six, nine,
  eleven, twelve staged — can only come from the pre-gate blocks, so they were populated by runs whose
  staged aircraft were undetectable by construction. Re-measured on ids 121-240 the answer is still 5,
  but the evidence is different and better: the excess rises monotonically and the honest win rate is
  10 of 10, not 15 of 15. **The script now defaults to the clean range.**
- **The corpus is not one corpus**, which is how the above was found. Runs 1-20 are **600 s** where
  every later run is 900 s (22,470 track observations against 33,779 for the same seeds); runs 1-100
  predate `scn-006`. Runs 41-60 are runs 1-20 regenerated at the corrected length, which is why 20
  seed/type pairs look like duplicates — the `aircraft-coverage-gap` arm is **80 runs over 60 distinct
  seeds**, and any figure quoted "of 80" weights twenty of them twice. The ladder's 75-of-80 row is
  affected; `source_gap_ceiling.py` escaped it by restricting to ids 121-240.
- **Two `make test-backend` runs were started concurrently against the same `test_em_fusion`
  database**, producing 18 failures and 65 errors in the schema tests. Cause was a `;` where an `&&`
  was meant: `ruff && mypy ; make test-backend` ran the suite even though ruff had failed, and a
  second run was then launched on top of it. Nothing to do with the code. **Never run two database
  tiers at once — they create and drop the same schema.**
- **A floor of zero is not a no-op**, which was assumed when the placeholder was committed. The old
  rule drew each aircraft's derived value against the fraction; the new rule takes
  `round(fraction x pool)`, which on a small pool is deterministically **zero**. So the placeholder
  converted an occasional empty answer key into a guaranteed one, and three database tests failed
  immediately. An expected count and a draw have the same mean and different behaviour at the bottom.
- **My own test claimed a floor of zero restored the previous behaviour.** It does not, for the
  reason above. The test was renamed and now asserts the opposite, with the reason attached.
- **Six mutants survived the first `scn-007` pass**, four of them genuine. The order-independence test
  could not see an unranked selection, because a small set of strings iterates the same way however it
  was built; and the different-seed test could not see an unseeded ranking, because changing the seed
  *also moves the zone centre*, so the pool changed too and the sets differed for the wrong reason.
  Four tests added; 17 of 19 now killed.
- **`scn007_floor.py` failed twice before producing anything**: `BoundingBox` is exported from
  `app.detection.track_gap`, not `app.dal.models`; and `detect_track_gaps` returns a plain tuple of
  findings, not a two-tuple — an over-correction of a note in the previous handoff.
- **Three measurement containers plus a test suite were left competing for one postgis**, which turned
  10-minute jobs into 30-minute ones. The ladder re-run was killed as redundant once
  `rf_noise_episode_duration.py` had proved the relocated kit runs.
- Measurement scripts print nothing until they finish. `python -u` does not help when every `print`
  is after the loop; a long run looks identical to a hung one. Worth adding progress output before
  the re-measurement.

## Next step

**The regeneration has not been run, and one decision gates it: which base seeds.** The originals
were never recorded, so full reuse is not available. The recommendation on the record is **fresh
seeds throughout**, reported as a new corpus under stated conditions, rather than a partially-paired
one where some runs are comparable and some are not.

1. **Regenerate the batches** with both items active. Record the base seed and run-id range per batch
   this time — the absence of that record is what removed the option above.
2. **Re-measure, in this order**, per `backend/measurements/README.md`: `sensor_fault_catch_rate` →
   `rate_excess_window_source` → `fusion_gate_decision` + `fusion_excess_distribution` →
   `source_gap_ceiling` → `ladder_end_to_end`. **Diff each new log against the committed one** and
   report every figure that moved, including ones that moved favourably.
3. **`anom-006`**, only after the re-measurement, repeating the seed-matched pair measurement before
   any threshold in it is chosen. It may still not be buildable; that is an honest outcome.
4. `anom-003` (z-score) — note that it is buildable now but **not measurable** before the
   regeneration, since its figures would read through `anom-002`'s baselines.
5. **`evb-001`**, evidence bundles — genuinely independent of the regeneration, because a bundle
   groups what the rules already emit and its shape does not change when the corpus does.

### Open and unowned

- **The progress note has not been updated** for `anom-014`, `scn-007`, or the measurement kit. It is
  at version 26 and now understates what exists.
- **The `aircraft-coverage-gap` arm still has no rule.** Its correct non-detections must not be
  reported as though the system had been tested on that arm.
- **Fusion is still the radio evidence with an occasional corroborating note.** Whether the
  regeneration changes the 47-of-61 unmeasurable figure is the first thing to check after it.
- A **broadband generation arm**, without which `anom-007`'s Medium and Low confidence bands have no
  corpus behind them.
- The **frontend suite exits non-zero**: `TypeError: control.runs.map is not a function` at
  `scenarioControl.tsx:344`. Needs a spec item covering both the test stub and `useScenarioControl`'s
  missing array check.
- `adp-008` exclusion applied to baseline windows; a detection-latency definition (gates `anom-009`);
  `api-011`; `nav-002`; reset/replay endpoints; `ops-002` (CI); `docs/qa.md` duplicate §47 (fix by
  note, never renumber); frontend coverage tooling; `pnpm format`; root `make check` never run in
  full; mypy does not check `tests/`.
