"""The prediction recorded with scn-006, re-measured on batch 2.

anom-004 found no separation between a staged run and its seed-matched
control at any radius 5-60 km, on runs where 55% of the signal was never
present. Does restoring it change the answer?
"""
from __future__ import annotations

import os
from datetime import timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, SourceType, TrackPayload, ValidationStatus)
from app.db.findings import save_findings
from app.detection.clustering import ClusterPolicy, cluster_track_gaps
from app.detection.findings import from_track_gap
from app.detection.track_gap import BoundingBox, GapPolicy, detect_track_gaps

BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)
POLICY = GapPolicy(threshold=timedelta(seconds=100),
                   contact_fresh_within=timedelta(seconds=30), box=BOX)
RADII = [5.0, 10.0, 20.0, 30.0, 45.0, 60.0]
LO, HI = int(os.environ["RUN_LO"]), int(os.environ["RUN_HI"])
LABEL = os.environ["BATCH_LABEL"]

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)


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


def measure(run_id):
    obs = observations_for(run_id)
    gaps = detect_track_gaps(obs, POLICY)
    save_findings(factory, scenario_run_id=run_id, rule_id="TRACK-GAP",
                  findings=[from_track_gap(g, scenario_run_id=run_id) for g in gaps])
    ts = [o.timestamp for o in obs]
    window = (min(ts) - timedelta(seconds=1), max(ts) + timedelta(seconds=1))
    out = {}
    for r in RADII:
        groups = cluster_track_gaps(factory, scenario_run_id=run_id, window=window,
                                    policy=ClusterPolicy(radius_km=r))
        out[r] = (len(groups), max((g.size for g in groups), default=0))
    return len(gaps), out


with factory.begin() as s:
    rows = s.execute(text(
        "SELECT seed, scenario_type, min(id) AS id FROM scenario_runs "
        "WHERE id BETWEEN :lo AND :hi AND scenario_type IN "
        "('rf-sensor-fault','gnss-degradation','aircraft-coverage-gap') "
        "GROUP BY seed, scenario_type"), {"lo": LO, "hi": HI}).all()
by_seed = {}
for seed, scenario, run_id in rows:
    by_seed.setdefault(seed, {})[scenario] = run_id
triples = [(s, m) for s, m in sorted(by_seed.items()) if len(m) == 3]

print(f"{LABEL}: {len(triples)} seed-matched triples\n")
CONTROL, STAGED = "rf-sensor-fault", ("gnss-degradation", "aircraft-coverage-gap")
agg = {k: {r: [] for r in RADII} for k in (CONTROL, *STAGED)}
found = {k: [] for k in (CONTROL, *STAGED)}
for seed, runs in triples:
    for scenario in (CONTROL, *STAGED):
        n, res = measure(runs[scenario])
        found[scenario].append(n)
        for r in RADII:
            agg[scenario][r].append(res[r])

print(f"{'scenario':24} {'found':>6} " + " ".join(f"r={r:g}km".rjust(14) for r in RADII))
print("-" * (24 + 7 + 15 * len(RADII)))
for scenario in (CONTROL, *STAGED):
    cells = []
    for r in RADII:
        rowsr = agg[scenario][r]
        g = sum(x[0] for x in rowsr) / len(rowsr)
        b = sum(x[1] for x in rowsr) / len(rowsr)
        cells.append(f"{g:5.2f} /{b:5.2f}".rjust(14))
    print(f"{scenario:24} {sum(found[scenario])/len(found[scenario]):6.2f} " + " ".join(cells))

print(f"\nstaged minus control, largest group (wins / {len(triples)} triples)")
for scenario in STAGED:
    line = []
    for r in RADII:
        diffs = [s[1] - c[1] for s, c in zip(agg[scenario][r], agg[CONTROL][r])]
        wins = sum(1 for d in diffs if d > 0)
        line.append(f"{sum(diffs)/len(diffs):+5.2f} ({wins}/{len(diffs)})".rjust(14))
    print(f"{scenario:24} {'':>6} " + " ".join(line))
