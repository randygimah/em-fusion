"""Two questions the anom-005 amendment left open, before it is built.

One: what should set the anomaly's confidence? The amendment said the rate
excess should. That may be the session's own error in a new costume --
letting a signal with a Youden's J near 0.3 grade a claim an 8 dB
deviation establishes. The alternative is that confidence follows the RF
evidence and the excess is carried as separate corroboration. Deciding it
needs the shape of the RF evidence: how many receivers does a zone
actually span, and how far past baseline do they sit?

Two: where is the floor between "measurably below threshold" and "too
little traffic to judge"? The arithmetic answer is that a period holding
no findings contributes no observation -- its rate is purely anom-012's
smoothing constant -- so the ratio is not a comparison of two observed
rates. This counts how many zones that rule catches.
"""
from __future__ import annotations

import os
from collections import Counter
from datetime import timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, RfPayload, SourceType, TrackPayload,
                            ValidationStatus)
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

receivers = Counter()
severities = Counter()
peaks = []
states = Counter()
state_by_receivers = Counter()

for run_id in runs:
    rf = obs_for(run_id, "rf")
    span = (min(o.timestamp for o in rf), max(o.timestamp for o in rf))
    found = detect_rf_noise(rf, table, RF_POLICY)
    assessed = detect_sensor_faults(found, rf, table, layout, FAULT)
    onward = [d for d in assessed.dismissed if d.verdict is Verdict.ENVIRONMENTAL]
    if not onward:
        continue
    d = max(onward, key=lambda x: (x.ended_at - x.started_at))

    # The zone's receivers: the subject plus the neighbours it named abnormal.
    zone_sensors = {d.sensor_id, *d.spatial.abnormal}
    receivers[len(zone_sensors)] += 1

    # The worst deviation anywhere in the zone, and its anom-001 severity.
    episodes = [a for a in found.anomalies if a.cell.sensor_id in zone_sensors
                and a.started_at <= d.ended_at and d.started_at <= a.ended_at]
    if episodes:
        peak = max(a.peak_deviation for a in episodes)
        peaks.append(peak)
        severities[RF_POLICY.severity_for(peak).value] += 1

    tracks = obs_for(run_id, "track")
    save_findings(factory, scenario_run_id=run_id, rule_id="TRACK-GAP",
                  findings=[from_track_gap(g, scenario_run_id=run_id)
                            for g in detect_track_gaps(tracks, GAP)])
    w = (max(d.started_at, span[0] + timedelta(seconds=1)),
         min(d.ended_at, span[1] - timedelta(seconds=1)))
    if (w[1] - w[0]).total_seconds() <= 0:
        states["window unusable"] += 1
        continue
    site = layout.site(d.sensor_id)
    r = measure_rate_excess(factory, scenario_run_id=run_id,
                            centre=Location(lat=site.lat, lon=site.lon),
                            policy=ExcessPolicy(radius_km=DEFAULT_RADIUS_KM),
                            window=w, run_span=span)
    if r.during == 0 or r.outside == 0:
        state = "not measurable"
    elif r.ratio >= THRESHOLD:
        state = "corroborated"
    else:
        state = "not corroborated"
    states[state] += 1
    state_by_receivers[(len(zone_sensors), state)] += 1

print(f"receivers per zone: {dict(sorted(receivers.items()))}")
if peaks:
    peaks.sort()
    print(f"peak deviation in the zone, dB: min={peaks[0]:.1f} "
          f"median={peaks[len(peaks)//2]:.1f} max={peaks[-1]:.1f}")
    print(f"anom-001 severity of that peak: {dict(severities)}")
print(f"\ncorroboration state, with 'both periods must hold a finding':")
for k, v in sorted(states.items()):
    print(f"  {k:18} {v}")
print(f"\nstate by receiver count: {dict(sorted(state_by_receivers.items()))}")
