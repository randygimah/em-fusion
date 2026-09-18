"""The whole ladder, end to end, over every stored run.

anom-013 shipped without this because only anom-007 produced claims. With
anom-005 built, two of the three steps exist, and the ladder can be run as
one decision over the corpus for the first time.

anom-006 is still absent, so the coverage-gap arm can only produce a
correct non-detection here. That is reported rather than hidden.
"""
from __future__ import annotations

import os
from collections import Counter, defaultdict
from datetime import timedelta

import _corpus
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, RfPayload, SourceType, TrackPayload,
                            ValidationStatus)
from app.db.findings import save_findings
from app.detection.baseline import RfMetric, compute_rf_baselines
from app.detection.findings import from_track_gap
from app.detection.fusion import (Corroboration, FusionPolicy, claims_from_interference,
                                  detect_interference)
from app.detection.precedence import PrecedencePolicy, claims_from_sensor_faults, resolve
from app.detection.rf_noise import Direction, ThresholdPolicy, detect_rf_noise
from app.detection.sensor_fault import FaultPolicy, detect_sensor_faults
from app.detection.track_gap import BoundingBox, GapPolicy, detect_track_gaps
from app.scenario.layout import load_layout

RF_POLICY = ThresholdPolicy(metric=RfMetric.POWER_DBM, direction=Direction.ABOVE,
                            threshold=6.0, medium_at=10.0, high_at=15.0)
FAULT, FUSION, LADDER = FaultPolicy(), FusionPolicy(), PrecedencePolicy()
BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)
GAP = GapPolicy(threshold=timedelta(seconds=100),
                contact_fresh_within=timedelta(seconds=30), box=BOX)

#: What each staged type should be decided as, under the declared order.
EXPECTED = {
    "rf-sensor-fault": "possible_sensor_fault",
    "gnss-degradation": "possible_interference_zone",
    "ambiguous-mixed-evidence": "possible_sensor_fault",   # stages one receiver
    "aircraft-coverage-gap": None,                          # anom-006 unbuilt
    "normal-baseline": None,
}

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
        f"SELECT id, scenario_type FROM scenario_runs "
        f"WHERE {_corpus.run_filter()} ORDER BY id")).mappings().all()

totals = Counter()
reported = defaultdict(Counter)
correct = Counter()
silent = Counter()
conflicts = Counter()
corrob = Counter()

for run in runs:
    kind, run_id = run["scenario_type"], run["id"]
    totals[kind] += 1

    rf = obs_for(run_id, "rf")
    span = (min(o.timestamp for o in rf), max(o.timestamp for o in rf))
    found = detect_rf_noise(rf, table, RF_POLICY)
    faults = detect_sensor_faults(found, rf, table, layout, FAULT)

    tracks = obs_for(run_id, "track")
    save_findings(factory, scenario_run_id=run_id, rule_id="TRACK-GAP",
                  findings=[from_track_gap(g, scenario_run_id=run_id)
                            for g in detect_track_gaps(tracks, GAP)])

    zones = detect_interference(faults, factory, scenario_run_id=run_id,
                                run_span=span, layout=layout, policy=FUSION)
    for z in zones.zones:
        corrob[z.corroboration.value] += 1

    claims = [*claims_from_sensor_faults(faults, layout),
              *claims_from_interference(zones)]
    result = resolve(claims, layout, LADDER)

    types = {c.anomaly_type for c in result.reported}
    for t in types:
        reported[kind][t] += 1
    if not result.reported:
        silent[kind] += 1
    if len(types) > 1:
        conflicts[kind] += 1

    want = EXPECTED[kind]
    if want is None:
        correct[kind] += 1 if not result.reported else 0
    else:
        correct[kind] += 1 if want in types else 0

print(f"{'scenario':26} {'runs':>5} {'decided correctly':>18} {'silent':>7} {'conflicting':>12}")
for kind in sorted(totals):
    print(f"{kind:26} {totals[kind]:5d} {correct[kind]:18d} {silent[kind]:7d} "
          f"{conflicts[kind]:12d}")

print("\nwhat each arm was actually reported as:")
for kind in sorted(reported):
    print(f"  {kind:26} {dict(reported[kind])}")
print(f"\ncorroboration across every interference zone raised: {dict(corrob)}")
print("\nNOTE: aircraft-coverage-gap can only be a correct non-detection here,"
      " because anom-006 is unbuilt (scn-007 blocks it).")
