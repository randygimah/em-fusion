"""The provider-agnostic hypothesis interface. Spec: ai-003.

The seam between *explain this bundle* and *some particular thing produced
it*. Three producers are planned -- a mechanical one, a hosted model and a
local one -- and this is built before either model exists, for the reason
the storage port already proved: defined first, the database became a
second *implementation* rather than a second layer. Defined afterwards, an
interface gets shaped around whichever provider was written first, and the
second arrives needing the caller to know which is which.

Four properties carry most of this suite.

**The result is an envelope, not a bare hypothesis.** This was an error in
the item as first written. `ai-004`, `ai-005` and `db-002` each need the
model id, the frozen parameters and the verbatim pre-parse response, so an
interface returning only a hypothesis forces every arm to invent its own
carrier -- which is the leak the item forbids, arriving by the back door.

**The model-call record is a typed absence.** Omittable only when the
generator is the template, refused in both directions at construction. The
migration already anticipated this and deferred the guarantee to the
repository boundary; this moves it to the point the result is *made*, so a
model arm cannot construct a result missing its own raw response.

**The configuration carries no credential.** Not tidiness: the parameters
are persisted verbatim beside every hypothesis, so a key held there is
written to the database once per row. The guard has to refuse `api_key`
while admitting `max_tokens`, because a guard that also blocks a legitimate
parameter is a guard somebody turns off.

**The port has two implementations on the day it lands.** The template is
registered through it, and the suite drives a second, unrelated provider
through the same interface. An interface with one implementation is a
description of that implementation.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import pytest

from app.ai import service
from app.ai.hypothesis import Hypothesis
from app.ai.providers import template as template_provider
from app.ai.registry import PROVIDERS, build_generator
from app.ai.service import (
    ConfigurationError,
    GenerationConfig,
    GenerationError,
    GenerationRefused,
    GenerationResult,
    GeneratorKind,
    HypothesisGenerator,
    ModelCall,
    ProviderUnavailable,
    Usage,
)
from app.ai.template import TemplateError
from tests.test_ai_template import fault_bundle, verdict_of, zone_bundle

BACKEND_ROOT = Path(__file__).resolve().parents[1]
AI_ROOT = BACKEND_ROOT / "app" / "ai"


def template_config(**kw) -> GenerationConfig:
    kw.setdefault("provider", "template")
    kw.setdefault("model_id", None)
    return GenerationConfig(**kw)


def a_hypothesis() -> Hypothesis:
    from app.ai.template import generate

    return generate(fault_bundle())


def a_call(**kw) -> ModelCall:
    kw.setdefault("model_id", "some-model-2026-01-01")
    kw.setdefault("parameters", {"temperature": 0.0})
    kw.setdefault("raw_response", '{"hypothesis_title": "..."}')
    kw.setdefault("usage", Usage(prompt_tokens=100, completion_tokens=50, cost_usd=0.01))
    return ModelCall(**kw)


# ------------------------------------------- the result carries its provenance


def test_a_model_arm_result_carries_the_model_and_its_verbatim_response():
    # spec: ai-003, db-002 -- the four reproducibility columns exist because a
    # raw_response added after a campaign has run is a campaign repeated.
    call = a_call()

    result = GenerationResult(
        hypothesis=a_hypothesis(), generator=GeneratorKind.HOSTED, call=call)

    assert result.generator is GeneratorKind.HOSTED
    assert result.call is not None
    assert result.call.model_id == "some-model-2026-01-01"
    assert result.call.raw_response == call.raw_response


def test_a_model_arm_result_cannot_be_built_without_its_model_call():
    # spec: ai-003, db-002 -- the named failure case. Nullable columns defer
    # this to the repository; a typed absence refuses it where the result is
    # made, which is where the generator is known for certain.
    with pytest.raises(GenerationError) as raised:
        GenerationResult(hypothesis=a_hypothesis(),
                         generator=GeneratorKind.HOSTED, call=None)

    assert "hosted" in str(raised.value)


@pytest.mark.parametrize("kind", [GeneratorKind.HOSTED, GeneratorKind.LOCAL])
def test_neither_model_arm_may_omit_it(kind: GeneratorKind):
    # spec: ai-003 -- both arms, because a rule written for one of two arms
    # is a rule the other arm does not have.
    with pytest.raises(GenerationError):
        GenerationResult(hypothesis=a_hypothesis(), generator=kind, call=None)


def test_which_arm_produced_a_result_is_readable_from_the_result_alone():
    # spec: ai-003, ai-010, evb-001 -- the typed-absence principle again, and
    # the requirement behind it: an analyst has to be shown which arm
    # produced what they are reading, and the campaign has to count per arm.
    # Asserting that a result built with no model call has none would assert
    # only what was passed in, so both kinds are built and compared.
    mechanical = GenerationResult(hypothesis=a_hypothesis(),
                                  generator=GeneratorKind.TEMPLATE, call=None)
    from_a_model = GenerationResult(hypothesis=a_hypothesis(),
                                    generator=GeneratorKind.HOSTED, call=a_call())

    assert (mechanical.call is None) != (from_a_model.call is None)
    assert mechanical.generator is not from_a_model.generator
    # And nothing has to ask the provider which it was.
    assert {r.generator.value for r in (mechanical, from_a_model)} == {
        "template", "hosted"}


def test_a_template_result_carrying_a_model_call_is_refused():
    # spec: ai-003 -- the other direction, so the declaration cannot be a lie
    # either way. A template result naming a model would make the campaign's
    # per-arm figures wrong in the direction nobody would check.
    with pytest.raises(GenerationError) as raised:
        GenerationResult(hypothesis=a_hypothesis(),
                         generator=GeneratorKind.TEMPLATE, call=a_call())

    assert "template" in str(raised.value)


def test_an_empty_raw_response_is_refused():
    # spec: ai-003, db-002 -- verbatim pre-parse output. An empty string is
    # not a response that was recorded; it is a response that was not.
    with pytest.raises(GenerationError):
        a_call(raw_response="   ")


def test_a_blank_model_id_is_refused():
    # spec: ai-003, ai-004 -- the model id is the reproducibility claim, so
    # an empty one is worse than none: it satisfies "populated" while
    # naming nothing.
    with pytest.raises(GenerationError):
        a_call(model_id="")


def test_the_generator_kinds_are_exactly_what_the_database_permits():
    # spec: ai-003, db-002 -- the stored column carries a check constraint on
    # these three spellings, so a value that validates here cannot be
    # refused at write time.
    assert {kind.value for kind in GeneratorKind} == {"template", "local", "hosted"}


def test_a_result_cannot_be_edited_after_it_is_made():
    # spec: ai-003 -- a result is a record of what a generator produced.
    # Something adjustable afterwards is not that.
    result = GenerationResult(hypothesis=a_hypothesis(),
                              generator=GeneratorKind.TEMPLATE, call=None)

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.generator = GeneratorKind.HOSTED  # type: ignore[misc]


# ------------------------------------------------ configuration, and no secret


def test_the_configuration_names_the_provider_the_model_and_the_parameters():
    # spec: ai-003, FR-503
    config = GenerationConfig(provider="hosted", model_id="m-2026-01-01",
                              parameters={"temperature": 0.0})

    assert config.provider == "hosted"
    assert config.model_id == "m-2026-01-01"
    assert config.parameters["temperature"] == 0.0


def test_the_model_id_has_no_default_so_omitting_it_is_impossible():
    # spec: ai-003, evb-001 -- the template legitimately has none and a model
    # arm must have one, which is exactly the case where a default lets a
    # missing value look like a deliberate one.
    with pytest.raises(TypeError):
        GenerationConfig(provider="template")  # type: ignore[call-arg]


def test_a_blank_model_id_in_the_configuration_is_refused():
    # spec: ai-003 -- None means "this provider has no model". An empty
    # string means nobody filled it in, and the two must not look alike.
    with pytest.raises(ConfigurationError):
        GenerationConfig(provider="hosted", model_id="   ")


@pytest.mark.parametrize(
    "key", ["api_key", "API_KEY", "apiKey", "secret", "client_secret",
            "password", "authorization", "bearer_token", "credentials", "key",
            "token", "auth"])
def test_a_credential_in_the_parameters_is_refused(key: str):
    # spec: ai-003 -- the named failure case, and not tidiness: these
    # parameters are persisted verbatim beside every hypothesis, so a key
    # here is written into the database once per row and then lives in every
    # backup of it.
    with pytest.raises(ConfigurationError) as raised:
        GenerationConfig(provider="hosted", model_id="m", parameters={key: "sk-x"})

    assert key in str(raised.value)


@pytest.mark.parametrize(
    "key", ["max_tokens", "max_completion_tokens", "top_k", "top_p",
            "temperature", "seed", "stop_sequences", "response_format"])
def test_a_legitimate_generation_parameter_is_not_mistaken_for_one(key: str):
    # spec: ai-003 -- a guard that also blocks a real parameter is a guard
    # somebody switches off. `max_tokens` contains the word "token" and is
    # exactly the parameter the campaign has to freeze.
    config = GenerationConfig(provider="hosted", model_id="m", parameters={key: 1})

    assert key in config.parameters


def test_the_configuration_has_no_field_a_credential_could_live_in():
    # spec: ai-003 -- the parameters are checked by value above; this checks
    # the shape, so a later field named `api_key` cannot slip past a guard
    # that only inspects one dictionary.
    names = [field.name for field in dataclasses.fields(GenerationConfig)]
    suspicious = [
        name for name in names
        if any(word in name.lower()
               for word in ("key", "secret", "password", "token", "auth", "cred"))
    ]

    # The positive half matters: the negative one alone is satisfied by a
    # configuration object with no fields at all.
    assert names == ["provider", "model_id", "parameters"]
    assert suspicious == []


def test_the_configuration_cannot_be_edited_after_it_is_made():
    # spec: ai-003 -- frozen parameters are the reproducibility claim, and
    # parameters that can be adjusted between calls are not frozen.
    config = template_config()

    with pytest.raises(dataclasses.FrozenInstanceError):
        config.provider = "hosted"  # type: ignore[misc]


def test_an_unknown_parameter_shape_is_not_silently_dropped():
    # spec: ai-003 -- unknown top-level fields are refused rather than
    # ignored, so a misspelled `moddel_id` fails loudly instead of leaving
    # the real one unset.
    with pytest.raises(TypeError):
        GenerationConfig(provider="hosted", model_id="m", moddel_id="m")  # type: ignore[call-arg]


# ----------------------------------------------------- the registry, and a name


def test_the_registry_resolves_a_provider_name_to_a_generator():
    # spec: ai-003 -- configuration selects the adapter, and the caller never
    # names a class. Two names into one registry, because asking for one and
    # getting something back proves nothing about resolution: the first
    # version of this test passed against a registry that ignored the name
    # entirely and always returned the template.
    registry = {"one": _SecondProvider, "two": _SecondProvider}
    seen: list[GenerationConfig] = []

    def recording(config: GenerationConfig) -> HypothesisGenerator:
        seen.append(config)
        return _SecondProvider(config)

    generator = build_generator(
        GenerationConfig(provider="two", model_id="m-2026-01-01"),
        providers={**registry, "two": recording})

    assert isinstance(generator.generate(fault_bundle()), GenerationResult)
    assert [c.provider for c in seen] == ["two"]


def test_an_unknown_provider_is_refused_rather_than_defaulted():
    # spec: ai-003 -- the named failure case. Falling back to a default
    # provider on an unrecognised name would run a whole campaign against
    # the wrong arm and report the configured one.
    with pytest.raises(ConfigurationError) as raised:
        build_generator(GenerationConfig(provider="gpt-9", model_id="m"))

    assert "gpt-9" in str(raised.value)
    assert "template" in str(raised.value), "must say which names are known"


def test_a_configuration_error_is_not_something_a_fallback_catches():
    # spec: ai-003, ai-006, ai-007 -- deliberately NOT a GenerationError. A
    # misconfiguration is not a runtime failure to fall back from; falling
    # back from one would hide the error the whole campaign rests on and
    # quietly produce template output for a run reported as hosted.
    assert not issubclass(ConfigurationError, GenerationError)


def test_the_template_is_registered_through_the_interface():
    # spec: ai-003, ai-007 -- which is what makes the correctness fallback
    # "ask the registry for the template" rather than a special case carved
    # into each model arm.
    assert "template" in PROVIDERS


def test_the_shipped_registry_is_the_only_place_a_provider_name_is_resolved():
    # spec: ai-003 -- the named failure case: a caller branching on provider.
    # Adding a provider must touch one adapter module and one registry line,
    # and nothing else, which is only true if nothing else knows the names.
    offenders = [
        path.relative_to(BACKEND_ROOT)
        for path in sorted(AI_ROOT.rglob("*.py"))
        if path.name not in {"registry.py"}
        and not path.parent.name == "providers"
        and "template" in _string_constants(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []


# ------------------------------------------------- the template through the port


def test_the_template_adapter_produces_a_template_result():
    # spec: ai-003, ai-002
    result = build_generator(template_config()).generate(zone_bundle())

    assert result.generator is GeneratorKind.TEMPLATE
    assert result.call is None


def test_the_template_adapter_returns_the_same_hypothesis_as_calling_it_directly():
    # spec: ai-003, ai-002 -- the adapter adapts and does not alter. An
    # adapter that reworded anything would make the baseline measured
    # through the interface differ from the baseline measured without it.
    from app.ai.template import generate

    bundle = zone_bundle()

    assert build_generator(template_config()).generate(bundle).hypothesis \
        == generate(bundle)


def test_a_template_configuration_naming_a_model_is_refused():
    # spec: ai-003 -- there is no model, so a model id here would be written
    # into the reproducibility columns as though a model had run.
    with pytest.raises(ConfigurationError) as raised:
        build_generator(GenerationConfig(provider="template", model_id="m-2026"))

    assert "model" in str(raised.value)


def test_the_template_refusal_is_in_neither_fallback_category():
    # spec: ai-003, ai-006, ai-007 -- the template IS the last resort, so a
    # refusal from it must not be caught by a handler that would respond by
    # falling back to the template.
    assert issubclass(TemplateError, GenerationError)
    assert not issubclass(TemplateError, GenerationRefused)
    assert not issubclass(TemplateError, ProviderUnavailable)


def test_a_bundle_the_template_refuses_still_refuses_through_the_port():
    # spec: ai-003 -- the adapter adds no swallowing. A refusal turned into
    # a result somewhere in the seam is the one failure that would look like
    # success all the way to an analyst.
    bundle = fault_bundle()
    verdict = verdict_of(bundle)
    broken = bundle.with_evidence([i for i in bundle.evidence if i is not verdict])

    with pytest.raises(TemplateError):
        build_generator(template_config()).generate(broken)


# ----------------------------------------- two failure categories, kept distinct


def test_the_two_failure_categories_are_siblings_not_one_type():
    # spec: ai-003, ai-006, ai-007 -- the two fallbacks must remain distinct
    # paths in code and in the write-up, and a single exception type makes
    # them indistinguishable to the code that has to choose between them.
    assert issubclass(ProviderUnavailable, GenerationError)
    assert issubclass(GenerationRefused, GenerationError)
    assert not issubclass(ProviderUnavailable, GenerationRefused)
    assert not issubclass(GenerationRefused, ProviderUnavailable)


def test_catching_one_category_does_not_catch_the_other():
    # spec: ai-003 -- stated as behaviour rather than as a class hierarchy,
    # because the hierarchy is the mechanism and this is the requirement.
    with pytest.raises(GenerationRefused):
        try:
            raise GenerationRefused("the model returned prose")
        except ProviderUnavailable:  # pragma: no cover -- must not fire
            pytest.fail("the correctness path caught an availability failure")


# ---------------------------------------- the port is not shaped around one case


class _SecondProvider:
    """A provider that is not the template, driven through the same port.

    An interface with one implementation is a description of that
    implementation. This is the second, and it is deliberately unlike the
    first: it has a model, a response and a usage record.
    """

    def __init__(self, config: GenerationConfig) -> None:
        if config.model_id is None:
            raise ConfigurationError("this provider needs a model id")
        self.config = config

    def generate(self, bundle) -> GenerationResult:
        from app.ai.template import generate

        return GenerationResult(
            hypothesis=generate(bundle),
            generator=GeneratorKind.LOCAL,
            call=ModelCall(
                model_id=self.config.model_id or "",
                parameters=self.config.parameters,
                raw_response='{"pretend": "this came off a model"}',
                usage=Usage(prompt_tokens=10, completion_tokens=5, cost_usd=None)),
        )


def test_a_second_provider_needs_no_change_to_the_interface():
    # spec: ai-003, US-E2, US-R6 -- the extensibility claim, stated where it
    # can fail. A provider unlike the template, added through the same port,
    # with the registry injected rather than mutated.
    config = GenerationConfig(provider="second", model_id="m-2026-01-01")

    result = build_generator(config, providers={"second": _SecondProvider}).generate(
        zone_bundle())

    assert result.generator is GeneratorKind.LOCAL
    assert result.call is not None
    assert result.call.raw_response


def test_a_caller_drives_both_providers_without_knowing_which_is_which():
    # spec: ai-003 -- the named failure case is "a caller having to branch on
    # provider", so the test is a caller that does not.
    registry = {**PROVIDERS, "second": _SecondProvider}
    configs = [template_config(),
               GenerationConfig(provider="second", model_id="m-2026-01-01")]

    results = [build_generator(c, providers=registry).generate(zone_bundle())
               for c in configs]

    assert [r.generator for r in results] == [GeneratorKind.TEMPLATE,
                                              GeneratorKind.LOCAL]
    assert all(isinstance(r.hypothesis, Hypothesis) for r in results)


def test_the_port_is_satisfied_structurally_rather_than_by_inheritance():
    # spec: ai-003 -- a Protocol, so a provider library's own client class
    # could satisfy it without importing anything of ours. Inheritance here
    # would make the interface a dependency of every adapter.
    assert isinstance(_SecondProvider(GenerationConfig(
        provider="second", model_id="m")), HypothesisGenerator)


def test_the_interface_signature_takes_a_bundle_and_returns_a_result():
    # spec: ai-003 -- read off the Protocol itself, so a later widening of
    # the signature to admit a provider-shaped argument fails here rather
    # than at the first adapter that exploits it.
    signature = inspect.signature(HypothesisGenerator.generate)

    assert list(signature.parameters) == ["self", "bundle"]
    assert signature.return_annotation in (GenerationResult, "GenerationResult")


# ---------------------------------------------- no provider shape in the seam

#: Anything that would mean a provider's own types had reached the interface.
PROVIDER_PACKAGES = frozenset({
    "anthropic", "openai", "cohere", "google", "vertexai", "boto3", "mistralai",
    "llama_cpp", "ollama", "transformers", "torch", "httpx", "requests",
    "aiohttp", "urllib", "http",
})

#: The modules allowed to know a provider exists. Everything else in the AI
#: package must be expressible without naming one.
ADAPTER_DIR = "providers"


def _string_constants(source: str) -> set[str]:
    """Every string literal in a module that is not a docstring.

    Parsed rather than grepped. A substring search is satisfied by an
    example inside a docstring, which is how the equivalent check in
    `dal-004` passed vacuously once already.
    """
    tree = ast.parse(source)
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef
                      | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                docstrings.add(id(first.value))
    return {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def imported_packages(source: str) -> set[str]:
    """The top-level package of every import in a module."""
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found


def test_the_import_check_recognises_a_real_violation():
    # spec: ai-003 -- the check below is an empty intersection when it holds
    # and an empty intersection when it is broken. Fired once, deliberately,
    # at a module written to break it.
    source = "import anthropic\n\n\ndef go() -> None:\n    anthropic.Client()\n"

    assert imported_packages(source) & PROVIDER_PACKAGES == {"anthropic"}


def test_a_provider_named_only_inside_a_docstring_is_not_a_violation():
    # spec: ai-003 -- a check that cannot tell a rule from a description of
    # the rule is the failure this file exists to prevent, one level up.
    source = '"""Adapters for anthropic and openai live under providers/."""\n'

    assert _string_constants(source) == set()


def test_no_module_in_the_ai_package_imports_a_provider_library():
    # spec: ai-003, ai-002 -- the interface is defined before either provider
    # exists, so nothing here can have been shaped by one. When ai-004 lands
    # its import will be confined to its own adapter module.
    offenders = [
        f"{path.relative_to(BACKEND_ROOT)}: {sorted(found)}"
        for path in sorted(AI_ROOT.rglob("*.py"))
        if path.parent.name != ADAPTER_DIR
        and (found := imported_packages(path.read_text(encoding="utf-8"))
             & PROVIDER_PACKAGES)
    ]

    assert offenders == []


def test_the_service_module_does_not_import_any_adapter():
    # spec: ai-003 -- the direction of the dependency IS the abstraction. An
    # interface importing its implementations is a module that happens to
    # contain a base class.
    tree = ast.parse((AI_ROOT / "service.py").read_text(encoding="utf-8"))
    named = {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any(m.startswith("app.ai.providers") or m == "app.ai.registry"
                   for m in named), named


def test_the_service_module_names_no_provider():
    # spec: ai-003 -- not even as a string. A default provider name here
    # would be the branch-on-provider failure case wearing a constant.
    assert "template" not in _string_constants(
        (AI_ROOT / "service.py").read_text(encoding="utf-8"))


def test_every_public_name_in_the_service_is_provider_neutral():
    # spec: ai-003 -- the failure case is a provider-specific TYPE in the
    # signature, so the names are read off the module rather than argued
    # about in review.
    exported = [name for name in vars(service) if not name.startswith("_")]

    offenders = [name for name in exported
                 if any(p in name.lower() for p in PROVIDER_PACKAGES)]

    assert offenders == []


def test_the_adapter_directory_is_where_a_provider_may_be_named():
    # spec: ai-003 -- stated positively as well, so the rule above cannot be
    # satisfied by there being no adapters at all.
    adapters = {p.name for p in (AI_ROOT / ADAPTER_DIR).glob("*.py")}

    assert (AI_ROOT / ADAPTER_DIR).is_dir()
    assert "template.py" in adapters
    assert template_provider is not None
