import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]  # repo root
F = ROOT / "backend/app/detection/rate_excess.py"
T = "tests/test_anom_rate_excess.py"
M = {
  "radius guard removed": ("        if self.radius_km <= 0:", "        if False:"),
  "no-reference guard removed": ("    if outside_s <= 0:", "    if False and outside_s <= 0:"),
  "counts instead of rates": (
      "    during_rate = _rate(during, window_s, span_s)\n    outside_rate = _rate(outside, outside_s, span_s)",
      "    during_rate = float(during) + 1.0\n    outside_rate = float(outside) + 1.0"),
  "smoothing dropped": ("    return count / seconds + 1.0 / span_seconds",
                        "    return count / seconds if seconds else 0.0"),
  "overlap becomes containment": (
      "        1 for f in in_disc if f.started_at < window[1] and f.ended_at > window[0]",
      "        1 for f in in_disc if f.started_at >= window[0] and f.ended_at <= window[1]"),
  "counts every rule, not just track gaps": ("        rule_id=SOURCE_RULE_ID,", "        rule_id=None,"),
  "radius ignored": ("        radius_km=policy.radius_km,\n        window=run_span,",
                     "        radius_km=1e6,\n        window=run_span,"),
  "outside computed as the whole span": ("    outside = len(in_disc) - during", "    outside = len(in_disc)"),
  "excess offset removed": ("        return self.ratio - 1.0", "        return self.ratio"),
  "window filter leaks the run span": ("        window=run_span,", "        window=window,"),
}
orig = F.read_text(); res = {}
try:
    for n, (o, w) in M.items():
        if orig.count(o) != 1:
            res[n] = f"INVALID ({orig.count(o)})"; print(f"{n:40} {res[n]}", flush=True); continue
        F.write_text(orig.replace(o, w, 1))
        p = subprocess.run(["make", "test-backend", f"PYTEST_ARGS={T} -q -x"], cwd=ROOT,
                           capture_output=True, text=True)
        t = [l for l in p.stdout.splitlines() if "passed" in l or "failed" in l or "error" in l]
        res[n] = ("KILLED   " if p.returncode else "SURVIVED ") + (t[-1] if t else "?")
        print(f"{n:40} {res[n]}", flush=True)
finally:
    F.write_text(orig); print("\nrestored")
k = sum(1 for v in res.values() if v.startswith("KILLED"))
print(f"\n{k}/{len(res)} killed")
for n, v in res.items():
    if not v.startswith("KILLED"): print(f"  !! {n}: {v}")
