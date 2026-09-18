"""The catch rate and the misattribution rate, on the rebuilt rule.

Same corpus, same baseline, same anom-001 policy as the first pass. What
changed is that nominality is now read off the neighbours' readings rather
than off their episodes.
"""
from __future__ import annotations

import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, RfPayload, SourceType, ValidationStatus)
from app.detection.baseline import RfMetric, compute_rf_baselines
from app.detection.rf_noise import Direction, ThresholdPolicy, detect_rf_noise
from app.detection.sensor_fault import FaultPolicy, detect_sensor_faults
from app.scenario.layout import load_layout

POLICY = ThresholdPolicy(metric=RfMetric.POWER_DBM, direction=Direction.ABOVE,
                         threshold=6.0, medium_at=10.0, high_at=15.0)
FAULT = FaultPolicy()

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)
layout = load_layout()


def rf_for(run_ids):
    with factory.begin() as s:
        rows = s.execute(text(
            "SELECT scenario_run_id, timestamp, ST_Y(location) AS lat, "
            "ST_X(location) AS lon, payload FROM observations "
            "WHERE observation_type='rf' AND scenario_run_id = ANY(:r) "
            "ORDER BY timestamp"), {"r": list(run_ids)}).mappings().all()
    return [CanonicalObservation(
        source_id="rf", source_type=SourceType.SYNTHETIC_RF,
        observation_type=ObservationType.RF, timestamp=r["timestamp"],
        location=Location(lat=r["lat"], lon=r["lon"]),
        data_mode=DataMode.SYNTHETIC, validation_status=ValidationStatus.VALID,
        provenance=Provenance(source_id="rf", source_type=SourceType.SYNTHETIC_RF,
                              data_mode=DataMode.SYNTHETIC,
                              scenario_run_id=r["scenario_run_id"]),
        payload=RfPayload(**r["payload"])) for r in rows]


with factory.begin() as s:
    runs = s.execute(text(
        "SELECT id, scenario_type, ground_truth FROM scenario_runs ORDER BY id"
    )).mappings().all()

quiet = [r["id"] for r in runs if r["scenario_type"] == "normal-baseline"]
table = compute_rf_baselines(rf_for(quiet), RfMetric.POWER_DBM,
                             baseline_run_ids=quiet, window=timedelta(hours=2))

total = Counter(); claimed = Counter(); other = Counter()
faults_per_run = defaultdict(list)
verdicts = defaultdict(Counter)
confidence = defaultdict(Counter)
spans = []

for run in runs:
    kind = run["scenario_type"]
    total[kind] += 1
    truth = run["ground_truth"] or {}
    sensors = set(truth.get("sensors") or [])
    w = truth.get("window")
    w0 = datetime.fromisoformat(w["start"]) if w else None
    w1 = datetime.fromisoformat(w["end"]) if w else None

    obs = rf_for([run["id"]])
    rf = detect_rf_noise(obs, table, POLICY)
    result = detect_sensor_faults(rf, obs, table, layout, FAULT)

    for d in result.dismissed:
        verdicts[kind][d.verdict.value] += 1
    for f in result.faults:
        confidence[kind][f.confidence.value] += 1

    hit = miss = False
    for f in result.faults:
        on_target = (f.sensor_id in sensors and w0 is not None
                     and f.started_at <= w1 and w0 <= f.ended_at)
        if on_target:
            hit = True
            spans.append((f.ended_at - f.started_at).total_seconds())
        else:
            miss = True
    faults_per_run[kind].append(len(result.faults))
    if hit:
        claimed[kind] += 1
    if miss:
        other[kind] += 1

print(f"{'scenario':26} {'runs':>5} {'claims staged':>14} {'other fires':>12} {'faults/run':>11}")
for kind in sorted(total):
    n = faults_per_run[kind]
    print(f"{kind:26} {total[kind]:5d} {claimed[kind]:14d} {other[kind]:12d} "
          f"{sum(n)/len(n):11.2f}")

print("\ndismissals by verdict:")
for kind in sorted(verdicts):
    print(f"  {kind:26} {dict(verdicts[kind])}")
print("\nconfidence of the faults raised:")
for kind in sorted(confidence):
    print(f"  {kind:26} {dict(confidence[kind])}")
if spans:
    spans.sort()
    print(f"\non-target fault window: n={len(spans)} min={spans[0]:.0f}s "
          f"median={spans[len(spans)//2]:.0f}s max={spans[-1]:.0f}s "
          f"(the staged incident is 300 s)")
