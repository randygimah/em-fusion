"""Mutation pass over scn-007, the minimum staged-aircraft floor.

The sites are the item's own argument: that the floor lifts the count only
when the fraction underfills, that the pool is ranked rather than drawn from,
that eligibility is decided in one place so the survey and the perturber
cannot disagree, and that a run which cannot reach the floor says so instead
of quietly staging fewer -- which is the empty answer key the item exists to
remove, arriving by a different door.
"""
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
F = ROOT / "app/scenario/tracks.py"
T = "tests/test_scn_tracks.py"
PY_BIN = str(ROOT / ".venv/bin/python")

M = {
  "floor ignored, fraction alone": (
      "    requested = max(minimum, round(len(eligible) * perturbation.fraction))",
      "    requested = round(len(eligible) * perturbation.fraction)"),
  "floor always wins over the fraction": (
      "    requested = max(minimum, round(len(eligible) * perturbation.fraction))",
      "    requested = minimum"),
  "floor takes the smaller of the two": (
      "    requested = max(minimum, round(len(eligible) * perturbation.fraction))",
      "    requested = min(minimum, round(len(eligible) * perturbation.fraction))"),
  "ranking replaced by arbitrary set order": (
      """    ranked = sorted(
        eligible,
        key=lambda p: (derive_unit(perturbation.seed, "track-target", p), p),
    )""",
      "    ranked = list(eligible)"),
  "ranking ignores the seed": (
      'key=lambda p: (derive_unit(perturbation.seed, "track-target", p), p),',
      "key=lambda p: p,"),
  "ties left unbroken": (
      'key=lambda p: (derive_unit(perturbation.seed, "track-target", p), p),',
      'key=lambda p: derive_unit(perturbation.seed, "track-target", p),'),
  "takes the highest rather than the lowest": (
      "        chosen=frozenset(ranked[:requested]),",
      "        chosen=frozenset(ranked[-requested:]),"),
  "takes the whole pool": (
      "        chosen=frozenset(ranked[:requested]),", "        chosen=frozenset(ranked),"),
  "floor_reached always true": (
      "        floor_reached=len(eligible) >= minimum,", "        floor_reached=True,"),
  "floor_reached excludes the boundary": (
      "        floor_reached=len(eligible) >= minimum,",
      "        floor_reached=len(eligible) > minimum,"),
  "floor_reached reports what was chosen, not what was found": (
      "        floor_reached=len(eligible) >= minimum,",
      "        floor_reached=len(ranked[:requested]) >= minimum,"),
  "negative floor accepted": ("    if minimum < 0:", "    if False:"),
  "survey ignores the window": (
      "        if not self.covers(record[\"timestamp\"]):\n            return False",
      "        pass"),
  "survey ignores the zone": (
      "        if not self.contains(location.get(\"lat\"), location.get(\"lon\")):\n"
      "            return False",
      "        pass"),
  "survey stages on parked aircraft": (
      "        return not record[\"payload\"].get(\"on_ground\")", "        return True"),
  "exclusions applied after the ranking": (
      "        if pseudonym is None or pseudonym in excluded:\n            continue",
      "        if pseudonym is None:\n            continue"),
  "eligibility counted per record, not per aircraft": (
      "    eligible: set[str] = set()", "    eligible: list[str] = []"),
  "perturber ignores the selection": (
      "        if self._selection is not None:\n"
      "            return pseudonym in self._selection.chosen",
      "        if False:\n            return pseudonym in self._selection.chosen"),
  "perturber inverts the selection": (
      "            return pseudonym in self._selection.chosen",
      "            return pseudonym not in self._selection.chosen"),
}

orig = F.read_text()
res = {}
try:
    for n, (o, w) in M.items():
        if orig.count(o) != 1:
            res[n] = f"INVALID ({orig.count(o)})"
            print(f"{n:52} {res[n]}", flush=True); continue
        F.write_text(orig.replace(o, w, 1))
        # Clear the bytecode cache: CPython validates a `.pyc` on the
        # source's (mtime-in-whole-seconds, size), and these runs are ~0.1 s
        # apart, so two consecutive mutants that change the file by the same
        # number of bytes are indistinguishable to that check and the second
        # silently runs the first's bytecode. Found on `evb-001`, where it
        # scored two genuinely-killed mutants as survivors.
        shutil.rmtree(F.parent / "__pycache__", ignore_errors=True)
        p = subprocess.run([PY_BIN, "-m", "pytest", T, "-q", "-x"], cwd=ROOT,
                           capture_output=True, text=True,
                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        t = [l for l in p.stdout.splitlines()
             if "passed" in l or "failed" in l or "error" in l]
        res[n] = ("KILLED   " if p.returncode else "SURVIVED ") + (t[-1] if t else "?")
        print(f"{n:52} {res[n]}", flush=True)
finally:
    F.write_text(orig); print("\nrestored")

k = sum(1 for v in res.values() if v.startswith("KILLED"))
print(f"\n{k}/{len(res)} killed")
for n, v in res.items():
    if not v.startswith("KILLED"): print(f"  !! {n}: {v}")
