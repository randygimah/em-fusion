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

### Bounding box: 49–54°N, 3–11°E, chosen on event-site density rather than coverage quality

The region the corpus covers was fixed on 2026-08-19 at 49–54°N, 3–11°E — roughly 309,000 km² over
the Low Countries, western Germany and Luxembourg. The box is a more consequential choice than it
looks, because it constrains three things at once that are expensive to change independently: the rows
that enter PostGIS, the basemap tile cut for the map view, and the geographic space in which every
scenario run places its injected event.

The selection criterion the checklist anticipated was coverage quality — that a box must have sensor
coverage dense enough that genuine ADS-B dropouts are not mistaken for injected ones. **That criterion
turned out not to discriminate at all.** Measured across eight candidate regions spanning Europe and
the north-eastern United States, every one showed at least 99.97% of consecutive-sample gaps sitting
exactly at the published ten-second cadence. The metric could not separate the candidates because
there was nothing to separate: OpenSky's coverage over populated airspace in 2022 is essentially
complete at this resolution.

Reaching that conclusion required correcting the measurement first, and the correction is the
methodologically interesting part. A naive gap report over each candidate returned maximum gaps of up
to 3,140 seconds — in a file spanning 3,600 seconds — which read as catastrophic coverage failure. It
was not. Those gaps are aircraft leaving the box and re-entering it later, which is a property of
drawing a finite box, not of the sensor network. A second confound sat underneath it: aircraft
stationary on the ground transmit differently from airborne ones, and counting a parked airframe going
quiet as a coverage dropout inflates the same statistic. Restricting the measurement to gaps whose
endpoints are both at least 0.5° inside the boundary and both airborne is what made the number mean
what it claimed to mean. Recorded here because the uncorrected metric was not merely noisy — it
pointed confidently in the wrong direction, and a box could have been rejected on it.

With coverage quality neutralised, the decision moved to a criterion derived from what the scenarios
actually do. Scenario types 2 and 4 inject events confined to roughly a 20 km area, and the evaluation
harness needs 20–30 randomised runs across each of five types, so 100–150 runs must be placed. A box is
therefore only usable if it contains enough distinct 20 km patches carrying enough simultaneous
traffic for an injected effect to have witnesses. Binning airborne samples into ~20 km cells over a
fifteen-minute window and counting cells holding at least five distinct aircraft gives a direct count
of usable event sites, and this did discriminate: from 132 sites for the tightest candidate to 556 for
the widest.

The chosen box offers 263 such sites against a ceiling of 150 runs, giving enough headroom that
randomised placement need not reuse locations — reuse would correlate runs that the evaluation treats
as independent, which is why the cheapest candidate, at 132 sites, was rejected despite being the
cleanest on every other measure. The widest candidate, 47–55°N/3–15°E, was rejected on the opposite
ground: it offers 2.1× the event sites for 2.4× the tile area and 1.9× the rows, which is proportional
scaling rather than a better trade, and it carries a lower per-cell aircraft density (median 3 against
4) alongside nearly double the confound rate discussed below.

One defect found during the sweep is worth recording because no metric would have surfaced it. An
earlier shortlisted box began at 5°E, which places both Amsterdam Schiphol (4.76°E) and Brussels
(4.48°E) outside the corpus — the two busiest fields in the region, excluded by a boundary drawn to a
round number. The metrics for that box were unremarkable rather than alarming; it simply looked like a
slightly quieter region. Moving the western edge to 3°E added 306 aircraft and 64 event sites for a
33% area increase, the best return in the entire sweep. **The general lesson, and one that transfers
to the scenario placement work: a geographic filter should be checked against named landmarks it ought
to contain, not only against aggregate statistics, because a statistic cannot report what it never
saw.**

**Threat to validity, stated in advance of the evaluation.** The natural dropouts that remain, though
rare, occupy the same duration band that scenario type 4 will inject into. Within the chosen box the
ten surviving interior airborne gaps measure 20, 100, 110, 200, 280, 280, 300, 970, 1,160 and 1,440
seconds — seven of the ten falling between 100 and 300 seconds, which is squarely where a plausible
injected coverage gap sits. This is the confound `adp-004` names as a failure case, and it is present
rather than avoided. Its magnitude is small and now quantified: it touches 10 of 948 tracks, or 1.05%,
against 1.84% for the widest candidate rejected above. It is also mitigable rather than merely
tolerable, because the coverage report identifies exactly which tracks carry a natural dropout, so the
scenario generator can refuse those tracks as injection sites and the evaluation can account for the
exclusion. *(Record here whether that exclusion was implemented in the generator, and the measured
false-positive rate on scenario type 4 with and without it.)*

A second limitation follows from the null-position retention rule rather than the box. The 500
retained rows with no coordinates are drawn in file order from the whole hour, not from within the
box, since a row with no position cannot be tested against a boundary at all. The extract therefore
contains 1,445 distinct aircraft while only 948 have any in-box position, and a count of distinct
airframes in the extract overstates in-box traffic by roughly half. This is harmless to the detection
path — such rows can only reach quarantine, never a canonical observation — but any descriptive
statistic quoted about the corpus needs to say which of the two counts it means.

### What the replay corpus actually contains

The extract is not committed and cannot be, so this section records its shape and a worked slice of
its contents — enough that a reader can follow every later claim about detection without access to
the file itself.

**Licence position for this section.** `thesis_notes.md` is committed and is dissertation material,
which makes it publication in the sense the OpenSky Data License Agreement §3(i) intends. The slice
below therefore has `icao24` and `callsign` replaced by pseudonyms, exactly as the canonical model
does. The pseudonyms shown were generated with a deliberately *illustrative* seed rather than the
corpus seed, so they do not correspond to the labels under which any measurement in this document was
taken and cannot be cross-referenced against them. The remaining fields are position and telemetry
values carrying no aircraft identity, shown for five rows as illustration rather than redistribution.
Required attribution: The OpenSky Network, http://www.opensky-network.org (Schäfer et al., 2014).

#### Columns

One row is one aircraft's state at one ten-second frame. Sixteen columns survive the extraction:

| Column | Type | What it holds |
|---|---|---|
| `time` | int64 | Frame timestamp, UNIX seconds. The cadence axis: 360 distinct values across the hour |
| `icao24` | string | Transponder address. **Kept as a string** — inferred as an integer, `004321` becomes `4321`, and airframes collide silently |
| `lat`, `lon` | float64 | Position in degrees. Null on 500 retained rows, which is what gives the quarantine path real input |
| `velocity` | float64 | Ground speed, m/s. Null on 23,585 rows |
| `heading` | float64 | Track angle, degrees |
| `vertrate` | float64 | Vertical rate, m/s. Negative is descending |
| `callsign` | string | Flight identifier, space-padded to a fixed width. Blank on 3,754 positioned rows |
| `onground` | bool | Surface or airborne. Never null |
| `alert`, `spi` | bool | Transponder flags. Not carried into the canonical payload |
| `squawk` | string | Mode A code, string for the same leading-zero reason as `icao24`. Sometimes empty |
| `baroaltitude` | float64 | Barometric altitude, m. The canonical `altitude_m` |
| `geoaltitude` | float64 | GNSS-derived altitude, m. Null wherever `baroaltitude` is |
| `lastposupdate` | float64 | When the *position* was last refreshed. Null on exactly the 500 null-position rows |
| `lastcontact` | float64 | When *any* message was last received. Never null, on any of the 133,634 rows |

The last two are the ones to read carefully, because the difference between them is a detection
signal rather than bookkeeping — see the `contact_staleness_s` subsection under System Design and
Architecture.

#### A worked slice

Five rows chosen to span the shapes the adapter and the DAL must handle. `→` gives the two derived
staleness values in seconds.

**Row 0 — nominal, airborne.** The common case: everything reported, position 1.06 s old.

```
time 1656331200   icao24 AC-48089ab4e5a9   callsign FL-0c53755a34bc
lat 51.0905  lon 7.5473  onground False  squawk '2556'
velocity 194.26  heading 135.64  vertrate 13.33
baroaltitude 5753.1  geoaltitude 5951.22
lastposupdate 1656331198.94   lastcontact 1656331200.0
→ position_staleness_s 1.06    contact_staleness_s 0.00
```

**Row 8969 — fresh contact, stale position.** The GNSS-degradation signature in real data, and the
single clearest argument for carrying both staleness fields. The aircraft is airborne at 10,607 m and
was heard from **1.35 seconds ago**, so it is emphatically not a coverage gap — yet the position
being reported is **209 seconds old**. A model carrying only position staleness would render this
indistinguishable from an aircraft that had dropped out entirely.

```
time 1656331460   icao24 AC-c62771cc89ff   callsign FL-285500f7594b
lat 49.6308  lon 6.2136  onground False  squawk '1000'
velocity 23.01  heading 259.70  vertrate -0.33
baroaltitude 10607.04  geoaltitude None
lastposupdate 1656331250.527   lastcontact 1656331458.649
→ position_staleness_s 209.47   contact_staleness_s 1.35
```

**Row 2122 — airborne, no altitude at all.** Both altitude columns null, and a blank callsign. Two of
the model's optionality decisions exercised by one row: `altitude_m` is `None` rather than zero, and
`flight_id` is absent rather than a pseudonym of the empty string.

```
time 1656331260   icao24 AC-ddba5357390a   callsign (blank)
lat 53.5227  lon 6.8907  onground False  squawk ''
velocity 78.42  heading 308.07  vertrate -0.33
baroaltitude None  geoaltitude None
lastposupdate 1656331257.584   lastcontact 1656331257.584
→ position_staleness_s 2.42    contact_staleness_s 2.42
```

**Row 122 — on the ground.** Note the negative barometric altitude: −15.24 m is a real reading, since
barometric altitude is pressure-derived and uncorrected, not a height above terrain. A validation
rule rejecting negative altitudes would quarantine legitimate surface traffic.

```
time 1656331210   icao24 AC-4d2ca0fb6595   callsign FL-3785a36267b2
lat 52.3192  lon 4.7433  onground True  squawk '1000'
velocity 50.99  heading 182.89  vertrate 0.0
baroaltitude -15.24  geoaltitude None
lastposupdate 1656331197.797   lastcontact 1656331209.673
→ position_staleness_s 12.20   contact_staleness_s 0.33
```

**Row 12 — no position, so it quarantines.** One of the 500 rows retained deliberately by `adp-004`.
The aircraft is being heard from perfectly well — contact staleness 0.00 s — and even reports an
altitude, but has no coordinate, so it cannot be placed and `lastposupdate` is itself null. The
adapter emits it unchanged and the DAL rejects it on `location`; nothing is invented to make it fit.

```
time 1656331210   icao24 AC-5fd6265ff4c5   callsign (blank)
lat None  lon None  onground False  squawk '3612'
velocity None  heading None  vertrate None
baroaltitude 388.62  geoaltitude None
lastposupdate None   lastcontact 1656331210.0
→ position_staleness_s None    contact_staleness_s 0.00
```

#### What row 0 becomes

The same row after the adapter's translation and the DAL's validation, provenance and
pseudonymisation, which is the transformation the whole Data Abstraction Layer exists to perform:

```
CanonicalObservation(
    source_id='opensky-replay', source_type=OPENSKY, observation_type=TRACK,
    timestamp=2022-06-27T12:00:00+00:00,
    location=Location(lat=51.0905, lon=7.5473),
    data_mode=REPLAYED, validation_status=VALID,
    provenance=Provenance(source_id='opensky-replay', source_type=OPENSKY,
                          data_mode=REPLAYED, scenario_run_id=1),
    payload=TrackPayload(aircraft_id='AC-…', flight_id='FL-…',
                         altitude_m=5753.1, velocity_ms=194.26, heading_deg=135.64,
                         vertical_rate_ms=13.33, on_ground=False,
                         position_staleness_s=1.06, contact_staleness_s=0.00),
)
```

Four things happened that no adapter did: provenance was attached, the run was recorded, the two
identifiers were replaced, and the record was marked validated. Three source columns — `alert`, `spi`
and `squawk` — were dropped as carrying nothing the detection rules read.

## System Design and Architecture

<!-- Actual architecture as built vs as planned (docs/em_fusion_v2.md section 7) and why it
diverged, if it did. DAL design decisions, canonical data model decisions, key diagrams. -->

### Identifier pseudonymisation placed at the DAL rather than in the adapter

The OpenSky Data License Agreement §3(i) obliges the licensee to de-identify aircraft identifiers for
any publication or other disclosure. `icao24` and `callsign` are aircraft identifiers, and they reach
three surfaces that both count as disclosure: figures in this dissertation, evidence bundles sent to
the hosted AI provider, and any screen captured for the write-up. The obligation was discovered on
reading the licence that ships inside the data tarball, after the corpus was downloaded but before any
replay code existed — which is the only reason it cost nothing.

The design question was *where* the substitution belongs. Placing it in the OpenSky adapter is the
obvious answer, since `icao24` is an OpenSky field and the adapter is where OpenSky's vocabulary is
supposed to be confined. It was rejected. The DAL exists precisely so that obligations holding across
every source are discharged in one place, and the project already makes that argument once, for
provenance: `dal-003` attaches provenance at the DAL "so it cannot be forgotten by a new adapter". A
de-identification obligation is the same shape of requirement — cross-cutting, silent when omitted, and
consequential — so putting it anywhere else would have contradicted an argument the architecture
already relies on. The extensibility claim in RQ1 is strengthened rather than weakened by this: a third
adapter inherits compliance without its author having to know the licence exists.

Nothing downstream is degraded, because nothing downstream needs the true identifier. The detectors
need *stable identity* across samples to reason about track continuity, not *real identity*, and a
deterministic seeded mapping supplies exactly that. This is pseudonymisation rather than anonymisation
in the strict sense — the link between records is deliberately preserved and only the link to the real
airframe is severed — and the distinction is worth stating explicitly in the write-up, because a claim
of "anonymised data" would be too strong for what is actually done.

Two details are deliberate. The source values are **discarded** rather than carried alongside the
pseudonym, since retaining them would satisfy the mapping while leaving the real value one query away.
And the pseudonym carries no information from its input, so airline prefixes in a callsign and country
blocks in an `icao24` allocation do not survive into it — a pseudonym that preserved either would leak
the thing it exists to remove.

The seed governing the mapping is held **separately from the scenario seed**, and the reasoning is worth
recording because the obvious alternative fails in a way that is easy to miss. The archived corpus is a
single replayed hour, so the same airframes appear in every run of a batch; deriving the pseudonym from
the scenario seed would give one aircraft twenty-five different labels across a twenty-five-run batch,
making cross-run comparison and any manual inspection of a suspected false positive far harder than it
needs to be. It would also have collided with `scn-001`, which requires two runs sharing a type,
parameter set and seed to emit byte-identical output: a per-run pseudonym draw is exactly the kind of
unseeded variation that guarantee forbids.

The resolution is to treat the mapping as a property of the **corpus** rather than of a run. It is fixed
once when the extract is built, recorded in the manifest beside the extract checksum, and never drawn
per run. `scn-001` is then untouched, because nothing about the mapping varies with the three values it
constrains, and changing the seed becomes a deliberate corpus-level event with a record rather than a
side effect of re-running a scenario.

### Reversal: the pseudonymisation seed is not recorded in the manifest

The specification for `dal-004` required the pseudonymisation seed to be "held as fixed project
configuration and recorded in the corpus manifest", and in the same paragraph required that "no
reverse mapping is persisted anywhere the application can read". Those two clauses cannot both hold,
and the contradiction survived several readings of the item before it was noticed during
implementation. The manifest is committed; the seed is therefore published; and an `icao24` is a
24-bit value, so the space of about 16.7 million addresses can be enumerated against a known seed in
seconds. A published seed *is* a readable reverse mapping. The item forbade the thing it mandated.

The error underneath is a category mistake worth recording, because it is the kind that survives
review by looking like good practice. A seed was being treated as a **salt** — a value whose
publication is harmless and whose recording aids reproducibility. That reasoning is sound when the
input space is large enough to resist exhaustive search, which is the case a salt is designed for: a
password is drawn from a vast and unguessable space, so knowing the salt buys an attacker very
little. A transponder address is drawn from a small and completely enumerable one. In that setting
the seed is not a salt but a **key**, and the confidentiality of the whole scheme rests on it. The
strength of HMAC-SHA256 is irrelevant to this failure and it is worth saying so explicitly: the
cryptography was never the weak link, and reaching for a stronger hash would have addressed nothing.

The resolution keeps what recording the seed was actually for and discards what it cost. The seed is
read from the environment, with its key documented in `backend/.env.example` under the convention
already established for secrets, and deliberately given no default — a default seed is a committed
seed under another name. What the manifest records is `pseudonym_seed_sha256`, a commitment to the
seed rather than the seed. A corpus therefore remains attributable to the seed that built it, and
changing the seed remains a detectable corpus-level event sitting beside the extract checksum rather
than a silent one, which is precisely the property the original clause was reaching for.

**The resulting limitation is real and belongs in the write-up rather than in a footnote.** The
mapping is now machine-local: a reader who accepts the OpenSky licence and rebuilds the corpus
supplies their own seed and obtains different pseudonyms from the ones appearing in this
dissertation. The cost is narrower than it first appears, because nothing downstream reads a
pseudonym's value — it is an opaque grouping key, and detection, spatial clustering, evidence
bundling and rubric scoring are all invariant under relabelling. Every reported metric therefore
reproduces exactly. What does not reproduce is a specific label quoted in a figure.

That trade is the correct one rather than a reluctant compromise, and the reasoning generalises. A
figure whose pseudonyms a reader could resolve back to real airframes is exactly the disclosure
§3(i) prohibits, so cross-machine label stability and the licence obligation are in direct
opposition — there is no arrangement that delivers both. Recognising that they were in opposition,
rather than assuming both were available, is what the implementation pass contributed.

This is the second occasion in the project on which a licence obligation was found to be
misunderstood only when the code that had to satisfy it was written, the first being the reversal on
committing the extract recorded in the Methodology chapter. Both were caught before any data had
been disclosed, and in both cases the cost of the correction was a design change rather than a
migration. The pattern is worth naming honestly in the write-up: reading a licence carefully is
necessary but was not, in either case, sufficient — what surfaced the defect was the attempt to
build a mechanism that satisfied it.

### The canonical model has no field for a source aircraft identifier

The entry above settles that pseudonymisation belongs at the DAL rather than in the adapter. Building
the canonical model raised a narrower question it did not settle: what the model should look like
*between* the point where the adapter reads `icao24` out of the corpus and the point where the DAL
replaces it. The obvious answer is that a canonical observation carries `icao24` like any other field
and `dal-004` overwrites or removes it downstream. That was rejected. The model instead has no field
anywhere in its tree — observation, payload, or provenance — capable of holding `icao24` or `callsign`
under any name; `TrackPayload.aircraft_id` is opaque by contract, and a unit test asserts the absence
across all four models rather than leaving it to review.

The reasoning is that `dal-004`'s third failure case — retaining the source identifier beside the
pseudonym, which satisfies the letter of the mapping while leaving the real value one query away — is
a failure of omission, and failures of omission are not reliably caught by inspection. A field that
exists can be populated by any adapter author who does not know why it should not be, and the
resulting record is well-formed, passes validation, and looks entirely correct. A field that does not
exist cannot be populated at all. The substitution therefore changes how `aircraft_id` is *derived*
rather than changing the shape of the record, which turns `dal-004` into a function that produces a
value rather than a migration that removes one.

This is the third instance of one pattern in the project, and the repetition is worth naming because
it is closer to a design principle than a coincidence. Confidence is an enum of Low, Medium and High
so that `0.87` is unrepresentable rather than rejected (`ui-001`, `ai-001`). Constrained decoding
makes structurally invalid model output unrepresentable rather than detectable (see "Schema
conformance as a generation-time guarantee" in the Implementation chapter). And the canonical model
makes a licence breach unrepresentable rather than reviewable. In each case a check that would have to
be remembered is replaced by a shape that cannot express the wrong thing. The general form is that a
constraint carried by the type is enforced once and thereafter costs nothing, whereas a constraint
carried by a check is enforced only as often as somebody remembers to run it.

Two limitations attach, and both should be stated rather than left implicit. The guarantee is about
the model's *shape*, not about the provenance of the value an adapter supplies: until `dal-004`
exists, nothing derives `aircraft_id` from `icao24` under a seed, and an adapter could in principle
pass a raw transponder address into an opaque-looking field. What the model forecloses is retention
*alongside* the pseudonym, which is the specific exposure the licence creates; deriving the value
correctly is `dal-004`'s obligation and is asserted there. And the arrangement is free only because it
was made before `adp-001` replayed a single row. Had the model carried `icao24` through even one
campaign, the correction would have been a migration across every stored observation, evidence bundle
and hypothesis — precisely the retrofit the Phase 7 build order was written to avoid. The cost of the
decision is therefore nil, and that is a fact about its timing rather than about its merit.

### Building the DAL before the database, behind a repository port

The planned phase order put persistence (Phase 6) ahead of the DAL and adapters (Phase 7). That order
was inverted: the DAL was built first, with persistence reached through a repository port whose only
implementation during the DAL's own construction is an in-memory fake used by the tests. The
PostgreSQL implementation lands with the schema.

The forcing constraint is the entry above. `dal-004` must precede `adp-001`, because the first
replayed row is the point after which pseudonymisation stops being cheap, and `dal-004` cannot be
built before `dal-001` defines the record it operates on. Building persistence first would have put
the DAL last and `dal-004` last of all, which is the one ordering the licence exposure makes
expensive.

The objection to inverting the order is that it means writing the persistence layer twice. It does
not, and identifying why is the part worth recording. `db-003` already requires that route handlers
obtain data through a repository function and contain no SQL, no session construction, and no spatial
logic — so the seam exists in the specification regardless of when the database is built. What
changes with the ordering is not whether the seam exists but how many implementations it has at the
moment the DAL items are complete. The validation, quarantine routing, provenance attachment and
pseudonymisation are written once either way, because none of them ever touches a database. The
in-memory implementation is not throwaway either: the detectors, the evidence bundle builder and the
grounding check all need canonical observations without a live database, and they reuse it.

The genuine cost sits in one place — the port's signature, which is being designed against a stand-in
more permissive than the thing that will eventually satisfy it. Three specific ways an in-memory
implementation forgives what PostGIS will not were identified in advance and constrained at the model
rather than left to be discovered. Geometry: `Location` carries latitude and longitude as floats and
has no WKT, WKB, or SRID attribute, so the conversion to a geometry column belongs to the repository
and the DAL stays ignorant of PostGIS; a storage-engine type in the port signature would have broken
the seam before it was built. Identity: record identifiers are assigned on write, so the repository
returns persisted objects and no test asserts an identifier literal, which keeps `evb-002`'s
requirement that evidence items resolve to stored records satisfiable under either implementation.
Atomicity: `dal-002` requires a batch of ten records with three invalid to yield seven observations
and three quarantine rows and complete without raising, which is one transaction against a database
and trivially free against two lists in memory — so the port has to express that the two writes
commit together rather than leaving it to be noticed later.

The limitation this ordering leaves open is narrow, and naming it is the reason it is recorded here
rather than in the commit message. Two distinct guarantees are being conflated by the plain reading of
the specification's word "persisted": that the DAL refuses to construct a record with provenance
missing, and that the schema refuses to store one. Only the first is in place when the DAL items pass;
the second is `db-001`'s `NOT NULL` constraints and is asserted there. The specification text for
`dal-002` and `dal-003` was amended to say so explicitly rather than leaving `passes: true` to imply
more than it demonstrates, on the grounds that a backlog item whose failure case reads as a database
guarantee but is proven by application logic is the kind of drift that stays invisible until somebody
checks.

*(Record here whether the port's signature survived the PostgreSQL implementation unchanged, and if
not, which of the three constraints above turned out to be the one that was got wrong. The prediction
is that geometry and atomicity are the risks and identity is not; a wrong prediction is the more
interesting result.)*

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
as Parquet, held locally and deliberately *not* committed — see the licence reversal in the
Methodology chapter. This is not the rejected decision creeping back in, and
the distinction is worth stating precisely because it would be easy to mistake one for the other. The
lakehouse proposal was about the **read path** — making Parquet-on-object-storage the substrate that
queries run against, which is what would have cost the indexed spatial join. Using Parquet as a
*container for a static, committed input file* touches none of that: the file is read once at replay
time, converted through the adapter and DAL, and written into PostGIS, which remains the sole query
substrate. Parquet was originally chosen over CSV for two reasons: that it is typed, and that it
compresses well enough for a bounding-box-filtered hour to be version-controlled, removing the
download step. **The second reason no longer exists** — the licence forbids committing the extract at
all — and it is worth recording that the decision survived losing half its justification rather than
quietly retaining the original wording.

The surviving reason turned out to be much stronger than it first appeared, and the corpus supplies
the evidence. `icao24`, the 24-bit transponder address, is a six-digit hexadecimal *string*, and it is
the field every track-continuity rule groups by. In the downloaded hour, 14,781 rows carry an
`icao24` that contains no letters and begins with a zero. Any read that infers that column as an
integer — which is what happens when a filtered subset contains no letter-bearing values, or when a
chunked reader infers types per chunk rather than per file — turns `004321` into `4321`. The leading
zeros are gone, two aircraft can collide onto one identifier, and nothing raises an error. A CSV
cannot carry a dtype, so the schema would have to live in code and be kept in step with the file by
discipline alone; Parquet carries it in the artefact. This also makes the determinism constraint on
the extraction step (`adp-004`) enforceable rather than aspirational, since "identical row content and
column schema" is checkable against a file that actually records its schema.

The general lesson for the write-up is not about Parquet. It is that a decision can outlive the reason
it was made for, and that the honest response is to re-examine whether the remaining reasons carry it
rather than to treat the original conclusion as settled.

The general point for the write-up is that a format decision and a substrate decision are different
decisions, and conflating them is how a rejected architecture returns unnoticed. The test applied
here was simple: does anything *query* the Parquet? Nothing does, so the PostGIS justification is
untouched. Recording the test is more useful than recording the outcome, because the same question
will arise again for the evaluation exports (`eval-003`), which stay CSV/JSON for the opposite
reason — they are read by humans and spreadsheets, not by the system.

Two low-cost practices are taken from that ecosystem without taking the infrastructure, to be
confirmed as built: the evaluation harness (M9) should export batch metrics as Parquet rather than
CSV (dtypes survive the round trip), and the archived OpenSky pull should be kept as immutable files
with a manifest recording source URL, download date, licence, and checksum. *(Corrected: an earlier
version of this note asserted that Pandas was already a dependency. It was not, and it has not become
one — the extraction pass runs on the standard library's `csv` module and writes through `pyarrow`
alone, which keeps the dependency footprint to the one library that is actually needed for the format
decision above.)*

### The replay adapter holds no clock: a windowed reader, with simulated time owned by the scenario runner

`adp-001` as first written took "a replay position in simulated time", which put a replay cursor
inside the OpenSky adapter — the adapter would know where in the hour the run had reached, and would
advance. That was reversed before any code was written, and the adapter is now a pure windowed
reader: given a half-open window over source time it yields the records falling inside it and keeps
no position between calls.

The decisive argument is a measurement one rather than an aesthetic one. Detection latency in this
project is defined as elapsed *simulated scenario time* from event onset to anomaly emission, never
wall clock, and that definition was fixed deliberately early because it is the metric most easily
rendered meaningless by an implementation detail. A clock inside the adapter would make two
components — the adapter and the scenario runner (`scn-001`) — each hold a notion of "now", and any
drift or disagreement between them lands directly in the latency figure with nothing to reveal it.
Latency would then be measured against a clock that is partly an artefact of how the replay was
paced. One clock, owned by the component that also owns event onset, removes the failure mode
outright rather than mitigating it.

Two lesser consequences reinforce the choice. A stateless reader is testable offline against a
handful of fixture rows with no scenario machinery in scope, whereas a cursor-holding adapter drags
the scenario generator into the test setup for every replay assertion. And the same windowed
signature is what the `track-window` endpoint needs for playback buffering, so the API layer consumes
the adapter's shape rather than working around it.

The alternative — a cursor in the adapter — is not unreasonable in general, and it is the more
conventional shape for a replay component; it was rejected here specifically because this system
*measures* the passage of simulated time and reports the number as a result. Where replay timing is
merely a presentation concern, the trade would run the other way.

### Canonical altitude takes the barometric reading, and the corpus rather than preference decided it

`TrackPayload` carries a single `altitude_m` field, while the OpenSky state vector reports two
altitudes: `baroaltitude`, derived from static pressure, and `geoaltitude`, derived from GNSS. The
canonical model has no field recording *which* reference a stored value came from, so the choice is
lossy and had to be made deliberately rather than by whichever column was read first.

The corpus settled it. Measured over the 133,134 positioned rows of the current extract (bounding box
49–54°N, 3–11°E), `baroaltitude` is null on 30,276 rows and `geoaltitude` on 34,777 — and the null
sets **nest**: every row lacking a barometric altitude also lacks a geometric one, so there are zero
rows that geoaltitude could rescue. A geo-preferred rule and a baro-preferred rule therefore produce
identical coverage, and the coverage argument that would normally decide such a question is simply
absent. The specified fallback from baro to geo is retained for robustness against a re-filtered
corpus over a different box, but on this corpus it provably never fires.

With coverage neutral, two arguments decide it, and the second is specific to this project.
Barometric altitude is a single consistent reference across the fleet, which matters because the
detectors compare aircraft against each other and against rolling baselines; mixing two references
would introduce systematic offsets of tens of metres that vary by aircraft and by conditions, and
those offsets would be indistinguishable from the deviations the system exists to detect. More
pointedly, `geoaltitude` is GNSS-derived, and GNSS degradation is precisely the phenomenon the
scenario generator injects. Preferring it would mean the canonical altitude field is derived from the
signal whose disruption is under study — a coupling that is harmless in this build, since the
replayed telemetry carries no injected effects and the injection happens on the synthetic RF side,
but which would become a genuine confound the moment anyone extended the generator to perturb
replayed positions. Choosing barometric costs nothing now and forecloses that.

The consequence is stated rather than hidden: **30,276 positioned rows, 22.7 per cent of the corpus,
carry a null `altitude_m`.** The canonical model permits it, and `adp-001` forbids the two tempting
repairs — defaulting to zero, which would place a cruising aircraft at sea level, and carrying the
previous sample forward, which would manufacture continuity the source never reported. A rule that
depends on altitude must therefore handle absence explicitly, and that is a real constraint on the
detection layer rather than an incidental data-quality note. *(Record here whether any detection rule
written in Phase 6 turned out to need altitude on more than 77 per cent of samples, and what was done
about it if so.)*

### Reopening the canonical model for `contact_staleness_s`, and why a passing spec item was reverted to do it

`dal-001` was a passing item when this was found, and reopening it was the more expensive of the two
available options. The cheaper one — leave `TrackPayload` alone, ship the adapter as specified, and
add the field later if a detection rule turned out to need it — was rejected, and the reasoning is
worth recording because it generalises beyond this field.

The OpenSky state vector reports two independent recency fields. `lastposupdate` gives the moment the
aircraft's *position* was last refreshed, so `time - lastposupdate` is the age of the coordinate
carried inside a row. `lastcontact` gives the moment *any* message was last received, so
`time - lastcontact` is the interval since the aircraft was heard from at all. The canonical model
carried only the first, and the adapter as first written read `lastcontact` from the file and
discarded it, because `TrackPayload` had nowhere to put it.

That omission is not a data-completeness nicety. The difference between the two fields is what
separates two of the five scenario types from one another:

| Signature | Interpretation | Scenario type |
|---|---|---|
| Contact stale **and** position stale | The aircraft is no longer being heard from | 4, aircraft data-source coverage gap |
| Contact **fresh**, position stale | Still transmitting, but its position has stopped advancing | 2, GNSS degradation / possible interference |

A model that cannot represent the distinction hands the detection layer data in which those two
scenarios look alike. The consequence would not have surfaced as a bug; it would have surfaced as a
mediocre confusion matrix between types 2 and 4 in the evaluation campaign, at a point where the
cause would be hard to attribute and expensive to fix. **That is the general argument: a confound
built into the canonical model is indistinguishable, in the results, from a detector that simply
performs poorly.** Discovering it while the model was still cheap to change was luck, and the luck
came from writing test fixtures with deliberately distinct values for the two source columns and
having to explain what the values meant.

The corpus confirms the mechanism rather than merely permitting it. Over the 133,134 positioned rows,
**4,553 (3.4 per cent) carry a position more than ten seconds older than their last contact**, to a
maximum of 1,552 seconds. The distributions are more persuasive than the count: contact staleness
caps at 299.97 s, which is OpenSky dropping a state vector after roughly five minutes of silence,
whereas position staleness runs on to 1,561 s — precisely because the row keeps being emitted while
the coordinate inside it is frozen. The two fields are measuring different things, and the ceiling on
one of them is what proves it.

The field is **required rather than optional**, decided against the data in the same way the altitude
question was: `lastcontact` is present on every one of the extract's 133,634 rows, including all 500
with no position, so requiring it creates no quarantine that a null position does not already cause.
`position_staleness_s` is the weaker of the two by this measure, absent on exactly those 500 rows.

Process note, since it is a deviation worth owning. `dal-001` was set back to `passes: false` while
the amended shape was unproven, taking the passing count from eight to seven, and returned to `true`
only after the new tests went red and then green. Amending a passing item's description while leaving
it marked passing would have made the flag assert something the tests did not demonstrate — which is
the same failure the `dal-002` and `dal-003` amendments were written to avoid.

### The replay adapter measured against the full corpus

The adapter was exercised against the real 133,634-row extract rather than fixtures alone, and every
figure predicted from the raw Parquet was reproduced through the complete DAL path:

| Measure | Result |
|---|---|
| Accepted as canonical observations | 133,134 |
| Quarantined | 500, all for a null position |
| Repository writes | 1 — the batch commits as one unit of work |
| Wall time, full simulated hour | 2.44 s |
| Observations with no altitude | 30,276 (22.7 per cent) |
| Fresh-contact / stale-position rows | 4,553 |

The last row is the one worth keeping. That figure was derived from the raw columns *before* the
field existed, and arrived at the far end of the pipeline unchanged — so it evidences that
`contact_staleness_s` is computed from the column it claims and not silently transposed with its
neighbour. A leak check over the first 2,000 observations found no `icao24` key and none of three
known transponder addresses, which is `dal-004` holding on real data rather than on fixtures.

*(Superseded 2026-09-04 by the figure below, taken through `adp-007` against PostGIS.)*

#### Re-measured through the replay entrypoint

The figures above were taken with an ad-hoc script that no longer exists, against the in-memory
repository. `adp-007` replaced it with a committed entrypoint, and the run below is reproducible by
anyone with the corpus and the seed:

| Measure | In-memory (2026-08-26) | PostGIS via `make replay` (2026-09-04) |
|---|---|---|
| Rows read | 133,634 | 133,634 |
| Accepted | 133,134 | 133,134 |
| Quarantined | 500 | 500 |
| Batches | 1 | 12 |
| Wall time | ~2.4 s | **14.25 s** |

Persistence therefore costs roughly 5.8 times what reading and normalising cost, and 14.25 s is the
figure that bounds a scenario run rather than the earlier one. Conditions: twelve batches of 300
simulated seconds each, so twelve transactions; both processes in containers; PostgreSQL under
amd64 emulation on Apple Silicon, which the container note elsewhere in this chapter measures at
about 2.5x native, so this is a pessimistic figure rather than an optimistic one.

Four independent cross-checks reproduced in the database what was derived from the raw Parquet
months earlier: 30,276 observations carrying no altitude, 948 distinct aircraft, every geometry at
SRID 4326, and zero rows mentioning `icao24` or `callsign` anywhere in a stored payload. The last is
`dal-004` holding over the full corpus rather than over a fixture.

**The earlier figure was also recorded inconsistently** — 2.44 s in this document against 2.46 s in
`qa.md` and the handoff — which nobody could adjudicate, because the script that produced it was
gone. That is the argument for `adp-007` in one sentence: a measurement whose method is not
committed is not a measurement, it is a memory. Both values are now superseded rather than
reconciled.

#### Two defects that the test suite could not reach

Both were found on the first real invocation, and both are worth recording because they share a
shape: the container is a different environment from the one the tests describe, and the tests
described the environment rather than the deployment.

The first was a path. `DEFAULT_ENV_FILE` was anchored to the repository root, two levels above
`backend/app/` — correct natively, and resolving to `/backend/.env` inside a container where Compose
mounts `./backend` as `/app` and nothing above it exists. `app/corpus/build.py` carries the same
defect and gets away with it only because it is never run in a container. The fix anchors the path
to the package instead, which resolves to the same file both ways.

The second was subtler and is the more useful one. Compose passes `PSEUDONYM_SEED` through from the
host, so an *unset* host variable arrives inside the container as an empty string — present, and
empty. `load_dotenv(override=False)` treats present-but-empty as present, so it declined to read
`backend/.env`, and the replay failed reporting a missing seed with the seed sitting in a mounted
file. Every existing test either set the variable or deleted it; none set it to the empty string,
which is the one state the deployment actually produces. **A test suite that enumerates the states a
developer thinks of will not cover the state the platform generates.** Both defects now carry
regression tests, written after the fix, which is a deviation recorded in the tests themselves.

### Persistence split into three items: connectivity, schema, then repository

The handoff written at the end of the adapter session described the next step as "`db-005` then
`db-001`, at which point the PostGIS implementation of `ObservationRepository` lands". Reading the
spec text back against that sentence showed it conflated two items: `db-001` is schema and
migrations, and the repository layer is `db-003`. The build was therefore sequenced as three items
rather than two, and the decision is recorded here because the reasoning generalises beyond this
instance.

Schema and repository fail differently, at different times, and against differently populated
databases. A wrong column type fails when a migration is applied to an empty database; a wrong
repository fails when a write is attempted against a schema that is already correct. Combined into
one spec item, a red test cannot discriminate between the two, and the item's `passes` flag then
asserts a conjunction rather than a claim. Keeping them separate also preserves an existing
prediction on record — that the repository port's signature would survive the PostgreSQL
implementation unchanged, with geometry and atomicity the risks and identity not — which is only
testable if the schema is already proved when the repository is written. Folded together, a
signature change would be indistinguishable from a schema correction.

The same reading resolved a second boundary. `db-002` requires four reproducibility columns on
`hypotheses` — `generator`, `model_id`, `generation_params`, `raw_response` — "from the first
migration, not a later one", which places the DDL in `db-001` while leaving `db-002` to prove the
null-rejection at the repository boundary. The consequence is that the first migration builds all
six tables, four of which have no consumer for several phases. That is not speculative construction:
a table built late is an ordinary migration, whereas `raw_response` built late — after an evaluation
campaign has run against a hosted model — is a campaign that has to be repeated, and §9 of the
technical specification says as much explicitly.

### The same split again, one level down: the repository and the rule that nothing bypasses it

Reading `db-003` immediately before writing its tests showed that its description had drifted from
what every planning document meant by it. The text specified a *route-handler* constraint — handlers
must contain no SQL, no session construction and no spatial logic, checked by inspecting the route
modules — while the handoff, the notes above and several session summaries all used `db-003` to mean
"implement the repository port against PostGIS". Both are real obligations and both trace to the same
functional requirement, FR-904, which is written as a single sentence with a semicolon in the middle:
a repository layer shall hold all SQL and spatial logic; route handlers shall contain none.

The item was split at that semicolon. `db-003` is now the repository existing and being correct;
`db-006` is nothing bypassing it. The argument is the one already made for splitting `db-001` from
`db-003`, applied a level down: the two fail at different times and against different conditions. A
defective repository fails at write time against a populated database and is caught by its own tests.
A query leaked into a route handler fails nothing at all — the endpoint returns correct data, the
tests pass, and the only cost is architectural, paid later. Fused into one item, `passes: true` would
again assert a conjunction rather than a claim.

The split also fixed a scheduling error that the fused item concealed. The route-handler rule cannot
be proved today, because the only route is `/api/v1/health` and there is nothing for a handler to
bypass. Written as part of `db-003` it would either have been asserted vacuously against an empty set
of modules — a test that passes because there is nothing to check, which is the failure mode recorded
in the note on proving that tests fail — or it would have blocked the repository behind an endpoint
that does not exist. As `db-006` it is scheduled with `api-002`, the first data-serving endpoint,
where the assertion has something to bite on.

*(Record here whether the check was written by parsing the route modules or by matching their source
text, and the result of mutation-testing it with a violation placed in a docstring. The equivalent
check in `dal-004` failed exactly that way once already.)*

### The repository port survived the database unchanged, and the prediction was right for the wrong reason

The `dal-002` repository port was specified and built before any database existed, and a prediction
was put on record at that point: that its signature would survive the PostgreSQL implementation, with
geometry and atomicity the two places most likely to force a change and identity not a risk at all.
The PostGIS implementation is now written, and the outcome is recorded here rather than left implicit
in a passing test, because a prediction that is never scored is not a prediction.

**The signature did not change.** `save_batch` still takes two sequences of Pydantic models and
returns nothing. No session, no ORM model, no WKT or WKB string and no caller-supplied identifier
crossed the boundary, and no parameter was added to accommodate one. Three structural tests now hold
that shape in place, each mutation-tested rather than assumed, so a future widening fails a test
instead of passing review.

The prediction named the right two risks and overstated both. Geometry was a risk, but it resolved
one level below the port: `Location` stays two floats, and the conversion to a point is a single
function inside the repository. Atomicity was a risk, and it resolved at the same level, because the
port's shape had already made it possible — `dal-002` had insisted on one call carrying both
collections precisely so that the implementation would have a transaction to own. In other words the
port survived contact with the database partly because the constraint that looked most likely to
break it was the constraint that had been designed for it. That is a weaker result than "the port was
specified well enough", and the weaker version is the honest one: the guarantee was specified, so the
implementation had somewhere to put it.

The one place identity did enter is worth recording because it was not predicted. Both models carry
enum members that subclass `str`, and passing one to the driver is silently accepted while rendering
as the Python identifier — `SourceType.OPENSKY` rather than `opensky`. That is not a signature
problem and would not have shown up as one; it is a conversion the implementation has to remember,
and the same trap is already documented one field over in the DAL's quarantine attribution. It was
caught here by a test asserting the stored column value rather than the round-tripped model, which is
the general lesson: a round-trip assertion cannot see a transformation that is symmetrical on the way
in and out.

*(Re-record the full-corpus replay wall time against this repository. The figure currently on record
measures the reader and the DAL against an in-memory implementation and is not the number that will
bound a scenario run.)*

### The schema is reflected rather than redeclared, and that is what GeoAlchemy2 is for

The repository needs to know the shape of two tables. The obvious approach is to declare them —
SQLAlchemy Core `Table` objects, or ORM models, listing the columns a second time. That was rejected
because `db-001`'s migration is the single source of truth for the schema, and a second declaration is
a copy that drifts silently: a column renamed in a later revision would fail at write time with an
error naming the copy rather than the schema, which is a long way from the cause.

Reflecting the tables at first use instead leaves exactly one description of the schema in the
repository. It also settles what GeoAlchemy2 is doing in the dependency list. The library was
deliberately excluded at `db-001`, where its only use would have been to hide two lines of explicit
DDL, and a warning filter was added to suppress SQLAlchemy's complaint that it did not recognise the
`geometry` type. That warning was reflection failing. Registering the type is what makes a geometry
column reflectable at all, so the dependency and the removal of the filter are the same change, and
the filter came out in the same commit that added the library rather than being left to be noticed
later. A suppression kept past its cause hides the next unrecognised type as well as the one it was
written for.

The cost is that construction of a repository no longer describes the schema in the source: a reader
has to consult the migration. That is the correct direction for the trade — one description that must
be read elsewhere beats two that can disagree — but it is a real loss of locality and is stated here
rather than glossed.

### The conditional coverage omission was specified twice and needed neither time

`db-001` and then `db-003` both carried a clause requiring the coverage gate to omit live-database
modules when `TEST_DATABASE_URL` is unset. It was removed from `db-001` when four unit tests took
`app/db/migrations.py` to full coverage with nothing omitted. It has now been removed from `db-003`
as well, and the second removal is on different and more interesting grounds.

Here the module genuinely is unexercised without a database: it measures 53 per cent natively against
100 per cent in the container. The mechanism was still not built, because measurement showed the
native suite sits at 97.44 per cent overall — comfortably over the 90 per cent gate — so the omission
would not have unblocked anything. What it would have done is raise the reported figure by hiding a
module that was not run. **A 53 per cent reading is the more informative number**, because it says
something true about the run that produced it, and the containerised run is already the authoritative
one precisely because nothing is excluded there.

The generalisable point is about when a coverage exclusion is legitimate. Omitting code that *cannot*
be exercised in a given environment is bookkeeping; omitting code that simply *was not* exercised is
suppression of a result. The two look identical in a configuration file. Specifying the rule twice
before measuring it, and needing it neither time, is itself the finding: the clause was written from
an assumption about what the numbers would be rather than from the numbers.

### Spatial columns stored as geometry and cast to geography at query time

`db-004` requires that the distance in the spatial clustering query be "computed by PostGIS on
geography, not by application-side arithmetic". Two readings of that constraint were available, and
they produce different DDL.

The literal reading stores the columns as `geography(Point, 4326)` and
`geography(Polygon, 4326)`, so the column type itself makes application-side arithmetic awkward. The
rejected cost is real: PostGIS implements a substantially smaller function set over geography than
over geometry, and operations other than distance are slower, which matters because the spatial
clustering in the detection phase is not purely a distance query.

The chosen reading stores `geometry(Point, 4326)` and `geometry(Polygon, 4326)`, GiST-indexed, and
casts to geography inside the query where true-metre distance is wanted. This satisfies the
constraint as written — the arithmetic remains PostGIS's, not the application's, which is the
property the requirement exists to guarantee — while keeping the full geometry function set
available. The distinction the requirement is actually drawing is between a spatial database doing
spatial work and Python computing haversine distances in a loop; a cast falls unambiguously on the
correct side of that line. What the choice gives up is that the geography semantics are re-asserted
at every call site rather than once in the schema, so a query that forgets the cast silently
computes distance in degrees. That is a testable failure — `db-004`'s own boundary case, a
discontinuity just outside the radius, catches it — and it is recorded here as the price paid.

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

### Migrations with Alembic, and the database-backed test tier they forced

Neither the requirements nor the technical specification named a migration tool: FR-906 asks only
for "a documented migration convention", and the build checklist suggested "even a simple
ordered-SQL-files convention" would do. Plain ordered SQL files were genuinely attractive, because
DDL is the most legible possible artefact for a thesis appendix and adds no dependency.

They were rejected on the strength of `db-001`'s own failure case, which requires that applying
migrations twice from empty must not error. Satisfying that means recording which files have been
applied, in a table, transactionally, and getting the ordering guarantee right — which is a
description of Alembic's `alembic_version` table. Hand-rolling it would mean writing and testing
infrastructure that a mature dependency already provides, and the resulting code would need its own
spec item to be trustworthy. Alembic was therefore adopted with revisions written by hand and
autogenerate switched off, the latter because autogenerate does not understand PostGIS geometry
columns and would emit a migration that nobody had read. The third option considered — letting the
`postgis` image's `/docker-entrypoint-initdb.d` apply the DDL — was discarded outright: it fires
only against an empty data directory, so it cannot migrate an existing database, and a silently
skipped initialisation step is a failure mode this project has already observed once with the
PostGIS extension itself.

That decision forced a second one. Until this point the backend suite ran with no database at all,
at 99.83 per cent coverage, and `db-005` deliberately preserves that property by requiring engine
construction to be lazy and to open no connection. `db-001` cannot inherit it: a migration that has
never been applied is an untested migration, and asserting that DDL is correct by reading it is the
same class of error as asserting a test failed without running it. The tests therefore run against a
disposable database in the `postgis` service that Compose already starts, carry a marker, and skip
when `DATABASE_URL` is absent — so the native `backend/make check` remains runnable without Docker
while the containerised surface runs the full set. The alternative, testcontainers-python starting
its own container per session, was rejected on measured grounds rather than on principle: the same
image was previously timed at roughly 2.5 times slower under amd64 emulation on this development
machine, and paying that on every run to avoid a marker is a poor trade.

A third decision followed from the second, and it is the one most likely to be got wrong quietly. With
database tests skipping when no database is reachable, the modules they exercise are unreachable
too, and a coverage gate of ninety per cent then fails for a reason that has nothing to do with the
quality of the tests. The obvious fix is to exclude those modules from the native gate and leave the
containerised gate alone. That fix, stated that way, makes the two command surfaces enforce two
different rules, which is precisely the drift the root `Makefile` already carries a comment warning
against — it keeps its pytest arguments deliberately in step with the backend's so that `make check`
does not mean two different things depending on where it was typed.

The exclusion was therefore conditioned on **database availability rather than on which Makefile was
invoked**. One rule holds everywhere: measure coverage over what was actually exercisable in this
environment. Natively, with no `DATABASE_URL`, the live-database modules are skipped and omitted
together; in the container, with the `postgis` service healthy, they are neither. The two surfaces
measure the same rule against different environments, and the containerised run is the authoritative
number because it is the only one where nothing is excluded. The risk this leaves is recorded as a
failure case in `db-001`: a module omitted in *both* environments is measured nowhere, and the
exclusion that keeps the native gate honest becomes the hole that hides an untested repository.

*(Record here, once `db-001` is applied, whether the first migration ran cleanly twice from empty
and what the missing-extension path actually reported — the failure case specifies a loud failure at
migration time rather than a `type "geography" does not exist` error at first query, and that is a
claim about an error message, which is only verifiable by causing it.)*

### Proving that tests fail: what a collection error hides

The workflow this project follows requires new tests to be run and seen to fail before any
implementation is written, on the principle that a test which passes against nothing is not testing
what its name claims. Implementing `db-005` showed that the check is weaker than it looks when the
tests are run against a module that does not yet exist.

The first run of the twenty new tests produced a single collection error: the module could not be
imported, so nothing ran. That satisfies the letter of the requirement — none of the tests passed —
while establishing almost nothing, because a collection error is produced by every test in the file
regardless of what it asserts. To get a per-test signal, a stub was written in which every function
raised `NotImplementedError`, the suite was run against it, and the stub was deleted before the tests
were committed. Eighteen tests failed. **Four passed**, and each of the three reasons was a real
defect in the test rather than an accident of the stub.

The first is a language detail with a general lesson. `NotImplementedError` is a subclass of
`RuntimeError`, so a test asserting `pytest.raises(RuntimeError)` around an unimplemented function
passes against the stub itself. Any "fails loudly" test written against the base class therefore
proves nothing about the implementation, and the fix was to introduce named exception types —
`MissingDatabaseUrlError`, `EngineNotInitialisedError` — which are still `RuntimeError` subclasses,
so the loudness guarantee is unchanged while the assertion becomes specific. The second was a test
that called `dispose_engine` twice and asserted no exception; a function whose body is `pass`
satisfies that, so it was rewritten to exercise a full construct-and-dispose cycle first.

The third and fourth are a category rather than a mistake, and the response to them is the part worth
carrying into other work. Both were structural guards asserting an *absence* — that no `Engine` is
constructed outside `app/db/`, and that no connection string is hardcoded anywhere under `app/`.
Neither can fail today, because the violation they exist to catch does not exist yet; they are
written for a future commit that introduces one. Deleting them because they pass would remove the
only mechanism that will catch that commit. They were instead **mutation-tested**: the violation was
introduced deliberately, the test was confirmed red, and the violation was reverted. A third mutation
ran the check in the opposite direction, placing a connection string inside a *docstring* and
confirming the test stayed green — because an earlier structural test in this project failed exactly
when an implementation docstring began explaining the rule the test enforced. The mutation results
are recorded in the tests' own docstrings with the date, so the evidence sits next to the assertion
rather than in a commit message.

The generalisable finding is that "the tests failed" is not one fact but three. A test can fail
because the implementation is absent, which is what the workflow intends; because the test is wrong,
which the workflow is meant to surface; or because the whole module could not load, which tells you
nothing at all. Only the second and third are distinguishable by running against a stub, and the
cost of building one is a few minutes.

### Building all seven tables in the first revision, four of them with no consumer

`db-001`'s first Alembic revision creates `observations`, `quarantined_records`, `anomalies`,
`evidence_bundles`, `hypotheses`, `analyst_feedback` and `scenario_runs`. At the time it was written
only the first two had any code that would ever write to them, and four will have no consumer for
several development phases. Building a schema ahead of the code that uses it is ordinarily a mistake,
so the reasoning for doing it deliberately is worth recording.

The argument is not symmetry or tidiness; it is that the cost of adding these objects late is not
uniform. A *table* added late is an ordinary migration, and the project has a migration mechanism
precisely so that this is cheap. A *column* added late is usually the same. But
`hypotheses.raw_response` is neither: it stores the hosted model's verbatim output before parsing,
and it is the entire mitigation for hosted-model retirement — the evaluation artefacts survive as
recorded evidence even after the model behind them no longer exists. Adding it after the campaign has
run does not recover the responses that were never stored. The campaign would have to be repeated, at
its full cost in money and wall time, to obtain data that a `TEXT` column would have captured for
nothing. The asymmetry between "cheap to add later" and "cannot be added later at all" is what
decides it, and the four tables come along because a foreign key needs its target to exist.

The same reasoning produced the two `CHECK` constraints on `hypotheses`. `confidence` is restricted
to `Low`, `Medium` and `High`, which is a project-wide rule about not presenting a percentage or a
decimal score to an analyst; putting it in the schema means the database cannot hold a value the
interface would then have to invent a rendering for. `generator` is restricted to `template`,
`local` and `hosted`, which keeps the RQ3 comparison a query — `generator IN ('hosted','template')` —
rather than a reconstruction, and makes any fallback to the local arm visible in the data rather than
inferred from a log.

### The ERD had no home for a quarantined record, and the fix was a table rather than a status flag

Specifying `db-001` surfaced an inconsistency that had been latent since `dal-002` was written. The
entity-relationship diagram in the technical specification lists six tables and none of them holds a
quarantine record, while `dal-002` requires that invalid records are persisted with the failing
field, the reason and the source attribution. The diagram predates the item; nothing had reconciled
them.

The available fix that adds no table is the wrong one, and it is worth stating why, because it is
superficially attractive. The canonical model's `ValidationStatus` enumeration already has a
`QUARANTINED` member, which reads as an invitation to store the record in `observations` with a
status flag. But the two shapes are not variants of one thing. A `CanonicalObservation` requires a
timestamp, a location and a payload; a `QuarantineRecord` has none of the three, and its
`source_id`, `source_type` and `observation_type` are optional where the observation's are required.
That is not an oversight in the design — those are precisely the fields whose absence or invalidity
caused the record to be quarantined. A record is rejected *because* its latitude will not parse, so
there is no location to store.

Storing it in `observations` therefore requires making `timestamp`, `location` and `payload`
nullable, which removes exactly the `NOT NULL` guarantee that `dal-003` defers to `db-001`. The item
would delete the assertion it exists to add, in order to avoid creating a table. A seventh table,
`quarantined_records`, was added instead, and the diagram amended to match.

Its nullability encodes the best-effort rule the DAL already states rather than restating it in
prose: `scenario_run_id` is `NOT NULL` because it comes from the ingest context rather than from the
record, so the run is known even when nothing else is, while `source_id`, `source_type` and
`observation_type` are nullable because a record can fail because it lacks the field that identifies
it. A `NOT NULL` on those would make the unattributable record unstorable and force the silent drop
that `dal-002` exists to prevent. The raw source row is deliberately not stored: a quarantined
OpenSky row still carries a real `icao24`, and keeping it would place in the database the identifier
`dal-004` exists to keep out.

### Testing a build file, and the limits of doing so structurally

`ops-003` specifies the root `Makefile` as the project's containerised command surface, and the
spec-driven workflow this project follows requires tests before implementation for every item without
exception. A build file is an awkward subject for that rule: its correctness is ultimately whether
the commands work against a real Docker daemon, which is an integration concern, and the obvious
reading is that the item is simply untestable in the unit tier.

That reading was rejected because the defect the item most needed to catch had already occurred and
was structural rather than behavioural. The `test-backend` target ran with `--no-deps` for several
weeks. That flag starts the backend container alone, so the database service never comes up, so every
test marked as needing a database would skip — and the target would report success over a suite that
had silently done less than its name claims. Nothing about that failure requires a daemon to detect:
it is a flag in a file. The tests therefore parse the `Makefile` and assert its structure — that each
enumerated target exists and is declared `.PHONY`, that no recipe swallows its own exit status with a
leading hyphen or a trailing `|| true`, that no target invokes a host toolchain outside a Compose
invocation, and that `test-backend` supplies a test database URL and depends on the target that
provisions the database.

The limitation is real and worth stating rather than hiding: a target can be structurally perfect and
still fail. These tests do not prove the commands work; they prove the commands cannot silently do
nothing. That is a narrower claim, and it happens to be the claim that matters, because a command
that fails is visible and a command that quietly succeeds having done less is not. The integration
half was covered once, by hand, by dropping the test database entirely and running the target from
nothing — 232 tests passed where the previous configuration would have run 205 and skipped 27 without
comment.

The three absence assertions among them were mutation-tested, as the project now does routinely for
any test that asserts something is *not* present: adding `|| true` to a recipe, adding a bare
`uv run pytest`, and restoring `--no-deps` each turned the corresponding test red. That practice
began when a structural test was found to pass vacuously and has since caught a test that reported
confidence without having mutated anything at all.

### Removing a specified mechanism rather than building it

`ops-003` and `db-001` both carried a requirement, written on 27 August, that the native coverage
gate omit modules requiring a live database exactly when those tests skip. The mechanism was designed
carefully — conditioned on database availability rather than on which command surface was invoked, so
that the two surfaces would enforce one rule rather than two — and recorded with its rationale before
either item was built.

When `db-001` was implemented the mechanism turned out to be unnecessary. The only module in question,
`app/db/migrations.py`, resolves filesystem paths and reads a committed ini file; none of that needs a
database, and four ordinary unit tests take it to full coverage with nothing omitted anywhere. The
requirement had been written from an assumption about what the module would look like, made before it
existed.

The clause was removed from both items rather than left standing, and the reasoning is worth
recording because the opposite choice is the tempting one. A specification that describes machinery
nobody built is worse than one that never mentioned it: it reads as a completed design, it survives
review because it is internally coherent, and the absence is discovered only when someone relies on
it. This project has now been bitten three times by spec text that was true when written and was
falsified by later work elsewhere, and the pattern in every case was text describing the state of
something outside the item's own scope. Deleting the clause and naming the item that will reintroduce
it — `db-003`, where the PostGIS repository genuinely cannot be exercised without a database — keeps
the specification a description of what exists rather than a description of what was once intended.

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

A second instance of the same failure mode appeared later, and the two together make the argument
better than either does alone. Compose bind-mounts the backend source over `/app`, but dependencies
are baked into the image at build time and are not mounted, so a container whose image predates a
dependency change runs today's code against yesterday's libraries. The visible symptom was a library
that had been a declared dependency for a week failing to import, which is loud and therefore
harmless. The direction that matters is the opposite one: a dependency *removed* from
`pyproject.toml` stays installed in a stale image, so the suite passes in the container and would
fail on a fresh clone or in CI. The environment being reported on is then one that exists nowhere
else, and the report is confident. The remedy was to make every quality target depend on its image
being rebuilt, but the observation worth carrying into the write-up is more general: a bind mount is
a *partial* override of an environment, and a partially overridden environment is a third environment
rather than either of the two it was assembled from.

The same episode exposed a divergence that care alone would not have prevented. The repository offers
two command surfaces for one test suite — `backend/Makefile` against the host virtual environment and
the root `Makefile` against containers — and they had drifted in three independent ways: the
dependencies they ran against, the pytest arguments they passed, and a comment asserting that the
OpenSky extract was committed, which the licence reversal had made false a week earlier. Each drift
was individually invisible, and all three surfaced because a person typed a command, not because
anything checked. This is the argument for continuous integration stated as evidence rather than as
principle: not that CI catches defects in code, but that a repository offering two ways to do one
thing will silently offer two different things unless something exercises both.

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
