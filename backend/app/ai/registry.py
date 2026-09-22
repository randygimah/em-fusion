"""Which adapter a provider name means. Spec: ai-003.

The one place in the system that knows a provider by name. Everything else
is handed a `HypothesisGenerator` and cannot tell which it has, which is
what the item's failure case -- "a caller having to branch on provider" --
amounts to in practice.

**Adding a provider is one adapter module and one line here.** That is the
extensibility claim, and it is the second data point for it alongside
`adp-003`'s third source adapter. It is measured rather than asserted: see
`docs/thesis_notes.md`.

The mapping is **injected rather than mutated**. A registry that tests
register into is global mutable state, and a test that forgot to unregister
leaks into the next one. Passing the mapping follows `api-006`'s injected
batch launcher, and it is what lets a second provider be driven through
this interface in the suite without the shipped registry knowing anything
about it.

An unknown name is **refused and the known ones named**. Falling back to a
default would run a whole campaign against one arm while the log reported
another -- a failure with no symptom until the results are compared with
something.
"""

from __future__ import annotations

from typing import Callable, Mapping

from app.ai.providers.openai import OpenAIGenerator
from app.ai.providers.template import TemplateGenerator
from app.ai.service import ConfigurationError, GenerationConfig, HypothesisGenerator

#: Config in, generator out. A callable rather than a class, so an adapter
#: needing setup can register a factory without pretending to be one.
ProviderFactory = Callable[[GenerationConfig], HypothesisGenerator]

#: Every provider this build can use. `ai-004` and `ai-005` each add one
#: line. `ai-002` is here because the template is a provider like any
#: other -- which is what makes `ai-007`'s correctness fallback "ask for
#: the template" rather than a special case carved into each model arm.
PROVIDERS: Mapping[str, ProviderFactory] = {
    "openai": OpenAIGenerator,
    "template": TemplateGenerator,
}


def build_generator(
    config: GenerationConfig,
    providers: Mapping[str, ProviderFactory] | None = None,
) -> HypothesisGenerator:
    """The adapter this configuration names, constructed and ready."""
    available = PROVIDERS if providers is None else providers
    try:
        factory = available[config.provider]
    except KeyError:
        known = ", ".join(sorted(available)) or "none"
        raise ConfigurationError(
            f"no provider named {config.provider!r}. Known providers: {known}. "
            "An unrecognised name is refused rather than defaulted, because a "
            "default would run the campaign against one arm and report another."
        ) from None
    return factory(config)


__all__ = ["PROVIDERS", "ProviderFactory", "build_generator"]
