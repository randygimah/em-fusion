"""Re-score every completed run under the pinned baseline. Spec: anom-017.

**This writes to the application's database.** It runs the shipped detection pass
over every completed run, replacing findings, storing bundles and moving each run's
examination stamp to today, under `BASELINE_QUIET_RUNS` -- the hundred quiet runs
`anom-017` pinned. Before it, the store held findings under two baselines (sixty
quiet runs on most of it, a hundred on the newest), which nothing on the screen or
in the results table could tell apart.

**A changed claim is the expected outcome and is recorded, not refused.** That is
the opposite of `evb-003`'s fill, which stopped on the first disagreement because
it was meant to reproduce the store exactly. This is meant to change it, so the
result is the list of runs whose reported claims moved, each with its claims
before and after. A log saying only *N runs changed* could not be read, which is
the item's own failure case.

**The twenty runs the scored campaign cites are refused, and the guard is left to
fire.** `db-011` forbids replacing a bundle a hypothesis cites, so on runs 102-175
the pass is refused before it writes its conclusions or its stamp. Those twenty
stay on the sixty-run baseline, where their claims, their bundles, their stamp and
the explanations scored against them all agree -- the one stated exception to a
consistent store, tellable apart by the stamp. They are not filtered out in
advance: a guard that is routed around is a guard nobody has seen work. Each one is
checked afterwards to confirm its claims and stamp did not move; one that did is a
defect and fails the run.

**Order is part of it**: the pin landed first, so the baseline here cannot be the
store's choice. `measure_normality` refuses if any pinned run is missing or holds
a different seed.

Run it:

    make measure SCRIPT=corpus/rescore_baseline.py                     # scope only
    make measure SCRIPT=corpus/rescore_baseline.py RESCORE_CONFIRM=yes  # and write

Dump the findings, bundles, runs and hypotheses tables first. Only reported claims
are printed, whose subject is a receiver id; no aircraft identifier of any kind
reaches this log, per `measurements/README.md`.
"""
from __future__ import annotations

import os
import sys
import time
from collections import Counter

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.bundles import CitedBundleError
from app.db.findings import findings_for_run
from app.db.repository import run_summary
from app.detection.chain import ChainError, assess, measure_normality
from app.detection.control import REGISTER, reportable_keys
from app.detection.findings import claim_identity
from app.detection.settings import (
    BASELINE_QUIET_RUNS,
    BASELINE_WINDOW,
    POLICIES_OF_RECORD,
)
from app.scenario.layout import load_layout

CONFIRM_VAR = "RESCORE_CONFIRM"
REPORTABLE = reportable_keys(REGISTER)


def confirmed() -> bool:
    return os.environ.get(CONFIRM_VAR, "").strip().lower() in {"yes", "1", "true"}


def stored_claims(factory: sessionmaker, run_id: int) -> list[tuple]:
    """The run's reported claims as stored, by `anom-015`'s own identity."""
    return sorted(
        claim_identity(f)
        for f in findings_for_run(factory, run_id)
        if (f.rule_id, f.finding_type) in REPORTABLE
    )


def stamp(factory: sessionmaker, run_id: int) -> tuple[object, object]:
    with factory.begin() as session:
        row = session.execute(
            text(
                "SELECT detection_pass_at, "
                "detection_policy->>'BASELINE.quiet_run_count' "
                "FROM scenario_runs WHERE id = :id"
            ),
            {"id": run_id},
        ).one()
    return row[0], row[1]


def show(claim: tuple) -> str:
    rule_id, finding_type, subject, started, ended = claim
    return (
        f"{rule_id} {finding_type} {subject} "
        f"{started:%H:%M:%S}-{ended:%H:%M:%S}"
    )


def main() -> int:
    url = make_url(os.environ["DATABASE_URL"])
    print("rescore_baseline.py -- anom-017")
    print(f"target: {url.host}:{url.port}/{url.database} as {url.username}")

    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    factory = sessionmaker(bind=engine, autoflush=False)

    with factory.begin() as session:
        ids = [
            row[0]
            for row in session.execute(
                text(
                    "SELECT id FROM scenario_runs "
                    "WHERE completed_at IS NOT NULL ORDER BY id"
                )
            ).all()
        ]
        cited = [
            row[0]
            for row in session.execute(
                text(
                    "SELECT DISTINCT b.scenario_run_id FROM hypotheses h "
                    "JOIN evidence_bundles b ON b.id = h.bundle_id ORDER BY 1"
                )
            ).all()
        ]
        baselines = session.execute(
            text(
                "SELECT detection_policy->>'BASELINE.quiet_run_count', count(*) "
                "FROM scenario_runs WHERE completed_at IS NOT NULL "
                "GROUP BY 1 ORDER BY 1"
            )
        ).all()

    print(f"completed runs           : {len(ids)} ({ids[0]}-{ids[-1]})")
    print(f"cited by hypotheses      : {len(cited)} {cited}")
    print("baselines on the stamps  : " + ", ".join(f"{n} quiet runs on {c}" for n, c in baselines))
    print(f"pinned baseline          : {len(BASELINE_QUIET_RUNS)} quiet runs\n")

    if not confirmed():
        print(
            f"This WRITES to the store. Set {CONFIRM_VAR}=yes to run it, after\n"
            "dumping the findings, bundles, runs and hypotheses tables."
        )
        return 1

    started = time.monotonic()
    normality = measure_normality(
        factory,
        quiet_runs=BASELINE_QUIET_RUNS,
        policies=POLICIES_OF_RECORD,
        window=BASELINE_WINDOW,
    )
    print(f"normality over {len(normality.quiet_run_ids)} pinned quiet runs "
          f"in {time.monotonic() - started:.1f} s\n", flush=True)

    layout = load_layout()
    moved: list[tuple[int, list[tuple], list[tuple]]] = []
    protected: list[int] = []
    protected_moved: list[int] = []
    refused: list[tuple[int, str]] = []
    broke: list[tuple[int, str]] = []
    before_types: Counter[str] = Counter()
    after_types: Counter[str] = Counter()
    unchanged = 0

    for done, run_id in enumerate(ids, start=1):
        before = stored_claims(factory, run_id)
        before_stamp = stamp(factory, run_id)
        summary = run_summary(factory, run_id)
        try:
            assess(
                summary,
                normality=normality,
                policies=POLICIES_OF_RECORD,
                layout=layout,
                session_factory=factory,
            )
        except CitedBundleError:
            protected.append(run_id)
            if stored_claims(factory, run_id) != before or stamp(factory, run_id) != before_stamp:
                protected_moved.append(run_id)
            continue
        except ChainError as refusal:
            refused.append((run_id, str(refusal).split(":")[0]))
            continue
        except Exception as defect:  # noqa: BLE001 -- recorded and stepped over
            broke.append((run_id, f"{type(defect).__name__}: {defect}"))
            continue
        after = stored_claims(factory, run_id)
        before_types.update(claim[1] for claim in before)
        after_types.update(claim[1] for claim in after)
        if after == before:
            unchanged += 1
        else:
            moved.append((run_id, before, after))
        if done % 50 == 0:
            rate = (time.monotonic() - started) / done
            print(f"  {done}/{len(ids)}, {rate:.2f} s a run", flush=True)

    elapsed = time.monotonic() - started
    with factory.begin() as session:
        baselines_after = session.execute(
            text(
                "SELECT detection_policy->>'BASELINE.quiet_run_count', count(*) "
                "FROM scenario_runs WHERE completed_at IS NOT NULL "
                "GROUP BY 1 ORDER BY 1"
            )
        ).all()

    rescored = unchanged + len(moved)
    print(f"\nre-scored {rescored} of {len(ids)} completed runs in {elapsed / 60:.1f} min")
    print(f"  claims unchanged : {unchanged}")
    print(f"  claims moved     : {len(moved)}")
    print(f"  protected        : {len(protected)} (refused by db-011, left on their baseline)")
    print(f"  refused          : {len(refused)}")
    print(f"  failed           : {len(broke)}")
    print("baselines on the stamps after: "
          + ", ".join(f"{n} quiet runs on {c}" for n, c in baselines_after))

    print("\nreported claims by type over the re-scored runs, before -> after:")
    for anomaly_type in sorted(set(before_types) | set(after_types)):
        print(f"  {anomaly_type:30} {before_types[anomaly_type]:4d} -> {after_types[anomaly_type]:4d}")

    print(f"\nRUNS WHOSE REPORTED CLAIMS MOVED ({len(moved)}):")
    for run_id, before, after in moved:
        print(f"  run {run_id}")
        for claim in before:
            print(f"    was {show(claim)}")
        for claim in after:
            print(f"    now {show(claim)}")

    print(f"\nprotected runs (claims and stamp checked unmoved): {protected}")
    if protected_moved:
        print(f"PROTECTED RUNS THAT MOVED -- a defect: {protected_moved}")
    if sorted(protected) != sorted(set(cited) & set(ids)):
        print(f"NOTE: protected {protected} differs from cited {cited}")
    for run_id, why in refused:
        print(f"refused run {run_id}: {why}")
    for run_id, why in broke:
        print(f"FAILED run {run_id}: {why}")

    failed = bool(broke or protected_moved)
    print(f"\nEXIT={1 if failed else 0}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
