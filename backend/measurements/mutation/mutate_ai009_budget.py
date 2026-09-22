"""Mutation pass over ai-009, the run-level call budget.

A spending guard fails in a particularly quiet way. Every mutant below
still produces hypotheses, still returns results, and still reports a
number when asked what the run spent. What changes is whether the number is
right and whether the guard is there at all -- and neither is visible from
the output of a successful run.

Four families.

**The ceiling, off by one or absent.** The item's whole purpose. A budget
that permits one extra call per run is a rounding error; a budget that
checks *after* recording rather than before permits N-1 calls and looks
like an off-by-one in the other direction; a budget that never checks is a
budget-shaped object. None of them raises.

**The two ceilings conflated.** The spec amendment is about these being
different instruments -- one checkable before a call, one only after, one
always available and one inert on an arm that reports no cost. Mutants move
the call check to after the call and the cost check to before, which is the
mistake the implementation actually made on its first draft.

**Exhaustion becoming a generation failure.** Reparenting `BudgetExceeded`
under `GenerationError` makes `ai-007` catch it, so the run finishes on
template output while reporting itself as hosted. The most expensive
possible defect here and the one with no symptom.

**The ledger, quietly wrong.** A refused call not counted, an unreachable
call priced, an unpriced call treated as free rather than unknown, an arm
attributed to whichever result came back. Each produces a plausible number
that `eval-005` would report as a result.

Driven from the repository root; the summary reports how many tests ran,
not only the exit code. See the README's hazard note.
"""

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # the repository root
BACKEND = ROOT / "backend"
MODULE = BACKEND / "app/ai/budget.py"
TESTS = "tests/test_ai_budget.py"

M = {
    # --- the ceiling itself -------------------------------------------------
    "one more call than the ceiling allows": (
        MODULE, "        if report.call_count >= self.max_calls:",
        "        if report.call_count > self.max_calls:"),
    "the call ceiling is never checked": (
        MODULE, "        if report.call_count >= self.max_calls:",
        "        if False:"),
    "a ceiling of zero calls is accepted": (
        MODULE, "        if max_calls < 1:", "        if max_calls < 0:"),
    "the ceiling is not validated at all": (
        MODULE, "        if max_calls < 1:", "        if False:"),
    "the recommended ceiling drifts": (
        MODULE, "RECOMMENDED_MAX_CALLS = 200", "RECOMMENDED_MAX_CALLS = 2000"),
    "the refusal does not name the ceiling": (
        MODULE,
        'f"ceiling of {self.max_calls}, so this one is refused before "',
        '"a ceiling, so this one is refused before "'),

    # --- the two ceilings conflated, which is the amendment's whole subject --
    "the call ceiling is checked after the call instead of before": (
        MODULE, "        self.budget.approve()\n        try:",
        "        try:"),
    "a spend ceiling of nothing is accepted": (
        MODULE, "        if max_cost_usd is not None and max_cost_usd <= 0:",
        "        if max_cost_usd is not None and max_cost_usd < 0:"),
    "the spend ceiling is never checked": (
        MODULE,
        "        if self.max_cost_usd is not None and report.spent_usd >= self.max_cost_usd:",
        "        if False:"),
    "the spend ceiling fires one call early": (
        MODULE,
        "        if self.max_cost_usd is not None and report.spent_usd >= self.max_cost_usd:",
        "        if self.max_cost_usd is not None and report.spent_usd > self.max_cost_usd:"),
    "an absent spend ceiling is treated as zero": (
        MODULE,
        "        if self.max_cost_usd is not None and report.spent_usd >= self.max_cost_usd:",
        "        if report.spent_usd >= (self.max_cost_usd or 0):"),

    # --- exhaustion becoming a generation failure ---------------------------
    "budget exhaustion is catchable as a generation failure": (
        MODULE, "class BudgetExceeded(RuntimeError):",
        "class BudgetExceeded(GenerationError):"),
    "an arm returning another arm's result is a generation failure": (
        MODULE,
        "        if result.generator is not self.arm:\n"
        "            raise ConfigurationError(",
        "        if result.generator is not self.arm:\n"
        "            raise GenerationRefused("),
    "the abort carries no ledger": (
        MODULE, "        raise BudgetExceeded(message, report=report)",
        "        raise BudgetExceeded(message, report=self.report())"),

    # --- the ledger, quietly wrong ------------------------------------------
    "a refused call is not counted": (
        MODULE,
        "            self.budget.record(self.arm, CallOutcome.REFUSED, refused.call)\n"
        "            raise",
        "            raise"),
    "a refused call's tokens are discarded": (
        MODULE, "            self.budget.record(self.arm, CallOutcome.REFUSED, refused.call)",
        "            self.budget.record(self.arm, CallOutcome.REFUSED, None)"),
    "an unreachable call is not counted": (
        MODULE,
        "            self.budget.record(self.arm, CallOutcome.UNREACHABLE, None)\n"
        "            raise",
        "            raise"),
    "a served call is not counted": (
        MODULE, "        self.budget.record(self.arm, CallOutcome.SERVED, result.call)",
        "        pass"),
    "an unpriced call is counted as free rather than unknown": (
        MODULE,
        "            if r.call is not None and r.call.usage.cost_usd is None\n"
        "        )",
        "            if False\n        )"),
    "a total over unpriced calls is declared complete": (
        MODULE, "        return self.unpriced_calls == 0", "        return True"),
    "the unpriced call still adds to the total as zero": (
        MODULE,
        "            r.call.usage.cost_usd\n"
        "            for r in self.calls\n"
        "            if r.call is not None and r.call.usage.cost_usd is not None",
        "            (r.call.usage.cost_usd or 0.0)\n"
        "            for r in self.calls\n"
        "            if r.call is not None"),
    "prompt and completion tokens are swapped": (
        MODULE, "        return sum(r.call.usage.prompt_tokens for r in self.calls if r.call)",
        "        return sum(r.call.usage.completion_tokens for r in self.calls if r.call)"),

    # --- attribution, which eval-005 reports per arm ------------------------
    "the arm is read from the result rather than declared": (
        MODULE, "        if result.generator is not self.arm:", "        if False:"),
    "every call is attributed to the same arm": (
        MODULE, "        return tuple(r for r in self.calls if r.arm is arm)",
        "        return tuple(self.calls)"),
    "ordinals restart rather than running through the run": (
        MODULE, "                ordinal=len(self._calls) + 1, arm=arm, outcome=outcome, call=call",
        "                ordinal=1, arm=arm, outcome=outcome, call=call"),

    # --- the records, and the report that must not move ---------------------
    "an ordinal below one is accepted": (
        MODULE, "        if self.ordinal < 1:", "        if False:"),
    "a call may be attributed to the template": (
        MODULE, "        if self.arm is GeneratorKind.TEMPLATE:", "        if False:"),
    "an unreachable call may carry a model call": (
        MODULE,
        "        if self.outcome is CallOutcome.UNREACHABLE and self.call is not None:",
        "        if False:"),
    "a served call may carry no model call": (
        MODULE,
        "        if self.outcome is CallOutcome.SERVED and self.call is None:",
        "        if False:"),
    "the template may be given a budget": (
        MODULE, "        if arm is GeneratorKind.TEMPLATE:", "        if False:"),
    "the ledger is handed out as the live list": (
        MODULE, '        object.__setattr__(self, "calls", tuple(self.calls))',
        "        pass"),
    "the report is a view rather than a snapshot": (
        MODULE, "            calls=tuple(self._calls),", "            calls=self._calls,"),

    # --- logging, which is all an aborted run leaves behind -----------------
    "the abort is logged below error": (
        MODULE, "        _LOG.error(", "        _LOG.debug("),
}

#: Survivors proven equivalent rather than left as gaps. Each was checked
#: by hand against the source, and two of the three say something the
#: module did not know about itself.
EXPECTED_EQUIVALENT = {
    # `_abort` is handed the report its caller already built and then raises
    # with one it builds itself. Nothing mutates the ledger between the two,
    # and BudgetReport is a frozen dataclass compared by value, so the two
    # objects differ in identity and in nothing observable. A wasteful
    # mutant rather than a behavioural one.
    "the abort carries no ledger",
    # Summing only the priced calls, and summing every call with None read
    # as 0.0, produce the same number -- necessarily, since the excluded
    # terms are exactly the ones that would have contributed zero. Worth
    # recording rather than dismissing: it proves the honest-total claim is
    # NOT carried by spent_usd at all. "Unpriced" and "free" are separated
    # entirely by unpriced_calls and cost_is_complete, and a reader who
    # quoted the total alone would be unable to tell them apart. That is
    # the argument for the companion flag, measured.
    "the unpriced call still adds to the total as zero",
    # Equivalent ONLY because another guard covers it: BudgetReport's
    # __post_init__ coerces `calls` to a tuple whatever it is handed, so
    # handing it the live list changes nothing. The same shape as evb-002's
    # covered survivor -- but note the cover is **one-directional**, which
    # this pass measured rather than assumed. Deleting the __post_init__
    # coercion IS caught, because a test constructs a report from a list
    # directly and the report site never runs; deleting the report site is
    # not. So they are not two guards making each other redundant, which is
    # what it looks like from the source: one is load-bearing and the other
    # states an intent at the place the sharing would occur. Both kept.
    "the report is a view rather than a snapshot",
}

RAN = re.compile(r"(\d+) (?:passed|failed)")

originals = {path: path.read_text() for path in {p for p, _, _ in M.values()}}
res: dict[str, str] = {}
try:
    for n, (path, o, w) in M.items():
        orig = originals[path]
        if orig.count(o) != 1:
            res[n] = f"INVALID ({orig.count(o)})"
            print(f"{n:62} {res[n]}", flush=True)
            continue
        path.write_text(orig.replace(o, w, 1))
        p = subprocess.run(
            ["make", "test-backend", f"PYTEST_ARGS={TESTS} -q --no-cov"],
            cwd=str(ROOT), capture_output=True, text=True, env=os.environ.copy())
        tail = [line for line in p.stdout.splitlines()
                if "passed" in line or "failed" in line or "error" in line]
        summary = tail[-1] if tail else "NO TEST SUMMARY -- did the suite run?"
        ran = bool(RAN.search(summary))
        if not ran:
            res[n] = f"INCONCLUSIVE -- {summary}"
        else:
            res[n] = ("KILLED   " if p.returncode else "SURVIVED ") + summary
        print(f"{n:62} {res[n]}", flush=True)
        path.write_text(orig)
finally:
    for path, text in originals.items():
        path.write_text(text)
    print("\nrestored")

killed = sum(1 for v in res.values() if v.startswith("KILLED"))
survived = [n for n, v in res.items() if v.startswith("SURVIVED")]
invalid = [n for n, v in res.items() if v.startswith("INVALID")]
unclear = [n for n, v in res.items() if v.startswith("INCONCLUSIVE")]
print(f"\n{killed} killed of {len(res) - len(invalid) - len(unclear)} valid mutants")
if invalid:
    print(f"INVALID (the anchor did not match exactly once): {invalid}")
if unclear:
    print(f"INCONCLUSIVE (no test summary -- the suite may not have run): {unclear}")
unexpected = [n for n in survived if n not in EXPECTED_EQUIVALENT]
if unexpected:
    print("SURVIVED, and NOT expected to -- each one is a gap in the tests:")
    for n in unexpected:
        print(f"  - {n}")
else:
    print("no unexpected survivors")
