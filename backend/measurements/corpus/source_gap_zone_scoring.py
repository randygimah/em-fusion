"""Does a staged coverage gap concentrate anywhere a detector could find?

Run-level counts say the effect is real and tiny: 16.1 findings against
15.1, never fewer, over 40 matched pairs. A detector sees one run and
cannot tell 16 from 15. The remaining hope is that the staged dropouts sit
*together* -- so this proposes zones from the track side by clustering and
asks whether the best zone on a staged run beats the best zone on its own
control.

The comparison absorbs the circularity rather than avoiding it: a
cluster-derived window is by construction where the findings are, so the
excess is inflated on both arms equally and only the difference is read.
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import timedelta

import _corpus
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, SourceType, TrackPayload, ValidationStatus)
from app.db.findings import cluster_findings, save_findings
from app.detection.findings import from_track_gap
from app.detection.rate_excess import ExcessPolicy, measure_rate_excess
from app.detection.track_gap import BoundingBox, GapPolicy, detect_track_gaps

BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)
GAP = GapPolicy(threshold=timedelta(seconds=100),
                contact_fresh_within=timedelta(seconds=30), box=BOX)
CLUSTER_RADII = [20.0, 40.0, 60.0]
EXCESS_RADIUS = 60.0

print(_corpus.describe())

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)


def tracks_for(run_id):
    with factory.begin() as s:
        rows = s.execute(text(
            "SELECT timestamp, ST_Y(location) AS lat, ST_X(location) AS lon, payload "
            "FROM observations WHERE scenario_run_id=:r AND observation_type='track' "
            "ORDER BY timestamp"), {"r": run_id}).mappings().all()
    return [CanonicalObservation(
        source_id="o", source_type=SourceType.OPENSKY,
        observation_type=ObservationType.TRACK, timestamp=r["timestamp"],
        location=Location(lat=r["lat"], lon=r["lon"]), data_mode=DataMode.REPLAYED,
        validation_status=ValidationStatus.VALID,
        provenance=Provenance(source_id="o", source_type=SourceType.OPENSKY,
                              data_mode=DataMode.REPLAYED, scenario_run_id=run_id),
        payload=TrackPayload(**r["payload"])) for r in rows]


def best_zone_excess(run_id, cluster_km):
    """The strongest cluster-proposed zone on this run, as an excess."""
    tracks = tracks_for(run_id)
    if not tracks:
        return None
    span = (min(o.timestamp for o in tracks), max(o.timestamp for o in tracks))
    findings = detect_track_gaps(tracks, GAP)
    if not findings:
        return None
    save_findings(factory, scenario_run_id=run_id, rule_id="TRACK-GAP",
                  findings=[from_track_gap(f, scenario_run_id=run_id)
                            for f in findings])
    groups = cluster_findings(factory, scenario_run_id=run_id, rule_id="TRACK-GAP",
                              window=span, radius_km=cluster_km)
    best = None
    for g in groups:
        # The cluster carries a centroid and its members, not a window;
        # the window is the span the members cover.
        w = (max(min(m.started_at for m in g.members), span[0] + timedelta(seconds=1)),
             min(max(m.ended_at for m in g.members), span[1] - timedelta(seconds=1)))
        if (w[1] - w[0]).total_seconds() <= 0:
            continue
        try:
            r = measure_rate_excess(
                factory, scenario_run_id=run_id, centre=g.centroid,
                policy=ExcessPolicy(radius_km=EXCESS_RADIUS),
                window=w, run_span=span)
        except ValueError:
            continue
        if best is None or r.ratio > best:
            best = r.ratio
    return best


with factory.begin() as s:
    runs = s.execute(text(
        "SELECT id, seed, scenario_type, ground_truth FROM scenario_runs "
        f"WHERE {_corpus.run_filter()} AND scenario_type IN "
        "('aircraft-coverage-gap','rf-sensor-fault') ORDER BY id")).mappings().all()

pairs = defaultdict(dict)
for r in runs:
    pairs[r["seed"]][r["scenario_type"]] = r

for cluster_km in CLUSTER_RADII:
    beats = ties = losses = 0
    skipped = 0
    staged_only_beats = staged_only_n = 0
    for seed, pair in sorted(pairs.items()):
        if len(pair) < 2:
            continue
        gap_run, ctl_run = pair["aircraft-coverage-gap"], pair["rf-sensor-fault"]
        a = best_zone_excess(gap_run["id"], cluster_km)
        b = best_zone_excess(ctl_run["id"], cluster_km)
        if a is None or b is None:
            skipped += 1
            continue
        staged = len((gap_run["ground_truth"] or {}).get("aircraft") or [])
        if a > b:
            beats += 1
        elif a == b:
            ties += 1
        else:
            losses += 1
        if staged:
            staged_only_n += 1
            staged_only_beats += 1 if a > b else 0
    print(f"cluster {cluster_km:4.0f} km: staged beats control {beats}, "
          f"ties {ties}, control beats staged {losses} (skipped {skipped}); "
          f"among runs that staged anything, {staged_only_beats} of "
          f"{staged_only_n}", flush=True)
