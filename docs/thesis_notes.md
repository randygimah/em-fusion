# Thesis Write-up Notes

Working notes filled in during development — the basis for the dissertation write-up, not the
proposal. For the scope/research questions being answered, see `research_scope.md`; for build
status, see `implementation.md`. Update the relevant section as each phase lands, while the
reasoning is still fresh, rather than reconstructing it from git history later.

## Methodology

<!-- Design rationale: why a modular monolith, why deterministic detection precedes AI, how the
evaluation was designed (batch runs + blind rubric + user study), ethics/employer-clearance
process notes as they happen. -->

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

### AI hosting: a locally-hosted open-weight model

The proposal specified a hosted LLM API. The implementation uses a locally-hosted open-weight model
instead, run via Ollama on the development machine (Apple silicon, 48 GB unified memory) behind a
provider-agnostic service module. The justification is ordered deliberately, because the weakest
argument is the one most likely to be over-claimed:

1. **Reproducibility.** Pinned weights plus a fixed seed at temperature 0 is near-deterministic and
   will still be reproducible at viva. Hosted models are deprecated on published retirement
   schedules and cannot be pinned indefinitely — a result generated against a hosted model months
   before submission may not be regenerable at examination time. For a dissertation whose central
   evaluation claim rests on reproducible seeded runs, this is the substantive argument.
2. **Offline demonstration.** Extends the existing no-live-API reliability requirement from the data
   layer to the AI layer. The complete system — replay, detection, hypothesis generation, map —
   demonstrates with no network, no API key, and no third-party account.
3. **Cost and data locality.** Zero marginal cost across hundreds of evaluation runs, and no data
   egress.

**Do not overstate the cost argument.** A full hosted evaluation campaign was costed at roughly
£20–30 using prompt caching and batch pricing — real but not prohibitive. Presenting cost as the
driver would be an inaccurate account of the decision and weaker than the reproducibility argument
it would displace.

**Known risk, and why it is acceptable.** A local open-weight model produces weaker prose — the
hypothesis title, uncertainty statement, and alternative explanations — than a frontier hosted
model. Schema validity and grounding are unaffected, as both are enforced deterministically
(below), but the blind-scored hypothesis-quality rubric may show a narrower or null template-vs-AI
gap than a frontier model would have produced. This is a direct threat to one research question and
is recorded as such rather than discovered at analysis time. Two mitigations: a null result is a
legitimate and reportable finding, particularly when reported alongside grounding-check catch rates
(the negative result "a locally-hosted constrained model did not measurably outperform a
well-constructed template baseline on analyst-rated quality" is itself informative about where the
value in this architecture actually sits); and a small contingency budget permits one additional
hosted arm over identical evidence bundles if the comparison looks marginal. The contingency is only
exercisable because the service module is provider-agnostic and `hypotheses.generator` was widened
to `"template" | "local" | "hosted"` before the table was populated — a decision made cheaply up
front that would have been a migration later.

**Implementation constraints worth recording.** Docker Desktop on macOS does not pass Metal through
to containers, so a containerised model runtime silently falls back to CPU at roughly an order of
magnitude less throughput; the model server therefore runs on the host and is reached from the
backend container via `host.docker.internal`, making it a Compose config value rather than a Compose
service. Separately, the binding constraint on local inference proved to be **batch throughput, not
quality** — hypotheses are short and constrained-decoded, but a full campaign is still hours of wall
time, which shapes the M9 schedule (iterate against a small model, run the final campaign against
the chosen model overnight). *(Record the model finally used, quantisation, and measured
tokens/sec and campaign wall-time here.)*

### Schema conformance as a generation-time guarantee

The original design treated schema validation as a post-hoc check with bounded retry and fallback.
The implementation strengthens this: constrained decoding compiles the JSON Schema into a grammar,
making structurally invalid output *unrepresentable* rather than merely detectable. Malformed JSON,
missing required fields, and out-of-enum confidence values cannot be emitted at all. Notably, this
also enforces the project's categorical-confidence rule mechanically — `Confidence: 87%` is not a
value the decoder is able to produce.

Pydantic validation is retained as defence-in-depth and to enforce constraints a grammar cannot
express (cross-field consistency, referential checks against the bundle), with bounded retry and
template fallback preserved for those cases. Retry rate is logged so the near-zero expectation is
evidenced rather than assumed.

The distinction that matters for the write-up: **step 1 constrains shape, step 2 constrains truth.**
Constrained decoding guarantees `supporting_evidence` is a well-formed list of correctly-typed
items; it says nothing about whether the rule IDs inside those items exist in the evidence bundle.
Hallucinated-but-well-formed evidence is exactly the failure mode the grounding check exists to
catch, and it is the one a schema cannot address. This makes the grounding-check catch rate the more
interesting of the two measurements, and it applies equally to a hosted model — the safeguard is not
a workaround for using a smaller model.

### Map library: MapLibre GL JS

Mapbox GL JS was replaced with MapLibre GL JS — the open-source fork, near-identical API, no account
or access token, usable with free tile sources. This removed the last hosted third-party dependency
and brought the project's running cost to zero, consistent with the local-model decision above.

The point worth making in the write-up is architectural rather than about the library: the swap was
a single-file change because the `MapView` adapter boundary was specified before any map code was
written, and no other component imports a map library directly. This is a small, concrete instance
of the same substitutability argument made at the storage layer — a boundary drawn in advance turned
a potentially invasive dependency change into a contained one. *(Record the actual diff size here
once the swap lands; it is a cheap second data point alongside the third-adapter RQ1 measurement.)*

## Evaluation

<!-- Anomaly detection metrics per scenario type (precision/recall/F1/FPR/FNR/latency), hypothesis
quality rubric results (template vs AI, blind scoring, inter-rater agreement if applicable),
grounding-check catch rate, user study results (NASA-TLX, task completion, qualitative feedback),
limitations encountered. -->
