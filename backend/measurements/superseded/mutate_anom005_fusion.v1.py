import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # repo root
F = ROOT / "backend/app/detection/fusion.py"
T = "tests/test_anom_fusion.py -q -x"

M = {
  "empty-period check removed": (
      "    if excess.during == 0 or excess.outside == 0:", "    if False:"),
  "only the window checked": (
      "    if excess.during == 0 or excess.outside == 0:", "    if excess.during == 0:"),
  "only the reference checked": (
      "    if excess.during == 0 or excess.outside == 0:", "    if excess.outside == 0:"),
  "absent measurement treated as measured": (
      "    if excess is None:", "    if False and excess is None:"),
  "unmeasurable lowers confidence": (
      '            corroboration=Corroboration.NOT_MEASURABLE,\n            confidence=Confidence.MEDIUM,\n            reason=(\n                f"the {empty} holds no track findings',
      '            corroboration=Corroboration.NOT_MEASURABLE,\n            confidence=Confidence.LOW,\n            reason=(\n                f"the {empty} holds no track findings'),
  "uncorroborated lowers confidence": (
      "        corroboration=Corroboration.NOT_CORROBORATED,\n        confidence=Confidence.MEDIUM,",
      "        corroboration=Corroboration.NOT_CORROBORATED,\n        confidence=Confidence.LOW,"),
  "corroboration does not raise confidence": (
      "            corroboration=Corroboration.CORROBORATED,\n            confidence=Confidence.HIGH,",
      "            corroboration=Corroboration.CORROBORATED,\n            confidence=Confidence.MEDIUM,"),
  "threshold boundary excluded": (
      "    if excess.ratio >= policy.corroboration_threshold:",
      "    if excess.ratio > policy.corroboration_threshold:"),
  "threshold ignored": (
      "    if excess.ratio >= policy.corroboration_threshold:", "    if True:"),
  "default threshold changed": (
      "DEFAULT_CORROBORATION_THRESHOLD = 1.58", "DEFAULT_CORROBORATION_THRESHOLD = 1.0"),
  "policy threshold ignored": (
      "    corroboration_threshold: float = DEFAULT_CORROBORATION_THRESHOLD",
      "    corroboration_threshold: float = 0.0"),
  "undecided zones become anomalies": (
      "        if dismissal.verdict is not Verdict.ENVIRONMENTAL:", "        if False:"),
  "undecided dropped silently": (
      "            declined.append(\n                Declination(", "            continue\n            declined.append(\n                Declination("),
  "faults become anomalies": (
      "    for dismissal in ordered:", "    for dismissal in (*ordered, *faults.faults):"),
  "dismissals not ordered": (
      "    ordered = sorted(\n        faults.dismissed, key=lambda d: (d.started_at, d.ended_at, d.sensor_id)\n    )",
      "    ordered = list(faults.dismissed)"),
  "excess refusal propagates": (
      "    except ValueError:\n        return None", "    except TypeError:\n        return None"),
  "zone loses the contributing neighbours": (
      "        sensors = (dismissal.sensor_id, *dismissal.spatial.abnormal)",
      "        sensors = (dismissal.sensor_id,)"),
  "declined zones become claims": (
      "        for zone in findings.zones", "        for zone in (*findings.zones, *findings.declined)"),
}

orig = F.read_text()
res = {}
try:
    for n, (o, w) in M.items():
        if orig.count(o) != 1:
            res[n] = f"INVALID ({orig.count(o)})"
            print(f"{n:42} {res[n]}", flush=True); continue
        F.write_text(orig.replace(o, w, 1))
        p = subprocess.run(["make", "test-backend", f"PYTEST_ARGS={T}"], cwd=ROOT,
                           capture_output=True, text=True)
        t = [l for l in p.stdout.splitlines() if "passed" in l or "failed" in l or "error" in l]
        res[n] = ("KILLED   " if p.returncode else "SURVIVED ") + (t[-1] if t else "?")
        print(f"{n:42} {res[n]}", flush=True)
finally:
    F.write_text(orig); print("\nrestored")

k = sum(1 for v in res.values() if v.startswith("KILLED"))
print(f"\n{k}/{len(res)} killed")
for n, v in res.items():
    if not v.startswith("KILLED"): print(f"  !! {n}: {v}")
