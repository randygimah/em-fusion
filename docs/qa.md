# Concepts Q&A

Running explanations of concepts used across the EM Fusion docs, written for reference while
building and writing up. **This document is explanatory, not authoritative** — where it touches
scope or technical decisions, `em_fusion_v2.md` is the source of truth and this file paraphrases it.
Append new questions as they come up rather than rewriting old answers.

---

## 1. Will the synthetic RF data be designed to simulate specific EM anomalies?

**Yes — but at the level of *observations*, not physics.**

The distinction matters and is worth stating explicitly in the write-up, because it is a limitation
someone will ask about.

A real RF sensor does not emit radio waves into a database. It emits **summary measurements** taken
over some window: "on band X, centred at frequency F, I measured signal power P, signal-to-noise
ratio S, over bandwidth B, at time T, from location L." The synthetic generator produces records of
exactly that shape (`em_fusion_v2.md` section 5) — it is a **sensor-report generator**, not an RF
propagation simulator. There is no waveform synthesis, no IQ sample generation, no path-loss or
multipath modelling, no antenna pattern. Those belong to the RF/IQ classifier work that was cut to
future work.

What "designed to simulate specific EM anomalies" means concretely is that each scenario type has a
distinct **signature** — a characteristic pattern across sensors, space, and time that the
deterministic detectors are meant to pick up:

| Scenario type | RF signature the generator injects | Why it is distinguishable |
|---|---|---|
| Normal baseline | Nothing. Sensors report near-baseline values with normal jitter. | The control condition. A detector firing here is a false positive. |
| GNSS degradation / possible interference | Noise floor raised near the GNSS L1 band (1575.42 MHz), across **several** sensors, **co-located** in a region, for a bounded window — so SNR drops on the affected band. | Multi-sensor + spatially coherent + band-specific + correlated with aircraft position degradation. |
| RF sensor fault | Abnormal readings on **one** sensor while its geographic neighbours stay nominal. | Spatially incoherent — the anomaly does not propagate to nearby sensors, which is not how a real emission behaves. |
| Aircraft coverage gap | **No RF anomaly at all.** Only the aviation side degrades. | The absence of an RF signature is itself the evidence: track dropouts without corroborating RF point at a data-source problem, not interference. |
| Ambiguous mixed evidence | Partial, weak, or conflicting signatures — e.g. a mild RF rise that does not fully align in time or space with the track degradation. | Deliberately under-determined. Tests whether the hypothesis layer expresses uncertainty rather than over-committing. |

Two things follow that are worth carrying into the thesis:

- **The anomaly is the deviation from baseline, not the absolute value.** The generator produces a
  normal-behaviour baseline first, then applies a parameterised perturbation on top. This is why
  `baseline delta` is a first-class field in the RF observation model — the detector's job is
  comparison, not recognition.
- **The scenario types are designed to be *confusable in the right ways*.** GNSS interference and a
  sensor fault both produce "an RF sensor reporting abnormal noise"; what separates them is whether
  neighbouring sensors agree. Coverage gap and GNSS interference both produce "aircraft tracks going
  discontinuous"; what separates them is whether an RF anomaly is present in the same place and
  window. This is the point of the whole system: no single stream disambiguates, the **fusion** does.
  A scenario set where every type was trivially separable by one field would not test anything.

**Limitation to state honestly.** Because the RF data is synthetic and generated at observation
level, detection performance measures how well the pipeline recovers *the anomalies it was told to
inject*. It is not evidence about real-world jamming detection, and the write-up should not claim it
is. What it does legitimately evaluate is the architecture: whether the DAL, fusion, and constrained
hypothesis layer behave correctly and are measurable against known ground truth.

---

## 2. For open aviation telemetry, are state vectors just the data fields returned?

**Essentially yes.** "State vector" is standard tracking/aerospace terminology, not OpenSky jargon:
the complete instantaneous **state** of a tracked object expressed as a **vector** of values — where
it is, how fast, which direction, at one specific instant.

So one state vector = **one aircraft, at one timestamp, as one row.** What you see hovering over an
aircraft on `map.opensky-network.org` is a rendering of that aircraft's most recent state vector.
The historical dataset is the same data model, just every row ever recorded rather than only the
latest one per aircraft.

The historical table (`state_vectors_data4`) gives, per aircraft per 10 seconds:

| Field | Meaning | Used for |
|---|---|---|
| `time` | Timestamp of this state vector | Replay ordering, time-window alignment |
| `icao24` | Unique 24-bit aircraft transponder address | The **track identity** — groups rows into a trajectory |
| `lat`, `lon` | Position (WGS84 degrees) | Map rendering, bounding-box filter, spatial clustering |
| `baroaltitude` | Barometric altitude (m) | Altitude behaviour |
| `geoaltitude` | GNSS-derived altitude (m) | Altitude behaviour; divergence from `baroaltitude` is itself a GNSS signal |
| `velocity` | Ground speed (m/s) | Kinematic plausibility |
| `heading` | Track angle (degrees) | Kinematic plausibility |
| `vertrate` | Climb/descent rate (m/s) | Kinematic plausibility |
| `onground` | Ground flag | Filtering out taxiing aircraft |
| `callsign` | Flight identifier | Display only |
| `lastposupdate` | Timestamp of the last *position* update received | **Position staleness** — the core detection input |
| `lastcontact` | Timestamp of the last *any* message received | Contact loss vs position loss |
| `hour` | Partition key (hour bucket) | File organisation |

Three clarifications that are easy to trip over:

**A state vector is a snapshot; a track is a sequence.** Detection does not operate on individual
state vectors — it operates on **tracks**: the time-ordered series of state vectors sharing an
`icao24`. "Track discontinuity" means gaps or jumps within that series. This is why `icao24` is
load-bearing and why the canonical observation model has to preserve it.

**`time` minus `lastposupdate` is the measurement that matters.** OpenSky publishes a row every 10
seconds whether or not fresh position data arrived. If the aircraft's position has not been updated
for 40 seconds, the row still exists but `lastposupdate` is 40 seconds behind `time`. That delta is
**position staleness**, and it is *directly measured rather than inferred* — you do not have to
guess at degradation from missing rows, the dataset tells you. This is the basis of the
"aircraft update frequency drops" rule and is why the static snapshot was judged to cost nothing in
capability (see `thesis_notes.md`, Methodology).

**Live API vs historical snapshot is a delivery difference, not a data-model difference.** Both
return state vectors with the same semantics. The project uses the archived snapshot so replays are
reproducible, offline, and immune to rate limits — the same data you would get live, frozen.

---

## 3. What is the parameterised scenario generator, and won't it be deterministic?

This question conflates two different determinisms, and separating them is the whole answer.

### What the generator is

A function of three inputs:

```
(scenario_type, parameters, seed) → a complete synthetic scenario run
```

- **`scenario_type`** — the *qualitative* shape. One of the five. Decides which signature gets
  injected (see Q1).
- **`parameters`** — the *quantitative* configuration. Noise amplitude, gap duration, number of
  affected sensors, affected-area size, event timing.
- **`seed`** — the initial value for the pseudo-random number generator that fills in everything the
  parameters leave open: which specific sensors, exactly where in the region, exact onset time
  within the allowed window, and the per-sample random jitter.

### Why determinism is the *point*, not the problem

> "won't this be deterministic, meaning we will end up with the same outputs for each run?"

Determinism here is **per seed**, not across seeds.

- Same type + same parameters + **same seed** → byte-identical run, every time. This is
  **reproducibility**, and it is a deliberate requirement: a result in the thesis can be regenerated
  exactly, by an examiner, months later.
- Same type + same parameters + **different seed** → a *different* run of the same kind. Different
  sensors affected, different onset, different jitter — but the same underlying scenario type, so
  the ground-truth label is still known.

The useful analogy is a **shuffled deck of cards**. Shuffling with seed 42 always produces the same
order — that is determinism. But seeds 42, 43, 44 produce three genuinely different orders. You are
not stuck with one deck; you have as many decks as you have seeds, and you can always get any one of
them back.

So "20–30 randomised runs per scenario type" means 20–30 **different seeds**, not 20–30 repeats of
one run. What varies is the data; what stays fixed is the recipe.

### Why this matters for the evaluation

With one run per scenario type, precision and recall are 1.0 or 0.0. That is an anecdote, not a
result — you cannot tell a robust detector from a lucky one.

With 25 seeded runs per type you get a **distribution**: a detection rate with variance, false
positives across varied conditions, latency spread. You can say "the GNSS detector achieved recall
of 0.92 across 25 runs" and defend it. You can also see *where* it fails — e.g. that recall collapses
when `gap_duration` falls below the rolling-average window, which is a finding rather than a bug.

### Three determinisms in the system, and which one is allowed to vary

Worth keeping straight, because they get discussed as one thing:

1. **The generator** is deterministic given a seed. → Reproducibility. Intended.
2. **The detectors** are deterministic given data — threshold rules, z-scores, and spatial queries
   have no randomness at all. Same observations always produce the same anomalies. → This is the
   deterministic-detection scope decision, and it is why detection results are trustworthy: any
   variation across runs comes from the *data*, never from the detector being moody.
3. **The AI hypothesis layer** is the one component that is *not* strictly deterministic, even at
   temperature 0 and a fixed seed — floating-point non-associativity in batched inference means
   identical inputs can occasionally produce different tokens. This is why the evaluation harness
   generates **N hypotheses per evidence bundle and records grounding variance**
   (`em_fusion_v2.md` section 5, Evaluation Harness) rather than assuming one generation is
   representative.

Variation enters the pipeline in exactly one place — the seed — and is measured in exactly one other
— the AI layer. Everything between is deterministic by design.

---

## 4. What are rolling averages, z-score deviation, and spatial clustering?

These are the deterministic detection methods (`em_fusion_v2.md` section 5). Two of them establish
"what normal looks like"; one establishes "did these things happen together."

### Rolling average (moving average)

The mean of the last *N* samples, recomputed as the window slides forward.

```
readings:        94  96  95  97  95  96  120  118  121
rolling mean(5):              95.4  95.8  96.6  ...
```

Two jobs:

- **Smoothing.** A single spurious reading barely moves a 5-sample mean, so the detector does not
  fire on one bad sample. Genuine sustained change does move it.
- **Producing the baseline.** In this project the baseline engine computes rolling averages over
  **normal-scenario runs** (`implementation.md` Phase 8) — RF noise per sensor, aircraft update rate
  per region — to establish the reference the detectors compare against.

Note the structural point: rolling averages are listed alongside the detectors but are really the
**baseline engine feeding them**. A rolling average does not, by itself, decide anything. It
produces the μ that the threshold rules and z-scores are measured against.

The tuning trade-off worth recording: a **short window** reacts fast but is noisy (false positives);
a **long window** is stable but slow to react and can absorb a short anomaly entirely. An anomaly
shorter than the window may never register — which is why `gap_duration` is a scenario parameter, so
the evaluation can find where that boundary sits rather than guessing.

### Z-score deviation

How many standard deviations a value sits from the mean:

```
z = (x − μ) / σ
```

where μ is the baseline mean and σ the baseline standard deviation. Conventionally |z| > 3 is an
outlier (~99.7% of normally distributed values fall within ±3σ).

**Why this is better than a fixed threshold here:** it is *self-calibrating per sensor*. Suppose two
RF sensors:

| | baseline μ | baseline σ | reading | z | verdict |
|---|---|---|---|---|---|
| Quiet rural sensor | −95 dBm | 2 dB | −85 dBm | **+5.0** | anomalous |
| Noisy urban sensor | −95 dBm | 6 dB | −85 dBm | +1.7 | normal |

Same absolute reading, correctly different verdicts. A fixed threshold at −88 dBm would flag both,
drowning the urban sensor in false positives. The z-score encodes "unusual **for this sensor**",
which is exactly the semantics an analyst wants.

**Two caveats to record as limitations:**

- **It needs a clean baseline.** μ and σ must be estimated from a period known to be normal. If the
  anomaly is inside the baseline window it inflates σ and *hides itself* — the anomaly raises the bar
  it has to clear. Hence baselines come from **normal-scenario runs**, not from the run under test.
- **It assumes roughly normal, roughly stationary data.** Heavily skewed distributions or a drifting
  baseline break the ±3σ interpretation. At prototype scale this is acceptable and stated, not
  solved.

### Spatial clustering

Grouping observations by geographic proximity — asking whether things that happened are *near each
other*, rather than scattered.

In this project it is deliberately the **simple form**: not DBSCAN or k-means (explicitly cut to
future work), but a proximity/containment query — *"are the track discontinuities clustered within
N km of the RF anomaly zone, in the same time window?"* — executed as an indexed PostGIS predicate
(`ST_DWithin`), which is the concrete justification for using PostGIS at all (see Q6).

ST_DWithin is a spatial SQL function that evaluates if two geometries are within a specified distance of each other, returning true or false. It utilizes spatial indexes, making it significantly faster and more accurate than generating geometric buffers

**This is the component that makes the system fusion rather than two dashboards side by side.**
Consider the difference:

```
RF noise elevated somewhere.            → weak. Could be a sensor fault.
Aircraft tracks degraded somewhere.     → weak. Could be a feed problem.
RF noise elevated AND tracks degraded
  in the SAME 20 km area
  in the SAME 15-minute window.         → strong. Co-location is the evidence.
```

Neither stream alone supports the hypothesis. Their **coincidence in space and time** does, and
quantifying that coincidence is what spatial clustering contributes. It is also what distinguishes
scenario 2 (GNSS interference — spatially coherent across sensors) from scenario 3 (sensor fault —
one sensor anomalous, neighbours nominal), and what makes scenario 4 (coverage gap) identifiable by
the *absence* of a co-located RF anomaly.

This is why `FUSION-SPATIAL-003` appears as a rule ID in the example evidence bundle: the spatial
correlation is itself a piece of traceable evidence, produced by the fusion engine rather than by
either source.

---

## 5. What is a bounding box?

A **bounding box** is a rectangle in coordinate space, defined by four numbers: minimum and maximum
latitude, minimum and maximum longitude.

```
lat_min = 45.0, lat_max = 55.0
lon_min =  0.0, lon_max = 15.0     ← roughly Central Europe
```

Any point is inside it if `lat_min ≤ lat ≤ lat_max` and `lon_min ≤ lon ≤ lon_max`. That is the
entire concept — two comparisons per axis, which is why it is used everywhere: it is the cheapest
possible spatial test.

**It is not the map viewport.** It does not change when you zoom or pan, and it is not derived from
what is currently rendered. It is a fixed geographic filter, chosen once and recorded. (In GIS
generally, "bounding box" can also mean the smallest axis-aligned rectangle that *bounds* a given
set of features — hence the name — but in this project it is chosen up front rather than computed.)

### Its two roles here

**1. Ingest filter — making the data tractable.** OpenSky's raw hourly files are *global*: millions
of rows, hundreds of MB per hour. Applying the bounding box on ingest keeps only rows inside the
study region, producing an extract small enough to archive and version alongside a manifest
(`em_fusion_v2.md` section 5).

**2. Study-region definition — a validity control.** This is the important one and is already
recorded as a threat to validity in `thesis_notes.md`. OpenSky's coverage comes from volunteer
ground receivers and is geographically uneven. In a sparsely covered region, aircraft genuinely drop
out because *nobody is listening* — and those dropouts are **indistinguishable, to the detector,
from the synthetic ones being injected**. Ground truth would be contaminated and the false-positive
rate uninterpretable. Choosing a densely covered box (Central Europe) is what prevents this, and the
acceptance check — run `Normal baseline` against the extract and confirm no dropouts appear before
injection — is what verifies it.

### Where it shows up again

Bounding boxes are also how spatial **indexes** work internally. A GiST index does not store complex
polygons at every node; it stores their bounding boxes. A query first eliminates candidates with
cheap rectangle comparisons, then runs exact geometry maths only on the few survivors. So the same
primitive that filters the download also makes the PostGIS queries in Q6 fast.

In PostGIS a box is constructed with `ST_MakeEnvelope(lon_min, lat_min, lon_max, lat_max, 4326)`.

---

## 6. What is PostGIS — just a Postgres store for geospatial data?

That is the right instinct but understates it. PostGIS is an **extension** to PostgreSQL that turns
it into a spatial database. It adds three things, and the third is where the actual value is.

### 1. Spatial types

Real column types — `POINT`, `LINESTRING`, `POLYGON`, and so on — instead of two loose `float`
columns. Each carries an **SRID** (spatial reference identifier) declaring the coordinate system:
`4326` is WGS84, the lat/lon system GPS and OpenSky use.

This is why `observations.location` and `anomalies.affected_area` are `geometry` in the schema
(`em_fusion_v2.md` section 9) — an anomaly's affected area is a *polygon*, not a pair of numbers, and
the database understands that.

### 2. Spatial functions

Several hundred `ST_*` functions expressing spatial relationships declaratively:

```sql
ST_DWithin(a, b, 20000)   -- is a within 20 km of b?
ST_Contains(zone, point)  -- is the point inside the zone?
ST_Distance(a, b)         -- how far apart?
ST_Intersects(a, b)       -- do they overlap at all?
```

The alternative is pulling every candidate row into Python and computing haversine distances by
hand — more code, slower, and impossible for the database to optimise.

### 3. Spatial indexes — the actual reason

PostGIS adds **GiST** indexes over geometry columns. Without one, "find all track discontinuities
within 20 km of this RF zone" is a full table scan computing a distance for every row. With one,
the index eliminates almost everything using bounding-box comparisons (see Q5) before any real
geometry maths runs.

This is the load-bearing point, and it is the reason the lakehouse alternative was rejected:
**Trino has `ST_*` functions but no comparable indexed spatial join, and Iceberg has no spatial
partitioning** (`thesis_notes.md`, storage substrate). The functions are the easy part to replicate;
the index is not.

### Why the project genuinely needs it

The justification is one specific query — clustering track discontinuities within N km of an RF
anomaly zone (Q4) — which is one of the four detection methods and the mechanism behind the
`FUSION-SPATIAL-003` evidence item. It is not "we might want maps later." Adopting PostGIS for a
prototype needs a load-bearing reason, and that query is it.

### Two traps worth knowing before writing spatial code

- **`geometry` vs `geography`.** On a `geometry` column with SRID 4326, distances are computed in
  **degrees**, not metres — so `ST_DWithin(a, b, 20000)` asks for 20,000 *degrees*, which is
  nonsense and will silently match everything. Either cast to `geography` (`ST_DWithin` then works in
  metres over a spheroid, slower but correct) or project to a metric CRS. Decide this once in the
  repository layer and keep it consistent.
- **The index must match the query.** A GiST index on `geometry` is not used by a query that casts to
  `geography` at runtime. Index the expression you actually query on, and check with `EXPLAIN` that
  the index is being hit rather than assuming it is.

---

## 7. Will the blind scorer just be scoring AI deviation from ground truth?

**No — and the assumption is worth unpicking, because it describes work two automated checks already
do, and misses the only thing the human is there for.**

### Ground truth is already scored, twice, without a human

| Check | What it compares | How it is scored | Spec |
|---|---|---|---|
| Detection metrics | Anomalies raised vs anomalies the generator injected | Machine, deterministic | `eval-002` |
| Grounding check | Every `supporting_evidence` item vs the evidence bundle | Machine, per-claim trace | `ai-008`, `eval-005` |

Between them, *"did the system detect the right thing"* and *"did the hypothesis cite evidence that
actually exists"* are settled before any human sees output. A rater asked to re-judge either would be
slower, less consistent, and adding nothing.

### What is left is what no machine can judge

Here is the part that makes the human necessary. **After the grounding check, both scored arms are
100% schema-valid and 100% grounded** — that is what constrained decoding plus a grounding gate
*mean*. So neither schema conformance nor grounding rate can distinguish the hosted arm from the
template arm; both score perfectly by construction. If those were the only measurements, RQ3 would
have no evidence at all.

The distinguishing question is whether the explanation is **useful to an analyst**, and that is
irreducibly a judgement:

| Dimension | What it asks | Schema field |
|---|---|---|
| Evidence use | Does it reason *from* the findings, or merely restate them? | `supporting_evidence` |
| Uncertainty quality | Substantive, or boilerplate? | `evidence_against_or_uncertainty` |
| Alternatives quality | Genuine competing explanations, or filler? | `alternative_explanations` |
| Actionability | Specific and appropriate, or generic? | `recommended_human_action` |
| Overall usefulness | Would this help an analyst triage faster? | whole |

Note what dimension 1 does: the grounding check proves a cited rule ID **exists in the bundle**; it
cannot tell you the finding was used *meaningfully*. A hypothesis can cite every rule ID correctly
and still reason badly. That gap between "traceable" and "well-reasoned" is exactly the human's
territory, and it is worth stating plainly in the write-up — it is the honest limit of automated
grounding.

### The two dimensions that *do* reference ground truth

Two do, and they are handled separately: **cause correctness** (does the stated cause match the
injected condition?) and **confidence calibration** (is `Low`/`Medium`/`High` warranted by the
evidence — a `High` on the ambiguous-mixed-evidence scenario is wrong however well written it is).
These are scored in a **separate final pass**, after all quality dimensions are complete, so that
knowing the ground truth cannot colour the earlier judgements.

### Deliberately excluded: fluency

Writing quality is not scored. It would inflate the hosted arm for reasons having nothing to do with
the constrained-generation architecture under study, contaminating the headline result. If it is
measured at all it is reported separately.

**A threat to validity to record now, not later.** Template output is stylistically distinctive and a
rater will probably recognise it. Rendering is normalised — identical field order, identical
formatting, no markdown flourishes — but blinding is imperfect and the write-up should say so. The
template must *not* be made to imitate model prose; that would corrupt the baseline it exists to
provide.

See `docs/scoring_rubric.md` for the instrument itself and `em_fusion_v2.md` section 5.9 for how the
harness produces the corpus.

---

## 8. When you say 20 triads, do you mean the randomised runs?

**No.** Three different units get conflated here, and the arithmetic only works if they are kept
apart.

```
scenario run   →   evidence bundle   →   scored item
(one seed)         (one grouped set       (one hypothesis
                    of related             from one
                    anomalies)             generator)
```

- A **run** is one execution of `(scenario_type, parameters, seed)` — see Q3. There are 20–30 per
  scenario type, so 100–150 in total.
- A **bundle** is what the evidence bundle builder produces by grouping related anomalies from a run.
  One run yields zero, one, or several. Normal-baseline runs should yield **zero** — that is
  `anom-008`, the correct non-detection, and it is why bundles come only from the four anomalous
  types. Expect roughly 80–120 bundles available.
- A **scored item** is one hypothesis: one bundle passed through one generator.

**Detection metrics run at full N** — every one of the 100–150 runs. Only the *human scoring* is
sampled, because human attention is the scarce resource and machine metrics are not.

### The sampling arithmetic

The scored corpus is a **stratified sample of bundles**, not of runs: roughly 5 bundles from each of
the four anomalous scenario types, so ~20 bundles. Stratified rather than random, so no scenario type
is accidentally absent from the comparison. Each selected bundle is generated by both scored arms:

```
20 bundles × 2 arms (hosted, template)  =  40 hypotheses
40 hypotheses × 2 raters                =  80 scoring judgements
                                        ≈  90 minutes per rater
```

The pairing matters: because both arms are scored on the *same* bundle, the comparison is **paired
within bundle**, which is far more powerful than 20 independent observations would suggest. Bundle
difficulty is held constant and cancels out of the comparison.

### Why full double-scoring, rather than an overlap fraction

An earlier version of this plan used a larger corpus with only a fraction double-scored — you score
everything, a second rater scores a slice, and inter-rater agreement is computed on that slice alone.
That is a standard technique and it exists for one reason: to buy corpus size with someone else's
time, when they cannot commit to the whole thing.

It was dropped because the trade was not needed. Full double-scoring at a smaller N is both simpler
and stronger:

| | Partial overlap | Full double-scoring |
|---|---|---|
| Corpus | Larger | Smaller |
| κ computed over | The overlap subset only | Every scored item |
| Unscored-by-second-rater remainder | Must be argued to be trustworthy | Does not exist |
| Explanation required in the write-up | The overlap design and its assumptions | None |

Use the overlap design only if the second rater cannot commit ~90 minutes. It is a concession, not
an improvement.

### One thing that does *not* multiply the corpus

The harness also generates **N hypotheses per bundle per arm** to measure grounding variance
(`em_fusion_v2.md` section 5.9, and Q3 on the AI layer being the one non-deterministic component).
That is a **separate, machine-computed measurement over all N**. Raters see exactly **one** generation
per arm per bundle. Confusing the two multiplies the human corpus by N and makes the scoring plan
impossible.

---

## 9. Is the synthetic RF data on a specific frequency range?

**It is now.** It wasn't when the question was asked, and finding that out is how the channel grid
got specified.

The original model gave each RF observation a `frequency`, a `band`, and a `bandwidth`, and named
GNSS L1 (1575.42 MHz) as the band the interference scenario targets — but there was **no channel
grid**, so no notion of frequency adjacency anywhere. Baselines were per-band or per-sensor; the
sensor-fault rule reasoned only about *spatial* neighbours. The model could say "this sensor is
noisy". It could not say "the noise is confined to one channel" or "it is smeared across the band."

### The grid

Observations are emitted on a fixed **sensor × channel × time** grid:

```
Channels:  8, each 2 MHz wide
Centres:   1567.42  1569.42  1571.42  1573.42  [1575.42]  1577.42  1579.42  1581.42   MHz
                                                 GNSS L1
Sensors:   6–8, at recorded positions
Cadence:   every sensor reports every channel, every interval of simulated time
```

One channel sits exactly on L1 with four either side, so adjacency runs in both directions.

This is **a plausible abstraction, not an RF-accurate channelisation** — the real L1 band is wider
than 16 MHz. That is consistent with Q1: this is a sensor-report generator, not a propagation
simulator. Eight channels is simply the smallest grid that supports the adjacency reasoning below.

### Why adjacency in frequency earns its place

It is the same argument the project already makes spatially, moved one axis over:

| | Spatial version | Frequency version |
|---|---|---|
| The physical fact | A real emission affects nearby sensors together | A real emission raises adjacent channels together |
| So an isolated deviation… | one sensor abnormal, neighbours nominal | one channel abnormal, adjacent channels nominal |
| …is evidence about | the instrument, not the environment | the instrument, not the environment |

So a single anomalous channel with clean neighbours on the same sensor **reinforces sensor fault over
interference** — a second, independent line of evidence for the discrimination that `anom-007` already
performs spatially. The axis strengthens an existing claim rather than introducing a new mechanism,
which is why it was worth adopting late.

Three consequences:

- **Baselines become per-sensor-per-channel.** Pooling channels into one per-sensor baseline hides a
  single-channel deviation inside the spread of the other seven.
- **Evidence bundles group on three axes** — time, space, *and* frequency adjacency. Grouping on time
  and space alone would fragment one broadband event into eight unrelated findings and hand the AI
  layer an incoherent picture.
- **The grid is dense.** Every sensor reports every channel every interval, even when there is nothing
  to report. A sparse grid would make a genuine dropout indistinguishable from "the generator had
  nothing to say."

### Narrowband vs broadband is a parameter, not a sixth scenario type

Once channels exist, `gnss-degradation` can inject a spike confined to the L1 channel or a raised
floor across all eight. That stays a **parameter** of the existing type. The five scenario types are a
scope boundary; adding a sixth for what is a variation within one phenomenon would reopen it.

### Why six to eight sensors, not three

Three sensors is enough for a non-spatial pipeline. It is not enough here. `anom-004` clusters track
discontinuities in PostGIS and `anom-005` requires spatial coherence *across* sensors — with three,
"the discontinuities are clustered" and "the neighbours are nominal" are not claims that can
meaningfully be tested, and the PostGIS justification would be correspondingly thin. Sensors are also
positioned deliberately, so that a candidate interference zone contains some and excludes others.

### What ground truth is allowed to touch: nothing

Related and worth stating separately. The generator records what it injected on
`scenario_runs.ground_truth`. **Nothing downstream may carry it** — no observation, adapter record,
detector input, API response, or evidence bundle, whether as a field, a label, or an inferable
artefact such as a scenario-type string attached to an observation (`api-009`, `NFR-604`).

The failure this guards against is easy to miss because it looks fine: a detector with access to the
answer is not a detector, and every precision, recall, and false-positive figure computed from such a
run is meaningless while still looking entirely plausible. No test catches it after the fact, which is
why it is asserted structurally.

---

## 10. Can we use Parquet for the synthetic data?

**For the archived aviation extract, yes. For anything the system queries, no** — and the distinction
is load-bearing rather than pedantic.

### The question underneath the question

Parquet-as-storage was already considered and rejected for this project — the lakehouse substrate
(Parquet on object storage under Iceberg, queried by Trino) is in the v1 out-of-scope list, with the
reasoning in `thesis_notes.md`. The short version: **PostGIS is justified by exactly one thing**, the
indexed spatial join behind `anom-004` (see Q6). Trino has `ST_*` functions but no comparable indexed
spatial join, and Iceberg has no spatial partitioning. Put the observations in Parquet and the reason
the database exists evaporates, taking `anom-004` and `db-004` with it.

So the test to apply is simple: **does anything *query* the Parquet?**

| Use | Queried? | Verdict |
|---|---|---|
| Archived OpenSky extract | No — read once at replay, converted through the DAL into PostGIS | **Yes, use Parquet** |
| Canonical observations | Yes — spatial and temporal queries | **No.** PostGIS, and the spatial index is the whole point |
| Generated synthetic observations | — | **Don't persist them.** `scn-001` guarantees byte-identical regeneration from type + parameters + seed, so the seed *is* the artefact |
| Evaluation exports | No — read by humans and spreadsheets | CSV/JSON per `eval-003`; Parquet adds nothing |

### Why Parquet is a genuine improvement for the archive

OpenSky publishes CSV, Avro, and JSON. Parquet is columnar, typed, and compresses hard enough that a
bounding-box-filtered hour becomes small enough to **commit to the repository**. That is the real gain
— not disk space, but that the pipeline then reproduces from a fresh clone with no download step, no
external dependency, and no drift between what was measured and what a reader can re-run. `pyarrow`
comes along with Pandas, which the evaluation harness needs anyway, so it costs nothing new.

### The general point

A **format** decision and a **substrate** decision are different decisions, and conflating them is how
a rejected architecture returns unnoticed. Parquet holding a static input file touches nothing the
lakehouse rejection was about; Parquet serving reads would reverse it entirely. Same file format,
opposite architectural consequence.

---

## 11. If the API contract is known, isn't it better to build the backend first?

**Yes for two specific features — and the reason is narrower and better than "backend-first is
generally sensible."**

The contract-first design was meant to make this *not* matter: a typed `OperationalPicture` mirroring
the future response, screens taking it as a prop, one seam in `App.tsx` where a fetch replaces the
mock import. That works, and for most of the UI the mock is genuinely sufficient.

**But it makes the data source substitutable, not the *behaviour*.** Two features have semantics that
live on the server and cannot be developed against a client-side stand-in however faithful its shape:

| Feature | Why a mock can't stand in |
|---|---|
| View filter (`api-007`) | Filtering happens server-side, so excluded rows never arrive. The suppressed counts that keep "+n nominal hidden" truthful exist **only** as response metadata — a client-side filter has nothing to report because it can still see everything. |
| Playback buffer (`api-008`) | `track-window` is bounded server-side, and over-long spans are truncated *with the truncation reported*. There is no mock equivalent of that behaviour to build against. |

The original checklist had already half-admitted this, instructing that the mock be filtered "behind
the same function signature the API call will use" — which is an explicit acknowledgement that the
work would be done twice.

### The revised order

```
Phase 3 layout  →  Phase 5 contract mirror  →  Phase 3 view filter  →  Phase 4 MapView  →  playback
```

Layout work (nav shell, status bar, map placeholder, panels, timeline) is design-driven and gains
nothing from a backend, so it still goes first. Phase 5 is small — `/operational-picture` returning
the mock shape **from a static fixture**, a contract test, and the `api.ts` function. It needs no
database, no generator, and no DAL; the point is to establish the seam, not the data.

### One risk the reorder introduces

The backend fixture and the frontend `OperationalPicture` type now describe one contract in two
languages, and will drift silently. Mitigation: assert the same shape from both sides, so a renamed
field fails a test rather than surfacing as an empty panel in the browser.

---

## 12. Why does `docker run -v /Users/randy.gyimah/structurizr:...` fail with "permission denied"?

**Because the directory does not exist and Docker cannot create it — the error is about the wrong
thing.** The home directory is `/Users/randygyimah`, with no dot. The mount source `/Users/randy.gyimah`
was a typo for a path that has never existed.

The misleading part is the wording. Docker's bind-mount behaviour is to *create* a missing mount
source rather than fail, so it tried to `mkdir /Users/randy.gyimah` — and `/Users` is not writable
by a normal user on macOS. The permission error is therefore about creating a **new** directory in
`/Users`, not about access to the directory you meant. The wrong assumption it invites is "Docker
Desktop needs file-sharing permission for my home folder", which sends you into Settings → Resources
→ File Sharing, where nothing is wrong. Read `mkdir <path>: permission denied` as *"that path does
not exist"* first, and only then as a permissions problem.

The general rule: **an absolute bind-mount source should always be a path you have confirmed exists.**
`-v "$(pwd)/docs/architecture":/usr/local/structurizr` is safer than a hand-typed absolute path
precisely because the shell resolves it and a typo fails loudly at the shell rather than quietly at
Docker.

Two related corrections came out of the same command:

| Assumption | Correction |
|---|---|
| `structurizr/structurizr` is the wrong image; Lite is `structurizr/lite` | **Both work.** Structurizr consolidated its tooling into one `structurizr/structurizr` image with subcommands. `local` is the successor to the standalone Lite image, and the trailing `local` in the original command was correct. The separate `structurizr/cli` image now prints an end-of-life notice. |
| Port 8080 is fine | It collides with `uvicorn --port 8080`, which Vite proxies `/api` to. Publish on **9090**; the container still listens on 8080 internally, so only the host side of `-p` changes. |
| The model can live anywhere on disk | It should live in the repo under `docs/architecture/`, and the mount should point there. Structurizr writes browser edits back to `workspace.dsl`, so mounting the repo directory is what makes diagram edits land in git instead of in a scratch folder. |

Worth recording as a limitation: **PNG/SVG export is not available from the Docker build** — it
reports "Exporting to PNG/SVG is not supported in this build" and the `-url` option it advertises for
that purpose does not change the outcome. Thesis figures have to be exported by hand from the browser
UI. Text formats (`mermaid`, `plantuml`, `json`, `dot`) do export from the CLI, and those are what
keep the "diagrams that cannot be regenerated go stale silently" property intact; the PNGs are
downstream artefacts of a model that is itself regenerable.

A second one, found while writing the model rather than running it: `theme default` in the DSL
fetches from `static.structurizr.com`, which reaches **end of life on 30 September 2026** — after
submission, but well within the life of the thesis as a document. A model whose rendering depends on
a service that will be switched off is not regenerable in the sense the checklist means, so the theme
is omitted and the styles are written out in full.

---

## 13. Can you explain more about the basemap tiles? Raster or vector?

**Vector — and self-hosted.** But the more useful correction is upstream of that question.

The wrong assumption was that choosing MapLibre had already settled the hosted-dependency question.
It had not. **MapLibre is a renderer and ships with no map data.** "No account or access token
required" is a statement about the *library*, not about the map. Point MapLibre at nothing and you get
a blank canvas — which is exactly why `MapView` needs a placeholder path. The tiles still come from
somewhere, and the default somewhere is a tile provider's server.

So `em_fusion_v2.md` §12 — "the data and map layers have no hosted dependency at all — archived
replay, **tokenless tiles**" — was conflating two different properties:

| Property | Means | Satisfied by MapLibre alone? |
|---|---|---|
| **Tokenless** | No account, no API key, no registration | Yes |
| **Self-hosted** | The bytes come from your own machine | **No** |

A web map draws its background — coastlines, roads, terrain, labels — by fetching pre-cut tiles
indexed by zoom/x/y as you pan. Those requests go somewhere. Without self-hosting, the browser is
talking to a third party on every pan and zoom.

### Raster versus vector

| | Raster | Vector |
|---|---|---|
| What ships | Pre-rendered PNG/JPEG images | Geometry + attributes (protobuf), drawn on the GPU |
| Who styles it | Whoever rendered the tiles | You, at runtime, from a style JSON |
| Restyling | Requires re-rendering every tile | Edit the style, reload |
| Zoom | Snaps between integer levels | Continuous |
| Labels | Baked into the image; rotate with the map | Live text; stay upright, collision-managed |
| Size | One image per level per tile | One tile serves a range of zooms |

**The decisive argument here is styling, not performance.** The Operational Picture is exception-first
— the whole premise is that anomalies are the most salient thing on screen. A raster basemap arrives
with standard-OpenStreetMap colours already burned in: bright, high-contrast, full of road casings and
place labels. Composited under dark anomaly overlays, it competes with the exact signal the screen
exists to foreground, and there is no way to tone it down short of a translucent scrim over the whole
map. With vector tiles the basemap style is written from the `DESIGN.md` tokens like any other part of
the interface, and can be deliberately subordinated.

### How self-hosting works without a tile server

The light option is **PMTiles**: the entire tile set as a *single file*, queried by the browser using
HTTP range requests. No tile-server process, no new Compose service — the nginx container that already
serves the frontend bundle can serve it as a static asset.

The data comes from a **Protomaps** build of OpenStreetMap. The planet file is ~100 GB, but a
bounding-box extract is tens of MB — and the project already has a fixed bounding box, chosen for the
OpenSky corpus. The same box does for both.

Worth recording as traps, both of which fail *silently*:

- **Glyphs and sprites.** A vector style references its fonts and icon sprites by URL, and stock
  styles point those at a CDN. Self-host the tiles but not the fonts and the hosted dependency comes
  straight back — with the map still rendering perfectly, so nothing looks wrong.
- **Attribution.** OpenStreetMap data is **ODbL**: "© OpenStreetMap contributors" must appear on the
  map. Same class of obligation as the OpenSky licence note, and the same rule applies — capture it at
  download time, because licence terms cannot be reconstructed from a file later.

## 14. Can the local model be removed from the architecture — it's just a silent fallback?

**No — but the instinct behind it was right, and the model was changed.** The word doing the damage
is "silent", which was carrying two incompatible meanings:

| "Silent" as… | Meaning | Project position |
|---|---|---|
| Non-interrupting | No error state, no modal; the hypothesis just appears | **Required.** §12: the degradation "must hold without an error state reaching the analyst" |
| Undisclosed | The analyst cannot tell which generator produced the output | **Forbidden.** §12: the UI "must surface *which* generator produced a hypothesis rather than hiding the degradation"; Phase 9 repeats it |

So a fallback that fires without disturbing the analyst is the specification; a fallback that fires
without the analyst being able to see it did is the opposite of the specification.

The second assumption worth correcting is that a fallback is not part of a system. **A fallback is a
designed path with a named trigger** — that is what distinguishes it from a crash. If the architecture
does not contain it, then when the hosted API drops out the system is doing something no diagram
describes, and the §12 reliability claim has nothing behind it. "What happens when the API is down?"
is a question an examiner will ask, and the architecture is where it gets answered.

What *was* wrong is where it was drawn. At Level 1 the local model server sat beside the analyst and
the archived corpus as a peer, which reads as "this system routinely depends on two model providers".
It does not. **Resolution: excluded from Levels 1 and 2, retained at Level 3 and in the deployment
view** — an implementation detail of the hypothesis service, documented at the level where
implementation details belong. Level 1 gets *sharper* as a result: the hosted AI provider is now the
only system EM Fusion reaches over a network, which is precisely the claim §10 and §12 make.

There is a legitimate route to removing it entirely, and it is a different decision: **cut the local
arm from scope**, which §10 already sanctions if its time-box expires. That makes the template
generator the sole fallback and the offline demo show template output. It changes §10, §12, Phase 8.5
and Phase 9 — it is a scope decision, not a diagram edit. See `thesis_notes.md` for the rationale;
this entry only explains what the distinction means.

---

## 15. I've created a Docker Compose file for frontend, backend and pipeline — route it through a Makefile

**Yes, and the Makefile is the easy half.** The compose file as first written could not start, for four
separate reasons, and three of them are the kind that stay invisible until a `make` target fails and the
Makefile gets blamed. Recording them here because each is a general Compose trap, not a typo.

| Problem | Symptom | Fix |
|---|---|---|
| `backend:`/`frontend:` keys indented at service level, `volumes:` nested inside `services:` | `docker compose config` refuses to parse; nothing runs | Service keys indent under the service name; top-level `volumes:` is a sibling of `services:` |
| `command: ["uv", "run", …]` | `exec: "uv": executable file not found` | The backend image installs with `pip` from `requirements.txt`; there is no `uv` in it. Call `uvicorn`/`python` directly |
| Every service carried a `profiles:` entry | `docker compose up` starts **nothing**, silently | Only genuinely optional services get a profile. `pipeline` (one-shot job) and `frontend-test` are profiled; `backend` and `frontend` are not |
| `ports: "8080:8080"` on the frontend | Container starts, connection refused | nginx listens on **80** inside the container. The mapping is `8080:80` — host port left, container port right |

### The two mismatches worth naming separately

**Service name vs. proxy target.** `nginx.conf` proxied to `http://api:8000/` while the service was
called `backend`. Compose's DNS resolves *service names*, so nginx returned 502 on every `/api/` call
while both containers reported healthy. A container being healthy says nothing about whether another
container can find it — the smoke test now checks the proxy hop (`/api/health` through the frontend)
precisely because the two endpoints can pass individually while the path between them is broken.

**Healthcheck vs. actual route.** The healthcheck polled `/api/v1/health`; the backend serves `/health`
(`backend/app/main.py`). A healthcheck that names a route the app does not expose fails forever, and
`depends_on: condition: service_healthy` then blocks the frontend indefinitely — presenting as a hang,
not an error. Healthchecks must be copied from the route table, never from memory.

### What did *not* transfer from the SignalWatch Makefile

The `ensure-artifacts` pattern — check for generated files, regenerate if missing — assumes a pipeline
whose outputs live on disk between runs. EM Fusion mostly does not work that way: the archived OpenSky
extract is **committed** to the repository rather than generated (§10, `em_fusion_v2.md` §3), and
synthetic observations are regenerated byte-identically from a seed under `scn-001`, so the seed is the
reproducibility artefact and a cached file alongside it would be redundant. The target is therefore kept
with `ARTIFACTS :=` empty, guarding nothing and saying so. Kept rather than deleted because the shape is
right for whatever the pipeline does eventually persist; add paths to the one variable and the guard
starts working. **Worth recording as a limitation:** an empty guard is a guard that has never been
exercised, so the first artefact added should be verified against a deliberately deleted file.

### One target fails today, by design

`make test-backend` exits 5 — "no tests collected" — because `backend/tests/` does not exist until the
first backend spec item lands. Special-casing exit 5 to pass was rejected: "no tests ran" and "tests
passed" are different states, and a suite that reports green while empty is exactly the failure mode the
spec → test → code workflow exists to prevent. See [[docs/implementation.md]] Phase 5.

---

## 16. Isn't `EXPOSE 8080` better than 80 for security? And should deps move to `pyproject.toml`, backend to 8000, health to `/api/v1/health`?

Four separate questions. Three are right; the first is right for a reason other than the one given.

### `EXPOSE 8080` "for security purposes" — right instinct, wrong lever

**`EXPOSE` does nothing for security.** It is documentation: a metadata line recording which port the
image *intends* to serve, read by `docker run -P` and by humans. It opens nothing, closes nothing, and
binds nothing. Changing `EXPOSE 80` to `EXPOSE 8080` while nginx still has `listen 80;` produces an
image whose metadata lies about it — strictly worse than the honest `EXPOSE 80`.

The real security property being reached for is **not running as root**, and *that* is what forces the
port choice:

| Port range | Who may bind it | Consequence |
|---|---|---|
| < 1024 (privileged) | root, or a process holding `CAP_NET_BIND_SERVICE` | nginx must start as root to bind 80 |
| ≥ 1024 (unprivileged) | any user | the container can run as a non-root uid throughout |

So the chain is: *want non-root* → *must listen ≥ 1024* → *8080* → `EXPOSE 8080` becomes the honest
metadata. The port number is a consequence of the decision, not the decision. Two ways to get there:

- **`nginxinc/nginx-unprivileged`** — the same nginx, pre-configured to listen on 8080 as uid 101, with
  the pid file and temp directories already relocated to writable paths. One base-image line.
- **Stock `nginx` + `user:` in compose** — also requires `listen 8080;`, plus `chown` on
  `/var/cache/nginx` and a moved `pid` directive, because the default paths are root-writable only.

The published host port is unaffected either way: `8080:80` and `8080:8080` both answer on
`localhost:8080`. Only the container-side number moves.

### Backend on 8000 everywhere

**Yes.** The backend was serving 8000 in Compose (`backend/Dockerfile`) while `vite.config.ts` proxied
`/api` to 8080, and `CLAUDE.md` documented `--port 8080` for host development. Three sources, two
numbers, no single correct one — the kind of drift that costs an afternoon the first time someone runs
the two modes on the same day. 8000 is the right survivor because it is what the image already
declares.

### Dependencies in `pyproject.toml`

**Yes for dependencies; partially for tool config.** One caveat and one trap.

The caveat: **flake8 cannot read `pyproject.toml`.** It is the one tool in this backend that refuses
TOML config, by longstanding maintainer decision, so `.flake8` survives any consolidation. `black`,
`isort`, `mypy` and `pytest` all read `pyproject.toml`, so only flake8 keeps a separate file — unless
it is replaced by `ruff`, which reads `pyproject.toml` and subsumes both flake8 and isort.

The trap is Docker layer caching. The current two-file split exists to serve it:

```dockerfile
COPY requirements.txt .          # this layer changes only when deps change
RUN pip install -r requirements.txt   # ...so this cached layer survives source edits
COPY . .                         # source changes invalidate only from here down
```

`pip install .` cannot reproduce that, because building the project requires the package source to be
present, so the dependency install and the source copy collapse into one layer and **every source edit
reinstalls every dependency**. Tools that separate the two steps (`uv sync --no-install-project`,
`pdm install --no-self`, or `pip-compile` back into a lockfile) restore it.

Independently of the file format, the current dependency list is **entirely unpinned** — `fastapi`,
`uvicorn`, `pydantic` with no version constraints. A fresh clone six months from now resolves different
versions than the ones any result was produced under, which sits badly against the reproducibility claim
made for the committed OpenSky extract (§10). A lockfile fixes that; the file format does not.

### `/api/v1/health` and an `app/api/` package

**Yes on both, and they interlock with the proxy layer.** Two things have to move at the same time.

Both proxies currently **strip** the `/api` prefix, on the assumption the backend serves bare paths:

| Layer | Current | If the backend owns `/api/v1` |
|---|---|---|
| nginx | `proxy_pass http://backend:8000/` — trailing slash strips `/api/` | drop the trailing slash so the path passes through intact |
| Vite | `rewrite: path.replace(/^\/api/, "")` | delete the rewrite |

A trailing slash on `proxy_pass` is the whole difference between forwarding `/api/v1/health` and
forwarding `/v1/health`. It is one character and it produces a 404 that looks like a routing bug in
FastAPI. The Compose healthcheck and `scripts/smoke-test.sh` follow the same path change.

The prefix also has documentation reach: `api-001`, `api-002`, `api-003`, `api-007` and `api-009` in
`spec.jsonl` all name bare paths, as do `em_fusion_v2.md` §5.8 and `implementation.md` Phase 5. All five
spec items are `passes: false`, so amending their descriptions is a legitimate spec edit rather than a
rewrite of proven work — but it is a spec edit, and needs agreeing before the tests are written.

On structure, prefer **one router module per resource** over a single `routes.py`:

```
app/api/v1/__init__.py   # api_router = APIRouter(prefix="/api/v1"); include_router each module
app/api/v1/health.py     # tags=["system"]
app/api/v1/operational_picture.py
```

A single `routes.py` is the file every future feature edits simultaneously, which is precisely the merge
conflict the worktree-per-spec-item workflow exists to avoid. `tags=` is worth setting from the first
route: it groups the generated OpenAPI page, and retro-fitting tags means touching every decorator.

### A note on `lifespan`

Adding `lifespan=lifespan` to the `FastAPI(...)` call without defining `lifespan` raises `NameError` at
**import** time, not request time, so `uvicorn --reload` crash-loops and the container reports unhealthy
while the source looks fine in the editor. Worth knowing the signature: `lifespan` is an
`@asynccontextmanager` taking the app and yielding once — code before the `yield` runs at startup, code
after it at shutdown. It replaces the deprecated `@app.on_event("startup")` pair, and is where the
database engine and replay loop will attach.

---

## 17. For the sake of `pyproject.toml`, let's use ruff instead of flake8 and isort

**Done — and it retires the caveat in §16.** That entry said flake8 could not read `pyproject.toml`
and so `.flake8` would survive any consolidation. That is still true *of flake8*, but flake8 is no
longer here: ruff implements the same checks, reads `pyproject.toml`, and subsumes isort as well.
`.flake8` is deleted, and the backend now has **no tool configuration outside `pyproject.toml`** —
which was the point of the consolidation and was previously 90% achieved.

| Before | After |
|---|---|
| `flake8` (config in `.flake8`) | `ruff check` (config in `[tool.ruff.lint]`) |
| `isort` (config in `[tool.isort]`) | ruff rule set `I` (config in `[tool.ruff.lint.isort]`) |
| `black` (config in `[tool.black]`) | unchanged — ruff's formatter was not adopted |

### Rule mapping, and one genuine gap

`select = ["E", "F", "W", "I"]` reproduces flake8's defaults: `F` is pyflakes, `E`/`W` are
pycodestyle, `I` is isort. Two entries in the old `.flake8` needed thought rather than translation:

- **`E203`** (whitespace before punctuation) is still ignored. It disagrees with how black formats
  slices, so it would fail on code black had just produced.
- **`W503`** (line break before binary operator) has no ruff equivalent, because ruff does not
  implement that check at all. It needs no ignore entry — there is nothing to ignore.

The gap worth knowing about: **ruff's whitespace rules are preview-only.** `E1`, `E2`, `E3` — including
`E225`, missing whitespace around an operator — do nothing under a stable ruff unless `preview = true`
is set. Selecting them explicitly produces a warning that the selection has no effect, verified here
rather than assumed. So `x=1` passes `make lint` where flake8 would have rejected it.

This is acceptable, but for a specific reason rather than by dismissal: black already normalises every
one of those cases, and `make check` runs `format` before `lint`, so formatted code cannot reach the
linter in that state. Preview rules were not enabled because preview is explicitly unstable and would
opt the project into every other in-development rule for the selected sets at the same time. The
division of labour is the standard one — **the formatter owns whitespace, the linter owns everything
else** — and the residual risk is limited to running `make lint` in isolation on unformatted code.

### Why keep black at all

Ruff ships a formatter that is a near drop-in for black, so the obvious follow-on question is whether
black should go too. It was kept because it is not what was asked for, and because the two changes have
different risk profiles: swapping the *linter* leaves every source file byte-identical, as the 7
files-unchanged result from black after the swap confirms, whereas swapping the *formatter* rewrites
files and puts a reformatting diff through the repository. That is a separate decision with a separate
diff, and it should be made on its own rather than smuggled in behind a linter change.

---

## 18. Why can't we just set `platform: linux/amd64`?

**You can, and it is what the project now does.** The question came up because `postgis/postgis`
publishes **no arm64 image at any tag** — 15, 16, 17, alpine or Debian — so on Apple Silicon the pull
fails outright with `no matching manifest for linux/arm64/v8`. There are exactly two ways past that,
and the initial recommendation of a multi-arch community rebuild (`imresamu/postgis`) over-weighted
performance against provenance.

| Option | Gets you | Costs you |
|---|---|---|
| `platform: linux/amd64` on the official image | The canonical image, byte-for-byte what upstream publishes | Runs emulated; ~2.5× slower on a spatial query here |
| A multi-arch rebuild (`imresamu`, `baosystems`) | Native arm64 speed | A third-party build, which is a weaker provenance claim in a thesis |

Emulation is not a fallback mode with different semantics — the container runs a real x86-64 Postgres,
`uname -m` inside it reports `x86_64`, and PostGIS behaves identically. Docker Desktop uses Rosetta 2
if it is enabled under Settings → General, and QEMU otherwise; the QEMU path is substantially slower
and historically more fragile, so the setting is worth checking rather than assuming.

### The measured cost

The same query on the same host, once each, warm:

```sql
SELECT count(*) FROM (
  SELECT ST_MakePoint(g*0.001, g*0.001)::geography AS p FROM generate_series(1,200000) g
) s WHERE ST_DWithin(p, ST_MakePoint(50,50)::geography, 100000);
```

| Image | Reported arch | Time |
|---|---|---|
| `postgis/postgis:15-3.5-alpine`, `platform: linux/amd64` | `x86_64` | **3231 ms** |
| `imresamu/postgis:15-3.5-alpine`, native | `aarch64` | **1314 ms** |

Roughly 2.5× — indicative, not a benchmark: one run each, no cache control, and the containers differ
in volume configuration. It is recorded because **detection latency is a reported evaluation metric**,
so any latency figure taken against this database inherits the emulation factor. That belongs in the
conditions attached to the measurement, not discovered afterwards. Note that the metric is defined in
*simulated* scenario time rather than wall clock, which insulates the headline detection-latency
numbers; what emulation actually threatens is any wall-clock claim about query or pipeline throughput.

### Other corrections to the stack as first written

**PGDATA was bind-mounted to `./data/postgres`.** Changed to a named volume, for three reasons that
compound: `./data` is already bind-mounted into the backend and pipeline as `/data` for generated
artefacts, so the database's internal files would sit inside the directory `make generate` writes to;
`data/` is not gitignored, so root-owned Postgres files would appear in `git status` and could be
committed; and `make clean` (`down --volumes`) would not have dropped a bind mount, so "clean" would
have silently left a stale database behind. A named volume fixes all three, and `make db-reset` now
exists for the deliberate wipe.

**The healthcheck named no database.** `pg_isready -U postgres` connects to a database named after the
user, which is not `em_fusion`. It now names the database it is actually gating on.

**The PostGIS extension is created by the image's init scripts on first start only**, against an empty
data directory. If that step is ever skipped — a pre-existing volume, a changed `POSTGRES_DB` — the
database still accepts connections and still reports healthy, and the failure appears much later as
`type "geography" does not exist`. `scripts/smoke-test.sh` now asserts `postgis_version()` for this
reason, and `make db-reset` was verified to re-run the initialisation.

---

## 19. SQLAlchemy is an ORM that lets us manipulate data with Python instead of SQL, psycopg is the driver handling network communication, and the engine configures SQLAlchemy to use psycopg?

**The psycopg half is right, the SQLAlchemy half is half right, and the engine does more than wire the
two together.** Taking them in order, because the layering is what makes the rest of `db-005` make
sense.

### The stack, top to bottom

```
repository function            your code — the only place SQL and spatial logic may live (db-003)
  ↓
Session                        ORM: identity map, unit of work, transaction scope
  ↓
Engine                         dialect + connection pool + execution entry point
  ↓
psycopg (DBAPI)                wire protocol, type adaptation, TLS, authentication
  ↓
TCP socket → PostgreSQL/PostGIS
```

Each layer talks only to its neighbours. That is why swapping the driver is a URL change, and why the
repository boundary in `db-003` can hold: everything above `Session` is project code, everything below
`Engine` is somebody else's problem.

### psycopg: yes, that is what a driver is

psycopg 3 implements PostgreSQL's **frontend/backend wire protocol** — the byte-level conversation a
client has with the server. Concretely it owns the connection handshake, authentication (SCRAM-SHA-256
and friends), TLS negotiation via `sslmode`, sending statements, streaming result rows back, `COPY`,
`LISTEN`/`NOTIFY`, and transaction control at the protocol level.

It also does one job that is easy to overlook and matters more than the networking: **type adaptation**
in both directions — a Python `datetime` to a Postgres `timestamptz`, a `dict` to `jsonb`, a returned
`numeric` to `Decimal`. And it is where **parameter binding** actually happens. Parameters are sent to
the server separately from the statement text, so the server never parses user data as SQL. That, not
escaping, is what makes parameterised queries injection-proof. psycopg is a PEP 249 (DBAPI 2.0)
implementation, which is the interface SQLAlchemy programs against — hence "driver" and "DBAPI" being
interchangeable in SQLAlchemy's documentation.

### SQLAlchemy: two libraries, and it does not replace SQL

The correction worth making is that SQLAlchemy is **two layers, and only the upper one is an ORM**:

| Layer | What it gives you | Used here for |
|---|---|---|
| **Core** | SQL expression language, schema/metadata, connection pooling, dialects. Composes SQL in Python; no classes, no objects-as-rows. | The PostGIS spatial query in `db-004`, and anything set-based |
| **ORM** | Declarative classes mapped to tables, identity map, unit of work, relationship loading | The CRUD-shaped tables: hypotheses, analyst feedback, scenario runs |

"Manipulate data with Python instead of SQL" is the framing that produces slow queries, because it
suggests SQL has been abstracted away. It has not — it has been made **composable and type-checked**.
`select(Observation).where(Observation.icao24 == x)` is not an alternative to SQL, it is a SQL `SELECT`
built out of Python objects, and you still have to know what statement it will emit, what it will join,
and how many round trips it will cost. The ORM's real contributions are narrower and more valuable than
"no SQL": it tracks which loaded objects changed and emits the right `UPDATE`s at flush (unit of work),
and it guarantees one Python object per database row per session (identity map).

**This project meets the limit of that abstraction early.** `db-004` requires a genuine PostGIS
predicate — track discontinuities within N km of an anomaly zone — and the ORM has no notion of
`ST_DWithin`. SQLAlchemy can *call* it through `func.ST_DWithin(...)`, but knowing that a column holds a
geometry, indexing it with GiST, and parsing WKB results needs **GeoAlchemy2**, a separate library that
adds PostGIS types on top of SQLAlchemy. The spatial query — the single feature that justifies choosing
PostGIS at all — is the part the ORM helps with least. That is an argument for keeping it in a
repository function written close to the SQL, which is what `db-003` mandates anyway.

### The Engine: the pool is the point

Configuring the driver is one of three jobs, and the least interesting:

1. **Dialect selection.** `postgresql+psycopg://` is read as *dialect* `postgresql` plus *DBAPI*
   `psycopg`. The dialect knows PostgreSQL's SQL flavour; the DBAPI knows how to talk to it.
2. **Connection pooling.** The Engine holds a pool of already-open connections and lends them out.
   Opening a PostgreSQL connection is expensive — TCP handshake, TLS, authentication, and a new backend
   *process* forked server-side. Pooling amortises that across requests.
3. **Execution entry point**, and the source every `Session` borrows its connection from.

Point 2 is why `db-005` insists on exactly one Engine per process. An Engine constructed inside a
request handler creates a *new pool* on every request, so nothing is ever reused, connections
accumulate, and Postgres eventually refuses new ones at `max_connections`. The symptom appears under
load, long after the code looks fine — which is why it is written as a failure case rather than left to
review.

A related property the spec depends on: **`create_engine()` does not connect.** It parses the URL and
builds the pool lazily; the first real connection happens at first use. That is what allows unit tests
for `db-005` to assert configuration and cleanup behaviour with no database running, and it is why live
connectivity is checked in `scripts/smoke-test.sh` instead.

### Session versus Engine versus Connection

Three things that are easy to conflate:

| | Lifetime | Holds |
|---|---|---|
| **Engine** | One per process | The pool and the dialect |
| **Connection** | One transaction's worth | A real socket, borrowed from the pool and returned |
| **Session** | One per request, per `db-005` | The ORM's work in progress: pending changes, identity map, and a borrowed Connection |

A `Session` is not a connection — it acquires one when it first needs it and releases it on close. This
is why "one session per request, rolled back on exception, closed on completion" is the whole of the
dependency's contract: a session left open holds a pooled connection hostage, and a request that raises
without rollback returns a connection to the pool with an aborted transaction still on it, so the *next*
request to borrow it fails for no visible reason.

### Could psycopg be used without SQLAlchemy?

**Yes**, and it is worth knowing the option exists. psycopg alone executes any statement this project
needs, and `db-003` already confines SQL to a repository layer, which is where an ORM's benefits are
thinnest. SQLAlchemy is retained because it is named in the target stack (`em_fusion_v2.md` §10) and
because the non-spatial tables are exactly the CRUD shape the unit of work handles well. The honest
statement for the write-up is that the ORM earns its place on the hypothesis, feedback, and scenario-run
tables and earns much less on the spatial query — not that it was needed throughout.

---

## 20. Is this a good time to get the OpenSky data in and generate the synthetic RF data, or is there something else we should do first?

**Half right — those are two tasks, not one, and they have opposite answers.** The question treats data
acquisition and data generation as a single "get the data in" step. They sit in different tracks, have
different blockers, and separating them is the useful part of the answer.

### The two halves

| | OpenSky acquisition | Synthetic RF generation |
|---|---|---|
| Where it sits | Track 0, non-code, marked *start now* | Phase 7 (`adp-002`), after the DAL |
| Blocked by | Nothing | `db-005`, `db-001`, `dal-001/002/003`, `scn-005`, `scn-001` |
| Cost of delay | Rises — a wrong bounding box invalidates the extract, the manifest, the PMTiles archive, and any run measured against them | Flat |
| Verdict | Do it now | Wait |

### Why the acquisition is genuinely urgent

The bounding box is an input to two artefacts, not one: the OpenSky extract *and* the Phase 4 PMTiles
basemap cut, which covers the same box. The coverage acceptance check can force the box to move. Every
week that check is deferred, more work is pinned to a box that has not been validated.

### The trap in the acceptance check as written

`docs/implementation.md` phrases the check as *"execute `Normal baseline` against the extract and confirm
no dropouts appear."* But `Normal baseline` is `scn-002` and "dropouts appear" needs the Phase 8 detectors.
Read literally, the check that validates the bounding box cannot run until the point at which a wrong box
is most expensive to fix.

The resolution is to split it into a cheap proxy now and the specified check later:

```text
now (pandas, no detector):   group by icao24, diff consecutive `time` values,
                             compare the gap distribution against the 10s cadence
Phase 8 (as specified):      run Normal baseline, confirm zero detections
```

The proxy answers the only question that has to be answered early — *is this region densely enough
covered that genuine gaps will not swamp injected ones* — without waiting for the detection layer.

### Why the generator has to wait for the DAL

This is the load-bearing blocker, and the reason is not sequencing tidiness. Adapters emit *into* the DAL;
the canonical observation model (`dal-001`) is their output target. Build `adp-001` first and the canonical
model gets shaped around whatever fields OpenSky happens to supply.

`adp-003` — the third adapter — exists specifically to measure whether a new source lands without modifying
the canonical model or any detection rule. That measurement is the RQ1 extensibility evidence. Building the
first adapter before the model it is supposed to be independent of pre-contaminates the result, and no test
catches it: the suite passes either way, and the number reported at the end is simply wrong in a direction
that flatters the project. Same class of hazard as `api-009` — a structural assertion, because there is no
after-the-fact check.

The two secondary blockers are more ordinary but still real: `dal-002` requires quarantine **rows**, and
`scn-002` requires ground truth on `scenario_runs`, so `db-001` has to exist or there is nowhere to put
either; and `scn-005` fixes the sensor/channel grid as configuration *before* the generator reads it.

### Gap found while answering

There is **no spec item covering production of the extract**. `adp-001` opens with "the archived,
bounding-box-filtered OpenSky extract, stored as a committed Parquet file with its manifest" — it consumes
the artefact and assumes it exists. The filter script, the manifest, the checksum of the original, and the
continuity check are an unspecced capability, and per the spec-first rule they need an item of their own
before any of it is written.

### Resulting order

Track 0, in parallel with code: extract spec → download, filter, commit Parquet + manifest → record licence
and attribution at download time → continuity proxy check → fill the two open placeholders in
`thesis_notes.md` (the bounding box and hour used; the OpenSky licence and citation terms).

Code: `api-002`/`api-003` → `db-005` → `db-001` → `dal-001/002/003` → `scn-005` → `scn-001`/`scn-002` →
`adp-001` → `adp-002`.

*Worth recording as a limitation:* the licence and attribution terms are the one part of this that is
genuinely unrecoverable later. A Parquet file can be re-filtered from a re-download; the terms as published
on the day of download cannot be reconstructed if the page changes. Same rule as the ODbL note for the
basemap.

---

## 21. Let me get the real file first — this will make writing the test easier. What do you think, and how do I get the snapshot?

**Agreed, and for a stronger reason than convenience.** The fixture has to reproduce the raw file's
quirks, and a fixture written blind invents its own. The real header, read off the bucket without
downloading the file:

```
time,icao24,lat,lon,velocity,heading,vertrate,callsign,onground,alert,spi,
squawk,baroaltitude,geoaltitude,lastposupdate,lastcontact
1656331200,4d22ec,51.090475825940146,7.54730224609375,194.26375447899966,
135.64374571417537,13.329920000000001,CXI27NM ,False,False,False,2556,
5753.1,5951.22,1656331198.94,1656331200.0
```

Three things a blind fixture would have missed: `callsign` is **space-padded to 8 characters**;
booleans serialise Python-style as `False`/`True`, not `0`/`1` or `false`/`true`; and `lastposupdate`
carries millisecond precision while `lastcontact` is whole seconds. `adp-004`'s determinism constraint
would have been verified against a file that does not resemble the input.

### Which dataset — a conflation in our own docs

`docs/em_fusion_v2.md` section 5 and `docs/thesis_notes.md` describe the source as "published tables as
of 2026-03-01: every Monday's complete state vectors at 10-second intervals, one file per hour,
CSV/Avro/JSON". That single sentence merges **two different entries** on
`https://opensky-network.org/data/scientific`:

| | Dataset 1 | Dataset 11 |
|---|---|---|
| Name | Weekly 24 Hours of State Vector Data | Complete Trino Tables Snapshot |
| Coverage | Mondays, 2017-06-05 to 2022-06-27 (259 dates) | Tables as of 2026-03-01 |
| Granularity | 10-second state vectors, one file per hour | Full table dump |
| Formats | CSV, Avro, JSON | Trino table export |
| Right one here | **Yes** | No |

The Monday/hourly/three-format description belongs to dataset 1; only the March 2026 date belongs to
dataset 11. **The corpus is from 2022, not 2026** — a claim an examiner can check, so both documents
need correcting rather than leaving the date to be quietly read as recency.

### Where it actually lives

The `datasets/` browser on the website is a JavaScript S3 bucket explorer over a public,
anonymously-readable bucket. The bucket is the real address:

```
https://s3.opensky-network.org/data-samples/states/YYYY-MM-DD/HH/states_YYYY-MM-DD-HH.csv.tar
```

`HH` is `00`-`23`; dates are restricted to the 259 Mondays. **No account or login is required** — this
was verified with unauthenticated requests. Each hourly tar wraps exactly one member, a `.csv.gz`, and
runs 120-180 MB; a full day is roughly 3.9 GB and is not needed, since one hour at 10-second intervals
already gives 360 samples per aircraft.

### The licence contradicts FR-110 and adp-004

Found while confirming the citation. The OpenSky Data License Agreement, section 3(iii):

> You will not distribute, disclose, transfer or otherwise make available the data set(s) to any person
> other than those employed by your institute who are assisting or collaborating with You.

`FR-110` and `adp-004` both require the filtered extract to be **committed to the repository**, so that a
fresh clone reproduces the pipeline with no download step. Committing it is redistribution — plainly so
for a public repository, and arguably so for private-with-examiner-access, which is still an open Track 0
item. Section 4(ii) points the same way: copies are to be expunged on completion of the research, with
only a narrow carve-out for reproducibility obligations.

The wrong assumption was that a bounding-box-filtered subset is a derived work rather than the data set,
and therefore freely committable. The agreement draws no such line, and a filtered extract of state
vectors is still state vectors.

Two further points from the same terms:

- **Commercial and contractor use.** "Any use by a for-profit or commercial entity — including government
  and military contractors — requires a written license from OpenSky Network, regardless of purpose." A
  university dissertation falls under the non-profit research licence, but this belongs in the employer
  clearance conversation alongside the EW/GNSS review question, not least because the project's subject
  matter is exactly what that clause contemplates.
- **Citation, now verified** rather than assumed. Section 4(i) requires either `The OpenSky Network,
  http://www.opensky-network.org` or the paper: Schäfer, Strohmeier, Lenders, Martinovic and Wilhelm,
  *Bringing up OpenSky: A large-scale ADS-B sensor network for research*, ACM/IEEE IPSN, April 2014. The
  conventional citation was correct; it is now checked against the current terms as the thesis note asked.

**Resolved the same day:** the extract is **not** committed. `data/opensky/` is gitignored; what the
repository carries is `manifest.json`, `coverage.json`, and a fetch-and-filter script that re-downloads
against the recorded SHA-256 and re-filters deterministically. A fresh clone reproduces the corpus in one
command once the reader accepts the licence themselves. FR-110, `adp-004`, and the Track 0 checklist item
were amended accordingly, and the reversal is written up in `docs/thesis_notes.md`.

*Worth recording as a limitation:* the reproducibility story for the corpus is now weaker than for the
synthetic half of the pipeline. Scenario runs regenerate from type, parameters and seed indefinitely; the
aviation backdrop can only be reproduced by a reader who accepts the same licence and re-downloads
against the recorded checksum. That asymmetry is a property of using real third-party data at all, and is
better stated than hidden behind a committed file that should not have been committed.

---

## 22. What did reading the actual licence file change?

**Two things, one of which reopens a Track 0 item that had been marked closed.** The licence was read
properly only after the file was downloaded, because `LICENSE.txt` ships *inside* the data tarball —
which is itself the first correction: the tar holds **three** members, not one.

```
states_2022-06-27-12.csv.gz   179733529
LICENSE.txt                       14973   (dated 2017-08-24)
README.txt                         7074
```

The shipped `LICENSE.txt` is byte-identical to the copy in the bucket (`d4ea34f0…`), and there are **no
Supplemental provisions** for state vectors, so the general agreement governs in full.

### Finding 1: aircraft identifiers must be de-identified

Section 3(i):

> For any publication or other disclosure, You will anonymize or de-identify personally-identifiable
> information, aircraft identifiers, sensor locations and other data identified in Supplemental
> provisions (if any).

`icao24` and `callsign` are aircraft identifiers. The `AircraftTrack` contract carries `id` and `name`,
which become exactly those two fields once `adp-001` replays real data. Three surfaces are affected:

| Surface | Why it counts |
|---|---|
| Thesis screenshots and figures | "publication" in the plain sense |
| Evidence bundles sent to the hosted AI provider | "other disclosure" — a third party outside the institute |
| The third adapter (`adp-003`) | would inherit the problem silently |

**The wrong assumption, which had been written into the Track 0 checklist**, was that data being openly
*accessible* makes it freely *disclosable*. It does not. The egress item had been closed on the reasoning
that bundle content is "synthetic or replayed open data, so this is expected to be a non-issue"; open
access is a statement about how the data is obtained, not about what may be done with it afterwards. The
item is reopened for the employer dimension, with the licence dimension now answered rather than assumed.

**Resolution: `dal-004`**, pseudonymisation at the DAL. A deterministic seeded mapping replaces `icao24`
and `callsign` before persistence, and the source values are discarded rather than kept beside the
pseudonym. Placing it at the DAL rather than in the adapter follows the argument `dal-003` already makes
for provenance — attached where all sources converge, so a new adapter cannot forget it.

Nothing downstream loses anything, because nothing downstream needs the real identifier:

| Consumer | Needs | Satisfied by a pseudonym? |
|---|---|---|
| Track continuity detectors | stable identity across samples | Yes — same aircraft, same pseudonym |
| Spatial clustering | position only | Not affected |
| Analyst UI | a distinguishable label | Yes |
| Evidence bundles / AI layer | a referent to cite | Yes |

The real identifiers stay in the local extract, which the licence permits — the restriction is on
publication and disclosure, not on local use.

**Where the seed lives — decided.** The pseudonym seed is held separately from the scenario seed, as fixed
configuration recorded in the corpus manifest, and is never drawn per run. The archived corpus is a single
replayed hour, so the same airframes recur in every run of a batch; deriving the pseudonym from the
scenario seed would relabel each aircraft in each of `scn-003`'s twenty-five runs, and would have broken
`scn-001`, which requires two runs sharing type, parameters and seed to emit byte-identical output. Making
the mapping a property of the corpus rather than of a run resolves both at once.

*The trap this avoids:* retrofitting is not a code change. Once a campaign has run, every stored
observation, evidence bundle, and persisted hypothesis carries a real identifier, and removing them means
migrating data and regenerating results. Building it alongside `dal-001`, before `adp-001` replays a
single real row, costs nothing.

### Finding 2: the shipped licence is not the operative licence

The `LICENSE.txt` inside the tarball is dated 2017-08-24. The terms published at
`opensky-network.org/about/terms-of-use`, retrieved 2026-08-13, differ materially — and the shipped file
is the **more permissive** of the two:

| | Shipped, 2017 | Published, 2026 |
|---|---|---|
| Permitted purposes | non-profit research, non-profit education, commercial internal testing and evaluation, government purposes | non-profit research and non-profit education only |
| Commercial entities | not addressed | written licence required |
| Government and military contractors | covered by "government purposes" | explicitly require a written licence |
| Operational REST API use | not addressed | written licence required regardless of non-profit status |

Section 2(iii) resolves which applies: modifications become effective fifteen days after notification and
continued use constitutes assent, so **the currently published terms govern, not the copy in the
tarball**. A reader who consulted only the shipped file — the natural thing to do, since it arrives with
the data — would reach a more permissive conclusion than the terms actually allow.

The manifest therefore records both: the shipped file's SHA-256 and date, and the published terms' URL
and retrieval date, with a note on which is operative. This is a stronger version of the rule that terms
must be captured at download time; here they had already drifted from the artefact before download.

*Worth recording as a limitation:* the licence is revocable and modifiable at OpenSky's sole discretion
(section 1), so a claim that this corpus is redistributable or reusable under fixed terms cannot be made
at all. Recording the retrieval date is what makes the compliance claim checkable — it fixes *which*
terms were complied with, which is the most that can be said about a licence that can change underneath
the work.

---

## 23. Since we can't commit the extract, is Parquet still necessary? I guess it is because it still compresses the data. And do we extract the data from its tar/gz state so it's readable, or keep it as is?

**Parquet yes, but compression is the wrong reason — and the tar should stay sealed.** Both answers were
checked against the downloaded corpus rather than reasoned from first principles, and the measurements
changed one of them.

### Parquet: the surviving reason is typing, not size

The original rationale, as recorded in `thesis_notes.md`, gave two reasons: Parquet is typed, *and* it
compresses well enough that a filtered hour could be version-controlled. **The second reason no longer
exists**, since the licence forbids committing the extract at all. Compression on its own does not
justify a format here — the source is already gzipped, and at 255,145 rows the extract is small in any
encoding.

The typing reason, however, is far stronger than it looks, and the corpus proves it:

| Measurement over the downloaded hour | |
|---|---|
| Total rows | 2,858,582 |
| Distinct `icao24` | 14,334 |
| `icao24` values that are all digits | ~10% |
| **All-digit `icao24` beginning with a zero** | **14,781 rows** |

`icao24` is a 24-bit transponder address written as six hexadecimal digits — a **string**, and the field
every track-continuity rule groups by. Roughly a tenth of values happen to contain no letters. Where such
a value also begins with `0`, any read that infers the column as an integer destroys it:

```
'004321'  --inferred as int64-->  4321      leading zeros gone, silently
```

This is not hypothetical: type inference over a *filtered subset* containing no letter-bearing values, or
a chunked reader inferring per chunk rather than per file, both produce it. The result is corruption of
the primary key for track continuity, with no error raised and no test failing unless one is written to
look for exactly this.

CSV cannot carry a dtype, so the schema would have to live in code and be kept in step with the file by
discipline. Parquet carries the schema inside the artefact, which also makes `adp-004`'s constraint —
"identical row content **and column schema**" — checkable rather than aspirational.

**Consequent dependency decision:** `pyarrow` only. Neither Pandas nor pyarrow was previously a
dependency, despite a note in `thesis_notes.md` claiming Pandas already was; that claim was wrong and has
been corrected. The filter pass runs on the standard library's `csv` module, so Pandas buys nothing here.

### The tar stays sealed

Reading straight through the archive was tested on the real file — `tarfile` → `extractfile` → `gzip` →
`csv`, no temporary files and no Pandas:

```
2,858,582 rows streamed in 13.6 s
```

| | Size |
|---|---|
| Tar as downloaded | 0.18 GB |
| Same data decompressed | 0.49 GB |

Four reasons not to unpack it:

1. **One artefact, one checksum.** The manifest records the SHA-256 of the `.tar`, which is the published
   object. Unpack it and the thing on disk is no longer the thing that was verified, so re-verification
   would require re-downloading.
2. **`LICENSE.txt` is inside the tar.** Unpacking separates the obligations from the data they attach to,
   which is the exact failure mode §3(iii) makes costly.
3. 2.7× the disk for a file that is streamed exactly once.
4. gzip is not seekable, but nothing needs to seek — the filter is a single sequential pass.

The already-extracted `.csv.gz` is therefore redundant and should be deleted.

### A third finding: the quarantine path had no real input

| | |
|---|---|
| Rows with a null `lat` or `lon` | 220,908 (7.73%) |

A bounding-box test cannot be applied to a null coordinate, so a pure spatial filter excludes **every one
of them**. That quietly defeats `adp-001`'s stated failure case — "a row with a null lat or lon must
quarantine rather than persist a track observation at a default coordinate" — because no such row would
ever reach the DAL. `dal-002`'s quarantine path would be exercised by fixtures only, and **AC-02 would
never be demonstrated on real data**.

**Decided: retain a bounded sample of null-position rows in the extract.** `adp-004` now takes the first
N such rows in file order, with N as configuration and both the value and the resulting count recorded in
the manifest. File order rather than a seeded sample, so the retention needs no seed of its own and stays
deterministic for a given raw file.

The property that makes this safe is worth stating: a null-position row **can only ever reach quarantine**
— it cannot become a canonical observation by definition, since `dal-001` requires a location. So it adds
real-data evidence for `AC-02` with no possibility of contaminating the operational picture or any metric.
The coverage report computes its gap distribution over positioned rows only, since a row with no position
is not a coverage gap.

### Incidental, but useful for the bounding box

The candidate box 47–55°N, 3–15°E yields 255,145 rows, 1,580 distinct aircraft, and **360 distinct
timestamps — exactly 3600/10**, so the hour is complete with no globally missing time steps. That is a
necessary condition for the coverage check, not a sufficient one: per-aircraft continuity is the question
the coverage report actually answers, and it remains open until the box is fixed.

---

## 24. For my understanding, adp-005 is testing the ability to download the OpenSky data with the same checksum and licence from the committed manifest before filtering to the bounding box?

**Half right.** The checksum half is exactly as described. The licence half works by a different
mechanism, and the difference matters more than it looks.

### The checksum: yes, and the ordering is the spec

`adp-005` reads `original_sha256` out of the committed `manifest.json`, downloads the tarball to a
temporary path, hashes what arrived, and only then moves it into `data/opensky/raw/` and hands it to
the `adp-004` filter.

Verify **before** filter, not after. Filtering first and checking later still produces an extract,
and that extract sits on disk beside a manifest asserting a provenance that does not hold — the
artefact is then unattributable to the recorded source, which is the failure the spec names. The
temp-then-move step exists for the neighbouring failure: an interrupted download left at the
destination path is a file a later run would accept as complete and filter into a silently truncated
extract, with no error anywhere.

A run that finds a local file already matching the recorded checksum skips the download entirely
rather than re-fetching roughly 180 MB.

### The licence: nothing is compared

The wrong assumption worth naming: that the licence is *verified against* the manifest the way the
checksum is. It is not. The two fields serve different purposes.

| | Checksum | Licence |
|---|---|---|
| Where it lives | `manifest.json`, `original_sha256` | `manifest.json`, `licence` and `attribution` |
| What the fetcher does with it | Compares it against the bytes it downloaded | Displays it, and refuses to proceed without an explicit acceptance act |
| What failure looks like | Mismatch → abort, leave no extract behind | Acceptance not given → no download at all |
| Is it a check? | Yes | No — it is a gate on the operator, not on the data |

The licence entry is *provenance*: the name, which version governs (published, per §2(iii)), the
SHA-256 of the `LICENSE.txt` that ships inside the tarball, and the §4(i) attribution string. Nothing
downstream can compare a downloaded file against it, because a licence is not a property of the
bytes.

Why the acceptance gate exists at all is the same reason the extract is not committed. Under DLA
§3(iii) the data cannot be made available outside the institute, so whoever wants the corpus fetches
it themselves — and fetching it is the moment they take on the terms. Handing someone a repository
that downloads 180 MB of licensed data without their say-so relocates that acceptance to whoever
wrote the script. A flag defaulting to true would be the same bypass with an extra step in front of
it. See [thesis_notes.md](thesis_notes.md), "Reversal: the corpus is not committed to the repository
after all".

### Two things adp-005 is beyond "download"

**The socket boundary.** It is the only module in the corpus tooling permitted to open a socket. That
is not a stylistic preference — it is what keeps `extract.py` offline-testable, and `adp-004` already
carries a test that monkeypatches `socket.socket` to prove the filter never reaches for one. Put the
download inside the filter and that test becomes unwritable.

**The one command.** Fresh clone to `opensky_extract.parquet`, `manifest.json` and `coverage.json` in
a single invocation. The fetch and the filter are separate modules but not separate chores.

### One trap worth recording

Every `adp-005` test mocks the transport; none performs a real download. Beyond speed and
determinism, a test suite that really fetches turns continuous integration into an unattended
acceptor of someone else's licence terms — the machine agreeing on the operator's behalf, which is
precisely the thing the acceptance gate was built to prevent. The spec names this as its fourth
failure case rather than leaving it to reviewer discipline.

---

## 25. Let's work on choosing the bounding box next, per the handoff

**The coverage report did not choose it, and that is the finding.** The handoff said to pick the box
"by running the coverage report over candidates and reading the gap distribution". That plan assumed
the candidates would differ in coverage quality. They do not.

### What was expected, and what happened

Eight candidate regions were scored against the full 2,858,582-row hour. Every one returned a p50, p90
*and* p99 gap of exactly 10 seconds — the published cadence — and a clean-cadence fraction of 0.999 or
better:

| box | rows | aircraft | p99 gap | clean fraction |
|---|---|---|---|---|
| central-europe | 255,145 | 1,580 | 10 s | 0.999 |
| benelux-ruhr | 84,355 | 642 | 10 s | 1.000 |
| uk-southeast | 98,614 | 701 | 10 s | 1.000 |
| france | 194,682 | 1,232 | 10 s | 1.000 |
| iberia | 141,955 | 787 | 10 s | 1.000 |
| alps-adriatic | 181,038 | 1,106 | 10 s | 1.000 |
| us-northeast | 196,010 | 1,224 | 10 s | 0.999 |

A metric that returns the same value for every option cannot rank them. OpenSky's 2022 coverage over
populated airspace is simply complete at this resolution, which is good news for the project and
useless for the decision.

### The measurement had to be corrected before it could be trusted

The same naive report showed maximum gaps of up to **3,140 seconds in a 3,600-second file**. Read at
face value that is near-total coverage collapse. It is nothing of the sort, and two distinct confounds
produce it:

| Confound | What it actually is | Fix |
|---|---|---|
| **Boundary crossing** | The aircraft flew out of the box and came back. A property of drawing a finite box, not of the sensor network. | Count a gap only if both endpoints are ≥ 0.5° inside the edge |
| **Ground movement** | A parked airframe transmits differently from an airborne one. Its quiet period is not a dropout. | Count a gap only if `onground` is false on both sides |

With both applied, `central-europe` drops from a 2,970 s maximum to **29 gaps above cadence out of
170,673** — 0.02%. The corrected and uncorrected numbers do not merely differ in precision; they
support opposite conclusions. Worth recording as a trap: an uncorrected spatial-temporal gap metric
points confidently in the wrong direction.

### What actually decided it

The criterion came from what the scenarios need rather than from data quality. Types 2 and 4 inject
events confined to roughly a 20 km area, and the harness runs 20–30 randomised runs across five types,
so **100–150 event placements** are needed. Binning airborne samples into ~20 km cells and counting
cells with ≥ 5 distinct aircraft in a 15-minute window gives the number of *usable event sites* — and
that discriminates, from 132 to 556 across the shortlist.

Chosen: **49–54°N, 3–11°E**, with 263 sites against a ceiling of 150. The tightest candidate (132
sites) was rejected because randomised runs would exhaust the pool and start reusing locations,
correlating runs the evaluation treats as independent.

### The mistake the metrics would never have caught

An earlier shortlisted box started at **5°E**, which puts Schiphol (4.76°E) and Brussels (4.48°E)
*outside* the corpus. Nothing in its statistics looked wrong — it simply read as a slightly quieter
region. Moving the western edge to 3°E added 306 aircraft and 64 event sites for 33% more area, the
best return in the sweep.

**A geographic filter has to be checked against named landmarks it ought to contain, not only against
aggregate statistics.** A statistic cannot report what it never saw.

### Worth recording as a limitation

The surviving natural dropouts sit in the same duration band that scenario type 4 will inject into. In
the chosen box they are `[20, 100, 110, 200, 280, 280, 300, 970, 1160, 1440]` seconds — seven of ten
between 100 and 300 s. That is the confound `adp-004` names as a failure case, and it is present, not
avoided: 10 of 948 tracks, 1.05%. It is mitigable, because the coverage report names exactly which
tracks carry one, so the generator can refuse them as injection sites. See
[thesis_notes.md](thesis_notes.md), "Bounding box: 49–54°N, 3–11°E".
---

## 26. I am keen to go with the first option. Just want to understand the trade-off/overhead a bit more

**The overhead is smaller than it looks, because the repository seam is required by `db-003`
regardless of build order.** Deferring persistence does not add a layer that a database-first build
would have avoided; it defines that layer earlier and gives it a second implementation. The real cost
is concentrated in one place — the port's signature — and the real gap is one the spec text does not
currently distinguish.

The question arose when choosing what to build after the OpenSky corpus landed. `docs/handoff.md`
named `dal-004` as the next item, but `dal-004` pseudonymises identifiers on a canonical observation
that does not exist yet: `dal-001` is unbuilt, and `dal-002` (quarantine) and `dal-003` (provenance)
are the same code path. All three are worded around persistence, while `db-001` (schema and
migrations) and `db-005` (engine and session) are also unbuilt. So "build `dal-004` next" resolves to
one of two orderings, and the choice was between them.

### The wrong assumption the question corrects

The intuitive reading is that building the DAL before the database means **writing it twice** — once
against an in-memory stand-in, once against PostGIS. That is not what happens. What gets written
twice is the *repository implementation*, not the DAL. The validation, quarantine routing, provenance
attachment, and pseudonymisation are written once and never reopened, because they never touch a
database in either ordering. `db-003` forbids it:

> a route handler needing persisted data obtains it through a repository function; the handler
> contains no SQL, no session construction, and no spatial logic

The seam exists in the spec independently of when the database lands. Ordering decides only whether
the seam has one implementation or two at the moment the DAL items are marked passing.

### What is actually extra

| | |
|---|---|
| The port definition (a `Protocol`, two methods) | Not extra — `db-003` requires it either way |
| An in-memory fake in `backend/tests/` | Genuinely extra, roughly 50 lines. Not throwaway: the Phase 8 detectors, the evidence bundle builder, and the grounding check all need observations without a database, and reuse it |
| The SQLAlchemy implementation at `db-001` | Deferred, not duplicated — it is the code a database-first build would have written first instead of last |
| The DAL logic itself | Written once in both orderings |

### Where rework can actually happen

Only in the port's signature. An in-memory fake is permissive in three ways PostGIS is not, and each
is cheap to decide now and expensive to discover later:

| Decision | The fake makes it look like | PostGIS forces |
|---|---|---|
| `location` | a lat/lon pair carried on the model | a geometry column per `db-001`. The port must accept a canonical model and let the repository do the WKB conversion. A WKT string in the port signature means the DAL knows about PostGIS, and the seam is already broken |
| Record identity | sequential integers from a counter | `bigserial` or UUID assigned on flush. `evb-002` requires stored IDs to resolve, so the repository returns persisted objects and no test asserts an ID literal |
| Atomicity | trivially atomic — two lists appended | `dal-002`'s "seven observations and three quarantine rows, completes without raising" is **one transaction**. The port has to express that the two writes go together: one method taking both collections, or an explicit unit of work |

The blast radius if a signature turns out wrong is small, because the port is narrow and its only
callers at that point are the ingest function and `adp-001`.

### The gap this ordering leaves open, and why it is worth naming

Against a fake, `dal-003`'s failure case — an observation persisted with a null scenario run ID —
is proven by the DAL refusing to construct one. It is **not** proven by a `NOT NULL` constraint. Those
are two different guarantees, and only the first is in place when the DAL items pass:

- *The DAL behaves correctly* — asserted by unit tests against the fake, at `dal-001`–`dal-004`.
- *The database enforces it* — asserted by schema constraints, at `db-001`, later.

`dal-001`–`dal-004` at `passes: true` therefore means the first claim only. This is a deviation from
the plain reading of the spec text, which says "persisted", and it belongs in the handoff's
**Failed attempts**/deviation record rather than being left for the write-up to rediscover. The
second claim is not weakened by arriving later — it is simply not yet made.

### Why this ordering was chosen anyway

Because the alternative puts `dal-004` last. `docs/implementation.md` Phase 7 is explicit about why
that is the expensive mistake:

> Build it with `dal-001`, before `adp-001` replays a single real row: retrofitting it after a
> campaign means every stored observation, bundle, and hypothesis carries a real identifier that has
> to be migrated out.

A wrong port signature costs an afternoon. A campaign run before pseudonymisation exists costs the
campaign, and — per OpenSky DLA §3(i) and §3(iii), see [§22](#22-what-did-reading-the-actual-licence-file-change)
— makes every stored artefact a disclosure problem. The asymmetry is what settles it.
---

## 27. `dal-004` said to record the pseudonymisation seed in the corpus manifest. Why is it now a fingerprint?

**Because the manifest is committed, and `icao24` is only 24 bits wide.** A seed published beside the
derivation function does not protect anything: an `icao24` is six hex digits, so the whole space is
about 16.7 million values, and anyone holding the seed enumerates it and rebuilds the complete
pseudonym-to-airframe mapping in seconds on a laptop. The spec item forbade a readable reverse
mapping and required the seed to be published, in adjacent sentences. Only one of those could stand.

### The wrong assumption

The assumption was that a *seed* is like a *salt* — a value whose secrecy does not matter, recorded
for reproducibility. That holds when the input space is large enough to resist enumeration. It does
not hold here, and the reason is worth stating precisely because it is a property of the data rather
than of the cryptography:

| | |
|---|---|
| Hash function | HMAC-SHA256 — not the weak link, and not what fails |
| Input space | `icao24`: 24 bits, about 16.7 million values |
| Work to reverse the whole corpus, given the seed | One pass over 16.7M HMACs — seconds |
| Work to reverse it without the seed | Infeasible |

The seed is therefore not a salt but a **key**, and the security of the scheme rests entirely on it.
Publishing a key alongside the ciphertext is the failure, not the choice of algorithm. A password
hash resists an offline attack because a password is drawn from a large, unguessable space; a
transponder address is drawn from a small, fully enumerable one.

### What replaced it

The seed is read from the environment (`PSEUDONYM_SEED`, documented in `backend/.env.example`, no
default — a default seed is a committed seed by another name). The manifest records
`pseudonym_seed_sha256`, the SHA-256 of the seed. That preserves what recording it was for without
disclosing it:

- **A seed change stays a detectable, recorded corpus-level event**, sitting beside the extract
  checksum, rather than a silent one. Two corpora built under different seeds are distinguishable.
- **The corpus stays attributable** — a given extract can be shown to have been built under a given
  seed by whoever holds it.
- **The mapping stays irreversible to a reader**, which is the whole obligation under OpenSky DLA
  §3(i).

### The limitation this creates, which is real and should be stated

The mapping is now **machine-local**. A reader who accepts the licence and rebuilds the corpus
supplies their own seed, and gets different pseudonyms from the ones in this dissertation.

That costs less than it appears to, and the reason is worth being precise about. Nothing downstream
reads a pseudonym's *value* — it is an opaque grouping key, and detection, clustering, evidence
bundling and scoring are all invariant under relabelling. So every reported metric reproduces
exactly. What does not reproduce is a specific label quoted in a figure: `AC-a1d043d088e6` in a
screenshot cannot be matched to `AC-…` in a reader's rebuild.

That is the correct trade rather than a regrettable one. A figure whose labels a reader *could*
resolve back to real airframes is precisely the disclosure the item exists to prevent — so label
stability across machines and the licence obligation are in direct conflict, and the obligation wins.
See [§22](#22-what-did-reading-the-actual-licence-file-change) for the licence reading itself.

### Two smaller decisions recorded at the same time

**Callsigns are pseudonymised too, into a separate `flight_id`.** `dal-004` names both `icao24` and
`callsign` as identifiers. They are derived under separate namespaces, so an `icao24` and a callsign
that happen to share text cannot land on the same pseudonym. A **blank callsign yields no
`flight_id`** rather than a pseudonym of the empty string — OpenSky reports many blank callsigns, and
hashing `""` would give every one of them a single shared identity, which is worse than recording the
absence.

**Identifiers are normalised before hashing** — stripped and case-folded. OpenSky pads callsigns to a
fixed width, so `DLH8AT ` and `DLH8AT  ` are the same flight; without normalisation they would be two
different pseudonyms, and every track-continuity rule downstream would see two aircraft. This is a
trap rather than a refinement: the failure is silent, and it would present as a detection result
rather than as a bug.
---

## 28. What does a "seed" mean in this instance? Why does a rebuild give different pseudonyms, what is `PSEUDONYM_SEED` meant to be, and is `manifest.json` stale just because it lacks `pseudonym_seed_sha256`?

**Because the project has two unrelated things called a seed, and they have opposite disclosure
rules.** The scenario seed is published on purpose; the pseudonymisation seed must never be. Almost
all of the confusion in [§27](#27-dal-004-said-to-record-the-pseudonymisation-seed-in-the-corpus-manifest-why-is-it-now-a-fingerprint)
traces to the word being reused, and the original spec's instruction to commit the pseudonymisation
seed was very likely the same slip made once already.

### The two seeds

| | Scenario seed (`scn-001`) | Pseudonymisation seed (`dal-004`) |
|---|---|---|
| What it is | An integer initialising a pseudo-random number generator | A secret string used as an **HMAC key** |
| What it is for | Making randomness repeatable | Making a mapping irreversible |
| Scope | Per run — a batch of 25 runs has 25 derived seeds | Per **corpus** — one value, fixed for the project |
| Published? | **Yes.** A run is unreproducible without it, so `api-006` echoes it back and `scn-004` shows it in the UI | **No.** Publishing it reverses every pseudonym |
| Stored | On the run record | `backend/.env`, gitignored |
| In the manifest | n/a | Its SHA-256 **fingerprint**, never its value |

The pseudonymisation seed involves no randomness at all. It is a fixed secret that goes *into* a hash
function, in the same sense a password is a key. Calling it a seed is conventional but, in this
project, actively misleading.

### Why a rebuild under a different seed relabels everything

Because the seed is a direct input to the derivation. Nothing is random, so nothing is "regenerated":

```
pseudonym = HMAC-SHA256(key = seed, message = "icao24:3c6444")   then keep 12 hex characters
```

Worked, with the real implementation, on one aircraft — `icao24` `3c6444`:

| Input | Seed | Pseudonym |
|---|---|---|
| `3c6444` | `seed-one` | `AC-b743f8c6a190` |
| `3c6444` | `seed-one` | `AC-b743f8c6a190` — again, identical, always |
| `3c6444` | `seed-two` | `AC-2df5b3935837` — unrelated |
| `3c6445` | `seed-one` | `AC-9a2a5cc06bb2` — a neighbouring address, unrelated output |

Two properties follow, and the mechanism depends on both:

- **Deterministic in the seed.** One aircraft keeps one label across all 25 runs of a batch, which is
  what lets the detectors reason about track continuity across a replay.
- **Unpredictable without the seed.** The last row is the point: `3c6444` and `3c6445` are adjacent
  addresses in the German `3c` allocation block, and their pseudonyms share nothing. The allocation
  block does not survive, which is what [§27](#27-dal-004-said-to-record-the-pseudonymisation-seed-in-the-corpus-manifest-why-is-it-now-a-fingerprint)
  means by "carries no source information".

So a reader who rebuilds the corpus with their own seed gets a valid corpus with different labels.
Every metric still reproduces exactly, because nothing downstream reads a pseudonym's value — it is
an opaque grouping key.

### What `PSEUDONYM_SEED` should be set to

**Treat it as a password, because that is what it is.** Long and unguessable: if it can be guessed,
every pseudonym can be reversed, since checking a guess costs one pass over the 16.7 million `icao24`
values.

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Three rules attach to it:

- **Never commit it.** `backend/.env` is gitignored; `.env.example` carries only a placeholder.
- **Set it once and never change it.** Changing it relabels the whole corpus, so any figure already
  produced stops matching the data behind it.
- **Do not make it meaningful.** `em-fusion-2026` is guessable and therefore worthless as a key.

### Why the manifest is stale, and what fixes it

**Nothing in the file is wrong — it is missing one key.** `validate_manifest` now requires
`pseudonym_seed_sha256`, and the committed manifest predates it:

```
INVALID: manifest is missing required field: pseudonym_seed_sha256
```

Only `validate_manifest` rejects it. `build_corpus` still runs, because `read_source_ref` reads only
`source_url` and `original_sha256`, both present.

`build_corpus` rewrites the manifest wholesale, so running it adds the fingerprint. The raw tarball is
still under `data/opensky/raw/` and its checksum matches, so the roughly 180 MB download is **skipped**
— `adp-005` re-verifies and moves straight to filtering.

Two things to watch on that run:

- **`download_date` is a parameter, not a timestamp.** Passing today's date would record 2026-08-21 as
  the download date for a file fetched on 2026-08-13 — a false provenance claim in a committed
  artefact, and provenance is the entire reason the manifest exists. Pass `download_date="2026-08-13"`.
- **`content_sha256` must come out unchanged** at `7ce83881…be05`. The filter is deterministic over
  the same raw file and bounding box, and stability was verified across two builds. If it changes,
  something is wrong and the run should be stopped rather than committed — a changed content checksum
  means the extract is not the one every recorded measurement was taken against.

Worth recording as a limitation: the fingerprint proves *which* seed built a corpus only to somebody
who already holds that seed. To a reader it is an opaque commitment — enough to tell two corpora
apart, not enough to verify either. That is the intended trade, but it means the manifest's
reproducibility guarantee is weaker for the pseudonym mapping than for the extract itself, where the
content checksum is independently checkable.
---

## 29. I just ran the root `make check` and got errors, but the backend `make check` all passes

**The container image was stale.** Compose bind-mounts `./backend` over `/app`, so the container saw
today's source, but dependencies are baked into the image at build time and are not mounted. The
image predated `pyarrow` being added to `pyproject.toml`, so four test modules failed to import a
library that has been a declared dependency for over a week.

Nothing was wrong with the code, the Dockerfile, or the lockfile. `docker compose build backend`
followed by the same command gave 128 passed.

### Why the two halves disagreed

| | `backend/make check` | root `make check` |
|---|---|---|
| Runs against | the host venv, synced from `uv.lock` | the container image |
| Source | the working tree | the working tree, bind-mounted |
| Dependencies | `uv sync` — current | **baked into the image at build time** |
| Effect | always current | current only if the image was rebuilt since `pyproject.toml` last changed |

A bind mount that covers source but not `site-packages` produces a hybrid environment that exists
nowhere else: today's code against whichever dependencies were current when the image was last
built.

### The failure that matters is the other one

A missing module is loud, and it is the harmless direction. The dangerous direction is silent:

- A dependency is **removed** from `pyproject.toml`, but the stale image still has it installed. The
  suite passes in the container and would fail on a fresh clone or in CI.
- A dependency is **pinned to a new version** in `uv.lock`, but the image still holds the old one.
  The suite passes against a version nobody will ever install again.

In both cases the container reports success about an environment that does not exist. `ops-003`
already names this as its failure case — "a target that succeeds while the underlying compose command
fails, or a test target that reports success when either suite had failures" — and this is the same
defect one layer down: a target reporting success about the wrong environment rather than about a
failed command.

### What changed

Every quality target in the root `Makefile` now depends on `build-backend` or
`build-frontend-test`. Make resolves a shared prerequisite once per invocation, so `make check`
rebuilds once rather than five times, and a cached rebuild costs about a second.

The backend pytest arguments were also aligned. The root target ran bare `pytest --tb=short` while
`backend/Makefile` had just gained a 90% coverage gate, so `make check` meant two different things
depending on which directory it was typed in. Both now use one `PYTEST_ARGS` value with a comment
saying they must stay in step.

### Two smaller things the stale image was also hiding

The `StarletteDeprecationWarning` about `httpx` versus `httpx2` was an artefact of the same
staleness — `httpx2` is a declared dev dependency and the rebuilt image has it. It only became
visible because `--disable-warnings` had just been removed from `addopts`, which is a small argument
for having removed it.

Separately, the `ARTIFACTS` comment in the root `Makefile` still asserted that the OpenSky extract
"is committed to the repo rather than generated". That has been false since the licence reversal in
[§22](#22-what-did-reading-the-actual-licence-file-change). A comment is not executable, so nothing
failed; it had simply been wrong for a week.

### The general point, and it is not about Docker

The real defect was that **nothing runs both command surfaces**. Two ways to run the same suite
drifted apart in dependencies, in pytest arguments, and in a comment, and the drift was found by a
human typing a command rather than by anything automatic. That is `ops-002` — CI — and it remains
unbuilt. Until it exists, `make check` passing is evidence about one machine and one moment, not
about the repository.





---

## 30. What does an "adapter" mean in this project? My understanding is that it is the middle man between a raw data source and the application — it fetches the data, preprocesses it if needed, and hands it on

**Essentially yes, but this project makes an adapter considerably thinner than that description allows.** The middle-man framing is right; "fetches" and "preprocesses" both need narrowing, because in EM Fusion each of those has been deliberately moved somewhere else, and in two cases the move is enforced by an outright rejection rather than by convention.

An adapter here does exactly one thing: **translate a source's own dialect into the DAL's source-record shape.** Four jobs it does not do:

| Job | Who does it instead | How it is enforced |
|---|---|---|
| Fetching from the network | `adp-005` (`app/corpus/fetch.py`), the only module in the corpus tooling permitted to open a socket | `adp-001` reads from file only; a fallback to the OpenSky API when the extract is missing is its second failure case |
| Attaching provenance | The DAL, per `dal-003` | `validate_record` **rejects** a record arriving with a `provenance` key: "provenance is attached by the DAL, not supplied by an adapter" |
| Pseudonymising identifiers | The DAL, per `dal-004` | Validation rejects a payload arriving with `aircraft_id` or `flight_id` already populated |
| Persisting anything | `ingest_batch`, through the repository port | The adapter never imports `app.dal.repository` and cannot know a database exists |

What remains as legitimate "preprocessing" is dialect translation and nothing more: mapping Parquet column names onto source-record keys, handling units, and computing derived measured fields such as `position_staleness_s` from `time - lastposupdate`. It is *not* cleaning, enriching, or de-identifying.

One consequence is easy to get backwards. **An adapter must not drop rows it judges bad.** `adp-004` deliberately retained a bounded sample of null-position rows so that `dal-002`'s quarantine path has real input rather than fixture-only input; an adapter that filtered those out would silently remove the only real-data evidence for AC-02. A malformed row is passed through unchanged and the DAL quarantines it.

The shape an adapter emits, taken from the fixture in `tests/test_dal_pseudonymise.py`:

```python
{
    "source_id": "opensky-replay",
    "source_type": SourceType.OPENSKY,
    "observation_type": ObservationType.TRACK,
    "timestamp": datetime(...),
    "location": {"lat": 51.09, "lon": 7.54},
    "payload": {"icao24": "3c6444", "callsign": "DLH8AT  ", ...},
}
```

Note what is absent: no `data_mode` and no `scenario_run_id`. Those describe the run rather than the record, and reach the DAL through `IngestContext`.

The reason for the thinness is RQ1. Every obligation that holds across *all* sources is discharged once, at the DAL, so that `adp-003` — the third adapter, whose files-touched and lines-changed figures are the extensibility evidence — costs almost nothing to add. If adapters carried provenance and pseudonymisation themselves, that measurement would be recording an author's diligence rather than a property of the architecture, and the RQ1 claim would be unfalsifiable. See `docs/thesis_notes.md` for the decision itself; this entry only explains what it means.

## 31. `adp-001` requires an adapter that carries its provenance for OpenSky telemetry, which means an `icao24` or callsign is present — isn't that exactly what `dal-004` pseudonymisation is built to avoid?

**No, and the apparent conflict rests on two separate conflations.** Both are worth naming, because the second one is the same mistake that produced a real defect earlier in the build.

**First: provenance is not identity.** In this project provenance is exactly four fields, defined once on `Provenance` in `app/dal/models.py`:

| Field | What it records |
|---|---|
| `source_id` | Which instance of a source — `"opensky-replay"` |
| `source_type` | Which kind of source — `opensky`, `synthetic_rf` |
| `data_mode` | Replayed or synthetic |
| `scenario_run_id` | Which run this record was ingested under |

Provenance answers *where did this record come from, under which run*. It never answers *which aircraft is this*. An `icao24` is aircraft identity and lives in the payload, not in provenance. The RF adapter is the clean demonstration: RF observations carry full provenance and no identifiers whatsoever — `IDENTIFIER_RULES[ObservationType.RF]` is an empty tuple. So "the record carries provenance" implies nothing at all about whether an identifier is present.

**Second: the adapter does not carry provenance in the first place.** `dal-003` attaches it at the DAL, from the ingest context. A record that arrives with its own `provenance` key is rejected, not merged.

With those separated, the actual relationship is the opposite of a conflict. **The adapter must pass the raw `icao24` and callsign through, and that is the precondition for `dal-004` rather than a violation of it.** `dal-004` requires the substitution to happen at the DAL "so a new adapter cannot forget it" — and for the DAL to perform the substitution, the raw value has to reach it. An adapter that handed over a ready-made opaque `aircraft_id` would *be* the pseudonymiser, which is precisely the failure `dal-004` exists to prevent. This is not hypothetical: `dal-001`'s original fixtures did exactly that, and the defect survived until `dal-004` exposed it. The fixture now carries the corrective comment, "A source record as the adapter emits it: real identifiers, still."

Where a real `icao24` may and may not appear:

| Location | Real identifier present? | Why |
|---|---|---|
| `opensky_extract.parquet` on disk | Yes | Local use, which the licence permits — the restriction is on publication and disclosure |
| The adapter's source-record mapping, in memory | Yes | For the duration of one `validate_record` call, so the DAL has something to substitute |
| Canonical observation, database, API response, evidence bundle, hosted-provider payload, rendered screen | **No** | No field anywhere in the canonical model can hold one; a test asserts this across all four models |

The obligation under OpenSky DLA §3(i) is to de-identify for publication or other disclosure, and under §3(iii) not to make the data available outside the licensee's institute. Neither is a prohibition on local processing. The pseudonymisation boundary is therefore drawn at the edge of the canonical model, not at the edge of the process.

**A trap this creates for `adp-001`.** A quarantined OpenSky row still holds a real `icao24`, since it never reached the pseudonymiser. That is why `QuarantineRecord` stores the failing field, the reason, and best-effort attribution rather than the raw source row. Any logging, exception message, or diagnostic added on the quarantine path that echoes the row would reintroduce the real identifier into a place the model was carefully shaped to exclude — and it would do so on the error path, which is the least-inspected code in the system. Worth recording as a limitation of the boundary: the guarantee is structural for the success path and merely conventional for the failure path.

## 32. Just to understand what we are building for `adp-001` — this is essentially a read-only file that reads the parquet files through the built DAL and converts to the canonical model following the quarantine rules? And a `read_parquet` therefore needs to be added in `backend/app/corpus/extract.py`?

**Essentially yes on the pipeline, no on both specifics.** The read-only description is exactly right and the sequence of steps is right, but three of the four actions in the question belong to the DAL rather than to the adapter, and the reader belongs in the adapter module rather than in the corpus tool.

### The adapter converts nothing and quarantines nothing

Attributing the conversion and the quarantine rules to `adp-001` is the misunderstanding worth correcting, because it is the same boundary that §30 and §31 turn on, approached from a third direction. Ownership of each step:

| Step | Who does it | Where |
|---|---|---|
| Read Parquet rows | Adapter | `app/adapters/opensky.py` |
| Map columns onto source-record keys, compute `position_staleness_s`, select `baroaltitude` | Adapter | same |
| Validate required fields, decide quarantine, attach provenance, derive pseudonyms, construct `CanonicalObservation` | **DAL** | `validate_record`, `ingest_batch` |
| Persist observations and quarantine rows as one unit of work | Repository port | `app/dal/repository.py` |

The adapter never judges a row. It emits every row it reads — including the 500 null-position rows `adp-004` deliberately retained — and the DAL splits the batch. "Following the quarantine rules" is therefore not something the adapter does; it is something the adapter must not **pre-empt**, which is why `adp-001`'s third failure case makes filtering null-position rows inside the adapter a spec failure. Such an adapter would pass its own tests, look tidy, and silently remove the only real-data input `dal-002` has, reducing AC-02 to a fixture claim.

Stated positively: **`adp-001` reads Parquet rows and emits source records, and that is the whole of it.** The DAL is downstream of the adapter, not inside it.

### The reader does not belong in `extract.py`

Three reasons, in ascending order of weight.

**Lifecycle.** `extract.py` opens by declaring what it is: "This module is the tool; `opensky_extract.parquet` is the artefact it writes. Run by hand when the corpus is built — not on the request path." It is build-time tooling, run once per corpus. The adapter runs at replay time, on every scenario run. Merging them puts two lifecycles in one module.

**Dependency direction.** An adapter importing the corpus tool would pull `tarfile`, `gzip`, `csv`, `hashlib` and manifest construction into the replay path's dependency graph — the consumer of an artefact depending on the tool that downloads and filters it. The arrow points the wrong way.

**The reader needs nothing from it, by design.** Parquet carries its schema inside the file, which is what the comment on `parquet_schema` means by "the schema carried inside the artefact, so no reader can infer it". Verified against the real extract: `ParquetFile.schema_arrow` returns the writer's fields in the writer's order, so a reader recovers the exact types without being told them. A reader that imported `parquet_schema()` would be restating what the artefact already carries, and would drift from it the moment the two disagreed — precisely the failure the in-file schema exists to prevent. The correct reader asks the file.

So the reader lives in `backend/app/adapters/opensky.py` and imports nothing from `app.corpus`.

### Reading mechanism

`pq.ParquetFile(path).iter_batches(batch_size=...)` streams record batches rather than materialising the table, which is what `adp-001`'s lazy-yield constraint requires over a 133,634-row extract. Two practical notes established by inspection rather than assumption:

- `iter_batches` accepts `batch_size`, `row_groups`, `columns`, `use_threads` and `use_pandas_metadata` in pyarrow 25.0.1 — **no `filters` argument**. The time-window predicate is therefore applied per batch in Python, not pushed into the reader.
- The extract is written as a **single row group**, so row-group pruning would not help even if it were available. Predicate pushdown is not on the table for this artefact, and the streaming read is what keeps memory bounded.

### A trailing detail worth not being surprised by

Callsigns in the extract carry trailing spaces — `'KLM30Q  '`, `'CXI27NM '` — because the source pads them to a fixed width. The adapter passes them through unchanged, as it passes everything through unchanged; normalising whitespace is `dal-004`'s business, since it is the component that decides whether a callsign is blank and therefore yields no `flight_id`. An adapter that helpfully stripped them would be making an identity decision, which is the boundary §31 draws.

## 33. A couple of questions before we implement: what does a half-open window mean, what is position staleness, and what do the `-1` and `-2` and `offset_s` mean in the test fixture's `lastposupdate` and `lastcontact`?

**Three answers, and the third one surfaced a gap in the canonical model that is recorded at the foot of this entry.**

### Half-open window

`[start, end)` means **start included, end excluded** — square bracket inclusive, parenthesis exclusive, in the ordinary mathematical notation for intervals. `adp-001` specifies it rather than leaving it to the implementer because it is the only convention under which contiguous windows tile the timeline exactly once, and the two alternatives each corrupt a measurement the project reports.

With frames at 0, 10, 20 and 30 seconds, and a runner stepping two adjacent windows:

| Convention | `[0,20]` then `[20,40]` | Consequence |
|---|---|---|
| Closed, `[a,b]` | Frame 20 appears in **both** | The frame is ingested twice. A continuity rule then sees two samples at the same instant — a zero-second inter-sample gap that never occurred |
| Open, `(a,b)` | Frame 20 appears in **neither** | A ten-second dropout is manufactured, indistinguishable from the coverage gap scenario type 4 injects |
| **Half-open, `[a,b)`** | Frame 20 appears in the second only | Each frame seen exactly once |

Both failure modes land in the false-positive rate for the aircraft-coverage-gap scenario, which is a reported result, so the convention is a correctness requirement rather than a stylistic one.

### Position staleness

**How old the position carried inside a row is, at the moment that row was written**, computed as `time - lastposupdate`.

The mechanism is worth being precise about, because the field is easy to misread as "time since we last saw the aircraft". OpenSky emits a state vector for every tracked aircraft on a fixed ten-second cadence whether or not anything new has arrived. When no fresh position message has been received, the row is still emitted and repeats the **last known** position. `lastposupdate` records when that position was actually refreshed, so the delta is the age of the coordinate rather than the age of the row.

This is why `em_fusion_v2.md` §5 calls it a directly measured field rather than an inferred one, and makes it the basis of the "aircraft update frequency drops" rule: under interference an aircraft does not disappear from the feed, it continues to appear with a position that has stopped advancing.

Measured over the 133,134 positioned rows of the current extract:

| Statistic | Position staleness |
|---|---|
| p50 | 0.33 s |
| p90 | 38.92 s |
| p99 | 269.63 s |
| max | 1561.12 s |
| mean | 17.07 s |
| negative values | 0 |

The absence of negative values is a sanity check worth keeping: a negative staleness would mean a position refreshed after the row reporting it was written, which would indicate the two columns had been transposed.

**Do not conflate position staleness with the inter-sample gap.** They measure different things on different axes, and `coverage.json` reports the second, not the first:

| Measure | Axis | Question it answers |
|---|---|---|
| Position staleness | Within a single row | How old is this coordinate? |
| Inter-sample gap | Between consecutive rows for one `icao24` | How long since we heard from this aircraft at all? |

### The `-1`, the `-2`, and `offset_s`

`EPOCH_START` is `1656331200`, which is `2022-06-27T12:00:00Z` — the snapshot hour the manifest records. `offset_s` is seconds into that hour, so `_row(10)` is the frame at `12:00:10`.

```
time          = EPOCH_START + offset_s     the frame's own timestamp
lastposupdate = time - 2                   position last refreshed 2 s earlier
lastcontact   = time - 1                   last heard from 1 s earlier
```

The default row therefore carries `position_staleness_s == 2.0`, and the ordering `lastposupdate <= lastcontact <= time` mirrors the real relationship: an aircraft is heard from more often than it yields a fresh position, because not every transmitted message carries one.

The two offsets are **deliberately different values**. Were both `-1`, an implementation that read `lastcontact` where it meant `lastposupdate` would compute the correct answer and every test would pass — the fixture would be concealing exactly the bug it exists to catch. Distinct values make column confusion detectable. The same reasoning drives `test_position_staleness_is_the_measured_delta_from_lastposupdate` overriding `lastposupdate` to `EPOCH_START + 4` against a frame at offset 10 and expecting `6.0`: a different number from the fixture default, so the test cannot pass against a hardcoded constant.

`-2` is also empirically plausible rather than arbitrary — p50 staleness in the real corpus is 0.33 s, and the first row sampled from the extract showed 1.06 s.

### What this surfaced: `lastcontact` has nowhere to go

`TrackPayload` carries no field derived from `lastcontact`, so the adapter reads the column and drops it. The original `adp-001` text listed it among the output fields; the 2026-08-23 amendment listed the payload as exactly the canonical fields, which silently removed it.

That is not a harmless omission, because `lastcontact - lastposupdate` distinguishes two scenario types from one another:

| Signature | Interpretation | Scenario type |
|---|---|---|
| Contact stale **and** position stale | The aircraft is no longer being heard at all | 4, aircraft data-source coverage gap |
| Contact **fresh**, position stale | The aircraft is still transmitting but its position has stopped advancing | 2, GNSS degradation / possible interference |

The real data carries this signal in quantity: **4,553 positioned rows, 3.4 per cent, hold a position more than 10 seconds older than their last contact**, with a maximum of 1552 s. The distributions confirm the mechanism rather than merely suggesting it — contact staleness caps at 299.97 s, which is OpenSky dropping a state vector after roughly five minutes of silence, whereas position staleness runs to 1561 s precisely because the row continues to be emitted while the coordinate inside it is frozen.

Adding `contact_staleness_s` to `TrackPayload` is a change to `dal-001`, which is a passing item, so it is raised here rather than made in passing. The decision and its rationale belong in `docs/thesis_notes.md` once taken; what this entry records is what the field means and why its absence matters. See also §30 on why the adapter may not compensate by inventing a payload field of its own.

## 34. Based on `docs/handoff.md` next steps are `db-005` and `db-001`. Clarify these work with me and confirm that these are the next strands of work

**Confirmed, in that order — and the handoff overstates what `db-001` contains.**

### What each item actually is

| | `db-005` | `db-001` |
|---|---|---|
| Question it answers | *How does the process reach the database?* | *What is in the database?* |
| Output | `sqlalchemy` and `psycopg` added and locked; one `Engine` per process created in the lifespan hook and disposed on shutdown; a `sessionmaker` bound to it; a FastAPI dependency yielding one `Session` per request | Six tables — `observations`, `anomalies`, `evidence_bundles`, `hypotheses`, `analyst_feedback`, `scenario_runs` — created by ordered migrations, with geometry columns on `observations.location` and `anomalies.affected_area` |
| Needs a live database to prove? | **No.** Engine construction is lazy and opens no connection, which the spec requires precisely so this stays true | **Yes.** A migration that has never been applied is an untested migration |
| Touches | `app/main.py`'s lifespan, a new `app/db/` module, `pyproject.toml`, `backend/.env.example` | Migration files, table definitions, and the test tier |

The order is forced rather than preferred: a migration needs a URL and a connection, so `db-005` is `db-001`'s precondition. The reverse does not hold — `db-005` is provable against no database at all.

### Why this is the next strand, and why Phase 5 is not

Four things are waiting on it, and nothing else is:

1. **Two passing items assert only half of what they claim, and say so in their own text.** `dal-002` states that "the `NOT NULL` and foreign-key guarantees over the same fields are `db-001`'s to prove, and `passes: true` here asserts the first claim only". `dal-003` makes the same split for provenance: the DAL must refuse to *construct* a record without it, and the schema must refuse to *store* one. Until `db-001` lands, one assertion in each pair is a claim rather than a test.
2. **The only `ObservationRepository` is the in-memory fake in `backend/tests/fakes.py`.** The replay path runs end to end into a test double; nothing survives the process exiting.
3. **`adp-007` was deferred behind it on purpose** (decided 2026-08-26). A replay command written before there is a real repository could only count without persisting, and would need a second pass to grow a `--persist` path.
4. **The 2.46 s full-corpus replay figure measures the reader and the DAL only.** The figure that will bound a scenario run includes persistence, and cannot be taken until persistence exists. *(Superseded 2026-09-04: `adp-007` re-took it through PostGIS at **14.25 s** over twelve batches. The 2.44/2.46 s discrepancy between this file and `thesis_notes.md` was never adjudicable, because the script that produced it was gone — see the replay subsection in `thesis_notes.md`.)*

Phase 5 (`/api/v1/operational-picture`) is deliberately absent from that list. It serves a static fixture in the frontend's shape, and `docs/implementation.md` says outright that "nothing here needs the database, the generator, or the DAL". It neither blocks this work nor is blocked by it, so its position after the database items is a scheduling choice rather than a dependency — worth knowing, because a dependency cannot be reordered and a schedule can.

### The correction: `db-001` is not where the PostGIS repository lands

The handoff's Next step reads "`db-005` then `db-001` … at which point the PostGIS implementation of `ObservationRepository` lands". **That conflates two spec items.** `db-001`'s description is schema and migrations and nothing else; the repository layer is `db-003`, whose constraint is that route handlers contain no SQL, no session construction, and no spatial logic.

The distinction is practical, not bureaucratic. Schema and repository fail differently and at different times: a wrong column type fails at migration time against an empty database, whereas a wrong repository fails at write time against a populated one. Fused into one item, a red test cannot tell you which of the two is wrong. Decided 2026-08-26 to keep them separate, so the sequence is `db-005` → `db-001` → `db-003`, and the handoff's wording is the thing that was wrong.

### `db-002`'s columns are built by `db-001`'s migration

These two items overlap, and the overlap is intentional rather than an error. `db-002` requires `generator`, `model_id`, `generation_params`, and `raw_response` on `hypotheses` "from the first migration, not a later one" — so the DDL belongs to `db-001`. What `db-002` proves separately is the *rejection*: a hypothesis written with `generator` set but `model_id` or `raw_response` null must be refused at the repository boundary for the two model arms.

The consequence is that `db-001` cannot be built by writing only the tables the current code touches. `evidence_bundles`, `hypotheses`, `analyst_feedback`, and `scenario_runs` have no consumers yet and will have none for several phases. Building them anyway is not speculative work, because `docs/em_fusion_v2.md` §9 is explicit that `raw_response` "is not retrofittable after a campaign has run". A table built late is a migration; a *column* built late, after a campaign, is a campaign that has to be re-run.

### The four things that were undecided, and now are not

None of these were settled anywhere in the docs, and all four change what the first test asserts, so they were taken before any test was written.

| Question | Decision | The alternative it beat |
|---|---|---|
| Migration mechanism | **Alembic**, revisions hand-written, autogenerate off | Ordered SQL files with our own runner. Alembic's version table *is* the "apply twice from empty must not error" failure case, so hand-rolling it means writing and testing the thing the dependency already provides. Autogenerate is off because it does not understand PostGIS geometry columns |
| How database-backed tests run | A **disposable `test_em_fusion` database in the existing `postgis` service**, with DB tests marked and skipped when `DATABASE_URL` is absent | testcontainers-python, which starts its own container per session but costs startup time on every run — and §18 measured this image at roughly 2.5× slower under amd64 emulation. The marker is what preserves `db-005`'s requirement that unit tests need no live database |
| Where the PostGIS repository lands | **`db-003`**, after `db-001` | Widening `db-001`. See the correction above |
| Geometry column type | **`geometry(…, 4326)` with `::geography` casts at query time**, GiST-indexed | Storing `geography` directly. `db-004` requires the distance to be computed *by PostGIS* rather than in application code, and a cast satisfies that — the arithmetic is still PostGIS's. Geometry keeps the full function set available for the spatial clustering in Phase 6 |

Both `db-005` and `db-001` are pre-existing spec items, but `db-001`'s description was written long before these four answers existed and names none of them. It is amended before tests are written rather than after — the lesson `adp-001` taught, where stale spec text survived several readings and was falsified by a decision taken in a different item.

## 35. Amendment approved — write it. Amend `ops-003` as well to add `migrate`, and let's exclude the DB modules on `make test`

**Done, with one refinement to the exclusion — because "`make test`" names two different targets and the instruction is ambiguous between them.**

### The two surfaces, and why the difference matters here

There are two `test` targets, deliberately not merged, and §29 already recorded that they drift silently:

| | `backend/make test` | root `make test` |
|---|---|---|
| Runs | `uv run pytest` against the local venv | `docker compose run backend pytest`, plus Vitest |
| Database reachable? | Only if the operator set `DATABASE_URL` and started the container | Yes, once `test-backend` drops `--no-deps` (part of the `ops-003` amendment) |
| Coverage gate | 90 per cent | 90 per cent, from the same `PYTEST_ARGS` |

Excluding the database modules from "`make test`" therefore resolves two ways. Read as *the native
one*, it makes the two surfaces enforce different rules — which is the drift the root `Makefile`'s
own comment says it exists to prevent. Read as *both*, it excludes the modules everywhere and they
are then measured nowhere at all, which is worse than a failing gate because it is silent.

### The refinement

The exclusion is conditioned on **whether a database is reachable**, not on which Makefile was typed.
It is the same signal the skip marker already uses, so the modules and their tests are skipped and
omitted together, or neither. One rule — *measure coverage over what was exercisable here* — holds in
both places, and the containerised run is the authoritative figure because it is the one where
nothing is excluded.

This is written into `db-001` as its fifth failure case rather than left as an implementation note,
because the failure it guards against produces a green gate. An unconditional omission would let the
PostGIS repository land in `db-003` with no coverage in any environment, and every command surface
would keep reporting success.

### What the `ops-003` amendment carries

- **`migrate`** added to the enumerated target list, applying the Alembic revisions against the running database.
- **`test-backend` loses `--no-deps`.** It currently starts the backend container alone, so the `postgis` service is not running and every database test would skip while the target reported success. That satisfies the letter of `ops-003` and defeats its purpose, so it is now an explicit failure case.
- A note that this item **enumerates its targets**, which makes it the thing to amend whenever one is added. `replay` (`adp-007`) is the other one outstanding — the same trap the handoff flagged, now recorded in the item itself rather than only in a handoff that gets overwritten.

## 36. Couple of questions on `db-005`: can we cache the engine and the sessionmaker using `lru_cache`, and since `DATABASE_URL` runs through an env, do I need to add it to an env file?

**No to the first — it would fail two of `db-005`'s own tests. And the second exposed a defect in the README: the key is already in `.env.example`, but `backend/.env` is not read by the backend at all.**

### Why `lru_cache` is the wrong tool here

The idiom is real and widely used — the FastAPI documentation applies it to a settings object — so
the answer is not that caching is bad, but that this particular thing is not a cache.

| Problem | What happens |
|---|---|
| It reintroduces lazy self-construction | `@lru_cache` on `get_engine` builds an Engine on first call *from anywhere* — a route handler, a script, a stray import. `db-005` names "constructing an Engine inside a request handler" as a failure case; the cache does not prevent that, it hides it |
| Disposal splits in two | `dispose_engine` would need `.dispose()` **and** `get_engine.cache_clear()`. Clearing the cache does not dispose the pool, so a caller who does one and not the other leaks it. Today one function does both |
| On a zero-argument function it is a global with extra steps | Nothing is being memoised, because there is no key. The lifecycle just becomes less visible |
| Keyed on the URL it is actively wrong | `@lru_cache def _engine_for(url)` builds a *second* Engine the moment a process sees a second URL, violating "exactly one Engine exists per process". Memoising per distinct argument is the opposite of a singleton |
| Two caches can fall out of step | The sessionmaker must be bound to the current Engine. `init_engine` sets both in one place; two independent caches cannot guarantee that |

Concretely, two committed tests fail under the cached version.
`test_get_engine_before_startup_fails_loudly` asserts that a bare `get_engine()` raises
`EngineNotInitialisedError`; the cached version returns a working Engine instead.
`test_lifespan_creates_the_engine_and_disposes_it` asserts the same raise after the lifespan exits.
Both are asserting the same property — that the lifespan is the only place an Engine comes from —
and that property is exactly what the cache removes.

Worth being clear that the cache is not even available for the settings-shaped use here: caching
`database_url()` would break every test that monkeypatches the variable, because a cached read never
sees the change.

### The env file: the key exists, but nothing loads it

The wrong assumption embedded in the question is a reasonable one, and it was in the README too: that
because `DATABASE_URL` is read from the environment and `backend/.env.example` documents it, creating
`backend/.env` makes the backend see it. **It does not.**

`load_dotenv` is called in exactly one place in this repository — `app/corpus/build.py`, inside its
own entrypoint, so that `PSEUDONYM_SEED` need not be exported by hand. `app/main.py` does not call
it. A bare `uvicorn app.main:app` therefore fails at startup with `MissingDatabaseUrlError` even
with a correct `.env` file sitting beside it, and the error message points at the environment rather
than at the file, which is the least helpful possible place to look.

What is actually needed, by how the backend is run:

| How it runs | Needs `backend/.env`? | Where the value comes from |
|---|---|---|
| `make up`, or anything through Compose | **No** | `compose.yaml` passes `DATABASE_URL` to the `backend` and `pipeline` services, defaulting to `…@postgis:5432/em_fusion`. The host is the Compose service name, not `localhost` |
| `pytest`, native or containerised | **No** | `tests/conftest.py` sets it for every test, deliberately to an address where nothing listens |
| Native `uvicorn` | **Yes, and it must be loaded explicitly** | `uv run --env-file .env uvicorn app.main:app`, or export the variable |

The README has been corrected to the third row; it previously showed `cp .env.example .env` followed
by a bare `uvicorn`, which does not work.

### The decision this leaves open

There are two defensible fixes and only the documentation one has been applied. The alternative is to
call `load_dotenv(DEFAULT_ENV_FILE, override=False)` in `app/main.py`, matching the convention
`app/corpus/build.py` already set, so that `.env` works for both entrypoints and an explicitly
exported variable still wins. That is more consistent, and it is what someone coming from
`build.py` would reasonably expect. It is *not* in conflict with `db-005`'s "read from the
environment only" constraint, because `load_dotenv` populates the environment before it is read —
which is precisely what `build.py` does for the pseudonymisation seed.

It has been left undone rather than slipped in, because it is a behaviour change to application
startup and this project's workflow requires a spec item and a failing test before implementation
code. Recorded here as an open question rather than a settled one. The argument against it is thin
but not nothing: a container that mounts the source directory would then pick up a developer's local
`.env` in preference to nothing, which is a way for a local value to reach a containerised run
without anyone choosing it.

## 37. I think I will mostly be running `make up`, so if Compose passes it to backend and pipeline without needing a `.env`, then there's no need to load it via `main.py`

**Agreed, and this settles the open question left at the end of §36: `app/main.py` will not call `load_dotenv`.**

The reasoning holds on the file as written. `compose.yaml` supplies `DATABASE_URL` to both the
`backend` and `pipeline` services as `${DATABASE_URL:-postgresql+psycopg://…@postgis:5432/em_fusion}`,
and the `:-` is a shell-style default rather than a placeholder — so a fresh clone with no `.env`
gets a working value, pointing at the Compose service name rather than at `localhost`. Adding
`load_dotenv` to the application entrypoint would introduce a second mechanism supplying the same
variable for a path that is not the primary way this project is run, and a second place to look when
the value is wrong is a cost paid on every future debugging session.

The consequence to accept knowingly: **native `uvicorn` now requires `uv run --env-file .env` or an
exported variable, permanently, and that is documented in `README.md` rather than fixed in code.**
Someone who has previously run `python -m app.corpus.build`, which *does* load `.env`, will
reasonably expect the server to behave the same way. The inconsistency between the two entrypoints is
real; it is being accepted rather than resolved, because the entrypoint that behaves differently is
the one that is almost always run through Compose.

### The trap this leaves for `adp-007`

Worth recording now, because it will be hit later and will look like a new bug. **`compose.yaml`
passes `DATABASE_URL` and nothing else** — there is no `env_file:` key and no `PSEUDONYM_SEED` in any
service's `environment:`. That is harmless today, because nothing running inside the container calls
the pseudonymiser: the corpus is built natively, where `app/corpus/build.py` loads `.env` itself.

It stops being harmless at `adp-007`, whose whole purpose is a `python -m app.replay` entrypoint run
by a Makefile target in a container. Replay goes through the DAL, the DAL pseudonymises at ingest,
and `Pseudonymiser.from_environment` fails loudly when `PSEUDONYM_SEED` is absent — correctly, but
inside a container, with a message about project configuration held outside the repository. The fix
belongs to `adp-007`: pass the seed into the `pipeline` and `backend` services, from the host
environment rather than from a committed default, since §28 and `dal-004` forbid the value being
committed anywhere. Deciding it now costs a paragraph; discovering it costs a debugging session on a
container that fails for a reason the error message locates in the wrong place.

## 38. Let's start the spec-to-test cycle for `db-001`

**Two things in the amended text were wrong, and both were found by checking the spec against code written after it. Neither would have failed a test — they would have produced a schema that was quietly missing a table, and a test tier that could never run.**

### The six tables have nowhere to put a quarantined record

`dal-002` requires that invalid records are persisted "to quarantine with the failing field, the
reason, and the source attribution". `db-001` named six tables, taken from the ERD in
`docs/em_fusion_v2.md` §9, and none of them is a quarantine table. The ERD predates `dal-002`, so
nothing ever reconciled the two.

The tempting fix is the one that adds no table, and it is wrong. `ValidationStatus` already has a
`QUARANTINED` member, which reads as an invitation to store the record in `observations` with a
status flag. Compare the shapes:

| | `CanonicalObservation` | `QuarantineRecord` |
|---|---|---|
| `source_id` | required | **optional** |
| `source_type` | required | **optional** |
| `observation_type` | required | **optional** |
| `scenario_run_id` | required (in provenance) | required |
| `timestamp`, `location`, `payload` | required | **absent entirely** |
| `field`, `reason` | absent | required |

The three fields an observation cannot do without are the three a quarantined record does not have,
and that is not an oversight — they are the fields that failed validation. A record is quarantined
*because* its latitude would not parse, so there is no location to store. Putting it in
`observations` would mean making `timestamp`, `location` and `payload` nullable, which deletes the
`NOT NULL` guarantee `dal-003` explicitly defers to `db-001`. The item would remove the assertion it
exists to add.

So: a seventh table, `quarantined_records`, and the ERD in §9 amended to match. Its nullability
encodes the best-effort rule `dal-002` already states — `scenario_run_id` is `NOT NULL` because it
comes from the ingest context rather than from the record, while `source_id`, `source_type` and
`observation_type` are nullable because a record can fail precisely because it is missing the field
that identifies it. The raw source row is still not stored, for the reason `app/dal/repository.py`
gives: a quarantined OpenSky row carries a real `icao24`, and keeping it would put in the database
the identifier `dal-004` exists to keep out.

### The stated skip condition could never fire

`db-001` said its database tests "skip when `DATABASE_URL` is absent". That was true when written on
27 August. It was falsified on 28 August by `tests/conftest.py`, which sets `DATABASE_URL` for
**every** test to an address where nothing listens, so that `db-005`'s engine tests have a value that
resolves without connecting. The variable is now never absent, so the skip would never fire and the
database tests would attempt to run — against port 1 — in every environment.

This is the third time in this project that spec text has been falsified by later work in a
*different* item. `adp-001` described a committed Parquet file that `adp-004`'s licence reversal had
made gitignored; the previous handoff claimed a reader existed that did not. **The pattern is
consistent enough to name: spec text describing the state of something outside its own item is a
claim with no test behind it, and it decays silently.** Reading the spec immediately before writing
tests — rather than trusting the reading done when it was amended — is what has caught it each time.

The replacement is a separate `TEST_DATABASE_URL`, and the reason to prefer it is stronger than
naming. `db-001`'s tests create and drop schema. Keying them on whatever `DATABASE_URL` happens to
hold means that a developer running the suite with their normal environment loaded eventually runs a
`DROP` against a database they cared about. Two variables make that impossible by construction rather
than by remembering.

### Worth recording as a limitation

Both problems were found by reading, not by a failing test, and neither was reachable by one. A spec
that misdescribes the world produces tests that faithfully assert the wrong thing — a green suite
over a schema missing a table. The only mitigation in place is the workflow's requirement to read the
item immediately before writing its tests, which is a procedural control rather than a technical one,
and it should be stated as such rather than presented as rigour.

## 39. Let's move onto `db-003`, but remind me what that is trying to achieve

**It closes the only open seam in the ingest path: the DAL currently hands its output to an interface
that has exactly one implementation, and that implementation is a fake used in tests.** `db-003` writes
the real one, against PostgreSQL and PostGIS, so a replayed hour actually lands in the database
instead of in a Python list.

That is the *mechanical* answer. The reason the item exists as its own numbered capability, rather
than as the last paragraph of `db-001`, is a research answer, and it is the more important one.

### What the item is really testing

`dal-002` required the DAL to persist through a **port** — an interface accepting canonical
observations and quarantine records, with the storage engine hidden behind it. That port was defined
and built *before any database existed*, deliberately, and its signature was constrained in two ways:

| Constraint | Why it was imposed |
|---|---|
| No storage-engine type crosses it | No session, no engine, no WKT or WKB string, no caller-supplied primary key. A geometry type in the signature would mean the DAL knows about PostGIS, and the seam would be broken before it was built. |
| One call, both collections | A batch of ten with three invalid must leave seven observations and three quarantine rows, or nothing. Split across two methods there is a window where the observations are stored and their quarantine rows are not. |

Writing an interface against an imaginary database is easy. **The claim under test is that the
interface was designed well enough to survive contact with a real one unchanged**, and that claim
cannot be tested until the real one is written. `db-003` is where it gets tested.

There is a prediction on record from the session that built the port, and it should be scored rather
than quietly forgotten:

> geometry and atomicity are the risks; identity is not.

Meaning: the port passes latitude and longitude as plain numbers, and something has to turn them into
a PostGIS point — that conversion is where a storage type is most likely to leak upward. And the
one-unit-of-work guarantee has to become a real transaction, which is the other place the shape may
not fit. Identity was judged safe because the port never lets the caller supply a primary key.

**If the signature has to change, that is a finding, not a failure.** It is direct evidence about
RQ1 — how well a Data Abstraction Layer can be specified ahead of its storage — and a changed
signature with a recorded reason is a stronger result than an unchanged one asserted without test.

### What `db-003` is not

Two things it is repeatedly confused with:

- **It is not the spatial query.** Finding track discontinuities within N kilometres of an RF anomaly
  zone is `db-004`, and that is the item that justifies using a spatial database at all. `db-003`
  builds the layer such a query will live in; it does not write it.
- **It is not the schema.** That was `db-001`, and it is done. The tables exist and are empty.

### A problem found while re-reading the item

Two pieces of stale cross-reference text, both the pattern named in section 38 — a claim about
something outside the item's own scope, with no test behind it, decaying silently:

1. **`db-003`'s own description is narrower than the work everybody has been calling `db-003`.** It
   describes a *route-handler* constraint: handlers must contain no SQL, no session construction and
   no spatial logic, enforced by a test that greps route modules. That is a real and worthwhile rule,
   but it is a rule about the API layer, and there are no data-serving route handlers yet — the only
   route is `/api/v1/health`. Nothing in the text says "implement `ObservationRepository` against
   PostGIS", which is what the handoff, the thesis notes and every session summary have meant by
   `db-003` for weeks.
2. **`dal-002` still says the PostGIS implementation "lands with `db-001`".** It does not; it lands
   with `db-003`. This is the same conflation corrected in section 34, corrected then in the handoff
   and in `tests/fakes.py`, and missed in the spec line that started it.

### Worth recording as a limitation

Section 38 recorded this decay pattern and offered one mitigation: read the item immediately before
writing its tests. That mitigation worked again here — both problems were caught by reading, before
any test was written. But it has now caught **four** stale claims across three items in two sessions,
which is enough to say the procedural control is load-bearing rather than incidental, and that a spec
file with free-text cross-references between items has no mechanism to keep them true. A machine-
checkable reference format would; the project does not have one, and adopting one mid-build is not
obviously worth the cost. Stated here as a known weakness of the method rather than presented as
rigour.

## 40. Three from reviewing the replay work: is 14.25 s the total, is the atomicity trade-off "keep what worked", and what is the `.env` situation between the container and `build.py`?

### 1. "The 300 s batch is essentially batching the 1 hr data into 12 intervals... all together it took 14.25 s?"

**Yes — that is the total for all twelve.** The hour is cut into twelve five-minute slices; each is
read, validated, pseudonymised and written as one unit; the timer runs across the whole loop.

**But the question prompted a check that corrected something I had asserted without measuring.**
`read_window` cannot push its time filter into the Parquet reader — `iter_batches` takes no
`filters` and the artefact is a single row group — so it walks **the entire file for every window**
and keeps the rows in range. Twelve windows means twelve full scans of 133,634 rows.

That sounds expensive and measurably is not, until it is:

| Window length | Batches | Wall time |
|---|---|---|
| 3600 s | 1 | 13.99 s |
| 900 s | 4 | 12.69 s |
| 300 s | 12 | 13.60 s |
| 60 s | 60 | 23.17 s |

Eleven redundant scans cost nothing detectable, because a full scan is roughly **0.16 s** and is
swamped by per-row DAL work. At sixty batches about nine of the twenty-three seconds are pure
re-reading, which is where the design would start to matter.

Two things follow, and both are corrections rather than additions:

- **Run-to-run variance is about 5 per cent** — 13.60 s and 14.25 s for the same configuration — so
  the honest precision is "about 14 s", not 14.25 s.
- **"Persistence costs 5.8x reading and normalising" was overstated.** The ~2.4 s baseline was taken
  natively on the host against an in-memory store; this figure is a container against an emulated
  PostgreSQL. The backend container runs native `aarch64` and only `postgis` runs emulated `x86_64`,
  so the gap is *mostly* persistence — but it is not a controlled comparison and should not be
  reported as one. A clean measurement would need the same code path in the same container against
  the in-memory repository, which the CLI cannot currently do.

### 2. "Atomicity is all or nothing... but in our case we keep going and keep the operations that work?"

**Yes, and the part worth holding on to is that the boundary is a choice, not a property.**

Atomicity always applies *relative to a unit somebody picked*. Two units are in play here:

| Unit | Guarantee | Holds? |
|---|---|---|
| One batch (one window) | The accepted observations and the quarantine rows commit together or neither | **Yes** |
| One run (twelve batches) | The whole replay commits or none of it does | **No, deliberately** |

The per-batch guarantee is the one `dal-002` actually requires, and it is the one that matters: a
run can never end having stored seven observations while losing the record of the three rejections.
That is the bank-transfer property — debit and credit, or neither.

The per-run guarantee was declined. Wrapping all twelve in one transaction means holding a
133,634-row write open for the length of the replay, and a failure at 99 per cent discards
everything. So batch 7 failing leaves batches 1–6 committed.

**A consequence that was under-thought when this was specified, and is being recorded rather than
discovered later:** nothing cleans up a partial run. The rows already written stay under their
`scenario_runs` row, re-running creates a *new* run rather than resuming, and the database therefore
accumulates partial runs that are indistinguishable from complete ones by inspection. Harmless while
nothing reads runs; actively misleading once detection does. Either replay should mark a run
complete on success — so an unmarked run is visibly partial — or it should delete its own run on
failure. Neither exists. **Worth recording as a limitation:** any count taken over `scenario_runs`
before that is fixed may include partial runs.

### 3. "I still don't understand the env file situation between container and `build.py`"

**Three entrypoints, three behaviours, and the inconsistency is deliberate in one place and was a
bug in another.**

The file is `backend/.env`. It holds `PSEUDONYM_SEED` and is never committed.

| Entrypoint | Reads `.env`? | Why |
|---|---|---|
| `app/main.py` — the server | **No** | Always run through Compose, which supplies the environment itself (§37). |
| `app/corpus/build.py` — corpus CLI | Yes | An operator command, run by hand, natively. |
| `app/replay.py` — replay CLI | Yes | An operator command too — **and the first one ever run inside a container.** |

That last row is where both defects lived.

**The path.** `build.py` locates the file by walking up from its own location to the repository root
and back down to `backend/.env`:

```
backend/app/corpus/build.py  ->  parents[3] = <repo>  ->  <repo>/backend/.env    correct
/app/app/corpus/build.py     ->  parents[3] = /       ->  /backend/.env          does not exist
```

Compose mounts `./backend` as `/app`, so **nothing above `/app` exists** and the walk lands on the
filesystem root. `build.py` carries this defect right now and is unaffected only because it is never
run in a container. `replay.py` was written the same way and broke immediately. It now anchors to
the package rather than the repository:

```
backend/app/replay.py  ->  parents[1] = backend/  ->  backend/.env    correct
/app/app/replay.py     ->  parents[1] = /app      ->  /app/.env       the same file, through the mount
```

**The empty string.** `compose.yaml` passes `PSEUDONYM_SEED: ${PSEUDONYM_SEED}`. When the host shell
does not have it, Compose does not omit the variable — **it sets it to the empty string.** And
`load_dotenv(override=False)` means "do not overwrite variables that are already set", where set
includes set-to-empty. So the file was skipped and the replay failed reporting a missing seed, with
the seed present in a mounted file. The fix removes the variable when it is blank before loading,
because an empty seed is not a seed — which `Pseudonymiser.from_environment` already says one layer
down.

**Worth recording as a limitation:** the two CLIs now behave differently from each other in a way no
test covers — `build.py` still resolves `.env` from the repository root. It works today and will
break the first time anyone containerises the corpus build. The fix is one line and has not been
made, because changing a passing item outside its own spec is how the drift documented in §38 and
§39 starts.

## 41. Why is the detection summary null rather than `Low`, and what does "contract parity in both directions" actually check?

**Two separate things, and the first one is the more important.**

### Null, not `Low`

Four of the six sections in the operational picture have no code behind them: there is no detector,
no radio source and no hypothesis generator. The endpoint still has to return all six, because the
contract says so. The question is what to put in them.

| Option | What it says to an analyst | True? |
|---|---|---|
| `anomalyLevel: "Low"` | The anomaly level was assessed and is low | **No** |
| `anomalyLevel: 0` | Same, with a number attached | **No**, and it breaks `FR-715` too |
| Serve the mock | These are real readings from real sensors | **No** |
| `anomalyLevel: null` | Nothing has assessed this | **Yes** |

`Low` is a claim about the *data*. Null is a claim about the *system*. Only the second one can be
made truthfully right now, so it is the one that is served, and the screen shows a dash.

This is the same move as `db-007`'s completion flag, one day earlier: a value that is right most of
the time was rejected in favour of an absence that is right always. It is worth noticing the pattern
because it will come up again — the same question arises for every section that gets a producer
later than the screen that displays it.

It also made `scenario` nullable, which is what lets an empty database return a valid empty picture
instead of a 500. A screen that cannot render until someone has run a replay is a screen nobody can
develop against.

### Parity in both directions

The shape of the payload is declared twice, in two languages, and nothing checks them against each
other:

```
frontend/src/types/operationalPicture.ts   ← TypeScript, what the screen expects
backend/app/api/v1/schemas/...             ← Pydantic, what the server sends
```

"Both directions" means two failures are caught, not one:

| Change | Without the test | With it |
|---|---|---|
| Field added in TypeScript only | The screen reads `undefined` and renders an empty panel | Parity test fails |
| Field added in Python only | The extra field is silently ignored by the screen | Parity test fails |

The test parses the TypeScript file and compares the **set** of field names per interface against the
Pydantic models' serialised field names. Comparing sets is what makes it symmetric — a subset check
in either direction would catch one failure and miss the other.

Two traps are guarded explicitly. First, it parses rather than searching for text: a search for a
field name is satisfied by a *comment* mentioning it, which is the defect in §38 and one that has now
been hit twice. Second, it **raises rather than skips** when the contract file is not readable —
`frontend/` is not mounted into the backend container by default, and a skipped parity test reports
success over a check that never ran, which is precisely the failure it exists to catch.

Verified by mutation: adding one field to the TypeScript contract and nowhere else turns exactly one
parity case red and leaves the other six green.

**Worth recording as a limitation.** The parity check compares field *names*, not types — with two
exceptions, the detection-summary fields, which are asserted to be non-numeric on both sides because
that is the `FR-715` violation this item removed. A field that becomes a string on one side and stays
a number on the other would still pass. Full type parity would mean generating one side from the
other, which is a larger change than this item justified.


## 42. Can we use TanStack Query for the fetch, or is polling a bad fit for it? And why does the top bar say `unknown` — is the fetch broken?

**Two separate answers: "yes but not yet", and "no, that value is correct".**

### TanStack Query

**Not because polling is a bad fit — polling is the thing it is best at.** `refetchInterval` is
exactly this use case, `placeholderData: keepPreviousData` is the keep-the-last-good rule as one
config line, and it is not a push transport, so `FR-807` is untouched. The reason to hold off is
proportion, not suitability.

| What it would add | Does it bite today? |
|---|---|
| Request dedup across components | No — one screen, one consumer |
| Shared cache | No — nothing else reads the picture |
| Retry with backoff | No — the next poll is five seconds away regardless |
| Pausing polls on a hidden tab | Mildly — a demo left open in a background tab keeps asking |
| Loading and error state as data | No — the hook has two states and both are asserted |

Against that: a runtime dependency, a provider in `main.tsx`, and forty lines of hook whose every
behaviour is already covered by tests and verified in a browser.

**The trigger is written into `docs/implementation.md`**, in the Phase 3 view-filter subsection. That
is where a second polled endpoint arrives (`api-007`), joined by `track-window` in Phase 4
(`api-008`) — two consumers issuing overlapping requests, with a filter selection that must survive
poll ticks. Those are the problems the library exists to solve, and at that point writing it by hand
becomes the wrong call.

The swap is cheap when it comes: `src/lib/api.ts` stays the fetcher, and the existing tests assert
through the screen rather than through the hook, so most of them survive unchanged.

There is also a write-up angle. The dependency list is short and every entry is defensible in one
sentence; "a data-fetching library, for a single endpoint" is a weaker sentence than the hook is.

### Why the top bar says `unknown`

**The fetch is fine.** `unknown` is the value the endpoint is deliberately sending:

```json
{"scenario": {"id": "8", "name": "replay-only", "dataMode": "replayed", "health": "unknown"}}
```

Nothing in the system monitors health yet — not the database, not the adapters, not the replay's
liveness. The mock used to say `Healthy`, which was a reassurance nothing had performed. `unknown` is
the same decision as the two dashes in the Detection Summary, and the same decision as `db-007`'s
blank completion stamp: **absence reported as absence** rather than filled in with something
plausible. See §41.

**But reading it as a fault is a fair reaction, and that is a presentation problem.** The dashes work
because they sit beside labels — "Anomaly Level —" reads as *not assessed*. A bare `unknown` in the
top-right corner, where a health status used to sit, reads as *something broke*. The value is right
and the framing is missing.

Deliberately not fixed here: `op-001` owns that status bar and rebuilds it with a real system-health
strip, and patching one word in a bar that is about to be replaced is the kind of edit that makes a
passing item drift from its spec.

**Worth recording as a limitation of the honest-absence rule:** an absence is only legible when
something explains what is absent. Served without a label, `unknown` and `null` look like failures
rather than statements — which means every place this project chooses to report absence carries a
matching obligation on the interface that displays it.


## 43. Explain `scn-001` in plain English — what are we actually trying to achieve?

**One sentence: a scenario run must be repeatable from a single number, and that number must
actually control what happens.**

### What a scenario is, first

Everything ingested so far is *real* — an archived hour of aircraft broadcasts, replayed. Nothing has
gone wrong in it, because nothing went wrong that Monday over the North Sea. A system whose purpose
is to detect and explain electromagnetic interference cannot be evaluated on an hour in which there
is none.

A **scenario** is a staged incident laid over that real hour. The generator invents synthetic radio
observations — a grid of sensors reporting power on eight channels — and, for some scenario types,
perturbs the aircraft tracks as well. It then writes down exactly what it staged: what was injected,
where, in which channels, and in which window. That written-down record is the **ground truth**, and
it is the only reason any later measurement means anything. Without it, "the detector found an
anomaly" is an anecdote; with it, "the detector found the anomaly that was injected at 12:14 in cell
17, and raised no others" is a measurement.

### What `scn-001` adds on top of that

Staging an incident requires invented numbers: where the interference sits, how strong it is, how
noise varies per sensor, which of the eight channels bleed. Invented numbers come from a random
number generator, and a random number generator is precisely the thing that makes a run
unrepeatable.

`scn-001` says the run must be **fully determined by three inputs** — the scenario type, the
parameters, and an integer seed. Same three in, byte-identical observation stream out. Every time,
on any machine, forever.

### The half people forget

The property is two-sided, and the spec names both failures:

| Failure | Why it is a failure |
|---|---|
| Same type, parameters and seed → **different** output | The run is not repeatable; the ground truth describes something that will never occur again |
| **Different** seeds → **identical** output | The seed controls nothing |

The second one is the trap. A generator that ignores its seed entirely passes the first test
perfectly — it is trivially reproducible, and it is also useless, because a batch of thirty runs
would be thirty copies of one run. Reproducibility on its own is satisfied by a constant.

### What actually breaks it

Three specific things, all named in the item, and none of them look like bugs:

| Leak | How it shows up |
|---|---|
| Wall-clock time | Anything calling "what time is it now" during generation. The run differs by the second it was started, and the difference is invisible until two runs are compared |
| Unseeded randomness | One call to a global random function instead of the run's own seeded generator |
| Process-dependent ordering | Iterating a set, relying on a hash whose seed varies per process, or collecting results from parallel workers in completion order |

The third is the nastiest, because it is not random at all in the ordinary sense — it is stable
within one process and different across two, so it survives every test run in a loop and fails when
someone re-runs the campaign a week later.

### Why the dissertation depends on it

Four reasons, in ascending order of how much trouble their absence causes:

1. **Debugging.** A detection that fails on run 14 can only be investigated if run 14 can be produced
   again.
2. **Ground truth stays true.** The answer key describes a specific stream. If the stream is not
   reproducible, the key describes something that no longer exists.
3. **The generator comparison is otherwise confounded.** The central research question compares a
   template generator against an AI one. If the two arms see even slightly different evidence, the
   comparison measures scenario variation rather than generator quality — and the difference would be
   invisible in the results.
4. **The whole campaign reduces to one number.** `scn-003` derives twenty to thirty run seeds from a
   single base seed. Reproducibility at the run level means the entire evaluation is repeatable from
   one integer written in the write-up, which is the difference between a claim an examiner can
   check and one they must take on trust.

The constraint that the seed is **recorded even when it was generated automatically** exists for the
same reason. A run nobody chose a seed for is a run that can never be repeated unless the seed it
happened to use was written down at the time.

### An ordering problem worth resolving before starting

`scn-001` is a property, not a feature: it has no output of its own. Proving "same seed, same stream"
requires a stream, and the stream comes from the scenario types (`scn-002`), which emit through the
synthetic RF adapter (`adp-002`), which reports on a sensor and channel grid that does not exist yet
(`scn-005`).

`normal-baseline` cannot stand in as the minimal case either: it injects nothing by definition — that
is what makes it the false-positive control — so determinism over it is nearly vacuous.

The practical readings are: build `scn-005` first, since a fixed sensor and channel layout is pure
configuration with no randomness in it and nothing else can emit until it exists; then land `scn-001`
together with the smallest seeded emitter that actually has randomness to be deterministic about.
Recorded here because building `scn-001` "first" in the order the identifiers suggest would mean
building a determinism harness with nothing to be deterministic about.


## 44. What is `scn-005` actually fixing, and why does the sensor layout need a radius attached to it?

**It fixes the part of the synthetic RF world that never varies** — which sensors exist, where they
stand, which channels they listen on, and how often they report. Everything that changes between runs
belongs to `scn-002`. The radius is attached because without one, the requirement that gives the
layout its shape cannot be checked at all.

### The two halves of the layout

| | What it fixes | Why it is fixed rather than generated |
|---|---|---|
| **Sensors** | Seven ground stations, each at a recorded latitude and longitude | Detectors reason about *which* sensors saw something. If positions moved between runs, two runs would not be comparable, and the evaluation campaign compares runs. |
| **Channels** | Eight slices of radio spectrum, each 2 MHz wide, centred 1567.42 → 1581.42 MHz | The channel axis is what lets a rule say "the noise is confined to one channel" instead of only "this sensor is noisy" — the difference between a sensor fault and an emitter. |

Every sensor reports on every channel at every interval, ten seconds apart in simulated time. That
density is deliberate: with a complete grid, a *missing* reading is a detectable gap, whereas on a
sparse grid a genuine dropout and a sensor with nothing to report look identical.

### The requirement that could not be checked as written

`FR-109` says sensor positions must be chosen "so that a candidate interference zone contains some
sensors and excludes others". That sentence describes an intention, and a program cannot evaluate it:
it names no distance and no threshold, so **any** set of positions satisfies it.

The wrong assumption worth naming is that this is a note to the author — something to keep in mind
while placing sensors. It is not. It is the precondition for two detection rules meaning anything:

- `anom-007` decides "this one sensor is faulty" by checking that its **neighbours stayed nominal**. A
  sensor with no neighbours has nothing to check, and the rule quietly becomes "this sensor is
  abnormal", which is what it was supposed to improve on.
- `anom-005` fuses radio noise with aircraft track gaps only when both fall **in the same area**. If
  every sensor is inside every plausible area, that condition is always true and adds no information.

So the requirement became two rules, tested at a stated radius, and checked when the layout file is
read rather than when a detector runs:

1. every sensor has **at least one other sensor within** the radius;
2. every sensor has **at least one other sensor beyond** it.

They point in opposite directions on purpose. The first forbids a layout spread too thin, the second
one packed too tight, and passing both means the layout has internal structure for a spatial rule to
find.

### Why the radius has a range, and why the middle of it was chosen

The shipped layout is seven Dutch and German airfield positions inside the corpus bounding box. Their
distances, in kilometres:

| From | Nearest neighbour | Next nearest |
|---|---|---|
| Schiphol | Rotterdam, 45.3 | Lelystad, 54.1 |
| Rotterdam | Schiphol, 45.3 | Eindhoven, 85.7 |
| Lelystad | Schiphol, 54.1 | Rotterdam, 93.0 |
| Eindhoven | Weeze, 55.7 | Rotterdam, 85.7 |
| Weeze | Düsseldorf, 55.5 | Eindhoven, 55.7 |
| Düsseldorf | Köln/Bonn, 53.9 | Weeze, 55.5 |
| Köln/Bonn | Düsseldorf, 53.9 | Weeze, 107.5 |

Read the two invariants off that table and a **band** falls out rather than a single value. Below
**55.7 km**, Eindhoven has no neighbour and rule 1 fails. At **85.7 km**, Rotterdam and Eindhoven
become neighbours and the layout starts collapsing toward everything-sees-everything. So both rules
hold for any radius in **[55.7, 85.7) km**, and for no radius outside it.

The configured value is **70 km** — near the middle, not at an edge. The reason is robustness rather
than realism: at 56 km the property would be true and one small position edit from being false, and
nothing would announce the change. Fourteen kilometres of margin on each side means a later
adjustment has to be substantial before it breaks anything, and if it does, the layout is rejected
when it loads instead of producing quiet nonsense six phases later.

### A correction to the specification, recorded because the arithmetic was wrong

Both `scn-005` and `docs/em_fusion_v2.md` §5 described the plan as "one channel on L1 with four
either side". Four either side plus L1 is nine channels; the plan has eight. The frequency list was
right and the sentence was wrong: L1 sits at index 4, with **four channels below and three above**.

The point the sentence was reaching for survives and is now enforced directly. L1 must not be at
either end of the plan, so that frequency adjacency runs in **both** directions from it — a channel
at the edge would give `anom-007` a one-sided neighbour test, and "the adjacent channels were clean"
would be half a claim.

Worth recording as a limitation: this channel plan is a *plausible abstraction, not an RF-accurate
channelisation*. The real GPS L1 band is considerably wider than 16 MHz, and no real receiver
channelises it this way. Eight channels is the smallest grid that supports the adjacency reasoning
the detection rules need, and no claim is made that a result here transfers to a real spectrum
monitor.

## 45. I'm struggling to wrap my head around the receivers and their relationship with the channels — "four above and three below", "adjacent channels", the "distance window". Can this be explained better?

**The thing that makes it hard is that "next to" is being used for two entirely separate
relationships, and §44 used the word for both without ever saying so.** There is a *pitch* axis and a
*distance* axis. They are independent, they carry different evidence, and the design's whole trick is
that the same question is asked along each. Once they are separated the rest is arithmetic.

### The wrong picture to have

The natural reading of "seven sensors, eight channels" is that these are two halves of one structure —
that a channel is something a sensor *has*, the way a room has a door, and that "adjacent" therefore
means something like "the sensor next door". It does not. A better mental model:

> Each of the seven receivers independently produces **eight numbers** every ten seconds. That is a
> 7 × 8 grid of numbers at every instant. "Adjacent" can mean *along the row* (slices on one
> receiver) or *down the column* (receivers on one slice), and those are different tests.

### What a receiver is, before anything else

**A meter, not an ear.** It decodes nothing and listens to no conversation. It measures how much
radio energy is arriving and reports the number. Frequency is the "pitch" of a radio wave, in MHz;
different services sit at different pitches, which is how they coexist. Satellite navigation sits at
**1575.42 MHz**.

The one design decision everything else rests on: rather than report a single loudness figure for
everything it can hear, the receiver splits its range into eight narrow bands and reports **eight
numbers**. A single figure could only ever say "it is noisy here". Eight can say *where in the band*
the noise is — and the shape of that answer is the evidence.

### Why the shape is evidence

| Pattern across the eight slices | What it means |
|---|---|
| All eight roughly level | Background hiss. Nothing to say. |
| One slice up, the two either side untouched | **Physically odd.** Anything really radiating spills into neighbouring slices. Far more easily explained by the meter reporting a wrong number for one slice — so suspect the *receiver*. |
| A slice up with its neighbours also raised, tapering outwards | What an actual emission looks like — so suspect the *world*. |

Now the same logic, one axis over: if one receiver is hot and the receivers near it are quiet, that
is again the instrument; if several nearby receivers are hot together, something is really happening
out there.

### The two axes side by side

| | Pitch axis | Distance axis |
|---|---|---|
| What is compared | Eight slices on **one** receiver | Seven receivers on **one** slice |
| "Next to" means | The slice immediately above or below | Any receiver within 70 km |
| Isolated reading | One slice hot, its two neighbours quiet | One receiver hot, its nearby receivers quiet |
| → so probably | The instrument is at fault | The instrument is at fault |
| Shared reading | Several adjacent slices raised | Several nearby receivers raised |
| → so probably | Something is really transmitting | Something out there is really happening |

Two independent pieces of evidence with identical logic. Agreeing, they make a far stronger case than
either alone; **disagreeing, they are the kind of ambiguity an analyst should be shown rather than
have resolved for them** — which is the point of the whole system.

The asymmetry between the two columns is worth naming. The pitch-axis neighbours are fixed by the
channel plan and never change. The distance-axis neighbours depend entirely on where the receivers
were put — which is why positions had to be *chosen and measured* rather than scattered, and why the
distance window exists at all. §44 covers that measurement.

### "Four below and three above" is counting, not a choice

The plan has eight slices, and 1575.42 MHz has to be the centre of one of them. That uses one slice
and leaves seven, which fall four below and three above. Seven does not split evenly. There is
nothing to be done about it short of using nine slices.

**The number on each side was never the requirement**, which is why the earlier "four either side"
wording went unnoticed for so long — it was describing a decision nobody had actually made. The
requirement is that there is **at least one slice on each side**, so "did its neighbours see it too?"
can be asked in both directions. Put the navigation frequency at the very *edge* of the plan and it
has a neighbour on one side only: the check still runs, still reports success, and is now silently
answering half the question. That is the failure the layout validation exists to make impossible.

### Worth recording as a limitation

This channel plan is **a plausible abstraction, not an RF-accurate channelisation**. The real GPS L1
band is far wider than 16 MHz and no real receiver divides it this way. Eight slices is the smallest
grid that supports the adjacency reasoning above, and no claim is made that a result obtained here
transfers to a real spectrum monitor. The same caveat applies to the noise-spills-sideways argument:
it is true of real emissions in general, but the *degree* of spill is a property of the transmitter
and is here a parameter we choose rather than a measured fact.

## 46. This is the ethics form I have to complete. I am not doing a human study, however I will eventually have a human rater using the scoring rubric to rate evaluations from the two generators — at most two participants, work colleagues, no personal information collected except the score. How should I approach filling it out?

**No — it *is* a human study, and the form has to be answered as one.** That is the correction, and
everything else follows from it. The instinct behind "I am not doing a human study" is sound: nothing
personal is collected, nobody is being measured, the ratings are an instrument pointed at software
rather than at a person. All of that is true and none of it is the test.

### The distinction being conflated

Two separate things were being treated as one:

| | What it is | What triggers it |
|---|---|---|
| **Personal data processing** | Holding information that identifies a living person | Collecting names, contact details, demographics, anything attributable |
| **Human-participant research** | Recruiting a person to take part in a designed procedure and using what they produce as evidence | Asking someone to do something for your study |

A study can be one without the other, and this project is exactly that case: **heavy on
human participation, almost empty of personal data.** The ethics form asks the second question. "No
personal information except the score" answers the first and says nothing about the second.

### Why the rating exercise crosses the line

Four features, any one of which would be enough:

1. **Recruitment.** A person is approached and asked to take part. Not observed incidentally, not
   already producing the data for other reasons — approached, for the study.
2. **A designed procedure.** They follow a protocol fixed in advance: a rubric, a calibration round,
   two passes in a required order, with information deliberately withheld between them.
3. **Data they generate is the evidence.** Their judgements are not a by-product; roughly 280 values
   from one person become a headline result.
4. **A statistic about the humans.** Inter-rater agreement — quadratic-weighted Cohen's κ — measures
   *how closely two people agreed with each other*. It is not possible to report a statistic whose
   subject is a pair of humans and simultaneously claim no humans were studied.

The fourth is the one that settles it and the one easiest to miss, because κ feels like a property of
the instrument. It is computed *from* people.

### What changed since the proposal said otherwise

`proposal_draft.md` TOR 9 states plainly: *"The project collects no data from human participants."*
That was written when the second rater was expected to be the **supervisor**, where the rating plausibly
reads as supervision of a student's own work rather than participation in it. TOR 9's last sentence
already anticipated the alternative — *"Should the rater be a colleague rather than my supervisor,
participation will be genuinely voluntary…"* — without following the consequence through. Moving from
supervisor to colleague is what moved the study across the boundary. This is a reversal to declare,
not to paper over; it is recorded in `thesis_notes.md` under Methodology.

### The asymmetry, which is the actual argument

Ethics declarations are not a judgement call to be optimised. Compare the two errors:

| | Cost of being wrong |
|---|---|
| **Declare YES, didn't need to** | One information sheet, one consent form, one supervisor signature. All drafted. |
| **Declare NO, needed YES** | Page 1 of the form: *"risks a notable deduction in your grade and may risk a case of Academic misconduct."* |

There is no reading where NO is cheaper. And YES here does **not** mean a full committee application
with its four-to-eight-week wait — this remains inside **module-level approval**: competent adults, no
vulnerable groups, no special-category data, no deception, no physical intervention, voluntary, with a
right to withdraw. It is the low-risk form, correctly completed.

### The two things that genuinely need care

Not the data — the data is trivial. These:

**The colleague relationship.** Recruiting from your own workplace introduces perceived obligation
even where none is intended. Mitigations, all in the drafted material: exclude anyone in a
line-management relationship in *either* direction; approach once and do not follow up; state
explicitly in writing that declining carries no consequence and will not be raised again.

**Identifiability by elimination.** With two raters and one of them the author, "Rater 2" is
identifiable to anyone who knows who was asked. Pseudonymising the score sheet does not fix this and
at N=2 nothing can. The honest handling is to disclose it to the participant *before* they consent
rather than to claim an anonymity the design cannot deliver, and to constrain the reporting: "an
independent second rater," no name, no employer, no comment on how they scored.

### Worth recording as a limitation

Two, both already carried in `scoring_rubric.md` Part B and both now with an ethics dimension as well.
Small N is driven by the second rater's available time, which is a *participant burden* constraint,
not merely a statistical one — the corpus was sized to what a person could reasonably be asked to do.
And the blinding is imperfect by acknowledgement: the participant is told, in the information sheet,
that arm identity is withheld until debrief, which is disclosure of withholding rather than deception,
but the residual threat to the comparison stands either way.

Draft answers for every field of the form, plus a participant information sheet, consent form, and
recruitment email, are in `docs/ethics_form_answers.md`. Six decisions are still owed before it can be
signed — most importantly whether one colleague scores or two, since a third rater invalidates Cohen's
κ and would require a change-log entry against the pre-registered rubric.

## 47. When you say 5 dimensions, what do you mean?

**Five separate things each hypothesis gets scored on, each rated 1–5 on its own.** Not five questions
in a questionnaire and not five steps in a process — "dimension" is the rating-scale term for an
independent axis of judgement. One hypothesis comes out of the first pass carrying five numbers, not
one.

| # | Dimension | The question it asks |
|---|---|---|
| 1 | **Evidence use** | Does it reason *from* the evidence, or just repeat it back? |
| 2 | **Uncertainty** | Is it honest about what it doesn't know, and does it say what difference that makes? |
| 3 | **Alternative explanations** | Does it offer genuine competing possibilities, and say what would tell them apart? |
| 4 | **Recommended action** | Could an analyst actually act on it, or is it "investigate further"? |
| 5 | **Overall usefulness** | Would this help someone working under time pressure? |

Each has worded anchors at the 1, 3 and 5 points in `docs/scoring_rubric.md` Part A; 2 and 4 are for
anything in between.

### Why five rather than one overall score

Because "is this hypothesis any good" is unanswerable as a single number, and because each dimension
is tied to a specific claim the thesis makes. Four of the five map one-to-one onto fields of the
hypothesis output schema:

| Dimension | Schema field |
|---|---|
| Evidence use | `supporting_evidence` |
| Uncertainty | `evidence_against_or_uncertainty` |
| Alternatives | `alternative_explanations` |
| Actionability | `recommended_human_action` |
| Overall usefulness | the whole output |

The separation is what makes the comparison informative. If the AI arm beats the template on
alternatives but not on actionability, that is a finding about *where* constrained generation helps.
Collapsed into a single score it is not a finding at all, just a number that moved.

### Dimension 1 is the one carrying the research argument

It exists because of a gap nothing automated can close. After the grounding gate, every hypothesis
reaching a scorer is 100% schema-valid and 100% grounded on **both** arms — that is what constrained
decoding plus a grounding check mean, and it is why neither metric can separate the arms. The
grounding check proves a cited rule ID *exists in the evidence pack*. It cannot establish that the
finding was used *meaningfully*. Dimension 1 is precisely that gap, and it is the reason RQ3 needs
human judgement rather than more automation. See §7.

### Dimension 5 is not an average of the other four

The rubric tells the rater explicitly that if their overall judgement disagrees with the four
component scores, they should leave it disagreeing. It is there to catch a hypothesis that scores
respectably part-by-part and is useless taken as a whole — an output that ticks every structural box
without advancing the analyst's reasoning.

### What the anchors look like in practice

The worked example in Part A scores two hypotheses built from the same evidence pack:

| Dimension | A | B |
|---|---|---|
| Evidence use | 2 | 5 |
| Uncertainty | 1 | 5 |
| Alternatives | 2 | 5 |
| Actionability | 1 | 5 |
| Overall usefulness | 2 | 5 |

**A is not wrong.** Every claim it makes is accurate and every rule ID it cites is real. It scores low
because it lists the findings without connecting them, copies the pack's uncertainties without saying
what they do to the conclusion, names two undifferentiated alternatives, and recommends "review the
affected area". Accuracy is not usefulness — which is exactly why the instrument has dimensions rather
than a single correctness check.

### Where the "280 values" figure in the ethics form comes from

```
5 dimensions × 40 items   = 200   (pass 1, ordinal 1-5)
2 judgements × 40 items   =  80   (pass 2, categorical)
                            ---
                            280   values from one rater
```

The two pass-2 judgements are **cause correctness** (correct / partly correct / incorrect) and
**confidence calibration** (too low / about right / too high). They are categorical rather than 1–5,
and they are collected only after every item has been scored on all five dimensions, because knowing
the right answer changes how good an explanation feels. Reported as counts, not means.

### Note the vocabulary trap

"Dimension" is doing rating-scale work here and has nothing to do with dimensionality in the
data-science sense — no feature space, no reduction, no orthogonality claim. The five are not assumed
independent of one another and are expected to correlate; each is reported separately, and no
composite score is computed from them at any point.

## Appendix: quick glossary

| Term | Short definition |
|---|---|
| **State vector** | One tracked object's complete state (position, velocity, attributes) at one instant; one row. |
| **Track** | The time-ordered sequence of state vectors sharing an `icao24` — an aircraft's trajectory. |
| **`icao24`** | Unique 24-bit transponder address identifying an aircraft; the track identity key. |
| **Position staleness** | `time − lastposupdate`: how long since a fresh position was actually received. |
| **GNSS** | Global Navigation Satellite System — the general term (GPS, Galileo, GLONASS, BeiDou). |
| **GNSS L1** | The 1575.42 MHz band carrying civil GPS/Galileo signals; the band the interference scenario targets. |
| **SNR** | Signal-to-noise ratio — signal strength relative to background noise. Falls when noise rises. |
| **Noise floor** | Background RF power with no signal present; the reference that "elevated noise" is elevated above. |
| **Human-participant research** | Research in which a person is recruited into a designed procedure and what they produce is used as evidence — independent of whether personal data is collected. |
| **Module-level ethics approval** | A blanket departmental approval covering low-risk student projects; a short form plus supervisor sign-off, rather than a full committee application. |
| **Pseudonymous** | Identifiers replaced by a code, with the mapping held separately. Not the same as anonymous: re-identification remains possible while the mapping exists. |
| **Dimension** (scoring) | One independent axis of judgement on the rating instrument, scored 1–5 on its own. Five per hypothesis; no composite is computed. |
| **Anchor** (scoring) | The written description of what a given score means on a dimension. This rubric words the 1, 3 and 5 points and leaves 2 and 4 for anything in between. |
| **dBm** | Power in decibels relative to 1 milliwatt. Logarithmic; +10 dB is 10× the power. Less negative = stronger. |
| **Baseline delta** | An observation's deviation from its expected normal value — the quantity detectors act on. |
| **Seed** | The pseudo-random generator's starting value; makes a "random" run exactly repeatable. |
| **Ground truth** | What the generator actually injected — the known-correct answer detection is scored against. |
| **Atomicity** | A set of operations commits together or not at all — always relative to a chosen unit. Here: per batch, not per run. |
| **EWKT** | Extended Well-Known Text: a text form for a geometry that carries its SRID with it, e.g. `SRID=4326;POINT(7.5473 51.0905)`. |
| **SRID** | Spatial Reference System Identifier — which model of the earth a coordinate refers to. 4326 is WGS 84, what GPS reports. |
| **Precision / recall** | Precision: of the anomalies flagged, how many were real. Recall: of the real anomalies, how many were flagged. |
| **False positive** | Flagging an anomaly that was not injected. The `Normal baseline` scenario exists to measure this. |
| **Detection latency** | Simulated time from event onset to anomaly emission — never wall clock. |
| **Bounding box** | A lat/lon rectangle used as a geographic filter; also how spatial indexes pre-filter internally. |
| **SRID 4326** | WGS84 — the lat/lon coordinate system used by GPS and OpenSky. |
| **GiST** | The PostgreSQL index type PostGIS uses for spatial columns. |
| **Evidence bundle** | The structured, traceable anomaly summary that is the *only* input the AI layer sees. |
| **DBAPI (PEP 249)** | Python's standard database-driver interface. psycopg implements it; SQLAlchemy programs against it. |
| **Dialect** | SQLAlchemy's knowledge of one database's SQL flavour. `postgresql+psycopg` = dialect + driver. |
| **Connection pool** | Reusable open connections held by the Engine. Exists because a new PostgreSQL connection costs a handshake and a forked server process. |
| **Unit of work** | The ORM tracking which loaded objects changed and emitting the matching `UPDATE`s at flush time. |
| **Identity map** | The ORM's guarantee of one Python object per database row within a session. |
| **GeoAlchemy2** | The library that teaches SQLAlchemy about PostGIS geometry types. SQLAlchemy alone can call `ST_*` functions but does not know the column types. |
| **PGDATA** | Postgres's internal data directory. Belongs in a named volume, not a bind mount inside a directory used for anything else. |
| **Image platform** | The CPU architecture an image was built for. `platform: linux/amd64` runs an amd64 image emulated on arm64; it is real, just slower. |
| **Rosetta / QEMU** | The two emulation backends Docker Desktop can use for cross-architecture images. Rosetta is much faster and is a Docker Desktop setting. |
| **C4 model** | Four nested levels of architecture diagram — Context, Containers, Components, Code — each zooming into one box of the level above. |
| **Structurizr DSL** | A text format for writing a C4 model, so diagrams are generated from a diffable source rather than drawn by hand. |
| **Bind mount** | Docker's `-v host_path:container_path`; exposes a host directory inside the container. Docker creates a missing host path rather than failing. |
| **Seam** | An interface deliberately placed so one implementation can be swapped for another without touching callers — here, the DAL and the hypothesis service. |
| **Migration** | A versioned, ordered schema change applied to a database. The unit in which a schema evolves without being rebuilt from empty. |
| **Alembic** | SQLAlchemy's migration tool. Keeps an `alembic_version` table in the database recording which revisions have been applied. |
| **Autogenerate** | Alembic's diff of models against the live schema. Off here: it does not understand PostGIS geometry columns. |
| **Lifespan hook** | FastAPI's startup/shutdown context manager. Where a process-wide resource such as the Engine is created once and disposed. |
| **`sessionmaker`** | A factory bound to one Engine that produces Sessions. One per process; one Session per request. |
| **`lru_cache`** | Memoises a function's return per distinct argument tuple. A singleton is a different thing: one instance regardless of arguments. |
| **`load_dotenv`** | Reads a `.env` file into the process environment. Does nothing unless something calls it — it is not automatic. |
| **Basemap** | The background map — coastlines, roads, terrain, labels — that overlays are drawn on top of. Separate from the map library that renders it. |
| **Tile** | One square piece of a basemap, addressed by zoom/x/y. Maps are fetched a tile at a time as you pan. |
| **Raster tile** | A pre-rendered image tile. Styling is fixed at render time by whoever produced it. |
| **Vector tile** | Geometry and attributes (MVT/protobuf) styled by the client at draw time, so the same tiles can look any way you choose. |
| **PMTiles** | A whole tile set in one file, read by the browser via HTTP range requests — self-hosting with no tile-server process. |
| **ODbL** | The Open Database Licence covering OpenStreetMap data; requires attribution on the map. |
| **Glyphs / sprites** | The font and icon assets a vector style references by URL. Easy to leave pointing at a CDN by accident. |
| **Grounding check** | Verifying every claim in a generated hypothesis traces back to the evidence bundle. |
| **Constrained decoding** | Restricting generation to a grammar so invalid output is unrepresentable, not merely detectable. |
| **Arm** | One hypothesis generator treated as a condition in the evaluation. Two are scored — `hosted` and `template`; `local` runs as a fallback but is not scored. |
| **Evidence bundle** *(as a scoring unit)* | The sampling unit for blind scoring. ~20 are drawn, stratified across the four anomalous scenario types. |
| **Scored item** | One hypothesis — one bundle through one arm. 20 bundles × 2 arms = 40 items. |
| **Stratified sample** | A sample drawn deliberately from each subgroup, so no scenario type is accidentally absent from the comparison. |
| **Paired comparison** | Scoring both arms on the *same* bundle, so bundle difficulty cancels out of the arm difference. |
| **Blind scoring** | Rating output without knowing which arm produced it; the arm key is held in a separate file until scores are ingested. |
| **Rubric** | The fixed scoring instrument — dimensions plus worded 1/3/5 anchors. Lives in `docs/scoring_rubric.md`. |
| **Pre-registration** | Committing the rubric before the campaign runs and citing the commit hash, so the instrument demonstrably predates the results. |
| **Inter-rater agreement** | How closely two independent raters coincide. Reported as quadratic-weighted Cohen's κ, which penalises far-apart disagreements more than adjacent ones. |
| **Adjudication rule** | The pre-agreed procedure for handling rater disagreement — here, mean for analysis, discussion where scorers differ by ≥2. |
| **Calibration round** | A few shared items scored and discussed before independent scoring begins, to align interpretation of the anchors. |
| **Channel** | One 2 MHz slice of the RF grid. Eight of them, centred 1567.42–1581.42 MHz, with one centred exactly on GNSS L1. |
| **Frequency adjacency** | Neighbouring channels on the same sensor. A real emission raises them together, so an isolated single-channel deviation is evidence about the instrument. |
| **Sensor × channel × time grid** | The fixed shape of RF output: every sensor reports every channel every interval, so a missing reading is a detectable gap rather than an ambiguous absence. |
| **Narrowband / broadband** | Spectral extent of injected interference — one channel or the whole grid. A *parameter* of `gnss-degradation`, never a separate scenario type. |
| **Dense grid** | Emitting a reading even when there is nothing to report, so absence carries information. |
| **Parquet** | Columnar, typed, compressed file format. Used here for the archived aviation extract only — never as a read path, which stays PostGIS. |
| **Read path** | Where queries actually run. Distinguishing it from *archive format* is what keeps the rejected lakehouse decision rejected. |
| **Contract mirror** | A backend endpoint returning the frontend's expected shape from a static fixture, to establish the API seam before real data exists. |
| **Compose profile** | A tag that keeps a service out of `docker compose up` unless explicitly requested. Profiling every service means `up` starts nothing. |
| **Build target (`target:`)** | Which stage of a multi-stage Dockerfile to build. Used here to give the backend a `dev` image with pytest/mypy and a lean `runtime` image without. |
| **Smoke test** | A post-start check that the deployed pieces can reach *each other*, not just that each responds. The frontend→backend proxy hop is the part unit tests cannot cover. |
| **`EXPOSE`** | Dockerfile metadata declaring the intended port. Documentation only — it grants no access and blocks none. |
| **Privileged port** | Any port below 1024. Binding one requires root or `CAP_NET_BIND_SERVICE`, which is why a non-root container must listen on 8080 rather than 80. |
| **Lifespan** | FastAPI's startup/shutdown context manager, yielding once between the two phases. Replaces the deprecated `on_event` handlers. |
| **`proxy_pass` trailing slash** | In nginx, a trailing slash strips the matched location prefix before forwarding; without it the full path passes through. One character, two different backend routes. |
| **Coverage acceptance check** | A pre-build check that the chosen bounding box has dense enough OpenSky sensor coverage that *genuine* dropouts will not be mistaken for injected ones. Validates the region, not the code. |
| **Pseudonymisation** | Replacing an identifier with a stable substitute that carries no source information. Distinct from anonymisation: identity is preserved across records, only its link to the real subject is severed — which is what keeps track continuity intact. |
| **`icao24`** | The 24-bit ICAO transponder address, six hex digits, fixed to an airframe across flights. An aircraft identifier under OpenSky DLA §3(i), so it never leaves the DAL unpseudonymised. |
| **Manifest** | The record accompanying the archived extract — source URL, hour, download date, licence, checksum of the original. What makes a filtered extract reproducible without redistributing the full source file. |
| **Temp-then-move** | Writing a download to a temporary path and renaming it into place only once verified. An interrupted run then leaves nothing a later run could mistake for a complete file. |
| **Licence acceptance gate** | An explicit operator act required before the fetcher opens a socket. Not a check against the manifest — the manifest records the licence, the gate makes a human accept it. |
| **Interior gap** | A dropout with both endpoints well inside the bounding box and the aircraft airborne on both sides. The only kind that measures sensor coverage; the rest measure box geometry. |
| **Event site** | A ~20 km cell carrying enough simultaneous traffic (≥ 5 distinct aircraft) for a localised injected event to have witnesses. The count of these, not coverage quality, is what the bounding box was chosen on. |
| **Repository port** | The interface a caller depends on to persist or read records, defined independently of the storage engine behind it. Required by `db-003` regardless of build order, which is why defining it before the database exists adds a second implementation rather than a second layer. |
| **In-memory fake** | A working implementation of a port backed by plain data structures, used so unit tests need no database. Distinct from a mock: it has real behaviour and can be asserted against, rather than merely recording calls. |
| **Unit of work** | An explicit boundary declaring that several writes commit or fail together. Invisible against an in-memory fake, where appending to two lists is trivially atomic, and required against PostgreSQL for `dal-002`'s split of a batch into observations and quarantine rows. |
| **Seed vs salt** | A salt need not be secret because the input space resists enumeration; a seed over a small input space is a *key*, and publishing it reverses the mapping. `icao24` is 24 bits, which is why the pseudonymisation seed is a key. |
| **Seed fingerprint** | The SHA-256 of the pseudonymisation seed, recorded in the committed manifest in place of the seed. Identifies which seed built a corpus without disclosing it. |
| **Namespace separation** | Mixing the field name into the hashed message so two identifier spaces stay independent — an `icao24` and a callsign sharing text cannot collide onto one pseudonym. |
| **Scenario seed** | An integer initialising a pseudo-random generator, drawn per run and published so a run can be reproduced. The opposite of the pseudonymisation seed in every respect except the name. |
| **Pseudonymisation seed** | A secret HMAC key, fixed once per corpus and never published. Involves no randomness; "seed" is conventional here and misleading. |
| **HMAC** | A keyed hash: the output depends on both the message and a secret key, so it cannot be recomputed by someone holding only the message. |
| **Stale image** | A container image built before a dependency change. With source bind-mounted but `site-packages` baked in, it runs current code against outdated libraries — and reports confidently about an environment that exists nowhere else. |
| **Source record** | The mapping an adapter emits: source and observation type, timestamp, location, and a source-shaped payload still carrying real identifiers. Not a canonical observation — it has no provenance, no validation status, and no pseudonyms, all of which the DAL adds. |
| **Dialect translation** | The whole of an adapter's job: renaming a source's columns onto source-record keys, handling units, computing directly measured derived fields. Explicitly not cleaning, enriching, or de-identifying, all of which belong to the DAL. |
| **Provenance vs identity** | Provenance says where a record came from and under which run (`source_id`, `source_type`, `data_mode`, `scenario_run_id`); identity says which aircraft it is. Separate fields, separate obligations — RF observations carry the first and have none of the second. |
| **In-file schema** | The column names and types Parquet stores inside the artefact. It makes a reader independent of the writer's code: the file is asked, not a shared constant, so the two cannot drift apart. |
| **Predicate pushdown** | Filtering rows inside the storage reader rather than after loading them. Unavailable for this extract — `iter_batches` takes no `filters` and the file is one row group — so the replay window is applied per batch in Python. |
| **Half-open interval** | `[start, end)` — start included, end excluded. The only convention under which adjacent replay windows tile the timeline exactly once; closed intervals double-count the boundary frame and open ones manufacture a dropout at it. |
| **Position staleness** | `time - lastposupdate`: the age of the coordinate inside a state vector row. Not the age of the row, which is emitted on a fixed cadence regardless, and not the interval since the aircraft was last heard from. |
| **Contact staleness** | `time - lastcontact`: the interval since any message was received from the aircraft. Capped near 300 s by OpenSky's own drop timeout, whereas position staleness is uncapped — which is what makes the difference between them a usable discriminator. |
| **Inter-sample gap** | The interval between consecutive rows for one `icao24`. What `coverage.json` measures, and a different axis from staleness: between rows rather than within one. |
| **Contract parity** | Two declarations of one payload shape — the TypeScript type and the Pydantic models — checked against each other by a test, because no compiler spans both languages. Symmetric: a field added on either side alone fails. See §41. |
| **Level** | The Low / Medium / High vocabulary every confidence, severity and score is expressed in (`FR-715`, `AC-11`). Never a percentage and never a decimal, so that a generated judgement cannot be mistaken for a measurement. |
| **Scenario** | A staged incident laid over the replayed real hour: synthetic radio observations, and for some types perturbed tracks, plus a written record of exactly what was staged. See §43. |
| **Ground truth** | The generator's own record of what it injected — where, in which channels, in which window. Recorded at generation time and never inferred from detector output, which is what makes a detection measurable rather than anecdotal. Never leaves the run record (`api-009`). |
| **Layout** | The fixed geometry of the synthetic RF side: which sensors exist, where, and on which channels. Configuration read from a file and validated on load, not constants in the code (`scn-005`). See §44. |
| **Pitch axis / distance axis** | The two independent senses of "next to": slices adjacent in frequency on one receiver, and receivers within the radius of each other. Same reasoning applied along each. See §45. |
| **Channel** | One 2 MHz slice of the monitored spectrum, identified by an index. Eight of them, centred 1567.42–1581.42 MHz. The axis that lets a rule distinguish noise confined to one channel from noise smeared across the band. |
| **GNSS L1** | 1575.42 MHz, the civil GPS signal frequency. One channel is centred exactly on it, with four below and three above, and it is the band the `gnss-degradation` scenario targets. |
| **Discrimination radius** | The distance at which a layout is asserted to be discriminating: every sensor has at least one other within it and at least one beyond it. 70 km, chosen from a measured valid band of [55.7, 85.7) km. See §44. |
| **Seed** | The integer that determines every invented number in a run. Same type, parameters and seed must give a byte-identical stream; different seeds must not. Always recorded, including when generated automatically. |
