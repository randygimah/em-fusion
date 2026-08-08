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
| **dBm** | Power in decibels relative to 1 milliwatt. Logarithmic; +10 dB is 10× the power. Less negative = stronger. |
| **Baseline delta** | An observation's deviation from its expected normal value — the quantity detectors act on. |
| **Seed** | The pseudo-random generator's starting value; makes a "random" run exactly repeatable. |
| **Ground truth** | What the generator actually injected — the known-correct answer detection is scored against. |
| **Precision / recall** | Precision: of the anomalies flagged, how many were real. Recall: of the real anomalies, how many were flagged. |
| **False positive** | Flagging an anomaly that was not injected. The `Normal baseline` scenario exists to measure this. |
| **Detection latency** | Simulated time from event onset to anomaly emission — never wall clock. |
| **Bounding box** | A lat/lon rectangle used as a geographic filter; also how spatial indexes pre-filter internally. |
| **SRID 4326** | WGS84 — the lat/lon coordinate system used by GPS and OpenSky. |
| **GiST** | The PostgreSQL index type PostGIS uses for spatial columns. |
| **Evidence bundle** | The structured, traceable anomaly summary that is the *only* input the AI layer sees. |
| **C4 model** | Four nested levels of architecture diagram — Context, Containers, Components, Code — each zooming into one box of the level above. |
| **Structurizr DSL** | A text format for writing a C4 model, so diagrams are generated from a diffable source rather than drawn by hand. |
| **Bind mount** | Docker's `-v host_path:container_path`; exposes a host directory inside the container. Docker creates a missing host path rather than failing. |
| **Seam** | An interface deliberately placed so one implementation can be swapped for another without touching callers — here, the DAL and the hypothesis service. |
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
