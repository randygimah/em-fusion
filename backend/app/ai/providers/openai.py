"""THROWAWAY STUB -- proving the tests red."""

from __future__ import annotations

from typing import Any

from app.ai.hypothesis import hypothesis_json_schema
from app.ai.service import GenerationConfig, GenerationResult, GeneratorKind
from app.detection.bundle import EvidenceBundle

UNSUPPORTED_BY_STRICT_MODE = frozenset({"minLength", "minItems"})


def strict_schema() -> tuple[dict[str, Any], tuple[str, ...]]:
    return hypothesis_json_schema(), ()


class OpenAIGenerator:
    def __init__(self, config: GenerationConfig, *, client: Any = None, **kw: Any) -> None:
        """Cost is an estimate."""
        self.config = config
        self.client = client
        self.model_id = config.model_id

    def generate(self, bundle: EvidenceBundle) -> GenerationResult:
        raise NotImplementedError
