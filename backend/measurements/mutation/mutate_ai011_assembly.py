"""Mutation pass over ai-011, run assembly, and ai-003's forwarding.

Composition code is the worst place in this package for a test suite to be
weak, because almost every mutant here still produces hypotheses. Nothing
throws, nothing looks wrong, and the damage is in a bill, in a per-arm
column, or in a reported result nobody can re-derive afterwards.

Four surfaces.

**The nesting.** Budget outside the fallback instead of inside counts one
call per bundle and misses every retry -- the only failure `ai-009` names.
Both arrangements answer. Only a test that scripts a refusal and counts the
calls can tell them apart, so the mutant is here to prove one exists.

**The arm.** Hard-coding it, or reading it from the wrong place, attributes
spend to one arm and grounding catches to another. Every figure still comes
back; each is in the wrong column. `ai-009`'s own declaration guard catches
some of these for us, which is worth seeing rather than assuming.

**The refusals.** Each is a configuration that runs perfectly and reports
something false: a spend ceiling with nothing to enforce it against, a
campaign with no model identity on any row, a price of zero read as free.

**The forwarding.** Dropping the prices is invisible at every point except
the one that matters, and is the defect `ai-011` found in `ai-003` in the
first place.

Run in the repository's own virtualenv -- see `mutate_ai004_hosted.py` for
why, why it is valid for a file with no `database` marker, and the sentinel
that makes it safe.
"""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
SRC = BACKEND / "app/ai/assembly.py"
REGISTRY = BACKEND / "app/ai/registry.py"
TESTS = "tests/test_ai_assembly.py"

PYTEST = [
    str(BACKEND / ".venv/bin/python"),
    "-m",
    "pytest",
    "-q",
    "--no-cov",
    "-p",
    "no:cacheprovider",
]

M = {
    # --- the nesting --------------------------------------------------------
    "the budget wraps the fallback instead of the other way round": (
        SRC,
        "    generator = CorrectnessFallback(\n"
        "        # Budget inside, fallback outside. See the module note: the other\n"
        "        # way round counts one call per bundle and misses every retry.\n"
        "        BudgetedGenerator(inner, budget, arm=arm),\n"
        "        # Never budgeted. It makes no call, and counting a fallback against\n"
        "        # a model budget would abort a run for doing the safe thing.\n"
        "        replacement,\n"
        "        check=GroundingChecker(arm=arm, ledger=ledger),\n"
        "        max_attempts=max_attempts,\n"
        "    )",
        "    generator = BudgetedGenerator(\n"
        "        CorrectnessFallback(\n"
        "            inner,\n"
        "            replacement,\n"
        "            check=GroundingChecker(arm=arm, ledger=ledger),\n"
        "            max_attempts=max_attempts,\n"
        "        ),\n"
        "        budget,\n"
        "        arm=arm,\n"
        "    )"),
    "the arm is not budgeted at all": (
        SRC,
        "        BudgetedGenerator(inner, budget, arm=arm),",
        "        inner,"),
    "the template replacement is budgeted too": (
        SRC,
        "        replacement,\n"
        "        check=GroundingChecker(arm=arm, ledger=ledger),",
        "        BudgetedGenerator(replacement, budget, arm=arm),\n"
        "        check=GroundingChecker(arm=arm, ledger=ledger),"),
    "the arm is its own fallback": (
        SRC,
        "        replacement,\n"
        "        check=GroundingChecker(arm=arm, ledger=ledger),",
        "        BudgetedGenerator(inner, budget, arm=arm),\n"
        "        check=GroundingChecker(arm=arm, ledger=ledger),"),
    "no grounding check is wired in": (
        SRC,
        "        check=GroundingChecker(arm=arm, ledger=ledger),",
        "        check=None,"),
    "the retry ceiling is ignored and a fixed one used": (
        SRC,
        "        max_attempts=max_attempts,",
        "        max_attempts=2,"),

    # --- the arm ------------------------------------------------------------
    "the grounding checker is hard-coded to the hosted arm": (
        SRC,
        "        check=GroundingChecker(arm=arm, ledger=ledger),",
        "        check=GroundingChecker(arm=GeneratorKind.HOSTED, ledger=ledger),"),
    "the budgeted wrapper is hard-coded to the hosted arm": (
        SRC,
        "        BudgetedGenerator(inner, budget, arm=arm),",
        "        BudgetedGenerator(inner, budget, arm=GeneratorKind.HOSTED),"),
    "the checker is given no ledger": (
        SRC,
        "        check=GroundingChecker(arm=arm, ledger=ledger),",
        "        check=GroundingChecker(arm=arm),"),
    "the checker is given a ledger of its own": (
        SRC,
        "        check=GroundingChecker(arm=arm, ledger=ledger),",
        "        check=GroundingChecker(arm=arm, ledger=GroundingLedger()),"),
    "a budget of its own is created per arm": (
        SRC,
        "        BudgetedGenerator(inner, budget, arm=arm),",
        "        BudgetedGenerator(inner, CallBudget(\n"
        "            max_calls=budget.max_calls, max_cost_usd=budget.max_cost_usd\n"
        "        ), arm=arm),"),
    "the result reports an arm other than the one built": (
        SRC,
        "        arm=arm,\n        config=config,",
        "        arm=GeneratorKind.HOSTED,\n        config=config,"),

    # --- the refusals -------------------------------------------------------
    "the template may be assembled as the arm": (
        SRC,
        "    if arm is GeneratorKind.TEMPLATE:",
        "    if False:"),
    "a model arm may be assembled with no model id": (
        SRC,
        "    if model_id is None:",
        "    if False:"),
    "a spend ceiling with no prices is accepted": (
        SRC,
        "    if budget.max_cost_usd is not None and prices is None:",
        "    if False:"),
    "a spend ceiling is refused even when prices are given": (
        SRC,
        "    if budget.max_cost_usd is not None and prices is None:",
        "    if budget.max_cost_usd is not None:"),
    "prices are refused when no spend ceiling is set": (
        SRC,
        "    if budget.max_cost_usd is not None and prices is None:",
        "    if budget.max_cost_usd is None and prices is None:"),
    "the spend-ceiling refusal does not say prices are missing": (
        SRC,
        '            f"a spend ceiling of {budget.max_cost_usd} was set and no prices "\n'
        '            "were given. Cost is estimated from prices supplied at "',
        '            f"a spend ceiling of {budget.max_cost_usd} is not usable here. "\n'
        '            "Cost is estimated at "'),
    "the spend-ceiling refusal does not say what goes wrong": (
        SRC,
        '            "ceiling is never approached and it enforces nothing while "',
        '            "ceiling is never approached while "'),
    "a price of zero is accepted": (
        SRC,
        "            if value <= 0:",
        "            if value < 0:"),
    "a negative price is accepted": (
        SRC,
        "            if value <= 0:",
        "            if False:"),
    "only the prompt price is validated": (
        SRC,
        '            ("usd_per_1k_completion", self.usd_per_1k_completion),\n',
        ""),

    # --- the prices, and ai-003's forwarding ---------------------------------
    "the prices never reach the arm": (
        SRC,
        "    inner = build_generator(config, providers, **construction)",
        "    inner = build_generator(config, providers)"),
    "the completion price is not forwarded": (
        SRC,
        '        construction["usd_per_1k_completion"] = prices.usd_per_1k_completion',
        ""),
    "the two prices are forwarded the wrong way round": (
        SRC,
        '        construction["usd_per_1k_prompt"] = prices.usd_per_1k_prompt\n'
        '        construction["usd_per_1k_completion"] = prices.usd_per_1k_completion',
        '        construction["usd_per_1k_prompt"] = prices.usd_per_1k_completion\n'
        '        construction["usd_per_1k_completion"] = prices.usd_per_1k_prompt'),
    "absent prices are forwarded as zero rather than omitted": (
        SRC,
        "    construction: dict[str, Any] = {}\n"
        "    if prices is not None:",
        "    construction: dict[str, Any] = {\n"
        '        "usd_per_1k_prompt": 0.0, "usd_per_1k_completion": 0.0}\n'
        "    if prices is not None:"),
    "the prices are put into the generation parameters": (
        SRC,
        "    config = GenerationConfig(\n"
        "        provider=provider, model_id=model_id, parameters=dict(parameters)\n"
        "    )",
        "    config = GenerationConfig(\n"
        "        provider=provider, model_id=model_id,\n"
        "        parameters={**dict(parameters), **(\n"
        '            {"usd_per_1k_prompt": prices.usd_per_1k_prompt}\n'
        "            if prices is not None else {})},\n"
        "    )"),
    "the template factory is given the prices too": (
        SRC,
        "    replacement = build_generator(\n"
        "        GenerationConfig(provider=TEMPLATE_PROVIDER, model_id=None), providers\n"
        "    )",
        "    replacement = build_generator(\n"
        "        GenerationConfig(provider=TEMPLATE_PROVIDER, model_id=None), providers,\n"
        "        **construction,\n"
        "    )"),
    "the registry drops the construction keywords": (
        REGISTRY,
        "    return factory(config, **construction)",
        "    return factory(config)"),
    "the registry stops refusing an unknown name": (
        REGISTRY,
        "        factory = available[config.provider]",
        "        factory = available.get(config.provider, next(iter(available.values())))"),

    # --- the configuration ---------------------------------------------------
    "the parameters are dropped": (
        SRC,
        "        provider=provider, model_id=model_id, parameters=dict(parameters)",
        "        provider=provider, model_id=model_id, parameters={}"),
    "the provider name is ignored and the template used": (
        SRC,
        "        provider=provider, model_id=model_id, parameters=dict(parameters)",
        "        provider=TEMPLATE_PROVIDER, model_id=model_id, "
        "parameters=dict(parameters)"),
    "the replacement is given the arm's model id": (
        SRC,
        "        GenerationConfig(provider=TEMPLATE_PROVIDER, model_id=None), providers",
        "        GenerationConfig(provider=TEMPLATE_PROVIDER, model_id=model_id), "
        "providers"),
    "the replacement is built outside the injected registry": (
        SRC,
        "    replacement = build_generator(\n"
        "        GenerationConfig(provider=TEMPLATE_PROVIDER, model_id=None), providers\n"
        "    )",
        "    from app.ai.providers.template import TemplateGenerator\n"
        "    replacement = TemplateGenerator(\n"
        "        GenerationConfig(provider=TEMPLATE_PROVIDER, model_id=None)\n"
        "    )"),
    "the reported configuration is not the one used": (
        SRC,
        "        arm=arm,\n        config=config,",
        "        arm=arm,\n        config=GenerationConfig(\n"
        '            provider=provider, model_id=model_id, parameters={}),'),
    "the budget reported back is not the one wired in": (
        SRC,
        "        generator=generator,\n        budget=budget,",
        "        generator=generator,\n        budget=CallBudget(\n"
        "            max_calls=budget.max_calls, max_cost_usd=budget.max_cost_usd),"),
}

EXPECTED_EQUIVALENT: set[str] = set()

originals = {SRC: SRC.read_text(), REGISTRY: REGISTRY.read_text()}

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


def run_suite() -> tuple[int, str, bool]:
    proc = subprocess.run(
        [*PYTEST, TESTS], cwd=BACKEND, capture_output=True, text=True
    )
    lines = [
        line.strip()
        for line in proc.stdout.splitlines()
        if "passed" in line or "failed" in line or "error" in line
    ]
    summary = lines[-1] if lines else "NO TEST SUMMARY -- did the suite run?"
    return proc.returncode, summary, ("passed" in summary or "failed" in summary)


# --- the sentinel ---------------------------------------------------------
_sentinel_from = "        check=GroundingChecker(arm=arm, ledger=ledger),"
_sentinel_original = originals[SRC]
SRC.write_text(_sentinel_original.replace(_sentinel_from, "        check=None,", 1))
_code, _summary, _ran = run_suite()
SRC.write_text(_sentinel_original)
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
            print(f"{n:62} {res[n]}", flush=True)
            continue
        path.write_text(orig.replace(o, w, 1))
        code, summary, ran = run_suite()
        if not ran:
            res[n] = f"INCONCLUSIVE -- {summary}"
        else:
            res[n] = ("KILLED   " if code else "SURVIVED ") + summary
        print(f"{n:62} {res[n]}", flush=True)
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
