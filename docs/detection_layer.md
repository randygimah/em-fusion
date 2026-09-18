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

Over all 300 staged hours, **no event anywhere received two different answers** — and every arm is now decided correctly 60 times out of 60, with no spurious firing anywhere at all.

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

## What is blocking the rest

Since staging was restricted to aircraft actually in flight, a staged hour affects a mean of **1.7
aircraft**, and **11 of 40 affect none at all**. That single number is why:

- the coverage test cannot be built — its signal is 1 extra dropout against a background of 15;
- the aircraft evidence is unmeasurable in **47 of 61** reported zones.

**Both fixes are built, and the hours have been regenerated.** The corpus is now 300 hours made by
one generator, all the same length, with the seeds that produced them written down.

| Fix | What it does | What it actually changed |
|---|---|---|
| `anom-014` | A radio blip lasting one reading is not an event | **17 false alarms → 0**, across every arm, with real catches untouched |
| `scn-007` | At least five aircraft affected per hour | **0 hours now affect nobody**, against 11 in 40 before |

The aircraft side got materially stronger: the dropout-rate signal roughly doubled (median 3.87 →
9.61), and 58 of 60 interference hours now clear the bar where 26 of 40 did.

**The limitation that did not go away.** 41 of 60 reported places still have *no measurable aircraft
evidence at all* — better than 47 of 61, and the same sentence: this is the radio evidence with an
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
