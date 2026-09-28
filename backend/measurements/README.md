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
| `evidence_ref_uniqueness.py` | **Does a finding's `evidence_refs` coordinate identify exactly one observation?** Decides whether `evb-002` resolves by coordinate or the `from_*` functions must record row ids. Also checks the ISO round trip and what one lookup costs. | **Unique, everywhere.** RF by `sensor_id + channel_index + timestamp` and track by `aircraft_id + timestamp` are unique within a run across **both** corpora — 20.7M rows, worst collision 1, **zero** colliding coordinates. ISO round trip exact on 2,000 sampled rows. So `evb-002` resolves by coordinate and no rule adapter changes. **Cost: 64.7 ms per lookup**, index scan on `ix_observations_scenario_run_id` with **38,424 rows removed by filter** — a composite index would be wanted if bundles carry many items. **Superseded on that last point by `bundle_ref_cost.py`:** batching removes the cost the index would have removed, so the index stays a candidate rather than a prerequisite. |
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
| `draw_scored_sample.py` | **Which twenty packages is the scored campaign about?** `eval-004`'s first pass, and it **spends nothing and must run before the one that does**. Draws 10 `possible_interference_zone` and 10 `possible_sensor_fault` from a fixed seed, does the ground-truth join in the open — a bundle carries no scenario type, so the run's own row supplies it and it is recorded *beside* each entry, never inside a bundle — and writes `scored_sample.json`, which is **committed**. That split is the point: an instrument that provably predates its results is worth nothing if the corpus does not, and one script doing both could not enforce the ordering. Only ids, kinds and scenario types are written; the bundles stay in the database, because they carry pseudonymised identifiers and NFR-405 keeps those out of anything committed. Knob: `CORPUS=dev`. | *Not yet drawn.* |
| `scored_campaign.py` | **The scored campaign: twenty packages, both arms, every answer kept.** The second of the two real-billing scripts, and it requires `CAMPAIGN_CONFIRM=yes` — a variable of its own, so approving the three-bundle pre-flight can never also approve this. **It cannot draw its own sample**: the twenty come from the committed `scored_sample.json`, and a missing file is a refusal rather than a helpful redraw, following `ai-012`. It also refuses when the committed sample names a bundle the corpus no longer holds, because regenerated bundles mean the pre-registered corpus no longer exists — a change to argue for in the rubric's change log, not to work around. Three generations per bundle from the model arm and one from the baseline; the first model generation is what `eval-004` scores and is never substituted. Writes `scored_campaign_record.json`. Knob: `CORPUS=dev`. | *Not yet run.* Ceiling 200 calls / $3.00, estimated about **$0.97** before the ~19% the estimate runs high. |

| `bundle_payload.py` | **What does one bundle cost to send, and what is actually in it?** Two questions `ai-004` could not be specified without, and both were about to be answered by guessing. Knob: `CORPUS=dev`. | **Median 6,668 characters, ~1,667 tokens; max 22,540 / ~5,635.** A 20-bundle scored campaign is **~33,000 input tokens for one arm** — so the spend ceiling is about a runaway loop and never about the campaign. An interference bundle is **3.2x** a fault bundle (18,435 against 5,802 median), which unbalances a scorer's reading load and is why `docs/phase9_hypothesis_layer.md` §9 stratifies on bundle kind. On egress: the only positional fields in any bundle are `affected_area.lat`/`.lon`, which are the **synthetic** receiver or zone centre — **no aircraft position leaves**; a track citation carries a `dal-004` pseudonym, a timestamp, a duration and a gap shape. |

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
| `mutate_ai012_campaign.py` | `app/ai/campaign.py`, `app/ai/assembly.py` | **RERUN PENDING** |
| `mutate_anom014_minimum_duration.py` | `app/detection/rf_noise.py` | — |
| `mutate_scn007_floor.py` | `app/scenario/tracks.py` | 17 of 19, both survivors proven unreachable |
| `mutate_scn008_batch_provenance.py` | `app/scenario/emitter.py` | — |
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
