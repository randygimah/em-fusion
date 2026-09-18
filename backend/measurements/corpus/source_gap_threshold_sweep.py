"""Does a fixed threshold separate a coverage gap from everything else, on one run?

`source_gap_zone_scoring.py` asked whether a staged zone beats **its own
control**, and on corpus v2 it does: 20 wins to 7 losses at 20 km, about one
in fifty. That re-opened `anom-006`. It does not build it. A sign test over
matched pairs says the staged zone *tends to* be worse than its twin; a
detector has no twin, sees one run, and must answer against a fixed bar.
Two populations can overlap almost completely and still win a pairwise
comparison nearly every time.

So this runs the same machinery over **every** run in the corpus and asks the
detector's question instead: sensitivity against false-alarm rate across a
sweep of (cluster radius, minimum cluster size, excess threshold).

Pre-registered in `source_gap_threshold_prereg.md` before it was run --
including the development/holdout split, the operating-point rule, and the
bar at which `anom-006` closes again rather than being built. Read that
first; the decision it records is not re-derivable from this output.

The size floor is swept rather than fixed at one because the earlier
measurement already said why: a ratio over a disc holding one to three
findings is dominated by `anom-012`'s smoothing term, so the maximum across
zones selects for small-sample noise. Sweeping the threshold alone would
measure a rule nobody would build.
"""
from __future__ import annotations

import json
import os
import sys
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

POSITIVE = "aircraft-coverage-gap"
#: The decisive negative. `anom-008` requires zero reportable anomalies here.
QUIET = "normal-baseline"
#: Stages nothing on the track side, so its findings are *identical* to the
#: quiet run at the same seed -- verified exactly below. It is not a second
#: independent negative and must never be counted as one.
MIRROR_NEGATIVE = "rf-sensor-fault"
#: A negative, and not a clean one: this arm FREEZES track staleness, so it
#: genuinely perturbs the track side. A firing here confuses two real
#: effects rather than inventing one. Reported, outside the decision rule.
UNCLEAN_NEGATIVE = "gnss-degradation"
#: NOT a negative. `tracks.py` gives this arm the same SUPPRESS mode as the
#: positive, so at a shared seed its track findings are identical to the
#: coverage-gap run's -- again verified exactly. A firing here is detecting
#: a real staged gap, and `anom-013` gives the zone to `SENSOR-FAULT` first.
CO_STAGED = "ambiguous-mixed-evidence"

ARMS = [POSITIVE, QUIET, MIRROR_NEGATIVE, UNCLEAN_NEGATIVE, CO_STAGED]
SIZE_FLOORS = [1, 2, 3, 4, 5, 6]

#: Cached per-run zones, so the sweep can be re-read without re-measuring.
#: Ratios and group sizes only -- no aircraft identifier and no position
#: ever reaches this file, which is what lets it be looked at freely. It is
#: gitignored: derived from the corpus and regenerable from it.
CACHE = os.environ.get("ZONE_CACHE", "/tmp/source_gap_zones.json")

print(_corpus.describe(), flush=True)

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


def zones_for(run_id):
    """Every cluster-proposed zone on this run, as (ratio, size) per radius.

    Identical machinery to `source_gap_zone_scoring.py` -- the same gap
    policy, the same window derivation, the same excess disc -- so the two
    measurements are comparable. What differs is that this keeps every zone
    rather than only the strongest, because the size floor is a dial here
    and taking the maximum first would fix it at one.
    """
    tracks = tracks_for(run_id)
    if not tracks:
        return None
    span = (min(o.timestamp for o in tracks), max(o.timestamp for o in tracks))
    findings = detect_track_gaps(tracks, GAP)
    if not findings:
        return {str(km): [] for km in CLUSTER_RADII}
    save_findings(factory, scenario_run_id=run_id, rule_id="TRACK-GAP",
                  findings=[from_track_gap(f, scenario_run_id=run_id)
                            for f in findings])
    out = {}
    for cluster_km in CLUSTER_RADII:
        groups = cluster_findings(factory, scenario_run_id=run_id,
                                  rule_id="TRACK-GAP", window=span,
                                  radius_km=cluster_km)
        zones = []
        for g in groups:
            # The cluster carries a centroid and its members, not a window;
            # the window is the span the members cover, kept strictly inside
            # the run so the remainder it is compared against is not empty.
            w = (max(min(m.started_at for m in g.members),
                     span[0] + timedelta(seconds=1)),
                 min(max(m.ended_at for m in g.members),
                     span[1] - timedelta(seconds=1)))
            if (w[1] - w[0]).total_seconds() <= 0:
                continue
            try:
                r = measure_rate_excess(
                    factory, scenario_run_id=run_id, centre=g.centroid,
                    policy=ExcessPolicy(radius_km=EXCESS_RADIUS),
                    window=w, run_span=span)
            except ValueError:
                continue
            zones.append([r.ratio, g.size])
        out[str(cluster_km)] = zones
    return out


def collect():
    with factory.begin() as s:
        runs = s.execute(text(
            "SELECT id, seed, scenario_type, "
            "(parameters->>'base_seed')::bigint AS base_seed "
            f"FROM scenario_runs WHERE {_corpus.run_filter()} ORDER BY id"
        )).mappings().all()
    print(f"{len(runs)} runs to measure", flush=True)
    records = []
    for n, r in enumerate(runs, 1):
        zones = zones_for(r["id"])
        records.append({"id": r["id"], "seed": r["seed"],
                        "type": r["scenario_type"], "base_seed": r["base_seed"],
                        "zones": zones})
        if n % 10 == 0 or n == len(runs):
            print(f"  {n}/{len(runs)} runs measured", flush=True)
    with open(CACHE, "w") as fh:
        json.dump(records, fh)
    return records




def statistic(record, cluster_km, size_floor):
    """What the detector would see: the strongest qualifying zone, or nothing.

    The maximum, because a rule proposing several zones reports the worst
    one. That is also where the earlier measurement said the danger is --
    the maximum across zones selects for the noisiest small sample -- which
    is why the size floor is a dial here rather than fixed at one.
    """
    if record["zones"] is None:
        return None
    ratios = [ratio for ratio, size in record["zones"][str(cluster_km)]
              if size >= size_floor]
    return max(ratios) if ratios else None


def fired(pop, arm, cluster_km, size_floor, threshold):
    """(how many of this arm fire, how many there are)."""
    arm_records = [r for r in pop if r["type"] == arm]
    hits = sum(1 for r in arm_records
               if (lambda v: v is not None and v >= threshold)(
                   statistic(r, cluster_km, size_floor)))
    return hits, len(arm_records)


def candidates(pop, cluster_km, size_floor):
    """Every observed value is a candidate threshold.

    A fixed grid can step straight over the only interesting point; the
    observed values cannot, and they are the only thresholds that change
    any answer.
    """
    seen = {statistic(r, cluster_km, size_floor) for r in pop}
    return sorted(v for v in seen if v is not None)


if os.path.exists(CACHE) and os.environ.get("REUSE_CACHE"):
    print(f"reusing cached zones from {CACHE}", flush=True)
    records = json.load(open(CACHE))
else:
    records = collect()

development = [r for r in records if r["base_seed"] in _corpus.BASE_SEEDS[:2]]
holdout = [r for r in records if r["base_seed"] == _corpus.BASE_SEEDS[2]]
print(f"\ndevelopment {len(development)} runs (base seeds "
      f"{_corpus.BASE_SEEDS[0]}, {_corpus.BASE_SEEDS[1]}), "
      f"holdout {len(holdout)} runs (base seed {_corpus.BASE_SEEDS[2]})")

# ------------------------------------------------- are the arms independent?
print("\n" + "=" * 78)
print("ARM IDENTITY -- checked before anything is counted")
print("=" * 78)


def signature(arm):
    return [tuple(tuple(z) for z in r["zones"]["60.0"])
            for r in sorted(records, key=lambda x: x["seed"]) if r["type"] == arm]


same_neg = signature(QUIET) == signature(MIRROR_NEGATIVE)
same_pos = signature(POSITIVE) == signature(CO_STAGED)
print(f"  {QUIET} == {MIRROR_NEGATIVE}: {same_neg}")
print(f"  {POSITIVE} == {CO_STAGED}: {same_pos}")
print("""
Both are exact, and both follow from `tracks.py`: neither the quiet arm nor
the sensor-fault arm perturbs tracks, and the coverage-gap and ambiguous
arms share one SUPPRESS mode. So the clean negative population is 60
DISTINCT SEEDS and not 120 runs, and the ambiguous arm is not independent
evidence about this rule. Any false-alarm rate quoted "of 120" here would
be counting the same run twice.""")

# ----------------------------------------------------------------- the sweep
print("\n" + "=" * 78)
print("DEVELOPMENT -- the lowest threshold at which the quiet arm goes silent")
print("=" * 78)
print("Zero quiet-arm alarms is the pre-registered constraint: that arm is")
print("`anom-008`'s control and a rule firing there breaks a passing item.\n")
print(f"{'km':>4} {'floor':>5} {'thresh':>7} {'gap':>9} {'QUIET':>9} "
      f"{'fault':>9} {'gnss':>9} {'ambig':>9}")

best = None
for cluster_km in CLUSTER_RADII:
    for size_floor in SIZE_FLOORS:
        for threshold in candidates(development, cluster_km, size_floor):
            quiet, n_quiet = fired(development, QUIET, cluster_km,
                                   size_floor, threshold)
            if quiet:
                continue
            gap, n_gap = fired(development, POSITIVE, cluster_km,
                               size_floor, threshold)
            # A rule that fires on nothing satisfies "zero false alarms"
            # vacuously. It is not an operating point.
            if gap == 0:
                break
            fault, _ = fired(development, MIRROR_NEGATIVE, cluster_km,
                             size_floor, threshold)
            gnss, _ = fired(development, UNCLEAN_NEGATIVE, cluster_km,
                            size_floor, threshold)
            ambig, _ = fired(development, CO_STAGED, cluster_km,
                             size_floor, threshold)
            print(f"{cluster_km:>4.0f} {size_floor:>5} {threshold:>7.2f} "
                  f"{gap:>4}/{n_gap:<4} {quiet:>4}/{n_quiet:<4} "
                  f"{fault:>4}/40  {gnss:>4}/40  {ambig:>4}/40")
            key = (gap / n_gap, size_floor, threshold)
            if best is None or key > best[0]:
                best = (key, cluster_km, size_floor, threshold, gap, n_gap)
            break  # the lowest such threshold is the most sensitive one

# ------------------------------------------- how good could it be at all?
print("\n" + "=" * 78)
print("BEST TRADE-OFF ANYWHERE, ignoring the zero-quiet constraint")
print("=" * 78)
print("Youden's J = sensitivity - false-alarm rate; 0 is a coin flip.")
print("`anom-012` reported 0.23 to 0.40 and this project already calls that")
print("weak. A J here no better than that is the ceiling, not the floor.\n")
print(f"{'km':>4} {'floor':>5} {'best J':>7} {'thresh':>7} {'sens':>6} {'fpr':>6}")
ceiling = None
for cluster_km in CLUSTER_RADII:
    for size_floor in SIZE_FLOORS:
        row = None
        for threshold in candidates(development, cluster_km, size_floor):
            gap, n_gap = fired(development, POSITIVE, cluster_km, size_floor, threshold)
            quiet, n_quiet = fired(development, QUIET, cluster_km, size_floor, threshold)
            sens, fpr = gap / n_gap, quiet / n_quiet
            if row is None or sens - fpr > row[0]:
                row = (sens - fpr, threshold, sens, fpr)
        if row:
            print(f"{cluster_km:>4.0f} {size_floor:>5} {row[0]:>7.3f} "
                  f"{row[1]:>7.2f} {row[2]:>6.2f} {row[3]:>6.2f}")
            if ceiling is None or row[0] > ceiling[0]:
                ceiling = (row[0], cluster_km, size_floor) + row[1:]
if ceiling:
    print(f"\nCeiling on development: J = {ceiling[0]:.3f} at "
          f"{ceiling[1]:.0f} km, floor {ceiling[2]}, threshold {ceiling[3]:.2f} "
          f"(sensitivity {ceiling[4]:.2f} at a {ceiling[5]:.2f} quiet-arm rate, "
          f"which `anom-008` forbids outright).")

# --------------------------------------------------------------- the holdout
print("\n" + "=" * 78)
if best is None:
    print("NO development operating point fires on a coverage gap while leaving")
    print("the quiet arm silent. `anom-006` closes on this evidence.")
    raise SystemExit(0)

(sens, _, _), cluster_km, size_floor, threshold, gap, n_gap = best
print("OPERATING POINT chosen on development by the pre-registered rule")
print("=" * 78)
print(f"  cluster radius    {cluster_km:.0f} km")
print(f"  minimum zone size {size_floor} findings")
print(f"  excess threshold  {threshold:.2f}")
print(f"  development       {gap}/{n_gap} = {sens:.2f} sensitivity, "
      f"0/{len(development) // 5} quiet-arm alarms")

print(f"\nHOLDOUT -- base seed {_corpus.BASE_SEEDS[2]}, scored once, not re-entered")
for arm in ARMS:
    hits, n = fired(holdout, arm, cluster_km, size_floor, threshold)
    role = {POSITIVE: "POSITIVE -- what the rule is for",
            QUIET: "decisive negative (anom-008)",
            MIRROR_NEGATIVE: "same findings as the quiet arm, not independent",
            UNCLEAN_NEGATIVE: "negative, unclean -- freezes tracks",
            CO_STAGED: "same findings as the positive, not a negative"}[arm]
    print(f"  {arm:<26} {hits:>3}/{n:<4} ({hits / n:.2f})  {role}")

h_gap, h_n = fired(holdout, POSITIVE, cluster_km, size_floor, threshold)
h_quiet, _ = fired(holdout, QUIET, cluster_km, size_floor, threshold)
h_gnss, h_ngnss = fired(holdout, UNCLEAN_NEGATIVE, cluster_km, size_floor, threshold)
h_sens = h_gap / h_n

print(f"\nPre-registered bar: sensitivity >= 0.25 with ZERO quiet-arm alarms.")
print(f"Holdout: sensitivity {h_sens:.2f}, quiet-arm alarms {h_quiet}.")
print("VERDICT:", "SEPARATES -- build the rule against this curve"
      if h_sens >= 0.25 and h_quiet == 0
      else "DOES NOT SEPARATE -- anom-006 closes again on this evidence")

if h_gnss / h_ngnss > h_sens:
    print(f"""
AND THE RULE POINTS THE WRONG WAY. At this operating point it fires on
{h_gnss} of {h_ngnss} `{UNCLEAN_NEGATIVE}` runs ({h_gnss / h_ngnss:.2f}) against
{h_gap} of {h_n} coverage gaps ({h_sens:.2f}) -- more often on the arm it is not
for than on the arm it is. `anom-013` orders SENSOR-FAULT, SOURCE-GAP,
FUSION-SPATIAL, so SOURCE-GAP outranks the interference rule: a firing
here does not merely add a wrong finding, it can take the zone before
FUSION-SPATIAL is offered it, on the one arm the ladder currently gets
right 60 of 60. Whether the zones actually overlap is NOT measured here
-- this script kept no centroids -- so the hazard is established and its
size is not.""")
