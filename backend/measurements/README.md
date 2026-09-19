# Measurements

The instruments behind the numbers in `docs/thesis_notes.md`.

Every detection figure this project quotes — `anom-007`'s 60 of 60, `anom-012`'s trade-off curve,
`anom-005`'s gating decision, `anom-006`'s ceiling — was produced by a script, and until now those
scripts lived in a session-scoped temporary directory while only their *conclusions* were committed.
The reasoning survived and the reproduction did not. This directory closes that gap: a claim in the
write-up should be re-runnable, not just re-readable.

These are **research instruments, not application code**. They ship no behaviour into the product,
have no tests of their own, and are deliberately outside `app/` and `tests/` — so `make lint`,
`make type-check`, `make test` and the coverage gate never see them (all four name `app/` and
`tests/` explicitly, and `testpaths = ["tests"]`). The trade-off is real and worth stating: nothing
here is linted or type-checked, so it can rot silently against the code it measures. What guards
against that is the committed **log of record** beside each script — re-run it and diff.

## How to run one

`./backend` is bind-mounted to `/app`, so these are already inside the container. Nothing needs
mounting, which is what the old `-v <script>:/tmp/x.py` dance was working around.

```bash
# a corpus measurement — needs postgis up and a generated corpus
docker compose run --rm --no-deps -T -e PYTHONPATH=/app backend \
  python measurements/corpus/ladder_end_to_end.py

# with its knobs, where it has any
docker compose run --rm --no-deps -T -e PYTHONPATH=/app -e RUN_LO=121 -e RUN_HI=180 \
  -e BATCH_LABEL="batch 3" backend python measurements/corpus/track_gap_recall.py

# a mutation pass — needs only the repo and backend/.venv, no database
cd backend && .venv/bin/python measurements/mutation/mutate_anom007_sensor_fault.py
```

`PYTHONPATH=/app` is not optional: `python /app/measurements/...` puts the *script's* directory on
`sys.path`, not `/app`, and `import app` then fails. `DATABASE_URL` is already in the container
environment.

A corpus measurement over all 240 runs takes minutes, not seconds — it rebuilds the baseline from
the 20 quiet runs and re-runs the detectors over 9.06M observations. Redirect to a log and read the
log.

Three practical things, each learned the hard way:

- **Most of these scripts print nothing until they finish**, because every `print` sits after the
  loop. `python -u` does not help with that, so a long run looks exactly like a hung one. To tell
  them apart, ask the database what it is doing rather than watching the log:
  `docker compose exec -T postgis psql -U postgres -d em_fusion -c "SELECT state, now()-query_start
  FROM pg_stat_activity WHERE datname='em_fusion' AND state='active';"`. New scripts should print
  per-run progress.
- **Do not run several of these at once.** They each stream millions of rows, and three in parallel
  turned ten-minute jobs into thirty-minute ones with no work saved.
- **Never run two `make test-backend` at once.** Both create and drop schema in the same
  `test_em_fusion` database, and the result is dozens of unrelated-looking schema errors. This has
  already happened once and cost a full diagnosis.

## `corpus/` — measurements over stored runs

**The database holds two corpora, and every script here must say which one it means.**
`corpus/_corpus.py` is the selector: import it rather than hardcoding an id range.

| | Runs | What it is |
|---|---|---|
| **v1** | ids 1–240 | **Three generator versions.** Runs 1–20 are 600 s where everything later is 900 s; runs 1–100 predate `scn-006`'s airborne gate and name ~5 staged aircraft against <2 afterwards, mostly parked ones `anom-010` refuses. |
| **v2** | ids 241 on | One generator, 900 s throughout, `anom-014` and `scn-007` active from run one. Base seeds recorded in `CORPUS_V2_PLAN.md` and on every run row. |

The discriminator is **the base seed, not the id**: `scn-008` records it and nothing before it did, so
`parameters->>'base_seed' IS NOT NULL` names v2 exactly — and keeps naming it correctly if ids shift,
a batch is re-run, or a third corpus appears, none of which an id range survives. Default is v2;
`CORPUS=v1` overrides.

Mixing them is not theoretical. `scn-007`'s floor was first measured across the `scn-006` boundary
and the figure had to be withdrawn, on a corpus spanning only *two* generators.


Each needs the database and a generated corpus. **The figure of record is what the committed `.log`
said**; a script with no log is marked, and its figure lives in `docs/thesis_notes.md`.

### The sensor-fault rule (`anom-007`)

| Script | The question it answers | Figure of record |
|---|---|---|
| `sensor_fault_catch_rate.py` | Does `SENSOR-FAULT` claim the runs whose truth is a broken receiver — and does it claim anything else? The assumption the whole rule ordering rests on. | 60 of 60 claimed, on the right receiver inside the right window; **0 of 60** interference runs misattributed; 1.13 faults per run at a median span of exactly the staged 300 s. *(no log survived)* |
| `sensor_fault_fragmentation.py` | Why does a receiver with loud neighbours read as isolated? | One 300 s incident arrives as a **median of six episodes**: the 8 dB injection is scaled per tick by `1 + 0.25·N(0,1)` against a 6 dB threshold, so ~1 tick in 6 falls short. Neighbours sat 2.51 dB (p5) to 4.46 dB (median) above their own baselines and **not one of 37 crossed 6 dB**. *(no log survived)* |
| `sensor_fault_neighbour_candidates.py` | Tolerance, or readings? Two candidate repairs measured **before either was written**. | Readings win. Also the source of the 2 dB bar: touched neighbours 2.51 dB at p5, untouched 1.58 dB at p95, and the choice is a plateau. *(no log survived)* |

| `rf_noise_episode_duration.py` | What minimum episode duration should `anom-014` use? Measures the two populations a minimum has to separate. | **Total separation.** All 80 episodes outside a staged cell or window are **exactly one reading long**; the 1,257 on a staged cell run to a median of 20 s. A 10 s minimum removes 80 of 80 and still catches **140 of 140** runs that stage RF. 10/20/30 s are a plateau; the bottom is taken because larger values discard more true episodes for no gain. |

### The staged-aircraft floor (`scn-007`)

| Script | The question it answers | Figure of record |
|---|---|---|
| `scn007_floor.py` | How many staged aircraft does a coverage-gap run need before it is findable at all? **Defaults to runs 121-240** — see below. | Over the 40 post-`scn-006` pairs the excess rises monotonically (+0.7, +1.0, +2.0, +2.5, +3.0 at one through five staged) and the win rate goes from **13 of 19** below three to **10 of 10** at three to five. Floor set at 5, which is also the most any clean run stages, so the curve cannot be read further. Background: 15.1 findings per control run, sd 3.5. |

**This script must not be run over the whole corpus.** Its first version was, and the resulting figure had to be withdrawn. Runs 1-100 predate `scn-006`'s airborne gate and name a mean of about five staged aircraft against fewer than two afterwards, most of the difference being parked aircraft `anom-010` correctly refuses; runs 1-20 are also 600 s where everything later is 900 s. Measured across that boundary the high-count cells fill with runs whose staged aircraft were never detectable, and the curve flattens. The default range is the clean region and `RUN_LO`/`RUN_HI` override it only for deliberately looking at the old generator.

### The rate excess (`anom-012`)

| Script | The question it answers | Figure of record |
|---|---|---|
| `rate_excess_two_forms.py` | Naive ratio, or difference-in-differences? Knobs: `RUN_LO`, `RUN_HI`. | Form 2. The naive form is confounded by the temporal edge effect — the window sits mid-run where detection is easiest, so **control runs score 2.95** on it. *(no log survived)* |
| `rate_excess_window_source.py` | Does the measured curve describe what the rule will actually be given? | **No.** Window length against a staged 300 s: truth 300 s, `anom-001` episode **median 90 s**, `anom-007` assessment **median 320 s**. Re-scored at the pre-registered thresholds with the realistic window: **18 / 21 / 26 of 40** at 30 / 45 / 60 km, against 15 / 20 / 28 from truth-seeded windows. Six of 86 runs give a **zero-length** window, which divided by zero inside the rule — a real defect, now refused. |
| `rate_excess_prereg.md` | Not a script. The pre-registration **written before batch 3 existed**, fixing thresholds at 1.79 / 1.79 / 1.58 and stating in advance what agreement and disagreement would look like. | Its evidential weight is entirely in having been written first. Do not edit it. |
| `pool_batches.py` | Helper: pool two batches and recompute Fisher's exact and the Wilson intervals. Pure arithmetic, no database. Usage: `pool_batches.py 'r tp n fp n' ...` | — |

### The fusion rule (`anom-005`)

| Script | The question it answers | Figure of record |
|---|---|---|
| `fusion_gate_decision.py` | Should the rule **gate** on the rate excess, or carry it as evidence strength? | The trade-off curve answers a question the rule never faces. Zones reaching step three: **40 of 40** gnss-degradation, **0 of 40** coverage-gap, **0 of 20** quiet, **1 of 40** sensor-fault. A gate would report 26 and **reject nothing**, because nothing false arrives there. |
| `fusion_excess_distribution.py` | What would a gate actually reject? | Median 3.87, p75 11.47. The **14 runs a gate would lose all hold 4 or fewer** track findings in the whole run; 5 hold none during the window, 2 none anywhere. The gate would reject an interference report on the grounds of low traffic density. |
| `fusion_zone_shape.py` | How many receivers does a zone span, and what should set its confidence? | 34 zones of 2 receivers, 6 of 3. Peak deviation 11.9–15.9 dB (median 13.4) — beyond five sigma, which is why confidence has a **floor of Medium the track side cannot breach**. |

### The source-gap rule (`anom-006`) and what blocks it

| Script | The question it answers | Figure of record |
|---|---|---|
| `source_gap_ceiling.py` | **Can this rule be built on this corpus at all?** Measures the ceiling, not a design. | No. Over 40 seed-matched pairs: 16.1 findings against the control's 15.1 and **never fewer** (23 greater, 17 tied, **0 lower**) — real beyond doubt, and one in fifteen. Root cause: **1.7 staged aircraft per run, 11 of 40 staging nothing at all.** This is the measurement that forced `scn-007`. |
| `source_gap_zone_scoring.py` | Does a staged gap **concentrate** anywhere a detector could find? | No — **at chance**: 7:3, 5:4, 4:2 at 20/40/60 km cluster radii. The machinery destroys a signal raw counting preserves. |
| `mutation/mutate_evb001_bundle.py` | **Are `evb-001`'s tests load-bearing?** 34 mutants over the typed-absence boundary, the per-item data mode, the unit of a bundle, the frequency axis, and the scoping of superseded claims. | **34 of 34 killed** — after a first pass killed only 22. The 10 genuine survivors were **all scoping rules**: evidence from another receiver, another window, another zone. The suite had tested what goes *into* a bundle and barely what must stay *out*, which is the more dangerous half, because a bundle carrying a neighbouring event's evidence is not malformed — it is wrong. 7 tests added, 2 tightened. |
| `ladder_suppression.py` | **Does `anom-013`'s suppression ever fire?** `ladder_end_to_end.py`'s "conflicting" counter records runs reporting two anomaly *types* and never inspects `Resolution.suppressed`, so its zero says nothing about suppression. | **Never. 188 claims bid, 0 suppressed.** `gnss-degradation` bids 60 over 60 runs; `rf-sensor-fault` and `ambiguous-mixed-evidence` bid **64** each, so four runs of each produce two claims — two claims in a run is not rare, two claims **for one zone** has never happened. Read the ladder's 60/60 as evidence it declines to merge separate events, **not** that it arbitrates competing ones. |
| `evidence_ref_uniqueness.py` | **Does a finding's `evidence_refs` coordinate identify exactly one observation?** Decides whether `evb-002` resolves by coordinate or the `from_*` functions must record row ids. Also checks the ISO round trip and what one lookup costs. | **Unique, everywhere.** RF by `sensor_id + channel_index + timestamp` and track by `aircraft_id + timestamp` are unique within a run across **both** corpora — 20.7M rows, worst collision 1, **zero** colliding coordinates. ISO round trip exact on 2,000 sampled rows. So `evb-002` resolves by coordinate and no rule adapter changes. **Cost: 64.7 ms per lookup**, index scan on `ix_observations_scenario_run_id` with **38,424 rows removed by filter** — a composite index would be wanted if bundles carry many items. |
| `arm_rf_identity.py` | Is `ambiguous-mixed-evidence` a duplicate of `rf-sensor-fault`, or a control? Digests both arms' RF streams at every shared seed. | **A control, and it must not be dropped.** Same receiver, window and elevation 60/60, and the RF stream is **identical byte for byte in 60 of 60 pairs** — the only staged difference is five removed aircraft. So both arms being decided `possible_sensor_fault` 60/60 is a measured immunity result: a simultaneous track-side disturbance does not perturb the RF verdict. Carries the ordering trap in its docstring — the first version digested rows ordered by a payload key that does not exist, so every row sorted equal and 4 of 60 pairs looked like generator differences. |
| `source_gap_threshold_sweep.py` | **The detector's own question**: does a *fixed* threshold separate a staged gap from an unstaged run on a **single run**, with no control? Pre-registered in `source_gap_threshold_prereg.md`; fitted on two base seeds and scored once on the third. | **No, and it points the wrong way.** Best zero-false-alarm point (60 km, size floor 4, threshold 11.53) catches **3 of 20** on the holdout against a pre-registered bar of 0.25 — but fires on **6 of 20 `gnss-degradation`** runs, twice the rate of the arm it is for. Best Youden's J anywhere is 0.275, at a 0.38 quiet-arm rate `anom-008` forbids. **This is what closed `anom-006` the second time.** Also established, exactly: `normal-baseline` ≡ `rf-sensor-fault` and `aircraft-coverage-gap` ≡ `ambiguous-mixed-evidence` on the track side, so the clean negative population is **60 seeds, not 120 runs**. |

### The ladder, and the layers underneath it

| Script | The question it answers | Figure of record |
|---|---|---|
| `ladder_end_to_end.py` | The whole reportable-rule ladder as one decision over every stored run. | 60/60 sensor-fault, 60/60 interference, 20/20 ambiguous (as a sensor fault, by design), 75/80 coverage-gap silent, 19/20 quiet silent. **No zone in any run received two answers** — `anom-013`'s first failure case, and it does not occur. Corroboration across every interference zone: 7 corroborated, 7 not, **47 not measurable**. |
| `cluster_background.py` | Does the quiet-run background ever cluster into something reportable? | The largest cluster on a staged run **equals** the largest on its own seed-matched control, in eight triples of eight. This is why `anom-004` carries no severity. *(no log survived)* |
| `cluster_leak_into_fusion.py` | How exposed is the fusion rule to background track clusters on a run whose truth is a broken receiver? | See `docs/thesis_notes.md`. *(no log survived)* |
| `cluster_separation_after_scn006.py` | `scn-006` restored 55% of the signal. Does that change `anom-004`'s answer? | See `docs/thesis_notes.md`. *(no log survived)* |
| `track_gap_recall.py` | Where do the staged aircraft go? Knobs: `RUN_LO`, `RUN_HI`, `BATCH_LABEL`. | Batch 3, repaired generator: **81% / 95%, 0 of 74**. *(no log survived)* |
| `track_gap_hit_rate.py` | Does `TRACK-GAP` find the aircraft the run staged on? Separates a detector that never saw the injection from clustering that cannot discriminate. | See `docs/thesis_notes.md`. *(no log survived)* |
| `track_gap_policy_sweep.py` | Is 21% recall a property of the system, or of the policy I guessed? | See `docs/thesis_notes.md`. *(no log survived)* |
| `staging_on_ground.py` | Is 90% `on_ground` real, or an artefact of how the reasons were ranked? | Real. **55% of every injection was landing on a parked aircraft**, which is what `scn-006`'s airborne gate exists to fix. *(no log survived)* |

## `mutation/` — are the tests load-bearing?

A passing suite proves the tests run; a mutation pass proves they would notice. Each script edits one
source file in place, runs that item's tests, records whether they failed, and **restores the file**.
They need `backend/.venv` and no database.

Read a survivor before fixing it. Three categories came out of these passes and only one is a defect:
a genuine survivor (the tests do not cover that behaviour), an **equivalent mutant** (the edit changes
no observable behaviour), and an **invalid mutant** (the edit I wrote does not mean what I intended).

| Script | Target | Result of record |
|---|---|---|
| `mutate_db009_clustering.py` | `app/db/findings.py` | — |
| `mutate_anom004_clustering.py` | `app/detection/clustering.py` | — |
| `mutate_anom005_fusion.py` | `app/detection/fusion.py` | every genuine mutant killed, one proven equivalent |
| `mutate_scn006_tracks.py` | `app/scenario/tracks.py` | — |
| `mutate_anom007_sensor_fault.py` | `app/detection/sensor_fault.py` | **27 of 28 killed, no survivors** (the 28th site removed as a redundant guarantee) |
| `mutate_anom011_sensitivity.py` | the track-gap sensitivity path | — |
| `mutate_anom012_rate_excess.py` | `app/detection/rate_excess.py` | **5 of 5 killed** |
| `mutate_anom013_precedence.py` | `app/detection/precedence.py` | **16 of 16 killed** |
| `determinism_test_reliability.py` | `app/db/findings.py` | Not a mutation pass but the same question one level up: is the determinism test a reliable detector, or did it get lucky once? |

**A mutation score is measured against the tests, and the tests can share the code's wrong
assumption.** `anom-007`'s first implementation passed 36 tests and killed 18 of 20 mutants while
misattributing 21 of 60 interference runs, because both the tests and the code believed that a
neighbour with no reported anomaly is a neighbour reading normally. A high score is evidence the
tests are load-bearing; it is not evidence the rule is right. Only `corpus/` can say that.

## `superseded/`

Earlier iterations, kept because two of them are cited in the write-up as the step that exposed a
defect. Not part of the kit — do not re-run them expecting current numbers.

| File | Why it was replaced |
|---|---|
| `sensor_fault_catch_rate.v1.py` | Scored a fire as correct if it named a staged sensor, **without checking the window** — so a spurious episode on a staged receiver counted as a hit. |
| `sensor_fault_catch_rate.v2.py` | The window check added. This is the run that **exposed the 21 of 60 misattribution**; it measures the pre-fix rule and cannot be re-run meaningfully against the current one. |
| `rate_excess_feasibility.v1.py` | Naive ratio only, before the difference-in-differences form. |
| `track_gap_recall.v1.py` | Whole corpus at once, before `RUN_LO`/`RUN_HI` made it per-batch. |
| `mutate_*.v1.py` | Earlier mutation sites for the same three modules. |
| `rate_excess_window_source.aborted.log` | **Run against thresholds I invented** (1.55/1.32/1.19) rather than the pre-registered 1.79/1.79/1.58. Caught mid-run and restarted. Kept because a discarded run is part of the record. |
| `ladder_end_to_end.pre_merge_fix.log` | Before the one-event-one-zone fix: **160 zones for 60 events**. |

## Re-measuring after a corpus regeneration

Regenerating the batches invalidates every figure above at once, which is exactly why `scn-007` and
`anom-014` are specified to land **in the same regeneration** rather than one at a time. The protocol:

1. Generate the batches, recording the base seed and the run-id ranges.
2. Re-run `corpus/` in this order — later scripts depend on decisions the earlier ones settled:
   `sensor_fault_catch_rate` → `rate_excess_window_source` → `fusion_gate_decision` +
   `fusion_excess_distribution` → `source_gap_ceiling` → `ladder_end_to_end`.

`source_gap_threshold_sweep.py` measures every run in the corpus and takes roughly twenty minutes.
It caches the per-run zone data (ratios and group sizes only — **no identifier and no position**) so
the sweep can be re-read without re-measuring:

```bash
docker compose run --rm --no-deps -T -e PYTHONPATH=/app \
  -e ZONE_CACHE=/app/measurements/.zone_cache.json -e REUSE_CACHE=1 \
  backend python measurements/corpus/source_gap_threshold_sweep.py
```

Drop `REUSE_CACHE` to re-measure from the database. The cache is gitignored — it is derived from the
corpus and regenerable from it, and committing it would put 300 runs of intermediate data in the
history for no gain.
3. **Diff each new log against the committed one** and report every figure that moved, including the
   ones that moved in the project's favour.
4. Re-run `mutation/` only for modules whose code changed.
5. Update `docs/thesis_notes.md` with the new figures *and the conditions they were taken under*,
   then `docs/handoff.md`, `docs/detection_layer.md` and the progress note.

**Record the base seed and run-id range of every batch.** The first corpus did not: `scenario_runs`
holds each run's own derived seed but nothing holds the base seed a batch came from, and only one
of them survives anywhere (batch 3's `20260917`, in `corpus/rate_excess_prereg.md`). That is why a
run-for-run paired comparison across the regeneration is not available, and it is a cheap thing to
avoid repeating.

A figure re-measured under new conditions is a new figure. Replace the old one rather than averaging,
and say in the write-up which corpus each was taken on.

## Two constraints that apply to anything added here

**OpenSky Data License §3(i) and §3(iii).** Aircraft identifiers must be de-identified in anything
published or disclosed, and the data may not leave the institute. Every script here handles
`aircraft_id` by set membership and counting and **never prints one** — and by that point it is
already `dal-004`'s pseudonym, not the source `icao24`. Committed logs were checked and carry no
identifier. Keep it that way: a `print` of an identifier in a script whose log gets committed is the
violation, not the query.

**Never commit `PSEUDONYM_SEED`**, and never let a log capture it. The `"PSEUDONYM_SEED is not set"`
warning at the head of several logs is Compose noise and carries no value.


## A hazard in the mutation harnesses themselves, found 2026-09-19

**A mutation harness that writes a source file and immediately re-runs pytest can score a mutant
against the *previous* mutant's bytecode.** CPython validates a cached `.pyc` on the source's
`(mtime-in-whole-seconds, size)`. The host-venv harnesses run a test file in about 0.1 s, so
consecutive mutants land inside the same second — and two that change the file by the same number of
bytes are then indistinguishable to that check, so the second silently executes the first's compiled
module.

Found on `evb-001`, where two genuinely-killed mutants (`REPLAYED` → `SYNTHETIC`, twice, +1 byte
each) were scored SURVIVED and were killed the moment either was run alone. **The error has no
preferred direction**: it can equally score a real survivor as killed, which overstates a score.

Four harnesses used the vulnerable shape — `PY_BIN -m pytest` directly — and all four are now fixed
with `shutil.rmtree(__pycache__)` before each run plus `PYTHONDONTWRITEBYTECODE=1`. **The three with
published figures were re-run and every score held**: `anom-014` 13/13, `scn-007` 17/19,
`scn-008` 10/11, with the same survivors as before. The remaining harnesses drive `make test-backend`,
whose runs are minutes apart, so the same-second collision cannot occur — they are left alone rather
than changed for symmetry.

**Anything new here must clear the cache.** A mutation score is only evidence if each mutant was the
code that actually ran.
