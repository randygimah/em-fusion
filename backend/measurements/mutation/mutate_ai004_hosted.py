"""Mutation pass over ai-004, the hosted arm.

Four surfaces, and they fail in different ways.

**The payload.** This is what leaves the machine, and the measurement that
closed the data-egress gate describes it. Every mutant here still sends a
plausible document; what changes is whether the model saw the evidence it
was asked to reason from, or whether our bookkeeping went out with it.
Neither is visible in a generated hypothesis.

**The prompt.** The experiment's largest variable. A deleted binding rule
produces output that still validates and still reads well, and the defect
surfaces as a scoring difference nobody can attribute.

**The narrowed schema.** `ai-001` warns that a derivation which widened
confidence to a free string would pass every test written against the
Python model and lose the guarantee at the only boundary relying on it.
Several mutants do exactly that, and several others remove the narrowing
entirely -- which would be rejected by the live API and is invisible here,
so the tests have to hold the shape themselves.

**The adapter's error taxonomy.** The dangerous one. Mapping a rejected
request to a refusal makes `ai-007` retry it and then produce template
output for every bundle while the run reports itself as hosted; widening
the unavailable tuple does the same through `ai-006`. Both are campaigns
run against the wrong arm with no symptom until the results are compared.

Driven from the repository root; the summary reports how many tests ran,
not only the exit code.
"""

import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # the repository root
BACKEND = ROOT / "backend"
PAYLOAD = BACKEND / "app/ai/payload.py"
PROMPT = BACKEND / "app/ai/prompt.py"
ADAPTER = BACKEND / "app/ai/providers/openai.py"
REGISTRY = BACKEND / "app/ai/registry.py"
TESTS = "tests/test_ai_hosted.py"

M = {
    # --- what leaves the machine -------------------------------------------
    "the citable coordinates are not sent": (
        PAYLOAD, '        "refs": [dict(ref) for ref in item.refs],', ""),
    "a rule's own details are not sent": (
        PAYLOAD, '        "details": dict(item.details),', ""),
    "rejected claims are withheld": (
        PAYLOAD,
        '        "superseded": [\n'
        "            {\n"
        '                "rule_id": c.rule_id,',
        '        "superseded": [\n'
        "            {\n"
        '                "rule_id": None,'),
    "the recorded uncertainties are not sent": (
        PAYLOAD, '        "known_uncertainties": [', '        "unused_key": ['),
    "the frequency axis is not sent": (
        PAYLOAD, '        "affected_channels": list(bundle.affected_channels),',
        '        "affected_channels": [],'),
    "the run id goes out with the evidence": (
        PAYLOAD, 'BUNDLE_EXCLUDED = frozenset({"scenario_run_id"})',
        "BUNDLE_EXCLUDED = frozenset()"),
    "the resolved row ids go out with the evidence": (
        PAYLOAD, 'ITEM_EXCLUDED = frozenset({"observation_ids"})',
        "ITEM_EXCLUDED = frozenset()"),
    "a time is sent as an object rather than a string": (
        PAYLOAD, '"started_at": item.started_at.isoformat(),',
        '"started_at": item.started_at,'),
    "an enum is sent as the enum rather than its value": (
        PAYLOAD, '"data_mode": item.data_mode.value,', '"data_mode": item.data_mode,'),
    "every bundle serialises to the same bytes": (
        PAYLOAD, "    return json.dumps(bundle_payload(bundle), ensure_ascii=False)",
        '    return json.dumps({"anomaly_type": bundle.anomaly_type})'),

    # --- the instructions ---------------------------------------------------
    "the rule about rejected claims is deleted": (
        PROMPT,
        "3. The superseded list holds explanations the system considered and \\\n"
        "REJECTED.",
        "3. The superseded list holds earlier notes. \\\n"),
    "confidence is no longer restricted in the instructions": (
        PROMPT, "4. Confidence is Low, Medium or High", "4. Confidence is a judgement"),
    "the citation rule loses the pair": (
        PROMPT, "that appears in the package's evidence list, copied exactly.",
        "that is relevant, described in your own words."),
    "the pseudonym rule is deleted": (
        PROMPT, "7. Aircraft identifiers are pseudonyms.",
        "7. Aircraft identifiers are labels."),
    "the alternatives floor is removed": (
        PROMPT, "5. alternative_explanations must contain at least one genuine entry.",
        "5. alternative_explanations may be filled in where useful."),
    "the fingerprint is a constant rather than a derivation": (
        PROMPT, '    return hashlib.sha256(HYPOTHESIS_PROMPT.encode("utf-8")).hexdigest()',
        '    return "0" * 64'),

    # --- the narrowed schema ------------------------------------------------
    "the narrowing removes nothing": (
        ADAPTER, "        if key in UNSUPPORTED_BY_STRICT_MODE:",
        "        if False:"),
    "the narrowing does not report what it removed": (
        ADAPTER, "    return _narrow(hypothesis_json_schema(), dropped), tuple(sorted(dropped))",
        "    return _narrow(hypothesis_json_schema(), dropped), ()"),
    "the unsupported set forgets the list floor": (
        ADAPTER, '        "minItems",\n', ""),
    "the narrowing also removes the confidence enum": (
        ADAPTER, "UNSUPPORTED_BY_STRICT_MODE = frozenset(\n    {\n",
        'UNSUPPORTED_BY_STRICT_MODE = frozenset(\n    {\n        "enum",\n'),
    "the narrowing also removes required": (
        ADAPTER, "UNSUPPORTED_BY_STRICT_MODE = frozenset(\n    {\n",
        'UNSUPPORTED_BY_STRICT_MODE = frozenset(\n    {\n        "required",\n'),
    "the narrowing also removes additionalProperties": (
        ADAPTER, "UNSUPPORTED_BY_STRICT_MODE = frozenset(\n    {\n",
        'UNSUPPORTED_BY_STRICT_MODE = frozenset(\n    {\n        "additionalProperties",\n'),

    # --- the model id, pinned and dated -------------------------------------
    "a moving alias is accepted": (
        ADAPTER, "        if not _DATED_MODEL.search(model_id):", "        if False:"),
    "the dated pattern matches anything": (
        ADAPTER, '_DATED_MODEL = re.compile(r"-\\d{4}-\\d{2}-\\d{2}$")',
        '_DATED_MODEL = re.compile(r".*")'),
    "an arm with no model at all is accepted": (
        ADAPTER, "        if model_id is None:", "        if False:"),

    # --- the request ---------------------------------------------------------
    "the schema is sent unnarrowed": (
        ADAPTER, "        schema, _ = strict_schema()",
        "        schema = hypothesis_json_schema()"),
    "the generation is not constrained at all": (
        ADAPTER, '                        "strict": True,', '                        "strict": False,'),
    "the instructions are not sent": (
        ADAPTER, '{"role": "system", "content": HYPOTHESIS_PROMPT},',
        '{"role": "system", "content": "Explain this."},'),
    "the bundle is not sent": (
        ADAPTER, '{"role": "user", "content": payload_json(bundle)},',
        '{"role": "user", "content": "{}"},'),
    "the frozen parameters do not reach the request": (
        ADAPTER, "                **dict(self.config.parameters),\n            )",
        "            )"),

    # --- provenance ----------------------------------------------------------
    "the prompt fingerprint is not recorded": (
        ADAPTER, '                "prompt_sha256": prompt_fingerprint(),', ""),
    "a caller may supply its own fingerprint": (
        ADAPTER, '        if "prompt_sha256" in config.parameters:', "        if False:"),
    "the response is re-serialised rather than stored verbatim": (
        ADAPTER, "            raw_response=raw,",
        "            raw_response=json.dumps(json.loads(raw)),"),
    "the configured parameters are not recorded": (
        ADAPTER, "                **dict(self.config.parameters),\n"
                 '                "prompt_sha256": prompt_fingerprint(),',
        '                "prompt_sha256": prompt_fingerprint(),'),

    # --- the error taxonomy, which is the dangerous surface ------------------
    "a rejected request is treated as a bad answer": (
        ADAPTER,
        "            raise ConfigurationError(\n"
        '                f"the provider rejected the request itself: {rejected}.',
        "            raise GenerationRefused(\n"
        '                f"the provider rejected the request itself: {rejected}.'),
    "only a timeout counts as unreachable": (
        ADAPTER, "        except _UNAVAILABLE as unavailable:",
        "        except openai.APITimeoutError as unavailable:"),
    "a rate limit is treated as a misconfiguration": (
        ADAPTER, "    openai.RateLimitError,\n", ""),
    "the model declining to answer is ignored": (
        ADAPTER, '        if getattr(message, "refusal", None):', "        if False:"),
    "an empty answer is accepted": (
        ADAPTER, '        if not raw.strip():\n            raise GenerationRefused(\n'
                 '                "the provider returned an empty response.',
        '        if False:\n            raise GenerationRefused(\n'
                 '                "the provider returned an empty response.'),
    "every refusal is reported as structural": (
        ADAPTER, "        if _constraint_only(invalid):", "        if False:"),
    "no refusal is reported as structural": (
        ADAPTER, "        if _constraint_only(invalid):", "        if True:"),
    "a refused call carries nothing it paid for": (
        ADAPTER, "                call=call,\n            ) from broken",
        "                call=None,\n            ) from broken"),

    # --- cost, which ai-009's ceiling depends on -----------------------------
    "an unpriced call is reported as free": (
        ADAPTER, "            return None\n        return (\n"
                 "            prompt_tokens / 1000 * self.usd_per_1k_prompt",
        "            return 0.0\n        return (\n"
                 "            prompt_tokens / 1000 * self.usd_per_1k_prompt"),
    "the completion rate is applied to the prompt": (
        ADAPTER, "            prompt_tokens / 1000 * self.usd_per_1k_prompt",
        "            prompt_tokens / 1000 * self.usd_per_1k_completion"),
    "token counts are not recorded": (
        ADAPTER, '        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)',
        "        prompt_tokens = 0"),

    # --- the credential ------------------------------------------------------
    "an absent credential is accepted": (
        ADAPTER, "    if not key:", "    if False:"),

    # --- the registry --------------------------------------------------------
    "the arm is not registered": (
        REGISTRY, '    "openai": OpenAIGenerator,\n', ""),
}

EXPECTED_EQUIVALENT: set[str] = set()

RAN = re.compile(r"(\d+) (?:passed|failed)")

#: Originals, written to disk before the first mutant and removed on a
#: clean exit. The `finally` below restores the source on any ordinary
#: failure -- but it does NOT survive a SIGKILL, and this pass was killed
#: mid-run by the OOM killer, leaving a mutant sitting in the working tree
#: looking exactly like ordinary uncommitted work. One test was red and the
#: cause was three steps away. So the next invocation heals it and says so.
GUARD = Path(__file__).with_suffix(".in-progress.json")

if GUARD.exists():
    for name, text in json.loads(GUARD.read_text()).items():
        Path(name).write_text(text)
    GUARD.unlink()
    raise SystemExit(
        "A previous run of this harness was killed before it could restore the "
        "source. The originals have been put back from the guard file. Check "
        "`git diff` and run again."
    )

originals = {path: path.read_text() for path in {p for p, _, _ in M.values()}}
GUARD.write_text(json.dumps({str(k): v for k, v in originals.items()}))
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
