import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # repo root
TR = ROOT / "backend/app/scenario/tracks.py"
TESTS = "tests/test_scn_tracks.py tests/test_scn_ground_truth.py tests/test_scn_ambiguous.py"

MUTANTS = {
    "gate removed": ('        if record["payload"].get("on_ground"):\n            return dict(record)',
                     "        if False:\n            return dict(record)"),
    "gate inverted": ('        if record["payload"].get("on_ground"):',
                      '        if not record["payload"].get("on_ground"):'),
    "gate placed after the answer key": (
        '        if record["payload"].get("on_ground"):\n            return dict(record)\n\n'
        '        identifier = record["payload"].get("icao24")\n'
        '        if not identifier or not self.targets(str(identifier)):\n'
        '            return dict(record)\n\n'
        '        pseudonym = self._pseudonymiser.aircraft(str(identifier))\n'
        '        if pseudonym is not None:\n            self._affected.add(pseudonym)',
        '        identifier = record["payload"].get("icao24")\n'
        '        if not identifier or not self.targets(str(identifier)):\n'
        '            return dict(record)\n\n'
        '        pseudonym = self._pseudonymiser.aircraft(str(identifier))\n'
        '        if pseudonym is not None:\n            self._affected.add(pseudonym)\n\n'
        '        if record["payload"].get("on_ground"):\n            return dict(record)'),
    "gate reads the wrong field": ('        if record["payload"].get("on_ground"):',
                                   '        if record["payload"].get("onground"):'),
    "gate returns the record object rather than a copy": (
        '        if record["payload"].get("on_ground"):\n            return dict(record)',
        '        if record["payload"].get("on_ground"):\n            return None'),
}

original = TR.read_text()
results = {}
try:
    for name, (old, new) in MUTANTS.items():
        if original.count(old) != 1:
            results[name] = f"INVALID ({original.count(old)} matches)"
            print(f"{name:44} {results[name]}", flush=True); continue
        TR.write_text(original.replace(old, new, 1))
        proc = subprocess.run(["make", "test-backend", f"PYTEST_ARGS={TESTS} -q -x"],
                              cwd=ROOT, capture_output=True, text=True)
        tail = [l for l in proc.stdout.splitlines()
                if "passed" in l or "failed" in l or "error" in l]
        results[name] = ("KILLED   " if proc.returncode else "SURVIVED ") + (tail[-1] if tail else "?")
        print(f"{name:44} {results[name]}", flush=True)
finally:
    TR.write_text(original)
    print("\nrestored")

killed = sum(1 for r in results.values() if r.startswith("KILLED"))
print(f"\n{killed}/{len(results)} killed")
for n, r in results.items():
    if not r.startswith("KILLED"):
        print(f"  !! {n}: {r}")
