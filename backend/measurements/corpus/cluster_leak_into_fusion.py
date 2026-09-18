"""How exposed is FUSION-SPATIAL to background track clusters?

The dangerous case is not a clean run -- on a clean run RF-NOISE is silent
and nothing fuses. It is a run whose truth is `rf-sensor-fault`: the radio
side fires legitimately, and if ANY background track cluster happens to sit
within the fusion radius, FUSION-SPATIAL reports an interference zone where
the truth is a broken sensor. That anomaly would be real, its bundle would
be perfectly grounded, and the hypothesis built on it would be confidently
wrong.
"""
from __future__ import annotations

import os
from datetime import timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, SourceType, TrackPayload, ValidationStatus)
from app.db.findings import cluster_findings, save_findings
from app.detection.findings import from_track_gap
from app.detection.track_gap import BoundingBox, GapPolicy, detect_track_gaps
from app.scenario.layout import load_layout

BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)
POLICY = GapPolicy(threshold=timedelta(seconds=100),
                   contact_fresh_within=timedelta(seconds=30), box=BOX)
CLUSTER_KM = 20.0
#: The band scn-005 measured, in which every sensor has a neighbour inside
#: and a non-neighbour beyond. anom-005's radius must come from it.
FUSION_RADII = [55.7, 60.0, 70.0, 85.7]

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)
layout = load_layout()
POS = {s.sensor_id: (s.lat, s.lon) for s in layout.sensors}


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


with factory.begin() as s:
    runs = s.execute(text(
        "SELECT id, ground_truth->'sensors'->>0 AS centre FROM scenario_runs "
        "WHERE scenario_type='rf-sensor-fault' AND ground_truth->'sensors'->>0 IS NOT NULL "
        "ORDER BY id")).mappings().all()

print(f"Control runs (truth = sensor fault, nothing staged on tracks): {len(runs)}")
print(f"Clustering at {CLUSTER_KM:g} km. A cluster in range means FUSION-SPATIAL could fire.\n")
hdr = f"{'run':>4} {'faulty':>7} {'clusters':>9} " + " ".join(f"{r:g}km".rjust(14) for r in FUSION_RADII)
print(hdr); print("-" * len(hdr))

exposed = {r: 0 for r in FUSION_RADII}
biggest_in_range = {r: [] for r in FUSION_RADII}
total = 0
for row in runs:
    centre_id = row["centre"]
    if centre_id not in POS:
        continue
    lat, lon = POS[centre_id]
    obs = observations_for(row["id"])
    if not obs:
        continue
    total += 1
    gaps = detect_track_gaps(obs, POLICY)
    save_findings(factory, scenario_run_id=row["id"], rule_id="TRACK-GAP",
                  findings=[from_track_gap(g, scenario_run_id=row["id"]) for g in gaps])
    ts = [o.timestamp for o in obs]
    window = (min(ts) - timedelta(seconds=1), max(ts) + timedelta(seconds=1))
    groups = cluster_findings(factory, scenario_run_id=row["id"], rule_id="TRACK-GAP",
                              radius_km=CLUSTER_KM, window=window)
    cells = []
    for r in FUSION_RADII:
        near = [g for g in groups
                if _dist(g.centroid, lat, lon) <= r] if False else None
        # measure with the real query rather than app-side arithmetic
        from app.db.findings import findings_near
        hits = findings_near(factory, scenario_run_id=row["id"],
                             centre=Location(lat=lat, lon=lon), radius_km=r,
                             window=window, rule_id="TRACK-GAP")
        subjects = {f.subject for f in hits}
        in_range = [g for g in groups if any(m.subject in subjects for m in g.members)]
        n3 = [g for g in in_range if g.size >= 3]
        if in_range:
            exposed[r] += 1
        biggest_in_range[r].append(max((g.size for g in in_range), default=0))
        cells.append(f"{len(in_range)}/{len(n3)}".rjust(14))
    print(f"{row['id']:>4} {centre_id:>7} {len(groups):>9} " + " ".join(cells))

print(f"\n{'':>22} " + " ".join(f"{r:g}km".rjust(14) for r in FUSION_RADII))
print(f"{'runs with any cluster':>22} " +
      " ".join(f"{exposed[r]}/{total} = {exposed[r]/total:.0%}".rjust(14) for r in FUSION_RADII))
print(f"{'mean largest in range':>22} " +
      " ".join(f"{sum(biggest_in_range[r])/total:.2f}".rjust(14) for r in FUSION_RADII))
