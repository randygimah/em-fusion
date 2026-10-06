"""Fill in the evidence accounts the pass used to throw away. Spec: evb-003.

Until `evb-003` the detection pass built its bundles and did not store them,
so `api-015` reports a conclusion as **unexplained** on every hour whose
account was discarded. On the store of record that is 140 of the 240
claim-bearing hours, and every hour the screen offers first -- which makes
the evidence panel correct and empty exactly where anybody would look.

This fills them. Two conditions put a run in scope and both are measured
rather than assumed:

  * a reported claim with no bundle -- the 140 above;
  * a bundle matching no reported claim -- four on this store (ids 220, 237,
    242 and 251, on runs 54, 71, 76 and 105), each off by one or two
    sampling intervals at one end of its window. They were written by
    `bundle_end_to_end.py` on 19 and 28 September, before `anom-007`'s
    window derivation settled, and `evb-002` replaces per run, so a fill
    scoped to "runs with no bundle" would never reach them and they would
    disagree with themselves forever.

**It runs the shipped pass and reimplements nothing.** `assess` is the one
composition of the eight rules, and a second one here is the drift
`anom-015` exists to prevent.

**What protects the figures of record is the comparison, not a withheld
write.** Two rules read stored track findings back, so a pass that writes no
findings cannot reach the fusion decision at all -- the item's original
constraint was unachievable and is amended. Instead: each run's stored
reported claims are read **before** the pass runs and compared against what
it stored, and a disagreement **stops the whole fill**. Not skips -- stops.
A skip would carry on rewriting the remaining runs under settings just shown
to disagree with the ones every quoted figure was measured under.

Two costs, stated rather than hidden. `detection_pass_at` and
`detection_policy` move to today on every run touched, which is true: the
hour was re-examined. And the track findings are replaced without being
compared -- the comparison is over the reported claims, which are what the
bundles explain and what `eval-002`'s table is indexed by.

**Runs protected by `db-011` are refused, not worked around.** Twenty
bundles on runs 102-175 carry 155 hypothesis rows by a cascading delete.
They already have their accounts, so none of them is in scope; the refusal
is nonetheless left to fire rather than filtered out in advance, because a
guard that is routed around is a guard nobody has seen work.

Run it:

    make measure SCRIPT=corpus/backfill_bundles.py                    # scope only
    make measure SCRIPT=corpus/backfill_bundles.py BACKFILL_CONFIRM=yes  # and write

No aircraft identifier of any kind reaches this log, per
`measurements/README.md`: nothing here prints a bundle's contents.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.bundles import CitedBundleError
from app.db.repository import quiet_run_ids, run_summary
from app.detection.chain import assess, measure_normality
from app.detection.findings import claim_identity
from app.detection.settings import BASELINE_WINDOW, POLICIES_OF_RECORD
from app.scenario.layout import load_layout

CONFIRM_VAR = "BACKFILL_CONFIRM"

#: The run range, NAMED rather than taken from the store's own bounds. A
#: default of "everything" is how a protected population gets reached by a
#: script nobody re-read, and the point of this file is that the set it
#: touches is decided here in the open and printed before anything is written.
FIRST_RUN, LAST_RUN = 1, 420

REPORTABLE = (
    "possible_sensor_fault",
    "possible_interference_zone",
    "possible_data_source_issue",
)


def confirmed() -> bool:
    return os.environ.get(CONFIRM_VAR, "").strip().lower() in {"yes", "1", "true"}


def stored_claims(factory: sessionmaker, run_id: int) -> set[tuple]:
    """The run's reported claims, by `anom-015`'s own identity."""
    from app.db.findings import findings_for_run

    return {
        claim_identity(f)
        for f in findings_for_run(factory, run_id)
        if f.finding_type in REPORTABLE
    }


def in_scope(engine) -> tuple[list[int], list[int]]:
    """Runs with a claim and no bundle, and runs with a bundle and no claim."""
    types = ", ".join(f"'{t}'" for t in REPORTABLE)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "WITH claims AS ("
                "  SELECT DISTINCT scenario_run_id FROM detection_findings"
                f"  WHERE finding_type IN ({types})),"
                " bundles AS (SELECT DISTINCT scenario_run_id FROM evidence_bundles),"
                " orphan AS ("
                "  SELECT DISTINCT b.scenario_run_id FROM evidence_bundles b"
                "  WHERE NOT EXISTS ("
                "    SELECT 1 FROM detection_findings f"
                "    WHERE f.scenario_run_id = b.scenario_run_id"
                "      AND f.rule_id = b.rule_id AND f.finding_type = b.anomaly_type"
                "      AND f.subject = split_part(b.subject, ', ', 1)"
                "      AND f.started_at = b.started_at AND f.ended_at = b.ended_at))"
                " SELECT r.id,"
                "   (r.id IN (SELECT scenario_run_id FROM claims)"
                "     AND r.id NOT IN (SELECT scenario_run_id FROM bundles)) AS unbundled,"
                "   (r.id IN (SELECT scenario_run_id FROM orphan)) AS stale"
                " FROM scenario_runs r"
                " WHERE r.id BETWEEN :first AND :last AND r.completed_at IS NOT NULL"
                " ORDER BY r.id"
            ),
            {"first": FIRST_RUN, "last": LAST_RUN},
        ).all()
    return (
        [row[0] for row in rows if row[1]],
        [row[0] for row in rows if row[2]],
    )


def main() -> int:
    print("backfill_bundles.py -- evb-003")
    print(f"run range named here: {FIRST_RUN}-{LAST_RUN}\n")

    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    factory = sessionmaker(bind=engine, autoflush=False)

    unbundled, stale = in_scope(engine)
    scope = sorted(set(unbundled) | set(stale))
    print(f"a claim with no bundle : {len(unbundled)} runs")
    print(f"a bundle with no claim : {len(stale)} runs {stale}")
    print(f"in scope               : {len(scope)} runs\n")
    if not scope:
        print("nothing to fill.")
        return 0

    if not confirmed():
        print(
            f"This WRITES to the store. Set {CONFIRM_VAR}=yes to run it.\n"
            "It re-examines every run above: bundles are stored, the reported\n"
            "claims are replaced byte-identically (and checked), and the\n"
            "examination stamp moves to today."
        )
        return 1

    quiet = quiet_run_ids(factory)
    print(f"building normality over {len(quiet)} quiet runs ...")
    started = datetime.now(timezone.utc)
    normality = measure_normality(
        factory,
        quiet_run_ids=quiet,
        policies=POLICIES_OF_RECORD,
        window=BASELINE_WINDOW,
    )
    print(f"  {(datetime.now(timezone.utc) - started).total_seconds():.1f} s\n")

    layout = load_layout()
    filled = refused = 0
    for run_id in scope:
        before = stored_claims(factory, run_id)
        summary = run_summary(factory, run_id)
        if summary is None:
            print(f"run {run_id}: no row. stopping.")
            return 2
        try:
            assessment = assess(
                summary,
                normality=normality,
                policies=POLICIES_OF_RECORD,
                layout=layout,
                session_factory=factory,
            )
        except CitedBundleError as protected:
            # Left to fire rather than filtered out in advance: a guard that is
            # routed around is a guard nobody has seen work.
            refused += 1
            print(f"run {run_id}: REFUSED by db-011 -- {protected}")
            continue
        after = stored_claims(factory, run_id)
        if before and after != before:
            print(
                f"\nrun {run_id}: the rebuilt claims DISAGREE with the stored ones.\n"
                f"  was : {sorted(before)}\n"
                f"  now : {sorted(after)}\n"
                "STOPPING. The detectors no longer reproduce the figures of "
                "record, so every further run would be rewritten under settings "
                "that have just been shown to differ."
            )
            return 3
        filled += 1
        print(f"run {run_id}: {len(assessment.bundles)} bundle(s), claims agree")

    print(f"\nfilled {filled} runs, refused {refused}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
