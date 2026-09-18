"""Route B, measured before it is specified.

Instead of "is there a big cluster here", ask: **at this place, is the rate
of track discontinuities higher during the incident window than at the same
place outside it?**

The comparison is within one run and within one place, so it controls for
the two things that defeated clustering: air traffic is not uniform (busy
places are always busy) and runs differ from each other. Each run is its
own control, twice over.

Ground truth supplies the centre and window HERE ONLY, because this is a
feasibility measurement. The rule itself would take both from a detected
RF episode (api-009 keeps ground truth out of the detection path).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, SourceType, TrackPayload, ValidationStatus)
from app.detection.track_gap import BoundingBox, GapPolicy, detect_track_gaps
from app.scenario.layout import load_layout, great_circle_km

BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)
POLICY = GapPolicy(threshold=timedelta(seconds=100),
                   contact_fresh_within=timedelta(seconds=30), box=BOX)
RADII = [20.0, 30.0, 45.0, 60.0]
LO, HI = int(os.environ["RUN_LO"]), int(os.environ["RUN_HI"])

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)
POS = {s.sensor_id: (s.lat, s.lon) for s in load_layout().sensors}


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


def excess(run_id, centre, window, radius_km):
    """Findings per minute inside the disc, during the window vs outside it."""
    obs = observations_for(run_id)
    if not obs:
        return None
    gaps = detect_track_gaps(obs, POLICY)
    ts = [o.timestamp for o in obs]
    run_start, run_end = min(ts), max(ts)
    w_start, w_end = window
    during_s = (w_end - w_start).total_seconds()
    outside_s = (run_end - run_start).total_seconds() - during_s
    if during_s <= 0 or outside_s <= 0:
        return None

    near = [g for g in gaps
            if great_circle_km(centre[0], centre[1], g.location.lat, g.location.lon) <= radius_km]
    # A finding counts as "during" if its interval overlaps the window.
    during = sum(1 for g in near if g.started_at < w_end and g.ended_at > w_start)
    outside = len(near) - during
    return (during / during_s * 60.0, outside / outside_s * 60.0, during, outside)


with factory.begin() as s:
    rows = s.execute(text(
        "SELECT seed, scenario_type, min(id) AS id, "
        "  (array_agg(ground_truth ORDER BY id))[1] AS gt "
        "FROM scenario_runs WHERE id BETWEEN :lo AND :hi AND scenario_type IN "
        "('rf-sensor-fault','gnss-degradation','aircraft-coverage-gap') "
        "GROUP BY seed, scenario_type"), {"lo": LO, "hi": HI}).mappings().all()

by_seed = {}
for r in rows:
    by_seed.setdefault(r["seed"], {})[r["scenario_type"]] = (r["id"], r["gt"])
triples = [(s, m) for s, m in sorted(by_seed.items()) if len(m) == 3]
print(f"{len(triples)} seed-matched triples, runs {LO}-{HI}\n")

CONTROL, STAGED = "rf-sensor-fault", ("gnss-degradation", "aircraft-coverage-gap")
print(f"{'radius':>7}  {'scenario':24} {'during/min':>11} {'outside/min':>12} "
      f"{'ratio':>7} {'beats control':>14}")
print("-" * 82)

for radius in RADII:
    stats = {k: [] for k in (CONTROL, *STAGED)}
    wins = {k: 0 for k in STAGED}
    usable = 0
    for seed, runs in triples:
        gt = runs[CONTROL][1]
        centre_id = (gt.get("sensors") or [None])[0]
        if centre_id not in POS:
            continue
        centre = POS[centre_id]
        w = gt["window"]
        window = (datetime.fromisoformat(w["start"]), datetime.fromisoformat(w["end"]))
        got = {}
        for scenario in (CONTROL, *STAGED):
            r = excess(runs[scenario][0], centre, window, radius)
            if r is None:
                break
            got[scenario] = r
        if len(got) != 3:
            continue
        usable += 1
        for k, v in got.items():
            stats[k].append(v)
        for scenario in STAGED:
            if got[scenario][0] > got[CONTROL][0]:
                wins[scenario] += 1
    for scenario in (CONTROL, *STAGED):
        v = stats[scenario]
        d = sum(x[0] for x in v) / len(v)
        o = sum(x[1] for x in v) / len(v)
        ratio = d / o if o else float("inf")
        w = "" if scenario == CONTROL else f"{wins[scenario]}/{usable}"
        print(f"{radius:>7.0f}  {scenario:24} {d:>11.3f} {o:>12.3f} {ratio:>7.2f} {w:>14}")
    print()
