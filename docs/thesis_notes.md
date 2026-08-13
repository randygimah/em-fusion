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

### Scored arms: withdrawing the local model from the evaluation while keeping it in the system

The AI hypothesis layer was specified with three generators — template, hosted frontier model, and
local open-weight model — and all three were to be blind-scored. The scored comparison has since been
reduced to two: hosted against template. The local generator remains in the system, but it does not
appear in any results table.

The original argument for the third arm is recorded in the Implementation chapter below and was a
good one on its own terms: running an open-weight and a frontier model over identical evidence
bundles would have upgraded the research question from "does a constrained AI generator beat a
deterministic template?" to "how much of hypothesis quality comes from model capability as against
the constrained-generation architecture?" — a question with an informative answer in either
direction. Two things overturned it.

The first is that it answers a question the project does not ask. The research question concerns
whether a constrained AI layer can produce explainable, evidence-grounded hypotheses that a template
baseline cannot match. Open-weight against frontier is a capability comparison, and a substantial one
in its own right; annexing it to an architecture study widens the contribution without deepening it.
The scope document had already conceded this implicitly by demoting local-versus-hosted to "a smaller
secondary sample" on scoring-load grounds — a secondary comparison at reduced N that nobody would
have been able to draw a conclusion from.

The second is statistical, and is the stronger reason. Human rubric scoring is the binding constraint
on the evaluation: it costs a second rater's time, and the corpus is therefore on the order of twenty
evidence bundles. Splitting that budget three ways yields two underpowered comparisons; spending it
all on hosted-versus-template yields one adequately powered comparison, on the axis that bears
directly on the research question. Withdrawing the arm is not a concession to schedule pressure so
much as a correction — the three-arm design was spending scarce measurement capacity on the wrong
contrast.

What the project gives up is the ability to say anything about the capability-versus-architecture
split, and that should be stated rather than left as an unexplored implication. It is the second item
of future work, and it is unusually cheap to add later: the local generator is built, exercised, and
producing schema-valid output against the same bundles, so the marginal cost is a second generation
pass and a larger scoring budget.

The local generator stays for reasons that were always independent of evaluation, and separating
those from the evaluation argument is what made the decision tractable. It is the availability
fallback when the hosted API is unreachable; it is what allows the whole system to be demonstrated
offline with AI-generated rather than template hypotheses, with no API key, network, or third-party
account; and it is the second consumer of the provider-agnostic service interface, which is what
makes that interface demonstrably load-bearing rather than a speculative abstraction — a point that
feeds the extensibility claim. It is nonetheless time-boxed: if local model selection, quantisation,
and grammar-constrained output do not come together in about a day, it is cut, the template generator
becomes the sole fallback, and the offline demonstration shows template output.

*(Record the actual time spent standing up the local arm here, and whether the time-box held. If it
was cut, record that too — a time-box that fires is a result about estimation, not a failure.)*

### Build order: the API contract before the UI features that depend on it

The original phase order built the Operational Picture screen against mock data and introduced the
FastAPI contract mirror two phases later. That order has been amended: the contract mirror now
precedes the view filter and the map playback, though the purely visual layout work still runs first.

The reasoning is narrower than a general preference for backend-first development, and the narrowness
is the point. Two features are **server-side by specification** rather than by convention. The view
filter filters on the server so that excluded rows never reach the client — which means the
suppressed counts that keep the "+n nominal hidden" footer truthful can only come from response
metadata, and a client-side implementation has nothing to report. The playback buffer's time-window
query is bounded server-side, with over-long spans truncated and the truncation reported; a mock has
no equivalent behaviour to exercise. In both cases the original checklist had already conceded the
problem, instructing that the mock be filtered "behind the same function signature the API call will
use" — an explicit acknowledgement that the work would be done twice.

The general lesson worth carrying into the write-up is about where a contract-first architecture
actually pays. The project's contract-first design — a typed `OperationalPicture` mirroring the future
response shape, screens taking it as a prop, one seam in `App.tsx` — was intended to make the data
source substitutable, and it does. What it does not do is make *behaviour* substitutable: a feature
whose semantics live on the server cannot be developed against a client-side stand-in, however
faithful the shape. Recognising which features those are, rather than treating the mock as uniformly
sufficient, is the distinction that reordered the phases.

One risk the reorder introduces is recorded here in advance: the backend fixture and the frontend type
now describe one contract in two languages, and will drift silently unless something forces them
together. The mitigation is a contract test on each side asserting the same shape, so a renamed field
fails a test rather than surfacing as an empty panel in the browser.

*(Record here whether the reorder actually avoided rework, or whether the contract mirror turned out
to cost more than the shim it replaced. The estimate was that Phase 5 is small; that should be
checked against the outturn rather than assumed.)*

### RF observation model: a sensor × channel grid rather than per-sensor readings

The synthetic RF generator emits on a fixed grid of sensors by frequency channels by time, rather
than as one unstructured reading per sensor per interval. Eight channels of 2 MHz, centred on
1567.42 to 1581.42 MHz, place one channel exactly on GNSS L1 (1575.42 MHz) with four either side.
Sensors number six to eight, positioned so that a plausible interference zone contains some and
excludes others.

The original design had a `frequency` field but no channel axis, and the gap only became visible when
the design was compared against a previous anomaly-detection project of the author's that used a
sensor-by-channel grid. Without adjacency in frequency, the model can express "this sensor is noisy"
but not "the noise is confined to one channel" or "it is smeared across the band" — and that
distinction is a discriminator a deterministic rule can act on directly. It is the same argument the
project already makes spatially, one axis over: a real emission raises adjacent channels together,
just as it affects neighbouring sensors together, so an isolated single-channel deviation with clean
neighbours is evidence about the instrument rather than about the environment. Adding the axis
therefore strengthens an existing claim rather than introducing a new mechanism, which is why it was
adopted despite arriving late.

Three design choices within it are worth defending. The grid is **dense** — every sensor reports
every channel every interval — so that a missing reading is an unambiguous gap rather than a
generator that had nothing to say; a sparse grid would make genuine dropouts indistinguishable from a
design decision. Spectral extent is a **parameter of the GNSS degradation scenario** rather than a
sixth scenario type, because narrowband and broadband interference are variations within one
phenomenon and the five-type set is a scope boundary worth holding. And the sensor count rose from
the three used in the earlier project to six or eight, because that project was not spatial: with
three sensors, "the discontinuities are clustered" and "the neighbours are nominal" are not claims
that can meaningfully be tested, and the PostGIS justification would be correspondingly thin.

Two things were deliberately **not** carried across from the earlier project, and the reasons are
scope decisions rather than technical objections. Its Isolation Forest detector is exactly what v1
excludes: deterministic detection is the scope commitment the whole argument rests on, and ML
detectors are recorded as future work. Its 0–100 severity score conflicts directly with the
project-wide rule that confidence and severity are categorical — a numeric score implies a precision
the evidence does not support, and the rule exists to prevent exactly that. Its counterfactual
per-feature rescoring was also left behind: it is an explainability technique bound to the tree
model, whereas explanation here comes from rule IDs, the evidence bundle, and the constrained AI
layer, and importing a second explanation mechanism would blur that story.

*(Record here whether eight channels proved sufficient once the detectors ran, and whether the
narrowband/broadband parameter produced separable detection behaviour or collapsed into one case.)*

### Ground truth is generator-side only

The generator records what it injected on `scenario_runs.ground_truth`, and nothing downstream may
carry it — no observation, adapter record, detector input, API response, or evidence bundle, whether
as a field, a label, or an inferable artefact such as a scenario-type string attached to an
observation. This was made an explicit specification (`api-009`, `NFR-604`) rather than left as an
assumption, because it is the kind of constraint that holds by accident until one convenience field
is added during debugging and then silently invalidates a campaign. The practice was adopted from the
earlier project, where ground-truth labels were kept out of the published artefacts by the same
reasoning.

The failure it guards against is not subtle but is easy to miss: a detector with access to the answer
is not a detector, and every precision, recall, and false-positive figure computed from such a run
would be meaningless while still looking entirely plausible. There is no test that catches this after
the fact, which is why it is asserted structurally instead.

### Data acquisition: OpenSky static snapshot rather than the Trino interface

OpenSky offers two routes to historical state vectors. The **Trino/MinIO SQL interface** is free to
university-affiliated researchers but requires an application with written justification, carries an
unbounded approval wait, and its own documentation discourages the bulk-extraction pattern. The
**Weekly 24 Hours of State Vector Data** sample — every Monday's complete state vectors at 10-second
intervals, one file per hour, covering 2017-06-05 to 2022-06-27 — needs no application and is
available immediately, served anonymously from OpenSky's `data-samples` bucket. The snapshot was chosen on schedule-risk grounds: an approval wait of unknown length
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
   run to 120–180 MB compressed, so the archived corpus is a bounding-box-filtered extract
   accompanied by a manifest recording source URL, hour, download date, licence, attribution, and
   the SHA-256 checksum of the original. The manifest is what makes the extract reproducible without
   redistributing several hundred MB of someone else's data — a property that turned out to be the
   whole mechanism rather than a convenience, once the licence was read (see the reversal below).

Trino access remains available as future work if a date- or region-specific corpus is ever needed
beyond the sample's coverage.

**Citation and licence, confirmed from OpenSky's terms page on 2026-08-13** rather than assumed. §4(i)
of the Data License Agreement requires that any publication using the data cite either `The OpenSky
Network, http://www.opensky-network.org` or the paper introducing the network: Schäfer, M.,
Strohmeier, M., Lenders, V., Martinovic, I. and Wilhelm, M. (2014) *Bringing up OpenSky: A large-scale
ADS-B sensor network for research*, ACM/IEEE International Conference on Information Processing in
Sensor Networks (IPSN), April 2014. The conventional citation was the correct one; it is now checked
against the current terms as this note originally required. §4(i) also obliges the licensee to provide
OpenSky with a copy of or link to the publication.

### Reversal: the corpus is not committed to the repository after all

The original position, recorded above and written into FR-110, `adp-004`, and the Track 0 checklist,
was that the filtered extract would be **committed** so that the pipeline reproduces from a fresh
clone with no download step. That position was reversed on 2026-08-13, before any data was downloaded,
on reading the licence rather than on any technical ground.

§3(iii) of the OpenSky Data License Agreement states that the licensee "will not distribute, disclose,
transfer or otherwise make available the data set(s) to any person other than those employed by your
institute who are assisting or collaborating with You", and §4(ii) obliges the licensee to expunge
copies on completion of the stated research, with a narrow carve-out for scientific reproducibility.
Committing the extract is redistribution — unambiguously so for a public repository, and on any
honest reading still so for a private repository shared with an examiner, who is not employed by the
licensee's institute.

The failed assumption is worth naming precisely, because it is the kind that survives review: that a
bounding-box-filtered subset is a *derived work* and therefore freely committable. The agreement draws
no such line, and a filtered set of state vectors is still state vectors. Three alternatives were
considered. Committing to a private repository with examiner access was rejected because it rests on
the same reading of §3(iii) that fails, and because a file once in git history requires a history
rewrite to remove. Requesting written permission from OpenSky was rejected on schedule grounds — an
unbounded wait on the critical path, which is the identical risk that ruled out the Trino interface in
the first place, and it would have been inconsistent to accept it here having rejected it there.

What is committed instead is the manifest, the coverage report, and a fetch-and-filter script that
re-downloads against the recorded SHA-256 and re-filters deterministically. A reader reproduces the
corpus in one command, having accepted the same licence themselves — which is arguably the more
honest arrangement, since it makes the reader's acceptance of the terms explicit rather than bypassing
it by handing them the bytes.

**The resulting limitation should be stated plainly in the write-up.** The two halves of the pipeline
now have different reproducibility guarantees. The synthetic half regenerates indefinitely and exactly
from scenario type, parameters, and seed. The aviation backdrop regenerates only for a reader who
accepts the OpenSky terms and re-downloads, and depends on OpenSky continuing to host that hourly file
at that path — a dependency on a third party's hosting decisions that a committed file would not have
had. That is a genuine cost of the reversal, not a neutral trade, and it is the price of complying
with terms that should have been read before FR-110 was written.

A second point from the same terms, logged for the Track 0 employer-clearance conversation rather than
for the build: OpenSky now requires a written licence for "any use by a for-profit or commercial
entity — including government and military contractors — regardless of purpose". The work is
university research under the non-profit research licence, but the project's subject matter and the
employer relationship put it close enough to that clause that it belongs in the same conversation as
the EW/GNSS review question.

## System Design and Architecture

<!-- Actual architecture as built vs as planned (docs/em_fusion_v2.md section 7) and why it
diverged, if it did. DAL design decisions, canonical data model decisions, key diagrams. -->

### Architecture documentation: a generated C4 model rather than drawn diagrams

The architecture is documented as a C4 model written in Structurizr DSL and held in the repository at
`docs/architecture/workspace.dsl`, from which every diagram is generated. The alternative — drawing
the diagrams directly in a graphical tool and exporting images — was rejected on a maintenance
argument rather than an aesthetic one. A drawn diagram has no relationship to the code that survives
a refactor: it goes stale silently, and the failure is invisible precisely because an out-of-date
diagram still renders perfectly well. A generated model at least fails loudly, in that the `validate`
command rejects a view referring to an element that no longer exists, and it produces a text diff that
a reader can review alongside the code change that motivated it. The cost is that the model is one
more artefact to keep current; the mitigation is that it is cheap to regenerate and lives beside the
code rather than in a separate tool.

Three levels are modelled — Context, Containers, Components (backend only) — with a fourth deployment
view added beyond the standard set. Level 4 (Code) is deliberately omitted. C4 treats it as optional,
it is the level that decays fastest, and the TypeScript contract types and the schema in
`docs/em_fusion_v2.md` §9 already document structure at that granularity with the advantage of being
compiler-checked. Documenting it twice would guarantee that one copy is wrong.

Two modelling decisions are worth recording because C4 did not offer an obvious answer. First, the
local model server is drawn as an **external software system rather than a container**, despite being
part of the system in every ordinary sense. The reason is that it runs as a host process outside the
Compose stack — Docker Desktop on macOS does not pass Metal through, so a containerised runtime would
silently fall back to CPU — and C4's container notion carries an implicit deployment boundary that
would misrepresent this. The deployment view is where the arrangement is stated properly, and adding
that view was prompted entirely by the difficulty of expressing the constraint at Level 2.

That decision was then taken further, in a way worth recording because the reasoning generalises. In
the first draft the local model server appeared on all three levels, and at Level 1 it sat beside the
analyst and the archived corpus as a peer external system. That badly overstated it: a component which
fires only when the hosted API is unreachable is not part of the story the context diagram tells, and
drawing it there invited a reader to think the system routinely depends on two model providers. It is
therefore **excluded from Levels 1 and 2 and appears only at Level 3 and in the deployment view** —
an implementation detail of the hypothesis service, documented where implementation details belong.
The consequence at Level 1 is a sharper claim rather than a weaker one: the hosted AI provider becomes
the only system EM Fusion reaches over a network, which is precisely what `docs/em_fusion_v2.md` §10
and §12 assert.

Removing it from the model altogether was considered and rejected. The distinction that settles it is
between *silent* meaning "does not interrupt the analyst" and *silent* meaning "undisclosed". §12
commits to the first and explicitly forbids the second — the degradation must reach the analyst as a
visible attribution of which generator produced a hypothesis, never as an error state and never as an
unmarked substitution. An architecture that cannot answer "what happens when the API is down" leaves
that reliability claim unsupported, and a fallback is by definition a designed path with a named
trigger rather than an accident. The legitimate route to removal is to *cut the local arm* — which
§10 already sanctions if its time-box expires — and that is a scope decision touching §10, §12,
and two build phases, not a change to a diagram.

Second,
schema validation and the grounding check are modelled as **two components rather than one**, against
the single "Schema Validation + Grounding Check" node in `docs/em_fusion_v2.md` §7. They are separated
because the grounding catch rate is a per-arm reportable result of the evaluation, and a mechanism the
thesis reports on separately should be legible as a separate thing in the architecture that produces
it.

The two seams carrying the RQ1 extensibility argument — the adapter-to-DAL seam and the
hypothesis-service-to-generator seam — are given distinct visual styling. This is presentational, but
deliberately so: the claim the diagram exists to support is that a new source or a new generator
attaches at one identified place, and a diagram in which those places are indistinguishable from every
other box does not make the argument.

#### What drawing the model revealed about the planned architecture

The checklist predicted that a container diagram which is awkward to draw usually indicates the
boundaries are wrong, and that drawing it early would therefore be cheaper than drawing it at Phase 7.
That prediction held, in three specific ways, all of which are divergences from
`docs/em_fusion_v2.md` §7 rather than errors in it.

The §7 flowchart shows a single linear pipeline from source to analyst and does not distinguish
process boundaries. Drawing it at Level 2 forced the question of what runs *when*, and the answer is
that the scenario runner and evaluation harness are a batch entrypoint into the same image as the API
rather than part of any request path. This is not a change to the design; it is something the design
always implied and never stated, and the container diagram cannot avoid stating it. It matters to the
write-up because the reproducibility claim rests on the batch path being deterministic and the serving
path being irrelevant to it.

The §7 flowchart has no edge carrying analyst feedback back into the AI layer, and this is correct —
the system does not learn from verdicts. But the absence only becomes legible once the diagram is
drawn and the reader can see that no such edge exists. That negative space is arguably the clearest
single statement in the model that this is decision support rather than a learning loop, and it is
worth pointing at explicitly in the Design chapter rather than leaving the reader to notice it.

The third divergence is a factual correction rather than a framing one, and it was resolved by
changing the system rather than the sentence. `docs/em_fusion_v2.md` §10 states that the hosted AI
generator is the sole hosted dependency, and §12 goes further — the data and map layers have *no
hosted dependency at all*, "archived replay, tokenless tiles". Both claims were used to justify
MapLibre over Mapbox. Drawing the Level 1 context diagram surfaced a system neither claim accounted
for: **the basemap tile source, which the browser fetches from directly**. The error underneath was a
conflation of *tokenless* with *self-hosted*. MapLibre is a renderer and ships with no map data;
requiring no account for the library says nothing about where its tiles come from, and the default
answer is someone else's server.

The resolution taken is to **self-host the basemap**, which makes both claims literally true rather
than nearly true. A vector basemap covering the project's bounding box — the same box already fixed
for the OpenSky extract — is cut as a single PMTiles archive from a Protomaps build of OpenStreetMap
and served over HTTP range requests by the nginx container that already serves the frontend bundle.
This costs nothing, adds no Compose service and no tile-server process, and has the secondary benefit
of making the offline demonstration in §12 complete rather than partial: with the basemap local, the
hosted generator is the only thing the system reaches for over a network.

Vector rather than raster was chosen on design grounds rather than technical preference. Raster tiles
arrive pre-rendered, carrying whatever colour scheme their renderer baked in; vector tiles carry
geometry and attributes and are styled by the client at render time. The operational picture is
exception-first — its entire premise is that anomalies are the salient thing on screen — and a bright
standard-OpenStreetMap basemap composited under dark anomaly overlays competes with exactly the signal
the screen exists to foreground. With vector tiles the basemap style is written from the same
`DESIGN.md` tokens as the rest of the interface and can be deliberately subordinated. Continuous zoom
and upright, collision-managed labels follow as secondary benefits.

Two obligations follow, recorded now because both are cheaper to capture than to reconstruct.
OpenStreetMap data is licensed **ODbL**, so "© OpenStreetMap contributors" must be rendered on the
map — the same class of requirement as the OpenSky licence note, and captured at download time for the
same reason. And a vector style references **fonts and sprite assets by URL**, which default styles
point at a CDN; these must be self-hosted alongside the archive, or the hosted dependency just removed
returns silently with the map still rendering perfectly.

This sequence is the clearest example in the project of the model doing the job it was built for. A
sentence repeated across several documents without challenge failed the first time the system was
drawn as boxes and arrows, and the correction improved the system rather than merely qualifying the
claim.

*(Record here whether the .pmtiles archive was committed or downloaded against a checksum, and its
size, once Phase 4 lands.)*

*(Revisit this entire subsection at the end of the build and record the divergence between the model
as drawn now and the architecture as actually built, per the Track 0 checklist. The divergence is
itself write-up material: an architecture documented once at planning time and never revised is a
weaker artefact than one whose revisions are on record.)*

#### Tooling notes

Structurizr's tooling was consolidated during the project into a single `structurizr/structurizr`
Docker image with subcommands; the standalone `structurizr/lite` image and the separate
`structurizr/cli` image are superseded, and the latter now emits an end-of-life notice. The model is
rendered locally via `structurizr local`, never through the hosted structurizr.com workspace, which
keeps the account-free stance intact for this part of the toolchain.

One limitation constrains the thesis figures directly: **the Docker build does not support PNG or SVG
export**, reporting that the operation is unsupported regardless of the `-url` option it advertises
for the purpose. Image export is a manual action in the browser UI. Text exports (Mermaid, PlantUML,
JSON, DOT) do work from the command line, and it is those that preserve the regenerability property —
the exported images are downstream artefacts of a model that remains generated from source even though
the images themselves are produced by hand.

The DSL deliberately omits `theme default`. The default theme is fetched at render time from
`static.structurizr.com`, a service scheduled for end of life on 30 September 2026. That date falls
after submission but well within the useful life of the thesis as a document, and a model whose
rendering silently degrades once a third-party service is switched off is not regenerable in the sense
that motivated choosing a text-based model in the first place. The element styles are therefore
written out in full in the workspace, which is more verbose and entirely self-contained.

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

**A narrow, deliberate exception: Parquet as archive format.** The archived OpenSky extract is stored
as Parquet and committed to the repository. This is not the rejected decision creeping back in, and
the distinction is worth stating precisely because it would be easy to mistake one for the other. The
lakehouse proposal was about the **read path** — making Parquet-on-object-storage the substrate that
queries run against, which is what would have cost the indexed spatial join. Using Parquet as a
*container for a static, committed input file* touches none of that: the file is read once at replay
time, converted through the adapter and DAL, and written into PostGIS, which remains the sole query
substrate. Parquet was chosen over CSV because it is typed and compresses well enough that a
bounding-box-filtered hour can be version-controlled, which removes the download step and makes the
pipeline reproducible from a fresh clone — a reproducibility gain, not an architectural one.

The general point for the write-up is that a format decision and a substrate decision are different
decisions, and conflating them is how a rejected architecture returns unnoticed. The test applied
here was simple: does anything *query* the Parquet? Nothing does, so the PostGIS justification is
untouched. Recording the test is more useful than recording the outcome, because the same question
will arise again for the evaluation exports (`eval-003`), which stay CSV/JSON for the opposite
reason — they are read by humans and spreadsheets, not by the system.

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

### AI hosting: a hosted frontier model, with a local model as fallback

> **Partially superseded.** The argument below for retaining the local model as a *scored second
> evaluation arm* was subsequently withdrawn — see "Scored arms: withdrawing the local model from the
> evaluation while keeping it in the system" in Methodology. It is left in place unedited because the
> reversal is only legible against the position it reversed, and because everything else in this
> section — the case for hosted-primary, the reproducibility trade, the deliberate spend — still
> stands. Read the two together.

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
load**: three arms is three times the blind-rubric pairs, which may exceed what the available raters
can score. The plan at the time was hosted-vs-template at full N as the primary comparison with
local-vs-hosted as a smaller secondary sample, fixed before the campaign rather than adjusted after
seeing results. *This risk was subsequently resolved by withdrawing the third arm entirely — see the
Methodology entry. Recording it here is worthwhile precisely because it shows the constraint was
visible in advance and initially met with a partial mitigation that, on reflection, would not have
produced an interpretable secondary result.* Second, **data egress**: evidence bundles now leave the
machine. All content is synthetic or
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

### Containerisation: a Makefile over Compose, and what the first working `up` exposed

The three services (backend, frontend, and a profiled one-shot pipeline) are driven through a root
`Makefile` rather than by memorised `docker compose` invocations. The motivation is the same one behind
committing the OpenSky extract: a reader reproducing the system should reach a running stack by a
documented command, not by reconstructing a sequence of flags. The targets are adapted from an earlier
project of the author's, which is worth noting for a reason beyond provenance — the `ensure-artifacts`
pattern it contributed does not fit this system, and the misfit is the informative part. That pattern
guards a demo by regenerating pipeline outputs when they are missing from disk. EM Fusion has almost no
such outputs: the aviation extract is committed rather than generated, and synthetic observations are
regenerated byte-identically from a seed under `scn-001`, so the seed *is* the artefact. The target was
kept with an empty guard list rather than deleted, on the grounds that its shape is right for whatever
the pipeline eventually persists. That is a defensible choice but it carries a cost worth stating: an
unexercised guard is untested, and the first artefact added to it should be verified against a
deliberately deleted file rather than assumed to work.

More useful to the Implementation chapter is what the first genuinely-running stack revealed. The
Compose file had been written before it had ever been run, and it contained four independent faults, of
which only one — a YAML indentation error — announced itself. The other three were silent: a service
calling a package manager absent from its image, a profile on every service so that `docker compose up`
started nothing at all, and a published port mapped to a container port nginx was not listening on. Two
further faults appeared only once the services were up together: `nginx.conf` proxied to a hostname
(`api`) that did not match the service name (`backend`), and the container healthcheck polled a route
(`/api/v1/health`) the application did not then serve. Both of these are invisible to any single-service
test — each container reports itself healthy while the path between them is broken — which is the direct
justification for `scripts/smoke-test.sh` asserting the frontend-to-backend proxy hop as a first-class
check rather than only checking that each service responds. The general observation, and the one that
belongs in the write-up, is that integration configuration fails differently from code: it fails by
silence rather than by exception, so it needs a test that exercises the joins, not the parts.

### Database container: the official image emulated, and what that costs

PostgreSQL with PostGIS joined the Compose stack ahead of any code that uses it, which is the right
order given that the storage substrate decision (recorded above) rests on the indexed spatial join
being available rather than aspirational. One property of the image was not anticipated: `postgis/postgis`
publishes **amd64 builds only**, at every tag, so on the Apple Silicon development machine the pull
fails outright rather than degrading. The choice is therefore between the canonical image running under
emulation and a third-party multi-arch rebuild running natively, and it was resolved in favour of the
official image with `platform: linux/amd64`.

The reasoning is worth recording because the first recommendation was the other way round, on
performance grounds, and performance was the wrong thing to optimise. A thesis that cites its
dependencies is better served by the image its upstream project actually publishes than by a faithful
but third-party rebuild; provenance is the claim being made, and emulation does not weaken it, because
the emulated container runs a genuine x86-64 build with identical behaviour.

The cost was measured rather than assumed. The same spatial predicate over 200,000 generated points ran
in **3231 ms** emulated (`platform: linux/amd64`, reporting `x86_64`) against **1314 ms** on a native
arm64 rebuild of the same PostGIS version — roughly 2.5×. Conditions: one run each on the same host,
warm, no cache control, and the two containers differed in volume configuration, so this is indicative
of the order of magnitude and not a benchmark.

The threat to validity this creates is narrow but must be stated. Detection latency is a reported
evaluation metric, and it is defined in *simulated* scenario time rather than wall clock, which
insulates the headline figures from the emulation factor entirely. What emulation does affect is any
wall-clock claim about query or pipeline throughput — including the spatial-join performance argument
used to justify PostGIS over alternatives. If such a figure is reported, it must carry the emulation
condition, or be taken on an amd64 host where the image runs natively.

### Backend dependencies: a lockfile, chosen for reproducibility rather than ergonomics

Dependencies moved from `requirements.txt`/`requirements-dev.txt` into `pyproject.toml` with a committed
`uv.lock`. The consolidation of dependency declaration and tool configuration into one file is the
visible change; it is not the important one. The important one is that the previous dependency list
carried **no version constraints at all** — `fastapi`, `uvicorn`, `pydantic`, unpinned — so a clone
resolved at write-up time would install different versions than the ones any measurement was taken
under. That sits badly beside the reproducibility argument already made for committing the aviation
extract (`em_fusion_v2.md` §3): it is inconsistent to eliminate a download step for the data while
leaving the software environment free to drift. A lockfile closes the same gap on the other axis, and
the claim the thesis can then make is the stronger one — that a fresh clone reproduces both the input
and the environment that processed it.

`uv` was selected over plain `pip` for a specific mechanical reason rather than for speed. Installing
from `pyproject.toml` with `pip install .` requires the package source to be present in the same layer,
which collapses the dependency install and the source copy into one Docker layer and makes every source
edit reinstall the full dependency set; `uv sync --no-install-project` separates them and preserves the
cached layer that the original two-file split existed to protect. One tool initially resisted the consolidation:
flake8 does not read `pyproject.toml` by maintainer decision, so `.flake8` survived the first pass as
the single exception. It was judged a small enough residue to accept — and then, within the same
session, not accepted: flake8 and isort were both replaced by `ruff`, which reads `pyproject.toml` and
implements both, leaving the backend with no tool configuration outside that one file.

The sequence is worth recording because it is a small case of a pattern the Implementation chapter can
name. The residue was tolerable in isolation; it stopped being tolerable once the goal was stated as
*one file*, because a consolidation that is 90% complete still requires every reader to know which
tool is the exception and why. The cost of finishing was low precisely because the change was
mechanical — the rule set `["E", "F", "W", "I"]` reproduces flake8's defaults plus isort — and because
it was verifiable: black reported all seven source files unchanged afterwards, so the linter swap
altered no source byte. The formatter was deliberately not swapped at the same time, although ruff
offers a black-compatible one, on the grounds that a formatter change rewrites files and a linter
change does not; bundling them would have hidden a reformatting diff inside a tooling commit.

One honest limitation attaches to the swap. Ruff's whitespace rules (`E1`/`E2`/`E3`, including missing
whitespace around an operator) are preview-only and therefore inactive under a stable release, so a
small class of formatting defect that flake8 rejected now passes the linter. This is covered rather
than ignored: black normalises all of those cases, and the `check` target runs formatting before
linting, so the exposure is limited to invoking the linter alone on unformatted code. It is recorded
here rather than left implicit because "we replaced flake8 with ruff" reads as a pure superset claim,
and it is not quite one.

### Container hardening: the port number as a consequence of the user, not a choice in itself

The frontend container was moved to `nginxinc/nginx-unprivileged`, listening on 8080 as uid 101 rather
than on 80 as root. The reasoning is worth recording because the intuition that prompted it was aimed
at the wrong mechanism: the suggestion was to change the Dockerfile's `EXPOSE` directive from 80 to
8080 "for security". `EXPOSE` is metadata — it declares intent to `docker run -P` and to human readers,
and it opens, closes, and binds nothing, so changing it in isolation would have produced an image whose
documentation disagreed with its behaviour. The property actually wanted was that the process not run
as root, and that requirement is what determines the port: binding below 1024 requires root or
`CAP_NET_BIND_SERVICE`, so a non-root container must listen at 1024 or above. The port number is
downstream of the user decision, not parallel to it. The published host port is unchanged either way,
which is precisely why the distinction is easy to miss — the observable behaviour from a browser is
identical, and only the container's privilege level differs.

### API surface: a versioned prefix adopted while it was still cheap

Routes moved behind an `/api/v1` prefix declared once by a single `APIRouter`, with one module per
resource under `app/api/v1/` rather than a shared `routes.py`. The version prefix is conventional and
its direct benefit to a prototype that will never ship a v2 is admittedly slight; the argument for
adopting it now is that its cost is monotonically increasing. Applied while a single route existed, it
touched five spec items, three documents, and two proxy configurations. Applied after the operational
picture, hypothesis, feedback, and scenario endpoints exist, it would touch all of them plus the
frontend API module and every test asserting a path.

The change also demonstrated a coupling that had not previously been visible. Both proxies in front of
the backend — nginx in the container, Vite in development — had been configured to *strip* the `/api`
prefix, on the assumption that the backend served bare paths. Moving prefix ownership into FastAPI
required removing the strip in both places simultaneously, and in nginx that removal is a single
trailing slash on `proxy_pass`. The failure mode when it is wrong is a 404 that appears to originate
from FastAPI's router, which points an investigation at the application rather than at the proxy. This
is a small instance of a general point the Implementation chapter can make about layered
deployments: a path is rewritten by several components in sequence, and each one's contribution is
invisible in the others' configuration, so an apparently local change to routing is a distributed one.

The immediate work followed the mandated spec → test → code order, and the sequence was clean because
the route already existed at a different path: `api-001` was amended to name the versioned path, four
tests were written against it and observed to fail (404 on the versioned path, 200 on the unversioned
one, a missing OpenAPI entry), and only then was the router introduced. `api-001` now passes with five
tests at 100% statement coverage of `app/`. The fifth test exists because of a defect encountered during
this work rather than by design: adding `lifespan=` to the `FastAPI(...)` constructor without defining
the referenced function raises `NameError` at *import* time, which crash-loops `uvicorn --reload` and
leaves the container unhealthy while the source file looks correct in an editor. A bare `TestClient`
call does not execute the lifespan at all, so a passing suite would not have caught it; entering the
client as a context manager does. Startup-path code needs a test that actually runs the startup path.

## Evaluation

<!-- Anomaly detection metrics per scenario type (precision/recall/F1/FPR/FNR/latency) at full N;
hypothesis quality rubric results for the two scored arms (hosted vs template) over a stratified
sample of ~20 evidence bundles, fully double-scored — per-dimension means and quadratic-weighted
Cohen's kappa; the residual blinding threat from the template arm's distinctive style;
grounding-check catch rate, grounding variance, and retry rate per arm over all generations, and
local-arm fallback frequency; campaign cost and wall-time per arm; limitations encountered —
including the absence of any analyst-utility measurement following the withdrawal of the task-based
user study, and the absence of a capability-versus-architecture split following the withdrawal of
the local arm from scoring. -->
