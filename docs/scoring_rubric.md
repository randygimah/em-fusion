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
| `score_sheet.csv` | One row per hypothesis, with blank columns for your scores. |

Roughly **40 hypotheses, about 90 minutes**, plus a short calibration round first (below). Do it in
one or two sittings rather than five — consistency matters more than freshness.

You give **five numbers per hypothesis** in the first pass, and two more per hypothesis in a short
second pass at the end — around 280 entries in total. That sounds worse than it is: most of the time
goes on reading, and the scores themselves are quick once the anchors are familiar.

## How to score

For each hypothesis, give a **1 to 5** on each of five dimensions. The 1, 3, and 5 points are
described below; use 2 and 4 for anything in between.

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

- **Sampling unit is the evidence bundle**, not the scenario run. Roughly 5 bundles from each of the
  four anomalous scenario types, ~20 total, stratified so no type is absent. Normal-baseline runs
  produce no bundles by design (`anom-008`).
- **Two scored arms**: `hosted` and `template`. The `local` generator runs as an availability fallback
  and is **not** scored — see `thesis_notes.md`, "Scored arms".
- **One generation per arm per bundle** is scored. The N-generations-per-bundle grounding-variance
  measurement is separate, machine-computed, and does not enter the human corpus.
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

Implemented by `eval-004` (export) and `eval-006` (ingest and agreement).

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
