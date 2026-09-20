"""The seam between "explain this bundle" and whatever produced the answer.

Spec: ai-003.

Three things will write explanations -- the `ai-002` template, a hosted
model and a local one -- and this is defined before either model exists.
That ordering is the one `dal-002` already proved: the storage port was
written before the database, so the database arrived as a **second
implementation** rather than as a second layer. Written afterwards, an
interface takes the shape of whichever provider came first, and the second
one arrives needing its caller to know which is which.

**The result is an envelope, not a bare hypothesis**, and the item said
otherwise until building it showed why that could not be right. `ai-004`,
`ai-005` and `db-002` each need the model id, the frozen parameters and the
verbatim pre-parse response. An interface handing back only a hypothesis
forces every arm to carry that provenance some other way -- which is the
provider-specific shape leaking into the seam, arriving by the back door
rather than through the signature the item was watching.

**The model-call record is a typed absence**, not four nullable fields.
Legal to omit only when the generator is the template, refused in both
directions at construction. `0001_core_schema` made those columns nullable
and deferred the guarantee to the repository boundary "where the generator
is known"; the generator is known earlier than that -- at the moment the
result is made -- so the guarantee moves there and a model arm cannot
construct a result missing its own raw response.

**The configuration carries no credential.** This is not tidiness. The
parameters are persisted verbatim beside every hypothesis (`db-002`), so a
key held here is written into the database once per row and then into every
backup of it. The guard refuses a credential by name and has to admit
`max_tokens` while doing it, because a guard that also blocks the parameter
a campaign must freeze is a guard somebody turns off.

**Two failure categories, deliberately siblings.** `ai-006`'s availability
fallback fires on unreachable, unauthenticated or rate limited; `ai-007`'s
correctness fallback fires on output that cannot be used. Those must stay
distinct paths in code and in the write-up, and a single exception type
makes them indistinguishable to the code choosing between them. A
misconfiguration is in **neither**: `ConfigurationError` is not a
`GenerationError`, because falling back from a misconfiguration would hide
the error the whole campaign rests on and quietly produce template output
for a run reported as hosted.

Nothing here names a provider, imports one, or can be made to branch on
one. That is asserted from the syntax tree rather than promised, and the
check is fired once at a module written to break it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable

from app.ai.hypothesis import Hypothesis
from app.detection.bundle import EvidenceBundle


class GenerationError(Exception):
    """A generation that did not produce a usable result.

    The base of the two categories below, and of `ai-002`'s own refusal --
    which is deliberately neither of them, because the template is the last
    resort and falling back from the fallback has nowhere to go.
    """


class ProviderUnavailable(GenerationError):
    """The provider could not be reached, or would not serve us.

    Unreachable, unauthenticated, rate limited, timed out. `ai-006`
    responds to this by trying the local arm; nothing about the request was
    wrong, so retrying the same request elsewhere is the right answer.
    """


class GenerationRefused(GenerationError):
    """The provider answered, and the answer cannot be used.

    Malformed against the schema, or ungrounded against the bundle.
    `ai-007` responds with a bounded retry and then the template. Retrying
    *elsewhere* would be wrong here: the request reached a model and the
    model's answer was the problem.
    """


class ConfigurationError(ValueError):
    """The system is set up wrongly. Not a `GenerationError`, on purpose.

    A misconfiguration is not a runtime failure to fall back from. Caught
    by an availability handler it would run a campaign against the wrong
    arm; caught by a correctness handler it would produce template output
    for every bundle while the run reported itself as hosted. It has to
    stop the run.
    """


class GeneratorKind(str, Enum):
    """Which of the three produced an explanation.

    The spellings match `0001_core_schema`'s check constraint on the stored
    column, so a value that validates here cannot be refused at write time.
    """

    TEMPLATE = "template"
    HOSTED = "hosted"
    LOCAL = "local"


@dataclass(frozen=True, slots=True)
class Usage:
    """What one call consumed. Recorded from the first call, not retrofitted.

    `ai-009` needs this to abort a run that exceeds its budget, and the
    realistic route to an unexpected bill is a retry loop rather than a
    price rise -- which is only visible if every call is counted, including
    the ones that failed and were retried.

    `cost_usd` is optional because a locally hosted model genuinely costs
    nothing per call. That is an honest absence rather than a missing
    measurement, and it is the one field here where the two coincide.
    """

    prompt_tokens: int
    completion_tokens: int
    cost_usd: float | None


@dataclass(frozen=True, slots=True)
class ModelCall:
    """What a model was asked, and what it said before anything parsed it.

    `raw_response` is the verbatim pre-parse output (`db-002`, NFR-602). It
    is what makes a result reproducible and what makes a grounding failure
    investigable after the fact; a response reconstructed by re-serialising
    the parsed hypothesis is a record of what we understood, not of what
    was said.
    """

    model_id: str
    parameters: Mapping[str, Any]
    raw_response: str
    usage: Usage

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise GenerationError(
                "a model call carries no model id. An empty one is worse than "
                "none: it satisfies a check for 'populated' while naming "
                "nothing, and the model id is the whole reproducibility claim."
            )
        if not self.raw_response.strip():
            raise GenerationError(
                f"the call to {self.model_id!r} recorded an empty raw response. "
                "Verbatim pre-parse output is what makes a result "
                "reproducible, and an empty string is not a response that was "
                "recorded -- it is a response that was not."
            )
        object.__setattr__(self, "parameters", _frozen(self.parameters))


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """One explanation, and what produced it.

    The unit every arm hands back. `call` is the typed absence: present for
    a model arm, absent for the template, and both lies refused.
    """

    hypothesis: Hypothesis
    generator: GeneratorKind
    call: ModelCall | None

    def __post_init__(self) -> None:
        if self.generator is GeneratorKind.TEMPLATE and self.call is not None:
            raise GenerationError(
                "a template result carries a model call. No model ran, so a "
                "model id and a response here are a fiction written into the "
                "reproducibility columns -- and the campaign's per-arm figures "
                "would be wrong in the direction nobody would think to check."
            )
        if self.generator is not GeneratorKind.TEMPLATE and self.call is None:
            raise GenerationError(
                f"a {self.generator.value} result carries no model call. The "
                "model id, the frozen parameters and the verbatim response are "
                "what make it reproducible (db-002), and a result that can be "
                "built without them is one that will be."
            )


#: A parameter key that would be a credential. Matched on the key stripped
#: of separators and lower-cased, so `API_KEY`, `api-key` and `apiKey` are
#: one thing. Substring for the unambiguous words and **equality** for the
#: short ones, because `max_tokens` contains "token" and is precisely the
#: parameter a campaign has to freeze.
_CREDENTIAL_SUBSTRINGS = (
    "apikey",
    "secret",
    "password",
    "passwd",
    "credential",
    "bearer",
    "authorization",
)
_CREDENTIAL_EXACT = frozenset({"key", "token", "auth"})
_SEPARATORS = re.compile(r"[^a-z0-9]")


def _looks_like_a_credential(key: str) -> bool:
    normalised = _SEPARATORS.sub("", key.lower())
    return normalised in _CREDENTIAL_EXACT or any(
        word in normalised for word in _CREDENTIAL_SUBSTRINGS
    )


def _frozen(parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """An unmodifiable view over a copy. Frozen means frozen."""
    return MappingProxyType(dict(parameters))


@dataclass(frozen=True, slots=True)
class GenerationConfig:
    """Which arm to use, which model, and under what parameters.

    Supplied once and used to **construct** the adapter, rather than
    travelling with each call. That is deliberate: parameters that can vary
    per call will eventually vary per call, and a campaign whose arms ran
    under different parameters is not a comparison. `ai-004` requires a
    dated model identifier for the same reason one step further out -- an
    alias that changes mid-campaign invalidates the result with no visible
    failure.

    `model_id` has **no default**, so a caller must write `None` to mean
    "this provider has no model". Omission and deliberate absence must not
    look alike; that is `evb-001`'s rule and this is the case it was
    written for.
    """

    provider: str
    model_id: str | None
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ConfigurationError("a configuration names no provider")
        if self.model_id is not None and not self.model_id.strip():
            raise ConfigurationError(
                f"provider {self.provider!r} carries a blank model id. None "
                "means this provider has no model; an empty string means "
                "nobody filled it in, and the two must not look alike."
            )
        for key in self.parameters:
            if _looks_like_a_credential(key):
                raise ConfigurationError(
                    f"generation parameter {key!r} looks like a credential. "
                    "These parameters are persisted verbatim beside every "
                    "hypothesis (db-002), so a secret here is written into the "
                    "database once per row and into every backup of it. A key "
                    "belongs to the adapter that authenticates, never to the "
                    "configuration that travels."
                )
        object.__setattr__(self, "parameters", _frozen(self.parameters))


@runtime_checkable
class HypothesisGenerator(Protocol):
    """Bundle in, result out. The whole interface.

    A `Protocol` rather than a base class, so satisfying it costs an
    adapter nothing: structural, so a provider's own client could satisfy
    it without importing anything of ours. Inheritance would make this
    module a dependency of every adapter, which is the wrong direction for
    the thing that is supposed to be the abstraction.
    """

    def generate(self, bundle: EvidenceBundle) -> GenerationResult:
        """Explain this bundle, however this provider does that."""
        ...


__all__ = [
    "ConfigurationError",
    "GenerationConfig",
    "GenerationError",
    "GenerationRefused",
    "GenerationResult",
    "GeneratorKind",
    "HypothesisGenerator",
    "ModelCall",
    "ProviderUnavailable",
    "Usage",
]
