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
