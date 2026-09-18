"""How often does SENSOR-FAULT claim the runs whose truth is a broken box?

anom-013 orders the reportable rules with the sensor-fault rule first, and
the whole argument rests on an assumption nobody has tested: that it
actually claims the rf-sensor-fault runs. If it does not, the ordering
moves those runs nowhere and anom-012's radius cannot be read from the
sensitive end of its curve.

Measured over all 240 stored runs, with the baseline built only from the
20 normal-baseline ones (anom-002 refuses anything else).
"""
from __future__ import annotations

import os
from collections import Counter, defaultdict
from datetime import timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, RfPayload, SourceType, ValidationStatus)
from app.detection.baseline import RfMetric, compute_rf_baselines
from app.detection.rf_noise import Direction, ThresholdPolicy, detect_rf_noise
from app.detection.sensor_fault import FaultPolicy, Verdict, detect_sensor_faults
from app.scenario.layout import load_layout

#: anom-001's shipped bands: trigger 6 dB past baseline, Medium at 10,
#: High at 15. The staged elevation is 8 dB and the quiet spread ~1.5 dB,
#: so 6 dB is four standard deviations and well short of the injection.
POLICY = ThresholdPolicy(metric=RfMetric.POWER_DBM, direction=Direction.ABOVE,
                         threshold=6.0, medium_at=10.0, high_at=15.0)
FAULT = FaultPolicy()  # the layout's own 70 km discrimination radius

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
print(f"baseline from {len(quiet)} quiet runs: {quiet[0]}-{quiet[-1]}")

table = compute_rf_baselines(rf_for(quiet), RfMetric.POWER_DBM,
                             baseline_run_ids=quiet, window=timedelta(hours=2))
print(f"cells with a baseline: {len(table.baselines)}, thin: {len(table.insufficient)}")
print(f"cell means span {max(b.mean for b in table.baselines.values()) - min(b.mean for b in table.baselines.values()):.4f} dB")

fires = Counter()       # runs raising >=1 sensor fault
noisy = Counter()       # runs raising >=1 RF anomaly at all
total = Counter()
right_sensor = Counter()
verdicts = defaultdict(Counter)
confidence = defaultdict(Counter)

for run in runs:
    kind = run["scenario_type"]
    total[kind] += 1
    rf = detect_rf_noise(rf_for([run["id"]]), table, POLICY)
    if rf.anomalies:
        noisy[kind] += 1
    result = detect_sensor_faults(rf, layout, FAULT)
    for d in result.dismissed:
        verdicts[kind][d.verdict.value] += 1
    if result.faults:
        fires[kind] += 1
        for f in result.faults:
            confidence[kind][f.confidence.value] += 1
        staged = (run["ground_truth"] or {}).get("sensors") or []
        if staged and any(f.sensor_id in staged for f in result.faults):
            right_sensor[kind] += 1

print(f"\n{'scenario':26} {'runs':>5} {'RF fires':>9} {'FAULT fires':>12} {'right sensor':>13}")
for kind in sorted(total):
    print(f"{kind:26} {total[kind]:5d} {noisy[kind]:9d} {fires[kind]:12d} "
          f"{right_sensor[kind]:13d}")

print("\ndismissals (per run-window, not per run):")
for kind in sorted(verdicts):
    print(f"  {kind:26} {dict(verdicts[kind])}")
print("\nconfidence of the faults raised:")
for kind in sorted(confidence):
    print(f"  {kind:26} {dict(confidence[kind])}")
