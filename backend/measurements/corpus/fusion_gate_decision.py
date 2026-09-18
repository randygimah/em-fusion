"""Should anom-005 gate on the rate excess, or carry it as evidence strength?

Every figure quoted for the excess so far -- 26 of 40 staged against 15 of
40 controls at 60 km -- was measured over *all* runs of each type. But
anom-013 means anom-005 never sees most of them: anom-007 claims the
sensor faults, and a coverage gap raises no RF anomaly to fuse with.

So the question the trade-off curve answers is not the question anom-005
faces. The right question is: **among the zones that actually reach step
three, what would a threshold on the excess reject?** If everything
arriving there is real interference, a gate can only lose true positives,
because there is nothing false left for it to catch.

Three candidate designs, measured side by side on the same zones:
  A. gate on the excess threshold      -- the spec's "both are necessary"
  B. gate on any track evidence at all -- findings present in the disc
  C. no gate; fire on the RF pattern and carry the excess as strength
"""
from __future__ import annotations

import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, RfPayload, SourceType, TrackPayload,
                            ValidationStatus)
from app.db.findings import save_findings
from app.detection.baseline import RfMetric, compute_rf_baselines
from app.detection.findings import from_track_gap
from app.detection.precedence import Claim, PrecedencePolicy, Zone, claims_from_sensor_faults, resolve
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
#: The pre-registered threshold at the chosen radius.
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
        source_id="o", source_type=src, observation_type=ot,
        timestamp=r["timestamp"], location=Location(lat=r["lat"], lon=r["lon"]),
        data_mode=mode, validation_status=ValidationStatus.VALID,
        provenance=Provenance(source_id="o", source_type=src, data_mode=mode,
                              scenario_run_id=run_id),
        payload=pl(**r["payload"])) for r in rows]


quiet = list(range(101, 121))
table = compute_rf_baselines([o for q in quiet for o in obs_for(q, "rf")],
                             RfMetric.POWER_DBM, baseline_run_ids=quiet,
                             window=timedelta(hours=2))

with factory.begin() as s:
    runs = s.execute(text(
        "SELECT id, scenario_type FROM scenario_runs WHERE id BETWEEN 121 AND 240 "
        "OR scenario_type='normal-baseline' ORDER BY id")).mappings().all()

reached = Counter()
totals = Counter()
excesses = defaultdict(list)
no_evidence = Counter()
unusable = Counter()

for run in runs:
    kind = run["scenario_type"]
    run_id = run["id"]
    totals[kind] += 1

    rf = obs_for(run_id, "rf")
    span = (min(o.timestamp for o in rf), max(o.timestamp for o in rf))
    found = detect_rf_noise(rf, table, RF_POLICY)
    assessed = detect_sensor_faults(found, rf, table, layout, FAULT)

    # What anom-013 actually passes on: a zone anom-007 declined as
    # environmental. An undecided one passes too, but carries no window
    # anom-005 could trust, so it is counted separately.
    onward = [d for d in assessed.dismissed if d.verdict is Verdict.ENVIRONMENTAL]
    if not onward:
        continue
    reached[kind] += 1

    tracks = obs_for(run_id, "track")
    save_findings(factory, scenario_run_id=run_id, rule_id="TRACK-GAP",
                  findings=[from_track_gap(g, scenario_run_id=run_id) for g in tracks
                            and detect_track_gaps(tracks, GAP)])

    d = max(onward, key=lambda d: (d.ended_at - d.started_at))
    window = (max(d.started_at, span[0] + timedelta(seconds=1)),
              min(d.ended_at, span[1] - timedelta(seconds=1)))
    if (window[1] - window[0]).total_seconds() <= 0:
        unusable[kind] += 1
        continue

    r = measure_rate_excess(
        factory, scenario_run_id=run_id, centre=d.spatial_centre if False else
        Location(lat=layout.site(d.sensor_id).lat, lon=layout.site(d.sensor_id).lon),
        policy=ExcessPolicy(radius_km=DEFAULT_RADIUS_KM),
        window=window, run_span=span)
    excesses[kind].append(r.ratio)
    if r.during + r.outside == 0:
        no_evidence[kind] += 1

print(f"{'scenario':26} {'runs':>5} {'reach step 3':>13} {'measurable':>11}")
for kind in sorted(totals):
    print(f"{kind:26} {totals[kind]:5d} {reached[kind]:13d} {len(excesses[kind]):11d}")

print(f"\nAmong the zones that reach step three, at {DEFAULT_RADIUS_KM:g} km:")
print(f"{'scenario':26} {'n':>4} {'>= 1.58':>9} {'no track evidence':>18} {'median':>8}")
for kind in sorted(excesses):
    v = sorted(excesses[kind])
    if not v:
        continue
    fires = sum(1 for x in v if x >= THRESHOLD)
    print(f"{kind:26} {len(v):4d} {fires:9d} {no_evidence[kind]:18d} "
          f"{v[len(v)//2]:8.2f}")

print(f"\nunusable windows: {dict(unusable)}")
print("\nWhat each design would report, over the zones reaching step three:")
for kind in sorted(excesses):
    v = excesses[kind]
    if not v:
        continue
    a = sum(1 for x in v if x >= THRESHOLD)
    b = len(v) - no_evidence[kind]
    print(f"  {kind:26} A(gate on excess)={a:3d}  B(gate on any)={b:3d}  C(no gate)={len(v):3d}")
