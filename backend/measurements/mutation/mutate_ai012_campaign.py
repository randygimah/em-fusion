"""Mutation pass over ai-012, the campaign run.

The worst place in this package for a weak suite, for the same reason
`ai-011` was and worse: **almost every mutant here still produces
hypotheses.** Nothing throws, every bundle gets an explanation, and the
damage is a row that was never written, a verdict attached to the wrong
thing, or a per-arm figure that is off by exactly the population nobody
thought to count. A campaign is also the one thing in this project that
cannot simply be re-run: it spends money and it is pre-registered.

Five surfaces.

**The lossy path.** Asking through `ai-003`'s `generate` instead of
`ai-007`'s recorded method is the defect this item was built around. It
answers every bundle correctly and silently drops the ungrounded attempts,
which are the rows the catch rate is made of.

**The verdict.** Written from the wrong report, to the wrong row, for the
wrong generation, or not at all. The interesting one is the *replacement*:
marking it PASSED claims a check that never ran, and `ai-007` deliberately
does not check what it falls back to.

**The count.** Re-checking the delivered hypothesis through the ledger-
attached checker counts every model generation twice and halves the reported
catch rate. Counting the replacement against the arm that was asked dilutes
the model arm's rate with template output, in the direction that makes the
arm look better the more often it failed. Both produce a complete, plausible
number.

**What is skipped against what stops.** Catching `BudgetExceeded` per bundle
makes the budget inert and finishes the campaign on template output while
every row reports itself as hosted -- the failure those two exceptions were
carved out of the `GenerationError` tree to prevent, one layer up from where
`ai-009` was worried about it. Aborting on an ordinary refusal throws away a
campaign that has already been paid for.

**The corpus.** Inventing a sample, accepting an empty one, or accepting the
same bundle twice. The first is the one that matters: the corpus is fixed
before the campaign runs, and a runner able to choose its own bundles could
choose them after seeing a result.

Drives `make test-backend-nobuild` from the repository root -- see
`mutate_db002_hypotheses.py` for why both halves of that are lessons rather
than detail, and run `make build-backend` once before a pass.
"""

import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # the repository root
BACKEND = ROOT / "backend"
MODULE = BACKEND / "app/ai/campaign.py"
ASSEMBLY = BACKEND / "app/ai/assembly.py"
#: **Two** suites, not one. `ai-011`'s typing is what lets the campaign ask
#: for the record at all, and the test that pins it lives in the assembly
#: suite -- so a mutant widening that annotation survived a pass that ran
#: only the campaign's own tests. A harness whose scope is narrower than the
#: thing it scores reports a gap where there is none.
TESTS = ["tests/test_ai_campaign.py", "tests/test_ai_assembly.py"]

M = {
    # --- the lossy path ------------------------------------------------------
    "the arm is asked through the port, dropping every refusal": (
        MODULE,
        "    outcome = arm.generator.generate_recorded(bundle)\n"
        "    seconds = time.monotonic() - started",
        "    outcome = arm.generator.generate_recorded(bundle)\n"
        "    outcome = type(outcome)(\n"
        "        result=arm.generator.generate(bundle), refusals=(), fell_back=False\n"
        "    )\n"
        "    seconds = time.monotonic() - started"),
    "the refused attempts are recorded but never stored": (
        MODULE,
        "    if refusal.result is not None:",
        "    if False:"),
    "a malformed attempt is given a row anyway": (
        MODULE,
        "    if refusal.result is not None:",
        "    if True:"),
    "the refusals are dropped from the record": (
        MODULE,
        "        refusals=refusals,\n"
        "        usage=outcome.result.call.usage if outcome.result.call else None,",
        "        refusals=(),\n"
        "        usage=outcome.result.call.usage if outcome.result.call else None,"),

    # --- the verdict ---------------------------------------------------------
    "the delivered hypothesis is never given a verdict": (
        MODULE,
        "    if not outcome.fell_back:",
        "    if False:"),
    "the replacement is marked as checked too": (
        MODULE,
        "    if not outcome.fell_back:",
        "    if True:"),
    "a failing verdict on a model answer is recorded as passing": (
        MODULE,
        "        grounding = GroundingStatus.PASSED if report.passed else "
        "GroundingStatus.FAILED",
        "        grounding = GroundingStatus.PASSED"),
    "the row's verdict is not written, only the record's": (
        MODULE,
        "        record_grounding(session_factory, hypothesis_id=row, report=report)\n"
        "        grounding = ",
        "        grounding = "),
    "the refused row's verdict is never written": (
        MODULE,
        "        record_grounding(\n"
        "            session_factory,\n"
        "            hypothesis_id=row,\n"
        "            report=check(refusal.result.hypothesis, bundle),\n"
        "        )",
        "        pass"),
    "the refused row's verdict is checked against the delivered hypothesis": (
        MODULE,
        "            report=check(refusal.result.hypothesis, bundle),",
        "            report=check(template_generate(bundle), bundle),"),
    "the baseline's verdict is never written to its row": (
        MODULE,
        "    report = grounding.report(result.hypothesis, bundle)\n"
        "    record_grounding(session_factory, hypothesis_id=row, report=report)",
        "    report = grounding.report(result.hypothesis, bundle)"),

    # --- the count -----------------------------------------------------------
    "the delivered hypothesis is re-checked through the ledger": (
        MODULE,
        "        report = check(outcome.result.hypothesis, bundle)",
        "        report = GroundingChecker(\n"
        "            arm=arm.arm, ledger=arm.ledger\n"
        "        ).report(outcome.result.hypothesis, bundle)"),
    "the replacement is counted against the arm that was asked": (
        MODULE,
        "    grounding = GroundingStatus.NOT_CHECKED\n"
        "    if not outcome.fell_back:",
        "    grounding = GroundingStatus.NOT_CHECKED\n"
        "    if outcome.fell_back:\n"
        "        GroundingChecker(arm=arm.arm, ledger=arm.ledger).report(\n"
        "            outcome.result.hypothesis, bundle\n"
        "        )\n"
        "    if not outcome.fell_back:"),
    "the baseline is checked without the ledger, so its rate is never populated": (
        MODULE,
        "    report = grounding.report(result.hypothesis, bundle)",
        "    report = check(result.hypothesis, bundle)"),
    "the baseline is counted against the hosted arm": (
        MODULE,
        "    baseline_check = GroundingChecker(arm=GeneratorKind.TEMPLATE, "
        "ledger=arm.ledger)",
        "    baseline_check = GroundingChecker(arm=arm.arm, ledger=arm.ledger)"),
    "the baseline gets a ledger of its own": (
        MODULE,
        "    baseline_check = GroundingChecker(arm=GeneratorKind.TEMPLATE, "
        "ledger=arm.ledger)",
        "    baseline_check = GroundingChecker(arm=GeneratorKind.TEMPLATE)"),
    "a flagged baseline raises instead of being recorded": (
        MODULE,
        "    report = grounding.report(result.hypothesis, bundle)",
        "    grounding(result.hypothesis, bundle)\n"
        "    report = check(result.hypothesis, bundle)"),

    # --- which arm was asked -------------------------------------------------
    "the model rows do not say which arm was asked": (
        MODULE,
        "        result=outcome.result,\n"
        "        requested_generator=arm.arm,",
        "        result=outcome.result,\n"
        "        requested_generator=outcome.result.generator,"),
    "the refused rows are attributed to the template": (
        MODULE,
        "            result=refusal.result,\n"
        "            requested_generator=arm,",
        "            result=refusal.result,\n"
        "            requested_generator=GeneratorKind.TEMPLATE,"),
    "the record reports the generator as the arm that was asked": (
        MODULE,
        "        requested_arm=arm.arm,\n"
        "        generator=outcome.result.generator,",
        "        requested_arm=outcome.result.generator,\n"
        "        generator=outcome.result.generator,"),
    "a fallback is never reported as one in the record": (
        MODULE,
        "        return self.generator is not self.requested_arm",
        "        return False"),

    # --- what is skipped, what stops ----------------------------------------
    "a budget exhaustion is skipped like any other failure": (
        MODULE,
        "            except (BudgetExceeded, ConfigurationError) as stopped:",
        "            except (KeyboardInterrupt,) as stopped:"),
    "only the budget stops the run, a misconfiguration is skipped": (
        MODULE,
        "            except (BudgetExceeded, ConfigurationError) as stopped:",
        "            except (BudgetExceeded,) as stopped:"),
    "an ordinary refusal stops the whole campaign": (
        MODULE,
        "            except GenerationError as failed:\n"
        "                # Recorded and skipped. The remaining generations for this",
        "            except _NeverRaised as failed:\n"
        "                # Recorded and skipped. The remaining generations for this"),
    "a skipped generation is swallowed rather than recorded": (
        MODULE,
        "                skipped.append(\n"
        "                    SkippedGeneration(\n"
        "                        bundle_id=bundle_id,\n"
        "                        ordinal=ordinal,",
        "                if False:\n"
        "                    skipped.append(\n"
        "                    SkippedGeneration(\n"
        "                        bundle_id=bundle_id,\n"
        "                        ordinal=ordinal,"),
    "an abort hands back nothing of what it had done": (
        MODULE,
        "                    record=so_far(),\n"
        "                    cause=stopped,",
        "                    record=CampaignRecord(\n"
        "                        generations=(), skipped=(), budget=arm.budget.report(),\n"
        "                        ledger=arm.ledger),\n"
        "                    cause=stopped,"),
    "a skipped baseline is not recorded": (
        MODULE,
        "                    requested_arm=GeneratorKind.TEMPLATE,\n"
        "                    reason=str(failed) or type(failed).__name__,",
        "                    requested_arm=GeneratorKind.TEMPLATE,\n"
        "                    reason=\"\","),
    "the abort does not say which of the two stopped it": (
        MODULE, "        self.cause = cause", "        self.cause = None"),

    # --- the corpus, and what it is asked --------------------------------------
    "an empty sample is accepted": (
        MODULE, "    if not sample:", "    if False:"),
    "the same bundle twice is accepted": (
        MODULE, "        if bundle_id in seen:", "        if False:"),
    "zero generations is accepted": (
        MODULE, "    if generations < 1:", "    if False:"),
    "the configured number of generations is ignored": (
        MODULE,
        "        for ordinal in range(1, generations + 1):",
        "        for ordinal in range(1, 2):"),
    # Written twice. The first version indented the `try:` by two spaces
    # under a new `for`, which left the `except` clause below it stranded --
    # an IndentationError, scored INCONCLUSIVE rather than surviving. A
    # mutant that does not parse tests nothing, and this is the second time
    # that has happened in this directory. Write mutants against the
    # **formatted** source and check they parse.
    "the baseline is asked once per model generation": (
        MODULE,
        "        try:\n"
        "            made.append(\n"
        "                _baseline_generation(\n"
        "                    session_factory,\n"
        "                    bundle_id=bundle_id,\n"
        "                    bundle=bundle,\n"
        "                    baseline=baseline,\n"
        "                    grounding=baseline_check,\n"
        "                )\n"
        "            )",
        "        try:\n"
        "            for _ in range(generations):\n"
        "                made.append(\n"
        "                    _baseline_generation(\n"
        "                        session_factory,\n"
        "                        bundle_id=bundle_id,\n"
        "                        bundle=bundle,\n"
        "                        baseline=baseline,\n"
        "                        grounding=baseline_check,\n"
        "                    )\n"
        "                )"),
    "the ordinal is the same for every generation": (
        MODULE, "        ordinal=ordinal,\n        requested_arm=arm.arm,",
        "        ordinal=1,\n        requested_arm=arm.arm,"),

    # --- the artefact ---------------------------------------------------------
    "a catch rate of nothing over nothing is reported as zero": (
        MODULE,
        '                    "catch_rate": self.ledger.catch_rate(arm),',
        '                    "catch_rate": self.ledger.catch_rate(arm) or 0.0,'),
    "only the arms that ran are reported": (
        MODULE,
        "                for arm in GeneratorKind",
        "                for arm in GeneratorKind if self.ledger.checked(arm)"),
    "the record is serialised without the skipped generations": (
        MODULE,
        '            "skipped": [\n'
        "                {\n"
        '                    "bundle_id": skipped.bundle_id,',
        '            "skipped": [\n'
        "                {\n"
        '                    "bundle_id": skipped.bundle_id,'),
    "the budget total does not say whether it is complete": (
        MODULE,
        '                "cost_is_complete": self.budget.cost_is_complete,',
        '                "cost_is_complete": True,'),

    # --- ai-011's typing, which is what lets any of this be asked for --------
    "the assembled arm is typed loosely again": (
        ASSEMBLY,
        "    generator: CorrectnessFallback",
        "    generator: object"),
}

#: Mutants expected to survive. Each is an honest equivalence with its
#: argument written out, so a survivor list of this length is not read as
#: that many weak tests -- and so a later reader does not re-litigate them.
EXPECTED_EQUIVALENT = {
    # A no-op rewrite: the replacement text is identical to the original.
    # The harness's own control -- a KILLED here would mean the scoring is
    # wrong, not that a test is strong.
    "the record is serialised without the skipped generations",
    # **Equivalent, and the pass is what established it.** The branch only
    # runs when the arm did *not* fall back, and through an assembled arm a
    # non-fallback delivery is one `ai-007`'s injected checker has already
    # passed -- `assemble_arm` always wires a `GroundingChecker`, the gate
    # raises on anything it flags, and `check` is a pure function of the
    # same two arguments. So `report.passed` cannot be false there and the
    # mutant cannot be distinguished by behaviour.
    #
    # The derivation stays anyway rather than being simplified to the
    # constant the mutant proves it equals, because writing PASSED here
    # would encode another module's invariant as an assumption in this one,
    # and the whole reason this module re-derives the verdict is that a
    # verdict inferred from "nothing raised" is not a verdict.
    "a failing verdict on a model answer is recorded as passing",
}

RAN = re.compile(r"(\d+) (?:passed|failed)")

originals = {path: path.read_text() for path in {p for p, _, _ in M.values()}}

GUARD = Path(__file__).with_suffix(".in-progress.json")
if GUARD.exists():
    for name, text in json.loads(GUARD.read_text()).items():
        Path(name).write_text(text)
    GUARD.unlink()
    raise SystemExit(
        "a previous run did not finish and had left a mutant in the source. "
        "The originals have been put back from the guard file. Check "
        "`git diff` is clean, then run again."
    )
GUARD.write_text(json.dumps({str(k): v for k, v in originals.items()}))


def _suite() -> tuple[int, str, bool]:
    p = subprocess.run(
        ["make", "test-backend-nobuild",
         f"PYTEST_ARGS={' '.join(TESTS)} -q --no-cov"],
        cwd=str(ROOT), capture_output=True, text=True, env=os.environ.copy())
    tail = [line for line in p.stdout.splitlines()
            if "passed" in line or "failed" in line or "error" in line]
    summary = tail[-1] if tail else "NO TEST SUMMARY -- did the suite run?"
    return p.returncode, summary, bool(RAN.search(summary))


# --- the sentinel ---------------------------------------------------------
_from = "    if not sample:"
_original = originals[MODULE]
assert _original.count(_from) == 1
MODULE.write_text(_original.replace(_from, "    if False:", 1))
_code, _summary, _ran = _suite()
MODULE.write_text(_original)
if not _ran:
    GUARD.unlink(missing_ok=True)
    raise SystemExit(f"the suite did not run at all: {_summary}")
if not _code:
    GUARD.unlink(missing_ok=True)
    raise SystemExit(
        "SENTINEL SURVIVED. A deliberately broken source edit left the suite "
        f"green ({_summary}), so edits are not reaching the tests and no score "
        "from this harness can be believed."
    )
print(f"sentinel killed ({_summary}) -- source edits reach the tests\n", flush=True)

res: dict[str, str] = {}
try:
    for n, (path, o, w) in M.items():
        orig = originals[path]
        if orig.count(o) != 1:
            res[n] = f"INVALID ({orig.count(o)})"
            print(f"{n:66} {res[n]}", flush=True)
            continue
        path.write_text(orig.replace(o, w, 1))
        code, summary, ran = _suite()
        if not ran:
            res[n] = f"INCONCLUSIVE -- {summary}"
        else:
            res[n] = ("KILLED   " if code else "SURVIVED ") + summary
        print(f"{n:66} {res[n]}", flush=True)
        path.write_text(orig)
finally:
    for path, text in originals.items():
        path.write_text(text)
    GUARD.unlink(missing_ok=True)
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
