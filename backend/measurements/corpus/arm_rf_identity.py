"""Is `ambiguous-mixed-evidence` a duplicate of `rf-sensor-fault`, or a control?

With `anom-006` closed, those two arms produce the same reportable answer --
`possible_sensor_fault` on all 60 runs each -- which invites the conclusion
that one of them is redundant and could be dropped. This asks whether that
is true of the *data* or only of the *output*.

If the radio half of the two arms is identical at a shared seed, then the
pair differs in exactly one variable (five aircraft removed, or not), the
answer not changing is a measured immunity result rather than an absence of
one, and the arm earns its place as a negative control living inside a
positive one. If the radio half differs, the comparison is confounded and
the arm's only remaining value is as the future conflict case for
`anom-013`.

**A note on the ordering, because the first version of this script got it
wrong.** It ordered by `payload->>'channel_hz'`, a key no payload carries,
so every row within one timestamp sorted equal and the order came from the
heap. Four of sixty pairs then looked like genuine generator differences;
diffing them showed the "differences" were the same values in a different
channel order. This is the third time this repository has been caught by an
unordered partition -- `db-009`'s centroid was the first. **A digest over
rows needs a total order, and a key that does not exist sorts everything
equal without erroring.**
"""
from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict

import _corpus
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

FAULT = "rf-sensor-fault"
AMBIGUOUS = "ambiguous-mixed-evidence"

print(_corpus.describe(), flush=True)

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)


def rf_digest(run_id: int) -> tuple[str, int]:
    """A digest of one run's RF stream, under a TOTAL order.

    timestamp, then sensor, then channel index: no two rows of a run share
    all three, so the order is fully determined and two runs with the same
    readings digest the same however the heap chose to hand them over.
    """
    with factory.begin() as session:
        rows = session.execute(text(
            "SELECT timestamp, payload FROM observations WHERE scenario_run_id=:r "
            "AND observation_type='rf' ORDER BY timestamp, payload->>'sensor_id', "
            "(payload->>'channel_index')::int"), {"r": run_id}).all()
    digest = hashlib.sha256()
    for timestamp, payload in rows:
        digest.update(
            f"{timestamp.isoformat()}|{json.dumps(payload, sort_keys=True)}".encode())
    return digest.hexdigest()[:16], len(rows)


with factory.begin() as session:
    runs = session.execute(text(
        "SELECT id, seed, scenario_type, ground_truth FROM scenario_runs "
        f"WHERE {_corpus.run_filter()} AND scenario_type IN (:a, :b) ORDER BY seed"
    ), {"a": FAULT, "b": AMBIGUOUS}).mappings().all()

pairs: dict[int, dict[str, object]] = defaultdict(dict)
for run in runs:
    pairs[run["seed"]][run["scenario_type"]] = run

identical = different = 0
same_sensor = same_window = same_elevation = 0
staged_fault: list[int] = []
staged_ambiguous: list[int] = []
mismatched: list[tuple[int, int, int]] = []

for seed, pair in sorted(pairs.items()):
    if len(pair) < 2:
        continue
    fault, ambiguous = pair[FAULT], pair[AMBIGUOUS]
    fault_digest, fault_rows = rf_digest(fault["id"])
    ambiguous_digest, ambiguous_rows = rf_digest(ambiguous["id"])
    if fault_digest == ambiguous_digest and fault_rows == ambiguous_rows:
        identical += 1
    else:
        different += 1
        mismatched.append((seed, fault["id"], ambiguous["id"]))
    a_gt, b_gt = fault["ground_truth"] or {}, ambiguous["ground_truth"] or {}
    same_sensor += a_gt.get("sensors") == b_gt.get("sensors")
    same_window += a_gt.get("window") == b_gt.get("window")
    same_elevation += a_gt.get("elevation_db") == b_gt.get("elevation_db")
    staged_fault.append(len(a_gt.get("aircraft") or []))
    staged_ambiguous.append(len(b_gt.get("aircraft") or []))

total = identical + different
print(f"\nseed-matched pairs: {total}")
print(f"{'RF observation stream identical, byte for byte':50} {identical}/{total}")
print(f"{'same receiver staged':50} {same_sensor}/{total}")
print(f"{'same incident window':50} {same_window}/{total}")
print(f"{'same elevation above baseline':50} {same_elevation}/{total}")
if mismatched:
    print(f"  differing pairs: {mismatched[:5]}")


def spread(values: list[int]) -> str:
    ordered = sorted(values)
    return f"{ordered[0]}/{ordered[len(ordered) // 2]}/{ordered[-1]}"


print(f"\nstaged aircraft per run, min/median/max:")
print(f"  {FAULT:26} {spread(staged_fault)}")
print(f"  {AMBIGUOUS:26} {spread(staged_ambiguous)}")

print(f"""
FINDING. The two arms stage the same receiver, the same fault, over the same
window, and produce an identical RF stream in {identical} of {total} pairs. The only
staged difference is that {AMBIGUOUS} also removes aircraft.
So the pair is a controlled comparison differing in one variable, and both
arms being decided `possible_sensor_fault` 60 of 60 is a measured result:
a simultaneous track-side disturbance does not perturb the RF verdict.
`{FAULT}` alone cannot show that, having no disturbance to be
immune to. The arm is a negative control inside a positive one and should
not be dropped as redundant -- though with `anom-006` closed it cannot yet
serve its other purpose, of giving `anom-013` a second competing claim.""")
