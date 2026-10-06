"""The detection layer's results table, over the whole corpus. Spec: eval-002.

Everything before this measured one rule. This runs the whole chain over
every run of the corpus, scores what reached an analyst against the answer
key `scn-002` wrote at generation time, and prints the figures the detection
chapter quotes. **Precision, F1 and detection latency have never been
computed on real data at all** -- `anom-009` has a unit suite and a mutation
pass and has never been pointed at a run.

Six things it is careful about, all of them `eval-002`'s amendment:

**Recall here is per run and is not `anom-011`'s.** That one is per staged
aircraft on the track side and reads twenty-three points lower. Both are
printed, each under its own denominator, and neither is averaged into the
other. The per-aircraft figures are read from
`measurements/corpus/track_gap_recall.log` and passed in rather than
recomputed, so there is one measurement of them and not two.

**Recall is indexed by truth and precision by prediction**, so the arm table
and the type table are separate. A row carrying both would put two
denominators under one name.

**A misreport is two errors** -- a miss for the type staged and a false
alarm for the type claimed -- so the classification is one multi-class
confusion and the matrix is printed whole.

**Two false-positive rates.** `normal-baseline` asks whether the system
invents an anomaly from nothing; `aircraft-coverage-gap` asks whether a real
track-side disturbance leaks into a radio verdict. They are never pooled.

**Latency is conditional on detection**, reported over the claims that were
made with the count it was taken over.

**The false-positive rate is refused unless `anom-008` passes on every quiet
run.** That is what separates a layer that behaved from a pipeline that
never ran, and it is enforced by the metrics rather than by this script.

Note that the detectors are re-run here rather than read from
`detection_findings`: the stored findings are whatever the last measurement
wrote, and a results table must not depend on which script ran last. Since
`anom-017` they are re-run **without storing** -- every pass is rolled back --
so this script also leaves the store exactly as it found it.

Run:  make measure SCRIPT=corpus/detection_metrics.py
"""
from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

import _corpus
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location,
                            Provenance, RfPayload, SourceType, TrackPayload,
                            ValidationStatus)
from app.db.findings import save_findings
from app.detection.clustering import cluster_track_gaps
from app.detection.control import audit
from app.detection.findings import from_track_gap
from app.detection.fusion import claims_from_interference, detect_interference
from app.detection.latency import measure as measure_latency
from app.detection.precedence import (PrecedenceError, claims_from_sensor_faults,
                                      resolve)
from app.detection.rf_noise import detect_rf_noise
from app.detection.sensor_fault import detect_sensor_faults
from app.detection.track_gap import detect_track_gaps
from app.evaluation.export import DetectionProvenance, export_metrics
from app.evaluation.metrics import STAGED_TYPE, RunOutcome, TrackSideRecall, compute
from app.dal.models import ScenarioRunSummary
from app.detection.chain import assess_without_storing, measure_normality
from app.detection.settings import (BASELINE_QUIET_RUNS, BASELINE_WINDOW,
                                    POLICIES_OF_RECORD)
from app.scenario.layout import load_layout

#: `anom-015` then `anom-016`. The eight rules are composed in
#: `app/detection/chain.py` and the settings they run under live in
#: `app/detection/settings.py`, which together is the whole of those two items:
#: this file held the only copy of both, and `measurements/` is outside ruff,
#: mypy, pytest and the coverage gate. **The values are unchanged** -- eleven
#: numbers moved, byte for byte, from here to there -- and the gain is that the
#: application now reads a run under the same settings every figure below was
#: measured under, where before a trigger inside `app/` would have had to declare
#: a third copy with the same standing as this one.
POLICIES = POLICIES_OF_RECORD

#: `anom-011`'s figures, read off the final block of `track_gap_recall.log`
#: ("v2, every batch"). Not recomputed: two measurements of one quantity
#: eventually disagree, and the one that gets quoted is then whichever script
#: ran last.
TRACK_SIDE = {
    "gnss-degradation": TrackSideRecall(staged_aircraft=300, detected_aircraft=247),
    "aircraft-coverage-gap": TrackSideRecall(staged_aircraft=300, detected_aircraft=176),
    "ambiguous-mixed-evidence": TrackSideRecall(staged_aircraft=300,
                                                detected_aircraft=176),
}

#: Where eval-003's files land. Committed, because they are the inputs a
#: thesis table is built from and they are small. **Its own directory**, not
#: shared with the campaign's: the two halves were measured on different
#: corpora on different dates -- three hundred generated hours here, the dev
#: batch there -- and one `metrics.json` holding both would invite exactly
#: the reading that they are one measurement.
EXPORTS = Path(__file__).resolve().parents[1] / "exports" / "detection"

print(_corpus.describe())

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)
layout = load_layout()


# `anom-017`. The pinned population, and no longer this corpus's own quiet runs:
# those were sixty, the store's were a hundred, and the store ended up holding
# findings under both. `measure_normality` refuses if the store does not hold
# every pinned run with its pinned seed.
print(f"baseline over the {len(BASELINE_QUIET_RUNS)} pinned quiet runs", flush=True)

# `anom-016`. Built through the application rather than here, for one reason the
# version this replaces got away with: the metric was named twice -- once when the
# table was built and once on `RF_POLICY`, which the deviation is read against.
# Agreeing by hand is not the same as being unable to disagree. It also retires the
# last caller of this file's own observation reader, which `anom-015` had already
# cut back to one use: the reader it replaced invented five fields the row holds,
# and a right answer from a wrong source is `ai-004`'s defect in the input.
NORMALITY = measure_normality(factory, quiet_runs=BASELINE_QUIET_RUNS,
                              policies=POLICIES, window=BASELINE_WINDOW)

with factory.begin() as s:
    runs = s.execute(text(
        f"SELECT id, scenario_type, seed, started_at, completed_at, ground_truth "
        f"FROM scenario_runs WHERE {_corpus.run_filter()} ORDER BY id")).mappings().all()
    # `scn-008` put the base seed on the row precisely so a batch can be
    # re-derived from what it records rather than from what was remembered.
    # Ordered by the earliest run of each batch, which is wave order: the
    # sequence is part of what the corpus is, and the export's digest moves
    # with it.
    _seeds = s.execute(text(
        f"SELECT (parameters->>'base_seed')::bigint AS seed FROM scenario_runs "
        f"WHERE {_corpus.run_filter()} AND parameters->>'base_seed' IS NOT NULL "
        f"GROUP BY 1 ORDER BY MIN(id)")).all()
print(f"scoring {len(runs)} runs", flush=True)

outcomes: list[RunOutcome] = []
controls = {}
undecidable = []

for run in runs:
    kind, run_id, truth = run["scenario_type"], run["id"], run["ground_truth"] or {}

    # One call (`anom-015`). The ordering, the mid-chain persistence and the
    # receivers behind each claim all live in `app/detection/chain.py` now, where
    # the linter, the type checker and the coverage gate can see them.
    # `anom-017` (11): measured and rolled back, so the results table writes
    # nothing -- not the findings, not the stamps, and not the bundles of the
    # twenty runs the scored campaign cites, which `db-011` protects.
    assessment = assess_without_storing(
        ScenarioRunSummary(id=run_id, scenario_type=kind, seed=run["seed"],
                           started_at=run["started_at"],
                           completed_at=run["completed_at"]),
        normality=NORMALITY, policies=POLICIES, layout=layout,
        engine=engine)
    found = assessment.rf
    reported = assessment.reported
    types = sorted({c.anomaly_type for c in reported})

    # What the answer key says was staged, and when it began. An RF arm
    # stages an incident on the grid; the coverage-gap arm stages only on
    # aircraft. `scn-007` records a run that could stage nothing, and such a
    # run is a baseline wearing the wrong label.
    staged = bool(truth.get("sensors")) if kind != "aircraft-coverage-gap" \
        else bool(truth.get("aircraft"))
    window = truth.get("window")

    # Latency over the claims of the type this run staged, taking the
    # earliest: the first instant the system could have said the right thing.
    # Only over a claim of the type the run staged: a delay before an answer
    # that was never given, or before the wrong one, is not a latency.
    expected = STAGED_TYPE[kind]
    seconds = None
    if window and staged and expected in types:
        onset = datetime.fromisoformat(window["start"])
        measured = []
        for claim in reported:
            if claim.anomaly_type != expected:
                continue
            try:
                measured.append(measure_latency(
                    claim, sensors=assessment.receivers_for(claim), onset=onset,
                    episodes=found.anomalies).latency.total_seconds())
            except PrecedenceError as refused:
                undecidable.append((run_id, claim.rule_id, str(refused)[:60]))
        if measured:
            seconds = min(measured)

    outcomes.append(RunOutcome(
        run_id=str(run_id), scenario_type=kind, reported=tuple(types),
        staged=staged and kind != "normal-baseline", latency_seconds=seconds))

    if kind == "normal-baseline":
        # The account `anom-008` grades against comes from the pass, which is the
        # only place every producer is in view -- one hand-written here was a
        # second place for a producer to be forgotten.
        controls[str(run_id)] = audit(
            run_id=str(run_id), scenario_type=kind, counts=assessment.counts)

metrics = compute(outcomes, controls=controls,
                  track_side={k: v for k, v in TRACK_SIDE.items()
                              if any(o.scenario_type == k for o in outcomes)})

print(f"\nRECALL, INDEXED BY TRUTH -- one row per scenario type, over its own runs")
print(f"  {'scenario type':26} {'kind':14} {'runs':>5} {'excl':>5} {'found':>6} "
      f"{'missed':>7} {'recall/run':>11} {'FNR':>7}")
for arm in metrics.arms:
    r = arm.recall_per_run
    f = arm.false_negative_rate
    print(f"  {arm.scenario_type:26} {arm.kind.value:14} {arm.runs:5d} "
          f"{arm.excluded:5d} {arm.detected:6d} {arm.missed:7d} "
          f"{'--' if r is None else f'{r:.3f}':>11} "
          f"{'--' if f is None else f'{f:.3f}':>7}")

print(f"\nPRECISION, INDEXED BY PREDICTION -- one row per reportable type")
print(f"  {'anomaly type':28} {'built':>5} {'claimed':>8} {'right':>6} {'wrong':>6} "
      f"{'precision':>10} {'F1':>7}  arms")
for t in metrics.types:
    p, f1 = t.precision, t.f1
    print(f"  {t.anomaly_type:28} {str(t.built):>5} {t.claimed_runs:8d} {t.correct:6d} "
          f"{t.wrong:6d} {'--' if p is None else f'{p:.3f}':>10} "
          f"{'--' if f1 is None else f'{f1:.3f}':>7}  {list(t.arms)}")
print("  F1 is withheld where two arms produce one type: there is no arm it")
print("  would be about. anom-006 being unbuilt, its row is coverage, not a score.")

print(f"\nFALSE POSITIVES -- two rates, never pooled")
for rate in metrics.false_positive_rates:
    print(f"  {rate.arm.value:14} {rate.scenario_type:26} "
          f"{rate.runs_with_a_report:3d} of {rate.runs:3d} = "
          f"{'--' if rate.rate is None else f'{rate.rate:.3f}'}   "
          f"anom-008 control: {'yes' if rate.controlled else 'no'}   "
          f"reportable types covered: {rate.coverage}")

print(f"\nLATENCY, CONDITIONAL ON DETECTION -- seconds, signed, quantised to 10 s")
print(f"  {'scenario type':26} {'detections':>11} {'measured':>9} {'median':>8} "
      f"{'min':>8} {'max':>8}")
for arm in metrics.arms:
    lat = arm.latency
    if not lat.detections:
        continue
    print(f"  {arm.scenario_type:26} {lat.detections:11d} {lat.measured:9d} "
          f"{'--' if lat.median_seconds is None else f'{lat.median_seconds:.0f}':>8} "
          f"{'--' if lat.min_seconds is None else f'{lat.min_seconds:.0f}':>8} "
          f"{'--' if lat.max_seconds is None else f'{lat.max_seconds:.0f}':>8}")

print(f"\nTRACK-SIDE RECALL (anom-011) -- a different denominator, printed beside")
for arm in metrics.arms:
    if arm.track_side is None:
        continue
    ts = arm.track_side
    print(f"  {arm.scenario_type:26} {ts.detected_aircraft:4d} of "
          f"{ts.staged_aircraft:4d} staged aircraft = "
          f"{ts.recall_per_staged_aircraft:.3f}  (run-level: "
          f"{'--' if arm.recall_per_run is None else f'{arm.recall_per_run:.3f}'})")

print(f"\nCONFUSION -- truth down, reported across. A misreport is two errors.")
for truth_type in sorted(metrics.confusion):
    row = metrics.confusion[truth_type]
    print(f"  {truth_type:26} {dict(sorted(row.items()))}")

# eval-003: the same figures as files, with everything needed to regenerate
# them. The policies are read off the objects the run actually used rather
# than typed out again -- a recorded setting that is not the one in force is
# worse than none, since it looks like provenance.
provenance = DetectionProvenance(
    corpus=_corpus.which(),
    base_seeds=tuple(row[0] for row in _seeds),
    runs=len(runs),
    measured_on=date.today().isoformat(),
    # `anom-015`: the pass's own record rather than a second spelling of it, so
    # the settings the findings were produced under and the settings the export
    # quotes cannot disagree. It also gains the baseline's quiet runs, which this
    # hand-written version never carried -- two passes under identical thresholds
    # and different baselines were indistinguishable in the exported provenance.
    policies=POLICIES.record(NORMALITY, layout=layout),
)
export = export_metrics(detection=metrics, detection_provenance=provenance)
EXPORTS.mkdir(parents=True, exist_ok=True)
for name, text in sorted(export.files.items()):
    (EXPORTS / name).write_text(text)
print(f"\nexported {len(export.files)} files to measurements/exports/detection/, "
      f"every row stamped {provenance.digest}")
for name in sorted(export.files):
    print(f"  {name}")

print(f"\nscored {metrics.runs} runs, excluded {metrics.excluded} for staging nothing, "
      f"{metrics.multi_claim_runs} claimed more than one type")
if undecidable:
    print(f"\nclaims whose latency could not be taken: {len(undecidable)}")
    for row in undecidable[:5]:
        print(f"  run {row[0]} {row[1]}: {row[2]}")
