# The evaluation harness, on one page

*A standing orientation page for Phase 11, the counterpart to `docs/detection_layer.md`. **Edited,
never appended to** — if a figure here goes stale, change it in place. Last true as of 28 September
2026, after the scored campaign ran and the scoring pack was rebuilt.*

---

## The whole thing in one sentence

> **The detection layer decides what happened. The AI layer writes an explanation of it. The
> evaluation harness is how we find out whether that explanation is any good — and it has to answer
> that without taking the explainer's word for anything.**

Everything below is in service of one comparison: an explanation written by a hosted language model,
against an explanation written by a deterministic template, **over the identical evidence**, judged
by people who are not told which is which.

## Why it is hard, in three sentences

An explanation can be fluent and wrong. It can cite a rule that never ran, or cite a rule that ran
and misdescribe what it found. And the person best placed to notice is also the person whose time we
are trying to save — so if checking the explanation costs as much as doing the work, the system has
achieved nothing.

That splits the measurement in two, and **the split is the design**:

| | What it asks | Who answers | What it cannot see |
|---|---|---|---|
| **Automated grounding check** | Does every citation point at something that exists? | Code, on every generation | Whether the sentence attached to a real citation is *true* |
| **Blind human scoring** | Is the explanation actually useful? | Two people, not told which arm wrote what | Anything it does not have time to read |

The first is cheap, exhaustive and shallow. The second is expensive, tiny and deep. Neither is
sufficient and the project claims neither is.

## The pipeline

```mermaid
flowchart TD
    B["Evidence bundle<br/><i>one event, its findings,<br/>and what could not be measured</i>"]

    B --> S["<b>Sampling</b><br/>draw 20 bundles from a seed<br/><i>committed before anything is asked</i>"]

    S --> C["<b>Campaign</b><br/>ask each arm, per bundle"]

    C --> H1["Hosted model<br/>3 generations each"]
    C --> H2["Template<br/>1 generation each"]

    H1 --> G["<b>Grounding check</b><br/>does every citation resolve<br/>against this bundle?"]
    H2 --> G

    G --> DB[("Stored hypotheses<br/><i>every generation, every verdict,<br/>the verbatim response</i>")]

    DB --> ST["<b>Statistics</b><br/>per arm, never pooled"]
    DB --> PK["<b>Scoring pack</b><br/>generation 1 only,<br/>A/B reshuffled per bundle"]

    PK --> MK["Two markers,<br/>independently"]
    MK --> IR["<b>Agreement + adjudication</b><br/><i>not yet built</i>"]

    ST --> R["The result"]
    IR -.-> R

    style IR stroke-dasharray: 5 5
    style B fill:#1f3a5f,color:#fff
    style R fill:#1f3a5f,color:#fff
```

The dashed box is the only unbuilt part, and it is waiting on people rather than on code — see
**What is not built** below.

## The three arms, and the two fallbacks

There are three possible explanation writers and **two entirely separate reasons** one might be
swapped for another. Keeping those two reasons apart is one of the load-bearing design decisions in
the whole project, because merging them would make the results uninterpretable.

```mermaid
flowchart LR
    A["Ask the<br/>hosted model"] -->|"answers"| OK["Delivered"]
    A -->|"provider is down,<br/>rate-limited, unreachable"| L["Local model<br/><i>deferred, not built</i>"]
    A -->|"answer is malformed,<br/>or cites something<br/>that does not exist"| T["Template"]
    L --> OK
    T --> OK

    style L stroke-dasharray: 5 5
```

| Fallback | Trigger | What it means |
|---|---|---|
| **Availability** | The provider did not answer | Nothing is wrong with the answer, because there is no answer |
| **Correctness** | The answer came back unusable | Something *is* wrong with the answer, and that is a finding |

Retrying a **correctness** failure on a different model would be answering a different question.
Retrying an **availability** failure is just trying again. One exception type for both would make the
code unable to tell them apart, and the write-up unable to report them separately.

The **template arm is not scaffolding.** It is permanent, and it does two jobs at once:

1. It is what the analyst receives when a model answer fails the grounding check.
2. It is the **evaluation baseline** — the honest mechanical account of the same bundle, which is the
   only thing that turns "the model wrote something plausible" into a measurable claim.

It also acts as the **oracle for the grounding check itself.** A template hypothesis is built
entirely out of the bundle, so it is grounded *by construction* — it cannot cite something that is
not there. So if the grounding check ever flags a template hypothesis, the defect is in the check,
not in the baseline. That is why the check is validated against the template rather than the model.

## What is built, and what is not

| | What it does | State |
|---|---|---|
| **Sampling** | Draws the 20 scored bundles from one seed, records the population it drew from | **Built.** Drawn and committed before the first paid call |
| **Campaign** | Runs every arm over every sampled bundle, records everything | **Built.** Has run |
| **Grounding check** | Resolves every citation against its bundle | **Built.** 80 of 80 passed |
| **Statistics** | Per-arm catch rate, retry rate, fallback rate, cost, agreement across repeats | **Built and reported end to end.** Needed the campaign record rebuilt: it stores the budget pooled and this reports per arm |
| **Scoring pack** | What a marker reads, blinded, plus the workbook they score in | **Built and rebuilt** |
| **Score ingest + agreement** | Two sheets in, weighted κ out, adjudication applied | **Not built — deliberately deferred.** The second marker is unavailable until mid-October, so there are no sheets to ingest. Building the ingest against invented sheets is how you discover at ingest time that you guessed the shape |
| **Detection metrics** | Precision, recall, F1, two false-positive rates and latency over the staged corpus | **Built and measured.** 300 runs; the first precision, F1 or latency figures in the project |
| **Metrics export** | The figures as CSV and JSON, with everything needed to regenerate them | **Built and both halves exported**, into separate directories: different corpora, different dates, so one file holding both would read as one measurement |

## The order things happened in, and why the order is the result

A pre-registered comparison is worth nothing if the instrument could have been chosen after seeing
the answers. So the sequence matters as much as the content, and it is recorded rather than asserted:

```mermaid
timeline
    title What was fixed, and when
    7 Aug 2026 : Scoring rubric written : five dimensions, worded anchors, adjudication rule
    27 Sep 2026 : Two corrections argued in the open : stratification was unsatisfiable : N raised from 1 to 3 after a trial disproved its premise
    28 Sep 2026 morning : The 20 bundles drawn from a seed : committed before any paid call
    28 Sep 2026 afternoon : The campaign runs : 80 generations, nothing chosen after the fact
    28 Sep 2026 evening : Pack rebuilt for legibility : presentation only, before any marking
    mid-Oct 2026 : Marking : second rater available
```

Two of those entries are **changes to a pre-registered plan**, and both are recorded with their
reasoning in the rubric's change log rather than made quietly:

- The sample was specified as five bundles per scenario type. **That is unsatisfiable on the built
  system** — five scenario types produce only two kinds of bundle, because one detection rule was
  closed as unbuildable and two scenario types are silent by design. The stratification moved to
  bundle kind: 10 interference, 10 fault.
- The model was to be asked **once** per bundle, because temperature zero with a fixed seed should
  return the identical answer every time. The first real requests measured otherwise: 4 of 5
  comparable repeated pairs differed, one changing which *kinds* of evidence it cited. A single
  generation is therefore one draw from a distribution, not "the model's answer". N went to 3 — but
  **the human scoring stayed at one generation per arm**, because 280 values is the number on the
  ethics consent form and raising it is a re-consent, not a configuration change.

That last point is worth stating plainly: **the binding constraint on the study's size was a consent
form, not a budget.**

## What the campaign actually produced

One run, 28 September 2026, over the 20 sampled bundles.

| | Hosted model | Template |
|---|---|---|
| Generations | 60 (3 per bundle) | 20 (1 per bundle) |
| Bundles covered | 20 | 20 |
| Skipped | **0** | **0** |
| Grounding checked | 60 | 20 |
| **Grounding failures** | **0** | **0** |
| Fallbacks | 0 | — |
| Refusals | 0 | — |
| Wall time | 334.2 s | 0.008 s |
| Cost | **$0.85** | $0 |

20 of 20 complete scored pairs. 60 paid calls against a ceiling of 200; 326,106 prompt tokens and
25,269 completion tokens. Total project spend to date is about **$1.75 of a $5 budget**.

**How to read the zero.** A grounding catch rate of 0.0 on the hosted arm is a genuine result and a
narrow one. It says every rule identifier the model cited exists in the bundle it was given. It says
**nothing** about whether the sentence attached to each citation is true — the check resolves
identifiers, not prose. A real finding with a false sentence attached passes. So the catch rate is a
**lower bound on ungroundedness**, and *misdescribed reference* is left entirely to the human
scoring. This is the single most important caveat in the harness and it is the reason the human pass
exists at all.

The template's 0.0 is read differently again: it is the **oracle** reporting that the check found no
defect in itself.

## The scoring pack, and what must not be inferable

Twenty evidence packs, two explanations under each, labelled A and B. Four separate mechanisms keep
the marker from working out which arm wrote what:

1. **One renderer for both arms.** No code path anywhere branches on which arm produced a
   hypothesis. A formatting difference would be a *perfect* classifier, where prose style is only a
   hint.
2. **The labels are reshuffled per pack**, from a seed unrelated to the sampling seed. Working out
   one pack tells the marker nothing about the next.
3. **The arm key is a separate file** and is joined only after both markers' sheets are in.
4. **An automated scan** over everything the marker receives — the prose *and* the workbook's cells,
   headings, sheet names, notes and document properties — looking for the arm vocabulary.

The pack also opens with a **glossary** — every rule name, conclusion label and domain word a
marker will meet, on the page and again as a tab in the workbook they score in. Its one rule is that
a definition says what a term *denotes* and never what it *implies*: *"one aircraft's position
reports stopping"* is a definition, *"…which can indicate interference"* is the answer to the question
being asked. That is the summarising-pack failure in its most dangerous form, because prose reasoning
does not look like a computation, so it is guarded by a named list of causal connectives no
definition may contain. A citation key with no entry is refused rather than omitted — a guard which,
the first time it ran, found that the bundle test fixtures had been using a finding type the
detection layer never emits.

**Pass two has an answer sheet of its own**, handed over only once every pass-one score is in:
one section per pack, giving the correct answer and what was actually staged in the pack's run.
The correct answers are one sentence per scenario type, taken from that type's definition written
before the campaign, so nothing is decided pack by pack after the explanations have been read. It
names neither label and is scanned like the other files. It was built late: the rubric promised it
and nothing produced it until the first rater reached pass two and found only the arm key, which sat
in the same folder and was opened. On the five mixed-evidence packs the answer (*a fault and
interference cannot be told apart*) rests on aircraft evidence the pack never contains, because the
sensor-fault verdict stops the aircraft side being consulted, so cause correctness there measures the
detection layer rather than either arm and is reported separately.

The blinding is **honestly imperfect and the imperfection is stated**: the template's prose is
stylistically distinctive and a marker may well recognise it. That residual threat is recorded in the
Evaluation chapter rather than claimed away. What the four mechanisms prevent is *adding* a
structural leak to a stylistic one.

### The pack was rebuilt because it was unreadable

The first pack was technically correct and practically unusable, which is a failure mode worth
recording because every automated check on it passed.

| Fault | Why it mattered |
|---|---|
| Emitted as **space-aligned plain text in a Markdown file** | Any renderer reflowed nineteen findings into one paragraph and collapsed the alignment the layout relied on. Legible only in a raw editor |
| Findings **did not name their source** | The hypotheses above them cite `RF-06:4` by name. *Evidence use* is the first of five dimensions, and it was being scored against a pack the citation could not be checked against |
| Repetition printed verbatim | Nine identical track-gap lines; the same uncertainty three times |
| The bundle's own conclusion sat tenth of nineteen | The claim under scrutiny was buried in its own supporting material |

The restructure groups findings by the rule that produced them, **lists every finding individually
inside its group**, names every source, and de-duplicates uncertainties with a count.

**The constraint that governs the fix:** grouping must never replace detail with a summary. A pack
that pre-digested its own findings would do part of the work dimension 1 is scoring — which would
shrink the measured gap between the arms, in the direction that flatters the weaker one. So nothing
was removed; only the re-reading was. In fact the restructure *exposed* two facts the old pack hid:
the RF deviations split evenly 4/4 across the two sensors, and one aircraft dropped out **twice**
inside a single window.

## Two things that went wrong in production

Both cost real money or real data, and neither was visible from a green test suite.

**The application database was two migrations behind.** The test fixtures migrate the *test*
database; nothing migrated the application one. The campaign opened, made one paid call, and died
writing the row. **A green suite says nothing about the schema the system actually runs against.**
The fix was a pre-flight check that refuses to start if the schema is not at head — placed *before*
the first billed call, because a check that runs after the money is spent is a log line.

**Rate limiting silently shrank the corpus.** The provider returned 429s and the campaign recorded
them as "provider unavailable", losing 5 generations, 2 of them scored — 18 of 20 complete pairs
instead of 20. But a 429 is not "unavailable"; it says *try again in 5.09 seconds*. Treating a
retryable condition as permanent quietly reduced a pre-registered corpus. The fix was **pacing, not
retrying** — an 11-second gap between calls — because retrying inside the campaign would have blurred
the availability fallback into the correctness one, which is the distinction the whole design rests
on.

## The detection results table

Separate from everything above: this scores the **rules**, not the explanations, and it is the one
part of the harness that needed no model and no money. Measured over all 300 runs of corpus v2, with
the whole chain re-run rather than read from stored findings.

| Arm | Runs | Decided correctly | Recall per run | Recall per staged aircraft |
|---|---|---|---|---|
| `rf-sensor-fault` | 60 | 60 | 1.000 | — (no aircraft staged) |
| `gnss-degradation` | 60 | 60 | 1.000 | 0.823 |
| `ambiguous-mixed-evidence` | 60 | 60 | 1.000 | 0.587 |
| `normal-baseline` | 60 | silent 60 | — | — |
| `aircraft-coverage-gap` | 60 | silent 60 | — (no built rule judges it) | 0.587 |

| Reportable type | Claimed | Right | Precision | F1 |
|---|---|---|---|---|
| `possible_sensor_fault` | 120 | 120 | 1.000 | **withheld** — two arms produce it |
| `possible_interference_zone` | 60 | 60 | 1.000 | 1.000 |
| `possible_data_source_issue` | 0 | 0 | — | — (`anom-006` unbuilt) |

False positives: **0 of 60 from nothing** (`normal-baseline`, backed by `anom-008`) and **0 of 60
cross-modal** (`aircraft-coverage-gap`, not backed by a control — `anom-008` grades quiet runs only).
Never pooled: the first asks whether the system invents an anomaly, the second whether a track-side
disturbance leaks into a radio verdict.

Latency, conditional on detection: median **10 s** on both fault arms, **20 s** on the interference
arm, min 10 s and max 90 s over 60 detections each. The 10 s floor is `anom-014`'s minimum episode
duration — the fault arms decide as soon as they are allowed to look, and the interference arm waits
one sampling interval longer for a second receiver to qualify.

**Six constraints govern how this may be reported**, and five of them are about what each figure is
indexed by. Recall is indexed by truth and precision by prediction, so they never share a row. F1
exists only where one arm maps to one type. A misreport is two errors, so this is one multi-class
confusion and not three binary problems. There are two false-positive rates. Latency belongs to the
successes, not to the arm. And every rate is `None` over an empty population, never 0.0.

The seventh is a refusal rather than a definition: **no false-positive rate is reported for a corpus
whose quiet runs did not pass `anom-008`**. Zero findings is the answer the control wants and also the
answer a pipeline that never ran gives.

## The per-arm figures, run end to end

| Arm | Gens | Bundles | Checked | Caught | Catch | Retry | Fallback | Calls | Spend | Seconds |
|---|---|---|---|---|---|---|---|---|---|---|
| `template` (oracle) | 20 | 20 | 20 | 0 | 0.000 | 0.000 | 0.000 | 0 | $0.000000 | 0.008 |
| `hosted` | 60 | 20 | 60 | 0 | 0.000 | 0.000 | 0.000 | 60 | $0.854364 | 334.197 |
| `local` | 0 | 0 | 0 | 0 | — | — | — | 0 | $0.000000 | 0.000 |

Agreement across the three generations per bundle, on the model arm over 20 bundles: grounding
**1.000**, confidence **1.000**, cited evidence kinds **1.000**. The template arm is N=1 by design
and reports nothing rather than a perfect score it did not earn.

**That last row corrects a prediction this document used to carry.** The amendment written after the
three-bundle trial expected the *cited set* to be the dimension that moved, having seen it move on
one of three bundles. Over twenty it moved on none. The widening to three dimensions was still right
— grounding agreement alone would have printed 1.0 and been unable to say whether anything else had
changed — but the write-up must quote the measurement rather than the expectation. What it leaves is
sharper: across sixty generations the only thing that differed between repeated answers was the
**prose**, which none of these three measures and which the blind scoring is what examines.

**The local row is the `None`-over-nothing rule arriving as a result.** Blank, not 0.000: a catch
rate of zero would claim the check examined that arm's answers and flagged none, on an arm nobody
asked. The counts of zero beside it say which.

### Getting these figures out needed the record rebuilt

The campaign's artefact keeps every generation in full and keeps the spending and the grounding
checks as *figures* — a total spend, a catch rate — not the calls and checks behind them. This report
is **per arm, never pooled**, and needs the individual calls. So the one artefact the campaign
produced cannot answer the question the item after it asks of the campaign, and the two items passed
independently with that join never exercised.

Rebuilt without inventing anything — each call's spend from the generation it produced, its model id,
frozen parameters and verbatim response from the row stored for it — then **reconciled twice**, with
the whole report refused if either check fails:

| Check | Result |
|---|---|
| rebuilt calls sum to the stored pooled budget | 60 calls, 326,106 + 25,269 tokens, $0.854364, 0 unpriced — exact |
| rebuilt ledger matches the stored per-arm counts | 60 checked hosted, 20 template, 0 caught — exact |

A *failed* check cannot be rebuilt at all: the artefact records that a hypothesis failed and never
which citation failed, so that path raises rather than inventing a finding. Nothing failed here, so
it is unexercised. Storing enough for the record to round-trip is owed and would not help this
artefact, which predates it.

## The export, and what makes a file self-describing

Every figure above also lands as files a chart can be drawn from and a thesis row can be traced back
through. Three decisions make that more than a formatting step.

**A seed reproduces the hours; a policy reproduces the figures.** The scenario base seeds determine
which hours exist and say nothing about the settings the detectors ran at — the deviation threshold,
the minimum episode, the gap threshold and contact-freshness window, the three radii, the
corroboration ratio. Set the threshold to 8 dB instead of 6 and every figure moves on the same hours.
Thirteen detector settings therefore go out beside the seeds, read off the policy objects the
measurement actually used, and a provenance record missing one is **refused at construction**.

**Traceability is a resolvable key, because the unit that travels is one row.** A header comment
breaks a CSV parser and, more to the point, is lost the moment a row is pasted into a table. Each
row's first column is a twelve-character digest of the provenance record; `provenance.csv` resolves
it, one field per row so two unlike records share a shape. Change any field and the digest changes,
so a stale row fails to resolve rather than citing the wrong corpus.

**No rate is written without its counts.** This is the one place the `None`-over-an-empty-population
rule would have died: a CSV writes `None` as an empty cell, and an empty cell is zero to a
spreadsheet and to every dataframe library. A sentinel token would make the column non-numeric, so
the population sits in the next column instead — a blank beside a denominator of 60 and a blank
beside a denominator of 0 mean different things, and both are readable.

Two rules follow from those. The export **computes nothing** — every value appears verbatim in what
it was handed, so the quoted number is the tested number — and **column names are derived by
flattening** rather than typed, so `recall_per_run` cannot become `recall` at the one boundary that
guard exists for.

| File | What it holds |
|---|---|
| `metrics.json` | everything, nested, with both provenance records |
| `provenance.csv` | one field per row: corpus, seeds, run count, thirteen policies, date |
| `detection_arms.csv` | one row per scenario type — recall, misses, latency, per-aircraft recall |
| `detection_types.csv` | one row per reportable answer — precision, F1, the arms behind it |
| `detection_false_positives.csv` | the two silences, each with its own control status |
| `detection_confusion.csv` | one cell per row, long rather than wide |
| `campaign_arms.csv` | per-arm catch, retry, fallback, cost, agreement — in its own directory, with its own provenance |

## What this harness cannot tell you

Stated in advance, which is the only time it counts.

- **The grounding check verifies existence, not accuracy.** A true citation with a false sentence
  attached passes.
- **Two markers is two markers.** Agreement between two people is not agreement in general, and 20
  bundles is a small corpus, chosen because 280 scored values is what one person can do carefully.
- **The blinding is imperfect** on prose style, as above.
- **Only two kinds of bundle exist**, so the comparison covers interference and sensor-fault
  explanations and nothing else. A third rule would need a fresh sample.
- **Cost and latency are one run on one day.** The wall-time gap between the arms — 334 seconds
  against 8 milliseconds — is real and large, but it is a single measurement under one set of network
  conditions.
- **No result from the human pass exists yet.** Nothing in the write-up may speak as if it does.
- **The retry and fallback paths never fired.** Nothing was refused and nothing fell back on the
  scored campaign, so a fallback rate of zero reports that the path was not exercised — not that it
  works. The same run cannot test both.
- **Agreement was measured over what can be compared mechanically**, not over the prose. All three
  comparable dimensions agree perfectly across repeats; the prose is what varies and only the blind
  scoring examines it.
- **The detection table measures wiring, not detection accuracy.** Every rate in it is 1.000 or
  0.000, and three things make that a weak result: the radio side is synthetic and the injected
  incident sits well above threshold by construction, the corpus contains no near-misses, and one of
  three reportable types has no rule. The one figure carrying information from outside the generator
  is the per-aircraft recall, because the aircraft data is replayed — and that one is 0.587 on two
  arms of three.

## Vocabulary

| Term | In one line |
|---|---|
| **Arm** | One explanation writer. Hosted model, local model (not built), or template |
| **Bundle** | Everything about one detected event, and the only thing an arm is ever shown |
| **Generation** | One request, one answer. Three per bundle on the model arm |
| **Grounding** | Does each cited rule identifier exist in this bundle? Resolved on the `(rule, finding type)` pair, never the rule alone |
| **Catch rate** | Of the generations checked on one arm, the fraction the check flagged. `None`, never 0.0, when nothing was checked |
| **Retry rate** | Refusals over **attempts**, not over generations — over generations it is an average wearing the word *rate* and can exceed 1.0 |
| **Fallback** | An arm was asked and a different one answered. The stored row records both |
| **Oracle** | The template. Grounded by construction, so anything flagged on it is a defect in the check |
| **Scored generation** | Generation 1, fixed in advance, **never substituted** — swapping in a later one would delete every failure from the scored corpus |
| **Indexed by truth / by prediction** | Which set a rate's denominator comes from. Recall is the first, precision the second, and one table row cannot carry both |
| **Recall per run / per staged aircraft** | The two recalls. `eval-002`'s and `anom-011`'s, 41 points apart on `ambiguous-mixed-evidence`. Never averaged, and neither is exported as a bare `recall` |
| **Discriminating negative** | A staged case no rule is meant to report, so correct silence on it is evidence rather than an absence |
| **Conditional on detection** | A figure existing only over the successes. Latency is the one, and printed beside a recall below 1 it invites the opposite reading |
| **Provenance digest** | A short hash of the record describing a run, on every exported row, resolving in one file. Changes when any field changes |
| **Policy versus seed** | A seed reproduces the hours; a detector policy reproduces the figures. Both are exported |
| **Pass one / pass two** | Five quality dimensions scored blind; then, after the answers are revealed, two more judgements. Kept apart because knowing the answer changes how good an explanation feels |

## Where to look next

| Question | Document |
|---|---|
| How is the explanation scored, exactly? | `docs/scoring_rubric.md` — pre-registered, with its change log |
| What must this do? | `docs/requirements.md` |
| What is the binding definition of a capability? | `docs/spec.jsonl` |
| Why was this decided, and what lost? | `docs/thesis_notes.md` |
| What does this term mean, and what did I get wrong about it? | `docs/qa.md` |
| Why is the AI layer shaped this way at all? | `docs/phase9_hypothesis_layer.md` (written before any model code) |
| What feeds this? | `docs/detection_layer.md`, then `docs/phase8_evidence_bundles.md` |
| How do I explain this to someone outside the project? | the published progress note |
| Where does the work stand right now? | `docs/handoff.md` |
