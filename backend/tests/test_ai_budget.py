"""The run-level call budget. Spec: ai-009.

The project is about to start paying per request, and this counts the
requests, records what each one cost, and **stops the run** when it has
made too many. Stops, rather than degrades.

What it is guarding against is not the campaign. Measured over the real
bundles, a whole scored campaign is about 33,000 input tokens -- single
digit pounds at worst. The risk is a **loop**: a retry that does not
terminate, a batch that regenerates on every poll, a test accidentally
pointed at the real provider. Two guards sit at different distances, and
only one of them is here: the provider console's hard cap works when the
code itself is the broken thing, and this one notices in minutes rather
than at the billing boundary.

Four properties carry this suite.

**The call ceiling is the guard; the spend ceiling is a tripwire.** A call
count can be checked *before* a call is made, so the ceiling refuses the
call rather than noticing it. Spend cannot: cost is not known until the
answer comes back, so a spend ceiling fires one call late by construction.
And `ai-003`'s `Usage.cost_usd` is `float | None` on purpose, because a
locally hosted model genuinely costs nothing per call -- so a spend ceiling
on that arm enforces nothing at all. The item called them alternatives.
They are not, and a run configured with only the second has no guard.

**Exhaustion is not a generation failure.** `ai-006` catches unreachable
providers and `ai-007` catches unusable answers. A budget error shaped like
either would not stop the run -- it would finish the campaign on template
output while the run reported itself as hosted, which is the failure
`ConfigurationError` was carved out of the `GenerationError` tree to
prevent. `BudgetExceeded` is outside that tree, and the composition is
tested rather than assumed.

**It wraps the arm, inside the correctness fallback.** The ceiling exists
for a retry loop, so a budget placed *outside* `ai-007` counts one call per
bundle and misses every retry -- the only failure mode the item names.

**An unpriced call is unmeasurable, not free.** Total spend is a stated
lower bound whenever any call could not be priced, and the ledger says how
many. A cost figure that quietly omits what it could not price is worse
than none, and `eval-005` reports actual cost as a result.
"""

from __future__ import annotations

import dataclasses
import inspect
import logging

import pytest

from app.ai.budget import (
    RECOMMENDED_MAX_CALLS,
    BudgetedGenerator,
    BudgetExceeded,
    BudgetReport,
    CallBudget,
    CallOutcome,
    CallRecord,
)
from app.ai.fallback import CorrectnessFallback
from app.ai.service import (
    ConfigurationError,
    GenerationError,
    GenerationRefused,
    GenerationResult,
    GeneratorKind,
    HypothesisGenerator,
    ProviderUnavailable,
    Usage,
)
from tests.test_ai_fallback import _ScriptedArm, a_template_arm
from tests.test_ai_service import a_call, a_hypothesis
from tests.test_ai_template import fault_bundle


def usage(prompt=100, completion=50, cost=0.01) -> Usage:
    return Usage(prompt_tokens=prompt, completion_tokens=completion, cost_usd=cost)


def priced(cost: float | None, **kw) -> GenerationResult:
    """A model result whose call carries a stated (or absent) price."""
    kw.setdefault("generator", GeneratorKind.HOSTED)
    return GenerationResult(
        hypothesis=a_hypothesis(),
        call=a_call(usage=usage(cost=cost)),
        **kw,
    )


def a_budget(*, max_calls=10, max_cost_usd=None) -> CallBudget:
    return CallBudget(max_calls=max_calls, max_cost_usd=max_cost_usd)


def budgeted(arm, budget, kind=GeneratorKind.HOSTED) -> BudgetedGenerator:
    return BudgetedGenerator(arm, budget, arm=kind)


# ------------------------------------------------- the limits are stated, never assumed


def test_a_ceiling_below_one_call_is_refused():
    # spec: ai-009 -- a budget of zero calls is a run that cannot run,
    # reported as a run that overspent.
    with pytest.raises(ConfigurationError) as raised:
        a_budget(max_calls=0)

    assert "0" in str(raised.value)


def test_the_call_ceiling_has_no_default():
    # spec: ai-009 -- same rule as ai-007's retry ceiling and
    # GenerationConfig.model_id. A spending limit inherited by omission is
    # one nobody chose.
    parameters = inspect.signature(CallBudget.__init__).parameters
    assert parameters["max_calls"].default is inspect.Parameter.empty


def test_the_spend_ceiling_has_no_default():
    # spec: ai-009 -- None means "no spend ceiling" and has to be written,
    # because deciding against one and forgetting one must not look alike.
    parameters = inspect.signature(CallBudget.__init__).parameters
    assert parameters["max_cost_usd"].default is inspect.Parameter.empty


def test_a_spend_ceiling_of_nothing_is_refused():
    # spec: ai-009 -- zero or negative is not a ceiling, it is a run that
    # aborts on its first priced call while looking configured.
    with pytest.raises(ConfigurationError):
        a_budget(max_cost_usd=0.0)


def test_a_run_may_have_no_spend_ceiling_at_all():
    # spec: ai-009 -- the call ceiling is the guard, so the spend ceiling is
    # genuinely optional rather than merely defaulted away.
    budget = a_budget(max_cost_usd=None)

    assert budget.report().max_cost_usd is None


def test_the_template_arm_cannot_be_budgeted():
    # spec: ai-009, ai-002 -- it makes no call and costs nothing. Counting
    # fallbacks against a model budget would abort a run for doing the safe
    # thing, exactly when a model arm was already in trouble.
    with pytest.raises(ConfigurationError) as raised:
        budgeted(a_template_arm(), a_budget(), GeneratorKind.TEMPLATE)

    assert "template" in str(raised.value).lower()


def test_the_recommended_ceiling_is_stated_in_one_place():
    # spec: ai-009 -- five times the largest plausible scored run, and still
    # trivially cheap. A number rather than a principle, so it lives where
    # it can be found and changed.
    assert RECOMMENDED_MAX_CALLS == 200


# ------------------------------------------- the ceiling refuses before it spends


def test_the_ceiling_refuses_the_call_rather_than_noticing_it():
    # spec: ai-009 -- THE property that separates a call ceiling from a
    # spend ceiling. The arm is never reached on the call that breaches.
    arm = _ScriptedArm(*[priced(0.01) for _ in range(5)])
    generator = budgeted(arm, a_budget(max_calls=2))

    generator.generate(fault_bundle())
    generator.generate(fault_bundle())
    with pytest.raises(BudgetExceeded):
        generator.generate(fault_bundle())

    assert arm.calls == 2


def test_the_refusal_names_the_ceiling_and_what_was_spent():
    # spec: ai-009 -- "aborts with a clear reason". A limit reached with no
    # statement of what reached it is a stack trace, not a reason.
    arm = _ScriptedArm(priced(0.01))
    generator = budgeted(arm, a_budget(max_calls=1))
    generator.generate(fault_bundle())

    with pytest.raises(BudgetExceeded) as raised:
        generator.generate(fault_bundle())

    assert "1" in str(raised.value)


def test_the_refusal_carries_the_ledger_as_it_stood():
    # spec: ai-009 -- "the calls made so far are recorded". Recorded where
    # the person handling the abort can reach them, which is on the thing
    # they caught.
    arm = _ScriptedArm(priced(0.01), priced(0.02))
    generator = budgeted(arm, a_budget(max_calls=2))
    generator.generate(fault_bundle())
    generator.generate(fault_bundle())

    with pytest.raises(BudgetExceeded) as raised:
        generator.generate(fault_bundle())

    assert raised.value.report.call_count == 2
    assert raised.value.report.spent_usd == pytest.approx(0.03)


def test_it_satisfies_the_generation_port():
    # spec: ai-009, ai-003 -- a decorator over the port, so the arm it wraps
    # never learns it is being counted.
    assert isinstance(budgeted(_ScriptedArm(), a_budget()), HypothesisGenerator)


# ------------------------------- exhaustion is not a generation failure, and must not be


def test_budget_exhaustion_is_not_a_generation_error():
    # spec: ai-009, ai-003 -- ConfigurationError's rule for
    # ConfigurationError's reason. It has to stop the run.
    assert not issubclass(BudgetExceeded, GenerationError)


def test_the_correctness_fallback_does_not_convert_exhaustion_into_a_template():
    # spec: ai-009, ai-007 -- the named failure case, and the composition
    # this item actually ships in. Caught by ai-007 it would produce a
    # mechanical hypothesis for every remaining bundle while the run
    # reported itself as hosted -- a campaign against the wrong arm with no
    # symptom until the results are compared with something.
    arm = _ScriptedArm(*[priced(0.01) for _ in range(4)])
    generator = CorrectnessFallback(
        budgeted(arm, a_budget(max_calls=1)),
        a_template_arm(),
        check=None,
        max_attempts=2,
    )
    generator.generate(fault_bundle())

    with pytest.raises(BudgetExceeded):
        generator.generate(fault_bundle())


def test_exhaustion_produces_no_hypothesis_of_any_kind():
    # spec: ai-009 -- aborting is not degrading. Nothing reaches an analyst.
    arm = _ScriptedArm(priced(0.01))
    generator = CorrectnessFallback(
        budgeted(arm, a_budget(max_calls=1)),
        a_template_arm(),
        check=None,
        max_attempts=3,
    )
    generator.generate(fault_bundle())

    with pytest.raises(BudgetExceeded):
        generator.generate_recorded(fault_bundle())

    assert arm.calls == 1


def test_an_unreachable_provider_still_reaches_the_availability_fallback():
    # spec: ai-009, ai-006 -- the budget sits in the path and must not
    # swallow what it is not for.
    arm = _ScriptedArm(ProviderUnavailable("connection refused"))

    with pytest.raises(ProviderUnavailable):
        budgeted(arm, a_budget()).generate(fault_bundle())


# ------------------------------------- inside the retry loop, which is what it is for


def test_every_retry_is_counted_and_not_one_call_per_bundle():
    # spec: ai-009, ai-007 -- the ordering is load-bearing. The budget wraps
    # the ARM and the fallback wraps the budget; the other way round counts
    # one call per bundle and misses every retry, which is the only failure
    # mode the item names.
    budget = a_budget(max_calls=10)
    arm = _ScriptedArm(
        GenerationRefused("bad", call=a_call()),
        GenerationRefused("bad again", call=a_call()),
        priced(0.01),
    )
    generator = CorrectnessFallback(
        budgeted(arm, budget), a_template_arm(), check=None, max_attempts=3
    )

    generator.generate(fault_bundle())

    assert budget.report().call_count == 3


def test_a_retry_loop_runs_the_budget_down_and_is_stopped_by_it():
    # spec: ai-009, ai-007 -- the two ceilings compose: ai-007 bounds one
    # bundle, this bounds the run, and a loop bug that defeated the first
    # still meets the second.
    budget = a_budget(max_calls=3)
    arm = _ScriptedArm(*[GenerationRefused("no", call=a_call()) for _ in range(9)])
    generator = CorrectnessFallback(
        budgeted(arm, budget), a_template_arm(), check=None, max_attempts=2
    )

    generator.generate(fault_bundle())
    with pytest.raises(BudgetExceeded):
        generator.generate(fault_bundle())

    assert arm.calls == 3


# ------------------------------------------------- what a call costs, however it ended


def test_a_served_call_is_counted_with_its_usage():
    # spec: ai-009, FR-514
    budget = a_budget()
    budgeted(_ScriptedArm(priced(0.02)), budget).generate(fault_bundle())

    report = budget.report()
    assert report.call_count == 1
    assert report.prompt_tokens == 100
    assert report.completion_tokens == 50
    assert report.spent_usd == pytest.approx(0.02)


def test_a_refused_call_is_counted_and_its_tokens_taken_from_the_refusal():
    # spec: ai-009, ai-007 -- the calls that FAILED are the ones a retry
    # loop is made of, so a ledger that counts only successes cannot see the
    # thing it exists to catch. ai-003's GenerationRefused carries the call
    # for exactly this.
    budget = a_budget()
    arm = _ScriptedArm(
        GenerationRefused("malformed", call=a_call(usage=usage(cost=0.03)))
    )

    with pytest.raises(GenerationRefused):
        budgeted(arm, budget).generate(fault_bundle())

    report = budget.report()
    assert report.call_count == 1
    assert report.spent_usd == pytest.approx(0.03)


def test_an_unreachable_provider_is_counted_but_cost_nothing():
    # spec: ai-009 -- nothing was served, so there is nothing to price. It
    # is still an attempt, and a loop against a dead provider is still a
    # loop worth stopping.
    budget = a_budget()

    with pytest.raises(ProviderUnavailable):
        budgeted(_ScriptedArm(ProviderUnavailable("down")), budget).generate(
            fault_bundle()
        )

    report = budget.report()
    assert report.call_count == 1
    assert report.spent_usd == 0.0


def test_a_refusal_the_arm_priced_nothing_for_is_still_counted():
    # spec: ai-009 -- an arm that failed before the provider answered spent
    # nothing, and the attempt still happened.
    budget = a_budget()

    with pytest.raises(GenerationRefused):
        budgeted(_ScriptedArm(GenerationRefused("could not build")), budget).generate(
            fault_bundle()
        )

    assert budget.report().call_count == 1


def test_tokens_and_cost_accumulate_across_calls():
    # spec: ai-009, FR-514
    budget = a_budget()
    generator = budgeted(_ScriptedArm(priced(0.01), priced(0.02)), budget)
    generator.generate(fault_bundle())
    generator.generate(fault_bundle())

    report = budget.report()
    assert report.prompt_tokens == 200
    assert report.spent_usd == pytest.approx(0.03)


def test_an_empty_ledger_reports_nothing_spent_rather_than_nothing_known():
    # spec: ai-009 -- a run that has made no calls has spent zero, and that
    # is a measurement rather than an absence.
    report = a_budget().report()

    assert report.call_count == 0
    assert report.spent_usd == 0.0
    assert report.cost_is_complete is True


# --------------------------------- an unpriced call is unmeasurable, not free


def test_an_unpriced_call_adds_nothing_to_the_total_and_is_counted_as_unpriced():
    # spec: ai-009, ai-003 -- cost_usd is None on purpose, because a locally
    # hosted model genuinely costs nothing per call. Treating that as 0.00
    # and treating it as "we do not know" produce the same total and
    # different claims.
    budget = a_budget()
    generator = budgeted(_ScriptedArm(priced(0.05), priced(None)), budget)
    generator.generate(fault_bundle())
    generator.generate(fault_bundle())

    report = budget.report()
    assert report.spent_usd == pytest.approx(0.05)
    assert report.unpriced_calls == 1


def test_a_total_over_any_unpriced_call_is_declared_incomplete():
    # spec: ai-009, eval-005 -- actual cost is a REPORTED result, so a
    # figure that quietly omits what it could not price is worse than none.
    budget = a_budget()
    budgeted(_ScriptedArm(priced(None)), budget).generate(fault_bundle())

    assert budget.report().cost_is_complete is False


def test_a_total_over_only_priced_calls_is_declared_complete():
    # spec: ai-009 -- and the flag has to move, or it says nothing.
    budget = a_budget()
    budgeted(_ScriptedArm(priced(0.01)), budget).generate(fault_bundle())

    assert budget.report().cost_is_complete is True


# ------------------------------------------- the spend tripwire, and its honest limits


def test_exceeding_the_spend_ceiling_aborts_the_run():
    # spec: ai-009, FR-513
    budget = a_budget(max_cost_usd=0.05)
    generator = budgeted(_ScriptedArm(priced(0.04), priced(0.04)), budget)
    generator.generate(fault_bundle())

    with pytest.raises(BudgetExceeded) as raised:
        generator.generate(fault_bundle())

    assert "cost" in str(raised.value).lower() or "spend" in str(raised.value).lower()


def test_the_spend_ceiling_can_only_fire_after_the_call_that_breached_it():
    # spec: ai-009 -- the asymmetry the amendment is about. Cost is not
    # known until the answer comes back, so unlike the call ceiling this one
    # cannot refuse; it can only notice. The arm WAS called.
    budget = a_budget(max_cost_usd=0.01)
    arm = _ScriptedArm(priced(0.99))

    with pytest.raises(BudgetExceeded):
        budgeted(arm, budget).generate(fault_bundle())

    assert arm.calls == 1


def test_the_call_that_breached_the_spend_ceiling_is_not_thrown_away():
    # spec: ai-009, NFR-602 -- it was paid for. Its verbatim response is in
    # the ledger, so aborting loses the parsed hypothesis and not the thing
    # that was bought.
    budget = a_budget(max_cost_usd=0.01)

    with pytest.raises(BudgetExceeded) as raised:
        budgeted(_ScriptedArm(priced(0.99)), budget).generate(fault_bundle())

    last = raised.value.report.calls[-1]
    assert last.call is not None
    assert last.call.raw_response


def test_a_spend_ceiling_over_unpriced_calls_never_fires():
    # spec: ai-009 -- the documented inertness, asserted rather than left to
    # be discovered. On an arm that reports no cost the spend ceiling
    # enforces nothing at all, which is precisely why it cannot be the
    # guard and the call ceiling is.
    budget = a_budget(max_calls=5, max_cost_usd=0.01)
    generator = budgeted(_ScriptedArm(*[priced(None) for _ in range(4)]), budget)

    for _ in range(4):
        generator.generate(fault_bundle())

    assert budget.report().call_count == 4


def test_no_spend_ceiling_means_no_spend_ceiling():
    # spec: ai-009
    budget = a_budget(max_cost_usd=None)
    generator = budgeted(_ScriptedArm(priced(500.0), priced(500.0)), budget)
    generator.generate(fault_bundle())
    generator.generate(fault_bundle())

    assert budget.report().spent_usd == pytest.approx(1000.0)


# ------------------------------------------ one run, two arms, attributable (eval-005)


def test_one_budget_spans_both_model_arms():
    # spec: ai-009, ai-006 -- a hosted-to-local fallback is still ONE run,
    # so a budget held per arm would let a run spend its whole ceiling
    # twice.
    budget = a_budget(max_calls=2)
    hosted = _ScriptedArm(priced(0.01))
    local = _ScriptedArm(priced(0.01, generator=GeneratorKind.LOCAL))

    budgeted(hosted, budget, GeneratorKind.HOSTED).generate(fault_bundle())
    budgeted(local, budget, GeneratorKind.LOCAL).generate(fault_bundle())

    with pytest.raises(BudgetExceeded):
        budgeted(hosted, budget, GeneratorKind.HOSTED).generate(fault_bundle())


def test_the_ledger_attributes_every_call_to_the_arm_that_made_it():
    # spec: ai-009, eval-005 -- reported per arm rather than in aggregate,
    # because the comparison between arms is the result.
    budget = a_budget()
    budgeted(_ScriptedArm(priced(0.01)), budget, GeneratorKind.HOSTED).generate(
        fault_bundle()
    )
    budgeted(
        _ScriptedArm(priced(0.02, generator=GeneratorKind.LOCAL)),
        budget,
        GeneratorKind.LOCAL,
    ).generate(fault_bundle())

    report = budget.report()
    assert len(report.calls_for(GeneratorKind.HOSTED)) == 1
    assert len(report.calls_for(GeneratorKind.LOCAL)) == 1


def test_a_refused_call_is_attributed_even_though_it_has_no_result():
    # spec: ai-009, eval-005 -- the whole reason the arm is declared at
    # construction rather than read off the result. A refused call has no
    # result, and it is exactly the call the retry rate is made of.
    budget = a_budget()
    arm = _ScriptedArm(GenerationRefused("malformed", call=a_call()))

    with pytest.raises(GenerationRefused):
        budgeted(arm, budget, GeneratorKind.HOSTED).generate(fault_bundle())

    assert len(budget.report().calls_for(GeneratorKind.HOSTED)) == 1


def test_an_arm_that_returns_another_arms_result_is_refused():
    # spec: ai-009 -- the declaration and the result must agree, or every
    # per-arm figure is quietly attributed to the wrong column.
    budget = a_budget()
    arm = _ScriptedArm(priced(0.01, generator=GeneratorKind.LOCAL))

    with pytest.raises(ConfigurationError):
        budgeted(arm, budget, GeneratorKind.HOSTED).generate(fault_bundle())


def test_a_disagreeing_arm_is_not_a_generation_failure_either():
    # spec: ai-009, ai-007 -- caught by a fallback it would run the campaign
    # against one arm and report another, which is the same failure a
    # default provider name would cause.
    assert not issubclass(ConfigurationError, GenerationError)


# ----------------------------------------------------- the records refuse to lie


def test_an_ordinal_below_one_is_refused():
    # spec: ai-009 -- calls are counted from one; call zero did not happen.
    with pytest.raises(GenerationError):
        CallRecord(
            ordinal=0,
            arm=GeneratorKind.HOSTED,
            outcome=CallOutcome.SERVED,
            call=a_call(),
        )


def test_a_call_attributed_to_the_template_is_refused():
    # spec: ai-009, ai-002 -- the template makes no call, so a record of one
    # is a fiction in the column eval-005 reads.
    with pytest.raises(GenerationError):
        CallRecord(
            ordinal=1,
            arm=GeneratorKind.TEMPLATE,
            outcome=CallOutcome.SERVED,
            call=a_call(),
        )


def test_an_unreachable_call_carrying_a_model_call_is_refused():
    # spec: ai-009 -- nothing was served, so there is nothing that could
    # have been recorded.
    with pytest.raises(GenerationError):
        CallRecord(
            ordinal=1,
            arm=GeneratorKind.HOSTED,
            outcome=CallOutcome.UNREACHABLE,
            call=a_call(),
        )


def test_a_served_call_without_its_model_call_is_refused():
    # spec: ai-009, ai-003 -- a model arm's result always carries one, so a
    # served record without it is a row that lost its provenance.
    with pytest.raises(GenerationError):
        CallRecord(
            ordinal=1,
            arm=GeneratorKind.HOSTED,
            outcome=CallOutcome.SERVED,
            call=None,
        )


def test_the_records_are_frozen():
    # spec: ai-009, NFR-602 -- a ledger that can be edited after the fact is
    # not a ledger.
    budget = a_budget()
    budgeted(_ScriptedArm(priced(0.01)), budget).generate(fault_bundle())

    with pytest.raises(dataclasses.FrozenInstanceError):
        budget.report().calls[0].ordinal = 2


def test_the_ledger_is_a_tuple_rather_than_the_list_it_was_built_from():
    # spec: ai-009 -- built from a LIST on purpose: the budget appends
    # internally, so a report handing that list out would let a caller
    # rewrite the run's history.
    report = BudgetReport(
        calls=[
            CallRecord(
                ordinal=1,
                arm=GeneratorKind.HOSTED,
                outcome=CallOutcome.SERVED,
                call=a_call(),
            )
        ],
        max_calls=10,
        max_cost_usd=None,
    )

    assert isinstance(report.calls, tuple)


def test_a_report_is_a_snapshot_and_does_not_move_under_the_caller():
    # spec: ai-009 -- the report on a BudgetExceeded is evidence about the
    # moment the run stopped. If it tracked the live ledger it would be
    # evidence about whenever it was eventually read.
    budget = a_budget()
    generator = budgeted(_ScriptedArm(priced(0.01), priced(0.01)), budget)
    generator.generate(fault_bundle())
    taken = budget.report()
    generator.generate(fault_bundle())

    assert taken.call_count == 1
    assert budget.report().call_count == 2


def test_ordinals_are_consecutive_across_arms():
    # spec: ai-009 -- one run, one sequence. Per-arm numbering would make
    # "the 200th call" ambiguous at exactly the moment it matters.
    budget = a_budget()
    budgeted(_ScriptedArm(priced(0.01)), budget, GeneratorKind.HOSTED).generate(
        fault_bundle()
    )
    budgeted(
        _ScriptedArm(priced(0.01, generator=GeneratorKind.LOCAL)),
        budget,
        GeneratorKind.LOCAL,
    ).generate(fault_bundle())

    assert [record.ordinal for record in budget.report().calls] == [1, 2]


# ---------------------------------------------------------------- it is logged


def test_exhaustion_is_logged_with_what_was_spent(caplog):
    # spec: ai-009 -- an abort nobody can explain afterwards is an outage.
    arm = _ScriptedArm(priced(0.01))
    generator = budgeted(arm, a_budget(max_calls=1))
    generator.generate(fault_bundle())

    with caplog.at_level(logging.ERROR, logger="app.ai.budget"):
        with pytest.raises(BudgetExceeded):
            generator.generate(fault_bundle())

    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "1" in logged
