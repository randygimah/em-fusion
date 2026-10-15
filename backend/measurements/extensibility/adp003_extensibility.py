"""What did the third source cost? Spec: adp-003 (6), RQ1.

Read from git, not remembered: files and lines between the clock-start commit
and `adp-003`'s feat commit, split into new files and changes to existing ones,
and by where they sit (app code, tests, docs). Then the hours, total and with
the waits for the user taken out.

Also checks constraint (3) on the same diff: every protected path -- ingest,
validation, pseudonymisation, the port, the schema, the detectors, the screens
-- must be untouched. A change there is the negative result, printed as such.

Usage, from the repo root: python backend/measurements/extensibility/adp003_extensibility.py
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta

#: `api-020`'s fix: the clock started on the commit after it.
START_COMMIT = "269c894"
CLOCK_START = datetime(2026, 10, 15, 19, 11, 59, tzinfo=UTC)

#: Each wait runs from the agent's message that asked the user something to the
#: user's reply, read from the session transcript's timestamps (UTC). Declared,
#: because the transcript is not in the repository.
WAITS: tuple[tuple[datetime, datetime, str], ...] = (
    (
        datetime(2026, 10, 15, 19, 12, 27, tzinfo=UTC),
        datetime(2026, 10, 15, 20, 51, 51, tzinfo=UTC),
        "agreement on how the hours are counted",
    ),
    (
        datetime(2026, 10, 15, 20, 57, 21, tzinfo=UTC),
        datetime(2026, 10, 15, 21, 2, 42, tzinfo=UTC),
        "review of the implementation",
    ),
)

#: Constraint (3): none of these may change.
PROTECTED = (
    "backend/app/dal/ingest.py",
    "backend/app/dal/validation.py",
    "backend/app/dal/pseudonymise.py",
    "backend/app/dal/repository.py",
    "backend/alembic/",
    "backend/app/db/",
    "backend/app/detection/",
    "backend/app/api/",
    "frontend/src/",
)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def area(path: str) -> str:
    if path.startswith("backend/app/"):
        return "app"
    if path.startswith("backend/tests/"):
        return "tests"
    return "docs"


def main() -> None:
    end = git("log", "--format=%h", "--grep=^feat(adp-003)", "-1")
    if not end:
        raise SystemExit("no feat(adp-003) commit yet")
    end_at = datetime.fromisoformat(git("log", "-1", "--format=%cI", end)).astimezone(UTC)

    status = dict(
        line.split("\t", 1)[::-1]
        for line in git("diff", "--name-status", START_COMMIT, end).splitlines()
    )
    print(f"adp-003 extensibility, {START_COMMIT}..{end}")
    print(f"{'kind':<9}{'area':<7}{'+':>5}{'-':>5}  file")
    totals: dict[tuple[str, str], list[int]] = {}
    for line in git("diff", "--numstat", START_COMMIT, end).splitlines():
        added, removed, path = line.split("\t")
        kind = "new" if status[path] == "A" else "existing"
        print(f"{kind:<9}{area(path):<7}{added:>5}{removed:>5}  {path}")
        tally = totals.setdefault((kind, area(path)), [0, 0, 0])
        tally[0] += 1
        tally[1] += int(added)
        tally[2] += int(removed)

    print("\nfiles, lines added, lines removed")
    for (kind, where), (files, added_n, removed_n) in sorted(totals.items()):
        print(f"  {kind:<9}{where:<7}{files:>3} files  +{added_n:<5} -{removed_n}")

    touched = [p for p in status if p.startswith(PROTECTED)]
    print("\nconstraint (3), protected paths touched:", touched or "none")

    total = end_at - CLOCK_START
    waited = sum(
        (
            min(replied, end_at) - max(asked, CLOCK_START)
            for asked, replied, _ in WAITS
            if replied > CLOCK_START and asked < end_at
        ),
        timedelta(),
    )
    print(f"\nclock {CLOCK_START:%H:%M:%S} to {end_at:%H:%M:%S} UTC on {end_at:%Y-%m-%d}")
    for asked, replied, why in WAITS:
        print(f"  wait {asked:%H:%M:%S}-{replied:%H:%M:%S}  {why}")
    print(f"elapsed  {total}  ({total.total_seconds() / 3600:.2f} h)")
    print(f"waiting  {waited}")
    active = total - waited
    print(f"active   {active}  ({active.total_seconds() / 3600:.2f} h)  <- the figure")


if __name__ == "__main__":
    main()
