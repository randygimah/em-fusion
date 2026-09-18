"""What minimum episode duration should anom-014 use?

The item is specified and the number in it is not. anom-001 raises at least
one episode on 14 of 100 runs that stage nothing at all on the RF grid, and
6 of 86 staged runs produce an episode whose start equals its end -- a
window of no length, which anom-012 divides by. A minimum duration removes
the cause. Choosing it by eye would be choosing it quietly.

So this measures the two populations the choice has to separate:

  true   -- an episode on a cell the answer key names, inside the staged
            window. What a minimum must not destroy.
  false  -- every other episode, on any run. Includes every episode on a run
            that staged no RF at all, which is the population anom-014 exists
            to remove.

A minimum is only worth having if the two separate. If the shortest true
episodes are the same length as the longest false ones, the item cannot be
built at a threshold and should be reconsidered rather than tuned.

Note on validity: scn-007 changes the tracks and not the RF grid, so this
distribution is unaffected by the regeneration it is being measured ahead of.
The figure survives it.
"""
from __future__ import annotations

import os
from collections import Counter
from datetime import timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, RfPayload, SourceType, ValidationStatus)
from app.detection.baseline import RfMetric, compute_rf_baselines
from app.detection.rf_noise import Direction, ThresholdPolicy, detect_rf_noise

POLICY = ThresholdPolicy(metric=RfMetric.POWER_DBM, direction=Direction.ABOVE,
                         threshold=6.0, medium_at=10.0, high_at=15.0)

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)


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


def pct(values, p):
    if not values:
        return float("nan")
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(p / 100.0 * len(ordered)))]


with factory.begin() as s:
    runs = s.execute(text(
        "SELECT id, scenario_type, ground_truth FROM scenario_runs ORDER BY id"
    )).mappings().all()

quiet = [r["id"] for r in runs if r["scenario_type"] == "normal-baseline"]
table = compute_rf_baselines(rf_for(quiet), RfMetric.POWER_DBM,
                             baseline_run_ids=quiet, window=timedelta(hours=2))

true_s, false_s = [], []
true_n, false_n = [], []
intervals = set()
runs_with_rf, runs_without_rf = 0, 0
false_runs_firing = set()
per_run_true = {}

for run in runs:
    truth = run["ground_truth"] or {}
    sensors = set(truth.get("sensors") or [])
    channels = set(truth.get("channels") or [])
    w = truth.get("window")
    stages_rf = bool(sensors and w)
    runs_with_rf += stages_rf
    runs_without_rf += not stages_rf

    obs = rf_for([run["id"]])
    if not obs:
        continue
    stamps = sorted({o.timestamp for o in obs})
    for a, b in zip(stamps, stamps[1:]):
        intervals.add(round((b - a).total_seconds()))

    found = detect_rf_noise(obs, table, POLICY)
    if stages_rf:
        from datetime import datetime
        ws = datetime.fromisoformat(w["start"])
        we = datetime.fromisoformat(w["end"])

    hits = 0
    for a in found.anomalies:
        seconds = (a.ended_at - a.started_at).total_seconds()
        readings = len(a.triggering)
        on_truth = (
            stages_rf
            and a.cell.sensor_id in sensors
            and (not channels or a.cell.channel_index in channels)
            and a.started_at < we and a.ended_at > ws
        )
        if on_truth:
            true_s.append(seconds); true_n.append(readings); hits += 1
        else:
            false_s.append(seconds); false_n.append(readings)
            false_runs_firing.add(run["id"])
    per_run_true[run["id"]] = hits

print(f"reading intervals present in the corpus, seconds: {sorted(intervals)}")
print(f"runs staging RF: {runs_with_rf}   staging none: {runs_without_rf}")
print()
print(f"TRUE  episodes (staged cell, inside staged window): n={len(true_s)}")
print(f"  seconds  min={min(true_s):.0f} p5={pct(true_s,5):.0f} p25={pct(true_s,25):.0f} "
      f"median={pct(true_s,50):.0f} p75={pct(true_s,75):.0f} max={max(true_s):.0f}")
print(f"  readings min={min(true_n)} p5={pct(true_n,5)} median={pct(true_n,50)} max={max(true_n)}")
print()
print(f"FALSE episodes (everything else): n={len(false_s)}")
print(f"  seconds  min={min(false_s):.0f} p25={pct(false_s,25):.0f} median={pct(false_s,50):.0f} "
      f"p75={pct(false_s,75):.0f} p95={pct(false_s,95):.0f} max={max(false_s):.0f}")
print(f"  readings min={min(false_n)} median={pct(false_n,50)} p95={pct(false_n,95)} max={max(false_n)}")
print()
print("zero-length episodes (start == end, which anom-012 divides by):")
print(f"  among true:  {sum(1 for x in true_s if x == 0)} of {len(true_s)}")
print(f"  among false: {sum(1 for x in false_s if x == 0)} of {len(false_s)}")
print()
print("the trade-off, at candidate minimums (an episode is kept when its")
print("duration is >= the minimum, so the boundary belongs to the value):")
print(f"  {'minimum':>9}  {'true kept':>11}  {'false kept':>11}  {'runs still firing falsely':>26}")
for minimum in (0, 10, 20, 30, 40, 60, 90, 120):
    tk = sum(1 for x in true_s if x >= minimum)
    fk = sum(1 for x in false_s if x >= minimum)
    print(f"  {minimum:>7}s  {tk:>5} / {len(true_s):<5}  {fk:>5} / {len(false_s):<5}")
print()
print("runs whose ONLY episodes are false, by minimum -- the anom-008 number:")
clean_runs = [r["id"] for r in runs if not ((r["ground_truth"] or {}).get("sensors"))]
print(f"  runs staging no RF at all: {len(clean_runs)}")
