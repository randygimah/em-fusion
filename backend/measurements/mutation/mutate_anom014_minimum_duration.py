"""Mutation pass over anom-014, the minimum episode duration.

Every site here is one the item's own argument turns on: the comparison
direction at the boundary (an episode exactly at the minimum is an event),
the split between kept and suppressed, whether a suppression is reported at
all, and whether the negative-minimum refusal is real. The anom-001 sites the
file already had are left to their own pass -- this one asks only whether the
eleven new tests are load-bearing.
"""
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
F = ROOT / "app/detection/rf_noise.py"
T = "tests/test_anom_rf_noise.py"
PY_BIN = str(ROOT / ".venv/bin/python")

M = {
  "boundary excludes the minimum": (
      "        if span >= policy.minimum_duration:",
      "        if span > policy.minimum_duration:"),
  "minimum never applies": (
      "        if span >= policy.minimum_duration:", "        if True:"),
  "minimum always applies": (
      "        if span >= policy.minimum_duration:", "        if False:"),
  "span measured from the wrong end": (
      "        span = current[-1][0].timestamp - current[0][0].timestamp",
      "        span = current[0][0].timestamp - current[0][0].timestamp"),
  "suppressed episodes silently dropped": (
      """            suppressed.append(
                SuppressedEpisode(""",
      """            _ = (
                SuppressedEpisode("""),
  "suppression loses the reading count": (
      "                    readings=len(current),", "                    readings=0,"),
  "suppression loses the window": (
      "                    started_at=current[0][0].timestamp,\n"
      "                    ended_at=current[-1][0].timestamp,",
      "                    started_at=current[0][0].timestamp,\n"
      "                    ended_at=current[0][0].timestamp,"),
  "suppression loses the minimum it failed": (
      "                    minimum=policy.minimum_duration,",
      "                    minimum=timedelta(0),"),
  "negative minimum accepted": (
      "        if self.minimum_duration < timedelta(0):", "        if False:"),
  "negative minimum clamped rather than refused": (
      "        if self.minimum_duration < timedelta(0):",
      "        if self.minimum_duration < timedelta(seconds=-999999):"),
  "suppressions never reach the findings": (
      "        suppressed=tuple(suppressed),", "        suppressed=(),"),
  "suppressed folded in with the anomalies": (
      "        anomalies.extend(kept)\n        suppressed.extend(brief)",
      "        anomalies.extend(kept)"),
  "default minimum ignored by the policy": (
      "    minimum_duration: timedelta = DEFAULT_MINIMUM_DURATION",
      "    minimum_duration: timedelta = timedelta(0)"),
}

orig = F.read_text()
res = {}
try:
    for n, (o, w) in M.items():
        if orig.count(o) != 1:
            res[n] = f"INVALID ({orig.count(o)})"
            print(f"{n:46} {res[n]}", flush=True); continue
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
        print(f"{n:46} {res[n]}", flush=True)
finally:
    F.write_text(orig); print("\nrestored")

k = sum(1 for v in res.values() if v.startswith("KILLED"))
print(f"\n{k}/{len(res)} killed")
for n, v in res.items():
    if not v.startswith("KILLED"): print(f"  !! {n}: {v}")
