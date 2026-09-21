"""Mutation pass over ai-007, the correctness fallback.

This item is two guarantees wearing one coat, and the mutants are chosen
to separate them.

**The ceiling is about money.** A loop bug is the realistic route to an
unexpected bill -- not the campaign, which is pennies -- so several sites
here move the bound by one, remove it, or admit a value that makes it
meaningless. None of them raises. An off-by-one ceiling is a 50% overspend
that no test asserting "it eventually stopped" would notice.

**The record is about what a row means afterwards.** A mechanical
explanation that arrived because the model failed and one that arrived
because the template was the configured arm are the same row unless this
layer says otherwise, so the mutants that matter most are the quiet ones:
a fallback reported as a success, a refusal recorded under the wrong
category, a refused call whose tokens disappear.

**And one family is the item's central risk.** `ai-006` and `ai-007` end
at the same destination and fire for opposite reasons, which is what makes
merging them easy. Three mutants widen the caught exception from
`GenerationRefused` to its parent or to `Exception` -- each of which turns
an unreachable provider into a template hypothesis and reports it as a
model failure. If those survive, the distinction `ai-003` made
*expressible* is not being *observed*, and the write-up's claim that the
two fallbacks are separate paths rests on nothing.

Driven from the repository root: two harnesses here once ran `make` from
`backend/`, where the target does not exist, and scored every mutant
KILLED without a test having run. The summary reports how many tests ran.
"""

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # the repository root
BACKEND = ROOT / "backend"
MODULE = BACKEND / "app/ai/fallback.py"
SERVICE = BACKEND / "app/ai/service.py"
TESTS = "tests/test_ai_fallback.py"

M = {
    # --- the ceiling, which is the spend guard -----------------------------
    "one more attempt than configured": (
        MODULE, "for attempt in range(1, self.max_attempts + 1):",
        "for attempt in range(1, self.max_attempts + 2):"),
    "one fewer attempt than configured": (
        MODULE, "for attempt in range(1, self.max_attempts + 1):",
        "for attempt in range(1, self.max_attempts):"),
    "a ceiling of zero is accepted": (
        MODULE, "        if max_attempts < 1:", "        if max_attempts < 0:"),
    "the ceiling is not validated at all": (
        MODULE, "        if max_attempts < 1:", "        if False:"),
    "the ceiling message does not name the value": (
        MODULE, 'f"a correctness fallback configured for {max_attempts} "',
        '"a correctness fallback configured for too few "'),
    "a fallback may be its own primary": (
        MODULE, "        if fallback is primary:", "        if False:"),
    "the first refusal gives up instead of retrying": (
        MODULE,
        "                        attempt, RefusalCategory.MALFORMED, refused, result=None\n"
        "                    )\n"
        "                )\n"
        "                continue",
        "                        attempt, RefusalCategory.MALFORMED, refused, result=None\n"
        "                    )\n"
        "                )\n"
        "                break"),
    "an ungrounded answer is never retried": (
        MODULE,
        "                            attempt, RefusalCategory.UNGROUNDED, refused, result=result\n"
        "                        )\n"
        "                    )\n"
        "                    continue",
        "                            attempt, RefusalCategory.UNGROUNDED, refused, result=result\n"
        "                        )\n"
        "                    )\n"
        "                    break"),

    # --- the two fallbacks, merged. The item's central risk ----------------
    "an unreachable provider is caught as a bad answer": (
        MODULE,
        "            try:\n"
        "                result = self.primary.generate(bundle)\n"
        "            except GenerationRefused as refused:",
        "            try:\n"
        "                result = self.primary.generate(bundle)\n"
        "            except GenerationError as refused:"),
    "anything at all is caught as a bad answer": (
        MODULE,
        "            try:\n"
        "                result = self.primary.generate(bundle)\n"
        "            except GenerationRefused as refused:",
        "            try:\n"
        "                result = self.primary.generate(bundle)\n"
        "            except Exception as refused:"),
    "the check's failures are caught too broadly": (
        MODULE,
        "                    self.check(result.hypothesis, bundle)\n"
        "                except GenerationRefused as refused:",
        "                    self.check(result.hypothesis, bundle)\n"
        "                except Exception as refused:"),

    # --- the grounding check ------------------------------------------------
    "the injected check is never run": (
        MODULE, "            if self.check is not None:", "            if False:"),
    "the check is run whether or not one was given": (
        MODULE, "            if self.check is not None:", "            if True:"),

    # --- whether a fallback happened, which is what the row means ----------
    "a model answer is reported as a fallback": (
        MODULE, "                result=result, refusals=tuple(refusals), fell_back=False",
        "                result=result, refusals=tuple(refusals), fell_back=True"),
    "a template replacement is reported as a model answer": (
        MODULE, "            result=replacement, refusals=tuple(refusals), fell_back=True",
        "            result=replacement, refusals=tuple(refusals), fell_back=False"),
    "the port's own method always returns the template": (
        MODULE, "        return self.generate_recorded(bundle).result",
        "        return self.fallback.generate(bundle)"),
    "a fallback may be claimed with nothing behind it": (
        MODULE, "        if self.fell_back and not self.refusals:", "        if False:"),
    "the trail is left as the list it was built from": (
        MODULE, '        object.__setattr__(self, "refusals", tuple(self.refusals))',
        "        pass"),

    # --- the record, and the categories it must keep apart ------------------
    "the two categories share a spelling": (
        MODULE, '    MALFORMED = "malformed"', '    MALFORMED = "ungrounded"'),
    "an attempt number below one is accepted": (
        MODULE, "        if self.attempt < 1:", "        if False:"),
    "attempts are numbered from two": (
        MODULE, "            attempt=attempt,", "            attempt=attempt + 1,"),
    "a refusal with no reason is accepted": (
        MODULE, "        if not self.reason.strip():", "        if False:"),
    "the reason is a constant rather than the refusal's words": (
        MODULE, "                str(refused).strip()", '                "refused"'),
    "an ungrounded refusal may discard what it refused": (
        MODULE,
        "        if self.category is RefusalCategory.UNGROUNDED:\n"
        "            if self.result is None:",
        "        if self.category is RefusalCategory.UNGROUNDED:\n"
        "            if False:"),
    "a malformed refusal may carry a result": (
        MODULE, "        elif self.result is not None:", "        elif False:"),
    "an ungrounded refusal may carry a second copy of its call": (
        MODULE, "            if self.refused_call is not None:", "            if False:"),

    # --- every call countable, which is ai-009's whole basis ----------------
    "a refused generation's call is thrown away here": (
        MODULE, "            refused_call=None if result is not None else refused.call,",
        "            refused_call=None,"),
    "a refused generation's call is never recorded at all": (
        SERVICE, "        self.call = call", "        self.call = None"),
    "the call is read from the wrong side of the absence": (
        MODULE,
        "        return self.refused_call if self.result is None else self.result.call",
        "        return self.refused_call"),

    # --- the last resort, and what it surfaces with ------------------------
    "a template refusal loses the model refusal that summoned it": (
        MODULE, "            raise failed from last", "            raise failed from None"),

    # --- logging, which is a malformed answer's only record ----------------
    "the per-refusal log is demoted below warning": (
        MODULE,
        '        _LOG.warning(\n            "%s refused attempt %d of %d as %s: %s",',
        '        _LOG.debug(\n            "%s refused attempt %d of %d as %s: %s",'),
    "falling back to the template is not logged": (
        MODULE,
        '        _LOG.warning(\n            "%s exhausted %d attempt(s) on this bundle; falling back to the "',
        '        _LOG.debug(\n            "%s exhausted %d attempt(s) on this bundle; falling back to the "'),
}

EXPECTED_EQUIVALENT: set[str] = set()

RAN = re.compile(r"(\d+) (?:passed|failed)")

originals = {path: path.read_text() for path in {p for p, _, _ in M.values()}}
res: dict[str, str] = {}
try:
    for n, (path, o, w) in M.items():
        orig = originals[path]
        if orig.count(o) != 1:
            res[n] = f"INVALID ({orig.count(o)})"
            print(f"{n:58} {res[n]}", flush=True)
            continue
        path.write_text(orig.replace(o, w, 1))
        p = subprocess.run(
            ["make", "test-backend", f"PYTEST_ARGS={TESTS} -q --no-cov"],
            cwd=str(ROOT), capture_output=True, text=True, env=os.environ.copy())
        tail = [line for line in p.stdout.splitlines()
                if "passed" in line or "failed" in line or "error" in line]
        summary = tail[-1] if tail else "NO TEST SUMMARY -- did the suite run?"
        # A non-zero exit alone is not evidence a test noticed anything.
        ran = bool(RAN.search(summary))
        if not ran:
            res[n] = f"INCONCLUSIVE -- {summary}"
        else:
            res[n] = ("KILLED   " if p.returncode else "SURVIVED ") + summary
        print(f"{n:58} {res[n]}", flush=True)
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
