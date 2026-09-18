# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
it fuses replayed aviation telemetry and synthetic RF observations through a Data Abstraction Layer,
detects deviations deterministically, and turns evidence bundles into schema-validated,
grounding-checked AI hypotheses for an analyst to review. Decision support, never autonomous
decision-making.

This session cleared the decision the detection layer had been blocked on. It moved **the
measurement kit into the repo**, because every detection figure the project quotes was produced by a
script living in a session-scoped temporary directory — the conclusions were committed and the
reproduction was not. It built **`anom-014`** and **`scn-007`**, the two items specified and
deliberately left unbuilt because both change how the corpus is *made*; **`scn-008`**, so a run
records the batch it came from, which the first corpus never did; and **`db-010`**, an index the
`observations` table had been missing since its first migration. It then **regenerated the corpus**
and **re-measured the whole detection layer** against it.

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
- `d341e71` docs: detection layer, handoff, and the two measured parameters
- `f7a4ec4` docs: register the two new measurements and their logs of record
- `9d5ac83` feat(anom-014, scn-007): 925 passed on the database tier - both pass
- `1a68b8d` / `5a55dfd` / `28764be` spec, tests and build for **`scn-008`**
- `0d5d1ad` fix(scn-007): withdraw the floor's first measurement, re-measure cleanly
- `2a3019d` docs: record the corpus v2 base seeds **before** generating
- `424f90d` docs: a corpus selector, so two corpora cannot be mixed by accident
- `046d898` fix(measurements): point the kit at corpus v2, **including the baseline**
- `b9e28b7` / `10280ae` spec and build for **`db-010`**, with migration `0004`
- `e48a8e1` / `4981fc3` the v2 re-measurement and its logs of record
- `c17a393` spec: re-open `anom-006`; re-measure `anom-005`'s gate
- `a7c7520` docs: the regeneration written up in `thesis_notes.md` and `detection_layer.md`
- `8c04f8d` docs: handoff and **progress note v27**
- New: `CORPUS_V2_PLAN.md`, `backend/measurements/corpus/_corpus.py`,
  `backend/alembic/versions/0004_observations_run_index.py`,
  `measurements/mutation/mutate_scn008_batch_provenance.py`
- Changed: `app/scenario/emitter.py` (`BatchProvenance`, `with_batch`), `app/pipeline.py`
  (supplies the batch), `docs/spec.jsonl` (`scn-008` and `db-010` added; `anom-005`, `anom-006`,
  `anom-014` amended), `docs/qa.md` §78

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
- **Four measurement scripts hardcoded `range(101, 121)` as the quiet runs** — v1's
  `normal-baseline` block. Pointed at v2 they would have built the **baseline** from the old corpus
  while measuring the new one, which is the most damaging place the two could be mixed because the
  baseline is what "normal" means. Found by reading the scripts rather than by any failure. Now
  `_corpus.quiet_runs()`.
- **My own first patch to `fusion_gate_decision.py` made it worse**, writing
  `WHERE <v2 filter> OR scenario_type='normal-baseline'` — the `OR` pulled in both corpora's quiet
  runs. Caught on the next pass.
- **The `0004` migration was written with `down_revision = "0003"`** where the convention is the full
  stem `0003_detection_findings`. That left a broken chain and two heads, and **all 27 schema tests
  failed at once**, which is the right way for it to fail. Revision ids are now noted in the repo map.
- **`rf_noise_episode_duration.py` crashed on the v2 corpus** with `min() arg is an empty sequence`.
  Not a regression: `anom-014` means the false-episode population it characterises is now empty by
  construction. The script reports that as the finding instead of crashing.
- **A figure that looked like the one regression was a broken metric.** "Centre error" moved from a
  median of 0.0 km to 45.3 km with a max of 107.5 km. Those are **exactly this layout's minimum and
  median receiver separations**: the metric compared the dismissed receiver against `sensors[0]`, an
  arbitrary member of the staged set, so it was reporting the distance between two correct answers.
  Measured against the *nearest* staged receiver it is 0.0 km on every run. **A figure matching a
  constant of the apparatus is probably measuring the apparatus.**

## Next step

The regeneration is done and the detection layer is re-measured, so nothing is blocked on a corpus
decision any more. Three items are buildable; the order below is a recommendation, not a constraint.

1. **`anom-006`'s threshold measurement — do this first, it is cheap and decisive either way.**
   The regeneration moved zone-level scoring from chance to 20:7 at a 20 km cluster radius, which is
   why the item was re-opened. That figure compares a staged run against *its own control*, and a
   detector has no control: it sees one run and must decide. So the measurement to take is whether a
   **fixed threshold separates a staged zone from an unstaged one on a single run** — sensitivity and
   false-alarm rate across a sweep, on the v2 corpus, with the quiet arm as the negative population.
   If it separates, build the rule against that curve. **If it does not, close the item again with
   the evidence** — that is an honest outcome and it retires a stated threat to validity either way.
   It is now minutes of work rather than hours, because of `db-010`.
2. **`evb-001`, evidence bundles.** The natural consumer of what the ladder now produces, and the
   gateway to Phase 9 — the AI hypothesis layer, which is the project's actual contribution. It is
   also the one remaining item **no corpus change can invalidate**, because a bundle groups what the
   rules already emit and its shape does not depend on the data. Build it whichever way `anom-006`
   falls.
3. **`anom-003`, the z-score detector.** Carries the `db-008` extensibility prediction, scored once
   as a partial. Now genuinely measurable, since the corpus is stable and homogeneous — which it was
   not when this was last listed as "buildable now".

### Open and unowned

- **The `aircraft-coverage-gap` arm still has no rule.** Its 60 of 60 correct non-detections are
  correct only because nothing judges that arm. Must not be reported as though the system had been
  tested on it. Item 1 above is what retires this.
- **Fusion is still the radio evidence with an occasional corroborating note.** 41 of 60 reported
  zones have no measurable track side, improved from 47 of 61. Any write-up claiming multi-source
  fusion must say so plainly.
- **Corpus v1 is still in the database** and always will be (`db-007`). Every measurement must go
  through `measurements/corpus/_corpus.py`. Three scripts still select runs by other means and were
  not on the re-measurement path — `cluster_background.py`, `cluster_separation_after_scn006.py`,
  `track_gap_hit_rate.py`, `track_gap_recall.py`, `staging_on_ground.py`, `cluster_leak_into_fusion.py`,
  `rate_excess_two_forms.py`, `sensor_fault_fragmentation.py` and
  `sensor_fault_neighbour_candidates.py` should be checked before any of them is quoted again.
- **`DEFAULT_AFFECTED_FRACTION` is now inert.** With a mean eligible pool of 23.4, `round(0.08 x 23.4)`
  is 2 and the floor of 5 always wins, so every v2 run stages exactly five aircraft. Good for
  evaluation — no variance in difficulty between runs — but nobody should read the fraction as doing
  work. Revisit if the pool ever grows.
- A **broadband generation arm**, without which `anom-007`'s Medium and Low confidence bands have no
  corpus behind them. All 300 v2 runs are narrowband, as all 240 v1 runs were.
- The **frontend suite exits non-zero**: `TypeError: control.runs.map is not a function` at
  `scenarioControl.tsx:344`. Needs a spec item covering both the test stub and `useScenarioControl`'s
  missing array check.
- `adp-008` exclusion applied to baseline windows; a detection-latency definition (gates `anom-009`);
  `api-011`; `nav-002`; reset/replay endpoints; `ops-002` (CI); `docs/qa.md` duplicate §47 (fix by
  note, never renumber); frontend coverage tooling; `pnpm format`; root `make check` never run in
  full; mypy does not check `tests/`.
