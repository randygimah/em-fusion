"""What every detector produces on a run with nothing staged. Spec: anom-008.

The control needs two different things from this corpus and they point in
opposite directions. The rules an analyst is shown must produce **nothing**
on a quiet run, which is the false-positive requirement `eval-002` rests on.
The rules underneath them must produce **something**, because the track side
reads replayed flight data which genuinely contains gaps, and a detector
reporting none of them has not looked.

Only the second is a measurement. The first is a requirement, so no band is
recorded for it -- a band on the reportable side would make a false positive
negotiable.

The band this produces is measured on the quiet runs of this corpus and is
then applied to them, so **it cannot fail on the data that produced it**. It
is a drift tripwire for a later corpus or a changed generator, which is what
`anom-008` states it is for, and not an independent test of the present
figures.

Run:  make measure SCRIPT=corpus/quiet_run_background.py
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import timedelta

import _corpus
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, RfPayload, SourceType, TrackPayload,
                            ValidationStatus)
from app.db.findings import save_findings
from app.detection.baseline import RfMetric, compute_rf_baselines
from app.detection.clustering import ClusterPolicy, cluster_track_gaps
from app.detection.findings import from_track_gap
from app.detection.fusion import FusionPolicy, claims_from_interference, detect_interference
from app.detection.precedence import PrecedencePolicy, claims_from_sensor_faults, resolve
from app.detection.rf_noise import Direction, ThresholdPolicy, detect_rf_noise
from app.detection.sensor_fault import FaultPolicy, detect_sensor_faults
from app.detection.track_gap import BoundingBox, GapPolicy, detect_track_gaps
from app.scenario.layout import load_layout

RF_POLICY = ThresholdPolicy(metric=RfMetric.POWER_DBM, direction=Direction.ABOVE,
                            threshold=6.0, medium_at=10.0, high_at=15.0)
FAULT, FUSION, LADDER, CLUSTER = (FaultPolicy(), FusionPolicy(), PrecedencePolicy(),
                                  ClusterPolicy())
BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)
GAP = GapPolicy(threshold=timedelta(seconds=100),
                contact_fresh_within=timedelta(seconds=30), box=BOX)

#: The producers the control registers, in the order it reports them. The
#: key is the (rule_id, finding_type) pair `ai-001` defines: `anom-012`
#: borrows `anom-010`'s rule id, so keyed on the rule alone a rate excess
#: and a continuity gap would be one row.
INTERMEDIATE = (
    ("RF-NOISE", "rf_noise_deviation"),
    ("TRACK-CLUSTER", "track_gap_cluster"),
    ("TRACK-GAP", "track_continuity_gap"),
    ("TRACK-GAP", "track_rate_excess"),
)
REPORTABLE = (
    ("FUSION-SPATIAL", "possible_interference_zone"),
    ("SENSOR-FAULT", "possible_sensor_fault"),
)

print(_corpus.describe())

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


with factory.begin() as _s:
    quiet = _corpus.quiet_runs(_s)
print(f"baseline and population are the same {len(quiet)} quiet runs", flush=True)

table = compute_rf_baselines([o for q in quiet for o in obs_for(q, "rf")],
                             RfMetric.POWER_DBM, baseline_run_ids=quiet,
                             window=timedelta(hours=2))

observed: dict[tuple[str, str], list[int]] = defaultdict(list)

for run_id in quiet:
    rf = obs_for(run_id, "rf")
    span = (min(o.timestamp for o in rf), max(o.timestamp for o in rf))
    found = detect_rf_noise(rf, table, RF_POLICY)
    faults = detect_sensor_faults(found, rf, table, layout, FAULT)

    tracks = obs_for(run_id, "track")
    gaps = detect_track_gaps(tracks, GAP)
    save_findings(factory, scenario_run_id=run_id, rule_id="TRACK-GAP",
                  findings=[from_track_gap(g, scenario_run_id=run_id) for g in gaps])
    clusters = cluster_track_gaps(factory, scenario_run_id=run_id, window=span,
                                  policy=CLUSTER)

    zones = detect_interference(faults, factory, scenario_run_id=run_id,
                                run_span=span, layout=layout, policy=FUSION)
    claims = [*claims_from_sensor_faults(faults, layout),
              *claims_from_interference(zones)]
    reported = resolve(claims, layout, LADDER).reported

    observed[("RF-NOISE", "rf_noise_deviation")].append(len(found.anomalies))
    observed[("TRACK-GAP", "track_continuity_gap")].append(len(gaps))
    observed[("TRACK-CLUSTER", "track_gap_cluster")].append(len(clusters))
    # Every event `anom-005` formed from an environmental dismissal is one
    # `anom-012` invocation. On a quiet run nothing upstream fires, so this
    # is expected to be zero -- structurally, not statistically.
    observed[("TRACK-GAP", "track_rate_excess")].append(
        len(zones.zones) + len(zones.declined))
    for key in REPORTABLE:
        observed[key].append(sum(1 for c in reported if c.anomaly_type == key[1]))

n = len(quiet)


def line(key):
    values = sorted(observed[key])
    mid = values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2
    zeros = sum(1 for v in values if v == 0)
    return (f"  {key[0]:<14} {key[1]:<24} {values[0]:>5} {mid:>8} {values[-1]:>6} "
            f"{zeros:>7}/{n}")


print(f"\nINTERMEDIATE PRODUCERS -- the measured background, per quiet run")
print(f"  {'rule':<14} {'finding type':<24} {'min':>5} {'median':>8} {'max':>6} "
      f"{'zeros':>7}")
for key in INTERMEDIATE:
    print(line(key))

print(f"\nREPORTABLE RULES -- the requirement, not a measurement")
print(f"  {'rule':<14} {'anomaly type':<24} {'min':>5} {'median':>8} {'max':>6} "
      f"{'zeros':>7}")
for key in REPORTABLE:
    print(line(key))
print("  SOURCE-GAP     possible_data_source_issue   -- no rule: anom-006 unbuilt")

print(f"\nBANDS FOR THE REGISTER (min..max over n={n})")
for key in INTERMEDIATE:
    values = observed[key]
    print(f"  {key}: Background(low={min(values)}, high={max(values)}, runs={n})")

floors = {k: min(observed[k]) for k in INTERMEDIATE}
print(f"\nWhich producers' silence fails, and which passes, from the measured floor:")
for key in INTERMEDIATE:
    verdict = "silence FAILS" if floors[key] > 0 else "silence passes"
    print(f"  {key[0]:<14} {key[1]:<24} floor {floors[key]:>3}  {verdict}")

bad = {k: observed[k] for k in REPORTABLE if any(v > 0 for v in observed[k])}
print(f"\nquiet runs showing the analyst anything: "
      f"{sum(1 for i in range(n) if any(observed[k][i] for k in REPORTABLE))} of {n}")
if bad:
    print(f"  NOT CLEAN: {bad}")
