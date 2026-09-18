"""Where do SENSOR-FAULT's fires actually land?

The first pass counted a fire as correct if it named a staged sensor. That
is too weak: a staged sensor can also carry a spurious episode at another
time, and the fault raised over *that* window would be counted right for
the wrong reason. This pass checks the window as well, and separates:

  claimed   -- names a staged sensor AND overlaps the staged window
  offtarget -- names a staged sensor at some other time, or another sensor
  spurious  -- the run staged no RF at all

It also measures the episodes behind the fires, because a one-tick blip
and a 300 s elevation are not the same evidence and RF-NOISE does not
currently distinguish them.
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

kinds = Counter()
claimed_runs = Counter()     # runs with >=1 fault on the staged sensor in the staged window
offtarget_runs = Counter()   # runs with >=1 fault that is not that
episode_len = defaultdict(list)
spur_len = []
spur_channels = Counter()
staged_len = []

for run in runs:
    kind = run["scenario_type"]
    kinds[kind] += 1
    truth = run["ground_truth"] or {}
    sensors = set(truth.get("sensors") or [])
    window = truth.get("window")
    if window:
        w0 = datetime.fromisoformat(window["start"])
        w1 = datetime.fromisoformat(window["end"])

    rf = detect_rf_noise(rf_for([run["id"]]), table, POLICY)
    result = detect_sensor_faults(rf, layout, FAULT)

    claimed = offtarget = False
    for f in result.faults:
        span = (f.ended_at - f.started_at).total_seconds()
        on_target = (
            bool(sensors) and f.sensor_id in sensors
            and window is not None
            and f.started_at <= w1 and w0 <= f.ended_at
        )
        if on_target:
            claimed = True
            staged_len.append(span)
        else:
            offtarget = True
            spur_len.append(span)
            spur_channels[len(f.spectral.channels)] += 1
        episode_len[kind].append(span)
    if claimed:
        claimed_runs[kind] += 1
    if offtarget:
        offtarget_runs[kind] += 1

print(f"{'scenario':26} {'runs':>5} {'claims staged':>14} {'other fires':>12}")
for kind in sorted(kinds):
    print(f"{kind:26} {kinds[kind]:5d} {claimed_runs[kind]:14d} {offtarget_runs[kind]:12d}")

def stats(name, xs):
    if not xs:
        print(f"  {name}: none"); return
    xs = sorted(xs)
    print(f"  {name}: n={len(xs)} min={xs[0]:.0f}s median={xs[len(xs)//2]:.0f}s "
          f"max={xs[-1]:.0f}s  <=20s: {sum(1 for x in xs if x <= 20)}")

print("\nfault window durations")
stats("on the staged incident", staged_len)
stats("everything else       ", spur_len)
print(f"\nchannels per off-target fault: {dict(sorted(spur_channels.items()))}")
