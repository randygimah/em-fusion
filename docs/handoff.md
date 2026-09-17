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
had been measured on inputs the rule never receives.

## Current state

**`anom-007` and the `anom-012` amendment are both built, measured and green.** 95 spec items,
39 passing. Backend suite: **827 passed, 99.92% coverage** with the database (`make test-backend`).
Lint and mypy clean. `anom-007`: 49 tests, 100% module coverage, **27 of 28 mutants killed, no
survivors** (the 28th site removed as a redundant guarantee). The `anom-012` amendment: 3 new tests
plus one replaced, **5 of 5 mutants killed**.

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

## Next step

1. **Build `anom-013`**, the precedence. All three of its inputs are now measured, and the
   measurement above gives it something it did not have: the runs that actually reach each step.
2. **Decide whether `anom-005` gates on the rate excess.** At 60 km and the pre-registered threshold
   it fires on 26 of 40 interference runs, so as a necessary condition it loses 14. The alternative is
   to fire on the radio pattern and carry the excess as evidence strength in the bundle. This is the
   decision the whole ordering argument has been converging on and it should be taken deliberately,
   with the 8 dB versus Youden's-J-0.3 asymmetry in front of it.
3. `anom-006` (SOURCE-GAP), then `anom-005` itself.
4. `anom-003`, the z-score, which carries the `db-008` extensibility prediction scored once as a
   partial.

### Open and unowned

- ~~A minimum-duration constraint on `anom-001`~~ — now **`anom-014`**, specified and deliberately
  unbuilt. Regenerate and re-measure every batch *together* if it is ever built, never one item at a
  time.
- A **broadband generation arm**, without which `anom-007`'s Medium and Low confidence bands have no
  corpus behind them.
- The **frontend suite exits non-zero**: `TypeError: control.runs.map is not a function` at
  `scenarioControl.tsx:344`. Needs a spec item covering both the test stub and `useScenarioControl`'s
  missing array check.
- `adp-008` exclusion applied to baseline windows; a detection-latency definition (gates `anom-009`);
  `api-011`; `nav-002`; reset/replay endpoints; `ops-002` (CI); `docs/qa.md` duplicate §47 (fix by
  note, never renumber); frontend coverage tooling; `pnpm format`; root `make check` never run in
  full; mypy does not check `tests/`.
