"""Mutation pass over evb-001, the evidence bundle builder.

The specific risk this pass exists for: a builder whose tests all pass
against a version that quietly **drops the uncertainty list**, **flattens
the two data modes**, or **collapses two kinds of absence into one**. All
three leave a well-formed bundle behind, which is precisely the defect a
shape-checking test does not see -- and the item's whole argument is that a
consumer which cannot tell the three kinds of absence apart will read
silence as absence.

So most sites below are the typed-absence boundary in one costume or
another: not-applicable rewritten as not-measurable, a reason replaced by
the bare flag it was chosen over, a measured negative folded in with the
things that were never measured. A test suite that cannot see those is
asserting shape and calling it meaning.

The remaining sites are the three structural claims: the unit is a claim,
the frequency axis is this module's, and a superseded claim is scoped to
the zone it lost.
"""
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
F = ROOT / "app/detection/bundle.py"
T = "tests/test_evb_bundle.py"
PY_BIN = os.environ.get("PY_BIN", str(ROOT / ".venv/bin/python"))

M = {
  # --- the two stated failure cases -------------------------------------
  "empty evidence accepted": (
      "        if not self.evidence:", "        if False:"),
  "item without a rule id accepted": (
      "            if not item.rule_id:", "            if False:"),

  # --- data mode is per item, not per bundle ----------------------------
  "rate excess claims to be synthetic": (
      "            data_mode=DataMode.REPLAYED,\n"
      "            started_at=excess.window[0],",
      "            data_mode=DataMode.SYNTHETIC,\n"
      "            started_at=excess.window[0],"),
  "track findings claim to be synthetic": (
      "            data_mode=DataMode.REPLAYED,\n"
      "            started_at=finding.started_at,",
      "            data_mode=DataMode.SYNTHETIC,\n"
      "            started_at=finding.started_at,"),
  "the bundle reports one mode for everything": (
      "        return frozenset(item.data_mode for item in self.evidence)",
      "        return frozenset({DataMode.SYNTHETIC})"),

  # --- every absence is typed -------------------------------------------
  "not-applicable rewritten as not-measurable": (
      "        kind=UncertaintyKind.NOT_APPLICABLE,\n        subject=\"track\",",
      "        kind=UncertaintyKind.NOT_MEASURABLE,\n        subject=\"track\","),
  "the fault bundle says nothing about the track side": (
      "    uncertainties = [Uncertainty(",
      "    uncertainties = [] if True else [Uncertainty("),
  "not-measurable corroboration goes unreported": (
      "    if producer.corroboration is Corroboration.NOT_MEASURABLE:",
      "    if False:"),
  "the reason is replaced by the bare flag": (
      "            statement=(\"the local discontinuity rate could not be measured: the \"",
      "            statement=(producer.corroboration.value + (\"\""),
  "measured-and-found-nothing filed as not-measurable": (
      "    if producer.corroboration is Corroboration.NOT_MEASURABLE:",
      "    if producer.corroboration is not Corroboration.CORROBORATED:"),
  "the rate excess never becomes evidence": (
      "    if excess is not None:", "    if False:"),
  "brief episodes folded in with the unjudged": (
      "            kind=UncertaintyKind.MEASURED_NEGATIVE,",
      "            kind=UncertaintyKind.NOT_MEASURABLE,"),
  "brief episodes dropped": (
      "    for brief in findings.suppressed:", "    for brief in ():"),
  "unjudged cells dropped": (
      "    for cell in findings.unjudged:", "    for cell in ():"),
  "unjudged neighbours dropped": (
      "    for neighbour in spatial.unjudged:", "    for neighbour in ():"),
  "unjudged channels dropped": (
      "    for channel in spectral.adjacent_unjudged:", "    for channel in ():"),

  # --- nominal neighbours are evidence, not an absence ------------------
  "nominal neighbours never become evidence": (
      "    for neighbour in spatial.neighbours:", "    for neighbour in ():"),
  "abnormal neighbours counted as nominal": (
      "        if neighbour in spatial.abnormal or neighbour in spatial.unjudged:",
      "        if False:"),
  "the neighbour margin is lost": (
      "            details={\"db\": elevations.get(neighbour, 0.0),",
      "            details={\"decibels\": elevations.get(neighbour, 0.0),"),

  # --- the unit is one reported claim ------------------------------------
  "any producer will do": (
      "        if producer.rule_id == claim.rule_id and _zone_of(producer) == claim.zone:",
      "        if True:"),
  "a missing producer raises the wrong kind of error": (
      "    raise BundleError(\n        f\"no {claim.rule_id} output matches",
      "    raise ValueError(\n        f\"no {claim.rule_id} output matches"),
  "only the first claim becomes a bundle": (
      "    for claim in resolution.reported:", "    for claim in resolution.reported[:1]:"),

  # --- the frequency axis is this module's -------------------------------
  "only one episode reaches a bundle": (
      "    for episode in findings.anomalies:", "    for episode in findings.anomalies[:1]:"),
  "episodes from any receiver are collected": (
      "        if episode.cell.sensor_id not in sensors:", "        if False:"),
  "affected channels are not reported": (
      "    return tuple(sorted(seen or set(declared)))", "    return ()"),
  "affected channels come from the rule rather than the evidence": (
      "    return tuple(sorted(seen or set(declared)))", "    return tuple(sorted(declared))"),

  # --- a superseded claim is scoped, and is never evidence ---------------
  "superseded claims dropped": (
      "            replace(bundle, superseded=_superseded_for(claim, resolution, radius)))",
      "            replace(bundle, superseded=()))"),
  "superseded claims not scoped by distance": (
      "        if great_circle_km(claim.zone.centre.lat, claim.zone.centre.lon,\n"
      "                           other.centre.lat, other.centre.lon) > radius:\n"
      "            continue",
      "        if False:\n            continue"),
  "superseded claims not scoped by the winning rule": (
      "        if suppression.claimed_by != claim.rule_id:", "        if False:"),
  "superseded claims not scoped by window": (
      "        if not claim.zone.overlaps(other):", "        if False:"),
  "the superseded reason is lost": (
      "            reason=suppression.reason,", "            reason=\"\","),

  # --- windows -----------------------------------------------------------
  "track findings are not window-filtered": (
      "        if not _overlaps((finding.started_at, finding.ended_at), window):",
      "        if False:"),
  "episodes are not window-filtered": (
      "        if not _overlaps((episode.started_at, episode.ended_at), window):",
      "        if False:"),
  "overlap tested from one side only": (
      "    return a[0] <= b[1] and b[0] <= a[1]", "    return a[0] <= b[1]"),
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
        # **Clear the bytecode cache, every time.** CPython validates a
        # `.pyc` on the source's (mtime-in-whole-seconds, size). These tests
        # run in about 0.1 s, so consecutive mutants land in the same second
        # -- and two that change the file's size by the same amount are then
        # indistinguishable to that check, so the second one silently runs
        # the FIRST one's bytecode and is scored SURVIVED. Two mutants here
        # did exactly that (`REPLAYED` -> `SYNTHETIC`, twice, +1 byte each)
        # and both were killed the moment they were run alone.
        shutil.rmtree(F.parent / "__pycache__", ignore_errors=True)
        p = subprocess.run([PY_BIN, "-m", "pytest", T, "-q", "-x"], cwd=ROOT,
                           capture_output=True, text=True,
                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        t = [l for l in p.stdout.splitlines()
             if "passed" in l or "failed" in l or "error" in l]
        res[n] = ("KILLED   " if p.returncode else "SURVIVED ") + (t[-1] if t else "?")
        print(f"{n:52} {res[n]}", flush=True)
finally:
    F.write_text(orig)
    print("\nrestored")

killed = sum(1 for v in res.values() if v.startswith("KILLED"))
survived = [n for n, v in res.items() if v.startswith("SURVIVED")]
invalid = [n for n, v in res.items() if v.startswith("INVALID")]
print(f"\n{killed} killed of {len(res) - len(invalid)} valid mutants")
if invalid:
    print(f"INVALID (the anchor did not match exactly once): {invalid}")
if survived:
    print("SURVIVED:")
    for n in survived:
        print(f"  - {n}")
