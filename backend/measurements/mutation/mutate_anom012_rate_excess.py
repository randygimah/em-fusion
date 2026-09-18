import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]  # repo root
F = ROOT / "backend/app/detection/rate_excess.py"
T = "tests/test_anom_rate_excess.py -q -x"
M = {
  "zero-length guard removed": ("    if window_s <= 0:", "    if False:"),
  "zero-length guard excludes zero": ("    if window_s <= 0:", "    if window_s < 0:"),
  "negative window not caught": ("    if window_s <= 0:", "    if window_s == 0:"),
  "default radius is a different number": ("DEFAULT_RADIUS_KM = 60.0", "DEFAULT_RADIUS_KM = 45.0"),
  "policy ignores the default": ("    radius_km: float = DEFAULT_RADIUS_KM", "    radius_km: float = 1.0"),
}
orig = F.read_text(); res = {}
try:
    for n, (o, w) in M.items():
        if orig.count(o) != 1:
            res[n] = f"INVALID ({orig.count(o)})"; print(f"{n:38} {res[n]}", flush=True); continue
        F.write_text(orig.replace(o, w, 1))
        p = subprocess.run(["make", "test-backend", f"PYTEST_ARGS={T}"], cwd=ROOT,
                           capture_output=True, text=True)
        t = [l for l in p.stdout.splitlines() if "passed" in l or "failed" in l or "error" in l]
        res[n] = ("KILLED   " if p.returncode else "SURVIVED ") + (t[-1] if t else "?")
        print(f"{n:38} {res[n]}", flush=True)
finally:
    F.write_text(orig); print("\nrestored")
k = sum(1 for v in res.values() if v.startswith("KILLED"))
print(f"\n{k}/{len(res)} killed")
for n, v in res.items():
    if not v.startswith("KILLED"): print(f"  !! {n}: {v}")
