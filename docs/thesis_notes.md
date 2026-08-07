# Thesis Write-up Notes

Working notes filled in during development — the basis for the dissertation write-up, not the
proposal. For the scope/research questions being answered, see `research_scope.md`; for build
status, see `implementation.md`. Update the relevant section as each phase lands, while the
reasoning is still fresh, rather than reconstructing it from git history later.

## Methodology

<!-- Design rationale: why a modular monolith, why deterministic detection precedes AI, how the
evaluation was designed (batch runs + blind rubric), ethics/employer-clearance process notes as
they happen. -->

### Evaluation design: withdrawing the task-based user study, retaining blind rubric scoring

The evaluation was originally designed with three strands: automated detection metrics against
generator ground truth, blind rubric scoring of hypothesis quality against a template baseline, and
an ethics-approved task-based study with three to six participants measuring task completion time,
triage accuracy, and perceived workload. The third strand has been withdrawn. The decision was taken
in August 2026, before the ethics application was submitted, which is the point at which withdrawal
was cheapest — the application itself was the sunk cost being avoided, along with a four-to-eight
week approval wait that gated the strand.

The reason was capacity rather than value. The plan estimated 254 hours against roughly 240
available, and the study accounted for fourteen hours of session work plus recruitment and the
ethics application. Withdrawing it moved the plan from fourteen hours over to a small positive
margin. The contingency was not improvised: TOR 7 of the submitted proposal had already named the
user study as the strand to shed under the low-availability case, on the reasoning that the
evaluation would remain defensible on the other two. What changed was the assessment that the
planned case, not merely the low case, was too tight to carry it.

Two things are worth recording about how the decision was reasoned, because both are more
interesting than the outcome. First, "user study" turned out to name two separable things that were
being treated as one: the task-based study, and the human blind scoring of hypothesis quality. Only
the former was withdrawn. Dropping both would have left the central AI research question resting on
the author scoring his own system's output, which is not a defensible position and was very nearly
adopted by accident through imprecise language. The distinction is now made explicitly wherever the
evaluation is described. Second, the withdrawal creates a gap that must be stated rather than
elided: with the study gone, nothing in the evaluation measures analyst *utility*. Detection metrics
measure whether the pipeline finds what was injected; blind rubric scoring measures whether
hypotheses are rated better than a template baseline by two independent raters. Neither establishes
that an analyst completes a triage task faster or more accurately with the system than without it.
That is a real limitation of the contribution, it is named as such in the Evaluation chapter, and it
is the first item of future work.

A secondary consequence sits outside the research argument. The apprenticeship KSB on negotiating
and closing with senior stakeholders was evidenced partly by ethics approval and participant
recruitment; both are gone. Employer clearance and securing an independent second rater remain, but
the evidence is thinner, and that is a supervisor conversation rather than a silent re-tick.

*(Record the date of supervisor agreement to the revised objective 6 here once obtained.)*

### Data acquisition: OpenSky static snapshot rather than the Trino interface

OpenSky offers two routes to historical state vectors. The **Trino/MinIO SQL interface** is free to
university-affiliated researchers but requires an application with written justification, carries an
unbounded approval wait, and its own documentation discourages the bulk-extraction pattern. The
**static snapshot download** — published tables as of 2026-03-01, every Monday's complete state
vectors at 10-second intervals, one file per hour — needs no application and is available
immediately. The snapshot was chosen on schedule-risk grounds: an approval wait of unknown length
sits on the critical path of a time-boxed dissertation, and the alternative costs nothing in
capability.

It costs nothing in capability because the snapshot carries every field the detection rules consume:
`lat`/`lon`, `baroaltitude`/`geoaltitude`, `velocity`, `heading`, and — critically — `lastposupdate`
and `lastcontact`. The delta between `time` and `lastposupdate` is position staleness, a directly
measured quantity rather than an inferred one, and it is the basis of the aircraft-update-gap
detection rule. Had this field been absent the trade-off would have been real; it is not.

Three consequences, recorded because two of them are threats to validity rather than mere logistics:

1. **Monday-only coverage is not a limitation of this design.** Scenario variation is produced by the
   seeded synthetic generator (type + parameters + seed), not by sampling diverse real data. The
   aviation telemetry is a deterministic backdrop against which synthetic anomalies are injected, so
   one representative slice satisfies the requirement — and arguably serves reproducibility better
   than a varied corpus would.
2. **Region selection is a validity concern, not a convenience.** OpenSky's sensor coverage is
   geographically uneven. A sparsely covered bounding box produces *genuine* dropouts and coverage
   gaps that are indistinguishable, to the detector, from the synthetic ones being injected — which
   would contaminate ground truth and render the false-positive rate uninterpretable. A densely
   covered region (Central Europe) was selected for this reason. Acceptance check performed before
   any detection work: run the `Normal baseline` scenario against the extract and confirm no
   dropouts appear prior to injection. *(Record the box chosen, the hour used, and the result of
   this check here once run.)*
3. **Reproducibility depends on the manifest, not the raw file.** Raw hourly files are global and
   run to hundreds of MB, so the archived corpus is a bounding-box-filtered extract accompanied by a
   manifest recording source URL, hour, download date, licence, and the checksum of the original.
   The extract is the artefact; the manifest is what makes it reproducible without redistributing
   several hundred MB of someone else's data.

Trino access remains available as future work if a date- or region-specific corpus is ever needed
beyond the snapshot's coverage. *(Record licence and citation requirements here once confirmed from
OpenSky's terms page — the conventional academic citation is the 2014 IPSN paper introducing the
network, but verify against their current terms rather than relying on convention.)*

## System Design and Architecture

<!-- Actual architecture as built vs as planned (docs/em_fusion_v2.md section 7) and why it
diverged, if it did. DAL design decisions, canonical data model decisions, key diagrams. -->

### Storage substrate: why PostgreSQL/PostGIS and not a data lakehouse

A lakehouse stack (Parquet on object storage under an Iceberg table format, a REST catalog such as
Lakekeeper, Trino as the query engine) was considered and rejected for the prototype. The rejection
is on workload-fit grounds, not capability grounds, and the reasoning is worth stating explicitly
because it doubles as evidence that the DAL abstraction holds.

Four reasons it does not fit the prototype:

1. **Volume.** The non-functional requirement is hundreds to low thousands of observations per run
   (`em_fusion_v2.md` section 12); the full evaluation campaign — five scenario types × 20–30
   seeded batch runs — produces low hundreds of thousands of records in total. That is three to
   four orders of magnitude below the scale at which a lakehouse begins to pay for itself.
2. **Access pattern.** The pipeline is transactional: observations are written record-by-record
   during replay, malformed records are quarantined inline, and analyst verdicts are interactive
   writes. Iceberg is append- and commit-oriented; frequent small writes produce small-file
   accumulation and commit contention, and would add compaction maintenance to a prototype.
3. **Spatial detection is load-bearing.** Spatial clustering of track discontinuities within N km of
   an RF anomaly zone is one of the four deterministic detection methods, and it depends on indexed
   PostGIS predicates. Trino offers `ST_*` functions but no comparable indexed spatial join, and
   Iceberg has no spatial partitioning. Adopting the lakehouse would trade the strongest detection
   primitive for query flexibility the prototype does not need.
4. **Operational cost against RQ1.** The DAL is a *semantic* layer — canonical observation model,
   required-field validation, quarantine, provenance — not a storage or query abstraction. A
   lakehouse sits beneath it as substrate and contributes no evidence to RQ1, while enlarging the
   surface area that the late third-adapter extensibility measurement has to touch. It would make
   the RQ1 figure worse while answering none of the research questions. It also adds four services
   to a stack whose stated deployment target is local Docker Compose.

**Why this belongs in the architecture chapter rather than only in future work.** Because the
anomaly-detection engine consumes canonical observations rather than database rows, the persistence
layer is substitutable without touching detection, evidence-bundling, or hypothesis logic. At
operational ingest volumes the migration path is therefore: retain the adapters and DAL unchanged,
move the observation store to Parquet-on-object-storage under Iceberg, use Trino for cross-run
analytical and evaluation queries, and keep PostgreSQL for the transactional
hypothesis/feedback/scenario-run tables. This demonstrates the abstraction holds *vertically* (the
storage substrate can be swapped) as well as *horizontally* (a new source can be added), which is a
stronger extensibility claim than the third-adapter experiment alone.

State the limitation honestly: the spatial-clustering path would need rethinking under that
migration, since it is the one component genuinely coupled to PostGIS rather than to the canonical
model. Candidate approaches — spatial partitioning schemes, a retained PostGIS serving tier for the
active window, or grid-cell indexing computed at DAL time — are untested here.

Two low-cost practices are taken from that ecosystem without taking the infrastructure, to be
confirmed as built: the evaluation harness (M9) should export batch metrics as Parquet rather than
CSV (Pandas is already a dependency, and dtypes survive the round trip), and the archived OpenSky
pull should be kept as immutable files with a manifest recording source URL, download date,
licence, and checksum.

## Implementation

<!-- Notable technical decisions per phase (link to implementation.md phases), challenges and
deviations, the third-adapter extensibility measurement for RQ1 (files touched / lines changed /
hours taken), AI integration details (prompt design, schema validation, retry/fallback logic,
grounding-check implementation). -->

### AI hosting: a hosted frontier model, with a local model as a second arm

The design went through a reversal worth recording, because the reasoning behind the reversal is
more useful to the write-up than either endpoint. An intermediate design made a locally-hosted
open-weight model the sole AI generator, on reproducibility grounds. The implemented design uses a
**hosted frontier model as the primary generator and retains the local model as a genuine second
evaluation arm** rather than as dead-code insurance. Both run behind one provider-agnostic service
module over identical evidence bundles.

**Why the local-only design was reconsidered.** Its lead argument was that pinned weights plus a
fixed seed remain reproducible at viva, whereas hosted models are retired on published schedules.
That argument was overweighted, and identifying why is itself a methodological point: evaluation
artefacts are *persisted*, not regenerated on demand. Every hypothesis is stored with its
`model_id`, `generation_params`, and verbatim `raw_response`, and the harness exports them. The
reproducibility that the evaluation actually depends on is reproducibility of the **deterministic
pipeline** — seed → replayed and synthetic data → detection → evidence bundle — which is entirely
unaffected by where the model runs. What a hosted model genuinely forfeits is the ability to
*regenerate* that arm from scratch after retirement; the stored artefacts, and the fully regenerable
local arm, cover the rest. This is a real trade rather than a dismissed one, and it holds only
because the persistence was built before the campaign ran.

**Why hosted-primary, in order of weight:**

1. **It protects the research question.** The AI research question compares constrained AI
   generation against a template baseline. A capability-starved model narrows that gap for reasons
   unrelated to the architecture under study, so a null result would be uninterpretable — attributable
   either to the constraint design or simply to model size. A frontier model removes the confound:
   whatever gap emerges is attributable to the design.
2. **Schedule.** Batch throughput, not quality, was the binding constraint under the local-only plan
   — a full campaign was hours of wall time, effectively affording one attempt. Batch pricing and
   request concurrency make the campaign re-runnable after a bug is found, which in a time-boxed
   project is worth more than the fee.
3. **Development velocity.** No model server to operate or tune during the phases where the pipeline
   itself is what is being built.

**Cost is accepted, not minimised.** Roughly £20–30 for a full campaign with prompt caching and
batch pricing. This should be stated plainly as a deliberate spend. Presenting it as anything else
would misdescribe the decision — as would the earlier framing, which leaned on cost avoidance to
support a choice made on other grounds.

**Why the local arm is retained — and why it is not merely a fallback.** Running both models over
identical bundles changes the question from *"does an AI generator beat a template?"* to **"how much
of hypothesis quality comes from model capability versus from the constrained-generation
architecture?"** — which is the more interesting question for a thesis whose subject is constraint.
The outcomes are informative in both directions: if the local arm approaches the hosted one, the
finding is that the architecture carries the quality and the system runs offline on commodity
hardware; if the hosted arm leads clearly, the capability contribution is quantified. The two-arm
design could only yield one interesting result; the three-arm design yields one either way. The
local arm additionally satisfies the offline-demonstration requirement, which the hosted arm cannot.

This was cheap only because `hypotheses.generator` was widened to `"template" | "local" | "hosted"`
while the table was still unpopulated — a decision taken speculatively that turned out to be
load-bearing, and that would have been a migration had it been deferred.

**Two risks recorded in advance rather than discovered at analysis time.** First, **human scoring
load**: three arms is three times the blind-rubric pairs, which may exceed what 3–6 participants can
score. The plan is hosted-vs-template at full N as the primary comparison with local-vs-hosted as a
smaller secondary sample, fixed before the campaign rather than adjusted after seeing results.
Second, **data egress**: evidence bundles now leave the machine. All content is synthetic or
replayed open data, so this is expected to be immaterial, but it intersects the employer-clearance
track and was confirmed early rather than late.

**Implementation constraint on the local arm.** Docker Desktop on macOS does not pass Metal through
to containers, so a containerised model runtime silently falls back to CPU at roughly an order of
magnitude less throughput. The model server therefore runs on the host (Apple silicon, 48 GB unified
memory) and is reached from the backend container via `host.docker.internal` — a Compose config
value, not a Compose service. *(Record the hosted model ID and the local model, quantisation, and
measured tokens/sec here, along with actual campaign cost and wall-time.)*

### Schema conformance as a generation-time guarantee

The original design treated schema validation as a post-hoc check with bounded retry and fallback.
The implementation strengthens this: generation is constrained to the schema, making structurally
invalid output *unrepresentable* rather than merely detectable. Malformed JSON, missing required
fields, and out-of-enum confidence values cannot be emitted at all. Notably, this also enforces the
project's categorical-confidence rule mechanically — `Confidence: 87%` is not a value the decoder is
able to produce.

Worth noting for the architecture argument: **one schema, two enforcement mechanisms, identical
guarantee.** The hosted arm uses the API's native JSON-schema-constrained output; the local arm
compiles the same schema into a GBNF grammar. Because the guarantee is a property of the schema
rather than of a provider, the two model arms are comparable on prose quality without a confound
from differing structural reliability — which is precisely what the three-way comparison requires.
It also means the choice of provider carried no risk to this safeguard.

Pydantic validation is retained as defence-in-depth and to enforce constraints a grammar cannot
express (cross-field consistency, referential checks against the bundle), with bounded retry and
template fallback preserved for those cases. Retry rate is logged so the near-zero expectation is
evidenced rather than assumed.

The distinction that matters for the write-up: **step 1 constrains shape, step 2 constrains truth.**
Constrained decoding guarantees `supporting_evidence` is a well-formed list of correctly-typed
items; it says nothing about whether the rule IDs inside those items exist in the evidence bundle.
Hallucinated-but-well-formed evidence is exactly the failure mode the grounding check exists to
catch, and it is the one a schema cannot address. This makes the grounding-check catch rate the more
interesting of the two measurements. It applies identically to both model arms — the safeguard is a
property of the architecture, not a compensation for model weakness — which makes per-arm grounding
catch rates directly comparable and is one of the more useful numbers the three-arm design produces.

### Map library: MapLibre GL JS

Mapbox GL JS was replaced with MapLibre GL JS — the open-source fork, near-identical API, no account
or access token, usable with free tile sources. The data and presentation layers therefore carry no
hosted dependency at all — archived replay, tokenless tiles — leaving the AI layer as the single
deliberate exception and the project's only running cost.

The point worth making in the write-up is architectural rather than about the library: the swap was
a single-file change because the `MapView` adapter boundary was specified before any map code was
written, and no other component imports a map library directly. This is a small, concrete instance
of the same substitutability argument made at the storage layer — a boundary drawn in advance turned
a potentially invasive dependency change into a contained one. *(Record the actual diff size here
once the swap lands; it is a cheap second data point alongside the third-adapter RQ1 measurement.)*

## Evaluation

<!-- Anomaly detection metrics per scenario type (precision/recall/F1/FPR/FNR/latency); hypothesis
quality rubric results across the three arms (template / local / hosted, blind scoring, inter-rater
agreement if applicable) — primary comparison hosted-vs-template at full N, secondary
local-vs-hosted at reduced N; grounding-check catch rate, grounding variance, and retry rate per
arm; campaign cost and wall-time per arm; limitations encountered — including the absence of any
analyst-utility measurement following the withdrawal of the task-based user study. -->
