# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
it fuses replayed aviation telemetry and synthetic RF observations through a Data Abstraction Layer,
detects deviations deterministically, and turns evidence bundles into schema-validated,
grounding-checked AI hypotheses for an analyst to review. Decision support, never autonomous
decision-making.

This session built `anom-007`, the sensor-fault rule — the step the whole reportable-rule ordering
was waiting on, because `anom-013` assumes it claims the runs whose truth is a broken receiver and
that assumption had never been tested.

## Current state

**`anom-007` is built, measured, corrected, re-measured and green.** 94 spec items, 39 passing.
Backend suite: **824 passed, 99.92% coverage** with the database (`make test-backend`). Lint and
mypy clean. 49 tests on this item, 100% coverage on the module, **27 of 28 mutants killed and no
survivors** (the 28th site was removed as a redundant guarantee).

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
  100): `anom-001` false positives promoted one layer up. A minimum-duration constraint belongs to
  `anom-001`, not here, and is unowned.

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
- Updated: `docs/spec.jsonl` (anom-007 amended twice, then `passes: true`), `CLAUDE.md` repo map,
  `docs/thesis_notes.md` (four new Implementation subsections), `docs/qa.md` §72 plus two glossary
  terms

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

## Next step

1. **Choose `anom-012`'s radius.** It is unblocked for the first time: `anom-007` claims 60 of 60
   sensor-fault runs, so `anom-005`'s remaining discrimination is interference against nothing rather
   than interference against a fault, and the radius is read from the sensitive end — 31 of 40 at
   60 km. Record the choice on `anom-012` with the argument, not just the number.
2. **Build `anom-013`**, the precedence, which now has all three of its inputs measured.
3. `anom-006` (SOURCE-GAP) and `anom-005` (FUSION-SPATIAL, amended onto `anom-012`).
4. `anom-003`, the z-score, which carries the `db-008` extensibility prediction scored once as a
   partial.

### Open and unowned

- A **minimum-duration constraint on `anom-001`**, which would remove the residual 6 of 100
  false-positive rate this item surfaced. Needs its own spec item.
- A **broadband generation arm**, without which `anom-007`'s Medium and Low confidence bands have no
  corpus behind them.
- The **frontend suite exits non-zero**: `TypeError: control.runs.map is not a function` at
  `scenarioControl.tsx:344`. Needs a spec item covering both the test stub and `useScenarioControl`'s
  missing array check.
- `adp-008` exclusion applied to baseline windows; a detection-latency definition (gates `anom-009`);
  `api-011`; `nav-002`; reset/replay endpoints; `ops-002` (CI); `docs/qa.md` duplicate §47 (fix by
  note, never renumber); frontend coverage tooling; `pnpm format`; root `make check` never run in
  full; mypy does not check `tests/`.
