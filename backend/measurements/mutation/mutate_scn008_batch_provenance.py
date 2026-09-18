"""Mutation pass over scn-008, the batch provenance on a run row.

The sites are the item's own argument: that the three values are written,
that they are written only when there is a batch, that they survive the
round-trip through `from_record` as provenance rather than tripping its
refusal, and that the index is verified against the batch it claims.
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
F = ROOT / "app/scenario/emitter.py"
T = "tests/test_scn_batch.py"
PY_BIN = str(ROOT / ".venv/bin/python")

M = {
  "base seed never written": (
      '            recorded["base_seed"] = self.batch.base_seed',
      '            recorded["base_seed"] = 0'),
  "batch index never written": (
      '            recorded["batch_index"] = self.batch.index',
      '            recorded["batch_index"] = 0'),
  "batch run count never written": (
      '            recorded["batch_runs"] = self.batch.runs',
      '            recorded["batch_runs"] = 1'),
  "provenance written even with no batch": (
      "        if self.batch is not None:", "        if True:"),
  "provenance never written": (
      "        if self.batch is not None:", "        if False:"),
  "from_record ignores a recorded batch": (
      '        if "base_seed" in remaining:', "        if False:"),
  "from_record loses the batch on the way back": (
      "            batch = BatchProvenance(", "            _ = BatchProvenance("),
  "index past the batch accepted": (
      "        if self.index >= self.runs:", "        if False:"),
  "index boundary off by one": (
      "        if self.index >= self.runs:", "        if self.index > self.runs:"),
  "negative index accepted": (
      "    index: int = Field(ge=0)", "    index: int = Field()"),
  "zero-run batch accepted": (
      "    runs: int = Field(gt=0)", "    runs: int = Field()"),
}

orig = F.read_text()
res = {}
try:
    for n, (o, w) in M.items():
        if orig.count(o) != 1:
            res[n] = f"INVALID ({orig.count(o)})"
            print(f"{n:42} {res[n]}", flush=True); continue
        F.write_text(orig.replace(o, w, 1))
        p = subprocess.run([PY_BIN, "-m", "pytest", T, "-q", "-x"], cwd=ROOT,
                           capture_output=True, text=True)
        t = [l for l in p.stdout.splitlines()
             if "passed" in l or "failed" in l or "error" in l]
        res[n] = ("KILLED   " if p.returncode else "SURVIVED ") + (t[-1] if t else "?")
        print(f"{n:42} {res[n]}", flush=True)
finally:
    F.write_text(orig); print("\nrestored")

k = sum(1 for v in res.values() if v.startswith("KILLED"))
print(f"\n{k}/{len(res)} killed")
for n, v in res.items():
    if not v.startswith("KILLED"): print(f"  !! {n}: {v}")
