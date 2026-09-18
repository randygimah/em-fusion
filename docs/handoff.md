# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
it fuses replayed aviation telemetry and synthetic RF observations through a Data Abstraction Layer,
detects deviations deterministically, and turns evidence bundles into schema-validated,
grounding-checked AI hypotheses for an analyst to review. Decision support, never autonomous
decision-making.

This session built `anom-007`, the sensor-fault rule — the step the whole reportable-rule ordering
was waiting on, because `anom-013` assumes it claims the runs whose truth is a broken receiver and
that assumption had never been tested. It then settled `anom-012`'s radius, which was blocked on
that same assumption — and found, on the way, that the curve the radius would have been chosen from
had been measured on inputs the rule never receives. It finished with `anom-013`, the precedence
that makes the ordering a declaration rather than a coincidence; settled `anom-005`'s gating question
and built it; and found that `anom-006` cannot honestly be built on the corpus as it stands. **All
three reportable rules that can be built now are built**, and the ladder has been measured end to end.

## Current state

**`anom-007`, the `anom-012` amendment, `anom-013` and `anom-005` are all built, measured and
green.** **96 spec items, 41 passing** (`scn-007` and `anom-014` added, unbuilt by design).
Backend suite **889 passed, 99.92% coverage**. `anom-005`: 38 tests, 100% module coverage, every
genuine mutant killed and one proven equivalent.

### The ladder, end to end over all 240 runs — the measurement `anom-013` shipped without

| Staged | Runs | Decided as specified |
|---|---|---|
| `rf-sensor-fault` | 60 | **60** |
| `gnss-degradation` | 60 | **60** |
| `ambiguous-mixed-evidence` | 20 | 20, as a sensor fault by design |
| `aircraft-coverage-gap` | 80 | 75 correctly silent |
| `normal-baseline` | 20 | 19 correctly silent |

**No zone in any run received two answers** — `anom-013`'s first failure case, and it does not occur.

Two things that look like failures and are not: 6 runs staging nothing on the RF grid raise a sensor
fault (`anom-001`'s own false-positive rate promoted one layer, owned by `anom-014`); and 6 runs carry
a second anomaly of the other type in a **different zone** (the guarantee is one answer per *zone*,
never per run).

**Do not read the 75 of 80 coverage-gap row as a result.** Those non-detections are correct only
because `anom-006` is unbuilt — silent for want of a rule, not because it judged and declined.

### `anom-005` is built, and the end-to-end run found two defects the unit tests could not

It fires on the **RF pattern alone** — a zone `anom-007` declined as environmental — and carries the
excess as three-valued corroboration. Confidence has a **floor of Medium the track side cannot
breach**; the rule never emits Low.

1. **160 zones from 60 events.** Both receivers in an incident are dismissed as environmental, each
   naming the other, so one zone per dismissal reports the same event twice. Every unit test had used
   a single dismissal — not what `anom-007` actually emits. Fixed by merging on `anom-007`'s own
   naming, with chaining; the corpus now yields **61 zones for 61 events**.
2. **An unstated contract between two items.** `anom-013` suppresses cross-rule only, deliberately —
   which is safe only if each rule emits one claim per event. Neither document said so, and only
   running them together exposed it.

**The no-gate decision got much stronger after it was made.** Per event: corroborated 7, not
corroborated 7, **not measurable 47** of 61. A gate would report **7 of 60**, not 26 of 40. On this
corpus the track side is absent in three quarters of cases and confirms in about one in nine — so any
claim about *fusion* must be stated as what it is: the radio evidence with an occasional corroborating
note. Backend suite: **851 passed, 99.92% coverage** with the database
(`make test-backend`). Lint and mypy clean. `anom-007`: 49 tests, 100% module coverage, **27 of 28
mutants killed, no survivors** (the 28th site removed as a redundant guarantee). The `anom-012`
amendment: 3 new tests plus one replaced, **5 of 5 killed**. `anom-013`: 24 tests, 100% module
coverage, **16 of 16 killed**.

### `anom-013` is built, and it resolves claims rather than rules

That scoping is what made it finishable with two of its three rules unbuilt: each rule emits a bid
for a zone, the ladder sorts bids by a declared constant and returns at most one per zone with a
ledger. `anom-006` and `anom-005`'s only obligation to it is to emit a claim. The alternative — a
resolver that calls the three rules — could only have been proved against stubs, which is the
arrangement that let `anom-007` pass 36 tests and a mutation pass while being wrong about the corpus.

Decisions worth not re-deriving: **suppression is cross-rule only** (two broken receivers are two
events; suppressing within a rule would cap each rule at one finding per run); **an undecided verdict
is not a claim** (both of `anom-007`'s declines pass the zone on, or "I cannot decide" becomes
"nobody may decide"); **a claim whose rule has no declared position is refused**, never appended.

The zone-identity radius defaults to the layout's 70 km discrimination radius and is **recorded as
provisional**: an `anom-005` zone may span a centre and its neighbours, up to ~120 km across, and two
claims at opposite ends of one incident would then both be reported. Revisit when `anom-005`
produces a zone rather than guessing its shape now.

**What it ships without:** only `anom-007` produces claims, so the ladder cannot run end to end and
no corpus measurement of it is possible until `anom-005` lands.

### `anom-012`'s radius is 60 km, and the curve behind it was re-measured first

The recorded curve — 16/23/31 of 40 at 30/45/60 km — was measured with the centre and window taken
from **ground truth**. In production both come from a detected episode (`api-009`), and `anom-007`
had just established that an episode is not an incident. Measured over batches 2 and 3: the longest
`anom-001` episode on a run has a median length of **90 s** against a staged 300 s, while
`anom-007`'s window (seeded by episodes, bounded by readings) has a median of **320 s**. Six of 86
runs produce a **zero-length** episode, which divided by zero inside `measure_rate_excess`.

Re-scored at the same pre-registered thresholds (1.79 / 1.79 / 1.58) with the realistic window:
**18 / 21 / 26 of 40** at 30 / 45 / 60 km, against 15 / 20 / 28 from ground-truth windows. The curve
survives and flattens; nothing was withdrawn.

**The control arm was also wrong.** Of the 120 runs in batches 2–3, those reaching a fusion decision
at all are **40 of 40 `gnss-degradation`, 0 of 40 `aircraft-coverage-gap`, 1 of 40
`rf-sensor-fault`** — the ordering removes the arm every specificity figure was measured against, and
the arm that could actually cause a false interference call never occurs. With no false-positive
pressure the curve is read at its sensitive end, which `anom-013` predicted and this measures.

60 km also happens to be `scn-002`'s own configured incident radius, so the disc matches the zone it
measures — configuration, not per-run ground truth, and the basis `anom-004` already used.

### The measurement the item owed

Over all 240 stored runs, baseline built from the 20 quiet ones, `anom-001` at its shipped 6/10/15 dB
bands:

| scenario | runs | claims the staged incident | fires elsewhere | faults per run |
|---|---|---|---|---|
| rf-sensor-fault | 60 | **60** | 5 | 1.13 |
| gnss-degradation | 60 | **0** | 5 | 0.08 |
| ambiguous-mixed-evidence | 20 | 20 | 1 | 1.20 |
| aircraft-coverage-gap | 80 | 0 | 5 | 0.06 |
| normal-baseline | 20 | 0 | 1 | 0.05 |

**The ordering assumption holds: 60 of 60, on the right receiver, inside the right window.**
`anom-012`'s radius can now be read from the sensitive end of its curve — 31 of 40 at 60 km — which
is the decision that has been blocked since `anom-013` was written. It is *not yet made*.

### The defect that measurement found, and the correction

Built as first amended, the rule read a neighbour's nominality off `anom-001`'s **episodes**. That
gave the same 60 of 60 — and also claimed **21 of 60 gnss-degradation runs**, on a staged receiver
inside the staged window: the same misattribution `anom-013` exists to remove, in the opposite
direction.

Cause: `scn-002`'s elevation is 8 dB scaled per tick by `1 + 0.25·N(0,1)` against a 6 dB threshold,
so about one tick in six falls short and ends the episode. A staged cell emits a **median of six
episodes** where the incident is one, and two receivers loud through the same 300 s can have
fragments that never overlap. Measured over the 120 staged runs, the neighbours in those windows sat
**2.51 dB above their own baselines at the 5th percentile and 4.46 at the median — and not one of the
37 crossed the 6 dB threshold there.**

Corrected to read the neighbours' **readings** against their own baselines, which is what the item's
original wording had asked for. 21 → 0 misattributions, 60 catches kept. Episodes are now the *seed*
and readings the *boundary*, which also took faults per sensor-fault run from about five to 1.13 at a
median span of exactly the staged 300 s.

The bar — 2 dB — is measured, not chosen: touched neighbours reach 2.51 dB at the 5th percentile,
untouched ones 1.58 dB at the 95th, and the choice is a plateau (1.0 and 1.5 dB give the same result,
3.0 gives 5, 4.0 gives 7).

### Two findings recorded as limitations, not defects

- **The confidence bands have no corpus behind them.** All 240 runs are narrowband, so every fault
  raised is High. Medium and Low exist only in unit tests and must not be quoted as measured until a
  broadband arm is generated.
- **The ambiguous scenario resolves 20 of 20 as a broken receiver, at High confidence, with no trace
  of ambiguity.** It follows from `scn-002` staging that type on a single receiver and from
  `anom-013` offering a claimed zone to no later rule. A **threat to the validity** of any evaluation
  treating that type as a test of whether the system can express uncertainty.
- Runs staging nothing on the RF grid still raise a fault on **6 of 100** of them (down from 14 of
  100): `anom-001` false positives promoted one layer up. Now owned as **`anom-014`**, specified and
  deliberately unbuilt — building it changes `anom-001`, and every detection figure in the project
  was measured through `anom-001`. See below.
- **At the chosen radius and threshold the excess fires on 26 of 40 interference runs.** Used as a
  *necessary* condition `anom-005` would lose 14 of them. Whether that rule should gate on this
  quantity at all, or carry it as evidence strength while firing on the radio pattern, is `anom-005`'s
  decision and is now the most consequential open question in detection.

### `anom-005` does not gate on the rate excess — decided, recorded, unbuilt

The trade-off curve answers a question the rule does not face. Measured over batches 2–3 plus the 20
quiet runs, the zones reaching `anom-005` are **40 of 40 gnss-degradation, 0 of 40
aircraft-coverage-gap, 0 of 20 normal-baseline, 1 of 40 rf-sensor-fault** — and that one leak carries
a zero-length window. A gate would report 26 of 40 and **reject nothing**, because nothing false
arrives there.

What settles it: the 14 zones a gate would lose all hold **4 or fewer** track findings in the whole
run (5 hold none during the window, 2 none anywhere), against a median ratio of 3.87 and p75 of 11.47
over all 40. The gate would reject an interference report **on the grounds of low traffic density at
the staged location**. The threshold is kept but **demoted to a confidence boundary**, three-valued
in `anom-007`'s shape, the third band being *too little traffic to judge*.

Limitation on the record: the corpus has no multi-receiver RF anomaly that is *not* interference, so
the gate's benefit is **unmeasurable, not measured-zero**. Decision stands — an unmeasurable benefit
against a cost measured at 14 of 40 — and reopens if such an arm is generated.

### `anom-006` is blocked by the corpus, not by its design — specified, not built

Its **defensive job is already done**: 0 of 40 coverage-gap runs reach `anom-005`, so the
misattribution it exists to prevent cannot occur. What remains is the positive claim, and:

- Over 40 seed-matched pairs: **16.1 findings against the control's 15.1, and never fewer** (23
  greater, 17 tied, **0 lower**). Real beyond doubt, and one in fifteen.
- **Zone-level scoring is at chance** — 7:3, 5:4, 4:2 at 20/40/60 km cluster radii. The machinery
  *destroys* a signal raw counting preserves: a ratio over a disc of 1–3 findings is dominated by the
  smoothing term, so a maximum across zones selects small-sample noise.
- Building it as specified would be **actively wrong**: it would fire on every quiet run (~15
  findings, no RF anomaly) and destroy `anom-008`'s control.

**Root cause is `scn-006`'s own recorded open question** — the limiting quantity is how many aircraft
a run stages on. Mean **1.7 per run, 11 of 40 stage nothing at all**. Now written as **`scn-007`**.

### Two items blocked on one act

`scn-007` and `anom-014` both require regenerating the batches, which invalidates every detection
figure measured through them. **Recorded on both: when a regeneration happens, both land in it and
every figure is re-measured together** — one invalidation instead of two, and one set of conditions
for the re-measured figures.

## Files in flight

Tree is clean apart from the documentation commit this handoff belongs to. The frontend changes
listed at session start (`nav-001` work) are untouched and still uncommitted.

## Changed

- `6fc857b` spec: amend anom-007 — the three-valued verdict, the confidence bands, the measurement it owed
- `98b1834` test: add tests for anom-007
- `b7cf93c` feat(anom-007): the sensor-fault rule - tests pass
- `e59db8b` spec: correct anom-007 — the neighbour test reads readings, not episodes
- `d6580e1` test: rewrite anom-007 tests for the readings-based neighbour test
- New: `backend/app/detection/sensor_fault.py`, `backend/tests/test_anom_sensor_fault.py`
- Progress note republished as **version 25** — new section "Step two, and the thing it caught
  in itself", with a figure of the fragmented incident and one of the two neighbour
  populations; the ambiguous row of the ladder table corrected (it stages one receiver, so
  step two claims it); the held-back radius panel released; counts to 39/94, 824 tests, 99.92%
- `03b5caf` spec: amend anom-012 for the real window source and the radius; add anom-014
- `c4be93d` test: add tests for the anom-012 amendment
- `f778cf1` feat(anom-012): the radius, the real window source, and a zero-length refusal - tests pass
- `45dde95` spec: amend anom-013 — the ladder resolves claims, not rules
- `a808fa0` test: add tests for anom-013
- `32d0d2b` feat(anom-013): the reportable rule precedence - tests pass
- `b29f1cf` spec: anom-005 does not gate on the rate excess
- `d142b91` spec: anom-006 is blocked by the corpus, not by its design; add scn-007
- `12389d3` docs: the anom-005 gating decision and the anom-006 blocker
- `38cea7f` spec: correct anom-005's confidence design; qualify anom-012's figures
- `2b22a13` test: add tests for anom-005
- `35a3945` feat(anom-005): the fusion rule - tests pass
- New: `backend/app/detection/fusion.py`, `backend/tests/test_anom_fusion.py`
- Progress note republished as **version 26** — new section "The ladder is built, and what it
  said about two hundred and forty hours", with a figure comparing what the system reports
  (60 of 60) against what a gate would have reported (7 of 60), and the corroboration
  breakdown beneath it (7 confirmed / 7 measured-and-quiet / 47 unmeasurable). Carries the
  honest fusion statement, the 75-of-80 row flagged as not-a-result, and the one-event-one-zone
  defect as a worked example. Counts to 41/96, 889 tests, and the next-step tier rewritten
  around the regeneration decision.
- New: `backend/app/detection/precedence.py`, `backend/tests/test_anom_precedence.py`
- Updated: `docs/spec.jsonl` (anom-007 amended twice then `passes: true`; anom-012 amended with six
  decisions then `passes: true`; **anom-014 added**, `passes: false` by design), `CLAUDE.md` repo map,
  `docs/thesis_notes.md` (eight new Implementation subsections), `docs/qa.md` §72 and §73 plus four
  glossary terms
- Changed in `rate_excess.py`: `DEFAULT_RADIUS_KM = 60.0` and `ExcessPolicy.radius_km` defaults to it
  (**a reversal** — the test asserting no default is replaced, not deleted); a zero-length window is
  refused; the docstring now names `anom-007`'s assessment as the window source

## Failed attempts

- **The first implementation was wrong and the tests could not have caught it.** 36 unit tests
  passed, the mutation pass killed 18 of 20, and the rule still misattributed 21 of 60 interference
  runs. The unit tests construct clean, unfragmented episodes; the corpus does not. **The mutation
  score was measuring the tests against the code, and both shared the same wrong assumption.**
- The wrong assumption, recorded on the item that morning, was mine: *a neighbour with no reported
  anomaly is a neighbour reading normally.* It is not. A threshold tuned so that crossing it means
  something says nothing about what not crossing it means.
- **The first pass of the measurement scored a fire as correct if it named a staged sensor**, without
  checking the window. That counted a spurious episode on a staged receiver as a hit. Re-run with the
  window checked, which is what exposed the fragmentation.
- Two containerised script runs failed before producing anything: `SourceType.SYNTHETIC` (the member
  is `SYNTHETIC_RF`) and `DataMode.SIMULATED` (it is `SYNTHETIC`). A third failed with
  `ModuleNotFoundError: No module named 'app'` — `python /tmp/x.py` puts */tmp* on `sys.path`, not the
  working directory; `PYTHONPATH=/app` fixes it. Do not mount a script into `/app`, which is itself a
  bind mount of `./backend` and leaves empty files on the host.
- Three defects in the rewritten tests, all mine: a generator passed where a tuple of findings was
  needed (silently consumed, zero faults), a wrong expectation for the adjacent-channel ring when two
  neighbouring channels are both raised, and `TrackPayload` built with OpenSky field names rather
  than the DAL's pseudonymised ones.
- **I invented the pre-registered thresholds** in the first re-measurement script (1.55/1.32/1.19).
  The real ones are **1.79 / 1.79 / 1.58**, recorded in the scratchpad pre-registration. Caught
  before the run finished and the run was restarted; had it not been, the whole re-measurement would
  have been scored against numbers that were never pre-registered.
- Three further scripting failures before that run produced anything: `detect_track_gaps` returns a
  tuple, not an object with `.findings`; `save_findings` takes the session *factory*, not a session;
  and the zero-length window crashed the rule itself, which turned out to be the defect rather than a
  script bug.
- `anom-013`'s tests were written expecting a `DEFAULT_ZONE_RADIUS_KM` constant, where `anom-007`'s
  established pattern is a `None` that defers to the layout. Changed the test to match the codebase
  rather than adding a redundant constant — the test had never passed, so nothing was weakened.

## Next step

**The detection layer is now blocked on one decision, and it is the user's: regenerate the corpus, or
keep building around it?** Nothing further in detection is honestly measurable without it.

1. **`scn-007` + `anom-014` together, in one regeneration.** Both are specified and unbuilt, both
   invalidate every detection figure measured through the current batches, and they now block a third
   thing: `anom-006` cannot be built until `scn-007` lands, and `anom-005`'s corroboration is absent
   in 47 of 61 zones for the same underlying reason — a mean of 1.7 staged aircraft per run. Doing
   them together converts three separate invalidations into one, and gives every re-measured figure a
   single set of conditions to be reported under.
2. **`anom-006`**, only after `scn-007`, repeating the seed-matched pair measurement before any
   threshold in it is chosen.
3. `anom-003`, the z-score, which carries the `db-008` extensibility prediction scored once as a
   partial. Independent of the regeneration question, so buildable now if the answer is "not yet".
4. **`evb-001`**, evidence bundles — also independent, and the natural consumer of what the ladder now
   produces.

### Open and unowned

- ~~A minimum-duration constraint on `anom-001`~~ — now **`anom-014`**, specified and deliberately
  unbuilt. Regenerate and re-measure every batch *together* if it is ever built, never one item at a
  time. **`scn-007` is now blocked on the same act** — do them in one regeneration.
- **The `aircraft-coverage-gap` arm currently has no rule.** It contributes only correct
  non-detections to `eval-002` and must not be reported as though the system had been tested on it.
  A threat to validity, recorded on `anom-006` and visible as the 75-of-80 row above.
- **Fusion is currently the radio evidence with an occasional corroborating note.** 47 of 61 zones
  have no measurable track side. Any write-up claiming multi-source fusion must say so plainly.
- A **broadband generation arm**, without which `anom-007`'s Medium and Low confidence bands have no
  corpus behind them.
- The **frontend suite exits non-zero**: `TypeError: control.runs.map is not a function` at
  `scenarioControl.tsx:344`. Needs a spec item covering both the test stub and `useScenarioControl`'s
  missing array check.
- `adp-008` exclusion applied to baseline windows; a detection-latency definition (gates `anom-009`);
  `api-011`; `nav-002`; reset/replay endpoints; `ops-002` (CI); `docs/qa.md` duplicate §47 (fix by
  note, never renumber); frontend coverage tooling; `pnpm format`; root `make check` never run in
  full; mypy does not check `tests/`.
