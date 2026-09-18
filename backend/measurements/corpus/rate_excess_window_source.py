"""Does anom-012's measured curve describe what anom-012 will actually be given?

The curve that the radius would be chosen from -- 16 of 40 at 30 km, 23 at
45, 31 at 60 -- was measured with the centre and the window taken from
ground truth. In production both come from a detected RF episode, per
api-009. anom-007 established this week that an anom-001 episode is not the
incident: the injected elevation dips below the threshold about one tick in
six, so one 300 s incident arrives as a median of six episodes of about
20 s each.

If the detected window is 20 s where the measurement assumed 300 s, the
window is a fifteenth of what was measured and its complement is nearly the
whole run. The curve would then describe a measurement that never occurs.

This measures all three inputs side by side on the replication batches:
  truth      -- ground-truth centre and window, as the curve was measured
  episode    -- the raw anom-001 episode, which is what api-009 would give
                a rule reading anom-001 directly
  assessed   -- anom-007's window, which is seeded by the episode and
                bounded by the readings, and its sensor as the centre
"""
from __future__ import annotations

import os
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import _corpus
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, RfPayload, SourceType, TrackPayload,
                            ValidationStatus)
from app.db.findings import save_findings
from app.detection.baseline import RfMetric, compute_rf_baselines
from app.detection.findings import from_track_gap
from app.detection.rate_excess import ExcessPolicy, measure_rate_excess
from app.detection.rf_noise import Direction, ThresholdPolicy, detect_rf_noise
from app.detection.sensor_fault import FaultPolicy, Verdict, detect_sensor_faults
from app.detection.track_gap import BoundingBox, GapPolicy, detect_track_gaps
from app.scenario.layout import great_circle_km, load_layout

RF_POLICY = ThresholdPolicy(metric=RfMetric.POWER_DBM, direction=Direction.ABOVE,
                            threshold=6.0, medium_at=10.0, high_at=15.0)
FAULT = FaultPolicy()
BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)
GAP = GapPolicy(threshold=timedelta(seconds=100),
                contact_fresh_within=timedelta(seconds=30), box=BOX)
RADII = [30.0, 45.0, 60.0]
#: The thresholds batch 2 chose, which batch 3 was scored at out of sample.
THRESHOLD = {30.0: 1.79, 45.0: 1.79, 60.0: 1.58}

print(_corpus.describe())

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)
layout = load_layout()
POS = {s.sensor_id: (s.lat, s.lon) for s in layout.sensors}


def obs_for(run_id, kind):
    with factory.begin() as s:
        rows = s.execute(text(
            "SELECT timestamp, ST_Y(location) AS lat, ST_X(location) AS lon, payload "
            "FROM observations WHERE scenario_run_id=:r AND observation_type=:t "
            "ORDER BY timestamp"), {"r": run_id, "t": kind}).mappings().all()
    src = SourceType.OPENSKY if kind == "track" else SourceType.SYNTHETIC_RF
    mode = DataMode.REPLAYED if kind == "track" else DataMode.SYNTHETIC
    payload = TrackPayload if kind == "track" else RfPayload
    otype = ObservationType.TRACK if kind == "track" else ObservationType.RF
    return [CanonicalObservation(
        source_id="o", source_type=src, observation_type=otype,
        timestamp=r["timestamp"], location=Location(lat=r["lat"], lon=r["lon"]),
        data_mode=mode, validation_status=ValidationStatus.VALID,
        provenance=Provenance(source_id="o", source_type=src, data_mode=mode,
                              scenario_run_id=run_id),
        payload=payload(**r["payload"])) for r in rows]


with factory.begin() as _s:
    quiet = _corpus.quiet_runs(_s)
print(f"baseline from {len(quiet)} quiet runs of this corpus", flush=True)
table = compute_rf_baselines(obs_for_quiet := [o for q in quiet for o in obs_for(q, "rf")],
                             RfMetric.POWER_DBM, baseline_run_ids=quiet,
                             window=timedelta(hours=2))
print(f"baseline over {len(table.baselines)} cells", flush=True)

with factory.begin() as s:
    runs = s.execute(text(
        "SELECT id, seed, scenario_type, ground_truth FROM scenario_runs "
        f"WHERE {_corpus.run_filter()} ORDER BY id")).mappings().all()

by_seed = defaultdict(dict)
for r in runs:
    by_seed[r["seed"]][r["scenario_type"]] = r

win_len = defaultdict(list)
centre_err = []
candidates = Counter()
unusable = Counter()
fires = {(src, rad): Counter() for src in ("truth", "episode", "assessed") for rad in RADII}
ratios = defaultdict(list)

for seed, pair in sorted(by_seed.items()):
    for kind, run in pair.items():
        run_id = run["id"]
        gt = run["ground_truth"] or {}
        sensors = gt.get("sensors") or []
        w = gt.get("window")
        staged_rf = bool(w and sensors)
        w0 = datetime.fromisoformat(w["start"]) if staged_rf else None
        w1 = datetime.fromisoformat(w["end"]) if staged_rf else None

        rf = obs_for(run_id, "rf")
        span = (min(o.timestamp for o in rf), max(o.timestamp for o in rf))
        found = detect_rf_noise(rf, table, RF_POLICY)
        assessed = detect_sensor_faults(found, rf, table, layout, FAULT)

        # What reaches fusion under anom-013: zones anom-007 did not claim.
        passed_on = [d for d in assessed.dismissed if d.verdict is Verdict.ENVIRONMENTAL]
        if passed_on:
            candidates[kind] += 1

        tracks = obs_for(run_id, "track")
        gaps = detect_track_gaps(tracks, GAP)
        save_findings(factory, scenario_run_id=run_id, rule_id="TRACK-GAP",
                      findings=[from_track_gap(g, scenario_run_id=run_id)
                                for g in gaps])

        sources = {}
        if staged_rf:
            sources["truth"] = (POS[sensors[0]], (w0, w1))
            win_len["truth"].append((w1 - w0).total_seconds())
        episodes = [a for a in found.anomalies if a.cell.sensor_id in POS]
        if episodes:
            e = max(episodes, key=lambda a: (a.ended_at - a.started_at))
            sources["episode"] = (POS[e.cell.sensor_id], (e.started_at, e.ended_at))
            win_len["episode"].append((e.ended_at - e.started_at).total_seconds())
        if passed_on:
            d = max(passed_on, key=lambda d: (d.ended_at - d.started_at))
            sources["assessed"] = (POS[d.sensor_id], (d.started_at, d.ended_at))
            win_len["assessed"].append((d.ended_at - d.started_at).total_seconds())
            if staged_rf:
                # Distance to the NEAREST staged receiver, not to sensors[0].
                # An interference incident is staged on two or three receivers
                # and any of them is a correct centre, so comparing against an
                # arbitrary member of the list measured receiver spacing rather
                # than error: the figures it produced (median 45.3 km, max
                # 107.5 km) are exactly this layout's minimum and median
                # separations. Zero here means the detected centre sits on a
                # receiver the answer key names, which is the actual question.
                centre_err.append(min(
                    great_circle_km(*POS[d.sensor_id], *POS[s]) for s in sensors
                ))

        for src, (centre, window) in sources.items():
            if window[1] >= span[1] or window[0] <= span[0]:
                window = (max(window[0], span[0] + timedelta(seconds=1)),
                          min(window[1], span[1] - timedelta(seconds=1)))
            if (window[1] - window[0]).total_seconds() <= 0:
                # A single-reading episode gives a zero-length window, which
                # anom-012 divides by. Counted, not clamped: the point of
                # this pass is to find out how often production input is
                # unusable, and clamping would hide it.
                unusable[src] += 1
                continue
            for rad in RADII:
                r = measure_rate_excess(
                    factory, scenario_run_id=run_id, centre=Location(lat=centre[0], lon=centre[1]),
                    policy=ExcessPolicy(radius_km=rad), window=window, run_span=span)
                ratios[(src, rad, kind)].append(r.ratio)
                if r.ratio >= THRESHOLD[rad]:
                    fires[(src, rad)][kind] += 1

print("\nwindow length, seconds (staged incident is 300):")
for src in ("truth", "episode", "assessed"):
    v = sorted(win_len[src])
    if v:
        print(f"  {src:9} n={len(v):3d} min={v[0]:5.0f} median={v[len(v)//2]:5.0f} max={v[-1]:5.0f}")

if centre_err:
    centre_err.sort()
    print(f"\ncentre error vs the staged centre, km: median="
          f"{centre_err[len(centre_err)//2]:.1f} max={centre_err[-1]:.1f}")

print(f"\nruns producing a fusion candidate at all: {dict(candidates)}")
print(f"windows unusable (zero length, divides by zero): {dict(unusable)}")

ARMS = ("gnss-degradation", "aircraft-coverage-gap", "rf-sensor-fault")
print(f"\n{'source':10} {'radius':>7}  " + "  ".join(f"{a[:14]:>16}" for a in ARMS))
for src in ("truth", "episode", "assessed"):
    for rad in RADII:
        c = fires[(src, rad)]
        cells = []
        for a in ARMS:
            n = len(ratios[(src, rad, a)])
            cells.append(f"{c[a]:>10}/{n:<5}" if n else f"{'-':>16}")
        print(f"{src:10} {rad:7.0f}  " + "  ".join(cells))
print("\n(counts are runs whose excess reached the pre-registered threshold;"
      " a dash means no run of that arm reached fusion at all)")
