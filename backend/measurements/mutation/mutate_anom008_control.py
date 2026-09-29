"""Mutation pass over anom-008, the quiet-run control.

**Almost every mutant here leaves the control reporting that the quiet runs
were clean.** That is the failure mode the item is about: a control is the
one instrument whose broken state and whose correct state produce the same
output, because the answer it is looking for is *nothing*. A latency figure
that is wrong is at least a number somebody could sanity-check. A
false-positive rate of zero produced by a control that graded nothing looks
exactly like a false-positive rate of zero produced by a layer that behaved.

Four surfaces.

**The account.** The refusals are the item's own mechanism, not input
validation: with them disabled the control grades whatever it was handed and
reports a perfect quiet run for a pipeline that never ran. The inverted
difference is the subtle one -- `supplied - expected` refuses on a stray key
and lets a missing producer through, which is the same defect wearing the
appearance of a check.

**The band, which carries "zero fails".** Dropping the floor makes every
detector's silence acceptable and removes the only thing standing between
this control and a pipeline that stopped looking. Raising the RF floor does
the opposite and fails forty of forty correct runs -- the mistake the
measurement corrected, since the RF grid is synthetic and a quiet run has
nothing in it. Both directions are here.

**The reportable side.** A false positive that does not fail the control, a
verdict that inverts, and the boundary at zero.

**The rule that does not exist.** `anom-006` reported as clean rather than
not exercised, and the coverage count reading three of three. Either one
turns the absence of a rule into evidence of its accuracy, which is the
single most flattering thing this whole instrument could do.

Needs no database and no corpus -- the module reads neither -- so it runs
the suite directly rather than through Compose.

Run: `python measurements/mutation/mutate_anom008_control.py` from `backend/`.
"""

import ast
import json
import re
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
MODULE = BACKEND / "app/detection/control.py"
TESTS = ["tests/test_anom_control.py"]

M = {
    # --- the account: what makes silence insufficient ------------------------
    "a partial account is graded rather than refused": (
        "    missing = expected - supplied\n    if missing:",
        "    missing = expected - supplied\n    if False:"),
    "the difference runs the wrong way, so a missing producer passes": (
        "    missing = expected - supplied",
        "    missing = supplied - expected"),
    "an unregistered producer is graded": (
        "    unknown = supplied - set(register)\n    if unknown:",
        "    unknown = supplied - set(register)\n    if False:"),
    "counts from a rule with no implementation are accepted": (
        "    phantom = supplied & unbuilt\n    if phantom:",
        "    phantom = supplied & unbuilt\n    if False:"),
    "unbuilt producers are expected in the account too": (
        "    expected = {key for key, producer in register.items() if producer.built}",
        "    expected = set(register)"),
    "a negative count is accepted": (
        "        if observed < 0:",
        "        if False:"),

    # --- which runs this control will grade ----------------------------------
    "a staged run is graded as a quiet one": (
        "    if scenario_type != QUIET:",
        "    if False:"),
    "only staged runs are graded": (
        "    if scenario_type != QUIET:",
        "    if scenario_type == QUIET:"),

    # --- the band, which carries "zero fails" --------------------------------
    "the floor is dropped, so every detector's silence is acceptable": (
        "        return self.low <= observed <= self.high",
        "        return observed <= self.high"),
    "the ceiling is dropped, so drift is invisible": (
        "        return self.low <= observed <= self.high",
        "        return self.low <= observed"),
    "the floor stops belonging to the band": (
        "        return self.low <= observed <= self.high",
        "        return self.low < observed <= self.high"),
    "the ceiling stops belonging to the band": (
        "        return self.low <= observed <= self.high",
        "        return self.low <= observed < self.high"),
    "the RF floor is raised, failing forty of forty correct runs": (
        "            low=0,\n            high=0,\n            runs=40,\n"
        "            note=(\n                \"zero on 40 of 40, over two "
        "independently seeded batches. The RF \"",
        "            low=1,\n            high=1,\n            runs=40,\n"
        "            note=(\n                \"zero on 40 of 40, over two "
        "independently seeded batches. The RF \""),
    "the track floor drops to zero, so a silent detector passes": (
        "            low=8,\n            high=22,",
        "            low=0,\n            high=22,"),

    # --- the reportable side -------------------------------------------------
    "any number of reportable claims is clean": (
        "            outcome = Outcome.CLEAN if observed == 0 else Outcome.FALSE_POSITIVE",
        "            outcome = Outcome.CLEAN if observed >= 0 else Outcome.FALSE_POSITIVE"),
    "the reportable verdict inverts": (
        "            outcome = Outcome.CLEAN if observed == 0 else Outcome.FALSE_POSITIVE",
        "            outcome = Outcome.FALSE_POSITIVE if observed == 0 else Outcome.CLEAN"),
    "a false positive no longer fails the control": (
        "_FAILING = (Outcome.FALSE_POSITIVE, Outcome.OUTSIDE_BACKGROUND)",
        "_FAILING = (Outcome.OUTSIDE_BACKGROUND,)"),
    "a count outside the background no longer fails the control": (
        "_FAILING = (Outcome.FALSE_POSITIVE, Outcome.OUTSIDE_BACKGROUND)",
        "_FAILING = (Outcome.FALSE_POSITIVE,)"),
    "an unbuilt rule fails the control": (
        "_FAILING = (Outcome.FALSE_POSITIVE, Outcome.OUTSIDE_BACKGROUND)",
        "_FAILING = (Outcome.FALSE_POSITIVE, Outcome.OUTSIDE_BACKGROUND, "
        "Outcome.NOT_EXERCISED)"),
    "false_positives reports the wrong outcome": (
        "        return tuple(v for v in self.verdicts "
        "if v.outcome is Outcome.FALSE_POSITIVE)",
        "        return tuple(v for v in self.verdicts "
        "if v.outcome is Outcome.CLEAN)"),

    # --- the rule that does not exist ----------------------------------------
    "the absent rule is reported as clean": (
        "                Verdict(producer=producer, observed=None, "
        "outcome=Outcome.NOT_EXERCISED)",
        "                Verdict(producer=producer, observed=0, outcome=Outcome.CLEAN)"),
    "the absent rule is dropped from the register": (
        "    Producer(\n        rule_id=SOURCE_GAP_RULE,",
        "    Producer(\n        rule_id=FAULT_RULE,"),
    "coverage counts the rule that does not exist": (
        "            if v.producer.kind is Kind.REPORTABLE and v.producer.built",
        "            if v.producer.kind is Kind.REPORTABLE"),

    # --- the register's own guards -------------------------------------------
    "an intermediate producer may carry no band": (
        "        if self.kind is Kind.INTERMEDIATE and self.background is None:",
        "        if False:"),
    "a reportable producer may carry a band": (
        "        if self.kind is Kind.REPORTABLE and self.background is not None:",
        "        if False:"),
    "a band whose top is below its floor is accepted": (
        "        if self.high < self.low:",
        "        if False:"),
    "a band with no population behind it is accepted": (
        "        if self.runs < 1:",
        "        if False:"),
    "a producer registered twice silently replaces the first": (
        "        if producer.key in by_key:",
        "        if False:"),

    "the exported band loses the population behind it": (
        "            \"background\": None if band is None else "
        "[band.low, band.high, band.runs],",
        "            \"background\": None if band is None else [band.low, band.high],"),

    # --- the key -------------------------------------------------------------
    "the register is keyed on the rule alone": (
        "        by_key[producer.key] = producer",
        "        by_key[producer.rule_id] = producer"),
}

#: None. Every mutant above either lets a quiet run be graded on evidence
#: the control never saw, or changes what the false-positive figure means.
EXPECTED_EQUIVALENT: set[str] = set()

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
_from = "    if scenario_type != QUIET:"
assert original.count(_from) == 1
MODULE.write_text(original.replace(_from, "    if False:", 1))
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
        # Enforced here, as in `mutate_anom009_latency.py`.
        try:
            ast.parse(mutated)
        except SyntaxError as broken:
            res[n] = f"INVALID (does not parse: {broken.msg})"
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
