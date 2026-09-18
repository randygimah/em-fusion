"""Is the determinism test a reliable detector, or did it get lucky once?"""
import subprocess
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app/db/findings.py"
OLD = ('"  FROM clustered WINDOW w AS (PARTITION BY cluster_id "\n'
       '                    "    ORDER BY started_at, subject, id "\n'
       '                    "    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)"')
NEW = '"  FROM clustered WINDOW w AS (PARTITION BY cluster_id)"'
TEST = "tests/test_db_clustering.py::test_the_same_findings_give_the_same_groups_in_the_same_order"

original = SRC.read_text()
assert original.count(OLD) == 1


def run(label):
    proc = subprocess.run(
        ["make", "test-backend", f"PYTEST_ARGS={TEST} -q"],
        cwd=str(Path(__file__).resolve().parents[2]),
        capture_output=True, text=True,
    )
    print(f"{label}: {'FAIL' if proc.returncode else 'pass'}", flush=True)
    return proc.returncode != 0


try:
    SRC.write_text(original.replace(OLD, NEW, 1))
    caught = sum(run(f"  mutant run {i + 1}") for i in range(3))
finally:
    SRC.write_text(original)

fine = sum(not run(f"  fixed  run {i + 1}") for i in range(3))
print(f"\nmutant caught {caught}/3 ; fixed passed {fine}/3")
