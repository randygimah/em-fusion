"""How many observations does a real bundle cite, and what does resolving them cost?

`evb-002` deferred one decision explicitly: whether a composite index on
`observations` is owed *before* this item or after it. The spec says the
question "follows from the composition decision" -- and that composition is
now fixed, because `evb-001` is built. So this is the measurement that
closes it.

`evidence_ref_uniqueness.py` established that a cited coordinate identifies
exactly one row, and that **one** resolution costs 64.7 ms as an index scan
on `ix_observations_scenario_run_id` removing 38,424 rows by filter. What it
could not know was how many resolutions a bundle needs, because the evidence
list did not exist yet. 64.7 ms is nothing for a bundle citing four
observations and is half a minute for one citing five hundred.

Two things are measured here, and the second is the one that decides:

1. The **ref-count distribution** over real bundles -- per bundle, and per
   evidence item, split by the two coordinate shapes.
2. **Per-ref resolution against batched resolution.** A resolver issuing one
   query per ref pays the 38,424-row filter once per ref; a resolver issuing
   one query per coordinate shape per bundle pays it once. If batching
   collapses the cost, the composite index buys a constant factor on top of
   an already-acceptable number and can stay deferred; if it does not, the
   index is owed before this item ships.

No aircraft identifier is printed -- counts and timings only, per
`measurements/README.md`.
"""
from __future__ import annotations

import os
import statistics
import time
from collections import Counter
from datetime import timedelta

import _corpus
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, RfPayload, SourceType, TrackPayload,
                            ValidationStatus)
from app.db.findings import save_findings
from app.detection.baseline import RfMetric, compute_rf_baselines
from app.detection.bundle import build_bundles
from app.detection.findings import from_track_gap
from app.detection.fusion import (FusionPolicy, claims_from_interference,
                                  detect_interference)
from app.detection.precedence import PrecedencePolicy, claims_from_sensor_faults, resolve
from app.detection.rf_noise import Direction, ThresholdPolicy, detect_rf_noise
from app.detection.sensor_fault import FaultPolicy, detect_sensor_faults
from app.detection.track_gap import BoundingBox, GapPolicy, detect_track_gaps
from app.scenario.layout import load_layout

RF_POLICY = ThresholdPolicy(metric=RfMetric.POWER_DBM, direction=Direction.ABOVE,
                            threshold=6.0, medium_at=10.0, high_at=15.0)
FAULT, FUSION, LADDER = FaultPolicy(), FusionPolicy(), PrecedencePolicy()
BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)
GAP = GapPolicy(threshold=timedelta(seconds=100),
                contact_fresh_within=timedelta(seconds=30), box=BOX)

#: Enough runs of each staged arm to see both bundle kinds and the spread.
#: The whole corpus is not needed: this measures a shape, not a rate.
PER_ARM = int(os.environ.get("PER_ARM", "8"))

print(_corpus.describe(), flush=True)

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)
layout = load_layout()


def obs_for(run_id, kind):
    with factory.begin() as s:
        rows = s.execute(text(
            "SELECT timestamp, ST_Y(location) AS lat, ST_X(location) AS lon, payload "
            "FROM observations WHERE scenario_run_id=:r AND observation_type=:t "
            "ORDER BY timestamp"), {"r": run_id, "t": kind}).mappings().all()
    src = SourceType.OPENSKY if kind == "track" else SourceType.SYNTHETIC_RF
    mode = DataMode.REPLAYED if kind == "track" else DataMode.SYNTHETIC
    pl = TrackPayload if kind == "track" else RfPayload
    ot = ObservationType.TRACK if kind == "track" else ObservationType.RF
    return [CanonicalObservation(
        source_id="o", source_type=src, observation_type=ot, timestamp=r["timestamp"],
        location=Location(lat=r["lat"], lon=r["lon"]), data_mode=mode,
        validation_status=ValidationStatus.VALID,
        provenance=Provenance(source_id="o", source_type=src, data_mode=mode,
                              scenario_run_id=run_id),
        payload=pl(**r["payload"])) for r in rows]


# ------------------------------------------------------------ the two resolvers

def resolve_one_by_one(run_id: int, refs: list[dict]) -> tuple[int, Counter]:
    """One query per ref -- what the naive resolver costs.

    Returns how many resolved, and a tally of what the misses were, keyed by
    coordinate shape and finding shape rather than by identifier:
    `measurements/README.md` forbids an aircraft identifier reaching a
    committed log.
    """
    found = 0
    missed: Counter = Counter()
    with factory.begin() as s:
        for ref in refs:
            if "sensor_id" in ref:
                row = s.execute(text(
                    "SELECT id FROM observations WHERE scenario_run_id=:r "
                    "AND observation_type='rf' "
                    "AND payload->>'sensor_id'=:sid "
                    "AND (payload->>'channel_index')::int=:ch "
                    "AND timestamp = CAST(:ts AS timestamptz)"),
                    {"r": run_id, "sid": ref["sensor_id"],
                     "ch": ref["channel_index"], "ts": ref["timestamp"]}).all()
            else:
                row = s.execute(text(
                    "SELECT id FROM observations WHERE scenario_run_id=:r "
                    "AND observation_type='track' "
                    "AND payload->>'aircraft_id'=:aid "
                    "AND timestamp = CAST(:ts AS timestamptz)"),
                    {"r": run_id, "aid": ref["aircraft_id"], "ts": ref["at"]}).all()
            found += len(row)
            if len(row) != 1:
                kind = "rf" if "sensor_id" in ref else "track"
                missed[(kind, ref.get("shape", "?"), len(row))] += 1
    return found, missed


def resolve_batched(run_id: int, refs: list[dict]) -> int:
    """One query per coordinate shape -- the whole bundle at once."""
    rf = [r for r in refs if "sensor_id" in r]
    track = [r for r in refs if "aircraft_id" in r]
    found = 0
    with factory.begin() as s:
        if rf:
            values = ", ".join(f"(:s{i}, :c{i}, CAST(:t{i} AS timestamptz))"
                               for i in range(len(rf)))
            params = {"r": run_id}
            for i, ref in enumerate(rf):
                params[f"s{i}"] = ref["sensor_id"]
                params[f"c{i}"] = ref["channel_index"]
                params[f"t{i}"] = ref["timestamp"]
            found += len(s.execute(text(
                "SELECT id FROM observations WHERE scenario_run_id=:r "
                "AND observation_type='rf' AND ("
                "  payload->>'sensor_id', (payload->>'channel_index')::int, timestamp"
                f") IN ({values})"), params).all())
        if track:
            values = ", ".join(f"(:a{i}, CAST(:t{i} AS timestamptz))"
                               for i in range(len(track)))
            params = {"r": run_id}
            for i, ref in enumerate(track):
                params[f"a{i}"] = ref["aircraft_id"]
                params[f"t{i}"] = ref["at"]
            found += len(s.execute(text(
                "SELECT id FROM observations WHERE scenario_run_id=:r "
                "AND observation_type='track' AND ("
                "  payload->>'aircraft_id', timestamp"
                f") IN ({values})"), params).all())
    return found


# --------------------------------------------------------------------- baseline

with factory.begin() as _s:
    quiet = _corpus.quiet_runs(_s)
print(f"baseline from {len(quiet)} quiet runs of this corpus", flush=True)
table = compute_rf_baselines([o for q in quiet for o in obs_for(q, "rf")],
                             RfMetric.POWER_DBM, baseline_run_ids=quiet,
                             window=timedelta(hours=2))

with factory.begin() as s:
    runs = s.execute(text(
        f"SELECT id, scenario_type FROM scenario_runs "
        f"WHERE {_corpus.run_filter()} ORDER BY id")).mappings().all()

picked, seen = [], Counter()
for run in runs:
    if seen[run["scenario_type"]] < PER_ARM:
        seen[run["scenario_type"]] += 1
        picked.append((run["id"], run["scenario_type"]))

print(f"{len(picked)} runs sampled, {PER_ARM} per arm\n", flush=True)

# ------------------------------------------------------------------ measurement

unresolved: Counter = Counter()
per_bundle_refs: list[int] = []
per_item_refs: list[int] = []
shape = Counter()
items_with_refs = Counter()
by_type: dict[str, list[int]] = {}
one_by_one_ms: list[float] = []
batched_ms: list[float] = []
resolved_all = True

for run_id, kind in picked:
    rf = obs_for(run_id, "rf")
    span = (min(o.timestamp for o in rf), max(o.timestamp for o in rf))
    found = detect_rf_noise(rf, table, RF_POLICY)
    faults = detect_sensor_faults(found, rf, table, layout, FAULT)

    tracks = obs_for(run_id, "track")
    gaps = [from_track_gap(g, scenario_run_id=run_id)
            for g in detect_track_gaps(tracks, GAP)]
    save_findings(factory, scenario_run_id=run_id, rule_id="TRACK-GAP", findings=gaps)

    zones = detect_interference(faults, factory, scenario_run_id=run_id,
                                run_span=span, layout=layout, policy=FUSION)
    claims = [*claims_from_sensor_faults(faults, layout),
              *claims_from_interference(zones)]
    result = resolve(claims, layout, LADDER)

    bundles = build_bundles(result, scenario_run_id=run_id, faults=faults.faults,
                            zones=zones.zones, rf=found, track_findings=gaps)

    for bundle in bundles:
        # The finding's shape travels with the ref for attribution only, and
        # is ignored by both resolvers.
        refs = []
        for item in bundle.evidence:
            for ref in item.refs:
                tagged = dict(ref)
                tagged["shape"] = item.details.get("shape", item.finding_type)
                refs.append(tagged)
        per_bundle_refs.append(len(refs))
        by_type.setdefault(bundle.anomaly_type, []).append(len(refs))
        for item in bundle.evidence:
            per_item_refs.append(len(item.refs))
            items_with_refs["with refs" if item.refs else "no refs"] += 1
            for ref in item.refs:
                shape["rf" if "sensor_id" in ref else "track"] += 1

        if not refs:
            continue
        t0 = time.perf_counter()
        n1, missed = resolve_one_by_one(run_id, refs)
        unresolved.update(missed)
        one_by_one_ms.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        n2 = resolve_batched(run_id, refs)
        batched_ms.append((time.perf_counter() - t0) * 1000)
        if n1 != len(refs) or n2 != len(refs):
            resolved_all = False


def summarise(label: str, values: list[int | float], unit: str = "") -> None:
    if not values:
        print(f"  {label:34} (none)")
        return
    ordered = sorted(values)
    print(f"  {label:34} n={len(values):4d}  min={ordered[0]:8.1f}{unit}  "
          f"median={statistics.median(ordered):8.1f}{unit}  "
          f"max={ordered[-1]:8.1f}{unit}")


print("=" * 78)
print("HOW MANY OBSERVATIONS A BUNDLE CITES")
print("=" * 78)
print(f"  bundles built: {len(per_bundle_refs)}")
summarise("refs per bundle", per_bundle_refs)
summarise("refs per evidence item", per_item_refs)
print(f"  evidence items by whether they cite anything: {dict(items_with_refs)}")
print(f"  refs by coordinate shape: {dict(shape)}")
for anomaly_type in sorted(by_type):
    summarise(f"refs per {anomaly_type}", by_type[anomaly_type])

print()
print("=" * 78)
print("WHAT RESOLVING ONE BUNDLE COSTS")
print("=" * 78)
summarise("one query per ref", one_by_one_ms, " ms")
summarise("one query per coordinate shape", batched_ms, " ms")
if one_by_one_ms and batched_ms:
    print(f"  batching is {statistics.median(one_by_one_ms) / max(statistics.median(batched_ms), 1e-9):.1f}x "
          f"faster at the median")
print(f"  every cited coordinate resolved: {resolved_all}")

print()
print("=" * 78)
print("WHAT DID NOT RESOLVE")
print("=" * 78)
if not unresolved:
    print("  nothing -- every cited coordinate identified exactly one row")
else:
    print(f"  {'coordinate':10} {'finding shape':22} {'rows matched':>13} {'count':>7}")
    for key in sorted(unresolved):
        print(f"  {key[0]:10} {key[1]:22} {key[2]:13d} {unresolved[key]:7d}")
