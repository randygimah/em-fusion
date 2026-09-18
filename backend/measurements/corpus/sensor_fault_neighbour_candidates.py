"""Two candidate repairs for the neighbour test, measured before either is written.

The defect: the injected elevation is 8 dB scaled per cell per tick by
1 + 0.25*N(0,1), and the threshold is 6 dB, so roughly one tick in six
falls short and breaks the episode. A staged cell emits a median of six
episodes where the incident is one. Two receivers loud through the same
300 s can then have fragments that never overlap, and each reads as
isolated -- a broken receiver where the truth is interference.

Candidate A, tolerance: a neighbour episode within T seconds of the window
counts as overlapping it.

Candidate B, readings: ask whether the neighbour was *nominal*, which is a
question about its readings against its own baseline, not about whether
another rule's threshold happened to be crossed in this slice.

Both are measured on the two populations that matter: staged neighbours
during a misattributed window (B should catch them) and quiet neighbours
during a genuine fault window (neither must dismiss those).
"""
from __future__ import annotations

import os
import statistics
from collections import Counter
from datetime import datetime, timedelta

import _corpus
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, RfPayload, SourceType, ValidationStatus)
from app.detection.baseline import RfCell, RfMetric, compute_rf_baselines
from app.detection.rf_noise import Direction, ThresholdPolicy, detect_rf_noise
from app.detection.sensor_fault import FaultPolicy, detect_sensor_faults
from app.scenario.layout import load_layout

POLICY = ThresholdPolicy(metric=RfMetric.POWER_DBM, direction=Direction.ABOVE,
                         threshold=6.0, medium_at=10.0, high_at=15.0)
FAULT = FaultPolicy()
RADIUS = 70.0
TOLERANCES = [timedelta(seconds=s) for s in (10, 30, 60, 120)]
BARS = [1.0, 1.5, 2.0, 3.0, 4.0]

print(_corpus.describe())

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


with factory.begin() as _s:
    quiet = _corpus.quiet_runs(_s)
print(f"baseline from {len(quiet)} quiet runs of this corpus", flush=True)
table = compute_rf_baselines(rf_for(quiet), RfMetric.POWER_DBM,
                             baseline_run_ids=quiet, window=timedelta(hours=2))

with factory.begin() as s:
    runs = s.execute(text(
        "SELECT id, scenario_type, ground_truth FROM scenario_runs "
        "WHERE scenario_type IN ('gnss-degradation','rf-sensor-fault') ORDER BY id"
    )).mappings().all()

# Populations of neighbour elevation, in dB above that cell's own baseline.
staged_neighbour = []   # a neighbour the incident also touched
quiet_neighbour = []    # a neighbour the incident did not touch
claims = {"current": Counter()}
for t in TOLERANCES:
    claims[f"tol{int(t.total_seconds())}"] = Counter()
for b in BARS:
    claims[f"bar{b}"] = Counter()

for run in runs:
    kind = run["scenario_type"]
    truth = run["ground_truth"] or {}
    sensors = set(truth.get("sensors") or [])
    w = truth.get("window")
    if not w:
        continue
    w0, w1 = datetime.fromisoformat(w["start"]), datetime.fromisoformat(w["end"])
    obs = rf_for([run["id"]])
    rf = detect_rf_noise(obs, table, POLICY)
    result = detect_sensor_faults(rf, layout, FAULT)

    by_cell = {}
    for o in obs:
        p = o.payload
        by_cell.setdefault((p.sensor_id, p.channel_index), []).append(
            (o.timestamp, p.power_dbm))

    hit = {name: False for name in claims}
    for f in result.faults:
        on_target = f.sensor_id in sensors and f.started_at <= w1 and w0 <= f.ended_at
        if not on_target:
            continue
        hit["current"] = True

        # Candidate A: how near was the nearest neighbour episode?
        for name, tol in zip([f"tol{int(t.total_seconds())}" for t in TOLERANCES],
                             TOLERANCES):
            near = any(
                a.cell.sensor_id in f.spatial.neighbours
                and a.started_at - tol <= f.ended_at
                and f.started_at <= a.ended_at + tol
                for a in rf.anomalies)
            if not near:
                hit[name] = True

        # Candidate B: were the neighbours nominal, judged on their readings?
        worst = 0.0
        for n in f.spatial.neighbours:
            for ch in f.spectral.channels:
                base = table.baselines.get(RfCell(n, ch))
                vals = [v for t, v in by_cell.get((n, ch), [])
                        if f.started_at <= t <= f.ended_at]
                if not base or not vals:
                    continue
                dev = statistics.mean(vals) - base.mean
                worst = max(worst, dev)
                (staged_neighbour if n in sensors else quiet_neighbour).append(dev)
        for b in BARS:
            if worst <= b:
                hit[f"bar{b}"] = True

    for name, fired in hit.items():
        if fired:
            claims[name][kind] += 1


def show(name, xs):
    if not xs:
        print(f"  {name}: none"); return
    xs = sorted(xs)
    print(f"  {name}: n={len(xs)} p5={xs[len(xs)//20]:.2f} "
          f"median={xs[len(xs)//2]:.2f} p95={xs[-max(1,len(xs)//20)]:.2f} dB")


print("neighbour elevation during a fault window, dB above that cell's baseline")
show("incident also touched it ", staged_neighbour)
show("incident did not touch it", quiet_neighbour)

print(f"\n{'variant':10} {'gnss misattributed':>20} {'sensor-fault caught':>21}")
for name, c in claims.items():
    print(f"{name:10} {c['gnss-degradation']:>16}/60 {c['rf-sensor-fault']:>17}/60")
