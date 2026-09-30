"""Mutation pass over eval-003, the metrics export.

**Every mutant here produces files that open cleanly.** That is the shape of
the risk: this is the boundary between a computed figure and a quoted one,
and a defect in it does not crash, does not empty a file, and does not make
a number look odd. It makes a thesis table that is readable, plausible and
wrong -- or, worse, one that cannot be traced back to what produced it, which
nothing downstream can detect because there is nothing downstream.

Five surfaces, one per constraint the amendment settles.

**What reproduces a figure.** A seed reproduces the hours; a policy
reproduces the numbers. Disable the required-policy refusal and an export
that names its seeds and none of its thresholds passes -- satisfying the item
as first written while being unreproducible.

**Traceability.** The digest is only a traceability mechanism while it moves
with the record. Compute it over a subset, over a formatted string, or drop
it from the rows, and every file still looks self-describing while citing
nothing in particular.

**The blank cell.** `eval-002` is careful that a rate over nothing is `None`
and never 0.0. A CSV writes `None` as an empty cell, which is zero to every
tool that will open this, and the counts beside it are the only thing that
keeps the distinction. Render the blank as a zero, or drop a count column,
and the guarantee dies exactly here.

**Computing rather than re-organising.** Round a value, and the quoted
number and the computed number differ with no way to notice from either.

**Derived column names.** Rename a header by hand and `eval-002`'s
two-recalls guard evaporates at the one boundary it exists for.

Needs no database and no corpus -- the module reads neither -- so it runs the
suite directly rather than through Compose.

Run: `python measurements/mutation/mutate_eval003_export.py` from `backend/`.
"""

import ast
import json
import re
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
MODULE = BACKEND / "app/evaluation/export.py"
TESTS = ["tests/test_eval_export.py"]

M = {
    # --- what reproduces a figure --------------------------------------------
    "an export with no detector policies at all is accepted": (
        "        missing = [name for name in REQUIRED_POLICIES if name not in self.policies]",
        "        missing = []"),
    "only the policies that happen to be present are required": (
        "        missing = [name for name in REQUIRED_POLICIES if name not in self.policies]",
        "        missing = [name for name in self.policies if name not in REQUIRED_POLICIES]"),
    "the threshold is dropped from the required set": (
        '    "RF-NOISE.threshold_db",\n    "RF-NOISE.minimum_episode_s",',
        '    "RF-NOISE.minimum_episode_s",'),
    "the policies are recorded but not exported": (
        '            "policies": dict(sorted(self.policies.items())),',
        '            "policies": {},'),
    "a corpus with no base seed is accepted": (
        "        if not self.base_seeds:",
        "        if False:"),
    "a campaign with no population is accepted": (
        "        if not self.population:",
        "        if False:"),
    "a credential in the parameters is written to the file": (
        "            if _looks_like_a_credential(str(key)):",
        "            if False:"),

    # --- traceability ---------------------------------------------------------
    "the digest is taken over the corpus name alone": (
        '    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))',
        '    text = json.dumps(sorted(payload)[0], sort_keys=True)'),
    "the digest ignores the policies": (
        "    def as_json(self) -> dict[str, Any]:\n"
        "        record: dict[str, Any] = {\n"
        '            "corpus": self.corpus,\n'
        '            "base_seeds": list(self.base_seeds),\n'
        '            "runs": self.runs,\n'
        '            "measured_on": self.measured_on,\n'
        '            "policies": dict(sorted(self.policies.items())),\n'
        "        }\n"
        '        return {**record, "digest": _digest(record)}',
        "    def as_json(self) -> dict[str, Any]:\n"
        "        record: dict[str, Any] = {\n"
        '            "corpus": self.corpus,\n'
        '            "base_seeds": list(self.base_seeds),\n'
        '            "runs": self.runs,\n'
        '            "measured_on": self.measured_on,\n'
        '            "policies": dict(sorted(self.policies.items())),\n'
        "        }\n"
        '        return {**record, "digest": _digest({k: v for k, v in record.items() '
        'if k != "policies"})}'),
    "the seed order stops mattering": (
        '            "base_seeds": list(self.base_seeds),\n'
        '            "runs": self.runs,\n'
        '            "measured_on": self.measured_on,\n'
        '            "policies": dict(sorted(self.policies.items())),',
        '            "base_seeds": sorted(self.base_seeds),\n'
        '            "runs": self.runs,\n'
        '            "measured_on": self.measured_on,\n'
        '            "policies": dict(sorted(self.policies.items())),'),
    "the digest is not the first column": (
        '    columns: list[str] = ["source"]',
        '    columns: list[str] = []'),
    "the rows carry no digest at all": (
        "        tuple([source] + [record[key] for key in columns[1:]]) for record in records",
        "        tuple([\"\"] + [record[key] for key in columns[1:]]) for record in records"),
    "the provenance file resolves nothing because its digest differs": (
        "        digest = str(record[\"digest\"])",
        "        digest = str(record[\"digest\"])[:4]"),
    "the two records share one digest": (
        "    for name, record in sorted(records.items()):",
        "    for name, record in [(n, next(iter(records.values()))) "
        "for n in sorted(records)]:"),

    # --- the blank cell -------------------------------------------------------
    "an unmeasured rate is written as zero": (
        "    elif node is None:",
        "    elif node is None and False:"),
    "a rate is exported without the counts behind it": (
        "            absent = [c for c in (column, *counts) if c not in self.columns]",
        "            absent = []"),
    "only the rate itself has to be present, not its counts": (
        "            absent = [c for c in (column, *counts) if c not in self.columns]",
        "            absent = [c for c in (column,) if c not in self.columns]"),
    "the recall loses its denominator": (
        '    "recall_per_run": ("detected", "runs"),',
        '    "recall_per_run": ("detected",),'),
    "the per-aircraft recall is exported with no population declared": (
        '    "track_side_recall_per_staged_aircraft": (\n'
        '        "track_side_detected_aircraft",\n'
        '        "track_side_staged_aircraft",\n'
        "    ),",
        ""),
    "a record disagreeing about its own shape is blanked rather than refused": (
        "        tuple([source] + [record[key] for key in columns[1:]]) "
        "for record in records",
        '        tuple([source] + [record.get(key, "") for key in columns[1:]]) '
        "for record in records"),
    "a ragged row is written out": (
        "            if len(row) != len(self.columns):",
        "            if False:"),

    # --- computing rather than re-organising ----------------------------------
    "a value is rounded on the way out": (
        "    else:\n        out[name] = str(node)\n    return out",
        "    else:\n        out[name] = (str(round(node, 3)) if isinstance(node, float) "
        "else str(node))\n    return out"),
    "the type row recomputes its arm counts instead of copying them": (
        '        record["arm_runs"] = "" if arm is None else str(arm.runs)',
        '        record["arm_runs"] = "" if arm is None else str(arm.detected + arm.missed + 1)'),
    "the type row carries no arm counts, so F1 cannot be checked": (
        '        record["arm_detected"] = "" if arm is None else str(arm.detected)',
        '        record["arm_detected"] = ""'),
    "an arm's counts are taken from whichever arm sorts first": (
        "        arm = by_arm[arms_behind[0]] if len(arms_behind) == 1 else None",
        "        arm = by_arm[arms_behind[0]] if arms_behind else None"),

    # --- derived column names -------------------------------------------------
    "the per-run recall is renamed on the way out": (
        '    "recall_per_run": ("detected", "runs"),',
        '    "recall": ("detected", "runs"),'),
    "an absent nested record becomes a blank column of its own": (
        "            if filled.get(key) is None:",
        "            if False:"),
    "the shape of an absent record is guessed from one entry's keys": (
        "            if isinstance(value, Mapping):\n"
        "                shapes.setdefault(key, tuple(value))",
        "            if isinstance(value, Mapping):\n"
        "                shapes.setdefault(key, tuple(value)[:1])"),
    "the nested record's name is dropped from its columns": (
        '    return {k.replace(".", "_"): v for k, v in _flatten(node).items()}',
        '    return {k.rsplit(".", 1)[-1]: v for k, v in _flatten(node).items()}'),
    "the confusion matrix is exported wide": (
        '            {"staged": staged, "reported": reported, "runs": str(runs)}\n'
        "            for staged, row in sorted(exported[\"confusion\"].items())\n"
        "            for reported, runs in sorted(row.items())",
        '            {"staged": staged, **{k: str(v) for k, v in sorted(row.items())}}\n'
        "            for staged, row in sorted(exported[\"confusion\"].items())"),

    # --- the refusals ---------------------------------------------------------
    "figures are exported with no provenance": (
        "    if detection is not None and detection_provenance is None:",
        "    if False:"),
    "campaign figures are exported with no provenance": (
        "    if campaign is not None and campaign_provenance is None:",
        "    if False:"),
    "an empty export is produced rather than refused": (
        "    if detection is None and campaign is None:",
        "    if False:"),
    "provenance with nothing to describe is accepted": (
        "    if detection is None and detection_provenance is not None:",
        "    if False:"),
    "a file is written for a half that was not supplied": (
        "    if campaign is not None and campaign_provenance is not None:",
        "    if campaign_provenance is not None or True:"),
    "a blank model id is accepted": (
        "        if not self.model_id.strip():",
        "        if False:"),
    "a blank prompt digest is accepted": (
        "        if not self.prompt_digest.strip():",
        "        if False:"),
    "an unnamed corpus is accepted": (
        "        if not self.corpus.strip():",
        "        if False:"),
    "a measurement with no date is accepted": (
        '        if not self.measured_on.strip():\n'
        '            raise ExportError("no measurement date was recorded.")\n'
        "        missing =",
        '        if False:\n'
        '            raise ExportError("no measurement date was recorded.")\n'
        "        missing ="),
}

#: Mutants expected to survive, with the reason.
EXPECTED_EQUIVALENT: dict[str, str] = {}

RAN = re.compile(r"(\d+) (?:passed|failed)")
original = MODULE.read_text()

GUARD = Path(__file__).with_suffix(".in-progress.json")
if GUARD.exists():
    for name, text in json.loads(GUARD.read_text()).items():
        Path(name).write_text(text)
    GUARD.unlink()
    raise SystemExit(
        "a previous run did not finish and had left a mutant in the source. "
        "The original has been put back from the guard file. Check `git diff` "
        "is clean, then run again."
    )
GUARD.write_text(json.dumps({str(MODULE): original}))


def _suite() -> tuple[int, str, bool]:
    p = subprocess.run(
        [".venv/bin/python", "-m", "pytest", *TESTS,
         "-q", "--no-header", "-p", "no:cacheprovider", "--no-cov"],
        cwd=str(BACKEND), capture_output=True, text=True)
    tail = [line for line in p.stdout.splitlines()
            if "passed" in line or "failed" in line or "error" in line]
    summary = tail[-1] if tail else "NO TEST SUMMARY -- did the suite run?"
    return p.returncode, summary, bool(RAN.search(summary))


# --- the sentinel ---------------------------------------------------------
# A deliberately broken edit. If the suite stays green, edits are not
# reaching the tests and no score from this harness means anything.
_from = "        if not self.corpus.strip():"
assert original.count(_from) == 1
MODULE.write_text(original.replace(_from, "        if True:", 1))
_code, _summary, _ran = _suite()
MODULE.write_text(original)
if not _ran:
    GUARD.unlink(missing_ok=True)
    raise SystemExit(f"the suite did not run at all: {_summary}")
if not _code:
    GUARD.unlink(missing_ok=True)
    raise SystemExit(
        "SENTINEL SURVIVED. A deliberately broken source edit left the suite "
        f"green ({_summary}), so edits are not reaching the tests."
    )
print(f"sentinel killed ({_summary}) -- source edits reach the tests\n", flush=True)

res: dict[str, str] = {}
try:
    for n, (o, w) in M.items():
        if original.count(o) != 1:
            res[n] = f"INVALID ({original.count(o)})"
            print(f"{n:62} {res[n]}", flush=True)
            continue
        mutated = original.replace(o, w, 1)
        # A mutant that does not parse tests nothing: it is killed by a
        # syntax error rather than by a test, which scores a gap as a pass.
        try:
            ast.parse(mutated)
        except SyntaxError as broken:
            res[n] = f"INVALID (does not parse: {broken.msg})"
            print(f"{n:62} {res[n]}", flush=True)
            continue
        # A mutant identical to the original tests nothing either, and reads
        # as a survivor -- the sixth hazard in measurements/README.md.
        if mutated == original:
            res[n] = "INVALID (identical to the original)"
            print(f"{n:62} {res[n]}", flush=True)
            continue
        MODULE.write_text(mutated)
        code, summary, ran = _suite()
        res[n] = (f"INCONCLUSIVE -- {summary}" if not ran
                  else ("KILLED   " if code else "SURVIVED ") + summary)
        print(f"{n:62} {res[n]}", flush=True)
        MODULE.write_text(original)
finally:
    MODULE.write_text(original)
    GUARD.unlink(missing_ok=True)
    print("\nrestored")

killed = sum(1 for v in res.values() if v.startswith("KILLED"))
survived = [n for n, v in res.items() if v.startswith("SURVIVED")]
invalid = [n for n, v in res.items() if v.startswith("INVALID")]
unclear = [n for n, v in res.items() if v.startswith("INCONCLUSIVE")]
print(f"\n{killed} killed of {len(res) - len(invalid) - len(unclear)} valid mutants")
if invalid:
    print(f"INVALID (anchor did not match once, or the mutant does not parse): {invalid}")
if unclear:
    print(f"INCONCLUSIVE (no test summary): {unclear}")
unexpected = [n for n in survived if n not in EXPECTED_EQUIVALENT]
if unexpected:
    print("SURVIVED, and NOT expected to -- each one is a gap in the tests:")
    for n in unexpected:
        print(f"  - {n}")
else:
    print("no unexpected survivors")
