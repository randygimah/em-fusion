"""Mutation pass over db-009's implementation."""
import subprocess, sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app/db/findings.py"

MUTANTS = {
    "drop radius guard": (
        '    if radius_km <= 0:\n        raise ValueError(f"radius_km={radius_km} must be positive")\n\n    with session_factory.begin() as session:\n        rows = (\n            session.execute(\n                text(\n                    "WITH scoped AS ("',
        '    with session_factory.begin() as session:\n        rows = (\n            session.execute(\n                text(\n                    "WITH scoped AS ("',
    ),
    "drop rule filter": (
        '"  WHERE scenario_run_id = :run_id AND rule_id = :rule_id "',
        '"  WHERE scenario_run_id = :run_id AND :rule_id = :rule_id "',
    ),
    "drop run filter": (
        '"  WHERE scenario_run_id = :run_id AND rule_id = :rule_id "',
        '"  WHERE :run_id = :run_id AND rule_id = :rule_id "',
    ),
    "drop window filter": (
        '"    AND (started_at, ended_at) "\n                    "        OVERLAPS (:window_start, :window_end)"',
        '"    AND (:window_start, :window_end) "\n                    "        OVERLAPS (:window_start, :window_end)"',
    ),
    "cluster in degrees": (
        'f"    ST_Transform(location, {METRE_SRID}), :metres) "',
        'f"    location, :metres) "  # {METRE_SRID}',
    ),
    "unordered window frame": (
        '"  FROM clustered WINDOW w AS (PARTITION BY cluster_id "\n                    "    ORDER BY started_at, subject, id "\n                    "    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)"',
        '"  FROM clustered WINDOW w AS (PARTITION BY cluster_id)"',
    ),
    "centroid in degrees": (
        '"    ST_Transform(ST_Centroid(ST_Collect("\n                    f"      ST_Transform(location, {METRE_SRID})) OVER w), "\n                    f"      {SRID}) AS centroid, "',
        '"    ST_Centroid(ST_Collect("\n                    "      location) OVER w) AS centroid, "',
    ),
    "hull through the projection": (
        '"    ST_ConvexHull(ST_Collect(location) OVER w) AS hull "',
        'f"    ST_Transform(ST_ConvexHull(ST_Collect("\n                    f"      ST_Transform(location, {METRE_SRID})) OVER w), {SRID}) AS hull "',
    ),
    "drop member ordering": (
        '"FROM shaped "\n                    "ORDER BY started_at, subject, id"',
        '"FROM shaped"',
    ),
    "groups ordered by cluster id": (
        "    return [\n        FindingCluster(",
        "    grouped = dict(sorted(grouped.items()))\n    return [\n        FindingCluster(",
    ),
}

original = SRC.read_text()
results = {}
try:
    for name, (old, new) in MUTANTS.items():
        if original.count(old) != 1:
            results[name] = f"INVALID ({original.count(old)} matches)"
            continue
        SRC.write_text(original.replace(old, new, 1))
        proc = subprocess.run(
            ["make", "test-backend", "PYTEST_ARGS=tests/test_db_clustering.py -q -x"],
            cwd=str(Path(__file__).resolve().parents[2]),
            capture_output=True, text=True,
        )
        killed = proc.returncode != 0
        tail = [l for l in proc.stdout.splitlines() if "passed" in l or "failed" in l or "error" in l]
        results[name] = ("KILLED   " if killed else "SURVIVED ") + (tail[-1] if tail else "?")
        print(f"{name:32} {results[name]}", flush=True)
finally:
    SRC.write_text(original)
    print("\nrestored original")

print("\n--- summary ---")
for name, r in results.items():
    print(f"{name:32} {r}")
