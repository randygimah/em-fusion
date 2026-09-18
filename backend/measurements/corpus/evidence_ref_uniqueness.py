"""Does a finding's `evidence_refs` coordinate identify exactly one row?

`evb-002` requires every evidence item to resolve to a stored observation,
checked against the database rather than asserted. `DetectionFinding`
already carries `evidence_refs`, but what they hold is a **coordinate, not
an identifier**: an RF finding cites `{sensor_id, channel_index,
timestamp}` and a track finding cites `{aircraft_id, at}`. So resolution is
a query, and a query is only a resolution if it returns exactly one row.

This measures that, and it decides which of two test suites gets written:
resolve by coordinate, or change every `from_*` function to record row ids
at finding time. **A resolver that silently matches two rows is worse than
one that fails**, because the bundle would carry a citation to whichever
row the heap handed over first -- the same unordered-partition failure this
project has now recorded three times.

It also checks the second way a coordinate resolver fails quietly: the
refs store timestamps as ISO strings (`findings.py` records why), so a
resolver compares a parsed string against a stored `timestamptz`. If that
round trip is not exact -- microseconds, offset, DST spelling -- every
lookup misses and `evb-002` refuses every bundle, which at least fails
loudly, or worse, matches a neighbouring reading.
"""
from __future__ import annotations

import os

import _corpus
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

print(_corpus.describe(), flush=True)

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
factory = sessionmaker(bind=engine, autoflush=False)

#: The coordinate each kind of finding actually cites, as SQL.
COORDINATES = {
    "rf": ("payload->>'sensor_id', (payload->>'channel_index')::int, timestamp",
           "sensor_id + channel_index + timestamp"),
    "track": ("payload->>'aircraft_id', timestamp",
              "aircraft_id + timestamp"),
}


def uniqueness(observation_type: str, columns: str, corpus_filter: str) -> dict:
    """Rows, distinct coordinates, and the worst collision."""
    with factory.begin() as session:
        row = session.execute(text(f"""
            WITH scoped AS (
              SELECT o.scenario_run_id, {columns} AS coord_cols, o.id
              FROM observations o
              JOIN scenario_runs r ON r.id = o.scenario_run_id
              WHERE o.observation_type = :t AND {corpus_filter}
            ), grouped AS (
              SELECT scenario_run_id, coord_cols, COUNT(*) AS n
              FROM scoped GROUP BY 1, 2
            )
            SELECT COALESCE(SUM(n), 0) AS rows,
                   COUNT(*)            AS coordinates,
                   COALESCE(MAX(n), 0) AS worst,
                   COUNT(*) FILTER (WHERE n > 1) AS colliding
            FROM grouped
        """), {"t": observation_type}).mappings().one()
    return dict(row)


print("\n" + "=" * 74)
print("COORDINATE UNIQUENESS, within one scenario run")
print("=" * 74)

verdicts = {}
for corpus in ("v2", "v1"):
    os.environ["CORPUS"] = corpus
    corpus_filter = _corpus.run_filter("r")
    print(f"\ncorpus {corpus}:")
    for observation_type, (columns, label) in COORDINATES.items():
        # `columns` is a comma-separated list; wrap it so it groups as a tuple.
        result = uniqueness(observation_type, f"({columns})", corpus_filter)
        unique = result["colliding"] == 0
        verdicts[(corpus, observation_type)] = unique
        print(f"  {observation_type:6} by {label:34} "
              f"{result['rows']:>10,} rows / {result['coordinates']:>10,} coords  "
              f"worst={result['worst']}  colliding={result['colliding']:,}  "
              f"{'UNIQUE' if unique else '*** NOT UNIQUE ***'}")

os.environ["CORPUS"] = "v2"

# ------------------------------------------------- the ISO round-trip check
print("\n" + "=" * 74)
print("TIMESTAMP ROUND TRIP -- ISO string out, parsed value back in")
print("=" * 74)
with factory.begin() as session:
    samples = session.execute(text(
        "SELECT o.id, o.timestamp, o.observation_type FROM observations o "
        "JOIN scenario_runs r ON r.id = o.scenario_run_id "
        f"WHERE {_corpus.run_filter('r')} ORDER BY o.id LIMIT 2000")).mappings().all()

mismatches = []
for sample in samples:
    iso = sample["timestamp"].isoformat()
    with factory.begin() as session:
        back = session.execute(text(
            # CAST(... AS ...) and not `::timestamptz`: SQLAlchemy's text()
            # reads `:ts::timestamptz` as a parameter named `ts:` and hands
            # PostgreSQL a bare colon.
            "SELECT id FROM observations WHERE id = :i "
            "AND timestamp = CAST(:ts AS timestamptz)"),
            {"i": sample["id"], "ts": iso}).first()
    if back is None:
        mismatches.append((sample["id"], iso))

print(f"  sampled {len(samples):,} observations")
print(f"  ISO string re-matched its own row: {len(samples) - len(mismatches):,}")
print(f"  failed to re-match:                {len(mismatches):,}")
if mismatches:
    print(f"  examples: {mismatches[:3]}")

# --------------------------------------------------- what a lookup costs
print("\n" + "=" * 74)
print("WHAT ONE RESOLUTION COSTS")
print("=" * 74)
with factory.begin() as session:
    probe = session.execute(text(
        "SELECT o.scenario_run_id, o.timestamp, o.payload->>'sensor_id' AS s, "
        "o.payload->>'channel_index' AS c FROM observations o "
        "JOIN scenario_runs r ON r.id = o.scenario_run_id "
        f"WHERE {_corpus.run_filter('r')} AND o.observation_type='rf' LIMIT 1")).mappings().one()
    plan = session.execute(text(
        "EXPLAIN ANALYZE SELECT id FROM observations WHERE scenario_run_id=:r "
        "AND observation_type='rf' AND payload->>'sensor_id'=:s "
        "AND (payload->>'channel_index')::int=:c AND timestamp=:ts"),
        {"r": probe["scenario_run_id"], "s": probe["s"],
         "c": int(probe["c"]), "ts": probe["timestamp"]}).all()
for line in plan:
    print("  " + line[0])

print("\n" + "=" * 74)
all_unique = all(verdicts.values())
print("FINDING:", "every cited coordinate identifies exactly one row"
      if all_unique else "a cited coordinate can match more than one row")
print("=" * 74)
print(f"""
Decides `evb-002`: {'resolve by coordinate -- no change to the from_* functions'
                    if all_unique else
                    'record row ids at finding time; a coordinate resolver would be ambiguous'}.
The round-trip result is independent of that: it says whether a resolver may
compare the stored ISO string directly, or must normalise before comparing.""")
