"""How many staged aircraft does a coverage-gap run need to be findable?

scn-007 puts a floor under the number of aircraft a run stages on. The floor
is the whole point of the item and the item does not say what it is. This
measures it rather than choosing it.

The question is not "how many is more" but "how many is enough to see". A
quiet run genuinely holds ~15 track-gap findings, so a staged run has to
clear its own control by enough that a detector -- which sees one run and
never its control -- could tell. The existing corpus already contains the
experiment: 40 seed-matched pairs, same seed, same corpus window, same
aircraft, differing only in what was staged. Grouping those pairs by how
many aircraft the run actually staged on gives the excess as a function of
the count, which is the curve the floor should be read off.

The limit of it, stated in advance: the current generator draws a mean of
1.7 with a maximum of 5, so the high-count cells are thin and the curve
cannot be read far. If it cannot be read at all, that is the finding, and
the floor then has to come from the background arithmetic instead -- which
this also prints.

**Restricted to runs 121-240 by default, and that is not a detail.** Runs
1-100 were generated before scn-006 put the airborne gate in, when 55 per
cent of every injection landed on a parked aircraft: their answer keys name
a mean of 4.4 to 5.2 aircraft against 1.6 to 1.9 afterwards, and most of
the difference is aircraft that anom-010 correctly refuses because an
aircraft on the ground stopped reporting when it was switched off. Measured
across the boundary, the high-count cells fill up with runs whose staged
aircraft were never detectable, and the curve reads as though more staging
buys nothing. Runs 1-20 are also 600 s where every later run is 900 s, so
they carry two thirds of the track observations. Override with RUN_LO and
RUN_HI only to look at the old generator deliberately.
"""
from __future__ import annotations

import os
import statistics
from collections import defaultdict
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


def tracks_for(run_id):
    with factory.begin() as s:
        rows = s.execute(text(
            "SELECT timestamp, ST_Y(location) AS lat, ST_X(location) AS lon, payload "
            "FROM observations WHERE observation_type='track' AND scenario_run_id=:r "
            "ORDER BY timestamp"), {"r": run_id}).mappings().all()
    return [CanonicalObservation(
        source_id="opensky", source_type=SourceType.OPENSKY,
        observation_type=ObservationType.TRACK, timestamp=r["timestamp"],
        location=Location(lat=r["lat"], lon=r["lon"]),
        data_mode=DataMode.REPLAYED, validation_status=ValidationStatus.VALID,
        provenance=Provenance(source_id="opensky", source_type=SourceType.OPENSKY,
                              data_mode=DataMode.REPLAYED, scenario_run_id=run_id),
        payload=TrackPayload(**r["payload"])) for r in rows]


LO = int(os.environ.get("RUN_LO", "121"))
HI = int(os.environ.get("RUN_HI", "240"))

with factory.begin() as s:
    runs = s.execute(text(
        "SELECT id, scenario_type, seed, ground_truth FROM scenario_runs "
        "WHERE id BETWEEN :lo AND :hi ORDER BY id"), {"lo": LO, "hi": HI}).mappings().all()
print(f"runs {LO}-{HI} (post-scn-006 by default; 1-100 used the pre-gate generator)")

# Pair a coverage-gap run with the run sharing its seed that staged nothing
# on the tracks -- the same corpus window and the same aircraft.
by_seed = defaultdict(dict)
for r in runs:
    by_seed[r["seed"]][r["scenario_type"]] = r

pairs = []
for seed, arms in by_seed.items():
    staged = arms.get("aircraft-coverage-gap")
    control = arms.get("rf-sensor-fault")
    if staged and control:
        pairs.append((staged, control))

print(f"seed-matched pairs: {len(pairs)}")

by_count = defaultdict(list)
staged_counts = []
control_totals = []

for staged, control in pairs:
    n = len((staged["ground_truth"] or {}).get("aircraft") or [])
    staged_counts.append(n)
    s_findings = detect_track_gaps(tracks_for(staged["id"]), POLICY)
    c_findings = detect_track_gaps(tracks_for(control["id"]), POLICY)
    by_count[n].append((len(s_findings), len(c_findings)))
    control_totals.append(len(c_findings))

print(f"staged aircraft per run: mean {statistics.mean(staged_counts):.2f}, "
      f"max {max(staged_counts)}, zero on {staged_counts.count(0)} of {len(pairs)}")
print()
print("the background a staged run has to clear, from the control arm:")
print(f"  findings per control run: mean {statistics.mean(control_totals):.1f}, "
      f"sd {statistics.pstdev(control_totals):.1f}, "
      f"min {min(control_totals)}, max {max(control_totals)}")
print()
print(f"  {'staged':>6}  {'pairs':>5}  {'staged mean':>11}  {'control mean':>12}  "
      f"{'excess':>7}  {'wins':>9}")
for n in sorted(by_count):
    rows = by_count[n]
    sm = statistics.mean(a for a, _ in rows)
    cm = statistics.mean(b for _, b in rows)
    wins = sum(1 for a, b in rows if a > b)
    print(f"  {n:>6}  {len(rows):>5}  {sm:>11.1f}  {cm:>12.1f}  "
          f"{sm - cm:>+7.1f}  {wins:>4}/{len(rows):<4}")

sd = statistics.pstdev(control_totals)
print()
print("the arithmetic, for when the curve is too thin to read:")
print(f"  a staged aircraft yields ~1.0 detected dropout (source_gap_ceiling.py).")
print(f"  the control background has sd {sd:.1f} findings per run, so an excess")
print(f"  of one sd needs about {sd:.0f} staged aircraft and two sd about {2*sd:.0f}.")
