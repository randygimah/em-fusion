"""Why does a sensor with loud neighbours read as isolated?

Suspicion: the injected elevation is 8 dB scaled by 1 + 0.25*N(0,1) per
cell per tick, and the threshold is 6 dB. A tick whose draw falls below
-1 sigma does not exceed, which ends the episode -- so a receiver loud for
the whole 300 s incident emits a string of short episodes rather than one.
Two receivers both loud throughout can then have fragments that never
overlap, and each looks isolated to the other.

If that is it, the neighbours' *readings* during the fault window are
plainly elevated even though no episode of theirs overlaps it -- which is
what the spec item asked for in the first place.
"""
from __future__ import annotations

import os
import statistics
from collections import Counter
from datetime import datetime, timedelta

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
        "SELECT id, scenario_type, ground_truth FROM scenario_runs "
        "WHERE scenario_type IN ('gnss-degradation','rf-sensor-fault') ORDER BY id"
    )).mappings().all()
    quiet = [r["id"] for r in s.execute(text(
        "SELECT id FROM scenario_runs WHERE scenario_type='normal-baseline'"
    )).scalars()] if False else None

quiet = [r for r in range(101, 121)]
table = compute_rf_baselines(rf_for(quiet), RfMetric.POWER_DBM,
                             baseline_run_ids=quiet, window=timedelta(hours=2))

# Fragmentation: how many episodes does one staged cell produce?
frag = []
neighbour_elev = []          # neighbour elevation during a misattributed window
neighbour_episode_near = Counter()
TOL = timedelta(seconds=60)

for run in runs[:40]:
    truth = run["ground_truth"] or {}
    sensors = set(truth.get("sensors") or [])
    w = truth.get("window")
    if not w:
        continue
    w0, w1 = datetime.fromisoformat(w["start"]), datetime.fromisoformat(w["end"])
    obs = rf_for([run["id"]])
    rf = detect_rf_noise(obs, table, POLICY)
    staged_cells = Counter()
    for a in rf.anomalies:
        if a.cell.sensor_id in sensors and a.started_at <= w1 and w0 <= a.ended_at:
            staged_cells[a.cell] += 1
    frag.extend(staged_cells.values())

    if run["scenario_type"] != "gnss-degradation":
        continue
    result = detect_sensor_faults(rf, layout, FAULT)
    by_cell = {}
    for o in obs:
        p = o.payload
        by_cell.setdefault((p.sensor_id, p.channel_index), []).append((o.timestamp, p.power_dbm))
    for f in result.faults:
        if f.sensor_id not in sensors or not (f.started_at <= w1 and w0 <= f.ended_at):
            continue
        for n in f.spatial.neighbours:
            if n not in sensors:
                continue          # only ask about neighbours the incident touched
            for ch in f.spectral.channels:
                base = table.baselines.get(RfCell(n, ch))
                vals = [v for t, v in by_cell.get((n, ch), [])
                        if f.started_at <= t <= f.ended_at]
                if base and vals:
                    neighbour_elev.append(statistics.mean(vals) - base.mean)
            near = any(a.cell.sensor_id == n and a.started_at - TOL <= f.ended_at
                       and f.started_at <= a.ended_at + TOL for a in rf.anomalies)
            neighbour_episode_near[near] += 1

frag.sort()
print(f"episodes per staged cell: n={len(frag)} min={frag[0]} "
      f"median={frag[len(frag)//2]} max={frag[-1]}")
print(f"  (one unbroken 300 s incident at a 10 s grid would be 1 episode of 30 readings)")

neighbour_elev.sort()
if neighbour_elev:
    print(f"\nstaged neighbours' elevation during a misattributed window: "
          f"n={len(neighbour_elev)} min={neighbour_elev[0]:.2f} dB "
          f"median={neighbour_elev[len(neighbour_elev)//2]:.2f} dB "
          f"max={neighbour_elev[-1]:.2f} dB")
    print(f"  above the 6 dB threshold: "
          f"{sum(1 for x in neighbour_elev if x > 6.0)}/{len(neighbour_elev)}")
    print(f"  above 2 dB (beyond the 1.5 dB quiet spread): "
          f"{sum(1 for x in neighbour_elev if x > 2.0)}/{len(neighbour_elev)}")
print(f"\nneighbour had an episode within 60 s of the window: {dict(neighbour_episode_near)}")
