import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
F = ROOT / "app/detection/sensor_fault.py"
T = "tests/test_anom_sensor_fault.py"
PY = str(ROOT / ".venv/bin/python")

M = {
  "missing data reads as nominal": (
      "        if len(seen) < len(measured):", "        if False:"),
  "missing data outranks positive evidence": (
      "        if spatial.abnormal:", "        if spatial.abnormal and not spatial.unjudged:"),
  "no-neighbours case becomes a fault": (
      "        if not spatial.neighbours:", "        if False:"),
  "unsustained episode becomes a fault": (
      "        if not spectral.channels:", "        if False:"),
  "nominality bar ignored on neighbours": (
      "            if worst > policy.nominal_within_db:", "            if False:"),
  "nominality bar ignored on channels": (
      "        elif deviation > bar:", "        elif deviation > 1e9:"),
  "neighbour judged on the wrong channels": (
      "    channels = spectral.channels",
      "    channels = tuple(c.index for c in layout.channels)"),
  "worst neighbour channel becomes the best": (
      "            worst = max(seen)", "            worst = min(seen)"),
  "direction ignored for SNR": (
      "            deviation = value - baseline.mean if rises else baseline.mean - value",
      "            deviation = value - baseline.mean"),
  "no reading in the window reads as nominal": (
      "        if not inside:\n            return None\n        return sum(inside) / len(inside)",
      "        if not inside:\n            return 0.0\n        return sum(inside) / len(inside)"),
  "no series reads as nominal": (
      "        if series is None:\n            return None", "        if series is None:\n            return 0.0"),
  "mean becomes the peak": (
      "        return sum(inside) / len(inside)", "        return max(inside)"),
  "window not extended over the readings": (
      "        spans.append((min(start, raised[first]), max(end, raised[last])))",
      "        spans.append((start, end))"),
  "extension crosses a nominal reading": (
      "    return not any(left < at < right for at, _ in timeline)", "    return True"),
  "windows not merged after extension": (
      "        if merged and start <= merged[-1][1]:", "        if False:"),
  "configured radius ignored": (
      "        if self.neighbour_radius_km is None:\n            return layout.discrimination_radius_km\n        return self.neighbour_radius_km",
      "        return 1e6"),
  "radius default ignored": (
      "            return layout.discrimination_radius_km", "            return 1e6"),
  "radius guard removed": (
      "        if self.neighbour_radius_km is not None and self.neighbour_radius_km <= 0:",
      "        if False:"),
  "bar guard removed": ("        if self.nominal_within_db <= 0:", "        if False:"),
  "layout disagreement not refused": (
      "            raise FaultError(\n                f\"anomaly from {anomaly.cell.sensor_id}, which is not in this \"",
      "            continue\n            raise FaultError(\n                f\"anomaly from {anomaly.cell.sensor_id}, which is not in this \""),
  "track observation skipped not refused": (
      "                raise FaultError(\n                    f\"{observation.observation_type.value} observation belongs to \"",
      "                continue\n                raise FaultError(\n                    f\"{observation.observation_type.value} observation belongs to \""),
  "metric mismatch not refused": (
      "            if baseline.metric is not baselines.metric:", "            if False:"),
  "broadband is not the weak band": (
      "        if self.broadband:\n            # A wideband emitter beside the receiver produces this too.\n            return Confidence.LOW",
      "        if self.broadband:\n            return Confidence.HIGH"),
  "unmeasured adjacent channel does not lower confidence": (
      "        if self.adjacent_abnormal or self.adjacent_unjudged:",
      "        if self.adjacent_abnormal:"),
  "spread does not lower confidence": (
      "        if self.adjacent_abnormal or self.adjacent_unjudged:",
      "        if self.adjacent_unjudged:"),
  "adjacency ring is the whole plan": (
      "        checked.update(layout.adjacent_channels(channel))",
      "        checked.update(c.index for c in layout.channels)"),
  "seeds not sorted before extending": (
      "    for start, end in sorted(seeds):", "    for start, end in seeds:"),
  "sensors not sorted": ("    for sensor_id in sorted(seeds):", "    for sensor_id in seeds:"),
}

orig = F.read_text()
res = {}
try:
    for n, (o, w) in M.items():
        if orig.count(o) != 1:
            res[n] = f"INVALID ({orig.count(o)})"
            print(f"{n:54} {res[n]}", flush=True); continue
        F.write_text(orig.replace(o, w, 1))
        p = subprocess.run([PY, "-m", "pytest", T, "-q", "-x"], cwd=ROOT,
                           capture_output=True, text=True)
        t = [l for l in p.stdout.splitlines() if "passed" in l or "failed" in l or "error" in l]
        res[n] = ("KILLED   " if p.returncode else "SURVIVED ") + (t[-1] if t else "?")
        print(f"{n:54} {res[n]}", flush=True)
finally:
    F.write_text(orig); print("\nrestored")

k = sum(1 for v in res.values() if v.startswith("KILLED"))
print(f"\n{k}/{len(res)} killed")
for n, v in res.items():
    if not v.startswith("KILLED"): print(f"  !! {n}: {v}")
