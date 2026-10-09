"""Do receivers' timelines agree with the picture's whole-hour state? Spec: api-018.

`api-018` promises that a receiver's worst interval through the hour is the
state the picture gives it for the whole hour, because both read one ladder.
The suite proves that on fixtures; this checks it on every hour the screen
offers, through the two builders the endpoints use, over the findings and
pass stamps in the store.

Reads only. Prints counts, never an aircraft or a receiver's findings.
"""

from __future__ import annotations

import os
import time
from collections import Counter

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.schemas.operational_picture import build_operational_picture
from app.api.v1.schemas.receiver_states import build_receiver_states
from app.db.findings import findings_for_run
from app.db.repository import detection_pass_for_run, run_summary, selectable_hours
from app.scenario.layout import load_layout

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)
layout = load_layout()
RANK = {"fault": 2, "deviating": 1}

hours = selectable_hours(factory)
agree = disagree = unexamined = both = intervals = 0
worst_states: Counter[str] = Counter()
per_receiver: Counter[int] = Counter()
started = time.perf_counter()
for hour in hours:
    run = run_summary(factory, hour.run_id)
    assert run is not None
    findings = findings_for_run(factory, run.id)
    stamp = detection_pass_for_run(factory, run.id)
    states = build_receiver_states(
        run=run, layout=layout, findings=findings, detection_pass=stamp
    )
    picture = build_operational_picture(
        run=run, observations=[], layout=layout, findings=findings, detection_pass=stamp
    )
    health = {sensor.id: sensor.health for sensor in picture.rfSensors}
    if not states.examined:
        unexamined += 1
        assert all(r.intervals is None for r in states.receivers)
        continue
    for timeline in states.receivers:
        assert timeline.intervals is not None
        intervals += len(timeline.intervals)
        per_receiver[len(timeline.intervals)] += 1
        served = {interval.state for interval in timeline.intervals}
        worst = max(served, key=RANK.__getitem__, default="nominal")
        worst_states[worst] += 1
        both += len(served) > 1
        if worst == health[timeline.id]:
            agree += 1
        else:
            disagree += 1
elapsed = time.perf_counter() - started

print(f"hours            {len(hours)} offered by the hours index")
print(f"unexamined       {unexamined}")
print(f"receiver-hours   {agree + disagree}")
print(f"  agree          {agree}")
print(f"  disagree       {disagree}")
print(f"worst state      {dict(sorted(worst_states.items()))}")
print(f"intervals        {intervals} in all")
print(f"  per receiver   {dict(sorted(per_receiver.items()))}")
print(f"  both states    {both} receiver-hours hold a fault and a deviation")
print(f"elapsed          {elapsed:.1f} s for both builders over every hour")
if disagree:
    raise SystemExit("a timeline's worst moment disagrees with the picture")
