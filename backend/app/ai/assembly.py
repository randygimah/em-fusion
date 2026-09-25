"""Run assembly for a model arm. Spec: ai-011.

Composition rather than capability. Every part of the hypothesis layer
exists, is tested and is measured on its own -- the adapter that talks to
the provider, `ai-009`'s budget, `ai-007`'s retry-then-fall-back, `ai-008`'s
grounding check, `ai-002`'s template -- and nothing puts them together.
Without this, asking for one explanation means building five objects in the
right order and telling three of them, separately, which arm this is.

**Three failures this exists to prevent, none of which has a symptom.**

*The nesting order.* The budget sits inside the fallback. Outside, it counts
one call per bundle and misses every retry -- the only failure `ai-009`
names -- and both arrangements produce hypotheses, so the wrong one is
visible in a bill rather than in a test run.

*The arm.* Three components need it and none can discover it: a
`GenerationResult` does not carry one, and a *refused* call has no result at
all, which is exactly the call `eval-005`'s retry rate is made of. Told
separately they can disagree, and a disagreement attributes spend to one arm
and catches to another with nothing able to notice. So it is named once here
and derived everywhere.

*The prices.* They reach the adapter through the registry, which is the
composition defect this item surfaced in `ai-003`: the factory signature
carried a configuration and nothing else, so an assembled run lost them
silently -- cost `None` on every call, and a spend ceiling reporting itself
enforced while enforcing nothing.

**Two bad states are made unconstructible rather than refused.** Exactly one
price cannot be expressed, because `ArmPrices` requires both; and a price of
zero is refused, because a zero makes every call cost 0.00 and that is a
number standing in for unknown, which is the distinction the whole of
`ai-009`'s honest-total argument rests on.

**Nothing here reads the environment.** The credential is `ai-004`'s own
lookup and stays there. The model id, the parameters and the prices are
campaign facts persisted verbatim beside every hypothesis, so a value taken
from the environment would let two machines run different campaigns with
nothing in the results saying so -- the failure the dated-model rule already
exists to prevent, arriving by another route.

**This assembles and does not run.** Iterating bundles, storing results
through `db-002` and reporting through `eval-005` is a separate job, and
keeping them apart is what lets the pre-flight three-bundle smoke test need
nothing that does not already exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.ai.budget import BudgetedGenerator, CallBudget
from app.ai.fallback import CorrectnessFallback
from app.ai.grounding import GroundingChecker, GroundingLedger
from app.ai.registry import ProviderFactory, build_generator
from app.ai.service import (
    ConfigurationError,
    GenerationConfig,
    GeneratorKind,
    HypothesisGenerator,
)

#: The registry name of the generator both fallbacks fall back *to*. Looked
#: up rather than imported, following `ai-007`: importing `ai-002` here
#: would make the replacement a special case carved beside the port instead
#: of the port's own pattern.
TEMPLATE_PROVIDER = "template"


@dataclass(frozen=True, slots=True)
class ArmPrices:
    """What a thousand tokens cost, in and out. Both, or neither.

    A single frozen pair rather than two optional numbers, so *exactly one
    price* is not a state a caller can reach. Half a price makes every cost
    an undercount presented as a number, which is worse than no number:
    `ai-009` reports actual cost as a result, and a total that quietly omits
    what it could not price is the one shape of wrongness nobody downstream
    can detect.

    Prices are per **1k** tokens; provider price lists are usually per 1M.
    """

    usd_per_1k_prompt: float
    usd_per_1k_completion: float

    def __post_init__(self) -> None:
        for name, value in (
            ("usd_per_1k_prompt", self.usd_per_1k_prompt),
            ("usd_per_1k_completion", self.usd_per_1k_completion),
        ):
            if value <= 0:
                raise ConfigurationError(
                    f"{name} is {value}, which is not a price. A zero makes "
                    "every call cost 0.00 -- a number standing in for unknown, "
                    "which is exactly what `ai-009` separates from free -- and "
                    "a negative one makes a spend ceiling recede as the run "
                    "proceeds. Omit prices entirely to mean 'this arm cannot "
                    "be priced'."
                )


@dataclass(frozen=True, slots=True)
class AssembledArm:
    """One arm, ready to be handed a bundle, with what to read afterwards.

    The ledgers come back because they are **results** and not diagnostics:
    `eval-005` reports the catch rate and the actual cost per arm, and a
    caller that could not reach them would have to keep its own copies.
    """

    #: What a caller hands one bundle to. The outermost wrapper, so no
    #: caller ever sees the arm, the budget or the retry directly.
    generator: HypothesisGenerator
    budget: CallBudget
    ledger: GroundingLedger
    arm: GeneratorKind
    #: What was configured, which is also what is persisted beside every
    #: hypothesis this arm produces.
    config: GenerationConfig


def assemble_arm(
    *,
    arm: GeneratorKind,
    provider: str,
    model_id: str | None,
    parameters: Mapping[str, Any],
    budget: CallBudget,
    ledger: GroundingLedger,
    max_attempts: int,
    prices: ArmPrices | None = None,
    providers: Mapping[str, ProviderFactory] | None = None,
) -> AssembledArm:
    """Compose one model arm from the parts, in the one order that works.

    `budget` and `ledger` span a whole **run** and therefore both model
    arms, so they are passed in rather than created here: `ai-006`'s
    hosted-to-local fallback is still one run, and a per-arm budget would
    let a run spend its ceiling twice.
    """
    if arm is GeneratorKind.TEMPLATE:
        raise ConfigurationError(
            "the template was named as the arm to assemble. It makes no call, "
            "needs no credential, and is the thing both fallbacks fall back "
            "*to* -- an arm whose fallback is itself is not a fallback. Name "
            "a model arm; the template is wired in below it automatically."
        )
    if model_id is None:
        raise ConfigurationError(
            f"the {arm.value} arm was assembled with no model id. None means "
            "'this provider has no model', which is true of the template and "
            "false of every arm this builds -- and a campaign that recorded no "
            "model identity is a campaign to run again, which `db-002` calls "
            "the failure nobody can repair afterwards."
        )
    if budget.max_cost_usd is not None and prices is None:
        raise ConfigurationError(
            f"a spend ceiling of {budget.max_cost_usd} was set and no prices "
            "were given. Cost is estimated from prices supplied at "
            "construction, so without them every call reports no cost, the "
            "ceiling is never approached and it enforces nothing while "
            "reporting itself configured. This is the only place that sees "
            "both: `ai-009` never learns whether the arm it wraps can price a "
            "call, and `ai-004` never learns whether a ceiling was set. Supply "
            "prices, or drop the ceiling and rely on the call ceiling, which "
            "was always the guard."
        )

    config = GenerationConfig(
        provider=provider, model_id=model_id, parameters=dict(parameters)
    )
    # Prices are construction, never generation parameters: `parameters` is
    # splatted verbatim into the provider request, where an unrecognised key
    # is a rejected request, and is persisted as what the model was called
    # with, which a price is not.
    construction: dict[str, Any] = {}
    if prices is not None:
        construction["usd_per_1k_prompt"] = prices.usd_per_1k_prompt
        construction["usd_per_1k_completion"] = prices.usd_per_1k_completion

    inner = build_generator(config, providers, **construction)
    replacement = build_generator(
        GenerationConfig(provider=TEMPLATE_PROVIDER, model_id=None), providers
    )

    generator = CorrectnessFallback(
        # Budget inside, fallback outside. See the module note: the other
        # way round counts one call per bundle and misses every retry.
        BudgetedGenerator(inner, budget, arm=arm),
        # Never budgeted. It makes no call, and counting a fallback against
        # a model budget would abort a run for doing the safe thing.
        replacement,
        check=GroundingChecker(arm=arm, ledger=ledger),
        max_attempts=max_attempts,
    )
    return AssembledArm(
        generator=generator,
        budget=budget,
        ledger=ledger,
        arm=arm,
        config=config,
    )


__all__ = ["TEMPLATE_PROVIDER", "ArmPrices", "AssembledArm", "assemble_arm"]
