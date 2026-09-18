"""Is 21% recall a property of the system or of the policy I guessed?"""
from __future__ import annotations

import os
from datetime import timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, SourceType, TrackPayload, ValidationStatus)
from app.detection.track_gap import BoundingBox, GapPolicy, detect_track_gaps

BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)
engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)

# The best-staged matched pairs, plus their shared control.
CASES = [(13, 33, 73), (46, 26, 66), (19, 39, 79), (2, 22, 62)]


def observations_for(run_id):
    with factory.begin() as s:
        rows = s.execute(text(
            "SELECT timestamp, ST_Y(location) AS lat, ST_X(location) AS lon, payload "
            "FROM observations WHERE scenario_run_id=:r AND observation_type='track' "
            "ORDER BY timestamp"), {"r": run_id}).mappings().all()
    return [CanonicalObservation(
        source_id="o", source_type=SourceType.OPENSKY, observation_type=ObservationType.TRACK,
        timestamp=r["timestamp"], location=Location(lat=r["lat"], lon=r["lon"]),
        data_mode=DataMode.REPLAYED, validation_status=ValidationStatus.VALID,
        provenance=Provenance(source_id="o", source_type=SourceType.OPENSKY,
                              data_mode=DataMode.REPLAYED, scenario_run_id=run_id),
        payload=TrackPayload(**r["payload"])) for r in rows]


def staged(run_id):
    with factory.begin() as s:
        ac = s.execute(text("SELECT ground_truth->'aircraft' FROM scenario_runs WHERE id=:r"),
                       {"r": run_id}).scalar_one() or []
    return {a["aircraft_id"] if isinstance(a, dict) else a for a in ac}


obs = {r: observations_for(r) for c in CASES for r in c}
truth = {r: staged(r) for c in CASES for r in c}

print(f"{'thresh':>7} {'fresh':>6} | {'gap recall':>11} {'gnss recall':>12} | "
      f"{'staged found':>13} {'control found':>14} {'ratio':>7}")
print("-" * 82)

for thresh in (60, 100, 150, 200):
    for fresh in (10, 30, 60, 90, 100000):
        if fresh >= thresh and fresh != 100000:
            continue
        policy = GapPolicy(threshold=timedelta(seconds=thresh),
                           contact_fresh_within=timedelta(seconds=min(fresh, thresh - 1)),
                           box=BOX)
        gap_s = gap_h = gnss_s = gnss_h = 0
        staged_found = control_found = 0
        for gap_run, gnss_run, ctrl_run in CASES:
            for run, kind in ((gap_run, "gap"), (gnss_run, "gnss")):
                found = detect_track_gaps(obs[run], policy)
                ids = {g.aircraft_id for g in found}
                hits = len(truth[run] & ids)
                staged_found += len(found)
                if kind == "gap":
                    gap_s += len(truth[run]); gap_h += hits
                else:
                    gnss_s += len(truth[run]); gnss_h += hits
            control_found += len(detect_track_gaps(obs[ctrl_run], policy))
        ratio = staged_found / control_found if control_found else float("inf")
        label = "none" if fresh == 100000 else str(fresh)
        print(f"{thresh:>7} {label:>6} | {gap_h/gap_s:>10.0%} {gnss_h/gnss_s:>11.0%} | "
              f"{staged_found:>13} {control_found:>14} {ratio:>7.2f}")
