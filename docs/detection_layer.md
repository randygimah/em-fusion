# The detection layer, on one page

*A standing orientation page. **Edited, never appended to** — unlike `docs/qa.md` (a growing record of
questions) and `docs/thesis_notes.md` (a growing record of decisions). If something here is out of
date, change it. Last true as of 18 September 2026, after the corpus was regenerated (300 runs, corpus v2).*

---

## The whole thing in three boxes

**Given replayed real aircraft data and invented radio data, both passed through one common model:
establish what normal looks like, find what deviated from it, and decide what the deviation means.**

| | What it does | State |
|---|---|---|
| **1. Normal** | Average and spread of each radio reading, **per receiver per channel**, over quiet hours only | Built — 56 cells |
| **2. Deviation** | Radio: a reading far enough past its own normal. Aircraft: an aircraft that stopped reporting | Both built |
| **3. Meaning** | Three possible answers, asked in a fixed order | Two of three built |

**Box 2's output is not reportable.** A quiet hour with nothing staged holds about 15 aircraft
dropouts and occasionally a radio blip. Deviation is raw material; box 3 is where a claim is made.

## Box 3: the ladder

One decision asked three times, in a declared order. The first test to claim an event wins, and no
later test is offered it.

| | Question | Answer | State |
|---|---|---|---|
| 1 | One receiver off-normal, neighbours normal? | that receiver is broken | **Built** — 60 of 60, and no longer fires anywhere it shouldn't |
| 2 | Aircraft dropouts, no radio anomaly nearby? | we are not hearing aircraft here | **Ruled out, twice** — the regeneration reopened it and the measurement closed it again |
| 3 | Several receivers off-normal together? | something is interfering | **Built** — 60 of 60 |

Over all 180 staged hours, **no event anywhere received two different answers** — and every arm is now decided correctly 60 times out of 60, with no spurious firing anywhere at all.

**These are not the figures this page carried until 29 September 2026, and the difference is the corpus rather than the rules.** The 300-hour corpus every detection figure had been measured on was destroyed on 19 September by a test run pointed at the live store. One wave of 100 hours was regenerated on 28 September for the AI campaign and the remaining two on 29 September, and the whole measurement protocol was re-run over the 300 that now exist. **Every conclusion replicated, and at the same corpus size the figures came back within a point or two of the ones that were lost** — on independently drawn seeds, which is replication rather than recovery.

**Read that precisely.** It is not evidence that the ordering resolves conflicts, because on every
arm of this corpus **exactly one test bids**. The broken-receiver test answers the single-receiver
hours, the interference test answers the multi-receiver ones, and they never contest the same event.
The hour-type built to create a real conflict — one receiver *and* an aircraft gap together — has its
aircraft half invisible, because test 2 was never built. The ordering is proved by unit tests; the
corpus has never exercised it.

### What the five hour-types actually give you

| Hour type | What is staged | What the system says | Role |
|---|---|---|---|
| Quiet baseline | nothing | silence, 60/60 | Negative control |
| One broken receiver | one receiver | *that receiver is broken*, 60/60 | **Positive** |
| Interference | several receivers | *something is interfering*, 60/60 | **Positive** |
| Mixed evidence | one receiver **+ an aircraft gap** | *that receiver is broken*, 60/60 | **Positive, with a negative inside it** — see below |
| Aircraft coverage gap | an aircraft gap only | silence, 60/60 | Negative control, **discriminating** |

So **three hour-types produce a finding and two produce silence.** The coverage-gap hours are not a
duplicate of the quiet ones: quiet hours prove the system stays silent when *nothing happens*, and
coverage-gap hours prove it stays silent when *something real happens that no radio test should
claim*. That is the stronger of the two guarantees, and it is the job this hour-type was scoped for
from the beginning.

**Neither of the two "duplicate-looking" hour-types is a duplicate.** The coverage-gap hours and the
quiet hours differ as above. The mixed hours and the broken-receiver hours look identical in output —
both *that receiver is broken*, 60/60 — but measured at every shared seed they stage the same
receiver, the same size of fault, the same window, and an **identical radio stream, byte for byte, in
60 of 60 pairs**. The single difference is that the mixed hour also removes five aircraft. So the
answer not changing is a result, not an absence of one: a simultaneous disturbance to the aircraft
picture does not perturb the radio verdict. The broken-receiver hours alone cannot show that, having
no disturbance to be immune to.

What the mixed hours **cannot** do yet is supply a second competing claim, because the aircraft half
of their evidence is exactly what the unbuilt test 2 would have read. That is why "no event received
two answers" is not evidence the ordering works.

## How much of what is staged does the aircraft side actually see?

Every rule above the aircraft-dropout detector assumes that when an hour disrupts an aircraft, the
detector notices. Measured against the answer key written at generation time — so an aircraft the
rule said nothing about is a miss, not an absence from the denominator — across all three waves and 900
staged aircraft:

| Hour type | Wave 1 | Wave 2 | Wave 3 | Combined |
|---|---|---|---|---|
| Navigation degradation | 83% | 81% | 83% | **82%** |
| Aircraft coverage gap | 64% | 59% | 53% | **59%** |
| Mixed evidence | 64% | 59% | 53% | **59%** |
| All | 70% | 66% | 63% | **67%** |

**The three waves separate two things a single figure hides.** The navigation arm replicates almost
exactly — 83, 81, 83 — so 82% is a property of that mechanism. The two suppression arms spread
eleven points, 64 down to 53, and that spread is the whole of the drift in the combined row. The
frozen-position mechanism is a stable detector; the not-heard mechanism varies with which aircraft a
wave happened to stage on. One wave would have reported either as a fact. The two suppression arms are identical in every column because the generator gives them the
same mode at a shared seed — one measurement reported twice, not two.

**Where the missing third goes is fully accounted for.** 136 aircraft on the ground, 132 below the
staleness threshold, 33 without a fresh enough contact — and **zero** lost to the interior-to-box
filter, zero absent from the hour, zero to an absence with no report bracketing it. Of the four
places suspected when the item was written, two account for everything and two for nothing. The
on-ground remainder is aircraft taking off or landing inside the window rather than aircraft parked
throughout, which is the detector being right.

## The other half: the hours where nothing was staged

A catch rate can be driven to 100% by alarming on everything, so none of the numbers above mean
anything until the layer can be shown to stay quiet on ordinary data. Over the 60 hours of this
corpus with nothing staged: **no hour shows the analyst anything — 0 of 60.**

Quote that with its coverage. The ladder has three answers and only two have tests behind them, so
the figure is **0 false positives over two of the three reportable types**. Read as three, it
credits the layer with the accuracy of the test that was never built.

**Why this needed code at all.** Zero is the answer we want and also the answer a broken pipeline
gives: detectors that ran and found nothing, detectors that never ran, detectors pointed at the
wrong hours, and a filter that discarded everything upstream all produce an identical empty result.
So the control is handed **an account of every detector by name** and refuses to grade an hour where
one is missing from it. A detector that found nothing has to say so. That refusal, not a count, is
what answers *did this detector look*.

**The two halves of the data behave oppositely, and that is a measurement rather than a rule.** The
aircraft tracks are real recordings and are full of ordinary dropouts, so a detector reporting none
of them has not looked. The radio grid is synthetic and a quiet hour has nothing in it, so reporting
nothing is correct. Each detector carries a band measured off the quiet hours and the comparison is
the same for all of them — there is no rule name anywhere in it.

| Detector | Band per quiet hour | Median | Its silence is |
|---|---|---|---|
| Radio deviation (synthetic) | 0–0 | 0 | correct |
| Aircraft dropout (replayed) | 8–22 | 15 | **a failure** |
| Dropout cluster (replayed) | 4–10 | 7 | **a failure** |
| Dropout rate excess | 0–0 | 0 | correct — it is never invoked on a quiet hour |

**What the bands cannot tell you.** They were measured on these 60 hours and are applied to them, so
all 60 are inside by construction and "all within background" is not a result. Wave 2 widened two of
the four bands and **wave 3 moved none of them**, which is the more useful fact: they have
converged, and the radio floor stayed at zero on two further independently seeded waves rather than
holding by accident on one. They are a tripwire
for a future corpus or a changed generator — the counts nothing else in the project quotes. And a
`[min, max]` band over n hours puts roughly 2/(n+1) of fresh same-distribution hours outside it,
about one in thirty here, so a single out-of-band hour later is not yet a signal; the proportion is.

## The one fact almost every decision descends from

> **The radio evidence is very strong. The aircraft evidence is weak.**
> 8 dB against a normal wobble of 1.5 dB — beyond five standard deviations — versus a Youden's J
> of about 0.3, where 0 is a coin flip.

| Decision | Why |
|---|---|
| Clustering dropouts was abandoned | Busy airspace always has dropouts close together |
| The rate excess replaced it | An attempt to get more out of the weak side |
| The broken-receiver test goes **first** | So the weak signal never arbitrates what the strong one settles |
| Interference does **not** require aircraft agreement | So the weak signal cannot veto the strong one |
| The coverage test stays unbuilt | It has **only** the weak signal. More aircraft per hour improved it and did not rescue it — see below |

The radio side has been comparatively simple throughout and has essentially just worked. Nearly all
the complexity is the aircraft side, and it is the complexity of extracting a reliable decision from
genuinely marginal evidence.

## Vocabulary that shows up in specs and in conversation

| Term | In one line |
|---|---|
| **Baseline** | What one receiver normally reads on one channel. Never pooled across channels. |
| **Episode** | A run of consecutive radio readings past the threshold. Not an incident — one incident can arrive as six episodes. Must last at least 10 s, or it is reported as too brief rather than as an event. |
| **Finding** | One aircraft's dropout. Raw material, never reported on its own. |
| **Zone** | A place and a window that a candidate answer occupies. One event, one zone. |
| **Claim** | One test's bid for a zone. The ladder resolves claims, not tests. |
| **Rate excess** | In *this* place, did dropouts happen more often during the window than they normally do *in that same place*? A place compared against itself. |
| **Corroboration** | What the aircraft side contributed — confirmed, measured-and-nothing-found, or could-not-measure. Deliberately three-valued. |
| **Youden's J** | Catch rate minus false-alarm rate. 0 = coin flip, 1 = perfect. Stops a good catch rate hiding an equally bad false-alarm rate. |
| **Recall** | Of the things that really happened, what fraction did we catch. Denominator is the real events only — not all hours. |
| **Matched control** | The same hour, same seed, same aircraft, with nothing staged. Lets a staged hour be compared against its own counterfactual. |
| **Seeded from truth** | A measurement that takes its centre and window from the answer key. Right for asking *does this signal exist*; invalid for choosing a parameter the rule will apply to detected inputs. |
| **Mutation testing** | Breaking the code on purpose, one change at a time, to check the tests notice. Evidence the tests are load-bearing. |
| **Detection latency** | How much of an event must elapse before the claiming rule has all the evidence it demands, in simulated time. **Not** how fast the code is -- detection is batch and there is no moment of noticing. Quantised to the 10 s sampling interval, signed, per claim. Definition fixed 2026-09-28 before any measurement code existed; see `anom-009` and `docs/qa.md` §104. |
| **Correct non-detection** | A required *behaviour*, not an absence: shown data with nothing staged, the layer must show the analyst nothing. Written as a behaviour because an empty result is also what a pipeline that never ran produces. |
| **Background band** | The minimum and maximum an intermediate detector produced across the quiet hours, with the number of hours recorded. Membership in it, not zero-ness, is what a quiet hour is judged on. |
| **Not exercised** | A third verdict beside clean and false-positive, for a ladder answer with no test behind it. Stops the absence of a test being reported as its accuracy. |
| **Decidable instant** | The earliest simulated moment a rule could honestly have committed. Declared by the rule itself, because only the rule knows what evidence it required. |

## What is blocking the rest

Since staging was restricted to aircraft actually in flight, a staged hour affects a mean of **1.7
aircraft**, and **11 of 40 affect none at all**. That single number is why:

- the coverage test cannot be built — its signal is 1 extra dropout against a background of 15;
- the aircraft evidence is unmeasurable in **41 of 60** reported zones.

**Both fixes are built, and the hours have been regenerated.** The corpus is now **300 hours** made by
one generator, all the same length, in three independently seeded waves with the seeds that produced
them written on every row. It is complete, and was finished deliberately **before** the evaluation
figures are computed rather than after.

| Fix | What it does | What it actually changed |
|---|---|---|
| `anom-014` | A radio blip lasting one reading is not an event | **17 false alarms → 0**, across every arm, with real catches untouched |
| `scn-007` | At least five aircraft affected per hour | **0 hours now affect nobody**, against 11 in 40 before |

The aircraft side got materially stronger: the dropout-rate signal roughly doubled (median 3.87 →
9.90), and 58 of 60 interference hours now clear the bar where 26 of 40 did.

**The limitation that did not go away.** 41 of 60 reported places still have *no measurable aircraft
evidence at all* — 68%, against 77% before the generator was repaired, and the same sentence: this is the radio evidence with an
occasional corroborating note, not two sources agreeing.

**The coverage test was tried again, and it fails.** It had been ruled out because scoring a place
on a staged hour against the same place on its control was a coin flip. With five aircraft affected
instead of 1.7 that scoring wins 20 times against 7 — which reopened it, but only as *worth trying*,
because comparing an hour against its own control is not the question a detector faces. A detector
sees one hour, with no control, and must decide against a fixed bar.

That measurement has now been taken, with the bar for success written down first and the answer
checked on a block of hours the bar was not chosen on. **It does not work, and it fails in the worst
available direction.**

| | |
|---|---|
| Coverage-gap hours caught | **3 of 20**, where 5 of 20 was the agreed minimum |
| Quiet hours falsely alarmed | 0 of 20 — the one thing it does get right |
| **Interference hours falsely alarmed** | **6 of 20 — twice the rate of the thing it is looking for** |

The last row is what closes it. A test that fires more often on interference than on the coverage
gaps it exists to find is not a weak detector, it is a misleading one — and because it sits *above*
the interference test in the ladder, a wrong answer there does not simply add noise, it can take the
event before the interference test is offered it. That would put the one arm the system currently
gets right 60 times out of 60 at risk, to catch a seventh of an arm nothing looks at today.

**Why it fails is worth keeping.** Score every place on an hour and take the worst, and the worst
score on a perfectly quiet hour is indistinguishable from the worst on a staged one — both reach the
same maximum, and their middles differ by half a per cent. Taking the worst of many places selects
whichever place had the fewest aircraft to average over, which is noise, not signal. Insisting on at
least four dropouts in a place suppresses that and is where the little separation there is appears —
by which point a third of hours no longer qualify at all.

**What would change it is the generator, not the detector.** A coverage gap has to become an event
with a *place*, distinguishable from an hour where aircraft positions merely go stale. Until then
this arm has no test, its 60-of-60 "correct" score is correct only because nothing looks at it, and
it must not be reported as though the system had been tested on it.

## The RF knowledge this project actually needs

All of it:

1. Noise rising **raises** measured power and **lowers** signal-to-noise ratio — same event, two views.
2. A real transmitter is never infinitely narrow; its energy **spills into adjacent channels**.
3. Interference has a **location** and reaches whatever is near it. A broken receiver does not.
4. Every receiver has its own normal, and normals differ between receivers.

Everything else has been measurement discipline, not radio physics.

## Where to look next

| Question | Document |
|---|---|
| What must this do? | `docs/requirements.md` |
| What is the binding definition of a capability? | `docs/spec.jsonl` |
| What does this term mean, and what did I get wrong about it? | `docs/qa.md` |
| Why was this decided, and what lost? | `docs/thesis_notes.md` |
| How do I explain this to someone outside the project? | the published progress note |
| Why is the phase built this way at all? | `docs/phase8_detection.md` (written before the build) |
| Where does the work stand right now? | `docs/handoff.md` |
