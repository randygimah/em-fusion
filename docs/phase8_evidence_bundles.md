# Phase 8 (tail) — The Evidence Bundle Builder

*Written 2026-09-19, on picking up `evb-001`, and **written before it is built**. It is the reasoning
behind the builder in one place: what it is, what it is for, why it is shaped the way it is, and what
the specification gets wrong about it. Companion to `docs/phase8_detection.md`, which does the same
for the detectors that feed it.*

*Reference and drafting material. `docs/thesis_notes.md` holds the decisions and their rejected
alternatives, `docs/qa.md` explains what individual terms mean, `docs/spec.jsonl` is the binding
backlog, `docs/detection_layer.md` is the current state of what feeds this. **Where this document and
the spec disagree, the spec wins** — except where this document says the spec is wrong, in which case
the spec is amended first and built second.*

---

## 1. What this is

The detection layer now makes claims about the world. Over three hundred staged hours it decides
every arm correctly sixty times out of sixty, and it produces those decisions as a stream of small,
precise, individually meaningless facts: an episode of raised power on one receiver and one channel
between two timestamps; a discontinuity in one aircraft's reporting; a group of discontinuities
within twenty kilometres of each other; a ratio of local rates; a verdict that one receiver's
neighbours were measured and nominal.

A quiet hour holds about a hundred and thirty-eight of those track discontinuities on its own. A
staged hour holds more, plus radio episodes, plus clusters, plus verdicts. **Nothing downstream can
consume that.** An analyst handed eight hundred findings has been handed the interpretive work back.
A language model handed eight hundred findings will confabulate a story over whichever ones fit.

The evidence bundle is where those facts become **one account of one event**, with its sources
attached and its uncertainties stated. It is the last thing Phase 8 builds and the first thing Phase
9 consumes, and it is the only thing Phase 9 will ever be allowed to see.

## 2. What it is trying to achieve

| | Job | Why it is not optional |
|---|---|---|
| 1 | Gather the findings that belong to **one event** into one object | A correct detection reported in fragments is an incorrect picture |
| 2 | Attach to every claim **the record it came from** | An explanation that cannot be checked is an assertion |
| 3 | State what is **not** known alongside what is | The system's honest position is the one being evaluated |
| 4 | Be the **only** thing the AI layer sees | It is what makes the grounding check possible at all |

The fourth is the one that makes the other three load-bearing rather than tidy. It is discussed in
section 3, because it is the decision everything else in this phase descends from.

## 3. Why the bundle is a boundary, not a container

It would be possible to build this as a convenience object — a bag that collects findings so the
caller has one thing to pass around. That is not what it is. It is a **containment boundary**, and
three separate guarantees rest on it.

**It is what makes automated grounding tractable.** `ai-008` checks, for every claim a model makes,
whether the thing it cites actually exists. That check is only possible if the set of citable things
is **closed and enumerable**. If a model could see the observation stream, "is this claim grounded?"
has no computable answer — it would mean searching twenty million rows for something that resembles
what the model said. Against a bundle holding a dozen evidence items with rule IDs, it is a set
membership test. The bundle is not merely the input to the AI layer; it is the *reason the safeguard
works*.

**It is the last point before data leaves the machine.** The hosted generator is the project's only
running cost and its only egress. NFR-405 names the evidence bundle explicitly: no real aircraft
identifier may appear in one. That guarantee is already structurally satisfied, because
pseudonymisation happens far upstream at the abstraction layer (`dal-004`) and every identifier in
every finding is already of the form `AC-…`. **But inherited is not proved.** NFR-405 names this
object, so the builder owes a test that demonstrates the inheritance rather than assuming it — the
cost of being wrong is a licence breach, not a bug.

**It is what keeps the comparison a comparison.** The evaluation campaign scores hypothesis quality
across generator arms over *identical* bundles. If bundle content varied with the generator, or with
anything other than the run, a difference in hypothesis quality could not be attributed to the
generator. The builder must therefore be deterministic in the same sense the detectors are: same run,
same findings, same bundle, byte for byte.

## 4. The chain, end to end

What actually exists today, rather than what Phase 8 planned:

```
   stored observations                       (20.7M rows, two data modes)
            │
            ├── RF, synthetic ──────────┐         ├── tracks, replayed ───────┐
            ▼                           ▼         ▼                           ▼
   BASELINE anom-002              RF-NOISE anom-001            TRACK-GAP anom-010
   per sensor per channel         episodes per cell            discontinuities
   from quiet runs only           (+ suppressed, anom-014)     (~138 on a quiet hour)
            │                           │                           │
            │                           │                           ▼
            │                           │                  CLUSTERING anom-004 / db-009
            │                           │                  groups, centroid, hull
            │                           │                           │
            │                           │                           ▼
            │                           │                  RATE EXCESS anom-012
            │                           │                  local ratio, or NOT MEASURABLE
            │                           ▼                           │
            │                  SENSOR-FAULT anom-007 ◄───────────────┘
            │                  three-valued verdict
            │                  fault / environmental / undecided
            │                           │
            │            ┌──────────────┴───────────────┐
            │            ▼                              ▼
            │     (fault verdict)              (environmental verdict)
            │     SENSOR-FAULT claim           FUSION-SPATIAL anom-005
            │                                  + corroboration, three-valued
            │            │                              │
            │            └──────────────┬───────────────┘
            │                           ▼
            │                  PRECEDENCE anom-013
            │                  claims → zones, one event one zone
            │                  Resolution(reported, suppressed)
            │                           │
            ▼                           ▼
   ┌──────────────────────────────────────────────────────────┐
   │  EVIDENCE BUNDLE   evb-001                               │
   │  one reported claim → one bundle, with its evidence,     │
   │  its sources, and what it could not measure              │
   └──────────────────────────────────────────────────────────┘
                                │
                                ▼
                    TRACEABILITY evb-002
                    every item resolves to a stored row
                                │
                                ▼
                       the AI layer, Phase 9
```

`SOURCE-GAP` (`anom-006`) is **absent from this diagram on purpose.** It was measured twice and
closed twice; see `docs/detection_layer.md`. Its absence is a fact the builder must accommodate
rather than a gap to be left space for — see section 10.

## 5. What the detection layer actually hands it

This is the section most worth reading, because the specification for `evb-001` was written when
none of it existed, and it describes inputs that are now known precisely.

**One canonical finding shape** (`db-008`). Every rule's output becomes a `DetectionFinding` carrying
`scenario_run_id`, `rule_id`, `finding_type`, `subject`, a time window, a `location`, an
`evidence_refs` tuple and a rule-specific `details` map. The builder therefore needs no per-rule
knowledge to *carry* a finding — only to *interpret* one.

**Reported claims, already grouped into zones** (`anom-013`). The ladder emits a `Resolution` holding
`reported` and `suppressed` claims. A `Claim` is `rule_id`, `anomaly_type`, and a `Zone` of centre,
start and end. Claims for the same zone have already been merged: one event, one zone, merged on the
layout's discrimination radius and inclusive window overlap.

**Two anomaly types, not three**, because `SOURCE-GAP` has no producer. Across corpus v2 the ladder
reports `possible_sensor_fault` and `possible_interference_zone` and nothing else.

**Three-valued verdicts and an explicit not-measurable**, which is the material for section 7.

**Identifiers already pseudonymised.** `evidence_refs` on a track finding carries
`{"aircraft_id": "AC-…", "at": "…"}`; on an RF finding, `{"sensor_id", "channel_index", "timestamp"}`.

## 6. Grouping: three axes, and the one that already exists

`evb-001` requires grouping on **simulated time window, spatial proximity, and frequency adjacency**.
Taken literally that is a new grouping mechanism in the builder. It should not be.

**Time and space are already done, by `anom-013`.** The ladder merges claims into zones on exactly
those two axes, and it does so because it had to: one zone per dismissal gave a hundred and sixty
zones for sixty events. A second implementation of "near in time and space" in the builder would be a
second copy of a rule that already exists — the precise trap this repository has recorded once
already, where distance was nearly measured in two places and the second copy would have been in
degrees. **The builder consumes `Resolution.reported`; it does not re-group.**

So the unit is settled: **one reported claim, one bundle.** Not one bundle per run — a run with two
broken receivers is two events, and `anom-013` already refuses to merge them because its suppression
is cross-rule only. Not one bundle per finding — that is the fragmentation the item exists to
prevent.

**Frequency adjacency is the axis that is genuinely the builder's**, and it is the one with no
mechanism anywhere upstream. `anom-001` raises episodes per cell — per sensor *per channel* — so a
single event touching several channels of one receiver arrives as several episodes. Nothing merges
them. `anom-007` reasons across the band but emits a verdict about a receiver, not a grouping of
channels. So if a bundle is assembled from `anom-001` episodes without a frequency axis, a wide event
fragments, which is `evb-001`'s second stated failure case.

**And this is where the honest difficulty sits — see section 10, because that failure case cannot
currently be provoked by any run in the corpus.**

## 7. Known uncertainties: a field with real content

Most specifications that require a "known uncertainties" list get an empty list, because nothing
upstream produces uncertainty as a value — it produces answers, and uncertainty is something the
write-up adds afterwards. That is not the situation here, and it is worth stating plainly because it
is one of the stronger things this project can show.

The detection layer already produces uncertainty as **typed, countable output**:

| Source | What it says | Measured on corpus v2 |
|---|---|---|
| `anom-005` corroboration | `not_measurable` — the track side had nothing to weigh | **41 of 60 reported zones** |
| `anom-007` verdict | `undecided` — no neighbour inside the radius, or unmeasurable | three-valued by design |
| `anom-001` unjudged cells | no baseline existed, so the cell was **not looked at** | reported, never skipped |
| `anom-014` suppressed episodes | looked at, and too brief to call an event | own field, not folded into unjudged |
| `scn-007` floor shortfall | the run staged fewer aircraft than asked, and says so | on the answer key |

Four of those five are already separate fields on the detectors' outputs, deliberately, and the
reasoning is identical in each case: *"I looked and saw nothing"* and *"I could not look"* are
different claims and only one of them is evidence. The bundle is where that distinction finally pays
off, because it is the point at which a model would otherwise be free to read silence as absence.

**The forty-one in sixty is the single most important number this builder carries.** The project's
fusion claim is weaker than it sounds — in most reported zones there is no measurable track evidence
at all — and the bundle is the object that must say so to the thing writing the explanation. A bundle
that omitted it would be inviting exactly the overclaim the whole architecture exists to prevent.

## 8. Traceability, and a gap in what findings currently store

`evb-002` requires that every evidence item **resolve to a stored anomaly or observation**, checked
at build time against the database, with the resolved identifiers persisted so `ai-008` has something
to verify against. A bundle with an unresolvable item must raise and persist nothing.

`DetectionFinding.evidence_refs` looks like it was built for this, and it is close, but there is a
real gap worth knowing about before tests are written.

**What the refs currently carry is a coordinate, not an identifier.** An RF finding's refs are
`{sensor_id, channel_index, timestamp}`; a track finding's are `{aircraft_id, at}`. Those describe an
observation precisely enough for a human to find it, but neither is a row ID, so "resolves to a
stored observation" is a *query*, not a lookup. Two ways forward:

| Option | Cost |
|---|---|
| Resolve by coordinate at build time — query `observations` by run, subject and timestamp | Needs an index that may not exist; the coordinate must be provably unique, and "provably" means measured, not assumed |
| Change the `from_*` functions to record row IDs at finding time | Touches every rule's adapter. Findings are derived and regenerable (`db-008` replaces per run per rule), so the stored corpus is not a blocker — but every committed detection figure would want re-running to confirm nothing else moved |

The first is smaller and reversible; the second is the one that makes `ai-008` cheap later. **This is
a decision owed before tests, not during.** Whichever is chosen, the uniqueness of the coordinate must
be measured — a resolver that silently matches two rows is worse than one that fails.

## 9. Three defects in the specification, found before building

Writing this document found three things in `evb-001` that do not survive contact with what exists.
All three are cheap to fix now and expensive after tests are written against them.

**First: `data_mode` cannot be a single value on a fused bundle.** The spec and FR-401 both give the
bundle one `data_mode`. But RF observations are ingested as `SYNTHETIC` and replayed tracks as
`REPLAYED`, so **every run holds both**, and a `FUSION-SPATIAL` bundle draws its evidence from both by
definition — that is what makes it a fusion. One value would have to be wrong, and the wrong one is
the one that tells an analyst which half of the picture is invented. `data_mode` belongs on the
**evidence item**, with the bundle carrying the set. This matters beyond tidiness: `op-001`'s
SYNTHETIC ENVIRONMENT DATA badge is specified to reflect the data rather than a UI constant, and a
bundle that flattens two modes into one makes that badge a lie at the point it matters most.

**Second: the grouping constraint reads as a builder responsibility and is mostly not one.** Section
6 covers this. The item should name `anom-013`'s resolution as its input explicitly, so that a later
reader does not implement time-and-space grouping a second time in good faith.

**Third: "a group of related anomalies from one scenario run" predates the ladder.** When `evb-001`
was written there was no mechanism that decided which findings constituted one event. There is now,
it is measured, and it merges on a declared radius. The item should say so rather than leaving the
unit of a bundle to the builder's discretion.

None of these change what the bundle is *for*. They change what it is made of, and they are the
reason this document exists before the spec amendment rather than after it.

## 10. What the corpus cannot currently exercise

Two of this item's obligations cannot be demonstrated on the data as it stands. Both are stated here
so they are not discovered during a write-up.

**The broadband fragmentation case has no corpus behind it.** `evb-001`'s second failure case is a
broadband event spanning eight channels producing eight single-channel bundles. **All three hundred
runs of corpus v2 are narrowband**, as all two hundred and forty of corpus v1 were. So the exact
situation the frequency axis exists to handle **cannot be produced by any run available**. The axis
can and must still be proved — by unit tests over constructed findings, which is legitimate and is how
the same problem was solved for the baseline's per-channel granularity in Phase 8 section 5 — but a
unit test proves the mechanism, not that the mechanism matters. The corpus-level demonstration is owed
to a broadband generation arm that does not exist, and which is already recorded as open and unowned
for a second reason: `anom-007`'s Medium and Low confidence bands have no corpus behind them either.
One generator change closes both.

**Bundles will only ever carry two anomaly types.** With `anom-006` closed, no run produces a
`SOURCE-GAP` claim. The builder must not be written as though three types were coming; equally it
must not hard-code two, since the ladder's constant is the authority. A test asserting "exactly two
anomaly types appear in the corpus" would pass today and be wrong the day a rule is added — the
correct assertion is that the builder handles whatever the ladder reports, including a type it has
never seen.

And one interaction to get right rather than discover: **a quiet run must produce zero bundles, not
one empty bundle.** `anom-008` requires zero reportable anomalies on a quiet run, and `evb-001`
independently requires that a bundle with an empty evidence list fails to build. Those two agree, and
the way they agree is that no bundle is created at all. A builder that emits an empty bundle per
quiet run would satisfy neither, and would put sixty content-free objects in front of a model.

## 11. What this deliberately does not do

- **No hypotheses.** A bundle is evidence, not explanation. Turning it into readable assessment is
  Phase 9, and the separation is what lets the AI layer be swapped, compared and scored.
- **No ground truth.** The bundle carries no answer-key field, per `api-009`. The answer lives on the
  run record and nowhere else. A generator or consumer that can see the answer invalidates every
  metric computed from it.
- **No severity or confidence arithmetic.** `anom-001` already carries severity and `anom-005`
  confidence, both as Low/Medium/High. The bundle carries them; it does not combine them into a new
  number. A bundle-level score would be a fourth rule pretending not to be one — the objection
  `anom-013`'s referee already answered.
- **No new vocabulary.** Nothing in a bundle is a percentage or a decimal. The rate excess and the
  z-score are carried for traceability and are never rendered to an analyst as a score.
- **No UI.** The hypotheses screen consumes what Phase 9 produces, not this.

## 12. How it will be judged

`evb-001` and `evb-002` are proved by unit tests in the ordinary way, and then by two things the
tests cannot show.

The first is a **mutation pass**, as every detection item in this phase has had. The specific risk
here is a builder whose tests all pass against a version that silently drops the uncertainty list, or
flattens two data modes, or groups by run instead of by claim — all three are changes that leave a
well-formed bundle behind, which is precisely the kind of defect a shape-checking test does not see.

The second is a **corpus pass**: build bundles across all three hundred runs and check the aggregate
against what the ladder reported. Bundle count equals reported-claim count; zero bundles on all sixty
quiet runs; every bundle's evidence list non-empty; every item resolvable; the `not_measurable` count
matching `anom-005`'s own figure of forty-one in sixty. That last one is the useful check, because it
compares two independently computed numbers that must agree.

## 13. Decisions owed before any test is written

| Owed | Why it must be fixed first |
|---|---|
| `data_mode` per item or per bundle | Section 9. Changing it after tests means rewriting them |
| Resolve-by-coordinate, or record row IDs at finding time | Section 8. The two produce different test suites |
| Whether the coordinate `(run, subject, timestamp)` is unique | Must be **measured**, not assumed. A resolver matching two rows silently is worse than one that fails |
| The bundle's unit: one reported claim | Section 6. Write it into the item so it is not re-derived |
| Whether `suppressed` claims appear in the bundle they were suppressed by | An analyst may want to know a second rule bid and lost; a model given it may treat it as corroboration. Decide deliberately |
| What a bundle for a `SENSOR-FAULT` claim carries on the track side | Probably nothing, since that verdict never reaches `anom-012` — but "nothing" must be *stated* as not-applicable rather than left absent, or it reads as not-measurable |

## 14. Build order

`evb-001` → `evb-002`, and not in parallel: traceability is a constraint on a shape that does not
exist yet, and building both at once means discovering the shape twice.

Before either: the spec amendments from section 9, and the uniqueness measurement from section 13.
That measurement is the only one owed, it is cheap now that `db-010` exists, and it decides which of
two test suites gets written.

The **template hypothesis generator** in Phase 9 needs no model and nothing from Phase 8.5, so it is
the natural thing to build immediately after `evb-002` — it is both the correctness fallback and the
evaluation baseline, and it is the cheapest possible proof that a bundle contains enough to write an
explanation from. If a template generator cannot produce a readable assessment from a bundle, no model
will rescue it, and that is worth learning before any money is spent.
