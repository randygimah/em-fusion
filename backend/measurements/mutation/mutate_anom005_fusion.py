import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # repo root
F = ROOT / "backend/app/detection/fusion.py"
T = "tests/test_anom_fusion.py -q -x"

M = {
  "undecided zones become anomalies": (
      "    environmental = [d for d in ordered if d.verdict is Verdict.ENVIRONMENTAL]",
      "    environmental = list(ordered)"),
  "undecided dropped silently": (
      "        if dismissal.verdict is Verdict.ENVIRONMENTAL:\n            continue\n        declined.append(",
      "        if dismissal.verdict is not Verdict.ENVIRONMENTAL:\n            continue\n        declined.append("),
  "merging removed, one zone per dismissal": (
      "    groups: list[list[Dismissal]] = []\n    for dismissal in dismissals:",
      "    return [[d] for d in dismissals]\n    groups: list[list[Dismissal]] = []\n    for dismissal in dismissals:"),
  "everything merges into one zone": (
      "    ordered = [sorted(group, key=_member_order) for group in groups]",
      "    ordered = [sorted([d for g in groups for d in g], key=_member_order)] if groups else []"),
  "merge ignores the window": (
      "        and dismissal.started_at <= member.ended_at\n        and member.started_at <= dismissal.ended_at",
      "        and True"),
  "merge ignores which receivers were named": (
      "            member.sensor_id in dismissal.spatial.abnormal\n            or dismissal.sensor_id in member.spatial.abnormal",
      "            True or member.sensor_id in dismissal.spatial.abnormal"),
  "merge is one-directional": (
      "            member.sensor_id in dismissal.spatial.abnormal\n            or dismissal.sensor_id in member.spatial.abnormal",
      "            member.sensor_id in dismissal.spatial.abnormal"),
  "window overlap strict at endpoints": (
      "        and dismissal.started_at <= member.ended_at\n        and member.started_at <= dismissal.ended_at",
      "        and dismissal.started_at < member.ended_at\n        and member.started_at < dismissal.ended_at"),
  "chaining broken, only the first group joins": (
      "        merged = [dismissal, *(d for i in joined for d in groups[i])]",
      "        merged = [dismissal, *(groups[joined[0]] if joined else [])]"),
  "group members not ordered": (
      "    ordered = [sorted(group, key=_member_order) for group in groups]",
      "    ordered = [list(group) for group in groups]"),
  "groups not ordered": (
      "    return sorted(ordered, key=lambda group: _member_order(group[0]))",
      "    return ordered"),
  "merged window takes one end": (
      "        ended_at = max(d.ended_at for d in event)", "        ended_at = event[0].ended_at"),

  "centre is one receiver": (
      "    sites = [layout.site(sensor_id) for sensor_id in sensors]",
      "    sites = [layout.site(sensors[0])]"),
  "sensors lose the named neighbours": (
      "other for d in event for other in d.spatial.abnormal",
      "other for d in event for other in ()"),
  "merged window starts at one member (equivalent: members are sorted)": (
      "        started_at = min(d.started_at for d in event)",
      "        started_at = event[0].started_at"),
}

orig = F.read_text()
res = {}
try:
    for n, (o, w) in M.items():
        if orig.count(o) != 1:
            res[n] = f"INVALID ({orig.count(o)})"
            print(f"{n:44} {res[n]}", flush=True); continue
        F.write_text(orig.replace(o, w, 1))
        p = subprocess.run(["make", "test-backend", f"PYTEST_ARGS={T}"], cwd=ROOT,
                           capture_output=True, text=True)
        t = [l for l in p.stdout.splitlines() if "passed" in l or "failed" in l or "error" in l]
        res[n] = ("KILLED   " if p.returncode else "SURVIVED ") + (t[-1] if t else "?")
        print(f"{n:44} {res[n]}", flush=True)
finally:
    F.write_text(orig); print("\nrestored")

k = sum(1 for v in res.values() if v.startswith("KILLED"))
print(f"\n{k}/{len(res)} killed")
for n, v in res.items():
    if not v.startswith("KILLED"): print(f"  !! {n}: {v}")
