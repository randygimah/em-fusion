"""anom-011's deliverable: where the four staged aircraft in five go."""
from __future__ import annotations

import os
from collections import Counter
from datetime import timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, SourceType, TrackPayload, ValidationStatus)
from app.detection.sensitivity import Conditions, Loss, measure_recall
from app.detection.track_gap import BoundingBox, GapPolicy

BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)
POLICY = GapPolicy(threshold=timedelta(seconds=100),
                   contact_fresh_within=timedelta(seconds=30), box=BOX)
BATCH = os.environ.get("BATCH_LABEL", "batch-1 (stored, base seed unknown)")

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


with factory.begin() as s:
    runs = s.execute(text(
        "SELECT id, scenario_type, ground_truth->'aircraft' AS ac FROM scenario_runs "
        "WHERE scenario_type IN ('gnss-degradation','aircraft-coverage-gap',"
        "'ambiguous-mixed-evidence') ORDER BY scenario_type, id")).mappings().all()

per_type: dict[str, dict] = {}
skipped = 0
for row in runs:
    ac = row["ac"] or []
    staged = {a["aircraft_id"] if isinstance(a, dict) else a for a in ac}
    if not staged:
        skipped += 1
        continue
    obs = observations_for(row["id"])
    if not obs:
        continue
    # Restricted to staged aircraft that were airborne at some point in the
    # run. The generator's targeting tests position against the zone radius
    # and nothing else, so it stages on parked aircraft too -- and anom-010
    # refuses those correctly, because an aircraft on the ground stopped
    # reporting when it was switched off.
    airborne = {
        o.payload.aircraft_id for o in obs if not o.payload.on_ground
    }
    if os.environ.get("AIRBORNE_ONLY"):
        staged = staged & airborne
        if not staged:
            skipped += 1
            continue
    result = measure_recall(
        staged_aircraft=staged, observations=obs, policy=POLICY,
        conditions=Conditions(batch=BATCH, scenario_type=row["scenario_type"], runs=1),
    )
    d = per_type.setdefault(row["scenario_type"], {"staged": 0, "detected": 0,
                                                   "losses": Counter(), "runs": 0})
    d["staged"] += result.staged
    d["detected"] += result.detected
    d["losses"].update(result.losses)
    d["runs"] += 1

print(f"Conditions: {BATCH}")
print(f"  threshold {POLICY.threshold.total_seconds():.0f} s, "
      f"contact fresh within {POLICY.contact_fresh_within.total_seconds():.0f} s, "
      f"interior margin {POLICY.interior_margin_deg} deg")
print(f"  {skipped} runs excluded for staging nothing\n")

order = [Loss.NOT_IN_RUN, Loss.NO_PAIR, Loss.NOT_INTERIOR, Loss.ON_GROUND,
         Loss.CONTACT_NOT_FRESH, Loss.BELOW_THRESHOLD, Loss.POSITION_NOT_STALE]
hdr = f"{'scenario':24} {'runs':>5} {'staged':>7} {'found':>6} {'recall':>7}  " + \
      "  ".join(l.value[:9].rjust(9) for l in order)
print(hdr); print("-" * len(hdr))

grand = {"staged": 0, "detected": 0, "losses": Counter()}
for scenario, d in per_type.items():
    cells = "  ".join(str(d["losses"].get(l, 0)).rjust(9) for l in order)
    print(f"{scenario:24} {d['runs']:>5} {d['staged']:>7} {d['detected']:>6} "
          f"{d['detected']/d['staged']:>6.0%}  {cells}")
    grand["staged"] += d["staged"]; grand["detected"] += d["detected"]
    grand["losses"].update(d["losses"])

cells = "  ".join(str(grand["losses"].get(l, 0)).rjust(9) for l in order)
print(f"{'ALL':24} {'':>5} {grand['staged']:>7} {grand['detected']:>6} "
      f"{grand['detected']/grand['staged']:>6.0%}  {cells}")

missed = grand["staged"] - grand["detected"]
print(f"\nOf {missed} undetected staged aircraft:")
for loss, n in sorted(grand["losses"].items(), key=lambda kv: -kv[1]):
    print(f"  {loss.value:22} {n:5}  {n/missed:5.0%}")
