"""Mutation pass over ai-003, the provider-agnostic hypothesis interface.

An interface is mostly *refusals*, and a refusal that stops refusing is the
quietest defect there is: everything that used to work still works, and one
new thing is now permitted. Nearly every site below removes a refusal or
widens one rather than breaking anything, for the same reason the `ai-001`
pass did -- this is a schema by another name.

Three families, and they fail in different directions.

**The typed absence.** The migration made the four reproducibility columns
nullable and deferred the guarantee to the repository boundary; this item
moved it to where the result is made. Remove either half of that check and
a model arm can hand back a result with no model id and no raw response,
which is discovered after a campaign, when the response that would have
explained a grounding failure is the thing that was never recorded.

**The credential guard.** It has two failure directions and both matter.
Loosened, a key is written into the database once per hypothesis.
Tightened, it starts refusing `max_tokens` -- and a guard that blocks the
parameter a campaign must freeze is a guard somebody switches off, which is
worse than not having one.

**The seam itself.** A registry that defaults an unknown name, an adapter
that swallows a refusal, a template adapter that accepts a model id. None
of these raises anything. Each produces a perfectly ordinary result that is
attributed to the wrong arm, and the campaign has no way to notice.

Mutates three files, like the `evb-002` pass: the interface, the registry
and the one shipped adapter. A single-file pass over the interface alone
would leave the two places the interface is actually used untested.
"""

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
SERVICE = ROOT / "app/ai/service.py"
REGISTRY = ROOT / "app/ai/registry.py"
ADAPTER = ROOT / "app/ai/providers/template.py"
T = "tests/test_ai_service.py"
PY_BIN = os.environ.get("PY_BIN", str(ROOT / ".venv/bin/python"))

M = {
    # --- the typed absence: db-002's guarantee, moved earlier --------------
    "a model arm may omit its model call": (
        SERVICE,
        "        if self.generator is not GeneratorKind.TEMPLATE and self.call is None:",
        "        if False:"),
    "a template result may carry a model call": (
        SERVICE,
        "        if self.generator is GeneratorKind.TEMPLATE and self.call is not None:",
        "        if False:"),
    "the absence is checked for the template only, not for both arms": (
        SERVICE,
        "        if self.generator is not GeneratorKind.TEMPLATE and self.call is None:",
        "        if self.generator is GeneratorKind.HOSTED and self.call is None:"),
    "a model call may record an empty raw response": (
        SERVICE, "        if not self.raw_response.strip():", "        if False:"),
    "a raw response of pure whitespace counts as recorded": (
        SERVICE,
        "        if not self.raw_response.strip():",
        "        if not self.raw_response:"),
    "a model call may carry a blank model id": (
        SERVICE, "        if not self.model_id.strip():", "        if False:"),
    "a generator kind the database would refuse is added": (
        SERVICE, '    LOCAL = "local"', '    LOCAL = "local"\n    MOCK = "mock"'),
    "the stored generator kind is spelled differently from the column": (
        SERVICE, '    TEMPLATE = "template"', '    TEMPLATE = "Template"'),
    "a result can be edited after it is made": (
        SERVICE,
        "@dataclass(frozen=True, slots=True)\nclass GenerationResult:",
        "@dataclass(frozen=False, slots=True)\nclass GenerationResult:"),

    # --- the credential guard, in both directions --------------------------
    "a credential in the parameters is allowed through": (
        SERVICE,
        "            if _looks_like_a_credential(key):",
        "            if False:"),
    "the guard stops matching api_key": (
        SERVICE, '    "apikey",\n', ""),
    "the guard stops matching the short words": (
        SERVICE,
        '_CREDENTIAL_EXACT = frozenset({"key", "token", "auth"})',
        "_CREDENTIAL_EXACT = frozenset()"),
    "the guard matches on substring and starts refusing max_tokens": (
        SERVICE,
        "    return normalised in _CREDENTIAL_EXACT or any(",
        "    return any(w in normalised for w in _CREDENTIAL_EXACT) or any("),
    "the guard becomes case sensitive": (
        SERVICE,
        "    normalised = _SEPARATORS.sub(\"\", key.lower())",
        "    normalised = _SEPARATORS.sub(\"\", key)"),
    "the guard stops ignoring separators, so api_key passes": (
        SERVICE,
        "    normalised = _SEPARATORS.sub(\"\", key.lower())",
        "    normalised = key.lower()"),

    # --- the configuration -------------------------------------------------
    "the model id acquires a default": (
        SERVICE, "    model_id: str | None\n", "    model_id: str | None = None\n"),
    "a blank model id is accepted": (
        SERVICE,
        "        if self.model_id is not None and not self.model_id.strip():",
        "        if False:"),
    "the parameters are stored as the caller's own mutable dictionary": (
        SERVICE, "    return MappingProxyType(dict(parameters))", "    return parameters"),
    "a configuration error becomes something a fallback would catch": (
        SERVICE, "class ConfigurationError(ValueError):",
        "class ConfigurationError(GenerationError):"),
    "the two failure categories collapse into one": (
        SERVICE, "class GenerationRefused(GenerationError):",
        "class GenerationRefused(ProviderUnavailable):"),
    "the interface stops being structurally satisfiable": (
        SERVICE, "@runtime_checkable\nclass HypothesisGenerator(Protocol):",
        "class HypothesisGenerator(Protocol):"),
    "the interface signature admits a provider-shaped extra argument": (
        SERVICE,
        "    def generate(self, bundle: EvidenceBundle) -> GenerationResult:",
        "    def generate(self, bundle: EvidenceBundle, client: Any = None) "
        "-> GenerationResult:"),

    # --- the registry ------------------------------------------------------
    "an unknown provider falls back to the template": (
        REGISTRY,
        "        factory = available[config.provider]",
        '        factory = available.get(config.provider, available["template"])'),
    "the refusal does not say which providers are known": (
        REGISTRY,
        '            f"no provider named {config.provider!r}. Known providers: {known}. "',
        '            f"no provider named {config.provider!r}. "'),
    "an injected registry is ignored in favour of the shipped one": (
        REGISTRY,
        "    available = PROVIDERS if providers is None else providers",
        "    available = PROVIDERS"),
    "the template is not registered at all": (
        REGISTRY, '    "template": TemplateGenerator,', ""),

    # --- the one shipped adapter -------------------------------------------
    "the template adapter accepts a model id": (
        ADAPTER, "        if config.model_id is not None:", "        if False:"),
    "the template adapter reports itself as a model arm": (
        ADAPTER, "            generator=GeneratorKind.TEMPLATE,",
        "            generator=GeneratorKind.LOCAL,"),
    "the adapter swallows a refusal and invents a result": (
        ADAPTER,
        "        return GenerationResult(\n            hypothesis=generate(bundle),",
        "        try:\n            hypothesis = generate(bundle)\n"
        "        except Exception:\n            raise\n"
        "        return GenerationResult(\n            hypothesis=hypothesis,"),
}

#: Filled in by running the pass, not predicted.
EXPECTED_EQUIVALENT: set[str] = {
    # A try/except that re-raises is the same code with more words. Kept as a
    # site anyway: it is the shape a real swallow would take, and writing it
    # out confirmed the suite's refusal test reaches through the adapter
    # rather than stopping at it.
    "the adapter swallows a refusal and invents a result",
}

originals = {path: path.read_text() for path in (SERVICE, REGISTRY, ADAPTER)}
res = {}
try:
    for n, (path, o, w) in M.items():
        orig = originals[path]
        if orig.count(o) != 1:
            res[n] = f"INVALID ({orig.count(o)})"
            print(f"{n:62} {res[n]}", flush=True)
            continue
        path.write_text(orig.replace(o, w, 1))
        # See measurements/README.md: CPython validates a cached .pyc on the
        # source's (mtime-in-whole-seconds, size), so two consecutive mutants
        # of the same length can run each other's bytecode.
        for cache in ROOT.rglob("__pycache__"):
            shutil.rmtree(cache, ignore_errors=True)
        p = subprocess.run([PY_BIN, "-m", "pytest", T, "-q", "-x"], cwd=ROOT,
                           capture_output=True, text=True,
                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        t = [l for l in p.stdout.splitlines()
             if "passed" in l or "failed" in l or "error" in l]
        res[n] = ("KILLED   " if p.returncode else "SURVIVED ") + (t[-1] if t else "?")
        print(f"{n:62} {res[n]}", flush=True)
        path.write_text(orig)
finally:
    for path, text in originals.items():
        path.write_text(text)
    print("\nrestored")

killed = sum(1 for v in res.values() if v.startswith("KILLED"))
survived = [n for n, v in res.items() if v.startswith("SURVIVED")]
invalid = [n for n, v in res.items() if v.startswith("INVALID")]
print(f"\n{killed} killed of {len(res) - len(invalid)} valid mutants")
if invalid:
    print(f"INVALID (the anchor did not match exactly once): {invalid}")
unexpected = [n for n in survived if n not in EXPECTED_EQUIVALENT]
expected = [n for n in survived if n in EXPECTED_EQUIVALENT]
if expected:
    print("SURVIVED, and equivalent -- see the note above:")
    for n in expected:
        print(f"  - {n}")
if unexpected:
    print("SURVIVED, and NOT expected to -- each one is a gap in the tests:")
    for n in unexpected:
        print(f"  - {n}")
else:
    print("no unexpected survivors")
