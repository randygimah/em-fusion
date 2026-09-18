import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
F = ROOT / "app/detection/sensor_fault.py"
T = "tests/test_anom_sensor_fault.py"
PY = str(ROOT / ".venv/bin/python")

M = {
  "unjudged neighbours ignored": (
      "            identifier for identifier in neighbours if unjudged.get(identifier)",
      "            identifier for identifier in neighbours if False"),
  "missing data outranks positive evidence": (
      "        if spatial.abnormal:", "        if spatial.abnormal and not spatial.unjudged:"),
  "no-neighbours case becomes a fault": (
      "        if not spatial.neighbours:", "        if False:"),
  "neighbour overlap strict at endpoints": (
      "    return left.started_at <= right.ended_at and right.started_at <= left.ended_at",
      "    return left.started_at < right.ended_at and right.started_at < left.ended_at"),
  "merge strict at endpoints": (
      "            if group and anomaly.started_at <= max(a.ended_at for a in group):",
      "            if group and anomaly.started_at < max(a.ended_at for a in group):"),
  "merged window ends at the last episode by start": (
      "        ended_at=max(a.ended_at for a in group),", "        ended_at=group[-1].ended_at,"),
  "merged window starts at the first episode": (
      "        started_at=min(a.started_at for a in group),", "        started_at=group[0].started_at,"),
  "configured radius ignored": (
      "        if self.neighbour_radius_km is None:\n            return layout.discrimination_radius_km\n        return self.neighbour_radius_km",
      "        return 1e6"),
  "radius default ignored": (
      "            return layout.discrimination_radius_km", "            return 1e6"),
  "radius guard removed": (
      "        if self.neighbour_radius_km is not None and self.neighbour_radius_km <= 0:",
      "        if False:"),
  "layout disagreement not refused": (
      "            raise FaultError(\n                f\"anomaly from {anomaly.cell.sensor_id}, which is not in this \"",
      "            continue\n            raise FaultError(\n                f\"anomaly from {anomaly.cell.sensor_id}, which is not in this \""),
  "broadband is not the weak band": (
      "        if self.broadband:\n            # A wideband emitter beside the receiver produces this too.\n            return Confidence.LOW",
      "        if self.broadband:\n            return Confidence.HIGH"),
  "unjudged adjacent channel does not lower confidence": (
      "        if self.adjacent_abnormal or self.adjacent_unjudged:",
      "        if self.adjacent_abnormal:"),
  "spread adjacent channel does not lower confidence": (
      "        if self.adjacent_abnormal or self.adjacent_unjudged:",
      "        if self.adjacent_unjudged:"),
  "adjacency test ignores which channels deviated": (
      "        adjacent_abnormal=tuple(sorted(checked & deviating)),",
      "        adjacent_abnormal=tuple(sorted(deviating)),"),
  "adjacency ring is the whole plan": (
      "        checked.update(layout.adjacent_channels(channel))",
      "        checked.update(c.index for c in layout.channels)"),
  "neighbour identity not checked": (
      "            other.sensor_id == identifier and _overlaps(window, other)",
      "            _overlaps(window, other)"),
  "windows not sorted": (
      "    return tuple(sorted(windows, key=lambda w: (w.sensor_id, w.started_at)))",
      "    return tuple(windows)"),
  "episodes not sorted before merging": (
      "        for anomaly in sorted(\n            per_sensor[sensor_id],\n            key=lambda a: (a.started_at, a.ended_at, a.cell.channel_index),\n        ):",
      "        for anomaly in per_sensor[sensor_id]:"),
  "sensors not sorted": ("    for sensor_id in sorted(per_sensor):", "    for sensor_id in per_sensor:"),
}

orig = F.read_text()
res = {}
try:
    for n, (o, w) in M.items():
        if orig.count(o) != 1:
            res[n] = f"INVALID ({orig.count(o)})"
            print(f"{n:52} {res[n]}", flush=True)
            continue
        F.write_text(orig.replace(o, w, 1))
        p = subprocess.run([PY, "-m", "pytest", T, "-q", "-x"], cwd=ROOT,
                           capture_output=True, text=True)
        t = [l for l in p.stdout.splitlines() if "passed" in l or "failed" in l or "error" in l]
        res[n] = ("KILLED   " if p.returncode else "SURVIVED ") + (t[-1] if t else "?")
        print(f"{n:52} {res[n]}", flush=True)
finally:
    F.write_text(orig)
    print("\nrestored")

k = sum(1 for v in res.values() if v.startswith("KILLED"))
print(f"\n{k}/{len(res)} killed")
for n, v in res.items():
    if not v.startswith("KILLED"):
        print(f"  !! {n}: {v}")
