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

> **Re-measured 2026-09-29, and every count below moved.** The 300-run corpus these figures were
> first taken on was destroyed on 2026-09-19 (`ops-004`). Wave 1 of corpus v2 was regenerated on
> 2026-09-28 for the AI campaign and waves 2 and 3 on 2026-09-29, and the whole protocol was then
> re-run over the **300 runs** that now exist: **every conclusion replicated, and at the same corpus
> size the figures came back within a point or two of the ones that were lost** -- on independently
> drawn seeds, so replication rather than recovery. The corpus was finished deliberately before
> `eval-002` computes anything, so the headline metrics are taken once, on a frozen corpus. Between those two dates the committed logs described a corpus that was not in the
> database, and nothing in the repository said so — which is the argument for diffing a re-run
> against its log rather than trusting that a log exists.

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

> **`CORPUS=v1` now selects nothing, measured 2026-10-01.** The store holds 380 runs, ids 21-400, and **every one carries a base seed** -- v1's runs did not survive the 2026-09-19 destruction, so the predicate that names v1 (`base_seed IS NULL`) matches zero rows. The v1 row above is history rather than a corpus you can select. This matters because nothing refuses an empty population: a script run under `CORPUS=v1` would measure no runs and print figures over nothing. Fixing it means deciding whether v1 is retired outright, which is a decision rather than an edit, so it is recorded here and in `docs/handoff.md` instead.

Mixing them is not theoretical. `scn-007`'s floor was first measured across the `scn-006` boundary
and the figure had to be withdrawn, on a corpus spanning only *two* generators.


Each needs the database and a generated corpus. **The figure of record is what the committed `.log`
said**; a script with no log is marked, and its figure lives in `docs/thesis_notes.md`.

### The store itself: are the runs reproducible? (`eval-001`)

Not a rule and not a figure the detection chapter quotes -- the question is whether anything else
here can be trusted. Every measurement below is taken over runs, and a run that cannot be
regenerated from its recorded seed makes every figure derived from it unverifiable rather than
wrong. Deliberately covers the **whole store** and not `_corpus.run_filter()`'s three seeds: a check
scoped to the corpus of record would not notice a generator that had stopped recording provenance.

| Script | The question it answers | Figure of record |
|---|---|---|
| `corpus/batch_reproducibility.py` | **Does every stored run re-derive its own seed?** `eval-001`'s only failure case, taken for the first time -- and it could not have been taken before `scn-008`, which put the base seed on the run row; before that the seed was printed by the batch summary and discarded, so the case was untestable rather than failing. Checks the **record** and not the function: `scn-008`'s suite asserts a constructed run spec re-derives its seed, and between that and this lie a JSON round-trip, a base seed returning as text to be cast, and an index into a list. Deliberately covers the **whole store** rather than `_corpus.run_filter()`'s three seeds, because a check scoped to the corpus of record would not notice a generator that had stopped recording provenance. Read-only, so no guard. | **380 of 380 runs re-derive exactly** (`.log`), across 19 batches and five base seeds -- the three of corpus v2, the dev batch, and one generated from the screen -- with **0 unprovenanced** and every batch size inside 20-30. It also verifies the **seed matching** every matched-pair figure in this repository rests on (`anom-006`'s sixty pairs, `anom-004`'s eight triples, `scn-007`'s forty): 100 (base seed, index) positions, one to five arms at each, **every position carrying a single seed across all of its arms**. That follows from the derivation being keyed on the base seed and index alone, and had never been checked -- a generator additionally keyed on the scenario type would leave every matched-pair figure comparing unmatched runs with no test failing. First version grouped on the base seed alone and reported a batch of twenty holding a hundred runs: a base seed behind 100 runs is **five batches of twenty**, one per type. |

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
| `mutation/mutate_anom011_sensitivity.py` | **Would the tests notice a recall figure that is wrong in the flattering direction?** Scores `sensitivity.py` and the `track_gap.py` verdict path it reads, over four surfaces: the tally that refuses a loss account which does not add up, the refusal to score a run that staged nothing, the conditions being trusted from the caller rather than taken from the policy actually run, and the denominator. | **14 of 14 killed** (`.log`, recorded 2026-09-29). Its first run reported 13 of 14 with one survivor, `absent aircraft dropped from denominator` -- which was **not a survivor**: the mutant replaced `set(staged_aircraft)` with `{a for a in staged_aircraft}`, the same expression, so the "mutant" was the original and could only ever survive. It sent a reader looking for a test that had been there all along. Rewritten to intersect the answer key with the aircraft that actually appear, which is the defect the name claims, and killed. |
| `mutation/mutate_eval003_export.py` | **Would the tests notice an export that is readable and untraceable?** Every mutant here produces files that open cleanly: this is the boundary between a computed figure and a quoted one, and a defect in it does not crash, empty a file or make a number look odd. Five surfaces: what reproduces a figure (disable the required-policy refusal and an export naming its seeds and none of its thresholds passes); traceability (a digest over a subset, or dropped from the rows, leaves every file looking self-describing while citing nothing); the blank cell (render an unmeasured rate as zero, or drop a count column, and `eval-002`'s typed-absence rule dies here); computing rather than re-organising (round a value and the quoted number stops being the tested one); and derived column names. Needs no database and no corpus. | **39 of 39 killed** (`.log`). The first pass killed 33 of 37, and all four survivors were real: the declared count-columns were never checked against what each rate is actually taken over, the declaration *set* was never checked for completeness, no fixture value had more than three decimal places so a rounding mutant was invisible, and the row for a type two arms produce was never asserted to carry neither arm's counts. Two later survivors were the same finding in the opposite direction -- a missing-key fallback made unreachable by the record alignment, so two mutants of it changed nothing observable. Resolved by removing the dead defence rather than marking it equivalent: a record missing a column now raises, since blanking writes a file where one row's value sits under another row's heading. **The pass also found a defect the unit tests could not**: a nested record absent on one row and present on another flattened two ways, adding an always-blank column that on the rows where the record really was absent read as a missing value rather than a missing record -- visible only by opening the CSV. |
| `mutation/mutate_eval002_metrics.py` | **Would the tests notice a results table that is readable and wrong?** This is the last module in the detection chain and the first whose defects nothing downstream can catch, because there is nothing downstream -- what it prints is what the write-up quotes. Every mutant leaves a full table: five arm rows, three type rows, two rates, a matrix and a latency figure, all plausible. Six surfaces, one per reporting constraint: what each figure is indexed by (swap recall's denominator for precision's and both are right on a corpus where no arm is confused for another, and wrong exactly where the confusion begins); the two recalls (merged, or exported under a bare `recall`); a misreport counted once rather than twice; the two false-positive rates pooled, or the cross-modal one claiming a control it never had; the `anom-008` refusal disabled; and `None` over an empty population replaced by 0.0. Needs no database and no corpus. | **40 of 41 killed** (`.log`). Seven survivors on the first run, of which **five were real gaps**: the false-negative rate was tested at a recall of one half, where the figure and its complement are the same number; the confusion row for a run claiming two types was never asserted; the arms behind an unbuilt type were never checked to be empty; the silent-arm rate was tested with one claim per run, where per-run and per-claim counting agree; and F1 over a precision and a recall of both zero was untested, which is a division by zero rather than a score of zero. A **sixth was a redundancy in the code**, not a gap in the tests: two checks held the one-arm-per-type rule and either could be removed with no behavioural change, which means neither was being proved -- the contradiction is now refused at construction instead, and the mutant dies. The seventh is genuinely equivalent and recorded as such with its reason, since `RunOutcome` refuses a latency on a run with no matching claim, so an arm's runs carrying a latency *are* its detections; the guard that makes the two the same has its own mutant, which dies. The module sat at 100% line coverage throughout. |
| `mutation/mutate_anom008_control.py` | **Would the tests notice a control that reports the quiet runs were clean when it graded nothing?** This is the worst-shaped instrument in the repo for a weak suite: the answer it is looking for is *nothing*, so its correct output and its broken output are identical, and almost every mutant here is more flattering than the truth while looking exactly like it. Four surfaces: the account (disable the missing-producer refusal and it grades whatever it was handed; invert the set difference and it refuses a stray key while letting a missing producer through); the band (drop the floor and every detector's silence becomes acceptable, raise the RF floor and twenty of twenty correct runs fail); the reportable verdict; and the rule that does not exist, reported as clean or counted as covered. Needs no database and no corpus. | **29 of 29 killed, no survivors** (`.log`). One mutant had to be rejected and replaced: keying the register on the rule id alone broke the module at import, so no test ran and the harness scored it *inconclusive* rather than killed -- a mutant killed by the language is not killed by the suite. Second time in two items that a mutant appeared to be caught by a test that never ran. The module also sat at 100% line coverage while two of its guards had no test at all, which is the argument for scoring a control by mutation. |
| `mutation/mutate_anom009_latency.py` | **Would the tests notice a latency that is plausible and false?** Every mutant here returns a number of seconds -- nothing raises, nothing looks wrong, and the damage is a figure that would be quoted in a results table and never sanity-checked. Four surfaces: the receiver requirement (measuring interference as though one receiver sufficed reports when the *first* matured, understating the latency by however long they were staggered); the minimum (dropping it reports when evidence *started* rather than when it was *sufficient*, which is the rejected "first cited reading" definition and reports near-zero everywhere); the sign (clamping a negative turns "the rule swept in readings from before the incident" into "it detected instantly"); and the refusals. Needs no database and no corpus, because the module reads neither, so it runs pytest directly rather than through Compose and a pass takes seconds. **First harness here to enforce that a mutant parses** -- `mutate_ai012_campaign.py` records that lesson in a comment and never implemented it, so an unparseable mutant is still scored by a syntax error there rather than by a test. | **15 of 15 killed, no survivors** (`.log`). It found a real gap on its first run: every test had given a rule exactly as many receivers as it required, which makes *the second to qualify* and *the last to qualify* indistinguishable -- and the corpus carries three-receiver interference zones, so the untested case is the common one. Closed with a three-receiver test before the pass was recorded. |
| `mutation/mutate_evb001_bundle.py` | **Are `evb-001`'s tests load-bearing?** 34 mutants over the typed-absence boundary, the per-item data mode, the unit of a bundle, the frequency axis, and the scoping of superseded claims. | **34 of 34 killed** — after a first pass killed only 22. The 10 genuine survivors were **all scoping rules**: evidence from another receiver, another window, another zone. The suite had tested what goes *into* a bundle and barely what must stay *out*, which is the more dangerous half, because a bundle carrying a neighbouring event's evidence is not malformed — it is wrong. 7 tests added, 2 tightened. |
| `ladder_suppression.py` | **Does `anom-013`'s suppression ever fire?** `ladder_end_to_end.py`'s "conflicting" counter records runs reporting two anomaly *types* and never inspects `Resolution.suppressed`, so its zero says nothing about suppression. | **Never. 188 claims bid, 0 suppressed.** `gnss-degradation` bids 60 over 60 runs; `rf-sensor-fault` and `ambiguous-mixed-evidence` bid **64** each, so four runs of each produce two claims — two claims in a run is not rare, two claims **for one zone** has never happened. Read the ladder's 60/60 as evidence it declines to merge separate events, **not** that it arbitrates competing ones. |
| `evidence_ref_uniqueness.py` | **Does a finding's `evidence_refs` coordinate identify exactly one observation?** Decides whether `evb-002` resolves by coordinate or the `from_*` functions must record row ids. Also checks the ISO round trip and what one lookup costs. | **Unique, everywhere.** RF by `sensor_id + channel_index + timestamp` and track by `aircraft_id + timestamp` are unique within a run across **both** corpora — 20.7M rows, worst collision 1, **zero** colliding coordinates. ISO round trip exact on 2,000 sampled rows. So `evb-002` resolves by coordinate and no rule adapter changes. **Cost: 64.7 ms per lookup**, index scan on `ix_observations_scenario_run_id` with **38,424 rows removed by filter** — a composite index would be wanted if bundles carry many items. **Superseded on that last point by `bundle_ref_cost.py`:** batching removes the cost the index would have removed, so the index stays a candidate rather than a prerequisite. |
| `backfill_bundles.py` | **Give the 140 hours that report a conclusion with no evidence their accounts.** `evb-003`'s fill, **superseded by `rescore_baseline.py`** (`anom-017`), which stores every bundle as a side effect; kept because its stop is the finding that produced `anom-017`. It wrote to the store -- it runs the shipped pass (`assess`) over every run holding a claim with no bundle, plus four holding a bundle matching no claim, and reimplements nothing. Needs `BACKFILL_CONFIRM=yes`, which the Makefile forwards and which no other script reads. Each run's stored reported claims are read **before** the pass and compared against what it stored; a disagreement **stops the whole fill** rather than skipping the run, so at most one run is ever affected. Run range named in the file, never taken from the store's bounds. | **Blocked at run 71 of 144, and the stop is the result** (`.log`). The rebuilt claim's window begins 20 s -- two sampling intervals -- before the stored one, with identical thresholds. The cause is the **baseline**: `measure_normality` takes every quiet run the store holds, so the normality a run is scored against depends on how large the store was when the pass ran, and by the recorded policy this store holds findings written under **two** -- 378 runs at 60 quiet runs, 22 at 100. `anom-016` named that hazard when it put the quiet runs on the record and `eval-003`'s policy column is what made it visible; neither prevents it, and nothing on the screen or in `eval-002`'s table says which baseline a figure was taken under. It also inverts the reading the item started from: the four bundles matching no claim are **not** stale -- run 71's, written 2026-09-19, agrees with today's rebuild to the second, and it is the stored *finding* that came from the other baseline. The two runs written before the stop were restored from a dump taken beforehand; the store is byte-for-byte as it was. |
| `bundle_end_to_end.py` | **Do evidence bundles work, on real hours, through the shipped modules?** Detect, resolve the ladder, build, save through `app/db/bundles.py`, read back, compare. Carries a negative control and prints one whole bundle. Knobs: `CORPUS=dev`, `PER_ARM`. **Run against the development batch, not a corpus.** | **Yes, on 60 runs.** 41 bundles, 0 refusals, round trip exact 60 of 60. Both silent arms produced **zero** bundles rather than one empty bundle. 2,049 citations resolved to 2,014 distinct rows; 566 evidence items cite readings and 113 are judgements. Interference bundles span both data modes, fault bundles one. **Negative control: one real citation shifted by one second is refused, and the run's stored bundle is untouched.** |
| `bundle_ref_cost.py` | **How many observations does a real bundle cite, and what does resolving them cost?** Closes the composite-index question `evb-002` deferred, which could not be answered until the evidence list was composed. Knob: `PER_ARM`. | **Batch, and do not add the index.** 24 bundles over 40 runs cite 1,021 coordinates — median **26** per bundle, max **105**; a zone bundle cites 79 at the median, a fault bundle 23. One query per ref costs **194.5 ms** at the median and 748 ms at the worst; one query per coordinate shape costs **10.5 ms** and 131.5 ms — **18.6x**, because the 38,424-row filter is paid once instead of once per ref. Also found the defect below. |
| `bundle_ref_cost.py` (the defect it found) | Same run. Every cited coordinate looked up and the misses attributed by finding shape. | **91 of 1,021 citations resolved to zero rows, and every one is the start of a `frozen_position` finding** — a window start reconstructed by subtracting the reported staleness, which is by definition the one instant in the window at which nothing was recorded. Every RF citation and every `not_heard` citation resolved. Fixed on `anom-010` and `db-008`, not on the checker: the finding now carries the reports it read beside the window it concluded. See `docs/qa.md` 83. |
| `mutation/mutate_evb002_traceability.py` | **Are `evb-002`'s tests load-bearing?** 29 mutants over exactly-one-row, run scoping, the closed set of coordinate shapes, the OBSERVED/DERIVED declaration, per-run atomicity, and the two sites that restore the original citation defect. **Mutates four files**, unlike the single-file passes beside it, and each site names the suites that ought to notice. | **27 of 29 killed**, both survivors declared equivalent — after a first pass killed 22. The four genuine gaps were the same shape as `evb-001`'s: run scoping is written twice, once per coordinate shape, and **only the RF clause was under test**; the observation-type filter had no test; and two refusals were asserted with a pattern **any** failure message satisfies, so both guards could be deleted with the suite green. A refusal test that does not pin *which* refusal it got is testing that something went wrong. 3 tests added, 2 patterns tightened. |
| `arm_rf_identity.py` | Is `ambiguous-mixed-evidence` a duplicate of `rf-sensor-fault`, or a control? Digests both arms' RF streams at every shared seed. | **A control, and it must not be dropped.** Same receiver, window and elevation 60/60, and the RF stream is **identical byte for byte in 60 of 60 pairs** — the only staged difference is five removed aircraft. So both arms being decided `possible_sensor_fault` 60/60 is a measured immunity result: a simultaneous track-side disturbance does not perturb the RF verdict. Carries the ordering trap in its docstring — the first version digested rows ordered by a payload key that does not exist, so every row sorted equal and 4 of 60 pairs looked like generator differences. |
| `source_gap_threshold_sweep.py` | **The detector's own question**: does a *fixed* threshold separate a staged gap from an unstaged run on a **single run**, with no control? Pre-registered in `source_gap_threshold_prereg.md`; fitted on two base seeds and scored once on the third. | **No, and it points the wrong way.** Best zero-false-alarm point (60 km, size floor 4, threshold 11.53) catches **3 of 20** on the holdout against a pre-registered bar of 0.25 — but fires on **6 of 20 `gnss-degradation`** runs, twice the rate of the arm it is for. Best Youden's J anywhere is 0.275, at a 0.38 quiet-arm rate `anom-008` forbids. **This is what closed `anom-006` the second time.** Also established, exactly: `normal-baseline` ≡ `rf-sensor-fault` and `aircraft-coverage-gap` ≡ `ambiguous-mixed-evidence` on the track side, so the clean negative population is **60 seeds, not 120 runs**. |

### The hypothesis layer (`ai-002`)

| Script | The question it answers | Figure of record |
|---|---|---|
| `template_hypotheses.py` | **Does the template generator work on the bundles the system really makes?** Reads the *stored* bundles back through `app/db/bundles.py` and generates one hypothesis from each, rather than from fixtures this project wrote. Asks three things: does it refuse anything, is every citation's `(rule_id, finding_type)` pair really in its own bundle, and does the same bundle produce the same words on a second pass. Knob: `CORPUS=dev`. **Run against the development batch, not a corpus.** | **41 of 41, 0 refusals, 164 of 164 citations grounded, 0 unstable.** Confidence inherited from the deciding rule comes out **24 High, 17 Medium** — the value is live on real data, not a constant. Uncertainties carried: median 3, max 8, and **min 0**, so the empty case `ai-001` deliberately permits does occur. Citations are **exactly 4 on every bundle**, because both bundle shapes happen to carry four kinds of evidence — recorded as a limitation, since it means the baseline's size does not vary with the event. Found two prose defects no unit test could: a doubled full stop where a rule's own text already ends in one, and a summary framing `anom-005`'s not-measurable caveat as "the rule's own conclusion". |
| `grounding_catch_rate.py` | **Does the grounding check work on the bundles the system really makes?** Two questions, because specificity without sensitivity is a check that returns "fine" and passes the first one perfectly. First, what does it flag on input whose answer is known in advance: a template hypothesis is grounded by construction, so anything flagged is a defect in the *check*. Second, every real hypothesis is corrupted four ways, one citation at a time, and every corruption must be caught. Distinct from `template_hypotheses.py` section 2, which asks the same resolution question with a hand-written loop and is testing the *generator* — this runs the shipped module, which is also why the two must not share their derivation of the citation key. Knob: `CORPUS=dev`. **Run against the development batch, not a corpus.** | **0 flagged of 164 citations across 41 of 41 bundles**, and the template arm's catch rate is **0.0 measured** rather than `None` — the distinction the item is built around. **164 of 164 corruptions caught**, 41 of 41 on each of the four kinds. Near misses classify **123 of the 164**: 82 `rule_id_under_another_type`, 41 `case_or_spacing`, 41 unclassified — and the unclassified 41 are exactly the invented rule id, which is correct, because there is nothing for it to be near. One finding the unit tests could not produce: **a circular citation reads as a rule-id confusion.** Citing the bundle's own claim yields `rule_id_under_another_type` on every bundle, because the deciding rule genuinely does appear in the evidence under other finding types — so the near-miss axis does not separate circularity from type confusion. The verdict is right in both cases and only the classification is coarse, but a write-up quoting the `rule_id_under_another_type` count as "one rule's findings mistaken for another's" would be overstating it. **0 of 41 bundles carry a superseded claim**, so the amendment's failure case is unexercisable here exactly as `ai-008` records, and its corpus demonstration is owed to a second producing rule alongside `anom-013`'s arbitration. |
| `hosted_smoke_test.py` | **The first real requests: three bundles, hand-read.** The only script in this repository that makes a real, billed call to a hosted provider, and deliberately the last gate before a campaign rather than part of one — so it refuses to run without `SMOKE_TEST_CONFIRM=yes`, forwarded by the `measure` target for this script alone. Three bundles rather than twenty, printed **in full rather than asserted on**: a campaign can tell you a hypothesis validated and was grounded, and cannot tell you whether the words are any good. Four questions nothing else answers — does the request shape work at all (strict mode, narrowed schema, dated model, temperature and seed, any of which the provider may reject); which schema keywords strict mode *actually* accepts, printed beside the result because that list is provider documentation this repo cannot verify locally; is the cost estimate close, which can only be compared against the provider's own usage page **now**, while three calls are the account's whole history; and does the grounding check flag a real model rather than a corruption built for the purpose. The credential reaches the container through `backend/.env` on the bind mount, following `app/replay.py` — **not** through Compose interpolation, which turns an unset host variable into an empty string that `load_dotenv(override=False)` then treats as present, shadowing the file. Knob: `CORPUS=dev`. | **Run four times, 26–27 September 2026, against `gpt-4.1-2025-04-14`; about 12p in total.** Log of record is the third run: 3 bundles, **3 of 6 calls, 16,121 prompt and 1,201 completion tokens, $0.0419 estimated, 0 unpriced**. Temperature, seed and a token ceiling were all **accepted** — no rejected request, so the parameters the reproducibility argument rests on are honoured rather than ignored. Strict mode removed **exactly two** keywords, the minimum-length and minimum-items constraints, confirming that the constraint carries structure and not quantity. **Grounding passed every citation of every generation** — 31 across the four runs, none flagged — which is the model rather than a corruption built for the purpose, and the first evidence that the safeguard's catch rate on a real arm may be low. Two findings no automated check would have produced. **Citation count would have unblinded the blind scoring entirely**: the baseline emits four citations on every bundle and the model emitted one per *item* (10 on a fault bundle, and would have been 17–34 on an interference one), so a scorer would have had a perfect classifier rather than a hint — fixed by one binding prompt rule before any scored generation, changing the fingerprint from `275187dc…` to `af153726…`. And **the provider is not deterministic at temperature 0 with a fixed seed**: 4 of 5 comparable repeated pairs differed, one changing the *set* of cited evidence kinds and one losing an alternative's falsification condition, while confidence was stable on every pair. That narrows the reproducibility claim to the method and the structural output, settles `ai-007`'s retry as a mechanism rather than a tax, and is what raised `eval-004`'s N from 1 to 3. **Cost reconciliation:** $0.08 actually billed against $0.0953 estimated for the first three runs — the estimate runs ~19% **high**, the safe direction, consistent with cached-input pricing on the repeated prompt prefix. |
| `campaign_statistics.py` | **What did the scored campaign produce, per arm?** `eval-005`'s deliverable, run end to end for the first time, and it needed the campaign record **rebuilt rather than parsed**: `ai-012` serialises the budget and the grounding ledger as figures rather than as contents, and this report is per arm while the stored budget is pooled across the run -- so the one artefact the campaign produced cannot answer the question the next item asks of it. Nothing is invented: each call's spend and tokens come from the generation that call produced, and its model id, frozen parameters and verbatim response from the row `db-002` stored for it. Then **two reconciliations, either failing refusing the whole report** -- the rebuilt calls must sum to the stored pooled budget exactly, and the rebuilt ledger must match the stored per-arm checked and caught counts. A *failed* grounding check raises rather than being guessed, the artefact recording that a hypothesis failed and never which citation did; unexercised here because nothing failed. It also writes the reconstructed per-call split to `scored_campaign_calls.json` beside the record, **only after the reconciliation passes** so the file cannot exist in an unchecked state: those eighty rows are the only place the per-arm split exists outside the database, and this project has lost a corpus once already. A recovery artefact, not a result -- `eval-003`'s exported figures are the results. Needs the database for the stored hypotheses, needs no corpus, makes no model call, and so can be re-run freely. | **Hosted: 60 generations over 20 bundles, 60 checked, 0 caught, 0 refusals and so a retry rate of 0.000, 0 fallbacks, 60 calls, $0.854364, 334.197 s. Template: 20 generations, 20 checked, 0 caught, 0 calls, 0.008 s. Local never asked, and every one of its rates is blank rather than 0.0** (`.log`) -- the first live demonstration of that rule, everywhere else having had a non-empty population. Both reconciliations exact. **Agreement across the three generations per bundle is 1.000 on all three dimensions over 20 bundles, which corrects the prediction on `eval-005`**: the three-bundle trial had seen the cited set move on one of three and the amendment expected it to carry the result, and over twenty it moved on none. The only thing that differed between repeated answers was the prose, which none of the three measures. Read the zero fallback rate narrowly: it says the path never fired, not that it works. |
| `detection_metrics.py` | **How well did the detection layer actually do?** Also `eval-003`'s producer: after printing the tables it writes them to `measurements/exports/` with a provenance record assembled from the policy objects the run actually used, since a recorded setting that is not the one in force is worse than none. `eval-002`'s deliverable, and the only measurement here that scores the whole chain rather than one rule: it re-runs baselines, RF episodes, receiver faults, track gaps, clusters, fusion and the ladder over every run, then scores what survived the ladder against the answer key. **Re-runs rather than reading `detection_findings`**, because that table holds whatever measurement ran last (`db-008` replaces per run per rule), so a results table built from it would depend on script ordering while passing every check. Six reporting constraints are enforced by `app/evaluation/metrics.py` rather than by this script: recall indexed by truth and precision by prediction on separate tables, F1 only where one arm maps to one type, one multi-class confusion, two false-positive rates, latency conditional on detection, and `None` over an empty population -- plus a refusal to report a false-positive rate at all unless `anom-008` passed on every quiet run. `anom-011`'s per-aircraft figures are read off `track_gap_recall.log` and passed in rather than recomputed. Needs the database and a generated corpus. | **300 runs: recall 60 of 60 on all three positive arms, precision 1.000 on both built types, F1 1.000 for `possible_interference_zone` and withheld for `possible_sensor_fault` (two arms produce it), 0 of 60 false positives from nothing and 0 of 60 cross-modal, a diagonal confusion matrix and 0 runs excluded** (`.log`). **The first precision, F1 or latency figures in the project** -- `anom-009` had a unit suite and a mutation pass and had never been pointed at a run. Latency, conditional on detection: median **10 s** on both fault arms, **20 s** on the interference arm, min 10 s and max 90 s over 60 detections each; the floor is `anom-014`'s minimum episode duration, so the fault arms decide as soon as they are allowed to look and the interference arm waits one sampling interval longer for a second receiver. No latency came out negative and no claim was undecidable, both possibilities the item names. **Read the perfect scores narrowly**: the radio side is synthetic and the injected incident sits well above threshold by construction, the corpus holds no near-misses, and one reportable type has no rule -- so the table establishes that the layer is correctly wired, not that it detects real interference. The one figure carrying information from outside the generator is the per-aircraft recall, and `ambiguous-mixed-evidence` reads **1.000 run-level against 0.587 per-aircraft on the same sixty runs**, which is the clearest demonstration in the project of why the two recalls are never merged. | **Re-pointed at `app/detection/chain.py` on 2026-10-01** (`anom-015`): this file held the only copy of the ordering it runs -- baselines, episodes, faults, gaps, clusters, fusion, ladder -- and `measurements/` is outside ruff, mypy, pytest and the coverage gate, so the composition behind every figure here was the one part nothing checked. Re-run through the new composition the output is **byte-identical**; the single line that moved is the provenance stamp, `c421c41506fd` → `79ef76db46ba`, because the record gained the sixty quiet runs normality was measured over. A digest that stayed put while the record changed would be the failure. Its own `obs_for` is now the repository's read: the version it replaced invented five fields the row already holds.
| `quiet_run_background.py` | **What does every detector produce on a run with nothing staged?** The two halves of `anom-008` point in opposite directions and only one is a measurement. The rules an analyst is shown must produce nothing, which is a requirement and gets no band -- a band there would make a false positive negotiable. The rules underneath them read replayed flight data that genuinely contains gaps, so *their* silence is a detector that did not look, and the band is what says so. Runs the full chain per quiet run: baselines, RF episodes, receiver faults, track gaps, clusters, fusion, then the ladder, and counts the reportable side **post-ladder** because a suppressed zone is not something the analyst is shown. Needs the database and a generated corpus. | **0 of 60 quiet runs show the analyst anything**, over two of the three reportable types -- the third has no rule. Bands per quiet run, over all three waves of corpus v2: RF deviation **0-0** (zero on 60 of 60; the grid is synthetic, so its silence is correct), track continuity gap **8-22** (median 15, never zero), gap cluster **4-10** (median 7, never zero), rate excess **0-0** (structural: it is reached only through an environmental dismissal, so a quiet run never invokes it). Wave 2 widened the two track bands (from 9-19 and 5-9, measured at n=20) and **wave 3 moved none of the four**, which is the more useful result than the widening: they have converged, and the RF floor held at zero on an independently seeded wave rather than by accident on one. Measured on the quiet runs and applied to them, so it cannot fail on the data that produced it -- a drift tripwire, not a test of the present figures. |
| `draw_scored_sample.py` | **Which twenty packages is the scored campaign about?** `eval-004`'s first pass, and it **spends nothing and must run before the one that does**. Draws 10 `possible_interference_zone` and 10 `possible_sensor_fault` from a fixed seed, does the ground-truth join in the open — a bundle carries no scenario type, so the run's own row supplies it and it is recorded *beside* each entry, never inside a bundle — and writes `scored_sample.json`, which is **committed**. That split is the point: an instrument that provably predates its results is worth nothing if the corpus does not, and one script doing both could not enforce the ordering. Only ids, kinds and scenario types are written; the bundles stay in the database, because they carry pseudonymised identifiers and NFR-405 keeps those out of anything committed. Knob: `CORPUS=dev`. | **Drawn 28 September 2026, seed 20260928, committed as `scored_sample.json` before the campaign ran.** 20 of 62 available bundles: 10 `possible_interference_zone` from a population of 20 and 10 `possible_sensor_fault` from a population of 42. By scenario type the draw came out 10 `gnss-degradation`, 5 `rf-sensor-fault` and 5 `ambiguous-mixed-evidence` -- which is *not* the five-per-type stratification the rubric originally specified, because that is unsatisfiable: five scenario types produce two kinds of bundle. The population it drew from is recorded in the file beside the draw, so the selection is reproducible from the seed alone. |
| `scored_campaign.py` | **The scored campaign: twenty packages, both arms, every answer kept.** The second of the two real-billing scripts, and it requires `CAMPAIGN_CONFIRM=yes` — a variable of its own, so approving the three-bundle pre-flight can never also approve this. **It cannot draw its own sample**: the twenty come from the committed `scored_sample.json`, and a missing file is a refusal rather than a helpful redraw, following `ai-012`. It also refuses when the committed sample names a bundle the corpus no longer holds, because regenerated bundles mean the pre-registered corpus no longer exists — a change to argue for in the rubric's change log, not to work around. Three generations per bundle from the model arm and one from the baseline; the first model generation is what `eval-004` scores and is never substituted. Writes `scored_campaign_record.json`. Knob: `CORPUS=dev`. | **Run 28 September 2026 against `gpt-4.1-2025-04-14`; $0.8544.** 80 generations -- 60 hosted at three per bundle, 20 template -- with **0 skipped**, giving 20 of 20 complete scored pairs. **80 of 80 grounding passed**, 0 fallbacks, 0 refusals of either category. 60 calls against the 200 ceiling; 326,106 prompt and 25,269 completion tokens, 0 unpriced. Wall time 334.2 s hosted against 0.008 s template. **Two production failures on the way, both recorded rather than tidied away.** The first attempt died on `UndefinedColumn` after one paid call: the application database was two migrations behind, because the fixtures migrate the *test* database and nothing migrated this one -- a fully green 1,540-test suite said nothing about the schema the system ran against. A pre-flight revision check now runs **before the first billed call**. The second attempt lost 5 generations, 2 of them scored, to HTTP 429s classified as provider unavailability -- 18 of 20 pairs. A 429 says *try again in 5.09s*, so treating it as permanent silently shrank a pre-registered corpus; fixed by **pacing at 11.0 s and not by retrying**, since a retry inside the campaign would blur `ai-006`'s availability fallback into `ai-007`'s correctness one. Read the 0.0 catch rate narrowly: it says every cited identifier exists, and nothing about whether the sentence attached to it is true. |
| `build_scoring_pack.py` | **What the marker receives.** `eval-004`'s second pass, and it **spends nothing**: it reads the committed campaign record, reads the stored hypotheses back out of the database, and renders. Five files, three audiences -- `hypotheses.md` and `score_sheet.xlsx` go to the marker, `arm_key.csv` / `.xlsx` are held back until `eval-006` has ingested both sheets, and `score_sheet.csv` is the archival form the ingest reads. The scored generation is taken by **ordinal** and never by row order, and is never substituted when it fell back. Refuses to write if the arm vocabulary appears anywhere in either marker file -- scanned across the prose *and* the workbook's cells, headings, sheet names, notes and document properties. Knob: `CORPUS=dev`. | **Built 28 September 2026, shuffle seed 20260929, then rebuilt the same day for legibility.** 20 evidence packs, 40 explanations, **200 pass-one values per marker** -- the figure the participant information sheet and the ethics approval form quote, checked against what was exported rather than against what was planned. A/B balance: A is template on 12 packs and hosted on 8. Blinding scan clean on both marker files. **The first pack was unreadable and every automated check on it passed** -- space-aligned plain text in a `.md` file, so renderers reflowed 19 findings into one paragraph; findings carrying no source while the hypotheses above them cite `RF-06:4` by name, which left dimension 1 unscoreable; nine identical lines and one uncertainty printed three times. Rebuilt under `eval-007`/`eval-008`: findings grouped on the `(rule_id, finding_type)` citation key with **every finding still listed individually**, because a summarising pack would do part of the work dimension 1 scores and narrow the measured arm difference. It removed no information and exposed two facts the flat list hid -- an even 4/4 split of deviations across two sensors, and one aircraft dropping out twice in one window. |

| `bundle_payload.py` | **What does one bundle cost to send, and what is actually in it?** Two questions `ai-004` could not be specified without, and both were about to be answered by guessing. Knob: `CORPUS=dev`. | **Median 6,668 characters, ~1,667 tokens; max 22,540 / ~5,635.** A 20-bundle scored campaign is **~33,000 input tokens for one arm** — so the spend ceiling is about a runaway loop and never about the campaign. An interference bundle is **3.2x** a fault bundle (18,435 against 5,802 median), which unbalances a scorer's reading load and is why `docs/phase9_hypothesis_layer.md` §9 stratifies on bundle kind. On egress: the only positional fields in any bundle are `affected_area.lat`/`.lon`, which are the **synthetic** receiver or zone centre — **no aircraft position leaves**; a track citation carries a `dal-004` pseudonym, a timestamp, a duration and a gap shape. |

### The ladder, and the layers underneath it

| Script | The question it answers | Figure of record |
|---|---|---|
| `ladder_end_to_end.py` | The whole reportable-rule ladder as one decision over every stored run. | 60/60 sensor-fault, 60/60 interference, 20/20 ambiguous (as a sensor fault, by design), 75/80 coverage-gap silent, 19/20 quiet silent. **No zone in any run received two answers** — `anom-013`'s first failure case, and it does not occur. Corroboration across every interference zone: 7 corroborated, 7 not, **47 not measurable**. |
| `cluster_background.py` | Does the quiet-run background ever cluster into something reportable? | The largest cluster on a staged run **equals** the largest on its own seed-matched control, in eight triples of eight. This is why `anom-004` carries no severity. *(no log survived)* |
| `cluster_leak_into_fusion.py` | How exposed is the fusion rule to background track clusters on a run whose truth is a broken receiver? | See `docs/thesis_notes.md`. *(no log survived)* |
| `cluster_separation_after_scn006.py` | `scn-006` restored 55% of the signal. Does that change `anom-004`'s answer? | See `docs/thesis_notes.md`. *(no log survived)* |
| `track_gap_recall.py` | **Where do the staged aircraft go?** `anom-011`'s deliverable, scored against the answer key `scn-002` recorded at generation time rather than against the detector's own output -- a staged aircraft the rule said nothing about is a miss, not an absence from the denominator. Batches are now selected **by base seed** via `_corpus`, not by the `RUN_LO`/`RUN_HI` id range it used to take: an id range was how batches were addressed before `scn-008` put the seed on the row, and it is correct exactly until a corpus is regenerated. Knobs: `CORPUS`, and `BASE_SEED` for one batch. | **Corpus v2, three waves: 82% `gnss-degradation`, 59% on each suppression arm, 67% over 900 staged aircraft** (`.log`, per wave and combined). The waves separate two things a single figure hides: the navigation arm replicates almost exactly (83, 81, 83), so 82% is a property of that mechanism, while the suppression arms spread eleven points (64, 59, 53) and account for the whole of the drift in the combined row -- the frozen-position mechanism is a stable detector and the not-heard mechanism varies with which aircraft a wave staged on. One wave would have reported either as a fact. 0 runs excluded for staging nothing; 16 of 900 answer-key aircraft parked, against 209 of 381 before `scn-006`. Losses: 136 on ground, 132 below threshold, 33 contact not fresh, and **nothing at all** to the interior filter, to an absent aircraft, or to an unbracketed absence. The two suppression arms are byte-identical because `tracks.py` gives them the same mode at a shared seed, so they are one measurement reported twice rather than two. Corpus v1's figures (25/69/81% over three batches) are quoted on `anom-011` and **no log of them survived**; that corpus no longer exists. |
| `track_gap_hit_rate.py` | Does `TRACK-GAP` find the aircraft the run staged on? Separates a detector that never saw the injection from clustering that cannot discriminate. | See `docs/thesis_notes.md`. *(no log survived)* |
| `track_gap_policy_sweep.py` | Is 21% recall a property of the system, or of the policy I guessed? | See `docs/thesis_notes.md`. *(no log survived)* |
| `staging_on_ground.py` | Is 90% `on_ground` real, or an artefact of how the reasons were ranked? | Real. **55% of every injection was landing on a parked aircraft**, which is what `scn-006`'s airborne gate exists to fix. *(no log survived)* |

## Running one

```
make measure SCRIPT=corpus/bundle_end_to_end.py CORPUS=dev
```

`SCRIPT` is the path under `backend/measurements`. `CORPUS` selects which runs the script is about —
`v2` (the default), `v1`, or `dev` for the development batch. The target passes no database URL: the
only one reachable is the application's own, which is the right target for a measurement and the
wrong one for anything that drops schema. It also takes `--no-deps`, so a measurement can never
start an empty database beside the one it meant to read. **The database therefore has to be up already** — `docker compose up -d postgis`. When it is not, the script dies on
`failed to resolve host 'postgis'`, which reads like a defect in the script and is not one; it
bites after any restart of the Docker runtime.

Added 2026-09-19 (`ops-003`). Before it, every figure here was produced by hand-writing a compose
invocation — which is exactly where a wrong environment variable gets supplied, and how the corpus
came to be destroyed. See `ops-004`.

### Re-scoring every stored run under the pinned baseline (`anom-017`)

**The one script here that writes to the application's database on purpose.** `rescore_baseline.py`
runs the shipped pass over every completed run under `BASELINE_QUIET_RUNS`, replacing findings,
storing bundles and moving each run's examination stamp. It replaced `anom-016`'s
`rescore_corpus.py` (now in `superseded/` with its log), which baselined over corpus v2's sixty quiet
runs while the batch trigger used every quiet run in the store -- which is how the store came to hold
findings under two baselines, 380 runs at sixty and 80 at a hundred, with nothing on the screen able
to tell them apart. `anom-017` pinned the hundred, each with its seed, and `measure_normality` now
refuses a store that does not hold them.

Run, after dumping `detection_findings`, `evidence_bundles`, `scenario_runs` and `hypotheses`:

    make measure SCRIPT=corpus/rescore_baseline.py                     # scope only
    make measure SCRIPT=corpus/rescore_baseline.py RESCORE_CONFIRM=yes  # and write

A changed claim is the **expected** outcome and is listed run by run, before and after. The twenty
runs the scored campaign cites are refused by `db-011` and left on the sixty-run baseline, checked
afterwards for having moved nothing.

**Result of record, 2026-10-06** (`rescore_baseline.log`): **440 of 460 completed runs re-scored in
11.1 min**, 20 refused as cited, 0 failures. **11 runs' claims moved, all window boundaries by 10-30
s; no claim appeared or disappeared** (90 interference and 186 fault claims before and after). Stamps
after: 440 runs at a hundred quiet runs, 20 at sixty. Bundles 151 to 297, no run left with a claim
and no bundle, 155 hypothesis rows intact.

**`detection_metrics.py` writes nothing since the same item.** It used to run the storing pass, so it
replaced findings and re-dated every run it scored, and since `evb-003` it also stored bundles -- the
re-run after the re-score stopped at run 102 on `db-011`'s refusal. It now uses
`assess_without_storing`, which rolls every write back. Re-run under the pinned baseline, **every
figure in the table is byte-identical** to the 60-run figures of record: only the provenance moved
(`BASELINE.quiet_run_count` 60 to 100, measured-on date, digest `79ef76db46ba` to `d2a2c04ab428`).
Store checksums before and after the run are identical.

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
| `mutate_evb001_bundle.py` | `app/detection/bundle.py` | **34 of 34 killed** after a first pass killed 22; all 10 genuine survivors were scoping rules |
| `mutate_evb002_traceability.py` | `app/db/bundles.py`, `app/detection/bundle.py`, `app/detection/track_gap.py`, `app/detection/findings.py` | **27 of 29 killed**, both survivors equivalent. One of the two is equivalent *only because another guard covers it* — the constructor refuses a judgement carrying refs, so the resolver's skip has nothing to skip. Delete that check and this mutant becomes a live defect with no test on it. Recorded in the harness for that reason. |
| `mutate_db002_hypotheses.py` | `app/db/hypotheses.py`, `alembic/versions/0006_hypothesis_columns.py`, `alembic/versions/0007_hypothesis_requested_arm.py`, `app/db/bundles.py` | **44 of 44 killed, no survivors** (2026-09-27, 18 new mutants over the two additions `ai-012` forced) — after an earlier 26 of 26, itself after a first pass killed 21. All five genuine gaps were the same two families: **scoping and ordering** (three of them) and **a distinction Python cannot see** (two). Every earlier test had one bundle and one run in the database, so dropping a WHERE clause changed nothing any of them could observe; and a JSONB `null` reads back as `None` exactly like SQL NULL, so the round trip could not tell an absent parameter set from a recorded null one. The ordering gap needed the heap **disturbed** to see at all — with a few untouched rows a sequential scan returns them in insertion order anyway, so an UPDATE (which rewrites a row to the end of the heap under MVCC) is what makes physical order differ from id order. This is the third pass on this project whose survivors were mostly scoping rules, after `evb-001` and `evb-002`. One of the tests written to close a gap then found a real defect: a whitespace-only model id satisfied `if not model_id`. 7 tests added, 1 implementation fix. Nearly every site **stores something plausible** rather than raising: a renamed column still holding text, a parameter set serialised as a JSON null instead of omitted, a grounding state collapsing two of its three values, a write that replaces instead of appending. The migration is mutated too, because a column that is nullable when it should not be is not detectable from the Python at all. Reports how many tests **ran**, not only the exit code — see the hazard below. **Extended 2026-09-27** for the verdict writer and the asked-for-arm column, where the interesting mutants are not *does it write* but *does it write to the row it was given, does it write nothing else, and can it be made to write the third state that undoes the whole point of a nullable column* — and where every asked-for-arm mutant still stores a row, so a fallback simply becomes indistinguishable from the baseline again with nothing raising. It also gained the crash guard and the sentinel it had been owed, and moved to `test-backend-nobuild`: rebuilding the image once per mutant is what exhausted memory and had the OOM killer stop two passes mid-run, and the bind mount made the rebuild pointless anyway. **One new mutant had to be rewritten**: it produced an `IndentationError`, so the module could not import, 45 tests errored, and the harness saw a non-zero exit *and* a test summary and scored it KILLED — by a syntax error rather than by a test noticing anything. It slipped past the no-summary guard precisely because a broken import still produces a summary. Both this harness and `ai-012`'s now check, before a pass runs, that every anchor matches the formatted source exactly once **and** that every mutated file parses. |
| `mutate_ai001_schema.py` | `app/ai/hypothesis.py` | **17 of 18 killed**, the survivor proven equivalent. Almost every site *widens* rather than breaks, because that is the shape of nearly every schema defect: a schema that accepts more than it should passes everything it used to and admits something new. Half the sites are on the **derived** JSON schema, which is what actually constrains a hosted generation — a derivation that widened confidence to a free string would pass every test written against the Python model. |
| `mutate_ai002_template.py` | `app/ai/template.py` | **34 of 35 killed**, the survivor proven equivalent — after a first pass killed 29. All four genuine survivors were tests passing for a reason other than the one they name: a refusal test satisfied by a *different* refusal whose message carries the same words, a count test whose two fixtures also differed in source count, an ordering test asserting a word the displaced text also contains, and a differential test satisfied because the generic sentence interpolates the subject. |
| `mutate_ai003_service.py` | `app/ai/service.py`, `app/ai/registry.py`, `app/ai/providers/template.py` | **28 of 29 killed**, the survivor proven equivalent — after a first pass killed 27. An interface is mostly refusals, and a refusal that stops refusing is the quietest defect there is: everything that worked still works and one new thing is permitted. The single genuine gap was the one property nobody thinks to test — the suite asserted the configuration object was frozen and never that the **parameters mapping inside it** was, so a caller holding a live handle could change what every later call ran under. Frozen parameters are the reproducibility claim itself. 3 tests added. Mutates three files, like the `evb-002` pass: a single-file pass over the interface would leave the two places it is actually used untested. |
| `mutate_ai007_fallback.py` | `app/ai/fallback.py`, `app/ai/service.py` | **32 of 32 killed, no survivors** — after a first pass killed 29. This item is two guarantees wearing one coat and the mutants separate them: the ceiling is about **money**, so several sites move the bound by one or remove it without raising anything (an off-by-one ceiling is a 50% overspend that no test asserting "it eventually stopped" would notice); the record is about **what a row means afterwards**, since a mechanical explanation that arrived because the model failed and one that arrived because the template was the configured arm are the same row unless this layer says otherwise. Three mutants widen the caught exception from `GenerationRefused` to its parent or to `Exception`, because `ai-006` and `ai-007` end at the same destination for opposite reasons and merging them is the item's central risk. **One of those three was the first pass's most valuable survivor**: nothing had ever made the injected grounding check raise anything but a refusal, so a defect *inside `ai-008`* would have been caught here and recorded as the model being ungrounded — inflating a **reported evaluation result** with the checker's own fault. The behaviour was already right; nothing proved it, so nothing would have noticed it changing. The other two were a test satisfied by the wrong log line (the fallback summary names the same category and the same reason, so the per-refusal log could be deleted with the suite green — rewritten around a *successful* retry, where no summary is emitted) and a coercion no call site exercised (`refusals` is always passed as a tuple already, so the tuple() that defends against a caller's list was never run). 4 tests added, 2 rewritten, 0 implementation changes. |
| `mutate_ai009_budget.py` | `app/ai/budget.py` | **30 of 33 killed**, all three survivors proven equivalent — after a first pass killed 28. A spending guard fails quietly: every mutant here still produces hypotheses, still returns results, and still reports a number when asked what the run spent. The two genuine gaps were both boundaries. **The refusal did not have to name its ceiling** — the assertion looked for the value and the *call count* supplied it, and this one cannot be fixed by choosing better numbers, because the abort fires exactly when count equals ceiling so the two are always identical; the message structure had to be pinned instead. And **nothing ever landed exactly on the spend ceiling**, so `>=` and `>` were indistinguishable — a decision (an allowance spent in full is spent) that had never been tested, and without it a run configured for 20.00 would quietly continue at 20.00. 1 test added, 1 rewritten, 0 implementation changes. **One equivalence is a finding rather than a nuisance**: summing only the priced calls, and summing every call with `None` read as 0.00, *necessarily* produce the same number, since the excluded terms are exactly the ones that would have contributed zero — which proves the honest-total claim is not carried by `spent_usd` at all. Unpriced and free are separated entirely by `unpriced_calls` and `cost_is_complete`, so the figure to quote in the write-up is never the total on its own. A second equivalence measured something the source cannot show: the tuple coercion at the report site is covered by `BudgetReport.__post_init__`, but **the cover is one-directional** — deleting the `__post_init__` coercion is caught and deleting the report site is not, so they are not two guards making each other redundant as they appear to be. |
| `mutate_ai004_hosted.py` | `app/ai/payload.py`, `app/ai/prompt.py`, `app/ai/providers/openai.py`, `app/ai/registry.py` | **47 of 47 killed, no survivors** — after a first pass killed 40. All seven gaps were tests matching something weaker than their name. Two were **refusal tests that did not pin which refusal**: removing the declining-model branch or the empty-response guard still raised `GenerationRefused`, from a *later* guard, so both tests stayed green while the specific check they named was deleted — the same defect `evb-002` recorded, now twice. Two were **prompt checks matching words that survive the rule being gutted**: "superseded" is still present when rule 3 becomes "the superseded list holds earlier notes". One asserted the request's *envelope* and not the schema inside it, so sending the schema unnarrowed — which the live API rejects, failing every call in the campaign — was invisible. One found that a **`str`-subclass enum defeats `isinstance(x, str)`**, compares equal to its value, and serialises identically, so a domain type left in the payload was undetectable until the check became `type(x) is str`. And nothing asserted the **frequency axis** reaches the payload at all, which is the one axis `evb-001` contributes itself. 1 test added, 6 tightened, 0 implementation changes. Runs in the virtualenv rather than through Docker — see the note in the harness for why, and the sentinel that makes it safe. |
| `mutate_ai008_grounding.py` | `app/ai/grounding.py` | **46 of 46 killed, no survivors, on the first valid pass** — the only item so far to reach that without a second round, and *why* is the useful part rather than the score. The gap-finding happened **before the implementation existed**: a throwaway module reporting every citation grounded was run against the suite first and 24 of 58 tests passed against it, two of which were wrong tests and were strengthened then. That is the work a mutation pass normally does afterwards, done earlier and far more cheaply. A third gap — `near_misses(arm)` pooling every arm's findings, which the test could not see because it used one arm — was found while *writing* the harness and fixed before the run, so the pass never scored it. What the pass then confirmed is the part that matters most: **every mutant that still resolves *something* is killed.** Resolving on the rule id alone, resolving case-insensitively, and folding the superseded compartment into the citable set each pass the oracle perfectly, because a template hypothesis is grounded under all three — so `grounding_catch_rate.py` beside this cannot see them and only these tests can. One anchor was scored **INVALID (0 matches)** on the first run: Black had collapsed a wrapped call onto one line and the anchor was written against the wrapped form. That is the silent-INVALID failure this directory already records, and it surfaced only because the harness reports invalid anchors separately rather than counting them among the killed. |
| `mutate_ai011_assembly.py` | `app/ai/assembly.py`, `app/ai/registry.py` | **36 of 36 killed, no survivors** — after a first pass killed 33 of 35. Composition is the worst place in this package for a weak suite, because almost every mutant here still produces hypotheses: nothing throws, nothing looks wrong, and the damage lands in a bill, in a per-arm column, or in a reported result nobody can re-derive. Both genuine gaps were **refusal tests matching something weaker than their name**, the defect `evb-002` recorded and `ai-004` hit twice, now a third and fourth time. The template-as-arm test asserted only that *something* was raised — and `ai-009` refuses a budgeted template anyway, so this module's own guard could be deleted and the suite stayed green; it now pins the message and proves the refusal fires **before the arm is constructed**, which is the whole point, since constructing a real arm reads the credential. The spend-ceiling test matched the bare word "price", which survives in the message's tail (*"Supply prices, or drop the ceiling"*) when the sentence naming what is missing is deleted; it now pins three claims separately — the ceiling, the gap, the consequence. One mutant returned **INCONCLUSIVE** rather than surviving because it was written with unbalanced parentheses; rewritten properly, inverting the nesting kills **15 tests**, which is what makes the budget-inside-fallback ordering held rather than merely asserted. 2 tests strengthened, 0 implementation changes. |
| `mutate_ai012_campaign.py` | `app/ai/campaign.py`, `app/ai/assembly.py` | **37 of 39 killed, no unexpected survivors** — after a first pass killed 32 of 38 with one inconclusive. Almost every mutant here still produces hypotheses: nothing throws, every bundle gets an explanation, and the damage is a row never written or a per-arm figure off by exactly the population nobody thought to count. **Both genuine gaps were the same gap twice** — a test asserting the run's own record and never the row the run had written. Deleting the write that attaches a verdict left everything green, which is the defect `db-002`'s writer had been added to fix that same afternoon, reappearing one layer up. And swapping the baseline's recording call for the raising gate changed nothing any test could see, because **nothing in the suite ever makes the baseline fail** — it cannot fail on real input, being grounded by construction, which is exactly why it is the check's oracle; a property whose interesting case is unreachable from real input needs a deliberately unreal input or it is not tested at all. A third gap was that every test priced every call, so the budget's completeness flag was a constant. **Two survivors are declared equivalences with their arguments attached**: the harness's own no-op control, and hard-coding the delivered answer's verdict to PASSED — which survives because it is *correct*, since through an assembled arm a non-fallback delivery is one `ai-007`'s injected checker has already passed. The derivation stays anyway: writing the constant would encode another module's invariant as an assumption here, and the pass is what turned that invariant from a belief into a proof. 3 tests added or strengthened, 0 implementation changes. Two faults in the harness itself are recorded as the fourth and fifth hazards below. |
| `mutate_anom014_minimum_duration.py` | `app/detection/rf_noise.py` | — |
| `mutate_scn007_floor.py` | `app/scenario/tracks.py` | 17 of 19, both survivors proven unreachable |
| `mutate_scn008_batch_provenance.py` | `app/scenario/emitter.py` | — |
| `mutate_api011_guard.py` | `app/scenario/guard.py`, `app/api/v1/scenario.py`, `app/scenario/batch.py` | **17 of 17 killed**, three files, because the item is a seam. One survivor on the first run: a check-then-set `take`, which the barrier test caught only sometimes -- two threads released together are usually scheduled so one finishes both halves first, and a test that catches a defect occasionally is worse than none because it reads as coverage. Atomicity is now asserted against the parsed source. Reasoning about mutants before running also found two gaps: both posts in the refusal test carried one configuration, and under an inline thread a batch always finishes so *released in the thread* and *released at the call site* looked identical. |
| `mutate_anom015_chain.py` | `app/detection/chain.py` | **19 of 20 killed with one proven equivalent**, after a first pass left **six survivors** (`.log`). The worst was the item's own central claim: a test watching the statements the database received asserted that the aircraft findings are written before the rules that query them, and removing that write left it **green**, because the pass also writes the radio findings and *that* write still preceded the query -- the assertion was about a table when the claim is about a rule. Five of the six shared one cause: every database-tier test produced exactly one claim with nothing suppressed, which makes counting bids instead of reported claims, counting claims instead of claims-of-this-type, keeping a zone's first receiver, and dropping the declined zones all give identical answers. Fixed with three assertions over a *constructed* assessment carrying a suppressed bid, two claim types and a declined zone, plus one real run with every receiver raised. The same shape is on record from `anom-009`: a suite is weakest exactly where its fixtures are simplest. The equivalent mutant offers the bids to the ladder in the other order, which `anom-013` sorts by a declared constant precisely so arrival order cannot decide a contest. |
| `mutate_api012_detection_payload.py` | `app/api/v1/schemas/operational_picture.py`, `app/detection/chain.py`, `app/db/repository.py`, `app/detection/findings.py` | **33 of 33 killed, no survivors**, after a first pass killed **26 of 28 valid** and reported **five invalid anchors** -- recorded as the seventh hazard below, because black had reflowed three of those lines and one function had been rewritten after the table was drafted. Four files, because the item is a seam: the pass writes, the repository stamps and reads, the converter shapes, the payload assembles. Runs in the container rather than on the host, which is not a convenience -- half of these mutants are only observable against a database, and a host-only run would skip every chain and repository test and score their mutants as survivors of a suite that never ran them. The shape of the risk is that **almost every mutant leaves the endpoint serving a plausible payload**: the screen renders, the levels are bands rather than percentages, the receivers appear, and the only thing wrong is a distinction nobody can see -- which is exactly how the defect this item closes survived, three fields read by three planned panels and written by nothing. **Both genuine survivors were test gaps rather than figures.** One was the third occurrence of a shape this project now treats as a standing caution: the test forbidding the account from being keyed on the rule alone carried **one** finding of that rule, so rule-only and pair keying agreed -- exactly as `anom-009`'s receiver counts and `anom-015`'s single claim had agreed before it, and a property about distinguishing two things cannot be tested on one of them. The other was a docstring standing in for a test: `from_sensor_fault` argues in prose that a row carrying the verdict without the receivers "states a conclusion an analyst cannot test", and nothing asserted the receivers were stored. 2 tests strengthened, 0 implementation changes. |
| `mutate_api015_evidence.py` | `app/db/bundles.py`, `app/api/v1/schemas/evidence.py`, `app/detection/chain.py`, `frontend/src/components/em/EmEvidencePanel.tsx`, `frontend/src/hooks/useEvidenceAccount.ts`, `frontend/src/lib/api.ts`, `frontend/src/types/evidence.ts` | **32 of 32 valid killed, no survivors** (`.log`). Four items in one pass because they are one capability, and because the guarantee that matters spans all four: an account of every reported claim and every stored bundle, with nothing dropped in either direction. **The first run left five gaps and every one was real.** Three frontend survivors were a single defect -- `loading` and `failed` were the same state, so the panel said the evidence could not be loaded while a fetch was in flight, and with the two merged each of the hook's two mechanisms satisfied the test alone, so neither could be shown load-bearing. A fourth survived the fix: the loading test only *mounted*, and the hook's initial state is already loading, so the clear-on-hour-change could not be told from the initial value -- **a guard against stale state is killed only by a test that supplies stale state on purpose**, `anom-015`'s ordering rule in another costume, and the same shape killed the fifth (`min(started_at)` → `members[0]` survives while the builder emits a group's items in time order, so *first* is *earliest* on every fixture). One apparent survivor was **not** one and is the pass's methodological finding: `unclaimed = [` → `unclaimed = [] or [` is equivalent, since `[] or [x]` is `[x]`, and the harness's validity check cannot catch it -- the file parses and the text differs -- so an equivalent mutant reads as a gap. `GUARDED_BY` sends the TypeScript contract to the backend suite, where the parser lives. |
| `mutate_anom016_batch_trigger.py` | `app/detection/settings.py`, `app/detection/chain.py`, `app/db/repository.py`, `app/scenario/batch.py`, `app/pipeline.py`, `measurements/corpus/detection_metrics.py` | **28 of 29 valid killed, no unexpected survivors**, with one **proven equivalent declared in advance** (`.log`). Six files, because the item is a seam across two decisions: where the pass fires, and where the settings it fires under live. The shape of the risk is that **almost every mutant leaves a batch that generates, stores and reports success** -- the hours are the valuable thing and they are written by code this item does not touch, so a trigger can be wrong in every way available to it and the only symptom is a screen saying something slightly false about runs that are perfectly fine. The equivalent mutant drops a `run_id is not None` check that narrows a *type* rather than guarding a case: a completed `RunOutcome` always carries an id, so nothing the generator emits reaches it, and a test written to kill it would have to construct an outcome the system cannot produce. **The first run of this pass aborted on its own sentinel** and is recorded as the eighth hazard below: a threshold of 99 dB violates `ThresholdPolicy`'s own band ordering, so the module raised on import and the suite reported collection errors rather than a failing test -- the runtime twin of a mutant that does not parse. Two value mutants had the same defect and were replaced with single steps. 0 test changes and 0 implementation changes on the pass that ran, which is the first time that has happened here and is attributable to the two corrections the *red* run had already forced out: the baseline's duplicated metric and a refusal whose message was about the wrong thing. |
| `mutate_anom017_baseline.py` | `app/detection/settings.py`, `app/detection/chain.py`, `app/db/repository.py`, `app/scenario/batch.py` | **17 of 17 killed, one equivalent** (`.log`, 18 mutants). Dropping a pinned run, changing a seed, switching off either refusal, naming only the first failing run, keeping the seed from the check, dropping each of the check's four conditions, unordered results, an empty or non-pinned population at the trigger, committing the measurement instead of rolling it back, and moving the bundle skip to the wrong caller are all killed. **Equivalent: removing `join_transaction_mode="create_savepoint"`.** SQLAlchemy's default for a session joining an external transaction never commits it either, so nothing reaches the store; the modes differ only when a session inside the pass rolls back and the pass carries on, which it never does -- any failure propagates and the whole transaction is undone. Kept because it states the intent and guards that future case. |
| `mutate_op010_collapse.py` | `frontend/src/components/em/EmEvidencePanel.tsx`, `frontend/src/hooks/useEvidenceCollapsed.ts` | **14 of 14 killed** (`.log`). The folded header's two counts, the singular, the quiet-hour sentence, the unexamined and failed states, the fold itself, `aria-expanded`, the unclaimed note staying outside the fold, and the four storage guards. One mutant was first written so that it did not parse and was rewritten. |
| `mutate_ops005_schema_drift.py` | `app/db/migrations.py`, `app/db/repository.py`, `app/api/v1/health.py`, the root `Makefile` | **19 of 19 killed, no survivors**, after a first pass killed 18 of 19 and left **one real gap** (`.log`). A guard is the worst thing to get wrong because wrong means silent: every mutant here leaves a service that starts, answers and reports itself healthy, which is exactly the state the item ends -- the defect of record lasted a day with the main screen returning 500, the health route answering 200 and `docker compose ps` saying healthy. The sharpest mutant reads the expected revision out of the version table being checked, which makes the comparison agree with itself on every database there is: it passes everywhere, has no failure case, and looks exactly like a working guard. **The survivor is the shape worth recording**: two heads on disk was asserted on the function that *reads* them and refused by the function that *compares* them, and nothing tested the function between -- so with two heads the expectation silently became whichever head sorted first, and an unreachable database would have reported a bogus expectation beside its *could not tell*. A test at each end of a chain is not a test of the chain. 1 test added, 0 implementation changes. The Makefile is mutated too, because a guard that fires on every first run is one somebody switches off and the two start targets applying migrations first is what stops that. |
| `mutate_api013_hour_selection.py` | `app/dal/models.py`, `app/db/repository.py`, `app/api/v1/operational_picture.py`, `app/api/v1/schemas/operational_picture.py`, `frontend/src/lib/api.ts`, `frontend/src/hooks/useSelectableHours.ts`, `frontend/src/hooks/useOperationalPicture.ts`, `frontend/src/screens/operationalPicture.tsx` | **23 of 23 killed across both suites, no survivors and none declared equivalent** (`.log`). **The first pass here to drive two test runners**, because `op-009` is a frontend item and the frontend has no coverage tooling at all -- so this is its only instrument, and a mutant is dispatched to vitest or to containerised pytest by the file it edits, with a sentinel on each side rather than one: a suite that was never reached scores every mutant as a survivor. `SIDE=frontend` / `SIDE=backend` runs one half. Four frontend suites are in the runner and not one, which earned itself immediately -- accepting a non-list answer from the index is killed in `dataAccess.test.tsx` and nowhere else, an object mapped over as an array taking the whole screen down. **The gap it found is the result worth keeping**: two mutants adding a field to the *repository* row -- the scenario type, and a finding count -- survived the first attempt, because every assertion was about the shape that is **served** and the mapping names its four fields explicitly. Harmless, and a real gap: the item's claim is that the guarantee is structural, and it was structural at one boundary and nowhere else, while the layer below is precisely where somebody would add the field -- in the query, to make the chooser more useful -- with one further edit putting it on the analyst's screen. The same shape as `ops-005`'s survivor one step along: **a guarantee asserted where a value is serialised is not asserted where it is produced**, and only the second is where an engineer with a reasonable motive introduces it. 1 test change (two field-set assertions over the repository row), 0 implementation changes. **The first attempt was stopped by the OOM killer partway through and left a mutant in the source** -- the hazard below, reached from a new direction: twenty-three mutants, most starting a container, is enough churn without any image builds. The guard file made it recoverable; the pass of record was then taken in two parts. |
| `mutate_op001_header_labels.py` | `app/api/v1/schemas/operational_picture.py`, `app/api/v1/health.py`, `frontend/src/lib/api.ts`, `frontend/src/components/em/EmDataModeBadge.tsx`, `frontend/src/components/em/EmSystemStatus.tsx`, `frontend/src/hooks/useSystemHealth.ts`, `frontend/src/components/em/EmNavRail.tsx`, `frontend/src/screens/operationalPicture.tsx`, `frontend/src/App.tsx`, `frontend/src/types/operationalPicture.ts` | **25 of 25 killed across both suites, no survivors** (`.log`), after a first frontend half scored 20 of 21. Three items in one pass because they are one change: a field leaves the payload, the claim it half-carried splits in two, and the half that belongs everywhere moves into the rail. **This pass had more to prove than most.** Four of the frontend tests passed before any implementation existed -- not because they assert existing behaviour but because a test that something is ABSENT from the screen passes trivially while the thing it watches is unbuilt -- and with no coverage tooling on that side, this is the only instrument that can say they hold anything up. `the badge is derived from the payload` and `the rail drops its footer` both turn them red, the second taking 20 tests with it. The sharpest mutant reads a non-2xx from the health route as a lost connection, which reports a misconfigured deployment as an outage -- the conflation `ops-005` exists to end, and the state that cost a day of the main screen returning 500 while the container called itself healthy; its sibling gives the two refusals one wording, after which the strip cannot say which is happening. **The survivor was a harness fault rather than a test gap**, and it is the fifth hazard below in its most ordinary form: restoring `scenario.health` to the TypeScript contract is caught by `api-002`'s parity check, which parses that file and lives in the BACKEND suite because the parser exists once on the side that has one -- so a mutant under `frontend/` is guarded by a Python test, and dispatching on file location sent it to a runner that could not see it. The harness now dispatches on which suite GUARDS a file. 0 test changes, 0 implementation changes: the guard was green throughout and the instrument was wrong about where to look. |
| `mutate_op003_vocabulary.py` | `app/detection/control.py`, `app/api/v1/schemas/operational_picture.py`, `frontend/src/lib/detectionVocabulary.ts`, `frontend/src/components/em/EmLevel.tsx`, `frontend/src/screens/operationalPicture.tsx`, `frontend/src/types/operationalPicture.ts` | **23 of 23 killed across both suites, no survivors** (`.log`). Three items in one pass because the finding that shaped them is shared: the detection summary and the timeline carry the **same** verbatim finding type, so the copy is one module both panels read -- and `the timeline words a conclusion its own way` is the mutant that exists to prove it, killable only by a test reading one label from both panels. **18 of the 58 frontend tests had passed against a raising stub** for reasons that establish nothing (the non-numeric refusals have no digit to find; a stub rendering its label and a valid level satisfies those halves by accident), and with no coverage tooling on that side this pass is the only instrument that could say whether they hold anything up. Two results read better than they count: `the primitive throws rather than refusing` took **36 of 88** tests down, which is the blast radius the component's own note predicts -- a primitive raising during render takes a whole screen with it, a larger failure than the one it prevents; and `anything at all counts as a level` killed 19 where `any string counts as a level` killed 9, the gap being the shape of the guard, since widening the domain to any string still refuses numbers while removing the check lets 87 reach the DOM. **The backend half ran twice**: its first attempt scored `the register loses a reportable producer` INCONCLUSIVE on 2 import errors, the eighth hazard below met a second time -- flipping a producer to intermediate leaves it with no measured background, which `Producer` refuses. Carries the dispatch fix from the previous pass, so the contract mutant runs against the backend parity check rather than against vitest. |
| `determinism_test_reliability.py` | `app/db/findings.py` | Not a mutation pass but the same question one level up: is the determinism test a reliable detector, or did it get lucky once? |

**A mutation score is measured against the tests, and the tests can share the code's wrong
assumption.** `anom-007`'s first implementation passed 36 tests and killed 18 of 20 mutants while
misattributing 21 of 60 interference runs, because both the tests and the code believed that a
neighbour with no reported anomaly is a neighbour reading normally. A high score is evidence the
tests are load-bearing; it is not evidence the rule is right. Only `corpus/` can say that.

## `extensibility/` — what an abstraction actually costs

Needs no database and no corpus; it reads the source tree. `US-R6` asks for the cost of adding a
source adapter as a **measurement** rather than an assertion, and `ai-003` makes the same claim on
the generator side. The interesting number is never how big the new module is — that is mostly the
provider's own API surface. It is how much has to change **everywhere else**: an abstraction that
holds costs a constant, small edit outside the new module, and one that leaks costs a change per
existing caller.

| Script | The question it answers | Figure of record |
|---|---|---|
| `provider_cost.py` | What does adding a hypothesis provider cost outside its own module? The generator-side half of the RQ1 extensibility argument, taken now because the `ai-002` template is a real provider registered through the real interface. | **1 new module + 2 lines in 1 existing file, and 0 changes anywhere else.** The registry holds one import and one mapping entry per provider; the interface imports no adapter, and no caller can tell which generator it holds. The adapter itself is 27 lines of code against a 121-line interface — and that 27 is a **lower bound**, because it wraps a local function and makes no network call. The claim is about the cost outside the module, and that does not depend on what the adapter does. |

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

## How the identifier rule was broken, 2026-09-19

`bundle_end_to_end.py` prints a whole bundle so the thing the AI layer receives can be read. Its
first version routed the finding text through a redactor and **not** `source`, which is the field an
aircraft identifier actually lives in — so the first log it produced carried a dozen of them. Caught
before it was committed, and recorded because the near miss is the useful part: the redactor existed,
was written deliberately, was applied to the obvious field, and missed the one that mattered. A
redactor applied per field is a redactor with a list to keep up to date. Anything added here that
prints a bundle, a finding, or an observation should redact **everything it prints**, not the fields
where an identifier is expected.

## A fourth hazard: a mutant that does not parse tests nothing, found 2026-09-27

A mutant in the `db-002` pass replaced a line with an `if False:` at the *same* indentation as the
line below it. The result was an `IndentationError`, so the migration could not import, 45 tests
errored, and the harness saw a non-zero exit **and** a test summary and scored it KILLED. It was
killed by a syntax error rather than by a test noticing anything, and the mutant proved nothing
about whether the tests would catch a missing check constraint.

This is a sharper version of the second hazard. That one is caught by the no-summary guard, because
a harness invocation that fails to run produces no summary at all. A **broken import still produces
a summary** — `13 passed, 45 errors` — so the guard passes it straight through. An unbalanced-
parentheses mutant in the `ai-011` pass came back INCONCLUSIVE and was caught; this one did not.

The remedy costs two minutes against a forty-minute pass: before running, load the harness's mutant
table, check every anchor matches the source **exactly once**, and `ast.parse` every mutated file.
`db-002`'s and `ai-012`'s tables are both checked this way now, and the check is what turned a
plausible 44-of-44 into a real one.

## A fifth hazard: a harness scoped narrower than the thing it scores, found 2026-09-27

`mutate_ai012_campaign.py` mutates two files — the campaign and, in one mutant, the assembled arm's
type annotation, which is what lets the campaign ask for the full record at all. That mutant
survived a pass that ran only `tests/test_ai_campaign.py`, and it survived for a reason that is not
a gap: the test pinning that annotation lives in `tests/test_ai_assembly.py`.

Nothing was weak. The instrument was looking in one place. The harness now runs both suites, which
is the honest scope — the question it asks is whether *the tests that protect this item* are
load-bearing, and those are not all in one file.

Worth stating because the failure runs in the direction that wastes work rather than hiding defects:
it **manufactures** gaps. An investigator who believed the first report would have written a
duplicate test and found the original only afterwards.

**A second form of it, found 2026-10-03 by the first pass to drive two test runners.** `mutate_op001_header_labels.py` scored a mutant that restores a field to the TypeScript contract as a SURVIVOR, and it was not one: that field is guarded by `api-002`'s parity check, which parses the contract file and lives in the **backend** suite, because the parser exists once on the side that has one. The mutant edits a file under `frontend/`, so dispatching on file location ran it against vitest -- a suite with no reason to parse the contract and no business doing so.

The general shape is worth stating, because a two-language project will meet it again: **where a file LIVES and which suite GUARDS it are different facts, and a harness that assumes they agree reports a green guard as a gap.** The fix is a per-file override consulted before the location fallback, with the reason in the code rather than in a commit message. Note the direction of the error: this hazard's first form produced a flattering score, and this form produces a pessimistic one -- which is the safer direction, but only because it sends you looking for a defect that is not there rather than letting one through.

## A sixth hazard: a mutant that names one defect and implements another, found 2026-09-29

`mutate_anom011_sensitivity.py` carried a mutant called *absent aircraft dropped from denominator*
whose replacement text was `{a for a in staged_aircraft}` where the original read
`set(staged_aircraft)`. Those are the same expression. The mutant was the original, could not be
killed by any test, and was reported as a survivor.

That is worse than a missing mutant, because a survivor is a **claim about the test suite**: it says
a real defect would go unnoticed. Acted on, it sends someone to write a test for a case that is
already covered — the covering assertion was eleven lines long and nine months old — and the new
test then passes for the wrong reason. A missing mutant is a gap; a false survivor is a false
finding.

It is not catchable the way the unparseable mutant is. Comparing the mutated AST against the
original would not have caught this one: a set comprehension and a `set()` call are different trees
that mean the same thing, and semantic equivalence is undecidable in general. What catches it is the
discipline every survivor already deserves — **read the mutant's replacement text before believing
its verdict**, and check that it implements the defect its name describes. Both other hazards in this
series were found the same way and neither was found by a tool.

## Two constraints that apply to anything added here

**OpenSky Data License §3(i) and §3(iii).** Aircraft identifiers must be de-identified in anything
published or disclosed, and the data may not leave the institute. Every script here handles
`aircraft_id` by set membership and counting and **never prints one** — and by that point it is
already `dal-004`'s pseudonym, not the source `icao24`. Committed logs were checked and carry no
identifier. Keep it that way: a `print` of an identifier in a script whose log gets committed is the
violation, not the query.

**Never commit `PSEUDONYM_SEED`**, and never let a log capture it. The `"PSEUDONYM_SEED is not set"`
warning at the head of several logs is Compose noise and carries no value.


## A seventh hazard: an anchor written before the formatter ran, found 2026-10-02

Five of the thirty-three mutants in `mutate_api012_detection_payload.py` reported `INVALID (0)` on
their first pass: the anchor text matched the source **zero** times. Nothing was wrong with the
source or the mutants. The script had been drafted while the implementation was being written, and
`make format` ran afterwards -- black reflowed a generator expression onto one line, split a
three-branch conditional across three, and one of the functions had been rewritten in between for an
unrelated reason.

The guard did its job: `INVALID` is reported separately, excluded from the denominator, and listed by
name, so the score was *26 of 28 valid* rather than a silently inflated 26 of 33. That is the design
working -- the second hazard in this series exists because an earlier harness would have scored
them as passes.

What it costs is a wasted pass. Five mutants over four surfaces tested nothing for fifty minutes,
and three of them cover the two claims the item is most about -- that a suppressed claim is never
written and that the timeline carries no intermediate findings. The practical rule is **write the
anchors against the formatted source**: run `make format` before drafting the mutant table, and if
the implementation changes afterwards, re-read every anchor rather than the ones that look affected.
Two of these five were anchors I had no reason to suspect, because the lines they name were never
edited -- only reflowed around.

## An eighth hazard: a mutant that cannot be imported tests nothing, found 2026-10-02

The runtime twin of the fourth hazard. A mutant that does not **parse** is already excluded, because
it is killed by a syntax error rather than by a test; a mutant that parses and then **raises while
the module is being imported** is the same thing one step later, and the first run of
`mutate_anom016_batch_trigger.py` found it in the worst possible place -- the sentinel.

The sentinel set the radio threshold to 99 dB. `ThresholdPolicy` validates its own bands and refuses
`threshold < medium_at < high_at` when they do not increase, so importing `app/detection/settings.py`
raised, every test module that reaches it failed to collect, and the suite reported `3 errors in
1.28s`. The harness refused to read that as a kill and aborted the whole pass, which is the right
behaviour and cost nothing but a minute -- the alternative would have been thirty mutants scored
against a suite that never ran.

Two of the value mutants had the same defect: swapping the two severity steps for each other breaks
the same ordering rule. Both were replaced with single-step moves that construct cleanly and that the
pin still catches.

The practical rule for any pass over a **configuration** module: every mutant has to be a value the
object will accept. Policies in this project validate aggressively on purpose -- a Medium band at or
below the threshold makes every anomaly Medium, so refusing it at construction is correct -- which
means a mutation table over their values is also a table of things that must stay constructible.
Check by constructing each one before running the pass; it takes seconds and the alternative is a
`SURVIVED` or an `INCONCLUSIVE` that says nothing about the tests.

**Met again on 2026-10-03, and the second instance sharpens the rule.** `mutate_op003_vocabulary.py` flipped a detection producer from reportable to intermediate to check that a parity test really compares against the register. `Producer` refuses an intermediate producer with no measured background -- the band being what makes *silence fails* a measurement rather than an assertion -- so the module raised on import, the suite reported `2 errors`, and the harness declined to score it.

The two instances break the same invariant class **from opposite directions**: the first set a threshold to 99 dB and broke an ORDERING constraint, this one broke a MUTUAL EXCLUSION -- a reportable producer may carry no band and an intermediate one must. Neither edit looks unusual on the page. So the rule stands as written and is worth restating as a procedure rather than a warning: **before running a table over a module whose values are validated at construction, import each mutated module on its own and print what it yields.** On the retry that was one command, and it showed the register's reportable set reduced to two members, which is what the mutant was for.

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

## A second hazard in the harnesses, found 2026-09-21

**A harness that drives `make test-backend` from the wrong directory scores every mutant as killed.**
`make test-backend` lives at the repository root. Run from `backend/` it fails with `No rule to make
target 'test-backend'` — a non-zero exit, which a harness reads as "the tests failed", which it
reports as KILLED. The result is a perfect score produced without running a single test.

Two harnesses had it: `mutate_db009_clustering.py` and `determinism_test_reliability.py`, both using
`parents[2]` where the other five use `parents[3]`. Neither had a published figure — both show "—"
in the table above — which is the only reason nothing has to be withdrawn. Both are fixed.

The general form is worth keeping: **a harness that infers "killed" from a non-zero exit code cannot
tell a failed test from a failed invocation.** Anything added here should confirm the tests actually
ran, not merely that something exited badly.


## A third hazard: a killed run leaves a mutant in your working tree, found 2026-09-22

Every harness here restores the source in a `finally` block. **A `finally` does not survive a
`SIGKILL`** — the OOM killer, `kill -9`, or a runtime reclaiming memory. When
`mutate_ai004_hosted.py` was killed 18 mutants into a 47-mutant pass, one mutated file stayed on
disk. It looked exactly like ordinary uncommitted work: one test red, and the cause three steps
away from anything that pointed at it.

The same shape as the two hazards above, and the third time on this project that an *instrument*
rather than a measurement has been the defect. What is different here is the direction of the
damage: the other two produced a wrong figure, this one silently edits the code under test.

Two mitigations, in order of value.

1. **Run a mutation pass against committed code.** Recovery is then `git checkout -- <files>` and
   takes a second. This is now the rule rather than a suggestion: commit the implementation, run the
   pass, and commit the figure and any gap fixes separately. It costs one extra commit and removes
   the failure mode entirely.
2. `mutate_ai004_hosted.py` writes a **guard file** (`*.in-progress.json`, gitignored) holding the
   originals before the first mutant, and removes it on a clean exit. If the file is present at
   startup, the harness restores from it, deletes it, and refuses to run until you have looked at
   `git diff`. `ai-008`, `ai-011`, `db-002` and `ai-012` now have it too; **six harnesses still do
   not**, and adding it is owed and is a five-line change each.

**It happened again on 2026-09-28, and the guard did its job.** The OOM killer stopped
`mutate_ai012_campaign.py` mid-pass and left `if True:` in place of `if not outcome.fell_back:` in
`app/ai/campaign.py` — a mutant that makes the campaign mark a template stand-in as checked, which
is a plausible-looking row and not a crash. Re-running the harness detected the guard file, restored
the original, cleared the guard and refused to score. Two things are worth taking from the repeat.
The first mitigation carried the recovery as much as the second: the implementation was already
committed, so `git diff` showed exactly one line and the guard's claim could be *verified* rather
than trusted. And **removing the image rebuild did not remove the hazard** — this pass did no Docker
builds at all and was still killed, which is the same finding the `ai-004` pass reached one section
below.

A long pass is also the one most likely to be killed. At roughly **2.5 minutes per mutant** — each
source edit invalidated the image's `COPY app/` layer and forced a rebuild — 47 mutants was about two
hours of continuous Docker builds, which is what exhausted memory in the first place. It killed the
pass twice, and the second time it wedged the Docker daemon as well.

**And again on 2026-10-03, which is now three times.** `mutate_api013_hour_selection.py` was
stopped four mutants into a twenty-three-mutant pass and left `if False:` in place of the route's
404 branch -- a mutant that makes the picture serve the newest hour when a different one was asked
for, which is the item's own sharpest failure case and is invisible on screen. The guard file
restored it and `git diff` confirmed the claim against committed code, both mitigations above
working as written.

What is new is the cause. This pass does no image builds either, and it is not long by the earlier
standard -- roughly 45 seconds a mutant rather than 2.5 minutes. **Twenty-three `compose run`
invocations is enough churn on its own**, so the threshold is lower than the `ai-004` finding
suggested and "no rebuilds, therefore safe" is not a rule. The mitigation added here is to let a
pass be taken in **parts**: this harness takes `SIDE=frontend` / `SIDE=backend`, each half short
enough to finish and memory reclaimed in between. Generalising it to the other harnesses is owed.
Worth stating as a limit of the method rather than a mishap -- a mutation pass is a loop that
rebuilds the world once per mutant, so its cost grows with the mutant count rather than with the
size of the item being scored.

### The rebuild was never necessary, and `test-backend-nobuild` is the fix

The `backend` service **bind-mounts `./backend` to `/app`**. A source edit is therefore already
visible inside the container, and `build-backend` was rebuilding an image whose source the mount
overrides anyway. `make test-backend-nobuild` skips it and keeps everything else — the same compose
run, the same `db-test-create`, the same mounts — so a mutant costs seconds rather than minutes and
a pass does no Docker builds at all.

Two rules come with it. Run `make build-backend` **once** before a pass, because this target does not
pick up a dependency change. And use `make test-backend` for everything else: this one exists for
mutation passes and its comment in the Makefile says so.

**The assumption is checked rather than trusted.** "A mount makes my edits visible" is exactly the
shape of the two defects above, where a harness reported a perfect score without running a test. So
`mutate_ai004_hosted.py` makes one **deliberately broken edit first** and requires the suite to go
red. If the sentinel survives, the harness aborts and says no score from the run can be believed.
Any harness moved onto this target must carry the same sentinel — it is the whole safety margin.

### And that was still not enough: the pass now runs in the virtualenv

Skipping the rebuild was not sufficient. A third attempt was killed at 3 mutants of 47 having done
no Docker builds at all — each `docker compose run` still costs minutes and memory this machine does
not have, and the daemon wedged again afterwards.

`mutate_ai004_hosted.py` therefore runs `tests/test_ai_hosted.py` in `backend/.venv` directly. The
whole 47-mutant pass then takes **under a minute** against roughly two hours, and uses no Docker.

This is a deliberate, bounded exception to the rule that `make test-backend` is the only correct way
to run the suite, and the bounds are what make it acceptable:

- **That file touches no database.** No `database` marker, no session, no PostGIS — it is unit work
  over a payload, a prompt, a schema and an injected fake client.
- **Both runners agree exactly**, 54 passed either way, checked before the switch.
- **The sentinel still runs**, so a harness that stopped reaching the code would abort rather than
  report a perfect score.
- **The authoritative figure is unchanged.** Coverage and the full-tier count still come from
  `make test-backend`, and nothing here replaces them.

Do **not** copy this to a harness whose tests need the database. `PYTHONDONTWRITEBYTECODE` is set and
the cache provider disabled, because a stale bytecode cache has already made one measurement on this
project lie.
