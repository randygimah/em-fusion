"""The excess distribution among the zones that actually reach step three."""
from __future__ import annotations
import os, statistics
from collections import Counter
from datetime import timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, RfPayload, SourceType, TrackPayload, ValidationStatus)
from app.db.findings import save_findings
from app.detection.baseline import RfMetric, compute_rf_baselines
from app.detection.findings import from_track_gap
from app.detection.rate_excess import DEFAULT_RADIUS_KM, ExcessPolicy, measure_rate_excess
from app.detection.rf_noise import Direction, ThresholdPolicy, detect_rf_noise
from app.detection.sensor_fault import FaultPolicy, Verdict, detect_sensor_faults
from app.detection.track_gap import BoundingBox, GapPolicy, detect_track_gaps
from app.scenario.layout import load_layout

RF_POLICY = ThresholdPolicy(metric=RfMetric.POWER_DBM, direction=Direction.ABOVE,
                            threshold=6.0, medium_at=10.0, high_at=15.0)
FAULT = FaultPolicy()
BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)
GAP = GapPolicy(threshold=timedelta(seconds=100),
                contact_fresh_within=timedelta(seconds=30), box=BOX)
THRESHOLD = 1.58
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

quiet = list(range(101, 121))
table = compute_rf_baselines([o for q in quiet for o in obs_for(q, "rf")],
                             RfMetric.POWER_DBM, baseline_run_ids=quiet,
                             window=timedelta(hours=2))
with factory.begin() as s:
    runs = s.execute(text("SELECT id FROM scenario_runs WHERE id BETWEEN 121 AND 240 "
                          "AND scenario_type='gnss-degradation' ORDER BY id")).scalars().all()

vals = []
for run_id in runs:
    rf = obs_for(run_id, "rf")
    span = (min(o.timestamp for o in rf), max(o.timestamp for o in rf))
    found = detect_rf_noise(rf, table, RF_POLICY)
    assessed = detect_sensor_faults(found, rf, table, layout, FAULT)
    onward = [d for d in assessed.dismissed if d.verdict is Verdict.ENVIRONMENTAL]
    if not onward:
        continue
    tracks = obs_for(run_id, "track")
    save_findings(factory, scenario_run_id=run_id, rule_id="TRACK-GAP",
                  findings=[from_track_gap(g, scenario_run_id=run_id)
                            for g in detect_track_gaps(tracks, GAP)])
    d = max(onward, key=lambda d: (d.ended_at - d.started_at))
    w = (max(d.started_at, span[0] + timedelta(seconds=1)),
         min(d.ended_at, span[1] - timedelta(seconds=1)))
    if (w[1] - w[0]).total_seconds() <= 0:
        continue
    site = layout.site(d.sensor_id)
    r = measure_rate_excess(factory, scenario_run_id=run_id,
                            centre=Location(lat=site.lat, lon=site.lon),
                            policy=ExcessPolicy(radius_km=DEFAULT_RADIUS_KM),
                            window=w, run_span=span)
    vals.append((r.ratio, r.during, r.outside))

vals.sort()
ratios = [v[0] for v in vals]
print(f"n={len(ratios)}")
print(f"  min={ratios[0]:.2f}  p25={ratios[len(ratios)//4]:.2f}  "
      f"median={ratios[len(ratios)//2]:.2f}  p75={ratios[3*len(ratios)//4]:.2f}  "
      f"max={ratios[-1]:.2f}")
print(f"  >= {THRESHOLD}: {sum(1 for x in ratios if x >= THRESHOLD)}")
print(f"  no findings in the disc at all: {sum(1 for _, d, o in vals if d + o == 0)}")
print(f"  findings present but below {THRESHOLD}: "
      f"{sum(1 for r, d, o in vals if r < THRESHOLD and d + o > 0)}")
print("\nthe 14 that would be lost to a gate, lowest first:")
for r, d, o in vals:
    if r < THRESHOLD:
        print(f"    ratio={r:5.2f}  findings during={d:3d} outside={o:3d}")
