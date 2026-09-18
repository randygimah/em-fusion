"""Two forms of route B, and how well each separates staged from control.

Form 1, the naive one: inside the disc, rate during the window over rate
outside it. Confounded -- the window sits mid-run, where detection is
easiest because a gap needs reports either side, so even control runs score
2.95.

Form 2, difference-in-differences: that same ratio, divided by the same
ratio computed over the REST of the box. The rest of the box shares the
temporal edge effect and not the incident, so dividing cancels it. Each run
remains its own control on both axes, place and time.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import (CanonicalObservation, DataMode, Location, ObservationType,
                            Provenance, SourceType, TrackPayload, ValidationStatus)
from app.detection.track_gap import BoundingBox, GapPolicy, detect_track_gaps
from app.scenario.layout import load_layout, great_circle_km

BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)
POLICY = GapPolicy(threshold=timedelta(seconds=100),
                   contact_fresh_within=timedelta(seconds=30), box=BOX)
engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)
POS = {s.sensor_id: (s.lat, s.lon) for s in load_layout().sensors}


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


def forms(run_id, centre, window, radius_km):
    obs = observations_for(run_id)
    if not obs:
        return None
    gaps = detect_track_gaps(obs, POLICY)
    ts = [o.timestamp for o in obs]
    during_s = (window[1] - window[0]).total_seconds()
    outside_s = (max(ts) - min(ts)).total_seconds() - during_s
    if during_s <= 0 or outside_s <= 0:
        return None

    def split(subset):
        d = sum(1 for g in subset if g.started_at < window[1] and g.ended_at > window[0])
        return d / during_s, (len(subset) - d) / outside_s

    inside = [g for g in gaps if great_circle_km(
        centre[0], centre[1], g.location.lat, g.location.lon) <= radius_km]
    elsewhere = [g for g in gaps if g not in inside]

    id_, io = split(inside)
    ed, eo = split(elsewhere)
    # Laplace smoothing on the rates, so a zero denominator is not a divide.
    eps = 1.0 / (during_s + outside_s)
    naive = (id_ + eps) / (io + eps)
    control_ratio = (ed + eps) / (eo + eps)
    return naive, naive / control_ratio if control_ratio else float("inf")


with factory.begin() as s:
    rows = s.execute(text(
        "SELECT seed, scenario_type, min(id) AS id, "
        "  (array_agg(ground_truth ORDER BY id))[1] AS gt FROM scenario_runs "
        "WHERE id BETWEEN :lo AND :hi AND scenario_type IN "
        "('rf-sensor-fault','gnss-degradation') GROUP BY seed, scenario_type"),
        {"lo": int(os.environ.get("RUN_LO", 1)), "hi": int(os.environ.get("RUN_HI", 999999))}
    ).mappings().all()
by_seed = {}
for r in rows:
    by_seed.setdefault(r["seed"], {})[r["scenario_type"]] = (r["id"], r["gt"])
pairs = [(s, m) for s, m in sorted(by_seed.items()) if len(m) == 2]


def separation(staged, control):
    """Best threshold, and what it costs. staged/control are score lists."""
    best = (0.0, None, 0, 0)
    for t in sorted(set(staged + control)):
        tp = sum(1 for x in staged if x >= t)
        fp = sum(1 for x in control if x >= t)
        youden = tp / len(staged) - fp / len(control)
        if youden > best[0]:
            best = (youden, t, tp, fp)
    return best


for radius in (30.0, 45.0, 60.0):
    naive_s, naive_c, did_s, did_c = [], [], [], []
    for seed, runs in pairs:
        gt = runs["rf-sensor-fault"][1]
        centre_id = (gt.get("sensors") or [None])[0]
        if centre_id not in POS:
            continue
        w = gt["window"]
        window = (datetime.fromisoformat(w["start"]), datetime.fromisoformat(w["end"]))
        a = forms(runs["gnss-degradation"][0], POS[centre_id], window, radius)
        b = forms(runs["rf-sensor-fault"][0], POS[centre_id], window, radius)
        if a is None or b is None:
            continue
        naive_s.append(a[0]); did_s.append(a[1])
        naive_c.append(b[0]); did_c.append(b[1])

    print(f"=== radius {radius:.0f} km, {len(naive_s)} matched pairs ===")
    # A threshold chosen on the batch it is scored against is fitted to it.
    # FIXED_T lets batch 3 be scored at the threshold batch 2 chose, which is
    # the only honest out-of-sample test available here.
    ft = os.environ.get(f"FIXED_T_{int(radius)}")
    if ft:
        t = float(ft)
        tp = sum(1 for x in naive_s if x >= t)
        fp = sum(1 for x in naive_c if x >= t)
        print(f"  form 1 at the threshold fixed by the other batch ({t:.2f}): "
              f"{tp}/{len(naive_s)} staged, {fp}/{len(naive_c)} controls  "
              f"(separation {tp/len(naive_s) - fp/len(naive_c):+.2f})")
    for name, sv, cv in (("form 1 (during vs outside)", naive_s, naive_c),
                         ("form 2 (difference-in-differences)", did_s, did_c)):
        y, t, tp, fp = separation(sv, cv)
        print(f"  {name:36} staged mean {sum(sv)/len(sv):6.2f}  "
              f"control mean {sum(cv)/len(cv):6.2f}")
        print(f"  {'':36} best threshold {t:6.2f} -> "
              f"{tp}/{len(sv)} staged caught, {fp}/{len(cv)} controls fired  "
              f"(separation {y:+.2f})")
        print(f"  {'':36} RAW {name.split()[1]} {radius:.0f} {tp} {len(sv)} {fp} {len(cv)}")
    print()
