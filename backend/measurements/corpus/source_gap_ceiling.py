"""Can anom-006 be built on this corpus?

The rule fires when track dropouts are present and no co-located RF anomaly
is. Two things make that hard, and both are properties of the corpus rather
than of any detector:

  * a quiet run genuinely holds ~138 raw track-gap findings, so "dropouts
    are present" is true of every run ever generated; and
  * since scn-006, a coverage-gap run stages a mean of 1.7 aircraft, and
    11 of 40 stage none at all.

So this measures the ceiling rather than a design: over 40 coverage-gap
runs and their seed-matched controls, is there anything on the track side
that separates them -- before asking how a detector would find it.

The control is rf-sensor-fault at the same seed: same corpus window, same
aircraft, nothing staged on tracks at all (0 of 40, verified).
"""
from __future__ import annotations

import os
from collections import Counter, defaultdict
from datetime import timedelta

import _corpus
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, TrackPayload, ValidationStatus)
from app.detection.track_gap import BoundingBox, GapPolicy, detect_track_gaps

BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)
GAP = GapPolicy(threshold=timedelta(seconds=100),
                contact_fresh_within=timedelta(seconds=30), box=BOX)

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


from app.dal.models import SourceType  # noqa: E402

with factory.begin() as s:
    runs = s.execute(text(
        "SELECT id, seed, scenario_type, ground_truth FROM scenario_runs "
        f"WHERE {_corpus.run_filter()} AND scenario_type IN "
        "('aircraft-coverage-gap','rf-sensor-fault') ORDER BY id")).mappings().all()

pairs = defaultdict(dict)
for r in runs:
    pairs[r["seed"]][r["scenario_type"]] = r

print(f"seeds with both arms: "
      f"{sum(1 for p in pairs.values() if len(p) == 2)} of {len(pairs)}")

staged_counts = []
rows = []
for seed, pair in sorted(pairs.items()):
    if len(pair) < 2:
        continue
    gap_run = pair["aircraft-coverage-gap"]
    ctl_run = pair["rf-sensor-fault"]
    staged = set((gap_run["ground_truth"] or {}).get("aircraft") or [])
    staged_counts.append(len(staged))

    g = detect_track_gaps(tracks_for(gap_run["id"]), GAP)
    c = detect_track_gaps(tracks_for(ctl_run["id"]), GAP)
    hit = sum(1 for f in g if f.aircraft_id in staged)
    rows.append((len(staged), len(g), len(c), hit))

n = len(rows)
print(f"\nmatched pairs: {n}")
print(f"runs staging nothing at all: {sum(1 for r in rows if r[0] == 0)} of {n}")
print(f"staged aircraft per run: mean {sum(r[0] for r in rows)/n:.1f}, "
      f"max {max(r[0] for r in rows)}")

print(f"\n{'':22} {'coverage-gap':>14} {'its control':>13}")
print(f"{'findings per run, mean':22} {sum(r[1] for r in rows)/n:14.1f} "
      f"{sum(r[2] for r in rows)/n:13.1f}")
more = sum(1 for r in rows if r[1] > r[2])
same = sum(1 for r in rows if r[1] == r[2])
print(f"{'staged beats control':22} {more:>14} of {n}   (ties {same})")
print(f"\ndetected staged dropouts per run: "
      f"{sum(r[3] for r in rows)/n:.2f} against a background of "
      f"{sum(r[2] for r in rows)/n:.1f}")

only = [r for r in rows if r[0] > 0]
if only:
    m = len(only)
    more_s = sum(1 for r in only if r[1] > r[2])
    print(f"\nrestricted to the {m} runs that staged anything:")
    print(f"  staged beats control: {more_s} of {m}")
    print(f"  detected staged per run: {sum(r[3] for r in only)/m:.2f}")
    print(f"  recall on staged aircraft: "
          f"{sum(r[3] for r in only)}/{sum(r[0] for r in only)}")
