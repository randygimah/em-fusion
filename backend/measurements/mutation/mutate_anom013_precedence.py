import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
F = ROOT / "app/detection/precedence.py"
T = "tests/test_anom_precedence.py"
PY = str(ROOT / ".venv/bin/python")

M = {
  "declared order reversed": (
      'RULE_ORDER: tuple[str, ...] = ("SENSOR-FAULT", "SOURCE-GAP", "FUSION-SPATIAL")',
      'RULE_ORDER: tuple[str, ...] = ("FUSION-SPATIAL", "SOURCE-GAP", "SENSOR-FAULT")'),
  "fusion put before the fault": (
      'RULE_ORDER: tuple[str, ...] = ("SENSOR-FAULT", "SOURCE-GAP", "FUSION-SPATIAL")',
      'RULE_ORDER: tuple[str, ...] = ("SOURCE-GAP", "FUSION-SPATIAL", "SENSOR-FAULT")'),
  "resolution follows arrival order": (
      "    ranked = sorted(_checked(claims), key=_position)",
      "    ranked = _checked(claims)"),
  "rule position ignored in the sort": (
      "        RULE_ORDER.index(candidate.rule_id),",
      "        0,"),
  "undeclared rule accepted": (
      "        if candidate.rule_id not in RULE_ORDER:", "        if False:"),
  "same-rule claims suppress each other": (
      "        if held.rule_id == candidate.rule_id:\n            continue", "        pass"),
  "zone radius ignored": ("        if distance <= radius:", "        if True:"),
  "zone radius excludes the boundary": (
      "        if distance <= radius:", "        if distance < radius * 0.5:"),
  "time overlap ignored": (
      "        if not held.zone.overlaps(candidate.zone):\n            continue",
      "        pass"),
  "overlap strict at endpoints": (
      "        return self.started_at <= other.ended_at and other.started_at <= self.ended_at",
      "        return self.started_at < other.ended_at and other.started_at < self.ended_at"),
  "inverted zone accepted": (
      "        if self.ended_at < self.started_at:", "        if False:"),
  "zone radius guard removed": (
      "        if self.zone_radius_km is not None and self.zone_radius_km <= 0:",
      "        if False:"),
  "radius default ignored": (
      "            return layout.discrimination_radius_km", "            return 60.0"),
  "dismissals become claims": (
      "        for fault in findings.faults", "        for fault in findings.dismissed"),
  "suppression loses who took the zone": (
      "                claimed_by=taken,", "                claimed_by=\"\","),
  "suppressed claims reported anyway": (
      "        if taken is None:\n            reported.append(candidate)\n            continue",
      "        reported.append(candidate)\n        if taken is None:\n            continue"),
}

orig = F.read_text()
res = {}
try:
    for n, (o, w) in M.items():
        if orig.count(o) != 1:
            res[n] = f"INVALID ({orig.count(o)})"
            print(f"{n:42} {res[n]}", flush=True); continue
        F.write_text(orig.replace(o, w, 1))
        p = subprocess.run([PY, "-m", "pytest", T, "-q", "-x"], cwd=ROOT,
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
