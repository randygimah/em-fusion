"""Mutation pass over anom-004."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # repo root
CLU = ROOT / "backend/app/detection/clustering.py"
FND = ROOT / "backend/app/detection/findings.py"

MUTANTS = {
    "drop radius guard": (CLU,
        '        if self.radius_km <= 0:\n            raise ValueError(f"radius_km={self.radius_km} must be positive")',
        '        pass'),
    "default radius changed": (CLU, "DEFAULT_RADIUS_KM = 60.0", "DEFAULT_RADIUS_KM = 45.0"),
    "cluster every rule, not just track gaps": (CLU,
        "        rule_id=SOURCE_RULE_ID,", "        rule_id=None,  # type: ignore[arg-type]"),
    "started_at from the first member only": (CLU,
        "            started_at=min(member.started_at for member in cluster.members),",
        "            started_at=cluster.members[0].started_at,"),
    "ended_at from the first member only": (CLU,
        "            ended_at=max(member.ended_at for member in cluster.members),",
        "            ended_at=cluster.members[0].ended_at,"),
    "reportable finding type": (CLU,
        'FINDING_TYPE = "track_gap_cluster"', 'FINDING_TYPE = "possible_track_cluster"'),
    "a severity field appears": (CLU,
        "    finding_type: str = FINDING_TYPE",
        '    severity: str = "medium"\n    finding_type: str = FINDING_TYPE'),
    "size counts wrong": (CLU, "        return len(self.members)", "        return max(len(self.members) - 1, 0)"),
    "cluster passes a fixed radius": (CLU,
        "        radius_km=policy.radius_km,", "        radius_km=DEFAULT_RADIUS_KM,"),
    "finding drops its members": (FND,
        '            "members": list(cluster.members),', '            "members": [],'),
    "finding drops its size": (FND, '"size": cluster.size,', '"size": 0,'),
    "finding uses the source rule id": (FND,
        "        rule_id=cluster.rule_id,", '        rule_id="TRACK-GAP",'),
}

originals = {CLU: CLU.read_text(), FND: FND.read_text()}
results = {}
try:
    for name, (path, old, new) in MUTANTS.items():
        base = originals[path]
        if base.count(old) != 1:
            results[name] = f"INVALID ({base.count(old)} matches)"
            print(f"{name:42} {results[name]}", flush=True)
            continue
        path.write_text(base.replace(old, new, 1))
        proc = subprocess.run(
            ["make", "test-backend", "PYTEST_ARGS=tests/test_anom_clustering.py -q -x"],
            cwd=ROOT, capture_output=True, text=True,
        )
        tail = [l for l in proc.stdout.splitlines() if "passed" in l or "failed" in l or "error" in l]
        results[name] = ("KILLED   " if proc.returncode else "SURVIVED ") + (tail[-1] if tail else "?")
        print(f"{name:42} {results[name]}", flush=True)
        path.write_text(base)
finally:
    for path, text in originals.items():
        path.write_text(text)
    print("\nrestored")

killed = sum(1 for r in results.values() if r.startswith("KILLED"))
print(f"\n{killed}/{len(results)} killed")
for n, r in results.items():
    if not r.startswith("KILLED"):
        print(f"  !! {n}: {r}")
