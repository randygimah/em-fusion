"""Do evidence bundles actually work, on real hours, through the real modules?

Everything proving `evb-001` and `evb-002` so far is a unit test over
constructed input, plus one measurement that resolved citations with its
**own** inline SQL rather than the module that ships. Nothing in the
application calls the builder or the saver at all yet -- the AI layer that
will is unbuilt -- so until this script existed, the sentence "evidence
bundles work" rested on tests whose fixtures I wrote myself.

That is the same gap `ladder_end_to_end.py` filled for the ladder, and it
is worth remembering what that found: two defects that unit tests and a
mutation pass had both missed, because both were about what real data does
rather than about what the code says.

So this runs the **shipped** path end to end over stored hours: detect,
resolve the ladder, build bundles, save them through `app/db/bundles.py`,
read them back, and compare. Five things are then checked, and the last two
are the ones worth having:

1. Every arm produces the bundles it should, and the **quiet arms produce
   none at all** -- not one empty bundle. `anom-008` requires zero
   reportable anomalies and `evb-001` refuses an empty evidence list, and
   the way those two agree is that nothing is created.
2. Every citation in every bundle resolves, through the real resolver.
3. The round trip is exact: what comes back out of the database equals what
   went in, field for field.
4. **A negative control.** One citation in one real bundle is shifted by a
   single second and the save is expected to be refused. A traceability
   check that has never been seen to reject anything is a check nobody has
   tested -- and shifting by one second is the smallest lie available.
5. **One complete bundle, printed**, so the thing the AI layer will receive
   can be read rather than described.

Aircraft identifiers are redacted from everything printed here, per
`measurements/README.md`. They are already pseudonyms; the rule is that no
aircraft identifier of any kind reaches a committed log.
"""
from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import replace
from datetime import timedelta

import _corpus
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, RfPayload, SourceType, TrackPayload,
                            ValidationStatus)
from app.db.bundles import ResolutionError, bundles_for_run, save_bundles
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

#: Runs per arm. Defaults to the whole corpus; lower it for a quick pass.
PER_ARM = int(os.environ.get("PER_ARM", "60"))

#: Arms that must produce nothing. `aircraft-coverage-gap` is silent for a
#: different reason from `normal-baseline` -- its rule does not exist -- and
#: both are correct non-detections here.
SILENT_ARMS = {"normal-baseline", "aircraft-coverage-gap"}

AIRCRAFT_ID = re.compile(r"AC-[0-9a-fA-F]{6,}")


def redact(value: object) -> str:
    """Anything printed goes through here. No aircraft identifier, ever."""
    return AIRCRAFT_ID.sub("AC-<redacted>", str(value))


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


def bundles_of(run_id):
    """One run, all the way through the shipped path."""
    rf = obs_for(run_id, "rf")
    span = (min(o.timestamp for o in rf), max(o.timestamp for o in rf))
    found = detect_rf_noise(rf, RF_TABLE, RF_POLICY)
    faults = detect_sensor_faults(found, rf, RF_TABLE, layout, FAULT)

    gaps = [from_track_gap(g, scenario_run_id=run_id)
            for g in detect_track_gaps(obs_for(run_id, "track"), GAP)]
    save_findings(factory, scenario_run_id=run_id, rule_id="TRACK-GAP", findings=gaps)

    zones = detect_interference(faults, factory, scenario_run_id=run_id,
                                run_span=span, layout=layout, policy=FUSION)
    result = resolve([*claims_from_sensor_faults(faults, layout),
                      *claims_from_interference(zones)], layout, LADDER)
    return build_bundles(result, scenario_run_id=run_id, faults=faults.faults,
                         zones=zones.zones, rf=found, track_findings=gaps)


# --------------------------------------------------------------------- baseline

with factory.begin() as _s:
    quiet = _corpus.quiet_runs(_s)
print(f"baseline from {len(quiet)} quiet runs of this corpus", flush=True)
RF_TABLE = compute_rf_baselines([o for q in quiet for o in obs_for(q, "rf")],
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
print(f"{len(picked)} runs, up to {PER_ARM} per arm\n", flush=True)

# ------------------------------------------------------------------ the pass

runs_per_arm: Counter = Counter()
bundles_per_arm: Counter = Counter()
types_per_arm: dict[str, Counter] = {}
silent_runs: Counter = Counter()
citations = 0
distinct_rows: set[int] = set()
uncertainty_kinds: Counter = Counter()
grounding_kinds: Counter = Counter()
modes_per_type: dict[str, Counter] = {}
round_trip_exact = 0
round_trip_broken: list[int] = []
refusals: list[str] = []
specimen = None

for index, (run_id, kind) in enumerate(picked, start=1):
    runs_per_arm[kind] += 1
    built = bundles_of(run_id)
    if not built:
        silent_runs[kind] += 1

    try:
        saved = save_bundles(factory, scenario_run_id=run_id, bundles=built)
    except ResolutionError as refused:
        refusals.append(f"run {run_id} ({kind}): {redact(refused)}")
        continue

    read_back = bundles_for_run(factory, run_id)
    if list(read_back) == list(saved):
        round_trip_exact += 1
    else:
        round_trip_broken.append(run_id)

    bundles_per_arm[kind] += len(saved)
    for bundle in saved:
        types_per_arm.setdefault(kind, Counter())[bundle.anomaly_type] += 1
        modes_per_type.setdefault(bundle.anomaly_type, Counter())[
            " + ".join(sorted(m.value for m in bundle.data_modes))] += 1
        for uncertainty in bundle.known_uncertainties:
            uncertainty_kinds[uncertainty.kind.value] += 1
        for item in bundle.evidence:
            grounding_kinds[item.grounding.value] += 1
            citations += len(item.observation_ids)
            distinct_rows.update(item.observation_ids)
        if specimen is None and bundle.anomaly_type == "possible_interference_zone":
            specimen = (run_id, bundle)

    if index % 25 == 0:
        print(f"  {index}/{len(picked)} runs through the whole path", flush=True)

print()
print("=" * 78)
print("WHAT EACH ARM PRODUCED")
print("=" * 78)
print(f"  {'scenario':26} {'runs':>5} {'bundles':>8} {'silent runs':>12}  what they were")
for kind in sorted(runs_per_arm):
    what = dict(types_per_arm.get(kind, {})) or "-"
    print(f"  {kind:26} {runs_per_arm[kind]:5d} {bundles_per_arm[kind]:8d} "
          f"{silent_runs[kind]:12d}  {what}")

print()
print("  The two silent arms must produce ZERO bundles and not one empty bundle:")
for kind in sorted(SILENT_ARMS):
    ok = bundles_per_arm[kind] == 0 and silent_runs[kind] == runs_per_arm[kind]
    print(f"    {kind:26} {bundles_per_arm[kind]} bundles from "
          f"{runs_per_arm[kind]} runs   {'PASS' if ok else 'FAIL'}")

print()
print("=" * 78)
print("WHAT WAS CITED, AND WHETHER IT RESOLVED")
print("=" * 78)
total_bundles = sum(bundles_per_arm.values())
print(f"  bundles saved through the shipped resolver: {total_bundles}")
print(f"  evidence items by kind: {dict(grounding_kinds)}")
print(f"  citations resolved: {citations:,} to {len(distinct_rows):,} distinct rows")
print(f"  refused during the pass: {len(refusals)}")
for refusal in refusals[:5]:
    print(f"    {refusal}")
print(f"  round trip exact: {round_trip_exact} of {round_trip_exact + len(round_trip_broken)}"
      f" runs   {'PASS' if not round_trip_broken else 'FAIL ' + str(round_trip_broken[:5])}")

print()
print("  uncertainties carried, by kind:")
for name, count in sorted(uncertainty_kinds.items()):
    print(f"    {name:20} {count:6d}")
print("  data modes each kind of bundle spans:")
for anomaly_type in sorted(modes_per_type):
    print(f"    {anomaly_type:28} {dict(modes_per_type[anomaly_type])}")

# ------------------------------------------------- the negative control

print()
print("=" * 78)
print("NEGATIVE CONTROL -- one real citation moved by one second")
print("=" * 78)
if specimen is None:
    print("  no interference bundle in this sample; control not run")
else:
    run_id, bundle = specimen
    item_index = next(i for i, item in enumerate(bundle.evidence) if item.refs)
    item = bundle.evidence[item_index]
    ref = dict(item.refs[0])
    key = "timestamp" if "timestamp" in ref else "at"
    from datetime import datetime
    ref[key] = (datetime.fromisoformat(ref[key]) + timedelta(seconds=1)).isoformat()
    tampered = bundle.with_evidence([
        replace(item, refs=(ref, *item.refs[1:]), observation_ids=())
        if i == item_index else other
        for i, other in enumerate(bundle.evidence)
        for item in [other]
    ])
    print(f"  run {run_id}, one citation shifted from")
    print(f"    {redact(item.refs[0])}")
    print(f"  to")
    print(f"    {redact(ref)}")
    before = len(bundles_for_run(factory, run_id))
    try:
        save_bundles(factory, scenario_run_id=run_id, bundles=[tampered])
        print("  RESULT: accepted -- THE CHECK DOES NOT WORK")
    except ResolutionError as refused:
        print(f"  RESULT: refused. {redact(refused)}")
    after = len(bundles_for_run(factory, run_id))
    print(f"  bundles stored for this run before {before}, after {after}   "
          f"{'PASS -- nothing was disturbed' if before == after else 'FAIL'}")

# ------------------------------------------------------- one bundle, in full

print()
print("=" * 78)
print("ONE COMPLETE BUNDLE, AS THE AI LAYER WOULD RECEIVE IT")
print("=" * 78)
if specimen is not None:
    run_id, bundle = specimen
    print(f"  run {run_id}   {bundle.anomaly_type}   claimed by {bundle.rule_id}")
    print(f"  subject          {bundle.subject}")
    print(f"  window           {bundle.time_window[0]} .. {bundle.time_window[1]}")
    print(f"  area             {bundle.affected_area}")
    print(f"  channels         {bundle.affected_channels}")
    print(f"  data modes       {sorted(m.value for m in bundle.data_modes)}")
    print(f"  superseded       {len(bundle.superseded)}")
    print(f"\n  EVIDENCE ({len(bundle.evidence)} items)")
    for item in bundle.evidence:
        print(f"    [{item.grounding.value:8}] {item.source:22} {item.rule_id}"
              f" / {item.finding_type}")
        print(f"               {redact(item.finding)}")
        if item.observation_ids:
            shown = ", ".join(str(i) for i in item.observation_ids[:6])
            more = "" if len(item.observation_ids) <= 6 else \
                f" (+{len(item.observation_ids) - 6} more)"
            print(f"               cites rows {shown}{more}")
    print(f"\n  KNOWN UNCERTAINTIES ({len(bundle.known_uncertainties)})")
    for uncertainty in bundle.known_uncertainties:
        print(f"    [{uncertainty.kind.value:16}] {uncertainty.subject or '-'}")
        print(f"      {redact(uncertainty.statement)}")
