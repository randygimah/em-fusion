"""Run assembly for a model arm. Spec: ai-011.

The last thing between this project and a first real request, and it is
composition rather than capability: every part exists, is tested and is
measured, and nothing puts them together. Asking for one explanation today
means building five objects in the right order and telling three of them,
separately, which arm this is.

**Three failures this exists to prevent, and none of them has a symptom.**

The *nesting order* is load-bearing. `ai-009`'s budget must sit inside
`ai-007`'s fallback, because outside it counts one call per bundle and
misses every retry -- and a retry loop is the only failure the budget
names. Both arrangements produce hypotheses, so a suite that only asks
"did it answer" cannot tell them apart; the proof here is behavioural, by
scripting a refusal and requiring two calls to be counted for one bundle.

The *arm* is needed by three components that cannot discover it. A result
does not carry one, and a *refused* call has no result at all -- which is
exactly the call `eval-005`'s retry rate is made of. Told separately they
can disagree, and a disagreement attributes spend to one arm and catches
to another with nothing able to notice.

*Prices* reach the adapter through the registry, which is the composition
defect this item surfaced in `ai-003`: the factory signature carries a
configuration and nothing else, so an assembled run silently lost them and
`ai-009`'s spend ceiling reported itself enforced while enforcing nothing.

**Two shapes are made unconstructible rather than checked.** Exactly one
price cannot be expressed, because the pair is frozen and requires both;
and a spend ceiling with no prices is refused here, since this is the only
place that sees the ceiling and the prices at the same moment -- `ai-009`
never learns whether the arm it wraps can price a call, and `ai-004` never
learns whether a ceiling was set.

These tests make no network call. The arm is injected through the registry
the same way `api-006` injects a batch launcher, which is what makes the
whole composition testable without a provider, a key, or a bundle the real
builder did not produce.
"""

from __future__ import annotations

import pytest

from app.ai.assembly import ArmPrices, AssembledArm, assemble_arm
from app.ai.budget import BudgetedGenerator, BudgetExceeded, CallBudget
from app.ai.fallback import CorrectnessFallback
from app.ai.grounding import GroundingChecker, GroundingLedger
from app.ai.hypothesis import Citation, Hypothesis
from app.ai.providers.template import TemplateGenerator
from app.ai.registry import build_generator
from app.ai.service import (
    ConfigurationError,
    GenerationConfig,
    GenerationRefused,
    GeneratorKind,
)
from app.ai.template import generate
from tests.test_ai_fallback import _ScriptedArm, model_result
from tests.test_ai_template import fault_bundle

MODEL = "some-model-2026-01-01"


# ------------------------------------------------------------------ the doubles


class _RecordingFactory:
    """A provider factory that records exactly how it was constructed."""

    def __init__(self, generator=None) -> None:
        self.generator = generator
        self.config: GenerationConfig | None = None
        self.kwargs: dict = {}
        self.calls = 0

    def __call__(self, config: GenerationConfig, **kwargs):
        self.calls += 1
        self.config = config
        self.kwargs = dict(kwargs)
        return self.generator if self.generator is not None else _ScriptedArm()


def registry(arm_factory=None, *, template=TemplateGenerator):
    """A provider mapping with one model arm and the template beside it."""
    return {"stub": arm_factory or _RecordingFactory(), "template": template}


def assembled(**kw) -> AssembledArm:
    """An assembled arm over defaults every test can override."""
    kw.setdefault("arm", GeneratorKind.HOSTED)
    kw.setdefault("provider", "stub")
    kw.setdefault("model_id", MODEL)
    kw.setdefault("parameters", {"temperature": 0.0, "seed": 7})
    kw.setdefault("budget", CallBudget(max_calls=10, max_cost_usd=None))
    kw.setdefault("ledger", GroundingLedger())
    kw.setdefault("max_attempts", 2)
    kw.setdefault("providers", registry())
    return assemble_arm(**kw)


def ungrounded(bundle) -> Hypothesis:
    """A real hypothesis whose one citation names nothing in the bundle."""
    base = generate(bundle)
    return Hypothesis(
        **{
            **base.model_dump(),
            "supporting_evidence": (
                Citation(
                    rule_id="NOT-A-RULE", finding_type="nope", statement="invented"
                ),
            ),
        }
    )


# ------------------------------------------------------------- what it builds


def test_the_thing_you_call_is_the_correctness_fallback():
    # spec: ai-011 -- the outermost wrapper is what a caller hands a bundle
    # to, so a caller never sees the arm, the budget or the retry directly.
    assert isinstance(assembled().generator, CorrectnessFallback)


def test_the_budget_sits_inside_the_fallback_and_not_outside_it():
    # spec: ai-011, ai-009 -- the structural half. Outside, the budget
    # counts one call per bundle and misses every retry, which is the only
    # failure ai-009 names.
    generator = assembled().generator

    assert isinstance(generator.primary, BudgetedGenerator)


def test_a_retry_is_counted_as_a_second_call():
    # spec: ai-011, ai-009 -- the behavioural half, and the one that
    # matters: both nestings answer, so a test asking only whether a
    # hypothesis came back cannot tell them apart. One bundle, one refusal,
    # one success, two calls paid for.
    bundle = fault_bundle()
    arm = _ScriptedArm(
        GenerationRefused("the provider broke its own schema"),
        model_result(hypothesis=generate(bundle)),
    )
    built = assembled(providers=registry(_RecordingFactory(arm)))

    built.generator.generate(bundle)

    assert arm.calls == 2
    assert built.budget.report().call_count == 2


def test_the_replacement_is_the_template_generator():
    # spec: ai-011, ai-002 -- what an analyst reads when a model's answer
    # cannot be used.
    assert isinstance(assembled().generator.fallback, TemplateGenerator)


def test_the_injected_check_is_the_grounding_checker():
    # spec: ai-011, ai-008 -- the safeguard is wired in here or it is not
    # wired in at all; ai-007 takes whatever check it is given, including
    # none.
    assert isinstance(assembled().generator.check, GroundingChecker)


def test_the_budget_and_ledger_handed_in_are_the_ones_used():
    # spec: ai-011 -- one of each spans a whole run and therefore both model
    # arms, so they are inputs rather than things this creates per arm.
    budget = CallBudget(max_calls=4, max_cost_usd=None)
    ledger = GroundingLedger()

    built = assembled(budget=budget, ledger=ledger)

    assert built.budget is budget
    assert built.ledger is ledger
    assert built.generator.primary.budget is budget
    assert built.generator.check.ledger is ledger


def test_the_retry_ceiling_reaches_the_fallback():
    # spec: ai-011, ai-007 -- a retry count is a spending decision, so a
    # caller's value has to arrive rather than being quietly defaulted here.
    assert assembled(max_attempts=3).generator.max_attempts == 3


def test_the_configuration_records_what_was_asked_for():
    # spec: ai-011, db-002 -- these parameters are persisted verbatim beside
    # every hypothesis, so what was configured and what is recorded must be
    # the same object rather than two descriptions of it.
    built = assembled(parameters={"temperature": 0.0, "seed": 11})

    assert built.config.provider == "stub"
    assert built.config.model_id == MODEL
    assert built.config.parameters == {"temperature": 0.0, "seed": 11}


# ---------------------------------------------------------- the arm named once


def test_the_budgeted_wrapper_takes_the_declared_arm():
    # spec: ai-011, ai-009 -- a refused call has no result to read an arm
    # from, and that is exactly the call eval-005's retry rate is made of.
    assert assembled().generator.primary.arm is GeneratorKind.HOSTED


def test_the_grounding_checker_takes_the_same_declared_arm():
    # spec: ai-011, ai-008 -- told separately these two can disagree, and a
    # disagreement attributes spend to one arm and catches to another with
    # nothing able to notice. One argument, both derived from it.
    built = assembled()

    assert built.generator.check.arm is built.generator.primary.arm


def test_a_second_arm_value_reaches_both_places_too():
    # spec: ai-011 -- the differential. Both tests above are satisfied by an
    # assembler that hard-codes the hosted arm, which is the shape of wrong
    # test this project has recorded three times.
    built = assembled(arm=GeneratorKind.LOCAL)

    assert built.arm is GeneratorKind.LOCAL
    assert built.generator.primary.arm is GeneratorKind.LOCAL
    assert built.generator.check.arm is GeneratorKind.LOCAL


def test_the_provider_is_looked_up_by_the_name_given():
    # spec: ai-011, ai-003 -- through the registry, which stays the only
    # module that knows a provider by name. Importing an adapter here would
    # make this a special case carved beside the port.
    factory = _RecordingFactory()

    assembled(providers=registry(factory))

    assert factory.calls == 1
    assert factory.config is not None
    assert factory.config.provider == "stub"


def test_an_unknown_provider_name_is_refused_and_the_known_ones_listed():
    # spec: ai-011, ai-003 -- a default would run the campaign against one
    # arm and report another.
    with pytest.raises(ConfigurationError) as raised:
        assembled(provider="nothing-by-that-name")

    assert "nothing-by-that-name" in str(raised.value)
    assert "stub" in str(raised.value)


# --------------------------------------------------------------- the template


def test_the_template_is_never_given_a_budget():
    # spec: ai-011, ai-009 -- it makes no call, and counting a fallback
    # against a model budget would abort a run for doing the safe thing, at
    # exactly the moment a model arm was already in trouble.
    assert not isinstance(assembled().generator.fallback, BudgetedGenerator)


def test_the_template_replacement_carries_no_model_id():
    # spec: ai-011, ai-003 -- model_id has no default and None is written
    # deliberately to mean "this provider has no model".
    assert assembled().generator.fallback.config.model_id is None


def test_assembling_the_template_as_the_arm_is_refused_before_anything_is_built():
    # spec: ai-011 -- it makes no call, needs no credential, and is the
    # thing both fallbacks fall back *to*. An arm that is its own fallback
    # is not a fallback.
    #
    # The refusal has to be pinned to *this* one. ai-009 refuses a budgeted
    # template as well, so a test asserting only that something was raised
    # stays green with this guard deleted -- the defect evb-002 recorded and
    # ai-004 hit twice, found here a third time by the mutation pass. What
    # this guard buys is the ordering: it fires before the arm is
    # constructed, and constructing a real arm reads the credential from the
    # environment.
    factory = _RecordingFactory()

    with pytest.raises(ConfigurationError) as raised:
        assembled(arm=GeneratorKind.TEMPLATE, providers=registry(factory))

    assert factory.calls == 0
    assert "wired in below it automatically" in str(raised.value)


def test_the_template_replacement_comes_from_the_injected_registry():
    # spec: ai-011, ai-007 -- ai-007 refuses to import ai-002 so that the
    # replacement stays injected rather than carved in beside the port. The
    # same has to be true one layer up, or this module reintroduces exactly
    # what that one avoided.
    seen = _RecordingFactory(
        generator=TemplateGenerator(
            GenerationConfig(provider="template", model_id=None)
        )
    )

    built = assembled(providers={"stub": _RecordingFactory(), "template": seen})

    assert seen.calls == 1
    assert built.generator.fallback is seen.generator


def test_the_template_factory_is_never_given_prices():
    # spec: ai-011, ai-004 -- the template makes no call and has no cost, so
    # a price handed to it is meaningless at best and a constructor error at
    # worst.
    template = _RecordingFactory(
        generator=TemplateGenerator(
            GenerationConfig(provider="template", model_id=None)
        )
    )

    assembled(
        providers={"stub": _RecordingFactory(), "template": template},
        prices=ArmPrices(usd_per_1k_prompt=0.00125, usd_per_1k_completion=0.01),
    )

    assert template.kwargs == {}


# ------------------------------------------------------------------ the prices


def test_prices_reach_the_arm_through_the_registry():
    # spec: ai-011, ai-003, ai-004 -- the composition defect this item
    # found. The factory signature carried a configuration and nothing
    # else, so an assembled run lost the prices with no visible failure.
    factory = _RecordingFactory()

    assembled(
        providers=registry(factory),
        prices=ArmPrices(usd_per_1k_prompt=0.00125, usd_per_1k_completion=0.01),
    )

    assert factory.kwargs == {
        "usd_per_1k_prompt": 0.00125,
        "usd_per_1k_completion": 0.01,
    }


def test_no_prices_means_no_pricing_arguments_at_all():
    # spec: ai-011, ai-009 -- absent, never zero. A zero handed to the
    # adapter would make every call cost 0.00, which is a number standing
    # in for unknown.
    factory = _RecordingFactory()

    assembled(providers=registry(factory))

    assert factory.kwargs == {}


def test_exactly_one_price_cannot_be_expressed():
    # spec: ai-011 -- the item's first failure case, met by construction
    # rather than by a check. Half a price makes every cost an undercount
    # presented as a number.
    with pytest.raises(TypeError):
        ArmPrices(usd_per_1k_prompt=0.00125)  # type: ignore[call-arg]


def test_a_price_of_zero_is_refused():
    # spec: ai-011, ai-009 -- free and unpriced are different states, and
    # the whole of ai-009's honest-total argument rests on keeping them
    # apart.
    with pytest.raises(ConfigurationError):
        ArmPrices(usd_per_1k_prompt=0.0, usd_per_1k_completion=0.01)


def test_a_negative_price_is_refused():
    # spec: ai-011 -- a negative price makes a spend ceiling recede as the
    # run proceeds, which is a ceiling that can never be reached.
    with pytest.raises(ConfigurationError):
        ArmPrices(usd_per_1k_prompt=0.00125, usd_per_1k_completion=-0.01)


def test_a_spend_ceiling_without_prices_is_refused():
    # spec: ai-011 -- the agreed second failure case, and the commoner
    # shape. This is the only place that sees the ceiling and the prices at
    # the same moment: ai-009 never learns whether the arm it wraps can
    # price a call, and ai-004 never learns whether a ceiling was set.
    with pytest.raises(ConfigurationError):
        assembled(budget=CallBudget(max_calls=10, max_cost_usd=5.0))


def test_the_refusal_names_the_ceiling_the_gap_and_the_consequence():
    # spec: ai-011 -- three claims, each pinned separately, because a
    # refusal that names only one of them is not actionable. Matching the
    # bare word "price" was the first version and the mutation pass killed
    # it: the tail of the message says "Supply prices, or drop the
    # ceiling", so the word survives the sentence that reports what is
    # actually missing being deleted. That is ai-004's lesson about tests
    # matching words rather than claims, one item later.
    with pytest.raises(ConfigurationError) as raised:
        assembled(budget=CallBudget(max_calls=10, max_cost_usd=5.0))

    message = str(raised.value)
    assert "5.0" in message, "does not name the ceiling it is refusing"
    assert "no prices" in message, "does not say what is missing"
    assert "enforces nothing" in message, "does not say why it matters"


def test_a_spend_ceiling_with_prices_is_accepted():
    # spec: ai-011 -- the differential. A refusal that fired on every spend
    # ceiling would satisfy the test above and forbid the configuration the
    # item exists to support.
    built = assembled(
        budget=CallBudget(max_calls=10, max_cost_usd=5.0),
        prices=ArmPrices(usd_per_1k_prompt=0.00125, usd_per_1k_completion=0.01),
    )

    assert built.budget.max_cost_usd == 5.0


def test_no_spend_ceiling_and_no_prices_is_accepted():
    # spec: ai-011 -- the spend ceiling stays optional. ai-009 settled that
    # the call ceiling is the guard and the spend ceiling is a tripwire, so
    # a run configured without one is properly guarded.
    assert assembled().budget.max_cost_usd is None


def test_prices_never_become_generation_parameters():
    # spec: ai-011, ai-004 -- parameters are splatted verbatim into the
    # provider request, so a price among them is a rejected request; and
    # they are persisted beside every hypothesis, so it would also be
    # recorded as something the model was called with.
    built = assembled(
        prices=ArmPrices(usd_per_1k_prompt=0.00125, usd_per_1k_completion=0.01)
    )

    assert built.config.parameters == {"temperature": 0.0, "seed": 7}


# ------------------------------------------------------- what it refuses to build


def test_an_undated_model_id_is_refused_by_the_arm_it_builds():
    # spec: ai-011, ai-004 -- the check belongs to the adapter and this
    # proves assembly does not route around it. A moving alias changing
    # mid-campaign invalidates the comparison with no visible error.
    from app.ai.providers.openai import OpenAIGenerator

    with pytest.raises(ConfigurationError) as raised:
        assembled(
            provider="openai",
            model_id="gpt-4o",
            providers={"openai": OpenAIGenerator, "template": TemplateGenerator},
        )

    assert "dated" in str(raised.value)


def test_a_retry_ceiling_below_one_is_refused():
    # spec: ai-011, ai-007 -- one attempt is how to say "do not retry"; zero
    # would report every bundle as a model failure that fell back, without
    # ever asking the model.
    with pytest.raises(ConfigurationError):
        assembled(max_attempts=0)


def test_a_model_id_of_none_on_a_model_arm_is_refused():
    # spec: ai-011, ai-003 -- None means "this provider has no model", which
    # is true of the template and false of every arm this assembles. Left
    # through, the campaign records no model identity at all, which db-002
    # calls the failure nobody can repair afterwards.
    with pytest.raises(ConfigurationError):
        assembled(model_id=None)


# ---------------------------------------------------------------- end to end


def test_a_grounded_answer_comes_back_unchanged_and_costs_one_call():
    # spec: ai-011 -- the whole composition, exercised.
    bundle = fault_bundle()
    hypothesis = generate(bundle)
    arm = _ScriptedArm(model_result(hypothesis=hypothesis))
    built = assembled(providers=registry(_RecordingFactory(arm)))

    result = built.generator.generate(bundle)

    assert result.hypothesis == hypothesis
    assert built.budget.report().call_count == 1
    assert built.ledger.catch_rate(GeneratorKind.HOSTED) == 0.0


def test_an_ungrounded_answer_retries_then_falls_back_and_is_counted():
    # spec: ai-011, ai-007, ai-008, ai-009 -- the four parts doing their
    # jobs in one pass: the check catches it, the retry pays again, the
    # budget counts both, and the analyst gets the template.
    bundle = fault_bundle()
    bad = ungrounded(bundle)
    arm = _ScriptedArm(model_result(hypothesis=bad), model_result(hypothesis=bad))
    built = assembled(providers=registry(_RecordingFactory(arm)))

    outcome = built.generator.generate_recorded(bundle)

    assert outcome.fell_back is True
    assert built.budget.report().call_count == 2
    assert built.ledger.caught(GeneratorKind.HOSTED) == 2
    assert built.ledger.catch_rate(GeneratorKind.HOSTED) == 1.0


def test_the_template_the_run_falls_back_to_is_not_counted_against_the_budget():
    # spec: ai-011, ai-009 -- the fallback makes no model call, so a budget
    # that counted it would abort a run for doing the safe thing.
    bundle = fault_bundle()
    bad = ungrounded(bundle)
    arm = _ScriptedArm(model_result(hypothesis=bad))
    built = assembled(providers=registry(_RecordingFactory(arm)), max_attempts=1)

    built.generator.generate(bundle)

    assert built.budget.report().call_count == 1
    assert built.budget.report().calls_for(GeneratorKind.TEMPLATE) == ()


def test_budget_exhaustion_escapes_the_fallback_rather_than_being_absorbed():
    # spec: ai-011, ai-009 -- caught by ai-007 it would finish the campaign
    # on template output while every row recorded the arm as hosted. Proved
    # through the real composition rather than by a subclass check.
    bundle = fault_bundle()
    arm = _ScriptedArm(
        model_result(hypothesis=generate(bundle)),
        model_result(hypothesis=generate(bundle)),
    )
    built = assembled(
        providers=registry(_RecordingFactory(arm)),
        budget=CallBudget(max_calls=1, max_cost_usd=None),
    )

    built.generator.generate(bundle)

    with pytest.raises(BudgetExceeded):
        built.generator.generate(bundle)


def test_two_arms_share_one_budget_and_one_ledger():
    # spec: ai-011 -- one run spans both model arms, which is what ai-006's
    # hosted-to-local fallback means, so the totals have to be the run's and
    # the per-arm figures have to stay separable inside them.
    bundle = fault_bundle()
    budget = CallBudget(max_calls=10, max_cost_usd=None)
    ledger = GroundingLedger()
    hosted = assembled(
        arm=GeneratorKind.HOSTED,
        budget=budget,
        ledger=ledger,
        providers=registry(
            _RecordingFactory(_ScriptedArm(model_result(hypothesis=generate(bundle))))
        ),
    )
    # The scripted result has to declare the local arm too: ai-009 refuses a
    # wrapper declared one way returning a result declared the other, and
    # that guard caught this test being wrong before the test caught
    # anything. Left as a comment because it is the guard working.
    local = assembled(
        arm=GeneratorKind.LOCAL,
        budget=budget,
        ledger=ledger,
        providers=registry(
            _RecordingFactory(
                _ScriptedArm(
                    model_result(
                        hypothesis=generate(bundle), generator=GeneratorKind.LOCAL
                    )
                )
            )
        ),
    )

    hosted.generator.generate(bundle)
    local.generator.generate(bundle)

    assert budget.report().call_count == 2
    assert len(budget.report().calls_for(GeneratorKind.HOSTED)) == 1
    assert len(budget.report().calls_for(GeneratorKind.LOCAL)) == 1
    assert ledger.checked(GeneratorKind.HOSTED) == 1
    assert ledger.checked(GeneratorKind.LOCAL) == 1


# ------------------------------------------------- the registry's own forwarding


def test_the_registry_forwards_construction_keywords_to_the_factory():
    # spec: ai-003 (amended), ai-011 -- the amendment itself. Without this
    # the assembler cannot price a call without importing an adapter by
    # name, which is the one thing the registry exists to prevent.
    factory = _RecordingFactory()

    build_generator(
        GenerationConfig(provider="stub", model_id=MODEL),
        {"stub": factory},
        usd_per_1k_prompt=0.00125,
        usd_per_1k_completion=0.01,
    )

    assert factory.kwargs == {
        "usd_per_1k_prompt": 0.00125,
        "usd_per_1k_completion": 0.01,
    }


def test_the_registry_still_builds_with_no_keywords_at_all():
    # spec: ai-003 -- the existing contract is unchanged; a factory taking
    # only a configuration is still a provider factory.
    built = build_generator(
        GenerationConfig(provider="template", model_id=None),
        {"template": TemplateGenerator},
    )

    assert isinstance(built, TemplateGenerator)


def test_an_unknown_name_is_still_refused_when_keywords_are_supplied():
    # spec: ai-003 -- the refusal must not be routed around by the new
    # argument, which would be the amendment quietly widening more than it
    # was meant to.
    with pytest.raises(ConfigurationError):
        build_generator(
            GenerationConfig(provider="absent", model_id=MODEL),
            {"template": TemplateGenerator},
            usd_per_1k_prompt=0.00125,
        )
