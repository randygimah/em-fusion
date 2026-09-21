# Phase 9 — The Constrained AI Hypothesis Layer

*Written 2026-09-21, after `ai-001`, `ai-002` and `ai-003` and **before any model code**. It is the
reasoning behind the model arms in one place: what the phase is for, what "comparable" means when
three different things produce the same object, what the two fallbacks are and why they must not
merge, what actually leaves the machine, what a campaign costs, and what the plan currently gets
wrong. Third in the series after `docs/phase8_detection.md` and `docs/phase8_evidence_bundles.md`,
both of which found defects in their own specifications before a line was written.*

*Reference and drafting material. `docs/thesis_notes.md` holds decisions and their rejected
alternatives, `docs/qa.md` explains what terms mean, `docs/spec.jsonl` is the binding backlog,
`docs/scoring_rubric.md` is pre-registered and may not be edited after the campaign starts. **Where
this document and the spec disagree, the spec wins** — except where this document says the spec is
wrong, in which case the spec is amended first and built second.*

---

## 1. What this is

Everything before this phase produces **evidence**. A reported event becomes one bundle, every
statement in it resolves to a stored reading, and each kind of not-knowing is labelled rather than
left as silence. Forty-one such bundles exist, built from real replayed hours through the shipped
modules.

This phase turns a bundle into an **explanation a person can act on**, and does it three ways: a
mechanical generator with no model, a hosted model, and possibly a local one. The research question
is whether the model adds anything over the mechanical account of the same evidence — which is why
the mechanical one was built first, and why it is permanent rather than scaffolding.

Three of the ten items are done:

| Item | What it settled |
|---|---|
| `ai-001` | The one shape all three produce. A constraint on generation rather than a description of it, so every guarantee is asserted on the *derived* JSON schema a model is actually handed. |
| `ai-002` | The template generator. 41 of 41 real bundles, 0 refusals, 164 of 164 citations grounded. |
| `ai-003` | The seam. A result *envelope* rather than a bare hypothesis; two named failure categories; the configuration carries no credential. |

What remains is the part the project is actually about, and it is the part that costs money, leaves
the machine, and cannot be repeated cheaply once a campaign has run.

## 2. What "comparable" has to mean

The campaign asks a human scorer to grade hypotheses blind and compare arms. That comparison is only
meaningful if everything except the generator is held still. Four things have to be identical across
arms, and each is a separate opportunity to get it wrong.

**The same bundle.** Not the same *run* — the same bundle object. `evb-001` already guarantees a
bundle is a pure function of the detection output, and `ai-002`'s determinism tests extend that to
the words. The campaign should generate from stored bundles read back through `app/db/bundles.py`,
not from a fresh detection pass, so that a change in a detection parameter between arms is
impossible rather than unlikely.

**The same shape out.** `ai-001`, already done.

**The same parameters.** Temperature, seed, maximum tokens — fixed once, recorded on every row, and
never varied between arms. `ai-003` made this structural: the configuration constructs the adapter
rather than travelling per call, so parameters that vary per call would have to be deliberate.

**The same instructions.** This one is *not* yet settled anywhere and is the largest remaining
design decision. The prompt is not a generation parameter in the provider's sense, but it is
absolutely a variable in the experiment: two arms given different instructions are not two answers
to one question. The prompt must be written once, stored beside the results, and shared verbatim
between the hosted and local arms. It is `ai-004`'s first real piece of work and it should be
reviewed before any call is made, because prompt drift mid-campaign is invisible in the output.

**What is deliberately *not* held still:** the template generator receives no prompt at all. That is
the point of it, and it is also the reason it cannot be compared with the model arms on every
dimension — see §8.

## 3. The two fallbacks, and why they must never merge

This is the distinction most likely to be collapsed by accident, because both end with "the analyst
sees something other than the primary arm's output".

| | Availability (`ai-006`) | Correctness (`ai-007`) |
|---|---|---|
| Fires when | the provider is unreachable, unauthenticated, rate limited, timed out | the provider answered and the answer cannot be used |
| What was wrong | nothing about the request | the answer |
| Right response | try the *same request* somewhere else | retry *here* a bounded number of times, then give up |
| Wrong response | retrying the same place harder | retrying elsewhere, which asks a different model the same failed question |

`ai-003` made the distinction expressible rather than conventional: `ProviderUnavailable` and
`GenerationRefused` are siblings under one base, neither a subclass of the other, and the suite
asserts that catching one does not catch the other. A single exception type would have made them
indistinguishable to the code that has to choose.

Two things sit deliberately outside both. A **misconfiguration** is not a generation failure at all —
caught by an availability handler it would run a campaign against the wrong arm; caught by a
correctness handler it would produce mechanical output for every bundle while the run reported itself
as hosted. It has to stop the run. And the **template's own refusal** is outside both for the
opposite reason: the template is what both fallbacks fall back *to*, so a handler responding to it by
reaching for the template has nowhere to go.

**A consequence worth stating now.** Because `ai-003` records *which category* fired, the two
fallbacks stay distinguishable in the record even if they share a destination. "Fell back to the
template because the provider was unreachable" and "fell back to the template because the answer
could not be grounded" remain different facts. This matters for §7.

## 4. What actually leaves the machine

The employer clearance for data egress to a hosted API was confirmed on 2026-09-21, closing the
Track 0 item reopened on 2026-08-13. The licence half was already settled: `dal-004` pseudonymises
aircraft identifiers at ingest, so no real `icao24` or callsign can reach a bundle, which is what
OpenSky DLA §3(i) requires for disclosure.

That is the narrow claim. The honest wider claim needs the actual contents, so they were measured
rather than recalled — every field name in all 41 stored bundles
(`measurements/corpus/bundle_payload.log`):

- **No aircraft position leaves.** The only positional fields in a bundle are `affected_area.lat`
  and `affected_area.lon`, and that is the RF receiver or zone centre from `scn-005`'s **synthetic**
  layout. It is not an aircraft location.
- **Track citations carry a pseudonym and a timestamp** — `aircraft_id` and `at`, 496 of them across
  41 bundles — plus durations and a gap shape in `details`. No coordinates.
- **RF citations are entirely synthetic**: sensor, channel, timestamp, against readings this project
  invented.

So what a hosted provider would receive from the real-data side is: *a pseudonymous identifier, and
the exact second at which that aircraft's reporting broke*. Recorded as a **limitation rather than a
solved problem**: with the same source extract in hand, a precise gap timestamp is quite identifying,
and pseudonymisation of an identifier is a weaker guarantee than non-re-identifiability. What makes
the residual risk small is that reconstructing it requires the source data, and redistributing that
is precisely what §3(iii) forbids — so the attack needs someone who already holds what they would be
trying to learn.

## 5. What a campaign costs, and why the ceiling is not about the campaign

Measured over the 41 real bundles:

| | Characters | ~Tokens |
|---|---|---|
| Smallest bundle | 2,556 | 639 |
| Median | 6,668 | 1,667 |
| Largest | 22,540 | 5,635 |

A whole scored campaign of 20 bundles, one generation, one model arm is **roughly 33,000 input
tokens**. At three generations and two arms it is about 200,000. In money, at any current hosted
price, that is single-digit pounds at worst.

**This reframes the spend ceiling entirely.** The campaign is not the financial risk and never was.
The risk is a loop — a retry that does not terminate, a batch that re-generates on every poll, a
test accidentally pointed at the real provider. That is why the plan puts a run-level call budget in
the code (`ai-009`) *and* a hard cap at the provider console: the console cap is the backstop that
works when the code is the thing that is broken, and the in-code budget is the one that notices in
minutes rather than at the billing boundary.

Recommended, and these are numbers rather than principles: a **run-level ceiling of 200 calls**,
which is five times the largest plausible scored run and still trivially cheap, and a **console cap
of £20**, which is roughly two orders of magnitude above the expected campaign and would take a
genuine runaway to reach. Per-call token and cost logging from the first call, never retrofitted —
`ai-003`'s `Usage` type already exists for exactly this and is carried on every model result.

**One asymmetry the table hides**, and it matters for the scoring campaign rather than for cost: an
interference bundle has a median of 18,435 characters against a sensor-fault bundle's 5,802. The two
kinds differ in size by 3.2×. A scorer marking five of each is reading very unequal amounts, and a
rubric dimension about completeness is not measuring the same thing on both. See §9.

## 6. Reproducibility: what a pinned model actually buys

`db-002` requires four columns on every hypothesis: the generator, the model ID, the generation
parameters and the verbatim pre-parse response. `ai-003` made three of them impossible to omit for a
model arm.

The model ID must be **dated, never a moving alias**. An alias that is repointed mid-campaign changes
what produced half the results with no error, no log line, and no visible symptom — the hypotheses
keep arriving and keep validating. `ai-004`'s stated failure case is that a configuration naming an
alias is refused at startup, and that check belongs in the hosted adapter's constructor, where
`ai-003` already puts configuration validation.

The **verbatim** response matters more than it looks. It is not the parsed hypothesis re-serialised;
it is what came back before anything understood it. The difference only shows up once — when
somebody investigates a grounding failure months later and finds that what was stored is a record of
what we *understood*, not of what was *said*.

## 7. The local arm: a decision, with a trigger

The gate asks whether the local model arm stays in scope. The plan already time-boxes it to about a
day and says explicitly it can be cut.

**What keeping it buys.** An availability fallback that is still a *model* rather than a mechanical
summary; an offline demonstration; and one genuinely interesting result — the same JSON Schema
enforced two ways, by a hosted provider's constrained decoding and by a grammar compiled locally,
producing an identical guarantee. That last is a real portability finding.

**What it costs.** Two spec items (`ai-005`, `ai-006`), a day time-boxed and realistically more, and
a permanent moving part in the demo: Docker Desktop on macOS does not pass Metal through, so the
model server runs on the host and the container reaches it over `host.docker.internal` as a config
value rather than a Compose service.

**What cutting it actually loses is less than it appears**, for two reasons that only became true
recently. First, the offline demonstration survives: the template generator needs no network and
produces a real explanation, so an offline demo shows template output rather than nothing. Second —
and this is the load-bearing one — `ai-003` names the two failure *categories*, so cutting the local
arm does **not** collapse the two fallbacks. They keep different causes and different log records;
only the destination coincides. The distinction §3 insists on is preserved in the data either way.

**Recommendation: defer the decision until after `ai-004` works, and let the hosted arm's measured
reliability settle it.** Deferral is normally the wrong answer to a gate item, and the reason it is
safe *here specifically* is narrow and worth stating: **the local arm is not scored.** The
pre-registration covers hosted-versus-template only, so adding a second model arm afterwards costs
nothing in validity — unlike every other item on this gate, which is expensive-to-impossible after
the campaign precisely because it *is* inside the pre-registration.

The trigger: build `ai-004`, record how often the hosted arm is unavailable over development use,
and revisit. If it is reliable, a local arm buys an offline demo the template already provides and a
portability result that costs a day. If it is flaky, the case rewrites itself.

## 8. N generations, and a contradiction in the plan

The gate says two things that cannot both hold:

> Fix generation parameters once — **temperature 0**, seed, max tokens — and freeze them across arms.

> Decide **N generations per bundle per arm**. This multiplies both cost and campaign wall-time, and
> **drives the grounding-variance measurement**.

At temperature 0 with a fixed seed, generation is intended to be deterministic. You cannot measure
the variance of a process you have configured not to vary. Either the temperature is not 0 for the
variance arm, or there is no variance measurement, or the thing actually being measured is not what
the sentence says.

**The resolution, and it is better than either horn.** Keep temperature 0 and **N = 1 for the scored
campaign**: reproducibility is the priority, the campaign is pre-registered, and a scored corpus of
one generation per bundle per arm is exactly what the rubric was written for. Then run a **separate,
small, explicitly non-scored probe at N = 3** on a handful of bundles, whose question is not
"how much does the model vary" but:

> *Is this provider actually deterministic at temperature 0?*

Many are not, because of batching and floating-point non-associativity in the serving stack — the
same class of problem this project has already hit three times in its own results. If the answer is
no, that is a **threat to reproducibility** that belongs in the write-up and is far better discovered
before the campaign than after. It costs about 100,000 input tokens, which is pennies, and it is the
only version of this measurement that is coherent.

## 9. The scoring corpus, and a stratification that does not exist

The gate fixes the blind-scoring corpus as:

> a stratified sample of ~20 evidence bundles (**5 per anomalous scenario type**), 40 hypotheses,
> fully double-scored.

That cannot be satisfied as written, and the reason is a fact about the built system rather than
about the plan's intent. Five scenario types exist, but they do not produce five kinds of bundle:

| Scenario type | What it produces |
|---|---|
| `gnss-degradation` | `possible_interference_zone` — 20 of 20 |
| `rf-sensor-fault` | `possible_sensor_fault` — 21 of 21 |
| `ambiguous-mixed-evidence` | `possible_sensor_fault`, 20 of 20, **by design** |
| `aircraft-coverage-gap` | nothing, 75 of 80 — its rule was closed as unbuildable on this corpus |
| `normal-baseline` | nothing, by design, and that is `anom-008`'s control |

So there are **two kinds of bundle**, from three producing scenario types. "Five per anomalous
scenario type" would require bundles from a type that produces none.

**Recommendation: stratify on bundle kind rather than on scenario type** — 10 interference and 10
fault, keeping the planned 20 bundles and 40 hypotheses — and record the producing scenario type on
every sampled bundle so the `rf-sensor-fault` against `ambiguous-mixed-evidence` split can be
examined afterwards without having stratified on it.

Two things follow that the rubric may need to acknowledge before it is locked:

- **Size.** Interference bundles are 3.2× larger. Balanced by kind, a scorer reads roughly equal
  numbers of long and short documents; stratified by scenario type it would have been three-quarters
  short ones.
- **The mechanical arm's constancy.** The template emits exactly four citations on all 41 bundles,
  because both bundle kinds happen to carry four kinds of evidence. Its length does not vary with the
  event where a model's will, so any dimension rewarding completeness or concision is scored against
  a constant for one arm. Already recorded in `docs/thesis_notes.md`; it belongs in the scorer's
  briefing too.

## 10. Defects in the specification, found while writing this

Four, in the order they were found. The first three are amendments owed before building; the fourth
is already fixed.

1. **`db-002`'s columns do not match `ai-001`.** The `hypotheses` table has no `summary` and no
   `recommended_human_action` column at all, and names three fields differently — `title`,
   `uncertainty`, `alternatives` against `hypothesis_title`,
   `evidence_against_or_uncertainty`, `alternative_explanations`. Nothing can be persisted until
   this is fixed, and the first migration's own comment explains the urgency: a column added late,
   after a campaign has run, is a campaign that has to be repeated.
2. **N generations contradicts temperature 0** (§8). The gate item should be amended to name the two
   separate things it was conflating.
3. **The scoring stratification is unsatisfiable** (§9). The gate item should be amended to stratify
   on bundle kind.
4. **`ai-007`'s two triggers are not two triggers for the hosted arm.** It fires on "a model response
   that fails Pydantic validation **or** the grounding check". But `ai-004` uses the provider's native
   schema-constrained output, which makes schema conformance a *generation-time* guarantee — so for
   the hosted arm a validation failure cannot happen in the ordinary course. If one does, it means the
   provider broke its own constraint, which is a different and much more alarming event than an
   ungrounded claim, and it should be logged distinctly rather than folded into a retry count. The
   retry ceiling is, in practice, about grounding failures.

## 11. What this deliberately does not decide

- **The prompt.** Named as the largest open variable in §2 and left to `ai-004`, where it can be
  written against the real derived schema rather than imagined.
- **The hosted provider and model.** A dated identifier is required; which one is a procurement
  question, not a design one, and the interface is provider-agnostic precisely so it is not settled
  here.
- **Whether the local arm happens** (§7) — deferred with a stated trigger and a stated reason why
  deferral is safe for this item and not for the others.
- **The rubric.** `docs/scoring_rubric.md` is pre-registered and may not be edited after the campaign
  starts. §9's two observations are inputs to a decision about it, made deliberately and recorded,
  not a quiet edit.

## 12. Build order

1. **`db-002`** — the two missing columns and the three renamed ones. Independent of every decision
   above, and the only item here that gets *more* expensive with every day it waits.
2. **Amend `ai-007` and the two gate items** per §10.
3. **`ai-009`**, the run-level call budget, and the per-call token and cost logging it needs. Before
   the first real call, not after the first surprise.
4. **`ai-007`**, bounded retry. Also before the first real call: the realistic route to an unexpected
   bill is a loop bug.
5. **`ai-004`**, the hosted arm — prompt first, reviewed, then the adapter, with tests that mock the
   provider and never make a real call.
6. **`ai-008`**, the grounding check. Unusually cheap to validate, because the template generator is
   an input whose correct answer is known in advance: anything it flags on a template hypothesis is a
   defect in the check.
7. **Revisit the local arm** (§7) with the hosted arm's measured reliability in hand.
