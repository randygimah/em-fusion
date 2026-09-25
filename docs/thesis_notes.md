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
rather than avoided.

**Two corrections to this paragraph, both found by `adp-008` when the analysis was made
reproducible.** The first is arithmetic: the ten gaps are *not* ten tracks. Three aircraft carry two
gaps each, so the confound touches **7 of 948 tracks, or 0.74%**, not the 1.05% recorded here
originally. The error was an inference — ten gaps read as ten aircraft — and it survived because the
hand analysis reported durations and nothing else. The comparison with the rejected widest candidate
is left unrecomputed and should be treated as indicative only, since that figure was derived the same
way. The second correction is to the claim that "the coverage report identifies exactly which tracks
carry a natural dropout". It does not, and never did: `coverage.json` records a cadence, an aircraft
count, a gap count, a maximum, three percentiles and a clean-cadence fraction, with no identity in it
anywhere and neither the interior nor the airborne filter applied. The mitigation had no input, and
would have been discovered to have none at the point someone tried to use it.

`adp-008` supplies that input, and the ten durations it reports against the real extract are
identical to the ten recorded above — which is the evidence that it reproduces the hand analysis
rather than merely resembling it. *(Record here the measured false-positive rate on scenario type 4
with and without the exclusion, once `scn-002` can run one.)*

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

### Reversal: the evaluation is human-participant research after all, and a change of rater is what made it so

The proposal states, in TOR 9, that "the project collects no data from human participants." That
sentence was accurate to the design as it stood when it was written, and it is no longer accurate. The
reversal is worth recording precisely because nothing about the *data* changed — the study collects
exactly what it always intended to collect, roughly 280 ordinal values and no demographic field
whatsoever — and the ethical classification flipped anyway.

What changed was the identity of the second rater. The proposal expected the university supervisor,
and a supervisor scoring a student's output sits plausibly within the supervisory relationship rather
than within a research procedure. Securing the second scorer during Track 0 resolved instead to a
professional colleague. That single substitution introduces recruitment, an approach made
specifically for the study, a person with no prior stake in it, and a power dimension arising from
shared employment. TOR 9 had in fact anticipated the possibility — its closing sentence commits to
voluntariness and to avoiding line-management relationships should the rater be a colleague — but it
did not follow the consequence through to the classification itself, and so the two halves of that
paragraph now contradict each other.

The decisive feature, and the one that resisted the intuition longest, is the inter-rater agreement
statistic. Quadratic-weighted Cohen's κ is a measurement of how closely two people agreed with one
another. It feels like a property of the instrument, and is reported as evidence about the rubric's
reliability, but it is computed from human judgements and its subject is a pair of humans. A study
cannot report a statistic about people and simultaneously claim to have studied none. The conflation
being corrected is between *personal data processing*, which this study almost entirely avoids, and
*human-participant research*, which it plainly is; the ethics form asks the second question and the
project's own framing had been answering the first.

The decision was made on asymmetry rather than on a fine judgement about where the boundary sits.
Declaring participants where none were required costs an information sheet, a consent form and a
supervisor signature. Declaring none where they were required is, in the form's own words, a notable
grade deduction and possible academic misconduct. Where the two errors are that unequal, the
borderline case is not worth adjudicating; the expensive-to-be-wrong answer is simply taken. The
declaration remains within module-level approval — competent adults, no vulnerable groups, no
special-category data, no deception, no physical intervention — so the four-to-eight-week committee
gate that drove the withdrawal of the task-based user study is not reopened by it.

Two consequences are carried forward rather than resolved. Recruiting from one's own workplace
introduces perceived obligation, mitigated by excluding anyone in a line-management relationship in
either direction and by approaching once without follow-up, but not eliminated. And with two raters,
one of whom is the author, the second is identifiable by elimination to anyone who knows they were
asked; pseudonymising the score sheet does not touch this and at N=2 no design can. The handling is
disclosure before consent rather than a claim of anonymity the study cannot deliver, with reporting
constrained to "an independent second rater," unnamed, with no comment on how they scored. Both are
stated as limitations in the Evaluation chapter rather than argued away.

The form answers, participant information sheet, consent form and recruitment text are drafted in
`docs/ethics_form_answers.md`; the conceptual correction is `docs/qa.md` §46. *(Record here the date
the form was signed off by the supervisor, and whether one colleague or two were ultimately recruited
— the latter would move the agreement statistic from Cohen's κ to a pairwise or Fleiss form and
requires a change-log entry against the pre-registered rubric.)*

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

The figure that bounds a scenario run is therefore about **14 seconds**, not the earlier one.
Conditions: twelve batches of 300 simulated seconds each, so twelve transactions; both processes in
containers; the backend container native `aarch64` and only `postgis` under `amd64` emulation, which
the container note elsewhere in this chapter measures at about 2.5x native, so the persistence half
is pessimistic rather than optimistic.

**The comparison is not controlled, and an earlier draft of this section overclaimed from it.** It
is tempting to read the two columns as "persistence costs 5.8 times what reading and normalising
cost", and that was written down before it was examined. The baseline was taken natively on the host
against an in-memory repository; the new figure is a container against an emulated database. The
gap is mostly persistence — the emulated component is the database — but the two measurements differ
in more than one variable and only a same-container run against the in-memory repository would
isolate it. The CLI cannot currently do that, and the honest position is that the total is measured
and the attribution is not.

**Run-to-run variance is about 5 per cent**, measured as 13.60 s and 14.25 s for identical
invocations, so the figure should be quoted as "about 14 s" rather than to two decimal places. This
matters for the write-up: two decimal places on a figure with that spread implies a precision the
method does not have.

#### Batch size barely matters until it suddenly does

The window length decides the unit of work, and `read_window` cannot push its time predicate into
the Parquet reader — `iter_batches` takes no `filters` and the artefact is a single row group — so
every window walks the whole 133,634-row file and keeps what falls in range. Twelve windows means
twelve full scans. That is obviously wasteful and was expected to show:

| Window length | Batches | Wall time |
|---|---|---|
| 3600 s | 1 | 13.99 s |
| 900 s | 4 | 12.69 s |
| 300 s | 12 | 13.60 s |
| 60 s | 60 | 23.17 s |

It does not show, until sixty batches. Eleven redundant scans are indistinguishable from noise,
because a full scan costs roughly 0.16 s and per-row DAL work dominates by two orders of magnitude.
At sixty batches about nine of the twenty-three seconds are re-reading, and the design starts to
matter.

Recorded because the inference runs the wrong way round from intuition. The redundant scan is a real
inefficiency, visible in the source, and the obvious optimisation — read once, dispatch to windows —
would have bought nothing at the batch sizes actually in use while adding a buffering concern. *(If
scenario runs later drive much shorter windows, this is the first place to look, and the constant is
now on record.)*

Four independent cross-checks reproduced in the database what was derived from the raw Parquet
months earlier: 30,276 observations carrying no altitude, 948 distinct aircraft, every geometry at
SRID 4326, and zero rows mentioning `icao24` or `callsign` anywhere in a stored payload. The last is
`dal-004` holding over the full corpus rather than over a fixture.

**The earlier figure was also recorded inconsistently** — 2.44 s in this document against 2.46 s in
`qa.md` and the handoff — which nobody could adjudicate, because the script that produced it was
gone. That is the argument for `adp-007` in one sentence: a measurement whose method is not
committed is not a measurement, it is a memory. Both values are now superseded rather than
reconciled.

#### The atomicity boundary, and the gap it leaves

`adp-007` chose one window as the unit of work rather than one run, so `dal-002`'s all-or-nothing
guarantee holds per batch: the accepted observations and the quarantine records for a five-minute
slice commit together or neither. Across the run there is no enclosing transaction, and a failure at
batch seven leaves batches one to six committed.

The point worth carrying into the write-up is that **atomicity is always relative to a boundary
somebody chose**, and the choice is an engineering trade rather than a property of the database. The
whole-run alternative was declined because it holds a 133,634-row write open for the length of the
replay and discards everything on a failure at 99 per cent.

**The consequence was under-thought when the item was specified, and is recorded here rather than
left to be discovered.** Nothing marks a run complete and nothing cleans up a partial one. A failed
replay leaves its rows under a `scenario_runs` row; re-running creates a *new* run rather than
resuming; and the two are indistinguishable by inspection. This is harmless while nothing reads
runs, and actively misleading once the detection layer does — any count over `scenario_runs` taken
before it is fixed may include partial runs. The fix is small in either direction, a completion flag
set on success or a run deleted on failure, and neither exists yet.

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

### A run's completion is one nullable column, not a status with three values

The replay entrypoint chose one window as its unit of work rather than one run, which means a replay
interrupted half-way leaves its committed batches in the database and its run row looking exactly
like a run that finished. Nothing read runs at the time, so the ambiguity cost nothing; it becomes
wrong the moment the evaluation campaign counts runs or a detector reads a window out of one. The
fix is a single nullable `completed_at` on `scenario_runs`, set after the final batch commits.

The alternative considered was the one that reads better: a `status` column holding `running`,
`failed` or `complete`. It was rejected because it cannot be honest. A process killed outright — the
container stopped, the machine sleeping, the operator's interrupt — cannot record its own failure, so
`failed` would be correct for exceptions the program caught and silently wrong for every other way a
run ends. That produces the worst kind of column: one that looks authoritative and is not. A single
null collapses running, failed and crashed into the one proposition a later reader can actually
assert, which is that the run is *not known to have finished*. The information given up is real —
the database cannot distinguish a crash from a replay still in progress — and it is given up
deliberately, because a distinction that is right most of the time is worse than an absence that is
right always.

Three smaller decisions follow from the same reasoning. The column is nullable with **no server
default**, because a default stamps completion at the moment the row is created and so records an
intention rather than an outcome. The revision performs **no backfill**, because the rows already in
the database are precisely the runs whose completion nobody recorded, and stamping them complete
would erase the only evidence that the question is open — the migration was applied to a development
database holding one such run, and it stayed null, which is the behaviour asserted rather than the
one hoped for. And **nothing is deleted on failure**: the rows a partial run wrote are evidence
about what went wrong, and a cascading delete over 133,634 observations is a surprising thing for a
failure path to do to a database.

The function that sets the flag lives in the storage layer as a free function rather than as a
method on the observation repository, because every producer of a run has to set it and not every
producer writes observations — the scenario generator will create runs — and a rule enforced only by
whoever happens to be holding an observation repository is a rule enforced by coincidence. It raises
rather than returning quietly when the run id does not exist, because PostgreSQL reports no error
for an `UPDATE` that matches nothing: it reports zero rows affected, and a caller holding a wrong id
would otherwise be told that a run it never marked had been marked.

### The contract violated the project's own no-fake-precision rule, and the endpoint was the last cheap moment to find out

`FR-715` and `AC-11` state that no confidence, severity or score is rendered as a percentage or a
decimal anywhere in the interface. The rule exists because a hypothesis presented as "87% confident"
invites an analyst to treat a generated number as a measurement, and the system's entire claim is
that it supports a human judgement rather than substituting for one. The committed frontend contract
declared `anomalyScore: number` and `signalIntegrity: number`, and the screen rendered them as
`74.2%` and `0.92`. The violation had been in the repository since the screen was first built and no
test had ever looked for it.

It surfaced while specifying the endpoint, because that item's deliverable is a parity test between
the TypeScript contract and the response models. A test whose purpose is to make a shape hard to
change is also, unavoidably, a test that defends whatever shape it is pointed at, so the moment
before writing it is the cheapest moment the contract will ever be changeable. The fields became
`Low | Medium | High`, and `anomalyScore` was renamed `anomalyLevel` because it is no longer a score.

Two details are worth keeping. First, the type system located the violation rather than a reviewer:
changing the declaration produced a compile error reading `Property 'toFixed' does not exist on type
'Level'`, which is the decimal formatting the requirement forbids, named by the compiler at the exact
line. Second, the rendering half of this problem already had a home — `ui-001` specifies a shared
primitive that accepts only the three levels — so the endpoint item removed the violation and left
the primitive to the item that owns it, rather than absorbing work because it happened to be nearby.

### Absence is served as absence: null rather than a neutral reading

Four of the six sections in the operational picture have no producer: there is no detector, no radio
source and no hypothesis generator. The question is what an endpoint should return for a section
whose machinery does not exist, and the tempting answer — a neutral value, `Low`, a zero — is wrong
for a specific reason. `Low` is a claim about the data. It says the anomaly level was assessed and
found low, which is false, and an analyst has no way to distinguish that from a system that has
genuinely assessed it. Null is a claim about the system: nothing has assessed this. Only the second
statement is true, so only the second is served, and the screen renders a dash.

This is the same reasoning that made `db-007`'s completion flag nullable a day earlier, and the
repetition is the useful part: in both cases a value that is right most of the time was rejected in
favour of an absence that is right always. It also made `scenario` itself nullable, which is what
lets an empty database return a valid empty picture rather than a 500 — a property `op-001` had
already anticipated by requiring the data-mode badge to render when scenario data is absent.

The alternative that was actually available — serving the frontend mock from the backend, so the
screen stayed populated — was rejected without much difficulty. Invented data flowing through a real
endpoint into a real screen is indistinguishable from the genuine article at the point where it
matters, and a system whose thesis is that AI output must be grounded and checked before an analyst
sees it cannot make an exception for its own placeholder content.

### A failed poll keeps the last real data rather than reverting to the mock

The specification for frontend data access said the application should fall back to the mock on a
fetch failure and show a degraded indicator rather than blanking. Implemented literally, that means a
single failed request replaces real telemetry with invented example data. The intent behind the
sentence is "do not blank", and blanking is not the only way to mislead: silently swapping measured
data for fabricated data is worse, because a blank screen at least announces itself.

The implemented behaviour keeps whatever is already displayed and changes only the indicator. The
mock remains the fallback while nothing real has ever arrived, which is the case the sentence was
written for. Stale real data behind a "not live" badge is both more useful and more honest than fresh
invented data behind no badge at all.

A second decision follows from the same argument and is less obvious: **the application reports
itself degraded from the first paint**, before any request has resolved. At that moment the screen is
showing the example payload, and example data presented as though it were the system's own output is
precisely the failure this project exists to argue against. The indicator clears on the first
successful response. The mutation that proves this matters is the "fall back silently" reading — make
a failed poll restore the mock and clear the flag, and three tests fail; without them, the interface
would look healthy while displaying fiction.

### Data fetching written by hand, with the adoption point for a library fixed in advance

The frontend polls through a forty-line hook rather than a data-fetching library such as TanStack
Query. The choice is not a judgement that the library is unsuitable — polling on an interval is
precisely what it is best at, and its keep-previous-data behaviour is the retain-the-last-good rule
expressed as configuration. The judgement is about proportion: with one screen consuming one
endpoint, the library's real advantages — request deduplication across components, a shared cache,
retry with backoff, suspending polls for a hidden tab — have nothing to act on.

What makes this a decision rather than an omission is that the adoption point was fixed at the same
time and written into the build checklist, in the Phase 3 view-filter subsection. That is where a
second polled endpoint appears, joined by the playback window in Phase 4: two consumers issuing
overlapping requests, with a filter selection that must survive poll ticks. Those are the problems
the library exists to solve, and continuing to hand-write at that point would be the mistake this
note is trying to avoid in the other direction.

The cost of deferring is deliberately kept low by the structure already in place. One module performs
the fetch and a test asserts that no other module does, so the library would slot in behind that
boundary and the swap would touch the hook alone. The tests assert behaviour through the rendered
screen rather than through the hook's internals, so they would survive the substitution — which is
also the strongest evidence that they were testing the right things.

The write-up angle is worth stating plainly, because it applies to several decisions in this project:
the dependency list is short, and each entry can be defended in a sentence naming what it does that
hand-written code could not. "A data-fetching library, for a single endpoint" is a weaker sentence
than the hook is, and a dependency that cannot be defended in a sentence is one that will have to be
defended at length in a viva.

### Turning "positioned so a zone contains some and excludes others" into a check

`FR-109` asks that RF sensor positions be chosen "so that a candidate interference zone contains some
sensors and excludes others". As written this is a design intention rather than a property: it names
no radius, no threshold, and nothing a program could evaluate. A requirement in that form is
satisfied by whatever layout the author happens to write down, which is the same as not constraining
the layout at all — and the cost of getting it wrong would not appear until Phase 6, where the
symptom would be a detection rate nobody could explain rather than an error anybody could locate.

The requirement was therefore restated as two invariants at a recorded radius, both checked when the
layout is loaded and before any observation exists. **Every sensor must have at least one other
sensor within the radius**, or the neighbour comparison `anom-007` depends on has nothing to compare
that sensor against, and the sensor-fault rule silently degenerates into "this sensor is abnormal".
**Every sensor must have at least one other beyond it**, or a zone centred anywhere contains the
entire layout and `anom-005`'s spatial-coherence test is satisfied by every event, discriminating
nothing. The two run in opposite directions, which is what makes them a pair rather than a single
density heuristic: the first forbids a layout that is too sparse, the second one that is too dense,
and a layout satisfying both necessarily contains the internal structure the fusion rules read.

The shipped layout is seven sensors at real airfield positions inside the corpus bounding box
(49–54°N, 3–11°E) — Schiphol, Rotterdam, Lelystad, Eindhoven, Weeze, Düsseldorf and Köln/Bonn. Seven
rather than six or eight for two reasons: an odd count leaves no tie in any future "most neighbours
stayed nominal" reasoning, and seven was the smallest count that produced two separated groups joined
by a bridge sensor rather than one undifferentiated cluster. Every sensor stands inside the bounding
box because a sensor outside it would watch airspace the replayed telemetry never covers, so
`anom-005` could never fuse its readings with a track cluster — a constraint that is obvious once
stated and invisible until it is.

The radius is the interesting number, because the invariants do not hold at every value and the
range over which they do is a property of the layout rather than of the configuration. Measured
against the shipped positions, **both invariants hold for any radius in [55.7, 85.7) km** and fail
outside it: below 55.7 km Eindhoven loses its only neighbour, and at 85.7 km Rotterdam and Eindhoven
become neighbours and the chain begins to collapse toward the fully connected case. The configured
value is **70 km**, chosen near the middle of that band rather than at either end, so that a later
adjustment to a sensor position or to `anom-005`'s configured distance does not silently destroy the
property it depends on. That the valid band was measured at all is the substantive point: the
alternative is a radius chosen because it sounded plausible, with no knowledge of how close it sits
to the edge of working.

One thing this deliberately does not do is fix the detectors' radii. `anom-005`'s fusion distance and
`anom-007`'s neighbour radius are separate configuration in their own items and may legitimately
differ from each other and from this one; what the layout records is the radius at which it is
*asserted* discriminating, and the measured band is the range those detector radii should be chosen
from. *(Record here whether either detector was in fact configured outside [55.7, 85.7) km, and what
the layout validation had to become if so.)*

An arithmetic error in the specification surfaced while writing this. Both `scn-005` and
`docs/em_fusion_v2.md` §5 described the channel plan as "one channel on L1 with four either side",
which requires nine channels; the plan has eight, and the frequency list places L1 at index 4 with
four channels below and three above. The list was right and the sentence was wrong, and both
documents were corrected. The substantive requirement the sentence was reaching for — that frequency
adjacency runs in *both* directions from L1, so `anom-007`'s frequency-neighbour test is not
one-sided — is preserved and is now enforced directly, by rejecting any plan whose L1 channel sits at
either end. The lesson is narrow but worth stating: a prose restatement of a table is a second source
of truth, and it drifted from the table it restated before anything was built from either.

### Determinism by keyed derivation rather than by a seeded sequence

`scn-001` requires that a scenario run be fully determined by its type, its parameters and an integer
seed, and names three ways that guarantee leaks: wall-clock time, unseeded randomness, and
process-dependent ordering. The obvious implementation defends against the first two and *is* the
third. Constructing one `random.Random(seed)` and drawing from it as the sensor–channel–time grid is
walked makes the output a function of the traversal order, which is a property of the loop rather
than of the run. Reordering the layout file would then change every reading; generating two sensors
concurrently would change every reading; and inserting one additional draw per cell during
development — which `scn-002` will do the moment it adds an injected component — would shift the
whole stream after the point of insertion. None of these announce themselves, because each produces
a stream that is still perfectly reproducible within the process that produced it.

The design adopted instead derives each value from the seed and the coordinates of the thing being
valued: a BLAKE2b digest over the seed, the sensor identifier, the channel index, the tick index and
a short tag naming the quantity, reduced to a float in `[0, 1)`. No cell can observe any other, so
traversal order is not an input at all and the third leak is closed by construction rather than by
discipline. Three consequences follow that were not the reason for the choice but justify it more
strongly than the original argument did. A single cell can be recomputed years later without
replaying the run that produced it, which is what a spot check of a recorded ground truth actually
needs. Generation may be parallelised or reordered at any point without invalidating a stored result.
And — the one that matters most for the phases still to come — **adding a new derived quantity to a
cell does not disturb the quantities already there**, because each is namespaced by its own tag,
whereas under a sequential design every value drawn after the new one would change and every ground
truth recorded before it would cease to describe the stream it was recorded against.

Two details in that scheme are load-bearing and neither is obvious. The keys are joined with the
ASCII unit separator rather than concatenated, because `("RF-1", 12)` and `("RF-11", 2)` are the same
string under concatenation, and a collision does not produce an error: it produces two cells with
identical readings, which is precisely the correlated-neighbour structure `anom-005` exists to find.
And the digest comes from `hashlib` rather than the built-in `hash`, which Python salts per process —
a stream derived through it is identical across every test in one run of the suite and different the
next morning, which is to say reproducible for exactly as long as it takes to be trusted.

Normally distributed noise is produced by Box–Muller over two derived uniforms rather than by
`random.gauss`. The transform is then owned by this project and visible in it, instead of being
whichever algorithm the standard library implements in a given version; a campaign that must
regenerate identically across the life of the project cannot afford to depend on that. The
guard against `log(0)` — mapping the first uniform from `[0, 1)` to `(0, 1]` — matters for the same
reason the separator does: the failure is reachable with probability 2⁻⁵³, which is rare enough to
survive every test ever run against it and to appear once inside a campaign.

Readings are rounded to a hundredth of a decibel before they are emitted, and the honest reason is
not presentation. Floating-point arithmetic is deterministic, but `log` and `cos` are provided by the
platform's maths library and their final unit in the last place is a property of that library rather
than of the arithmetic. Rounding places that difference below the value that gets serialised, which
converts "identical on identical builds" into a reproducibility claim that needs no footnote about
the C library. A hundredth of a decibel is orders of magnitude below any threshold a Phase 8 detector
will use, so nothing is lost that the system can see. The alternative — emit full precision and
qualify the claim — was rejected because the qualification would have to appear in the write-up
beside every number derived from a regenerated run.

The cost of the scheme is a hash computation per derived value rather than a state advance in a
pseudo-random generator, and it is small enough not to matter: a full hour of the shipped layout is
20,160 records, emitted in **0.11 s** and digested in **0.10 s** on the development machine, measured
over three consecutive runs that varied by 5 ms. At `scn-003`'s batch of thirty runs that is under
seven seconds of generation, against a replay of the same hour that takes about ten.

### The run record moves to the storage layer, and the seed is written before anything is emitted

`adp-007` needed a `scenario_runs` row before it could write an observation, and no generator existed
to create one, so the replay command inserted the row itself with the SQL written inline — recorded
at the time as a borrowing, with a comment naming `scn-001` as the item that would reclaim it. It has
now been reclaimed: `create_scenario_run` sits beside `complete_scenario_run` in the storage layer, a
free function rather than a repository method for the same reason `db-007` gave, namely that every
producer of a run creates one while only some producers write observations.

The seed is a required argument rather than a defaulted one, so no caller can open a run without
having decided a seed, and `RunSpec.create` draws one before the row is written when none was
supplied. This is what makes `scn-001`'s third failure case unreachable rather than merely
discouraged: a generated seed cannot fail to be recorded, because the value is generated *into* the
object the row is written from. Writing the test for it surfaced a constraint that would otherwise
have been found much later and much more expensively — `scenario_runs.seed` is a 32-bit signed
integer column, so a seed drawn from a wider range inserts successfully until it does not, at some
unpredictable run inside a batch. The draw is bounded to the column's width, and a test asserts it.

The replay's own run row now records a seed of zero, and the value is a claim worth stating
precisely: a replay invents no numbers, so it has no randomness for a seed to control, and its
reproducibility comes from the corpus and the requested span rather than from a seed. Zero is
recorded rather than null only because the column is `NOT NULL`. *(This is a small ambiguity to note
as a limitation: a reader cannot distinguish "seed zero was chosen" from "no seed applies" by looking
at the column alone. The `replay-only` scenario type is what disambiguates it, and any later query
over seeds should filter on the type rather than trust the value.)*

The structural consequence is the third instance of a pattern this project keeps rediscovering.
Because the run row's SQL has left the command module, `app/replay.py` no longer imports SQLAlchemy
at all, so "no SQL outside the repository" is a fact about the import graph rather than an argument
about the contents of strings — the same move `db-006` made when it named `SessionFactory` in
`app/db/session.py` so the API layer could not say `sqlalchemy`. A rule that can be checked by
looking at what a module imports is enforceable; a rule that requires reading what a module *says*
is not.

### The five scenario types span a confusion space rather than enumerate faults

The obvious reading of "five scenario types" is a list of things that can go wrong, and under that
reading the set looks arbitrary — why not six, why not congestion, why not a spoofed identity. The
set is better understood as the smallest one that forces the system to *discriminate*, and the
discriminations it must make are fixed by the three deterministic rules Phase 8 will carry: noise
co-located with track trouble means interference; track trouble with a clean spectrum means a
data-source problem; a single receiver deviating while its neighbours stay nominal means the
receiver. Four of the five types land squarely on one of those, and the fifth is built to land
between two.

`normal-baseline` earns its place by staging nothing, which makes it the only run on which any
finding at all is definitionally wrong, and therefore the only run from which a false-positive rate
can be computed. `gnss-degradation` and `aircraft-coverage-gap` are a matched pair distinguished
only by the spectrum: both produce aircraft trouble, and the presence or absence of a co-located
raised floor is what separates interference from a receiving problem. `rf-sensor-fault` is the case
where the environment is innocent.

`ambiguous-mixed-evidence` is the one that required a decision, because the item named it without
defining it. Three readings were considered. A track gap and an RF anomaly *separated in space*
beyond the fusion distance was rejected: it is a negative test for the fusion rule, which that rule's
own failure case already covers, and the evidence it produces reads as unrelated rather than
ambiguous. Two overlapping unrelated injections was rejected because the ground truth would then
describe two events, which complicates every per-scenario metric in the harness for no gain in what
is being studied. The chosen reading is a **single deviating receiver with a co-located
contemporaneous coverage gap** — which is `rf-sensor-fault` plus one addition, and that is the
point. The sensor-fault rule reads the clean neighbours as evidence of a faulty receiver; the fusion
rule reads the co-located gap as evidence of real interference. Both readings are available, neither
is safe, and the correct output is that the two cannot be distinguished. It is the only run in the
set where *confidence itself is the error*, which is what makes it the sharpest instrument in the
generator comparison: a fluent arm that produces a crisp, well-written, confident answer is worse
than one that declines, and two of the rubric's five dimensions — uncertainty, and alternative
explanations — exist to catch exactly that.

A related decision is recorded here rather than rediscovered later: **spectral extent is a parameter
of two types, not a sixth type.** Narrowband and broadband interference differ in what the
frequency-adjacency evidence says, not in what caused them, and modelling them as separate types
would make a comparison between narrow and wide a comparison *between scenarios* — confounded with
everything else that differs between two types — rather than a comparison within one.

### One centre per run, and a defect that shipped because the spec was read too narrowly

`scn-002` was built in passes: the RF grid first, the replayed tracks second. Each pass was green,
mutation-tested and committed, and the second pass shipped a real defect anyway. Track targeting was
keyed to the seed and the aircraft's own identity — order-independent, reproducible, everything the
determinism work required — and applied to the **whole fleet**, with no reference to where the
incident was. A navigation incident centred on Rotterdam would therefore have frozen the reported
positions of aircraft over Cologne, 200 km away, while the answer key recorded the two as one event.

The spec said "aircraft inside the affected area" from the moment it was amended. The defect was not
a missing requirement but a partial reading of one, and the tests written for that pass encoded the
same partial reading, so nothing failed. What surfaced it was writing the *next* pass, where
co-location is the whole substance of the scenario and its absence became impossible to miss.

The fix is structural rather than a check bolted on. There is now **one centre per run**, derived
from the seed by the same function both halves call, so the radio anomaly and the track effect are
co-located by construction rather than by a caller remembering to line them up. `anom-005` fuses on
co-location in space as well as in time, so two independently placed halves would have made a
scenario's own detectability a function of how far apart they happened to land — a confound that
would have appeared in the results as detector behaviour. `aircraft-coverage-gap` is given a zone of
its own despite having no radio incident, because its dropouts have to cluster somewhere or
`anom-004` has nothing to group.

The generalisable finding is about test authorship rather than about zones: **tests written from the
same reading of the spec as the implementation cannot catch a misreading of the spec.** Both were
mine, written in the same hour, and they agreed with each other perfectly. What caught it was a later
piece of work whose correctness depended on the same property from a different direction.

### Freezing a position without holding state, and what the shortcut costs

The `gnss-degradation` signature is an aircraft that keeps transmitting while the position it reports
stops advancing — fresh contact, stale position, the shape 4,553 rows of the real corpus already
carry. The obvious implementation holds each aircraft's last position and re-emits it for the
duration of the window.

That was rejected, and the reason is `scn-001` rather than anything about aviation. Holding a last
position is per-aircraft state, and the replay processes the corpus one window at a time; state
would have to persist across those batches, which makes the output a function of how the replay was
batched and in what order the batches ran. That is precisely the process-dependent-ordering leak the
determinism work closed, reintroduced at a different layer.

The implementation instead rewrites the *reported position staleness* to grow with elapsed time
inside the window and leaves contact staleness untouched. It is stateless, order-independent, and it
moves the field the canonical model documents as the discriminator and the field the Phase 8 rules
will read.

**The cost is real and is recorded as a limitation.** The coordinate itself continues to advance, so
an aircraft under a staged navigation incident reports a position that is moving while claiming to be
three hundred seconds old. A detector that recomputed staleness from successive coordinates, rather
than reading the reported value, would not see the signature at all — and would be right to be
suspicious. No rule in Phase 8 does this, so nothing in the planned system is affected; a rule added
later that did so would silently fail on this scenario type. *(If such a rule is ever written, this
trade has to be revisited rather than worked around.)*

### Every run carries both halves, including the two that stage nothing on the tracks

A run could reasonably have been defined as whichever streams its scenario type needs. Three of the
five types edit replayed aircraft reports — suppressing them for a coverage gap, freezing the
reported position for navigation degradation, suppressing them again for the ambiguous case — and the
other two touch the track side not at all. Generating only what a type stages would halve the work
for those two and remove a dependency on the archived corpus being present when a batch runs.

That definition was rejected, and the reason is about non-detection rather than about detection. Two
of the deterministic rules are defined across both sources: one fires on a raised noise floor
co-located with track trouble and calls it possible interference, the other on track trouble with a
clean spectrum and calls it a data-source problem. In a run containing no track observations at all,
"no track trouble" is true by construction. Both rules stay silent, both look correct, and neither
has been tested — the silence is a property of what the run omitted rather than of what the rules
concluded. The quiet control is the sharper case of the same thing: it exists to measure how often
the system reports something when nothing was staged, and a control carrying only the synthetic radio
grid measures that for one source while the write-up would quote it for the system.

So a run is two streams always, and the type decides only what is staged on them. The cost is modest:
the radio grid was measured at 0.45 seconds per fifteen-minute run into PostGIS, and a fifteen-minute
window of the corpus is roughly a quarter of an hour that the replay stores at about ten seconds, so
near three seconds per run and around a minute and a half for a batch of thirty, leaving in the
region of 1.1 million rows behind. The real cost is a dependency: a batch cannot run without the
OpenSky extract on disk, and the extract is not in the repository because the licence forbids
redistributing it. The batch therefore has to fail before it writes anything when the corpus is
absent, in the way the replay entrypoint already does, rather than quietly producing runs with no
traffic in them — which would be indistinguishable, after the fact, from runs whose traffic was
suppressed.

A second decision follows from the first and would not have arisen without it. The incident's zone
centre is derived from the run's seed and there are seven receivers, so a batch of twenty to thirty
runs stages at the same place several times over — measured across thirty derived seeds, every
receiver is used, between two and six times each. If those runs also replayed the same stretch of the
recorded hour, runs sharing a centre would be near-duplicates: the same aircraft, in the same place,
differing only in the invented noise. Each run's window is therefore derived from its own seed as
well. The limitation that remains belongs to the data rather than the design, and is recorded under
Evaluation: thirty fifteen-minute windows inside one recorded hour overlap heavily, so track-side
independence across a batch is bounded by the corpus.


### Routing: the URL hash rather than a router library or component state

Three screens had to become reachable, and the second of them had been built, tested and merged with
no way to open it in a browser. The choice was between a routing library, component state in the
application shell, and the URL fragment.

A library was rejected on proportion. React Router and its peers exist for nested routes, route
parameters, loaders and navigation guards, and this interface has three destinations, no nesting and
no parameters; the dependency would have been taken on for a switch statement. Component state was
rejected for a stronger reason than proportion: it makes the address bar lie. A reload returns the
analyst to whichever screen the shell initialises to rather than the one they were on, no screen can
be linked to, and no screen can be named in a bug report — which matters more here than in an
ordinary application, because the evaluation campaign depends on a second scorer being able to reach
a specific view and on defects being reported precisely enough to reproduce.

The fragment was chosen, and one consequence of it is an accessibility property rather than a
convenience. A destination with an address is a link, so the rail is built from anchors and
`aria-current="page"` sits on an anchor, which is where assistive technology expects to find the
current page. Component state would have produced buttons styled as links, and `aria-current` on a
button is a weaker claim about a thing that is not navigation. The fragment rather than the path also
avoids a deployment concern: the frontend is served as a static bundle behind nginx, and a path-based
route needs the server to rewrite unknown paths onto `index.html` — configuration taken on, again,
for three destinations.

An unrecognised fragment resolves to the Operational Picture rather than rendering nothing. The
alternative, an empty workspace beneath a working navigation rail, reads to a user as a broken
application rather than as a bad link, and the distinction matters for a prototype that will be put
in front of people who did not build it.

### An entry that leads nowhere, and a table that says it is a fixture

Two presentation decisions in the navigation item follow the same rule, and the rule is the one the
project exists to argue for rather than a matter of taste.

The first: the specification fixes the rail at three entries, and the third screen has no
implementation. The entry could have been hidden until it was built, or left to render a blank
workspace. It instead states that the screen is not built and names what it will hold. Hiding it
would have made the interface disagree with its own specification; a blank page would have said
nothing at all, and a user cannot distinguish a blank page from a failure.

The second is the load-bearing one. The Scenario Control screen lists recent runs, and with no
scenario endpoint that table is reading a fixture — real seeds, real windows and real parameters
lifted from a batch that genuinely ran, which is precisely what makes it dangerous. Rows that came
from nowhere would announce themselves; rows that came from a real batch look exactly like rows from
the database. This is the same failure the picture feed already guards against by reporting itself
degraded from the first paint, before any response has arrived, and the two are now one rule applied
twice: **example data is never presented as though it were the system's own**. The screen already
carried a note explaining that its controls were inert, so the statement went there rather than
becoming a second banner.

Recording this as a design position rather than a detail is deliberate. A prototype for explainable
situational awareness that quietly showed invented rows as observations would undermine its own
argument more thoroughly than any weakness in its detectors, and the discipline is easier to defend
in a write-up if the places it was applied are enumerated rather than asserted.

### Two kinds of state that both survive a reload, and only one belongs in the address

The collapsible rail forced a distinction that the routing decision had left implicit. Both the
current route and the rail's collapsed state are interface state that ought to survive a reload, and
that shared property is what makes them look like one problem. They are not, and the discriminator
is not persistence but *ownership*.

The route answers where the analyst is. It is a property of the thing being looked at, so it has to
be shareable: a link into the application must land the recipient on the same screen, and a screen
named in a fault report must be reachable from that name. The rail's width answers how one person
likes their chrome. It is a property of the reader, not of the thing read.

Putting the preference in the address would break both halves of what the address is for. One screen
would acquire two addresses, differing only in a decoration nobody navigating cares about, and every
shared link would carry one analyst's layout into someone else's session. The mirror error is the one
the routing decision already rejected — holding the route in component state, where it survives
nothing and can be linked to by nobody. So the two live in different places for the same underlying
reason, and stating the reason as *ownership* rather than as *persistence* is what makes the pair
consistent rather than arbitrary.

The limitation is worth recording alongside it. Browser storage is per-browser and per-origin, so the
preference does not follow an analyst to another machine, and it is unavailable outright in a private
window with site data blocked. Both are acceptable for a preference and would not be for a route,
which is a further way of saying the two are different kinds of thing.

### The fixture had two halves, and only one of them was pretending

Retiring the Scenario Control screen's fixture turned out not to be a deletion.
The mock carried two things: a list of recent runs, and a library of the five
scenario types with the copy describing each. Only the first was a problem.

Those runs were the sharp case of the honesty rule this project keeps
restating. They held real seeds, real windows and real parameters from a batch
that genuinely ran, which is precisely what made them dangerous — rows invented
from nothing announce themselves, and rows lifted from a real batch are
indistinguishable from the database's own to anyone reading them. The library is
not data about the system's state at all. It is the closed set of five types the
generator can produce, already parity-checked against the backend enum, with
presentation text attached, and no endpoint serves it or ever will.

So the library moved out into a module of its own and became what the
application imports, the mock imports it in turn and keeps its shape for the
tests that already use it, and the runs half simply went. Deleting the fixture
wholesale would have taken with it the one half nothing else provides, and
almost certainly have been followed by quietly reintroducing it somewhere less
honest. The general form is worth stating: **a fixture is usually a mixture, and
the question is not whether it is example data but whether anything downstream
would mistake it for the system's own.**

### Emptiness rather than fiction, and a deliberate divergence from the picture

The screen's behaviour before its first answer is the item's one real departure
from the pattern the picture feed established, and the reason is worth keeping
because the two look inconsistent until the distinction is named.

The operational picture falls back to its example payload before any response
has arrived, and carries a degraded indicator from the first paint to say so.
That is defensible there: a map with nothing on it cannot be developed against,
most of the screen's machinery has nothing to show yet in any case, and the
warning is unmissable and permanent until real data lands.

A runs table is not like that. An empty table is perfectly legible — it says
"nothing here yet" without any help — so the argument that justified the
fallback does not apply, while the argument against it is at its strongest,
because these particular rows are the ones a reader cannot tell from real ones.
So the state before the first answer is *no rows*, and the screen says which of
the two silences it is in: whether the list has not been read, or has been read
and is empty. Those are different facts and a blank table would conflate them.

Stated generally: **the fallback to example data is justified by what the screen
cannot do without it, not by what looks finished.** Where an empty state is
legible on its own, the example data has no defence.


### The safeguard's hardest case is created by the bundle's own honesty

An evidence bundle carries, besides its evidence, the competing conclusions the rule ladder
considered and rejected — a claim another rule bid for the same place and lost when a
higher-precedence rule claimed it. Carrying them was an honesty decision: dropping a rejected claim
would make the bundle assert more confidence than the system has, and keeping it is what lets a
generator write a real alternative explanation instead of pretending none existed.

The consequence is a hole in the check that follows, and it was recorded when the bundle's
composition was agreed rather than discovered later. A grounding check that verifies a cited
identifier *exists* resolves a rejected claim perfectly well — the identifier is in the bundle. Such
a check would therefore certify a hypothesis citing another rule's rejected conclusion **as support
for this one**, which reads two rules' disagreement as two rules' agreement. The safeguard would put
its stamp on exactly the error it exists to catch, and nothing about the failure would look wrong: a
well-formed hypothesis, a citation that resolves, a passing check.

So the check distinguishes what may be *cited* from what may only be *discussed*. Both compartments
are in the bundle; only the evidence list is citable, and a rejected claim reached for as support is
refused with a verdict of its own rather than folded in with outright invention. The two are
different failures and the second is the worse. An invented identifier is a model producing a name
that does not exist; a citation of a rejected claim is a model misreading the document it was handed
— a comprehension failure rather than a fabrication. They are also of very different frequency, so
merging them would bury the rarer and more serious one inside the commoner one, which is the same
reasoning that gave the hosted adapter two kinds of refusal rather than one.

There is a symmetry worth stating, because it is what makes the arrangement coherent rather than
merely restrictive. The rejected claim is *supposed* to be mentioned — in the free-text alternative
explanations, which is why it is sent to the model at all and why the instructions label it as
rejected. It is only a failure when it appears in the structured supporting evidence. The same
content is legitimate in the field that is prose and illegitimate in the field that is checkable,
and that is not an accident of the design: the field that can be checked is the field that carries a
claim about what the system observed.

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

### The replay figure moved from about fourteen seconds to about ten, and the conditions are the answer

Verifying the completion flag against the real corpus produced a number that contradicted one
already written down. Three consecutive full replays of the hour measured 9.75 s, 9.64 s and 10.01 s
— about 9.8 s — against the 13.60 s and 14.25 s recorded a session earlier and reported on the
progress note as "about 14 s". The counts were identical in every run (133,634 read, 133,134
accepted, 500 quarantined, 12 batches), so this is the same work taking meaningfully less time.

The condition that differs and can be named is the state of the stack. The earlier figures were
taken shortly after the database container was started, against a freshly migrated and empty schema;
these three were taken against a container that had been up for some time and a database that
already held a previous replay's 133,134 rows. The naive expectation runs the other way — inserting
into a larger table should be slower, not faster — which points at the container rather than the
data, and the plausible mechanism is the emulation layer: the PostGIS image runs translated on this
machine, and a translation cache that is cold on the first heavy workload after start is warm
afterwards. That is a hypothesis and is recorded as one. What can be stated without qualification is
that the replay time varies by roughly 40 per cent with the state of the surrounding stack, which is
larger than the run-to-run variance of about 5 per cent measured earlier and which no single figure
quoted in the write-up should be allowed to hide.

The methodological point is the one worth carrying: a wall-time figure for this system is a property
of the machine and its warm-up state as much as of the code, and the useful reporting form is a
range with its conditions rather than a single number. The batch-size comparison taken earlier
survives this — the four batch sizes were measured in one session against the same warm state, so
the shape of that comparison holds even though its absolute values do not.

A second, independent check fell out of the column itself. `completed_at - started_at` for the
verified run read 9.765 s against the summary's self-reported 9.75 s, which is the first time the
replay's own measurement has been corroborated by a clock the application does not control.

### A mutation test reverted with `git checkout` deleted the implementation it was testing

The mutation-testing discipline this project uses — apply the mutation, assert the substitution
actually applied, run the tests, revert — was run against an implementation that had not yet been
committed. The revert step is `git checkout <file>`, which restores the file from the index, and the
index still held the version from the *test* commit. Two files of finished implementation were
destroyed, and the next mutation run then reported failures that looked like the mutation working
and were in fact the absence of any implementation at all.

That second part is the interesting failure, not the first. Losing the work cost ten minutes of
retyping. The dangerous outcome was a mutation test that produced exactly the red result it was
supposed to produce, for entirely the wrong reason, and would have been recorded as evidence had the
assertion guarding the substitution not failed first and made the discrepancy visible. The mutation
discipline already carries one rule learned this way — assert that the mutation applied before
trusting the result — and this adds its complement: mutate only from a committed baseline, so that
"revert" means what it is assumed to mean. Both rules exist because a mutation test is the one kind
of test whose *passing* is the failure signal, which makes it uniquely capable of manufacturing
false confidence.

### The first endpoint measured: 412 tracks, 58 KB, 0.4 seconds

The operational picture endpoint was verified against the development database rather than only
against fixtures. It returned the run identified as complete, 412 aircraft — the latest position of
each aircraft seen in the final five minutes of the replayed hour — in a 58 KB payload, in about
1.04 s cold and 0.40 s warm over three consecutive calls.

Two of those numbers were predicted before the code existed and reproduced exactly, which is worth
recording as evidence that the corpus is understood rather than merely stored: 412 came from a
manual SQL count taken while writing the specification, and 94 of the 412 tracks carry no altitude,
which is 22.8% against the 22.7% measured over the whole corpus in an earlier session.

The 0.40 s figure matters for the item after this one. A frontend poll is what will consume it, and a
poll interval shorter than the response time produces overlapping requests rather than fresher data.
Whether 0.4 s is dominated by the two queries, by the emulated database, or by JSON serialisation of
412 objects has not been measured, and the attribution is deliberately not claimed — the same
discipline the replay timing figure had to be corrected into.

### Two reductions kept in SQL, and one policy kept out of it

The tracks query does two things that could have been done in Python and are not: `DISTINCT ON`
keeps one row per aircraft, and a window bound keeps only aircraft seen near the end of the run. Both
exist to avoid reading 133,134 rows into the application in order to discard all but a few hundred.
The window is measured from the newest observation in the run rather than from the wall clock,
because a replayed hour from 2022 has no relationship to the time now — an obvious point that is easy
to get wrong once a playback clock exists.

What deliberately stayed out of SQL is the choice of *which* run to serve. That is a policy — prefer
a run known to have completed over a more recent one that is not — and expressing it as an `ORDER BY`
clause inside a joined query would have buried the reasoning in a place where it cannot be stated.
It is two calls instead of one, and the second call is the one that can carry a docstring explaining
why the obvious query is wrong.

### The rule found the code written the day before it, and a grep would not have

`db-006` is the enforcement half of the requirement that all SQL and spatial logic live in a
repository and none in a route handler. It was split out of the repository item deliberately and
held back until a data-serving route existed, on the grounds that a check written earlier would have
reported a clean API layer containing one health endpoint and nothing at all to bypass.

The first thing it caught was the endpoint written the previous day. Not a query — a type
annotation. The handler declared its injected parameter as `sessionmaker[Session]`, which meant the
route module imported SQLAlchemy in order to describe something it never constructed. The fix was to
name the type once in the storage layer and import that name instead, which leaves the API layer
unable to say the word `sqlalchemy` at all. That is a stronger property than "holds no SQL" and a
much easier one to check: "no storage engine is imported" is a fact about the import graph, while
"holds no SQL" is an argument about strings.

The item required the check to be mutation-tested **in both directions**, and the second direction
is the one that justifies the whole approach. A real query placed in the handler turned three
assertions red at once — the import, the statement, and the constructor — which is what stating one
property three ways is for. The identical text written into the module's docstring, phrased as a
prohibition, left all thirteen tests green. Run against the same file at the same moment, `grep -c`
returned 1.

That pair is the argument, and it is worth stating in the write-up as more than a technicality. A
text-matching check fails on the clearest possible documentation of the rule it enforces. The
rational response to such a check is to stop writing the rule down — so the check does not merely
fail to enforce the property, it actively drives out the explanation of why the property matters.
This project has now hit the same defect three times (`dal-004`, a `compose.yaml` test during
`adp-007`, and this item's own specified failure case), which is why every structural check here
parses.

### The end-to-end check the tests could not perform

Every test of the polling layer mocks `fetch`. That is the right way to test the behaviour — the
failure paths are otherwise unreachable — but it means the suite says nothing about whether the
browser, the nginx container, the proxy configuration and the backend actually agree. This project
has already shipped two defects of exactly that shape, both found on a first real invocation and
neither reachable from any test, and the lesson recorded then was that *the place the code runs is
not the place the tests describe*.

So the item was finished with a manual pass against the running stack, in a real browser:

| Step | Observed |
|---|---|
| Load the dashboard | The screen renders `replay-only`, `replayed`, and dashes for the detection summary — the real payload, not the example one |
| Watch the network | Five successive `GET /api/v1/operational-picture`, all 200, at the five-second interval, through nginx |
| Stop the backend container | The degraded badge appears, and the last real picture stays on screen — it does not revert to the example data |
| Start it again | The badge clears on the next successful poll |

Two of those four could not have been established by the test suite at all: that nginx proxies the
versioned prefix without rewriting it, and that the interval survives a container restart rather than
wedging after the first failure. The third row is the one worth keeping for the write-up, because it
is the specified behaviour observed rather than asserted — the interface degrading honestly under a
genuinely dead backend rather than a mocked one.

An honest caveat: the first read after restarting the container still showed the degraded badge,
because the backend had not finished starting. That was correct behaviour and briefly looked like a
bug, which is a reminder that a manual check needs its own controls as much as an automated one does.

### Phase 5 in review: the seam held, and the phase served real data rather than the fixture it was planned around

Phase 5 was specified as a contract mirror. Its stated purpose was to establish the seam between the
dashboard and a backend, and its stated method was an endpoint returning a static fixture in the
frontend's shape — "the point is to establish the seam, not the data". It completed with eight of
eight items done, and it did not do that. The endpoint serves real rows out of PostGIS, because
persistence and the replay adapter landed before this phase was reached and a fixture would have
meant writing the endpoint twice while putting invented data on an analyst's screen in the interim.
The plan was written when there was no database to read; the correction is recorded in
`docs/implementation.md` at the head of the phase rather than silently applied.

The phase order had already been amended once, for a different reason, and that amendment can now be
judged. Phase 5 was moved ahead of the Phase 3 view filter and the Phase 4 playback on the grounds
that both are server-side by specification, so building them against a mock would mean building them
twice. Nothing in the phase contradicted that reasoning, and one thing strengthened it: the view
filter's suppressed counts and the playback window's truncation reporting have no mock equivalent at
all, and both now have a real endpoint and a real polling client to extend rather than a client-side
approximation to throw away.

#### The contract-first prediction, scored

The frontend was built contract-first from the start: components take a typed value, screens never
import the mock, and `App.tsx` was designated in advance as the single seam where a real fetch would
replace the mock import. That is a prediction, and this phase is where it was tested. The diff for
the change that replaced the mock with a live API, over the frontend source and excluding tests:

| File | Change |
|---|---|
| `src/lib/api.ts` | new, 39 lines |
| `src/hooks/useOperationalPicture.ts` | new, 62 lines |
| `src/App.tsx` | +10 −3 |
| `src/screens/operationalPicture.tsx` | +10 −1 |
| **Total** | **4 files, 118 insertions, 3 deletions** |

The honest reading is not "one file changed". A hundred and one of the hundred and eighteen lines are
the two new modules that did not previously exist, which is transport code that had to be written
somewhere. Of the two existing files, `App.tsx` is the designated seam and behaved exactly as
designated. The screen changed too — and the detail that matters is *what* changed in it: an optional
boolean prop and a badge that renders when the data is not live. **Nothing about how the screen
consumes its data changed at all.** Had the degraded indicator not been required, the screen would
have been untouched.

So the claim that survives contact is narrower than the one originally made, and more useful: the
contract-first structure meant that changing the *source* of the data cost nothing in the components,
while changing what is *displayed* cost exactly what displaying something new always costs. The
prediction was about provenance and it held for provenance. This is the same shape as the repository
port's result one layer down — the guarantee was specified early, so the implementation had somewhere
to put it — and the repetition across two independent boundaries is worth more to the argument than
either instance alone.

#### What the phase produced

Four capabilities, of which one predated the phase's active work: the health endpoint, the
operational picture endpoint, the rule that route handlers hold no storage logic, and the polling
client. Thirty-nine new backend test functions and sixteen frontend ones, leaving the suites at 340
and 23 respectively, at 99.89% backend coverage. The end of the phase is the first moment the system
runs end to end without a mock in the path: an hour of archived air traffic enters by one command and
leaves as pixels in a browser.

#### Three limitations the phase leaves behind

The first is in the parity check, which is the phase's central mechanism. It compares field *names*
between the TypeScript contract and the response models, not types, with the two detection fields as
a deliberate exception because they carried the requirement violation this phase removed. A field
that became a string on one side and stayed a number on the other would pass. Closing that properly
means generating one declaration from the other, which is a larger change than any item here
justified.

The second is that the frontend's structural checks scrub rather than parse. The backend's equivalent
reads an abstract syntax tree, in which comments do not exist and docstrings can be identified;
the frontend's strips comments and string literals with regular expressions before matching, because
parsing TypeScript would mean adding the compiler as a dependency for a single test. Both halves were
mutation-tested and both behave correctly, but they are not equally strong, and the weaker one guards
the half of the codebase with fewer other checks.

The third is that "green" still means one machine. Continuous integration does not exist, so every
figure in this section was produced on a single developer laptop, on containers whose database runs
under processor emulation. That is already known to move a wall-time measurement by forty per cent.

#### The pattern the phase surfaced

Three separate decisions in this phase independently reached the same conclusion: report absence as
absence. A run that may not have finished carries a null completion stamp rather than a status guess;
a detection summary with no detector behind it is null rather than `Low`; a system with no health
monitoring reports `unknown` rather than `Healthy`. In each case a plausible value was available and
rejected because it would have been a claim about the world rather than a statement about the system.

The phase also surfaced the obligation that comes with it, and did so through a reader's reaction
rather than by analysis: shown a bare `unknown` in the corner of a status bar, the natural reading is
that something is broken. An absence is only legible when something explains what is absent. The two
dashes in the detection panel read correctly because they sit beside labels; the same value with no
label reads as a fault. Every place this project chooses to report absence therefore carries a
matching obligation on the interface that displays it, and the interface work that discharges those
obligations sits in a later phase than the decisions that created them.

### Four tests that did not test what they claimed, and the stub that would have caught them

`db-005` established that a collection error is the weakest possible red: it is produced by every
test in a file regardless of what that test asserts, so it proves only that nothing passed. The
response recorded there was to write a throwaway stub in which every function raises, run against it
to get a per-test signal, and delete the stub before committing. **That practice was not followed for
`scn-005`.** The new test file was run, produced a single `ModuleNotFoundError`, and was committed on
the strength of it, with the intention of substituting a mutation sweep after implementation.

The sweep was run — twenty-five mutations across the validation rules, the distance function, the two
accessors and the loader — and it found **four tests that passed for reasons unrelated to what their
names claimed**. Each is a distinct failure mode, and the four together are a better argument for the
stub than the original `db-005` finding was.

Two were *shadowed rules*: a mutation disabling the rule under test was still caught, but by a
different rule. Removing the sensor-identifier uniqueness check left `test_duplicate_sensor_ids_are_rejected`
green, because the test collided two adjacent sensors and the resulting layout then failed the
*discrimination* invariant instead — excluding "the other RF-01" stranded Rotterdam with no
neighbour. Removing the channel-count check left its test green because the contiguity rule was
written as `indices != list(range(CHANNEL_COUNT))`, which tests the count as well as the order and
made the count rule unreachable. The first was fixed in the test, by colliding the two ends of the
layout instead, where both sensors keep their real neighbours; the second was fixed in the
*implementation*, by making the contiguity rule compare against the plan's own length so each rule
tests exactly one thing. A rule that cannot be observed to fail on its own is either redundant or
untested, and the two cases are indistinguishable until something tries to tell them apart.

The third was an *unobservable boundary*. Changing the neighbour test from `distance <= radius` to
`distance < radius` broke nothing, because no pair in the shipped layout sits exactly on the radius.
Whether the radius is inclusive is not a detail: it decides `anom-007`'s evidence on any layout tuned
to it, and it was settled by nothing at all. A test now places a pair exactly on the boundary by
deriving the radius from the measured distance, and asserts both that the pair is a neighbour at that
value and that it is not one nudge below it.

The fourth was a *test proving the wrong thing entirely*. `test_an_unknown_key_is_rejected` renamed a
field, which removes a required key as well as adding an unknown one, so it stayed green when Pydantic's
`extra="forbid"` was removed: it had been proving required-field enforcement all along, which another
test already covered. It now adds a key without removing one.

The finding is that the stub is not merely a stronger form of the same check. A per-test red
distinguishes "this test fails because the implementation is absent" from "this test cannot fail",
and all four defects above are in the second category — they would have been visible in about two
minutes against a stub, and instead cost a twenty-five-mutation sweep, two test rewrites and one
implementation change after the code was already written. The mutation sweep is the more thorough
instrument and remains necessary for structural guards that assert an absence; it is a poor
substitute for the cheap check it was used to replace. *(The practice for the remaining Phase 7 items
is the stub first, then mutations on the absence guards only.)*

One further deviation is recorded plainly: a rejection branch for a channel plan of the wrong length
had no test at all in the first pass of the file, and was found by the coverage report after the
implementation was written. The test was added afterwards, which reverses the specified order, and
says so in its own comment.

### A property built third in its own phase, on the smallest emitter that could carry it

Phase 7 begins with `scn-001` by identifier and could not begin with it in practice. The item states
a property — same type, parameters and seed give a byte-identical stream — and a property has no
output of its own to test. Proving it requires a stream, the stream comes from the scenario types
(`scn-002`), the types emit through the synthetic RF adapter (`adp-002`), and the adapter reports on
a sensor and channel grid that did not exist until `scn-005`. The `normal-baseline` type cannot serve
as the minimal case either, because it injects nothing by definition — that is what makes it the
false-positive control — so determinism over it would be nearly vacuous.

The order was therefore reversed deliberately: `scn-005` first, as the one item in the phase with no
dependency on the others, then `scn-001` together with the smallest emitter that has randomness to be
deterministic about. What that emitter turned out to be is worth recording, because it is not a
scenario type and the distinction keeps the three items from collapsing into one. It emits the
unperturbed baseline — a nominal noise floor with seeded per-cell variation, one reading per sensor
per channel per interval — and nothing else. Injection and the ground-truth record belong to
`scn-002`; wiring the stream through the Data Abstraction Layer into storage belongs to `adp-002`.
The emitter produces source records in the same shape the OpenSky adapter produces, carrying no
provenance, no data mode and no scenario run identifier, because those describe the run rather than
the record and are attached at the DAL. It carries no scenario type or ground truth either, per
`api-009`: `RunSpec` holds the scenario type because the run record needs it, and the emitter never
reads it. The moment an emitter branches on scenario type, the generator can see the answer key.

The generalisable point for the write-up is that the numbering of a backlog is not a build order. The
identifiers here encode the order the capabilities were *thought of*, which put the property that
constrains everything first and the configuration everything depends on last.

### The generator measured across two platforms, and what four mutations showed

The reproducibility claim was tested rather than asserted, on two axes.

The first is cross-platform identity. The same run — the shipped seven-sensor layout, seed 20220627,
a sixty-second span, default parameters — was emitted on the development host and inside the Linux
container, and the SHA-256 over the canonical serialisation of the 336 records was identical:
`92e53488…c5ed`, with cell zero reading −96.92 dBm at a −1.92 dB delta in both. The conditions matter
more than the digest: **macOS on arm64 under Python 3.14.3 against Linux on aarch64 under Python
3.13.15**, so the result spans an operating system and a Python minor version. It does not span a
processor architecture, which is the obvious remaining gap. *(Record here whether the digest survives
an x86-64 run, which the first CI job under `ops-002` will produce for free.)*

The second axis is whether the tests would notice if the property failed. Four mutations were applied
from a committed baseline, each confirmed to have been substituted before the suite was run, and each
reverted afterwards. The two rows to read are the first and the third.

| Mutation | Tests red | Tests green |
|---|---|---|
| `derive_unit` uses the built-in salted `hash` | 2 | **19** |
| A wall-clock read inside the per-cell reading | 5 | 16 |
| The emitter ignores its seed entirely | **1** | 20 |
| `replay.py` re-implements the run row in SQL | 1 | (that test only) |

A generator whose stream differs between processes — which is to say a generator that cannot
reproduce a campaign at all — leaves nineteen of twenty-one tests green, including every test whose
name contains the word "identical". A generator that ignores its seed completely, and would therefore
turn `scn-003`'s batch of thirty runs into thirty copies of one run, is caught by exactly one test.
Both defects are invisible to the check a developer naturally writes, which is to emit twice in one
process and compare. **The two tests that catch them are the two the item's failure cases name and
the two that are easiest to leave out**: the cross-process comparison, which requires spawning
children under differing `PYTHONHASHSEED` values, and the arm asserting that *different* seeds give
different output. This is the strongest available argument for writing a spec's failure cases down
before the tests rather than after.

The cross-process test carries a guard for the same reason: each child also reports `hash("em-fusion")`,
and the test asserts those two values differ before it compares the digests. Without it, an
environment variable that failed to take effect would produce two identical digests and a passing
test that had measured nothing.

Two smaller findings sit alongside these. The parse-versus-grep defect appeared for the fourth time
in this project: the module that most clearly documents why the built-in `hash` and the `random`
module are not used says `hash` three times and `random` twice, all in prose, and the syntax-tree
check over it passes. A text search would have flagged the file precisely because it explains the
rule — which does not merely fail to enforce the property, it drives the explanation out of the
codebase. And the practice recorded at the end of `scn-005` — write a stub, run the new tests against
it, and get a per-test red before implementing — **was not followed here**. The first run produced a
single collection error, which satisfies the letter of the workflow and establishes nothing, exactly
as the `db-005` entry above describes. The cost was one defective test that survived to the green
stage: a check that `app/replay.py` no longer owns the run row asserted `not hasattr(module,
"create_scenario_run")`, which is false as soon as the module imports the name it is supposed to
use. It was rewritten to assert that the module defines no function of that name and that the name it
holds *is* the storage layer's function, which is both sharper and what was meant. In fairness to the
stub practice, a stub would not have caught this one — the flaw only becomes visible once the import
exists — but the deviation is recorded because the reason for skipping it was momentum rather than
judgement.

### A mitigation that had been recorded as available was not, and making it real corrected the threat it mitigates

The coverage-gap scenario injects a dropout by suppressing an aircraft's reports for a window, and
the corpus already contains a small number of natural dropouts in the same duration band. The
mitigation recorded in the threat-to-validity note above was to refuse those tracks as injection
sites, and it was described as cheap on the grounds that the coverage report already identified
them. It did not. `coverage.json` reports a distribution and keeps no identity, so the mitigation
had no input and would have been found to have none at the moment `scn-002` reached for it — after
the scenario generator was being written, which is the expensive moment rather than the cheap one.

The gap between the recorded claim and the artefact is the finding worth carrying into the write-up.
It was not a mistake in the analysis, which was correct, but in the *retention* of it: the hand
analysis was run, its conclusion was written into the notes, and the thing that would let anyone act
on the conclusion was never produced. A number in a document and a capability in a system are
different objects, and prose is very willing to describe the second while recording only the first.

`adp-008` produces the exclusion list as a committed artefact rebuilt by the same command that builds
the corpus. Three decisions in it are worth recording. **Identities are pseudonyms**, because the
artefact is committed and `icao24` is a 24-bit space, so a committed list of source identifiers would
hand a reader the mapping `dal-004` exists to prevent — the generator therefore derives the pseudonym
for each candidate track and tests membership, rather than the reverse. **Two filters separate a
coverage failure from an artefact of the bounding box**: a gap counts only when both bracketing rows
sit at least a quarter of a degree inside the boundary and the aircraft is airborne at both ends,
which is the same correction the box sweep needed when its naive figure reported gaps of 3,140
seconds in a 3,600-second file. **Where a rule is uncertain the analysis over-reports** — a row whose
ground flag is missing is treated as airborne, so its gap is listed — because being wrongly on the
list costs one candidate injection site out of hundreds, while being wrongly absent from it costs the
false-positive rate for an entire scenario type. The asymmetry is not close, and recording it stops
the choice being made by whichever branch happened to be written first.

Running it against the real extract reproduced the ten recorded durations exactly — 20, 100, 110,
200, 280, 280, 300, 970, 1,160 and 1,440 seconds — which is strong evidence that the reproducible
analysis and the hand one are the same analysis. It also showed the ten gaps belong to seven
aircraft, correcting the confound figure from 1.05% of the fleet to 0.74%. Both corrections are
recorded against the original paragraph rather than replacing it.

Two smaller deviations are recorded plainly. Three branches of the module had no test in the first
pass and were found by the coverage report afterwards, so their tests were written after the
implementation and say so in their own comments — the same reversal of order that `scn-005` recorded,
and the second time the coverage report has been the thing that noticed. And two of this file's own
tests were wrong on first run: one assumed each aircraft carries at most one gap, which is what the
corrected figure above disproves, and one used a fixture in which the second aircraft had a
qualifying gap of its own while asserting that only one gap existed.

### `scn-002` in four passes, and what each one found

The item was too large to test in one batch — roughly sixty tests over two producers — so it was
built in four passes, each a complete spec-test-code cycle with no code preceding its own tests: the
RF grid, the replayed tracks, the ambiguous type together with the shared zone, and the answer key
reaching the database. The structure is worth recording because the passes found different kinds of
thing, and only the first was the kind the workflow is designed to find.

**Pass 1** was uneventful and produced the item's strongest test.
`test_every_untouched_cell_is_identical_to_the_quiet_run` compares an injected run against the same
seed's baseline cell by cell: 5,040 readings in a fifteen-minute run, of which 60 change — two
receivers, one slice, thirty ten-second steps, exactly what the answer key says. That test is only
*passable* because of the keyed derivation chosen in `scn-001`; under sequential draws the extra
per-cell draw would shift every reading after the first one it touched. A design decision made for
one reason paid off in another, which is the kind of thing worth noticing in a write-up rather than
presenting as foresight.

**Pass 2** shipped the co-location defect described in System Design above, and produced a test
defect of a family this project keeps meeting. An `api-009` check asserted that no key of a record
contains the substring `"ground"` — and `on_ground`, a legitimate field recording whether the
aircraft is airborne, matches it. The same assertion in pass 1 had passed only because RF payloads
happen to carry no similarly-named field. Both now compare *structure*: a perturbation may change
what a field says, and may never add a field. This is the fifth appearance of text-matching where
parsing was needed.

**Pass 3** required editing pass 2's committed tests, because the zone changed the signature they
called and their fixture aircraft sat at Köln/Bonn, outside it. Editing tests to accommodate an
implementation change is usually a smell; here it is the correct response to a misreading being
corrected, and the change is annotated in the file so the reason survives.

**Pass 4** raised a question the spec had not settled: *when* ground truth is recorded. The item says
"at generation time, never inferred afterwards from detector output", which rules out the wrong
answer without choosing between two right ones. What a run intends to stage is known before it
starts; which aircraft it actually touched is known only once the corpus has streamed past, because
whether a targeted aircraft appears inside the zone during the window is a property of the data
rather than of the seed. Recording only the plan would mean an answer key naming aircraft that never
appeared, scoring the detector as having missed things it was never shown. Recording only at the end
would mean a run that died part-way left no record of what it was attempting. Both are therefore
written: the plan with the run row, the completed key at the end of generation. Both are generation
time, and neither consults a detector.

Mutation results across the four passes, each applied from a committed baseline, asserted to have
been substituted, and reverted:

| Mutation | Red |
|---|---|
| A sixth scenario type added | 1 — the closed-set assertion, and nothing else |
| Perturbation ignores the zone | 2 |
| The two halves stop sharing a centre | 4 |
| The answer key written as `{}` rather than null when absent | 2, including an existing replay test |

The first row is the one the stub practice predicted. `test_there_are_exactly_five_scenario_types`
passed against the stub, because the stub declared the enum — an absence assertion, which the
practice established at `db-005` says to mutation-test rather than delete. Two further tests in pass
3 passed against their stub for a different and legitimate reason: the ambiguous type inherits its
single-receiver shape from pass 1, so those tests assert a composition that was already true. They
are regression guards and cannot fail today, which is recorded rather than treated as a pass.

### The synthetic run commits whole, and the argument that chose windows for the replay reverses

`adp-007` tiles a replay into five-minute windows and commits each one separately, which is a
deliberate weakening of the all-or-nothing guarantee the Data Abstraction Layer makes: an
interrupted replay leaves the windows it already wrote in place. `adp-002` does the opposite. One
synthetic run is one transaction, and a run that fails part-way leaves nothing at all. The two
decisions look inconsistent and are not, because the argument that produced the first reverses on
the second side of the system.

What decided the replay was the cost of losing committed work. The corpus is 133,634 rows and takes
about ten seconds to drive through the DAL into PostGIS; it is also an artefact that cannot be
redistributed under the OpenSky licence and is rebuilt from a manifest rather than stored, so work
lost there is work that has to be reconstructed from outside the repository. A synthetic run has no
equivalent cost. It regenerates byte-identically from its seed — an hour of the shipped layout
emits in about a tenth of a second — so discarding a partial run and repeating it is close to free,
and the thing that was expensive to lose is the thing the seed makes cheap to recreate. Size does
not resist the choice either: one fifteen-minute run is 5,040 records against roughly 11,100 in each
of the replay's twelve batches, so the large-transaction objection that shaped `adp-007` does not
apply at this scale.

The consumer decided the rest. `scn-003` executes batches of twenty to thirty runs and is required
to record a failing run and carry on rather than abort, which means the store will contain rows
belonging to runs the batch knows failed. If a failed run could leave half its grid behind, those
rows would still be read as observations by everything downstream — a detector would see a run that
simply stops mid-window, and would be right to call it a coverage gap. The scenario type that
stages exactly that signature is one of the five. Committing whole means a skipped run contributes
nothing rather than contributing a convincing artefact.

Three smaller decisions in the same item were made for the same kind of reason — removing the
opportunity for a caller to be wrong, rather than detecting it afterwards.

The adapter **plans the incident itself** from the run specification rather than accepting one.
Accepting an `Incident` would have been symmetrical with the emitter underneath it, which takes one,
and it would allow a caller to emit a quiet grid under a run row whose answer key claims
interference. Nothing downstream could detect that: the observations would be internally consistent,
the ground truth would be internally consistent, and the run would score as a total detection
failure. Since the planner is a pure function of the layout and the specification, the batch runner
computing it again for the answer key gets the same result by construction rather than by
agreement.

The **data mode is not an argument**. A synthetic source has exactly one mode it may claim, and the
analyst-facing badge reads that field off the data rather than off a constant in the interface, so a
mislabelled row makes the interface misdescribe what the analyst is looking at. Building the ingest
context inside the adapter removes the parameter that could carry the wrong value, and the
corresponding test asserts the other enum member is never referenced in the module at all.

The **pseudonymiser is carried and unused**. RF payloads have no identifier rules, so substitution is
a no-op on them, and it would have been tidier to let this one source skip the argument. It is
passed anyway, because the guarantee that provenance and pseudonymisation are properties of the
architecture rather than of each adapter's diligence rests on there being one way in. A single
entrypoint with an exemption for one source is not a single entrypoint, and the next source arrives
to find two patterns and a choice to make.

#### A test whose two sides were not comparable, and the one that hid behind it

The implementation found a defect in the tests written the same day. Two tests compared a digest of
the stored observations against a digest of the emitted stream: one asserting equality for the clean
scenario type, the other inequality for a staged one. The stored side was flattened to a timestamp
and a payload; the emitted side was digested as whole source records, which also carry a source
identifier, a source type, an observation type and a location. The two sides were therefore never
comparable, and neither test was measuring what it claimed. The equality assertion could not hold
however correct the adapter was, and the inequality assertion could not fail however wrong it was.

Only one of the pair announced itself. The equality test failed on the first run of the
implementation and was investigated; the inequality test had been green since it was written and
would have stayed green through any mutation, including the one that mattered — an adapter that
never applies the incident at all. The false-passing test was invisible precisely because its twin
failed loudly, which is the part worth recording: a broken assertion in a pair is easy to find, and
its mirror image is not. Both sides now reduce to the same shape before they are digested, and the
mutation table below confirms the inequality test is sensitive to the thing it exists to detect.

This is a different family from the text-matching defects recorded earlier in this chapter. Nothing
was being matched as text; the failure was comparing two *representations* of the same data and
reading the difference between the representations as a difference in the data. The generalisation
is that an assertion whose two sides come from different layers has to be reduced to one layer
explicitly, and that a test which can only ever pass is as useless as one which can only ever fail —
but far harder to notice, because the suite is green.

#### Mutations, all applied from the committed baseline and reverted

| Mutation | Red |
|---|---|
| The incident is never planned; the run emits quiet under a staged specification | 2 |
| The run is marked as replayed rather than synthetic | 2 |
| The adapter nudges a reading by a value it derives itself | 3 |
| The adapter defines its own run-creation function | **1** |
| One batch per tick instead of one per run | 1 |

The fourth row is the one the practice established at `db-005` predicted: it is a structural
assertion of an absence, so it passed against the stub and could not have failed before the module
existed. It is also the only test that moves under that mutation, which is the argument for writing
it — an adapter that opened its own run row would produce rows that look entirely correct, and
nothing about the stored data would be wrong until two producers disagreed about what a run is.

The item measures 11 statements at 100% coverage, inside a suite of 508 tests at 99.92%. The figure
worth keeping is not the coverage but the ratio: nineteen tests and mutation evidence for a function
that is one call to the ingest entrypoint. The expense is deliberate, because this function is the
one the evaluation campaign runs twenty-five times per scenario type, and a defect in it is a defect
in every measurement taken afterwards.


### Two defects the batch runner had that only running it could find

`adp-007` recorded that its command shipped two faults reachable only by invoking it, both of the
shape "the place the software runs is not the place the tests describe". The batch runner produced
two more, and neither is of that shape — which is the more interesting result, because it means the
category is wider than the earlier entry suggested.

**The first was a stale image, and the target had no build prerequisite.** Every containerised target
in the root Makefile depends on its image being current, for a reason the file states in a comment:
Compose bind-mounts the source but not the installed packages, so a cached image runs today's code
against yesterday's dependencies. `generate` was the single target with no such dependency, because
it had never worked and so had never needed one. The first invocation died importing SQLAlchemy — a
dependency added weeks after the pipeline image was last built. The fix is a `build-pipeline` target,
and the finding worth keeping is that the pipeline service builds its own image from the same
directory rather than sharing the backend service's, so refreshing one does not refresh the other.
Nothing in the test suite could see this: the tests run inside a freshly built backend image.

**The second was a batch that reported twenty successes and produced twenty mislabelled controls.**
Invoked with a two-minute run duration and the default incident offset of two minutes, every run
staged its incident after its own end. Nothing was suppressed and no cell was raised, so all twenty
runs were byte-identical to quiet controls — while their rows claimed `aircraft-coverage-gap` and
their answer keys named nothing. The command printed `ok` twenty times.

This is the exact inverse of a failure case the specification already had. `scn-002` says a
`normal-baseline` run that injects any deviation fails the spec, because the false-positive rate
depends on the control being genuinely clean. The mirror — an injected type that injects nothing —
was not written down, and it is the more dangerous of the two: a contaminated control inflates the
false-positive rate, which is visible in the results, whereas an empty incident inflates the
*miss* rate against an event that never happened, which looks exactly like a detector that is not
working. The configuration is now refused before any run opens, and the message says why.

The general lesson is one this project keeps meeting from new directions. A test asserts what
somebody thought to assert; running the thing asserts what the thing does. Both defects were in code
covered at one hundred per cent by tests that passed.

### The second contract-first screen, and the five shapes that keep it honest

The Operational Picture was built against a typed contract and a mock before `api-002` existed, and
the seam held: when the endpoint arrived, four files changed and 118 lines, none of them in a
component that consumes the data. Scenario Control is the same bet placed a second time. It is worth
recording because "it worked last time" is not the reason, and because this project has a written
rule that appears to forbid it.

The phase order was amended once already to put Phase 5 in front of the Phase 3 view filter and the
Phase 4 playback transport, on the grounds that both are *server-side by specification* — a
client-side filter built against a mock is a filter that gets built twice and thrown away once. The
question for `scn-004` is whether the Scenario Control screen is that kind of thing. It is not. Every
obligation the item is judged on is client-side and provable today: the seed field is visible and
editable, replay of a listed run reuses that run's recorded seed and parameters, the library offers
exactly five types, and a run started with no seed shows the seed it was given. The one part that is
irreducibly server-side — actually starting a batch — is the part the screen deliberately does not
simulate.

**The risk the bet carries is a contract that describes a generator nobody has**, and that is what
the parity tests are for. Five shapes are declared twice, in two languages that no compiler checks
against each other, and the backend suite parses the TypeScript and compares them in both
directions: the configuration form against the batch entrypoint's own arguments, its defaults against
that parser's defaults, the recorded parameters against what `as_parameters` writes onto a run row,
a listed run against the run summary, and the five type identifiers against the scenario enum. A
sixth shape is asserted as a closed set rather than a blacklist, because `api-009` is a rule about
what must never appear and the only version of that rule a test can hold is one that fails on
anything new.

The parser those tests use was `api-002`'s, and it was lifted into `backend/tests/contracts.py` when
the second suite needed it. Two copies of a parser is two places for the rule to drift while both
suites stay green, which is the exact failure the parity tests exist to prevent one level down.

**The design reference asked for three controls the generator does not have.** The generated mockup
for this screen shows Noise Amplitude, Affected Sensor Count and Gap Duration, and renders the seed
as `0xA4F2`. The generator accepts none of those three: its dials are the incident's offset,
duration, radius, elevation and spectral extent, plus the run count and the per-run duration. Putting
the mockup's controls on screen would have produced a form whose sliders change nothing, which is
`scn-001`'s fourth failure case — a parameter that controls nothing is the same defect as a seed that
controls nothing — arriving through the design rather than through the code. The rule adopted is that
the form offers exactly what `python -m app.pipeline` accepts, minus `--data-dir`, which says where
the corpus lives rather than what the run is; and the test that enforces it reads the parser rather
than a list, so a dial added to either side alone fails. The seed is rendered as the decimal integer
the run record stores, because its whole purpose is to be pasted back into a command or re-sent by a
replay, and a second representation is one more conversion to get wrong.

This is the first place in the project where the generated design and the built system diverge on
substance rather than on styling, and the divergence runs in the direction worth noting: the mockup
is a plausible-looking instrument panel for a generator that was never built.

**A control that cannot act is rendered as a control that cannot act.** `api-006` does not exist, so
start, reset and replay take handlers that are not supplied, and the screen renders them disabled
with a note saying a batch runs from the command line today. Hiding them was the alternative and is
worse: an unbuilt capability the screen conceals is exactly the degradation `NFR-204` requires to be
visible, and a disabled control with a reason attached is also the most accurate statement of where
the system is.

**One requirement is met by refusing it.** `FR-714` lists start, pause, reset and replay; `FR-806`
specifies start, reset and runs, and provides no pause endpoint. Generation has nothing to pause: a
batch is a loop of whole runs, each committing atomically in about three seconds, so the only
coherent reading of pause is "stop after the current run", which is a server-side lifecycle nothing
in the specification describes. `FR-717`'s playback transport over a recorded run's simulated time is
where a pause control has something to pause. The screen therefore renders no pause control, and the
divergence from `FR-714` is recorded here and in the spec item rather than being quietly satisfied by
a button that does nothing.

### The frontend measures no coverage, and three tests were missing because of it

The backend gate is 90% and it has repeatedly earned its place: `scn-003`'s refusal of an unknown
recorded parameter was written only because coverage reported the branch had never been exercised,
and that deviation is recorded under Implementation above. The frontend has no coverage tooling at
all — `vitest --run` with no `@vitest/coverage-v8` — so nothing measures the same thing on that side
of the repository.

The consequence showed up immediately. After `scn-004`'s implementation passed all nineteen tests
written at the test stage, three behaviours had no test at all: the reset control's handler, which no
test ever clicked; the spectral-extent control, which no test ever changed, so nothing proved the
value reached the start payload; and the fallback that names a run whose type the library does not
list. All three were written afterwards and marked in their own comments as deviations from the
order this project works in. On the backend, the gate would have named all three before the commit.

The asymmetry is worth stating as a measurement rather than an impression: **nineteen tests written
against a specification caught sixteen of nineteen behaviours; the three it missed were all
behaviours with no assertion rather than wrong assertions**, which is the class of gap a coverage
report finds mechanically and a careful reading of the spec does not. Adding the tooling is a new
dependency and is left as a decision rather than taken mid-item, but the argument for it is now
evidence rather than principle.

### Eight mutations in place of a coverage report, and the one test they left unproved

The navigation item was the first to land after the gap recorded above — that the frontend measures
no coverage, and that three of `scn-004`'s behaviours consequently had no test. No tooling was added
for it, since that remains an open decision rather than something to take mid-item, so the tests were
instead checked by mutation: each decision in the specification was broken in the implementation, one
at a time, and the suite was run to see whether anything went red.

Eight mutations were applied to the tree committed at `fe5b5c6`, under Node 24.18.0 and Vitest 4.1.9,
against a suite of 55 tests of which 10 belong to this item. Each was applied singly and reverted
from a copy taken before the pass — not with `git checkout`, which on an earlier item deleted the
untracked implementation it was meant to be testing, a mistake recorded above and avoided here by
construction rather than by care.

| Mutation | Red |
|---|---|
| A fourth entry joins the rail | 2 |
| An unrecognised address renders no screen | 1 |
| The route lives in state, so the address is ignored | 1 |
| Every entry marked as the current page | 2 |
| Fixture rows presented with nothing saying so | 1 |
| The poll runs above the switch, for every screen | 1 |
| The Hypotheses destination renders a blank page | 1 |
| The Scenario Control entry leads nowhere | 4 |

Every mutation was caught, and each failed on the test written to catch it rather than on some
distant assertion — which is the property worth having, because a suite where one broken thing turns
twenty tests red localises nothing.

The more useful result came from tallying which tests the mutations had exercised rather than from
the mutations themselves. The first seven were derived from the specification's six decisions and its
two failure cases, and they moved nine of the ten tests; the tenth, which asserts that choosing the
Scenario Control entry actually reaches that screen, was untouched, because no mutation of a
*decision* breaks the wiring that the decision presumes. The eighth mutation was written for it
specifically. This is a limit of specification-derived mutation worth stating plainly: it tests the
claims a specification makes and is blind to the assumptions the specification does not think to
state, so the tally of tests against mutations is the step that finds the gap, not the pass itself.
A coverage report would have found the same gap mechanically, and the argument for adding the tooling
is unchanged.


### A caption the tests could read but not see, and a third kind of blind spot

The browser pass that closed the navigation item found a defect in the screen the item had just made
reachable. The recent-runs table's caption was rendering *below* the column headers rather than above
them, and the cause was one word: the caption reused the constant that styles field labels, and that
constant begins with `block`. Setting `display: block` on a `<caption>` takes it out of the table's
caption box, so the browser stops hoisting it above the table and lays it out in normal flow instead.

What makes it worth recording is why nothing caught it. The suite finds that table *by its accessible
name*, which the caption supplies, and the name is correct however the caption is displayed; the DOM
order never changed either. So the tests were not merely silent, they were **passing for the right
reason on the exact element that was wrong** — and the project's own testing convention, which
forbids asserting on CSS classes in favour of analyst-visible behaviour, is what closes off the only
assertion that would have caught it. jsdom does not do layout, so no test written under that
convention can see a box-model defect at all.

That is a third distinct blind spot, alongside the two already recorded. Coverage tooling finds
behaviours with no assertion. Mutation finds assertions that are not load-bearing. Neither finds a
behaviour that is asserted correctly and *rendered* wrongly, and only looking at the running
interface does. The fix therefore landed with no accompanying test, which is a deviation from the
order this project works in and is recorded as one; writing a class-name assertion to satisfy the
form of the workflow would have contradicted the testing convention while still proving nothing about
the rendering.

### A cosmetic transition broke the feature it was decorating, and only the browser said so

The rail item's specification carried a known limit, written down before any code: that a collapsed
rail's *width* is not assertable from this project's test stack, because jsdom performs no layout and
the testing convention forbids reaching for the CSS class instead. It was recorded as the third blind
spot in a row. It then produced a real defect within the hour, which is a sharper demonstration than
the prediction deserved.

Eleven mutations were run against the finished rail. Ten behaved: each went red on the test written
for it. Two survived, and they are the interesting pair.

The first survivor was **a test of mine that could not fail**. A test asserting that all three entries
keep their accessible names while collapsed passed unchanged when the label was deleted outright,
because the collapsed entry also carries a tooltip and a tooltip supplies an accessible name when
nothing else does. The requirement held — by a mechanism other than the one under test — so the test
was measuring the tooltip. It now asserts the label text itself as well, and the mutation duly turns
it red. This is the same class as the four found in the layout work, and it was found the same way:
by breaking the thing on purpose rather than by reading the test.

The second survivor was the width, exactly as predicted — and behind it sat the defect. Driving the
finished rail in a real browser showed the collapse doing everything except the one thing it was for:
`aria-expanded` flipped, the preference was written, all three entries and the current-page marker
survived, the address was untouched — and the rail stayed 280 pixels wide. Mounting the page
*already* collapsed rendered at 56 pixels correctly. The difference between the two was a width
transition, added for polish, which left the element at its old used width when the class changed
rather than animating to the new one. Removing it fixed the feature outright.

Three things are worth drawing out. The specification had already declared the transition out of
scope as cosmetic, so the decoration that broke the feature was not even part of the deliverable —
deleting it was cheaper than debugging it, and the decision to delete followed directly from having
written down what the item was actually for. The test suite was green throughout, before and after,
because every assertion it makes is about semantics and the failure was entirely in layout. And the
defect is invisible in exactly the way the caption defect was: the mutation that should have caught it
is the one the specification had already flagged as uncatchable. **A blind spot named in advance is
still a blind spot**; naming it buys the knowledge of where to look by hand, not immunity.

### Two tests that could not fail, and the fixture that satisfied them

Wiring the screen to its endpoints produced the clearest instance yet of a
defect this project has now recorded four times, and the red run caught it at
exactly the moment it is supposed to.

Two of the tests were written to prove that the runs on screen come from the
database rather than from the fixture. Both passed **before a single line of the
implementation existed**. The cause was mine: building the fake API response, I
had reused seed values taken from the fixture itself — they were the numbers to
hand, because they were the ones visible on the screen at the time. So a test
asserting that the table shows API rows was satisfied by the table showing
fixture rows carrying the same numbers. The test could not fail, and its subject
was precisely the thing it could not detect.

The fix was to pick seeds appearing nowhere in the fixture, and then to assert
both halves rather than one: that the API's rows are present *and* that every
one of the fixture's is absent. The second assertion is the load-bearing one,
and it is the one the original framing had no way to express.

The lesson is narrower than "watch the tests fail" and worth stating on its own:
**a test that distinguishes A from B must be built from values that occur in
only one of them.** Drawing the fixture for the new behaviour from the old
behaviour's data guarantees the two are indistinguishable to the assertion, and
no amount of care in the test's wording recovers that. Four instances now sit on
the record — the four in the layout work, the tooltip satisfying the rail's
label test, and these two — and the only thing that has ever found one is
running the test against something that ought to break it.

### A structural check that punished writing the rule down, for the third time

The same item produced a fourth recurrence of a defect this repository has
documented three times before, which is enough repetition to be worth naming as
a pattern rather than as an incident.

A test was added asserting that the application imports the retired fixture
nowhere. It failed immediately, on the module that had just been created to
*replace* the fixture — because that module's opening comment explains where it
came from, and names the fixture in doing so. A check scanning raw source cannot
tell a rule broken from a rule described, and the path of least resistance is
always to delete the explanation.

The established answer here is a scrubber, and the interesting part is that it
had to be applied differently. The transport check strips comments **and string
literals**, because it looks for `fetch(`, which a string can name innocently.
This check looks for an *import*, and an import path is a string literal — so
scrubbing strings would have made it match nothing at all and pass forever,
which is the same failure wearing the opposite mask. Comments are stripped and
strings are kept, and a further test asserts both halves: that a real import is
caught and a described one is not.

**The general rule is that the scrubber has to be cut to the thing being
searched for.** A single shared helper applied uniformly would have been wrong
in one direction here and wrong in the other there, and in both cases silently.

### A remedy copied twice, and the third caller that did not know about it

The batch button, the first time it was pressed against the running system, reported success over a
failure. The screen said *Batch accepted — 20 runs from base seed 1817692939*, no runs ever appeared,
and the reason sat in a container log: the pseudonymisation seed was not set.

The immediate cause is a defect this project had already recorded twice. Compose passes that seed
through from the host, so a host variable that is **unset arrives inside the container as an empty
string rather than as absent**, and the library that reads the configuration file treats
present-but-empty as present — so nothing shadowed a perfectly good file sitting right there. Both
command-line entrypoints handle it. Each carries its own four-line block, and each carries its own
comment explaining the trap, because the defect was found twice and fixed twice in the place it was
found.

That is the part worth keeping. **A remedy that has been copied is a remedy the next caller will not
know about.** The batch launcher was a third site with the same need, written months later and by a
different route into the system — an HTTP request rather than a command — and there was nothing in
the code to tell its author that two other places had already solved this. Two copies of a fix look
like diligence; they are better read as a warning that the thing is easy to get wrong and has no
single home. The fix therefore extracts one function that all three call, beside the object it
protects, rather than adding a third copy.

The testing lesson is sharper and less comfortable. The launcher had tests, and they could not have
caught this: they substitute the thing that reads the seed, precisely so the tests need no seed. The
substitution that made them runnable is the substitution that made them blind. This is the second
recurrence of the more general rule — **the place the code runs is not the place the tests describe**
— and, as with the two faults recorded under Phase 5 and the caption defect, what found it was a
person pressing the button.

A limitation remains, and is more interesting than the bug. The request is answered before the work
starts, so nothing carries a later failure back to the caller. A batch that dies is, from the
screen's point of view, indistinguishable from one still running. That is the same shape of
dishonesty the project argues against everywhere else, it is not fixed, and it is recorded as owed
work rather than folded into a claim that the feature is complete.

### The requirement that could not be proved against its own data

`anom-002` requires the RF baseline to be computed per sensor *per channel*, and states pooling as a
named failure case: averaging a sensor's eight channels into one number hides a deviation confined
to one of them inside the spread of the other seven. The requirement is sound, and the argument for
it is `anom-007`'s — the sensor-fault rule discriminates a single loud channel with clean neighbours
from a deviation across all eight, and a pooled baseline removes that distinction before the rule
can make it.

Before writing the tests, the baseline data was measured rather than assumed. Across the twenty
completed `normal-baseline` runs held in the development database: 100,800 RF readings, 56
sensor-channel cells, 1,800 samples per cell, a pooled mean of −95.00 dBm and pooled standard
deviation of 1.50 dB. The discriminating figures are the per-cell ones. **Cell means span 0.177 dB,
from −95.081 to −94.904, and per-cell standard deviations run from 1.437 to 1.551.**

The fifty-six cells are, on quiet data, statistically indistinguishable. That is not a defect in the
emitter; it follows directly from `scn-001`, which gives every cell the same nominal power and the
same noise spread by construction. But it has a consequence for how the requirement can be
established: **a pooled implementation would reproduce the per-cell numbers almost exactly, so any
test of the granularity built from quiet runs alone would pass whatever the implementation did.**

This is the same failure shape recorded twice already in this project — a test that cannot fail
because it was built from values common to both of the things it was meant to separate. The
difference is that here it was found by measuring before writing rather than by a mutation pass
afterwards, which is the first time that ordering has held.

Two things follow, and both are recorded on the spec item rather than left in the code. The
granularity is justified **structurally rather than empirically on clean data**: it is what makes
the sensor-fault discrimination possible once something is injected, not something the quiet corpus
demonstrates. And the tests that prove it are built from a constructed series in which one channel
is genuinely loud — fifteen dB above its neighbours, far outside the 1.5 dB natural spread — with an
assertion that no cell's baseline equals the per-sensor pool. A pooled implementation puts a number
in all eight cells; the assertion is that the number is wrong in all eight, which is the only form
of the claim that a pooled implementation cannot satisfy.

The wider methodological point is worth stating for the write-up: *a requirement can be correct, and
important, and still be untestable against the data the system normally produces.* Noticing that
before writing the test is the difference between a test that documents a decision and a test that
enforces it.

### An engine that cannot recognise the data it must refuse

`anom-002` requires the baseline to derive from normal-scenario data only — a baseline built over
injected data is an expectation that already contains the deviation it exists to measure. Writing it
exposed that the engine has no way to honour that requirement by itself.

An observation carries no scenario type. That is deliberate and load-bearing: `api-009` forbids
ground truth from leaving the run record, and `dal-001` gives the canonical model nowhere to put one
precisely so that no observation can leak the answer key. The consequence at this layer is that the
baseline engine, handed a set of observations, genuinely cannot tell a quiet reading from a staged
one.

Three options existed. The engine could query the run table itself, which would put persistence
inside a pure arithmetic component and break the seam that lets it be tested without Docker. It
could trust the caller, which makes the requirement a convention that no test can hold. Or the
caller could name the runs the baseline may draw from, and the engine refuse anything else.

The third was taken, and it converts the item's first failure case from prose into an enforced
precondition. The refusal is also all-or-nothing: a batch carrying one observation from an unlisted
run yields no table at all, rather than a table computed from the remainder. A baseline computed
from most of a batch is not a smaller correct answer; it is a wrong one that looks exactly like a
right one, and there is no later point at which the difference becomes visible.

This is a small instance of a pattern worth naming in the write-up: **a privacy or integrity
constraint enforced at one layer removes information that a later layer needed, and the cost is paid
as an explicit parameter rather than as a leak.** The parameter is the visible price of `api-009`.

### Ten mutations, and one that could not have been caught because it changes nothing

The frontend still measures no coverage and the backend measures a great deal, so `anom-002` was
checked both ways: 100% line coverage on the module, and an eleven-mutation pass to test whether the
tests were load-bearing rather than merely present.

Nine were caught on the first run. Two survived, and they were different in kind.

The first was a genuine gap. Deleting the guard that refuses an empty set of baseline runs left every
test green — because with observations supplied, an empty allowed-set means every observation belongs
to no listed run, so the *next* guard refuses the call and the test still sees its exception. The test
passed for the wrong reason. It was rewritten to call with no observations at all, where nothing but
the deleted guard can raise, and to assert on the message text rather than the exception type. A
second test now covers the path a caller would actually take.

The second survivor was not a gap at all. Replacing `statistics.mean(values)` with
`sum(values) / len(values)` changed no result, and the test asserting that traversal order is not an
input stayed green. The reason is a property of the interpreter rather than of the tests:
**CPython's built-in `sum` has used Neumaier compensated summation for floats since 3.12**, so it is
order-independent for realistic magnitudes. This was checked rather than assumed — a search over
300,000 randomly generated 30-sample sets of plausible dBm readings found no set whose float sum
differs when reversed, and `sum([0.1] * 10)` returns exactly `1.0` on the interpreters in use (3.14
locally, 3.13 in the container).

So it is an **equivalent mutant**: a change that cannot alter behaviour, and therefore cannot be
caught by any test. `statistics.mean` is kept anyway, because it is exact by specification rather
than by an implementation detail of one interpreter version, and because the order-independence of
a baseline is a reproducibility requirement (NFR-601) rather than a convenience.

Two of the twenty-seven tests were written *after* the implementation rather than before it, and
that is a deviation from the project's own workflow rather than a variation on it. Both came from
the coverage report: a guard refusing a non-positive window and the path where nothing at all is
supplied were each unreachable from the tests written first. They are legitimate behaviours and the
tests are sound, but the sequence is the wrong way round, and the honest observation is that the
coverage report found two gaps the test-first pass had missed — which is an argument for the gate
rather than against it. The same thing happened on `api-006`, where the batch launcher sat at 65%
while every other module was at 100%.

Recording the distinction matters for how mutation scores are reported. A raw score of 10 of 11
understates the result; the honest statement is ten of ten killable mutants caught, with one
equivalent mutant identified and explained. **A mutation score reported without separating
equivalent mutants is not a measurement of test quality**, and this is a concrete instance to cite.

### The most plausible wrong implementation of a threshold rule

`anom-001` compares an RF reading against the baseline for its cell and raises a finding when the
reading is far enough from normal. Written the obvious way — the absolute difference from the
baseline mean, past a configured threshold — the rule is wrong, and wrong in a way that would have
survived the entire evaluation campaign without ever looking wrong.

Raised power is the interference signature. But an absolute deviation also fires when a channel goes
*quieter* than its baseline, and a channel reporting well below its normal power is not interference
at all: it is most likely a receiver that has stopped hearing properly. Reporting it as
`rf_noise_deviation` would hand the AI layer evidence labelled as the opposite of what it is.

The reason it would have survived testing is the part worth recording. **Staged interference only
ever pushes the metric one way.** Every scenario type the generator can produce raises the noise
floor; none of them lowers it. So the absolute-deviation implementation and the correct one agree on
every run in the corpus, and would agree on every run of the scoring campaign. The defect is only
reachable by data the project does not generate — which is exactly the data a real deployment would
eventually see.

The rule therefore carries an explicit direction per metric: power is measured upwards, SNR
downwards. Those are the same physical event seen from two sides, since noise rising is what drives
signal-to-noise down, and a rule that did not know which way each metric moves would report an
*improving* signal as a deviation.

The general observation for the write-up: **a synthetic corpus tests the implementation against the
scenarios it was built to contain, and is silent about the ones it was not.** A test suite derived
entirely from generated data inherits that silence. Here the defect was caught by reasoning about
the rule before writing it; there is no guarantee the next one will be.

### Naming a finding so that a person can check it

`anom-001` is specified to carry "the observation IDs that triggered it", and the canonical
observation model has no id. That is deliberate: `dal-001` keeps storage identity off the model, so
nothing above the persistence layer learns what a database row is.

Three options. Add an id to the model, and lose the property `dal-001` exists to protect. Have the
detector query the store for ids, which puts persistence inside a pure function and breaks the seam
that lets detection be tested without Docker. Or identify a reading by its **natural key** — sensor,
channel, timestamp — which `scn-005`'s dense grid makes unique, because every sensor reports every
channel at every interval and those three values therefore name exactly one reading.

The third was taken, and the argument that decided it is not really about layering. This phase exists
to make findings *checkable*. `RF-03, channel 4, at 12:07:30` is a reference an analyst can carry
back to the data and verify; `observation 84412` is a reference only the database can resolve. When
the evidence bundle reaches a human reviewer — or an examiner — the natural key is the form that
still means something. `evb-002` can resolve it against the store as readily as a surrogate id, so
nothing downstream is given up.

This is a small case of a recurring tension in the project: **the identifier that is most convenient
for the machine and the identifier that is most useful for the explanation are not the same one**,
and an explainability system should prefer the second wherever it can afford to.

### A detector that skips what it cannot measure makes its own control meaningless

`anom-002` can return an insufficient-data result for a cell, and a cell may be missing from the
baseline table entirely. `anom-001` has to do something with those, and the obvious thing — carry on
past them — is quietly disastrous.

`anom-008` requires a `normal-baseline` run to raise zero anomalies, and the false-positive rate
reported in the evaluation is computed from exactly that. If the detector silently passes over cells
it cannot assess, then "zero anomalies" becomes satisfiable by *not having looked*, and the
distinction between a clean run and an unexamined one disappears at the point where it matters most.
A detector with no usable baseline anywhere would post a perfect false-positive rate.

So an unjudged cell is a reported outcome with a reason attached, and the rule returns findings in
two parts: what it concluded, and what it could not conclude. The second part is not an error
channel. It is a result.

The general form is worth stating because it recurs wherever a negative result is being measured:
**a correct non-detection and an absent detection are different claims, and any system reporting the
first has to be able to prove it is not reporting the second.**

### A determinism test with one cell cannot catch an ordering bug across cells

Fifteen mutations were applied to `anom-001`; fourteen were caught on the first run. The survivor
replaced the sorted iteration over cells with iteration in arrival order, which makes the sequence of
emitted anomalies depend on the order the readings happened to arrive in.

The test that should have caught it was the one asserting that traversal order is not an input — and
it did not, because it was written with a single cell. With one cell there is no cell ordering to get
wrong, so the assertion was true for both implementations. The fix was to give the test two cells and
assert the emitted order explicitly.

This is the third instance in this project of the same defect shape, and by now it is worth stating
as a rule rather than as an anecdote: **a test that distinguishes two behaviours must contain the
structure along which they differ.** Values common to both cannot separate them (`api-010`); a single
sample cannot exercise an ordering (`anom-001`); a uniform data set cannot demonstrate a requirement
about non-uniformity (`anom-002`). All three passed for the right reason on the wrong structure.

### The staged track signature sits inside the corpus's own background, and no threshold separates them

Measured 2026-09-14, against the 120 runs in the development database, before writing a line of
`anom-010`. The item was specced that morning from reasoning about the corpus; measuring it first
corrected the reasoning by roughly two orders of magnitude.

**What the rule was expected to face.** The coverage acceptance check of 2026-08-19 found 10 of 948
tracks (1.05%) carrying a genuine interior airborne dropout, seven of them in the 100–300 s band the
coverage-gap scenario injects into. `anom-010` was written on the assumption that those ten tracks
were the whole of the false-positive problem, and that excluding them would let `anom-008`'s
zero-anomalies control hold.

**What it actually faces.** Position staleness is reported by the corpus, not inferred, and the
background rate is far higher than ten tracks:

| Per run, averaged over 20 runs of each type | `normal-baseline` | `gnss-degradation` |
|---|---|---|
| Aircraft seen | 530.2 | 535.8 |
| Peak position staleness > 100 s | **137.7** | 141.1 |
| > 300 s | 19.3 | 20.7 |
| > 600 s | **1.0** | 0.6 |
| > 900 s | **0.5** | 0.2 |
| Fresh contact *and* position > 100 s | 24.6 | 28.0 |
| Both clocks stale > 100 s | 126.6 | 127.3 |

**There is no threshold that separates the two.** At 100 s the staged runs exceed the quiet ones by
3.4 aircraft against a background of 137.7 — a ratio of about 1:40. At 600 s and above the quiet runs
are *higher* than the staged ones. The two-clock discriminator, which exists precisely to tell a
frozen position from an unheard aircraft, narrows the background from 137.7 to 24.6 and still leaves
the staged signature at 3.4 aircraft inside it.

The cause is structural rather than a tuning error. The generator stages GNSS degradation by adding
elapsed time to the reported position-staleness field, and the incident affects a handful of aircraft
inside a roughly 20 km zone — 0 to 11 per run. The corpus background, meanwhile, occupies exactly the
same range, because the 100–300 s band the injection was designed to sit in is also where real
receiver coverage fails. **The injected signature was designed into the busiest part of the
distribution it has to be distinguished from.**

**What this does not mean.** It is not evidence that the scenario type is undetectable. A per-aircraft
threshold is the wrong instrument for it, and the architecture already says so: `anom-004` clusters
discontinuities spatially, and `anom-005` requires co-located RF noise in the same window. The
background gaps are scattered across 309,000 km²; the staged ones are concentrated in a 20 km zone
with a raised noise floor over it. The discriminating information is *spatial and cross-modal*, and a
rule looking at one aircraft's clock at a time cannot see it.

**What it does mean** is that `anom-010`'s output cannot be a reportable anomaly in the sense
`anom-008` uses the word. A run with nothing staged in it will contain of the order of 138 track
discontinuities that are real properties of real data, and a control requiring zero of them is a
control requiring the detector to be wrong.

### A measured validation of the exclusion list, from a different code path

The same measurement produced an unexpected check on `adp-008`. Taking the quiet runs' stored
observations and looking for intervals between consecutive reports of one aircraft — a different
quantity from reported staleness, and a different code path from the corpus tooling that built the
exclusion list:

| Filter applied | Gaps remaining |
|---|---|
| Interval > 100 s | 164 |
| …and airborne at both ends | 32 |
| …and both ends interior to the bounding box by 0.25° | **23** |
| …and not on the `adp-008` exclusion list | **0** |

The 23 survivors belong to **4 distinct aircraft, and all four are on the list**, with none unlisted.
`adp-008` was built at corpus-build time from raw archive rows with pandas; this check ran against
pseudonymised observations in PostGIS after a full replay and perturbation pass. **Two independent
routes to the same set of tracks** is stronger evidence for that artefact than its own unit tests
provide, and it is worth citing as such.

It also confirms, with a number, the gap recorded on `anom-010` the same morning from reasoning
alone: the exclusion list exists and is correct, and **it is not being applied to baseline windows**.
23 avoidable gaps across 20 quiet runs are sitting in the database now.

The two filters matter in their own right as well. Of the 164 raw gaps, 132 are explained by the
aircraft being on the ground or crossing the bounding-box boundary — artefacts of having drawn a box
and of aircraft being switched off, exactly the two corrections the bounding-box sweep needed in
August. **A detector that omitted them would report four-fifths false positives**, and would look
like a detector problem rather than a framing one.

### Seventeen mutations, and what the four survivors were each a different kind of

`anom-010` was checked with a seventeen-mutation pass on top of 100% line coverage. Thirteen died on
the first run. The four that lived were four distinct things, and separating them is more useful than
the score.

**Two were boundary cases I had already written once and did not carry across.** Both thresholds
compared with a strict inequality, and no test placed a value exactly on the boundary — 99 s and
150 s bracket it without touching it. `anom-001` has precisely this test, written the day before,
because that item's own failure case names the boundary explicitly. `anom-010`'s did not, so it was
not written. **A test that exists in one rule does not propagate to the next by being a good idea**;
it propagates by being in the spec item, which is an argument for the failure cases in `spec.jsonl`
being specific rather than general.

**One was a test passing for the wrong reason, and the second instance of one exact shape.** Deleting
the guard that refuses a non-positive threshold left every test green, because the policy's *other*
guard — that the contact window must be shorter than the threshold — then raises instead: any
positive contact window is longer than a zero threshold. The test saw its exception and passed. This
is the same defect as the baseline engine's empty-run-set test, two items earlier, and the same fix:
assert on the message, not the type. The general form is worth stating, because it will recur:
**a guard that can only be reached through the guard beside it is not under test**, and validation
guards cluster, so they are where this happens.

**One was not a defect in the tests at all: I built the mutation wrongly.** Intending to test that no
trailing gap is extrapolated past an aircraft's last report, I mutated the pairwise iteration to
`zip(reports, reports[1:] or reports)`. That differs from the original only when an aircraft has a
single report, where it pairs the report with itself and yields a zero-length interval — no gap
either way. It was an equivalent mutant, and reported as a survivor. Rebuilt as a mutation that
genuinely appends a trailing finding, it killed 23 of 28 tests immediately.

The lesson generalises past this item. **Mutation testing has its own failure mode: a mutation that
does not change behaviour reports as a surviving mutant and looks exactly like a gap in the tests.**
Both of this project's equivalent mutants so far were mine rather than inherent — one relied on
CPython's compensated summation, one on a short-circuit that could not fire — and both would have
been recorded as test weaknesses if they had not been read carefully. A mutation score is only as
good as the mutations, and the mutations need reviewing with the same suspicion as the tests.

### A second canonical shape, and a prediction worth scoring

`dal-001` established the project's central structural claim: every adapter's output becomes one
canonical observation, so a new source changes the adapter and nothing else. That is the evidence for
RQ1, and it has been scored once — the second adapter landed with the canonical model untouched.

`db-008` is the same argument at a second seam, and it was not planned as one. It arose because
`db-004` was picked up and found to have nothing to query: the `anomalies` table had existed since
the first migration, nothing had ever written to it or read it, and no spec item covered doing so.
Building the storage for detection findings raised the same question the DAL had answered — an RF
episode carries a sensor-channel cell, a severity and a peak deviation; a track discontinuity carries
an aircraft and one of two shapes — and the same answer was taken: one shape every rule becomes, with
whatever is rule-specific carried in a `details` payload.

**The prediction is explicit and falsifiable: `anom-003` should require no change to
`app/db/findings.py` at all.** It is recorded here before that item is written so that scoring it
later means something. A test names the nine top-level fields explicitly, so a rule-specific column
added at the top level fails rather than quietly reintroducing a branch per rule.

A second decision on that item is worth recording because it cuts against a rule established
elsewhere in the project. `db-007` made the case that nothing is ever deleted: a run is a fact about
what happened, and an absent completion stamp is informative. Detection findings are not like that.
They are derived, regenerable from the run's seed, and re-derived whenever a rule changes — so the
write replaces rather than appends, per run per rule, including when the new set is empty. Appending
would be the worse failure by a distance: after a rule changed, the old findings would sit beside the
new and every metric in the evaluation would count both, with nothing on screen or in a log to say
so. **The never-delete rule is about facts, not about derivations**, and stating the boundary is more
useful than stating the rule.

### The same helper twice, and the reason it could not be shared

`app/db/repository.py` builds a PostGIS point with GeoAlchemy2's `WKTElement`. The obvious move when
writing the findings module was to reuse it. It does not work, and the reason is a seam rather than
an oversight: the repository builds its statements from a reflected table whose column carries the
geometry *type*, and it is that type which adapts the element for the driver. The findings module's
statements are textual, so the driver sees a bare Python object and refuses it —
`cannot adapt type 'WKTElement'`.

The fix was to pass EWKT as text and let `ST_GeomFromEWKT` parse it, which is better than the thing
it replaced: the SRID travels attached to the value rather than being assumed by the column. But the
finding worth keeping is about duplication policy. This project has a recorded scar from the opposite
mistake — a remedy that existed in two places, and a third caller that did not know about it — and
the instinct after that is to extract every shared-looking helper. **Two functions that look
identical are not duplication when the machinery around them differs**; here one takes coordinates
loose and produces a typed element for a reflected column, the other takes a model and produces text
for a textual statement. Merging them would have coupled two layers to make one line shorter.

### A scripted multi-file edit that failed halfway, twice, and a partial fix built on a guess

Recorded because it is a working-practice failure rather than a design one, and because it happened
twice in two days in an identical shape.

Documentation for these items is applied by a short script that makes several exact-string
replacements across `CLAUDE.md`, `docs/implementation.md` and `docs/thesis_notes.md`, each guarded by
an assertion that the target text occurs exactly once. When a later assertion fails, the earlier
files have already been written and the process exits non-zero — but the commit command that follows
it in the same shell invocation still runs. The result is a commit whose message describes three
files and whose content is one.

It happened first on `anom-001` and was noticed. It happened again on `anom-010`, and the second time
the repair was worse than the fault: seeing the traceback point at a line number, I inferred which
edit had failed, fixed that one, and did not check the others. The inference was wrong. The
checklist was repaired and the repository map silently kept a stale entry for a day, describing a
detection package that had gained a module it did not mention.

Two things generalise. **A partial application is worse than a failure**, because the failure is
visible and the partial state is not — and a commit message asserting what a script intended is
evidence of intent rather than of content. And **a diagnosis inferred from an error's line number is
a hypothesis, not an observation**; the file was one `grep` away throughout. The corrected practice
is to apply every edit, verify each independently against the file, and only then commit — which is
the same discipline the project already applies to tests, arriving a layer up.

### An edge case asserted from documentation, and what the database actually did

`db-004` is the one real PostGIS spatial query FR-905 asks for, and the item was amended before its
tests were written to fix both ends of its boundary. The original failure case said a discontinuity
just *outside* N km must be excluded; the amendment added that a finding *exactly* N km away is
inside, on the grounds that `ST_DWithin` is inclusive. That is what the documentation says, and it is
what the test asserted.

It is not what PostGIS 3.5 does. Measured directly:

```
ST_Distance(a::geography, b::geography)  =  34338.94037894 m
ST_DWithin(a::geography, b::geography, 34338.94037894)  =  false
```

The round trip through kilometres introduces no drift at all — the value comes back bit-identical —
so this is not floating-point error in the caller. **The operator itself excludes the boundary on
geography**, where the distance is computed on a spheroid and the containment test is a separate code
path from the measurement.

The correction was not to force inclusivity. Comparing `ST_Distance <= radius` instead would have
given the documented behaviour and lost the index assist, trading a real property for an edge case no
measured distance occupies. What the item now specifies is that a finding **one metre inside** the
radius is returned and one metre outside is not, which brackets the edge to metre precision and
leaves exact equality where it belongs — undefined, and PostGIS's business.

The methodological point is the one this phase keeps producing, now in a fourth form. The per-channel
baseline claim could not be proved against the project's own quiet data; the track signature could not
be separated from the corpus background; two mutations that looked like test gaps were artefacts of
how I built them; and here an edge case was specified from a manual rather than from the system.
**Every one was found by measuring the thing rather than reasoning about it, and in each case the
reasoning had been confident and wrong.** For a dissertation that argues for explainable, checkable
detection, that is not an embarrassing pattern to record — it is the argument.

### The index the query could not have used, and the prefilter that fixes it

`db-001` created a GiST index on a geometry column with a comment naming `db-004` as its reason, and
`db-008` carried that index to the table the findings actually live in. Neither would have helped.

Distance has to be measured on geography, because the stored geometry is in degrees and a degree is
not a distance — at 52 degrees north a degree of longitude is about 69 km and a degree of latitude
about 111, so a radius applied to raw coordinates is wrong by a different factor in each direction.
But casting the column to geography in the predicate is a function call on the column, and a plain
GiST index on the geometry cannot answer it. The query would have been correct and would have
scanned the table, which is precisely the failure `db-001`'s own comment predicted: *it fails as a
performance claim rather than a correctness one, which is the kind of defect that survives every
functional test.*

The fix is the standard PostGIS idiom and worth stating because it is not obvious: a bounding-box
prefilter with `&&`, which the geometry index answers, followed by the exact `ST_DWithin` on
geography over the survivors. The expansion is deliberately generous — computed from the shortest
degree of longitude anywhere in the corpus box, so it over-covers at every lower latitude — because
an over-wide prefilter costs a few extra exact comparisons and an under-wide one silently loses rows.

What made this visible was writing a test that asserts the *plan* rather than the answer: sequential
scans disabled, `EXPLAIN` inspected for an index scan naming the location column. That is an unusual
test to write and it is the only kind that could have caught this, because every assertion about
returned rows passes either way. **A performance guarantee needs a test that can see the plan**, and
this project now has one.

### A constraint that named a function the database does not have

The clustering item, `db-009`, was written the same day it was built, and it specified that grouping
be "performed by PostGIS on geography rather than by application-side arithmetic" while also naming
`ST_ClusterWithin` as the function to do it with. Both halves were written in the same sentence and
they contradict each other. `ST_ClusterWithin` has no geography overload: PostGIS 3.5 exposes exactly
two signatures, `(geometry[], double precision)` and `(geometry, double precision)`, and the distance
argument is interpreted in the units of the geometry's own spatial reference system — degrees, for
the WGS 84 this project stores everything in. The constraint as written could not be satisfied by the
function it was written about.

This is the second time in two days that an item asserted something about PostGIS that PostGIS did
not do: `db-004` claimed `ST_DWithin` was inclusive at its boundary, from the documentation, and
measurement showed it was not. The pattern is specific enough to name. Claims about *this system's
own code* have been reliable, because they were derived from reading it. Claims about the
*dependency's* behaviour have been wrong roughly as often as they have been right, because they were
derived from recalling documentation. The methodological correction is not "be more careful" but
"query the catalogue" — a single `SELECT proname, pg_get_function_arguments(oid) FROM pg_proc`
settled in one second a question that had been written into a specification as a constraint.

The resolution keeps the substance and changes the mechanism. The findings are projected to EPSG:3035
— ETRS89-extended Lambert Azimuthal Equal-Area Europe, a metre-based projection covering the whole
corpus box — clustered there, and the radius therefore means metres. The approximation this accepts
was measured rather than assumed. At the corners and centre of the corpus bounding box, a 5 km
separation in EPSG:3035 differs from the geodesic distance computed on geography by at most 2.57 m,
which is 0.055 per cent, worst at 54°N 3°E:

| Position | Geodesic | EPSG:3035 | Error |
|---|---|---|---|
| 49°N 3°E | 5224.47 m | 5222.50 m | −1.96 m |
| 52°N 5°E | 4903.61 m | 4901.84 m | −1.77 m |
| 54°N 3°E | 4682.11 m | 4679.54 m | −2.57 m |
| 54°N 11°E | 4682.11 m | 4682.92 m | +0.81 m |

What makes this defensible rather than convenient is the comparison with what the constraint was
written to forbid. A radius applied to raw degrees is wrong by about 62 per cent between the two axes
at 52°N, because a degree of longitude there is roughly 69 km and a degree of latitude roughly 111.
Three orders of magnitude separate the approximation accepted from the one refused, and the spec item
records both numbers so the judgement can be checked rather than taken on trust.

The alternative that would have satisfied the constraint literally — a recursive transitive closure
over `ST_DWithin` on geography — was considered and rejected. It is exact, and it buys 2.57 m of
accuracy on a radius that nothing in the project has a basis for choosing to within a kilometre, at
the cost of the one property `ST_ClusterWithin` was selected for: being explainable to an analyst in
a single sentence. Paying a large explainability cost for an accuracy gain three orders of magnitude
below the uncertainty in the parameter itself would be the wrong trade for a system whose thesis is
explainability.

### Determinism that held everywhere except the fifteenth decimal place

`NFR-601` requires a run to be reproducible from its seed, and `db-009` restates it as a constraint:
the same findings and radius must always give the same groups, in the same order. The test written
for it stores three findings, reads the clusters, stores the same three in reverse order, reads
again, and asserts the two results are equal. Membership was identical. Ordering was identical. The
objects were not equal.

The difference was in the centroid, at the fifteenth significant figure:

```
forward   POINT(5.060000171976006 52.00001017169536)
reverse   POINT(5.060000171975998 52.00001017169536)
```

Eight parts in 10^15 of a degree — roughly 0.9 nanometres on the ground. The cause is that
`ST_Centroid` sums coordinates in whatever order `ST_Collect` assembled them, floating-point addition
is not associative, and an unordered window partition takes its order from however the rows came back
off the heap. Re-inserting the same rows changed that order, and so changed the last bit of the sum.

The interesting question is what to do about a defect that is physically meaningless. Loosening the
assertion to a tolerance was the obvious move and the wrong one: the requirement is not that the
centroid be accurate to a nanometre, it is that a run *reproduce*, and a result that varies with
storage layout does not reproduce however small the variation. Rounding the output would have hidden
the cause behind a number chosen to make a test pass. The fix taken instead makes the summation order
a property of the query — an explicit window frame, `ORDER BY started_at, subject, id ROWS BETWEEN
UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING`, over the same content-derived key the final `ORDER BY`
already uses. The frame has to be spelled out because a window `ORDER BY` alone defaults to a running
aggregate, which would give every row the centroid of its own prefix rather than of its group.

Two things are worth carrying into the write-up. The first is that this is the same principle the
item already applied one level up, arriving from a different direction: the groups are ordered by
their content rather than by the cluster identifiers PostGIS hands out, because those are numbered in
an internal order over rows that have none imposed. Determinism at this seam is not one decision but
a rule — nothing in the output may depend on the order rows arrive in — and the centroid was the
place the rule had been applied incompletely. The second is that the test is a genuine detector
rather than a lucky one: reverting the frame and running the single test three times caught it three
times out of three, and the fixed version passed three out of three.

### The two spaces a clustering query works in, and why the answer is both

`db-009` computes its centroid in metres and its covering geometry in degrees, which looks like an
inconsistency and is the same rule applied twice: each value is computed in the space where that
value is right.

A centroid taken on raw coordinates is the arithmetic mean of longitudes and latitudes, and that
underweights longitude wherever a degree of it is shorter than a degree of latitude. For four
findings spread across about 25 km at 52°N, the mean of the coordinates is `POINT(5.1175 52.0125)`
and the true areal centre is `POINT(5.117447601845757 52.012561112115044)` — 7.69 m apart. That is
small enough to ignore and free to get right, and it is the point an analyst would be shown as the
centre of a disruption, so it is computed in the equal-area projection and transformed back.

The covering geometry goes the other way, for a reason that only appeared on measuring the round
trip. A convex hull's vertices are findings that are already stored exactly, and projecting to
EPSG:3035 and back does not return them unchanged: longitude 5.0 comes back as 4.999999999999997 and
latitude 52.0 as 52.000000000000014. Sending the shape through the projection would introduce drift
into coordinates that arrived exact, in exchange for nothing — the hull is an enclosure of points,
not a measurement of distance, so there is no accuracy to gain. (`db-004` measured the opposite
result for its own round trip through kilometres and metres, which came back bit-identical; the
difference is that a unit conversion is a multiplication and a reprojection is a trigonometric
transform.)

The same query therefore holds a single rule in two places, and the rule generalises past this item:
project when the number you want is a distance, and leave the data alone when the number you want is
a coordinate you already had.

### A group of one, and the temptation to call it noise

The covering geometry of a cluster is a convex hull, which means a group of one member is a `POINT`
and a group of two is a `LINESTRING`. Only three non-collinear members produce a `POLYGON`. Since the
`anomalies` table requires a `Polygon` for its affected area, there is an obvious pressure to make
`db-009` always return one — by buffering the hull, or by returning a bounding box with some minimum
size.

Both were rejected, and the reason is the same one that runs through the whole detection layer. A
group of one was observed at a single point and has no measured extent; a buffer radius chosen to
make it into a polygon would be a number with no evidence behind it, presented to an analyst as the
area a disruption covered. The system's claim to explainability rests on every displayed quantity
tracing back to something measured, and an invented area is exactly the kind of quantity that
survives into a screenshot and then into a conclusion. Promoting a cluster to a reportable anomaly is
`anom-004`'s decision, and if it needs a polygon it must choose and justify the buffer itself, in the
item where that choice is visible.

The related temptation is to drop singletons altogether, on the grounds that a lone finding among 138
background discontinuities is noise. That would delete the signal `anom-006` exists to read: a source
that goes quiet *by itself*, with no neighbours and no radio explanation, is evidence of an
infrastructure problem rather than of an incident. The isolated case is not the residue left after
clustering; it is one of the two answers clustering is asked for.

### The measurement clustering was supposed to settle, and the answer it gave

When `anom-010` was rescoped from a reportable anomaly to an intermediate finding, one risk was
recorded and deliberately not pre-solved: a quiet run contains a large background of genuine track
discontinuities, and whether any of them fall close enough together to cluster into something a
reportable rule would fire on was declared measurable once `db-009` and `anom-004` existed. With
`db-009` built, the measurement could be taken before `anom-004` was written. It was, and it
falsifies the premise the item was written on.

**The control had to be chosen before anything could be measured.** The obvious control is a
`normal-baseline` run, and it is the wrong one here: in the batch of 120 runs stored, no
`normal-baseline` run shares a seed with any staged run, so it replays a different stretch of the
corpus entirely. Comparing against it would confound the injection with the traffic. The batch does
contain a better control, free: `rf-sensor-fault` shares seeds with the staged types, and only
`aircraft-coverage-gap`, `gnss-degradation` and `ambiguous-mixed-evidence` perturb tracks at all. An
`rf-sensor-fault` run is therefore the same corpus window, the same aircraft, and nothing staged on
the track side — its track findings *are* that window's background. Its ground truth confirms it:
zero aircraft staged, against 2 to 11 in each matched staged run.

**Clustering does not separate staged runs from their matched controls.** Over eight seed-matched
triples, comparing the largest group each run produces:

| Radius | `gnss-degradation` − control | `aircraft-coverage-gap` − control |
|---|---|---|
| 5 km | +0.00 (0 of 8 triples differ) | −0.38 (0 of 8) |
| 10 km | +0.00 (0 of 8) | −0.38 (0 of 8) |
| 20 km | +0.00 (0 of 8) | −0.38 (0 of 8) |
| 30 km | +0.12 (1 of 8) | −0.38 (0 of 8) |
| 45 km | +0.25 (2 of 8) | −0.38 (0 of 8) |
| 60 km | +0.25 (2 of 8) | −1.00 (0 of 8) |

At every radius up to 20 km the largest cluster in a staged run is *identical* to the largest cluster
in its own control, in all eight triples. The coverage-gap runs are consistently worse than their
controls, which is the more interesting half and is addressed below. Total findings per run tell the
same story: 15.9 on staged runs against 16.0 on controls — staging changes the count by nothing.

**A cluster threshold would fire on every clean run.** The control runs carry a mean largest group of
3.75 and between 1.0 and 1.9 groups of three or more members, depending on radius. Any rule of the
form "a cluster of N track gaps is reportable" therefore fires on every quiet run in the batch for
any N a staged run could also reach. This is the quantitative form of the risk `anom-008` was
amended to describe, and it is now a number rather than a worry.

### Twenty-one per cent, and what it is not caused by

The clustering result has an upstream cause, found by scoring `TRACK-GAP` against the answer key
rather than against a control. Across the matched runs, **119 aircraft were actually staged on and 25
produced a finding: 21 per cent recall** — 19 per cent for `aircraft-coverage-gap`, 25 per cent for
`gnss-degradation`. The shapes are correctly assigned in every case, `frozen_position` for the
degradation runs and `not_heard` for the coverage gaps, so the two-mechanism design is wired
correctly. It is a sensitivity result, not a wiring one.

The immediate suspicion was that this measured the policy parameters rather than the system, since
the staleness threshold and the contact-freshness window were both chosen for the measurement rather
than derived. Sweeping them says otherwise:

| Threshold | Contact freshness | Coverage-gap recall | Degradation recall |
|---|---|---|---|
| 60 s | 10 s / 30 s / disabled | 19% | 26% |
| 100 s | 10 s / 30 s / 60 s / 90 s / disabled | 19% | 23% |
| 150 s | 10 s / 30 s / 60 s / 90 s / disabled | 12% | 23% |
| 200 s | 10 s / 30 s / 60 s / 90 s / disabled | 12% | 23% |

Recall is flat across a threefold range of threshold and the entire range of the freshness
discriminator including switching it off. It is not a tuning artefact. **Why** it is 21 per cent is
not established by this measurement and is deliberately not guessed at here; the injection is a 300 s
disruption beginning 120 s into the window, which is comfortably above any threshold tried, so the
loss is somewhere between the perturber deciding which records to touch and the detector's airborne
and interior-to-box filters. That is `anom-010`'s question, and it is now an owed piece of work with
a number attached.

**Why the coverage-gap runs come out below their own controls** is worth stating, because it looks
like an error and is a consequence of a deliberate decision. That scenario stages by *suppressing*
rows. `anom-010` detects an absence by looking at consecutive surviving reports, and refuses to
extrapolate a gap from a track's final report, since every aircraft still in flight is stale when the
window closes. Suppressing a run of rows can therefore remove the very reports that would have
bracketed a *natural* gap, so the injection destroys evidence as well as creating it. The refusal to
extrapolate is right and should stay; the interaction was not anticipated.

### What this does to `anom-004`, and why the item is rescoped rather than abandoned

The item was written on the assumption that clustering discriminates — that grouping discontinuities
by place is what turns a scatter of background events into something worth reporting. Measured, it
does not, for the input it actually has. Three responses were available.

Tuning the radius until the two separate was rejected outright. The measurement covers 5 to 60 km and
the separation is zero to 0.25 clusters across all of it; a radius that appeared to work would be
fitted to eight triples of one batch, and the project has already recorded what it thinks of numbers
chosen to make a control go green.

Abandoning the item was rejected because the capability is still needed. `anom-005` fuses an RF
deviation with *clustered* track gaps, and `anom-006` reads clusters to decide that a dropout
happened with no radio explanation. Both need grouping to exist whatever its discriminating power in
isolation.

What remains is the same move `anom-010` made when its own premise failed, and for the same reason:
the output is scoped to an **intermediate finding**, and the discrimination is left to the rules that
add the other half of the picture. The finding that forces it is stronger than a design preference —
clustering track gaps alone provably cannot tell a staged run from its own matched control, so a rule
that reported on cluster size would be reporting noise. Recording that the discriminating information
is cross-modal rather than spatial-alone is a result of this project, not a limitation of it: it is
the same conclusion `anom-010` reached from the time axis, now reached independently from the space
axis.

*(Threat to validity, to be carried into the evaluation chapter: every number above comes from one
batch of 120 runs generated from one base seed, and the eight matched triples share the corpus hour.
The recall figure in particular should be re-measured against a second batch before it is reported as
a property of the detector rather than of this batch.)*

### Where the intermediate findings actually leak, and where they cannot

Two intermediate producers now exist, `anom-010`'s discontinuities and `anom-004`'s clusters, with no
reportable rule yet built on either. The question this raises is whether a layer with poor
discrimination, declared intermediate, can still damage the results that matter — the anomalies an
analyst sees and the hypotheses generated from them. The answer differs for the two, and only one of
them is safe by construction.

**The hypothesis layer is structurally insulated, and not by accident.** `evb-001` takes *anomalies*
as its input and states that the bundle is the only thing the AI layer ever receives; `api-009` keeps
ground truth out of it. An intermediate finding has no path to a model: it is not an anomaly, so it
cannot enter a bundle, so it cannot reach a prompt. That boundary was drawn for a different reason —
keeping raw observations away from a hosted provider — and it happens to contain this problem too.

**Attribution is not insulated, and the exposure is measurable.** The unsafe path is indirect. If a
fused rule is misled by background clusters it raises a *real* anomaly; that anomaly builds a bundle
whose evidence genuinely exists; the grounding check in `ai-008` passes, because every claim does
trace to the evidence supplied; and the model produces a confident, well-grounded, wrong explanation.
A grounding check cannot catch a correctly-grounded wrong premise, and this is the shape of failure
it is blind to.

The measurement that matters is not the clean run. On a `normal-baseline` run `RF-NOISE` is silent,
so nothing fuses and `anom-008`'s control passes regardless. The dangerous case is a run whose truth
is `rf-sensor-fault`: the radio side fires legitimately and correctly, and the only question is
whether any background track cluster happens to lie within the fusion radius. Across all twenty
sensor-fault runs, clustering at 20 km and measuring distance with `db-004`:

| Fusion radius | Runs with a background cluster in range | Runs with one of three or more members |
|---|---|---|
| 55.7 km | 12 of 20 (60%) | 4 of 20 |
| 60 km | 14 of 20 (70%) | 5 of 20 |
| 70 km | 14 of 20 (70%) | 5 of 20 |
| 85.7 km | 15 of 20 (75%) | 6 of 20 |

`anom-005` as specified — an RF noise anomaly and a co-located track-gap cluster in the same window —
would therefore report `possible_interference_zone` on about seventy per cent of the runs whose
correct answer is `possible_sensor_fault`. `anom-006` compounds it: it is defined to be mutually
exclusive with `anom-005` for the same cluster, so the false fusion does not merely add a wrong
anomaly, it removes the run from the rule that would have got it right.

**A minimum cluster size helps and cannot be used.** Requiring three or more members cuts the
exposure from 70 per cent to 25 per cent at a 60 km radius, which looks like the obvious fix until it
is checked against the true positives. With `TRACK-GAP` recall at 21 per cent, a staged run with
between two and eleven affected aircraft typically yields one to three findings in total, and only
one of the measured runs produced three detections on staged aircraft. The threshold that suppresses
the background suppresses the signal at the same time, because they are the same size. There is no
value of the parameter that separates them.

That is the finding, and it is a single number rather than three problems: **the background is not too
large, the recall is too small.** Clustering is not at fault and neither is fusion; both are
downstream of a detector that sees one staged aircraft in five. Until that changes, no arrangement of
radii or cluster sizes in the rules above it can produce a discriminating result, and building those
rules first would produce three items that pass their unit tests on constructed fixtures and fail
together at evaluation time, with the cause two layers below where the failure appeared.

*(Threat to validity for the evaluation chapter: this exposure is measured on one batch, at one
clustering radius, with one staleness policy. The direction of the result is robust — it is driven by
the ratio of signal to background, which the parameter sweep showed to be stable — but the specific
percentages are not yet a property of the system.)*

### Scoring a prediction that was recorded before it could be checked

`db-008` made a claim in writing and staked the RQ1 extensibility argument on it at a second seam:
one canonical shape that every detection rule becomes, so that adding a rule needs no change to the
storage layer at all. The prediction recorded alongside it was that `anom-003`, the z-score detector,
should require no edit to `app/db/findings.py`. `anom-004` arrived first and turned out to be a
harder test than the one the prediction named, because a cluster is structurally unlike the two rules
the shape was derived from: an RF episode is about one sensor-channel cell and a track gap about one
aircraft, while a cluster is about several aircraft at once.

**The storage half of the prediction holds cleanly.** `app/db/findings.py` was not touched — verified
against the commit rather than asserted — and the new rule's findings write and read back through the
same two functions, with a test that stores a cluster and reads it out again.

**One field's meaning had to widen, and that is recorded as a partial rather than a clean score.**
`subject` was documented as "the thing observed", and a cluster has no single one; it now carries the
members joined. Nothing broke — the column is unbounded text, and the migration's own comment had
already anticipated that "a third detector's subject is neither of those" — but the honest reading is
that the shape absorbed a case it was not designed for by stretching a field rather than by fitting
it. Both halves are worth reporting: a claim scored only where it succeeds is not evidence.

`anom-003` remains the prediction's fair test, since a z-score finding is about one cell again, and
it should now be scored against a shape that has already been stretched once.

### An equivalent mutant that the query's own contract creates

The mutation pass over `anom-004` killed eleven of twelve. The survivor was replacing
`min(member.started_at for member in cluster.members)` with `cluster.members[0].started_at`, and it
survives because it is equivalent: `db-009` returns members ordered by start time, then subject, then
row, so the first member's start time *is* the minimum, always. No test can separate the two without
constructing an input the query's ordering forbids.

What makes it worth recording rather than dismissing is that its twin died. The identical mutation on
`ended_at` — taking the first member's end time instead of the maximum — was caught immediately,
because members are not ordered by when they finish. The pair is a precise illustration of the
difference between a weak assertion and an equivalent mutation, sitting two lines apart in the same
expression, and it is the sort of case that makes an unexamined mutation score misleading in both
directions.

The defensive form was kept in the code. `min()` does not depend on `db-009`'s ordering contract
holding, and a later change to that ordering — which is a property of a different module, tested
elsewhere — would silently break the indexed form while leaving every test in this file green.

### Twenty-one per cent was the right number attached to the wrong cause

`anom-011` was written to explain a recall figure, and the explanation reverses the conclusion the
figure had been used to support. Recorded here in full, because the reversal is more useful than
either endpoint.

The position at the end of `anom-004` was that clustering cannot discriminate because `TRACK-GAP`
recall is 21 per cent, and that the detector was therefore too insensitive for any rule above it to
work. The first half stands. The second was wrong, and wrong in the specific way this item exists to
prevent: a cause had been *named* — detector sensitivity — rather than counted.

Counting it gives an answer that is almost entirely one thing. Across 77 staged runs of the three
track-perturbing types, the loss breakdown for 286 undetected staged aircraft is:

| Where the aircraft went | Count | Share |
|---|---|---|
| On the ground | 258 | 90% |
| Gap under the threshold | 26 | 9% |
| Position stale but contact not fresh | 2 | 1% |
| Never appeared in the run | 0 | — |
| No report to bracket the absence | 0 | — |
| Near the edge of the box | 0 | — |

Ninety per cent in one bucket was suspicious rather than conclusive, because `ON_GROUND` outranks
`BELOW_THRESHOLD` in the precedence the harness uses and a single grounded report anywhere in a track
would claim the attribution. Checking it directly: of the undetected staged aircraft, **92 per cent
are on the ground in every single one of their reports**, with a median of 86 reports each. Not
aircraft that took off or landed during the window — aircraft parked for its entirety.

The cause is in the generator, not the detector. The zone test asks whether a reported position falls
within the staged radius and asks nothing else, so an aircraft parked at an airfield inside the zone
is targeted exactly like one flying through it. `anom-010` then refuses it, correctly: an aircraft on
the ground stopped reporting because it was switched off, and its stale position is indistinguishable
from that. Both components are behaving as specified and the combination produces a guaranteed false
negative.

Restricting the measurement to staged aircraft that were airborne at any point in the run:

| Scenario type | Recall, all staged | Recall, airborne staged |
|---|---|---|
| `gnss-degradation` | 37% | **74%** |
| `ambiguous-mixed-evidence` | 18% | 53% |
| `aircraft-coverage-gap` | 23% | 46% |
| All three | 25% | **55%** |

Of 381 aircraft the answer key records as staged, 172 were ever airborne. **Fifty-five per cent of
every injection lands on an aircraft that cannot be detected**, and the detector that looked
insensitive at 21 per cent is at 74 on the scenario type whose mechanism is cleanest.

Two things follow, and the second is why this was worth stopping for. The first is `scn-006`: the
targeting gains an airborne test where the decision is made, following `adp-008`'s precedent of
keeping unsuitable tracks out of a run rather than correcting the metrics afterwards. The alternative
— leaving the targeting alone and filtering the answer key — produces identical arithmetic and leaves
perturbed records in the run that the ground truth does not mention, which is unlabelled staged data
in a corpus whose entire value is that its key is complete.

The second is that `anom-004`'s null result is now **provisional rather than settled**. It measured
no separation between a staged run and its matched control at any radius from 5 to 60 km, on runs
where roughly half the intended signal was never present. Whether doubling the detected staged
findings per run changes that is unknown, and it is recorded as a falsifiable prediction attached to
`scn-006` rather than assumed in either direction. The honest summary of where this leaves the
project is that the fusion rules are still gated — but on a generator fix with a measured effect
size, rather than on a detector rewrite with none.

*(Method note for the evaluation chapter: the 90 per cent figure was not trusted when it appeared,
because the harness's own precedence ordering could have produced it. The check that confirmed it —
counting what fraction of each undetected aircraft's reports were on the ground — is independent of
that ordering. A result that arrives overwhelmingly in one bucket deserves a second measurement
designed to falsify it, and this is the second time in two days that doing so changed the
conclusion.)*

### A prediction recorded in advance, and falsified on the first test

`scn-006` was written with a falsifiable prediction attached, and the prediction was wrong. Recording
it in full, because a prediction that is only reported when it succeeds is not evidence, and the
reason it failed is more useful than the prediction would have been.

**The prediction.** `anom-004` measured no separation between a staged run and its seed-matched
control at any radius from 5 to 60 km. That measurement was taken on runs where 55 per cent of the
intended signal was never present, because the generator was staging on parked aircraft. Repairing
the targeting should roughly double the detected staged findings per run, and that might make
clustering discriminate. It was recorded as something to re-measure after the fix and to report
whichever way it fell.

**The fix worked, measured on a second independently seeded batch of 60 runs:**

| | Batch 1 (original) | Batch 2 (airborne gate) |
|---|---|---|
| Parked aircraft in the answer key | 209 of 381 (55%) | 1 of 62 (2%) |
| Recall, `gnss-degradation` | 37% | **81%** |
| Recall, `aircraft-coverage-gap` | 23% | 58% |
| Recall, all types | 25% | **69%** |

**And clustering still does not discriminate.** Over twenty seed-matched triples, staged minus
control on the largest cluster a run produces:

| Radius | `gnss-degradation` | `aircraft-coverage-gap` |
|---|---|---|
| 5 km | +0.05 (1 of 20 triples) | +0.05 (1 of 20) |
| 20 km | +0.10 (1 of 20) | +0.10 (1 of 20) |
| 60 km | +0.40 (3 of 20) | +0.30 (3 of 20) |

The explanation is arithmetic that was available before the prediction was made, and was not done:

| | Batch 1 | Batch 2 |
|---|---|---|
| Staged aircraft per staging run | 4.9 | 2.1 |
| Recall | 25% | 69% |
| **Detected staged findings per run** | **1.2** | **1.4** |
| Background findings per run | ~16 | 15.5 |

**`scn-006` fixed the measurement, not the signal.** It raised recall by removing undetectable targets
from the *denominator*, not by adding detectable ones to the numerator — the airborne gate discards
55 per cent of targets, and 69 per cent of the survivors is very nearly the same absolute number as
25 per cent of all of them. Recall nearly tripled while the quantity clustering depends on moved from
1.2 to 1.4 findings per run.

That is not an argument against the fix. Recall is now an honest figure rather than one depressed by
a defect, which it has to be before any evaluation metric built on it means anything, and the answer
key no longer contains aircraft nothing could detect. It is an argument that two separate problems
were being read as one, and only the smaller has been solved.

**What the remaining problem actually is.** A cluster needs members, and a run supplies one or two
against a background of fifteen. No radius helps: the staged findings can at most add one or two
members to whichever background cluster they happen to fall in, and background clusters already reach
four or five members on their own. The limiting quantity is **how many aircraft a run stages on**,
which is set by the affected fraction of eight per cent, the zone radius of 60 km, and how much
traffic happens to be inside that zone during the window. None of those three has been chosen with
this constraint in mind, and the measurement that would settle them — how many co-located
discontinuities are needed before a cluster is distinguishable from the background — has not been
taken.

*(Recorded as an open question rather than answered, and deliberately not fixed by raising the
affected fraction until the required number is known. Tuning a scenario parameter until a detector
succeeds on it is the failure this project has avoided four times now, and doing it here would make
every detection metric a measurement of the tuning.)*

**A second consequence of the fix, which is a cost rather than a benefit.** With parked aircraft no
longer eligible, more runs stage nothing at all: 10 of 40 in batch 2 against 3 of 80 in batch 1. That
is `scn-006` behaving as specified — a run whose eligible target set is empty records that it staged
nothing rather than staging on an ineligible aircraft — but it means a batch yields fewer usable runs
than it did, and the evaluation's target of 100 to 150 staged incidents now needs roughly a quarter
more runs than a naive count suggests. Worth carrying into the campaign plan.

### Changing the question rather than the parameters

With clustering shown not to discriminate even after the generator was repaired, two routes were
available and the choice between them is a methodological one rather than a technical one.

The first was to make the signal bigger: split the incident radius, which is one number serving two
contradictory requirements, and raise the eight per cent affected fraction until staged clusters
stand out from background clusters. It would probably work. It was rejected because the parameter
would then have been chosen by searching for a value at which the detector succeeds, and every
detection metric afterwards would be partly a measurement of that search. An examiner asking how the
affected fraction was set deserves a better answer than "we raised it until detection worked".

The second was to change the question the track side is asked. Cluster size asks *is there a large
group here*, and answers it against an absolute standard that the background already meets. The
replacement asks *at this place, is the rate of discontinuities higher during the window than at the
same place outside it* — a comparison internal to one run and one location, which makes each run its
own control on both axes and needs no absolute threshold calibrated against anything external.

**Measured before being specified**, over 20 seed-matched pairs in the repaired batch:

| Radius | Staged runs caught | Control runs that fired |
|---|---|---|
| 30 km | 5 of 20 (25%) | **2 of 20 (10%)** |
| 45 km | 10 of 20 (50%) | 5 of 20 (25%) |
| 60 km | 16 of 20 (80%) | 9 of 20 (45%) |

As a standalone detector that is poor, and saying so is the point of recording both columns. What
makes it worth building is the comparison with what it replaces. `anom-005` as specified fires when
an RF anomaly has any co-located track cluster, and a background cluster lies within the fusion
radius on **70 per cent** of the runs whose truth is a sensor fault — the rule would misattribute
most of them, and being mutually exclusive with `anom-006` for the same cluster, would take them from
that rule as well. At 30 km the rate excess fires on **10 per cent** of those same controls.

**The improvement is in false attribution, not in sensitivity**, and that is the failure that
mattered. A detection layer whose whole claim is explainability is damaged more by confidently
reporting interference where a sensor is broken than by missing an incident quietly.

**The strength of that claim was overstated when first written, and the correction belongs here
rather than in a footnote.** Twenty pairs is a small sample and the counts above carry wide
intervals. Two-sided Fisher's exact on staged against control gives p=0.407 at 30 km, p=0.191 at
45 km and p=0.048 at 60 km: **only the widest radius separates the rule from its control at all**,
and marginally. Wilson intervals on the rates are roughly plus or minus twenty percentage points —
the 10 per cent false-alarm figure is 2 of 20, interval [3–30], and the 70 per cent it replaces is 14
of 20, interval [48–85]. Those intervals do not overlap, so the direction of the improvement is
supported; the specific pair of numbers is not. The honest statement is that false attribution falls
substantially and that the effect reaches significance only at the wide radius.

The consequence for the build is concrete: **no threshold may be fixed from this curve**, because
each of its three points is estimated from one batch to within about twenty points, and choosing a
radius from it would be choosing from noise. A second independently seeded batch is required first,
on the terms `anom-011` already sets for the recall figure.

Worth stating plainly for the evaluation chapter: as a standalone detector this scores a Youden's J
between 0.15 and 0.35, on a scale where zero is a coin flip and a screening instrument anyone would
act on wants better than 0.6. Within the same system, the radio side separates an 8 dB elevation from
a baseline spread of about 1.5 dB — beyond five sigma. **The two halves of the fusion evidence are
not remotely comparable in strength**, and a fusion rule that treats them as two equal votes would be
making a claim the measurements do not support.

### A confound found, measured, and then deliberately not engineered around

The naive form of the test is confounded. The incident window sits in the middle of a run, and a gap
measured as an absence needs a report either side of it, so findings are easier to detect mid-run
than at its edges. Control runs therefore score a ratio above one — 2.95 at a 60 km radius — purely
from where the window sits.

The obvious correction is a difference-in-differences: divide the disc's during-versus-outside ratio
by the same ratio computed over the rest of the box, which shares the temporal edge effect and not
the incident. It is more defensible in principle and it was implemented and measured alongside the
naive form.

It makes no difference. Separation by Youden's J is **+0.35 for both forms at 60 km** and **+0.25 for
both at 45 km**; the correction rescales the scores without reordering them, because the edge effect
applies almost equally to the disc and to its complement. The simpler form was kept and the confound
is recorded rather than engineered around — which is the right outcome for a thesis, since the more
elaborate estimator would have looked more rigorous while measuring the same thing.

### The discrimination the track side may not have to carry

One observation recorded while measuring, and deliberately not acted on yet, because acting on it
would change three items at once.

The hard case throughout has been telling a sensor fault from environmental interference, and the
track side has been asked to do it: `anom-005` claims the run when track evidence is co-located and
`anom-006` when it is not. But `anom-007` separates the same two causes from the **RF pattern alone**
— one sensor abnormal with its spatial neighbours nominal is a fault; several adjacent sensors
abnormal together is the environment. On this generator that is an eight-decibel elevation on a
single sensor against clean neighbours, which is a far stronger signal than any track evidence
measured in this session.

If `anom-007` claims the sensor-fault runs first, the track side is no longer the discriminator for
that case, and `anom-012`'s threshold can be read from the sensitive end of its curve rather than the
specific end — 16 of 20 staged runs caught at 60 km, rather than 5 of 20 at 30 km, with the false
attributions that would have caused already removed by a different rule. The ordering between the
three fusion rules therefore has to be settled before any of their thresholds are fixed, and it has
never been written down.

### Pre-registering the replication before running it

Batch 3: base seed 20260917, fixed generator, 60 runs. Batch 2's figures are the claim under test.

## What batch 2 said

| Radius | Staged caught | Controls fired | Best threshold (form 1) |
|---|---|---|---|
| 30 km | 5/20 | 2/20 | 1.79 |
| 45 km | 10/20 | 5/20 | 1.79 |
| 60 km | 16/20 | 9/20 | 1.58 |

## What is being tested, and how it can fail

1. **Out-of-sample, not re-fitted.** Batch 3 is scored at the thresholds batch 2 chose, not at
   thresholds refitted to batch 3. A threshold chosen on the data it is scored against is fitted to
   it, and would make any batch look like confirmation.
2. **Agreement** = batch 3's counts at the fixed thresholds fall inside batch 2's Wilson intervals,
   and the ordering across radii is preserved (60 km most sensitive, 30 km most specific).
3. **Disagreement** = batch 3 lands outside those intervals, or the ordering inverts. That would mean
   batch 2's curve was a property of its seed rather than of the method, and `anom-012` would need
   rewriting before it is built rather than after.
4. **Pooled estimate.** Whatever happens, the two batches are pooled to 40 pairs and the significance
   recomputed — the batch-2 p-values (0.407, 0.191, 0.048) are the figures most likely to move.

## Recorded in advance

The outcome is reported whichever way it falls, as `scn-006`'s prediction was. If batch 3 disagrees,
the correct response is to weaken `anom-012`'s claims, not to average the two batches until the
number looks better.

### The replication, scored against a pre-registration that was written first

The pre-registration above was committed before batch 3 existed. This is the result, reported against
it rather than around it.

**Batch 3 was scored at batch 2's thresholds, not at thresholds refitted to itself.** That is the only
part of this measurement that could genuinely fail, and it is worth being explicit about why. Every
figure quoted for this rule up to that point came from choosing the best-separating threshold *on the
same twenty pairs being scored*, which is fitting; repeated on a fresh batch it would produce a
flattering number every time, and the two batches agreeing would mean nothing at all.

| Radius | Batch 2, fitted | Batch 3, out of sample | Pooled, 40 pairs |
|---|---|---|---|
| 30 km | 5/20 vs 2/20, J +0.15, p 0.407 | 11/20 vs 5/20, J +0.30, p 0.105 | 16/40 vs 7/40, J +0.23, **p 0.047** |
| 45 km | 10/20 vs 5/20, J +0.25, p 0.191 | 13/20 vs 5/20, J +0.40, p 0.025 | 23/40 vs 10/40, J +0.32, **p 0.006** |
| 60 km | 16/20 vs 9/20, J +0.35, p 0.048 | 15/20 vs 6/20, J +0.45, p 0.010 | 31/40 vs 15/40, J +0.40, **p 0.001** |

**Five of the six rates fall inside the intervals batch 2 predicted, and the ordering across radii is
preserved.** The sixth does not: recall at 30 km came in at 55 per cent against a predicted interval
of 11 to 47. It is recorded here as a miss rather than absorbed into a general verdict of agreement,
and the reason it is worth being careful about is that it **missed in the favourable direction**. A
pre-registration that is honoured only when the surprise is unwelcome is not a pre-registration.

**A caveat of my own turned out to be the artefact.** The statistics taken on batch 2 alone had led to
the conclusion that only the widest radius separates the rule from its control, and that was carried
into the spec item, the notes and the progress note as a limitation of the method. Pooled over 40
pairs, all three radii separate, at p = 0.047, 0.006 and 0.001. The limitation was the sample size.
That is a correction of a correction, and the useful part is the general shape: a null result on
twenty paired observations is very often a statement about twenty, and this project has now made that
mistake in the same week as making the opposite one — asserting a precision twenty pairs could not
support. Both are the same error with the sign flipped.

**What the replication does not change is the strength.** Pooled Youden's J is 0.23 to 0.40, against a
scale where zero is a coin flip. The rule is now reliably better than chance and still nowhere near
something that could be acted on alone, and the radio side of the same system remains beyond five
sigma. The curve is now supported well enough to choose a radius from; the choice still belongs to the
evaluation, and to the unsettled ordering between the three fusion rules.

### The generator fix, on three batches

`scn-006` was measured on one batch when it landed. Three batches now exist and the picture is
consistent in direction and better than the first repair suggested:

| Batch | Generator | Recall, all types | Recall, `gnss-degradation` | Parked aircraft in the answer key |
|---|---|---|---|---|
| 1 | original | 25% | 37% | 209 of 381 (55%) |
| 2 (seed 20260916) | repaired | 69% | 81% | 1 of 62 (2%) |
| 3 (seed 20260917) | repaired | **81%** | **95%** | **0 of 74** |

The loss account `anom-011` asked for is now settled as well. In batch 3, of 14 remaining misses, 11
are on-ground and 3 are below threshold, with **nothing at all** lost to the interior filter, to an
aircraft absent from its run, or to an unbracketed absence. The on-ground remainder is no longer
parked aircraft — those cannot be targeted any more — but aircraft that took off or landed during the
window, which is the detector being right rather than a defect to chase.

The staging yield across the two repaired batches is 58 runs of 80, or **72.5 per cent**, which is
close enough to the 75 per cent first measured that the campaign sizing in `eval-002` stands: roughly
200 runs for 150 staged incidents.

### Settling an ordering that had never been written down

Three rules produce the anomalies an analyst sees, and until now they were specified as three
independent tests. Reading them together shows they are not: they partition a single decision, and
the partition had no declared order, so which one claimed a run would have been decided by whichever
happened to be evaluated first — a property of the source file rather than of the evidence.

The order settled in `anom-013` is `anom-007`, then `anom-006`, then `anom-005`, and the argument for
it is an asymmetry that has been measured rather than assumed. `anom-007` separates a broken receiver
from an environmental cause using the RF pattern alone: one sensor abnormal with its spatial
neighbours nominal. On this generator that is an eight-decibel elevation against a baseline spread of
about 1.5 dB, beyond five sigma. The track side's rate excess, pooled over 40 matched pairs, reaches
a Youden's J of 0.40. **Asking the weaker signal to arbitrate what the stronger one already settles
is the error**, and it is the error that produced a background track cluster inside the fusion radius
on 14 of 20 sensor-fault runs.

What makes this worth recording as a design decision rather than an implementation detail is that it
*removes* a question instead of answering it. The alternative was to make the track evidence good
enough to tell a fault from interference — the direction the whole session had been pushing in, and
the direction that produced two rejected parameter-tuning routes. Ordering the rules so that the
fault is decided before the track side is consulted means the track evidence never has to make that
distinction at all. Its remaining job is to separate interference from nothing, which is a much
easier question and one its measured strength can support.

The consequence for `anom-012` is recorded and deliberately not acted on: once `anom-007` claims the
sensor-fault runs, the radius should be read from the sensitive end of the trade-off curve — 31 of 40
at 60 km — rather than the specific end. That is left unfixed because the argument assumes `anom-007`
claims them, `anom-007` does not exist, and its catch rate has never been measured. Fixing a
threshold on an assumption about an unbuilt component would be the same class of error as the two
already recorded this session, with the added disadvantage of being harder to notice.

### Building the replacement, and one decision the measurement forced

`anom-012` computes the rate excess and nothing else: no threshold, no severity, and a policy with no
default radius. The absence of a default is the part worth explaining, because the obvious thing is to
supply one. The three measured radii are not a curve with a maximum to be found; they are three
different trades between a missed incident and a misattributed one, and which is right depends on
`anom-013`'s ordering and on costs the evaluation has not yet assigned. A default would make that
choice silently, in the one place nobody reviewing the fusion rule would think to look.

Two implementation decisions came from the measurement rather than from taste. The disc is selected
with `db-004`'s proximity query rather than by computing distances in the detector, because a second
copy of the distance rule is the trap this repository recorded when a remedy lived in two places and
a third caller knew about neither. And the ratio is **smoothed** — one finding per run, spread over
the run's whole span, added to both rates — because a window holding findings against a remainder
holding none otherwise gives an infinite ratio that no threshold can order against a finite one. The
smoothing is not a detail: every figure quoted for this rule was measured with it, so changing it
would silently invalidate the replication, and the module says so where someone tempted to tidy it
would read it.

### The sensor-fault rule, and a defect the unit tests could not have found

`anom-007` separates a broken receiver from a cause out in the world using two pieces of evidence that
are deliberately not combined: the receiver's close neighbours, and the channels either side of the
one that moved. The geography argument is that interference has a location and reaches whatever is
near it, so a receiver away from its normal while its neighbours sit at theirs is describing itself.
The frequency argument is independent of it: a real emission spills into adjacent channels, so an
isolated channel between two normal ones is a pattern the physics does not easily produce, while the
whole plan rising together is the weaker claim because a wideband emitter parked beside the receiver
would look the same. Confidence is High, Medium and Low across those three cases and qualifies the
*attribution* rather than the deviation, whose severity `anom-001` already carries.

The item was built, its thirty-six unit tests passed, its mutation pass killed eighteen of twenty, and
the implementation was wrong. The measurement that the item itself required found it.

Built as first written, the rule read a neighbour's nominality off `anom-001`'s episodes: a neighbour
with no overlapping anomaly was treated as clean. Over the 240 stored runs that gave a catch rate of
60 of 60 on the runs whose truth is a sensor fault -- the number `anom-013`'s ordering depends on, and
it held without qualification -- and it also claimed **21 of 60 gnss-degradation runs**, on a staged
receiver, inside the staged window. That is a misattribution of exactly the class `anom-013` was
written to remove, running in the opposite direction.

The cause was neither the radius nor the layout. `scn-002`'s injected elevation is 8 dB scaled per cell
per tick by 1 + 0.25 of a standard normal draw, and `anom-001`'s threshold is 6 dB, so roughly one tick
in six falls short and ends the episode: a staged cell emits a median of six episodes where the
incident is one. Two receivers loud through the same 300 s therefore have fragments that never
overlap, and each reads as isolated from the other. Measured across the 120 staged runs, the
neighbours in those windows sat 2.51 dB above their own baselines at the fifth percentile and 4.46 dB
at the median -- and not one of the thirty-seven measurements crossed the 6 dB anomaly threshold in
the window concerned. Every one of them was invisible to a test built on episodes.

The repair is a reversal of a decision recorded on the item the same day, and the original wording of
the item was right: it asked for "the readings of its spatial neighbours in the same window", and the
amendment had replaced the readings with another rule's findings because that made the rule pure and
testable without a database. *Was this receiver anomalous* and *was this receiver nominal* are
different questions, and only the second one is this rule's. Asking it of the readings removed all
twenty-one misattributions and cost none of the sixty catches.

### Choosing the nominality bar from two populations rather than from one

The bar is the one number the repair introduces, and it was set from a measurement designed to make it
falsifiable. Two populations were collected over the 120 staged runs: the elevation of a neighbour the
incident also touched, during a window the rule was about to call a fault, and the elevation of a
neighbour it did not touch. The first reaches 2.51 dB at the fifth percentile and 4.46 dB at the
median; the second sits at −0.05 dB at the median and 1.58 dB at the ninety-fifth. The populations
separate, and 2 dB lies in the gap between them.

Two decisions follow from the shape of that measurement rather than from the chosen value. The bar is
reported with its neighbours -- 1.0 and 1.5 dB give the same result on this corpus, 3.0 dB gives five
misattributions and 4.0 gives seven -- so the choice is visibly a plateau rather than a maximum, which
is the distinction `anom-012`'s radius had to be protected from. And it is expressed in decibels
rather than in multiples of the baseline's own spread, because that is `anom-003`, and keeping the two
apart is what stops one detector being counted twice in an evidence bundle.

The rejected alternative is recorded because it also works on this corpus. Treating a neighbour episode
within 30 s of the window as overlapping it removes all twenty-one misattributions too, keeps all sixty
catches, and requires no readings at all. It was rejected on an argument rather than on a count: it
answers whether the neighbour was *anomalous recently*, and it only works while the neighbour crosses
`anom-001`'s threshold somewhere nearby. The 8 dB elevation is the generator's choice and not a
property of interference; a weaker emitter, or a neighbour further out, raises a neighbour by three or
four decibels, produces no episode at any tolerance, and would read as nominal for ever. The readings
form sees it directly. This is a case where the cheaper repair passes every test available today and
fails the first realistic change to the scenario, and the measurement could not have distinguished
them -- only the argument could.

### What the episode boundary was also costing, and the refusal that fell out of the repair

The same fragmentation had a second effect nobody had looked for. Because the window came from the
episodes, one broken receiver was reported roughly five times per run, each fault spanning a median of
20 s of a 300 s incident. Taking `anom-001`'s episodes as the *seed* and the readings as the boundary
-- the event began where the receiver left its baseline, not where a threshold happened to be crossed
-- brings that to 1.13 faults per run at a median span of exactly 300 s. The window now recovers the
incident. It overruns at the top, 390 s at the maximum, because a tick either side can still read
above a 2 dB bar on ordinary noise; that is the price of a bar low enough to keep the window
contiguous, and it is recorded rather than trimmed.

Separating the seed from the boundary also created a case that had not existed before: an episode
whose window the readings do not sustain, where the receiver sits inside the bar of its own baseline
across the whole window the episode seeds. That is now refused as undecided rather than reported,
because a threshold crossing the window does not bear out is not evidence about an instrument. It is
responsible for most of the improvement in the false-positive rate: runs staging nothing on the RF
grid raise a fault on 6 of 100 of them, down from 14 of 100. The residue is `anom-001`'s own false
positives promoted one layer up, and a minimum-duration constraint belongs to that item rather than
to this one.

### Two results this measurement produced that are not about the rule

First, the ordering `anom-013` declares is now supported by the number it was missing. The rule claims
every one of the sixty sensor-fault runs, on the right receiver and in the right window, so the
assumption that putting it first moves those runs out of fusion's way is not an assumption any more.
`anom-012`'s radius can therefore be read from the sensitive end of its curve, which was the decision
that has been waiting on this item.

Second, and less comfortably, the rule claims **20 of 20 ambiguous-mixed-evidence runs at High
confidence, with no trace of ambiguity in the output.** That follows from the scenario design rather
than from a defect: `scn-002` stages that type on a single receiver by construction, and `anom-013`
offers a claimed zone to no later rule. It is a threat to the validity of any evaluation that treats
the ambiguous type as a test of whether the system can express uncertainty -- because under this
ordering it cannot, and the type instead measures how confidently the system resolves a case designed
not to resolve. Recorded here before the evaluation is designed rather than discovered inside it.

### A trade-off curve measured on inputs the rule would never receive

`anom-012`'s radius was held back through three items on an explicit condition: it could not be
chosen until `anom-007` existed and its catch rate on sensor-fault runs had been measured. When that
condition was discharged, the obvious move was to read the recorded curve — 16 of 40 at 30 km, 23 at
45, 31 at 60 — at its sensitive end and take 60 km. Checking where those numbers came from first
turned out to matter more than the choice.

**They were measured with the centre and the window taken from ground truth.** The measuring script
says so in its own header, and at the time that was defensible: the question it was asking was
whether the *signal* existed at all, and seeding it from truth isolates the signal from the
detector's ability to find it. What was never revisited is that the rule does not receive those
inputs. Per `api-009` its centre and window come from a detected RF episode, and `anom-007`
established the week before that an `anom-001` episode is not an incident — the injected elevation
dips below the threshold about one tick in six, so one 300 s incident arrives as a median of six
episodes.

The consequence is sharper for this rule than for any other, because the window and its complement
are the two halves of the ratio it computes. A window shorter than the event does not merely measure
less of it; it moves the remainder of the event into the reference period the window is being
compared against, depressing the numerator and inflating the denominator at once. Measured over the
same 40 matched pairs, the longest episode on a run has a median length of 90 s against a staged
300 s, while `anom-007`'s window — seeded by the episodes and bounded by the readings — has a median
of 320 s.

Re-scored at the same pre-registered thresholds, with the window the rule will actually be given:
18 of 40 at 30 km, 21 at 45, 26 at 60, against 15, 20 and 28 from the ground-truth windows. The curve
survives and flattens. Nothing had to be withdrawn, which is the outcome that makes this worth
recording rather than the outcome that would have made it dramatic: **the check was cheap, the result
was benign, and it was still the difference between a parameter chosen from evidence and a parameter
chosen from a coincidence.** The general form is that a measurement taken to answer one question —
does this signal exist — silently becomes the evidence for a second question it was never designed
for, which is how a parameter gets chosen.

### The control arm that the rule ordering removes

A second assumption failed the same check, and this one changed the decision rather than the numbers.

Every specificity figure recorded for `anom-012` was measured against `rf-sensor-fault` runs as the
negative arm: a run at the same seed, replaying the same traffic, with nothing staged on the track
side. That was the right control while the fusion rule was expected to argue with sensor faults.
`anom-013` removed that expectation, and the measurement confirms it removes the arm as well. Of the
120 runs in the replication batches, those reaching a fusion decision at all are 40 of 40
`gnss-degradation`, **0 of 40 `aircraft-coverage-gap`, and 1 of 40 `rf-sensor-fault`.**

So the arm the curve's false-alarm rate was measured against never reaches the rule, and the arm that
could actually produce a false interference call — a coverage gap with a spurious radio anomaly
beside it, which is the failure `anom-006` exists to prevent — does not occur once in forty runs.
There is effectively no false-positive pressure at this step, which is what `anom-013` predicted from
the ordering alone and is now measured rather than assumed.

That is what justifies reading the curve at its sensitive end, and it is a stronger justification
than the one `anom-013` offered, because it is a property of what reaches the rule rather than an
argument about what ought to. The radius is 60 km on that basis and on a second, independent one:
60 km is `scn-002`'s own configured incident radius, so the disc matches the scale of the zone it
measures. That is configuration rather than per-run ground truth — the same class of knowledge as the
number of receivers in the layout — and it is the basis `anom-004` already used for its own default.

### Discharging an argument rather than overturning it

`anom-012` shipped with no default radius, and a test asserting the absence. The recorded reason was
that every measured point was a different trade-off and a default would make that choice quietly, in
the one place nobody reviewing the fusion rule would look. Adding a default now is a reversal, and
the distinction worth preserving is that the original argument was not *wrong* — it was conditional,
and the condition has been met. The objection was to a choice made silently, not to the existence of
a choice. Once the choice is made in the open with its reasons attached, a named constant carrying
those reasons is more discoverable than the number repeated at every call site, which is the
arrangement `anom-004` and `anom-007` already use for values of exactly this kind.

The test was replaced rather than deleted, and the replacement asserts the value *and* cites the
reasons in its docstring, so the reversal is visible from the test suite rather than only from the
backlog.

### A defect found by supplying realistic input rather than by reasoning about it

Feeding the rule detected windows rather than ground-truth ones also crashed it. A single-reading
`anom-001` episode has its start equal to its end, and the rate divides by the window's length: 6 of
86 runs produce such an episode as their longest. The item had a failure case for a window that
leaves no remainder and none for a window that leaves no window.

It is refused rather than clamped. A clamped zero-length window would return a number computed over
one reading with nothing in the result to mark it as different from a measurement, which is the shape
of error this project has twice recorded as the expensive one.

The upstream fix — a minimum episode duration on `anom-001` — is specified as `anom-014` and
deliberately left unbuilt, and the reasoning is the part worth keeping. The problem it would solve is
real and measured: `anom-001` raises an episode on 14 of 100 runs that stage nothing on the RF grid.
But the harm is already contained twice downstream, by `anom-007`'s refusal of episodes its readings
do not sustain and by the refusal above. Building it would change `anom-001`, and every detection
figure in this chapter — `anom-007`'s 60 of 60, `anom-012`'s curve on 40 matched pairs, `anom-011`'s
recall, and a batch-3 replication scored against a pre-registration written before it ran — was
measured through `anom-001`. That is the whole evidence base, spent on removing the source of a harm
that is already caught. The decision is to specify it, record why it waits, and regenerate and
re-measure the batches together if something ever depends on it that the downstream refusals do not
cover.

### Building a precedence over rules that do not exist yet

`anom-013` declares the order in which the three reportable rules speak, and two of those rules were
unbuilt when it was written. That looks like a reason to defer it, and the opposite turned out to be
true: `anom-006`'s own specification already carried the constraint that it is *mutually exclusive
with `anom-005` for the same cluster*, and until a precedence existed that constraint was a sentence
in a document rather than something any code could enforce. Building the two rules first would have
meant implementing that exclusion twice, once in each of them, which is the arrangement the
constraint was written to avoid.

The scoping decision that made the item finishable is that **it resolves claims rather than rules.**
Each rule emits a bid for a zone; the ladder sorts the bids by a declared constant and hands back at
most one per zone with a ledger of what was suppressed and by whom. The alternative — a resolver that
calls the three rules itself — cannot be built before them, and could only have been proved against
stubs. This project has just paid for that arrangement once: `anom-007` passed thirty-six unit tests
and a mutation pass built from clean constructed episodes, and was wrong about the corpus. A
mechanism that orders whatever it is handed can be tested honestly today; a mechanism that
orchestrates two absent rules cannot.

What that scoping costs is stated on the item rather than discovered later: only `anom-007` produces
claims, so the ladder cannot be exercised end to end, and no measurement of it over the corpus is
possible until `anom-005` lands.

### The ordering already worked before anything enforced it

The measurement taken for `anom-012`'s radius answers a question about `anom-013` as a side effect.
Of the 120 runs in the replication batches, those reaching a fusion decision at all are 40 of 40
`gnss-degradation`, 0 of 40 `aircraft-coverage-gap` and 1 of 40 `rf-sensor-fault` — because
`anom-007` claims the rest outright.

That is the separation this item was written to produce, and it is already present without it. The
honest reading is that it is currently a property of *what the rules happen to emit* rather than of a
declaration anything checks: `anom-007` claims those runs because its own evidence is strong, not
because anything forbids a later rule from claiming them too. The moment `anom-005` exists and bids
for a zone `anom-007` has taken, the separation depends on a rule nobody wrote down. That is an
argument for writing it down before the third rule arrives rather than after, which is the ordering
this session took.

### Two decisions inside the ladder that are not obvious

**Suppression is between rules and never within one.** The tempting reading of "at most one
reportable anomaly per candidate zone" is that a zone admits one anomaly full stop, which would also
suppress a rule's second finding in the same place. Two broken receivers forty-five kilometres apart
are two broken receivers, and a rule that reported one of them would be wrong in a way nothing
downstream could detect. The exclusion the item exists to enforce is `anom-006`'s with `anom-005`,
which is cross-rule by construction, so the implementation skips same-rule comparisons deliberately
and a mutation that removes that skip is killed by a test that says why.

**An undecided verdict is not a claim.** `anom-007` is three-valued, and the two ways it declines a
zone — environmental, or not decidable — both pass the zone to the next step untouched. The
environmental case is straightforward, since that is precisely what `anom-005` exists for. The
undecided case is the one worth arguing: a rule that could not tell must not thereby block the rules
that might, or "I cannot decide" would silently become "nobody may decide", which is a stronger claim
than the evidence supports and the opposite of what the word means.

### A parameter recorded as provisional rather than defended

Two claims count as one zone when their centres lie within a configured radius and their windows
overlap. The default is the layout's own discrimination radius, on the same argument `anom-007` uses
for its neighbour test: it is the distance `scn-005` validates as the range over which one cause can
reach two receivers. Deliberately not `anom-012`'s 60 km, which answers how wide a patch to count
dropouts over — a different question that happens to be asked in the same units.

It is recorded as provisional on the item, and the reason is specific rather than a general hedge. An
`anom-005` zone may span a centre and its neighbours, up to about 120 km across, and two claims at
opposite ends of one incident would then fail this test and both be reported. Guessing now at the
shape of a zone produced by a rule that does not exist is how a parameter gets fitted to an
imagination rather than to evidence, so the value is justified for the claims that exist today and
revisited when the third rule produces its own.

### A gate that would have rejected reports on the grounds of low air traffic

`anom-005` was specified from the outset with both conditions necessary: a radio anomaly *and*
co-located track evidence. Once `anom-012` had a measured trade-off curve and a chosen radius, the
apparent decision was simply which point on that curve to gate at. The measurement that settled it
instead removed the gate, and did so for a reason the curve could not show.

The curve was measured over all runs of each type. Under `anom-013`, `anom-005` sees almost none of
them. Measured over batches 2 and 3 plus the twenty quiet runs, the zones actually reaching the rule
are 40 of 40 `gnss-degradation`, 0 of 40 `aircraft-coverage-gap`, 0 of 20 `normal-baseline` and 1 of
40 `rf-sensor-fault` — and that single leaked fault carries a zero-length window and cannot be
measured at all. The population arriving at the rule is forty true interference zones and one
unmeasurable leak. A gate at the pre-registered threshold would report 26 of the 40 and reject
nothing, because there is nothing false there to reject.

The decisive part is what the fourteen rejected zones have in common. They are not zones where the
track evidence was weak; they are zones with almost no air traffic in them. Every one of the fourteen
holds four or fewer track findings in the disc across the whole run — five hold none during the
window, two hold none anywhere — while the distribution over all forty has a median ratio of 3.87 and
a seventy-fifth percentile of 11.47. The gate would therefore suppress an interference report, backed
by an eight-decibel radio signal, because few aircraft happened to be near the incident. That is not
a specificity/sensitivity trade-off at all; it is a detector whose output depends on traffic density
at the staged location, which is a property of where the generator put the zone.

The threshold is kept and demoted rather than discarded: it becomes the boundary between confidence
bands rather than a condition of firing, so the measurement still does work and the cost disappears.
The confidence is three-valued in the same shape `anom-007` uses, and for the same reason — the third
band is *too little traffic to judge*, which must not read as absent corroboration. That is now the
third distinct place in the detection layer where silence had to be separated from evidence of
absence, after `anom-001`'s unjudged cells and `anom-007`'s unmeasurable neighbours. A pattern
recurring three times in one layer is worth naming in the write-up as a property of building
detectors over incomplete observation, rather than as three coincidences.

### The limitation that decision rests on, stated rather than buried

What the measurement establishes is that the gate has no opportunity to help in this corpus, not that
it would never help. There is no scenario type producing a multi-receiver radio anomaly that is *not*
interference — no weather, no distant emitter, no two receivers failing together — so the population
arriving at `anom-005` is pure by construction. A deployment would not be.

The decision stands anyway, and the reason is worth stating as a principle rather than as a
convenience: a gate whose benefit is unmeasurable and whose cost is measured at fourteen of forty
cannot be justified on this evidence. If a corpus arm is ever generated that stages such a cause, the
question reopens with data. That is a different posture from deciding the gate is wrong in general,
and the item records which of the two is being claimed.

### A rule that cannot be built, and the difference between a weak detector and an absent signal

`anom-006` was next, and the measurement taken before specifying its threshold established that it
should not be built at all yet. The finding is worth the space because it separates two things that
look identical from inside a failing detector.

Its defensive job turns out to be already done. The item exists to keep a coverage gap from being
reported as interference, and measured over 240 runs, 0 of 40 coverage-gap runs reach `anom-005` —
because that type stages nothing on the radio grid and `anom-005`'s trigger is a radio anomaly. The
misattribution the rule was written to prevent can no longer occur, and it is prevented by the
*absence of a strong signal* rather than by the presence of a weak one. What remains is the positive
claim: saying we are not hearing aircraft here, when that is true.

Against forty seed-matched pairs, the effect is real and unmistakable and far too small to act on. A
coverage-gap run holds a mean of 16.1 track-gap findings against its control's 15.1, and **never
fewer**: 23 pairs strictly greater, 17 tied, none lower. Zero discordant losses in forty pairs is
about as strong as evidence of existence gets. It is also one finding in fifteen, and a detector sees
one run without its control.

The zone-level design does not rescue it and actively makes it worse. Proposing zones by clustering
the findings and scoring each with `anom-012`'s rate excess, then taking the strongest zone per run,
gives staged against control of 7 to 3 at a 20 km cluster radius, 5 to 4 at 40 km and 4 to 2 at
60 km. That is chance. **The machinery destroys a signal that raw counting preserves**, and the
mechanism is the one `anom-005`'s measurement exposed: a ratio over a disc holding one to three
findings is dominated by the smoothing term, so taking a maximum across zones selects for
small-sample noise rather than for effect. A statistic chosen to be robust in one setting can be
strictly worse than the naive count in another, and taking the extreme value across many candidates
is where that reverses.

Building the rule as specified would have been actively wrong rather than merely weak: it fires when
dropouts are present and no co-located radio anomaly exists, a quiet run holds about fifteen findings
and no radio anomaly, so it would fire on every quiet run in the corpus and destroy `anom-008`'s
zero-anomalies control. A discrimination threshold is mandatory and no threshold on the available
quantities provides one.

### Two items now blocked on the same act, and the argument for doing it once

What blocks `anom-006` is not its design but the corpus, and specifically the open question `scn-006`
already recorded: the limiting quantity is how many aircraft a run stages on. Since that fix
restricted staging to airborne aircraft, the eligible pool shrank and the eight per cent fraction
draws a mean of 1.7 aircraft per run, with 11 of 40 runs drawing none — so a quarter of the
coverage-gap arm has an empty answer key and is indistinguishable from its control by construction.
That is now written as `scn-007`, which guarantees a floor while keeping the draw order-independent
and reproducible from the seed.

`scn-007` and `anom-014` are now blocked on the same act. Both are generator or upstream-detector
changes; both would invalidate every detection figure measured through the current batches —
`anom-007`'s 60 of 60, `anom-012`'s curve, `anom-011`'s recall, and a replication scored against a
pre-registration written before it ran. Deferring each individually is the right call twice over, and
it also means the project is accumulating a queue of changes that share one cost. The position
recorded on both items is that when a regeneration happens, both land in it and every figure is
re-measured together — which converts two separate invalidations into one, and gives the re-measured
figures a single set of conditions to be reported under.

### Two defects an end-to-end run found that unit tests and mutation testing could not

`anom-005` was built with thirty-eight tests, a hundred per cent coverage of its module, and a
mutation pass in which every genuine mutant died. It was then run over the corpus as part of the whole
ladder, and two things showed up immediately that none of that could have revealed.

The first was arithmetic: the ladder produced **160 interference zones from 60 staged runs**. An
incident spanning two receivers has both dismissed as environmental by `anom-007`, each naming the
other, so emitting one zone per dismissal describes the same event twice. Every unit test had used a
single dismissal, which is not what the upstream rule emits. The fix merges dismissals into events
before any zone is produced, grouping on `anom-007`'s own finding of which receivers deviated together
rather than measuring distance a second time, with membership chaining so that a deviation reaching
three receivers is one event even where the outer two never name each other. The corpus then yields 61
zones for 60 staged runs and one leaked fault — exactly one per event.

This is the third time in this project that the unit of report has had to be corrected upward:
`anom-001` groups readings into episodes, `anom-007` groups episodes into one verdict per receiver,
and now `anom-005` groups receivers into one zone per event. The pattern is that each rule's natural
output is its *evidence*, and the thing worth reporting is one level coarser. It is worth stating in
the write-up as a design lesson rather than three separate bugs, because in each case the test that
would have caught it is the one that feeds the rule what the layer below actually produces.

The second defect was a consequence of the first that nobody would have looked for. `anom-013`
suppresses between rules and never within one, deliberately — two broken receivers are two events.
That decision is safe only if each rule emits one claim per event, so the 160 zones would all have
been reported. The precedence and the rule it orders had a contract between them that neither
document stated, and only running them together exposed it.

### A parameter whose case got stronger after it was settled

Merging also changed the corroboration figures, and the change is large enough to be worth recording
in its own right. Per receiver, over 40 runs: corroborated 6, not corroborated 9, not measurable 25.
Per event, over the merged 61 zones: **corroborated 7, not corroborated 7, not measurable 47.**

The decision not to gate `anom-005` on the track evidence was taken on a measurement showing a gate
would report 26 of 40 and reject nothing. The merged figures make that case much stronger: a gate
would report **7 of 60** staged interference runs, because 47 of 61 zones cannot have their track side
measured at all — the disc holds no finding in one of the two periods. On this corpus the track side
is not a weak second vote. It is absent in three quarters of cases and confirms in about one in nine.

That is an uncomfortable result to record after two sessions of work on `anom-012`, and it is the
honest one. It does not make that work wasted: the rate excess is the reason cluster size was
abandoned, it is what `anom-006` was measured against, and the reason its contribution is so thin here
is the same corpus limitation `scn-007` exists to fix — a mean of 1.7 staged aircraft per run leaves
most discs with nothing in them. What it does mean is that any claim about the *fusion* of radio and
track evidence in this system must be stated as what it is: on the current corpus, fusion is the radio
evidence with an occasional corroborating note.

### The whole ladder, measured for the first time

With `anom-005` built, the three-step decision could be run end to end over all 240 runs:

| Staged | Runs | Decided as specified |
|---|---|---|
| `rf-sensor-fault` | 60 | 60 |
| `gnss-degradation` | 60 | 60 |
| `ambiguous-mixed-evidence` | 20 | 20, as a sensor fault by design |
| `aircraft-coverage-gap` | 80 | 75 correctly silent |
| `normal-baseline` | 20 | 19 correctly silent |

**No zone in any run received two answers**, which is `anom-013`'s first failure case and it does not
occur. Six runs that stage nothing on the radio grid raise a sensor fault, which is `anom-001`'s own
false-positive rate promoted one layer and is owned by `anom-014`. Five interference runs and one
sensor-fault run carry a second anomaly of the other type in a *different* zone; that is not a
precedence violation, because the guarantee is one answer per zone and never per run, and a run may
genuinely hold a broken receiver in one place and interference in another.

The figure that must not be read as a result is the coverage-gap row. Those 75 correct non-detections
are correct only because `anom-006` is unbuilt: the system is silent on that arm because it has no
rule for it, not because it judged and declined. Reporting 75 of 80 as a success would be exactly the
error `anom-008` exists to prevent, one level up.

### A threshold that says what crossing it means and nothing about not crossing it

`anom-001` reports an episode: a run of consecutive readings sitting past a configured bar. Nothing
in the original item stopped an episode being one reading long, and the consequence was measured
twice before it was fixed. At least one episode was raised on 14 of 100 runs that staged nothing at
all on the RF grid, and a one-reading episode has a start equal to its end, so it presents a window
of no length to `anom-012`, which divides by it. Both symptoms were contained downstream —
`anom-007` refuses an episode its own readings do not sustain, and `anom-012` refuses a zero-length
window outright — and the item was therefore specified and deliberately left unbuilt, on the grounds
that removing the cause would invalidate every figure measured through `anom-001` for the sake of
tidiness at a harm already caught. It was built when a corpus regeneration became necessary for
other reasons, so that one invalidation covered both.

The value of the minimum was not chosen. It was measured on the two populations it has to separate,
over all 240 stored runs at the shipped bands: episodes on a cell the answer key names inside the
staged window, against every other episode raised anywhere. The separation is complete. Of the 80
episodes in the second population, **every single one is exactly one reading long**, while the 1,257
in the first run to a median of 20 seconds and a maximum of 210. A minimum of 10 seconds — one
sampling interval, which is to say *at least two readings* — removes 80 of 80 false episodes and
still catches **140 of the 140 runs that stage any RF at all**. It is not a trade-off; at that value
nothing measured is lost.

Ten, twenty and thirty seconds are indistinguishable on both populations, and the bottom of that
plateau was taken deliberately. Each larger value discards more true episodes for no measured gain —
24 per cent of them at 10 s against 56 per cent at 30 s — and 10 s claims no more than the sentence
the item exists to enforce, that one reading is not an event. The number is tied to the corpus's 10 s
sampling interval and is recorded as such: the quantity it encodes is a count of readings, not a span
of time, and a change of interval requires re-deriving it rather than carrying it across.

The design decision worth recording is where a suppressed episode is reported. The item as first
written said it should go "in the same channel `anom-001` already uses for cells it could not judge",
which reads as though it should join the unjudged cells. It should not, and the reason is the
distinction this project has now made three times in three rules. An unjudged cell is the statement
*I had no baseline, so I did not look*; a suppressed episode is the statement *I looked, I saw the
bar crossed, and it did not last*. Those are the same separation of silence from evidence of absence
that `anom-007`'s three-valued verdict and `anom-005`'s three-valued corroboration are built on, and
folding the second into the first would discard the episode's own window — the only thing that makes
a suppression checkable afterwards. It gets its own field, carrying the cell, the window, the
reading count, and the minimum it failed.

The wrong assumption underneath the original defect is worth stating plainly, because it is the same
one that produced `anom-007`'s misattribution a day earlier: *a threshold tuned so that crossing it
means something says nothing about what not crossing it means.* There it was a neighbour with no
reported anomaly being read as a neighbour reading normally. Here it is a single crossing being read
as an event. In both cases the rule was treating the absence of a threshold crossing as positive
evidence, and in both cases the fix was to go back to the readings.

### A specification that could not be implemented where it assumed

`scn-007` puts a floor under the number of aircraft a run stages on, and the item named its own
implementation: rank the eligible aircraft by their derived value and take the lowest *n*, where *n*
is the greater of the floor and the fraction's expected count. Building it revealed that the
implementation cannot be done where the item assumed it would be, and the reason is a property the
generator acquired deliberately two items earlier.

Ranking needs the pool. `scn-002`'s staging seam is a per-record transform over a stream the replay
processes one window at a time, and it never holds a pool — which is precisely why selection was made
a pure function of the seed and one aircraft's own pseudonym in the first place, so that nothing
depended on arrival order, batch size, or how many aircraft had been seen so far. A floor cannot be
expressed that way, because "the lowest *n*" is a statement about a set rather than about a member.
The two requirements are not in conflict but they cannot be met in the same pass.

The resolution was to add a pass rather than weaken either. The run now reads its corpus window once
through the replay adapter's reader without ingesting anything, collects the pseudonyms eligible
under the same three gates the perturber applies — inside the window, inside the zone, airborne, and
not on `adp-008`'s exclusion list — ranks that set, and hands the chosen subset to the perturber
before the replay begins. The cost is one additional scan of a 133,634-row extract per run, against a
run that already ingests tens of thousands of observations. What it buys is the original property
intact: the selection is still a pure function of the seed and the pool, still independent of order,
and still reproducible without replaying the run.

One guard was added to stop the survey and the perturber drifting apart. Eligibility is asked of the
perturbation object itself rather than implemented twice, because a survey that disagreed with the
perturber about what may be staged on would rank aircraft the perturber then refused — and the answer
key would name aircraft nothing was done to, which is the empty-answer-key failure this item exists
to remove, arriving by a different door.

A second decision followed from running it. The run records what the survey *found* and not only what
it staged: how many aircraft were eligible, how many were asked for, and whether the floor was
reached. A run that staged two aircraft because only two were there is a different fact from a run
that staged two because two were asked for, and the aircraft list alone cannot distinguish them —
which would leave an evaluation unable to say whether a miss belonged to the detector or to the
corpus.

### A default that made the behaviour worse before the measurement was in

Worth recording because it was caught by the existing suite rather than by inspection, and because
the mechanism is easy to reproduce. The floor was committed with a placeholder default of zero while
its value was being measured, on the assumption that zero would be a no-op that restored the previous
behaviour. It is not, and three database-backed tests failed immediately.

The old rule thresholded each aircraft's own derived value at the fraction, which on a small pool
sometimes drew one aircraft and sometimes none. The new rule takes `round(fraction × pool)`, which on
a small pool is deterministically **zero**. So a floor of zero is strictly worse than what came
before: it converts an occasional empty answer key into a guaranteed one on exactly the runs the item
was written to protect. The tests that caught it were asserting that a coverage-gap run withholds
rows and that its answer key names aircraft — both true before, both false with the placeholder in
place.

The lesson is not about the placeholder. It is that an "expected count" and a "draw" are different
estimators with the same mean, and substituting one for the other is a behavioural change even when
the parameter is unchanged. A test asserting the two are equivalent at zero would have been wrong;
the test now in place asserts the opposite, with the reason attached.

### Where the floor was set, and what it does not fix

The floor's value was measured the same way the minimum duration was: on the populations it has to
separate, and before the number was written down. The existing corpus already contains the
experiment, in 60 seed-matched pairs — a coverage-gap run and a run on the same seed staging nothing
on the tracks, so the same corpus window and the same aircraft. Grouping those pairs by how many
aircraft the run actually staged on gives the excess in track-gap findings as a function of the
count.

The first version of this measurement was taken over all 60 pairs in the corpus and had to be
withdrawn; the reasons are in the subsection below on the corpus not being one corpus. Restricted to
the 40 pairs generated after `scn-006`, the curve is both cleaner and more informative than the
contaminated one had been.

The excess rises **monotonically** with the number staged — +0.7, +1.0, +2.0, +2.5 and +3.0 findings
at one through five — and the win rate goes from 13 of 19 pairs below three to **10 of 10** at three,
four and five. At even odds, ten of ten is about one in a thousand. The contaminated version had
shown the excess flat and noisy above five, which is what a population of undetectable parked
aircraft looks like when it is mixed in, and it had made the result look stronger (15 of 15) while
hiding the monotonic relationship that actually matters: staging more aircraft does buy more signal.

The floor is set at five, the top of the band and its largest measured excess. **Five is also the
most that any run in the clean region stages**, so the curve cannot be read beyond it. Extrapolating
the slope, an excess of one standard deviation of the background would need about six staged aircraft
and two standard deviations about twelve — and twelve is roughly a third of a typical eligible pool,
which is an outage rather than an incident and would leave no unaffected traffic to judge against.
Six is defensible and unmeasured; five is measured, and measured is what the project takes.

The choice took the *top* of its band where `anom-014` took the *bottom* of its plateau, and the
asymmetry is deliberate rather than inconsistent. For the minimum duration every larger value on the
plateau had a measured cost — more true episodes discarded for no gain, since the false population
was already empty. For the floor a larger value inside the reliable band costs nothing measured and
buys margin toward the spread the detector actually has to clear. A parameter should be read from the
end of its range where the cost lies, and the two ends differ because the costs do.

**What the floor does not fix**, recorded so that the regeneration is not over-sold. The control
background is 14.4 findings per run with a standard deviation of 3.5, and a detector sees one run
without its control. The single run in the corpus that staged twelve aircraft cleared its control by
4.0 findings — about 1.1 standard deviations. Extrapolating the measured yield, an excess of one
standard deviation needs roughly seven staged aircraft and two standard deviations roughly fourteen.
**No reachable floor makes `anom-006` work by counting findings per run.** What `scn-007` does is
remove the empty answer key, which was making a fifth of the arm unscoreable by construction, and
give a zone-level rule enough co-located dropouts to concentrate. Whether that is enough for
`anom-006` to be built at all is a question for re-measurement after the regeneration, and it is
explicitly not settled by this item.

### The corpus is not one corpus, and a measurement of mine was taken across the join

Found while mapping the stored runs in order to plan the regeneration, and recorded because it is a
threat to the validity of figures already on the record as well as an error of my own.

The 240 stored runs were generated in twelve batches of twenty, and the generator changed underneath
them twice. The evidence is unambiguous once the runs are grouped by block:

| Block | Run length | Mean aircraft named on the answer key |
|---|---|---|
| ids 1-20 | **600 s** | 4.35 |
| ids 21-100 | 900 s | 4.75 - 5.20 |
| ids 121-220 | 900 s | **1.55 - 1.85** |

Two separate changes. The first twenty runs are 600 seconds where every later run is 900, so they
carry two thirds of the track observations - 22,470 against 33,779 for the same seeds regenerated
later. And runs 1-100 predate `scn-006`, the gate restricting staging to aircraft in flight, so their
answer keys name a mean of about five aircraft where later runs name fewer than two. Most of that
difference is aircraft that were parked, which `anom-010` correctly refuses to find, because an
aircraft on the ground stopped reporting when it was switched off.

That explains a structure that first looked like duplication. Twenty seeds appear twice within the
`aircraft-coverage-gap` arm, because runs 41-60 are runs 1-20 regenerated at the corrected length.
The arm is therefore **80 runs over 60 distinct seeds**, and any figure quoted "of 80" weights twenty
of them twice while also including twenty runs shorter than the rest.

**The error this caused was mine.** `scn-007`'s floor was measured over all 60 seed-matched pairs in
the corpus, which straddles the `scn-006` boundary. The high-count cells of that curve - six, nine,
eleven and twelve staged aircraft - can only be drawn from the pre-gate blocks, because the later
generator never stages that many. Those cells are therefore populated almost entirely by runs whose
staged aircraft were largely parked and undetectable by construction, which depresses the measured
excess exactly where the floor is being read. The measurement was restricted to the post-`scn-006`
region and re-run.

This is the same error the project has now made in three different costumes, and it is worth naming
once rather than three times: **a measurement is only evidence for a decision if it was taken on the
inputs the decision will actually face.** `anom-012`'s curve was first measured with the centre and
window taken from ground truth, which the rule never receives. `anom-005`'s gating trade-off was
first quoted over all runs of each type, when the ladder means the rule only ever sees some of them.
And here, a parameter for the *next* generator was read off runs made by two *previous* ones. In each
case the arithmetic was correct and the population was wrong.

`anom-014`'s minimum duration is unaffected, and that was checked rather than assumed. It measures RF
episodes, and neither change touched the RF grid: `scn-006` gates track staging only, and the shorter
block affects just twenty runs, all of them in the staged-no-RF group where a shorter stream can only
*reduce* the count of false episodes. The finding that every false episode is exactly one reading long
is a property of the noise distribution and does not depend on how many readings there were.

The consequence for the regeneration is a requirement rather than a caveat: **generate the whole
corpus with one generator, at one run length, and record the base seed and run count of every batch**
- which is what `scn-008` now exists to make possible.

### What the regeneration changed, reported in both directions

Corpus v2 is 300 runs in twelve batches of twenty, three base seeds recorded before generation, one
generator, one run length, every run carrying its batch provenance. Sixty seeds carry all five
scenario types, so every staged run has a same-seed `normal-baseline` twin - the same hour, the same
aircraft, nothing staged - which the first corpus never had and which its measurements had to
approximate with `rf-sensor-fault` runs.

**The two items did what they were specified to do, and the prediction matched the outcome exactly.**
`anom-014` was justified on a measurement saying every one of the 80 false episodes was a single
reading. On the regenerated corpus every one of the **17 spurious sensor faults** those episodes were
promoting is gone, across all five arms, with the catch rate unchanged at 60 of 60 on both staged
types. The false-episode population is now empty by construction, and no episode anywhere has zero
length, so `anom-012`'s zero-length refusal guards a case that can no longer arise. `scn-007` removed
the empty answer key entirely: 0 runs of 60 stage nothing, against 11 of 40 before.

The ladder is clean on every arm: 60 of 60 on all five, no spurious fires anywhere, and still no zone
receiving two answers. The `aircraft-coverage-gap` and `normal-baseline` arms are now **wholly**
silent rather than 75 of 80 and 19 of 20, and that difference is entirely the 17 spurious faults.

The track side strengthened substantially. The rate excess median went from 3.87 to **9.61** and the
proportion clearing the pre-registered threshold from 26 of 40 to **58 of 60**, with no unusable
windows where there had been seven. Corroboration improved from 7 zones of 61 to **18 of 60**.

**What did not change is the honest limitation.** Forty-one of sixty reported zones still have no
measurable track side. Two thirds is better than three quarters and it is the same statement: fusion
remains the radio evidence with an occasional corroborating note, and any write-up claiming
multi-source fusion must say so.

### A decision reversed by measurement, and the care the reversal needs

`anom-006` was closed as unbuildable on two findings, and the regeneration overturns one of them
while confirming the other.

The run-level finding held exactly as predicted. Staged runs now hold 16.9 track-gap findings against
their controls' 14.2, winning 57 of 60 pairs with 3 ties and no losses, and detected staged dropouts
rose from 1.07 to 3.05 per run. But the excess of 2.7 sits against a control spread of 3.3 - 0.8 of a
standard deviation - and a detector sees one run without its control, so it still cannot tell 17 from
14. That was written on the item *before* the regeneration, with the arithmetic that produced it, and
it is worth noting that a prediction recorded in advance and then confirmed is the only reason this
half can be reported without suspicion of hindsight.

The zone-level finding reversed. Scoring the best zone on a staged run against the best zone on its
own control was previously indistinguishable from a coin at every radius - 7:3, 5:4 and 4:2 at 20, 40
and 60 km. It is now **20:7, 14:8 and 10:5**, and at 20 km twenty wins against seven losses is about
one in fifty by sign test. The mechanism is visible in the other figures: five staged aircraft put
enough co-located dropouts in one place for a cluster to form, where 1.7 could not.

The care this needs is in what it does *not* establish, and it is the same distinction that has
caught this project before. A sign test over matched pairs says the staged zone **tends to** beat its
control. A detector has no control: it sees one run and must decide. Whether a threshold exists that
separates a staged zone from an unstaged one on a single run is a different question, and the figures
above are not evidence for it. The item is therefore recorded as *buildable to try*, not as *known
buildable*, with the instruction that the threshold measurement comes before any threshold is chosen.
Treating a matched-pair result as though it licensed a single-run threshold would be the same error
as reading `anom-012`'s truth-seeded curve as a production curve.

### A metric that was measuring the layout rather than the system

Recorded because it looked like the one regression in the regeneration and was not.

`rate_excess_window_source.py` reported a "centre error" - how far the detected zone centre sat from
the staged one - and it moved from a median of 0.0 km on v1 to 45.3 km on v2, with a maximum of
107.5 km. Those two numbers are exactly this layout's **minimum and median receiver separations**,
which is what gave it away. The metric compared the dismissed receiver against `sensors[0]`, the
first entry in the answer key's list, when an interference incident is staged on two or three
receivers and any of them is a correct centre. It was measuring which staged receiver happened to be
dismissed first, and v1's 0.0 was luck in list ordering rather than accuracy.

Measured as the distance to the *nearest* staged receiver - which is the question the label claims to
ask - it is **0.0 km on every run**, maximum 0.0. The detected centre always lands on a receiver the
answer key names.

The general form is worth keeping: a figure that is stable at a suspiciously round value, or that
matches a constant of the apparatus, should be checked against that constant before it is believed.
Here the "error" was a distance between two correct answers.

### A paired test reopened an item and a single-run test closed it again

The `anom-006` data-source rule was closed as unbuildable, reopened by the regeneration, and closed
again a day later by a measurement it had itself demanded. The sequence is worth recording in full
because the reopening was correct, the closure is correct, and the two are not in tension: they
answer different questions, and the item said so at the time.

The reopening rested on a paired comparison. Each staged coverage-gap run has a twin generated from
the same seed over the same corpus window with nothing staged, so the pair differs in exactly one
respect. Scoring the strongest cluster-proposed zone on each and asking which is worse gave twenty
wins against seven losses at a 20 km cluster radius, about one in fifty by sign test, where every
radius had previously been indistinguishable from a coin. The effect is real, and the amendment
reopening the item recorded it as *buildable to try* and explicitly not as *known to be buildable*,
with the reason attached: a sign test over matched pairs says the staged zone tends to beat its
control and says nothing about whether a threshold separates them on a single run, which is the
question a detector faces.

That distinction is the methodological content of this episode. A paired design is powerful
precisely because it cancels everything the two runs share — the seed, the window, the aircraft, the
local density of traffic — so it can resolve an effect far smaller than the variation between runs.
A detector inherits none of that cancellation. It sees one run and must answer against a fixed bar,
so it is exposed to exactly the variation the pairing removed. Two populations can therefore be
ordered reliably within pairs and overlap almost completely across runs, and this one does.

The measurement was pre-registered before it was run, with the populations, the operating-point rule
and the failure bar fixed in advance, and scored on a held-out base seed the threshold was not
chosen on. Corpus v2 came from three base seeds of a hundred runs each, so two were used to choose
an operating point and the third scored once. Without that split the threshold would have been read
off the same runs that produced the twenty-to-seven and the result would have been fitted to its own
evidence — the error `rate_excess_prereg.md` was written to avoid, in a place where it would have
been easy to repeat.

The best operating point that leaves the quiet arm silent is a 60 km cluster radius, a minimum zone
size of four findings and an excess threshold of 11.53, catching seven of forty coverage gaps on the
development seeds and three of twenty on the holdout, against a pre-registered bar of one in four.
The out-of-sample agreement is close — 0.17 against 0.15 — which matters for the strength of the
conclusion: this is a reliable measurement of a weak effect rather than a noisy measurement that
more data would resolve. Repeating it on more runs of the same corpus will not change it.

What closes the item is not the low sensitivity but its direction. At that operating point the rule
fires on six of twenty `gnss-degradation` runs against three of twenty coverage gaps — twice as
often on the arm it is not for as on the arm it is. That arm freezes reported staleness rather than
suppressing rows, so it genuinely perturbs the track side; the rule cannot tell the two
perturbations apart, and it is more sensitive to the wrong one. Because `anom-013` orders
`SENSOR-FAULT`, `SOURCE-GAP`, `FUSION-SPATIAL`, the data-source rule outranks the interference rule,
so a wrong firing does not merely add a finding — it can claim the zone before the interference rule
is offered it. Building this would risk the one arm the ladder decides correctly sixty times out of
sixty in order to catch a seventh of an arm nothing currently judges. Whether the zones in question
actually overlap was not measured, so the hazard is established and its magnitude is not; that is
recorded as a limitation rather than quietly asserted either way.

The mechanism behind the failure is the one predicted when the item was first closed, now visible
directly. The statistic saturates. At a minimum zone size of one, every arm reaches the same maximum
ratio of 198.78 and the medians differ by 0.6, because taking the maximum across a run's zones
selects whichever zone had the fewest findings to average over — `anom-012`'s smoothing constant
dominating a small sample. Separation only begins to appear at a size floor of four, by which point
a third of runs produce no qualifying zone at all. The best Youden's J anywhere on the development
sweep is 0.275, and it occurs at a quiet-arm false-alarm rate of 0.38 that `anom-008` forbids
outright; `anom-012` reported 0.23 to 0.40 on a curve this project already describes as weak.

Two structural facts fell out of the measurement and outlive the item. `ambiguous-mixed-evidence`
shares `aircraft-coverage-gap`'s `SUPPRESS` track mode, and `rf-sensor-fault` perturbs tracks not at
all, so at a shared seed the first pair and the second pair produce *identical* track findings —
verified by exact comparison, not by summary statistics. Any track-side figure quoting a hundred and
twenty negatives, or treating the ambiguous arm as independent evidence about a track-side rule, is
counting sixty seeds twice. The measurement that found this had itself been designed with the wrong
population table: it named an `rf-interference` arm this project does not have, and omitted the
ambiguous arm entirely. The error was caught by the arms producing byte-identical columns, which is
the kind of result that should never be read as a coincidence.

The honest outcome is therefore that the `aircraft-coverage-gap` arm has no rule, that its sixty
correct non-detections are correct only because nothing judges it, and that this must not be
reported as though the system had been tested on that arm. Both closures of this item reached the
same conclusion about what would change it: a generator change rather than a detector one. A
coverage gap has to become a zone-level event separable from a staleness freeze before any threshold
here is worth choosing.

### The first time every citation was checked, one in eleven pointed at nothing

`evb-002` requires that every item in an evidence bundle resolve to a stored observation, checked
against the database rather than asserted by the builder. It is the precondition for the grounding
check in the AI layer: verifying that a generated hypothesis cites something real is a
set-membership test against a resolved bundle, and has no computable answer against 20.7 million
observations.

The item was expected to be close to a formality. The detection layer had carried `evidence_refs`
since `db-008`, every rule populated them, and the coordinates had already been measured unique
across both corpora. Measuring what those references actually pointed at was therefore a
confirmation step, and it did not confirm.

Over 24 real bundles built from 40 runs, **91 of 1,021 cited coordinates resolved to zero rows** —
one citation in eleven. The misses were not scattered, which is what made them diagnosable: every
single one was the *start* of a `frozen_position` track finding, and every radio citation and every
`not_heard` citation resolved cleanly. A focused re-check over three runs put it at 48 of 48.

The cause is a distinction the finding model had collapsed. A detection finding carries two kinds of
time, and they are not the same kind:

| | What it is | Must a row exist at it? |
|---|---|---|
| The window (`started_at`, `ended_at`) | The rule's **conclusion** — when it believes the event began and ended | No |
| The reference | The rule's **evidence** — the reports it actually read | Yes, or it is not a reference |

The storable shape was built writing the window ends into the reference field, on the unexamined
assumption that the moment an event began is a moment something was recorded. For the coverage-gap
mechanism that holds, because its window ends *are* the reports either side of the silence. For the
frozen-position mechanism it cannot hold: that finding is raised from a report which arrives
carrying a stale position, and the rule reconstructs when the freeze began by subtracting the
staleness the report declares from the report's own arrival time. That instant is an inference. It
is also, by construction, the one moment in the entire window at which nothing was recorded — the
position had stopped updating, which is the whole content of the finding. The citation pointed at
the only place a citation could never land.

The fix keeps the window and adds the observed report times beside it, so the finding cites the
report that *showed* the stale position rather than the instant it infers from it. Moving the window
instead was considered and rejected: "when the position went stale" is the right answer to the
question the window asks, and replacing it with the first stale report's own timestamp would make
every frozen finding shorter than the event it describes, which would quietly change the
during-window counts the rate-excess rule computes.

Two things about this are worth carrying into the write-up beyond the defect itself.

**It was invisible to every check the project had.** The references were written, stored, covered by
tests, and survived a mutation pass. Nothing read them. A field that is produced and never consumed
is not tested by anything, however green the suite is, and this one sat that way across two corpora
and 240 runs before the first consumer arrived.

**A plausible test would have missed it.** A traceability test written over a coverage-gap finding
passes, because both of its ends are real rows. Two mechanisms produce the same shape of output,
only one of them can satisfy the constraint, and a fixture drawn from the wrong one proves nothing
about the other. This is the second time in the project that a test could not have failed — the
per-channel baseline test was rebuilt for the same reason — and the general form is now recorded:
a check is only as strong as the variety in what it is run against.

### Batching decided a deferred index question, and cost nothing to measure

The same measurement settled the open performance question the specification had deliberately
deferred. A single resolution had been measured at 64.7 ms, running as an index scan on the run and
then discarding 38,424 rows by filter, and whether that mattered depended entirely on how many
citations a bundle carries — which could not be known until the evidence list was composed.

It carries 26 at the median and 105 at the worst. One query per citation costs 194.5 ms per bundle
at the median and 748 ms at the worst; one query per coordinate shape costs **10.5 ms and 131.5 ms**,
because the row filter is paid once instead of once per reference. That is 18.6× at the median, and
it is the difference between a design decision and a schema change: the composite index that was
being considered would have bought the same constant factor, and batching buys it without altering
the schema at all. The index remains a candidate rather than a prerequisite.

The general point is worth one sentence in the methodology chapter. The first instinct on seeing
64.7 ms per lookup was to add an index, which is a change to stored structure that has to be
migrated, reasoned about and kept. The cheaper fix was to stop issuing the query 26 times.

### Two guards that make each other redundant, found by mutation rather than by reading

The mutation pass over this item killed 27 of 29, with both survivors equivalent. One of the two is
worth recording because of *why* it is equivalent rather than that it is.

Evidence items now declare whether they cite observations or state a judgement, and the resolver
skips the judgements. Removing that skip changes nothing — because the item constructor already
refuses a judgement that carries references, so a judgement reaching the resolver has nothing to
iterate. The two guards cover each other exactly.

That is an equivalent mutant today and a latent defect tomorrow: delete the constructor check and
the resolver's skip becomes load-bearing with no test on it, and nothing in the suite would say so.
It is recorded in the harness rather than in a comment, because a note saying "this mutant is
equivalent" is only useful where the next person is already looking.

The other four survivors of the first pass were genuine gaps, and all four were the same shape as
`evb-001`'s: the suite tested thoroughly what a correct lookup returns and barely tested what must
be *excluded*. Run scoping was written twice, once per coordinate shape, and only one of the two was
under test. Two refusals were asserted with a pattern that any failure message satisfies, so both
guards could be deleted with the suite still green. A refusal test that does not pin *which* refusal
it got is not testing the guard; it is testing that something went wrong.

### A safety property that was a convention, and the corpus it cost

On 19 September 2026 I destroyed the project's generated corpus — 540 scenario runs and 20.7 million
observations across two corpora — by supplying the application's own database as the test tier's
`TEST_DATABASE_URL`, on a hand-written command issued to avoid waiting for the target that
provisions a separate database. The database-tier fixture opens with `DROP SCHEMA public CASCADE`.
Every targeted test run I issued that afternoon dropped the corpus and rebuilt it empty, silently,
because from the fixture's point of view nothing unusual had happened.

The incident belongs in the write-up for a reason beyond honesty, which is that the codebase had
already identified this exact failure and written a defence against it. The test configuration
states that its variable is deliberately not the application's, so that a fixture which drops schema
can never be pointed at a live database, and concludes: *two variables make that impossible by
construction rather than by care.*

**That sentence is the finding.** Two variables do not make it impossible by construction. They make
it inconvenient. A property enforced by construction holds whatever anybody types, because the code
refuses; a property enforced by convention holds while everybody follows the convention, and the two
are indistinguishable from the inside right up to the moment they are not. The distinguishing test
is one question — *can I break this by typing something?* — and the defence had never been subjected
to it. What the project had was a well-reasoned, well-documented convention that described itself as
a construction.

The replacement, specified as `ops-004`, performs two checks before any drop: an identity check on
host, port and database, and a population count on the target. The second is the load-bearing one,
because the first compares spellings, and one database reached as `localhost` and as a container
hostname is two spellings of one disaster. The population check asks what the target is actually
holding and refuses when that exceeds what a fixture could have created — which is indifferent to
how the database was addressed.

### A guard that passed every test it had and did not work

The more useful half of the incident came afterwards. Having written the guard with ten unit tests,
all green, I pointed it deliberately at the real database expecting to watch it refuse — and instead
watched eighteen database-tier tests drop and rebuild the schema without a word.

The cause was local and instructive. The test suite carries an autouse fixture that replaces
`DATABASE_URL` with a deliberately unreachable address for every test, so that nothing can
accidentally acquire a live connection. A guard that reads the environment *at the moment it runs*
therefore compares its target against that placeholder, finds no match, and permits the drop. The
guard's own unit tests could not see this, because they called the comparison directly with two
URLs rather than exercising it through the fixture stack it actually lives in.

The general statement, which generalises well beyond this project: **a guard verified only against
its own unit tests has been verified against the author's model of the world, and that is the same
model that produced the defect.** A safety interlock has to be fired at the real hazard at least
once, deliberately, and watched. The fix — capturing the application's URL at import rather than at
call time — is trivial; noticing that it was needed cost nothing only because I happened to re-run
the fatal command as a check rather than trusting the green suite.

This pairs with the traceability defect found the same day, and the pairing is the point. There, a
field was written and stored and covered by tests for months and was wrong, because nothing read it.
Here, a check was written and tested and was inert, because nothing had triggered it. Both are the
same shape: **code that has never been exercised in the direction that matters is untested however
green the suite is**, and coverage counts execution rather than consequence.

### What a destroyed corpus does and does not do to a measurement

Worth stating precisely, because the instinct runs the wrong way. A figure recorded in a committed
log is a record of what was observed under stated conditions. The observation happened; deleting the
data afterwards does not retract it. What is lost is narrower and should be named as such: the
ability to **re-verify** a figure, and the ability to take any *new* measurement, until the corpus
is regenerated.

*No longer checkable* and *no longer true* are different claims, and only the first applies. Two
specific claims move into that category. The coordinate-uniqueness result was measured across both
corpora and v1 cannot be regenerated, so its "across two independently generated corpora" phrasing
now rests on its log alone. And the superseded measurements kept deliberately for the write-up cite
v1 runs by identifier, which will not resolve.

The asymmetry between the two corpora is itself the argument for the work that made it: corpus v2 is
recoverable because recording a batch's base seed on every run row was built as a specification item
after discovering that v1's seeds had been printed to a screen and never stored. That item is the
only reason 300 of the 540 lost runs can be reproduced, and the gap it was written to close is
exactly why the other 240 cannot. Regeneration was also measured at roughly four seconds a run —
about twenty minutes for the full corpus — a figure nobody had ever recorded, and one which changes
the cost of the incident from an unknown to an afternoon.


### One shape three generators must agree on, and the half of it that is easy to lose

The hypothesis layer has three producers planned — a deterministic template, a hosted model and a
local one — and the first thing built for it was not any of them. It was the object all three hand
back. That ordering is deliberate and it buys two things at once: the screen can render any
hypothesis without knowing which arm produced it, and the evaluation can compare them at all, since
a comparison across arms is only possible if the arms produce comparable things.

The design decision worth recording is that this schema is **a constraint on generation rather than
a description of it**. The hosted arm is handed the schema's JSON derivation and can only emit
conforming output, which means every guarantee has to survive the derivation. It is entirely
possible to write a model class whose Python-side tests all pass while its derived schema has
quietly widened — an enumeration becoming a free string is the obvious case, and it would lose the
guarantee at precisely the one boundary that depends on it, because the Python model never runs
during a constrained generation. Every guarantee is therefore asserted twice: once on the class and
once on the derived schema.

Two smaller choices carry more weight than their size suggests. A supporting-evidence item is a
**structured citation and never a sentence**, because prose cannot be resolved against an evidence
bundle; a prose citation does not make the automated grounding check awkward, it makes it
impossible. And a citation names **two** identifiers rather than one, because one does not identify:
the rate-excess rule defines no rule identity of its own and borrows the continuity rule's, so a
rate excess and a discontinuity arrive carrying the same rule identifier while making different
claims. That ambiguity had been recorded as owed since the bundle builder was specified; naming the
pair is where it was actually closed.

Nothing in the schema defaults. This is the typed-absence principle the evidence bundle already
applies to uncertainties, moved one layer up: a list that became empty because a generator omitted
it makes *weighed the alternatives and found none* and *never mentioned alternatives* arrive
identically. On top of that, the alternatives list carries a floor of one and the
evidence-against list deliberately does not — *nothing speaks against this* can be true, where
*nothing else could explain this* essentially cannot, and a system built to stop a fluent model
overclaiming must not accept the second.

Stated as a limitation rather than solved: this stops a number appearing in the confidence *field*
and cannot stop a generator writing "High (about 87% sure)" into the summary. The prohibition on
numeric confidence is a rendering rule as well as a schema rule, and the interface carries the other
half of it.

### A baseline that cannot flatter itself, and the two jobs that shape it

The template generator is the first thing in the system that turns an evidence bundle into an
explanation, and it has no model in it. It has two jobs, and almost every decision in it follows
from having both at once rather than either alone.

It is the **correctness fallback**: when a model arm returns something that fails validation or
fails the grounding check, this is what the analyst receives instead of an error. And it is the
**evaluation baseline**: the research question is whether a language model adds anything over an
honest mechanical summary of the same evidence, which has no answer without the honest mechanical
summary to compare against. The campaign scores it blind alongside the model arms.

The first job produces a hard constraint that is easy to state and easy to violate: a fallback that
shares a dependency with the thing whose failure summons it is not a fallback. If the hosted
provider is unreachable and the fallback needs an HTTP client to run, there is no fallback. This is
enforced from the import graph rather than promised in a comment — the test suite walks every module
reachable from the generator and refuses an HTTP client, a provider library or a model server
anywhere in the closure. That guard is a set intersection which is empty when it holds and empty
when it is broken, so it is paired with one test proving the walker reaches what it claims to and
one firing it at a module that genuinely does reach the network. The reasoning is the same as the
database guard's, and the lesson behind it is the same: a guard verified only against the case it is
meant to pass is verified against the author's model of the world.

The second job produces a subtler constraint. A baseline that overstates the evidence flatters
itself, and every comparison drawn against it moves by exactly that much, silently — a defect in a
model arm shows up as a bad hypothesis a human scorer can see, while a defect in the baseline shifts
the yardstick. So three decisions all push the same way.

**Confidence is inherited, never computed.** Every bundle already carries the deciding rule's own
confidence, and that value was measured and argued when the rule was built — the sensor-fault rule's
qualifies an attribution rather than a deviation, the fusion rule's has a floor of Medium the
aircraft side cannot breach. Recomputing it here would be a second scoring scheme, and a constant
expressed in two places is a constant that will eventually disagree with itself while both halves go
on working. It also means the template can never be more confident than the rule that produced its
evidence.

The join between the two vocabularies is where this nearly went wrong. The detection layer spells
confidence in lower case and the hypothesis schema demands initial capitals, so a pass-through
raises. The obvious repair — capitalise the first letter — is worse than the fault it fixes, because
it launders *any* word into something that looks valid and the failure then surfaces at the schema,
one layer too late to say which bundle caused it. The join is by enumeration member name instead, so
an unfamiliar word is refused at the point where the bundle is still in hand.

**A citation stands for a kind of evidence, not for an item.** A real bundle carries 34 evidence
items; one citation per item is complete and unreadable, and a baseline nobody can read is not a
baseline a scorer can grade. The grouping key is exactly the two-part citation identity the schema
defines, which is also the first place that choice becomes visible in behaviour rather than in
argument: grouping on the rule alone would collapse the rate excess and the discontinuities into one
citation making neither claim.

**Alternatives come from what the system already ruled out.** A claim the precedence ladder
suppressed *is* a competing conclusion, recorded as one — so those are the alternatives, and a
generator inventing alternatives while ignoring the ones the system itself set aside would be
disagreeing with its own evidence. Below those sits the standing pair, a broken receiver and
interference in the environment being each other's competing reading of the same radio evidence.
Last and unconditionally sits the caveat that deterministic rules can only choose among the
explanations they were written to distinguish. That last entry is the one a fluent generator omits,
and it also keeps the schema's floor satisfied by construction for a bundle type that does not exist
yet — which matters, because a fallback generator that raised on an unfamiliar claim would fail at
exactly the moment it is needed.

Uncertainties are copied verbatim and untruncated, in bundle order. They are already written out in
prose that carries which kind of not-knowing each one is, so copying composes nothing; and dropping
a tail to keep the text short would lose the distinction between *measured and found nothing* and
*never looked*, which is the material the layer exists to preserve.

### Four tests that passed for a reason other than the one they name

The mutation pass over the template generator killed 29 of 34 on its first run, and the four genuine
survivors turned out to have a single shape between them. None of the four tests was testing nothing;
each was passing for a reason other than the one its name claimed, and in every case the accidental
reason was invisible by reading.

A refusal test asserted that a damaged bundle raises and that the message names the claim type — and
the *mutant's* fallback path raised too, for a different reason, with a message that also names the
claim type. A count test compared two fixtures and asserted their citations differed, without
noticing that the fixtures differed in how many sources they spanned as well as how many findings,
so removing the count changed nothing measurable. An ordering test asserted a word appeared in the
last alternative, and the text that displaced it contains that word too. A differential test
compared the recommended action across two bundle types, where a single generic sentence still
differed between them because it interpolates the subject.

The repairs are worth recording as a pattern, because none of them was "assert harder". Each removed
the accidental route to the assertion: the refusal test now gives the fallback item a valid
confidence, so a generator that fell back would *succeed* rather than raise for another reason; the
ordering test now asserts that the final entry is one identical string across three different kinds
of bundle, which only the standing caveat can be; the action test strips each bundle's own subject
out before comparing, so what remains can only differ by what the generator says about that kind of
claim.

This is the third time in this project that a mutation pass has found gaps of a family rather than
scattered ones — the bundle builder's were all scoping rules, the traceability checker's were all
refusals asserted with a pattern any failure satisfies. The generalisation is that a suite tends to
be uniformly strong on the thing its author was thinking about and uniformly weak on the thing
they were not, so the survivors cluster.

### Two prose defects that only real bundles could find

The generator passed 37 unit tests and a mutation pass before it was run over the 41 evidence bundles
stored from real replayed hours. That run produced no refusals and no ungrounded citations, and it
found two defects anyway, both in the text a human being reads.

The first is trivial and instructive: the fusion rule's stated reason for a zone whose corroboration
could not be measured is three sentences long and ends in a full stop, so appending one produced a
doubled stop. Every fixture in the test suite ended without punctuation, because I wrote them.
Cosmetic in most contexts and not in this one — the output is read blind beside a language model's,
where punctuation a model would never produce reads as a quality difference rather than as a typo.

The second is a framing error. The summary introduced the verdict item's text with "the rule's own
conclusion", which is accurate for most bundles and wrong for the majority case here: on a zone whose
aircraft-side rate could not be measured, the rule's recorded reason is a *caveat about what could
not be established*, so the summary presented a statement of ignorance as a conclusion. Nothing was
invented and nothing was schema-invalid; the sentence simply pointed at the wrong thing. It now
reads "the rule states", which is true of whatever the rule recorded.

Both belong in the same category as the two defects the end-to-end bundle run found: properties of
what real data contains rather than of what the code says, and therefore invisible to any test whose
inputs the author chose.


### An interface written before its implementations, for the second time

The hypothesis layer will have three producers and two of them do not exist. The interface between
"explain this bundle" and "whatever produced the answer" was written now, before either model, and
the argument for that ordering is not aesthetic — the project has already run the experiment once.
The storage port was defined before the database existed, so when the database arrived it was a
**second implementation** rather than a second layer, and the port needed no change to accommodate
it. An interface written afterwards takes the shape of whichever implementation came first, and the
second one arrives needing its caller to know which is which.

Building it found an error in its own specification, which is the third time a phase has produced
that result and the reason the explain-then-specify step exists at all. The item said *Output: a
validated hypothesis*. That cannot be right. Both model arms must persist the model identifier, the
frozen parameters and the verbatim pre-parse response, and the retry path must know what was spent.
An interface returning only a hypothesis forces every arm to carry that provenance some other way —
which is precisely the provider-specific shape leaking into the seam, arriving by the back door
rather than through the signature the item was watching. The output is an envelope: the hypothesis,
which arm produced it, and for a model arm the record of the call.

### Moving a guarantee from where it is checked to where it is made

The first migration created the four reproducibility columns nullable, with a comment saying the
presence of three of them would be enforced "at the repository boundary, where the generator is
known". That was correct and it was later than necessary. The generator is known earlier — at the
moment the result object is constructed — so the guarantee moved there, expressed as a typed
absence: the model-call record may be omitted only when the generator is the template, and both
lies are refused at construction.

The difference is not stylistic. Under the original arrangement a hosted arm could build a result
with no raw response, carry it through the grounding check, and fail only at the write. Under this
one it cannot be built. And the failure the write-time check would have caught is the one whose
symptom appears last: a missing verbatim response is discovered when somebody tries to investigate a
grounding failure after a campaign, at which point the thing that would have explained it is the
thing that was never recorded.

The same principle produced a second, smaller decision. The configuration's model identifier carries
**no default**, so a caller must write an explicit absence to mean "this provider has no model". The
template legitimately has none and a model arm must have one, which is exactly the case where a
default lets a value nobody filled in look like a value somebody chose.

### A guard whose two failure directions are both real

The generation parameters are persisted verbatim beside every hypothesis. A credential held in them
is therefore written into the database once per row, and into every backup of it. So the
configuration refuses a parameter whose name looks like a credential.

What makes this worth recording is that the guard has two failure directions and the second is the
one that actually bites. Loosened, it lets a key through. **Tightened, it starts refusing
`max_tokens`** — which contains the word "token" and is precisely the parameter a campaign has to
freeze. A guard that blocks a legitimate parameter is a guard somebody switches off, and a switched-off
guard is worse than no guard, because the code still reads as though it were protected.

The rule is therefore substring matching for the unambiguous words and **exact matching** for the
short ones, over the key stripped of separators and lower-cased. Eleven credential spellings are
tested as refused and eight real generation parameters as accepted, and the mutation pass attacks
both directions: one mutant loosens the guard and another tightens it into refusing `max_tokens`.

### Two failure categories, because two fallbacks must not become one

The specification requires the availability fallback and the correctness fallback to remain distinct
paths in code and in the write-up. Availability fires when the provider cannot be reached and
responds by trying the other arm; correctness fires when a model answered and the answer cannot be
used, and responds with a bounded retry and then the template. Retrying elsewhere would be wrong for
the second — the request reached a model and the model's answer was the problem — and retrying the
same place would be wrong for the first.

That distinction has to live in the type system rather than in a comment, because a single exception
type makes the two indistinguishable to the code choosing between them. They are siblings under one
base, and two properties of the hierarchy are asserted rather than assumed: that neither is a
subclass of the other, and that a handler catching one does not catch the other.

A misconfiguration is deliberately in **neither**, and is not a generation failure at all. Caught by
an availability handler it would run a whole campaign against the wrong arm; caught by a correctness
handler it would produce mechanical output for every bundle while the run reported itself as hosted.
It has to stop the run. The template generator's own refusal is also in neither, for the opposite
reason: the template is what both fallbacks fall back *to*, so a handler responding to it by reaching
for the template would have nowhere to go.

### The extensibility claim, measured rather than asserted

The research question about extensibility is scheduled to be answered by adding a third source
adapter and recording what it cost. This item provides the same measurement on the generator side,
and it can be taken now because the template generator is registered as a real provider through the
real interface — which is also what stops the interface being hypothetical. An interface with one
implementation is a description of that implementation; this one had two the day it landed, and the
test suite drives a third through it that is deliberately unlike the template in every respect that
matters.

Measured over the source tree: **one provider costs one new module plus two lines in one existing
file, and nothing anywhere else.** The registry holds one import and one mapping entry per provider;
the interface imports no adapter; no caller can tell which generator it holds. The adapter itself is
27 lines of code against a 121-line interface.

The caveat is recorded with the figure rather than left for a reader to notice. The shipped adapter
wraps a local function and makes no network call, so its own size is a lower bound and a hosted
adapter will be several times larger. The number that carries the claim is the one *outside* the new
module, and that one does not depend on what the adapter does — which is the whole point of
measuring it there.

### A test that was too blunt, and the distinction that sharpened it

The suite's purity check began as "no module in the AI package may contain the literal name of a
provider", enforced over the syntax tree rather than the source text. It failed immediately, on the
interface module itself, because the enumeration of *which arm produced a result* spells its first
member `template`.

The blunt reading is that the test was wrong and should be relaxed. The useful reading is that two
things had been conflated. The stored generator kind is a value with a database check constraint on
it, written to a column and read back for every per-arm figure the campaign produces. The provider
name is a registry key that selects an adapter. They coincide today by convention, deliberately, so
that configuration reads naturally — but they are not the same thing, and a build could register two
hosted providers under different names while both stored the same kind.

So the check was **sharpened rather than relaxed**: what must not exist is a *comparison* against a
provider name, which is what branching on provider is however it is spelled. Reading the name to
resolve it, or to name it in an error message, is not that — and a check unable to tell those apart
would forbid the one module allowed to do the resolving. The sharpened version is fired at three
spellings of a real violation and at two legitimate uses, because a check that returns an empty list
when it holds returns an empty list when it is broken.


### A gate item deferred rather than decided, and the one argument that makes that safe

The plan gates the model arms behind a list of decisions to be settled before any model code is
written, on the stated grounds that each is cheap now and expensive-to-impossible after a campaign
has run. One of them — whether to build a local model arm alongside the hosted one — was deferred
instead, and the reasoning is worth recording because the general form of the argument is wrong and
the specific form is right.

The general form is wrong: "decide later" is what gates exist to prevent, and every other item on
that list genuinely cannot be revisited. Change the frozen generation parameters after scoring and
the arms are no longer comparable. Change the scoring corpus after seeing results and the campaign
is not blind. Change the model identifier mid-run and half the results came from something else.

The specific form is right because of one fact that distinguishes this item from all the others:
**the local arm is not scored.** The pre-registered instrument compares the hosted arm against the
template only. An arm that no scorer ever sees is outside the pre-registration, so adding it later
costs nothing in validity — the thing that makes the other items irreversible simply does not apply.

Two further observations reduced what a later cut would cost, and both became true only recently,
which is itself the argument for revisiting rather than deciding early. The offline demonstration
that was one of the local arm's justifications is already provided by the template generator, which
needs no network and produces a real explanation rather than a placeholder. And the two fallbacks —
availability and correctness — were at risk of merging if the local arm disappeared, because they
would then share a destination; but the provider-agnostic interface names the two failure
*categories* separately, so they keep different causes and different records even when both end at
the template. Only the destination coincides.

What remains genuinely at stake is a portability result: one JSON Schema enforced two ways, by a
hosted provider's constrained decoding and by a grammar compiled locally, producing an identical
guarantee. That is worth a time-boxed day if the hosted arm proves flaky and worth very little if it
does not, which is exactly the shape of decision that should wait for the measurement rather than
precede it.

The deferral is recorded on the two affected specification items themselves rather than in a session
note, following the precedent set when the reasoning document was made a precondition of the hosted
arm: a handoff is overwritten and a specification is not.


### A table designed before the thing it stores, and the window in which that is free to fix

The hypotheses table was created in the first migration, deliberately and for a good reason: its own
docstring records that a column for the model's verbatim response, added late and after an
evaluation campaign has run, is a campaign that has to be repeated. So the four columns that make a
result reproducible were placed before anything needed them.

What that revision could not anticipate is the field vocabulary the output schema settled four
phases later. Comparing the table against it turned up four problems, none of which is visible from
either artefact alone. Two fields of a hypothesis had no column at all — the summary an analyst reads
first, and the recommended action, which is the entire purpose of decision support. Three more had
columns under different names. A flag intended to record whether every claim had been checked
against the evidence was a plain boolean, and could not express *not yet checked*. And the analyst
review status accepted arbitrary text while the columns either side of it were both constrained to
their permitted values.

The decision worth recording is **renaming rather than mapping**. A translation layer between two
vocabularies is a permanent place for them to drift, and the drift is silent: content stored under
the wrong field's name complains to nobody and is discovered by reading output that makes no sense.
The rename was available because the table held zero rows, which it had since creation — and that
window closes permanently the moment anything is written. The same argument the first migration made
for placing the reproducibility columns early applies to fixing the rest of the table now.

The third problem is the same typed-absence principle this project has now applied at three separate
layers. A hypothesis is written before the grounding check examines it, so a two-valued flag forces
every new row to claim an outcome it does not have, and makes *failed the check* indistinguishable
from *was never checked*. The column became nullable and the three states became an enumeration in
code — not a `bool | None`, because that invites `if not passed:`, which is precisely the
substitution being prevented.

### Two writes that look the same and must behave oppositely

Findings are replaced per run per rule; hypotheses are appended. The asymmetry looks like an
inconsistency and is not.

A finding is derived. It is a pure function of stored observations and a seed, so regenerating it
produces the same finding, and keeping the old one beside the new one means every metric counts
both. Replacement is the only correct behaviour.

A model call is not derived. It consumed money, happened once, and produced one specific response
that cannot be reproduced by asking again — even at temperature zero, since the serving stack may
not be deterministic. Two calls are two facts. One bundle legitimately carries a model's hypothesis
and the mechanical one that replaced it after a grounding failure, and a retry is a second call that
the run-level budget has to count and the retry rate has to be computed from. Collapsing them would
destroy the only record of what the campaign actually did.

### A mutation harness that reported a perfect score without running a test

Found while writing the harness for this item, by checking how an existing one invoked the suite.
Two harnesses ran the containerised test target from the backend directory. That target lives at the
repository root; from the backend directory the build tool exits with *no rule to make target*,
which is a non-zero exit, which the harness read as "the tests failed", which it reported as a
killed mutant. Every mutant would have scored perfect without a single test having run.

Neither harness had a published figure, which is the only reason nothing has to be withdrawn — and
that is luck rather than process. The generalisable lesson is sharper than the bug: **a harness that
infers "the tests noticed" from a non-zero exit code cannot distinguish a failed test from a failed
invocation.** The two are the same signal. The new harness therefore parses the test summary and
reports a third outcome, inconclusive, when no summary appears at all.

This is the second defect found in the measurement instruments themselves rather than in the code
they measure, after the bytecode-cache collision that scored two genuinely-killed mutants as
survivors. Both share a shape worth stating: the instrument was trusted because it produced
plausible numbers, and plausible numbers are exactly what a broken instrument produces.


### A retry that cannot work, and the measurement already scheduled to prove it

`ai-007` says that a model response failing validation or the grounding check is retried a bounded
number of times before the template replaces it. The bound is the part the item argues for, and the
argument is sound: a retry loop, not the campaign, is the realistic route to an unexpected bill. What
the item does not say is whether a retry can succeed at all.

It cannot, if the provider is deterministic. The Phase 8.5 gate fixes **temperature 0 with a fixed
seed** for exactly the reason a pre-registered comparison needs — an arm whose parameters moved
mid-campaign is not an arm. A retry sends the *identical* request. A deterministic serving stack
returns the identical answer, which fails the identical check. The retry is then a second payment for
the same refusal, and the ceiling's only effect is to multiply the cost of a failure by N.

Three responses were available and two are worse than they look. Widening the port so a retry can
carry the refusal back to the model — "you cited a rule this bundle does not contain" — makes the
retried generation run under a *different prompt* from the scored one, which raises the question of
which of the two is the campaign's result and answers it badly whichever way it is answered. Removing
the retry entirely is defensible but forecloses a question that has not been asked yet. What was
chosen instead was to keep the mechanism, make the ceiling an argument the caller must supply, and
record that its value is **contingent on a measurement already in the plan**.

That measurement is §8's non-scored probe. It exists for an unrelated reason — N generations per
bundle contradicted temperature 0, and the coherent version of that measurement turned out to be
"is this provider actually deterministic at temperature 0?" rather than "how much does it vary?".
Many providers are not, because of batching and floating-point non-associativity in the serving
stack, which is the same class of problem this project has hit three times in its own results. The
probe was written as a threat-to-reproducibility check. It is also, without modification, the thing
that says whether `ai-007`'s retry is a mechanism or a tax.

So the recommended ceiling is **2 attempts, chosen and not measured** — the only figure in the module
with no corpus behind it, and labelled as such at the constant. The choice is defensible in the
interim because the arithmetic is asymmetric rather than because the value is right: being wrong
upwards costs at most about twenty extra calls against a 200-call run budget, while being wrong
downwards throws a recoverable hypothesis to the template and understates the model arm in a
comparison that cannot be re-run. The ceiling itself carries **no default**, on the same rule as
`GenerationConfig.model_id` — a retry count is a spending decision, and one made by omission is one
nobody chose.

*(Record here what the determinism probe returns, and whether the ceiling moved to 1 as a result.)*

### Two records of the same failure, one of which leaves no row

The phase 9 document found that `ai-007`'s two triggers are not two triggers for a schema-constrained
arm: `ai-004` uses the provider's native constrained decoding, so schema conformance is a
generation-time guarantee and a validation failure cannot happen in the ordinary course. If one
happens anyway, the provider broke its own constraint, which is a different and much more alarming
event than a model citing a rule that is not there. The amendment owed was that it be logged
distinctly rather than folded into a retry count.

Building it showed a second, sharper reason, which is about what survives rather than about alarm.
The two categories leave records of **different strength**.

| | Ungrounded | Malformed |
|---|---|---|
| What happened | it parsed, then cited something absent | nothing parsed |
| What survives | a full hypothesis, stored with grounding FAILED | a log line and a counted call |
| Rows in the database | one, beside the template that replaced it | **none** |

The ungrounded case is why `db-002` appends and never replaces: one bundle legitimately carries a
model hypothesis and the template that superseded it, and the pair *is* the record of what happened.
The malformed case has no such pair. Nothing became a hypothesis, so there is nothing for the write
path to take, and the only evidence that a model was asked and answered badly is whatever this layer
chose to keep. That makes the log line and the attempt trail load-bearing rather than diagnostic, and
it is a second argument for the amendment that has nothing to do with how alarming the event is.

The categories are distinguished **by origin rather than by a flag**: a refusal raised by the
generator is malformed, a refusal raised by the injected grounding check is ungrounded. Neither
`ai-004` nor `ai-008` has to know a shared enum exists, and — more to the point — neither can forget
to set it. A flag is a thing an adapter author omits under deadline; the position in the call stack
is not.

### Building one fallback against an interface that had already named the other

`ai-006` and `ai-007` end at the same destination for opposite reasons, which the phase 9 document
identified in advance as the distinction most likely to be collapsed by accident. `ai-003` responded
by making it *expressible*: `ProviderUnavailable` and `GenerationRefused` are siblings under one base,
neither a subclass of the other. What building `ai-007` added is that the distinction is now
*observed* — the correctness fallback catches one and is blind to the other, and the suite proves
this by scripting the answer a wrongly-retried arm would give, so an implementation that widened its
`except` clause to the shared parent returns a hypothesis where the test demands a raise.

That is a small illustration of a claim this project has now made three times and should make in the
write-up once: a distinction recorded in prose is a distinction that survives until the next person
writes an `except` clause, and a distinction recorded in the type system is one that has to be
deliberately removed. The same argument produced `evb-001`'s typed absences, `db-002`'s three-valued
grounding state, and here the pair of sibling exceptions. In each case the alternative — a comment, a
nullable boolean, one exception type — would pass every ordinary test and fail at the one moment the
distinction mattered.

The fallback is a **decorator over the port** rather than a branch inside each arm, which is what
keeps the two paths separate in code as well as in the write-up. `ai-004` and `ai-005` never learn
that retry exists. The grounding check and the replacement generator are both injected, following the
pattern `api-006`'s batch launcher and `ai-003`'s provider registry already established; importing
`ai-002` here would have made the correctness fallback a special case carved beside the port instead
of the port's own shape, and the suite could then never have driven it with anything else.

### A survivor that was not a weak test but a hidden defect

The mutation pass over `ai-007` killed 29 of 32 on its first run. Two of the three survivors were
the ordinary kind — a test whose name promised more than it checked. The third was not, and it is
worth separating because the distinction matters to how much weight a mutation score can carry.

The mutant widened the `except` clause around the **injected grounding check** from
`GenerationRefused` to `Exception`. It survived because nothing in the suite had ever made the check
raise anything else. Every test handed it either a refusal or a pass, which is what one writes when
one is thinking about the check's *verdicts*.

The consequence is not a missing test. It is that a defect *inside `ai-008`* — a `TypeError`, an
attribute error, any ordinary bug — would have been caught by the fallback and recorded as the
category `UNGROUNDED`. The model would then be blamed for the checker's fault, and the per-arm
ungrounded rate would rise. That rate is not a safety net whose false positives cost nothing; `ai-008`
states explicitly that the catch rate per arm is **a reportable evaluation result**. A checker with a
bug would produce a *finding* about model reliability, and the finding would be about the checker.

The behaviour was already correct — the implementation only ever caught `GenerationRefused`. What
was missing was any reason it had to stay that way. A property nothing asserts is a property that
changes the next time somebody widens a clause to make a traceback go away, and this is the third
time on this project that a mutation pass has found a correct behaviour resting on nothing:
`evb-002`'s two refusals asserted with a pattern any failure message satisfied, `ai-003`'s frozen
parameters asserted on the wrapper and not the mapping, and now this.

What separates this one from those is where the damage lands. The earlier two would have produced a
wrong *answer*. This one would have produced a wrong *measurement of how often the answers are
wrong* — a defect in the instrument rather than in the thing measured, which is the second time
Phase 9 has turned one up, after the two mutation harnesses that reported a perfect score without
running a test. Both share a shape worth naming in the write-up: **the instrument was trusted
because its output was plausible**, and nothing downstream of a plausible number asks where it came
from.

### Two ceilings that are not the same kind of thing, and a first draft that treated them as one

`ai-009` was written as "a configured maximum number of model calls **or** maximum spend for a run".
The "or" was wrong, and the reason is worth stating precisely because it is not a matter of taste.

| | Call count | Spend |
|---|---|---|
| When it can be checked | **before** the call | only **after** — cost is unknown until the answer returns |
| Is the number always available? | yes | **no** — `Usage.cost_usd` is `float \| None`, because a local model costs nothing per call |
| What it therefore is | a guard that refuses | a tripwire that notices |

So a spend ceiling fires one call late by construction, and on the local arm it enforces nothing at
all. A run configured with only the second has no working guard while appearing configured — which is
the failure mode the item permitted as written. Amended so that the call ceiling is required and the
spend ceiling is optional, late, and documented as possibly inert.

**The implementation then made exactly the error the amendment was about.** The first draft shared one
private `_enforce()` between the pre-flight check and the post-record check — tidy, and it looked like
removing a duplication. It meant the call ceiling was also evaluated *after* recording, so a ceiling of
N aborted on the call that **filled** the budget rather than the one that would exceed it, and only
N−1 calls ever returned. Seven tests caught it immediately.

The interesting part is not the off-by-one. It is that the argument for keeping the two checks apart
had already been written down, in the spec, that morning — and the code still merged them, because at
the level of "where does this `if` go" they look like the same statement about the same object. That
is worth recording as a small general finding: **a distinction argued in prose does not survive
contact with a refactor unless something about the structure resists it.** The method docstrings now
carry the reason, which is the weakest available form of resistance; the tests are the real one.

### An unpriced call is unmeasurable, not free

`ai-003` made `cost_usd` optional deliberately — a locally hosted model genuinely has no per-call
price, and that is an honest absence rather than a missing measurement. One layer up, that creates a
reporting problem the budget has to answer rather than dodge, because `eval-005` reports **actual
cost per arm as a result**.

Two wrong answers were available. Treating an unpriced call as `0.00` produces a total that is
arithmetically the same and epistemically different: it says the run spent that much, when what is
true is that it spent *at least* that much. Refusing unpriced calls outright would break the local arm
entirely. What the ledger does instead is count them, exclude them from the total, and expose
`cost_is_complete` — so `spent_usd` is a stated lower bound whenever it is one, and a figure quoted in
the write-up can say which it is.

The same shape as `evb-001`'s typed absences and `db-002`'s three-valued grounding state, now for the
third time in this project: *not measured* and *measured as zero* must not be the same value. What is
new here is that the consequence is a **reported figure** rather than an internal decision.

### Aborting is not degrading, and the tree says so

Two fallbacks already exist. `ai-006` catches an unreachable provider and tries elsewhere; `ai-007`
catches an unusable answer and retries, then falls back to the template. A budget exhaustion that was
shaped like either would not stop the run. It would be *handled* — the campaign would finish on
mechanical output while every row recorded the arm as hosted, and nothing would look wrong until the
per-arm figures were compared with something.

So `BudgetExceeded` sits outside the `GenerationError` tree, for the reason `ConfigurationError`
already sits outside it. That is now the second exception carved out on this argument, which makes it
a pattern worth naming in the write-up rather than a one-off: **the fallback tree is a statement about
what may be recovered from, and anything that must stop the run has to be outside it.** The test that
proves it is a composition test rather than a subclass check — the budget is wrapped inside a real
`CorrectnessFallback` and the exception is required to come out the other side.

The placement is load-bearing in the other direction too. The budget wraps the *arm* and the fallback
wraps the budget, because the ceiling exists for a retry loop: placed outside, it would count one call
per bundle and miss every retry, which is the only failure mode the item actually names.

### An equivalent mutant that settled which number the write-up may quote

The mutation pass over `ai-009` killed 30 of 33, and unusually for this project three of the five
first-pass survivors were **equivalent** rather than gaps. One of the three is worth more than the
score.

The mutant rewrote the spend total from *sum the priced calls* to *sum every call, reading an absent
price as `0.00`*. It survived, and it survives **necessarily**: the terms the original excludes are
exactly the terms that would have contributed zero. No test can separate them because there is
nothing to separate.

That is the useful part. The module's organising claim is that an unpriced call is *unmeasurable
rather than free* — and the pass demonstrates that the claim is **not carried by `spent_usd` at
all**. The arithmetic is identical under both readings. What separates them is entirely
`unpriced_calls` and `cost_is_complete`, which are companion properties rather than the headline
figure. A reader handed only the total cannot tell a run that spent £0.40 from one that spent £0.40
plus an unknown amount.

The consequence for the write-up is concrete rather than philosophical: **the figure to quote is
never the total on its own.** `eval-005` reports actual cost per arm as a result, and a cost quoted
without its completeness flag is a claim the system cannot support. That was an argument before the
pass and is a measurement after it.

### A cover that turned out to be one-directional

A second equivalent survivor looked like a case this project has recorded before — two guards making
each other redundant, found by mutation rather than by reading. The report's `calls` field is coerced
to a tuple in two places: once where the report is built from the live ledger, and once in the frozen
record's own `__post_init__`. Deleting the first changes nothing, because the second catches it.

But the pass killed the *other* mutant, and that asymmetry is the finding. Deleting the
`__post_init__` coercion **is** caught, because a test constructs a report from a list directly and
the build site never runs on that path. So the two are not mutually redundant, which is what the
source looks like: one is load-bearing and the other states an intent at the place where the sharing
would actually occur. Both are kept, and the distinction is now recorded rather than inferred.

Worth generalising carefully, because the earlier note on this topic overstated it. Mutation can show
that a guard is unreachable *through the paths the suite exercises*; it cannot show that two guards
are equivalent to one. Establishing that needs the mutants run in both directions, which is cheap and
was not previously being done.

### A test that could not be repaired by choosing better values

The third finding is smaller and is a note about test design. The abort message names both what the
run has spent and what it was allowed, and the test asserted the ceiling appeared in the message by
looking for its value. Deleting the ceiling from the message left the test green, because the **call
count** supplied the same digits.

The usual repair — pick values that cannot be confused — is unavailable here. The call ceiling fires
exactly when the count reaches it, so the two numbers are equal at the only moment the message is
ever produced. No choice of ceiling separates them. The assertion had to move from the value to the
**structure** of the message, pinning "ceiling of N" and "N model call" as distinct phrases.

That is a class of test worth recognising: where two quantities are equal by construction at the
point of observation, an assertion on the value cannot distinguish their sources, and the only
remaining evidence is the shape of the output.

### The measurement that closed the egress gate described a script, not the system

The Track 0 data-egress item was closed on a measurement: §4 of the phase 9 document records, field
by field, exactly what reaches a hosted provider. No aircraft position appears in a bundle at all; a
track citation carries a `dal-004` pseudonym and a timestamp. That measurement is what the clearance
conversation rested on and what NFR-405 is checked against.

Building `ai-004` showed that it was taken against a payload dictionary **hand-written inside
`measurements/corpus/bundle_payload.py`**, and that nothing in `app/` serialised a bundle at all. The
figure was therefore about a document that existed only inside a measurement script. Unless the
adapter happened to reproduce it exactly, the thing measured and the thing sent were different
documents that nobody would ever compare.

This is a different failure from the three instrument defects already recorded, and worth separating
from them. Those were instruments that produced a **wrong number**. This is an instrument that
produced a **right number about the wrong object** — and it is harder to notice, because every check
you could run on the measurement passes.

The repair is small and the principle is not: a measurement about what the system does must be taken
against the system. `app/ai/payload.py` is now the single definition, inside the package that lint,
mypy and the coverage gate see, and the measurement re-runs against that function rather than beside
it.

Writing the test that holds the payload to the bundle's own field list then immediately forced a
decision that had never been made. `EvidenceBundle` carries `scenario_run_id` and each evidence item
carries `observation_ids`, and **neither was in the measured payload** — not by decision, but because
the person writing the dictionary did not think of them. Both are our bookkeeping rather than
evidence, and a model cannot query the store, so excluding them is right. What matters is that it is
now an exclusion **argued for by name in a test** rather than an omission, and a third one has to be
argued for in the same place.

### A constrained schema carries structure, not quantity

`ai-004` uses the provider's native structured outputs, which is what lets `ai-001` describe schema
conformance as a *generation-time guarantee* rather than a post-hoc check. §10 drew a consequence
from that: for the hosted arm a validation failure cannot happen in the ordinary course, so if one
does it means the provider broke its own constraint — a more alarming event than an ungrounded
claim, and one that must be recorded separately rather than folded into a retry count.

The consequence is half right, and the half that fails is the half `ai-001` warned about. Strict mode
carries **structure** — field names, types, the three-value confidence enum, `additionalProperties:
false` — and does not carry **quantity**. `minLength` and `minItems` are not honoured, and `ai-001`
relies on both: at least one citation, no blank summary, at least one alternative explanation.

Those guarantees are not lost. They **move**, from generation time to parse time, and are enforced by
the Pydantic model as a refusal rather than as an impossibility. `ai-001` predicted the shape of this
exactly — "a derivation that widened confidence to a free string would pass every test written
against the Python model and lose the guarantee at the one boundary relying on it" — and the
difference is that this loss is loud rather than silent.

The correction to `ai-007` follows. A malformed refusal from the hosted arm is **not automatically
alarming**: an empty citation list is conformant to the provider and invalid to us, and will happen
in the ordinary course. A confidence outside the three is a different matter, because the enum *does*
survive. So the adapter sorts its refusals by which kind they are, and the alarming event keeps a
signal of its own instead of being buried under the expected one — which was §10's purpose, arrived
at by a different route than §10 imagined.

*(The exact set of unsupported keywords is provider documentation rather than something this
repository can verify without a real call. It is a named constant, every surviving guarantee is
re-asserted on the narrowed schema, and the gate's three-bundle smoke test is what confirms it.
Record the result of that smoke test here.)*

### An instrument that edits the code under test

Two mutation passes over `ai-004` were killed mid-run by the OOM killer. Each harness restores the
source in a `finally` block, and **a `finally` does not survive a `SIGKILL`** — so a mutated file was
left on disk, looking exactly like ordinary uncommitted work. One test was red and the cause was
three steps from anything that pointed at it.

The third instrument defect on this project, after the bytecode-cache collision and the two harnesses
that scored perfectly without running a test. The direction of the damage is what is new: those
produced a wrong figure, this one silently edited the thing being measured. An instrument that
corrupts its subject is worse than one that misreports it, because every subsequent measurement is
also wrong and nothing says so.

Investigating the cause produced a second finding that is more useful than the first. The reason a
pass was long enough to exhaust memory is that each mutant rebuilt the Docker image — and **that
rebuild was never necessary**. The backend service bind-mounts the source into the container, so an
edit is already visible and the rebuild was recreating an image whose source the mount overrides. Two
hours of continuous builds per pass, for nothing; a pass now does none and a mutant costs seconds.

The obvious risk in that change is the exact defect already recorded twice here: an assumption that
the harness is really testing what it thinks it is. So it is not assumed. The harness makes one
**deliberately broken edit before the run** and requires the suite to go red; if the sentinel
survives, it aborts and says no score from the run can be believed. That is a cheap general pattern
and it is what the two earlier harness defects were missing — neither would have survived a sentinel.

### The oracle has to be independent of the thing it validates

The grounding check is unusually cheap to validate, and the reason is that one of its inputs has a
known correct answer. The template generator copies every word it writes out of the evidence bundle,
so a template hypothesis is grounded by construction; running the check over one is therefore a test
whose result is known in advance, and **anything flagged there is a defect in the check rather than
in the generator**. This is why the check was built after the template rather than before it, and it
is the whole reason the build order in the phase document puts it late.

That argument holds only under a condition it is easy not to notice. Both modules group a citation on
the same `(rule_id, finding_type)` pair. Had they derived that key from shared code, a defect in it
would have been *invisible*: the template would emit wrongly-keyed citations, the check would resolve
wrongly-keyed citations, the two would agree perfectly, and the oracle would report a clean result
while both halves were wrong. An oracle that can share the fault it is testing for is not an oracle.

So the independence is asserted rather than promised — the import graph is walked and the check is
required not to reach the generator, the same instrument `ai-002` already uses for a different
independence one layer along. Two details make the guard worth its lines. It is a membership test
that comes back empty when it holds and empty when it is broken, so it is paired with a control
proving the walker reaches anything at all; and it is fired at a module that genuinely does import
the template, so the interlock is verified against a real positive rather than against the author's
model of the world. That is the same shape of mistake this repository recorded when a database guard
passed ten tests without ever firing.

### Matching is exact, and a near miss is recorded rather than forgiven

A model that writes `rf-noise` where the bundle says `RF-NOISE` has got the identifier wrong. The
tempting response is to normalise case and spacing before comparing, which repairs the obvious slips
and produces a check that looks more robust. It was rejected, because the catch rate is not a
diagnostic here — it is a **reported result**, one of the numbers the evaluation exists to produce.
Silently repairing model output would understate it, and understate it in a way that no later reader
could detect or correct.

Refusing the citation, however, leaves a different problem: a bare count of catches says nothing
about what went wrong, and the three things that can go wrong have very different implications. So
the refusal carries *why it nearly matched*, without that ever changing the verdict. Two kinds are
recorded. One is a difference of case or spacing only. The other is the interesting one — the rule
id is genuinely present in the bundle, but under a different finding type. That is precisely the
confusion the two-identifier citation was introduced to catch, since one rule in this system borrows
another's identity, and it is the most likely genuine model error rather than a hypothetical one.

The two are checked in a fixed order, and the order is load-bearing: both apply at once when a rule
carrying several finding types is cited with one of them miscapitalised, and reporting that as a rule
confusion rather than a spelling slip would invert what the measurement says. The general form of the
result is the point. "Fourteen catches" and "fourteen catches, eleven of them one rule's findings
mistaken for another's" are different findings, and only the second can be acted on.

### The arm has to be declared, because a hypothesis does not know what made it

The catch rate is reported per generator arm, and a `Hypothesis` object carries no record of which
arm produced it — deliberately, since the object is the one shape all three generators agree on. So
the arm is stated where the check is wired in, which is the same conclusion `ai-009` reached for a
refused model call: a call that failed has no result to read an arm from, and a hypothesis has no
field to read one from either.

The second decision in the same place is the one more likely to matter at write-up time. A catch rate
over zero checks is `None` and not `0.0`. *Never caught anything* and *never ran* must not arrive
identically, because the sentence "the check flagged nothing on the template arm" is true-looking in
exactly the case where that arm was never put through the check at all. This is `evb-001`'s typed
absence principle applied to a reported number rather than to evidence, and it is now the third place
in the project where the distinction has had to be built into a type rather than left to a
convention — after the three-valued grounding column and the completeness flag on a cost total.

Nothing in the module knows which arm is *expected* to pass. Encoding that the template cannot be
ungrounded would make the check's answer depend on who it was asked about, which is the one property
an instrument must not have — and it would destroy the oracle, since the oracle works precisely by
asking the check a question it could get wrong.

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

### Detectability varies fourfold with where the seed puts the zone, and the variation sits inside the batch

*Recorded 2026-09-12, before any detection rule exists and before any run has been scored. It is
written now because a threat identified after the analysis reads as an excuse, and because the
measurement that establishes it is available today.*

Deciding that every run replays a window of the corpus made the traffic inside a staged zone a
property of the evaluation rather than an implementation detail. Measured over the default
five-minute incident window (12:02:00–12:07:00 on 27 June 2022), which holds 10,759 rows and 410
distinct aircraft across the whole bounding box, the seven candidate zone centres carry markedly
different amounts of traffic within the default 60 km radius:

| Zone centre | Aircraft within 60 km | Staged at the default 8% |
|---|---|---|
| Schiphol | 75 | 6.0 |
| Lelystad | 74 | 5.9 |
| Rotterdam | 71 | 5.7 |
| Köln/Bonn | 28 | 2.2 |
| Düsseldorf | 28 | 2.2 |
| Weeze | 25 | 2.0 |
| Eindhoven | 18 | 1.4 |

Every centre carries enough traffic for a staging to be possible, which was the first question. The
second is the threat. A coverage-gap run centred on Eindhoven stages one or two aircraft; the same
run centred on Schiphol stages six. The spatial-clustering rule groups dropouts that occur close
together, so those two runs are not equally findable, and the difference is a property of where the
seed happened to place the zone rather than of the detector. Because the centre is seed-derived, the
variation sits *inside* a batch: aggregate recall over thirty runs would average a nearly
undetectable run together with an easy one and report one number for both.

Three responses were considered. Rejecting low-traffic seeds was rejected in turn, because it
complicates the claim that a batch reproduces from a single value in exchange for concealing
something that can simply be reported. The two taken are to record the number of aircraft actually
staged on each run's answer key — which the record already does, since it names them — and to report
recall broken down by that number alongside the aggregate. A floor on the affected count, rather than
a bare fraction of whatever traffic is present, is worth considering when the detectors exist and the
sensitivity of the clustering rule to the number of dropouts is known; it is noted here rather than
decided, because deciding it now would be tuning the generator against a detector nobody has written.

**Measured on the first real batch, 2026-09-12.** Twenty `aircraft-coverage-gap` runs over ten
simulated minutes each, from base seed 20220627, staged between **zero and eleven** aircraft — a mean
near four, and **one run that staged nothing at all**. That run is data-identical to a quiet control
while its row claims a scenario type, so it cannot contribute to recall, and counting it as a miss
would score the detector for an incident it was never shown. The batch report therefore carries the
count per run and a campaign-level line saying how many runs staged nothing, because a zero in row
four of thirty is not something anyone notices. The spread is the predicted fourfold variation
appearing in practice at the first opportunity, which is worth stating plainly: the threat was
written down in the morning and observed the same afternoon.

A second and independent limitation is recorded alongside it. The corpus is one recorded hour, and a
batch of thirty fifteen-minute runs draws thirty windows from inside it, so the windows overlap
heavily and the traffic across a batch is not thirty independent samples. Detection metrics aggregated
over a batch therefore carry less independent evidence than the run count suggests. This is a
consequence of the data — one hour was chosen deliberately, for licence and size reasons recorded
under Methodology — rather than of the generator, and no change to the generator would remove it.
Acquiring a second, non-adjacent hour would, and is the obvious mitigation if the result turns out to
be sensitive to it.

### What separates two runs of a batch is where the zone sits, not when the window opens

*Measured 2026-09-13 by reproducing base seed 20220627 offline — deriving the twenty seeds, windows
and zone centres, and counting the corpus directly — without touching the database. The derivation
reproduced the batch's own report row for row, including the staged-aircraft count of every run,
which is itself the first useful result: the answer key is a pure function of the base seed, so a
campaign can be audited from one number without being re-executed.*

The batch report shows each run's window, and reading it, the obvious conclusion is that time is what
makes twenty runs twenty different things. The measurement says otherwise. Across the twenty runs the
number of distinct aircraft present **in the fifteen-minute window** varies only between 514 and 550,
a spread of about seven per cent: the recorded hour is uniformly busy, and moving the window moves
which aircraft are present without much changing how many. The number present **inside the staged
zone** varies between 13 and 91, a spread of sevenfold, and tracks the seed-derived zone centre almost
exactly — the three Randstad receivers average 85 aircraft within the default 60 km radius, the four
southern and eastern ones between 19 and 33. Since the affected fraction is a flat 8%, the centre is
what decides whether a run stages eleven aircraft or none, and the window is close to irrelevant to
it.

The seed decides four things, and they are separable: the window, the zone centre, which aircraft in
that zone are staged on, and every one of the 5,040 radio readings. The third is easy to overlook and
is what keeps runs from duplicating each other when the first two collide. This batch contains the
demonstration by coincidence. Runs 16 and 17 open **two seconds apart**, share a zone centre, and
their zones contain **the same ninety aircraft** — identical sets, not merely equal counts. They stage
two aircraft and five aircraft respectively, **with no aircraft in common**; run 8 shares their centre
with a 97% window overlap, stages nine, and is disjoint from both. Three runs over the same traffic in
the same place at the same time are still three different incidents, because the target draw is keyed
on the run's own seed.

That result cuts both ways, and the second edge is a limitation. The batch's guarantee is that no two
runs share a window, and runs 16 and 17 satisfy it by two seconds: **distinct is not independent**.
Ten of the 190 pairs in this batch overlap by more than 90% of their duration and the mean pairwise
overlap is 30%, so the three near-duplicate runs are not an unlucky outlier but the expected
consequence of drawing twenty fifteen-minute windows from one recorded hour. The per-run window was
introduced to prevent exactly the same-centre-same-window case (`docs/qa.md` §53) and it does not
fully prevent it. The generator cannot: the windows do not fit. What the measurement changes is that
the limitation is now quantified rather than asserted — the earlier note said the windows "overlap
heavily", and the number is 30% mean overlap with three runs of twenty forming a correlated cluster.
Aggregated recall over such a batch carries less independent evidence than twenty suggests, and the
mitigation remains a second, non-adjacent hour of corpus rather than a change to the code.

### The five batches can share one base seed, and that makes every control a counterfactual

A campaign is five batches, one per scenario type, because the metrics are reported per type
(`eval-001`, FR-205). Whether those five share a base seed looked like an arbitrary choice and is not.

Per-run seeds are a function of the base seed and the run index alone, so five batches from one base
receive the same twenty seeds, and therefore the same twenty windows and the same twenty zone centres.
Every invented number is derived under a key that includes the cell it values — sensor, channel, tick
— and the injection is derived under a *separate* key, which is what lets an incident be added without
moving any reading it does not touch. The consequence is that a `normal-baseline` run and a scenario
run at the same seed are the same run apart from the injection.

**Measured 2026-09-13**: run 0 of base seed 20220627, emitted once as `normal-baseline` and once as
`gnss-degradation` at the same seed and window, differs in **60 of 5,040 cells — 1.2%** — which is
exactly the incident's footprint of two receivers by one channel by thirty ticks. The remaining 4,980
readings are identical values, and the replayed track rows are the same rows.

This makes the control arm a *matched* control rather than an independent sample of quiet: a false
alarm on the paired quiet run can be attributed to the background the scenario run also contained,
because it is the same background. The alternative — a different base seed per type — buys independent
placements across types at the cost of that attribution, and independence across types is not
something any planned metric needs, since no result compares one type's traffic with another's.

The decision is recorded here as a recommendation and left to `eval-001`, along with the open question
of whether the incident dials vary within a batch. Both have to be settled before the scoring campaign
is generated, because changing either afterwards invalidates every run already scored — and a seeded
campaign makes that cost visible rather than hiding it, which is the point of recording the reasoning
now.

### The mixed-evidence arm is a controlled comparison, not a duplicate

The first write-up of the `anom-006` closure recorded that `ambiguous-mixed-evidence` and
`rf-sensor-fault` produce the same reportable answer on all sixty runs each, and treated that purely
as a limitation. That is half the story, and the missing half reverses the practical conclusion: the
arm is doing real experimental work and should not be dropped.

The question is whether the two arms are identical in the *data* or only in the *output*. Measured
over all sixty shared seeds, they stage the same receiver, the same elevation above baseline and the
same incident window in sixty of sixty, and their RF observation streams are **identical byte for
byte in sixty of sixty**. The only staged difference is that the ambiguous arm additionally removes
five aircraft.

The pair therefore differs in exactly one variable, which is the definition of a controlled
comparison, and it changes what the identical verdict means. Both arms being decided
`possible_sensor_fault` sixty times out of sixty is not a null result reported for completeness; it
is a positive finding that **a simultaneous disturbance to the track picture does not perturb the RF
verdict**. The sensor-fault arm alone cannot establish that, having no disturbance to be immune to.
In the vocabulary of controls, the arm is a negative control living inside a positive one: the
positive half asks whether the fault can be found, and the negative half asks whether something
irrelevant can change the answer. Only this arm answers the second question, and deleting it would
delete the answer.

Three reporting consequences follow, and they are narrower than "keep it" or "drop it". The arm
should be reported as the immunity check, quoting the identical-stream figure so a reader can see
the comparison is controlled. It should *not* be reported as a third independent positive arm, since
its positive half duplicates the sensor-fault arm by construction. And it remains the right vehicle
for the conflict case `anom-013` has never been given — identical RF plus five removed aircraft is
precisely two claims over one place with everything else held constant — so what is missing there is
a second producing rule, not a different scenario design.

The measurement carries a methodological warning of its own, and it is the third instance of the same
fault in this project. Its first version reported four of sixty pairs differing, which read as
generator non-determinism and would have been a far more serious finding than the question being
asked. It was an artefact: the digest ordered rows by a payload key that does not exist, so every row
within a timestamp sorted equal and the order came from the heap. Diffing a "differing" pair showed
the same values in a different channel order. **A sort key that does not exist sorts everything equal
and raises no error**, which makes this failure silent in a way the `db-009` centroid case was not,
and a digest taken over rows needs an order that is provably total rather than merely plausible.

### Limitation: the aircraft-coverage-gap arm has no positive rule

Stated in full, in the order a write-up needs it, because this is the project's largest single
limitation and the one most likely to be challenged.

**Why the scenario was chosen.** `docs/research_scope.md` lists five scenario types and says of this
one and the sensor-fault one that they "are deliberately negative/discriminating cases — correctly
*not* claiming interference is a first-class evaluation result, not a non-event". The coverage gap
exists because the failure mode that matters operationally is not missing an incident but *inventing*
one: an analyst told that an area is being jammed, when in truth the receivers simply stopped hearing
aircraft there, has been actively misled. The arm was scoped to prove the system does not make that
mistake. `anom-006` was specified later, as the positive counterpart — the rule that would say *we
have stopped hearing aircraft here, and nobody is jamming* — giving the arm a claim of its own rather
than only a silence.

**What was done to test whether it would work.** Three measurements, in sequence, each answering the
objection to the last.

1. *Run-level counting* (`source_gap_ceiling.py`). Over 40 seed-matched pairs a coverage-gap run held
   a mean of 16.1 track discontinuities against its control's 15.1, and **never fewer** — 23 greater,
   17 tied, 0 lower. Zero discordant losses is overwhelming evidence the effect is real. It is also
   one finding in fifteen, and a detector has no control, so it cannot tell 16 from 15. The root
   cause was diagnosed as staging yield: 1.7 aircraft per run, with 11 of 40 staging none at all.
2. *Zone-level scoring* (`source_gap_zone_scoring.py`). If the staged dropouts sit *together*,
   clustering should concentrate them. Before the corpus was regenerated this scored at chance —
   7:3, 5:4, 4:2 at 20, 40 and 60 km. After `scn-007` put a floor of five staged aircraft under every
   run it scored **20 wins to 7** at 20 km, about one in fifty by sign test. That reopened the item.
3. *Single-run thresholding* (`source_gap_threshold_sweep.py`). The reopening amendment recorded, in
   advance, that a paired result is not the detector's question, and demanded this measurement before
   any threshold was chosen. Pre-registered populations, operating-point rule and failure bar; fitted
   on two base seeds; scored once on a third the threshold never saw.

**Why it does not work, and what proved it.** The third measurement. The best operating point leaving
`anom-008`'s quiet arm silent — 60 km cluster radius, minimum zone size four, excess threshold 11.53
— catches 7 of 40 coverage gaps on the development seeds and **3 of 20 on the holdout**, against a
pre-registered bar of one in four. Two further facts make this a closure rather than a near miss.

*It points the wrong way.* At that operating point the rule fires on **6 of 20 `gnss-degradation`
runs against 3 of 20 coverage gaps** — twice as often on the arm it is not for as on the arm it is.
That arm freezes reported staleness where this one suppresses rows; both are genuine track-side
perturbations and the statistic cannot tell them apart. Because `anom-013` orders `SENSOR-FAULT`,
`SOURCE-GAP`, `FUSION-SPATIAL`, the data-source rule *outranks* the interference rule, so a wrong
firing need not merely add a finding — it can claim the zone before the interference rule is offered
it. Building this would put the one arm the ladder decides correctly 60 times in 60 at risk in order
to catch a seventh of an arm nothing currently judges. Whether those zones would actually overlap was
not measured; the hazard is established and its magnitude is not.

*The ceiling is low everywhere, not only at the constraint.* The best Youden's J anywhere on the
development sweep is 0.275, and it occurs at a 0.38 quiet-arm false-alarm rate `anom-008` forbids
outright. `anom-012` reported 0.23 to 0.40 on a curve this project already calls weak.

*And the mechanism is visible.* The statistic saturates. At a minimum zone size of one, every arm
reaches the same maximum ratio of 198.78 with medians differing by 0.6, because taking the maximum
across a run's zones selects whichever zone had the fewest findings to average over — `anom-012`'s
smoothing constant dominating a small sample. Separation appears only at a size floor of four, by
which point a third of runs produce no qualifying zone at all.

Development and holdout sensitivities agree closely, 0.17 against 0.15, which is what makes the
conclusion strong rather than merely negative: this is a **reliable measurement of a weak effect**,
not a noisy measurement that more data would resolve. Re-running it over more of the same corpus
cannot change the answer.

**What could have been done to make it work, and why it was not done.** Five options were available.
None is impossible; each was declined for a stated reason, and the reasons are mostly cost and scope
rather than impossibility — which is the honest position for a prototype of this size.

| Option | Why not |
|---|---|
| Build it at a more sensitive operating point and accept the false alarms | Breaks `anom-008`, a passing item, and the arm it would falsely fire on is the one the system currently gets right. A rule with an adverse likelihood ratio is worse than no rule |
| Use the specification's own design — fire on dropouts wherever there is no co-located RF anomaly | Measured at the first closure: a quiet run genuinely holds about 15 discontinuities and no RF anomaly, so the rule would fire on **every** baseline run. The RF side is a *veto*, not a discriminator |
| Change the statistic — sum or count qualifying zones rather than take the maximum | The two ends of this family were both measured and both failed: the run-level aggregate at 0.8 standard deviations, the zone-level maximum here. Intermediate forms were not tried, and this is the cheapest untried option |
| Raise the staged fraction so a gap removes most aircraft in an area | With a mean eligible pool of 23.4 this is possible, and it changes what the scenario *means*: removing most aircraft over a region is an outage, not a coverage gap, and an easier problem than the one scoped. It would also require a third corpus generation and invalidate every detection figure measured on v2 |
| Change the generator so a coverage gap is a zone-level event by construction — suppress a contiguous area rather than a selected set of aircraft | **This is the option both closures identify as the one that would actually work**, and it is declined on cost, not on merit: a third regeneration, every figure in the detection chapter re-measured, and the `scn-007` floor re-derived. It is recorded as future work rather than attempted |

**What the limitation does and does not cost.** It does not cost the scenario. The arm still performs
the role `research_scope.md` assigned it: a discriminating negative case, scoring 60 of 60 correct
non-detections, and a *stronger* negative control than `normal-baseline` because it proves the RF
rules stay silent when something real is happening on the track side — a specificity test against
cross-modal leakage that a baseline with no disturbance at all cannot provide. What it costs is the
positive claim, and honesty about it: **the arm contributes no true positives to `eval-002`, its
correct non-detections are correct only because nothing judges it, and it must never be reported as
though the system had been tested on it.**

**A consequence that is easy to miss, and a correction to how it was first written up.** With
`anom-006` absent, `ambiguous-mixed-evidence` and `rf-sensor-fault` are **indistinguishable in the
detection layer's reportable output** — both are
decided `possible_sensor_fault` on all 60 runs. The only staged difference between them is the track
gap, `tracks.py` gives the ambiguous arm the same `SUPPRESS` mode as the coverage-gap arm, and
`fusion.py` consumes only `anom-007`'s *environmental* verdict, so on a single-receiver run the track
evidence never reaches a claim. The arm built to present `anom-013` with genuinely conflicting
evidence therefore cannot currently produce a second bid. The ladder's "no zone received two answers"
is a real result and must be read precisely: the ordering is proved by unit tests and a mutation
pass, but the corpus has never presented it with two rules bidding for one zone, because on every arm
exactly one rule bids. That is a limitation of the **ladder's** corpus evidence, not only of
`anom-006`.


### Threat to validity: the baseline's confidence is inherited, so one scoring dimension compares two mechanisms

The template generator takes its confidence from the deciding rule rather than assigning one, which
is the right engineering decision and introduces an asymmetry the scoring campaign has to declare.
The model arms will *choose* a confidence, and can therefore be miscalibrated — confident about thin
evidence, hedged about strong evidence — which is one of the things the rubric is designed to
detect. The template cannot be miscalibrated in that sense, because its confidence is not a judgement
it made. It is the rule's judgement, restated.

So on the calibration dimension the campaign is not comparing two answers to one question; it is
comparing an answer to a restatement. This does not invalidate the comparison — it is arguably the
point, since a model arm that cannot beat a restatement of the rule's own confidence has added
nothing on that dimension — but it must be stated in advance rather than discovered in the analysis,
and the second scorer should be told what the baseline's confidence *is* before scoring begins.
Recorded here rather than in the rubric because the rubric is pre-registered and may not be edited
after the campaign starts.

A second, smaller asymmetry came out of the run over real bundles. The template emits exactly four
citations on every one of the 41 stored bundles, because both bundle shapes the system currently
produces happen to carry four kinds of evidence. The baseline's *size* therefore does not vary with
the event, where a model arm's will. Any dimension of the rubric that rewards completeness or
concision is, for the baseline, being scored against a constant.

### Threat to validity: the grounding check resolves identifiers, not sentences

The grounding check verifies that each supporting citation names a kind of evidence the bundle
carries. It does not, and cannot, verify that the sentence the generator wrote beside that citation
is a true description of the finding it names. A model can correctly identify a real rate-excess
finding and then characterise it as showing something it does not show, and the check will pass it.

This matters for how the catch rate should be read. It is a lower bound on ungroundedness, not a
measure of it: it bounds the *fabricated reference* failure and says nothing about the
*misdescribed reference* one. The second is left to the blind human scoring, where it falls under the
rubric's evidence-fidelity dimension — which means a single scoring dimension carries the whole
weight of a failure mode the automated instrument cannot see, and the inter-rater agreement on that
dimension is correspondingly more load-bearing than on the others.

Stating the boundary precisely also settles what the check is evidence *for*. It supports the claim
that a constrained generator can be prevented from citing evidence that does not exist. It does not
support the broader claim that the generated explanations are grounded in the evidence, and the
write-up must not slide between the two.

*(Record the measured catch rate per arm here once the campaign runs, alongside the near-miss
breakdown — the proportion of catches that were one rule's findings mistaken for another's is what
says whether the failures were fabrication or confusion.)*
