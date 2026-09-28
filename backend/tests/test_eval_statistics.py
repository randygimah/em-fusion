"""The numbers a campaign produces, per arm. Spec: eval-005.

**Per arm, never pooled**, and that is the whole item rather than a detail:
the comparison between arms is the result, so a single pooled catch rate
hides the very difference being measured. The item's own failure case says
so, and every figure here is computed per arm for that reason.

**The population is all N generations**, deliberately larger than the
one-per-arm corpus `eval-004` exports for human scoring. Saying which
population a number came from is part of the number, so the count is
reported beside every rate.

**Variance needed sharpening before it could be built.** The item asks for
"grounding variance across N generations", and the three-bundle trial says
that will be zero -- grounding passed every citation of every generation,
and confidence was stable on every comparable pair. What actually moved was
the prose and, on one bundle, the *set* of evidence kinds cited. A report
carrying only grounding agreement would print a 1.0 and miss the finding.
So agreement is measured over the three things that can vary -- the
verdict, the confidence and the cited set -- and the third is the one the
trial suggests will carry the result.

**A rate over nothing is `None`, never 0.0.** `ai-008`'s ledger rule, one
layer up and now applied to four rates rather than one: a zero fallback
rate on an arm that never ran reads as perfect reliability.

These tests touch no database. The hypotheses arrive as a mapping the
caller has already read, which keeps the join in the open and lets the
arithmetic be checked without Docker -- the same shape `eval-004`'s sampler
uses for scenario types.
"""

from __future__ import annotations

import json

import pytest

from app.ai.budget import BudgetReport, CallOutcome, CallRecord
from app.ai.campaign import (
    CampaignRecord,
    GenerationRecord,
    RefusalRecord,
    SkippedGeneration,
)
from app.ai.fallback import RefusalCategory
from app.ai.grounding import GroundingLedger, check
from app.ai.hypothesis import Citation, Confidence, Hypothesis
from app.ai.service import ConfigurationError, GeneratorKind, ModelCall, Usage
from app.ai.template import generate
from app.db.hypotheses import GroundingStatus
from app.evaluation.statistics import summarise
from tests.test_ai_template import fault_bundle

HOSTED = GeneratorKind.HOSTED
TEMPLATE = GeneratorKind.TEMPLATE
LOCAL = GeneratorKind.LOCAL


# ------------------------------------------------------------------ the doubles


def usage(prompt=1000, completion=200, cost=0.01) -> Usage:
    return Usage(prompt_tokens=prompt, completion_tokens=completion, cost_usd=cost)


def call(**kw) -> ModelCall:
    kw.setdefault("model_id", "some-model-2026-01-01")
    kw.setdefault("parameters", {"temperature": 0.0})
    kw.setdefault("raw_response", '{"a": 1}')
    kw.setdefault("usage", usage())
    return ModelCall(**kw)


def budget(*records: CallRecord, max_calls=200) -> BudgetReport:
    return BudgetReport(calls=records, max_calls=max_calls, max_cost_usd=None)


def served(ordinal: int, arm=HOSTED, **kw) -> CallRecord:
    return CallRecord(
        ordinal=ordinal, arm=arm, outcome=CallOutcome.SERVED, call=call(**kw)
    )


def refused_call(ordinal: int, arm=HOSTED, **kw) -> CallRecord:
    return CallRecord(
        ordinal=ordinal, arm=arm, outcome=CallOutcome.REFUSED, call=call(**kw)
    )


def generation(bundle_id=1, ordinal=1, arm=HOSTED, **kw) -> GenerationRecord:
    kw.setdefault("generator", arm)
    kw.setdefault("hypothesis_id", bundle_id * 100 + ordinal)
    kw.setdefault("grounding", GroundingStatus.PASSED)
    kw.setdefault("refusals", ())
    kw.setdefault("usage", usage())
    kw.setdefault("seconds", 1.5)
    return GenerationRecord(
        bundle_id=bundle_id, ordinal=ordinal, requested_arm=arm, **kw
    )


def refusal(attempt=1, category=RefusalCategory.UNGROUNDED, row=None) -> RefusalRecord:
    return RefusalRecord(
        attempt=attempt,
        category=category,
        reason="cited something the bundle does not carry",
        hypothesis_id=row,
        usage=usage(),
    )


def a_hypothesis(*, confidence=None, kinds=None) -> Hypothesis:
    """A real template hypothesis, with confidence or citations replaced."""
    base = generate(fault_bundle())
    fields = base.model_dump()
    if confidence is not None:
        fields["confidence"] = confidence
    if kinds is not None:
        fields["supporting_evidence"] = tuple(
            Citation(rule_id=rule, finding_type=kind, statement="what it showed")
            for rule, kind in kinds
        )
    return Hypothesis(**fields)


def ledger_over(*reports) -> GroundingLedger:
    led = GroundingLedger()
    for arm, report in reports:
        led.record(arm, report)
    return led


def a_record(generations, *, skipped=(), calls=(), ledger=None) -> CampaignRecord:
    return CampaignRecord(
        generations=tuple(generations),
        skipped=tuple(skipped),
        budget=budget(*calls),
        ledger=ledger if ledger is not None else GroundingLedger(),
    )


def summary(record, hypotheses=None):
    if hypotheses is None:
        hypotheses = {gen.hypothesis_id: a_hypothesis() for gen in record.generations}
    return summarise(record, hypotheses=hypotheses)


# --------------------------------------------------------------- per arm, always


def test_every_figure_is_reported_per_arm_and_never_pooled() -> None:
    # spec: eval-005 -- the item's own failure case. A single pooled catch
    # rate hides the difference the whole study is about.
    record = a_record(
        [generation(1, 1, HOSTED), generation(1, 1, TEMPLATE)],
        calls=(served(1),),
    )

    stats = summary(record)

    assert {arm.arm for arm in stats.arms} == set(GeneratorKind)
    assert stats.for_arm(HOSTED).generations == 1
    assert stats.for_arm(TEMPLATE).generations == 1
    assert not hasattr(stats, "catch_rate"), "there is no campaign-wide rate"


def test_an_arm_that_never_ran_is_reported_as_unmeasured_not_as_zero() -> None:
    # spec: eval-005, ai-008, evb-001 -- zero out of zero is unmeasured. A
    # fallback rate of 0.0 on an arm nobody asked reads as perfect
    # reliability, which is the typed-absence failure applied to a result.
    stats = summary(a_record([generation(1, 1, HOSTED)]))

    local = stats.for_arm(LOCAL)

    assert local.generations == 0
    assert local.catch_rate is None
    assert local.retry_rate is None
    assert local.fallback_rate is None
    assert local.spent_usd == 0.0


def test_the_population_each_rate_was_taken_over_is_reported_beside_it() -> None:
    # spec: eval-005, eval-004 -- this population is all N generations and
    # is deliberately larger than the one eval-004 exports for marking.
    # Which population a number came from is part of the number.
    record = a_record(
        [generation(1, n, HOSTED) for n in (1, 2, 3)]
        + [generation(2, n, HOSTED) for n in (1, 2, 3)]
    )

    hosted = summary(record).for_arm(HOSTED)

    assert hosted.generations == 6
    assert hosted.bundles == 2


# ------------------------------------------------------- what the safeguard said


def test_the_catch_rate_comes_from_the_ledger_per_arm() -> None:
    # spec: eval-005, ai-008 -- the ledger's population is every hypothesis
    # the check examined, which includes the attempts that were refused and
    # never became a delivered generation.
    bundle = fault_bundle()
    passing = check(a_hypothesis(), bundle)
    failing = check(a_hypothesis(kinds=[("NOT-A-RULE", "nope")]), bundle)
    led = ledger_over((HOSTED, failing), (HOSTED, passing), (TEMPLATE, passing))

    stats = summary(a_record([generation(1, 1, HOSTED)], ledger=led))

    assert stats.for_arm(HOSTED).checked == 2
    assert stats.for_arm(HOSTED).caught == 1
    assert stats.for_arm(HOSTED).catch_rate == 0.5
    assert stats.for_arm(TEMPLATE).catch_rate == 0.0


def test_the_template_rate_is_labelled_as_the_oracle_reading() -> None:
    # spec: eval-005, ai-002, ai-008 -- the template is grounded by
    # construction, so anything flagged on it is a defect in the CHECK. A
    # reader given two rates side by side and no note would read a non-zero
    # template rate as the baseline inventing citations.
    stats = summary(a_record([generation(1, 1, TEMPLATE)]))

    assert stats.for_arm(TEMPLATE).is_oracle is True
    assert stats.for_arm(HOSTED).is_oracle is False


# --------------------------------------------------- retries and replacements


def test_the_retry_rate_is_a_rate_over_attempts() -> None:
    # spec: eval-005, ai-009 -- "of every call this arm made, what fraction
    # produced an answer nobody could use". Over *generations* instead it
    # would be an average number of retries wearing the word rate, and a
    # bundle retried twice would push it above 1.0; over *bundles* it would
    # report 1 where a bundle retried twice cost twice. The denominator is
    # reported beside it either way.
    record = a_record(
        [
            generation(1, 1, HOSTED, refusals=(refusal(1), refusal(2))),
            generation(2, 1, HOSTED),
        ]
    )

    hosted = summary(record).for_arm(HOSTED)

    assert hosted.attempts == 4, "two generations, one of which took three"
    assert hosted.refusals == 2
    assert hosted.retry_rate == 0.5


def test_the_refusals_are_split_by_why_they_were_refused() -> None:
    # spec: eval-005, ai-007 -- malformed and ungrounded are kept apart
    # because a schema-constrained arm breaking its own guarantee is a more
    # alarming event than a wrong citation, and an aggregate loses it.
    record = a_record(
        [
            generation(
                1,
                1,
                HOSTED,
                refusals=(
                    refusal(1, RefusalCategory.MALFORMED),
                    refusal(2, RefusalCategory.UNGROUNDED, row=7),
                ),
            )
        ]
    )

    hosted = summary(record).for_arm(HOSTED)

    assert hosted.refusals_by_category == {"malformed": 1, "ungrounded": 1}


def test_the_fallback_rate_is_reported_because_it_is_a_reliability_result() -> None:
    # spec: eval-005, ai-007, db-002 -- how often a model arm had to be
    # replaced is a result in its own right, and it is only measurable at
    # all because a row now records which arm was asked.
    record = a_record(
        [
            generation(1, 1, HOSTED, generator=TEMPLATE),
            generation(2, 1, HOSTED),
            generation(3, 1, HOSTED),
            generation(4, 1, HOSTED),
        ]
    )

    hosted = summary(record).for_arm(HOSTED)

    assert hosted.fell_back == 1
    assert hosted.fallback_rate == 0.25


def test_a_skipped_generation_is_reported_and_not_silently_absent() -> None:
    # spec: eval-005, ai-012 -- a bundle nobody could answer is a corpus
    # quietly smaller than the pre-registered one, and the count is how a
    # reader sees it happened.
    record = a_record(
        [generation(1, 1, HOSTED)],
        skipped=[
            SkippedGeneration(
                bundle_id=2, ordinal=1, requested_arm=HOSTED, reason="unreachable"
            )
        ],
    )

    assert summary(record).for_arm(HOSTED).skipped == 1


# ------------------------------------------------------------ what it cost


def test_cost_and_tokens_are_attributed_per_arm() -> None:
    # spec: eval-005, ai-009 -- the arm is on the call record rather than
    # read off a result, because a refused call has no result and those are
    # exactly the calls a retry rate is made of.
    record = a_record(
        [generation(1, 1, HOSTED)],
        calls=(
            served(1, HOSTED, usage=usage(cost=0.02)),
            refused_call(2, HOSTED, usage=usage(cost=0.01)),
            served(3, LOCAL, usage=usage(cost=None)),
        ),
    )

    stats = summary(record)

    assert stats.for_arm(HOSTED).calls == 2
    assert stats.for_arm(HOSTED).spent_usd == pytest.approx(0.03)
    assert stats.for_arm(HOSTED).cost_is_complete is True
    assert stats.for_arm(LOCAL).calls == 1
    assert stats.for_arm(LOCAL).unpriced_calls == 1


def test_an_unpriced_call_makes_that_arm_s_total_a_lower_bound() -> None:
    # spec: eval-005, ai-009 -- an unpriced call is unmeasurable, not free,
    # and this item reports cost as a result. Per arm, because a local arm
    # prices nothing while a hosted one prices everything, and one flag for
    # the campaign would call the hosted figure incomplete.
    record = a_record(
        [generation(1, 1, HOSTED), generation(1, 1, LOCAL)],
        calls=(served(1, HOSTED), served(2, LOCAL, usage=usage(cost=None))),
    )

    stats = summary(record)

    assert stats.for_arm(HOSTED).cost_is_complete is True
    assert stats.for_arm(LOCAL).cost_is_complete is False


def test_wall_time_is_summed_per_arm() -> None:
    # spec: eval-005 -- write-up material, and the template's near-zero
    # figure beside a model's is the concrete form of the claim that the
    # baseline costs nothing to run.
    record = a_record(
        [
            generation(1, 1, HOSTED, seconds=2.0),
            generation(2, 1, HOSTED, seconds=3.0),
            generation(1, 1, TEMPLATE, seconds=0.01),
        ]
    )

    stats = summary(record)

    assert stats.for_arm(HOSTED).seconds == pytest.approx(5.0)
    assert stats.for_arm(TEMPLATE).seconds == pytest.approx(0.01)


# ------------------------------------------------ how much the answers varied


def test_agreement_is_measured_over_the_three_things_that_can_vary() -> None:
    # spec: eval-005 -- the item asks for grounding variance, and the trial
    # says that will be zero: grounding passed every citation of every
    # generation and confidence was stable on every pair. What moved was the
    # cited set. A report carrying only grounding agreement prints 1.0 and
    # misses the finding.
    same = a_hypothesis(kinds=[("RF-NOISE", "rf_deviation")])
    other = a_hypothesis(kinds=[("RF-NOISE", "rf_deviation"), ("X", "y")])
    record = a_record([generation(1, n, HOSTED) for n in (1, 2, 3)])
    hypotheses = {101: same, 102: same, 103: other}

    variation = summary(record, hypotheses).for_arm(HOSTED).agreement

    assert variation.bundles == 1
    assert variation.grounding == 1.0
    assert variation.confidence == 1.0
    assert variation.cited_kinds == 0.0, "one bundle, and its three disagree"


def test_a_bundle_asked_once_cannot_disagree_with_itself() -> None:
    # spec: eval-005 -- agreement is undefined over a single generation, and
    # counting it as agreement would inflate every figure here with bundles
    # that were never asked twice. The template arm is always N=1.
    record = a_record([generation(1, 1, TEMPLATE)])

    variation = summary(record).for_arm(TEMPLATE).agreement

    assert variation.bundles == 0
    assert variation.grounding is None
    assert variation.cited_kinds is None


def test_agreement_is_on_the_set_of_kinds_and_not_their_order() -> None:
    # spec: eval-005, ai-001 -- a citation stands for a KIND of evidence,
    # and two answers citing the same two kinds in the other order have not
    # disagreed about anything the study is asking about.
    pair = [("RF-NOISE", "rf_deviation"), ("TRACK-GAP", "gap")]
    record = a_record([generation(1, n, HOSTED) for n in (1, 2)])
    hypotheses = {
        101: a_hypothesis(kinds=pair),
        102: a_hypothesis(kinds=list(reversed(pair))),
    }

    variation = summary(record, hypotheses).for_arm(HOSTED).agreement

    assert variation.cited_kinds == 1.0


def test_a_confidence_that_moved_between_generations_is_visible() -> None:
    # spec: eval-005 -- the trial found confidence stable on every pair,
    # which is the reassuring half of the non-determinism finding. If that
    # stops holding at twenty bundles it is a far more serious result than
    # varying wording, and nothing else would report it.
    record = a_record([generation(1, n, HOSTED) for n in (1, 2)])
    hypotheses = {
        101: a_hypothesis(confidence=Confidence.HIGH),
        102: a_hypothesis(confidence=Confidence.MEDIUM),
    }

    variation = summary(record, hypotheses).for_arm(HOSTED).agreement

    assert variation.confidence == 0.0


def test_a_generation_whose_hypothesis_was_not_supplied_is_refused() -> None:
    # spec: eval-005 -- a mapping quietly missing a row would drop that
    # generation from the agreement figures while every count beside them
    # still included it, so the two halves of one report would describe
    # different populations.
    record = a_record([generation(1, n, HOSTED) for n in (1, 2)])

    with pytest.raises(ConfigurationError, match="no hypothesis"):
        summarise(record, hypotheses={101: a_hypothesis()})


def test_asking_for_an_arm_the_report_does_not_carry_is_an_error() -> None:
    # spec: eval-005 -- summarise() builds one entry per arm, so this is
    # unreachable through it and is a guard against a report assembled some
    # other way. Returning None instead would put "this arm was never asked"
    # and "you asked the wrong question" into the same answer, which is the
    # collapse this project refuses everywhere else.
    from app.evaluation.statistics import CampaignStatistics

    empty = CampaignStatistics(arms=())

    with pytest.raises(KeyError):
        empty.for_arm(HOSTED)


# ------------------------------------------------------------- the artefact


def test_the_report_serialises_to_json() -> None:
    # spec: eval-005, eval-003 -- these are thesis-table numbers, so they
    # have to leave the process in a shape a table can be built from.
    record = a_record(
        [generation(1, n, HOSTED) for n in (1, 2)] + [generation(1, 1, TEMPLATE)],
        calls=(served(1), served(2)),
    )

    written = json.loads(json.dumps(summary(record).as_json()))

    assert {arm["arm"] for arm in written["arms"]} == {"hosted", "template", "local"}
    hosted = next(a for a in written["arms"] if a["arm"] == "hosted")
    assert hosted["generations"] == 2
    assert hosted["agreement"]["bundles"] == 1
    local = next(a for a in written["arms"] if a["arm"] == "local")
    assert local["catch_rate"] is None


def test_the_serialised_report_carries_no_hypothesis_text() -> None:
    # spec: eval-005, NFR-405 -- it is a table of figures, and a bundle's
    # prose carries pseudonymised aircraft identifiers. The hypotheses are
    # in the database; this is the arithmetic over them.
    record = a_record([generation(1, 1, HOSTED)])

    written = json.dumps(summary(record).as_json())

    assert "supporting_evidence" not in written
    assert "AC-" not in written
