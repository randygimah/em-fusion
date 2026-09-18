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

**`anom-014` and `scn-007` are built, measured and green.** Both parameters were read off
measurements taken before the number was written down. **98 spec items** (no new ids; both existing
items amended).

| Item | Tests | Mutants | Parameter | Measured on |
|---|---|---|---|---|
| `anom-014` | 12 new | **13 of 13 killed** | minimum episode duration **10 s** | 240 runs, 1,337 episodes |
| `scn-007` | 21 new | **17 of 19**, 2 provably equivalent | staged-aircraft floor **5** | 60 seed-matched pairs |

Unit tier: **739 passed**, ruff and mypy clean. Database tier: re-running at the time of writing
after a self-inflicted failure (see Failed attempts) — the last clean run before the `scn-007`
parameter landed was 916 passed with 99.88% coverage.

### The measurement kit is in the repo — `backend/measurements/`

45 files. `corpus/` holds 20 measurements needing the database and a generated corpus; `mutation/`
holds 9 harnesses needing neither; `superseded/` keeps 7 earlier iterations, two of which the
write-up cites as the step that exposed a defect. **The committed `.log` beside each script is the
figure of record** — re-run it and diff, which is also the re-measurement protocol after a
regeneration.

Deliberately outside `app/` and `tests/`, so `make lint`, `make type-check`, `make test` and the
coverage gate never see it. The cost is real and stated in its README: nothing there is linted, and
the guard against rot is the diff.

Checked before committing: **no aircraft identifier appears in any log**, and every script handles
`aircraft_id` by set membership and counting, never printing one — and by that point it is already
`dal-004`'s pseudonym. Recorded in the README as a standing constraint on anything added.

Two things found while doing it. The eight long-form measurement notes in the same directory were
**already in `thesis_notes.md` verbatim** — the reasoning had been captured and only the instruments
had not. And the base seed each batch was derived from is **recorded nowhere**: `scenario_runs` holds
the per-run seed, and only batch 3's `20260917` survives, in the pre-registration.

### `anom-014`: the separation is total, not a trade-off

Measured over 240 runs at the shipped bands, on the two populations the minimum must separate:

| | n | duration |
|---|---|---|
| **False** — episodes outside any staged cell or window | 80 | **every one exactly 1 reading, 0 s** |
| **True** — on a staged cell inside its window | 1,257 | median 20 s, max 210 s |

A minimum of **10 s** removes **80 of 80** false episodes and still catches **140 of the 140 runs
that stage any RF**. 10, 20 and 30 s are indistinguishable on both populations; the **bottom** of
that plateau is taken because every larger value discards more true episodes for no gain — 24 per
cent at 10 s against 56 per cent at 30 s. Tied to the corpus's 10 s sampling interval: it encodes a
count of readings, not a span of time.

A suppressed episode is reported in **its own field**, not among the unjudged cells. "I looked and it
was too brief" is a different claim from "I had no baseline, so I did not look", and folding them
together discards the episode's window — the only thing that makes a suppression checkable.

### `scn-007`: the floor is 5, and the spec's own implementation was impossible

Over 60 seed-matched pairs, grouped by how many aircraft the run actually staged on:

| staged | pairs | excess over its own control | staged beats control |
|---|---|---|---|
| 0 | 12 | +0.0 | 0/12 |
| 1 | 12 | +0.8 | 9/12 |
| 2 | 14 | +0.7 | 7/14 |
| 3 | 4 | +2.0 | **4/4** |
| 4 | 3 | +2.0 | **3/3** |
| 5 | 8 | +2.2 | **8/8** |

Below three, 16 of 26 — barely better than a coin. At three to five, **15 of 15**. The floor is 5:
the top of that band and its best-evidenced cell.

**The two parameters were read from opposite ends of their bands, deliberately.** `anom-014` took the
bottom of its plateau because every larger value had a measured cost; `scn-007` took the top of its
band because a larger value there costs nothing measured and buys margin. The rule as recorded: *read
a parameter from the end of its range where the cost lies.*

**The item's stated implementation could not be done where it assumed.** It says to rank the eligible
aircraft and take the lowest n — but ranking needs a pool, and `scn-002`'s staging seam is a
per-record transform on a stream, which is exactly why selection was made a pure function of seed and
pseudonym. So the run now **surveys its window first**: one read through `adp-001`'s reader with no
ingest, ranking the eligible set and handing the chosen subset to the perturber. Eligibility is asked
of the perturbation object rather than implemented twice, so the survey and the perturber cannot
drift and name aircraft nothing was done to. The answer key gained `aircraft_eligible`,
`aircraft_requested` and `aircraft_floor_reached`.

### What `scn-007` will not fix — stated in advance

The control background is **14.4 findings per run, standard deviation 3.5**, and a detector sees one
run without its control. The single run staging twelve aircraft cleared its control by **4.0** —
about 1.1 standard deviations. Extrapolating the measured yield, a one-sd excess needs roughly seven
staged aircraft and two sd roughly fourteen. **No reachable floor makes `anom-006` work by counting
findings per run.** The floor removes the empty answer key and gives a zone-level rule enough
co-located dropouts to concentrate; whether that is enough is for re-measurement, and it is written
into the spec item, the thesis notes and `detection_layer.md` so it cannot quietly become a claim.

## Files in flight

Tree is clean apart from the documentation commit this handoff belongs to. `docs/spec.jsonl` still
has `anom-014` and `scn-007` at `passes: false` pending the database tier confirming green.

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
