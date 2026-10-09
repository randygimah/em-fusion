# Hypothesis Scoring Rubric

**Status: pre-registered.** This document is fixed before the evaluation campaign runs. The commit
hash of the last change made *before* the first scored item is generated is cited in the thesis, so
the instrument demonstrably predates the results. Any change after that point goes in the change log
at the foot of this file, with a reason — it does not silently overwrite what was scored against.

Part A is written to be handed to the second scorer as-is. Part B is method detail for the author and
the write-up; the scorer does not need it and should not be given it, because it describes what the
two systems are.

---

# Part A — Scorer's handout

## What you are doing

You are rating short written explanations produced by a decision-support prototype.

The prototype watches two data feeds — aircraft movement data and radio-sensor readings — and detects
when something deviates from normal. When it finds related deviations, it groups them into an
**evidence pack** and asks a generator to write a **hypothesis**: a short structured explanation of
what might be going on, for a human analyst to accept, reject, or challenge.

**Two different generators produce a hypothesis from the same evidence pack.** You will see both,
labelled only A and B. You will not be told which generator produced which, and the labels are
reshuffled on every item — A on one page has nothing to do with A on the next. Please don't try to
work it out; just rate what is in front of you.

Everything you will read is generated from synthetic and public data. Nothing is real, nothing is
operational, and there are no consequences to any judgement you make.

## What you'll be given

| File | What's in it |
|---|---|
| `hypotheses.md` | 20 evidence packs. Under each one, two hypotheses labelled A and B. |
| `score_sheet.xlsx` | One row per hypothesis. Pick your score from the dropdown in each column; hover a column heading to see that dimension's anchors without leaving the sheet. The **How to score** tab carries all of them in full, and the **Terms** tab carries the glossary. |

`hypotheses.md` opens with **Terms used in these packs** — every rule name, conclusion label and
piece of domain vocabulary you will meet, defined. The same list is a tab in the workbook, so it is
to hand whether you are reading or scoring. The definitions say what a word *refers to* and
deliberately not what it would *mean* if you saw it: judging that is the job, and a glossary that did
it for you would be answering the first question on the sheet.

Each evidence pack is laid out the same way: **what the detection rules concluded**, then **the
findings behind that conclusion**, then **what the rules could not determine**. Findings are grouped
by the rule that produced them, and every finding is still listed individually inside its group —
the grouping saves you re-reading near-identical lines, it is not a summary, and nothing has been
left out.

Roughly **40 hypotheses, about 90 minutes**, plus a short calibration round first (below). Do it in
one or two sittings rather than five — consistency matters more than freshness.

You give **five numbers per hypothesis** in the first pass, and two more per hypothesis in a short
second pass at the end — around 280 entries in total. That sounds worse than it is: most of the time
goes on reading, and the scores themselves are quick once the anchors are familiar.

## How to score

For each hypothesis, give a **1 to 5** on each of five dimensions. The 1, 3, and 5 points are
described below; use 2 and 4 for anything in between. The sheet's dropdowns offer all five.

Read the evidence pack first, then both hypotheses, then score each one.

### The five dimensions

**1. Evidence use** — does it actually reason from the evidence, or just repeat it?

| | |
|---|---|
| **1** | Repeats the findings back, or ignores them. No reasoning connects the evidence to the conclusion. |
| **3** | Uses the findings correctly, but in a generic way — the same words would fit many different situations. |
| **5** | Reasons from these specific findings, connects them to each other, and shows how they lead to the conclusion. |

**2. Uncertainty** — is it honest about what it doesn't know?

| | |
|---|---|
| **1** | No uncertainty stated, or a boilerplate disclaimer that would apply to any output whatsoever. |
| **3** | Names a real uncertainty, but doesn't say what difference it makes. |
| **5** | Names specific uncertainties and explains how each one weakens or qualifies the conclusion. |

**3. Alternative explanations** — does it offer genuine competing possibilities?

| | |
|---|---|
| **1** | None offered, or the "alternatives" are restatements of the main explanation. |
| **3** | Plausible alternatives listed, but nothing said about how you'd tell them apart. |
| **5** | Genuine competing explanations, with an indication of what evidence would distinguish them. |

**4. Recommended action** — could an analyst act on this?

| | |
|---|---|
| **1** | No action, or something so generic it carries no information ("investigate further"). |
| **3** | Sensible, but non-specific — right direction, no concrete step. |
| **5** | A specific next step, appropriate to this evidence, that an analyst could take immediately. |

**5. Overall usefulness** — would this help an analyst working under time pressure?

| | |
|---|---|
| **1** | Would waste time, or point in the wrong direction. |
| **3** | Mildly helpful. Saves a little work. |
| **5** | Would meaningfully speed up correct triage. |

This is your overall judgement, not an average of the other four. If it disagrees with them, that's
fine — leave it disagreeing.

### Then a second pass, at the end

Once you have finished all five dimensions for **every** item, you'll be given the correct answer for
each evidence pack — what the system was actually looking at. Go back through and add two more
judgements:

**6. Cause correctness** — `Correct` / `Partly correct` / `Incorrect`. Does the explanation identify
what was actually happening?

**7. Confidence calibration** — `Too low` / `About right` / `Too high`. Each hypothesis states a
confidence of Low, Medium, or High. Given how strong the evidence actually was, is that the right
level? A confident-sounding hypothesis built on weak or conflicting evidence should be marked
**Too high** even if it turned out to be correct.

The two passes are kept separate on purpose. Knowing the right answer changes how good an explanation
*feels*, so all the quality judgements are made before you see it.

## A worked example

Not from the real set — a practice item, so you can see the anchors applied.

### The evidence pack

```
Time window:   12:10–12:25
Area:          Sector A
Data mode:     Synthetic RF + open data replay

Findings:
  TRACK-GAP-001       Aircraft replay feed — position update rate dropped 62%
  RF-NOISE-002        RF sensors SNS-01, SNS-03 — elevated noise near GNSS L1
  FUSION-SPATIAL-003  Fusion engine — track discontinuities clustered within
                      20 km of the elevated-noise zone

Known uncertainties:
  RF data is synthetic
  The replay feed may contain its own gaps
```

### Hypothesis A

> **Track continuity deviation detected in Sector A** — Confidence: Medium
>
> A track continuity deviation has been detected in Sector A between 12:10 and 12:25.
>
> *Supporting evidence:* Aircraft position update rate dropped 62% (TRACK-GAP-001). RF sensors SNS-01
> and SNS-03 reported elevated noise near GNSS L1 (RF-NOISE-002). Track discontinuities were
> clustered within 20 km of the elevated-noise zone (FUSION-SPATIAL-003).
>
> *Uncertainty:* RF data is synthetic. The replay feed may contain gaps.
>
> *Alternatives:* Sensor fault. Data-source issue.
>
> *Recommended action:* Review the affected area.

### Hypothesis B

> **Possible localised GNSS interference affecting Sector A** — Confidence: Medium
>
> Elevated noise near GNSS L1 was reported by two separate sensors, and aircraft in the same area lost
> position-update reliability during the same window. Because GNSS L1 is the band aircraft depend on
> for positioning, noise on that band is a mechanism that would produce exactly this degradation —
> and the two effects are co-located within 20 km rather than merely simultaneous.
>
> *Supporting evidence:* Position update rate fell 62% during the window (TRACK-GAP-001). Two sensors,
> not one, reported the noise rise (RF-NOISE-002) — a single faulty sensor would not affect aircraft
> positioning. The discontinuities cluster within 20 km of the noise zone (FUSION-SPATIAL-003), so
> the two effects coincide in space as well as time.
>
> *Uncertainty:* The RF observations are synthetic, so this tests the detection logic rather than real
> interference. The replay feed can produce its own dropouts, and some of the 62% may be feed
> artefact rather than degradation — which is why the spatial correlation, not the drop alone, carries
> the argument.
>
> *Alternatives:* A data-feed outage would produce the track gaps without any RF signature — the
> presence of one argues against it. A sensor fault would show on one sensor, not two, and would not
> affect aircraft. Checking whether aircraft outside the 20 km zone were also degraded would separate
> these.
>
> *Recommended action:* Confirm whether track degradation stops at the 20 km boundary. If it extends
> well beyond, the interference explanation weakens and a feed problem becomes more likely.

### How these score, and why

| Dimension | A | B | Reasoning |
|---|---|---|---|
| Evidence use | **2** | **5** | A lists all three findings accurately but does nothing with them — no mechanism, no connection. B explains *why* L1 noise would degrade positioning and treats co-location as the load-bearing evidence. |
| Uncertainty | **1** | **5** | A copies the pack's uncertainties verbatim without consequence. B says what each one does to the conclusion, and concedes part of the 62% may be artefact. |
| Alternatives | **2** | **5** | A names two, undifferentiated. B names two *and* gives the discriminator for each, plus a check that would separate them. |
| Actionability | **1** | **5** | "Review the affected area" carries no information. B gives a concrete test with a stated interpretation either way. |
| Overall usefulness | **2** | **5** | A tells the analyst what they already saw. B advances the reasoning and hands over a next step. |

Note that **A is not wrong.** Every claim it makes is accurate and every rule ID is real. It scores
low because accuracy is not the same as usefulness — which is the whole point of the exercise, and
the reason these dimensions exist rather than a single correctness check.

Note also that **both said Medium**, and Medium is defensible here — the evidence is suggestive rather
than conclusive. In the second pass both would score `About right` on calibration. A hypothesis that
had said **High** on this evidence would be marked `Too high`, however well argued.

## Four things to hold to

**Ignore writing quality.** Polish, fluency, and tone are not being measured. A clumsily worded
hypothesis that reasons well should score higher than a smooth one that doesn't. If you catch
yourself rewarding style, stop and re-read for substance.

**Score each one on its own.** Not "better than the other one" — against the descriptions above. Both
can score 5. Both can score 1.

**Don't go back and adjust for consistency.** If item 14 makes you feel differently about item 3,
leave item 3 alone. Drift is expected and is handled in the analysis; retrofitting is not.

**Use the whole scale.** If nothing ever scores 1 or 5, the scores can't distinguish anything.

## Calibration round

Before the real scoring, we'll both independently score the **same five items**, then compare and
talk through any gaps. This isn't a test — it's to make sure we're reading the anchors the same way.
Those five are discarded and not counted in the results.

## If you get stuck

- **The evidence pack doesn't make sense to you.** Score the hypothesis on whether it reasons well
  from what's in front of it. You don't need domain knowledge to judge whether an argument follows.
- **A dimension doesn't apply.** Score it 1. A missing section is a low score, not a blank.
- **The two hypotheses under one pack look the same, or very nearly.** That happens, and it is
  expected rather than a mistake in the pack. Score each one on its own terms exactly as you would
  any other item, including giving them the same numbers if that is your honest reading.
- **You genuinely can't decide between two adjacent scores.** Take the lower one and move on. Don't
  spend more than about two minutes on any single hypothesis.

---

# Part B — Method notes (author only)

## Why these five dimensions

Each maps to one field of the hypothesis output schema and to a claim the thesis makes:

| Dimension | Schema field | Claim it tests |
|---|---|---|
| Evidence use | `supporting_evidence` | The gap the automated grounding check cannot close — see below |
| Uncertainty | `evidence_against_or_uncertainty` | Explainability NFR: uncertainty is surfaced, not hidden |
| Alternatives | `alternative_explanations` | The automation-bias mitigation claimed in the proposal's ethics section |
| Actionability | `recommended_human_action` | Decision support is actually supporting a decision |
| Overall usefulness | whole | Guards against a hypothesis that scores well part-by-part and poorly as a whole |

**Why a human is needed at all.** After the grounding check, every hypothesis reaching a scorer is
100% schema-valid and 100% grounded, on both arms — that is what constrained decoding plus a grounding
gate mean. Neither metric can separate the arms; both score perfectly by construction. The grounding
check proves a cited rule ID *exists in the evidence pack*; it cannot establish that the finding was
used *meaningfully*. Dimension 1 is precisely that gap, and it is why RQ3 needs human judgement rather
than more automation. See `docs/qa.md` Q7.

**Why fluency is excluded.** It would inflate the frontier-model arm for reasons unrelated to the
constrained-generation architecture under study, contaminating the headline comparison. Excluded by
design, not by oversight, and stated as such in the write-up.

**Why five rather than one overall score.** "Is this hypothesis any good" is unanswerable as a single
number, and collapsing to one would destroy the finding the study is after. If the hosted arm beats
the template on alternatives but not on actionability, that is a result about *where* constrained
generation helps; as a single score it is just a number that moved. The schema mapping above is what
makes each dimension a test of a specific claim rather than a general impression.

**What "dimension" means here, and what it does not.** The term is rating-scale vocabulary: one
independent axis of judgement, scored on its own, with worded anchors at 1, 3 and 5. It carries none
of its data-science sense — there is no feature space, no dimensionality reduction, and **no
orthogonality claim**. The five are expected to correlate with one another, and dimension 5 is
explicitly not an average of the other four. Each is reported separately and **no composite score is
computed from them at any point**; the averaging in the adjudication rule below is across *raters* on
a single dimension, never across dimensions. Worth pre-empting in the Evaluation chapter, because
"five dimensions" invites the wrong reading from a technical examiner. See `docs/qa.md` Q47.

## Corpus and procedure

- **Sampling unit is the evidence bundle**, not the scenario run. **Stratified on bundle kind**: 10
  `possible_interference_zone` and 10 `possible_sensor_fault`, 20 in total. Stratifying on scenario
  type, as this document originally said, cannot be done — five scenario types produce **two** kinds
  of bundle, and one of the four anomalous types produces none at all. Two consequences the scorer's
  experience depends on: interference bundles are about 3.2x larger, so balancing by kind gives
  roughly equal numbers of long and short documents where balancing by type would have given
  three-quarters short ones; and the producing scenario type is recorded on every sampled bundle, so
  the two fault-producing types can still be compared afterwards without having been stratified on.
  Normal-baseline runs produce no bundles by design (`anom-008`). The sample is a **seeded draw,
  committed before the first scored generation is made**, recording the chosen bundles, the seed and
  the rule: an instrument that predates the results is worth nothing if the corpus does not.
- **Two scored arms**: `hosted` and `template`. The `local` generator runs as an availability fallback
  and is **not** scored — see `thesis_notes.md`, "Scored arms".
- **One generation per arm per bundle is scored, and for the model arm three are generated.** The
  scored one is the **first**, fixed in advance and never substituted — including when it is a
  generation the model failed and the template answered, which is what the model arm *delivered* on
  that bundle. The other two are never scored and become the machine-computed grounding-variance
  population instead. The template baseline is generated once, and that is safe for the reason the
  model arm's single generation was not: there is no provider in it. See the change log for why this
  changed.
- 20 bundles × 2 arms = **40 items**, each scored independently by **both raters** — full
  double-scoring, no partial overlap. Every reported number is therefore double-scored and there is
  no unscored remainder to defend. See `docs/qa.md` Q8 for why this beat the larger-corpus,
  partial-overlap alternative.
- **Paired within bundle**: both arms are scored against the same evidence, so bundle difficulty
  cancels out of the arm difference.

**Scoring volume per rater**, which is what the participant is actually being asked for and the figure
quoted to them:

```
5 dimensions × 40 items   = 200   pass 1, ordinal 1-5
2 judgements × 40 items   =  80   pass 2, categorical
                            ---
                            280   values from one rater
```

Plus 25 discarded values from the five-item calibration round. The 280 figure is stated in the
participant information sheet in `docs/ethics_form_answers.md` and on the ethics approval form; if the
corpus size or the dimension count ever changes, those three places change together or the consent is
no longer informed by the right number.

## Analysis

- **Reported per arm**: mean and distribution for each of the five dimensions, plus the
  hosted-minus-template difference per dimension. Pass-2 judgements reported as counts.
- **Inter-rater agreement**: quadratic-weighted Cohen's κ per dimension, over the full corpus.
  Quadratic weighting because a 1-vs-5 disagreement matters more than 3-vs-4, and unweighted κ treats
  them identically.
- **Adjudication rule, fixed in advance**: the two scores are averaged for analysis. Where they differ
  by **2 or more**, the item is flagged, discussed, and both raters may revise — with the pre- and
  post-discussion scores retained and κ reported on the pre-discussion set. Choosing this rule after
  inspecting the disagreements would be a validity problem.
- **Partial coverage** is reported as partial coverage. If one rater completes only part of the
  corpus, κ is computed over the double-scored subset and the remainder reported separately — never
  silently averaged as though both had scored it.

Implemented by `eval-004` (the sample, drawn first; then the export), `ai-012` (the campaign that generates what is exported) and `eval-006` (ingest and agreement).

## Threats to validity, recorded in advance

**Blinding is imperfect.** Template output is stylistically distinctive and a rater may well recognise
it. Mitigation is limited to normalising the rendering: identical field order, identical formatting,
no markdown flourishes, arm key held in a separate file, A/B labels reshuffled per item. The template
is deliberately **not** made to imitate model prose, because that would corrupt the baseline it exists
to provide. The residual threat is stated in the Evaluation chapter rather than claimed away.

**The author is one of the two raters,** and is not blind to the project's hypotheses even when blind
to the arm. This is the reason for pre-registration, for full double-scoring by an independent second
rater, and for reporting κ. It remains a limitation and is named as one.

**Small N.** 20 bundles is a small corpus, chosen against the binding constraint of the second rater's
time. The paired within-bundle design recovers much of the lost power, but the comparison supports a
directional finding rather than a precise effect size, and should be reported that way.

**Single scenario family.** All bundles come from one synthetic generator over one geographic extract.
Results describe this prototype on this data, not hypothesis generation in general.

## Change log

| Date | Change | Reason |
|---|---|---|
| 2026-08-07 | Initial version. | Pre-registration before any campaign run. |
| 2026-09-06 | Part B: added "Why five rather than one overall score" and "What 'dimension' means here, and what it does not". | Clarification only — no dimension, anchor, or procedure altered. Records that the term is rating-scale vocabulary carrying no orthogonality claim, that the five are expected to correlate, and that no composite is computed across them. Pre-empts a misreading by a technical examiner. See `docs/qa.md` Q47. |
| 2026-09-06 | Part B: added the per-rater scoring volume (280 values) to "Corpus and procedure"; Part A: added the same figure to "What you'll be given". | Derived from figures already fixed (40 items × 5 dimensions, plus 40 × 2 pass-2 judgements), not a change to them. Needed because the number is quoted to the participant in the information sheet and on the ethics approval form, and the three must agree. Makes explicit that the five calibration items sit **outside** the 40 — previously only implied by 20 bundles × 2 arms = 40. |
| 2026-09-27 | Part B: the sample is stratified on **bundle kind** (10 interference, 10 fault) rather than on scenario type, and is a seeded draw committed before the first scored generation. | **A correction, recorded late.** The five-per-type stratification is unsatisfiable on the built system: five scenario types produce two kinds of bundle, `aircraft-coverage-gap` produces none because its rule was closed as unbuildable on this corpus, and `normal-baseline` produces none by design. The backlog recorded this on 2026-09-21 and this document was not told, so for six days the instrument cited as fixed-in-advance described a corpus that could not exist. Corpus size (20), item count (40) and scoring volume (280) are unchanged, so nothing quoted to the participant moves. The commitment that the sample is drawn and committed *before* any scored generation is new here and was previously implicit. |
| 2026-09-27 | Part B: the model arm generates **three** times per bundle, of which the **first** is scored and is never substituted; the two others become the grounding-variance population. Part A: a new stuck-point telling the scorer that two hypotheses under one pack may be identical. | **A change to the method, not a clarification, and the premise it rested on was measured false.** N was fixed at 1 because temperature 0 with a fixed seed returns the identical answer, so a second generation could add nothing to score. The first real requests measured otherwise: 4 of 5 comparable repeated pairs differed, one changing the set of cited evidence kinds and one losing an alternative's falsification test between runs. A single generation is therefore one draw from a distribution rather than the model's answer, and the observed variation falls on dimensions 1 and 3 — the two this study is most about. Scoring all three was rejected because it takes one rater from 280 values to 840 and from about 90 minutes to four and a half hours: 280 is quoted in the participant information sheet and on the ethics approval form, so raising it is a re-consent and not a configuration change. **The human corpus is therefore unchanged at 40 items and 280 values.** The scored generation is the first, declared here rather than chosen later, because substituting a different one when the first fell back would delete every fallback from the scored corpus and flatter the arm under test. The Part A note follows from that rule: a fallback item and the template baseline for the same pack carry the same text. Both entries are committed before any scored generation is made. |
| 2026-09-28 | Part A: the scoring pack's **presentation** changed — the evidence packs are restructured and the score sheet is a workbook rather than a CSV. No dimension, anchor, scale, item count or procedure is altered. | **A change to the instrument's presentation, argued for rather than made quietly, and available only because no marking has happened yet.** Both raters have scored nothing; the second is unavailable until mid-October, so no value collected under the old presentation exists to be invalidated. Four faults, one of them not cosmetic. The pack was emitted as space-aligned plain text into a `.md` file, so any renderer reflowed nineteen findings into a single paragraph and collapsed the alignment the layout depended on — it was legible only in a raw editor. The findings **did not name the sensor or aircraft they came from**, while the hypotheses above them cite `RF-06:4` by name, so *evidence use* — the first of the five dimensions — was being scored against a pack the citation could not be checked against. Repeated findings and repeated uncertainties were printed verbatim, nine and three times over. And the bundle's own conclusion sat tenth of nineteen rather than leading. The restructure groups findings on the `(rule_id, finding_type)` pair already used everywhere else in the system, **lists every finding individually inside its group**, and de-duplicates uncertainties with a count. The grouping constraint is deliberate and is the one risk in the change: a pack that *summarised* its own findings would do part of the work dimension 1 scores, deflating the measured difference between the arms in the direction that flatters the weaker one. It therefore removes scan cost and no information — two facts it in fact **exposed** on the first rebuilt pack were an even 4/4 split of the RF deviations across the two sensors, and one aircraft dropping out twice inside one window, both previously invisible. The workbook adds validated dropdowns over the full 1–5 scale, the anchors on the sheet itself, and locked identifier columns; the arm key remains a separate file. Threat to validity, recorded: the blinding argument now has to cover two marker artefacts rather than one, so the arm-vocabulary scan was extended to the workbook's cells, headings, sheet names, notes **and document properties** — a leak in the last of those would sit in the file and never appear on screen. |
| 2026-09-28 | No change to Part A or B; recorded because it was nearly one. The scoring workbook's dropdown was built offering **1/3/5 only**. | **Caught and corrected before any scoring.** The reasoning was that those are the three points carrying worded anchors, which is true and is not what the rubric says: Part A says *"use 2 and 4 for anything in between"*. A sheet refusing a 4 refuses a value this instrument invites, and because the analysis reports **quadratic-weighted** κ — computed across the scale actually used — narrowing the scale would have been a silent change to the pre-registered analysis wearing the appearance of a stricter form. The unit test asserted the author's assumption rather than this document and was green throughout. Recorded here rather than only in the commit, because the failure mode — a pre-registered instrument re-implemented from memory in a second artefact — is the one this change log exists to make visible. |
| 2026-09-28 | Part A: the evidence packs are restructured a **second** time, and the reasoning given for the first restructure is **withdrawn and replaced**. No dimension, anchor, scale, item count or procedure is altered. | **The first rebuild was valid Markdown and still unreadable, and its stated constraint was wrong in direction.** Read by a person, the rebuilt pack was still a wall: fourteen table rows repeating *power_dbm deviated by X dB at its peak* and fourteen repeating *reporting from this aircraft broke during the window* carry one sentence and N values between them, and the sentence is what the eye must re-read. Six known uncertainties differing only in which receiver they named survived exact de-duplication and filled six lines with one fact. The pack now **factors the shared text**: a group states its common sentence once and each row keeps only what differs, gathered under its source; where the wording is byte-identical the group becomes one sentence and a list of sources; uncertainties factor the same way within a kind. Nothing is removed — one pack went from roughly thirty-five lines to fifteen with every value intact, and the change *exposed* two aircraft that had dropped out twice each, invisible among identical lines. **The withdrawn claim.** The previous entry justified the "group but never summarise" constraint on the grounds that a summarising pack would flatter the weaker arm and narrow the measured difference. That is backwards. The template baseline's own citations *are* summaries, so a pack that summarises makes the baseline read as pure restatement and scores it **lower**, widening the gap — while also lowering the model arm for the same reason. The net effect is not predictable in advance, which is a better argument for the constraint than the one given, not a worse one: the pack must not be in that business at all. **The constraint that replaces it is mechanical and tested rather than judged by eye: the pack re-organises values and computes none.** Every measurement rendered must appear verbatim in a finding, an uncertainty, or the bundle's own metadata; a count of items the pack itself lists is the only arithmetic permitted, because a reader could count them and a marker checking "nine aircraft" against the pack needs to. No minimum, maximum, mean, range, ratio or total may be introduced. The same conditions that made the first restructure safe still hold: **no marking has happened**, both raters having scored nothing. |
| 2026-09-28 | Part A: a **glossary** is added to the pack — a terms section at the head of `hypotheses.md` and a matching tab in the workbook. No dimension, anchor, scale, item count or procedure is altered. | **Added so a scorer in flow does not have to stop and ask.** The packs use `track_rate_excess`, `smoothing constant`, `nominal`, `disc`, `power_dbm` and `corroborate` without defining any of them, and a rater meeting those for the first time either interrupts the session or guesses — the second being worse, because a guess is invisible in the returned sheet. Two placements rather than one: the prose document is where the evidence is read and the workbook is what is open while a score is entered, and a glossary only in the other file is exactly the interruption it exists to remove. **The constraint, which is what makes this safe.** A definition states what a term *denotes* and never what it *implies*. "One aircraft's position reports stopping for longer than the gap the rule allows" is a definition; "…which can indicate interference in the area" is the causal link that *evidence use* exists to test in pass one and *cause correctness* exists to test again in pass two. Handing that over in the reference material would move part of the instrument somewhere nobody would think to look for it — the same failure as a summarising evidence pack, in its most dangerous form, because reasoning in prose does not look like a computation and so does not trip the "computes no new number" guard. It is enforced by a named list of causal connectives that no entry may contain, asserted over every definition rather than over whichever ones a fixture happens to render, and fired at a real violation to prove the guard bites. Only terms actually present in the exported pack are listed, and a citation key with no definition is **refused** rather than quietly omitted, since a missing entry leaves the page looking complete while a marker meets an undefined rule nineteen packs from the end. The same conditions hold as for the two previous presentation changes: **no marking has happened.** |
| 2026-10-09 | No change to Part A or B; recorded because the instrument promised an artefact that did not exist, and three facts about pass two follow from building it late. An **answer sheet** (`answer_sheet.md`) is added to the scoring pack. | **The promised answer was never built.** Part A says that once pass one is finished the rater is "given the correct answer for each evidence pack". Nothing in the backlog produced it, and the first rater, having finished pass one, found only the arm key. **It is rendered after scoring began, from definitions fixed before the campaign.** The correct answer is one sentence per scenario type, taken from `scn-002`'s definition of that type (the mixed type's carries its words verbatim: *the correct hypothesis is that they cannot be distinguished*), so nothing is judged pack by pack by an author who has by then read every explanation. Each section also states what was staged, copied from the run's record, and whether the pack's conclusion is about the staged incident at all (a staged receiver named and an overlapping window); all twenty are. It names neither label and passed the same arm-vocabulary scan as the marker's other files. No pass-one file was regenerated: every other file in the pack is byte-identical. **The first rater saw the arm key between passes.** It sat in the same folder as the pack. Pass one is unaffected; that rater's pass-two judgements are made knowing the arm, and are reported as such. The second rater must be handed the pack without the key. **On the five mixed-evidence packs the answer rests on evidence the pack does not contain.** Their staged aircraft dropout never reaches the evidence pack, because the sensor-fault verdict stops the aircraft side being consulted (each pack says so in its own uncertainties). Judged strictly, cause correctness on those ten items measures the detection layer's inability to represent *cannot be distinguished* for that scenario, not either arm's reasoning. The answer is not softened after the fact; cause correctness is reported separately for those five packs, and confidence calibration, judged against the pack's own evidence, is unaffected. Both arms face the same answer on each pack, so the paired comparison is not biased by it. |
