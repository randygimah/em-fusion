# Handoff

## Goal

EM Fusion is a human-in-the-loop AI prototype for explainable electromagnetic situational awareness:
it fuses replayed aviation telemetry and synthetic RF observations through a Data Abstraction Layer,
detects deviations deterministically, and turns evidence bundles into schema-validated,
grounding-checked AI hypotheses for an analyst to review. Decision support, never autonomous
decision-making.

This session took **`anom-006`'s threshold measurement** — the first item the previous handoff
listed, chosen because it was cheap and decisive either way. It was decisive. **`anom-006` is closed
again**, on stronger evidence than the first closure, and the detection layer's remaining work no
longer has a measurement blocking it.

## Current state

**45 spec items passing of 98** — unchanged, because this session closed an item rather than
building one. That is the intended outcome of a measurement whose pre-registered failure branch
fired.

### What `anom-006` asked, and what it got

The regeneration reopened the item on a **paired** result: scoring a staged coverage-gap zone
against its own same-seed control gives **20 wins to 7** at a 20 km cluster radius. The amendment
reopening it recorded that this says nothing about whether a **fixed threshold separates a staged
run from an unstaged one on a single run**, which is the question a detector faces, and demanded
that measurement before any threshold. It has now been taken.

Pre-registered in `backend/measurements/corpus/source_gap_threshold_prereg.md` — populations,
operating-point rule and failure bar fixed in advance — fitted on two base seeds and scored **once**
on the third.

| | Development (2 seeds) | Holdout (1 seed) |
|---|---|---|
| Coverage gaps caught | 7/40 (0.17) | **3/20 (0.15)** — pre-registered bar was 0.25 |
| Quiet runs falsely alarmed | 0/40 | **0/20** |
| **`gnss-degradation` falsely alarmed** | 15/40 | **6/20 (0.30)** |

Operating point: 60 km cluster radius, minimum zone size 4, excess threshold 11.53.

**What closes the item is the third row, not the first.** The rule fires twice as often on the
interference arm as on the coverage gaps it exists to find. `anom-013` orders `SENSOR-FAULT`,
`SOURCE-GAP`, `FUSION-SPATIAL`, so `SOURCE-GAP` **outranks** the interference rule: a wrong firing
can claim the zone before `FUSION-SPATIAL` is offered it. Building it would risk the one arm the
ladder decides correctly 60 of 60 to catch a seventh of an arm nothing judges. Whether those zones
actually overlap was **not measured** — the hazard is established, its size is not.

**Development and holdout agree closely (0.17 / 0.15).** This is a reliable measurement of a weak
effect, not a noisy one. More runs of the same corpus will not change it.

**Ceiling, ignoring the false-alarm constraint:** best Youden's J anywhere is **0.275**, at a 0.38
quiet-arm rate `anom-008` forbids outright. `anom-012` reported 0.23–0.40 on a curve this project
already calls weak.

**Mechanism, as predicted at the first closure:** the statistic saturates. At a size floor of 1
every arm reaches the same maximum ratio (198.78) with medians differing by 0.6, because taking the
maximum across zones selects whichever zone had the fewest findings — `anom-012`'s smoothing
constant dominating a small sample. Separation only appears at a size floor of 4, where a third of
runs no longer qualify.

### A population fact that outlives the item

Verified by **exact** comparison, not summary statistics:

```
normal-baseline        track findings ≡ rf-sensor-fault           (same seed)
aircraft-coverage-gap  track findings ≡ ambiguous-mixed-evidence  (same seed)
```

`tracks.py` gives the coverage-gap and ambiguous arms one `SUPPRESS` mode, and neither the quiet arm
nor the sensor-fault arm perturbs tracks at all. **Any track-side figure quoting 120 negatives is
counting 60 seeds twice**, and the ambiguous arm is not independent evidence about a track-side
rule. Check any figure before re-quoting it.

## Files in flight

Tree is clean. Nothing is part-built: this session added a measurement and closed a spec item.

## Changed

- `9584d74` spec: close `anom-006` again — the threshold measurement it asked for
- `66896df` docs: the `anom-006` threshold measurement written up
- New: `backend/measurements/corpus/source_gap_threshold_sweep.py` and its `.log`,
  `backend/measurements/corpus/source_gap_threshold_prereg.md` (with its change log)
- Changed: `docs/spec.jsonl` (`anom-006` amended, still `passes: false`),
  `docs/detection_layer.md` (ladder row 2 and the coverage-test section rewritten),
  `docs/thesis_notes.md` (Implementation subsection on paired vs single-run tests),
  `docs/qa.md` §79, `backend/measurements/README.md`, `.gitignore` (the zone cache)

## Failed attempts

- **My pre-registration named a scenario arm this project does not have.** It listed
  `rf-interference` as a negative population; the five types are `normal-baseline`,
  `gnss-degradation`, `rf-sensor-fault`, `aircraft-coverage-gap`, `ambiguous-mixed-evidence`. The
  interference arm is `gnss-degradation` — several documents call it "the interference ones" in
  prose, which is what I read it from instead of reading `app/scenario/incident.py`. The column came
  out `0/0`.
- **The same table omitted `ambiguous-mixed-evidence` entirely, and it is not a negative.** It
  shares the positive arm's `SUPPRESS` track mode, so a firing there detects a real staged gap.
  **The decision rule and the bar were unaffected** — both refer only to the coverage-gap and quiet
  arms, both correctly identified — so the verdict stands, but the reporting had to be corrected.
  Recorded in the prereg's change log rather than silently fixed.
- **My first sweep's print filter hid the entire decisive region.** It printed thresholds 1.0, 2.0
  and 3.0, where the statistic is saturated and every arm fires identically, and never printed the
  region above 10 where the arms part. It had computed those rows and discarded them. The first
  output therefore looked like a bug (`40/40  40/40  40/40` across every arm) when it was a real
  property of the statistic shown at useless thresholds.
- **My first operating-point search selected a rule that fires on nothing.** "Maximise sensitivity
  subject to zero false alarms" is satisfied vacuously at a size floor of 8, where no run of any arm
  produces a qualifying zone. It picked exactly that and printed the right verdict for the wrong
  reason. The search now requires at least one true positive, and thresholds come from the observed
  values rather than a fixed grid that can step over the only interesting point.
- **The identical columns were nearly dismissed as an aliasing bug.** They were not: two arm-pairs
  genuinely produce identical track findings. **Byte-identical columns are never a coincidence and
  should always be chased** — this one turned into a standing correction to how negatives are
  counted.
- **Rebuilding the script by splicing dropped a module constant** (`CACHE`), which failed
  immediately with a `NameError`. Cost one run; caught because the script fails at import rather
  than silently.

## Next step

`anom-006` is settled, so the two items the previous handoff listed behind it are now the whole of
the near-term detection work. The order is a recommendation, not a constraint.

1. **`evb-001`, evidence bundles.** Now the clear first item. It is the natural consumer of what the
   ladder produces, the gateway to Phase 9 — the AI hypothesis layer, which is the project's actual
   contribution — and **the one remaining item no corpus change can invalidate**, because a bundle
   groups what the rules already emit and its shape does not depend on the data.
2. **`anom-003`, the z-score detector.** Carries the `db-008` extensibility prediction, scored once
   as a partial. Genuinely measurable now that the corpus is stable and homogeneous.

### Open and unowned

- **The `aircraft-coverage-gap` arm has no rule, and this is now settled rather than pending.** Its
  60 of 60 correct non-detections are correct only because nothing judges that arm. It must not be
  reported as though the system had been tested on it. **What would change it is a generator change,
  not a detector one** — a coverage gap must become a zone-level event separable from a staleness
  freeze. Both closures of `anom-006` reached that conclusion independently.
- **Unmeasured, and recorded rather than assumed:** whether a wrongly-claimed `SOURCE-GAP` zone on
  an interference run would actually overlap the `FUSION-SPATIAL` zone. The sweep kept no centroids.
- **Fusion is still the radio evidence with an occasional corroborating note.** 41 of 60 reported
  zones have no measurable track side. Any write-up claiming multi-source fusion must say so plainly.
- **Corpus v1 is still in the database** and always will be (`db-007`). Every measurement must go
  through `measurements/corpus/_corpus.py`. Still selecting runs by other means and unchecked since
  the regeneration: `cluster_background.py`, `cluster_separation_after_scn006.py`,
  `track_gap_hit_rate.py`, `track_gap_recall.py`, `staging_on_ground.py`,
  `cluster_leak_into_fusion.py`, `rate_excess_two_forms.py`, `sensor_fault_fragmentation.py`,
  `sensor_fault_neighbour_candidates.py`.
- **`DEFAULT_AFFECTED_FRACTION` is inert.** With a mean eligible pool of 23.4, `round(0.08 × 23.4)`
  is 2 and the floor of 5 always wins, so every v2 run stages exactly five aircraft. Nobody should
  read the fraction as doing work.
- A **broadband generation arm**, without which `anom-007`'s Medium and Low confidence bands have no
  corpus behind them. All 300 v2 runs are narrowband, as all 240 v1 runs were.
- The **frontend suite exits non-zero**: `TypeError: control.runs.map is not a function` at
  `scenarioControl.tsx:344`. Needs a spec item covering both the test stub and
  `useScenarioControl`'s missing array check.
- `adp-008` exclusion applied to baseline windows; a detection-latency definition (gates `anom-009`);
  `api-011`; `nav-002`; reset/replay endpoints; `ops-002` (CI); `docs/qa.md` duplicate §47 (fix by
  note, never renumber); frontend coverage tooling; `pnpm format`; root `make check` never run in
  full; mypy does not check `tests/`.
