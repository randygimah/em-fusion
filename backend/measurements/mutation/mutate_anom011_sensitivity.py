import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # repo root
TG = ROOT / "backend/app/detection/track_gap.py"
SN = ROOT / "backend/app/detection/sensitivity.py"
TESTS = "tests/test_anom_sensitivity.py tests/test_anom_track_gap.py"

MUTANTS = {
    "tally check removed": (SN,
        "        if counted != missed:", "        if False:"),
    "tally check uses <=": (SN,
        "        if counted != missed:", "        if counted > missed:"),
    "empty-staged guard removed": (SN,
        "    if not staged:\n        raise ValueError(",
        "    if False:\n        raise ValueError("),
    # Written 2026-09-29 to replace a version that named this defect and
    # implemented none: `staged = {a for a in staged_aircraft}` is exactly
    # `set(staged_aircraft)`, so the "mutant" was the original and could
    # only ever survive. It was reported as a survivor for two days and
    # sent a reader looking for a test that was already there.
    "absent aircraft dropped from denominator": (SN,
        "    detected = 0\n    losses: Counter[Loss] = Counter()",
        "    detected = 0\n    losses: Counter[Loss] = Counter()\n"
        "    staged = staged & set(verdicts)"),
    "absent aircraft not counted as a loss": (SN,
        "            losses[Loss.NOT_IN_RUN] += 1", "            detected += 0"),
    "conditions trusted from the caller": (SN,
        "        conditions=replace(\n            conditions,\n"
        "            threshold_s=policy.threshold.total_seconds(),",
        "        conditions=replace(\n            conditions,\n"
        "            threshold_s=conditions.threshold_s,"),
    "loss taken from the least informative reason": (SN,
        "            losses[Loss(verdict.rejections[0].value)] += 1",
        "            losses[Loss(verdict.rejections[-1].value)] += 1"),
    "verdict always says detected": (TG,
        "        detected = bool(_not_heard(reports, policy) or _frozen(reports, policy))",
        "        detected = bool(_not_heard(reports, policy))"),
    "no-pair case dropped": (TG,
        "            if len(reports) < 2:\n                found.add(Rejection.NO_PAIR)",
        "            if False:\n                found.add(Rejection.NO_PAIR)"),
    "pair reasons not collected": (TG,
        "                if (why := _judge_pair(before, after, policy)) is not None:\n"
        "                    found.add(why)",
        "                if _judge_pair(before, after, policy) is None:\n"
        "                    pass"),
    "report reasons not collected": (TG,
        "                if (why := _judge_report(report, policy)) is not None:\n"
        "                    found.add(why)",
        "                if _judge_report(report, policy) is None:\n"
        "                    pass"),
    "interior guard inverted in the shared judge": (TG,
        "    if not _both_interior(before, after, policy):\n        return Rejection.NOT_INTERIOR",
        "    if _both_interior(before, after, policy):\n        return Rejection.NOT_INTERIOR"),
    "contact-fresh guard dropped from the shared judge": (TG,
        "    if report.contact_staleness >= policy.contact_fresh_within:\n"
        "        return Rejection.CONTACT_NOT_FRESH",
        "    if False:\n        return Rejection.CONTACT_NOT_FRESH"),
    "an aircraft can be missing from the verdicts": (TG,
        "        reports = sorted(per_aircraft[aircraft_id], key=lambda r: r.timestamp)\n"
        "        detected = bool(",
        "        reports = sorted(per_aircraft[aircraft_id], key=lambda r: r.timestamp)\n"
        "        if len(reports) < 2:\n            continue\n"
        "        detected = bool("),
}

originals = {TG: TG.read_text(), SN: SN.read_text()}
results = {}
try:
    for name, (path, old, new) in MUTANTS.items():
        base = originals[path]
        if base.count(old) != 1:
            results[name] = f"INVALID ({base.count(old)} matches)"
            print(f"{name:46} {results[name]}", flush=True); continue
        path.write_text(base.replace(old, new, 1))
        proc = subprocess.run(["make", "test-backend", f"PYTEST_ARGS={TESTS} -q -x"],
                              cwd=ROOT, capture_output=True, text=True)
        tail = [l for l in proc.stdout.splitlines()
                if "passed" in l or "failed" in l or "error" in l]
        results[name] = ("KILLED   " if proc.returncode else "SURVIVED ") + (tail[-1] if tail else "?")
        print(f"{name:46} {results[name]}", flush=True)
        path.write_text(base)
finally:
    for path, text in originals.items():
        path.write_text(text)
    print("\nrestored")

killed = sum(1 for r in results.values() if r.startswith("KILLED"))
print(f"\n{killed}/{len(results)} killed")
for n, r in results.items():
    if not r.startswith("KILLED"):
        print(f"  !! {n}: {r}")
