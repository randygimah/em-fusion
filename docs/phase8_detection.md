# Phase 8 — Baseline, Detection, and Evidence Bundles

*Written 2026-09-14, on picking the phase up, and **written before the phase was built** — several
specifics here were overtaken by measurement. For where the detection layer actually stands, read
`docs/detection_layer.md` first; this remains the record of why the phase was shaped this way.*

*This is the reasoning behind the phase, in one place:
what it is, what it is for, and why it is built the way it is. It is reference and drafting material
— `docs/thesis_notes.md` holds the decisions and their rejected alternatives, `docs/qa.md` explains
what individual terms mean, `docs/spec.jsonl` is the binding backlog, and the published progress note
tells the same story without identifiers. Where this document and the spec disagree, the spec wins.*

---

## 1. What this phase is

Everything built so far **moves data**. The replay adapter reads archived aviation telemetry and
translates it; the synthetic generator emits a radio-frequency grid under scenario control; the Data
Abstraction Layer validates, pseudonymises and stores both through one entrypoint; the API serves
what was stored, and the dashboard draws it. Not one line of it forms an opinion. A screen showing
four hundred aircraft and fifty-six radio channels is a faithful picture of a situation and says
nothing whatsoever about it.

Phase 8 is where the system first **makes a claim about the world** — *something here is wrong, and
this is what it looks like* — and, inseparably, where it must be able to say **why** it thinks so.
Those two obligations are not a feature and a nicety. The second is the entire reason the first is
built the way it is, and almost every design decision in this phase falls out of it.

It is also the phase that first has an answer to be right or wrong about. Every scenario run carries
a recorded ground truth: what was injected, where, and when. Until now nothing consulted it. From
here on, every run is a question with a known answer, and the system's output can be scored.

## 2. What it is trying to achieve

Three jobs, in order, each the input to the next.

| | Job | What it produces |
|---|---|---|
| 1 | Establish what **normal** looks like | A baseline per metric, per sensor, per channel, computed from quiet runs only |
| 2 | Notice **departures** from it | Anomalies, each carrying the rule that fired, its inputs, and the observations that triggered it |
| 3 | Assemble departures into a **coherent account** | Evidence bundles: grouped, traceable, and the sole input the AI layer ever receives |

The third is easy to under-read. It is not packaging. An analyst — and, later, a language model —
cannot work from eight hundred individual findings, and a system that emits them has pushed the
interpretive work back onto the person it was supposed to help. Grouping *is* part of the judgement,
and getting the grouping wrong produces an incoherent picture out of perfectly correct detections.

## 3. Why the detectors are deterministic, and only deterministic

No machine learning is used for detection. Not as a simplification, and not because it would be hard:
it is ruled out on purpose, for four independent reasons, any one of which would be sufficient.

**Explainability is the research question, not a feature.** The project's claim is that a constrained
AI layer can produce *explainable* situational assessments. An explanation has to bottom out in
something a human can check. A rule that fired because measured power exceeded a named baseline by a
configured threshold is checkable: the analyst can look at the threshold, look at the reading, and
disagree. An anomaly score of 0.87 from an isolation forest is not an explanation, it is an assertion,
and dressing it in natural language makes it worse rather than better.

**The AI layer is the thing under evaluation, so the detector must be a fixed instrument.** The
campaign compares hypothesis quality across generator arms over identical evidence bundles. If the
detector were stochastic, a difference in hypothesis quality could not be attributed to the generator
rather than to variation in what the generator was handed. A deterministic detector makes the bundles
a constant, and the comparison a comparison.

**Reproducibility is a stated non-functional requirement.** NFR-601 requires every evaluation result
to be regenerable from scenario type, parameters and seed alone. A learned detector introduces
training data, training procedure and model state as further hidden inputs; regenerating a result
would then mean reproducing a training run, and the guarantee quietly stops being a guarantee.

**It is out of scope by decision.** Scope v2 cut the isolation forest and the density clustering that
v1 carried. Reintroducing them here would be scope creep with a research cost attached.

The permitted methods are exactly four: threshold rules, rolling averages, z-score deviation, and
spatial clustering performed by PostGIS. That is a deliberately small toolkit, and the interesting
part of this phase is how far it gets on **combination** rather than on any individual method being
clever.

## 4. The chain, end to end

```
    replayed aircraft tracks              synthetic RF grid
    (real, pseudonymised)                 (7 sensors x 8 channels x time)
              │                                     │
              └──────────────┬──────────────────────┘
                             │
                      stored observations
                             │
                             ▼
           ┌─────────────────────────────────────────┐
           │  BASELINE          anom-002             │   what "normal" is,
           │  rolling averages over quiet runs only  │   per sensor per channel
           └─────────────────────────────────────────┘
                             │
          ┌──────────────────┴───────────────────┐
          ▼                                      ▼
   RF-NOISE      anom-001                 TRACK-GAP     anom-010
   z-score       anom-003                 position staleness
   power/SNR past threshold               past threshold
          │                                      │
          │                                      ▼
          │                            CLUSTERING   anom-004 + db-004
          │                            discontinuities within N km,
          │                            distance computed by PostGIS
          │                                      │
          └──────────────────┬───────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
  FUSION-SPATIAL       SOURCE-GAP           SENSOR-FAULT
  anom-005             anom-006             anom-007
  RF + gaps,           gaps, no RF          one sensor abnormal,
  same window & area                        neighbours nominal
        └────────────────────┼────────────────────┘
                             │
                             ▼
           ┌─────────────────────────────────────────┐
           │  EVIDENCE BUNDLE   evb-001, evb-002     │   grouped on time,
           │  every item traceable to a stored row   │   space and frequency
           └─────────────────────────────────────────┘
                             │
                             ▼
                    the AI layer (Phase 9)
```

Running underneath all of it, and not a stage: **`anom-008`, correct non-detection** — every detector
must also be shown to stay silent when nothing was injected — and **`anom-009`, latency** — how long
each detection took, measured in simulated time.

## 5. The baseline, and why it is per sensor per channel

A deviation is only meaningful against an expectation. The baseline engine builds that expectation by
rolling average over **normal-baseline runs only** — the scenario type that stages nothing and exists
precisely to be the quiet reference.

The granularity is the design decision. RF baselines are computed per metric **per sensor per
channel**, not per sensor. The layout is seven sensors reporting on eight 2 MHz channels each, one
centred exactly on the GNSS L1 frequency: fifty-six independent cells. Pooling the eight channels of
a sensor into one number would mean a deviation confined to a single channel gets averaged against
seven quiet ones, and a real single-channel event can disappear inside the spread of its neighbours.
That matters most for the sensor-fault rule, whose whole discrimination is single-channel against
broadband.

**What the current data actually shows, measured 2026-09-14** against the twenty completed
normal-baseline runs in the development database:

| | |
|---|---|
| RF readings in quiet runs | 100,800 |
| Sensor × channel cells | 56 (7 × 8) |
| Samples per cell | 1,800 |
| Pooled mean / standard deviation, power | −95.00 dBm / 1.50 dB |
| Spread of per-cell means | **0.177 dB** (−95.081 to −94.904) |
| Range of per-cell standard deviations | **1.437 to 1.551 dB** |

The last two rows are an uncomfortable result and are recorded rather than buried. **On quiet data
the fifty-six cells are statistically indistinguishable**, because the baseline emitter gives every
cell the same nominal power and the same noise spread by construction. A pooled baseline would
therefore produce almost exactly the same numbers as a per-cell one, and any test of the per-channel
requirement built from quiet runs alone would pass for an implementation that ignored the requirement
entirely.

So the granularity is justified **structurally, not empirically on clean data**: it is what makes the
sensor-fault discrimination possible once something *is* injected. The test proving it has to be
built from staged runs, or from a constructed series where cells genuinely differ. This is the same
error shape as a defect already recorded in this project — a test meant to distinguish two sources
that was built from values common to both, and therefore could not fail.

A further constraint, and a small one that matters: a window with too few samples returns an explicit
**insufficient-data** result. It must not return an average over one point dressed as a baseline,
because a baseline of one sample has a standard deviation of zero and every subsequent reading
deviates from it infinitely.

## 6. The rules, and what separates them

Five named rules, each with a rule ID that travels with every anomaly it raises and into the evidence
bundle after that. The ID is what makes an explanation checkable.

| Rule ID | Fires when | Concludes | Item |
|---|---|---|---|
| `RF-NOISE` | Power or SNR passes the baseline threshold | A radio-frequency deviation exists here | `anom-001` |
| `TRACK-GAP` | An aircraft's position staleness passes threshold | Track continuity broke here | `anom-010` |
| `FUSION-SPATIAL` | RF noise **and** clustered track gaps, same window and area | Possible interference zone | `anom-005` |
| `SOURCE-GAP` | Clustered track gaps **and no** co-located RF anomaly | Possible data-source issue | `anom-006` |
| `SENSOR-FAULT` | One sensor abnormal, spatial neighbours nominal, channel neighbours clean | Possible sensor fault | `anom-007` |

### The discrimination is the point

The first two rules are ordinary threshold detection. The last three are where the system earns its
keep, and the reason is this: **the same surface symptom means different things depending on what
else is present.**

Aircraft in an area stop reporting their positions. That single observation is compatible with at
least three completely different situations — interference degrading the navigation signal the
aircraft depend on, a failure in the data source that collects their reports, or nothing at all
beyond the ordinary patchiness of real coverage. A system that reported "track gaps detected" would
be accurate and useless. What separates the cases is **what the radio was doing at the same time and
place**:

| Track gaps | RF anomaly | Reading | Rule |
|---|---|---|---|
| Clustered | Present, co-located, same window | Something in the environment is interfering | `FUSION-SPATIAL` |
| Clustered | **Absent** | The aircraft are fine; the data source is not | `SOURCE-GAP` |
| None | Present, one sensor only, neighbours clean | The receiver is faulty, not the environment | `SENSOR-FAULT` |
| None | None | Nothing happened, and saying so is a result | `anom-008` |

`SOURCE-GAP` is the discriminator that keeps a coverage gap from being reported as interference, and
it is defined to be **mutually exclusive** with `FUSION-SPATIAL` for the same cluster. Both cannot be
true of one set of dropouts. This is the single most important rule in the phase for the project's
argument, because confusing the two is exactly the error a plausible-sounding language model would
make unprompted, and the detection layer is what stops it being asked to.

`SENSOR-FAULT` carries a second discrimination of the same kind, along the frequency axis rather than
the spatial one. A genuine emission raises adjacent channels together — radio energy is not confined
to one 2 MHz slice. So a deviation on a single channel with clean neighbours **on the same sensor**
is evidence about the instrument; a deviation across all eight channels is evidence about the
environment, and is weaker evidence of a fault rather than stronger. The frequency-adjacency test is
recorded as its own piece of evidence rather than folded into the spatial one, so that a reader of
the bundle can see the two independent reasons.

### What each scenario type should produce

The five scenario types the generator can produce, and the verdict a correct engine reaches on each:

| Scenario type | What is staged | Correct verdict |
|---|---|---|
| `normal-baseline` | Nothing | **No anomalies at all** |
| `gnss-degradation` | Raised noise over a zone; aircraft inside hold last position | Possible interference zone |
| `aircraft-coverage-gap` | Aircraft in a zone stop reporting; radio quiet | Possible data-source issue |
| `rf-sensor-fault` | One receiver deviating; neighbours nominal; tracks untouched | Possible sensor fault |
| `ambiguous-mixed-evidence` | Both signatures at once | **Genuinely ambiguous** |

The last one is not a detector failure mode, it is a deliberate instrument. It stages evidence that
supports more than one explanation, and the detection layer is **not** expected to resolve it. Its
purpose arrives in Phase 9: it tests whether the AI layer expresses honest uncertainty and offers
alternatives, or whether it picks the more fluent-sounding story and states it confidently. A system
that is never given an ambiguous case has not been tested on the failure mode that matters most.

## 7. Correct non-detection is a behaviour, not an absence

`anom-008` requires a normal-baseline run to raise **zero anomalies of any type**, and requires this
to be asserted for every detector individually rather than once in aggregate.

This looks like a test and is actually a control. Every detection metric reported in the evaluation —
precision, false-positive rate — is meaningless if the engine is noisy on clean data. A detector that
fires on everything has perfect recall. The quiet runs are what make the other numbers mean anything,
which is why the scenario type exists at all and why a third of the corpus is spent on it.

It is also why the item does not land as a single step at the end of the phase: a non-detection case
is added as each detector arrives, and the item closes when the last one does.

## 8. The problem the real data brings with it

Here is the honest difficulty in this phase, and it is worth stating plainly because it is exactly
the kind of thing an examiner should see acknowledged rather than discovered.

**`normal-baseline` replays real traffic, and real traffic has real gaps.** The coverage acceptance
check run on 2026-08-19 measured the archived extract directly: **10 of 948 tracks (1.05%) contain a
genuine interior airborne dropout**, and **seven of those ten fall in the 100–300 second band** that
the coverage-gap scenario injects into. These are not artefacts of the pipeline. They are aircraft
that really did stop being reported, in the real archived hour, for durations indistinguishable from
the ones the generator stages on purpose.

So `TRACK-GAP` over a quiet run will fire on real gaps, on a run that `anom-008` requires to be
silent. Three responses were considered:

| Option | Why it was or was not taken |
|---|---|
| Raise the staleness threshold above 300 s | **Rejected.** It buys a clean false-positive rate by blinding the detector to precisely the band the injected gaps occupy. The number would improve and the instrument would stop working. |
| Relax `anom-008` to "no anomalies attributable to injection" | **Rejected.** A false-positive control that permits known firings is not a control, and FR-308 makes correct non-detection a required behaviour rather than a target. |
| Exclude the ten affected tracks from corpus windows | **Accepted.** The generator refuses them as window content, identified from the coverage report. |

The exclusion was already owed — it was recorded as a mitigation for *injection sites*, so that a
staged gap would never be placed on a track that already had one. What had not been noticed is that
it is equally needed for **baseline windows**, for the same reason in reverse.

And the exclusion carries its own cost, which is recorded rather than swept up: it removes real data
in order to make a false-positive rate measurable, so the reported rate is **conditional on it**. The
evaluation therefore owes the measured rate both with and without the exclusion, and the difference
between them is itself a finding about how far synthetic ground truth can be trusted over real data.

## 9. Latency, and why it is measured in simulated time

`anom-009` measures how long detection took: the interval between the injected event's onset and the
anomaly being raised. The constraint is that it is measured in **simulated scenario time, never wall
clock**, and the reason is straightforward — a wall-clock latency is a property of the machine that
happened to run the batch. Re-run the same seed on a faster laptop and the number changes while
nothing about the detector has. That is not a measurement, and NFR-601's regenerability guarantee
would be broken by it.

The stated failure case is exactly that: a latency that changes when the same run is replayed on
faster hardware fails the spec, because it proves wall-clock time leaked in somewhere.

One thing is owed **before** any of this is written, and deliberately so: the precise definition of
detection latency is an open Track 0 item. Its entire value lies in being fixed in advance, since a
definition chosen after seeing the first results is a definition chosen to flatter them.

## 10. Evidence bundles

*Superseded in detail by `docs/phase8_evidence_bundles.md`, written 2026-09-19 when the builder was
picked up and the inputs were known rather than anticipated. That document supersedes this section on
three points in particular: `data_mode` cannot be a single value on a fused bundle, the time-and-space
grouping described below already exists in `anom-013` and must not be built twice, and the broadband
fragmentation case named here cannot be provoked by any run in the corpus. This section remains the
record of why the bundle was scoped this way.*

The bundle is the phase's output and the boundary around everything after it.

**It is the only input the AI layer ever receives.** Raw observations never reach a model. This is a
containment decision with several consequences at once: the volume handed to a model stays bounded;
nothing carrying a real aircraft identifier can reach a hosted provider, since pseudonymisation
happened far upstream at the abstraction layer; and — most importantly — the automated grounding
check becomes possible at all. A claim can only be checked against its source if the source is a
closed, enumerable set. If the model could see the whole observation stream, "is this claim
grounded?" would have no tractable answer.

**Grouping happens on three axes: simulated time window, spatial proximity, and frequency adjacency.**
The third is the one that is easy to leave out and expensive to leave out. A broadband interference
event raises all eight channels of every affected sensor. Grouped on time and space alone, that is
eight separate findings about eight channels — one coherent event fragmented into eight unrelated
ones, handed to the AI layer as an incoherent picture it will then try to explain as eight things.
Grouped on frequency adjacency as well, it is what it actually is: one event, wide.

Each bundle carries the anomaly type, the time window, the affected area, the affected channels, the
data mode, a list of evidence items and a list of **known uncertainties**. Each evidence item carries
a source, a finding, and a rule ID. A bundle with an empty evidence list, or an item without a rule
ID, fails to build rather than being emitted incomplete.

**`evb-002` adds traceability as a build-time check against the database**, not as an assertion the
builder makes about itself. Every evidence item must resolve to a stored anomaly or observation, the
resolved identifiers are persisted with the bundle, and a bundle containing an unresolvable item
raises and persists nothing — no partial bundle. Those persisted identifiers are what the Phase 9
grounding check verifies claims against, so a gap here becomes an unverifiable claim two phases later.

**The bundle carries no ground-truth field.** This is the same rule that governs the API surface: a
detector or a generator that can see the answer key invalidates every metric computed from it. The
answer lives on the run record and nowhere else.

## 11. What this phase deliberately does not do

- **No hypotheses.** Bundles are evidence, not explanations. Turning them into readable assessments is Phase 9, and the separation is what allows the AI layer to be swapped, compared and scored.
- **No machine learning**, per section 3.
- **No user interface.** The panel on the operational picture currently showing two dashes gets its first content from this phase, but wiring it is separate work.
- **No scoring.** Computing precision, recall, F1 and the rest is Phase 11's harness. Phase 8 produces the output those metrics are computed over.
- **No new confidence vocabulary.** Where confidence appears it stays Low, Medium or High. The z-score computed by `anom-003` is stored on the anomaly for traceability and is **never** rendered to an analyst as a score, because a decimal implies a precision the method does not have.

## 12. How it will be judged

Phase 11 computes, per scenario type: precision, recall, F1, false-positive rate, false-negative rate,
and detection latency in simulated time. The quiet runs contribute the false-positive rate; the four
staged types contribute the rest. Every one of those numbers traces back to a run that is regenerable
from its type, parameters and seed.

Beyond the metrics, the phase carries two qualitative claims that the write-up will have to defend:
that the discrimination in section 6 is genuine rather than an artefact of how the scenarios were
staged, and that a deterministic detector built from four simple methods is sufficient to produce
evidence worth reasoning over. The ambiguous scenario type is the strongest available evidence on the
first, and the second is ultimately answered by the hypothesis-scoring campaign rather than here.

## 13. Decisions still owed

| Owed | Gates |
|---|---|
| The precise definition of detection latency, fixed in advance | `anom-009` |
| Detector radii for `anom-005` and `anom-007`, chosen from the measured band [55.7, 85.7) km | `anom-005`, `anom-007` |
| The staleness threshold for `TRACK-GAP`, set against the corpus's 10 s reporting cadence | `anom-010` |
| The RF deviation threshold, as configuration rather than a literal | `anom-001` |
| A floor on the affected-aircraft count, rather than a bare 8% | `anom-005`, `anom-006` |
| Applying the ten-track exclusion to baseline windows as well as injection sites | `anom-008`, `anom-010` |

## 14. Build order

`anom-002` → `anom-001` → `anom-010` → `db-004` → `anom-004` → `anom-005` + `anom-006` → `anom-007`
→ `anom-009`, with `anom-008` accumulating throughout, then `evb-001` → `evb-002`.

The identifiers are not the order. `anom-001` consumes the baseline that `anom-002` produces, so the
item numbered first depends on the item numbered second — the same inversion Phase 7 hit, recorded
there as well. `db-004` is carried forward from Phase 6, where it is the last unticked item, because
this is the first point at which there are discontinuities for it to query over. The reasoning for the
sequence is in `docs/implementation.md` at the head of the Phase 8 list.
