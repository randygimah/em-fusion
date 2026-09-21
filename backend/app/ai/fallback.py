"""When a model answers badly: retry, bounded, then the template. Spec: ai-007.

The model is asked to explain a bundle and it answers, and the answer
cannot be used -- it cites a rule the bundle does not carry, or it does not
fit the required shape at all. The analyst must see neither that hypothesis
nor an error, so the request is retried a **fixed** number of times and
then `ai-002`'s mechanical explanation is produced instead, with a record
of why.

**The ceiling and the record are one deliverable.** The ceiling is here
because a retry loop is the realistic route to an unexpected bill -- not
the campaign, which is about 33,000 input tokens and costs pennies. The
record is here because a mechanical explanation that arrived *because the
model failed* and one that arrived because the template was the configured
arm look identical on screen, and must not look identical in the data.

**This is not the availability fallback, and merging them is the likeliest
error in the item.** Both end with the analyst reading something other than
the primary arm's output, which is exactly what makes them easy to
conflate. But an unreachable provider means nothing was wrong with the
question and the answer is to ask it somewhere else (`ai-006`); a bad
answer means the question reached a model, and asking a *different* model
the same failed question is the wrong move. So `ProviderUnavailable` passes
straight through here -- uncaught, unretried, unfallen-back-from -- and the
only exception this module handles is `GenerationRefused`.

**A retry only means anything if the provider is not deterministic.**
`ai-004` pins temperature 0 with a fixed seed, and a retry sends the
identical request, so a deterministic serving stack returns the identical
answer and fails the identical check: a second payment for the same
refusal. The measurement that settles this is already scheduled -- the
non-scored N=3 probe asks whether the provider actually *is* deterministic
at temperature 0, which many are not, because of batching and
floating-point non-associativity in the serving stack. Until it reports,
`RECOMMENDED_MAX_ATTEMPTS` is chosen rather than measured, and the choice
is stated below with its arithmetic.

**The two refusal categories are told apart by origin.** A refusal raised
by the generator is `MALFORMED`; a refusal raised by the injected grounding
check is `UNGROUNDED`. Neither `ai-004` nor `ai-008` has to know about a
shared flag, and neither can forget to set one. That distinction is owed:
`ai-004` uses the provider's native schema-constrained output, so for the
hosted arm a malformed answer means the provider broke its own guarantee,
which is a more alarming event than an ungrounded claim and must not
disappear into an aggregate retry count.

**The two categories leave records of different strength**, and the
asymmetry is the second reason to keep them apart. An ungrounded hypothesis
parsed, so it is a storable row carrying grounding FAILED beside the
template row that replaced it -- which is precisely why `db-002` appends
and never replaces. A malformed response never became a hypothesis, so it
leaves **no row at all**: a log line and a counted call are its entire
record.

The grounding check is **injected**, because `ai-008` is built after this,
and the fallback generator is injected too -- importing `ai-002` here would
make this a special case carved beside the port instead of the port's own
pattern, and the suite could then never drive it with anything else.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from app.ai.hypothesis import Hypothesis
from app.ai.service import (
    ConfigurationError,
    GenerationError,
    GenerationRefused,
    GenerationResult,
    HypothesisGenerator,
    ModelCall,
)
from app.detection.bundle import EvidenceBundle

_LOG = logging.getLogger(__name__)

#: What this build recommends, and **chosen rather than measured** -- the
#: one figure in this module without a corpus behind it, because no model
#: has run yet. The arithmetic is asymmetric, which is what makes the
#: choice defensible in the meantime: being wrong upwards costs at most
#: about 20 extra calls across the campaign, against `ai-009`'s 200-call
#: run budget, while being wrong downwards throws a recoverable hypothesis
#: to the template and understates the model arm in a pre-registered
#: comparison. Revisit when the determinism probe reports; if the provider
#: is deterministic at temperature 0, the honest value is 1.
RECOMMENDED_MAX_ATTEMPTS = 2

#: `ai-008`, as this module needs it: raise `GenerationRefused` if the
#: hypothesis cites anything the bundle does not carry, and return
#: otherwise. A predicate returning a bool would make "ungrounded" and
#: "the check itself failed" the same answer.
GroundingCheck = Callable[[Hypothesis, EvidenceBundle], None]


class RefusalCategory(str, Enum):
    """Why an attempt was thrown away. Determined by *where* it was refused."""

    #: The generator could not use its own provider's answer. For a
    #: schema-constrained arm this is the provider breaking its guarantee.
    MALFORMED = "malformed"

    #: It parsed, and then cited something the bundle does not carry.
    UNGROUNDED = "ungrounded"


@dataclass(frozen=True, slots=True)
class Refusal:
    """One attempt that was paid for and thrown away.

    `result` is present exactly when the refusal was `UNGROUNDED`, because
    that is what ungrounded *means*: it parsed. It is the row `db-002`
    stores with grounding FAILED beside the hypothesis that replaced it.

    `refused_call` is the awkward half and exists only for `MALFORMED`: a
    generation that never became a result has nowhere else to carry the
    tokens it consumed. Read it through `call`, which knows where to look.
    """

    attempt: int
    category: RefusalCategory
    reason: str
    result: GenerationResult | None
    refused_call: ModelCall | None

    def __post_init__(self) -> None:
        if self.attempt < 1:
            raise GenerationError(
                f"a refusal recorded against attempt {self.attempt}. Attempts "
                "are counted from one, because attempt zero is not an event "
                "that happened."
            )
        if not self.reason.strip():
            raise GenerationError(
                "a refusal carries no reason. An empty one satisfies a check "
                "for 'populated' while recording nothing, and for a malformed "
                "answer this string is the entire surviving record."
            )
        if self.category is RefusalCategory.UNGROUNDED:
            if self.result is None:
                raise GenerationError(
                    "an ungrounded refusal carries no result. Ungrounded means "
                    "it parsed, so there is a hypothesis, and db-002 appends it "
                    "with grounding FAILED beside the one that replaced it -- a "
                    "record saying otherwise loses the row."
                )
            if self.refused_call is not None:
                raise GenerationError(
                    "an ungrounded refusal carries a second copy of its model "
                    "call. The call lives inside the result it kept, and a "
                    "value stored twice eventually disagrees with itself while "
                    "both halves keep working."
                )
        elif self.result is not None:
            raise GenerationError(
                f"a {self.category.value} refusal carries a result. Nothing "
                "parsed, which is what malformed means, so there is no "
                "hypothesis and no row -- only this record and a counted call."
            )

    @property
    def call(self) -> ModelCall | None:
        """What this attempt paid for, wherever its record survived.

        One read site for `ai-009`, whichever way the attempt failed.
        """
        return self.refused_call if self.result is None else self.result.call


@dataclass(frozen=True, slots=True)
class FallbackOutcome:
    """One explanation, and every attempt that did not become one.

    `fell_back` is an explicit field rather than something inferred from
    the length of `refusals`, because it is the fact the stored row's
    interpretation depends on and "len(refusals) == max_attempts" is a
    derivation that goes wrong quietly the day the ceiling changes.
    """

    result: GenerationResult
    refusals: tuple[Refusal, ...]
    fell_back: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "refusals", tuple(self.refusals))
        if self.fell_back and not self.refusals:
            raise GenerationError(
                "an outcome reports a fallback with nothing to fall back from. "
                "The fallback and the record of why it fired are one "
                "deliverable, and this is half of it missing."
            )


class CorrectnessFallback:
    """A model arm, a bounded number of times, then something that always works.

    A decorator over `ai-003`'s port rather than a branch inside each arm,
    so `ai-004` and `ai-005` never learn that retry exists -- and so the
    two fallbacks stay two code paths, which is what the write-up claims
    and what the suite checks.

    The retry rate *per arm* falls out of this without being computed here:
    one of these is constructed per arm, so the caller that chose the
    configuration is the one that can attribute the refusals to it.
    """

    def __init__(
        self,
        primary: HypothesisGenerator,
        fallback: HypothesisGenerator,
        *,
        check: GroundingCheck | None,
        max_attempts: int,
    ) -> None:
        if max_attempts < 1:
            raise ConfigurationError(
                f"a correctness fallback configured for {max_attempts} "
                "attempts never asks the model arm at all, and would report "
                "every bundle as a model failure that fell back. One attempt "
                "is how to say 'do not retry'."
            )
        if fallback is primary:
            raise ConfigurationError(
                "the fallback generator is the primary one. A fallback that "
                "shares the thing whose failure summons it fails identically, "
                "and reports that second failure as a recovery."
            )
        self.primary = primary
        self.fallback = fallback
        self.check = check
        self.max_attempts = max_attempts

    def generate(self, bundle: EvidenceBundle) -> GenerationResult:
        """`ai-003`'s method: the explanation, with the trail dropped."""
        return self.generate_recorded(bundle).result

    def generate_recorded(self, bundle: EvidenceBundle) -> FallbackOutcome:
        """The explanation *and* every attempt that did not become one.

        The trail is returned rather than only logged, because `ai-009`
        counts calls that failed and `db-002` stores the hypothesis a
        grounding failure rejected. Neither can read a log line.
        """
        refusals: list[Refusal] = []
        last: GenerationRefused | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                result = self.primary.generate(bundle)
            except GenerationRefused as refused:
                # The arm could not use its own provider's answer.
                last = refused
                refusals.append(
                    self._refusal(
                        attempt, RefusalCategory.MALFORMED, refused, result=None
                    )
                )
                continue

            if self.check is not None:
                try:
                    self.check(result.hypothesis, bundle)
                except GenerationRefused as refused:
                    # It parsed; the claims inside it are the problem.
                    last = refused
                    refusals.append(
                        self._refusal(
                            attempt, RefusalCategory.UNGROUNDED, refused, result=result
                        )
                    )
                    continue

            return FallbackOutcome(
                result=result, refusals=tuple(refusals), fell_back=False
            )

        _LOG.warning(
            "%s exhausted %d attempt(s) on this bundle; falling back to the "
            "template generator. Last refusal (%s): %s",
            type(self.primary).__name__,
            self.max_attempts,
            refusals[-1].category.value,
            refusals[-1].reason,
        )
        try:
            replacement = self.fallback.generate(bundle)
        except GenerationError as failed:
            # The template is what both fallbacks fall back *to*, so its own
            # refusal has nowhere to go and must surface -- but it surfaces
            # carrying the model refusal that summoned it, or the
            # investigation starts from a bundle nothing could explain and
            # never learns a model was asked first.
            raise failed from last
        return FallbackOutcome(
            result=replacement, refusals=tuple(refusals), fell_back=True
        )

    def _refusal(
        self,
        attempt: int,
        category: RefusalCategory,
        refused: GenerationRefused,
        *,
        result: GenerationResult | None,
    ) -> Refusal:
        record = Refusal(
            attempt=attempt,
            category=category,
            reason=(
                # A refusal that says nothing would otherwise crash the
                # record it is the only copy of, turning a recoverable
                # refusal into the unhandled error this item exists to
                # prevent. Name the type instead.
                str(refused).strip()
                or f"{type(refused).__name__} (no message given)"
            ),
            result=result,
            refused_call=None if result is not None else refused.call,
        )
        _LOG.warning(
            "%s refused attempt %d of %d as %s: %s",
            type(self.primary).__name__,
            attempt,
            self.max_attempts,
            category.value,
            record.reason,
        )
        return record


__all__ = [
    "RECOMMENDED_MAX_ATTEMPTS",
    "CorrectnessFallback",
    "FallbackOutcome",
    "GroundingCheck",
    "Refusal",
    "RefusalCategory",
]
