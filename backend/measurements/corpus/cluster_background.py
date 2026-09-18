"""Does the quiet-run background ever cluster into something reportable?

The open question recorded when anom-010 landed. Runs the real TRACK-GAP
rule over real stored runs, stores the findings, and clusters them at a
range of radii -- quiet runs against staged ones.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.dal.models import CanonicalObservation, Location, Provenance, TrackPayload
from app.dal.models import DataMode, ObservationType, SourceType, ValidationStatus
from app.db.findings import cluster_findings, save_findings
from app.detection.findings import from_track_gap
from app.detection.track_gap import BoundingBox, GapPolicy, detect_track_gaps

BOX = BoundingBox(lat_min=49.0, lat_max=54.0, lon_min=3.0, lon_max=11.0)
POLICY = GapPolicy(
    threshold=timedelta(seconds=100),
    contact_fresh_within=timedelta(seconds=30),
    box=BOX,
)
RADII_KM = [5.0, 10.0, 20.0, 30.0, 45.0, 60.0]

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)


def matched_triples(limit: int) -> list[tuple[int, dict[str, int]]]:
    """Seed-matched sets, so the control replays the same corpus window.

    `rf-sensor-fault` stages nothing on the track side -- only coverage-gap,
    gnss-degradation and ambiguous-mixed-evidence perturb tracks -- so its
    track findings ARE that window's quiet background. `normal-baseline`
    shares a seed with nothing in this batch, which makes it a control
    matched on nothing but the generator.
    """
    with factory.begin() as s:
        rows = s.execute(
            text(
                "SELECT seed, scenario_type, min(id) AS id FROM scenario_runs "
                "WHERE scenario_type IN "
                "  ('rf-sensor-fault','gnss-degradation','aircraft-coverage-gap') "
                "GROUP BY seed, scenario_type"
            )
        ).all()
    by_seed: dict[int, dict[str, int]] = {}
    for seed, scenario, run_id in rows:
        by_seed.setdefault(seed, {})[scenario] = run_id
    full = [(s, m) for s, m in sorted(by_seed.items()) if len(m) == 3]
    return full[:limit]


def observations_for(run_id: int) -> list[CanonicalObservation]:
    with factory.begin() as s:
        rows = (
            s.execute(
                text(
                    "SELECT timestamp, ST_Y(location) AS lat, ST_X(location) AS lon, payload "
                    "FROM observations WHERE scenario_run_id = :r "
                    "AND observation_type = 'track' ORDER BY timestamp"
                ),
                {"r": run_id},
            )
            .mappings()
            .all()
        )
    out = []
    for row in rows:
        p = row["payload"]
        out.append(
            CanonicalObservation(
                source_id="opensky-replay",
                source_type=SourceType.OPENSKY,
                observation_type=ObservationType.TRACK,
                timestamp=row["timestamp"],
                location=Location(lat=row["lat"], lon=row["lon"]),
                data_mode=DataMode.REPLAYED,
                validation_status=ValidationStatus.VALID,
                provenance=Provenance(
                    source_id="opensky-replay",
                    source_type=SourceType.OPENSKY,
                    data_mode=DataMode.REPLAYED,
                    scenario_run_id=run_id,
                ),
                payload=TrackPayload(**p),
            )
        )
    return out


def window_for(obs: list[CanonicalObservation]) -> tuple[datetime, datetime]:
    ts = [o.timestamp for o in obs]
    return (min(ts) - timedelta(seconds=1), max(ts) + timedelta(seconds=1))


CONTROL = "rf-sensor-fault"
STAGED = ("gnss-degradation", "aircraft-coverage-gap")
LABEL = {"rf-sensor-fault": "control (tracks untouched)",
         "gnss-degradation": "gnss-degradation",
         "aircraft-coverage-gap": "aircraft-coverage-gap"}


def measure(run_id: int) -> tuple[int, dict[float, tuple[int, int, int]]]:
    obs = observations_for(run_id)
    gaps = detect_track_gaps(obs, POLICY)
    findings = [from_track_gap(g, scenario_run_id=run_id) for g in gaps]
    save_findings(factory, scenario_run_id=run_id, rule_id="TRACK-GAP", findings=findings)
    window = window_for(obs)
    out = {}
    for r in RADII_KM:
        groups = cluster_findings(
            factory, scenario_run_id=run_id, rule_id="TRACK-GAP",
            radius_km=r, window=window,
        )
        out[r] = (
            len(groups),
            max((g.size for g in groups), default=0),
            sum(1 for g in groups if g.size >= 3),
        )
    return len(findings), out


triples = matched_triples(8)
print(f"{len(triples)} seed-matched triples; each row is groups/largest/3-plus\n")
hdr = f"{'seed':>11}  {'scenario':26} {'found':>6} " + " ".join(f"r={r:g}".rjust(9) for r in RADII_KM)
print(hdr)
print("-" * len(hdr))

agg: dict[str, dict[float, list[tuple[int, int, int]]]] = {
    k: {r: [] for r in RADII_KM} for k in LABEL
}
found_agg: dict[str, list[int]] = {k: [] for k in LABEL}

for seed, runs in triples:
    for scenario in (CONTROL, *STAGED):
        n, res = measure(runs[scenario])
        found_agg[scenario].append(n)
        cells = []
        for r in RADII_KM:
            agg[scenario][r].append(res[r])
            g, b, m = res[r]
            cells.append(f"{g}/{b}/{m}".rjust(9))
        print(f"{seed:>11}  {LABEL[scenario]:26} {n:>6} " + " ".join(cells))
    print()

print("\n=== means over the 8 matched triples: groups / largest group / groups of 3+ ===")
hdr2 = f"{'scenario':28} {'found':>6} " + " ".join(f"r={r:g}km".rjust(19) for r in RADII_KM)
print(hdr2)
for scenario in (CONTROL, *STAGED):
    cells = []
    for r in RADII_KM:
        rows = agg[scenario][r]
        g = sum(x[0] for x in rows) / len(rows)
        b = sum(x[1] for x in rows) / len(rows)
        m = sum(x[2] for x in rows) / len(rows)
        cells.append(f"{g:5.2f} /{b:5.2f} /{m:5.2f}".rjust(19))
    avg = sum(found_agg[scenario]) / len(found_agg[scenario])
    print(f"{LABEL[scenario]:28} {avg:6.2f} " + " ".join(cells))

print("\n=== staged minus control, per matched triple (largest group) ===")
for scenario in STAGED:
    line = []
    for r in RADII_KM:
        diffs = [s[1] - c[1] for s, c in zip(agg[scenario][r], agg[CONTROL][r])]
        wins = sum(1 for d in diffs if d > 0)
        line.append(f"{sum(diffs)/len(diffs):+5.2f} ({wins}/8)".rjust(19))
    print(f"{LABEL[scenario]:28} {'':>6} " + " ".join(line))
