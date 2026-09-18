"""Is 90% on_ground real, or an artefact of how I ranked the reasons?"""
from __future__ import annotations

import os
from collections import Counter
from datetime import timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, SourceType, TrackPayload, ValidationStatus)
from app.detection.track_gap import BoundingBox, GapPolicy, explain_track_gaps

BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)
POLICY = GapPolicy(threshold=timedelta(seconds=100),
                   contact_fresh_within=timedelta(seconds=30), box=BOX)
engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)


def rows_for(run_id):
    with factory.begin() as s:
        return s.execute(text(
            "SELECT timestamp, ST_Y(location) AS lat, ST_X(location) AS lon, payload "
            "FROM observations WHERE scenario_run_id=:r AND observation_type='track' "
            "ORDER BY timestamp"), {"r": run_id}).mappings().all()


def obs(rows, run_id):
    return [CanonicalObservation(
        source_id="o", source_type=SourceType.OPENSKY, observation_type=ObservationType.TRACK,
        timestamp=r["timestamp"], location=Location(lat=r["lat"], lon=r["lon"]),
        data_mode=DataMode.REPLAYED, validation_status=ValidationStatus.VALID,
        provenance=Provenance(source_id="o", source_type=SourceType.OPENSKY,
                              data_mode=DataMode.REPLAYED, scenario_run_id=run_id),
        payload=TrackPayload(**r["payload"])) for r in rows]


with factory.begin() as s:
    runs = s.execute(text(
        "SELECT id, ground_truth->'aircraft' AS ac FROM scenario_runs "
        "WHERE scenario_type='gnss-degradation' ORDER BY id LIMIT 8")).mappings().all()

profile = Counter()
ground_fraction = []
reports_per = []
for row in runs:
    ac = row["ac"] or []
    staged = {a["aircraft_id"] if isinstance(a, dict) else a for a in ac}
    if not staged:
        continue
    rows = rows_for(row["id"])
    by_ac: dict[str, list] = {}
    for r in rows:
        by_ac.setdefault(r["payload"]["aircraft_id"], []).append(r["payload"])
    verdicts = {v.aircraft_id: v for v in explain_track_gaps(obs(rows, row["id"]), POLICY)}
    for a in staged:
        v = verdicts.get(a)
        if v is None or v.detected:
            continue
        payloads = by_ac.get(a, [])
        grounded = sum(1 for p in payloads if p["on_ground"])
        n = len(payloads)
        reports_per.append(n)
        frac = grounded / n if n else -1.0
        ground_fraction.append(frac)
        if frac == 1.0:
            profile["every report on the ground"] += 1
        elif frac == 0.0:
            profile["never on the ground"] += 1
        else:
            profile["mixed: took off or landed"] += 1

print("Undetected staged aircraft, by how much of their track is on the ground:\n")
total = sum(profile.values())
for k, n in profile.most_common():
    print(f"  {k:32} {n:4}  {n/total:5.0%}")
print(f"\n  reports per undetected aircraft: min {min(reports_per)}, "
      f"median {sorted(reports_per)[len(reports_per)//2]}, max {max(reports_per)}")
print(f"  mean fraction of reports on the ground: {sum(ground_fraction)/len(ground_fraction):.2f}")
