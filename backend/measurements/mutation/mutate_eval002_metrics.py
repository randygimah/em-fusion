"""Mutation pass over eval-002, the detection metrics.

**The failure mode here is a report that is readable and wrong.** Every
mutant below leaves a full results table: five arm rows, three type rows,
two false-positive rates, a confusion matrix and a latency figure. Nothing
raises, nothing is empty, and the numbers are plausible. This is the last
module in the detection chain and the first whose defects are invisible to
anything downstream, because there is nothing downstream -- what it prints
is what the write-up quotes.

Six surfaces, one per constraint the item's amendment settles.

**What each figure is indexed by.** Recall's denominator is the runs of a
scenario type and precision's is the runs given an anomaly type. Swapping
one for the other produces two numbers that are right on a corpus where no
arm is ever confused for another and wrong exactly where the confusion this
item exists to measure begins.

**The two recalls.** `anom-011`'s is per staged aircraft, this one is per
run, and they differ by more than twenty points. A mutant that merges them,
or that exports either under a bare `recall`, is the write-up defect the
mechanical guard was built for.

**A wrong answer is two errors.** Counting a misreport only as a miss, or
only as a false alarm, halves the cost of exactly the error a multi-class
problem exists to price.

**The two false-positive rates.** Pooling them destroys the cross-modal
one, which is the test the quiet arm cannot make. Reporting the cross-modal
rate as controlled borrows an assurance `anom-008` never gave it.

**The control guard.** With it disabled, a false-positive rate of zero
computed over quiet runs whose detectors never ran is indistinguishable
from one computed over a layer that behaved -- `anom-008`'s own argument,
one item along and now load-bearing for a published figure.

**None over an empty population.** A 0.0 where nothing was measured is the
value that reads as a measured failure, and it is the item's named
divide-by-zero failure case wearing the appearance of an answer.

Needs no database and no corpus -- the module reads neither -- so it runs
the suite directly rather than through Compose.

Run: `python measurements/mutation/mutate_eval002_metrics.py` from `backend/`.
"""

import ast
import json
import re
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
MODULE = BACKEND / "app/evaluation/metrics.py"
TESTS = ["tests/test_eval_metrics.py"]

M = {
    # --- what each figure is indexed by --------------------------------------
    "recall indexed by prediction rather than by truth": (
        "        return _rate(self.detected, self.runs)",
        "        return _rate(self.detected, self.detected + self.missed + 1)"),
    "precision indexed by truth rather than by prediction": (
        "        return _rate(self.correct, self.claimed_runs)",
        "        return _rate(self.correct, self.correct + self.wrong + self.wrong)"),
    "a claim is credited to the arm that made it rather than the one staged": (
        "    correct = [run for run in claimed "
        "if STAGED_TYPE[run.scenario_type] == anomaly_type]",
        "    correct = list(claimed)"),
    "the false negative rate is the recall rather than its complement": (
        "        return None if recall is None else 1.0 - recall",
        "        return None if recall is None else recall"),

    # --- the two recalls ------------------------------------------------------
    "the run-level recall is exported under a bare key": (
        '            "recall_per_run": self.recall_per_run,',
        '            "recall": self.recall_per_run,'),
    "the track-side recall is exported under a bare key": (
        '            "recall_per_staged_aircraft": self.recall_per_staged_aircraft,',
        '            "recall": self.recall_per_staged_aircraft,'),
    "the two recalls are averaged into one figure": (
        "        if self.kind is not ArmKind.POSITIVE:\n            return None\n"
        "        return _rate(self.detected, self.runs)",
        "        if self.kind is not ArmKind.POSITIVE:\n            return None\n"
        "        per_run = _rate(self.detected, self.runs)\n"
        "        if per_run is None or self.track_side is None:\n"
        "            return per_run\n"
        "        other = self.track_side.recall_per_staged_aircraft\n"
        "        return per_run if other is None else (per_run + other) / 2"),
    "a per-aircraft recall is accepted for an arm that stages nothing": (
        "        if STAGED_TYPE[scenario_type] is None:",
        "        if False:"),

    # --- a wrong answer is two errors ----------------------------------------
    "a misreport is a miss but not a false alarm": (
        "    claimed = [run for run in scored if anomaly_type in run.reported]",
        "    claimed = [run for run in scored if anomaly_type in run.reported "
        "and STAGED_TYPE[run.scenario_type] == anomaly_type]"),
    "a misreport is a false alarm but not a miss": (
        "        detections = [r for r in runs if r.detected] "
        "if kind is ArmKind.POSITIVE else []",
        "        detections = [r for r in runs if r.reported] "
        "if kind is ArmKind.POSITIVE else []"),
    "a run claiming two types is counted once": (
        "        for predicted in run.reported or (SILENT,):",
        "        for predicted in run.reported[:1] or (SILENT,):"),
    "a run claiming two types is not flagged": (
        "        multi_claim_runs=sum(1 for run in scored if len(run.reported) > 1),",
        "        multi_claim_runs=0,"),

    # --- F1 only where one arm maps to one type ------------------------------
    "F1 is emitted where two arms produce one type": (
        "        arm_recall_per_run=("
        "by_arm[arms[0]].recall_per_run if len(arms) == 1 else None),",
        "        arm_recall_per_run=("
        "by_arm[arms[0]].recall_per_run if arms else None),"),
    "the contradiction behind that is accepted rather than refused": (
        "        if self.arm_recall_per_run is not None and len(self.arms) != 1:",
        "        if False:"),
    "F1 over an unmeasured half is zero rather than absent": (
        "        return precision is not None and recall is not None "
        "and precision + recall > 0",
        "        return True"),
    "F1 over a precision and a recall of zero divides by zero": (
        "and precision + recall > 0",
        "and precision + recall >= 0"),
    "the arms behind a type include the one with no rule": (
        "            if staged == anomaly_type and anomaly_type in built",
        "            if staged == anomaly_type"),

    # --- the two false-positive rates ----------------------------------------
    "the cross-modal arm is dropped, leaving one pooled-looking rate": (
        "        if arm_kind(scenario_type, register=register) is ArmKind.POSITIVE:\n"
        "            continue",
        "        if scenario_type != QUIET:\n            continue"),
    "the cross-modal rate claims a control it never had": (
        "                controlled=scenario_type == QUIET,",
        "                controlled=True,"),
    "a silent arm's reports are counted per claim rather than per run": (
        "                runs_with_a_report=sum(1 for r in runs if r.reported),",
        "                runs_with_a_report=sum(len(r.reported) for r in runs),"),
    "the coverage figure counts the rule that does not exist": (
        "                reportable_types_covered=len(built),",
        "                reportable_types_covered=len(types),"),

    # --- the control guard ----------------------------------------------------
    "a failing control does not stop the rate being computed": (
        "        if not control.holds:",
        "        if False:"),
    "an ungraded quiet run is scored": (
        "    ungraded = sorted(quiet - set(controls))",
        "    ungraded = sorted(set(controls) - quiet)"),
    "a control for a run outside the population is accepted": (
        "        if run_id not in quiet:",
        "        if False:"),
    "a control filed under the wrong run is accepted": (
        "        if control.run_id != run_id:",
        "        if False:"),

    # --- exclusions and the vocabulary ---------------------------------------
    "a staged-type run that staged nothing is scored": (
        "        target = excluded if "
        "(run.scenario_type != QUIET and not run.staged) else scored",
        "        target = scored"),
    "an intermediate finding counts as reportable output": (
        "        unknown = [t for t in run.reported if t not in allowed]",
        "        unknown = []"),
    "a duplicated run is weighted twice": (
        "        if run.run_id in seen:",
        "        if False:"),
    "an unknown scenario type is scored as if it were a sixth arm": (
        "        if self.scenario_type not in STAGED_TYPE:",
        "        if False:"),
    "a quiet run that claims to have staged something is scored": (
        "        if self.scenario_type == QUIET and self.staged:",
        "        if False:"),

    # --- latency conditional on detection -------------------------------------
    "latency is taken over the arm rather than over its detections": (
        "        measured = [\n"
        "            r.latency_seconds for r in detections "
        "if r.latency_seconds is not None\n        ]",
        "        measured = [\n"
        "            r.latency_seconds for r in runs "
        "if r.latency_seconds is not None\n        ]"),
    "a detection carrying no latency is invisible": (
        "                    detections=len(detections),",
        "                    detections=len(measured),"),
    "latency stops saying what population it is conditional on": (
        '            "conditional_on": "detections",',
        '            "conditional_on": "runs",'),
    "a negative latency is clamped to zero": (
        "                    min_seconds=min(measured) if measured else None,",
        "                    min_seconds=max(0.0, min(measured)) if measured else None,"),
    "a latency is accepted on a run that produced no matching claim": (
        "            if truth is None or truth not in self.reported:",
        "            if False:"),

    # --- None over an empty population ---------------------------------------
    "an unjudged arm reports a recall of zero rather than none": (
        "        if self.kind is not ArmKind.POSITIVE:\n            return None",
        "        if self.kind is not ArmKind.POSITIVE:\n            return 0.0"),
    "an arm that stages nothing a built rule judges is scored as positive": (
        "    return ArmKind.POSITIVE if staged in _built_types(register) "
        "else ArmKind.UNJUDGED",
        "    return ArmKind.POSITIVE"),
    "a table omits the arms nobody generated": (
        "    for scenario_type in sorted(STAGED_TYPE):\n"
        "        runs = [r for r in scored if r.scenario_type == scenario_type]",
        "    for scenario_type in sorted({r.scenario_type for r in scored}):\n"
        "        runs = [r for r in scored if r.scenario_type == scenario_type]"),
    "the type with no rule is dropped from the table rather than listed": (
        "        sorted({p.finding_type for p in register.values() "
        "if p.kind is Kind.REPORTABLE})",
        "        sorted({p.finding_type for p in register.values() "
        "if p.kind is Kind.REPORTABLE and p.built})"),
    "a track side detecting more than was staged is accepted": (
        "        if self.detected_aircraft > self.staged_aircraft:",
        "        if False:"),
    "an empty corpus produces a report of every rate absent": (
        "    if not scored and not excluded:",
        "    if False:"),
}

#: Mutants expected to survive, with the reason.
EXPECTED_EQUIVALENT: dict[str, str] = {
    "latency is taken over the arm rather than over its detections": (
        "Equivalent, and the reason is the design: `RunOutcome` refuses a "
        "latency on a run that produced no claim of the type it staged, so "
        "the runs of an arm carrying a latency are exactly its detections "
        "and the two spellings select the same rows. The guard that makes "
        "them the same has its own mutant above, which dies -- which is "
        "where that constraint is actually held."
    ),
}

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
_from = "        if self.scenario_type not in STAGED_TYPE:"
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
