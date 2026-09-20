"""The `ai-002` template generator, behind the `ai-003` interface.

An adapter and nothing more: it adds a provenance envelope and alters not a
word. That matters for the campaign rather than for tidiness -- the
baseline measured through the interface has to be the same baseline
measured without it, or the arm the models are compared against depends on
how it was called.

Registering the template as a provider is what gives the port two
implementations on the day it lands. An interface with one implementation
is a description of that implementation, and this project has already
watched that happen the other way round: `dal-002`'s port had the in-memory
repository beside it from the start, which is why the PostGIS one needed no
change to the interface.
"""

from __future__ import annotations

from app.ai.service import (
    ConfigurationError,
    GenerationConfig,
    GenerationResult,
    GeneratorKind,
)
from app.ai.template import generate
from app.detection.bundle import EvidenceBundle


class TemplateGenerator:
    """Bundle in, mechanically written explanation out. No model, no network."""

    def __init__(self, config: GenerationConfig) -> None:
        if config.model_id is not None:
            raise ConfigurationError(
                f"the template generator was configured with model id "
                f"{config.model_id!r}. There is no model here, so that value "
                "would be written into the reproducibility columns as though "
                "one had run, and the campaign would count a mechanical "
                "explanation as a model's."
            )
        self.config = config

    def generate(self, bundle: EvidenceBundle) -> GenerationResult:
        """The `ai-002` hypothesis, wrapped and otherwise untouched.

        A refusal is deliberately not caught. The template is the last
        resort, so a refusal here is a bundle nothing can explain, and
        swallowing it would be the one failure that looks like success all
        the way to an analyst.
        """
        return GenerationResult(
            hypothesis=generate(bundle),
            generator=GeneratorKind.TEMPLATE,
            call=None,
        )


__all__ = ["TemplateGenerator"]
