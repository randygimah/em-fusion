"""Does TRACK-GAP actually find the aircraft the run staged on?

Separates two very different failures: clustering that cannot discriminate,
and a detector that never saw the injection in the first place.
"""
from __future__ import annotations

import json, os
from datetime import timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, SourceType, TrackPayload, ValidationStatus)
from app.detection.track_gap import BoundingBox, GapPolicy, detect_track_gaps

BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)
POLICY = GapPolicy(threshold=timedelta(seconds=100),
                   contact_fresh_within=timedelta(seconds=30), box=BOX)

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)

SEEDS = (177252997, 393812995, 638834611, 799651109, 812093417, 870060953, 927741824)


def run_rows():
    with factory.begin() as s:
        return s.execute(text(
            "SELECT id, seed, scenario_type, ground_truth->'aircraft' AS ac "
            "FROM scenario_runs WHERE seed = ANY(:seeds) "
            "AND scenario_type IN ('gnss-degradation','aircraft-coverage-gap') "
            "ORDER BY seed, scenario_type, id"
        ), {"seeds": list(SEEDS)}).mappings().all()


def observations_for(run_id):
    with factory.begin() as s:
        rows = s.execute(text(
            "SELECT timestamp, ST_Y(location) AS lat, ST_X(location) AS lon, payload "
            "FROM observations WHERE scenario_run_id = :r AND observation_type='track' "
            "ORDER BY timestamp"), {"r": run_id}).mappings().all()
    return [CanonicalObservation(
        source_id="opensky-replay", source_type=SourceType.OPENSKY,
        observation_type=ObservationType.TRACK, timestamp=r["timestamp"],
        location=Location(lat=r["lat"], lon=r["lon"]), data_mode=DataMode.REPLAYED,
        validation_status=ValidationStatus.VALID,
        provenance=Provenance(source_id="opensky-replay", source_type=SourceType.OPENSKY,
                              data_mode=DataMode.REPLAYED, scenario_run_id=run_id),
        payload=TrackPayload(**r["payload"])) for r in rows]


print(f"{'run':>4} {'scenario':22} {'staged':>7} {'found':>6} {'hits':>5} {'recall':>7}  shapes")
print("-" * 78)
tot_staged = tot_hits = 0
by_type = {}
for row in run_rows():
    ac = row["ac"] or []
    staged = {a["aircraft_id"] if isinstance(a, dict) else a for a in ac}
    if not staged:
        continue
    gaps = detect_track_gaps(observations_for(row["id"]), POLICY)
    found_ids = {g.aircraft_id for g in gaps}
    hits = staged & found_ids
    shapes = {}
    for g in gaps:
        if g.aircraft_id in staged:
            shapes[g.shape.value] = shapes.get(g.shape.value, 0) + 1
    rec = len(hits) / len(staged)
    d = by_type.setdefault(row["scenario_type"], [0, 0])
    d[0] += len(staged); d[1] += len(hits)
    tot_staged += len(staged); tot_hits += len(hits)
    print(f"{row['id']:>4} {row['scenario_type']:22} {len(staged):>7} {len(gaps):>6} "
          f"{len(hits):>5} {rec:>6.0%}  {shapes or '—'}")

print()
for k, (s, h) in by_type.items():
    print(f"{k:22} staged {s:3}  detected {h:3}   recall {h/s:.0%}")
print(f"{'overall':22} staged {tot_staged:3}  detected {tot_hits:3}   recall {tot_hits/tot_staged:.0%}")
