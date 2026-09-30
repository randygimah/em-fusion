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
wrote, and a results table must not depend on which script ran last.

Run:  make measure SCRIPT=corpus/detection_metrics.py
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path

import _corpus
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, RfPayload, SourceType, TrackPayload,
                            ValidationStatus)
from app.db.findings import save_findings
from app.detection.baseline import RfMetric, compute_rf_baselines
from app.detection.clustering import ClusterPolicy, cluster_track_gaps
from app.detection.control import audit
from app.detection.findings import from_track_gap
from app.detection.fusion import (FusionPolicy, claims_from_interference,
                                  detect_interference)
from app.detection.latency import measure as measure_latency
from app.detection.precedence import (PrecedenceError, PrecedencePolicy,
                                      claims_from_sensor_faults, resolve)
from app.detection.rf_noise import Direction, ThresholdPolicy, detect_rf_noise
from app.detection.sensor_fault import FaultPolicy, detect_sensor_faults
from app.detection.track_gap import BoundingBox, GapPolicy, detect_track_gaps
from app.evaluation.export import DetectionProvenance, export_metrics
from app.evaluation.metrics import STAGED_TYPE, RunOutcome, TrackSideRecall, compute
from app.detection.rate_excess import DEFAULT_RADIUS_KM as EXCESS_RADIUS_KM
from app.detection.rf_noise import DEFAULT_MINIMUM_DURATION
from app.scenario.layout import load_layout

RF_POLICY = ThresholdPolicy(metric=RfMetric.POWER_DBM, direction=Direction.ABOVE,
                            threshold=6.0, medium_at=10.0, high_at=15.0)
FAULT, FUSION, LADDER, CLUSTER = (FaultPolicy(), FusionPolicy(), PrecedencePolicy(),
                                  ClusterPolicy())
BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)
GAP = GapPolicy(threshold=timedelta(seconds=100),
                contact_fresh_within=timedelta(seconds=30), box=BOX)

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
#: thesis table is built from and they are small.
EXPORTS = Path(__file__).resolve().parents[1] / "exports"

BASELINE_WINDOW = timedelta(hours=2)

print(_corpus.describe())

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)
layout = load_layout()


def obs_for(run_id, kind):
    with factory.begin() as s:
        rows = s.execute(text(
            "SELECT timestamp, ST_Y(location) AS lat, ST_X(location) AS lon, payload "
            "FROM observations WHERE scenario_run_id=:r AND observation_type=:t "
            "ORDER BY timestamp"), {"r": run_id, "t": kind}).mappings().all()
    src = SourceType.OPENSKY if kind == "track" else SourceType.SYNTHETIC_RF
    mode = DataMode.REPLAYED if kind == "track" else DataMode.SYNTHETIC
    pl = TrackPayload if kind == "track" else RfPayload
    ot = ObservationType.TRACK if kind == "track" else ObservationType.RF
    return [CanonicalObservation(
        source_id="o", source_type=src, observation_type=ot, timestamp=r["timestamp"],
        location=Location(lat=r["lat"], lon=r["lon"]), data_mode=mode,
        validation_status=ValidationStatus.VALID,
        provenance=Provenance(source_id="o", source_type=src, data_mode=mode,
                              scenario_run_id=run_id),
        payload=pl(**r["payload"])) for r in rows]


with factory.begin() as _s:
    quiet = _corpus.quiet_runs(_s)
print(f"baseline from {len(quiet)} quiet runs of this corpus", flush=True)
table = compute_rf_baselines([o for q in quiet for o in obs_for(q, "rf")],
                             RfMetric.POWER_DBM, baseline_run_ids=quiet,
                             window=timedelta(hours=2))

with factory.begin() as s:
    runs = s.execute(text(
        f"SELECT id, scenario_type, ground_truth FROM scenario_runs "
        f"WHERE {_corpus.run_filter()} ORDER BY id")).mappings().all()
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

    rf = obs_for(run_id, "rf")
    span = (min(o.timestamp for o in rf), max(o.timestamp for o in rf))
    found = detect_rf_noise(rf, table, RF_POLICY)
    faults = detect_sensor_faults(found, rf, table, layout, FAULT)

    tracks = obs_for(run_id, "track")
    gaps = detect_track_gaps(tracks, GAP)
    save_findings(factory, scenario_run_id=run_id, rule_id="TRACK-GAP",
                  findings=[from_track_gap(g, scenario_run_id=run_id) for g in gaps])
    clusters = cluster_track_gaps(factory, scenario_run_id=run_id, window=span,
                                  policy=CLUSTER)

    zones = detect_interference(faults, factory, scenario_run_id=run_id,
                                run_span=span, layout=layout, policy=FUSION)

    # The receivers behind each claim, kept alongside it: a `Claim` carries a
    # centre and a window and `anom-009` needs the receivers whose evidence
    # the rule rested on. The two producers emit in finding order, so this
    # pairs rather than looks up.
    fault_claims = claims_from_sensor_faults(faults, layout)
    zone_claims = claims_from_interference(zones)
    sensors_of = {id(c): (f.sensor_id,) for c, f in zip(fault_claims, faults.faults)}
    sensors_of.update({id(c): z.sensors for c, z in zip(zone_claims, zones.zones)})

    reported = resolve([*fault_claims, *zone_claims], layout, LADDER).reported
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
                    claim, sensors=sensors_of[id(claim)], onset=onset,
                    episodes=found.anomalies).latency.total_seconds())
            except PrecedenceError as refused:
                undecidable.append((run_id, claim.rule_id, str(refused)[:60]))
        if measured:
            seconds = min(measured)

    outcomes.append(RunOutcome(
        run_id=str(run_id), scenario_type=kind, reported=tuple(types),
        staged=staged and kind != "normal-baseline", latency_seconds=seconds))

    if kind == "normal-baseline":
        controls[str(run_id)] = audit(
            run_id=str(run_id), scenario_type=kind,
            counts={("RF-NOISE", "rf_noise_deviation"): len(found.anomalies),
                    ("TRACK-GAP", "track_continuity_gap"): len(gaps),
                    ("TRACK-CLUSTER", "track_gap_cluster"): len(clusters),
                    ("TRACK-GAP", "track_rate_excess"): len(zones.zones)
                    + len(zones.declined),
                    ("SENSOR-FAULT", "possible_sensor_fault"):
                        sum(1 for t in types if t == "possible_sensor_fault"),
                    ("FUSION-SPATIAL", "possible_interference_zone"):
                        sum(1 for t in types if t == "possible_interference_zone")})

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
    policies={
        "BASELINE.window_h": str(BASELINE_WINDOW.total_seconds() / 3600),
        "RF-NOISE.metric": RF_POLICY.metric.value,
        "RF-NOISE.direction": RF_POLICY.direction.value,
        "RF-NOISE.threshold_db": str(RF_POLICY.threshold),
        "RF-NOISE.medium_at_db": str(RF_POLICY.medium_at),
        "RF-NOISE.high_at_db": str(RF_POLICY.high_at),
        "RF-NOISE.minimum_episode_s": str(DEFAULT_MINIMUM_DURATION.total_seconds()),
        "TRACK-GAP.threshold_s": str(GAP.threshold.total_seconds()),
        "TRACK-GAP.contact_fresh_within_s": str(GAP.contact_fresh_within.total_seconds()),
        "TRACK-GAP.box": f"{BOX.lat_min},{BOX.lat_max},{BOX.lon_min},{BOX.lon_max}",
        "TRACK-GAP.rate_excess_radius_km": str(EXCESS_RADIUS_KM),
        "TRACK-CLUSTER.radius_km": str(CLUSTER.radius_km),
        "SENSOR-FAULT.neighbour_radius_km": str(FAULT.radius_for(layout)),
        "FUSION-SPATIAL.corroboration_threshold": str(FUSION.corroboration_threshold),
        "FUSION-SPATIAL.excess_radius_km": str(
            EXCESS_RADIUS_KM if FUSION.excess_radius_km is None else FUSION.excess_radius_km
        ),
    },
)
export = export_metrics(detection=metrics, detection_provenance=provenance)
EXPORTS.mkdir(exist_ok=True)
for name, text in sorted(export.files.items()):
    (EXPORTS / name).write_text(text)
print(f"\nexported {len(export.files)} files to measurements/exports/, "
      f"every row stamped {provenance.digest}")
for name in sorted(export.files):
    print(f"  {name}")

print(f"\nscored {metrics.runs} runs, excluded {metrics.excluded} for staging nothing, "
      f"{metrics.multi_claim_runs} claimed more than one type")
if undecidable:
    print(f"\nclaims whose latency could not be taken: {len(undecidable)}")
    for row in undecidable[:5]:
        print(f"  run {row[0]} {row[1]}: {row[2]}")
