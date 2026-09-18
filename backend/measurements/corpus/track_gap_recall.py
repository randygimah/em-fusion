"""anom-011 deliverable, per batch. RUN_LO/RUN_HI bound the batch."""
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
LO = int(os.environ.get("RUN_LO", "1"))
HI = int(os.environ.get("RUN_HI", "999999"))
LABEL = os.environ.get("BATCH_LABEL", f"runs {LO}-{HI}")

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
        "'ambiguous-mixed-evidence') AND id BETWEEN :lo AND :hi "
        "ORDER BY scenario_type, id"), {"lo": LO, "hi": HI}).mappings().all()

per_type: dict[str, dict] = {}
skipped = 0
parked_in_key = 0
staged_total = 0
for row in runs:
    ac = row["ac"] or []
    staged = {a["aircraft_id"] if isinstance(a, dict) else a for a in ac}
    if not staged:
        skipped += 1
        continue
    obs = observations_for(row["id"])
    if not obs:
        continue
    airborne = {o.payload.aircraft_id for o in obs if not o.payload.on_ground}
    staged_total += len(staged)
    parked_in_key += len(staged - airborne)
    result = measure_recall(
        staged_aircraft=staged, observations=obs, policy=POLICY,
        conditions=Conditions(batch=LABEL, scenario_type=row["scenario_type"], runs=1))
    d = per_type.setdefault(row["scenario_type"],
                            {"staged": 0, "detected": 0, "losses": Counter(), "runs": 0})
    d["staged"] += result.staged
    d["detected"] += result.detected
    d["losses"].update(result.losses)
    d["runs"] += 1

print(f"{LABEL}")
print(f"  threshold {POLICY.threshold.total_seconds():.0f} s, contact fresh within "
      f"{POLICY.contact_fresh_within.total_seconds():.0f} s, interior margin "
      f"{POLICY.interior_margin_deg} deg")
print(f"  {skipped} runs excluded for staging nothing")
pct = parked_in_key / staged_total if staged_total else 0
print(f"  parked aircraft in the answer key: {parked_in_key}/{staged_total} = {pct:.0%}\n")

order = [Loss.NOT_IN_RUN, Loss.NO_PAIR, Loss.NOT_INTERIOR, Loss.ON_GROUND,
         Loss.CONTACT_NOT_FRESH, Loss.BELOW_THRESHOLD, Loss.POSITION_NOT_STALE]
hdr = (f"{'scenario':26} {'runs':>5} {'staged':>7} {'found':>6} {'recall':>7}  "
       + "  ".join(l.value[:9].rjust(9) for l in order))
print(hdr); print("-" * len(hdr))
grand = {"staged": 0, "detected": 0, "losses": Counter()}
for scenario, d in per_type.items():
    cells = "  ".join(str(d["losses"].get(l, 0)).rjust(9) for l in order)
    print(f"{scenario:26} {d['runs']:>5} {d['staged']:>7} {d['detected']:>6} "
          f"{d['detected']/d['staged']:>6.0%}  {cells}")
    grand["staged"] += d["staged"]; grand["detected"] += d["detected"]
    grand["losses"].update(d["losses"])
cells = "  ".join(str(grand["losses"].get(l, 0)).rjust(9) for l in order)
print(f"{'ALL':26} {'':>5} {grand['staged']:>7} {grand['detected']:>6} "
      f"{grand['detected']/grand['staged']:>6.0%}  {cells}")
