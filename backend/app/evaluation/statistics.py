"""What a campaign produced, per arm. Spec: eval-005.

**Per arm, never pooled**, and that is the item rather than a detail: the
comparison between arms *is* the result, so a single pooled catch rate hides
the very difference being measured. Every figure here is per arm for that
reason, and there is deliberately no campaign-wide rate to quote by mistake.

**The population is all N generations**, which is a separate and larger
population than the one-per-arm corpus `eval-004` exports for human scoring.
Which population a number came from is part of the number, so the count sits
beside every rate.

**A rate over nothing is `None`, never 0.0** -- `ai-008`'s ledger rule,
applied to four rates rather than one. A fallback rate of 0.0 on an arm
nobody asked reads as perfect reliability, which is `evb-001`'s typed absence
arriving as a reported result.

**Variance needed sharpening before it could be computed.** The item asks
for "grounding variance across N generations per bundle", and the
three-bundle trial says that figure will be 1.0: grounding passed every
citation of every generation, and confidence was stable on every comparable
pair. What actually moved was the free prose and, on one bundle, the *set*
of evidence kinds cited. A report carrying only grounding agreement would
print a 1.0 and miss the finding that motivated raising N at all. So
agreement is measured over the three things that can vary -- the verdict,
the confidence, and the cited set -- and on the trial's evidence the third
is the one that will carry the result.

**Nothing here reaches a database.** The hypotheses arrive as a mapping the
caller has already read, which keeps the join in the open, lets the
arithmetic be checked without Docker, and follows `eval-004`'s sampler,
where the scenario types arrive the same way.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from app.ai.campaign import CampaignRecord, GenerationRecord
from app.ai.hypothesis import Hypothesis
from app.ai.service import ConfigurationError, GeneratorKind


def _rate(part: int, whole: int) -> float | None:
    """`part / whole`, or `None` when there is no whole.

    One implementation, because four rates need it and four spellings of
    "zero out of zero is unmeasured" eventually disagree about one of them.
    """
    return part / whole if whole else None


@dataclass(frozen=True, slots=True)
class Agreement:
    """How often the N generations of one bundle said the same thing.

    Computed only over bundles this arm was asked about **more than once**:
    agreement is undefined over a single generation, and counting one as
    agreeing with itself would inflate every figure here with the template
    arm, which is always N=1 by design.
    """

    #: Bundles with more than one generation. The denominator, stated.
    bundles: int
    grounding: float | None
    confidence: float | None
    #: The one the trial suggests will move. A citation stands for a *kind*
    #: of evidence (`ai-001`), so this compares sets and not order.
    cited_kinds: float | None

    def as_json(self) -> dict[str, Any]:
        return {
            "bundles": self.bundles,
            "grounding": self.grounding,
            "confidence": self.confidence,
            "cited_kinds": self.cited_kinds,
        }


@dataclass(frozen=True, slots=True)
class ArmStatistics:
    """One arm's figures. Nothing here is averaged with another arm's."""

    arm: GeneratorKind
    generations: int
    bundles: int
    skipped: int

    checked: int
    caught: int
    catch_rate: float | None

    attempts: int
    refusals: int
    refusals_by_category: Mapping[str, int]
    retry_rate: float | None

    fell_back: int
    fallback_rate: float | None

    calls: int
    prompt_tokens: int
    completion_tokens: int
    spent_usd: float
    unpriced_calls: int
    cost_is_complete: bool
    seconds: float

    agreement: Agreement

    @property
    def is_oracle(self) -> bool:
        """Whether this arm's catch rate validates the check rather than the arm.

        `ai-002` is grounded by construction, so anything flagged on it is a
        defect in `ai-008` and not in the baseline. Carried on the report
        because a reader handed two rates side by side and no note would
        read a non-zero template rate as the baseline inventing citations --
        which is the opposite of what it means.
        """
        return self.arm is GeneratorKind.TEMPLATE

    def as_json(self) -> dict[str, Any]:
        return {
            "arm": self.arm.value,
            "is_oracle": self.is_oracle,
            "generations": self.generations,
            "bundles": self.bundles,
            "skipped": self.skipped,
            "checked": self.checked,
            "caught": self.caught,
            "catch_rate": self.catch_rate,
            "attempts": self.attempts,
            "refusals": self.refusals,
            "refusals_by_category": dict(sorted(self.refusals_by_category.items())),
            "retry_rate": self.retry_rate,
            "fell_back": self.fell_back,
            "fallback_rate": self.fallback_rate,
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "spent_usd": self.spent_usd,
            "unpriced_calls": self.unpriced_calls,
            "cost_is_complete": self.cost_is_complete,
            "seconds": self.seconds,
            "agreement": self.agreement.as_json(),
        }


@dataclass(frozen=True, slots=True)
class CampaignStatistics:
    """Every arm's figures, and deliberately no figure spanning them."""

    arms: tuple[ArmStatistics, ...]

    def for_arm(self, arm: GeneratorKind) -> ArmStatistics:
        for stats in self.arms:
            if stats.arm is arm:
                return stats
        raise KeyError(arm)

    def as_json(self) -> dict[str, Any]:
        return {"arms": [stats.as_json() for stats in self.arms]}


def summarise(
    record: CampaignRecord, *, hypotheses: Mapping[int, Hypothesis]
) -> CampaignStatistics:
    """Turn one campaign's account into the numbers the write-up quotes.

    `hypotheses` maps a stored row id to what was stored there, and is
    required to cover every generation: a mapping quietly missing a row
    would drop that generation from the agreement figures while every count
    beside them still included it, so two halves of one report would
    describe different populations.
    """
    missing = [
        generation.hypothesis_id
        for generation in record.generations
        if generation.hypothesis_id not in hypotheses
    ]
    if missing:
        raise ConfigurationError(
            f"no hypothesis was supplied for {len(missing)} of "
            f"{len(record.generations)} generation(s), starting at row "
            f"{missing[0]}. Dropping them would leave the agreement figures "
            "and the counts beside them describing different populations, "
            "with nothing in the report saying so."
        )

    return CampaignStatistics(
        arms=tuple(_for_arm(record, arm, hypotheses) for arm in GeneratorKind)
    )


def _for_arm(
    record: CampaignRecord,
    arm: GeneratorKind,
    hypotheses: Mapping[int, Hypothesis],
) -> ArmStatistics:
    mine = [g for g in record.generations if g.requested_arm is arm]
    refusals = [refusal for g in mine for refusal in g.refusals]
    by_category: dict[str, int] = {}
    for refusal in refusals:
        by_category[refusal.category.value] = (
            by_category.get(refusal.category.value, 0) + 1
        )

    calls = record.budget.calls_for(arm)
    priced = [
        r.call.usage.cost_usd
        for r in calls
        if r.call is not None and r.call.usage.cost_usd is not None
    ]
    unpriced = sum(
        1 for r in calls if r.call is not None and r.call.usage.cost_usd is None
    )

    return ArmStatistics(
        arm=arm,
        generations=len(mine),
        bundles=len({g.bundle_id for g in mine}),
        skipped=sum(1 for s in record.skipped if s.requested_arm is arm),
        checked=record.ledger.checked(arm),
        caught=record.ledger.caught(arm),
        catch_rate=record.ledger.catch_rate(arm),
        # One generation is one attempt, plus every attempt before it that
        # was thrown away. Counting *bundles that needed a retry* would
        # report 1 where a bundle retried twice cost twice, and a retry is a
        # second call with its own price (`ai-009`).
        attempts=len(mine) + len(refusals),
        refusals=len(refusals),
        refusals_by_category=by_category,
        # Over **attempts**, not over generations: the question the write-up
        # asks is "of every call this arm made, what fraction produced an
        # answer nobody could use", which is directly comparable across arms
        # and directly comparable with the spend. Over generations it would
        # be an average number of retries wearing the word "rate", and a
        # bundle retried twice would push it above 1.0.
        retry_rate=_rate(len(refusals), len(mine) + len(refusals)),
        fell_back=sum(1 for g in mine if g.fell_back),
        fallback_rate=_rate(sum(1 for g in mine if g.fell_back), len(mine)),
        calls=len(calls),
        prompt_tokens=sum(
            r.call.usage.prompt_tokens for r in calls if r.call is not None
        ),
        completion_tokens=sum(
            r.call.usage.completion_tokens for r in calls if r.call is not None
        ),
        spent_usd=sum(priced),
        unpriced_calls=unpriced,
        # Per arm, not per campaign. A local arm prices nothing while a
        # hosted one prices everything, and one flag for the run would call
        # the hosted figure incomplete on the strength of the other's.
        cost_is_complete=unpriced == 0,
        seconds=sum(g.seconds for g in mine),
        agreement=_agreement(mine, hypotheses),
    )


def _agreement(
    generations: list[GenerationRecord], hypotheses: Mapping[int, Hypothesis]
) -> Agreement:
    """How often a bundle's repeated generations said the same thing."""
    by_bundle: dict[int, list[GenerationRecord]] = {}
    for generation in generations:
        by_bundle.setdefault(generation.bundle_id, []).append(generation)
    repeated = [group for group in by_bundle.values() if len(group) > 1]

    def agreed(read: Callable[[GenerationRecord], object]) -> float | None:
        """The proportion of bundles whose generations all read the same."""
        return _rate(
            sum(1 for group in repeated if len({read(g) for g in group}) == 1),
            len(repeated),
        )

    return Agreement(
        bundles=len(repeated),
        grounding=agreed(lambda g: g.grounding),
        confidence=agreed(lambda g: hypotheses[g.hypothesis_id].confidence),
        # A citation stands for a *kind* of evidence and not for an item
        # (`ai-001`), and a **set** rather than a sequence, because two
        # answers citing the same kinds in the other order have not
        # disagreed about anything this study is asking about.
        cited_kinds=agreed(
            lambda g: frozenset(
                (citation.rule_id, citation.finding_type)
                for citation in hypotheses[g.hypothesis_id].supporting_evidence
            )
        ),
    )


__all__ = [
    "Agreement",
    "ArmStatistics",
    "CampaignStatistics",
    "summarise",
]
