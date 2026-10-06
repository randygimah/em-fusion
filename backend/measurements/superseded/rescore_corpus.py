"""Examine every stored run with the detection pass. Spec: anom-016.

**Superseded by `anom-017`'s `corpus/rescore_baseline.py`.** This baselines over
`_corpus.quiet_runs` -- sixty runs -- and rewrites every stamp, which is how the
store came to hold findings under two baselines. Kept with its log as the record of
the 3 October re-score; moved here so nothing runs it by accident.

**This writes to the application's database**, which makes it the odd one out in
this directory. Everything else here measures and prints; this one replaces the
findings of every completed run and stamps each one with when it was examined and
under what settings. It is the command `anom-016` deliberately did *not* make into
behaviour: a stage that decided on its own to re-examine three hundred hours would
rewrite the findings behind every quoted figure under whatever settings happened to
be current, so it is run by name, once, by somebody who means it.

Why it is needed at all. `anom-016` fires the pass when a batch **completes**, so
it reaches new batches only. Every run already in the store was examined by
`detection_metrics.py` before anything recorded that examinations happen, so each
one has findings and no stamp -- and `api-012` reads the absence of a stamp as *not
known to have been examined*, which is the correct reading and is also why the
screen shows nothing for them.

**One baseline, and it is the corpus of record's.** `app/db/repository.py`'s
`quiet_run_ids` returns every completed quiet run in the store, which is the right
answer for the application: it should use all the quiet hours it has. It is the
wrong answer *here*, because the figures of record were measured over corpus v2's
sixty quiet runs alone, and a re-score under a wider baseline would stamp those
runs with provenance no quoted figure was taken under. So the baseline comes from
`_corpus.quiet_runs`, and the stamp records exactly which runs it was measured over
-- which is what `Normality` carries that list for.

That difference is worth stating rather than smoothing over: a batch generated from
the screen today is baselined over every quiet hour in the store, and the corpus
was baselined over sixty. Both are honest, both are recorded on the run, and the
stamp is what makes them tellable apart.

**Every completed run, not only the corpus.** The store holds three batches, and
the one the screen serves is the most recent -- so scoring the corpus alone leaves
the screen exactly as it was. Scoring them all also means every run carries the
same settings and the same baseline, which is the only state in which two runs'
findings can be compared at all.

Findings are **replaced** per run per rule (`db-008`), so this is idempotent and
re-running it is the whole of the repair if it dies part way. It does not touch
`evidence_bundles`: the pass builds bundles and does not store them, on
`eval-004`'s argument that its pre-registered sample names twenty of them by id.

No identifier of any kind is printed, per the two standing constraints in
`measurements/README.md` -- a finding's subject is a sensor id or an aircraft id,
so only counts go to the log.

Run:  make measure SCRIPT=corpus/rescore_corpus.py
"""
from __future__ import annotations

import os
import time
from collections import Counter

import _corpus
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.dal.models import ScenarioRunSummary
from app.detection.chain import ChainError, assess, measure_normality
from app.detection.settings import BASELINE_WINDOW, POLICIES_OF_RECORD
from app.scenario.layout import load_layout

url = make_url(os.environ["DATABASE_URL"])
print(f"target: {url.host}:{url.port}/{url.database} as {url.username}", flush=True)
print(_corpus.describe(), flush=True)

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)
layout = load_layout()

with factory.begin() as session:
    quiet = _corpus.quiet_runs(session)
    rows = (
        session.execute(
            text(
                "SELECT id, scenario_type, seed, started_at, completed_at "
                "FROM scenario_runs WHERE completed_at IS NOT NULL ORDER BY id"
            )
        )
        .mappings()
        .all()
    )
    before = session.execute(
        text("SELECT count(detection_pass_at) FROM scenario_runs")
    ).scalar_one()

print(
    f"{len(rows)} completed runs to examine, {before} already stamped; "
    f"baseline over {len(quiet)} quiet runs of the corpus of record",
    flush=True,
)

started = time.monotonic()
NORMALITY = measure_normality(
    factory, quiet_run_ids=tuple(quiet), policies=POLICIES_OF_RECORD,
    window=BASELINE_WINDOW,
)
baseline_seconds = time.monotonic() - started
print(f"baseline measured in {baseline_seconds:.1f} s", flush=True)

#: A failure is recorded and stepped over, which is `scn-003`'s posture and
#: `anom-016`'s: a pass that died on run 14 of 380 would have spent the time and
#: kept the stamp off every run after it.
refused: list[tuple[int, str]] = []
broke: list[tuple[int, str]] = []
claims: Counter[str] = Counter()
scored = 0

for row in rows:
    run = ScenarioRunSummary(
        id=row["id"],
        scenario_type=row["scenario_type"],
        seed=row["seed"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
    )
    try:
        assessment = assess(
            run,
            normality=NORMALITY,
            policies=POLICIES_OF_RECORD,
            layout=layout,
            session_factory=factory,
        )
    except ChainError as refusal:
        refused.append((run.id, str(refusal).split(":")[0]))
    except Exception as defect:  # noqa: BLE001 -- recorded and stepped over
        broke.append((run.id, f"{type(defect).__name__}: {defect}"))
    else:
        scored += 1
        for claim in assessment.reported:
            claims[claim.anomaly_type] += 1
    done = scored + len(refused) + len(broke)
    if done % 25 == 0:
        rate = (time.monotonic() - started) / done
        print(
            f"  {done}/{len(rows)} examined, {rate:.2f} s a run, "
            f"{(len(rows) - done) * rate / 60:.1f} min left",
            flush=True,
        )

elapsed = time.monotonic() - started

with factory.begin() as session:
    after = session.execute(
        text("SELECT count(detection_pass_at) FROM scenario_runs")
    ).scalar_one()
    unstamped = session.execute(
        text(
            "SELECT count(*) FROM scenario_runs "
            "WHERE completed_at IS NOT NULL AND detection_pass_at IS NULL"
        )
    ).scalar_one()
    policies_recorded = session.execute(
        text(
            "SELECT count(DISTINCT detection_policy) FROM scenario_runs "
            "WHERE detection_policy IS NOT NULL"
        )
    ).scalar_one()

print(
    f"\n{scored} examined of {len(rows)} completed runs in {elapsed / 60:.1f} min "
    f"({elapsed / max(len(rows), 1):.2f} s a run)",
    flush=True,
)
print(f"stamped: {before} before, {after} after; {unstamped} completed runs unstamped")
print(f"distinct settings recorded across the store: {policies_recorded}")
print("\nreported claims by type, over every examined run:")
for anomaly_type, count in sorted(claims.items()):
    print(f"  {anomaly_type:34} {count}")
if refused:
    print(f"\nrefused ({len(refused)}) -- the pass declined these:")
    for run_id, why in refused:
        print(f"  run {run_id}: {why}")
if broke:
    print(f"\nFAILED ({len(broke)}) -- each one is a defect, not a refusal:")
    for run_id, why in broke:
        print(f"  run {run_id}: {why}")
print(f"\nEXIT={1 if broke else 0}")
raise SystemExit(1 if broke else 0)
