"""The hosted arm. Spec: ai-004.

The primary generator, and the first thing in this project that spends
money. It uses the provider's **native structured outputs** -- a JSON
schema pinned into the request with `strict` set -- so that conforming to
`ai-001`'s shape is a generation-time guarantee rather than a hope checked
afterwards.

**That guarantee does not cover everything, which corrects this project's
own reading of §10.** The record on `ai-007` says a validation failure from
this arm cannot happen in the ordinary course, and therefore means the
provider broke its own constraint. That is true of **structure** -- the
field names, the types, the three-value confidence enum,
`additionalProperties: false` -- and false of **quantity**. Strict mode
does not honour `minLength` or `minItems`, which `ai-001` relies on for "at
least one citation" and "no blank summary". Those guarantees therefore
**move** from generation time to parse time: still enforced, by the
Pydantic model, but as a refusal rather than as an impossibility. So a
refusal from here is sorted into two kinds, and only one of them is
alarming.

The exact set of unsupported keywords is the provider's documentation
rather than something this repository can verify without a real call. It is
a named constant, every surviving guarantee is re-asserted on the
**narrowed** schema, and what was removed is returned rather than
discarded. The three-bundle smoke test on the Phase 8.5 gate is what
confirms it against the live API.

**The model id must be dated.** An alias that changes mid-campaign
invalidates the comparison with no visible error, which is the worst
failure mode available to this item.

**The credential is read from the environment and never travels in
`GenerationConfig`**, whose parameters are persisted verbatim beside every
hypothesis (`db-002`) -- a key held there would be written to the database
once per row and into every backup of it.

**Cost is an estimate.** The provider returns token counts, not money, so
`Usage.cost_usd` is absent unless prices are supplied here. One consequence
is worth stating plainly: `ai-009`'s spend ceiling is inert on *this* arm
too without them, not only on the local one. That sharpens rather than
breaks the design -- the call ceiling was always the guard.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import openai
from pydantic import ValidationError

from app.ai.hypothesis import Hypothesis, hypothesis_json_schema
from app.ai.payload import payload_json
from app.ai.prompt import HYPOTHESIS_PROMPT, prompt_fingerprint
from app.ai.service import (
    ConfigurationError,
    GenerationConfig,
    GenerationRefused,
    GenerationResult,
    GeneratorKind,
    ModelCall,
    ProviderUnavailable,
    Usage,
)
from app.detection.bundle import EvidenceBundle

#: The environment variable the credential is read from. No default.
API_KEY_VARIABLE = "OPENAI_API_KEY"

#: A dated identifier, never a moving alias. `gpt-4o-2024-08-06` passes and
#: `gpt-4o` does not.
_DATED_MODEL = re.compile(r"-\d{4}-\d{2}-\d{2}$")

#: Keywords structured-output strict mode does not honour. Taken from the
#: provider's documentation, not derivable here -- which is why what is
#: actually removed is returned by `strict_schema` rather than assumed, and
#: why the gate's three-bundle smoke test exists.
UNSUPPORTED_BY_STRICT_MODE = frozenset(
    {
        "default",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "format",
        "maxItems",
        "maxLength",
        "maximum",
        "minItems",
        "minLength",
        "minimum",
        "multipleOf",
        "pattern",
        "uniqueItems",
    }
)

#: Pydantic error types that mean a quantitative constraint was violated
#: rather than the shape being wrong. These are the ones strict mode could
#: not express, so they are the ORDINARY refusals rather than the alarming
#: ones.
_CONSTRAINT_ERRORS = frozenset(
    {"string_too_short", "string_too_long", "too_short", "too_long"}
)

#: The provider is unreachable or will not serve us. Nothing about the
#: request was wrong, so `ai-006` responds by trying elsewhere.
_UNAVAILABLE: tuple[type[Exception], ...] = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.AuthenticationError,
    openai.PermissionDeniedError,
    openai.RateLimitError,
    openai.InternalServerError,
)


def _narrow(node: Any, dropped: set[str]) -> Any:
    """Remove what strict mode will not take, recording what went."""
    if isinstance(node, list):
        return [_narrow(item, dropped) for item in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in UNSUPPORTED_BY_STRICT_MODE:
            dropped.add(key)
            continue
        out[key] = _narrow(value, dropped)
    return out


def strict_schema() -> tuple[dict[str, Any], tuple[str, ...]]:
    """`ai-001`'s schema as strict mode will take it, and what was removed.

    The removal is returned rather than logged, because a narrowing that
    does not say what it took is a place for a guarantee to vanish quietly
    between versions of a provider's API. `ai-001` already hands back a
    deep copy, so nothing here edits the shared document.
    """
    dropped: set[str] = set()
    return _narrow(hypothesis_json_schema(), dropped), tuple(sorted(dropped))


def _constraint_only(error: ValidationError) -> bool:
    """Whether every complaint is one strict mode could not have prevented."""
    kinds = {detail.get("type") for detail in error.errors()}
    return bool(kinds) and kinds <= _CONSTRAINT_ERRORS


class OpenAIGenerator:
    """One evidence bundle in, one schema-constrained hypothesis out."""

    def __init__(
        self,
        config: GenerationConfig,
        *,
        client: Any = None,
        usd_per_1k_prompt: float | None = None,
        usd_per_1k_completion: float | None = None,
    ) -> None:
        """Build the arm this configuration names.

        `client` is injected so the suite can drive this without a
        credential and without ever reaching a network; supplying one means
        no client is built here at all.

        Prices are constructor arguments and deliberately not part of
        `GenerationConfig`, because a price is a fact about billing rather
        than about what the model did and would otherwise be persisted as a
        generation parameter. A cost computed from them is an **estimate**:
        the provider's console remains the authority, which is why
        `ai-009` reports a lower bound rather than a total.
        """
        model_id = config.model_id
        if model_id is None:
            raise ConfigurationError(
                "the hosted arm was configured with no model id. None means "
                "this provider has no model, which is true of the template "
                "and false here."
            )
        if not _DATED_MODEL.search(model_id):
            raise ConfigurationError(
                f"model id {model_id!r} is not dated. A moving alias changing "
                "mid-campaign invalidates the comparison with no visible "
                "error, which is the worst failure mode this item has -- pin "
                "a dated identifier such as 'gpt-4o-2024-08-06'."
            )
        if "prompt_sha256" in config.parameters:
            raise ConfigurationError(
                "a generation parameter named 'prompt_sha256' was supplied. "
                "That value is evidence about which instructions ran and is "
                "derived from the prompt itself; a caller providing one is "
                "writing that evidence by hand."
            )
        self.config = config
        self.model_id = model_id
        self.usd_per_1k_prompt = usd_per_1k_prompt
        self.usd_per_1k_completion = usd_per_1k_completion
        self.client = client if client is not None else _client_from_environment()

    def generate(self, bundle: EvidenceBundle) -> GenerationResult:
        """Ask the model to explain this bundle, constrained to the schema."""
        schema, _ = strict_schema()
        try:
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": HYPOTHESIS_PROMPT},
                    {"role": "user", "content": payload_json(bundle)},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "hypothesis",
                        "strict": True,
                        "schema": schema,
                    },
                },
                **dict(self.config.parameters),
            )
        except _UNAVAILABLE as unavailable:
            raise ProviderUnavailable(
                f"the hosted provider could not be used: {unavailable}"
            ) from unavailable
        except openai.BadRequestError as rejected:
            # Our request, not their answer. Retried or fallen back from, a
            # rejected request would run the whole campaign on template
            # output while every row reported itself as hosted.
            raise ConfigurationError(
                f"the provider rejected the request itself: {rejected}. This is "
                "a misconfiguration -- most likely a schema strict mode will "
                "not accept -- and it has to stop the run rather than degrade "
                "it."
            ) from rejected

        message = response.choices[0].message
        raw = message.content or ""
        call = self._call(raw, response.usage)

        if getattr(message, "refusal", None):
            raise GenerationRefused(
                f"the model declined to answer: {message.refusal}", call=call
            )
        if not raw.strip():
            raise GenerationRefused(
                "the provider returned an empty response. Structurally this is "
                "not an answer that was recorded, it is an answer that was not.",
                call=None,
            )

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as broken:
            raise GenerationRefused(
                f"the response is not structurally valid JSON: {broken}. "
                "Constrained decoding makes this impossible in the ordinary "
                "course, so it means the provider broke its own guarantee.",
                call=call,
            ) from broken

        try:
            hypothesis = Hypothesis.model_validate(parsed)
        except ValidationError as invalid:
            raise GenerationRefused(self._why(invalid), call=call) from invalid

        return GenerationResult(
            hypothesis=hypothesis, generator=GeneratorKind.HOSTED, call=call
        )

    def _why(self, invalid: ValidationError) -> str:
        if _constraint_only(invalid):
            return (
                f"the response violates a constraint strict mode cannot "
                f"express: {invalid}. minLength and minItems do not survive "
                "narrowing, so this is an ordinary refusal rather than the "
                "provider breaking a guarantee."
            )
        return (
            f"the response is structurally wrong against the schema: {invalid}. "
            "Constrained decoding should make this impossible, so it means the "
            "provider did not honour the schema it was given."
        )

    def _call(self, raw: str, usage: Any) -> ModelCall | None:
        if not raw.strip():
            return None
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        return ModelCall(
            model_id=self.model_id,
            parameters={
                **dict(self.config.parameters),
                "prompt_sha256": prompt_fingerprint(),
            },
            raw_response=raw,
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=self._cost(prompt_tokens, completion_tokens),
            ),
        )

    def _cost(self, prompt_tokens: int, completion_tokens: int) -> float | None:
        """An estimate, or nothing. Never a zero standing in for unknown."""
        if self.usd_per_1k_prompt is None or self.usd_per_1k_completion is None:
            return None
        return (
            prompt_tokens / 1000 * self.usd_per_1k_prompt
            + completion_tokens / 1000 * self.usd_per_1k_completion
        )


def _client_from_environment() -> Any:
    """The provider's client, authenticated from the environment.

    No default and no silent fallback to an unauthenticated client, on
    `PSEUDONYM_SEED`'s rule: a missing credential should stop the run where
    it is missing, not where it is first used.
    """
    key = os.environ.get(API_KEY_VARIABLE, "").strip()
    if not key:
        raise ConfigurationError(
            f"{API_KEY_VARIABLE} is not set. The hosted arm reads its "
            "credential from the environment and never from a "
            "GenerationConfig, whose parameters are persisted verbatim beside "
            f"every hypothesis. Add {API_KEY_VARIABLE} to your .env, and set a "
            "hard spend cap at the provider console before the first call."
        )
    return openai.OpenAI(api_key=key)



__all__ = [
    "API_KEY_VARIABLE",
    "UNSUPPORTED_BY_STRICT_MODE",
    "OpenAIGenerator",
    "strict_schema",
]
